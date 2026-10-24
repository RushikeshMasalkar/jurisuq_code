"""Phase F (M9) tests: calibration maps, folds, metrics and G6 logic.

These tests fix the *behaviour* of the calibrator independently of any
experiment: monotonicity, the single-class refusal, deterministic folds,
finite-sample conformal arithmetic, and the verdict logic of Gate G6.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from jurisuq.calibration import (IsotonicMap, PlattMap, ace, attach_probabilities,
                                 brier, conformal_quantile_index, conformal_threshold,
                                 coverage_tolerance, cross_fitted_predictions, ece,
                                 empirical_coverage, evaluate_g6, fit_isotonic,
                                 fit_map, fit_platt, fit_strata, fold_assignment,
                                 group_key, grouped_folds, map_from_dict, predict,
                                 reliability_input, reliability_table, selective_risk)
from jurisuq.calibration.policy import DecisionPolicy


def _toy_records(n=60, *, correct_share=0.5, score_from="u_prov"):
    records = []
    n_correct = int(n * correct_share)
    for i in range(n):
        correct = 1 if i < n_correct else 0
        # correct items get low risk, incorrect items high risk, with a little noise
        risk = (0.15 + 0.02 * (i % 5)) if correct else (0.75 - 0.02 * (i % 5))
        records.append({
            "item_id": f"L1-topic{i % 4}-{i:03d}",
            "slice": "L1",
            "topic": f"topic{i % 4}",
            "uq_uncertainty": risk,
            "uq_components": {score_from: risk},
            "majority_correct": correct,
            "warrant_common_mode_flags": [],
            "warrant_as_of": "2024-06-30",
        })
    return records


# ----------------------------------------------------------------------
# maps
# ----------------------------------------------------------------------
def test_isotonic_recovers_a_monotone_step():
    x = [0.1] * 5 + [0.9] * 5
    y = [0] * 5 + [1] * 5
    mapping = fit_isotonic(x, y)
    assert mapping.predict(0.05) == pytest.approx(0.0)
    assert mapping.predict(0.95) == pytest.approx(1.0)
    assert mapping.predict(0.1) <= mapping.predict(0.9)


def test_isotonic_is_order_invariant():
    x = [0.2, 0.8, 0.5, 0.5, 0.1, 0.9]
    y = [0, 1, 0, 1, 0, 1]
    a = fit_isotonic(x, y)
    order = [5, 3, 1, 4, 0, 2]
    b = fit_isotonic([x[i] for i in order], [y[i] for i in order])
    assert a.x == b.x and a.y == b.y


def test_isotonic_is_monotone_between_knots():
    mapping = fit_isotonic([0.0, 0.25, 0.5, 0.75, 1.0], [0, 0, 1, 1, 1])
    values = [mapping.predict(p / 20) for p in range(21)]
    assert all(b >= a for a, b in zip(values, values[1:]))


def test_isotonic_refuses_single_class():
    with pytest.raises(ValueError, match="both correctness classes"):
        fit_isotonic([0.1, 0.2, 0.3], [1, 1, 1])


def test_isotonic_refuses_misaligned_inputs():
    with pytest.raises(ValueError):
        fit_isotonic([0.1, 0.2], [1])


def test_platt_is_monotone_and_bounded():
    mapping = fit_platt([0.05, 0.2, 0.4, 0.6, 0.8, 0.95], [0, 0, 1, 0, 1, 1])
    values = [mapping.predict(p / 10) for p in range(11)]
    assert all(0.0 <= v <= 1.0 for v in values)
    assert all(b >= a for a, b in zip(values, values[1:]))


def test_platt_refuses_negative_slope():
    with pytest.raises(ValueError, match="non-negative"):
        PlattMap(-1.0, 0.0)


def test_fit_map_rejects_unknown_method():
    with pytest.raises(ValueError, match="unknown calibration method"):
        fit_map([0.1, 0.9], [0, 1], method="spline")


def test_map_round_trip_preserves_predictions():
    mapping = fit_isotonic([0.1, 0.2, 0.8, 0.9], [0, 1, 0, 1])
    restored = map_from_dict(mapping.to_dict())
    for p in (0.0, 0.15, 0.5, 0.85, 1.0):
        assert restored.predict(p) == pytest.approx(mapping.predict(p))


def test_map_from_dict_rejects_non_monotone_knots():
    with pytest.raises(ValueError, match="non-decreasing"):
        IsotonicMap((0.1, 0.2), (0.8, 0.2))


def test_reliability_input_inverts_the_risk_score():
    assert reliability_input(0.25) == pytest.approx(0.75)
    with pytest.raises(ValueError):
        reliability_input(float("nan"))


def test_predict_on_a_stored_map_uses_one_minus_score():
    mapping = fit_isotonic([0.9] * 4 + [0.1] * 4, [1] * 4 + [0] * 4)
    assert predict(mapping, 0.05) > predict(mapping, 0.95)


# ----------------------------------------------------------------------
# folds
# ----------------------------------------------------------------------
def test_group_key_requires_slice_and_topic():
    with pytest.raises(ValueError):
        group_key({"item_id": "x", "topic": "theft"})
    with pytest.raises(ValueError):
        group_key({"item_id": "x", "slice": "L1"})
    assert group_key({"item_id": "x", "slice": "L1", "topic": "theft"}) == "L1|theft"


def test_fold_assignment_is_deterministic_and_total():
    groups = ["L1|theft", "L1|murder", "L7|theft", "L7|murder", "L1|cheating"]
    first, effective = fold_assignment(groups, k=3, seed="s")
    second, effective2 = fold_assignment(list(reversed(groups)), k=3, seed="s")
    assert first == second and effective == effective2 == 3
    assert set(first) == set(groups)


def test_fold_assignment_keeps_a_group_whole():
    records = _toy_records(24)
    folds = grouped_folds(records, k=4, seed="phaseF-test")
    seen: dict[str, int] = {}
    for record in records:
        group = group_key(record)
        fold = folds["item_fold"][record["item_id"]]
        seen.setdefault(group, fold)
        assert seen[group] == fold


def test_fewer_groups_than_folds_reduces_the_fold_count():
    records = [{"item_id": "a", "slice": "L1", "topic": "theft"},
               {"item_id": "b", "slice": "L1", "topic": "theft"}]
    folds = grouped_folds(records, k=5, seed="s")
    assert folds["effective_k"] == 1 and folds["requested_k"] == 5


def test_cross_fitting_leaves_every_row_out_of_its_training_set():
    records = _toy_records(60)
    labels = [r["majority_correct"] for r in records]
    scores = [r["uq_uncertainty"] for r in records]
    predictions, report = cross_fitted_predictions(records, labels, scores,
                                                   method="platt", k=5, seed="s")
    assert report["n_cross_fitted"] > 0
    assert all(p is None or 0.0 <= p <= 1.0 for p in predictions)
    fitted_folds = [f for f in report["folds"] if f["status"] == "fitted"]
    assert fitted_folds, "at least one fold should have both classes available"


# ----------------------------------------------------------------------
# metrics
# ----------------------------------------------------------------------
def test_ace_is_zero_for_a_perfect_forecast():
    p = [0.0] * 4 + [1.0] * 4
    y = [0] * 4 + [1] * 4
    assert ace(p, y, bins=5) == pytest.approx(0.0, abs=1e-12)


def test_ace_detects_a_bad_forecast():
    p = [0.9] * 10
    y = [0] * 10
    assert ace(p, y, bins=5) == pytest.approx(0.9)


def test_brier_and_ece_are_lower_for_better_forecasts():
    y = [0, 1, 0, 1, 1, 0]
    good = [0.1, 0.9, 0.2, 0.8, 0.7, 0.3]
    bad = [0.9, 0.1, 0.8, 0.2, 0.3, 0.7]
    assert brier(good, y) < brier(bad, y)
    assert ece(good, y) < ece(bad, y)


def test_reliability_table_bins_sum_to_the_population():
    p = [0.05, 0.55, 0.95, 0.35]
    y = [0, 1, 1, 0]
    rows = reliability_table(p, y, bins=5)
    assert sum(r["n"] for r in rows) == 4
    assert len(rows) == 5


def test_metrics_skip_undefined_probabilities_and_reject_nan():
    assert ace([None, 0.5], [0, 1], bins=5) is not None
    with pytest.raises(ValueError):
        ace([float("nan")], [1])
    with pytest.raises(ValueError):
        brier([0.5], [2])


def test_selective_risk_accepts_the_most_reliable_half():
    p = [0.9, 0.8, 0.2, 0.1]
    y = [1, 1, 0, 0]
    result = selective_risk(p, y, 0.5)
    assert result["n_accepted"] == 2
    assert result["risk"] == pytest.approx(0.0)


def test_selective_risk_rejects_bad_coverage():
    with pytest.raises(ValueError):
        selective_risk([0.5], [1], 0.0)


def test_harm_weighting_changes_the_risk_when_weights_differ():
    p = [0.9, 0.8, 0.2, 0.1]
    y = [0, 1, 0, 1]
    weighted = selective_risk(p, y, 0.5, weights=[5.0, 1.0, 1.0, 5.0])
    plain = selective_risk(p, y, 0.5)
    assert weighted["risk"] == pytest.approx(0.5)
    assert weighted["harm_weighted_risk"] == pytest.approx(5.0 / 6.0)
    assert plain["risk"] != weighted["harm_weighted_risk"]


# ----------------------------------------------------------------------
# conformal
# ----------------------------------------------------------------------
def test_conformal_index_uses_the_finite_sample_correction():
    # n=9, target 0.8 -> ceil(10*0.8) = 8
    assert conformal_quantile_index(9, target_coverage=0.8) == 8
    # n=9, target 0.95 -> ceil(10*0.95) = 10 > 9 -> undefined
    assert conformal_quantile_index(9, target_coverage=0.95) is None


def test_conformal_threshold_and_coverage():
    values = [i / 100 for i in range(1, 101)]
    result = conformal_threshold(values, target_coverage=0.9)
    assert result["status"] == "defined"
    coverage = empirical_coverage(values, result["threshold"])
    assert coverage["coverage"] >= 0.9


def test_conformal_threshold_reports_insufficient_data():
    result = conformal_threshold([0.5, 0.6], target_coverage=0.99)
    assert result["threshold"] is None
    assert result["status"] == "insufficient_calibration_pairs"
    assert empirical_coverage([0.5], None)["coverage"] is None


def test_coverage_tolerance_shrinks_with_n():
    assert coverage_tolerance(20, 0.8) > coverage_tolerance(200, 0.8)
    assert math.isclose(coverage_tolerance(0, 0.8), 1.0)


# ----------------------------------------------------------------------
# fitting per stratum
# ----------------------------------------------------------------------
def test_fit_strata_calibrates_only_strata_with_both_classes():
    records = _toy_records(60)
    dev = {r["item_id"] for r in records}
    fitted = fit_strata(records, dev, k=3)
    entry = fitted["strata"]["L1"]
    assert entry["status"] == "fitted"
    assert entry["method"] == "isotonic"
    assert entry["development_metrics"]["ace_5bin_cross_fitted"] is not None
    stored = entry["cross_fitted_p_reliable"]
    assert stored and all(0.0 <= v <= 1.0 for v in stored.values())
    sensitivity = entry["descriptive_method_sensitivity"]
    assert sensitivity["method"] == "platt"
    assert sensitivity["used_for_selection_or_gate"] is False


def test_fit_strata_marks_a_single_class_stratum_and_never_imputes():
    records = _toy_records(40, correct_share=1.0)
    fitted = fit_strata(records, {r["item_id"] for r in records}, k=3)
    entry = fitted["strata"]["L1"]
    assert entry["status"] == "single_class_in_development"
    assert entry["map"] is None
    probabilities = attach_probabilities(records, fitted)
    assert all(p["p_reliable"] is None for p in probabilities.values())
    assert {p["calibration_status"] for p in probabilities.values()} == {
        "undefined_stratum_not_calibrated"}


def test_attach_probabilities_is_monotone_in_the_risk_score():
    records = _toy_records(40)
    fitted = fit_strata(records, {r["item_id"] for r in records}, k=3)
    low = dict(records[0], item_id="probe-low", uq_uncertainty=0.01)
    high = dict(records[0], item_id="probe-high", uq_uncertainty=0.99)
    probabilities = attach_probabilities([low, high] + records, fitted)
    assert probabilities["probe-low"]["p_reliable"] >= probabilities["probe-high"]["p_reliable"]


# ----------------------------------------------------------------------
# G6 verdict logic
# ----------------------------------------------------------------------
def _statutes():
    return [{"act": "IPC", "section": "302", "offence_cluster": "topic0",
             "consequence_class": "custodial"},
            {"act": "BNS", "section": "103", "offence_cluster": "topic0",
             "consequence_class": "definition"}]


def _split(records, share=0.5):
    """Interleave the split so both correctness classes land on both sides."""
    ids = [r["item_id"] for r in records]
    development = {item for index, item in enumerate(ids) if index % 2 == 0}
    holdout = set(ids) - development
    assert share == 0.5
    return development, holdout


def test_g6_is_not_evaluable_when_the_holdout_has_one_class():
    records = _toy_records(40)
    dev, holdout = _split(records)
    fitted = fit_strata(records, dev, k=3)
    for record in records:
        if record["item_id"] in holdout:
            record["majority_correct"] = 0
    report = evaluate_g6(records, holdout, fitted, policy=DecisionPolicy(),
                         statute_rows=_statutes())
    assert report["per_stratum"]["L1"]["status"] == "not_evaluable_single_class_holdout"
    assert report["verdict"] == "NOT_EVALUABLE"
    assert report["conditions"]["harm_weighted_selective_risk_at_50pct_below_every_baseline"]["pass"] is None


def test_g6_verdict_is_not_met_when_calibration_is_poor():
    records = _toy_records(60)
    dev, holdout = _split(records)
    fitted = fit_strata(records, dev, k=3)
    # flatten the map onto an over-confident constant so the holdout is badly calibrated
    fitted["strata"]["L1"]["map"] = IsotonicMap((0.0, 1.0), (0.9, 0.9)).to_dict()
    report = evaluate_g6(records, holdout, fitted, policy=DecisionPolicy(),
                         statute_rows=_statutes())
    assert report["per_stratum"]["L1"]["metrics"]["ace_5bin"] > 0.05
    assert report["verdict"] == "NOT_MET"


def test_g6_interface_rule_failure_blocks_the_verdict():
    records = _toy_records(60)
    dev, holdout = _split(records)
    fitted = fit_strata(records, dev, k=3)
    report = evaluate_g6(records, holdout, fitted, policy=DecisionPolicy(),
                         statute_rows=_statutes(), interface_rule_ok=False)
    assert report["conditions"]["query_path_reads_no_labels"]["pass"] is False
    assert report["verdict"] == "NOT_MET"


def test_g6_report_states_the_harm_weight_caveat():
    records = _toy_records(40)
    dev, holdout = _split(records)
    fitted = fit_strata(records, dev, k=3)
    report = evaluate_g6(records, holdout, fitted, policy=DecisionPolicy(),
                         statute_rows=_statutes())
    assert report["harm_class_counts"]
    assert isinstance(report["harm_weight_variance_present"], bool)
    assert any("harm" in limitation for limitation in report["limitations"])


# ----------------------------------------------------------------------
# interface rule (label-blind query path)
# ----------------------------------------------------------------------
def test_query_path_scanner_flags_a_label_access(tmp_path):
    from jurisuq.calibration.evaluate import query_path_is_label_blind

    good = tmp_path / "good.py"
    good.write_text('"""Reads majority_correct never; just a docstring."""\n'
                    "# a comment mentioning majority_correct is fine\n"
                    'score = record.get("uq_uncertainty")\n'
                    'label_note = "no labels read"\n', encoding="utf-8")
    bad = tmp_path / "bad.py"
    bad.write_text('"""Scoring helper."""\n'
                   'value = record["majority_correct"]\n', encoding="utf-8")
    assert query_path_is_label_blind(good)["label_blind"] is True
    result = query_path_is_label_blind(bad)
    assert result["label_blind"] is False
    assert "majority_correct" in result["forbidden_fields_found"]


def test_the_shipped_policy_script_is_label_blind():
    from jurisuq.calibration.evaluate import query_path_is_label_blind

    result = query_path_is_label_blind(ROOT / "scripts" / "30_apply_policy.py")
    assert result["label_blind"] is True, result["forbidden_fields_found"]


def test_query_path_scanner_rejects_a_missing_file(tmp_path):
    from jurisuq.calibration.evaluate import query_path_is_label_blind

    with pytest.raises(FileNotFoundError):
        query_path_is_label_blind(tmp_path / "absent.py")
