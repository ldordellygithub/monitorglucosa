"""Router para la identidad del usuario actual."""

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from src.api.dependencies import current_identity
from src.application.identity import Identity

router = APIRouter(prefix="/api/v1", tags=["identidad"])


class MeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sub: str


@router.get("/me", response_model=MeResponse)
async def get_me(identity: Identity = current_identity) -> MeResponse:
    """Devuelve la identidad (claim `sub`) del usuario autenticado."""
    return MeResponse(sub=identity.subject)
