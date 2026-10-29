import textwrap
from pathlib import Path

from backend.compiler.ast_scanner import scan_repository
from backend.compiler.dag_builder import build_dag
from backend.config import REPO_ROOT

SAMPLE = REPO_ROOT / "tests" / "fixtures" / "sample_repo"

STEPS = '''
import openai
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


def test_same_named_function_resolves_to_local_definition(tmp_path):
    (tmp_path / "x.py").write_text('import openai\ndef a(c):\n    c.chat.completions.create(model="m")\n')
    (tmp_path / "y.py").write_text('def a(c):\n    c.chat.completions.create(model="m")\n'
                                   'def b(c):\n    c.chat.completions.create(model="m")\n'
                                   'def run(c):\n    a(c)\n    b(c)\n')
    scan = scan_repository(tmp_path)
    assert build_dag(scan.trees, scan.calls) == [("node_a__2", "node_b")]


# ------------------------------------------------------------- P2 review regressions


def test_nested_call_is_data_flow_in_eval_order(tmp_path):
    assert _dag(tmp_path, '''
        from steps import a, b
        def run(c, q):
            return b(c, a(c, q))
    ''') == [("node_a", "node_b")]


def test_nested_call_through_non_node_wrapper(tmp_path):
    assert _dag(tmp_path, '''
        import json
        from steps import a, b
        def run(c, q):
            return b(c, json.dumps(a(c, q)))
    ''') == [("node_a", "node_b")]


def test_tuple_unpacking_maps_element_wise(tmp_path):
    edges = _dag(tmp_path, '''
        from steps import a, b, d
        def run(c, q):
            x, y = a(c, q), b(c, q)
            return d(c, x)
    ''')
    assert ("node_a", "node_d") in edges and ("node_a", "node_b") in edges


def test_exclusive_branches_are_not_chained(tmp_path):
    assert _dag(tmp_path, '''
        from steps import a, b
        def run(c, q, flag):
            if flag:
                return a(c, q)
            else:
                return b(c, q)
    ''') == []


def test_branch_then_common_step(tmp_path):
    edges = _dag(tmp_path, '''
        from steps import a, b, d
        def run(c, q, flag):
            if flag:
                r = a(c, q)
            else:
                r = b(c, q)
            return d(c, r)
    ''')
    assert ("node_a", "node_b") not in edges
    assert ("node_a", "node_d") in edges and ("node_b", "node_d") in edges


def test_lambdas_are_not_sequenced(tmp_path):
    assert _dag(tmp_path, '''
        from steps import a, b
        def run(c, q):
            table = {"x": lambda: a(c, q), "y": lambda: b(c, q)}
            return table
    ''') == []


def test_library_method_with_same_name_is_not_a_node(tmp_path):
    (tmp_path / "steps.py").write_text(textwrap.dedent(STEPS) + textwrap.dedent('''
        def search(c, x):
            return c.chat.completions.create(model="m", messages=[])
    '''))
    (tmp_path / "flow.py").write_text(textwrap.dedent('''
        import re
        from steps import a, b
        def run(c, q):
            r = a(c, q)
            m = re.search("x", q)
            return b(c, r)
    '''))
    scan = scan_repository(tmp_path)
    assert build_dag(scan.trees, scan.calls) == [("node_a", "node_b")]


def test_methods_resolved_via_self(tmp_path):
    (tmp_path / "agent.py").write_text(textwrap.dedent('''
        import openai
        class Agent:
            def classify(self, q):
                return self.c.chat.completions.create(model="m", messages=[])
            def answer(self, label):
                return self.c.chat.completions.create(model="m", messages=[])
            def run(self, q):
                label = self.classify(q)
                return self.answer(label)
        class Other:
            def classify(self, q):
                return self.c.chat.completions.create(model="m", messages=[])
    '''))
    scan = scan_repository(tmp_path)
    assert build_dag(scan.trees, scan.calls) == [("node_classify", "node_answer")]


def test_multiple_calls_in_one_function_are_linked(tmp_path):
    (tmp_path / "two.py").write_text(textwrap.dedent('''
        import openai
        def pipeline(c):
            draft = c.chat.completions.create(model="m", messages=[])
            return c.chat.completions.create(model="m", messages=[{"role": "user", "content": str(draft)}])
        def after(c):
            return c.chat.completions.create(model="m", messages=[])
        def run(c):
            p = pipeline(c)
            return after(c)
    '''))
    scan = scan_repository(tmp_path)
    edges = build_dag(scan.trees, scan.calls)
    assert ("node_pipeline", "node_pipeline__2") in edges
    assert ("node_pipeline__2", "node_after") in edges  # outgoing edge from the last call site


def test_match_guard_and_except_handler(tmp_path):
    edges = _dag(tmp_path, '''
        from steps import a, b, d
        def run(c, q):
            match q:
                case "x" if a(c, q):
                    return b(c, q)
            try:
                pass
            except d(c, q):
                pass
    ''')
    assert ("node_a", "node_b") in edges


def test_unreachable_after_return_not_chained(tmp_path):
    assert _dag(tmp_path, '''
        from steps import a, b
        def run(c, q):
            return a(c, q)
            b(c, q)
    ''') == []
