"""Grouped, deterministic cross-fitting folds for Phase F (M9).

The master guide requires grouped K-fold, grouped by offence cluster and by
slice, so the calibrator cannot memorise a topic. Grouping is therefore by
``(slice, topic)``: a group is never split across folds, and the assignment is a
pure function of the group name and the seed, so two machines get the same
folds from the same records.

This module deliberately does not read correctness labels.
"""
from __future__ import annotations

import hashlib


def group_key(record: dict) -> str:
    """Grouping key for an item: slice plus offence topic (the matched design)."""
    slice_name = record.get("slice")
    topic = record.get("topic")
    if not isinstance(slice_name, str) or not slice_name:
        raise ValueError(f"record {record.get('item_id')!r} has no slice")
    if not isinstance(topic, str) or not topic:
        raise ValueError(f"record {record.get('item_id')!r} has no topic")
    return f"{slice_name}|{topic}"


def fold_assignment(groups: list[str], *, k: int,
                    seed: str = "phaseF-v1") -> tuple[dict[str, int], int]:
    """Assign whole groups to ``k`` folds by stable hash order.

    Groups are ordered by ``sha256(seed|group)`` and dealt round-robin, which is
    deterministic and does not depend on input order. If there are fewer groups
    than folds, the effective fold count is reduced instead of creating empty
    folds, and the caller is expected to record that.
    """
    if k < 2:
        raise ValueError("k must be at least 2")
    if not groups:
        raise ValueError("at least one group is required")
    unique = sorted(set(groups))
    order = sorted(unique, key=lambda g: hashlib.sha256(f"{seed}|{g}".encode("utf-8")).hexdigest())
    effective = min(k, len(order))
    return {group: index % effective for index, group in enumerate(order)}, effective


def grouped_folds(records: list[dict], *, k: int, seed: str = "phaseF-v1") -> dict:
    """Return fold metadata plus ``item_id -> fold`` for the given records."""
    if not records:
        raise ValueError("records must not be empty")
    groups = [group_key(record) for record in records]
    mapping, effective = fold_assignment(groups, k=k, seed=seed)
    item_fold: dict[str, int] = {}
    for record, group in zip(records, groups):
        item_id = record.get("item_id")
        if not isinstance(item_id, str) or not item_id:
            raise ValueError("every record needs a string item_id")
        if item_id in item_fold:
            raise ValueError(f"duplicate item_id {item_id!r}")
        item_fold[item_id] = mapping[group]
    fold_sizes = {str(f): sum(1 for v in item_fold.values() if v == f) for f in range(effective)}
    return {"seed": seed, "requested_k": k, "effective_k": effective,
            "groups": sorted(mapping), "group_to_fold": dict(sorted(mapping.items())),
            "fold_sizes": fold_sizes, "item_fold": item_fold}


def cross_fitted_predictions(records: list[dict], labels: list[int], risk_scores: list[float],
                             *, method: str, k: int, seed: str,
                             min_train_per_fold: int = 10):
    """Out-of-fold calibrated probabilities for a development partition.

    Returns ``(predictions, fold_report)``. ``predictions`` is a list aligned to
    ``records``. A fold whose training portion lacks one correctness class is
    reported and left ``None`` rather than silently imputed.
    """
    from .maps import fit_map, reliability_input  # local import avoids a cycle

    if not (len(records) == len(labels) == len(risk_scores)):
        raise ValueError("records, labels and risk_scores must be aligned")
    folds = grouped_folds(records, k=k, seed=seed)
    by_fold = folds["item_fold"]
    predictions: list[float | None] = [None] * len(records)
    notes: list[dict] = []
    for fold in range(folds["effective_k"]):
        train_idx = [i for i, r in enumerate(records) if by_fold[r["item_id"]] != fold]
        test_idx = [i for i, r in enumerate(records) if by_fold[r["item_id"]] == fold]
        if len(train_idx) < min_train_per_fold or not test_idx:
            notes.append({"fold": fold, "status": "skipped_insufficient_training_rows",
                          "n_train": len(train_idx), "n_test": len(test_idx)})
            continue
        train_labels = [labels[i] for i in train_idx]
        if len(set(train_labels)) < 2:
            notes.append({"fold": fold, "status": "skipped_single_class_training",
                          "n_train": len(train_idx), "n_test": len(test_idx)})
            continue
        mapping = fit_map([reliability_input(risk_scores[i]) for i in train_idx],
                          train_labels, method=method, note=f"cross-fit fold {fold}")
        for i in test_idx:
            predictions[i] = mapping.predict(reliability_input(risk_scores[i]))
        notes.append({"fold": fold, "status": "fitted", "n_train": len(train_idx),
                      "n_test": len(test_idx)})
    folds = {key: value for key, value in folds.items() if key != "item_fold"}
    folds["folds"] = notes
    folds["n_cross_fitted"] = sum(1 for p in predictions if p is not None)
    return predictions, folds
