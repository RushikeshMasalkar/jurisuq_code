"""Tests for the offline integrity and integration check (scripts/47_offline_check.py).

The check is what a maintainer runs before trusting the stored evidence, so the
things worth pinning are the ones that would let it pass while lying:

* it must never modify a shipped artefact under ``runs/`` or ``data/``;
* it must report the gate verdicts the stored evidence records, and must not
  upgrade any of them;
* it must keep calling the mock screen a wiring check, not a measurement;
* it must fail loudly when a frozen input no longer matches its recorded digest.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "47_offline_check.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("offline_check47", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def check() -> dict:
    """Run the full check once into a temporary directory."""
    out = ROOT / "runs" / "offline-check-test-tmp"
    try:
        proc = subprocess.run(
            [sys.executable, "-X", "utf8", str(SCRIPT), "--out-dir", str(out), "--quiet"],
            cwd=ROOT, capture_output=True, text=True)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        return json.loads((out / "offline_check_summary.json").read_text(encoding="utf-8"))
    finally:
        for child in sorted(out.glob("*")):
            child.unlink()
        if out.is_dir():
            out.rmdir()


# ----------------------------------------------------------------------
# integrity
# ----------------------------------------------------------------------
def test_integrity_matches_every_recorded_digest():
    module = _load_module()
    checks = module.check_integrity(ROOT)
    assert checks, "the check must verify at least one frozen input"
    assert [c["status"] for c in checks] == ["MATCH"] * len(checks)


def test_integrity_fails_loudly_on_a_changed_file(tmp_path):
    module = _load_module()
    for rel in module.EXPECTED_HASHES:
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("tampered\n", encoding="utf-8")
    checks = module.check_integrity(tmp_path)
    assert all(c["status"] == "MISMATCH" for c in checks)


def test_integrity_fails_loudly_on_a_missing_file(tmp_path):
    module = _load_module()
    checks = module.check_integrity(tmp_path)
    assert all(c["status"] == "MISSING" for c in checks)


# ----------------------------------------------------------------------
# the run itself
# ----------------------------------------------------------------------
def test_the_check_runs_offline(check):
    assert check["model_called"] is False
    assert check["network_used"] is False


def test_every_stage_succeeds(check):
    assert check["step_failures"] == []
    assert check["steps"], "the check must actually run stages"
    assert all(step["returncode"] == 0 for step in check["steps"])


def test_the_check_reports_the_recorded_gates_and_upgrades_none(check):
    assert check["gates_recorded"] == {
        "G1": "PASS", "G2": "NOT YET", "G3": "NOT MET", "G4": "PASS",
        "G5": "NOT_EVALUABLE", "G6": "NOT_MET", "G7": "NOT_MET",
    }
    assert check["pilot"] == "ON_HOLD"


def test_the_g7_verdict_recomputed_from_the_matrix_agrees(check):
    assert check["g7_recomputed_from_matrix"] == "NOT_MET"


def test_the_check_covers_both_candidate_versions_without_verifying_them(check):
    for version in ("v1", "v2"):
        info = check["candidates"][version]
        assert info["n_items"] == 24
        assert info["slices"] == {"L1": 12, "L7": 12}
        assert info["provenance_verified_all_false"] is True
        assert info["review_status"] == ["PENDING_HUMAN_REVIEW"]


def test_the_check_reports_the_label_review_as_ai_assisted(check):
    review = check["label_review"]
    assert review["n_items"] == 12
    assert (review["confirmed"], review["ambiguous"], review["unsupported"]) == (8, 3, 1)
    assert review["gold_labels_changed"] == 0
    assert review["is_human_legal_review"] is False


def test_the_check_keeps_calling_the_mock_screen_a_wiring_check(check):
    text = " ".join(check["notes"]).lower()
    assert "mock" in text and "wiring" in text
    mock_reports = [p for p in check["artifacts"] if "offline_check_screen_mock" in p]
    assert mock_reports


def test_quick_mode_skips_the_mock_screen(tmp_path):
    out = tmp_path / "quick"
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", str(SCRIPT), "--out-dir", str(out), "--quick", "--quiet"],
        cwd=ROOT, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    summary = json.loads((out / "offline_check_summary.json").read_text(encoding="utf-8"))
    assert not any("offline_check_screen_mock" in p for p in summary["artifacts"])
    assert summary["model_called"] is False


# ----------------------------------------------------------------------
# it must not disturb the shipped evidence
# ----------------------------------------------------------------------
def test_a_check_run_does_not_modify_any_shipped_artifact(tmp_path):
    from jurisuq.pilot import sha256_file

    watched = [p for p in sorted((ROOT / "runs").glob("*.json"))]
    watched += [p for p in sorted((ROOT / "data").glob("*.jsonl"))]
    before = {str(p): sha256_file(p) for p in watched}

    proc = subprocess.run(
        [sys.executable, "-X", "utf8", str(SCRIPT), "--out-dir", str(tmp_path / "d"), "--quiet"],
        cwd=ROOT, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr

    after = {str(p): sha256_file(p) for p in watched}
    assert after == before, "the offline check must not touch the shipped evidence"


# ----------------------------------------------------------------------
# the check must be repeatable into the same directory
# ----------------------------------------------------------------------
def test_the_check_can_be_re_run_into_the_same_directory(tmp_path):
    """The check is run more than once. The second run must not fail because it
    finds its own previous output."""
    out = tmp_path / "repeat"
    for attempt in (1, 2):
        proc = subprocess.run(
            [sys.executable, "-X", "utf8", str(SCRIPT), "--out-dir", str(out), "--quiet"],
            cwd=ROOT, capture_output=True, text=True)
        assert proc.returncode == 0, f"attempt {attempt} failed: {proc.stdout}{proc.stderr}"
    summary = json.loads((out / "offline_check_summary.json").read_text(encoding="utf-8"))
    assert summary["step_failures"] == []
    assert (out / "offline_check_screen_mock.json").is_file()
