"""Phase G Stage 2: the candidate-item-set contract.

Phase G's "Remaining work" (`PHASE-G.md`) fixes the first step of Stage 2 in a
single sentence:

    author an approved candidate item set in the Phase A schema with
    ``verified: false`` provenance

Two parts of that sentence are mechanically checkable, and this module checks
exactly those two and nothing else:

*Phase A schema*
    the fields the pipeline actually consumes when it builds a record: a
    non-empty ``item_id``, ``pair_id``, ``slice`` and ``question``, and a
    ``gold`` object carrying both ``act`` and ``provision``. ``slice`` must be
    one of the benchmark's two slices.

*``verified: false`` provenance*
    every item must carry a ``provenance`` object whose ``verified`` flag is
    present and **exactly** ``False``, plus a non-empty ``source`` describing
    where the item came from. This is the same convention Phase A records use
    (``provenance.verified = false``) and Phase C's statute rows use for
    rows no human has checked. The point is that items written for the
    Stage 2 screen are, by construction, unverified: they are proposals for
    measurement, not established benchmark rows. An item that claims
    ``verified: true`` must be refused, because the screen's job is to decide
    whether such items are worth a run, and no review has happened yet.

What this module deliberately does **not** do: it does not decide whether an
item is legally correct, whether its gold provision is right, whether the item
is answerable, or whether any gate passes. It is a contract check on a file
before the screen spends compute on it, not an evaluation. Nothing here calls a
model or reaches the network.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from jurisuq.pilot import sha256_file

#: The item fields the Phase A pipeline consumes when it builds a record.
#: ``gold.act`` and ``gold.provision`` are checked separately below.
REQUIRED_ITEM_FIELDS = ("item_id", "pair_id", "slice", "question")

#: The benchmark's two slices. A third slice would be a new experiment, not a
#: Stage 2 candidate set, so it is refused rather than silently accepted.
ALLOWED_SLICES = ("L1", "L7")

#: The provenance flag Stage 2 requires on every candidate item.
REQUIRED_PROVENANCE_VERIFIED = False


class CandidateContractError(ValueError):
    """A candidate item set does not satisfy the documented Stage 2 contract."""


def content_sha256(path: str | Path) -> str:
    """SHA-256 of the candidate file's content.

    Shares :func:`jurisuq.pilot.sha256_file`'s semantics so a Windows
    ``core.autocrlf`` checkout does not change the recorded hash.
    """
    return sha256_file(path)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CandidateContractError(message)


def validate_item(item: dict, *, index: int | None = None) -> None:
    """Check one candidate item against the contract, or raise."""
    where = f"item {item.get('item_id')!r}" if item.get("item_id") else f"item #{index}"

    missing = [field for field in REQUIRED_ITEM_FIELDS if not item.get(field)]
    _require(not missing, f"ERROR: {where} is missing {missing}")

    _require(item["slice"] in ALLOWED_SLICES,
             f"ERROR: {where} has slice {item['slice']!r}; "
             f"expected one of {ALLOWED_SLICES}")

    gold = item.get("gold")
    _require(isinstance(gold, dict), f"ERROR: {where} needs a gold object")
    missing_gold = [field for field in ("act", "provision") if not gold.get(field)]
    _require(not missing_gold,
             f"ERROR: {where} needs gold.act and gold.provision "
             f"(missing: {missing_gold})")

    provenance = item.get("provenance")
    _require(isinstance(provenance, dict),
             f"ERROR: {where} needs a provenance object, because Stage 2 items "
             "must declare where they came from")
    _require("verified" in provenance,
             f"ERROR: {where} provenance is missing the 'verified' flag; "
             f"Stage 2 requires verified: {REQUIRED_PROVENANCE_VERIFIED}")
    _require(provenance["verified"] is REQUIRED_PROVENANCE_VERIFIED,
             f"ERROR: {where} declares provenance.verified = "
             f"{provenance['verified']!r}; a Stage 2 candidate item must be "
             f"verified: {REQUIRED_PROVENANCE_VERIFIED} because it has not been "
             "reviewed yet")
    _require(isinstance(provenance.get("source"), str) and provenance["source"].strip(),
             f"ERROR: {where} needs a non-empty provenance.source")


def validate_candidates(items: list[dict]) -> dict:
    """Validate a whole candidate set and summarise it.

    Returns a small machine-readable summary suitable for a report payload.
    Raises :class:`CandidateContractError` on the first violation.
    """
    _require(bool(items), "ERROR: the candidate item set contains no items")

    seen: set[str] = set()
    for index, item in enumerate(items):
        _require(isinstance(item, dict),
                 f"ERROR: item #{index} is {type(item).__name__}, not an object")
        validate_item(item, index=index)
        _require(item["item_id"] not in seen,
                 f"ERROR: duplicate item_id {item['item_id']!r}")
        seen.add(item["item_id"])

    slices = Counter(item["slice"] for item in items)
    sources = sorted({str(item["provenance"]["source"]) for item in items})
    return {
        "schema": "Phase A item schema",
        "source_document": "PHASE-G.md, 'Remaining work: all of it blocked on "
                           "the pilot' (Stage 2, step 1)",
        "n_items": len(items),
        "slices": dict(sorted(slices.items())),
        "provenance_verified": REQUIRED_PROVENANCE_VERIFIED,
        "provenance_sources": sources,
        "checked": ["required_fields", "slice", "gold.act", "gold.provision",
                    "unique_item_id", "provenance.verified", "provenance.source"],
        "not_checked": ["legal correctness of gold", "answerability",
                        "duplicate questions across items", "any gate"],
    }


def load_candidates(path: str | Path) -> list[dict]:
    """Read a candidate jsonl file and validate it against the contract."""
    path = Path(path)
    if not path.is_file():
        raise CandidateContractError(f"ERROR: candidate file not found: {path}")
    items = [json.loads(line) for line in
             path.read_text(encoding="utf-8").splitlines() if line.strip()]
    validate_candidates(items)
    return items
