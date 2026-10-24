#!/usr/bin/env python3
"""44 - Phase G limited pilot: approval-gated, cost-capped, 240 requests.

Two modes, and the second one refuses to run without the first one's hash.

    # 1) plan: offline, free, prints what would be sent and what it would cost
    python scripts/44_phase_g_pilot.py --plan

    # 2) run: only after the plan has been reviewed and approved verbatim
    python scripts/44_phase_g_pilot.py --run --approve <plan_sha256>

The runner refuses to start when any of these is true:

* the approval hash does not match the current plan;
* the provider, model, request configuration, item list or request count has
  drifted from the stored plan;
* the estimated maximum cost exceeds the cap in the config (default $0.50);
* the API key environment variable is unset;
* the endpoint does not list the requested model id;
* the target run directory already exists;
* a frozen dataset differs from its recorded digest.

Generation is the only paid step and it happens nowhere else. The analysis that
follows is offline, and it applies the outcome rules that were registered in the
plan *before* any request was sent.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from jurisuq import pilot
from jurisuq.cluster import make_clusterer
from jurisuq.generators import PROMPT_VERSION, OpenAICompatGenerator
from jurisuq.judge import UNRESOLVED_LABELS, make_judge
from jurisuq.pilot import (COST_CAP_USD, build_plan, build_smoke_plan, classify_slice,
                           enforce_cost_cap, ensure_fresh_run_dir, estimate_cost,
                           g7_from_pilot, redact_secret, require_approval, select_items,
                           selection_summary, verify_frozen_inputs, verify_no_drift)

DEFAULT_CONFIG = ROOT / "configs" / "phase_g_pilot.json"
PLAN_PATH = ROOT / "runs" / "phaseG_pilot_plan.json"


def _load_config(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_items() -> list[dict]:
    path = ROOT / "data" / "lexuq_slice.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def _prompt_tokens(items: list[dict]) -> tuple[int, int]:
    """Upper-bound prompt tokens per request: max over the selected items.

    ``len(text) / 4`` is the standard rough ratio and errs high for English
    prose, which is the right direction for a cost ceiling. The measured value
    is replaced by the provider's own ``usage.prompt_tokens`` after the run.
    """
    system_len = len(OpenAICompatGenerator.SYSTEM)
    per_item = [(system_len + len(item["question"]) + 3) // 4 for item in items]
    return max(per_item), sum(per_item) // len(per_item)


def _rates(config: dict, model: str) -> dict:
    candidates = config["pricing"]["candidates"]
    if model not in candidates:
        raise SystemExit(f"ERROR: no pricing recorded for model {model!r}; "
                         f"known models: {sorted(candidates)}")
    entry = candidates[model]
    # The peak rate is used, because an estimate that can be undercut by the
    # clock is not a maximum.
    return entry["peak"]


def _plan(config: dict, items: list[dict]) -> dict:
    gen = config["generator"]
    chosen = select_items(items, per_slice=int(config["items_per_slice"]),
                          seed=int(config["seed"]))
    selection = selection_summary(chosen)
    max_prompt, mean_prompt = _prompt_tokens(chosen)
    rates = _rates(config, gen["model"])
    pricing = {
        "rates_used": rates,
        "rate_basis": "peak (the higher of the provider's published rates)",
        "retrieved_utc": config["pricing"]["retrieved_utc"],
        "source_urls": config["pricing"]["source_urls"],
        "currency": "USD",
        "unit": "per 1M tokens",
    }
    plan = build_plan(
        provider=gen["provider"],
        base_url=gen["base_url"],
        model=gen["model"],
        temperature=float(gen["temperature"]),
        top_p=float(gen["top_p"]),
        max_tokens=int(gen["max_tokens"]),
        n_samples=int(gen["n_samples"]),
        seed=int(config["seed"]),
        prompt_version=PROMPT_VERSION,
        judge=config["judge"],
        judge_scope=config["judge_scope"],
        selection=selection,
        pricing=pricing,
        rates=rates,
        prompt_tokens_per_request=max_prompt,
        run_id=config["run_id"],
        dataset_sha256=dict(pilot.FROZEN_DATASET_SHA256),
    )
    plan["prompt_token_estimate"] = {
        "max_per_request": max_prompt,
        "mean_per_request": mean_prompt,
        "method": "ceil(len(system_prompt + question) / 4), max taken for the ceiling",
    }
    plan["privacy"] = config["privacy"]
    plan["cost_cap_usd"] = float(config.get("cost_cap_usd", COST_CAP_USD))
    plan["plan_sha256"] = pilot.plan_digest(plan)
    return plan


def _print_plan(plan: dict) -> None:
    cfg = plan["request_configuration"]
    cost = plan["cost_estimate"]
    sel = plan["selection"]
    print("=" * 84)
    print("PHASE G LIMITED PILOT — PLAN (nothing has been sent)")
    print("=" * 84)
    print(f"  run id        : {plan['run_id']}  (new directory; existing runs untouched)")
    print(f"  provider      : {plan['provider']}  via OpenAI-compatible /v1/chat/completions")
    print(f"  base url      : {plan['base_url']}")
    print(f"  model id      : {plan['model']}")
    print(f"  temperature   : {cfg['temperature']}   top_p: {cfg['top_p']}   "
          f"max_tokens: {cfg['max_tokens']}")
    print(f"  samples/item  : {cfg['n_samples']} (M)   seed: {cfg['seed']}")
    print(f"  prompt        : {cfg['prompt_version']}   logprobs requested: {cfg['logprobs_requested']}")
    print(f"  judge         : {plan['judge']['method']} (scope {plan['judge']['scope']}, "
          f"deterministic={plan['judge']['deterministic']})")
    print()
    print(f"  items         : {sel['n_items']}  {sel['by_slice']}")
    print(f"  requests      : {plan['n_requests']}  = {sel['n_items']} items x {cfg['n_samples']} samples")
    print(f"  prompt tokens : {plan['prompt_token_estimate']['max_per_request']} max, "
          f"{plan['prompt_token_estimate']['mean_per_request']} mean per request")
    print()
    print("  cost (upper bound)")
    print(f"    rates       : in ${cost.get('input_per_mtok', '')}"
          f"{plan['pricing']['rates_used']['input_per_mtok']}/M, "
          f"out ${plan['pricing']['rates_used']['output_per_mtok']}/M "
          f"({plan['pricing']['rate_basis']})")
    print(f"    input       : {cost['prompt_tokens']:,} tokens -> ${cost['input_cost_usd']:.6f}")
    print(f"    output      : {cost['completion_tokens']:,} tokens (max_tokens every time) "
          f"-> ${cost['output_cost_usd']:.6f}")
    print(f"    TOTAL MAX   : ${cost['total_cost_usd']:.6f}   cap ${plan['cost_cap_usd']:.2f}"
          f"   headroom ${plan['cost_cap_usd'] - cost['total_cost_usd']:.6f}")
    print()
    print("  data handling")
    print(f"    sent        : {plan['privacy']['what_is_sent']}")
    print(f"    not sent    : {'; '.join(plan['privacy']['what_is_not_sent'][:2])}")
    print(f"    retention   : {plan['privacy']['provider_retention']}")
    print()
    print("  pre-registered outcome rules")
    rules = plan["outcome_rules"]
    print(f"    L7 zero correct   -> G7 {rules['on_zero_correct_in_L7']['g7']}, "
          f"ranking {rules['on_zero_correct_in_L7']['ranking']}")
    print(f"    L7 all correct    -> G7 {rules['on_all_correct_in_L7']['g7']}, "
          f"ranking {rules['on_all_correct_in_L7']['ranking']}")
    print(f"    L7 both classes   -> G7 {rules['on_both_classes_in_L7']['g7']}")
    print(f"    sparse class      -> {rules['on_sparse_class']['action']} "
          f"(< {rules['on_sparse_class']['threshold_items']} items)")
    print(f"    slices            : {rules['slices']}")
    print()
    smoke = build_smoke_plan(plan)
    print("  smoke check (2 requests, recommended before the 240)")
    print(f"    compares    : {smoke['item_ids']}  ({smoke['n_requests']} requests, "
          f"max ${smoke['cost_estimate']['total_cost_usd']:.6f})")
    print(f"    learns      : {smoke['purpose']}")
    print(f"    SMOKE SHA256: {smoke['plan_sha256']}")
    print()
    print(f"  PLAN SHA256: {plan['plan_sha256']}")
    print()
    print("  Approve verbatim with, in this order:")
    print(f"    python scripts/44_phase_g_pilot.py --smoke --approve {smoke['plan_sha256']}")
    print(f"    python scripts/44_phase_g_pilot.py --run --approve {plan['plan_sha256']}")


# ----------------------------------------------------------------------
# the smoke check: two requests, and it reports what the provider really did
# ----------------------------------------------------------------------
def _smoke(plan: dict, config: dict, args) -> int:
    """Send one request per slice and inspect the raw response.

    Deliberately bypasses the generator's abstraction: the questions worth
    answering here are about the wire format (is there a ``reasoning_content``
    field, are there ``logprobs``, does ``usage`` report reasoning tokens), and
    the abstraction discards exactly those fields.
    """
    import requests

    smoke = build_smoke_plan(plan)
    require_approval(smoke, args.approve, mode="--smoke")
    enforce_cost_cap(smoke["cost_estimate"], plan["cost_cap_usd"])

    gen_cfg = config["generator"]
    api_key = os.environ.get(gen_cfg["api_key_env"], "").strip()
    if not api_key:
        raise SystemExit(f"ERROR: {gen_cfg['api_key_env']} is not set.")

    probe = pilot.fetch_models(smoke["base_url"], api_key)
    if not probe["reachable"]:
        raise SystemExit(f"ERROR: cannot reach {smoke['base_url']}/models: "
                         f"{redact_secret(str(probe['error']), api_key)}")

    run_dir = ensure_fresh_run_dir(ROOT / "runs" / smoke["run_id"])
    run_dir.mkdir(parents=True, exist_ok=True)

    by_id = {i["item_id"]: i for i in _load_items()}
    cfg = smoke["request_configuration"]
    results = []
    print(f"smoke: {smoke['n_requests']} requests against {smoke['base_url']}")
    print("-" * 70)
    for item_id in smoke["item_ids"]:
        item = by_id[item_id]
        payload = {
            "model": smoke["model"],
            "messages": [{"role": "system", "content": OpenAICompatGenerator.SYSTEM},
                         {"role": "user", "content": item["question"]}],
            "temperature": cfg["temperature"],
            "top_p": cfg["top_p"],
            "max_tokens": cfg["max_tokens"],
            "stream": False,
            "logprobs": True,
            "top_logprobs": 1,
        }
        t0 = time.time()
        response = requests.post(f"{smoke['base_url'].rstrip('/')}/chat/completions",
                                 json=payload, timeout=120,
                                 headers={"Authorization": f"Bearer {api_key}",
                                          "Content-Type": "application/json"})
        elapsed = time.time() - t0
        entry = {"item_id": item_id, "slice": item["slice"],
                 "http_status": response.status_code, "latency_s": round(elapsed, 2)}
        if response.status_code != 200:
            entry["error"] = redact_secret(response.text[:400], api_key)
            results.append(entry)
            print(f"  {item_id}: HTTP {response.status_code}  {entry['error'][:100]}")
            continue

        data = response.json()
        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        usage = data.get("usage") or {}
        logprob_field = (choice.get("logprobs") or {}).get("content")
        entry.update({
            "served_model": data.get("model"),
            "finish_reason": choice.get("finish_reason"),
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "reasoning_tokens": (usage.get("completion_tokens_details") or {}).get("reasoning_tokens"),
            "has_reasoning_content": bool(message.get("reasoning_content")),
            "logprobs_returned": bool(logprob_field),
            "answer_preview": (message.get("content") or "")[:160],
        })
        results.append(entry)
        print(f"  {item_id}: {entry['prompt_tokens']} in / {entry['completion_tokens']} out, "
              f"finish={entry['finish_reason']}, reasoning={entry['reasoning_tokens']}, "
              f"logprobs={entry['logprobs_returned']}")

    thinking = any(r.get("has_reasoning_content") or (r.get("reasoning_tokens") or 0) > 0
                   for r in results)
    logprobs = all(r.get("logprobs_returned") for r in results if "error" not in r)         if any("error" not in r for r in results) else None
    truncated = any(r.get("finish_reason") == "length" for r in results)
    observed_prompt = max([r["prompt_tokens"] for r in results
                           if isinstance(r.get("prompt_tokens"), int)] or [0])
    findings = {
        "thinking_mode_active": thinking,
        "logprobs_returned": logprobs,
        "output_truncated_at_max_tokens": truncated,
        "served_model_ids": sorted({r.get("served_model") for r in results if r.get("served_model")}),
        "observed_prompt_tokens_max": observed_prompt,
        "planned_prompt_token_ceiling": plan["prompt_token_estimate"]["max_per_request"],
        "prompt_estimate_held": (observed_prompt <= plan["prompt_token_estimate"]["max_per_request"]
                                 if observed_prompt else None),
    }
    findings["implications"] = {
        "p_true": ("logprobs available; the p_true column can be computed"
                   if logprobs else
                   "no logprobs returned: p_true stays undefined with reason logprobs_absent"),
        "cost": ("reasoning tokens appear, so completions may be longer than the pilot "
                 "assumes and the cost ceiling should be re-checked"
                 if thinking else "no reasoning tokens observed"),
        "answers": ("some completion hit max_tokens and was cut off; the answer may be "
                    "truncated, which depresses accuracy for a reason unrelated to the model"
                    if truncated else "no completion was truncated"),
    }

    actual = estimate_cost(
        sum(r.get("prompt_tokens") or 0 for r in results),
        sum(r.get("completion_tokens") or 0 for r in results),
        plan["pricing"]["rates_used"])

    report = {
        "phase": "G",
        "report": "smoke check",
        "run_id": smoke["run_id"],
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "plan_sha256": smoke["plan_sha256"],
        "parent_plan_sha256": smoke["parent_plan_sha256"],
        "provider": smoke["provider"],
        "base_url": smoke["base_url"],
        "model": smoke["model"],
        "request_configuration": smoke["request_configuration"],
        "endpoint_models_visible": probe["model_ids"][:25],
        "results": results,
        "findings": findings,
        "cost": {"actual": actual,
                 "estimated_max": smoke["cost_estimate"]["total_cost_usd"]},
        "note": ("a smoke check measures the provider's behaviour, not the model's "
                 "accuracy; no correctness or gate claim follows from it"),
    }
    (run_dir / "smoke_report.json").write_text(json.dumps(report, indent=2) + "\n",
                                               encoding="utf-8")

    print("-" * 70)
    print(f"  thinking mode : {'ACTIVE' if thinking else 'not observed'}")
    print(f"  logprobs      : {'returned' if logprobs else 'NOT returned'}")
    print(f"  truncation    : {'some answers hit max_tokens' if truncated else 'none'}")
    print(f"  served model  : {findings['served_model_ids']}")
    print(f"  prompt tokens : observed max {observed_prompt}, "
          f"planned ceiling {plan['prompt_token_estimate']['max_per_request']}  "
          f"({'held' if findings['prompt_estimate_held'] else 'EXCEEDED'})")
    print(f"  cost          : ${actual['total_cost_usd']:.6f} actual "
          f"(max ${smoke['cost_estimate']['total_cost_usd']:.6f} authorised)")
    for key, text in findings["implications"].items():
        print(f"  {key:<13} : {text}")
    print(f"\n  report: {run_dir / 'smoke_report.json'}")
    print("  The main run is still gated: --run --approve " + plan["plan_sha256"])
    return 0


# ----------------------------------------------------------------------
# the paid path
# ----------------------------------------------------------------------
def _run(plan: dict, config: dict, args) -> int:
    approved_path = Path(args.approved_plan) if args.approved_plan else PLAN_PATH
    if not approved_path.is_file():
        raise SystemExit(f"ERROR: no stored plan at {approved_path}; run --plan first")
    approved = json.loads(approved_path.read_text(encoding="utf-8"))
    verify_no_drift(plan, approved)

    enforce_cost_cap(plan["cost_estimate"], plan["cost_cap_usd"])

    gen_cfg = config["generator"]
    api_key = os.environ.get(gen_cfg["api_key_env"], "").strip()
    if not api_key:
        raise SystemExit(
            f"ERROR: {gen_cfg['api_key_env']} is not set. Export it in the shell that runs "
            "the pilot; do not put it in a config file, a command line or this repository.")

    probe = pilot.fetch_models(plan["base_url"], api_key)
    if not probe["reachable"]:
        raise SystemExit(f"ERROR: cannot reach {plan['base_url']}/models: "
                         f"{redact_secret(str(probe['error']), api_key)}")
    if plan["model"] not in probe["model_ids"]:
        raise SystemExit(f"ERROR: {plan['model']!r} is not served by this endpoint. "
                         f"Available: {probe['model_ids']}")

    run_dir = ensure_fresh_run_dir(ROOT / "runs" / plan["run_id"])
    run_dir.mkdir(parents=True, exist_ok=True)
    items = _load_items()
    chosen = [i for i in items if i["item_id"] in set(plan["selection"]["item_ids"])]

    from jurisuq.config import Config
    cfg = Config()
    cfg.provider = "openai"
    cfg.base_url = plan["base_url"]
    cfg.model = plan["model"]
    cfg.api_key = api_key
    cfg.temperature = plan["request_configuration"]["temperature"]
    cfg.top_p = plan["request_configuration"]["top_p"]
    cfg.max_tokens = plan["request_configuration"]["max_tokens"]
    cfg.n_samples = plan["request_configuration"]["n_samples"]
    cfg.seed = plan["request_configuration"]["seed"]
    cfg.judge = plan["judge"]["method"]
    cfg.judge_scope = plan["judge"]["scope"]
    cfg.run_id = plan["run_id"]
    cfg.slices = ["L1", "L7"]

    gen = OpenAICompatGenerator(cfg)
    judge = make_judge(cfg, gen)
    discrete, entail, backend = make_clusterer(cfg)

    from jurisuq.pipeline import build_record

    meta = {
        "run_id": plan["run_id"],
        "phase": "G",
        "kind": "limited approval-gated pilot",
        "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "provider": gen.name,
        "base_url": plan["base_url"],
        "model": plan["model"],
        "n_samples": cfg.n_samples,
        "temperature": cfg.temperature,
        "top_p": cfg.top_p,
        "max_tokens": cfg.max_tokens,
        "seed": cfg.seed,
        "prompt_version": PROMPT_VERSION,
        "system_prompt": OpenAICompatGenerator.SYSTEM,
        "judge": judge.method,
        "judge_scope": cfg.judge_scope,
        "nli_backend": backend,
        "plan_sha256": plan["plan_sha256"],
        "dataset_sha256": plan["dataset_sha256"],
        "approved_plan_file": str(approved_path.relative_to(ROOT)),
        "config": {k: v for k, v in cfg.__dict__.items() if k != "api_key"},
        "pricing": plan["pricing"],
        "outcome_rules": plan["outcome_rules"],
        "api_key_env": gen_cfg["api_key_env"],
    }
    (run_dir / "meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")

    print(f"run      : {run_dir}")
    print(f"generator: {gen.name}")
    print(f"items    : {len(chosen)}   requests: {len(chosen) * cfg.n_samples}")
    print("-" * 70)

    records, usage = [], {"prompt_tokens": 0, "completion_tokens": 0, "requests": 0}
    t0 = time.time()
    with (run_dir / "items.jsonl").open("a", encoding="utf-8") as fh:
        for index, item in enumerate(chosen, start=1):
            try:
                samples = gen.sample(item["question"], cfg.n_samples,
                                     meta={"slice": item["slice"],
                                           "template": item["template"],
                                           "gold_act": item["gold_act"],
                                           "gold_provision": item["gold_provision"]})
            except Exception as exc:
                record = {"item_id": item["item_id"], "slice": item["slice"],
                          "error": redact_secret(repr(exc), api_key)}
                fh.write(json.dumps(record) + "\n")
                fh.flush()
                print(f"  [{index}/{len(chosen)}] ERROR {item['item_id']}: {record['error'][:80]}")
                continue

            record = build_record(item, [s.text for s in samples], cfg, judge,
                                  (discrete, entail),
                                  n_tokens=[s.n_tokens for s in samples],
                                  logprobs=[s.mean_logprob for s in samples])
            record["gen_latency_s"] = sum(s.latency_s for s in samples)
            record["usage"] = {
                "prompt_tokens": sum(s.prompt_tokens for s in samples),
                "completion_tokens": sum(s.n_tokens for s in samples),
            }
            for key in ("prompt_tokens", "completion_tokens"):
                usage[key] += record["usage"][key]
            usage["requests"] += len(samples)

            fh.write(json.dumps(record, default=str) + "\n")
            fh.flush()
            records.append(record)
            if index % 4 == 0 or index == len(chosen):
                print(f"  [{index}/{len(chosen)}] {item['slice']} {item['item_id']} "
                      f"elapsed {time.time() - t0:5.0f}s")

    meta["finished_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    meta["elapsed_s"] = round(time.time() - t0, 1)
    meta["usage"] = usage
    (run_dir / "meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")

    return _report(plan, config, run_dir, records, usage)


def _report(plan: dict, config: dict, run_dir: Path, records: list[dict], usage: dict) -> int:
    """Apply the pre-registered outcome rules and write the pilot report."""
    per_slice = {}
    for slice_name in ("L1", "L7"):
        subset = [r for r in records if r.get("slice") == slice_name and "error" not in r]
        counts = {"correct": 0, "incorrect": 0, "unresolved": 0}
        samples_total = samples_resolved = 0
        for record in subset:
            value = record.get("majority_correct")
            if value == 1:
                counts["correct"] += 1
            elif value == 0:
                counts["incorrect"] += 1
            else:
                counts["unresolved"] += 1
            labels = record.get("sample_verdict_labels") or []
            samples_total += len(labels)
            samples_resolved += sum(1 for label in labels if label not in UNRESOLVED_LABELS)
        n_items = len(subset)
        block = classify_slice(counts)
        block["n_items"] = n_items
        block["errors"] = sum(1 for r in records
                              if r.get("slice") == slice_name and "error" in r)
        block["judge_coverage"] = {
            "item_level": (counts["correct"] + counts["incorrect"]) / n_items if n_items else None,
            "sample_level": samples_resolved / samples_total if samples_total else None,
            "n_samples": samples_total,
            "n_samples_resolved": samples_resolved,
        }
        per_slice[slice_name] = block

    g7 = g7_from_pilot(per_slice)

    rates = plan["pricing"]["rates_used"]
    actual = estimate_cost(usage["prompt_tokens"], usage["completion_tokens"], rates)
    actual.update({"requests": usage["requests"],
                   "estimated_max_cost_usd": plan["cost_estimate"]["total_cost_usd"],
                   "under_estimate": actual["total_cost_usd"] <= plan["cost_estimate"]["total_cost_usd"]})
    if usage["prompt_tokens"] == 0:
        actual["token_note"] = ("the provider reported no usage for these requests, so these "
                                "cost figures are zero, not free; report them as unmeasured")

    report = {
        "phase": "G",
        "report": "limited pilot",
        "run_id": plan["run_id"],
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "plan_sha256": plan["plan_sha256"],
        "provider": plan["provider"],
        "model": plan["model"],
        "request_configuration": plan["request_configuration"],
        "n_items": len(records),
        "n_requests": usage["requests"],
        "per_slice": per_slice,
        "g7": g7,
        "cost": {"rates": rates, "actual": actual},
        "outcome_rules_applied": plan["outcome_rules"],
        "invariants_held": plan["invariants"],
        "note": ("a pilot of this size cannot settle G7 or rank methods; it measures "
                 "whether the target slice can carry both classes at all"),
    }
    (run_dir / "pilot_report.json").write_text(json.dumps(report, indent=2) + "\n",
                                               encoding="utf-8")

    print("=" * 84)
    print("PILOT RESULT — pre-registered rules applied")
    print("=" * 84)
    for slice_name in ("L1", "L7"):
        block = per_slice[slice_name]
        counts = block["counts"]
        coverage = block["judge_coverage"]
        item_cov = "undefined" if coverage["item_level"] is None else f"{coverage['item_level']:.4f}"
        sample_cov = ("undefined" if coverage["sample_level"] is None
                      else f"{coverage['sample_level']:.4f}")
        print(f"  {slice_name}: n={block['n_items']} correct={counts['correct']} "
              f"incorrect={counts['incorrect']} unresolved={counts['unresolved']}")
        print(f"      judge coverage  item={item_cov}  sample={sample_cov} "
              f"({coverage['n_samples_resolved']}/{coverage['n_samples']} samples)")
        print(f"      state           {block['state']}  -> {block['interpretation']}")
    print()
    print(f"  G7: {g7['status']} (provisional, not final)")
    print(f"      {g7['reason']}")
    print()
    print(f"  cost: ${actual['total_cost_usd']:.6f} actual "
          f"(max ${plan['cost_estimate']['total_cost_usd']:.6f} authorised)")
    print(f"        {actual['prompt_tokens']:,} in / {actual['completion_tokens']:,} out "
          f"over {actual['requests']} requests")
    print(f"\n  report: {run_dir / 'pilot_report.json'}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=str(DEFAULT_CONFIG))
    ap.add_argument("--plan", action="store_true", help="print the plan; sends nothing")
    ap.add_argument("--smoke", action="store_true",
                    help="send 2 requests to check thinking mode and logprobs")
    ap.add_argument("--run", action="store_true", help="execute the approved plan")
    ap.add_argument("--approve", default=None, help="the plan_sha256 the user approved")
    ap.add_argument("--approved-plan", default=None,
                    help="path to the stored plan that was approved")
    ap.add_argument("--out", default=str(PLAN_PATH))
    args = ap.parse_args()

    if not args.plan and not args.run and not args.smoke:
        ap.error("choose --plan (free), --smoke (2 paid requests) or --run "
                 "(240 paid requests, needs --approve)")

    config = _load_config(Path(args.config))
    verify_frozen_inputs()
    plan = _plan(config, _load_items())

    if args.plan:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
        _print_plan(plan)
        print(f"\n  plan file: {out}")
        print("  Nothing was sent. Generation requires --run --approve <sha256>.")
        return 0

    if args.smoke:
        return _smoke(plan, config, args)

    require_approval(plan, args.approve)
    return _run(plan, config, args)


if __name__ == "__main__":
    raise SystemExit(main())
