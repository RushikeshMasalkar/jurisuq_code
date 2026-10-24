"""Phase D: the common-mode failure detector (module M7).

The question the whole project turns on, asked once per item: *is the
agreement among the samples warranted by legal structure, or is it merely
repeated?*  A model that cites a repealed provision cites it confidently,
coherently and ten times out of ten -- the samples agree, but the agreement
is not legally warranted.  This module decomposes the observed agreement
into the part the legal context supports and the part it does not.

The detector's interface to the uncertainty estimator (Phase E) is a fixed
four-tuple plus flags, reproduced from the record alone so that an ablation
that removes the detector removes exactly one module and nothing else
(engineering guide v2, section 18):

    A   observed agreement   the modal cluster's share (unanimity is 1)
    T   temporal validity    share of the modal cluster whose asserted
                             provisions are in force at the item's as-of date
    J   jurisdiction fit     share of the modal cluster whose asserted
                             provisions belong to the declared legal order
    K   contradiction mass   probability mass of clusters whose relation to
                             the modal cluster is CONTRADICTORY
    W   warranted agreement  A * T * J * (1 - K)
    CM  common-mode score    A - W   (large positive == the failure signature)

Each factor is reported separately *before* they are composed, because a
single multiplicative score cannot be ablated factor by factor and its
failure modes cannot be attributed.  With the factors separate, Phase H can
remove the temporal factor alone and see exactly what changes.

The as-of date is the item's, not the analysis date.  An L7 item asks about
the law *today* (on or after 1 July 2024); an L1 item asks about the law
*immediately before* 1 July 2024.  The temporal factor is only meaningful
at the date the question asks about -- that is what makes the detector
silent on a correct pre-transition answer (IPC 302 *was* in force then) and
loud on a stale current-law answer (IPC 302 is not in force now).  Using a
single analysis date for both slices would make the detector fire on
everything, which the spec calls worthless.

No learning component: this module imports nothing from torch/transformers
and reads no correctness label.  It consumes agreement statistics and the
legal context (statute store, link table, jurisdiction), exactly as M7 is
specified to.
"""
from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from typing import Sequence

from jurisuq.context.statute import (StatuteStore, base_key,
                                     is_store_ref, normalize_key)
from jurisuq.normalize import CURRENT_CODES, REPEALED_CODES

# The legal orders the project declares.  A provision "belongs to the
# declared legal order" when its act is one of the Indian codes -- including
# the repealed ones, which are Indian law that is simply no longer in force.
INDIAN_ACTS = frozenset(REPEALED_CODES) | frozenset(CURRENT_CODES)

# The four flags the spec registers for the detector.
FLAG_STALE = "stale_provision"
FLAG_FOREIGN = "foreign_provision"
FLAG_CONTRADICTION = "internal_contradiction"
FLAG_UNRESOLVABLE = "unresolvable_assertion"


@dataclass(frozen=True)
class WarrantThresholds:
    """When a factor is treated as having 'fired'.

    Defaults are deliberately maximal-sensitivity: a factor fires on *any*
    not-in-force / not-Indian / contradictory mass in the modal cluster.  On
    the frozen collision population the factors are binary (a unanimous
    cluster is either entirely in force or entirely not), so any threshold in
    (0, 1) gives the same verdict there; the thresholds matter only for the
    partial clusters of the wider run and are reported, not hidden.
    """
    temporal: float = 1.0          # stale_provision fires when T < temporal
    jurisdiction: float = 1.0      # foreign_provision fires when J < jurisdiction
    contradiction: float = 0.0     # internal_contradiction fires when K > contradiction


@dataclass(frozen=True)
class EraPolicy:
    """How an item's as-of date is derived from its slice.

    ``era`` (the default) maps each slice to the date its question asks
    about: L7 -> the first day the new code is in force, L1 -> the last day
    the old code is in force.  ``fixed`` uses one supplied date for every
    item (the degenerate ablation that fires on both slices, kept so the
    temporal factor's necessity can be *shown*, not just asserted).
    """
    mode: str = "era"                       # "era" | "fixed"
    transition_date: str = "2024-07-01"     # first day BNS is in force
    slices: dict = field(default_factory=lambda: {
        "L7": "2024-07-01",   # current law begins
        "L1": "2024-06-30",   # pre-transition law (last day IPC is in force)
    })
    fixed_date: str = "2026-10-01"

    def as_of_for(self, slice_name: str) -> str:
        if self.mode == "fixed":
            return self.fixed_date
        return self.slices.get(slice_name, self.fixed_date)


@dataclass
class WarrantResult:
    """The detector's four-tuple and its provenance, for one item."""
    observed_agreement: float          # A
    temporal_validity: float | None    # T (None when the store cannot resolve)
    jurisdiction_fit: float | None     # J (None when no act is determinable)
    contradiction_mass: float | None   # K (None when there is no relation signal)
    warranted_agreement: float | None  # W = A*T*J*(1-K), None if a factor is None
    common_mode_score: float | None    # CM = A - W, None when W is None
    flags: list[str] = field(default_factory=list)
    modal_key: str = "NONE"
    modal_size: int = 0
    n_clusters: int = 0
    as_of: str = ""
    cluster_representation: str = "exact_key"
    contradiction_source: str = "none"
    factor_coverage: dict = field(default_factory=dict)

    def to_record(self) -> dict:
        """The flat ``warrant_*`` fields appended to a run record.

        Absent factors are written as ``None`` (JSON null), never as 0: a
        factor the store cannot resolve is missing, and a downstream reader
        must treat null as missing rather than as a confident zero.
        """
        return {
            "warrant_observed_agreement": self.observed_agreement,
            "warrant_temporal_validity": self.temporal_validity,
            "warrant_jurisdiction_fit": self.jurisdiction_fit,
            "warrant_contradiction_mass": self.contradiction_mass,
            "warrant_warranted_agreement": self.warranted_agreement,
            "warrant_common_mode_score": self.common_mode_score,
            "warrant_common_mode_flags": list(self.flags),
            "warrant_modal_key": self.modal_key,
            "warrant_modal_size": self.modal_size,
            "warrant_n_clusters": self.n_clusters,
            "warrant_as_of": self.as_of,
            "warrant_cluster_representation": self.cluster_representation,
            "warrant_contradiction_source": self.contradiction_source,
            "warrant_factor_coverage": self.factor_coverage,
        }

    @classmethod
    def from_record(cls, rec: dict) -> "WarrantResult":
        """Rebuild a result from a stored record's ``warrant_*`` fields.

        This is what makes the E4 validation cheap and honest: every
        number is reproduced from the record alone, with no
        re-detection and no access to anything but the stored fields.
        """
        return cls(
            observed_agreement=rec.get("warrant_observed_agreement"),
            temporal_validity=rec.get("warrant_temporal_validity"),
            jurisdiction_fit=rec.get("warrant_jurisdiction_fit"),
            contradiction_mass=rec.get("warrant_contradiction_mass"),
            warranted_agreement=rec.get("warrant_warranted_agreement"),
            common_mode_score=rec.get("warrant_common_mode_score"),
            flags=list(rec.get("warrant_common_mode_flags") or []),
            modal_key=rec.get("warrant_modal_key", "NONE"),
            modal_size=rec.get("warrant_modal_size", 0),
            n_clusters=rec.get("warrant_n_clusters", 0),
            as_of=rec.get("warrant_as_of", ""),
            cluster_representation=rec.get(
                "warrant_cluster_representation", "exact_key"),
            contradiction_source=rec.get(
                "warrant_contradiction_source", "none"),
            factor_coverage=rec.get("warrant_factor_coverage") or {},
        )


def _modal_cluster(keys: Sequence[str]) -> tuple[str, int, int]:
    """``(modal_key, modal_size, n_clusters)`` over exact assertion keys.

    Ties are broken lexicographically so the answer is a deterministic
    function of the key multiset and never of sample order.
    """
    counts = Counter(k for k in keys)
    if not counts:
        return "NONE", 0, 0
    ordered = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return ordered[0][0], ordered[0][1], len(counts)


def _cluster_groups(labels: Sequence[int] | None,
                    keys: Sequence[str]) -> list[list[str]]:
    """Cluster membership as lists of assertion keys.

    With no typed labels the exact-key partition is used: samples asserting
    the identical provision are one cluster.  This is the Phase A
    representation and the identity special case of the Phase B relation.
    """
    if labels is None:
        groups: dict[str, list[str]] = {}
        for k in keys:
            groups.setdefault(k, []).append(k)
        return list(groups.values())
    by_label: dict[int, list[str]] = {}
    for lab, k in zip(labels, keys):
        by_label.setdefault(lab, []).append(k)
    return list(by_label.values())


def rule_contradiction_mass(groups: Sequence[Sequence[str]],
                            modal_key: str,
                            different_offence: set[frozenset[str]]) -> float:
    """Rule-based K for records that carry no learned relation matrix.

    Two provision keys stand in a *declared* ``different_offence`` relation
    in the crosswalk when they are alternative charges for the same facts --
    legally mutually exclusive, so mass asserting one against the other is
    contradiction mass.  Only pairs the crosswalk actually declares are
    counted; an undeclared pair is not assumed contradictory (absence is
    never read as evidence).
    """
    total = sum(len(g) for g in groups)
    if total == 0:
        return 0.0
    mass = 0.0
    for g in groups:
        canon = Counter(g).most_common(1)[0][0] if g else "NONE"
        if canon == modal_key or canon == "NONE":
            continue
        pair = frozenset({normalize_key(modal_key), normalize_key(canon)})
        if pair in different_offence:
            mass += len(g) / total
    return mass


class WarrantDetector:
    """The common-mode failure detector (M7).

    Parameters
    ----------
    store:
        The Phase C statute store, queried for validity at each item's
        era as-of date.
    links:
        The Phase B crosswalk, used only for the rule-based contradiction
        approximation and for reporting; never needed for T or J.
    era:
        How an item's as-of date is derived from its slice.
    thresholds:
        When a factor counts as having fired.
    jurisdiction:
        The declared legal order (the context pack's jurisdiction).
    """

    def __init__(self, store: StatuteStore, links: dict | None = None,
                 era: EraPolicy | None = None,
                 thresholds: WarrantThresholds | None = None,
                 jurisdiction: str = "IN"):
        self.store = store
        self.links = links or {}
        self.era = era or EraPolicy()
        self.thresholds = thresholds or WarrantThresholds()
        self.jurisdiction = jurisdiction
        # Pairs the crosswalk declares to be different (mutually exclusive)
        # offences -- the only relation the rule-based K may use.
        self._different_offence: set[frozenset[str]] = set()
        for (a, b), rel in self.links.items():
            if rel == "different_offence":
                self._different_offence.add(frozenset({a, b}))

    # -- individual factors ------------------------------------------------

    def temporal_validity(self, group: Sequence[str], as_of: str) -> tuple[float | None, dict]:
        """T: share of the cluster whose asserted provisions are in force.

        None is returned only when *no* member's provision the store can
        resolve -- the factor is then undefined, never zero.  The coverage
        dict records how many members were resolvable, so a T computed over
        three of ten members is never quoted as if it covered all ten.
        """
        verdicts = [self.store.in_force(k, as_of) for k in group]
        known = [v for v in verdicts if v is not None]
        coverage = {"n": len(group), "known": len(known),
                    "unknown": len(group) - len(known)}
        if not known:
            return None, coverage
        return sum(1 for v in known if v) / len(known), coverage

    def jurisdiction_fit(self, group: Sequence[str]) -> tuple[float | None, dict]:
        """J: share of the cluster whose asserted provisions are Indian law.

        Members whose act cannot be determined are excluded from the
        denominator and reported in the coverage; a cluster of entirely
        undeterminable acts leaves J undefined.
        """
        acts = []
        for k in group:
            if k == "NONE" or k.startswith("FOREIGN"):
                acts.append("FOREIGN" if k.startswith("FOREIGN") else None)
                continue
            act = k.split()[0] if k.split() else None
            acts.append(act if act in INDIAN_ACTS or act == "FOREIGN" else act)
        determinable = [a for a in acts if a is not None]
        coverage = {"n": len(group), "determinable": len(determinable),
                    "unknown": len(group) - len(determinable)}
        if not determinable:
            return None, coverage
        indian = sum(1 for a in determinable if a in INDIAN_ACTS)
        return indian / len(determinable), coverage

    # -- the detector ------------------------------------------------------

    def detect(self, record: dict,
               cluster_labels: Sequence[int] | None = None,
               relation_matrix: Sequence[Sequence[str]] | None = None,
               contradiction_source: str = "auto"
               ) -> WarrantResult:
        """Score one run record.  Pure: it reads no correctness label."""
        keys = [str(k) for k in (record.get("asserted_keys") or [])]
        m = len(keys)
        slice_name = record.get("slice", "?")
        as_of = self.era.as_of_for(slice_name)

        groups = _cluster_groups(cluster_labels, keys)
        if cluster_labels is not None:
            representation = "typed"
        else:
            representation = "exact_key"

        # modal cluster and observed agreement A
        if cluster_labels is not None:
            sizes = sorted((len(g) for g in groups), reverse=True)
            modal_size = sizes[0] if sizes else 0
            n_clusters = len(sizes)
            modal_group = max(groups, key=len) if groups else []
            modal_counts = Counter(modal_group)
            modal_key = (sorted(modal_counts.items(),
                                key=lambda kv: (-kv[1], kv[0]))[0][0]
                         if modal_counts else "NONE")
        else:
            modal_key, modal_size, n_clusters = _modal_cluster(keys)
            modal_group = [k for k in keys if k == modal_key]
        A = (modal_size / m) if m else float("nan")

        # T and J over the modal cluster
        T, t_cov = self.temporal_validity(modal_group, as_of)
        J, j_cov = self.jurisdiction_fit(modal_group)

        # K: contradiction mass of the non-modal clusters against the modal
        use_rule = contradiction_source == "rule" or (
            contradiction_source == "auto" and self._different_offence)
        if use_rule and cluster_labels is not None:
            K = rule_contradiction_mass(groups, modal_key,
                                        self._different_offence)
            k_source = "rule_crosswalk_different_offence"
        elif contradiction_source == "none":
            K = None
            k_source = "none"
        elif relation_matrix is not None and cluster_labels is not None:
            K = self._model_contradiction_mass(groups, modal_group,
                                               relation_matrix, cluster_labels, m)
            k_source = "model"
        elif len(groups) <= 1:
            # a single cluster has nothing to contradict it: K is exactly 0,
            # not a default
            K = 0.0
            k_source = "exact_single_cluster"
        else:
            K = None                       # no relation signal for multi-cluster
            k_source = "no_relation_signal"

        flags: list[str] = []
        if T is None or J is None or K is None and len(groups) > 1:
            # an unresolvable factor is itself a finding: the assertion
            # cannot be legally grounded at all
            if T is None:
                flags.append(FLAG_UNRESOLVABLE)
        if T is not None and T < self.thresholds.temporal:
            flags.append(FLAG_STALE)
        if J is not None and J < self.thresholds.jurisdiction:
            flags.append(FLAG_FOREIGN)
        if K is not None and K > self.thresholds.contradiction:
            flags.append(FLAG_CONTRADICTION)

        # W and CM are composed only when every factor is defined
        if T is not None and J is not None and K is not None:
            W = A * T * J * (1.0 - K)
            CM = A - W
        else:
            W = None
            CM = None

        return WarrantResult(
            observed_agreement=A,
            temporal_validity=T,
            jurisdiction_fit=J,
            contradiction_mass=K,
            warranted_agreement=W,
            common_mode_score=CM,
            flags=flags,
            modal_key=modal_key,
            modal_size=modal_size,
            n_clusters=n_clusters,
            as_of=as_of,
            cluster_representation=representation,
            contradiction_source=k_source,
            factor_coverage={"temporal": t_cov, "jurisdiction": j_cov,
                             "n_clusters": n_clusters,
                             "modal_share": A},
        )

    def _model_contradiction_mass(self, groups, modal_group, relation_matrix,
                                  labels, m) -> float:
        """K from a learned relation matrix: mass of clusters whose relation
        to the modal cluster is CONTRADICTORY (majority of cross pairs)."""
        if m == 0 or not modal_group:
            return 0.0
        # index samples by cluster; the modal cluster is the one holding the
        # first sample of the largest group
        by_label: dict[int, list[int]] = {}
        for i, lab in enumerate(labels):
            by_label.setdefault(lab, []).append(i)
        modal_label = max(by_label, key=lambda l: len(by_label[l]))
        mass = 0.0
        for lab, members in by_label.items():
            if lab == modal_label:
                continue
            contrad = sum(1 for x in members for y in by_label[modal_label]
                          if relation_matrix[x][y] == "CONTRADICTORY")
            pairs = len(members) * len(by_label[modal_label])
            if pairs and contrad / pairs >= 0.5:
                mass += len(members) / m
        return mass


def compose(A: float, T: float | None, J: float | None,
            K: float | None) -> tuple[float | None, float | None]:
    """W = A*T*J*(1-K) and CM = A - W, or (None, None) if a factor is None.

    The product form is chosen because it is conservative -- any single
    factor at zero removes all warrant -- and because each factor can be
    ablated independently.
    """
    if T is None or J is None or K is None:
        return None, None
    W = A * T * J * (1.0 - K)
    return W, A - W


def _is_defined(x) -> bool:
    return x is not None and isinstance(x, (int, float)) and not math.isnan(x)
