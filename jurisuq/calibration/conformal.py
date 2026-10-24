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
