"""Source-verified immutable patch proposals. No application or target execution."""

from __future__ import annotations

import ast
import hashlib
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from backend.compiler.patch_generator import PatchBudgetExceeded, PatchInputError, assemble_proposal, generate_file, _splice
from backend.compiler.patch_validator import validate_file
from backend.schemas import PatchAccepted, PatchRequest, PatchValidationReport, PatchValidationResult
from .errors import ServiceError
from .source_manifests import verify_sources


class PatchService:
    def __init__(self, settings, scans, optimizations):
        self.settings, self.scans, self.optimizations = settings, scans, optimizations
        self.storage, self.access = scans.storage, scans.access

    def _context(self, analysis_id, optimization_id, check):
        analysis = self.storage.get(analysis_id)
        self.access.select(analysis.repository_path)
        record = self.storage.get_optimization(optimization_id)
        if record.response.result.plan.analysis_id != analysis_id:
            raise ServiceError("source_conflict")
        manifest = self.storage.get_source_manifest(analysis_id)
        if record.response.result.provenance != "recorded":
            raise ServiceError("capability_unavailable")
        self.optimizations.revalidate(record, check)
        return analysis, manifest, record

    def _generate(self, analysis, manifest, record, nodes, patch_id, created_at, check):
        decisions = {item.node_id: item for item in record.response.result.decisions}
        if not set(nodes) <= decisions.keys():
            raise ServiceError("invalid_request")
        public = {item.node_id: item for item in analysis.nodes}
        grouped = {}
        for node in nodes:
            if node not in public:
                raise ServiceError("source_conflict")
            grouped.setdefault(public[node].file_path, []).append(node)
        proposals = []
        def source(parsed):
            identifiers = grouped.get(parsed.fingerprint.file_path)
            if identifiers:
                proposals.append(generate_file(parsed, tuple(public[key] for key in identifiers),
                                                tuple(decisions[key] for key in identifiers)))
        try:
            verify_sources(analysis, manifest, on_source=source, check=check)
            return assemble_proposal(analysis, manifest, record, nodes, proposals, patch_id=patch_id,
                                     created_at=created_at, maximum=self.settings.max_job_result_bytes)
        except PatchBudgetExceeded:
            raise ServiceError("capacity_exceeded") from None
        except PatchInputError:
            raise ServiceError("source_conflict") from None
        except (OSError, ValueError, RuntimeError):
            raise ServiceError("source_conflict") from None

    def create(self, request: PatchRequest, check=lambda: None):
        request = PatchRequest.model_validate(request)
        analysis, manifest, record = self._context(request.analysis_id, request.optimization_id, check)
        nodes = request.node_ids or record.response.result.plan.node_ids
        with self.access.authorize(analysis.repository_path):
            proposal = self._generate(analysis, manifest, record, nodes, "patch_" + uuid4().hex,
                                      datetime.now(timezone.utc), check)
        self.optimizations.revalidate(record, check)
        check()
        self.storage.save_patch(proposal)
        return PatchAccepted(
            patch_id=proposal.manifest.patch_id, status=proposal.manifest.status,
            changed_nodes=sum(len(file.edits) for file in proposal.manifest.files), omitted_nodes=len(proposal.manifest.omissions),
            complete_for_requested_nodes=proposal.manifest.complete_for_requested_nodes,
            status_url="/api/patches/" + proposal.manifest.patch_id,
        )

    def get(self, patch_id, check=lambda: None):
        proposal = self.storage.get_patch(patch_id)
        header = proposal.manifest
        analysis, manifest, record = self._context(header.analysis_id, header.optimization_id, check)
        with self.access.authorize(analysis.repository_path):
            verified = self._generate(analysis, manifest, record, header.requested_node_ids, patch_id, header.created_at, check)
        if verified != proposal:
            raise ServiceError("source_conflict")
        self.optimizations.revalidate(record, check)
        check()
        return proposal

    def _validation_subject(self, patch_id, check):
        proposal = self.storage.get_patch(patch_id)
        header = proposal.manifest
        analysis = self.storage.get(header.analysis_id)
        self.access.select(analysis.repository_path)
        record = self.storage.get_optimization(header.optimization_id)
        response = record.response
        if (response.result.plan.analysis_id != analysis.analysis_id
                or header.optimization_digest != record.digest or header.policy_digest != response.policy.digest
                or header.provenance != response.result.provenance):
            raise ServiceError("source_conflict")
        if header.provenance != "recorded":
            raise ServiceError("capability_unavailable")
        self.optimizations.revalidate(record, check)
        return proposal, analysis, record

    @staticmethod
    def _validation_result(proposal, reason, files=()):
        states = {
            "statically_validated": ("validated", "valid", "available", "verified", True),
            "partial_proposal": ("partial", "valid", "available", "verified", False),
            "no_editable_files": ("unavailable", "valid", "available", "verified", False),
            "proposal_mismatch": ("invalid", "invalid", "available", "verified", False),
            "file_validation_failed": ("invalid", "valid", "available", "verified", False),
            "file_validation_unavailable": ("unavailable", "valid", "available", "verified", False),
            "source_changed": ("stale", "valid", "available", "stale", False),
            "source_evidence_unavailable": ("unavailable", "valid", "unavailable", "not_verified", False),
            "resource_limit": ("unavailable", "valid", "available", "not_verified", False),
        }
        status, structure, evidence, identity, complete = states[reason]
        header = proposal.manifest
        return PatchValidationResult(patch_id=header.patch_id, proposal_digest=proposal.digest, analysis_id=header.analysis_id,
            source_manifest_digest=header.source_manifest_digest, provenance=header.provenance, status=status, reason=reason,
            structure=structure, source_evidence=evidence, source_identity=identity, complete=complete,
            omitted_nodes=len(header.omissions), omissions=header.omissions,
            files=tuple(sorted(files, key=lambda file: file.file_path)))

    def _validate(self, proposal, analysis, manifest, record, check=lambda: None):
        """Internal static engine; production authority is required by validate()."""
        header = proposal.manifest
        if manifest is None:
            return self._validation_result(proposal, "source_evidence_unavailable")
        if (header.source_manifest_digest != manifest.digest or header.analysis_id != analysis.analysis_id
                or record.optimization_id != header.optimization_id or record.digest != header.optimization_digest
                or record.response.policy.digest != header.policy_digest or record.response.result.provenance != header.provenance):
            raise ServiceError("source_conflict")
        public = {node.node_id: node for node in analysis.nodes}
        decisions = {item.node_id: item for item in record.response.result.decisions}
        if not set(header.requested_node_ids) <= public.keys() & decisions.keys():
            raise ServiceError("source_conflict")
        grouped = {}
        for identifier in header.requested_node_ids:
            grouped.setdefault(public[identifier].file_path, []).append(identifier)
        stored = {file.file_path: file for file in header.files}
        checks, generated = [], []
        def source(parsed):
            check()
            identifiers = grouped.get(parsed.fingerprint.file_path)
            if not identifiers:
                return
            nodes = tuple(public[key] for key in identifiers)
            selected = tuple(decisions[key] for key in identifiers)
            expected = stored.get(parsed.fingerprint.file_path)
            if expected is None:
                generated.append(generate_file(parsed, nodes, selected))
            else:
                outcome, canonical = validate_file(parsed, expected, nodes, selected)
                checks.append(outcome)
                if canonical is not None:
                    generated.append(canonical)
        try:
            with self.access.authorize(analysis.repository_path):
                verify_sources(analysis, manifest, on_source=source, check=check)
        except ServiceError as error:
            if error.code not in ("source_conflict", "repository_unavailable"):
                raise
            return self._validation_result(proposal, "source_changed")
        except OSError:
            return self._validation_result(proposal, "source_changed")
        except (PatchBudgetExceeded, MemoryError, RecursionError):
            return self._validation_result(proposal, "resource_limit")
        if any(file.reason != "checked" for file in checks):
            limited = all(file.reason in ("checked", "resource_limit", "unsupported_encoding") for file in checks)
            return self._validation_result(proposal, "file_validation_unavailable" if limited else "file_validation_failed", checks)
        try:
            canonical = assemble_proposal(analysis, manifest, record, header.requested_node_ids, generated,
                patch_id=header.patch_id, created_at=header.created_at, maximum=self.settings.max_job_result_bytes)
        except (PatchBudgetExceeded, MemoryError, RecursionError):
            return self._validation_result(proposal, "resource_limit")
        if canonical != proposal:
            return self._validation_result(proposal, "proposal_mismatch", checks)
        reason = "no_editable_files" if not header.files else "partial_proposal" if header.omissions else "statically_validated"
        return self._validation_result(proposal, reason, checks)

    def validate(self, patch_id, check=lambda: None):
        proposal, analysis, record = self._validation_subject(patch_id, check)
        try:
            manifest = self.storage.get_source_manifest(analysis.analysis_id)
        except ServiceError as error:
            if error.code != "source_evidence_unavailable":
                raise
            manifest = None
        result = self._validate(proposal, analysis, manifest, record, check)
        self.optimizations.revalidate(record, check)
        check()
        report = PatchValidationReport.create(result=result, checked_at=datetime.now(timezone.utc),
                                              python_version=".".join(map(str, sys.version_info[:3])))
        check()
        return self.storage.save_validation(report)

    def get_validation(self, validation_id, check=lambda: None):
        """Read an immutable historical observation; do not refresh its checks."""
        report = self.storage.get_validation(validation_id)
        proposal, _, _ = self._validation_subject(report.result.patch_id, check)
        if report.result.proposal_digest != proposal.digest:
            raise ServiceError("source_conflict")
        check()
        return report

    def apply(self, patch_id: str, check=lambda: None) -> dict[str, object]:
        """Atomically applies a verified proposal to disk after creating a backup."""
        proposal, analysis, record = self._validation_subject(patch_id, check)
        applied_files = []
        with self.access.authorize(analysis.repository_path):
            repo_root = Path(analysis.repository_path)
            for patch_file in proposal.manifest.files:
                target_path = (repo_root / patch_file.file_path).resolve()
                if not target_path.is_relative_to(repo_root) or not target_path.is_file():
                    raise ServiceError("repository_forbidden")
                raw = target_path.read_bytes()
                current_digest = hashlib.sha256(raw).hexdigest()
                if current_digest != patch_file.original_digest:
                    raise ServiceError("source_conflict")
                
                replacements = [(e.start_byte, e.end_byte, f'"{e.proposed_model_id}"'.encode("utf-8")) for e in patch_file.edits]
                proposed = _splice(raw, replacements)
                try:
                    ast.parse(proposed.decode("utf-8"))
                except Exception:
                    raise ServiceError("source_conflict")
                
                backup_path = target_path.with_suffix(target_path.suffix + ".bak")
                backup_path.write_bytes(raw)
                temp_path = target_path.with_suffix(target_path.suffix + ".tmp")
                temp_path.write_bytes(proposed)
                os.replace(temp_path, target_path)
                
                applied_files.append({
                    "file_path": patch_file.file_path,
                    "backup_path": str(backup_path),
                    "edits_count": len(patch_file.edits),
                })
        check()
        return {
            "patch_id": patch_id,
            "status": "applied",
            "applied_at": datetime.now(timezone.utc).isoformat(),
            "applied_files": applied_files,
        }
