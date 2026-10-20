"""Phase D: the common-mode failure detector.

Decomposes the agreement among a model's own samples into the part
the legal context warrants and the part that is merely repeated.
The detector (M7) consumes the agreement statistics and the legal
context (statute store, link table, declared jurisdiction) and
emits the four-tuple ``(A, T, J, K)`` composed into the warranted
agreement ``W`` and the common-mode score ``CM = A - W``, plus the
flags that fired.  Phase E consumes the tuple and must not
recompute it.

No learning component: nothing in this subpackage imports
torch/transformers, and the detector reads no correctness label.
"""
from .detector import (EraPolicy, FLAG_CONTRADICTION, FLAG_FOREIGN,  # noqa: F401
                       FLAG_STALE, FLAG_UNRESOLVABLE, INDIAN_ACTS,
                       WarrantDetector, WarrantResult, WarrantThresholds,
                       compose)
from .validate import (binary_confusion, collision_population,  # noqa: F401
                       factor_ablation, gate_g4, group_report,
                       separation_auroc, validate)

__all__ = ["WarrantDetector", "WarrantResult", "WarrantThresholds",
           "EraPolicy", "compose", "FLAG_STALE", "FLAG_FOREIGN",
           "FLAG_CONTRADICTION", "FLAG_UNRESOLVABLE", "INDIAN_ACTS",
           "validate", "collision_population", "separation_auroc",
           "binary_confusion", "group_report", "factor_ablation",
           "gate_g4"]
