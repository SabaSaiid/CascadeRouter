"""Static discovery of LLM call sites using only Python's `ast` module.

Target code is parsed, never imported or executed.
"""

from __future__ import annotations

import ast
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from backend.schemas import LLMNode

logger = logging.getLogger(__name__)

SKIP_DIRS = frozenset(
    {
        ".git", ".hg", ".svn", "venv", ".venv", "env", "node_modules", "__pycache__",
        "site-packages", "build", "dist", ".tox", ".mypy_cache", ".pytest_cache",
        "tests", "test",
    }
)
MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_FILES = 500

# Attribute chains (suffixes) that denote an LLM invocation.
LLM_CALL_SUFFIXES = (
    ("chat", "completions", "create"),
    ("completions", "create"),
    ("responses", "create"),
)

FRAMEWORK_IMPORTS = {
    "openai": "OpenAI SDK",
    "langchain": "LangChain",
    "langchain_openai": "LangChain",
    "litellm": "LiteLLM",
    "anthropic": "Anthropic SDK",
}

DYNAMIC_MODEL = "<dynamic>"
UNSPECIFIED_MODEL = "<unspecified>"


class ScanPathError(ValueError):
    """The requested repository path is missing or outside the allowed roots."""


@dataclass
class DiscoveredCall:
    """Everything the later compiler stages need about one call site."""

    node_id: str
    file_path: str  # posix path relative to the scanned root
    line_number: int  # first line of the enclosing statement
    end_line_number: int
    call_line: int
    call_col: int
    call_end_line: int
    call_end_col: int
    current_model: str
    model_is_literal: bool
    call_signature: str
    function_name: Optional[str]
    docstring: Optional[str]
    prompt_reference: Optional[str]
    expected_schema: Optional[dict[str, Any]]
    json_required: bool
    max_tokens: Optional[int]
    snippet: str
    kwargs: list[str] = field(default_factory=list)

    def to_llm_node(self) -> LLMNode:
        return LLMNode(
            node_id=self.node_id,
            file_path=self.file_path,
            line_number=self.line_number,
            current_model=self.current_model,
            call_signature=self.call_signature,
            prompt_reference=self.prompt_reference,
            expected_schema=self.expected_schema,
            function_name=self.function_name,
            docstring=self.docstring,
            snippet=self.snippet,
        )


@dataclass
class RepoScan:
    root: Path
    calls: list[DiscoveredCall]
    trees: dict[str, ast.Module]  # relative path -> parsed module
    sources: dict[str, str]
    scanned_files_count: int
    detected_framework: str
    warnings: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Path safety                                                                  #
# --------------------------------------------------------------------------- #


def resolve_scan_path(raw: str, allowed_roots: list[Path], base: Path) -> Path:
    """Resolve a user-supplied path and ensure it is a directory under an allowed root."""
    if not raw or "\x00" in raw:
        raise ScanPathError("repository_path is empty or invalid")
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = base / candidate
    if candidate.is_symlink():
        raise ScanPathError("repository_path must not be a symlink")
    resolved = candidate.resolve()
    if not any(resolved == root or root in resolved.parents for root in allowed_roots):
        raise ScanPathError("repository_path is outside the allowed scan roots")
    if not resolved.is_dir():
        raise ScanPathError(f"repository_path does not exist or is not a directory: {raw}")
    return resolved


def iter_python_files(root: Path, warnings: list[str]) -> list[Path]:
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = sorted(
            d for d in dirnames
            if d not in SKIP_DIRS and not d.startswith(".") and not (Path(dirpath) / d).is_symlink()
        )
        for name in sorted(filenames):
            if not name.endswith(".py") or name.startswith("test_") or name.endswith("_test.py"):
                continue
            path = Path(dirpath) / name
            if path.is_symlink():
                continue
            if path.stat().st_size > MAX_FILE_BYTES:
                warnings.append(f"Skipped {path.relative_to(root).as_posix()}: larger than 2 MB")
                continue
            files.append(path)
            if len(files) >= MAX_FILES:
                warnings.append(f"Stopped after {MAX_FILES} files")
                return files
    return files


# --------------------------------------------------------------------------- #
# AST helpers                                                                  #
# --------------------------------------------------------------------------- #


def attribute_chain(node: ast.AST) -> list[str]:
    """`a.b.c.d` -> ['a', 'b', 'c', 'd']; anything non-trivial in the chain -> ['?', ...]."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    else:
        parts.append("?")
    return list(reversed(parts))


def is_llm_call(call: ast.Call) -> bool:
    chain = attribute_chain(call.func)
    return any(len(chain) > len(s) and tuple(chain[-len(s):]) == s for s in LLM_CALL_SUFFIXES)


def module_constants(tree: ast.Module) -> tuple[dict[str, str], dict[str, Any]]:
    """Top-level string constants and literal-evaluable dict constants."""
    strings: dict[str, str] = {}
    literals: dict[str, Any] = {}
    for stmt in tree.body:
        targets: list[ast.expr] = []
        value: Optional[ast.expr] = None
        if isinstance(stmt, ast.Assign):
            targets, value = stmt.targets, stmt.value
        elif isinstance(stmt, ast.AnnAssign) and stmt.value is not None:
            targets, value = [stmt.target], stmt.value
        if value is None:
            continue
        for target in targets:
            if not isinstance(target, ast.Name):
                continue
            try:
                evaluated = ast.literal_eval(value)
            except (ValueError, SyntaxError, TypeError, MemoryError, RecursionError):
                continue
            if isinstance(evaluated, str):
                strings[target.id] = evaluated
            elif isinstance(evaluated, dict):
                literals[target.id] = evaluated
    return strings, literals


def _local_assignments(func: Optional[ast.AST]) -> dict[str, list[ast.expr]]:
    assigned: dict[str, list[ast.expr]] = {}
    if func is None:
        return assigned
    for node in ast.walk(func):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    assigned.setdefault(target.id, []).append(node.value)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value:
            assigned.setdefault(node.target.id, []).append(node.value)
    return assigned


def _names_in(expr: ast.AST) -> list[str]:
    names = [n for n in ast.walk(expr) if isinstance(n, ast.Name)]
    names.sort(key=lambda n: (n.lineno, n.col_offset))
    return [n.id for n in names]


def find_prompt_reference(
    messages: Optional[ast.expr],
    func: Optional[ast.AST],
    string_constants: dict[str, str],
    max_depth: int = 3,
) -> Optional[str]:
    """First module-level string constant reachable from `messages` via local assignments."""
    if messages is None:
        return None
    locals_ = _local_assignments(func)
    seen: set[str] = set()
    frontier = _names_in(messages)
    for _ in range(max_depth + 1):
        next_frontier: list[str] = []
        for name in frontier:
            if name in seen:
                continue
            seen.add(name)
            if name in string_constants:
                return name
            for value in locals_.get(name, []):
                next_frontier.extend(_names_in(value))
        frontier = next_frontier
        if not frontier:
            break
    return None


def _tokens(name: Optional[str]) -> set[str]:
    if not name:
        return set()
    return {t for t in name.lower().split("_") if t and t not in {"schema", "prompt", "system", "template"}}


def find_expected_schema(
    func: Optional[ast.AST],
    response_format: Any,
    schema_constants: dict[str, Any],
    prompt_reference: Optional[str],
    function_name: Optional[str],
) -> Optional[dict[str, Any]]:
    # 1. Inline `response_format={"type": "json_schema", "json_schema": {"schema": {...}}}`.
    if isinstance(response_format, dict) and response_format.get("type") == "json_schema":
        inner = response_format.get("json_schema")
        if isinstance(inner, dict) and isinstance(inner.get("schema"), dict):
            return inner["schema"]

    candidates = {k: v for k, v in schema_constants.items() if k.upper().endswith("SCHEMA")}
    if not candidates:
        return None

    # 2. A *_SCHEMA constant referenced inside the enclosing function.
    if func is not None:
        for name in _names_in(func):
            if name in candidates:
                return candidates[name]

    # 3. Best token overlap with the prompt constant / function name.
    wanted = _tokens(prompt_reference) | _tokens(function_name)
    best_name, best_score = None, 0
    for name in sorted(candidates):
        score = len(_tokens(name) & wanted)
        if score > best_score:
            best_name, best_score = name, score
    return candidates[best_name] if best_name else None


# --------------------------------------------------------------------------- #
# Visitor                                                                      #
# --------------------------------------------------------------------------- #


class _CallVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.func_stack: list[ast.AST] = []
        self.stmt_stack: list[ast.stmt] = []
        self.found: list[tuple[ast.Call, Optional[ast.AST], ast.stmt]] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_scope(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_scope(node)

    def _visit_scope(self, node: ast.AST) -> None:
        self.func_stack.append(node)
        self.generic_visit(node)
        self.func_stack.pop()

    def generic_visit(self, node: ast.AST) -> None:
        is_stmt = isinstance(node, ast.stmt)
        if is_stmt:
            self.stmt_stack.append(node)
        if isinstance(node, ast.Call) and is_llm_call(node):
            func = self.func_stack[-1] if self.func_stack else None
            self.found.append((node, func, self.stmt_stack[-1]))
        super().generic_visit(node)
        if is_stmt:
            self.stmt_stack.pop()


def _kwarg(call: ast.Call, name: str) -> Optional[ast.expr]:
    for kw in call.keywords:
        if kw.arg == name:
            return kw.value
    return None


def _literal(expr: Optional[ast.expr]) -> Any:
    if expr is None:
        return None
    try:
        return ast.literal_eval(expr)
    except (ValueError, SyntaxError, TypeError, MemoryError, RecursionError):
        return None


def _call_signature(call: ast.Call) -> str:
    func = ".".join(attribute_chain(call.func))
    parts = ["..." for _ in call.args]
    for kw in call.keywords:
        if kw.arg is None:
            parts.append("**...")
        elif kw.arg == "messages":
            parts.append("messages=[...]")
        else:
            parts.append(f"{kw.arg}=...")
    return f"{func}({', '.join(parts)})"


def scan_module(
    tree: ast.Module, source: str, rel_path: str
) -> list[DiscoveredCall]:
    string_constants, literal_constants = module_constants(tree)
    visitor = _CallVisitor()
    visitor.visit(tree)

    calls: list[DiscoveredCall] = []
    for call, func, stmt in visitor.found:
        model_expr = _kwarg(call, "model")
        if isinstance(model_expr, ast.Constant) and isinstance(model_expr.value, str):
            model, literal = model_expr.value, True
        elif isinstance(model_expr, ast.Name) and model_expr.id in string_constants:
            model, literal = string_constants[model_expr.id], False
        elif model_expr is None:
            model, literal = UNSPECIFIED_MODEL, False
        else:
            model, literal = DYNAMIC_MODEL, False

        function_name = getattr(func, "name", None)
        docstring = ast.get_docstring(func) if isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)) else None
        prompt_ref = find_prompt_reference(
            _kwarg(call, "messages") or _kwarg(call, "input"), func, string_constants
        )
        response_format = _literal(_kwarg(call, "response_format"))
        schema = find_expected_schema(func, response_format, literal_constants, prompt_ref, function_name)
        json_required = schema is not None or (
            isinstance(response_format, dict)
            and response_format.get("type") in ("json_object", "json_schema")
        )
        max_tokens = _literal(_kwarg(call, "max_tokens"))
        if not isinstance(max_tokens, int) or isinstance(max_tokens, bool):
            max_tokens = None

        snippet = ast.get_source_segment(source, stmt) or ast.get_source_segment(source, call) or ""
        base_id = f"node_{function_name}" if function_name else f"node_{Path(rel_path).stem}_l{stmt.lineno}"
        calls.append(
            DiscoveredCall(
                node_id=base_id,
                file_path=rel_path,
                line_number=stmt.lineno,
                end_line_number=stmt.end_lineno or stmt.lineno,
                call_line=call.lineno,
                call_col=call.col_offset,
                call_end_line=call.end_lineno or call.lineno,
                call_end_col=call.end_col_offset or 0,
                current_model=model,
                model_is_literal=literal,
                call_signature=_call_signature(call),
                function_name=function_name,
                docstring=docstring,
                prompt_reference=prompt_ref,
                expected_schema=schema,
                json_required=json_required,
                max_tokens=max_tokens,
                snippet=snippet,
                kwargs=[kw.arg for kw in call.keywords if kw.arg],
            )
        )
    return calls


def detect_frameworks(trees: dict[str, ast.Module]) -> str:
    found: list[str] = []
    for tree in trees.values():
        for node in ast.walk(tree):
            modules: list[str] = []
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                modules = [node.module]
            for module in modules:
                label = FRAMEWORK_IMPORTS.get(module.split(".")[0])
                if label and label not in found:
                    found.append(label)
    return " / ".join(found) if found else "Unknown"


def _dedupe_ids(calls: list[DiscoveredCall]) -> None:
    taken: set[str] = set()
    for call in calls:
        candidate, n = call.node_id, 1
        while candidate in taken:
            n += 1
            candidate = f"{call.node_id}_{n}"
        call.node_id = candidate
        taken.add(candidate)


def scan_repository(root: Path) -> RepoScan:
    """Parse every Python file under `root` and collect LLM call sites."""
    warnings: list[str] = []
    files = iter_python_files(root, warnings)
    trees: dict[str, ast.Module] = {}
    sources: dict[str, str] = {}
    calls: list[DiscoveredCall] = []

    for path in files:
        rel = path.relative_to(root).as_posix()
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=rel)
        except (SyntaxError, UnicodeDecodeError, ValueError) as exc:
            warnings.append(f"Skipped {rel}: {exc.__class__.__name__}")
            continue
        trees[rel] = tree
        sources[rel] = source
        calls.extend(scan_module(tree, source, rel))

    _dedupe_ids(calls)
    for w in warnings:
        logger.warning("scan %s: %s", root, w)
    return RepoScan(
        root=root,
        calls=calls,
        trees=trees,
        sources=sources,
        scanned_files_count=len(trees),
        detected_framework=detect_frameworks(trees),
        warnings=warnings,
    )
