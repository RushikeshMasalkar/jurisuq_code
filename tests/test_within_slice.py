"""Tests for follow-up experiment 2: slice-restricted refit versus the pooled fit."""
from __future__ import annotations

import math

import pytest

from jurisuq.calibration.within_slice import (
    compare_within_slice,
    features_for,
    fit_within_slice,
    score_arm,
)
from jurisuq.uncertainty.estimator import fit_monotone_logistic
from jurisuq.uncertainty.features import feature_names


TOPICS = [f"topic-{i:02d}" for i in range(10)]


def _record(item_id: str, *, topic: str, slice_name: str, correct: int,
            u_prov: float = 0.5, u_text: float = 0.5, legal: bool = True,
            n_samples: int = 3) -> dict:
    """A synthetic Phase A/D record with explicit, controllable components."""
    record = {
        "item_id": item_id,
        "topic": topic,
        "slice": slice_name,
        "n_samples": n_samples,
        "majority_correct": correct,
        "methods": {
            # extract_features normalizes prov_se by log2(n_samples), so this
            # reproduces u_prov exactly.
            "prov_se": u_prov * math.log2(n_samples),
            "disc_se": u_text * math.log2(n_samples),
        },
    }
    if legal:
        record.update({
            "warrant_warranted_agreement": 1.0 - 0.5,
            "warrant_common_mode_score": 0.25,
            "warrant_contradiction_mass": 0.25,
        })
    return record


def _corpus(n_dev: int = 60, n_hold: int = 20, *, slice_name: str = "L1") -> list[dict]:
    """Development + holdout records for one slice, with a learnable signal.

    The score is driven by ``u_prov`` so that a model restricted to this slice
    can recover it; a pooled fit that spends mass on the legal factors (which
    are constant here) ranks worse.
    """
    records = []
    for i in range(n_dev):
        u_prov = 0.05 + 0.9 * (i % 10) / 10.0
        correct = 1 if u_prov < 0.5 else 0
        records.append(_record(f"dev-{i:03d}", topic=TOPICS[i % 10], slice_name=slice_name,
                               correct=correct, u_prov=u_prov))
    for i in range(n_hold):
        u_prov = 0.05 + 0.9 * (i % 10) / 10.0
        correct = 1 if u_prov < 0.5 else 0
        records.append(_record(f"hold-{i:03d}", topic=TOPICS[i % 10], slice_name=slice_name,
                               correct=correct, u_prov=u_prov))
    return records


def _ids(records, prefix):
    return {r["item_id"] for r in records if r["item_id"].startswith(prefix)}


def _pooled_model(records, development_ids) -> dict:
    """A model fitted on all development rows, as Phase E ships it."""
    features = features_for(records)
    rows, labels = [], []
    for record in records:
        if record["item_id"] not in development_ids:
            continue
        rows.append(features[record["item_id"]]["components"])
        labels.append(1 - int(record["majority_correct"]))
    model = fit_monotone_logistic(rows, labels)
    return {
        "feature_names": model.names,
        "weights": model.weights,
        "intercept": model.intercept,
        "fit_note": model.fit_note,
        "training_n": len(labels),
        "training_positive": sum(labels),
        "training_negative": len(labels) - sum(labels),
    }


def test_features_for_maps_every_record_and_rejects_a_missing_id():
    records = _corpus(n_dev=4, n_hold=2)
    features = features_for(records)
    assert set(features) == {r["item_id"] for r in records}
    with pytest.raises(ValueError):
        features_for([{"topic": "t", "slice": "L1"}])


def test_features_for_rejects_an_unknown_provision_variant():
    with pytest.raises(ValueError):
        features_for(_corpus(n_dev=2, n_hold=1), provision_variant="typedish")


def test_score_arm_skips_items_without_complete_legal_features():
    records = _corpus(n_dev=60, n_hold=4)
    records.append(_record("hold-fallback", topic=TOPICS[0], slice_name="L1",
                           correct=1, legal=False))
    features = features_for(records)
    dev_ids = _ids(records, "dev-")
    model = fit_monotone_logistic(
        [features[i]["components"] for i in sorted(dev_ids)],
        [1 - int(r["majority_correct"]) for r in records if r["item_id"] in dev_ids])
    scores = score_arm(model, features, sorted(_ids(records, "hold-")))
    assert "hold-fallback" not in scores
    assert len(scores) == 4
    assert all(0.0 <= v <= 1.0 for v in scores.values())


def test_fit_within_slice_uses_only_the_requested_slice():
    records = _corpus(n_dev=60, n_hold=10)
    # Add L7 development rows: a within-L1 fit must ignore them.
    for i in range(30):
        records.append(_record(f"dev7-{i:03d}", topic=TOPICS[i % 10], slice_name="L7",
                               correct=1, u_prov=0.9))
    features = features_for(records)
    development = _ids(records, "dev-") | _ids(records, "dev7-")
    fitted = fit_within_slice(records, features, development, slice_name="L1")
    assert fitted["training_n"] == 60
    assert set(fitted["training_ids"]) == _ids(records, "dev-")


def test_fit_within_slice_refuses_insufficient_development_rows():
    records = _corpus(n_dev=6, n_hold=4)
    features = features_for(records)
    with pytest.raises(ValueError, match="insufficient development records"):
        fit_within_slice(records, features, _ids(records, "dev-"), slice_name="L1")


def test_fit_within_slice_refuses_a_single_correctness_class():
    records = _corpus(n_dev=60, n_hold=2)
    for record in records:
        record["majority_correct"] = 1
    features = features_for(records)
    with pytest.raises(ValueError, match="one correctness class"):
        fit_within_slice(records, features, _ids(records, "dev-"), slice_name="L1")


def test_fit_within_slice_refuses_a_non_binary_label():
    records = _corpus(n_dev=60, n_hold=2)
    for record in records:
        if record["item_id"] == "dev-000":
            record["majority_correct"] = None
    features = features_for(records)
    with pytest.raises(ValueError, match="lacks binary majority_correct"):
        fit_within_slice(records, features, _ids(records, "dev-"), slice_name="L1")


def test_compare_scores_both_arms_on_the_same_items_and_reports_fallbacks():
    records = _corpus(n_dev=60, n_hold=20)
    records.append(_record("hold-fallback", topic=TOPICS[0], slice_name="L1",
                           correct=1, legal=False))
    development = _ids(records, "dev-")
    report = compare_within_slice(records, development, _ids(records, "hold-"),
                                  _pooled_model(records, development))
    ranking = report["ranking_on_identical_holdout_items"]
    assert ranking["pooled"]["n"] == ranking["within_slice"]["n"] == 20
    assert report["holdout_excluded_ids"] == ["hold-fallback"]
    assert report["n_holdout_candidates"] == 21
    assert report["n_holdout_eligible"] == 20
    assert report["within_slice_training"]["training_n"] == 60
    assert report["n_phase_e_development_items"] == 60


def test_compare_reports_the_stored_pooled_weights_under_the_right_names():
    records = _corpus(n_dev=60, n_hold=20)
    development = _ids(records, "dev-")
    report = compare_within_slice(records, development, _ids(records, "hold-"),
                                  _pooled_model(records, development))
    weights = report["pooled_training"]["feature_weights"]
    assert set(weights) == set(feature_names())
    assert any(abs(v) > 0 for v in weights.values())
    assert set(report["within_slice_training"]["feature_weights"]) == set(feature_names())


def test_compare_reports_ace_brier_and_log_loss_for_both_arms():
    records = _corpus(n_dev=60, n_hold=20)
    development = _ids(records, "dev-")
    report = compare_within_slice(records, development, _ids(records, "hold-"),
                                  _pooled_model(records, development))
    for arm in ("pooled", "within_slice"):
        block = report["downstream_calibration"][arm]
        for key in ("holdout_ace_5bin", "holdout_brier", "holdout_log_loss",
                    "development_cross_fitted_ace_5bin"):
            assert block[key] is not None, (arm, key)
        assert 0.0 <= block["holdout_brier"] <= 1.0
        assert block["n_holdout"] == 20


def test_compare_requires_enough_topics_for_the_folds():
    records = _corpus(n_dev=60, n_hold=20)
    for index, record in enumerate(records):
        record["topic"] = "only-topic" if index % 2 == 0 else "other-topic"
    development = _ids(records, "dev-")
    with pytest.raises(ValueError, match="fewer topics than folds"):
        compare_within_slice(records, development, _ids(records, "hold-"),
                             _pooled_model(records, development))
