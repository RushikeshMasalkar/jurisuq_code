"""Run configuration: one JSON file per experiment run."""
from __future__ import annotations

import argparse
import json
import pathlib
from dataclasses import asdict, dataclass, field

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "configs" / "phase_a.json"


@dataclass
class Config:
    # ---- run identity -------------------------------------------------
    run_id: str = "phaseA-smoke"
    out_dir: str = "runs"

    # ---- generator ----------------------------------------------------
    provider: str = "mock"                      # "mock" | "openai"
    base_url: str = "http://127.0.0.1:1234/v1"  # LM Studio default
    model: str = "local-model"
    api_key: str = "sk-local"
    temperature: float = 1.0
    top_p: float = 1.0
    max_tokens: int = 220
    n_samples: int = 10
    request_timeout: int = 240
    retries: int = 3
    workers: int = 1                            # >1 only if the server has slots

    # ---- clustering ---------------------------------------------------
    clusterer: str = "both"                     # "discrete" | "entailment" | "both"
    nli_model: str = "MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli"
    entail_threshold: float = 0.80
    allow_lexical_fallback: bool = True         # if transformers is unavailable

    # ---- correctness --------------------------------------------------
    judge: str = "provision"                    # "provision" | "llm"
    judge_scope: str = "representatives"        # "representatives" | "all"

    # ---- data ---------------------------------------------------------
    slices: list[str] = field(default_factory=lambda: ["L7", "L1"])
    limit: int = 0                              # 0 = all items
    seed: int = 20261005

    # ---- mock-generator behaviour (smoke tests only) -------------------
    # mock generator: per item one of three regimes is drawn
    #   "trapped"   all samples give the identical wrong answer (shared bias)
    #   "uncertain" samples vary, sometimes wrong (ordinary uncertainty)
    #   "confident" all samples give the identical correct answer
    mock_p_trap_slice: dict = field(default_factory=lambda: {"L7": 0.55, "L1": 0.05})
    mock_p_uncertain: float = 0.20
    mock_p_wrong_when_uncertain: float = 0.40

    # ------------------------------------------------------------------
    @classmethod
    def load(cls, path: str | pathlib.Path | None = None) -> "Config":
        path = pathlib.Path(path) if path else DEFAULT_CONFIG
        if not path.exists():
            return cls()
        data = json.loads(path.read_text())
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})

    def save(self, path: str | pathlib.Path) -> None:
        path = pathlib.Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2) + "\n")

    def run_dir(self) -> pathlib.Path:
        d = ROOT / self.out_dir / self.run_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def apply_overrides(self, kv: list[str]) -> "Config":
        """--set key=value overrides, values parsed as JSON when possible."""
        for item in kv or []:
            key, _, raw = item.partition("=")
            key = key.strip().replace("-", "_")
            if not key or key not in self.__dataclass_fields__:
                raise SystemExit(f"unknown config key: {key!r}")
            try:
                value = json.loads(raw)
            except json.JSONDecodeError:
                value = raw
            setattr(self, key, value)
        return self


def add_common_args(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--set", dest="overrides", action="append", default=[],
                        help="override a config key, e.g. --set n_samples=20")
    return parser


def config_from_args(args: argparse.Namespace) -> Config:
    cfg = Config.load(args.config).apply_overrides(args.overrides)
    if getattr(args, "run_id", None):
        cfg.run_id = args.run_id
    return cfg
