"""Unit tests: the correctness resolver, revision 2.

Each case comes from a real answer or a real legal subtlety, including the three
failure modes observed on the first laptop run (unresolved counted as wrong, no
act-level rule, no foreign-jurisdiction rule).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jurisuq.judge import ProvisionJudge

L7 = {   # asks about the law in force today; gold is the BNS provision
    "question": "Which section applies today?",
    "gold": {"act": "BNS", "provision": "103", "label": "murder"},
    "trap": {"act": "IPC", "provision": "302", "label": "repealed"},
    "distractor": {"act": "BNS", "provision": "105", "label": "culpable homicide"},
}
L1 = {   # asks about the law as it stood before 1 July 2024; gold is the IPC provision
    "question": "Which section applied before 1 July 2024?",
    "gold": {"act": "IPC", "provision": "302", "label": "murder"},
    "trap": {"act": "BNS", "provision": "103", "label": "successor"},
    "distractor": {"act": "IPC", "provision": "304", "label": "culpable homicide"},
}
J = ProvisionJudge()


# ---- correct answers -------------------------------------------------
def test_gold_stated():
    v = J.score(L7, "Provision: BNS, section 103\nReason: murder is defined there.")
    assert v.correct is True and v.label == "gold"


def test_gold_with_superseded_note():
    text = ("The applicable provision today is Section 103 of the BNS (formerly section 302 of "
            "the Indian Penal Code, which was repealed with effect from 1 July 2024).")
    v = J.score(L7, text)
    assert v.correct is True and v.label == "gold_with_superseded_note"


def test_gold_subsection_tolerated():
    item = {**L7, "gold": {"act": "BNS", "provision": "303(2)"}}
    v = J.score(item, "It is theft under Section 303(2) of the BNS.")
    assert v.correct is True
    v2 = J.score(item, "It is theft under Section 303 of the BNS.")
    assert v2.correct is True          # gold has a subsection, answer does not: accepted


def test_different_subsection_is_not_the_provision():
    item = {**L7, "gold": {"act": "BNS", "provision": "318(4)"}}
    v = J.score(item, "Provision: BNS, section 318(1)")
    assert v.correct is False


def test_foreign_reference_does_not_spoil_a_correct_answer():
    text = ("Provision: BNS, section 103. In most jurisdictions, including the United Kingdom, "
            "the equivalent offence is charged differently.")
    v = J.score(L7, text)
    assert v.correct is True


# ---- wrong answers, by kind -----------------------------------------
def test_stale_law_on_a_today_question():
    v = J.score(L7, "Provision: IPC, section 302\nReason: murder.")
    assert v.correct is False and v.label == "stale_law"


def test_stale_law_named_without_a_section():
    v = J.score(L7, "The Indian Penal Code would apply to these facts.")
    assert v.correct is False and v.label == "stale_law_act_only"


def test_premature_law_on_a_2023_question():
    v = J.score(L1, "Provision: BNS, section 103\nReason: murder.")
    assert v.correct is False and v.label == "premature_law"


def test_wrong_section_same_act():
    v = J.score(L7, "It is culpable homicide under Section 105 of the BNS.")
    assert v.correct is False and v.label == "wrong_section"


def test_foreign_jurisdiction_is_its_own_kind():
    text = ("The applicable provision would be Section 403 of the South African Criminal Procedure "
            "Act 51 of 1977.")
    v = J.score(L7, text)
    assert v.correct is False and v.label == "non_indian_act"


def test_other_jurisdictions_wording():
    v = J.score(L7, "In most jurisdictions the applicable provision is section 403.")
    assert v.correct is False and v.label == "non_indian_act"


# ---- what the judge must refuse to decide ----------------------------
def test_ambiguous_hedge_is_not_guessed():
    text = ("Section 302 of the IPC applies, and Section 103 of the BNS also applies.")
    v = J.score(L7, text)
    assert v.correct is None and v.label == "ambiguous"


def test_no_provision_at_all_is_unresolved():
    v = J.score(L7, "This is a serious offence punishable with imprisonment.")
    assert v.correct is None and v.label == "unresolved"


def test_declining_answer():
    v = J.score(L7, "I cannot determine the specific provision from these facts.")
    assert v.correct is None
    assert v.label in {"declines", "unresolved"}


def test_act_without_section_is_not_guessed_when_era_matches():
    # an unambiguous but incomplete answer: the act named is the right era, no section
    v = J.score(L1, "This was governed by the Indian Penal Code.")
    assert v.correct is None     # nothing wrong is asserted, nothing right is stated
