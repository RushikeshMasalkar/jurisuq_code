#!/usr/bin/env python3
"""28 - adapt the Phase C encoder with continued masked-language modelling.

The corpus is deliberately unlabeled: statute-store text excerpts plus every
stored answer text in the frozen Phase A slice. The public InLegalBERT encoder
is continued with MLM rather than replaced or relation-fine-tuned, preserving
its general legal-language representation while adapting vocabulary and
phrasing to this project's statute/answer corpus.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import time
from pathlib import Path

import torch
from torch.utils.data import Dataset
from transformers import (AutoModelForMaskedLM, AutoTokenizer,
                          DataCollatorForLanguageModeling, Trainer,
                          TrainingArguments)

ROOT = Path(__file__).resolve().parents[1]


def source_hash() -> str:
    h = hashlib.sha256()
    excluded = {".git", ".venv", "models", "runs", "__pycache__", ".pytest_cache"}
    for path in sorted(p for p in ROOT.rglob("*") if p.is_file()
                       and not any(part in excluded for part in p.relative_to(ROOT).parts)):
        rel = path.relative_to(ROOT).as_posix().encode("utf-8")
        data = path.read_bytes()
        h.update(len(rel).to_bytes(8, "big"))
        h.update(rel)
        h.update(len(data).to_bytes(8, "big"))
        h.update(data)
    return h.hexdigest()


class TokenCorpus(Dataset):
    def __init__(self, texts: list[str], tokenizer, max_length: int) -> None:
        self.rows = tokenizer(texts, truncation=True, max_length=max_length,
                              padding=False, return_attention_mask=True)

    def __len__(self) -> int:
        return len(self.rows["input_ids"])

    def __getitem__(self, index: int) -> dict:
        return {key: values[index] for key, values in self.rows.items()}


def load_texts() -> list[str]:
    statutes = ROOT / "data" / "statutes" / "statutes_v1.jsonl"
    answers = ROOT / "runs" / "phaseA-laptop-v2-rejudged" / "items.jsonl"
    texts = []
    for line in statutes.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        text = " ".join(str(row.get(key, "")) for key in
                        ("act", "section", "title", "text_excerpt")).strip()
        if text:
            texts.append(text)
    for line in answers.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        texts.extend(str(text).strip() for text in row.get("sample_texts", [])
                     if str(text).strip())
    if not texts:
        raise SystemExit("ERROR: adaptation corpus is empty")
    return texts


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--encoder", default="law-ai/InLegalBERT")
    ap.add_argument("--out-dir", default="models/phaseC-inlegalbert-adapted")
    ap.add_argument("--epochs", type=int, default=1)
    ap.add_argument("--batch-size", type=int, default=8)
    ap.add_argument("--max-length", type=int, default=320)
    ap.add_argument("--learning-rate", type=float, default=2e-5)
    ap.add_argument("--seed", type=int, default=20261023)
    args = ap.parse_args()
    if args.epochs < 1 or args.batch_size < 1 or args.max_length < 8:
        ap.error("epochs, batch-size, and max-length must be positive")

    before = source_hash()
    random.seed(args.seed)
    torch.manual_seed(args.seed)
    texts = load_texts()
    tokenizer = AutoTokenizer.from_pretrained(args.encoder)
    dataset = TokenCorpus(texts, tokenizer, args.max_length)
    token_count = sum(sum(row) for row in dataset.rows["attention_mask"])
    model = AutoModelForMaskedLM.from_pretrained(args.encoder)
    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = ROOT / out_dir
    if out_dir.exists() and any(out_dir.iterdir()):
        raise SystemExit(f"ERROR: output directory is not empty: {out_dir}")
    out_dir.mkdir(parents=True, exist_ok=True)
    collator = DataCollatorForLanguageModeling(tokenizer=tokenizer,
                                               mlm=True, mlm_probability=0.15)
    training = TrainingArguments(
        output_dir=str(out_dir / "trainer"),
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        learning_rate=args.learning_rate,
        weight_decay=0.01,
        logging_strategy="epoch",
        save_strategy="no",
        report_to=[],
        seed=args.seed,
        data_seed=args.seed,
        remove_unused_columns=False,
    )
    trainer = Trainer(model=model, args=training, train_dataset=dataset,
                      data_collator=collator)
    started = time.perf_counter()
    trainer.train()
    elapsed = time.perf_counter() - started
    metrics = trainer.evaluate(eval_dataset=dataset)
    loss = float(metrics["eval_loss"])
    if not math.isfinite(loss):
        raise SystemExit(f"ERROR: final MLM loss is not finite: {loss}")
    tokenizer.save_pretrained(out_dir)
    model.save_pretrained(out_dir)
    after = source_hash()
    if before != after:
        raise SystemExit("ERROR: source tree changed during adaptation")
    metadata = {
        "phase": "C",
        "method": "continued masked-language-model pretraining",
        "reason": "adapt the public legal encoder to the statute and answer corpus without relation retraining",
        "encoder": args.encoder,
        "corpus": {
            "statute_file": "data/statutes/statutes_v1.jsonl",
            "answer_file": "runs/phaseA-laptop-v2-rejudged/items.jsonl",
            "document_count": len(texts),
            "token_count_after_truncation": token_count,
        },
        "epochs": args.epochs,
        "batch_size": args.batch_size,
        "max_length": args.max_length,
        "learning_rate": args.learning_rate,
        "seed": args.seed,
        "wall_clock_seconds": round(elapsed, 3),
        "final_masked_lm_loss": loss,
        "source_tree_sha256_before": before,
        "source_tree_sha256_after": after,
        "source_tree_unchanged": before == after,
    }
    (out_dir / "adaptation_meta.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    checkpoint_hash = hashlib.sha256()
    for path in sorted(p for p in out_dir.rglob("*")
                       if p.is_file() and p.name != "adaptation_meta.json"):
        checkpoint_hash.update(path.relative_to(out_dir).as_posix().encode())
        checkpoint_hash.update(path.read_bytes())
    metadata["adapted_checkpoint_sha256"] = checkpoint_hash.hexdigest()
    (out_dir / "adaptation_meta.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metadata, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
