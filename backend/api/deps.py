"""Process-wide singletons injected into route handlers (overridable in tests)."""

from __future__ import annotations

from functools import lru_cache

from backend.store import ScanStore


@lru_cache(maxsize=1)
def get_scan_store() -> ScanStore:
    return ScanStore()
