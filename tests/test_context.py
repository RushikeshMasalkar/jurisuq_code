"""Phase C unit tests: statute store, links, context packs, both scripts.

Every test here runs on the standard library + pytest: no torch, no
transformers, no network. The five acceptance requirements of the engineering
spec (v2, section 15.3) are marked with [SPEC].
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys

import pytest

from jurisuq.context import (StatuteStore, attach_context, build_context,
                             build_rows, is_store_ref, load_links,
                             load_statutes, relation_between, validate_rows)
from jurisuq.context.statute import base_key, normalize_key
from jurisuq.facts import OFFENCES

ROOT = pathlib.Path(__file__).resolve().parents[1]
CROSSWALK = ROOT / "data" / "relations" / "crosswalk_v1.jsonl"
FROZEN_RUN = ROOT / "runs" / "phaseA-laptop-v2-rejudged" / "items.jsonl"


@pytest.fixture(scope="module")
def store() -> StatuteStore:
    rows = build_rows()
    assert validate_rows(rows) == [], validate_rows(rows)
    return StatuteStore(rows)


# --------------------------------------------------------------------------
# [SPEC] 15.3: boundary dates are exact
# --------------------------------------------------------------------------

def test_boundary_ipc302_day_before_transition(store):
    assert store.in_force("IPC 302", "2024-06-30") is True


def test_boundary_ipc302_on_transition_day(store):
    assert store.in_force("IPC 302", "2024-07-01") is False


def test_boundary_bns103_on_transition_day(store):
    assert store.in_force("BNS 103", "2024-07-01") is True


def test_boundary_bns103_day_before_transition(store):
    assert store.in_force("BNS 103", "2024-06-30") is False


def test_windows_bracket_the_transition(store):
    assert store.window("IPC 302") == ("1862-01-01", "2024-07-01")
    assert store.window("BNS 103") == ("2024-07-01", None)


# --------------------------------------------------------------------------
# [SPEC] 15.3: unknown is not False
# --------------------------------------------------------------------------

def test_unknown_key_returns_none_not_false(store):
    result = store.in_force("IPC 99999", "2024-07-01")
    assert result is None
    assert result is not False


def test_unknown_key_window_is_none(store):
    assert store.window("IPC 99999") is None
    assert store.successor("IPC 99999") is None
    assert store.predecessor("IPC 99999") is None


def test_unknown_before_enactment_and_after_repeal(store):
    # known keys outside their window are False, not None -- the two cases
    # must stay distinguishable
    assert store.in_force("IPC 302", "1800-01-01") is False
    assert store.in_force("BNS 103", "2020-01-01") is False


# --------------------------------------------------------------------------
# [SPEC] 15.3: coverage is reported
# --------------------------------------------------------------------------

def test_coverage_counts_known_and_unknown(store):
    cov = store.coverage(["IPC 302", "BNS 103", "IPC 99999", "BNS 888"])
    assert cov["assertions"] == 4
    assert cov["known"] == 2
    assert cov["unknown"] == 2
    assert cov["unknown_keys"] == ["BNS 888", "IPC 99999"]


@pytest.mark.skipif(not FROZEN_RUN.exists(),
                    reason="frozen Phase A run not present")
def test_coverage_over_frozen_phase_a_run(store):
    rows = [json.loads(l) for l in FROZEN_RUN.read_text().splitlines()
            if l.strip()]
    keys = sorted({k for r in rows for k in (r.get("asserted_keys") or [])
                   if is_store_ref(k)})
    cov = store.coverage(keys)
    assert cov["assertions"] == len(keys)
    assert cov["known"] + cov["unknown"] == cov["assertions"]
    # the ten cluster provisions and the most-asserted extensions are covered
    assert cov["known"] >= 20
    for must in ("IPC 302", "BNS 103", "IPC 378", "IPC 307"):
        assert must not in cov["unknown_keys"]


# --------------------------------------------------------------------------
# [SPEC] 15.3: links are symmetric
# --------------------------------------------------------------------------

@pytest.mark.skipif(not CROSSWALK.exists(), reason="crosswalk not shipped")
def test_relation_between_is_symmetric_on_real_crosswalk():
    links = load_links(CROSSWALK)
    assert links, "crosswalk must not be empty"
    for (a, b) in links:
        assert relation_between(a, b, links) == relation_between(b, a, links)


@pytest.mark.skipif(not CROSSWALK.exists(), reason="crosswalk not shipped")
def test_relation_between_declared_pair():
    links = load_links(CROSSWALK)
    assert relation_between("IPC 302", "BNS 103", links) == "successor_of"
    assert relation_between("BNS 103", "IPC 302", links) == "successor_of"


def test_relation_between_undeclared_is_none():
    assert relation_between("IPC 302", "IPC 99999", {}) is None


# --------------------------------------------------------------------------
# [SPEC] 15.3: no learned component
# --------------------------------------------------------------------------

def test_no_learning_component_in_phase_c_modules():
    """The module surface imports nothing from torch/transformers -- checked
    on the real import graph (AST), not on text, so docstrings that *mention*
    the ban do not trip the test."""
    import ast

    banned = {"torch", "transformers"}
    ctx_dir = ROOT / "jurisuq" / "context"
    for path in sorted(ctx_dir.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                mods = {alias.name.split(".")[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module:
                mods = {node.module.split(".")[0]}
            else:
                continue
            assert not (mods & banned), \
                f"{path.name}: imports forbidden module(s) {mods & banned}"


# --------------------------------------------------------------------------
# table structure
# --------------------------------------------------------------------------

def test_generated_table_is_valid(store):
    assert len(store) == 48  # 10 cluster + 3 distractor + 11 extension pairs
    assert all(not r["verified"] for r in store.rows())


def test_all_ten_clusters_covered(store):
    clusters = {r["offence_cluster"] for r in store.rows()}
    assert clusters == set(OFFENCES)


def test_successor_predecessor_are_symmetric(store):
    for r in store.rows():
        if r["successor"]:
            assert store.predecessor(r["successor"]) == \
                f"{r['act']} {r['section']}"
        if r["predecessor"]:
            assert store.successor(r["predecessor"]) == \
                f"{r['act']} {r['section']}"


def test_every_ipc_row_is_repealed_and_every_bns_row_in_force(store):
    for r in store.rows():
        if r["act"] == "IPC":
            assert r["in_force_until"] == "2024-07-01"
            assert store.in_force(f"IPC {r['section']}", "2026-10-01") is False
        else:
            assert r["in_force_until"] is None
            assert store.in_force(f"BNS {r['section']}", "2026-10-01") is True


def test_validate_rows_catches_a_broken_row():
    rows = build_rows()
    rows[0]["text_excerpt"] = ""          # empty excerpt
    rows[1]["successor"] = "IPC 302"      # asymmetric link
    errors = validate_rows(rows)
    assert any("empty text_excerpt" in e for e in errors)
    assert any("symmetric" in e for e in errors)


def test_key_normalisation_and_base_fallback(store):
    assert normalize_key(" ipc   302 ") == "IPC 302"
    assert base_key("IPC 307(1)") == "IPC 307"
    # subsections resolve to their section: validity is a section property
    assert store.in_force("IPC 307(1)", "2024-07-01") is False
    assert store.in_force("BNS 127(3)", "2026-10-01") is True
    assert store.in_force("IPC 34(2)", "2024-07-01") is False


def test_is_store_ref_excludes_sentinels():
    assert not is_store_ref("NONE")
    assert not is_store_ref("FOREIGN:ZA-1")
    assert not is_store_ref("UNKNOWN 17")
    assert not is_store_ref("IPC (no section)")
    assert is_store_ref("IPC 302")
    assert is_store_ref("BNS 303(2)")


# --------------------------------------------------------------------------
# context packs
# --------------------------------------------------------------------------

def _murder_record():
    return {
        "item_id": "L7-murder-000", "slice": "L7", "topic": "murder",
        "gold": {"act": "BNS", "provision": "103", "label": "murder"},
        "trap": {"act": "IPC", "provision": "302",
                 "label": "the repealed provision"},
        "asserted_keys": ["IPC 302", "IPC 302", "BNS 103", "NONE"],
    }


@pytest.mark.skipif(not CROSSWALK.exists(), reason="crosswalk not shipped")
def test_build_context_matches_the_spec_example(store):
    links = load_links(CROSSWALK)
    ctx = build_context(_murder_record(), store, links,
                        as_of="2026-10-01", jurisdiction="IN")
    assert ctx["as_of"] == "2026-10-01"
    assert ctx["jurisdiction"] == "IN"
    assert ctx["crosswalk_relation"] == "successor_of"
    assert ctx["validity"]["IPC 302"] == {
        "in_force": False, "window": ["1862-01-01", "2024-07-01"]}
    assert ctx["validity"]["BNS 103"] == {
        "in_force": True, "window": ["2024-07-01", None]}
    # coverage counts real refs among asserted keys only (NONE is excluded)
    assert ctx["coverage"]["known"] == 2
    assert ctx["coverage"]["unknown"] == 0
    assert ctx["excluded_assertions"] == 1


def test_build_context_carries_unknown_as_none(store):
    rec = {"gold": {"act": "IPC", "provision": "99999"}, "trap": None,
           "asserted_keys": ["IPC 99999", "FOREIGN:XX-1", "NONE"]}
    ctx = build_context(rec, store, {}, as_of="2026-10-01")
    assert ctx["validity"]["IPC 99999"]["in_force"] is None
    assert ctx["validity"]["IPC 99999"]["window"] is None
    assert ctx["coverage"] == {"assertions": 1, "known": 0, "unknown": 1,
                               "unknown_keys": ["IPC 99999"]}
    assert ctx["excluded_assertions"] == 2
    assert ctx["crosswalk_relation"] is None


def test_attach_context_replaces_previous_pack(store):
    rec = {"context": {"stale": True}}
    ctx = build_context(_murder_record(), store, {}, as_of="2026-10-01")
    attach_context(rec, ctx)
    assert rec["context"] is ctx
    assert "stale" not in rec["context"]


# --------------------------------------------------------------------------
# scripts, end to end
# --------------------------------------------------------------------------

def _run_script(name: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / name), *args],
        cwd=ROOT, capture_output=True, text=True, timeout=300)


def test_script_20_builds_a_loadable_table(tmp_path):
    out = tmp_path / "statutes_v1.jsonl"
    p = _run_script("20_build_statutes.py", "--out", str(out))
    assert p.returncode == 0, p.stdout + p.stderr
    assert out.exists()
    s = load_statutes(out)                       # re-validates on load
    assert len(s) == 48
    assert s.in_force("IPC 302", "2024-07-01") is False
    assert s.in_force("BNS 103", "2024-07-01") is True
    manifest = json.loads((tmp_path / "statutes_v1.manifest.json")
                          .read_text())
    assert manifest["n_rows"] == 48
    assert 0.0 <= manifest["verified_share"] <= 1.0  # share changes after verification pass
    assert manifest["sha256"]


def test_script_21_packs_a_run_and_leaves_the_source_untouched(tmp_path):
    # a minimal fixture run: two items, one per slice
    runs = tmp_path / "runs"
    src = runs / "fixtureA"
    src.mkdir(parents=True)
    items = [
        {"item_id": "L7-murder-000", "slice": "L7", "topic": "murder",
         "gold": {"act": "BNS", "provision": "103"},
         "trap": {"act": "IPC", "provision": "302"},
         "asserted_keys": ["IPC 302", "IPC 302", "NONE"]},
        {"item_id": "L1-murder-000", "slice": "L1", "topic": "murder",
         "gold": {"act": "IPC", "provision": "302"},
         "trap": {"act": "BNS", "provision": "103"},
         "asserted_keys": ["IPC 302", "IPC 99999"]},
    ]
    (src / "items.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in items))

    statutes = tmp_path / "statutes_v1.jsonl"
    b = _run_script("20_build_statutes.py", "--out", str(statutes))
    assert b.returncode == 0, b.stdout + b.stderr

    p = _run_script("21_attach_context.py", "--run-id", "fixtureA",
                    "--out-suffix", "+ctx", "--as-of", "2026-10-01",
                    "--statutes", str(statutes),
                    "--runs-dir", str(runs))
    assert p.returncode == 0, p.stdout + p.stderr
    assert "SOURCE RUN UNCHANGED" in p.stdout

    out_dir = runs / "fixtureA+ctx"
    packed = [json.loads(l) for l in
              (out_dir / "items.jsonl").read_text().splitlines()]
    assert len(packed) == 2
    assert all("context" in r for r in packed)
    assert packed[0]["context"]["crosswalk_relation"] == "successor_of"
    assert packed[0]["context"]["validity"]["IPC 302"]["in_force"] is False
    assert packed[0]["context"]["validity"]["BNS 103"]["in_force"] is True
    assert packed[1]["context"]["coverage"]["unknown"] == 1

    report = json.loads((out_dir / "context_report.json").read_text())
    assert report["phase_a_untouched"] is True
    assert report["source_tree_hash_before"] == report["source_tree_hash_after"]
    # item 1 refs {IPC 302} -> known 1; item 2 refs {IPC 302, IPC 99999}
    # -> known 1, unknown 1; totals: 3 lookups, 2 known, 1 unknown
    assert report["assertion_lookups"] == 3
    assert report["known"] == 2 and report["unknown"] == 1
    assert report["unknown_keys"] == {"IPC 99999": 1}
    assert report["excluded_assertions"] == 1

    meta = json.loads((out_dir / "meta.json").read_text())
    assert meta["phase"] == "C"
    assert meta["source_run"] == "fixtureA"


def test_script_21_refuses_to_overwrite_and_reports_missing_run(tmp_path):
    runs = tmp_path / "runs"
    src = runs / "fixtureB"
    src.mkdir(parents=True)
    (src / "items.jsonl").write_text("")
    out = runs / "fixtureB+ctx"
    out.mkdir()

    p = _run_script("21_attach_context.py", "--run-id", "fixtureB",
                    "--runs-dir", str(runs))
    assert p.returncode == 1
    assert "already exists" in p.stdout

    q = _run_script("21_attach_context.py", "--run-id", "no-such-run",
                    "--runs-dir", str(runs))
    assert q.returncode == 1
    assert "no such run" in q.stdout


# --------------------------------------------------------------------------
# byte-level reproducibility (the Windows CRLF incident) and the
# human-verification workflow
# --------------------------------------------------------------------------

CANONICAL_TABLE_SHA = ("7be783e38c21effb24734a8be5400b9bd0c358d63130bb896aa13220"
                       "ea09b61f")


def test_script_20_output_is_lf_and_hash_is_canonical(tmp_path):
    """The table must be byte-identical on every platform: LF endings only,
    and the sha256 recorded in PHASE-C.md. This test fails (correctly) if
    table.py changes -- then the documented hash must be re-pinned."""
    import hashlib

    out = tmp_path / "statutes_v1.jsonl"
    p = _run_script("20_build_statutes.py", "--out", str(out),
                    "--no-overrides")
    assert p.returncode == 0, p.stdout + p.stderr
    data = out.read_bytes()
    assert b"\r" not in data, "table must use LF line endings everywhere"
    assert hashlib.sha256(data).hexdigest() == CANONICAL_TABLE_SHA
    manifest = json.loads((tmp_path / "statutes_v1.manifest.json").read_text())
    assert manifest["sha256"] == CANONICAL_TABLE_SHA
    assert manifest["line_endings"] == "lf"


def test_crlf_table_still_loads(tmp_path, store):
    """A CRLF-written table (what an unfixed Windows writer produces) is
    semantically identical: json tolerates the carriage returns. This is why
    the hash mismatch broke nothing downstream -- and why the fix belongs in
    the writer, not the loader."""
    rows_file = tmp_path / "crlf.jsonl"
    payload = "".join(json.dumps(r) + "\n" for r in store.rows())
    rows_file.write_bytes(payload.replace("\n", "\r\n").encode("utf-8"))
    s = load_statutes(rows_file)
    assert s.in_force("IPC 302", "2024-07-01") is False
    assert s.in_force("BNS 103", "2024-07-01") is True
    assert len(s) == len(store)


def test_overrides_flip_verified_and_change_the_hash(tmp_path):
    import hashlib

    out = tmp_path / "statutes_v1.jsonl"
    ov = tmp_path / "overrides.jsonl"
    ov.write_text(json.dumps({
        "key": "IPC 302", "verified": True,
        "official_source": "India Code, Act 45 of 1860",
    }) + "\n" + json.dumps({
        "key": "BNS 999", "verified": True,   # not in the table
    }) + "\n", encoding="utf-8", newline="\n")

    p = _run_script("20_build_statutes.py", "--out", str(out),
                    "--overrides", str(ov))
    assert p.returncode == 0, p.stdout + p.stderr
    assert "not in table" in p.stdout            # unmatched key is reported
    s = load_statutes(out)
    by_key = {(r["act"], r["section"]): r for r in s.rows()}
    assert by_key[("IPC", "302")]["verified"] is True
    assert s.verified_share() == 1 / 48
    assert hashlib.sha256(out.read_bytes()).hexdigest() != CANONICAL_TABLE_SHA
    manifest = json.loads((tmp_path / "statutes_v1.manifest.json").read_text())
    assert manifest["overrides_applied"] == 1
    assert manifest["overrides_unmatched"] == ["BNS 999"]

    # ignoring the overrides restores the canonical bytes exactly
    q = _run_script("20_build_statutes.py", "--out", str(out),
                    "--no-overrides")
    assert q.returncode == 0
    assert hashlib.sha256(out.read_bytes()).hexdigest() == CANONICAL_TABLE_SHA


def test_script_22_export_apply_roundtrip(tmp_path):
    import csv as _csv

    checklist = tmp_path / "checklist.csv"
    ov = tmp_path / "overrides.jsonl"
    e = _run_script("22_verify_statutes.py", "--export",
                    "--checklist", str(checklist))
    assert e.returncode == 0, e.stdout + e.stderr
    rows = list(_csv.DictReader(checklist.open(encoding="utf-8")))
    assert len(rows) == 48
    assert all(r["verified_ok"] == "" for r in rows)

    # simulate the human pass: two verified, one explicitly rejected
    for r in rows:
        if r["key"] == "IPC 302":
            r["verified_ok"] = "yes"
            r["official_source"] = "India Code, Act 45 of 1860, s.302"
        elif r["key"] == "BNS 103":
            r["verified_ok"] = "yes"
        elif r["key"] == "IPC 506":
            r["verified_ok"] = "no"
            r["notes"] = "Schedule places criminal intimidation at 351(4)-(5)"
    with checklist.open("w", encoding="utf-8", newline="") as f:
        w = _csv.DictWriter(f, fieldnames=list(rows[0].keys()),
                            lineterminator="\n")
        w.writeheader()
        w.writerows(rows)

    a = _run_script("22_verify_statutes.py", "--apply",
                    "--checklist", str(checklist), "--overrides", str(ov))
    assert a.returncode == 0, a.stdout + a.stderr
    entries = [json.loads(l) for l in ov.read_text().splitlines() if l.strip()]
    assert {e2["key"] for e2 in entries} == {"IPC 302", "BNS 103"}
    assert all(e2["verified"] is True for e2 in entries)

    out = tmp_path / "statutes_v1.jsonl"
    b = _run_script("20_build_statutes.py", "--out", str(out),
                    "--overrides", str(ov))
    assert b.returncode == 0, b.stdout + b.stderr
    s = load_statutes(out)
    assert s.verified_share() == 2 / 48
