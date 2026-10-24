"""Phase G (§21.2): the offline evaluation matrix.

The guide defines Phase G as the phase that produces "the tables a reviewer will
read first" (§21, p.32). This module builds those tables from stored records: a
matrix of *uncertainty method x slice*, with every metric the guide lists and an
explicit reason wherever a number cannot be computed.

Sources of the requirements implemented here
--------------------------------------------
§21.1 (p.32), the structural requirement:

* both correctness classes on every evaluated slice;
* slices reported separately, with a pooled number only alongside both;
* judge coverage reported per slice, as a column and not a footnote;
* undefined values printed as undefined, with the reason named.

§21.2 (p.32), the evaluation matrix:

* methods: exact agreement, lexical similarity, discrete semantic entropy,
  standard semantic entropy, SelfCheck-style, ``p_true`` where available,
  provision-level agreement, the legal-aware score, and the legal-aware score
  without calibration;
* metrics: AUROC, AUPRC, nAURC, selective risk at fixed coverage, ACE, ECE,
  Brier score, reliability diagrams, abstention rate, harm-weighted risk;
* metric discipline: AUROC always detects incorrect answers from an uncertainty
  score, so larger is better; a confident wrong prediction is an item whose
  returned answer is wrong *and* whose uncertainty is in the lowest quartile;
  the correctness label is the judge's verdict on the returned (modal) answer,
  never on an individual sample.

§12 (p.19) defines the gate this matrix exists to satisfy:

    G7: the target slice carries both correctness classes and the headline
        comparison is computable.
    Fails when: no target slice exists on which a ranking is defined.

Design rules
------------
1. **Nothing is imputed.** A metric that cannot be computed is ``None`` with a
   reason code in ``undefined``. ``jurisuq.uncertainty.io.write_json`` uses
   ``allow_nan=False``, so a stray NaN raises at the report boundary instead of
   being written out.
2. **A single-class population has no ranking metric.** Per §21.1 a ranking
   metric needs both classes, so AUROC/AUPRC/nAURC/selective risk are all
   reported as undefined rather than as a degenerate 1.0 (AUPRC is trivially
   1.0 when every item is incorrect, which is not a measurement).
3. **Calibration metrics need a probability.** ACE/ECE/Brier/reliability are
   computed on ``p_reliable = 1 - u`` and therefore only when the score already
   lies in [0, 1]. An entropy in bits is a ranking signal, not a probability;
   reporting its ACE would be a category error.
4. **Slices are never pooled by default.** :func:`build_matrix` returns one block
   per slice. :func:`pooled_reference` exists but refuses unless both slices are
   present and tags the block as reference-only.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from ..calibration.metrics import (
    ace,
    brier,
    ece as calibration_ece,
    harm_weight,
    reliability_table,
    selective_risk,
)
from ..metrics import auprc, auroc, normalized_aurc, risk_coverage

#: §21.2 says "selective risk at fixed coverage". The project already fixes this
#: at 0.5 in ``configs/phase_f_calibration.json`` (``gates.selective_coverage``),
#: so the matrix uses the same value rather than inventing a second one.
FIXED_COVERAGE = 0.5
ACE_BINS = 5
ECE_BINS = 10
RELIABILITY_BINS = 5
CONFIDENT_QUARTILE = 0.25

# ----------------------------------------------------------------------
# reason codes for an undefined value
# ----------------------------------------------------------------------
NO_RECORDS = "no_records"
NO_SCORED_ITEMS = "no_items_with_a_score_and_a_label"
SINGLE_CLASS = "single_correctness_class"
CONSTANT_SCORE = "constant_score"
METHOD_UNAVAILABLE = "method_not_implemented"
LOGPROBS_ABSENT = "logprobs_absent"
OUTSIDE_UNIT_INTERVAL = "score_outside_unit_interval"
HARM_ABSENT = "harm_class_absent"
DEGENERATE = "degenerate_label_distribution"

#: Short forms for the printed table, so a reason never overflows its column.
SHORT_REASONS = {
    SINGLE_CLASS: "single_class",
    METHOD_UNAVAILABLE: "unimplemented",
    LOGPROBS_ABSENT: "no_logprobs",
    NO_SCORED_ITEMS: "no_scores",
    NO_RECORDS: "no_records",
    CONSTANT_SCORE: "constant",
    OUTSIDE_UNIT_INTERVAL: "not_a_prob",
    HARM_ABSENT: "no_harm_class",
    DEGENERATE: "degenerate",
}


# ----------------------------------------------------------------------
# the nine methods of §21.2
# ----------------------------------------------------------------------
@dataclass(frozen=True)
class MethodSpec:
    """One row of the §21.2 method axis."""

    key: str
    guide_name: str
    source: str
    implemented: bool = True
    note: str = ""


#: Order follows the guide's sentence, so a reader can check the matrix against
#: the specification line by line.
METHODS: tuple[MethodSpec, ...] = (
    MethodSpec(
        key="exact_agreement",
        guide_name="exact agreement",
        source="methods.agreement = 1 - top discrete-cluster probability",
        note="larger = less agreement = more uncertain"),
    MethodSpec(
        key="lexical_similarity",
        guide_name="lexical similarity",
        source="not implemented as a standalone score",
        implemented=False,
        note=("the lexical proxy is the *entailment backend* behind "
              "standard semantic entropy and is recorded there; it is not a "
              "separate uncertainty score in this codebase")),
    MethodSpec(
        key="discrete_semantic_entropy",
        guide_name="discrete semantic entropy",
        source="methods.disc_se (bits)"),
    MethodSpec(
        key="standard_semantic_entropy",
        guide_name="standard semantic entropy",
        source="methods.se (bits)"),
    MethodSpec(
        key="selfcheck",
        guide_name="SelfCheck-style",
        source="methods.selfcheck (contradiction mass)"),
    MethodSpec(
        key="p_true",
        guide_name="p_true where available",
        source="methods.p_true, stored as 1 - length-normalised sequence probability",
        note="requires server logprobs; absent on the frozen run"),
    MethodSpec(
        key="provision_agreement",
        guide_name="provision-level agreement",
        source="methods.prov_agreement = 1 - provision top share"),
    MethodSpec(
        key="legal_aware",
        guide_name="legal-aware score (this work)",
        source="1 - p_reliable from the Phase F calibration run",
        note="the calibrated form; equals 1 - uq_uncertainty where p_reliable is null"),
    MethodSpec(
        key="legal_aware_uncalibrated",
        guide_name="legal-aware score without calibration",
        source="uq_uncertainty (Phase E, uncalibrated_monotone_risk_score)"),
)

METHOD_INDEX = {spec.key: spec for spec in METHODS}

#: Which methods count as the project's own contribution, for the G7 headline
#: comparison. Everything else is a published-style baseline.
LEGAL_AWARE_METHODS = ("legal_aware", "legal_aware_uncalibrated")
BASELINE_METHODS = tuple(spec.key for spec in METHODS
                         if spec.key not in LEGAL_AWARE_METHODS and spec.implemented)


# ----------------------------------------------------------------------
# score extraction
# ----------------------------------------------------------------------
def _finite(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def _unit(value) -> float | None:
    value = _finite(value)
    if value is None or value < 0.0 or value > 1.0:
        return None
    return value


def method_score(record: dict, key: str) -> float | None:
    """Extract one method's uncertainty for one record, or ``None``.

    Every value returned here is oriented so that **larger means more
    uncertain**, which is the orientation §21.2 fixes for the whole matrix.
    """
    if key not in METHOD_INDEX:
        raise ValueError(f"unknown uncertainty method {key!r}")

    if key == "legal_aware":
        p_reliable = _unit(record.get("p_reliable"))
        return None if p_reliable is None else 1.0 - p_reliable
    if key == "legal_aware_uncalibrated":
        return _finite(record.get("uq_uncertainty"))
    if key == "lexical_similarity":
        return None

    methods = record.get("methods")
    methods = methods if isinstance(methods, dict) else {}
    field = {
        "exact_agreement": "agreement",
        "discrete_semantic_entropy": "disc_se",
        "standard_semantic_entropy": "se",
        "selfcheck": "selfcheck",
        "p_true": "p_true",
        "provision_agreement": "prov_agreement",
    }[key]
    value = _finite(methods.get(field))
    if key == "p_true" and value is not None:
        # pipeline stores p_true already as 1 - mean sequence probability, so it
        # is already an uncertainty. Documented rather than silently reused.
        return value
    return value


def _label(record: dict) -> int | None:
    """The correctness label: the judge's verdict on the modal answer (§21.2)."""
    value = record.get("majority_correct")
    if isinstance(value, bool) or value not in (0, 1):
        return None
    return int(value)


def judge_coverage(records: list[dict]) -> dict:
    """Per §21.1: the coverage column, not a footnote.

    Item coverage is the share of items with a resolved correctness label.
    Sample coverage is reported too, because the label is derived from samples
    and a run can resolve every item while leaving some samples unresolved.
    """
    items = len(records)
    resolved = sum(1 for r in records if _label(r) is not None)
    sample_total = sample_resolved = 0
    for record in records:
        labels = record.get("sample_verdict_labels")
        if isinstance(labels, list) and labels:
            sample_total += len(labels)
            sample_resolved += sum(1 for lab in labels
                                   if isinstance(lab, str) and lab != "unresolved")
    return {
        "n_items": items,
        "n_items_resolved": resolved,
        "item_coverage": (resolved / items) if items else None,
        "n_samples": sample_total,
        "n_samples_resolved": sample_resolved,
        "sample_coverage": (sample_resolved / sample_total) if sample_total else None,
        "definition": "item coverage = resolved correctness labels / items",
    }


# ----------------------------------------------------------------------
# one cell
# ----------------------------------------------------------------------
def _quartile(values: list[float], q: float) -> float:
    """Linear-interpolated quantile of an already-ordered list."""
    if not values:
        raise ValueError("no values")
    if len(values) == 1:
        return values[0]
    position = q * (len(values) - 1)
    lower = int(math.floor(position))
    upper = min(lower + 1, len(values) - 1)
    weight = position - lower
    return values[lower] * (1 - weight) + values[upper] * weight


def confident_wrong(uncertainty: list[float], correct: list[int]) -> dict:
    """§21.2: wrong answer whose uncertainty is in the lowest quartile.

    Returns the count, the rate among the quartile, and the threshold used.
    ``None`` when the population cannot support a quartile.
    """
    n = len(uncertainty)
    if n < 4:
        return {"n": n, "n_confident": None, "n_confident_wrong": None,
                "rate": None, "threshold": None,
                "undefined": "population_too_small_for_a_quartile"}
    order = sorted(uncertainty)
    threshold = _quartile(order, CONFIDENT_QUARTILE)
    in_quartile = [i for i, u in enumerate(uncertainty) if u <= threshold]
    wrong = sum(1 for i in in_quartile if correct[i] == 0)
    return {
        "n": n,
        "n_confident": len(in_quartile),
        "n_confident_wrong": wrong,
        "rate": (wrong / len(in_quartile)) if in_quartile else None,
        "threshold": threshold,
        "definition": ("wrong and uncertainty <= the 25th percentile of the "
                       "evaluated population"),
        "undefined": None,
    }


def score_cell(records: list[dict], method_key: str, *,
               coverage: float = FIXED_COVERAGE,
               harm_class_of: dict[str, str] | None = None) -> dict:
    """All §21.2 metrics for one (method, slice) cell.

    ``records`` must already be restricted to one slice: this function never
    pools, and takes a single slice's rows so that a pooled cell cannot be built
    by accident.
    """
    spec = METHOD_INDEX[method_key]
    coverage_block = judge_coverage(records)
    undefined: dict[str, str] = {}

    uncertainty: list[float] = []
    correct: list[int] = []
    weights: list[float] = []
    harm_classes: set[str] = set()
    for record in records:
        label = _label(record)
        if label is None:
            continue
        score = method_score(record, method_key)
        if score is None:
            continue
        uncertainty.append(score)
        correct.append(label)
        harm_class = (harm_class_of or {}).get(record.get("item_id"),
                                               record.get("harm_class"))
        if harm_class:
            harm_classes.add(harm_class)
        weights.append(harm_weight(harm_class) if harm_class else None)

    n_scored = len(uncertainty)
    cell: dict = {
        "method": method_key,
        "guide_name": spec.guide_name,
        "source": spec.source,
        "note": spec.note,
        "n_items": coverage_block["n_items"],
        "n_scored": n_scored,
        "judge_coverage": coverage_block,
        "metrics": {},
        "undefined": undefined,
    }
    metrics = cell["metrics"]

    if not spec.implemented:
        undefined["all"] = METHOD_UNAVAILABLE
        cell["metrics"] = {k: None for k in _METRIC_KEYS}
        return cell
    if n_scored == 0:
        reason = (LOGPROBS_ABSENT if method_key == "p_true" else NO_SCORED_ITEMS)
        undefined["all"] = reason
        cell["metrics"] = {k: None for k in _METRIC_KEYS}
        return cell

    n_correct = sum(correct)
    n_incorrect = n_scored - n_correct
    both_classes = n_correct > 0 and n_incorrect > 0
    constant = len(set(uncertainty)) == 1
    metrics["base_error_rate"] = n_incorrect / n_scored

    # ---- ranking metrics: need both classes and a non-constant score ----
    if not both_classes:
        for name in ("auroc", "auprc", "normalized_aurc",
                     "selective_risk_at_fixed_coverage",
                     "risk_coverage_at_fixed"):
            metrics[name] = None
            undefined[name] = SINGLE_CLASS
    elif constant:
        # With one distinct score, "the lowest 50%" is decided by the sort's
        # tie-break, not by the method. Any number here would be an artefact of
        # input order, so the selective risk is undefined too; the base error
        # rate stands in for it and is reported as its own, honest field.
        for name in ("auroc", "auprc", "normalized_aurc",
                     "selective_risk_at_fixed_coverage",
                     "risk_coverage_at_fixed"):
            metrics[name] = None
            undefined[name] = CONSTANT_SCORE
        metrics["base_error_rate"] = n_incorrect / n_scored
    else:
        metrics["auroc"] = _clean(auroc(uncertainty, correct), undefined, "auroc")
        metrics["auprc"] = _clean(
            auprc(uncertainty, [1 - c for c in correct]), undefined, "auprc")
        metrics["normalized_aurc"] = _clean(
            normalized_aurc(correct, uncertainty), undefined, "normalized_aurc")
        metrics["selective_risk_at_fixed_coverage"] = _risk(uncertainty, correct, coverage)
        metrics["risk_coverage_at_fixed"] = {"coverage": coverage}

    # ---- calibration metrics: only for a probability-like score ----
    unit_interval = all(0.0 <= u <= 1.0 for u in uncertainty)
    p_reliable = [1.0 - u for u in uncertainty]
    if not unit_interval:
        for name in ("ace_5bin", "ece_10bin", "brier", "reliability_5bin",
                     "harm_weighted_risk_at_fixed_coverage"):
            metrics[name] = None
            undefined[name] = OUTSIDE_UNIT_INTERVAL
    elif not both_classes:
        for name in ("ace_5bin", "ece_10bin", "brier", "harm_weighted_risk_at_fixed_coverage"):
            metrics[name] = None
            undefined[name] = SINGLE_CLASS
        metrics["reliability_5bin"] = reliability_table(p_reliable, correct,
                                                       bins=RELIABILITY_BINS)
    else:
        metrics["ace_5bin"] = _clean(ace(p_reliable, correct, bins=ACE_BINS),
                                     undefined, "ace_5bin")
        metrics["ece_10bin"] = _clean(calibration_ece(p_reliable, correct, bins=ECE_BINS),
                                      undefined, "ece_10bin")
        metrics["brier"] = _clean(brier(p_reliable, correct), undefined, "brier")
        metrics["reliability_5bin"] = reliability_table(p_reliable, correct,
                                                       bins=RELIABILITY_BINS)
        if any(w is None for w in weights):
            metrics["harm_weighted_risk_at_fixed_coverage"] = None
            undefined["harm_weighted_risk_at_fixed_coverage"] = HARM_ABSENT
        else:
            block = selective_risk(p_reliable, correct, coverage, weights=weights)
            metrics["harm_weighted_risk_at_fixed_coverage"] = block["harm_weighted_risk"]
            metrics["harm_weight_variation_present"] = len(harm_classes) > 1
            cell["harm_classes"] = sorted(harm_classes)

    # ---- §21.2 confident-wrong definition ----
    metrics["confident_wrong"] = confident_wrong(uncertainty, correct)
    metrics["label_counts"] = {"correct": n_correct, "incorrect": n_incorrect}
    metrics["score_range"] = {"min": min(uncertainty), "max": max(uncertainty)}
    return cell


_METRIC_KEYS = (
    "auroc", "auprc", "normalized_aurc", "selective_risk_at_fixed_coverage",
    "ace_5bin", "ece_10bin", "brier", "reliability_5bin",
    "harm_weighted_risk_at_fixed_coverage", "confident_wrong", "label_counts",
    "risk_coverage_at_fixed", "score_range", "base_error_rate",
)


def _risk(uncertainty: list[float], correct: list[int], coverage: float) -> float:
    """Selective risk at a fixed coverage, from the project's own curve."""
    curve = risk_coverage(correct, uncertainty, coverages=[coverage])
    return curve["at"][coverage]["risk"]


def _clean(value, undefined: dict, name: str):
    """Store a metric or record why it is undefined. NaN never survives.

    The project's metric functions return NaN when a quantity has no definition
    on the population (one correctness class, no skill range to normalise
    against). That becomes ``None`` plus ``degenerate_label_distribution`` here;
    the caller has already handled the explicit single-class cases above.
    """
    if value is None:
        undefined[name] = DEGENERATE
        return None
    value = float(value)
    if not math.isfinite(value):
        undefined[name] = DEGENERATE
        return None
    return value


# ----------------------------------------------------------------------
# the matrix
# ----------------------------------------------------------------------
def build_matrix(records: list[dict], *, slices: tuple[str, ...] | list[str] = ("L1", "L7"),
                 methods: tuple[str, ...] | list[str] | None = None,
                 harm_class_of: dict[str, str] | None = None,
                 coverage: float = FIXED_COVERAGE) -> dict:
    """Per-slice method x metric matrix. **Never pools.**

    Returns a dict with one block per slice; a missing slice is reported as
    absent rather than as an empty table.
    """
    if not records:
        raise ValueError("build_matrix requires records")
    if coverage <= 0.0 or coverage > 1.0:
        raise ValueError("coverage must lie in (0, 1]")
    method_keys = tuple(methods or [spec.key for spec in METHODS])
    unknown = [key for key in method_keys if key not in METHOD_INDEX]
    if unknown:
        raise ValueError(f"unknown uncertainty method(s): {unknown}")

    present = {r.get("slice") for r in records if r.get("slice")}
    blocks: dict[str, dict] = {}
    for slice_name in slices:
        rows = [r for r in records if r.get("slice") == slice_name]
        if not rows:
            blocks[slice_name] = {"slice": slice_name, "present": False,
                                  "cells": {}, "judge_coverage": None}
            continue
        blocks[slice_name] = {
            "slice": slice_name,
            "present": True,
            "n_items": len(rows),
            "judge_coverage": judge_coverage(rows),
            "label_counts": {
                "correct": sum(1 for r in rows if _label(r) == 1),
                "incorrect": sum(1 for r in rows if _label(r) == 0),
                "unresolved": sum(1 for r in rows if _label(r) is None),
            },
            "cells": {key: score_cell(rows, key, coverage=coverage,
                                      harm_class_of=harm_class_of)
                      for key in method_keys},
        }

    return {
        "phase": "G",
        "section": "21.2 evaluation matrix",
        "coverage_for_selective_risk": coverage,
        "bins": {"ace": ACE_BINS, "ece": ECE_BINS, "reliability": RELIABILITY_BINS},
        "slices_evaluated": list(slices),
        "slices_present_in_data": sorted(p for p in present if p),
        "slices_absent": [s for s in slices if not blocks[s]["present"]],
        "pooled": None,
        "pooling_note": ("no pooled block is computed; §21.1 requires slices to be "
                         "reported separately. See pooled_reference() if one is "
                         "needed for reference."),
        "blocks": blocks,
        "method_order": list(method_keys),
    }


def pooled_reference(records: list[dict], *,
                     slices: tuple[str, ...] | list[str] = ("L1", "L7"),
                     methods: tuple[str, ...] | list[str] | None = None,
                     harm_class_of: dict[str, str] | None = None) -> dict:
    """A pooled block that may never be reported alone (§21.1).

    Refuses unless **both** slices are present, because the guide permits a
    pooled number only alongside both of its constituents.
    """
    present = {r.get("slice") for r in records if r.get("slice")}
    missing = [s for s in slices if s not in present]
    if missing:
        raise ValueError(f"cannot pool: slice(s) absent from the data: {missing}")
    matrix = build_matrix(records, slices=slices, methods=methods,
                          harm_class_of=harm_class_of)
    pooled_cells = {}
    for key in (methods or [spec.key for spec in METHODS]):
        uncertainty, correct = [], []
        for record in records:
            label = _label(record)
            score = method_score(record, key)
            if label is None or score is None:
                continue
            uncertainty.append(score)
            correct.append(label)
        pooled_cells[key] = _metrics_only(uncertainty, correct, key)
    return {
        "phase": "G",
        "pooled_for_reference_only": True,
        "may_not_be_reported_alone": True,
        "reason": ("§21.1: pooling the control and target slices would average away "
                   "the effect being measured; this block exists only to be shown "
                   "beside the per-slice tables"),
        "slices_pooled": list(slices),
        "n_items": len(records),
        "cells": pooled_cells,
        "per_slice_present": {s: matrix["blocks"][s]["present"] for s in slices},
    }


def _metrics_only(uncertainty: list[float], correct: list[int], key: str) -> dict:
    """Ranking metrics for an already-extracted population (used by pooling)."""
    if not uncertainty:
        return {"n_scored": 0, "auroc": None, "undefined": NO_SCORED_ITEMS}
    n_correct = sum(correct)
    if n_correct == 0 or n_correct == len(correct):
        return {"n_scored": len(uncertainty), "auroc": None, "undefined": SINGLE_CLASS}
    return {
        "n_scored": len(uncertainty),
        "auroc": float(auroc(uncertainty, correct)),
        "confident_wrong": confident_wrong(uncertainty, correct),
    }


# ----------------------------------------------------------------------
# G7 (guide §12, p.19)
# ----------------------------------------------------------------------
def gate_g7(matrix: dict) -> dict:
    """Evaluate G7 as the guide states it.

    Guide text: *"G7: the target slice carries both correctness classes and the
    headline comparison is computable"*, failing when *"no target slice exists
    on which a ranking is defined"*.

    Two of the four conditions below are direct restatements. The third is an
    operationalisation that is stated explicitly rather than assumed:
    "the headline comparison is computable" is read as *for each evaluated slice,
    at least one legal-aware method and at least one baseline method have a
    defined AUROC*, because a comparison needs both sides.
    """
    blocks = matrix.get("blocks") or {}
    evaluated = [s for s, b in blocks.items() if b.get("present")]
    if not evaluated:
        return {"gate": "G7", "status": "NOT_EVALUABLE",
                "reason": "no slice present in the data", "conditions": {}}

    conditions: dict[str, dict] = {}
    slice_detail: dict[str, dict] = {}
    for slice_name in evaluated:
        block = blocks[slice_name]
        counts = block.get("label_counts") or {}
        both = counts.get("correct", 0) > 0 and counts.get("incorrect", 0) > 0
        cells = block.get("cells") or {}
        legal_defined = [k for k in LEGAL_AWARE_METHODS
                         if (cells.get(k) or {}).get("metrics", {}).get("auroc") is not None]
        baseline_defined = [k for k in BASELINE_METHODS
                            if (cells.get(k) or {}).get("metrics", {}).get("auroc") is not None]
        comparable = bool(legal_defined) and bool(baseline_defined)
        slice_detail[slice_name] = {
            "correct": counts.get("correct"), "incorrect": counts.get("incorrect"),
            "unresolved": counts.get("unresolved"),
            "both_classes": both,
            "legal_aware_methods_with_auroc": legal_defined,
            "baseline_methods_with_auroc": baseline_defined,
            "headline_comparison_computable": comparable,
            "reason": None if both else SINGLE_CLASS,
        }

    conditions["both_classes_on_every_evaluated_slice"] = {
        "met": all(d["both_classes"] for d in slice_detail.values()),
        "detail": {s: d["both_classes"] for s, d in slice_detail.items()},
        "source": "guide §21.1 and §12 (G7); PHASE-E §7.4",
    }
    conditions["headline_comparison_computable"] = {
        "met": all(d["headline_comparison_computable"] for d in slice_detail.values()),
        "detail": {s: d["headline_comparison_computable"] for s, d in slice_detail.items()},
        "source": "guide §12 (G7), operationalised as: a legal-aware method and a "
                  "baseline both have a defined AUROC on that slice",
    }
    conditions["judge_coverage_reported_per_slice"] = {
        "met": all((blocks[s].get("judge_coverage") or {}).get("item_coverage") is not None
                   for s in evaluated),
        "detail": {s: (blocks[s].get("judge_coverage") or {}).get("item_coverage")
                   for s in evaluated},
        "source": "guide §21.1",
    }
    undefined_stated = all(
        (cell.get("metrics", {}).get("auroc") is not None)
        or ("auroc" in (cell.get("undefined") or {}) or "all" in (cell.get("undefined") or {}))
        for s in evaluated for cell in (blocks[s].get("cells") or {}).values())
    conditions["undefined_values_stated_with_reason"] = {
        "met": undefined_stated,
        "detail": "every undefined AUROC carries a reason code",
        "source": "guide §21.1",
    }

    met = all(c["met"] for c in conditions.values())
    target = [s for s in evaluated if s in ("L7",)]
    target_failed = bool(target) and not slice_detail[target[0]]["both_classes"]
    status = "MET" if met else ("NOT_MET" if target_failed else "NOT_MET")
    return {
        "gate": "G7",
        "status": status,
        "guide_text": ("G7: the target slice carries both correctness classes and "
                       "the headline comparison is computable"),
        "guide_fail_condition": ("no target slice exists on which a ranking is defined"),
        "conditions": conditions,
        "per_slice": slice_detail,
        "reason": _g7_reason(conditions, slice_detail),
    }


def _g7_reason(conditions: dict, slice_detail: dict) -> str:
    failed = [name for name, block in conditions.items() if not block["met"]]
    if not failed:
        return "all four conditions hold"
    parts = []
    for name in failed:
        if name == "both_classes_on_every_evaluated_slice":
            thin = [s for s, d in slice_detail.items() if not d["both_classes"]]
            parts.append(f"slice(s) with a single correctness class: {thin} "
                         "(this is the guide's stated fail condition)")
        elif name == "headline_comparison_computable":
            thin = [s for s, d in slice_detail.items()
                    if not d["headline_comparison_computable"]]
            parts.append(f"no computable legal-aware vs baseline comparison on: {thin}")
        else:
            parts.append(name.replace("_", " "))
    return "; ".join(parts)
