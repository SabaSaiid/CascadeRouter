"""Operational guardrails for the hosted demo: rate limit, spend cap, request limits."""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable, Optional


from backend.compiler.metrics import estimate_cost
from backend.compiler.prompt_capture import DEFAULT_MAX_OUTPUT_TOKENS
from backend.config import ModelSpec, Settings
from backend.services.llm import CompletionResult, LLMClient, LLMError

MAX_BODY_BYTES = 64 * 1024
EXEMPT_PATHS = frozenset({"/api/health"})


class RateLimiter:
    """Token bucket per client key (e.g. IP): `per_minute` requests, refilled continuously."""

    def __init__(self, per_minute: int, clock: Callable[[], float] = time.monotonic, max_keys: int = 10_000):
        self.capacity = float(per_minute)
        self.rate = per_minute / 60.0
        self._clock = clock
        self._buckets: dict[str, tuple[float, float]] = {}
        self._lock = threading.Lock()
        self._max_keys = max_keys

    def allow(self, key: str) -> bool:
        now = self._clock()
        with self._lock:
            tokens, last = self._buckets.get(key, (self.capacity, now))
            tokens = min(self.capacity, tokens + (now - last) * self.rate)
            allowed = tokens >= 1.0
            if allowed:
                tokens -= 1.0
            if key not in self._buckets and len(self._buckets) >= self._max_keys:
                # Drop the stalest bucket so memory stays bounded.
                oldest = min(self._buckets, key=lambda k: self._buckets[k][1])
                del self._buckets[oldest]
            self._buckets[key] = (tokens, now)
            return allowed


class SpendTracker:
    """USD spend on live calls, reset at UTC midnight.

    Calls reserve a worst-case cost *before* they start (under the lock), so
    concurrent calls can never jointly overshoot the cap; the reservation is
    settled to the real cost afterwards.
    """

    def __init__(self, cap_usd: float, today: Callable[[], str] | None = None):
        self.cap_usd = cap_usd
        self._today = today or (lambda: datetime.now(timezone.utc).date().isoformat())
        self._day = self._today()
        self._spent = 0.0
        self._reserved = 0.0
        self._lock = threading.Lock()

    def _roll(self) -> None:
        day = self._today()
        if day != self._day:
            self._day, self._spent = day, 0.0

    @property
    def spent_usd(self) -> float:
        with self._lock:
            self._roll()
            return self._spent

    def remaining_usd(self) -> float:
        with self._lock:
            self._roll()
            return max(0.0, self.cap_usd - self._spent - self._reserved)

    def exhausted(self) -> bool:
        return self.remaining_usd() <= 0.0

    def add(self, amount: float) -> None:
        if amount < 0:
            raise ValueError("spend cannot be negative")
        with self._lock:
            self._roll()
            self._spent += amount

    def reserve(self, amount: float) -> bool:
        """Atomically reserve `amount`; False if it would exceed the cap."""
        if amount < 0:
            raise ValueError("reservation cannot be negative")
        with self._lock:
            self._roll()
            if self._spent + self._reserved + amount > self.cap_usd:
                return False
            self._reserved += amount
            return True

    def settle(self, reserved: float, actual: float) -> None:
        """Release a reservation and record what was actually spent."""
        with self._lock:
            self._roll()
            self._reserved = max(0.0, self._reserved - reserved)
            self._spent += max(0.0, actual)


def worst_case_cost(spec: ModelSpec, messages: list[dict[str, Any]], params: dict[str, Any]) -> float:
    """Upper bound for one call: every prompt character counted as a token, plus full max_tokens."""
    prompt_chars = sum(len(str(m.get("content", ""))) for m in messages)
    input_upper = prompt_chars + 16 * len(messages)
    output_upper = params.get("max_tokens") or params.get("max_completion_tokens") or DEFAULT_MAX_OUTPUT_TOKENS
    return estimate_cost(spec, input_upper, int(output_upper))


class SpendCappedClient:
    """Reserves worst-case cost before each live call; settles to the real cost after.

    A call that fails or is cancelled (e.g. by a timeout) is charged its full
    reservation, because the provider may still have generated tokens.
    """

    def __init__(self, inner: LLMClient, tracker: SpendTracker, settings: Settings):
        self._inner = inner
        self._tracker = tracker
        self._settings = settings

    async def complete(self, model: str, messages: list[dict[str, Any]], params: dict[str, Any]) -> CompletionResult:
        spec = self._settings.model_by_id(model)
        if spec is None:
            raise LLMError(f"{model}: not in the priced model catalog; refusing an uncapped call")
        reservation = worst_case_cost(spec, messages, params)
        if not self._tracker.reserve(reservation):
            raise LLMError(f"{model}: daily spend cap of ${self._tracker.cap_usd:.2f} reached")
        try:
            result = await self._inner.complete(model, messages, params)
        except BaseException:
            self._tracker.settle(reservation, reservation)
            raise
        self._tracker.settle(reservation, estimate_cost(spec, result.input_tokens, result.output_tokens))
        return result


async def _send_json(send: Callable, status: int, detail: str, headers: Optional[list] = None) -> None:
    body = json.dumps({"detail": detail}).encode()
    await send({
        "type": "http.response.start",
        "status": status,
        "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]
        + (headers or []),
    })
    await send({"type": "http.response.body", "body": body})


class GuardrailMiddleware:
    """Pure ASGI middleware: rate limit first (429), then bound the request body (413).

    The body limit is enforced while the body streams in, so chunked requests
    without Content-Length can never make the server buffer more than the limit.
    """

    def __init__(self, app: Any, limiter: Optional[RateLimiter], max_body_bytes: int = MAX_BODY_BYTES):
        self.app = app
        self.limiter = limiter
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope: dict, receive: Callable, send: Callable) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        client = scope.get("client")
        key = client[0] if client else "unknown"
        if (
            self.limiter is not None
            and scope.get("method") != "OPTIONS"
            and scope.get("path") not in EXEMPT_PATHS
            and not self.limiter.allow(key)
        ):
            await _send_json(send, 429, "rate limit exceeded; try again shortly", [(b"retry-after", b"1")])
            return

        headers = dict(scope.get("headers") or [])
        length = headers.get(b"content-length")
        if length is not None:
            try:
                declared = int(length)
            except ValueError:
                await _send_json(send, 400, "invalid Content-Length")
                return
            if declared > self.max_body_bytes:
                await _send_json(send, 413, "request body too large")
                return

        received = 0
        too_large = False

        async def limited_receive() -> dict:
            nonlocal received, too_large
            if too_large:
                return {"type": "http.disconnect"}
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_body_bytes:
                    # Stop reading; the app sees a disconnect and its response is replaced below.
                    too_large = True
                    return {"type": "http.disconnect"}
            return message

        started = False

        async def guarded_send(message: dict) -> None:
            nonlocal started
            if not too_large:
                started = started or message["type"] == "http.response.start"
                await send(message)

        try:
            await self.app(scope, limited_receive, guarded_send)
        except Exception:
            if not too_large:
                raise
        if too_large and not started:
            await _send_json(send, 413, "request body too large")
