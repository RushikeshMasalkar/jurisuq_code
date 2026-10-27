# JURIS-UQ — implementation roadmap

Companion to [`STATUS.md`](STATUS.md), which holds the authoritative per-phase
status. This file holds the **order of work**: what depends on what, what can be
done today without violating a prerequisite, and what cannot be done at all yet.

Nothing here overrides the protocol. A milestone that needs human legal review
or a model endpoint stays blocked until that prerequisite is genuinely met;
"finish the roadmap" is never a reason to relax it.

## 1. Ordering principle

```
data (frozen)  ──►  A sampling/judging  ──►  B relations  ──►  C statutes
                                                                   │
                                                                   ▼
                                             D detector ──► E uncertainty ──► F calibration/policy
                                                                                   │
                                                                                   ▼
                                                     G target population ──► G5 / G6-L7 / G7
```

Downstream phases consume stored artefacts of upstream phases; they never
recompute them. So the rule for new work is: **if it does not need a new model
run, it can be done now; if it does, it waits for the endpoint and the
prerequisites.**

## 2. Milestones

| # | Milestone | Depends on | Status |
|---|---|---|---|
| M0 | Phases A–F implemented, evaluated, gates recorded | frozen data | **done** (G1, G4 pass; G2, G3, G5, G6 as recorded) |
| M1 | Phase G infrastructure: audit, screen harness, §21.2 matrix, §21.3 deployment, pilot harness | M0 | **done** |
| M2 | Stage 2 candidate set + three screening runs | M1 | **done** (L7 0/12) |
| M3 | L7 investigation: why the L7 arm yields nothing | M2 | **done** (document); diagnostic **operator-reported** |
| M4 | AI-assisted label review of the 12 L7 golds | M3 | **done** — 8 confirmed / 3 ambiguous / 1 unsupported, no label changed |
| M5 | v2 candidate set with the four decided corrections | M4 | **done** — authored, never screened |
| M6 | Maintenance surface: authoritative status doc, dependency roadmap, one-command offline integrity check | M1–M5 | **done** |
| M7 | Screen `v2` (12 L7 items × 3 samples, ≈11–27 min, $0) | a local endpoint + the operator's go-ahead | **ready, unrun** |
| M8 | Cross-model comparison (`PHASE-G-L7-INVESTIGATION.md` §9) | human legal review of the labels | **BLOCKED** by protocol |
| M9 | L7 calibration extension | a stored L7 run with both correctness classes | **BLOCKED** (needs M7 + a two-class outcome) |
| M10 | §21.3 laptop measurements | a run on the target laptop with timings | **BLOCKED** on hardware |
| M11 | Independent human legal review of the 12 L7 golds and the 48 statute rows | a qualified reviewer | **PENDING_HUMAN_REVIEW** |

## 3. What can be done today, and what it costs

| Task | Needs a model? | Needs a human? | Cost |
|---|---|---|---|
| Run the suite, the offline check, `--check` on the v2 builder | no | no | seconds |
| Commit the diagnostic artefacts so the 0/12 / 0/36 figures become recomputable | no | no | — |
| Reconcile the statute table's `verified` flag with its actual semantics | no | yes (to approve the wording) | an hour of review |
| Screen `v2` on the local endpoint | **yes** | no (operator's call) | 11–27 min, $0 |
| Cross-model comparison | yes | **yes** | 11–27 min per model, $0 |
| Extend calibration to L7 | yes | no | minutes after data exists |

## 4. Explicitly out of scope until a prerequisite is met

- Any new gate, threshold, dataset membership or scoring rule.
- Regenerating the frozen Phase A slice, the Phase A–F runs, or the three Stage 2
  screening reports.
- Editing `data/lexuq_target_candidates_v1.jsonl` (screened, hash recorded in
  three reports) or silently repointing `configs/phase_g_target.json` from v1 to
  v2.
- Marking any candidate label `provenance.verified = true` on the strength of an
  AI-assisted review.

## 5. Definition of done for the software

1. `python -X utf8 -m pytest -q` green, with the skip explained.
2. `python -X utf8 scripts/47_offline_check.py` exits 0, writes
   `runs/offline_check/offline_check_summary.json`, and modifies nothing under
   `runs/` or `data/`.
3. `python -X utf8 scripts/46_revise_target_candidates_v2.py --check` reports that
   the committed v2 matches its builder.
4. `STATUS.md` agrees with the artefacts (checked by `tests/test_status_docs.py`).
5. The setup instructions in [`README.md`](README.md) work from a clean checkout
   with the documented dependencies only.
