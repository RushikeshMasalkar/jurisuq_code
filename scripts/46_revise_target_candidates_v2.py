"""46_revise_target_candidates_v2.py -- build the v2 candidate set from v1.

Why this exists
---------------
`data/lexuq_target_candidates_v1.jsonl` has already been screened. Its bytes are
recorded as ``data_sha256`` inside three committed screen reports, so it must
never be edited in place: rewriting a row would silently detach those reports
from the dataset they were taken over. Corrections therefore go into a **new
versioned file**, and v1 stays exactly as it was.

What v2 changes
---------------
Four L7 items, decided after the AI-assisted label review in
``reports/phaseG_l7_label_review_v1.md`` and recorded, with the legal source and
the reasoning for each, in ``runs/phaseG_l7_candidate_revisions_v1.json``:

* ``criminal_breach_of_trust-c003`` -- the facts name an *agent*, so the tier is
  BNS 316(5) and the repealed counterpart is IPC 409, not 316(2)/406;
* ``culpable_homicide-c003`` -- the fact pattern is given the knowledge cue it
  was missing, and the gold becomes the subsection it now entails, 105(2);
* ``wrongful_restraint-c001`` -- the facts are re-authored as a plain
  obstruction, which is what BNS 126(2) actually punishes;
* ``wrongful_restraint-c003`` -- locking a compound gate is confinement, so the
  gold becomes BNS 127(2), the trap becomes its repealed counterpart IPC 342,
  and the distractor moves to 126(2).

Everything else is copied through **byte for byte**: the 12 L1 items and the 8
untouched L7 items are emitted as the raw v1 lines they came from, so a diff
between v1 and v2 shows only the four revised rows.

This is an AI-assisted revision. It is **not** human legal approval: every item
still carries ``provenance.verified = false`` and ``review.status =
PENDING_HUMAN_REVIEW``, and the revision block records who decided what and on
what basis.

    python scripts/46_revise_target_candidates_v2.py            # write v2
    python scripts/46_revise_target_candidates_v2.py --check    # verify only

No model is called and the network is not touched.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

V1 = ROOT / "data" / "lexuq_target_candidates_v1.jsonl"
V2 = ROOT / "data" / "lexuq_target_candidates_v2.jsonl"

#: The decided revisions. Keys are ``pair_id`` values, which are unique per
#: topic-and-variant in this set. Each entry lists only the fields it changes.
REVISIONS: dict[str, dict] = {
    "criminal_breach_of_trust-c003": {
        "decided_by": "operator decision, 2026-10-27, on the AI-assisted review "
                      "in reports/phaseG_l7_label_review_v1.md",
        "reason": "The facts state that A was 'B's agent for collecting rent' and "
                  "used the rent himself. BNS 316 punishes criminal breach of trust "
                  "in tiers by capacity: 316(2) is the general tier reproducing IPC "
                  "406, while 316(5) reproduces IPC 409 for a public servant or a "
                  "person entrusted in the way of his business as a banker, "
                  "merchant, factor, broker, attorney or agent, and carries "
                  "imprisonment for life or up to ten years and fine. An agent is "
                  "named in 316(5), so the v1 gold (316(2)) and the v1 trap (IPC "
                  "406) both understate the tier and mis-identify the repealed "
                  "counterpart.",
        "sources": ["https://devgan.in/bns/section/316/",
                    "https://lawrato.com/bharatiya-nyaya-sanhita/bns-section-316"],
        "fields": {
            "gold_provision": "316(5)",
            "trap_provision": "409",
            "punishment": "imprisonment for life, or up to ten years, and fine",
        },
        "provenance": {
            "section_pair": {"bns": "316(5)", "ipc": "409"},
            "mapping_note": "BNS 316 consolidates IPC 405-409 into one section with "
                            "five sub-sections: 316(2)<-406, 316(3)<-407, "
                            "316(4)<-408 and 316(5)<-409. The facts name an agent, "
                            "which is the 316(5)/409 tier; v1 collapsed the section "
                            "to the general tier and paired it with IPC 406.",
        },
    },
    "culpable_homicide-c003": {
        "decided_by": "operator decision, 2026-10-27, on the AI-assisted review "
                      "in reports/phaseG_l7_label_review_v1.md",
        "reason": "v1 negated intention but said nothing about knowledge, which is "
                  "the element separating culpable homicide punished under BNS "
                  "105(2) (knowledge that the act is likely to cause death, up to "
                  "ten years and fine) from causing death by negligence under BNS "
                  "106(1). With knowledge stated, 105(2) follows and 106(1) is no "
                  "longer available; the item tests the repealed-code phenomenon "
                  "instead of an ambiguity.",
        "sources": ["https://devgan.in/bns/section/105/",
                    "https://devgan.in/bns/section/106/"],
        "fields": {
            "question": "Under the law in force in India today (after 1 July 2024), "
                        "which section applies to this situation, and what is the "
                        "punishment prescribed? A pushed B during a quarrel, not "
                        "intending death or injury likely to cause it, but knowing "
                        "that the push was likely to make B fall and strike his head "
                        "on the stone floor; B fell, struck his head and died.",
            "gold_provision": "105(2)",
            "punishment": "up to ten years and fine (the knowledge limb of BNS 105)",
        },
        "provenance": {
            "section_pair": {"bns": "105(2)", "ipc": "304"},
            "mapping_note": "BNS 100 restates IPC 299 and BNS 101 restates IPC 300. "
                            "BNS 105(1) covers the intention limbs and 105(2) the "
                            "knowledge limb of former IPC 304. The fact pattern now "
                            "states knowledge expressly, so the gold is the "
                            "subsection that limb entails.",
        },
    },
    "wrongful_restraint-c001": {
        "decided_by": "operator decision, 2026-10-27, on the AI-assisted review "
                      "in reports/phaseG_l7_label_review_v1.md",
        "reason": "v1 had A block the only exit of the room B was in. That restrains "
                  "B so as to prevent proceeding beyond the circumscribing limits of "
                  "the room, which is wrongful confinement under BNS 127, not "
                  "restraint under BNS 126. The facts are re-authored as a plain "
                  "obstruction so that the item tests 126(2) as intended; the gold "
                  "is unchanged.",
        "sources": ["https://devgan.in/bns/section/126/",
                    "https://devgan.in/bns/section/127/"],
        "fields": {
            "question": "Under the law in force in India today (after 1 July 2024), "
                        "which section applies to this situation, and what is the "
                        "punishment prescribed? A stood in the road in front of B's "
                        "car and refused to move, so that B could not drive on, "
                        "without B's consent.",
        },
        "provenance": {
            "section_pair": {"bns": "126(2)", "ipc": "341"},
            "mapping_note": "BNS 126(1) is wrongful restraint (IPC 339); 126(2) is "
                            "the punishment (IPC 341). The fine ceiling rose from "
                            "five hundred to five thousand rupees. The fact pattern "
                            "was re-authored in v2 to a plain obstruction so that it "
                            "does not describe confinement under BNS 127.",
        },
    },
    "wrongful_restraint-c003": {
        "decided_by": "operator decision, 2026-10-27, on the AI-assisted review "
                      "in reports/phaseG_l7_label_review_v1.md",
        "reason": "A locks the gate of B's compound from outside so that B cannot "
                  "leave. B is restrained so as to prevent proceeding beyond the "
                  "circumscribing limits of the compound; Illustration 1 to BNS 127 "
                  "is the lock-in case. The gold therefore moves to 127(2), its "
                  "repealed counterpart moves to IPC 342 (the confinement "
                  "punishment, not the restraint punishment in IPC 341), and the "
                  "distractor moves to 126(2), which is now the plausible wrong "
                  "answer.",
        "sources": ["https://devgan.in/bns/section/127/",
                    "https://devgan.in/bns/section/126/"],
        "fields": {
            "gold_provision": "127(2)",
            "trap_provision": "342",
            "punishment": "up to one year, or fine up to five thousand rupees, or both",
            "distractor_provision": "126(2)",
            "distractor": {"act": "BNS", "provision": "126(2)",
                           "label": "wrongful restraint"},
        },
        "provenance": {
            "section_pair": {"bns": "127(2)", "ipc": "342"},
            "mapping_note": "BNS 127(1) defines wrongful confinement (IPC 340 and "
                            "illustrations, including the lock-in case); 127(2) is "
                            "the punishment (IPC 342). v1 treated the item as "
                            "restraint under 126(2)/IPC 341, which the illustrations "
                            "to BNS 127 do not support.",
        },
    },
}

REVISION_DATE = "2026-10-27"
REVISION_BASIS = ("ai_assisted_source_comparison; operator-decided; "
                  "not human legal verification")


def _apply(item: dict, revision: dict) -> dict:
    revised = dict(item)
    for key, value in revision["fields"].items():
        revised[key] = value
    provenance = dict(revised["provenance"])
    for key, value in revision["provenance"].items():
        provenance[key] = value
    # Everything cumulative is additive; nothing here may claim verification.
    provenance["verified"] = False
    provenance["revision"] = {
        "version": "v2",
        "date": REVISION_DATE,
        "revised_from": "data/lexuq_target_candidates_v1.jsonl",
        "basis": REVISION_BASIS,
        "decided_by": revision["decided_by"],
        "reason": revision["reason"],
        "sources": revision["sources"],
        "changed_fields": sorted(revision["fields"]),
        "still_requires_human_review": True,
    }
    revised["provenance"] = provenance
    review = dict(revised.get("review") or {})
    review["status"] = "PENDING_HUMAN_REVIEW"
    review["ai_assisted_revision"] = ("v2 revised on 2026-10-27 after "
                                      "reports/phaseG_l7_label_review_v1.md; the "
                                      "gold is still not human-verified")
    revised["review"] = review
    return revised


def build() -> tuple[str, str, list[dict]]:
    """Return (v1_text, v2_text, revisions_applied)."""
    v1_lines = V1.read_text(encoding="utf-8").splitlines()
    if not v1_lines:
        raise SystemExit(f"ERROR: {V1} is empty")

    applied: list[dict] = []
    seen: set[str] = set()
    out_lines: list[str] = []
    for raw in v1_lines:
        item = json.loads(raw)
        pair_id = item.get("pair_id")
        revision = REVISIONS.get(pair_id)
        if revision is None:
            out_lines.append(raw)          # byte-identical passthrough
            continue
        before = {key: item.get(key) for key in revision["fields"]}
        revised = _apply(item, revision)
        out_lines.append(json.dumps(revised, ensure_ascii=False))
        seen.add(pair_id)
        applied.append({
            "item_id": item["item_id"],
            "pair_id": pair_id,
            "before": before,
            "after": {key: revised.get(key) for key in revision["fields"]},
            "reason": revision["reason"],
            "sources": revision["sources"],
            "decided_by": revision["decided_by"],
        })

    missing = sorted(set(REVISIONS) - seen)
    if missing:
        raise SystemExit(f"ERROR: revision targets not found in v1: {missing}")

    return V1.read_text(encoding="utf-8"), "\n".join(out_lines) + "\n", applied


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true",
                    help="verify the committed v2 matches what this script builds")
    ap.add_argument("--json", action="store_true",
                    help="print the applied revision list as JSON")
    args = ap.parse_args(argv)

    _v1_text, v2_text, applied = build()

    if args.check:
        if not V2.is_file():
            print(f"MISSING: {V2}")
            return 1
        current = V2.read_text(encoding="utf-8")
        if current != v2_text:
            print("MISMATCH: data/lexuq_target_candidates_v2.jsonl is not what "
                  "this script builds")
            return 1
        print(f"OK: {V2.relative_to(ROOT)} matches the builder "
              f"({len(applied)} revisions)")
        return 0

    V2.write_text(v2_text, encoding="utf-8")

    from jurisuq.target.candidates import content_sha256, load_candidates

    items = load_candidates(V2)
    print(f"wrote {V2.relative_to(ROOT)}")
    print(f"  v1 sha256: {content_sha256(V1)}")
    print(f"  v2 sha256: {content_sha256(V2)}")
    print(f"  items: {len(items)}  revisions: {len(applied)}")
    if args.json:
        print(json.dumps(applied, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
