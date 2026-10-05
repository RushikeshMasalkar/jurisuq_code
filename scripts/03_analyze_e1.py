#!/usr/bin/env python3
"""03 - E1: the common-mode diagnostic.

Reads runs/<run_id>/items.jsonl and answers one question:

    can a sample-only uncertainty method tell a correct legal answer from an
    incorrect one, and does it collapse on the slice where the errors are
    common-mode?

Reported per slice and per method
---------------------------------
* AUROC of the uncertainty score for detecting incorrect answers, with a
  bootstrap CI over items
* normalized AURC (selective-prediction skill against the trivial orderings)
* selective risk at 50 per cent coverage
* the *collision population*: items where every sample fell in one discrete
  cluster. Accuracy there is the direct measure of confident agreement with a
  wrong answer.

Decision rule for gate G1 (Section 6.5 of the guide)
---------------------------------------------------
Condition 1 (ceiling): on L7 the best sample-only method stays at or below
0.70 AUROC - agreement alone cannot rank legal correctness there. When a slice
contains only one correctness class (the model fails every item, or passes every
item) AUROC is undefined; the ceiling is then read from the collision statistic
instead, because in that situation the question "can agreement rank errors?"
has an operational answer: the answers the method accepts with maximum
confidence are themselves wrong.

Condition 2 (contrast), satisfied by either of:
  (a) the L1-minus-L7 AUROC gap has a 95 per cent bootstrap interval that
      excludes zero, or
  (b) the collision-population contrast is real: the share of *confidently
      wrong* answers (zero semantic entropy, wrong answer) on L7 exceeds that
      on L1 by at least 20 points with non-overlapping Wilson intervals.

Condition 2(b) exists because it is the direct measurement of the phenomenon:
zero entropy with a wrong answer is exactly "the samples agreed and the whole
sample set was wrong". It is less sensitive to tie structure in the AUROC than
condition 2(a), and it is the number to quote in the paper.

    python scripts/03_analyze_e1.py --run-id phaseA-laptop
"""
from __future__ import annotations

import argparse
import json
import math
import random
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jurisuq.config import Config, ROOT
from jurisuq.metrics import (auroc, aurc, normalized_aurc, risk_coverage,
                             two_sample_bootstrap_diff)

METHOD_LABEL = {
    "prov_se": "Provision-level entropy (this work)",
    "prov_agreement": "1 - provision agreement (this work)",
    "disc_se": "Discrete semantic entropy [SE24]",
    "se": "Standard semantic entropy [SE24]",
    "selfcheck": "SelfCheckGPT-style contradiction",
    "agreement": "1 - majority agreement (discrete)",
    "p_true": "1 - p_true from logprobs",
}
GATE_AUROC_MAX = 0.70


# ----------------------------------------------------------------------
def load_records(run_dir: Path) -> list[dict]:
    path = run_dir / "items.jsonl"
    if not path.exists():
        raise SystemExit(f"{path} not found - run scripts/02_run_inference.py first")
    recs, errors = [], 0
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if "error" in r:
            errors += 1
            continue
        recs.append(r)
    if errors:
        print(f"NOTE: skipped {errors} records that failed during inference")
    return recs


def resolved_only(recs: list[dict]) -> list[dict]:
    """Items whose returned answer the judge could actually resolve.

    Unresolved answers are excluded, never counted as wrong: counting them as
    wrong would report a model as 0% accurate when the truth is that the judge
    could not read the answer. The count of exclusions is printed in the report
    and written to the JSON, so the exclusion is visible rather than silent.
    """
    return [r for r in recs if int(r.get("majority_resolved", 1)) == 1]


def _available_methods(recs: list[dict]) -> list[str]:
    out = []
    for m in METHOD_LABEL:
        vals = [r["methods"].get(m) for r in recs]
        if any(v is not None and v == v for v in vals):
            out.append(m)
    return out


def slice_table(recs: list[dict], method: str) -> dict:
    recs = resolved_only(recs)
    rows = [(r["methods"][method], int(r["majority_correct"])) for r in recs
            if r["methods"].get(method) is not None and r["methods"][method] == r["methods"][method]]
    if not rows:
        return {}
    unc = [u for u, _ in rows]
    cor = [c for _, c in rows]
    rc = risk_coverage(cor, unc, coverages=(0.5, 0.75, 1.0))
    return {
        "n": len(rows),
        "accuracy": sum(cor) / len(cor),
        "auroc": auroc(unc, cor),
        "aurc_norm": normalized_aurc(cor, unc),
        "risk_at_50": rc["at"][0.5]["risk"],
        "risk_at_full": rc["at"][1.0]["risk"],
    }


def bootstrap_auroc_diff(recs_a: list[dict], recs_b: list[dict], method: str,
                         n_boot: int = 2000, alpha: float = 0.05, seed: int = 0) -> dict:
    """CI for AUROC(method on A) - AUROC(method on B), resampling items within each set."""

    def pairs(recs):
        return [(r["methods"][method], int(r["majority_correct"])) for r in resolved_only(recs)
                if r["methods"].get(method) is not None and r["methods"][method] == r["methods"][method]]

    pa, pb = pairs(recs_a), pairs(recs_b)
    if not pa or not pb:
        return {"point": float("nan")}
    point = auroc([u for u, _ in pa], [c for _, c in pa]) - auroc([u for u, _ in pb], [c for _, c in pb])
    rng = random.Random(seed)
    diffs = []
    for _ in range(n_boot):
        sa = [pa[rng.randrange(len(pa))] for _ in range(len(pa))]
        sb = [pb[rng.randrange(len(pb))] for _ in range(len(pb))]
        ca = [c for _, c in sa]
        cb = [c for _, c in sb]
        if all(x == ca[0] for x in ca) or all(x == cb[0] for x in cb):
            continue
        d = auroc([u for u, _ in sa], ca) - auroc([u for u, _ in sb], cb)
        if d == d:
            diffs.append(d)
    diffs.sort()
    if not diffs:
        return {"point": point}
    lo = diffs[int(alpha / 2 * (len(diffs) - 1))]
    hi = diffs[int((1 - alpha / 2) * (len(diffs) - 1))]
    p_le_zero = sum(1 for d in diffs if d <= 0) / len(diffs)
    return {"point": point, "lo": lo, "hi": hi, "p_le_zero": p_le_zero,
            "ci_excludes_zero": bool(lo > 0 or hi < 0)}


def bootstrap_auroc(recs: list[dict], method: str, n_boot: int = 2000,
                    alpha: float = 0.05, seed: int = 0) -> dict:
    recs = resolved_only(recs)
    pairs = [(r["methods"][method], int(r["majority_correct"])) for r in recs
             if r["methods"].get(method) is not None and r["methods"][method] == r["methods"][method]]
    if not pairs:
        return {"point": float("nan")}
    point = auroc([u for u, _ in pairs], [c for _, c in pairs])
    rng = random.Random(seed)
    vals = []
    for _ in range(n_boot):
        s = [pairs[rng.randrange(len(pairs))] for _ in range(len(pairs))]
        c = [cc for _, cc in s]
        if all(x == c[0] for x in c):
            continue
        v = auroc([u for u, _ in s], c)
        if v == v:
            vals.append(v)
    vals.sort()
    if not vals:
        return {"point": point}
    return {"point": point,
            "lo": vals[int(alpha / 2 * (len(vals) - 1))],
            "hi": vals[int((1 - alpha / 2) * (len(vals) - 1))],
            "n_boot": len(vals)}


def collision_population(recs: list[dict], level: str = "provision") -> dict:
    """Items where every sample asserted the same thing.

    ``level="provision"`` (default) groups samples by the provision they assert,
    extracted by the judge, so ten differently-worded answers that all name IPC
    302 count as *one* answer - which is the point. ``level="text"`` uses exact
    string identity and is kept only as a diagnostic: on a model that paraphrases
    freely it under-counts the phenomenon badly (a real run had text-level
    collisions of zero while every sample agreed on the repealed section).

    The returned ``confident_wrong`` is the share of those unanimous items whose
    unanimous answer is wrong. It is the operational definition of common-mode
    error: agreement at maximum confidence, and the answer is nevertheless wrong.
    """
    key = "prov_all_same" if level == "provision" else "all_same"
    pool = [r for r in recs if r.get(key, 0) == 1]
    pop = [r for r in pool if int(r.get("majority_resolved", 1)) == 1]
    if not pop:
        return {"n": 0}
    cor = [int(r["majority_correct"]) for r in pop]
    n, k = len(cor), sum(cor)
    acc = k / n
    # Wilson 95 per cent interval
    z = 1.959963984540054
    denom = 1 + z * z / n
    centre = (acc + z * z / (2 * n)) / denom
    half = z * math.sqrt(acc * (1 - acc) / n + z * z / (4 * n * n)) / denom
    return {"n": n, "n_all_items": len(pool), "level": level, "accuracy": acc,
            "lo": max(0.0, centre - half), "hi": min(1.0, centre + half),
            "confident_wrong": 1 - acc}


# ----------------------------------------------------------------------
def markdown_table(rows: list[list[str]], header: list[str]) -> str:
    widths = [max(len(str(r[i])) for r in [header] + rows) for i in range(len(header))]
    line = "| " + " | ".join(str(h).ljust(widths[i]) for i, h in enumerate(header)) + " |"
    sep = "|" + "|".join("-" * (w + 2) for w in widths) + "|"
    body = ["| " + " | ".join(str(r[i]).ljust(widths[i]) for i in range(len(header))) + " |" for r in rows]
    return "\n".join([line, sep] + body)


GATE_CONTRAST_MIN = 0.20


def gate_verdict(results: dict) -> dict:
    """Apply the G1 decision rule to a finished E1 report. Pure function."""
    reasons: list[str] = []
    verdict: dict = {"pass": False, "ceiling_ok": None, "gap_ok": None,
                     "contrast_ok": None, "reasons": reasons}

    per_slice = results.get("per_slice", {})
    if "L7" not in per_slice or not per_slice["L7"].get("methods"):
        reasons.append("L7 slice missing: run with --set slices=[\"L7\",\"L1\"]")
        verdict["reading"] = "Cannot evaluate the gate without the L7 slice."
        return verdict

    l7_methods = per_slice["L7"]["methods"]
    best_name, best_st = max(
        l7_methods.items(),
        key=lambda kv: (kv[1]["auroc"] if kv[1]["auroc"] == kv[1]["auroc"] else -1))
    verdict["l7_accuracy"] = per_slice["L7"].get("accuracy")
    verdict["best_method_on_L7"] = best_name
    verdict["best_auroc_on_L7"] = best_st["auroc"]
    auroc_l7 = best_st["auroc"]
    l7_accuracy = per_slice["L7"].get("accuracy")
    if l7_accuracy is None:
        l7_accuracy = next((m.get("accuracy") for m in l7_methods.values()
                            if m.get("accuracy") is not None), None)
    coll_l7_probe = results.get("collision", {}).get("L7", {})
    if auroc_l7 != auroc_l7:                     # NaN: one correctness class only
        l7_acc = l7_accuracy
        n_coll = coll_l7_probe.get("n", 0)
        coll_acc = coll_l7_probe.get("accuracy")
        if (l7_acc is not None and l7_acc < 0.5 and n_coll >= 10
                and coll_acc is not None and coll_acc < 0.5):
            verdict["ceiling_ok"] = True
            verdict["ceiling_basis"] = "collision-statistic (AUROC undefined: single class)"
            reasons.append(
                f"ceiling: AUROC on L7 is undefined because the model failed every scored "
                f"item (accuracy {l7_acc:.3f}) - the strongest possible form of the ceiling "
                f"condition. Its unanimous answers are themselves wrong in "
                f"{coll_l7_probe.get('confident_wrong', float('nan')):.3f} of the {n_coll} "
                f"items where every sample asserted the same provision -> met, read from the "
                f"provision-level collision statistic.")
        else:
            verdict["ceiling_ok"] = False
            verdict["ceiling_basis"] = "undefined"
            reasons.append(
                f"ceiling: AUROC on L7 is undefined: only one correctness class is present "
                f"(accuracy {l7_acc}). With fewer than 10 zero-entropy items there is nothing "
                f"for agreement to rank; record more items or use a second checkpoint.")
    else:
        verdict["ceiling_ok"] = bool(auroc_l7 <= GATE_AUROC_MAX)
        reasons.append(
            f"ceiling: best sample-only AUROC on L7 = {auroc_l7:.3f} "
            f"({METHOD_LABEL.get(best_name, best_name)}); need <= {GATE_AUROC_MAX} -> "
            f"{'met' if verdict['ceiling_ok'] else 'NOT met'}")

    gaps_excl = [m for m, g in results.get("gaps", {}).items() if g.get("ci_excludes_zero")]
    verdict["gap_ok"] = bool(gaps_excl)
    reasons.append(
        f"AUROC contrast: L1-L7 gap excludes zero for {len(gaps_excl)}/{len(results.get('gaps', {}))} "
        f"methods ({', '.join(gaps_excl) if gaps_excl else 'none'})")

    coll_l7 = results.get("collision", {}).get("L7", {})
    coll_l1 = results.get("collision", {}).get("L1", {})
    contrast_ok = False
    if coll_l7.get("n") and coll_l1.get("n"):
        cw7, cw1 = coll_l7.get("confident_wrong"), coll_l1.get("confident_wrong")
        # the share confidently wrong on L7 minus the same on L1, with the two
        # Wilson intervals used conservatively: they must not overlap
        contrast = cw7 - cw1
        non_overlapping = coll_l7["lo"] > coll_l1["hi"] or coll_l1["lo"] > coll_l7["hi"]
        contrast_ok = bool(contrast >= GATE_CONTRAST_MIN and non_overlapping)
        verdict["contrast"] = contrast
        verdict["contrast_non_overlapping"] = non_overlapping
        verdict["collision_L7"] = coll_l7
        verdict["collision_L1"] = coll_l1
        reasons.append(
            f"collision contrast: confidently wrong (zero entropy, wrong answer) = "
            f"{cw7:.3f} on L7 (n = {coll_l7['n']}) vs {cw1:.3f} on L1 (n = {coll_l1['n']}); "
            f"difference {contrast:+.3f}, need >= {GATE_CONTRAST_MIN} -> "
            f"{'met' if contrast_ok else 'NOT met'}"
            f"{'' if non_overlapping else ' (intervals overlap)'}")
    else:
        reasons.append("collision contrast: not available (no zero-entropy items measured)")

    verdict["contrast_ok"] = contrast_ok
    condition_2 = bool(verdict["gap_ok"] or contrast_ok)
    verdict["pass"] = bool(verdict["ceiling_ok"] and condition_2)

    if verdict["pass"]:
        if contrast_ok:
            verdict["reading"] = (
                "Reading: on the superseded-provision slice the model produces zero-entropy, "
                "self-consistent, wrong answers far more often than on the matched controls, "
                "while the best sample-only method cannot rank it above 0.70 AUROC. The premise "
                "of JURIS-UQ holds. Quote the collision-population row in the paper; it is the "
                "diagnostic result, and the L7 slice is its home.")
        else:
            verdict["reading"] = (
                "Reading: the AUROC gap is established but the collision population is not yet "
                "decisive. Report the gap, and add items to the L7 slice (aim for at least 60 "
                "zero-entropy wrong answers) before treating the contrast as a claim.")
    else:
        verdict["reading"] = (
            "Reading: read the two conditions separately. If the ceiling is met but condition 2 "
            "fails, the model may simply not share the bias on this slice - try the second "
            "checkpoint (for example the 3B against the 7B model) and a lower temperature before "
            "touching the design. If the ceiling is NOT met, sample-only agreement already "
            "detects the error on L7, and the honest move is to report that and re-aim the paper "
            "at the calibration and abstention contribution rather than at the diagnostic one.")
    return verdict


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", default="phaseA-smoke")
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--n-boot", type=int, default=2000)
    args = ap.parse_args()

    cfg = Config.load()
    run_dir = ROOT / cfg.out_dir / args.run_id
    out_dir = Path(args.out_dir) if args.out_dir else run_dir
    recs = load_records(run_dir)
    meta = json.loads((run_dir / "meta.json").read_text()) if (run_dir / "meta.json").exists() else {}

    slices = sorted({r["slice"] for r in recs})
    methods = _available_methods(recs)
    usable = resolved_only(recs)
    if not usable:
        print("NO ITEM COULD BE SCORED: the correctness resolver (judge) could not read the")
        print("answers at all. The uncertainty numbers below are therefore meaningless - this")
        print("is a judge problem, not a model problem. Fix it without re-sampling:")
        print(f"    python scripts/05_rejudge.py --run-id {args.run_id} --inspect")
        print(f"    python scripts/05_rejudge.py --run-id {args.run_id}")
        print()

    print("=" * 78)
    print("E1 - CAN SAMPLE-ONLY CONSISTENCY DETECT LEGAL ERROR?")
    print("=" * 78)
    print(f"run        : {args.run_id}")
    print(f"generator  : {meta.get('provider', '?')}")
    print(f"nli backend: {meta.get('nli_backend', '?')}")
    print(f"items      : {len(recs)}  slices {slices}  methods {methods}")
    print()

    results: dict = {"run_id": args.run_id, "n_items": len(recs), "slices": slices,
                     "gate_auroc_max": GATE_AUROC_MAX, "per_slice": {}, "gaps": {},
                     "collision": {}}

    # ---- per slice, per method --------------------------------------
    for s in slices:
        sub = [r for r in recs if r["slice"] == s]
        usable = resolved_only(sub)
        excluded = len(sub) - len(usable)
        results["per_slice"][s] = {"n_items": len(sub), "n_scored": len(usable),
                                   "n_excluded_unresolved": excluded, "methods": {}}
        if usable:
            acc = sum(int(r["majority_correct"]) for r in usable) / len(usable)
            results["per_slice"][s]["accuracy"] = acc
            print(f"slice {s}:  n = {len(sub)}   scored = {len(usable)}"
                  f"   (excluded as unresolved: {excluded})   "
                  f"accuracy of the returned answer = {acc:.3f}")
        else:
            print(f"slice {s}:  n = {len(sub)}   SCORED = 0 - every answer was unresolved")
        if excluded and len(sub):
            print(f"  judge coverage {len(usable) / len(sub) * 100:.1f}%; unresolved answers are "
                  f"excluded from the metrics, not counted as wrong")
        if usable and results["per_slice"][s]["methods"]:
            st0 = next(iter(results["per_slice"][s]["methods"].values()))
            if st0.get("auroc") != st0.get("auroc"):
                print(f"  note: every scored answer on {s} fell in one correctness class "
                      f"(accuracy {st0['accuracy']:.3f}), so AUROC is undefined here and the "
                      f"collision population below carries the diagnostic instead")
        if not usable:
            continue
        rows = []
        for m in methods:
            st = slice_table(sub, m)
            if not st:
                continue
            ci = bootstrap_auroc(sub, m, n_boot=args.n_boot)
            st.update({"auroc_lo": ci.get("lo"), "auroc_hi": ci.get("hi")})
            results["per_slice"][s]["methods"][m] = st
            rows.append([METHOD_LABEL[m],
                         f"{st['auroc']:.3f}",
                         f"[{ci.get('lo', float('nan')):.3f}, {ci.get('hi', float('nan')):.3f}]",
                         f"{st['aurc_norm']:.3f}",
                         f"{st['risk_at_50']:.3f}", f"{st['accuracy']:.3f}"])
        print(markdown_table(rows, ["method", "AUROC", "95% CI", "nAURC", "risk@50%", "accuracy"]))
        coll = collision_population(sub, level="provision")
        coll_text = collision_population(sub, level="text")
        results["collision"][s] = coll
        results.setdefault("collision_text", {})[s] = {
           "n": coll_text.get("n", 0),
	    "confident_wrong": coll_text.get("confident_wrong", float("nan"))
	}
        if coll["n"]:
            print(f"  unanimous at the provision level: n = {coll['n']} of {len(sub)} items, "
                  f"accuracy = {coll['accuracy']:.3f} [{coll['lo']:.3f}, {coll['hi']:.3f}], "
                  f"confident-and-wrong = {coll['confident_wrong']:.3f}")
        if coll_text["n"]:
            print(f"  unanimous at the text level     : n = {coll_text['n']} of {len(sub)} items, "
                  f"confident-and-wrong = {coll_text['confident_wrong']:.3f}"
                  f"{'   <- text-level agreement under-counts; quote the provision level' if coll_text['n'] < coll['n'] else ''}")
        # what did the model actually say, per slice
        top: dict[str, int] = {}
        for r in sub:
            top[r.get("prov_majority") or "NONE"] = top.get(r.get("prov_majority") or "NONE", 0) + 1
        ordered = sorted(top.items(), key=lambda kv: -kv[1])[:6]
        print("  most frequent asserted provision (modal answer per item):")
        for k, v in ordered:
            print(f"      {k:<28} {v:4d} items   {v / len(sub) * 100:5.1f}%")
        rep_share = [r.get("repealed_code_share") for r in sub
                     if r.get("repealed_code_share") == r.get("repealed_code_share")]
        if rep_share:
            print(f"  samples asserting a provision of a code repealed on 1 July 2024: "
                  f"{statistics.fmean(rep_share) * 100:.1f}% of answers")
        results.setdefault("asserted", {})[s] = {
            "top_provisions": dict(ordered),
            "repealed_code_share": statistics.fmean(rep_share) if rep_share else None}
        print()

    # ---- accuracy contrast (the headline number) ---------------------
    if "L7" in slices and "L1" in slices:
        l7 = resolved_only([r for r in recs if r["slice"] == "L7"])
        l1 = resolved_only([r for r in recs if r["slice"] == "L1"])
        if l7 and l1:
            diff = two_sample_bootstrap_diff(
                [float(r["majority_correct"]) for r in l1],
                [float(r["majority_correct"]) for r in l7],
                lambda v: sum(v) / len(v), n_boot=args.n_boot)
            results["accuracy_contrast"] = diff
            print("-" * 78)
            print("accuracy contrast (matched items, era reversed)")
            print(f"  L1 control  (law before 1 July 2024): "
                  f"{sum(r['majority_correct'] for r in l1) / len(l1):.3f}  (n = {len(l1)})")
            print(f"  L7 target   (law in force today)    : "
                  f"{sum(r['majority_correct'] for r in l7) / len(l7):.3f}  (n = {len(l7)})")
            print(f"  difference L1 - L7 = {diff['point']:+.3f} "
                  f"[{diff.get('lo', float('nan')):+.3f}, {diff.get('hi', float('nan')):+.3f}]  "
                  f"(paired by construction: same facts, same frames)")
            print()

    # ---- L1 minus L7 gaps -------------------------------------------
    if "L7" in slices and "L1" in slices:
        l7 = [r for r in recs if r["slice"] == "L7"]
        l1 = [r for r in recs if r["slice"] == "L1"]
        print("-" * 78)
        print("L1 minus L7 gap per method  (positive = the method works on ordinary items "
              "and collapses on the superseded-provision items)")
        rows = []
        for m in methods:
            g = bootstrap_auroc_diff(l1, l7, m, n_boot=args.n_boot)
            results["gaps"][m] = g
            rows.append([METHOD_LABEL[m], f"{g['point']:+.3f}",
                         f"[{g.get('lo', float('nan')):+.3f}, {g.get('hi', float('nan')):+.3f}]",
                         "yes" if g.get("ci_excludes_zero") else "no",
                         f"{g.get('p_le_zero', float('nan')):.4f}"])
        print(markdown_table(rows, ["method", "gap", "95% CI", "CI excludes 0", "P(gap <= 0)"]))
        print()

    # ---- gate verdict ------------------------------------------------
    verdict = gate_verdict(results)
    results["judge_coverage"] = {
        "n_items": len(recs),
        "n_scored": len(usable),
        "share_scored": (len(usable) / len(recs)) if recs else float("nan"),
        "note": "unresolved answers are excluded from every metric in this report",
    }
    results["gate_G1"] = verdict
    print("=" * 78)
    print("GATE G1 VERDICT:", "PASS" if verdict["pass"] else "NOT YET")
    for r in verdict["reasons"]:
        print("  -", r)
    print()
    print(verdict["reading"])
    print("=" * 78)

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "e1_report.json").write_text(json.dumps(results, indent=2) + "\n")
    print(f"wrote {out_dir / 'e1_report.json'}")
    print("next: python scripts/04_make_figure.py --run-id " + args.run_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
