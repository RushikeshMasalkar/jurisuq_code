"""Pair construction and structural verification for the relation dataset.

Text generation here is deliberately template-driven: the dataset's purpose is
to teach and test a *relation*, so the lexical surface is varied systematically
while the asserted provision stays exact and checkable. Every generated pair is
passed through the same extractor the pipeline uses at inference time, so a pair
whose asserted key does not round-trip is rejected rather than trained on.
"""
from __future__ import annotations

import itertools
import random
from dataclasses import dataclass

from ..facts import OFFENCES
from ..judge import _assertion
from ..normalize import find_mentions
from .schema import Assertion, PairRecord, make_pair

ACT_NAME = {
    "IPC": "Indian Penal Code",
    "BNS": "Bharatiya Nyaya Sanhita",
    "CRPC": "Code of Criminal Procedure",
    "BNSS": "Bharatiya Nagarik Suraksha Sanhita",
    "IEA": "Indian Evidence Act",
    "BSA": "Bharatiya Sakshya Adhiniyam",
}
DEFAULT_CONTEXT = {"as_of": "2026-10-01", "jurisdiction": "IN", "crosswalk_relation": None}


def asserted_from_text(text: str) -> dict | None:
    """The comparable assertion the pipeline itself would extract from an answer."""
    for m in find_mentions(text):
        a = _assertion(m, text)
        if a is not None:
            return a
    return None


def key_of(asserted: dict | None) -> str:
    return Assertion(**asserted).key() if asserted else "NONE"


# ---- answer surface forms --------------------------------------------------
def form(a: int, act: str, prov: str, label: str, punishment: str) -> str:
    """One of six surface forms asserting (act, prov). Index is deterministic."""
    name = ACT_NAME.get(act, act)
    if a == 0:
        return (f"Provision: {name}, section {prov}\n"
                f"Reason: {label} as defined in the code.\n"
                f"Punishment: {punishment}.")
    if a == 1:
        return f"{label.capitalize()} is punishable under section {prov} of the {name}."
    if a == 2:
        return (f"The applicable provision is s. {prov} {act}. "
                f"The punishment provided is {punishment}.")
    if a == 3:
        return (f"Under the {name}, the offence of {label} falls under s. {prov}; "
                f"the prescribed punishment is {punishment}.")
    if a == 4:
        return (f"Section {prov} {act} applies here. The reason is that the facts "
                f"constitute {label}.")
    return (f"Answer: s. {prov} of the {name}. Reason: the conduct amounts to {label}, "
            f"punishable with {punishment}.")


def ambiguous_form(a: int, act: str, label: str, prov: str) -> str:
    """Act-only or truncated surface forms (stratum S7)."""
    name = ACT_NAME.get(act, act)
    if a == 0:
        return f"The offence of {label} falls under the {name}."
    if a == 1:
        return f"This is governed by the {name}. The specific section is not stated."
    return f"Section {prov} {act} applies to the facts as stated"


@dataclass
class Offence:
    topic: str
    label: str
    old_act: str
    old_prov: str
    new_act: str
    new_prov: str
    punishment: str
    distractor: tuple


def offences() -> list[Offence]:
    out = []
    for topic, rec in OFFENCES.items():
        out.append(Offence(
            topic=topic, label=rec["label"],
            old_act=rec["old"]["act"], old_prov=rec["old"]["provision"],
            new_act=rec["new"]["act"], new_prov=rec["new"]["provision"],
            punishment=rec["punishment"], distractor=tuple(rec["old"]["distractor"]),
        ))
    return out


def _ctx(as_of: str, relation: str | None = None) -> dict:
    return {"as_of": as_of, "jurisdiction": "IN", "crosswalk_relation": relation}


def candidate_pairs(dataset_version: str, seed: int = 20261005) -> list[PairRecord]:
    """Enumerate every candidate pair for the seven strata. Labels are rule-derived."""
    rng = random.Random(seed)
    offs = offences()
    out: list[PairRecord] = []

    def add(tag, ta, tb, ctx, label, stratum, source="rule", cond=None, prov=None,
            split_hint=None):
        aa, ab = asserted_from_text(ta), asserted_from_text(tb)
        rec = make_pair(ta, aa, tb, ab, ctx, label, dataset_version,
                        split=split_hint or "train", stratum=stratum,
                        label_source=source, condition_tag=cond,
                        provenance=prov or {"generator": "template", "topic": tag})
        out.append(rec)

    for o in offs:
        prov, act = o.old_prov, o.old_act
        texts = [form(i, act, prov, o.label, o.punishment) for i in range(6)]
        # S1 easy positive: same provision, both sides explicit
        explicit = (0, 2, 5)
        for i, j in itertools.combinations(explicit, 2):
            add(o.topic, texts[i], texts[j], _ctx("2024-01-01"), "SAME_PROVISION", "S1")
        # S2 hard positive: every remaining same-provision form pair
        for i, j in itertools.combinations(range(6), 2):
            if (i, j) in set(itertools.combinations(explicit, 2)):
                continue
            add(o.topic, texts[i], texts[j], _ctx("2024-01-01"), "SAME_PROVISION", "S2")
        # S3 context dependence: identical text, two as-of dates
        for t in (texts[1], texts[3]):
            add(o.topic, t, t, _ctx("2024-01-01", "successor_of"),
                "CONDITIONALLY_EQUIVALENT", "S3", cond="era:pre-transition",
                prov={"generator": "template", "topic": o.topic,
                       "note": "identical text, context differs"})
            add(o.topic, t, t, _ctx("2026-10-01", "successor_of"),
                "CONDITIONALLY_EQUIVALENT", "S3", cond="era:current",
                prov={"generator": "template", "topic": o.topic,
                       "note": "identical text, context differs"})
        # S4 crosswalk equivalents across the transition
        for i, j in itertools.product(range(3), repeat=2):
            a = form(i, o.old_act, o.old_prov, o.label, o.punishment)
            b = form(j, o.new_act, o.new_prov, o.label, o.punishment)
            add(o.topic, a, b, _ctx("2026-10-01", "successor_of"), "LEGALLY_EQUIVALENT", "S4")
        # S5 hard negative: adjacent section of the same act
        d_act, d_prov, _ = o.distractor
        a = form(0, act, prov, o.label, o.punishment)
        b = form(1, d_act, d_prov, o.label, o.punishment)
        add(o.topic, a, b, _ctx("2024-01-01"), "DIFFERENT_PROVISION", "S5")
        add(o.topic, form(3, act, prov, o.label, o.punishment),
            form(4, d_act, d_prov, o.label, o.punishment), _ctx("2024-01-01"),
            "DIFFERENT_PROVISION", "S5")
        # S6 hard negative: same number, different act
        a = form(0, o.old_act, o.old_prov, o.label, o.punishment)
        b = form(2, o.new_act, o.old_prov, o.label, o.punishment)
        add(o.topic, a, b, _ctx("2026-10-01"), "DIFFERENT_PROVISION", "S6")
        # S7 ambiguous: act-only or truncated
        add(o.topic, ambiguous_form(0, act, o.label, prov),
            ambiguous_form(1, act, o.label, prov), _ctx("2024-01-01"), "AMBIGUOUS", "S7")
        add(o.topic, ambiguous_form(0, act, o.label, prov), texts[0], _ctx("2024-01-01"),
            "AMBIGUOUS", "S7")
        rng.random()  # keep the RNG stream deterministic in call order
    return out


def structural_verify(rec: PairRecord) -> list[str]:
    """Label-consistency checks that need no human: what the pair claims vs what it says.

    These rules are the Phase B analogue of the judge's gold-only correctness rule:
    a pair is only usable if its label is entailed by keys that the pipeline itself
    extracted, the context it was given, and the crosswalk link it declares.
    """
    bad: list[str] = []
    ka, kb = rec.key_a(), rec.key_b()
    link = rec.context.get("crosswalk_relation")
    if rec.label == "SAME_PROVISION":
        if ka == "NONE" or kb == "NONE":
            bad.append("SAME_PROVISION with an unresolved assertion")
        elif ka != kb:
            bad.append(f"SAME_PROVISION but keys differ ({ka} vs {kb})")
    elif rec.label == "LEGALLY_EQUIVALENT":
        if ka == kb:
            bad.append("LEGALLY_EQUIVALENT but the keys are identical")
        if not link:
            bad.append("LEGALLY_EQUIVALENT without a crosswalk link in the context")
    elif rec.label == "CONDITIONALLY_EQUIVALENT":
        if not rec.condition_tag:
            bad.append("CONDITIONALLY_EQUIVALENT without a condition tag")
    elif rec.label == "DIFFERENT_PROVISION":
        if ka == kb and ka != "NONE":
            bad.append("DIFFERENT_PROVISION but the keys are identical")
        if link in ("successor_of", "same_offence_as", "definition_of", "merged_into"):
            bad.append(f"DIFFERENT_PROVISION contradicted by a crosswalk link {link!r}")
    elif rec.label == "AMBIGUOUS":
        if ka != "NONE" and kb != "NONE" and ka == kb:
            bad.append("AMBIGUOUS but both answers assert the same resolved provision")
    return bad
