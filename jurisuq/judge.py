"""Correctness resolution without ground-truth labels at query time.

The judge runs *offline*, on the development split, exactly as in [SE24] and
[EVSE26]: it converts a sampled answer into 1/0 so that uncertainty scores can
be evaluated. It is never called on the query path.

Three outcomes, not two
-----------------------
``correct = True``   the operative provision in the answer is the in-force one
``correct = False``  the answer asserts a provision (or an act) other than the
                     in-force one, so it answers the question wrongly
``correct = None``   the answer does not settle which provision applies: either
                     it names none at all, or it names two without saying which
                     one governs

Unresolvable answers are *excluded* from the metrics and counted in the report.
Counting them as wrong would report a model as 0 % accurate when the truth is
that the judge could not read the answer; ignoring them silently would hide a
broken judge. Both failure modes destroyed an earlier run, which is why the
distinction is explicit here and printed by the harness.

What revision 2 adds, each from a real observed failure
------------------------------------------------------
* **Act-level errors.** "The Indian Penal Code would apply" names no section.
  On a question about today's law that is a stale answer, so it is *wrong*, not
  unresolvable.
* **Foreign jurisdiction.** One sampled answer cited a South African Act. The
  judge now recognises a non-Indian legal order and reports it as its own
  error kind, because that is a different failure from picking the wrong
  section of the right code.
* **Repealed-code detection.** Asserting a provision of the IPC, CrPC or the
  Evidence Act as the operative law on a question about today falls under
  ``stale_law``; asserting a BNS provision on a question about 2023 falls under
  ``premature_law``. The two directions are reported separately because they are
  different mistakes.
* **No dependence on the trap table.** Correctness is decided against the gold
  provision only. The trap and the distractor are used to *explain* an error,
  never to decide it, so a wrong trap row can no longer manufacture a wrong
  verdict.
"""
from __future__ import annotations

import collections
import json
import re
from dataclasses import dataclass

from .normalize import (REPEALED_CODES, act_level_mentions, act_key,
                        find_mentions, foreign_marker, is_operative, match_kind,
                        sentence_around)


@dataclass
class Verdict:
    correct: bool | None
    label: str
    reason: str = ""
    method: str = ""
    # the provision the answer asserts, as a comparable key:
    #   {"act": "IPC", "provision": "302"}   a specific provision
    #   {"act": "IPC", "provision": None}    only the act is named
    #   {"act": "FOREIGN", "provision": "..."} another legal order
    #   None                                 nothing recognised
    # This is what makes provision-level agreement measurable: two samples that
    # word the same wrong provision differently are the *same* wrong answer, and
    # only this key can say so. It is also the input to the staleness table.
    asserted: dict | None = None

    @property
    def resolved(self) -> bool:
        return self.correct is not None


# labels that mean "the judge could not decide", used by the analysis scripts
UNRESOLVED_LABELS = ("unresolved", "ambiguous", "no_provision_named",
                     "only_superseded_mentioned")


def _assertion(mention: dict | None, text: str = "") -> dict | None:
    """Comparable key for the provision a mention asserts."""
    if mention is None:
        return None
    num = mention.get("num")
    if mention.get("sub"):
        num = f"{num}({mention['sub']})"
    act = mention.get("act")
    if act is None and text and foreign_marker(sentence_around(text, mention["pos"])):
        act = "FOREIGN"
    return {"act": act, "provision": num}


def _classify_wrong(text: str, mention: dict | None, gold_act: str | None,
                    gold_note: str = "") -> tuple[str, str]:
    """Name the kind of error. Purely for reporting; correctness is already decided."""
    gold_key = act_key(gold_act or "")
    if mention is None:
        # act-level error: an act was named, no section given
        return "stale_law_act_only", gold_note or "names a code as applying, without a section"
    act = mention.get("act")
    sent = sentence_around(text, mention["pos"])
    if foreign_marker(sent) or foreign_marker(mention["raw"]):
        return "non_indian_act", f"invokes a non-Indian legal order near {mention['raw']!r}"
    if mention["act"] and gold_key:
        if mention["act"] in REPEALED_CODES and gold_key not in REPEALED_CODES:
            return "stale_law", f"asserts {mention['raw']!r} from a code repealed on 1 July 2024"
        if mention["act"] not in REPEALED_CODES and gold_key in REPEALED_CODES:
            return "premature_law", (f"asserts {mention['raw']!r}, which did not exist before "
                                     f"1 July 2024")
        if mention["act"] == gold_key:
            return "wrong_section", f"asserts {mention['raw']!r}, a different section of the same act"
    if act is None:
        return "other_provision", f"asserts {mention['raw']!r}, which is not the applicable provision"
    return "wrong_act", f"asserts {mention['raw']!r} from the wrong act"


class ProvisionJudge:
    method = "provision"

    def score(self, item: dict, answer: str) -> Verdict:
        text = answer or ""
        gold = item.get("gold") or {}
        gold_act = gold.get("act")
        gold_prov = gold.get("provision")

        mentions = find_mentions(text)
        gold_hits = [(m, match_kind(m, gold_prov, gold_act)) for m in mentions] if gold_prov else []
        gold_hits = [(m, k) for m, k in gold_hits if k]
        others = [m for m in mentions if not (gold_prov and match_kind(m, gold_prov, gold_act))]

        # ---- the in-force provision is stated ---------------------------
        if gold_hits:
            gold_asserted = _assertion(gold_hits[0][0], text)
            if not others:
                return Verdict(True, "gold", "states the applicable provision and nothing "
                                             "that conflicts with it", self.method,
                               asserted=gold_asserted)
            unmarked = [m for m in others if not m["repeal_cue"]]
            if not unmarked:
                return Verdict(True, "gold_with_superseded_note",
                               "states the applicable provision and marks the other one as "
                               "superseded", self.method, asserted=gold_asserted)
            # a reference to another legal order is not a conflict with Indian law
            unmarked = [m for m in unmarked
                        if not foreign_marker(sentence_around(text, m["pos"]))]
            if not unmarked:
                return Verdict(True, "gold_with_foreign_note",
                               "states the applicable provision; the other reference is to a "
                               "foreign legal order", self.method, asserted=gold_asserted)
            gold_op = any(is_operative(text, m) for m, _ in gold_hits)
            other_op = any(is_operative(text, m) for m in unmarked)
            gold_first = min(m["pos"] for m, _ in gold_hits) < min(m["pos"] for m in unmarked)
            if gold_op and not other_op:
                return Verdict(True, "gold_operative",
                               "states the applicable provision as the one that governs",
                               self.method, asserted=gold_asserted)
            if gold_first and not other_op:
                return Verdict(True, "gold_first",
                               "states the applicable provision first, as the governing one",
                               self.method, asserted=gold_asserted)
            if gold_first and len(gold_hits) >= len(unmarked):
                return Verdict(True, "gold_first_only",
                               "states the applicable provision first", self.method,
                               asserted=gold_asserted)
            return Verdict(None, "ambiguous",
                           "names the applicable provision and another one without saying which "
                           "governs", self.method)

        # ---- the in-force provision is not stated ------------------------
        if others:
            first = min(others, key=lambda m: m["pos"])
            label, why = _classify_wrong(text, first, gold_act)
            return Verdict(False, label, why, self.method,
                           asserted=_assertion(first, text))

        # ---- nothing with a section number: check for act-level answers ---
        foreign = foreign_marker(text)
        if foreign:
            return Verdict(False, "non_indian_act",
                           f"invokes a non-Indian legal order ({foreign!r}) and names no "
                           f"applicable Indian provision", self.method,
                           asserted={"act": "FOREIGN", "provision": foreign})

        acts = act_level_mentions(text)
        if acts:
            stale = [a for a in acts if a["act"] in REPEALED_CODES]
            current = [a for a in acts if a["act"] in ("BNS", "BNSS", "BSA")]
            gold_key = act_key(gold_act or "")
            if stale and gold_key not in REPEALED_CODES:
                return Verdict(False, "stale_law_act_only",
                               f"asserts {stale[0]['raw']!r} as applying, without a section; that "
                               f"code was repealed on 1 July 2024", self.method,
                               asserted={"act": stale[0]["act"], "provision": None})
            if current and gold_key in REPEALED_CODES:
                return Verdict(False, "premature_law_act_only",
                               f"asserts {current[0]['raw']!r}, which did not exist before "
                               f"1 July 2024", self.method,
                               asserted={"act": current[0]["act"], "provision": None})
            if not gold_key and stale:
                return Verdict(False, "stale_law_act_only",
                               f"asserts {stale[0]['raw']!r} as applying", self.method,
                               asserted={"act": stale[0]["act"], "provision": None})
            return Verdict(None, "no_provision_named",
                           "names an act but no section, and it is not decisive", self.method,
                           asserted={"act": acts[0]["act"], "provision": None})

        if re.search(r"\bno (?:specific|particular) provision\b|\bcannot (?:be )?(?:say|determine)\b",
                     text, re.I):
            return Verdict(None, "declines",
                           "the answer declines to name a provision", self.method)
        return Verdict(None, "unresolved", "no provision and no act recognised in the answer",
                       self.method)


class LLMJudge:
    """Prompted correctness judge. Needs a working generator endpoint."""

    method = "llm"

    PROMPT = """You are a strict legal answer checker. Decide whether the CANDIDATE answer gives the \
provision of law asked about in the QUESTION.

QUESTION:
{question}

WHAT COUNTS AS CORRECT:
- the provision that applies in the era the question asks about: {gold_act}, section {gold_provision}
- an answer that also mentions the other code's provision is still correct if it makes clear which one applies.

WHAT COUNTS AS INCORRECT:
- an answer whose operative provision is {trap_desc}
- an answer that cites a provision of a repealed code as the law in force today
- an answer that cites the law of a country other than India
- an answer that cites no provision at all.

CANDIDATE ANSWER:
{answer}

Reply with JSON only, no prose: {{"verdict": "correct" | "incorrect", "reason": "<12 words max>"}}"""

    def __init__(self, generator, max_tokens: int = 96):
        self.gen = generator
        self.max_tokens = max_tokens

    def _trap_desc(self, item: dict) -> str:
        trap = item.get("trap") or {}
        if trap.get("provision"):
            return f"{trap.get('act')}, section {trap['provision']}"
        return "a provision other than the one stated above"

    def score(self, item: dict, answer: str) -> Verdict:
        prompt = self.PROMPT.format(
            question=item.get("question", ""),
            gold_act=(item.get("gold") or {}).get("act", ""),
            gold_provision=(item.get("gold") or {}).get("provision", ""),
            trap_desc=self._trap_desc(item),
            answer=(answer or "").strip()[:1500],
        )
        res = self.gen.one(prompt, temperature=0.0, max_tokens=self.max_tokens)
        text = res.text
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            try:
                data = json.loads(m.group(0))
                verdict = str(data.get("verdict", "")).lower()
                reason = str(data.get("reason", ""))[:120]
                if verdict.startswith("corr"):
                    return Verdict(True, "llm_correct", reason, self.method)
                if verdict.startswith("inc"):
                    return Verdict(False, "llm_incorrect", reason, self.method)
            except json.JSONDecodeError:
                pass
        low = text.lower()
        if "incorrect" in low:
            return Verdict(False, "llm_incorrect_unparsed", text[:80], self.method)
        if "correct" in low:
            return Verdict(True, "llm_correct_unparsed", text[:80], self.method)
        return Verdict(None, "llm_unparsed", text[:80], self.method)


class CascadeJudge:
    """Deterministic judge first; the LLM judge only on what it cannot decide."""

    method = "cascade"

    def __init__(self, primary, secondary=None):
        self.primary = primary
        self.secondary = secondary

    def score(self, item: dict, answer: str) -> Verdict:
        v = self.primary.score(item, answer)
        if v.resolved or self.secondary is None:
            return v
        v2 = self.secondary.score(item, answer)
        return Verdict(v2.correct, f"{v.label}|{v2.label}", v2.reason, self.method,
                       asserted=v2.asserted if v2.asserted is not None else v.asserted)


def make_judge(cfg, generator):
    if cfg.judge == "provision":
        return ProvisionJudge()
    if cfg.judge == "llm":
        return CascadeJudge(ProvisionJudge(), LLMJudge(generator))
    raise SystemExit(f"unknown judge: {cfg.judge!r} (use 'provision' or 'llm')")


def label_summary(records: list[dict]) -> dict:
    """How the judge looked on a finished run, for the console and the report."""
    counts: collections.Counter = collections.Counter()
    per_slice: dict[str, collections.Counter] = {}
    for r in records:
        if "error" in r:
            continue
        per_slice.setdefault(r["slice"], collections.Counter())
        labs = r.get("sample_verdict_labels") or []
        if not labs:
            counts["<no labels>"] += 1
            continue
        for lab in labs:
            base = lab.split("|")[-1]          # cascade labels: keep the final verdict
            counts[base] += 1
            per_slice[r["slice"]][base] += 1
    total = sum(counts.values()) or 1
    unresolved = sum(v for k, v in counts.items() if k in UNRESOLVED_LABELS)
    return {"counts": dict(counts),
            "shares": {k: v / total for k, v in counts.items()},
            "resolved_share": 1.0 - unresolved / total,
            "per_slice": {k: dict(v) for k, v in per_slice.items()},
            "n_records": sum(1 for r in records if "error" not in r)}
