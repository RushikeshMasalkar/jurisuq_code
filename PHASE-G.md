# JURIS-UQ — Phase G: target population for the G5 and G6 target stratum

**Status: infrastructure implemented and audited; the target population does not
exist yet. No Phase G gate is defined, because none is documented.**

## Specification status — read this first

The repository contains **no Phase G specification**. The engineering guide
whose §16.4, §20, §20.3 and §21.1 this project cites is not part of the tree,
and no gate number, threshold, or acceptance table for Phase G appears anywhere
in it. Every occurrence of "Phase G" in the documentation is a forward
reference, and all of them say the same thing:

| Source | Text | What it requires |
|---|---|---|
| `PHASE-E.md` §7.4 | "The synthetic matched slice has no correct L7 majority answers. Build a target population containing both classes before claiming target-slice AUROC or evaluating the complete G5 criterion." | both correctness classes on the target slice |
| `PHASE-E.md`, structural G5 finding | "It requires an evaluation population in which `T` varies within a slice: a slice with both correctness classes on which the detector both fires and stays silent." | both classes **and** both detector states, **within one slice** |
| `PHASE-F.md` §12.1 | "build a target slice with both correctness classes; without it G6's second and third conditions remain single-sided and the L7 stratum stays unevaluable." | same population, so G6's L7 half becomes defined |

That is the entire documented scope. Phase G is a **data-availability phase**:
it exists to make G5 and the L7 half of G6 evaluable, not to add a model.

Because no gate is documented, this phase implements **no new gate**, changes no
existing gate constant, and does not report a pass or a fail of anything. What
it does implement is the documented prerequisite, as an executable check, plus
the audit that establishes whether that prerequisite is currently met. A numeric
Phase G gate can be added later only once an approved specification exists.

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

# focused tests
python -X utf8 -m pytest tests\test_target_population.py tests\test_target_screen.py -q
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
| After Phase G infrastructure | 320 passed, 1 skipped |
| New tests | 50 (34 population + 16 screen) |
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

**Does not show**

* Any Phase G result. There is no target population yet, so G5 stays
  `NOT_EVALUABLE`, G6 stays `NOT_MET`, and the L7 stratum stays undefined.
* That a generator change would fix the yield. That is the open empirical
  question the screen exists to answer.
* That the base model is "responsible" for the legal errors in a scientific
  sense. The observation is a hypothesis with a plausible mechanism, not an
  attribution.

## Remaining work and the pending checkpoint

The next step is the only one that can move the gates, and it requires
generation:

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

1. **No specification.** The conditions implemented are faithful to the phase
   records, but a gate defined in the missing guide could require more or other
   things. The gap is recorded in `configs/phase_g_target.json`
   (`specification_status`) and must be closed before a Phase G verdict is
   claimed.
2. **The audit covers one run.** It characterises the frozen
   `qwen2.5-7b-instruct` run; a different generator could produce a different
   class balance, which is exactly what the screen measures.
3. **`items_needed` is a planning projection.** It assumes independent items at a
   constant rate; real yield varies by topic, which is why the report is
   per-topic.
4. **Detector states are coarse.** `W = 1` and `W = 0` are treated as the two
   documented states, and interior values are reported separately rather than
   assigned to either. If the guide defines "fires" differently, the
   classification needs revisiting.
