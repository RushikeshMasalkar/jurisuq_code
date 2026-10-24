"""Tests for the Phase G §21.2 evaluation matrix (jurisuq/evaluation/matrix.py).

The matrix exists to satisfy the guide's reporting rules, so most of these tests
pin a rule rather than a formula: slices never pool, a single-class population
has no ranking metric, an undefined value always carries a reason, and NaN never
reaches the report.
"""
from __future__ import annotations

import json
import math

import pytest

from jurisuq.evaluation.matrix import (
    CONSTANT_SCORE,
    DEGENERATE,
    HARM_ABSENT,
    LOGPROBS_ABSENT,
    METHOD_UNAVAILABLE,
    METHODS,
    NO_SCORED_ITEMS,
    OUTSIDE_UNIT_INTERVAL,
    SHORT_REASONS,
    SINGLE_CLASS,
    build_matrix,
    confident_wrong,
    gate_g7,
    judge_coverage,
    method_score,
    pooled_reference,
    score_cell,
)


# ----------------------------------------------------------------------
# fixtures
# ----------------------------------------------------------------------
def _record(item_id, *, slice_name="L1", correct, agreement=0.5, disc_se=2.0,
            se=1.5, selfcheck=0.3, p_true=None, prov_agreement=0.4,
            uq=None, p_reliable=None, harm_class=None, samples=None):
    record = {
        "item_id": item_id,
        "slice": slice_name,
        "majority_correct": correct,
        "methods": {"agreement": agreement, "disc_se": disc_se, "se": se,
                    "selfcheck": selfcheck, "p_true": p_true,
                    "prov_agreement": prov_agreement, "prov_se": disc_se},
        "uq_uncertainty": uq,
        "p_reliable": p_reliable,
    }
    if harm_class is not None:
        record["harm_class"] = harm_class
    if samples is not None:
        record["sample_verdict_labels"] = samples
    return record


def _two_class_slice(slice_name="L1", n=10, *, uq=True):
    """Alternating correct/incorrect with a signal the score can rank."""
    records = []
    for i in range(n):
        correct = 1 if i % 2 == 0 else 0
        # correct items get low uncertainty, incorrect get high
        # keep every score inside [0, 1] so the fixture exercises the ordinary
        # path; out-of-interval handling has its own test
        score = 0.05 + 0.04 * i if correct else 0.55 + 0.04 * i
        records.append(_record(
            f"{slice_name}-{i}", slice_name=slice_name, correct=correct,
            agreement=score, prov_agreement=score,
            uq=(score if uq else None), p_reliable=(1 - score if uq else None)))
    return records


# ----------------------------------------------------------------------
# the method axis must match the guide
# ----------------------------------------------------------------------
def test_all_nine_guide_methods_are_declared():
    keys = [spec.key for spec in METHODS]
    assert len(keys) == 9, "§21.2 lists nine uncertainty methods"
    assert keys == [
        "exact_agreement", "lexical_similarity", "discrete_semantic_entropy",
        "standard_semantic_entropy", "selfcheck", "p_true",
        "provision_agreement", "legal_aware", "legal_aware_uncalibrated",
    ]


def test_lexical_similarity_is_declared_unimplemented_with_an_explanation():
    spec = next(s for s in METHODS if s.key == "lexical_similarity")
    assert spec.implemented is False
    assert "entailment backend" in spec.note


def test_method_scores_are_all_oriented_larger_means_more_uncertain():
    record = _record("x", correct=1, agreement=0.8, disc_se=1.0, uq=0.3,
                     p_reliable=0.7)
    assert method_score(record, "exact_agreement") == pytest.approx(0.8)
    assert method_score(record, "legal_aware_uncalibrated") == pytest.approx(0.3)
    # calibrated form is 1 - p_reliable
    assert method_score(record, "legal_aware") == pytest.approx(0.3)


def test_method_score_rejects_an_unknown_key():
    with pytest.raises(ValueError):
        method_score(_record("x", correct=1), "not_a_method")


# ----------------------------------------------------------------------
# orientation of AUROC (§21.2)
# ----------------------------------------------------------------------
def test_auroc_rewards_a_score_that_is_high_when_the_answer_is_wrong():
    records = []
    for i in range(10):
        correct = 1 if i < 5 else 0
        records.append(_record(f"i{i}", correct=correct,
                               agreement=0.1 if correct else 0.9))
    cell = score_cell(records, "exact_agreement")
    assert cell["metrics"]["auroc"] == pytest.approx(1.0)


def test_auroc_punishes_an_inverted_score():
    records = []
    for i in range(10):
        correct = 1 if i < 5 else 0
        records.append(_record(f"i{i}", correct=correct,
                               agreement=0.9 if correct else 0.1))
    cell = score_cell(records, "exact_agreement")
    assert cell["metrics"]["auroc"] == pytest.approx(0.0)


# ----------------------------------------------------------------------
# §21.1: a single-class slice has no ranking metric
# ----------------------------------------------------------------------
def test_single_class_slice_reports_undefined_not_a_degenerate_value():
    records = [_record(f"L7-{i}", slice_name="L7", correct=0, agreement=0.1 * i)
               for i in range(10)]
    cell = score_cell(records, "exact_agreement")
    assert cell["metrics"]["auroc"] is None
    assert cell["undefined"]["auroc"] == SINGLE_CLASS
    for name in ("auprc", "normalized_aurc", "selective_risk_at_fixed_coverage"):
        assert cell["metrics"][name] is None
        assert cell["undefined"][name] == SINGLE_CLASS


def test_all_correct_slice_is_equally_undefined():
    records = [_record(f"i{i}", correct=1, agreement=0.1 * i) for i in range(10)]
    cell = score_cell(records, "exact_agreement")
    assert cell["metrics"]["auroc"] is None
    assert cell["undefined"]["auroc"] == SINGLE_CLASS


# ----------------------------------------------------------------------
# degenerate scores
# ----------------------------------------------------------------------
def test_constant_score_reports_no_selective_risk_only_a_base_error_rate():
    records = [_record(f"i{i}", correct=1 if i % 2 else 0, agreement=0.5)
               for i in range(10)]
    cell = score_cell(records, "exact_agreement")
    assert cell["undefined"]["auroc"] == CONSTANT_SCORE
    assert cell["metrics"]["auroc"] is None
    # which half a constant score "selects" is a tie-break artefact, so the
    # selective risk must not be reported; the base error rate can be
    assert cell["metrics"]["selective_risk_at_fixed_coverage"] is None
    assert cell["undefined"]["selective_risk_at_fixed_coverage"] == CONSTANT_SCORE
    assert cell["metrics"]["base_error_rate"] == pytest.approx(0.5)


# ----------------------------------------------------------------------
# calibration metrics need a probability
# ----------------------------------------------------------------------
def test_calibration_metrics_are_undefined_for_a_score_in_bits():
    records = _two_class_slice()
    cell = score_cell(records, "discrete_semantic_entropy")   # entropy in bits
    for name in ("ace_5bin", "ece_10bin", "brier"):
        assert cell["metrics"][name] is None
        assert cell["undefined"][name] == OUTSIDE_UNIT_INTERVAL


def test_calibration_metrics_are_computed_for_a_probability_score():
    records = _two_class_slice()
    cell = score_cell(records, "legal_aware")
    for name in ("ace_5bin", "ece_10bin", "brier"):
        assert cell["metrics"][name] is not None, name
        assert cell["undefined"].get(name) is None
    assert cell["metrics"]["reliability_5bin"]


# ----------------------------------------------------------------------
# unavailable methods and fields
# ----------------------------------------------------------------------
def test_unimplemented_method_yields_a_row_of_undefined_values():
    records = _two_class_slice()
    cell = score_cell(records, "lexical_similarity")
    assert cell["undefined"]["all"] == METHOD_UNAVAILABLE
    assert cell["metrics"]["auroc"] is None


def test_absent_logprobs_produce_the_logprobs_reason():
    records = _two_class_slice()          # p_true is None throughout
    cell = score_cell(records, "p_true")
    assert cell["undefined"]["all"] == LOGPROBS_ABSENT
    assert cell["n_scored"] == 0


def test_legal_aware_without_a_calibrated_probability_reports_no_scores():
    records = _two_class_slice(uq=False)
    cell = score_cell(records, "legal_aware")
    assert cell["undefined"]["all"] == NO_SCORED_ITEMS


# ----------------------------------------------------------------------
# judge coverage is a column, not a footnote (§21.1)
# ----------------------------------------------------------------------
def test_judge_coverage_counts_resolved_items_and_samples():
    records = [
        _record("a", correct=1, samples=["gold", "gold"]),
        _record("b", correct=None, samples=["unresolved", "gold"]),
    ]
    coverage = judge_coverage(records)
    assert coverage["n_items"] == 2
    assert coverage["n_items_resolved"] == 1
    assert coverage["item_coverage"] == pytest.approx(0.5)
    assert coverage["n_samples"] == 4
    assert coverage["n_samples_resolved"] == 3
    assert coverage["sample_coverage"] == pytest.approx(0.75)


def test_unresolved_items_are_excluded_from_scoring_but_keep_coverage():
    records = _two_class_slice()
    records.append(_record("unres", correct=None, agreement=0.99))
    cell = score_cell(records, "exact_agreement")
    assert cell["n_items"] == 11
    assert cell["n_scored"] == 10
    assert cell["judge_coverage"]["item_coverage"] == pytest.approx(10 / 11)


def test_every_cell_carries_the_coverage_column():
    matrix = build_matrix(_two_class_slice())
    for block in matrix["blocks"].values():
        if not block["present"]:
            continue
        assert block["judge_coverage"] is not None
        for cell in block["cells"].values():
            assert "judge_coverage" in cell


# ----------------------------------------------------------------------
# confident wrong (§21.2 definition)
# ----------------------------------------------------------------------
def test_confident_wrong_uses_the_lowest_quartile():
    # 8 items: quartile threshold at the 25th percentile
    uncertainty = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7]
    correct = [0, 0, 1, 1, 1, 1, 1, 1]
    block = confident_wrong(uncertainty, correct)
    assert block["n"] == 8
    assert block["threshold"] == pytest.approx(0.175)
    assert block["n_confident"] == 2          # 0.0 and 0.1
    assert block["n_confident_wrong"] == 2
    assert block["rate"] == pytest.approx(1.0)


def test_confident_wrong_is_undefined_for_a_tiny_population():
    block = confident_wrong([0.1, 0.2], [0, 1])
    assert block["n_confident"] is None
    assert block["undefined"] == "population_too_small_for_a_quartile"


def test_confident_wrong_of_a_perfect_score_is_zero():
    uncertainty = [0.9, 0.8, 0.7, 0.1]
    correct = [0, 0, 0, 1]
    block = confident_wrong(uncertainty, correct)
    assert block["n_confident_wrong"] == 0
    assert block["rate"] == 0.0


# ----------------------------------------------------------------------
# harm weighting
# ----------------------------------------------------------------------
def test_harm_weighted_risk_is_undefined_without_a_harm_class():
    records = _two_class_slice()
    cell = score_cell(records, "legal_aware")
    assert cell["metrics"]["harm_weighted_risk_at_fixed_coverage"] is None
    assert cell["undefined"]["harm_weighted_risk_at_fixed_coverage"] == HARM_ABSENT


def test_harm_weighted_risk_is_computed_and_flags_constant_weights():
    records = _two_class_slice()
    for record in records:
        record["harm_class"] = "custodial"
    cell = score_cell(records, "legal_aware")
    assert cell["metrics"]["harm_weighted_risk_at_fixed_coverage"] is not None
    assert cell["metrics"]["harm_weight_variation_present"] is False
    assert cell["harm_classes"] == ["custodial"]


def test_harm_weight_variation_is_detected():
    records = _two_class_slice()
    for index, record in enumerate(records):
        record["harm_class"] = "custodial" if index % 2 else "procedural"
    cell = score_cell(records, "legal_aware")
    assert cell["metrics"]["harm_weight_variation_present"] is True


# ----------------------------------------------------------------------
# no-pooling safeguard (§21.1)
# ----------------------------------------------------------------------
def test_build_matrix_never_pools():
    matrix = build_matrix(_two_class_slice("L1") + _two_class_slice("L7"))
    assert matrix["pooled"] is None
    assert "pooled" in matrix["pooling_note"].lower()
    assert set(matrix["blocks"]) == {"L1", "L7"}


def test_pooled_reference_refuses_when_a_slice_is_missing():
    with pytest.raises(ValueError, match="absent from the data"):
        pooled_reference(_two_class_slice("L1"))


def test_pooled_reference_is_tagged_unreportable_alone():
    records = _two_class_slice("L1") + _two_class_slice("L7")
    pooled = pooled_reference(records)
    assert pooled["pooled_for_reference_only"] is True
    assert pooled["may_not_be_reported_alone"] is True
    assert "average away" in pooled["reason"]


def test_a_slice_absent_from_the_data_is_marked_absent():
    matrix = build_matrix(_two_class_slice("L1"), slices=("L1", "L7"))
    assert matrix["blocks"]["L7"]["present"] is False
    assert matrix["slices_absent"] == ["L7"]


# ----------------------------------------------------------------------
# input validation
# ----------------------------------------------------------------------
def test_build_matrix_rejects_empty_input():
    with pytest.raises(ValueError):
        build_matrix([])


def test_build_matrix_rejects_an_unknown_method():
    with pytest.raises(ValueError, match="unknown uncertainty method"):
        build_matrix(_two_class_slice(), methods=["nope"])


def test_coverage_must_be_in_the_unit_interval():
    with pytest.raises(ValueError):
        build_matrix(_two_class_slice(), coverage=0.0)
    with pytest.raises(ValueError):
        build_matrix(_two_class_slice(), coverage=1.5)


# ----------------------------------------------------------------------
# G7 (guide §12)
# ----------------------------------------------------------------------
def test_g7_is_not_met_when_the_target_slice_has_one_class():
    matrix = build_matrix(_two_class_slice("L1")
                          + [_record(f"L7-{i}", slice_name="L7", correct=0,
                                     agreement=0.1 * i, uq=0.1 * i,
                                     p_reliable=0.5)
                             for i in range(10)])
    status = gate_g7(matrix)
    assert status["status"] == "NOT_MET"
    assert status["conditions"]["both_classes_on_every_evaluated_slice"]["met"] is False
    assert "L7" in status["reason"]
    assert "fail condition" in status["reason"]


def test_g7_is_met_when_both_slices_have_both_classes_and_a_comparison():
    matrix = build_matrix(_two_class_slice("L1") + _two_class_slice("L7"))
    status = gate_g7(matrix)
    assert status["conditions"]["both_classes_on_every_evaluated_slice"]["met"] is True
    assert status["conditions"]["headline_comparison_computable"]["met"] is True
    assert status["status"] == "MET"


def test_g7_reports_not_evaluable_without_any_slice():
    status = gate_g7({"blocks": {}})
    assert status["status"] == "NOT_EVALUABLE"


def test_g7_headline_comparison_needs_both_a_legal_aware_and_a_baseline_method():
    # both classes present, but no legal-aware score at all
    matrix = build_matrix(_two_class_slice("L1", uq=False)
                          + _two_class_slice("L7", uq=False))
    status = gate_g7(matrix)
    assert status["conditions"]["both_classes_on_every_evaluated_slice"]["met"] is True
    assert status["conditions"]["headline_comparison_computable"]["met"] is False
    assert status["status"] == "NOT_MET"


def test_g7_records_the_guide_text_and_the_fail_condition():
    status = gate_g7(build_matrix(_two_class_slice()))
    assert "both correctness classes" in status["guide_text"]
    assert "ranking is defined" in status["guide_fail_condition"]


# ----------------------------------------------------------------------
# NaN must never reach the report
# ----------------------------------------------------------------------
def test_matrix_is_json_serialisable_without_nan():
    matrix = build_matrix(_two_class_slice("L1")
                          + [_record(f"L7-{i}", slice_name="L7", correct=0,
                                     agreement=0.1 * i, disc_se=0.1 * i)
                             for i in range(10)])
    text = json.dumps(matrix, allow_nan=False)     # raises on NaN/inf
    assert "NaN" not in text
    assert "Infinity" not in text


def test_no_metric_value_is_nan():
    matrix = build_matrix(_two_class_slice())
    for block in matrix["blocks"].values():
        for cell in block["cells"].values():
            for name, value in cell["metrics"].items():
                if isinstance(value, float):
                    assert math.isfinite(value), name


def test_every_scored_cell_reports_the_base_error_rate():
    matrix = build_matrix(_two_class_slice())
    scored = 0
    for block in matrix["blocks"].values():
        for cell in block["cells"].values():
            if cell["n_scored"]:
                assert cell["metrics"]["base_error_rate"] == pytest.approx(0.5)
                scored += 1
    assert scored > 0


def test_every_short_reason_maps_a_known_code():
    assert SHORT_REASONS[SINGLE_CLASS] == "single_class"
    assert SHORT_REASONS[DEGENERATE] == "degenerate"
    for short in SHORT_REASONS.values():
        # the printed table reserves a fixed-width column for "undef:<reason>"
        assert 0 < len("undef:" + short) <= 20, "short reason must fit the table column"
