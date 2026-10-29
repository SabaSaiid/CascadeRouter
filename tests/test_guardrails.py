import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.config import load_settings
from backend.guardrails import GuardrailMiddleware, RateLimiter, SpendCappedClient, SpendTracker
from backend.services.llm import CompletionResult, LLMError

S = load_settings()


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def test_rate_limiter_bucket_and_refill():
    clock = Clock()
    rl = RateLimiter(per_minute=3, clock=clock)
    assert [rl.allow("a") for _ in range(4)] == [True, True, True, False]
    assert rl.allow("b")  # independent keys
    clock.t += 20  # one token per 20s
    assert rl.allow("a") and not rl.allow("a")
    clock.t += 600
    assert sum(rl.allow("a") for _ in range(10)) == 3  # never exceeds capacity


def test_rate_limiter_bounds_memory():
    clock = Clock()
    rl = RateLimiter(per_minute=1, clock=clock, max_keys=3)
    for i in range(10):
        clock.t += 1
        rl.allow(f"ip{i}")
    assert len(rl._buckets) == 3


def test_spend_tracker_rolls_over_daily():
    day = {"d": "2026-10-29"}
    t = SpendTracker(1.0, today=lambda: day["d"])
    t.add(0.4)
    t.add(0.6)
    assert t.spent_usd == pytest.approx(1.0) and t.exhausted() and t.remaining_usd() == 0
    day["d"] = "2026-10-30"
    assert t.spent_usd == 0 and not t.exhausted()
    with pytest.raises(ValueError):
        t.add(-1)


class Inner:
    def __init__(self):
        self.calls = 0

    async def complete(self, model, messages, params):
        self.calls += 1
        return CompletionResult("x", 1_000_000, 0, True, 1.0, None)


async def test_spend_capped_client_records_real_cost_and_blocks():
    tracker = SpendTracker(1.0)
    inner = Inner()
    client = SpendCappedClient(inner, tracker, S)
    ultra = S.powerful_model.id
    await client.complete(ultra, [], {})  # 1M input tokens on Ultra = $1.00
    assert tracker.spent_usd == pytest.approx(1.0)
    with pytest.raises(LLMError, match="daily spend cap"):
        await client.complete(ultra, [], {})
    assert inner.calls == 1


async def test_unknown_model_cost_not_tracked():
    tracker = SpendTracker(1.0)
    await SpendCappedClient(Inner(), tracker, S).complete("acme/other", [], {})
    assert tracker.spent_usd == 0


def _app(limiter=None, max_body=100):
    app = FastAPI()
    app.add_middleware(GuardrailMiddleware, limiter=limiter, max_body_bytes=max_body)

    @app.post("/api/echo")
    async def echo(body: dict):
        return body

    @app.get("/api/health")
    async def health():
        return {"ok": True}

    return TestClient(app)


def test_body_size_limit():
    c = _app()
    assert c.post("/api/echo", json={"a": "x"}).status_code == 200
    assert c.post("/api/echo", json={"a": "x" * 200}).status_code == 413
    assert c.post("/api/echo", content=b"{}", headers={"content-length": "abc", "content-type": "application/json"}).status_code == 400


def test_chunked_body_limit():
    c = _app()

    def gen():
        yield b'{"a": "' + b"x" * 300 + b'"}'

    assert c.post("/api/echo", content=gen(), headers={"content-type": "application/json"}).status_code == 413


def test_rate_limit_middleware_exempts_health():
    clock = Clock()
    c = _app(RateLimiter(per_minute=1, clock=clock))
    assert c.post("/api/echo", json={}).status_code == 200
    r = c.post("/api/echo", json={})
    assert r.status_code == 429 and r.headers["retry-after"] == "1"
    assert all(c.get("/api/health").status_code == 200 for _ in range(5))
