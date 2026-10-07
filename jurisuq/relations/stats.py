"""Typed agreement statistics: the quantities the detector consumes.

All entropies are in bits. ``agreement`` is the modal cluster share, i.e. the
probability that two samples drawn at random fall in the same cluster, which is
the same quantity Phase A reports as ``prov_agreement`` in the exact-key case.
"""
from __future__ import annotations

import math

from .cluster_typed import ClusterResult


def entropy_bits(counts: list[int]) -> float:
    m = sum(counts)
    if m <= 0:
        return float("nan")
    return -sum((c / m) * math.log2(c / m) for c in counts if c > 0)


def normalized_entropy(counts: list[int]) -> float:
    """H in bits divided by log2(M), so that 1.0 means maximum dispersion."""
    m = sum(counts)
    if m <= 1:
        return 0.0
    return entropy_bits(counts) / math.log2(m)


def contradiction_mass(result: ClusterResult, relation: list[list[str]]) -> float:
    """Total cluster mass whose relation to the modal cluster is CONTRADICTORY."""
    m = len(result.labels)
    if m == 0:
        return float("nan")
    sizes = [len(g) for g in result.members]
    modal = max(range(len(sizes)), key=lambda k: (sizes[k], -k))
    mass = 0.0
    for ci, members in enumerate(result.members):
        if ci == modal:
            continue
        pairs = [(x, y) for x in members for y in result.members[modal]]
        if not pairs:
            continue
        contrad = sum(1 for x, y in pairs if relation[x][y] == "CONTRADICTORY")
        if contrad / len(pairs) >= 0.5:
            mass += len(members) / m
    return mass


def typed_stats(result: ClusterResult, relation: list[list[str]] | None = None,
                keys: list[str] | None = None) -> dict:
    """The statistics block written into every record and used by the detector."""
    counts = [len(g) for g in result.members]
    m = sum(counts)
    sizes = counts or [0]
    modal_idx = max(range(len(sizes)), key=lambda k: (sizes[k], -k)) if counts else -1
    out = {
        "n_clusters": len(counts),
        "counts": sorted(counts, reverse=True),
        "entropy": entropy_bits(counts),
        "entropy_norm": normalized_entropy(counts),
        "top_share": (max(counts) / m) if m else float("nan"),
        "agreement": (max(counts) / m) if m else float("nan"),
        "all_same": int(len(counts) == 1) if counts else 0,
        "canonical": result.canonical[modal_idx] if modal_idx >= 0 else "NONE",
        "merges_applied": result.merges_applied,
        "merges_skipped": result.merges_skipped,
        "forced_unions": result.forced_unions,
        "flags": list(result.flags),
    }
    if relation is not None:
        out["contradiction_mass"] = contradiction_mass(result, relation)
    if keys is not None:
        resolved = [k for k in keys if k != "NONE"]
        out["n_resolved"] = len(resolved)
        out["n_unique_keys"] = len(set(resolved))
    return out


def merge_effect(stats_exact: dict, stats_typed: dict) -> dict:
    """What typed clustering changed relative to exact-key clustering."""
    return {
        "d_agreement": stats_typed["agreement"] - stats_exact["agreement"],
        "d_entropy": stats_typed["entropy"] - stats_exact["entropy"],
        "d_n_clusters": stats_typed["n_clusters"] - stats_exact["n_clusters"],
        "collision_lost": int(stats_exact["all_same"] == 1 and stats_typed["all_same"] == 0),
    }


# ---------------------------------------------------------------------------
# classification metrics (shared by training and evaluation scripts)
# ---------------------------------------------------------------------------
def prf(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    return prec, rec, f1


def per_class(y_true: list[str], y_pred: list[str], labels: tuple[str, ...]) -> tuple[float, dict]:
    """Per-class precision/recall/F1/support and their unweighted mean (macro-F1)."""
    rows, f1s = {}, []
    for lab in labels:
        tp = sum(1 for a, b in zip(y_true, y_pred) if a == lab and b == lab)
        fp = sum(1 for a, b in zip(y_true, y_pred) if a != lab and b == lab)
        fn = sum(1 for a, b in zip(y_true, y_pred) if a == lab and b != lab)
        p_, r_, f_ = prf(tp, fp, fn)
        rows[lab] = {"precision": round(p_, 4), "recall": round(r_, 4), "f1": round(f_, 4),
                     "support": tp + fn}
        f1s.append(f_)
    return (sum(f1s) / len(f1s)) if f1s else float("nan"), rows


def macro_f1(y_true: list[str], y_pred: list[str], labels: tuple[str, ...]) -> float:
    return per_class(y_true, y_pred, labels)[0]


def confusion(y_true: list[str], y_pred: list[str], labels: tuple[str, ...]) -> dict:
    out = {a: {b: 0 for b in labels} for a in labels}
    for a, b in zip(y_true, y_pred):
        if a in out and b in out[a]:
            out[a][b] += 1
    return out


def exact_key_baseline(records, merge_relations) -> float:
    """The Phase A rule expressed as a classifier: same asserted key merges, an
    explicitly crosswalked pair merges, everything else splits."""
    from .schema import OPERATIONAL

    y_true, y_pred = [], []
    for r in records:
        ka, kb = r.key_a(), r.key_b()
        if ka == kb and ka != "NONE":
            pred = "SAME_PROVISION"
        elif r.context.get("crosswalk_relation") in ("successor_of", "merged_into"):
            pred = "LEGALLY_EQUIVALENT"
        elif ka == "NONE" or kb == "NONE":
            pred = "AMBIGUOUS"
        else:
            pred = "DIFFERENT_PROVISION"
        y_true.append(r.label)
        y_pred.append(pred)
    return macro_f1(y_true, y_pred, OPERATIONAL)
