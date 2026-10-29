import pytest

from backend.compiler.evaluator import evaluate, extract_json, strip_reasoning, validate_schema

INTENT_SCHEMA = {
    "type": "object",
    "properties": {
        "category": {"type": "string", "enum": ["billing", "tech_support", "general"]},
        "confidence": {"type": "number"},
        "urgency": {"type": "string", "enum": ["low", "medium", "high"]},
    },
    "required": ["category", "confidence"],
}


# ---------------------------------------------------------------- extraction


@pytest.mark.parametrize(
    "text,expected",
    [
        ('{"a": 1}', {"a": 1}),
        ('  [1, 2] ', [1, 2]),
        ('```json\n{"a": 1}\n```', {"a": 1}),
        ('```\n{"a": 1}\n```', {"a": 1}),
        ('Sure! Here it is: {"a": {"b": [1]}} hope that helps', {"a": {"b": [1]}}),
        ('<think>maybe {"wrong": 1}</think>{"a": 2}', {"a": 2}),
        ('broken { here then {"ok": true}', {"ok": True}),
    ],
)
def test_extract_json_finds_value(text, expected):
    assert extract_json(text) == (True, expected)


@pytest.mark.parametrize("text", ["", "no json here", "{not: json}", "<think>{\"a\":1}</think>"])
def test_extract_json_missing(text):
    assert extract_json(text) == (False, None)


def test_strip_reasoning_multiline():
    assert strip_reasoning("<THINK>\nline\n</think>\nanswer") == "answer"


# ---------------------------------------------------------------- schema subset


def test_validate_schema_valid():
    assert validate_schema({"category": "billing", "confidence": 0.9}, INTENT_SCHEMA) == []


def test_validate_schema_reports_each_violation():
    errors = validate_schema({"category": "sales", "confidence": "high", "urgency": "low"}, INTENT_SCHEMA)
    assert errors == [
        "$.category: 'sales' not in ['billing', 'tech_support', 'general']",
        "$.confidence: expected number, got string",
    ]


def test_validate_schema_types():
    assert validate_schema(True, {"type": "number"}) == ["$: expected number, got boolean"]
    assert validate_schema(True, {"type": "integer"}) != []
    assert validate_schema(3.0, {"type": "integer"}) == []
    assert validate_schema(3.5, {"type": "integer"}) != []
    assert validate_schema(None, {"type": ["string", "null"]}) == []
    assert validate_schema([1, "x"], {"type": "array", "items": {"type": "integer"}}) == [
        "$[1]: expected integer, got string"
    ]
    assert validate_schema({"a": {}}, {"properties": {"a": {"required": ["b"]}}}) == [
        "$.a: missing required field 'b'"
    ]
    assert validate_schema("x", {"type": "custom"}) == []


# ---------------------------------------------------------------- structured scoring


def test_perfect_structured_output_passes():
    r = evaluate(
        '{"category": "billing", "confidence": 0.97, "urgency": "high"}',
        threshold=0.92,
        expected_schema=INTENT_SCHEMA,
        reference={"category": "billing"},
    )
    assert r.quality_score == 1.0
    assert r.passes_validation
    assert r.validation_errors == []
    assert r.parsed_output["category"] == "billing"


def test_reference_mismatch_lowers_score_below_threshold():
    r = evaluate(
        '{"category": "general", "confidence": 0.6}',
        threshold=0.92,
        expected_schema=INTENT_SCHEMA,
        reference={"category": "billing"},
    )
    assert r.quality_score == pytest.approx(0.75)
    assert not r.passes_validation
    assert r.validation_errors[0] == "Quality score 0.75 below 0.92 threshold"
    assert "Field 'category' = 'general', expected 'billing'" in r.validation_errors


def test_reference_comparison_is_case_insensitive_and_nested():
    r = evaluate(
        '{"category": " Billing ", "confidence": 1, "meta": {"x": [1, 2.0]}}',
        threshold=0.9,
        json_required=True,
        reference={"category": "billing", "meta": {"x": [1, 2]}},
    )
    assert r.quality_score == 1.0 and r.passes_validation


def test_schema_enum_is_strict_even_when_reference_is_lenient():
    r = evaluate(
        '{"category": "Billing", "confidence": 1}',
        threshold=0.92,
        expected_schema=INTENT_SCHEMA,
        reference={"category": "billing"},
    )
    assert r.quality_score == pytest.approx(0.9)
    assert not r.passes_validation


def test_missing_required_field_is_hard_failure():
    r = evaluate('{"category": "billing"}', threshold=0.5, expected_schema=INTENT_SCHEMA)
    assert not r.passes_validation  # hard check fails even though score >= 0.5
    assert r.quality_score == pytest.approx((0.30 + 0.25 * 0.5 + 0.20) / 0.75, abs=1e-4)
    assert "Missing required fields: confidence" in r.validation_errors


def test_invalid_json_scores_zero():
    r = evaluate("I think it's billing", threshold=0.92, expected_schema=INTENT_SCHEMA, reference={"category": "billing"})
    assert r.quality_score == 0.0
    assert not r.passes_validation
    assert "Output is not valid JSON" in r.validation_errors
    assert r.parsed_output is None


def test_root_type_mismatch():
    r = evaluate("[1, 2]", threshold=0.5, expected_schema=INTENT_SCHEMA)
    assert not r.passes_validation
    assert any("expected object, got array" in e for e in r.validation_errors)


def test_json_required_without_schema():
    assert evaluate('{"x": 1}', threshold=0.92, json_required=True).passes_validation
    r = evaluate("plain", threshold=0.92, json_required=True)
    assert r.quality_score == 0.0 and not r.passes_validation


def test_non_dict_reference():
    assert evaluate("[1, 2]", threshold=0.9, json_required=True, reference=[1, 2]).passes_validation
    r = evaluate("[1, 3]", threshold=0.9, json_required=True, reference=[1, 2])
    assert not r.passes_validation and "Output does not match reference" in r.validation_errors


def test_bool_never_equals_number():
    r = evaluate('{"flag": 1}', threshold=0.9, json_required=True, reference={"flag": True})
    assert not r.passes_validation


# ---------------------------------------------------------------- free text scoring


def test_free_text_non_empty_only():
    r = evaluate("Restart the router.", threshold=0.92)
    assert r.quality_score == 1.0 and r.passes_validation
    r = evaluate("   ", threshold=0.92)
    assert r.quality_score == 0.0 and "Output is empty" in r.validation_errors
    assert not evaluate(None, threshold=0.5).passes_validation


def test_free_text_must_include_is_hard():
    r = evaluate(
        "Step 1: restart. Step 2: clear cache.",
        threshold=0.5,
        must_include=["step 1", "step 2", "step 3"],
    )
    assert not r.passes_validation
    assert r.quality_score == pytest.approx((0.20 + 0.50 * 2 / 3) / 0.70, abs=1e-4)
    assert "Missing required content: step 3" in r.validation_errors


def test_free_text_forbidden_and_length():
    r = evaluate("As an AI I cannot help", threshold=0.5, must_not_include=["as an ai"], max_chars=10)
    assert not r.passes_validation
    assert "Contains forbidden content: as an ai" in r.validation_errors
    assert "Output length 22 above maximum 10" in r.validation_errors
    r = evaluate("hi", threshold=0.5, min_chars=5)
    assert "Output length 2 below minimum 5" in r.validation_errors
    assert r.passes_validation  # length is a soft check: 0.2/0.35 = 0.57 >= 0.5


def test_reasoning_is_ignored_for_text():
    assert evaluate("<think>step 3</think>done", threshold=0.9, must_include=["step 3"]).passes_validation is False


def test_threshold_bounds():
    with pytest.raises(ValueError):
        evaluate("x", threshold=1.5)
    assert evaluate('{"a":1}', threshold=1.0, json_required=True).passes_validation
    assert evaluate("", threshold=0.0).passes_validation is False


# ---------------------------------------------------------------- review regressions


def test_huge_integers_do_not_crash():
    big = "1" + "0" * 400
    r = evaluate('{"n": %s}' % big, threshold=0.5,
                 expected_schema={"type": "object", "properties": {"n": {"type": "number"}}})
    assert r.passes_validation
    r = evaluate('{"n": %s}' % big, threshold=0.5, json_required=True, reference={"n": 10**400})
    assert r.passes_validation
    r = evaluate('{"n": %s}' % big, threshold=0.9, json_required=True, reference={"n": 1.5})
    assert not r.passes_validation


def test_deeply_nested_input_does_not_crash():
    assert evaluate("[" * 100000, threshold=0.5, json_required=True).quality_score == 0.0
    assert extract_json("x " + '{"a":' * 5000) == (False, None)


def test_nested_required_fields_are_enforced():
    schema = {
        "type": "object",
        "required": ["address"],
        "properties": {"address": {"type": "object", "required": ["city"], "properties": {"city": {"type": "string"}}}},
    }
    r = evaluate('{"address": {}}', threshold=0.92, expected_schema=schema)
    assert not r.passes_validation
    assert "Schema violation $.address: missing required field 'city'" in r.validation_errors


@pytest.mark.parametrize("text", ['"I cannot help"', "null", "42", "true"])
def test_json_scalars_are_not_accepted(text):
    r = evaluate(text, threshold=0.5, json_required=True)
    assert not r.passes_validation and "Output is not valid JSON" in r.validation_errors


def test_scalar_before_object_still_finds_object():
    assert extract_json('"note" {"a": 1}') == (True, {"a": 1})


def test_enum_is_bool_strict():
    assert validate_schema(False, {"enum": [0]}) == ["$: False not in [0]"]
    assert validate_schema(1, {"enum": [True]}) == ["$: 1 not in [True]"]
    assert validate_schema(1.0, {"enum": [1]}) == []
    assert validate_schema("1", {"enum": [1]}) != []
    r = evaluate('{"x": true}', threshold=0.92,
                 expected_schema={"type": "object", "properties": {"x": {"enum": [1, 2]}}})
    assert not r.passes_validation


def test_malformed_enum_is_ignored():
    r = evaluate('{"x": 5}', threshold=0.5,
                 expected_schema={"type": "object", "properties": {"x": {"enum": "abc"}}})
    assert r.passes_validation


@pytest.mark.parametrize("const", ["NaN", "Infinity", "-Infinity"])
def test_non_standard_json_constants_rejected(const):
    r = evaluate('{"x": %s}' % const, threshold=0.5,
                 expected_schema={"type": "object", "properties": {"x": {"type": "number"}}})
    assert not r.passes_validation and "Output is not valid JSON" in r.validation_errors


def test_non_finite_type_name():
    assert validate_schema(float("nan"), {"type": "number"}) == ["$: expected number, got non-finite number"]
    assert validate_schema(float("inf"), {"type": "integer"}) != []


def test_extraction_attempts_are_bounded(monkeypatch):
    import backend.compiler.evaluator as ev

    monkeypatch.setattr(ev, "MAX_DECODE_ATTEMPTS", 2)
    assert extract_json('[x [y {"a": 1}') == (False, None)
    monkeypatch.setattr(ev, "MAX_DECODE_ATTEMPTS", 3)
    assert extract_json('[x [y {"a": 1}') == (True, {"a": 1})


# ---------------------------------------------------------------- answer selection


def test_example_before_answer_grades_the_answer():
    text = 'Example: {"a": 1}. Answer: {"category": "billing", "confidence": 0.9}'
    r = evaluate(text, threshold=0.92, expected_schema=INTENT_SCHEMA, reference={"category": "billing"})
    assert r.passes_validation and r.parsed_output["category"] == "billing"


def test_without_schema_last_json_wins():
    from backend.compiler.evaluator import json_candidates

    assert json_candidates('{"a": 1} then {"b": 2}') == [{"a": 1}, {"b": 2}]
    assert extract_json('{"a": 1} then {"b": 2}') == (True, {"b": 2})


def test_multiple_fenced_blocks():
    text = '```json\n{"draft": true}\n```\nFinal:\n```json\n{"category": "general", "confidence": 1}\n```'
    assert extract_json(text, INTENT_SCHEMA) == (True, {"category": "general", "confidence": 1})


def test_unclosed_think_hides_reasoning():
    assert strip_reasoning('answer <think>{"category": "billing"') == "answer"
    r = evaluate('<think>{"category": "billing", "confidence": 1}', threshold=0.5, expected_schema=INTENT_SCHEMA)
    assert not r.passes_validation and "Output is not valid JSON" in r.validation_errors


def test_malformed_schema_shapes_do_not_crash():
    bad = {"type": "object", "properties": ["a"], "required": "a"}
    r = evaluate('{"a": 1}', threshold=0.5, expected_schema=bad)
    assert r.passes_validation
    assert validate_schema({"a": 1}, {"required": [1, "b"]}) == ["$: missing required field 'b'"]
