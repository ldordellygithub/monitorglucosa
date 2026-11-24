"""Router para la identidad del usuario actual."""

from typing import Annotated

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from src.api.dependencies import current_identity
from src.application.identity import Identity

router = APIRouter(prefix="/api/v1", tags=["identidad"])


class MeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sub: str = Field(
        description=(
            "Identificador estable del usuario en Cognito (claim `sub`). "
            "No es un dato de salud."
        ),
        json_schema_extra={"format": "uuid"},
    )


@router.get(
    "/me",
    operation_id="getCurrentIdentity",
    summary="Obtener la identidad del usuario autenticado",
    response_model=MeResponse,
    openapi_extra={
        "x-requirements": ["3.1", "3.2", "3.3", "3.5", "4.5"],
        "security": [{"cognitoAccessToken": []}],
    },
)
async def get_me(identity: Annotated[Identity, current_identity]) -> MeResponse:
    """Devuelve solo el identificador estable del usuario (claim `sub` de Cognito).
    Sirve para comprobar la cadena de autenticación completa:
    cliente → Cognito → API Gateway → API. No toca la base de datos.
    """
    return MeResponse(sub=identity.subject)
