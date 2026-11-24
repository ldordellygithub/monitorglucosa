"""Pruebas unitarias de /health, /health/ready y acceso a base de datos."""

import asyncio
import ssl
from typing import Any
from unittest import mock

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.pool import NullPool

from src.application.errors import DatabaseUnavailableError
from src.application.readiness import CheckReadiness
from src.infrastructure.db.config import DatabaseConfig
from src.infrastructure.db.engine import build_connect_args, create_engine
from src.infrastructure.db.probe import SqlDatabaseProbe
from src.main import create_app
from tests.unit.settings_env import build_settings, local_env


class SuccessfulProbe:
    """Sonda de prueba que simula una base de datos operativa."""

    def __init__(self) -> None:
        self.checked = False

    async def check(self) -> None:
        self.checked = True


class FailingProbe:
    """Sonda de prueba que simula una base de datos reanudándose o inaccesible."""

    def __init__(self) -> None:
        self.checked = False

    async def check(self) -> None:
        self.checked = True
        raise DatabaseUnavailableError(
            "La base de datos se está despertando. Reintenta en unos segundos."
        )


# ==============================================================================
# Endpoint /health (Requisito 2.1)
# ==============================================================================


@pytest.mark.req("fase-1a:2.1")
def test_health_returns_200_without_touching_database() -> None:
    """GET /health devuelve 200 ok sin abrir conexión a la base de datos."""
    probe = SuccessfulProbe()
    app = create_app(build_settings(local_env()), database_probe=probe)
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert "x-request-id" in response.headers
    # NUNCA debe tocar la sonda ni despertar la base de datos
    assert not probe.checked


@pytest.mark.req("fase-1a:2.1")
def test_health_returns_200_even_when_database_is_failing() -> None:
    """GET /health responde 200 incluso si la base de datos está caída."""
    probe = FailingProbe()
    app = create_app(build_settings(local_env()), database_probe=probe)
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert not probe.checked


# ==============================================================================
# Endpoint /health/ready (Requisito 2.2, NFR-2)
# ==============================================================================


@pytest.mark.req("fase-1a:2.2")
def test_readiness_returns_200_when_database_is_ready() -> None:
    """GET /health/ready devuelve 200 ready cuando la base de datos responde."""
    probe = SuccessfulProbe()
    app = create_app(build_settings(local_env()), database_probe=probe)
    client = TestClient(app)

    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
    assert "x-request-id" in response.headers
    assert probe.checked


@pytest.mark.req("fase-1a:2.2", "fase-1a:NFR-2")
def test_readiness_returns_503_when_database_is_unavailable() -> None:
    """GET /health/ready devuelve 503 con Retry-After: 5 si la base de datos falla."""
    probe = FailingProbe()
    app = create_app(build_settings(local_env()), database_probe=probe)
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.headers.get("Retry-After") == "5"
    assert "x-request-id" in response.headers
    body = response.json()
    assert body["code"] == "DATABASE_UNAVAILABLE"
    assert "se está despertando" in body["message"]
    assert body["details"] == []
    assert probe.checked


# ==============================================================================
# Caso de uso CheckReadiness (Lógica de aplicación)
# ==============================================================================


@pytest.mark.req("fase-1a:2.2")
def test_check_readiness_use_case_delegates_to_probe() -> None:
    """CheckReadiness delega la verificación en la sonda inyectada."""

    async def _run() -> None:
        probe = SuccessfulProbe()
        readiness = CheckReadiness(probe)
        await readiness.execute()
        assert probe.checked

    asyncio.run(_run())


@pytest.mark.req("fase-1a:2.2")
def test_check_readiness_use_case_propagates_error() -> None:
    """CheckReadiness propaga DatabaseUnavailableError sin alterar."""

    async def _run() -> None:
        probe = FailingProbe()
        readiness = CheckReadiness(probe)
        with pytest.raises(DatabaseUnavailableError):
            await readiness.execute()

    asyncio.run(_run())


# ==============================================================================
# SqlDatabaseProbe (Requisitos 2.2, 5.4)
# ==============================================================================


class FakeConnection:
    def __init__(self, should_fail: Exception | None = None) -> None:
        self.should_fail = should_fail
        self.executed_query: Any = None
        self.closed = False

    async def execute(self, statement: Any) -> None:
        if self.should_fail:
            raise self.should_fail
        self.executed_query = statement

    async def close(self) -> None:
        self.closed = True

    async def __aenter__(self) -> "FakeConnection":
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()


class FakeEngine:
    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection

    def connect(self) -> FakeConnection:
        return self.connection


@pytest.mark.req("fase-1a:5.4")
def test_sql_database_probe_executes_select_1() -> None:
    """SqlDatabaseProbe ejecuta SELECT 1 y cierra su conexión efímera."""

    async def _run() -> None:
        conn = FakeConnection()
        probe = SqlDatabaseProbe(FakeEngine(conn))  # type: ignore[arg-type]
        await probe.check()
        assert str(conn.executed_query) == str(text("SELECT 1"))
        assert conn.closed

    asyncio.run(_run())


@pytest.mark.req("fase-1a:2.2", "fase-1a:NFR-2")
@pytest.mark.parametrize(
    "failure_exc",
    [
        OperationalError("connection timeout", params=None, orig=Exception("timeout")),
        SQLAlchemyError("database unreachable"),
        TimeoutError("timeout exceeded 20s"),
        ConnectionRefusedError("connection refused"),
        OSError("network unreachable"),
    ],
    ids=["operational-error", "sqlalchemy-error", "timeout", "refused", "os-error"],
)
def test_sql_database_probe_translates_exceptions(
    failure_exc: Exception,
) -> None:
    """SqlDatabaseProbe traduce timeouts y fallos en DatabaseUnavailableError."""

    async def _run() -> None:
        conn = FakeConnection(should_fail=failure_exc)
        probe = SqlDatabaseProbe(FakeEngine(conn))  # type: ignore[arg-type]

        with pytest.raises(DatabaseUnavailableError) as exc_info:
            await probe.check()

        assert "se está despertando" in str(exc_info.value)
        assert conn.closed

    asyncio.run(_run())


# ==============================================================================
# create_engine y DatabaseConfig (Requisito 5.3, 5.4)
# ==============================================================================


@pytest.mark.req("fase-1a:5.4")
def test_create_engine_uses_nullpool_and_connect_timeout() -> None:
    """create_engine usa NullPool y connect_timeout_s configurado."""
    config = DatabaseConfig(
        host="localhost",
        port=5432,
        name="monitorglucosa",
        user="mg_api",
        connect_timeout_s=15,
        password=SecretStr("local-secret"),
    )

    engine = create_engine(config)

    assert isinstance(engine, AsyncEngine)
    assert isinstance(engine.pool, NullPool)
    # Verifica que la URL no contiene la contraseña en texto plano
    assert "local-secret" not in str(engine.url)


@pytest.mark.req("fase-1a:5.3")
def test_create_engine_prod_configures_iam_token_and_verify_full() -> None:
    """create_engine en prod genera token IAM con boto3 y TLS verify-full."""
    config = DatabaseConfig(
        host="mydb.aurora.amazonaws.com",
        port=5432,
        name="monitorglucosa",
        user="mg_api",
        connect_timeout_s=20,
        password=None,  # En prod no hay contraseña
        region="us-east-1",
    )

    mock_boto_client = mock.MagicMock()
    mock_boto_client.generate_db_auth_token.return_value = "signed-iam-token"

    with mock.patch("boto3.client", return_value=mock_boto_client) as mock_boto:
        connect_args = build_connect_args(config)
        mock_boto.assert_called_once_with("rds", region_name="us-east-1")

        password_callable = connect_args.get("password")
        assert callable(password_callable)
        auth_value = password_callable()
        assert auth_value == "signed-iam-token"

        mock_boto_client.generate_db_auth_token.assert_called_once_with(
            DBHostname="mydb.aurora.amazonaws.com",
            Port=5432,
            DBUsername="mg_api",
        )

        ssl_ctx = connect_args.get("ssl")
        assert isinstance(ssl_ctx, ssl.SSLContext)
        assert ssl_ctx.check_hostname is True
        assert ssl_ctx.verify_mode == ssl.CERT_REQUIRED

        engine = create_engine(config)
        assert isinstance(engine.pool, NullPool)


@pytest.mark.req("fase-1a:5.3")
def test_create_engine_ca_bundle_sets_ssl_context(tmp_path: Any) -> None:
    """create_engine con ca_bundle_path configura SSLContext para verify-full."""
    ca_file = tmp_path / "dummy-ca.pem"
    ca_file.write_text("dummy-cert-data")

    config = DatabaseConfig(
        host="mydb.aurora.amazonaws.com",
        port=5432,
        name="monitorglucosa",
        user="mg_api",
        password=None,
        ca_bundle_path=str(ca_file),
    )

    with (
        mock.patch("boto3.client"),
        mock.patch("ssl.create_default_context") as mock_ssl_ctx,
    ):
        mock_context_instance = mock.MagicMock(spec=ssl.SSLContext)
        mock_ssl_ctx.return_value = mock_context_instance

        connect_args = build_connect_args(config)
        assert connect_args.get("ssl") == mock_context_instance

        mock_ssl_ctx.assert_called_once_with(
            ssl.Purpose.SERVER_AUTH, cafile=str(ca_file)
        )
        assert mock_context_instance.check_hostname is True
        assert mock_context_instance.verify_mode == ssl.CERT_REQUIRED


@pytest.mark.req("fase-1a:5.3")
def test_create_engine_raises_filenotfound_when_ca_bundle_missing() -> None:
    """build_connect_args lanza FileNotFoundError si el bundle CA no existe."""
    config = DatabaseConfig(
        host="localhost",
        port=5432,
        name="monitorglucosa",
        user="mg_api",
        password=None,
        ca_bundle_path="/nonexistent/ca.pem",
    )
    with pytest.raises(FileNotFoundError, match="El bundle de CA de RDS no existe"):
        build_connect_args(config)


# ==============================================================================
# Inyección y cableado en main.py create_app
# ==============================================================================


@pytest.mark.req("fase-1a:2.1", "fase-1a:2.2")
def test_create_app_wires_probe_and_readiness_automatically() -> None:
    """create_app crea y expone probe y readiness en app.state desde Settings."""
    settings = build_settings(local_env())
    app = create_app(settings)

    assert hasattr(app.state, "probe")
    assert isinstance(app.state.probe, SqlDatabaseProbe)
    assert hasattr(app.state, "readiness")
    assert isinstance(app.state.readiness, CheckReadiness)
