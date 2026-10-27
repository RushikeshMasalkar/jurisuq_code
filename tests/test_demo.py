"""Tests for the offline demonstration (scripts/47_demo.py) and its guards.

The demonstration is the artefact a reader runs first, so the things worth
pinning are the ones that would make it lie:

* it must never modify a shipped artefact under ``runs/`` or ``data/``;
* it must report the gate verdicts the stored evidence records, and must not
  upgrade any of them;
* it must keep calling the mock screen a plumbing check;
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
SCRIPT = ROOT / "scripts" / "47_demo.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("demo47", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def demo() -> dict:
    """Run the full demonstration once into a temporary directory."""
    out = ROOT / "runs" / "demo-test-tmp"
    try:
        proc = subprocess.run(
            [sys.executable, "-X", "utf8", str(SCRIPT), "--out-dir", str(out), "--quiet"],
            cwd=ROOT, capture_output=True, text=True)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        return json.loads((out / "demo_summary.json").read_text(encoding="utf-8"))
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
    assert checks, "the demo must check at least one frozen input"
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
def test_the_demo_runs_offline(demo):
    assert demo["model_called"] is False
    assert demo["network_used"] is False


def test_every_step_succeeds(demo):
    assert demo["step_failures"] == []
    assert demo["steps"], "the demo must actually run steps"
    assert all(step["returncode"] == 0 for step in demo["steps"])


def test_the_demo_reports_the_recorded_gates_and_upgrades_none(demo):
    assert demo["gates_recorded"] == {
        "G1": "PASS", "G2": "NOT YET", "G3": "NOT MET", "G4": "PASS",
        "G5": "NOT_EVALUABLE", "G6": "NOT_MET", "G7": "NOT_MET",
    }
    assert demo["pilot"] == "ON_HOLD"


def test_the_g7_verdict_recomputed_from_the_matrix_agrees(demo):
    assert demo["g7_recomputed_from_matrix"] == "NOT_MET"


def test_the_demo_covers_both_candidate_versions_without_verifying_them(demo):
    for version in ("v1", "v2"):
        info = demo["candidates"][version]
        assert info["n_items"] == 24
        assert info["slices"] == {"L1": 12, "L7": 12}
        assert info["provenance_verified_all_false"] is True
        assert info["review_status"] == ["PENDING_HUMAN_REVIEW"]


def test_the_demo_reports_the_label_review_as_ai_assisted(demo):
    review = demo["label_review"]
    assert review["n_items"] == 12
    assert (review["confirmed"], review["ambiguous"], review["unsupported"]) == (8, 3, 1)
    assert review["gold_labels_changed"] == 0
    assert review["is_human_legal_review"] is False


def test_the_demo_keeps_calling_the_mock_screen_a_plumbing_check(demo):
    text = " ".join(demo["disclaimers"]).lower()
    assert "mock" in text and "plumbing" in text
    mock_reports = [p for p in demo["artifacts"] if "demo_screen_mock" in p]
    assert mock_reports


def test_quick_mode_skips_the_mock_screen(tmp_path):
    out = tmp_path / "quick"
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", str(SCRIPT), "--out-dir", str(out), "--quick", "--quiet"],
        cwd=ROOT, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    summary = json.loads((out / "demo_summary.json").read_text(encoding="utf-8"))
    assert not any("demo_screen_mock" in p for p in summary["artifacts"])
    assert summary["model_called"] is False


# ----------------------------------------------------------------------
# it must not disturb the shipped evidence
# ----------------------------------------------------------------------
def test_a_demo_run_does_not_modify_any_shipped_artifact(tmp_path):
    from jurisuq.pilot import sha256_file

    watched = [p for p in sorted((ROOT / "runs").glob("*.json"))]
    watched += [p for p in sorted((ROOT / "data").glob("*.jsonl"))]
    before = {str(p): sha256_file(p) for p in watched}

    proc = subprocess.run(
        [sys.executable, "-X", "utf8", str(SCRIPT), "--out-dir", str(tmp_path / "d"), "--quiet"],
        cwd=ROOT, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr

    after = {str(p): sha256_file(p) for p in watched}
    assert after == before, "the demonstration must not touch the shipped evidence"


# ----------------------------------------------------------------------
# the captured sample output is labelled, and still describes the demo
# ----------------------------------------------------------------------
def test_the_captured_sample_output_exists_and_is_labelled():
    path = ROOT / "reports" / "demo_sample_output.txt"
    assert path.is_file(), "the demonstration must ship a captured sample"
    text = path.read_text(encoding="utf-8")
    head = text.lower()
    assert "demonstration" in head and "not a research result" in head
    assert "no model was" in head
    assert "by construction" in head, "the mock accuracy must be labelled"
    assert "G7: NOT_MET" in text
    assert "RESULT: ok" in text
