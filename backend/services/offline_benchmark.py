"""Offline captured-output evaluation through the existing job executor contract."""

from __future__ import annotations

import hashlib
import threading
from datetime import datetime, timezone

from backend.compiler.evaluator import evaluate, parse_bounded_json
from backend.compiler.metrics import calculate_cost
from backend.schemas import (
    BenchmarkMeasurement, BenchmarkPlan, CountMeasurement, NumberMeasurement, OfflineRecordingDocument,
    content_digest,
)
from .benchmark_assets import ApprovedAssetStore
from .benchmark_cases import BenchmarkRegistry, digest
from .errors import ServiceError


class OfflineBenchmarkExecutor:
    idempotent = True

    def __init__(self, registry: BenchmarkRegistry, document: OfflineRecordingDocument, *, assets: ApprovedAssetStore | None = None):
        self.registry = registry
        self.document = OfflineRecordingDocument.model_validate(document)
        document = self.document
        self.assets = assets
        self.provenance = self.document.provenance
        registry.validate_offline()
        if ((registry.document.origin == "test") != (self.provenance == "test")):
            raise ServiceError("capability_unavailable")
        if len(self.document.model_dump_json().encode("utf-8")) > 4 * 1024 * 1024:
            raise ServiceError("capacity_exceeded")
        self.identity = digest((registry.identity + content_digest(document)
                                + (assets.manifest_digest if assets is not None else "test-only")).encode("ascii"))
        self.case_sets = {item.identifier: item for item in registry.document.case_sets}
        self.profiles = {item.identifier: item for item in registry.document.evaluation_profiles}
        self.prices = {(item.identifier, item.version): item for item in document.pricing_records}
        model_ids = {item.identifier for item in registry.document.models}
        for group in document.recordings:
            cases = self.case_sets.get(group.case_set.identifier)
            profile = self.profiles.get(group.evaluation_profile.identifier)
            if (cases is None or profile is None or cases.version != group.case_set.version
                    or profile.version != group.evaluation_profile.version or group.registry_digest != registry.identity):
                raise ServiceError("source_conflict")
            case_map = {item.identifier: item for item in cases.cases}
            for item in group.records:
                if (item.case_id not in case_map or (item.model_id is not None and item.model_id not in model_ids)
                        or hashlib.sha256(case_map[item.case_id].input_text.encode("utf-8")).hexdigest() != item.input_digest):
                    raise ServiceError("source_conflict")
            if profile.mechanism != "exact":
                for case in cases.cases:
                    if case.expected_output is not None:
                        parse_bounded_json(case.expected_output)

    @property
    def production_approved(self):
        return (type(self.assets) is ApprovedAssetStore and self.assets.production_approved
                and self.registry.production_approved and self.registry.approval is self.assets
                and "offline_recordings" in self.assets.loaded
                and self.assets.loaded["offline_recordings"][0].provenance == "recorded"
                and self.provenance == "recorded")

    def version_records(self):
        return tuple(("recording", unit.recording_id, "v1", unit.digest, self.provenance)
                     for group in self.document.recordings for unit in group.records) + tuple(
            ("pricing", price.identifier, price.version, price.digest, self.provenance) for price in self.document.pricing_records)

    def _group(self, plan):
        if (plan.registry_digest != self.registry.identity or plan.execution_digest != self.identity or plan.provenance != self.provenance):
            raise ServiceError("source_conflict")
        for group in self.document.recordings:
            if (group.analysis_id == plan.analysis_id and group.analysis_digest == plan.analysis_digest
                    and group.case_set == plan.case_set and group.evaluation_profile == plan.evaluation_profile):
                return group
        raise ServiceError("capability_unavailable")

    def validate_plan(self, plan: BenchmarkPlan):
        if self.assets is not None:
            self.assets.verify()
        group = self._group(plan)
        cases = self.case_sets[plan.case_set.identifier]
        profile = self.profiles[plan.evaluation_profile.identifier]
        if (plan.case_set_digest != cases.content_digest or plan.evaluation_profile_digest != profile.content_digest
                or plan.case_ids != tuple(case.identifier for case in cases.cases)
                or not set(plan.unit_keys()) <= {record.unit_key() for record in group.records}):
            raise ServiceError("source_conflict")

    def execute(self, plan: BenchmarkPlan, cancellation: threading.Event, deadline: datetime):
        self.validate_plan(plan)
        group = self._group(plan)
        records = {item.unit_key(): item for item in group.records}
        cases = {item.identifier: item for item in self.case_sets[plan.case_set.identifier].cases}
        profile = self.profiles[plan.evaluation_profile.identifier]
        for key in plan.unit_keys():
            if cancellation.is_set() or datetime.now(timezone.utc) >= deadline:
                return
            record = records[key]
            evaluation = evaluate(cases[record.case_id], profile, record.captured_output)
            evidence = record.evidence
            ref = evidence.pricing_reference
            price = None if ref is None else self.prices.get((ref.identifier, ref.version))
            def number(value):
                return NumberMeasurement(availability="available" if value is not None else "unavailable", value=value)
            def count(value):
                return CountMeasurement(availability="available" if value is not None else "unavailable", value=value)
            yield BenchmarkMeasurement(
                node_id=record.node_id, model_id=record.model_id, case_id=record.case_id, provenance=self.provenance,
                latency_ms=number(evidence.latency_ms), ttft_ms=number(evidence.ttft_ms),
                input_tokens=count(evidence.input_tokens), output_tokens=count(evidence.output_tokens),
                cost_usd=number(None), calculated_cost=calculate_cost(evidence, price),
                evaluation_status=evaluation.status, evaluation=evaluation, quality_score=None,
                recording_id=record.recording_id, evidence_digest=record.digest,
                output_available=record.captured_output is not None,
            )
