"""Private version capture and verification through the scanner's guarded reads."""

from __future__ import annotations

import hashlib
from dataclasses import asdict
from pathlib import Path

from backend.compiler.ast_scanner import ScannerOptions, _scan_repository_with_sources
from backend.schemas import PrivateSourceManifest, SourceFileVersion, content_digest
from .errors import ServiceError


class SourceCapture:
    def __init__(self, root):
        info = root.lstat()
        self.root_identity = info.st_dev, info.st_ino
        self.versions, self.counts = {}, {}

    def observe(self, version):
        item = SourceFileVersion.model_validate(asdict(version))
        previous = self.versions.get(item.file_path)
        if previous is not None and previous != item:
            raise ServiceError("source_conflict")
        self.versions[item.file_path] = item
        self.counts[item.file_path] = self.counts.get(item.file_path, 0) + 1

    def finish(self, response):
        if not response.complete:
            return None  # Partial/historical scans cannot authorize a patch.
        if len(self.versions) != response.scanned_files_count or any(count != 2 for count in self.counts.values()):
            raise ServiceError("source_conflict")
        manifest = PrivateSourceManifest(
            analysis_id=response.analysis_id, analysis_digest=hashlib.sha256(response.model_dump_json().encode("utf-8")).hexdigest(),
            root_device=self.root_identity[0], root_inode=self.root_identity[1], complete=True,
            files=tuple(self.versions[key] for key in sorted(self.versions)),
        )
        return PrivateSourceManifest.model_validate({**manifest.model_dump(), "digest": content_digest(manifest, exclude={"digest"})})


def verify_sources(analysis, manifest, *, on_source=None, check=lambda: None):
    """Caller holds RepositoryAccess.authorize across both verification passes.

    Reuses the original scanner boundary, including byte/AST/directory budgets,
    no-follow handles and SDK-shadow checks. Only the first verified pass invokes
    the pure transformer; the second detects changes during proposal generation.
    This remains point-in-time evidence, never an atomic filesystem snapshot.
    """
    manifest = PrivateSourceManifest.model_validate(manifest)
    root = Path(analysis.repository_path)
    info = root.lstat()
    if (not manifest.complete or not analysis.complete or manifest.digest is None
            or manifest.analysis_id != analysis.analysis_id
            or manifest.analysis_digest != hashlib.sha256(analysis.model_dump_json().encode("utf-8")).hexdigest()
            or (info.st_dev, info.st_ino) != (manifest.root_device, manifest.root_inode)):
        raise ServiceError("source_conflict")
    expected = {item.file_path: item for item in manifest.files}
    public_nodes = tuple(sorted((item.node_id, item.file_path, item.line_number, item.column_number,
                                 item.call_signature, item.current_model, item.function_name) for item in analysis.nodes))
    for iteration in range(2):
        seen = set()
        def source(parsed):
            check()
            version = None if parsed.version is None else SourceFileVersion.model_validate(asdict(parsed.version))
            if version is None or expected.get(version.file_path) != version or version.file_path in seen:
                raise ServiceError("source_conflict")
            seen.add(version.file_path)
            if iteration == 0 and on_source is not None:
                on_source(parsed)
        fresh = _scan_repository_with_sources(str(root), ScannerOptions(), source)
        nodes = tuple(sorted((item.node_id, item.file_path, item.line_number, item.column_number,
                              item.call_signature, item.current_model, item.function_name) for item in fresh.nodes))
        if not fresh.complete or seen != expected.keys() or nodes != public_nodes:
            raise ServiceError("source_conflict")
        check()
