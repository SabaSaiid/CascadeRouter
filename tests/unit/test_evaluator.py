"""Synthetic strings test deterministic checks, never model behavior."""

import pytest

from backend.compiler.evaluator import EvaluationInputError, compile_schema, evaluate, parse_bounded_json
from backend.schemas import EvaluationProfile, LocalBenchmarkCase


def case(expected="answer", **changes):
    return LocalBenchmarkCase(identifier="test-case", input_text="test input", expected_output=expected, **changes)


def profile(mechanism="exact", schema=None):
    return EvaluationProfile(identifier="test-profile", version="v1", criteria_id="test-criteria", mechanism=mechanism,
                             validation_schema_json=schema)


@pytest.mark.parametrize("output,status", [("answer", "passed"), ("wrong", "failed"), ("answer\n", "failed"), (None, "not_run")])
def test_exact_matching_is_literal_and_requires_actual_output(output, status):
    assert evaluate(case(), profile(), output).status == status


@pytest.mark.parametrize("mechanism,schema", [("exact", None), ("json", None), ("json_schema", '{"type":"object"}')])
def test_missing_ground_truth_never_yields_a_pass(mechanism, schema):
    result = evaluate(case(None), profile(mechanism, schema), "{}")
    assert result.status == "inconclusive" and result.reason == "ground_truth_unavailable"


def test_skipped_and_unrun_cases_do_not_claim_checks():
    result = evaluate(case(skip_reason="operator_excluded"), profile(), "answer")
    assert result.status == "skipped" and result.checks_ran == ()
    result = evaluate(case(), profile(), None)
    assert result.status == "not_run" and result.checks_ran == ()


@pytest.mark.parametrize("text", ['{"x":1,"x":2}', "NaN", "Infinity", "1e9999", "[" * 17 + "]" * 17,
                                  '"\\ud800"', "[1,]", "1" * 129])
def test_strict_json_rejects_duplicates_nonfinite_and_budget_attacks(text):
    with pytest.raises(EvaluationInputError):
        parse_bounded_json(text)


def test_json_comparison_ignores_key_order_but_distinguishes_bool_and_number():
    assert evaluate(case('{"a":1,"b":2}'), profile("json"), '{"b":2,"a":1}').status == "passed"
    assert evaluate(case('{"a":1}'), profile("json"), '{"a":true}').status == "failed"
    assert evaluate(case('{"a":1}'), profile("json"), '{bad').reason == "invalid_json"
    assert evaluate(case('bad expected'), profile("json"), '{}').status == "inconclusive"


@pytest.mark.parametrize("schema", [
    '{"$ref":"https://attacker.invalid/schema"}', '{"$ref":"file:///PRIVATE/file"}', '{"$ref":"#/$defs/a"}',
    '{"type":"string","pattern":"(a+)+$"}', '{"validator":"os.system"}',
    '{"properties":{"value":{"$dynamicRef":"https://attacker.invalid/"}}}',
    '{"type":["object","null"]}', '{"required":[1]}', '{"maxLength":true}',
])
def test_schema_allowlist_disables_code_regex_and_all_reference_resolution(schema):
    with pytest.raises(EvaluationInputError):
        compile_schema(schema)


@pytest.mark.parametrize("output,status", [('{"n":2,"tags":["x"]}', "passed"), ('{"n":4,"tags":["x"]}', "failed"),
                                          ('{"n":2,"tags":[1]}', "failed"), ('{"n":2,"tags":["x"],"extra":1}', "failed")])
def test_json_schema_required_types_ranges_and_array_rules(output, status):
    schema = '{"type":"object","properties":{"n":{"type":"integer","minimum":1,"maximum":3},"tags":{"type":"array","items":{"type":"string","minLength":1},"minItems":1}},"required":["n","tags"],"additionalProperties":false}'
    result = evaluate(case('{"n":2,"tags":["x"]}'), profile("json_schema", schema), output)
    assert result.status == status and result.checks_ran == ("json", "json_schema")


def test_case_content_is_data_and_diagnostics_do_not_disclose_it(tmp_path):
    marker = tmp_path / "never-created"
    text = f"__import__('pathlib').Path({str(marker)!r}).touch()"
    assert evaluate(case(text), profile(), text).status == "passed"
    assert not marker.exists()
    result = evaluate(case("PRIVATE_EXPECTED"), profile("json"), "PRIVATE_OUTPUT")
    assert "PRIVATE" not in result.model_dump_json()
    assert result.model_dump_json() == evaluate(case("PRIVATE_EXPECTED"), profile("json"), "PRIVATE_OUTPUT").model_dump_json()


def test_budget_exhaustion_is_inconclusive_instead_of_a_quality_failure():
    result = evaluate(case("[]"), profile("json"), "[" * 17 + "0" + "]" * 17)
    assert result.status == "inconclusive" and result.reason == "resource_limit" and result.checks_ran == ()
