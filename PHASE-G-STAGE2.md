# JURIS-UQ — Phase G Stage 2: candidate population, and where the measurement stops

**Status: PARTIAL — screening complete, L7 investigation outstanding.** The
candidate item set is built and contract-valid. The target-yield screen has been
run on Qwen3 14B via LM Studio, and **all three artefacts are committed in this
repository**:

| Artefact | Scope |
|---|---|
| [`runs/phaseG_screen_qwen3_14b_full.json`](runs/phaseG_screen_qwen3_14b_full.json) | full run, 24 items × 10 samples |
| [`runs/phaseG_screen_qwen3_14b_sliced.json`](runs/phaseG_screen_qwen3_14b_sliced.json) | full run **with a per-slice breakdown** |
| [`runs/phaseG_screen_qwen3_14b_smoke.json`](runs/phaseG_screen_qwen3_14b_smoke.json) | smoke test, **2 items only — not an evaluation** |

The full and sliced files are **two separate runs of the same 24 items**, not one
run reported twice: they agree on majority-correct items (3/24) and differ on
individual correct samples (34 vs 32). Their sample-level counts must not be
merged or substituted for one another.

The sliced run answers the question the full run could not: **all 3 correct items
are L1 (3/12); L7 produced 0 correct samples out of 120.** Gate G5/G6/G7 are
**unchanged** — a yield screen is not a gate evaluation.

Machine-readable record: [`runs/phaseG_stage2_status.json`](runs/phaseG_stage2_status.json).
Source and review record: [`runs/phaseG_candidate_sources_v1.json`](runs/phaseG_candidate_sources_v1.json).

## 1. What Stage 2 asked for

`PHASE-G.md` §"Remaining work" fixes the sequence:

> Stage 2, when it is authorised, would proceed as: author an approved candidate
> item set in the Phase A schema with `verified: false` provenance; run the yield
> screen (`scripts/41`, ~24 items × 10 samples); decide from the measured
> `items_needed` whether a full run is affordable; and only then run full
> generation under a new run id (`phaseG-target-v1…`).

Gate **G7**: "the target slice carries both correctness classes and the headline
comparison is computable", failing when "no target slice exists on which a
ranking is defined" (`jurisuq/evaluation/matrix.py::gate_g7`).

| Step | Outcome |
|---|---|
| 1. Author candidate set, Phase A schema, `verified: false` | **done** — 24 items |
| 2. Source the candidates, record provenance | **done** — per-item source, section pair, authority level |
| 3. Candidate-contract validation | **done** — `jurisuq/target/candidates.py`, all 24 pass |
| 4. Candidate-yield screening (24 × 10 samples) | **done** — three artefacts committed (§6a–6c) |
| 5. Affordability decision from `items_needed` | **done** — defer, pending L7 investigation (§6d) |
| 6. Investigate the L7 zero | **outstanding** — the reason is not established (§6e) |
| 7. Gate G7 evaluation | **not evaluable from a screen** — needs a stored run (§8) |
| 8. Human legal review of the items | **outstanding** |

## 2. The dataset

`data/lexuq_target_candidates_v1.jsonl` — 24 items, 12 L1 and 12 L7, 8 offences,
24 distinct questions, `sha256 f49f4d91946387eb0534718945092cc2f840bd9f2aee053ed9ac13c3f296d341`.

Built deterministically by `scripts/45_build_target_candidates.py`, which holds
the item table and the citations in one file so the dataset and its provenance
record cannot drift apart. No network, no model.

### Data card

| Field | Value |
|---|---|
| Purpose | candidate population for the Stage 2 yield screen |
| Size | 24 items (12 L1, 12 L7) |
| Schema | Phase A item schema (`item_id`, `pair_id`, `slice`, `question`, `gold`, `trap`, `distractor`, `provenance`) |
| Offences | murder, culpable homicide, theft, theft in a dwelling house, criminal breach of trust, cheating, wrongful restraint, cruelty by a husband |
| Templates | T1, T2, T6 — textually close to the frozen benchmark's frames |
| Language | English |
| Transition date | 1 July 2024 |
| Correctness labels | **none authored** — see §3 |
| `provenance.verified` | `false` on every item |
| Review status | `PENDING_HUMAN_REVIEW` on every item |
| Fact patterns | authored for this dataset; **not** taken from case law or any decided case |
| Known duplication | none; all 24 questions are distinct |

### L7 / L1 construction

The two slices are the same offence viewed from opposite sides of the transition:

* **L7** asks the law *today (after 1 July 2024)*. Gold is the **BNS** section;
  the trap is the **repealed IPC** section.
* **L1** asks the law *immediately before 1 July 2024*. Gold is the **IPC**
  section; the trap is the **BNS** section, which was not in force then.

Example (`L7-murder-c001`): gold `BNS 103(1)` (punishment for murder) against
trap `IPC 302`, both "punishment for murder". The trap is legally correct as a
statement of the pre-transition law and wrong as an answer to the question
asked — which is the exact failure the benchmark is built to detect.

## 3. Why there is no authored correctness label

This is the most important design point in this stage, and it is easy to get
wrong in a way that would fabricate the evidence G7 depends on.

Correctness is **measured**, not authored. `jurisuq/pipeline.py:143` computes
`"majority_correct": int(maj_correct_frac >= 0.5)` by comparing generated samples
against `gold`. The frozen Phase A items contain no correctness field at all.
Authoring a correctness label would be inventing the very measurement that G7
reads, so this dataset deliberately contains none.

The only authored expectation is `review.answerability_hypothesis`, which is
labelled as an untested hypothesis. It is not a measurement and must not be
quoted as a yield.

## 4. Sources and what was actually verified

Full record with per-source authority level: `runs/phaseG_candidate_sources_v1.json`.

| Source | Authority | How it was read here |
|---|---|---|
| Bharatiya Nyaya Sanhita, 2023 bare act (NCRB, MHA) | official government publication | **full text fetched**; official BNS↔IPC corresponding section table read for Chapters I–V |
| Comparison Summary BNS to IPC (BPRD, MHA) | official government publication | search excerpt only (PDF returned HTTP 500) |
| Corresponding Section Table (Uttar Pradesh Police) | official government publication | search excerpt only |
| BNS 2023, No. 45 of 2023 (e-Gazette) | primary legislation | search excerpt only |
| Reference Material on New Criminal Laws (MHA) | official government publication | search excerpt only |

The distinction between "full text fetched" and "search excerpt only" is
recorded per source rather than summarised away, because it is the difference
between citing a document and having checked it.

### The source trap worth recording

The **Bill** version of the BNS, as introduced, numbered *punishment for murder*
as s.101 and *punishment for culpable homicide* as s.103. The **enacted Act**
renumbers these to s.103 and s.105. Any table built from Bill-era numbering will
mis-map exactly the two most prominent offences in this dataset. Every item here
cites the enacted numbering, and the risk is recorded in the status file for the
reviewer.

### Section pairs used

| Offence | BNS | IPC | Sub-section confidence |
|---|---|---|---|
| murder | 103(1) | 302 | high |
| culpable homicide not amounting to murder | 105 | 304 | medium |
| theft | 303(2) | 379 | high |
| theft in a dwelling house | 305 | 380 | medium |
| criminal breach of trust | 316(2) | 406 | medium |
| cheating | 318(4) | 420 | medium |
| wrongful restraint | 126(2) | 341 | medium |
| cruelty by a husband | 85 | 498A | medium |

"Medium" means the *definition* section pair is well evidenced but the
punishment sub-section pairing is less directly confirmed here, or that the
source was read only as an excerpt. No item claims more confidence than that.

## 5. Review performed, and what it is not

Three passes were run, all **machine-assisted by the same system that authored
the items**:

* **Pass A — source verification.** Every item's section pair was checked
  against the sources above. The BNS titles were confirmed against the official
  arrangement of sections. The IPC counterparts were confirmed where the
  correspondence table covered them and otherwise recorded as excerpt-level.
* **Pass B — question and answer review.** Each question states the operative
  date, names no provision, and does not state a punishment figure, so it cannot
  leak its own answer. Gold matches the slice's era. Duplicate check: 24 distinct
  questions.
* **Pass C — consistency review.** Both slices are present and balanced 12/12.
  Gold/trap direction is asserted per item and tested (see §7).

**This is not human legal approval.** The reviewer is the authoring system; there
is no qualified legal reviewer in this loop. `provenance.verified` therefore
remains `false` on every item, and `review.status` remains
`PENDING_HUMAN_REVIEW`. Claiming otherwise would be fabricating approval.

### Review package for a human reviewer

Open `runs/phaseG_candidate_sources_v1.json`, then for each item in the JSONL
check: the section pair against the cited source; the punishment text against
the bare act (the dataset deliberately does *not* restate graduated terms for
BNS 105 or 305); that the fact pattern actually falls in the intended offence
rather than a neighbouring one; and the L1/L7 era direction. Items marked
`subsection_confidence: medium` need this most.

## 6. The screen: what the runs measured, and what they leave open

**Generation guard — works.**

```
python scripts/41_screen_target_yield.py --data data/lexuq_target_candidates_v1.jsonl \
    --out /tmp/should_not_exist.json --set provider=openai
ERROR: this script calls a model when provider != 'mock'. ...
report written? NO
```

### 6a. The full run

`runs/phaseG_screen_qwen3_14b_full.json` — generator `openai-compat:qwen3-14b`,
`is_mock: false`, 24 items × 10 samples, 9,474.5 s wall clock, $0.00 (local model).

| Measurement | Value |
|---|---|
| Items / samples | 24 items × 10 samples = **240 generations** |
| Slices | 12 L1 / 12 L7 |
| Majority-correct items | **3 / 24** |
| Majority rate | **0.1250** |
| 95% interval (Wilson) | **[0.0434, 0.3100]** |
| Individual correct samples | **34 / 240** |
| Sample-level rate | **0.1417** |
| Projection | **172 items** for 15 correct at 95% confidence |
| Cost | $0.00 |

**This report has no per-slice breakdown** (`yield_by_slice` is absent). It
predates the change to `scripts/41` that added one, which is why a second run was
needed to answer the per-slice question.

### 6b. Majority-correct yield is not sample-level accuracy

The two numbers measure different things and must not be interchanged:

* **Majority-correct yield (3/24, 0.1250)** — the fraction of *items* whose
  majority answer across 10 samples is correct. This is the quantity Stage 2
  needs, because an item whose samples are sometimes right but whose majority is
  wrong still contributes an **incorrect** item to the evaluation population.
  `yield_report` says so directly: "Using the sample rate alone would overstate
  yield."
* **Sample-level rate (34/240, 0.1417)** — the fraction of individual generations
  that are correct. It is a property of the generator's sampling, not of the
  population you can build.

Reporting 0.1417 as "the yield" would overstate the usable population by roughly
13%, so the majority figure is the headline and the sample figure is supporting
detail.

### 6c. The sliced run — and what it settles

`runs/phaseG_screen_qwen3_14b_sliced.json` — a **separate run** of the same 24
items (10,684.6 s), identical in configuration but emitting `yield_by_slice`.

| Metric | L1 | L7 | Overall |
|---|---:|---:|---:|
| Candidate items | 12 | 12 | 24 |
| Majority-correct items | **3** | **0** | 3 |
| Majority-correct rate | 0.250 | 0.000 | 0.125 |
| Individual correct samples | 32/120 | **0/120** | 32/240 |
| Sample-level rate | 0.267 | 0.000 | 0.133 |

**Established for this run:** the L7 arm produced **no correct majority answer
and no correct sample at all** across 120 generations. The 3 correct items are
entirely L1.

**Not established by this report:** why. Both zeros are findings, not diagnoses,
and neither report keeps per-item records. The cause was investigated separately
in **[`PHASE-G-L7-INVESTIGATION.md`](PHASE-G-L7-INVESTIGATION.md)**, which finds
that the same model (`qwen3-14b`) asserts the repealed IPC provision in **33 of 36
L7 samples (91.7%)** in the committed frozen-slice pilot, and never once names the
BNS gold. That establishes the mechanism for L7 items of this design; it is
corroboration from a different item set, not a direct measurement of these twelve
items, because this harness discarded the evidence (§4 of that document, now
fixed).

**The full and sliced runs disagree slightly and must be kept apart:** 34 vs 32
correct samples. Both report 3/24 majority. They are independent draws from the
same stochastic process, not a correction of one by the other.

### 6d. Affordability decision

Stage 2 asks for a decision from the measured `items_needed`. **Decision: defer
the full target run pending the L7 investigation.**

The projection (172 items for 15 correct) is computed from the *aggregate* rate of
0.125. But the sliced result shows the aggregate is carried entirely by L1: L7's
own rate is 0.00, and `items_needed` cannot project from a zero rate — it returns
`reachable: false` with the note "a zero observed rate cannot be projected; a
zero would be indistinguishable from an even lower unobserved rate."

So a 172-item run at 1,720 generations (~7.2× the completed screen) would be
buying more L1 items. It cannot be expected to create an L7 correct class, and
without one **G7 remains `NOT_MET`** however much generation is spent.

### 6e. The smoke test

`runs/phaseG_screen_qwen3_14b_smoke.json` — **2 items, 20 generations, 0 correct**,
723.8 s. It exercises connectivity and the report path against the local endpoint
before committing to a long run.

**It is a smoke test, not an evaluation.** Two items cannot estimate a yield; its
projection is `reachable: false` because a zero rate is not projectable. It is
cited here only to record that the harness was checked end to end, and its 0/2
must never be pooled with, averaged against, or reported alongside the full or
sliced runs.

### 6f. Dataset hash

All three reports record
`data_sha256 f49f4d91946387eb0534718945092cc2f840bd9f2aee053ed9ac13c3f296d341`,
which equals `jurisuq.target.content_sha256()` on the committed
`data/lexuq_target_candidates_v1.jsonl`. In this Linux checkout the file is LF, so
the raw-byte and normalised hashes coincide; on a Windows `core.autocrlf` checkout
the raw bytes differ but the normalised hash — the one recorded in the reports —
still matches. That was the previously reported hash discrepancy.

### 6g. Earlier blocker, retained

The failure below is why the screen could not run in *this* environment, and is
kept as the record of that attempt.

**Real generation attempt (in this sandbox) — fails, no cost.**

```
python scripts/41_screen_target_yield.py --data data/lexuq_target_candidates_v1.jsonl \
    --items 2 --out /tmp/screen_real_attempt.json --set provider=openai --allow-generation
RuntimeError: generation request failed after 3 tries:
HTTPConnectionPool(host='127.0.0.1', port=1234): Max retries exceeded ...
Connection refused
```

No LM Studio instance is running here, no API key is present, and the hosted
endpoints are unreachable from this environment. **0 requests succeeded, 0 generations obtained, $0.00 spent.** The DeepSeek pilot stays `ON_HOLD`.

**Mock plumbing check — ran, and is not evidence.**

```
python scripts/41_screen_target_yield.py --data data/lexuq_target_candidates_v1.jsonl \
    --out runs/phaseG_screen_mock_candidates_v1.json --set provider=mock --set n_samples=3
```

Output: 24/24 items, majority rate 1.0000, 8 topics × 3 items.
**This number is meaningless and must never be cited as a yield.** The mock
generator echoes the gold provision, so it is guaranteed to score 1.0; the report
carries `is_mock: true` and the script prints that the mock's numbers are a
plumbing check only. It establishes that the harness ingests a 24-item
contract-valid file end to end and writes a report — nothing more.

## 7. Tests

`tests/test_target_screen_report.py` holds the checks for the real reports. With
the artefacts now committed, **all of its checks run** — none skip. They verify
that each report is a real (non-mock) Qwen3 run, that its `data_sha256` matches
the candidate dataset committed here, that its arithmetic is self-consistent,
that its projection matches this repository's planning code, and that the sliced
report carries both L1 and L7 buckets whose counts reconcile with the aggregate.
They also pin the run-to-run distinction: a report without `yield_by_slice` must
not be treated as having answered the per-slice question.

They verify that it is a
real (non-mock) run over the dataset in this repository, with self-consistent
arithmetic and a projection matching this repository's planning code.

The screen harness itself is covered by `tests/test_target_screen.py`, including
two regression tests added by the L7 investigation: that `--save-items` writes the
per-sample diagnostics the aggregate report cannot carry, and that an existing
output is refused **before** generation rather than after it.

Dataset-level tests live in `tests/test_target_candidates.py` and cover: the file
exists and parses; 24 items; 12/12 slice balance; 24 distinct questions and ids;
`provenance.verified is False` on every item; every item cites a source and a
section pair; no item carries an authored correctness field; L7 gold is BNS and
its trap is IPC, L1 the reverse; the dataset digest matches the sources record;
and the sources record marks non-primary retrieval honestly.

## 8. G7

**Unchanged at `NOT_MET`.** No gate was edited, and no evaluation code was run
that could legitimately change it.

A screen report cannot move G7 even once added. G7 is computed by
`jurisuq/evaluation/matrix.py::gate_g7` over *evaluated partitions of a stored
run* — records carrying detector fields, uncertainty scores and calibration. A
yield report carries none of those: it has no `majority_correct` per item joined
to a detector state, no method scores, and no evaluated partition. Passing it to
the matrix would not produce a defined ranking; it would produce nothing.

The standing L7 finding — 0 correct of 100 — is untouched by the candidate work,
and the reported screen cannot say whether it has changed, because 6b.

## 9. Reproduction

```bash
# 1. build the candidate set (offline, deterministic, no network)
python -X utf8 scripts/45_build_target_candidates.py

# 2. validate against the contract (offline)
python -X utf8 -c "from jurisuq.target import load_candidates as l; print(len(l('data/lexuq_target_candidates_v1.jsonl')))"

# 3. the guard must refuse a real provider without explicit permission
python -X utf8 scripts/41_screen_target_yield.py --data data/lexuq_target_candidates_v1.jsonl \
    --out /tmp/x.json --set provider=openai

# 4. mock plumbing check (NOT a measurement)
python -X utf8 scripts/41_screen_target_yield.py --data data/lexuq_target_candidates_v1.jsonl \
    --out runs/phaseG_screen_mock_candidates_v1.json --set provider=mock --set n_samples=3

# 5. the real screen (needs LM Studio + a loaded model; ~2.6 h for 24 items)
python -X utf8 scripts/41_screen_target_yield.py --data data/lexuq_target_candidates_v1.jsonl \
    --out runs/phaseG_screen_<model>_full.json --allow-generation

# 6. inspect the committed reports without regenerating anything
python -X utf8 -m pytest tests/test_target_screen_report.py -q

# 7. the L7-only diagnostic -- RUN on 2026-10-27; results in PHASE-G-L7-INVESTIGATION.md
#    section 3.4. --slice narrows the run before the cap, so it screens 12 L7 items
#    and never selects L1. --save-items writes the per-item evidence the aggregate
#    omits. --set model= is mandatory: without it the run is labelled with the
#    placeholder in configs/phase_a.json and is not attributable to any model.
python -X utf8 scripts/41_screen_target_yield.py --data data/lexuq_target_candidates_v1.jsonl \
    --slice L7 --out runs/phaseG_l7_qwen3_14b_diagnostic.json \
    --save-items runs/phaseG_l7_qwen3_14b_diagnostic_items.jsonl --allow-generation \
    --set model=qwen3-14b --set n_samples=3
```

Step 5 was already run and its artefacts are committed, so **no regeneration is
needed** to reproduce this document's analysis. Re-running it would spend about
2.6 hours of local compute.

Step 7 **was run** on 2026-10-27 against qwen3-14b: 12 L7 items × 3 samples, 0/12
majority correct, 0/36 correct samples, Wilson 95% interval [0.0, 0.2425], every
sample asserting a repealed code. An earlier attempt used a placeholder model id
and is **not** attributable to Qwen3-14B; the two runs are kept separate in
`PHASE-G-L7-INVESTIGATION.md` section 3.4. The comparison experiment that would
follow gold review has **not** been run.

`--slice SLICE` restricts a screen to one slice (`L1` or `L7`). It is validated
against the slices present in the file, so a typo — or asking for `L1` in an
L7-only file — fails immediately with the available slices named, before any
generation. The report records `slice_filter` (`null` for a whole-set run), and
`candidate_contract.slices` continues to describe the *file*, not the subset, so
a partial run is never mistaken for a full one. Omitting `--slice` screens every
slice exactly as before.

## 10. Limitations

A `--slice` run covers one slice by construction. Its report is **not** a
whole-set screen: `n_items` counts only the selected slice, `yield_by_slice` holds
one bucket, and the exit code still reports whether any majority answer was
correct for that slice alone. Do not compare a slice-filtered rate with the
24-item aggregate rate as if they measured the same population.

1. **The L7 zero is unexplained** (§6c) — the central limitation of this stage.
   Zero correct samples in 120 generations is a finding, not a diagnosis, and no
   per-item records exist to attribute it to item difficulty, label error, or the
   model taking the trap.
2. **Two runs, slightly different sample counts.** The full run found 34 correct
   samples and the sliced run 32, both at 3/24 majority. Neither supersedes the
   other and they must not be pooled.
3. **No human legal review.** `verified: false` everywhere, by design.
4. **Item quality is unvalidated.** The screen measured how often an answer was
   correct *against the item's own gold*, not whether that gold is legally right.
   A wrong gold label would register as a model error, and an unanswerable item
   would register as an incorrect answer.
5. **Eight offences only.** The frozen benchmark has ten topics including
   criminal intimidation and attempt to murder; those two were left out because
   their punishment sub-section pairings were not directly confirmed here.
   Coverage is narrower than the frozen slice by design, not by oversight.
6. **Sub-section confidence is uneven.** Recorded per offence above; nothing here
   should be treated as settled statutory text without human checking.
7. **Punishment text is deliberately thin.** Graduated terms for BNS 105 and 305
   are described, not restated, to avoid asserting figures not checked here.

## 11. The L7 investigation, and the next action

The investigation asked for here has been carried out and is reported in full in
**[`PHASE-G-L7-INVESTIGATION.md`](PHASE-G-L7-INVESTIGATION.md)**. In short:

- **Mechanism.** On L7 items of this design the generator writes the **repealed
  IPC provision**. The committed `qwen3-14b` frozen-slice pilot records 33/36
  L7 samples as `stale_law` and **0** as correct, with 91.7% mean
  `repealed_code_share`; the frozen primary run shows the same at 832/1000.
- **Not a scoring artefact.** The judge accepts correct L7 answers in every form
  tested, tolerates a missing subsection in gold, and the same run scored 32/240
  correct samples on L1 with the same parser — so no slice-agnostic defect can
  produce the 3/12 versus 0/12 split.
- **Two harness defects, fixed.** The screen discarded the per-item diagnostics it
  had already computed (the sole reason the zero was unattributable), and checked
  for an existing output only after the full generation. Both now have regression
  tests.
- **Provenance audited.** All twelve L7 items trace to official government sources
  with URLs, but four of the eight section pairs lean partly on a BPRD PDF that
  could not be opened here (search excerpts only), and two pairs —
  `cheating` and `cruelty_by_husband` — are the weakest. Gold labels remain
  unverified: **human legal review is outstanding**, with a per-item checklist in
  §10 of the investigation document.

**Next action: independent review of the twelve L7 gold labels**, using the
checklist in section 10 of that document. The diagnostic itself has been run
(section 3.4 there): on these twelve items, under this configuration, the
generator produced 0 correct majority answers and 0 correct samples in 36
generations, and every sample asserted a repealed code. That is a measurement on
twelve items with one model — not a statement that L7 is unanswerable in general —
and it does not verify any gold label. A cross-model comparison (section 9 there)
is worth running only after the labels survive review. A larger run is still
**not** justified: the 172-item projection comes from an aggregate rate that L7
contributes nothing to.

An **AI-assisted source comparison** of those twelve labels is recorded in
[`reports/phaseG_l7_label_review_v1.md`](reports/phaseG_l7_label_review_v1.md):
8 confirmed, 3 ambiguous, 1 unsupported, no label changed. It narrows the human
review to four decisions but does not replace it.

Stage 2 remains **partial**: item authoring, contract validation, screening, the
affordability decision and the L7 investigation are done; human legal review and
any G7 re-evaluation are not.
