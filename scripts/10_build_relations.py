"""10_build_relations.py -- build, verify and split the Phase B relation dataset.

    python scripts/10_build_relations.py --config configs/phase_b_relations.json
    python scripts/10_build_relations.py --verify-only
    python scripts/10_build_relations.py --export-for-human 300

Everything this script writes is derived and reproducible: the manifest records
the seed, the source mix, the counts and a sha256 per file, so any later run can
prove it used the same pairs.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from jurisuq.relations.pairs import (asserted_from_text, candidate_pairs,  # noqa: E402
                                     structural_verify)
from jurisuq.relations.schema import (LABEL2IDX, OPERATIONAL, SCHEMA_VERSION,  # noqa: E402
                                      STRATA, PairRecord, text_hash)


def load_config(path: str | pathlib.Path) -> dict:
    return json.loads(pathlib.Path(path).read_text())


def sha256_file(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_lines(records: list[PairRecord]) -> str:
    h = hashlib.sha256()
    for r in sorted(records, key=lambda r: r.pair_id):
        h.update(r.to_json().encode("utf-8") + b"\n")
    return h.hexdigest()


def split_by_topic(records: list[PairRecord], cfg: dict, seed: int) -> None:
    """Topic-disjoint splits; assignment is a deterministic function of the topic."""
    topics = sorted({r.provenance.get("topic", "unknown") for r in records})
    order = sorted(topics, key=lambda t: hashlib.sha256(f"{seed}|{t}".encode()).hexdigest())
    n_dev = max(1, round(len(order) * cfg["dev_topic_share"]))
    n_test = max(1, round(len(order) * cfg["test_topic_share"]))
    dev_topics = set(order[:n_dev])
    test_topics = set(order[n_dev:n_dev + n_test])
    for r in records:
        t = r.provenance.get("topic", "unknown")
        r.split = "test" if t in test_topics else ("dev" if t in dev_topics else "train")


def from_phase_a(records_dir: pathlib.Path, dataset_version: str,
                 per_item: int = 6) -> list[PairRecord]:
    """Real answer pairs from a Phase A run: same-provision and different-provision
    pairs are labelled by the extractor, so no human label is needed to build them."""
    path = records_dir / "items.jsonl"
    if not path.exists():
        raise SystemExit(f"no Phase A records at {path}")
    out: list[PairRecord] = []
    for line in path.read_text().splitlines():
        rec = json.loads(line)
        texts = rec.get("sample_texts") or []
        asserted = rec.get("asserted_keys")
        if not texts or not asserted:
            continue
        ctx = {"as_of": "2024-01-01" if rec.get("slice") == "L1" else "2026-10-01",
               "jurisdiction": "IN", "crosswalk_relation": None}
        taken = 0
        for i in range(len(texts)):
            if taken >= per_item:
                break
            for j in range(i + 1, len(texts)):
                if taken >= per_item:
                    break
                ka, kb = asserted[i], asserted[j]
                if ka == "NONE" or kb == "NONE":
                    continue
                label = "SAME_PROVISION" if ka == kb else "DIFFERENT_PROVISION"
                stratum = "S1" if ka == kb else "S5"
                a_assert = asserted_from_text(texts[i])
                b_assert = asserted_from_text(texts[j])
                if a_assert is None or b_assert is None:
                    continue            # a pair is only usable if both sides parse
                pair = PairRecord(
                    pair_id=f"obs-{text_hash(texts[i] + texts[j])}",
                    dataset_version=dataset_version, split="train", stratum=stratum,
                    answer_a={"text": texts[i], "asserted": a_assert},
                    answer_b={"text": texts[j], "asserted": b_assert},
                    context=ctx, label=label, label_source="rule",
                    provenance={"generator": "phaseA", "topic": rec.get("topic"),
                                "item_id": rec.get("item_id")},
                    verifier="rule", text_hash=text_hash(texts[i] + texts[j]))
                pair.validate()
                out.append(pair)
                taken += 1
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(ROOT / "configs" / "phase_b_relations.json"))
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--verify-only", action="store_true")
    ap.add_argument("--export-for-human", type=int, default=0)
    ap.add_argument("--source", default=None, choices=["synthetic", "phaseA", "both"])
    args = ap.parse_args()

    cfg = load_config(args.config)
    out_dir = pathlib.Path(args.out_dir or cfg["dataset_dir"])
    if not out_dir.is_absolute():
        out_dir = ROOT / out_dir
    ds = cfg["dataset_version"]
    seed = int(cfg.get("seed", 20261005))
    source = args.source or cfg.get("source", "synthetic")

    records = candidate_pairs(ds, seed=seed) if source in ("synthetic", "both") else []
    if source in ("phaseA", "both"):
        pa = pathlib.Path(cfg["phase_a_records"] or (ROOT / "runs" / cfg["phase_a_run"]))
        try:
            records += from_phase_a(pa, ds)
        except SystemExit as exc:
            print(f"  phase-A source skipped: {exc}")

    rejected: collections.Counter = collections.Counter()
    kept: list[PairRecord] = []
    seen: set[str] = set()
    for r in records:
        bad = structural_verify(r)
        if bad:
            rejected[bad[0]] += 1
            continue
        dedup_key = (r.text_hash, r.context.get("as_of"), r.context.get("crosswalk_relation"))
        if dedup_key in seen:
            rejected["duplicate pair under the same context"] += 1
            continue
        seen.add(dedup_key)
        kept.append(r)

    split_by_topic(kept, cfg, seed)
    counts = {
        "by_split": dict(collections.Counter(r.split for r in kept)),
        "by_stratum": dict(sorted(collections.Counter(r.stratum for r in kept).items())),
        "by_label": dict(sorted(collections.Counter(r.label for r in kept).items())),
        "by_split_stratum": {f"{s}/{st}": sum(1 for r in kept if r.split == s and r.stratum == st)
                             for s in ("train", "dev", "test") for st in STRATA},
    }
    print(f"candidates {len(records)}  kept {len(kept)}  rejected {sum(rejected.values())}")
    for k, v in counts["by_split"].items():
        print(f"  {k:6s} {v}")
    if rejected:
        print("  rejections:", dict(rejected))

    if args.verify_only:
        print("verify-only: nothing written")
        return

    out_dir.mkdir(parents=True, exist_ok=True)
    files = {}
    for split in ("train", "dev", "test"):
        rows = [r for r in kept if r.split == split]
        path = out_dir / f"{split}.jsonl"
        path.write_text("".join(r.to_json() + "\n" for r in rows))
        files[split] = {"path": str(path.relative_to(ROOT)), "n": len(rows),
                        "sha256": sha256_file(path)}

    if args.export_for_human:
        sample = [r for r in kept if r.split == "test"][: args.export_for_human]
        path = out_dir / "to_verify.jsonl"
        path.write_text("".join(r.to_json() + "\n" for r in sample))
        files["to_verify"] = {"path": str(path.relative_to(ROOT)), "n": len(sample),
                              "sha256": sha256_file(path)}
        print(f"  exported {len(sample)} test pairs to {path.name} for human verification")

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "dataset_version": ds,
        "seed": seed,
        "source": source,
        "label_order": list(OPERATIONAL),
        "label_to_index": LABEL2IDX,
        "strata": STRATA,
        "counts": counts,
        "files": files,
        "rejected": dict(rejected),
        "content_hash": sha256_lines(kept),
        "human_verified_test": False,
        "notes": [
            "Splits are topic-disjoint; a topic appears in exactly one split.",
            "test must be replaced by the human-verified file before any reported metric.",
        ],
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(f"wrote {out_dir}/manifest.json  content_hash {manifest['content_hash'][:16]}")


if __name__ == "__main__":
    main()
