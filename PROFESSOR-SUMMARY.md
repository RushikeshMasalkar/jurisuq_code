# JURIS-UQ — research summary

*One page for a reader who wants the question, the evidence, and the honest gaps.*

## The question

LLM uncertainty estimates usually assume that when a model gives the same answer
many times, that agreement is evidence of correctness. JURIS-UQ asks whether that
assumption survives contact with law — specifically, whether a model can be
**confidently and consistently wrong** because its knowledge is frozen before a
statutory change.

The benchmark is built around India's penal-code transition: the Indian Penal
Code (IPC, 1860) was replaced by the Bharatiya Nyaya Sanhita (BNS, 2023) with
effect from **1 July 2024** (MHA notification S.O. 850(E), 23 February 2024,
except s.106(2)). Two matched slices of the same fact patterns ask:

- **L7** — "which provision applies today?" The repealed IPC section is the trap.
- **L1** — "which provision applied immediately before the transition?" The BNS
  successor is the trap.

If a model answers the repealed provision every time, sample agreement is
maximal and confidence is maximal while the law is wrong. That is the
common-mode legal error the project is built to detect.

## What was built

Seven cumulative phases, each consuming the stored artefacts of the one before:

| Phase | Component | Research gate |
|---|---|---|
| A | sampling, judging, clustering, sample-only uncertainty | **G1 PASS** |
| B | typed legal relations (entails / contradicts / different-provision) | G2 NOT YET |
| C | deterministic statute store, validity windows, IPC↔BNS links, context packs | G3 NOT MET |
| D | common-mode detector: agreement × temporal validity × jurisdiction × contradiction | **G4 PASS** |
| E | legal-aware uncertainty with an explicit sample-only fallback | G5 `NOT_EVALUABLE` |
| F | per-stratum calibration + harm-weighted answer/verify/abstain policy + conformal layer | G6 NOT_MET |
| G | target population construction and the §21 evaluation matrix | G7 NOT_MET (pilot on hold) |

The reference implementation is Python + NumPy on CPU: generation through an
OpenAI-compatible local endpoint (LM Studio), judging by provision matching,
clustering lexically / by NLI / by typed relations, then a small statistical
layer. **No paid API was ever used**; all runs cost $0.

## The evidence

1. **The phenomenon is real in this setup.** On the frozen 200-item construction
   (2,000 samples, quantized `qwen2.5-7b-instruct`), the model answered 43.4 % of
   control questions correctly and **0 of 100** target questions. At the
   provision level, 16 items were answered unanimously — and **all 16 were
   wrong**. Unanimity tracked a repeated legal error, not correctness.
2. **A temporal detector separates those cases.** G4 PASS: AUROC 0.9412,
   95 % CI [0.8529, 1.0000] on the collision population. Pinning the temporal
   factor to 1.0 collapses AUROC to 0.5000, so the signal is genuinely the
   validity window and not an artefact of agreement.
3. **Typed relations are accurate.** `relations_v2` reaches macro-F1 0.9942 on a
   308-pair held-out split versus 0.7941 for exact-string keys.
4. **But the uncertainty instrument cannot be validated on the population that
   exists.** G5 is `NOT_EVALUABLE`, not failed for want of effort: the temporal
   factor is constant *within* each slice (`T=1.0` on 94/94 resolvable L1 records;
   `T=0.0` on 80/81 L7), and L7 contains only incorrect answers. A ranking needs
   both classes inside one slice. G6's calibration result (ACE 0.2797 against a
   0.05 target; selective risk 0.5455 versus 0.4545 for the sample-only baseline)
   is a genuine negative result on L1.
5. **Why Phase G exists.** Building the missing two-class target population is
   the only route to G5 and to the L7 half of G6. A 24-item candidate set was
   authored, screened, and produced **0/12 on L7** (0/120 samples) while scoring
   3/12 on L1. A 12-item L7 diagnostic at 3 samples reached **0/12 majority and
   0/36 samples** (operator-run; the artefact files are not in this repository).
   Every one of those 36 answers asserted a **repealed IPC** provision; none
   named a BNS section.

## What is provisional, and why

- **The labels are not human-verified.** An AI-assisted review of the twelve L7
  gold labels (2026-10-27) found **8 confirmed, 3 ambiguous, 1 unsupported** — one
  item described confinement while labelling it restraint, one under-stated a
  punishment tier by an order of magnitude, one left a required mental element
  unstated. Four corrections were applied to a **new** file
  (`data/lexuq_target_candidates_v2.jsonl`); the screened `v1` was left byte-identical.
  This is a machine comparison against statutory text, **not** legal sign-off.
- **The gate verdicts are scoped.** G1 and G4 pass on one quantized 7B checkpoint
  and one synthetic construction. Nothing here establishes that the instrument
  generalises to other models, other legal transitions, or real case facts.
- **The 0/12 diagnostic is not a cross-model comparison.** It measures one model,
  one prompt, one temperature, twelve items. The comparison experiment that would
  support a general claim is specified and deliberately **not run** until the
  labels have been reviewed by a human.

## What the next experiment is

The cheapest informative step is a screen of the corrected `v2` set on the same
local model (12 items × 3 samples, ≈11–27 minutes, $0). It replaces four known-bad
labels. It will not move G7, and it does not substitute for human review.

The step that would move the science is a **cross-model comparison** on
human-reviewed labels: the same twelve items, one alternative generator or one
prompt variant, everything else fixed. It is blocked by design until that review
exists — because if a gold label is wrong, "the model was wrong" is the wrong
conclusion, and every row of the Phase G measurement inverts.

## Where to look

| To see | Read |
|---|---|
| what is done, blocked, and why | [`STATUS.md`](STATUS.md) |
| the order of remaining work | [`ROADMAP.md`](ROADMAP.md) |
| how to run the demonstration in one command | [`DEMO.md`](DEMO.md) |
| the full method and historical results per phase | `PHASE-A.md` … `PHASE-G.md` |
| the L7 investigation and the label review | `PHASE-G-L7-INVESTIGATION.md`, `reports/phaseG_l7_label_review_v1.md`, `reports/phaseG_l7_label_review_v2_changes.md` |

**Scope statement.** JURIS-UQ is a research prototype. It is not a legal
research service, it does not give legal advice, and its benchmark is a scoped,
partly synthetic construction with incomplete legal verification.
