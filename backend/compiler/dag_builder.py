"""Reconstruct the workflow graph between discovered LLM nodes.

An edge A -> B is added when, inside one calling function:
  * data flow: B's function is called with a variable holding A's result, or
  * sequence: B's function is the next node function called after A's.
Edges that would close a cycle are dropped, so the result is always a DAG.
"""

from __future__ import annotations

import ast
from typing import Iterable, Optional

from backend.compiler.ast_scanner import DiscoveredCall, attribute_chain


def _called_name(call: ast.Call) -> Optional[str]:
    chain = attribute_chain(call.func)
    return chain[-1] if chain and chain[-1] != "?" else None


def _function_to_node(calls: Iterable[DiscoveredCall]) -> dict[str, str]:
    """Map function name -> node id, only for names that are unambiguous."""
    mapping: dict[str, str] = {}
    ambiguous: set[str] = set()
    owners: dict[str, str] = {}
    for c in calls:
        if not c.function_name:
            continue
        key = c.function_name
        if key in owners and owners[key] != c.file_path:
            ambiguous.add(key)
        owners.setdefault(key, c.file_path)
        mapping.setdefault(key, c.node_id)  # first call site represents the function
    return {k: v for k, v in mapping.items() if k not in ambiguous}


def _assigned_names(target: ast.expr) -> list[str]:
    return [n.id for n in ast.walk(target) if isinstance(n, ast.Name)]


def _edges_in_function(func: ast.AST, fn_to_node: dict[str, str]) -> list[tuple[str, str]]:
    edges: list[tuple[str, str]] = []
    var_source: dict[str, str] = {}
    previous: Optional[str] = None

    for stmt in _ordered_statements(func):
        node_calls = [
            (c, fn_to_node[name])
            for c in ast.walk(stmt)
            if isinstance(c, ast.Call) and (name := _called_name(c)) in fn_to_node
        ]
        node_calls.sort(key=lambda item: (item[0].lineno, item[0].col_offset))
        for call, target_node in node_calls:
            args = list(call.args) + [kw.value for kw in call.keywords]
            for arg in args:
                for name in (n.id for n in ast.walk(arg) if isinstance(n, ast.Name)):
                    source = var_source.get(name)
                    if source and source != target_node:
                        edges.append((source, target_node))
            if previous and previous != target_node:
                edges.append((previous, target_node))
            previous = target_node

        if node_calls and isinstance(stmt, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            targets = stmt.targets if isinstance(stmt, ast.Assign) else [stmt.target]
            produced = node_calls[-1][1]
            for target in targets:
                for name in _assigned_names(target):
                    var_source[name] = produced
    return edges


_BODY_FIELDS = ("body", "orelse", "finalbody")


def _ordered_statements(func: ast.AST) -> list[ast.AST]:
    """Units to inspect, in source order.

    Simple statements are returned as-is. For compound statements (if/for/while/
    with/try/match) only the header expressions are returned, followed by the
    statements of their bodies, so no call is counted twice.
    """
    result: list[ast.AST] = []

    def walk(body: list[ast.stmt]) -> None:
        for stmt in body:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue  # nested scopes are handled on their own
            has_body = any(isinstance(getattr(stmt, f, None), list) for f in _BODY_FIELDS) or isinstance(
                stmt, ast.Match
            )
            if not has_body:
                result.append(stmt)
                continue
            for name, value in ast.iter_fields(stmt):
                if name in _BODY_FIELDS or name in ("handlers", "cases"):
                    continue
                values = value if isinstance(value, list) else [value]
                result.extend(v for v in values if isinstance(v, ast.AST))
            for f in _BODY_FIELDS:
                inner = getattr(stmt, f, None)
                if isinstance(inner, list):
                    walk(inner)
            for handler in getattr(stmt, "handlers", None) or []:
                walk(handler.body)
            for case in getattr(stmt, "cases", None) or []:
                walk(case.body)

    walk(getattr(func, "body", []))
    return result


def _drop_cycles(edges: list[tuple[str, str]]) -> list[tuple[str, str]]:
    kept: list[tuple[str, str]] = []
    adjacency: dict[str, set[str]] = {}

    def reachable(start: str, goal: str) -> bool:
        stack, seen = [start], set()
        while stack:
            cur = stack.pop()
            if cur == goal:
                return True
            if cur in seen:
                continue
            seen.add(cur)
            stack.extend(adjacency.get(cur, ()))
        return False

    for a, b in edges:
        if a == b or (a, b) in kept or reachable(b, a):
            continue
        kept.append((a, b))
        adjacency.setdefault(a, set()).add(b)
    return kept


def build_dag(
    trees: dict[str, ast.Module], calls: list[DiscoveredCall]
) -> list[tuple[str, str]]:
    fn_to_node = _function_to_node(calls)
    if len(fn_to_node) < 2:
        return []
    edges: list[tuple[str, str]] = []
    for rel in sorted(trees):
        for node in ast.walk(trees[rel]):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                edges.extend(_edges_in_function(node, fn_to_node))
    return _drop_cycles(edges)
