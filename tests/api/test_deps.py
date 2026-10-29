import dataclasses

import pytest

from backend.api.deps import build_llm_client, effective_mode
from backend.config import load_settings
from backend.guardrails import SpendCappedClient, SpendTracker
from backend.services.llm import LLMError
from backend.services.recordings import RecordingClient, RecordingWriter


def settings(**over):
    return dataclasses.replace(load_settings(), **over)


@pytest.mark.parametrize("mode,expected", [("live", "live"), ("recorded", "recorded"), ("mock", "recorded")])
def test_effective_mode(mode, expected):
    assert effective_mode(settings(data_source_mode=mode)) == expected


def test_recorded_and_mock_use_replay(tmp_path):
    for mode in ("recorded", "mock"):
        c = build_llm_client(settings(data_source_mode=mode, recordings_dir=tmp_path), SpendTracker(1))
        assert isinstance(c, RecordingClient)


def test_live_requires_key():
    with pytest.raises(LLMError, match="NEBIUS_API_KEY"):
        build_llm_client(settings(data_source_mode="live", nebius_api_key=""), SpendTracker(1))


def test_live_is_spend_capped_and_optionally_recorded(tmp_path):
    s = settings(data_source_mode="live", nebius_api_key="sk-x", recordings_dir=tmp_path)
    assert isinstance(build_llm_client(s, SpendTracker(1)), SpendCappedClient)
    assert isinstance(build_llm_client(dataclasses.replace(s, record_runs=True), SpendTracker(1)), RecordingWriter)
