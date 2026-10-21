#!/usr/bin/env python3
"""25 - fit the Phase E monotone estimator on development groups only.

Correctness labels are read here solely to fit the supervised legal-aware
head. The inference CLI (26) is a separate path and does not read labels.
No model/API calls or third-party ML packages are required.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from jurisuq.uncertainty.estimator import fit_monotone_logistic
from jurisuq.uncertainty.features import extract_features
from jurisuq.uncertainty.io import read_jsonl, tree_hash, write_json
from jurisuq.uncertainty.split import load_pair_ids, split_name


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-id", default="phaseA-laptop-v2-rejudged+ctx+warrant",
                    help="input Phase D run id under runs/")
    ap.add_argument("--model-out", default="runs/phaseE_model.json",
                    help="model JSON path, relative to repository root unless absolute")
    ap.add_argument("--split-seed", default="phaseE-v1")
    ap.add_argument("--test-fraction", type=float, default=0.20)
    args = ap.parse_args()
    if not 0.0 < args.test_fraction < 1.0:
        ap.error("--test-fraction must be between 0 and 1")
    if (Path(args.run_id).name != args.run_id or "/" in args.run_id
            or "\\" in args.run_id or args.run_id in {"", ".", ".."}):
        ap.error("--run-id must be a single run-directory name")

    source = ROOT / "runs" / args.run_id
    items_path = source / "items.jsonl"
    dataset = ROOT / "data" / "lexuq_slice.jsonl"
    if not items_path.is_file():
        raise SystemExit(f"ERROR: no input run: {items_path}")
    if not dataset.is_file():
        raise SystemExit(f"ERROR: missing pair map: {dataset}")
    before = tree_hash(source)
    records = read_jsonl(items_path)
    pair_ids = load_pair_ids(dataset)

    train_records, train_labels = [], []
    training_ids, test_ids = [], []
    unsupported_ids = []
    for record in records:
        item_id = record.get("item_id")
        if item_id not in pair_ids:
            raise SystemExit(f"ERROR: {item_id!r} has no pair_id in data/lexuq_slice.jsonl")
        part = split_name(pair_ids[item_id], seed=args.split_seed,
                          test_fraction=args.test_fraction)
        if part == "test":
            test_ids.append(item_id)
            continue
        feat = extract_features(record)
        if not feat["legal_complete"]:
            unsupported_ids.append(item_id)
            continue
        label = record.get("majority_correct")
        if isinstance(label, bool) or label not in (0, 1):
            raise SystemExit(f"ERROR: training item {item_id} lacks binary majority_correct")
        train_records.append(feat["components"])
        # Higher Phase E score means greater uncertainty / higher error risk.
        train_labels.append(1 - int(label))
        training_ids.append(item_id)

    model_obj = None
    fit_note = ""
    if len(set(train_labels)) >= 2 and len(train_labels) >= 10:
        model_obj = fit_monotone_logistic(train_records, train_labels)
        fit_note = "trained on legal-complete development records only"
    else:
        fit_note = (
            "no legal-aware head fitted: fewer than 10 legal-complete development records "
            "or fewer than two correctness classes; estimator will use sample-only fallback"
        )

    after = tree_hash(source)
    if before != after:
        raise SystemExit("ERROR: input run changed while fitting; refusing to trust model")
    payload = {
        "schema_version": 1,
        "phase": "E",
        "module": "M8",
        "source_run_id": args.run_id,
        "source_tree_sha256": before,
        "split": {"kind": "sha256 pair-grouped holdout",
                  "seed": args.split_seed,
                  "test_fraction": args.test_fraction,
                  "development_item_count": len(records) - len(test_ids),
                  "test_item_count": len(test_ids),
                  "training_pair_grouped_item_ids": training_ids,
                  "test_item_ids": test_ids,
                  "unsupported_development_item_ids": unsupported_ids},
        "label_field_used_only_for_fit": "majority_correct (recoded as error=1-correct)",
        "training_target": "majority answer incorrect (1); correct (0)",
        "legal_head": model_obj.to_dict() if model_obj else None,
        "legal_head_training_n": len(train_labels),
        "legal_head_training_errors": sum(train_labels),
        "legal_head_training_correct": len(train_labels) - sum(train_labels),
        "fit_note": fit_note,
        "feature_spec": ["u_prov", "u_text", "u_warrant", "u_cm", "u_contra",
                         "all pairwise interactions; all coefficients constrained >= 0"],
        "fallback": "normalized sample-only provision entropy u_prov; null is not zero",
        "calibration_status": "uncalibrated ranking/risk score; Phase F owns calibration",
    }
    model_path = Path(args.model_out)
    if not model_path.is_absolute():
        model_path = ROOT / model_path
    if source.resolve() in model_path.resolve().parents:
        raise SystemExit("ERROR: model output must not be inside the frozen source run")
    write_json(model_path, payload)
    print(f"Phase E model written: {model_path}")
    print(f"development records: {len(records) - len(test_ids)}; holdout records: {len(test_ids)}")
    print(f"legal-complete development rows fitted: {len(train_labels)} "
          f"(incorrect={sum(train_labels)}, correct={len(train_labels)-sum(train_labels)})")
    print(f"legal-aware head: {'trained' if model_obj else 'unavailable; sample-only fallback'}")
    print(f"source tree SHA-256 unchanged: {before == after} ({before[:24]})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
