"""Checks for the real Phase G target-yield screen report.

The screen has been run locally on Qwen3 14B, but the report file is not in this
repository. Rather than fabricate it from a summary, this module validates it the
moment it is added, and otherwise records that its absence is the documented
state.

When `runs/phaseG_screen_qwen3_14b_full.json` exists, these tests assert that it
is a *real* run (not the mock), that it was taken over the candidate dataset that
is actually in this repository, that its arithmetic is self-consistent, and that
its projection matches this repository's own planning code. Those are provenance
and consistency checks -- they do not and cannot establish that any individual
item was labelled correctly.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from jurisuq.target import content_sha256, items_needed

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "runs" / "phaseG_screen_qwen3_14b_full.json"
STATUS = ROOT / "runs" / "phaseG_stage2_status.json"
CANDIDATES = ROOT / "data" / "lexuq_target_candidates_v1.jsonl"

MISSING = pytest.mark.skipif(
    not REPORT.is_file(),
    reason="runs/phaseG_screen_qwen3_14b_full.json is not in this repository; the screen was run "
           "locally and its summary is recorded as reported in runs/phaseG_stage2_status.json")


def _status() -> dict:
    return json.loads(STATUS.read_text(encoding="utf-8"))


def _report() -> dict:
    return json.loads(REPORT.read_text(encoding="utf-8"))


# ----------------------------------------------------------------------
# the documented state, which holds whether or not the file is present
# ----------------------------------------------------------------------
def test_the_status_record_declares_whether_the_report_is_present():
    record = _status()["reported_screen"]
    assert record["exists_in_repository"] is REPORT.is_file(), \
        "the status record must not disagree with the repository about the artefact"


def test_the_reported_figures_are_marked_reported_not_measured_here():
    record = _status()["reported_screen"]
    assert record["status"] == "REPORTED_BY_PRINCIPAL_INVESTIGATOR"
    assert "not present in this repository" in record["observation_source"]
    assert record["verification_status"] in {"AWAITING_ARTIFACT", "VERIFIED"}


def test_the_reported_summary_matches_this_repositorys_own_mathematics():
    """The summary is reproducible from the repo's code, which is why it is
    recorded as corroborated while still not treated as an artefact."""
    record = _status()["reported_screen"]
    rate = record["majority_correct"] / record["items"]
    assert abs(rate - record["majority_rate"]) < 1e-9
    projection = items_needed(rate, 15, confidence=0.95)
    assert projection["items_for_confidence"] == record["projection_items_for_15_correct"]


def test_the_per_slice_question_is_declared_unanswered():
    """The one question G7 depends on cannot be answered from an aggregate."""
    gap = _status()["per_slice_question"]
    assert gap["answerable_from_reported_summary"] is False
    assert "L7" in gap["reason"]


# ----------------------------------------------------------------------
# only meaningful once the artefact is added
# ----------------------------------------------------------------------
@MISSING
def test_the_report_is_a_real_run_not_the_mock():
    report = _report()
    assert report["is_mock"] is False
    assert report["provider"] != "mock"


@MISSING
def test_the_report_was_taken_over_the_dataset_in_this_repository():
    """A yield is only meaningful against the bytes it screened."""
    report = _report()
    assert report["data_sha256"] == content_sha256(CANDIDATES)
    assert report["data_path"].endswith("lexuq_target_candidates_v1.jsonl")


@MISSING
def test_the_report_is_the_expected_shape():
    report = _report()
    assert report["phase"] == "G"
    assert report["n_items"] == 24
    assert report["n_samples_per_item"] == 10
    assert report["candidate_contract"]["slices"] == {"L1": 12, "L7": 12}
    assert report["candidate_contract"]["provenance_verified"] is False


@MISSING
def test_the_reports_own_arithmetic_is_consistent():
    overall = _report()["yield"]["overall"]
    assert overall["items"] == 24
    assert 0 <= overall["majority_correct"] <= overall["items"]
    assert abs(overall["majority_rate"]
               - overall["majority_correct"] / overall["items"]) < 1e-9
    if overall.get("sample_rate") is not None:
        assert 0.0 <= overall["sample_rate"] <= 1.0


@MISSING
def test_the_reports_projection_matches_this_repositorys_planning_code():
    report = _report()
    overall = report["yield"]["overall"]
    projection = items_needed(overall["majority_rate"], 15, confidence=0.95)
    assert report["projection"]["items_for_confidence"] == projection["items_for_confidence"]


@MISSING
def test_per_slice_yield_is_present_or_its_absence_is_declared():
    """Per-slice yield is what decides the L7 question. A report made before the
    breakdown existed must be declared as unable to answer it."""
    report = _report()
    if "yield_by_slice" in report:
        assert set(report["yield_by_slice"]) <= {"L1", "L7"}
        assert set(report["yield_by_slice"]) == {"L1", "L7"}
    else:
        assert _status()["per_slice_question"]["answerable_from_reported_summary"] is False


@MISSING
def test_the_report_does_not_claim_a_gate_verdict():
    """A yield screen is not a G7 evaluation; the report must not imply one."""
    text = json.dumps(_report()).lower()
    assert "g7 pass" not in text
    assert '"status": "pass"' not in text
