"""Phase F (M10) tests: the answer/verify/abstain decision layer."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from jurisuq.calibration.policy import (ACTIONS, DecisionPolicy, action_census,
                                        harm_class_from_store)
from jurisuq.calibration.metrics import HARM_WEIGHTS, harm_weight


def test_thresholds_are_harm_dependent():
    policy = DecisionPolicy()
    low = policy.thresholds("definition")
    high = policy.thresholds("custodial")
    assert high["p_answer"] > low["p_answer"]
    assert high["p_verify"] >= low["p_verify"]


def test_policy_answers_a_confident_question():
    policy = DecisionPolicy()
    decision = policy.decide(0.99, "custodial")
    assert decision["action"] == "answer"
    assert decision["trigger"] == "reliability_above_answer_threshold"
    assert "answered without verification" in decision["reason"]


def test_policy_verifies_in_the_middle_band():
    policy = DecisionPolicy()
    # custodial h=5: answer threshold 0.97, abstain threshold 0.93
    decision = policy.decide(0.95, "custodial")
    assert decision["action"] == "verify"


def test_policy_abstains_below_the_verify_threshold():
    policy = DecisionPolicy()
    decision = policy.decide(0.05, "custodial")
    assert decision["action"] == "abstain"
    assert "not answered" in decision["reason"]


def test_a_phase_d_flag_downgrades_an_answer_to_verify():
    policy = DecisionPolicy()
    plain = policy.decide(0.99, "custodial")
    flagged = policy.decide(0.99, "custodial", flags=("stale_provision",))
    assert plain["action"] == "answer"
    assert flagged["action"] == "verify"
    assert flagged["trigger"] == "phase_d_flag_outranks_calibrated_reliability"
    assert "not in force" in flagged["reason"]


def test_undefined_reliability_uses_the_declared_action_and_says_why():
    policy = DecisionPolicy()
    decision = policy.decide(None, "custodial")
    assert decision["action"] == "verify"
    assert decision["trigger"] == "undefined_reliability"
    assert "undefined" in decision["reason"]
    strict = DecisionPolicy(on_undefined="abstain").decide(None, "custodial")
    assert strict["action"] == "abstain"


def test_policy_rejects_an_out_of_range_probability():
    policy = DecisionPolicy()
    with pytest.raises(ValueError):
        policy.decide(1.2, "custodial")
    with pytest.raises(ValueError):
        policy.decide(float("nan"), "custodial")


def test_policy_rejects_inconsistent_costs():
    with pytest.raises(ValueError, match="verify_cost must be below abstain_cost"):
        DecisionPolicy(verify_cost=0.5, abstain_cost=0.2)
    with pytest.raises(ValueError):
        DecisionPolicy(verify_cost=0.0)


def test_policy_rejects_an_unknown_undefined_action():
    with pytest.raises(ValueError):
        DecisionPolicy(on_undefined="ignore")


def test_reason_names_the_as_of_date_and_harm_class():
    decision = DecisionPolicy().decide(0.99, "custodial", as_of="2024-07-01")
    assert "2024-07-01" in decision["reason"]
    assert "custodial" in decision["reason"]


def test_policy_round_trip():
    policy = DecisionPolicy(verify_cost=0.2, abstain_cost=0.4, on_undefined="abstain")
    restored = DecisionPolicy.from_dict(policy.to_dict())
    assert restored.verify_cost == 0.2 and restored.abstain_cost == 0.4
    assert restored.on_undefined == "abstain"
    assert restored.decide(0.5, "both")["action"] == policy.decide(0.5, "both")["action"]


def test_harm_class_from_store_uses_the_offence_cluster():
    rows = [{"offence_cluster": "murder", "consequence_class": "custodial"},
            {"offence_cluster": "theft", "consequence_class": "definition"},
            {"offence_cluster": "theft", "consequence_class": "both"}]
    assert harm_class_from_store("murder", rows) == "custodial"
    assert harm_class_from_store("theft", rows, rule="max") == "both"
    assert harm_class_from_store("theft", rows, rule="modal") in ("both", "definition")
    assert harm_class_from_store("unknown_topic", rows) == "unknown"
    assert harm_class_from_store(None, rows) == "unknown"
    with pytest.raises(ValueError):
        harm_class_from_store("theft", rows, rule="mean")


def test_unknown_harm_is_weighted_conservatively():
    assert harm_weight(None) == HARM_WEIGHTS["unknown"]
    assert HARM_WEIGHTS["unknown"] >= max(v for k, v in HARM_WEIGHTS.items() if k != "unknown")
    with pytest.raises(ValueError):
        harm_weight("trivial")


def test_procedural_harm_thresholds_are_the_loosest_but_abstention_stays_reachable():
    policy = DecisionPolicy()
    thresholds = policy.thresholds("procedural")  # h = 1.0
    assert thresholds["p_answer"] == pytest.approx(0.85)
    assert thresholds["p_verify"] == pytest.approx(0.65)
    assert thresholds["abstain_reachable"] is True  # h > abstain_cost


def test_thresholds_are_degenerate_when_harm_is_below_abstain_cost():
    policy = DecisionPolicy(harm_weights=(("trivial", 0.2), ("unknown", 5.0)))
    thresholds = policy.thresholds("trivial")
    assert thresholds["abstain_reachable"] is False
    assert thresholds["p_verify"] == pytest.approx(0.0)


def test_policy_requires_a_configured_weight_for_every_class_it_sees():
    policy = DecisionPolicy(harm_weights=(("custodial", 5.0), ("unknown", 5.0)))
    with pytest.raises(ValueError, match="no harm weight configured"):
        policy.thresholds("definition")
    assert policy.weight(None) == 5.0


def test_action_census_counts_every_action():
    policy = DecisionPolicy()
    decisions = [policy.decide(0.99, "custodial"), policy.decide(0.95, "custodial"),
                 policy.decide(0.01, "custodial"), policy.decide(None, "custodial")]
    census = action_census(decisions)
    assert set(census["actions"]) == set(ACTIONS)
    assert sum(census["actions"].values()) == 4
    assert census["triggers"]


def test_action_census_rejects_an_unknown_action():
    with pytest.raises(ValueError):
        action_census([{"action": "escalate"}])
