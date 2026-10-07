"""Phase B unit tests: schema, pair construction, typed clustering, statistics.

Every test here runs without torch. The model file is import-guarded, so the
serialisation format - which must not drift between training and inference - is
tested directly.
"""
from __future__ import annotations

import itertools

import pytest

from jurisuq.relations import model as M
from jurisuq.relations.cluster_typed import (argmax_labels, canonical_provision,
                                             identity_pairs, merge_score_matrix,
                                             typed_cluster)
from jurisuq.relations.pairs import (asserted_from_text, candidate_pairs, form,
                                     offences, structural_verify)
from jurisuq.relations.schema import (BLOCKING_RELATIONS, LABEL2IDX, MERGE_RELATIONS,
                                      OPERATIONAL, PairError, PairRecord, make_pair,
                                      pair_id, text_hash)
from jurisuq.relations.stats import (contradiction_mass, exact_key_baseline,
                                     entropy_bits, merge_effect, per_class, typed_stats)

CTX = {"as_of": "2026-10-01", "jurisdiction": "IN", "crosswalk_relation": None}
CTX_LINK = {"as_of": "2026-10-01", "jurisdiction": "IN", "crosswalk_relation": "successor_of"}


def pair(text_a="Murder is punishable under section 302 IPC.", asserted_a=None,
         text_b="The applicable provision is s. 302 IPC.", asserted_b=None,
         label="SAME_PROVISION", ctx=None, stratum="S1", condition=None):
    return make_pair(text_a, asserted_a or {"act": "IPC", "provision": "302"},
                     text_b, asserted_b or {"act": "IPC", "provision": "302"},
                     ctx or CTX, label, "test_ds", "train", stratum, condition_tag=condition)


# ---------------------------------------------------------------- schema ----
def test_label_sets_are_disjoint_and_complete():
    assert set(OPERATIONAL) & set(M.MERGE_RELATIONS) == set(M.MERGE_RELATIONS)
    assert not (set(M.MERGE_RELATIONS) & BLOCKING_RELATIONS)
    assert len(set(M.OPERATIONAL)) == 5 and len(LABEL2IDX) == 5


def test_pair_id_is_order_independent():
    a = pair_id("one", "two", "ctx")
    assert a == pair_id("two", "one", "ctx")
    assert a != pair_id("one", "two", "other-ctx")


def test_text_hash_ignores_whitespace_only():
    assert text_hash("a  b\n c") == text_hash("a b c")


def test_condition_tag_required_only_for_conditional_equivalence():
    with pytest.raises(PairError):
        pair(label="CONDITIONALLY_EQUIVALENT")
    with pytest.raises(PairError):
        pair(label="SAME_PROVISION", condition="gravity")
    ok = pair(label="CONDITIONALLY_EQUIVALENT", condition="gravity:simple")
    assert ok.condition_tag == "gravity:simple"


def test_reserved_labels_are_refused():
    with pytest.raises(PairError):
        pair(label="TEMPORAL_MISMATCH")


def test_ambiguous_requires_an_unresolved_side():
    with pytest.raises(PairError):
        pair(label="AMBIGUOUS")
    ok = pair(text_b="This is governed by the Indian Penal Code.",
              asserted_b={"act": "IPC", "provision": None}, label="AMBIGUOUS", stratum="S7")
    assert ok.key_b() == "IPC (no section)"


# ------------------------------------------------------------ extraction ----
def test_asserted_from_text_reads_both_section_and_act_first_forms():
    assert asserted_from_text("Section 302 IPC applies.") == {"act": "IPC", "provision": "302"}
    a = asserted_from_text("Under the Bharatiya Nyaya Sanhita, s. 103 applies.")
    assert a and a["act"] == "BNS" and a["provision"] == "103"
    assert asserted_from_text("I cannot answer this question.") is None


def test_generated_pairs_round_trip_and_verify():
    recs = candidate_pairs("relations_v1")
    assert len(recs) > 200
    assert all(not structural_verify(r) for r in recs)
    assert len({r.pair_id for r in recs}) == len(recs)


def test_every_stratum_produces_pairs():
    strata = {r.stratum for r in candidate_pairs("relations_v1")}
    assert strata == {"S1", "S2", "S3", "S4", "S5", "S6", "S7"}


def test_verifier_catches_a_mislabelled_pair():
    good = pair(label="SAME_PROVISION")
    assert structural_verify(good) == []
    bad = pair(text_b="Section 304 IPC applies.",
               asserted_b={"act": "IPC", "provision": "304"}, label="SAME_PROVISION")
    assert structural_verify(bad)


# -------------------------------------------------------------- clustering --
def _matrix(m, value):
    return [[value for _ in range(m)] for _ in range(m)]


def _rel_from(keys, same="SAME_PROVISION", diff="DIFFERENT_PROVISION"):
    m = len(keys)
    out = _matrix(m, diff)
    for i in range(m):
        for j in range(m):
            if i == j or (keys[i] == keys[j] and keys[i] != "NONE"):
                out[i][j] = same
    return out


def test_identical_keys_merge_even_without_model_support():
    keys = ["IPC 302"] * 10
    rel = _matrix(10, "AMBIGUOUS")
    score = _matrix(10, 0.0)
    res = typed_cluster(keys, rel, score, tau=0.9)
    assert res.n_clusters == 1 and res.forced_unions == 9
    assert res.canonical == ["IPC 302"]


def test_learned_merge_requires_threshold_and_permitted_relation():
    keys = ["IPC 302", "BNS 103"]
    rel = [["SAME_PROVISION", "LEGALLY_EQUIVALENT"], ["LEGALLY_EQUIVALENT", "SAME_PROVISION"]]
    below = typed_cluster(keys, rel, [[1.0, 0.4], [0.4, 1.0]], tau=0.5)
    above = typed_cluster(keys, rel, [[1.0, 0.8], [0.8, 1.0]], tau=0.5)
    assert below.n_clusters == 2
    assert above.n_clusters == 1 and above.merges_applied == 1
    assert above.canonical[0] in ("IPC 302", "BNS 103")


def test_blocking_relation_prevents_a_transitive_merge():
    keys = ["IPC 302", "IPC 304", "IPC 302"]
    rel = [["SAME_PROVISION", "LEGALLY_EQUIVALENT", "SAME_PROVISION"],
           ["LEGALLY_EQUIVALENT", "SAME_PROVISION", "DIFFERENT_PROVISION"],
           ["SAME_PROVISION", "DIFFERENT_PROVISION", "SAME_PROVISION"]]
    score = [[1.0, 0.95, 1.0], [0.95, 1.0, 0.1], [1.0, 0.1, 1.0]]
    res = typed_cluster(keys, rel, score, tau=0.5)
    assert res.n_clusters == 2, "0 and 2 share a key, 1 is contradicted by 2"
    assert res.merges_skipped == 1


def test_clustering_is_order_independent():
    keys = ["IPC 302", "IPC 304", "BNS 103", "IPC 302"]
    rel = _rel_from(keys)
    rel[0][2] = rel[2][0] = "LEGALLY_EQUIVALENT"
    score = [[1.0 if i == j else 0.8 for j in range(4)] for i in range(4)]
    base = typed_cluster(keys, rel, score, tau=0.5)
    for perm in itertools.permutations(range(4)):
        k2 = [keys[i] for i in perm]
        r2 = [[rel[perm[i]][perm[j]] for j in range(4)] for i in range(4)]
        s2 = [[score[perm[i]][perm[j]] for j in range(4)] for i in range(4)]
        got = typed_cluster(k2, r2, s2, tau=0.5)
        assert got.n_clusters == base.n_clusters
        assert sorted(map(len, got.members)) == sorted(map(len, base.members))


def test_canonical_provision_tie_break_is_lexicographic():
    assert canonical_provision(["BNS 103", "IPC 302"]) == "BNS 103"
    assert canonical_provision(["NONE", "NONE"]) == "NONE"
    assert canonical_provision(["IPC 302", "IPC 302", "BNS 103"]) == "IPC 302"


def test_merge_score_is_symmetric_and_directional_labels_are_resolved():
    p = [[[0.0] * 5 for _ in range(2)] for _ in range(2)]
    p[0][1][LABEL2IDX["LEGALLY_EQUIVALENT"]] = 0.7
    p[1][0][LABEL2IDX["DIFFERENT_PROVISION"]] = 0.9
    s = merge_score_matrix(p)
    assert abs(s[0][1] - s[1][0]) < 1e-12
    assert abs(s[0][1] - 0.35) < 1e-12
    labels = argmax_labels(p)
    assert labels[0][1] == labels[1][0]


# -------------------------------------------------------------- statistics --
def test_entropy_and_agreement_on_known_shapes():
    assert entropy_bits([10]) == 0.0
    assert abs(entropy_bits([5, 5]) - 1.0) < 1e-12
    res = typed_cluster(["IPC 302"] * 10, _matrix(10, "SAME_PROVISION"), _matrix(10, 1.0), 0.5)
    st = typed_stats(res, _matrix(10, "SAME_PROVISION"), ["IPC 302"] * 10)
    assert st["agreement"] == 1.0 and st["all_same"] == 1 and st["entropy"] == 0.0
    assert st["entropy_norm"] == 0.0 and st["n_resolved"] == 10 and st["n_unique_keys"] == 1


def test_contradiction_mass_counts_only_contradicted_clusters():
    keys = ["IPC 302", "IPC 304"]
    rel = [["SAME_PROVISION", "CONTRADICTORY"], ["CONTRADICTORY", "SAME_PROVISION"]]
    res = typed_cluster(keys, rel, [[1.0, 0.0], [0.0, 1.0]], 0.5)
    assert contradiction_mass(res, rel) == 0.5


def test_merge_effect_reports_the_collision_loss():
    exact = {"agreement": 1.0, "entropy": 0.0, "n_clusters": 1, "all_same": 1}
    typed = {"agreement": 0.7, "entropy": 1.1, "n_clusters": 2, "all_same": 0}
    eff = merge_effect(exact, typed)
    assert eff["collision_lost"] == 1 and eff["d_agreement"] == pytest.approx(-0.3)


def test_per_class_metrics_and_undefined_class():
    f1, rows = per_class(["A", "A", "B"], ["A", "B", "B"], ("A", "B"))
    assert rows["A"]["precision"] == 1.0 and rows["A"]["recall"] == 0.5
    assert rows["B"]["support"] == 1 and 0 < f1 < 1


def test_exact_key_baseline_labels_by_construction():
    recs = [pair(label="SAME_PROVISION"),
            pair(text_b="Section 304 IPC applies.",
                 asserted_b={"act": "IPC", "provision": "304"}, label="DIFFERENT_PROVISION"),
            pair(text_b="Under the Bharatiya Nyaya Sanhita, s. 103 applies.",
                 asserted_b={"act": "BNS", "provision": "103"}, label="LEGALLY_EQUIVALENT",
                 ctx=CTX_LINK, stratum="S4")]
    assert 0.0 <= exact_key_baseline(recs, M.MERGE_RELATIONS) <= 1.0


# ---------------------------------------------------------- serialisation ---
def test_serialize_pair_is_stable_and_carries_context():
    s = M.serialize_pair("Answer one.", "Answer two.", CTX_LINK)
    assert s == ("[A] Answer one. [/A] [B] Answer two. [/B] "
                 "[CTX] as_of=2026-10-01; jurisdiction=IN; crosswalk=successor_of [/CTX]")
    assert "crosswalk=none" in M.serialize_pair("a", "b", CTX)
    assert "  " not in M.serialize_pair("a \n b", "c", CTX)


def test_checkpoint_metadata_contract_is_declared():
    assert M.SERIALISATION_VERSION and M.SEGMENT_TOKENS == {"a": 120, "b": 120, "ctx": 60}
    assert M.DEFAULT_ENCODER != M.CONTROL_ENCODER


# ---------------------------------------------------------------- optional --
@pytest.mark.skipif(not M.HAS_TORCH, reason="torch not installed")
def test_threshold_selection_maximises_merge_f1():  # pragma: no cover
    probs = [[0.9, 0, 0, 0.1, 0], [0.1, 0, 0, 0.9, 0], [0.8, 0, 0, 0.2, 0]]
    labels = ["SAME_PROVISION", "DIFFERENT_PROVISION", "LEGALLY_EQUIVALENT"]
    tau, stats = M.select_threshold(probs, labels)
    assert 0.0 < tau < 1.0 and stats["f1"] == 1.0


def test_identity_pairs_are_exactly_the_fully_resolved_duplicates():
    keys = ["IPC 302", "IPC 302", "BNS 103", "NONE", "NONE", "IPC 302"]
    assert identity_pairs(keys) == {(0, 1), (0, 5), (1, 5)}
    assert identity_pairs(["NONE"] * 10) == set()
    assert identity_pairs(["IPC 302"]) == set()


def test_identity_shortcut_cannot_change_the_clustering_outcome():
    """Filling rule-decided pairs with SAME_PROVISION must give the same partition as
    the real model would, because step 1 merges those pairs unconditionally."""
    keys = ["IPC 302", "IPC 302", "IPC 304"]
    forced = identity_pairs(keys)
    rel_rule = [["SAME_PROVISION"] * 3 for _ in range(3)]
    rel_model = [["DIFFERENT_PROVISION"] * 3 for _ in range(3)]
    for i in range(3):
        rel_model[i][i] = "SAME_PROVISION"
    for (i, j) in forced:
        rel_model[i][j] = rel_model[j][i] = "AMBIGUOUS"      # worst case: model says no
    score = [[1.0 if (min(i, j), max(i, j)) in forced or i == j else 0.0 for j in range(3)]
             for i in range(3)]
    a = typed_cluster(keys, rel_rule, score, 0.5)
    b = typed_cluster(keys, rel_model, score, 0.5)
    assert sorted(map(len, a.members)) == sorted(map(len, b.members)) == [1, 2]
