# Phase E — legal-aware uncertainty estimation (M8)

Phase E turns the Phase A sample statistics and stored Phase D warrant outputs into a per-answer uncertainty score. It is an incremental, label-separated stage: fitting is supervised on a development partition; scoring is a separate label-blind command; validation reads correctness labels only after scores have been written.

## Field and script registry

| Field | Type | Producer | Consumer | Status |
|---|---|---|---|---|
| `clusters` | `list[int]` | `scripts/13_attach_typed.py` | Phase D, E | registered |
| `cluster_provisions` | `list[str]` | `scripts/13_attach_typed.py` | Phase D | registered |
| `relation_matrix` | `list[list[str]]` | `scripts/13_attach_typed.py` | Phase D (K) | registered |
| `relation_scores` | `list[list[float]]` | `scripts/13_attach_typed.py` | audit / figures | registered |
| `typed_stats` | object | `scripts/13_attach_typed.py` | Phase E (`u_prov`) | registered |
| `scripts/13_attach_typed.py` | CLI script | Phase B | Phase D, E | registered |
| `scripts/23_detect_warrant.py --cluster-source {auto,exact,typed}` | CLI flag; default `auto` | Phase D | Phase D evaluation | registered; pending Block 4 |
| `scripts/23_detect_warrant.py --contradiction-source {auto,rule,model,none}` | CLI flag; default `auto` | Phase D | Phase D evaluation | registered; Block 4 |

Alias decision: retain the shipped fields
`warrant_observed_agreement`, `warrant_warranted_agreement`,
`warrant_common_mode_score`, and `uq_uncertainty`. Their master-guide aliases
are `warrant_A/T/J/K`, `warrant_W`, `common_mode`, and `u_combined`,
respectively; no renaming is performed.

Block 5 evaluates two registered provision-entropy variants side by side:
`typed_stats.entropy_norm` and the like-for-like Phase A form
`methods.prov_se / log2(n_samples)`. The latter is directly comparable to
the frozen pilot; neither variant is selected as definitive.

Threat to validity: the frozen slice has zero gold/trap co-occurrence across
200 items (L1 gold-only 69 / neither 31; L7 trap-only 52 / neither 48).
The relation model's false-merge risk across the IPC-to-BNS transition is
therefore unmeasured by this benchmark.

## 1. Scope and evidence boundary

The technical guide defines Phase E as a small learned monotone model, fitted on development data, over the sample-only and legal-structure signals. The implementation follows that design with a pure-Python projected logistic model and pairwise interactions. It does **not** claim calibration, general legal reliability, or a passed G5.

The current Phase D run stores `warrant_warranted_agreement`, `warrant_common_mode_score`, and `warrant_contradiction_mass`; the first two are already Phase D's computed `W` and `CM`. Phase E consumes those exact fields. It never re-derives `A`, `T`, `J`, `K`, `W`, or `CM`.

The Block 5 input is the typed Phase D run and contains the Phase B
`typed_stats` block. The evaluation fits two separate models: typed
`typed_stats.entropy_norm`, and the normalized Phase A
`methods.prov_se` exact provision-key entropy retained for like-for-like
comparison with the frozen pilot. No variant is selected as definitive.

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

On the current checked-in run the pair-grouped holdout has 44 items (22 per slice); L7 has 22 incorrect and zero correct records. The complete results and uncertainty record is included below. These are properties of the one existing run and do not establish general performance.

## 7. Limitations and next data needs

1. Only 32 of 200 records have all stored legal components needed for a learned legal-aware score; the other 168 take the explicit sample-only fallback.
2. The fitted legal head has a small development population, and the held-out legal-aware subset is very small. Component ablations are descriptive only; confirmatory refit ablations belong in Phase H.
3. The current D run uses exact provision keys, not typed Phase B cluster statistics. `u_prov` is therefore an exact-key Phase A entropy proxy.
4. The synthetic matched slice has no correct L7 majority answers. Build a target population containing both classes before claiming target-slice AUROC or evaluating the complete G5 criterion.
5. Scores are not calibrated; they must not be used as probabilities or decision thresholds before Phase F.
6. The Phase C statute and crosswalk verification caveats remain in force.

---

## Complete experimental results and validation record

### Merged record: `PHASE-E.md`

# Phase E pilot results — M8 legal-aware uncertainty estimation

## Run identity and separation

- Input: `runs/phaseA-laptop-v2-rejudged+ctx+warrant/` (the Phase D run of record).
- Output: `runs/phaseA-laptop-v2-rejudged+ctx+warrant+uq/`.
- Model: `runs/phaseE_model.json`.
- Split: deterministic SHA-256 by the frozen data's `pair_id`, seed `phaseE-v1`, 20% test; matched L1/L7 siblings stay in the same partition.
- Training labels: `majority_correct` is accessed only in script 25 and recoded to `error = 1 - majority_correct`.
- Scoring labels: script 26 strips correctness/gold fields before feature extraction; source tree hash was identical before and after scoring.
- Validation labels: script 27 reads `majority_correct` only on the held-out test records.
- No LM Studio call or new external dependency was used. A separate degradation check on `phaseA-laptop-v2-rejudged` (no Phase D fields) produced no legal-aware head, 200 sample-only fallback scores, and an unchanged source tree.

For the current Phase E `+uq` run, the source tree hash before and after scoring was `12a1039b4a7b4650f356431f18c3ceec719d3a47ad331b954b20f7e2463976f3`. This is the source tree hash for that run, not a universal project hash; Phase D's timestamped operational report can make full-tree hashes generation-specific.

## Actual sandbox execution

| Measurement | Observed |
|---|---:|
| Total input records | 200 |
| Development / held-out records | 156 / 44 |
| Legal-complete development records used to fit | 29 (15 incorrect, 14 correct) |
| Records scored legal-aware | 32 |
| Sample-only fallback / unscorable | 168 / 0 |
| Holdout L1 | 22 (7 correct, 15 incorrect) |
| Holdout L7 | 22 (0 correct, 22 incorrect) |
| L1 Phase E operational-score AUROC | 0.9000 |
| L1 normalized provision-entropy AUROC | 0.8714 |
| Paired bootstrap AUROC difference (Phase E − baseline) | +0.0286 |
| Paired bootstrap 95% interval (2,000 draws, seed 0) | [−0.0417, +0.1500] |
| L7 AUROC | Undefined (one correctness class) |
| Legal-aware-only heldout subset | n=3 (1 correct, 2 incorrect), AUROC 0.7500 |
| Gate G5 | **NOT_EVALUABLE** |
| Focused Phase E tests (supplied pre-change run) | 11 passed |
| Focused Phase E tests (final, including metadata tests) | 13 passed |
| Full regression suite (sandbox environment) | **149 passed, 1 skipped** |
| Full regression suite (historical Windows PowerShell, project `.venv`, 2026-10-21) | **147 passed in 36.84s** |
| Full regression suite (latest Windows PowerShell post-change, project `.venv`, 2026-10-21) | **149 passed in 7.58s** |

The control-slice point AUROC is above the Phase A reference 0.766, but the bootstrap interval for improvement over the provision-entropy baseline includes zero. More importantly, the held-out target slice has no correct answers, so target-slice AUROC is undefined and the design guide explicitly disallows a G5 claim until both target correctness classes exist. Therefore this is **not** a G5 pass. It is also not evidence that Phase E improves general legal QA.

## Score and fallback behavior observed

The stored Phase D `W`, `CM`, and `K` fields were consumed without recomputing the Phase D tuple. Where all required stored components and sample features were valid, the learned monotone score was emitted with `uq_score_mode = legal_aware`. For the other 168 records, at least one legal input was unavailable or null, so the score fell back to normalized provision entropy (`uq_score_mode = sample_only_fallback`). No record was assigned zero for an unresolved legal factor. All 200 records were scoreable because the sample-only fallback was available.

The current Phase D records use `exact_key` representation and do not store Phase B typed-cluster statistics. Thus `u_prov` is the Phase A provision entropy, normalized by `log2(n_samples)`; it is not a Phase B typed-cluster entropy.

## Ablation and limits

Only three held-out records received a legal-aware score in this split. Coefficient-removal ablations on that subset returned AUROC 0.75 for the full score and each tested removal; the sample contains only 1 correct and 2 incorrect records, so these findings are descriptive only and are not strong evidence about component contribution. The drops are recorded as descriptive only in `uq_validation.json`, not as evidence that components do or do not help. Confirmatory component ablations should use a larger development/test population and the Phase H plan.

The score is an uncalibrated risk ranking, not a probability of error or reliability. Phase F calibration is not implemented here. The synthetic 200-item benchmark, 7B checkpoint, Phase C statute coverage/verification limits, and single-class L7 outcome sharply constrain interpretation.

## Block 5b — attribution-controlled evaluation

Block 5b is retained in new sibling runs:

- `phaseE-5b-pooled-typed_model.json` and `...+uq-5b-pooled-typed`
- `phaseE-5b-pooled-exact_model.json` and `...+uq-5b-pooled-exact`
- `phaseE-5b-L1-typed_model.json` and `...+uq-5b-L1-typed`
- `phaseE-5b-L1-exact_model.json` and `...+uq-5b-L1-exact`

These outputs do not modify the frozen pilot or the earlier Block 5 runs.
Missing legal inputs use the fitted degradation of the sample-only submodel
(intercept, `u_prov`, `u_text`, and `u_prov*u_text`); they are labelled
`sample_only_degraded`, not raw-entropy fallbacks. Each new scoring run has
187 `legal_aware`, 13 `sample_only_degraded`, 0 `sample_only_fallback`, and
0 `unscorable` records.

The pooled split is 156 development / 44 holdout; the L1-only split is 78 /
22 and evaluates only L1. Within-slice holdout results are:

| Fit / variant | Slice | AUROC | AUPRC | nAURC | risk@50% | baseline AUROC |
|---|---|---:|---:|---:|---:|---:|
| pooled / typed | L1 (22) | 0.6238 | 0.7243 | 0.3963 | 0.5455 | 0.6381 |
| pooled / exact | L1 (22) | 0.6905 | 0.7568 | 0.5054 | 0.5455 | 0.8714 |
| L1-only / typed | L1 (22) | 0.5714 | 0.7129 | 0.3358 | 0.5455 | 0.6381 |
| L1-only / exact | L1 (22) | 0.8714 | 0.9349 | 0.7078 | 0.4545 | 0.8714 |

For pooled runs, L7 is 22/22 incorrect: AUROC and nAURC are undefined,
while AUPRC and risk@50% are both 1.0. L1-only runs have no L7 evaluation
population. Paired AUROC score-minus-baseline differences are -0.0143
(pooled typed, 95% CI [-0.1458, 0.0882]), -0.1810 (pooled exact,
[-0.5000, 0.0000]), -0.0667 (L1-only typed, [-0.3158, 0.1880]), and
0.0000 (L1-only exact, [0.0000, 0.0000]). G5 is NOT_EVALUABLE in every
case; no variant is selected.

For the pooled exact-key L1 holdout, 20 records were legal-aware and 2 were
degraded fallbacks; both fallbacks were incorrect. On the same 20 legal-aware
records, learned-score AUROC was 0.6868 versus exact `u_prov` 0.8626. On
all 22 L1 records after degradation rescaling, the values were 0.6905 and
0.8714. This remains a negative result. Typed entropy is exactly zero on
106/200 records versus 33/200 for exact keys; all 32 legal-aware records in
the frozen pilot had exact `u_prov=0`, explaining its zero fitted provision
weight.

## Block 5c — structural G5 finding

On the frozen 200-item instrument, the temporal factor is constant within each
slice: `T=1.0` on 94 of 94 resolvable L1 records and `T=0.0` on 80 of 81
resolvable L7 records. With `J=1` and `K` approximately zero, warranted
agreement collapses to `W=A` on L1 and `W=0` on L7. Consequently `u_cm` is
identically zero on the L1 control slice, while `u_warrant` reduces to a
function of observed agreement `A`, which `u_prov` already encodes.

The legal-aware components therefore have no within-slice information:
there is zero variance on L1, and L7 has only one correctness class. This
explains why the L1-only fit reproduces the sample-only ranking exactly
(AUROC `0.8714` versus baseline `0.8714`; paired difference `0.0000`,
interval `[0.0000, 0.0000]`) and why the pooled exact fit is worse within L1
(AUROC `0.6905`): it uses `u_warrant` and `u_cm` as slice indicators.

This is a structural impossibility result for the current instrument. Gate G5
cannot be satisfied by any estimator, hyperparameter, or ablation on this
instrument. It requires an evaluation population in which `T` varies within
a slice: a slice with both correctness classes on which the detector both
fires and stays silent. Building that population is Phase G work and is the
sole remaining blocker for G5.

Block 6 is therefore ordered as a representation-trustworthiness check, not
as a G5 rescue attempt. Typed entropy is exactly zero on 106/200 records
versus 33/200 under exact keys, and the typed relation model's
`DIFFERENT_PROVISION` recall is `0.00`. Block 6 can assess or improve
confidence in the typed representation, but it cannot create the missing
within-slice variance in `T`; the expensive 13/23/24/25/26/27 chain must be
rerun only once, after the two-class target population exists.

## Reproduction commands

From the repository root:

```powershell
python -X utf8 -m pytest tests\test_uncertainty.py -q
python -X utf8 scripts\25_fit_uncertainty.py --run-id "phaseA-laptop-v2-rejudged+ctx+warrant" --model-out runs\phaseE_model.json
python -X utf8 scripts\26_estimate_uncertainty.py --run-id "phaseA-laptop-v2-rejudged+ctx+warrant" --model runs\phaseE_model.json --out-suffix "+uq"
python -X utf8 scripts\27_validate_uncertainty.py --run-id "phaseA-laptop-v2-rejudged+ctx+warrant+uq"
python -X utf8 -m pytest -q
```

`uq_validation.json` is the machine-readable source for the E5 holdout metrics and G5 status.

## Block 6b — corrected typed-input rehearsal

Blocks 4 and 5 are superseded, not deleted. Their reported numbers were
computed under relations_v1 (tau 0.45, DIFFERENT_PROVISION F1 0.00);
superseded by relations_v2; see Block 6b.

The rehearsal used new sibling runs
`phaseA-laptop-v2-rejudged+ctx-r2+typed-v2-r3` and
`phaseA-laptop-v2-rejudged+ctx-r2+typed-v2-r3+warrant-v2-r3`, followed by
four new Phase E model/output pairs. No prior run or report was overwritten.
The typed cluster distribution was 1: 33, 2: 54, 3: 39, 4: 38, 5: 14,
6: 13, 7: 7, and 9: 2. Typed collisions therefore total 33 and equal
the exact-key collision count of 33.

The corrected Phase D/G4 result is AUROC 0.9412, 95% CI [0.8529, 1.0000],
with TP=16, FP=0, TN=15, FN=2. Ablations are: T pinned to 1, AUROC
0.5000 (drop 0.4412); J pinned to 1, AUROC 0.9412 (drop 0.0000); and
K pinned to 0, AUROC 0.9412 (drop 0.0000). `cm_defined` is 172/200.

The four provision-entropy/fitting variants all retain G5 `NOT_EVALUABLE`
because the held-out L7 target slice remains single-class. Results below
are AUROC for the Phase E score versus the sample-only baseline:

| Fit / variant | L1 AUROC | L1 baseline AUROC | L7 AUROC | Paired delta (95% CI) |
|---|---:|---:|---:|---:|
| pooled / typed | 0.6857 | 0.8571 | undefined | -0.1714 [-0.3932, 0.0000] |
| pooled / exact | 0.6857 | 0.8714 | undefined | -0.1857 [-0.4063, -0.0167] |
| L1-only / typed | 0.8095 | 0.8571 | not evaluated | -0.0476 [-0.1429, 0.0139] |
| L1-only / exact | 0.8095 | 0.8714 | not evaluated | -0.0619 [-0.1667, 0.0000] |

The Block 5c structural finding is confirmed on corrected typed inputs:
T=1 on all 93 resolvable L1 records, and T=0 on 78 of 79 resolvable L7
records (T=1 on the remaining one). `u_cm` is zero on all resolvable L1
records, so the missing within-slice variance remains structural rather than
an estimator or representation artifact.

This remains a rehearsal; Phase F has not started.

### Why typed clustering cannot differ from exact-key on this instrument

No item co-asserts IPC and BNS within its ten stored samples: 182 items are
IPC-only, 3 are IPC plus no provision, and 15 are BNS-only. All 10
`successor_of` rows in `data/relations/crosswalk_v1.jsonl` are IPC -> BNS.
Across 962 within-item co-occurrence pairs (368 distinct pairs), 0 are
`successor_of`, 19 are `different_offence`, and 943 (98%) are unknown to the
crosswalk.

The typed cluster-count distribution is 33/54/39/38/14/13/7/2, while the
exact-key distribution is 33/53/39/38/15/13/7/2. They match on 199/200
items. G2's typed-clustering criterion is structurally unsatisfiable on this
instrument, independent of relation-model quality.
