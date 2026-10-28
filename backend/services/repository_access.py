"""Authorization and directory guards; path syntax is never authority."""

from __future__ import annotations

import os
import stat
from contextlib import ExitStack, contextmanager
from pathlib import Path, PureWindowsPath
from typing import Iterator

from backend.compiler.ast_scanner import (
    ScannerOptions, _directory_access, _is_link, _RepositoryIdentityChanged, _require_repository_identity,
)
from backend.config import BackendConfig
from .errors import ServiceError


def _identity(info: os.stat_result) -> tuple[int, int]:
    return info.st_dev, info.st_ino


class RepositoryAccess:
    def __init__(self, settings: BackendConfig):
        self.roots = settings.require_repository_roots()
        self.identities = {root: _identity(root.lstat()) for root in self.roots}

    def select(self, requested: str) -> tuple[Path, Path]:
        """Resolve relative requests against one explicit root, never the CWD."""
        windows = PureWindowsPath(requested)
        path = Path(requested)
        if (
            not requested.strip() or len(requested) > 4096 or "\x00" in requested
            or requested.startswith(("\\\\", "//")) or ".." in windows.parts
            or ".." in path.parts or (windows.drive and not windows.is_absolute())
            or (os.name != "nt" and (windows.drive or "\\" in requested))
            or (os.name == "nt" and path.root and not path.drive)
        ):
            raise ServiceError("repository_forbidden")
        if not path.is_absolute():
            if len(self.roots) != 1:
                raise ServiceError("invalid_request")
            path = self.roots[0] / path
        # Lexical containment is checked before filesystem access. Canonical
        # containment and no-follow identity are then enforced under handles.
        matches = [root for root in self.roots if path.is_relative_to(root)]
        if not matches:
            raise ServiceError("repository_forbidden")
        root = max(matches, key=lambda root: len(root.parts))
        parts = path.relative_to(root).parts
        if len(parts) > ScannerOptions().max_directory_depth or (
            os.name == "nt" and any(part.endswith((" ", ".")) or ":" in part for part in parts)
        ):
            raise ServiceError("repository_forbidden")
        return path, root

    def _verify(self, root: Path, path: Path, identity: tuple[int, int]) -> None:
        if (
            _is_link(root.lstat()) or _identity(root.lstat()) != self.identities[root]
            or root.resolve(strict=True) != root or path.resolve(strict=True) != path
            or _is_link(path.lstat()) or _identity(path.lstat()) != identity
        ):
            raise ServiceError("source_conflict")

    @contextmanager
    def authorize(self, requested: str) -> Iterator[Path]:
        path, root = self.select(requested)
        stack = ExitStack()
        try:
            try:
                descriptor = stack.enter_context(_directory_access(root, root, self.identities[root]))
                current = root
                for part in path.relative_to(root).parts:
                    try:
                        info = (current / part).lstat() if descriptor is None else os.stat(
                            part, dir_fd=descriptor, follow_symlinks=False,
                        )
                    except OSError:
                        raise ServiceError("repository_unavailable") from None
                    if _is_link(info):
                        raise ServiceError("repository_forbidden")
                    if not stat.S_ISDIR(info.st_mode):
                        raise ServiceError("repository_unavailable")
                    current = current / part
                    # The parent remains pinned. Pin this one child, rather
                    # than retain a quadratic number of ancestor handles.
                    descriptor = stack.enter_context(_directory_access(current, current, _identity(info)))
                    pinned = current.lstat() if descriptor is None else os.fstat(descriptor)
                    if _identity(pinned) != _identity(info):
                        raise ServiceError("source_conflict")
                info = path.lstat() if descriptor is None else os.fstat(descriptor)
                identity = _identity(info)
                self._verify(root, path, identity)
            except (OSError, ValueError, RuntimeError):
                raise ServiceError("source_conflict") from None
            with _require_repository_identity(path, identity):
                try:
                    yield path
                except _RepositoryIdentityChanged:
                    raise ServiceError("source_conflict") from None
            try:
                self._verify(root, path, identity)
            except (OSError, ValueError, RuntimeError):
                raise ServiceError("source_conflict") from None
        finally:
            stack.close()
