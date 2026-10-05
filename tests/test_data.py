"""Unit tests: revision-2 slice construction."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

make_data = importlib.import_module("01_make_data")


def test_questions_are_unique_within_a_slice():
    items = make_data.build(60, seed=5)
    for s in ("L7", "L1"):
        qs = [i["question"] for i in items if i["slice"] == s]
        assert len(qs) == len(set(qs))


def test_slices_are_era_reversed_matched_pairs():
    items = make_data.build(30, seed=9)
    l7 = {i["pair_id"]: i for i in items if i["slice"] == "L7"}
    l1 = {i["pair_id"]: i for i in items if i["slice"] == "L1"}
    assert set(l7) == set(l1), "every L7 item must have an L1 twin"
    for pid, a in l7.items():
        b = l1[pid]
        assert a["gold"]["act"] == "BNS" and b["gold"]["act"] == "IPC"
        assert a["trap"]["act"] == "IPC" and b["trap"]["act"] == "BNS"
        assert a["topic"] == b["topic"]
        assert a["era"] == "current" and b["era"] == "pre2024"
        # the asked-about era must be visible in the question text
        assert "today" in a["question"]
        assert "before 1 July 2024" in b["question"]


def test_gold_and_trap_never_collide():
    for it in make_data.build(40, seed=3):
        gold = it["gold"]["provision"]
        assert gold != it["trap"]["provision"]
        assert gold != it["distractor"]["provision"]


def test_distractors_stay_inside_their_own_code():
    for it in make_data.build(40, seed=4):
        code = it["gold"]["act"]
        assert it["distractor"]["act"] == code, "a distractor must be a sister provision"
        assert it["trap"]["act"] != code, "the trap must be the other code's provision"


def test_every_item_is_flagged_unverified():
    for it in make_data.build(10, seed=1):
        assert it["provenance"]["verified"] is False
