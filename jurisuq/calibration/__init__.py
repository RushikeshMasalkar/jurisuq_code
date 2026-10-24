"""Phase F (M9/M10): calibration and the decision layer.

M9 turns the Phase E risk score into a calibrated ``p_reliable`` per stratum;
M10 turns that probability and a harm class into ``answer`` / ``verify`` /
``abstain`` with a reason string. Fitting is offline and supervised; applying
the stored maps is label-blind. Nothing here recomputes a Phase A-E quantity.
"""

from .conformal import (conformal_quantile_index, conformal_threshold,
                        coverage_tolerance, empirical_coverage)
from .evaluate import (attach_probabilities, evaluate_g6, fit_strata,
                       query_path_is_label_blind, stratum_of)
from .maps import (IsotonicMap, PlattMap, fit_isotonic, fit_map, fit_platt,
                   map_from_dict, predict, reliability_input)
from .metrics import (ace, brier, ece, harm_weight, log_loss, reliability_table,
                      risk_coverage_curve, selective_risk)
from .policy import ACTIONS, DecisionPolicy, action_census, harm_class_from_store
from .splits import cross_fitted_predictions, fold_assignment, group_key, grouped_folds

__all__ = [
    "ACTIONS", "DecisionPolicy", "IsotonicMap", "PlattMap", "ace", "action_census",
    "attach_probabilities", "brier", "conformal_quantile_index", "conformal_threshold",
    "coverage_tolerance", "cross_fitted_predictions", "ece", "empirical_coverage",
    "evaluate_g6", "fit_isotonic", "fit_map", "fit_platt", "fit_strata",
    "fold_assignment", "group_key", "grouped_folds", "harm_class_from_store",
    "harm_weight", "log_loss", "map_from_dict", "predict", "query_path_is_label_blind",
    "reliability_input", "reliability_table", "risk_coverage_curve", "selective_risk",
    "stratum_of",
]
