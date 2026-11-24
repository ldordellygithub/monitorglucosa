"""Property 7: bootstrap.sql es idempotente tras n >= 1 ejecuciones no superusuario."""

import asyncio
import os
import secrets
from dataclasses import dataclass
from pathlib import Path

import asyncpg  # type: ignore[import-untyped]
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

REPO_ROOT = Path(__file__).resolve().parents[3]
BOOTSTRAP_SQL_PATH = REPO_ROOT / "scripts" / "sql" / "bootstrap.sql"


@dataclass(frozen=True)
class BootstrapState:
    """Instantánea completa del estado que gestiona `scripts/sql/bootstrap.sql`."""

    roles: tuple[tuple[object, ...], ...]
    memberships: tuple[tuple[str, str, bool], ...]
    schemas: tuple[tuple[str, str, tuple[str, ...]], ...]
    default_acls: tuple[tuple[str, str, str, tuple[str, ...]], ...]
    object_acls: tuple[tuple[str, str, tuple[str, ...]], ...]
    public_can_create_in_public: bool
    api_can_use_app: bool
    api_can_create_in_app: bool


def _pg_params() -> dict[str, str]:
    return {
        "host": os.environ.get("TEST_POSTGRES_HOST", "127.0.0.1"),
        "port": os.environ.get("TEST_POSTGRES_PORT", "5432"),
        "superuser": os.environ.get("TEST_POSTGRES_SUPERUSER", "postgres"),
        "superpass": os.environ.get("TEST_POSTGRES_SUPERPASS", "testpass"),
    }


async def _connect_superuser(database: str = "postgres") -> asyncpg.Connection:
    params = _pg_params()
    return await asyncpg.connect(
        host=params["host"],
        port=int(params["port"]),
        user=params["superuser"],
        password=params["superpass"],
        database=database,
        timeout=3,
    )


def _require_postgres() -> None:
    async def _probe() -> None:
        conn = await _connect_superuser("postgres")
        await conn.close()

    try:
        asyncio.run(_probe())
    except (OSError, TimeoutError, asyncpg.PostgresError):
        params = _pg_params()
        pytest.skip(
            f"PostgreSQL 16 no disponible en {params['host']}:{params['port']} "
            "para Property 7 (idempotencia de bootstrap.sql)"
        )


async def _snapshot_state(conn: asyncpg.Connection) -> BootstrapState:
    role_rows = await conn.fetch(
        """
        SELECT
            rolname,
            rolsuper,
            rolinherit,
            rolcreaterole,
            rolcreatedb,
            rolcanlogin,
            rolreplication,
            rolbypassrls,
            COALESCE(rolconfig, ARRAY[]::text[]) AS rolconfig
        FROM pg_roles
        WHERE rolname IN ('mg_migrator', 'mg_api')
        ORDER BY rolname
        """
    )
    roles = tuple(
        (
            r["rolname"],
            r["rolsuper"],
            r["rolinherit"],
            r["rolcreaterole"],
            r["rolcreatedb"],
            r["rolcanlogin"],
            r["rolreplication"],
            r["rolbypassrls"],
            tuple(sorted(r["rolconfig"])),
        )
        for r in role_rows
    )

    membership_rows = await conn.fetch(
        """
        SELECT
            role_r.rolname AS role_name,
            member_r.rolname AS member_name,
            am.admin_option
        FROM pg_auth_members am
        JOIN pg_roles role_r ON role_r.oid = am.roleid
        JOIN pg_roles member_r ON member_r.oid = am.member
        WHERE member_r.rolname IN ('mg_migrator', 'mg_api')
           OR role_r.rolname IN ('mg_migrator', 'mg_api')
        ORDER BY role_r.rolname, member_r.rolname, am.admin_option
        """
    )
    memberships = tuple(
        (r["role_name"], r["member_name"], bool(r["admin_option"]))
        for r in membership_rows
    )

    schema_rows = await conn.fetch(
        """
        SELECT
            nspname,
            pg_get_userbyid(nspowner) AS owner_name,
            COALESCE(nspacl::text[], ARRAY[]::text[]) AS acl
        FROM pg_namespace
        WHERE nspname IN ('app', 'public')
        ORDER BY nspname
        """
    )
    schemas = tuple(
        (r["nspname"], r["owner_name"], tuple(sorted(r["acl"]))) for r in schema_rows
    )

    default_acl_rows = await conn.fetch(
        """
        SELECT
            pg_get_userbyid(d.defaclrole) AS role_name,
            n.nspname AS schema_name,
            d.defaclobjtype::text AS obj_type,
            COALESCE(d.defaclacl::text[], ARRAY[]::text[]) AS acl
        FROM pg_default_acl d
        JOIN pg_namespace n ON n.oid = d.defaclnamespace
        WHERE n.nspname = 'app'
        ORDER BY role_name, schema_name, obj_type
        """
    )
    default_acls = tuple(
        (r["role_name"], r["schema_name"], r["obj_type"], tuple(sorted(r["acl"])))
        for r in default_acl_rows
    )

    object_acl_rows = await conn.fetch(
        """
        SELECT
            c.relname,
            c.relkind::text AS relkind,
            COALESCE(c.relacl::text[], ARRAY[]::text[]) AS acl
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'app' AND c.relkind IN ('r', 'S')
        ORDER BY c.relname, c.relkind
        """
    )
    object_acls = tuple(
        (r["relname"], r["relkind"], tuple(sorted(r["acl"]))) for r in object_acl_rows
    )

    public_can_create = bool(
        await conn.fetchval("SELECT has_schema_privilege('public', 'public', 'CREATE')")
    )
    api_can_use_app = bool(
        await conn.fetchval("SELECT has_schema_privilege('mg_api', 'app', 'USAGE')")
    )
    api_can_create_in_app = bool(
        await conn.fetchval("SELECT has_schema_privilege('mg_api', 'app', 'CREATE')")
    )

    return BootstrapState(
        roles=roles,
        memberships=memberships,
        schemas=schemas,
        default_acls=default_acls,
        object_acls=object_acls,
        public_can_create_in_public=public_can_create,
        api_can_use_app=api_can_use_app,
        api_can_create_in_app=api_can_create_in_app,
    )


async def _run_idempotency_check(
    total_runs: int,
    *,
    create_table_after_first_run: bool,
) -> None:
    suffix = secrets.token_hex(4)
    db_name = f"mg_prop7_{suffix}"
    admin_pass = f"admin_{suffix}"
    migrator_pass = f"mig_{suffix}"
    bootstrap_sql = BOOTSTRAP_SQL_PATH.read_text(encoding="utf-8")
    params = _pg_params()

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
        await super_conn.execute(f"ALTER ROLE mg_admin WITH PASSWORD '{admin_pass}'")
        await super_conn.execute(f'CREATE DATABASE "{db_name}" OWNER mg_admin')
    finally:
        await super_conn.close()

    try:
        admin_conn = await asyncpg.connect(
            host=params["host"],
            port=int(params["port"]),
            user="mg_admin",
            password=admin_pass,
            database=db_name,
            timeout=5,
        )
        try:
            # Confirmar que `mg_admin` NO es superusuario (igual que el maestro de RDS)
            assert not await admin_conn.fetchval(
                "SELECT rolsuper FROM pg_roles WHERE rolname = current_user"
            )

            # Primera ejecución (n = 1): línea base de referencia
            await admin_conn.execute(bootstrap_sql)
            state_after_one = await _snapshot_state(admin_conn)

            # Invariantes obligatorias del Requisito 5.3 tras la primera ejecución
            assert ("rds_iam", "mg_api", False) in state_after_one.memberships
            assert ("rds_iam", "mg_migrator", False) in state_after_one.memberships
            assert (
                dict((name, owner) for name, owner, _acl in state_after_one.schemas)[
                    "app"
                ]
                == "mg_migrator"
            )
            assert not state_after_one.public_can_create_in_public
            assert state_after_one.api_can_use_app
            assert not state_after_one.api_can_create_in_app
            default_obj_types = {
                obj_type for _, _, obj_type, _ in state_after_one.default_acls
            }
            assert default_obj_types == {"r", "S"}

            if create_table_after_first_run:
                await admin_conn.execute(
                    f"ALTER ROLE mg_migrator WITH PASSWORD '{migrator_pass}'"
                )
                mig_conn = await asyncpg.connect(
                    host=params["host"],
                    port=int(params["port"]),
                    user="mg_migrator",
                    password=migrator_pass,
                    database=db_name,
                    timeout=5,
                )
                try:
                    await mig_conn.execute(
                        """
                        CREATE TABLE app.idempotency_probe (
                            id SERIAL PRIMARY KEY,
                            note TEXT NOT NULL
                        )
                        """
                    )
                finally:
                    await mig_conn.close()
                # Con tabla existente, comparamos 1 ejecución tras crear la tabla
                # frente a n ejecuciones sobre la misma base de datos.
                await admin_conn.execute(bootstrap_sql)
                baseline_state = await _snapshot_state(admin_conn)
            else:
                baseline_state = state_after_one

            # Ejecutar bootstrap.sql (total_runs - 1) veces adicionales sobre la BD
            for _ in range(total_runs - 1):
                await admin_conn.execute(bootstrap_sql)

            state_after_n = await _snapshot_state(admin_conn)
            assert state_after_n == baseline_state
        finally:
            await admin_conn.close()
    finally:
        cleanup_conn = await _connect_superuser("postgres")
        try:
            await cleanup_conn.execute(
                """
                SELECT pg_terminate_backend(pid)
                FROM pg_stat_activity
                WHERE datname = $1 AND pid <> pg_backend_pid()
                """,
                db_name,
            )
            await cleanup_conn.execute(f'DROP DATABASE IF EXISTS "{db_name}"')
        finally:
            await cleanup_conn.close()


@pytest.mark.integration
@pytest.mark.req("fase-1a:5.3")
def test_bootstrap_sql_es_idempotente_para_cualquier_n_ejecuciones() -> None:
    """Property 7: n >= 1 ejecuciones como no superusuario producen el mismo estado."""
    _require_postgres()

    @settings(max_examples=6, deadline=None)
    @given(
        total_runs=st.integers(min_value=1, max_value=6),
        create_table_after_first_run=st.booleans(),
    )
    def _property(total_runs: int, create_table_after_first_run: bool) -> None:
        asyncio.run(
            _run_idempotency_check(
                total_runs,
                create_table_after_first_run=create_table_after_first_run,
            )
        )

    _property()
