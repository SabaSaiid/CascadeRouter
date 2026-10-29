"""Common types for anything that can answer a chat completion request."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any, Optional, Protocol


class LLMError(RuntimeError):
    """A completion could not be produced (timeout, HTTP error, missing recording)."""


@dataclass(frozen=True)
class CompletionResult:
    text: str
    input_tokens: int
    output_tokens: int
    usage_reported: bool  # False -> token counts are estimates
    total_latency_ms: float
    time_to_first_token_ms: Optional[float]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CompletionResult":
        return cls(
            text=str(data["text"]),
            input_tokens=int(data["input_tokens"]),
            output_tokens=int(data["output_tokens"]),
            usage_reported=bool(data["usage_reported"]),
            total_latency_ms=float(data["total_latency_ms"]),
            time_to_first_token_ms=(
                None if data.get("time_to_first_token_ms") is None else float(data["time_to_first_token_ms"])
            ),
        )


class LLMClient(Protocol):
    async def complete(
        self, model: str, messages: list[dict[str, Any]], params: dict[str, Any]
    ) -> CompletionResult: ...


def request_key(model: str, messages: list[dict[str, Any]], params: dict[str, Any]) -> str:
    """Stable identity of a request, used to store and look up recordings."""
    canonical = json.dumps(
        {"model": model, "messages": messages, "params": params},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
