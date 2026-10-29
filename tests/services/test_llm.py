import pytest

from backend.services.llm import CompletionResult, request_key


def test_request_key_is_stable_and_order_independent():
    a = request_key("m", [{"role": "user", "content": "hi"}], {"temperature": 0, "max_tokens": 5})
    b = request_key("m", [{"content": "hi", "role": "user"}], {"max_tokens": 5, "temperature": 0})
    assert a == b and len(a) == 64


@pytest.mark.parametrize(
    "change",
    [("other", [{"role": "user", "content": "hi"}], {}), ("m", [{"role": "user", "content": "hi!"}], {}),
     ("m", [{"role": "user", "content": "hi"}], {"temperature": 1})],
)
def test_request_key_changes_with_any_field(change):
    assert request_key("m", [{"role": "user", "content": "hi"}], {}) != request_key(*change)


def test_completion_result_round_trip():
    r = CompletionResult("t", 1, 2, True, 3.5, None)
    assert CompletionResult.from_dict(r.to_dict()) == r
    r2 = CompletionResult("t", 1, 2, False, 3.5, 1.25)
    assert CompletionResult.from_dict(r2.to_dict()) == r2


def test_completion_result_from_bad_dict():
    with pytest.raises(KeyError):
        CompletionResult.from_dict({"text": "x"})
