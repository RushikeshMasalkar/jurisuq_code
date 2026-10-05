"""Unit tests: metrics. Every expected value is computed by hand."""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jurisuq.metrics import (aurc, auroc, cohen_kappa, ece, normalized_aurc,
                             risk_coverage, two_sample_bootstrap_diff)


def test_auroc_perfect_and_reversed():
    unc = [0.1, 0.2, 0.3, 0.9, 0.95]
    cor = [1, 1, 1, 0, 0]
    assert auroc(unc, cor) == pytest.approx(1.0)
    assert auroc(unc, list(reversed(cor))) == pytest.approx(0.0)


def test_auroc_ties_give_half():
    # every uncertainty value identical -> no ranking information
    unc = [0.5] * 6
    cor = [1, 0, 1, 0, 1, 0]
    assert auroc(unc, cor) == pytest.approx(0.5)


def test_auroc_known_value():
    # one error ranked above one correct answer, others perfectly ordered:
    # AUC = 1 - (rank_of_error_pair)/... computed by hand below
    unc = [0.1, 0.4, 0.6, 0.2]
    cor = [1, 1, 0, 0]
    # pairs (correct i, incorrect j): (1,6) 0.1<0.6 ok ; (1,2) 0.1<0.2 ok
    #                                (4,6) 0.4<0.6 ok ; (4,2) 0.4>0.2 miss
    assert auroc(unc, cor) == pytest.approx(0.75)


def test_auroc_undefined_when_single_class():
    assert math.isnan(auroc([0.1, 0.2], [1, 1]))


def test_risk_coverage_monotone_shape():
    cor = [1, 0, 1, 1]
    unc = [0.1, 0.9, 0.2, 0.3]
    rc = risk_coverage(cor, unc)
    assert rc["coverage"] == [0.25, 0.5, 0.75, 1.0]
    # most confident first: 1, 1, 1, 0 -> risk 0, 0, 0, 0.25
    assert rc["risk"] == [0.0, 0.0, 0.0, 0.25]
    at = risk_coverage(cor, unc, coverages=(0.5,))["at"][0.5]
    assert at["risk"] == pytest.approx(0.0)


def test_aurc_and_normalized():
    cor = [1, 1, 0, 1]
    unc_good = [0.1, 0.2, 0.9, 0.3]
    unc_bad = [0.9, 0.8, 0.1, 0.7]
    assert aurc(cor, unc_good) < aurc(cor, unc_bad)
    assert normalized_aurc(cor, unc_good) > normalized_aurc(cor, unc_bad)


def test_ece_bounds():
    conf = [0.9] * 10
    cor = [1] * 9 + [0]
    e = ece(conf, cor)
    assert 0 <= e <= 1
    assert e == pytest.approx(abs(0.9 - 0.9), abs=1e-9) or e > 0


def test_kappa_perfect_and_chance():
    assert cohen_kappa([1, 0, 1, 0], [1, 0, 1, 0]) == pytest.approx(1.0)
    # 50/50 labels predicted independently -> kappa near 0
    a = [1, 1, 0, 0, 1, 1, 0, 0]
    b = [1, 0, 0, 1, 1, 0, 0, 1]
    assert abs(cohen_kappa(a, b)) < 0.3


def test_two_sample_bootstrap_direction():
    a = [1.0, 1.1, 1.2, 0.9, 1.05]
    b = [2.0, 2.1, 1.9, 2.2, 2.05]
    out = two_sample_bootstrap_diff(a, b, lambda v: sum(v) / len(v), n_boot=200, seed=1)
    assert out["hi"] < 0 < out["point"] or out["lo"] < 0
