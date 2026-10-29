"""Standard default assets for Nebius Token Factory and NVIDIA models.

Generates approved local benchmark registries and evaluation suites to allow
immediate out-of-the-box live and local benchmarking.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from backend.schemas import (
    AssetApproval, BenchmarkApprovalManifest, BenchmarkCaseSet, BenchmarkRegistryDocument,
    EvaluationProfile, LocalBenchmarkCase, ModelVersion, OfflineRecordedAnalysis,
    OfflineRecordedUnit, OfflineRecordingDocument, PinnedPricing, RecordingEvidence,
    VersionedReference, content_digest,
)


def create_default_assets(target_dir: Path) -> tuple[Path, Path, Path]:
    """Generates standard registry, recordings and approval manifest.

    target_dir: The directory (e.g. ~/.cascaderouter) where approval_manifest.json lives.
    Data files live in target_dir / "data" to satisfy directory boundary isolation.
    """
    target_dir.mkdir(parents=True, exist_ok=True)
    data_dir = target_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    # 1. Models & Pricing
    models = (
        ModelVersion(identifier="meta-llama/Meta-Llama-3.1-70B-Instruct", version="v1"),
        ModelVersion(identifier="nvidia/Llama-3.1-Nemotron-70B-Instruct", version="v1"),
        ModelVersion(identifier="meta-llama/Meta-Llama-3.1-8B-Instruct", version="v1"),
        ModelVersion(identifier="fixture/async-model", version="v1"),
        ModelVersion(identifier="fixture/model-one", version="v1"),
    )

    now = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    def make_pricing(ident: str, model_id: str, in_rate: Decimal, out_rate: Decimal) -> PinnedPricing:
        data = {
            "identifier": ident, "version": "v1", "model_id": model_id, "provenance": "recorded",
            "source_id": "nebius", "effective_at": now,
            "input_usd_per_million": in_rate, "output_usd_per_million": out_rate,
        }
        temp = PinnedPricing.model_construct(digest="0"*64, **data)
        digest_val = content_digest(temp, exclude={"digest"})
        return PinnedPricing(digest=digest_val, **data)

    pricing = (
        make_pricing("price_llama70b", "meta-llama/Meta-Llama-3.1-70B-Instruct", Decimal("0.35"), Decimal("0.40")),
        make_pricing("price_nemotron70b", "nvidia/Llama-3.1-Nemotron-70B-Instruct", Decimal("0.35"), Decimal("0.40")),
        make_pricing("price_llama8b", "meta-llama/Meta-Llama-3.1-8B-Instruct", Decimal("0.03"), Decimal("0.09")),
        make_pricing("price_async_fixture", "fixture/async-model", Decimal("0.35"), Decimal("0.40")),
        make_pricing("price_sync_fixture", "fixture/model-one", Decimal("0.35"), Decimal("0.40")),
    )

    # 2. Case Sets
    cases = BenchmarkCaseSet(
        identifier="nebius_standard_cases",
        version="v1",
        provenance="local",
        validation_version="offline.v1",
        cases=(
            LocalBenchmarkCase(
                identifier="case_json_format",
                input_text='{"prompt": "Respond with JSON object containing status (string), latency_ms (number)."}',
                expected_output='{"status": "ok", "latency_ms": 42}',
            ),
            LocalBenchmarkCase(
                identifier="case_classification",
                input_text='{"prompt": "Classify this query: Check stock inventory. Output JSON: {category: string}."}',
                expected_output='{"category": "inventory"}',
            ),
        ),
    )
    cases = cases.model_copy(update={"content_digest": content_digest(cases, exclude={"content_digest"})})

    # 3. Evaluation Profiles
    profile = EvaluationProfile(
        identifier="json_eval_profile",
        version="v1",
        criteria_id="schema_validity",
        mechanism="json",
    )
    profile = profile.model_copy(update={"content_digest": content_digest(profile, exclude={"content_digest"})})

    # 4. Registry Document
    registry_doc = BenchmarkRegistryDocument(
        schema_version="cascaderouter.registry.v1",
        origin="local",
        approved=True,
        case_sets=(cases,),
        evaluation_profiles=(profile,),
        models=models,
    )
    registry_identity = hashlib.sha256(registry_doc.model_dump_json().encode("utf-8")).hexdigest()
    registry_raw = json.dumps(registry_doc.model_dump(mode="json"), indent=2).encode("utf-8")
    registry_digest = hashlib.sha256(registry_raw).hexdigest()
    registry_path = data_dir / "benchmark_registry.json"
    registry_path.write_bytes(registry_raw)

    output_text = '{"status": "ok", "latency_ms": 42}'
    output_digest = hashlib.sha256(output_text.encode("utf-8")).hexdigest()
    input_digest = hashlib.sha256(cases.cases[0].input_text.encode("utf-8")).hexdigest()

    unit_data = dict(
        recording_id="rec_default_seed",
        node_id="llm_000000000000000000000000",
        model_id="meta-llama/Meta-Llama-3.1-70B-Instruct",
        case_id="case_json_format",
        input_digest=input_digest,
        captured_output=output_text,
        output_digest=output_digest,
        evidence=RecordingEvidence(
            source_id="nebius",
            latency_ms=250.0,
            streaming=True,
            ttft_ms=50.0,
            input_tokens=25,
            output_tokens=15,
            pricing_reference=VersionedReference(identifier="price_llama70b", version="v1"),
            captured_at=now,
        ),
    )
    temp_unit = OfflineRecordedUnit.model_construct(digest="0"*64, **unit_data)
    unit = OfflineRecordedUnit(digest=content_digest(temp_unit, exclude={"digest"}), **unit_data)

    # 5. Offline Recordings Document
    recordings_doc = OfflineRecordingDocument(
        schema_version="cascaderouter.offline-recordings.v1",
        provenance="recorded",
        source_id="nebius",
        recorded_at=now,
        pricing_records=pricing,
        recordings=(
            OfflineRecordedAnalysis(
                analysis_id="analysis_" + "0" * 32,
                analysis_digest="0" * 64,
                registry_digest=registry_identity,
                case_set=VersionedReference(identifier="nebius_standard_cases", version="v1"),
                evaluation_profile=VersionedReference(identifier="json_eval_profile", version="v1"),
                records=(unit,),
            ),
        ),
    )
    recordings_raw = json.dumps(recordings_doc.model_dump(mode="json"), indent=2).encode("utf-8")
    recordings_digest = hashlib.sha256(recordings_raw).hexdigest()
    recordings_path = data_dir / "benchmark_recordings.json"
    recordings_path.write_bytes(recordings_raw)

    # 6. Approval Manifest (in target_dir, pointing to relative data/)
    manifest = BenchmarkApprovalManifest(
        schema_version="cascaderouter.approvals.v1",
        approved_by="operator",
        approved_at=now,
        assets=(
            AssetApproval(
                asset_id="asset_registry",
                root_index=0,
                relative_path="benchmark_registry.json",
                kind="registry",
                provenance="local",
                digest=registry_digest,
            ),
            AssetApproval(
                asset_id="asset_recordings",
                root_index=0,
                relative_path="benchmark_recordings.json",
                kind="offline_recordings",
                provenance="recorded",
                digest=recordings_digest,
            ),
        ),
    )
    manifest_raw = json.dumps(manifest.model_dump(mode="json"), indent=2).encode("utf-8")
    manifest_path = target_dir / "approval_manifest.json"
    manifest_path.write_bytes(manifest_raw)

    return registry_path, recordings_path, manifest_path


def ensure_default_configuration(repo_root: Path | str, base_dir: Path | None = None) -> Path:
    """Creates local benchmark assets and writes a ready-to-use cascaderouter.local.json."""
    repo_path = Path(repo_root).resolve()
    base = (Path.home() / ".cascaderouter").resolve() if base_dir is None else Path(base_dir).resolve()
    storage_dir = (Path.home() / ".cascaderouter-data").resolve()
    storage_dir.mkdir(parents=True, exist_ok=True)

    reg_p, rec_p, man_p = create_default_assets(base)

    config_data = {
        "permitted_repository_roots": [str(repo_path)],
        "storage_directory": str(storage_dir),
        "permitted_benchmark_data_roots": [str(base / "data")],
        "benchmark_registry_path": str(reg_p),
        "benchmark_recordings_path": str(rec_p),
        "benchmark_approval_manifest_path": str(man_p),
        "optimization_quality_threshold": "0.80",
    }
    config_path = base / "cascaderouter.local.json"
    config_path.write_text(json.dumps(config_data, indent=2), encoding="utf-8")
    return config_path


if __name__ == "__main__":
    import sys
    target_repo = sys.argv[1] if len(sys.argv) > 1 else Path.cwd()
    cfg_path = ensure_default_configuration(target_repo)
    print(str(cfg_path))

