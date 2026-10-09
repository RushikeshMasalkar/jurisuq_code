"""Phase C: context packs -- attach the statute table to a record.

``build_context`` reads a record (a Phase A item, with its ``gold``, ``trap``
and ``asserted_keys`` fields) and packs the table entries the later phases
need: the validity of every real provision reference in the record, the
declared relation between the gold and trap provisions, and -- crucially --
the coverage counts, so a temporal factor computed over a subset of the
assertions can never be quoted as if it covered all of them.

The packed dict is stored under the registered field ``record['context']``
(engineering spec v2, section 15.2):

    {"as_of": "2026-10-01", "jurisdiction": "IN",
     "crosswalk_relation": "successor_of",
     "validity": {"IPC 302": {"in_force": false,
                              "window": ["1862-01-01", "2024-07-01"]}, ...},
     "coverage": {"assertions": 2, "known": 2, "unknown": 0,
                  "unknown_keys": []},
     "excluded_assertions": 0}

H1 note: this pack reads only the *question-side* fields of a record (gold
and trap are part of the item definition, like the question itself) and the
asserted provision keys. It never reads correctness verdicts, so nothing on
the query path can see the answer key through the context.

No learning component: this module imports nothing from torch/transformers.
"""
from __future__ import annotations

from jurisuq.context.links import relation_between
from jurisuq.context.statute import is_store_ref, normalize_key


def _part_key(part: dict | None) -> str | None:
    """``'IPC 302'`` from a ``{'act', 'provision', ...}`` part, else None."""
    if not part or not part.get("act") or not part.get("provision"):
        return None
    return normalize_key(f"{part['act']} {part['provision']}")


def _unique(seq) -> list[str]:
    out: list[str] = []
    for k in seq:
        if k not in out:
            out.append(k)
    return out


def build_context(record: dict, store, links: dict, as_of: str,
                  jurisdiction: str = "IN") -> dict:
    """Pack the statute/link entries a record needs, at date ``as_of``.

    * ``validity`` covers the asserted provisions plus the gold and trap
      provisions of the item (the provisions the question is *about*), with
      ``in_force`` and ``window`` per key -- ``in_force`` is None for keys the
      store has never heard of, and that None is carried, never coerced;
    * ``coverage`` counts only real provision references among the asserted
      keys (sentinels ``NONE`` / ``FOREIGN:*`` / ``UNKNOWN n`` / ``<ACT> (no
      section)`` are not provision references; their count is reported
      separately as ``excluded_assertions``);
    * ``crosswalk_relation`` is the declared relation between the trap and
      the gold provision, symmetric, or None when undeclared or when the item
      has no trap.
    """
    asserted = [str(k) for k in (record.get("asserted_keys") or [])]
    refs_asserted = _unique([k for k in asserted if is_store_ref(k)])
    excluded = len(_unique(asserted)) - len(refs_asserted)

    gold_key = _part_key(record.get("gold"))
    trap_key = _part_key(record.get("trap"))

    validity = {}
    for k in _unique(refs_asserted + [x for x in (gold_key, trap_key) if x]):
        win = store.window(k)
        validity[k] = {
            "in_force": store.in_force(k, as_of),
            "window": list(win) if win is not None else None,
        }

    crosswalk_relation = None
    if gold_key and trap_key:
        crosswalk_relation = relation_between(trap_key, gold_key, links)

    return {
        "as_of": as_of,
        "jurisdiction": jurisdiction,
        "crosswalk_relation": crosswalk_relation,
        "validity": validity,
        "coverage": store.coverage(refs_asserted),
        "excluded_assertions": excluded,
    }


def attach_context(rec: dict, ctx: dict) -> None:
    """Store ``ctx`` under the registered field ``rec['context']``, replacing
    any previous pack (a record carries exactly one context)."""
    rec["context"] = ctx
