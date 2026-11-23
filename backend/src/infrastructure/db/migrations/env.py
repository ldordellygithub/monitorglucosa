"""Entorno async de Alembic con tabla de versiones en el esquema `app`."""

from __future__ import annotations

import asyncio
from typing import Any

from alembic import context
from sqlalchemy import Connection, pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from src.infrastructure.db.config import DatabaseConfig
from src.infrastructure.db.engine import create_engine
from src.infrastructure.db.metadata import metadata

VERSION_TABLE_SCHEMA = "app"
target_metadata = metadata


def _configure_context(**kwargs: Any) -> None:
    context.configure(
        target_metadata=target_metadata,
        version_table_schema=VERSION_TABLE_SCHEMA,
        include_schemas=True,
        **kwargs,
    )


def do_run_migrations(connection: Connection) -> None:
    """Ejecuta las migraciones usando una conexión síncrona puenteada por `run_sync`."""
    _configure_context(connection=connection)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_offline() -> None:
    """Ejecuta migraciones en modo offline (generación de SQL sin conexión)."""
    url = context.config.get_main_option("sqlalchemy.url")
    _configure_context(
        url=url,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Crea un motor async con `NullPool` y ejecuta las migraciones online."""
    db_config = context.config.attributes.get("db_config")
    if isinstance(db_config, DatabaseConfig):
        connectable = create_engine(db_config)
    else:
        configuration = context.config.get_section(context.config.config_ini_section)
        connectable = async_engine_from_config(
            configuration or {},
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )

    try:
        async with connectable.begin() as connection:
            await connection.run_sync(do_run_migrations)
    finally:
        await connectable.dispose()


def run_migrations_online() -> None:
    """Ejecuta migraciones online reutilizando la conexión inyectada si existe."""
    connection = context.config.attributes.get("connection")
    if isinstance(connection, Connection):
        do_run_migrations(connection)
        return

    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
