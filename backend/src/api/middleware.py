"""Identificador de correlación y log de acceso, una línea por petición."""

import json
import logging
import re
import time
import uuid

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger("api.access")

REQUEST_ID_HEADER = "x-request-id"
NO_ROUTE = "-"

# Lo que API Gateway usa como requestId (p. ej. `Jw0yzgtkNjMEPNA=`). Cualquier otra
# cosa se descarta: el valor llega en una cabecera y acaba en cada línea de log.
_REQUEST_ID = re.compile(r"[A-Za-z0-9._=-]{1,128}")


def request_id_of(scope: Scope) -> str:
    """`requestId` del contexto que deja Lambda Web Adapter, o un UUID4.

    La cabecera `x-amzn-request-context` es el propio contexto de la petición en JSON
    (`requestId`, `authorizer`...). Un `x-request-id` enviado por el cliente se ignora.
    """
    for name, value in scope["headers"]:
        if name == b"x-amzn-request-context":
            try:
                candidate = json.loads(value)["requestId"]
            except (ValueError, KeyError, TypeError):
                break
            if isinstance(candidate, str) and _REQUEST_ID.fullmatch(candidate):
                return candidate
            break
    return str(uuid.uuid4())


def route_template(scope: Scope) -> str:
    """Ruta plantilla (`/items/{item_id}`), nunca la URL real; `-` si no hubo ruta."""
    path = getattr(scope.get("route"), "path", None)
    return path if isinstance(path, str) else NO_ROUTE


class RequestLogMiddleware:
    """Fija `request_id`, lo devuelve en `x-request-id` y registra la petición."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = request_id_of(scope)
        scope.setdefault("state", {})["request_id"] = request_id
        status = 500  # lo que verá el cliente si la excepción escapa sin respuesta
        started = time.perf_counter()

        async def send_with_request_id(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            logger.info(
                "petición",
                extra={
                    "request_id": request_id,
                    "method": scope["method"],
                    "route": route_template(scope),
                    "status": status,
                    "duration_ms": round((time.perf_counter() - started) * 1000),
                },
            )
