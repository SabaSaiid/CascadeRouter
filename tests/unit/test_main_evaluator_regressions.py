"""Main's malformed-schema/example scenarios under the approved strict evaluator.

Adapted from 098b54d and b9477ba: synthetic strings only, never benchmark evidence.
The integration contract rejects malformed profiles and non-JSON envelopes;
it does not heuristically extract an answer or invent a weighted quality score.
"""

import json

import pytest

from backend.compiler.evaluator import evaluate
from backend.schemas import EvaluationProfile, LocalBenchmarkCase


@pytest.mark.parametrize("schema", [
    {"required": "x"}, {"required": [1]}, {"properties": []},
    {"properties": {"x": None}}, {"enum": None}, {"enum": "x"}, {"items": 3},
])
def test_malformed_profile_is_inconclusive_without_claiming_checks(schema):
    case = LocalBenchmarkCase(identifier="merge-test", input_text="test", expected_output='{"x":1}')
    profile = EvaluationProfile(identifier="merge-profile", version="v1", criteria_id="merge-test",
                                mechanism="json_schema", validation_schema_json=json.dumps(schema))

    result = evaluate(case, profile, '{"x":1}')

    assert result.status == "inconclusive"
    assert result.reason == "profile_unavailable"
    assert result.checks_ran == ()
    assert result.validation_status == "not_run"


@pytest.mark.parametrize("output", [
    'Example: {"x":0}\nAnswer: {"x":1}',
    '{"x":0}\n{"x":1}',
    '```json\n{"x":0}\n```\n```json\n{"x":1}\n```',
    '<think>unfinished reasoning {"x":1}',
])
def test_json_envelopes_do_not_turn_an_embedded_answer_into_success(output):
    case = LocalBenchmarkCase(identifier="merge-test", input_text="test", expected_output='{"x":1}')
    profile = EvaluationProfile(identifier="merge-profile", version="v1", criteria_id="merge-test",
                                mechanism="json")

    result = evaluate(case, profile, output)

    assert result.status == "failed"
    assert result.reason == "invalid_json"
    assert result.checks_ran == ("json",)
    assert result.validation_status == "failed"
