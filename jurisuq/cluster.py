"""Legal-semantics clustering used by the sample-only baselines.

Two channels:

``DiscreteClusterer``
    Exact equivalence after conservative normalisation (Kuhn et al. 2023,
    "discrete semantic entropy", Eq. 2-3 of [SE24]).

``EntailmentClusterer``
    Greedy bidirectional-entailment clustering against cluster
    representatives (Kuhn et al. 2023 / Farquhar et al. 2024 [SE24]).

Phase A deliberately ships *generic* entailment only: E1 is a diagnostic
about what sample-only agreement can and cannot see, so the relation model
of Phase B must not be smuggled in. The entailment *backend* is pluggable:
the real NLI model on your machine, or a lexical proxy when transformers is
not installed (the run records which backend produced the numbers).
"""
from __future__ import annotations

import math
import re
from typing import Sequence

from .normalize import normalize


# ----------------------------------------------------------------------
# cluster statistics
# ----------------------------------------------------------------------
def cluster_stats(labels: Sequence[int]) -> dict:
    """Probabilities over clusters, entropy in bits, top probability."""
    m = len(labels)
    if m == 0:
        return {"probs": [], "entropy": float("nan"), "top_prob": float("nan"),
                "n_clusters": 0, "counts": []}
    counts: dict[int, int] = {}
    for lab in labels:
        counts[lab] = counts.get(lab, 0) + 1
    ordered = sorted(counts.values(), reverse=True)
    probs = [c / m for c in ordered]
    entropy = -sum(p * math.log2(p) for p in probs if p > 0)
    return {"probs": probs, "entropy": entropy, "top_prob": probs[0],
            "n_clusters": len(probs), "counts": ordered}


def entropy_with_unobserved(labels: Sequence[int], p_unobserved: float) -> float:
    """Semantic entropy including an explicit mass on unseen answers.

    ``p_unobserved`` is the total probability that a further sample would fall
    outside every observed cluster; it is estimated from length-normalised
    sequence probabilities in [SE24]. Phase A accepts it as an input (usually
    0.0) and Phase B estimates it; the parameter exists so the estimator is
    written once.
    """
    st = cluster_stats(labels)
    if not st["probs"]:
        return float("nan")
    m = len(labels)
    p_u = max(0.0, min(1.0, p_unobserved))
    probs = [(1 - p_u) * p for p in st["probs"]]
    if p_u > 0:
        probs.append(p_u)
        probs.sort(reverse=True)
    return -sum(p * math.log2(p) for p in probs if p > 0)


def majority_label(labels: Sequence[int]) -> int:
    counts: dict[int, int] = {}
    first: dict[int, int] = {}
    for i, lab in enumerate(labels):
        counts[lab] = counts.get(lab, 0) + 1
        first.setdefault(lab, i)
    return max(counts, key=lambda k: (counts[k], -first[k]))


# ----------------------------------------------------------------------
# clusterers
# ----------------------------------------------------------------------
class DiscreteClusterer:
    name = "discrete"

    def cluster(self, texts: Sequence[str]) -> list[int]:
        keys: dict[str, int] = {}
        labels = []
        for t in texts:
            k = normalize(t)
            if k not in keys:
                keys[k] = len(keys)
            labels.append(keys[k])
        return labels


class EntailmentClusterer:
    """Greedy bidirectional-entailment clustering.

    A candidate joins a cluster when both directions clear ``threshold``
    against that cluster's representative (its first member). Greedy rather
    than exact because exact clustering over M samples costs O(M^2) NLI calls
    and the greedy variant is the published procedure.
    """

    name = "entailment"

    def __init__(self, backend, threshold: float = 0.8):
        self.backend = backend
        self.threshold = threshold

    @property
    def backend_name(self) -> str:
        return getattr(self.backend, "name", "unknown")

    def cluster(self, texts: Sequence[str]) -> list[int]:
        labels = [-1] * len(texts)
        if not texts:
            return labels
        reps: list[int] = []                 # cluster -> representative index
        labels[0] = 0
        reps.append(0)
        for i in range(1, len(texts)):
            pairs = [(texts[r], texts[i]) for r in reps]
            scores = self.backend.entail_batch(pairs)
            assigned = False
            for ci, (p_forward, p_backward) in enumerate(scores):
                if p_forward >= self.threshold and p_backward >= self.threshold:
                    labels[i] = ci
                    assigned = True
                    break
            if not assigned:
                labels[i] = len(reps)
                reps.append(i)
        return labels


# ----------------------------------------------------------------------
# entailment backends
# ----------------------------------------------------------------------
class LexicalEntailmentBackend:
    """Token-set overlap proxy. NOT the published method.

    Used only when ``transformers`` is unavailable, so that the harness can be
    exercised end to end before the NLI checkpoint is downloaded. Every run
    records ``backend = "lexical-proxy"`` so these numbers can never be
    reported as standard semantic entropy.
    """

    name = "lexical-proxy"
    _TOK = re.compile(r"[a-z0-9]+")

    def __init__(self):
        self._cache: dict[tuple[str, str], float] = {}

    def _sim(self, a: str, b: str) -> float:
        key = (a, b) if a <= b else (b, a)
        if key in self._cache:
            return self._cache[key]
        ta = set(self._TOK.findall(normalize(a)))
        tb = set(self._TOK.findall(normalize(b)))
        if not ta or not tb:
            sim = 0.0
        else:
            inter = len(ta & tb)
            sim = inter / max(len(ta), len(tb))
        self._cache[key] = sim
        return sim

    def entail_batch(self, pairs: Sequence[tuple[str, str]]) -> list[tuple[float, float]]:
        return [(self._sim(a, b), self._sim(b, a)) for a, b in pairs]


class NLIEntailmentBackend:
    """MNLI-class entailment backend via Hugging Face transformers.

    Premise = one sampled answer, hypothesis = another; the pair is merged when
    both directions are entailed above the threshold. Model download happens on
    first construction (about 700 MB for the default checkpoint).
    """

    name = "nli"

    def __init__(self, model_name: str, batch_size: int = 16, device: int = -1,
                 max_length: int = 320):
        try:
            import torch
            from transformers import AutoModelForSequenceClassification, AutoTokenizer
        except ImportError as exc:  # pragma: no cover - depends on the machine
            raise ImportError(
                "NLIEntailmentBackend needs `transformers` and `torch`. "
                "Install them (see requirements-nli.txt) or set "
                "allow_lexical_fallback=true."
            ) from exc
        self._torch = torch
        self.name = f"nli:{model_name}"
        self.batch_size = batch_size
        self.max_length = max_length
        self.tok = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModelForSequenceClassification.from_pretrained(model_name)
        self.model.eval()
        if device >= 0 and torch.cuda.is_available():  # pragma: no cover
            self.model.to("cuda")
            self._device = "cuda"
        else:
            self._device = "cpu"
        self._entail_idx = self._find_entail_index()

    def _find_entail_index(self) -> int:
        id2label = {int(k): str(v).lower() for k, v in self.model.config.id2label.items()}
        for idx, label in id2label.items():
            if "entail" in label:
                return idx
        # 3-class NLI convention when the config only says LABEL_0/1/2
        return 2

    def entail_batch(self, pairs: Sequence[tuple[str, str]]) -> list[tuple[float, float]]:
        if not pairs:
            return []
        torch = self._torch
        flat: list[tuple[str, str]] = []
        for a, b in pairs:
            flat.append((a, b))
            flat.append((b, a))
        out: list[float] = []
        with torch.no_grad():
            for start in range(0, len(flat), self.batch_size):
                chunk = flat[start:start + self.batch_size]
                enc = self.tok([c[0] for c in chunk], [c[1] for c in chunk],
                               truncation=True, max_length=self.max_length,
                               padding=True, return_tensors="pt")
                logits = self.model(**enc).logits
                probs = torch.softmax(logits, dim=-1)[:, self._entail_idx]
                out.extend(float(p) for p in probs)
        return [(out[2 * i], out[2 * i + 1]) for i in range(len(pairs))]


def make_clusterer(cfg) -> tuple[object | None, object | None, str]:
    """Build (discrete_clusterer, entailment_clusterer|None, backend_name)."""
    discrete = DiscreteClusterer()
    if cfg.clusterer == "discrete":
        return discrete, None, "n/a"
    try:
        backend = NLIEntailmentBackend(cfg.nli_model)
    except ImportError:
        if not cfg.allow_lexical_fallback:
            raise
        backend = LexicalEntailmentBackend()
    return discrete, EntailmentClusterer(backend, cfg.entail_threshold), backend.name
