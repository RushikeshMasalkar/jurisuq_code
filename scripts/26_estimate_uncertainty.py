#!/usr/bin/env python3
"""26 - score a Phase D run with the fitted Phase E model (label-blind path).

This script does not inspect majority_correct, sample_correct, gold, or any
other correctness label. Missing/null/invalid Phase D fields use the normalized
sample-only provision-entropy fallback rather than being replaced by zero.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from jurisuq.uncertainty.estimator import MonotoneLogistic, estimate
from jurisuq.uncertainty.features import extract_features
from jurisuq.uncertainty.io import read_jsonl, tree_hash, write_json, write_jsonl


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-id", default="phaseA-laptop-v2-rejudged+ctx+warrant",
                    help="input run id under runs/")
    ap.add_argument("--model", default="runs/phaseE_model.json",
                    help="model JSON path, relative to repository root unless absolute")
    ap.add_argument("--out-suffix", default="+uq")
    ap.add_argument("--force", action="store_true", help="replace only the Phase E output run")
    args = ap.parse_args()
    if (Path(args.run_id).name != args.run_id or "/" in args.run_id
            or "\\" in args.run_id or args.run_id in {"", ".", ".."}):
        ap.error("--run-id must be a single run-directory name")
    if (not args.out_suffix.startswith("+") or "/" in args.out_suffix
            or "\\" in args.out_suffix or args.out_suffix in {"+", "+.", "+.."}):
        ap.error("--out-suffix must be a safe suffix such as +uq")
    source = ROOT / "runs" / args.run_id
    src_items = source / "items.jsonl"
    if not src_items.is_file():
        raise SystemExit(f"ERROR: no input run: {src_items}")
    model_path = Path(args.model)
    if not model_path.is_absolute():
        model_path = ROOT / model_path
    if not model_path.is_file():
        raise SystemExit(f"ERROR: no Phase E model: {model_path}; run scripts/25_fit_uncertainty.py first")
    model_payload = json.loads(model_path.read_text(encoding="utf-8"))
    if model_payload.get("phase") != "E" or model_payload.get("source_run_id") != args.run_id:
        raise SystemExit("ERROR: model phase/source_run_id does not match the input run")
    model_sha256 = hashlib.sha256(model_path.read_bytes()).hexdigest()
    before = tree_hash(source)
    if before != model_payload.get("source_tree_sha256"):
        raise SystemExit("ERROR: source run differs from the immutable tree used to fit this model")
    legal_head = None
    if model_payload.get("legal_head") is not None:
        legal_head = MonotoneLogistic.from_dict(model_payload["legal_head"])

    dest = ROOT / "runs" / f"{args.run_id}{args.out_suffix}"
    if dest.resolve() == source.resolve() or source.resolve() in dest.resolve().parents:
        raise SystemExit("ERROR: Phase E destination must be separate from the source run")
    if dest.exists():
        if not args.force:
            raise SystemExit(f"ERROR: output already exists: {dest} (choose another suffix or pass --force)")
        shutil.rmtree(dest)
    dest.mkdir(parents=True)

    records = read_jsonl(src_items)
    rows = []
    modes = {"legal_aware": 0, "sample_only_fallback": 0, "unscorable": 0}
    reasons: dict[str, int] = {}
    for source_record in records:
        # Query-time feature path: pass a whitelist, never iterate over/read labels.
        allowed = ("methods", "n_samples", "warrant_warranted_agreement",
                   "warrant_common_mode_score", "warrant_contradiction_mass")
        feature_record = {key: source_record.get(key) for key in allowed}
        extracted = extract_features(feature_record)
        components = extracted["components"]
        estimated = estimate(extracted, legal_head)
        score = estimated["score"]
        mode = estimated["mode"]
        reason = estimated["fallback_reason"]
        semantics = estimated["semantics"]
        modes[mode] += 1
        if reason:
            reasons[reason] = reasons.get(reason, 0) + 1
        row = dict(source_record)
        row.update({
            "uq_components": components,
            "uq_uncertainty": score,
            "uq_score_mode": mode,
            "uq_score_semantics": semantics,
            "uq_fallback_reason": reason,
            "uq_model_sha256": model_sha256,
            "uq_feature_provenance": {
                "u_prov": extracted["provision_entropy_source"],
                "u_text": extracted["text_entropy_source"],
                "legal": extracted["warrant_source"],
            },
        })
        rows.append(row)

    after = tree_hash(source)
    if before != after:
        shutil.rmtree(dest, ignore_errors=True)
        raise SystemExit("ERROR: source run changed during scoring; output removed")
    write_jsonl(dest / "items.jsonl", rows)
    write_json(dest / "uq_model.json", model_payload)
    write_json(dest / "meta.json", {
        "phase": "E", "module": "M8", "run_id": dest.name,
        "source_run_id": args.run_id, "source_tree_sha256_before": before,
        "source_tree_sha256_after": after, "source_unchanged": before == after,
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "n_items": len(rows), "score_modes": modes, "fallback_reasons": reasons,
        "model_path": str(model_path.relative_to(ROOT)) if ROOT in model_path.parents else str(model_path),
        "correctness_labels_used_by_scoring_path": False,
        "calibration_status": "uncalibrated; not a probability of correctness",
    })
    print(f"scored {len(rows)} records -> {dest}")
    print(f"score modes: {modes}")
    print(f"source tree hash: {before[:24]} -> {after[:24]}; SOURCE RUN UNCHANGED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
