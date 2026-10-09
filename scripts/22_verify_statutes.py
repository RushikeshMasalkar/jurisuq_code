"""22_verify_statutes.py -- run the human verification pass on the statute table.

Every generated row carries ``verified: false`` until a human compares it
with the official text (India Code gazette + the Schedule to the Bharatiya
Nyaya Sanhita, 2023). This script is the workflow for that pass; the
generated JSONL itself is never hand-edited.

    # 1. export the checklist (one row per statute, editable columns)
    python scripts/22_verify_statutes.py --export

    # 2. open data/statutes/verification_checklist.csv next to the official
    #    texts; for each row set verified_ok to yes/no and fill
    #    official_source (e.g. "BNS Schedule, India Code vol. ...") / notes

    # 3. apply: rewrites the overrides file from the checklist
    python scripts/22_verify_statutes.py --apply

    # 4. rebuild the table (hash changes -- expected -- and the manifest
    #    reports the new verified share)
    python scripts/20_build_statutes.py --out data/statutes/statutes_v1.jsonl

Only ``verified_ok=yes`` rows become overrides; ``--apply`` rewrites the
whole overrides file from the checklist, so changing a yes back to no and
re-applying removes it. Overrides carry ``official_source`` and ``notes``
for provenance; only the ``verified`` flag is copied into the table rows
(the row schema is closed).
"""
from __future__ import annotations

import argparse
import csv
import datetime as _dt
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from jurisuq.context.table import build_rows  # noqa: E402

COLUMNS = ["key", "act", "section", "title", "offence_cluster",
           "consequence_class", "successor", "predecessor", "text_excerpt",
           "generated_verified", "verified_ok", "official_source", "notes"]

DEFAULT_CHECKLIST = "data/statutes/verification_checklist.csv"
DEFAULT_OVERRIDES = "data/statutes/statutes_v1.overrides.jsonl"


def _key(row: dict) -> str:
    return " ".join(f"{row['act']} {row['section']}".upper().split())


def export(checklist: pathlib.Path) -> int:
    rows = build_rows()
    checklist.parent.mkdir(parents=True, exist_ok=True)
    # newline="" + lineterminator="\n": csv's documented pattern, and
    # byte-identical on every platform
    with checklist.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({
                "key": _key(r), "act": r["act"], "section": r["section"],
                "title": r["title"], "offence_cluster": r["offence_cluster"],
                "consequence_class": r["consequence_class"],
                "successor": r["successor"] or "",
                "predecessor": r["predecessor"] or "",
                "text_excerpt": r["text_excerpt"],
                "generated_verified": r["verified"],
                "verified_ok": "", "official_source": "", "notes": "",
            })
    print(f"exported {len(rows)} rows -> {checklist}")
    print("  fill verified_ok (yes/no), official_source and notes, then run:")
    print("  python scripts/22_verify_statutes.py --apply")
    return 0


def apply_checklist(checklist: pathlib.Path, overrides: pathlib.Path) -> int:
    if not checklist.exists():
        print(f"ERROR: checklist not found: {checklist}")
        print("       run first: python scripts/22_verify_statutes.py --export")
        return 1
    valid_keys = {_key(r) for r in build_rows()}
    entries: list[dict] = []
    n_no = n_blank = 0
    with checklist.open(encoding="utf-8", newline="") as f:
        for i, row in enumerate(csv.DictReader(f), 2):
            key = " ".join(str(row.get("key", "")).upper().split())
            ok = str(row.get("verified_ok", "")).strip().lower()
            if key not in valid_keys:
                print(f"WARNING: line {i}: unknown key {key!r} (skipped)")
                continue
            if ok in ("yes", "y", "true"):
                entries.append({
                    "key": key, "verified": True,
                    "official_source": str(row.get("official_source", "")).strip(),
                    "notes": str(row.get("notes", "")).strip(),
                    "recorded_utc": _dt.datetime.now(
                        _dt.timezone.utc).isoformat(timespec="seconds"),
                })
            elif ok in ("no", "n", "false"):
                n_no += 1
            else:
                n_blank += 1
    if not entries:
        print("no rows marked verified_ok=yes; nothing to apply.")
        print(f"  (marked no: {n_no}, left blank: {n_blank})")
        return 0
    overrides.parent.mkdir(parents=True, exist_ok=True)
    payload = "".join(json.dumps(e, ensure_ascii=True) + "\n" for e in entries)
    overrides.write_text(payload, encoding="utf-8", newline="\n")
    print(f"applied {len(entries)} verified rows -> {overrides}")
    print(f"  (marked no: {n_no}, left blank: {n_blank}, total checked: "
          f"{len(entries) + n_no} of {len(valid_keys)})")
    print("  next: rebuild the table so the flags take effect:")
    print("  python scripts/20_build_statutes.py --out "
          "data/statutes/statutes_v1.jsonl")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--export", action="store_true",
                   help="write the editable verification checklist CSV")
    g.add_argument("--apply", action="store_true",
                   help="rewrite the overrides file from the checklist")
    ap.add_argument("--checklist", default=DEFAULT_CHECKLIST,
                    help=f"checklist CSV path (default: {DEFAULT_CHECKLIST})")
    ap.add_argument("--overrides", default=DEFAULT_OVERRIDES,
                    help=f"overrides JSONL path (default: {DEFAULT_OVERRIDES})")
    args = ap.parse_args()

    checklist = pathlib.Path(args.checklist)
    if not checklist.is_absolute():
        checklist = ROOT / checklist
    overrides = pathlib.Path(args.overrides)
    if not overrides.is_absolute():
        overrides = ROOT / overrides

    if args.export:
        return export(checklist)
    return apply_checklist(checklist, overrides)


if __name__ == "__main__":
    raise SystemExit(main())
