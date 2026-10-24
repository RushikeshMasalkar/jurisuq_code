"""Phase F (M10): the decision layer - answer, verify or abstain.

The policy is a loss comparison, not a coverage target chosen for convenience
(master guide section 20.2). For a question with harm class ``h`` and calibrated
reliability ``p``:

    loss(answer)  = (1 - p) * h        # a wrong answer costs the stakes of the question
    loss(verify)  = c_verify           # verification effort does not scale with stakes
    loss(abstain) = c_abstain          # abstaining is a fallback, not a free action

with ``c_verify < c_abstain`` and both constant. The rule is

    answer  if (1 - p) * h <= c_verify
    verify  if (1 - p) * h <= c_abstain
    abstain otherwise

which makes the thresholds harm-dependent:

    p_answer(h)  = 1 - c_verify / h
    p_verify(h)  = 1 - c_abstain / h

A higher-stakes question therefore needs a higher reliability before the system
will answer it unassisted. If ``h <= c_abstain`` the corresponding threshold is
degenerate (the policy never abstains because abstaining costs more than the
worst case answer), and that is reported rather than clipped silently.

Labels are never an input: the policy sees only a calibrated probability, a harm
class, and the Phase D flags (which are themselves label-free).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .metrics import HARM_WEIGHTS, harm_weight

ACTIONS = ("answer", "verify", "abstain")

_FLAG_TEXT = {
    "stale_provision": "the asserted provision was not in force at the date the question asks about",
    "unresolvable_assertion": "the asserted provision could not be resolved in the statute store",
    "foreign_provision": "the asserted provision belongs to a different legal order",
    "internal_contradiction": "the samples contradict each other on a rule-level relation",
    "undefined_reliability": "no calibrated reliability is available for this stratum",
}


@dataclass(frozen=True)
class DecisionPolicy:
    """Loss-based answer/verify/abstain rule.

    ``verify_cost`` and ``abstain_cost`` are expressed on the same scale as the
    harm weights (a multiple of the least serious wrong answer). They are design
    constants, recorded in the run metadata and never tuned against the
    evaluation split.
    """

    verify_cost: float = 0.15
    abstain_cost: float = 0.35
    on_undefined: str = "verify"
    harm_weights: tuple[tuple[str, float], ...] = tuple(sorted(HARM_WEIGHTS.items()))

    def __post_init__(self) -> None:
        if not (math.isfinite(self.verify_cost) and self.verify_cost > 0):
            raise ValueError("verify_cost must be finite and positive")
        if not (math.isfinite(self.abstain_cost) and self.abstain_cost > 0):
            raise ValueError("abstain_cost must be finite and positive")
        if self.verify_cost >= self.abstain_cost:
            raise ValueError("verify_cost must be below abstain_cost")
        if self.on_undefined not in ("verify", "abstain"):
            raise ValueError("on_undefined must be 'verify' or 'abstain'")

    # -- weights and thresholds -----------------------------------------
    def weight(self, harm_class: str | None) -> float:
        """Harm weight from this policy's configured table.

        An unknown harm class is an error rather than a silent default: the
        operator must state how serious an unresolvable question is.
        """
        key = "unknown" if harm_class is None else str(harm_class)
        weights = dict(self.harm_weights)
        if key not in weights:
            raise ValueError(f"no harm weight configured for {key!r}; "
                             f"configured: {sorted(weights)}")
        return float(weights[key])

    def thresholds(self, harm_class: str | None) -> dict:
        h = self.weight(harm_class)
        p_answer = 1.0 - self.verify_cost / h
        p_verify = 1.0 - self.abstain_cost / h
        return {"harm_class": harm_class or "unknown", "harm_weight": h,
                "p_answer": max(0.0, min(1.0, p_answer)),
                "p_verify": max(0.0, min(1.0, p_verify)),
                "abstain_reachable": h > self.abstain_cost}

    # -- decision -------------------------------------------------------
    def decide(self, p_reliable: float | None, harm_class: str | None, *,
               flags: tuple[str, ...] | list[str] = (),
               as_of: str | None = None) -> dict:
        """Return the action, the thresholds used and a user-facing reason."""
        thresholds = self.thresholds(harm_class)
        if p_reliable is None:
            action = self.on_undefined
            return {"action": action, "p_reliable": None,
                    "thresholds": thresholds, "reason": self.reason(
                        action, None, harm_class, ("undefined_reliability",) + tuple(flags), as_of),
                    "trigger": "undefined_reliability"}
        p = float(p_reliable)
        if not math.isfinite(p) or not 0.0 <= p <= 1.0:
            raise ValueError("p_reliable must be finite and lie in [0, 1]")
        loss_answer = (1.0 - p) * thresholds["harm_weight"]
        if loss_answer <= self.verify_cost:
            action, trigger = "answer", "reliability_above_answer_threshold"
        elif loss_answer <= self.abstain_cost:
            action, trigger = "verify", "reliability_between_verify_and_answer_thresholds"
        else:
            action, trigger = "abstain", "reliability_below_verify_threshold"
        if action == "answer" and flags:
            # A fired Phase D flag is a legal objection to the answer; never
            # answer unassisted over one, whatever the calibrated number says.
            action, trigger = "verify", "phase_d_flag_outranks_calibrated_reliability"
        return {"action": action, "p_reliable": p, "thresholds": thresholds,
                "loss_answer": loss_answer, "loss_verify": self.verify_cost,
                "loss_abstain": self.abstain_cost, "trigger": trigger,
                "reason": self.reason(action, p, harm_class, tuple(flags), as_of)}

    # -- explanation ----------------------------------------------------
    def reason(self, action: str, p: float | None, harm_class: str | None,
               flags: tuple[str, ...] | list[str], as_of: str | None) -> str:
        parts: list[str] = []
        if p is None:
            parts.append("calibrated reliability is undefined for this stratum")
        else:
            parts.append(f"calibrated reliability {p:.2f}")
        if harm_class:
            parts.append(f"harm class {harm_class}")
        if as_of:
            parts.append(f"law as of {as_of}")
        detail = [ _FLAG_TEXT.get(flag, f"detector flag {flag}") for flag in flags ]
        if detail:
            parts.append("; ".join(detail))
        if action == "answer":
            parts.append("answered without verification")
        elif action == "verify":
            parts.append("needs human verification before reliance")
        else:
            parts.append("not answered: the system cannot state a reliable provision for this question")
        return "; ".join(parts)

    def to_dict(self) -> dict:
        return {"verify_cost": self.verify_cost, "abstain_cost": self.abstain_cost,
                "on_undefined": self.on_undefined,
                "harm_weights": dict(self.harm_weights),
                "rule": "answer if (1-p)*h <= verify_cost; verify if <= abstain_cost; else abstain"}

    @classmethod
    def from_dict(cls, obj: dict) -> "DecisionPolicy":
        weights = obj.get("harm_weights") or HARM_WEIGHTS
        return cls(float(obj.get("verify_cost", 0.15)),
                   float(obj.get("abstain_cost", 0.35)),
                   str(obj.get("on_undefined", "verify")),
                   tuple(sorted((str(k), float(v)) for k, v in weights.items())))


def harm_class_from_store(topic: str | None, store_rows: list[dict], *,
                          rule: str = "max") -> str:
    """Harm class of the offence cluster a question is about.

    Derived from the question's topic and the Phase C statute store, so the
    query path never needs the gold provision. ``rule`` chooses the most serious
    class in the cluster (``max``, the conservative default) or the most common
    one (``modal``).
    """
    if not topic:
        return "unknown"
    classes = [row.get("consequence_class") for row in store_rows
               if row.get("offence_cluster") == topic and row.get("consequence_class")]
    if not classes:
        return "unknown"
    if rule == "modal":
        counts: dict[str, int] = {}
        for cls in classes:
            counts[cls] = counts.get(cls, 0) + 1
        return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
    if rule != "max":
        raise ValueError("rule must be 'max' or 'modal'")
    return max(classes, key=lambda cls: harm_weight(cls))


def action_census(decisions: list[dict]) -> dict:
    """Count actions and triggers over a run (report helper)."""
    census = {action: 0 for action in ACTIONS}
    triggers: dict[str, int] = {}
    for decision in decisions:
        action = decision.get("action")
        if action not in census:
            raise ValueError(f"unexpected action {action!r}")
        census[action] += 1
        trigger = decision.get("trigger", "unknown")
        triggers[trigger] = triggers.get(trigger, 0) + 1
    return {"actions": census, "triggers": dict(sorted(triggers.items()))}
