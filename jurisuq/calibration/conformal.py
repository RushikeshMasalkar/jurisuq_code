"""Split-conformal reliability thresholds for Phase F (M10).

The conformal layer supplies the property thresholds alone cannot: a finite-
sample coverage guarantee, *conditional on the stated assumptions*. The
assumption here is the standard one and it is stated rather than implied:

    calibration and evaluation items are exchangeable within a stratum

That assumption is **false in the strong form** for this benchmark: items are
matched L1/L7 pairs drawn from ten offence clusters, so items sharing a topic
are dependent, and the two slices are deliberately different populations. The
per-stratum guarantee is therefore reported as *approximate*, with the
dependency named, exactly as master-guide section 20.2 requires ("with the
exchangeability assumption stated explicitly and its failure case named").

Implementation: split-conformal with the finite-sample correction. Given ``n``
calibration reliabilities and a target coverage ``1 - alpha``, accept an item
when its reliability is at least the ``ceil((n + 1)(1 - alpha))``-th smallest
calibration value. When ``ceil((n + 1)(1 - alpha)) > n`` no finite-sample
threshold exists at that confidence, and the function returns ``None`` rather
than a number it cannot stand behind.
"""
from __future__ import annotations

import math
from typing import Sequence


def conformal_quantile_index(n: int, *, target_coverage: float) -> int | None:
    """1-based order-statistic index for the conformal threshold, or None."""
    if n <= 0:
        raise ValueError("n must be positive")
    if not 0.0 < target_coverage < 1.0:
        raise ValueError("target_coverage must lie in (0, 1)")
    alpha = 1.0 - target_coverage
    index = math.ceil((n + 1) * (1.0 - alpha))
    if index > n:
        return None
    return max(1, index)


def conformal_threshold(calibration_p: Sequence[float], *,
                        target_coverage: float) -> dict:
    """Threshold on ``p_reliable`` that accepts at least the target share.

    The nonconformity score is ``1 - p_reliable``, so the conformal order
    statistic is counted from the *bottom* of the reliability values: the
    ``ceil((n+1)(1-alpha))``-th smallest nonconformity is the ``n - k + 1``-th
    smallest reliability. Accepting items at or above that threshold rejects at
    most ``alpha`` of the calibration population, which is the guarantee.
    """
    values = sorted(float(v) for v in calibration_p)
    if any(not math.isfinite(v) or not 0.0 <= v <= 1.0 for v in values):
        raise ValueError("calibration probabilities must be finite and lie in [0, 1]")
    index = conformal_quantile_index(len(values), target_coverage=target_coverage)
    if index is None:
        return {"threshold": None, "n_calibration": len(values),
                "target_coverage": target_coverage, "index": None,
                "status": "insufficient_calibration_pairs",
                "reason": ("ceil((n+1)(1-alpha)) exceeds n, so no finite-sample "
                           "threshold exists at this target")}
    from_top = len(values) - index  # index-th largest reliability
    return {"threshold": values[from_top], "n_calibration": len(values),
            "target_coverage": target_coverage, "index": index,
            "index_from_bottom": from_top + 1, "status": "defined"}


def empirical_coverage(probabilities: Sequence[float], threshold: float | None) -> dict:
    """Share of items whose reliability clears the conformal threshold."""
    if threshold is None:
        return {"n": len(probabilities), "covered": None, "coverage": None}
    values = [float(v) for v in probabilities]
    if not values:
        return {"n": 0, "covered": None, "coverage": None}
    covered = sum(1 for v in values if v >= threshold)
    return {"n": len(values), "covered": covered, "coverage": covered / len(values)}


def coverage_tolerance(n: int, target: float, *, z: float = 1.96) -> float:
    """Sampling tolerance for an empirical coverage check (normal approximation)."""
    if n <= 0:
        return 1.0
    return z * math.sqrt(max(target * (1.0 - target), 0.0) / n)


def clopper_pearson_lower(covered: int, n: int, *, alpha: float = 0.05) -> float | None:
    """Exact one-sided lower confidence bound on a binomial proportion.

    The Wald tolerance in ``coverage_tolerance`` is the criterion the parallel
    Phase D/E work used; it is deliberately permissive at small n. This exact
    bound is reported alongside it so a reader can see how little a coverage
    of k/n really certifies when n is in the low tens.

    Returns 0.0 for ``covered == 0`` and 1.0 for ``covered == n``; ``None`` for
    an empty sample.
    """
    if n <= 0:
        return None
    if not 0 <= covered <= n:
        raise ValueError("covered must lie in [0, n]")
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha must lie in (0, 1)")
    if covered == 0:
        return 0.0
    if covered == n:
        return 1.0
    # Solve P(X >= covered | p) = alpha for p by bisection; the left side is
    # increasing in p, so a bracketed search is safe and deterministic.
    def upper_tail(p: float) -> float:
        # sum_{i=covered}^{n} C(n,i) p^i (1-p)^(n-i)
        total = 0.0
        for i in range(covered, n + 1):
            total += math.comb(n, i) * (p ** i) * ((1.0 - p) ** (n - i))
        return total

    lo, hi = 0.0, 1.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        # upper_tail is increasing in p: above the root we are too generous.
        if upper_tail(mid) > alpha:
            hi = mid
        else:
            lo = mid
    return 0.5 * (lo + hi)


def coverage_report(holdout_p: Sequence[float], calibration_p: Sequence[float], *,
                    target_coverage: float, alpha: float = 0.05,
                    calibration_source: str) -> dict:
    """Full conformal record from an explicit, out-of-sample calibration set.

    ``calibration_p`` must come from data disjoint from ``holdout_p``. Nothing
    in this function inspects correctness labels; the coverage it reports is a
    statement about the score, not about accuracy.
    """
    threshold = conformal_threshold(calibration_p, target_coverage=target_coverage)
    coverage = empirical_coverage(holdout_p, threshold["threshold"])
    tolerance = coverage_tolerance(coverage["n"], target_coverage)
    exact = (None if coverage["coverage"] is None
             else clopper_pearson_lower(coverage["covered"], coverage["n"], alpha=alpha))
    return {
        "method": "split-conformal, finite-sample corrected",
        "calibration_source": calibration_source,
        "n_calibration": threshold["n_calibration"],
        "threshold": threshold["threshold"],
        "threshold_status": threshold["status"],
        "target_coverage": target_coverage,
        "n_holdout": coverage["n"],
        "covered": coverage["covered"],
        "empirical_coverage_on_holdout": coverage["coverage"],
        "tolerance": tolerance,
        "wald_criterion_floor": target_coverage - tolerance,
        "within_tolerance": (None if coverage["coverage"] is None
                             else coverage["coverage"] >= target_coverage - tolerance),
        "clopper_pearson_lower_95": exact,
        "exact_bound_reaches_target": (None if exact is None else exact >= target_coverage),
        "calibration_disjoint_from_holdout": True,
        "exchangeability_caveat": (
            "Items are matched L1/L7 pairs from ten offence clusters; within-stratum "
            "exchangeability is approximate, so the guarantee is approximate."),
    }
