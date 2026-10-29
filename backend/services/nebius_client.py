"""Live client for NVIDIA Nemotron models on Nebius Token Factory (OpenAI-compatible)."""

from __future__ import annotations

import time
from typing import Any, Optional

import openai
from openai import AsyncOpenAI

from backend.compiler.metrics import estimate_tokens
from backend.services.llm import CompletionResult, LLMError


def _prompt_text(messages: list[dict[str, Any]]) -> str:
    parts = []
    for message in messages:
        content = message.get("content")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            parts.extend(p.get("text", "") for p in content if isinstance(p, dict))
    return "\n".join(parts)


class NebiusClient:
    """Streams completions to measure time-to-first-token and exact usage."""

    def __init__(self, api_key: str, base_url: str, timeout: float, client: Optional[AsyncOpenAI] = None):
        if not api_key:
            raise LLMError("NEBIUS_API_KEY is not configured")
        self._timeout = timeout
        self._client = client or AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=timeout, max_retries=1)

    async def complete(
        self, model: str, messages: list[dict[str, Any]], params: dict[str, Any]
    ) -> CompletionResult:
        start = time.perf_counter()
        first_token_at: Optional[float] = None
        chunks: list[str] = []
        usage = None
        try:
            stream = await self._client.chat.completions.create(
                model=model,
                messages=messages,
                stream=True,
                stream_options={"include_usage": True},
                **params,
            )
            async for chunk in stream:
                if chunk.usage is not None:
                    usage = chunk.usage
                for choice in chunk.choices or []:
                    delta = getattr(choice.delta, "content", None)
                    if delta:
                        if first_token_at is None:
                            first_token_at = time.perf_counter()
                        chunks.append(delta)
        except openai.APITimeoutError as exc:
            raise LLMError(f"{model}: request timed out after {self._timeout:g}s") from exc
        except openai.APIStatusError as exc:
            raise LLMError(f"{model}: HTTP {exc.status_code}: {_short(exc.message)}") from exc
        except openai.APIConnectionError as exc:
            raise LLMError(f"{model}: connection error: {_short(str(exc))}") from exc

        end = time.perf_counter()
        text = "".join(chunks)
        if usage is not None and usage.prompt_tokens is not None and usage.completion_tokens is not None:
            input_tokens, output_tokens, reported = usage.prompt_tokens, usage.completion_tokens, True
        else:
            input_tokens = estimate_tokens(_prompt_text(messages))
            output_tokens = estimate_tokens(text)
            reported = False
        return CompletionResult(
            text=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            usage_reported=reported,
            total_latency_ms=round((end - start) * 1000, 1),
            time_to_first_token_ms=(
                round((first_token_at - start) * 1000, 1) if first_token_at is not None else None
            ),
        )


def _short(message: str, limit: int = 200) -> str:
    message = " ".join(str(message).split())
    return message if len(message) <= limit else message[: limit - 1] + "…"
