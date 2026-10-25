"""Tests for the Phase G yield screen (scripts/41_screen_target_yield.py).

The screen is the only Phase G entry point that can call a model, so these tests
pin two things: it refuses to generate without explicit permission, and it runs
end to end offline against the mock provider.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "41_screen_target_yield.py"
sys.path.insert(0, str(ROOT / "scripts"))

import importlib.util

_spec = importlib.util.spec_from_file_location("screen_yield", SCRIPT)
screen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(screen)


def _item(item_id="L7-theft-001", slice_name="L7", **overrides):
    item = {
        "item_id": item_id,
        "pair_id": "theft-001",
        "slice": slice_name,
        "topic": "theft",
        "template": "T1",
        "question": "Which section applies to this situation?",
        "gold": {"act": "BNS", "provision": "303(2)", "label": "theft"},
        "trap": {"act": "IPC", "provision": "379", "label": "the repealed provision"},
        # Stage 2 requires unverified provenance on every candidate item; these
        # fixtures are proposals for measurement, not reviewed benchmark rows.
        "provenance": {"source": "test fixture", "verified": False},
    }
    item.update(overrides)
    return item


def _write(tmp_path, items, name="candidates.jsonl"):
    path = tmp_path / name
    path.write_text("\n".join(json.dumps(i) for i in items) + "\n", encoding="utf-8")
    return path


def _run(args, cwd=ROOT):
    return subprocess.run([sys.executable, str(SCRIPT)] + args, cwd=str(cwd),
                          capture_output=True, text=True, timeout=300)


# ----------------------------------------------------------------------
# validation
# ----------------------------------------------------------------------
def test_load_candidates_accepts_a_valid_file(tmp_path):
    items = screen.load_candidates(_write(tmp_path, [_item(), _item("L1-theft-002", "L1")]))
    assert len(items) == 2


def test_load_candidates_rejects_a_missing_file(tmp_path):
    with pytest.raises(SystemExit):
        screen.load_candidates(tmp_path / "absent.jsonl")


def test_load_candidates_rejects_an_empty_file(tmp_path):
    path = tmp_path / "empty.jsonl"
    path.write_text("\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        screen.load_candidates(path)


@pytest.mark.parametrize("mutation,message", [
    ({"question": ""}, "missing"),
    ({"gold": {"act": "BNS"}}, "gold.act"),
    ({"slice": "L9"}, "slice"),
    ({"item_id": ""}, "missing"),
])
def test_load_candidates_rejects_bad_items(tmp_path, mutation, message):
    path = _write(tmp_path, [_item(**mutation)])
    with pytest.raises(SystemExit) as excinfo:
        screen.load_candidates(path)
    assert message in str(excinfo.value)


@pytest.mark.parametrize("provenance,message", [
    ({"verified": True, "source": "asserted checked"}, "verified"),
    ({"source": "no flag at all"}, "'verified' flag"),
    ({"verified": False}, "provenance.source"),
    ("not-an-object", "provenance object"),
])
def test_load_candidates_refuses_provenance_that_breaks_the_contract(
        tmp_path, provenance, message):
    """Stage 2 items are unverified by construction; the screen must refuse
    anything that claims otherwise or does not say where it came from."""
    path = _write(tmp_path, [_item(provenance=provenance)])
    with pytest.raises(SystemExit) as excinfo:
        screen.load_candidates(path)
    assert message in str(excinfo.value)


def test_load_candidates_rejects_an_item_with_no_provenance(tmp_path):
    item = _item()
    del item["provenance"]
    with pytest.raises(SystemExit) as excinfo:
        screen.load_candidates(_write(tmp_path, [item]))
    assert "provenance" in str(excinfo.value)


def test_duplicate_item_ids_are_rejected(tmp_path):
    with pytest.raises(SystemExit) as excinfo:
        screen.load_candidates(_write(tmp_path, [_item(), _item()]))
    assert "duplicate" in str(excinfo.value)


# ----------------------------------------------------------------------
# capping must not empty one side of the screen
# ----------------------------------------------------------------------
def test_limit_keeps_both_slices_when_capping():
    items = ([_item(f"L7-{i}") for i in range(10)]
             + [_item(f"L1-{i}", "L1") for i in range(10)])
    capped = screen._limit(items, 6)
    assert len(capped) == 6
    assert {i["slice"] for i in capped} == {"L1", "L7"}


def test_limit_rejects_a_non_positive_count():
    with pytest.raises(SystemExit):
        screen._limit([_item()], 0)


def test_limit_beyond_the_set_size_returns_everything():
    items = [_item(f"L7-{i}") for i in range(3)]
    assert screen._limit(items, 99) == items


# ----------------------------------------------------------------------
# the generation guard
# ----------------------------------------------------------------------
def test_a_real_provider_is_refused_without_allow_generation(tmp_path):
    path = _write(tmp_path, [_item()])
    proc = _run(["--data", str(path), "--out", str(tmp_path / "o.json"),
                 "--set", "provider=openai"])
    assert proc.returncode != 0
    assert "--allow-generation" in (proc.stdout + proc.stderr)
    assert not (tmp_path / "o.json").exists()


def test_the_guard_names_the_provider(tmp_path):
    path = _write(tmp_path, [_item()])
    proc = _run(["--data", str(path), "--out", str(tmp_path / "o.json"),
                 "--set", "provider=openai"])
    assert "openai" in (proc.stdout + proc.stderr)


# ----------------------------------------------------------------------
# end to end, offline
# ----------------------------------------------------------------------
def test_mock_screen_runs_end_to_end_and_writes_a_report(tmp_path):
    data = _write(tmp_path, [_item(f"L7-{i}") for i in range(2)]
                  + [_item(f"L1-{i}", "L1") for i in range(2)])
    out = tmp_path / "screen.json"
    proc = _run(["--data", str(data), "--out", str(out),
                 "--set", "provider=mock", "--set", "n_samples=3"])
    assert proc.returncode == 0, proc.stdout + proc.stderr
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["phase"] == "G"
    assert report["is_mock"] is True
    assert report["n_items"] == 4
    assert report["n_samples_per_item"] == 3
    assert report["yield"]["overall"]["items"] == 4
    assert "not a gate" in report["verdict_note"]
    assert set(report["yield"]["topics"]) == {"theft"}
    # provenance: the report names the exact bytes it screened and the contract
    # they satisfied, so a yield cannot be quoted against a different item set
    import hashlib
    expected = hashlib.sha256(data.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    assert report["data_sha256"] == expected
    assert report["candidate_contract"]["provenance_verified"] is False
    assert report["candidate_contract"]["slices"] == {"L1": 2, "L7": 2}


def test_the_screen_refuses_an_item_set_that_claims_verification(tmp_path):
    """End to end: a set marked verified never reaches the generator."""
    data = _write(tmp_path, [_item(provenance={"source": "s", "verified": True})])
    out = tmp_path / "screen.json"
    proc = _run(["--data", str(data), "--out", str(out),
                 "--set", "provider=mock", "--set", "n_samples=2"])
    assert proc.returncode != 0
    assert "verified" in (proc.stdout + proc.stderr)
    assert not out.exists(), "a refused item set must not produce a report"


def test_mock_screen_refuses_to_overwrite_without_force(tmp_path):
    data = _write(tmp_path, [_item()])
    out = tmp_path / "screen.json"
    out.write_text("{}", encoding="utf-8")
    proc = _run(["--data", str(data), "--out", str(out),
                 "--set", "provider=mock", "--set", "n_samples=2"])
    assert proc.returncode != 0
    assert "exists" in (proc.stdout + proc.stderr)


def test_screen_report_flags_the_mock_as_not_a_measurement(tmp_path):
    data = _write(tmp_path, [_item()])
    out = tmp_path / "screen.json"
    proc = _run(["--data", str(data), "--out", str(out),
                 "--set", "provider=mock", "--set", "n_samples=2"])
    assert proc.returncode == 0
    assert "plumbing check" in proc.stdout
    assert json.loads(out.read_text(encoding="utf-8"))["is_mock"] is True


def test_the_screen_reports_yield_per_slice(tmp_path):
    """G7 asks about both classes *per slice*, so an aggregate rate alone cannot
    show whether the L7 arm produced any correct majority answer."""
    data = _write(tmp_path, [_item(f"L7-{i}") for i in range(2)]
                  + [_item(f"L1-{i}", "L1") for i in range(2)])
    out = tmp_path / "screen.json"
    proc = _run(["--data", str(data), "--out", str(out),
                 "--set", "provider=mock", "--set", "n_samples=2"])
    assert proc.returncode == 0, proc.stdout + proc.stderr
    report = json.loads(out.read_text(encoding="utf-8"))
    by_slice = report["yield_by_slice"]
    assert set(by_slice) == {"L1", "L7"}
    assert by_slice["L1"]["overall"]["items"] == 2
    assert by_slice["L7"]["overall"]["items"] == 2
    # the slice breakdown must reconcile with the aggregate
    assert (by_slice["L1"]["overall"]["items"]
            + by_slice["L7"]["overall"]["items"]) == report["yield"]["overall"]["items"]
    # and it is printed, so a reader of the console sees it
    assert "L7" in proc.stdout
