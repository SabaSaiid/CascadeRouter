import asyncio
from types import SimpleNamespace

import pytest

from backend.runtime.cascade_router import (
    ENV_DISABLE,
    ENV_POLICY_PATH,
    POLICY_FILENAME,
    CascadeRouter,
    NodeRule,
    check_response,
)

POLICY = """
version: '1.0'
nodes:
  node_json:
    primary_model: small
    fallback_model: big
    routing_conditions: {enforce_json: true, required_fields: [category], max_retries: 1}
  node_text:
    primary_model: small
    fallback_model: big
    routing_conditions: {enforce_json: false, required_fields: [], max_retries: 1}
  node_top:
    primary_model: big
    fallback_model: big
"""


def resp(text):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])


class Client:
    """Test double: replies per model from a script; records requested models."""

    def __init__(self, replies, is_async=False):
        self.replies = replies
        self.models = []

        def create(**kwargs):
            self.models.append(kwargs.get("model"))
            reply = self.replies[kwargs.get("model")]
            if isinstance(reply, Exception):
                raise reply
            return resp(reply)

        async def acreate(**kwargs):
            return create(**kwargs)

        self.chat = SimpleNamespace(completions=SimpleNamespace(create=acreate if is_async else create))


@pytest.fixture
def router(tmp_path, monkeypatch):
    monkeypatch.delenv(ENV_POLICY_PATH, raising=False)
    monkeypatch.delenv(ENV_DISABLE, raising=False)
    (tmp_path / POLICY_FILENAME).write_text(POLICY)
    return CascadeRouter.load(tmp_path)


def test_primary_used_when_valid(router):
    c = Client({"small": '{"category": "billing"}'})
    out = router.dispatch("node_json", c, model="orig", messages=[])
    assert out.choices[0].message.content == '{"category": "billing"}'
    assert c.models == ["small"] and router.stats.primary_ok == 1


def test_escalates_on_invalid_json_or_missing_field(router):
    for bad in ("not json", '{"other": 1}', ""):
        c = Client({"small": bad, "big": '{"category": "x"}'})
        assert router.dispatch("node_json", c, model="orig").choices[0].message.content == '{"category": "x"}'
        assert c.models == ["small", "big"]
    assert router.stats.escalations == 3


def test_escalates_on_primary_exception(router):
    c = Client({"small": RuntimeError("503"), "big": "fine"})
    assert router.dispatch("node_text", c).choices[0].message.content == "fine"


def test_failing_fallback_returns_primary_response(router):
    c = Client({"small": "not json", "big": RuntimeError("down")})
    assert router.dispatch("node_json", c).choices[0].message.content == "not json"


def test_both_raise_reraises_last(router):
    c = Client({"small": RuntimeError("a"), "big": ValueError("b")})
    with pytest.raises(ValueError, match="b"):
        router.dispatch("node_json", c)


def test_unknown_node_passes_through_with_original_model(router):
    c = Client({"orig": "hi"})
    assert router.dispatch("node_missing", c, model="orig").choices[0].message.content == "hi"
    assert c.models == ["orig"] and router.stats.passthrough == 1


def test_top_tier_does_not_escalate_to_itself(router):
    c = Client({"big": ""})
    router.dispatch("node_top", c)
    assert c.models == ["big"]


def test_custom_validator(router):
    c = Client({"small": "short", "big": "long enough"})
    out = router.dispatch("node_text", c, validator=lambda r: len(r.choices[0].message.content) > 5)
    assert out.choices[0].message.content == "long enough"


def test_async_dispatch(router):
    c = Client({"small": "nope", "big": '{"category": "y"}'}, is_async=True)
    out = asyncio.run(router.dispatch_async("node_json", c, model="orig"))
    assert out.choices[0].message.content == '{"category": "y"}' and c.models == ["small", "big"]
    c2 = Client({"orig": "x"}, is_async=True)
    assert asyncio.run(router.dispatch_async("unknown", c2, model="orig")).choices[0].message.content == "x"


def test_load_walks_up_from_file(tmp_path, monkeypatch):
    monkeypatch.delenv(ENV_POLICY_PATH, raising=False)
    (tmp_path / POLICY_FILENAME).write_text(POLICY)
    module = tmp_path / "pkg" / "sub" / "m.py"
    module.parent.mkdir(parents=True)
    module.write_text("")
    r = CascadeRouter.load(str(module))
    assert set(r.rules) == {"node_json", "node_text", "node_top"}
    assert r.source == str(tmp_path / POLICY_FILENAME)


def test_env_path_and_disable(tmp_path, monkeypatch):
    p = tmp_path / "custom.yaml"
    p.write_text(POLICY)
    monkeypatch.setenv(ENV_POLICY_PATH, str(p))
    assert "node_json" in CascadeRouter.load().rules
    monkeypatch.setenv(ENV_POLICY_PATH, str(tmp_path / "missing.yaml"))
    assert CascadeRouter.load().rules == {}
    monkeypatch.setenv(ENV_DISABLE, "1")
    monkeypatch.setenv(ENV_POLICY_PATH, str(p))
    assert CascadeRouter.load().rules == {}


@pytest.mark.parametrize("content", ["a: [unclosed", "- just\n- a list\n", "!!python/object/apply:os.system ['x']"])
def test_bad_policy_means_passthrough(tmp_path, monkeypatch, content):
    monkeypatch.delenv(ENV_POLICY_PATH, raising=False)
    (tmp_path / POLICY_FILENAME).write_text(content)
    assert CascadeRouter.load(tmp_path).rules == {}


def test_missing_policy_means_passthrough(tmp_path, monkeypatch):
    monkeypatch.delenv(ENV_POLICY_PATH, raising=False)
    monkeypatch.chdir(tmp_path)
    assert CascadeRouter.load().rules == {}


def test_from_dict_skips_malformed_rules():
    r = CascadeRouter.from_dict({"nodes": {"a": "x", "b": {"fallback_model": "f"}, "c": {"primary_model": "p", "routing_conditions": {"max_retries": -3}}}})
    assert list(r.rules) == ["c"] and r.rules["c"].max_retries == 1 and r.rules["c"].fallback_model is None
    assert CascadeRouter.from_dict({}).rules == {}


def test_check_response():
    rule = NodeRule("p", "f", enforce_json=True, required_fields=("a",))
    assert check_response(rule, resp('<think>{"a": 0}</think>{"a": 1}')) is None
    assert check_response(rule, resp('```json\n{"a": 1}\n```')) is None
    assert check_response(rule, resp('[1, 2]')) == "response is not a JSON object"
    assert check_response(rule, SimpleNamespace()) == "empty response"
    assert check_response(NodeRule("p", None), resp("text")) is None


def test_events_are_bounded(router):
    c = Client({"small": "fine"})
    for _ in range(1100):
        router.dispatch("node_text", c)
    assert len(router.stats.events) == 1000
