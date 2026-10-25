#!/usr/bin/env python3
"""41 - Phase G: screen a candidate target item set for answerable yield.

Phase G needs a target population in which the generator is *sometimes right*.
The frozen L7 slice yields zero correct answers (see scripts/40), so before any
long run this script measures, on a small sample, how often a candidate item set
produces a correct majority answer.

It does not decide a gate. It reports a rate with an interval and a projection
of how many items a full run would need, using the planning parameters handed to
it by ``configs/phase_g_target.json``.

Generation is opt-in. The default provider is ``mock`` so the harness can be
exercised end to end with no model; a real backend requires ``--allow-generation``
because it spends compute on the operator's machine.

    python scripts/41_screen_target_yield.py                       # mock, no model
    python scripts/41_screen_target_yield.py --data data/lexuq_target_candidates_v1.jsonl \
        --provider openai --allow-generation                       # ~20 min, laptop
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from jurisuq.cluster import make_clusterer
from jurisuq.config import add_common_args, config_from_args
from jurisuq.generators import make_generator
from jurisuq.judge import make_judge
from jurisuq.pipeline import build_record
from jurisuq.target import candidates as _candidates
from jurisuq.target import content_sha256, items_needed, yield_report
from jurisuq.uncertainty.io import write_json

#: The contract moved to ``jurisuq/target/candidates.py`` so the screen, the
#: tests and the documentation all cite one implementation. Re-exported here
#: because earlier callers (and the tests) import them from this module.
REQUIRED_ITEM_FIELDS = _candidates.REQUIRED_ITEM_FIELDS
ALLOWED_SLICES = _candidates.ALLOWED_SLICES


def load_candidates(path: Path) -> list[dict]:
    """Read and validate a candidate item file against the Stage 2 contract."""
    try:
        return _candidates.load_candidates(path)
    except _candidates.CandidateContractError as exc:
        raise SystemExit(str(exc)) from exc


def main() -> int:
    ap = add_common_args(argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter))
    ap.add_argument("--config-g", default=str(ROOT / "configs" / "phase_g_target.json"))
    ap.add_argument("--data", default=None, help="candidate item jsonl")
    ap.add_argument("--items", type=int, default=None, help="cap the number of items")
    ap.add_argument("--out", default=None)
    ap.add_argument("--allow-generation", action="store_true",
                    help="required when the provider is not 'mock'")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    cfg_g = json.loads(Path(args.config_g).read_text(encoding="utf-8"))
    screen_cfg = cfg_g.get("screen", {})
    data_path = Path(args.data or screen_cfg.get("data", ""))
    if not str(data_path):
        raise SystemExit("ERROR: no candidate file given (--data or config screen.data)")

    cfg = config_from_args(args)
    # An explicit --set n_samples=... wins; otherwise the target config decides.
    if not any(override.startswith("n_samples=") for override in args.overrides):
        cfg.n_samples = int(screen_cfg.get("samples", 10))

    if cfg.provider != "mock" and not args.allow_generation:
        raise SystemExit(
            "ERROR: this script calls a model when provider != 'mock'.\n"
            f"       provider is {cfg.provider!r}. Re-run with --allow-generation once "
            "the cost is approved, or use --set provider=mock for a plumbing check.")

    items = load_candidates(data_path)
    # `load_candidates` already validated this set. Re-running the pure check is
    # how the report obtains its summary; it must happen before the cap so a bad
    # item cannot be hidden by capping, and the summary describes the whole set.
    contract = _candidates.validate_candidates(items)
    data_sha256 = content_sha256(data_path)
    items = _limit(items, args.items if args.items is not None
                   else int(screen_cfg.get("items", len(items))))

    gen = make_generator(cfg)
    judge = make_judge(cfg, gen)
    discrete, entail, _backend = make_clusterer(cfg)
    clusterers = (discrete, entail)

    print("=" * 78)
    print("PHASE G SCREEN - is a candidate target item set answerable often enough?")
    print("=" * 78)
    print(f"generator : {gen.name}")
    print(f"judge     : {judge.method}")
    print(f"items     : {len(items)} ({dict(Counter(i['slice'] for i in items))})")
    print(f"samples   : {cfg.n_samples} per item   temperature: {cfg.temperature}")
    if cfg.provider == "mock":
        print("NOTE: the mock generator's numbers are a plumbing check only and must "
              "never be reported as a yield estimate.")
    print("-" * 78)

    started = time.time()
    records = []
    for index, item in enumerate(items, start=1):
        samples = gen.sample(item["question"], cfg.n_samples,
                             meta={"slice": item["slice"], "template": item.get("template"),
                                   "gold_act": item["gold"]["act"],
                                   "gold_provision": item["gold"]["provision"]})
        record = build_record(item, [s.text for s in samples], cfg, judge, clusterers,
                              n_tokens=[s.n_tokens for s in samples],
                              logprobs=[s.mean_logprob for s in samples])
        record["slice"] = item["slice"]
        record["topic"] = item.get("topic")
        records.append(record)
        print(f"[{index}/{len(items)}] {item['item_id']:34s} "
              f"majority={'correct' if record.get('majority_correct') == 1 else 'incorrect'}")

    elapsed = time.time() - started
    report = yield_report(records)
    # Per-slice yield, using the same function over the same records. G7's
    # condition is per slice ("both_classes_on_every_evaluated_slice"), so an
    # aggregate rate cannot tell a reader whether the L7 arm produced any correct
    # majority answer -- the single question the screen exists to answer. This
    # changes no metric; it reports the measurement already taken, grouped by the
    # slice field the candidate dataset already carries.
    yield_by_slice = {name: yield_report([record for record in records
                                          if record.get("slice") == name])
                      for name in sorted({record.get("slice") for record in records
                                          if record.get("slice")})}
    planning = cfg_g.get("yield_planning", {})
    needed = items_needed(float(report["overall"]["majority_rate"]),
                          int(planning.get("needed_correct", 15)),
                          confidence=float(planning.get("confidence", 0.95)))

    payload = {
        "phase": "G",
        "experiment": "candidate-yield screen",
        "generator": gen.name,
        "provider": cfg.provider,
        "is_mock": cfg.provider == "mock",
        "data_path": _relative(data_path),
        # Provenance: the exact bytes screened, and the contract they satisfy.
        # Without this a reported yield cannot be tied back to an item set.
        "data_sha256": data_sha256,
        "candidate_contract": contract,
        "n_items": len(items),
        "n_samples_per_item": cfg.n_samples,
        "elapsed_seconds": round(elapsed, 1),
        "seconds_per_item": round(elapsed / len(items), 2) if items else None,
        "yield": report,
        "yield_by_slice": yield_by_slice,
        "projection": needed,
        "projection_basis": planning.get("basis"),
        "verdict_note": ("This is a yield estimate, not a gate. A zero rate means no "
                         "two-class population can be built from this item set with this "
                         "generator; it does not license changing any Phase E/F constant."),
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    out = Path(args.out) if args.out else (
        ROOT / "runs" / f"phaseG_screen_{cfg.provider}_{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}.json")
    if not out.is_absolute():
        out = ROOT / out
    if out.exists() and not args.force:
        raise SystemExit(f"ERROR: {out} exists (pass --force)")
    write_json(out, payload)

    overall = report["overall"]
    print("-" * 78)
    print(f"  items                    : {overall['items']}")
    print(f"  correct majority answers : {overall['majority_correct']}")
    print(f"  majority rate            : {overall['majority_rate']:.4f} "
          f"95% CI [{overall['majority_interval']['lo']:.4f}, "
          f"{overall['majority_interval']['hi']:.4f}]")
    sample_rate = overall["sample_rate"]
    sample_text = "n/a" if sample_rate is None else f"{sample_rate:.4f}"
    print(f"  per-sample correct rate  : {sample_text}")
    print()
    print(f"  {'topic':26s} {'items':>6s} {'correct':>8s} {'rate':>7s}")
    for topic, block in sorted(report["topics"].items()):
        print(f"  {topic:26s} {block['items']:6d} {block['majority_correct']:8d} "
              f"{block['majority_rate']:7.3f}")
    print()
    if needed["reachable"]:
        print(f"  projection: {needed['items_for_confidence']} items for "
              f"{needed['needed_correct']} correct at {needed['confidence']:.0%} "
              f"confidence (expectation {needed['expected_items']})")
    else:
        print(f"  projection: not reachable from this item set - {needed.get('note')}")
    print()
    print(f"  {'slice':7s} {'items':>6s} {'correct':>8s} {'rate':>7s}")
    for name, block in yield_by_slice.items():
        overall_slice = block["overall"]
        print(f"  {name:7s} {overall_slice['items']:6d} "
              f"{overall_slice['majority_correct']:8d} "
              f"{overall_slice['majority_rate']:7.3f}")
    print(f"  report written: {out}")
    return 0 if overall["majority_correct"] > 0 else 1


def _limit(items: list[dict], count: int) -> list[dict]:
    if count <= 0:
        raise SystemExit("ERROR: --items must be positive")
    if count >= len(items):
        return items
    # Stratify by slice so a cap cannot silently empty one side of the screen.
    per_slice: dict[str, list[dict]] = {}
    for item in items:
        per_slice.setdefault(item["slice"], []).append(item)
    quota = max(1, count // max(1, len(per_slice)))
    chosen: list[dict] = []
    for slice_name in sorted(per_slice):
        chosen.extend(per_slice[slice_name][:quota])
    return chosen[:count]


def _relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


if __name__ == "__main__":
    raise SystemExit(main())
