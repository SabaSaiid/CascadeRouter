"""HTTP route handlers. Handlers stay thin; logic lives in backend.compiler."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from starlette.concurrency import run_in_threadpool

from backend import __version__
from backend.api.deps import (
    effective_mode,
    get_llm_client_factory,
    get_run_store,
    get_scan_store,
    get_spend_tracker,
)
from backend.compiler.ast_scanner import ScanPathError, resolve_scan_path, scan_repository
from backend.compiler.cases import CasesError, load_cases
from backend.compiler.dag_builder import build_dag
from backend.compiler.metrics import estimate_cost
from backend.compiler.prompt_capture import DEFAULT_MAX_OUTPUT_TOKENS
from backend.compiler.shadow_runner import BenchmarkRunner, RunExtras
from backend.config import REPO_ROOT, Settings, get_settings
from backend.guardrails import SpendTracker
from backend.schemas import (
    BenchmarkRequest,
    BenchmarkRun,
    BenchmarkStarted,
    HealthResponse,
    ModelTierConfig,
    OptimizeRequest,
    OptimizeResult,
    ScanRequest,
    ScanResult,
)
from backend.services.llm import LLMError
from backend.services.optimization import OptimizeError, optimize_run
from backend.store import RunStore, ScanStore, StoredRun, StoredScan

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
    # Keep sources (needed for patching) but not the ASTs, to bound memory.
    repo.trees = {}
    store.put(StoredScan(repo=repo, result=result))
    return result


@router.post("/benchmark", response_model=BenchmarkStarted, status_code=status.HTTP_202_ACCEPTED)
async def start_benchmark(
    body: BenchmarkRequest,
    settings: Settings = Depends(get_settings),
    scans: ScanStore = Depends(get_scan_store),
    runs: RunStore = Depends(get_run_store),
    tracker: SpendTracker = Depends(get_spend_tracker),
    client_factory=Depends(get_llm_client_factory),
) -> BenchmarkStarted:
    if body.repository_path is not None:
        try:
            root = resolve_scan_path(body.repository_path, settings.allowed_scan_roots, REPO_ROOT)
        except ScanPathError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
        scan = scans.get(str(root))
    else:
        scan = scans.find_by_node_ids(body.node_ids)
    if scan is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "No scan contains these nodes; run /api/scan first")

    known = {c.node_id: c for c in scan.repo.calls}
    unknown = [n for n in body.node_ids if n not in known]
    if unknown:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown node ids: {', '.join(unknown[:10])}")
    if runs.running_count() >= settings.max_concurrent_runs:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many benchmark runs in progress")

    mode = effective_mode(settings)
    if mode == "live":
        if tracker.exhausted():
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Daily spend cap reached")
        projected = projected_output_cost(scan.repo.root, body.node_ids, settings)
        if projected > tracker.remaining_usd():
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                f"Projected worst-case cost ${projected:.4f} exceeds the remaining daily budget "
                f"${tracker.remaining_usd():.4f}",
            )
    try:
        client = client_factory(settings, tracker)
    except LLMError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc

    calls = [known[n] for n in dict.fromkeys(body.node_ids)]
    run = BenchmarkRun(
        run_id=f"run_{uuid.uuid4().hex[:16]}",
        status="running",
        progress_pct=0.0,
        current_step="Queued",
        nodes=[],
        data_source=mode,  # type: ignore[arg-type]
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    extras = RunExtras(repo_root=scan.repo.root, node_ids=[c.node_id for c in calls], threshold=settings.quality_threshold)
    stored = StoredRun(run=run, extras=extras, scan=scan)
    runs.put(stored)
    stored.task = asyncio.create_task(BenchmarkRunner(settings, client).run(run, extras, calls))
    return BenchmarkStarted(run_id=run.run_id)


def projected_output_cost(repo_root, node_ids: list[str], settings: Settings) -> float:
    """Worst-case output cost of a run: every case on every model emits max_tokens."""
    try:
        cases = load_cases(repo_root)
    except CasesError:
        return 0.0  # the run itself reports the invalid file without calling any model
    per_case = sum(estimate_cost(m, 0, DEFAULT_MAX_OUTPUT_TOKENS) for m in settings.models)
    return per_case * sum(len(cases.get(n, [])) for n in dict.fromkeys(node_ids))


@router.get("/runs/{run_id}", response_model=BenchmarkRun)
async def get_run(run_id: str, runs: RunStore = Depends(get_run_store)) -> BenchmarkRun:
    stored = runs.get(run_id)
    if stored is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown run id")
    return stored.run


@router.post("/optimize", response_model=OptimizeResult)
async def optimize(
    body: OptimizeRequest,
    settings: Settings = Depends(get_settings),
    runs: RunStore = Depends(get_run_store),
) -> OptimizeResult:
    stored = runs.get(body.run_id)
    if stored is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown run id")
    cached = stored.optimized.get(body.quality_threshold)
    if cached is not None:
        return cached
    try:
        result = await run_in_threadpool(optimize_run, stored, body.quality_threshold, settings)
    except OptimizeError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    stored.optimized[body.quality_threshold] = result
    return result
