"""12_eval_relation.py -- evaluate the relation model and run the E2 separation test.

    python scripts/12_eval_relation.py --run-id phaseB-relations-01 \
        --phase-a-run phaseA-laptop-v2-rejudged

Two outputs, one report:

  * the frozen test-split metrics (per-class P/R/F1, macro-F1, merge precision,
    the exact-key baseline, the confusion matrix);
  * the E2 separation test, which re-clusters the *stored* Phase A samples
    read-only and asks whether typed structure changes the collision population.

Gate G2 passes when: merge precision >= threshold, macro-F1 beats the exact-key
baseline, at least one separation criterion fires, and Phase A's stored numbers
are unchanged after the run (checked by re-hashing the run directory).
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from jurisuq.relations import model as M  # noqa: E402
from jurisuq.relations.cluster_typed import typed_cluster  # noqa: E402
from jurisuq.relations.schema import (LABEL2IDX, OPERATIONAL, PairRecord,  # noqa: E402
                                      text_hash)
from jurisuq.relations.stats import (confusion as _confusion, exact_key_baseline,  # noqa: E402
                                     merge_effect, per_class, typed_stats)


def tree_hash(d: pathlib.Path) -> str:
    h = hashlib.sha256()
    for p in sorted(d.rglob("*")):
        if p.is_file():
            h.update(p.name.encode())
            h.update(hashlib.sha256(p.read_bytes()).digest())
    return h.hexdigest()[:24]


def rule_relations(keys_a: list[str], keys_b: list[str], crosswalk: dict) -> str:
    """A relation without a model: identity, declared crosswalk link, else different."""
    if keys_a != "NONE" and keys_a == keys_b:
        return "SAME_PROVISION"
    if crosswalk.get((keys_a, keys_b)) or crosswalk.get((keys_b, keys_a)):
        return "LEGALLY_EQUIVALENT"
    if keys_a == "NONE" or keys_b == "NONE":
        return "AMBIGUOUS"
    return "DIFFERENT_PROVISION"


def load_crosswalk(path: pathlib.Path) -> dict:
    if not path.exists():
        return {}
    out = {}
    for line in path.read_text().splitlines():
        r = json.loads(line)
        out[(r["from"], r["to"])] = r.get("type", "successor_of")
    return out


def e2_separation(phase_a_dir: pathlib.Path, model=None, tokenizer=None, meta=None,
                  cfg=None, crosswalk=None, limit_items: int = 0,
                  progress_every: int = 10) -> dict:
    """Re-cluster the stored Phase A answers read-only and compare populations."""
    path = phase_a_dir / "items.jsonl"
    rows = [json.loads(l) for l in path.read_text().splitlines()]
    if limit_items:
        rows = rows[:limit_items]
    by_slice: dict[str, list[dict]] = collections.defaultdict(list)
    changed: list[str] = []
    encoder_pairs = rule_pairs = 0
    t_start = time.time()
    for n_done, rec in enumerate(rows, 1):
        if progress_every and (n_done % progress_every == 0 or n_done == len(rows)):
            el = time.time() - t_start
            rate = n_done / el if el else 0.0
            eta = (len(rows) - n_done) / rate if rate else 0.0
            print(f"    E2 {n_done}/{len(rows)} items  {el:5.0f}s elapsed  "
                  f"{rate:4.1f} items/s  eta {eta / 60:4.1f} min", flush=True)
        texts = rec.get("sample_texts") or []
        keys = rec.get("asserted_keys") or []
        if not texts or len(keys) != len(texts):
            continue
        m = len(texts)
        ctx = {"as_of": "2024-01-01" if rec["slice"] == "L1" else "2026-10-01",
               "jurisdiction": "IN", "crosswalk_relation": None}
        if model is not None:
            out = M.score_samples(model, tokenizer, texts, [None] * len(texts), ctx, cfg,
                                  keys=keys, tau=meta.get("merge_threshold"))
            result = typed_cluster(keys, out["relation"], out["merge_score"], out["tau"])
            encoder_pairs += out.get("encoder_pairs", 0)
            rule_pairs += out.get("rule_pairs", 0)
        else:
            relation = [[rule_relations(keys[i], keys[j], crosswalk or {}) for j in range(m)]
                        for i in range(m)]
            score = [[1.0 if relation[i][j] == "SAME_PROVISION" else
                      (0.9 if relation[i][j] == "LEGALLY_EQUIVALENT" else 0.0)
                      for j in range(m)] for i in range(m)]
            result = typed_cluster(keys, relation, score, 0.5)
            out = {"relation": relation, "merge_score": score}
        typed = typed_stats(result, out["relation"], keys)
        exact = typed_stats(typed_cluster(keys,
                                          [[("SAME_PROVISION" if keys[i] == keys[j] and keys[i] != "NONE"
                                             else "DIFFERENT_PROVISION") for j in range(m)]
                                           for i in range(m)],
                                          [[1.0] * m for _ in range(m)], 0.5), None, keys)
        eff = merge_effect(exact, typed)
        by_slice[rec["slice"]].append({
            "item_id": rec["item_id"], "correct": int(rec.get("majority_correct", 0)),
            "exact_all_same": exact["all_same"], "typed_all_same": typed["all_same"],
            "exact_agreement": exact["agreement"], "typed_agreement": typed["agreement"],
            "typed_entropy": typed["entropy"], "typed_contradiction": typed.get("contradiction_mass"),
            "changed": int(eff["d_agreement"] != 0 or exact["all_same"] != typed["all_same"]),
        })
        if eff["d_agreement"] != 0 or exact["all_same"] != typed["all_same"]:
            changed.append(rec["item_id"])

    report = {"n_scored": sum(len(v) for v in by_slice.values()), "changed_items": len(changed),
              "changed_ids": changed[:50], "by_slice": {},
              "encoder_pairs": encoder_pairs, "rule_pairs": rule_pairs,
              "seconds": round(time.time() - t_start, 1)}
    for sl, items in by_slice.items():
        coll_exact = [i for i in items if i["exact_all_same"]]
        coll_typed = [i for i in items if i["typed_all_same"]]
        report["by_slice"][sl] = {
            "n": len(items),
            "exact_collision_n": len(coll_exact),
            "typed_collision_n": len(coll_typed),
            "exact_collision_acc": (sum(i["correct"] for i in coll_exact) / len(coll_exact))
            if coll_exact else None,
            "typed_collision_acc": (sum(i["correct"] for i in coll_typed) / len(coll_typed))
            if coll_typed else None,
            "reclassified_out_of_collision": len(
                [i for i in items if i["exact_all_same"] and not i["typed_all_same"]]),
        }
    # criterion 3: does the typed score rank correctness inside the collision population?
    pop = [i for sl in by_slice.values() for i in sl if i["exact_all_same"]]
    correct = [i["correct"] for i in pop]
    if len(set(correct)) == 2:
        from jurisuq.metrics import auroc
        report["collision_auroc_typed_entropy"] = auroc([i["typed_entropy"] for i in pop], correct)
    else:
        report["collision_auroc_typed_entropy"] = None
        report["collision_auroc_note"] = ("single correctness class inside the collision "
                                          "population: AUROC undefined")
    # criterion 2: does the unanimous-population accuracy gap narrow?
    gaps = {}
    for sl, items in by_slice.items():
        coll = [i for i in items if i["typed_all_same"]]
        gaps[sl] = (sum(i["correct"] for i in coll) / len(coll)) if coll else None
    if gaps.get("L1") is not None and gaps.get("L7") is not None:
        report["typed_unanimous_accuracy_gap"] = gaps["L1"] - gaps["L7"]
    report["typed_unanimous_accuracy"] = gaps
    return report


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(ROOT / "configs" / "phase_b_relations.json"))
    ap.add_argument("--run-id", default="phaseB-relations-01")
    ap.add_argument("--phase-a-run", default="phaseA-laptop-v2-rejudged")
    ap.add_argument("--no-model", action="store_true",
                    help="use rule relations instead of the checkpoint (plumbing check)")
    ap.add_argument("--limit-items", type=int, default=0,
                    help="E2 over the first N Phase A items only (0 = all)")
    ap.add_argument("--progress", type=int, default=10,
                    help="print an E2 progress line every N items (0 = silent)")
    ap.add_argument("--skip-e2", action="store_true",
                    help="test-split metrics only; skip the E2 re-clustering")
    args = ap.parse_args()

    cfg = json.loads(pathlib.Path(args.config).read_text())
    ds_dir = pathlib.Path(cfg["dataset_dir"])
    manifest = json.loads((ds_dir / "manifest.json").read_text())
    test = [PairRecord.from_json(l) for l in (ds_dir / "test.jsonl").read_text().splitlines()]
    run_dir = ROOT / cfg["run_dir"] / args.run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    model = tokenizer = meta = None
    if not args.no_model:
        ckpt = sorted((ROOT / cfg["checkpoint_dir"]).glob(f"*-{args.run_id}"))
        if not ckpt:
            raise SystemExit(f"no checkpoint for run {args.run_id}; train first or pass --no-model")
        model, tokenizer, meta = M.load_checkpoint(ckpt[-1])
        cfg["merge_threshold"] = meta["merge_threshold"]
        probs = M.predict_proba(model, tokenizer, test, cfg)
        preds = [M.IDX2LABEL[max(range(len(p)), key=lambda k: p[k])] for p in probs]
    else:
        preds = ["SAME_PROVISION" if (r.key_a() == r.key_b() and r.key_a() != "NONE")
                 else "DIFFERENT_PROVISION" for r in test]
        meta = {"merge_threshold": 0.5, "encoder": "rule-baseline"}

    y_true = [r.label for r in test]
    mf1, rows = per_class(y_true, preds, OPERATIONAL)
    lbl = sorted(M.MERGE_RELATIONS)
    merge_true = [r.label if r.label in M.MERGE_RELATIONS else "DIFFERENT_PROVISION" for r in test]
    merge_pred = [p if p in M.MERGE_RELATIONS else "DIFFERENT_PROVISION" for p in preds]
    merge_f1, _merge_rows = per_class(merge_true, merge_pred,
                                      ("SAME_PROVISION", "DIFFERENT_PROVISION"))
    merge_prec = rows["SAME_PROVISION"]["precision"] if "SAME_PROVISION" in rows else None

    pa_dir = ROOT / cfg["run_dir"] / args.phase_a_run
    before = tree_hash(pa_dir) if pa_dir.exists() else None
    e2 = e2_separation(pa_dir, model, tokenizer, meta, cfg,
                       load_crosswalk(pathlib.Path(cfg["crosswalk_file"])),
                       limit_items=args.limit_items,
                       progress_every=args.progress) \
        if (pa_dir.exists() and not args.skip_e2) else {"skipped": True}
    after = tree_hash(pa_dir) if pa_dir.exists() else None

    report = {
        "run_id": args.run_id,
        "dataset_version": manifest.get("dataset_version"),
        "dataset_content_hash": manifest.get("content_hash"),
        "checkpoint": meta.get("encoder"),
        "merge_threshold": meta.get("merge_threshold"),
        "n_test": len(test),
        "macro_f1": round(mf1, 4),
        "per_class": rows,
        "merge_f1": round(merge_f1, 4),
        "merge_precision": merge_prec,
        "exact_key_baseline_macro_f1": round(exact_key_baseline(test, M.MERGE_RELATIONS), 4),
        "confusion": _confusion(y_true, preds, OPERATIONAL),
        "ambiguous_rate": round(sum(1 for p in preds if p == "AMBIGUOUS") / len(preds), 4),
        "e2_separation": e2,
        "phase_a_untouched": (before == after) if before else None,
        "phase_a_tree_hash_before": before,
        "phase_a_tree_hash_after": after,
    }
    gates = {
        "merge_precision_ok": (merge_prec or 0.0) >= cfg["gates"]["merge_precision_min"],
        "beats_exact_key": mf1 > report["exact_key_baseline_macro_f1"],
        "separation_criterion_met": bool(
            e2.get("changed_items") or
            (e2.get("typed_unanimous_accuracy_gap") is not None and
             e2["typed_unanimous_accuracy_gap"] < 0.882) or
            (e2.get("collision_auroc_typed_entropy") or 0) > 0.5),
        "phase_a_untouched": report["phase_a_untouched"] is not False,
    }
    report["gate_g2"] = {"conditions": gates,
                         "verdict": "PASS" if all(gates.values()) else "NOT YET"}
    (run_dir / "relation_report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(f"test n={len(test)}  macro-F1 {mf1:.3f}  merge precision {merge_prec}  "
          f"exact-key baseline {report['exact_key_baseline_macro_f1']:.3f}")
    if e2.get("skipped"):
        print("E2: skipped (--skip-e2)")
    else:
        print(f"E2: changed items {e2.get('changed_items')}  typed gap "
              f"{e2.get('typed_unanimous_accuracy_gap')}  "
              f"encoder pairs {e2.get('encoder_pairs')} / rule pairs {e2.get('rule_pairs')}  "
              f"({e2.get('seconds')}s)")
    print("GATE G2:", report["gate_g2"]["verdict"], gates)
    print(f"report: {run_dir.relative_to(ROOT)}/relation_report.json")


if __name__ == "__main__":
    main()
