"""21_attach_context.py -- attach Phase C context packs to a stored Phase A run.

    python scripts/21_attach_context.py --run-id phaseA-laptop-v2-rejudged \
            --out-suffix +ctx

Reads ``runs/<run-id>/items.jsonl`` READ-ONLY and writes a new sibling run
directory ``runs/<run-id><suffix>/`` whose records carry the registered field
``record['context']``: validity of every asserted / gold / trap provision at
the given ``as_of`` date, the declared crosswalk relation, and the coverage
counts. The source run is tree-hashed before and after (hard rule H2: a
frozen artefact is never edited) and the report records both hashes.

Nothing here samples, scores or learns -- it is a table lookup over stored
answers, so it is cheap, deterministic and re-runnable.
"""
from __future__ import annotations

import argparse
import collections
import datetime as _dt
import hashlib
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from jurisuq.context.links import load_links  # noqa: E402
from jurisuq.context.pack import attach_context, build_context  # noqa: E402
from jurisuq.context.statute import load_statutes  # noqa: E402


def tree_hash(d: pathlib.Path) -> str:
    """sha256 over every file of a directory tree (name + content), 24 hex."""
    h = hashlib.sha256()
    for p in sorted(d.rglob("*")):
        if p.is_file():
            h.update(p.name.encode())
            h.update(hashlib.sha256(p.read_bytes()).digest())
    return h.hexdigest()[:24]


def sha256_file(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run-id", required=True,
                    help="the stored Phase A run to pack (read-only)")
    ap.add_argument("--out-suffix", default="+ctx",
                    help="suffix for the new sibling run directory "
                         "(default: +ctx)")
    ap.add_argument("--as-of", default=_dt.date.today().isoformat(),
                    help="validity date, ISO 8601 (default: today)")
    ap.add_argument("--jurisdiction", default="IN")
    ap.add_argument("--statutes", default="data/statutes/statutes_v1.jsonl",
                    help="statute table (build it with 20_build_statutes.py)")
    ap.add_argument("--links", default="data/relations/crosswalk_v1.jsonl",
                    help="link table (the Phase B crosswalk)")
    ap.add_argument("--runs-dir", default="runs",
                    help="directory containing the run folders "
                         "(default: runs)")
    ap.add_argument("--limit", type=int, default=0,
                    help="pack only the first N items (smoke)")
    ap.add_argument("--force", action="store_true",
                    help="overwrite an existing output run directory")
    args = ap.parse_args()

    runs_dir = pathlib.Path(args.runs_dir)
    if not runs_dir.is_absolute():
        runs_dir = ROOT / runs_dir
    src = runs_dir / args.run_id
    items = src / "items.jsonl"
    if not items.exists():
        print(f"ERROR: no such run: {items}")
        print("       available runs:",
              ", ".join(sorted(p.name for p in runs_dir.iterdir()
                               if p.is_dir())) if runs_dir.exists() else "-")
        return 1
    out = runs_dir / f"{args.run_id}{args.out_suffix}"
    if out.exists() and not args.force:
        print(f"ERROR: {out} already exists (use --force to overwrite, "
              f"or a different --out-suffix)")
        return 1

    statutes = pathlib.Path(args.statutes)
    if not statutes.is_absolute():
        statutes = ROOT / statutes
    if not statutes.exists():
        print(f"ERROR: statute table not found: {statutes}")
        print("       run first: python scripts/20_build_statutes.py")
        return 1
    links_path = pathlib.Path(args.links)
    if not links_path.is_absolute():
        links_path = ROOT / links_path

    hash_before = tree_hash(src)
    store = load_statutes(statutes)
    links = load_links(links_path) if links_path.exists() else {}
    if not links:
        print(f"WARNING: link table not found at {links_path}; "
              f"crosswalk_relation will be null")

    records = [json.loads(l) for l in items.read_text().splitlines()
               if l.strip()]
    if args.limit:
        records = records[:args.limit]

    unknown_counter: collections.Counter = collections.Counter()
    in_force_counts = collections.Counter()
    per_slice: dict[str, dict] = collections.defaultdict(
        lambda: {"items": 0, "assertions": 0, "known": 0, "unknown": 0})
    relation_counts: collections.Counter = collections.Counter()
    excluded_total = 0

    for rec in records:
        ctx = build_context(rec, store, links, args.as_of, args.jurisdiction)
        attach_context(rec, ctx)
        sl = per_slice[rec.get("slice", "?")]
        sl["items"] += 1
        cov = ctx["coverage"]
        sl["assertions"] += cov["assertions"]
        sl["known"] += cov["known"]
        sl["unknown"] += cov["unknown"]
        excluded_total += ctx["excluded_assertions"]
        relation_counts[str(ctx["crosswalk_relation"])] += 1
        for k in cov["unknown_keys"]:
            unknown_counter[k] += 1
        for k, v in ctx["validity"].items():
            in_force_counts[str(v["in_force"])] += 1

    hash_after = tree_hash(src)
    untouched = hash_before == hash_after

    known = sum(v["known"] for v in per_slice.values())
    unknown = sum(v["unknown"] for v in per_slice.values())
    report = {
        "run_id": f"{args.run_id}{args.out_suffix}",
        "source_run": args.run_id,
        "phase": "C",
        "as_of": args.as_of,
        "jurisdiction": args.jurisdiction,
        "generated_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(
            timespec="seconds"),
        "statutes_file": str(statutes),
        "statutes_sha256": sha256_file(statutes),
        "statutes_rows": len(store),
        "statutes_verified_share": store.verified_share(),
        "links_file": str(links_path),
        "links_sha256": sha256_file(links_path) if links_path.exists() else None,
        "items_packed": len(records),
        "assertion_lookups": known + unknown,
        "known": known,
        "unknown": unknown,
        "coverage_share": (known / (known + unknown)) if known + unknown
                          else None,
        "excluded_assertions": excluded_total,
        "unknown_keys": dict(unknown_counter.most_common()),
        "in_force_counts": dict(in_force_counts),
        "crosswalk_relation_counts": dict(relation_counts),
        "per_slice": {k: dict(v) for k, v in sorted(per_slice.items())},
        "source_tree_hash_before": hash_before,
        "source_tree_hash_after": hash_after,
        "phase_a_untouched": untouched,
    }

    out.mkdir(parents=True, exist_ok=True)
    # newline="\n" everywhere: run artefacts are byte-identical on every
    # platform, so tree hashes and report hashes compare across machines
    with (out / "items.jsonl").open("w", encoding="utf-8", newline="\n") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    (out / "context_report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    meta = {
        "run_id": report["run_id"],
        "phase": "C",
        "source_run": args.run_id,
        "as_of": args.as_of,
        "jurisdiction": args.jurisdiction,
        "generated_utc": report["generated_utc"],
        "statutes_sha256": report["statutes_sha256"],
        "links_sha256": report["links_sha256"],
        "source_tree_hash": hash_after,
        "phase_a_untouched": untouched,
    }
    (out / "meta.json").write_text(json.dumps(meta, indent=2) + "\n",
                                   encoding="utf-8", newline="\n")

    print(f"packed {len(records)} items -> {out}")
    print(f"  as_of {args.as_of}   statutes rows {len(store)} "
          f"(verified share {store.verified_share():.2f})")
    print(f"  assertion lookups: {known + unknown}   known {known}   "
          f"unknown {unknown}"
          + (f"   coverage {known / (known + unknown):.3f}"
             if known + unknown else ""))
    if unknown_counter:
        top = ", ".join(f"{k} x{v}" for k, v in unknown_counter.most_common(8))
        print(f"  unknown keys (top): {top}")
    print(f"  in_force over validity entries: {dict(in_force_counts)}")
    print(f"  crosswalk_relation: {dict(relation_counts)}")
    print(f"  source run tree hash: {hash_before} -> {hash_after}")
    if untouched:
        print("  SOURCE RUN UNCHANGED (hard rule H2 satisfied)")
        return 0
    print("  ERROR: SOURCE RUN CHANGED -- investigate before trusting "
          "anything in this report")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
