"""Tests for the Phase G §21.3 deployment measurements (jurisuq/evaluation/deployment.py).

Two of the four measurements in the guide cannot be produced from the frozen
runs. The point of these tests is that they come back as ``undefined`` with a
stated reason, never as a zero or a plausible-looking placeholder, and that a
supplied measurement is summarised correctly.
"""
from __future__ import annotations

import json
import math

import pytest

from jurisuq.evaluation.deployment import (
    FULL_CASCADE_STAGES,
    NO_DATA,
    NOT_INSTRUMENTED,
    deployment_report,
    full_cascade_latency,
    ladder_violations,
    peak_memory,
    percentile,
    stage1_latency,
    summarize_latencies,
)


# ----------------------------------------------------------------------
# percentile
# ----------------------------------------------------------------------
def test_percentile_matches_linear_interpolation():
    values = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert percentile(values, 0.5) == pytest.approx(3.0)
    assert percentile(values, 0.95) == pytest.approx(4.8)
    assert percentile(values, 0.0) == pytest.approx(1.0)
    assert percentile(values, 1.0) == pytest.approx(5.0)


def test_percentile_of_one_sample_is_that_sample():
    assert percentile([7.5], 0.95) == pytest.approx(7.5)


def test_percentile_rejects_an_empty_sequence():
    with pytest.raises(ValueError):
        percentile([], 0.5)


def test_percentile_rejects_q_outside_the_unit_interval():
    with pytest.raises(ValueError):
        percentile([1.0, 2.0], 1.5)


def test_p95_is_not_the_maximum():
    values = [float(v) for v in range(1, 21)]      # 1..20
    assert percentile(values, 0.95) == pytest.approx(19.05)
    assert percentile(values, 0.95) < max(values)


# ----------------------------------------------------------------------
# summarize_latencies
# ----------------------------------------------------------------------
def test_summary_reports_every_column():
    block = summarize_latencies([10.0, 20.0, 30.0])
    assert block["n"] == 3
    assert block["median"] == pytest.approx(20.0)
    assert block["mean"] == pytest.approx(20.0)
    assert block["min"] == pytest.approx(10.0)
    assert block["max"] == pytest.approx(30.0)
    assert block["undefined"] is None
    assert block["unit"] == "seconds"


def test_summary_of_empty_input_is_undefined_not_zero():
    block = summarize_latencies([])
    assert block["n"] == 0
    assert block["median"] is None and block["p95"] is None
    assert block["undefined"] == NO_DATA


def test_summary_of_one_sample_notes_that_a_p95_is_meaningless():
    block = summarize_latencies([4.0])
    assert block["n"] == 1
    assert block["p95"] == pytest.approx(4.0)
    assert "single sample" in block["note"]


def test_summary_drops_non_numeric_negative_and_non_finite_values():
    block = summarize_latencies([1.0, None, "2.0", -1.0, float("nan"), True, 3.0])
    assert block["n"] == 2
    assert block["max"] == pytest.approx(3.0)


def test_summary_of_only_bad_values_is_undefined():
    block = summarize_latencies([None, -5.0, float("inf")])
    assert block["n"] == 0
    assert block["undefined"] == NO_DATA


# ----------------------------------------------------------------------
# stage-1 latency
# ----------------------------------------------------------------------
def test_stage1_latency_adds_generation_and_scoring_per_item():
    records = [{"gen_latency_s": 10.0, "scoring_s": 1.0},
               {"gen_latency_s": 20.0, "scoring_s": 1.0}]
    block = stage1_latency(records)
    assert block["n"] == 2
    assert block["median"] == pytest.approx(16.0)
    assert block["n_items_skipped"] == 0


def test_stage1_latency_skips_missing_fields_rather_than_zero_filling():
    records = [{"gen_latency_s": 10.0, "scoring_s": 0.0},
               {"gen_latency_s": 10.0},                     # no scoring
               {"scoring_s": 0.5},                          # no generation
               {}]
    block = stage1_latency(records)
    assert block["n"] == 1
    assert block["n_items_skipped"] == 3
    assert block["median"] == pytest.approx(10.0)


def test_stage1_latency_names_the_modules_it_excludes():
    block = stage1_latency([{"gen_latency_s": 1.0, "scoring_s": 0.0}])
    assert "relation model" in block["modules_excluded"]
    assert "stage-1" in block["stage"]


def test_ladder_failure_names_the_offending_items():
    block = ladder_violations([0.5, 0.5, 0.5], [0.4, 0.9, 0.5])
    assert block["violation_indices"] == [0]
    assert block["n_violations"] == 1


def test_stage1_latency_of_no_records_is_undefined():
    block = stage1_latency([])
    assert block["n"] == 0
    assert block["undefined"] == NO_DATA


# ----------------------------------------------------------------------
# full cascade: undefined with a reason, or measured
# ----------------------------------------------------------------------
def test_full_cascade_is_undefined_with_a_reason_when_not_measured():
    block = full_cascade_latency()
    assert block["median"] is None and block["p95"] is None
    assert block["undefined"] == NOT_INSTRUMENTED
    assert "not instrumented" in block["reason"] or "instrumented" in block["reason"]
    assert block["how_to_measure"]


def test_full_cascade_reports_median_and_p95_when_measured():
    block = full_cascade_latency([400.0, 380.0, 420.0, 390.0])
    assert block["undefined"] is None
    assert block["median"] == pytest.approx(395.0)
    assert block["p95"] is not None and block["p95"] >= block["median"]


def test_full_cascade_lists_every_stage_in_the_measured_path():
    assert block_stages() == list(FULL_CASCADE_STAGES)


def block_stages():
    return full_cascade_latency([1.0])["stages"]


# ----------------------------------------------------------------------
# peak memory
# ----------------------------------------------------------------------
def test_peak_memory_is_undefined_with_a_reason_when_not_measured():
    block = peak_memory()
    assert block["megabytes"] is None
    assert block["undefined"] == NOT_INSTRUMENTED
    assert "no memory sampling" in block["reason"]
    assert block["how_to_measure"]


def test_peak_memory_records_how_it_was_measured():
    block = peak_memory(7420.0, method="psutil sampled rss")
    assert block["megabytes"] == pytest.approx(7420.0)
    assert block["method"] == "psutil sampled rss"
    assert block["undefined"] is None


def test_peak_memory_requires_a_stated_method():
    block = peak_memory(100.0)
    assert block["method"] == "unspecified"
    assert "must state" in block["caveat"] or "state which" in block["caveat"]


@pytest.mark.parametrize("bad", [-1.0, float("nan"), float("inf")])
def test_peak_memory_rejects_impossible_values(bad):
    with pytest.raises(ValueError):
        peak_memory(bad)


# ----------------------------------------------------------------------
# the §21.3 block as a whole
# ----------------------------------------------------------------------
def test_deployment_report_requires_the_configuration_that_ran():
    with pytest.raises(ValueError, match="configuration"):
        deployment_report([], configuration={})


def test_deployment_report_states_the_configuration_actually_measured():
    config = {"model": "qwen2.5-7b-instruct", "quantisation": "q4_k_m", "M": 10,
              "modules_run": ["generation"], "degraded": True}
    report = deployment_report([{"gen_latency_s": 5.0, "scoring_s": 0.1}],
                               configuration=config)
    assert report["configuration_actually_measured"] == config
    assert report["stage1_latency"]["n"] == 1
    assert report["full_cascade_latency"]["undefined"] == NOT_INSTRUMENTED
    assert report["peak_resident_memory"]["undefined"] == NOT_INSTRUMENTED


def test_deployment_report_separates_offline_from_laptop_measurements():
    report = deployment_report([], configuration={"model": "m"})
    assert "stage1_latency" in report["completed_offline"]
    assert "full_cascade_latency" in report["requires_laptop_run"]
    assert "peak_resident_memory" in report["requires_laptop_run"]


def test_deployment_report_is_json_serialisable_without_nan():
    report = deployment_report([{"gen_latency_s": 3.0, "scoring_s": 0.2}],
                               configuration={"model": "m", "M": 10})
    text = json.dumps(report, allow_nan=False)
    assert "NaN" not in text
    for value in (report["stage1_latency"]["median"],
                  report["stage1_latency"]["p95"]):
        assert math.isfinite(value)


# ----------------------------------------------------------------------
# §27.1 degradation ladder
# ----------------------------------------------------------------------
def test_ladder_with_no_violation_when_degradation_only_widens_uncertainty():
    # these are uncertainty scores, so the degraded arm must be >= the full one
    block = ladder_violations([0.5, 0.4, 0.3], [0.6, 0.5, 0.3])
    assert block["n_violations"] == 0
    assert block["violation_indices"] == []
    assert block["monotone"] is True
    assert "degraded_uncertainty >= full_uncertainty" in block["rule"]


def test_ladder_flags_a_degraded_arm_that_becomes_more_confident():
    # degraded uncertainty below the full-cascade uncertainty is the violation:
    # a smaller computation may never buy extra confidence (§27.1)
    block = ladder_violations([0.6, 0.5], [0.4, 0.6])
    assert block["n_violations"] == 1
    assert block["violation_indices"] == [0]
    assert block["monotone"] is False


def test_ladder_requires_equal_lengths():
    with pytest.raises(ValueError):
        ladder_violations([0.5, 0.4], [0.5])


def test_ladder_of_empty_input_is_undefined_and_not_a_pass():
    block = ladder_violations([], [])
    assert block["n"] == 0
    assert block["undefined"] == NO_DATA
    assert block["monotone"] is None
    assert "was not applied" in block["reason"]
