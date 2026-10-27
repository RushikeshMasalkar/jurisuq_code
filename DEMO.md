# JURIS-UQ — quick start and demonstration

Everything on this page runs **offline, with no model and no API key**. It
demonstrates the implementation: the pipeline components, the frozen evidence,
the gates as recorded, and the current Phase G state. It is not a research
result and it does not reproduce the model runs.

For the research narrative, read [`PROFESSOR-SUMMARY.md`](PROFESSOR-SUMMARY.md).
For what is finished and what is blocked, read [`STATUS.md`](STATUS.md).

---

## 1. Requirements

- Python **3.10+** (developed and tested on 3.11).
- About 25 MB of disk for the core install; the repository itself is small.
- No GPU, no internet, no API key.

Optional, only for re-running real inference (not needed for the demo):

```powershell
pip install -r requirements-phase-a.txt   # torch + transformers, CPU wheels, ~700 MB
```

## 2. Setup

### Windows PowerShell

```powershell
cd C:\path\to\jurisuq_code

python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If `Activate.ps1` is blocked by execution policy, either use
`.\.venv\Scripts\activate.bat` from `cmd.exe`, or run the interpreter directly:
`.\.venv\Scripts\python.exe -m pytest -q`.

### macOS / Linux

```bash
cd /path/to/jurisuq_code
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## 3. The three commands that matter

```powershell
# 1. the test suite (~10 s on a laptop CPU)
python -X utf8 -m pytest -q

# 2. the environment check (read-only; warns, does not fail, when no model is running)
python -X utf8 scripts/00_env_check.py --skip-endpoint

# 3. the offline end-to-end demonstration (~1 s; writes runs/demo/)
python -X utf8 scripts/47_demo.py
```

Expected from step 3 (abridged):

```
Integrity of frozen inputs
  [ok]   MATCH    data/lexuq_target_candidates_v1.jsonl
  [ok]   MATCH    data/lexuq_target_candidates_v2.jsonl
  [ok]   MATCH    data/statutes/statutes_v1.jsonl

Steps
  [ok]   40_audit_target_feasibility.py ...
  [ok]   42_build_eval_matrix.py ...
  [ok]   43_measure_deployment.py ...
  [ok]   41_screen_target_yield.py ...        (mock provider)
  [ok]   46_revise_target_candidates_v2.py --check

Gates (as recorded; unchanged by this demo)
  G1: PASS   G2: NOT YET   G3: NOT MET   G4: PASS
  G5: NOT_EVALUABLE   G6: NOT_MET   G7: NOT_MET
  pilot: ON_HOLD

RESULT: ok. Nothing above is a research result; see DEMO.md.
```

## 4. What the demo actually does

| Step | Command it runs | What it proves |
|---|---|---|
| Integrity | — (in-process hashing) | the frozen inputs are still the bytes the project recorded; a mismatch aborts the demo with exit code 2 |
| Target-population audit | `scripts/40_audit_target_feasibility.py` | whether any frozen slice holds both correctness classes (it does not in L7) |
| §21.2 matrix, Gate G7 | `scripts/42_build_eval_matrix.py` | the headline comparison table, per-slice judge coverage, and a reason code for every undefined value |
| §21.3 deployment | `scripts/43_measure_deployment.py` | what the stored runs already measured, and which laptop numbers are still undefined |
| Plumbing screen | `scripts/41_screen_target_yield.py --set provider=mock` | the real screen harness end to end, including per-item evidence |
| Candidate contract + v2 | `scripts/46_revise_target_candidates_v2.py --check` | both candidate sets validate; the committed v2 is exactly what its builder produces |

Outputs land in `runs/demo/` (override with `--out-dir`):

| File | Contents |
|---|---|
| `demo_summary.json` | machine-readable record of every step, integrity check, gate value and disclaimer |
| `phaseG_feasibility_audit.json` | target-population audit |
| `phaseG_eval_matrix.json` | §21.2 matrix + `gate_g7` |
| `phaseG_deployment.json` | §21.3 measurements |
| `demo_screen_mock.json`, `demo_screen_mock_items.jsonl` | the mock plumbing screen and its per-item records |

`runs/demo/` is a scratch directory. Nothing under the shipped `runs/`, `data/`
or `configs/` is written to — a test enforces that.

## 5. How to read the gate output

| Gate | Verdict | One-line reading |
|---|---|---|
| G1 | **PASS** | on the matched slice, sample agreement hid a repeated legal error: 43.4 % correct on L1, 0/100 on L7 |
| G2 | **NOT YET** | typed relations are accurate, but the required unanimously-wrong collision rescue does not occur |
| G3 | **NOT MET** | no encoder earns a passing representation-safety claim |
| G4 | **PASS** | the temporal detector separates wrong from right collisions (AUROC 0.9412, CI [0.8529, 1.0000]) |
| G5 | **NOT_EVALUABLE** | the L7 holdout has one correctness class, so a ranking is undefined |
| G6 | **NOT_MET** | calibration and selective risk fail their thresholds on L1 |
| G7 | **NOT_MET** | no target slice exists on which a headline ranking is defined |

**A passing gate in this table is not a claim that the instrument works in
general.** G1 and G4 are scoped to one quantized 7B checkpoint and one synthetic
200-item construction.

## 6. Mock, fixture, or real — do not confuse them

| Term | What it means here |
|---|---|
| **mock provider** | a deterministic stub that echoes the correct answer. Any accuracy it shows (100 %) is by construction. Used only to prove plumbing. |
| **fixture** | a stored artefact under `runs/` from a real past run. Re-analysing it is not a new experiment. |
| **real run** | generation against a live model endpoint with `--allow-generation`. None is performed by this demo. |

The demonstration never calls a model. If you see an accuracy figure from the
demo, it came from a mock or from a stored run — never from a model executed
during the demo.

## 7. Running it against a real local model (optional, not required)

Only if you have LM Studio or `llama-server` serving an OpenAI-compatible
endpoint. Check reachability **without** generating anything:

```powershell
python -X utf8 scripts/00_env_check.py --base-url http://127.0.0.1:1234/v1
```

A real screen requires the explicit flag and a model id, because the committed
config carries the placeholder `REPLACE_WITH_YOUR_MODEL_ID`:

```powershell
python -X utf8 scripts/41_screen_target_yield.py `
    --data data\lexuq_target_candidates_v2.jsonl `
    --slice L7 `
    --out runs\phaseG_l7_v2_diagnostic.json `
    --save-items runs\phaseG_l7_v2_diagnostic_items.jsonl `
    --allow-generation `
    --set model=<your-model-id> --set n_samples=3
```

That command spends 11–27 minutes of local compute and $0. It is **not** run by
this demo, and running it does not discharge the human-review prerequisite for
the cross-model comparison.

## 8. End-to-end sequence for the available pipeline

```powershell
python -X utf8 -m pytest -q                                   # tests
python -X utf8 scripts/00_env_check.py --skip-endpoint        # environment
python -X utf8 scripts/47_demo.py                             # offline chain
python -X utf8 scripts/46_revise_target_candidates_v2.py --check
python -X utf8 -c "from jurisuq.target import load_candidates as l; print(len(l('data/lexuq_target_candidates_v1.jsonl')))"
```

## 9. Known limitations of the demonstration

- It does not reproduce Phase A–F numbers; those need the stored runs (present)
  or the model (absent here). Re-analysis of the stored runs is included.
- It does not evaluate any model, so it cannot say anything about model quality.
- The `torch`/`transformers`-dependent paths (NLI clusterer, local generation)
  are not exercised; their tests skip or use stubs where possible.
- The 12-item L7 diagnostic figures (0/12 majority, 0/36 samples) are
  **operator-reported**: the two artefact files are not in this repository.

## 10. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `AttributeError: module 'openai'` / import errors | wrong interpreter | activate the venv, or call `.\.venv\Scripts\python.exe` directly |
| `Activate.ps1 cannot be loaded` | PowerShell execution policy | use `activate.bat`, or call the venv interpreter directly |
| demo exits `2` | a frozen input no longer matches its recorded hash | `git status` — a tracked data file was modified; restore it, do not "fix" the hash |
| `ERROR: ... exists (pass --force)` | a script refuses to overwrite shipped evidence | pass `--out` to a new path instead of `--force` |
| endpoint warnings from `00_env_check` | no local model running | expected; everything on this page is offline |
