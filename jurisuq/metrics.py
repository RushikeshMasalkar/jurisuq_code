"""Evaluation metrics for selective prediction under uncertainty.

All functions are pure Python with no compiled dependencies, so the numbers
can be reproduced on any machine and unit-tested exactly.

Conventions
-----------
* ``uncertainty``: higher means *less* certain (semantic entropy, 1 - top
  probability, and so on).
* ``correct``: 1/0 per item, resolved without ground truth by the judge.
* AUROC is reported for the *confidence* direction, i.e. AUROC = P(uncertainty
  of a correct answer < uncertainty of an incorrect answer) + 0.5 * P(tie).
"""
from __future__ import annotations

import math
import random
from typing import Callable, Sequence

# ----------------------------------------------------------------------
# AUROC
# ----------------------------------------------------------------------
def _average_ranks(values: Sequence[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def auroc(uncertainty: Sequence[float], correct: Sequence[int]) -> float:
    """Area under the ROC curve for detecting incorrect answers.

    ``correct`` must contain at least one 0 and one 1; otherwise NaN is
    returned (an undefined rather than a perfect score).
    """
    n_pos = sum(1 for c in correct if c == 1)
    n_neg = len(correct) - n_pos
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    # Confidence = -uncertainty, so the higher-confidence class is the positive.
    conf = [-u for u in uncertainty]
    ranks = _average_ranks(conf)
    rank_sum_pos = sum(r for r, c in zip(ranks, correct) if c == 1)
    return (rank_sum_pos - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg)


# ----------------------------------------------------------------------
# Selective prediction
# ----------------------------------------------------------------------
def risk_coverage(correct: Sequence[int], uncertainty: Sequence[float],
                  coverages: Sequence[float] | None = None) -> dict:
    """Selective risk and accuracy as a function of coverage.

    Answers are accepted in ascending order of uncertainty (most confident
    first). Coverage k/n means accepting the k most confident answers.
    """
    n = len(correct)
    if n == 0:
        return {"coverage": [], "risk": [], "accuracy": []}
    order = sorted(range(n), key=lambda i: (uncertainty[i], i))
    cov, risk, acc = [], [], []
    errs = 0
    for k, idx in enumerate(order, start=1):
        errs += 1 - int(correct[idx])
        cov.append(k / n)
        risk.append(errs / k)
        acc.append(1 - errs / k)
    out = {"coverage": cov, "risk": risk, "accuracy": acc}
    if coverages:
        out["at"] = {c: {"risk": _interp(cov, risk, c), "accuracy": _interp(cov, acc, c)}
                     for c in coverages}
    return out


def _interp(xs: Sequence[float], ys: Sequence[float], x: float) -> float:
    if not xs:
        return float("nan")
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    for i in range(1, len(xs)):
        if xs[i] >= x:
            x0, x1, y0, y1 = xs[i - 1], xs[i], ys[i - 1], ys[i]
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0) if x1 > x0 else y1
    return ys[-1]


def aurc(correct: Sequence[int], uncertainty: Sequence[float]) -> float:
    """Area under the risk-coverage curve (lower is better).

    This is mean selective risk over the coverage grid 1/n .. 1, the standard
    AURC used with accuracy-rejection curves (Nadeem et al., MLSB 2009).
    """
    rc = risk_coverage(correct, uncertainty)
    return sum(rc["risk"]) / len(rc["risk"]) if rc["risk"] else float("nan")


def normalized_aurc(correct: Sequence[int], uncertainty: Sequence[float]) -> float:
    """AURC expressed as a skill score against the trivial orderings.

    1.0 = as good as a perfect uncertainty ranking; 0.0 = equal to always
    accepting a random subset; negative = worse than random (a broken signal).
    """
    n = len(correct)
    if n == 0:
        return float("nan")
    perfect_order = sorted(range(n), key=lambda i: -int(correct[i]))
    best = aurc([correct[i] for i in perfect_order], list(range(n)))
    worst = aurc([correct[i] for i in perfect_order[::-1]], list(range(n)))
    random_aurc = sum(1 - int(c) for c in correct) / n  # expected risk of a random subset
    got = aurc(correct, uncertainty)
    if random_aurc <= best:
        return float("nan")
    return (random_aurc - got) / (random_aurc - best)


# ----------------------------------------------------------------------
# Calibration of a confidence-like score
# ----------------------------------------------------------------------
def ece(confidence: Sequence[float], correct: Sequence[int], bins: int = 10) -> float:
    """Expected calibration error with equal-width bins."""
    n = len(confidence)
    if n == 0:
        return float("nan")
    total = 0.0
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        idx = [i for i in range(n) if (confidence[i] > lo or (b == 0 and confidence[i] >= lo))
               and confidence[i] <= hi]
        if not idx:
            continue
        acc = sum(int(correct[i]) for i in idx) / len(idx)
        conf = sum(confidence[i] for i in idx) / len(idx)
        total += (len(idx) / n) * abs(acc - conf)
    return total


# ----------------------------------------------------------------------
# Bootstrap
# ----------------------------------------------------------------------
def _percentile(sorted_vals: Sequence[float], q: float) -> float:
    if not sorted_vals:
        return float("nan")
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    pos = q * (len(sorted_vals) - 1)
    lo = int(math.floor(pos))
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = pos - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac


def bootstrap_ci(values: Sequence[float], stat: Callable[[Sequence[float]], float],
                 n_boot: int = 2000, alpha: float = 0.05, seed: int = 0) -> dict:
    rng = random.Random(seed)
    n = len(values)
    if n == 0:
        return {"point": float("nan"), "lo": float("nan"), "hi": float("nan"), "n": 0}
    point = stat(values)
    samples = []
    for _ in range(n_boot):
        idx = [rng.randrange(n) for _ in range(n)]
        v = stat([values[i] for i in idx])
        if v == v:  # skip NaN
            samples.append(v)
    samples.sort()
    return {"point": point,
            "lo": _percentile(samples, alpha / 2),
            "hi": _percentile(samples, 1 - alpha / 2),
            "n": n, "n_boot": len(samples)}


def two_sample_bootstrap_diff(a: Sequence[float], b: Sequence[float],
                              stat: Callable[[Sequence[float]], float],
                              n_boot: int = 2000, alpha: float = 0.05,
                              seed: int = 0) -> dict:
    """CI for stat(a) - stat(b) when the two sets are *independent* samples.

    Use this for the L7-versus-L1 comparison, where the item sets differ.
    """
    rng = random.Random(seed)
    point = stat(a) - stat(b)
    diffs = []
    na, nb = len(a), len(b)
    for _ in range(n_boot):
        sa = [a[rng.randrange(na)] for _ in range(na)]
        sb = [b[rng.randrange(nb)] for _ in range(nb)]
        d = stat(sa) - stat(sb)
        if d == d:
            diffs.append(d)
    diffs.sort()
    p_le_zero = sum(1 for d in diffs if d <= 0) / len(diffs) if diffs else float("nan")
    return {"point": point, "lo": _percentile(diffs, alpha / 2),
            "hi": _percentile(diffs, 1 - alpha / 2),
            "p_le_zero": p_le_zero, "n_boot": len(diffs)}


def paired_bootstrap_diff(correct: Sequence[int],
                          uncertainty_a: Sequence[float],
                          uncertainty_b: Sequence[float],
                          n_boot: int = 2000, alpha: float = 0.05,
                          seed: int = 0) -> dict:
    """CI for AUROC(a) - AUROC(b) on the *same* items (paired resampling).

    Use this to compare two uncertainty methods on one slice.
    """
    rng = random.Random(seed)
    n = len(correct)
    if n == 0:
        return {"point": float("nan"), "lo": float("nan"), "hi": float("nan")}
    point = auroc(uncertainty_a, correct) - auroc(uncertainty_b, correct)
    diffs = []
    for _ in range(n_boot):
        idx = [rng.randrange(n) for _ in range(n)]
        c = [correct[i] for i in idx]
        if all(x == c[0] for x in c):
            continue
        d = auroc([uncertainty_a[i] for i in idx], c) - auroc([uncertainty_b[i] for i in idx], c)
        if d == d:
            diffs.append(d)
    diffs.sort()
    p_le_zero = sum(1 for d in diffs if d <= 0) / len(diffs) if diffs else float("nan")
    return {"point": point, "lo": _percentile(diffs, alpha / 2),
            "hi": _percentile(diffs, 1 - alpha / 2),
            "p_le_zero": p_le_zero, "n_boot": len(diffs)}


# ----------------------------------------------------------------------
# Agreement between two correctness resolvers
# ----------------------------------------------------------------------
def cohen_kappa(a: Sequence[int], b: Sequence[int]) -> float:
    """Cohen's kappa for two binary labellings of the same items."""
    n = len(a)
    if n == 0:
        return float("nan")
    po = sum(1 for x, y in zip(a, b) if x == y) / n
    pa1 = sum(a) / n
    pb1 = sum(b) / n
    pe = pa1 * pb1 + (1 - pa1) * (1 - pb1)
    return (po - pe) / (1 - pe) if pe != 1 else float("nan")


def summarize_method(correct: Sequence[int], uncertainty: Sequence[float],
                     coverages: Sequence[float] = (0.25, 0.5, 0.75, 1.0)) -> dict:
    rc = risk_coverage(correct, uncertainty, coverages)
    unc_correct = [u for u, c in zip(uncertainty, correct) if c == 1]
    unc_wrong = [u for u, c in zip(uncertainty, correct) if c == 0]
    return {
        "n": len(correct),
        "acc_full": (sum(correct) / len(correct)) if correct else float("nan"),
        "auroc": auroc(uncertainty, correct),
        "aurc": aurc(correct, uncertainty),
        "aurc_norm": normalized_aurc(correct, uncertainty),
        "risk_at": {k: v["risk"] for k, v in rc.get("at", {}).items()},
        "mean_unc_correct": (sum(unc_correct) / len(unc_correct)) if unc_correct else float("nan"),
        "mean_unc_incorrect": (sum(unc_wrong) / len(unc_wrong)) if unc_wrong else float("nan"),
    }
