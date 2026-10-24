"""Tests for follow-up experiment 3: calibration-method comparison and the frozen rule."""
from __future__ import annotations

import pytest

from jurisuq.calibration.method_selection import (
    CANDIDATE_METHODS,
    choose_method,
    compare_calibration_methods,
    compare_per_stratum,
)


def _development(n: int = 78) -> tuple[dict, dict]:
    """Development scores + labels with a narrow, learnable reliability range."""
    scores, labels = {}, {}
    for i in range(n):
        item_id = f"dev-{i:03d}"
        narrow = 0.05 + 0.0795 * (i % 10) / 10.0  # spawns < the 0.15 threshold
        scores[item_id] = 1.0 - (0.85 + narrow)
        labels[item_id] = 1 if (i % 10) < 4 else 0
    return scores, labels


def _holdout(n: int = 22) -> tuple[dict, dict]:
    scores, labels = {}, {}
    for i in range(n):
        item_id = f"hold-{i:03d}"
        scores[item_id] = 1.0 - (0.85 + 0.0795 * (i % 10) / 10.0)
        labels[item_id] = 1 if (i % 10) < 3 else 0
    return scores, labels


RULE = {"n_threshold": 100, "range_threshold": 0.15,
        "small_sample_method": "platt", "default_method": "isotonic"}


# --------------------------------------------------------------------- rule
def test_rule_fires_on_a_narrow_range_even_with_many_rows():
    # 120 rows is above the size threshold, so only the narrow range can fire.
    decision = choose_method([0.85 + 0.05 * i / 119 for i in range(120)], **RULE)
    assert decision["chosen"] == "platt"
    assert decision["n_development"] == 120
    assert any("reliability range" in reason for reason in decision["triggered_by"])
    assert not any("n_development" in reason for reason in decision["triggered_by"])


def test_rule_fires_on_a_small_sample_even_with_a_wide_range():
    decision = choose_method([0.0, 0.25, 0.5, 0.75, 1.0], **RULE)
    assert decision["chosen"] == "platt"
    assert any("n_development" in reason for reason in decision["triggered_by"])


def test_rule_keeps_isotonic_when_both_conditions_are_satisfied():
    values = [i / 99 for i in range(100)]
    decision = choose_method(values, **RULE)
    assert decision["chosen"] == "isotonic"
    assert decision["reliability_range"] > 0.15
    assert decision["triggered_by"] == ["neither condition: default method applies"]
    assert decision["rule_uses_holdout_labels"] is False


def test_rule_is_inclusive_at_the_thresholds():
    # exactly n_threshold rows and exactly range_threshold are "not triggering"
    values = [0.0 + 0.15 * i / 99 for i in range(100)]
    assert max(values) - min(values) == pytest.approx(0.15)
    assert choose_method(values, **RULE)["chosen"] == "isotonic"


def test_rule_rejects_empty_or_non_finite_input():
    with pytest.raises(ValueError):
        choose_method([], **RULE)
    with pytest.raises(ValueError):
        choose_method([0.1, float("nan")], **RULE)


def test_rule_rejects_impossible_thresholds():
    with pytest.raises(ValueError):
        choose_method([0.1, 0.9], n_threshold=0, range_threshold=0.15)
    with pytest.raises(ValueError):
        choose_method([0.1, 0.9], n_threshold=100, range_threshold=-1.0)


# --------------------------------------------------------------- comparison
def test_every_candidate_is_reported_and_the_rule_picks_the_shipped_one():
    dev_scores, dev_labels = _development()
    hold_scores, hold_labels = _holdout()
    report = compare_calibration_methods(dev_scores, dev_labels, hold_scores, hold_labels,
                                         rule=RULE, folds=5, seed="phaseE-v1|L1")
    assert set(report["candidates"]) == set(CANDIDATE_METHODS)
    assert report["chosen_by_rule"] == "platt"
    assert report["selection_used_holdout_labels"] is False
    for method, block in report["candidates"].items():
        assert block["holdout"]["n"] == 22, method
        assert block["development"]["n"] == 78, method
        assert 0.0 <= block["holdout"]["brier"] <= 1.0, method
        assert block["holdout"]["log_loss"] is not None, method


def test_the_report_does_not_promote_a_holdout_winner_over_the_rule():
    """The chosen method must follow the rule even when another candidate wins."""
    dev_scores, dev_labels = _development(200)
    # Widen the range so the rule selects isotonic...
    for index, item_id in enumerate(dev_scores):
        dev_scores[item_id] = index / 200.0
        dev_labels[item_id] = 1 if index < 80 else 0
    hold_scores, hold_labels = {}, {}
    for index in range(22):
        hold_scores[f"hold-{index:03d}"] = index / 22.0
        hold_labels[f"hold-{index:03d}"] = 1 if index < 8 else 0
    report = compare_calibration_methods(dev_scores, dev_labels, hold_scores, hold_labels,
                                         rule=RULE, folds=5, seed="phaseE-v1|L1")
    assert report["rule"]["reliability_range"] > RULE["range_threshold"]
    assert report["chosen_by_rule"] == "isotonic"
    # Whatever the ranking says, the shipped choice is untouched by it.
    best = report["holdout_ace_ranking_best_first"][0]
    assert report["chosen_by_rule"] == "isotonic", best


def test_constant_candidate_equals_the_development_base_rate():
    dev_scores, dev_labels = _development()
    hold_scores, hold_labels = _holdout()
    report = compare_calibration_methods(dev_scores, dev_labels, hold_scores, hold_labels,
                                         rule=RULE, folds=5, seed="phaseE-v1|L1")
    base = report["development_base_rate_correct"]
    assert report["candidates"]["constant"]["parameters"]["base_rate"] == pytest.approx(base)
    assert report["candidates"]["constant"]["holdout_saturated_at_one"] == 0


def test_isotonic_saturation_is_reported_not_hidden():
    """Isotonic clamps above its top knot, so items can be pinned at 1.0."""
    dev_scores, dev_labels = _development()
    hold_scores, hold_labels = _holdout()
    report = compare_calibration_methods(dev_scores, dev_labels, hold_scores, hold_labels,
                                         rule=RULE, folds=5, seed="phaseE-v1|L1")
    isotonic = report["candidates"]["isotonic"]
    if isotonic["holdout_saturated_at_one"]:
        assert isotonic["predicts_a_single_value_above_the_top_knot"] in (True, False)
    assert "holdout_saturated_at_one" in isotonic


def test_comparison_requires_two_development_classes():
    dev_scores, dev_labels = _development(20)
    for item_id in dev_labels:
        dev_labels[item_id] = 1
    with pytest.raises(ValueError, match="single class"):
        compare_calibration_methods(dev_scores, dev_labels, {}, {}, rule=RULE, folds=2,
                                    seed="s")


def test_comparison_requires_development_data():
    with pytest.raises(ValueError, match="no development items"):
        compare_calibration_methods({}, {}, {"h": 0.5}, {"h": 1}, rule=RULE, folds=2, seed="s")


# ------------------------------------------------------------- per stratum
def _records(n_dev: int = 78, n_hold: int = 22) -> tuple[list[dict], set[str], set[str]]:
    records, dev, hold = [], set(), set()
    for i in range(n_dev):
        item_id = f"L1-topic-{i:03d}"
        records.append({"item_id": item_id, "slice": "L1", "topic": f"topic-{i % 10}",
                        "uq_uncertainty": 1.0 - (0.85 + 0.005 * (i % 10)),
                        "majority_correct": 1 if (i % 10) < 4 else 0})
        dev.add(item_id)
    for i in range(n_hold):
        item_id = f"L1-topic-h{i:03d}"
        records.append({"item_id": item_id, "slice": "L1", "topic": f"topic-{i % 10}",
                        "uq_uncertainty": 1.0 - (0.85 + 0.005 * (i % 10)),
                        "majority_correct": 1 if (i % 10) < 3 else 0})
        hold.add(item_id)
    return records, dev, hold


def test_per_stratum_reports_each_stratum_and_a_pooled_reference():
    records, dev, hold = _records()
    report = compare_per_stratum(records, dev, hold, rule=RULE, folds=5, seed="phaseE-v1")
    assert report["stratum_key"] == "slice"
    assert "L1" in report["strata"]
    assert report["strata"]["L1"]["chosen_by_rule"] == "platt"
    assert report["combined_pooled"]["note"].startswith("pooled across strata for reference only")


def test_per_stratum_records_a_single_class_stratum_instead_of_fitting_it():
    records, dev, hold = _records()
    for record in records:
        if record["item_id"] in dev:
            record["majority_correct"] = 0          # every development item wrong
    report = compare_per_stratum(records, dev, hold, rule=RULE, folds=5, seed="phaseE-v1")
    assert "error" in report["strata"]["L1"]
    assert "single class" in report["strata"]["L1"]["error"]
    assert report["strata"]["L1"]["n_development"] == 78


def test_per_stratum_skips_records_without_a_score_or_label():
    records, dev, hold = _records()
    records.append({"item_id": "L1-broken-1", "slice": "L1", "topic": "topic-0",
                    "uq_uncertainty": None, "majority_correct": 1})
    records.append({"item_id": "L1-broken-2", "slice": "L1", "topic": "topic-0",
                    "uq_uncertainty": 0.5, "majority_correct": None})
    dev.update({"L1-broken-1", "L1-broken-2"})
    report = compare_per_stratum(records, dev, hold, rule=RULE, folds=5, seed="phaseE-v1")
    assert report["strata"]["L1"]["n_development"] == 78
