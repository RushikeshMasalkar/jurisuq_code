"""Small monotone logistic estimator for Phase E (pure Python, no ML runtime)."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

from .features import BASE_FEATURES, design_vector, feature_names


def _sigmoid(z: float) -> float:
    z = max(-35.0, min(35.0, z))
    return 1.0 / (1.0 + math.exp(-z))


@dataclass(frozen=True)
class MonotoneLogistic:
    """Weights are constrained non-negative; output is an uncalibrated risk score."""
    intercept: float
    weights: tuple[float, ...]
    names: tuple[str, ...]
    trained: bool = True
    training_n: int = 0
    training_positive: int = 0
    training_negative: int = 0
    fit_note: str = ""

    def to_dict(self) -> dict:
        return {
            "intercept": self.intercept,
            "weights": list(self.weights),
            "feature_names": list(self.names),
            "monotone_nonnegative": True,
            "trained": self.trained,
            "training_n": self.training_n,
            "training_positive": self.training_positive,
            "training_negative": self.training_negative,
            "fit_note": self.fit_note,
        }

    @classmethod
    def from_dict(cls, obj: dict) -> "MonotoneLogistic":
        names = tuple(obj.get("feature_names", []))
        weights = tuple(float(x) for x in obj.get("weights", []))
        if len(names) != len(weights) or not names:
            raise ValueError("invalid model: feature_names and weights must be nonempty and aligned")
        if any(not math.isfinite(w) or w < 0 for w in weights):
            raise ValueError("invalid model: monotonicity requires finite non-negative weights")
        intercept = float(obj.get("intercept"))
        if not math.isfinite(intercept):
            raise ValueError("invalid model intercept")
        return cls(intercept, weights, names, bool(obj.get("trained", True)),
                   int(obj.get("training_n", 0)), int(obj.get("training_positive", 0)),
                   int(obj.get("training_negative", 0)), str(obj.get("fit_note", "")))


def fit_monotone_logistic(components: Sequence[dict], labels: Sequence[int],
                          *, l2: float = 0.25, learning_rate: float = 0.05,
                          epochs: int = 2500) -> MonotoneLogistic:
    """Fit projected batch logistic regression on development records only.

    All main effects and pairwise interactions have non-negative coefficients,
    so increasing any uncertainty component cannot lower the fitted score.
    The returned sigmoid is a ranking/risk score, not a calibrated probability.
    """
    if len(components) != len(labels) or not labels:
        raise ValueError("components and labels must be nonempty and have equal length")
    ys = [int(y) for y in labels]
    if any(y not in (0, 1) for y in ys):
        raise ValueError("labels must be binary 0/1")
    if len(set(ys)) < 2:
        raise ValueError("training requires both correctness classes")
    xs = [design_vector(c) for c in components]
    n_features = len(xs[0])
    if any(len(x) != n_features for x in xs):
        raise ValueError("inconsistent feature vectors")
    mean_y = sum(ys) / len(ys)
    intercept = math.log(mean_y / (1.0 - mean_y))
    weights = [0.0] * n_features
    n = len(ys)
    for _ in range(epochs):
        gi = 0.0
        gw = [0.0] * n_features
        for x, y in zip(xs, ys):
            err = _sigmoid(intercept + sum(w * v for w, v in zip(weights, x))) - y
            gi += err
            for j, v in enumerate(x):
                gw[j] += err * v
        intercept -= learning_rate * gi / n
        for j in range(n_features):
            grad = gw[j] / n + l2 * weights[j]
            weights[j] = max(0.0, weights[j] - learning_rate * grad)
    return MonotoneLogistic(
        intercept=intercept, weights=tuple(weights), names=tuple(feature_names()),
        trained=True, training_n=n, training_positive=sum(ys),
        training_negative=n - sum(ys),
        fit_note="Projected batch logistic; pairwise interactions; L2=0.25; coefficients >= 0.",
    )


def score_features(model: MonotoneLogistic, components: dict,
                   *, drop_components: Sequence[str] = ()) -> float:
    """Score features; ablation removes coefficients, never imputes nulls."""
    x = design_vector(components)
    if len(x) != len(model.weights):
        raise ValueError("model and feature schema are incompatible")
    dropped = set(drop_components)
    total = model.intercept
    for name, weight, value in zip(model.names, model.weights, x):
        factors = name.split("*")
        if any(factor in dropped for factor in factors):
            continue
        total += weight * value
    return _sigmoid(total)


def estimate(extracted: dict, model: MonotoneLogistic | None) -> dict:
    """Apply the legal-aware head or the explicit sample-only fallback.

    This function accepts feature output only, not the source record or labels.
    """
    if model is not None and model.trained and extracted.get("legal_complete"):
        return {"score": score_features(model, extracted["components"]),
                "mode": "legal_aware", "semantics": "uncalibrated_monotone_risk_score",
                "fallback_reason": None}
    fallback = extracted.get("fallback_score")
    if fallback is not None:
        reason = extracted.get("fallback_reason")
        if model is None or not model.trained:
            reason = (reason + "; " if reason else "") + "legal-aware model head unavailable"
        return {"score": fallback, "mode": "sample_only_fallback",
                "semantics": "normalized_sample_only_provision_entropy",
                "fallback_reason": reason}
    return {"score": None, "mode": "unscorable", "semantics": "undefined",
            "fallback_reason": extracted.get("fallback_reason")
                or "sample-only feature unavailable"}
