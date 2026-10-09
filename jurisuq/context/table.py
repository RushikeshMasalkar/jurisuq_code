"""Phase C: the rows of the statute table (``data/statutes/statutes_v1.jsonl``).

``build_rows()`` is a pure function -- no IO, no clock, no randomness -- so
the generated table has a stable sha256 on every machine.

Scope (engineering spec v2, section 15, RISK note): the ten offence clusters
of the frozen slice and the provisions those clusters touch. Three tiers:

1. **Frozen cluster pairs** (10 pairs): gold provisions of ``facts.OFFENCES``,
   both eras. Successor/predecessor exactly mirror the frozen crosswalk
   ``data/relations/crosswalk_v1.jsonl`` -- the store brackets the same slice
   Phase A measured.
2. **Frozen distractor pairs** (3 pairs): the remaining distractors of
   ``facts.OFFENCES`` (IPC 304B/BNS 80, IPC 504/BNS 352, IPC 342/BNS 127).
3. **Coverage-extension pairs** (11 pairs): the provisions most frequently
   asserted in the frozen run ``phaseA-laptop-v2-rejudged`` (IPC 378 is
   asserted 200 times -- without it the coverage report would be fiction).
   Mappings were taken from published IPC->BNS comparative tables (the
   Schedule correspondence reproduced by state-police and legal-reference
   sources, e.g. IPC 306 -> BNS 108, IPC 384 -> BNS 308, IPC 417 -> BNS
   318(2), IPC 468 -> BNS 336, IPC 344 -> BNS 127(4), IPC 345 -> BNS 127(5),
   IPC 409 -> BNS 316(4), IPC 34 -> BNS 3(5)).

EVERY row carries ``verified: false`` until a human compares it with the
official text (gazette + the Schedule to the Bharatiya Nyaya Sanhita, 2023).
One known item for that review: the frozen crosswalk maps IPC 506 ->
"BNS 351(2)", while the official Schedule places criminal intimidation at
BNS 351(4)-(5); the store mirrors the frozen slice and flags the row --
which is exactly what ``verified`` is for.

Dates: the IPC came into force on 1862-01-01 and stands repealed from
2024-07-01; the BNS is in force from 2024-07-01 with no end date.
``in_force_until`` is exclusive (the first date the provision is NOT in
force), so the boundary belongs to exactly one code.
"""
from __future__ import annotations

IPC_FROM = "1862-01-01"
IPC_UNTIL = "2024-07-01"      # exclusive: not in force on 2024-07-01
BNS_FROM = "2024-07-01"

# (ipc_section, bns_section, title, ipc_excerpt, bns_excerpt,
#  offence_cluster, consequence_class, tier)
PAIRS: list[tuple] = [
    # -- tier 1: the ten frozen clusters (gold provisions, both eras) --------
    ("302", "103", "murder",
     "Whoever commits murder shall be punished with death, or imprisonment "
     "for life, and shall also be liable to fine.",
     "Whoever commits murder shall be punished with death or imprisonment "
     "for life, and shall also be liable to fine.",
     "murder", "custodial", "frozen"),
    ("304", "105", "culpable homicide not amounting to murder",
     "Whoever commits culpable homicide not amounting to murder shall be "
     "punished with imprisonment for life, or imprisonment of either "
     "description for a term which may extend to ten years, and shall also "
     "be liable to fine.",
     "Whoever commits culpable homicide not amounting to murder shall be "
     "punished with imprisonment for life, or imprisonment of either "
     "description for a term which may extend to ten years, and shall also "
     "be liable to fine.",
     "culpable_homicide", "custodial", "frozen"),
    ("379", "303(2)", "theft (punishment)",
     "Whoever commits theft shall be punished with imprisonment of either "
     "description for a term which may extend to three years, or with fine, "
     "or with both.",
     "Whoever commits theft shall be punished with imprisonment of either "
     "description for a term which may extend to three years, or with fine, "
     "or with both.",
     "theft", "both", "frozen"),
    ("420", "318(4)", "cheating and dishonestly inducing delivery of property",
     "Whoever cheats and thereby dishonestly induces the person deceived to "
     "deliver any property to any person shall be punished with imprisonment "
     "of either description for a term which may extend to seven years, and "
     "shall also be liable to fine.",
     "Whoever cheats and thereby dishonestly induces the person deceived to "
     "deliver any property to any person shall be punished with imprisonment "
     "of either description for a term which may extend to seven years, and "
     "shall also be liable to fine.",
     "cheating", "custodial", "frozen"),
    ("406", "316(2)", "criminal breach of trust (punishment)",
     "Whoever commits criminal breach of trust shall be punished with "
     "imprisonment of either description for a term which may extend to "
     "three years, or with fine, or with both.",
     "Whoever commits criminal breach of trust shall be punished with "
     "imprisonment of either description for a term which may extend to "
     "five years, or with fine, or with both.",
     "criminal_breach_of_trust", "custodial", "frozen"),
    ("307", "109", "attempt to murder",
     "Whoever does any act with such intention or knowledge, and under such "
     "circumstances that, if he by that act caused death, he would be guilty "
     "of murder, shall be punished with imprisonment of either description "
     "for a term which may extend to ten years, and shall also be liable to "
     "fine.",
     "Whoever does any act with such intention or knowledge, and under such "
     "circumstances that, if he by that act caused death, he would be guilty "
     "of murder, shall be punished with imprisonment of either description "
     "for a term which may extend to ten years, and shall also be liable to "
     "fine.",
     "attempt_to_murder", "custodial", "frozen"),
    ("498A", "85", "cruelty by husband or his relatives",
     "Whoever, being the husband or the relative of the husband of a woman, "
     "subjects such woman to cruelty shall be punished with imprisonment for "
     "a term which may extend to three years and shall also be liable to "
     "fine.",
     "Whoever, being the husband or the relative of the husband of a woman, "
     "subjects such woman to cruelty shall be punished with imprisonment for "
     "a term which may extend to three years and shall also be liable to "
     "fine.",
     "cruelty_by_husband", "custodial", "frozen"),
    # NOTE: the frozen crosswalk says IPC 506 -> "BNS 351(2)"; the official
    # Schedule places criminal intimidation at BNS 351(4)-(5). The store
    # mirrors the frozen slice; verified=false flags this row for review.
    ("506", "351(2)", "criminal intimidation",
     "Whoever commits the offence of criminal intimidation shall be punished "
     "with imprisonment of either description for a term which may extend to "
     "two years, or with fine, or with both.",
     "Whoever commits the offence of criminal intimidation shall be punished "
     "with imprisonment of either description for a term which may extend to "
     "two years, or with fine, or with both.",
     "criminal_intimidation", "custodial", "frozen"),
    ("341", "126(2)", "wrongful restraint (punishment)",
     "Whoever wrongfully restrains any person shall be punished with simple "
     "imprisonment for a term which may extend to one month, or with fine "
     "which may extend to five hundred rupees, or with both.",
     "Whoever wrongfully restrains any person shall be punished with simple "
     "imprisonment for a term which may extend to one month, or with fine "
     "which may extend to five thousand rupees, or with both.",
     "wrongful_restraint", "both", "frozen"),
    ("380", "305", "theft in a dwelling house",
     "Whoever commits theft in any building, tent or vessel, which building, "
     "tent or vessel is used as a human dwelling, or used for the custody of "
     "property, shall be punished with imprisonment of either description "
     "for a term which may extend to seven years, and shall also be liable "
     "to fine.",
     "Whoever commits theft in any building, tent or vessel, which building, "
     "tent or vessel is used as a human dwelling, or used for the custody of "
     "property, shall be punished with imprisonment of either description "
     "for a term which may extend to seven years, and shall also be liable "
     "to fine.",
     "theft_in_dwelling", "custodial", "frozen"),

    # -- tier 2: the remaining frozen distractors -----------------------------
    ("304B", "80", "dowry death",
     "Where the death of a woman is caused by burns or bodily injury, or "
     "occurs otherwise than under normal circumstances, within seven years "
     "of her marriage, and soon before her death she was subjected to "
     "cruelty or harassment for dowry, such death is called dowry death; her "
     "husband or his relative shall be punished with imprisonment for not "
     "less than seven years but which may extend to life.",
     "Where the death of a woman is caused by burns or bodily injury, or "
     "occurs otherwise than under normal circumstances, within seven years "
     "of her marriage, and soon before her death she was subjected to "
     "cruelty or harassment for dowry, such death is called dowry death; her "
     "husband or his relative shall be punished with imprisonment for not "
     "less than seven years but which may extend to life.",
     "cruelty_by_husband", "custodial", "distractor"),
    ("504", "352", "intentional insult with intent to provoke breach of peace",
     "Whoever intentionally insults, and thereby gives provocation to any "
     "person, intending or knowing it to be likely that such provocation "
     "will cause him to break the public peace, or to commit any offence, "
     "shall be punished with imprisonment of either description for a term "
     "which may extend to two years, or with fine, or with both.",
     "Whoever intentionally insults, and thereby gives provocation to any "
     "person, intending or knowing it to be likely that such provocation "
     "will cause him to break the public peace, or to commit any offence, "
     "shall be punished with imprisonment of either description for a term "
     "which may extend to two years, or with fine, or with both.",
     "criminal_intimidation", "custodial", "distractor"),
    ("342", "127", "wrongful confinement",
     "Whoever wrongfully confines any person shall be punished with "
     "imprisonment of either description for a term which may extend to one "
     "year, or with fine which may extend to one thousand rupees, or with "
     "both.",
     "Whoever wrongfully confines any person shall be punished with "
     "imprisonment of either description for a term which may extend to one "
     "year, or with fine which may extend to five thousand rupees, or with "
     "both. Subsections (3)-(8) punish aggravated forms of wrongful "
     "confinement.",
     "wrongful_restraint", "both", "distractor"),

    # -- tier 3: coverage extensions (most-asserted provisions of the frozen
    #    run; mappings from published IPC->BNS comparative tables) -----------
    ("378", "303(1)", "theft (definition)",
     "Whoever, intending to take dishonestly any movable property out of the "
     "possession of any person without that person's consent, moves that "
     "property in order to such taking, is said to commit theft.",
     "Whoever, intending to take dishonestly any movable property out of the "
     "possession of any person without that person's consent, moves that "
     "property in order to such taking, is said to commit theft.",
     "theft", "definition", "extension"),
    ("384", "308", "extortion (punishment)",
     "Whoever commits extortion shall be punished with imprisonment of "
     "either description for a term which may extend to three years, or with "
     "fine, or with both.",
     "Whoever commits extortion shall be punished with imprisonment of "
     "either description for a term which may extend to seven years, and "
     "shall also be liable to fine.",
     "theft", "custodial", "extension"),
    ("304A", "106(1)", "causing death by negligence",
     "Whoever causes the death of any person by doing any rash or negligent "
     "act not amounting to culpable homicide shall be punished with "
     "imprisonment of either description for a term which may extend to two "
     "years, or with fine, or with both.",
     "Whoever causes death of a person by doing any rash or negligent act "
     "not amounting to culpable homicide shall be punished with imprisonment "
     "of either description for a term which may extend to five years, and "
     "shall also be liable to fine.",
     "culpable_homicide", "both", "extension"),
    ("405", "316(1)", "criminal breach of trust (definition)",
     "Whoever, being in any manner entrusted with property, or with any "
     "dominion over property, dishonestly misappropriates or converts to his "
     "own use that property, commits criminal breach of trust.",
     "Whoever, being in any manner entrusted with property, or with any "
     "dominion over property, dishonestly misappropriates or converts to his "
     "own use that property, commits criminal breach of trust.",
     "criminal_breach_of_trust", "definition", "extension"),
    ("409", "316(4)",
     "criminal breach of trust by public servant, banker, merchant or agent",
     "Whoever, being in any manner entrusted with property, in the way of "
     "his employment as a public servant, banker, merchant, factor, broker, "
     "attorney or agent, commits criminal breach of trust in respect of that "
     "property, shall be punished with imprisonment for life, or with "
     "imprisonment of either description for a term which may extend to ten "
     "years, and shall also be liable to fine.",
     "Whoever, being in any manner entrusted with property, in the way of "
     "his employment as a public servant, banker, merchant, factor, broker, "
     "attorney or agent, commits criminal breach of trust in respect of that "
     "property, shall be punished with imprisonment for life, or with "
     "imprisonment of either description for a term which may extend to ten "
     "years, and shall also be liable to fine.",
     "criminal_breach_of_trust", "custodial", "extension"),
    ("306", "108", "abetment of suicide",
     "If any person commits suicide, whoever abets the commission of such "
     "suicide shall be punished with imprisonment of either description for "
     "a term which may extend to ten years, and shall also be liable to "
     "fine.",
     "If any person commits suicide, whoever abets the commission of such "
     "suicide shall be punished with imprisonment of either description for "
     "a term which may extend to ten years, and shall also be liable to "
     "fine.",
     "cruelty_by_husband", "custodial", "extension"),
    ("417", "318(2)", "cheating (punishment)",
     "Whoever cheats shall be punished with imprisonment of either "
     "description for a term which may extend to one year, or with fine, or "
     "with both.",
     "Whoever cheats shall be punished with imprisonment of either "
     "description for a term which may extend to three years, or with fine, "
     "or with both.",
     "cheating", "custodial", "extension"),
    ("468", "336", "forgery for purpose of cheating",
     "Whoever commits forgery, intending that the document forged shall be "
     "used for the purpose of cheating, shall be punished with imprisonment "
     "of either description for a term which may extend to seven years, and "
     "shall also be liable to fine.",
     "Whoever commits forgery, intending that the document forged shall be "
     "used for the purpose of cheating, shall be punished with imprisonment "
     "of either description for a term which may extend to seven years, and "
     "shall also be liable to fine.",
     "cheating", "custodial", "extension"),
    ("34", "3(5)", "acts done by several persons in furtherance of common "
                   "intention",
     "When a criminal act is done by several persons in furtherance of the "
     "common intention of all, each of such persons is liable for that act "
     "in the same manner as if it were done by him alone.",
     "When a criminal act is done by several persons in furtherance of the "
     "common intention of all, each of such persons is liable for that act "
     "in the same manner as if it were done by him alone.",
     "criminal_intimidation", "procedural", "extension"),
    ("344", "127(4)", "wrongful confinement for ten or more days",
     "Whoever wrongfully confines any person for ten days, or more, shall be "
     "punished with imprisonment of either description for a term which may "
     "extend to three years, and shall also be liable to fine.",
     "Whoever wrongfully confines any person for ten days or more shall be "
     "punished with imprisonment of either description for a term which may "
     "extend to five years, and shall also be liable to fine which shall not "
     "be less than ten thousand rupees.",
     "wrongful_restraint", "custodial", "extension"),
    ("345", "127(5)", "wrongful confinement of person for whose liberation "
                      "writ has been issued",
     "Whoever keeps any person in wrongful confinement, knowing that a writ "
     "for the liberation of that person has been duly issued, shall be "
     "punished with imprisonment of either description for a term which may "
     "extend to two years in addition to any term of imprisonment to which "
     "he may be liable under any other section of this Chapter.",
     "Whoever keeps any person in wrongful confinement, knowing that a writ "
     "for the liberation of that person has been duly issued, shall be "
     "punished with imprisonment of either description for a term which may "
     "extend to two years in addition to any other term of imprisonment, and "
     "shall also be liable to fine.",
     "wrongful_restraint", "custodial", "extension"),
]


def build_rows() -> list[dict]:
    """The full statute table as a list of row dicts (spec v2, section 15.1).

    Bracketing pairs are emitted adjacently -- the IPC row first, then its
    BNS successor -- so the file reads as one row per era of each provision.
    """
    rows: list[dict] = []
    for (ipc_sec, bns_sec, title, ipc_text, bns_text, cluster, cons,
         tier) in PAIRS:
        ipc_key = f"IPC {ipc_sec}"
        bns_key = f"BNS {bns_sec}"
        rows.append({
            "act": "IPC", "section": ipc_sec, "title": title,
            "text_excerpt": ipc_text,
            "in_force_from": IPC_FROM, "in_force_until": IPC_UNTIL,
            "successor": bns_key, "predecessor": None,
            "offence_cluster": cluster, "consequence_class": cons,
            "verified": False,
        })
        rows.append({
            "act": "BNS", "section": bns_sec, "title": title,
            "text_excerpt": bns_text,
            "in_force_from": BNS_FROM, "in_force_until": None,
            "successor": None, "predecessor": ipc_key,
            "offence_cluster": cluster, "consequence_class": cons,
            "verified": False,
        })
    return rows


def tier_of(key: str) -> str | None:
    """Which tier a provision key belongs to ('frozen'|'distractor'|'extension')."""
    for (ipc_sec, bns_sec, _t, _a, _b, _c, _d, tier) in PAIRS:
        if key in (f"IPC {ipc_sec}", f"BNS {bns_sec}"):
            return tier
    return None
