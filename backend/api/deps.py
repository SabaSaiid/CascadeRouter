"""Process-wide singletons injected into route handlers (overridable in tests)."""

from __future__ import annotations

from functools import lru_cache

from fastapi import Depends

from backend.config import Settings, get_settings
from backend.guardrails import SpendCappedClient, SpendTracker
from backend.services.llm import LLMClient, LLMError
from backend.services.nebius_client import NebiusClient
from backend.services.recordings import RecordingClient, RecordingStore, RecordingWriter
from backend.store import RunStore, ScanStore


@lru_cache(maxsize=1)
def get_scan_store() -> ScanStore:
    return ScanStore()


@lru_cache(maxsize=1)
def get_run_store() -> RunStore:
    return RunStore()


@lru_cache(maxsize=8)
def _tracker_for_cap(cap_usd: float) -> SpendTracker:
    return SpendTracker(cap_usd)


def get_spend_tracker(settings: Settings = Depends(get_settings)) -> SpendTracker:
    """One process-wide tracker per configured cap (honours explicit Settings)."""
    return _tracker_for_cap(settings.daily_spend_cap_usd)


def effective_mode(settings: Settings) -> str:
    """'mock' is a frontend-only mode: the backend serves real recordings instead."""
    return "recorded" if settings.data_source_mode in ("recorded", "mock") else "live"


def build_llm_client(settings: Settings, tracker: SpendTracker) -> LLMClient:
    """Client for the configured data source. Raises LLMError when live mode has no key."""
    store = RecordingStore(settings.recordings_dir)
    if effective_mode(settings) == "recorded":
        return RecordingClient(store)
    if not settings.nebius_configured:
        raise LLMError("NEBIUS_API_KEY is not configured; set it or use DATA_SOURCE_MODE=recorded")
    client: LLMClient = SpendCappedClient(
        NebiusClient(settings.nebius_api_key, settings.nebius_base_url, settings.benchmark_timeout_seconds),
        tracker,
        settings,
    )
    if settings.record_runs:
        client = RecordingWriter(client, store)
    return client


def get_llm_client_factory():
    """Dependency returning a factory, so tests can inject a fake client."""
    return build_llm_client
