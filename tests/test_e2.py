"""Regression test for the E2 separation test: both branches must run.

The model branch crashed once with an UnboundLocalError because its sample count
was defined only in the rule branch. The stub below keeps that path covered
without torch.
"""
from __future__ import annotations

import importlib.util
import json
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def load_script():
    spec = importlib.util.spec_from_file_location("eval12", ROOT / "scripts" / "12_eval_relation.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def fixture(tmp_path, n_items=6):
    run = tmp_path / "phaseA-fixture"
    run.mkdir()
    rows = []
    for i in range(n_items):
        wrong = i % 2 == 0
        key = "IPC 302" if wrong else "BNS 103"
        rows.append({
            "item_id": f"L7-t{i:03d}", "slice": "L7",
            "sample_texts": [f"answer {k}" for k in range(10)],
            "asserted_keys": [key] * 10,
            "majority_correct": 0 if wrong else 1,
        })
    (run / "items.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    return run


def test_model_branch_runs_with_a_stub_predictor(tmp_path, monkeypatch):
    e = load_script()
    run = fixture(tmp_path)

    class StubModel:
        pass

    def fake_score_samples(model, tokenizer, texts, asserted, ctx, cfg, keys=None, tau=None):
        m = len(texts)
        same = [["SAME_PROVISION"] * m for _ in range(m)]
        score = [[1.0] * m for _ in range(m)]
        return {"relation": same, "merge_score": score, "clusters": [0] * m,
                "canonical": [keys[0]], "members": [list(range(m))], "tau": 0.5,
                "merges_applied": m - 1, "merges_skipped": 0,
                "encoder_pairs": 0, "rule_pairs": m * (m - 1)}

    monkeypatch.setattr(e.M, "score_samples", fake_score_samples)
    meta = {"merge_threshold": 0.5, "encoder": "stub"}
    rep = e.e2_separation(run, model=StubModel(), tokenizer=object(), meta=meta, cfg={},
                          crosswalk={}, progress_every=0)
    assert rep["n_scored"] == 6
    assert rep["rule_pairs"] == 6 * 10 * 9
    assert rep["by_slice"]["L7"]["typed_collision_n"] == 6


def test_rule_branch_and_limit(tmp_path):
    e = load_script()
    run = fixture(tmp_path)
    rep = e.e2_separation(run, model=None, crosswalk={}, limit_items=4, progress_every=0)
    assert rep["n_scored"] == 4
    assert "typed_unanimous_accuracy" in rep
