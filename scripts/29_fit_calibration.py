#!/usr/bin/env python3
"""29 - fit Phase F calibration maps on the development partition only (M9).

Correctness labels are read here and nowhere else in the Phase F pipeline. The
split is the Phase E split (pair-grouped SHA-256 holdout), recomputed from the
frozen slice, so the holdout used for calibration is the same holdout Phase E
never trained on.

Output is a JSON model file holding, per stratum, the fitted map, the grouped
cross-fitted development metrics and the fold assignment. Isotonic regression is
the default; Platt scaling is used when the stratum is smaller than
``--isotonic-min-n``; a stratum with one correctness class is recorded as
uncalibratable and is never imputed.
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

from jurisuq.calibration.evaluate import fit_strata
from jurisuq.calibration.policy import DecisionPolicy
from jurisuq.uncertainty.io import read_jsonl, tree_hash, write_json
from jurisuq.uncertainty.split import load_pair_ids, split_name


def load_config(path: Path) -> dict:
    if not path.is_file():
        raise SystemExit(f"ERROR: no config: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default=str(ROOT / "configs" / "phase_f_calibration.json"))
    ap.add_argument("--run-id", default=None, help="input Phase E run id under runs/")
    ap.add_argument("--model-out", default=None,
                    help="model JSON path, relative to repository root unless absolute")
    ap.add_argument("--score-field", default=None)
    ap.add_argument("--split-seed", default=None)
    ap.add_argument("--test-fraction", type=float, default=None)
    ap.add_argument("--isotonic-min-n", type=int, default=None)
    ap.add_argument("--min-fit-n", type=int, default=None)
    ap.add_argument("--folds", type=int, default=None)
    args = ap.parse_args()

    cfg = load_config(Path(args.config))
    run_id = args.run_id or cfg["source_run_id"]
    model_out = args.model_out or cfg["model_out"]
    score_field = args.score_field or cfg.get("score_field", "uq_uncertainty")
    split_seed = args.split_seed or cfg.get("split_seed", "phaseE-v1")
    test_fraction = (args.test_fraction if args.test_fraction is not None
                     else float(cfg.get("test_fraction", 0.20)))
    isotonic_min_n = (args.isotonic_min_n if args.isotonic_min_n is not None
                      else int(cfg.get("isotonic_min_n", 40)))
    min_fit_n = (args.min_fit_n if args.min_fit_n is not None
                 else int(cfg.get("min_fit_n", 10)))
    folds = args.folds if args.folds is not None else int(cfg.get("folds", 5))
    if not 0.0 < test_fraction < 1.0:
        ap.error("--test-fraction must be between 0 and 1")
    if folds < 2:
        ap.error("--folds must be at least 2")
    if Path(run_id).name != run_id or "/" in run_id or "\\" in run_id or run_id in {"", ".", ".."}:
        ap.error("--run-id must be a single run-directory name")

    source = ROOT / "runs" / run_id
    items_path = source / "items.jsonl"
    dataset = ROOT / "data" / "lexuq_slice.jsonl"
    statute_path = ROOT / "data" / "statutes" / "statutes_v1.jsonl"
    links_path = ROOT / "data" / "relations" / "crosswalk_v1.jsonl"
    for required in (items_path, dataset, statute_path, links_path):
        if not required.is_file():
            raise SystemExit(f"ERROR: missing input: {required}")

    before = tree_hash(source)
    records = read_jsonl(items_path)
    pair_ids = load_pair_ids(dataset)
    development_ids, holdout_ids = set(), set()
    for record in records:
        item_id = record.get("item_id")
        if item_id not in pair_ids:
            raise SystemExit(f"ERROR: {item_id!r} has no pair_id in {dataset}")
        part = split_name(pair_ids[item_id], seed=split_seed, test_fraction=test_fraction)
        (holdout_ids if part == "test" else development_ids).add(item_id)

    for stratum in {r.get("slice") for r in records}:
        if not any(r.get("slice") == stratum and r["item_id"] in holdout_ids for r in records):
            raise SystemExit(f"ERROR: stratum {stratum!r} has no holdout items")

    fitted = fit_strata(records, development_ids, score_field=score_field,
                        isotonic_min_n=isotonic_min_n, min_fit_n=min_fit_n,
                        seed=split_seed, k=folds)
    policy = DecisionPolicy.from_dict(cfg.get("policy", {}))
    after = tree_hash(source)
    if before != after:
        raise SystemExit("ERROR: source run changed while fitting; refusing to trust the maps")

    payload = {
        "schema_version": 1,
        "phase": "F",
        "modules": ["M9", "M10"],
        "source_run_id": run_id,
        "source_tree_sha256": before,
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "score_field": score_field,
        "label_field": "majority_correct",
        "label_use": "read here to fit the maps; never read by the scoring path",
        "split": {"kind": "pair-grouped SHA-256 holdout (identical to Phase E)",
                  "seed": split_seed, "test_fraction": test_fraction,
                  "n_development": len(development_ids), "n_holdout": len(holdout_ids),
                  "holdout_item_ids": sorted(holdout_ids)},
        "method_rule": (f"isotonic when the stratum has >= {isotonic_min_n} development "
                        f"records with both classes, otherwise platt; a single-class or "
                        f"too-small stratum is recorded as uncalibratable"),
        "isotonic_min_n": isotonic_min_n,
        "min_fit_n": min_fit_n,
        "folds": folds,
        "strata": fitted["strata"],
        "policy": policy.to_dict(),
        "harm_rule": cfg.get("harm_rule", "max"),
        "conformal_target_coverage": float(cfg.get("conformal_target_coverage", 0.80)),
        "gate": {"ace_max": float(cfg.get("gates", {}).get("ace_max", 0.05)),
                 "selective_coverage": float(cfg.get("gates", {}).get("selective_coverage", 0.5)),
                 "coverage_tolerance": "1.96*sqrt(target*(1-target)/n)"},
        "dataset_sha256": hashlib.sha256(dataset.read_bytes()).hexdigest(),
        "statutes_sha256": hashlib.sha256(statute_path.read_bytes()).hexdigest(),
        "links_sha256": hashlib.sha256(links_path.read_bytes()).hexdigest(),
        "config_path": str(Path(args.config)),
    }
    model_path = Path(model_out)
    if not model_path.is_absolute():
        model_path = ROOT / model_path
    if source.resolve() in model_path.resolve().parents:
        raise SystemExit("ERROR: model output must not be inside the frozen source run")
    write_json(model_path, payload)

    print(f"Phase F calibration model written: {model_path}")
    print(f"source: {run_id}  (development {len(development_ids)}, holdout {len(holdout_ids)})")
    for stratum, entry in sorted(fitted["strata"].items()):
        metrics = entry.get("development_metrics") or {}
        ace_value = metrics.get("ace_5bin_cross_fitted")
        ace_text = "undefined" if ace_value is None else f"{ace_value:.4f}"
        print(f"  {stratum}: {entry['status']:<34} method={entry.get('method')!s:<9} "
              f"n={entry['n_scored']:<4} cross-fit ACE(5)={ace_text}")
    print(f"decision policy: verify_cost={policy.verify_cost} abstain_cost={policy.abstain_cost}")
    print(f"source tree SHA-256 unchanged: {before == after} ({before[:24]})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
