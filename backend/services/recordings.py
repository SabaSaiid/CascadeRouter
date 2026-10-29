"""Record real Nebius responses and replay them ("recorded" data source).

Recordings are written only from genuine live calls, one JSON file per request
key, so a replay shows exactly what a real run measured.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.services.llm import CompletionResult, LLMClient, LLMError, request_key

_KEY_RE = re.compile(r"^[0-9a-f]{64}$")


class RecordingStore:
    """One JSON file per request key holding every recorded response, in order."""

    def __init__(self, directory: Path):
        self.directory = directory
        self._lock = threading.Lock()

    def _path(self, key: str) -> Path:
        if not _KEY_RE.match(key):
            raise ValueError("invalid recording key")
        return self.directory / f"{key}.json"

    def _load(self, path: Path) -> list[dict[str, Any]]:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data.get("responses"), list):
            return data["responses"]
        return [{"result": data["result"], "recorded_at": data.get("recorded_at")}]  # single-response format

    def count(self, key: str) -> int:
        path = self._path(key)
        if not path.is_file():
            return 0
        try:
            return len(self._load(path))
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
            raise LLMError(f"recording {path.name} is corrupt: {exc}") from exc

    def get(self, key: str, index: int = 0) -> CompletionResult | None:
        path = self._path(key)
        if not path.is_file():
            return None
        try:
            responses = self._load(path)
            if not responses:
                return None
            # Replays beyond what was recorded reuse the last real response.
            return CompletionResult.from_dict(responses[min(index, len(responses) - 1)]["result"])
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
            raise LLMError(f"recording {path.name} is corrupt: {exc}") from exc

    def put(self, key: str, model: str, result: CompletionResult) -> None:
        with self._lock:
            self.directory.mkdir(parents=True, exist_ok=True)
            path = self._path(key)
            responses: list[dict[str, Any]] = []
            if path.is_file():
                try:
                    responses = self._load(path)
                except (OSError, ValueError, KeyError, TypeError, AttributeError):
                    responses = []  # replace a corrupt file with fresh real data
            responses.append({"recorded_at": datetime.now(timezone.utc).isoformat(), "result": result.to_dict()})
            payload = {"model": model, "responses": responses}
            # Atomic write so concurrent runs never leave a half-written file.
            fd, tmp = tempfile.mkstemp(dir=self.directory, suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    json.dump(payload, fh, indent=2, ensure_ascii=False)
                os.replace(tmp, path)
            except BaseException:
                Path(tmp).unlink(missing_ok=True)
                raise


class RecordingClient:
    """Replays recordings in recorded order; never fabricates a result when one is missing."""

    def __init__(self, store: RecordingStore):
        self._store = store
        self._seen: dict[str, int] = {}

    async def complete(
        self, model: str, messages: list[dict[str, Any]], params: dict[str, Any]
    ) -> CompletionResult:
        key = request_key(model, messages, params)
        index = self._seen.get(key, 0)
        self._seen[key] = index + 1
        result = self._store.get(key, index)
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
