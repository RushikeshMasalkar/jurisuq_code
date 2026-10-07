"""Phase B: typed legal relations, their dataset, clustering and statistics."""
from .schema import (BLOCKING_RELATIONS, EVIDENCE, IDX2LABEL, LABEL2IDX,  # noqa: F401
                     MERGE_RELATIONS, OPERATIONAL, RELATIONS, RESERVED, SCHEMA_VERSION,
                     STRATA, Assertion, PairError, PairRecord, make_pair, pair_id,
                     text_hash)

__all__ = ["OPERATIONAL", "EVIDENCE", "RESERVED", "RELATIONS", "MERGE_RELATIONS",
           "BLOCKING_RELATIONS", "LABEL2IDX", "IDX2LABEL", "STRATA", "SCHEMA_VERSION",
           "Assertion", "PairRecord", "PairError", "make_pair", "pair_id", "text_hash"]
