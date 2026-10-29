"""Benchmark cases: real inputs with hand-written expectations.

Read from `cascade_cases.yaml` at the root of the scanned repository:

    node_classify_customer_intent:
      - vars: {query: "I was double charged"}
        expected: {category: billing}
      - vars: {...}
        must_include: ["1.", "2."]
        min_chars: 80

Nothing is ever invented: a node without cases is simply not benchmarked.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

CASES_FILENAME = "cascade_cases.yaml"
MAX_CASES_BYTES = 1024 * 1024
MAX_CASES_PER_NODE = 20

_ALLOWED_KEYS = {"vars", "expected", "must_include", "must_not_include", "min_chars", "max_chars"}


class CasesError(ValueError):
    """The cases file is malformed."""


@dataclass(frozen=True)
class BenchmarkCase:
    vars: dict[str, Any]
    expected: Any = None
    must_include: list[str] = field(default_factory=list)
    must_not_include: list[str] = field(default_factory=list)
    min_chars: Optional[int] = None
    max_chars: Optional[int] = None


def _string_list(value: Any, where: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(v, str) and v for v in value):
        raise CasesError(f"{where}: must be a list of non-empty strings")
    return list(value)


def _opt_int(value: Any, where: str) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise CasesError(f"{where}: must be a non-negative integer")
    return value


def parse_cases(data: Any) -> dict[str, list[BenchmarkCase]]:
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise CasesError("top level must be a mapping of node_id -> list of cases")
    result: dict[str, list[BenchmarkCase]] = {}
    for node_id, raw_cases in data.items():
        if not isinstance(node_id, str) or not node_id:
            raise CasesError(f"invalid node id {node_id!r}")
        if not isinstance(raw_cases, list) or not raw_cases:
            raise CasesError(f"{node_id}: must be a non-empty list of cases")
        if len(raw_cases) > MAX_CASES_PER_NODE:
            raise CasesError(f"{node_id}: at most {MAX_CASES_PER_NODE} cases allowed")
        cases = []
        for i, raw in enumerate(raw_cases):
            where = f"{node_id}[{i}]"
            if not isinstance(raw, dict):
                raise CasesError(f"{where}: must be a mapping")
            unknown = set(raw) - _ALLOWED_KEYS
            if unknown:
                raise CasesError(f"{where}: unknown keys {sorted(unknown)}")
            variables = raw.get("vars", {})
            if not isinstance(variables, dict) or not all(isinstance(k, str) for k in variables):
                raise CasesError(f"{where}.vars: must be a mapping of argument name -> value")
            if "client" in variables:
                raise CasesError(f"{where}.vars: 'client' is injected automatically")
            for key in ("vars", "expected"):
                try:
                    json.dumps(raw.get(key), allow_nan=False)
                except (TypeError, ValueError) as exc:
                    raise CasesError(
                        f"{where}.{key}: must contain only JSON values (quote dates and times): {exc}"
                    ) from exc
            min_chars = _opt_int(raw.get("min_chars"), f"{where}.min_chars")
            max_chars = _opt_int(raw.get("max_chars"), f"{where}.max_chars")
            if min_chars is not None and max_chars is not None and min_chars > max_chars:
                raise CasesError(f"{where}: min_chars > max_chars")
            cases.append(
                BenchmarkCase(
                    vars=dict(variables),
                    expected=raw.get("expected"),
                    must_include=_string_list(raw.get("must_include"), f"{where}.must_include"),
                    must_not_include=_string_list(raw.get("must_not_include"), f"{where}.must_not_include"),
                    min_chars=min_chars,
                    max_chars=max_chars,
                )
            )
        result[node_id] = cases
    return result


def load_cases(repo_root: Path) -> dict[str, list[BenchmarkCase]]:
    """Load cases for a repository; a missing file means no cases."""
    path = repo_root / CASES_FILENAME
    if not path.is_file() or path.is_symlink():
        return {}
    if path.stat().st_size > MAX_CASES_BYTES:
        raise CasesError(f"{CASES_FILENAME} is larger than 1 MB")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (yaml.YAMLError, UnicodeDecodeError) as exc:
        raise CasesError(f"{CASES_FILENAME} is not valid YAML: {exc}") from exc
    return parse_cases(data)
