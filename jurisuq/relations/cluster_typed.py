"""Typed clustering: turn pairwise relation predictions into clusters.

Order of operations is part of the specification:

  1. constraint  - samples asserting the identical, fully resolved provision are
                   merged unconditionally (this is the Phase A behaviour and it
                   bounds the damage any learned component can do);
  2. learned merge - remaining pairs merge when the symmetric merge score is at
                   or above the threshold and the predicted relation permits it;
  3. cycle repair - a merge that would join two clusters containing a blocking
                   pair is skipped, and the skip is recorded;
  4. canonicalisation - each cluster exposes one canonical provision.

The result is a deterministic function of (keys, relation matrix, merge scores,
threshold) and does not depend on the order in which samples are processed.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .schema import BLOCKING_RELATIONS, MERGE_RELATIONS


@dataclass
class ClusterResult:
    labels: list[int]                     # cluster index per sample, 0..k-1
    canonical: list[str]                  # canonical provision key per cluster
    members: list[list[int]]              # sample indices per cluster
    merges_applied: int = 0
    merges_skipped: int = 0
    forced_unions: int = 0
    flags: list[str] = field(default_factory=list)

    @property
    def n_clusters(self) -> int:
        return len(self.members)


class _UF:
    def __init__(self, n: int):
        self.p = list(range(n))
        self.sz = [1] * n

    def find(self, x: int) -> int:
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a: int, b: int) -> bool:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return False
        if self.sz[ra] < self.sz[rb]:
            ra, rb = rb, ra
        self.p[rb] = ra
        self.sz[ra] += self.sz[rb]
        return True

    def groups(self) -> dict[int, list[int]]:
        out: dict[int, list[int]] = {}
        for i in range(len(self.p)):
            out.setdefault(self.find(i), []).append(i)
        return out


def canonical_provision(keys: list[str]) -> str:
    """Most frequent non-NONE key; ties broken lexicographically (deterministic)."""
    counts: dict[str, int] = {}
    for k in keys:
        if k and k != "NONE":
            counts[k] = counts.get(k, 0) + 1
    if not counts:
        return "NONE"
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]


def identity_pairs(keys: list[str]) -> set[tuple[int, int]]:
    """Pairs (i, j), i < j, that the step-1 constraint merges without any model.

    Samples asserting the identical, fully resolved provision are merged
    unconditionally, so their relation never needs to be predicted: asking the
    encoder about them spends time on a decision that is already made by rule.
    """
    by_key: dict[str, list[int]] = {}
    for i, k in enumerate(keys):
        if k and k != "NONE":
            by_key.setdefault(k, []).append(i)
    out: set[tuple[int, int]] = set()
    for idxs in by_key.values():
        for a in range(len(idxs)):
            for b in range(a + 1, len(idxs)):
                out.add((idxs[a], idxs[b]))
    return out


def typed_cluster(keys: list[str], relation: list[list[str]], score: list[list[float]],
                  tau: float, block_contradictions: bool = True) -> ClusterResult:
    """Cluster M samples. All matrices are M x M and symmetric by construction."""
    m = len(keys)
    if m == 0:
        return ClusterResult([], [], [])
    for name, mat in (("relation", relation), ("score", score)):
        if len(mat) != m or any(len(row) != m for row in mat):
            raise ValueError(f"{name} matrix must be {m} x {m}")

    uf = _UF(m)
    res = ClusterResult([], [], [])

    # ---- step 1: unconditional merge on the identical resolved key --------
    first: dict[str, int] = {}
    for i, k in enumerate(keys):
        if k == "NONE":
            continue
        if k in first:
            if uf.union(first[k], i):
                res.forced_unions += 1
        else:
            first[k] = i

    # ---- step 2/3: learned merges in descending score order ---------------
    cands = []
    for i in range(m):
        for j in range(i + 1, m):
            if relation[i][j] in MERGE_RELATIONS and score[i][j] >= tau:
                cands.append((score[i][j], i, j, relation[i][j]))
    cands.sort(key=lambda t: (-t[0], t[1], t[2]))

    for s, i, j, rel in cands:
        ri, rj = uf.find(i), uf.find(j)
        if ri == rj:
            continue
        members_i = [x for x in range(m) if uf.find(x) == ri]
        members_j = [x for x in range(m) if uf.find(x) == rj]
        blocked = False
        for x in members_i:
            for y in members_j:
                rel_xy = relation[x][y]
                if rel_xy in BLOCKING_RELATIONS:
                    if rel_xy != "CONTRADICTORY" or block_contradictions:
                        blocked = True
                        break
                kx, ky = keys[x], keys[y]
                if kx != "NONE" and ky != "NONE" and kx != ky \
                        and rel_xy not in MERGE_RELATIONS:
                    blocked = True
                    break
            if blocked:
                break
        if blocked:
            res.merges_skipped += 1
        elif uf.union(i, j):
            res.merges_applied += 1

    # ---- step 4: labels, members, canonical provisions --------------------
    groups = uf.groups()
    # deterministic cluster numbering: by the smallest member index
    ordered = sorted(groups.values(), key=lambda g: min(g))
    labels = [0] * m
    canonical, members = [], []
    for ci, g in enumerate(ordered):
        g = sorted(g)
        for x in g:
            labels[x] = ci
        members.append(g)
        canonical.append(canonical_provision([keys[x] for x in g]))

    res.labels, res.canonical, res.members = labels, canonical, members
    if res.merges_skipped:
        res.flags.append("merge_skipped")
    if res.n_clusters == 1 and canonical and canonical[0] == "NONE":
        res.flags.append("all_unresolved")
    return res


def merge_score_matrix(prob_forward: list[list[list[float]]], labels=None) -> list[list[float]]:
    """Symmetric merge score from directional class probabilities.

    ``prob_forward[i][j]`` is the distribution over OPERATIONAL labels for the
    ordered pair (i, j). The score is the mean of the merge mass in both
    directions, which makes agreement unbreakable by directional asymmetry.
    """
    from .schema import MERGE_RELATIONS as _M, LABEL2IDX as _L

    idx = [_L[r] for r in _M]
    m = len(prob_forward)
    out = [[0.0] * m for _ in range(m)]
    for i in range(m):
        for j in range(m):
            if i == j:
                out[i][j] = 1.0
                continue
            fwd = sum(prob_forward[i][j][k] for k in idx)
            bwd = sum(prob_forward[j][i][k] for k in idx)
            out[i][j] = 0.5 * (fwd + bwd)
    return out


def argmax_labels(prob_forward: list[list[list[float]]]) -> list[list[str]]:
    """Deterministic relation label per ordered pair: the higher-scoring direction,
    with the lexicographically smaller label winning an exact tie."""
    from .schema import IDX2LABEL

    m = len(prob_forward)
    out = [["AMBIGUOUS"] * m for _ in range(m)]
    for i in range(m):
        for j in range(m):
            if i == j:
                out[i][j] = "SAME_PROVISION"
                continue
            p, q = prob_forward[i][j], prob_forward[j][i]
            vi = max(range(len(p)), key=lambda k: (p[k], -k))
            vj = max(range(len(q)), key=lambda k: (q[k], -k))
            li, lj = IDX2LABEL[vi], IDX2LABEL[vj]
            if abs(p[vi] - q[vj]) < 1e-12:
                out[i][j] = min(li, lj)
            else:
                out[i][j] = li if p[vi] >= q[vj] else lj
    return out
