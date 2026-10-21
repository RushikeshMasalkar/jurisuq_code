"""Deterministic pair-grouped development/test split for the Phase E pilot."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


def load_pair_ids(path: Path) -> dict[str, str]:
    pairs = {}
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            item_id, pair_id = row.get("item_id"), row.get("pair_id")
            if not isinstance(item_id, str) or not isinstance(pair_id, str):
                raise ValueError(f"{path}:{line_no}: item_id and pair_id must be strings")
            if item_id in pairs and pairs[item_id] != pair_id:
                raise ValueError(f"duplicate item_id with conflicting pair_id: {item_id}")
            pairs[item_id] = pair_id
    return pairs


def split_name(pair_id: str, *, seed: str = "phaseE-v1", test_fraction: float = 0.20) -> str:
    """Assign matched L1/L7 pair groups to test by stable SHA-256 threshold."""
    if not 0.0 < test_fraction < 1.0:
        raise ValueError("test_fraction must be between 0 and 1")
    digest = hashlib.sha256(f"{seed}|{pair_id}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:8], "big") / float(2**64)
    return "test" if value < test_fraction else "development"
