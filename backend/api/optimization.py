"""Reference-only optimization under existing HTTP and bounded-worker controls."""

from fastapi import APIRouter, Request, Response

from backend.schemas import OptimizationRequest, OptimizationResponse
from backend.services.errors import ServiceError
from .scan import ERRORS


router = APIRouter(prefix="/api")


@router.post("/optimize", response_model=OptimizationResponse, responses=ERRORS)
async def optimize(body: OptimizationRequest, request: Request) -> Response:
    scans = request.app.state.scan_service
    service = request.app.state.optimization_service
    if scans is None or service is None:
        raise ServiceError("capability_unavailable")

    def work(check):
        return service.optimize(body, check).model_dump_json().encode("utf-8")

    payload = await scans._run(work, request.state.deadline)
    return Response(payload, media_type="application/json")
