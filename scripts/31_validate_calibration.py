#!/usr/bin/env python3
"""31 - held-out Gate G6 evaluation for Phase F (E6).

Correctness labels are read only here, after the calibrated probabilities and
actions have been written by ``30_apply_policy.py``. The calibration maps are
applied, never refitted, and the holdout is the Phase E pair-grouped holdout.

The four G6 conditions of master-guide section 20.3 are evaluated individually
and the verdict is recorded, including the case where a condition cannot be
evaluated at all. A failed condition is reported with the strata that failed;
it is never repaired by changing a threshold after the fact.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from jurisuq.calibration.evaluate import evaluate_g6, query_path_is_label_blind
from jurisuq.calibration.policy import DecisionPolicy
from jurisuq.uncertainty.io import read_jsonl, tree_hash, write_json

QUERY_SCRIPT = ROOT / "scripts" / "30_apply_policy.py"


def _finite(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-id", default="phaseA-laptop-v2-rejudged+ctx-r2+typed+warrant+uq-exact+cal",
                    help="Phase F output run id under runs/")
    ap.add_argument("--config", default=str(ROOT / "configs" / "phase_f_calibration.json"))
    ap.add_argument("--report-out", default=None,
                    help="default: <run>/calibration_report.json")
    ap.add_argument("--force", action="store_true", help="overwrite an existing report only")
    args = ap.parse_args()

    if (Path(args.run_id).name != args.run_id or "/" in args.run_id
            or "\\" in args.run_id or args.run_id in {"", ".", ".."}):
        ap.error("--run-id must be a single run-directory name")
    cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
    source = ROOT / "runs" / args.run_id
    items_path = source / "items.jsonl"
    model_path = source / "calibration_model.json"
    if not items_path.is_file():
        raise SystemExit(f"ERROR: no Phase F run: {items_path}")
    if not model_path.is_file():
        raise SystemExit(f"ERROR: no stored calibration model in {source}; "
                         "run scripts/30_apply_policy.py first")
    model = json.loads(model_path.read_text(encoding="utf-8"))
    if model.get("phase") != "F":
        raise SystemExit("ERROR: stored model is not a Phase F calibration model")
    # The model names its own Phase E source; the Phase F run must extend it.
    if not args.run_id.startswith(str(model["source_run_id"]) + "+"):
        raise SystemExit("ERROR: run id does not extend the model's source_run_id "
                         f"({model['source_run_id']!r})")

    report_path = Path(args.report_out) if args.report_out else source / "calibration_report.json"
    if not report_path.is_absolute():
        report_path = ROOT / report_path
    if report_path.exists() and not args.force:
        raise SystemExit(f"ERROR: report already exists: {report_path} (pass --force)")

    statute_path = ROOT / "data" / "statutes" / "statutes_v1.jsonl"
    statute_rows = [json.loads(line) for line in
                    statute_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if hashlib.sha256(statute_path.read_bytes()).hexdigest() != model.get("statutes_sha256"):
        raise SystemExit("ERROR: statute store changed since the maps were fitted")

    items_before = hashlib.sha256(items_path.read_bytes()).hexdigest()
    records = read_jsonl(items_path)

    # Determinism / plumbing checks before any metric is computed.
    missing = [r["item_id"] for r in records if "p_reliable" not in r or "action" not in r]
    if missing:
        raise SystemExit(f"ERROR: {len(missing)} records lack Phase F fields "
                         f"(first: {missing[0]})")
    if any(r.get("calibration_model_sha256") != hashlib.sha256(model_path.read_bytes()).hexdigest()
           for r in records):
        raise SystemExit("ERROR: records were scored with a different calibration model")

    interface = query_path_is_label_blind(QUERY_SCRIPT)
    policy = DecisionPolicy.from_dict(model.get("policy", {}))
    report = evaluate_g6(
        records, set(model["split"]["holdout_item_ids"]), model,
        policy=policy, statute_rows=statute_rows,
        target_coverage=float(model.get("conformal_target_coverage", 0.80)),
        ace_max=float(model.get("gate", {}).get("ace_max", 0.05)),
        min_stratum_n=int(cfg.get("gates", {}).get("min_stratum_n", 30)),
        interface_rule_ok=bool(interface["label_blind"]),
        harm_rule=model.get("harm_rule", "max"),
    )
    items_after = hashlib.sha256(items_path.read_bytes()).hexdigest()
    if items_before != items_after:
        raise SystemExit("ERROR: scored items changed during validation")

    calibration_rows = [r for r in records if _finite(r.get("p_reliable"))]
    report.update({
        "run_id": args.run_id,
        "source_run_id": model["source_run_id"],
        "calibration_model_path": str(model_path.relative_to(ROOT)),
        "calibration_model_sha256": hashlib.sha256(model_path.read_bytes()).hexdigest(),
        "scored_items_sha256": items_after,
        "items_unchanged_by_validation": items_before == items_after,
        "interface_rule": interface,
        "n_records": len(records),
        "n_calibrated": len(calibration_rows),
        "n_undefined_reliability": len(records) - len(calibration_rows),
        "calibration_status_census": {
            status: sum(1 for r in records if r.get("calibration_status") == status)
            for status in sorted({str(r.get("calibration_status")) for r in records})},
        "action_census": {action: sum(1 for r in records if r.get("action") == action)
                          for action in ("answer", "verify", "abstain")},
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "label_access": ("correctness labels are read only in this offline validation "
                         "script, after scoring was written"),
        "source_tree_hash_after_validation": tree_hash(source),
    })
    write_json(report_path, report)

    print(f"Phase F G6 report written: {report_path}")
    print(f"records {len(records)}; calibrated {len(calibration_rows)}; "
          f"undefined reliability {len(records) - len(calibration_rows)}")
    print(f"interface rule (label-blind query path): {interface['label_blind']}")
    for stratum, entry in sorted(report["per_stratum"].items()):
        metrics = entry.get("metrics") or {}
        ace_value = metrics.get("ace_5bin")
        text = "undefined" if ace_value is None else f"{ace_value:.4f}"
        print(f"  {stratum}: holdout n={entry['n_holdout']} scored={entry['n_scored']} "
              f"correct={entry['n_correct']} ACE(5)={text} status={entry['status']}")
    for name, condition in report["conditions"].items():
        state = ("undefined" if not condition["defined"]
                 else ("pass" if condition["pass"] else "FAIL"))
        print(f"  {name}: {state}")
    print(f"GATE G6: {report['verdict']}  ({report['verdict_reason']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
