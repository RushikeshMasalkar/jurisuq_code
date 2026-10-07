# Phase B results — typed legal relations and the E2 re-clustering test

Run of record. Numbers below are transcribed from the run directories produced by
`scripts/11_train_relation.py` and `scripts/12_eval_relation.py` on the target laptop.
The authoritative machine-readable sources are
`runs/phaseB-relations-full/dev_report.json` and
`runs/phaseB-relations-full/relation_report.json`. Fields the pasted run output did not
contain are marked **not reported here** rather than filled in.

## Run identity

| Field | Value |
|---|---|
| Training run of record | `phaseB-relations-full` (3 epochs) |
| Training run kept as a plumbing baseline | `phaseB-relations-01` (1 epoch, `--limit 200`) |
| Evaluation run | `scripts/12_eval_relation.py --run-id phaseB-relations-full --phase-a-run phaseA-laptop-v2-rejudged` |
| Checkpoint | `models/relation/relations_v1-InLegalBERT-phaseB-relations-full` |
| Encoder | `law-ai/InLegalBERT`, uncased wordpiece tokenizer, `SEGMENT_TOKENS` = 120/120/60 |
| Device | CPU (xpu/cuda/mps all unavailable to this torch build on the machine) |
| Python / libs | Python 3.13, torch 2.14.1, transformers 5.19.0, sentencepiece 0.2.2 |
| Dataset | `relations_v1`, 330 pairs (train 198 / dev 66 / test 66), `content_hash e1aa4ba0916cbc95…` |
| Phase A input to E2 | `runs/phaseA-laptop-v2-rejudged` (200 items: 100 L1 + 100 L7) |
| Date / machine | not reported (Windows laptop, Lenovo IdeaPad Slim 5, Intel Core Ultra with Intel Arc graphics) |

Dataset composition, as built by `scripts/10_build_relations.py`: strata S1 30, S2 120,
S3 40, S4 90, S5 20, S6 10, S7 20; labels SAME_PROVISION 150, CONDITIONAL_EQUIVALENT 40,
LEGALLY_EQUIVALENT 90, DIFFERENT_PROVISION 30, AMBIGUOUS 20. Labels are rule-generated
from the templates in `jurisuq/relations/pairs.py` and verified structurally on build;
they are not yet human-annotated.

## Training (dev split, n = 66)

τ is selected on dev by maximising merge F1 over the configured grid, so the dev merge
numbers are selection-biased upward and must not be quoted as test performance.

| Run | Epochs | Per-epoch wall time | Loss trace | τ | Merge F1 (P, R) | Dev macro-F1 | Exact-key baseline |
|---|---|---|---|---|---|---|---|
| `phaseB-relations-01` | 1 (`--limit 200`) | 73.0 s | 1.5860 | 0.05 | 0.312 (0.848, 1.000) | 0.333 | 0.776 |
| `phaseB-relations-full` | 3 | 55.7 / 50.3 / 48.3 s | 1.5860 → 1.4112 → 1.0580 | **0.45** | **0.612 (0.903, 1.000)** | **0.777** | 0.776 |

Total training wall time for the run of record: 161 s. The loss was still falling at
epoch 3 (1.058), so 3 epochs was a budget choice, not a converged model; `epochs` is now
12 in `configs/phase_b_relations.json`.

## Test split (n = 66, never used for threshold selection)

| Metric | Value | Gate | Verdict |
|---|---|---|---|
| Macro-F1 over operational labels | 0.777 | — | — |
| Exact-key identity baseline | 0.776 | — | margin **+0.001** |
| Merge precision (`SAME_PROVISION`) | **0.8824** | ≥ 0.85 | met, margin +0.032 |
| Ambiguous rate, per-class rows, confusion matrix | **not reported here** — see `runs/phaseB-relations-full/relation_report.json` | — | — |

The margin over the exact-key baseline is 0.001 on a 66-pair split. That is a tie for
practical purposes and must never be written as "the learned model beats the exact-key
baseline"; the defensible statement is that it reaches parity while additionally
producing graded, non-identity relations that the exact-key rule cannot express.

## E2 — re-clustering the Phase A run under typed relations

E2 re-clusters the stored Phase A answers read-only with the record tree hashed before
and after. Two passes were run: a 10-item timing pass and the full 200-item pass.

| Quantity | 10-item pass | 200-item pass |
|---|---|---|
| Items scored | 10 | 200 |
| Items whose clustering state changed | 7 | **130** |
| Typed-unanimous accuracy gap (L1 − L7) | 0.400 | **0.4516** |
| Encoder pairs scored | 384 | 9,092 |
| Rule-decided pairs (never sent to the encoder) | 516 | 8,908 |
| Wall time | 59.7 s | 1,282.5 s (21.4 min, ≈ 0.2 items/s) |
| Collision AUROC (typed entropy) | not reported | **not reported here** |

Reference value for the gap criterion: under exact-text clustering the Phase A
unanimous-population accuracy gap is **0.882** (L1 0.882, L7 0.000). Under typed
relations the corresponding gap is **0.4516**, so the criterion
`typed gap < 0.882` is met. Per-slice un-margined populations (`L1`/`L7` entries of
`typed_unanimous_accuracy`) are **not reported here**; they are in the report JSON.

The 130 changed items are the substantive E2 signal: for 130 of 200 Phase A items, asking
the typed relation layer instead of exact-text identity gives a different clustering
state — different agreement, entropy or unanimity. E2 is therefore not a null result.

## Gate G2

```
GATE G2: PASS {'merge_precision_ok': True, 'beats_exact_key': True,
               'separation_criterion_met': True, 'phase_a_untouched': True}
```

| Condition | Result | Reading |
|---|---|---|
| `merge_precision_ok` | True | 0.8824 on test vs the 0.85 gate; 0.903 on dev. This is the solid criterion of the gate. |
| `beats_exact_key` | True | 0.777 vs 0.776. True by 0.001 — a hairline pass, not a demonstration. |
| `separation_criterion_met` | True | 130 changed items (and a typed gap of 0.4516 < 0.882). The changed-item count is the weakest of the three alternatives the gate accepts. |
| `phase_a_untouched` | True | The Phase A tree hash is identical before and after the E2 pass; the re-clustering is read-only. Absolute hash values **not reported here**. |

## One-paragraph reading

Phase B closes the plumbing: the typed relation layer builds, trains in under three
minutes on CPU, scores the frozen test split above the merge-precision gate, and
re-clusters the Phase A run without mutating it. What it does **not** yet do is
demonstrate that learned relations are better than the exact-key rule — the macro-F1
margin is +0.001 on both splits, which is indistinguishable from noise at n = 66. The
honest headline is the merge-precision result on frozen test data (0.8824 vs a 0.85
gate) plus the E2 finding that typed relations change the clustering state of 130 of 200
Phase A items and cut the L1−L7 unanimous-population accuracy gap from 0.882 to 0.4516.
The 330-pair dataset is template-generated, so both of those numbers describe the
pipeline rather than the legal domain; a larger, human-verified pair set is the lever
that would make the relation model a scientific claim in its own right.

## Limitations and things to carry forward

1. **Sample size.** dev and test are 66 pairs each. Any macro-F1 difference of ~0.001
   is noise; do not compute or quote a significance claim from it.
2. **Rule-generated labels.** Labels come from the templates in `pairs.py`, so the model
   is learning to reproduce rules that are already available at inference time. Its value
   is on the pairs the rules cannot decide, which this dataset under-samples.
3. **Un-converged training.** Loss was 1.058 at the last epoch; `epochs` is now 12.
   Retraining with `--run-id phaseB-relations-01b` is the first thing to do if a stronger
   relation model is needed.
4. **E2 cost.** ≈ 0.2 items/s on CPU, ≈ 21 min per full pass, driven by 9,092 encoder
   pairs. The rule shortcut already removes 8,908 pairs. A GPU/OpenVINO path for the
   encoder is the obvious accelerator if E2 becomes routine.
5. **Dev numbers are selection-biased.** τ was chosen on dev, so dev merge precision
   (0.903) must never be quoted as test performance; the test value is 0.8824.
6. **Not reported here.** Per-class precision/recall, the confusion matrix, the ambiguous
   rate, per-slice typed-unanimous accuracies, the collision AUROC and the absolute
   Phase A tree hashes exist in `relation_report.json` and can be transcribed into this
   note without re-running anything.
7. **Phase A is unchanged.** `phaseA-laptop-v2-rejudged` remains the Phase A run of
   record; every Phase A number in `docs/results_phase_a.md` stands as published.

## Freeze note

`phaseB-relations-full` is the Phase B run of record: dataset `relations_v1`
(`content_hash e1aa4ba0916cbc95…`), checkpoint
`relations_v1-InLegalBERT-phaseB-relations-full` (τ 0.45), gate G2 PASS.
`phaseB-relations-01` is a deliberately kept plumbing baseline (undertrained by design)
and is not a result. The checkpoint's `model.pt` (~440 MB) is intentionally not tracked
in git; `meta.json` and the two run reports are.
