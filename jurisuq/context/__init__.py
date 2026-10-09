"""Phase C: statute store and context packs.

Turns the project's temporal claims into table lookups. Two files and three
modules: a statute table with validity intervals (``data/statutes/``), a link
table with relation types (the Phase B crosswalk), a loader, and a context
builder that attaches the relevant entries to a record.

Nothing in this subpackage learns. No torch, no transformers, no network:
every property it provides is testable by inspection.
"""
from .links import load_links, relation_between  # noqa: F401
from .pack import attach_context, build_context  # noqa: F401
from .statute import (CONSEQUENCE_CLASSES, StatuteStore, is_store_ref,  # noqa: F401
                      load_statutes, normalize_key, validate_rows)
from .table import build_rows  # noqa: F401

__all__ = ["StatuteStore", "load_statutes", "validate_rows", "normalize_key",
           "is_store_ref", "CONSEQUENCE_CLASSES", "load_links",
           "relation_between", "build_context", "attach_context", "build_rows"]
