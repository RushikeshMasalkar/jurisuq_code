"""Phase D validation (experiment E4) and Gate G4.

The detector can be validated before Phase E exists, because the
frozen Phase A records already carry the ground truth about which
unanimous answers were wrong.  The validation is therefore a direct
computation, not a new experiment: on the unanimously-wrong
target-slice items and the unanimously-wrong control items, does the
detector fire, and on the unanimously-correct control items does it
stay silent?  A detector that fires on everything is worthless, so the
confusion matrix over the collision population -- including the
negatives -- is the first number Phase D produces.

Gate G4 has three conditions, all of which must hold:

1. **Separation.**  The common-mode score separates correct from
   incorrect unanimous answers with AUROC above 0.5 and a bootstrap
   interval excluding 0.5.  (n is small; the interval is reported
   honestly rather than rounded away.)
2. **Factor attribution.**  The temporal factor alone recovers most of
   the separation the composite achieves -- otherwise the composite is
   over-fitted to this slice and should be simplified.
3. **Base-rate honesty.**  The false-alarm rate on unanimously-correct
   items is reported and is below the alarm rate on unanimously-wrong
   items -- otherwise the detector is a constant, not a signal.

The factor-attribution condition is evaluated by *ablation*: the score
is recomputed with each factor pinned to its warrant-maximising value
(T=1, J=1, K=0) and the drop in AUROC is recorded.  This is the same
mechanism Phase H will use, so the ablation machinery is built once,
here, and reused.
"""
from __future__ import annotations

import math
import random
from collections import Counter, defaultdict

from jurisuq.metrics import auroc
from jurisuq.warrant.detector import (FLAG_CONTRADICTION, FLAG_FOREIGN,
                                       FLAG_STALE, FLAG_UNRESOLVABLE,
                                       WarrantDetector, WarrantResult,
                                       compose)


def collision_population(results: list[tuple[dict, WarrantResult]],
                         correct_of) -> list[tuple[dict, WarrantResult]]:
    """The unanimous provision-level collision population.

    An item is in the collision population when every sample resolves
    to one provision cluster -- the population in which agreement is
    total and any error is therefore common-mode.  Correctness is read
    only here, offline, never inside the detector.
    """
    out = []
    for rec, res in results:
        if int(rec.get("prov_all_same") or 0) == 1:
            out.append((rec, res))
    return out


def _cm(res: WarrantResult) -> float | None:
    return res.common_mode_score


def separation_auroc(population, correct_of) -> dict:
    """AUROC of the common-mode score over the collision population.

    Items whose CM is undefined (an unresolvable factor) are excluded
    from the score-based AUROC -- absent is never treated as zero --
    and the exclusion is reported.  The binary firing rate over the
    *whole* population is reported separately, so the unresolvable
    items still count as detections.
    """
    scored = [(r, res) for (r, res) in population
              if _cm(res) is not None]
    correct = [int(correct_of(r)) for r, _ in scored]
    scores = [_cm(res) for _, res in scored]
    n_excluded = len(population) - len(scored)
    if len(set(correct)) < 2:
        return {"auroc": float("nan"), "n_scored": len(scored),
                "n_excluded_undefined": n_excluded,
                "ci": {"lo": float("nan"), "hi": float("nan")},
                "defined": False}
    ci = _paired_auroc_ci(scores, correct)
    return {"auroc": auroc(scores, correct), "n_scored": len(scored),
            "n_excluded_undefined": n_excluded,
            "ci": {"lo": ci["lo"], "hi": ci["hi"],
                   "n_boot": ci["n_boot"]},
            "defined": True}


def _paired_auroc_ci(scores, correct, n_boot=2000, seed=0):
    """Bootstrap CI for AUROC, resampling (score, label) pairs together.

    AUROC is a function of the *pairing* of scores and labels, so a
    bootstrap that resamples only the scores (as the generic helper
    does) silently misaligns them and produces a meaningless interval.
    """
    rng = random.Random(seed)
    n = len(scores)
    pts = []
    for _ in range(n_boot):
        idx = [rng.randrange(n) for _ in range(n)]
        sc = [scores[i] for i in idx]
        cc = [correct[i] for i in idx]
        if len(set(cc)) < 2:
            continue
        a = auroc(sc, cc)
        if a == a:                      # skip single-class resamples
            pts.append(a)
    pts.sort()

    def _pct(q):
        if not pts:
            return float("nan")
        pos = q * (len(pts) - 1)
        lo = int(math.floor(pos))
        hi = min(lo + 1, len(pts) - 1)
        return pts[lo] * (1 - (pos - lo)) + pts[hi] * (pos - lo)
    return {"lo": _pct(0.025), "hi": _pct(0.975), "n_boot": len(pts)}


def binary_confusion(population, correct_of) -> dict:
    """TP/FP/TN/FN of the binary ``fires`` predicate on the population."""
    tp = fp = tn = fn = 0
    for rec, res in population:
        fires = bool(res.flags)
        correct = int(correct_of(rec))
        if fires and not correct:
            tp += 1
        elif fires and correct:
            fp += 1
        elif not fires and correct:
            tn += 1
        else:
            fn += 1
    n = tp + fp + tn + fn
    return {
        "n": n, "tp": tp, "fp": fp, "tn": tn, "fn": fn,
        "accuracy": (tp + tn) / n if n else float("nan"),
        "precision": tp / (tp + fp) if tp + fp else float("nan"),
        "recall": tp / (tp + fn) if tp + fn else float("nan"),
        "false_alarm_rate": fp / (fp + tn) if fp + tn else 0.0,
    }


def group_report(population, correct_of) -> dict:
    """Firing behaviour broken down by (slice, correctness)."""
    groups = defaultdict(list)
    for rec, res in population:
        groups[(rec.get("slice", "?"), int(correct_of(rec)))].append(res)
    out = {}
    for (sl, correct), reses in sorted(groups.items()):
        fires = sum(1 for r in reses if r.flags)
        flags = Counter(f for r in reses for f in r.flags)
        cms = [_cm(r) for r in reses]
        defined = [c for c in cms if c is not None]
        out[f"{sl}|correct={correct}"] = {
            "n": len(reses), "fires": fires,
            "fire_rate": fires / len(reses) if reses else float("nan"),
            "flags": dict(flags),
            "cm_mean": (sum(defined) / len(defined)) if defined else None,
            "cm_undefined": len(cms) - len(defined),
        }
    return out


def factor_ablation(population, correct_of, detector: WarrantDetector) -> dict:
    """How much separation each factor contributes, by pinning it.

    For each factor the score is recomputed with that factor pinned to
    the value that maximises warrant (T=1, J=1, K=0) while the others
    keep their measured values.  The AUROC drop when a factor is pinned
    is the separation that factor alone carries.  This is the mechanism
    Phase H reuses, built once here.
    """
    rows = []
    base = _auroc_over(population, correct_of, lambda r: _cm(r))
    for factor, pin in (("temporal", 1.0), ("jurisdiction", 1.0),
                        ("contradiction", 0.0)):
        def ablated(res, factor=factor, pin=pin):
            A = res.observed_agreement
            T = pin if factor == "temporal" else res.temporal_validity
            J = pin if factor == "jurisdiction" else res.jurisdiction_fit
            K = pin if factor == "contradiction" else res.contradiction_mass
            W, CM = compose(A, T, J, K)
            return CM
        auc = _auroc_over(population, correct_of, ablated)
        rows.append({"factor": factor, "pinned_to": pin,
                     "auroc_when_pinned": auc,
                     "auroc_drop_from_full":
                         (base - auc) if (base == base and auc == auc)
                         else None})
    return {"full_auroc": base, "ablations": rows}


def _auroc_over(population, correct_of, score_of) -> float:
    pairs = [(rec, res) for rec, res in population]
    correct = [int(correct_of(rec)) for rec, _ in pairs]
    scores = [score_of(res) for _, res in pairs]
    keep = [(s, c) for s, c in zip(scores, correct) if s is not None and s == s]
    if not keep:
        return float("nan")
    sc = [s for s, _ in keep]
    cc = [c for _, c in keep]
    if len(set(cc)) < 2:
        return float("nan")
    return auroc(sc, cc)


def gate_g4(sep: dict, attribution: dict,
            correct_item_alarm_rate: float,
            wrong_item_alarm_rate: float) -> dict:
    """Evaluate Gate G4.  All three conditions must hold.

    1. Separation: CM-score AUROC > 0.5 with a bootstrap interval
       excluding 0.5, over the collision population.
    2. Factor attribution: pinning the temporal factor to its
       warrant-maximising value removes at least half of the
       *above-chance* separation the composite achieves -- i.e.
       the temporal factor alone carries most of the effect.
    3. Base-rate honesty: the alarm rate on unanimously-correct
       items is below the alarm rate on unanimously-wrong items.
    """
    full = attribution.get("full_auroc")
    temporal_drop = next((a["auroc_drop_from_full"] for a in
                          attribution["ablations"]
                          if a["factor"] == "temporal"), None)
    auroc_val = sep.get("auroc")
    ci_lo = sep.get("ci", {}).get("lo")

    c1 = bool(sep.get("defined") and auroc_val == auroc_val
              and auroc_val > 0.5
              and ci_lo == ci_lo and ci_lo is not None
              and ci_lo > 0.5)

    # the separation that can be attributed is the part above
    # chance (0.5); a factor "carries" it when pinning it away
    # removes at least half of that part
    if (full == full and temporal_drop == temporal_drop
            and full is not None and temporal_drop is not None
            and full > 0.5):
        achievable = full - 0.5
        c2 = bool(temporal_drop >= 0.5 * achievable)
    else:
        c2 = False

    c3 = bool(correct_item_alarm_rate == correct_item_alarm_rate
              and wrong_item_alarm_rate == wrong_item_alarm_rate
              and correct_item_alarm_rate < wrong_item_alarm_rate)

    return {
        "gate": "G4",
        "conditions": {
            "separation_auroc_gt_0.5_ci_excludes_0.5": c1,
            "temporal_factor_carries_half_of_above_chance": c2,
            "correct_item_alarm_below_wrong_item_alarm": c3,
        },
        "verdict": "PASS" if (c1 and c2 and c3) else "FAIL",
        "notes": {
            "separation_auroc": auroc_val,
            "separation_ci": sep.get("ci"),
            "full_auroc": full,
            "temporal_auroc_drop": temporal_drop,
            "temporal_share_of_above_chance":
                (temporal_drop / (full - 0.5))
                if (full == full and full is not None
                    and full > 0.5 and temporal_drop == temporal_drop)
                else None,
            "correct_item_alarm_rate": correct_item_alarm_rate,
            "wrong_item_alarm_rate": wrong_item_alarm_rate,
        },
    }


def validate(detector: WarrantDetector | None, records: list[dict],
             correct_of, results: list | None = None) -> dict:
    """Run the detector over records and produce the E4 validation.

    ``correct_of`` is called offline on each record to obtain the
    majority-outcome correctness label; the detector itself never sees
    it.  The collision population is isolated, scored, and ablated, and
    the false-alarm base rate is reported over the rest of the run.

    ``results`` may carry pre-computed ``(record, WarrantResult)``
    pairs -- for example rebuilt from a run's stored ``warrant_*``
    fields -- in which case the detector is not called at all and
    every number is reproduced from the record alone.
    """
    if results is None:
        if detector is None:
            raise ValueError("either a detector or pre-computed "
                             "results is required")
        results = [(rec, detector.detect(rec)) for rec in records]
    population = collision_population(results, correct_of)
    sep = separation_auroc(population, correct_of)
    confusion = binary_confusion(population, correct_of)
    groups = group_report(population, correct_of)
    attribution = factor_ablation(population, correct_of, detector)

    # false-alarm base rate: firing on the non-collision population,
    # decomposed by correctness so the true alarm rate on correct
    # items is visible rather than buried in an aggregate
    non_collision = [(r, s) for (r, s) in results
                     if int(r.get("prov_all_same") or 0) != 1]
    nc_groups = defaultdict(list)
    for rec, res in non_collision:
        nc_groups[int(correct_of(rec))].append(res)
    correct_alarms = [r for r in nc_groups.get(1, []) if r.flags]
    wrong_alarms = [r for r in nc_groups.get(0, []) if r.flags]
    base_rate = {
        "non_collision_items": len(non_collision),
        "non_collision_fire_rate":
            (sum(1 for _, r in non_collision if r.flags)
             / len(non_collision)) if non_collision else float("nan"),
        "correct_item_alarm_rate":
            (len(correct_alarms) / len(nc_groups.get(1, []))
             if nc_groups.get(1) else 0.0),
        "wrong_item_alarm_rate":
            (len(wrong_alarms) / len(nc_groups.get(0, []))
             if nc_groups.get(0) else 0.0),
    }
    # Gate G4's base-rate condition is evaluated on the collision
    # population itself: the alarm rate on its correct items versus
    # its wrong items.  The non-collision base rate is reported
    # alongside for honesty, but the gate is about the validation
    # population the spec defines.
    collision_correct_alarm = confusion["false_alarm_rate"]
    collision_wrong_alarm = confusion["recall"]

    gate = gate_g4(sep, attribution,
                   collision_correct_alarm,
                   collision_wrong_alarm)

    # flag census over the whole run, for the report
    flag_census = Counter(f for _, r in results for f in r.flags)

    return {
        "experiment": "E4",
        "n_records": len(records),
        "collision_population": {
            "n": len(population),
            "separation": sep,
            "binary_confusion": confusion,
            "by_group": groups,
            "factor_ablation": attribution,
        },
        "base_rate": base_rate,
        "flag_census": dict(flag_census),
        "gate_g4": gate,
    }
