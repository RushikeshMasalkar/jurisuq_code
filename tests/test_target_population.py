"""Tests for Phase G target-population readiness (jurisuq/target/population.py).

The point of these tests is that the readiness check must refuse to bless a
population that cannot support the documented G5/G6 prerequisites, and must
never impute a detector value to get there.
"""
from __future__ import annotations

import pytest

from jurisuq.target import (
    DETECTOR_FIRED,
    DETECTOR_INVALID,
    DETECTOR_MISSING,
    DETECTOR_PARTIAL,
    DETECTOR_SILENT,
    STATUS_NOT_READY,
    STATUS_READY,
    confound_report,
    detector_state,
    items_needed,
    population_report,
    yield_report,
)


# ----------------------------------------------------------------------
# fixtures
# ----------------------------------------------------------------------
def _record(item_id, *, slice_name="L1", correct, warrant, score=0.5, topic="theft",
            samples=None):
    record = {"item_id": item_id, "slice": slice_name, "topic": topic,
              "majority_correct": correct, "warrant_warranted_agreement": warrant,
              "uq_uncertainty": score}
    if samples is not None:
        record["sample_correct"] = samples
    return record


def _ready_population(n_correct=6, n_incorrect=6):
    """Single slice, both classes, detector fires and stays silent, both partitions."""
    records = []
    for i in range(n_correct):
        records.append(_record(f"L1-c{i}", correct=1, warrant=1.0,
                               score=0.2, topic=f"t{i % 3}"))
    for i in range(n_incorrect):
        records.append(_record(f"L1-w{i}", correct=0, warrant=0.0,
                               score=0.8, topic=f"t{i % 3}"))
    partitions = {r["item_id"]: ("development" if i % 2 == 0 else "evaluation")
                  for i, r in enumerate(records)}
    return records, partitions


# ----------------------------------------------------------------------
# detector_state
# ----------------------------------------------------------------------
@pytest.mark.parametrize("value,expected", [
    (1.0, DETECTOR_SILENT),
    (0.0, DETECTOR_FIRED),
    (0.4, DETECTOR_PARTIAL),
    (None, DETECTOR_MISSING),
    (float("nan"), DETECTOR_INVALID),
    (1.5, DETECTOR_INVALID),
    (-0.1, DETECTOR_INVALID),
    ("1.0", DETECTOR_INVALID),
    (True, DETECTOR_INVALID),
])
def test_detector_state_classifies_every_stored_shape(value, expected):
    assert detector_state(value) == expected


def test_detector_state_does_not_round_interior_values_into_a_state():
    # W = A*T*J*K is continuous; 0.99 is not "silent" and 0.01 is not "fired".
    assert detector_state(0.99) == DETECTOR_PARTIAL
    assert detector_state(0.01) == DETECTOR_PARTIAL


# ----------------------------------------------------------------------
# the happy path
# ----------------------------------------------------------------------
def test_a_population_meeting_every_documented_condition_is_ready():
    records, partitions = _ready_population()
    report = population_report(records, slice_name="L1", partition_of=partitions)
    assert report["status"] == STATUS_READY
    assert all(c["met"] for c in report["conditions"].values())
    assert report["counts"]["correct"] == 6
    assert report["counts"]["incorrect"] == 6


def test_status_documentation_disclaims_any_gate_verdict():
    records, partitions = _ready_population()
    report = population_report(records, slice_name="L1", partition_of=partitions)
    assert "not a gate verdict" in report["status_meaning"]


# ----------------------------------------------------------------------
# the failure modes that matter
# ----------------------------------------------------------------------
def test_single_class_population_is_not_ready():
    """The L7 situation: correct answers absent."""
    records = [_record(f"L7-w{i}", slice_name="L7", correct=0, warrant=0.0)
               for i in range(10)]
    partitions = {r["item_id"]: ("development" if i < 5 else "evaluation")
                  for i, r in enumerate(records)}
    report = population_report(records, slice_name="L7", partition_of=partitions)
    assert report["status"] == STATUS_NOT_READY
    assert report["conditions"]["both_correctness_classes"]["met"] is False
    assert "0 correct" in report["conditions"]["both_correctness_classes"]["detail"]
    assert report["detector_auroc"] is None


def test_population_where_the_detector_never_fires_is_not_ready():
    """Both classes present but W never reaches 0 - the L1 situation."""
    records, partitions = _ready_population()
    for record in records:
        if record["warrant_warranted_agreement"] == 0.0:
            record["warrant_warranted_agreement"] = 0.4   # partial, never fired
    report = population_report(records, slice_name="L1", partition_of=partitions)
    assert report["status"] == STATUS_NOT_READY
    condition = report["conditions"]["detector_fires_and_stays_silent"]
    assert condition["met"] is False
    assert "fired 0" in condition["detail"]


def test_population_where_the_detector_never_stays_silent_is_not_ready():
    records, partitions = _ready_population()
    for record in records:
        record["warrant_warranted_agreement"] = 0.0
    report = population_report(records, slice_name="L1", partition_of=partitions)
    assert report["conditions"]["detector_fires_and_stays_silent"]["met"] is False


def test_pooling_two_slices_is_rejected_even_when_every_count_looks_right():
    """The trap: L1+L7 has both classes, both detector states and both partitions."""
    records, partitions = _ready_population()
    for i in range(4):
        records.append(_record(f"L7-w{i}", slice_name="L7", correct=0, warrant=0.0))
        partitions[f"L7-w{i}"] = "development" if i % 2 == 0 else "evaluation"
    report = population_report(records, slice_name=None, partition_of=partitions)
    assert report["status"] == STATUS_NOT_READY
    assert report["conditions"]["single_slice_population"]["met"] is False
    assert report["slices_present"] == ["L1", "L7"]
    detail = report["conditions"]["single_slice_population"]["detail"]


def test_partition_that_holds_only_one_class_is_not_ready():
    records, _ = _ready_population()
    # every correct record lands in development; evaluation is all incorrect
    partitions = {r["item_id"]: ("development" if r["majority_correct"] == 1
                                 else "evaluation") for r in records}
    report = population_report(records, slice_name="L1", partition_of=partitions)
    assert report["status"] == STATUS_NOT_READY
    assert report["conditions"]["both_classes_in_every_partition"]["met"] is False
    assert "single-class partition" in report["conditions"]["both_classes_in_every_partition"]["detail"]


def test_partition_map_missing_a_partition_is_not_ready():
    records, partitions = _ready_population()
    moved = {i: p for i, p in partitions.items() if p == "development"}
    report = population_report(records, slice_name="L1", partition_of=moved)
    assert report["conditions"]["both_classes_in_every_partition"]["met"] is False


def test_without_a_partition_map_the_condition_fails_closed():
    records, _ = _ready_population()
    report = population_report(records, slice_name="L1")
    assert report["conditions"]["both_classes_in_every_partition"]["met"] is False
    assert "not checked" in report["conditions"]["both_classes_in_every_partition"]["detail"]
    assert report["status"] == STATUS_NOT_READY


# ----------------------------------------------------------------------
# missing values are counted, never imputed
# ----------------------------------------------------------------------
def test_missing_detector_values_are_counted_and_excluded_from_the_auroc():
    records, partitions = _ready_population()
    records.append(_record("L1-gap", correct=0, warrant=None))
    partitions["L1-gap"] = "evaluation"
    report = population_report(records, slice_name="L1", partition_of=partitions)
    assert report["detector_census"][DETECTOR_MISSING] == 1
    assert report["counts"]["incorrect"] == 7          # still a labelled item
    assert report["detector_auroc"] == 1.0             # computed on the 12 real values
    assert report["conditions"]["no_imputed_detector_values"]["met"] is True


def test_an_invalid_detector_value_fails_the_no_imputation_condition():
    records, partitions = _ready_population()
    records.append(_record("L1-bad", correct=1, warrant=1.7))
    partitions["L1-bad"] = "development"
    report = population_report(records, slice_name="L1", partition_of=partitions)
    assert report["conditions"]["no_imputed_detector_values"]["met"] is False


def test_unresolved_correctness_labels_are_excluded_not_counted_as_incorrect():
    records, partitions = _ready_population()
    records.append(_record("L1-unres", correct=None, warrant=1.0))
    partitions["L1-unres"] = "development"
    report = population_report(records, slice_name="L1", partition_of=partitions)
    assert report["counts"]["unlabelled"] == 1
    assert report["counts"]["incorrect"] == 6


# ----------------------------------------------------------------------
# input validation
# ----------------------------------------------------------------------
def test_report_rejects_empty_input():
    with pytest.raises(ValueError):
        population_report([])


def test_report_rejects_an_absent_slice():
    records, _ = _ready_population()
    with pytest.raises(ValueError):
        population_report(records, slice_name="L9")


def test_report_rejects_a_record_without_an_item_id():
    records, _ = _ready_population()
    records.append({"slice": "L1", "majority_correct": 1,
                    "warrant_warranted_agreement": 1.0})
    with pytest.raises(ValueError):
        population_report(records, slice_name="L1")


# ----------------------------------------------------------------------
# the confound diagnostic
# ----------------------------------------------------------------------
def test_confound_report_flags_a_detector_that_is_a_slice_indicator():
    records = ([_record(f"L1-{i}", correct=1 if i % 2 else 0, warrant=1.0)
                for i in range(10)]
               + [_record(f"L7-{i}", slice_name="L7", correct=0, warrant=0.0)
                  for i in range(10)])
    report = confound_report(records)
    assert report["detector_auroc_against_slice_l1"] == 1.0
    # 5 correct (all L1) against 5 incorrect-in-L1 + 10 incorrect-in-L7:
    # (5*5*0.5 + 5*10*1) / 75 = 0.8333 - a number that looks informative only
    # because the slices differ, not because the detector works.
    assert report["detector_auroc_pooled"] == 0.8333
    assert report["detector_auroc_within_slice"]["L1"]["detector_auroc"] == 0.5


def test_confound_report_rejects_records_without_the_needed_fields():
    with pytest.raises(ValueError):
        confound_report([{"item_id": "x", "slice": "L1"}])


# ----------------------------------------------------------------------
# yield estimation
# ----------------------------------------------------------------------
def test_yield_report_separates_majority_rate_from_sample_rate():
    """An item with correct samples but a wrong majority is still an incorrect item."""
    records = [
        _record("a", correct=1, warrant=1.0, samples=[1, 1, 1, 0]),
        _record("b", correct=0, warrant=0.0, samples=[1, 1, 0, 0]),
        _record("c", correct=0, warrant=0.0, samples=[0, 0, 0, 0]),
    ]
    report = yield_report(records)
    overall = report["overall"]
    assert overall["items"] == 3
    assert overall["majority_correct"] == 1
    assert overall["majority_rate"] == pytest.approx(1 / 3)
    # a: 3 correct samples, b: 2, c: 0 -> 5 of 12 (0.417) while the majority
    # rate is 1/3; using the sample rate alone would overstate the yield.
    assert overall["correct_samples"] == 5
    assert overall["sample_rate"] == pytest.approx(5 / 12)
    assert overall["sample_rate"] > overall["majority_rate"]
    assert "not items with at least one correct sample" in report["unit_note"]


def test_yield_report_groups_by_topic_and_tags_missing_topics():
    records = [
        _record("a", correct=1, warrant=1.0, topic="theft"),
        _record("b", correct=0, warrant=0.0, topic="murder"),
        {"item_id": "c", "majority_correct": 0, "warrant_warranted_agreement": 0.0},
    ]
    report = yield_report(records)
    assert set(report["topics"]) == {"theft", "murder", "(untagged)"}
    assert report["topics"]["theft"]["majority_rate"] == 1.0


def test_yield_report_rejects_empty_input():
    with pytest.raises(ValueError):
        yield_report([])


# ----------------------------------------------------------------------
# planning projection
# ----------------------------------------------------------------------
def test_items_needed_at_certainty_returns_the_exact_count():
    block = items_needed(1.0, 15)
    assert block["expected_items"] == 15
    assert block["items_for_confidence"] == 15
    assert block["reachable"] is True


def test_items_needed_at_zero_rate_is_reported_unreachable_not_as_infinity():
    block = items_needed(0.0, 15)
    assert block["reachable"] is False
    assert block["items_for_confidence"] is None
    assert "zero observed rate" in block["note"]


def test_items_needed_grows_with_a_lower_rate_and_a_higher_confidence():
    cheap = items_needed(0.5, 15)
    dear = items_needed(0.1, 15)
    assert dear["items_for_confidence"] > cheap["items_for_confidence"]
    assert cheap["expected_items"] == 30
    assert dear["expected_items"] == 150
    assert (items_needed(0.3, 15, confidence=0.99)["items_for_confidence"]
            > items_needed(0.3, 15, confidence=0.80)["items_for_confidence"])


def test_items_needed_rejects_impossible_arguments():
    with pytest.raises(ValueError):
        items_needed(1.5, 5)
    with pytest.raises(ValueError):
        items_needed(0.5, 0)
    with pytest.raises(ValueError):
        items_needed(0.5, 5, confidence=1.5)
