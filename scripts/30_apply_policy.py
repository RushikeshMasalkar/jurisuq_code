#!/usr/bin/env python3
"""30 - apply the Phase F calibration maps and decision policy (label-blind).

This is the query path. It reads a whitelist of fields from each stored record -
the Phase E score, the Phase D flags and as-of date, the slice, and the question
topic - and never reads ``majority_correct``, ``sample_correct``, ``gold`` or
``trap``. Harm class comes from the question's offence cluster in the Phase C
statute store, not from the gold provision.

A stratum with no fitted map yields ``p_reliable = null`` (absence, never zero)
and the policy's documented undefined-reliability action.
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

from jurisuq.calibration.evaluate import attach_probabilities
from jurisuq.calibration.policy import DecisionPolicy, harm_class_from_store
from jurisuq.uncertainty.io import read_jsonl, tree_hash, write_json, write_jsonl

#: The only keys the query path may read from a stored record.
QUERY_FIELDS = ("item_id", "slice", "topic", "uq_uncertainty",
                "uq_components", "warrant_common_mode_flags", "warrant_as_of")

_FLAG_TOKENS = ("stale_provision", "unresolvable_assertion", "foreign_provision",
                "internal_contradiction")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-id", default="phaseA-laptop-v2-rejudged+ctx-r2+typed+warrant+uq-exact",
                    help="input Phase E run id under runs/")
    ap.add_argument("--model", default="runs/phaseF_calibration_model.json",
                    help="Phase F calibration model, relative to repository root unless absolute")
    ap.add_argument("--out-suffix", default="+cal")
    ap.add_argument("--statutes", default="data/statutes/statutes_v1.jsonl")
    ap.add_argument("--force", action="store_true", help="replace only the Phase F output run")
    args = ap.parse_args()

    if (Path(args.run_id).name != args.run_id or "/" in args.run_id
            or "\\" in args.run_id or args.run_id in {"", ".", ".."}):
        ap.error("--run-id must be a single run-directory name")
    if (not args.out_suffix.startswith("+") or "/" in args.out_suffix
            or "\\" in args.out_suffix or args.out_suffix in {"+", "+.", "+.."}):
        ap.error("--out-suffix must be a safe suffix such as +cal")

    source = ROOT / "runs" / args.run_id
    src_items = source / "items.jsonl"
    if not src_items.is_file():
        raise SystemExit(f"ERROR: no input run: {src_items}")
    model_path = Path(args.model)
    if not model_path.is_absolute():
        model_path = ROOT / model_path
    if not model_path.is_file():
        raise SystemExit(f"ERROR: no Phase F model: {model_path}; "
                         "run scripts/29_fit_calibration.py first")
    payload = json.loads(model_path.read_text(encoding="utf-8"))
    if payload.get("phase") != "F" or payload.get("source_run_id") != args.run_id:
        raise SystemExit("ERROR: model phase/source_run_id does not match the input run")
    model_sha256 = hashlib.sha256(model_path.read_bytes()).hexdigest()

    statute_path = Path(args.statutes)
    if not statute_path.is_absolute():
        statute_path = ROOT / statute_path
    if hashlib.sha256(statute_path.read_bytes()).hexdigest() != payload.get("statutes_sha256"):
        raise SystemExit("ERROR: statute store differs from the store used to fit the maps")
    statute_rows = [json.loads(line) for line in
                    statute_path.read_text(encoding="utf-8").splitlines() if line.strip()]

    before = tree_hash(source)
    if before != payload.get("source_tree_sha256"):
        raise SystemExit("ERROR: source run differs from the immutable tree used to fit the maps")

    policy = DecisionPolicy.from_dict(payload.get("policy", {}))
    harm_rule = payload.get("harm_rule", "max")
    dest = ROOT / "runs" / f"{args.run_id}{args.out_suffix}"
    if dest.resolve() == source.resolve() or source.resolve() in dest.resolve().parents:
        raise SystemExit("ERROR: Phase F destination must be separate from the source run")
    if dest.exists():
        if not args.force:
            raise SystemExit(f"ERROR: output already exists: {dest} "
                             "(choose another suffix or pass --force)")
        shutil.rmtree(dest)
    dest.mkdir(parents=True)

    records = read_jsonl(src_items)
    probabilities = attach_probabilities(records, payload)
    rows, decisions = [], []
    status_census: dict[str, int] = {}
    for record in records:
        query = {key: record.get(key) for key in QUERY_FIELDS}
        item_id = query["item_id"]
        prob = probabilities[item_id]
        harm_class = harm_class_from_store(query["topic"], statute_rows, rule=harm_rule)
        flags = tuple(flag for flag in (query.get("warrant_common_mode_flags") or [])
                      if flag in _FLAG_TOKENS)
        decision = policy.decide(prob["p_reliable"], harm_class, flags=flags,
                                 as_of=query.get("warrant_as_of"))
        decisions.append(decision)
        status_census[prob["calibration_status"]] = status_census.get(
            prob["calibration_status"], 0) + 1
        row = dict(record)
        row.update({
            "p_reliable": decision["p_reliable"],
            "calibration_status": prob["calibration_status"],
            "calibration_stratum": prob["stratum"],
            "calibration_method": (payload["strata"].get(prob["stratum"]) or {}).get("method"),
            "harm_class": harm_class,
            "action": decision["action"],
            "action_trigger": decision["trigger"],
            "action_reason": decision["reason"],
            "action_thresholds": decision["thresholds"],
            "calibration_model_sha256": model_sha256,
        })
        rows.append(row)

    after = tree_hash(source)
    if before != after:
        shutil.rmtree(dest, ignore_errors=True)
        raise SystemExit("ERROR: source run changed during scoring; output removed")

    action_counts = {action: sum(1 for d in decisions if d["action"] == action)
                     for action in ("answer", "verify", "abstain")}
    write_jsonl(dest / "items.jsonl", rows)
    write_json(dest / "calibration_model.json", payload)
    write_json(dest / "meta.json", {
        "phase": "F", "modules": ["M9", "M10"], "run_id": dest.name,
        "source_run_id": args.run_id,
        "source_tree_sha256_before": before, "source_tree_sha256_after": after,
        "source_unchanged": before == after,
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "n_items": len(rows),
        "query_fields_read": list(QUERY_FIELDS),
        "correctness_labels_used_by_scoring_path": False,
        "calibration_status_census": dict(sorted(status_census.items())),
        "actions": action_counts,
        "policy": policy.to_dict(),
        "harm_rule": harm_rule,
        "harm_class_census": {cls: sum(1 for r in rows if r["harm_class"] == cls)
                              for cls in sorted({r["harm_class"] for r in rows})},
        "model_path": (str(model_path.relative_to(ROOT)) if ROOT in model_path.parents
                       else str(model_path)),
        "model_sha256": model_sha256,
        "calibration_semantics": ("p_reliable estimates P(returned majority answer correct) "
                                  "under the fitting population; not a guarantee"),
    })
    print(f"calibrated and decided {len(rows)} records -> {dest}")
    print(f"calibration status: {dict(sorted(status_census.items()))}")
    print(f"actions: {action_counts}")
    print(f"source tree hash: {before[:24]} -> {after[:24]}; SOURCE RUN UNCHANGED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
