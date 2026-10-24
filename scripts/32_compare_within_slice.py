#!/usr/bin/env python3
"""32 - follow-up experiment 2: pooled vs within-slice Phase E fitting.

Compares the shipped pooled Phase E model against the same estimator fitted on
one slice's development records only, on identical holdout items. Reads stored
artefacts; trains nothing large and calls no model.

    python scripts/32_compare_within_slice.py \
        --run-id phaseA-laptop-v2-rejudged+ctx-r2+typed+warrant+uq-exact
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

from jurisuq.calibration.within_slice import compare_within_slice
from jurisuq.uncertainty.io import read_jsonl, tree_hash, write_json
from jurisuq.uncertainty.split import load_pair_ids, split_name


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-id", default="phaseA-laptop-v2-rejudged+ctx-r2+typed+warrant+uq-exact",
                    help="Phase E run whose stored model and split define the comparison")
    ap.add_argument("--config", default=str(ROOT / "configs" / "phase_f_followup.json"))
    ap.add_argument("--out", default="runs/phaseF_exp2_within_slice.json")
    ap.add_argument("--slice", default="L1")
    ap.add_argument("--provision-variant", default="exact")
    ap.add_argument("--method", default=None, help="calibration map for the downstream arm")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    if Path(args.run_id).name != args.run_id or "/" in args.run_id or "\\" in args.run_id:
        ap.error("--run-id must be a single run-directory name")
    cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
    method = args.method or cfg.get("calibration_method_for_downstream", "isotonic")
    seed = cfg.get("split", {}).get("seed", "phaseE-v1") + "|exp2"
    k = int(cfg.get("folds", 5))

    source = ROOT / "runs" / args.run_id
    items_path = source / "items.jsonl"
    model_path = source / "uq_model.json"
    for required in (items_path, model_path):
        if not required.is_file():
            raise SystemExit(f"ERROR: missing input: {required}")
    payload = json.loads(model_path.read_text(encoding="utf-8"))
    if payload.get("phase") != "E":
        raise SystemExit("ERROR: uq_model.json is not a Phase E model")
    # The model records the Phase D run it was fitted from; the Phase E run id
    # extends that name, so require the prefix rather than equality.
    if not args.run_id.startswith(str(payload.get("source_run_id"))):
        raise SystemExit("ERROR: uq_model.json does not belong to the requested run")

    before = tree_hash(source)
    records = read_jsonl(items_path)
    pair_ids = load_pair_ids(ROOT / "data" / "lexuq_slice.jsonl")
    test_fraction = float(payload["split"]["test_fraction"])
    split_seed = payload["split"]["seed"]
    development, holdout = set(), set()
    for record in records:
        part = split_name(pair_ids[record["item_id"]], seed=split_seed,
                          test_fraction=test_fraction)
        (holdout if part == "test" else development).add(record["item_id"])
    # The Phase E split recorded in the model is authoritative; verify it matches.
    if set(payload["split"]["test_item_ids"]) != holdout:
        raise SystemExit("ERROR: recomputed holdout does not match the stored split")

    report = compare_within_slice(
        records, development, holdout, payload["legal_head"],
        slice_name=args.slice, provision_variant=args.provision_variant,
        method=method, seed=seed, k=k)
    after = tree_hash(source)
    if before != after:
        raise SystemExit("ERROR: source run changed while comparing; refusing to report")

    report.update({
        "run_id": "phaseF_exp2_within_slice",
        "source_run_id": args.run_id,
        "source_tree_sha256": before,
        "source_unchanged": before == after,
        "split": {"seed": split_seed, "test_fraction": test_fraction,
                  "n_development": len(development), "n_holdout": len(holdout),
                  "source": "stored in the Phase E model and verified against the slice"},
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

    rank = report["ranking_on_identical_holdout_items"]
    print(f"experiment 2 report written: {out}")
    print(f"  eligible holdout items: {report['n_holdout_eligible']} "
          f"(excluded {len(report['holdout_excluded_ids'])} without complete legal features)")
    for arm in ("pooled", "within_slice"):
        r = rank[arm]
        a = "undefined" if r["auroc"] is None else f"{r['auroc']:.4f}"
        print(f"  {arm:13s} AUROC={a}  n={r['n']}")
    for arm in ("pooled", "within_slice"):
        d = report["downstream_calibration"][arm]
        print(f"  {arm:13s} dev cross-fit ACE={_fmt(d['development_cross_fitted_ace_5bin'])} "
              f"holdout ACE={_fmt(d['holdout_ace_5bin'])} "
              f"risk@50={_fmt(d['holdout_selective_risk_at_50'])}")
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
