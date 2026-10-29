"""Reference-only patch creation and protected artifact review; no apply route."""

from fastapi import APIRouter, Request, Response

from backend.schemas import PatchAccepted, PatchId, PatchProposal, PatchRequest, PatchValidationId, PatchValidationReport, PatchValidationRequest
from backend.services.errors import ServiceError
from .scan import ERRORS


router = APIRouter(prefix="/api")


async def _operation(request, operation):
    scans, patches = request.app.state.scan_service, request.app.state.patch_service
    if scans is None or patches is None:
        raise ServiceError("capability_unavailable")
    def work(check):
        return operation(patches, check).model_dump_json().encode("utf-8")
    payload = await scans._run(work, request.state.deadline)
    return Response(payload, media_type="application/json")


@router.post("/patches", status_code=201, response_model=PatchAccepted, responses=ERRORS)
async def create_patch(body: PatchRequest, request: Request):
    response = await _operation(request, lambda patches, check: patches.create(body, check))
    response.status_code = 201
    return response


@router.get("/patches/{patch_id}", response_model=PatchProposal, responses=ERRORS)
async def get_patch(patch_id: PatchId, request: Request):
    return await _operation(request, lambda patches, check: patches.get(patch_id, check))


@router.post("/patches/{patch_id}/validate", status_code=201, response_model=PatchValidationReport, responses=ERRORS)
async def validate_patch(patch_id: PatchId, request: Request, body: PatchValidationRequest | None = None):
    if request.query_params:
        raise ServiceError("invalid_request")
    response = await _operation(request, lambda patches, check: patches.validate(patch_id, check))
    response.status_code = 201
    return response


@router.get("/patch-validations/{validation_id}", response_model=PatchValidationReport, responses=ERRORS)
async def get_validation(validation_id: PatchValidationId, request: Request):
    if request.query_params:
        raise ServiceError("invalid_request")
    return await _operation(request, lambda patches, check: patches.get_validation(validation_id, check))
