#!/usr/bin/env python3
"""00 - environment check. Run this first, on your laptop, inside the repo.

Checks, in order: Python version, required packages, optional packages,
generator endpoint reachability, and the writable output directory.

    python scripts/00_env_check.py
    python scripts/00_env_check.py --base-url http://127.0.0.1:1234/v1 --model qwen2.5-7b-instruct
"""
from __future__ import annotations

import argparse
import importlib
import platform
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jurisuq.config import Config, ROOT
from jurisuq.generators import endpoint_status

REQUIRED = ["requests", "numpy", "matplotlib"]
OPTIONAL = ["torch", "transformers", "scipy", "sklearn", "pytest"]

OK = "  [ok]  "
WARN = "  [warn]"
BAD = "  [fail]"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(ROOT / "configs" / "phase_a.json"))
    ap.add_argument("--base-url", default=None)
    ap.add_argument("--model", default=None)
    ap.add_argument("--skip-endpoint", action="store_true")
    args = ap.parse_args()

    cfg = Config.load(args.config)
    if args.base_url:
        cfg.base_url = args.base_url
    if args.model:
        cfg.model = args.model

    failures = 0
    print("JURIS-UQ environment check")
    print("=" * 68)
    print(f"platform      : {platform.platform()}")
    print(f"python        : {sys.version.split()[0]}  ({sys.executable})")
    print(f"repo root     : {ROOT}")
    print("-" * 68)

    if sys.version_info < (3, 10):
        print(BAD, "Python 3.10 or newer is required")
        failures += 1
    else:
        print(OK, f"Python {sys.version_info.major}.{sys.version_info.minor}")

    for name in REQUIRED:
        try:
            mod = importlib.import_module(name)
            print(OK, f"{name} {getattr(mod, '__version__', '')}".strip())
        except ImportError:
            print(BAD, f"{name} missing  ->  pip install -r requirements.txt")
            failures += 1

    for name in OPTIONAL:
        try:
            mod = importlib.import_module(name)
            print(OK, f"{name} {getattr(mod, '__version__', '')} (optional)".strip())
        except ImportError:
            note = {
                "torch": "needed only for the real NLI clusterer and for local generation",
                "transformers": "needed for standard semantic entropy (NLI clustering)",
                "scipy": "optional, used for extra statistics",
                "sklearn": "optional, used for calibration curves later",
                "pytest": "needed to run tests/",
            }[name]
            print(WARN, f"{name} missing - {note}")

    # writable output directory
    try:
        d = ROOT / cfg.out_dir
        d.mkdir(parents=True, exist_ok=True)
        (d / ".write_test").write_text("ok")
        (d / ".write_test").unlink()
        print(OK, f"output directory writable: {d}")
    except Exception as exc:
        print(BAD, f"cannot write to {cfg.out_dir}: {exc}")
        failures += 1

    # free disk (the runs directory grows with sample dumps)
    try:
        total, used, free = shutil.disk_usage(str(ROOT))
        print(OK, f"disk free: {free / 1e9:.1f} GB of {total / 1e9:.1f} GB")
    except Exception:
        pass

    # generator endpoint
    print("-" * 68)
    if args.skip_endpoint:
        print(WARN, "endpoint check skipped (--skip-endpoint)")
    else:
        st = endpoint_status(cfg)
        if st["reachable"]:
            print(OK, f"generator endpoint reachable at {st['base_url']}")
            if st["models"]:
                print("        models:", ", ".join(str(m) for m in st["models"][:8]))
                if cfg.model not in st["models"]:
                    print(WARN, f"configured model {cfg.model!r} is not in the list above; "
                                f"set it with --set model=<id>")
            else:
                print(WARN, "endpoint answered but listed no models")
        else:
            print(WARN, f"no generator at {cfg.base_url} ({st['error']})")
            print("        start LM Studio (or llama-server) and load a model, or use "
                  "--set provider=mock for a plumbing test")
            print("        this is a warning, not a failure: data and analysis scripts run offline")

    print("=" * 68)
    if failures:
        print(f"RESULT: {failures} blocking problem(s). Fix them before Phase A.")
        return 1
    print("RESULT: ready. Next: python scripts/01_make_data.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
