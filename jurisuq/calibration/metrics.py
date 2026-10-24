"""Calibration and selective-prediction metrics used by Phase F (M9/M10).

Definitions are fixed here once, in the spirit of master-guide section 21:

* ``p_reliable`` estimates P(the returned majority answer is correct).
* **ACE** (primary) averages absolute calibration error over five equal-width
  bins; **ECE** (secondary) repeats it over ten bins. Both are lower-is-better.
* **Brier** is the mean squared error of ``p_reliable``; lower-is-better.
* **Selective risk** at a coverage is the error rate among the accepted
  (highest-reliability) fraction; harm-weighted variants weight each accepted
  error by the harm class of the question.
* Ties in the acceptance order are broken by item order, so a risk-coverage
  curve is reproducible from the record alone.

``jurisuq.metrics`` already owns ECE, AUROC, AUPRC and risk-coverage for the
sample-level quantities; this module reuses ``ece`` rather than re-deriving it,
and adds only what is specific to calibration and harm weighting.
"""
from __future__ import annotations

import math
from typing import Sequence

from jurisuq.metrics import ece as _ece

HARM_WEIGHTS: dict[str, float] = {
    # Relative cost of a wrong answer by the consequence class of the offence
    # cluster the question is about (Phase C statute store vocabulary).
    "custodial": 5.0,
    "both": 3.0,
    "definition": 1.5,
    "procedural": 1.0,
    # A question whose harm class the store cannot resolve is treated as the
    # most serious class: the policy may over-verify, never under-warn.
    "unknown": 5.0,
}


def harm_weight(harm_class: str | None) -> float:
    """Cost multiplier for a harm class; unknown is conservative, never zero."""
    if harm_class is None:
        return HARM_WEIGHTS["unknown"]
    key = str(harm_class)
    if key not in HARM_WEIGHTS:
        raise ValueError(f"unknown harm class {key!r}; expected {sorted(HARM_WEIGHTS)}")
    return HARM_WEIGHTS[key]


def _paired(p: Sequence[float], y: Sequence[int]) -> tuple[list[float], list[int]]:
    if len(p) != len(y):
        raise ValueError("probabilities and labels must be aligned")
    probs, labels = [], []
    for prob, label in zip(p, y):
        if prob is None:
            continue
        value = float(prob)
        if not math.isfinite(value) or not 0.0 <= value <= 1.0:
            raise ValueError("probabilities must be finite and lie in [0, 1]")
        if label not in (0, 1) or isinstance(label, bool):
            raise ValueError("labels must be binary 0/1")
        probs.append(value)
        labels.append(int(label))
    return probs, labels


def ace(p: Sequence[float], y: Sequence[int], bins: int = 5) -> float | None:
    """Absolute calibration error over ``bins`` equal-width bins (primary)."""
    probs, labels = _paired(p, y)
    if not probs:
        return None
    value = _ece(probs, labels, bins=bins)
    return None if not math.isfinite(value) else float(value)


def ece(p: Sequence[float], y: Sequence[int], bins: int = 10) -> float | None:
    """Expected calibration error over ten bins (secondary)."""
    probs, labels = _paired(p, y)
    if not probs:
        return None
    value = _ece(probs, labels, bins=bins)
    return None if not math.isfinite(value) else float(value)


def brier(p: Sequence[float], y: Sequence[int]) -> float | None:
    """Mean squared error of the probability forecast."""
    probs, labels = _paired(p, y)
    if not probs:
        return None
    return sum((prob - label) ** 2 for prob, label in zip(probs, labels)) / len(probs)


def log_loss(p: Sequence[float], y: Sequence[int], *, epsilon: float = 1e-6) -> float | None:
    """Binary negative log-likelihood with probability clipping."""
    probs, labels = _paired(p, y)
    if not probs:
        return None
    total = 0.0
    for prob, label in zip(probs, labels):
        q = min(1.0 - epsilon, max(epsilon, prob))
        total += -math.log(q if label else 1.0 - q)
    return total / len(probs)


def reliability_table(p: Sequence[float], y: Sequence[int], bins: int = 5) -> list[dict]:
    """Per-bin count, mean forecast and observed accuracy (reliability diagram)."""
    probs, labels = _paired(p, y)
    if not probs:
        return []
    rows = []
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        idx = [i for i, prob in enumerate(probs)
               if (prob > lo or (b == 0 and prob >= lo)) and prob <= hi]
        if not idx:
            rows.append({"bin": b, "lo": lo, "hi": hi, "n": 0,
                         "mean_p": None, "accuracy": None})
            continue
        rows.append({"bin": b, "lo": lo, "hi": hi, "n": len(idx),
                     "mean_p": sum(probs[i] for i in idx) / len(idx),
                     "accuracy": sum(labels[i] for i in idx) / len(idx)})
    return rows


def acceptance_order(p: Sequence[float]) -> list[int]:
    """Indices from most to least reliable; ties keep record order."""
    return sorted(range(len(p)), key=lambda i: (-float(p[i]), i))


def selective_risk(p: Sequence[float], y: Sequence[int], coverage: float, *,
                   weights: Sequence[float] | None = None) -> dict:
    """Error rate among the accepted fraction, optionally harm-weighted.

    ``p`` must already be filtered to the evaluable population and aligned with
    ``y`` (and ``weights``). Returns ``None`` metrics when the population is
    empty or the coverage is out of range.
    """
    if not 0.0 < coverage <= 1.0:
        raise ValueError("coverage must lie in (0, 1]")
    if len(p) != len(y):
        raise ValueError("probabilities and labels must be aligned")
    n = len(p)
    if n == 0:
        return {"coverage": coverage, "n": 0, "n_accepted": 0, "risk": None,
                "harm_weighted_risk": None, "threshold": None}
    if weights is not None and len(weights) != n:
        raise ValueError("weights must be aligned with the population")
    order = acceptance_order(p)
    n_accept = max(1, int(math.ceil(coverage * n)))
    accepted = order[:n_accept]
    errors = sum(1 - int(y[i]) for i in accepted)
    risk = errors / n_accept
    if weights is None:
        harm_risk = risk
    else:
        total_w = sum(float(weights[i]) for i in accepted)
        harm_risk = (sum(float(weights[i]) * (1 - int(y[i])) for i in accepted) / total_w
                     if total_w > 0 else risk)
    threshold = float(p[accepted[-1]])
    return {"coverage": coverage, "n": n, "n_accepted": n_accept, "risk": risk,
            "harm_weighted_risk": harm_risk, "threshold": threshold,
            "n_errors_accepted": errors}


def risk_coverage_curve(p: Sequence[float], y: Sequence[int], *,
                        weights: Sequence[float] | None = None,
                        points: Sequence[float] = (0.1, 0.2, 0.3, 0.4, 0.5, 0.6,
                                                   0.7, 0.8, 0.9, 1.0)) -> list[dict]:
    """Selective risk at each requested coverage."""
    return [selective_risk(p, y, cover, weights=weights) for cover in points]
