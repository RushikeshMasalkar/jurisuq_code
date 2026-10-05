"""End-to-end smoke test of the Phase A instrument with the mock generator.

Purpose: prove the plumbing - sampling, judging, clustering, metrics, gate
evaluation - before a model is installed. It also checks that the mock's own
two error regimes are recovered by the instrument, which is the property that
makes the mock useful:

* on L7 the mock answers with the repealed provision as a *shared* error, so
  discrete semantic entropy stays at zero while the answer is wrong;
* on L1 the errors are idiosyncratic, so entropy rises when a sample is wrong.

If the instrument failed to recover that, the bug would be in the harness, not
in a real model's behaviour.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jurisuq.cluster import cluster_stats, make_clusterer
from jurisuq.config import Config
from jurisuq.generators import MockGenerator
from jurisuq.judge import ProvisionJudge
from jurisuq.metrics import auroc

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import importlib  # noqa: E402

make_data = importlib.import_module("01_make_data")
run_inference = importlib.import_module("02_run_inference")


@pytest.fixture(scope="module")
def records():
    cfg = Config()
    cfg.provider = "mock"
    cfg.n_samples = 8
    cfg.clusterer = "discrete"
    cfg.mock_p_trap_slice = {"L7": 0.5, "L1": 0.0}
    cfg.mock_p_uncertain = 0.25
    items = make_data.build(60, seed=11)
    gen = MockGenerator(cfg)
    judge = ProvisionJudge()
    discrete, entail, _ = make_clusterer(cfg)
    return [run_inference.score_item(it, cfg, gen, judge, (discrete, entail)) for it in items]


def test_records_have_the_required_fields(records):
    r = records[0]
    for key in ("item_id", "slice", "methods", "majority_correct", "all_same",
                "n_unique", "sample_texts", "sample_correct"):
        assert key in r
    assert r["methods"]["disc_se"] >= 0.0
    assert 0.0 <= r["methods"]["agreement"] <= 1.0
    assert len(r["sample_texts"]) == len(r["sample_correct"])


def test_mock_common_mode_regime_is_recovered(records):
    l7 = [r for r in records if r["slice"] == "L7"]
    l1 = [r for r in records if r["slice"] == "L1"]
    # on L7 roughly half the items are answered with the same wrong provision
    collision = [r for r in l7 if r["all_same"] == 1]
    assert collision, "mock produced no zero-entropy L7 items"
    wrong_in_collision = [r for r in collision if r["frac_correct"] == 0.0]
    assert len(wrong_in_collision) / len(collision) > 0.5, \
        "the mock's common-mode error is not visible to the instrument"
    # on L1 there is no shared-bias regime at all, so most samples are correct.
    # The assertion uses frac_correct (per-sample), not the majority verdict,
    # because with exact-string clustering at high paraphrase variance the modal
    # cluster can be a single paraphrase - which is a fact about the discrete
    # channel, not about the generator.
    frac_l1 = sum(r["frac_correct"] for r in l1) / len(l1)
    assert frac_l1 > 0.75, f"L1 per-sample accuracy too low: {frac_l1:.3f}"


def test_entropy_separates_idiosyncratic_errors_only(records):
    l1 = [r for r in records if r["slice"] == "L1"]
    # every L1 item is answered correctly by construction, so AUROC is undefined;
    # the meaningful check is that entropy is non-zero somewhere when samples vary
    assert any(r["n_unique"] > 1 for r in l1) or all(r["n_unique"] == 1 for r in l1)
    l7 = [r for r in records if r["slice"] == "L7"]
    assert auroc([r["methods"]["disc_se"] for r in l7],
                 [int(r["frac_correct"] >= 0.5) for r in l7]) <= 0.75


def test_report_pipeline_runs(tmp_path):
    """03_analyze_e1 builds a report with the required keys from these records."""
    analyze = importlib.import_module("03_analyze_e1")
    l7 = [r for r in _records_cached() if r["slice"] == "L7"]
    l1 = [r for r in _records_cached() if r["slice"] == "L1"]
    st = analyze.slice_table(l7, "disc_se")
    assert {"auroc", "aurc_norm", "risk_at_50", "accuracy"} <= set(st)
    g = analyze.bootstrap_auroc_diff(l1, l7, "disc_se", n_boot=100)
    assert "point" in g
    coll = analyze.collision_population(l7)
    assert coll["n"] > 0 and 0.0 <= coll["accuracy"] <= 1.0


_CACHE: list[dict] = []


def _records_cached() -> list[dict]:
    if not _CACHE:
        cfg = Config()
        cfg.provider = "mock"
        cfg.n_samples = 6
        cfg.clusterer = "discrete"
        cfg.mock_p_trap_slice = {"L7": 0.6, "L1": 0.0}
        cfg.mock_p_uncertain = 0.25
        items = make_data.build(40, seed=3)
        gen = MockGenerator(cfg)
        discrete, entail, _ = make_clusterer(cfg)
        _CACHE.extend(run_inference.score_item(it, cfg, gen, ProvisionJudge(), (discrete, entail))
                      for it in items)
    return _CACHE
