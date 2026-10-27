# Phase G — the L7 zero: what the evidence does and does not establish

**Status: investigation complete. The mechanism was established from corroborating
committed evidence; it has since been *directly measured* on the twelve candidate
items (§3.4). Human legal review is still outstanding. No gate moves.**

This document answers one question: why did the Phase G Stage 2 screen produce
zero correct L7 answers (0/120 samples, 0/12 majority)? It is an audit of
committed artefacts plus deterministic probes of the judge. **This audit ran no
model.** The diagnostic runs recorded in §3.4 were performed separately by the
operator on a local endpoint; §9 specifies the comparison that has *not* been
run.

| | |
|---|---|
| Branch | `arena/74bd4c7f-jurisuq-code`, from `main` at `e8e7544` |
| Dataset | `data/lexuq_target_candidates_v1.jsonl`, sha256 `f49f4d91…d341` |
| Reports audited | the full, sliced and smoke Stage 2 screens; the frozen Phase A records; the committed qwen3-14b pilot |
| Generation performed here | **none** |
| Diagnostic runs in §3.4 | **two**, made by the operator on a local endpoint, not by this audit; Run B is timestamped `2026-10-27T11:35:24Z`, Run A's date is not recorded here |
| Gate effect | **none** — G5 `NOT_EVALUABLE`, G6 `NOT_MET`, G7 `NOT_MET` |

---

## 1. The question

The sliced screen reported L7 at 0/12 majority-correct and 0/120 correct samples
while the L1 control arm scored 3/12 and 32/120 in the same run. `PHASE-G-STAGE2.md`
§6c recorded the zero as established but its cause as **not** established. That
distinction is correct and this document narrows it.

Three explanations had to be separated, because they call for completely
different responses:

1. **The judge or the parser rejects correct answers** — a scoring artefact, and
   therefore a bug to fix.
2. **The generator does not produce the correct provision** — a knowledge limit,
   and therefore a research finding about the generator, not a defect.
3. **The items themselves are wrong** — bad gold labels or unanswerable facts,
   and therefore a dataset problem that invalidates the measurement.

## 2. What was examined

Committed artefacts only, plus code and deterministic probes:

| Source | What it contributes |
|---|---|
| `runs/phaseG_screen_qwen3_14b_{full,sliced,smoke}.json` | the three screen reports, read separately |
| `runs/pilot-qwen3-14b-pilot/pilot_items.jsonl` | **per-sample** qwen3-14b records, 24 items × 3 samples |
| `runs/phaseA-laptop-v2-rejudged+ctx-r2/items.jsonl` | frozen Phase A per-sample records (200 items) |
| `runs/phaseG_candidate_sources_v1.json` | the provenance registry for the candidate set |
| `runs/phaseG_l7_qwen3_14b_diagnostic.json` and `…_items.jsonl` | the corrected diagnostic on the twelve candidate items (§3.4); not committed here at the time of writing |
| a superseded diagnostic whose model id was a placeholder | preserved as history, not attributable to any model (§3.4) |
| `jurisuq/judge.py`, `jurisuq/normalize.py`, `jurisuq/pipeline.py` | the correctness decision path |
| `scripts/41_screen_target_yield.py` | the screen harness |
| `tests/test_judge.py` | the judge's existing behavioural tests |

## 3. Finding 1 — the mechanism, from per-sample evidence

### 3.1 A committed qwen3-14b run already answers this question

`runs/pilot-qwen3-14b-pilot/pilot_items.jsonl` is a screen of **the same model
family, the same slice design and the same judge**, run over 12 L7 and 12 L1
items drawn from the frozen slice (`data/lexuq_slice.jsonl`), 3 samples each.
`PHASE-A.md` documents it: *"the endpoint model id `qwen3-14b` with reasoning
off … 24 pilot items (12 per slice, 72 sampled answers), with 100% judge
coverage. Per-sample accuracy was L7 `0.00` and L1 `0.56`. The verdict mix was
`stale_law=33`, `wrong_section=19`, `gold=16`, and `gold_operative=4`."*

Reading the records directly reproduces those totals exactly (72 labels) and
splits them by slice:

| qwen3-14b, frozen-slice pilot | L1 | L7 |
|---|---:|---:|
| Items × samples | 12 × 3 | 12 × 3 |
| Samples | 36 | 36 |
| Majority-correct items | 7/12 | **0/12** |
| Samples labelled `gold` / `gold_operative` | 16 / 4 (55.6% correct) | **0 (0.0%)** |
| Samples labelled `stale_law` (asserts the repealed IPC) | 0 | **33 (91.7%)** |
| Samples labelled `wrong_section` | 16 | 3 (8.3%) |
| Mean `repealed_code_share` | 1.000 (correct: L1 gold *is* the IPC) | **0.917** |

Eleven of the twelve L7 items are **3/3 `stale_law`**; the twelfth
(`L7-wrongful_restraint-093`) is 3/3 `wrong_section`. Not one sample in any of the
36 L7 generations names the BNS gold provision. The answers are explicit, e.g.
for a question asking for the law in force *today*:

```
[stale_law] Provision: Indian Penal Code, section 420   Reason: Section 420 deals with cheating ...
[stale_law] Provision: Indian Penal Code, section 406   Reason: Section 406 deals with criminal breach of trust ...
```

### 3.2 The frozen primary model shows the same pattern at larger n

`PHASE-G.md` §"Why the L7 stratum has no correct answers (measured, not assumed)"
records, for `qwen2.5-7b-instruct` over the frozen slice, 10 samples/item:

| L7, frozen primary run | Value |
|---|---|
| Majority-correct items | 0 / 100 |
| Samples naming the gold provision | 0 / 1000 |
| `stale_law` samples | 832 / 1000 |
| `wrong_section` samples | 150 / 1000 |
| L1 control majority accuracy | 43 / 100 |

### 3.3 What this establishes — and what it does not

**Established.** On L7 items of this design, both models the project has screened
produce almost exclusively the **repealed IPC provision**, and neither ever
produces the BNS gold. For qwen3-14b this is recorded per sample across 36
answers; for qwen2.5-7b across 1,000.

**Not directly established *by this pilot*.** That the *Stage 2 candidate* L7 zero
had this same cause: the pilot used a different item set (`data/lexuq_slice.jsonl`,
0 id overlap with the candidate set), and at the time the Stage 2 reports kept no
per-item records (§4). The pilot alone was therefore strong corroboration across a
different item set, not a measurement of these 12 items. **§3.4 now supplies that
measurement**, and the two should be read together: §3.3 shows the pattern is not
an artefact of one item set; §3.4 records what these twelve items actually
produced.

### 3.4 The direct measurement on the twelve candidate items

Two runs were made on the twelve candidates, 3 samples each. **They are not the
same experiment and must never be pooled or averaged.**

| | Run A — superseded | Run B — corrected |
|---|---|---|
| `generator` recorded in the report | `openai-compat:REPLACE_WITH_YOUR_MODEL_ID` | `openai-compat:qwen3-14b` |
| Model actually under test | **unknown** — not attributable to Qwen3-14B | qwen3-14b |
| Items × samples | 12 × 3 = 36 | 12 × 3 = 36 |
| Elapsed | ≈895.5 s (operator-reported) | not transcribed here |
| Majority correct | not transcribed here | **0/12** |
| Correct samples | not transcribed here | **0/36** |
| Wilson 95% CI (majority) | — | [0.000000, 0.242494] |
| Projection | — | `reachable: false` |

**Why Run A is superseded — and preserved.** `scripts/41` takes its model from
`--set model=`, which defaults to `configs/phase_a.json`; that file carries the
literal string `REPLACE_WITH_YOUR_MODEL_ID`, and the OpenAI-compatible generator
names itself `openai-compat:{model}` (`jurisuq/config.py:10`,
`jurisuq/generators.py:196`). Nothing in the harness refuses such a value, so an
un-overridden run silently labels itself with the placeholder. Run A is kept as
the record of a mis-specified model id. **It is not evidence about Qwen3-14B and
its numbers must not be cited as if it were.**

**Run B — command as run** (Windows, from the repository root):

```powershell
python scripts\41_screen_target_yield.py `
    --data data\lexuq_target_candidates_v1.jsonl `
    --slice L7 `
    --out runs\phaseG_l7_qwen3_14b_diagnostic.json `
    --save-items runs\phaseG_l7_qwen3_14b_diagnostic_items.jsonl `
    --allow-generation `
    --set model=qwen3-14b --set n_samples=3
```

`--provider` is **not** a flag of this script; the provider comes from
`configs/phase_a.json` (`"provider": "openai"`). Earlier drafts of §9 showed
`--provider openai` and would have failed at argument parsing.

**Verified against the run files** by the operator on 2026-10-27:

| Field | Value |
|---|---|
| `generator` | `openai-compat:qwen3-14b` |
| `data_sha256` | `f49f4d91946387eb0534718945092cc2f840bd9f2aee053ed9ac13c3f296d341` — matches the committed dataset |
| `n_items` / `n_samples_per_item` | 12 / 3 |
| `yield.overall` | 0/12 majority correct; 0/36 samples correct |
| `yield.overall.majority_interval` | Wilson, `[0.0, 0.242494]`, 95% |
| `projection.reachable` | `false` — "a zero observed rate cannot be projected" |
| `generated_utc` | `2026-10-27T11:35:24Z` |
| judge / temperature | **not recorded in the report**; `configs/phase_a.json` reads `provision` and `1.0` |

**Item-level results.** Twelve records, three samples each. `majority_verdict` is
`stale_law` for all twelve and `repealed_code_share` is exactly 1.0 for all
twelve, so every one of the 36 samples asserted a code repealed on 1 July 2024.

| Item | Gold | Majority verdict | Provision counts (per sample) | Repealed share |
|---|---|---|---|---:|
| `L7-cheating-c001` | `BNS 318(4)` | `stale_law` | IPC 420 ×3 | 1.0 |
| `L7-criminal_breach_of_trust-c001` | `BNS 316(2)` | `stale_law` | IPC 201 ×1; IPC 406 ×2 | 1.0 |
| `L7-criminal_breach_of_trust-c003` | `BNS 316(2)` | `stale_law` | IPC 406 ×3 | 1.0 |
| `L7-cruelty_by_husband-c001` | `BNS 85` | `stale_law` | IPC 304B ×2; IPC 498A ×1 | 1.0 |
| `L7-culpable_homicide-c003` | `BNS 105` | `stale_law` | IPC 304A ×3 | 1.0 |
| `L7-murder-c001` | `BNS 103(1)` | `stale_law` | IPC 300 ×3 | 1.0 |
| `L7-theft-c001` | `BNS 303(2)` | `stale_law` | IPC 379 ×3 | 1.0 |
| `L7-theft-c003` | `BNS 303(2)` | `stale_law` | IPC 379 ×3 | 1.0 |
| `L7-theft_in_dwelling-c001` | `BNS 305` | `stale_law` | IPC 395 ×3 | 1.0 |
| `L7-theft_in_dwelling-c003` | `BNS 305` | `stale_law` | IPC 395 ×1; IPC 397 ×2 | 1.0 |
| `L7-wrongful_restraint-c001` | `BNS 126(2)` | `stale_law` | IPC 376 ×1; IPC 376A ×1; IPC 377 ×1 | 1.0 |
| `L7-wrongful_restraint-c003` | `BNS 126(2)` | `stale_law` | IPC 377 ×1; IPC 379 ×2 | 1.0 |

**Three things this table shows that the aggregate does not.**

1. **Label unanimity is not provision unanimity.** `majority_verdict` is a judge
   label taken from the modal cluster's first member; `prov_counts` is a per-sample
   tally of `provision_key`. **5** of the twelve items split across two or three
   different IPC sections while all carrying `stale_law`.
2. **The attractor is "a repealed code", not "the matched repealed twin".**
   Measured against each item's designed `trap`: **4** items take the trap on all
   three samples, **2** take it on some, and **6 never take it at all**:
   `L7-culpable_homicide-c003`, `L7-murder-c001`, `L7-theft_in_dwelling-c001`, `L7-theft_in_dwelling-c003`, `L7-wrongful_restraint-c001`, `L7-wrongful_restraint-c003`. The murder item answers `IPC 300` (the
   *definition* of murder, not the punishment in `IPC 302`); the culpable-homicide
   item answers `IPC 304A` (negligence); the theft-in-dwelling items answer dacoity
   sections `IPC 395`/`397`; the wrongful-restraint items answer sexual-offence
   sections `IPC 376`/`376A`/`377`.
3. **The gold provision is never reached.** Not one of the 36 samples names a BNS
   section, consistent with §3.1 and with the frozen runs.

**What §3.4 establishes.** On these twelve items, under this configuration, the
generator produced no correct majority answer and no correct sample in 36
generations, and every sample asserted a repealed criminal code.

**What it does not establish.** Independent correctness of any gold label
(`provenance.verified` remains `false`); that L7 is unanswerable in general
(n = 12, one model, one prompt, one temperature, CI upper bound 0.2425); that
another model would behave the same; or any change to a Phase G gate.

**Provenance of this table.** The twelve rows are the operator's transcription of
`runs/phaseG_l7_qwen3_14b_diagnostic_items.jsonl`, verified against that file
locally; this audit did not hold the file in its own environment. Counts are per
sample, not per item. Regenerate rather than retype — see §11.

## 4. Finding 2 — the zero was unattributable because the harness discards the evidence (confirmed)

This is a **reproducible defect in the screening harness**, not a property of the
data.

`jurisuq/pipeline.py:build_record` computes, for every item, exactly the fields a
diagnosis needs: `sample_texts`, `sample_correct`, `sample_verdict_labels`,
`sample_verdict_reasons`, `asserted_keys`, `asserted_acts`, `repealed_code_share`.
The frozen runs persist them (`runs/*/items.jsonl`, 40 fields per record).

`scripts/41_screen_target_yield.py` built those same records and then wrote only
aggregates:

```python
records.append(record)          # full diagnostics, held in memory ...
...
payload = { ... "yield": report, "yield_by_slice": yield_by_slice ... }   # ... and dropped
```

So the information existed at run time — 240 labelled answers, 10,684.6 s of
generation — and was discarded when the process exited. **That is the sole reason
the Stage 2 L7 zero is unexplained**, while the frozen run's identical zero *is*
explained. It is an observability gap, not a scientific mystery.

Fixed in this task: see §8.

A second, related defect was found in the same file: the `--force`/overwrite guard
on the output report ran **after** all generation, so an accidental re-run burned
the entire compute budget (hours on the laptop) before refusing to write. Also
fixed.

## 5. Finding 3 — the judge is not the cause

### 5.1 The judge accepts correct answers in every form tested

Deterministic probes (`ProvisionJudge`, no model), for L7 `L7-murder-c001`
(gold `BNS 103(1)`):

| Answer | Verdict | Correct |
|---|---|---|
| `Under the BNS, Section 103(1) applies. Punishment: death or life imprisonment. (IPC s.302 is repealed.)` | `gold_operative` | **True** |
| `Section 103 of the Bharatiya Nyaya Sanhita, 2023 applies.` | `gold` (subsection dropped, tolerated) | **True** |
| `Section 302 of the Indian Penal Code applies.` | `stale_law` | False |
| `This is murder. Punishment is death or life imprisonment.` | `unresolved` | None |
| *(empty)* | `unresolved` | None |

`match_kind` (`normalize.py:190`) deliberately accepts a gold that carries a
subsection when the answer omits it (`"base"` match), so an answer writing
"BNS 103" for gold "103(1)" is **not** penalised. The frozen cross-check also
found **0 of 1,000** L7 samples rejected for asserting the section in parent form.

### 5.2 The L1/L7 asymmetry is by design, and already tested

The two slices are the same legal material viewed from opposite sides of the
1 July 2024 repeal: L1 asks about the law *before* that date with the IPC as gold;
L7 asks about the law *today* with the BNS as gold. The judge reflects this
exactly, and `tests/test_judge.py:66-78` already pins it:

| Answer | On L1 (gold IPC 302) | On L7 (gold BNS 103(1)) |
|---|---|---|
| `Section 302 IPC` | **correct** (`gold`) | incorrect (`stale_law`) |
| `Section 103(1) BNS` | incorrect (`premature_law`) | **correct** |

This yields a decisive argument about the Stage 2 result: **the L1 arm of the same
run scored 32/240 correct samples with the same generator, judge, question
template and item schema.** The pipeline therefore demonstrably *can* mark an
answer correct on this item format. Any slice-agnostic defect — parsing,
normalisation, matching, clustering — would depress both arms together and cannot
by itself produce the observed 3/12 versus 0/12 split. The split must come from
something the slices differ in: the era framing and therefore the answer the
model produces.

### 5.3 Real parser limitations, demonstrated — but they are slice-symmetric

`find_mentions` needs an act name, the word "Section", or both. Deterministic
probes:

| Text | Mentions found |
|---|---|
| `Section 103(1) of the BNS applies.` | `103(1)` (act BNS, sub `1`) |
| `BNS s.103(1)` | `103` (act BNS, **sub lost**) |
| `under BNS 103(1)` | `103` (act BNS, **sub lost**) |
| `punishment is under 103(1)` | **none** |
| `103(1)` | **none** |
| `Section 101 of the BNS defines murder; punishment is under 103(1).` | only `101` → scored `wrong_section` |

These are genuine limitations: a correct provision written without a cue is
invisible to the judge, and an act-preceded subsection loses its subsection. They
were not changed, because a bare number is genuinely ambiguous and loosening the
parser would risk false positives across the whole project. They are recorded
because they matter for a future run: if the next L7 run shows a large
`unresolved` label count rather than `stale_law`, this parser behaviour becomes a
prime suspect. They cannot explain the current gap (§5.2).

## 6. Finding 4 — the 12 L7 candidates and their provenance

### 6.1 The source registry

Every L7 item traces to `runs/phaseG_candidate_sources_v1.json`, generated by
`scripts/45_build_target_candidates.py`. Sources are official, with URLs, and —
to the project's credit — record honestly what was actually opened:

| Source | Authority | Retrieved |
|---|---|---|
| `NCRB_BNS_2023` | National Crime Records Bureau, MHA | **full text** (Chapters I–V read in full; later chapters via the arrangement-of-sections list) |
| `BPRD_COMPARISON` | Bureau of Police Research and Development, MHA | **search excerpt only** — "the PDF could not be opened from this environment (HTTP 500)" |
| `EGAZETTE_BNS` | Government of India e-Gazette | **search excerpt only** |
| `UPPOLICE_COMPARATIVE` | Uttar Pradesh Police | **search excerpt only** |
| `MHA_REFERENCE_2023` | MHA | **search excerpt only** (supports the enforcement date, 1 July 2024) |

### 6.2 Section-pair confidence, as recorded by the builder

| Topic | BNS | IPC | Confidence | Sources |
|---|---|---|---|---|
| `cheating` | `318(4)` | `420` | **medium** | `NCRB_BNS_2023`, `UPPOLICE_COMPARATIVE` |
| `criminal_breach_of_trust` | `316(2)` | `406` | **medium** | `NCRB_BNS_2023`, `BPRD_COMPARISON` |
| `cruelty_by_husband` | `85` | `498A` | **medium** | `NCRB_BNS_2023` |
| `culpable_homicide` | `105` | `304` | **medium** | `NCRB_BNS_2023` |
| `murder` | `103(1)` | `302` | **high** | `NCRB_BNS_2023`, `BPRD_COMPARISON`, `EGAZETTE_BNS` |
| `theft` | `303(2)` | `379` | **high** | `NCRB_BNS_2023` |
| `theft_in_dwelling` | `305` | `380` | **medium** | `NCRB_BNS_2023`, `BPRD_COMPARISON`, `UPPOLICE_COMPARATIVE` |
| `wrongful_restraint` | `126(2)` | `341` | **high** | `NCRB_BNS_2023`, `BPRD_COMPARISON` |

**Weakest three, worth the reviewer's attention first:**

- `cheating` — `318(4) ← 420`. The only non-NCRB support is a UP Police excerpt
  that, as recorded, *"showed only 318(1)-(3)"*. The 318(4) pairing is described
  as "standard" but not directly evidenced in this environment.
- `cruelty_by_husband` — `85 ← 498A`. *"The official correspondence table was read
  only up to Chapter V here, so this pair rests on the BNS titles plus the standard
  published mapping and needs human confirmation."*
- `criminal_breach_of_trust` — `316(2) ← 406`. BNS 316 consolidates IPC 405–409, so
  the 406/407/408/409 distinctions are partly lost; recorded as a limitation.

Four of the eight pairs depend in part on `BPRD_COMPARISON`, whose PDF was never
opened here.

### 6.3 What is verified and what is not

- **Verified in this environment:** the dataset validates against the contract; the
  hash matches; the section *numbering* was checked against NCRB full text; the
  provenance is internally consistent and every item is `verified: false`.
- **Not verified:** the legal correctness of any gold label. No qualified reviewer
  has approved any item. `provenance.verified` stays `false`.
- **Inferred, not verified:** where only a search excerpt was read, the mapping is
  as good as the excerpt.

### 6.4 A structural observation about `pair_id`

`PHASE-A.md:116` describes the frozen slice as "100 matched pairs, matched on
`pair_id`", and `PHASE-E.md:84` relies on that grouping to keep L1/L7 siblings in
the same partition. The candidate set reuses the field name but assigns **24
distinct `pair_id` values to 24 items**, and **no fact pattern is shared across
slices** (0 identical questions). So within this dataset `pair_id` is a per-item
label, not a cross-slice key.

This does not affect the screen — which groups by `slice`, not `pair_id` — and it
does not invalidate any result. It does mean the cross-slice comparison here is
between *unmatched* items, so part of the L1/L7 difference could reflect fact-pattern
difficulty rather than the era flip alone. Any future fitting or paired analysis on
this candidate set must not assume sibling matching. Recorded, not changed:
dataset composition is out of scope for this task.

## 7. Confirmed versus unresolved

| Claim | Status | Basis |
|---|---|---|
| The Stage 2 L7 arm scored 0/12 majority and 0/120 samples | **Established** | committed sliced report |
| The screen discarded the per-item diagnostics it had computed | **Established** | `scripts/41` vs `pipeline.build_record` |
| The overwrite guard ran only after generation | **Established** | line order in `scripts/41` |
| The judge accepts correct L7 answers in every form tested | **Established** | deterministic probes + `test_judge.py` |
| The judge is lenient about missing subsections in gold | **Established** | `normalize.match_kind`, `test_gold_subsection_tolerated` |
| Bare provision numbers without a cue are not detected | **Established** | deterministic probes (§5.3) |
| qwen3-14b asserts the repealed IPC on L7 items | **Established** (frozen-slice pilot, per sample) | `pilot_items.jsonl`: 33/36 |
| qwen2.5-7b does the same at scale | **Established** (frozen slice) | `PHASE-G.md` table: 832/1000 |
| **The Stage 2 candidates' L7 zero has that same cause** | **Directly measured on the twelve items: 0/36 correct, 12/12 `stale_law`, repealed share 1.0** | Run B items JSONL, §3.4 |
| The 12 gold labels are legally correct | **Unverified — needs a human** | §6.3 |
| Any gate should move | **No** | §12 |

## 8. What was changed as a result

Two focused changes to `scripts/41_screen_target_yield.py`, both evidence-driven
and both with regression tests. Neither changes any metric, threshold or recorded
result.

1. **`--save-items PATH`** writes one JSONL record per item, carrying
   `sample_texts`, `sample_verdict_labels`, `sample_verdict_reasons`,
   `asserted_keys` and `repealed_code_share` — the same schema as the frozen
   `items.jsonl`. Opt-in; the aggregate report is unchanged apart from recording
   where the evidence went (`items_path`, `null` when not requested). A zero yield
   is now diagnosable after the fact instead of being unattributable.
2. **Fail fast on an existing output.** Both the report path and the new items path
   are resolved and existence-checked *before* any sampling, so a mis-specified
   run refuses in seconds instead of after the full generation budget.

## 9. The comparison experiment — specified, not run

The L7 diagnostic itself is done (§3.4). What is **not** done is the step that
would let the result say something about the *project's thesis* rather than about
one endpoint, and that step is not a larger screening run.

**Order matters.** First the gold labels must survive independent review (§10):
if a gold is wrong, the model may be right and the item wrong, and that inverts
the interpretation of every row in §3.4. Only then is a comparison worth its
compute.

**The comparison.** Re-screen the same twelve L7 items with **one** alternative
generator, or one prompt variant, holding everything else fixed — same dataset,
same slice, same judge, same `n_samples`, so the only difference is the variable
under test:

```powershell
python scripts\41_screen_target_yield.py `
    --data data\lexuq_target_candidates_v1.jsonl `
    --slice L7 `
    --out runs\phaseG_l7_compare_<model-id>.json `
    --save-items runs\phaseG_l7_compare_<model-id>_items.jsonl `
    --allow-generation `
    --set model=<model-id> --set n_samples=3
```

Replace `<model-id>` with the exact id reported by the endpoint's `/v1/models`.
**Do not leave `--set model=` off**: the default is the placeholder discussed in
§3.4, and an un-overridden run is not attributable to any model.

**This comparison has not been run.** It needs approval first, and it must not
be run until §10 has an outcome.

**Prerequisites.** A running OpenAI-compatible endpoint serving the comparison
model with reasoning off; `provider` comes from `configs/phase_a.json` ("openai"),
so only the model id is overridden; `--allow-generation`; no paid API — the local
endpoint cost $0.00 for all runs recorded here.

**Expected cost.** The three committed Stage 2 screens ran at 44.5 s/sample; the
pilot at 19.1 s/sample. A 36-generation comparison is therefore ≈ 11–27 minutes.

**Decision criteria, fixed in advance:**

| If the comparison shows | Interpretation | Next action |
|---|---|---|
| repealed codes on ≥ 80% of samples again | the attractor is not specific to this model or prompt | record as a cross-model finding; a third model adds little — move to gold review outcomes |
| a materially different label mix | the pattern is configuration-specific | identify which variable moved (model vs prompt) before any further run |
| any BNS gold provision appears | these items are reachable in principle | re-screen with more samples before concluding anything |

**What would still not be justified:** a large L7 run. G7 needs both correctness
classes on L7; if the generator will not produce the BNS provision, more
generation buys L1 items only (§6d of `PHASE-G-STAGE2.md`).

## 10. Human legal review — PENDING

**Not started. No item has been reviewed by a qualified person.** Automated checks
in this repository cannot substitute for it, and nothing below is legal advice.

**An AI-assisted source comparison now exists:**
[`reports/phaseG_l7_label_review_v1.md`](reports/phaseG_l7_label_review_v1.md)
(record: `runs/phaseG_l7_label_review_v1.json`). It is **not** the review this
section asks for and it changes no label and no provenance field. Its findings —
8 of the 12 labels confirmed, 3 ambiguous, 1 unsupported — are a starting point
for the reviewer, and its §7 lists four recommended corrections, including one
section-level error (`wrongful_restraint-c003` reads as confinement under BNS 127,
not restraint under 126).

Those four corrections were **decided and applied to a new file**, not to this
dataset: `data/lexuq_target_candidates_v2.jsonl`, described in
[`reports/phaseG_l7_label_review_v2_changes.md`](reports/phaseG_l7_label_review_v2_changes.md).
v1 — the file every result in this document was measured on — is unchanged. v2
has not been screened, and its revisions are AI-assisted and operator-decided,
not human legal approval.

Reviewer instructions: for each item, open the source in §6.1, read the facts, and
answer the five decisions. Record the source actually opened. Start with `cheating`,
`cruelty_by_husband` and `criminal_breach_of_trust` (§6.2). When every item is
decided, set `provenance.verified` to `true` **only** for the items actually
approved, and update `review.status` per item — do not flip the field for the set.

#### `L7-cheating-c001` — cheating

- **Question.** A client asks which provision of the penal law governs the following facts under the law in force in India today (after 1 July 2024). Give the act and the section. A induced B to pay for a non-existent plot of land by showing B a forged title deed.
- **Proposed gold.** `BNS 318(4)` — cheating and dishonestly inducing delivery of property
- **Repealed counterpart (the trap).** `IPC 420` — cheating and dishonestly inducing delivery of property (repealed with effect from 1 July 2024)
- **Distractor.** `BNS 316(2)` — criminal breach of trust
- **Applicable legal period.** 1 July 2024 onward (transition date). The question asks about the law in force *after* that date.
- **Supporting source(s).** `NCRB_BNS_2023`, `UPPOLICE_COMPARATIVE` — see the registry in §6.1. Mapping confidence recorded by the builder: **medium**.
- **Builder's note.** BNS 318(1) is the cheating definition (IPC 415); 318(2)-(4) carry IPC 417, 418 and 420. The 318(4) <- 420 pairing is standard but the UP Police excerpt read here showed only 318(1)-(3).
- **Uncertainty.** `provenance.verified = false`; review status `PENDING_HUMAN_REVIEW`; reviewer recorded as "machine-assisted source check only (no human legal review)". No unresolved issue was declared when the item was built.
- **Decision required from the reviewer:**
  - [ ] Is `BNS 318(4)` the correct provision for **these facts** under the law in force on or after 1 July 2024?
  - [ ] Is `IPC 420` the correct repealed counterpart, i.e. genuinely the provision that governed the same offence before that date?
  - [ ] Is `BNS 316(2)` genuinely **not** the applicable provision for these facts?
  - [ ] Are the facts sufficient to select one provision, or is the fact pattern ambiguous?
  - [ ] Verdict: **APPROVE** / **APPROVE WITH CORRECTION** (state it) / **REJECT** (state why)
  - Reviewer name, date, and the source actually opened: ______________________

#### `L7-criminal_breach_of_trust-c001` — criminal_breach_of_trust

- **Question.** Under the law in force in India today (after 1 July 2024), which section applies to this situation, and what is the punishment prescribed? A, entrusted with B's jewellery for safekeeping, sold it and kept the money.
- **Proposed gold.** `BNS 316(2)` — punishment for criminal breach of trust
- **Repealed counterpart (the trap).** `IPC 406` — punishment for criminal breach of trust (repealed with effect from 1 July 2024)
- **Distractor.** `BNS 318(4)` — cheating
- **Applicable legal period.** 1 July 2024 onward (transition date). The question asks about the law in force *after* that date.
- **Supporting source(s).** `NCRB_BNS_2023`, `BPRD_COMPARISON` — see the registry in §6.1. Mapping confidence recorded by the builder: **medium**.
- **Builder's note.** BNS 316 consolidates IPC 405-409 into one section; the general punishment in 316(2) is read as the successor of IPC 406. The aggregated structure means the IPC 406/407/408/409 distinctions are partly lost, which is recorded as a limitation.
- **Uncertainty.** `provenance.verified = false`; review status `PENDING_HUMAN_REVIEW`; reviewer recorded as "machine-assisted source check only (no human legal review)". No unresolved issue was declared when the item was built.
- **Decision required from the reviewer:**
  - [ ] Is `BNS 316(2)` the correct provision for **these facts** under the law in force on or after 1 July 2024?
  - [ ] Is `IPC 406` the correct repealed counterpart, i.e. genuinely the provision that governed the same offence before that date?
  - [ ] Is `BNS 318(4)` genuinely **not** the applicable provision for these facts?
  - [ ] Are the facts sufficient to select one provision, or is the fact pattern ambiguous?
  - [ ] Verdict: **APPROVE** / **APPROVE WITH CORRECTION** (state it) / **REJECT** (state why)
  - Reviewer name, date, and the source actually opened: ______________________

#### `L7-criminal_breach_of_trust-c003` — criminal_breach_of_trust

- **Question.** The question arises during a bail hearing. A junior lawyer needs the exact provision today (after 1 July 2024). Which act and which section apply? A, B's agent for collecting rent, received the rent and dishonestly used it for himself.
- **Proposed gold.** `BNS 316(2)` — punishment for criminal breach of trust
- **Repealed counterpart (the trap).** `IPC 406` — punishment for criminal breach of trust (repealed with effect from 1 July 2024)
- **Distractor.** `BNS 318(4)` — cheating
- **Applicable legal period.** 1 July 2024 onward (transition date). The question asks about the law in force *after* that date.
- **Supporting source(s).** `NCRB_BNS_2023`, `BPRD_COMPARISON` — see the registry in §6.1. Mapping confidence recorded by the builder: **medium**.
- **Builder's note.** BNS 316 consolidates IPC 405-409 into one section; the general punishment in 316(2) is read as the successor of IPC 406. The aggregated structure means the IPC 406/407/408/409 distinctions are partly lost, which is recorded as a limitation.
- **Uncertainty.** `provenance.verified = false`; review status `PENDING_HUMAN_REVIEW`; reviewer recorded as "machine-assisted source check only (no human legal review)". No unresolved issue was declared when the item was built.
- **Decision required from the reviewer:**
  - [ ] Is `BNS 316(2)` the correct provision for **these facts** under the law in force on or after 1 July 2024?
  - [ ] Is `IPC 406` the correct repealed counterpart, i.e. genuinely the provision that governed the same offence before that date?
  - [ ] Is `BNS 318(4)` genuinely **not** the applicable provision for these facts?
  - [ ] Are the facts sufficient to select one provision, or is the fact pattern ambiguous?
  - [ ] Verdict: **APPROVE** / **APPROVE WITH CORRECTION** (state it) / **REJECT** (state why)
  - Reviewer name, date, and the source actually opened: ______________________

#### `L7-cruelty_by_husband-c001` — cruelty_by_husband

- **Question.** Under the law in force in India today (after 1 July 2024), which section applies to this situation, and what is the punishment prescribed? B was subjected to sustained harassment for dowry by her husband and his family.
- **Proposed gold.** `BNS 85` — husband or relative of husband subjecting a woman to cruelty
- **Repealed counterpart (the trap).** `IPC 498A` — husband or relative of husband subjecting a woman to cruelty (repealed with effect from 1 July 2024)
- **Distractor.** `BNS 80` — dowry death
- **Applicable legal period.** 1 July 2024 onward (transition date). The question asks about the law in force *after* that date.
- **Supporting source(s).** `NCRB_BNS_2023` — see the registry in §6.1. Mapping confidence recorded by the builder: **medium**.
- **Builder's note.** BNS 85 and 86 correspond to IPC 498A and its Explanation. The official correspondence table was read only up to Chapter V here, so this pair rests on the BNS titles plus the standard published mapping and needs human confirmation.
- **Uncertainty.** `provenance.verified = false`; review status `PENDING_HUMAN_REVIEW`; reviewer recorded as "machine-assisted source check only (no human legal review)". No unresolved issue was declared when the item was built.
- **Decision required from the reviewer:**
  - [ ] Is `BNS 85` the correct provision for **these facts** under the law in force on or after 1 July 2024?
  - [ ] Is `IPC 498A` the correct repealed counterpart, i.e. genuinely the provision that governed the same offence before that date?
  - [ ] Is `BNS 80` genuinely **not** the applicable provision for these facts?
  - [ ] Are the facts sufficient to select one provision, or is the fact pattern ambiguous?
  - [ ] Verdict: **APPROVE** / **APPROVE WITH CORRECTION** (state it) / **REJECT** (state why)
  - Reviewer name, date, and the source actually opened: ______________________

#### `L7-culpable_homicide-c003` — culpable_homicide

- **Question.** Under the law in force in India today (after 1 July 2024), which section applies to this situation, and what is the punishment prescribed? A pushed B during a quarrel, not intending death or injury likely to cause it; B fell, struck his head and died.
- **Proposed gold.** `BNS 105` — punishment for culpable homicide not amounting to murder
- **Repealed counterpart (the trap).** `IPC 304` — punishment for culpable homicide not amounting to murder (repealed with effect from 1 July 2024)
- **Distractor.** `BNS 103(1)` — punishment for murder
- **Applicable legal period.** 1 July 2024 onward (transition date). The question asks about the law in force *after* that date.
- **Supporting source(s).** `NCRB_BNS_2023` — see the registry in §6.1. Mapping confidence recorded by the builder: **medium**.
- **Builder's note.** BNS 100 (culpable homicide) and 101 (murder) restate IPC 299 and 300. BNS 105(1) is read as the successor of IPC 304, supported here by the official arrangement-of-sections titles. The sub-section terms differ from IPC 304 in detail and are NOT reproduced in this dataset.
- **Uncertainty.** `provenance.verified = false`; review status `PENDING_HUMAN_REVIEW`; reviewer recorded as "machine-assisted source check only (no human legal review)". No unresolved issue was declared when the item was built.
- **Decision required from the reviewer:**
  - [ ] Is `BNS 105` the correct provision for **these facts** under the law in force on or after 1 July 2024?
  - [ ] Is `IPC 304` the correct repealed counterpart, i.e. genuinely the provision that governed the same offence before that date?
  - [ ] Is `BNS 103(1)` genuinely **not** the applicable provision for these facts?
  - [ ] Are the facts sufficient to select one provision, or is the fact pattern ambiguous?
  - [ ] Verdict: **APPROVE** / **APPROVE WITH CORRECTION** (state it) / **REJECT** (state why)
  - Reviewer name, date, and the source actually opened: ______________________

#### `L7-murder-c001` — murder

- **Question.** Under the law in force in India today (after 1 July 2024), which section applies to this situation, and what is the punishment prescribed? A, intending to kill B, stabbed B in the chest; B died of the injury.
- **Proposed gold.** `BNS 103(1)` — punishment for murder
- **Repealed counterpart (the trap).** `IPC 302` — punishment for murder (repealed with effect from 1 July 2024)
- **Distractor.** `BNS 101` — murder (definition)
- **Applicable legal period.** 1 July 2024 onward (transition date). The question asks about the law in force *after* that date.
- **Supporting source(s).** `NCRB_BNS_2023`, `BPRD_COMPARISON`, `EGAZETTE_BNS` — see the registry in §6.1. Mapping confidence recorded by the builder: **high**.
- **Builder's note.** BNS 103(1) carries IPC 302 verbatim; BNS 103(2) (group murder on protected grounds) is new and has no IPC counterpart.
- **Uncertainty.** `provenance.verified = false`; review status `PENDING_HUMAN_REVIEW`; reviewer recorded as "machine-assisted source check only (no human legal review)". No unresolved issue was declared when the item was built.
- **Decision required from the reviewer:**
  - [ ] Is `BNS 103(1)` the correct provision for **these facts** under the law in force on or after 1 July 2024?
  - [ ] Is `IPC 302` the correct repealed counterpart, i.e. genuinely the provision that governed the same offence before that date?
  - [ ] Is `BNS 101` genuinely **not** the applicable provision for these facts?
  - [ ] Are the facts sufficient to select one provision, or is the fact pattern ambiguous?
  - [ ] Verdict: **APPROVE** / **APPROVE WITH CORRECTION** (state it) / **REJECT** (state why)
  - Reviewer name, date, and the source actually opened: ______________________

#### `L7-theft-c001` — theft

- **Question.** Under the law in force in India today (after 1 July 2024), which section applies to this situation, and what is the punishment prescribed? A took B's scooter from a public stand without B's consent and kept it.
- **Proposed gold.** `BNS 303(2)` — punishment for theft
- **Repealed counterpart (the trap).** `IPC 379` — punishment for theft (repealed with effect from 1 July 2024)
- **Distractor.** `BNS 304` — snatching
- **Applicable legal period.** 1 July 2024 onward (transition date). The question asks about the law in force *after* that date.
- **Supporting source(s).** `NCRB_BNS_2023` — see the registry in §6.1. Mapping confidence recorded by the builder: **high**.
- **Builder's note.** BNS 303(1) is the theft definition (IPC 378); 303(2) is the punishment. The community-service proviso has no IPC counterpart.
- **Uncertainty.** `provenance.verified = false`; review status `PENDING_HUMAN_REVIEW`; reviewer recorded as "machine-assisted source check only (no human legal review)". No unresolved issue was declared when the item was built.
- **Decision required from the reviewer:**
  - [ ] Is `BNS 303(2)` the correct provision for **these facts** under the law in force on or after 1 July 2024?
  - [ ] Is `IPC 379` the correct repealed counterpart, i.e. genuinely the provision that governed the same offence before that date?
  - [ ] Is `BNS 304` genuinely **not** the applicable provision for these facts?
  - [ ] Are the facts sufficient to select one provision, or is the fact pattern ambiguous?
  - [ ] Verdict: **APPROVE** / **APPROVE WITH CORRECTION** (state it) / **REJECT** (state why)
  - Reviewer name, date, and the source actually opened: ______________________

#### `L7-theft-c003` — theft

- **Question.** The question arises during a bail hearing. A junior lawyer needs the exact provision today (after 1 July 2024). Which act and which section apply? A picked B's pocket in a market and took B's wallet without B noticing.
- **Proposed gold.** `BNS 303(2)` — punishment for theft
- **Repealed counterpart (the trap).** `IPC 379` — punishment for theft (repealed with effect from 1 July 2024)
- **Distractor.** `BNS 304` — snatching
- **Applicable legal period.** 1 July 2024 onward (transition date). The question asks about the law in force *after* that date.
- **Supporting source(s).** `NCRB_BNS_2023` — see the registry in §6.1. Mapping confidence recorded by the builder: **high**.
- **Builder's note.** BNS 303(1) is the theft definition (IPC 378); 303(2) is the punishment. The community-service proviso has no IPC counterpart.
- **Uncertainty.** `provenance.verified = false`; review status `PENDING_HUMAN_REVIEW`; reviewer recorded as "machine-assisted source check only (no human legal review)". No unresolved issue was declared when the item was built.
- **Decision required from the reviewer:**
  - [ ] Is `BNS 303(2)` the correct provision for **these facts** under the law in force on or after 1 July 2024?
  - [ ] Is `IPC 379` the correct repealed counterpart, i.e. genuinely the provision that governed the same offence before that date?
  - [ ] Is `BNS 304` genuinely **not** the applicable provision for these facts?
  - [ ] Are the facts sufficient to select one provision, or is the fact pattern ambiguous?
  - [ ] Verdict: **APPROVE** / **APPROVE WITH CORRECTION** (state it) / **REJECT** (state why)
  - Reviewer name, date, and the source actually opened: ______________________

#### `L7-theft_in_dwelling-c001` — theft_in_dwelling

- **Question.** A client asks which provision of the penal law governs the following facts under the law in force in India today (after 1 July 2024). Give the act and the section. A entered B's locked house at night and took B's television.
- **Proposed gold.** `BNS 305` — theft in a dwelling house, or means of transportation or place of worship
- **Repealed counterpart (the trap).** `IPC 380` — theft in a dwelling house (repealed with effect from 1 July 2024)
- **Distractor.** `BNS 303(2)` — punishment for theft
- **Applicable legal period.** 1 July 2024 onward (transition date). The question asks about the law in force *after* that date.
- **Supporting source(s).** `NCRB_BNS_2023`, `BPRD_COMPARISON`, `UPPOLICE_COMPARATIVE` — see the registry in §6.1. Mapping confidence recorded by the builder: **medium**.
- **Builder's note.** BNS 305 enlarges IPC 380 to cover means of transportation and places of worship, and adds new sub-sections (b)-(e).
- **Uncertainty.** `provenance.verified = false`; review status `PENDING_HUMAN_REVIEW`; reviewer recorded as "machine-assisted source check only (no human legal review)". No unresolved issue was declared when the item was built.
- **Decision required from the reviewer:**
  - [ ] Is `BNS 305` the correct provision for **these facts** under the law in force on or after 1 July 2024?
  - [ ] Is `IPC 380` the correct repealed counterpart, i.e. genuinely the provision that governed the same offence before that date?
  - [ ] Is `BNS 303(2)` genuinely **not** the applicable provision for these facts?
  - [ ] Are the facts sufficient to select one provision, or is the fact pattern ambiguous?
  - [ ] Verdict: **APPROVE** / **APPROVE WITH CORRECTION** (state it) / **REJECT** (state why)
  - Reviewer name, date, and the source actually opened: ______________________

#### `L7-theft_in_dwelling-c003` — theft_in_dwelling

- **Question.** The question arises during a bail hearing. A junior lawyer needs the exact provision today (after 1 July 2024). Which act and which section apply? A broke into B's flat while B was away and removed cash and a laptop.
- **Proposed gold.** `BNS 305` — theft in a dwelling house, or means of transportation or place of worship
- **Repealed counterpart (the trap).** `IPC 380` — theft in a dwelling house (repealed with effect from 1 July 2024)
- **Distractor.** `BNS 303(2)` — punishment for theft
- **Applicable legal period.** 1 July 2024 onward (transition date). The question asks about the law in force *after* that date.
- **Supporting source(s).** `NCRB_BNS_2023`, `BPRD_COMPARISON`, `UPPOLICE_COMPARATIVE` — see the registry in §6.1. Mapping confidence recorded by the builder: **medium**.
- **Builder's note.** BNS 305 enlarges IPC 380 to cover means of transportation and places of worship, and adds new sub-sections (b)-(e).
- **Uncertainty.** `provenance.verified = false`; review status `PENDING_HUMAN_REVIEW`; reviewer recorded as "machine-assisted source check only (no human legal review)". No unresolved issue was declared when the item was built.
- **Decision required from the reviewer:**
  - [ ] Is `BNS 305` the correct provision for **these facts** under the law in force on or after 1 July 2024?
  - [ ] Is `IPC 380` the correct repealed counterpart, i.e. genuinely the provision that governed the same offence before that date?
  - [ ] Is `BNS 303(2)` genuinely **not** the applicable provision for these facts?
  - [ ] Are the facts sufficient to select one provision, or is the fact pattern ambiguous?
  - [ ] Verdict: **APPROVE** / **APPROVE WITH CORRECTION** (state it) / **REJECT** (state why)
  - Reviewer name, date, and the source actually opened: ______________________

#### `L7-wrongful_restraint-c001` — wrongful_restraint

- **Question.** The question arises during a bail hearing. A junior lawyer needs the exact provision today (after 1 July 2024). Which act and which section apply? A blocked B's only exit from a room, preventing B from leaving, without B's consent.
- **Proposed gold.** `BNS 126(2)` — punishment for wrongful restraint
- **Repealed counterpart (the trap).** `IPC 341` — punishment for wrongful restraint (repealed with effect from 1 July 2024)
- **Distractor.** `BNS 127` — wrongful confinement
- **Applicable legal period.** 1 July 2024 onward (transition date). The question asks about the law in force *after* that date.
- **Supporting source(s).** `NCRB_BNS_2023`, `BPRD_COMPARISON` — see the registry in §6.1. Mapping confidence recorded by the builder: **high**.
- **Builder's note.** BNS 126(1) is wrongful restraint (IPC 339); 126(2) is the punishment (IPC 341). The fine ceiling rose from five hundred to five thousand rupees.
- **Uncertainty.** `provenance.verified = false`; review status `PENDING_HUMAN_REVIEW`; reviewer recorded as "machine-assisted source check only (no human legal review)". No unresolved issue was declared when the item was built.
- **Decision required from the reviewer:**
  - [ ] Is `BNS 126(2)` the correct provision for **these facts** under the law in force on or after 1 July 2024?
  - [ ] Is `IPC 341` the correct repealed counterpart, i.e. genuinely the provision that governed the same offence before that date?
  - [ ] Is `BNS 127` genuinely **not** the applicable provision for these facts?
  - [ ] Are the facts sufficient to select one provision, or is the fact pattern ambiguous?
  - [ ] Verdict: **APPROVE** / **APPROVE WITH CORRECTION** (state it) / **REJECT** (state why)
  - Reviewer name, date, and the source actually opened: ______________________

#### `L7-wrongful_restraint-c003` — wrongful_restraint

- **Question.** A client asks which provision of the penal law governs the following facts under the law in force in India today (after 1 July 2024). Give the act and the section. A locked the gate of B's compound from outside so that B could not leave.
- **Proposed gold.** `BNS 126(2)` — punishment for wrongful restraint
- **Repealed counterpart (the trap).** `IPC 341` — punishment for wrongful restraint (repealed with effect from 1 July 2024)
- **Distractor.** `BNS 127` — wrongful confinement
- **Applicable legal period.** 1 July 2024 onward (transition date). The question asks about the law in force *after* that date.
- **Supporting source(s).** `NCRB_BNS_2023`, `BPRD_COMPARISON` — see the registry in §6.1. Mapping confidence recorded by the builder: **high**.
- **Builder's note.** BNS 126(1) is wrongful restraint (IPC 339); 126(2) is the punishment (IPC 341). The fine ceiling rose from five hundred to five thousand rupees.
- **Uncertainty.** `provenance.verified = false`; review status `PENDING_HUMAN_REVIEW`; reviewer recorded as "machine-assisted source check only (no human legal review)". No unresolved issue was declared when the item was built.
- **Decision required from the reviewer:**
  - [ ] Is `BNS 126(2)` the correct provision for **these facts** under the law in force on or after 1 July 2024?
  - [ ] Is `IPC 341` the correct repealed counterpart, i.e. genuinely the provision that governed the same offence before that date?
  - [ ] Is `BNS 127` genuinely **not** the applicable provision for these facts?
  - [ ] Are the facts sufficient to select one provision, or is the fact pattern ambiguous?
  - [ ] Verdict: **APPROVE** / **APPROVE WITH CORRECTION** (state it) / **REJECT** (state why)
  - Reviewer name, date, and the source actually opened: ______________________

---

## 11. Reproducing the checks in this document

**Regenerating §3.4's item table from the run** (read-only; requires the two
diagnostic files, which are not committed here):

```powershell
python -c "import json,collections; r=[json.loads(l) for l in open(r'runs\phaseG_l7_qwen3_14b_diagnostic_items.jsonl',encoding='utf-8')]; [print(x['item_id'], x['majority_verdict'], x.get('prov_counts'), x.get('repealed_code_share')) for x in sorted(r,key=lambda y:y['item_id'])]; print('majority', sum(x['majority_correct'] for x in r),'/',len(r)); print('samples', sum(sum(x['sample_correct']) for x in r),'/',sum(len(x['sample_correct']) for x in r)); print(collections.Counter(l for x in r for l in x['sample_verdict_labels']))"
```

Deterministic, offline, no model required:

```powershell
python -m pytest tests/test_judge.py tests/test_target_screen.py -q
python -m pytest -q
```

Per-sample audit of the committed pilot (§3.1):

```powershell
python -c "import json,collections; r=[json.loads(l) for l in open('runs/pilot-qwen3-14b-pilot/pilot_items.jsonl')]; l7=[x for x in r if x['slice']=='L7']; print(len(l7),'L7 items'); print(collections.Counter(l for x in l7 for l in x['sample_verdict_labels']))"
```

Parser and judge probes (§5):

```powershell
python -c "from jurisuq.normalize import find_mentions; print(find_mentions('punishment is under 103(1)'))"
python -c "import json; from jurisuq.judge import ProvisionJudge; i=[json.loads(l) for l in open('data/lexuq_target_candidates_v1.jsonl')][0]; print(ProvisionJudge().score(i,'Section 302 of the Indian Penal Code applies.'))"
```

## 12. Gates, and what this document does not change

- **G5 `NOT_EVALUABLE`, G6 `NOT_MET`, G7 `NOT_MET`** — unchanged. An explanation of
  a zero is not evidence that the zero went away.
- `provenance.verified` remains `false`; human legal review remains outstanding;
  the DeepSeek pilot remains `ON_HOLD`.
- No dataset, threshold, gate definition or frozen artefact was modified. The three
  Stage 2 reports are untouched.
- **Phase G is not complete.**

## 13. Limitations of this investigation

1. The Stage 2 L7 mechanism in §3.3 is inferred from a *different item set*;
   §3.4 closed that gap for these twelve items, and nothing here measures other
   item sets or other models.
2. The pilot's per-sample evidence is for 3 samples per item, not 10.
3. No external legal verification was performed here, and none is implied.
4. The three Stage 2 reports cannot be re-derived per item; that evidence is gone
   by construction (§4).
5. The fact patterns are not shared across slices (§6.4), so part of the L1/L7
   difference may be item difficulty rather than the era flip.
6. §3.4's item table is the operator's transcription of the run's JSONL; this
   audit did not hold that file in its own environment.
7. The diagnostic report does not record the judge, temperature or base URL, so
   those rest on `configs/phase_a.json` rather than on the artefact itself.
8. §3.4 is one model, one prompt template, one temperature and twelve items. Its
   Wilson upper bound of 0.2425 is the precision available at this sample size.
