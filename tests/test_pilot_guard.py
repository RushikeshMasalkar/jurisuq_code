"""Tests for the Phase G pilot safeguards.

This is the first code path in the project that spends money, so the guards are
tested as hard as the metrics: the cost ceiling, the approval hash, drift
detection, and the rule that the pilot can never overwrite a frozen run.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from jurisuq import pilot
from jurisuq.pilot import (
    COST_CAP_USD,
    FROZEN_DATASET_SHA256,
    SPARSE_CLASS_BELOW,
    build_plan,
    classify_slice,
    enforce_cost_cap,
    estimate_cost,
    ensure_fresh_run_dir,
    estimate_plan_cost,
    g7_from_pilot,
    outcome_rules,
    plan_digest,
    redact_secret,
    require_approval,
    select_items,
    selection_summary,
    verify_frozen_inputs,
    verify_no_drift,
)

ROOT = Path(__file__).resolve().parents[1]
RATES = {"input_per_mtok": 0.30, "output_per_mtok": 1.20}


def _items(n_per_slice=30):
    items = []
    for slice_name in ("L1", "L7"):
        for i in range(n_per_slice):
            items.append({"item_id": f"{slice_name}-{i:03d}", "slice": slice_name,
                          "topic": f"topic{i % 5}"})
    return items


def _plan(**overrides):
    base = dict(
        provider="openai", base_url="https://api.deepseek.com/v1",
        model="deepseek-flash", temperature=1.0, top_p=1.0, max_tokens=220,
        n_samples=10, seed=20261024, prompt_version="p2-structured",
        judge="provision", judge_scope="representatives",
        selection=selection_summary(select_items(_items())),
        pricing={"rates_used": RATES}, rates=RATES,
        prompt_tokens_per_request=200, run_id="phaseG-pilot-test",
        dataset_sha256=dict(FROZEN_DATASET_SHA256),
    )
    base.update(overrides)
    return build_plan(**base)


# ----------------------------------------------------------------------
# cost arithmetic and the cap
# ----------------------------------------------------------------------
def test_cost_uses_published_per_million_rates():
    cost = estimate_cost(prompt_tokens=1_000_000, completion_tokens=1_000_000, rates=RATES)
    assert cost["input_cost_usd"] == pytest.approx(0.30)
    assert cost["output_cost_usd"] == pytest.approx(1.20)
    assert cost["total_cost_usd"] == pytest.approx(1.50)


def test_plan_cost_scales_with_requests():
    estimate = estimate_plan_cost(240, 200, 220, RATES)
    assert estimate["n_requests"] == 240
    assert estimate["prompt_tokens"] == 240 * 200
    assert estimate["completion_tokens"] == 240 * 220


def test_twenty_four_item_pilot_is_far_below_the_cap():
    estimate = estimate_plan_cost(240, 200, 220, RATES)
    assert estimate["total_cost_usd"] < COST_CAP_USD


def test_cap_refuses_an_expensive_plan():
    # a $2/$10 model at this pilot size lands above the cap
    expensive = {"input_per_mtok": 2.0, "output_per_mtok": 10.0}
    estimate = estimate_plan_cost(240, 200, 220, expensive)
    assert estimate["total_cost_usd"] > COST_CAP_USD
    with pytest.raises(SystemExit, match="exceeds"):
        enforce_cost_cap(estimate)


def test_cap_accepts_a_plan_inside_it_and_reports_headroom():
    verdict = enforce_cost_cap(estimate_plan_cost(240, 200, 220, RATES))
    assert verdict["within_cap"] is True
    assert verdict["headroom_usd"] == pytest.approx(COST_CAP_USD - verdict["estimated_max_cost_usd"])


def test_cost_rejects_missing_or_negative_rates():
    with pytest.raises(ValueError):
        estimate_cost(100, 100, {"input_per_mtok": 1.0})
    with pytest.raises(ValueError):
        estimate_cost(100, 100, {"input_per_mtok": -1.0, "output_per_mtok": 1.0})


def test_plan_estimate_is_documented_as_an_upper_bound():
    estimate = estimate_plan_cost(240, 200, 220, RATES)
    assert "upper bound" in estimate["basis"]


# ----------------------------------------------------------------------
# the plan and its hash
# ----------------------------------------------------------------------
def test_plan_records_everything_needed_to_review_it():
    plan = _plan()
    assert plan["provider"] and plan["model"] and plan["base_url"]
    assert plan["request_configuration"]["n_samples"] == 10
    assert plan["n_requests"] == plan["selection"]["n_items"] * 10
    assert plan["judge"]["deterministic"] is True
    assert plan["plan_sha256"]


def test_plan_hash_changes_when_the_model_changes():
    a = _plan()
    b = _plan(model="deepseek-v4-pro")
    assert a["plan_sha256"] != b["plan_sha256"]


def test_plan_hash_changes_when_a_request_parameter_changes():
    a = _plan()
    b = _plan(max_tokens=400)
    assert a["plan_sha256"] != b["plan_sha256"]


def test_plan_hash_changes_when_the_items_change():
    a = _plan()
    b = _plan(selection=selection_summary(select_items(_items(), seed=999)))
    assert a["plan_sha256"] != b["plan_sha256"]


def test_plan_hash_is_stable_for_the_same_plan():
    assert _plan()["plan_sha256"] == _plan()["plan_sha256"]


def test_plan_does_not_contain_a_secret():
    plan = _plan()
    blob = json.dumps(plan)
    assert "sk-" not in blob
    assert "api_key" not in blob.lower().replace("api_key_env", "")


# ----------------------------------------------------------------------
# approval gate
# ----------------------------------------------------------------------
def test_execution_refuses_without_an_approval_hash():
    with pytest.raises(SystemExit, match="without approval"):
        require_approval(_plan(), None)


def test_execution_refuses_a_mismatched_hash():
    with pytest.raises(SystemExit, match="does not match"):
        require_approval(_plan(), "0" * 64)


def test_execution_accepts_the_matching_hash():
    plan = _plan()
    require_approval(plan, plan["plan_sha256"])      # must not raise


# ----------------------------------------------------------------------
# drift detection: the approved plan is the only runnable plan
# ----------------------------------------------------------------------
def test_drift_in_model_is_refused():
    approved = _plan()
    drifted = _plan(model="deepseek-v4-pro")
    with pytest.raises(SystemExit, match="model differs"):
        verify_no_drift(drifted, approved)


def test_drift_in_base_url_is_refused():
    approved = _plan()
    drifted = _plan(base_url="https://api.openai.com/v1")
    with pytest.raises(SystemExit, match="base_url differs"):
        verify_no_drift(drifted, approved)


def test_drift_in_request_configuration_is_refused():
    approved = _plan()
    drifted = _plan(temperature=0.2)
    with pytest.raises(SystemExit, match="request configuration differs"):
        verify_no_drift(drifted, approved)


def test_drift_in_item_list_is_refused():
    approved = _plan()
    drifted = _plan(selection=selection_summary(select_items(_items(), seed=7)))
    with pytest.raises(SystemExit, match="selected items differ"):
        verify_no_drift(drifted, approved)


def test_an_unchanged_plan_passes_drift_check():
    approved = _plan()
    verify_no_drift(_plan(), approved)


# ----------------------------------------------------------------------
# item selection
# ----------------------------------------------------------------------
def test_selection_draws_twelve_from_each_slice():
    chosen = select_items(_items())
    summary = selection_summary(chosen)
    assert summary["by_slice"] == {"L1": 12, "L7": 12}
    assert summary["n_items"] == 24


def test_selection_is_deterministic_for_a_seed():
    first = [i["item_id"] for i in select_items(_items(), seed=123)]
    second = [i["item_id"] for i in select_items(_items(), seed=123)]
    assert first == second


def test_selection_changes_with_the_seed():
    first = [i["item_id"] for i in select_items(_items(), seed=1)]
    second = [i["item_id"] for i in select_items(_items(), seed=2)]
    assert first != second


def test_selection_spreads_across_topics():
    summary = selection_summary(select_items(_items(), per_slice=10))
    assert len(summary["topics_by_slice"]["L1"]) > 1


def test_selection_refuses_a_slice_that_is_too_small():
    with pytest.raises(ValueError, match="cannot draw"):
        select_items(_items(n_per_slice=3), per_slice=12)


def test_selection_never_mixes_slices():
    chosen = select_items(_items())
    for slice_name in ("L1", "L7"):
        ids = [i["item_id"] for i in chosen if i["slice"] == slice_name]
        assert all(i.startswith(slice_name) for i in ids)


# ----------------------------------------------------------------------
# pre-registered outcome rules
# ----------------------------------------------------------------------
def test_rules_are_marked_as_registered_before_generation():
    assert outcome_rules()["registered_before_generation"] is True


def test_zero_correct_leaves_g7_not_met():
    verdict = classify_slice({"correct": 0, "incorrect": 12, "unresolved": 0})
    assert verdict["state"] == "zero_correct"
    assert verdict["ranking_defined"] is False
    assert "undefined" in verdict["interpretation"]


def test_all_correct_leaves_g7_not_met():
    verdict = classify_slice({"correct": 12, "incorrect": 0, "unresolved": 0})
    assert verdict["state"] == "all_correct"
    assert verdict["ranking_defined"] is False


def test_both_classes_do_not_automatically_pass_g7():
    verdict = g7_from_pilot({"L7": classify_slice({"correct": 5, "incorrect": 7,
                                                   "unresolved": 0})})
    assert verdict["status"] == "PROVISIONAL_MET"
    assert verdict["final"] is False
    assert "cannot settle a gate" in verdict["note"]


def test_a_sparse_class_is_flagged_and_does_not_define_a_ranking():
    verdict = classify_slice({"correct": 2, "incorrect": 10, "unresolved": 0})
    assert verdict["state"] == "sparse_class"
    assert verdict["sparse_class"] is True
    assert verdict["ranking_defined"] is False
    assert str(SPARSE_CLASS_BELOW) in verdict["interpretation"]


def test_g7_is_not_met_when_the_target_slice_is_sparse():
    verdict = g7_from_pilot({"L7": classify_slice({"correct": 1, "incorrect": 11,
                                                   "unresolved": 0})})
    assert verdict["status"] == "NOT_MET"


def test_g7_is_not_met_when_l7_was_not_evaluated():
    verdict = g7_from_pilot({})
    assert verdict["status"] == "NOT_MET"
    assert verdict["final"] is False


def test_unresolved_items_are_counted_separately():
    verdict = classify_slice({"correct": 0, "incorrect": 0, "unresolved": 12})
    assert verdict["state"] == "no_resolved_items"
    assert verdict["ranking_defined"] is False


def test_gates_g5_and_g6_are_unchanged_by_a_pilot():
    verdict = g7_from_pilot({"L7": classify_slice({"correct": 6, "incorrect": 6,
                                                   "unresolved": 0})})
    assert verdict["unchanged"] == {"G5": "NOT_EVALUABLE", "G6": "NOT_MET"}


def test_pilot_never_claims_pooling():
    plan = _plan()
    assert plan["invariants"]["pools_slices"] is False
    assert "pooled AUROC never presented" in outcome_rules()["slices"]


def test_pilot_never_changes_gates_or_thresholds():
    invariants = _plan()["invariants"]
    assert invariants["changes_gate_constants"] is False
    assert invariants["changes_thresholds"] is False
    assert invariants["modifies_frozen_runs"] is False
    assert invariants["modifies_frozen_datasets"] is False


# ----------------------------------------------------------------------
# frozen inputs and secret handling
# ----------------------------------------------------------------------
def test_frozen_inputs_are_verified_against_recorded_digests():
    digests = verify_frozen_inputs(ROOT)
    assert all(entry["match"] for entry in digests.values())


@pytest.mark.parametrize("relative", sorted(FROZEN_DATASET_SHA256))
def test_frozen_inputs_survive_a_crlf_checkout(relative, tmp_path):
    """A Windows CRLF checkout must not read as a tampered dataset.

    ``core.autocrlf=true`` rewrites line endings on checkout without changing
    content, so the digest is computed over content with CRLF read as LF.
    """
    source = (ROOT / relative).read_bytes().replace(b"\r\n", b"\n")
    (tmp_path / "data").mkdir()
    for other in FROZEN_DATASET_SHA256:          # a complete copy to verify against
        (tmp_path / other).write_bytes((ROOT / other).read_bytes().replace(b"\r\n", b"\n"))
    crlf = source.replace(b"\n", b"\r\n")
    (tmp_path / relative).write_bytes(crlf)
    assert (tmp_path / relative).read_bytes() != source, "fixture is not actually CRLF"
    digests = verify_frozen_inputs(tmp_path)
    assert digests[relative]["match"], f"{relative} failed only because of line endings"
    assert digests[relative]["actual"] == FROZEN_DATASET_SHA256[relative]


@pytest.mark.parametrize("relative", sorted(FROZEN_DATASET_SHA256))
def test_frozen_inputs_still_detect_a_real_edit(relative, tmp_path):
    """Line-ending tolerance must not make a genuine change invisible."""
    (tmp_path / "data").mkdir()
    for other in FROZEN_DATASET_SHA256:          # a complete, untouched copy
        (tmp_path / other).write_bytes((ROOT / other).read_bytes().replace(b"\r\n", b"\n"))
    source = (tmp_path / relative).read_bytes()
    edited = source + b'{"injected": true}\n' if relative.endswith(".jsonl") \
        else source.replace(b"}", b', "injected": true}', 1)
    assert edited != source, "fixture edit did not apply"
    (tmp_path / relative).write_bytes(edited)
    with pytest.raises(SystemExit, match="differs from its recorded digest"):
        verify_frozen_inputs(tmp_path)


def test_the_guard_refuses_a_tampered_dataset(tmp_path):
    (tmp_path / "data").mkdir()
    for relative in FROZEN_DATASET_SHA256:
        (tmp_path / relative).write_text("tampered\n")
    with pytest.raises(SystemExit, match="differs from its recorded digest"):
        verify_frozen_inputs(tmp_path)


def test_secrets_are_redacted_from_log_text():
    assert redact_secret("failed with sk-abc123", "sk-abc123") == "failed with <redacted>"
    assert redact_secret("no secret here", "sk-abc123") == "no secret here"


def test_the_config_never_stores_an_api_key():
    config = json.loads((ROOT / "configs" / "phase_g_pilot.json").read_text())
    assert "api_key_env" in config["generator"]
    assert "api_key" not in config["generator"]
    assert config["generator"]["api_key_env"].isupper()


# ----------------------------------------------------------------------
# the smoke check
# ----------------------------------------------------------------------
def _smoke():
    return pilot.build_smoke_plan(_plan())


def test_smoke_plan_is_two_requests_one_per_slice():
    smoke = _smoke()
    assert smoke["n_requests"] == 2
    assert len(smoke["item_ids"]) == 2
    slices = sorted(item_id.split("-", 1)[0] for item_id in smoke["item_ids"])
    assert slices == ["L1", "L7"]


def test_smoke_plan_inherits_the_approved_configuration():
    plan = _plan()
    smoke = pilot.build_smoke_plan(plan)
    assert smoke["model"] == plan["model"]
    assert smoke["base_url"] == plan["base_url"]
    assert smoke["request_configuration"] == plan["request_configuration"]
    assert smoke["parent_plan_sha256"] == plan["plan_sha256"]


def test_smoke_plan_costs_almost_nothing():
    smoke = _smoke()
    assert smoke["cost_estimate"]["total_cost_usd"] < 0.01
    enforce_cost_cap(smoke["cost_estimate"])       # must not raise


def test_smoke_plan_has_its_own_hash_distinct_from_the_pilot():
    plan = _plan()
    smoke = pilot.build_smoke_plan(plan)
    assert smoke["plan_sha256"] != plan["plan_sha256"]


def test_smoke_plan_changes_if_the_model_changes():
    a = pilot.build_smoke_plan(_plan())
    b = pilot.build_smoke_plan(_plan(model="deepseek-v4-pro"))
    assert a["plan_sha256"] != b["plan_sha256"]


def test_smoke_requires_its_own_approval():
    smoke = _smoke()
    with pytest.raises(SystemExit, match="without approval"):
        require_approval(smoke, None, mode="--smoke")
    with pytest.raises(SystemExit, match="does not match"):
        require_approval(smoke, _plan()["plan_sha256"], mode="--smoke")
    require_approval(smoke, smoke["plan_sha256"], mode="--smoke")


def test_smoke_plan_states_what_it_is_for():
    assert "thinking" in _smoke()["purpose"]
    assert "logprobs" in _smoke()["purpose"]


# ----------------------------------------------------------------------
# run-directory protection
# ----------------------------------------------------------------------
def test_fresh_run_dir_is_created_when_absent(tmp_path):
    target = tmp_path / "phaseG-pilot-v1"
    assert ensure_fresh_run_dir(target) == target


def test_empty_run_dir_is_accepted(tmp_path):
    target = tmp_path / "phaseG-pilot-v1"
    target.mkdir()
    ensure_fresh_run_dir(target)          # must not raise


def test_a_populated_run_dir_is_refused(tmp_path):
    target = tmp_path / "phaseG-pilot-v1-smoke"
    target.mkdir()
    (target / "smoke_report.json").write_text("{}")
    with pytest.raises(SystemExit, match="never overwritten"):
        ensure_fresh_run_dir(target)


def test_refusal_does_not_delete_the_existing_run(tmp_path):
    target = tmp_path / "run"
    target.mkdir()
    kept = target / "items.jsonl"
    kept.write_text("precious")
    with pytest.raises(SystemExit):
        ensure_fresh_run_dir(target)
    assert kept.read_text() == "precious", "an existing run must survive the refusal"
