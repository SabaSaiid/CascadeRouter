"""Capture the exact request a node sends, by running it once in the sandbox.

The node's function is called with each case's `vars` and a capturing test
double in place of the OpenAI client. When the target call site is reached the
request kwargs (messages, response_format, max_tokens, ...) are recorded and
execution is aborted. No credentials are present and no network call is made.
"""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from backend.compiler.ast_scanner import DiscoveredCall
from backend.compiler.cases import BenchmarkCase
from backend.compiler.sandbox import run_python, sandbox_copy

HARNESS_FILENAME = "_cascade_capture_harness.py"
RESULT_MARKER = "__CASCADE_CAPTURE_RESULT__"
# Request parameters never forwarded to the benchmark (the runner sets its own).
DROPPED_PARAMS = frozenset({"model", "stream", "stream_options", "n", "extra_headers", "extra_body"})
# Only these generation parameters are forwarded to Nebius; anything else the
# (untrusted) target code passed is ignored.
FORWARDED_PARAMS = frozenset(
    {"temperature", "top_p", "max_tokens", "max_completion_tokens", "response_format", "stop",
     "seed", "presence_penalty", "frequency_penalty"}
)
DEFAULT_MAX_OUTPUT_TOKENS = 2048
MAX_MESSAGES = 64
MAX_REQUEST_CHARS = 200_000
_ROLES = {"system", "user", "assistant", "developer"}

HARNESS_SOURCE = r'''
import asyncio, inspect, json, os, sys, types

MARKER = "__CASCADE_CAPTURE_RESULT__"
NONCE = ""


class _Captured(BaseException):
    """BaseException so `except Exception` in target code cannot swallow it."""


class _Unexpected(BaseException):
    pass


def _make_fake(state):
    def capture(kind):
        def create(*args, **kwargs):
            frame = sys._getframe(1)
            while frame is not None:
                fname = os.path.realpath(frame.f_code.co_filename)
                if fname == state["file"] and state["start"] <= frame.f_lineno <= state["end"]:
                    if kind != "chat":
                        raise _Unexpected(f"only chat.completions calls can be benchmarked (got {kind})")
                    state["request"] = kwargs
                    raise _Captured()
                frame = frame.f_back
            raise _Unexpected("another LLM call ran before the node's call site")
        return create

    ns = types.SimpleNamespace
    fake = ns(
        chat=ns(completions=ns(create=capture("chat"))),
        completions=ns(create=capture("completions")),
        responses=ns(create=capture("responses")),
    )
    return fake


def _install_openai_stub(fake):
    def factory(*a, **k):
        return fake
    try:
        import openai
    except ImportError:
        openai = types.ModuleType("openai")
        sys.modules["openai"] = openai
    for name in ("OpenAI", "AsyncOpenAI", "AzureOpenAI", "AsyncAzureOpenAI"):
        setattr(openai, name, factory)


def _json_safe(kwargs, dropped):
    safe, skipped = {}, []
    for key, value in kwargs.items():
        if key in dropped:
            continue
        try:
            json.dumps(value)
        except (TypeError, ValueError):
            skipped.append(key)
            continue
        safe[key] = value
    return safe, skipped


def main():
    global NONCE
    job = json.loads(sys.stdin.read())
    NONCE = job.pop("nonce")
    root = os.path.realpath(os.getcwd())
    sys.path.insert(0, root)
    state = {
        "file": os.path.realpath(os.path.join(root, job["file"])),
        "start": job["start_line"],
        "end": job["end_line"],
    }
    fake = _make_fake(state)
    _install_openai_stub(fake)
    results = []
    try:
        import importlib
        module = importlib.import_module(job["module"])
    except BaseException as exc:
        err = f"import failed: {type(exc).__name__}: {exc}"
        results = [{"ok": False, "error": err} for _ in job["cases"]]
        print(MARKER + NONCE + json.dumps(results))
        return
    if hasattr(module, "client"):
        module.client = fake
    func = getattr(module, job["function"], None)
    if not callable(func):
        results = [{"ok": False, "error": f"function {job['function']} not found at module level"} for _ in job["cases"]]
        print(MARKER + NONCE + json.dumps(results))
        return
    try:
        params = inspect.signature(func).parameters
    except (TypeError, ValueError):
        params = {}
    for case_vars in job["cases"]:
        state.pop("request", None)
        kwargs = dict(case_vars)
        if "client" in params:
            kwargs["client"] = fake
        try:
            out = func(**kwargs)
            if inspect.isawaitable(out):
                asyncio.run(out)
            results.append({"ok": False, "error": "the node's LLM call was not reached"})
        except _Captured:
            safe, skipped = _json_safe(state["request"], set(job["dropped"]))
            if not isinstance(safe.get("messages"), list) or not safe["messages"]:
                results.append({"ok": False, "error": "captured call has no messages list"})
            else:
                results.append({"ok": True, "request": safe, "skipped": skipped})
        except _Unexpected as exc:
            results.append({"ok": False, "error": str(exc)})
        except BaseException as exc:
            results.append({"ok": False, "error": f"{type(exc).__name__}: {exc}"})
    print(MARKER + NONCE + json.dumps(results))


main()
'''


@dataclass(frozen=True)
class CapturedRequest:
    messages: list[dict[str, Any]]
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CaptureResult:
    request: Optional[CapturedRequest]
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.request is not None


def module_name(rel_path: str) -> str:
    parts = Path(rel_path).with_suffix("").parts
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    if not parts or not all(p.isidentifier() for p in parts):
        raise ValueError(f"cannot import {rel_path!r} as a module")
    return ".".join(parts)


def capture_requests(
    repo_root: Path,
    call: DiscoveredCall,
    cases: list[BenchmarkCase],
    timeout: float,
) -> list[CaptureResult]:
    """One CaptureResult per case, in order."""
    if not cases:
        return []
    if not call.function_name:
        return [CaptureResult(None, "module-level calls cannot be benchmarked")] * len(cases)
    try:
        module = module_name(call.file_path)
    except ValueError as exc:
        return [CaptureResult(None, str(exc))] * len(cases)

    job = {
        "module": module,
        "function": call.function_name,
        "file": call.file_path,
        "start_line": call.line_number,
        "end_line": call.end_line_number,
        "cases": [c.vars for c in cases],
        "dropped": sorted(DROPPED_PARAMS),
        # Read by the harness before any target code is imported; a result line
        # without it (e.g. printed by the target itself) is ignored.
        "nonce": secrets.token_hex(16),
    }
    with sandbox_copy(repo_root, prefix="cascade_capture_") as work:
        (work / HARNESS_FILENAME).write_text(HARNESS_SOURCE, encoding="utf-8")
        proc = run_python([HARNESS_FILENAME], cwd=work, timeout=timeout, stdin=json.dumps(job))

    if proc.timed_out:
        return [CaptureResult(None, f"prompt capture timed out after {timeout:g}s")] * len(cases)
    return parse_harness_output(proc.stdout, proc.stderr, len(cases), job["nonce"])


def sanitize_request(
    messages: Any, params: dict[str, Any], max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS
) -> tuple[Optional[CapturedRequest], Optional[str]]:
    """Validate a captured request before it is sent to a paid API."""
    if not isinstance(messages, list) or not 0 < len(messages) <= MAX_MESSAGES:
        return None, f"captured messages must be a list of 1-{MAX_MESSAGES} items"
    clean_messages = []
    for m in messages:
        if not isinstance(m, dict) or m.get("role") not in _ROLES or not isinstance(m.get("content"), str):
            return None, "captured messages must be {role, content: str} objects"
        clean_messages.append({"role": m["role"], "content": m["content"]})
    clean = {k: v for k, v in params.items() if k in FORWARDED_PARAMS}
    for key in ("max_tokens", "max_completion_tokens"):
        value = clean.get(key)
        if value is not None:
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                return None, f"captured {key} must be a positive integer"
            clean[key] = min(value, max_output_tokens)
    if "max_tokens" not in clean and "max_completion_tokens" not in clean:
        clean["max_tokens"] = max_output_tokens
    size = len(json.dumps({"m": clean_messages, "p": clean}))
    if size > MAX_REQUEST_CHARS:
        return None, f"captured request is too large ({size} chars)"
    return CapturedRequest(messages=clean_messages, params=clean), None


def parse_harness_output(stdout: str, stderr: str, expected: int, nonce: str) -> list[CaptureResult]:
    prefix = RESULT_MARKER + nonce
    line = next((ln for ln in reversed(stdout.splitlines()) if ln.startswith(prefix)), None)
    if line is None:
        tail = stderr.strip().splitlines()[-1:] or ["no output"]
        return [CaptureResult(None, f"prompt capture failed: {tail[0]}")] * expected
    try:
        raw = json.loads(line[len(prefix):])
    except json.JSONDecodeError:
        return [CaptureResult(None, "prompt capture returned malformed output")] * expected
    if not isinstance(raw, list) or len(raw) != expected:
        return [CaptureResult(None, "prompt capture returned the wrong number of results")] * expected

    results = []
    for item in raw:
        if isinstance(item, dict) and item.get("ok") and isinstance(item.get("request"), dict):
            request = dict(item["request"])
            messages = request.pop("messages", None)
            sanitized, error = sanitize_request(messages, request)
            results.append(CaptureResult(sanitized, error))
        else:
            error = item.get("error") if isinstance(item, dict) else None
            results.append(CaptureResult(None, str(error or "prompt capture failed")))
    return results
