#!/usr/bin/env python3
"""34 - follow-up experiment 4: topic-clustered uncertainty for the Phase F numbers.

Recomputes the Phase F point estimates and attaches topic-clustered and
item-level percentile bootstrap intervals, plus a paired interval for the
selective-risk gap between the calibrated map and the raw Phase E score. Reads
stored artefacts; fits only the small Phase F maps. Calls no model.

    python scripts/34_estimate_uncertainty.py

The topic is the sampling unit (items within a topic share legal facts and come
as matched L1/L7 pairs), so the clustered interval is the primary figure and the
item-level one is reported as the optimistic secondary.
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

from jurisuq.calibration.conformal import clopper_pearson_lower
from jurisuq.calibration.maps import map_from_dict, reliability_input
from jurisuq.calibration.metrics import ace, brier, log_loss, selective_risk
from jurisuq.calibration.uncertainty_intervals import (
    bootstrap_interval,
    paired_bootstrap_interval,
    summarize_gate_stability,
    wilson_interval,
)
from jurisuq.metrics import auroc
from jurisuq.uncertainty.io import read_jsonl, tree_hash, write_json
from jurisuq.uncertainty.split import load_pair_ids, split_name


def _paired(rows: list[dict], probabilities: dict[str, float]) -> tuple[list[float], list[int]]:
    p = [probabilities[r["item_id"]] for r in rows if r["item_id"] in probabilities]
    y = [int(r["majority_correct"]) for r in rows if r["item_id"] in probabilities]
    return p, y


def _metric_over(rows: list[dict], probabilities: dict[str, float], labels: dict[str, int],
                 fn) -> callable:
    """Wrap a metric so it reads resampled *positions* rather than raw lists."""
    def metric(positions):
        ps = [probabilities[rows[i]["item_id"]] for i in positions
              if rows[i]["item_id"] in probabilities]
        ys = [labels[rows[i]["item_id"]] for i in positions
              if rows[i]["item_id"] in probabilities]
        if len(ps) < 2 or len(set(ys)) < 2:
            return None
        return fn(ps, ys)
    return metric


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-id", default="phaseA-laptop-v2-rejudged+ctx-r2+typed+warrant+uq-exact")
    ap.add_argument("--cal-run-suffix", default="+cal-r2")
    ap.add_argument("--config", default=str(ROOT / "configs" / "phase_f_followup.json"))
    ap.add_argument("--out", default="runs/phaseF_exp4_uncertainty.json")
    ap.add_argument("--stratum", default="L1")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    if Path(args.run_id).name != args.run_id or "/" in args.run_id or "\\" in args.run_id:
        ap.error("--run-id must be a single run-directory name")
    cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
    unc = cfg["uncertainty"]
    reps = int(unc["bootstrap_reps"])
    seed = int(unc["bootstrap_seed"])
    confidence = float(unc["confidence"])

    source = ROOT / "runs" / args.run_id
    cal_dir = ROOT / "runs" / (args.run_id + args.cal_run_suffix)
    items_path = source / "items.jsonl"
    model_path = source / "uq_model.json"
    cal_model_path = cal_dir / "calibration_model.json"
    for required in (items_path, model_path, cal_model_path):
        if not required.is_file():
            raise SystemExit(f"ERROR: missing input: {required}")
    payload = json.loads(model_path.read_text(encoding="utf-8"))
    if payload.get("phase") != "E":
        raise SystemExit("ERROR: uq_model.json is not a Phase E model")
    stored = json.loads(cal_model_path.read_text(encoding="utf-8"))
    stratum_entry = (stored.get("strata") or {}).get(args.stratum) or {}
    if stratum_entry.get("status") != "fitted":
        raise SystemExit(f"ERROR: stratum {args.stratum} has no fitted map: "
                         f"{stratum_entry.get('status')}")
    mapping = map_from_dict(stratum_entry["map"])
    cross_fitted = stratum_entry.get("cross_fitted_p_reliable") or {}

    before = tree_hash(source)
    cal_before = tree_hash(cal_dir)
    records = read_jsonl(items_path)
    pair_ids = load_pair_ids(ROOT / "data" / "lexuq_slice.jsonl")
    test_fraction = float(cfg["split"]["test_fraction"])
    split_seed = payload["split"]["seed"]
    development_ids, holdout_ids = set(), set()
    for record in records:
        part = split_name(pair_ids[record["item_id"]], seed=split_seed,
                          test_fraction=test_fraction)
        (holdout_ids if part == "test" else development_ids).add(record["item_id"])
    if holdout_ids != set(payload["split"]["test_item_ids"]):
        raise SystemExit("ERROR: recomputed holdout does not match the stored split")

    rows = [r for r in records if r.get("slice") == args.stratum
            and r.get("majority_correct") in (0, 1)
            and isinstance(r.get("uq_uncertainty"), (int, float))
            and not isinstance(r.get("uq_uncertainty"), bool)]
    dev_rows = [r for r in rows if r["item_id"] in development_ids]
    hold_rows = [r for r in rows if r["item_id"] in holdout_ids]
    labels = {r["item_id"]: int(r["majority_correct"]) for r in rows}
    dev_groups = [str(r.get("topic")) for r in dev_rows]
    hold_groups = [str(r.get("topic")) for r in hold_rows]

    # Calibrated probabilities: development uses the stored cross-fitted values
    # (out-of-fold), holdout uses the frozen map - exactly as Phase F reports.
    dev_probs = {r["item_id"]: cross_fitted[r["item_id"]] for r in dev_rows
                 if r["item_id"] in cross_fitted}
    hold_probs = {r["item_id"]: mapping.predict(reliability_input(float(r["uq_uncertainty"])))
                  for r in hold_rows}
    # Two baselines: the uncalibrated Phase E score itself, and the sample-only
    # fallback score (u_prov), which is what an auditor would compare against.
    raw_probs = {r["item_id"]: reliability_input(float(r["uq_uncertainty"])) for r in rows}
    sample_only_probs = {
        r["item_id"]: 1.0 - float((r.get("uq_components") or {})["u_prov"])
        for r in rows if (r.get("uq_components") or {}).get("u_prov") is not None}

    intervals: dict[str, dict] = {}
    point: dict[str, float | None] = {}

    p_dev, y_dev = _paired(dev_rows, dev_probs)
    point["development_ace_5bin"] = ace(p_dev, y_dev, bins=5)
    point["development_brier"] = brier(p_dev, y_dev)
    point["development_log_loss"] = log_loss(p_dev, y_dev)
    for unit in ("cluster", "item"):
        intervals[f"development_ace_5bin_{unit}"] = bootstrap_interval(
            _metric_over(dev_rows, dev_probs, labels, lambda p, y: ace(p, y, bins=5)),
            dev_groups, reps=reps, seed=seed, unit=unit, confidence=confidence)
        intervals[f"development_brier_{unit}"] = bootstrap_interval(
            _metric_over(dev_rows, dev_probs, labels, brier),
            dev_groups, reps=reps, seed=seed + 1, unit=unit, confidence=confidence)

    p_hold, y_hold = _paired(hold_rows, hold_probs)
    point["holdout_ace_5bin"] = ace(p_hold, y_hold, bins=5)
    point["holdout_brier"] = brier(p_hold, y_hold)
    point["holdout_log_loss"] = log_loss(p_hold, y_hold)
    point["holdout_auroc_error_ranking"] = (
        float(auroc(list(hold_probs.values()),
                    [1 - labels[i] for i in hold_probs])) if len(set(y_hold)) > 1 else None)
    for unit in ("cluster", "item"):
        intervals[f"holdout_ace_5bin_{unit}"] = bootstrap_interval(
            _metric_over(hold_rows, hold_probs, labels, lambda p, y: ace(p, y, bins=5)),
            hold_groups, reps=reps, seed=seed + 2, unit=unit, confidence=confidence)
        intervals[f"holdout_brier_{unit}"] = bootstrap_interval(
            _metric_over(hold_rows, hold_probs, labels, brier),
            hold_groups, reps=reps, seed=seed + 4, unit=unit, confidence=confidence)

    # Selective-risk gaps at 50% coverage, paired on the same resampled topics:
    #   gap_to_scores = calibrated - raw Phase E score (1 - risk)
    #   gap_to_sample_only = calibrated - sample-only baseline (1 - u_prov)
    # A positive gap means the calibrated map admits riskier items at the same
    # coverage; both baselines are reported so neither comparison is implied.
    point["development_selective_risk_calibrated"] = selective_risk(p_dev, y_dev, 0.5)["risk"]
    for baseline_name, baseline in (("raw", raw_probs), ("sample_only", sample_only_probs)):
        dev_base = [baseline[r["item_id"]] for r in dev_rows if r["item_id"] in dev_probs]
        base_y = [labels[r["item_id"]] for r in dev_rows if r["item_id"] in dev_probs]
        point[f"development_selective_risk_{baseline_name}"] =             selective_risk(dev_base, base_y, 0.5)["risk"]
        gap = None
        if point["development_selective_risk_calibrated"] is not None and \
                point[f"development_selective_risk_{baseline_name}"] is not None:
            gap = (point["development_selective_risk_calibrated"]
                   - point[f"development_selective_risk_{baseline_name}"])
        point[f"development_selective_risk_gap_to_{baseline_name}"] = gap

        def gap_metric(positions, arm, baseline=baseline):
            ids = [dev_rows[i]["item_id"] for i in positions if dev_rows[i]["item_id"] in dev_probs]
            if len(ids) < 4 or len(set(labels[i] for i in ids)) < 2:
                return None
            if arm == 1 and any(i not in baseline for i in ids):
                return None
            ps = [dev_probs[i] for i in ids] if arm == 0 else [baseline[i] for i in ids]
            return selective_risk(ps, [labels[i] for i in ids], 0.5)["risk"]

        for unit in ("cluster", "item"):
            intervals[f"development_selective_risk_gap_to_{baseline_name}_{unit}"] = \
                paired_bootstrap_interval(gap_metric, dev_groups, reps=reps, seed=seed + 3,
                                          unit=unit, confidence=confidence)

    # Conformal coverage of the target, on the holdout partition.
    conformal = (json.loads((cal_dir / "calibration_report.json").read_text(encoding="utf-8"))
                 if (cal_dir / "calibration_report.json").is_file() else {})
    coverage_block = None
    per_stratum = conformal.get("per_stratum") or {}
    entry = per_stratum.get(args.stratum) if isinstance(per_stratum, dict) else None
    if entry:
        record = entry.get("conformal") or {}
        if record:
            n_cal = record.get("n_holdout")
            hits = record.get("covered")
            if isinstance(n_cal, int) and isinstance(hits, int):
                coverage_block = {
                    "n_calibration": record.get("n_calibration"),
                    "n_holdout": n_cal, "n_covered": hits,
                    "coverage": hits / n_cal,
                    "target": float(cfg["gates"]["conformal_target_coverage"]),
                    "wilson": wilson_interval(hits, n_cal, confidence=confidence),
                    "clopper_pearson_lower": clopper_pearson_lower(
                        hits, n_cal, alpha=1.0 - confidence),
                    "threshold": record.get("threshold"),
                    "wald_criterion_floor": record.get("wald_criterion_floor"),
                    "within_tolerance": record.get("within_tolerance"),
                    "exact_bound_reaches_target": record.get("exact_bound_reaches_target"),
                    "source": f"{cal_dir.name}/calibration_report.json",
                }
    if coverage_block is not None:
        point["conformal_coverage"] = coverage_block["coverage"]

    gates = cfg["gates"]
    # Gate stability: is the ACE verdict the same at every point of the interval?
    # Both partitions are checked because a verdict that holds on the development
    # cross-fit but not on the holdout is not the same claim.
    ace_max = float(gates["ace_max"])
    stability = {
        "development_ace_5bin (topic-clustered)":
            summarize_gate_stability(
                {"ace": intervals["development_ace_5bin_cluster"]}, {"ace": ace_max})["ace"],
        "development_ace_5bin (item-level)":
            summarize_gate_stability(
                {"ace": intervals["development_ace_5bin_item"]}, {"ace": ace_max})["ace"],
        "holdout_ace_5bin (topic-clustered)":
            summarize_gate_stability(
                {"ace": intervals["holdout_ace_5bin_cluster"]}, {"ace": ace_max})["ace"],
        "holdout_ace_5bin (item-level)":
            summarize_gate_stability(
                {"ace": intervals["holdout_ace_5bin_item"]}, {"ace": ace_max})["ace"],
    }

    after = tree_hash(source)
    cal_after = tree_hash(cal_dir)
    if (before, cal_before) != (after, cal_after):
        raise SystemExit("ERROR: a source run changed while estimating; refusing to report")

    report = {
        "experiment": "E5d",
        "question": ("are the Phase F point estimates resolvable at this sample size once "
                     "topic-level dependence is respected?"),
        "stratum": args.stratum,
        "source_run_id": args.run_id,
        "calibration_run_id": cal_dir.name,
        "source_tree_sha256": before,
        "calibration_tree_sha256": cal_before,
        "n_development": len(dev_rows),
        "n_holdout": len(hold_rows),
        "n_development_topics": len(set(dev_groups)),
        "n_holdout_topics": len(set(hold_groups)),
        "bootstrap": {"reps": reps, "seed": seed, "confidence": confidence,
                      "primary_unit": unc["primary_unit"],
                      "secondary_unit": unc["secondary_unit"]},
        "point_estimates": point,
        "intervals": intervals,
        "gate_stability_at_ace_max": stability,
        "conformal_coverage": coverage_block,
        "split": {"seed": split_seed, "test_fraction": test_fraction,
                  "source": "stored in the Phase E model and verified against the slice"},
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "inputs": {"items_sha256": hashlib.sha256(items_path.read_bytes()).hexdigest(),
                   "calibration_model_sha256":
                       hashlib.sha256(cal_model_path.read_bytes()).hexdigest()},
        "git_commit": _git_commit(),
    }

    out = Path(args.out)
    if not out.is_absolute():
        out = ROOT / out
    if out.exists() and not args.force:
        raise SystemExit(f"ERROR: {out} exists (pass --force)")
    write_json(out, report)

    print(f"experiment 4 report written: {out}")
    print(f"  stratum {args.stratum}: dev n={len(dev_rows)} ({len(set(dev_groups))} topics), "
          f"hold n={len(hold_rows)} ({len(set(hold_groups))} topics)")
    for name in ("development_ace_5bin", "holdout_ace_5bin", "development_brier",
                 "holdout_brier", "development_selective_risk_gap_to_raw",
                 "development_selective_risk_gap_to_sample_only"):
        if point.get(name) is None:
            continue
        print(f"  {name:38s} point={point[name]:.4f}")
        for unit in ("cluster", "item"):
            block = intervals.get(f"{name}_{unit}")
            if not block:
                continue
            lo, hi = block["estimate_interval"]
            print(f"      {block['unit']:13s} 95% [{lo:+.4f}, {hi:+.4f}]")
    if coverage_block:
        w = coverage_block["wilson"]
        print(f"  conformal coverage {coverage_block['n_covered']}/"
              f"{coverage_block['n_holdout']} = {coverage_block['coverage']:.4f} "
              f"(target {coverage_block['target']}) Wilson [{w['lo']:.4f}, {w['hi']:.4f}], "
              f"CP lower {coverage_block['clopper_pearson_lower']:.4f}")
    print(f"  gate ace_max={ace_max}: "
          f"{sorted({block['status'] for block in stability.values()})}"
          f" across partitions and sampling units")
    print(f"  sources unchanged: {before == after and cal_before == cal_after}")
    return 0


def _git_commit() -> str | None:
    import subprocess
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                              text=True, timeout=10).stdout.strip() or None
    except Exception:
        return None


if __name__ == "__main__":
    raise SystemExit(main())
