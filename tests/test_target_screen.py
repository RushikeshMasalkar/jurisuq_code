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


# ----------------------------------------------------------------------
# per-item evidence: a zero yield must be diagnosable after the fact
# ----------------------------------------------------------------------
def test_save_items_writes_the_per_item_evidence(tmp_path):
    """The aggregate report cannot say *why* an item scored zero.

    `build_record` already computes the sampled texts, the judge label and the
    reason for every sample; before this option existed the screen discarded all
    of it, which is why the Stage 2 L7 zero could not be attributed. The records
    written here are the same shape as the frozen runs' `items.jsonl`.
    """
    data = _write(tmp_path, [_item(f"L7-{i}") for i in range(2)]
                  + [_item(f"L1-{i}", "L1") for i in range(2)])
    out = tmp_path / "screen.json"
    items_out = tmp_path / "items.jsonl"
    proc = _run(["--data", str(data), "--out", str(out), "--save-items", str(items_out),
                 "--set", "provider=mock", "--set", "n_samples=3"])
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert items_out.exists()

    records = [json.loads(line) for line in items_out.read_text(encoding="utf-8").splitlines()]
    assert len(records) == 4
    for record in records:
        # the fields that make a failure attributable rather than mysterious
        assert record["sample_texts"] and len(record["sample_texts"]) == 3
        assert len(record["sample_verdict_labels"]) == 3
        assert len(record["sample_verdict_reasons"]) == 3
        assert "repealed_code_share" in record
        assert "asserted_keys" in record
        assert record["slice"] in {"L1", "L7"}

    # the report points at the evidence, and the item count reconciles
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["items_path"].endswith("items.jsonl")
    assert len(records) == report["n_items"]


def test_no_items_file_is_written_unless_asked(tmp_path):
    """Opt-in: the default report keeps its schema and writes one file."""
    data = _write(tmp_path, [_item()])
    out = tmp_path / "screen.json"
    proc = _run(["--data", str(data), "--out", str(out),
                 "--set", "provider=mock", "--set", "n_samples=2"])
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert json.loads(out.read_text(encoding="utf-8"))["items_path"] is None
    assert not (tmp_path / "items.jsonl").exists()


def test_the_screen_refuses_an_existing_output_before_generating(tmp_path):
    """The overwrite guard must fire before sampling, not after.

    Checking at the end meant an accidental re-run spent the whole generation
    budget to discover it could not write. The run header is printed only once
    generation is about to start, so its absence proves the guard ran first.
    """
    data = _write(tmp_path, [_item()])
    out = tmp_path / "screen.json"
    out.write_text("{}", encoding="utf-8")
    proc = _run(["--data", str(data), "--out", str(out),
                 "--set", "provider=mock", "--set", "n_samples=2"])
    assert proc.returncode != 0
    assert "exists" in (proc.stdout + proc.stderr)
    assert "PHASE G SCREEN" not in proc.stdout, "the guard must run before generation"


def test_save_items_refuses_an_existing_file_without_force(tmp_path):
    data = _write(tmp_path, [_item()])
    out = tmp_path / "screen.json"
    items_out = tmp_path / "items.jsonl"
    items_out.write_text("", encoding="utf-8")
    proc = _run(["--data", str(data), "--out", str(out), "--save-items", str(items_out),
                 "--set", "provider=mock", "--set", "n_samples=2"])
    assert proc.returncode != 0
    assert "exists" in (proc.stdout + proc.stderr)
    assert not out.exists(), "no report may be written when the run is refused"


# ----------------------------------------------------------------------
# --slice: the L7 diagnostic must target L7 and nothing else
# ----------------------------------------------------------------------
def test_select_slice_keeps_only_the_requested_slice():
    """The whole point: an L7 diagnostic must not quietly include L1 items."""
    items = ([_item(f"L7-{i}") for i in range(3)]
             + [_item(f"L1-{i}", "L1") for i in range(2)])
    chosen = screen._select_slice(items, "L7")
    assert [i["item_id"] for i in chosen] == ["L7-0", "L7-1", "L7-2"]
    assert all(i["slice"] == "L7" for i in chosen)


def test_select_slice_is_a_no_op_when_not_asked_for():
    """Default behaviour must be byte-for-byte what it was before the flag."""
    items = [_item("L7-0"), _item("L1-0", "L1")]
    assert screen._select_slice(items, None) == items


def test_select_slice_accepts_any_case():
    items = [_item("L7-0"), _item("L1-0", "L1")]
    assert [i["item_id"] for i in screen._select_slice(items, " l7 ")] == ["L7-0"]


def test_select_slice_refuses_a_slice_the_file_does_not_contain():
    """A filter matching nothing would otherwise reach yield_report *after* the
    generation had been paid for, and fail there with a bare ValueError."""
    items = [_item("L7-0"), _item("L1-0", "L1")]
    with pytest.raises(SystemExit) as excinfo:
        screen._select_slice(items, "L9")
    message = str(excinfo.value)
    assert "L9" in message and "matches no items" in message
    assert "L1" in message and "L7" in message      # says what *is* available


def test_select_slice_refuses_a_present_slice_that_the_file_lacks():
    """Asking for L1 in an L7-only file is a mistake worth reporting, not an
    empty run."""
    with pytest.raises(SystemExit) as excinfo:
        screen._select_slice([_item("L7-0")], "L1")
    assert "matches no items" in str(excinfo.value)


# ---- end to end, against the committed candidate set ------------------
def _candidate_ids(slice_name):
    path = ROOT / "data" / "lexuq_target_candidates_v1.jsonl"
    items = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
             if line.strip()]
    return {i["item_id"] for i in items if i["slice"] == slice_name}


def test_the_l7_diagnostic_selects_exactly_the_committed_l7_candidates(tmp_path):
    """The diagnostic this flag exists for, run offline against the real dataset.

    Every one of the twelve committed L7 candidates, and not one L1 item.
    """
    expected = _candidate_ids("L7")
    assert len(expected) == 12
    out = tmp_path / "screen.json"
    items_out = tmp_path / "items.jsonl"
    proc = _run(["--data", str(ROOT / "data" / "lexuq_target_candidates_v1.jsonl"),
                 "--slice", "L7", "--out", str(out), "--save-items", str(items_out),
                 "--set", "provider=mock", "--set", "n_samples=1"])
    assert proc.returncode == 0, proc.stdout + proc.stderr

    records = [json.loads(line) for line in
               items_out.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert {r["item_id"] for r in records} == expected
    assert all(r["slice"] == "L7" for r in records)
    assert not any(r["slice"] == "L1" for r in records)

    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["n_items"] == 12
    assert report["slice_filter"] == "L7"
    assert list(report["yield_by_slice"]) == ["L7"]
    # the contract still describes the *file*, not the subset, so the report must
    # say separately that only one slice was screened
    assert report["candidate_contract"]["slices"] == {"L1": 12, "L7": 12}
    # and the console warns that the run is partial
    assert "does not cover" in proc.stdout


def test_the_slice_cap_is_counted_within_the_slice(tmp_path):
    """`--slice L7 --items 2` must give two L7 items, not one of each slice."""
    data = _write(tmp_path, [_item(f"L7-{i}") for i in range(3)]
                  + [_item(f"L1-{i}", "L1") for i in range(3)])
    out = tmp_path / "screen.json"
    items_out = tmp_path / "items.jsonl"
    proc = _run(["--data", str(data), "--slice", "L7", "--items", "2",
                 "--out", str(out), "--save-items", str(items_out),
                 "--set", "provider=mock", "--set", "n_samples=1"])
    assert proc.returncode == 0, proc.stdout + proc.stderr
    records = [json.loads(line) for line in
               items_out.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(records) == 2
    assert {r["slice"] for r in records} == {"L7"}


def test_without_the_flag_both_slices_are_still_screened(tmp_path):
    """Regression: the default run is unchanged by this feature."""
    data = _write(tmp_path, [_item(f"L7-{i}") for i in range(2)]
                  + [_item(f"L1-{i}", "L1") for i in range(2)])
    out = tmp_path / "screen.json"
    proc = _run(["--data", str(data), "--out", str(out),
                 "--set", "provider=mock", "--set", "n_samples=1"])
    assert proc.returncode == 0, proc.stdout + proc.stderr
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["n_items"] == 4
    assert report["slice_filter"] is None
    assert set(report["yield_by_slice"]) == {"L1", "L7"}


def test_an_unknown_slice_is_refused_before_generating(tmp_path):
    data = _write(tmp_path, [_item()])
    out = tmp_path / "screen.json"
    proc = _run(["--data", str(data), "--slice", "L9", "--out", str(out),
                 "--set", "provider=mock", "--set", "n_samples=1"])
    assert proc.returncode != 0
    assert "L9" in (proc.stdout + proc.stderr)
    assert not out.exists(), "a refused filter must not produce a report"
    assert "PHASE G SCREEN" not in proc.stdout, "the check must run before generation"
