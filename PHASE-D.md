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
PHASE-D-RESULTS.md            # the consolidated result record
docs/results_phase_d.md       # the authoritative result note
```

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
`configs/phase_d_warrant.json`, `PHASE-D.md`, `PHASE-D-RESULTS.md`,
`docs/results_phase_d.md`. Extract **into the `jurisuq_code` folder**
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
