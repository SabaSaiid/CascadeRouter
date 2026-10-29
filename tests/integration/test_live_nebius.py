"""Optional live smoke test against Nebius Token Factory.

Skipped unless NEBIUS_LIVE_TEST_KEY is set (deliberately not NEBIUS_API_KEY,
so CI and local runs never spend money by accident). Run with:
    NEBIUS_LIVE_TEST_KEY=sk-... pytest -m live tests/integration/test_live_nebius.py
"""

import os

import pytest

from backend.config import load_settings
from backend.services.nebius_client import NebiusClient

KEY = os.environ.get("NEBIUS_LIVE_TEST_KEY")


@pytest.mark.live
@pytest.mark.skipif(not KEY, reason="NEBIUS_LIVE_TEST_KEY not set")
async def test_nano_answers_with_usage_and_ttft():
    s = load_settings()
    client = NebiusClient(KEY, s.nebius_base_url, timeout=60)
    r = await client.complete(s.models[0].id, [{"role": "user", "content": "Reply with the word OK."}], {"max_tokens": 16})
    assert r.text.strip()
    assert r.usage_reported and r.input_tokens > 0 and r.output_tokens > 0
    assert r.time_to_first_token_ms is not None
