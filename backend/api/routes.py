"""HTTP route handlers. Handlers stay thin; logic lives in backend.compiler."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from starlette.concurrency import run_in_threadpool

from backend import __version__
from backend.api.deps import get_scan_store
from backend.compiler.ast_scanner import ScanPathError, resolve_scan_path, scan_repository
from backend.compiler.dag_builder import build_dag
from backend.config import REPO_ROOT, Settings, get_settings
from backend.schemas import HealthResponse, ModelTierConfig, ScanRequest, ScanResult
from backend.store import ScanStore, StoredScan

router = APIRouter(prefix="/api")


@router.get("/health", response_model=HealthResponse)
def health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    return HealthResponse(
        status="ok",
        version=__version__,
        environment=settings.environment,
        data_source=settings.data_source_mode,
        nebius_configured=settings.nebius_configured,
    )


@router.get("/models", response_model=list[ModelTierConfig])
def list_models(settings: Settings = Depends(get_settings)) -> list[ModelTierConfig]:
    return [
        ModelTierConfig(
            id=m.id,
            name=m.name,
            tier=m.tier,
            inputPricePerM=m.input_price_per_m,
            outputPricePerM=m.output_price_per_m,
            description=m.description,
            badgeColor=m.badge_color,
        )
        for m in settings.models
    ]


def _display_path(root) -> str:
    try:
        return root.relative_to(REPO_ROOT).as_posix() or "."
    except ValueError:
        return str(root)


@router.post("/scan", response_model=ScanResult)
async def scan(
    body: ScanRequest,
    settings: Settings = Depends(get_settings),
    store: ScanStore = Depends(get_scan_store),
) -> ScanResult:
    try:
        root = resolve_scan_path(body.repository_path, settings.allowed_scan_roots, REPO_ROOT)
    except ScanPathError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    repo = await run_in_threadpool(scan_repository, root)
    edges = build_dag(repo.trees, repo.calls)
    result = ScanResult(
        repository_path=_display_path(root),
        nodes=[c.to_llm_node() for c in repo.calls],
        graph_edges=edges,
        timestamp=datetime.now(timezone.utc).isoformat(),
        # Scanning is real static analysis of the requested repository, never replayed.
        data_source="live",
        scanned_files_count=repo.scanned_files_count,
        detected_framework=repo.detected_framework,
    )
    store.put(StoredScan(repo=repo, result=result))
    return result
