"""Pruebas de integración contra PostgreSQL 16: bootstrap.sql, roles y Alembic."""

import asyncio
import os
import secrets
from pathlib import Path

import asyncpg  # type: ignore[import-untyped]
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from src.infrastructure.db.config import DatabaseConfig
from src.infrastructure.db.migrations import (
    current_revision,
    downgrade_to,
    upgrade_to_head,
)
from src.main import create_migrator_app
from tests.unit.settings_env import build_settings, local_env

REPO_ROOT = Path(__file__).resolve().parents[3]
BOOTSTRAP_SQL_PATH = REPO_ROOT / "scripts" / "sql" / "bootstrap.sql"
EXPECTED_BASELINE_REVISION = "20261123_baseline"


def _pg_params() -> dict[str, str]:
    return {
        "host": os.environ.get("TEST_POSTGRES_HOST", "127.0.0.1"),
        "port": os.environ.get("TEST_POSTGRES_PORT", "5432"),
        "superuser": os.environ.get("TEST_POSTGRES_SUPERUSER", "postgres"),
        "superpass": os.environ.get("TEST_POSTGRES_SUPERPASS", "testpass"),
    }


async def _connect_superuser(database: str = "postgres") -> asyncpg.Connection:
    params = _pg_params()
    try:
        return await asyncpg.connect(
            host=params["host"],
            port=int(params["port"]),
            user=params["superuser"],
            password=params["superpass"],
            database=database,
            timeout=3,
        )
    except (OSError, TimeoutError, asyncpg.PostgresError):
        pytest.skip(
            f"PostgreSQL 16 no disponible en {params['host']}:{params['port']} "
            "para pruebas de integración de migraciones y roles"
        )


async def _prepare_isolated_database() -> tuple[str, str, str, str]:
    """Crea una BD aislada de `mg_admin` (no superusuario) y ejecuta bootstrap.sql."""
    suffix = secrets.token_hex(4)
    db_name = f"mg_test_{suffix}"
    admin_pass = f"admin_{suffix}"
    migrator_pass = f"mig_{suffix}"
    api_pass = f"api_{suffix}"

    super_conn = await _connect_superuser("postgres")
    try:
        await super_conn.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'rds_iam') THEN
                    CREATE ROLE rds_iam NOLOGIN;
                END IF;
                IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mg_admin') THEN
                    CREATE ROLE mg_admin WITH LOGIN CREATEROLE;
                END IF;
                GRANT rds_iam TO mg_admin WITH ADMIN OPTION;
            END
            $$;
            """
        )
        # Fijar contraseña de mg_admin (solo para la BD de pruebas)
        await super_conn.execute(f"ALTER ROLE mg_admin WITH PASSWORD '{admin_pass}'")
        await super_conn.execute(f'CREATE DATABASE "{db_name}" OWNER mg_admin')
    finally:
        await super_conn.close()

    params = _pg_params()
    admin_conn = await asyncpg.connect(
        host=params["host"],
        port=int(params["port"]),
        user="mg_admin",
        password=admin_pass,
        database=db_name,
        timeout=5,
    )
    try:
        bootstrap_sql = BOOTSTRAP_SQL_PATH.read_text(encoding="utf-8")
        # Ejecutar bootstrap.sql como no-superusuario `mg_admin` (igual que Data API)
        await admin_conn.execute(bootstrap_sql)
        await admin_conn.execute(
            f"ALTER ROLE mg_migrator WITH PASSWORD '{migrator_pass}'"
        )
        await admin_conn.execute(f"ALTER ROLE mg_api WITH PASSWORD '{api_pass}'")
    finally:
        await admin_conn.close()

    return db_name, admin_pass, migrator_pass, api_pass


async def _drop_isolated_database(db_name: str) -> None:
    super_conn = await _connect_superuser("postgres")
    try:
        await super_conn.execute(
            """
            SELECT pg_terminate_backend(pid)
            FROM pg_stat_activity
            WHERE datname = $1 AND pid <> pg_backend_pid()
            """,
            db_name,
        )
        await super_conn.execute(f'DROP DATABASE IF EXISTS "{db_name}"')
    finally:
        await super_conn.close()


@pytest.mark.integration
@pytest.mark.req("fase-1a:5.3")
def test_bootstrap_roles_y_privilegios_minimos_en_postgres_16() -> None:
    """mg_migrator puede CREATE TABLE en app; mg_api solo tiene DML y nunca DDL."""

    async def _run() -> None:
        (
            db_name,
            admin_pass,
            migrator_pass,
            api_pass,
        ) = await _prepare_isolated_database()
        params = _pg_params()
        try:
            migrator_conn = await asyncpg.connect(
                host=params["host"],
                port=int(params["port"]),
                user="mg_migrator",
                password=migrator_pass,
                database=db_name,
                timeout=5,
            )
            try:
                assert await migrator_conn.fetchval("SHOW search_path") == "app"
                # mg_migrator puede crear tablas en el esquema app
                await migrator_conn.execute(
                    """
                    CREATE TABLE app.permission_probe (
                        id SERIAL PRIMARY KEY,
                        label TEXT NOT NULL
                    )
                    """
                )
            finally:
                await migrator_conn.close()

            # Re-ejecutar bootstrap.sql como mg_admin tras crear tablas sigue ok
            admin_conn = await asyncpg.connect(
                host=params["host"],
                port=int(params["port"]),
                user="mg_admin",
                password=admin_pass,
                database=db_name,
                timeout=5,
            )
            try:
                await admin_conn.execute(BOOTSTRAP_SQL_PATH.read_text(encoding="utf-8"))
            finally:
                await admin_conn.close()

            api_conn = await asyncpg.connect(
                host=params["host"],
                port=int(params["port"]),
                user="mg_api",
                password=api_pass,
                database=db_name,
                timeout=5,
            )
            try:
                assert await api_conn.fetchval("SHOW search_path") == "app"

                # mg_api NO puede crear tablas en app ni en public
                with pytest.raises(asyncpg.InsufficientPrivilegeError):
                    await api_conn.execute("CREATE TABLE app.forbidden (id INT)")

                with pytest.raises(asyncpg.InsufficientPrivilegeError):
                    await api_conn.execute("CREATE TABLE public.forbidden (id INT)")

                # mg_api SÍ tiene DML (INSERT, SELECT, UPDATE, DELETE) y secuencias
                inserted_id = await api_conn.fetchval(
                    "INSERT INTO app.permission_probe (label) "
                    "VALUES ('ok') RETURNING id"
                )
                assert inserted_id == 1
                assert (
                    await api_conn.fetchval(
                        "SELECT label FROM app.permission_probe WHERE id = $1",
                        inserted_id,
                    )
                    == "ok"
                )
                await api_conn.execute(
                    "UPDATE app.permission_probe SET label = 'updated' WHERE id = $1",
                    inserted_id,
                )
                await api_conn.execute(
                    "DELETE FROM app.permission_probe WHERE id = $1",
                    inserted_id,
                )

                # mg_api NO puede borrar ni alterar la tabla
                with pytest.raises(asyncpg.InsufficientPrivilegeError):
                    await api_conn.execute("DROP TABLE app.permission_probe")
            finally:
                await api_conn.close()
        finally:
            await _drop_isolated_database(db_name)

    asyncio.run(_run())


@pytest.mark.integration
@pytest.mark.req("fase-1a:7.1", "fase-1a:7.4")
def test_alembic_upgrade_downgrade_upgrade_y_migrator_app_real() -> None:
    """Verifica upgrade head -> downgrade base -> upgrade head y create_migrator_app."""

    async def _run() -> None:
        (
            db_name,
            _admin_pass,
            migrator_pass,
            _api_pass,
        ) = await _prepare_isolated_database()
        params = _pg_params()
        migrator_config = DatabaseConfig(
            host=params["host"],
            port=int(params["port"]),
            name=db_name,
            user="mg_migrator",
            connect_timeout_s=10,
            password=SecretStr(migrator_pass),
        )
        try:
            # 1. upgrade head
            rev_up_1 = await upgrade_to_head(migrator_config)
            assert rev_up_1 == EXPECTED_BASELINE_REVISION
            assert await current_revision(migrator_config) == EXPECTED_BASELINE_REVISION

            # Confirmar que alembic_version vive en esquema `app` y no en `public`
            check_conn = await asyncpg.connect(
                host=params["host"],
                port=int(params["port"]),
                user="mg_migrator",
                password=migrator_pass,
                database=db_name,
                timeout=5,
            )
            try:
                schemas = [
                    row["table_schema"]
                    for row in await check_conn.fetch(
                        """
                        SELECT table_schema
                        FROM information_schema.tables
                        WHERE table_name = 'alembic_version'
                        """
                    )
                ]
                assert schemas == ["app"]
            finally:
                await check_conn.close()

            # 2. downgrade base
            rev_down = await downgrade_to(migrator_config, "base")
            assert rev_down is None
            assert await current_revision(migrator_config) is None

            # 3. upgrade head nuevamente mediante create_migrator_app (POST /events)
            migrator_env = {
                **local_env("test"),
                "DATABASE_HOST": params["host"],
                "DATABASE_PORT": params["port"],
                "DATABASE_NAME": db_name,
                "DATABASE_USER": "mg_migrator",
                "DATABASE_PASSWORD": migrator_pass,
            }
            app = create_migrator_app(build_settings(migrator_env))
            client = TestClient(app)

            res_ready = client.get("/")
            assert res_ready.status_code == 200
            assert res_ready.json() == {"status": "ok"}

            res_migrate = client.post("/events", json={"source": "integration-test"})
            assert res_migrate.status_code == 200
            assert res_migrate.json() == {
                "status": "ok",
                "revision": EXPECTED_BASELINE_REVISION,
            }
            assert await current_revision(migrator_config) == EXPECTED_BASELINE_REVISION
        finally:
            await _drop_isolated_database(db_name)

    asyncio.run(_run())
