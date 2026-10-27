# JURIS-UQ

Legal-aware uncertainty quantification for LLM-based Indian legal question
answering.

> **Research prototype.** JURIS-UQ is not a legal research service and does
> not provide legal advice. Its benchmark is scoped and partly synthetic, and
> Phase C legal verification is incomplete.

**Where to start.** [`PROFESSOR-SUMMARY.md`](PROFESSOR-SUMMARY.md) for the
question and the evidence, [`STATUS.md`](STATUS.md) for what is finished,
blocked and why, [`DEMO.md`](DEMO.md) to run everything offline in one command,
and [`ROADMAP.md`](ROADMAP.md) for the order of the remaining work.

```bash
python -X utf8 -m pytest -q        # the suite
python -X utf8 scripts/47_demo.py  # offline end-to-end demonstration (no model)
```

## Purpose and scope

JURIS-UQ studies whether agreement among an LLM's sampled answers can hide a
shared legal error. The current benchmark is matched around the transition
from the Indian Penal Code (IPC) to the Bharatiya Nyaya Sanhita (BNS), effective
1 July 2024:

- **L7** asks for current law and uses the repealed IPC provision as the trap.
- **L1** asks for law immediately before the transition and uses the BNS
  successor as the trap.

The phases are cumulative:

1. **Phase A** builds the sampling, judging, clustering, and sample-only
   uncertainty instrument.
2. **Phase B** adds typed legal relations and re-clusters the frozen Phase A
   answers.
3. **Phase C** adds a deterministic statute store, validity windows,
   IPC/BNS links, and context packs.
4. **Phase D** detects whether agreement is legally warranted using observed
   agreement, temporal validity, jurisdiction fit, and contradiction mass.
5. **Phase E** consumes stored Phase D fields in a monotone uncertainty model
   with an explicit sample-only fallback.
6. **Phase F** calibrates that score per stratum and applies a harm-weighted
   answer / verify / abstain policy with a conformal coverage layer.
7. **Phase G** builds (and must first measure) the target population without
   which G5 and the L7 half of G6 cannot be evaluated at all.

The phases are deliberately separated: Phase C/D/E write sibling runs and
leave their source runs unchanged. Phase E never recomputes Phase D outputs.

## Compute and cost

All inference runs locally through LM Studio on this machine. No accelerator is
used: PyTorch reports `2.9.1+cpu`, with CUDA, MPS, and XPU unavailable.
Inference and relation-model training therefore run on CPU. The project spent
nothing: no paid API calls, subscriptions, or billing.

The primary Phase A run remains `qwen2.5-7b-instruct`, with the frozen
`p2-structured` prompt; it is the source of the 2,000 Phase A samples and all
Phase B-E numbers. `Qwen3-14B Q4_K_M` (about 9 GB) was screened locally with
reasoning on and off: it answered IPC 379 to a post-1-July-2024 theft question
and scored 0% on L7. It is a screen only; no slice was regenerated with it.
Gemini API screening found 2.5-flash unavailable, 3.8-flash returning 503,
and 3.6-flash exhausting the free-tier daily quota (HTTP 429). Under the
zero-cost constraint no API model was used.

The Qwen3-14B local pilot screen (reasoning off, 24 items, 12 per slice)
completed in 1,373 seconds with 100% judge coverage. Per-sample accuracy was
L7 `0.00` and L1 `0.56`; the verdict mix was `stale_law=33`,
`wrong_section=19`, `gold=16`, and `gold_operative=4`. This did not alter the
frozen slice: the primary run remains `qwen2.5-7b-instruct`.

Under this constraint L7 has no correct items, so G5 remains
**NOT_EVALUABLE** and the L1-L7 comparison cannot be made. Per master-guide
section 16.4, the failed G2 directs the project to its diagnostic
contribution: Phase A plus the Phase D temporal detector. This is a finding
about the model class under test, not a defect in the instrument.

### Registry status through Block 8

| Registry | Status |
|---|---|
| Files, fields, configs, scripts, and experiment outputs from Blocks 1-8 | registered in the phase guides and run metadata |
| E5 / G5 | implemented and recorded as **NOT_EVALUABLE** |
| Frozen dataset / statute / link digests | verified in every new context, warrant, typed, and uncertainty run metadata |
| Aborted API/debug runs | deleted; no API-key patterns remain in `runs/**/meta.json` |

The full repository suite was run in this environment with
`python -m pytest -q`: **160 passed**.

## Current status

| Phase | Status | Run or record of reference |
|---|---|---|
| A | Complete and frozen | `runs/phaseA-laptop-v2-rejudged/` |
| B | Implemented; run of record complete; supplemental evaluations retained | `runs/phaseB-relations-full/` |
| C | Engineering complete; four mappings corrected and eight target rows verified from documented statutory text | `runs/phaseA-laptop-v2-rejudged+ctx/` |
| D | Typed-cluster rerun complete; G4 PASS; CM coverage limited by 13 unresolved records | `runs/phaseA-laptop-v2-rejudged+ctx-r2+typed+warrant/` |
| E | Two-variant typed-run evaluation; G5 NOT_EVALUABLE | `runs/phaseA-laptop-v2-rejudged+ctx-r2+typed+warrant+uq-typed/` and `...+uq-exact/` |
| F | Implemented and evaluated; G6 NOT_MET (control-slice calibration and selective risk fail, L7 stratum unevaluable). Conformal figures superseded by the follow-up run `+cal-r2`; the original `+cal` is preserved unchanged | `runs/phaseA-laptop-v2-rejudged+ctx-r2+typed+warrant+uq-exact+cal/` (see also `...+cal-r2/`) |
| G | Infrastructure implemented; §21.2 matrix and §21.3 deployment measurements computed offline; G7 is defined and **NOT_MET** (no target slice on which a ranking is defined). **API pilot ON HOLD** for resource reasons — no model output obtained. G5 NOT_EVALUABLE, G6 NOT_MET | `runs/phaseG_eval_matrix.json`, `runs/phaseG_deployment.json`, `runs/phaseG_pilot_status.json` |

Phase E's target holdout contains only incorrect L7 answers, so its L7 AUROC
is undefined and no G5 pass is claimed. The score is an uncalibrated risk
ranking, not a probability.

### Block 5b attribution-controlled evaluation

Block 5b added four new sibling runs and did not modify the frozen Phase E
outputs. Missing legal factors use the fitted sample-only degradation
(intercept + `u_prov` + `u_text` + `u_prov*u_text`), with
`uq_score_mode=sample_only_degraded`; all four runs have 187 legal-aware and
13 degraded records, with no raw fallback or unscorable records. The pooled
models use 156 development and 44 holdout records; the L1-only models use 78
development and 22 holdout records and are evaluated only within L1.

| Fit / variant | Evaluation | AUROC | AUPRC | nAURC | risk@50% | baseline AUROC |
|---|---|---:|---:|---:|---:|---:|
| pooled / typed | L1 (22) | 0.6238 | 0.7243 | 0.3963 | 0.5455 | 0.6381 |
| pooled / exact | L1 (22) | 0.6905 | 0.7568 | 0.5054 | 0.5455 | 0.8714 |
| L1-only / typed | L1 (22) | 0.5714 | 0.7129 | 0.3358 | 0.5455 | 0.6381 |
| L1-only / exact | L1 (22) | 0.8714 | 0.9349 | 0.7078 | 0.4545 | 0.8714 |

The L7 holdout in pooled runs is 22/22 incorrect, so AUROC and nAURC are
undefined (AUPRC 1.0 and risk@50% 1.0 are reported descriptively). L1-only
runs have no L7 evaluation population. Pooled paired AUROC differences
(score minus baseline) are -0.0143 (typed, 95% CI [-0.1458, 0.0882]) and
-0.1810 (exact, [-0.5000, 0.0000]); L1-only differences are -0.0667
([-0.3158, 0.1880]) and 0.0000 ([0.0000, 0.0000]). G5 remains
NOT_EVALUABLE. The exact-key variant is the like-for-like comparison with the
frozen pilot; neither variant is selected.

For the exact-key pooled L1 holdout, 20 records were legal-aware and 2 were
degraded fallbacks; both fallbacks were incorrect. On the identical
legal-aware subset, learned-score AUROC was 0.6868 versus exact `u_prov`
0.8626. On the full L1 holdout after degradation rescaling, the corresponding
values were 0.6905 and 0.8714. This is a negative result, not an imputation
artifact. Typed entropy is exactly zero on 106/200 records (exact-key 33/200);
the frozen pilot's 32 legal-aware records all had `u_prov=0`, explaining its
zero fitted `u_prov` weight.

### Structural limitation of the current instrument

The temporal factor is constant within each slice: `T=1.0` on 94/94
resolvable L1 records and `T=0.0` on 80/81 resolvable L7 records. With
`J=1` and `K` approximately zero, `W=A` on L1 and `W=0` on L7. Thus `u_cm`
is identically zero on L1, and `u_warrant` is only a function of observed
agreement `A`, already encoded by `u_prov`. The legal-aware components have no
within-slice information: zero variance on L1 and a single correctness class
on L7.

This explains the exact L1-only result (AUROC `0.8714` versus baseline
`0.8714`; paired difference `0.0000`, interval `[0.0000, 0.0000]`) and the
pooled exact result falling to `0.6905` within L1 because it uses `u_warrant`
and `u_cm` as slice indicators. Therefore G5 cannot be satisfied by any
estimator, hyperparameter, or ablation on this instrument. G5 requires a
slice with both correctness classes where the detector both fires and stays
silent. Building that population is Phase G work and the sole remaining G5
blocker.

Block 6 is a typed-representation trustworthiness check, not a route to G5:
typed entropy is zero on 106/200 records versus 33/200 under exact keys, and
`DIFFERENT_PROVISION` recall is `0.00`. It cannot create the missing variance
in `T`. The expensive chain will be rerun once, after the two-class target
population exists.

Block 6 subsequently improved the relation model without rerunning the
downstream chain. `relations_v2` combines synthetic and observed Phase A pairs
(1,520 kept; 918/294/308 train/dev/test) and was trained for 12 epochs in
5,980 seconds. On its 308-pair test split, macro-F1 is 0.9942 versus the
0.7941 exact-key baseline (margin +0.2001), and
`DIFFERENT_PROVISION` precision/recall/F1 are 1.0000/0.9726/0.9861.
Separately thresholded merge precision/recall are 0.9753/1.0000 at
`tau=0.05`.

The gold/trap probe merge rates are L1 `0/10` at both 2024-01-01 and
2026-10-01, and L7 `1/10` and `2/10`, respectively. E2 changed items remain
a diagnostic (0 L1, 1 L7); the corrected rescue count is 0 in both slices.
Thus corrected G2 is `NOT YET`: precision, macro-F1, and integrity pass, but
the required unanimously-wrong collision rescue does not occur. G5 remains
blocked by the missing within-slice temporal-factor variance, independently
of this relation-model improvement.

### Phase F — calibration and the decision layer (M9/M10)

Phase F converts the uncalibrated Phase E score into a per-stratum
`p_reliable` (isotonic regression, Platt scaling for small strata, grouped
K-fold grouped by slice and offence cluster) and then into a decision
(`answer` / `verify` / `abstain`) using a harm-weighted loss comparison rather
than a coverage target. A split-conformal layer reports an approximate,
finite-sample coverage threshold with its exchangeability assumption stated.
The query path is label-blind: `scripts/30_apply_policy.py` reads only a
whitelist of fields and never reads `majority_correct`, `sample_correct`,
`gold` or `trap` when scoring, and the validator checks that statically by
parsing the script.

The phase is implemented and evaluated end to end in under a second on CPU, and
**Gate G6 is NOT_MET**:

| G6 condition | Threshold | Measured | Verdict |
|---|---|---|---|
| Calibration quality (development, cross-fitted) | ACE ≤ 0.05 | 0.2797 (L1, n=78) | FAIL |
| Harm-weighted selective risk at 50 % coverage | below every baseline | 0.5455 vs 0.4545 (sample-only) | FAIL |
| Conformal coverage within sampling tolerance | empirical ≥ target − tol | 0.8636 ≥ 0.80 − 0.1671 | pass |
| No labels on the query path | static check | label-blind | pass |
| Target stratum evaluable | both classes | L7 has 0 correct of 100 | not evaluable |

Two structural notes, both recorded in the run: a monotone calibration map
cannot change the ranking, so selective risk equals the raw score's by
construction and only a different score is an informative baseline; and on this
slice every offence cluster resolves to `custodial`, so harm weighting is a
constant multiplier here. The L7 stratum is single-class, so `p_reliable` is
`null` for all 100 L7 records and they take the declared `verify` action rather
than receiving an imputed probability. G6 cannot pass until Phase G builds a
target slice with both correctness classes; see `PHASE-F.md` for the full E6
record, the descriptive isotonic-versus-Platt sensitivity, and the limitations.

With Phase F added the suite is **216 passed, 1 skipped** (57 new Phase F tests;
the skip is the pre-existing torch-gated Phase B test).

#### Phase F follow-up (post-merge audit)

Four follow-up experiments re-examined the E6 record. The conformal threshold
had been taken from the same holdout items its coverage was measured on; that is
corrected in a **new sibling run** (`+cal-r2`, original `+cal` preserved), which
moves coverage from 0.8636 to 0.6818 and the threshold from 0.3855 to 0.4702
**without changing the G6 verdict**. The other three: an L1-only refit of the
Phase E legal head raises within-slice AUROC from 0.687 to 0.863 on the same 20
items, a pre-registered input-range rule selects Platt over isotonic (dev
cross-fit ACE 0.0911 vs 0.2797, both still above `ace_max = 0.05`), and
topic-clustered bootstrap intervals show the ACE failure is stable under
resampling while the selective-risk gap is unresolvable at n=78. No gate
constant changed. Full record:
[`PHASE-F-FOLLOWUP.md`](PHASE-F-FOLLOWUP.md); suite is now **270 passed, 1
skipped**.

### Phase G — target population, the §21 evaluation matrix, and a pilot on hold

Phase G is the guide's "measure everything" phase (§12, §21.1–21.3). Both G5 and
the L7 half of G6 are blocked on one thing: no evaluation population has both
correctness classes. The guide defines **Gate G7** for exactly this — "the target
slice carries both correctness classes and the headline comparison is
computable", failing when "no target slice exists on which a ranking is
defined".

> **Correction.** Earlier revisions of this README, `PHASE-G.md` and
> `configs/phase_g_target.json` said the repository had no Phase G specification
> and no Phase G gate. That was inaccurate and is retracted. The specification
> exists; it lives in the project's external engineering guide, which is why its
> text was not to hand. G7 is a defined gate, and it currently **fails**.

§21.2's evaluation matrix and the offline half of §21.3 are now implemented
(`jurisuq/evaluation/`, `scripts/42`, `scripts/43`) and computed from the frozen
runs — no new generation. On the frozen evaluation partition, 44 items:

| Method (larger score = more uncertain) | L1 AUROC | L7 AUROC |
|---|---:|---|
| exact agreement | 0.5714 | undefined — single class |
| lexical similarity | undefined — not implemented | undefined — not implemented |
| discrete semantic entropy | 0.5714 | undefined — single class |
| standard semantic entropy | 0.4857 | undefined — single class |
| SelfCheck | 0.5905 | undefined — single class |
| p_true | undefined — no logprobs | undefined — no logprobs |
| provision agreement | 0.8333 | undefined — single class |
| legal-aware | 0.6524 | undefined — no calibrated score |
| legal-aware, uncalibrated | 0.6524 | undefined — single class |

Judge coverage is 1.0000 per slice. **G7 is NOT_MET**: L7 has 0 correct of 100
items, so no ranking is defined there, and the calibrated arm is fitted on L1
only. Stage-1 latency is measured (n=200, median 45.02 s, p95 67.41 s); full
cascade latency and peak memory are `not_instrumented` and await a laptop run.
Twenty-two items with 7 correct cannot rank methods, so no ordering is claimed.

#### API pilot: ON HOLD

**A resource-driven postponement, not a scientific finding and not evidence of a
failed detector.** Machine-readable record:
[`runs/phaseG_pilot_status.json`](runs/phaseG_pilot_status.json).

| | |
|---|---|
| **Completed** | the specification correction, the §21.2 matrix, the offline §21.3 measurements, the target-population audit and yield screen, and an approval-gated pilot harness with 53 guard tests. The approved DeepSeek plan was produced offline without generation. |
| **Attempted, unsuccessful** | the DeepSeek smoke check (2 requests, `phaseG-pilot-v1-smoke`) returned **HTTP 402 Insufficient Balance on both requests**. No completion was returned, so no output, usage or accuracy exists to analyse. Cost incurred: zero. |
| **On hold** | the same smoke check against an alternative free provider, and the full 240-request pilot. Neither has run. No free-provider code path was added, so there is no untested branch and no silent paid fallback. |
| **Reason** | no confirmed zero-cost configuration can carry 240 requests. The free Gemini quota visible in AI Studio is 20 requests/day for 2.5 Flash-Lite — 12 days for the pilot — and a Gemini arm would additionally be a protocol deviation (no documented log-probabilities on the compat endpoint; thinking cannot be disabled on 3.x and its minimum budget exceeds `max_tokens` 220). A local model is not an automatic substitute: its knowledge of the July 2024 IPC→BNS transition is unestablished. |
| **Restart conditions** | a zero-cost tier or funding appears; the exact model ID is verified as served; quotas and billing status are confirmed; a fresh approval hash is issued; and a 2-request smoke check succeeds before any full run. A multi-day run is deferred, not rejected, and needs a validated resume path first. |

The approved DeepSeek plan and its hash
(`eb06ed62…`, `runs/phaseG_pilot_plan.json`) are preserved unchanged. A different
provider is a different experiment and would require its own configuration,
plan, hash and smoke check — it must never reuse that approval.

The audit (`scripts/40_audit_target_feasibility.py`, read-only) establishes that
**no valid target population exists in the frozen artefacts**:

| Population | correct / incorrect | detector fired / silent | detector AUROC | status |
|---|---|---|---|---|
| L1 | 43 / 57 | 0 / 61 (37 partial) | 0.4890 (chance) | NOT_READY |
| L7 | 0 / 100 | 82 / 7 | undefined | NOT_READY |
| L1 + L7 | 43 / 157 | 82 / 68 | 0.7720 | NOT_READY (confounded) |

The pooled 0.772 is an artefact: the detector scores 0.9458 against
`slice == L1`, and within the only two-class slice it is at chance. Separately,
the L7 zero is not a comparator artefact — 0 of 1,000 samples across ten offences
assert the gold section in any form. **G5 stays NOT_EVALUABLE and G6 stays
NOT_MET.** Building the population needs new items and new generation, which is
an open, costed checkpoint in `PHASE-G.md`.

**Stage 2 status: partial.** A 24-item candidate set exists
(`data/lexuq_target_candidates_v1.jsonl`, 12 L1 / 12 L7, 8 offences, every item
`provenance.verified = false` and `PENDING_HUMAN_REVIEW`), with a per-item source
record in `runs/phaseG_candidate_sources_v1.json`.

The target-yield screen **has been run** on Qwen3 14B via LM Studio, and its
three artefacts are committed:

| Report | Scope | Result |
|---|---|---|
| `runs/phaseG_screen_qwen3_14b_full.json` | 24 items × 10 samples | **3/24 majority-correct**, rate 0.1250, 95% interval [0.0434, 0.3100], 34/240 correct samples (0.1417), projection 172 items, $0.00 |
| `runs/phaseG_screen_qwen3_14b_sliced.json` | same design, separate run, **per-slice** | **L1 3/12** (0.250, 32/120 samples); **L7 0/12** (0.000, **0/120 samples**) |
| `runs/phaseG_screen_qwen3_14b_smoke.json` | **2 items only** | smoke test, not an evaluation; 0/2, not projectable |

The full and sliced files are **two independent runs**, not one run reported
twice: they agree on 3/24 majority and differ on correct samples (34 vs 32).
Neither supersedes the other and their sample counts must not be pooled.

The sliced run answers the question the full run could not: **every correct item
is L1, and L7 produced no correct sample at all in 120 generations.** The cause
has since been investigated in
[`PHASE-G-L7-INVESTIGATION.md`](PHASE-G-L7-INVESTIGATION.md): on L7 items of this
design the model writes the **repealed IPC provision** — the committed
`qwen3-14b` frozen-slice pilot labels 33 of 36 L7 samples `stale_law` and none
correct — and the judge is not the cause, since the same run scored 32/240 correct
samples on L1 with the same parser. That is corroboration from a different item
set, not a direct measurement of these twelve items: the screen harness discarded
its per-item records, which is now fixed (`--save-items`). Gold labels remain
unverified pending human legal review.

Because the aggregate rate that produces the 172-item projection is carried
entirely by L1, a larger run cannot be expected to create an L7 correct class, and
without one **G7 remains `NOT_MET`**. Human legal review is outstanding
(`provenance.verified = false` throughout). Full reports:
[`PHASE-G-STAGE2.md`](PHASE-G-STAGE2.md) and
[`PHASE-G-L7-INVESTIGATION.md`](PHASE-G-L7-INVESTIGATION.md).

The screen can now be aimed at one slice: `--slice L7` narrows the run to L7
before the item cap (so `--slice L7 --items 12` is twelve L7 items, not six of
each), refuses a slice the file does not contain, and leaving the flag out
screens every slice exactly as before. The report records `slice_filter`, and
`--save-items PATH` writes one JSONL record per item — the sampled text, the
judge label and the reason — which is the evidence the aggregate report cannot
carry. **The L7-only diagnostic that uses both flags has been run** (2026-10-27,
qwen3-14b): 12 items × 3 samples, **0/12 majority correct, 0/36 correct samples**,
Wilson 95% interval [0.0, 0.2425], with all twelve items `stale_law` and every
sample asserting a repealed code. An earlier attempt was labelled with a
placeholder model id and is **not** attributable to Qwen3-14B; the two are kept
apart in [`PHASE-G-L7-INVESTIGATION.md`](PHASE-G-L7-INVESTIGATION.md) §3.4. Gold
labels remain unverified, and the comparison that would follow review has not
been run.

Authoring items cannot move G7 on its own — the gate is defined over *measured*
correctness classes from a stored run, and a set of questions with no answers
cannot enter that grid. Correctness is computed (`pipeline.py`, `majority_correct`),
never authored, so the dataset deliberately carries no correctness labels.

Building the population is Stage 2, and its first step is now enforced in code
rather than left to prose. Stage 2 begins by authoring a candidate item set "in
the Phase A schema with `verified: false` provenance"; `jurisuq/target/candidates.py`
checks exactly that before `scripts/41` screens anything, and the screen's report
records the candidate file's `data_sha256` so a yield cannot be quoted against a
different item set. The contract also states in the artefact what it does *not*
establish — legal correctness, answerability and every gate are outside it. No
candidate item set exists yet and none was invented, so Stage 2 remains blocked
on authoring input.

The suite is now **589 passed, 1 skipped** (319 Phase G tests: 34 population
screening + 36 yield screen + 52 candidate-set contract and dataset + 18
screen-report provenance + 39 evaluation matrix + 32 deployment + 51
documentation guards + 57 pilot guards). With the screening artefacts committed,
none of the screen-report checks skip any more; the single remaining skip is the
pre-existing torch gate. Reports:
`runs/phaseG_eval_matrix.json`, `runs/phaseG_deployment.json`,
`runs/phaseG_pilot_status.json`.

## Documentation map

Project-level documents, read first:

- [`PROFESSOR-SUMMARY.md`](PROFESSOR-SUMMARY.md) — the research question,
  architecture, the evidence that exists, what is provisional, and the next
  experiment, in one page.
- [`STATUS.md`](STATUS.md) — the authoritative per-phase status: implemented
  components and paths, tests actually run, artefacts and hashes, remaining
  implementation and experimental work, human dependencies, the status label for
  each phase, and the exact action that resolves each blocker.
- [`ROADMAP.md`](ROADMAP.md) — the dependency order for the remaining work, with
  the blocked milestones and their unblock conditions.
- [`DEMO.md`](DEMO.md) — quick start for Windows PowerShell and POSIX, the
  one-command offline demonstration, expected outputs, and the difference between
  a mock, a fixture and a real run.

Canonical phase guides, each containing implementation details and the complete
historical results record:

- [Phase A guide](PHASE-A.md) — sampling, judging, analysis, reproduction,
  E1/G1 results, dataset hash, and historical run notes.
- [Phase B guide](PHASE-B.md) — relation data, training, evaluation, E2,
  metrics, confusion matrix, G2 interpretation, and limitations.
- [Phase C guide](PHASE-C.md) — statute store, context-pack workflow,
  verification evidence, hashes, coverage, and test records.
- [Phase D guide](PHASE-D.md) — warrant detector, E4 metrics, confidence
  interval, ablation, G4, integrity hashes, and legal limits.
- [Phase E guide](PHASE-E.md) — legal-aware scoring, fallback behavior, paired
  AUROC interval, G5 status, and separate environment test records.
- [Phase F follow-up](PHASE-F-FOLLOWUP.md) — the four post-merge experiments,
  corrected conformal provenance, and clustered uncertainty.
- [Phase G Stage 2 report](PHASE-G-STAGE2.md) — the candidate item set, its
  data card and source record, the review that was and was not performed, the
  three committed screening runs, and why G7 is unchanged.
- [Phase G L7 investigation](PHASE-G-L7-INVESTIGATION.md) — why the L7 arm
  yields nothing, the evidence that the generator asserts the repealed IPC
  provision, the harness defect that hid it, the candidate provenance audit, and
  the human review checklist.
- [Phase G guide](PHASE-G.md) — the corrected specification status and Gate G7,
  the §21.2 evaluation matrix with its undefined reason codes, the §21.3
  deployment measurements, the target-population readiness check, the
  feasibility audit, the pilot harness, and the API pilot's hold with its
  reasons and restart conditions.
- [Phase F guide](PHASE-F.md) — calibration maps, grouped cross-fitting, the
  decision policy, the conformal layer, E6 results, and the G6 verdict with its
  failure conditions and limitations.

[Deployment and troubleshooting](DEPLOYMENT-GUIDE.md) contains operational
setup notes and known environment issues. The machine-readable source records
remain under `runs/`; do not replace them with README summaries.

## Architecture

```text
Phase A: generator -> normalization/judge -> clustering -> metrics
              |
Phase B: typed relation dataset/model -> re-clustering of frozen A answers
              |
Phase C: statute table + IPC/BNS links -> immutable context-packed run
              |
Phase D: context + stored answers -> A/T/J/K, W, CM, flags
              |
Phase E: sample statistics + stored W/CM/K -> monotone risk score/fallback
Phase F: stored score + flags -> per-stratum p_reliable, conformal threshold,
         answer / verify / abstain with a reason
Phase G: stored runs -> population readiness audit; candidate-item yield screen
```

Primary modules are in [`jurisuq/`](jurisuq/): core pipeline and metrics,
`relations/` for Phase B, `context/` for Phase C, `warrant/` for Phase D,
`uncertainty/` for Phase E, `calibration/` for Phase F, and `target/`
(including the Stage 2 candidate contract in `target/candidates.py`) and
`evaluation/` for Phase G.
Scripts are numbered by phase: `00`–`06` (A), `10`–`13` (B), `20`–`22` (C),
`23`–`27` (D/E), `29`–`31` (F, with follow-up experiments `32`–`34`) and `40`–`44` (G).

## Requirements and installation

Supported runtime: Python 3.11 or newer (3.11/3.12 generally have the widest
binary-wheel compatibility), Git, and a virtual environment. The repository
is not packaged as an installable wheel.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

On macOS/Linux, activate with `source .venv/bin/activate`.

`requirements.txt` contains shared/core packages (`requests`, `numpy`,
`matplotlib`, and `pytest`). Install optional or phase-specific packages only
when needed:

```bash
# Phase A standard semantic-entropy/NLI backend
python -m pip install -r requirements-phase-a.txt

# Phase B relation model (install the suitable PyTorch wheel first)
python -m pip install -r requirements-phase-b.txt
```

Phase C and D add no Python packages beyond the shared file. Phase E is also
stdlib-only beyond the shared test/runtime environment. The NLI and relation
files may download model checkpoints at first use; they are not external legal
sources. Real Phase A runs additionally require an OpenAI-compatible local
server such as LM Studio or `llama-server` at the configured endpoint. GPU/XPU
support depends on the platform-specific PyTorch wheel.

## Recommended verification

Run from the repository root:

```bash
python -m pytest -q
python scripts/00_env_check.py --skip-endpoint
```

**Current suite (2026-10-27, Python 3.11.2, CPU-only sandbox): `650 passed, 1
skipped` in about 9 s.** The one skip is the optional `torch`/`transformers`
path, which needs the Phase A optional requirements; it is a genuine dependency
skip, not a weakened test. Re-run the command for the count on your machine.

The per-block counts quoted further up this file (160, 216, 270, 589 …) are
**historical records** of the suite at the time each block was merged. They are
not claims about the present suite; only the line above is.

Offline end-to-end demonstration of the implementation (no model, no network):

```bash
python scripts/47_demo.py
```

It verifies the frozen-input hashes, re-runs the target-population audit, the
§21.2 matrix, the §21.3 deployment summary and a mock plumbing screen into
`runs/demo/`, and prints the gate verdicts exactly as stored. See
[`DEMO.md`](DEMO.md).

Focused deterministic checks:

```bash
python -m pytest tests/test_context.py -q
python -m pytest tests/test_warrant.py -q
python -m pytest tests/test_uncertainty.py -q
python -m pytest tests/test_calibration.py tests/test_policy.py -q
```

The checked-in Phase E record reports 149 passed and 1 skipped in the sandbox,
147 passed in a historical Windows PowerShell run, and 149 passed in the latest
post-change Windows PowerShell run. These are separate environment-specific
records, not a fresh-environment claim.

## Reproduction entry points

Use a new run suffix for generated outputs; do not overwrite frozen runs.

```bash
# Phase A shipped-run analysis (no new model answers)
python scripts/03_analyze_e1.py --run-id phaseA-laptop-v2-rejudged
python scripts/04_make_figure.py --run-id phaseA-laptop-v2-rejudged

# Phase B dataset verification
python scripts/10_build_relations.py --verify-only

# Phase C
python scripts/20_build_statutes.py --out data/statutes/statutes_v1.jsonl
python scripts/21_attach_context.py --run-id phaseA-laptop-v2-rejudged --out-suffix +ctx-repro --as-of 2026-10-01

# Phase D (requires the Phase C +ctx run)
python scripts/23_detect_warrant.py --run-id phaseA-laptop-v2-rejudged+ctx --out-suffix +warrant-repro

# Phase D typed-cluster rerun (requires the rebuilt Phase C +typed run)
python scripts/23_detect_warrant.py --run-id phaseA-laptop-v2-rejudged+ctx-r2+typed `
  --out-suffix +warrant --cluster-source typed --contradiction-source rule
python scripts/24_validate_warrant.py --run-id phaseA-laptop-v2-rejudged+ctx-r2+typed+warrant
```

The phase guides contain complete commands, inputs, outputs, smoke modes,
Windows variants, and integrity precautions. `run_phase_a.sh smoke` is
non-production plumbing only: it rewrites the checked-in data slice and must
be run in a disposable worktree.

## Historical results that must not be conflated

The project preserves the original metrics rather than normalizing them:

- Phase A L7 AUROC is undefined because all 100 scored L7 answers are wrong;
  its provision-level collision population is 16/100 and all 16 are wrong.
- Phase B test macro-F1 is 0.7770 versus the 0.7765 exact-key baseline;
  all six errors are false merges, and the L7 typed collision population is
  44 with accuracy 0.0000. The supplemental full E2 evaluation in
  `runs/full/relation_report.json` reproduces G2 PASS with 130 changed items
  in 636.6 seconds; `runs/relations-full/relation_report.json` is a
  metrics-only run with E2 skipped and is not a G2 verdict.
- Phase C contains 48 statute rows. The eight target rows are now verified from
  user-transcribed text from a government-hosted IPC reproduction, the enacted
  BNS Act text, and the BNS section 1 commencement footnote. The 40 existing
  overrides retain their prior secondary-supported provenance and are not
  newly primary-source verified. Current table SHA-256:
  `ef50705e99b3ba8de8287df0e289c3df2dd5a4f648ccd58bdb9a9afd2c682b18`.
  Context coverage remains 0.689034 (421 known of 611 asserted-reference
  lookups; the separate validity-entry count is 890 because each record's gold
  and trap keys are also packed).
- Phase D reports CM AUROC 0.9412 with bootstrap 95% CI [0.8529, 1.0000],
  binary TP/FP/TN/FN 16/0/15/2, and G4 PASS; temporal ablation carries all
  above-chance separation. The typed rerun preserves the collision population
  at n=33 and the same AUROC/CI. It defines CM for 187/200 records; 13 remain
  undefined because a required factor is unresolved. The rule contradiction
  channel uses all 10 `different_offence` crosswalk rows, all of which carry
  `verified: false`: K is non-zero on 4/200 records, always 0.3, and the
  internal-contradiction flag fires 4 times. The typed modal cluster contains
  both the gold and trap keys on 0 records overall (0 L1, 0 L7). This
  contradiction measurement inherits the crosswalk verification gap.
- Phase E Block 5 evaluates both `typed_stats.entropy_norm` and the
  like-for-like `methods.prov_se / log2(n_samples)` variant. Both runs use a
  156/44 development/holdout split, with 150 legal-complete development rows
  and modes 187 legal-aware / 13 sample-only fallback. On L1, typed scores
  AUROC 0.5476, AUPRC 0.6978, nAURC 0.0417, risk@50% 0.5455 versus its
  baseline AUROC 0.6381, AUPRC 0.8019, nAURC 0.2681, risk@50% 0.5455;
  exact scores AUROC 0.6524, AUPRC 0.7516, nAURC 0.2624, risk@50% 0.5455
  versus baseline AUROC 0.8714, AUPRC 0.9349, nAURC 0.7078, risk@50%
  0.4545. L7 AUROC and nAURC are undefined because the holdout has one
  correctness class; AUPRC and risk@50% remain defined. Paired AUROC
  differences are -0.0905 [−0.2500, +0.0427] for typed and -0.2190
  [−0.5235, 0.0000] for exact. The exact variant is the like-for-like
  frozen-pilot comparison; neither variant is selected.
- The typed gold/trap diagnostic is 0/200 (L1 0, L7 0); sample-level
  co-occurrence is L1 gold-only 69 / neither 31 and L7 trap-only 52 /
  neither 48. False-merge risk across the transition is unmeasured.
- The typed Phase D run changed flag sets on 12 records: 10 old-only fires
  (all old `unresolvable_assertion` flags cleared after typed modal clusters
  enlarged) and 2 new-only fires (both `internal_contradiction`, L1 murder
  items with modal `IPC 302` and non-modal `IPC 307`). This explains the
  base-rate movement from the old run's correct-item alarm 0.000 and
  wrong-item alarm 0.640 to 0.071 and 0.568. It is not evidence that typed
  merging pulled a stale provision into an otherwise-correct modal cluster;
  the changed examples reflect unresolved-factor clearing and the newly
  enabled rule contradiction channel.
- Phase E reports 32 legal-aware scores and 168 sample-only fallbacks;
  L1 AUROC 0.9000 versus 0.8714 provision-entropy baseline, paired difference
  +0.0286 with 95% interval [−0.0417, +0.1500], and a legal-aware-only
  subset of three records with AUROC 0.7500. G5 remains NOT_EVALUABLE.

See the linked result documents for counts, source hashes, run IDs, confidence
interval methods, limitations, validation outcomes, and historical execution
records. Unknown legal provisions remain `None`, never stale/false.

## Data, integrity, and limitations

The checked-in 200-item data slice, relation dataset, statute table, manifests,
overrides, run records, and validation JSON files are research artifacts.
Phase C's current statute hash is
`ef50705e99b3ba8de8287df0e289c3df2dd5a4f648ccd58bdb9a9afd2c682b18`; the
Phase A and Phase B dataset hashes and Phase D/E run hashes are recorded in
their result documents. Source runs are tree-hashed before and after overlay
steps. Do not modify generated metrics or model outputs when documenting a new
run.

The benchmark is one synthetic 200-item matched construction and one
quantized 7B checkpoint. Phase B labels are rule-generated, not human
annotations. Phase C legal verification is incomplete, and the detector is a
temporal common-mode detector rather than a general correctness oracle. Phase E
does not provide calibration; later calibration and broader evaluation remain
future work.

## License and citation

No project license has been declared. Preserve the research and source
citations in the result records when reusing this code.
