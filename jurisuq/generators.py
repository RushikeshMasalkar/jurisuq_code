"""Sampling harness: one interface, three providers.

``OpenAICompatGenerator``
    Any server exposing ``/v1/chat/completions``: LM Studio (port 1234),
    llama.cpp ``llama-server`` (port 8080), Ollama (port 11434), vLLM.

``MockGenerator``
    A deterministic synthetic answerer used to exercise the whole pipeline
    before a model is installed. It reproduces the two error regimes that E1
    is about: *common-mode* error (the whole sample set agrees on a wrong,
    systematically biased answer) and *idiosyncratic* error (individual
    samples deviate at high temperature). Numbers produced with it are a
    plumbing check and must never be reported as results.
"""
from __future__ import annotations

import hashlib
import random
import time
from dataclasses import dataclass, field

import requests

# Prompt revision identifier. Stored in every run's meta.json, because an answer
# is only interpretable together with the instructions that produced it.
PROMPT_VERSION = "p2-structured"


@dataclass
class GenResult:
    text: str
    n_tokens: int = 0
    mean_logprob: float | None = None
    finish_reason: str | None = None
    latency_s: float = 0.0
    meta: dict = field(default_factory=dict)


# ----------------------------------------------------------------------
def _stable_seed(*parts) -> int:
    h = hashlib.md5("|".join(str(p) for p in parts).encode()).hexdigest()
    return int(h[:12], 16)


class BaseGenerator:
    name = "base"

    def sample(self, prompt: str, n: int, meta: dict | None = None) -> list[GenResult]:
        raise NotImplementedError

    def one(self, prompt: str, temperature: float = 0.0, max_tokens: int = 320) -> GenResult:
        return self.sample(prompt, n=1, meta={"temperature": temperature,
                                              "max_tokens": max_tokens})[0]


# ----------------------------------------------------------------------
class MockGenerator(BaseGenerator):
    """Deterministic synthetic answerer used to exercise the harness.

    Per item it draws one of three regimes, which is exactly the structure the
    diagnostic slice is built to expose:

    ``trapped``    the model appears to believe the repealed provision: every
                   sample is the *identical* wrong answer, so any agreement-
                   based uncertainty score reports zero entropy and maximum
                   confidence. This is the common-mode failure E1 measures.
    ``uncertain``  genuine uncertainty: samples differ in wording and in
                   substance, sometimes wrong.
    ``confident``  every sample is the identical correct answer.

    The wording is fixed *per regime, not per sample*, because a shared bias
    reproduces the same sentence, not three paraphrases of it - that is what
    makes a real common-mode error invisible to sampling.

    Numbers from this generator are a plumbing check and must never be
    reported as results.
    """

    name = "mock"

    def __init__(self, cfg):
        self.cfg = cfg
        self.seed = cfg.seed
        self.p_trap_slice = dict(cfg.mock_p_trap_slice)
        self.p_uncertain = float(cfg.mock_p_uncertain)
        self.p_wrong_uncertain = float(cfg.mock_p_wrong_when_uncertain)
        self.calls = 0

    # -- answer construction ------------------------------------------
    @staticmethod
    def _fmt(act: str, provision: str) -> str:
        return f"Section {provision} of the {act}"

    def _correct_form(self, item: dict, variant: int) -> str:
        act, prov = item["gold_act"], item["gold_provision"]
        pun = item.get("punishment") or "the prescribed punishment"
        if item.get("template") == "T4" and item.get("trap_act"):
            body = (f"The {item['trap_act']} was repealed with effect from 1 July 2024. "
                    f"The provision now in force is {self._fmt(act, prov)}, "
                    f"which prescribes {pun}.")
            return body if variant != 1 else f"Answer: {body}"
        if variant == 0:
            return f"The applicable provision is {self._fmt(act, prov)}, which prescribes {pun}."
        if variant == 1:
            return f"Answer: {act} section {prov} - punishment: {pun}."
        return f"In India today, the applicable provision is {self._fmt(act, prov)}, which prescribes {pun}."

    def _wrong_form(self, item: dict, variant: int) -> str:
        act, prov = item.get("trap_act"), item.get("trap_provision")
        pun = item.get("punishment") or "the prescribed punishment"
        if not act:                                     # no temporal trap available
            act = item["gold_act"]
            prov = item.get("distractor_provision") or item["gold_provision"]
        if variant == 0:
            return f"The applicable provision is {self._fmt(act, prov)}, which prescribes {pun}."
        if variant == 1:
            return f"Answer: section {prov} of the {act} - {pun}."
        return f"In India today, {self._fmt(act, prov)} applies, and the punishment is {pun}."

    # -- regimes --------------------------------------------------------
    def _regime(self, prompt: str, slice_name: str) -> str:
        rng = random.Random(_stable_seed(prompt, self.seed, "regime"))
        u = rng.random()
        p_trap = float(self.p_trap_slice.get(slice_name, 0.0))
        if u < p_trap:
            return "trapped"
        if u < p_trap + self.p_uncertain:
            return "uncertain"
        return "confident"

    # -- sampling -------------------------------------------------------
    def sample(self, prompt: str, n: int, meta: dict | None = None) -> list[GenResult]:
        item = meta or {}
        regime = self._regime(prompt, item.get("slice", "L1"))
        fixed_variant = random.Random(_stable_seed(prompt, self.seed, "variant", regime)).randrange(3)

        out: list[GenResult] = []
        for i in range(n):
            rng = random.Random(_stable_seed(prompt, self.seed, i))
            if regime == "trapped":
                wrong, variant = True, fixed_variant
            elif regime == "confident":
                wrong, variant = False, fixed_variant
            else:
                wrong = rng.random() < self.p_wrong_uncertain
                variant = rng.randrange(3)
            text = self._wrong_form(item, variant) if wrong else self._correct_form(item, variant)
            out.append(GenResult(text=text, n_tokens=len(text.split()),
                                 mean_logprob=-0.12 - 0.4 * rng.random(),
                                 finish_reason="stop", latency_s=0.0,
                                 meta={"mock": True, "regime": regime}))
            self.calls += 1
        return out


# ----------------------------------------------------------------------
class OpenAICompatGenerator(BaseGenerator):
    """Any OpenAI-compatible ``/v1/chat/completions`` endpoint."""

    name = "openai-compat"

    # Prompt revision 2. Three deliberate constraints, each with a reason:
    #  * a fixed answer skeleton, so the provision is on the first line and the
    #    judge reads a structured field instead of prose;
    #  * the era is named explicitly, because the slice asks about two eras and a
    #    model that silently answers about the wrong one is not being measured;
    #  * Indian law only, so that the measured failure is the temporal one.
    #    Jurisdiction confusion is a real phenomenon (revision 1 recorded a South
    #    African citation) but it is a separate claim, reported from that run
    #    rather than mixed into this measurement.
    SYSTEM = ("You are an Indian legal research assistant answering questions about Indian "
              "penal law.\n\n"
              "Answer in exactly this format, with no preamble and no extra headings:\n"
              "Provision: <name of the Act>, section <number>\n"
              "Reason: <one sentence>\n"
              "Punishment: <one short line, or 'not applicable'>\n\n"
              "Rules:\n"
              "- Give the provision that applies in the era the question asks about.\n"
              "- Use Indian law only. Never cite the law of another country.\n"
              "- Always give your single best answer, even if you are not sure.")

    def __init__(self, cfg):
        self.cfg = cfg
        self.base = cfg.base_url.rstrip("/")
        self.model = cfg.model
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "Authorization": f"Bearer {cfg.api_key}",
        })
        self._logprobs_ok = True
        self.name = f"openai-compat:{self.model}"

    def _payload(self, prompt: str, temperature: float, max_tokens: int,
                 seed: int | None, want_logprobs: bool) -> dict:
        p = {
            "model": self.model,
            "messages": [{"role": "system", "content": self.SYSTEM},
                         {"role": "user", "content": prompt}],
            "temperature": temperature,
            "top_p": self.cfg.top_p,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if seed is not None:
            p["seed"] = seed
        if want_logprobs:
            p["logprobs"] = True
            p["top_logprobs"] = 1
        return p

    def _post(self, payload: dict) -> dict:
        url = f"{self.base}/chat/completions"
        last = None
        for attempt in range(self.cfg.retries):
            try:
                r = self.session.post(url, json=payload, timeout=self.cfg.request_timeout)
                if r.status_code == 400 and "logprobs" in payload:
                    raise _LogprobsUnsupported()
                r.raise_for_status()
                return r.json()
            except _LogprobsUnsupported:
                raise
            except Exception as exc:                     # network / server hiccup
                last = exc
                time.sleep(1.5 * (attempt + 1))
        raise RuntimeError(f"generation request failed after {self.cfg.retries} tries: {last}")

    def sample(self, prompt: str, n: int, meta: dict | None = None) -> list[GenResult]:
        meta = meta or {}
        temperature = float(meta.get("temperature", self.cfg.temperature))
        max_tokens = int(meta.get("max_tokens", self.cfg.max_tokens))
        base_seed = int(meta.get("seed", self.cfg.seed))

        results: list[GenResult] = []
        i = 0
        while len(results) < n:
            payload = self._payload(prompt, temperature, max_tokens,
                                    base_seed + i, self._logprobs_ok)
            t0 = time.time()
            try:
                data = self._post(payload)
            except _LogprobsUnsupported:
                self._logprobs_ok = False
                continue
            dt = time.time() - t0
            choice = (data.get("choices") or [{}])[0]
            text = ((choice.get("message") or {}).get("content") or "").strip()
            if not text:
                i += 1
                continue
            usage = data.get("usage") or {}
            results.append(GenResult(
                text=text,
                n_tokens=int(usage.get("completion_tokens") or 0),
                mean_logprob=_mean_logprob(choice),
                finish_reason=choice.get("finish_reason"),
                latency_s=dt,
            ))
            i += 1
        return results


class _LogprobsUnsupported(Exception):
    pass


def _mean_logprob(choice: dict) -> float | None:
    lp = choice.get("logprobs") or {}
    content = lp.get("content") or []
    vals = [c.get("logprob") for c in content if isinstance(c, dict) and c.get("logprob") is not None]
    if not vals:
        return None
    return sum(vals) / len(vals)


# ----------------------------------------------------------------------
def make_generator(cfg) -> BaseGenerator:
    if cfg.provider == "mock":
        return MockGenerator(cfg)
    if cfg.provider == "openai":
        return OpenAICompatGenerator(cfg)
    raise SystemExit(f"unknown provider: {cfg.provider!r} (use 'mock' or 'openai')")


def endpoint_status(cfg) -> dict:
    """Probe an OpenAI-compatible endpoint; used by scripts/00_env_check.py."""
    base = cfg.base_url.rstrip("/")
    out = {"base_url": base, "reachable": False, "models": [], "error": None}
    try:
        r = requests.get(f"{base}/models", timeout=10)
        out["reachable"] = r.status_code == 200
        if out["reachable"]:
            data = r.json().get("data") or r.json().get("models") or []
            out["models"] = [d.get("id") or d.get("name") for d in data if isinstance(d, dict)]
    except Exception as exc:
        out["error"] = str(exc)
    return out
