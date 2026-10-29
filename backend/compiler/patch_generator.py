"""Synthesise a reviewable unified diff that routes optimized calls through CascadeRouter.

For every optimized node, the call

    client.chat.completions.create(model=..., messages=...)

becomes

    cascade_router.dispatch(node_id="node_x", client=client, model=..., messages=...)

The original `model=` stays as the passthrough default; the runtime replaces it
with the policy's primary model. Each touched module gets one import and one
`CascadeRouter.load(__file__)` line. Every patched file must parse before it is
emitted.
"""

from __future__ import annotations

import ast
import difflib
from dataclasses import dataclass, field
from typing import Iterable, Optional

from backend.compiler.ast_scanner import DiscoveredCall

RUNTIME_MODULE = "cascaderouter"
IMPORT_LINE = f"from {RUNTIME_MODULE} import CascadeRouter"
LOADER_LINE = "cascade_router = CascadeRouter.load(__file__)"
ROUTER_NAME = "cascade_router"


class PatchError(ValueError):
    """A call site could not be rewritten safely."""


@dataclass
class FilePatch:
    path: str
    original: str
    patched: str

    def diff(self) -> str:
        return "".join(
            difflib.unified_diff(
                self.original.splitlines(keepends=True),
                self.patched.splitlines(keepends=True),
                fromfile=f"a/{self.path}",
                tofile=f"b/{self.path}",
            )
        )


@dataclass
class PatchSet:
    files: dict[str, FilePatch] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)  # node_id -> reason

    def combined_diff(self) -> str:
        return "".join(self.files[p].diff() for p in sorted(self.files))


def _line_offsets(source: bytes) -> list[int]:
    offsets, total = [0], 0
    for line in source.splitlines(keepends=True):
        total += len(line)
        offsets.append(total)
    return offsets


# Call shapes the runtime cannot validate or re-route faithfully.
UNSUPPORTED_KWARGS = ("stream", "tools", "functions", "tool_choice", "function_call")


def _find_call(tree: ast.Module, call: DiscoveredCall) -> ast.Call:
    """The exact Call node (start *and* end position), so `create(...).choices` style
    chains, whose outer node starts at the same place, are never mistaken for it."""
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and node.lineno == call.call_line
            and node.col_offset == call.call_col
            and node.end_lineno == call.call_end_line
            and node.end_col_offset == call.call_end_col
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "create"
        ):
            return node
    raise PatchError("call site not found in source (file changed since scan?)")


def _client_expr(func: ast.Attribute) -> ast.expr:
    """`client.chat.completions.create` -> the `client` expression."""
    node: ast.expr = func
    for expected in ("create", "completions", "chat"):
        if not isinstance(node, ast.Attribute) or node.attr != expected:
            raise PatchError("only <client>.chat.completions.create(...) calls can be patched")
        node = node.value
    return node


def _call_edit(
    source: bytes, offsets: list[int], node: ast.Call, node_id: str, awaited: bool = False
) -> tuple[int, int, bytes]:
    """Replacement for the callee part `client.chat.completions.create(`."""
    if any(kw.arg in ("node_id", "client", "validator") for kw in node.keywords):
        raise PatchError("call already uses reserved keyword names")
    unsupported = [kw.arg for kw in node.keywords if kw.arg in UNSUPPORTED_KWARGS]
    if unsupported:
        raise PatchError(f"calls using {', '.join(unsupported)} are not routed (runtime cannot validate them)")
    func = node.func
    assert isinstance(func, ast.Attribute)
    client = _client_expr(func)

    def abs_offset(lineno: int, col: int) -> int:
        return offsets[lineno - 1] + col

    client_src = source[abs_offset(client.lineno, client.col_offset): abs_offset(client.end_lineno, client.end_col_offset)]  # type: ignore[arg-type]
    start = abs_offset(node.lineno, node.col_offset)
    func_end = abs_offset(func.end_lineno, func.end_col_offset)  # type: ignore[arg-type]
    paren = source.index(b"(", func_end)
    # Preserve the original layout of the first argument (same line vs. next line).
    after = source[paren + 1:]
    stripped = after.lstrip(b" \t")
    newline_first = stripped.startswith(b"\n") or stripped.startswith(b"\r")
    has_args = bool(node.args or node.keywords)
    if newline_first:
        indent_line = after[after.index(b"\n") + 1:]
        indent = indent_line[: len(indent_line) - len(indent_line.lstrip(b" \t"))]
        inserted = b"\n" + indent + f'node_id="{node_id}",'.encode() + b"\n" + indent + b"client=" + client_src + b","
    else:
        inserted = f'node_id="{node_id}", client='.encode() + client_src + (b", " if has_args else b"")
    method = "dispatch_async" if awaited else "dispatch"
    replacement = f"{ROUTER_NAME}.{method}(".encode() + inserted
    return start, paren + 1, replacement


def _import_edit(
    tree: ast.Module, source: bytes, offsets: list[int], need_import: bool = True, need_loader: bool = True
) -> tuple[int, int, bytes]:
    """Insert the runtime import + loader after the last top-level import."""
    insert_line = 0
    for stmt in tree.body:
        is_docstring = (
            stmt is tree.body[0] and isinstance(stmt, ast.Expr)
            and isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str)
        )
        if isinstance(stmt, (ast.Import, ast.ImportFrom)) or is_docstring:
            insert_line = stmt.end_lineno or stmt.lineno
        elif insert_line:
            break
    pos = offsets[insert_line] if insert_line < len(offsets) else len(source)
    lines = ([IMPORT_LINE] if need_import else []) + ([LOADER_LINE] if need_loader else [])
    text = ("\n".join(lines) + "\n").encode()
    if pos > 0 and not source[:pos].endswith(b"\n"):
        text = b"\n" + text
    return pos, pos, text


def _async_call_ids(tree: ast.Module) -> set[int]:
    """Calls whose nearest enclosing function is `async def` (they return awaitables)."""
    found: set[int] = set()

    def visit(node: ast.AST, in_async: bool) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.AsyncFunctionDef):
                visit(child, True)
            elif isinstance(child, (ast.FunctionDef, ast.Lambda)):
                visit(child, False)
            else:
                if in_async and isinstance(child, ast.Call):
                    found.add(id(child))
                visit(child, in_async)

    visit(tree, False)
    return found


def _has_router_setup(tree: ast.Module) -> tuple[bool, bool]:
    """(runtime import present, module-level cascade_router assignment present) — from the AST."""
    has_import = any(
        isinstance(s, ast.ImportFrom) and s.module == RUNTIME_MODULE and any(a.name == "CascadeRouter" and a.asname is None for a in s.names)
        for s in tree.body
    )
    has_loader = any(
        isinstance(s, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == ROUTER_NAME for t in s.targets)
        and isinstance(s.value, ast.Call)
        and isinstance(s.value.func, ast.Attribute)
        and s.value.func.attr == "load"
        and isinstance(s.value.func.value, ast.Name)
        and s.value.func.value.id == "CascadeRouter"
        for s in tree.body
    )
    return has_import, has_loader


def patch_source(source: str, calls: list[DiscoveredCall]) -> str:
    """Rewrite all `calls` (same file) in `source`; raises PatchError on any problem.

    The file's newline style (LF or CRLF) is preserved for inserted lines.
    """
    if not calls:
        return source
    raw = source.encode("utf-8")
    tree = ast.parse(source)
    has_import, has_loader = _has_router_setup(tree)
    if not has_loader and any(
        isinstance(n, ast.Name) and n.id == ROUTER_NAME and isinstance(n.ctx, ast.Store) for n in ast.walk(tree)
    ):
        raise PatchError(f"module already defines `{ROUTER_NAME}`")
    offsets = _line_offsets(raw)
    async_ids = _async_call_ids(tree)
    edits = []
    for c in calls:
        node = _find_call(tree, c)
        edits.append(_call_edit(raw, offsets, node, c.node_id, awaited=id(node) in async_ids))
    if not (has_import and has_loader):
        edits.append(_import_edit(tree, raw, offsets, need_import=not has_import, need_loader=not has_loader))
    newline = b"\r\n" if b"\r\n" in raw else b"\n"
    if newline != b"\n":
        edits = [(a, b, t.replace(b"\n", newline)) for a, b, t in edits]
    edits.sort(key=lambda e: (e[0], e[1]), reverse=True)
    for (start, end, _), (next_start, _, _) in zip(edits[1:], edits[:-1]):
        if end > next_start:
            raise PatchError("overlapping edits")
    for start, end, text in edits:
        raw = raw[:start] + text + raw[end:]
    patched = raw.decode("utf-8")
    try:
        ast.parse(patched)
    except SyntaxError as exc:
        raise PatchError(f"patched file does not parse: {exc.msg}") from exc
    return patched


def build_patches(sources: dict[str, str], calls: Iterable[DiscoveredCall]) -> PatchSet:
    """Patch every file; a node that cannot be patched is reported, not fatal."""
    by_file: dict[str, list[DiscoveredCall]] = {}
    for call in calls:
        by_file.setdefault(call.file_path, []).append(call)
    result = PatchSet()
    for path in sorted(by_file):
        source = sources.get(path)
        if source is None:
            for c in by_file[path]:
                result.errors[c.node_id] = "source not available"
            continue
        good: list[DiscoveredCall] = []
        for c in by_file[path]:
            try:
                patch_source(source, [c])
            except (PatchError, SyntaxError) as exc:
                result.errors[c.node_id] = str(exc)
            else:
                good.append(c)
        if good:
            result.files[path] = FilePatch(path, source, patch_source(source, good))
    return result


def node_diff(sources: dict[str, str], call: DiscoveredCall) -> Optional[str]:
    """Diff for a single node in isolation (for the per-decision view)."""
    source = sources.get(call.file_path)
    if source is None:
        return None
    try:
        return FilePatch(call.file_path, source, patch_source(source, [call])).diff()
    except (PatchError, SyntaxError):
        return None
