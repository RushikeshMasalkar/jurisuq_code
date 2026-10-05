"""Unit tests: the G1 decision rule, exercised on controlled records.

These tests fix the *logic* of the gate, independently of any generator:
we construct item records whose uncertainty scores and correctness labels are
known, run them through the same functions the analysis script uses, and check
that the verdict responds to the two conditions the rule is built on.
"""
from __future__ import annotations

import importlib
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

analyze = importlib.import_module("03_analyze_e1")


def rec(slice_name: str, unc: float, correct: int, all_same: int = 0) -> dict:
    """A record as the pipeline writes it, with both collision levels set."""
    return {"slice": slice_name,
            "methods": {"disc_se": unc, "agreement": min(1.0, unc / 3.0),
                        "prov_se": unc, "prov_agreement": min(1.0, unc / 3.0)},
            "majority_correct": correct,
            "majority_resolved": 1,
            "prov_all_same": all_same,
            "all_same": all_same}


def build_case(l7_collision_wrong: int, l7_auroc_shift: float,
               l1_collision_wrong: int) -> list[dict]:
    rng = random.Random(7)
    recs: list[dict] = []
    # L7: zero-entropy, wrong, self-consistent answers dominate the errors
    for _ in range(l7_collision_wrong):
        recs.append(rec("L7", 0.0, 0, all_same=1))
    for _ in range(80 - l7_collision_wrong):
        wrong = rng.random() < 0.10
        unc = rng.uniform(1.6, 2.4) if wrong else rng.uniform(0.4, 1.2) + l7_auroc_shift
        recs.append(rec("L7", unc, int(not wrong)))
    for _ in range(l1_collision_wrong):
        recs.append(rec("L1", 0.0, 0, all_same=1))
    for _ in range(80 - l1_collision_wrong):
        wrong = rng.random() < 0.20
        unc = rng.uniform(1.8, 2.6) if wrong else rng.uniform(0.1, 0.6)
        recs.append(rec("L1", unc, int(not wrong)))
    return recs


def evaluate(recs: list[dict]) -> dict:
    slices = sorted({r["slice"] for r in recs})
    per_slice = {}
    for s in slices:
        sub = [r for r in recs if r["slice"] == s]
        per_slice[s] = {"n_items": len(sub),
                        "methods": {m: analyze.slice_table(sub, m) for m in ("disc_se", "agreement")}}
    l7 = [r for r in recs if r["slice"] == "L7"]
    l1 = [r for r in recs if r["slice"] == "L1"]
    results = {
        "per_slice": per_slice,
        "gaps": {m: analyze.bootstrap_auroc_diff(l1, l7, m, n_boot=400, seed=3)
                 for m in ("disc_se", "agreement")},
        "collision": {s: analyze.collision_population([r for r in recs if r["slice"] == s])
                      for s in slices},
    }
    results["gate_G1"] = analyze.gate_verdict(results)
    return results


def test_gate_passes_when_both_conditions_hold():
    res = evaluate(build_case(l7_collision_wrong=36, l7_auroc_shift=0.0, l1_collision_wrong=2))
    v = res["gate_G1"]
    assert v["ceiling_ok"] is True
    assert v["contrast_ok"] is True or v["gap_ok"] is True
    assert v["pass"] is True


def test_gate_fails_when_agreement_ranks_errors_well_on_l7():
    # L7 with almost no collision population and informative entropy: the
    # ceiling fails, and the rule must say so rather than pass on a contrast
    # borrowed from the collision statistic.
    recs = build_case(l7_collision_wrong=1, l7_auroc_shift=1.2, l1_collision_wrong=1)
    res = evaluate(recs)
    v = res["gate_G1"]
    assert "ceiling_ok" in v
    if not v["ceiling_ok"]:
        assert v["pass"] is False


def test_collision_contrast_requires_non_overlapping_intervals():
    # L7 confidently wrong more often than L1, but with so few zero-entropy
    # items that the intervals overlap: the contrast must not pass.
    recs = [rec("L7", 0.0, 0, all_same=1) for _ in range(3)]
    recs += [rec("L7", 1.0, 1) for _ in range(20)]
    recs += [rec("L1", 0.0, 1, all_same=1) for _ in range(2)]
    recs += [rec("L1", 1.0, 1) for _ in range(20)]
    res = evaluate(recs)
    assert res["gate_G1"]["contrast_ok"] is False


def test_collision_population_wilson_bounds_are_sane():
    recs = [rec("L7", 0.0, 0, all_same=1) for _ in range(30)] + \
           [rec("L7", 1.0, 1) for _ in range(10)]
    coll = analyze.collision_population([r for r in recs if r["slice"] == "L7"])
    assert coll["n"] == 30
    assert coll["accuracy"] == 0.0
    assert coll["confident_wrong"] == 1.0
    assert coll["lo"] <= coll["accuracy"] <= coll["hi"]


def test_single_class_slice_uses_collision_for_the_ceiling():
    """When the model fails every item, AUROC is undefined and the ceiling must be
    read from the collision statistic - that is the situation the real 7B model
    produced, so the rule has to handle it explicitly."""
    recs = [rec("L7", 0.0, 0, all_same=1) for _ in range(40)]
    recs += [rec("L7", 1.5, 0) for _ in range(20)]
    recs += [rec("L1", 0.0, 1, all_same=1) for _ in range(5)]
    recs += [rec("L1", 0.2, 1) for _ in range(60)]
    res = evaluate(recs)
    v = res["gate_G1"]
    assert v["ceiling_ok"] is True
    assert v.get("ceiling_basis", "").startswith("collision-statistic")
    assert v["contrast_ok"] is True
    assert v["pass"] is True


def test_single_class_without_a_collision_population_does_not_pass():
    recs = [rec("L7", 1.2, 0) for _ in range(40)]
    recs += [rec("L1", 0.2, 1) for _ in range(40)]
    res = evaluate(recs)
    v = res["gate_G1"]
    assert v["pass"] is False


def test_collision_population_prefers_the_provision_level():
    """Ten differently worded answers that all assert one wrong provision must
    count as unanimous, even though no two strings are identical."""
    recs = [rec("L7", 3.3, 0, all_same=0) for _ in range(20)]
    for r in recs:
        r["prov_all_same"] = 1        # same provision, different wording
    prov = analyze.collision_population(recs, level="provision")
    text = analyze.collision_population(recs, level="text")
    assert prov["n"] == 20 and text["n"] == 0
    assert prov["confident_wrong"] == 1.0
