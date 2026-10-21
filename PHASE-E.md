# Phase E — legal-aware uncertainty estimation (M8)

Phase E turns the Phase A sample statistics and stored Phase D warrant outputs into a per-answer uncertainty score. It is an incremental, label-separated stage: fitting is supervised on a development partition; scoring is a separate label-blind command; validation reads correctness labels only after scores have been written.

## 1. Scope and evidence boundary

The technical guide defines Phase E as a small learned monotone model, fitted on development data, over the sample-only and legal-structure signals. The implementation follows that design with a pure-Python projected logistic model and pairwise interactions. It does **not** claim calibration, general legal reliability, or a passed G5.

The current Phase D run stores `warrant_warranted_agreement`, `warrant_common_mode_score`, and `warrant_contradiction_mass`; the first two are already Phase D's computed `W` and `CM`. Phase E consumes those exact fields. It never re-derives `A`, `T`, `J`, `K`, `W`, or `CM`.

The shipped `+ctx+warrant` run marks its representation `exact_key` and does not contain the Phase B `typed_stats` block. Accordingly, this implementation's `u_prov` is the normalized Phase A `methods.prov_se` exact provision-key entropy, **not** a newly computed typed-cluster entropy. Once a Phase B typed-statistics field is registered in the run schema, a later version may use it; this drop does not invent or reconstruct one.

## 2. Components and score

For each record, the feature extractor reads:

| Component | Definition used here | Source |
|---|---|---|
| `u_prov` | `methods.prov_se / log2(n_samples)` | Phase A provision-key entropy; sample-only baseline |
| `u_text` | `methods.disc_se / log2(n_samples)` | Phase A discrete semantic entropy |
| `u_warrant` | `1 - warrant_warranted_agreement` | Stored Phase D `W`; the deficit is the guide's definition |
| `u_cm` | `max(0, warrant_common_mode_score)` | Stored Phase D `CM`; positive common-mode residue per §28.5 |
| `u_contra` | `warrant_contradiction_mass` | Stored Phase D `K` |

The model uses all five main effects and every pairwise product. A projected batch logistic fit constrains every coefficient to be non-negative. Therefore increasing any one component while holding the others fixed cannot reduce the model's score. The target during fit is `error = 1 - majority_correct`; larger `uq_uncertainty` means higher estimated error risk.

The sigmoid output is an **uncalibrated monotone risk score**, not a calibrated probability. Phase F owns calibration. For a record where any required sample feature or stored legal field is absent, null, non-finite, or outside its valid range, no learned legal-aware score is produced for that record. The explicit fallback is `u_prov` (normalized sample-only provision entropy). If `u_prov` itself is unavailable, `uq_uncertainty` is `null` and mode is `unscorable`. A missing factor is never converted to zero.

`warrant_temporal_validity`, `warrant_jurisdiction_fit`, flags, and the modal key are preserved from the input record but not used to recompute the Phase D tuple. The estimator uses only the stored `W`, `CM`, and `K` outputs for its legal components.

## 3. Label boundary and reproducibility

- `scripts/25_fit_uncertainty.py` is the **training-only** path. It reads `majority_correct` solely for fitting and recodes it to the error target. It makes a deterministic 80/20 SHA-256 split by the frozen data's `pair_id`, so L1/L7 matched siblings remain in the same partition.
- `scripts/26_estimate_uncertainty.py` is the **label-blind scoring** path. It explicitly strips correctness/gold fields before calling the feature extractor and only writes to a new sibling run. It checks the input tree hash against the model and before/after scoring.
- `scripts/27_validate_uncertainty.py` is the **offline evaluation** path. It reads `majority_correct` only to compute held-out metrics and never refits the model.

The split seed is `phaseE-v1`; test fraction is 0.20. The same input data and files produce the same split, fitted weights, and scores. No LM Studio endpoint or model downloads are required.

## 4. Windows PowerShell workflow

First overlay the ZIP into the existing checkout (adjust `$zip` only if your download is elsewhere), then run from the repository root. `-Force` permits the two updated documentation files to be replaced; no Phase A/B/C/D files are overwritten. Phase E does not require reinstalling the project's dependencies.

```powershell
$zip = Join-Path $HOME 'Downloads\jurisuq_phaseE_drop.zip'
Expand-Archive -LiteralPath $zip -DestinationPath 'E:\PROJECTS\JURIS-UQ\jurisuq_code' -Force
Set-Location 'E:\PROJECTS\JURIS-UQ\jurisuq_code'
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation, use this only for the current shell and retry:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

Verify `pytest` is present; install only it if the import fails:

```powershell
python -c "import pytest; print('pytest', pytest.__version__)"
# Only if the command above fails:
python -m pip install pytest
```

Mandatory focused regression test:

```powershell
python -X utf8 -m pytest tests\test_uncertainty.py -q
```

Mandatory Phase E commands, in order:

```powershell
python -X utf8 scripts\25_fit_uncertainty.py --run-id "phaseA-laptop-v2-rejudged+ctx+warrant" --model-out runs\phaseE_model.json
python -X utf8 scripts\26_estimate_uncertainty.py --run-id "phaseA-laptop-v2-rejudged+ctx+warrant" --model runs\phaseE_model.json --out-suffix "+uq"
python -X utf8 scripts\27_validate_uncertainty.py --run-id "phaseA-laptop-v2-rejudged+ctx+warrant+uq"
```

If the output run already exists after an earlier attempt, deliberately replace only that Phase E output with:

```powershell
python -X utf8 scripts\26_estimate_uncertainty.py --run-id "phaseA-laptop-v2-rejudged+ctx+warrant" --model runs\phaseE_model.json --out-suffix "+uq" --force
```

Optional inspection and mandatory full regression suite:

```powershell
Get-Content runs\phaseA-laptop-v2-rejudged+ctx+warrant+uq\meta.json -Raw
Get-Content runs\phaseA-laptop-v2-rejudged+ctx+warrant+uq\uq_validation.json -Raw
python -X utf8 -m pytest -q
```

The full suite is the regression check for all earlier phases. The prior sandbox execution was `149 passed, 1 skipped`; a historical Windows PowerShell execution in the project `.venv` on 2026-10-21 reported `147 passed in 36.84s`; and the latest post-change Windows PowerShell execution in the same `.venv`, using `.\.venv\Scripts\python.exe -X utf8 -m pytest -q`, reported `149 passed in 7.58s`. These are separate environment-specific executions.

### Optional degradation check when Phase D is absent

The same pipeline can be run on a Phase A source run. Since it has no `warrant_*` fields, fitting produces no legal-aware head and every record uses the sample-only fallback. Use a distinct model file and output suffix:

```powershell
python -X utf8 scripts\25_fit_uncertainty.py --run-id "phaseA-laptop-v2-rejudged" --model-out runs\phaseE_sample_only_model.json
python -X utf8 scripts\26_estimate_uncertainty.py --run-id "phaseA-laptop-v2-rejudged" --model runs\phaseE_sample_only_model.json --out-suffix "+uq"
python -X utf8 scripts\27_validate_uncertainty.py --run-id "phaseA-laptop-v2-rejudged+uq"
```

This path does not rerun or synthesize Phase D. On the workspace check, it emitted 200 sample-only fallback scores and left the Phase A source tree unchanged.

## 5. Output contract

The fit command writes `runs/phaseE_model.json`. Scoring writes a new run at:

`runs/phaseA-laptop-v2-rejudged+ctx+warrant+uq/`

Files written there:

- `items.jsonl` — source records copied to a sibling run with `uq_components`, `uq_uncertainty`, `uq_score_mode`, `uq_score_semantics`, `uq_fallback_reason`, and model hash/provenance fields appended.
- `meta.json` — mode counts, fallback reasons, source-tree hashes, and label-blind scoring statement.
- `uq_model.json` — exact model and split metadata used for this scoring run.
- `uq_validation.json` — held-out metrics, bootstrap comparison, ablations, G5 status, and limitations; produced by script 27.

Expected mode counts on the shipped Phase D run: 32 `legal_aware`, 168 `sample_only_fallback`, and 0 `unscorable`. They depend on the exact input artifacts; the scripts print the actual counts.

## 6. Gate G5 and honest interpretation

The guide's E5/G5 criterion compares against the strongest Phase A control-slice baseline (provision-level entropy, AUROC 0.766) and requires an improvement interval excluding zero. The guide also says that no target-slice AUROC claim is made until both correctness classes exist on that slice. The current L7 run has only incorrect majority answers, so its AUROC is undefined. Consequently the current pilot must report **G5 NOT_EVALUABLE**, not PASS. The control-slice comparison remains reported as a held-out exploratory result.

On the current checked-in run the pair-grouped holdout has 44 items (22 per slice); L7 has 22 incorrect and zero correct records. Results and uncertainty are recorded in [`docs/results_phase_e.md`](docs/results_phase_e.md). These are properties of the one existing run and do not establish general performance.

## 7. Limitations and next data needs

1. Only 32 of 200 records have all stored legal components needed for a learned legal-aware score; the other 168 take the explicit sample-only fallback.
2. The fitted legal head has a small development population, and the held-out legal-aware subset is very small. Component ablations are descriptive only; confirmatory refit ablations belong in Phase H.
3. The current D run uses exact provision keys, not typed Phase B cluster statistics. `u_prov` is therefore an exact-key Phase A entropy proxy.
4. The synthetic matched slice has no correct L7 majority answers. Build a target population containing both classes before claiming target-slice AUROC or evaluating the complete G5 criterion.
5. Scores are not calibrated; they must not be used as probabilities or decision thresholds before Phase F.
6. The Phase C statute and crosswalk verification caveats remain in force.
