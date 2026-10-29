"""HTTP route handlers. Handlers stay thin; logic lives in backend.compiler."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from backend import __version__
from backend.config import Settings, get_settings
from backend.schemas import HealthResponse, ModelTierConfig

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
