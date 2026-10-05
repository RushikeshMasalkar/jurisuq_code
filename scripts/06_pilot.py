#!/usr/bin/env python3
"""06 - pilot: validate the judge and the prompt on 12 items before the real run.

Twenty minutes of model time that can save a night. It samples a handful of
items from both slices and prints, for each one, what the model actually
answered and how the judge scored it. Then it reports:

  * judge coverage   - the share of sampled answers the judge could resolve.
                       Below 0.85 the full run is not worth starting: fix the
                       judge or the prompt first.
  * verdict mix      - how many answers were correct, stale, premature,
                       foreign, or unresolvable.
  * a preview of E1  - the accuracy of each slice, which tells you whether the
                       benchmark is answerable at all. A slice where *nothing*
                       is correct cannot support the AUROC comparison, and you
                       want to learn that now, on 24 items, not after a full run.

Run it against any model:

    python scripts/06_pilot.py --set model=qwen2.5-7b-instruct
    python scripts/06_pilot.py --set model=llama-3.1-8b-instruct --set n_samples=2

Exit code is 0 when the pilot passes, 1 when it does not, so it can gate a
scripted full run.
"""
from __future__ import annotations

import argparse
import collections
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jurisuq.cluster import cluster_stats, make_clusterer
from jurisuq.config import Config, add_common_args, config_from_args, ROOT
from jurisuq.generators import make_generator
from jurisuq.judge import UNRESOLVED_LABELS, make_judge
from jurisuq.pipeline import build_record

COVERAGE_MIN = 0.85


def first_line(text: str, n: int = 96) -> str:
    line = (text or "").strip().splitlines()[0] if (text or "").strip() else ""
    return line[:n]


def main() -> int:
    ap = add_common_args(argparse.ArgumentParser())
    ap.add_argument("--items-per-slice", type=int, default=12)
    ap.add_argument("--samples", type=int, default=3, help="M for the pilot (small on purpose)")
    ap.add_argument("--show", type=int, default=12, help="how many items to print in full")
    args = ap.parse_args()

    cfg = config_from_args(args)
    cfg.n_samples = args.samples
    cfg.run_id = cfg.run_id if cfg.run_id != "phaseA-smoke" else "phaseA-pilot"

    path = ROOT / "data" / "lexuq_slice.jsonl"
    if not path.exists():
        raise SystemExit("data/lexuq_slice.jsonl not found - run scripts/01_make_data.py first")
    items = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]

    per_slice = args.items_per_slice
    chosen = []
    for s in ("L7", "L1"):
        sub = [i for i in items if i["slice"] == s]
        chosen += sub[:per_slice]
    chosen.sort(key=lambda i: (i["slice"], i["item_id"]))

    gen = make_generator(cfg)
    judge = make_judge(cfg, gen)
    discrete, entail, _backend = make_clusterer(cfg)
    clusterers = (discrete, entail)

    print("=" * 78)
    print("PILOT - does the judge read the answers, and is the slice answerable?")
    print("=" * 78)
    print(f"generator : {gen.name}")
    print(f"prompt    : p2-structured (see meta.json of a full run for the exact text)")
    print(f"judge     : {judge.method}")
    print(f"items     : {len(chosen)}  ({per_slice} per slice)     samples per item: {cfg.n_samples}")
    print(f"temperature: {cfg.temperature}   max_tokens: {cfg.max_tokens}")
    print("-" * 78)

    t0 = time.time()
    recs = []
    for k, it in enumerate(chosen, start=1):
        samples = gen.sample(it["question"], cfg.n_samples,
                             meta={"slice": it["slice"], "template": it["template"],
                                   "trap_act": it.get("trap_act"),
                                   "trap_provision": it.get("trap_provision"),
                                   "distractor_provision": it.get("distractor_provision"),
                                   "punishment": it.get("punishment"),
                                   "gold_act": it["gold_act"],
                                   "gold_provision": it["gold_provision"]})
        rec = build_record(it, [s.text for s in samples], cfg, judge, clusterers,
                           n_tokens=[s.n_tokens for s in samples],
                           logprobs=[s.mean_logprob for s in samples])
        recs.append(rec)
        print(f"[{k}/{len(chosen)}] {it['item_id']}   asks: {it['asked_about']}")
        print(f"    gold     : {it['gold_act']}, section {it['gold']['provision']} "
              f"({it['gold']['label']})")
        if k <= args.show:
            for i, (txt, v) in enumerate(zip(rec["sample_texts"], rec["sample_verdict_labels"])):
                mark = {"gold": "OK ", "wrong_section": "WRG", "stale_law": "STALE",
                        "stale_law_act_only": "STALE", "premature_law": "NEW",
                        "non_indian_act": "FOREIGN"}.get(v, "?  ")
                print(f"    sample {i} [{mark}] {first_line(txt)}")
                if i == 0:
                    print(f"              verdict: {v} ({rec['sample_verdict_reasons'][0]})")
        print(f"    -> judged: {rec['sample_verdict_labels'][0]}   "
              f"answerability: {rec['frac_correct']:.2f} of samples correct   "
              f"disc_SE: {rec['methods']['disc_se']:.2f} bits")
        print()
    dt = time.time() - t0

    # ---------------- summary ----------------
    labels = collections.Counter()
    for r in recs:
        for lab in r["sample_verdict_labels"]:
            labels[lab.split("|")[-1]] += 1
    total = sum(labels.values()) or 1
    unresolved = sum(v for k, v in labels.items() if k in UNRESOLVED_LABELS)
    coverage = 1 - unresolved / total

    print("=" * 78)
    print("PILOT SUMMARY")
    print("=" * 78)
    print(f"wall time          : {dt:.0f}s for {len(recs) * cfg.n_samples} sampled answers "
          f"({dt / max(1, len(recs) * cfg.n_samples):.1f}s per answer)")
    print(f"judge coverage     : {coverage * 100:.1f}%   (need >= {COVERAGE_MIN * 100:.0f}%)")
    print("verdict mix        : " + ", ".join(f"{k}={v}" for k, v in labels.most_common()))
    errors = {k: v for k, v in labels.items() if k not in UNRESOLVED_LABELS and not k.startswith("gold")}
    print(f"error kinds seen   : {errors if errors else 'none'}")
    print()
    print("per slice:")
    for s in ("L7", "L1"):
        sub = [r for r in recs if r["slice"] == s]
        if not sub:
            continue
        frac = statistics.fmean(r["frac_correct"] for r in sub)
        same = sum(r["all_same"] for r in sub)
        print(f"  {s}: {len(sub)} items   per-sample accuracy = {frac:.2f}   "
              f"items where every sample was identical = {same}/{len(sub)}")
    print()

    ok = True
    if coverage < COVERAGE_MIN:
        ok = False
        print("FAIL - judge coverage too low. The judge cannot read the answers.")
        print("       Compare the printed samples with their verdicts above. If the answer names a")
        print("       provision and the verdict says unresolved, that is a parser gap - send me that")
        print("       line and I will extend the judge. If the answers name nothing, the answer")
        print("       format is being ignored: run with --set max_tokens=400.")
    l7 = [r for r in recs if r["slice"] == "L7"]
    l1 = [r for r in recs if r["slice"] == "L1"]
    if l7 and l1:
        acc7 = statistics.fmean(r["frac_correct"] for r in l7)
        acc1 = statistics.fmean(r["frac_correct"] for r in l1)
        if acc1 < 0.20:
            ok = False
            print(f"FAIL - the control slice L1 is barely answerable (accuracy {acc1:.2f}).")
            print("       Without correct answers on L1 there is nothing to contrast the collapse")
            print("       against, and AUROC will be undefined. Try another checkpoint before")
            print("       spending the night on a full run.")
        elif acc7 > 0.80:
            print(f"WARN - the model is accurate on L7 as well ({acc7:.2f}). It may simply know the")
            print("       new codes; the common-mode phenomenon needs a model that does not. Keep")
            print("       the result, and run the pilot again with a smaller or older checkpoint.")
        if acc1 - acc7 < 0.10 and acc1 >= 0.20:
            print(f"WARN - the L1-minus-L7 accuracy gap is small ({acc1 - acc7:+.2f}). Read the full")
            print("       run before concluding anything; the pilot has only "
                  f"{len(recs) * cfg.n_samples} answers.")
    if ok:
        print("PASS - the judge reads the answers and both slices behave as designed.")
        print("       Next: python scripts/02_run_inference.py --config configs/phase_a.json")
    print("=" * 78)

    out = ROOT / cfg.out_dir / (cfg.run_id + "-pilot")
    out.mkdir(parents=True, exist_ok=True)
    (out / "pilot_items.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in recs))
    print(f"records written to {out / 'pilot_items.jsonl'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
