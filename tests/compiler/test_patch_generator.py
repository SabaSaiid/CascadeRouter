import ast
import textwrap

import pytest

from backend.compiler.ast_scanner import scan_module, scan_repository
from backend.compiler.patch_generator import (
    IMPORT_LINE,
    LOADER_LINE,
    PatchError,
    build_patches,
    node_diff,
    patch_source,
)
from backend.config import REPO_ROOT

SAMPLE = REPO_ROOT / "tests" / "fixtures" / "sample_repo"


def calls_for(src, path="app.py"):
    return scan_module(ast.parse(src), src, path)


def test_sample_repo_patch():
    scan = scan_repository(SAMPLE)
    ps = build_patches(scan.sources, scan.calls)
    assert ps.errors == {} and list(ps.files) == ["agent/workflow.py"]
    patched = ps.files["agent/workflow.py"].patched
    ast.parse(patched)
    assert patched.count(IMPORT_LINE) == 1 and patched.count(LOADER_LINE) == 1
    assert patched.count("cascade_router.dispatch(") == 3
    assert "client.chat.completions.create(" not in patched
    assert 'node_id="node_extract_ticket_metadata",' in patched
    assert "model=ULTRA_MODEL," in patched  # original arguments preserved
    diff = ps.combined_diff()
    assert diff.startswith("--- a/agent/workflow.py\n+++ b/agent/workflow.py\n")
    assert diff.count("-    response = client.chat.completions.create(") == 1


def test_import_goes_after_imports_and_docstring():
    src = '"""Doc."""\nimport os\nfrom openai import OpenAI\n\nX = 1\ndef f(c):\n    return c.chat.completions.create(model="m", messages=[])\n'
    out = patch_source(src, calls_for(src))
    lines = out.splitlines()
    assert lines[:5] == ['"""Doc."""', "import os", "from openai import OpenAI", IMPORT_LINE, LOADER_LINE]


def test_module_without_imports_or_trailing_newline():
    src = 'def f(c):\n    return c.chat.completions.create(model="m", messages=[])'
    out = patch_source(src, calls_for(src))
    assert out.startswith(IMPORT_LINE + "\n" + LOADER_LINE + "\n")
    ast.parse(out)


def test_inline_and_no_arg_calls():
    src = "import openai\ndef f(c):\n    return c.chat.completions.create(model='m')\ndef g(c):\n    return c.chat.completions.create()\n"
    out = patch_source(src, calls_for(src))
    assert "cascade_router.dispatch(node_id=\"node_f\", client=c, model='m')" in out
    assert 'cascade_router.dispatch(node_id="node_g", client=c)' in out


def test_complex_client_expression_and_unicode():
    src = 'import openai\n# héllo ✓\ndef f(self):\n    s = "ünïcode"\n    return self.clients["x"].chat.completions.create(model="m", messages=[{"role": "user", "content": s}])\n'
    out = patch_source(src, calls_for(src))
    assert 'client=self.clients["x"], model="m"' in out
    ast.parse(out)


def test_async_call_uses_dispatch_async():
    src = "import openai\nasync def f(c):\n    return await c.chat.completions.create(model='m', messages=[])\n"
    assert "await cascade_router.dispatch_async(" in patch_source(src, calls_for(src))


def test_two_calls_in_one_line_region():
    src = "import openai\ndef f(c):\n    a = c.chat.completions.create(model='x', messages=[]); b = c.chat.completions.create(model='y', messages=[])\n    return a, b\n"
    out = patch_source(src, calls_for(src))
    assert out.count("cascade_router.dispatch(") == 2
    ast.parse(out)


def test_idempotent_import_when_already_present():
    src = f"import openai\n{IMPORT_LINE}\ndef f(c):\n    return c.chat.completions.create(model='m', messages=[])\n"
    out = patch_source(src, calls_for(src))
    assert out.count(IMPORT_LINE) == 1


@pytest.mark.parametrize(
    "src,msg",
    [
        ("import openai\ncascade_router = 1\ndef f(c):\n    c.chat.completions.create(model='m')\n", "already defines"),
        ("import openai\ndef f(c):\n    c.chat.completions.create(model='m', node_id='x')\n", "reserved"),
        ("import openai\ndef f(c):\n    c.completions.create(model='m')\n", "only <client>.chat.completions.create"),
    ],
)
def test_unpatchable_calls(src, msg):
    with pytest.raises(PatchError, match=msg):
        patch_source(src, calls_for(src))


def test_stale_scan_is_detected():
    src = "import openai\ndef f(c):\n    return c.chat.completions.create(model='m', messages=[])\n"
    calls = calls_for(src)
    with pytest.raises(PatchError, match="not found"):
        patch_source("\n\n" + src, calls)


def test_build_patches_reports_bad_nodes_and_keeps_good_ones():
    src = "import openai\ndef good(c):\n    return c.chat.completions.create(model='m', messages=[])\ndef bad(c):\n    return c.responses_api.completions.create(model='m')\n"
    calls = calls_for(src)
    ps = build_patches({"app.py": src}, calls)
    assert set(ps.errors) == {"node_bad"}
    assert 'node_id="node_good"' in ps.files["app.py"].patched
    ps2 = build_patches({}, calls)
    assert ps2.errors == {"node_good": "source not available", "node_bad": "source not available"}
    assert ps2.combined_diff() == ""


def test_node_diff_isolated():
    scan = scan_repository(SAMPLE)
    diff = node_diff(scan.sources, scan.calls[0])
    assert diff.count("cascade_router.dispatch(") == 1
    assert node_diff({}, scan.calls[0]) is None


def test_build_patches_empty():
    assert build_patches({}, []).files == {}
    assert patch_source("x = 1\n", []) == "x = 1\n"
