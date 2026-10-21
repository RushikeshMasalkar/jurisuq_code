"""Phase E (M8): legal-aware uncertainty estimation.

The score layer consumes stored Phase D warrant fields; it does not run or
reimplement the warrant detector. Correctness labels are confined to model
fitting and offline validation, never feature extraction or scoring.
"""

from .features import extract_features
from .estimator import MonotoneLogistic, estimate, fit_monotone_logistic, score_features

__all__ = ["extract_features", "MonotoneLogistic", "estimate", "fit_monotone_logistic", "score_features"]
