"""Relation and pair schema for Phase B (typed legal relations).

The label set is closed. Operational labels are learned by the pair classifier;
evidence labels are computed by rules elsewhere in the pipeline and are never
predicted; reserved labels are placeholders for Phase C onward and must not be
emitted by any Phase B artefact.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field

SCHEMA_VERSION = "pb1"

# ---- the label set (closed) ------------------------------------------------
OPERATIONAL = ("SAME_PROVISION", "LEGALLY_EQUIVALENT", "CONDITIONALLY_EQUIVALENT",
               "DIFFERENT_PROVISION", "AMBIGUOUS")
EVIDENCE = ("CONTRADICTORY", "OUTDATED_PROVISION")
RESERVED = ("TEMPORAL_MISMATCH", "JURISDICTION_MISMATCH")
RELATIONS = OPERATIONAL + EVIDENCE + RESERVED

# relations that permit a merge in typed clustering
MERGE_RELATIONS = frozenset({"SAME_PROVISION", "LEGALLY_EQUIVALENT",
                             "CONDITIONALLY_EQUIVALENT"})
# relations that block a merge even when the score is high
BLOCKING_RELATIONS = frozenset({"DIFFERENT_PROVISION", "AMBIGUOUS", "CONTRADICTORY"})

LABEL2IDX = {r: i for i, r in enumerate(OPERATIONAL)}
IDX2LABEL = {i: r for r, i in LABEL2IDX.items()}

SPLITS = ("train", "dev", "test")
# S1..S7 as specified in the master guide, section 13/14
STRATA = {
    "S1": "same provision, paraphrase (easy positive)",
    "S2": "same provision, heavy paraphrase / reordered (hard positive)",
    "S3": "context-dependent: identical text under two contexts",
    "S4": "crosswalk-equivalent provisions across the transition",
    "S5": "hard negative: adjacent sections of the same act",
    "S6": "hard negative: same number, different act",
    "S7": "ambiguous: act-only or truncated assertion",
}
VERIFIERS = ("human", "rule", "model", "pending")

_WS = re.compile(r"\s+")


class PairError(ValueError):
    """Raised when a pair record fails schema validation."""


def normalize_text(text: str) -> str:
    """Whitespace-collapse and casefold-strip; used only for hashing and dedup."""
    return _WS.sub(" ", (text or "").strip())


def text_hash(text: str) -> str:
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()[:16]


def pair_id(text_a: str, text_b: str, context_key: str) -> str:
    """Deterministic identity of a pair: order-independent in the two answers."""
    ha, hb = sorted((text_hash(text_a), text_hash(text_b)))
    h = hashlib.sha256(f"{ha}|{hb}|{context_key}".encode("utf-8")).hexdigest()
    return f"{SCHEMA_VERSION}-{h[:16]}"


@dataclass
class Assertion:
    """The provision an answer asserts, in comparable form (mirrors the judge)."""
    act: str | None = None
    provision: str | None = None

    def key(self) -> str:
        if self.act is None and self.provision is None:
            return "NONE"
        act = self.act or "UNKNOWN_ACT"
        if act == "FOREIGN":
            return f"FOREIGN:{self.provision or '?'}"
        return f"{act} {self.provision}" if self.provision else f"{act} (no section)"


@dataclass
class PairRecord:
    """One training/evaluation pair. Field names are frozen by the master guide."""
    pair_id: str
    dataset_version: str
    split: str
    stratum: str
    answer_a: dict                      # {"text": str, "asserted": dict | None}
    answer_b: dict
    context: dict                       # {"as_of": str, "jurisdiction": str,
                                        #  "crosswalk_relation": str | None}
    label: str
    label_source: str = "rule"
    condition_tag: str | None = None
    provenance: dict = field(default_factory=dict)
    verifier: str = "pending"
    text_hash: str = ""

    # ---- validation -------------------------------------------------------
    def validate(self) -> None:
        if self.label not in RELATIONS:
            raise PairError(f"label {self.label!r} not in the closed label set")
        if self.label in RESERVED:
            raise PairError(f"{self.label} is reserved for later phases and must not be "
                            "emitted by Phase B")
        if self.split not in SPLITS:
            raise PairError(f"split {self.split!r} not in {SPLITS}")
        if self.stratum not in STRATA:
            raise PairError(f"stratum {self.stratum!r} not in {tuple(STRATA)}")
        if self.verifier not in VERIFIERS:
            raise PairError(f"verifier {self.verifier!r} not in {VERIFIERS}")
        for side in ("answer_a", "answer_b"):
            a = self.answer_a if side == "answer_a" else self.answer_b
            if not isinstance(a, dict) or "text" not in a:
                raise PairError(f"{side} must be a dict with a 'text' field")
            if not normalize_text(a["text"]):
                raise PairError(f"{side}.text is empty")
            asserted = a.get("asserted")
            if asserted is not None and not isinstance(asserted, dict):
                raise PairError(f"{side}.asserted must be null or a dict")
        if self.label == "CONDITIONALLY_EQUIVALENT" and not self.condition_tag:
            raise PairError("CONDITIONALLY_EQUIVALENT requires a condition_tag")
        if self.label != "CONDITIONALLY_EQUIVALENT" and self.condition_tag:
            raise PairError("condition_tag is only meaningful for CONDITIONALLY_EQUIVALENT")
        if self.label == "AMBIGUOUS" and self.answer_a.get("asserted") \
                and self.answer_b.get("asserted"):
            ka = Assertion(**self.answer_a["asserted"]).key()
            kb = Assertion(**self.answer_b["asserted"]).key()
            if ka != "NONE" and kb != "NONE" and ka == kb:
                raise PairError("two identical, fully resolved assertions cannot be AMBIGUOUS")
        if not self.pair_id:
            raise PairError("pair_id is required")

    # ---- (de)serialisation ------------------------------------------------
    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_json(cls, line: str) -> "PairRecord":
        return cls(**json.loads(line))

    def key_a(self) -> str:
        a = self.answer_a.get("asserted")
        return Assertion(**a).key() if a else "NONE"

    def key_b(self) -> str:
        b = self.answer_b.get("asserted")
        return Assertion(**b).key() if b else "NONE"


def make_pair(text_a: str, asserted_a: dict | None, text_b: str, asserted_b: dict | None,
              context: dict, label: str, dataset_version: str, split: str, stratum: str,
              label_source: str = "rule", condition_tag: str | None = None,
              provenance: dict | None = None, verifier: str = "pending") -> PairRecord:
    """Build a validated pair in one call."""
    ctx_key = f"{context.get('as_of')}|{context.get('jurisdiction')}|" \
              f"{context.get('crosswalk_relation')}"
    rec = PairRecord(
        pair_id=pair_id(text_a, text_b, ctx_key),
        dataset_version=dataset_version,
        split=split,
        stratum=stratum,
        answer_a={"text": text_a, "asserted": asserted_a},
        answer_b={"text": text_b, "asserted": asserted_b},
        context=dict(context),
        label=label,
        label_source=label_source,
        condition_tag=condition_tag,
        provenance=provenance or {},
        verifier=verifier,
        text_hash=text_hash(text_a + "\u241f" + text_b),
    )
    rec.validate()
    return rec
