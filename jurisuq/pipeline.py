"""Record construction: everything that happens after sampling.

Kept in the package (not in a script) because two entry points need it:

* ``scripts/02_run_inference.py`` - sample, then build a record per item;
* ``scripts/05_rejudge.py`` - re-run the *judge* and the *scoring* on answers
  that are already stored, which is what you do when the judge turns out to be
  too strict. It costs seconds instead of a second overnight run, and it is the
  reason raw answers are kept in the record.
"""
from __future__ import annotations

import statistics
import time

from .normalize import REPEALED_CODES


def cluster_labels_for(texts, discrete, entail):
    """Cluster labels for each channel; returns (labels, source, pairs)."""
    disc = discrete.cluster(texts)
    if entail is None:
        return disc, "discrete", None, None, None
    n = len(texts)
    pairs = [(texts[i], texts[j]) for i in range(n) for j in range(i + 1, n)]
    scores = entail.backend.entail_batch(pairs) if pairs else []
    ent = entail.cluster(texts)
    return disc, "entailment", pairs, ent, scores


def provision_key(asserted: dict | None) -> str:
    """The comparable identity of an asserted provision.

    Two answers that say "Section 302 of the Indian Penal Code" and "IPC, s. 302
    (murder)" are the same answer about the *law* even though they are different
    strings. Agreement must be measured at this level, because that is the level
    at which a common-mode legal error is common: the model repeats one wrong
    provision, not one sentence.
    """
    if not asserted:
        return "NONE"
    act = asserted.get("act") or "UNKNOWN"
    prov = asserted.get("provision")
    if act == "FOREIGN":
        return f"FOREIGN:{prov}"
    if prov is None:
        return f"{act} (no section)"
    return f"{act} {prov}"


def provision_stats(keys: list[str]) -> dict:
    """Agreement statistics over asserted provisions, in bits."""
    import math
    m = len(keys)
    if m == 0:
        return {"n_keys": 0, "probs": [], "entropy": float("nan"), "top_share": float("nan"),
                "all_same": 0, "majority": None}
    counts: dict[str, int] = {}
    for k in keys:
        counts[k] = counts.get(k, 0) + 1
    ordered = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    probs = [c / m for _, c in ordered]
    entropy = max(0.0, -sum(p * math.log2(p) for p in probs if p > 0))
    return {"n_keys": len(ordered), "probs": probs, "entropy": entropy,
            "top_share": probs[0], "all_same": int(len(ordered) == 1),
            "majority": ordered[0][0],
            "counts": {k: c for k, c in ordered}}


def build_record(item: dict, texts: list[str], cfg, judge, clusterers,
                 n_tokens: list[int] | None = None,
                 logprobs: list[float | None] | None = None) -> dict:
    """Score one item's samples into a record. Pure with respect to sampling."""
    from .cluster import cluster_stats

    discrete, entail = clusterers
    t0 = time.time()

    verdicts = [judge.score(item, t) for t in texts]
    correct = [1 if v.correct else 0 for v in verdicts]
    unresolved = [v.correct is None for v in verdicts]

    disc_labels, majority_source, pairs, ent_labels, ent_scores = \
        cluster_labels_for(texts, discrete, entail)
    disc = cluster_stats(disc_labels)

    methods: dict = {
        "disc_se": disc["entropy"],
        "agreement": 1.0 - disc["top_prob"],
    }
    maj_labels = disc_labels

    if ent_labels is not None:
        ent = cluster_stats(ent_labels)
        methods["se"] = ent["entropy"]
        n = len(texts)
        max_ent = [0.0] * n
        if ent_scores:
            k = 0
            for i in range(n):
                for j in range(i + 1, n):
                    f, b = ent_scores[k]
                    k += 1
                    max_ent[i] = max(max_ent[i], f)
                    max_ent[j] = max(max_ent[j], b)
        methods["selfcheck"] = (statistics.fmean(1.0 - m for m in max_ent) if n
                                else float("nan"))
        maj_labels = ent_labels
        majority_source = "entailment"

    lps = [lp for lp in (logprobs or []) if lp is not None]
    methods["p_true"] = (1.0 - pow(2.718281828459045, statistics.fmean(lps))) if lps else None

    # the returned answer = the modal cluster; the item is scored by the
    # majority outcome *among its members*, and marked unresolved when the
    # majority of the members could not be resolved
    maj = max(range(len(maj_labels)), key=lambda i: (maj_labels.count(maj_labels[i]), -i))
    members = [j for j, lab in enumerate(maj_labels) if lab == maj_labels[maj]]
    maj_correct_frac = statistics.fmean(correct[j] for j in members)
    maj_resolved_frac = statistics.fmean(0.0 if unresolved[j] else 1.0 for j in members)
    maj_verdict_labels = [verdicts[j].label for j in members]

    # ---- provision-level view: what did the samples actually say about the law?
    asserted_keys = [provision_key(v.asserted) for v in verdicts]
    prov = provision_stats(asserted_keys)
    asserted_acts = [((v.asserted or {}).get("act") if v.asserted else None) for v in verdicts]
    repealed_share = (statistics.fmean(1.0 if a in REPEALED_CODES else 0.0 for a in asserted_acts)
                      if asserted_acts else float("nan"))
    methods["prov_se"] = prov["entropy"]
    methods["prov_agreement"] = 1.0 - prov["top_share"]

    rec = {
        "item_id": item["item_id"],
        "slice": item["slice"],
        "topic": item.get("topic"),
        "template": item.get("template"),
        "question": item.get("question"),
        "gold": item.get("gold"),
        "trap": item.get("trap"),
        "distractor": item.get("distractor"),
        "n_samples": len(texts),
        "methods": methods,
        "majority_correct": int(maj_correct_frac >= 0.5),
        "majority_resolved": int(maj_resolved_frac >= 0.5),
        "majority_frac_correct": maj_correct_frac,
        "majority_cluster_size": len(members),
        "majority_source": majority_source,
        "majority_verdict": maj_verdict_labels[0] if maj_verdict_labels else "n/a",
        "frac_correct": statistics.fmean(correct) if correct else float("nan"),
        "frac_unresolved": statistics.fmean(unresolved) if unresolved else float("nan"),
        "all_same": int(disc["n_clusters"] == 1),
        "prov_all_same": prov["all_same"],
        "prov_n_unique": prov["n_keys"],
        "prov_top_share": prov["top_share"],
        "prov_majority": prov["majority"],
        "prov_counts": prov.get("counts", {}),
        "asserted_keys": asserted_keys,
        "asserted_acts": asserted_acts,
        "repealed_code_share": repealed_share,
        "n_unique": disc["n_clusters"],
        "top_prob": disc["top_prob"],
        "sample_texts": texts,
        "sample_correct": correct,
        "sample_unresolved": [int(u) for u in unresolved],
        "sample_verdict_labels": [v.label for v in verdicts],
        "sample_verdict_reasons": [v.reason for v in verdicts],
        "mean_len_tokens": statistics.fmean(n_tokens) if n_tokens else None,
        "logprob_source": "server" if lps else "none",
        "scoring_s": time.time() - t0,
    }
    return rec


def item_from_record(rec: dict) -> dict:
    """Rebuild the fields the judge needs from a stored record.

    This is what makes offline re-judging possible: the record carries the
    question, the gold provision, the trap and the distractor, which is all any
    judge consumes.
    """
    return {
        "item_id": rec["item_id"],
        "slice": rec["slice"],
        "topic": rec.get("topic"),
        "template": rec.get("template"),
        "question": rec.get("question", ""),
        "gold": rec.get("gold") or {},
        "trap": rec.get("trap"),
        "distractor": rec.get("distractor"),
    }
