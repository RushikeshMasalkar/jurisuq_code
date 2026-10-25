#!/usr/bin/env python3
"""45 - Phase G Stage 2: build the target candidate item set.

Offline, deterministic, no network. Writes:

    data/lexuq_target_candidates_v1.jsonl      the candidate items
    runs/phaseG_candidate_sources_v1.json      the source + review record

Why a builder and not hand-edited JSONL
---------------------------------------
Stage 2 step 1 requires "an approved candidate item set in the Phase A schema
with `verified: false` provenance" (`PHASE-G.md`). Keeping the item table and its
citations in one explicit, reviewable source and emitting the JSONL from it means
the dataset and its provenance record cannot drift apart, and a reviewer can see
every item, its source, and its open issues in one file.

What this script does NOT do
----------------------------
* It does not verify that the items are legally correct. It records, per item,
  which section pair was checked against which source, and leaves
  ``provenance.verified = false``. Human legal review is outstanding.
* It does not assign a correctness class. Correctness is *measured* by the judge
  against ``gold`` from generated samples (``jurisuq/pipeline.py``,
  ``majority_correct``); it is not an authored field and must never be invented
  here. The only authored expectation is ``answerability_hypothesis``.
* It does not estimate yield, run a model, or decide any gate.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from jurisuq.target import candidates as contract
from jurisuq.uncertainty.io import write_json

TRANSITION = "1 July 2024"
TRANSITION_NOTE = (
    "The three criminal codes were replaced with effect from 1 July 2024: the "
    "Indian Penal Code, 1860 by the Bharatiya Nyaya Sanhita, 2023; the Code of "
    "Criminal Procedure, 1973 by the Bharatiya Nagarik Suraksha Sanhita, 2023; "
    "and the Indian Evidence Act, 1872 by the Bharatiya Sakshya Adhiniyam, 2023."
)

# ----------------------------------------------------------------------
# sources
# ----------------------------------------------------------------------
#: ``retrieved`` records exactly what this environment observed. ``full_text``
#: means the document body was fetched and read here; ``search_excerpt`` means
#: only a search-engine excerpt was seen and the document itself was NOT
#: opened. That distinction is the difference between citing a source and
#: claiming to have checked it, so it is recorded per source rather than
#: summarised away.
SOURCES = {
    "NCRB_BNS_2023": {
        "title": "Bharatiya Nyaya Sanhita, 2023 (bare act, with corresponding "
                 "section table of BNS with the repealed Act)",
        "issuing_authority": "National Crime Records Bureau, Ministry of Home Affairs, "
                             "Government of India",
        "url": "https://www.ncrb.mha.gov.in/uploads/SankalanPortal/DownloadPDF/BNS2023.pdf",
        "authority_type": "official_government_publication",
        "retrieved": "full_text",
        "supports": "BNS section numbering and titles; the official BNS-to-IPC "
                    "corresponding section table (Chapters I-V read in full here; "
                    "later chapters read via the arrangement-of-sections list).",
    },
    "BPRD_COMPARISON": {
        "title": "Comparison Summary BNS to IPC",
        "issuing_authority": "Bureau of Police Research and Development, "
                             "Ministry of Home Affairs, Government of India",
        "url": "https://bprd.nic.in/uploads/pdf/COMPARISON%20SUMMARY%20BNS%20to%20IPC%20.pdf",
        "authority_type": "official_government_publication",
        "retrieved": "search_excerpt",
        "supports": "Section-level BNS-to-IPC mapping and change notes for "
                    "s.103(1), s.126, s.305, s.306, s.307, s.318.",
        "caveat": "The PDF could not be opened from this environment (HTTP 500); "
                  "only search-engine excerpts were read. A human reviewer should "
                  "open the document before relying on it.",
    },
    "UPPOLICE_COMPARATIVE": {
        "title": "Corresponding Section Table of Bharatiya Nyaya Sanhita 2023",
        "issuing_authority": "Uttar Pradesh Police",
        "url": "https://uppolice.gov.in/site/writereaddata/siteContent/Three%20New%20"
               "Major%20Acts/202406281710564823BNS_IPC_Comparative.pdf",
        "authority_type": "official_government_publication",
        "retrieved": "search_excerpt",
        "supports": "s.305 <- 380, s.318(1) <- 415, s.318(2) <- 417, s.318(3) <- 418.",
        "caveat": "Read via search excerpt only; document not opened here.",
    },
    "EGAZETTE_BNS": {
        "title": "The Bharatiya Nyaya Sanhita, 2023, No. 45 of 2023 (Gazette of India)",
        "issuing_authority": "Government of India (e-Gazette)",
        "url": "https://egazette.gov.in/WriteReadData/2023/250883.pdf",
        "authority_type": "primary_legislation",
        "retrieved": "search_excerpt",
        "supports": "Enacted text of s.103(1) (punishment for murder: death or "
                    "imprisonment for life and fine) and s.103(2).",
        "caveat": "Search excerpt only; the gazette PDF was not opened here.",
    },
    "MHA_REFERENCE_2023": {
        "title": "Reference Material on New Criminal Laws, 2023",
        "issuing_authority": "Ministry of Home Affairs, Government of India",
        "url": "https://cdnbbsr.s3waas.gov.in/s3ec02907edb0aa6986220dbffb79a7885/"
               "uploads/2024/05/2024052146.pdf",
        "authority_type": "official_government_publication",
        "retrieved": "search_excerpt",
        "supports": "Enforcement date 1 July 2024; Act 45 of 2023; assent 25 December 2023.",
        "caveat": "Read via search excerpt only.",
    },
}

# ----------------------------------------------------------------------
# the section pairs
# ----------------------------------------------------------------------
#: BNS <-> IPC pairs used by the candidate set. ``bns_label``/``ipc_label`` are
#: the offence labels; ``sources`` lists which sources support the pairing.
#: ``subsection_confidence`` is recorded separately from <-> because the
#: *definition* section pair is better evidenced than the punishment sub-section
#: pair for some offences.
PAIRS = {
    "murder": {
        "bns": "103(1)", "bns_label": "punishment for murder",
        "ipc": "302", "ipc_label": "punishment for murder",
        "distractor": {"act": "BNS", "provision": "101", "label": "murder (definition)"},
        "punishment": "death or imprisonment for life, and fine",
        "sources": ["NCRB_BNS_2023", "BPRD_COMPARISON", "EGAZETTE_BNS"],
        "subsection_confidence": "high",
        "note": "BNS 103(1) carries IPC 302 verbatim; BNS 103(2) (group murder on "
                "protected grounds) is new and has no IPC counterpart.",
    },
    "culpable_homicide": {
        "bns": "105", "bns_label": "punishment for culpable homicide not amounting to murder",
        "ipc": "304", "ipc_label": "punishment for culpable homicide not amounting to murder",
        "distractor": {"act": "BNS", "provision": "103(1)", "label": "punishment for murder"},
        "punishment": "see BNS 105(1)-(2); the graduated terms are cited, not reproduced",
        "sources": ["NCRB_BNS_2023"],
        "subsection_confidence": "medium",
        "note": "BNS 100 (culpable homicide) and 101 (murder) restate IPC 299 and 300. "
                "BNS 105(1) is read as the successor of IPC 304, supported here by "
                "the official arrangement-of-sections titles. The sub-section terms "
                "differ from IPC 304 in detail and are NOT reproduced in this dataset.",
    },
    "theft": {
        "bns": "303(2)", "bns_label": "punishment for theft",
        "ipc": "379", "ipc_label": "punishment for theft",
        "distractor": {"act": "BNS", "provision": "304", "label": "snatching"},
        "punishment": "up to three years, or fine, or both; separate tiers for repeat "
                      "conviction and for low-value first offences",
        "sources": ["NCRB_BNS_2023"],
        "subsection_confidence": "high",
        "note": "BNS 303(1) is the theft definition (IPC 378); 303(2) is the "
                "punishment. The community-service proviso has no IPC counterpart.",
    },
    "theft_in_dwelling": {
        "bns": "305", "bns_label": "theft in a dwelling house, or means of transportation "
                                    "or place of worship",
        "ipc": "380", "ipc_label": "theft in a dwelling house",
        "distractor": {"act": "BNS", "provision": "303(2)", "label": "punishment for theft"},
        "punishment": "not reproduced here; BNS 305 is subdivided and the added "
                      "sub-sections have no IPC counterpart",
        "sources": ["NCRB_BNS_2023", "BPRD_COMPARISON", "UPPOLICE_COMPARATIVE"],
        "subsection_confidence": "medium",
        "note": "BNS 305 enlarges IPC 380 to cover means of transportation and places "
                "of worship, and adds new sub-sections (b)-(e).",
    },
    "criminal_breach_of_trust": {
        "bns": "316(2)", "bns_label": "punishment for criminal breach of trust",
        "ipc": "406", "ipc_label": "punishment for criminal breach of trust",
        "distractor": {"act": "BNS", "provision": "318(4)", "label": "cheating"},
        "punishment": "up to five years, or fine, or both (raised from three years under IPC 406)",
        "sources": ["NCRB_BNS_2023", "BPRD_COMPARISON"],
        "subsection_confidence": "medium",
        "note": "BNS 316 consolidates IPC 405-409 into one section; the general "
                "punishment in 316(2) is read as the successor of IPC 406. The "
                "aggregated structure means the IPC 406/407/408/409 distinctions "
                "are partly lost, which is recorded as a limitation.",
    },
    "cheating": {
        "bns": "318(4)", "bns_label": "cheating and dishonestly inducing delivery of property",
        "ipc": "420", "ipc_label": "cheating and dishonestly inducing delivery of property",
        "distractor": {"act": "BNS", "provision": "316(2)", "label": "criminal breach of trust"},
        "punishment": "up to seven years, and fine",
        "sources": ["NCRB_BNS_2023", "UPPOLICE_COMPARATIVE"],
        "subsection_confidence": "medium",
        "note": "BNS 318(1) is the cheating definition (IPC 415); 318(2)-(4) carry "
                "IPC 417, 418 and 420. The 318(4) <- 420 pairing is standard but the "
                "UP Police excerpt read here showed only 318(1)-(3).",
    },
    "wrongful_restraint": {
        "bns": "126(2)", "bns_label": "punishment for wrongful restraint",
        "ipc": "341", "ipc_label": "punishment for wrongful restraint",
        "distractor": {"act": "BNS", "provision": "127", "label": "wrongful confinement"},
        "punishment": "up to one month, or fine up to five thousand rupees, or both",
        "sources": ["NCRB_BNS_2023", "BPRD_COMPARISON"],
        "subsection_confidence": "high",
        "note": "BNS 126(1) is wrongful restraint (IPC 339); 126(2) is the punishment "
                "(IPC 341). The fine ceiling rose from five hundred to five thousand rupees.",
    },
    "cruelty_by_husband": {
        "bns": "85", "bns_label": "husband or relative of husband subjecting a woman to cruelty",
        "ipc": "498A", "ipc_label": "husband or relative of husband subjecting a woman to cruelty",
        "distractor": {"act": "BNS", "provision": "80", "label": "dowry death"},
        "punishment": "up to three years, and fine",
        "sources": ["NCRB_BNS_2023"],
        "subsection_confidence": "medium",
        "note": "BNS 85 and 86 correspond to IPC 498A and its Explanation. The official "
                "correspondence table was read only up to Chapter V here, so this pair "
                "rests on the BNS titles plus the standard published mapping and needs "
                "human confirmation.",
    },
}

#: Three distinct fact patterns per offence. ``facts`` is the scenario only; the
#: template supplies the question frame. No fact pattern depends on case law,
#: and none states a punishment figure, so the item cannot leak its own answer.
FACTS = {
    "murder": [
        "A, intending to kill B, stabbed B in the chest; B died of the injury.",
        "A poured petrol over B's house and set it alight knowing B was asleep inside; B died.",
        "A shot B at point-blank range after planning the killing for a week; B died.",
    ],
    "culpable_homicide": [
        "A struck B once on the head during a sudden fight, without premeditation; B died later.",
        "A, a driver, ran over B while reversing negligently in a crowded market; B died.",
        "A pushed B during a quarrel, not intending death or injury likely to cause it; B fell, struck his head and died.",
    ],
    "theft": [
        "A took B's scooter from a public stand without B's consent and kept it.",
        "A quietly removed B's mobile phone from B's bag on a bus and walked away.",
        "A picked B's pocket in a market and took B's wallet without B noticing.",
    ],
    "theft_in_dwelling": [
        "A entered B's locked house at night and took B's television.",
        "A stole a gold chain from a jewellery shop inside a temple complex during worship hours.",
        "A broke into B's flat while B was away and removed cash and a laptop.",
    ],
    "criminal_breach_of_trust": [
        "A, entrusted with B's jewellery for safekeeping, sold it and kept the money.",
        "A, a warehouse keeper, was entrusted with B's goods and dishonestly disposed of them.",
        "A, B's agent for collecting rent, received the rent and dishonestly used it for himself.",
    ],
    "cheating": [
        "A induced B to pay for a non-existent plot of land by showing B a forged title deed.",
        "A promised B a job in return for a fee, never intending to provide it, and kept the money.",
        "A, posing as a bank officer, induced B to transfer money to an account A controlled.",
    ],
    "wrongful_restraint": [
        "A blocked B's only exit from a room, preventing B from leaving, without B's consent.",
        "A stood in front of B's car on the road and refused to move, stopping B from proceeding.",
        "A locked the gate of B's compound from outside so that B could not leave.",
    ],
    "cruelty_by_husband": [
        "B was subjected to sustained harassment for dowry by her husband and his family.",
        "B's husband repeatedly subjected her to mental cruelty with demands for money from her parents.",
        "B was harassed by her husband's relatives for failing to bring a car in dowry.",
    ],
}

#: Question frames, kept textually close to the frozen benchmark's T1-T6 so the
#: candidate set exercises the same instrument rather than a new one.
TEMPLATES = {
    "T1": {
        "L7": "Under the law in force in India today (after 1 July 2024), which section "
              "applies to this situation, and what is the punishment prescribed?",
        "L1": "Under the law in force in India immediately before 1 July 2024, which "
              "section applies to this situation, and what is the punishment prescribed?",
    },
    "T2": {
        "L7": "A client asks which provision of the penal law governs the following facts "
              "under the law in force in India today (after 1 July 2024). Give the act "
              "and the section.",
        "L1": "A client asks which provision of the penal law governs the following facts "
              "under the law in force in India immediately before 1 July 2024. Give the "
              "act and the section.",
    },
    "T6": {
        "L7": "The question arises during a bail hearing. A junior lawyer needs the exact "
              "provision today (after 1 July 2024). Which act and which section apply?",
        "L1": "The question arises during a bail hearing. A junior lawyer needs the exact "
              "provision in force immediately before 1 July 2024. Which act and which "
              "section apply?",
    },
}

#: 24 items: 3 per offence, 12 on L7 and 12 on L1. Each row is
#: (topic, slice, template, fact index). Alternating slices keeps both arms
#: balanced so neither side of the screen is empty.
PLAN = [
    ("murder", "L7", "T1", 0),
    ("murder", "L1", "T1", 1),
    ("murder", "L1", "T6", 2),
    ("culpable_homicide", "L1", "T2", 0),
    ("culpable_homicide", "L1", "T6", 1),
    ("culpable_homicide", "L7", "T1", 2),
    ("theft", "L7", "T1", 0),
    ("theft", "L1", "T2", 1),
    ("theft", "L7", "T6", 2),
    ("theft_in_dwelling", "L7", "T2", 0),
    ("theft_in_dwelling", "L1", "T1", 1),
    ("theft_in_dwelling", "L7", "T6", 2),
    ("criminal_breach_of_trust", "L7", "T1", 0),
    ("criminal_breach_of_trust", "L1", "T2", 1),
    ("criminal_breach_of_trust", "L7", "T6", 2),
    ("cheating", "L7", "T2", 0),
    ("cheating", "L1", "T1", 1),
    ("cheating", "L1", "T6", 2),
    ("wrongful_restraint", "L7", "T6", 0),
    ("wrongful_restraint", "L1", "T1", 1),
    ("wrongful_restraint", "L7", "T2", 2),
    ("cruelty_by_husband", "L7", "T1", 0),
    ("cruelty_by_husband", "L1", "T2", 1),
    ("cruelty_by_husband", "L1", "T6", 2),
]


def build_items() -> list[dict]:
    items: list[dict] = []
    per_topic_count: dict[str, int] = {}
    for topic, slice_name, template, fact_index in PLAN:
        pair = PAIRS[topic]
        per_topic_count[topic] = per_topic_count.get(topic, 0) + 1
        n = per_topic_count[topic]
        item_id = f"{slice_name}-{topic}-c{n:03d}"
        # L7 asks the law today -> BNS is gold, repealed IPC is the trap.
        # L1 asks the law before 1 July 2024 -> IPC is gold, BNS is the trap.
        if slice_name == "L7":
            gold = {"act": "BNS", "provision": pair["bns"], "label": pair["bns_label"]}
            trap = {"act": "IPC", "provision": pair["ipc"],
                    "label": f"{pair['ipc_label']} (repealed with effect from {TRANSITION})"}
            distractor = pair["distractor"]
            era, asked_about = "current", "current law"
        else:
            gold = {"act": "IPC", "provision": pair["ipc"], "label": pair["ipc_label"]}
            trap = {"act": "BNS", "provision": pair["bns"],
                    "label": f"{pair['bns_label']} (in force only from {TRANSITION})"}
            distractor = {"act": "IPC", "provision": pair["ipc"], "label": "not applicable"}
            era, asked_about = "pre-transition", "law immediately before 1 July 2024"

        question = f"{TEMPLATES[template][slice_name]} {FACTS[topic][fact_index]}"

        items.append({
            "item_id": item_id,
            "pair_id": f"{topic}-c{n:03d}",
            "slice": slice_name,
            "era": era,
            "asked_about": asked_about,
            "topic": topic,
            "template": template,
            "question": question,
            "gold": gold,
            "trap": trap,
            "distractor": distractor,
            "gold_act": gold["act"],
            "gold_provision": gold["provision"],
            "trap_act": trap["act"],
            "trap_provision": trap["provision"],
            "distractor_provision": distractor["provision"],
            "punishment": pair["punishment"],
            "provenance": {
                "source": "authored for the Phase G Stage 2 screen, from the official "
                          "BNS-to-IPC corresponding section table",
                "built_from": "scripts/45_build_target_candidates.py",
                "verified": False,
                "transition_date": TRANSITION,
                "note": TRANSITION_NOTE,
                "section_pair": {"bns": pair["bns"], "ipc": pair["ipc"]},
                "sources": pair["sources"],
                "subsection_confidence": pair["subsection_confidence"],
                "mapping_note": pair["note"],
            },
            "review": {
                "status": "PENDING_HUMAN_REVIEW",
                "reviewer": "machine-assisted source check only (no human legal review)",
                "fact_pattern_origin": "authored for this dataset; not taken from case law",
                "answerability_hypothesis": "answerable; untested until a generator runs",
                "unresolved_issues": [],
            },
        })
    return items


def main() -> int:
    items = build_items()
    summary = contract.validate_candidates(items)

    out_jsonl = ROOT / "data" / "lexuq_target_candidates_v1.jsonl"
    out_jsonl.write_text(
        "\n".join(json.dumps(item, ensure_ascii=False, allow_nan=False)
                  for item in items) + "\n",
        encoding="utf-8")

    payload = {
        "phase": "G",
        "experiment": "Stage 2 candidate item set (step 1)",
        "source_document": summary["source_document"],
        "dataset": "data/lexuq_target_candidates_v1.jsonl",
        "dataset_sha256": contract.content_sha256(out_jsonl),
        "n_items": summary["n_items"],
        "slices": summary["slices"],
        "topics": sorted({item["topic"] for item in items}),
        "templates": sorted({item["template"] for item in items}),
        "contract": summary,
        "provenance_verified": False,
        "verification_statement": (
            "Every item is provenance.verified = false. The section pairs were checked "
            "against official government sources in this environment, but that is a "
            "machine-assisted source check, not human legal approval. No item has been "
            "approved by a qualified legal reviewer."),
        "correctness_classes": {
            "authored": "none",
            "reason": "correctness is measured by the judge against gold from generated "
                      "samples (jurisuq/pipeline.py, majority_correct); it is not an "
                      "authored field, so authoring one would fabricate the measurement "
                      "G7 depends on",
        },
        "sources": SOURCES,
        "section_pairs": PAIRS,
        "not_done": [
            "no generation", "no yield measurement", "no correctness label",
            "no human legal review", "no gate verdict",
        ],
        "generated_by": "scripts/45_build_target_candidates.py",
    }
    write_json(ROOT / "runs" / "phaseG_candidate_sources_v1.json", payload)

    print(f"items written : {len(items)} -> {out_jsonl.relative_to(ROOT)}")
    print(f"slices        : {summary['slices']}")
    print(f"topics        : {len(set(i['topic'] for i in items))}")
    print(f"sha256        : {payload['dataset_sha256']}")
    print("provenance    : verified = false on every item (human review outstanding)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
