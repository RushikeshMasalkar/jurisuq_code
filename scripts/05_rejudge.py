#!/usr/bin/env python3
"""05 - re-judge stored answers, and diagnose the judge. No re-sampling.

Why this exists: sampling is the expensive step (hours), judging is cheap
(seconds) and depends only on the text of the answers, which ``items.jsonl``
stores. So when the judge turns out to be too strict - or when you want the LLM
judge instead - you re-score the same answers instead of running the model
again.

Two modes:

    python scripts/05_rejudge.py --run-id phaseA-laptop --inspect
        Report only: how the current judge scored the stored answers, per slice,
        with examples. Use this first when accuracy looks implausible.

    python scripts/05_rejudge.py --run-id phaseA-laptop
        Re-score every stored answer with the current judge code, recompute the
        uncertainty methods, and write a new run directory
        ``runs/<run_id>-rejudged/``. The original run is never modified.

The new directory then behaves exactly like a fresh run:

    python scripts/03_analyze_e1.py --run-id phaseA-laptop-rejudged
    python scripts/04_make_figure.py  --run-id phaseA-laptop-rejudged
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jurisuq.cluster import make_clusterer
from jurisuq.config import Config, add_common_args, config_from_args, ROOT
from jurisuq.judge import UNRESOLVED_LABELS, label_summary, make_judge
from jurisuq.pipeline import build_record, item_from_record

def load(run_dir: Path) -> list[dict]:
    path = run_dir / "items.jsonl"
    if not path.exists():
        raise SystemExit(f"{path} not found")
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def inspect(recs: list[dict], n_examples: int = 3) -> None:
    usable = [r for r in recs if "error" not in r and r.get("sample_texts")]
    print("=" * 78)
    print("JUDGE DIAGNOSIS")
    print("=" * 78)
    print(f"records: {len(recs)}   with stored answers: {len(usable)}")
    print()

    summ = label_summary(usable)
    total = sum(summ["counts"].values()) or 1
    print("verdict labels over all stored answers")
    for lab, n in sorted(summ["counts"].items(), key=lambda kv: -kv[1]):
        print(f"    {lab:<30} {n:7d}   {n / total * 100:5.1f}%")
    print()

    for sl in sorted({r["slice"] for r in usable}):
        sub = [r for r in usable if r["slice"] == sl]
        c = collections.Counter()
        for r in sub:
            for lab in r.get("sample_verdict_labels") or []:
                c[lab.split("|")[-1]] += 1
        tot = sum(c.values()) or 1
        unres = sum(v for k, v in c.items() if k in UNRESOLVED_LABELS)
        wrong = sum(v for k, v in c.items() if k.startswith("wrong"))
        print(f"slice {sl}: answers = {tot}   unresolved = {unres / tot * 100:5.1f}%   "
              f"asserted-wrong = {wrong / tot * 100:5.1f}%")
        print("    " + ", ".join(f"{k}={v}" for k, v in c.most_common(8)))
    print()

    print(f"first {n_examples} answers with their verdict, so the failure is visible")
    for sl in sorted({r["slice"] for r in usable}):
        shown = 0
        for r in usable:
            if r["slice"] != sl or shown >= n_examples:
                continue
            txt = (r["sample_texts"][0] if r["sample_texts"] else "")[:260].replace("\n", " ")
            print(f"  [{sl}] {r['item_id']}  gold = {r['gold'].get('act')} "
                  f"{r['gold'].get('provision')}")
            print(f"      answer : {txt}")
            print(f"      verdict: {r['sample_verdict_labels'][0]}  "
                  f"({r['sample_verdict_reasons'][0]})")
            shown += 1
        print()

    print("how to read this")
    print("  * unresolved > 10-15%  -> the judge cannot see the provision in the answer.")
    print("      Look at the examples above: if the answer *does* name a section, it is a")
    print("      parser bug - re-run this script without --inspect to re-score and see if the")
    print("      new judge resolves them. If the answers genuinely name no section, the model")
    print("      is not answering the question, and the prompt or max_tokens is the issue.")
    print("  * asserted-wrong near 100% on BOTH slices -> the judge is rejecting the in-force")
    print("      provision, which is the bug this script exists to fix.")
    print("  * asserted-wrong high on L7 and low on L1 -> that is the real, expected pattern.")
    print("=" * 78)


def main() -> int:
    ap = add_common_args(argparse.ArgumentParser())
    ap.add_argument("--inspect", action="store_true", help="report only, do not rewrite")
    ap.add_argument("--out-suffix", default="-rejudged")
    args = ap.parse_args()
    cfg = config_from_args(args)

    src = ROOT / cfg.out_dir / cfg.run_id
    recs = load(src)
    if args.inspect:
        inspect(recs)
        return 0

    out_id = cfg.run_id + args.out_suffix
    out = ROOT / cfg.out_dir / out_id
    out.mkdir(parents=True, exist_ok=True)

    judge = make_judge(cfg, generator=None) if cfg.judge == "provision" else None
    if judge is None:
        print("judge=llm needs a live generator; re-judging with the deterministic judge only.")
        cfg.judge = "provision"
        judge = make_judge(cfg, generator=None)
    discrete, entail, backend_name = make_clusterer(cfg)

    new_recs = []
    for r in recs:
        if "error" in r or not r.get("sample_texts"):
            continue
        item = item_from_record(r)
        # carry the original sampling metadata across so the new run stays
        # comparable with the old one
        rec = build_record(item, r["sample_texts"], cfg, judge, (discrete, entail))
        rec["rejudged_from"] = cfg.run_id
        rec["gen_latency_s"] = r.get("gen_latency_s", 0.0)
        new_recs.append(rec)

    with (out / "items.jsonl").open("w") as fh:
        for rec in new_recs:
            fh.write(json.dumps(rec) + "\n")

    meta_path = src / "meta.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    meta.update({
        "run_id": out_id,
        "rejudged_from": cfg.run_id,
        "rejudged_with_judge": judge.method,
        "nli_backend": backend_name,
        "note": "answers are the original samples; only judging and scoring were recomputed",
    })
    (out / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")

    summ = label_summary(new_recs)
    total = sum(summ["counts"].values()) or 1
    print(f"re-judged {len(new_recs)} items -> {out}")
    print("new verdict mix:")
    for lab, n in sorted(summ["counts"].items(), key=lambda kv: -kv[1]):
        print(f"    {lab:<30} {n:7d}   {n / total * 100:5.1f}%")
    print()
    print(f"next: python scripts/03_analyze_e1.py --run-id {out_id}")
    print(f"      python scripts/04_make_figure.py  --run-id {out_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
