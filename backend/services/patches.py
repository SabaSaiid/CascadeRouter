"""Source-verified immutable patch proposals. No application or target execution."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from backend.compiler.patch_generator import PatchBudgetExceeded, PatchInputError, assemble_proposal, generate_file
from backend.schemas import PatchAccepted, PatchRequest
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
