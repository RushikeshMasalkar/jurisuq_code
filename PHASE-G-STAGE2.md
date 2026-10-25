# JURIS-UQ — Phase G Stage 2: candidate population, and where the measurement stops

**Status: PARTIAL.** The candidate item set is built and contract-valid. The
target-yield screen **has been run**, on the principal investigator's machine
(Qwen3 14B via LM Studio), and its figures reproduce exactly under this
repository's own code. Its **report file is not in this repository**, so the
numbers are recorded as reported-and-corroborated rather than as a verified
in-repo artefact. Gate G7 is **unchanged** — a yield screen is not a gate
evaluation.

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
| 4. Candidate-yield screening (24 × 10 samples) | **DONE remotely** — reported complete; artifact pending |
| 5. Affordability decision from `items_needed` | **DONE** — defer, pending the per-slice question (§6a) |
| 6. Gate G7 evaluation | **not evaluable from a screen** — needs a stored run (§8) |
| 7. Human legal review of the items | **OUTSTANDING** |

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

## 6. The screen: reported result, and the one question left open

**Generation guard — works.**

```
python scripts/41_screen_target_yield.py --data data/lexuq_target_candidates_v1.jsonl \
    --out /tmp/should_not_exist.json --set provider=openai
ERROR: this script calls a model when provider != 'mock'. ...
report written? NO
```

### 6a. The reported measurement

The screen was run locally on Qwen3 14B. The figures below were supplied by the
principal investigator; **the report file is not in this repository**, and it was
not reconstructed from this summary.

| Measurement | Value |
|---|---|
| Items / samples | 24 items × 10 samples = **240 generations** |
| Slices | 12 L1 / 12 L7 |
| Majority-correct items | **3 / 24** |
| Majority rate | **0.1250** |
| 95% interval (Wilson) | **[0.0434, 0.3100]** |
| Per-sample correct rate | 0.1417 |
| Projection | **172 items** for 15 correct at 95% confidence |
| Cost | $0.00 (local model) |

**Corroboration performed here.** Every figure was recomputed with this
repository's own code, without regenerating anything:

| Claim | Repo value | Match |
|---|---|---|
| rate 0.1250 for 3 of 24 | `0.125` via `yield_report` | ✅ |
| interval [0.0434, 0.3100] | `[0.043443340766555705, 0.31003881288351376]` | ✅ |
| 172 items for 15 correct | `items_needed(0.125, 15, 0.95)` → `items_for_confidence 172`, `expected_items 120` | ✅ |
| per-sample 0.1417 | 34/240 = `0.14166…` | ✅ arithmetic only |

That is strong evidence the summary came from this codebase's method — but it is
**not** the artefact, and it does not establish what the model actually answered.

### 6b. The question the aggregate cannot answer

`yield_report` breaks down **per topic**, not per slice, and the report carries no
per-item records. So **the 3 correct items cannot be attributed to L1 or L7.**

This matters more than it looks. G7's condition is per slice. The frozen
evidence has **L7 at 0 correct of 100**. If all three correct candidates are L1,
a 172-item full run would still leave L7 single-class and **G7 would remain
`NOT_MET`** however much generation was spent.

`scripts/41` now emits `yield_by_slice` on every run, so this cannot recur. The
existing report predates the change and must be treated as unable to answer it.

### 6c. Affordability decision

Stage 2 asks for a decision from the measured `items_needed`. **Decision: defer
the full run pending the per-slice question.**

A 172-item run is 1,720 generations — roughly **7.2×** the completed screen — and
the summary cannot show that it would fix the L7 arm that actually blocks G7.

### 6d. Earlier blocker, retained

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

`tests/test_target_screen_report.py` holds the checks for the real report. While
the file is absent, seven of them **skip** with a reason naming the missing path;
the four that always run assert that the status record agrees with the repository
about the artefact's absence and that the reported summary is reproducible. The
moment the file is added, the skipped checks activate and verify that it is a
real (non-mock) run over the dataset in this repository, with self-consistent
arithmetic and a projection matching this repository's planning code.

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

# 5. the real screen, once a generator is available
python -X utf8 scripts/41_screen_target_yield.py --data data/lexuq_target_candidates_v1.jsonl \
    --allow-generation
```

Step 5 is the single blocked command. It needs a running LM Studio with a loaded
model, or an approved paid endpoint. Nothing else in this stage is blocked.

## 10. Limitations

1. **The measurement is reported, not in-repo.** The screen ran, but its report
   is absent from the repository, so the numbers are corroborated rather than
   verified against an artefact.
2. **The per-slice split is unknown** (6b) — the central limitation of this
   stage, because it decides whether a full run can change G7.
3. **No human legal review.** `verified: false` everywhere, by design.
4. **Item quality is unvalidated.** Whether the fact patterns are answerable, and
   whether a model actually falls into the trap, is exactly what the blocked
   screen would measure.
5. **Eight offences only.** The frozen benchmark has ten topics including
   criminal intimidation and attempt to murder; those two were left out because
   their punishment sub-section pairings were not directly confirmed here.
   Coverage is narrower than the frozen slice by design, not by oversight.
6. **Sub-section confidence is uneven.** Recorded per offence above; nothing here
   should be treated as settled statutory text without human checking.
7. **Punishment text is deliberately thin.** Graduated terms for BNS 105 and 305
   are described, not restated, to avoid asserting figures not checked here.

## 11. Next action

Two things, in this order.

1. **Add the report file** to `runs/phaseG_screen_qwen3_14b_full.json` in the
   repository. Everything needed to check it is already committed. Once it is
   added, `python -m pytest tests/test_target_screen_report.py -q` activates the
   seven provenance checks — and if the file retains per-item records, the per-slice
   question in 6b can be answered from it directly.
2. **Answer the per-slice question** before authorising any 172-item run. If the
   3 correct items are all L1, a full run cannot fix L7 and G7 stays `NOT_MET`
   regardless of the compute spent. A cheap way to settle it: re-run the screen
   at a small `--items` on L7 only with the updated script, whose
   `yield_by_slice` block answers it directly.

Stage 2 remains **partial**: item authoring, contract validation, the screen and
the affordability decision are done; human legal review and any G7 re-evaluation
are not.
