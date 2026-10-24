"""Phase G (§21.3): deployment measurements, computed honestly.

The guide's §21.3 table (p.32) asks for four things:

===============  =====================================================  ==========
Measurement      Definition                                             Purpose
===============  =====================================================  ==========
Stage-1 latency  time to produce the answer and the provision-level      the fallback a
                 score with no legal modules                            user gets
Full-cascade     sampling, relation prediction, clustering, detection,   headline
latency          estimation and decision; median and p95                 deployability
Peak resident    maximum observed working set during a query            the laptop has a
memory                                                                  hard ceiling
Configuration    model, quantisation, M, and which modules ran          a degraded
actually                                                                configuration
measured                                                                must be described
===============  =====================================================  ==========

What can and cannot be produced offline
---------------------------------------
The frozen Phase A runs store exactly two per-item timings: ``gen_latency_s``
(the M samples of one item) and ``scoring_s`` (judge, clustering and record
construction). That is the stage-1 measurement, and the project can report it
from stored artefacts today.

The other three need a laptop run against a live model:

* **full-cascade latency** — the relation model, detector, estimator and
  decision stages are timed nowhere in the frozen runs, so no number is
  derivable from them. It is reported as undefined with reason
  ``not_instrumented`` and never estimated from the Phase D/E/F wall clock.
* **peak resident memory** — not sampled anywhere. Reported as undefined.
* the **configuration actually measured** is echoed from run metadata.

Estimating any of these would be fabrication, which is why this module returns
``None`` plus a reason instead of a plausible-looking number. The laptop path is
implemented (:func:`deployment_report` accepts measured samples) so Stage 2 can
populate it without a code change.
"""
from __future__ import annotations

import math

NOT_INSTRUMENTED = "not_instrumented"
NO_DATA = "no_data"
SINGLE_SAMPLE = "single_sample"

#: The stages that make up a full cascade, in query order (§24 module list).
FULL_CASCADE_STAGES = (
    "generation",
    "relation_prediction",
    "typed_clustering",
    "detection",
    "estimation",
    "decision",
)


def percentile(values: list[float], q: float) -> float:
    """Linear-interpolated percentile, the convention used for the p95 column.

    ``q`` is a fraction in [0, 1]. Equivalent to NumPy's default ``linear``
    interpolation, stated explicitly because a p95 with a different convention
    would not be comparable with the guide's expectation.
    """
    if not values:
        raise ValueError("percentile of an empty sequence")
    if not 0.0 <= q <= 1.0:
        raise ValueError("q must lie in [0, 1]")
    ordered = sorted(float(v) for v in values)
    if len(ordered) == 1:
        return ordered[0]
    position = q * (len(ordered) - 1)
    lower = int(math.floor(position))
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def summarize_latencies(values: list[float], *, unit: str = "seconds") -> dict:
    """n, median, p95, mean, min and max for one latency measurement."""
    clean = [float(v) for v in values
             if isinstance(v, (int, float)) and not isinstance(v, bool)
             and math.isfinite(float(v)) and float(v) >= 0.0]
    if not clean:
        return {"n": 0, "median": None, "p95": None, "mean": None,
                "min": None, "max": None, "unit": unit, "undefined": NO_DATA}
    return {
        "n": len(clean),
        "median": percentile(clean, 0.5),
        "p95": percentile(clean, 0.95),
        "mean": sum(clean) / len(clean),
        "min": min(clean),
        "max": max(clean),
        "unit": unit,
        "undefined": None,
        "percentile_convention": "linear interpolation (numpy default)",
        **({"note": "a single sample cannot support a p95"}
           if len(clean) == 1 else {}),
    }


# ----------------------------------------------------------------------
# the four §21.3 measurements
# ----------------------------------------------------------------------
def stage1_latency(records: list[dict]) -> dict:
    """Answer + provision-level score, no legal modules.

    Uses the stored ``gen_latency_s`` (M samples) plus ``scoring_s`` (judge,
    clustering, provision statistics). Records missing either field are skipped
    and counted, not zero-filled.
    """
    totals: list[float] = []
    skipped = 0
    for record in records:
        generation = record.get("gen_latency_s")
        scoring = record.get("scoring_s")
        if (not isinstance(generation, (int, float)) or isinstance(generation, bool)
                or not isinstance(scoring, (int, float)) or isinstance(scoring, bool)):
            skipped += 1
            continue
        if not (math.isfinite(generation) and math.isfinite(scoring)):
            skipped += 1
            continue
        totals.append(float(generation) + float(scoring))
    block = summarize_latencies(totals)
    block.update({
        "stage": "stage-1 (generation + provision-level score)",
        "definition": "gen_latency_s + scoring_s per item, legal modules excluded",
        "n_items_skipped": skipped,
        "source": "stored Phase A run fields",
        "modules_excluded": ["relation model", "detector", "estimator", "decision"],
    })
    return block


def full_cascade_latency(measured: list[float] | None = None) -> dict:
    """Sampling through decision, median and p95.

    ``measured`` is a list of end-to-end per-query timings from a laptop run.
    Without it the measurement is undefined with an explicit reason; the frozen
    runs do not time these stages.
    """
    if measured:
        block = summarize_latencies(measured)
        block.update({"stage": "full cascade", "stages": list(FULL_CASCADE_STAGES),
                      "source": "measured on the target laptop"})
        return block
    return {
        "stage": "full cascade",
        "stages": list(FULL_CASCADE_STAGES),
        "n": 0, "median": None, "p95": None, "mean": None, "min": None, "max": None,
        "unit": "seconds",
        "undefined": NOT_INSTRUMENTED,
        "reason": ("the frozen runs time only generation and record construction; "
                   "relation, detection, estimation and decision stages are not "
                   "instrumented, so no cascade latency is derivable from them"),
        "how_to_measure": ("scripts/43_measure_deployment.py --timings <file> on the "
                           "target laptop, or --instrument during a live run"),
    }


def peak_memory(measured_mb: float | None = None, *,
                method: str | None = None) -> dict:
    """Maximum observed working set during a query.

    ``method`` must say how the peak was obtained, because a sampled high-water
    mark and a true peak are different measurements.
    """
    if measured_mb is None:
        return {
            "measurement": "peak resident memory",
            "megabytes": None,
            "undefined": NOT_INSTRUMENTED,
            "reason": "no memory sampling exists in any Phase A-F run",
            "how_to_measure": ("psutil.Process().memory_info().rss sampled during a "
                               "live query, or resource.getrusage(RUSAGE_SELF).ru_maxrss "
                               "on POSIX; record which one was used"),
        }
    if not isinstance(measured_mb, (int, float)) or isinstance(measured_mb, bool) \
            or not math.isfinite(float(measured_mb)) or measured_mb < 0:
        raise ValueError("measured_mb must be a finite non-negative number")
    return {
        "measurement": "peak resident memory",
        "megabytes": float(measured_mb),
        "method": method or "unspecified",
        "undefined": None,
        "caveat": ("a sampled RSS is a high-water approximation, not a true peak; "
                   "the report must state which was recorded"),
    }


def deployment_report(records: list[dict], *, configuration: dict,
                      full_cascade_samples: list[float] | None = None,
                      peak_mb: float | None = None,
                      peak_method: str | None = None) -> dict:
    """The §21.3 block: four measurements plus the configuration that ran."""
    if not configuration:
        raise ValueError("a configuration record is required by §21.3")
    return {
        "phase": "G",
        "section": "21.3 deployment measurements",
        "configuration_actually_measured": configuration,
        "stage1_latency": stage1_latency(records),
        "full_cascade_latency": full_cascade_latency(full_cascade_samples),
        "peak_resident_memory": peak_memory(peak_mb, method=peak_method),
        "completed_offline": ["stage1_latency", "configuration_actually_measured"],
        "requires_laptop_run": ["full_cascade_latency", "peak_resident_memory"],
        "rule": ("a degraded configuration must be described, not hidden; the report "
                 "states what ran (guide §21.3)"),
    }


# ----------------------------------------------------------------------
# §27.1 degradation ladder
# ----------------------------------------------------------------------
def ladder_violations(full_scores: list[float], degraded_scores: list[float]) -> dict:
    """Check that degradation only ever widens uncertainty (§27.1).

    The guide: "a smaller computation may widen the uncertainty and therefore
    cause more verification or abstention; it may never produce a higher
    confidence". A violation is any item whose degraded score is *lower* than
    its full-cascade score.
    """
    if len(full_scores) != len(degraded_scores):
        raise ValueError("full and degraded score lists must be aligned")
    if not full_scores:
        # nothing was run: an undefined result with a reason, not a pass
        return {
            "n": 0,
            "n_violations": None,
            "violation_indices": [],
            "monotone": None,
            "undefined": NO_DATA,
            "reason": "no paired scores were supplied, so the ladder was not applied",
            "rule": "degraded_uncertainty >= full_uncertainty for every item",
            "source": "guide §27.1 degradation ladder",
        }
    violations = [i for i, (full, degraded) in enumerate(zip(full_scores, degraded_scores))
                  if float(degraded) < float(full)]
    return {
        "n": len(full_scores),
        "n_violations": len(violations),
        "violation_indices": violations,
        "monotone": not violations,
        "rule": "degraded_uncertainty >= full_uncertainty for every item",
        "source": "guide §27.1 degradation ladder",
    }
