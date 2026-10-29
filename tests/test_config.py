from pathlib import Path

import pytest

from backend.config import REPO_ROOT, ConfigError, load_settings


def test_defaults_match_env_example():
    s = load_settings()
    assert [m.id for m in s.models] == [
        "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B",
        "nvidia/Nemotron-3_5-Lightning",
        "nvidia/Nemotron-3.5-Super-VL",
        "nvidia/Nemotron-3-Ultra-550b-a55b",
    ]
    assert [m.tier for m in s.models] == ["efficient", "efficient", "balanced", "powerful"]
    assert s.models[0].input_price_per_m == 0.06 and s.models[0].output_price_per_m == 0.24
    assert s.models[2].input_price_per_m == 0.30 and s.models[2].output_price_per_m == 0.90
    assert s.models[3].input_price_per_m == 1.00 and s.models[3].output_price_per_m == 3.00
    assert s.quality_threshold == 0.92
    assert s.benchmark_concurrency == 4
    assert s.data_source_mode == "live"
    assert s.allowed_scan_roots == [REPO_ROOT]
    assert s.powerful_model.id == "nvidia/Nemotron-3-Ultra-550b-a55b"


def test_env_overrides(monkeypatch):
    monkeypatch.setenv("PRICE_EFFICIENT_INPUT", "0.1")
    monkeypatch.setenv("MODEL_TIER_BALANCED", "acme/mid")
    monkeypatch.setenv("CORS_ORIGINS", "http://a, http://b ,")
    monkeypatch.setenv("ENABLE_RATE_LIMITING", "off")
    monkeypatch.setenv("DATA_SOURCE_MODE", "Recorded")
    s = load_settings()
    assert s.models[0].input_price_per_m == 0.1
    assert s.models[1].input_price_per_m == 0.1  # alt shares efficient pricing
    assert s.model_by_id("acme/mid").tier == "balanced"
    assert s.model_by_id("missing") is None
    assert s.cors_origins == ["http://a", "http://b"]
    assert s.enable_rate_limiting is False
    assert s.data_source_mode == "recorded"


@pytest.mark.parametrize(
    "key,value",
    [
        ("DATA_SOURCE_MODE", "fake"),
        ("QUALITY_THRESHOLD", "1.5"),
        ("QUALITY_THRESHOLD", "abc"),
        ("BENCHMARK_CONCURRENCY", "0"),
        ("BENCHMARK_CONCURRENCY", "2.5"),
        ("PRICE_POWERFUL_OUTPUT", "-1"),
        ("ENABLE_RATE_LIMITING", "maybe"),
        ("MODEL_TIER_EFFICIENT_ALT", "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B"),
    ],
)
def test_invalid_values_raise(monkeypatch, key, value):
    monkeypatch.setenv(key, value)
    with pytest.raises(ConfigError):
        load_settings()


def test_nebius_configured(monkeypatch):
    assert load_settings().nebius_configured is False
    monkeypatch.setenv("NEBIUS_API_KEY", "your-nebius-token-factory-api-key-here")
    assert load_settings().nebius_configured is False
    monkeypatch.setenv("NEBIUS_API_KEY", "sk-real")
    assert load_settings().nebius_configured is True


def test_relative_scan_roots_resolve_against_repo(monkeypatch, tmp_path):
    monkeypatch.setenv("ALLOWED_SCAN_ROOTS", f"tests/fixtures,{tmp_path}")
    s = load_settings()
    assert s.allowed_scan_roots == [(REPO_ROOT / "tests/fixtures").resolve(), Path(tmp_path).resolve()]


@pytest.mark.parametrize(
    "key,value",
    [
        ("QUALITY_THRESHOLD", "nan"),
        ("BENCHMARK_TIMEOUT_SECONDS", "inf"),
        ("DAILY_SPEND_CAP_USD", "-inf"),
        ("LOG_LEVEL", "verbose"),
        ("ALLOWED_SCAN_ROOTS", ","),
        ("PORT", "abc"),
    ],
)
def test_more_invalid_values_raise(monkeypatch, key, value):
    monkeypatch.setenv(key, value)
    with pytest.raises(ConfigError):
        load_settings()


def test_log_level_is_case_insensitive(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "debug")
    assert load_settings().log_level == "DEBUG"


def test_scan_roots_expand_home(monkeypatch):
    monkeypatch.setenv("ALLOWED_SCAN_ROOTS", "~/code")
    assert load_settings().allowed_scan_roots == [(Path.home() / "code").resolve()]


def test_load_settings_accepts_explicit_mapping():
    s = load_settings({"ENVIRONMENT": "staging", "DATA_SOURCE_MODE": "recorded"})
    assert (s.environment, s.data_source_mode) == ("staging", "recorded")


def test_get_settings_uses_dotenv_without_mutating_environ(monkeypatch, tmp_path):
    import os

    import backend.config as config

    env_file = tmp_path / ".env"
    env_file.write_text('ENVIRONMENT="from-dotenv"\nLOG_LEVEL=debug\nNEBIUS_API_KEY=sk-file\n')
    monkeypatch.setattr(config, "DOTENV_PATH", env_file)
    monkeypatch.setenv("LOG_LEVEL", "warning")  # real env wins over .env
    config.get_settings.cache_clear()
    s = config.get_settings()
    assert s.environment == "from-dotenv"
    assert s.log_level == "WARNING"
    assert s.nebius_api_key == "sk-file"
    assert "ENVIRONMENT" not in os.environ and "NEBIUS_API_KEY" not in os.environ
    assert config.get_settings() is s  # cached
