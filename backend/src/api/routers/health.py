"""Router para comprobaciones de salud (/health y /health/ready)."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from src.api.dependencies import get_check_readiness
from src.application.readiness import CheckReadiness

router = APIRouter(tags=["salud"])


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ok"]


class ReadinessResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ready"]


@router.get(
    "/health",
    operation_id="getHealth",
    summary="Comprobar que la API está viva",
    response_model=HealthResponse,
    openapi_extra={
        "x-requirements": ["2.1", "6.2"],
        "security": [],
    },
)
async def get_health() -> HealthResponse:
    """Responde sin abrir ninguna conexión a la base de datos, así que nunca
    despierta Aurora. Lambda Web Adapter la usa como comprobación de arranque.
    Pública.
    """
    return HealthResponse(status="ok")


@router.get(
    "/health/ready",
    operation_id="getReadiness",
    summary="Comprobar que la API llega a la base de datos",
    response_model=ReadinessResponse,
    openapi_extra={
        "x-requirements": ["2.2", "6.2", "7.5", "NFR-2"],
        "security": [{"awsSigV4": []}],
    },
)
async def get_readiness(
    readiness: Annotated[CheckReadiness, Depends(get_check_readiness)],
) -> ReadinessResponse:
    """Ejecuta `SELECT 1` con una conexión propia que se cierra al terminar.
    Si Aurora está en pausa, la petición la despierta. Exige SigV4 en producción;
    en local no hay autorización.
    """
    await readiness.execute()
    return ReadinessResponse(status="ready")
