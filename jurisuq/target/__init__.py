"""Phase G: target-population construction and readiness checks for G5/G6.

The package answers one question that Phases E and F both deferred: *does an
evaluation population exist on which the existing gates can actually be
evaluated?* It does not define a new gate, score anything, or call a model.

See :mod:`jurisuq.target.population` for the documented sources of every
condition it checks.
"""

from .population import (
    DETECTOR_FIRED,
    DETECTOR_INVALID,
    DETECTOR_MISSING,
    DETECTOR_PARTIAL,
    DETECTOR_SILENT,
    STATUS_NOT_READY,
    STATUS_READY,
    confound_report,
    detector_state,
    items_needed,
    population_report,
    population_status,
    yield_report,
)

__all__ = [
    "DETECTOR_FIRED", "DETECTOR_INVALID", "DETECTOR_MISSING", "DETECTOR_PARTIAL",
    "DETECTOR_SILENT",
    "STATUS_NOT_READY", "STATUS_READY",
    "confound_report", "detector_state", "items_needed",
    "population_report", "population_status", "yield_report",
]
