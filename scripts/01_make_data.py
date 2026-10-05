#!/usr/bin/env python3
"""01 - build the diagnostic slice (Phase A, gate G1 data), revision 2.

Design, in one paragraph. Every offence yields a *matched pair* of questions
built from identical facts, identical frame wording and identical context; the
only difference is the era the question asks about:

  L7  "under the law in force today (after 1 July 2024) ..."  gold = the BNS
      provision. The tempting answer is the repealed IPC section, which a model
      trained before the transition will produce confidently and repeatedly.

  L1  "as the law stood immediately before 1 July 2024 ..."    gold = the IPC
      provision. Same facts, same difficulty of provision lookup, no staleness
      trap. This is the control: it measures whether the model can do this
      *kind* of question at all, separately from whether it is out of date.

Revision 1 used a control that asked today's law as well; on a real 7B model
almost nothing could be scored, because the model did not know the new codes at
all, so the control produced no correct answers and the comparison was
degenerate. The era-reversed control fixes that: it is answerable by the same
model with the same effort, and the L7-minus-L1 difference isolates staleness.

    python scripts/01_make_data.py                       # 100 + 100 items
    python scripts/01_make_data.py --n-per-slice 150

Output: data/lexuq_slice.jsonl (one JSON object per item, with pair_id),
        data/lexuq_slice_summary.json
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jurisuq.config import ROOT
from jurisuq.facts import ERAS, OFFENCES, TRANSITION_DATE, TRANSITION_NOTE

# ----------------------------------------------------------------------
# frames: {era_phrase} makes the asked-about era explicit in every question
# ----------------------------------------------------------------------
FRAMES = {
    "T1": "{ctx} Under the law in force in India {era_phrase}, which section applies to this "
          "situation, and what is the punishment prescribed? {fact}",
    "T2": "{ctx} A client asks which provision of the penal law governs the following facts under "
          "the law in force in India {era_phrase}. Give the act and the section. {fact}",
    "T3": "{ctx} Identify the offence and the section that applies {era_phrase}. {fact}",
    "T4": "{ctx} The Indian Penal Code was replaced by the Bharatiya Nyaya Sanhita with effect from "
          "1 July 2024. Which section applies to these facts {era_phrase}, and which section of the "
          "other code corresponds to it? {fact}",
    "T5": "{ctx} State the section under which the accused should be charged {era_phrase}, and the "
          "act in which that section appears. {fact}",
    "T6": "{ctx} A junior lawyer needs the exact provision {era_phrase}. Which act and which "
          "section apply? {fact}",
}

# Neutral procedural contexts: they do not alter the offence, they make the item
# text unique and stop the same wording appearing twice in a slice.
CONTEXTS = [
    "A first information report has been registered.",
    "The matter is at the stage of framing of charges.",
    "The question arises during a bail hearing.",
    "The question arises in a written opinion for a client.",
    "The question is put by the court during arguments.",
    "The matter is before a magistrate for committal.",
]


def make_item(slice_name: str, topic: str, spec: dict, frame: str, ctx: str,
              n: int, rng: random.Random) -> dict:
    era = ERAS[slice_name]
    gold_side = spec[era["gold"]]
    trap_side = spec[era["trap"]]
    d_act, d_prov, d_label = gold_side["distractor"]

    return {
        "item_id": f"{slice_name}-{topic}-{n:03d}",
        "pair_id": f"{topic}-{n:03d}",          # links the L1 and L7 twins
        "slice": slice_name,
        "era": "current" if era["gold"] == "new" else "pre2024",
        "asked_about": era["label"],
        "topic": topic,
        "template": frame,
        "question": FRAMES[frame].format(ctx=ctx, fact=spec["fact"],
                                         era_phrase=era["era_phrase"]),
        "gold": {"act": gold_side["act"], "provision": gold_side["provision"],
                 "label": spec["label"]},
        "trap": {"act": trap_side["act"], "provision": trap_side["provision"],
                 "label": era["tempting"]},
        "distractor": {"act": d_act, "provision": d_prov, "label": d_label},
        # fields used by the mock generator and by the reviewer's cross-check
        "gold_act": gold_side["act"],
        "gold_provision": gold_side["provision"],
        "trap_act": trap_side["act"],
        "trap_provision": trap_side["provision"],
        "distractor_provision": d_prov,
        "punishment": spec.get("punishment"),
        "provenance": {
            "source": "synthetic, from statute structure",
            "built_from": "official successor mapping IPC <-> BNS plus the offence description",
            "verified": False,
            "transition_date": TRANSITION_DATE,
            "note": TRANSITION_NOTE,
        },
    }


def build(n_per_slice: int, seed: int) -> list[dict]:
    """Deterministic construction with matched pairs and unique question text."""
    rng = random.Random(seed)
    topics = sorted(OFFENCES)
    frames = sorted(FRAMES)
    items: list[dict] = []

    combos = [(t, f, c) for t in topics for f in frames for c in CONTEXTS]
    rng.shuffle(combos)
    if n_per_slice > len(combos):
        raise ValueError(f"only {len(combos)} unique (offence, frame, context) combinations "
                         f"available; asked for {n_per_slice}")

    for n, (topic, frame, ctx) in enumerate(combos[:n_per_slice]):
        for slice_name in ("L7", "L1"):
            items.append(make_item(slice_name, topic, OFFENCES[topic], frame, ctx, n, rng))

    for s in ("L7", "L1"):
        sub = [i for i in items if i["slice"] == s]
        dupes = len(sub) - len({i["question"] for i in sub})
        if dupes:
            raise AssertionError(f"{dupes} duplicate question texts in slice {s}")
    rng.shuffle(items)
    return items


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-per-slice", type=int, default=100)
    ap.add_argument("--seed", type=int, default=20261005)
    ap.add_argument("--out", default=str(ROOT / "data" / "lexuq_slice.jsonl"))
    args = ap.parse_args()

    items = build(args.n_per_slice, args.seed)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w") as fh:
        for it in items:
            fh.write(json.dumps(it) + "\n")

    summary = {
        "revision": 2,
        "design": "matched pairs across the 1 July 2024 transition; era-reversed control",
        "n_items": len(items),
        "n_per_slice": args.n_per_slice,
        "slices": {
            "L7": {"n": sum(1 for i in items if i["slice"] == "L7"),
                   "asks": "law in force today", "gold_act": "BNS",
                   "trap": "the repealed IPC section"},
            "L1": {"n": sum(1 for i in items if i["slice"] == "L1"),
                   "asks": "law as it stood immediately before 1 July 2024", "gold_act": "IPC",
                   "trap": "the successor BNS section"},
        },
        "topics": sorted({i["topic"] for i in items}),
        "templates": {t: sum(1 for i in items if i["template"] == t) for t in FRAMES},
        "seed": args.seed,
        "crosswalk_verified": False,
        "warning": ("The IPC <-> BNS rows in jurisuq/facts.py are the published successor mappings "
                    "and are flagged verified=False. Check them against the official crosswalk and "
                    "the gazette text before treating this slice as the released benchmark."),
    }
    (out.parent / "lexuq_slice_summary.json").write_text(json.dumps(summary, indent=2) + "\n")

    print(f"wrote {len(items)} items ({args.n_per_slice} per slice) -> {out}")
    print(f"  L7  asks the law in force today          gold = BNS   trap = repealed IPC section")
    print(f"  L1  asks the law before 1 July 2024      gold = IPC   trap = successor BNS section")
    print(f"  matched pairs: {args.n_per_slice}   topics: {len(summary['topics'])}   "
          f"frames: {len(FRAMES)}   contexts: {len(CONTEXTS)}")
    print("  reminder: verify the crosswalk in jurisuq/facts.py before freezing this slice")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
