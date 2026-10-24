"""Attach typed relation clustering to a stored Phase A/Phase C run."""
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
from jurisuq.relations.stats import typed_stats  # noqa: E402


def tree_hash(directory: pathlib.Path) -> str:
    h = hashlib.sha256()
    for path in sorted(directory.rglob("*")):
        if path.is_file():
            h.update(path.name.encode("utf-8"))
            h.update(hashlib.sha256(path.read_bytes()).digest())
    return h.hexdigest()[:24]


def sha256_file(path: pathlib.Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def context_for(record: dict) -> dict:
    return {
        "as_of": "2024-01-01" if record["slice"] == "L1" else "2026-10-01",
        "jurisdiction": "IN",
        "crosswalk_relation": None,
    }


def exact_agreement(keys: list[str]) -> float:
    if not keys:
        return float("nan")
    counts = collections.Counter(k for k in keys if k != "NONE")
    return max(counts.values(), default=0) / len(keys)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--out-suffix", default="+typed")
    ap.add_argument("--checkpoint", default=None)
    ap.add_argument("--config", default=str(ROOT / "configs" / "phase_b_relations.json"))
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--progress", type=int, default=10)
    ap.add_argument("--runs-dir", default="runs")
    args = ap.parse_args()

    runs_dir = pathlib.Path(args.runs_dir)
    if not runs_dir.is_absolute():
        runs_dir = ROOT / runs_dir
    source = runs_dir / args.run_id
    source_items = source / "items.jsonl"
    if not source_items.exists():
        print(f"ERROR: no source run: {source_items}")
        return 1
    output = runs_dir / f"{args.run_id}{args.out_suffix}"
    if output.exists() and not args.force:
        print(f"ERROR: {output} already exists (use --force or another suffix)")
        return 1

    checkpoint = pathlib.Path(args.checkpoint) if args.checkpoint else (
        ROOT / "models" / "relation" /
        "relations_v1-InLegalBERT-phaseB-relations-full")
    if not checkpoint.is_absolute():
        checkpoint = ROOT / checkpoint
    config_path = pathlib.Path(args.config)
    if not config_path.is_absolute():
        config_path = ROOT / config_path
    if not checkpoint.exists():
        print(f"ERROR: checkpoint not found: {checkpoint}")
        return 1
    config = json.loads(config_path.read_text(encoding="utf-8"))
    source_before = tree_hash(source)
    model, tokenizer, meta = M.load_checkpoint(checkpoint)
    if "merge_threshold" not in meta:
        print("ERROR: checkpoint metadata has no merge_threshold")
        return 1
    tau = float(meta["merge_threshold"])
    records = [json.loads(line) for line in source_items.read_text(
        encoding="utf-8").splitlines() if line.strip()]
    if args.limit:
        records = records[:args.limit]

    scored = []
    skipped = []
    changed_ids = []
    n_clusters = collections.Counter()
    encoder_pairs = rule_pairs = 0
    started = time.time()
    for index, record in enumerate(records, 1):
        texts = record.get("sample_texts") or []
        keys = record.get("asserted_keys") or []
        if not texts or len(texts) != len(keys):
            skipped.append(record.get("item_id"))
            continue
        result = M.score_samples(
            model, tokenizer, texts, [None] * len(texts), context_for(record),
            config, keys=keys, tau=tau)
        cluster = typed_cluster(
            keys, result["relation"], result["merge_score"], result["tau"])
        stats = typed_stats(cluster, result["relation"], keys)
        record["clusters"] = cluster.labels
        record["cluster_provisions"] = cluster.canonical
        record["relation_matrix"] = result["relation"]
        record["relation_scores"] = [
            [round(float(value), 6) for value in row]
            for row in result["merge_score"]
        ]
        record["typed_stats"] = stats
        record["typed_provenance"] = {
            "checkpoint": str(checkpoint),
            "tau": tau,
            "schema": "pb1",
            "serialisation": "ser1",
            "cluster_representation": "typed",
            "script": "13_attach_typed.py",
        }
        n_clusters[stats["n_clusters"]] += 1
        encoder_pairs += result.get("encoder_pairs", 0)
        rule_pairs += result.get("rule_pairs", 0)
        if stats["agreement"] != exact_agreement(keys):
            changed_ids.append(record.get("item_id"))
        scored.append(record)
        if args.progress and (index % args.progress == 0 or index == len(records)):
            elapsed = time.time() - started
            rate = index / elapsed if elapsed else 0.0
            eta = (len(records) - index) / rate if rate else 0.0
            print(f"typed {index}/{len(records)} items  {elapsed:5.0f}s elapsed  "
                  f"{rate:4.1f} items/s  eta {eta / 60:4.1f} min", flush=True)

    source_after = tree_hash(source)
    if source_before != source_after:
        print("ERROR: source run changed during typed attachment; refusing to write")
        return 1
    dataset = ROOT / "data" / "lexuq_slice.jsonl"
    statutes = ROOT / "data" / "statutes" / "statutes_v1.jsonl"
    links = ROOT / "data" / "relations" / "crosswalk_v1.jsonl"
    report = {
        "run_id": f"{args.run_id}{args.out_suffix}",
        "source_run": args.run_id,
        "n_scored": len(scored),
        "n_skipped": len(skipped),
        "skipped_item_ids": skipped,
        "encoder_pairs": encoder_pairs,
        "rule_pairs": rule_pairs,
        "seconds": round(time.time() - started, 1),
        "changed_agreement_item_ids": changed_ids[:50],
        "changed_agreement_item_ids_capped": len(changed_ids) > 50,
        "changed_agreement_count": len(changed_ids),
        "n_clusters_distribution": dict(sorted(n_clusters.items())),
        "checkpoint": str(checkpoint),
        "tau": tau,
        "source_tree_hash_before": source_before,
        "source_tree_hash_after": source_after,
        "source_run_untouched": source_before == source_after,
        "dataset_sha256": sha256_file(dataset),
        "statutes_sha256": sha256_file(statutes),
        "links_sha256": sha256_file(links),
    }
    output.mkdir(parents=True, exist_ok=True)
    with (output / "items.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
        for record in scored:
            handle.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
    (output / "typed_report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    (output / "meta.json").write_text(json.dumps({
        "run_id": report["run_id"],
        "phase": "B",
        "source_run": args.run_id,
        "checkpoint": str(checkpoint),
        "tau": tau,
        "dataset_sha256": report["dataset_sha256"],
        "statutes_sha256": report["statutes_sha256"],
        "links_sha256": report["links_sha256"],
        "source_tree_hash": source_after,
        "source_run_untouched": report["source_run_untouched"],
    }, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"typed {len(scored)} items -> {output}")
    print(f"  skipped {len(skipped)}  changed agreement {len(changed_ids)}"
          f" (IDs capped at 50: {len(changed_ids) > 50})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
