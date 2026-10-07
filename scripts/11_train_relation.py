"""11_train_relation.py -- fine-tune the Phase B relation model and select tau.

    python scripts/11_train_relation.py --config configs/phase_b_relations.json \
        --run-id phaseB-relations-01
    python scripts/11_train_relation.py --run-id phaseB-relations-01 --epochs 1 --limit 200

Writes, and never overwrites, a run directory; the checkpoint carries the encoder
name, the label order, the serialisation version, the dataset hashes and the
selected threshold, so an evaluation can prove which model and threshold it used.
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
from jurisuq.relations.schema import OPERATIONAL, PairRecord  # noqa: E402
from jurisuq.relations.stats import exact_key_baseline as _baseline  # noqa: E402
from jurisuq.relations.stats import macro_f1 as _macro_f1  # noqa: E402
from jurisuq.relations.stats import per_class as _per_class  # noqa: E402


def load_split(path: pathlib.Path, limit: int = 0) -> list[PairRecord]:
    rows = [PairRecord.from_json(l) for l in path.read_text().splitlines()]
    return rows[:limit] if limit else rows


def file_sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(ROOT / "configs" / "phase_b_relations.json"))
    ap.add_argument("--run-id", default="phaseB-relations-01")
    ap.add_argument("--epochs", type=int, default=None)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--encoder", default=None)
    ap.add_argument("--threshold-only", action="store_true",
                    help="re-select tau on the existing checkpoint without training")
    args = ap.parse_args()

    cfg = json.loads(pathlib.Path(args.config).read_text())
    if args.epochs:
        cfg["epochs"] = args.epochs
    if args.encoder:
        cfg["encoder"] = args.encoder
    ds_dir = pathlib.Path(cfg["dataset_dir"])
    manifest = json.loads((ds_dir / "manifest.json").read_text())
    train = load_split(ds_dir / "train.jsonl", args.limit)
    dev = load_split(ds_dir / "dev.jsonl", args.limit)
    print(f"dataset {manifest['dataset_version']}  train {len(train)}  dev {len(dev)}  "
          f"encoder {cfg['encoder']}")

    if not M.HAS_TORCH or not M.HAS_TRANSFORMERS:
        raise SystemExit("torch/transformers are required to train; install the relation "
                         "extras first (see requirements-relations.txt)")

    run_dir = ROOT / cfg["run_dir"] / args.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    model, history = M.train_model(train, cfg, encoder_name=cfg["encoder"])
    tokenizer = M.load_tokenizer(cfg["encoder"])

    dev_probs = M.predict_proba(model, tokenizer, dev, cfg)
    tau, tau_stats = M.select_threshold(dev_probs, [r.label for r in dev], cfg.get("tau_grid"))
    merge_idx = [M.LABEL2IDX[r] for r in sorted(M.MERGE_RELATIONS)]
    preds = [M.IDX2LABEL[max(range(len(p)), key=lambda k: p[k])] for p in dev_probs]
    merge_pred = ["SAME_PROVISION" if sum(p[k] for k in merge_idx) >= tau else "DIFFERENT_PROVISION"
                  for p in dev_probs]
    merge_gold = [r.label if r.label in M.MERGE_RELATIONS else "DIFFERENT_PROVISION" for r in dev]
    mf1, per_class = _per_class([r.label for r in dev], preds, OPERATIONAL)
    merge_f1, merge_per = _per_class(merge_gold, merge_pred,
                                      ("SAME_PROVISION", "DIFFERENT_PROVISION"))
    base = _baseline(dev, M.MERGE_RELATIONS)

    meta = {
        "encoder": cfg["encoder"],
        "labels": list(OPERATIONAL),
        "serialisation_version": M.SERIALISATION_VERSION,
        "segment_tokens": M.SEGMENT_TOKENS,
        "merge_threshold": tau,
        "threshold_stats": tau_stats,
        "dataset_version": manifest["dataset_version"],
        "dataset_content_hash": manifest["content_hash"],
        "dataset_files": {k: v["sha256"] for k, v in manifest["files"].items()},
        "seed": cfg.get("seed"),
        "trained_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "run_id": args.run_id,
        "dev": {"n": len(dev), "macro_f1": round(mf1, 4), "merge_f1": round(merge_f1, 4),
                "exact_key_baseline_macro_f1": round(base, 4), "per_class": per_class},
    }
    ckpt = M.save_checkpoint(ROOT / cfg["checkpoint_dir"] /
                             f"{manifest['dataset_version']}-{cfg['encoder'].split('/')[-1]}-{args.run_id}",
                             model, tokenizer, meta)
    (run_dir / "train_log.jsonl").write_text(
        "".join(json.dumps(h) + "\n" for h in history))
    (run_dir / "dev_report.json").write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n")

    print(f"  tau = {tau:.2f}  merge F1 {merge_f1:.3f}  (precision {tau_stats['precision']:.3f}, "
          f"recall {tau_stats['recall']:.3f})")
    print(f"  dev macro-F1 {mf1:.3f}  exact-key baseline {base:.3f}")
    print(f"  checkpoint {ckpt.relative_to(ROOT)}  ({time.time() - t0:.0f}s)")
    if mf1 <= base:
        print("  WARNING: the learned model does not beat exact-key identity on dev yet")


if __name__ == "__main__":
    main()
