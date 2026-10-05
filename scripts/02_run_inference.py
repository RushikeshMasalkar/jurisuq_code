#!/usr/bin/env python3
"""02 - sampling harness. Produces the per-item record that E1 analyses.

For every item: draw M samples from the generator, resolve each sample's
correctness offline, cluster the samples with each enabled channel, and write
one JSON record per item.

What is recorded per item
-------------------------
``methods``          uncertainty scores, one per sample-only method:
                     * ``disc_se``  discrete semantic entropy, bits        [SE24]
                     * ``se``       standard (entailment) semantic entropy, bits [SE24]
                     * ``selfcheck`` SelfCheckGPT-style contradiction mass   [SELFCHECK]
                     * ``agreement`` 1 - top cluster probability (discrete)
                     * ``p_true``   1 - length-normalised sequence probability, when
                                    the server exposes logprobs (null otherwise)
``majority_correct`` 1/0 for the answer the system would return (majority cluster)
``frac_correct``     fraction of samples that are correct (diagnostic only)
``all_same``         1 when every sample falls in one discrete cluster - the
                     collision population that E1 is about

The record keeps every sampled answer and its verdict, so any later analysis
can be re-run without touching the model again. That is deliberate: sampling is
the expensive step, analysis is free.

    python scripts/02_run_inference.py --config configs/phase_a.json
    python scripts/02_run_inference.py --set provider=mock --set limit=40   # smoke test
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jurisuq.cluster import make_clusterer
from jurisuq.config import Config, add_common_args, config_from_args, ROOT
from jurisuq.generators import (PROMPT_VERSION, OpenAICompatGenerator,
                                make_generator)
from jurisuq.judge import label_summary, make_judge
from jurisuq.pipeline import build_record


# ----------------------------------------------------------------------
def load_items(cfg: Config) -> list[dict]:
    path = ROOT / "data" / "lexuq_slice.jsonl"
    if not path.exists():
        raise SystemExit("data/lexuq_slice.jsonl not found - run scripts/01_make_data.py first")
    items = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    items = [i for i in items if i["slice"] in cfg.slices]
    if cfg.limit:
        items = items[: cfg.limit]
    return items


def load_done(items_path: Path) -> set[str]:
    if not items_path.exists():
        return set()
    done = set()
    for line in items_path.read_text().splitlines():
        if line.strip():
            try:
                done.add(json.loads(line)["item_id"])
            except Exception:
                continue
    return done


# ----------------------------------------------------------------------
def score_item(item: dict, cfg: Config, gen, judge, clusterers) -> dict:
    """Sample the item, then hand the answers to the shared scoring pipeline."""
    samples = gen.sample(item["question"], cfg.n_samples,
                         meta={"slice": item["slice"], "template": item["template"],
                               "trap_act": item.get("trap_act"),
                               "trap_provision": item.get("trap_provision"),
                               "distractor_provision": item.get("distractor_provision"),
                               "punishment": item.get("punishment"),
                               "gold_act": item["gold_act"],
                               "gold_provision": item["gold_provision"]})
    texts = [s.text for s in samples]
    rec = build_record(item, texts, cfg, judge, clusterers,
                       n_tokens=[s.n_tokens for s in samples],
                       logprobs=[s.mean_logprob for s in samples])
    rec["gen_latency_s"] = sum(s.latency_s for s in samples)
    return rec


# ----------------------------------------------------------------------
def main() -> int:
    ap = add_common_args(argparse.ArgumentParser())
    args = ap.parse_args()
    cfg = config_from_args(args)
    run = cfg.run_dir()

    items = load_items(cfg)
    items_path = run / "items.jsonl"
    done = load_done(items_path)
    todo = [i for i in items if i["item_id"] not in done]

    gen = make_generator(cfg)
    judge = make_judge(cfg, gen)
    discrete, entail, backend_name = make_clusterer(cfg)

    meta = {
        "run_id": cfg.run_id,
        "phase": "A",
        "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "provider": gen.name,
        "n_samples": cfg.n_samples,
        "temperature": cfg.temperature,
        "nli_backend": backend_name,
        "judge": judge.method,
        "prompt_version": PROMPT_VERSION,
        "system_prompt": OpenAICompatGenerator.SYSTEM,
        "slices": cfg.slices,
        "n_items": len(items),
        "n_todo": len(todo),
        "n_resumed": len(done),
        "config": {k: v for k, v in cfg.__dict__.items()},
    }
    (run / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")

    print(f"run        : {run}")
    print(f"generator  : {gen.name}")
    print(f"clustering : discrete{'' if entail is None else ' + ' + backend_name}")
    print(f"judge      : {judge.method}")
    print(f"items      : {len(items)}  (todo {len(todo)}, already done {len(done)})")
    if entail is not None and backend_name == "lexical-proxy":
        print("NOTE: lexical-proxy clustering is a plumbing stand-in, not standard semantic "
              "entropy. Install transformers+torch for the real NLI channel, or report the "
              "discrete channel only.")
    print("-" * 68)

    t0 = time.time()
    with items_path.open("a") as fh:
        def work(it):
            try:
                return score_item(it, cfg, gen, judge, (discrete, entail))
            except Exception as exc:
                return {"item_id": it["item_id"], "slice": it["slice"], "error": repr(exc)}

        if cfg.workers > 1:
            with ThreadPoolExecutor(max_workers=cfg.workers) as pool:
                stream = pool.map(work, todo)
                for k, rec in enumerate(stream, start=1):
                    fh.write(json.dumps(rec) + "\n")
                    fh.flush()
                    if k % 5 == 0 or k == len(todo):
                        print(f"  {k}/{len(todo)} items   elapsed {time.time() - t0:6.0f}s")
        else:
            for k, it in enumerate(todo, start=1):
                rec = work(it)
                fh.write(json.dumps(rec) + "\n")
                fh.flush()
                if k % 5 == 0 or k == len(todo):
                    el = time.time() - t0
                    eta = el / k * (len(todo) - k)
                    print(f"  {k}/{len(todo)} items   elapsed {el:6.0f}s   eta {eta:6.0f}s")

    meta["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    meta["elapsed_s"] = round(time.time() - t0, 1)
    (run / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")

    print("-" * 68)
    print(f"wrote {items_path}  ({len(todo)} new records, {meta['elapsed_s']}s)")

    # the judge is the component that silently spoils a run, so its behaviour is
    # printed here, at the end of the expensive step, not only in the analysis
    all_recs = [json.loads(l) for l in items_path.read_text().splitlines() if l.strip()]
    summ = label_summary(all_recs)
    meta["judge_summary"] = summ
    (run / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    print("-" * 68)
    print("correctness resolver (judge) behaviour:")
    for lab, n in sorted(summ["counts"].items(), key=lambda kv: -kv[1]):
        print(f"    {lab:<28} {n:6d}   {n / max(1, sum(summ['counts'].values())) * 100:5.1f}%")
    res_rate = 1.0 - sum(v for k, v in summ["shares"].items()
                         if k in ("unresolved", "ambiguous", "only_superseded_mentioned"))
    print(f"    resolved share               {res_rate * 100:5.1f}%")
    if res_rate < 0.7:
        print()
        print("WARNING: fewer than 70% of answers could be resolved by the deterministic judge.")
        print("         The accuracy figure is not meaningful yet. Options, cheapest first:")
        print("           1) python scripts/05_rejudge.py --run-id " + cfg.run_id)
        print("              (re-scores the stored answers; no re-sampling)")
        print("           2) --set judge=llm   to route unresolved answers to a prompted judge")
        print("           3) --set max_tokens=180 so answers stop mid-reasoning less often")
    print("next: python scripts/03_analyze_e1.py --run-id " + cfg.run_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
