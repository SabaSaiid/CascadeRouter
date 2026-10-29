"""FastAPI application entrypoint: `uvicorn backend.main:app`."""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend import __version__
from backend.api.routes import router
from backend.config import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the app. An explicit `settings` object overrides env-based settings everywhere."""
    explicit = settings is not None
    settings = settings if settings is not None else get_settings()
    logging.basicConfig(level=settings.log_level)

    app = FastAPI(
        title="CascadeRouter API",
        version=__version__,
        description="Autonomous FinOps & latency compiler for LLM architectures",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    app.include_router(router)
    if explicit:
        app.dependency_overrides[get_settings] = lambda: settings
    return app


def __getattr__(name: str) -> FastAPI:
    """Lazily build `backend.main:app` for uvicorn, so importing this module
    (e.g. in tests) never reads configuration as a side effect."""
    if name == "app":
        global app
        app = create_app()
        return app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
