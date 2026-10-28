"""Local scan and immutable-snapshot retrieval routes."""

from fastapi import APIRouter, Request, Response

from backend.schemas import AnalysisId, ErrorResponse, HealthResponse, ScanRequest, ScanResponse
from backend.services.errors import ServiceError


router = APIRouter(prefix="/api")
ERRORS = {status: {"model": ErrorResponse} for status in (403, 404, 405, 409, 413, 422, 429, 500, 503)}


def _service(request: Request):
    service = request.app.state.scan_service
    if service is None:
        raise ServiceError("capability_unavailable")
    return service


@router.get("/health", response_model=HealthResponse, responses=ERRORS)
async def health(request: Request) -> HealthResponse:
    available = request.app.state.scan_service is not None
    jobs = request.app.state.job_service
    benchmarks = jobs is not None and jobs.available
    return HealthResponse(scan_available=available, analysis_retrieval_available=available,
                          configuration_required=not available, benchmark_available=benchmarks,
                          benchmark_provenance=jobs.executor.provenance if benchmarks else None,
                          benchmark_unavailable_reason="lifecycle_unavailable" if jobs is None else jobs.unavailable_reason)


@router.post("/scan", response_model=ScanResponse, responses=ERRORS)
async def scan(body: ScanRequest, request: Request) -> Response:
    payload = await _service(request).scan(body.repository_path, request.state.deadline)
    return Response(payload, media_type="application/json")


@router.get("/analyses/{analysis_id}", response_model=ScanResponse, responses=ERRORS)
async def retrieve(analysis_id: AnalysisId, request: Request) -> Response:
    payload = await _service(request).retrieve(analysis_id, request.state.deadline)
    return Response(payload, media_type="application/json")
