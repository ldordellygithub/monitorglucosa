"""Composition root de la API: el único punto donde se conectan las capas."""

import logging
import os

from fastapi import FastAPI

from src.api.errors import register_error_handlers
from src.api.middleware import RequestLogMiddleware
from src.api.routers.health import router as health_router
from src.api.routers.me import router as me_router
from src.application.ports import Authenticator, DatabaseProbe
from src.application.readiness import CheckReadiness
from src.config import Settings
from src.infrastructure.auth import (
    ApiGatewayClaimsAuthenticator,
    LocalJwksAuthenticator,
)
from src.infrastructure.db import DatabaseConfig, SqlDatabaseProbe, create_engine
from src.infrastructure.observability import JsonFormatter


def configure_logging(log_level: str) -> None:
    """Configura los loggers de la API y uvicorn con el formateador JSON."""
    formatter = JsonFormatter()
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    for logger_name in ("api", "uvicorn.error", "infrastructure"):
        log = logging.getLogger(logger_name)
        log.handlers = [handler]
        log.setLevel(log_level)


def create_app(
    settings: Settings | None = None,
    *,
    authenticator: Authenticator | None = None,
    database_probe: DatabaseProbe | None = None,
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

    if database_probe is not None:
        probe = database_probe
    else:
        ca_bundle_path: str | None = None
        if settings.environment == "prod":
            default_ca = "/etc/ssl/certs/rds-combined-ca-bundle.pem"
            if os.path.exists(default_ca):
                ca_bundle_path = default_ca

        db_config = DatabaseConfig(
            host=settings.database_host,
            port=settings.database_port,
            name=settings.database_name,
            user=settings.database_user,
            connect_timeout_s=settings.database_connect_timeout_s,
            password=settings.database_password,
            ca_bundle_path=ca_bundle_path,
        )
        engine = create_engine(db_config)
        probe = SqlDatabaseProbe(engine)

    readiness = CheckReadiness(probe)

    app.state.settings = settings
    app.state.authenticator = auth_adapter
    app.state.probe = probe
    app.state.readiness = readiness

    register_error_handlers(app)
    app.add_middleware(RequestLogMiddleware)
    app.include_router(health_router)
    app.include_router(me_router)

    return app
