"""CI-required client checks must fail, rather than silently skip, without Node."""
from types import SimpleNamespace
import pytest
import acceptance_support


def outcome():
    try:
        acceptance_support.node24()
    except pytest.skip.Exception:
        return "skipped"
    except pytest.fail.Exception:
        return "failed"
    return "available"


def test_required_missing_node_is_a_failure(monkeypatch):
    monkeypatch.setenv("CASCADEROUTER_REQUIRE_NODE_ACCEPTANCE", "1")
    monkeypatch.setattr(acceptance_support.shutil, "which", lambda _name: None)
    assert outcome() == "failed"


@pytest.mark.parametrize("flag,expected", [(None,"skipped"),("0","skipped"),("1","failed"),("invalid","failed")])
def test_missing_tool_has_explicit_optional_or_required_outcome(monkeypatch, flag, expected):
    monkeypatch.delenv("CASCADEROUTER_REQUIRE_NODE_ACCEPTANCE", raising=False)
    if flag is not None: monkeypatch.setenv("CASCADEROUTER_REQUIRE_NODE_ACCEPTANCE", flag)
    monkeypatch.setattr(acceptance_support.shutil, "which", lambda _name: None)
    assert outcome() == expected


@pytest.mark.parametrize("version", ["v20.19.0", "PRIVATE_INVALID_VERSION"])
def test_required_unsupported_or_invalid_node_is_a_controlled_failure(monkeypatch, version):
    monkeypatch.setenv("CASCADEROUTER_REQUIRE_NODE_ACCEPTANCE", "1")
    monkeypatch.setattr(acceptance_support.shutil, "which", lambda _name: "test-node")
    monkeypatch.setattr(acceptance_support.subprocess, "run", lambda *_args, **_kwargs: SimpleNamespace(stdout=version, returncode=0))
    assert outcome() == "failed"


def test_unrunnable_required_node_does_not_leak_raw_probe_exception(monkeypatch):
    monkeypatch.setenv("CASCADEROUTER_REQUIRE_NODE_ACCEPTANCE", "1")
    monkeypatch.setattr(acceptance_support.shutil, "which", lambda _name: "test-node")
    def fail(*_args, **_kwargs): raise OSError("PRIVATE_PROBE_ERROR")
    monkeypatch.setattr(acceptance_support.subprocess, "run", fail)
    with pytest.raises(pytest.fail.Exception) as error:
        acceptance_support.node24()
    assert "PRIVATE_" not in str(error.value)
