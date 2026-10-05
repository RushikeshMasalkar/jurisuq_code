#!/usr/bin/env bash
# Phase A, one command per stage. Run from the repo root:
#
#   bash run_phase_a.sh smoke     # plumbing test, no model needed (~20 s)
#   bash run_phase_a.sh laptop    # the real E1 run on your machine (hours)
#   bash run_phase_a.sh analyze   # analysis + figure for the laptop run
#   bash run_phase_a.sh tests     # unit tests
#
set -euo pipefail

STAGE="${1:-smoke}"
PY="${PY:-python3}"

case "$STAGE" in
  smoke)
    echo "== 00 environment =="        ; $PY scripts/00_env_check.py --skip-endpoint || true
    echo "== 01 build slice =="        ; $PY scripts/01_make_data.py --n-per-slice 40
    echo "== 02 sample (mock) =="      ; $PY scripts/02_run_inference.py --config configs/phase_a_smoke.json
    echo "== 03 E1 analysis =="        ; $PY scripts/03_analyze_e1.py --run-id phaseA-smoke
    echo "== 04 figure =="             ; $PY scripts/04_make_figure.py --run-id phaseA-smoke
    echo; echo "smoke test complete. Look at runs/phaseA-smoke/"
    ;;

  laptop)
    echo "== 00 environment =="        ; $PY scripts/00_env_check.py
    echo "== 01 build slice =="        ; $PY scripts/01_make_data.py --n-per-slice 100
    echo "== 02 sample (your model) =="; $PY scripts/02_run_inference.py --config configs/phase_a.json
    echo "== 03 E1 analysis =="        ; $PY scripts/03_analyze_e1.py --run-id phaseA-laptop
    echo "== 04 figure =="             ; $PY scripts/04_make_figure.py --run-id phaseA-laptop
    ;;

  analyze)
    $PY scripts/03_analyze_e1.py --run-id "${RUN_ID:-phaseA-laptop}"
    $PY scripts/04_make_figure.py --run-id "${RUN_ID:-phaseA-laptop}"
    ;;

  tests)
    $PY -m pytest -q
    ;;

  *)
    echo "usage: bash run_phase_a.sh [smoke|laptop|analyze|tests]" >&2
    exit 2
    ;;
esac
