# JURIS-UQ — Phase D deployment guide

This guide takes you from a fresh unzip to a fully run Phase D
and an updated main `README.md`, in detail. It assumes you are
starting from the **complete** zip (`jurisuq_code_phaseD_complete.zip`),
which is the repository with Phase D already integrated and the
`+ctx` and `+ctx+warrant` runs of record shipped. If instead you
are merging the **drop** zip (`jurisuq_phaseD_drop.zip`) into
your own existing Phase C checkout, see §7.

Two zips are provided:

| Zip | Contents | Use it when |
|---|---|---|
| `jurisuq_code_phaseD_complete.zip` | the whole repository, Phase D integrated, README updated, runs of record shipped | you want the complete, runnable state |
| `jurisuq_phaseD_drop.zip` | only the new Phase D files (`jurisuq/warrant/`, `scripts/23…24`, `tests/test_warrant.py`, `configs/phase_d_warrant.json`, the three Phase D docs) | you want to add Phase D to your own Phase C checkout |

---

## 1. Unzip into your working directory

Pick a working directory (call it `D:\work` on Windows, or
`~/work` on macOS/Linux) and unzip there. The zip has **no
wrapper folder**: it extracts a single top-level
`jurisuq_code/` directory.

**Windows PowerShell:**
```powershell
cd D:\work
Expand-Archive -Path .\jurisuq_code_phaseD_complete.zip -DestinationPath D:\work
```

**Windows Explorer:** right-click the zip → *Extract All…* →
choose `D:\work` → Extract.

**macOS / Linux:**
```bash
cd ~/work
unzip jurisuq_code_phaseD_complete.zip
```

You should now have `D:\work\jurisuq_code\` (or
`~/work/jurisuq_code/`). Confirm the Phase D pieces are present:

```powershell
cd jurisuq_code
dir jurisuq\warrant                       # __init__.py, detector.py, validate.py
dir scripts\23_detect_warrant.py
dir scripts\24_validate_warrant.py
dir tests\test_warrant.py
dir configs\phase_d_warrant.json
dir runs\phaseA-laptop-v2-rejudged+ctx+warrant
```

## 2. Create the environment and install dependencies

Phase D needs **nothing beyond the base project** — it is
stdlib-only, like Phase C. There is no torch, no transformers,
no model download, and no internet at runtime.

```powershell
python -m venv .venv
.\\.venv\\Scripts\\Activate.ps1        # Windows PowerShell
# source .venv/bin/activate            # macOS / Linux
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

`requirements.txt` installs `requests`, `numpy`, `matplotlib`
and `pytest`. That is everything Phase D (and the Phase A/B/C
plumbing you are about to re-verify) needs. The optional NLI and
relation-model requirements (`requirements-phase-a.txt`,
`requirements-phase-b.txt`) are **not** needed for Phase D.

## 3. Quick verification (the non-mutating check)

Run the whole test suite first. This mutates nothing and is the
fastest proof that your environment is correct:

```powershell
python -m pytest -q
```

Expected (core environment, no torch):

```text
138 passed, 1 skipped in ~1s
```

The single skip is the pre-existing torch-gated Phase B
relation-model test. The **24** new Phase D tests are in
`tests/test_warrant.py`; run them alone with:

```powershell
python -m pytest tests\test_warrant.py -q     # 27 passed
```

## 4. Run the phases, in order

The phases are cumulative. Phases A–C are already **frozen and
shipped** as runs of record; you re-run them only to reproduce,
not to proceed. Phase D is the new work. The commands below are
from the repository root with the venv active.

### 4.1 Phase A — already frozen (re-analyse only)

The Phase A run of record is `runs/phaseA-laptop-v2-rejudged/`
(200 items, 10 samples each, Qwen2.5-7B-Instruct Q4_K_M). You do
**not** need a model to re-analyse it:

```powershell
python scripts\03_analyze_e1.py --run-id phaseA-laptop-v2-rejudged
python scripts\04_make_figure.py --run-id phaseA-laptop-v2-rejudged
```

Outputs: `runs/phaseA-laptop-v2-rejudged/e1_report.json`,
`fig_e1.png`, `fig_e1.svg`. (To generate *new* answers you would
need LM Studio or `llama-server` on port 1234 and
`scripts/02_run_inference.py`; that is not required for Phase D.)

### 4.2 Phase B — already a run of record (checkpoint excluded)

The Phase B relation reports are shipped in
`runs/phaseB-relations-full/`. The 440 MB learned checkpoint is
intentionally **not** in Git, so you cannot reproduce the learned
report from the tracked files alone. Phase D does **not** depend
on the checkpoint — it runs on the exact-key representation and
activates the typed representation automatically if a record
carries Phase B cluster labels.

```powershell
python scripts\10_build_relations.py --verify-only   # dataset check, no model
```

Supplemental learned-evaluation outputs may also be present:

```text
runs\full\relation_report.json
runs\relations-full\relation_report.json
```

`runs\full` is a full E2 evaluation and reproduces the run-of-record test
metrics and G2 PASS, with 130 changed items. `runs\relations-full` is a
metrics-only evaluation with `--skip-e2`; its G2 result is `NOT YET` because
the separation criterion was intentionally not evaluated. Neither replaces
`runs\phaseB-relations-full`.

### 4.3 Phase C — reproduce the context packs

Phase C is deterministic and stdlib-only. Rebuild the statute
table, then re-attach context packs to the frozen Phase A run
under a **new** suffix so the shipped `+ctx` run stays untouched:

```powershell
:: Step 1 — build + validate the 48-row statute table
python scripts\20_build_statutes.py --out data\statutes\statutes_v1.jsonl
python -m pytest tests\test_context.py -q            # 31 passed

:: Step 2 — attach context packs (new suffix; shipped +ctx untouched)
python scripts\21_attach_context.py --run-id phaseA-laptop-v2-rejudged --out-suffix +ctx-repro --as-of 2026-10-01
```

Step 2 prints `SOURCE RUN UNCHANGED (hard rule H2 satisfied)` and
writes `runs/phaseA-laptop-v2-rejudged+ctx-repro/`. The statute
table must hash to
`20c98b74c0855c5ec4c8cda2b2d52388ea5f3e8d2514376f56db425bdd90b21e`
(the post-override value; 40 of 48 rows verified).

> If you want Phase D to read your **reproduced** context run
> instead of the shipped one, pass
> `--run-id phaseA-laptop-v2-rejudged+ctx-repro` in step 4.4 and
> a matching `--out-suffix`. The numbers are identical because
> Phase C is deterministic.

### 4.4 Phase D — the new work

```powershell
:: Step 1 — attach the warrant tuple to the Phase C +ctx run
python scripts\23_detect_warrant.py --run-id phaseA-laptop-v2-rejudged+ctx --out-suffix +warrant

:: Step 2 — E4 validation and Gate G4
python scripts\24_validate_warrant.py --run-id phaseA-laptop-v2-rejudged+ctx+warrant
```

**Step 1 expected output:**

```text
detected 200 items -> ...\runs\phaseA-laptop-v2-rejudged+ctx+warrant
  as_of policy: era (era dates {'L7': '2024-07-01', 'L1': '2024-06-30'})
  fires 105   silent 95   fire rate 0.525
  flags: {'stale_provision': 80, 'unresolvable_assertion': 25}
  CM defined on 32/200 items (undefined = an unresolvable factor, never a zero)
  contradiction source: {'no_relation_signal': 167, 'exact_single_cluster': 33}
  source run tree hash: a39434fa145c0fc98378ba8b -> a39434fa145c0fc98378ba8b
  SOURCE RUN UNCHANGED (hard rule H2 satisfied)
```

**Step 2 expected output:**

```text
E4 validation on 200 records (33 in the collision population)
  CM-score AUROC = 0.9412  95% CI [0.8529, 1.0000]  (n=32, 1 undefined-CM excluded)
  binary detector: TP=16 FP=0 TN=15 FN=2  (precision 1.000, recall 0.889, false-alarm 0.000)
    L1|correct=0: n=2 fires=0 (0.00)  flags={}
    L1|correct=1: n=15 fires=0 (0.00)  flags={}
    L7|correct=0: n=16 fires=16 (1.00)  flags={'stale_provision': 15, 'unresolvable_assertion': 1}
  factor ablation (AUROC drop):
    pin temporal=1.0: AUROC 0.5000 (drop 0.4412)
    pin jurisdiction=1.0: AUROC 0.9412 (drop 0.0000)
    pin contradiction=0.0: AUROC 0.9412 (drop 0.0000)
  base rate over 167 non-collision items: fire 0.533; correct-item alarm 0.000, wrong-item alarm 0.640
  GATE G4: PASS
```

**Reproducibility check.** Phase D is deterministic. Regenerate
it and confirm the two integrity anchors hash to the documented
values:

```powershell
python scripts\23_detect_warrant.py --run-id phaseA-laptop-v2-rejudged+ctx --out-suffix +warrant --force
python -m pytest tests\test_warrant.py -q
# then:
Get-FileHash -Algorithm SHA256 runs\phaseA-laptop-v2-rejudged+ctx+warrant\items.jsonl
# 915E8EFB197D8223767B39428E6CF0052D2CE9A907F1CC2192FCADE917D01587
Get-FileHash -Algorithm SHA256 runs\phaseA-laptop-v2-rejudged+ctx+warrant\warrant_validation.json
# 96041FAA3F538A534D5A560FFB4BD579DC2BD9D160D443B989F7633A04EFC7FE
```

(On macOS/Linux use `sha256sum`. `warrant_report.json` carries a
`generated_utc` timestamp, so only its *content* — not its byte
hash — is stable across runs.)

### 4.5 Phase G — offline only; the API pilot is on hold

Phase G needs no generation to reproduce its committed results. The audit, the
evaluation matrix and the deployment report are all offline:

```powershell
python -X utf8 scripts\40_audit_target_feasibility.py
python -X utf8 scripts\42_build_eval_matrix.py
python -X utf8 scripts\43_measure_deployment.py
```

`python -X utf8 scripts\44_phase_g_pilot.py --plan` is also free: it prints the
approved configuration and its cost ceiling and sends nothing.

The hosted-model paths are **on hold and are not part of this setup guide**.
`--smoke` and `--run` spend money, require an explicit approval hash, and will
refuse to start without one; the approved DeepSeek plan was never exercised
because the smoke check returned HTTP 402. Do not add an API key to any config
file, and do not run those flags to "check whether they work". See
[`PHASE-G.md`](PHASE-G.md#api-pilot-on-hold) and
[`runs/phaseG_pilot_status.json`](runs/phaseG_pilot_status.json) for the hold,
its reasons and the restart conditions.

## 5. What each Phase D artefact is

| Path | What it is |
|---|---|
| `runs/...+ctx+warrant/items.jsonl` | the 200 records, each now carrying the `warrant_*` fields (the frozen `+ctx` run is untouched) |
| `runs/...+ctx+warrant/warrant_report.json` | fire/silent counts, flag census, per-slice rates, contradiction sources, both tree hashes (operational log; carries a timestamp) |
| `runs/...+ctx+warrant/warrant_validation.json` | the E4 record: collision population, separation AUROC + CI, confusion matrix, factor ablation, base rate, Gate G4 verdict (**deterministic — the result-of-record**) |
| `runs/...+ctx+warrant/fig_warrant.png` / `.svg` | the three-panel E4 figure |
| `runs/...+ctx+warrant/meta.json` | run metadata, input hashes, as-of policy |

## 6. Update the main README about Phase D

The complete zip already contains the updated `README.md`. If
you are working from your own Phase C checkout, apply the
Phase D README changes with the supplied patch:

```powershell
cd D:\work\jurisuq_code
git apply ..\README_phaseD_patch.diff
# or, without git:
# patch -p1 < ..\README_phaseD_patch.diff
```

The patch makes exactly these edits to `README.md`:

1. **Badges** — "Implemented through" `Phase C` → `Phase D`;
   tests `111 passed` → `138 passed`; adds a
   `Gate G4-PASS` badge.
2. **Disclaimer** — notes Phase D inherits Phase C's
   legal-verification limit.
3. **Overview** — "three cumulative phases" → "four cumulative
   phases", adding the Phase D bullet.
4. **Contributes-today list** — adds the detector line and
   extends the artefact line to "Phase A–D".
5. **Implementation-status table** — adds the Phase D row
   (status: *Complete and frozen*; artefact of record
   `runs/phaseA-laptop-v2-rejudged+ctx+warrant/`).
6. **Scope boundary + warning** — "through Phase C" → "through
   Phase D"; the warning notes Phase D reads the store.
7. **Results at a glance** — a full **"Phase D: common-mode
   failure detector"** subsection: the four-tuple definition, the
   era-date rule, the validation table, the headline numbers
   (AUROC 0.941, CI [0.853, 1.000]), the factor-attribution
   table, the base-rate honesty line, and the Gate G4 PASS.
8. **Table of contents** — adds the Phase D result and
   reproduction entries.
9. **System architecture** — the mermaid diagram gains the
   Phase D detector and the `+ctx+warrant` sibling run, with its
   own tree-hash edge; the component map gains the *Warrant*
   layer (`jurisuq/warrant/`).
10. **Repository structure** — adds `configs/phase_d_warrant.json`,
    `PHASE-D.md`, `jurisuq/warrant/`, the
    `+ctx+warrant` run, `scripts/23…24`, `PHASE-D.md`,
    `PHASE-D.md`; test count 112 → 135.
11. **Requirements** — adds the Phase D row (stdlib-only).
12. **Quick verification** — `138 passed, 1 skipped`; adds the
    focused Phase D suite command.
13. **Reproducing the project** — adds a **"Phase D"**
    subsection with the two commands and the useful options.
14. **Data and artefact contracts** — adds the Phase D warrant
    record contract (the `warrant_*` fields) and three Phase D
    rows to the artefact registry.
15. **Configuration** — adds the Phase D config paragraph.
16. **Metrics and decision gates** — adds the **Gate G4**
    definition and its PASS result.
17. **Testing** — 112 → 135 tests, adds the `test_warrant.py`
    row, updates the core-environment result.
18. **Limitations** — adds a "Phase D detector scope"
    subsection.
19. **Troubleshooting** — adds four Phase D rows.
20. **Documentation** — adds the three Phase D docs and the
    Phase D config row.

If you prefer to edit by hand rather than apply the patch, the
authoritative Phase D prose already lives in
`PHASE-D.md`, `PHASE-D.md` and
`PHASE-D.md`; mirror those sections into the README
at the anchor points listed above.

After editing, commit on a new branch with a new run id for any
experimental output (the project's change-control rule):

```powershell
git checkout -b phase-d-common-mode-detector
git add .
git commit -m "feat(phase-d): common-mode failure detector, E4 validation, Gate G4 PASS"
```

## 7. Merging the drop zip into your own Phase C checkout

If you started from your own clone (not the complete zip):

```powershell
cd D:\work\jurisuq_code          # your existing Phase C checkout
# back up first (optional but recommended):
git checkout -b phase-d
# extract the drop ON TOP of the repo root:
Expand-Archive -Path ..\jurisuq_phaseD_drop.zip -DestinationPath . -Force
```

The drop contains the new Phase D files (a new `jurisuq/warrant/`
package, two new scripts, one new test module, one new config,
three new docs) **plus three one-line encoding-robustness fixes
to existing Phase C files** — `jurisuq/context/statute.py`,
`jurisuq/context/links.py` and `scripts/21_attach_context.py` —
so that every read on the Phase D path is explicit UTF-8. Those
three changes are backward-compatible (they alter no behaviour on
ASCII data; they only stop a Windows cp1252 locale from raising on
the non-ASCII text that Phase C itself writes). Nothing else is
overwritten. Then apply the README patch (§6), install nothing
new, and run §3 → §4.4.

Why this matters: Phase C writes its `+ctx` artefacts with
`ensure_ascii=False`, so `runs/…+ctx/items.jsonl` carries real
UTF-8 (curly quotes, and in some samples CJK text). The Phase A
source files are pure ASCII, which is why Phases A–C ran clean;
Phase D is the first phase to *read* the non-ASCII `+ctx` output,
so it is where a locale-default read raises. The fix is explicit
`encoding="utf-8"` on every read — already applied, so the plain
commands in §4 work without `python -X utf8`.

## 8. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError: jurisuq` | you ran from a subfolder | `cd` to the repo root (every script inserts the root into `sys.path`) |
| `138 passed` becomes `111 passed` | the drop was not extracted into the repo root | re-extract the drop so `jurisuq/warrant/` sits next to `jurisuq/context/` |
| `ERROR: no such run: …+ctx/items.jsonl` | Phase D was pointed at an unpacked run | run Phase C's `21_attach_context.py` first, or point at the shipped `phaseA-laptop-v2-rejudged+ctx` |
| `ERROR: <out> already exists` | re-running a shipped suffix | use a new `--out-suffix`, or `--force` for a deliberate replacement |
| Detector fires on **both** slices | `--as-of-policy fixed` was used | that is the deliberate ablation; use the default `era` policy |
| `CM defined on 0/200` | the source run has no `asserted_keys` | detect on a Phase A run of record, not an empty tree |
| `SOURCE RUN CHANGED` (exit 2) | something wrote into the frozen `+ctx` run | restore it from git / re-clone; investigate before trusting the report |
| `Get-FileHash` shows a different value than documented | you are hashing `warrant_report.json` | that file carries a timestamp; the deterministic anchors are `items.jsonl` and `warrant_validation.json` |
| `git apply` fails on the README patch | your README already diverged | apply the patch to the Phase C README, or copy the Phase D sections by hand from `PHASE-D.md` |
| `UnicodeDecodeError: 'charmap' codec can't decode byte 0x9d` | Windows' cp1252 locale default reading the UTF-8 `+ctx` artefacts (they contain curly quotes and CJK text) | **fixed in this drop** — every Phase D/C read is now explicit UTF-8, so the plain command works. Re-extract the updated drop zip. `python -X utf8` was only a workaround. |

## 9. Where Phase D sits in the roadmap

Phase D is module **M7**; Phase E is the **M8** uncertainty estimator. Phase E consumes the stored `warrant_warranted_agreement`, `warrant_common_mode_score`, and `warrant_contradiction_mass` fields. It never recomputes `(A, T, J, K)`, `W`, or `CM`. If any required legal field is missing, null, non-finite, or invalid, the record takes the documented sample-only `u_prov` fallback; no null becomes zero. The scorer is label-blind, while the separate fit and validation scripts access correctness labels only for training and evaluation respectively. The score is uncalibrated, and the current G5 status is NOT_EVALUABLE because the target L7 population has only one correctness class.

See [`PHASE-E.md`](PHASE-E.md) for the full interface, field definitions,
actual sandbox run results, and caveats.

## 10. Run Phase E (M8)

Run these commands from the repository root in PowerShell. Phase E uses the already-generated Phase D run; do not rerun Phase D unless its input artefacts are missing. It does not call LM Studio and needs no additional package beyond the project's existing environment (`pytest` is used for tests).

```powershell
# Optional: activate the existing environment.
.\.venv\Scripts\Activate.ps1

# Mandatory focused test.
python -X utf8 -m pytest tests\test_uncertainty.py -q

# Mandatory: fit the model on legal-complete development records only.
python -X utf8 scripts\25_fit_uncertainty.py --run-id "phaseA-laptop-v2-rejudged+ctx+warrant" --model-out runs\phaseE_model.json

# Mandatory: score into a distinct sibling run; this command does not read correctness labels.
python -X utf8 scripts\26_estimate_uncertainty.py --run-id "phaseA-laptop-v2-rejudged+ctx+warrant" --model runs\phaseE_model.json --out-suffix "+uq"

# Mandatory: held-out E5 comparison and G5 status.
python -X utf8 scripts\27_validate_uncertainty.py --run-id "phaseA-laptop-v2-rejudged+ctx+warrant+uq"

# Optional: inspect output metadata and metrics.
Get-Content runs\phaseA-laptop-v2-rejudged+ctx+warrant+uq\meta.json -Raw
Get-Content runs\phaseA-laptop-v2-rejudged+ctx+warrant+uq\uq_validation.json -Raw

# Mandatory full regression check after the Phase E changes.
python -X utf8 -m pytest -q
```

The fit command creates `runs/phaseE_model.json`; scoring creates `runs/phaseA-laptop-v2-rejudged+ctx+warrant+uq/` with `items.jsonl`, `meta.json`, and a copy `uq_model.json`; validation adds `uq_validation.json`. If the `+uq` output already exists, use `--force` on script 26 to replace only that generated Phase E sibling output.

The checked-in pilot produces 32 `legal_aware` and 168 `sample_only_fallback` rows. This can vary if the local Phase D files differ. The prior sandbox execution reported 149 passed, 1 skipped (the torch-gated test). A historical Windows PowerShell execution in the project `.venv` on 2026-10-21 reported 147 passed in 36.84s; the latest post-change Windows PowerShell execution in the same `.venv`, using `.\.venv\Scripts\python.exe -X utf8 -m pytest -q`, reported 149 passed in 7.58s. These are separate environment-specific executions. The current held-out L7 slice is single-class, so AUROC is undefined and G5 must report NOT_EVALUABLE—not PASS. The L1/control comparison is exploratory; it does not establish universal performance.
