# JURIS-UQ — Phase F: calibration and the decision layer (M9, M10)

Phase F turns a ranking into a decision. Phase E produced an **uncalibrated risk
score**; Phase F (M9) converts it into a calibrated probability that the
returned majority answer is correct, and (M10) applies a loss-based policy that
answers, verifies or abstains with a reason. It implements master-guide §20 and
gate **G6** exactly as specified there: isotonic regression as the default map,
Platt scaling as the small-stratum fallback, grouped K-fold grouped by offence
cluster and slice, ACE with five bins as the primary metric, thresholds derived
from a harm-weighted loss rather than a coverage target, and a conformal layer
with its exchangeability assumption stated.

Nothing here recomputes a Phase A–E quantity. Phase F reads
`uq_uncertainty` and the Phase D flags from a stored run, writes a new sibling
run, and never writes into its source.

## Status: implemented and evaluated — Gate G6 is **NOT_MET**

| Item | State |
|---|---|
| M9 calibrator (isotonic + Platt, grouped cross-fitting) | implemented, tested, fitted |
| M10 decision layer (answer / verify / abstain, harm-weighted) | implemented, tested, applied |
| Conformal coverage layer (split-conformal, finite-sample corrected) | implemented, tested, evaluated |
| E6 evaluation on the held-out partition | executed on two Phase E variants |
| Gate G6 | **NOT_MET** — 2 of 4 conditions fail, 1 stratum unevaluable |
| Post-merge follow-up (4 experiments) | executed; see [`PHASE-F-FOLLOWUP.md`](PHASE-F-FOLLOWUP.md) |

Phase F is **not** complete in the sense the guide means by a phase gate. The
machinery is complete and reproducible; the *claim* the gate exists to license
is not supported by this instrument. The two failures are reported in §7 and
are not repairable by changing a threshold after the fact.

### Follow-up correction (supersedes the conformal figures below)

An audit of the numbers in §6 found that the conformal threshold was computed
from the same 22 holdout items its coverage was then measured on. The corrected
pipeline takes the threshold from the 78 development items' grouped cross-fitted
probabilities and report both a Wald tolerance and a Clopper–Pearson bound. The
corrected run is the **new sibling** `…+uq-exact+cal-r2`; the original `+cal`
run is preserved unchanged and is **not** replaced. Coverage moves from 0.8636
to 0.6818 (15/22), the threshold from 0.3855 to 0.4702, and **the G6 verdict does
not change: it is NOT_MET in both.**

Three further experiments (within-slice refitting, calibration-map selection
under a pre-registered rule, and topic-clustered uncertainty intervals) are
recorded in [`PHASE-F-FOLLOWUP.md`](PHASE-F-FOLLOWUP.md). None of them changes a
gate constant or produces a pass. The §6 and §7 tables below are retained as the
historical record of the as-merged run.

### Dependency finding (read this before extending Phase F)

Phase F depends on Phase E scores and on a stratum that contains both
correctness classes. On the frozen run:

* `L1` development: 78 records, 36 correct / 42 incorrect → **calibratable**;
* `L7` development and holdout: 100 records, **0 correct** → **not
  calibratable**. A calibration map needs both classes; none is imputed, and
  `p_reliable` is `null` for all 100 L7 records.

So the L7 half of G6 is structurally unevaluable, exactly as G5 was
(`uq_validation.json` carries `target_slice_both_classes_present = false`). The
safest next step for a *passing* G6 is therefore **Phase G's structural
requirement** (§21.1: a target slice with both correctness classes), not another
Phase F experiment. Phase F was built anyway because it is deterministic,
seconds to run, and its L1 half is evaluable; the result of that evaluation is a
negative one, and it is reported as such.

## Compute and cost

Stdlib-only, like Phases C, D and E: no torch, no transformers, no model
downloads, no network. The three Phase F commands together run in **under one
second** on CPU. The project remains at zero spend: no paid API calls, no
subscriptions, no billing. The Phase E scores consumed here come from the frozen
local `qwen2.5-7b-instruct` run; Phase F starts no generation.

## 1. What is in this drop

```
jurisuq/calibration/
├── __init__.py        # Phase F exports
├── maps.py            # IsotonicMap (PAV) + PlattMap (smoothed logistic), monotone by construction
├── splits.py          # grouped K-fold by (slice, topic) + cross-fitted predictions
├── metrics.py         # ACE 5-bin (primary), ECE 10-bin, Brier, log-loss, reliability, selective risk
├── policy.py          # DecisionPolicy (M10), harm classes, user-facing reason strings
├── conformal.py       # split-conformal threshold, finite-sample correction, coverage tolerance
└── evaluate.py        # fit_strata, attach_probabilities, Gate G6, label-blind static check
scripts/
├── 29_fit_calibration.py     # fit maps on the development partition -> runs/phaseF_calibration_model.json
├── 30_apply_policy.py        # label-blind scoring + decisions -> sibling run +cal
└── 31_validate_calibration.py# held-out E6 + Gate G6 -> calibration_report.json
configs/
└── phase_f_calibration.json  # split, method rule, policy costs, gate thresholds
tests/
├── test_calibration.py       # 39 tests (maps, folds, metrics, conformal, G6 logic, interface rule)
└── test_policy.py            # 18 tests (thresholds, actions, reasons, harm classes)
PHASE-F.md                    # this file
```

## 2. Registered fields (Phase F writes only these)

| Field | Type | Meaning | Producer |
|---|---|---|---|
| `p_reliable` | `float \| null` | calibrated P(returned majority answer correct); `null` when the stratum is uncalibratable | `scripts/30_apply_policy.py` |
| `calibration_status` | `str` | `calibrated` / `undefined_stratum_not_calibrated` / `no_score` | same |
| `calibration_stratum` | `str` | the slice the map was fitted for | same |
| `calibration_method` | `str \| null` | `isotonic` or `platt` for that stratum | same |
| `harm_class` | `str` | consequence class of the question's offence cluster (Phase C vocabulary) | same |
| `action` | `str` | `answer` / `verify` / `abstain` | same |
| `action_trigger` | `str` | the rule that produced the action | same |
| `action_reason` | `str` | user-facing explanation naming the flag and the as-of date | same |
| `action_thresholds` | `object` | the thresholds in force for that harm class | same |
| `calibration_model_sha256` | `str` | provenance of the applied maps | same |

Master-guide alias: `p_reliable` is the guide's calibrated reliability; there is
no rename. `action`/`action_reason` are the guide's decision fields unchanged.

### The query path is label-blind

`scripts/30_apply_policy.py` reads a whitelist — `item_id`, `slice`, `topic`,
`uq_uncertainty`, `uq_components`, `warrant_common_mode_flags`,
`warrant_as_of` — and nothing else. Harm class comes from the question's offence
cluster in the Phase C statute store, **not** from the gold provision, so no
answer key reaches the policy. `scripts/31_validate_calibration.py` parses the
scoring script with `ast` and fails the interface-rule condition if any label
field (`majority_correct`, `sample_correct`, `frac_correct`,
`majority_frac_correct`, `gold`, `trap`) appears as an identifier or a
non-docstring string. The check currently reports `label_blind: true`.

## 3. Method, exactly as specified

| Element | Implementation | Note |
|---|---|---|
| Calibration map | isotonic regression (PAV, tie-aggregated, piecewise-linear interpolation) | default |
| Fallback map | Platt scaling, Platt's smoothed targets, slope constrained `>= 0` | used when a stratum has fewer than `isotonic_min_n = 40` development records |
| Orientation | maps fitted on `r = 1 - risk` → `P(correct)`; monotonicity asserted in `__post_init__` and tested | a negative Platt slope is rejected, never clipped silently |
| Cross-fitting | grouped K-fold, grouped by `(slice, topic)`, deterministic SHA-256 group ordering, seed `phaseF-v1` | a group is never split across folds |
| Stratification | per slice; no pooling across L1 and L7 | a single-class stratum is reported as uncalibratable |
| Primary metric | ACE over 5 equal-width bins, cross-fitted on development | ECE (10 bins), Brier, log-loss, reliability table also reported |
| Decision policy | `answer` if `(1-p)·h <= c_verify`; `verify` if `<= c_abstain`; else `abstain` | `c_verify = 0.15`, `c_abstain = 0.35`, `h` from the harm class |
| Harm classes | `custodial 5.0`, `both 3.0`, `definition 1.5`, `procedural 1.0`, `unknown 5.0` | unknown is the most serious class: over-verify, never under-warn |
| Phase D override | a fired `stale_provision` / `unresolvable_assertion` / `foreign_provision` / `internal_contradiction` flag downgrades `answer` to `verify` | the detector outranks the calibrated number |
| Undefined reliability | declared action `verify`, trigger `undefined_reliability`, reason states why | degradation may widen caution, never narrow it |
| Conformal | split-conformal, `n - ceil((n+1)(1-alpha)) + 1` order statistic; tolerance `1.96·sqrt(target(1-target)/n)` | threshold is `null` when `ceil((n+1)(1-alpha)) > n` |

The policy costs are design constants, recorded in the model, the run metadata
and this note. They were fixed before the holdout was read and were not tuned.

## 4. Exact commands and expected output

```bash
python scripts/29_fit_calibration.py
python scripts/30_apply_policy.py
python scripts/31_validate_calibration.py
```

Measured output (`zsh`/`bash`, CPU, October 2026):

```
Phase F calibration model written: runs/phaseF_calibration_model.json
source: phaseA-laptop-v2-rejudged+ctx-r2+typed+warrant+uq-exact  (development 156, holdout 44)
  L1: fitted                             method=isotonic  n=78   cross-fit ACE(5)=0.2797
  L7: single_class_in_development        method=None      n=78   cross-fit ACE(5)=undefined
decision policy: verify_cost=0.15 abstain_cost=0.35
source tree SHA-256 unchanged: True (2f753a3d6f6101f9f497cff2)

calibrated and decided 200 records -> runs/...+uq-exact+cal
calibration status: {'calibrated': 100, 'undefined_stratum_not_calibrated': 100}
actions: {'answer': 17, 'verify': 101, 'abstain': 82}
source tree hash: 2f753a3d6f6101f9f497cff2 -> 2f753a3d6f6101f9f497cff2; SOURCE RUN UNCHANGED

records 200; calibrated 100; undefined reliability 100
interface rule (label-blind query path): True
  L1: holdout n=22 scored=22 correct=7 ACE(5)=0.2797 status=evaluated
  L7: holdout n=22 scored=0 correct=0 ACE(5)=undefined status=not_evaluable_single_class_holdout
  calibration_ace_at_or_below_0.05_on_development: FAIL
  harm_weighted_selective_risk_at_50pct_below_every_baseline: FAIL
  empirical_coverage_within_tolerance_of_target: pass
  query_path_reads_no_labels: pass
GATE G6: NOT_MET
```

## 5. Runs of record

| Item | Value |
|---|---|
| Phase F run (primary) | `runs/phaseA-laptop-v2-rejudged+ctx-r2+typed+warrant+uq-exact+cal` |
| Source run (read-only) | `runs/...typed+warrant+uq-exact` (Phase E, exact-key provision-entropy variant — the like-for-like frozen-pilot comparison) |
| Supplementary run | `runs/...typed+warrant+uq-typed+cal` (typed-entropy variant) |
| Calibration model (primary) | `runs/phaseF_calibration_model.json`, sha256 `f1095036d5f016c05656b80bf972f85f2bb01b114f724bf39e865182422b969a` |
| Calibration model (typed) | `runs/phaseF_calibration_model_typed.json`, sha256 `5263ef7496fe3db06e6595fd201382e74e187bc7cbfbba058496595c03dd92ab` |
| Scored items (primary) | `items.jsonl`, sha256 `5d2fc388600a3b4cd5b48ab0a2b0962b1a7699de9ef2b103c2ec67993f860c32` |
| Scored items (typed) | `items.jsonl`, sha256 `fd3ecebc20a7025331d015abd931a744bf32c6c8b9ebeaaf0fe97e56bdd28960` |
| Gate record | `<run>/calibration_report.json` (`gate: G6`, per-condition detail, per-stratum tables) |
| Source runs modified | **None** — tree hash identical before and after fitting and scoring |
| Byte-reproducibility | `items.jsonl` and the calibration model are deterministic (no timestamps): two consecutive full re-runs produced identical SHA-256 for both. `meta.json` and `calibration_report.json` carry `generated_utc` and are generation-specific; their content apart from that field is identical |

The split is the Phase E pair-grouped SHA-256 holdout (`phaseE-v1`, 20 %), 156
development / 44 holdout records, recomputed from `data/lexuq_slice.jsonl`; the
holdout item ids in the Phase F model are byte-identical to those in the
consumed `uq_validation.json`.

## 6. E6 results (measured, not projected)

### 6.1 Primary variant — `+uq-exact`

Development (`L1`, n = 78, 36 correct / 42 incorrect, isotonic, 5 grouped folds):

| Metric | Value |
|---|---:|
| cross-fitted ACE (5 bins) | **0.2797** |
| cross-fitted ECE (10 bins) | 0.2797 |
| cross-fitted Brier | 0.2993 |
| cross-fitted log-loss | 1.5375 |

Holdout (`L1`, n = 22, 7 correct / 15 incorrect):

| Metric | Value |
|---|---:|
| ACE (5 bins) | 0.2797 |
| ECE (10 bins) | 0.2797 |
| Brier | 0.2993 |
| log-loss | 1.5375 |
| harm-weighted selective risk @ 50 % coverage | **0.5455** (11 accepted, 6 errors) |
| baseline: raw Phase E score, same coverage | 0.5455 |
| baseline: sample-only `u_prov`, same coverage | **0.4545** |
| conformal target 0.80 → threshold 0.3855 | empirical coverage 0.8636 (n = 22, tolerance 0.1671) |

Action census over all 200 records: `answer 17`, `verify 101`, `abstain 82`. On
the L1 holdout: `answer 3`, `verify 0`, `abstain 19`. All 100 L7 records have
`p_reliable = null` and therefore take the declared `verify` action with the
reason "calibrated reliability is undefined for this stratum".

### 6.2 Supplementary variant — `+uq-typed`

| Metric | Development (n=78) | Holdout (n=22) |
|---|---:|---:|
| ACE (5 bins) | 0.0723 | 0.2316 |
| ECE (10 bins) | — | 0.2815 |
| Brier | — | 0.2734 |
| log-loss | — | 0.7402 |
| harm-weighted selective risk @ 50 % | — | 0.5455 (calibrated) vs 0.5455 (sample-only) |

Action census: `answer 0`, `verify 100`, `abstain 100`. L1 holdout: all 22
abstain.

### 6.3 Descriptive method sensitivity (not used for selection or the gate)

The pre-specified method rule chooses the map; the other map was also
cross-fitted for transparency. On the primary variant, Platt's cross-fitted ACE
is **0.0911** versus isotonic's 0.2797 (n = 78); on the typed variant it is
0.5385 versus 0.0723. Neither number changes the shipped model, and the gate is
evaluated on the pre-specified map only. The honest reading is that with 78
development records the choice of map matters as much as the score does, and
neither choice reaches ACE ≤ 0.05 on the primary variant.

## 7. Gate G6 (master-guide §20.3)

| Condition | Threshold | Measured (primary) | Verdict |
|---|---|---|---|
| Calibration quality on development | ACE ≤ 0.05 | 0.2797 (L1, cross-fitted, n=78) | **FAIL** |
| Harm-weighted selective risk at 50 % coverage below every baseline | `<` each baseline | 0.5455 vs 0.4545 (sample-only `u_prov`) | **FAIL** |
| Conformal coverage within sampling tolerance | empirical ≥ target − tol | 0.8636 vs 0.80 − 0.1671 | pass |
| Interface rule: no labels on the query path | static check | `label_blind: true` | pass |
| Target stratum evaluable | both classes | L7 has 0 correct of 100 | **not evaluable** |

**Gate G6: NOT_MET** (`gate_status: "NOT_MET"` in
`calibration_report.json`). Per the guide's failure branch, the uncalibrated
score and the failing strata are reported rather than smoothed over.

Two clarifications that matter for reading the second condition:

1. A monotone calibration map **cannot** change the ranking, so the selective
   risk of the calibrated score equals that of the raw Phase E score at every
   coverage, by construction. That comparison is reported
   (`raw_equal_by_construction: true`) and excluded from the pass/fail rule; the
   informative comparison is against a *different* score, the sample-only
   provision entropy.
2. On this slice every offence cluster resolves to `custodial`, so
   `harm_weight_variance_present` is `false`: the harm weighting is a constant
   multiplier and changes neither the ranking nor the threshold comparison here.
   The weighting is implemented and unit-tested with varying harm classes, but
   this instrument cannot exercise it.

## 8. What this phase does and does not show

**Does show**

* The calibration and decision machinery satisfies the specification's
  interfaces, determinism and label-blindness requirements, and it is
  reproducible from the stored record alone.
* On the control slice the Phase E score is **poorly calibrated**: ACE 0.2797
  against a 0.05 target, with 3 holdout items forecast at ≈1.0 while only 1 of 3
  was correct. Calibration does not rescue a score that is not better than the
  sample-only baseline.
* The conformal layer behaves as specified at the requested target on this
  population (0.8636 ≥ 0.80), but with n = 22 the tolerance is ±0.167, so this
  is weak evidence rather than a guarantee.
* The decision layer is conservative on this instrument: with `custodial`
  stakes, `answer` requires `p ≥ 0.97`, and 82/200 records abstain.

**Does not show**

* That G6 passes. It does not.
* Any L7 / post-transition calibration claim: that stratum has a single
  correctness class, so `p_reliable` is undefined there by construction.
* That calibration improves selective prediction. At equal coverage the
  calibrated and raw rankings are identical, and both are worse than the
  sample-only provision entropy on the primary variant's holdout.
* That the harm-weighted policy is better than a flat threshold: the slice
  contains one harm class, so the weighting is untested in situ.
* Any transferability: the maps are fitted on one quantised 7B checkpoint's
  answers to one synthetic 200-item slice.

## 9. Limitations

1. **Target stratum single-class** — the L7 half of G6 is unevaluable; this is
   the same structural limit as G5 and needs Phase G's two-class population.
2. **Small holdout** — 22 L1 items; every holdout number here has a wide
   interval and is reported without one only where the metric is a plain rate.
3. **Isotonic overfits at n = 78** — cross-fitted ACE 0.2797 versus Platt's
   0.0911; the shipped map follows the pre-specified rule, not the better
   number.
4. **Exchangeability** — conformal coverage assumes exchangeable items within a
   stratum; matched L1/L7 pairs from ten shared topics violate that in the
   strong form. The guarantee is approximate and the report says so.
5. **Harm weighting degenerate on this slice** — one harm class throughout.
6. **Inherited limits** — Phase F reads the Phase C statute store (harm classes)
   and the Phase D detector (flags); it inherits their verification gaps. It
   also inherits the Phase E score, which lost to the sample-only baseline on
   the control slice.
7. **Cost constants are design choices** — `c_verify = 0.15`, `c_abstain =
   0.35` and the harm weights are stated policy, not estimates. A deployment
   with different stakes must restate them; nothing here was fitted to them.

## 10. Test record

| Check | Result |
|---|---|
| `python -m pytest tests/test_calibration.py tests/test_policy.py -q` | **63 passed** (45 + 18) after the follow-up conformal tests |
| `python -m pytest -q` (full suite) | **270 passed, 1 skipped in 4.94 s** after the follow-up work (216 passed at merge) |
| Baseline before Phase F (same environment) | 159 passed, 1 skipped |
| Skipped | `tests/test_relations.py:236` — `torch not installed`; pre-existing, unrelated |
| Linting | `python -m compileall` clean on the new package and scripts; the repository declares no linter |
| Type checking | not configured in this repository; annotations are present but unchecked |

The new tests cover: PAV correctness and order-invariance, monotone
interpolation, single-class refusal, Platt boundedness and non-negative slope,
map round-tripping and rejection of non-monotone knots, deterministic and
whole-group folds, cross-fitting leaving every row out of its own training set,
ACE/ECE/Brier/log-loss behaviour and invalid inputs, selective risk and harm
weighting, the finite-sample conformal correction and its insufficient-data
case, per-stratum fitting with a single-class stratum, G6 verdict logic for the
not-evaluable, not-met and interface-rule cases, all policy actions and
triggers, threshold degeneracy when harm is below the abstention cost, and the
label-blind static check (positive and negative).

## 11. Reproduction and safety rules

```bash
# 1. fit the maps (development partition only)
python scripts/29_fit_calibration.py
# 2. score and decide (label-blind; writes a sibling run)
python scripts/30_apply_policy.py
# 3. held-out evaluation and Gate G6
python scripts/31_validate_calibration.py

# supplementary typed variant
python scripts/29_fit_calibration.py \
  --run-id "phaseA-laptop-v2-rejudged+ctx-r2+typed+warrant+uq-typed" \
  --model-out runs/phaseF_calibration_model_typed.json
python scripts/30_apply_policy.py \
  --run-id "phaseA-laptop-v2-rejudged+ctx-r2+typed+warrant+uq-typed" \
  --model runs/phaseF_calibration_model_typed.json
python scripts/31_validate_calibration.py \
  --run-id "phaseA-laptop-v2-rejudged+ctx-r2+typed+warrant+uq-typed+cal"
```

* Always write to a new `+` suffix; the scripts refuse to overwrite a run
  without `--force`, and refuse to write inside the source run.
* The source tree is hashed before and after fitting and scoring; a change
  aborts the step.
* The calibration model records the statute-store hash and the scored items
  record the model hash, so a mismatched pair is detected rather than trusted.
* The model file deliberately carries no generation timestamp, so the scored
  `items.jsonl` is byte-reproducible; wall-clock provenance lives in `meta.json`
  and the gate report.
* Do not relax `ace_max`, `c_verify`, `c_abstain` or the conformal target to
  change the verdict. Any change to a gate constant is a new experiment with a
  new run id and its own record.

## 12. Next actions

1. **Phase G, §21.1** — build a target slice with both correctness classes;
   without it G6's second and third conditions remain single-sided and the L7
   stratum stays unevaluable. This is the only route to a G6 verdict that is
   more than "the control slice fails".
2. **E3 human-verified relation test set** — still the open item from Phase B;
   it does not block Phase F but it blocks any claim that typed clustering is
   better than exact keys, which is the premise Phase F's typed variant uses.
3. **Re-scope the harm model** — with one harm class on this slice, either
   stratify evaluation by a finer consequence taxonomy or state in the paper
   that harm weighting is implemented but untested in situ.
4. **Do not tune the map to the gate.** Isotonic is the specified default; if a
   future run prefers Platt, that decision must be pre-registered on a
   development split that is not the reported holdout.
