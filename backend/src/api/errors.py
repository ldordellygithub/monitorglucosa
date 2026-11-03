"""Cuerpo de error uniforme y manejadores de errores de la API.

Ninguna respuesta repite lo recibido: los problemas de validación salen del tipo de
error de Pydantic, nunca de su mensaje ni de su `input`.
"""

import logging
import traceback
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.api.middleware import REQUEST_ID_HEADER, route_template
from src.application.errors import DatabaseUnavailableError
from src.application.identity import UnauthenticatedError

logger = logging.getLogger("api.errors")

ErrorCode = Literal[
    "VALIDATION_ERROR",
    "UNAUTHENTICATED",
    "NOT_FOUND",
    "METHOD_NOT_ALLOWED",
    "DATABASE_UNAVAILABLE",
    "INTERNAL_ERROR",
]

RETRY_AFTER_SECONDS = "5"


class ErrorDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: str
    problem: str


class ErrorBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: ErrorCode
    message: str
    details: list[ErrorDetail]


@dataclass(frozen=True)
class ErrorSpec:
    status: int
    code: ErrorCode
    message: str


VALIDATION_ERROR = ErrorSpec(422, "VALIDATION_ERROR", "La petición no es válida.")
UNAUTHENTICATED = ErrorSpec(401, "UNAUTHENTICATED", "Se requiere autenticación.")
NOT_FOUND = ErrorSpec(404, "NOT_FOUND", "Recurso no encontrado.")
METHOD_NOT_ALLOWED = ErrorSpec(405, "METHOD_NOT_ALLOWED", "Método no permitido.")
DATABASE_UNAVAILABLE = ErrorSpec(
    503,
    "DATABASE_UNAVAILABLE",
    "La base de datos se está despertando. Reintenta en unos segundos.",
)
INTERNAL_ERROR = ErrorSpec(500, "INTERNAL_ERROR", "Error interno.")

HTTP_ERRORS = {
    NOT_FOUND.status: NOT_FOUND,
    METHOD_NOT_ALLOWED.status: METHOD_NOT_ALLOWED,
}


def problem_of(error_type: str) -> str:
    """Problema en español para un tipo de error de Pydantic (`int_parsing`...)."""
    if error_type == "missing":
        return "obligatorio"
    if error_type.endswith("_type"):
        return "tipo no válido"
    if error_type.endswith(("too_short", "too_long")):
        return "longitud no válida"
    if error_type.startswith(("greater_than", "less_than")):
        return "fuera de rango"
    if error_type.endswith("_parsing"):
        return "formato no válido"
    return "valor no válido"


def field_of(error: Mapping[str, Any]) -> str:
    """Ubicación del error, por ejemplo `query.limit`.

    Los índices de lista se omiten (llegan con los lotes) y, en un campo no permitido,
    también el último elemento, que es el nombre que envió el cliente.
    """
    location = tuple(error["loc"])
    if error["type"] == "extra_forbidden":
        location = location[:-1]
    return ".".join(part for part in location if isinstance(part, str))


def safe_traceback(error: BaseException) -> str:
    """Clase y marcos de la excepción, sin su mensaje, que puede llevar datos."""
    kind = f"{type(error).__module__}.{type(error).__qualname__}"
    return kind + "\n" + "".join(traceback.format_tb(error.__traceback__))


def error_response(
    spec: ErrorSpec,
    details: list[ErrorDetail] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    body = ErrorBody(code=spec.code, message=spec.message, details=details or [])
    return JSONResponse(
        status_code=spec.status,
        content=body.model_dump(),
        headers=dict(headers) if headers else None,
    )


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def validation_error(
        request: Request, error: RequestValidationError
    ) -> JSONResponse:
        details = [
            ErrorDetail(field=field_of(item), problem=problem_of(item["type"]))
            for item in error.errors()
        ]
        return error_response(VALIDATION_ERROR, details)

    @app.exception_handler(UnauthenticatedError)
    async def unauthenticated(
        request: Request, error: UnauthenticatedError
    ) -> JSONResponse:
        return error_response(UNAUTHENTICATED)

    @app.exception_handler(DatabaseUnavailableError)
    async def database_unavailable(
        request: Request, error: DatabaseUnavailableError
    ) -> JSONResponse:
        return error_response(
            DATABASE_UNAVAILABLE, headers={"Retry-After": RETRY_AFTER_SECONDS}
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error(
        request: Request, error: StarletteHTTPException
    ) -> JSONResponse:
        spec = HTTP_ERRORS.get(error.status_code, INTERNAL_ERROR)
        return error_response(spec, headers=error.headers)

    @app.exception_handler(Exception)
    async def unhandled_error(request: Request, error: Exception) -> JSONResponse:
        # Starlette ejecuta este manejador fuera de RequestLogMiddleware y relanza la
        # excepción después: aquí se añade x-request-id y se registra la traza segura.
        request_id = getattr(request.state, "request_id", None)
        logger.error(
            "error no controlado",
            extra={
                "request_id": request_id,
                "method": request.method,
                "route": route_template(request.scope),
                "status": INTERNAL_ERROR.status,
                "traceback": safe_traceback(error),
            },
        )
        headers = {REQUEST_ID_HEADER: request_id} if request_id else None
        return error_response(INTERNAL_ERROR, headers=headers)
