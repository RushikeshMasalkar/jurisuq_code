"""Phase C: the statute store -- provisions with validity intervals.

A ``StatuteStore`` is a read-only table indexed by ``'ACT section'`` keys such
as ``"IPC 302"`` or ``"BNS 303(2)"``. It answers three questions, and refuses
to invent an answer to a fourth:

* ``in_force(key, as_of)`` -> True / False / **None when unknown**
  (None is never coerced to False: a fabricated stale-law verdict on a
  provision the store has never heard of is the exact failure the coverage
  report exists to prevent);
* ``window(key)`` -> the validity interval ``(from, until_or_None)``;
* ``successor`` / ``predecessor`` -> the bracketing provision of the other era.

Boundary semantics are exact and are the pivot of the whole slice:
``in_force('IPC 302', '2024-06-30') is True`` and
``in_force('IPC 302', '2024-07-01') is False`` -- ``in_force_until`` is the
first date the provision is NOT in force.

Lookup resolution: exact key first; if absent, the base section (the key with
any ``(subsection)`` part stripped, e.g. ``IPC 307(1)`` -> ``IPC 307``),
because validity is a property of the whole section. Rows sharing a base
section must have identical windows (enforced by :func:`validate_rows`).

No learning component: this module imports nothing from torch/transformers.
"""
from __future__ import annotations

import datetime as _dt
import json
import pathlib
from collections.abc import Iterable, Sequence
from typing import Any

from jurisuq.facts import OFFENCES
from jurisuq.normalize import ACT_ALIASES

# The closed schema of a statute row (engineering spec v2, section 15.1).
FIELDS = ("act", "section", "title", "text_excerpt", "in_force_from",
          "in_force_until", "successor", "predecessor", "offence_cluster",
          "consequence_class", "verified")
CONSEQUENCE_CLASSES = frozenset({"custodial", "fine", "both", "procedural",
                                 "definition"})
VALID_ACTS = frozenset(ACT_ALIASES.values())
MAX_EXCERPT = 400


def normalize_key(key: str) -> str:
    """Canonical form of an ``'ACT section'`` key: upper act, single spaces."""
    return " ".join(str(key or "").upper().split())


def base_key(key: str) -> str:
    """The section-level key: ``'IPC 307(1)'`` -> ``'IPC 307'``."""
    k = normalize_key(key)
    i = k.find("(")
    return k[:i].strip() if i != -1 else k


def is_store_ref(key: str) -> bool:
    """Is this asserted key a real provision reference the store can answer for?

    The pipeline's sentinels are not provision references and must never be
    sent to the store: ``NONE`` (nothing asserted), ``FOREIGN:<x>`` (another
    legal order), ``UNKNOWN <n>`` (a section with no identifiable act) and
    ``'<ACT> (no section)'`` (an act with no section).
    """
    k = normalize_key(key)
    if not k or k == "NONE":
        return False
    if k.startswith("FOREIGN") or k.startswith("UNKNOWN"):
        return False
    if "(NO SECTION)" in k:
        return False
    return True


def _date(value: Any) -> _dt.date:
    if isinstance(value, _dt.date):
        return value
    return _dt.date.fromisoformat(str(value))


class StatuteStore:
    """Read-only index of statute rows keyed by ``'ACT section'``."""

    def __init__(self, rows: Sequence[dict]):
        self._rows: dict[str, dict] = {}
        self._base: dict[str, list[str]] = {}
        for row in rows:
            key = normalize_key(f"{row['act']} {row['section']}")
            if key in self._rows:
                raise ValueError(f"duplicate statute key: {key}")
            self._rows[key] = dict(row)
            self._base.setdefault(base_key(key), []).append(key)
        for keys in self._base.values():
            keys.sort()
            windows = {(self._rows[k]["in_force_from"],
                        self._rows[k]["in_force_until"]) for k in keys}
            if len(windows) > 1:
                raise ValueError(f"inconsistent validity windows within "
                                 f"section: {keys}")

    # -- lookups -------------------------------------------------------------

    def get(self, key: str) -> dict | None:
        """The row for ``key``: exact match first, then base-section fallback."""
        k = normalize_key(key)
        row = self._rows.get(k)
        if row is not None:
            return row
        matches = self._base.get(base_key(k))
        if not matches:
            return None
        # validity is a property of the section; windows are equal by validation
        return self._rows[matches[0]]

    def in_force(self, key: str, as_of: str) -> bool | None:
        """True / False / None-when-unknown. None is never coerced to False.

        ``in_force_from`` is inclusive; ``in_force_until`` is the first date
        the provision is no longer in force (exclusive), so a boundary date
        belongs to exactly one side of the transition.
        """
        row = self.get(key)
        if row is None:
            return None
        d = _date(as_of)
        if d < _date(row["in_force_from"]):
            return False
        until = row["in_force_until"]
        if until is not None and d >= _date(until):
            return False
        return True

    def window(self, key: str) -> tuple[str, str | None] | None:
        """``(in_force_from, in_force_until)``; None when the key is unknown."""
        row = self.get(key)
        if row is None:
            return None
        return (row["in_force_from"], row["in_force_until"])

    def successor(self, key: str) -> str | None:
        row = self.get(key)
        return row["successor"] if row is not None else None

    def predecessor(self, key: str) -> str | None:
        row = self.get(key)
        return row["predecessor"] if row is not None else None

    def coverage(self, keys: Iterable[str]) -> dict:
        """Known / unknown counts over the given keys, plus the unknown list.

        The counts exist so that a temporal factor computed over a subset of
        assertions can never be quoted as if it covered all of them.
        """
        keys = list(keys)
        unknown = sorted({normalize_key(k) for k in keys
                          if self.get(k) is None})
        known = sum(1 for k in keys if self.get(k) is not None)
        return {"assertions": len(keys), "known": known,
                "unknown": len(unknown), "unknown_keys": unknown}

    # -- introspection --------------------------------------------------------

    def keys(self) -> list[str]:
        return sorted(self._rows)

    def rows(self) -> list[dict]:
        return [dict(self._rows[k]) for k in self.keys()]

    def verified_share(self) -> float:
        if not self._rows:
            return float("nan")
        n = sum(1 for r in self._rows.values() if r.get("verified"))
        return n / len(self._rows)

    def __len__(self) -> int:
        return len(self._rows)

    def __contains__(self, key: str) -> bool:
        return normalize_key(key) in self._rows


# ---------------------------------------------------------------------------
# validation and loading
# ---------------------------------------------------------------------------

def validate_rows(rows: Sequence[dict]) -> list[str]:
    """Every structural property of the table, as a list of human-readable errors.

    An empty list is the only acceptable result of building a store: a table
    lookup is only safe if the table cannot be wrong in ways a caller would
    never notice.
    """
    errors: list[str] = []
    seen: dict[str, int] = {}
    for i, row in enumerate(rows):
        where = f"row {i} ({row.get('act', '?')} {row.get('section', '?')})"
        missing = [f for f in FIELDS if f not in row]
        if missing:
            errors.append(f"{where}: missing fields {missing}")
            continue
        if row["act"] not in VALID_ACTS:
            errors.append(f"{where}: act {row['act']!r} not in {sorted(VALID_ACTS)}")
        if not str(row["section"]).strip():
            errors.append(f"{where}: empty section")
        if not str(row["title"]).strip():
            errors.append(f"{where}: empty title")
        excerpt = str(row["text_excerpt"])
        if not excerpt.strip():
            errors.append(f"{where}: empty text_excerpt")
        elif len(excerpt) > MAX_EXCERPT:
            errors.append(f"{where}: text_excerpt exceeds {MAX_EXCERPT} chars "
                          f"({len(excerpt)})")
        try:
            frm = _date(row["in_force_from"])
        except (TypeError, ValueError):
            errors.append(f"{where}: in_force_from is not an ISO date")
            frm = None
        until = row["in_force_until"]
        if until is not None:
            try:
                until_d = _date(until)
                if frm is not None and until_d <= frm:
                    errors.append(f"{where}: in_force_until <= in_force_from")
            except (TypeError, ValueError):
                errors.append(f"{where}: in_force_until is not an ISO date or null")
        if row["offence_cluster"] not in OFFENCES:
            errors.append(f"{where}: offence_cluster {row['offence_cluster']!r} "
                          f"not in facts.OFFENCES")
        if row["consequence_class"] not in CONSEQUENCE_CLASSES:
            errors.append(f"{where}: consequence_class "
                          f"{row['consequence_class']!r} not in "
                          f"{sorted(CONSEQUENCE_CLASSES)}")
        if not isinstance(row["verified"], bool):
            errors.append(f"{where}: verified must be a bool")
        key = normalize_key(f"{row['act']} {row['section']}")
        if key in seen:
            errors.append(f"{where}: duplicate key {key} (first at row {seen[key]})")
        seen[key] = i

    def _target(row: dict, field: str, mirror: str) -> None:
        own_key = normalize_key(f"{row['act']} {row['section']}")
        where = f"row {own_key}"
        target = row.get(field)
        if target is None:
            return
        tkey = normalize_key(target)
        if tkey not in seen:
            errors.append(f"{where}: {field} {target!r} is not a row of this table")
            return
        other = rows[seen[tkey]]
        if normalize_key(other.get(mirror) or "") != own_key:
            errors.append(f"{where}: {field} {target!r} but {tkey}.{mirror} is "
                          f"{other.get(mirror)!r} (links must be symmetric)")

    for row in rows:
        _target(row, "successor", "predecessor")
        _target(row, "predecessor", "successor")
    return errors


def load_statutes(path: str | pathlib.Path) -> StatuteStore:
    """Load a JSONL statute table, validating every row before indexing."""
    p = pathlib.Path(path)
    rows = [json.loads(line) for line in p.read_text().splitlines()
            if line.strip()]
    errors = validate_rows(rows)
    if errors:
        raise ValueError(f"{p}: invalid statute table:\n  " +
                         "\n  ".join(errors))
    return StatuteStore(rows)
