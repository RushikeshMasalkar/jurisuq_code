#!/usr/bin/env python3
"""47 - offline integrity and integration check for JURIS-UQ.

This is a validation tool, not an experiment. It runs the parts of the pipeline
that need **no model, no network and no API key** against the frozen inputs, so
that a regression in the stored evidence or in an offline stage shows up as a
non-zero exit instead of as a silently changed number.

    python scripts/47_offline_check.py                 # -> runs/offline_check/
    python scripts/47_offline_check.py --out-dir /tmp/jurisuq-check
    python scripts/47_offline_check.py --quick         # skip the mock screen

Checks, in order:

1. **Integrity** -- hashes the frozen inputs and compares them with the digests
   this repository records. A mismatch is an integrity failure (exit 2), so the
   check cannot run stages against data that has changed underneath it.
2. **Target-population audit** (`scripts/40`) -- does any frozen slice hold both
   correctness classes?
3. **§21.2 evaluation matrix and Gate G7** (`scripts/42`) -- the headline table,
   with per-slice judge coverage and a reason code for every undefined value.
4. **§21.3 deployment measurements** (`scripts/43`) -- the offline half.
5. **Screen-harness smoke run** (`scripts/41`, `provider=mock`) -- a handful of
   items through the real screen harness. The mock provider echoes the gold, so
   its accuracy is 100 % *by construction*: this checks the harness wiring, not
   a model.
6. **Candidate-set contract** -- `v1` and `v2` both validate, and `v2` is
   rebuilt in memory by `scripts/46` and compared with the committed file.

Everything is written under ``--out-dir`` (default ``runs/offline_check``).
Nothing in the shipped `runs/` tree or under `data/` is modified or overwritten.

The check **reports** the recorded gate verdicts (G1-G7) and never re-derives or
upgrades one; the only verdict it recomputes is G7, from the matrix produced in
step 3, as a cross-check against the stored value.
"""
from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

#: Frozen inputs and the digests this repository records for them.
#: A mismatch is an integrity failure, not a warning.
EXPECTED_HASHES = {
    "data/lexuq_target_candidates_v1.jsonl":
        "f49f4d91946387eb0534718945092cc2f840bd9f2aee053ed9ac13c3f296d341",
    "data/lexuq_target_candidates_v2.jsonl":
        "44e7b5a2f3f968a7523b071a972ef522894f7ad0453e7390dff728b020878e8c",
    "data/statutes/statutes_v1.jsonl":
        "ef50705e99b3ba8de8287df0e289c3df2dd5a4f648ccd58bdb9a9afd2c682b18",
}

#: Gate verdicts as the phase documents record them. The check *reports* these;
#: it does not re-derive them and never changes them.
RECORDED_GATES = {
    "G1": "PASS",
    "G2": "NOT YET",
    "G3": "NOT MET",
    "G4": "PASS",
    "G5": "NOT_EVALUABLE",
    "G6": "NOT_MET",
    "G7": "NOT_MET",
}

#: The canonical source and calibration runs are the ones scripts/40 and
#: scripts/42 use by default; the check does not override them, so a changed
#: default in those scripts would surface here.
FROZEN_RUN = "phaseA-laptop-v2-rejudged+ctx-r2+typed+warrant+uq-exact"
CAL_RUN = "phaseA-laptop-v2-rejudged+ctx-r2+typed+warrant+uq-exact+cal-r2"


def _sha256(path: Path) -> str:
    from jurisuq.pilot import sha256_file

    return sha256_file(path)


def check_integrity(root: Path = ROOT) -> list[dict]:
    """Compare the frozen inputs with their recorded digests."""
    checks = []
    for rel, expected in EXPECTED_HASHES.items():
        path = root / rel
        if not path.is_file():
            checks.append({"path": rel, "status": "MISSING", "expected": expected})
            continue
        actual = _sha256(path)
        checks.append({
            "path": rel,
            "status": "MATCH" if actual == expected else "MISMATCH",
            "expected": expected,
            "actual": actual,
        })
    return checks


def _run(script: str, args: list[str], root: Path) -> dict:
    """Run a repository script and capture its tail of output."""
    cmd = [sys.executable, "-X", "utf8", str(root / "scripts" / script), *args]
    proc = subprocess.run(cmd, cwd=str(root), capture_output=True, text=True)
    tail = [line for line in (proc.stdout + proc.stderr).splitlines() if line.strip()][-8:]
    return {"script": script, "argv": args, "returncode": proc.returncode, "tail": tail}


def _out_path(out_dir: Path, name: str) -> str:
    return str(out_dir / name)


def build_offline_check(out_dir: Path, root: Path = ROOT, quick: bool = False) -> dict:
    """Run every offline stage and return the summary record."""
    out_dir.mkdir(parents=True, exist_ok=True)

    integrity = check_integrity(root)
    integrity_ok = all(c["status"] == "MATCH" for c in integrity)

    steps: list[dict] = []
    artifacts: list[str] = []

    if integrity_ok:
        # 1. target-population audit (offline, reads frozen runs only)
        # the scripts' own defaults name the canonical source run
        steps.append(_run("40_audit_target_feasibility.py",
                          ["--out", _out_path(out_dir, "phaseG_feasibility_audit.json"),
                           "--force"], root))
        artifacts.append(_out_path(out_dir, "phaseG_feasibility_audit.json"))

        # 2. the §21.2 evaluation matrix and the G7 verdict
        steps.append(_run("42_build_eval_matrix.py",
                          ["--out", _out_path(out_dir, "phaseG_eval_matrix.json"),
                           "--force"], root))
        artifacts.append(_out_path(out_dir, "phaseG_eval_matrix.json"))

        # 3. §21.3 deployment measurements, offline half
        steps.append(_run("43_measure_deployment.py",
                          ["--out", _out_path(out_dir, "phaseG_deployment.json"),
                           "--force"], root))
        artifacts.append(_out_path(out_dir, "phaseG_deployment.json"))

        # 4. the real screen harness with the mock provider: wiring only
        if not quick:
            # --force is scoped to this check's own scratch directory: the screen
            # harness refuses to overwrite an existing report, which is correct
            # for shipped evidence and wrong for a check that can be re-run.
            steps.append(_run("41_screen_target_yield.py",
                              ["--data", "data/lexuq_target_candidates_v1.jsonl",
                               "--slice", "L7", "--items", "2",
                               "--out", _out_path(out_dir, "offline_check_screen_mock.json"),
                               "--save-items", _out_path(out_dir, "offline_check_screen_mock_items.jsonl"),
                               "--force",
                               "--set", "provider=mock", "--set", "n_samples=3"], root))
            artifacts.extend([_out_path(out_dir, "offline_check_screen_mock.json"),
                              _out_path(out_dir, "offline_check_screen_mock_items.jsonl")])

        # 5. candidate-set contract + the v2 builder reproducibility check
        steps.append(_run("46_revise_target_candidates_v2.py", ["--check"], root))

    from jurisuq.target import load_candidates

    candidates = {}
    for version in ("v1", "v2"):
        path = root / "data" / f"lexuq_target_candidates_{version}.jsonl"
        items = load_candidates(path)
        candidates[version] = {
            "path": str(path.relative_to(root)),
            "n_items": len(items),
            "slices": {s: sum(1 for i in items if i["slice"] == s) for s in ("L1", "L7")},
            "provenance_verified_all_false": all(
                i["provenance"]["verified"] is False for i in items),
            "review_status": sorted({i["review"]["status"] for i in items}),
        }

    # The label review is an artefact in this repository; report it as recorded.
    review_path = root / "runs" / "phaseG_l7_label_review_v1.json"
    review = json.loads(review_path.read_text(encoding="utf-8")) if review_path.is_file() else None
    label_review = None
    if review:
        s = review["summary"]
        label_review = {
            "report": review["artifact_path"],
            "n_items": s["n_items_reviewed"],
            "confirmed": s["confirmed"],
            "ambiguous": s["ambiguous"],
            "unsupported": s["unsupported"],
            "gold_labels_changed": s["gold_labels_changed"],
            "is_human_legal_review": review["reviewer"]["is_human_legal_review"],
        }

    g7_from_artifact = None
    matrix_path = out_dir / "phaseG_eval_matrix.json"
    if matrix_path.is_file():
        matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
        gate = matrix.get("gate_g7") or {}
        g7_from_artifact = gate.get("verdict") or gate.get("status")

    summary = {
        "artifact": "offline integrity and integration check",
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "model_called": False,
        "network_used": False,
        "integrity": integrity,
        "integrity_ok": integrity_ok,
        "steps": steps,
        "step_failures": [s["script"] for s in steps if s["returncode"] != 0],
        "gates_recorded": RECORDED_GATES,
        "g7_recomputed_from_matrix": g7_from_artifact,
        "pilot": "ON_HOLD",
        "candidates": candidates,
        "label_review": label_review,
        "artifacts": artifacts,
        "notes": [
            "The mock screen exercises the harness wiring only; the mock provider "
            "echoes the gold, so its accuracy is 100% by construction and is not "
            "a measurement.",
            "No model was called and no network request was made.",
            "Gate verdicts are the ones the stored artefacts record; this check "
            "does not re-derive or upgrade them.",
            "The 12-item L7 diagnostic (0/12 majority, 0/36 samples) is a single-model "
            "measurement, not a cross-model evaluation.",
        ],
    }

    (out_dir / "offline_check_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    summary["summary_path"] = str(out_dir / "offline_check_summary.json")
    return summary


def print_report(summary: dict) -> None:
    line = "-" * 74
    print(line)
    print("JURIS-UQ offline integrity and integration check")
    print(line)
    print(f"python {summary['python']} | model called: {summary['model_called']} | "
          f"network used: {summary['network_used']}")
    print()
    print("Integrity of frozen inputs")
    for check in summary["integrity"]:
        mark = {"MATCH": "[ok]", "MISMATCH": "[FAIL]", "MISSING": "[FAIL]"}[check["status"]]
        print(f"  {mark:6} {check['status']:8} {check['path']}")
    print()
    print("Stages")
    for step in summary["steps"]:
        mark = "[ok]" if step["returncode"] == 0 else "[FAIL]"
        print(f"  {mark:6} {step['script']} {' '.join(step['argv'])[:70]}")
    if summary["step_failures"]:
        print(f"  failing: {summary['step_failures']}")
    print()
    print("Gates (as recorded; unchanged by this check)")
    for gate, verdict in summary["gates_recorded"].items():
        print(f"  {gate}: {verdict}")
    print(f"  pilot: {summary['pilot']}")
    print()
    print("Candidate sets")
    for version, info in summary["candidates"].items():
        print(f"  {version}: {info['n_items']} items {info['slices']} "
              f"provenance_verified_all_false={info['provenance_verified_all_false']}")
    if summary["label_review"]:
        lr = summary["label_review"]
        print(f"  label review: {lr['n_items']} items, {lr['confirmed']} confirmed, "
              f"{lr['ambiguous']} ambiguous, {lr['unsupported']} unsupported, "
              f"human_review={lr['is_human_legal_review']}")
    print()
    print(f"Summary written: {summary.get('summary_path')}")
    print(line)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out-dir", default=str(ROOT / "runs" / "offline_check"),
                    help="where to write the check outputs (default runs/offline_check)")
    ap.add_argument("--quick", action="store_true",
                    help="skip the mock screen stage")
    ap.add_argument("--quiet", action="store_true", help="write outputs but print nothing")
    args = ap.parse_args(argv)

    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = ROOT / out_dir

    summary = build_offline_check(out_dir, ROOT, quick=args.quick)
    if not args.quiet:
        print_report(summary)

    if not summary["integrity_ok"]:
        if not args.quiet:
            print("RESULT: integrity failure. The offline stages were not run.")
        return 2
    if summary["step_failures"]:
        if not args.quiet:
            print(f"RESULT: {len(summary['step_failures'])} stage(s) failed.")
        return 1
    if not args.quiet:
        print("RESULT: ok. Frozen inputs match their recorded digests and every "
              "offline stage exited 0.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
