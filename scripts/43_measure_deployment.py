#!/usr/bin/env python3
"""43 - Phase G: §21.3 deployment measurements.

Offline by default: summarises the stage-1 latency the frozen runs already
recorded, echoes the configuration that ran, and reports the two measurements
that need a laptop run as undefined with an explicit reason.

The laptop path is here so Stage 2 needs no code change:

    # after a live run on the target machine, with timings captured to JSON:
    python scripts/43_measure_deployment.py --timings deployment_timings.json

The timings file is a JSON object:

    {
      "configuration": {"model": "...", "quantisation": "...", "M": 10,
                        "modules_run": ["generation", "relation", "..."], "degraded": false},
      "full_cascade_seconds": [412.0, 398.4, ...],
      "peak_memory_mb": 7420.0,
      "peak_memory_method": "psutil sampled rss during query"
    }

No model is called by this script, in either mode.

    python scripts/43_measure_deployment.py            # offline summary
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from jurisuq.evaluation.deployment import deployment_report
from jurisuq.uncertainty.io import read_jsonl, tree_hash, write_json

DEFAULT_RUN = "phaseA-laptop-v2-rejudged"


def _git_commit() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                              text=True, timeout=10).stdout.strip() or None
    except Exception:
        return None


def _configuration_from_run(run_dir: Path, records: list[dict]) -> dict:
    """The configuration actually measured, from the run's own metadata (§21.3)."""
    meta_path = run_dir / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.is_file() else {}
    config = meta.get("config") or {}
    n_samples = meta.get("n_samples") or config.get("n_samples")
    return {
        "model": meta.get("provider") or config.get("model") or "unknown",
        "quantisation": config.get("quantisation") or "not recorded in run metadata",
        "M": n_samples,
        "prompt_version": meta.get("prompt_version"),
        "temperature": config.get("temperature"),
        "judge": (meta.get("judge") or {}).get("method") if isinstance(meta.get("judge"), dict) else meta.get("judge"),
        "modules_run": ["generation", "provision-level scoring"],
        "modules_not_run": ["relation model", "detector", "estimator", "decision"],
        "degraded": True,
        "degraded_because": ("this is the Phase A run: legal modules had not been built, "
                            "so it measures the stage-1 fallback path, not the full cascade"),
        "source": f"{run_dir.name}/meta.json",
        "n_items_timed": len(records),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-id", default=DEFAULT_RUN)
    ap.add_argument("--timings", default=None,
                    help="JSON with full-cascade and memory measurements from a laptop run")
    ap.add_argument("--out", default="runs/phaseG_deployment.json")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    if Path(args.run_id).name != args.run_id or "/" in args.run_id or "\\" in args.run_id:
        ap.error("--run-id must be a single run-directory name")

    run_dir = ROOT / "runs" / args.run_id
    items_path = run_dir / "items.jsonl"
    if not items_path.is_file():
        raise SystemExit(f"ERROR: missing input: {items_path}")

    before = tree_hash(run_dir)
    records = read_jsonl(items_path)
    configuration = _configuration_from_run(run_dir, records)

    measured = None
    if args.timings:
        timings_path = Path(args.timings)
        if not timings_path.is_file():
            raise SystemExit(f"ERROR: timings file not found: {timings_path}")
        measured = json.loads(timings_path.read_text(encoding="utf-8"))
        configuration = measured.get("configuration") or configuration

    report = deployment_report(
        records,
        configuration=configuration,
        full_cascade_samples=(measured or {}).get("full_cascade_seconds"),
        peak_mb=(measured or {}).get("peak_memory_mb"),
        peak_method=(measured or {}).get("peak_memory_method"),
    )
    report.update({
        "generated_by": "scripts/43_measure_deployment.py",
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "git_commit": _git_commit(),
        "source_run_id": args.run_id,
        "inputs": {"source_tree_sha256": before,
                   "items_sha256": hashlib.sha256(items_path.read_bytes()).hexdigest()},
        "measurement_mode": "laptop timings supplied" if args.timings else "offline summary only",
    })

    after = tree_hash(run_dir)
    if before != after:
        raise SystemExit("ERROR: source run changed while reading; refusing to report")
    report["inputs"]["source_unchanged_during_report"] = True

    out = Path(args.out)
    if not out.is_absolute():
        out = ROOT / out
    if out.exists() and not args.force:
        raise SystemExit(f"ERROR: {out} exists (pass --force)")
    write_json(out, report)

    stage1 = report["stage1_latency"]
    cascade = report["full_cascade_latency"]
    memory = report["peak_resident_memory"]
    print("=" * 88)
    print("PHASE G — §21.3 DEPLOYMENT MEASUREMENTS")
    print("=" * 88)
    print(f"  mode: {report['measurement_mode']}   source run: {args.run_id}")
    print(f"  configuration: {configuration['model']} | quantisation: "
          f"{configuration['quantisation']} | M={configuration['M']}")
    print(f"  modules that ran: {', '.join(configuration['modules_run'])}")
    print()
    print(f"  stage-1 latency   n={stage1['n']}  median={_fmt(stage1['median'])}s  "
          f"p95={_fmt(stage1['p95'])}s  max={_fmt(stage1['max'])}s")
    if stage1["undefined"]:
        print(f"      undefined: {stage1['undefined']}")
    print(f"  full cascade      median={_fmt(cascade['median'])}  p95={_fmt(cascade['p95'])}"
          f"   [{cascade['undefined'] or 'measured'}]")
    if cascade.get("reason"):
        print(f"      reason: {cascade['reason']}")
    print(f"  peak memory       {memory['megabytes']}   [{memory['undefined'] or 'measured'}]")
    if memory.get("reason"):
        print(f"      reason: {memory['reason']}")
    print()
    print(f"  completed offline : {', '.join(report['completed_offline'])}")
    print(f"  needs a laptop run: {', '.join(report['requires_laptop_run'])}")
    print(f"\nreport written: {out}")
    return 0


def _fmt(value) -> str:
    return "undefined" if value is None else f"{value:.2f}"


if __name__ == "__main__":
    raise SystemExit(main())
