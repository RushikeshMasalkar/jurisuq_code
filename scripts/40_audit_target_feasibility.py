#!/usr/bin/env python3
"""40 - Phase G: audit whether a valid target population exists in the frozen runs.

Read-only. Answers, from stored artefacts alone:

1. does any slice hold both correctness classes (PHASE-E §7.4, PHASE-F §12.1)?
2. does the Phase D detector fire *and* stay silent inside that slice
   (PHASE-E structural G5 finding)?
3. are both classes present in the development and evaluation partitions
   (PHASE-E §6, PHASE-F §7)?
4. is a pooled L1+L7 population confounded by slice?

Nothing is generated, fitted or scored here, and the source run is hashed before
and after to prove it was not modified.

    python scripts/40_audit_target_feasibility.py
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

from jurisuq.target import confound_report, population_report
from jurisuq.uncertainty.io import read_jsonl, tree_hash, write_json
from jurisuq.uncertainty.split import load_pair_ids, split_name


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-id",
                    default="phaseA-laptop-v2-rejudged+ctx-r2+typed+warrant+uq-exact",
                    help="run holding the Phase D detector fields and Phase E scores")
    ap.add_argument("--config", default=str(ROOT / "configs" / "phase_g_target.json"))
    ap.add_argument("--out", default="runs/phaseG_feasibility_audit.json")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    if Path(args.run_id).name != args.run_id or "/" in args.run_id or "\\" in args.run_id:
        ap.error("--run-id must be a single run-directory name")
    cfg_path = Path(args.config)
    cfg = json.loads(cfg_path.read_text(encoding="utf-8")) if cfg_path.is_file() else {}

    source = ROOT / "runs" / args.run_id
    items_path = source / "items.jsonl"
    model_path = source / "uq_model.json"
    for required in (items_path, model_path):
        if not required.is_file():
            raise SystemExit(f"ERROR: missing input: {required}")

    payload = json.loads(model_path.read_text(encoding="utf-8"))
    before = tree_hash(source)
    records = read_jsonl(items_path)

    # The stored split is authoritative; recompute it only to check agreement.
    split_seed = payload["split"]["seed"]
    test_fraction = float(payload["split"]["test_fraction"])
    pair_ids = load_pair_ids(ROOT / "data" / "lexuq_slice.jsonl")
    partition_of = {}
    for record in records:
        part = split_name(pair_ids[record["item_id"]], seed=split_seed,
                          test_fraction=test_fraction)
        partition_of[record["item_id"]] = (
            "evaluation" if part == "test" else "development")
    stored_test = set(payload["split"]["test_item_ids"])
    recomputed_test = {i for i, p in partition_of.items() if p == "evaluation"}
    split_matches = stored_test == recomputed_test
    if not split_matches:
        raise SystemExit("ERROR: recomputed holdout does not match the stored split")

    slices = sorted({r.get("slice") for r in records if r.get("slice")})
    per_slice = {}
    for name in slices:
        per_slice[name] = population_report(records, slice_name=name,
                                           partition_of=partition_of)
    pooled = population_report(records, slice_name=None, partition_of=partition_of)
    confound = confound_report(records)

    after = tree_hash(source)
    if before != after:
        raise SystemExit("ERROR: source run changed during the audit; refusing to report")

    report = {
        "phase": "G",
        "experiment": "target-population feasibility (read-only)",
        "question": ("does any population in the frozen artefacts satisfy the documented "
                     "prerequisite for evaluating G5 and the L7 half of G6?"),
        "source_run_id": args.run_id,
        "source_tree_sha256": before,
        "source_unchanged": before == after,
        "split": {"seed": split_seed, "test_fraction": test_fraction,
                  "seed_source": "stored in the Phase E model, recomputed and checked",
                  "matches_stored": split_matches},
        "per_slice": per_slice,
        "pooled_l1_l7": pooled,
        "confound": confound,
        "any_population_ready": any(block["status"] == "READY"
                                    for block in per_slice.values()),
        "specification_note": (
            "The repository contains no Phase G specification or gate number; the "
            "conditions tested here are the sentences in PHASE-E.md §7.4 and the "
            "structural G5 finding, and PHASE-F.md §12.1. No new gate is defined."),
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "inputs": {"items_sha256": hashlib.sha256(items_path.read_bytes()).hexdigest(),
                   "model_sha256": hashlib.sha256(model_path.read_bytes()).hexdigest()},
        "config_path": (cfg_path.relative_to(ROOT).as_posix()
                        if cfg_path.is_file() and cfg_path.is_relative_to(ROOT) else None),
    }

    out = Path(args.out)
    if not out.is_absolute():
        out = ROOT / out
    if out.exists() and not args.force:
        raise SystemExit(f"ERROR: {out} exists (pass --force)")
    write_json(out, report)

    print(f"target-population feasibility audit written: {out}")
    print(f"  source run: {args.run_id}")
    print()
    header = (f"  {'population':10s} {'n':>5s} {'correct':>8s} {'incorrect':>10s} "
              f"{'fired':>6s} {'silent':>7s} {'partial':>8s} {'AUROC(W)':>9s} {'status':>10s}")
    for name, block in list(per_slice.items()) + [("L1+L7", pooled)]:
        counts, census = block["counts"], block["detector_census"]
        auroc_text = "undefined" if block["detector_auroc"] is None else f"{block['detector_auroc']:.4f}"
        print(header if name == list(per_slice)[0] else "")
        print(f"  {name:10s} {counts['total']:5d} {counts['correct']:8d} "
              f"{counts['incorrect']:10d} {census['fired']:6d} {census['silent']:7d} "
              f"{census['partial']:8d} {auroc_text:>9s} {block['status']:>10s}")
    print()
    for name, block in list(per_slice.items()) + [("L1+L7", pooled)]:
        failed = [k for k, v in block["conditions"].items() if not v["met"]]
        detail = "; ".join(f"{k}: {block['conditions'][k]['detail']}" for k in failed)
        print(f"  {name}: {'all documented conditions met' if not failed else 'NOT ready -> ' + detail}")
    print()
    print(f"  detector AUROC against slice==L1: {confound['detector_auroc_against_slice_l1']}")
    print(f"  detector AUROC within slice      : "
          f"L1={confound['detector_auroc_within_slice']['L1']['detector_auroc']}, "
          f"L7={confound['detector_auroc_within_slice']['L7']['detector_auroc']}")
    print(f"  detector AUROC pooled            : {confound['detector_auroc_pooled']}")
    print(f"  any ready population: {report['any_population_ready']}")
    print(f"  source unchanged: {before == after}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
