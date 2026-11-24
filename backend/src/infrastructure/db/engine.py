"""Creación del motor async de SQLAlchemy con asyncpg y NullPool."""

import os
import ssl
from typing import Any

import boto3  # type: ignore[import-untyped]
from sqlalchemy import URL
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from src.infrastructure.db.config import DatabaseConfig


def build_connect_args(config: DatabaseConfig) -> dict[str, Any]:
    """Construye los argumentos de conexión para asyncpg.

    En `prod`, el token IAM lo firma boto3 y TLS se fija en verify-full mediante un
    SSLContext configurado con el bundle de CA de RDS. En `local` o `test`, la
    contraseña viene de config.password.
    """
    connect_args: dict[str, Any] = {
        "timeout": config.connect_timeout_s,
        "command_timeout": config.connect_timeout_s,
    }

    if config.password is not None:
        connect_args["password"] = config.password.get_secret_value()
        if config.ca_bundle_path:
            if not os.path.exists(config.ca_bundle_path):
                raise FileNotFoundError(
                    f"El bundle de CA de RDS no existe: {config.ca_bundle_path}"
                )
            ssl_ctx = ssl.create_default_context(
                ssl.Purpose.SERVER_AUTH,
                cafile=config.ca_bundle_path,
            )
            ssl_ctx.check_hostname = True
            ssl_ctx.verify_mode = ssl.CERT_REQUIRED
            connect_args["ssl"] = ssl_ctx
        elif config.ssl_mode:
            connect_args["ssl"] = config.ssl_mode
        else:
            connect_args["ssl"] = False
    else:
        # Reutilizamos el cliente de boto3 para no pagar el coste de inicialización
        # de sesión/botocore en cada conexión del modelo NullPool.
        rds_client = boto3.client("rds", region_name=config.region)

        def _get_iam_token() -> str:
            return rds_client.generate_db_auth_token(  # type: ignore[no-any-return]
                DBHostname=config.host,
                Port=config.port,
                DBUsername=config.user,
            )

        connect_args["password"] = _get_iam_token

        # Siempre usamos un SSLContext explícito en prod con verify-full
        if config.ca_bundle_path:
            if not os.path.exists(config.ca_bundle_path):
                raise FileNotFoundError(
                    f"El bundle de CA de RDS no existe: {config.ca_bundle_path}"
                )
            ssl_ctx = ssl.create_default_context(
                ssl.Purpose.SERVER_AUTH,
                cafile=config.ca_bundle_path,
            )
        else:
            ssl_ctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)

        ssl_ctx.check_hostname = True
        ssl_ctx.verify_mode = ssl.CERT_REQUIRED
        connect_args["ssl"] = ssl_ctx

    return connect_args


def create_engine(config: DatabaseConfig) -> AsyncEngine:
    """Crea un motor async de SQLAlchemy con asyncpg y NullPool.

    Cada conexión se abre y se cierra al terminar (NullPool) para no impedir la
    pausa automática de Aurora Serverless v2 tras 300 s.
    """
    url = URL.create(
        drivername="postgresql+asyncpg",
        username=config.user,
        host=config.host,
        port=config.port,
        database=config.name,
    )

    connect_args = build_connect_args(config)

    return create_async_engine(
        url,
        poolclass=NullPool,
        connect_args=connect_args,
    )
