"""Tests for follow-up experiment 4: topic-clustered bootstrap intervals."""
from __future__ import annotations

import math

import pytest

from jurisuq.calibration.uncertainty_intervals import (
    bootstrap_interval,
    cluster_index,
    normal_interval,
    paired_bootstrap_interval,
    summarize_gate_stability,
    wilson_interval,
)


# ------------------------------------------------------------------- helpers
def test_cluster_index_groups_positions():
    assert cluster_index(["a", "b", "a", "c"]) == {"a": [0, 2], "b": [1], "c": [3]}


def test_cluster_index_rejects_empty_and_bad_ids():
    with pytest.raises(ValueError):
        cluster_index([])
    with pytest.raises(ValueError):
        cluster_index(["a", ""])
    with pytest.raises(ValueError):
        cluster_index(["a", 3])


def test_wilson_interval_brackets_the_estimate_and_stays_in_range():
    block = wilson_interval(15, 22)
    assert block["estimate"] == pytest.approx(15 / 22)
    assert 0.0 <= block["lo"] < block["estimate"] < block["hi"] <= 1.0
    assert block["lo"] == pytest.approx(0.4732, abs=1e-3)


def test_wilson_interval_handles_the_degenerate_counts():
    assert wilson_interval(0, 10)["lo"] == 0.0
    assert wilson_interval(10, 10)["hi"] == 1.0


def test_wilson_interval_rejects_impossible_inputs():
    with pytest.raises(ValueError):
        wilson_interval(0, 0)
    with pytest.raises(ValueError):
        wilson_interval(11, 10)
    with pytest.raises(ValueError):
        wilson_interval(1, 10, confidence=1.5)


def test_normal_interval_rejects_a_negative_standard_error():
    with pytest.raises(ValueError):
        normal_interval(0.2, -0.1)


def test_normal_interval_is_wide_for_a_large_standard_error():
    narrow = normal_interval(0.2, 0.01)
    wide = normal_interval(0.2, 0.10)
    assert (wide["hi"] - wide["lo"]) > (narrow["hi"] - narrow["lo"])
    assert 0.2 == pytest.approx((wide["lo"] + wide["hi"]) / 2)


# ---------------------------------------------------------------- bootstrap
def test_bootstrap_reports_the_requested_metadata():
    positions = [i for i in range(40)]

    def metric(picked):
        return sum(positions[i] for i in picked) / len(picked) / 40.0

    block = bootstrap_interval(metric, [f"g{i % 8}" for i in positions], reps=200,
                               seed=7, unit="cluster")
    assert block["n_resamples_used"] == 200
    assert block["n_clusters"] == 8
    assert block["unit"] == "topic (cluster)"
    assert block["seed"] == 7
    lo, hi = block["estimate_interval"]
    assert lo <= hi


def test_clustered_interval_is_wider_than_item_interval_under_dependence():
    """Perfect within-cluster dependence must show up as a wider interval."""
    groups = [f"g{i // 5}" for i in range(40)]          # 8 clusters of 5
    values = [1.0 if int(g[1:]) % 2 == 0 else 0.0 for g in groups]

    def metric(picked):
        return sum(values[i] for i in picked) / len(picked)

    clustered = bootstrap_interval(metric, groups, reps=500, seed=11, unit="cluster")
    item = bootstrap_interval(metric, groups, reps=500, seed=11, unit="item")
    c_width = clustered["estimate_interval"][1] - clustered["estimate_interval"][0]
    i_width = item["estimate_interval"][1] - item["estimate_interval"][0]
    assert c_width > i_width


def test_bootstrap_skips_resamples_where_the_metric_is_undefined():
    calls = {"n": 0}

    def metric(picked):
        calls["n"] += 1
        return None if calls["n"] <= 5 else 0.5

    block = bootstrap_interval(metric, ["a", "b", "c"], reps=10, seed=1)
    assert block["n_resamples_used"] == 5


def test_bootstrap_raises_when_nothing_is_computable():
    def metric(picked):
        raise ValueError("cannot compute")

    with pytest.raises(ValueError, match="no usable resamples"):
        bootstrap_interval(metric, ["a", "b"], reps=5, seed=1)


def test_bootstrap_rejects_an_unknown_unit_and_zero_reps():
    with pytest.raises(ValueError):
        bootstrap_interval(lambda p: 1.0, ["a"], reps=5, unit="topic")
    with pytest.raises(ValueError):
        bootstrap_interval(lambda p: 1.0, ["a"], reps=0)


def test_bootstrap_is_deterministic_for_a_fixed_seed():
    def metric(picked):
        return len(picked) / 10.0

    groups = ["a", "b", "c", "d"]
    first = bootstrap_interval(metric, groups, reps=100, seed=3)
    second = bootstrap_interval(metric, groups, reps=100, seed=3)
    assert first["estimate_interval"] == second["estimate_interval"]
    assert first["bootstrap_mean"] == second["bootstrap_mean"]


# ------------------------------------------------------------------- paired
def test_paired_bootstrap_uses_the_same_resample_for_both_arms():
    """A constant offset must give a zero-width interval around that offset."""
    groups = [f"g{i // 4}" for i in range(32)]

    def metric(picked, arm):
        return 0.30 if arm == 0 else 0.10

    block = paired_bootstrap_interval(metric, groups, reps=100, seed=5)
    lo, hi = block["estimate_interval"]
    assert lo == pytest.approx(0.20)
    assert hi == pytest.approx(0.20)


def test_paired_bootstrap_detects_a_consistent_gap():
    groups = [f"g{i // 4}" for i in range(40)]
    values = [0.6 + 0.01 * i for i in range(40)]

    def metric(picked, arm):
        if arm == 0:
            return sum(values[i] for i in picked) / len(picked)
        return sum(values[i] for i in picked) / len(picked) - 0.15

    block = paired_bootstrap_interval(metric, groups, reps=300, seed=6)
    lo, hi = block["estimate_interval"]
    assert lo > 0.0 and block["excludes_zero"] is True


def test_paired_bootstrap_reports_no_gap_as_indeterminate():
    groups = [f"g{i // 4}" for i in range(40)]
    values = [0.5] * 40
    values[0], values[39] = 0.1, 0.9

    def metric(picked, arm):
        return sum(values[i] for i in picked) / len(picked)

    block = paired_bootstrap_interval(metric, groups, reps=200, seed=8)
    assert block["estimate_interval"] == [pytest.approx(0.0), pytest.approx(0.0)]
    assert block["excludes_zero"] is False


def test_paired_bootstrap_rejects_zero_reps():
    with pytest.raises(ValueError):
        paired_bootstrap_interval(lambda p, a: 1.0, ["a"], reps=0)


# ----------------------------------------------------------- gate stability
def test_gate_stability_marks_a_clear_fail_as_stable():
    block = summarize_gate_stability(
        {"ace": {"estimate_interval": [0.12, 0.46]}}, {"ace": 0.05})
    assert block["ace"]["status"] == "stable_fail"


def test_gate_stability_marks_a_clear_pass_as_stable():
    block = summarize_gate_stability(
        {"ace": {"estimate_interval": [0.01, 0.04]}}, {"ace": 0.05})
    assert block["ace"]["status"] == "stable_pass"


def test_gate_stability_calls_an_interval_over_the_threshold_indeterminate():
    block = summarize_gate_stability(
        {"ace": {"estimate_interval": [0.02, 0.09]}}, {"ace": 0.05})
    assert block["ace"]["status"] == "indeterminate"
    assert "straddles" in block["ace"]["note"]


def test_gate_stability_reports_a_missing_metric():
    block = summarize_gate_stability({}, {"ace": 0.05})
    assert block["ace"]["status"] == "not_computed"


def test_wilson_matches_a_hand_computed_value():
    # p=0.5, n=100 -> Wilson 95% is [0.4038, 0.5962] to four places.
    block = wilson_interval(50, 100)
    assert block["lo"] == pytest.approx(0.4038, abs=5e-4)
    assert block["hi"] == pytest.approx(0.5962, abs=5e-4)
    assert math.isclose(block["estimate"], 0.5)
