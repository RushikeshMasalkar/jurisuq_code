import importlib.util
import json
import math
from pathlib import Path

import pytest

from jurisuq.uncertainty.estimator import estimate, fit_monotone_logistic, score_features
from jurisuq.uncertainty.features import extract_features
from jurisuq.uncertainty.split import split_name


VALIDATOR_PATH = Path(__file__).resolve().parents[1] / "scripts" / "27_validate_uncertainty.py"
VALIDATOR_SPEC = importlib.util.spec_from_file_location("validate_uncertainty", VALIDATOR_PATH)
VALIDATOR = importlib.util.module_from_spec(VALIDATOR_SPEC)
VALIDATOR_SPEC.loader.exec_module(VALIDATOR)


def sample_record():
    return {
        "item_id": "x",
        "n_samples": 10,
        "methods": {"prov_se": 1.660964047443681, "disc_se": 2.0},
        "warrant_warranted_agreement": 0.4,
        "warrant_common_mode_score": 0.3,
        "warrant_contradiction_mass": 0.2,
        "majority_correct": 0,
    }


def test_validator_uses_training_count_from_model_metadata():
    statement = VALIDATOR.training_limit_statement({"legal_head_training_n": 29})
    assert statement == (
        "The legal-aware head is trained on 29 legal-complete development "
        "records in this run; all scores are uncalibrated."
    )


def test_validator_does_not_invent_training_count_without_metadata():
    statement = VALIDATOR.training_limit_statement({})
    assert statement == (
        "The legal-aware head training count is unavailable in model metadata; "
        "all scores are uncalibrated."
    )


def test_extracts_phase_a_and_phase_d_components_without_recomputing_warrant():
    result = extract_features(sample_record())
    assert result["legal_complete"] is True
    assert result["components"]["u_prov"] == pytest.approx(0.5)
    assert result["components"]["u_text"] == pytest.approx(2.0 / math.log2(10))
    assert result["components"]["u_warrant"] == pytest.approx(0.6)
    assert result["components"]["u_cm"] == pytest.approx(0.3)
    assert result["components"]["u_contra"] == pytest.approx(0.2)


@pytest.mark.parametrize("field", [
    "warrant_warranted_agreement", "warrant_common_mode_score",
    "warrant_contradiction_mass",
])
def test_null_phase_d_component_triggers_sample_only_fallback_not_zero(field):
    record = sample_record()
    record[field] = None
    result = extract_features(record)
    assert result["legal_complete"] is False
    assert result["fallback_score"] == pytest.approx(0.5)
    key = {"warrant_warranted_agreement": "u_warrant",
           "warrant_common_mode_score": "u_cm",
           "warrant_contradiction_mass": "u_contra"}[field]
    assert result["components"][key] is None
    assert field in result["fallback_reason"]


def test_missing_warrant_schema_uses_sample_only_fallback():
    record = sample_record()
    for key in list(record):
        if key.startswith("warrant_"):
            del record[key]
    result = extract_features(record)
    assert result["legal_complete"] is False
    assert result["fallback_score"] == pytest.approx(0.5)
    assert result["components"]["u_warrant"] is None
    assert result["components"]["u_cm"] is None
    assert result["components"]["u_contra"] is None
    scored = estimate(result, model=None)
    assert scored["mode"] == "sample_only_fallback"
    assert scored["score"] == pytest.approx(0.5)
    assert "model head unavailable" in scored["fallback_reason"]


def test_invalid_nan_or_out_of_range_phase_d_fields_are_unresolved():
    record = sample_record()
    record["warrant_warranted_agreement"] = float("nan")
    record["warrant_common_mode_score"] = 1.01
    result = extract_features(record)
    assert result["legal_complete"] is False
    assert result["components"]["u_warrant"] is None
    assert result["components"]["u_cm"] is None
    assert result["fallback_score"] == pytest.approx(0.5)


def test_sample_only_score_is_undefined_if_sample_entropy_is_missing():
    record = sample_record()
    del record["methods"]["prov_se"]
    result = extract_features(record)
    assert result["fallback_score"] is None
    assert result["legal_complete"] is False
    scored = estimate(result, model=None)
    assert scored["mode"] == "unscorable"
    assert scored["score"] is None


def test_feature_extraction_never_reads_correctness_labels():
    class LabelGuard(dict):
        def get(self, key, default=None):
            if key in {"majority_correct", "sample_correct", "gold"}:
                raise AssertionError("label access in query-time feature path")
            return super().get(key, default)

    record = LabelGuard(sample_record())
    del record["majority_correct"]
    assert extract_features(record)["legal_complete"] is True


def test_projected_logistic_is_monotone_and_component_ablation_is_defined():
    rows = []
    labels = []
    for i in range(20):
        x = i / 19
        rows.append({"u_prov": x, "u_text": x, "u_warrant": x,
                     "u_cm": x, "u_contra": x})
        labels.append(int(i >= 10))
    model = fit_monotone_logistic(rows, labels, epochs=300)
    low = {k: 0.1 for k in rows[0]}
    high = {k: 0.8 for k in rows[0]}
    assert score_features(model, high) >= score_features(model, low)
    assert score_features(model, high, drop_components=("u_contra",)) <= 1.0
    assert all(w >= 0 for w in model.weights)


def test_split_is_deterministic_and_keeps_matched_pair_as_one_unit():
    assert split_name("offence-001", seed="fixed") == split_name("offence-001", seed="fixed")
    assert split_name("offence-001", seed="fixed") in {"test", "development"}


def test_shipped_phase_d_output_schema_and_coverage():
    root = Path(__file__).resolve().parents[1]
    path = root / "runs" / "phaseA-laptop-v2-rejudged+ctx+warrant" / "items.jsonl"
    if not path.is_file():
        pytest.skip("the shipped Phase D run is not present in this checkout")
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(records) == 200
    assert all("warrant_warranted_agreement" in row for row in records)
    assert all("warrant_common_mode_score" in row for row in records)
    assert all("warrant_contradiction_mass" in row for row in records)
    assert sum(extract_features(row)["legal_complete"] for row in records) == 32
