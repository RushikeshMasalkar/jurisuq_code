#!/usr/bin/env python3
"""27 - held-out Phase E validation, sample-only comparison, and ablations.

Correctness labels are read only in this offline evaluation script. The test
set is grouped by the existing matched pair_id, and the model is not refitted.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from jurisuq.metrics import auroc
from jurisuq.uncertainty.estimator import MonotoneLogistic, score_features
from jurisuq.uncertainty.io import read_jsonl, tree_hash, write_json
from jurisuq.uncertainty.split import load_pair_ids, split_name


def safe_metric(values, labels):
    value = auroc(values, labels) if values and len(values) == len(labels) else float("nan")
    return None if not math.isfinite(value) else value


def bootstrap_delta(rows, seed=0, n_boot=2000):
    """Paired item bootstrap of AUROC(model)-AUROC(provision entropy)."""
    rows = [r for r in rows
            if isinstance(r.get("uq_uncertainty"), (int, float))
            and not isinstance(r.get("uq_uncertainty"), bool)
            and math.isfinite(float(r["uq_uncertainty"]))
            and isinstance((r.get("uq_components") or {}).get("u_prov"), (int, float))
            and r.get("majority_correct") in (0, 1)]
    if not rows:
        return {"point": None, "lo": None, "hi": None, "valid_replicates": 0}
    y = [int(r["majority_correct"]) for r in rows]
    model = [float(r["uq_uncertainty"]) for r in rows]
    baseline = [float(r["uq_components"]["u_prov"]) for r in rows]
    point_m, point_b = safe_metric(model, y), safe_metric(baseline, y)
    if point_m is None or point_b is None:
        return {"point": None, "lo": None, "hi": None, "valid_replicates": 0}
    point = point_m - point_b
    rng = random.Random(seed)
    diffs = []
    n = len(rows)
    for _ in range(n_boot):
        idx = [rng.randrange(n) for _ in range(n)]
        ys = [y[i] for i in idx]
        if len(set(ys)) < 2:
            continue
        diffs.append(auroc([model[i] for i in idx], ys)
                     - auroc([baseline[i] for i in idx], ys))
    diffs.sort()
    if not diffs:
        lo = hi = None
    else:
        lo = diffs[int(0.025 * (len(diffs) - 1))]
        hi = diffs[int(0.975 * (len(diffs) - 1))]
    return {"point": point, "lo": lo, "hi": hi, "valid_replicates": len(diffs),
            "n_boot": n_boot, "seed": seed}


def metric_block(rows, score_key):
    usable = [r for r in rows if isinstance(r.get(score_key), (int, float))
              and not isinstance(r.get(score_key), bool)
              and math.isfinite(float(r[score_key]))
              and r.get("majority_correct") in (0, 1)]
    labels = [int(r["majority_correct"]) for r in usable]
    scores = [float(r[score_key]) for r in usable]
    return {"n": len(usable), "correct": sum(labels), "incorrect": len(labels)-sum(labels),
            "auroc": safe_metric(scores, labels)}


def training_limit_statement(model):
    training_n = model.get("legal_head_training_n")
    if isinstance(training_n, int) and not isinstance(training_n, bool) and training_n >= 0:
        return (
            f"The legal-aware head is trained on {training_n} legal-complete "
            "development records in this run; all scores are uncalibrated."
        )
    return (
        "The legal-aware head training count is unavailable in model metadata; "
        "all scores are uncalibrated."
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-id", default="phaseA-laptop-v2-rejudged+ctx+warrant+uq",
                    help="Phase E output run id under runs/")
    ap.add_argument("--bootstrap-samples", type=int, default=2000)
    ap.add_argument("--bootstrap-seed", type=int, default=0)
    args = ap.parse_args()
    if (Path(args.run_id).name != args.run_id or "/" in args.run_id
            or "\\" in args.run_id or args.run_id in {"", ".", ".."}):
        ap.error("--run-id must be a single run-directory name")
    if args.bootstrap_samples < 1:
        ap.error("--bootstrap-samples must be positive")
    out = ROOT / "runs" / args.run_id
    items_path = out / "items.jsonl"
    model_path = out / "uq_model.json"
    dataset = ROOT / "data" / "lexuq_slice.jsonl"
    if not items_path.is_file() or not model_path.is_file():
        raise SystemExit(f"ERROR: Phase E output missing items.jsonl or uq_model.json in {out}")
    before = tree_hash(out)
    records = read_jsonl(items_path)
    model = json.loads(model_path.read_text(encoding="utf-8"))
    pair_ids = load_pair_ids(dataset)
    seed = model["split"]["seed"]
    test_fraction = float(model["split"]["test_fraction"])

    test_rows = []
    for record in records:
        item_id = record.get("item_id")
        if item_id not in pair_ids:
            raise SystemExit(f"ERROR: no pair_id for {item_id!r}")
        if split_name(pair_ids[item_id], seed=seed, test_fraction=test_fraction) != "test":
            continue
        label = record.get("majority_correct")
        if isinstance(label, bool) or label not in (0, 1):
            continue
        test_rows.append(record)
    if not test_rows:
        raise SystemExit("ERROR: the grouped holdout contains no labeled records")

    by_slice = {}
    for slice_name in sorted({r.get("slice") for r in test_rows}):
        rows = [r for r in test_rows if r.get("slice") == slice_name]
        by_slice[slice_name] = {
            "n": len(rows),
            "correct": sum(int(r["majority_correct"]) for r in rows),
            "incorrect": sum(1-int(r["majority_correct"]) for r in rows),
            "uq_auroc": metric_block(rows, "uq_uncertainty"),
            "sample_only_provision_entropy_auroc": metric_block(
                [{**r, "u_prov_score": (r.get("uq_components") or {}).get("u_prov")} for r in rows],
                "u_prov_score"),
        }
        if slice_name == "L1":
            control = rows
    if "control" not in locals():
        control = []

    delta = bootstrap_delta(control, seed=args.bootstrap_seed,
                            n_boot=args.bootstrap_samples)
    control_uq = metric_block(control, "uq_uncertainty")
    control_baseline = metric_block(
        [{**r, "u_prov_score": (r.get("uq_components") or {}).get("u_prov")} for r in control],
        "u_prov_score")
    legal_test = [r for r in test_rows if r.get("uq_score_mode") == "legal_aware"]
    ablations = {}
    legal_head_obj = model.get("legal_head")
    if legal_head_obj is not None and legal_test:
        legal_head = MonotoneLogistic.from_dict(legal_head_obj)
        full_scores = [float(r["uq_uncertainty"]) for r in legal_test]
        labels_legal = [int(r["majority_correct"]) for r in legal_test]
        full_auc = safe_metric(full_scores, labels_legal)
        for component in ("u_prov", "u_text", "u_warrant", "u_cm", "u_contra"):
            ablated_scores = [score_features(legal_head, r["uq_components"],
                                             drop_components=(component,))
                              for r in legal_test]
            ablated_auc = safe_metric(ablated_scores, labels_legal)
            ablations[component] = {
                "method": "zero that component's fitted coefficients and all interactions containing it; no refit",
                "n_legal_aware_test": len(legal_test),
                "full_auroc": full_auc,
                "ablated_auroc": ablated_auc,
                "auroc_drop": (full_auc - ablated_auc)
                    if full_auc is not None and ablated_auc is not None else None,
                "interpretation": "descriptive only; small holdout; Phase H should use confirmatory refits",
            }
    else:
        for component in ("u_prov", "u_text", "u_warrant", "u_cm", "u_contra"):
            ablations[component] = {"n_legal_aware_test": len(legal_test),
                                    "auroc_drop": None,
                                    "status": "not evaluable: no fitted legal head or no legal-aware holdout rows"}

    target = [r for r in test_rows if r.get("slice") == "L7"]
    target_labels = {int(r["majority_correct"]) for r in target}
    target_classes_defined = target_labels == {0, 1}
    # The source E5 gate explicitly requires a target-slice population with both
    # correctness classes before any target-slice AUROC claim.
    if not target_classes_defined:
        gate_status = "NOT_EVALUABLE"
        gate_reason = "held-out L7 target slice lacks both correctness classes; target AUROC undefined"
    elif control_uq["auroc"] is None or control_baseline["auroc"] is None or delta["lo"] is None:
        gate_status = "NOT_EVALUABLE"
        gate_reason = "control-slice AUROC or paired improvement interval is undefined"
    elif control_uq["auroc"] > 0.766 and delta["lo"] > 0.0:
        gate_status = "PASS"
        gate_reason = "control AUROC exceeds 0.766 and paired CI for improvement excludes zero"
    else:
        gate_status = "FAIL"
        gate_reason = "held-out control-slice improvement criterion was not met"

    result = {
        "phase": "E", "experiment": "E5", "gate": "G5",
        "source_run_id": model.get("source_run_id"), "output_run_id": args.run_id,
        "split": {"kind": "pair-grouped SHA-256 holdout", "seed": seed,
                  "test_fraction": test_fraction, "n_test": len(test_rows),
                  "test_item_ids": [r["item_id"] for r in test_rows]},
        "evaluation_label_field": "majority_correct",
        "labels_used_only_for_offline_evaluation": True,
        "holdout_metrics_by_slice": by_slice,
        "control_slice": "L1",
        "strongest_phase_a_baseline": "normalized provision-level entropy (methods.prov_se)",
        "control_auroc": control_uq["auroc"],
        "control_baseline_auroc": control_baseline["auroc"],
        "control_auroc_difference_bootstrap_ci": delta,
        "target_slice": "L7",
        "target_slice_both_classes_present": target_classes_defined,
        "target_slice_auroc": metric_block(target, "uq_uncertainty")["auroc"],
        "legal_aware_only_test_population": metric_block(legal_test, "uq_uncertainty"),
        "ablation_status": ablations,
        "gate_status": gate_status,
        "gate_reason": gate_reason,
        "limitations": [
            "Only the deterministic 20% pair-grouped holdout is evaluated; this 200-item synthetic slice is small.",
            "The L7 run-of-record has no correct majority answers, so L7 AUROC is undefined.",
            "The shipped Phase D records use exact_key representation; Phase B typed-cluster entropy is not present. u_prov uses Phase A provision entropy.",
            training_limit_statement(model),
            "Fallback rows use normalized provision entropy; they are explicitly marked and are not interpreted as model probabilities.",
            "Component-removal refits are not performed in this pilot; Phase H owns confirmatory ablation testing."
        ],
    }
    after = tree_hash(out)
    result["output_tree_hash_before"] = before
    result["output_tree_hash_after_validation"] = after
    result["output_unchanged_by_validation"] = before == after
    write_json(out / "uq_validation.json", result)
    print(f"E5 holdout: {len(test_rows)} records; by slice: "
          + ", ".join(f"{s}={v['n']} (correct={v['correct']}, incorrect={v['incorrect']})"
                       for s, v in by_slice.items()))
    print(f"L1/control AUROC: {control_uq['auroc']} vs provision-entropy baseline {control_baseline['auroc']}")
    print(f"paired AUROC delta 95% CI: {delta['lo']} to {delta['hi']}")
    print(f"L7/target both classes: {target_classes_defined}; GATE G5: {gate_status} ({gate_reason})")
    print(f"wrote {out / 'uq_validation.json'}; validation left scored items unchanged: {before == after}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
