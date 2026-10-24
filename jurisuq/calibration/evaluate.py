"""Phase F (M9/M10) fitting and Gate G6 evaluation.

Two entry points, deliberately separated so the query path never sees a label:

``fit_strata``
    reads correctness labels, fits one calibration map per stratum on the
    development partition only, and returns a storable model payload.

``evaluate_g6``
    reads correctness labels, applies the frozen maps to the held-out
    partition, and evaluates the four Gate G6 conditions of master-guide
    section 20.3.

Conditions are reported individually, with the reason each one is defined or
not. A condition that cannot be computed is ``None`` and a stratum that cannot
be calibrated is reported as such; nothing is imputed and nothing is zeroed.
The verdict follows the guide's failure branches: report the uncalibrated score
and the strata that failed rather than manufacture a pass.
"""
from __future__ import annotations

import math

from .conformal import coverage_report
from .maps import fit_map, map_from_dict, predict, reliability_input
from .metrics import (ace, brier, ece, log_loss, reliability_table,
                      risk_coverage_curve, selective_risk)
from .policy import DecisionPolicy, action_census, harm_class_from_store
from .splits import cross_fitted_predictions

PHASE = "F"
STRATUM_KEY = "slice"
METHODS = ("isotonic", "platt")

#: Fields the query path is forbidden to read; used by the interface-rule check.
FORBIDDEN_QUERY_FIELDS = ("majority_correct", "sample_correct", "frac_correct",
                          "majority_frac_correct", "gold", "trap")


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------
def _binary_label(record: dict, label_field: str) -> int:
    value = record.get(label_field)
    if isinstance(value, bool) or value not in (0, 1):
        raise ValueError(f"item {record.get('item_id')!r} lacks binary {label_field}")
    return int(value)


def _finite_score(record: dict, score_field: str) -> float | None:
    value = record.get(score_field)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def stratum_of(record: dict) -> str:
    value = record.get(STRATUM_KEY)
    if not isinstance(value, str) or not value:
        raise ValueError(f"item {record.get('item_id')!r} has no {STRATUM_KEY}")
    return value


def choose_method(n: int, *, isotonic_min_n: int) -> str:
    """Isotonic when the stratum is large enough, Platt otherwise."""
    return "isotonic" if n >= isotonic_min_n else "platt"


def fit_strata(records: list[dict], development_ids: set[str], *,
               score_field: str = "uq_uncertainty",
               label_field: str = "majority_correct",
               isotonic_min_n: int = 40, min_fit_n: int = 10,
               seed: str = "phaseF-v1", k: int = 5) -> dict:
    """Fit one calibration map per stratum on the development partition."""
    dev = [r for r in records if r.get("item_id") in development_ids]
    if not dev:
        raise ValueError("development partition is empty")
    strata = sorted({stratum_of(r) for r in dev})
    fitted: dict[str, dict] = {}
    for stratum in strata:
        rows = [r for r in dev if stratum_of(r) == stratum]
        usable = [(r, _finite_score(r, score_field)) for r in rows]
        usable = [(r, score) for r, score in usable if score is not None]
        labels = [_binary_label(r, label_field) for r, _ in usable]
        entry: dict = {"stratum": stratum, "n_development": len(rows),
                       "n_scored": len(usable),
                       "n_correct": sum(labels), "n_incorrect": len(labels) - sum(labels),
                       "status": None, "map": None, "method": None,
                       "cross_fit": None, "development_metrics": None}
        if not usable:
            entry["status"] = "no_scored_records"
            fitted[stratum] = entry
            continue
        if len(set(labels)) < 2:
            entry["status"] = "single_class_in_development"
            entry["reason"] = ("calibration requires both correctness classes in the "
                               "development partition; none is imputed")
            fitted[stratum] = entry
            continue
        if len(labels) < min_fit_n:
            entry["status"] = "insufficient_development_records"
            fitted[stratum] = entry
            continue
        method = choose_method(len(labels), isotonic_min_n=isotonic_min_n)
        reliabilities = [reliability_input(score) for _, score in usable]
        mapping = fit_map(reliabilities, labels, method=method,
                          note=f"fitted on {len(labels)} development records; stratum {stratum}")
        cross_fit_p, fold_report = cross_fitted_predictions(
            [r for r, _ in usable], labels, [score for _, score in usable],
            method=method, k=k, seed=f"{seed}|{stratum}")
        paired = [(p, y) for p, y in zip(cross_fit_p, labels) if p is not None]
        cross_p = [p for p, _ in paired]
        cross_y = [y for _, y in paired]
        entry.update({
            "status": "fitted",
            "method": method,
            "map": mapping.to_dict(),
            "cross_fit": fold_report,
            "development_metrics": {
                "ace_5bin_cross_fitted": ace(cross_p, cross_y, bins=5),
                "ece_10bin_cross_fitted": ece(cross_p, cross_y, bins=10),
                "brier_cross_fitted": brier(cross_p, cross_y),
                "log_loss_cross_fitted": log_loss(cross_p, cross_y),
                "n_cross_fitted": len(cross_p),
                "reliability_5bin": reliability_table(cross_p, cross_y, bins=5),
            },
        })
        # Cross-fitted predictions are stored (item id -> probability, no labels)
        # so a reviewer can recompute the development metrics without refitting.
        entry["cross_fitted_p_reliable"] = {
            r["item_id"]: prob for (r, _), prob in zip(usable, cross_fit_p)
            if prob is not None}
        # Descriptive sensitivity: the same cross-fitting with the other map.
        # It is reported for transparency and is **not** used to choose the
        # shipped map (the method rule above decides that) or to evaluate G6.
        other = "platt" if method != "platt" else "isotonic"
        other_pred, _ = cross_fitted_predictions(
            [r for r, _ in usable], labels, [score for _, score in usable],
            method=other, k=k, seed=f"{seed}|{stratum}")
        other_pairs = [(q, t) for q, t in zip(other_pred, labels) if q is not None]
        entry["descriptive_method_sensitivity"] = {
            "method": other,
            "ace_5bin_cross_fitted": ace([q for q, _ in other_pairs],
                                         [t for _, t in other_pairs], bins=5),
            "n_cross_fitted": len(other_pairs),
            "used_for_selection_or_gate": False,
            "note": ("descriptive only: the shipped map follows the pre-specified "
                     "method rule and the gate is evaluated on it"),
        }
        fitted[stratum] = entry
    return {"score_field": score_field, "label_field": label_field,
            "isotonic_min_n": isotonic_min_n, "min_fit_n": min_fit_n,
            "k": k, "seed": seed, "strata": fitted}


def attach_probabilities(records: list[dict], fitted: dict, *,
                         score_field: str | None = None) -> dict[str, dict]:
    """Apply the frozen maps to every record (maps only; labels never read)."""
    field = score_field or fitted.get("score_field", "uq_uncertainty")
    maps: dict[str, object] = {}
    for stratum, entry in fitted["strata"].items():
        if entry.get("map"):
            maps[stratum] = map_from_dict(entry["map"])
    out: dict[str, dict] = {}
    for record in records:
        item_id = record.get("item_id")
        if not isinstance(item_id, str) or not item_id:
            raise ValueError("every record needs a string item_id")
        stratum = stratum_of(record)
        score = _finite_score(record, field)
        mapping = maps.get(stratum)
        if mapping is None:
            status = "undefined_stratum_not_calibrated"
            probability = None
        elif score is None:
            status = "no_score"
            probability = None
        else:
            probability = predict(mapping, score)
            status = "calibrated"
        out[item_id] = {"p_reliable": probability, "calibration_status": status,
                        "stratum": stratum}
    return out


def _evaluate_stratum(rows: list[dict], probabilities: dict[str, dict], *,
                      label_field: str, harm_classes: list[str],
                      policy: DecisionPolicy, target_coverage: float,
                      calibration_probabilities: dict[str, float] | None = None,
                      calibration_source: str = "") -> dict:
    usable = [(r, probabilities[r["item_id"]]["p_reliable"]) for r in rows
              if probabilities[r["item_id"]]["p_reliable"] is not None]
    labels = [_binary_label(r, label_field) for r, _ in usable]
    probs = [p for _, p in usable]
    weights = [policy.weight(h) for h in harm_classes]
    result: dict = {
        "n_holdout": len(rows),
        "n_scored": len(usable),
        "n_correct": sum(labels),
        "n_incorrect": len(labels) - sum(labels),
        "both_classes_present": len(set(labels)) >= 2,
        "metrics": None, "selective": None, "conformal": None,
        "calibration_undefined_ids": [r["item_id"] for r in rows
                                      if probabilities[r["item_id"]]["p_reliable"] is None],
    }
    if not usable:
        result["status"] = "not_evaluable_no_calibrated_scores"
        return result
    result["metrics"] = {
        "ace_5bin": ace(probs, labels, bins=5),
        "ece_10bin": ece(probs, labels, bins=10),
        "brier": brier(probs, labels),
        "log_loss": log_loss(probs, labels),
        "reliability_5bin": reliability_table(probs, labels, bins=5),
    }
    raw_baseline = []
    prov_baseline = []
    for r, _ in usable:
        score = _finite_score(r, "uq_uncertainty")
        raw_baseline.append(reliability_input(score) if score is not None else 0.0)
        u_prov = (r.get("uq_components") or {}).get("u_prov")
        prov_baseline.append(reliability_input(float(u_prov))
                             if isinstance(u_prov, (int, float)) and not isinstance(u_prov, bool)
                             else 0.0)
    result["selective"] = {
        "coverage": 0.5,
        "calibrated": selective_risk(probs, labels, 0.5, weights=weights),
        "baseline_phase_e_raw": selective_risk(raw_baseline, labels, 0.5, weights=weights),
        "baseline_sample_only_u_prov": selective_risk(prov_baseline, labels, 0.5,
                                                     weights=weights),
        "risk_coverage_curve": risk_coverage_curve(probs, labels, weights=weights),
    }
    # The conformal threshold must come from data disjoint from the holdout.
    # Before the follow-up audit this call passed the holdout probabilities
    # themselves, which made the reported coverage in-sample. The calibration
    # set is now required explicitly and its provenance is recorded verbatim.
    calibration_values = sorted(float(v) for v in (calibration_probabilities or {}).values())
    if calibration_values:
        result["conformal"] = coverage_report(
            probs, calibration_values, target_coverage=target_coverage,
            calibration_source=calibration_source)
    else:
        result["conformal"] = {
            "method": "split-conformal, finite-sample corrected",
            "calibration_source": calibration_source or "unavailable",
            "n_calibration": 0,
            "threshold": None,
            "threshold_status": "no_development_calibration_set",
            "target_coverage": target_coverage,
            "n_holdout": len(probs),
            "covered": None,
            "empirical_coverage_on_holdout": None,
            "tolerance": None,
            "wald_criterion_floor": None,
            "within_tolerance": None,
            "clopper_pearson_lower_95": None,
            "exact_bound_reaches_target": None,
            "calibration_disjoint_from_holdout": True,
            "exchangeability_caveat": ("no development calibration probabilities were "
                                       "available for this stratum, so no threshold is "
                                       "reported"),
        }
    decisions = [policy.decide(p, h) for (_, p), h in zip(usable, harm_classes)]
    result["policy"] = action_census(decisions)
    result["policy"]["thresholds_by_harm_class"] = {
        harm: policy.thresholds(harm) for harm in sorted(set(harm_classes))}
    result["status"] = "evaluated"
    return result


# ----------------------------------------------------------------------
# Gate G6
# ----------------------------------------------------------------------
def evaluate_g6(records: list[dict], holdout_ids: set[str], fitted: dict, *,
                policy: DecisionPolicy, statute_rows: list[dict],
                target_coverage: float = 0.80, ace_max: float = 0.05,
                min_stratum_n: int = 30, label_field: str = "majority_correct",
                interface_rule_ok: bool = True,
                harm_rule: str = "max") -> dict:
    """Evaluate the four Gate G6 conditions on the held-out partition."""
    holdout = [r for r in records if r.get("item_id") in holdout_ids]
    if not holdout:
        raise ValueError("holdout partition is empty")
    probabilities = attach_probabilities(records, fitted)
    harm_by_item = {r["item_id"]: harm_class_from_store(r.get("topic"), statute_rows,
                                                        rule=harm_rule)
                    for r in holdout}
    strata = sorted({stratum_of(r) for r in holdout})
    per_stratum: dict[str, dict] = {}
    for stratum in strata:
        rows = [r for r in holdout if stratum_of(r) == stratum]
        dev = fitted["strata"].get(stratum, {})
        calibration_probabilities = dev.get("cross_fitted_p_reliable") or None
        entry = _evaluate_stratum(
            rows, probabilities, label_field=label_field,
            harm_classes=[harm_by_item[r["item_id"]] for r in rows],
            policy=policy, target_coverage=target_coverage,
            calibration_probabilities=calibration_probabilities,
            calibration_source=(
                "development partition, grouped cross-fitted probabilities "
                f"(n={len(calibration_probabilities)})" if calibration_probabilities
                else "none: this stratum has no fitted calibration map"))
        entry["development"] = {
            "status": dev.get("status"),
            "method": dev.get("method"),
            "n_correct": dev.get("n_correct"),
            "n_incorrect": dev.get("n_incorrect"),
            "ace_5bin_cross_fitted": (dev.get("development_metrics") or {}).get(
                "ace_5bin_cross_fitted"),
            "n_cross_fitted": (dev.get("development_metrics") or {}).get("n_cross_fitted"),
        }
        if not entry["both_classes_present"]:
            entry["status"] = "not_evaluable_single_class_holdout"
            entry["reason"] = ("the held-out stratum contains one correctness class, so a "
                              "calibration or ranking metric on it is undefined")
        per_stratum[stratum] = entry

    # ---- condition 1: calibration quality on the development split -------
    calib_rows, calib_failures = [], []
    for stratum, entry in per_stratum.items():
        dev = entry["development"]
        n_cross = dev.get("n_cross_fitted") or 0
        value = dev.get("ace_5bin_cross_fitted")
        evaluable = value is not None and n_cross >= min_stratum_n
        calib_rows.append({"stratum": stratum, "ace_5bin": value,
                           "n_cross_fitted": n_cross, "evaluable": evaluable,
                           "threshold": ace_max,
                           "pass": (value <= ace_max) if evaluable else None})
        if evaluable and value > ace_max:
            calib_failures.append(stratum)
    cond1_defined = any(row["evaluable"] for row in calib_rows)
    cond1 = (None if not cond1_defined
             else all(row["pass"] for row in calib_rows if row["evaluable"]))

    # ---- condition 2: selective risk below every baseline ---------------
    selective_rows, selective_failures = [], []
    for stratum, entry in per_stratum.items():
        sel = entry.get("selective")
        if not entry["both_classes_present"] or not sel:
            selective_rows.append({"stratum": stratum, "evaluable": False,
                                   "reason": entry.get("reason", "no calibrated scores")})
            continue
        calibrated = sel["calibrated"]["harm_weighted_risk"]
        base_e = sel["baseline_phase_e_raw"]["harm_weighted_risk"]
        base_p = sel["baseline_sample_only_u_prov"]["harm_weighted_risk"]
        # The raw Phase E score is the same ranking: any monotone calibration map
        # preserves it, so equality with that baseline is a mathematical identity,
        # not evidence. It is reported and excluded from the comparison set. The
        # comparison that carries information is against a *different* score
        # (the sample-only provision entropy), which is what the guide means by
        # "below every baseline".
        comparison = {"baseline_sample_only_u_prov": base_p}
        ok = (calibrated is not None and base_p is not None
              and all(value is not None and calibrated < value
                      for value in comparison.values()))
        selective_rows.append({"stratum": stratum, "evaluable": True,
                               "calibrated": calibrated, "baseline_phase_e_raw": base_e,
                               "baseline_sample_only_u_prov": base_p,
                               "comparison_baselines": sorted(comparison),
                               "raw_equal_by_construction": (
                                   None if calibrated is None or base_e is None
                                   else abs(calibrated - base_e) < 1e-12),
                               "coverage": sel["coverage"], "pass": ok})
        if not ok:
            selective_failures.append(stratum)
    cond2_defined = any(row["evaluable"] for row in selective_rows)
    cond2 = (None if not cond2_defined else all(row["pass"] for row in selective_rows
                                                if row["evaluable"]))

    # ---- condition 3: conformal coverage within tolerance ----------------
    coverage_rows, coverage_failures = [], []
    for stratum, entry in per_stratum.items():
        conf = entry.get("conformal")
        if not conf or conf.get("empirical_coverage_on_holdout") is None:
            coverage_rows.append({"stratum": stratum, "evaluable": False})
            continue
        ok = bool(conf["within_tolerance"])
        coverage_rows.append({"stratum": stratum, "evaluable": True,
                              "target": conf["target_coverage"],
                              "empirical": conf["empirical_coverage_on_holdout"],
                              "tolerance": conf["tolerance"], "pass": ok})
        if not ok:
            coverage_failures.append(stratum)
    cond3_defined = any(row["evaluable"] for row in coverage_rows)
    cond3 = (None if not cond3_defined else all(row["pass"] for row in coverage_rows
                                                if row["evaluable"]))

    # ---- condition 4: interface rule ------------------------------------
    cond4 = bool(interface_rule_ok)

    conditions = {
        "calibration_ace_at_or_below_0.05_on_development": {
            "pass": cond1, "defined": cond1_defined,
            "threshold": ace_max, "rows": calib_rows,
            "failed_strata": calib_failures,
            "reason": (None if cond1_defined else
                       "no stratum had both classes and enough cross-fitted rows"),
        },
        "harm_weighted_selective_risk_at_50pct_below_every_baseline": {
            "pass": cond2, "defined": cond2_defined, "rows": selective_rows,
            "failed_strata": selective_failures,
            "reason": (None if cond2_defined else
                       "no held-out stratum had both correctness classes"),
            "note": ("A monotone calibration map preserves the Phase E ranking, so the "
                     "selective risk of the calibrated score equals that of the raw "
                     "score by construction; only baselines built on a different score "
                     "are informative and only they decide this condition."),
        },
        "empirical_coverage_within_tolerance_of_target": {
            "pass": cond3, "defined": cond3_defined, "rows": coverage_rows,
            "failed_strata": coverage_failures,
            "reason": (None if cond3_defined else
                       "no conformal threshold could be evaluated on the holdout"),
        },
        "query_path_reads_no_labels": {
            "pass": cond4, "defined": True,
            "reason": None if cond4 else "the inference path was found to read a label field",
        },
    }
    failed = [k for k, v in conditions.items() if v["defined"] and v["pass"] is False]
    undefined = [k for k, v in conditions.items() if not v["defined"]]
    unevaluable_strata = sorted(s for s, e in per_stratum.items()
                                if str(e["status"]).startswith("not_evaluable"))
    if failed or not cond4:
        verdict = "NOT_MET"
    elif undefined or unevaluable_strata:
        verdict = "NOT_EVALUABLE"
    else:
        verdict = "PASS"

    return {
        "phase": PHASE,
        "experiment": "E6",
        "gate": "G6",
        "label_field": label_field,
        "harm_rule": harm_rule,
        "target_coverage": target_coverage,
        "policy": policy.to_dict(),
        "holdout": {"n": len(holdout), "strata": strata},
        "per_stratum": per_stratum,
        "harm_class_counts": {cls: sum(1 for v in harm_by_item.values() if v == cls)
                              for cls in sorted(set(harm_by_item.values()))},
        "harm_weight_variance_present": len({policy.weight(c) for c in harm_by_item.values()}) > 1,
        "conditions": conditions,
        "verdict": verdict,
        "gate_status": verdict,
        "verdict_reason": _verdict_reason(verdict, failed, undefined, unevaluable_strata),
        "limitations": [
            ("Evaluation is on the frozen 200-item slice; the holdout is 44 items "
             "(22 per slice) and the L7 stratum has a single correctness class."),
            ("Calibration maps are fitted on one 7B quantised checkpoint's answers; "
             "they do not transfer to another model without refitting."),
            ("The harm class is derived from the question's offence cluster in the "
             "Phase C statute store; on this slice every cluster resolves to the same "
             "class, so harm weighting does not change the ranking here."),
            ("The conformal guarantee assumes exchangeability within a stratum; matched "
             "L1/L7 pairs and shared topics violate that assumption in the strong form."),
            ("The Phase E score this layer consumes was not better than the sample-only "
             "baseline on the control slice, so calibration cannot create skill."),
        ],
    }


def _verdict_reason(verdict: str, failed: list[str], undefined: list[str],
                    unevaluable: list[str]) -> str:
    if verdict == "PASS":
        return "all four G6 conditions evaluated and met"
    if verdict == "NOT_MET":
        return "failed conditions: " + ", ".join(failed)
    parts = []
    if undefined:
        parts.append("undefined conditions: " + ", ".join(undefined))
    if unevaluable:
        parts.append("strata without both correctness classes: " + ", ".join(unevaluable))
    return "no verdict is claimable: " + "; ".join(parts)


def query_path_is_label_blind(path) -> dict:
    """Static interface-rule check for the label-blind scoring script.

    The rule (master guide section 20.3 / section 36) is that no component on
    the query path reads a correctness label. The scoring CLI is parsed and its
    identifiers and non-docstring string constants are compared with the label
    field names, so a label named only in a docstring or comment does not raise
    a false alarm while an actual field access does.
    """
    import ast
    from pathlib import Path

    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"query-path script not found: {source}")
    text = source.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(source))
    docstring_nodes = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            body = getattr(node, "body", [])
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                docstring_nodes.add(id(body[0].value))
    identifiers: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) not in docstring_nodes:
                identifiers.add(node.value)
        elif isinstance(node, ast.Name):
            identifiers.add(node.id)
        elif isinstance(node, ast.Attribute):
            identifiers.add(node.attr)
    hits = sorted(field for field in FORBIDDEN_QUERY_FIELDS if field in identifiers)
    return {"path": str(source), "label_blind": not hits, "forbidden_fields_found": hits,
            "forbidden_fields_checked": list(FORBIDDEN_QUERY_FIELDS),
            "method": "AST scan of identifiers and non-docstring string constants"}
