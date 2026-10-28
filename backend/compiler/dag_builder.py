"""Provisional, evidence-based LLM data-dependency graphs; never runtime DAGs.

An edge A -> B means A's output was bound to a name (possibly through simple
aliases, field/index reads or ordered literal containers) and then read by an
argument of B in the same straight-line lexical scope. Dictionaries require
unique literal keys. File order, shared models and prompts are not evidence.
Functions have isolated flow state; class bodies are unsupported barriers.
Constructed containers can flow as a whole; selecting individual elements is
omitted because this subset does not retain element-level provenance.

Control flow, opaque calls/awaits, mutations, unpacking and dynamic transformations
are conservative barriers. No interprocedural, cross-file or heap analysis is
claimed. Cycles are rejected defensively; acyclicity applies to this subset.
These dataclasses are NOT the team's shared API/Pydantic contract. An adapter
must explicitly decide how richer evidence maps to the frontend's ID pairs.
"""

from __future__ import annotations

import ast
import os
import re
from collections import deque
from dataclasses import asdict, dataclass, field, fields, replace
from pathlib import Path, PurePosixPath
from typing import Iterator, Literal

from .ast_scanner import (
    ProvisionalLLMNode, ProvisionalScanResult, ScannerOptions, SourceFingerprint,
    _ParsedSource, _definition_expressions, _normal_windows_path,
    _scan_repository_with_sources,
)


@dataclass(frozen=True)
class GraphOptions:
    source_options: ScannerOptions = field(default_factory=ScannerOptions)
    max_nodes: int = 20_000
    max_edges: int = 10_000
    max_evidence_per_edge: int = 32
    max_analysis_steps: int = 200_000  # Per file, including lexical prepasses.
    max_expression_nodes: int = 256
    max_value_provenances: int = 128
    max_alias_depth: int = 16
    max_diagnostics: int = 1_000

    def __post_init__(self) -> None:
        if not isinstance(self.source_options, ScannerOptions):
            raise TypeError("source_options must be ScannerOptions")
        for item in fields(self):
            if item.name == "source_options":
                continue
            value = getattr(self, item.name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{item.name} must be a positive integer")


@dataclass(frozen=True, order=True)
class DependencyEvidence:
    file_path: str
    line_number: int
    column_number: int
    argument: str
    reference: str
    aliases: tuple[str, ...]


@dataclass(frozen=True)
class WorkflowEdge:
    from_node_id: str
    to_node_id: str
    kind: Literal["data_dependency"]
    evidence: tuple[DependencyEvidence, ...]


@dataclass(frozen=True)
class GraphDiagnostic:
    code: str
    message: str
    file_path: str | None = None
    line_number: int | None = None
    column_number: int | None = None


@dataclass(frozen=True)
class ProvisionalWorkflowGraph:
    repository_path: str
    node_ids: tuple[str, ...]
    edges: tuple[WorkflowEdge, ...]
    verified_sources: tuple[SourceFingerprint, ...]
    diagnostics: tuple[GraphDiagnostic, ...]
    complete: bool

    def to_dict(self) -> dict[str, object]:
        def lists(value: object) -> object:
            if isinstance(value, dict):
                return {key: lists(item) for key, item in value.items()}
            if isinstance(value, (list, tuple)):
                return [lists(item) for item in value]
            return value

        return {key: lists(value) for key, value in asdict(self).items()}


def _valid_path(value: str) -> bool:
    if not isinstance(value, str) or not value or len(value) > 4096 or "\\" in value or ":" in value:
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and ".." not in path.parts and path.as_posix() == value


def _identity(node: ProvisionalLLMNode) -> tuple[object, ...]:
    return (node.node_id, node.file_path, node.line_number, node.column_number,
            node.call_signature, node.function_name)


class _FlowLimit(Exception):
    pass


class _ExpressionLimit(Exception):
    def __init__(self, node: ast.AST) -> None:
        self.node = node


@dataclass(frozen=True)
class _Trace:
    producer: str
    aliases: tuple[str, ...] = ()
    reference: str = ""
    line: int = 0
    column: int = 0


@dataclass(frozen=True)
class _Value:
    traces: frozenset[_Trace] = frozenset()
    blocked: bool = False
    aggregate: bool = False  # Constructed container, not an opaque LLM output.


class _Scope:
    def __init__(self, locals_: set[str], outer_names: set[str]) -> None:
        self.bindings = dict.fromkeys(locals_, _Value())
        self.outer_names = outer_names
        self.invalidated: set[str] = set()


class _GraphBuild:
    def __init__(self, scan: ProvisionalScanResult, options: GraphOptions) -> None:
        self.scan = scan
        self.options = options
        self.expected: dict[str, list[ProvisionalLLMNode]] = {}
        self.fingerprints: dict[str, SourceFingerprint] = {}
        self.nodes: tuple[str, ...] = ()
        self.edges: dict[tuple[str, str], set[DependencyEvidence]] = {}
        self.verified: list[SourceFingerprint] = []
        self.seen: set[str] = set()
        self.diagnostics: list[GraphDiagnostic] = []
        self.diagnostic_keys: set[tuple[object, ...]] = set()
        self.issue = False

    def report(
        self, code: str, message: str, path: str | None = None,
        node: ast.AST | None = None,
        *, line_number: int | None = None,
    ) -> None:
        self.issue = True
        key = (code, path, getattr(node, "lineno", line_number), getattr(node, "col_offset", None))
        if key in self.diagnostic_keys:
            return
        if len(self.diagnostics) >= self.options.max_diagnostics:
            self.diagnostics[-1] = GraphDiagnostic("diagnostic_limit", "Additional graph diagnostics were omitted.")
            return
        self.diagnostic_keys.add(key)
        self.diagnostics.append(GraphDiagnostic(code, message, path, key[2], key[3]))

    def validate(self) -> bool:
        if len(self.scan.nodes) > self.options.max_nodes:
            self.report("node_limit", "Scanner node count exceeds the graph node budget.")
            return False
        identifiers: set[str] = set()
        locations: set[tuple[object, ...]] = set()
        valid = True
        for node in self.scan.nodes:
            location = (node.file_path, node.line_number, node.column_number)
            if (
                not _valid_path(node.file_path)
                or not isinstance(node.node_id, str)
                or re.fullmatch(r"llm_[0-9a-f]{24}", node.node_id) is None
                or type(node.line_number) is not int or node.line_number < 1
                or type(node.column_number) is not int or node.column_number < 0
                or node.node_id in identifiers or location in locations
            ):
                self.report("invalid_scanner_node", "Scanner identities or locations are invalid or duplicated.")
                valid = False
                continue
            identifiers.add(node.node_id)
            locations.add(location)
            self.expected.setdefault(node.file_path, []).append(node)
        self.nodes = tuple(node.node_id for node in sorted(
            (node for nodes in self.expected.values() for node in nodes),
            key=lambda item: (item.file_path, item.line_number, item.column_number, item.node_id),
        ))
        if len(self.scan.source_fingerprints) > self.options.max_nodes:
            self.report("fingerprint_limit", "Source fingerprint count exceeds the graph input budget.")
            return False
        for fingerprint in self.scan.source_fingerprints:
            if (
                not _valid_path(fingerprint.file_path)
                or not isinstance(fingerprint.sha256, str)
                or re.fullmatch(r"[0-9a-f]{64}", fingerprint.sha256) is None
                or fingerprint.file_path in self.fingerprints
            ):
                self.report("invalid_source_fingerprint", "Source-version evidence is invalid or duplicated.")
                valid = False
                continue
            self.fingerprints[fingerprint.file_path] = fingerprint
        if any(path not in self.fingerprints for path in self.expected):
            self.report("missing_source_fingerprint", "Rescan with the current scanner to obtain source-version evidence.")
            valid = False
        if not isinstance(self.scan.source_options, ScannerOptions):
            self.report("invalid_source_options", "The scanner's source limits are unavailable.")
            valid = False
        if not self.scan.complete or self.scan.diagnostics:
            self.report("input_scan_incomplete", "The supplied scan reported incomplete coverage.")
        return valid

    def source(self, parsed: _ParsedSource) -> None:
        path = parsed.fingerprint.file_path
        self.seen.add(path)
        if self.fingerprints.get(path) != parsed.fingerprint:
            self.report("source_changed", "Source is new or changed since the supplied scan; no edges were inferred for it.", path)
            return
        expected = sorted((_identity(node) for node in self.expected.get(path, [])))
        actual = sorted((_identity(node) for node in parsed.nodes))
        if expected != actual:
            self.report("call_sites_mismatch", "Source call sites do not match the supplied scanner nodes; file edges were omitted.", path)
            return
        if len(parsed.calls) != len(parsed.nodes) or len(set(parsed.calls)) != len(parsed.calls):
            self.report("call_objects_mismatch", "Confirmed source call objects are inconsistent; file edges were omitted.", path)
            return
        self.verified.append(parsed.fingerprint)
        if not parsed.nodes:
            return
        analyzer = _Flow(self, parsed)
        try:
            analyzer.run()
        except _ExpressionLimit as error:
            self.report("expression_limit", "Expression budget reached; file edges were omitted.", path, error.node)
            return
        except (_FlowLimit, RecursionError, MemoryError):
            self.report("flow_analysis_limit", "Data-flow work or recursion limit reached; file edges were omitted.", path)
            return
        # File-local work is transactional: budget failures never retain edges
        # from a partially analyzed file.
        for endpoints, evidence in sorted(analyzer.edges.items()):
            if endpoints not in self.edges and len(self.edges) >= self.options.max_edges:
                self.report("edge_limit", "Graph edge budget reached; additional dependencies were omitted.", path)
                break
            self.edges.setdefault(endpoints, set()).update(evidence)

    def finish(self, repository_path: str) -> ProvisionalWorkflowGraph:
        # Defensive endpoint/cycle checks. Normal inference only points from an
        # already evaluated producer to a consumer in the same lexical scope.
        outgoing: dict[str, list[str]] = {identifier: [] for identifier in self.nodes}
        indegree = dict.fromkeys(self.nodes, 0)
        inconsistent = False
        for source, target in self.edges:
            if source not in indegree or target not in indegree or source == target:
                inconsistent = True
                continue
            outgoing[source].append(target)
            indegree[target] += 1
        ready = deque(identifier for identifier, count in indegree.items() if count == 0)
        visited = 0
        while ready:
            identifier = ready.popleft()
            visited += 1
            for target in outgoing[identifier]:
                indegree[target] -= 1
                if indegree[target] == 0:
                    ready.append(target)
        if inconsistent or visited != len(indegree):
            self.report("inconsistent_graph", "Invalid endpoints or a cycle were detected; all graph edges were rejected.")
            self.edges.clear()
        return ProvisionalWorkflowGraph(
            repository_path, self.nodes,
            tuple(WorkflowEdge(source, target, "data_dependency", tuple(sorted(evidence)))
                  for (source, target), evidence in sorted(self.edges.items())),
            tuple(sorted(self.verified, key=lambda item: item.file_path)),
            tuple(sorted(self.diagnostics, key=lambda item: (
                item.file_path or "", item.line_number or 0, item.column_number or 0, item.code,
            ))),
            not self.issue,
        )


class _Flow:
    def __init__(self, build: _GraphBuild, parsed: _ParsedSource) -> None:
        self.build = build
        self.options = build.options
        self.path = parsed.fingerprint.file_path
        self.tree = parsed.tree
        # Nested calls can share a start position. Match the exact AST objects
        # confirmed by the scanner, never every Call with the same line/column.
        self.calls = {call: node.node_id for call, node in zip(parsed.calls, parsed.nodes)}
        self.steps = 0
        self.scope = _Scope(set(), set())
        self.edges: dict[tuple[str, str], set[DependencyEvidence]] = {}

    def tick(self) -> None:
        self.steps += 1
        if self.steps > self.options.max_analysis_steps:
            raise _FlowLimit

    def report(self, code: str, message: str, node: ast.AST) -> None:
        self.build.report(code, message, self.path, node)

    def walk(self, roots: list[ast.AST]) -> Iterator[ast.AST]:
        pending = list(reversed(roots))
        while pending:
            self.tick()
            node = pending.pop()
            yield node
            pending.extend(reversed(list(ast.iter_child_nodes(node))))

    def bound_names(self, roots: list[ast.AST]) -> set[str]:
        names: set[str] = set()
        pending = list(roots)
        while pending:
            self.tick()
            node = pending.pop()
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                names.add(node.name)
                pending.extend(_definition_expressions(node))
                continue
            if isinstance(node, ast.ClassDef):
                names.add(node.name)
                pending.extend([*node.decorator_list, *node.bases, *node.keywords])
                continue
            if isinstance(node, ast.Lambda):
                pending.extend(item for item in [*node.args.defaults, *node.args.kw_defaults] if item is not None)
                continue
            if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
                names.add(node.id)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                names.update(alias.asname or alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, (ast.Global, ast.Nonlocal)):
                names.update(node.names)
            elif isinstance(node, (ast.ExceptHandler, ast.MatchAs, ast.MatchStar)) and node.name:
                names.add(node.name)
            elif isinstance(node, ast.MatchMapping) and node.rest:
                names.add(node.rest)
            pending.extend(ast.iter_child_nodes(node))
        return names

    def run(self) -> None:
        self.scope = _Scope(self.bound_names(list(self.tree.body)), set())
        self.block(self.tree.body)

    def merge(self, values: list[_Value], node: ast.AST) -> _Value:
        traces: set[_Trace] = set()
        blocked = False
        aggregate = False
        for value in values:
            traces.update(trace for trace in value.traces if trace.producer not in self.scope.invalidated)
            blocked |= value.blocked or any(trace.producer in self.scope.invalidated for trace in value.traces)
            aggregate |= value.aggregate
            if len(traces) > self.options.max_value_provenances:
                self.report("value_provenance_limit", "Value provenance budget reached; this dependency remains unresolved.", node)
                return _Value(blocked=True)
        return _Value(frozenset(traces), blocked, aggregate)

    def barrier(self, node: ast.AST, code: str = "control_flow_boundary") -> _Value:
        related = any(value.traces for value in self.scope.bindings.values())
        contains_call = any(isinstance(item, ast.Call) and item in self.calls
                            for item in self.walk([node]))
        names = self.bound_names([node])
        for name, value in list(self.scope.bindings.items()):
            if value.traces:
                self.scope.invalidated.update(trace.producer for trace in value.traces)
                self.scope.bindings[name] = _Value(blocked=True)
        for name in names:
            self.scope.bindings[name] = _Value(blocked=True)
        if related or contains_call:
            self.report(code, "Dependencies across unsupported control flow or dynamic behavior were omitted.", node)
        return _Value(blocked=True)

    def bind(self, target: ast.AST, value: _Value) -> None:
        if isinstance(target, ast.Name):
            if len(target.id) > 128:
                self.scope.bindings[target.id] = _Value(blocked=True)
                self.report("reference_limit", "An oversized identifier was omitted from graph evidence.", target)
                return
            traces = set()
            for trace in value.traces:
                aliases = trace.aliases + (target.id,)
                if len(aliases) > self.options.max_alias_depth:
                    self.scope.bindings[target.id] = _Value(blocked=True)
                    self.report("alias_limit", "Alias-chain limit reached; this dependency remains unresolved.", target)
                    return
                traces.add(replace(trace, aliases=aliases, reference=target.id,
                                   line=target.lineno, column=target.col_offset))
            self.scope.bindings[target.id] = self.merge([_Value(frozenset(traces), value.blocked, value.aggregate)], target)
        elif isinstance(target, (ast.Tuple, ast.List, ast.Starred)):
            # Iteration and target setters can have side effects, even when the
            # RHS has no currently known producer references.
            self.barrier(target, "complex_assignment")
            if value.traces or value.blocked:
                self.report("complex_assignment", "Unpacking assignments are not used as producer evidence.", target)
        else:
            self.barrier(target, "mutation_boundary")

    def target_expressions(self, target: ast.AST) -> None:
        if isinstance(target, (ast.Tuple, ast.List)):
            for element in target.elts:
                self.target_expressions(element)
        elif isinstance(target, ast.Starred):
            self.target_expressions(target.value)
        elif isinstance(target, ast.Attribute):
            self.expression(target.value)
        elif isinstance(target, ast.Subscript):
            self.expression(target.value)
            self.expression(target.slice)

    def block(self, statements: list[ast.stmt]) -> None:
        for node in statements:
            self.tick()
            if isinstance(node, ast.Assign):
                value = self.expression(node.value)
                for target in node.targets:
                    self.target_expressions(target)
                    self.bind(target, value)
            elif isinstance(node, ast.AnnAssign):
                if node.value is not None:
                    value = self.expression(node.value)
                    self.target_expressions(node.target)
                    self.bind(node.target, value)
                self.expression(node.annotation)
            elif isinstance(node, (ast.AugAssign, ast.Delete)):
                self.barrier(node, "mutation_boundary")
            elif isinstance(node, ast.Expr):
                self.expression(node.value)
            elif isinstance(node, ast.ClassDef):
                self.barrier(node, "class_boundary")
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                defaults = {item for item in [*node.args.defaults, *node.args.kw_defaults]
                            if item is not None}
                for expression in _definition_expressions(node):
                    value = self.expression(expression)
                    if expression in defaults and value.traces:
                        self.report("default_value_boundary", "Producer values passed through function defaults are not resolved across scopes.", expression)
                if node.decorator_list:
                    self.barrier(node, "decorator_boundary")
                outer = self.scope
                outer.bindings[node.name] = _Value()
                names = self.bound_names(list(node.body))
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    names.update(argument.arg for argument in [
                        *node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs,
                        *([node.args.vararg] if node.args.vararg else []),
                        *([node.args.kwarg] if node.args.kwarg else []),
                    ])
                outer_names = outer.outer_names | {
                    name for name, value in outer.bindings.items() if value.traces
                }
                self.scope = _Scope(names, outer_names)
                self.block(node.body)
                self.scope = outer
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                self.barrier(node, "import_boundary")
                for alias in node.names:
                    if alias.name == "*":
                        self.barrier(node, "wildcard_boundary")
                    else:
                        self.scope.bindings[alias.asname or alias.name.split(".")[0]] = _Value()
            elif isinstance(node, (ast.Return, ast.Raise)):
                value = node.value if isinstance(node, ast.Return) else node.exc
                self.expression(value)
                break
            elif isinstance(node, (ast.Global, ast.Nonlocal)):
                for name in node.names:
                    self.scope.bindings[name] = _Value(blocked=True)
            elif not isinstance(node, ast.Pass):
                self.barrier(node)

    def expression(self, node: ast.AST | None) -> _Value:
        if node is None:
            return _Value()
        # All nested work for this expression shares one syntactic node budget.
        for count, _ in enumerate(self.walk([node]), 1):
            if count > self.options.max_expression_nodes:
                raise _ExpressionLimit(node)
        return self.value(node)

    def value(self, node: ast.AST) -> _Value:
        self.tick()
        if isinstance(node, ast.Constant):
            return _Value()
        if isinstance(node, ast.Name):
            value = self.scope.bindings.get(node.id)
            if value is None and node.id in self.scope.outer_names:
                self.report("cross_scope_dependency", "Captured producer values are not resolved across lexical scopes.", node)
                return _Value(blocked=True)
            if len(node.id) > 128:
                self.report("reference_limit", "An oversized identifier was omitted from graph evidence.", node)
                return _Value(blocked=True)
            value = value or _Value()
            return self.merge([_Value(frozenset(
                replace(trace, reference=node.id, line=node.lineno, column=node.col_offset)
                for trace in value.traces
            ), value.blocked, value.aggregate)], node)
        if isinstance(node, ast.Await):
            value = self.value(node.value)
            if isinstance(node.value, ast.Call) and node.value in self.calls:
                return value
            # An unknown awaitable can execute arbitrary __await__ code. Only
            # directly awaited, scanner-confirmed SDK calls are modeled here.
            return self.barrier(node, "opaque_await_boundary")
        if isinstance(node, (ast.Attribute, ast.Subscript)):
            base = self.value(node.value)
            if base.aggregate:
                return self.barrier(node, "container_selection")
            if not base.traces and not isinstance(node.value, (ast.Constant, ast.List, ast.Tuple, ast.Dict)):
                return self.barrier(node, "opaque_selector")
            if isinstance(node, ast.Subscript):
                index = self.value(node.slice)
                if index.traces or index.blocked:
                    return self.barrier(node, "dynamic_index")
            reference = _reference(node)
            return self.merge([_Value(frozenset(
                replace(trace, reference=reference or trace.reference,
                        line=node.lineno, column=node.col_offset) for trace in base.traces
            ), base.blocked)], node)
        if isinstance(node, (ast.List, ast.Tuple)):
            return replace(self.merge([self.value(item) for item in node.elts], node), aggregate=True)
        if isinstance(node, ast.Dict):
            if any(key is None for key in node.keys):
                return self.barrier(node, "unpacking_boundary")
            # Only exact builtin literal keys are compared. A dynamic or
            # duplicate key can overwrite the producer-bearing entry.
            keys: set[object] = set()
            for key in node.keys:
                if not isinstance(key, ast.Constant) or type(key.value) not in (str, bytes, int, float, complex, bool, type(None)):
                    return self.barrier(node, "ambiguous_container")
                if key.value in keys:
                    return self.barrier(node, "ambiguous_container")
                keys.add(key.value)
            values = []
            for key, value in zip(node.keys, node.values):
                if key is not None:
                    values.append(self.value(key))
                values.append(self.value(value))
            return replace(self.merge(values, node), aggregate=True)
        if isinstance(node, ast.NamedExpr):
            value = self.value(node.value)
            self.bind(node.target, value)
            return self.scope.bindings.get(node.target.id, _Value(blocked=True))
        if isinstance(node, ast.Call):
            identifier = self.calls.get(node)
            if any(keyword.arg is None for keyword in node.keywords) or any(isinstance(item, ast.Starred) for item in node.args):
                self.barrier(node, "unpacking_boundary")
                return _Value(frozenset({_Trace(identifier)})) if identifier else _Value(blocked=True)
            if identifier is None:
                self.value(node.func)
            else:
                receiver = node.func
                while isinstance(receiver, ast.Attribute):
                    receiver = receiver.value
                if not isinstance(receiver, ast.Name):
                    self.value(receiver)
            arguments = [(f"arg:{index}", self.value(value)) for index, value in enumerate(node.args)]
            arguments.extend((keyword.arg or "**kwargs", self.value(keyword.value)) for keyword in node.keywords)
            if identifier is None:
                self.barrier(node, "opaque_call_boundary")
                return _Value(blocked=True)
            for argument, value in arguments:
                self.consume(identifier, argument, self.merge([value], node), node)
            return _Value(frozenset({_Trace(identifier)}))
        return self.barrier(node, "unsupported_expression")

    def consume(self, consumer: str, argument: str, value: _Value, node: ast.Call) -> None:
        if value.blocked:
            self.report("unresolved_input", "A call input crosses unsupported data flow; no dependency was invented for it.", node)
        for trace in sorted(value.traces, key=lambda item: (
            item.producer, item.reference, item.aliases, item.line, item.column,
        )):
            if not trace.aliases:
                self.report("unbound_producer", "Direct nested results require an explicit name assignment in this subset.", node)
                continue
            if trace.producer == consumer:
                self.report("self_dependency", "Self-referential evidence was rejected.", node)
                continue
            key = (trace.producer, consumer)
            if key not in self.edges and len(self.edges) >= self.options.max_edges:
                self.report("edge_limit", "File edge budget reached; additional dependencies were omitted.", node)
                continue
            evidence = self.edges.setdefault(key, set())
            if len(evidence) >= self.options.max_evidence_per_edge:
                self.report("edge_evidence_limit", "Additional supporting references were omitted at the evidence limit.", node)
                continue
            evidence.add(DependencyEvidence(
                self.path, trace.line, trace.column, argument[:128],
                trace.reference[:256], trace.aliases,
            ))


def _reference(node: ast.AST) -> str:
    parts: list[str] = []
    for _ in range(16):
        if isinstance(node, ast.Attribute):
            parts.append("." + node.attr)
            node = node.value
        elif isinstance(node, ast.Subscript):
            parts.append("[]")  # Never disclose a string literal used as a key.
            node = node.value
        elif isinstance(node, ast.Name):
            reference = node.id + "".join(reversed(parts))
            return reference if len(reference) <= 256 else ""
        else:
            break
    return ""


def build_workflow_graph(
    repository_path: str, scan_result: ProvisionalScanResult,
    options: GraphOptions | None = None,
) -> ProvisionalWorkflowGraph:
    """Infer same-scope, assignment-supported dependencies from verified sources.

    Sources are rechecked through the scanner's exact guarded I/O/parse pipeline,
    with limits no weaker than either the supplied scan or GraphOptions. Raw
    SHA-256 fingerprints detect edits even when call IDs/locations are unchanged.
    Missing legacy fingerprints require a new scan. Each file is transactional.
    ``complete`` covers only the explicitly documented static inference subset;
    it never asserts a complete runtime execution graph or an atomic repo snapshot.
    """
    if not isinstance(scan_result, ProvisionalScanResult):
        raise TypeError("scan_result must be ProvisionalScanResult")
    options = options or GraphOptions()
    build = _GraphBuild(scan_result, options)
    if not build.validate():
        return build.finish(scan_result.repository_path)
    limits = ScannerOptions(**{
        item.name: min(getattr(scan_result.source_options, item.name), getattr(options.source_options, item.name))
        for item in fields(ScannerOptions)
    })
    fresh = _scan_repository_with_sources(repository_path, limits, build.source)
    for diagnostic in fresh.diagnostics:
        build.report("source_" + diagnostic.code, diagnostic.message, diagnostic.file_path,
                     line_number=diagnostic.line_number)
    for path in sorted(set(build.fingerprints) - build.seen):
        build.report("source_unavailable", "A previously scanned source could not be verified; its edges were omitted.", path)
    normalize = _normal_windows_path if os.name == "nt" else Path
    if normalize(fresh.repository_path) != normalize(scan_result.repository_path):
        build.report("repository_mismatch", "The selected root does not match the supplied scan; all edges were rejected.")
        build.edges.clear()
        build.verified.clear()
    return build.finish(fresh.repository_path)
