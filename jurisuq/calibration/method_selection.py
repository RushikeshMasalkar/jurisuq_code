"""Follow-up experiment 3: which calibration map should Phase F ship?

The merged Phase F map is isotonic. The audit showed that at n=78 with a
reliability input spanning only 0.0795, isotonic has to place its end knots on a
handful of items and then clamps: every holdout item above the top knot gets the
same probability. This experiment compares the candidate maps on the development
partition, applies a *pre-registered* selection rule, and reports the holdout
metrics for every candidate so the reader can see all of them.

Discipline enforced here
------------------------
* Every map is fitted on the **development** partition only.
* The selection rule is frozen in ``configs/phase_f_followup.json`` and is a
  function of the development design (sample size, input range) - never of
  holdout accuracy.
* Holdout labels are used once, to report, and never to choose. The chosen map
  is whatever the rule names, even when another candidate happens to score
  better on the holdout.
* The constant map ("base rate") and the raw Phase E score are included as the
  two reference points. The raw score is a genuine candidate: it is monotone in
  the risk score and needs no fit at all.
* Method choice is reported with Brier and log loss alongside ACE, per the
  project rule that no map is selected on a single metric.

Nothing here writes artefacts; ``scripts/33_compare_calibration_methods.py``
persists the report.
"""
from __future__ import annotations

import math

from .maps import fit_map, reliability_input
from .metrics import ace, brier, ece, log_loss, selective_risk
from .splits import cross_fitted_predictions

CANDIDATE_METHODS = ("raw", "platt", "isotonic", "constant", "development_rate")

METHOD_DESCRIPTIONS = {
    "raw": "the Phase E risk score used directly as 1 - risk; no fitting, monotone by construction",
    "platt": "smoothed logistic map fitted on the development partition",
    "isotonic": "pool-adjacent-violators map fitted on the development partition",
    "constant": "a single probability = development positive rate, for every item",
    "development_rate": "alias of constant, kept so the report names the Phase F 'constant' baseline explicitly",
}


def _finite_unit(value) -> bool:
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(float(value)) and 0.0 <= float(value) <= 1.0)


def choose_method(development_reliability: list[float], *, n_threshold: int,
                  range_threshold: float, small_sample_method: str = "platt",
                  default_method: str = "isotonic") -> dict:
    """Apply the frozen small-sample rule to the development design only.

    The rule was written down before the holdout was scored:

        use Platt when n_development < n_threshold
                     OR (max - min) of the reliability input < range_threshold;
        otherwise isotonic.
    """
    values = [float(v) for v in development_reliability]
    if not values:
        raise ValueError("cannot choose a calibration method without development data")
    if any(not math.isfinite(v) for v in values):
        raise ValueError("development reliability inputs must be finite")
    if n_threshold < 1:
        raise ValueError("n_threshold must be positive")
    if range_threshold < 0.0:
        raise ValueError("range_threshold must be non-negative")
    spread = max(values) - min(values)
    too_few = len(values) < n_threshold
    too_narrow = spread < range_threshold
    if too_few or too_narrow:
        chosen = small_sample_method
    else:
        chosen = default_method
    reasons = []
    if too_few:
        reasons.append(f"n_development={len(values)} < {n_threshold}")
    if too_narrow:
        reasons.append(f"reliability range {spread:.4f} < {range_threshold}")
    return {
        "chosen": chosen,
        "n_development": len(values),
        "reliability_min": min(values),
        "reliability_max": max(values),
        "reliability_range": spread,
        "n_threshold": n_threshold,
        "range_threshold": range_threshold,
        "small_sample_method": small_sample_method,
        "default_method": default_method,
        "triggered_by": reasons or ["neither condition: default method applies"],
        "rule_uses_holdout_labels": False,
    }


def _score_candidate(probabilities: list[float], labels: list[int]) -> dict:
    return {
        "n": len(probabilities),
        "ace_5bin": ace(probabilities, labels, bins=5),
        "ece_10bin": ece(probabilities, labels, bins=10),
        "brier": brier(probabilities, labels),
        "log_loss": log_loss(probabilities, labels),
        "selective_risk_at_50": selective_risk(probabilities, labels, 0.5)["risk"],
    }


def compare_calibration_methods(development_scores: dict[str, float],
                                development_labels: dict[str, int],
                                holdout_scores: dict[str, float],
                                holdout_labels: dict[str, int], *,
                                development_records: list[dict] | None = None,
                                rule: dict | None = None,
                                folds: int = 5, seed: str = "phaseF-v2",
                                method_for_cross_fit: str = "isotonic") -> dict:
    """Fit every candidate on development data and report development + holdout metrics.

    ``development_scores`` and ``holdout_scores`` are Phase E *risk* scores
    (larger = more likely wrong); labels are 1 when the item is correct, the
    same orientation Phase F uses for ``P(correct)``.
    """
    rule = rule or {"n_threshold": 100, "range_threshold": 0.15}
    # Preserve the caller's record order: the grouped fold assignment is
    # order-sensitive, and reproducing the shipped cross-fit exactly matters
    # more here than a canonical ordering.
    dev_ids = [i for i in development_scores if i in development_labels]
    hold_ids = [i for i in holdout_scores if i in holdout_labels]
    if not dev_ids:
        raise ValueError("no development items with both a score and a label")
    if len(set(development_labels[i] for i in dev_ids)) < 2:
        raise ValueError("development labels contain a single class")

    dev_rel = [reliability_input(development_scores[i]) for i in dev_ids]
    dev_y = [int(development_labels[i]) for i in dev_ids]
    hold_rel = [reliability_input(holdout_scores[i]) for i in hold_ids]
    hold_y = [int(holdout_labels[i]) for i in hold_ids]
    base_rate = sum(dev_y) / len(dev_y)

    candidates: dict[str, dict] = {}
    for method in CANDIDATE_METHODS:
        entry: dict = {"description": METHOD_DESCRIPTIONS[method],
                       "fitted_on": "development partition",
                       "n_development": len(dev_rel)}

        if method == "raw":
            dev_p = list(dev_rel)
            hold_p = list(hold_rel)
            entry.update({"fitted_on": "no fit (identity on 1 - risk)", "parameters": {}})
        elif method in ("constant", "development_rate"):
            dev_p = [base_rate] * len(dev_rel)
            hold_p = [base_rate] * len(hold_rel)
            entry["parameters"] = {"base_rate": base_rate}
        else:
            mapping = fit_map(dev_rel, dev_y, method=method,
                              note=f"follow-up experiment 3 candidate: {method}")
            dev_p = [mapping.predict(r) for r in dev_rel]
            hold_p = [mapping.predict(r) for r in hold_rel]
            entry["parameters"] = mapping.to_dict()
            entry["predicts_a_single_value_above_the_top_knot"] = (
                max(hold_rel) > max(dev_rel) if method == "isotonic" else False)
            entry["n_development_above_top_knot"] = sum(1 for r in dev_rel if r == max(dev_rel))

        entry["development"] = _score_candidate(dev_p, dev_y)
        entry["holdout"] = _score_candidate(hold_p, hold_y)
        entry["holdout_saturated_at_one"] = sum(1 for p in hold_p if p >= 1.0 - 1e-12)
        entry["holdout_at_zero"] = sum(1 for p in hold_p if p <= 1e-12)
        candidates[method] = entry

    # Development cross-fitted ACE: the honest in-development estimate that
    # Phase F uses, so a candidate is not credited for fitting its own rows.
    if development_records is None:
        # Synthesize a stable grouping so the cross-fit can still run when the
        # caller passes bare score dictionaries. Ten pseudo-groups mirror the
        # ten L1 offence topics in the real data.
        development_records = [{"item_id": item_id, "slice": "L1",
                                "topic": f"group-{index % 10}"}
                               for index, item_id in enumerate(dev_ids)]
    cross_fit = {}
    for method in ("platt", "isotonic"):
        try:
            predictions, report = cross_fitted_predictions(
                development_records, dev_y, [development_scores[i] for i in dev_ids],
                # Same fold assignment for every candidate, and the same seed
                # convention as the shipped Phase F report, so the cross-fitted
                # column is a paired comparison and matches the stored figures.
                method=method, k=folds, seed=seed)
        except (ValueError, KeyError) as exc:
            cross_fit[method] = {"error": f"{type(exc).__name__}: {exc}"}
            continue
        paired = [(p, y) for p, y in zip(predictions, dev_y) if p is not None]
        cross_fit[method] = {
            "n": len(paired),
            "ace_5bin": ace([p for p, _ in paired], [y for _, y in paired], bins=5),
            "brier": brier([p for p, _ in paired], [y for _, y in paired]),
            "log_loss": log_loss([p for p, _ in paired], [y for _, y in paired]),
            "fold_report": report,
        }

    decision = choose_method(dev_rel,
                            n_threshold=rule["n_threshold"],
                            range_threshold=rule["range_threshold"],
                            small_sample_method=rule.get("small_sample_method", "platt"),
                            default_method=rule.get("default_method", "isotonic"))

    ranked = sorted((m for m in ("raw", "platt", "isotonic", "constant")
                     if candidates[m]["holdout"]["ace_5bin"] is not None),
                    key=lambda m: candidates[m]["holdout"]["ace_5bin"])
    return {
        "experiment": "E5c",
        "question": ("is isotonic the right map at this sample size, and does a "
                     "pre-registered small-sample rule agree with the evidence?"),
        "n_development": len(dev_ids),
        "n_holdout": len(hold_ids),
        "development_base_rate_correct": base_rate,
        "rule": decision,
        "candidates": candidates,
        "development_cross_fitted": cross_fit,
        "holdout_ace_ranking_best_first": ranked,
        "chosen_by_rule": decision["chosen"],
        "selection_used_holdout_labels": False,
        "honesty_note": (
            "The holdout block is reported for every candidate so nothing is hidden, "
            "but the shipped choice is 'chosen_by_rule'. Reporting a candidate that "
            "wins on holdout as the winner would be selecting on held-out labels."),
        "caveat": (
            "n_holdout is small; a single item moves ACE by ~1/n. The development "
            "cross-fitted column is the primary evidence, the holdout column is a check."),
    }


def compare_per_stratum(records: list[dict], development_ids: set[str], holdout_ids: set[str],
                        *, score_field: str = "uq_uncertainty",
                        label_field: str = "majority_correct",
                        stratum_key: str = "slice", rule: dict | None = None,
                        folds: int = 5, seed: str | None = None) -> dict:
    """Run experiment 3 within each stratum, as the Phase F gate does.

    Phase F fits and gates one map per stratum, so the method question has to be
    asked per stratum too: a pooled range can look wide while one stratum's
    range is narrow, and the small-sample rule is about the stratum that will
    actually carry the map.
    """
    seen = []
    for record in records:
        stratum = record.get(stratum_key)
        if stratum not in seen:
            seen.append(stratum)
    report: dict = {"experiment": "E5c", "stratum_key": stratum_key, "strata": {},
                    "combined_pooled": None}
    for stratum in sorted(seen):
        rows = [r for r in records if r.get(stratum_key) == stratum]
        dev_scores, dev_labels, hold_scores, hold_labels = {}, {}, {}, {}
        for record in rows:
            item_id = record.get("item_id")
            label = record.get(label_field)
            score = record.get(score_field)
            if (item_id is None or label not in (0, 1) or isinstance(label, bool)
                    or not isinstance(score, (int, float)) or isinstance(score, bool)):
                continue
            if item_id in holdout_ids:
                hold_scores[item_id], hold_labels[item_id] = float(score), int(label)
            elif item_id in development_ids:
                dev_scores[item_id], dev_labels[item_id] = float(score), int(label)
        entry = {"n_development": len(dev_scores), "n_holdout": len(hold_scores)}
        try:
            entry.update(compare_calibration_methods(
                dev_scores, dev_labels, hold_scores, hold_labels,
                development_records=[r for r in rows if r.get("item_id") in dev_scores],
                rule=rule, folds=folds, seed=f"{seed}|{stratum}"))
        except ValueError as exc:
            entry["error"] = f"{type(exc).__name__}: {exc}"
        report["strata"][stratum] = entry
    pooled_dev = {r["item_id"]: float(r[score_field]) for r in records
                  if r.get("item_id") in development_ids
                  and r.get(label_field) in (0, 1) and not isinstance(r.get(label_field), bool)
                  and isinstance(r.get(score_field), (int, float))
                  and not isinstance(r.get(score_field), bool)}
    pooled_dev_labels = {r["item_id"]: int(r[label_field]) for r in records
                         if r.get("item_id") in pooled_dev}
    pooled_hold = {r["item_id"]: float(r[score_field]) for r in records
                   if r.get("item_id") in holdout_ids
                   and r.get(label_field) in (0, 1) and not isinstance(r.get(label_field), bool)
                   and isinstance(r.get(score_field), (int, float))
                   and not isinstance(r.get(score_field), bool)}
    pooled_hold_labels = {r["item_id"]: int(r[label_field]) for r in records
                          if r.get("item_id") in pooled_hold}
    try:
        report["combined_pooled"] = compare_calibration_methods(
            pooled_dev, pooled_dev_labels, pooled_hold, pooled_hold_labels,
            development_records=[r for r in records if r.get("item_id") in pooled_dev],
            rule=rule, folds=folds, seed=f"{seed}|pooled")
        report["combined_pooled"]["note"] = (
            "pooled across strata for reference only; Phase F fits one map per stratum, "
            "so this is not the configuration that ships")
    except ValueError as exc:
        report["combined_pooled"] = {"error": f"{type(exc).__name__}: {exc}"}
    return report
