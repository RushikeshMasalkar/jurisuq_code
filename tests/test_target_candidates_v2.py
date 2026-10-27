"""Guards for the v2 candidate set.

`data/lexuq_target_candidates_v1.jsonl` has been screened, and three committed
screen reports record its sha256 as `data_sha256`. It is therefore frozen: a
correction may never be written into it. The four label revisions decided on
2026-10-27 (reports/phaseG_l7_label_review_v2_changes.md) went into a new
versioned file instead.

These tests hold that line: v1 must still hash to its recorded value, v2 must be
exactly what its builder produces, only the four intended rows may differ, and
nothing may quietly acquire `provenance.verified = true` or a gate claim.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
V1 = ROOT / "data" / "lexuq_target_candidates_v1.jsonl"
V2 = ROOT / "data" / "lexuq_target_candidates_v2.jsonl"
REGISTRY = ROOT / "runs" / "phaseG_l7_candidate_revisions_v1.json"
BUILDER = ROOT / "scripts" / "46_revise_target_candidates_v2.py"

#: The hash the three committed screens were taken over. If this ever changes,
#: those reports silently stop describing this repository's dataset.
V1_SHA256 = "f49f4d91946387eb0534718945092cc2f840bd9f2aee053ed9ac13c3f296d341"

#: The four revisions decided on 2026-10-27, and nothing else.
REVISED = {
    "L7-criminal_breach_of_trust-c003": {"gold_provision": "316(5)",
                                         "trap_provision": "409"},
    "L7-culpable_homicide-c003": {"gold_provision": "105(2)"},
    "L7-wrongful_restraint-c001": {"gold_provision": "126(2)"},
    "L7-wrongful_restraint-c003": {"gold_provision": "127(2)",
                                   "trap_provision": "342",
                                   "distractor_provision": "126(2)"},
}


def _lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def _items(path: Path) -> list[dict]:
    return [json.loads(line) for line in _lines(path)]


def _by_id(items: list[dict]) -> dict[str, dict]:
    return {item["item_id"]: item for item in items}


@pytest.fixture(scope="module")
def v1_items() -> list[dict]:
    return _items(V1)


@pytest.fixture(scope="module")
def v2_items() -> list[dict]:
    return _items(V2)


# ----------------------------------------------------------------------
# v1 is frozen
# ----------------------------------------------------------------------
def test_v1_still_hashes_to_the_value_the_screens_recorded():
    from jurisuq.target import content_sha256

    assert content_sha256(V1) == V1_SHA256, (
        "v1 has been edited in place; the committed screen reports record this "
        "hash and would no longer describe the dataset they were taken over")


def test_the_committed_screens_still_reference_v1_not_v2():
    for name in ("full", "sliced", "smoke"):
        report = json.loads(
            (ROOT / "runs" / f"phaseG_screen_qwen3_14b_{name}.json").read_text(encoding="utf-8"))
        assert report["data_sha256"] == V1_SHA256
        assert report["data_path"].endswith("lexuq_target_candidates_v1.jsonl")


def test_the_two_versions_are_different_files_and_must_not_be_pooled():
    from jurisuq.target import content_sha256

    assert content_sha256(V1) != content_sha256(V2)


# ----------------------------------------------------------------------
# v2 satisfies the same contract as v1
# ----------------------------------------------------------------------
def test_v2_satisfies_the_candidate_contract():
    from jurisuq.target import load_candidates

    items = load_candidates(V2)
    assert len(items) == 24


def test_v2_keeps_the_shape_of_v1(v1_items, v2_items):
    assert len(v2_items) == len(v1_items) == 24
    assert [i["item_id"] for i in v2_items] == [i["item_id"] for i in v1_items]
    assert [i["pair_id"] for i in v2_items] == [i["pair_id"] for i in v1_items]
    slices = [i["slice"] for i in v2_items]
    assert slices.count("L1") == 12 and slices.count("L7") == 12


# ----------------------------------------------------------------------
# exactly the four decided revisions, and nothing else
# ----------------------------------------------------------------------
def test_only_the_four_decided_rows_differ_from_v1():
    v1_lines, v2_lines = _lines(V1), _lines(V2)
    assert len(v1_lines) == len(v2_lines) == 24
    differing = [json.loads(a)["item_id"]
                 for a, b in zip(v1_lines, v2_lines) if a != b]
    assert sorted(differing) == sorted(REVISED), (
        "the v2 diff must be exactly the four revised rows")


def test_every_other_row_is_byte_identical_to_v1():
    v1_lines, v2_lines = _lines(V1), _lines(V2)
    same = sum(1 for a, b in zip(v1_lines, v2_lines) if a == b)
    assert same == 20


def test_no_l1_item_was_revised(v1_items, v2_items):
    v1_lines, v2_lines = _lines(V1), _lines(V2)
    for raw1, raw2 in zip(v1_lines, v2_lines):
        if json.loads(raw1)["slice"] == "L1":
            assert raw1 == raw2


@pytest.mark.parametrize("item_id,expected", sorted(REVISED.items()))
def test_the_revised_provisions_are_the_decided_ones(v2_items, item_id, expected):
    item = _by_id(v2_items)[item_id]
    for field, value in expected.items():
        assert item[field] == value, f"{item_id}.{field}"


def test_the_agent_item_carries_the_agent_tier_punishment(v2_items):
    item = _by_id(v2_items)["L7-criminal_breach_of_trust-c003"]
    assert "life" in item["punishment"].lower()
    assert item["provenance"]["section_pair"] == {"bns": "316(5)", "ipc": "409"}


def test_the_confinement_item_no_longer_offers_127_as_a_distractor(v2_items):
    item = _by_id(v2_items)["L7-wrongful_restraint-c003"]
    assert item["distractor"]["provision"] == "126(2)"
    assert item["provenance"]["section_pair"] == {"bns": "127(2)", "ipc": "342"}


def test_the_culpable_homicide_facts_now_state_knowledge(v2_items):
    question = _by_id(v2_items)["L7-culpable_homicide-c003"]["question"]
    assert "knowing" in question.lower()
    assert "105(2)" in _by_id(v2_items)["L7-culpable_homicide-c003"]["gold_provision"]


# ----------------------------------------------------------------------
# the revision never claims verification
# ----------------------------------------------------------------------
def test_no_item_in_either_version_claims_verification(v1_items, v2_items):
    for items in (v1_items, v2_items):
        for item in items:
            assert item["provenance"]["verified"] is False
            assert item["review"]["status"] == "PENDING_HUMAN_REVIEW"


def test_only_the_four_revised_items_carry_a_revision_block(v2_items):
    carrying = [i["item_id"] for i in v2_items if "revision" in i["provenance"]]
    assert sorted(carrying) == sorted(REVISED)


def test_every_revision_block_records_its_basis_and_sources(v2_items):
    for item in v2_items:
        block = item["provenance"].get("revision")
        if block is None:
            continue
        assert block["version"] == "v2"
        assert block["date"] == "2026-10-27"
        assert block["sources"] and all(s.startswith("http") for s in block["sources"])
        assert block["reason"].strip()
        assert block["still_requires_human_review"] is True
        assert "not human legal" in block["basis"].lower()
        assert block["changed_fields"]


# ----------------------------------------------------------------------
# the artefacts agree with each other
# ----------------------------------------------------------------------
def test_the_registry_records_both_dataset_hashes_correctly():
    from jurisuq.target import content_sha256

    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    assert registry["datasets"]["v1"]["sha256"] == content_sha256(V1)
    assert registry["datasets"]["v2"]["sha256"] == content_sha256(V2)
    assert registry["datasets"]["v1"]["screened"] is True
    assert registry["datasets"]["v2"]["screened"] is False


def test_the_registry_before_after_matches_the_dataset(v2_items):
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    items = _by_id(v2_items)
    assert len(registry["revisions"]) == 4
    for revision in registry["revisions"]:
        item = items[revision["item_id"]]
        for field, value in revision["after"].items():
            assert item[field] == value, f"{revision['item_id']}.{field}"


def test_the_registry_does_not_move_a_gate_or_claim_a_measurement():
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    assert registry["gates_unchanged"] == {"G5": "NOT_EVALUABLE",
                                           "G6": "NOT_MET", "G7": "NOT_MET"}
    assert registry["pilot_unchanged"] == "ON_HOLD"
    assert registry["datasets"]["v2"]["screened"] is False
    assert "not human legal" in registry["basis"].lower()


def test_the_config_still_points_at_v1():
    """Repointing the configured dataset is a separate, deliberate decision."""
    config = json.loads((ROOT / "configs" / "phase_g_target.json").read_text(encoding="utf-8"))
    assert config["screen"]["data"] == "data/lexuq_target_candidates_v1.jsonl"


# ----------------------------------------------------------------------
# the committed v2 is exactly what the builder produces
# ----------------------------------------------------------------------
def test_the_builder_reproduces_the_committed_v2():
    result = subprocess.run([sys.executable, "-X", "utf8", str(BUILDER), "--check"],
                            cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "matches the builder" in result.stdout
