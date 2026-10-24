"""Phase G: constructing and validating a target evaluation population.

Why this package exists
-----------------------
Phases E and F each ended with a gate that could not be evaluated, and both
records say the same thing: the target slice has only one correctness class.

* ``PHASE-E.md`` §7.4: "The synthetic matched slice has no correct L7 majority
  answers. Build a target population containing both classes before claiming
  target-slice AUROC or evaluating the complete G5 criterion."
* ``PHASE-E.md`` (structural G5 finding): G5 "requires an evaluation population
  in which ``T`` varies within a slice: a slice with both correctness classes on
  which the detector both fires and stays silent."
* ``PHASE-F.md`` §12.1: "build a target slice with both correctness classes;
  without it G6's second and third conditions remain single-sided and the L7
  stratum stays unevaluable."

Those sentences are the entire documented Phase G requirement. The engineering
guide's §21 (which ``PHASE-F.md`` cites for the gate numbering) is **not in this
repository**, so no Phase G gate number, threshold, or acceptance table exists to
implement. This package therefore implements the *documented prerequisite* — a
population that is structurally able to carry the existing G5 and G6 criteria —
and deliberately defines no new gate.

What is implemented, and from where
-----------------------------------
Every condition in :func:`population_status` is a restatement of a sentence from
the phase records above, and each carries its citation in the returned payload:

``both_correctness_classes``
    PHASE-E §7.4 / PHASE-F §12.1. A slice with one class has no defined AUROC.
``detector_fires_and_stays_silent``
    PHASE-E structural finding. The detector must be exercised in both states
    within the population, otherwise its within-slice information cannot be
    tested.
``both_classes_in_every_partition``
    PHASE-E §6 and PHASE-F §7 both need two classes in the *evaluation* portion
    (for AUROC and coverage) and in the *development* portion (to fit a map).
``no_imputed_detector_values``
    PHASE-E: "No record was assigned zero for an unresolved legal factor."
    Missing detector output is counted as missing, never coerced.
``single_slice_population``
    PHASE-E structural finding requires ``T`` to vary *within* a slice. The
    temporal factor is 1.0 on L1 and 0.0 on L7 by construction, so a population
    that spans both cannot support a within-population detector claim: the
    detector would be reading the era phrase in the question. This is a
    structural condition, not a statistical threshold.

Nothing here scores anything, reads a model, or touches a frozen artefact. The
functions are pure over the records they are given.

The confound
------------
A population built by pooling L1 and L7 does have both classes, and on the
frozen run the pooled detector AUROC looks respectable (0.772). It is an
artefact: the warrant score is almost a perfect slice indicator, so pooling
measures the slices' different accuracy, not the detector. ``PHASE-E.md``
states the structural reason and ``PHASE-F-FOLLOWUP.md`` experiment 2 measured
it (pooled AUROC 0.6868 versus 0.8626 for the same estimator fitted within
L1). :func:`confound_report` reports that diagnostic alongside every population
check so a pooled "success" cannot be reported without it.
"""
from __future__ import annotations

import math

from ..calibration.uncertainty_intervals import wilson_interval
from ..metrics import auroc

CORRECTNESS_FIELD = "majority_correct"
WARRANT_FIELD = "warrant_warranted_agreement"
SCORE_FIELD = "uq_uncertainty"
SLICE_FIELD = "slice"

#: Phase D states the detector in two-valued terms: ``W = 1`` is "silent" (the
#: agreement is warranted) and ``W = 0`` is "fired" (the agreement is not
#: warranted). Interior values come from ``W = A * T * J * K`` and are reported
#: separately rather than rounded into either state.
DETECTOR_SILENT = "silent"
DETECTOR_FIRED = "fired"
DETECTOR_PARTIAL = "partial"
DETECTOR_MISSING = "missing"
DETECTOR_INVALID = "invalid"

STATUS_READY = "READY"
STATUS_NOT_READY = "NOT_READY"


# ----------------------------------------------------------------------
# small helpers
# ----------------------------------------------------------------------
def _binary(value) -> int | None:
    """Return 0/1 for a real label, else None (never coerce a bool or a null)."""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if value in (0, 1) else None


def _unit(value) -> float | None:
    """Return a finite value in [0, 1], else None."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    if not math.isfinite(value) or value < 0.0 or value > 1.0:
        return None
    return value


def detector_state(value) -> str:
    """Classify one stored warrant score into a Phase D detector state."""
    score = _unit(value)
    if score is None:
        return DETECTOR_MISSING if value is None else DETECTOR_INVALID
    if score == 1.0:
        return DETECTOR_SILENT
    if score == 0.0:
        return DETECTOR_FIRED
    return DETECTOR_PARTIAL


def _auroc_or_none(uncertainty: list[float], correct: list[int]) -> float | None:
    """AUROC in the project's orientation (higher uncertainty -> incorrect).

    Uses :func:`jurisuq.metrics.auroc`, which returns NaN when a class is
    absent; that is reported as ``None``, never as a number.
    """
    if not uncertainty or len(uncertainty) != len(correct):
        return None
    value = auroc([1.0 - u for u in uncertainty], correct)
    return None if isinstance(value, float) and math.isnan(value) else round(float(value), 4)


# ----------------------------------------------------------------------
# the report
# ----------------------------------------------------------------------
def population_report(records: list[dict], *,
                      slice_name: str | None = None,
                      partition_of: dict[str, str] | None = None,
                      correctness_field: str = CORRECTNESS_FIELD,
                      warrant_field: str = WARRANT_FIELD,
                      score_field: str = SCORE_FIELD) -> dict:
    """Describe one candidate population and test the documented prerequisites.

    ``partition_of`` maps ``item_id`` to ``"development"`` or ``"evaluation"``.
    When it is omitted, the partition conditions are reported as not checked
    rather than assumed to hold.
    """
    if not isinstance(records, list) or not records:
        raise ValueError("population_report requires a non-empty list of records")

    rows = [r for r in records if slice_name is None or r.get(SLICE_FIELD) == slice_name]
    if not rows:
        raise ValueError(f"no records for slice {slice_name!r}")

    census = {state: 0 for state in (DETECTOR_SILENT, DETECTOR_FIRED,
                                     DETECTOR_PARTIAL, DETECTOR_MISSING, DETECTOR_INVALID)}
    labelled: list[tuple[str, int, float | None]] = []
    counts = {"total": len(rows), "correct": 0, "incorrect": 0, "unlabelled": 0}

    for record in rows:
        item_id = record.get("item_id")
        if not isinstance(item_id, str) or not item_id:
            raise ValueError("every record needs a string item_id")
        state = detector_state(record.get(warrant_field))
        census[state] += 1
        label = _binary(record.get(correctness_field))
        if label is None:
            counts["unlabelled"] += 1
            continue
        counts["correct" if label == 1 else "incorrect"] += 1
        labelled.append((item_id, label, _unit(record.get(warrant_field))))

    # Detector discrimination is computed only over rows that have both a label
    # and a real detector value; missing values are never filled in.
    detector_pairs = [(w, y) for _, y, w in labelled if w is not None]
    detector_auroc = _auroc_or_none([w for w, _ in detector_pairs],
                                    [y for _, y in detector_pairs])
    score_pairs = [(s, y) for s, y in
                   ((_unit(r.get(score_field)), _binary(r.get(correctness_field))) for r in rows)
                   if s is not None and y is not None]
    score_auroc = _auroc_or_none([s for s, _ in score_pairs], [y for _, y in score_pairs])

    partitions: dict[str, dict] = {}
    if partition_of is not None:
        for name in sorted(set(partition_of.values())):
            sub = [r for r in rows if partition_of.get(r["item_id"]) == name]
            sub_correct = sum(1 for r in sub if _binary(r.get(correctness_field)) == 1)
            sub_incorrect = sum(1 for r in sub if _binary(r.get(correctness_field)) == 0)
            partitions[name] = {"n": len(sub), "correct": sub_correct,
                                "incorrect": sub_incorrect}

    slices_present = sorted({r.get(SLICE_FIELD) for r in rows if r.get(SLICE_FIELD)})
    conditions = _conditions(counts, census, partitions, partition_of,
                             slice_name=slice_name, slices_present=slices_present)
    return {
        "slice": slice_name,
        "slices_present": slices_present,
        "counts": counts,
        "detector_census": census,
        "detector_auroc": detector_auroc,
        "score_auroc": score_auroc,
        "partitions": partitions,
        "conditions": conditions,
        "status": STATUS_READY if all(c["met"] for c in conditions.values()) else STATUS_NOT_READY,
        "status_meaning": (
            f"{STATUS_READY} means only that the population can carry the existing "
            "G5 and G6 criteria. It is not a gate verdict and asserts nothing about "
            "whether either gate passes."),
    }


def _conditions(counts: dict, census: dict, partitions: dict,
                partition_of: dict[str, str] | None, *,
                slice_name: str | None = None,
                slices_present: list[str] | None = None) -> dict:
    both_classes = counts["correct"] > 0 and counts["incorrect"] > 0
    fires = census[DETECTOR_FIRED] > 0
    silent = census[DETECTOR_SILENT] > 0
    partition_ok = None
    partition_detail = "no partition map supplied; not checked"
    if partition_of is not None:
        needed = {"development", "evaluation"}
        missing = sorted(needed - set(partitions))
        if missing:
            partition_ok = False
            partition_detail = f"partition(s) absent from the map: {missing}"
        else:
            thin = [name for name in sorted(needed)
                    if partitions[name]["correct"] == 0 or partitions[name]["incorrect"] == 0]
            partition_ok = not thin
            partition_detail = ("both partitions hold both classes" if partition_ok
                                else f"single-class partition(s): {thin}")

    def entry(met, detail, source):
        return {"met": bool(met), "detail": detail, "source": source}

    return {
        "both_correctness_classes": entry(
            both_classes,
            f"{counts['correct']} correct, {counts['incorrect']} incorrect",
            "PHASE-E.md §7.4; PHASE-F.md §12.1"),
        "detector_fires_and_stays_silent": entry(
            fires and silent,
            f"fired {census[DETECTOR_FIRED]}, silent {census[DETECTOR_SILENT]}, "
            f"partial {census[DETECTOR_PARTIAL]}",
            "PHASE-E.md, structural G5 finding"),
        "both_classes_in_every_partition": entry(
            partition_ok is True, partition_detail,
            "PHASE-E.md §6; PHASE-F.md §7"),
        "no_imputed_detector_values": entry(
            census[DETECTOR_INVALID] == 0,
            f"{census[DETECTOR_MISSING]} missing (counted, not filled), "
            f"{census[DETECTOR_INVALID]} invalid",
            "PHASE-E.md: no unresolved factor is assigned zero"),
        "single_slice_population": entry(
            slice_name is not None,
            ("single slice: " + slice_name) if slice_name is not None else
            (f"population spans {slices_present}; the temporal factor is 1.0 on L1 and "
             "0.0 on L7, so a detector AUROC here measures the era difference rather "
             "than detection"),
            "PHASE-E.md structural finding: T must vary within a slice"),
    }


def population_status(records: list[dict], **kwargs) -> dict:
    """Convenience wrapper: :func:`population_report` under a clearer name."""
    return population_report(records, **kwargs)


# ----------------------------------------------------------------------
# the confound
# ----------------------------------------------------------------------
def confound_report(records: list[dict], *,
                    warrant_field: str = WARRANT_FIELD,
                    correctness_field: str = CORRECTNESS_FIELD) -> dict:
    """Quantify whether the detector is a slice indicator on this run.

    If the warrant score predicts the slice almost perfectly, a pooled
    population's detector AUROC measures slice accuracy, not detection. The
    diagnostic is the AUROC of the detector against ``slice == L1``, next to the
    within-slice and pooled AUROCs against correctness.
    """
    usable = [r for r in records
              if _unit(r.get(warrant_field)) is not None
              and _binary(r.get(correctness_field)) is not None
              and r.get(SLICE_FIELD) in ("L1", "L7")]
    if not usable:
        raise ValueError("no records with a slice, a detector value and a label")

    slices = [1 if r[SLICE_FIELD] == "L1" else 0 for r in usable]
    warrants = [float(r[warrant_field]) for r in usable]
    is_l1 = _auroc_or_none(warrants, slices)

    per_slice = {}
    for name in ("L1", "L7"):
        sub = [r for r in usable if r[SLICE_FIELD] == name]
        per_slice[name] = {
            "n": len(sub),
            "detector_auroc": _auroc_or_none([float(r[warrant_field]) for r in sub],
                                             [_binary(r[correctness_field]) for r in sub]),
        }
    pooled = _auroc_or_none(warrants, [_binary(r[correctness_field]) for r in usable])
    return {
        "detector_auroc_against_slice_l1": is_l1,
        "detector_auroc_within_slice": per_slice,
        "detector_auroc_pooled": pooled,
        "interpretation": (
            "A detector AUROC against slice near 1.0 means the pooled population "
            "cannot separate detection from which era the item asks about; only the "
            "within-slice column is informative. Phase F follow-up experiment 2 "
            "measured the same confound on the score itself "
            "(pooled 0.6868 vs within-L1 0.8626)."),
        "source": "PHASE-E.md structural finding; PHASE-F-FOLLOWUP.md experiment 2",
    }


# ----------------------------------------------------------------------
# yield estimation (used before committing to a generation run)
# ----------------------------------------------------------------------
def yield_report(records: list[dict], *,
                 correctness_field: str = CORRECTNESS_FIELD,
                 topic_field: str = "topic",
                 confidence: float = 0.95) -> dict:
    """Estimate how often a generator produces a correct answer, per topic.

    ``records`` are full Phase A-style records (with ``sample_correct`` where
    available). Both the majority-level and the sample-level rates are
    reported, because a population needs *correct majority answers*: an item
    whose samples are sometimes correct but whose majority is wrong still counts
    as an incorrect item. Using the sample rate alone would overstate yield.
    """
    if not records:
        raise ValueError("yield_report requires at least one record")

    per_topic: dict[str, dict] = {}
    seen = 0
    for record in records:
        topic = record.get(topic_field)
        topic = topic if isinstance(topic, str) and topic else "(untagged)"
        bucket = per_topic.setdefault(topic, {"items": 0, "majority_correct": 0,
                                              "samples": 0, "correct_samples": 0})
        bucket["items"] += 1
        seen += 1
        label = _binary(record.get(correctness_field))
        if label == 1:
            bucket["majority_correct"] += 1
        samples = record.get("sample_correct")
        if isinstance(samples, list):
            bucket["samples"] += len(samples)
            bucket["correct_samples"] += sum(1 for s in samples if s == 1)

    if seen == 0:
        raise ValueError("yield_report saw no usable records")

    items = sum(b["items"] for b in per_topic.values())
    majority_hits = sum(b["majority_correct"] for b in per_topic.values())
    samples = sum(b["samples"] for b in per_topic.values())
    sample_hits = sum(b["correct_samples"] for b in per_topic.values())
    for bucket in per_topic.values():
        bucket["majority_rate"] = bucket["majority_correct"] / bucket["items"]
        bucket["sample_rate"] = (bucket["correct_samples"] / bucket["samples"]
                                 if bucket["samples"] else None)

    return {
        "topics": per_topic,
        "overall": {
            "items": items,
            "majority_correct": majority_hits,
            "majority_rate": majority_hits / items,
            "majority_interval": wilson_interval(majority_hits, items, confidence=confidence),
            "samples": samples,
            "correct_samples": sample_hits,
            "sample_rate": (sample_hits / samples) if samples else None,
            "sample_interval": (wilson_interval(sample_hits, samples, confidence=confidence)
                                if samples else None),
        },
        "confidence": confidence,
        "unit_note": ("majority_rate is the planning quantity: a target population needs "
                      "items whose *majority* answer is correct, not items with at least "
                      "one correct sample."),
    }


def items_needed(rate: float, needed_correct: int, *,
                 confidence: float = 0.95, cap: int = 20000) -> dict:
    """How many items to generate so that ``needed_correct`` are likely correct.

    Returns the smallest ``n`` for which a binomial draw at ``rate`` yields at
    least ``needed_correct`` correct items with probability ``>= confidence``,
    plus the plain expectation. These are planning numbers for a cost estimate,
    not a gate: the caller decides whether the projection is affordable.
    """
    if not 0.0 <= rate <= 1.0:
        raise ValueError("rate must lie in [0, 1]")
    if needed_correct < 1:
        raise ValueError("needed_correct must be at least 1")
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must lie strictly between 0 and 1")

    expected = math.inf if rate == 0.0 else math.ceil(needed_correct / rate)
    if rate == 1.0:
        return {"rate": rate, "needed_correct": needed_correct,
                "expected_items": needed_correct, "items_for_confidence": needed_correct,
                "confidence": confidence, "reachable": True}
    if rate == 0.0:
        return {"rate": rate, "needed_correct": needed_correct,
                "expected_items": None, "items_for_confidence": None,
                "confidence": confidence, "reachable": False,
                "note": "a zero observed rate cannot be projected; a zero would be "
                        "indistinguishable from an even lower unobserved rate"}

    def tail(n: int) -> float:
        # P(X >= k) for X ~ Binomial(n, rate); stdlib only.
        if n < needed_correct:
            return 0.0
        total = 0.0
        for k in range(needed_correct, n + 1):
            total += math.comb(n, k) * rate ** k * (1 - rate) ** (n - k)
        return total

    n = needed_correct
    while n < cap and tail(n) < confidence:
        n += 1
    reachable = n < cap
    return {"rate": rate, "needed_correct": needed_correct,
            "expected_items": expected,
            "items_for_confidence": n if reachable else None,
            "confidence": confidence, "reachable": reachable,
            **({"note": f"not reached within cap={cap} items"} if not reachable else {})}
