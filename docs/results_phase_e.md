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
