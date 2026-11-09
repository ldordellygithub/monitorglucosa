"""Composition root de la API: el único punto donde se conectan las capas."""

import logging

from fastapi import FastAPI

from src.api.errors import register_error_handlers
from src.api.middleware import RequestLogMiddleware
from src.api.routers.me import router as me_router
from src.application.ports import Authenticator
from src.config import Settings
from src.infrastructure.auth import (
    ApiGatewayClaimsAuthenticator,
    LocalJwksAuthenticator,
)
from src.infrastructure.observability import JsonFormatter


def configure_logging(log_level: str) -> None:
    """Configura los loggers de la API y uvicorn con el formateador JSON."""
    formatter = JsonFormatter()
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    for logger_name in ("api", "uvicorn.error"):
        log = logging.getLogger(logger_name)
        log.handlers = [handler]
        log.setLevel(log_level)


def create_app(
    settings: Settings | None = None,
    *,
    authenticator: Authenticator | None = None,
) -> FastAPI:
    """Crea y cablea la aplicación FastAPI según el entorno."""
    if settings is None:
        settings = Settings()

    configure_logging(settings.log_level)

    if settings.environment == "prod":
        app = FastAPI(
            title="monitorglucosa",
            docs_url=None,
            redoc_url=None,
            openapi_url=None,
        )
        auth_adapter = authenticator or ApiGatewayClaimsAuthenticator()
    else:
        app = FastAPI(title="monitorglucosa")
        auth_adapter = authenticator or LocalJwksAuthenticator(
            issuer=settings.local_jwt_issuer or "",
            jwks_url=str(settings.local_jwks_url or ""),
            client_ids=settings.local_jwt_client_ids or [],
        )

    app.state.settings = settings
    app.state.authenticator = auth_adapter

    register_error_handlers(app)
    app.add_middleware(RequestLogMiddleware)
    app.include_router(me_router)

    return app
