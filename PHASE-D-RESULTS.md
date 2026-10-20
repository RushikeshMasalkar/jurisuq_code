# JURIS-UQ Phase D Results

This is the single consolidated Phase D record: the common-mode
failure detector (module M7), its E4 validation on the frozen
Phase A collision population, and the Gate G4 verdict.

## Status

**Complete and frozen.** The detector is implemented (stdlib-only,
no learned component), its unit tests pass, the E4 validation runs
end to end on the shipped `+ctx` run, and Gate G4 **passes**. The
legal-verification limitation inherited from Phase C (no row
independently confirmed against primary India Code / Gazette text)
carries forward and bounds every temporal claim below.

## 1. Identity and scope

| Field | Value |
|---|---|
| Source run (read-only) | `runs/phaseA-laptop-v2-rejudged+ctx` (200 items, each with a Phase C context pack) |
| Output run | `runs/phaseA-laptop-v2-rejudged+ctx+warrant` |
| As-of policy | `era` — L7 → `2024-07-01`, L1 → `2024-06-30` (the date each question asks about) |
| Jurisdiction | `IN` |
| Statute table | `data/statutes/statutes_v1.jsonl` (48 rows, sha256 `20c98b74…`) |
| Link table | `data/relations/crosswalk_v1.jsonl` (20 rows) |
| Cluster representation | `exact_key` (the Phase A provision view; the typed representation is supported and activates when a record carries Phase B cluster labels) |

## 2. The detector run

`python scripts/23_detect_warrant.py --run-id
phaseA-laptop-v2-rejudged+ctx --out-suffix +warrant`:

| Measurement | Result |
|---|---:|
| Items detected | 200 |
| Fires | 105 |
| Silent | 95 |
| Fire rate | 0.525 |
| `stale_provision` flags | 80 |
| `unresolvable_assertion` flags | 25 |
| CM score defined | 32 / 200 (undefined = an unresolvable factor, never a zero) |
| Contradiction source | `exact_single_cluster` 33, `no_relation_signal` 167 |
| Source tree hash before → after | `a39434fa145c0fc98378ba8b` → `a39434fa145c0fc98378ba8b` |
| Source run untouched | **Yes** (hard rule H2 satisfied) |

Per slice: L1 fires 6 / 100 (CM defined on 17, mean CM 0.000);
L7 fires 99 / 100 (CM defined on 15, mean CM 1.000).

## 3. E4 validation on the collision population

The unanimous provision-level collision population (`prov_all_same
= 1`) has 33 items. The detector's behaviour on it, decomposed by
slice and correctness:

| Population | Items | Fires | Flags fired | Mean CM |
|---|---:|---:|---|---:|
| L7 unanimous, all wrong | 16 | **16** (1.00) | `stale_provision` 15, `unresolvable_assertion` 1 | 1.000 |
| L1 unanimous, all correct | 15 | **0** (0.00) | — | 0.000 |
| L1 unanimous, wrong | 2 | 0 (0.00) | — | 0.000 |

### Separation

| Measurement | Result |
|---|---:|
| CM-score AUROC (collision population) | **0.9412** |
| Items scored (CM defined) | 32 (1 excluded: an L7 item whose modal provision `BNS 307` is unknown to the store, so CM is undefined — reported, never zeroed) |
| Bootstrap 95% CI | **[0.8529, 1.0000]** (2000 resamples, seed 0) |

### Binary detector (fires vs silent)

| TP | FP | TN | FN | Accuracy | Precision | Recall | False-alarm rate |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 16 | 0 | 15 | 2 | 0.9394 | 1.000 | 0.8889 | 0.000 |

The two false negatives are the L1-wrong items, whose errors are
wrong-*section* errors, not staleness — the detector is correctly
silent on them (see §5).

### Factor attribution (ablation)

Each factor is pinned to its warrant-maximising value while the
others keep their measured values; the AUROC drop is the separation
that factor alone carries:

| Factor pinned | AUROC when pinned | Drop from full | Share of above-chance separation |
|---|---:|---:|---:|
| (none — full composite) | 0.9412 | — | — |
| temporal `T = 1` | 0.5000 | 0.4412 | **1.00** |
| jurisdiction `J = 1` | 0.9412 | 0.0000 | 0.00 |
| contradiction `K = 0` | 0.9412 | 0.0000 | 0.00 |

The temporal factor alone carries **all** of the above-chance
separation; jurisdiction and contradiction carry none on this
construction.

### Base-rate honesty

Over the 167 non-collision items: fire rate 0.533 overall, but
decomposed by correctness the **correct-item alarm rate is 0.000**
(0 / 28) and the wrong-item alarm rate is 0.640. The detector does
not fire on correct answers anywhere in the run.

## 4. Gate G4

| Condition | Threshold | Measured | Verdict |
|---|---|---|---|
| Separation: CM AUROC > 0.5, CI excludes 0.5 | > 0.5 | 0.9412, CI [0.8529, 1.0000] | PASS |
| Factor attribution: temporal factor carries ≥ half the above-chance separation | ≥ 0.5 | 1.00 (drop 0.4412 of 0.4412 achievable) | PASS |
| Base-rate honesty: correct-item alarm < wrong-item alarm | — | 0.000 < 0.889 | PASS |

**Gate G4: PASS.**

## 5. Interpretation (what this does and does not show)

* **The common-mode signature is real and detected.** On the
  frozen run, every unanimously-wrong L7 answer asserts a repealed
  IPC provision; the temporal factor `T` is 0 for those items and
  the common-mode score `CM = A − W` is 1.0 — agreement that is
  total but legally unwarranted. This is precisely the failure the
  project exists to expose, and the detector's composite is driven
  entirely by the temporal factor.
* **The matched design is doing the work.** The same IPC provision
  is *in force* on the L1 (pre-transition) date and *not in force*
  on the L7 (current-law) date. The detector is silent on the 15
  unanimously-correct L1 items and loud on the 16 unanimously-wrong
  L7 items because it evaluates validity at the date the question
  asks about — not at a single analysis date, which would fire on
  both slices and be worthless.
* **The detector is a temporal-failure detector, not a correctness
  oracle.** The two L1-wrong false negatives are wrong-section
  errors (the asserted IPC provision was in force pre-transition but
  is the wrong section); the detector is correctly silent on them.
  On the wider run it fires on 83 of 84 non-collision L7-wrong
  items and on 6 of 55 non-collision L1-wrong items (the premature-
  or wrong-law subset), and on **none** of the correct items.
* **The separation is small-sample and single-checkpoint.** The
  collision population is 33 items (32 with a defined CM score) from
  one 7B checkpoint on one synthetic slice. The bootstrap interval
  [0.853, 1.000] is reported honestly; it excludes 0.5 but it is
  wide, and the AUROC is undefined within L7 alone (all L7 items are
  wrong, the same single-class limitation Phase A recorded).
* **Jurisdiction and contradiction factors are implemented but
  inactive on this data.** No asserted provision in the frozen run
  is foreign (`J = 1` throughout), and the collision population is
  single-cluster (`K = 0` exactly). They are wired, tested and
  reported so a future run with foreign assertions or a relation
  matrix exercises them; they carry none of the current separation.
* **Inherited legal-verification limit.** `T` is only as good as the
  Phase C statute store. 40 of its 48 rows are secondary-source
  supported and 8 are unresolved; no row was independently
  primary-source verified. A temporal verdict therefore inherits
  that uncertainty, and the 25 `unresolvable_assertion` flags are
  the honest boundary of what the store can currently ground.

## 6. Integrity measurements

| Artefact | SHA-256 | Deterministic? |
|---|---|---|
| `runs/...+ctx+warrant/items.jsonl` | `915e8efb197d8223767b39428e6cf0052d2ce9a907f1cc2192fcade917d01587` | yes — byte-identical on regeneration |
| `runs/...+ctx+warrant/warrant_validation.json` | `96041faa3f538a534d5a560ffb4bd579dc2bd9d160d443b989f7633a04efc7fe` | yes — the E4 result-of-record; carries no timestamp |
| `runs/...+ctx+warrant/warrant_report.json` | generation-specific | no — carries `generated_utc`; the operational detect log |

The two deterministic hashes are the integrity anchors: regenerate
Phase D on any machine and `items.jsonl` and
`warrant_validation.json` hash to the values above. The detect
report carries a generation timestamp (like Phase C's
`context_report.json`) and is therefore generation-specific; its
*content* apart from that timestamp is identical.

The `+ctx` source run was hashed before and after detection
(`a39434fa145c0fc98378ba8b`, unchanged). No frozen artefact was
modified.

## 7. Commands and test results

Executed from the repository root:

```
python -m pytest tests/test_warrant.py -q          # 24 passed
python scripts/23_detect_warrant.py --run-id phaseA-laptop-v2-rejudged+ctx --out-suffix +warrant
python scripts/24_validate_warrant.py --run-id phaseA-laptop-v2-rejudged+ctx+warrant
python -m pytest -q                                 # 135 passed, 1 skipped
```

## 8. Next actions (Phase E)

Phase E consumes this four-tuple and must not recompute it. The
warrant fields are now registered on the `+ctx+warrant` records, so
the uncertainty estimator can read `warrant_warranted_agreement`
(the warrant deficit `1 − W`), `warrant_common_mode_score`, and the
flags directly. The degradation ladder is already exercised: with
the detector absent the warrant fields are `null` and the estimator
must fall back to the sample-only scores, never treat null as zero.
