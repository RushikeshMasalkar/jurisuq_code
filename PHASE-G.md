# JURIS-UQ — Phase G: target population and the §21 evaluation matrix

**Status: measurement infrastructure implemented.** The §21.2 evaluation matrix
and the offline half of the §21.3 deployment report can now be produced from the
frozen runs. The target population the guide's Gate G7 requires does **not**
exist, so **G7 is `NOT_MET`**. G5 stays `NOT_EVALUABLE` and G6 stays `NOT_MET`.

## Specification status — corrected

> **Correction (Phase G, Stage 1).** Earlier revisions of this file and of
> `configs/phase_g_target.json` stated that no Phase G specification and no gate
> number existed. That was wrong, and it is retracted here. The project's
> engineering guide defines Phase G (weeks 13–15) and a gate for it, G7. The
> guide is a project document that lives outside this repository, which is why
> the text was not to hand — that is a filing problem, not an absence of
> specification, and it must never again be reported as one.

Phase G, per the guide, is the "measure everything" phase: headline evaluation
tables, external-benchmark transfer, and laptop latency and memory. Its
governing sections are §12 (the gate table, including G7), §21.1 (reporting
discipline), §21.2 (the evaluation grid) and §21.3 (deployment measurements).

**Gate G7 — the sentence that defines it.** "The target slice carries both
correctness classes and the headline comparison is computable." The guide states
the failure condition explicitly: G7 fails when "no target slice exists on which
a ranking is defined."

G7 is therefore a defined gate with two substantive conditions, and it is **not**
satisfied today. The measured status is in "Gate G7" below. Nothing in this phase invents
a gate, a threshold, or an acceptance table; the threshold-free conditions of G7
are the guide's own words, operationalised as four explicit checks that can be
inspected in `jurisuq/evaluation/matrix.py::gate_g7`.

### How the guide's requirements map onto this repository

| Guide requirement | Where it is implemented | Status |
|---|---|---|
| §21.1(a) both correctness classes on every evaluated slice | `gate_g7`, condition 1 | **fails on L7** (0 correct of 100) |
| §21.1(b) slices reported separately, pooled only *alongside* both | `build_matrix` (never pools), `pooled_reference` (refuses unless both slices present, tagged reference-only) | implemented |
| §21.1(c) judge coverage per slice, as a column | `judge_coverage`, attached to every cell and block | implemented, 1.0000 on both slices |
| §21.1(d) undefined printed as undefined, with a reason | reason codes in `matrix.py`, propagated into the JSON | implemented |
| §21.2 nine uncertainty methods on identical items and samples | `METHODS` (9 declared) | 7 computed, `lexical_similarity` unimplemented, `p_true` has no logprobs |
| §21.2 metrics: AUROC, AUPRC, nAURC, selective risk @ fixed coverage, ACE, ECE, Brier, reliability, abstention rate, harm-weighted risk | `score_cell` | all implemented |
| §21.2 discipline: AUROC detects *incorrect*; confident-wrong = wrong ∧ lowest-quartile uncertainty | `score_cell`, `confident_wrong` | implemented |
| §21.2 slices: control, target, external benchmark | L1, L7 present | external benchmark **deferred** (dataset + licensing approval) |
| §21.2 generator: two laptop sizes/quantisations + one API model | 1 of 2 laptop arms | both extra arms **deferred** |
| §21.3 stage-1 latency, full-cascade median + p95, peak RSS, configuration measured | `deployment.py`, `scripts/43` | stage-1 + configuration measured; cascade and RSS **not instrumented** |

The old forward references remain accurate as *prerequisites* and are kept
below for provenance:

| Source | Text | What it requires |
|---|---|---|
| `PHASE-E.md` §7.4 | "The synthetic matched slice has no correct L7 majority answers. Build a target population containing both classes before claiming target-slice AUROC or evaluating the complete G5 criterion." | both correctness classes on the target slice |
| `PHASE-E.md`, structural G5 finding | "It requires an evaluation population in which `T` varies within a slice: a slice with both correctness classes on which the detector both fires and stays silent." | both classes **and** both detector states, **within one slice** |
| `PHASE-F.md` §12.1 | "build a target slice with both correctness classes; without it G6's second and third conditions remain single-sided and the L7 stratum stays unevaluable." | same population, so G6's L7 half becomes defined |

## The finding: no valid target population exists in the frozen artefacts

Measured by `scripts/40_audit_target_feasibility.py` on
`runs/phaseA-laptop-v2-rejudged+ctx-r2+typed+warrant+uq-exact/` (Phase D detector
fields plus Phase E scores, read-only, source tree hash unchanged). Result file:
`runs/phaseG_feasibility_audit.json`.

| Population | n | correct | incorrect | detector fired (W=0) | silent (W=1) | partial | detector AUROC | status |
|---|---:|---:|---:|---:|---:|---:|---|---|
| L1 | 100 | 43 | 57 | 0 | 61 | 37 | 0.4890 | **NOT_READY** |
| L7 | 100 | 0 | 100 | 82 | 7 | 0 | undefined | **NOT_READY** |
| L1 + L7 pooled | 200 | 43 | 157 | 82 | 68 | 37 | 0.7720 | **NOT_READY** |

Why each fails, in the words of the conditions the module checks:

* **L1** has both classes and both partitions, but the detector never fires:
  61 silent, 37 partial, 0 fired. `W = A·T·J·K` with `T = 1` on L1, so the
  detector cannot reach 0 there.
* **L7** has both detector states (82 fired, 7 silent) but **one correctness
  class**: 0 correct of 100. It is also single-class in *both* the development
  and the evaluation partition, so neither a calibration map nor an AUROC can
  be formed.
* **L1 + L7** satisfies the counting conditions and is rejected anyway, because
  it spans two slices. The temporal factor is 1.0 on L1 and 0.0 on L7 by
  construction, so any within-population detector statistic reads the era phrase
  in the question rather than the detector.

**The pooled trap, quantified.** On the pooled population the detector's AUROC
against correctness is 0.772, which would look like a working detector. It is an
artefact of the confound:

| Statistic | Value |
|---|---|
| detector AUROC against `slice == L1` | **0.9458** |
| detector AUROC within L1 | **0.4890** (chance) |
| detector AUROC within L7 | undefined (one class) |
| detector AUROC pooled | 0.7720 |

The warrant score is very nearly a slice indicator, and within the only slice
that has two classes it carries no information at all. `PHASE-F-FOLLOWUP.md`
experiment 2 measured the same confound on the score rather than the detector:
pooled AUROC 0.6868 versus 0.8626 for the same estimator fitted within L1. Any
future Phase G result must therefore be reported **within one slice**; a pooled
number is not admissible evidence.

I also searched every slice × topic subgroup for a population that has both
classes *and* both detector states. There are none: on L1 the detector never
fires, and on L7 there is never a correct answer.

## Why the L7 stratum has no correct answers (measured, not assumed)

The obvious next question is whether the zero is a scoring artefact. It is not,
and the check is worth recording because it forecloses cheaper fixes:

| Check on the frozen Phase A run (`qwen2.5-7b-instruct`, 10 samples/item) | Value |
|---|---|
| L7 items with a correct **majority** answer | 0 / 100 |
| L7 items with **any** correct sample | 0 / 100 |
| L7 gold-labelled samples | 0 / 1000 |
| L7 samples labelled `stale_law` (asserts the repealed IPC provision) | 832 / 1000 |
| L7 samples labelled `wrong_section` (BNS act, wrong section) | 150 / 1000 |
| L7 samples asserting the gold section in parent form (e.g. `BNS 351` for gold `BNS 351(2)`) | **0** |
| Per-topic gold-labelled samples | 0 in all 10 topics |
| L1 majority accuracy (control) | 43 / 100 |

The comparator itself was probed directly on an L7 item before drawing that
conclusion, because "the model never says the right thing" is also what a broken
comparator looks like:

| Answer fed to `ProvisionJudge` for `L7-culpable_homicide-004` (gold BNS 105) | Label |
|---|---|
| `Section 105 of the Bharatiya Nyaya Sanhita, 2023 applies.` | `gold` |
| `BNS 105` | `gold` |
| `Under the BNS, section 105 applies; punishment is life imprisonment.` | `gold` |
| `Section 105 BNS read with Section 106 BNS.` | `gold_first` |
| `BNS 103 applies.` | `wrong_section` |
| `IPC 304 applies.` | `stale_law` |

The judge accepts the correct answer in every form tested, so the zero is a
property of the generated text, not of the matching logic.

Two conclusions follow, and they are deliberately separated:

1. **Confirmed.** On this slice, with this generator, no L7 item is answerable,
   and no re-sampling, larger `n`, or different judge can change that — the gold
   section never appears in 1,000 samples across ten offences. The judge is not
   labelling a correct answer wrong: the parent-form check finds zero cases
   where a section was asserted in a form the comparator would reject.
2. **Hypothesis, not confirmed.** The pattern is consistent with a generator
   knowledge limit: the model frequently emits the *BNS* label with *IPC*
   numbering (`BNS 304`, `BNS 307`, `BNS 378`), which is what a model that has
   seen the new code's label but not its table would produce. This project has no
   mechanism for attributing errors to the model versus the prompt in general,
   and this observation does not establish it. It is recorded as a hypothesis to
   test, not as a finding.

Either way, a two-class target population cannot be assembled from the frozen
artefacts. It needs new items and new generation, which is the checkpoint below.

## What is implemented

Everything below is offline, deterministic and tested. Nothing in this phase
calls a model, and no frozen artefact is modified.

| Path | Purpose |
|---|---|
| `jurisuq/target/population.py` | detector-state classification, `population_report` / `population_status` (the documented conditions, each carrying its source), `confound_report`, `yield_report`, `items_needed` |
| `jurisuq/target/__init__.py` | package exports |
| `scripts/40_audit_target_feasibility.py` | read-only audit of a stored run → `runs/phaseG_feasibility_audit.json` |
| `scripts/41_screen_target_yield.py` | candidate-item yield screen; `mock` by default, real generation only with `--allow-generation` |
| `configs/phase_g_target.json` | audit inputs, screen parameters, planning assumptions, and the recorded forbidden operations |
| `tests/test_target_population.py` | 34 tests: state classification, every readiness condition, the pooled trap, missing-value handling, confound diagnostic, yield estimation, planning projection |
| `tests/test_target_screen.py` | 16 tests: item-schema validation, slice-stratified capping, the generation guard, end-to-end mock run |
| `jurisuq/evaluation/matrix.py` | the §21.2 grid: 9 methods × per-slice matrices, all ten metrics, per-slice judge coverage, reason-coded undefineds, confident-wrong, harm-weighted risk, `gate_g7`, and the no-pooling guard |
| `jurisuq/evaluation/deployment.py` | §21.3 measurements: stage-1 latency, full-cascade median/p95, peak RSS, the measured-configuration record, and the §27.1 ladder check |
| `scripts/42_build_eval_matrix.py` | builds `runs/phaseG_eval_matrix.json` from the frozen runs (offline) |
| `scripts/43_measure_deployment.py` | builds `runs/phaseG_deployment.json`; offline by default, `--timings` on the laptop |
| `tests/test_eval_matrix.py` | 39 tests: every metric, the single-class and constant-score traps, every reason code, confidence-quartile edges, the no-pooling guard, G7 on both fixtures, no-NaN |
| `tests/test_deployment_metrics.py` | 32 tests: percentile convention, empty/single summaries, field skipping, both undefined reasons, the ladder, configuration requirement |
| `tests/test_phase_g_docs.py` | 15 tests: the corrected specification status, config/report/module agreement on the G7 verdict and the reason codes, the published table against the JSON, provenance, no pooling, no silent nulls |

### Gate G7, measured

Produced by `scripts/42_build_eval_matrix.py` from the frozen Phase E scores and
the Phase F calibration run. Headline columns are the frozen pair-grouped
**evaluation** partition (44 items), which is the only partition on which every
method is out of sample; the report also carries a descriptive all-item matrix
with an explicit in-sample caveat for the fitted method.

| Method | L1 AUROC | L7 AUROC |
|---|---:|---|
| exact agreement | 0.5714 | undefined — `single_correctness_class` |
| lexical similarity | undefined — `method_not_implemented` | undefined — `method_not_implemented` |
| discrete semantic entropy | 0.5714 | undefined — `single_correctness_class` |
| standard semantic entropy | 0.4857 | undefined — `single_correctness_class` |
| SelfCheck | 0.5905 | undefined — `single_correctness_class` |
| p_true | undefined — `logprobs_absent` | undefined — `logprobs_absent` |
| provision agreement | 0.8333 | undefined — `single_correctness_class` |
| legal-aware | 0.6524 | undefined — `no_items_with_a_score_and_a_label` |
| legal-aware, uncalibrated | 0.6524 | undefined — `single_correctness_class` |

Judge coverage is 1.0000 on both slices (0 unresolved items, 0 unresolved
samples). The four G7 checks come out met / NOT met as follows:

| G7 condition | Status |
|---|---|
| both correctness classes on every evaluated slice | **NOT met** — L7 has 0 correct of 22 evaluation items (0 of 100 overall) |
| headline comparison computable | **NOT met** — no legal-aware vs baseline ranking exists on L7 |
| judge coverage reported per slice | met |
| undefined values stated with a reason | met |

**Gate G7: `NOT_MET`.** The reason is the guide's own fail condition: no target
slice exists on which a ranking is defined.

Two further gaps sit underneath that verdict and are reported rather than
papered over:

* The calibrated legal-aware method is defined on **L1 only** (100 of 100 items
  there, 0 of 100 on L7). Even if L7 had both classes, the calibrated arm could
  not be scored on it without extending calibration, which needs generation.
* `p_true` is unavailable for every item because the frozen runs stored no
  token log-probabilities. It is a declared arm with a measured absence, not a
  method that was silently dropped.

### §21.3 deployment measurements

| Measurement | Result |
|---|---|
| stage-1 latency (generation + provision score, no legal modules) | n=200, median 45.02 s, p95 67.41 s, max 97.83 s |
| full-cascade latency, median and p95 | undefined — `not_instrumented` |
| peak resident memory | undefined — `not_instrumented` |
| configuration actually measured | `openai-compat:qwen2.5-7b-instruct`, M=10, quantisation not recorded in the run metadata, degraded (no legal modules) |

The two undefined rows are undefined because the frozen runs record only
generation time; relation, detection, estimation and decision are not
instrumented, and no memory sampling exists in any Phase A–F run. They require a
laptop run and are reproduced with `scripts/43_measure_deployment.py --timings
<file>`, whose expected input shape is documented in the script. No value is
estimated for them.

### Evaluation arms that are missing by decision

| §21.2 arm | Status | Why |
|---|---|---|
| second laptop model or quantisation | deferred | cost and storage review; the guide's two-arm generator axis is 1 of 2 |
| one API model at evaluation time | deferred | not approved; no spend or generation authorised in this stage |
| external benchmark slice | deferred | dataset selection and licensing need separate approval; no benchmark data is in the repository |

### The readiness conditions

Each is a restatement of a documented sentence and carries its citation in the
report payload. They are boolean; no numeric threshold is introduced.

| Condition | Source |
|---|---|
| `both_correctness_classes` | PHASE-E §7.4; PHASE-F §12.1 |
| `detector_fires_and_stays_silent` | PHASE-E structural G5 finding |
| `both_classes_in_every_partition` | PHASE-E §6 (evaluation); PHASE-F §7 (development) |
| `no_imputed_detector_values` | PHASE-E: "no unresolved legal factor is assigned zero" |
| `single_slice_population` | PHASE-E structural finding: `T` must vary *within* a slice |

A `READY` status means only that the population can carry the existing criteria.
The payload says so in `status_meaning`, and the tests assert that disclaimer is
present, because a status flag is exactly the sort of thing that gets quoted out
of context later.

Partition conditions **fail closed**: if no partition map is supplied, the
condition is reported as not met rather than assumed to hold.

## Reproduction

```powershell
# the audit (offline; seconds)
python -X utf8 scripts\40_audit_target_feasibility.py

# the screen, offline plumbing check (no model is called)
python -X utf8 scripts\41_screen_target_yield.py --data data\lexuq_slice.jsonl --items 6 --out runs\phaseG_screen_mock.json --set provider=mock --set n_samples=3

# the evaluation matrix (§21.2) and the G7 verdict, offline
python -X utf8 scripts\42_build_eval_matrix.py

# the deployment report (§21.3), offline half
python -X utf8 scripts\43_measure_deployment.py

# focused tests
python -X utf8 -m pytest tests\test_target_population.py tests\test_target_screen.py tests\test_eval_matrix.py tests\test_deployment_metrics.py -q
```

The screen **refuses** to run against a real backend unless `--allow-generation`
is passed; the default config points at LM Studio, so the guard fires
immediately:

```
ERROR: this script calls a model when provider != 'mock'.
       provider is 'openai'. Re-run with --allow-generation once the cost is approved...
```

## Test record

| Check | Result |
|---|---|
| Sandbox baseline before this phase | 270 passed, 1 skipped |
| After Phase G population infrastructure | 320 passed, 1 skipped |
| After the §21 matrix and deployment tooling | 391 passed, 1 skipped |
| After the documentation guard tests | 406 passed, 1 skipped |
| New tests | 136 (34 population + 16 screen + 39 matrix + 32 deployment + 15 doc guards) |
| Skipped | `tests/test_relations.py:236` — `torch not installed`; pre-existing |
| User's Windows environment | torch present, so the skip runs there (271 passed at baseline) |

## What this phase does and does not show

**Does show**

* No population in the frozen artefacts satisfies the documented prerequisite
  for G5 or for the L7 half of G6, and the reason is structural in each case:
  L1 never fires the detector, L7 has no correct answer, and pooling is
  confounded.
* The pooled detector AUROC of 0.772 is an artefact; within the only two-class
  slice the detector is at chance (0.489).
* The L7 zero is not a comparator artefact: zero of 1,000 samples assert the gold
  section, in any form, in any of the ten topics.
* The §21.2 matrix can be computed end to end from frozen artefacts. On L1, the
  only two-class slice, provision agreement (0.8333) and the two legal-aware arms
  (0.6524) rank above chance, as do the exact-agreement, discrete-semantic-entropy
  and SelfCheck columns (0.57–0.59); only standard semantic entropy lands at
  0.4857, i.e. at chance.
* G7 fails, and fails for a measured reason: L7 carries one correctness class,
  so no ranking is defined there.

**Does not show**

* Any Phase G result on a valid target population. There is still no target
  population, G5 stays `NOT_EVALUABLE`, G6 stays `NOT_MET`, and the L7 stratum
  stays undefined.
* That the legal-aware method beats the baselines. On L1 the strongest single
  column is the provision-agreement baseline (0.8333), above both legal-aware
  arms (0.6524), and that comparison rests on 22 evaluation items with 7
  correct — far too few to rank methods. No method ordering is claimed here.
* That a generator change would fix the yield. That is the open empirical
  question the screen exists to answer.
* That the base model is "responsible" for the legal errors in a scientific
  sense. The observation is a hypothesis with a plausible mechanism, not an
  attribution.

## Remaining work and the pending checkpoint

Stage 1 (this work) is offline and stops here. The steps below are Stage 2 and
need explicit approval before any of them is run. The first is the only one that
can move G7, and it requires generation:

1. **Author an approved candidate item set** — new post-transition items in the
   Phase A schema, with `verified: false` provenance, covering more than the ten
   frozen offences if the specification allows it.
2. **Run the screen** (~24 items × 10 samples ≈ 20 minutes, `scripts/41`).
3. **Decide from the measured yield** whether a full run is affordable, using
   `items_needed` from the same report.
4. **Only then** run full generation, assemble the population, and re-run the
   existing chain under a new run id (`phaseG-target-v1…`).

No step here may change `ace_max = 0.05`, `c_verify = 0.15`, `c_abstain = 0.35`,
the 0.80 conformal target, the `phaseE-v1` split, or any frozen run.

## Known limitations

1. **G7 is failed, not merely unevaluable.** The guide defines G7 and states
   its failure condition; the target slice has one correctness class, so the
   gate is `NOT_MET` on the guide's own terms. It is not a documentation gap and
   must not be reported as one.
2. **Half of the §21.2 grid is absent by decision.** One generator, two slices,
   no external benchmark. The matrix is honest about the missing axes but it is
   not the full grid the guide describes, and no claim should be read as if it
   were.
3. **The audit covers one run.** It characterises the frozen
   `qwen2.5-7b-instruct` run; a different generator could produce a different
   class balance, which is exactly what the screen measures.
4. **`items_needed` is a planning projection.** It assumes independent items at a
   constant rate; real yield varies by topic, which is why the report is
   per-topic.
5. **Detector states are coarse.** `W = 1` and `W = 0` are treated as the two
   documented states, and interior values are reported separately rather than
   assigned to either. If the guide defines "fires" differently, the
   classification needs revisiting.
