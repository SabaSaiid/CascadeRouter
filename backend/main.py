"""Local FastAPI factory and explicit non-secret JSON configuration entry point."""

from __future__ import annotations

import argparse
import json
import logging
import os
import stat
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from starlette.exceptions import HTTPException
from starlette.middleware.cors import CORSMiddleware

from backend.api.boundaries import LOCAL_ORIGINS, RequestBoundary, error_response
from backend.api.scan import router
from backend.api.jobs import router as jobs_router
from backend.api.optimization import router as optimization_router
from backend.compiler.ast_scanner import _is_link
from backend.config import BackendConfig, ConfigurationError
from backend.services.errors import ServiceError
from backend.services.scan_service import ScanService
from backend.services.benchmark_cases import BenchmarkExecutor, BenchmarkRegistry, load_local_assets
from backend.services.jobs import JobService
from backend.services.optimization import OptimizationService


def create_app(settings: BackendConfig | None = None, *, benchmark_registry: BenchmarkRegistry | None = None,
               benchmark_executor: BenchmarkExecutor | None = None, allow_test_benchmarks: bool = False) -> FastAPI:
    settings = BackendConfig() if settings is None else BackendConfig.model_validate(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        service = None
        jobs = None
        if settings.permitted_repository_roots and settings.storage_directory is not None:
            try:
                service = ScanService(settings)
            except (ServiceError, ConfigurationError, OSError):
                logging.getLogger("cascaderouter.api").error("Scan services unavailable; check approved configuration and storage.")
        if service is not None:
            registry, executor = benchmark_registry, benchmark_executor
            if registry is None and executor is None:
                try:
                    registry, executor = load_local_assets(settings, allow_test_assets=allow_test_benchmarks is True)
                except ServiceError:
                    logging.getLogger("cascaderouter.api").error("Local benchmark assets unavailable.")
            try:
                jobs = JobService(settings, service.storage, service.access, registry=registry, executor=executor,
                                  allow_test_executor=allow_test_benchmarks is True)
            except (ServiceError, OSError):
                logging.getLogger("cascaderouter.api").error("Job lifecycle services unavailable.")
        app.state.scan_service = service
        app.state.job_service = jobs
        app.state.optimization_service = None if service is None else OptimizationService(settings, service, jobs)
        try:
            yield
        finally:
            if jobs is not None:
                jobs.close()
            if service is not None:
                service.close()
            app.state.scan_service = None
            app.state.job_service = None
            app.state.optimization_service = None

    app = FastAPI(title="CascadeRouter local scan API", version="1", lifespan=lifespan)
    app.state.scan_service = None
    app.state.job_service = None
    app.state.optimization_service = None

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, _error):
        return error_response("invalid_request", request.state.request_id)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, error):
        return error_response("not_found" if error.status_code == 404 else "invalid_request",
                              request.state.request_id, 422 if error.status_code == 400 else error.status_code)

    app.include_router(router)
    app.include_router(jobs_router)
    app.include_router(optimization_router)
    app.add_middleware(CORSMiddleware, allow_origins=list(LOCAL_ORIGINS), allow_methods=["GET", "POST"],
                       allow_headers=["Content-Type"], allow_credentials=False)
    app.add_middleware(RequestBoundary, settings=settings)
    return app


def load_settings(config_path: str) -> BackendConfig:
    """Only an explicitly named, bounded regular JSON file; never environment/dotenv."""
    try:
        path = Path(config_path)
        if not path.is_absolute() or path.suffix.lower() != ".json":
            raise ConfigurationError("An absolute JSON configuration path is required.")
        before = path.lstat()
        if _is_link(before) or not stat.S_ISREG(before.st_mode) or before.st_size > 65536:
            raise ConfigurationError("Configuration file is invalid or unavailable.")
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)
        with os.fdopen(os.open(path, flags), "rb") as stream:
            opened = os.fstat(stream.fileno())
            if (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino):
                raise ConfigurationError("Configuration identity changed.")
            data = stream.read(65537)
            after = os.fstat(stream.fileno())
        if len(data) > 65536 or (opened.st_size, opened.st_mtime_ns, opened.st_ctime_ns) != (
            after.st_size, after.st_mtime_ns, after.st_ctime_ns,
        ):
            raise ConfigurationError("Configuration changed or exceeds the size limit.")
        return BackendConfig.model_validate(json.loads(data))
    except (OSError, ValueError, RuntimeError, ValidationError):
        raise ConfigurationError("Configuration file is invalid or unavailable.") from None


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ConfigurationError("Startup arguments are invalid.")


def main() -> int:
    parser = _Parser(description="Loopback-only local scan API; explicit non-secret JSON settings.")
    parser.add_argument("--config", help="Absolute path to an approved non-secret JSON configuration file")
    try:
        args = parser.parse_args()
        settings = load_settings(args.config) if args.config else BackendConfig()
        # Configured startup must not look successful with scanning disabled.
        if args.config:
            settings.require_repository_roots()
            if settings.storage_directory is None:
                raise ConfigurationError("Explicit storage is required.")
        else:
            print("No configuration supplied: scan and retrieval are disabled.")
        import uvicorn
        uvicorn.run(create_app(settings), host=settings.bind_host, port=settings.bind_port, access_log=False)
        return 0
    except (ConfigurationError, ValidationError, OSError):
        print("Backend configuration is invalid or incomplete.")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
