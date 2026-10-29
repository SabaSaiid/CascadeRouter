"""Operational guardrails for the hosted demo: rate limit, spend cap, request limits."""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from backend.compiler.metrics import estimate_cost
from backend.config import Settings
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
    """Running USD spend on live calls, reset at UTC midnight."""

    def __init__(self, cap_usd: float, today: Callable[[], str] | None = None):
        self.cap_usd = cap_usd
        self._today = today or (lambda: datetime.now(timezone.utc).date().isoformat())
        self._day = self._today()
        self._spent = 0.0
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
        return max(0.0, self.cap_usd - self.spent_usd)

    def exhausted(self) -> bool:
        return self.remaining_usd() <= 0.0

    def add(self, amount: float) -> None:
        if amount < 0:
            raise ValueError("spend cannot be negative")
        with self._lock:
            self._roll()
            self._spent += amount


class SpendCappedClient:
    """Refuses live calls once the daily cap is reached; records the real cost of each call."""

    def __init__(self, inner: LLMClient, tracker: SpendTracker, settings: Settings):
        self._inner = inner
        self._tracker = tracker
        self._settings = settings

    async def complete(self, model: str, messages: list[dict[str, Any]], params: dict[str, Any]) -> CompletionResult:
        if self._tracker.exhausted():
            raise LLMError(f"{model}: daily spend cap of ${self._tracker.cap_usd:.2f} reached")
        result = await self._inner.complete(model, messages, params)
        spec = self._settings.model_by_id(model)
        if spec is not None:
            self._tracker.add(estimate_cost(spec, result.input_tokens, result.output_tokens))
        return result


def _client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


class GuardrailMiddleware(BaseHTTPMiddleware):
    """Rejects oversized bodies (413) and rate-limited clients (429)."""

    def __init__(self, app: Any, limiter: Optional[RateLimiter], max_body_bytes: int = MAX_BODY_BYTES):
        super().__init__(app)
        self.limiter = limiter
        self.max_body_bytes = max_body_bytes

    async def dispatch(self, request: Request, call_next: Callable[[Request], Any]) -> Response:
        length = request.headers.get("content-length")
        if length is not None:
            try:
                too_big = int(length) > self.max_body_bytes
            except ValueError:
                return JSONResponse({"detail": "invalid Content-Length"}, status_code=400)
            if too_big:
                return JSONResponse({"detail": "request body too large"}, status_code=413)
        elif request.method in ("POST", "PUT", "PATCH"):
            body = await request.body()  # chunked body: bounded check after read
            if len(body) > self.max_body_bytes:
                return JSONResponse({"detail": "request body too large"}, status_code=413)
        if (
            self.limiter is not None
            and request.method != "OPTIONS"
            and request.url.path not in EXEMPT_PATHS
            and not self.limiter.allow(_client_key(request))
        ):
            return JSONResponse(
                {"detail": "rate limit exceeded; try again shortly"},
                status_code=429,
                headers={"Retry-After": "1"},
            )
        return await call_next(request)
