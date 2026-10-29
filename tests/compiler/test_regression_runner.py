import textwrap

from backend.compiler.ast_scanner import scan_repository
from backend.compiler.patch_generator import FilePatch, PatchSet, build_patches
from backend.compiler.regression_runner import RegressionResult, parse_pytest_output, run_regression
from backend.config import REPO_ROOT

SAMPLE = REPO_ROOT / "tests" / "fixtures" / "sample_repo"
POLICY = """version: '1.0'
nodes:
  node_classify_customer_intent:
    primary_model: small
    fallback_model: big
    routing_conditions: {enforce_json: true, required_fields: [category, confidence], max_retries: 1}
"""


def test_patched_sample_repo_passes():
    scan = scan_repository(SAMPLE)
    r = run_regression(SAMPLE, build_patches(scan.sources, scan.calls), POLICY, timeout=60)
    assert r.passed, r.log
    assert r.summary.startswith("6 passed")
    assert r.outcomes["tests/test_agent.py::test_classify_intent"] == "PASSED"
    assert "test_classify_intent PASSED" in r.log_for("classify_customer_intent")
    assert not (SAMPLE / "cascaderouter.py").exists()  # original repo untouched
    assert not (SAMPLE / ".cascaderouter.yaml").exists()


def _repo(tmp_path, test_body, app="def add(a, b):\n    return a + b\n"):
    (tmp_path / "app.py").write_text(app)
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "conftest.py").write_text(
        "import sys, pathlib\nsys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))\n")
    (tmp_path / "tests" / "test_app.py").write_text(textwrap.dedent(test_body))
    return tmp_path


def test_breaking_patch_fails(tmp_path):
    root = _repo(tmp_path, "from app import add\ndef test_add():\n    assert add(1, 2) == 3\n")
    bad = PatchSet(files={"app.py": FilePatch("app.py", "", "def add(a, b):\n    return a - b\n")})
    r = run_regression(root, bad, "nodes: {}\n", timeout=60)
    assert not r.passed and r.outcomes == {"tests/test_app.py::test_add": "FAILED"}
    assert r.summary.startswith("1 failed")


def test_no_tests_is_unverified(tmp_path):
    (tmp_path / "app.py").write_text("x = 1\n")
    r = run_regression(tmp_path, PatchSet(), "nodes: {}\n", timeout=60)
    assert not r.passed and r.summary == "no tests were collected; patch is unverified"


def test_timeout(tmp_path):
    root = _repo(tmp_path, "import time\ndef test_slow():\n    time.sleep(30)\n")
    r = run_regression(root, PatchSet(), "nodes: {}\n", timeout=2)
    assert not r.passed and r.timed_out and "timed out after 2s" in r.summary


def test_runtime_and_policy_are_vendored(tmp_path):
    root = _repo(tmp_path, """
        import pathlib
        from cascaderouter import CascadeRouter
        def test_vendored():
            r = CascadeRouter.load(pathlib.Path(__file__).parent.parent)
            assert r.rules["node_classify_customer_intent"].primary_model == "small"
    """)
    assert run_regression(root, PatchSet(), POLICY, timeout=60).passed


def test_tests_cannot_see_api_key(tmp_path, monkeypatch):
    monkeypatch.setenv("NEBIUS_API_KEY", "sk-leak")
    root = _repo(tmp_path, "import os\ndef test_env():\n    assert 'NEBIUS_API_KEY' not in os.environ\n")
    assert run_regression(root, PatchSet(), "nodes: {}\n", timeout=60).passed


def test_refuses_paths_outside_sandbox(tmp_path):
    root = _repo(tmp_path, "def test_ok():\n    pass\n")
    evil = PatchSet(files={"../escape.py": FilePatch("../escape.py", "", "x = 1\n")})
    r = run_regression(root, evil, "nodes: {}\n", timeout=60)
    assert not r.passed and r.summary == "refused to write outside the sandbox"


def test_parse_pytest_output():
    out = "PASSED tests/a.py::t1\nFAILED tests/a.py::t2 - assert 0\nERROR tests/b.py::t3\n=== 1 failed, 1 passed, 1 error in 0.5s ===\n"
    outcomes, summary = parse_pytest_output(out)
    assert outcomes == {"tests/a.py::t1": "PASSED", "tests/a.py::t2": "FAILED", "tests/b.py::t3": "ERROR"}
    assert summary == "1 failed, 1 passed, 1 error in 0.5s"
    assert parse_pytest_output("garbage") == ({}, "")


def test_log_for_falls_back_to_summary():
    r = RegressionResult(True, "3 passed in 0.1s", "", {"tests/t.py::test_other": "PASSED"})
    assert r.log_for("classify_intent") == "3 passed in 0.1s"
    assert r.log_for(None) == "3 passed in 0.1s"


def test_xpass_and_noisy_passing_suite_count_as_passed(tmp_path):
    root = _repo(tmp_path, """
        import pytest
        @pytest.mark.xfail(strict=False)
        def test_unexpectedly_fine():
            assert True
        def test_noisy():
            print("x" * 1_200_000)
    """)
    r = run_regression(root, PatchSet(), "nodes: {}\\n", timeout=60)
    assert r.passed, (r.summary, r.outcomes)
    assert r.outcomes["tests/test_app.py::test_unexpectedly_fine"] == "XPASS"
