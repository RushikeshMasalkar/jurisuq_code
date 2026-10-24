#!/usr/bin/env python3
"""42 - Phase G: build the §21.2 evaluation matrix from frozen runs.

Offline. Reads stored records only: no model, no generation, no API call.

Produces ``runs/phaseG_eval_matrix.json`` with

* the headline matrix on the frozen pair-grouped **evaluation** partition, which
  is the only partition on which every method is out-of-sample (the calibrated
  legal-aware method was fitted on the development partition, so reporting it
  in-sample would overstate it);
* a descriptive matrix on **all items**, explicitly flagged as in-sample for the
  fitted method;
* the §21.1 columns: per-slice judge coverage, slices reported separately, and
  every undefined value carrying a reason code;
* the §12 Gate G7 status;
* which §21.2 evaluation arms are present and which are missing.

    python scripts/42_build_eval_matrix.py
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from jurisuq.evaluation.matrix import METHODS, SHORT_REASONS, build_matrix, gate_g7
from jurisuq.uncertainty.io import read_jsonl, tree_hash, write_json
from jurisuq.uncertainty.split import load_pair_ids, split_name

DEFAULT_SOURCE = "phaseA-laptop-v2-rejudged+ctx-r2+typed+warrant+uq-exact"
DEFAULT_CAL = "phaseA-laptop-v2-rejudged+ctx-r2+typed+warrant+uq-exact+cal-r2"


def _git_commit() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                              text=True, timeout=10).stdout.strip() or None
    except Exception:
        return None


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_calibration(run_dir: Path) -> dict[str, dict]:
    """p_reliable, harm_class and action per item, from the Phase F run."""
    path = run_dir / "items.jsonl"
    if not path.is_file():
        raise SystemExit(f"ERROR: missing calibration run artefacts: {path}")
    return {r["item_id"]: r for r in read_jsonl(path)}


def _attach_phase_f(records: list[dict], cal: dict[str, dict]) -> dict:
    """Join the calibrated fields by item_id and report what could not be joined."""
    joined = missing = 0
    for record in records:
        source = cal.get(record["item_id"])
        if source is None:
            missing += 1
            record["p_reliable"] = None
            record["harm_class"] = None
            continue
        joined += 1
        record["p_reliable"] = source.get("p_reliable")
        record["harm_class"] = source.get("harm_class")
        record["action"] = source.get("action")
    return {"items_joined": joined, "items_missing": missing,
            "join_key": "item_id",
            "fields": ["p_reliable", "harm_class", "action"]}


def _calibration_coverage(records: list[dict]) -> dict:
    """How far the Phase F calibrated probability actually reaches.

    `p_reliable` exists only where Phase F could fit and apply a calibration
    map, so the calibrated legal-aware method is scored on a subset. Stating
    the subset per slice stops a partial column from reading as a full one.
    """
    coverage: dict[str, dict] = {}
    for record in records:
        slice_name = record.get("slice") or "unknown"
        block = coverage.setdefault(slice_name, {"n_items": 0, "n_with_p_reliable": 0,
                                                "n_with_harm_class": 0})
        block["n_items"] += 1
        if isinstance(record.get("p_reliable"), (int, float)):
            block["n_with_p_reliable"] += 1
        if record.get("harm_class"):
            block["n_with_harm_class"] += 1
    for block in coverage.values():
        block["p_reliable_fraction"] = (block["n_with_p_reliable"] / block["n_items"]
                                        if block["n_items"] else None)
    return {
        "per_slice": coverage,
        "consequence": ("legal_aware is defined only where p_reliable exists; on a "
                        "slice with none it is reported as undefined rather than "
                        "silently dropped"),
    }


def _partition(records: list[dict], payload: dict, pair_ids: dict[str, str]) -> dict[str, str]:
    seed = payload["split"]["seed"]
    fraction = float(payload["split"]["test_fraction"])
    out = {}
    for record in records:
        part = split_name(pair_ids[record["item_id"]], seed=seed, test_fraction=fraction)
        out[record["item_id"]] = "evaluation" if part == "test" else "development"
    stored = set(payload["split"]["test_item_ids"])
    recomputed = {i for i, p in out.items() if p == "evaluation"}
    if stored != recomputed:
        raise SystemExit("ERROR: recomputed holdout does not match the stored split")
    return out


def _action_census(records: list[dict]) -> dict:
    counts: dict[str, int] = {}
    for record in records:
        action = record.get("action")
        if isinstance(action, str) and action:
            counts[action] = counts.get(action, 0) + 1
    total = sum(counts.values())
    return {"counts": counts, "n_decided": total,
            "abstention_rate": (counts.get("abstain", 0) / total) if total else None,
            "note": ("abstention is a decision-layer quantity, not a property of an "
                     "uncertainty score, so it is reported once here rather than per "
                     "method row")}


def _arms() -> dict:
    """The §21.2 generator and slice axes, and what is actually available."""
    return {
        "generator": {
            "present": ["qwen2.5-7b-instruct (p2-structured, M=10) — frozen Phase A arm"],
            "missing": [
                {"arm": "second laptop model / second quantisation",
                 "status": "deferred",
                 "reason": "requires a cost and storage review; no second arm has been "
                           "run, so the guide's two-size/four-bit axis is 1 of 2"},
                {"arm": "one API model at evaluation time",
                 "status": "deferred",
                 "reason": "not approved; no generation or spend authorised in Stage 1"},
            ],
        },
        "slices": {
            "present": ["L1 control", "L7 target"],
            "missing": [
                {"arm": "external benchmark task",
                 "status": "deferred",
                 "reason": "dataset selection and licensing require separate approval; "
                           "no benchmark data is present in the repository"},
            ],
        },
        "note": ("a missing arm is reported here and left out of the tables; nothing is "
                 "estimated for it"),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-id", default=DEFAULT_SOURCE)
    ap.add_argument("--cal-run-id", default=DEFAULT_CAL)
    ap.add_argument("--config", default=str(ROOT / "configs" / "phase_g_target.json"))
    ap.add_argument("--out", default="runs/phaseG_eval_matrix.json")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    for name in (args.run_id, args.cal_run_id):
        if Path(name).name != name or "/" in name or "\\" in name:
            ap.error("--run-id values must be single run-directory names")

    source_dir = ROOT / "runs" / args.run_id
    cal_dir = ROOT / "runs" / args.cal_run_id
    items_path = source_dir / "items.jsonl"
    model_path = source_dir / "uq_model.json"
    for required in (items_path, model_path):
        if not required.is_file():
            raise SystemExit(f"ERROR: missing input: {required}")

    before = {"source": tree_hash(source_dir), "calibration": tree_hash(cal_dir)}
    payload = json.loads(model_path.read_text(encoding="utf-8"))
    if payload.get("phase") != "E":
        raise SystemExit("ERROR: uq_model.json is not a Phase E model")

    records = read_jsonl(items_path)
    cal = _load_calibration(cal_dir)
    join = _attach_phase_f(records, cal)
    partitions = _partition(records, payload, load_pair_ids(ROOT / "data" / "lexuq_slice.jsonl"))

    holdout = [r for r in records if partitions[r["item_id"]] == "evaluation"]
    development = [r for r in records if partitions[r["item_id"]] == "development"]

    headline = build_matrix(holdout)
    headline["partition"] = "evaluation (frozen pair-grouped holdout, never refitted here)"
    headline["out_of_sample_for_every_method"] = True

    descriptive = build_matrix(records)
    descriptive["partition"] = "all items (development + evaluation)"
    descriptive["out_of_sample_for_every_method"] = False
    descriptive["caveat"] = (
        "the calibrated legal-aware method was fitted on the development partition, so "
        "its rows are in-sample here; use the evaluation-partition matrix for claims")
    descriptive["development_item_count"] = len(development)

    g7 = gate_g7(headline)

    after = {"source": tree_hash(source_dir), "calibration": tree_hash(cal_dir)}
    if before != after:
        raise SystemExit("ERROR: a source run changed while reading; refusing to report")

    report = {
        "phase": "G",
        "report": "evaluation matrix",
        "guide_sections": ["§12 (gate table, G7)", "§21.1", "§21.2", "§21.3"],
        "generated_by": "scripts/42_build_eval_matrix.py",
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "git_commit": _git_commit(),
        "source_run_id": args.run_id,
        "calibration_run_id": args.cal_run_id,
        "inputs": {
            "source_tree_sha256": before["source"],
            "calibration_tree_sha256": before["calibration"],
            "source_items_sha256": _sha256(items_path),
            "dataset_sha256": _sha256(ROOT / "data" / "lexuq_slice.jsonl"),
            "sources_unchanged_during_report": before == after,
        },
        "split": {"seed": payload["split"]["seed"],
                  "test_fraction": float(payload["split"]["test_fraction"]),
                  "n_evaluation": len(holdout), "n_development": len(development),
                  "verified_against_stored_split": True},
        "phase_f_join": join,
        "phase_f_calibration_coverage": _calibration_coverage(records),
        "methods_declared": [{"key": s.key, "guide_name": s.guide_name,
                              "implemented": s.implemented, "note": s.note}
                             for s in METHODS],
        "headline_matrix": headline,
        "descriptive_matrix_all_items": descriptive,
        "gate_g7": g7,
        "decision_layer": _action_census(records),
        "evaluation_arms": _arms(),
        "stage2_pending": {
            "deployment_measurements": "see scripts/43_measure_deployment.py (laptop only)",
            "generation": "no generation run was performed for this report",
        },
    }

    out = Path(args.out)
    if not out.is_absolute():
        out = ROOT / out
    if out.exists() and not args.force:
        raise SystemExit(f"ERROR: {out} exists (pass --force)")
    write_json(out, report)

    _print_table(headline, g7, report)
    print(f"\nreport written: {out}")
    print(f"sources unchanged: {before == after}")
    return 0


def _print_table(matrix: dict, g7: dict, report: dict) -> None:
    print("=" * 96)
    print("PHASE G — §21.2 EVALUATION MATRIX (headline: evaluation partition)")
    print("=" * 96)
    blocks = matrix["blocks"]
    slices = [s for s, b in blocks.items() if b.get("present")]
    print(f"  evaluation items: {report['split']['n_evaluation']}   "
          f"development items: {report['split']['n_development']}")
    width = 20
    header = f"  {'method':28s}" + "".join(f"{s + ' AUROC':>{width}s}" for s in slices)
    print(header)
    print("  " + "-" * (len(header) - 2))
    for key in matrix["method_order"]:
        row = f"  {key:28s}"
        for slice_name in slices:
            cell = blocks[slice_name]["cells"][key]
            value = cell["metrics"].get("auroc")
            if value is None:
                reason = cell["undefined"].get("auroc") or cell["undefined"].get("all") or "?"
                text = "undef:" + SHORT_REASONS.get(reason, reason)
            else:
                text = f"{value:.4f}"
            row += f"{text:>{width}s}"
        print(row)
    reasons_used = sorted({r for s in slices
                           for cell in blocks[s]["cells"].values()
                           for r in (cell["undefined"].values() or [])})
    if reasons_used:
        print("\n  reason codes: " + ", ".join(
            f"{SHORT_REASONS.get(r, r)} = {r}" for r in reasons_used))
    print()
    for slice_name in slices:
        coverage = blocks[slice_name]["judge_coverage"]
        counts = blocks[slice_name]["label_counts"]
        rate = coverage["item_coverage"]
        rate_text = "undefined" if rate is None else f"{rate:.4f}"
        print(f"  {slice_name}: n={blocks[slice_name]['n_items']} "
              f"correct={counts['correct']} incorrect={counts['incorrect']} "
              f"unresolved={counts['unresolved']} judge coverage={rate_text}")
    decision = report["decision_layer"]
    print(f"  decision layer (all items): {decision['counts']} "
          f"abstention rate={_fmt(decision['abstention_rate'])}")
    print()
    print(f"  G7: {g7['status']}")
    print(f"      {g7['reason']}")
    for name, block in g7["conditions"].items():
        print(f"      [{'met' if block['met'] else 'NOT met'}] {name}")


def _fmt(value) -> str:
    return "undefined" if value is None else f"{value:.4f}"


if __name__ == "__main__":
    raise SystemExit(main())
