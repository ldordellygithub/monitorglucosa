"""Composition root de la API y del migrator: único punto que conecta las capas."""

import logging
import os
import time
from collections.abc import Awaitable, Callable
from functools import partial
from typing import Literal

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from src.api.errors import register_error_handlers, safe_traceback
from src.api.middleware import RequestLogMiddleware
from src.api.openapi import build_openapi
from src.api.routers.health import router as health_router
from src.api.routers.me import router as me_router
from src.application.ports import Authenticator, DatabaseProbe
from src.application.readiness import CheckReadiness
from src.config import Settings
from src.infrastructure.auth import (
    ApiGatewayClaimsAuthenticator,
    LocalJwksAuthenticator,
)
from src.infrastructure.db import (
    DatabaseConfig,
    SqlDatabaseProbe,
    create_engine,
    upgrade_to_head,
)
from src.infrastructure.observability import JsonFormatter

RDS_CA_BUNDLE_DEFAULT_PATH = "/etc/ssl/certs/rds-combined-ca-bundle.pem"
MIGRATOR_LOG_FIELDS = ("status", "revision", "duration_ms", "traceback")

MigratorRunner = Callable[[DatabaseConfig], Awaitable[str]]


class MigrationResult(BaseModel):
    """Resultado JSON de una invocación del `migrator`, sin trazas ni secretos."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["ok", "error"]
    revision: str | None = None


def _build_database_config(settings: Settings) -> DatabaseConfig:
    """Traduce `Settings` en la configuración inmutable de infraestructura."""
    ca_bundle_path: str | None = None
    if settings.environment == "prod" and os.path.exists(RDS_CA_BUNDLE_DEFAULT_PATH):
        ca_bundle_path = RDS_CA_BUNDLE_DEFAULT_PATH

    return DatabaseConfig(
        host=settings.database_host,
        port=settings.database_port,
        name=settings.database_name,
        user=settings.database_user,
        connect_timeout_s=settings.database_connect_timeout_s,
        password=settings.database_password,
        ca_bundle_path=ca_bundle_path,
    )


def configure_logging(log_level: str) -> None:
    """Configura los loggers de la API y uvicorn con el formateador JSON."""
    formatter = JsonFormatter()
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    for logger_name in ("api", "uvicorn.error", "infrastructure"):
        log = logging.getLogger(logger_name)
        log.handlers = [handler]
        log.setLevel(log_level)


def configure_migrator_logging(log_level: str) -> None:
    """Configura los loggers del `migrator` con lista blanca de campos."""
    migrator_handler = logging.StreamHandler()
    migrator_handler.setFormatter(JsonFormatter(fields=MIGRATOR_LOG_FIELDS))

    migrator_log = logging.getLogger("migrator")
    migrator_log.handlers = [migrator_handler]
    migrator_log.setLevel(log_level)

    error_handler = logging.StreamHandler()
    error_handler.setFormatter(JsonFormatter())
    for logger_name in ("uvicorn.error", "infrastructure"):
        log = logging.getLogger(logger_name)
        log.handlers = [error_handler]
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
        db_config = _build_database_config(settings)
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
    app.openapi = partial(build_openapi, app)  # type: ignore[method-assign]

    return app


def create_migrator_app(
    settings: Settings | None = None,
    *,
    run_migrations: MigratorRunner | None = None,
) -> FastAPI:
    """Composition root de la Lambda `migrator` dentro de la VPC (ADR 0006, 7.4).

    Expone `GET /` para la comprobación de arranque de Lambda Web Adapter y
    `POST /events` para ejecutar `upgrade_to_head` de forma síncrona.
    """
    if settings is None:
        settings = Settings()

    configure_migrator_logging(settings.log_level)
    db_config = _build_database_config(settings)
    runner = run_migrations or upgrade_to_head
    migrator_logger = logging.getLogger("migrator")

    app = FastAPI(
        title="monitorglucosa-migrator",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.settings = settings
    app.state.database_config = db_config

    @app.get("/")
    async def readiness_check() -> dict[str, str]:
        """Comprobación de arranque de Lambda Web Adapter; nunca toca la BD."""
        return {"status": "ok"}

    @app.post("/events", response_model=MigrationResult)
    async def handle_event() -> MigrationResult | JSONResponse:
        """Aplica las migraciones pendientes de Alembic hasta `head`."""
        started = time.monotonic()
        try:
            revision = await runner(db_config)
        except Exception as exc:
            duration_ms = int((time.monotonic() - started) * 1000)
            migrator_logger.error(
                "migración fallida",
                extra={
                    "status": "error",
                    "revision": None,
                    "duration_ms": duration_ms,
                    "traceback": safe_traceback(exc),
                },
            )
            body = MigrationResult(status="error", revision=None)
            return JSONResponse(status_code=500, content=body.model_dump())

        duration_ms = int((time.monotonic() - started) * 1000)
        migrator_logger.info(
            "migración completada",
            extra={
                "status": "ok",
                "revision": revision,
                "duration_ms": duration_ms,
            },
        )
        return MigrationResult(status="ok", revision=revision)

    return app
