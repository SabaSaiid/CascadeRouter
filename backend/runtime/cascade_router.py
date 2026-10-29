"""CascadeRouter runtime: route each LLM call by the generated policy, with fallback.

Standalone by design (stdlib + PyYAML) so it can be vendored into a target
application as `cascaderouter.py`:

    from cascaderouter import CascadeRouter
    cascade_router = CascadeRouter.load(__file__)
    response = cascade_router.dispatch(node_id="node_x", client=client, model=..., messages=[...])

Behaviour per call:
  1. Unknown node or no policy -> the original call, unchanged.
  2. Call the policy's primary model.
  3. If the response fails the node's structural checks (JSON parse, required
     fields) or the call raises, retry on the fallback model (max_retries).
  4. A failing fallback never makes things worse: the primary response is
     returned if one exists, otherwise the last error is raised.
"""

from __future__ import annotations

import inspect
import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

POLICY_FILENAME = ".cascaderouter.yaml"
ENV_POLICY_PATH = "CASCADEROUTER_POLICY"
ENV_DISABLE = "CASCADEROUTER_DISABLE"

logger = logging.getLogger("cascaderouter")

_THINK_RE = re.compile(r"<think>.*?</think>", re.S | re.I)


@dataclass(frozen=True)
class NodeRule:
    primary_model: str
    fallback_model: Optional[str]
    enforce_json: bool = False
    required_fields: tuple[str, ...] = ()
    max_retries: int = 1


@dataclass
class DispatchStats:
    primary_ok: int = 0
    escalations: int = 0
    passthrough: int = 0
    events: list[dict[str, Any]] = field(default_factory=list)


def _response_text(response: Any) -> Optional[str]:
    try:
        content = response.choices[0].message.content
    except (AttributeError, IndexError, KeyError, TypeError):
        return None
    return content if isinstance(content, str) else None


def _parse_json_object(text: str) -> Optional[dict[str, Any]]:
    cleaned = _THINK_RE.sub("", text).strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned[cleaned.find("{"):] if "{" in cleaned else cleaned
    decoder = json.JSONDecoder()
    for idx, char in enumerate(cleaned):
        if char == "{":
            try:
                value, _ = decoder.raw_decode(cleaned, idx)
            except (ValueError, RecursionError):
                continue
            if isinstance(value, dict):
                return value
    return None


def _has_tool_call(response: Any) -> bool:
    try:
        message = response.choices[0].message
    except (AttributeError, IndexError, KeyError, TypeError):
        return False
    return bool(getattr(message, "tool_calls", None) or getattr(message, "function_call", None))


def check_response(rule: NodeRule, response: Any) -> Optional[str]:
    """None if the response satisfies the rule's structural checks, else the reason."""
    text = _response_text(response)
    if (text is None or not text.strip()) and _has_tool_call(response) and not rule.enforce_json:
        return None  # a tool call is a real answer, not an empty one
    if text is None or not text.strip():
        return "empty response"
    if not rule.enforce_json and not rule.required_fields:
        return None
    data = _parse_json_object(text)
    if data is None:
        return "response is not a JSON object"
    missing = [f for f in rule.required_fields if f not in data]
    if missing:
        return f"missing required fields: {', '.join(missing)}"
    return None


class CascadeRouter:
    def __init__(self, rules: dict[str, NodeRule], source: Optional[str] = None):
        self.rules = rules
        self.source = source
        self.stats = DispatchStats()

    # ------------------------------------------------------------------ loading

    @classmethod
    def from_dict(cls, policy: dict[str, Any], source: Optional[str] = None) -> "CascadeRouter":
        """Build rules; malformed entries are skipped, never raised (the app must keep working)."""
        rules: dict[str, NodeRule] = {}
        nodes = policy.get("nodes") if isinstance(policy, dict) else None
        if not isinstance(nodes, dict):
            return cls(rules, source)
        for node_id, raw in nodes.items():
            if not isinstance(raw, dict) or not isinstance(raw.get("primary_model"), str):
                continue
            cond = raw.get("routing_conditions")
            if not isinstance(cond, dict):
                cond = {}
            fields = cond.get("required_fields")
            if not isinstance(fields, (list, tuple)):
                fields = ()
            fallback = raw.get("fallback_model")
            retries = cond.get("max_retries", 1)
            rules[str(node_id)] = NodeRule(
                primary_model=raw["primary_model"],
                fallback_model=fallback if isinstance(fallback, str) and fallback else None,
                enforce_json=bool(cond.get("enforce_json", False)),
                required_fields=tuple(str(f) for f in fields),
                max_retries=retries if isinstance(retries, int) and retries >= 0 else 1,
            )
        return cls(rules, source)

    @classmethod
    def load(cls, start: str | os.PathLike[str] | None = None) -> "CascadeRouter":
        """Load the policy from $CASCADEROUTER_POLICY or the nearest .cascaderouter.yaml
        found walking up from `start` (a file or directory; default: cwd).

        A missing or unreadable policy yields an empty router (pure passthrough),
        so the application keeps working exactly as before.
        """
        if os.environ.get(ENV_DISABLE):
            return cls({}, None)
        path = cls._find_policy(start)
        if path is None:
            logger.warning("cascaderouter: no %s found; calls pass through unchanged", POLICY_FILENAME)
            return cls({}, None)
        try:
            import yaml

            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except Exception as exc:  # never break the host application
            logger.error("cascaderouter: cannot read %s (%s); passthrough", path, exc)
            return cls({}, str(path))
        if not isinstance(data, dict):
            logger.error("cascaderouter: %s is not a mapping; passthrough", path)
            return cls({}, str(path))
        try:
            return cls.from_dict(data, str(path))
        except Exception as exc:  # never break the host application at import time
            logger.error("cascaderouter: invalid policy %s (%s); passthrough", path, exc)
            return cls({}, str(path))

    @staticmethod
    def _find_policy(start: str | os.PathLike[str] | None) -> Optional[Path]:
        env_path = os.environ.get(ENV_POLICY_PATH)
        if env_path:
            p = Path(env_path)
            return p if p.is_file() else None
        here = Path(start).resolve() if start else Path.cwd()
        if here.is_file():
            here = here.parent
        for directory in (here, *here.parents):
            candidate = directory / POLICY_FILENAME
            if candidate.is_file():
                return candidate
        return None

    # ------------------------------------------------------------------ dispatch

    def _plan(self, node_id: str, kwargs: dict[str, Any]) -> tuple[Optional[NodeRule], list[str]]:
        rule = self.rules.get(node_id)
        if rule is None:
            return None, []
        models = [rule.primary_model]
        if rule.fallback_model and rule.fallback_model != rule.primary_model:
            models.extend([rule.fallback_model] * max(0, rule.max_retries))
        return rule, models[: 1 + max(0, rule.max_retries)]

    def _record(self, node_id: str, model: str, outcome: str) -> None:
        if len(self.stats.events) < 1000:
            self.stats.events.append({"node_id": node_id, "model": model, "outcome": outcome})

    def dispatch(self, node_id: str, client: Any, validator: Optional[Callable[[Any], bool]] = None, **kwargs: Any) -> Any:
        """Synchronous chat completion routed by policy."""
        create = client.chat.completions.create
        rule, models = self._plan(node_id, kwargs)
        if rule is None:
            self.stats.passthrough += 1
            return create(**kwargs)
        if kwargs.get("stream"):
            # Streams cannot be validated before they are consumed: route, don't check.
            self._record(node_id, models[0], "stream")
            return create(**{**kwargs, "model": models[0]})

        first_response: Any = None
        last_error: Optional[BaseException] = None
        for attempt, model in enumerate(models):
            try:
                response = create(**{**kwargs, "model": model})
            except Exception as exc:
                last_error = exc
                self._record(node_id, model, f"error: {type(exc).__name__}")
                continue
            if inspect.isawaitable(response):
                # An async client reached the sync API: hand the awaitable back unchanged.
                self._record(node_id, model, "awaitable")
                return response
            problem = check_response(rule, response)
            if problem is None and validator is not None and not validator(response):
                problem = "custom validator rejected response"
            if problem is None:
                if attempt == 0:
                    self.stats.primary_ok += 1
                self._record(node_id, model, "ok")
                return response
            self._record(node_id, model, f"invalid: {problem}")
            if first_response is None:
                first_response = response
            if attempt < len(models) - 1:
                self.stats.escalations += 1
        if first_response is not None:
            return first_response
        assert last_error is not None
        raise last_error

    async def dispatch_async(
        self, node_id: str, client: Any, validator: Optional[Callable[[Any], bool]] = None, **kwargs: Any
    ) -> Any:
        """Async variant for AsyncOpenAI clients."""
        create = client.chat.completions.create
        rule, models = self._plan(node_id, kwargs)
        if rule is None:
            self.stats.passthrough += 1
            return await create(**kwargs)
        if kwargs.get("stream"):
            self._record(node_id, models[0], "stream")
            return await create(**{**kwargs, "model": models[0]})

        first_response: Any = None
        last_error: Optional[BaseException] = None
        for attempt, model in enumerate(models):
            try:
                response = await create(**{**kwargs, "model": model})
            except Exception as exc:
                last_error = exc
                self._record(node_id, model, f"error: {type(exc).__name__}")
                continue
            problem = check_response(rule, response)
            if problem is None and validator is not None and not validator(response):
                problem = "custom validator rejected response"
            if problem is None:
                if attempt == 0:
                    self.stats.primary_ok += 1
                self._record(node_id, model, "ok")
                return response
            self._record(node_id, model, f"invalid: {problem}")
            if first_response is None:
                first_response = response
            if attempt < len(models) - 1:
                self.stats.escalations += 1
        if first_response is not None:
            return first_response
        assert last_error is not None
        raise last_error
