"""Deterministic quality evaluation of model outputs (no LLM judge).

Structured nodes (an `expected_schema` or JSON response format) are scored on:

    parses as JSON        0.30  hard
    required fields       0.25  hard
    types & enums         0.20
    reference agreement   0.25  (only when a reference is supplied)

Free-text nodes are scored on:

    non-empty             0.20  hard
    required phrases      0.50  hard (only when `must_include` is supplied)
    forbidden phrases     0.15  hard (only when `must_not_include` is supplied)
    length window         0.15  (only when min/max chars are supplied)

Checks that do not apply are dropped and the remaining weights renormalised.
`passes` requires every applicable hard check to pass and score >= threshold.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from typing import Any, Optional

_THINK_RE = re.compile(r"<think>.*?</think>", re.S | re.I)
_FENCE_RE = re.compile(r"```(?:json|JSON)?\s*\n?(.*?)```", re.S)

# Upper bound on "{"/"[" start positions tried when JSON is embedded in prose;
# keeps adversarial outputs (e.g. "[[[[...") from making extraction quadratic.
MAX_DECODE_ATTEMPTS = 256

_STRUCTURED_WEIGHTS = {"parse": 0.30, "required": 0.25, "types": 0.20, "reference": 0.25}
_TEXT_WEIGHTS = {"non_empty": 0.20, "must_include": 0.50, "must_not_include": 0.15, "length": 0.15}


@dataclass
class EvaluationResult:
    quality_score: float
    passes_validation: bool
    validation_errors: list[str] = field(default_factory=list)
    parsed_output: Any = None


# --------------------------------------------------------------------------- #
# JSON extraction                                                              #
# --------------------------------------------------------------------------- #


def strip_reasoning(text: str) -> str:
    """Remove <think>…</think> blocks; an unclosed <think> hides everything after it."""
    text = _THINK_RE.sub("", text)
    unclosed = re.search(r"<think>", text, re.I)
    if unclosed:
        text = text[: unclosed.start()]
    return text.strip()


def _reject_constant(name: str) -> Any:
    raise ValueError(f"non-standard JSON constant {name}")


# Strict decoder: NaN / Infinity / -Infinity are not valid JSON.
_DECODER = json.JSONDecoder(parse_constant=_reject_constant)


def json_candidates(text: str) -> list[Any]:
    """All JSON objects/arrays found in `text`, in order of appearance.

    Accepts bare JSON, ```json fenced blocks, and JSON embedded in prose.
    Bare scalars (strings, numbers, null) are not accepted.
    """
    cleaned = strip_reasoning(text)
    try:
        whole = _DECODER.decode(cleaned)
        if isinstance(whole, (dict, list)):
            return [whole]
    except (ValueError, RecursionError):
        pass

    found: list[Any] = []
    for match in _FENCE_RE.finditer(cleaned):
        try:
            value = _DECODER.decode(match.group(1).strip())
        except (ValueError, RecursionError):
            continue
        if isinstance(value, (dict, list)):
            found.append(value)
    if found:
        return found

    attempts, idx = 0, 0
    while idx < len(cleaned):
        char = cleaned[idx]
        if char in "{[":
            attempts += 1
            if attempts > MAX_DECODE_ATTEMPTS:
                break
            try:
                value, end = _DECODER.raw_decode(cleaned, idx)
            except (ValueError, RecursionError):
                idx += 1
                continue
            found.append(value)
            idx = end
            continue
        idx += 1
    return found


def extract_json(text: str, schema: Optional[dict[str, Any]] = None) -> tuple[bool, Any]:
    """Pick the JSON value that is the model's answer.

    When several JSON values appear (e.g. an example followed by the answer),
    the last one that has every required top-level field wins; otherwise the
    last one. Returns (found, value).
    """
    candidates = json_candidates(text)
    if not candidates:
        return False, None
    raw = schema.get("required") if isinstance(schema, dict) else None
    required = [k for k in raw if isinstance(k, str)] if isinstance(raw, list) else []
    if required:
        for value in reversed(candidates):
            if isinstance(value, dict) and all(k in value for k in required):
                return True, value
    return True, candidates[-1]


# --------------------------------------------------------------------------- #
# Minimal JSON-schema subset: type, properties, required, enum, items          #
# --------------------------------------------------------------------------- #


def _matches_type(value: Any, expected: str) -> bool:
    if expected == "string":
        return isinstance(value, str)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        if isinstance(value, bool):
            return False
        return isinstance(value, int) or (
            isinstance(value, float) and math.isfinite(value) and value.is_integer()
        )
    if expected == "number":
        if isinstance(value, bool):
            return False
        return isinstance(value, int) or (isinstance(value, float) and math.isfinite(value))
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "null":
        return value is None
    return True  # unknown type keywords are not enforced


def validate_schema(value: Any, schema: dict[str, Any], path: str = "$") -> list[str]:
    """Return human-readable violations of `schema` by `value` (empty if valid)."""
    errors: list[str] = []
    expected_type = schema.get("type")
    if expected_type is not None:
        types = expected_type if isinstance(expected_type, list) else [expected_type]
        if not any(_matches_type(value, t) for t in types):
            errors.append(f"{path}: expected {' or '.join(types)}, got {_type_name(value)}")
            return errors

    enum = schema.get("enum")
    if isinstance(enum, (list, tuple)) and not any(_strict_equal(value, e) for e in enum):
        errors.append(f"{path}: {value!r} not in {list(enum)}")

    if isinstance(value, dict):
        required = schema.get("required")
        for key in required if isinstance(required, list) else []:
            if isinstance(key, str) and key not in value:
                errors.append(f"{path}: missing required field '{key}'")
        properties = schema.get("properties")
        for key, sub in (properties.items() if isinstance(properties, dict) else []):
            if key in value and isinstance(sub, dict):
                errors.extend(validate_schema(value[key], sub, f"{path}.{key}"))

    if isinstance(value, list) and isinstance(schema.get("items"), dict):
        for i, item in enumerate(value):
            errors.extend(validate_schema(item, schema["items"], f"{path}[{i}]"))

    return errors


def _strict_equal(a: Any, b: Any) -> bool:
    """Equality that never treats booleans as numbers (True != 1)."""
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a is b
    if _is_num(a) and _is_num(b):
        return a == b
    return type(a) is type(b) and a == b


def _is_num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, float) and not math.isfinite(value):
        return "non-finite number"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


# --------------------------------------------------------------------------- #
# Scoring                                                                      #
# --------------------------------------------------------------------------- #


def _values_agree(actual: Any, expected: Any) -> bool:
    if isinstance(expected, str) and isinstance(actual, str):
        return actual.strip().casefold() == expected.strip().casefold()
    if isinstance(expected, bool) or isinstance(actual, bool):
        return actual is expected
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        if isinstance(expected, int) and isinstance(actual, int):
            return actual == expected
        try:
            return math.isclose(actual, expected, rel_tol=1e-6, abs_tol=1e-9)
        except OverflowError:
            return False
    if isinstance(expected, dict) and isinstance(actual, dict):
        return all(k in actual and _values_agree(actual[k], v) for k, v in expected.items())
    if isinstance(expected, list) and isinstance(actual, list):
        return len(actual) == len(expected) and all(
            _values_agree(a, e) for a, e in zip(actual, expected)
        )
    return actual == expected


def _weighted(components: dict[str, float], weights: dict[str, float]) -> float:
    total_weight = sum(weights[k] for k in components)
    if total_weight == 0:
        return 0.0
    score = sum(components[k] * weights[k] for k in components) / total_weight
    return round(min(1.0, max(0.0, score)), 4)


def _evaluate_structured(
    text: str,
    schema: Optional[dict[str, Any]],
    reference: Any,
) -> tuple[dict[str, float], list[str], bool, Any]:
    errors: list[str] = []
    found, parsed = extract_json(text, schema)
    if not found:
        errors.append("Output is not valid JSON")
        components = {"parse": 0.0}
        if schema and schema.get("required"):
            components["required"] = 0.0
        if schema:
            components["types"] = 0.0
        if reference is not None:
            components["reference"] = 0.0
        return components, errors, False, None

    components: dict[str, float] = {"parse": 1.0}
    hard_ok = True

    if schema:
        raw_required = schema.get("required")
        required = [k for k in raw_required if isinstance(k, str)] if isinstance(raw_required, list) else []
        if required:
            if isinstance(parsed, dict):
                present = [k for k in required if k in parsed]
            else:
                present = []
            components["required"] = len(present) / len(required)
            missing = [k for k in required if k not in present]
            if missing:
                hard_ok = False
                errors.append(f"Missing required fields: {', '.join(missing)}")

        # Root-level required fields are scored by the "required" component above;
        # nested ones remain ordinary schema violations.
        violations = [
            e for e in validate_schema(parsed, schema) if not e.startswith("$: missing required field")
        ]
        checked = _count_checked_properties(parsed, schema)
        if checked == 0:
            components["types"] = 0.0 if violations else 1.0
        else:
            components["types"] = max(0.0, 1.0 - len(violations) / checked)
        errors.extend(f"Schema violation {v}" for v in violations)

    if reference is not None:
        if isinstance(reference, dict) and isinstance(parsed, dict):
            if reference:
                agree = [k for k, v in reference.items() if k in parsed and _values_agree(parsed[k], v)]
                components["reference"] = len(agree) / len(reference)
                for key in reference:
                    if key not in agree:
                        errors.append(
                            f"Field '{key}' = {parsed.get(key)!r}, expected {reference[key]!r}"
                        )
            else:
                components["reference"] = 1.0
        else:
            ok = _values_agree(parsed, reference)
            components["reference"] = 1.0 if ok else 0.0
            if not ok:
                errors.append("Output does not match reference")

    return components, errors, hard_ok, parsed


def _count_checked_properties(parsed: Any, schema: dict[str, Any]) -> int:
    """Number of schema-constrained values present in the output (min 1 for a typed root)."""
    count = 0
    properties = schema.get("properties")
    if isinstance(parsed, dict) and isinstance(properties, dict):
        for key, sub in properties.items():
            if key in parsed and isinstance(sub, dict):
                count += 1
    if count == 0 and ("type" in schema or "enum" in schema):
        count = 1
    return count


def _evaluate_text(
    text: str,
    must_include: Optional[list[str]],
    must_not_include: Optional[list[str]],
    min_chars: Optional[int],
    max_chars: Optional[int],
) -> tuple[dict[str, float], list[str], bool]:
    errors: list[str] = []
    cleaned = strip_reasoning(text)
    folded = cleaned.casefold()
    hard_ok = True

    components: dict[str, float] = {"non_empty": 1.0 if cleaned else 0.0}
    if not cleaned:
        hard_ok = False
        errors.append("Output is empty")

    if must_include:
        missing = [p for p in must_include if p.casefold() not in folded]
        components["must_include"] = 1 - len(missing) / len(must_include)
        if missing:
            hard_ok = False
            errors.append(f"Missing required content: {', '.join(missing)}")

    if must_not_include:
        found = [p for p in must_not_include if p.casefold() in folded]
        components["must_not_include"] = 1 - len(found) / len(must_not_include)
        if found:
            hard_ok = False
            errors.append(f"Contains forbidden content: {', '.join(found)}")

    if min_chars is not None or max_chars is not None:
        length = len(cleaned)
        too_short = min_chars is not None and length < min_chars
        too_long = max_chars is not None and length > max_chars
        components["length"] = 0.0 if (too_short or too_long) else 1.0
        if too_short:
            errors.append(f"Output length {length} below minimum {min_chars}")
        if too_long:
            errors.append(f"Output length {length} above maximum {max_chars}")

    return components, errors, hard_ok


def evaluate(
    output_text: str,
    *,
    threshold: float,
    expected_schema: Optional[dict[str, Any]] = None,
    json_required: bool = False,
    reference: Any = None,
    must_include: Optional[list[str]] = None,
    must_not_include: Optional[list[str]] = None,
    min_chars: Optional[int] = None,
    max_chars: Optional[int] = None,
) -> EvaluationResult:
    """Score one model output against the node's checks."""
    if not 0 <= threshold <= 1:
        raise ValueError("threshold must be within [0, 1]")
    if output_text is None:
        output_text = ""

    structured = bool(expected_schema) or json_required
    parsed: Any = None
    if structured:
        components, errors, hard_ok, parsed = _evaluate_structured(
            output_text, expected_schema, reference
        )
        score = _weighted(components, _STRUCTURED_WEIGHTS)
    else:
        components, errors, hard_ok = _evaluate_text(
            output_text, must_include, must_not_include, min_chars, max_chars
        )
        score = _weighted(components, _TEXT_WEIGHTS)

    if score < threshold:
        errors.insert(0, f"Quality score {score:.2f} below {threshold:.2f} threshold")

    return EvaluationResult(
        quality_score=score,
        passes_validation=hard_ok and score >= threshold,
        validation_errors=errors,
        parsed_output=parsed,
    )
