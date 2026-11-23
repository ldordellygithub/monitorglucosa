"""Pruebas unitarias de bootstrap.sql, metadatos SQLAlchemy y create_migrator_app."""

import io
import json
import logging
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import (
    CheckConstraint,
    Column,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Table,
    UniqueConstraint,
)

from src.infrastructure.db.config import DatabaseConfig
from src.infrastructure.db.metadata import NAMING_CONVENTION, metadata
from src.infrastructure.observability import JsonFormatter
from src.main import MIGRATOR_LOG_FIELDS, MigrationResult, create_migrator_app
from tests.unit.settings_env import build_settings, local_env, prod_env

REPO_ROOT = Path(__file__).resolve().parents[3]
BOOTSTRAP_SQL_PATH = REPO_ROOT / "scripts" / "sql" / "bootstrap.sql"
DATA_API_MAX_SQL_CHARS = 65_536


@pytest.mark.req("fase-1a:5.3")
def test_bootstrap_sql_es_un_unico_bloque_do_y_cabe_en_data_api() -> None:
    """bootstrap.sql debe ser un único bloque DO $$ ... $$ (< 65 536 caracteres)."""
    sql = BOOTSTRAP_SQL_PATH.read_text(encoding="utf-8")

    # Eliminar líneas de comentario SQL (`-- ...`) para inspeccionar la estructura real.
    body_lines = [
        line for line in sql.splitlines() if not line.lstrip().startswith("--")
    ]
    cleaned = "\n".join(body_lines).strip()

    assert len(sql) < DATA_API_MAX_SQL_CHARS
    assert re.fullmatch(r"DO\s+\$\$.*\$\$;?", cleaned, flags=re.DOTALL | re.IGNORECASE)
    # No debe haber otro delimitador $$ fuera de la apertura y el cierre del bloque.
    assert cleaned.count("$$") == 2


@pytest.mark.req("fase-1a:7.1")
def test_metadata_usa_esquema_app_y_convencion_de_nombres() -> None:
    """MetaData fija el esquema `app` y aplica la convención de structure.md."""
    assert metadata.schema == "app"
    assert metadata.naming_convention == NAMING_CONVENTION

    # Verificamos sobre tablas temporales en una copia de MetaData sin ensuciar la real.
    sample_meta = MetaData(schema=metadata.schema, naming_convention=NAMING_CONVENTION)
    parent = Table(
        "devices",
        sample_meta,
        Column("id", Integer, primary_key=True),
        Column("serial", Integer, nullable=False),
        UniqueConstraint("serial"),
        CheckConstraint("serial > 0", name="serial_positive"),
    )
    child = Table(
        "readings",
        sample_meta,
        Column("id", Integer, primary_key=True),
        Column("device_id", Integer, ForeignKey("app.devices.id"), nullable=False),
        Index(None, "device_id"),
    )

    assert parent.primary_key.name == "pk_devices"
    uq_names = {c.name for c in parent.constraints if isinstance(c, UniqueConstraint)}
    ck_names = {c.name for c in parent.constraints if isinstance(c, CheckConstraint)}
    fk_names = {fk.constraint.name for fk in child.foreign_keys if fk.constraint}
    ix_names = {ix.name for ix in child.indexes}

    assert "uq_devices_serial" in uq_names
    assert "ck_devices_serial_positive" in ck_names
    assert "fk_readings_device_id_devices" in fk_names
    assert "ix_readings_device_id" in ix_names


@pytest.mark.req("fase-1a:7.4")
def test_migrator_get_raiz_responde_200_sin_ejecutar_migraciones() -> None:
    """GET / es la comprobación de arranque de LWA y nunca dispara migraciones."""
    called = False

    async def fake_runner(config: DatabaseConfig) -> str:
        nonlocal called
        called = True
        return "20261123_baseline"

    app = create_migrator_app(build_settings(local_env()), run_migrations=fake_runner)
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert not called


@pytest.mark.req("fase-1a:7.4")
def test_migrator_post_events_aplica_migraciones_y_registra_log_json() -> None:
    """POST /events ejecuta upgrade_to_head, responde MigrationResult y loguea JSON."""
    received_configs: list[DatabaseConfig] = []

    async def fake_runner(config: DatabaseConfig) -> str:
        received_configs.append(config)
        return "20261123_baseline"

    app = create_migrator_app(build_settings(local_env()), run_migrations=fake_runner)

    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter(fields=MIGRATOR_LOG_FIELDS))
    migrator_log = logging.getLogger("migrator")
    migrator_log.addHandler(handler)
    try:
        client = TestClient(app)
        response = client.post("/events", json={"trigger": "deploy"})
    finally:
        migrator_log.removeHandler(handler)

    assert response.status_code == 200
    result = MigrationResult.model_validate(response.json())
    assert result.status == "ok"
    assert result.revision == "20261123_baseline"
    assert len(received_configs) == 1

    [log_line] = [json.loads(line) for line in stream.getvalue().splitlines()]
    assert log_line["logger"] == "migrator"
    assert log_line["level"] == "INFO"
    assert log_line["status"] == "ok"
    assert log_line["revision"] == "20261123_baseline"
    assert isinstance(log_line["duration_ms"], int)


@pytest.mark.req("fase-1a:7.4")
def test_migrator_post_events_fallido_devuelve_500_sin_trazas_ni_secretos() -> None:
    """Si falla una migración, POST /events responde 500 error sin filtrar detalles."""
    sensitive_marker = "detalle-interno-no-debe-salir"

    async def failing_runner(config: DatabaseConfig) -> str:
        raise RuntimeError(f"fallo de conexión con {sensitive_marker}")

    app = create_migrator_app(
        build_settings(local_env()), run_migrations=failing_runner
    )

    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter(fields=MIGRATOR_LOG_FIELDS))
    migrator_log = logging.getLogger("migrator")
    migrator_log.addHandler(handler)
    try:
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post("/events", json={})
    finally:
        migrator_log.removeHandler(handler)

    assert response.status_code == 500
    assert response.json() == {"status": "error", "revision": None}
    assert sensitive_marker not in response.text
    assert "Traceback" not in response.text

    [log_line] = [json.loads(line) for line in stream.getvalue().splitlines()]
    assert log_line["level"] == "ERROR"
    assert log_line["status"] == "error"
    assert log_line["revision"] is None
    assert log_line["traceback"].startswith("builtins.RuntimeError\n")
    assert sensitive_marker not in stream.getvalue()


@pytest.mark.req("fase-1a:7.4")
def test_migrator_desactiva_docs_redoc_y_openapi() -> None:
    """El migrator es una función interna sin documentación HTTP expuesta."""
    app = create_migrator_app(build_settings(local_env()))
    client = TestClient(app)

    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404


@pytest.mark.req("fase-1a:5.3", "fase-1a:7.4")
def test_migrator_en_prod_construye_database_config_sin_contrasena() -> None:
    """En prod el migrator usa autenticación IAM (sin DATABASE_PASSWORD)."""
    env = {**prod_env(), "DATABASE_USER": "mg_migrator"}
    app = create_migrator_app(build_settings(env))

    db_config: DatabaseConfig = app.state.database_config
    assert db_config.user == "mg_migrator"
    assert db_config.password is None
