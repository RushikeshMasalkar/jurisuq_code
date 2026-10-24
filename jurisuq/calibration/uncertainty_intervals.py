"""Follow-up experiment 4: how uncertain are the Phase F numbers, really?

Phase F reports point estimates and one analytic interval (the Wald tolerance
around conformal coverage). The audit showed that two of those point estimates
are not resolvable at this sample size once the dependence structure is
respected: items are matched L1/L7 pairs within an offence topic, so item-level
resampling understates the variance.

This module provides a small, dependency-free bootstrap with two sampling units:

* ``topic`` (primary) - resample offence topics with replacement, taking every
  item of a resampled topic. This is the honest unit: legal facts, templates and
  the paired L1/L7 items are shared within a topic.
* ``item`` (secondary) - resample items with replacement. Reported because it is
  the conventional choice and because the gap between the two is itself the
  finding worth reporting.

All intervals are percentile intervals at a stated confidence. A paired gap
(``metric(a) - metric(b)``) resamples the *same* units for both arms, which is
the only correct way to interval a difference on matched data.

Nothing here writes artefacts; ``scripts/34_estimate_uncertainty.py`` persists
the report.
"""
from __future__ import annotations

import math
import random
from typing import Callable, Iterable, Sequence

DEFAULT_REPS = 4000
DEFAULT_SEED = 20261024
DEFAULT_CONFIDENCE = 0.95


def _check_aligned(*sequences: Sequence) -> int:
    lengths = {len(s) for s in sequences}
    if len(lengths) != 1:
        raise ValueError("all inputs must be aligned")
    return lengths.pop()


def normal_interval(estimate: float, standard_error: float,
                    confidence: float = DEFAULT_CONFIDENCE) -> dict:
    """Analytic normal interval, for comparison with the bootstrap."""
    if not math.isfinite(standard_error) or standard_error < 0.0:
        raise ValueError("standard error must be finite and non-negative")
    z = _z_for(confidence)
    return {"method": "normal", "estimate": estimate, "standard_error": standard_error,
            "lo": estimate - z * standard_error, "hi": estimate + z * standard_error,
            "confidence": confidence}


def wilson_interval(successes: int, n: int, confidence: float = DEFAULT_CONFIDENCE) -> dict:
    """Wilson score interval for a proportion (used for conformal coverage)."""
    if n <= 0:
        raise ValueError("n must be positive")
    if not 0 <= successes <= n:
        raise ValueError("successes must lie in [0, n]")
    z = _z_for(confidence)
    p = successes / n
    denom = 1.0 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return {"method": "wilson", "estimate": p, "n": n, "successes": successes,
            "lo": max(0.0, centre - half), "hi": min(1.0, centre + half),
            "confidence": confidence}


def _z_for(confidence: float) -> float:
    """Two-sided normal quantile via a rational approximation (no scipy)."""
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must lie strictly between 0 and 1")
    # Acklam's inverse normal CDF, adequate to ~1e-9 over this range.
    p = 1.0 - (1.0 - confidence) / 2.0
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
               ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    if p > phigh:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
               ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    q = p - 0.5
    r = q * q
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / \
           (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)


def cluster_index(groups: Sequence[str]) -> dict[str, list[int]]:
    """Map each cluster to the positions it owns."""
    if not groups:
        raise ValueError("groups must not be empty")
    clusters: dict[str, list[int]] = {}
    for position, group in enumerate(groups):
        if not isinstance(group, str) or not group:
            raise ValueError("every observation needs a non-empty cluster id")
        clusters.setdefault(group, []).append(position)
    return clusters


def _resample_indices(clusters: dict[str, list[int]], rng: random.Random,
                      unit: str) -> list[int]:
    keys = list(clusters)
    if unit == "cluster":
        drawn = [rng.choice(keys) for _ in keys]
        indices: list[int] = []
        for key in drawn:
            indices.extend(clusters[key])
        return indices
    if unit == "item":
        universe = [i for key in keys for i in clusters[key]]
        return [rng.choice(universe) for _ in universe]
    raise ValueError(f"unknown resampling unit {unit!r}; expected 'cluster' or 'item'")


def bootstrap_interval(metric: Callable[[list[int]], float | None],
                       groups: Sequence[str], *, reps: int = DEFAULT_REPS,
                       seed: int = DEFAULT_SEED, unit: str = "cluster",
                       confidence: float = DEFAULT_CONFIDENCE) -> dict:
    """Percentile bootstrap for a single metric computed on resampled positions.

    ``metric`` receives a list of source positions and returns the statistic, or
    ``None`` when that resample cannot form it.
    """
    if reps < 1:
        raise ValueError("reps must be positive")
    clusters = cluster_index(groups)
    rng = random.Random(seed)
    values: list[float] = []
    failures: list[str] = []
    for _ in range(reps):
        positions = _resample_indices(clusters, rng, unit)
        try:
            value = metric(positions)
        except (ValueError, ZeroDivisionError) as exc:
            if len(failures) < 5:
                failures.append(f"{type(exc).__name__}: {exc}")
            continue
        if value is not None and math.isfinite(value):
            values.append(float(value))
    if not values:
        raise ValueError(f"bootstrap produced no usable resamples; first failures: {failures}")
    return _summarize(values, reps=reps, seed=seed, unit=unit, confidence=confidence,
                      n_clusters=len(clusters), failures=failures)


def paired_bootstrap_interval(metric: Callable[[list[int], int], float | None],
                              groups: Sequence[str], *, reps: int = DEFAULT_REPS,
                              seed: int = DEFAULT_SEED, unit: str = "cluster",
                              confidence: float = DEFAULT_CONFIDENCE) -> dict:
    """Percentile bootstrap for ``metric(positions, 0) - metric(positions, 1)``.

    Both arms see the same resampled positions, which is what makes the interval
    a statement about the *difference* rather than about two separate numbers.
    """
    if reps < 1:
        raise ValueError("reps must be positive")
    clusters = cluster_index(groups)
    rng = random.Random(seed)
    values: list[float] = []
    for _ in range(reps):
        positions = _resample_indices(clusters, rng, unit)
        try:
            first, second = metric(positions, 0), metric(positions, 1)
        except (ValueError, ZeroDivisionError):
            continue
        if first is None or second is None:
            continue
        gap = float(first) - float(second)
        if math.isfinite(gap):
            values.append(gap)
    if not values:
        raise ValueError("paired bootstrap produced no usable resamples")
    return _summarize(values, reps=reps, seed=seed, unit=unit, confidence=confidence,
                      n_clusters=len(clusters), failures=[])


def _summarize(values: list[float], *, reps: int, seed: int, unit: str,
               confidence: float, n_clusters: int, failures: list[str]) -> dict:
    ordered = sorted(values)
    alpha = (1.0 - confidence) / 2.0
    lo = ordered[max(0, int(math.floor(alpha * (len(ordered) - 1))))]
    hi = ordered[min(len(ordered) - 1, int(math.ceil((1 - alpha) * (len(ordered) - 1))))]
    mean = sum(ordered) / len(ordered)
    variance = sum((v - mean) ** 2 for v in ordered) / max(1, len(ordered) - 1)
    return {
        "estimate_interval": [lo, hi],
        "bootstrap_mean": mean,
        "standard_error": math.sqrt(variance),
        "n_resamples_used": len(ordered),
        "n_resamples_requested": reps,
        "unit": "topic (cluster)" if unit == "cluster" else "item",
        "n_clusters": n_clusters,
        "seed": seed,
        "confidence": confidence,
        "method": "percentile bootstrap",
        "excludes_zero": (lo > 0.0) or (hi < 0.0),
        "resample_failures": failures,
        "caveat": (f"{n_clusters} clusters is few for a percentile bootstrap; read the "
                   "interval as an indication of precision, not an exact coverage claim"),
    }


def summarize_gate_stability(intervals: dict[str, dict], thresholds: dict[str, float]) -> dict:
    """Say, per metric, whether the decision is stable across the whole interval.

    A gate verdict is *stable* when every point in the interval falls on the same
    side of the threshold; otherwise the point estimate is being over-read.
    """
    out = {}
    for name, threshold in thresholds.items():
        interval = intervals.get(name)
        if not interval:
            out[name] = {"status": "not_computed", "threshold": threshold}
            continue
        lo, hi = interval["estimate_interval"]
        below = hi < threshold
        above = lo > threshold
        status = "stable_pass" if below else ("stable_fail" if above else "indeterminate")
        out[name] = {"threshold": threshold, "interval": [lo, hi], "status": status,
                     "note": ("the whole interval is on one side of the threshold"
                              if status != "indeterminate" else
                              "the interval straddles the threshold, so the point "
                              "estimate alone does not settle the gate")}
    return out
