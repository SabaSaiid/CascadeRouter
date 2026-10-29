import json
import textwrap
from pathlib import Path

import pytest

from backend.compiler.ast_scanner import scan_repository
from backend.compiler.cases import BenchmarkCase, load_cases
from backend.compiler.prompt_capture import (
    DEFAULT_MAX_OUTPUT_TOKENS,
    RESULT_MARKER,
    capture_requests,
    module_name,
    parse_harness_output,
    sanitize_request,
)
from backend.config import REPO_ROOT

SAMPLE = REPO_ROOT / "tests" / "fixtures" / "sample_repo"


def _repo(tmp_path: Path, code: str) -> Path:
    (tmp_path / "app.py").write_text("import openai\n" + textwrap.dedent(code))
    return tmp_path


def _capture(root: Path, node_id: str, cases):
    call = next(c for c in scan_repository(root).calls if c.node_id == node_id)
    return capture_requests(root, call, cases, timeout=30)


def test_sample_repo_captures_exact_prompts():
    scan = scan_repository(SAMPLE)
    cases = load_cases(SAMPLE)
    by_id = {c.node_id: c for c in scan.calls}

    classify = capture_requests(SAMPLE, by_id["node_classify_customer_intent"], cases["node_classify_customer_intent"], 30)
    assert all(r.ok for r in classify)
    req = classify[0].request
    assert req.messages[0]["role"] == "system"
    assert req.messages[0]["content"].startswith("You are a support triage classifier")
    assert req.messages[1] == {"role": "user", "content": cases["node_classify_customer_intent"][0].vars["query"]}
    assert req.params == {"temperature": 0, "max_tokens": DEFAULT_MAX_OUTPUT_TOKENS}

    extract = capture_requests(SAMPLE, by_id["node_extract_ticket_metadata"], cases["node_extract_ticket_metadata"], 30)
    assert extract[0].request.params["response_format"] == {"type": "json_object"}
    assert "ACC-48213" in extract[0].request.messages[0]["content"]  # f-string rendered

    synth = capture_requests(SAMPLE, by_id["node_generate_support_resolution"], cases["node_generate_support_resolution"], 30)
    assert synth[0].request.messages[-1] == {"role": "user", "content": "Generate fix"}
    assert synth[0].request.params["max_tokens"] == 1024
    assert "Category: tech_support" in synth[0].request.messages[1]["content"]


def test_no_cases_returns_empty():
    call = scan_repository(SAMPLE).calls[0]
    assert capture_requests(SAMPLE, call, [], 30) == []


def test_module_level_client_and_openai_constructor_are_replaced(tmp_path):
    root = _repo(tmp_path, '''
        from openai import OpenAI
        client = OpenAI(api_key="would-fail-without-stub")
        def ask(q):
            return client.chat.completions.create(model="m", messages=[{"role": "user", "content": q}])
        def ask_new(q):
            c = OpenAI()
            return c.chat.completions.create(model="m", messages=[{"role": "user", "content": q}])
    ''')
    assert _capture(root, "node_ask", [BenchmarkCase(vars={"q": "hi"})])[0].request.messages[0]["content"] == "hi"
    assert _capture(root, "node_ask_new", [BenchmarkCase(vars={"q": "yo"})])[0].ok


def test_async_function_and_broad_except(tmp_path):
    root = _repo(tmp_path, '''
        async def ask(client, q):
            try:
                return await client.chat.completions.create(model="m", messages=[{"role": "user", "content": q}])
            except Exception:
                return None  # must not swallow the capture
    ''')
    assert _capture(root, "node_ask", [BenchmarkCase(vars={"q": "x"})])[0].ok


def test_per_case_errors(tmp_path):
    root = _repo(tmp_path, '''
        def ask(client, q):
            if q == "skip":
                return "no call"
            if q == "boom":
                raise KeyError("bad")
            return client.chat.completions.create(model="m", messages=[{"role": "user", "content": q}])
    ''')
    results = _capture(root, "node_ask", [
        BenchmarkCase(vars={"q": "ok"}), BenchmarkCase(vars={"q": "skip"}),
        BenchmarkCase(vars={"q": "boom"}), BenchmarkCase(vars={"wrong": 1}),
    ])
    assert [r.ok for r in results] == [True, False, False, False]
    assert results[1].error == "the node's LLM call was not reached"
    assert results[2].error.startswith("KeyError")
    assert results[3].error.startswith("TypeError")


def test_other_llm_call_first_is_reported(tmp_path):
    root = _repo(tmp_path, '''
        def ask(client, q):
            first = client.chat.completions.create(model="a", messages=[{"role": "user", "content": "pre"}])
            return client.chat.completions.create(model="b", messages=[{"role": "user", "content": q}])
    ''')
    results = _capture(root, "node_ask__2", [BenchmarkCase(vars={"q": "x"})])
    assert results[0].error == "another LLM call ran before the node's call site"


def test_import_failure_and_missing_function(tmp_path):
    root = _repo(tmp_path, '''
        raise RuntimeError("import time failure")
        def ask(client):
            client.chat.completions.create(model="m", messages=[])
    ''')
    r = _capture(root, "node_ask", [BenchmarkCase(vars={})])
    assert r[0].error.startswith("import failed: RuntimeError")


def test_methods_are_not_capturable(tmp_path):
    root = _repo(tmp_path, '''
        class Agent:
            def ask(self, client):
                return client.chat.completions.create(model="m", messages=[{"role": "user", "content": "x"}])
    ''')
    r = _capture(root, "node_ask", [BenchmarkCase(vars={})])
    assert "not found at module level" in r[0].error


def test_timeout(tmp_path):
    root = _repo(tmp_path, '''
        import time
        def ask(client):
            time.sleep(30)
            client.chat.completions.create(model="m", messages=[])
    ''')
    call = scan_repository(root).calls[0]
    r = capture_requests(root, call, [BenchmarkCase(vars={})], timeout=1)
    assert r[0].error == "prompt capture timed out after 1s"


def test_target_cannot_see_api_key(tmp_path, monkeypatch):
    monkeypatch.setenv("NEBIUS_API_KEY", "sk-must-not-leak")
    root = _repo(tmp_path, '''
        import os
        def ask(client):
            return client.chat.completions.create(model="m", messages=[{"role": "user", "content": os.environ.get("NEBIUS_API_KEY", "absent")}])
    ''')
    assert _capture(root, "node_ask", [BenchmarkCase(vars={})])[0].request.messages[0]["content"] == "absent"


def test_forged_result_line_is_ignored(tmp_path):
    root = _repo(tmp_path, f'''
        import os, json
        def ask(client):
            print({RESULT_MARKER!r} + json.dumps([{{"ok": True, "request": {{"messages": [{{"role": "user", "content": "FORGED"}}], "max_tokens": 999999}}}}]), flush=True)
            os._exit(0)
            client.chat.completions.create(model="m", messages=[])
    ''')
    r = _capture(root, "node_ask", [BenchmarkCase(vars={})])
    assert not r[0].ok and "prompt capture failed" in r[0].error


# ------------------------------------------------------------- pure helpers


@pytest.mark.parametrize("path,expected", [("a/b.py", "a.b"), ("pkg/__init__.py", "pkg"), ("m.py", "m")])
def test_module_name(path, expected):
    assert module_name(path) == expected


@pytest.mark.parametrize("path", ["my-app/x.py", "__init__.py", "1bad.py"])
def test_module_name_rejects(path):
    with pytest.raises(ValueError):
        module_name(path)


def test_sanitize_request():
    msgs = [{"role": "user", "content": "hi", "name": "x"}]
    req, err = sanitize_request(msgs, {"temperature": 0, "max_tokens": 10**6, "tools": [1], "user": "u"}, 100)
    assert err is None
    assert req.messages == [{"role": "user", "content": "hi"}]
    assert req.params == {"temperature": 0, "max_tokens": 100}
    assert sanitize_request(msgs, {})[0].params == {"max_tokens": DEFAULT_MAX_OUTPUT_TOKENS}


@pytest.mark.parametrize(
    "messages,params",
    [
        ([], {}),
        ("x", {}),
        ([{"role": "hacker", "content": "x"}], {}),
        ([{"role": "user", "content": ["parts"]}], {}),
        ([{"role": "user", "content": "x"}], {"max_tokens": 0}),
        ([{"role": "user", "content": "x"}], {"max_tokens": True}),
        ([{"role": "user", "content": "x" * 300_000}], {}),
        ([{"role": "user", "content": "x"}] * 65, {}),
    ],
)
def test_sanitize_rejects(messages, params):
    req, err = sanitize_request(messages, params)
    assert req is None and err


def test_parse_harness_output_edge_cases():
    nonce = "n1"
    ok_line = RESULT_MARKER + nonce + json.dumps([{"ok": True, "request": {"messages": [{"role": "user", "content": "a"}]}}])
    assert parse_harness_output("noise\n" + ok_line, "", 1, nonce)[0].ok
    assert "wrong number" in parse_harness_output(ok_line, "", 2, nonce)[0].error
    assert "malformed" in parse_harness_output(RESULT_MARKER + nonce + "{bad", "", 1, nonce)[0].error
    assert parse_harness_output("", "Traceback\nNameError: x", 1, nonce)[0].error == "prompt capture failed: NameError: x"
    assert parse_harness_output(ok_line, "", 1, "other")[0].ok is False
    bad = RESULT_MARKER + nonce + json.dumps([{"ok": True, "request": {"messages": "nope"}}])
    assert not parse_harness_output(bad, "", 1, nonce)[0].ok


def test_noisy_target_output_does_not_hide_result(tmp_path):
    root = _repo(tmp_path, '''
        print("x" * 1_100_000)
        def ask(client):
            return client.chat.completions.create(model="m", messages=[{"role": "user", "content": "hi"}])
    ''')
    assert _capture(root, "node_ask", [BenchmarkCase(vars={})])[0].ok


def test_background_helper_in_target_does_not_break_capture(tmp_path):
    root = _repo(tmp_path, '''
        import subprocess, sys
        subprocess.Popen([sys.executable, "-c", "import time; time.sleep(20)"])
        def ask(client):
            return client.chat.completions.create(model="m", messages=[{"role": "user", "content": "hi"}])
    ''')
    call = scan_repository(root).calls[0]
    assert capture_requests(root, call, [BenchmarkCase(vars={})], timeout=5)[0].ok
