"""Bounded deterministic evaluation; no imports, expressions, regex or references.

JSON Schema support is an explicit allowlisted subset, not a full draft engine.
Unknown keywords and all reference-resolution mechanisms are rejected at intake.
"""

from __future__ import annotations

import json
import math

from backend.schemas import CaseEvaluation, EvaluationProfile, LocalBenchmarkCase


class EvaluationInputError(ValueError):
    """Controlled invalid/over-budget input; never render input or parser errors."""


class EvaluationBudgetExceeded(EvaluationInputError):
    """Insufficient evaluation budget is inconclusive, not a quality failure."""


def parse_bounded_json(text: str, *, max_bytes=16384, max_depth=16, max_nodes=4096):
    try:
        if type(text) is not str or len(text.encode("utf-8")) > max_bytes:
            raise EvaluationBudgetExceeded()
        depth, quoted, escaped = 0, False, False
        for char in text:
            if quoted:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    quoted = False
            elif char == '"':
                quoted = True
            elif char in "[{":
                depth += 1
                if depth > max_depth:
                    raise EvaluationBudgetExceeded()
            elif char in "]}":
                depth -= 1
                if depth < 0:
                    raise EvaluationInputError()

        def pairs(values):
            result = {}
            for key, value in values:
                if key in result:
                    raise EvaluationInputError()
                result[key] = value
            return result

        def number(value, convert):
            if len(value) > 128:
                raise EvaluationBudgetExceeded()
            result = convert(value)
            if type(result) is float and not math.isfinite(result):
                raise EvaluationBudgetExceeded()
            return result

        def constant(_value):
            raise EvaluationInputError()

        result = json.loads(text, object_pairs_hook=pairs, parse_int=lambda value: number(value, int),
                            parse_float=lambda value: number(value, float), parse_constant=constant)
        pending = [result]
        count = 0
        while pending:
            item = pending.pop()
            count += 1
            if count > max_nodes:
                raise EvaluationBudgetExceeded()
            if type(item) is dict:
                pending.extend(item.keys())
                pending.extend(item.values())
            elif type(item) is list:
                pending.extend(item)
            elif type(item) is str:
                item.encode("utf-8")  # Reject unpaired surrogate data.
        return result
    except EvaluationBudgetExceeded:
        raise EvaluationBudgetExceeded("Evaluation input exceeds its budget.") from None
    except (ValueError, UnicodeError, RecursionError, OverflowError, TypeError):
        raise EvaluationInputError("Evaluation input is invalid or exceeds its budget.") from None


_TYPES = {"object", "array", "string", "integer", "number", "boolean", "null"}
_KEYS = {"type", "properties", "required", "additionalProperties", "items", "minimum", "maximum",
         "minLength", "maxLength", "minItems", "maxItems", "enum", "const", "$schema"}


def json_equal(left, right):
    if type(left) in (int, float) and type(right) in (int, float):
        return left == right
    if type(left) is not type(right):
        return False
    if type(left) is dict:
        return left.keys() == right.keys() and all(json_equal(left[key], right[key]) for key in left)
    if type(left) is list:
        return len(left) == len(right) and all(json_equal(a, b) for a, b in zip(left, right))
    return left == right


def compile_schema(text: str):
    schema = parse_bounded_json(text, max_nodes=512)
    pending = [schema]
    while pending:
        item = pending.pop()
        if type(item) is bool:
            continue
        if type(item) is not dict or item.keys() - _KEYS:
            raise EvaluationInputError("Unsupported validation schema.")
        if "$schema" in item and item["$schema"] != "https://json-schema.org/draft/2020-12/schema":
            raise EvaluationInputError("Unsupported validation schema.")
        if "type" in item and (type(item["type"]) is not str or item["type"] not in _TYPES):
            raise EvaluationInputError("Unsupported schema type.")
        if "properties" in item:
            if type(item["properties"]) is not dict:
                raise EvaluationInputError("Invalid property rules.")
            pending.extend(item["properties"].values())
        if "items" in item:
            pending.append(item["items"])
        if "required" in item and (type(item["required"]) is not list
                or any(type(key) is not str for key in item["required"])
                or len(set(item["required"])) != len(item["required"])):
            raise EvaluationInputError("Invalid required keys.")
        if "additionalProperties" in item and type(item["additionalProperties"]) is not bool:
            raise EvaluationInputError("Only boolean additional-property rules are supported.")
        for name in ("minLength", "maxLength", "minItems", "maxItems"):
            if name in item and (type(item[name]) is not int or not 0 <= item[name] <= 1000000):
                raise EvaluationInputError("Invalid size rule.")
        for name in ("minimum", "maximum"):
            if name in item and type(item[name]) not in (int, float):
                raise EvaluationInputError("Invalid numeric rule.")
        if "enum" in item:
            values = item["enum"]
            if type(values) is not list or not 1 <= len(values) <= 64 or any(
                json_equal(a, b) for index, a in enumerate(values) for b in values[:index]
            ):
                raise EvaluationInputError("Invalid enumeration.")
    return schema


def _matches(schema, value):
    if type(schema) is bool:
        return schema
    kind = schema.get("type")
    checks = {
        "object": type(value) is dict, "array": type(value) is list, "string": type(value) is str,
        "integer": type(value) is int or (type(value) is float and value.is_integer()),
        "number": type(value) in (int, float), "boolean": type(value) is bool, "null": value is None,
    }
    if kind is not None and not checks[kind]:
        return False
    if "const" in schema and not json_equal(value, schema["const"]):
        return False
    if "enum" in schema and not any(json_equal(value, item) for item in schema["enum"]):
        return False
    if type(value) is dict:
        properties = schema.get("properties", {})
        if any(key not in value for key in schema.get("required", ())):
            return False
        if schema.get("additionalProperties") is False and value.keys() - properties.keys():
            return False
        return all(_matches(rule, value[key]) for key, rule in properties.items() if key in value)
    if type(value) in (list, str):
        low, high = ("minItems", "maxItems") if type(value) is list else ("minLength", "maxLength")
        if len(value) < schema.get(low, 0) or len(value) > schema.get(high, 1000000):
            return False
        if type(value) is list and "items" in schema:
            return all(_matches(schema["items"], item) for item in value)
    if type(value) in (int, float):
        if ("minimum" in schema and value < schema["minimum"]) or ("maximum" in schema and value > schema["maximum"]):
            return False
    return True


def validate_profile(profile: EvaluationProfile) -> None:
    if profile.mechanism is None:
        raise EvaluationInputError("An explicit evaluation mechanism is required.")
    if profile.mechanism == "json_schema":
        if profile.validation_schema_json is None:
            raise EvaluationInputError("A local validation schema is required.")
        compile_schema(profile.validation_schema_json)
    elif profile.validation_schema_json is not None:
        raise EvaluationInputError("This profile does not accept schema rules.")


def evaluate(case: LocalBenchmarkCase, profile: EvaluationProfile, output: str | None) -> CaseEvaluation:
    def result(status, reason, checks=(), validation="not_run"):
        return CaseEvaluation(status=status, reason=reason, checks_ran=checks, validation_status=validation)

    if case.skip_reason is not None:
        return result("skipped", "operator_excluded")
    if output is None:
        return result("not_run", "output_unavailable")
    try:
        if len(output.encode("utf-8")) > 16384:
            return result("inconclusive", "resource_limit")
        validate_profile(profile)
    except (EvaluationInputError, UnicodeError):
        return result("inconclusive", "profile_unavailable")
    if profile.mechanism == "exact":
        if case.expected_output is None:
            return result("inconclusive", "ground_truth_unavailable")
        matched = output == case.expected_output
        return result("passed" if matched else "failed", "matched" if matched else "mismatch", ("exact",), "passed" if matched else "failed")
    checks = ("json",)
    try:
        value = parse_bounded_json(output)
    except EvaluationBudgetExceeded:
        return result("inconclusive", "resource_limit")
    except EvaluationInputError:
        return result("failed", "invalid_json", checks, "failed")
    if profile.mechanism == "json_schema":
        checks += ("json_schema",)
        if not _matches(compile_schema(profile.validation_schema_json), value):
            return result("failed", "schema_mismatch", checks, "failed")
    if case.expected_output is None:
        return result("inconclusive", "ground_truth_unavailable", checks, "passed")
    try:
        expected = parse_bounded_json(case.expected_output)
    except EvaluationInputError:
        return result("inconclusive", "invalid_expected_output", checks, "passed")
    matched = json_equal(value, expected)
    return result("passed" if matched else "failed", "matched" if matched else "mismatch", checks, "passed")
