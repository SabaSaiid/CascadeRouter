"""Bound actual streamed bytes before JSON parsing; sanitize every public failure."""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import threading
import time
from urllib.parse import urlsplit
from uuid import uuid4

from starlette.responses import Response

from backend.schemas import ErrorResponse
from backend.services.errors import ServiceError


LOCAL_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173", "http://[::1]:5173")


def error_response(code: str, request_id: str | None = None, status_code: int | None = None) -> Response:
    error = ServiceError(code)
    return Response(ErrorResponse(code=code, request_id=request_id).model_dump_json(),
                    status_code=status_code or error.status_code, media_type="application/json")


def _local_host(value: str) -> bool:
    try:
        parsed = urlsplit("http://" + value)
        if parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
            return False
        if parsed.port is not None and not 1 <= parsed.port <= 65535:
            return False
        return parsed.hostname == "localhost" or ipaddress.ip_address(parsed.hostname).is_loopback
    except (ValueError, TypeError):
        return False


class RequestBoundary:
    def __init__(self, app, *, settings):
        self.app = app
        self.settings = settings
        # Bound aggregate buffering as well as each individual request. Scans
        # have their own smaller admission limit, with no executor backlog.
        self.slots = threading.BoundedSemaphore(max(1, min(8, (64 * 1024 * 1024) // settings.max_request_body_bytes)))

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = "req_" + uuid4().hex
        state = scope.setdefault("state", {})
        state["request_id"] = request_id
        deadline = state["deadline"] = time.monotonic() + self.settings.scan_timeout_seconds
        origins = [value.decode("latin-1") for name, value in scope.get("headers", []) if name.lower() == b"origin"]

        async def failure(code):
            response = error_response(code, request_id)
            if len(origins) == 1 and origins[0] in LOCAL_ORIGINS:
                response.headers["Access-Control-Allow-Origin"] = origins[0]
                response.headers["Vary"] = "Origin"
            await response(scope, receive, send)

        if not self.slots.acquire(blocking=False):
            await failure("capacity_exceeded")
            return
        started = False

        async def tracked_send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            headers = scope.get("headers", [])
            hosts = [value.decode("latin-1") for name, value in headers if name.lower() == b"host"]
            if len(hosts) != 1 or not _local_host(hosts[0]) or len(origins) > 1 or any(origin not in LOCAL_ORIGINS for origin in origins):
                raise ServiceError("invalid_request")
            methods = [value for name, value in headers if name.lower() == b"access-control-request-method"]
            requested_headers = [value for name, value in headers if name.lower() == b"access-control-request-headers"]
            if scope.get("method") == "OPTIONS" and methods:
                allowed_headers = {b"accept", b"accept-language", b"content-language", b"content-type"}
                if (len(methods) != 1 or methods[0] not in (b"GET", b"POST") or len(requested_headers) > 1
                        or any(header.strip().lower() not in allowed_headers
                               for value in requested_headers for header in value.split(b","))):
                    raise ServiceError("invalid_request")
            lengths = [value for name, value in headers if name.lower() == b"content-length"]
            encodings = [value for name, value in headers if name.lower() == b"content-encoding"]
            transfers = [value for name, value in headers if name.lower() == b"transfer-encoding"]
            if (len(lengths) > 1 or (lengths and transfers) or any(value.lower() != b"identity" for value in encodings)
                    or any(value.lower() != b"chunked" for value in transfers)):
                raise ServiceError("invalid_request")
            declared = None
            if lengths:
                if len(lengths[0]) > 20 or not lengths[0].isdigit():
                    raise ServiceError("invalid_request")
                declared = int(lengths[0])
                if declared > self.settings.max_request_body_bytes:
                    raise ServiceError("request_too_large")
            body = bytearray()
            while True:
                try:
                    message = await asyncio.wait_for(receive(), max(0, deadline - time.monotonic()))
                except TimeoutError:
                    raise ServiceError("capability_unavailable") from None
                if message["type"] == "http.disconnect":
                    return
                if message["type"] != "http.request":
                    raise ServiceError("invalid_request")
                chunk = message.get("body", b"")
                if len(body) + len(chunk) > self.settings.max_request_body_bytes:
                    raise ServiceError("request_too_large")
                body.extend(chunk)
                if not message.get("more_body", False):
                    break
            if declared is not None and declared != len(body):
                raise ServiceError("invalid_request")
            delivered = False

            async def buffered_receive():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {"type": "http.request", "body": bytes(body), "more_body": False}
                return await receive()

            await self.app(scope, buffered_receive, tracked_send)
        except ServiceError as error:
            if not started:
                await failure(error.code)
        except Exception:
            logging.getLogger("cascaderouter.api").error("Request failed (%s).", request_id)
            if not started:
                await failure("internal_error")
        finally:
            self.slots.release()
