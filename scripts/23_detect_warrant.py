"""23_detect_warrant.py -- attach the Phase D warrant tuple to a run.

    python scripts/23_detect_warrant.py \
        --run-id phaseA-laptop-v2-rejudged+ctx \
        --out-suffix +warrant

Reads ``runs/<run-id>/items.jsonl`` READ-ONLY and writes a new sibling
run directory ``runs/<run-id><suffix>/`` whose records carry the
registered ``warrant_*`` fields: the four factors (A, T, J, K), the
composed warranted agreement W and common-mode score CM, the flags
that fired, and the provenance needed to attribute every number
(the item's as-of date, the cluster representation, the contradiction
source, and the per-factor coverage).

The detector is a pure table lookup over stored answers: it samples
nothing, scores nothing and learns nothing, so it is cheap,
deterministic and re-runnable.  Like Phase C it hashes the source run
before and after and fails the integrity rule (hard rule H2: a frozen
artefact is never edited) if the source tree changes.

The as-of date is the item's era date by default (L7 -> the first day
the new code is in force; L1 -> the last day the old code is in
force), because the temporal factor is only meaningful at the date the
question asks about.  ``--as-of-policy fixed --fixed-as-of DATE`` pins
one date for every item; that is the deliberate ablation that fires on
both slices, kept so the temporal factor's necessity can be shown.
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

from jurisuq.context import load_links, load_statutes  # noqa: E402
from jurisuq.relations.schema import RELATIONS  # noqa: E402
from jurisuq.warrant.detector import (EraPolicy,  # noqa: E402
                                        WarrantDetector, WarrantThresholds,
                                        _cluster_groups)


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
                    help="the stored run to detect on (read-only); "
                         "use the Phase C +ctx run")
    ap.add_argument("--out-suffix", default="+warrant",
                    help="suffix for the new sibling run directory "
                         "(default: +warrant)")
    ap.add_argument("--statutes", default="data/statutes/statutes_v1.jsonl",
                    help="statute table (build it with 20_build_statutes.py)")
    ap.add_argument("--links", default="data/relations/crosswalk_v1.jsonl",
                    help="link table (the Phase B crosswalk)")
    ap.add_argument("--runs-dir", default="runs",
                    help="directory containing the run folders (default: runs)")
    ap.add_argument("--as-of-policy", choices=("era", "fixed"),
                    default="era",
                    help="how each item's as-of date is derived "
                         "(default: era, from the slice)")
    ap.add_argument("--fixed-as-of", default="2026-10-01",
                    help="the date used under --as-of-policy fixed")
    ap.add_argument("--jurisdiction", default="IN")
    ap.add_argument("--stale-threshold", type=float, default=1.0)
    ap.add_argument("--jurisdiction-threshold", type=float, default=1.0)
    ap.add_argument("--contradiction-threshold", type=float, default=0.0)
    ap.add_argument("--cluster-source", choices=("auto", "exact", "typed"),
                    default="auto")
    ap.add_argument("--contradiction-source",
                    choices=("auto", "rule", "model", "none"),
                    default="auto")
    ap.add_argument("--limit", type=int, default=0,
                    help="detect on only the first N items (smoke)")
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
    raw_links = [
        json.loads(line) for line in links_path.read_text().splitlines()
        if line.strip()
    ] if links_path.exists() else []
    different_offence_rows = [
        row for row in raw_links if row.get("type") == "different_offence"
    ]
    era = EraPolicy(mode=args.as_of_policy,
                    fixed_date=args.fixed_as_of)
    thresholds = WarrantThresholds(
        temporal=args.stale_threshold,
        jurisdiction=args.jurisdiction_threshold,
        contradiction=args.contradiction_threshold)
    detector = WarrantDetector(store, links, era=era,
                                 thresholds=thresholds,
                                 jurisdiction=args.jurisdiction)

    records = [json.loads(l) for l in items.read_text().splitlines()
               if l.strip()]
    if args.limit:
        records = records[:args.limit]

    fire_counts: collections.Counter = collections.Counter()
    flag_counts: collections.Counter = collections.Counter()
    rep_counts: collections.Counter = collections.Counter()
    ksrc_counts: collections.Counter = collections.Counter()
    fallback_counts: collections.Counter = collections.Counter()
    typed_modal_trap_counts = collections.Counter({"L1": 0, "L7": 0})
    dataset_path = ROOT / "data" / "lexuq_slice.jsonl"
    dataset = {r["item_id"]: r for r in (
        json.loads(line) for line in dataset_path.read_text().splitlines()
        if line.strip())}
    cm_defined = 0
    per_slice: dict[str, dict] = collections.defaultdict(
        lambda: {"items": 0, "fires": 0, "cm_defined": 0,
                 "cm_sum": 0.0})

    for rec in records:
        labels = rec.get("clusters") if args.cluster_source in ("auto", "typed") else None
        relation = rec.get("relation_matrix") if args.cluster_source in ("auto", "typed") else None
        typed_valid = (
            isinstance(labels, list) and len(labels) == len(rec.get("asserted_keys") or [])
            and isinstance(relation, list) and len(relation) == len(labels)
            and all(isinstance(row, list) and len(row) == len(labels) for row in relation)
            and all(value in RELATIONS for row in relation for value in row)
        )
        if args.cluster_source == "exact":
            labels = relation = None
        elif not typed_valid:
            if args.cluster_source == "typed" or args.cluster_source == "auto":
                fallback_counts["invalid_typed_signal"] += 1
            labels = relation = None
        if labels is not None:
            keys = rec.get("asserted_keys") or []
            groups = _cluster_groups(labels, keys)
            source_item = dataset.get(rec.get("item_id"), {})
            gold = f"{source_item.get('gold_act')} {source_item.get('gold_provision')}"
            trap = f"{source_item.get('trap_act')} {source_item.get('trap_provision')}"
            modal = max(groups, key=len, default=[])
            if gold in modal and trap in modal:
                typed_modal_trap_counts[rec.get("slice", "?")] += 1
        res = detector.detect(
            rec, cluster_labels=labels, relation_matrix=relation,
            contradiction_source=args.contradiction_source)
        rec.update(res.to_record())
        sl = per_slice[rec.get("slice", "?")]
        sl["items"] += 1
        fire_counts["fires" if res.flags else "silent"] += 1
        for f in res.flags:
            flag_counts[f] += 1
        rep_counts[res.cluster_representation] += 1
        ksrc_counts[res.contradiction_source] += 1
        if res.common_mode_score is not None:
            cm_defined += 1
            sl["cm_defined"] += 1
            sl["cm_sum"] += res.common_mode_score
        if res.flags:
            sl["fires"] += 1

    hash_after = tree_hash(src)
    untouched = hash_before == hash_after

    report = {
        "run_id": f"{args.run_id}{args.out_suffix}",
        "source_run": args.run_id,
        "phase": "D",
        "experiment": "E4-detector",
        "generated_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(
            timespec="seconds"),
        "statutes_file": str(statutes),
        "statutes_sha256": sha256_file(statutes),
        "statutes_rows": len(store),
        "links_file": str(links_path),
        "links_sha256": sha256_file(links_path) if links_path.exists()
                        else None,
        "as_of_policy": args.as_of_policy,
        "fixed_as_of": args.fixed_as_of if args.as_of_policy == "fixed"
                       else None,
        "era_reference_dates": dict(era.slices),
        "jurisdiction": args.jurisdiction,
        "thresholds": {"temporal": args.stale_threshold,
                       "jurisdiction": args.jurisdiction_threshold,
                       "contradiction": args.contradiction_threshold},
        "cluster_source": args.cluster_source,
        "contradiction_source_requested": args.contradiction_source,
        "items_detected": len(records),
        "fires": fire_counts["fires"],
        "silent": fire_counts["silent"],
        "fire_rate": (fire_counts["fires"] / len(records)) if records
                     else None,
        "cm_defined": cm_defined,
        "cm_undefined": len(records) - cm_defined,
        "flag_counts": dict(flag_counts),
        "cluster_representation_counts": dict(rep_counts),
        "contradiction_source_counts": dict(ksrc_counts),
        "typed_signal_fallback_counts": dict(fallback_counts),
        "typed_modal_cluster_contains_gold_and_trap": {
            "overall": sum(typed_modal_trap_counts.values()),
            "per_slice": dict(sorted(typed_modal_trap_counts.items())),
        },
        "crosswalk_different_offence_rows": len(different_offence_rows),
        "crosswalk_different_offence_rows_verified": False,
        "crosswalk_different_offence_unverified_rows": sum(
            1 for row in different_offence_rows if row.get("verified") is not True),
        "dataset_sha256": sha256_file(dataset_path),
        "per_slice": {k: dict(v) for k, v in sorted(per_slice.items())},
        "source_tree_hash_before": hash_before,
        "source_tree_hash_after": hash_after,
        "source_run_untouched": untouched,
    }

    out.mkdir(parents=True, exist_ok=True)
    # newline="\n" everywhere: run artefacts are byte-identical on
    # every platform, so tree hashes and report hashes compare across
    # machines (the same rule Phase C established)
    with (out / "items.jsonl").open("w", encoding="utf-8",
                                    newline="\n") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    (out / "warrant_report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8",
        newline="\n")
    meta = {
        "run_id": report["run_id"],
        "phase": "D",
        "source_run": args.run_id,
        "as_of_policy": args.as_of_policy,
        "jurisdiction": args.jurisdiction,
        "generated_utc": report["generated_utc"],
        "statutes_sha256": report["statutes_sha256"],
        "links_sha256": report["links_sha256"],
        "source_tree_hash": hash_after,
        "source_run_untouched": untouched,
        "dataset_sha256": sha256_file(dataset_path),
    }
    (out / "meta.json").write_text(json.dumps(meta, indent=2) + "\n",
                                     encoding="utf-8", newline="\n")

    print(f"detected {len(records)} items -> {out}")
    print(f"  as_of policy: {args.as_of_policy}"
          + (f" (era dates {dict(era.slices)})"
             if args.as_of_policy == "era" else
             f" (fixed {args.fixed_as_of})"))
    print(f"  fires {fire_counts['fires']}   silent {fire_counts['silent']}"
          f"   fire rate {report['fire_rate']:.3f}"
          if records else "  (no items)")
    print(f"  flags: {dict(flag_counts)}")
    print(f"  CM defined on {cm_defined}/{len(records)} items "
          f"(undefined = an unresolvable factor, never a zero)")
    print(f"  contradiction source: {dict(ksrc_counts)}")
    print(f"  source run tree hash: {hash_before} -> {hash_after}")
    if untouched:
        print("  SOURCE RUN UNCHANGED (hard rule H2 satisfied)")
        return 0
    print("  ERROR: SOURCE RUN CHANGED -- investigate before trusting "
          "anything in this report")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
