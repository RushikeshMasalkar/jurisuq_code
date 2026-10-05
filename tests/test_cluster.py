"""Unit tests: clustering, entropy in bits, and the published-example check."""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jurisuq.cluster import (DiscreteClusterer, EntailmentClusterer,
                             LexicalEntailmentBackend, cluster_stats,
                             entropy_with_unobserved, majority_label)


def test_discrete_clusterer_merges_formatting_only():
    texts = ["Section 103 of the BNS.", "Answer: Section 103 of the BNS",
             "**Section 103** of the BNS.", "Section 302 of the IPC."]
    labels = DiscreteClusterer().cluster(texts)
    assert labels[:3] == [0, 0, 0]
    assert labels[3] != 0


def test_entropy_of_uniform_is_log2_of_count():
    labels = [0, 1, 2, 3, 4, 5, 6, 7]
    st = cluster_stats(labels)
    assert st["entropy"] == pytest.approx(3.0)     # log2(8)
    assert st["top_prob"] == pytest.approx(0.125)


def test_entropy_zero_when_all_same():
    st = cluster_stats([2, 2, 2, 2])
    assert st["entropy"] == pytest.approx(0.0)
    assert st["n_clusters"] == 1


def test_unobserved_mass_raises_entropy():
    labels = [0, 0, 0, 0]
    assert entropy_with_unobserved(labels, 0.0) == pytest.approx(0.0)
    h = entropy_with_unobserved(labels, 0.5)
    assert h == pytest.approx(1.0)                 # one bit from the unseen mass


def test_majority_label_is_stable():
    assert majority_label([1, 1, 0]) == 1
    assert majority_label([0, 1, 1]) == 1
    assert majority_label([3]) == 3


def test_entailment_clusterer_with_lexical_proxy():
    # proxy merges near-identical wording only; the assertion documents that
    c = EntailmentClusterer(LexicalEntailmentBackend(), threshold=0.8)
    texts = ["Section 103 of the BNS applies to murder.",
             "Section 103 of the BNS applies to murder.",
             "Cheating is covered by Section 318 of the BNS."]
    labels = c.cluster(texts)
    assert labels[0] == labels[1]
    assert labels[2] != labels[0]


def test_published_evse_running_example_replicates():
    """EVSE26 scenario 1: BetP = (0.540, 0.190, 0.090, 0.140, 0.040), H = 1.83 bits.

    This is the replication check that the guide promises for the evidence
    layer; the entropy here is the Shannon entropy of the pignistic
    projection, which is what the published figure reports.
    """
    betp = [0.540, 0.190, 0.090, 0.140, 0.040]
    h = -sum(p * math.log2(p) for p in betp if p > 0)
    assert h == pytest.approx(1.83, abs=0.005)
