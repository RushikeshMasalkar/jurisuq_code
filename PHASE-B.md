# JURIS-UQ Phase B: typed legal relations

Phase B replaces identity-only grouping with a five-way relation model and
typed clustering. It builds a deterministic relation dataset, trains/evaluates
an InLegalBERT classifier, and re-clusters the frozen Phase A answers
read-only.

## Compute and cost

Inference runs locally through LM Studio on this machine. No accelerator is
used: PyTorch reports `2.9.1+cpu`, with CUDA, MPS, and XPU unavailable.
Inference and relation-model training therefore run on CPU. The project spent
nothing: no paid API calls, subscriptions, or billing were used. The Phase A
input remains the frozen `qwen2.5-7b-instruct` run; the Qwen3-14B Q4_K_M
screen (reasoning on and off) answered IPC 379 to a post-1-July-2024 theft
question and scored 0% on L7, so it was not used to regenerate a slice.
Gemini 2.5-flash was unavailable, 3.8-flash returned 503, and 3.6-flash hit
the free-tier daily quota (HTTP 429); no API model was used.

## Components and data

- `jurisuq/relations/`: pair schema, synthetic strata, model, typed clustering,
  and relation statistics.
- `scripts/10_build_relations.py`: build or verify `relations_v1`.
- `scripts/11_train_relation.py`: train a checkpoint under `models/relation/`.
- `scripts/12_eval_relation.py`: test metrics and E2 re-clustering.
- `configs/phase_b_relations.json`: model, split, device, and threshold setup.
- `data/relations/relations_v1/`: train/dev/test data and manifest.
- `runs/phaseB-relations-full/`: run-of-record reports.
- `runs/full/`: supplemental full E2 evaluation report.
- `runs/relations-full/`: supplemental test-only evaluation report.

## Field and script registry

| Field or script | Type / interface | Producer | Consumer | Status |
|---|---|---|---|---|
| `clusters` | `list[int]` | `scripts/13_attach_typed.py` | Phase D, E | registered; produced in typed runs |
| `cluster_provisions` | `list[str]` | `scripts/13_attach_typed.py` | Phase D | registered; produced in typed runs |
| `relation_matrix` | `list[list[str]]` | `scripts/13_attach_typed.py` | Phase D (K) | registered; produced in typed runs |
| `relation_scores` | `list[list[float]]` | `scripts/13_attach_typed.py` | audit / figures | registered; produced in typed runs |
| `typed_stats` | object | `scripts/13_attach_typed.py` | Phase E (`u_prov`) | registered; produced in typed runs |
| `typed_stats.n_clusters, counts, entropy, entropy_norm, top_share, agreement, all_same, canonical, contradiction_mass, merges_applied, merges_skipped, forced_unions, flags` | object keys | `scripts/13_attach_typed.py` | Phase E / audit | registered; exact `jurisuq.relations.stats.typed_stats` keys |
| `scripts/13_attach_typed.py` | CLI script; `--run-id`, `--out-suffix`, `--checkpoint`, `--config`, `--limit`, `--force`, `--progress` | Phase B | Phase D, E | registered; implementation in progress |

The authoritative frozen Phase A dataset digest is
`89bc1180a4df76287768ce59432aa7ff0aa9d38c16d5f296ed16c3e45449bd53`.
Historical registry value `45b2d194e9c2f623457481c0d7d02f36c6267ec65c0b75ee3df2be4c0d1d010a`
is retained only as a stale historical value.

### Block 5 limitation: gold/trap co-occurrence

On the frozen 200-item slice, no item's ten stored samples contain both its
gold provision and its trap provision. The counts are L1 gold-only 69,
L1 neither 31, L7 trap-only 52, L7 neither 48, and both 0. The typed
gold/trap modal-cluster diagnostic therefore has a measured ceiling of zero:
it provides no evidence about whether the relation model falsely merges
legally distinct provisions across the IPC-to-BNS transition. That risk is
unmeasured on this benchmark.

The seven controlled strata cover same-provision paraphrases, context
dependence, IPC/BNS crosswalk equivalence, adjacent-section and cross-act hard
negatives, and ambiguous assertions. Labels are rule-generated, not
human-annotated. The relation dataset content hash is
`e1aa4ba0916cbc95e9e8edd93aba11a795c7ea66bde636aeb9b2bf4da8177674`.

## Reproduce

Install the shared requirements and the phase file. Install the PyTorch wheel
appropriate to the machine before the phase file if needed:

```bash
python scripts/10_build_relations.py --verify-only
python scripts/10_build_relations.py --config configs/phase_b_relations.json --source synthetic
python scripts/11_train_relation.py --config configs/phase_b_relations.json --run-id phaseB-relations-repro --epochs 3
python scripts/12_eval_relation.py --config configs/phase_b_relations.json --run-id phaseB-relations-repro --phase-a-run phaseA-laptop-v2-rejudged
```

Use `--skip-e2` for test metrics only, `--limit-items 10` for a timing pass,
or `--no-model --limit-items 10` for the rule-only plumbing path. The
approximately 440 MB learned checkpoint is ignored by Git, so a fresh clone
must train or provide a compatible checkpoint before reproducing the learned
report.

### Supplemental evaluation records

Two additional local evaluations were run without changing the dataset,
checkpoint, or frozen Phase A input:

| Output | Scope | Result |
|---|---|---|
| `runs/full/relation_report.json` | Full learned evaluation, including E2 | Same test metrics as the run of record; 130 changed items; G2 `PASS`; E2 took 636.6 s |
| `runs/relations-full/relation_report.json` | Learned test metrics with `--skip-e2` | Same test metrics; E2 intentionally skipped; G2 `NOT YET` because the separation criterion was not evaluated |

These are supplemental reruns, not replacements for
`runs/phaseB-relations-full/`. The authoritative Phase B result remains the
run of record below because it includes the complete training metadata,
training log, test report, and full E2 results. The shorter `full` report has
the same metrics and gate outcome but does not include the training metadata.

## Result record

[The results section below is authoritative. It preserves the complete
train/test metrics, confusion matrix, merge metrics,
E2 counts and timing, G2 interpretation, and limitations. In particular,
test macro-F1 is 0.7770 versus 0.7765 exact-key baseline; all six errors are
false merges; and typed clustering changes 130 item states without rescuing
an exact collision.

---

## Complete experimental results and validation record

### Merged record: `PHASE-B.md`

# Phase B results — typed legal relations and the E2 re-clustering test

Run of record. Numbers below are transcribed from
`runs/phaseB-relations-full/dev_report.json` and
`runs/phaseB-relations-full/relation_report.json` as produced by
`scripts/11_train_relation.py` and `scripts/12_eval_relation.py` on the target laptop.
Nothing here is estimated; anything the reports do not contain is marked
**not reported** rather than filled in.

## Run identity

| Field | Value |
|---|---|
| Training run of record | `phaseB-relations-full` (3 epochs) |
| Kept as a plumbing baseline | `phaseB-relations-01` (1 epoch, `--limit 200`) |
| Evaluation command | `python scripts/12_eval_relation.py --run-id phaseB-relations-full --phase-a-run phaseA-laptop-v2-rejudged` |
| Checkpoint | `models/relation/relations_v1-InLegalBERT-phaseB-relations-full` (τ = 0.45) |
| Encoder | `law-ai/InLegalBERT`, `SEGMENT_TOKENS` = 120/120/60 |
| Device | CPU (xpu / cuda / mps unavailable to this torch build on the machine) |
| Python / libs | Python 3.13, torch 2.14.1, transformers 5.19.0, sentencepiece 0.2.2 |
| Dataset | `relations_v1`, 330 pairs (train 198 / dev 66 / test 66), `content_hash e1aa4ba0916cbc95e9e8edd93aba11a795c7ea66bde636aeb9b2bf4da8177674` |
| Phase A input to E2 | `runs/phaseA-laptop-v2-rejudged`, 200 items (100 L1 + 100 L7) |
| Phase A tree hash, before == after | `a98583fd66db4f46bb1ac014` |
| Date / machine | not reported (Windows laptop, Lenovo IdeaPad Slim 5, Intel Core Ultra with Intel Arc graphics) |

Dataset composition: strata S1 30, S2 120, S3 40, S4 90, S5 20, S6 10, S7 20; labels
SAME_PROVISION 150, CONDITIONALLY_EQUIVALENT 40, LEGALLY_EQUIVALENT 90,
DIFFERENT_PROVISION 30, AMBIGUOUS 20. Labels are generated by the templates in
`jurisuq/relations/pairs.py` and structurally verified at build time; they are **not
human-annotated**, so nothing below measures legal judgement in the wild.

## Training (dev split, n = 66)

τ is chosen on dev by maximising merge F1 over the configured grid, so dev merge numbers
are selection-biased upward and must not be quoted as test performance. Loss was still
falling at the last epoch (1.058), so 3 epochs was a budget choice, not convergence;
`epochs` is now 12 in `configs/phase_b_relations.json`.

| Run | Epochs | Per-epoch wall time | Loss trace | τ | Dev merge F1 (P, R) | Dev macro-F1 | Exact-key baseline |
|---|---|---|---|---|---|---|---|
| `phaseB-relations-01` | 1 (`--limit 200`) | 73.0 s | 1.5860 | 0.05 | 0.312 (0.848, 1.000) | 0.333 | 0.776 |
| `phaseB-relations-full` | 3 | 55.7 / 50.3 / 48.3 s | 1.5860 → 1.4112 → 1.0580 | **0.45** | **0.612 (0.903, 1.000)** | **0.777** | 0.776 |

Total training wall time for the run of record: 161 s.

## Test split (n = 66, never used for threshold selection)

| Label | Support | Precision | Recall | F1 |
|---|---|---|---|---|
| SAME_PROVISION | 30 | 0.8824 | 1.0000 | 0.9375 |
| LEGALLY_EQUIVALENT | 18 | 0.9000 | 1.0000 | 0.9474 |
| CONDITIONALLY_EQUIVALENT | 8 | 1.0000 | 1.0000 | 1.0000 |
| AMBIGUOUS | 4 | 1.0000 | 1.0000 | 1.0000 |
| **DIFFERENT_PROVISION** | **6** | **0.0000** | **0.0000** | **0.0000** |
| **macro-F1** | 66 | — | — | **0.7770** |

macro-F1 is the unweighted mean of the five F1s: (0.9375 + 0.9474 + 1.0000 + 1.0000 +
0.0000) / 5 = 0.77698 → 0.777. The exact-key identity baseline is 0.7765.

Confusion matrix — the diagonal is perfect everywhere except one row:

| gold ↓ / pred → | SAME | LE_EQ | COND_EQ | AMBIG | DIFF |
|---|---|---|---|---|---|
| SAME_PROVISION | 30 | 0 | 0 | 0 | 0 |
| LEGALLY_EQUIVALENT | 0 | 18 | 0 | 0 | 0 |
| CONDITIONALLY_EQUIVALENT | 0 | 0 | 8 | 0 | 0 |
| AMBIGUOUS | 0 | 0 | 0 | 4 | 0 |
| DIFFERENT_PROVISION | **4** | **2** | 0 | 0 | **0** |

60 of 66 predictions are correct. **All six errors are different-provision pairs that the
model merged** — four called SAME_PROVISION, two called LEGALLY_EQUIVALENT. The model
never once predicts DIFFERENT_PROVISION on this split. Ambiguous rate: 0.0606 (4 of 66).

Two merge statistics are reported and they are not the same quantity:

- `merge_precision` = 0.8824 — the precision of the **SAME_PROVISION** operational label
  (30 / (30 + 4)). This is the number the gate tests against ≥ 0.85.
- `merge_f1` = 0.7545 — the mean of the two class F1s under the three-way merge decision
  (merge = SAME, LE_EQ or COND_EQ): merge-positive F1 0.9375, non-merge F1 0.5714
  (precision 1.0, recall 0.4). The 0.4 recall is the same defect the confusion matrix
  shows: of the 10 gold non-merge pairs, only the 4 AMBIGUOUS ones are predicted non-merge.

## The margin over the baseline, stated exactly

Test macro-F1 is 0.7770 against an exact-key baseline of 0.7765, so the gate's
`beats_exact_key` condition is satisfied by **≈ +0.0005** — half of one thousandth, i.e.
smaller than the third decimal anyone would quote. Both numbers carry four-decimal
rounding, so the true margin lies inside (+0.0004, +0.0006). Every training loss except
the first is also above the level at which a 198-pair fit would be expected to separate
classes cleanly.

The defensible sentence is: **the learned relation model reaches parity with the exact-key
rule on this split while additionally producing graded relations the rule cannot express
(LE_EQ F1 0.9474, COND_EQ 1.0000, AMBIGUOUS 1.0000).** The sentence to avoid is "the
learned model beats exact-key identity", and no significance claim can be made at n = 66.

## E2 — re-clustering the Phase A run under typed relations

E2 re-clusters the stored Phase A answers read-only, with the run directory hashed before
and after. Two passes were made: a 10-item timing pass and a full 200-item pass.

| Quantity | 10-item pass | 200-item pass |
|---|---|---|
| Items scored | 10 | 200 |
| Items whose clustering state changed | 7 | **130** |
| Encoder pairs scored | 384 | 9,092 |
| Rule-decided pairs (never sent to the encoder) | 516 | 8,908 |
| Wall time | 59.7 s | 1,282.5 s (21.4 min, ≈ 0.2 items/s) |
| `typed_unanimous_accuracy_gap` (L1 − L7) | 0.400 | **0.4516** |
| Collision AUROC (typed entropy) | not reported | 0.5000 |
| Phase A tree hash before / after | not reported | `a98583fd66db4f46bb1ac014` / same |

Per slice:

| Slice | n | Exact-collision n | Exact-collision accuracy | Typed-collision n | Typed-collision accuracy | Reclassified **out** of collision |
|---|---|---|---|---|---|---|
| L1 | 100 | 17 | 0.8824 | 62 | **0.4516** | 0 |
| L7 | 100 | 16 | 0.0000 | 44 | **0.0000** | 0 |

("Collision" = the population in which every sample asserts the same provision, i.e.
typed/ exact clustering leaves one cluster.)

### How the gap criterion was met — read this before quoting it

The gate's third condition accepts any of: ≥ 1 changed item, a typed gap below the Phase A
value 0.882, or a collision AUROC above 0.5. Here:

1. **No item was rescued.** `reclassified_out_of_collision` is 0 in both slices: every item
   that was unanimous under exact-text clustering is still unanimous under typed
   relations. The change is **pure inflow** — the typed layer merges more, never less.
2. **L7 is untouched.** Its collision population grew 16 → 44 and its accuracy inside that
   population is still exactly 0.0000. Under typed relations, **44 of 100 L7 items now sit
   in a unanimous-provision population in which every single one is wrong.** The Phase A
   headline (16/100) is not weakened by Phase B; if anything the honest restatement is
   44/100 with the same 0.000 accuracy.
3. **The L1 side was diluted, not sharpened.** Its collision population grew 17 → 62 and
   its accuracy fell 0.8824 → 0.4516, because the 45 incoming items are 13 correct and 32
   incorrect. The L1−L7 gap narrowed from 0.882 to 0.4516 by pulling incorrect L1 answers
   into the "unanimous" bucket — which makes the L1 unanimous flag *less* trustworthy, not
   more.
4. **The AUROC alternative is structurally vacuous as implemented.** The population scored
   is the exact-collision set (33 items); `all_same` means one cluster, so typed entropy is
   exactly 0 for every member; a constant score vector yields AUROC 0.5 by the tie rule.
   The 0.5000 is not evidence of "no signal" — it is a statistic that cannot vary. The gate
   therefore passed on the **changed-item count alone**, the weakest of the three
   alternatives.

The honest reading of E2: **typed relations re-partition the Phase A collision population
substantially (130/200 items change state, +73 items pulled into unanimity), but they do
not separate correct from incorrect answers, and the L7 failure survives intact.** E2 is
a real, non-null effect on the clustering layer; it is not evidence that the diagnostic
improves.

## Gate G2

```
GATE G2: PASS {'merge_precision_ok': True, 'beats_exact_key': True,
               'separation_criterion_met': True, 'phase_a_untouched': True}
```

| Condition | Result | Reading |
|---|---|---|
| `merge_precision_ok` | True | 0.8824 on test vs the ≥ 0.85 gate (margin +0.032); 0.903 on dev. Solid — the strongest condition of the gate. |
| `beats_exact_key` | True | 0.7770 vs 0.7765 → **+0.0005**. A hairline pass that establishes parity, not superiority. |
| `separation_criterion_met` | True | Fired on `changed_items` = 130. The typed-gap alternative (0.4516 < 0.882) is also literally satisfied, by inflow (see above); the AUROC alternative cannot fire. |
| `phase_a_untouched` | True | Tree hash `a98583fd66db4f46bb1ac014` identical before and after; the re-clustering is read-only. |

## One-paragraph reading

Phase B closes the plumbing. The typed relation layer builds deterministically, fine-tunes
in 161 s on CPU, scores the frozen test split with a merge precision of 0.8824 against a
0.85 gate, and re-clusters the Phase A run without mutating a byte of it. Its weaknesses
are equally clear and must travel with the numbers: the model has **zero recall on
DIFFERENT_PROVISION** (all six test errors are merged pairs), its macro-F1 advantage over
the exact-key rule is **+0.0005**, and the E2 gain in the L1−L7 gap comes from diluting the
L1 population with incorrect answers rather than from separating them (no item was
reclassified out of a collision population, and L7's collision population grew to 44 while
staying 100 % wrong). The 330-pair dataset is template-generated, so all of this
characterises the pipeline, not the legal domain.

## Limitations and things to carry forward

1. **Sample size.** dev and test are 66 pairs. A macro-F1 difference of 0.0005 is noise;
   no significance claim is computable or permitted from it.
2. **Rule-generated labels.** All 330 labels come from `pairs.py` templates, so the model
   is largely learning to reproduce rules that are already free at inference time. Its
   scientific value lies on pairs the rules cannot decide, which this dataset
   under-samples (DIFFERENT_PROVISION has 30 pairs in total, 6 in test).

   ## Block 6 — Phase B model-quality follow-up

   Block 6 was run on the current frozen Phase A data without rerunning any typed
   attachment, warrant detection, or Phase E scripts. The accepted Block 5c
   structural finding remains decisive: typed representation quality cannot create
   the missing within-slice variance in `T`, so this block does not make G5
   evaluable.

   ### Dataset and training

   `relations_v2` was built into `data/relations/relations_v2` from both the
   synthetic generator and observed Phase A pairs. The v1 dataset was not edited.
   It contains 1,520 kept pairs (918 train, 294 dev, 308 test); 10 duplicate pairs
   were rejected. Content hash:
   `6e39a85276af8136bdfb4b2a5831862bbf85c662d232e29515d68386b3e9a94b`.

   The new run is `runs/phaseB-relations-02/`, trained for the committed 12
   epochs with the explicit `DIFFERENT_PROVISION` class weight of 10.0. Epoch
   loss and wall time were:

   | Epoch | Loss | Seconds |
   |---:|---:|---:|
   | 1 | 0.5636 | 430.8 |
   | 2 | 0.2553 | 978.9 |
   | 3 | 0.1122 | 569.4 |
   | 4 | 0.0454 | 560.0 |
   | 5 | 0.0192 | 389.1 |
   | 6 | 0.0206 | 403.0 |
   | 7 | 0.0103 | 393.7 |
   | 8 | 0.0084 | 481.0 |
   | 9 | 0.0034 | 355.0 |
   | 10 | 0.0050 | 499.5 |
   | 11 | 0.0154 | 536.7 |
   | 12 | 0.0023 | 354.6 |

   Training wall time was 5,980 seconds. The dev-selected merge threshold was
   `tau=0.05`.

   ### Test metrics and threshold diagnostics

   | Metric | relations_v1 / old | relations_v2 / new |
   |---|---:|---:|
   | Macro-F1 | 0.7770 | 0.9942 |
   | Exact-key baseline macro-F1 | 0.7765 | 0.7941 |
   | Exact margin | +0.0005 | +0.2001 |
   | `DIFFERENT_PROVISION` precision | 0.0000 | 1.0000 |
   | `DIFFERENT_PROVISION` recall | 0.0000 | 0.9726 |
   | `DIFFERENT_PROVISION` F1 | 0.0000 | 0.9861 |

   The operational argmax merge precision is 0.9706. The separately thresholded
   merge decision at `tau=0.05` has precision 0.9753 and recall 1.0000. This
   separation is now recorded explicitly rather than treating the operational
   argmax as the merge decision.

   ### Gold/trap transition probe

   The probe contains 10 IPC/BNS gold-trap pairs per slice and as-of date, all
   labelled `DIFFERENT_PROVISION`. Merge rates are reported separately:

   | Slice | 2024-01-01 | 2026-10-01 |
   |---|---:|---:|
   | L1 | 0/10 (0.000) | 0/10 (0.000) |
   | L7 | 1/10 (0.100) | 2/10 (0.200) |

   This is direct evidence that the remaining typed false-merge risk is not zero
   on the IPC-to-BNS transition, especially for L7. It is a probe, not a
   replacement for a human-verified relation test set.

   ### E2 rescue criterion and G2

   The new E2 run processed all 200 Phase A items in 644.7 seconds. Changed items
   are retained as a diagnostic: 1 item changed in total (0 in L1, 1 in L7).
   The rescue metric is the number of unanimously-wrong exact-key collision items
   reclassified out of collision; it is 0 in L1 and 0 in L7. Collision AUROC is
   0.5000; the typed collision populations are 17 in L1 and 16 in L7, with
   within-slice collision accuracy 0.8824 and 0.0000 respectively.

   Old G2 used `changed_items` as its separation alternative and reported PASS
   despite zero rescue. The corrected G2 conditions are:

   - merge precision threshold: PASS (`0.9753 >= 0.85`);
   - macro-F1 above the exact-key baseline: PASS (`0.9942 > 0.7941`);
   - rescue criterion: FAIL (`L1=0`, `L7=0`);
   - Phase A untouched: PASS (tree hash unchanged).

   Therefore corrected G2 is **NOT YET**. The model-quality improvement and
   `DIFFERENT_PROVISION` recall gain are real, but they do not constitute rescue
   of unanimously-wrong collisions.
3. **Merge bias.** Every test error is a false merge. If a later phase uses the relation
   model to *decide* collisions in a legal setting, that failure mode is the one to fix
   first — class weighting, or thresholding the merge decision separately from the
   operational argmax.
4. **Un-converged training.** Loss 1.058 at the last epoch, `epochs` now 12. Retraining as
   `--run-id phaseB-relations-01b` is the first lever if a stronger relation model is
   wanted; `--source both` (Phase A observed pairs, capped at 6 per item) is the second.
5. **E2 cost.** ≈ 0.2 items/s, ≈ 21 min per full pass on this CPU, driven by 9,092 encoder
   pairs after the rule shortcut already removed 8,908. A GPU/OpenVINO encoder path is the
   obvious accelerator if E2 becomes routine.
6. **Dev numbers are selection-biased.** τ was picked on dev, so dev merge precision
   (0.903) is not test performance; the test value is 0.8824.
7. **Still not in the report.** The 130 changed item ids are truncated to the first 50 by
   design (`changed_ids[:50]`); a per-epoch timing breakdown for the 10-item E2 pass, and
   the wall-clock date of the runs, were not captured. Fixable by re-running, not worth
   re-running for.
8. **Metric revision candidate for the log.** Replace the collision-AUROC alternative in
   criterion 3 with a rescue metric (e.g. L7 items reclassified out of the collision
   population) before Phase C relies on G2-style gates; the current alternative cannot
   fire and the typed-gap alternative can be satisfied by dilution.
9. **Phase A is unchanged.** `phaseA-laptop-v2-rejudged` remains the Phase A run of
   record; every number in `PHASE-A.md` stands as published.

## Freeze note

Phase B run of record: dataset `relations_v1`
(`content_hash e1aa4ba0916cbc95…`), checkpoint
`relations_v1-InLegalBERT-phaseB-relations-full` (τ 0.45), gate G2 PASS on all four
conditions. `phaseB-relations-01` is a deliberately kept plumbing baseline (undertrained
by construction) and is not a result. The checkpoint's `model.pt` (~440 MB) is not tracked
in git; `meta.json` and the two run reports are.

### Block 6b interpretation and corrected G2 record

The Block 6b rehearsal confirms that macro-F1 `0.9942` is measured on
rule-generated pairs and is very likely the model reproducing the generator's
rules. E3 therefore still requires the 1,500-pair human-verified test set;
`0.9942` must not be reported as evidence of legal-domain competence.

The gold/trap probe remains the residual false-merge risk: L7 had 1/10
merged pairs at `2024-01-01` and 2/10 merged pairs at `2026-10-01`.
This probe is not a substitute for the human-verified test set.

G2 is **NOT YET**, with all three criteria stated separately:

1. Rescue criterion: FAIL — rescue is 0.
2. Collision separation criterion: FAIL — collision AUROC is 0.5000.
3. L1-L7 unanimous accuracy criterion: FAIL to improve — the unanimous
   accuracy gap is unchanged at 0.8824.

Per the guide's section 16.4 prescribed response, proceed on the diagnostic
contribution and rewrite the Phase D and E expectations accordingly. Do not
re-tune the relation model, the threshold, or the dataset to make the rescue
criterion fire.

### Why typed clustering cannot differ from exact-key on this instrument

No item co-asserts IPC and BNS within its ten stored samples: 182 items are
IPC-only, 3 are IPC plus no provision, and 15 are BNS-only. All 10
`successor_of` rows in `data/relations/crosswalk_v1.jsonl` are IPC -> BNS.
Across 962 within-item co-occurrence pairs (368 distinct pairs), 0 are
`successor_of`, 19 are `different_offence`, and 943 (98%) are unknown to the
crosswalk.

The typed cluster-count distribution is 33/54/39/38/14/13/7/2, while the
exact-key distribution is 33/53/39/38/15/13/7/2. They therefore match on
199/200 items. G2's typed-clustering criterion is structurally unsatisfiable
on this instrument, independent of relation-model quality; it must be recorded
as such rather than treated as a model-quality failure.
