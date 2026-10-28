"""Benchmark lifecycle endpoints using the existing body/error/admission boundary."""

from fastapi import APIRouter, Request, Response

from backend.schemas import BenchmarkRequest, JobAccepted, JobResponse, RunId
from backend.services.errors import ServiceError
from .scan import ERRORS


router = APIRouter(prefix="/api")


async def _operation(request: Request, operation) -> Response:
    scans, jobs = request.app.state.scan_service, request.app.state.job_service
    if scans is None or jobs is None:
        raise ServiceError("capability_unavailable")

    def work(check):
        return operation(jobs, check).model_dump_json().encode("utf-8")

    payload = await scans._run(work, request.state.deadline)
    return Response(payload, media_type="application/json")


@router.post("/benchmark", status_code=202, response_model=JobAccepted, responses=ERRORS)
async def benchmark(body: BenchmarkRequest, request: Request) -> Response:
    response = await _operation(request, lambda jobs, check: jobs.submit(body, check))
    response.status_code = 202
    return response


@router.get("/runs/{run_id}", response_model=JobResponse, responses=ERRORS)
async def get_run(run_id: RunId, request: Request) -> Response:
    return await _operation(request, lambda jobs, check: jobs.get(run_id))


@router.post("/runs/{run_id}/cancel", response_model=JobResponse, responses=ERRORS)
async def cancel_run(run_id: RunId, request: Request) -> Response:
    return await _operation(request, lambda jobs, check: jobs.cancel(run_id))
