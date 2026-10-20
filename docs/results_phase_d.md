# Phase D results — E4 common-mode failure detector

Run of record. The numbers below are transcribed from the reports
produced by `scripts/23_detect_warrant.py` and
`scripts/24_validate_warrant.py` for the runs named in the first
table. Fields the run did not contain are marked **not reported**
rather than filled in. The authoritative machine-readable source is
`runs/phaseA-laptop-v2-rejudged+ctx+warrant/warrant_validation.json`.

## Run identity

| Field | Value |
|---|---|
| Detector run id | phaseA-laptop-v2-rejudged+ctx+warrant |
| Source run (read-only) | phaseA-laptop-v2-rejudged+ctx (Phase C packed, 200 items) |
| Date / machine | generated 2026-10-20; the frozen Phase A answers are the recorded laptop run (Qwen2.5-7B-Instruct, Q4_K_M, LM Studio) |
| Detector | WarrantDetector (module M7), stdlib-only, no learned component |
| As-of policy | `era` — L7 → 2024-07-01, L1 → 2024-06-30 (the date each question asks about) |
| Jurisdiction | IN |
| Cluster representation | exact_key (the Phase A provision view; typed activates when a record carries Phase B cluster labels) |
| Statute store | data/statutes/statutes_v1.jsonl, 48 rows, sha256 `20c98b74…` |
| Link table | data/relations/crosswalk_v1.jsonl, 20 rows |
| Source run untouched | yes — tree hash `a39434fa145c0fc98378ba8b` before and after |

## The four-tuple

The detector emits, per item, the fixed interface Phase E consumes
and never recomputes: observed agreement `A`, temporal validity
`T`, jurisdiction fit `J`, contradiction mass `K`, the composed
warranted agreement `W = A·T·J·(1−K)` and common-mode score
`CM = A − W`, plus the flags that fired. Each factor is reported
separately before composition so Phase H can ablate one factor and
attribute its effect.

## Detector run (200 items)

| Measurement | Result |
|---|---:|
| Fires / silent | 105 / 95 |
| Fire rate | 0.525 |
| `stale_provision` flags | 80 |
| `unresolvable_assertion` flags | 25 |
| `foreign_provision` / `internal_contradiction` flags | 0 / 0 |
| CM score defined | 32 / 200 |
| Contradiction source | exact_single_cluster 33, no_relation_signal 167 |

Per slice: L1 fires 6 / 100 (CM defined on 17, mean CM 0.000);
L7 fires 99 / 100 (CM defined on 15, mean CM 1.000).

## E4 validation: the collision population

The unanimous provision-level collision population
(`prov_all_same = 1`) has **33 items**. This is the population the
engineering specification fixes for validating the detector before
Phase E exists, because it already carries the ground truth about
which unanimous answers were wrong.

| Population | Items | Fires | Dominant flag | Mean CM |
|---|---:|---:|---|---:|
| L7 unanimous, all wrong | 16 | **16 (1.00)** | `stale_provision` (15), `unresolvable_assertion` (1) | 1.000 |
| L1 unanimous, all correct | 15 | **0 (0.00)** | — | 0.000 |
| L1 unanimous, wrong | 2 | 0 (0.00) | — | 0.000 |

## Separation

| Measurement | Result |
|---|---:|
| CM-score AUROC (collision population) | **0.9412** |
| Items scored (CM defined) | 32 (1 excluded: L7 item whose modal provision `BNS 307` is unknown to the store — CM undefined, reported, never zeroed) |
| Bootstrap 95% CI (2000 resamples, seed 0) | **[0.8529, 1.0000]** |

## Binary detector

| TP | FP | TN | FN | Accuracy | Precision | Recall | False-alarm rate |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 16 | 0 | 15 | 2 | 0.9394 | 1.000 | 0.8889 | 0.000 |

## Factor attribution (ablation)

| Factor pinned | AUROC when pinned | Drop from full | Share of above-chance separation |
|---|---:|---:|---:|
| (none — composite) | 0.9412 | — | — |
| temporal `T = 1` | 0.5000 | 0.4412 | **1.00** |
| jurisdiction `J = 1` | 0.9412 | 0.0000 | 0.00 |
| contradiction `K = 0` | 0.9412 | 0.0000 | 0.00 |

## Base-rate honesty (167 non-collision items)

| Population | n | Fire rate |
|---|---:|---:|
| Non-collision, all | 167 | 0.533 |
| Non-collision, wrong | 139 | 0.640 |
| Non-collision, correct | 28 | **0.000** |

## Gate G4

| Condition | Threshold | Measured | Met |
|---|---|---|---|
| Separation: CM AUROC > 0.5 with CI excluding 0.5 | > 0.5 | 0.9412, CI [0.8529, 1.0000] | MET |
| Factor attribution: temporal factor carries ≥ half the above-chance separation | ≥ 0.5 | 1.00 (drop 0.4412 of 0.4412 achievable) | MET |
| Base-rate honesty: correct-item alarm < wrong-item alarm | — | 0.000 < 0.889 | MET |

**Verdict: PASS.**

## One-paragraph reading

> On the frozen Phase A collision population, the common-mode
> detector fires on 16 of 16 unanimously-wrong current-law (L7)
> items — 15 with `stale_provision`, 1 with
> `unresolvable_assertion` — and stays silent on all 15
> unanimously-correct pre-transition (L1) control items, a
> false-alarm rate of 0.000 on correct items across the whole
> run. The common-mode score separates correct from incorrect
> unanimous answers with AUROC 0.941 (bootstrap 95% CI
> [0.853, 1.000], n = 32). Ablation attributes the entire
> above-chance separation to the temporal factor: pinning `T`
> to 1 collapses the AUROC to 0.500, while pinning `J` or `K`
> changes nothing. The detector is a common-mode *temporal*
> failure detector, not a correctness oracle — it is correctly
> silent on the two L1 wrong-section errors, which are not
> staleness.

## What this does and does not show

* **Shows:** on this checkpoint and slice, sample agreement that
  is total (`A = 1`) can be legally unwarranted (`W = 0`), and the
  temporal factor alone identifies it. This is the common-mode
  failure the project's thesis predicts, detected without a learned
  component and without reading a correctness label on the query
  path.
* **Does not show:** generality across models, slices, or offence
  types. The collision population is 33 items from one quantised
  7B checkpoint on one synthetic matched construction; the CM AUROC
  is undefined within L7 alone (all L7 items are wrong, the same
  single-class limitation Phase A recorded). The jurisdiction and
  contradiction factors are implemented and tested but carry none of
  the current separation (`J = 1` throughout; the collision
  population is single-cluster so `K = 0` exactly).
* **Inherits:** the Phase C statute store's legal-verification
  state. Forty of 48 rows are secondary-source supported and eight
  are unresolved; no row was independently confirmed against
  primary India Code / Gazette text in the recording environment.
  Every temporal verdict therefore inherits that limit, and the 25
  `unresolvable_assertion` flags mark the honest boundary of what
  the store can currently ground.

## Freeze note

The detector run `phaseA-laptop-v2-rejudged+ctx+warrant` and its
reports are frozen as the Phase D record. The source `+ctx` run was
tree-hashed before and after detection and is unchanged. The warrant
fields are registered additively (`warrant_*`); no frozen field was
renamed, retyped or deleted. Phase E consumes the four-tuple and must
not recompute it.
