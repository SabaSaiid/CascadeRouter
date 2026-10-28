"""Fixed public failures shared by services and transport."""

from backend.schemas import ERROR_MESSAGES

STATUS_CODES = {
    "invalid_request": 422, "repository_forbidden": 403, "repository_unavailable": 422,
    "not_found": 404, "source_conflict": 409, "request_too_large": 413,
    "capacity_exceeded": 429, "capability_unavailable": 503, "internal_error": 500,
}


class ServiceError(Exception):
    def __init__(self, code: str):
        self.code = code
        self.status_code = STATUS_CODES[code]
        super().__init__(ERROR_MESSAGES[code])
