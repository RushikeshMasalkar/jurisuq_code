"""Phase G: offline evaluation matrix and deployment measurement.

Two independent concerns, both specified in the engineering guide and both
offline-first:

* :mod:`jurisuq.evaluation.matrix` — the §21.2 method x slice matrix, with the
  §21.1 reporting rules (per-slice tables, judge-coverage column, undefined
  values stated with a reason) and the §12 Gate G7 check.
* :mod:`jurisuq.evaluation.deployment` — the §21.3 measurements (stage-1 and
  full-cascade latency, peak resident memory, configuration actually measured).

Nothing here calls a model. The deployment module summarises timings that a
laptop run has already recorded, and reports what has not been instrumented as
undefined rather than as an estimate.
"""

from .deployment import (
    deployment_report,
    full_cascade_latency,
    ladder_violations,
    peak_memory,
    percentile,
    stage1_latency,
    summarize_latencies,
)
from .matrix import (
    BASELINE_METHODS,
    METHODS,
    METHOD_INDEX,
    build_matrix,
    confident_wrong,
    gate_g7,
    judge_coverage,
    method_score,
    pooled_reference,
    score_cell,
)

__all__ = [
    "BASELINE_METHODS", "METHODS", "METHOD_INDEX",
    "build_matrix", "confident_wrong", "gate_g7", "judge_coverage",
    "method_score", "pooled_reference", "score_cell",
    "deployment_report", "full_cascade_latency", "ladder_violations",
    "peak_memory", "percentile", "stage1_latency", "summarize_latencies",
]
