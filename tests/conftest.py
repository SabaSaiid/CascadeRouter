"""Shared test fixtures: isolate every test from the host environment."""

from __future__ import annotations

import os

import pytest

from backend.config import get_settings

_ENV_PREFIXES = (
    "NEBIUS_", "MODEL_TIER_", "PRICE_", "QUALITY_", "BENCHMARK_", "REGRESSION_",
    "DATA_SOURCE_", "RATE_LIMIT", "ENABLE_RATE", "DAILY_SPEND", "CORS_", "ALLOWED_SCAN",
    "TAVILY_", "ENVIRONMENT", "LOG_LEVEL",
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch):
    for key in list(os.environ):
        if key.startswith(_ENV_PREFIXES):
            monkeypatch.delenv(key, raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
