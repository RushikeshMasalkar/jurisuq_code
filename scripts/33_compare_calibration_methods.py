#!/usr/bin/env python3
"""33 - follow-up experiment 3: compare calibration maps and apply the frozen rule.

Fits every candidate map on the Phase E development partition, applies the
pre-registered small-sample rule from ``configs/phase_f_followup.json``, and
reports development (cross-fitted) and holdout metrics for every candidate.
Reads stored artefacts; trains nothing large and calls no model.

    python scripts/33_compare_calibration_methods.py

The chosen map is whatever the rule names. The holdout columns are printed so
nothing is hidden, but they never select the shipped method.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from jurisuq.calibration.method_selection import compare_per_stratum
from jurisuq.uncertainty.io import read_jsonl, tree_hash, write_json
from jurisuq.uncertainty.split import load_pair_ids, split_name


def _risk(record: dict) -> float | None:
    value = record.get("uq_uncertainty")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-id", default="phaseA-laptop-v2-rejudged+ctx-r2+typed+warrant+uq-exact")
    ap.add_argument("--config", default=str(ROOT / "configs" / "phase_f_followup.json"))
    ap.add_argument("--out", default="runs/phaseF_exp3_calibration_methods.json")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    if Path(args.run_id).name != args.run_id or "/" in args.run_id or "\\" in args.run_id:
        ap.error("--run-id must be a single run-directory name")
    cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
    rule = dict(cfg["preregistered_small_sample_rule"])
    folds = int(cfg.get("folds", 5))
    split_seed = cfg.get("split", {}).get("seed", "phaseE-v1")
    test_fraction = float(cfg.get("split", {}).get("test_fraction", 0.2))

    source = ROOT / "runs" / args.run_id
    items_path = source / "items.jsonl"
    model_path = source / "uq_model.json"
    for required in (items_path, model_path):
        if not required.is_file():
            raise SystemExit(f"ERROR: missing input: {required}")
    payload = json.loads(model_path.read_text(encoding="utf-8"))
    if payload.get("phase") != "E":
        raise SystemExit("ERROR: uq_model.json is not a Phase E model")

    shipped = {}
    shipped_sensitivity = {}
    shipped_model_path = ROOT / "runs" / (args.run_id + "+cal-r2") / "calibration_model.json"
    if shipped_model_path.is_file():
        shipped = json.loads(shipped_model_path.read_text(encoding="utf-8"))
        shipped_sensitivity = {
            stratum: (entry or {}).get("descriptive_method_sensitivity")
            for stratum, entry in (shipped.get("strata") or {}).items()}

    before = tree_hash(source)
    records = read_jsonl(items_path)
    pair_ids = load_pair_ids(ROOT / "data" / "lexuq_slice.jsonl")
    stored_test = set(payload["split"]["test_item_ids"])
    development_ids, holdout_ids = set(), set()
    for record in records:
        part = split_name(pair_ids[record["item_id"]], seed=split_seed,
                          test_fraction=test_fraction)
        (holdout_ids if part == "test" else development_ids).add(record["item_id"])
    if holdout_ids != stored_test:
        raise SystemExit("ERROR: recomputed holdout does not match the stored split")

    skipped = []
    for record in records:
        if record.get("majority_correct") not in (0, 1) or isinstance(record.get("majority_correct"), bool):
            skipped.append({"item_id": record.get("item_id"),
                            "reason": "majority_correct is not binary"})
        elif _risk(record) is None:
            skipped.append({"item_id": record.get("item_id"),
                            "reason": "uq_uncertainty missing"})

    report = compare_per_stratum(
        records, development_ids, holdout_ids, rule=rule, folds=folds,
        seed=split_seed)  # same fold seeds as the shipped Phase F report

    after = tree_hash(source)
    if before != after:
        raise SystemExit("ERROR: source run changed while comparing; refusing to report")

    report.update({
        "run_id": "phaseF_exp3_calibration_methods",
        "source_run_id": args.run_id,
        "shipped_calibration_run_id": (args.run_id + "+cal-r2"
                                       if shipped_model_path.is_file() else None),
        "source_tree_sha256": before,
        "source_unchanged": before == after,
        "split": {"seed": split_seed, "test_fraction": test_fraction,
                  "n_development": len(development_ids), "n_holdout": len(holdout_ids),
                  "source": "stored in the Phase E model and verified against the slice"},
        "risk_score_field": "uq_uncertainty (Phase E, uncalibrated_monotone_risk_score)",
        "shipped_method_rule": {
            "rule": ("isotonic when the stratum has >= 40 development records with both "
                     "classes, otherwise platt"),
            "isotonic_min_n": shipped.get("isotonic_min_n"),
            "source": "calibration_model.json of the +cal-r2 run",
            "uses_reliability_range": False,
            "note": ("the shipped rule looks only at sample size, so L1 (n=78) is always "
                     "isotonic; the follow-up rule adds the input-range condition"),
        },
        "shipped_descriptive_sensitivity": shipped_sensitivity,
        "skipped_items": skipped,
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "inputs": {"items_sha256": hashlib.sha256(items_path.read_bytes()).hexdigest(),
                   "model_sha256": hashlib.sha256(model_path.read_bytes()).hexdigest()},
        "git_commit": _git_commit(),
    })

    out = Path(args.out)
    if not out.is_absolute():
        out = ROOT / out
    if out.exists() and not args.force:
        raise SystemExit(f"ERROR: {out} exists (pass --force)")
    write_json(out, report)

    print(f"experiment 3 report written: {out}")
    if skipped:
        print(f"  skipped {len(skipped)} item(s): {skipped}")
    for stratum, block in list(report["strata"].items()) + [
            ("pooled (reference only)", report["combined_pooled"])]:
        if block is None or "error" in block:
            print(f"\n{stratum}: not evaluable ({block.get('error') if block else 'no data'})")
            continue
        rule_block = block["rule"]
        print(f"\n{stratum}: dev n={block['n_development']} hold n={block['n_holdout']} "
              f"range={rule_block['reliability_range']:.4f} "
              f"-> rule chooses {block['chosen_by_rule']}")
        print(f"  {'method':16s} {'dev cf ACE':>11s} {'hold ACE':>9s} {'hold ECE':>9s}"
              f" {'hold Brier':>10s} {'hold logloss':>12s} {'sat@1':>6s}")
        for method, cand in block["candidates"].items():
            cf = block["development_cross_fitted"].get(method, {})
            cf_ace = cf.get("ace_5bin") if isinstance(cf, dict) else None
            print(f"  {method:16s} {_fmt(cf_ace):>11s} {_fmt(cand['holdout']['ace_5bin']):>9s}"
                  f" {_fmt(cand['holdout']['ece_10bin']):>9s} {_fmt(cand['holdout']['brier']):>10s}"
                  f" {_fmt(cand['holdout']['log_loss']):>12s} {cand['holdout_saturated_at_one']:>6d}")
        print(f"  best holdout ACE: {block['holdout_ace_ranking_best_first'][:1]} "
              f"(reported, not selected)")
    print(f"  source run unchanged: {before == after}")
    return 0


def _fmt(value) -> str:
    return "undefined" if value is None else f"{value:.4f}"


def _git_commit() -> str | None:
    import subprocess
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                              text=True, timeout=10).stdout.strip() or None
    except Exception:
        return None


if __name__ == "__main__":
    raise SystemExit(main())
