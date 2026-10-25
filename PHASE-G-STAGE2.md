# JURIS-UQ — Phase G Stage 2: candidate population, and where the measurement stops

**Status: PARTIAL / BLOCKED.** The candidate item set is built and
contract-valid. The candidate-yield screen and the Gate G7 evaluation **were not
and could not be run here**, because this environment has no reachable
generator. That is a resource blocker. It is not a scientific finding and it is
not evidence about any detector.

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
| 4. Candidate-yield screening (24 × 10 samples) | **BLOCKED** — no generator reachable |
| 5. Gate G7 evaluation | **BLOCKED** — depends on step 4 |
| 6. Follow-up experiments | not applicable while step 4 is blocked |

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

## 6. What was run, and the blocker

**Generation guard — works.**

```
python scripts/41_screen_target_yield.py --data data/lexuq_target_candidates_v1.jsonl \
    --out /tmp/should_not_exist.json --set provider=openai
ERROR: this script calls a model when provider != 'mock'. ...
report written? NO
```

**Real generation attempt — fails, no cost.**

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

Dataset-level tests live in `tests/test_target_candidates.py` and cover: the file
exists and parses; 24 items; 12/12 slice balance; 24 distinct questions and ids;
`provenance.verified is False` on every item; every item cites a source and a
section pair; no item carries an authored correctness field; L7 gold is BNS and
its trap is IPC, L1 the reverse; the dataset digest matches the sources record;
and the sources record marks non-primary retrieval honestly.

## 8. G7

**Unchanged at `NOT_MET`.** This stage produced no measured population, so it
cannot re-evaluate G7, let alone pass it. The standing verdict rests on the
frozen run, where L7 has 0 correct of 100 items and no ranking is defined.

Authoring a candidate set cannot move G7 on its own: the §21.2 grid and G7 are
defined over *evaluated partitions of a stored run*, and a set of questions with
no answers cannot enter that grid.

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

1. **No measurement was made.** There is no yield estimate, no correctness
   class, and no G7 evidence from this work.
2. **No human legal review.** `verified: false` everywhere, by design.
3. **Item quality is unvalidated.** Whether the fact patterns are answerable, and
   whether a model actually falls into the trap, is exactly what the blocked
   screen would measure.
4. **Eight offences only.** The frozen benchmark has ten topics including
   criminal intimidation and attempt to murder; those two were left out because
   their punishment sub-section pairings were not directly confirmed here.
   Coverage is narrower than the frozen slice by design, not by oversight.
5. **Sub-section confidence is uneven.** Recorded per offence above; nothing here
   should be treated as settled statutory text without human checking.
6. **Punishment text is deliberately thin.** Graduated terms for BNS 105 and 305
   are described, not restated, to avoid asserting figures not checked here.

## 11. Next action

Run step 5 above on a machine with a loaded local model. That single command
turns this dataset into a measured yield, which is the prerequisite for any G7
re-evaluation. Until it runs, G7 stays `NOT_MET` and Stage 2 stays partial.
