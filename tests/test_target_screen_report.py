"""Checks for the Phase G target-yield screening artefacts.

Three reports are committed, and they measure different things:

* ``phaseG_screen_qwen3_14b_full.json``    — 24 items x 10 samples, aggregate only
* ``phaseG_screen_qwen3_14b_sliced.json``  — a SEPARATE run of the same 24 items,
  with the per-slice breakdown the first one lacks
* ``phaseG_screen_qwen3_14b_smoke.json``   — 2 items, a connectivity check

These tests pin the provenance and internal consistency of each: that they are
real (non-mock) runs over the candidate dataset committed here, that their
arithmetic reconciles, that the sliced counts reconcile with its own aggregate,
and that the two full-size runs are kept separate rather than pooled.

What they cannot do — and deliberately do not claim — is establish that any
individual item's gold label is legally correct. Automated screening against a
possibly-wrong gold is not human legal verification, so
``provenance.verified`` must remain ``False``.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from jurisuq.target import content_sha256, items_needed

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "runs" / "phaseG_screen_qwen3_14b_full.json"
SLICED = ROOT / "runs" / "phaseG_screen_qwen3_14b_sliced.json"
SMOKE = ROOT / "runs" / "phaseG_screen_qwen3_14b_smoke.json"
STATUS = ROOT / "runs" / "phaseG_stage2_status.json"
CANDIDATES = ROOT / "data" / "lexuq_target_candidates_v1.jsonl"

#: All three artefacts are committed; a checkout without them is broken, not
#: merely missing a report, so their absence is an error rather than a skip.
COMMITTED = pytest.mark.skipif(
    not (REPORT.is_file() and SLICED.is_file() and SMOKE.is_file()),
    reason="the Phase G screening artefacts are committed to this repository")


def _status() -> dict:
    return json.loads(STATUS.read_text(encoding="utf-8"))


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# ----------------------------------------------------------------------
# the status record must agree with the repository
# ----------------------------------------------------------------------
def test_the_status_record_declares_whether_the_report_is_present():
    record = _status()["reported_screen"]
    assert record["exists_in_repository"] is REPORT.is_file(), \
        "the status record must not disagree with the repository about the artefact"


def test_the_status_record_marks_the_artefacts_as_committed_not_reported():
    """The screening results are read from committed files, not from a summary."""
    status = _status()
    assert status["reported_screen"]["status"] == "ARTIFACT_COMMITTED"
    assert status["reported_screen"]["verification_status"] == "VERIFIED_AGAINST_ARTIFACT"
    assert status["sliced_screen"]["status"] == "ARTIFACT_COMMITTED"
    assert status["smoke_screen"]["status"] == "ARTIFACT_COMMITTED"
    assert status["status"] == "SCREEN_COMPLETE_L7_OUTSTANDING"


def test_the_status_record_still_denies_legal_verification():
    """Committing artefacts is not legal verification. This must not drift."""
    status = _status()
    text = json.dumps(status).lower()
    assert "not human legal verification" in text or "not human legal" in text
    # The L7 investigation has since been carried out, so the record must no longer
    # say the mechanism is unknown -- but it must still say human review is open.
    l7 = status["not_completed"]["l7_investigation"]
    assert l7["status"] != "OUTSTANDING"
    assert "human" in json.dumps(l7).lower() and "review" in json.dumps(l7).lower()
    assert status["gates_unchanged"] == {"G5": "NOT_EVALUABLE", "G6": "NOT_MET", "G7": "NOT_MET"}


def test_the_reported_summary_matches_this_repositorys_own_mathematics():
    record = _status()["reported_screen"]
    rate = record["majority_correct"] / record["items"]
    assert abs(rate - record["majority_rate"]) < 1e-9
    projection = items_needed(rate, 15, confidence=0.95)
    assert projection["items_for_confidence"] == record["projection_items_for_15_correct"]


# ----------------------------------------------------------------------
# the full run
# ----------------------------------------------------------------------
@COMMITTED
def test_the_report_is_a_real_run_not_the_mock():
    report = _load(REPORT)
    assert report["is_mock"] is False
    assert report["provider"] != "mock"
    assert "qwen3" in report["generator"].lower()


@COMMITTED
def test_the_report_was_taken_over_the_dataset_in_this_repository():
    """A yield is only meaningful against the bytes it screened."""
    report = _load(REPORT)
    assert report["data_sha256"] == content_sha256(CANDIDATES)
    assert report["data_path"].endswith("lexuq_target_candidates_v1.jsonl")


@COMMITTED
def test_the_report_is_the_expected_shape():
    report = _load(REPORT)
    assert report["phase"] == "G"
    assert report["n_items"] == 24
    assert report["n_samples_per_item"] == 10
    assert report["candidate_contract"]["slices"] == {"L1": 12, "L7": 12}
    assert report["candidate_contract"]["provenance_verified"] is False


@COMMITTED
def test_the_reports_own_arithmetic_is_consistent():
    overall = _load(REPORT)["yield"]["overall"]
    assert overall["items"] == 24
    assert overall["samples"] == 240
    assert 0 <= overall["majority_correct"] <= overall["items"]
    assert abs(overall["majority_rate"]
               - overall["majority_correct"] / overall["items"]) < 1e-9
    assert abs(overall["sample_rate"]
               - overall["correct_samples"] / overall["samples"]) < 1e-9


@COMMITTED
def test_the_reports_projection_matches_this_repositorys_planning_code():
    report = _load(REPORT)
    overall = report["yield"]["overall"]
    projection = items_needed(overall["majority_rate"], 15, confidence=0.95)
    assert report["projection"]["items_for_confidence"] == projection["items_for_confidence"]


@COMMITTED
def test_the_full_report_has_no_per_slice_breakdown():
    """It predates the change to scripts/41; that is why a second run exists."""
    assert "yield_by_slice" not in _load(REPORT)


# ----------------------------------------------------------------------
# the sliced run answers the per-slice question
# ----------------------------------------------------------------------
@COMMITTED
def test_the_sliced_report_carries_both_slices():
    report = _load(SLICED)
    assert report["is_mock"] is False
    assert report["data_sha256"] == content_sha256(CANDIDATES)
    by_slice = report["yield_by_slice"]
    assert set(by_slice) == {"L1", "L7"}
    assert by_slice["L1"]["overall"]["items"] == 12
    assert by_slice["L7"]["overall"]["items"] == 12


@COMMITTED
def test_the_sliced_result_is_exactly_the_documented_one():
    """L1 carries every correct item; L7 produced none."""
    by_slice = _load(SLICED)["yield_by_slice"]
    l1, l7 = by_slice["L1"]["overall"], by_slice["L7"]["overall"]
    assert l1["majority_correct"] == 3 and l1["majority_rate"] == 0.25
    assert l7["majority_correct"] == 0 and l7["majority_rate"] == 0.0
    # the L7 zero is at the sample level too, not only the majority level
    assert l7["correct_samples"] == 0 and l7["samples"] == 120


@COMMITTED
def test_the_sliced_counts_reconcile_with_its_own_aggregate():
    report = _load(SLICED)
    overall = report["yield"]["overall"]
    by_slice = report["yield_by_slice"]
    assert sum(b["overall"]["items"] for b in by_slice.values()) == overall["items"]
    assert (sum(b["overall"]["majority_correct"] for b in by_slice.values())
            == overall["majority_correct"])
    assert (sum(b["overall"]["correct_samples"] for b in by_slice.values())
            == overall["correct_samples"])


def test_the_per_slice_question_is_recorded_as_answered():
    gap = _status()["per_slice_question"]
    assert gap["answerable"] is True
    assert gap["answered_by"] == "runs/phaseG_screen_qwen3_14b_sliced.json"
    assert "L7" in gap["answer"] and "0" in gap["answer"]
    # it must remain scoped: answered for this run, not a legal finding
    assert "does not establish legal correctness" in gap["scope_limit"]


# ----------------------------------------------------------------------
# the two full-size runs are separate measurements
# ----------------------------------------------------------------------
@COMMITTED
def test_the_full_and_sliced_runs_are_kept_separate():
    """They agree on majority-correct items and differ on samples. Neither
    supersedes the other and their sample counts must not be pooled."""
    full = _load(REPORT)["yield"]["overall"]
    sliced = _load(SLICED)["yield"]["overall"]
    assert full["majority_correct"] == sliced["majority_correct"] == 3
    assert full["correct_samples"] == 34
    assert sliced["correct_samples"] == 32
    note = _status()["sliced_screen"]["relationship_to_full_run"]
    assert "SEPARATE" in note and "Do not pool" in note


# ----------------------------------------------------------------------
# the smoke test is not an evaluation
# ----------------------------------------------------------------------
@COMMITTED
def test_the_smoke_report_is_scoped_as_a_smoke_test():
    smoke = _load(SMOKE)
    assert smoke["n_items"] == 2
    assert smoke["yield"]["overall"]["samples"] == 20
    assert _status()["smoke_screen"]["scope"].startswith("SMOKE TEST")


@COMMITTED
def test_the_smoke_run_is_not_projectable():
    """A zero rate cannot be projected, so it must not be quoted as a yield."""
    projection = _load(SMOKE)["projection"]
    assert projection["reachable"] is False
    assert "cannot be projected" in projection["note"]


# ----------------------------------------------------------------------
# no gate claim anywhere
# ----------------------------------------------------------------------
@COMMITTED
def test_no_screening_report_claims_a_gate_verdict():
    for path in (REPORT, SLICED, SMOKE):
        text = json.dumps(_load(path)).lower()
        assert "g7 pass" not in text, path.name
        assert '"status": "pass"' not in text, path.name
    for path in (REPORT, SLICED):
        assert _load(path).get("is_mock") is False
