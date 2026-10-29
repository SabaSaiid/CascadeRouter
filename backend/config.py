"""Central configuration for the CascadeRouter backend.

Every value comes from the environment (or a `.env` file at the repo root).
The model catalog defined here is the single source of truth for prices.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent

DataSourceMode = Literal["live", "recorded", "mock"]
ModelTier = Literal["efficient", "balanced", "powerful"]

_VALID_MODES = ("live", "recorded", "mock")


class ConfigError(ValueError):
    """Raised when an environment value cannot be parsed."""


def _get_str(name: str, default: str) -> str:
    value = os.getenv(name)
    return default if value is None or value.strip() == "" else value.strip()


def _get_float(name: str, default: float, *, minimum: float | None = None) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a number, got {raw!r}") from exc
    if minimum is not None and value < minimum:
        raise ConfigError(f"{name} must be >= {minimum}, got {value}")
    return value


def _get_int(name: str, default: int, *, minimum: int | None = None) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer, got {raw!r}") from exc
    if minimum is not None and value < minimum:
        raise ConfigError(f"{name} must be >= {minimum}, got {value}")
    return value


def _get_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    lowered = raw.strip().lower()
    if lowered in ("1", "true", "yes", "on"):
        return True
    if lowered in ("0", "false", "no", "off"):
        return False
    raise ConfigError(f"{name} must be a boolean, got {raw!r}")


def _get_list(name: str, default: list[str]) -> list[str]:
    raw = os.getenv(name)
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
    nebius_api_key: str
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
    tavily_api_key: str
    allowed_scan_roots: list[Path] = field(default_factory=list)

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


def _build_catalog() -> tuple[ModelSpec, ...]:
    eff_in = _get_float("PRICE_EFFICIENT_INPUT", 0.06, minimum=0)
    eff_out = _get_float("PRICE_EFFICIENT_OUTPUT", 0.24, minimum=0)
    bal_in = _get_float("PRICE_BALANCED_INPUT", 0.30, minimum=0)
    bal_out = _get_float("PRICE_BALANCED_OUTPUT", 0.90, minimum=0)
    pow_in = _get_float("PRICE_POWERFUL_INPUT", 1.00, minimum=0)
    pow_out = _get_float("PRICE_POWERFUL_OUTPUT", 3.00, minimum=0)

    catalog = (
        ModelSpec(
            id=_get_str("MODEL_TIER_EFFICIENT", "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B"),
            name="Nemotron-3 Nano (30B)",
            tier="efficient",
            input_price_per_m=eff_in,
            output_price_per_m=eff_out,
            description="Lightweight & ultra-low latency, ideal for extraction & categorization",
            badge_color="emerald",
        ),
        ModelSpec(
            id=_get_str("MODEL_TIER_EFFICIENT_ALT", "nvidia/Nemotron-3_5-Lightning"),
            name="Nemotron-3.5 Lightning",
            tier="efficient",
            input_price_per_m=eff_in,
            output_price_per_m=eff_out,
            description="Ultra-fast token generation for intermediate agent steps",
            badge_color="cyan",
        ),
        ModelSpec(
            id=_get_str("MODEL_TIER_BALANCED", "nvidia/Nemotron-3.5-Super-VL"),
            name="Nemotron-3.5 Super-VL",
            tier="balanced",
            input_price_per_m=bal_in,
            output_price_per_m=bal_out,
            description="Balanced multimodal reasoning & complex structured transformations",
            badge_color="purple",
        ),
        ModelSpec(
            id=_get_str("MODEL_TIER_POWERFUL", "nvidia/Nemotron-3-Ultra-550b-a55b"),
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


def load_settings() -> Settings:
    """Build a fresh Settings object from the current environment."""
    mode = _get_str("DATA_SOURCE_MODE", "live").lower()
    if mode not in _VALID_MODES:
        raise ConfigError(f"DATA_SOURCE_MODE must be one of {_VALID_MODES}, got {mode!r}")

    threshold = _get_float("QUALITY_THRESHOLD", 0.92, minimum=0)
    if threshold > 1:
        raise ConfigError(f"QUALITY_THRESHOLD must be <= 1, got {threshold}")

    roots = _get_list("ALLOWED_SCAN_ROOTS", [str(REPO_ROOT)])
    allowed_roots = [
        (Path(r) if Path(r).is_absolute() else REPO_ROOT / r).resolve() for r in roots
    ]

    return Settings(
        nebius_api_key=_get_str("NEBIUS_API_KEY", ""),
        nebius_base_url=_get_str("NEBIUS_BASE_URL", "https://api.studio.nebius.ai/v1"),
        models=_build_catalog(),
        quality_threshold=threshold,
        benchmark_concurrency=_get_int("BENCHMARK_CONCURRENCY", 4, minimum=1),
        benchmark_timeout_seconds=_get_float("BENCHMARK_TIMEOUT_SECONDS", 45, minimum=1),
        regression_timeout_seconds=_get_float("REGRESSION_TIMEOUT_SECONDS", 30, minimum=1),
        host=_get_str("HOST", "0.0.0.0"),
        port=_get_int("PORT", 8000, minimum=1),
        environment=_get_str("ENVIRONMENT", "development"),
        log_level=_get_str("LOG_LEVEL", "INFO").upper(),
        cors_origins=_get_list(
            "CORS_ORIGINS",
            ["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173"],
        ),
        data_source_mode=mode,  # type: ignore[arg-type]
        enable_rate_limiting=_get_bool("ENABLE_RATE_LIMITING", True),
        rate_limit_per_minute=_get_int("RATE_LIMIT_PER_MINUTE", 60, minimum=1),
        daily_spend_cap_usd=_get_float("DAILY_SPEND_CAP_USD", 10.0, minimum=0),
        tavily_api_key=_get_str("TAVILY_API_KEY", ""),
        allowed_scan_roots=allowed_roots,
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings for the running app (loads `.env` once)."""
    load_dotenv(REPO_ROOT / ".env", override=False)
    return load_settings()
