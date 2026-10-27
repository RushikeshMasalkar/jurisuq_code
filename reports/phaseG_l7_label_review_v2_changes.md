# Candidate set v2 — the four L7 revisions, and why

**Status: authored, not screened, not human-reviewed.** `data/lexuq_target_candidates_v2.jsonl`
exists so that four defects found by the AI-assisted label review
([`phaseG_l7_label_review_v1.md`](phaseG_l7_label_review_v1.md)) could be corrected
**without touching the dataset the screens were taken over**.

| | |
|---|---|
| Built from | `data/lexuq_target_candidates_v1.jsonl`, sha256 `f49f4d91…d341` — **unchanged** |
| Output | `data/lexuq_target_candidates_v2.jsonl`, sha256 `44e7b5a2…8e8c` |
| Builder | `scripts/46_revise_target_candidates_v2.py` (deterministic; `--check` verifies the committed file) |
| Machine-readable record | `runs/phaseG_l7_candidate_revisions_v1.json` |
| Rows revised | **4 of 24** (all L7); the 12 L1 rows and 8 L7 rows are copied byte for byte |
| Basis | AI-assisted source comparison, **operator-decided 2026-10-27** |
| Human legal approval | **none** — every item still carries `provenance.verified = false` and `review.status = PENDING_HUMAN_REVIEW` |

## 1. Why a new file instead of an edit

The three committed screen reports record `data_sha256 =
f49f4d91946387eb0534718945092cc2f840bd9f2aee053ed9ac13c3f296d341`, the v1 hash.
Editing v1 would leave those reports pointing at a dataset that no longer exists,
which is the failure mode the repository spends most of its Phase G documentation
guarding against. So v1 is frozen, and corrections accumulate in a versioned file.

The two files carry **different hashes and must never be pooled**: v1 carries the
measured screens, v2 carries no measurement at all.

## 2. The four revisions

### 2.1 `L7-criminal_breach_of_trust-c003` — wrong tier, wrong trap

| | v1 | v2 |
|---|---|---|
| Gold | `BNS 316(2)` | **`BNS 316(5)`** |
| Trap | `IPC 406` | **`IPC 409`** |
| Punishment | up to five years, or fine, or both | **imprisonment for life, or up to ten years, and fine** |

The facts say A was *"B's agent for collecting rent"* and used the rent himself.
BNS 316 punishes breach of trust in tiers by capacity: 316(2) is the general tier
reproducing IPC 406, while 316(5) reproduces IPC 409 for a public servant or a
person entrusted *"in the way of his business as a banker, merchant, factor,
broker, attorney or agent"*. "Agent" is named in 316(5), so v1 understated the
tier by an order of magnitude and paired the item with the wrong repealed
counterpart.

Sources: <https://devgan.in/bns/section/316/>,
<https://lawrato.com/bharatiya-nyaya-sanhita/bns-section-316>.

**Open question for the human reviewer:** whether collecting rent is "in the way
of his business" as an agent, or an informal one-off. If it is not, 316(2)/406 was
defensible and this revision should be reverted.

### 2.2 `L7-culpable_homicide-c003` — the missing element

v1 said A pushed B *"not intending death or injury likely to cause it"* and said
nothing about **knowledge** — which is precisely the element that separates BNS
105(2) (knowledge that the act is likely to cause death; up to ten years and fine)
from BNS 106(1) (death by negligence). The item therefore tested an ambiguity
rather than the repealed-code phenomenon.

v2 adds the cue and follows it through:

- **Facts now read** "…, but knowing that the push was likely to make B fall and
  strike his head on the stone floor; B fell, struck his head and died."
- **Gold:** `BNS 105` → **`BNS 105(2)`**
- **Punishment:** "up to ten years and fine (the knowledge limb of BNS 105)"

Sources: <https://devgan.in/bns/section/105/>, <https://devgan.in/bns/section/106/>.

The trap stays `IPC 304`, which remains the repealed counterpart of the knowledge
limb.

### 2.3 `L7-wrongful_restraint-c001` — facts re-authored, gold unchanged

v1 had A block *"B's only exit from a room"*. That prevents B from proceeding
beyond the circumscribing limits of the room, which is **confinement** under BNS
127, not restraint. The gold `126(2)` was therefore testing an offence the facts
did not describe.

v2 re-authors the facts to a plain obstruction: A stands in the road in front of
B's car and refuses to move, so B cannot drive on. Gold, trap (`IPC 341`),
punishment and distractor are unchanged.

Sources: <https://devgan.in/bns/section/126/>, <https://devgan.in/bns/section/127/>.

### 2.4 `L7-wrongful_restraint-c003` — the section-level error

A locks the gate of B's compound from outside so B cannot leave. That is the
lock-in case of BNS 127 (Illustration 1), so v1's gold was wrong at section level,
not merely at subsection level. Worse, v1's *distractor* was BNS 127 — the
distractor was the right answer.

| | v1 | v2 |
|---|---|---|
| Gold | `BNS 126(2)` | **`BNS 127(2)`** |
| Trap | `IPC 341` | **`IPC 342`** |
| Punishment | up to one month, or fine up to ₹5,000, or both | **up to one year, or fine up to ₹5,000, or both** |
| Distractor | `BNS 127` wrongful confinement | **`BNS 126(2)` wrongful restraint** |

Both the trap and the distractor are consequential edits and are worth a
reviewer's eye: IPC 342 is the repealed punishment for confinement (IPC 341 is
restraint), and the distractor moves to 126(2) because restraint is now the
plausible wrong answer. If the reviewer prefers to keep the trap at IPC 341, that
is a one-line change in the builder.

Sources: <https://devgan.in/bns/section/127/>, <https://devgan.in/bns/section/126/>.

## 3. What did not change

- **v1 is byte-identical** — sha256 `f49f4d91…d341`, verified before and after.
- **20 of 24 rows are byte-identical to v1**; only the four revised rows differ,
  and their previous values are recorded in `before` in the registry.
- **Every item_id and pair_id is unchanged**, so v1 and v2 are directly
  comparable item-by-item.
- **Slices unchanged**: 12 L1, 12 L7.
- **Provenance unchanged in kind**: `verified` stays `false` on all 24 items, and
  `review.status` stays `PENDING_HUMAN_REVIEW`. The revision block added to the
  four revised items records the date, basis, decision-maker, reason, sources and
  the fields changed — it does not claim verification.
- **No gate, threshold, config or frozen artefact was touched.**
- `configs/phase_g_target.json` **still points at v1**. Repointing it is a
  separate decision and has not been made.

## 4. What this does not do

1. It does not produce a measurement. **v2 has never been screened**; it has no
   yield, no interval and no projection.
2. It does not change the recorded L7 result. The 2026-10-27 diagnostic ran
   against v1 and produced 0/12 majority and 0/36 samples; that result belongs to
   v1 and stays true of v1.
3. It does not verify anything legally. Four of the eight previously *confirmed*
   labels were left alone on the strength of the AI-assisted review; they are
   still not human-verified.
4. It does not unblock the cross-model comparison. Screening v2 does not replace
   gold-label review — it would repeat the same "is the question right?" risk
   with four fewer known defects.

## 5. Reproducing the revision

```powershell
python -X utf8 scripts/46_revise_target_candidates_v2.py --check
python -X utf8 -c "from jurisuq.target import load_candidates as l; print(len(l('data/lexuq_target_candidates_v2.jsonl')))"
python -X utf8 -m pytest tests/test_target_candidates_v2.py -q
```

`--check` rebuilds v2 in memory and compares it with the committed file, so any
hand-edit of the dataset is caught.
