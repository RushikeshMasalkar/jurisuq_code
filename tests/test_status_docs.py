"""Guards for the project-level documents: STATUS, ROADMAP, DEMO, PROFESSOR-SUMMARY.

These documents are what a reader trusts first, so the failure mode worth
testing is drift: a hash, a count, a gate verdict or a file path that no longer
matches the artefacts it claims to describe.

Nothing here re-runs the pipeline; it compares prose against stored records.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

STATUS = ROOT / "STATUS.md"
ROADMAP = ROOT / "ROADMAP.md"
DEMO = ROOT / "DEMO.md"
SUMMARY = ROOT / "PROFESSOR-SUMMARY.md"
README = ROOT / "README.md"

DOCS = (STATUS, ROADMAP, DEMO, SUMMARY)


def _text(path: Path) -> str:
    assert path.is_file(), f"missing required document: {path.name}"
    return path.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def status_text() -> str:
    return _text(STATUS)


@pytest.fixture(scope="module")
def label_review() -> dict:
    return json.loads((ROOT / "runs" / "phaseG_l7_label_review_v1.json").read_text(encoding="utf-8"))


# ----------------------------------------------------------------------
# the documents exist and are cross-linked
# ----------------------------------------------------------------------
@pytest.mark.parametrize("path", DOCS)
def test_each_project_document_exists_and_is_not_a_stub(path):
    text = _text(path)
    assert len(text.splitlines()) > 40, f"{path.name} looks like a stub"
    assert text.lstrip().startswith("#"), f"{path.name} must open with a heading"


def test_status_is_the_authoritative_document_and_the_others_point_at_it():
    for doc in (ROADMAP, DEMO, SUMMARY):
        assert "STATUS.md" in _text(doc), f"{doc.name} must link to STATUS.md"


def test_status_covers_every_phase_and_uses_the_status_vocabulary(status_text):
    for phase in ("Phase A", "Phase B", "Phase C", "Phase D",
                  "Phase E", "Phase F", "Phase G"):
        assert phase in status_text, f"STATUS.md does not mention {phase}"
    for label in ("IMPLEMENTED", "TESTED", "BLOCKED",
                  "PENDING_HUMAN_REVIEW", "NOT_EVALUABLE"):
        assert label in status_text, f"STATUS.md never uses the status label {label}"


# ----------------------------------------------------------------------
# hashes quoted in STATUS.md must be the hashes on disk
# ----------------------------------------------------------------------
@pytest.mark.parametrize("rel", [
    "data/lexuq_slice.jsonl",
    "data/lexuq_target_candidates_v1.jsonl",
    "data/lexuq_target_candidates_v2.jsonl",
    "data/statutes/statutes_v1.jsonl",
])
def test_every_quoted_dataset_hash_matches_the_file(status_text, rel):
    from jurisuq.pilot import sha256_file

    actual = sha256_file(ROOT / rel)
    assert actual in status_text, (
        f"STATUS.md does not quote the current sha256 of {rel} ({actual})")
    assert rel in status_text, f"STATUS.md never mentions {rel}"


# ----------------------------------------------------------------------
# gate verdicts in the prose must equal the verdicts in the artefacts
# ----------------------------------------------------------------------
def test_the_g4_verdict_matches_the_stored_validation_record(status_text):
    record = json.loads((ROOT / "runs" / "phaseA-laptop-v2-rejudged+ctx-r2+typed+warrant"
                         / "warrant_validation.json").read_text(encoding="utf-8"))
    verdict = record["gate_g4"]["verdict"]
    assert verdict == "PASS"
    assert "G4" in status_text and verdict in status_text


def test_the_g7_verdict_matches_the_stored_matrix(status_text):
    matrix = json.loads((ROOT / "runs" / "phaseG_eval_matrix.json").read_text(encoding="utf-8"))
    gate = matrix["gate_g7"]
    verdict = gate.get("verdict") or gate.get("status")
    assert verdict == "NOT_MET"
    assert "G7" in status_text and verdict in status_text


def test_the_phase_g_status_record_agrees_with_the_documents(status_text):
    record = json.loads((ROOT / "runs" / "phaseG_stage2_status.json").read_text(encoding="utf-8"))
    assert record["gates_unchanged"] == {"G5": "NOT_EVALUABLE",
                                         "G6": "NOT_MET", "G7": "NOT_MET"}
    assert record["pilot_unchanged"]["status"] == "ON_HOLD"
    for value in ("NOT_EVALUABLE", "NOT_MET", "ON_HOLD"):
        assert value in status_text


# ----------------------------------------------------------------------
# counts quoted in the prose must match the data and the records
# ----------------------------------------------------------------------
def test_the_candidate_counts_quoted_are_the_counts_on_disk(status_text):
    from jurisuq.target import load_candidates

    for version in ("v1", "v2"):
        items = load_candidates(ROOT / "data" / f"lexuq_target_candidates_{version}.jsonl")
        assert len(items) == 24
        assert sum(1 for i in items if i["slice"] == "L7") == 12
        assert f"lexuq_target_candidates_{version}.jsonl" in status_text


def test_the_label_review_numbers_quoted_match_the_record(status_text, label_review):
    summary = label_review["summary"]
    assert (summary["confirmed"], summary["ambiguous"],
            summary["unsupported"]) == (8, 3, 1)
    assert "8 confirmed" in status_text
    assert "3 ambiguous" in status_text
    assert "1 unsupported" in status_text
    assert label_review["reviewer"]["is_human_legal_review"] is False


def test_the_documents_never_claim_human_legal_verification():
    forbidden = [
        "human-approved labels",
        "verified by a lawyer",
        "legal review complete",
        "human legal review complete",
    ]
    for doc in DOCS:
        text = _text(doc).lower()
        for phrase in forbidden:
            assert phrase not in text, f"{doc.name} claims {phrase!r}"


def test_the_documents_keep_the_l7_result_scoped_to_one_model():
    text = _text(SUMMARY)
    assert "not a cross-model comparison" in text.lower()


# ----------------------------------------------------------------------
# every relative link and every referenced script resolves
# ----------------------------------------------------------------------
LINK = re.compile(r"\]\(([^)]+)\)")
PATH_IN_BACKTICKS = re.compile(r"`((?:scripts|data|runs|jurisuq|tests)/[^`\s]+?\.(?:py|json|jsonl|md|csv))`")

#: Display patterns ("runs/*.json", "jurisuq/{a,b}.py") are prose, not paths.
SKIP_MARKERS = ("*", "{", "}", "\u2026", "<", ">")

#: Files the documents deliberately name as NOT present in this checkout: the
#: principal investigator's local Phase G diagnostics. STATUS.md section 5 exists
#: precisely to record that they are absent, so their absence is not an error.
ALLOW_MISSING = {
    "runs/phaseG_l7_diagnostic.json",
    "runs/phaseG_l7_diagnostic_items.jsonl",
    "runs/phaseG_l7_qwen3_14b_diagnostic.json",
    "runs/phaseG_l7_qwen3_14b_diagnostic_items.jsonl",
    "runs/phaseG_l7_rehearsal.json",
    "runs/phaseG_l7_rehearsal_items.jsonl",
    # produced by scripts/47_demo.py, not committed
    "runs/demo/demo_summary.json",
}


def test_every_relative_markdown_link_resolves():
    missing = []
    for doc in (*DOCS, README):
        for target in LINK.findall(_text(doc)):
            if target.startswith(("http://", "https://", "#")):
                continue
            path = target.split("#")[0].strip()
            if not path:
                continue
            if not (doc.parent / path).exists():
                missing.append(f"{doc.name} -> {target}")
    assert not missing, f"broken relative links: {missing}"


def test_every_referenced_script_and_artifact_exists():
    missing = []
    for doc in (*DOCS, README):
        for rel in PATH_IN_BACKTICKS.findall(_text(doc)):
            if any(marker in rel for marker in SKIP_MARKERS):
                continue
            if rel in ALLOW_MISSING:
                continue
            if not (ROOT / rel).exists():
                missing.append(f"{doc.name} -> {rel}")
    assert not missing, f"documents reference files that do not exist: {missing}"


# ----------------------------------------------------------------------
# the demo document describes the demo that exists
# ----------------------------------------------------------------------
def test_the_demo_guide_runs_the_real_demo_script():
    text = _text(DEMO)
    assert "scripts/47_demo.py" in text
    assert (ROOT / "scripts" / "47_demo.py").is_file()
    assert "runs/demo" in text
    for command in ("python -X utf8 -m pytest -q", "scripts/00_env_check.py"):
        assert command in text


def test_the_demo_guide_marks_the_mock_and_the_missing_artifacts():
    text = _text(DEMO).lower()
    assert "mock provider" in text
    assert "by construction" in text
    assert "operator-reported" in text
