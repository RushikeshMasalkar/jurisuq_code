# JURIS-UQ — Phase D: the common-mode failure detector

Phase D is the module the project's thesis turns on. It takes the
agreement statistics of a stored run and the legal context of Phase C
and answers, once per item, the question the whole project exists to
ask: **is the agreement among the model's samples warranted by legal
structure, or is it merely repeated?**  A model that cites a repealed
provision cites it confidently, coherently and ten times out of ten —
the samples agree, but the agreement is not legally warranted. Phase D
decomposes the observed agreement into the part the legal context
supports and the part it does not. Implements the engineering
specification v2, section 18 (interfaces, factor definitions, the E4
validation populations and Gate G4 are exactly as specified there).

Nothing in Phase D learns, samples or reads a correctness label on the
query path. It is a deterministic lookup over stored answers, so it is
cheap, re-runnable and reproducible from the record alone.

---

## 0. What is in this drop

```
jurisuq/warrant/
├── __init__.py               # Phase D exports
├── detector.py               # WarrantDetector (M7): A, T, J, K -> W, CM, flags
└── validate.py               # E4 validation populations + Gate G4 + ablations
scripts/
├── 23_detect_warrant.py      # attaches the warrant tuple to a run -> new sibling (+warrant)
└── 24_validate_warrant.py    # E4 validation, Gate G4, figure
configs/
└── phase_d_warrant.json      # era dates, thresholds, validation settings
tests/
└── test_warrant.py           # 24 tests, incl. the era-matched L1/L7 behaviour
PHASE-D.md                    # this file
PHASE-D.md            # the consolidated result record
PHASE-D.md       # the authoritative result note
```

## Field and script registry

| Field | Type | Producer | Consumer | Status |
|---|---|---|---|---|
| `clusters` | `list[int]` | `scripts/13_attach_typed.py` | Phase D, E | registered |
| `cluster_provisions` | `list[str]` | `scripts/13_attach_typed.py` | Phase D | registered |
| `relation_matrix` | `list[list[str]]` | `scripts/13_attach_typed.py` | Phase D (K) | registered |
| `relation_scores` | `list[list[float]]` | `scripts/13_attach_typed.py` | audit / figures | registered |
| `typed_stats` | object | `scripts/13_attach_typed.py` | Phase E (`u_prov`) | registered |
| `scripts/23_detect_warrant.py --cluster-source {auto,exact,typed}` | CLI flag; default `auto` | Phase D | Phase D evaluation | registered; pending Block 4 |
| `scripts/23_detect_warrant.py --contradiction-source {auto,rule,model,none}` | CLI flag; default `auto` | Phase D | Phase D evaluation | registered; Block 4 |

The shipped field names remain authoritative. The master-guide aliases are
recorded explicitly: `warrant_A/T/J/K` maps to the shipped warrant factor
fields, `warrant_W` maps to `warrant_warranted_agreement`,
`common_mode` maps to `warrant_common_mode_score`, and `u_combined` maps to
`uq_uncertainty`. No field is renamed.

The Phase D run is **not** written into the frozen Phase A or Phase C
runs. Like Phase C it writes a new sibling directory
(`runs/...+ctx+warrant`) and hashes the source tree before and after.

## 1. Prerequisites — what you must install (short answer: nothing new)

Phase D is **stdlib-only**, like Phase C. No torch, no transformers, no
model downloads, no LM Studio, no internet at runtime.

* If you already ran Phase A/B/C in a venv → **install nothing**. Your
  existing `.venv` with `requirements.txt` already has everything
  (pytest and matplotlib included).
* Fresh machine? You need only Python 3.11+ and, in the repo root:
  ```powershell
  python -m venv .venv
  .venv\Scripts\activate          # Windows PowerShell
  # source .venv/bin/activate    # macOS / Linux
  python -m pip install --upgrade pip
  pip install -r requirements.txt
  ```
* You need a Phase C `+ctx` run on disk to detect on — the repo ships
  `runs/phaseA-laptop-v2-rejudged+ctx` (200 items, each carrying a
  `context` pack). The commands below use it.

## 2. Extract this zip into the repository root

The zip has no wrapper folder: its paths are `jurisuq/warrant/…`,
`scripts/23_…`, `scripts/24_…`, `tests/test_warrant.py`,
`configs/phase_d_warrant.json`, `PHASE-D.md`, `PHASE-D.md`,
`PHASE-D.md`. Extract **into the `jurisuq_code` folder**
(next to the existing `jurisuq/` and `scripts/`), so the files merge
into the existing tree.

**PowerShell (recommended):**
```powershell
cd D:\work            # the folder that CONTAINS jurisuq_code
Expand-Archive -Path .\jurisuq_phaseD.zip -DestinationPath .\jurisuq_code -Force
```

**Windows Explorer:** right-click `jurisuq_phaseD.zip` → *Extract All…*
→ choose `D:\work\jurisuq_code` as the destination → Extract.

**macOS / Linux:**
```bash
unzip jurisuq_phaseD.zip -d jurisuq_code
```

Check you landed in the right place:
```powershell
cd jurisuq_code
dir jurisuq\warrant          # __init__.py, detector.py, validate.py
dir scripts\23_detect_warrant.py
dir scripts\24_validate_warrant.py
```

## 3. Run Phase D

From the repository root, with the venv active:

```powershell
# Step 1 — the Phase D test suite (24 tests, ~1 s)
python -m pytest tests\test_warrant.py -q

# Step 2 — attach the warrant tuple to the Phase C +ctx run (~1 s)
python scripts\23_detect_warrant.py --run-id phaseA-laptop-v2-rejudged+ctx --out-suffix +warrant

# Step 3 — E4 validation and Gate G4 (~2 s)
python scripts\24_validate_warrant.py --run-id phaseA-laptop-v2-rejudged+ctx+warrant

# Step 4 — full repo suite: nothing regressed
python -m pytest -q
```

(On macOS/Linux use `scripts/23_detect_warrant.py` etc., with `/`.)

### Expected output (measured on the build machine, October 2026)

Step 1: `24 passed`.

Step 2:
```
detected 200 items -> ...\runs\phaseA-laptop-v2-rejudged+ctx+warrant
  as_of policy: era (era dates {'L7': '2024-07-01', 'L1': '2024-06-30'})
  fires 105   silent 95   fire rate 0.525
  flags: {'stale_provision': 80, 'unresolvable_assertion': 25}
  CM defined on 32/200 items (undefined = an unresolvable factor, never a zero)
  contradiction source: {'no_relation_signal': 167, 'exact_single_cluster': 33}
  source run tree hash: a39434fa145c0fc98378ba8b -> a39434fa145c0fc98378ba8b
  SOURCE RUN UNCHANGED (hard rule H2 satisfied)
```

Step 3:
```
E4 validation on 200 records (33 in the collision population)
  CM-score AUROC = 0.9412  95% CI [0.8529, 1.0000]  (n=32, 1 undefined-CM excluded)
  binary detector: TP=16 FP=0 TN=15 FN=2  (precision 1.000, recall 0.889, false-alarm 0.000)
    L1|correct=0: n=2 fires=0 (0.00)  flags={}
    L1|correct=1: n=15 fires=0 (0.00)  flags={}
    L7|correct=0: n=16 fires=16 (1.00)  flags={'stale_provision': 15, 'unresolvable_assertion': 1}
  factor ablation (AUROC drop):
    pin temporal=1.0: AUROC 0.5000 (drop 0.4412)
    pin jurisdiction=1.0: AUROC 0.9412 (drop 0.0000)
    pin contradiction=0.0: AUROC 0.9412 (drop 0.0000)
  base rate over 167 non-collision items: fire 0.533; correct-item alarm 0.000, wrong-item alarm 0.640
  GATE G4: PASS
```

Step 4: `135 passed, 1 skipped` (111 pre-existing + 24 new; the skip is
the pre-existing torch-gated Phase B test, so a machine with torch
reports 136 passed).

## 4. What it wrote

| Path | Contents |
|---|---|
| `runs/phaseA-laptop-v2-rejudged+ctx+warrant/items.jsonl` | the 200 stored records, each now carrying the `warrant_*` fields (source `+ctx` run untouched) |
| `runs/...+ctx+warrant/warrant_report.json` | fire/silent counts, flag census, per-slice rates, contradiction sources, both tree hashes |
| `runs/...+ctx+warrant/warrant_validation.json` | the E4 record: collision population, separation AUROC + CI, confusion matrix, factor ablation, base rate, Gate G4 verdict |
| `runs/...+ctx+warrant/fig_warrant.png` / `.svg` | the three-panel E4 figure |
| `runs/...+ctx+warrant/meta.json` | run metadata, input hashes, as-of policy |

## 5. The four-tuple, and how each factor is computed

The detector's interface to Phase E is a fixed four-tuple plus flags,
reproduced from the record alone so an ablation that removes the
detector removes exactly one module:

| Factor | Symbol | Definition | Source in this repo |
|---|---|---|---|
| observed agreement | `A` | the modal cluster's share (unanimity = 1) | `asserted_keys` (exact-key special case of the Phase B relation) |
| temporal validity | `T` | share of the modal cluster whose asserted provisions are in force at the item's as-of date | `jurisuq.context.StatuteStore.in_force` |
| jurisdiction fit | `J` | share of the modal cluster whose asserted provisions belong to the declared legal order | act attribution (`jurisuq.normalize`) |
| contradiction mass | `K` | probability mass of clusters whose relation to the modal cluster is CONTRADICTORY | relation matrix when present; else 0 on a single cluster, absent (`None`) on a multi-cluster record |
| warranted agreement | `W` | `A × T × J × (1 − K)` | composed |
| common-mode score | `CM` | `A − W` | composed |

The factors are reported **separately before they are composed**,
because a single multiplicative score cannot be ablated factor by
factor and its failure modes cannot be attributed. The product form is
deliberate: it is conservative (any single factor at zero removes all
warrant) and each factor can be removed independently in Phase H.

### The as-of date is the item's, not the analysis date

This is the crux of the design and the easiest thing to get wrong.
An L7 item asks about the law *today* (on or after 1 July 2024); an L1
item asks about the law *immediately before* 1 July 2024. The temporal
factor is only meaningful at the date the question asks about:

* L7 → as-of `2024-07-01` (the first day the new code is in force)
* L1 → as-of `2024-06-30` (the last day the old code is in force)

That is what makes the detector **silent on a correct pre-transition
answer** (IPC 302 *was* in force on 2024-06-30, so `T = 1`) and **loud
on a stale current-law answer** (IPC 302 is not in force on 2024-07-01,
so `T = 0`). Using a single analysis date for both slices — the Phase C
pack's `as_of` — would make `T = 0` on *both* slices and the detector
would fire on everything, which the spec calls worthless. The Phase C
pack's `as_of` is the analysis-date snapshot for human reporting; the
detector's era date is the question's date. They answer different
questions and both are correct.

`--as-of-policy fixed --fixed-as-of DATE` pins one date for every item;
that is the deliberate ablation that fires on both slices, kept so the
temporal factor's necessity can be *shown* rather than asserted.

### `None` is a first-class result

A factor the statute store cannot resolve is `None` (JSON `null`),
never `0`. When any factor is undefined, `W` and `CM` are undefined too
— the detector still *fires* on the resolvable factors (for example an
`unresolvable_assertion` flag), but it will not quote a composite score
it cannot stand behind. On the frozen run the CM score is therefore
defined on exactly the 32 single-cluster items whose modal provision the
store can resolve, and the report says so.

## 6. The E4 validation populations (read before interpreting)

The detector is validated before Phase E exists, because the frozen
Phase A records already carry the ground truth about which unanimous
answers were wrong. The validation is a direct computation over the
**unanimous provision-level collision population** (`prov_all_same = 1`,
33 items):

| Population | Items | Expected behaviour | Measured |
|---|---:|---|---|
| L7 unanimous, all wrong | 16 | fires, `stale_provision` dominant | **16/16 fire** (15 `stale_provision`, 1 `unresolvable_assertion`) |
| L1 unanimous, all correct | 15 | silent | **0/15 fire** |
| L1 unanimous, wrong | 2 | may fire; too few to conclude | 0/2 fire (see below) |
| All other items | 167 | a computed base rate of false alarms | fire rate 0.533; **correct-item alarm 0.000**, wrong-item alarm 0.640 |

The two L1-wrong items do **not** fire, and that is correct, not a
miss: their errors are wrong-*section* errors (the asserted IPC
provision was in force on the pre-transition date, but it is the wrong
section of the right code). The detector is a common-mode *temporal*
failure detector; it is designed to be silent on errors that are not
staleness. The spec anticipates exactly this ("may fire; too few items
to conclude anything at this n").

## 7. Useful options

```powershell
# smoke: detect on the first 10 items only
python scripts\23_detect_warrant.py --run-id phaseA-laptop-v2-rejudged+ctx --out-suffix +warrant-smoke --limit 10

# the fixed-date ablation (fires on both slices by construction)
python scripts\23_detect_warrant.py --run-id <run> --out-suffix +warrant-fixed --as-of-policy fixed --fixed-as-of 2026-10-01

# a new output suffix (never overwrite a shipped run)
python scripts\23_detect_warrant.py --run-id <run> --out-suffix +warrant2

# looser / stricter firing thresholds
python scripts\23_detect_warrant.py --run-id <run> --stale-threshold 0.5
```

## 8. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError: jurisuq` | run from a subfolder | run from the repo root (scripts add the root to `sys.path`) |
| `ERROR: no such run: …items.jsonl` | wrong `--run-id` | the message lists the available run folders; Phase D reads the `+ctx` run |
| `ERROR: <out> already exists` | re-running step 2 | add `--force` or a new `--out-suffix` |
| `CM defined on 0/200` | the source run has no `asserted_keys` | detect on a Phase A run of record, not an empty tree |
| detector fires on both slices | `--as-of-policy fixed` was used | that is the deliberate ablation; use the default `era` policy |
| `SOURCE RUN CHANGED` (exit 2) | something wrote into the frozen `+ctx` run | restore it from git / re-clone; investigate before trusting the report |
| AUROC prints `None` / undefined | the collision population has only one correctness class | expected on a single-slice population; the E4 validation uses the matched L1+L7 collision population, which has both |

## 9. Scope discipline (what Phase D is not)

* It is **not** a general correctness detector. It detects *common-mode
  temporal* failure — agreement on a provision that is not in force at
  the date the question asks about. Wrong-section, wrong-act and
  foreign-jurisdiction errors are separate factors (`J`) or out of scope.
* It is **not** a learned component. There is no model, no training, no
  checkpoint. The contradiction mass `K` accepts a Phase B relation
  matrix when one is present and is honestly absent (`None`) otherwise.
* It is **not** legal verification. It reads the Phase C statute store,
  whose rows carry their own `verified` flags and whose primary-source
  verification is still incomplete (see the Phase C results note). Phase
  D inherits that limitation: a temporal verdict is only as good as the
  store it reads.

---

## Complete experimental results and validation record

### Merged record: `PHASE-D.md`

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

### Merged record: `PHASE-D.md`

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

## Block 6b status and supersession

Blocks 4 and 5 are superseded, not deleted. Their reported numbers were
computed under relations_v1 (tau 0.45, DIFFERENT_PROVISION F1 0.00);
superseded by relations_v2; see Block 6b.

The Block 6b rehearsal re-ran typed attachment and warrant detection on
current data with the `relations_v2` checkpoint. The new typed run produced
the following cluster-size distribution: 1: 33, 2: 54, 3: 39, 4: 38,
5: 14, 6: 13, 7: 7, and 9: 2. Thus the typed one-cluster collision count
is 33, equal to the exact-key collision count (33), rather than the
superseded typed count of 106.

The new warrant run detected 117 fires and 83 silent items; common-mode was
defined for 172/200 records. G4 was recomputed on the 33-item collision
population: AUROC 0.9412, bootstrap 95% CI [0.8529, 1.0000], with
TP=16, FP=0, TN=15, FN=2. The per-factor ablation was temporal T pinned
to 1: AUROC 0.5000 (drop 0.4412), jurisdiction J pinned to 1: AUROC
0.9412 (drop 0.0000), and contradiction K pinned to 0: AUROC 0.9412
(drop 0.0000). G4 remains PASS.

The new run ids are
`phaseA-laptop-v2-rejudged+ctx-r2+typed-v2-r3` and
`phaseA-laptop-v2-rejudged+ctx-r2+typed-v2-r3+warrant-v2-r3`; all are
new siblings and the source runs remain unchanged. This is a rehearsal
only; Phase F has not started.

## L7 composition finding

The frozen instrument has `majority_correct = 43/100` on L1 and `0/100` on
L7. Every L7 item is resolved by the judge (`frac_unresolved = 0.000` on all
100 items). Across the 1,000 L7 stored answers, the verdict mix is
`stale_law = 832`, `wrong_section = 150`, and `other_provision = 18`.

The 150 `wrong_section` answers are exactly the 15 L7 items whose modal key is
BNS. They cite sections that mostly exceed BNS 2023's 358 sections, treating
IPC numbers as if they were BNS sections. The missing second correctness class
on L7 is a property of the model under test, not of the judge and not of the
statute store.

## Model-cutoff explanation for the L7 result

The frozen Phase A run was generated by `qwen2.5-7b-instruct`, with provider
`openai-compat:qwen2.5-7b-instruct`, temperature `1.0`, `max_tokens = 220`,
and `n_samples = 10` (see `runs/phaseA-laptop-v2-rejudged/meta.json`). The
model's training data ends near the IPC/BNS transition, and it answers IPC
379 to a post-1 July 2024 theft question.

Accordingly, the L7 result — 0/100 items correct and 832/1,000 stored answers
labelled `stale_law` — is partly a model-cutoff artefact, not purely a
legal-reasoning failure. A model with post-2024 training data is required
before any L7-based gate, including G5, can be evaluated. This limitation is
a property of the model under test, not a defect in the instrument.
