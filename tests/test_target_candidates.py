"""Tests for the Phase G Stage 2 candidate-item-set contract.

`PHASE-G.md` fixes Stage 2's first step as "author an approved candidate item
set in the Phase A schema with ``verified: false`` provenance". These tests pin
that sentence: the schema fields the pipeline needs, the two-slice rule, and the
provenance flag that keeps an unreviewed item set from being mistaken for
reviewed benchmark data.

They also pin what the contract does *not* claim. A passing candidate set is not
evidence that any item is legally correct or answerable, and no gate is decided
here.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from jurisuq.target import candidates as contract
from jurisuq.target.candidates import (ALLOWED_SLICES, REQUIRED_ITEM_FIELDS,
                                       CandidateContractError, content_sha256,
                                       load_candidates, validate_candidates,
                                       validate_item)

ROOT = Path(__file__).resolve().parents[1]


def _item(item_id="L7-theft-001", slice_name="L7", **overrides):
    item = {
        "item_id": item_id,
        "pair_id": "theft-001",
        "slice": slice_name,
        "topic": "theft",
        "template": "T1",
        "question": "Which section applies to this situation?",
        "gold": {"act": "BNS", "provision": "303(2)", "label": "theft"},
        "trap": {"act": "IPC", "provision": "379"},
        "provenance": {"source": "authored for the Stage 2 screen",
                       "verified": False},
    }
    item.update(overrides)
    return item


def _write(tmp_path, items, name="candidates.jsonl"):
    path = tmp_path / name
    path.write_text("\n".join(json.dumps(i) for i in items) + "\n", encoding="utf-8")
    return path


# ----------------------------------------------------------------------
# the documented contract
# ----------------------------------------------------------------------
def test_the_contract_names_its_source_document():
    summary = validate_candidates([_item()])
    assert "PHASE-G.md" in summary["source_document"]
    assert "Stage 2" in summary["source_document"]


def test_the_contract_requires_the_stage_2_unverified_flag():
    assert contract.REQUIRED_PROVENANCE_VERIFIED is False
    assert validate_candidates([_item()])["provenance_verified"] is False


def test_a_valid_set_is_summarised_by_slice():
    items = [_item("L7-a"), _item("L7-b"), _item("L1-a", "L1")]
    summary = validate_candidates(items)
    assert summary["n_items"] == 3
    assert summary["slices"] == {"L1": 1, "L7": 2}


def test_the_summary_records_what_it_did_and_did_not_check():
    summary = validate_candidates([_item()])
    assert "provenance.verified" in summary["checked"]
    # the honesty boundary: a passing set is not a validated item set
    assert any("legal correctness" in entry for entry in summary["not_checked"])
    assert any("any gate" in entry for entry in summary["not_checked"])


def test_required_fields_are_the_ones_the_pipeline_consumes():
    assert set(REQUIRED_ITEM_FIELDS) == {"item_id", "pair_id", "slice", "question"}
    assert ALLOWED_SLICES == ("L1", "L7")


# ----------------------------------------------------------------------
# refusals: schema
# ----------------------------------------------------------------------
@pytest.mark.parametrize("field", REQUIRED_ITEM_FIELDS)
def test_each_required_field_is_enforced(field):
    item = _item()
    item[field] = ""
    with pytest.raises(CandidateContractError, match="missing"):
        validate_candidates([item])


@pytest.mark.parametrize("slice_name", ["L9", "l7", "", "L1+L7"])
def test_only_the_two_benchmark_slices_are_accepted(slice_name):
    with pytest.raises(CandidateContractError, match="slice"):
        validate_candidates([_item(slice_name=slice_name)])


def test_a_missing_gold_object_is_refused():
    item = _item()
    del item["gold"]
    with pytest.raises(CandidateContractError, match="gold object"):
        validate_candidates([item])


@pytest.mark.parametrize("gold", [{"act": "BNS"}, {"provision": "303"}, {}])
def test_gold_must_carry_act_and_provision(gold):
    with pytest.raises(CandidateContractError, match="gold.act and gold.provision"):
        validate_candidates([_item(gold=gold)])


def test_duplicate_item_ids_are_refused():
    with pytest.raises(CandidateContractError, match="duplicate item_id"):
        validate_candidates([_item("L7-a"), _item("L7-a")])


def test_an_empty_set_is_refused():
    with pytest.raises(CandidateContractError, match="no items"):
        validate_candidates([])


def test_a_non_object_item_is_refused():
    with pytest.raises(CandidateContractError, match="not an object"):
        validate_candidates(["just a string"])


# ----------------------------------------------------------------------
# refusals: the provenance flag
# ----------------------------------------------------------------------
def test_an_item_claiming_verification_is_refused():
    """The screen exists to decide whether items are worth a run; an item that
    already claims to be verified is out of contract."""
    with pytest.raises(CandidateContractError, match="verified"):
        validate_candidates([_item(provenance={"source": "s", "verified": True})])


@pytest.mark.parametrize("verified", ["false", 0, None, 1, "no"])
def test_the_verified_flag_must_be_the_boolean_false(verified):
    """A string "false" or an int 0 is not the documented boolean flag."""
    with pytest.raises(CandidateContractError, match="verified"):
        validate_candidates([_item(provenance={"source": "s", "verified": verified})])


def test_missing_provenance_is_refused():
    item = _item()
    del item["provenance"]
    with pytest.raises(CandidateContractError, match="provenance object"):
        validate_candidates([item])


def test_provenance_without_the_verified_key_is_refused():
    with pytest.raises(CandidateContractError, match="'verified' flag"):
        validate_candidates([_item(provenance={"source": "s"})])


@pytest.mark.parametrize("source", ["", "   ", None, 7])
def test_provenance_source_must_be_a_non_empty_string(source):
    with pytest.raises(CandidateContractError, match="provenance.source"):
        validate_candidates([_item(provenance={"source": source, "verified": False})])


def test_validate_item_reports_the_offending_item_id():
    with pytest.raises(CandidateContractError, match="L7-broken"):
        validate_item(_item("L7-broken", provenance={"source": "s", "verified": True}))


# ----------------------------------------------------------------------
# loading files: the real Phase A shape is accepted, and provenance is hashed
# ----------------------------------------------------------------------
def test_a_real_phase_a_record_satisfies_the_schema():
    """The Phase A slice is the schema of record. Its records must pass the
    field and slice checks; they carry ``verified: false`` provenance already."""
    records = [json.loads(line) for line in
               (ROOT / "data" / "lexuq_slice.jsonl").read_text(
                   encoding="utf-8").splitlines() if line.strip()]
    assert records, "the frozen slice must not be empty"
    sample = records[:25]
    for record in sample:
        assert record["provenance"]["verified"] is False
        validate_item(record)
    assert {record["slice"] for record in sample} <= set(ALLOWED_SLICES)


def test_load_candidates_reads_a_valid_file(tmp_path):
    path = _write(tmp_path, [_item(), _item("L1-a", "L1")])
    assert len(load_candidates(path)) == 2


def test_load_candidates_rejects_a_missing_file(tmp_path):
    with pytest.raises(CandidateContractError, match="not found"):
        load_candidates(tmp_path / "absent.jsonl")


def test_content_hash_identifies_the_bytes_screened(tmp_path):
    path = _write(tmp_path, [_item()])
    digest = content_sha256(path)
    assert len(digest) == 64 and all(c in "0123456789abcdef" for c in digest)
    # the hash must change when the item set changes
    changed = _write(tmp_path, [_item("L7-other")], name="other.jsonl")
    assert content_sha256(changed) != digest


def test_content_hash_is_line_ending_agnostic(tmp_path):
    """A Windows checkout must not change the recorded provenance hash."""
    body = json.dumps(_item()) + "\n"
    lf = tmp_path / "lf.jsonl"
    crlf = tmp_path / "crlf.jsonl"
    lf.write_bytes(body.encode("utf-8"))
    crlf.write_bytes(body.replace("\n", "\r\n").encode("utf-8"))
    assert lf.read_bytes() != crlf.read_bytes()
    assert content_sha256(lf) == content_sha256(crlf)
