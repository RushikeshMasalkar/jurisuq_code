"""Phase C: the link table -- declared legal relations between provisions.

The link table is the Phase B crosswalk (``data/relations/crosswalk_v1.jsonl``):
rows of ``(from, to, type)`` such as ``("IPC 302", "BNS 103", "successor_of")``
or ``("IPC 302", "IPC 304", "different_offence")``.

:func:`relation_between` is a **symmetric** lookup: ``relation_between(a, b)``
and ``relation_between(b, a)`` return the same declared type, because a merge
permitted in one direction only would be a silent asymmetry in every cluster
built on top of this table. Absence of a declared link is None, never a guess.

No learning component: this module imports nothing from torch/transformers.
"""
from __future__ import annotations

import json
import pathlib

from jurisuq.context.statute import normalize_key


def load_links(path: str | pathlib.Path) -> dict[tuple[str, str], str]:
    """``(from, to) -> type`` with both endpoints in canonical key form."""
    out: dict[tuple[str, str], str] = {}
    for line in pathlib.Path(path).read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        key = (normalize_key(r["from"]), normalize_key(r["to"]))
        out[key] = str(r.get("type", "successor_of"))
    return out


def relation_between(a: str, b: str, links: dict) -> str | None:
    """The declared relation type between two provision keys, or None.

    Symmetric by construction: both directions of the pair are consulted, so
    the answer cannot depend on argument order. Identity (``a == b``) has no
    declared link in the table and returns None -- equality is a rule the
    callers apply themselves, not a relation to be looked up.
    """
    ka, kb = normalize_key(a), normalize_key(b)
    rel = links.get((ka, kb))
    if rel is None:
        rel = links.get((kb, ka))
    return rel
