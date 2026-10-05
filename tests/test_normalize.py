"""Unit tests: normalisation and provision extraction."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jurisuq.normalize import (act_key, find_mentions, norm_num, normalize,
                               provision_matches)


def test_normalize_strips_labels_and_markdown():
    assert normalize("Answer: **Section 103** of the BNS.") == "section 103 of the bns"
    assert normalize("  Final answer - Section 302  ") == "section 302"
    assert normalize("") == ""


def test_normalize_keeps_digits():
    # the discrete channel must not merge 302 and 304
    assert normalize("section 302") != normalize("section 304")


def test_find_mentions_section_and_bare_forms():
    m = find_mentions("A is guilty under Section 302 of the IPC.")
    assert any(x["num"] == "302" and x["act"] == "IPC" for x in m)
    m2 = find_mentions("This is punishable under 103 BNS.")
    assert any(x["num"] == "103" and x["act"] == "BNS" for x in m2)
    m3 = find_mentions("See Article 21.")
    assert any(x["num"] == "21" and x["act"] == "CONSTITUTION" for x in m3)


def test_find_mentions_records_subsection_and_repeal_cue():
    m = find_mentions("Section 303(2) of the BNS applies. IPC 379 was repealed in 2024.")
    sub = [x for x in m if x["num"] == "303"]
    assert sub and sub[0]["sub"] == "2"
    old = [x for x in m if x["num"] == "379"]
    assert old and old[0]["repeal_cue"] is True


def test_provision_matches_respects_act_when_named():
    mentions = find_mentions("Section 302 of the BNS was invoked")
    assert provision_matches(mentions[0], "302", "BNS")
    assert not provision_matches(mentions[0], "302", "IPC")


def test_norm_num_and_act_key():
    assert norm_num("0302") == "302"
    assert norm_num("103(1)") == "1031"
    assert act_key("the indian penal code") == "IPC"
    assert act_key("Bharatiya Nyaya Sanhita") == "BNS"
    assert act_key("nothing here") is None
