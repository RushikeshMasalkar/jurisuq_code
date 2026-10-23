"""Phase E feature extraction from Phase A and Phase D records.

This module is query-time safe: it never reads correctness labels. Missing or
unresolved legal evidence is represented as unavailable and triggers the
sample-only fallback; it is never imputed as zero.
"""
from __future__ import annotations

import math
from typing import Any

BASE_FEATURES = ("u_prov", "u_text", "u_warrant", "u_cm", "u_contra")
LEGAL_FEATURES = ("u_warrant", "u_cm", "u_contra")


def _finite_unit(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    if not math.isfinite(value) or value < 0.0 or value > 1.0:
        return None
    return value


def _normalized_entropy(methods: dict, key: str, n_samples: Any) -> float | None:
    if isinstance(n_samples, bool) or not isinstance(n_samples, int) or n_samples < 2:
        return None
    value = methods.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    denom = math.log2(n_samples)
    if not math.isfinite(value) or value < 0.0 or value > denom + 1e-8:
        return None
    return min(1.0, max(0.0, value / denom))


def extract_features(record: dict, provision_variant: str = "exact") -> dict:
    """Return explicit Phase E components and fallback provenance.

    ``u_prov`` is normalized Phase A provision-key entropy (``methods.prov_se``)
    because the shipped Phase D run uses ``exact_key`` representation and has
    no Phase B typed-cluster-statistics block. ``u_text`` is normalized
    discrete semantic entropy (``methods.disc_se``).

    Legal components are read only from Phase D outputs:
      * u_warrant = 1 - stored ``warrant_warranted_agreement``
      * u_cm = max(0, stored ``warrant_common_mode_score``)
      * u_contra = stored ``warrant_contradiction_mass``

    The subtraction and positive-part transform are the Phase E definitions;
    no A/T/J/K factors or W/CM are recomputed. A legal-aware score is supported
    only when all required stored factors and sample components are present and
    valid. Otherwise the caller must use ``u_prov`` as the sample-only fallback.
    """
    if provision_variant not in ("exact", "typed"):
        raise ValueError(f"unknown provision entropy variant: {provision_variant}")
    methods = record.get("methods")
    methods = methods if isinstance(methods, dict) else {}
    n_samples = record.get("n_samples")
    typed_stats = record.get("typed_stats")
    typed_entropy = None
    if isinstance(typed_stats, dict):
        typed_entropy = _finite_unit(typed_stats.get("entropy_norm"))
    if provision_variant == "typed" and typed_entropy is not None:
        u_prov = typed_entropy
        provision_source = "typed_stats.entropy_norm"
    else:
        u_prov = _normalized_entropy(methods, "prov_se", n_samples)
        provision_source = "methods.prov_se / log2(n_samples)"
    u_text = _normalized_entropy(methods, "disc_se", n_samples)

    reasons = []
    if u_prov is None:
        reasons.append("sample-only provision entropy is missing or invalid")
    if u_text is None:
        reasons.append("text entropy is missing or invalid")

    warranted = _finite_unit(record.get("warrant_warranted_agreement"))
    cm_raw = _finite_unit(record.get("warrant_common_mode_score"))
    contradiction = _finite_unit(record.get("warrant_contradiction_mass"))
    if warranted is None:
        reasons.append("warrant_warranted_agreement missing, null, or invalid")
    if cm_raw is None:
        reasons.append("warrant_common_mode_score missing, null, or invalid")
    if contradiction is None:
        reasons.append("warrant_contradiction_mass missing, null, or invalid")

    u_warrant = 1.0 - warranted if warranted is not None else None
    u_cm = max(0.0, cm_raw) if cm_raw is not None else None
    features = {
        "u_prov": u_prov,
        "u_text": u_text,
        "u_warrant": u_warrant,
        "u_cm": u_cm,
        "u_contra": contradiction,
    }
    legal_complete = (
        u_prov is not None and u_text is not None
        and all(features[name] is not None for name in LEGAL_FEATURES)
    )
    if u_prov is None:
        fallback_reason = "; ".join(reasons)
    elif not legal_complete:
        fallback_reason = "; ".join(reasons)
    else:
        fallback_reason = None
    return {
        "components": features,
        "legal_complete": bool(legal_complete),
        "fallback_score": u_prov,
        "fallback_reason": fallback_reason,
        "provision_entropy_source": provision_source,
        "text_entropy_source": "methods.disc_se / log2(n_samples)",
        "warrant_source": "stored Phase D warrant_* fields",
    }


def design_vector(components: dict, include: tuple[str, ...] = BASE_FEATURES) -> list[float]:
    """Build monotone logistic main effects + non-negative pair interactions."""
    vals = [components[name] for name in include]
    if any(v is None for v in vals):
        raise ValueError("cannot build a design vector with missing components")
    numeric = [float(v) for v in vals]
    out = numeric[:]
    for i in range(len(numeric)):
        for j in range(i + 1, len(numeric)):
            out.append(numeric[i] * numeric[j])
    return out


def feature_names(include: tuple[str, ...] = BASE_FEATURES) -> list[str]:
    names = list(include)
    names.extend(f"{include[i]}*{include[j]}" for i in range(len(include))
                 for j in range(i + 1, len(include)))
    return names
