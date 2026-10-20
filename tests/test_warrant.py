"""Phase D unit tests: the common-mode failure detector and E4/G4.

Everything here runs on the standard library + pytest: no torch,
no transformers, no network.  The detector is tested against a
real statute store built from ``context.table.build_rows`` so the
validity windows are the shipped ones, not a toy table.
"""
from __future__ import annotations

import math

import pytest

from jurisuq.context import StatuteStore, build_rows, load_links
from jurisuq.context.statute import load_statutes
from jurisuq.warrant import (FLAG_CONTRADICTION, FLAG_FOREIGN,
                               FLAG_STALE, FLAG_UNRESOLVABLE,
                               EraPolicy, WarrantDetector,
                               WarrantResult, WarrantThresholds,
                               compose)
from jurisuq.warrant.validate import (binary_confusion,
                                         collision_population,
                                         factor_ablation, gate_g4,
                                         group_report,
                                         separation_auroc, validate)

ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]
CROSSWALK = ROOT / "data" / "relations" / "crosswalk_v1.jsonl"


@pytest.fixture(scope="module")
def store() -> StatuteStore:
    rows = build_rows()
    return StatuteStore(rows)


@pytest.fixture(scope="module")
def links() -> dict:
    return load_links(CROSSWALK) if CROSSWALK.exists() else {}


@pytest.fixture(scope="module")
def detector(store, links) -> WarrantDetector:
    return WarrantDetector(store, links)


def _rec(keys, slice_name="L7", prov_all_same=1):
    return {"item_id": "t", "slice": slice_name,
            "asserted_keys": list(keys),
            "prov_all_same": prov_all_same,
            "majority_correct": 0}


# ---------------------------------------------------------------------------
# the era-aware as-of date -- the crux of the design
# ---------------------------------------------------------------------------

def test_era_policy_maps_slices_to_the_dates_they_ask_about():
    era = EraPolicy()
    assert era.as_of_for("L7") == "2024-07-01"   # current law
    assert era.as_of_for("L1") == "2024-06-30"   # pre-transition


def test_era_policy_fixed_mode_pins_one_date():
    era = EraPolicy(mode="fixed", fixed_date="2026-10-01")
    assert era.as_of_for("L7") == "2026-10-01"
    assert era.as_of_for("L1") == "2026-10-01"


def test_stale_law_fires_on_L7_but_not_on_the_matched_L1(
        detector):
    """The same wrong provision must be stale in one era only.

    IPC 302 is repealed on 1 July 2024.  An L7 item asks about
    the law today, so asserting it is stale (the detector fires);
    the matched L1 item asks about the law *before* the
    transition, when IPC 302 was in force, so the detector must
    stay silent.  This is the matched design doing its job.
    """
    res_l7 = detector.detect(_rec(["IPC 302"] * 10, "L7"))
    res_l1 = detector.detect(_rec(["IPC 302"] * 10, "L1"))
    assert res_l7.temporal_validity == 0.0
    assert res_l7.common_mode_score == pytest.approx(1.0)
    assert FLAG_STALE in res_l7.flags
    assert res_l1.temporal_validity == 1.0
    assert res_l1.common_mode_score == pytest.approx(0.0)
    assert res_l1.flags == []


# ---------------------------------------------------------------------------
# the four factors and their composition
# ---------------------------------------------------------------------------

def test_observed_agreement_is_the_modal_share(detector):
    res = detector.detect(_rec(["IPC 302"] * 7 + ["IPC 304"] * 3))
    assert res.observed_agreement == pytest.approx(0.7)
    assert res.modal_key == "IPC 302"
    assert res.modal_size == 7


def test_temporal_validity_is_a_share_over_the_modal_cluster(
        detector):
    # Under typed clustering a cluster can mix provisions, so T
    # is a genuine share.  The modal cluster (label 0, six
    # members) asserts three stale IPC 302 and three current
    # BNS 103 -> T = 0.5 on the L7 (current-law) era date.
    keys = (["IPC 302"] * 3 + ["BNS 103"] * 3 +
            ["IPC 304"] * 4)
    labels = [0] * 6 + [1] * 4
    rec = _rec(keys, "L7", prov_all_same=0)
    res = detector.detect(rec, cluster_labels=labels)
    assert res.cluster_representation == "typed"
    assert res.observed_agreement == pytest.approx(0.6)
    assert res.temporal_validity == pytest.approx(0.5)


def test_temporal_validity_none_when_store_cannot_resolve(detector):
    res = detector.detect(_rec(["IPC 99999"] * 10, "L7"))
    assert res.temporal_validity is None
    assert FLAG_UNRESOLVABLE in res.flags
    # an unresolvable factor is never silently turned into zero
    assert res.warranted_agreement is None
    assert res.common_mode_score is None


def test_jurisdiction_fit_flags_a_foreign_assertion(detector):
    res = detector.detect(_rec(["FOREIGN:XYZ"] * 10, "L7"))
    assert res.jurisdiction_fit == 0.0
    assert FLAG_FOREIGN in res.flags


def test_jurisdiction_fit_is_one_for_indian_codes(detector):
    # a repealed code is still Indian law: J is about the legal
    # order, not about whether the provision is in force
    res = detector.detect(_rec(["IPC 302"] * 10, "L7"))
    assert res.jurisdiction_fit == 1.0
    assert FLAG_FOREIGN not in res.flags


def test_contradiction_mass_is_exactly_zero_on_a_single_cluster(
        detector):
    res = detector.detect(_rec(["IPC 302"] * 10, "L7"))
    assert res.contradiction_mass == 0.0
    assert res.contradiction_source == "exact_single_cluster"


def test_contradiction_mass_is_absent_without_a_relation_signal(
        detector):
    res = detector.detect(_rec(["IPC 302"] * 6 + ["IPC 304"] * 4,
                               "L7", prov_all_same=0))
    assert res.contradiction_mass is None
    assert res.contradiction_source == "no_relation_signal"
    # W and CM are then undefined, not zero
    assert res.warranted_agreement is None
    assert res.common_mode_score is None


def test_contradiction_mass_from_a_relation_matrix(detector):
    # A learned relation matrix makes K computable: the
    # non-modal cluster (label 1, four members) stands in a
    # CONTRADICTORY relation to the modal cluster, so its
    # mass (0.4) is the contradiction mass.
    keys = (["BNS 103"] * 6 + ["IPC 302"] * 4)
    labels = [0] * 6 + [1] * 4
    n = len(keys)
    relation = [["SAME_PROVISION"] * n for _ in range(n)]
    for i in range(6):
        for j in range(6, n):
            relation[i][j] = "CONTRADICTORY"
            relation[j][i] = "CONTRADICTORY"
    rec = _rec(keys, "L7", prov_all_same=0)
    res = detector.detect(rec, cluster_labels=labels,
                            relation_matrix=relation)
    assert res.contradiction_mass == pytest.approx(0.4)
    assert res.contradiction_source == "model"
    assert FLAG_CONTRADICTION in res.flags


def test_warranted_agreement_product_form(detector):
    # A=1, T=0, J=1, K=0 -> W=0, CM=1 (the failure signature)
    res = detector.detect(_rec(["IPC 302"] * 10, "L7"))
    assert res.observed_agreement == 1.0
    assert res.warranted_agreement == pytest.approx(0.0)
    assert res.common_mode_score == pytest.approx(1.0)


def test_compose_is_conservative_and_ablatable():
    # any single factor at zero removes all warrant
    assert compose(1.0, 0.0, 1.0, 0.0) == (0.0, 1.0)
    assert compose(1.0, 1.0, 0.0, 0.0) == (0.0, 1.0)
    assert compose(1.0, 1.0, 1.0, 1.0) == (0.0, 1.0)
    # a defined factor composed with an undefined one is undefined
    assert compose(1.0, None, 1.0, 0.0) == (None, None)


# ---------------------------------------------------------------------------
# the record round-trip and the additive schema
# ---------------------------------------------------------------------------

def test_result_round_trips_through_the_record(detector):
    rec = _rec(["IPC 302"] * 10, "L7")
    res = detector.detect(rec)
    fields = res.to_record()
    rec.update(fields)
    rebuilt = WarrantResult.from_record(rec)
    assert rebuilt.observed_agreement == res.observed_agreement
    assert rebuilt.temporal_validity == res.temporal_validity
    assert rebuilt.common_mode_score == res.common_mode_score
    assert rebuilt.flags == res.flags
    assert rebuilt.modal_key == res.modal_key


def test_record_fields_use_the_registered_prefix(detector):
    res = detector.detect(_rec(["IPC 302"] * 10, "L7"))
    fields = res.to_record()
    assert all(k.startswith("warrant_") for k in fields)
    for registered in ("warrant_observed_agreement",
                       "warrant_temporal_validity",
                       "warrant_jurisdiction_fit",
                       "warrant_contradiction_mass",
                       "warrant_warranted_agreement",
                       "warrant_common_mode_score",
                       "warrant_common_mode_flags"):
        assert registered in fields


# ---------------------------------------------------------------------------
# E4 validation and Gate G4
# ---------------------------------------------------------------------------

def _mini_population(detector):
    """A tiny run with both correctness classes in collision."""
    wrong = [_rec(["IPC 302"] * 10, "L7", 1) for _ in range(4)]
    for r in wrong:
        r["majority_correct"] = 0
    right = [_rec(["BNS 103"] * 10, "L7", 1) for _ in range(4)]
    for r in right:
        r["majority_correct"] = 1
    return wrong + right


def test_collision_population_selects_unanimous_items(detector):
    recs = _mini_population(detector)
    results = [(r, detector.detect(r)) for r in recs]
    pop = collision_population(results, lambda r: r["majority_correct"])
    assert len(pop) == 8


def test_separation_auroc_perfect_on_the_mini_population(detector):
    recs = _mini_population(detector)
    results = [(r, detector.detect(r)) for r in recs]
    pop = collision_population(results, lambda r: r["majority_correct"])
    sep = separation_auroc(pop, lambda r: r["majority_correct"])
    assert sep["defined"]
    assert sep["auroc"] == pytest.approx(1.0)
    assert sep["ci"]["lo"] > 0.5


def test_binary_confusion_counts_every_population_member(detector):
    recs = _mini_population(detector)
    results = [(r, detector.detect(r)) for r in recs]
    pop = collision_population(results, lambda r: r["majority_correct"])
    conf = binary_confusion(pop, lambda r: r["majority_correct"])
    assert conf["tp"] + conf["fn"] == 4      # wrong items
    assert conf["fp"] + conf["tn"] == 4      # correct items
    assert conf["n"] == 8


def test_factor_ablation_attributes_the_effect_to_time(detector):
    recs = _mini_population(detector)
    results = [(r, detector.detect(r)) for r in recs]
    pop = collision_population(results, lambda r: r["majority_correct"])
    ab = factor_ablation(pop, lambda r: r["majority_correct"],
                         detector)
    assert ab["full_auroc"] == pytest.approx(1.0)
    by = {a["factor"]: a for a in ab["ablations"]}
    # pinning the temporal factor away collapses the separation
    assert by["temporal"]["auroc_when_pinned"] == pytest.approx(0.5)
    # the other factors carry nothing on this construction
    assert by["jurisdiction"]["auroc_when_pinned"] == \
        pytest.approx(1.0)
    assert by["contradiction"]["auroc_when_pinned"] == \
        pytest.approx(1.0)


def test_gate_g4_passes_when_the_temporal_factor_carries_the_effect():
    sep = {"defined": True, "auroc": 0.94,
           "ci": {"lo": 0.85, "hi": 1.0}}
    attribution = {"full_auroc": 0.94,
                   "ablations": [
                       {"factor": "temporal",
                        "auroc_drop_from_full": 0.44},
                       {"factor": "jurisdiction",
                        "auroc_drop_from_full": 0.0},
                       {"factor": "contradiction",
                        "auroc_drop_from_full": 0.0}]}
    gate = gate_g4(sep, attribution, 0.0, 1.0)
    assert gate["verdict"] == "PASS"
    assert all(gate["conditions"].values())


def test_gate_g4_fails_when_separation_is_at_chance():
    sep = {"defined": True, "auroc": 0.5,
           "ci": {"lo": 0.4, "hi": 0.6}}
    attribution = {"full_auroc": 0.5,
                   "ablations": [
                       {"factor": "temporal",
                        "auroc_drop_from_full": 0.0}]}
    gate = gate_g4(sep, attribution, 0.5, 0.5)
    assert gate["verdict"] == "FAIL"


def test_gate_g4_fails_when_correct_items_alarm_as_often():
    sep = {"defined": True, "auroc": 0.9,
           "ci": {"lo": 0.8, "hi": 1.0}}
    attribution = {"full_auroc": 0.9,
                   "ablations": [
                       {"factor": "temporal",
                        "auroc_drop_from_full": 0.4}]}
    gate = gate_g4(sep, attribution, 0.9, 0.9)
    assert gate["verdict"] == "FAIL"
    assert gate["conditions"][
        "correct_item_alarm_below_wrong_item_alarm"] is False


# ---------------------------------------------------------------------------
# the end-to-end validation entry point
# ---------------------------------------------------------------------------

def test_validate_reproduces_from_stored_fields(detector):
    recs = _mini_population(detector)
    # attach the stored fields, then validate from the record alone
    for r in recs:
        r.update(detector.detect(r).to_record())
    report = validate(None, recs, lambda r: r["majority_correct"],
                      results=[(r, WarrantResult.from_record(r))
                               for r in recs])
    assert report["experiment"] == "E4"
    assert report["collision_population"]["n"] == 8
    assert report["gate_g4"]["verdict"] == "PASS"


def test_validate_reports_a_base_rate_over_the_rest(detector):
    recs = _mini_population(detector)
    # add non-collision items that are silent
    for _ in range(4):
        r = _rec(["BNS 103"] * 5 + ["BNS 105"] * 5, "L7", 0)
        r["majority_correct"] = 1
        recs.append(r)
    report = validate(detector, recs,
                      lambda r: r["majority_correct"])
    br = report["base_rate"]
    assert br["non_collision_items"] == 4
    assert br["correct_item_alarm_rate"] == 0.0
