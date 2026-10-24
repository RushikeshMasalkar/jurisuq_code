# JURIS-UQ

Legal-aware uncertainty quantification for LLM-based Indian legal question
answering.

> **Research prototype.** JURIS-UQ is not a legal research service and does
> not provide legal advice. Its benchmark is scoped and partly synthetic, and
> Phase C legal verification is incomplete.

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
| F | Implemented and evaluated; G6 NOT_MET (control-slice calibration and selective risk fail, L7 stratum unevaluable) | `runs/phaseA-laptop-v2-rejudged+ctx-r2+typed+warrant+uq-exact+cal/` |

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

## Documentation map

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
```

Primary modules are in [`jurisuq/`](jurisuq/): core pipeline and metrics,
`relations/` for Phase B, `context/` for Phase C, `warrant/` for Phase D,
`uncertainty/` for Phase E, and `calibration/` for Phase F. Scripts are numbered by phase:
`00`–`06` (A), `10`–`13` (B), `20`–`22` (C), `23`–`27` (D/E) and `29`–`31` (F).

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
