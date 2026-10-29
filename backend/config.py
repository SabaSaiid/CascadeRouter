"""Central configuration for the CascadeRouter backend.

Every value comes from the environment (or a `.env` file at the repo root).
The model catalog defined here is the single source of truth for prices.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Literal, Mapping

from dotenv import dotenv_values

REPO_ROOT = Path(__file__).resolve().parent.parent
DOTENV_PATH = REPO_ROOT / ".env"

DataSourceMode = Literal["live", "recorded", "mock"]
ModelTier = Literal["efficient", "balanced", "powerful"]

_VALID_MODES = ("live", "recorded", "mock")
_VALID_LOG_LEVELS = ("CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET")

Env = Mapping[str, str]


class ConfigError(ValueError):
    """Raised when an environment value cannot be parsed."""


def _get_str(env: Env, name: str, default: str) -> str:
    value = env.get(name)
    return default if value is None or value.strip() == "" else value.strip()


def _get_float(env: Env, name: str, default: float, *, minimum: float | None = None) -> float:
    raw = env.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a number, got {raw!r}") from exc
    if not math.isfinite(value):
        raise ConfigError(f"{name} must be finite, got {raw!r}")
    if minimum is not None and value < minimum:
        raise ConfigError(f"{name} must be >= {minimum}, got {value}")
    return value


def _get_int(env: Env, name: str, default: int, *, minimum: int | None = None) -> int:
    raw = env.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer, got {raw!r}") from exc
    if minimum is not None and value < minimum:
        raise ConfigError(f"{name} must be >= {minimum}, got {value}")
    return value


def _get_bool(env: Env, name: str, default: bool) -> bool:
    raw = env.get(name)
    if raw is None or raw.strip() == "":
        return default
    lowered = raw.strip().lower()
    if lowered in ("1", "true", "yes", "on"):
        return True
    if lowered in ("0", "false", "no", "off"):
        return False
    raise ConfigError(f"{name} must be a boolean, got {raw!r}")


def _get_list(env: Env, name: str, default: list[str]) -> list[str]:
    raw = env.get(name)
    if raw is None or raw.strip() == "":
        return list(default)
    return [item.strip() for item in raw.split(",") if item.strip()]


@dataclass(frozen=True)
class ModelSpec:
    id: str
    name: str
    tier: ModelTier
    input_price_per_m: float
    output_price_per_m: float
    description: str
    badge_color: str


@dataclass(frozen=True)
class Settings:
    nebius_api_key: str = field(repr=False)
    nebius_base_url: str
    models: tuple[ModelSpec, ...]
    quality_threshold: float
    benchmark_concurrency: int
    benchmark_timeout_seconds: float
    regression_timeout_seconds: float
    host: str
    port: int
    environment: str
    log_level: str
    cors_origins: list[str]
    data_source_mode: DataSourceMode
    enable_rate_limiting: bool
    rate_limit_per_minute: int
    daily_spend_cap_usd: float
    tavily_api_key: str = field(repr=False)
    allowed_scan_roots: list[Path] = field(default_factory=list)
    allowed_hosts: list[str] = field(default_factory=lambda: ["localhost", "127.0.0.1"])
    max_concurrent_runs: int = 2
    record_runs: bool = False
    recordings_dir: Path = REPO_ROOT / "recordings"

    @property
    def nebius_configured(self) -> bool:
        key = self.nebius_api_key
        return bool(key) and not key.startswith("your-")

    def model_by_id(self, model_id: str) -> ModelSpec | None:
        for spec in self.models:
            if spec.id == model_id:
                return spec
        return None

    @property
    def powerful_model(self) -> ModelSpec:
        return next(m for m in self.models if m.tier == "powerful")


def _build_catalog(env: Env) -> tuple[ModelSpec, ...]:
    eff_in = _get_float(env, "PRICE_EFFICIENT_INPUT", 0.06, minimum=0)
    eff_out = _get_float(env, "PRICE_EFFICIENT_OUTPUT", 0.24, minimum=0)
    bal_in = _get_float(env, "PRICE_BALANCED_INPUT", 0.30, minimum=0)
    bal_out = _get_float(env, "PRICE_BALANCED_OUTPUT", 0.90, minimum=0)
    pow_in = _get_float(env, "PRICE_POWERFUL_INPUT", 1.00, minimum=0)
    pow_out = _get_float(env, "PRICE_POWERFUL_OUTPUT", 3.00, minimum=0)

    catalog = (
        ModelSpec(
            id=_get_str(env, "MODEL_TIER_EFFICIENT", "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B"),
            name="Nemotron-3 Nano (30B)",
            tier="efficient",
            input_price_per_m=eff_in,
            output_price_per_m=eff_out,
            description="Lightweight & ultra-low latency, ideal for extraction & categorization",
            badge_color="emerald",
        ),
        ModelSpec(
            id=_get_str(env, "MODEL_TIER_EFFICIENT_ALT", "nvidia/Nemotron-3_5-Lightning"),
            name="Nemotron-3.5 Lightning",
            tier="efficient",
            input_price_per_m=eff_in,
            output_price_per_m=eff_out,
            description="Ultra-fast token generation for intermediate agent steps",
            badge_color="cyan",
        ),
        ModelSpec(
            id=_get_str(env, "MODEL_TIER_BALANCED", "nvidia/Nemotron-3.5-Super-VL"),
            name="Nemotron-3.5 Super-VL",
            tier="balanced",
            input_price_per_m=bal_in,
            output_price_per_m=bal_out,
            description="Balanced multimodal reasoning & complex structured transformations",
            badge_color="purple",
        ),
        ModelSpec(
            id=_get_str(env, "MODEL_TIER_POWERFUL", "nvidia/Nemotron-3-Ultra-550b-a55b"),
            name="Nemotron-3 Ultra (550B)",
            tier="powerful",
            input_price_per_m=pow_in,
            output_price_per_m=pow_out,
            description="Frontier reasoning & code generation; acts as fallback safety tier",
            badge_color="amber",
        ),
    )
    ids = [m.id for m in catalog]
    if len(set(ids)) != len(ids):
        raise ConfigError(f"MODEL_TIER_* ids must be unique, got {ids}")
    return catalog


def _resolve_dir(raw: str) -> Path:
    path = Path(raw).expanduser()
    return (path if path.is_absolute() else REPO_ROOT / path).resolve()


def load_settings(env: Env | None = None) -> Settings:
    """Build a Settings object from `env` (defaults to the process environment)."""
    env = os.environ if env is None else env
    mode = _get_str(env, "DATA_SOURCE_MODE", "live").lower()
    if mode not in _VALID_MODES:
        raise ConfigError(f"DATA_SOURCE_MODE must be one of {_VALID_MODES}, got {mode!r}")

    threshold = _get_float(env, "QUALITY_THRESHOLD", 0.92, minimum=0)
    if threshold > 1:
        raise ConfigError(f"QUALITY_THRESHOLD must be <= 1, got {threshold}")

    log_level = _get_str(env, "LOG_LEVEL", "INFO").upper()
    if log_level not in _VALID_LOG_LEVELS:
        raise ConfigError(f"LOG_LEVEL must be one of {_VALID_LOG_LEVELS}, got {log_level!r}")

    roots = _get_list(env, "ALLOWED_SCAN_ROOTS", [str(REPO_ROOT)])
    if not roots:
        raise ConfigError("ALLOWED_SCAN_ROOTS must name at least one directory")
    allowed_roots = []
    for raw_root in roots:
        root = Path(raw_root).expanduser()
        allowed_roots.append((root if root.is_absolute() else REPO_ROOT / root).resolve())

    return Settings(
        nebius_api_key=_get_str(env, "NEBIUS_API_KEY", ""),
        nebius_base_url=_get_str(env, "NEBIUS_BASE_URL", "https://api.studio.nebius.ai/v1"),
        models=_build_catalog(env),
        quality_threshold=threshold,
        benchmark_concurrency=_get_int(env, "BENCHMARK_CONCURRENCY", 4, minimum=1),
        benchmark_timeout_seconds=_get_float(env, "BENCHMARK_TIMEOUT_SECONDS", 45, minimum=1),
        regression_timeout_seconds=_get_float(env, "REGRESSION_TIMEOUT_SECONDS", 30, minimum=1),
        host=_get_str(env, "HOST", "127.0.0.1"),
        port=_get_int(env, "PORT", 8000, minimum=1),
        environment=_get_str(env, "ENVIRONMENT", "development"),
        log_level=log_level,
        cors_origins=_get_list(
            env,
            "CORS_ORIGINS",
            ["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173"],
        ),
        data_source_mode=mode,  # type: ignore[arg-type]
        enable_rate_limiting=_get_bool(env, "ENABLE_RATE_LIMITING", True),
        rate_limit_per_minute=_get_int(env, "RATE_LIMIT_PER_MINUTE", 60, minimum=1),
        daily_spend_cap_usd=_get_float(env, "DAILY_SPEND_CAP_USD", 10.0, minimum=0),
        tavily_api_key=_get_str(env, "TAVILY_API_KEY", ""),
        allowed_scan_roots=allowed_roots,
        allowed_hosts=_get_list(env, "ALLOWED_HOSTS", ["localhost", "127.0.0.1"]),
        max_concurrent_runs=_get_int(env, "MAX_CONCURRENT_RUNS", 2, minimum=1),
        record_runs=_get_bool(env, "RECORD_RUNS", False),
        recordings_dir=_resolve_dir(_get_str(env, "RECORDINGS_DIR", "recordings")),
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings for the running app.

    Values from `.env` are used as defaults; real environment variables win.
    `os.environ` itself is never modified.
    """
    file_values = {k: v for k, v in dotenv_values(DOTENV_PATH).items() if v is not None}
    return load_settings({**file_values, **os.environ})
