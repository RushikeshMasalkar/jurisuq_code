"""Follow-up experiment 2: does pooled Phase E fitting lose within-slice ranking?

Phase E (M8) fits one monotone logistic model on the pooled development
partition, which contains both slices. Within L1 the temporal factor is
constant and the common-mode score is identically zero, so the two legal
features carry no within-slice variance; a pooled fit can still spend
coefficient mass on them because they separate L1 from L7. This module fits the
same estimator restricted to one slice and compares the two on identical items.

Discipline enforced here
------------------------
* Both arms are fitted on the **development** partition only.
* Both arms are scored on the **same** eligible holdout items, selected by a
  rule that does not look at correctness labels (a record is eligible when its
  features are complete and both arms produce a finite score).
* No arm is selected on holdout performance; the comparison is pre-specified as
  "does the slice-restricted fit rank better", and the result is reported as
  found.
* Items the legal features cannot represent (the sample-only fallbacks) are
  reported separately and excluded from both arms rather than silently dropped.

Nothing here writes artefacts; ``scripts/32_compare_within_slice.py`` persists
the report.
"""
from __future__ import annotations

import math

from jurisuq.metrics import auroc
from jurisuq.uncertainty.estimator import MonotoneLogistic, fit_monotone_logistic, score_features
from jurisuq.uncertainty.features import extract_features

from .maps import fit_map, reliability_input
from .metrics import ace, brier, log_loss, selective_risk
from .splits import cross_fitted_predictions


def _finite(value) -> bool:
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(float(value)))


def features_for(records: list[dict], provision_variant: str = "exact") -> dict[str, dict]:
    """Extract Phase E components once per record (label-blind)."""
    out = {}
    for record in records:
        item_id = record.get("item_id")
        if not isinstance(item_id, str) or not item_id:
            raise ValueError("every record needs a string item_id")
        out[item_id] = extract_features(record, provision_variant=provision_variant)
    return out


def score_arm(model: MonotoneLogistic, features: dict[str, dict],
              item_ids: list[str]) -> dict[str, float]:
    """Score the given items with a fitted model; require complete features."""
    scores = {}
    for item_id in item_ids:
        extracted = features[item_id]
        if not extracted.get("legal_complete"):
            continue
        value = score_features(model, extracted["components"])
        if _finite(value):
            scores[item_id] = float(value)
    return scores


def fit_within_slice(records: list[dict], features: dict[str, dict],
                     development_ids: set[str], *, slice_name: str,
                     label_field: str = "majority_correct") -> dict:
    """Fit the Phase E estimator on one slice's development records only."""
    rows, labels, used = [], [], []
    for record in records:
        item_id = record["item_id"]
        if item_id not in development_ids or record.get("slice") != slice_name:
            continue
        extracted = features[item_id]
        if not extracted.get("legal_complete"):
            continue
        label = record.get(label_field)
        if isinstance(label, bool) or label not in (0, 1):
            raise ValueError(f"item {item_id!r} lacks binary {label_field}")
        rows.append(extracted["components"])
        labels.append(1 - int(label))  # Phase E target: error = 1
        used.append(item_id)
    if len(labels) < 10:
        raise ValueError(f"insufficient development records for slice {slice_name!r}: "
                         f"{len(labels)}")
    if len(set(labels)) < 2:
        raise ValueError(f"slice {slice_name!r} development data has one correctness class")
    model = fit_monotone_logistic(rows, labels)
    return {"model": model, "training_ids": used, "training_n": len(used),
            "training_positive": sum(labels), "training_negative": len(labels) - sum(labels)}


def _ranking(scores: dict[str, float], labels: dict[str, int]) -> dict:
    ids = [i for i in scores if i in labels]
    if len(ids) < 2:
        return {"n": len(ids), "auroc": None}
    values = [scores[i] for i in ids]
    ys = [labels[i] for i in ids]
    if len(set(ys)) < 2 or len(set(values)) < 2:
        return {"n": len(ids), "auroc": None,
                "reason": "single correctness class or constant score"}
    return {"n": len(ids), "auroc": float(auroc(values, ys)),
            "correct": sum(ys), "incorrect": len(ys) - sum(ys)}


def _downstream(development_scores: dict[str, float], development_labels: dict[str, int],
                holdout_scores: dict[str, float], holdout_labels: dict[str, int],
                *, method: str, seed: str, k: int,
                development_topics: dict[str, str]) -> dict:
    """Calibrate each arm exactly as Phase F does, then score the holdout.

    Folds stay grouped by topic so the cross-fitted development metric is
    comparable with the shipped Phase F numbers.
    """
    dev_ids = sorted(development_scores)
    if len({development_topics[i] for i in dev_ids}) < k:
        raise ValueError("fewer topics than folds in the development partition")
    records = [{"item_id": i, "slice": "L1", "topic": development_topics[i]}
               for i in dev_ids]
    dev_p, fold_report = cross_fitted_predictions(
        records, [development_labels[i] for i in dev_ids],
        [development_scores[i] for i in dev_ids], method=method, k=k, seed=seed)
    paired = [(p, development_labels[i]) for i, p in zip(dev_ids, dev_p) if p is not None]
    dev_cross_ace = ace([p for p, _ in paired], [y for _, y in paired], bins=5) if paired else None

    mapping = fit_map([reliability_input(development_scores[i]) for i in dev_ids],
                      [development_labels[i] for i in dev_ids], method=method,
                      note="follow-up experiment 2 arm")
    hold_ids = sorted(holdout_scores)
    probs = [mapping.predict(reliability_input(holdout_scores[i])) for i in hold_ids]
    ys = [holdout_labels[i] for i in hold_ids]
    return {
        "method": method,
        "development_cross_fitted_ace_5bin": dev_cross_ace,
        "holdout_ace_5bin": ace(probs, ys, bins=5),
        "holdout_brier": brier(probs, ys),
        "holdout_log_loss": log_loss(probs, ys),
        "holdout_selective_risk_at_50": selective_risk(probs, ys, 0.5)["risk"],
        "n_holdout": len(hold_ids),
        "fold_report": fold_report,
    }


def compare_within_slice(records: list[dict], development_ids: set[str],
                         holdout_ids: set[str], pooled_model: dict, *,
                         slice_name: str = "L1", provision_variant: str = "exact",
                         label_field: str = "majority_correct", method: str = "isotonic",
                         seed: str = "phaseF-v2", k: int = 5) -> dict:
    """Compare the shipped pooled fit against a slice-restricted refit."""
    features = features_for(records, provision_variant)
    labels = {r["item_id"]: int(r[label_field]) for r in records
              if r.get(label_field) in (0, 1)}
    pooled = MonotoneLogistic.from_dict(pooled_model)
    within = fit_within_slice(records, features, development_ids,
                              slice_name=slice_name, label_field=label_field)

    # Candidate holdout items: same slice, and representable by the legal features.
    candidates = [r["item_id"] for r in records
                  if r["item_id"] in holdout_ids and r.get("slice") == slice_name]
    representable = [i for i in candidates if features[i].get("legal_complete")]
    excluded = sorted(set(candidates) - set(representable))

    pooled_scores_all = score_arm(pooled, features, representable)
    within_scores_all = score_arm(within["model"], features, representable)
    # Eligibility is defined without labels: both arms must produce a finite score.
    eligible = sorted(set(pooled_scores_all) & set(within_scores_all))
    pooled_scores = {i: pooled_scores_all[i] for i in eligible}
    within_scores = {i: within_scores_all[i] for i in eligible}
    hold_labels = {i: labels[i] for i in eligible}

    dev_ids = [r["item_id"] for r in records
               if r["item_id"] in development_ids and r.get("slice") == slice_name
               and features[r["item_id"]].get("legal_complete")]
    pooled_dev = score_arm(pooled, features, dev_ids)
    within_dev = score_arm(within["model"], features, dev_ids)
    dev_common = sorted(set(pooled_dev) & set(within_dev))
    dev_labels = {i: labels[i] for i in dev_common}
    dev_topics = {r["item_id"]: r.get("topic") for r in records}

    return {
        "experiment": "E5b",
        "question": "does pooled Phase E fitting lose within-slice ranking?",
        "slice": slice_name,
        "provision_entropy_variant": provision_variant,
        # The development ids are the Phase E development split; they are not
        # repeated here, only counted, so the report stays small and stays tied
        # to the frozen split rather than to a copy of it.
        "n_phase_e_development_items": len(development_ids),
        "n_development_scored": len(dev_common),
        "n_holdout_candidates": len(candidates),
        "n_holdout_eligible": len(eligible),
        "holdout_excluded_ids": excluded,
        "holdout_exclusion_rule": ("features not complete for the legal head, so neither arm "
                                   "can score the item; reported, not dropped silently"),
        "pooled_training": {"source": "stored legal_head from the Phase E run",
                            "training_n": pooled_model.get("training_n"),
                            "training_positive": pooled_model.get("training_positive"),
                            "training_negative": pooled_model.get("training_negative"),
                            "feature_weights": dict(zip(pooled_model.get("feature_names", []),
                                                        pooled_model.get("weights", []))),
                            "fit_note": pooled_model.get("fit_note"),},
        "within_slice_training": {"training_n": within["training_n"],
                                  "training_positive": within["training_positive"],
                                  "training_negative": within["training_negative"],
                                  "feature_weights": dict(zip(within["model"].names,
                                                              within["model"].weights)),
                                  "fit_note": within["model"].fit_note},
        "ranking_on_identical_holdout_items": {
            "pooled": _ranking(pooled_scores, hold_labels),
            "within_slice": _ranking(within_scores, hold_labels),
        },
        "downstream_calibration": {
            "pooled": _downstream({i: pooled_dev[i] for i in dev_common}, dev_labels,
                                  pooled_scores, hold_labels, method=method,
                                  seed=f"{seed}|pooled", k=k,
                                  development_topics=dev_topics),
            "within_slice": _downstream({i: within_dev[i] for i in dev_common}, dev_labels,
                                        within_scores, hold_labels, method=method,
                                        seed=f"{seed}|within", k=k,
                                        development_topics=dev_topics),
        },
        "selection_note": ("the comparison is pre-specified (pooled vs slice-restricted); no "
                           "arm was chosen on holdout performance"),
        "caveats": [
            f"holdout eligible n={len(eligible)}; a difference of one item moves AUROC by "
            "roughly 0.05-0.1, so this is a signal, not a precise estimate",
            "both arms are fitted on the same development items, but the within-slice arm "
            "has fewer training rows, which trades variance for relevance",
            "no nested model selection was performed: the slice-restricted fit is the "
            "pre-specified alternative, not the winner of a search",
        ],
    }
