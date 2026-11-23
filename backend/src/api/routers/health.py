"""Router para comprobaciones de salud (/health y /health/ready)."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from src.api.dependencies import get_check_readiness
from src.application.readiness import CheckReadiness

router = APIRouter(tags=["salud"])


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ok"] = "ok"


class ReadinessResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ready"] = "ready"


@router.get("/health", response_model=HealthResponse)
async def get_health() -> HealthResponse:
    """Comprueba que la API está viva.

    Responde sin abrir ninguna conexión a la base de datos, así que nunca
    despierta Aurora. Lambda Web Adapter la usa como comprobación de arranque.
    Pública.
    """
    return HealthResponse(status="ok")


@router.get("/health/ready", response_model=ReadinessResponse)
async def get_readiness(
    readiness: Annotated[CheckReadiness, Depends(get_check_readiness)],
) -> ReadinessResponse:
    """Comprueba que la API llega a la base de datos.

    Ejecuta SELECT 1 con una conexión propia que se cierra al terminar.
    Si Aurora está en pausa, la petición la despierta.
    En caso de timeout o indisponibilidad, se responde 503 DATABASE_UNAVAILABLE.
    """
    await readiness.execute()
    return ReadinessResponse(status="ready")
