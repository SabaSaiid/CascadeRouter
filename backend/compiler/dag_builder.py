"""Reconstruct the workflow graph between discovered LLM nodes.

Within each calling function, statements are walked in evaluation order along
control-flow paths:
  * data flow: B is called with a variable (or a nested call) produced by A,
  * sequence:  B is the next node function called after A on the same path.
Alternative branches (if/else, match cases, except handlers) each start from
the state before the branch, so mutually exclusive calls are never chained.
Edges that would close a cycle are dropped, so the result is always a DAG.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Iterable, Optional

from backend.compiler.ast_scanner import DiscoveredCall


@dataclass(frozen=True)
class NodeFunction:
    file_path: str
    qualname: str
    name: str
    first_node: str
    last_node: str


def _module_stem(rel_path: str) -> str:
    path = PurePosixPath(rel_path)
    return path.parent.name if path.stem == "__init__" else path.stem


def _node_functions(calls: Iterable[DiscoveredCall]) -> tuple[list[NodeFunction], list[tuple[str, str]]]:
    """Group call sites by enclosing function; emit edges between sites of one function."""
    grouped: dict[tuple[str, str], list[DiscoveredCall]] = {}
    for c in calls:
        if c.function_name and c.qualname:
            grouped.setdefault((c.file_path, c.qualname), []).append(c)
    functions, internal = [], []
    for (file_path, qualname), sites in grouped.items():
        sites.sort(key=lambda c: (c.line_number, c.call_col))
        internal.extend((a.node_id, b.node_id) for a, b in zip(sites, sites[1:]))
        functions.append(
            NodeFunction(file_path, qualname, sites[0].function_name or "", sites[0].node_id, sites[-1].node_id)
        )
    return functions, internal


@dataclass
class _Resolver:
    """Resolves a call expression in one module to a NodeFunction, or None."""

    file_path: str
    functions: list[NodeFunction]
    imported_names: dict[str, tuple[str, str]] = field(default_factory=dict)  # alias -> (module stem, name)
    imported_modules: dict[str, str] = field(default_factory=dict)  # alias -> module stem
    class_stack: list[str] = field(default_factory=list)

    @classmethod
    def for_module(cls, file_path: str, tree: ast.Module, functions: list[NodeFunction]) -> "_Resolver":
        r = cls(file_path, functions)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    r.imported_modules[alias.asname or alias.name.split(".")[0]] = alias.name.split(".")[-1]
            elif isinstance(node, ast.ImportFrom):
                module_stem = (node.module or "").split(".")[-1]
                for alias in node.names:
                    local = alias.asname or alias.name
                    # `from pkg import module` and `from module import func` are both possible.
                    r.imported_modules.setdefault(local, alias.name)
                    r.imported_names[local] = (module_stem, alias.name)
        return r

    def _unique(self, matches: list[NodeFunction]) -> Optional[NodeFunction]:
        return matches[0] if len(matches) == 1 else None

    def resolve(self, call: ast.Call) -> Optional[NodeFunction]:
        func = call.func
        if isinstance(func, ast.Name):
            local = [f for f in self.functions if f.file_path == self.file_path and f.qualname == func.id]
            if local:
                return self._unique(local)
            imported = self.imported_names.get(func.id)
            if imported:
                stem, name = imported
                return self._unique(
                    [f for f in self.functions if f.qualname == name and _module_stem(f.file_path) == stem]
                )
            return None
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            receiver, attr = func.value.id, func.attr
            if receiver in ("self", "cls") and self.class_stack:
                qual = f"{self.class_stack[-1]}.{attr}"
                return self._unique([f for f in self.functions if f.file_path == self.file_path and f.qualname == qual])
            stem = self.imported_modules.get(receiver)
            if stem:
                return self._unique(
                    [f for f in self.functions if f.qualname == attr and _module_stem(f.file_path) == stem]
                )
        return None


def _calls_in_eval_order(expr: ast.AST) -> list[tuple[ast.Call, list[ast.Call]]]:
    """Calls in post-order (arguments before the call), each with its directly nested calls."""
    ordered: list[tuple[ast.Call, list[ast.Call]]] = []

    def visit(node: ast.AST) -> list[ast.Call]:
        if isinstance(node, (ast.Lambda, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            return []  # deferred execution: not part of this path
        produced: list[ast.Call] = []
        for child in ast.iter_child_nodes(node):
            produced.extend(visit(child))
        if isinstance(node, ast.Call):
            ordered.append((node, produced))
            return [node]
        return produced

    visit(expr)
    return ordered


@dataclass
class _PathState:
    previous: Optional[NodeFunction] = None


class _FunctionWalker:
    def __init__(self, resolver: _Resolver):
        self.resolver = resolver
        self.edges: list[tuple[str, str]] = []
        self.var_source: dict[str, set[str]] = {}

    def _handle_expr(self, expr: ast.AST, state: _PathState) -> list[NodeFunction]:
        """Process calls in `expr`; return node functions whose results the expression yields."""
        resolved: dict[int, NodeFunction] = {}
        for call, nested in _calls_in_eval_order(expr):
            target = self.resolver.resolve(call)
            if target is None:
                # Non-node calls pass node results through (e.g. json.dumps(a(...))).
                for inner in nested:
                    if id(inner) in resolved:
                        resolved[id(call)] = resolved[id(inner)]
                continue
            resolved[id(call)] = target
            sources: set[str] = set()
            for inner in nested:
                if id(inner) in resolved:
                    sources.add(resolved[id(inner)].last_node)
            for arg in [*call.args, *(kw.value for kw in call.keywords)]:
                for name in (n.id for n in ast.walk(arg) if isinstance(n, ast.Name)):
                    sources |= self.var_source.get(name, set())
            for source in sorted(sources):
                self.edges.append((source, target.first_node))
            if state.previous is not None:
                self.edges.append((state.previous.last_node, target.first_node))
            state.previous = target
        top = [resolved[id(c)] for c in ast.iter_child_nodes(expr) if isinstance(c, ast.Call) and id(c) in resolved]
        if isinstance(expr, ast.Call) and id(expr) in resolved:
            top = [resolved[id(expr)]]
        return top

    def _assign(self, targets: list[ast.expr], value: ast.expr, state: _PathState) -> None:
        if (
            len(targets) == 1
            and isinstance(targets[0], (ast.Tuple, ast.List))
            and isinstance(value, (ast.Tuple, ast.List))
            and len(targets[0].elts) == len(value.elts)
        ):
            for t, v in zip(targets[0].elts, value.elts):
                self._assign([t], v, state)
            return
        produced = self._handle_expr(value, state)
        if not produced:
            produced = [
                r for c, _ in _calls_in_eval_order(value) if (r := self.resolver.resolve(c)) is not None
            ]
        nodes = {p.last_node for p in produced}
        for target in targets:
            for name in (n.id for n in ast.walk(target) if isinstance(n, ast.Name)):
                if nodes:
                    self.var_source[name] = set(nodes)
                else:
                    self.var_source.pop(name, None)

    def walk(self, body: list[ast.stmt], state: _PathState) -> bool:
        """Walk statements; returns False when the path terminates (return/raise)."""
        for stmt in body:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            if isinstance(stmt, ast.Assign):
                self._assign(stmt.targets, stmt.value, state)
            elif isinstance(stmt, ast.AnnAssign) and stmt.value is not None:
                self._assign([stmt.target], stmt.value, state)
            elif isinstance(stmt, (ast.Return, ast.Raise)):
                if getattr(stmt, "value", None) is not None or getattr(stmt, "exc", None) is not None:
                    self._handle_expr(stmt, state)
                return False
            elif isinstance(stmt, ast.If):
                self._handle_expr(stmt.test, state)
                self._branches([stmt.body, stmt.orelse], state)
            elif isinstance(stmt, ast.Match):
                self._handle_expr(stmt.subject, state)
                alternatives = []
                for case in stmt.cases:
                    guard = [ast.Expr(case.guard)] if case.guard is not None else []
                    alternatives.append([*guard, *case.body])
                self._branches(alternatives, state, exhaustive=False)
            elif isinstance(stmt, (ast.For, ast.AsyncFor)):
                self._handle_expr(stmt.iter, state)
                self.walk(stmt.body, state)
                self.walk(stmt.orelse, state)
            elif isinstance(stmt, ast.While):
                self._handle_expr(stmt.test, state)
                self.walk(stmt.body, state)
                self.walk(stmt.orelse, state)
            elif isinstance(stmt, (ast.With, ast.AsyncWith)):
                for item in stmt.items:
                    self._handle_expr(item.context_expr, state)
                if not self.walk(stmt.body, state):
                    return False
            elif isinstance(stmt, (ast.Try, getattr(ast, "TryStar", ast.Try))):
                before = _PathState(state.previous)
                alive = self.walk(stmt.body, state)
                for handler in stmt.handlers:
                    h_state = _PathState(before.previous)
                    if handler.type is not None:
                        self._handle_expr(handler.type, h_state)
                    self.walk(handler.body, h_state)
                if alive:
                    self.walk(stmt.orelse, state)
                self.walk(stmt.finalbody, state)
                if not alive:
                    return False
            else:
                self._handle_expr(stmt, state)
        return True

    def _branches(self, alternatives: list[list[ast.stmt]], state: _PathState, exhaustive: bool = True) -> None:
        start = state.previous
        ends: list[Optional[NodeFunction]] = []
        for body in alternatives:
            branch = _PathState(start)
            if self.walk(body, branch):
                ends.append(branch.previous)
        if not exhaustive:
            ends.append(start)
        distinct = {e.first_node if e else None for e in ends}
        # After a branch the "previous" node is only known if all live paths agree.
        state.previous = ends[0] if ends and len(distinct) == 1 else None


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


def _functions_with_classes(tree: ast.Module) -> list[tuple[ast.AST, list[str]]]:
    found: list[tuple[ast.AST, list[str]]] = []

    def visit(body: list[ast.stmt], classes: list[str]) -> None:
        for stmt in body:
            if isinstance(stmt, ast.ClassDef):
                visit(stmt.body, [*classes, stmt.name])
            elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                found.append((stmt, classes))
                visit(stmt.body, classes)

    visit(tree.body, [])
    return found


def build_dag(trees: dict[str, ast.Module], calls: list[DiscoveredCall]) -> list[tuple[str, str]]:
    functions, edges = _node_functions(calls)
    if not functions:
        return []
    for rel in sorted(trees):
        resolver = _Resolver.for_module(rel, trees[rel], functions)
        for func, classes in _functions_with_classes(trees[rel]):
            resolver.class_stack = classes
            walker = _FunctionWalker(resolver)
            try:
                walker.walk(func.body, _PathState())
            except RecursionError:
                continue
            edges.extend(walker.edges)
    return _drop_cycles(edges)
