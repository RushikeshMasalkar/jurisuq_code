# Phase G — AI-assisted review of the twelve L7 gold labels

**Status: AI-assisted source comparison complete. This is not human legal
verification, it does not set `provenance.verified`, and it does not discharge the
human legal review recorded as outstanding in
[`PHASE-G-L7-INVESTIGATION.md`](../PHASE-G-L7-INVESTIGATION.md) §10.**

| | |
|---|---|
| Artifact | `reports/phaseG_l7_label_review_v1.md` (this file) |
| Machine-readable record | `runs/phaseG_l7_label_review_v1.json` |
| Dataset reviewed | `data/lexuq_target_candidates_v1.jsonl`, sha256 `f49f4d91946387eb0534718945092cc2f840bd9f2aee053ed9ac13c3f296d341` |
| Scope | the **12 L7 items** only; the 12 L1 items were not reviewed |
| Reviewer | AI-assisted source comparison (an automated agent), **not** a qualified lawyer |
| Gold labels changed | **none** — this report recommends, it does not edit |
| Effect on gates | **none** — see §6 |
| Review date | 2026-10-27 |

## 1. What this review did and did not do

For each of the twelve L7 items it read the stored fact pattern, the stored
`gold_act`/`gold_provision`, the recorded `punishment`, the designed `trap` and
`distractor`, then compared the provision against the enacted text of the
Bharatiya Nyaya Sanhita, 2023 and the commencement notification.

It did **not**: edit the dataset, re-run any generator, call any model, set
`provenance.verified`, or consult a human lawyer. Where a conclusion depends on
how a practising lawyer would characterise facts (rather than on what the section
text says), the item is marked *ambiguous* rather than *confirmed*.

**Commencement, verified.** The BNS was brought into force on **1 July 2024** by
Ministry of Home Affairs notification **S.O. 850(E) dated 23 February 2024**,
which appoints 1 July 2024 for all provisions **except section 106(2)**. The same
notification series (S.O. 848(E), S.O. 849(E)) commenced the BNSS and the BSA.
The items' framing "after 1 July 2024" is therefore correct.

## 2. Outcome

| Status | Count | Items |
|---|---:|---|
| Confirmed | 8 | `cheating-c001`, `criminal_breach_of_trust-c001`, `cruelty_by_husband-c001`, `murder-c001`, `theft-c001`, `theft-c003`, `theft_in_dwelling-c001`, `theft_in_dwelling-c003` |
| Ambiguous | 3 | `criminal_breach_of_trust-c003`, `culpable_homicide-c003`, `wrongful_restraint-c001` |
| Unsupported (likely wrong) | 1 | `wrongful_restraint-c003` |
| Unresolved | 0 | — |

"Unresolved" is zero because every item could be assessed on text that was
actually read. The *confidence* ceiling is set by source access (§5), not by any
item's obscurity.

Two different failures are in play and they should not be conflated:

* **Section-level error (1 item).** `wrongful_restraint-c003`'s facts describe
  wrongful confinement, not wrongful restraint.
* **Subsection-level error (3 items).** The section is right or defensible but the
  cited sub-section — and therefore the stated punishment — is not.

## 3. Item-by-item findings

| # | Item | Facts tested | Gold | Verdict | Basis | Conf. |
|---|---|---|---|---|---|---|
| 1 | `L7-cheating-c001` | Forged title deed shown to induce payment for a non-existent plot | BNS 318(4) | Confirmed | 318(1) defines cheating; 318(4) covers cheating that dishonestly induces the person deceived to deliver property → up to 7 years + fine, matching the recorded punishment. Forgery (BNS 336/340) is also made out, but 318(4) is the provision governing the induced payment | High |
| 2 | `L7-criminal_breach_of_trust-c001` | Jewellery entrusted for safekeeping, sold, proceeds kept | BNS 316(2) | Confirmed | Entrustment plus dishonest conversion = CBT under 316(1); no aggravated capacity is pleaded, so the general tier 316(2) applies (5 years, or fine, or both, raised from 3 years under IPC 406) | High |
| 3 | `L7-criminal_breach_of_trust-c003` | "B's agent for collecting rent" received the rent and used it himself | BNS 316(2) | **Ambiguous — likely wrong** | 316(5) punishes CBT by a person entrusted "in the way of his business as a … agent": life, or up to 10 years, and fine. The correct IPC analogue is **409**, not the item's trap 406. Whether rent collection is "in the way of his business" is a question of fact for a human | Med-High |
| 4 | `L7-cruelty_by_husband-c001` | Sustained dowry harassment by the husband and his family | BNS 85 | Confirmed (section level) | 85 punishes a husband or relative who subjects a woman to cruelty: 3 years + fine. The *definition* of cruelty, including dowry harassment, is in **86** and should be cited in any gold rationale | High |
| 5 | `L7-culpable_homicide-c003` | Push in a quarrel, expressly "not intending death or injury likely to cause it"; fall, head injury, death | BNS 105 | **Ambiguous** | The facts negate intention but are **silent on knowledge**. Knowledge limb → culpable homicide (100) punished under **105(2)**. If knowledge is also absent, the offence is **106(1)** death by negligence, not culpable homicide at all. This is exactly the item on which the diagnostic answered IPC 304A | Medium |
| 6 | `L7-murder-c001` | Intent to kill, stab to the chest, death | BNS 103(1) | Confirmed | 101 defines murder; 103(1) punishes it with death or imprisonment for life + fine | High |
| 7 | `L7-theft-c001` | Scooter taken from a public stand without consent and kept | BNS 303(2) | Confirmed | 303(1) defines theft; 303(2) carries 3 years/fine/both with the repeat-conviction and sub-₹5,000 tiers. Residual risk: 305(b) could be argued for "means of transport", but that limb is aimed at transport in service, not a privately parked scooter | High |
| 8 | `L7-theft-c003` | Wallet lifted from a pocket in a market | BNS 303(2) | Confirmed | 303(2); its Explanation expressly includes "pick pocketing" among the forms relevant to the repeat-conviction tier | High |
| 9 | `L7-theft_in_dwelling-c001` | Entered a locked house at night, took a television | BNS 305 | Confirmed | 305(a): theft in any building used as a human dwelling → up to 7 years + fine | High |
| 10 | `L7-theft_in_dwelling-c003` | Broke into a flat, removed cash and a laptop | BNS 305 | Confirmed | Same limb, 305(a). House-trespass provisions may also be attracted, but the theft provision is 305 | High |
| 11 | `L7-wrongful_restraint-c001` | Blocked B's **only exit from a room**, preventing B from leaving | BNS 126(2) | **Ambiguous** | 126(1) restrains by obstructing proceeding "in any direction"; **127(1)** confines by restraining "in such a manner as to prevent that person from proceeding beyond certain circumscribing limits", Illustration 1 being "locks Z in". B inside a room with the only exit blocked reads as confinement → 127(2), up to 1 year, against 126(2)'s 1 month. The punishment gap makes the choice substantive | Medium |
| 12 | `L7-wrongful_restraint-c003` | **Locked the gate of B's compound from outside** so that B could not leave | BNS 126(2) | **Unsupported** | On the section text and 127's own illustrations this is wrongful confinement under **127**, not restraint under 126. The item's own distractor (127) is arguably the correct answer. Gold should be 127(2) | Med-High |

## 4. Findings that go beyond the individual items

### 4.1 A builder-level mapping defect in the criminal-breach-of-trust topic

`L7-criminal_breach_of_trust-c001` and `-c003` both carry the section pair
`{BNS 316(2), IPC 406}` and the same `mapping_note`, which states that "the
general punishment in 316(2) is read as the successor of IPC 406".

BNS 316 is not a two-part section. It has five sub-sections, each reproducing a
separate IPC provision:

| BNS | IPC | Who | Punishment |
|---|---|---|---|
| 316(1) | 405 | definition | — |
| 316(2) | 406 | any person | up to 5 years, or fine, or both |
| 316(3) | 407 | carrier, wharfinger, warehouse-keeper | up to 7 years + fine |
| 316(4) | 408 | clerk or servant | up to 7 years + fine |
| 316(5) | 409 | public servant, or banker, merchant, factor, broker, attorney or **agent** | life, or up to 10 years, + fine |

The dataset collapsed that structure to a single tier. The defect is latent for
`-c001` (plain entrustment, correctly 316(2)) but active for `-c003`, whose facts
name an **agent**: the gold under-states the punishment by an order of magnitude,
and the item's trap (IPC 406) is not the repealed provision the facts actually
correspond to (IPC 409). This is a defect in the generator
`scripts/45_build_target_candidates.py`'s assumption about BNS 316, not a typo in
one row, and it should be recorded as such rather than fixed row by row forever.

### 4.2 The wrongful-restraint pair appears to test the wrong offence

Both items describe enclosure — B inside a room, B inside a locked compound —
and both golds are 126(2) (restraint). BNS 127 (confinement) is the closer fit on
the statutory language, and under the BNS the two carry materially different
punishments (1 month versus 1 year), so the distinction is not academic.

### 4.3 What a mislabelled item does to a scored run

This matters for the forward experiment. `culpable_homicide-c003` is scored
against `BNS 105`; a generator that answered `BNS 106(1)` would be marked wrong.
`wrongful_restraint-c003` is scored against `BNS 126(2)`; a generator answering
`BNS 127(2)` would be marked wrong. Under the current labels, the *correct* answer
to two items can be scored incorrect.

### 4.4 What it does **not** do to the existing measurement

**The 0/36 result is unaffected.** Every one of the 36 recorded samples asserted a
repealed **IPC** section; not a single sample named any BNS provision. No revision
to any of these twelve golds can convert a recorded answer into a correct one, so
0/12 majority and 0/36 samples stand as recorded. The label defects bear on
(a) human sign-off of the item set and (b) the fairness of any *future* run —
including the cross-model comparison specified in
[`PHASE-G-L7-INVESTIGATION.md`](../PHASE-G-L7-INVESTIGATION.md) §9, which should
not be run against these labels as they stand.

## 5. Sources, and the limits of what was verified

Section texts were checked against reproductions of the enacted Act that agree
across multiple independent sites, plus the commencement notification:

| Provision | Source read |
|---|---|
| BNS 85 | https://devgan.in/bns/section/85/ |
| BNS 103 | https://devgan.in/bns/section/103/ |
| BNS 105 | https://devgan.in/bns/section/105/ |
| BNS 126 | https://devgan.in/bns/section/126/ |
| BNS 127 | https://devgan.in/bns/section/127/ |
| BNS 303 | https://devgan.in/bns/section/303/ |
| BNS 305 | https://devgan.in/bns/section/305/ ; https://lawx.in/acts/section/99/845/7429 ; BPRD *Ready Reckoner on Offences Against Property* https://bprd.nic.in/uploads/pdf/202402021153004864390OFFENCESAGAINSTPROPERTY.pdf |
| BNS 316 (all five sub-sections) | https://devgan.in/bns/section/316/ ; https://lawrato.com/bharatiya-nyaya-sanhita/bns-section-316 |
| BNS 318 | https://devgan.in/bns/section/318/ |
| Commencement, S.O. 850(E) | https://www.mha.gov.in/sites/default/files/BhartiyaNyayaSanhita_24022024.pdf ; footnote to s.1 at https://www.indiacode.nic.in/indiacode/bitstream/123456789/20062/1/a202345.pdf |

**Limits, stated plainly.**

1. The **India Code bare-act PDF could not be opened** from the reviewing
   environment (fetch error), and the MHA gazette PDF itself was not opened —
   its notification text was read from a search-index excerpt. The section texts
   therefore rest on **reproductions that agree across independent sites**, not on
   a gazette page opened by the reviewer.
2. No human lawyer read this. Characterisation questions — is rent collection "in
   the way of his business"; is a blocked exit a confinement; was the push
   accompanied by knowledge — are flagged as ambiguous rather than resolved.
3. Only the 12 L7 items were reviewed. The 12 L1 items are untouched and
   unreviewed.
4. The BNS numbering used here is the **enacted** numbering. The Bill version
   numbered punishment for murder as 101 and for culpable homicide as 103; the
   enacted Act renumbers these to 103 and 105. A reviewer using Bill-era tables
   will mis-assess items 5 and 6.

## 6. Gates and provenance

* G5 `NOT_EVALUABLE`, G6 `NOT_MET`, G7 `NOT_MET` — unchanged. An AI-assisted
  reading of twelve labels cannot move a gate, and no threshold was touched.
* Pilot `ON_HOLD` — unchanged.
* `provenance.verified` remains `false` on every item; every item's
  `review.status` remains `PENDING_HUMAN_REVIEW`.
* The dataset file was not modified by this review.

## 7. Recommended corrections — for human approval, not applied

| Item | Current | Recommended | Why |
|---|---|---|---|
| `L7-criminal_breach_of_trust-c003` | gold `316(2)`, trap `IPC 406`, punishment "up to five years" | gold `316(5)`, trap `IPC 409`, punishment "life, or up to 10 years, and fine"; **or** re-author the facts as a non-capacity entrustment and keep 316(2) | 316(5) names "agent"; 409 is the true IPC analogue of the facts |
| `L7-culpable_homicide-c003` | gold `105`, facts silent on knowledge | gold `105(2)`, and add a knowledge cue to the facts (e.g. "A knew the push was likely to make B fall and strike his head") | Without the cue, 106(1) is equally available and the item tests ambiguity rather than the era flip |
| `L7-wrongful_restraint-c001` | gold `126(2)` | re-author to plain obstruction (e.g. "A stood in front of B's car so that B could not drive on"), keeping 126(2) | The current facts read as confinement |
| `L7-wrongful_restraint-c003` | gold `126(2)` | change gold to `127(2)`, punishment "up to 1 year, or fine up to ₹5,000, or both" | Locking a compound gate is the 127 Illustration case |

Each of these changes would alter the dataset's sha256 and invalidate the
`data_sha256` recorded in the committed screen reports. They should therefore be
made as a **new dataset version** (`…_v2.jsonl`) with the screens re-pointed,
never as an in-place edit of `data/lexuq_target_candidates_v1.jsonl`.

## 8. What this changes in the project state

One thing only: the pending human legal review now has a documented starting
point. The next step for Phase G is unchanged in kind and narrower in scope — a
human reviews these twelve labels, with this report as an input, four specific
questions to answer, and no generation spent until then.
