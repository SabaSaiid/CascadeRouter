"""Record real Nebius responses and replay them ("recorded" data source).

Recordings are written only from genuine live calls, one JSON file per request
key, so a replay shows exactly what a real run measured.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.services.llm import CompletionResult, LLMClient, LLMError, request_key

_KEY_RE = re.compile(r"^[0-9a-f]{64}$")


class RecordingStore:
    def __init__(self, directory: Path):
        self.directory = directory

    def _path(self, key: str) -> Path:
        if not _KEY_RE.match(key):
            raise ValueError("invalid recording key")
        return self.directory / f"{key}.json"

    def get(self, key: str) -> CompletionResult | None:
        path = self._path(key)
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return CompletionResult.from_dict(data["result"])
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise LLMError(f"recording {path.name} is corrupt: {exc}") from exc

    def put(self, key: str, model: str, result: CompletionResult) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        payload = {
            "model": model,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "result": result.to_dict(),
        }
        # Atomic write so concurrent runs never leave a half-written file.
        fd, tmp = tempfile.mkstemp(dir=self.directory, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2, ensure_ascii=False)
            os.replace(tmp, self._path(key))
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise


class RecordingClient:
    """Replays recordings; never fabricates a result when one is missing."""

    def __init__(self, store: RecordingStore):
        self._store = store

    async def complete(
        self, model: str, messages: list[dict[str, Any]], params: dict[str, Any]
    ) -> CompletionResult:
        result = self._store.get(request_key(model, messages, params))
        if result is None:
            raise LLMError(f"{model}: no recording for this request; run once in live mode with RECORD_RUNS=true")
        return result


class RecordingWriter:
    """Wraps a live client and saves every successful response."""

    def __init__(self, inner: LLMClient, store: RecordingStore):
        self._inner = inner
        self._store = store

    async def complete(
        self, model: str, messages: list[dict[str, Any]], params: dict[str, Any]
    ) -> CompletionResult:
        result = await self._inner.complete(model, messages, params)
        self._store.put(request_key(model, messages, params), model, result)
        return result
