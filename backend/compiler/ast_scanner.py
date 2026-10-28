"""Bounded, source-only discovery of OpenAI chat-completions call sites.

This module's dataclasses are a PROVISIONAL SCANNER INTERFACE, not the shared
backend API schema. No graph is inferred. Only source syntax is inspected:
imports, constructors, annotations, prompts and schemas are never executed.

Provenance is local and conservative. Straight-line imports/assignments are
tracked; conditional bindings, global/nonlocal declarations, instance fields,
comprehensions, wrappers and cross-file resolution are unsupported. Captured
bindings must have a single syntactic binding site in the enclosing scope.
Static call sites do not imply runtime reachability or runtime type guarantees.
"""

from __future__ import annotations

import ast
import hashlib
import io
import os
import re
import stat
import tokenize
from collections import Counter
from contextlib import ExitStack, contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Iterator, Literal

if os.name == "nt":
    import ctypes
    import msvcrt
    from ctypes import wintypes


EXCLUDED_DIRECTORIES = frozenset(
    {".git", ".venv", "venv", "node_modules", "__pycache__", "build", "dist"}
)
_CONSTRUCTORS = frozenset({"OpenAI", "AsyncOpenAI"})
_SCHEMA_TYPES = frozenset(
    {"object", "array", "string", "number", "integer", "boolean", "null"}
)
_MODEL_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}\Z", re.ASCII)
_CREDENTIAL_PREFIXES = (
    "sk-", "sk_", "ghp_", "gho_", "ghu_", "ghs_", "ghr_", "github_pat_",
    "xoxb-", "xoxp-", "xoxa-", "aiza",
)


@dataclass(frozen=True)
class ScannerOptions:
    max_files: int = 500
    max_file_bytes: int = 1024 * 1024
    max_total_bytes: int = 25 * 1024 * 1024
    max_directory_entries: int = 50_000
    max_directory_depth: int = 64
    max_ast_nodes: int = 100_000
    max_metadata_nodes: int = 256

    def __post_init__(self) -> None:
        for name, value in asdict(self).items():
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")


@dataclass(frozen=True)
class ArgumentMetadata:
    """References are syntax, not resolved values; literal prompts stay redacted.

    ``value`` is populated only for a literal model ID or a deliberately limited
    response-format summary. Schema descriptions, enums, defaults, examples and
    arbitrary response-format keys are not copied into results.
    Literal model export accepts at most 256 ASCII identifier characters and
    rejects recognizable credential prefixes; other strings stay unresolved.
    """

    kind: Literal["missing", "literal", "reference", "unresolved"]
    reference: str | None = None
    references: tuple[str, ...] = ()
    value: str | dict[str, object] | None = None


@dataclass(frozen=True)
class ProvisionalLLMNode:
    node_id: str
    file_path: str
    line_number: int
    column_number: int  # Zero-based UTF-8 byte offset, following Python's AST.
    call_signature: str
    current_model: str | None
    model: ArgumentMetadata
    messages: ArgumentMetadata
    response_format: ArgumentMetadata
    function_name: str | None


@dataclass(frozen=True)
class ScanDiagnostic:
    code: str
    message: str
    file_path: str | None = None
    line_number: int | None = None


@dataclass(frozen=True)
class SourceFingerprint:
    """Provisional source-version evidence; contains no source text."""

    file_path: str
    sha256: str


@dataclass(frozen=True)
class ProvisionalScanResult:
    repository_path: str
    nodes: tuple[ProvisionalLLMNode, ...]
    discovered_files_count: int
    scanned_files_count: int
    total_source_bytes_read: int
    diagnostics: tuple[ScanDiagnostic, ...]
    complete: bool  # Coverage within the documented supported analysis subset.
    source_fingerprints: tuple[SourceFingerprint, ...] = ()
    source_options: ScannerOptions = field(default_factory=ScannerOptions)

    def to_dict(self) -> dict[str, object]:
        """Return a deterministic, JSON-compatible copy, without a timestamp."""
        def lists(value: object) -> object:
            if isinstance(value, dict):
                return {key: lists(item) for key, item in value.items()}
            if isinstance(value, (list, tuple)):
                return [lists(item) for item in value]
            return value

        return {key: lists(value) for key, value in asdict(self).items()}


@dataclass(frozen=True)
class _ParsedSource:
    """Ephemeral compiler hook data. ASTs never enter serialized scan results."""

    fingerprint: SourceFingerprint
    tree: ast.Module
    nodes: tuple[ProvisionalLLMNode, ...]
    calls: tuple[ast.Call, ...]


class _RepositoryIdentityChanged(Exception):
    """The service-authorized root changed; never downgrade to partial coverage."""


_expected_repository: ContextVar[tuple[Path, tuple[int, int]] | None] = ContextVar(
    "expected_repository", default=None,
)


@contextmanager
def _require_repository_identity(path: Path, identity: tuple[int, int]) -> Iterator[None]:
    """Private service boundary, shared by the scan and guarded graph reread."""
    token = _expected_repository.set((path, identity))
    try:
        yield
    finally:
        _expected_repository.reset(token)


def _is_link(info: os.stat_result) -> bool:
    # Windows junctions/reparse points are not necessarily S_ISLNK on Python 3.11.
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    )


def _normal_windows_path(path: str) -> Path:
    if path[:8].casefold() == "\\\\?\\unc\\":
        path = "\\\\" + path[8:]
    elif path.startswith("\\\\?\\"):
        path = path[4:]
    return Path(path)


def _windows_handle_path(handle: int) -> Path:
    """Inspect the opened object, not a path an attacker can swap back."""
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    final_path = kernel.GetFinalPathNameByHandleW
    final_path.argtypes = [wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD]
    final_path.restype = wintypes.DWORD
    buffer = ctypes.create_unicode_buffer(32768)
    length = final_path(handle, buffer, len(buffer), 0)
    if not length or length >= len(buffer):
        raise OSError("Opened-path verification failed.")
    return _normal_windows_path(buffer.value)


def _pin_windows_directory(path: Path, root: Path, stack: ExitStack) -> None:
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    create = kernel.CreateFileW
    create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                       wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    create.restype = wintypes.HANDLE
    close = kernel.CloseHandle
    close.argtypes = [wintypes.HANDLE]
    close.restype = wintypes.BOOL
    # No DELETE sharing: pin every ancestor against rename/junction replacement.
    # OPEN_REPARSE_POINT opens a final link itself instead of following it.
    # FILE_LIST_DIRECTORY is necessary: metadata-only (zero-access) handles do
    # not enforce the sharing restriction against directory renames on Windows.
    handle = create(str(path), 1, 1, None, 3, 0x02000000 | 0x00200000, None)
    if handle == wintypes.HANDLE(-1).value:
        raise OSError("Could not pin a source directory.")
    stack.callback(close, handle)
    actual = _windows_handle_path(handle)
    if actual != _normal_windows_path(str(path)) or not actual.is_relative_to(_normal_windows_path(str(root))):
        raise OSError("Directory containment changed.")
    info = path.lstat()
    if _is_link(info) or not stat.S_ISDIR(info.st_mode):
        raise OSError("Directory is a link or is not a directory.")


@contextmanager
def _directory_access(
    root: Path, directory: Path, root_identity: tuple[int, int],
) -> Iterator[int | None]:
    """Pin Windows ancestors, or use component-wise no-follow POSIX descriptors.

    Windows sharing locks prevent the inspected directory path being redirected
    while scandir/reads run. POSIX descriptors keep lookup anchored to the chosen
    directory even if its pathname is concurrently renamed.
    """
    parts = directory.relative_to(root).parts
    with ExitStack() as stack:
        if os.name == "nt":
            current = root
            _pin_windows_directory(current, root, stack)
            info = current.lstat()
            if (info.st_dev, info.st_ino) != root_identity:
                raise OSError("Repository identity changed.")
            for part in parts:
                current = current / part
                _pin_windows_directory(current, root, stack)
            yield None
        else:
            flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            descriptor = os.open(root, flags)
            stack.callback(os.close, descriptor)
            info = os.fstat(descriptor)
            if (info.st_dev, info.st_ino) != root_identity:
                raise OSError("Repository identity changed.")
            for part in parts:
                descriptor = os.open(part, flags, dir_fd=descriptor)
                stack.callback(os.close, descriptor)
            yield descriptor


class _RepositoryScan:
    def __init__(
        self, repository_path: str, options: ScannerOptions,
        on_source: Callable[[_ParsedSource], None] | None = None,
    ) -> None:
        self.options = options
        self.on_source = on_source
        self.fingerprints: list[SourceFingerprint] = []
        self.root = Path(repository_path).absolute()
        self.nodes: list[ProvisionalLLMNode] = []
        self.diagnostics: list[ScanDiagnostic] = []
        self.discovered = 0
        self.scanned = 0
        self.bytes_read = 0
        self.entries_seen = 0
        self.root_identity: tuple[int, int] = (0, 0)

    def report(
        self, code: str, message: str, path: Path | None = None,
        line_number: int | None = None,
    ) -> None:
        relative = path.relative_to(self.root).as_posix() if path else None
        self.diagnostics.append(ScanDiagnostic(code, message, relative, line_number))

    def run(self) -> ProvisionalScanResult:
        try:
            root_info = self.root.lstat()
            expected = _expected_repository.get()
            if expected is not None and (
                self.root != expected[0] or _is_link(root_info)
                or (root_info.st_dev, root_info.st_ino) != expected[1]
            ):
                raise _RepositoryIdentityChanged()
            if _is_link(root_info):
                self.report("link_skipped", "The selected root is a link or reparse point.")
            elif not stat.S_ISDIR(root_info.st_mode):
                self.report("invalid_root", "Select an existing repository directory.")
            else:
                self.root = self.root.resolve(strict=True)
                if expected is not None and self.root != expected[0]:
                    raise _RepositoryIdentityChanged()
                self.root_identity = (root_info.st_dev, root_info.st_ino)
                self.walk()
        except (OSError, ValueError, RuntimeError):
            self.report("root_error", "Could not safely inspect the repository root.")
        diagnostics = tuple(sorted(
            self.diagnostics,
            key=lambda item: (item.file_path or "", item.line_number or 0, item.code),
        ))
        return ProvisionalScanResult(
            self.root.as_posix(),
            tuple(sorted(self.nodes, key=lambda node: (
                node.file_path, node.line_number, node.column_number, node.node_id,
            ))),
            self.discovered, self.scanned, self.bytes_read, diagnostics,
            not diagnostics,
            tuple(sorted(self.fingerprints, key=lambda item: item.file_path)),
            self.options,
        )

    def inspect(self, path: Path, directory_fd: int | None = None) -> tuple[Path, os.stat_result] | None:
        try:
            info = (
                path.lstat() if directory_fd is None
                else os.stat(path.name, dir_fd=directory_fd, follow_symlinks=False)
            )
            if _is_link(info):
                self.report("link_skipped", "Skipped a link or reparse point.", path)
                return None
            resolved = path.resolve(strict=True)
            if not resolved.is_relative_to(self.root):
                self.report("outside_root", "Skipped a path outside the repository root.", path)
                return None
            return resolved, info
        except (OSError, ValueError, RuntimeError):
            self.report("path_error", "Could not safely inspect this path; it may have disappeared.", path)
            return None

    def walk(self) -> None:
        pending = [self.root]
        while pending:
            directory = pending.pop()
            # Ancestors must be pinned for each directory. Bound relative depth
            # so a directory-only tree cannot amplify this into quadratic work.
            if len(directory.relative_to(self.root).parts) > self.options.max_directory_depth:
                self.report("directory_depth_limit", "Directory depth limit reached; deeper coverage is incomplete.", directory)
                continue
            try:
                with _directory_access(self.root, directory, self.root_identity) as directory_fd:
                    # Skip an over-budget directory in full rather than depend
                    # on a filesystem's unspecified enumeration order.
                    entries: list[os.DirEntry[str]] = []
                    with os.scandir(directory if directory_fd is None else directory_fd) as iterator:
                        for entry in iterator:
                            self.entries_seen += 1
                            if self.entries_seen > self.options.max_directory_entries:
                                self.report("directory_entry_limit", "Directory-entry limit reached; remaining coverage is incomplete.", directory)
                                return
                            entries.append(entry)
                    children: list[Path] = []
                    for entry in sorted(entries, key=lambda item: item.name):
                        path = directory / entry.name
                        inspected = self.inspect(path, directory_fd)
                        if inspected is None:
                            continue
                        resolved, info = inspected
                        if stat.S_ISDIR(info.st_mode):
                            if entry.name.casefold() not in EXCLUDED_DIRECTORIES:
                                children.append(path)
                        elif stat.S_ISREG(info.st_mode) and path.suffix.lower() == ".py":
                            if self.discovered >= self.options.max_files:
                                self.report("file_count_limit", "Python-file discovery limit reached; remaining coverage is incomplete.", path)
                                return
                            self.discovered += 1
                            self.scan_file(path, resolved, info, directory_fd)
                    pending.extend(reversed(children))
            except OSError:
                self.report("directory_error", "Could not safely pin or enumerate this directory.", directory)
                continue

    def scan_file(
        self, path: Path, resolved: Path, expected: os.stat_result,
        directory_fd: int | None = None,
    ) -> None:
        remaining = self.options.max_total_bytes - self.bytes_read
        if expected.st_size > self.options.max_file_bytes:
            self.report("file_size_limit", "Source file exceeds the per-file byte limit.", path)
            return
        if expected.st_size > remaining or remaining == 0:
            self.report("total_bytes_limit", "Source file skipped because the aggregate byte budget is exhausted.", path)
            return
        try:
            flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
            flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
            descriptor = (
                os.open(resolved, flags) if directory_fd is None
                else os.open(path.name, flags, dir_fd=directory_fd)
            )
            with os.fdopen(descriptor, "rb", buffering=0) as stream:
                opened = os.fstat(stream.fileno())
                handle_inside = True
                if os.name == "nt":
                    actual = _windows_handle_path(msvcrt.get_osfhandle(stream.fileno()))
                    handle_inside = actual.is_relative_to(_normal_windows_path(str(self.root)))
                # Check identity and containment again before reading. This also
                # rejects a file replaced with a device, FIFO or a link target.
                if (
                    not stat.S_ISREG(opened.st_mode)
                    or not handle_inside
                    or _is_link(opened)
                    or (opened.st_dev, opened.st_ino) != (expected.st_dev, expected.st_ino)
                    or resolved.resolve(strict=True) != resolved
                    or self.root.resolve(strict=True) != self.root
                ):
                    self.report("file_changed", "Source identity or containment changed before reading.", path)
                    return
                if opened.st_size > self.options.max_file_bytes:
                    self.report("file_size_limit", "Source file exceeds the per-file byte limit.", path)
                    return
                if opened.st_size > remaining:
                    self.report("total_bytes_limit", "Source file exceeds the remaining aggregate byte budget.", path)
                    return
                raw = stream.read(min(self.options.max_file_bytes, remaining, opened.st_size + 1))
                self.bytes_read += len(raw)
                after = os.fstat(stream.fileno())
                if (
                    len(raw) != opened.st_size or after.st_size != opened.st_size
                    or after.st_mtime_ns != opened.st_mtime_ns
                    or after.st_ctime_ns != opened.st_ctime_ns
                ):
                    self.report("file_changed", "Source changed while reading; analysis was skipped.", path)
                    return
        except (OSError, ValueError, RuntimeError):
            self.report("read_error", "Could not safely read this source file; it may be unreadable or missing.", path)
            return
        if b"\x00" in raw:
            self.report("binary_source", "NUL bytes found; this is not valid Python source.", path)
            return
        try:
            encoding, _ = tokenize.detect_encoding(io.BytesIO(raw).readline)
            source = raw.decode(encoding)
        except (SyntaxError, UnicodeError, LookupError):
            self.report("encoding_error", "Invalid or unsupported Python source encoding.", path)
            return
        try:
            tree = ast.parse(
                source, filename=path.relative_to(self.root).as_posix(),
                feature_version=(3, 11),
            )
            for count, _ in enumerate(ast.walk(tree), 1):
                if count > self.options.max_ast_nodes:
                    self.report("ast_node_limit", "AST node limit reached; analysis was skipped.", path)
                    return
            has_sdk_import = any(
                (isinstance(item, ast.Import) and any(alias.name == "openai" for alias in item.names))
                or (isinstance(item, ast.ImportFrom) and item.level == 0 and item.module == "openai")
                for item in ast.walk(tree)
            )
            if has_sdk_import and self.local_sdk_shadow(path):
                self.report(
                    "sdk_import_ambiguous",
                    "Local openai paths exist or could not be inspected; SDK provenance is unsupported.",
                    path,
                )
                self.scanned += 1
                self.record_source(path, raw, tree, ())
                return
            visitor = _CallVisitor(path.relative_to(self.root).as_posix(), tree, self.options)
            visitor.visit(tree)
        except SyntaxError as error:
            # SyntaxError messages/text can contain source literals. Export only
            # a fixed message and the location, never the exception's text.
            self.report("syntax_error", "Invalid Python syntax.", path, error.lineno)
            return
        except UnicodeError:
            self.report("encoding_error", "Decoded source cannot be represented as valid Python text.", path)
            return
        except (RecursionError, MemoryError):
            self.report("analysis_resource_limit", "Parser or visitor resource limit reached.", path)
            return
        self.nodes.extend(visitor.nodes)
        self.diagnostics.extend(visitor.diagnostics)
        self.scanned += 1
        self.record_source(path, raw, tree, tuple(visitor.nodes), tuple(visitor.call_nodes))

    def record_source(
        self, path: Path, raw: bytes, tree: ast.Module,
        nodes: tuple[ProvisionalLLMNode, ...],
        calls: tuple[ast.Call, ...] = (),
    ) -> None:
        fingerprint = SourceFingerprint(
            path.relative_to(self.root).as_posix(), hashlib.sha256(raw).hexdigest(),
        )
        self.fingerprints.append(fingerprint)
        if self.on_source is not None:
            self.on_source(_ParsedSource(fingerprint, tree, nodes, calls))

    def local_sdk_shadow(self, path: Path) -> bool:
        # An absolute import is not sufficient SDK evidence if a local module or
        # package can satisfy it. Inspect metadata only, without following links.
        directory = path.parent
        while directory.is_relative_to(self.root):
            for name in ("openai.py", "openai"):
                try:
                    (directory / name).lstat()
                except FileNotFoundError:
                    continue
                except OSError:
                    return True
                return True
            if directory == self.root:
                break
            directory = directory.parent
        return False


@dataclass(frozen=True)
class _Binding:
    kind: Literal["module", "constructor", "client"]
    constructor: str | None = None


class _Bindings(ast.NodeVisitor):
    """Collect lexical locals without descending into deferred/nested scopes."""

    def __init__(self) -> None:
        self.counts: Counter[str] = Counter()
        self.wildcard = False

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, (ast.Store, ast.Del)):
            self.counts[node.id] += 1

    def visit_Attribute(self, node: ast.Attribute | ast.Subscript) -> None:
        if isinstance(node.ctx, (ast.Store, ast.Del)):
            base = node.value
            while isinstance(base, (ast.Attribute, ast.Subscript)):
                base = base.value
            if isinstance(base, ast.Name):
                self.counts[base.id] += 1
        self.generic_visit(node)

    visit_Subscript = visit_Attribute

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.counts[alias.asname or alias.name.split(".")[0]] += 1

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            if alias.name == "*":
                self.wildcard = True
            self.counts[alias.asname or alias.name] += 1

    def visit_FunctionDef(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self.counts[node.name] += 1
        for expression in _definition_expressions(node):
            self.visit(expression)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.counts[node.name] += 1
        for expression in [*node.decorator_list, *node.bases, *node.keywords]:
            self.visit(expression)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        for expression in [*node.args.defaults, *node.args.kw_defaults]:
            if expression is not None:
                self.visit(expression)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.name:
            self.counts[node.name] += 1
        self.generic_visit(node)

    def visit_MatchAs(self, node: ast.MatchAs) -> None:
        if node.name:
            self.counts[node.name] += 1
        self.generic_visit(node)

    visit_MatchStar = visit_MatchAs

    def visit_MatchMapping(self, node: ast.MatchMapping) -> None:
        if node.rest:
            self.counts[node.rest] += 1
        self.generic_visit(node)


def _definition_expressions(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.AST]:
    arguments = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
    if node.args.vararg:
        arguments.append(node.args.vararg)
    if node.args.kwarg:
        arguments.append(node.args.kwarg)
    return [expression for expression in [
        *node.decorator_list, *node.args.defaults, *node.args.kw_defaults,
        node.returns, *(argument.annotation for argument in arguments),
    ] if expression is not None]


def _mutated_aliases(tree: ast.AST) -> set[str]:
    """Reject provenance whose syntactic alias group has attribute mutations.

    Grouping names across scopes deliberately over-approximates mutation. Losing
    a detection is preferable to confirming a client after an alias changed its
    SDK methods. It does not attempt arbitrary heap or interprocedural analysis.
    """
    neighbors: dict[str, set[str]] = {}
    mutated: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Attribute, ast.Subscript)) and isinstance(node.ctx, (ast.Store, ast.Del)):
            base = node.value
            while isinstance(base, (ast.Attribute, ast.Subscript)):
                base = base.value
            if isinstance(base, ast.Name):
                mutated.add(base.id)
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names = [target.id for target in targets if isinstance(target, ast.Name)]
            if isinstance(node.value, ast.Name):
                names.append(node.value.id)
            if names:
                anchor = names[0]
                for name in names[1:]:
                    neighbors.setdefault(anchor, set()).add(name)
                    neighbors.setdefault(name, set()).add(anchor)
    pending = list(mutated)
    while pending:
        for alias in neighbors.get(pending.pop(), ()):
            if alias not in mutated:
                mutated.add(alias)
                pending.append(alias)
    return mutated


class _Scope:
    def __init__(
        self, parent: _Scope | None, tree: ast.AST, kind: str,
    ) -> None:
        collector = _Bindings()
        # FunctionDef itself binds its name in the *parent*, not in its body.
        if isinstance(tree, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            for statement in tree.body:
                collector.visit(statement)
        else:
            collector.visit(tree)
        self.parent = parent
        self.kind = kind
        self.unstable = {
            name for name, count in collector.counts.items()
            if count != 1 or collector.wildcard
        }
        self.bindings: dict[str, _Binding | None] = (
            dict.fromkeys(collector.counts) if kind == "function" else {}
        )
        self.wildcard = False

    def lookup(self, name: str, captured: bool = False) -> _Binding | None:
        if captured and name in self.unstable:
            return None
        if name in self.bindings:
            return self.bindings[name]
        if self.wildcard or self.parent is None:
            return None
        return self.parent.lookup(name, captured=True)


class _CallVisitor(ast.NodeVisitor):
    def __init__(self, path: str, tree: ast.Module, options: ScannerOptions) -> None:
        self.path = path
        self.options = options
        self.scope = _Scope(None, tree, "module")
        self.nodes: list[ProvisionalLLMNode] = []
        self.diagnostics: list[ScanDiagnostic] = []
        self.functions: list[str] = []
        self.call_nodes: list[ast.Call] = []
        self.limited_metadata: set[ast.AST] = set()
        self.uncertain = 0
        # Refuse even apparently simple provenance involving global/nonlocal
        # names: deferred calls can otherwise observe a different binding.
        self.external_names = {
            name for item in ast.walk(tree)
            if isinstance(item, (ast.Global, ast.Nonlocal)) for name in item.names
        }
        self.external_names.update(_mutated_aliases(tree))

    def bind(self, name: str, binding: _Binding | None) -> None:
        self.scope.bindings[name] = (
            None if self.uncertain or name in self.external_names else binding
        )

    def resolve(self, node: ast.AST) -> _Binding | None:
        if isinstance(node, ast.Name):
            return self.scope.lookup(node.id)
        if isinstance(node, ast.Attribute) and node.attr in _CONSTRUCTORS:
            base = self.resolve(node.value)
            if base and base.kind == "module":
                return _Binding("constructor", node.attr)
        if isinstance(node, ast.Call):
            constructor = self.resolve(node.func)
            if constructor and constructor.kind == "constructor":
                return _Binding("client", constructor.constructor)
        return None

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.bind(alias.asname or alias.name.split(".")[0],
                      _Binding("module") if alias.name == "openai" else None)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            if alias.name == "*":
                self.scope.bindings = dict.fromkeys(self.scope.bindings)
                self.scope.wildcard = True
                continue
            binding = None
            if node.level == 0 and node.module == "openai" and alias.name in _CONSTRUCTORS:
                binding = _Binding("constructor", alias.name)
            self.bind(alias.asname or alias.name, binding)

    def assign(self, target: ast.AST, binding: _Binding | None = None) -> None:
        if isinstance(target, ast.Name):
            self.bind(target.id, binding)
        elif isinstance(target, (ast.Tuple, ast.List)):
            for element in target.elts:
                self.assign(element)
        elif isinstance(target, ast.Starred):
            self.assign(target.value)
        elif isinstance(target, (ast.Attribute, ast.Subscript)):
            base = target.value
            while isinstance(base, (ast.Attribute, ast.Subscript)):
                base = base.value
            if isinstance(base, ast.Name):
                self.bind(base.id, None)

    def visit_target(self, target: ast.AST) -> None:
        # Assignment targets can contain calls and walrus expressions. Visit
        # their evaluated parts without treating a stored Name as a read.
        if isinstance(target, (ast.Tuple, ast.List)):
            for element in target.elts:
                self.visit_target(element)
        elif isinstance(target, ast.Starred):
            self.visit_target(target.value)
        elif isinstance(target, ast.Attribute):
            self.visit(target.value)
        elif isinstance(target, ast.Subscript):
            self.visit(target.value)
            self.visit(target.slice)

    def visit_Assign(self, node: ast.Assign) -> None:
        self.visit(node.value)
        binding = self.resolve(node.value)
        for target in node.targets:
            self.visit_target(target)
            self.assign(target, binding)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.value is not None:
            self.visit(node.value)
            self.visit_target(node.target)
            self.assign(node.target, self.resolve(node.value))
        else:
            self.visit_target(node.target)
            self.assign(node.target)
        self.visit(node.annotation)

    def visit_NamedExpr(self, node: ast.NamedExpr) -> None:
        self.visit(node.value)
        self.assign(node.target, self.resolve(node.value))

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        self.visit_target(node.target)
        self.assign(node.target)
        self.visit(node.value)

    def visit_Delete(self, node: ast.Delete) -> None:
        for target in node.targets:
            self.visit_target(target)
            self.assign(target)

    def visit_FunctionDef(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        for expression in _definition_expressions(node):
            self.visit(expression)
        self.bind(node.name, None)
        outer, uncertain = self.scope, self.uncertain
        parent = outer
        while parent.kind == "class" and parent.parent is not None:
            parent = parent.parent
        self.scope = _Scope(parent, node, "function")
        for argument in [
            *node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs,
            *([node.args.vararg] if node.args.vararg else []),
            *([node.args.kwarg] if node.args.kwarg else []),
        ]:
            self.scope.bindings[argument.arg] = None
            self.scope.unstable.add(argument.arg)
        self.functions.append(node.name)
        self.uncertain = 0
        for statement in node.body:
            self.visit(statement)
        self.functions.pop()
        self.scope, self.uncertain = outer, uncertain

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Lambda(self, node: ast.Lambda) -> None:
        # Lambdas and comprehensions are deliberately outside this first subset.
        for expression in [*node.args.defaults, *node.args.kw_defaults]:
            if expression is not None:
                self.visit(expression)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        for expression in [*node.decorator_list, *node.bases, *node.keywords]:
            self.visit(expression)
        outer = self.scope
        self.scope = _Scope(outer, node, "class")
        for statement in node.body:
            self.visit(statement)
        self.scope = outer
        self.bind(node.name, None)

    def uncertain_block(self, node: ast.AST) -> None:
        collector = _Bindings()
        collector.visit(node)
        for name in collector.counts:
            self.bind(name, None)
        self.uncertain += 1
        self.generic_visit(node)
        self.uncertain -= 1
        for name in collector.counts:
            self.bind(name, None)

    visit_If = uncertain_block
    visit_For = uncertain_block
    visit_AsyncFor = uncertain_block
    visit_While = uncertain_block
    visit_With = uncertain_block
    visit_AsyncWith = uncertain_block
    visit_Try = uncertain_block
    visit_TryStar = uncertain_block
    visit_Match = uncertain_block
    visit_IfExp = uncertain_block
    visit_BoolOp = uncertain_block

    def visit_ListComp(self, node: ast.AST) -> None:
        collector = _Bindings()
        collector.visit(node)
        for name in collector.counts:
            self.bind(name, None)

    visit_SetComp = visit_ListComp
    visit_DictComp = visit_ListComp
    visit_GeneratorExp = visit_ListComp

    def visit_Call(self, node: ast.Call) -> None:
        method = node.func
        if (
            isinstance(method, ast.Attribute) and method.attr == "create"
            and isinstance(method.value, ast.Attribute) and method.value.attr == "completions"
            and isinstance(method.value.value, ast.Attribute) and method.value.value.attr == "chat"
        ):
            binding = self.resolve(method.value.value.value)
            if binding and binding.kind == "client":
                self.record(node, binding)
        self.generic_visit(node)

    def record(self, node: ast.Call, binding: _Binding) -> None:
        keywords = {keyword.arg: keyword.value for keyword in node.keywords if keyword.arg}
        unpacked = any(keyword.arg is None for keyword in node.keywords)
        model = self.metadata(keywords.get("model"), unpacked)
        model_node = keywords.get("model")
        current_model = None
        if isinstance(model_node, ast.Constant) and isinstance(model_node.value, str):
            value = model_node.value
            if (
                _MODEL_ID.fullmatch(value)
                and not value.casefold().startswith(_CREDENTIAL_PREFIXES)
                and not re.fullmatch(r"(?:AKIA|ASIA)[A-Z0-9]{16}", value)
            ):
                current_model = value
                model = ArgumentMetadata("literal", value=current_model)
            else:
                model = ArgumentMetadata("unresolved")
                self.diagnostics.append(ScanDiagnostic(
                    "model_literal_redacted",
                    "Model literal is outside the safe identifier subset or resembles a credential; its value was omitted.",
                    self.path, node.lineno,
                ))
        elif model.kind == "literal":
            model = ArgumentMetadata("unresolved")
        messages = self.metadata(keywords.get("messages"), unpacked)
        response_format = self.response_metadata(keywords.get("response_format"), unpacked)
        signature = f"openai.{binding.constructor}.chat.completions.create(...)"
        identity = f"{self.path}\0{node.lineno}\0{node.col_offset}\0{signature}"
        self.call_nodes.append(node)
        self.nodes.append(ProvisionalLLMNode(
            "llm_" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24],
            self.path, node.lineno, node.col_offset, signature, current_model,
            model, messages, response_format,
            ".".join(self.functions)[:256] if self.functions else None,
        ))

    def metadata(self, node: ast.AST | None, unpacked: bool = False) -> ArgumentMetadata:
        if node is None:
            return ArgumentMetadata("unresolved" if unpacked else "missing")
        reference = _reference(node)
        references: set[str] = set()
        literal = True
        for count, item in enumerate(ast.walk(node), 1):
            if count > self.options.max_metadata_nodes:
                if node not in self.limited_metadata:
                    self.limited_metadata.add(node)
                    self.diagnostics.append(ScanDiagnostic(
                        "metadata_limit",
                        "Argument metadata limit reached; value and references remain unresolved.",
                        self.path, getattr(node, "lineno", None),
                    ))
                return ArgumentMetadata("unresolved")
            if isinstance(item, (ast.Name, ast.Attribute)):
                name = _reference(item)
                if name:
                    references.add(name)
            if not isinstance(item, (ast.Constant, ast.List, ast.Tuple, ast.Dict, ast.Load)):
                literal = False
        kind: Literal["literal", "reference", "unresolved"] = (
            "reference" if reference else "literal" if literal else "unresolved"
        )
        return ArgumentMetadata(kind, reference, tuple(sorted(references))[:32])

    def response_metadata(self, node: ast.AST | None, unpacked: bool) -> ArgumentMetadata:
        metadata = self.metadata(node, unpacked)
        if not isinstance(node, ast.Dict) or node in self.limited_metadata:
            return metadata
        envelope = _dict_items(node)
        format_type = _string(envelope.get("type"))
        if format_type not in {"json_object", "json_schema", "text"}:
            return metadata
        summary: dict[str, object] = {"type": format_type}
        if format_type == "json_schema":
            definition_node = envelope.get("json_schema")
            definition = _dict_items(definition_node)
            definition_known = (
                isinstance(definition_node, ast.Dict)
                and len(definition) == len(definition_node.keys)
            )
            strict = definition.get("strict")
            if isinstance(strict, ast.Constant) and isinstance(strict.value, bool):
                summary["strict"] = strict.value
            schema_node = definition.get("schema")
            schema_info = self.metadata(
                schema_node, unpacked=definition_node is not None and not definition_known,
            )
            shape: dict[str, object] = {"kind": schema_info.kind}
            if schema_info.reference:
                shape["reference"] = schema_info.reference
            definition_reference = (
                _reference(definition_node) if definition_node is not None else None
            )
            if definition_reference:
                shape["definition_reference"] = definition_reference
            schema = _dict_items(schema_node)
            schema_type = _string(schema.get("type"))
            if schema_type in _SCHEMA_TYPES:
                shape["type"] = schema_type
            properties = schema.get("properties")
            if isinstance(properties, ast.Dict) and len(_dict_items(properties)) == len(properties.keys):
                shape["property_count"] = len(properties.keys)
            required = schema.get("required")
            if isinstance(required, ast.List) and all(_string(item) is not None for item in required.elts):
                shape["required_count"] = len(required.elts)
            summary["schema"] = shape
        return ArgumentMetadata(metadata.kind, metadata.reference, metadata.references, summary)


def _reference(node: ast.AST) -> str | None:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        if len(parts) > 16:
            return None
        node = node.value
    if not isinstance(node, ast.Name):
        return None
    reference = ".".join([node.id, *reversed(parts)])
    return reference if len(reference) <= 256 else None


def _dict_items(node: ast.AST | None) -> dict[str, ast.AST]:
    if not isinstance(node, ast.Dict):
        return {}
    # Unpacking/duplicate keys could override the apparent literal metadata.
    keys = [_string(key) for key in node.keys]
    if any(key is None for key in keys) or len(set(keys)) != len(keys):
        return {}
    return {key: value for key, value in zip(keys, node.values) if key is not None}


def _string(node: ast.AST | None) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def scan_repository(
    repository_path: str, *, options: ScannerOptions | None = None,
) -> ProvisionalScanResult:
    """Scan Python source without importing or executing the selected repository.

    Limits count discovered regular .py files and all raw source bytes actually
    read, including invalid files. Excluded directories are outside coverage.
    ``complete`` is false when any diagnostic reports skipped/incomplete work;
    true does not promise support for dynamic Python or other SDKs/frameworks.
    Source grammar is explicitly limited to Python 3.11 across host versions.
    This provisional result has no graph edges, snippets, or prompt literals.
    """
    return _scan_repository_with_sources(repository_path, options or ScannerOptions())


def _scan_repository_with_sources(
    repository_path: str, options: ScannerOptions,
    on_source: Callable[[_ParsedSource], None] | None = None,
) -> ProvisionalScanResult:
    """Internal compiler hook sharing every scanner I/O/parse safety check.

    Callbacks receive only successfully analyzed snapshots while directory pins
    remain held. They are trusted compiler code, never functions from the target.
    """
    return _RepositoryScan(repository_path, options, on_source).run()
