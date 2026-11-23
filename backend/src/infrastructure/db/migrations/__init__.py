"""Ejecución programática y asíncrona de migraciones de Alembic."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import Connection

from src.infrastructure.db.config import DatabaseConfig
from src.infrastructure.db.engine import create_engine

MIGRATIONS_DIR = Path(__file__).resolve().parent
VERSION_TABLE_SCHEMA = "app"


def _build_alembic_config() -> Config:
    alembic_cfg = Config()
    alembic_cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    return alembic_cfg


def _read_current_revision(connection: Connection) -> str | None:
    migration_context = MigrationContext.configure(
        connection,
        opts={"version_table_schema": VERSION_TABLE_SCHEMA},
    )
    return migration_context.get_current_revision()


def _run_upgrade_head(connection: Connection, alembic_cfg: Config) -> None:
    alembic_cfg.attributes["connection"] = connection
    command.upgrade(alembic_cfg, "head")


def _run_downgrade(connection: Connection, alembic_cfg: Config, revision: str) -> None:
    alembic_cfg.attributes["connection"] = connection
    command.downgrade(alembic_cfg, revision)


async def upgrade_to_head(config: DatabaseConfig) -> str:
    """Aplica las migraciones hasta `head` y devuelve la revisión vigente."""
    alembic_cfg = _build_alembic_config()
    engine = create_engine(config)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(_run_upgrade_head, alembic_cfg)
        async with engine.connect() as connection:
            revision = await connection.run_sync(_read_current_revision)
        return revision or ""
    finally:
        await engine.dispose()


async def downgrade_to(config: DatabaseConfig, revision: str) -> str | None:
    """Revierte las migraciones hasta `revision` (p. ej. `base`)."""
    alembic_cfg = _build_alembic_config()
    engine = create_engine(config)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(_run_downgrade, alembic_cfg, revision)
        async with engine.connect() as connection:
            return await connection.run_sync(_read_current_revision)
    finally:
        await engine.dispose()


async def current_revision(config: DatabaseConfig) -> str | None:
    """Devuelve la revisión actual registrada en `app.alembic_version`."""
    engine = create_engine(config)
    try:
        async with engine.connect() as connection:
            return await connection.run_sync(_read_current_revision)
    finally:
        await engine.dispose()
