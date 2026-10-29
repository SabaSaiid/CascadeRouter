import textwrap
from pathlib import Path

from backend.compiler.ast_scanner import scan_repository
from backend.compiler.dag_builder import build_dag
from backend.config import REPO_ROOT

SAMPLE = REPO_ROOT / "tests" / "fixtures" / "sample_repo"

STEPS = '''
def a(c, x):
    return c.chat.completions.create(model="m", messages=[])
def b(c, x):
    return c.chat.completions.create(model="m", messages=[])
def d(c, x):
    return c.chat.completions.create(model="m", messages=[])
'''


def _dag(tmp_path: Path, orchestrator: str):
    (tmp_path / "steps.py").write_text(textwrap.dedent(STEPS))
    (tmp_path / "flow.py").write_text(textwrap.dedent(orchestrator))
    scan = scan_repository(tmp_path)
    return build_dag(scan.trees, scan.calls)


def test_sample_repo_dag():
    scan = scan_repository(SAMPLE)
    assert build_dag(scan.trees, scan.calls) == [
        ("node_classify_customer_intent", "node_extract_ticket_metadata"),
        ("node_classify_customer_intent", "node_generate_support_resolution"),
        ("node_extract_ticket_metadata", "node_generate_support_resolution"),
    ]


def test_data_flow_and_sequence(tmp_path):
    edges = _dag(tmp_path, '''
        from steps import a, b, d
        def run(c, q):
            first = a(c, q)
            second = b(c, q)
            return d(c, first)
    ''')
    assert edges == [("node_a", "node_b"), ("node_a", "node_d"), ("node_b", "node_d")]


def test_calls_inside_compound_statements_counted_once(tmp_path):
    edges = _dag(tmp_path, '''
        import steps
        def run(c, q):
            if (r := steps.a(c, q)):
                for _ in range(2):
                    out = steps.b(c, r)
            try:
                steps.d(c, out)
            except Exception:
                pass
    ''')
    assert edges == [("node_a", "node_b"), ("node_b", "node_d")]


def test_loops_do_not_create_cycles(tmp_path):
    edges = _dag(tmp_path, '''
        from steps import a, b
        def run(c, q):
            x = q
            while True:
                x = a(c, x)
                x = b(c, x)
                x = a(c, x)
    ''')
    assert edges == [("node_a", "node_b")]


def test_unknown_or_single_function(tmp_path):
    (tmp_path / "one.py").write_text('def a(c):\n    c.chat.completions.create(model="m")\n')
    scan = scan_repository(tmp_path)
    assert build_dag(scan.trees, scan.calls) == []


def test_ambiguous_function_names_are_ignored(tmp_path):
    (tmp_path / "x.py").write_text('def a(c):\n    c.chat.completions.create(model="m")\n')
    (tmp_path / "y.py").write_text('def a(c):\n    c.chat.completions.create(model="m")\n'
                                   'def b(c):\n    c.chat.completions.create(model="m")\n'
                                   'def run(c):\n    a(c)\n    b(c)\n')
    scan = scan_repository(tmp_path)
    assert build_dag(scan.trees, scan.calls) == []
