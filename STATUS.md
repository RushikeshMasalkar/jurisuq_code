# JURIS-UQ — project status (authoritative)

**This is the single source of truth for what is finished, what is not, and what
each blocker needs.** The phase guides (`PHASE-A.md` … `PHASE-G.md`) own the
method and the full historical result records; this file owns the summary and
must not contradict them. If the two ever disagree, the phase guide and the
artefacts under `runs/` win, and this file is the thing to fix.

| | |
|---|---|
| Status date | 2026-10-27 |
| Branch of record | `main` |
| Full suite, actually run on 2026-10-27 | `python -X utf8 -m pytest -q` → **650 passed, 1 skipped** in about 9 s (651 collected; the skip is the optional torch/transformers path) |
| Offline demonstration | `python -X utf8 scripts/47_demo.py` — no model, no network |
| Gate summary | G1 PASS · G2 NOT YET · G3 NOT MET · G4 PASS · G5 NOT_EVALUABLE · G6 NOT_MET · G7 NOT_MET · pilot ON_HOLD |

**Two things this project is not.** It is not a legal service and gives no legal
advice. And "implemented and tested" is not "scientifically validated": only G1
and G4 currently pass, and both are scoped to one quantized 7B checkpoint, one
synthetic 200-item construction, and the artefacts actually stored here.

---

## 1. Status vocabulary

| Label | Meaning |
|---|---|
| `IMPLEMENTED` | code exists, is wired into the pipeline, and has tests |
| `TESTED` | the tests for that component were executed and passed in this environment |
| `BLOCKED` | cannot proceed without data, a model endpoint, or an external decision |
| `PENDING_HUMAN_REVIEW` | a qualified human has not signed off; an AI/machine check is not a substitute |
| `NOT_EVALUABLE` | the gate's own precondition is absent, so no verdict is possible |

A phase gets `IMPLEMENTED`/`TESTED` for its software and a **separate** label for
its science. Nothing below marks a phase experimentally complete because its
unit tests pass.

---

## 2. Phase status matrix

| Phase | Software | Science / gate | Human or external dependency | Next action |
|---|---|---|---|---|
| **A** sampling + common-mode diagnostic | `IMPLEMENTED`, `TESTED` | **G1 PASS** (scoped) | none | none — frozen |
| **B** typed legal relations | `IMPLEMENTED`, `TESTED` | **G2 NOT YET** (corrected) | relation labels are rule-generated, not human-annotated | needs a target population with a rescue collision |
| **C** statute store + context packs | `IMPLEMENTED`, `TESTED` | **G3 NOT MET** | statute verification is machine-assisted, `PENDING_HUMAN_REVIEW` | independent legal check of the 48 statute rows |
| **D** common-mode detector | `IMPLEMENTED`, `TESTED` | **G4 PASS** | 13 unresolved records limit coverage | none until Phase G data exists |
| **E** legal-aware uncertainty | `IMPLEMENTED`, `TESTED` | **G5 `NOT_EVALUABLE`** | needs a slice with both correctness classes | unblocked only by Phase G data |
| **F** calibration + decision layer | `IMPLEMENTED`, `TESTED` | **G6 `NOT_MET`** | same target-population dependency | same |
| **G** target population + §21 matrix | `IMPLEMENTED`, `TESTED` | **G7 `NOT_MET`**, pilot **ON_HOLD** | human legal review of 12 L7 golds; a model endpoint | §7 below |

### Gate summary, exactly as the artefacts record it

| Gate | Verdict | Where it is recorded |
|---|---|---|
| G1 | PASS | `PHASE-A.md` §Gate G1; `runs/phaseA-laptop-v2-rejudged/e1_report.json` |
| G2 | NOT YET (corrected) | `PHASE-B.md` §Gate G2 |
| G3 | NOT MET | `PHASE-C.md` §Block 7b |
| G4 | PASS | `runs/…+ctx-r2+typed+warrant/warrant_validation.json` → `gate_g4.verdict` |
| G5 | NOT_EVALUABLE | `PHASE-E.md` §6; `runs/phaseG_eval_matrix.json` |
| G6 | NOT_MET | `PHASE-F.md` §7; `runs/…+uq-exact+cal-r2/` |
| G7 | NOT_MET | `runs/phaseG_eval_matrix.json` → `gate_g7` |
| Pilot | ON_HOLD | `runs/phaseG_pilot_status.json` |

---

## 3. Phase detail

### Phase A — sampling and the common-mode diagnostic

- **Objective.** Build the sampling/judging/clustering instrument and measure
  whether sample agreement hides a shared legal error.
- **Implemented.** `jurisuq/{pipeline,generators,judge,normalize,cluster,metrics,facts}.py`;
  `scripts/01_make_data.py`, `02_run_inference.py`, `03_analyze_e1.py`, `04_make_figure.py`, `05_rejudge.py`, `06_pilot.py`.
- **Tests.** `tests/test_data.py`, `test_judge.py`, `test_normalize.py`, `test_cluster.py`, `test_metrics.py`, `test_pipeline_smoke.py`, `test_gate.py`.
- **Result.** G1 PASS on the L7 arm: 43.4 % correct on L1, 0/100 on L7;
  sample-only AUROC on L7 is undefined because the slice has one class.
- **Artifacts and reproducibility.** `runs/phaseA-laptop-v2-rejudged/`
  (`e1_report.json`, `items.jsonl`), dataset `data/lexuq_slice.jsonl`
  sha256 `89bc1180a4df76287768ce59432aa7ff0aa9d38c16d5f296ed16c3e45449bd53`,
  model `qwen2.5-7b-instruct` (quantized, local), `p2-structured` prompt, seed 20261005.
- **Remaining.** None. The run is frozen and must not be regenerated.

### Phase B — typed legal relations

- **Objective.** Replace exact-string clustering with typed legal relations and
  test whether that changes the cluster structure.
- **Implemented.** `jurisuq/relations/*`; `scripts/10_build_relations.py`,
  `11_train_relation.py`, `12_eval_relation.py`, `13_attach_typed.py`.
- **Tests.** `tests/test_relations.py`, `test_e2.py`, `test_attach_typed.py`.
- **Result.** `relations_v2` macro-F1 0.9942 on its 308-pair test split versus
  0.7941 exact-key baseline; **G2 is NOT YET** because the required
  unanimously-wrong collision rescue does not occur (0 in both slices).
- **Artifacts.** `runs/phaseB-relations-full/`, `runs/phaseB-7b-{generic,legal,adapted}/`,
  `data/relations/`.
- **Remaining implementation.** None. **Remaining experimental.** A target
  population that actually contains a rescueable collision — the same missing
  population that blocks G5/G7.
- **Human dependency.** Relation labels are rule-generated, not human-annotated;
  this is a stated limitation, not a blocker for the current verdict.

### Phase C — statute store and context packs

- **Objective.** Deterministic statute table, validity windows, IPC↔BNS links,
  context packs.
- **Implemented.** `jurisuq/context/*`; `scripts/20_build_statutes.py`,
  `21_attach_context.py`, `22_verify_statutes.py`.
- **Tests.** `tests/test_context.py`.
- **Artifacts.** `data/statutes/statutes_v1.jsonl` sha256
  `ef50705e99b3ba8de8287df0e289c3df2dd5a4f648ccd58bdb9a9afd2c682b18`
  (48 rows, 24 IPC / 24 BNS, 10 offence clusters);
  `runs/phaseA-laptop-v2-rejudged+ctx/`.
- **Gate.** G3 **NOT MET** — no encoder earns a passing representation-safety claim.
- **Human dependency — read this carefully.** All 48 rows carry `verified: true`
  and each override records an `official_source`, but those sources are
  **reproductions** (devgan.in) plus the MHA commencement notification, recorded
  through `scripts/22_verify_statutes.py --apply`. No qualified lawyer reviewed
  them. In this table `verified` therefore means *compared with a cited source*,
  **not** *human-approved*. Status: `PENDING_HUMAN_REVIEW`.
- **Next action.** An independent human read of the 48 rows using
  `data/statutes/verification_checklist.csv`; then decide whether the flag should
  be renamed (e.g. `source_checked`) to stop it reading as legal approval.

### Phase D — the common-mode failure detector

- **Objective.** Decide whether observed agreement is legally warranted, from
  agreement, temporal validity, jurisdiction fit and contradiction mass.
- **Implemented.** `jurisuq/warrant/*`; `scripts/23_detect_warrant.py`,
  `24_validate_warrant.py`.
- **Tests.** `tests/test_warrant.py`.
- **Result.** **G4 PASS**: separation AUROC 0.9412, 95 % CI [0.8529, 1.0000],
  n=32 collision records; pinning the temporal factor to 1.0 drops AUROC to
  0.5000, so the temporal factor carries the signal.
- **Artifacts.** `runs/phaseA-laptop-v2-rejudged+ctx-r2+typed+warrant/warrant_validation.json`.
- **Remaining.** 13 records remain unresolved, which caps collision coverage.

### Phase E — legal-aware uncertainty (M8)

- **Objective.** A monotone uncertainty score from stored Phase D fields with an
  explicit sample-only fallback.
- **Implemented.** `jurisuq/uncertainty/*`; `scripts/25`–`28`, `34`.
- **Tests.** `tests/test_uncertainty.py`.
- **Result.** **G5 `NOT_EVALUABLE`**: the target holdout contains only incorrect
  L7 answers, so AUROC is undefined there. The legal-aware factors are constant
  within slice (`T=1.0` on 94/94 resolvable L1, `T=0.0` on 80/81 L7), so no
  estimator or hyper-parameter on this instrument can satisfy G5.
- **Artifacts.** `runs/…+uq-exact/`, `runs/…+uq-typed/`, and the four Block-5b
  sibling runs; model JSONs `runs/phaseE*_model.json`; regression in
  `PHASE-F-FOLLOWUP.md` and Block 6b runs.
- **Remaining.** A slice with both correctness classes **and** both detector
  states. That is Phase G data.

### Phase F — calibration and the decision layer (M9/M10)

- **Objective.** Calibrate the Phase E score per stratum and apply a
  harm-weighted answer/verify/abstain policy with a conformal layer.
- **Implemented.** `jurisuq/calibration/*`; `scripts/29`–`33`.
- **Tests.** `tests/test_calibration.py`, `test_policy.py`, `test_method_selection.py`,
  `test_within_slice.py`, `test_uncertainty_intervals.py`.
- **Result.** **G6 `NOT_MET`**: ACE 0.2797 on L1 (target ≤ 0.05); selective risk
  at 50 % coverage 0.5455 versus 0.4545 for the sample-only baseline; conformal
  coverage passes; the query path is statically label-blind; the L7 stratum is
  not evaluable.
- **Artifacts.** `runs/…+uq-exact+cal-r2/` (run of record),
  `runs/phaseF_exp{2,3,4}_*.json`, `runs/phaseF_calibration_model*.json`.
- **Remaining.** Same population dependency; the follow-up document records four
  post-merge experiments and what they do and do not resolve at n=78.

### Phase G — target population and the §21 evaluation matrix

- **Objective.** Build (and first measure) a target population carrying both
  correctness classes, without which G5 and the L7 half of G6 cannot be evaluated.
- **Implemented.** `jurisuq/target/*`, `jurisuq/evaluation/*`;
  `scripts/40`–`46`, including the screen harness (`41`), the candidate-set
  contract (`jurisuq/target/candidates.py`), the §21.2 matrix (`42`), §21.3
  deployment measurements (`43`), the approval-gated pilot (`44`), the candidate
  builder (`45`) and the v2 reviser (`46`).
- **Tests.** `tests/test_target_population.py`, `test_target_candidates.py`,
  `test_target_candidates_v2.py`, `test_target_screen.py`,
  `test_target_screen_report.py`, `test_eval_matrix.py`, `test_deployment_metrics.py`,
  `test_phase_g_docs.py`.
- **Result.** **G7 `NOT_MET`** — no target slice exists on which a ranking is
  defined. Pilot **ON_HOLD** (no usable zero-cost provider in this environment).
- **Artifacts.** `runs/phaseG_eval_matrix.json`, `runs/phaseG_deployment.json`,
  `runs/phaseG_pilot_status.json`, `runs/phaseG_feasibility_audit.json`,
  `runs/phaseG_candidate_sources_v1.json`, `runs/phaseG_stage2_status.json`,
  `runs/phaseG_screen_qwen3_14b_{full,sliced,smoke}.json`,
  `runs/phaseG_l7_label_review_v1.json`, `runs/phaseG_l7_candidate_revisions_v1.json`.
- **Data.** `data/lexuq_target_candidates_v1.jsonl` sha256
  `f49f4d91946387eb0534718945092cc2f840bd9f2aee053ed9ac13c3f296d341` (screened);
  `data/lexuq_target_candidates_v2.jsonl` sha256
  `44e7b5a2f3f968a7523b071a972ef522894f7ad0453e7390dff728b020878e8c`
  (four revised L7 items, **never screened**).
- **Detail.** §7 below.

---

## 4. What "done" looks like for the software

| Layer | Component | Files | Status |
|---|---|---|---|
| data | frozen slice + candidate sets | `data/**` | `IMPLEMENTED` |
| generation | provider abstraction, guard, endpoint check | `jurisuq/generators.py`, `config.py` | `IMPLEMENTED`, mocked in tests |
| judging | provision judge + normalisation | `jurisuq/judge.py`, `normalize.py` | `TESTED` |
| clustering | lexical + NLI + typed | `jurisuq/cluster.py`, `relations/*` | `TESTED` |
| legal metadata | statutes, links, context packs | `jurisuq/context/*` | `TESTED` |
| detection | warrant tuple + validation | `jurisuq/warrant/*` | `TESTED` |
| uncertainty | features, estimator, IO | `jurisuq/uncertainty/*` | `TESTED` |
| calibration | maps, splits, policy, conformal | `jurisuq/calibration/*` | `TESTED` |
| evaluation | §21.2 matrix, §21.3 deployment | `jurisuq/evaluation/*` | `TESTED` |
| target population | contract, screen, yield, revisions | `jurisuq/target/*`, `scripts/40`–`46` | `TESTED` |
| **demonstration** | **one-command offline demo** | **`scripts/47_demo.py`**, `tests/test_demo.py` | `TESTED` |

---

## 5. Environment facts (this sandbox)

- Python 3.11.2; the suite runs in about 8 s here.
- `torch`, `transformers`, `scipy`, `sklearn` are **not installed**, so the real
  NLI clusterer and local generation cannot run here. Everything reported above
  is either stored from a prior local run or computed from stored artefacts.
- No generator is reachable at `http://127.0.0.1:1234/v1` in this environment.
- `configs/phase_a.json` is the repository copy: `model` is the literal
  placeholder `REPLACE_WITH_YOUR_MODEL_ID`. The principal investigator's local
  Qwen3-14B configuration is **not** present in this checkout and must not be
  committed if it contains machine-specific settings or keys.

### Files the principal investigator reported as local-only, verified absent here

`runs/phaseG_l7_diagnostic.json`, `runs/phaseG_l7_diagnostic_items.jsonl`,
`runs/phaseG_l7_qwen3_14b_diagnostic.json`,
`runs/phaseG_l7_qwen3_14b_diagnostic_items.jsonl`,
`runs/phaseG_l7_rehearsal.json`, `runs/phaseG_l7_rehearsal_items.jsonl` — **none
of these exist in this environment**, and `configs/phase_a.json` here is the
committed placeholder rather than the local endpoint configuration. Every figure
attributed to the 12-item diagnostic is therefore **operator-reported**, as the
status records already say. Nothing in this repository was fabricated to fill
that gap.

---

## 6. Known inconsistencies to resolve

1. **The word "verified" in the statute table** (see Phase C) reads as legal
   approval when it means source-compared. Documentation fix or field rename,
   after human review.
2. **The diagnostic artefacts are not committed**, so the 0/12 and 0/36 figures
   cannot be recomputed here. `PHASE-G-L7-INVESTIGATION.md` §11 carries the
   command that regenerates the item table once the files exist.
3. **Only the 12 L7 items were label-reviewed.** The 12 L1 items have had no
   AI-assisted review either.
4. **README suite counts are historical**, recorded at the time of each block
   (160, 216, 270, 589 …). They are records, not claims about today's suite; run
   the suite for the current number.

---

## 7. Phase G in detail, and what each blocker needs

| Item | State | Evidence | What unblocks it |
|---|---|---|---|
| Stage 2 screening (24 items × 10) | complete | `runs/phaseG_screen_qwen3_14b_{full,sliced}.json`; L1 3/12, **L7 0/12, 0/120 samples** | — |
| L7 diagnostic (12 items × 3) | **operator-reported**, artefacts absent | `PHASE-G-L7-INVESTIGATION.md` §3.4 | commit the two `runs/phaseG_l7_qwen3_14b_diagnostic*` files |
| AI-assisted label review | complete, **not human** | `reports/phaseG_l7_label_review_v1.md`, `runs/phaseG_l7_label_review_v1.json` (8 confirmed / 3 ambiguous / 1 unsupported) | — |
| v2 candidate set | authored, **never screened** | `data/lexuq_target_candidates_v2.jsonl`; `scripts/46_…py --check` | a decision to screen it |
| Cross-model comparison (§9) | **BLOCKED** | `PHASE-G-L7-INVESTIGATION.md` §9: "must not be run until §10 has an outcome" | independent human legal review, or an explicit, documented amendment of that sequencing rule |
| L7 calibration extension | **BLOCKED** | `PHASE-G.md`: calibrated arm is defined on L1 only (100/100, 0/100 on L7) | a stored L7 run with both classes |
| §21.3 laptop measurements | **BLOCKED** | `runs/phaseG_deployment.json` reports two values as undefined with reasons | a run on the target laptop with timings |

**The single most useful next experiment** is a screen of `v2` on the Qwen3-14B
endpoint (12 items × 3 samples, ≈11–27 minutes, $0). It is cheap and it would
replace four known-bad labels. It does **not** discharge the human review
prerequisite for the cross-model comparison, and it will not move G7.

---

## 8. How to verify this document

```powershell
python -X utf8 -m pytest -q
python -X utf8 scripts/47_demo.py
python -X utf8 scripts/46_revise_target_candidates_v2.py --check
python -X utf8 -c "from jurisuq.target import load_candidates as l; print(len(l('data/lexuq_target_candidates_v1.jsonl')), len(l('data/lexuq_target_candidates_v2.jsonl')))"
```

`tests/test_status_docs.py` checks that the hashes, counts and gate verdicts
quoted above match the artefacts, so this file fails CI when it drifts.
