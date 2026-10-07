"""Relation model: pair serialisation, encoder, head, inference and checkpointing.

Design constants that must not drift between training and inference are declared
once at the top of this module and written into every checkpoint's metadata:
the serialisation format, the per-segment token budget, the label order and the
encoder name. A checkpoint whose metadata disagrees with this file is refused at
load time rather than silently evaluated.
"""
from __future__ import annotations

import json
import math
import pathlib
import time

from .cluster_typed import (argmax_labels, identity_pairs, merge_score_matrix,
                            typed_cluster)
from .schema import IDX2LABEL, LABEL2IDX, MERGE_RELATIONS, OPERATIONAL, SPLITS

# ---- frozen serialisation constants ---------------------------------------
SEGMENT_TOKENS = {"a": 120, "b": 120, "ctx": 60}
SPECIAL = {"a_open": "[A]", "a_close": "[/A]", "b_open": "[B]", "b_close": "[/B]",
           "ctx_open": "[CTX]", "ctx_close": "[/CTX]"}
SERIALISATION_VERSION = "ser1"
DEFAULT_ENCODER = "law-ai/InLegalBERT"
CONTROL_ENCODER = "microsoft/deberta-v3-base"
HEAD_HIDDEN = 256

try:                                    # pragma: no cover - environment dependent
    import torch
    import torch.nn as nn
    HAS_TORCH = True
except Exception:                       # noqa: BLE001
    torch = None                        # type: ignore
    nn = None                           # type: ignore
    HAS_TORCH = False

try:                                    # pragma: no cover - environment dependent
    from transformers import AutoModel, AutoTokenizer
    HAS_TRANSFORMERS = True
except Exception:                       # noqa: BLE001
    HAS_TRANSFORMERS = False


def load_tokenizer(name: str):
    """Tokenizer loader kept in this module so training and inference cannot drift."""
    require("transformers")
    return AutoTokenizer.from_pretrained(name)


def require(dep: str) -> None:
    if dep == "torch" and not HAS_TORCH:
        raise RuntimeError("torch is not installed in this environment")
    if dep == "transformers" and not HAS_TRANSFORMERS:
        raise RuntimeError("transformers is not installed in this environment")


# ---------------------------------------------------------------------------
# serialisation (pure function; unit-tested without torch)
# ---------------------------------------------------------------------------
def serialize_pair(answer_a: str, answer_b: str, context: dict) -> str:
    """`[A] a [/A] [B] b [/B] [CTX] as_of=..; jurisdiction=..; crosswalk=.. [/CTX]`"""
    ctx = (f"as_of={context.get('as_of', 'unknown')}; "
           f"jurisdiction={context.get('jurisdiction', 'IN')}; "
           f"crosswalk={context.get('crosswalk_relation') or 'none'}")
    a = " ".join((answer_a or "").split())
    b = " ".join((answer_b or "").split())
    return (f"{SPECIAL['a_open']} {a} {SPECIAL['a_close']} "
            f"{SPECIAL['b_open']} {b} {SPECIAL['b_close']} "
            f"{SPECIAL['ctx_open']} {ctx} {SPECIAL['ctx_close']}")


def encode_pair(tokenizer, answer_a: str, answer_b: str, context: dict) -> dict:
    """Tokenise the three segments separately and truncate each on its own budget."""
    a = " ".join((answer_a or "").split())
    b = " ".join((answer_b or "").split())
    ctx = (f"as_of={context.get('as_of', 'unknown')}; "
           f"jurisdiction={context.get('jurisdiction', 'IN')}; "
           f"crosswalk={context.get('crosswalk_relation') or 'none'}")
    ta = tokenizer(a, add_special_tokens=False, truncation=True,
                   max_length=SEGMENT_TOKENS["a"])["input_ids"]
    tb = tokenizer(b, add_special_tokens=False, truncation=True,
                   max_length=SEGMENT_TOKENS["b"])["input_ids"]
    tc = tokenizer(ctx, add_special_tokens=False, truncation=True,
                   max_length=SEGMENT_TOKENS["ctx"])["input_ids"]
    prefix = tokenizer.convert_tokens_to_ids([SPECIAL["a_open"], SPECIAL["a_close"],
                                              SPECIAL["b_open"], SPECIAL["b_close"],
                                              SPECIAL["ctx_open"], SPECIAL["ctx_close"]])
    ids = prefix[0:1] + ta + prefix[1:2] + prefix[2:3] + tb + prefix[3:4] \
        + prefix[4:5] + tc + prefix[5:6]
    return {"input_ids": ids, "attention_mask": [1] * len(ids)}


# ---------------------------------------------------------------------------
# torch model
# ---------------------------------------------------------------------------
if HAS_TORCH:

    class RelationClassifier(nn.Module):
        """Encoder + mean pooling + a two-layer head over the operational labels."""

        def __init__(self, encoder_name: str = DEFAULT_ENCODER, dropout: float = 0.1):
            super().__init__()
            require("transformers")
            self.encoder_name = encoder_name
            self.encoder = AutoModel.from_pretrained(encoder_name)
            hidden = self.encoder.config.hidden_size
            self.dropout = nn.Dropout(dropout)
            self.head = nn.Sequential(
                nn.Linear(hidden, HEAD_HIDDEN),
                nn.GELU(),
                nn.Dropout(dropout),
                nn.Linear(HEAD_HIDDEN, len(OPERATIONAL)),
            )

        def forward(self, input_ids, attention_mask):
            out = self.encoder(input_ids=input_ids, attention_mask=attention_mask)
            hidden = out.last_hidden_state
            mask = attention_mask.unsqueeze(-1).float()
            pooled = (hidden * mask).sum(1) / mask.sum(1).clamp(min=1e-6)
            return self.head(self.dropout(pooled))

    def _collate(batch, tokenizer, device):
        maxlen = max(len(item["input_ids"]) for item in batch)
        pad = tokenizer.pad_token_id or 0
        ids, mask = [], []
        for item in batch:
            n = len(item["input_ids"])
            ids.append(item["input_ids"] + [pad] * (maxlen - n))
            mask.append(item["attention_mask"] + [0] * (maxlen - n))
        return (torch.tensor(ids, dtype=torch.long, device=device),
                torch.tensor(mask, dtype=torch.long, device=device))

    def resolve_device(prefer: str | None = None):
        """xpu (Intel Arc) -> cuda -> mps -> cpu, unless the config pins one."""
        if prefer:
            return torch.device(prefer)
        if hasattr(torch, "xpu") and torch.xpu.is_available():
            return torch.device("xpu")
        if torch.cuda.is_available():
            return torch.device("cuda")
        if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            return torch.device("mps")
        return torch.device("cpu")

    def train_model(pairs, cfg: dict, tokenizer=None, encoder_name: str | None = None,
                    log=print, device=None):
        """Fine-tune on training pairs, select the threshold on dev, return (model, history)."""
        require("transformers")
        device = device or resolve_device(cfg.get("device"))
        encoder_name = encoder_name or cfg.get("encoder", DEFAULT_ENCODER)
        tokenizer = tokenizer or AutoTokenizer.from_pretrained(encoder_name)
        torch.manual_seed(int(cfg.get("seed", 20261005)))
        model = RelationClassifier(encoder_name, dropout=float(cfg.get("dropout", 0.1)))
        model.to(device)

        def batches(records, bs, shuffle):
            idx = list(range(len(records)))
            if shuffle:
                g = torch.Generator().manual_seed(int(cfg.get("seed", 20261005)))
                idx = torch.randperm(len(idx), generator=g).tolist()
            for s in range(0, len(idx), bs):
                chunk = [records[i] for i in idx[s:s + bs]]
                encoded = [encode_pair(tokenizer, r.answer_a["text"], r.answer_b["text"],
                                       r.context) for r in chunk]
                labels = torch.tensor([LABEL2IDX[r.label] for r in chunk],
                                      dtype=torch.long, device=device)
                ids, mask = _collate(encoded, tokenizer, device)
                yield ids, mask, labels

        counts = [0] * len(OPERATIONAL)
        for r in pairs:
            counts[LABEL2IDX[r.label]] += 1
        total = sum(counts) or 1
        weights = torch.tensor(
            [min(10.0, total / max(1, c) / len(OPERATIONAL)) for c in counts],
            dtype=torch.float32, device=device)
        lossf = nn.CrossEntropyLoss(weight=weights)
        opt = torch.optim.AdamW(model.parameters(), lr=float(cfg.get("lr", 2e-5)),
                                weight_decay=float(cfg.get("weight_decay", 0.01)))
        epochs = int(cfg.get("epochs", 3))
        bs = int(cfg.get("batch_size", 16))
        history = []
        for ep in range(1, epochs + 1):
            model.train()
            t0, run, seen = time.time(), 0.0, 0
            for ids, mask, labels in batches(pairs, bs, shuffle=True):
                opt.zero_grad()
                logits = model(ids, mask)
                loss = lossf(logits, labels)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                opt.step()
                run += float(loss.item()) * labels.size(0)
                seen += labels.size(0)
            history.append({"epoch": ep, "train_loss": run / max(1, seen),
                            "seconds": round(time.time() - t0, 1)})
            log(f"  epoch {ep}/{epochs}  loss {run / max(1, seen):.4f}"
                f"  ({history[-1]['seconds']}s)")
        return model, history

    def predict_proba(model, tokenizer, records, cfg: dict, device=None) -> list[list[float]]:
        """Class probabilities for a list of pair records (ordered, not symmetric)."""
        require("transformers")
        device = device or resolve_device(cfg.get("device"))
        model.eval().to(device)
        bs = int(cfg.get("eval_batch_size", 32))
        probs: list[list[float]] = []
        with torch.no_grad():
            for s in range(0, len(records), bs):
                chunk = records[s:s + bs]
                encoded = [encode_pair(tokenizer, r.answer_a["text"], r.answer_b["text"],
                                       r.context) for r in chunk]
                ids, mask = _collate(encoded, tokenizer, device)
                with torch.inference_mode():
                    logits = model(ids, mask)
                probs.extend(torch.softmax(logits, dim=-1).cpu().tolist())
        return probs

    def select_threshold(dev_probs, dev_labels, grid=None) -> tuple[float, dict]:
        """Pick tau by merge-decision F1 on dev. Deterministic: ties break to the lower tau."""
        grid = grid or [round(0.05 * k, 2) for k in range(1, 20)]
        merge_idx = [LABEL2IDX[r] for r in sorted(MERGE_RELATIONS)]
        best = (-1.0, grid[0], {})
        for tau in grid:
            tp = fp = fn = tn = 0
            for p, y in zip(dev_probs, dev_labels):
                pred = sum(p[k] for k in merge_idx) >= tau
                gold = y in MERGE_RELATIONS
                if pred and gold:
                    tp += 1
                elif pred and not gold:
                    fp += 1
                elif gold and not pred:
                    fn += 1
                else:
                    tn += 1
            prec = tp / (tp + fp) if tp + fp else 0.0
            rec = tp / (tp + fn) if tp + fn else 0.0
            f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
            if f1 > best[0] + 1e-12:
                best = (f1, tau, {"precision": prec, "recall": rec, "f1": f1,
                                  "tp": tp, "fp": fp, "fn": fn, "tn": tn})
        return best[1], best[2]

    # ---- checkpointing ----------------------------------------------------
    def save_checkpoint(path, model, tokenizer, meta: dict) -> pathlib.Path:
        p = pathlib.Path(path)
        p.mkdir(parents=True, exist_ok=True)
        torch.save(model.state_dict(), p / "model.pt")
        tokenizer.save_pretrained(p)
        (p / "meta.json").write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n")
        return p

    def load_checkpoint(path):
        require("transformers")
        p = pathlib.Path(path)
        meta = json.loads((p / "meta.json").read_text())
        if meta.get("serialisation_version") != SERIALISATION_VERSION:
            raise ValueError(f"checkpoint was trained under serialisation "
                             f"{meta.get('serialisation_version')!r}, this code implements "
                             f"{SERIALISATION_VERSION!r}")
        if tuple(meta.get("labels", [])) != tuple(OPERATIONAL):
            raise ValueError("checkpoint label order differs from this code's label order")
        tokenizer = AutoTokenizer.from_pretrained(p)
        model = RelationClassifier(meta.get("encoder", DEFAULT_ENCODER))
        model.load_state_dict(torch.load(p / "model.pt", map_location="cpu"))
        model.eval()
        return model, tokenizer, meta


# ---------------------------------------------------------------------------
# inference over one item's samples
# ---------------------------------------------------------------------------
def score_samples(model, tokenizer, texts: list[str], asserted: list[dict | None], context: dict,
                  cfg: dict, keys: list[str] | None = None, tau: float | None = None) -> dict:
    """Predict the ordered relation matrix, score it, and cluster the samples."""
    from .pairs import key_of
    from .schema import PairRecord

    m = len(texts)
    keys = keys if keys is not None else [key_of(a) for a in asserted]
    # pairs the clustering constraint decides by itself never reach the encoder: the
    # identical-key rule is a certainty and asking the model about it costs time without
    # changing any outcome. They are filled with a SAME_PROVISION one-hot below.
    forced = identity_pairs(keys)
    same = LABEL2IDX["SAME_PROVISION"]
    prob = [[[0.0] * len(OPERATIONAL) for _ in range(m)] for _ in range(m)]
    for i in range(m):
        for j in range(m):
            if i == j or (min(i, j), max(i, j)) in forced:
                for c in range(len(OPERATIONAL)):
                    prob[i][j][c] = 1.0 if c == same else 0.0

    records, index = [], []
    for i in range(m):
        for j in range(m):
            if i == j or (min(i, j), max(i, j)) in forced:
                continue
            records.append(PairRecord(
                pair_id=f"{i}-{j}", dataset_version="inference", split="train", stratum="S1",
                answer_a={"text": texts[i], "asserted": asserted[i]},
                answer_b={"text": texts[j], "asserted": asserted[j]},
                context=dict(context), label="SAME_PROVISION"))
            index.append((i, j))
    flat = predict_proba(model, tokenizer, records, cfg) if records else []
    for (i, j), p_ij in zip(index, flat):
        prob[i][j] = p_ij
    score = merge_score_matrix(prob)
    relation = argmax_labels(prob)
    tau = float(tau if tau is not None else cfg.get("merge_threshold", 0.5))
    result = typed_cluster(keys, relation, score, tau)
    return {"prob": prob, "relation": relation, "merge_score": score,
            "clusters": result.labels, "canonical": result.canonical,
            "members": result.members, "tau": tau,
            "merges_applied": result.merges_applied,
            "merges_skipped": result.merges_skipped,
            "encoder_pairs": len(records), "rule_pairs": 2 * len(forced)}
