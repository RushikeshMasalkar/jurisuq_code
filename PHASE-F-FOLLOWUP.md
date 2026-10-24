# JURIS-UQ — Phase F follow-up experiments (post-G6 audit)

Phase F was implemented, evaluated, and left with Gate **G6 = NOT_MET**
(`PHASE-F.md` §7). A post-merge audit of that record found four things worth
correcting. This document records the four follow-up experiments, their
pre-registered rules, their measured results, and what they do and do not
change.

**The headline: nothing here turns G6 into a pass, and nothing here was meant
to.** Three of the four experiments make the failure *more* precisely stated —
the corrections move the numbers, tighten the intervals, and remove one
avoidable methodological error (a conformal threshold taken from the holdout).
The fourth shows where the recoverable performance actually is.

| # | Question | Outcome |
|---|---|---|
| 1 | Was the conformal threshold computed on data disjoint from the holdout? | **No — it was not.** Corrected; coverage now from the 78-item development cross-fit. Gate verdict unchanged. |
| 2 | Does fitting Phase E pooled across L1 and L7 cost within-slice ranking? | **Yes, substantially.** L1-only refit: AUROC 0.687 → 0.863 on the same 20 items. Calibration still fails. |
| 3 | Is isotonic the right map at n=78 with a reliability range of 0.0795? | **No.** A pre-registered range rule selects Platt; Platt beats isotonic on every metric. Gate still fails. |
| 4 | Are the point estimates resolvable once topic-level dependence is respected? | **Mostly yes for ACE (stable fail), no for the selective-risk gap.** |

All four experiments are read-only with respect to every existing artefact. The
frozen runs `+uq-exact`, `+uq-typed` and `+cal` are byte-identical to before;
the corrected calibration runs are new siblings (`+cal-r2`), never replacements.

## What was audited

| Finding | Detail |
|---|---|
| Conformal threshold source | `_evaluate_stratum` computed the threshold from the same 22 holdout items the coverage was then measured on. Every other Phase F figure was honest about its source; this one was not, and the docstring contradicted the code. |
| No exact interval for coverage | The gate used a ±1.96·√(p(1−p)/n) Wald tolerance only. With 22 items a Wald interval is unreliable, and no exact bound was reported. |
| Pooled fitting across unequal slices | One legal head was fitted on 156 development rows that mix L1 (temporal factor constant, common-mode zero) and L7. Coefficient mass can be spent separating the slices rather than ranking within one. |
| Method rule ignores input range | The shipped rule is `isotonic if n_development ≥ 40 and both classes`, i.e. size only. At n=78 with a reliability input spanning 0.0795, isotonic's end knots sit on a handful of items and it clamps: one L1 holdout item is scored exactly 1.0. |
| Item-level uncertainty only | Item-level resampling treats the 78 development items as independent, but they are 10 offence topics x matched L1/L7 pairs. Variances are understated. |

## Experiment 1 — conformal threshold from a disjoint set

**The bug.** The threshold was the empirical quantile of the 22 holdout
probabilities, then coverage was measured on those same 22 items. That is
in-sample, so it cannot fail for the reason the layer exists.

**The fix.** The threshold now comes from the 78 development items' **grouped
cross-fitted** probabilities (fold-grouped by `slice|topic`, k=5, so no item
contributes to its own threshold), and the code reports which partition the
threshold came from. A model with no cross-fitted development probabilities is
reported as `NOT_EVALUABLE` rather than silently falling back to the holdout. A
Clopper–Pearson one-sided lower bound was added alongside the Wald tolerance,
because 22 items is too few for Wald alone.

| Quantity | v1 `+cal` | r2 `+cal-r2` (corrected) |
|---|---|---|
| Threshold source | the 22 holdout items (in-sample) | 78 development grouped cross-fitted |
| Threshold | 0.3855 | **0.4702** |
| Empirical coverage | 0.8636 (19/22) | **0.6818 (15/22)** |
| Wald floor (0.80 − 0.1671) | 0.6329 → pass | 0.6329 → **pass** |
| Clopper–Pearson lower 95 % | not reported | **0.4845** |
| Exact bound reaches the 0.80 target | not reported | **no** |
| G6 verdict | NOT_MET | **NOT_MET (unchanged)** |
| `items.jsonl` | — | **byte-identical to `+cal`** |

The correction is uncomfortable but correct: the *reported* coverage drops from
0.86 to 0.68 because the honest threshold is higher. The gate's condition 3
still passes on the Wald tolerance and still fails on the exact bound. Both are
now in the report, which is the point.

Artifacts: `runs/phaseF_calibration_model_r2.json`,
`runs/…+uq-exact+cal-r2/`. Reproduce with:

```bash
python scripts/29_fit_calibration.py --model-out runs/phaseF_calibration_model_r2.json
python scripts/30_apply_policy.py \
  --model runs/phaseF_calibration_model_r2.json --out-suffix "+cal-r2"
python scripts/31_validate_calibration.py \
  --run-id "phaseA-laptop-v2-rejudged+ctx-r2+typed+warrant+uq-exact+cal-r2"
```

## Experiment 2 — pooled versus within-slice Phase E fitting

**Pre-specified question:** does the shipped pooled legal head lose
within-slice ranking? Both arms fitted on the same 78 L1 development rows
(pooled arm: the stored Phase E model, fitted on all 156; slice arm: the same
estimator refitted on L1 only), scored on the **same** 20 L1 holdout items.
Eligibility (features complete, both arms finite) never reads a label, and the
arms are not selected on holdout performance — the comparison is reported as
found.

| Arm | Training rows | L1 feature weights | AUROC (n=20) |
|---|---|---|---|
| Pooled (shipped) | 156 | non-zero on `u_warrant` 0.206, `u_cm` 0.207, and 6 interaction terms | 0.6868 |
| Within-slice | 78 (42 correct / 36 incorrect) | `u_prov` 0.172, `u_text` 0.006, `u_prov*u_text` 0.171 | **0.8626** |

The pooled fit spends real coefficient mass on `u_warrant` and `u_cm` — both
constant within L1 by construction — which is exactly the mechanism the audit
suspected. Two L1 holdout items (`L1-criminal_intimidation-009`,
`…-087`) have incomplete legal features; they are excluded from both arms and
**listed in the report** rather than dropped silently.

Downstream, with isotonic calibration as configured:

| Arm | Dev cross-fit ACE | Holdout ACE | Holdout Brier | Holdout log loss | Selective risk @ 50 % |
|---|---|---|---|---|---|
| Pooled | 0.2504 | 0.2388 | 0.2722 | 0.9769 | 0.5000 |
| Within-slice | 0.1958 | 0.1941 | 0.2073 | 0.8315 | 0.4000 |

The development cross-fit and the holdout agree closely for both arms, which is
the check that the ranking gain is not a holdout artefact. **But both arms still
miss `ace_max = 0.05` by a factor of four.** A better score does not by itself
buy calibration.

*Design note:* these arms are reported inside
`runs/phaseF_exp2_within_slice.json` rather than as full `+uq-l1only` run
directories. Materializing a run id would require re-scoring the frozen Phase E
`items.jsonl` under a different model, which changes an artifact the audit was
supposed to leave alone. The paired comparison answers the question without
touching it.

## Experiment 3 — which calibration map should ship?

**The rule, frozen before the holdout was scored** (`configs/phase_f_followup.json`,
`preregistered_small_sample_rule`):

> use Platt when `n_development < 100` **or** the reliability-input range
> `< 0.15`; otherwise isotonic.

Both thresholds come from the observed design (n=78, range 0.0795), not from
holdout performance. The rationale is structural: isotonic has to place end knots
on data, and with a narrow range those knots rest on a few items, after which
the map clamps.

The shipped rule, for contrast, is size-only (`isotonic_min_n = 40`), so L1 at
n=78 always gets isotonic.

**L1 results** (dev n=78, holdout n=22; cross-fitted column uses the same
fold seeds as the shipped report, and reproduces its figures exactly):

| Method | Dev cross-fit ACE | Holdout ACE | Holdout ECE(10) | Holdout Brier | Holdout log loss | Items pinned at 1.0 |
|---|---|---|---|---|---|---|
| raw (`1 − risk`, no fit) | *n/a* | 0.0555 | 0.1512 | 0.2177 | 0.6262 | 0 |
| **Platt (chosen by the rule)** | **0.0911** | **0.1398** | 0.1398 | 0.2386 | 0.6718 | 0 |
| isotonic (shipped) | 0.2797 | 0.2797 | 0.2797 | 0.2993 | 1.5375 | **1** |
| constant (base rate) | *n/a* | 0.1434 | 0.1434 | 0.2375 | 0.6681 | 0 |

Two independent lines of evidence agree that isotonic is the wrong map here:
the label-blind development cross-fit (0.0911 vs 0.2797) and the holdout check
(0.1398 vs 0.2797). The rule fires for the reason it was written to fire.

**This still does not pass the gate.** Platt's 0.0911 is better than isotonic's
0.2797 and still above `ace_max = 0.05`. Note also that the *uncalibrated* raw
score has the best holdout ACE (0.0555) of any candidate — but it is not a
calibration map and is reported for reference only. Selecting it because it wins
on the holdout would be selecting on held-out labels, which the report states
explicitly (`selection_used_holdout_labels: false`).

**L7 is not calibratable**, confirmed structurally: all 78 L7 development
records are wrong, so the stratum has one correctness class and no map exists.
The experiment records `development labels contain a single class` rather than
imputing one.

The pooled-across-strata view is included for reference only and is not the
configuration that ships.

## Experiment 4 — how much of this is resolvable at n=78?

Percentile bootstrap, 4000 resamples, seed 20261024, 95 % intervals. The
**topic** is the primary sampling unit (10 development topics, 8 holdout
topics): items within a topic share legal facts, templates and matched L1/L7
pairs. Item-level resampling is reported as the optimistic secondary.

| Quantity | Point | 95 % topic-clustered | 95 % item-level |
|---|---|---|---|
| Development ACE (5-bin) | 0.2797 | [0.1249, 0.4598] | [0.1867, 0.3867] |
| Holdout ACE (5-bin) | 0.2797 | [0.1562, 0.5302] | [0.1673, 0.4924] |
| Development Brier | 0.2976 | [0.1702, 0.4183] | [0.2385, 0.3623] |
| Holdout Brier | 0.2993 | [0.2353, 0.3909] | [0.2086, 0.4121] |
| Selective-risk gap vs raw score | −0.0256 | [−0.1905, +0.0833] | [−0.1538, +0.0769] |
| Selective-risk gap vs sample-only (`u_prov`) | **+0.0256** | **[−0.1765, +0.1750]** | [−0.1026, +0.1538] |

**Gate stability.** `ace_max = 0.05` lies outside every interval, in both
partitions and under both sampling units: the ACE failure is `stable_fail`. The
point estimate is not being over-read — calibration is genuinely bad here, not
merely under-powered.

**The selective-risk gap is a different story.** The audit's tentative reading
was that calibrated ranking is "directionally worse" than the sample-only
baseline. With topic clustering, the gap is +0.0256 with a 95 % interval of
[−0.1765, +0.1750]: **it is not resolved at n=78 in either direction**, and the
honest statement is that the two orderings are indistinguishable on this data.
The item-level interval ([−0.1026, +0.1538]) is narrower — that narrowing is
the dependence the clustered unit is there to capture.

**Conformal coverage**, corrected by Experiment 1: 15/22 = 0.6818 against a
target of 0.80. Wilson 95 % [0.4732, 0.8364]; Clopper–Pearson lower 0.4845. The
Wald tolerance passes (0.6818 ≥ 0.6329) and the exact bound does not reach the
target. Both are reported; neither is allowed to stand in for the other.

## What changed in the code

| File | Change |
|---|---|
| `jurisuq/calibration/conformal.py` | added `clopper_pearson_lower()`, `coverage_report()` |
| `jurisuq/calibration/evaluate.py` | conformal threshold from development cross-fitted probabilities; provenance recorded; `no_development_calibration_set` branch |
| `jurisuq/calibration/within_slice.py` | new — Experiment 2 |
| `jurisuq/calibration/method_selection.py` | new — Experiment 3 (frozen rule + per-stratum comparison) |
| `jurisuq/calibration/uncertainty_intervals.py` | new — Experiment 4 (clustered/paired bootstrap, Wilson, gate stability) |
| `scripts/32_compare_within_slice.py` | new — writes `runs/phaseF_exp2_within_slice.json` |
| `scripts/33_compare_calibration_methods.py` | new — writes `runs/phaseF_exp3_calibration_methods.json` |
| `scripts/34_estimate_uncertainty.py` | new — writes `runs/phaseF_exp4_uncertainty.json` |
| `configs/phase_f_followup.json` | new — the frozen rules, seeds, reps, confidence |
| `tests/test_calibration.py` | conformal tests updated; 6 added |
| `tests/test_within_slice.py`, `tests/test_method_selection.py`, `tests/test_uncertainty_intervals.py` | new — 11 + 15 + 22 tests |

No gate constant changed. `ace_max = 0.05`, `c_verify = 0.15`,
`c_abstain = 0.35`, the conformal target 0.80 and the `phaseE-v1` split are
exactly as merged.

## Test record

| Check | Result |
|---|---|
| Baseline before this work | **216 passed, 1 skipped** |
| `pytest -q` (full suite, after) | **270 passed, 1 skipped in 4.94 s** |
| New tests | 54 (6 conformal, 11 within-slice, 15 method-selection, 22 uncertainty) |
| Skipped | `tests/test_relations.py:236` — `torch not installed`; pre-existing |
| Linting | `python -m compileall` clean; the repository declares no linter |
| Type checking | not configured in this repository |

## Limitations

1. **20 holdout items.** Every holdout figure moves by ~0.05 per item. The
   development cross-fit is the primary evidence throughout and the holdout is a
   check, not the arbiter.
2. **8 holdout topics.** Few enough that the percentile bootstrap intervals are
   an indication of precision rather than an exact coverage claim; each report
   says so.
3. **`ace_max = 0.05` is unreachable on this instrument** regardless of map. The
   best dev cross-fit here is 0.0911 (Platt). Passing G6 needs a better score or
   a target slice with both classes, not a better map.
4. **Experiment 2's ranking gain is not a Phase F result.** It is a Phase E model
   finding: it says the pooled fit is misspecified for L1, and it would need a
   re-scored Phase E run to propagate into a new `+uq-*` run id.
5. **L7 remains structurally unevaluable** (0 correct of 100). No experiment here
   changes that; only Phase G §21.1 can.

## Recommendations, in order

1. **Do not tune the map to make G6 pass.** Experiments 3 and 4 both show the
   remaining gap is not a map-selection problem.
2. **Carry Experiment 3's rule into any future calibration run** — the range
   condition is the operative part, and it is label-blind.
3. **Carry Experiment 2's finding into Phase E**: fitting per slice (or with
   slice interactions) is the single largest ranking gain measured in this
   project, 0.687 → 0.863 AUROC.
4. **Adopt the clustered interval as the default** for reporting in Phases G and
   beyond; the item-level interval is systematically too narrow.
5. **Phase G §21.1 remains the blocking dependency** for a G6 verdict that is
   better than "the control slice fails".
