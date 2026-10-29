import pytest
from fastapi.testclient import TestClient

from backend import __version__
from backend.main import create_app


def _client() -> TestClient:
    return TestClient(create_app(), base_url="http://localhost")


def test_health_never_leaks_key(monkeypatch):
    monkeypatch.setenv("NEBIUS_API_KEY", "sk-secret-value")
    res = _client().get("/api/health")
    assert res.status_code == 200
    body = res.json()
    assert body == {
        "status": "ok",
        "version": __version__,
        "environment": "development",
        "data_source": "live",
        "nebius_configured": True,
    }
    assert "sk-secret-value" not in res.text


def test_models_endpoint_matches_catalog():
    res = _client().get("/api/models")
    assert res.status_code == 200
    models = res.json()
    assert len(models) == 4
    assert models[0] == {
        "id": "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B",
        "name": "Nemotron-3 Nano (30B)",
        "tier": "efficient",
        "inputPricePerM": 0.06,
        "outputPricePerM": 0.24,
        "description": "Lightweight & ultra-low latency, ideal for extraction & categorization",
        "badgeColor": "emerald",
    }


def test_cors_allows_vite_origin():
    res = _client().options(
        "/api/health",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"},
    )
    assert res.status_code == 200
    assert res.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_cors_rejects_unknown_origin():
    res = _client().options(
        "/api/health",
        headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "GET"},
    )
    assert "access-control-allow-origin" not in res.headers


def test_explicit_settings_override_routes():
    import dataclasses

    from backend.config import load_settings

    s = dataclasses.replace(load_settings(), environment="production", data_source_mode="recorded")
    body = TestClient(create_app(s), base_url="http://localhost").get("/api/health").json()
    assert (body["environment"], body["data_source"]) == ("production", "recorded")


def test_importing_main_does_not_build_app(monkeypatch):
    import importlib

    import backend.main as main

    monkeypatch.setenv("PORT", "abc")  # would raise if config were read at import
    importlib.reload(main)
    assert "app" not in vars(main)
    monkeypatch.delenv("PORT")
    assert main.app is main.app  # built lazily, once
    with pytest.raises(AttributeError):
        main.not_there
