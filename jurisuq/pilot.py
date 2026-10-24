"""Phase G pilot safeguards: planning, cost estimation, and pre-registration.

The pilot is the first time this project spends money on a hosted model, so the
rules that make it safe are code, not intentions:

* the plan is a frozen record with a hash, and execution requires that hash;
* the provider, model and request configuration must match the approved plan
  exactly - any drift refuses to run;
* the estimated **maximum** cost is computed from the provider's published
  rates before any request, and a plan over the cap refuses to run;
* the outcome rules are registered *before* generation, so the verdict cannot
  be chosen after seeing results;
* nothing here touches the frozen Phase A-F artefacts.

Everything in this module is offline and pure; the network call lives in the
scripts that use it.
"""
from __future__ import annotations

import hashlib
import json
import random
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: Frozen dataset digests. The pilot must never alter the data it reads.
FROZEN_DATASET_SHA256 = {
    "data/lexuq_slice.jsonl":
        "89bc1180a4df76287768ce59432aa7ff0aa9d38c16d5f296ed16c3e45449bd53",
    "data/lexuq_slice_summary.json":
        "0bd5186d767714b2f0f23d76eddbecb28c0b3ebd0edbe26c3617d914c9e37a84",
}

#: Hard spending cap for the pilot, in US dollars. A plan above this refuses.
COST_CAP_USD = 0.50

#: The pilot's fixed shape: 12 items per slice, M=10, so 240 requests.
ITEMS_PER_SLICE = 12
SAMPLES_PER_ITEM = 10

#: The smoke check: one request on one item per slice, to learn what the
#: provider actually does (thinking tokens, logprobs, served model id) before
#: spending on the full pilot. Two requests, two items, one slice each.
SMOKE_ITEMS = ("L1", "L7")


def build_smoke_plan(plan: dict) -> dict:
    """A two-request pre-flight derived from the approved pilot plan.

    It inherits every setting from the main plan so the smoke check measures the
    configuration that will actually run, and it carries its own hash because it
    is its own spending decision.
    """
    per_slice = {}
    for item_id in plan["selection"]["item_ids"]:
        slice_name = item_id.split("-", 1)[0]
        if slice_name in SMOKE_ITEMS and slice_name not in per_slice:
            per_slice[slice_name] = item_id
    missing = [s for s in SMOKE_ITEMS if s not in per_slice]
    if missing:
        raise ValueError(f"the pilot selection has no item for slice(s) {missing}")

    smoke = {
        "phase": "G",
        "kind": "smoke check (2 requests)",
        "run_id": plan["run_id"] + "-smoke",
        "provider": plan["provider"],
        "base_url": plan["base_url"],
        "model": plan["model"],
        "request_configuration": dict(plan["request_configuration"]),
        "n_requests": len(SMOKE_ITEMS),
        "item_ids": [per_slice[s] for s in SMOKE_ITEMS],
        "purpose": ("confirm the served model id, whether thinking tokens appear, "
                    "whether logprobs are returned, and the real prompt-token count"),
        "parent_plan_sha256": plan["plan_sha256"],
        "cost_estimate": estimate_plan_cost(
            len(SMOKE_ITEMS),
            plan["prompt_token_estimate"]["max_per_request"],
            plan["request_configuration"]["max_tokens"],
            plan["pricing"]["rates_used"]),
    }
    smoke["plan_sha256"] = plan_digest(smoke)
    return smoke

#: A correctness class with fewer than this many items is "sparse" and must be
#: reported as such rather than treated as a usable comparison class.
SPARSE_CLASS_BELOW = 5


def sha256_file(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_frozen_inputs(root: str | Path = ROOT) -> dict:
    """Confirm the slice is byte-identical to the frozen artefact."""
    root = Path(root)
    found, ok = {}, True
    for relative, expected in FROZEN_DATASET_SHA256.items():
        actual = sha256_file(root / relative)
        found[relative] = {"expected": expected, "actual": actual,
                           "match": actual == expected}
        ok = ok and actual == expected
    if not ok:
        raise SystemExit("ERROR: a frozen dataset differs from its recorded digest; "
                         "refusing to run the pilot until that is explained")
    return found


# ----------------------------------------------------------------------
# cost
# ----------------------------------------------------------------------
def estimate_cost(prompt_tokens: int, completion_tokens: int, rates: dict) -> dict:
    """Cost in USD from per-million-token rates.

    ``rates`` carries ``input_per_mtok`` and ``output_per_mtok``. The estimate is
    deliberately a **maximum**: the prompt is measured, the completion assumes
    every request reaches ``max_tokens``.
    """
    for key in ("input_per_mtok", "output_per_mtok"):
        if key not in rates:
            raise ValueError(f"pricing is missing {key}")
        if rates[key] < 0:
            raise ValueError(f"{key} must not be negative")
    input_cost = prompt_tokens / 1_000_000 * rates["input_per_mtok"]
    output_cost = completion_tokens / 1_000_000 * rates["output_per_mtok"]
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "input_cost_usd": round(input_cost, 6),
        "output_cost_usd": round(output_cost, 6),
        "total_cost_usd": round(input_cost + output_cost, 6),
    }


def estimate_plan_cost(n_requests: int, prompt_tokens_per_request: int,
                       max_tokens_per_request: int, rates: dict) -> dict:
    if n_requests <= 0:
        raise ValueError("n_requests must be positive")
    estimate = estimate_cost(n_requests * prompt_tokens_per_request,
                             n_requests * max_tokens_per_request, rates)
    estimate.update({
        "n_requests": n_requests,
        "prompt_tokens_per_request": prompt_tokens_per_request,
        "max_tokens_per_request": max_tokens_per_request,
        "basis": ("upper bound: the measured prompt length for every request and "
                  "max_tokens for every completion"),
    })
    return estimate


def enforce_cost_cap(estimate: dict, cap_usd: float = COST_CAP_USD) -> dict:
    """Refuse a plan whose maximum cost exceeds the cap."""
    total = float(estimate["total_cost_usd"])
    verdict = {
        "estimated_max_cost_usd": total,
        "cap_usd": cap_usd,
        "within_cap": total <= cap_usd,
        "headroom_usd": round(cap_usd - total, 6),
    }
    if not verdict["within_cap"]:
        raise SystemExit(
            f"ERROR: estimated maximum cost ${total:.4f} exceeds the ${cap_usd:.2f} cap. "
            "Reduce the item count, lower max_tokens, or ask for a revised cap.")
    return verdict


# ----------------------------------------------------------------------
# item selection
# ----------------------------------------------------------------------
def select_items(items: list[dict], per_slice: int = ITEMS_PER_SLICE,
                 seed: int = 20261024) -> list[dict]:
    """Deterministically pick a topic-spread sample from each slice.

    Shuffling with a recorded seed and then sorting by item_id gives a sample
    that is reproducible from the seed alone, but the plan also records the
    exact item ids so the choice is auditable without re-running this code.
    """
    chosen: list[dict] = []
    for slice_name in ("L1", "L7"):
        pool = sorted((i for i in items if i.get("slice") == slice_name),
                      key=lambda i: i["item_id"])
        if len(pool) < per_slice:
            raise ValueError(f"slice {slice_name} has {len(pool)} items, "
                             f"cannot draw {per_slice}")
        rng = random.Random(seed + (0 if slice_name == "L1" else 1))
        picked = rng.sample(pool, per_slice)
        chosen.extend(sorted(picked, key=lambda i: i["item_id"]))
    chosen.sort(key=lambda i: (i["slice"], i["item_id"]))
    return chosen


def selection_summary(chosen: list[dict]) -> dict:
    topics: dict[str, list[str]] = {}
    for item in chosen:
        topics.setdefault(item["slice"], [])
        if item["topic"] not in topics[item["slice"]]:
            topics[item["slice"]].append(item["topic"])
    return {
        "n_items": len(chosen),
        "by_slice": {s: sum(1 for i in chosen if i["slice"] == s)
                     for s in sorted({i["slice"] for i in chosen})},
        "topics_by_slice": {s: sorted(v) for s, v in topics.items()},
        "item_ids": [i["item_id"] for i in chosen],
    }


# ----------------------------------------------------------------------
# the plan: one frozen record, one hash
# ----------------------------------------------------------------------
def build_plan(*, provider: str, base_url: str, model: str, temperature: float,
               top_p: float, max_tokens: int, n_samples: int, seed: int,
               prompt_version: str, judge: str, judge_scope: str,
               selection: dict, pricing: dict, rates: dict,
               prompt_tokens_per_request: int, run_id: str,
               dataset_sha256: dict) -> dict:
    """Assemble the complete, reviewable plan and hash its decision fields."""
    n_requests = selection["n_items"] * n_samples
    estimate = estimate_plan_cost(n_requests, prompt_tokens_per_request,
                                  max_tokens, rates)
    plan = {
        "phase": "G",
        "kind": "limited pilot (approval-gated)",
        "run_id": run_id,
        "provider": provider,
        "base_url": base_url,
        "model": model,
        "request_configuration": {
            "temperature": temperature,
            "top_p": top_p,
            "max_tokens": max_tokens,
            "n_samples": n_samples,
            "seed": seed,
            "prompt_version": prompt_version,
            "stream": False,
            "logprobs_requested": True,
        },
        "judge": {"method": judge, "scope": judge_scope,
                  "deterministic": judge == "provision",
                  "note": "rule-based provision judge; no model call, no judge cost"},
        "selection": selection,
        "n_requests": n_requests,
        "pricing": pricing,
        "cost_estimate": estimate,
        # recorded here so a plan is self-contained: the smoke check and any
        # reviewer downstream read these fields rather than recomputing them
        "prompt_token_estimate": {
            "max_per_request": prompt_tokens_per_request,
            "mean_per_request": prompt_tokens_per_request,
            "method": "supplied by the caller",
        },
        "cost_cap_usd": COST_CAP_USD,
        "dataset_sha256": dataset_sha256,
        "outcome_rules": outcome_rules(),
        "invariants": {
            "writes_new_run_only": True,
            "modifies_frozen_runs": False,
            "modifies_frozen_datasets": False,
            "changes_gate_constants": False,
            "changes_thresholds": False,
            "pools_slices": False,
        },
    }
    plan["plan_sha256"] = plan_digest(plan)
    return plan


def plan_digest(plan: dict) -> str:
    """Hash the fields that define what would actually be sent and paid for."""
    item_ids = (plan["selection"]["item_ids"] if "selection" in plan
                else plan.get("item_ids", []))
    decision = {
        "provider": plan["provider"],
        "base_url": plan["base_url"],
        "model": plan["model"],
        "request_configuration": plan["request_configuration"],
        "judge": plan.get("judge"),
        "selection_item_ids": item_ids,
        "n_requests": plan["n_requests"],
        "cost_estimate": plan["cost_estimate"],
        "dataset_sha256": plan.get("dataset_sha256"),
    }
    blob = json.dumps(decision, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(blob).hexdigest()


# ----------------------------------------------------------------------
# pre-registered outcome rules
# ----------------------------------------------------------------------
def outcome_rules() -> dict:
    """The rules, registered before generation.

    These are the user's Stage-1 constraints restated so the analysis step can
    be held to them mechanically.
    """
    return {
        "registered_before_generation": True,
        "on_zero_correct_in_L7": {
            "g7": "NOT_MET",
            "ranking": "undefined on L7",
            "wording": "report the zero, do not describe it as a comparator artefact",
        },
        "on_all_correct_in_L7": {
            "g7": "NOT_MET",
            "ranking": "undefined on L7",
            "wording": "report the absence of the incorrect class",
        },
        "on_both_classes_in_L7": {
            "g7": "not automatically met",
            "action": ("report the counts, the uncertainty and the interval; a sparse "
                       "class must be stated explicitly and no gate is claimed"),
        },
        "on_sparse_class": {
            "threshold_items": SPARSE_CLASS_BELOW,
            "action": "flag as sparse and refuse to present the AUROC as a ranking",
        },
        "slices": "L1 and L7 reported separately; pooled AUROC never presented as "
                  "detector or method performance",
        "gates_unchanged": ["G5 NOT_EVALUABLE", "G6 NOT_MET"],
    }


def classify_slice(counts: dict) -> dict:
    """Apply the pre-registered rules to one slice's correctness counts."""
    correct = int(counts.get("correct", 0))
    incorrect = int(counts.get("incorrect", 0))
    unresolved = int(counts.get("unresolved", 0))
    resolved = correct + incorrect
    minority = min(correct, incorrect)

    if resolved == 0:
        state = "no_resolved_items"
    elif correct == 0:
        state = "zero_correct"
    elif incorrect == 0:
        state = "all_correct"
    elif minority < SPARSE_CLASS_BELOW:
        state = "sparse_class"
    else:
        state = "both_classes"

    ranking_defined = state == "both_classes"
    return {
        "counts": {"correct": correct, "incorrect": incorrect,
                   "unresolved": unresolved, "resolved": resolved},
        "state": state,
        "ranking_defined": ranking_defined,
        "sparse_class": state == "sparse_class",
        "minority_class_size": minority,
        "interpretation": {
            "zero_correct": ("no correct answers in this slice: the ranking is undefined "
                             "and G7's condition is not satisfied here"),
            "all_correct": ("no incorrect answers in this slice: the ranking is undefined "
                            "and G7's condition is not satisfied here"),
            "sparse_class": (f"the minority class has {minority} items (below "
                             f"{SPARSE_CLASS_BELOW}); any AUROC is unstable and must not "
                             "be presented as a ranking"),
            "both_classes": "both classes present with a usable minority class",
            "no_resolved_items": "the judge resolved nothing; no metric is defined",
        }[state],
    }


def g7_from_pilot(per_slice: dict) -> dict:
    """G7 is met only if the *target* slice has both classes. Never automatic."""
    target = per_slice.get("L7", {})
    state = target.get("state")
    met = state == "both_classes"
    return {
        "gate": "G7",
        "status": "PROVISIONAL_MET" if met else "NOT_MET",
        "final": False,
        "reason": (f"L7 state is {state}: " + target.get("interpretation", "")) if target
                  else "L7 was not evaluated",
        "note": ("a 12-item pilot cannot settle a gate; even a PROVISIONAL_MET label "
                 "only means the condition is no longer structurally impossible, and "
                 "the larger evaluation would have to confirm it"),
        "unchanged": {"G5": "NOT_EVALUABLE", "G6": "NOT_MET"},
    }


# ----------------------------------------------------------------------
# approval
# ----------------------------------------------------------------------
def require_approval(plan: dict, approved_sha: str | None, mode: str = "--run") -> None:
    """Execution is gated on the hash of the plan the user actually approved."""
    if not approved_sha:
        raise SystemExit(
            "ERROR: this script spends money and will not run without approval.\n"
            "       1) python scripts/44_phase_g_pilot.py --plan\n"
            f"       2) review the plan, then re-run with: {mode} --approve "
            f"{plan.get('plan_sha256', '<plan-sha>')}\n"
            f"       The plan's current hash is {plan.get('plan_sha256')}.")
    if approved_sha.strip() != plan.get("plan_sha256"):
        raise SystemExit(
            "ERROR: the approval hash does not match this plan, so the approved "
            "configuration is not the one about to run.\n"
            f"       approved: {approved_sha}\n"
            f"       current : {plan.get('plan_sha256')}")


def ensure_fresh_run_dir(path) -> Path:
    """Refuse to write into a directory that already holds a run.

    A pilot run is never appended to or overwritten, because a partial re-run
    would silently mix two attempts in one report. This lives here rather than
    inline so the protection is unit-tested.
    """
    path = Path(path)
    if path.exists() and any(path.iterdir()):
        raise SystemExit(
            f"ERROR: {path} already exists and is not empty; a pilot run is never "
            "overwritten. Change run_id in the config and re-plan, or move the "
            "existing run aside deliberately.")
    return path


def verify_no_drift(plan: dict, approved: dict) -> None:
    """Compare a stored approved plan against the plan about to run."""
    for field in ("provider", "base_url", "model"):
        if plan[field] != approved.get(field):
            raise SystemExit(
                f"ERROR: {field} differs from the approved plan "
                f"({plan[field]!r} vs {approved.get(field)!r}); refusing to run.")
    if plan["request_configuration"] != approved.get("request_configuration"):
        raise SystemExit("ERROR: request configuration differs from the approved "
                         "plan; refusing to run.")
    if plan["selection"]["item_ids"] != approved["selection"]["item_ids"]:
        raise SystemExit("ERROR: the selected items differ from the approved plan; "
                         "refusing to run.")
    if plan["n_requests"] != approved["n_requests"]:
        raise SystemExit("ERROR: the request count differs from the approved plan; "
                         "refusing to run.")


# ----------------------------------------------------------------------
# pricing lookup against the provider (read-only, no key)
# ----------------------------------------------------------------------
def fetch_models(base_url: str, api_key: str | None = None, timeout: int = 15) -> dict:
    """List the provider's models. A read-only call; it generates nothing.

    Used to confirm the requested model id exists on the endpoint that will be
    billed, because a typo in a model name is the cheapest way to spend money on
    the wrong thing.
    """
    url = base_url.rstrip("/") + "/models"
    request = urllib.request.Request(url)
    if api_key:
        request.add_header("Authorization", f"Bearer {api_key}")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode())
        ids = [m.get("id") or m.get("name") for m in payload.get("data", [])
               if isinstance(m, dict)]
        return {"reachable": True, "model_ids": ids, "error": None}
    except Exception as exc:                      # network, auth, or DNS
        return {"reachable": False, "model_ids": [], "error": str(exc)}


def redact_secret(text: str, secret: str | None) -> str:
    """Never let a key reach a log file or a report."""
    if secret and secret in text:
        return text.replace(secret, "<redacted>")
    return text
