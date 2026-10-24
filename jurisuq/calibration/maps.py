"""Phase F (M9): calibration maps from an uncertainty score to P(correct).

Two maps are provided, exactly as the master guide specifies:

* isotonic regression (pool-adjacent-violators) - the default, non-parametric;
* Platt scaling (smoothed logistic) - the small-stratum fallback.

Both are pure Python and stdlib-only, like every other phase-C/D/E component.
Neither map is fitted here on the query path: fitting is a separate offline CLI
(``scripts/29_fit_calibration.py``) and scoring (``scripts/30_apply_policy.py``)
only *applies* a stored map.

Orientation
-----------
Phase E emits a *risk* score: larger means more likely to be wrong. The maps in
this module are fitted on the reliability input ``r = 1 - risk`` so that the
monotone requirement is stated in one place and is testable:

    r1 <= r2  =>  p_reliable(r1) <= p_reliable(r2)

``p_reliable`` is an estimate of P(returned majority answer is correct). It is a
probability only insofar as the map is calibrated on data drawn like the fitting
data; the run metadata says which data that was.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

_EPS = 1e-12


def _clip01(value: float) -> float:
    return 0.0 if value < 0.0 else (1.0 if value > 1.0 else value)


def _sigmoid(z: float) -> float:
    z = max(-35.0, min(35.0, z))
    return 1.0 / (1.0 + math.exp(-z))


def reliability_input(risk_score: float) -> float:
    """Convert a Phase E risk score into the reliability input ``1 - risk``."""
    value = float(risk_score)
    if not math.isfinite(value):
        raise ValueError("risk score must be finite")
    return _clip01(1.0 - value)


# ----------------------------------------------------------------------
# Isotonic regression (pool adjacent violators)
# ----------------------------------------------------------------------
@dataclass(frozen=True)
class IsotonicMap:
    """Monotone non-decreasing step/interpolation map fitted by PAV.

    ``x`` holds the sorted, tie-aggregated abscissae and ``y`` the fitted
    probabilities at those abscissae. Points between knots are linearly
    interpolated; the ends are clamped. The result is continuous and monotone,
    which keeps the reliability ordering identical to the fitted ordering.
    """

    x: tuple[float, ...]
    y: tuple[float, ...]
    n: int = 0
    n_positive: int = 0
    n_negative: int = 0
    method: str = "isotonic"
    note: str = ""

    def __post_init__(self) -> None:
        if len(self.x) != len(self.y):
            raise ValueError("isotonic map: x and y must be aligned")
        if not self.x:
            raise ValueError("isotonic map: at least one knot is required")
        if any(b < a for a, b in zip(self.x, self.x[1:])):
            raise ValueError("isotonic map: knots must be non-decreasing")
        if any(not math.isfinite(v) for v in self.x):
            raise ValueError("isotonic map: knots must be finite")
        if any(not 0.0 <= v <= 1.0 for v in self.y):
            raise ValueError("isotonic map: fitted values must lie in [0, 1]")
        if any(b < a for a, b in zip(self.y, self.y[1:])):
            raise ValueError("isotonic map: fitted values must be non-decreasing")

    def predict(self, reliability: float) -> float:
        r = _clip01(float(reliability))
        if len(self.x) == 1:
            return _clip01(self.y[0])
        if r <= self.x[0]:
            return _clip01(self.y[0])
        if r >= self.x[-1]:
            return _clip01(self.y[-1])
        lo, hi = 0, len(self.x) - 1
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if self.x[mid] <= r:
                lo = mid
            else:
                hi = mid
        x0, x1 = self.x[lo], self.x[hi]
        y0, y1 = self.y[lo], self.y[hi]
        if x1 == x0:
            return _clip01(y1)
        t = (r - x0) / (x1 - x0)
        return _clip01(y0 + t * (y1 - y0))

    def to_dict(self) -> dict:
        return {"method": self.method, "x": list(self.x), "y": list(self.y),
                "n": self.n, "n_positive": self.n_positive,
                "n_negative": self.n_negative, "note": self.note}

    @classmethod
    def from_dict(cls, obj: dict) -> "IsotonicMap":
        return cls(tuple(float(v) for v in obj["x"]), tuple(float(v) for v in obj["y"]),
                   int(obj.get("n", 0)), int(obj.get("n_positive", 0)),
                   int(obj.get("n_negative", 0)), str(obj.get("method", "isotonic")),
                   str(obj.get("note", "")))


def fit_isotonic(reliability: Sequence[float], correct: Sequence[int], *,
                 note: str = "") -> IsotonicMap:
    """Fit P(correct) against the reliability input with PAV.

    Ties in ``reliability`` are aggregated with counts before pooling, so the
    fit does not depend on record order.
    """
    if len(reliability) != len(correct) or not correct:
        raise ValueError("reliability and correct must be nonempty and aligned")
    labels = [int(bool(c)) for c in correct]
    if any(y not in (0, 1) for y in labels):
        raise ValueError("correct labels must be binary 0/1")
    if len(set(labels)) < 2:
        raise ValueError("isotonic calibration requires both correctness classes")
    xs = [float(v) for v in reliability]
    if any(not math.isfinite(v) for v in xs):
        raise ValueError("reliability input must be finite")
    if any(not 0.0 <= v <= 1.0 for v in xs):
        raise ValueError("reliability input must lie in [0, 1]")

    # aggregate ties: (x, positives, count)
    grouped: dict[float, list[int]] = {}
    for x, y in zip(xs, labels):
        cell = grouped.setdefault(x, [0, 0])
        cell[0] += y
        cell[1] += 1
    blocks: list[list[float]] = [[x, pos, n] for x, (pos, n) in sorted(grouped.items())]

    # pool adjacent violators
    i = 0
    while i < len(blocks) - 1:
        mean_i = blocks[i][1] / blocks[i][2]
        mean_j = blocks[i + 1][1] / blocks[i + 1][2]
        if mean_i <= mean_j + _EPS:
            i += 1
            continue
        merged = [blocks[i][0], blocks[i][1] + blocks[i + 1][1], blocks[i][2] + blocks[i + 1][2]]
        blocks[i:i + 2] = [merged]
        if i > 0:
            i -= 1
    knots_x = tuple(b[0] for b in blocks)
    knots_y = tuple(_clip01(b[1] / b[2]) for b in blocks)
    return IsotonicMap(knots_x, knots_y, len(labels), sum(labels),
                       len(labels) - sum(labels), "isotonic", note)


# ----------------------------------------------------------------------
# Platt scaling
# ----------------------------------------------------------------------
@dataclass(frozen=True)
class PlattMap:
    """Logistic calibration ``p = sigmoid(a * r + b)`` with ``a >= 0``.

    Platt's smoothed targets are used ((N+ + 1)/(N+ + 2) and 1/(N- + 2)) so a
    perfectly separated small stratum does not produce infinite coefficients.
    The non-negative slope is enforced because the map must preserve the
    reliability ordering; a negative slope would invert it.
    """

    slope: float
    intercept: float
    n: int = 0
    n_positive: int = 0
    n_negative: int = 0
    method: str = "platt"
    note: str = ""

    def __post_init__(self) -> None:
        if not math.isfinite(self.slope) or not math.isfinite(self.intercept):
            raise ValueError("platt map: coefficients must be finite")
        if self.slope < 0.0:
            raise ValueError("platt map: slope must be non-negative to preserve ordering")

    def predict(self, reliability: float) -> float:
        return _clip01(_sigmoid(self.slope * _clip01(float(reliability)) + self.intercept))

    def to_dict(self) -> dict:
        return {"method": self.method, "slope": self.slope, "intercept": self.intercept,
                "n": self.n, "n_positive": self.n_positive,
                "n_negative": self.n_negative, "note": self.note}

    @classmethod
    def from_dict(cls, obj: dict) -> "PlattMap":
        return cls(float(obj["slope"]), float(obj["intercept"]), int(obj.get("n", 0)),
                   int(obj.get("n_positive", 0)), int(obj.get("n_negative", 0)),
                   str(obj.get("method", "platt")), str(obj.get("note", "")))


def fit_platt(reliability: Sequence[float], correct: Sequence[int], *,
              iterations: int = 200, note: str = "") -> PlattMap:
    """Fit Platt scaling by damped Newton steps on the smoothed likelihood."""
    if len(reliability) != len(correct) or not correct:
        raise ValueError("reliability and correct must be nonempty and aligned")
    labels = [int(bool(c)) for c in correct]
    if any(y not in (0, 1) for y in labels):
        raise ValueError("correct labels must be binary 0/1")
    if len(set(labels)) < 2:
        raise ValueError("platt calibration requires both correctness classes")
    xs = [float(v) for v in reliability]
    if any(not math.isfinite(v) for v in xs):
        raise ValueError("reliability input must be finite")
    if any(not 0.0 <= v <= 1.0 for v in xs):
        raise ValueError("reliability input must lie in [0, 1]")

    n_pos = sum(labels)
    n_neg = len(labels) - n_pos
    t_pos = (n_pos + 1.0) / (n_pos + 2.0)
    t_neg = 1.0 / (n_neg + 2.0)
    targets = [t_pos if y else t_neg for y in labels]

    slope, intercept = 1.0, 0.0
    for _ in range(iterations):
        g_a = g_b = 0.0
        h_aa = h_ab = h_bb = 0.0
        for x, t in zip(xs, targets):
            p = _sigmoid(slope * x + intercept)
            w = max(p * (1.0 - p), 1e-9)
            err = p - t
            g_a += err * x
            g_b += err
            h_aa += w * x * x
            h_ab += w * x
            h_bb += w
        h_aa += 1e-9
        h_bb += 1e-9
        det = h_aa * h_bb - h_ab * h_ab
        if det <= 1e-12:
            break
        step_a = (h_bb * g_a - h_ab * g_b) / det
        step_b = (h_aa * g_b - h_ab * g_a) / det
        slope -= 0.5 * step_a
        intercept -= 0.5 * step_b
        slope = max(0.0, slope)
        if abs(step_a) < 1e-10 and abs(step_b) < 1e-10:
            break
    return PlattMap(slope, intercept, len(labels), n_pos, n_neg, "platt", note)


# ----------------------------------------------------------------------
# Registry-style helpers
# ----------------------------------------------------------------------
MAP_KINDS = ("isotonic", "platt")


def fit_map(reliability: Sequence[float], correct: Sequence[int], *,
            method: str = "isotonic", note: str = ""):
    """Fit the named map; raise for an unknown method or a single-class sample."""
    if method == "isotonic":
        return fit_isotonic(reliability, correct, note=note)
    if method == "platt":
        return fit_platt(reliability, correct, note=note)
    raise ValueError(f"unknown calibration method {method!r}; expected one of {MAP_KINDS}")


def map_from_dict(obj: dict):
    """Reconstruct a stored map, validating its method and monotonicity."""
    method = obj.get("method")
    if method == "isotonic":
        return IsotonicMap.from_dict(obj)
    if method == "platt":
        return PlattMap.from_dict(obj)
    raise ValueError(f"unknown stored calibration method {method!r}")


def predict(mapping, risk_score: float) -> float:
    """Apply a stored map to a Phase E risk score."""
    return mapping.predict(reliability_input(risk_score))
