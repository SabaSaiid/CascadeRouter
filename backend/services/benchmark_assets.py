"""Operator-approved, no-follow local data reads with pinned byte identities."""

from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path

from pydantic import ValidationError

from backend.compiler.ast_scanner import _directory_access, _is_link
from backend.compiler.evaluator import parse_bounded_json
from backend.config import BackendConfig
from backend.schemas import BenchmarkApprovalManifest
from .errors import ServiceError


class ApprovedAssetStore:
    """The manifest is operator-owned, separate from writable dataset roots.

    Approval is a local operator attestation plus integrity validation. It is not
    a claim that software can prove the truth of historical model measurements.
    """

    def __init__(self, settings: BackendConfig, *, allow_test_assets: bool = False):
        self.roots = settings.permitted_benchmark_data_roots
        self.manifest_path = settings.benchmark_approval_manifest_path
        self.allow_test_assets = allow_test_assets is True
        if not self.roots or self.manifest_path is None:
            raise ServiceError("capability_unavailable")
        self.root_identities = {root: self._identity(root.lstat()) for root in self.roots}
        self.operator_root = self.manifest_path.parent
        self.operator_identity = self._identity(self.operator_root.lstat())
        raw = self._read(self.operator_root, self.manifest_path, self.operator_identity, 65536)
        self.manifest_digest = hashlib.sha256(raw).hexdigest()
        try:
            self.manifest = BenchmarkApprovalManifest.model_validate(parse_bounded_json(
                raw.decode("utf-8"), max_bytes=65536, max_depth=16, max_nodes=4096,
            ))
        except (ValueError, ValidationError, UnicodeError):
            raise ServiceError("capability_unavailable") from None
        if any(item.root_index >= len(self.roots) for item in self.manifest.assets):
            raise ServiceError("capability_unavailable")
        self.loaded = {}

    @staticmethod
    def _identity(info):
        return info.st_dev, info.st_ino

    @staticmethod
    def _read(root: Path, path: Path, identity: tuple[int, int], maximum: int) -> bytes:
        try:
            if not path.is_absolute() or not path.is_relative_to(root):
                raise ServiceError("repository_forbidden")
            parts = path.relative_to(root).parts
            if not parts or len(parts) > 64 or ".." in parts or any(
                part.endswith((".", " ")) or ":" in part for part in parts
            ):
                raise ServiceError("repository_forbidden")
            with _directory_access(root, path.parent, identity) as directory_fd:
                before = path.lstat() if directory_fd is None else os.stat(path.name, dir_fd=directory_fd, follow_symlinks=False)
                if _is_link(before) or not stat.S_ISREG(before.st_mode):
                    raise ServiceError("repository_forbidden")
                if before.st_size > maximum:
                    raise ServiceError("capacity_exceeded")
                flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
                descriptor = os.open(path if directory_fd is None else path.name, flags,
                                     **({} if directory_fd is None else {"dir_fd": directory_fd}))
                with os.fdopen(descriptor, "rb") as stream:
                    opened = os.fstat(stream.fileno())
                    if _is_link(opened) or not stat.S_ISREG(opened.st_mode) or ApprovedAssetStore._identity(before) != ApprovedAssetStore._identity(opened):
                        raise ServiceError("source_conflict")
                    data = stream.read(maximum + 1)
                    after = os.fstat(stream.fileno())
                current = path.lstat() if directory_fd is None else os.stat(path.name, dir_fd=directory_fd, follow_symlinks=False)
                if (len(data) > maximum or _is_link(current) or ApprovedAssetStore._identity(current) != ApprovedAssetStore._identity(opened)
                        or (opened.st_size, opened.st_mtime_ns, opened.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns)
                        or root.resolve(strict=True) != root or path.resolve(strict=True) != path
                        or ApprovedAssetStore._identity(root.lstat()) != identity):
                    raise ServiceError("source_conflict")
                return data
        except (OSError, ValueError, RuntimeError):
            raise ServiceError("capability_unavailable") from None

    def load(self, path: Path, kind: str, maximum: int):
        selected = [(item, self.roots[item.root_index]) for item in self.manifest.assets
                    if item.kind == kind and self.roots[item.root_index].joinpath(*item.relative_path.split("/")) == path]
        if len(selected) != 1:
            raise ServiceError("repository_forbidden")
        approval, root = selected[0]
        expected = "local" if kind == "registry" else "recorded"
        if approval.provenance != expected and not (self.allow_test_assets and approval.provenance == "test"):
            raise ServiceError("capability_unavailable")
        raw = self._read(root, path, self.root_identities[root], maximum)
        if hashlib.sha256(raw).hexdigest() != approval.digest:
            raise ServiceError("source_conflict")
        try:
            document = parse_bounded_json(raw.decode("utf-8"), max_bytes=maximum, max_depth=24, max_nodes=100000)
        except (ValueError, UnicodeError):
            raise ServiceError("capability_unavailable") from None
        actual = document.get("origin" if kind == "registry" else "provenance") if type(document) is dict else None
        if actual != approval.provenance:
            raise ServiceError("capability_unavailable")
        if kind in self.loaded and self.loaded[kind] != (approval, root, path, maximum):
            raise ServiceError("source_conflict")
        self.loaded[kind] = (approval, root, path, maximum)
        return document

    def verify(self):
        raw = self._read(self.operator_root, self.manifest_path, self.operator_identity, 65536)
        if hashlib.sha256(raw).hexdigest() != self.manifest_digest:
            raise ServiceError("source_conflict")
        for approval, root, path, maximum in self.loaded.values():
            raw = self._read(root, path, self.root_identities[root], maximum)
            if hashlib.sha256(raw).hexdigest() != approval.digest:
                raise ServiceError("source_conflict")

    @property
    def production_approved(self):
        return (not self.allow_test_assets and "registry" in self.loaded
                and self.loaded["registry"][0].provenance == "local")
