from types import SimpleNamespace

import httpx
import openai
import pytest

from backend.services.llm import LLMError
from backend.services.nebius_client import NebiusClient


def _chunk(content=None, usage=None, choices=True):
    choice = SimpleNamespace(delta=SimpleNamespace(content=content))
    return SimpleNamespace(choices=[choice] if choices else [], usage=usage)


class FakeStream:
    def __init__(self, chunks):
        self._chunks = chunks

    def __aiter__(self):
        self._it = iter(self._chunks)
        return self

    async def __anext__(self):
        try:
            return next(self._it)
        except StopIteration:
            raise StopAsyncIteration


class FakeAsyncOpenAI:
    def __init__(self, chunks=None, exc=None):
        self.calls = []
        self._chunks, self._exc = chunks or [], exc
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs):
        self.calls.append(kwargs)
        if self._exc:
            raise self._exc
        return FakeStream(self._chunks)


def _client(fake):
    return NebiusClient("sk-test", "https://example.invalid/v1", timeout=5, client=fake)


async def test_streams_text_usage_and_ttft():
    usage = SimpleNamespace(prompt_tokens=12, completion_tokens=3)
    fake = FakeAsyncOpenAI([_chunk(None), _chunk("Hel"), _chunk("lo"), _chunk(choices=False, usage=usage)])
    r = await _client(fake).complete("m", [{"role": "user", "content": "hi"}], {"temperature": 0})
    assert r.text == "Hello"
    assert (r.input_tokens, r.output_tokens, r.usage_reported) == (12, 3, True)
    assert r.time_to_first_token_ms is not None and r.total_latency_ms >= r.time_to_first_token_ms >= 0
    sent = fake.calls[0]
    assert sent["stream"] is True and sent["stream_options"] == {"include_usage": True}
    assert sent["model"] == "m" and sent["temperature"] == 0


async def test_missing_usage_is_estimated():
    fake = FakeAsyncOpenAI([_chunk("abcdefgh")])
    r = await _client(fake).complete("m", [{"role": "user", "content": "abcd"}], {})
    assert (r.input_tokens, r.output_tokens, r.usage_reported) == (1, 2, False)


async def test_empty_output_has_no_ttft():
    r = await _client(FakeAsyncOpenAI([_chunk(None)])).complete("m", [{"role": "user", "content": "x"}], {})
    assert r.text == "" and r.time_to_first_token_ms is None


def _request():
    return httpx.Request("POST", "https://example.invalid/v1/chat/completions")


@pytest.mark.parametrize(
    "exc,expected",
    [
        (openai.APITimeoutError(request=_request()), "m: request timed out after 5s"),
        (openai.APIConnectionError(request=_request()), "m: connection error"),
        (openai.APIStatusError("bad model", response=httpx.Response(404, request=_request()), body=None), "m: HTTP 404: bad model"),
    ],
)
async def test_errors_become_llm_errors(exc, expected):
    with pytest.raises(LLMError, match=expected):
        await _client(FakeAsyncOpenAI(exc=exc)).complete("m", [{"role": "user", "content": "x"}], {})


def test_requires_api_key():
    with pytest.raises(LLMError, match="not configured"):
        NebiusClient("", "https://x", timeout=5)


def test_builds_real_sdk_client_without_network():
    c = NebiusClient("sk-test", "https://example.invalid/v1", timeout=7)
    assert isinstance(c._client, openai.AsyncOpenAI)
