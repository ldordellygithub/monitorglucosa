"""Pruebas de integración de /health y /health/ready contra PostgreSQL real."""

import asyncio

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from src.application.errors import DatabaseUnavailableError
from src.infrastructure.db.config import DatabaseConfig
from src.infrastructure.db.engine import create_engine
from src.infrastructure.db.probe import SqlDatabaseProbe
from src.main import create_app
from tests.unit.settings_env import build_settings, local_env


@pytest.mark.integration
@pytest.mark.req("fase-1a:2.1", "fase-1a:2.2")
def test_health_and_readiness_when_database_is_unreachable() -> None:
    """Verifica que con la BD caída, /health responde 200 y /health/ready 503."""

    async def _run() -> None:
        failing_config = DatabaseConfig(
            host="127.0.0.1",
            port=54321,  # Puerto cerrado
            name="monitorglucosa",
            user="mg_api",
            connect_timeout_s=1,
            password=SecretStr("testpass"),
        )
        failing_engine = create_engine(failing_config)
        failing_probe = SqlDatabaseProbe(failing_engine)

        app = create_app(build_settings(local_env()), database_probe=failing_probe)
        client = TestClient(app, raise_server_exceptions=False)

        res_health = client.get("/health")
        assert res_health.status_code == 200
        assert res_health.json() == {"status": "ok"}

        res_ready = client.get("/health/ready")
        assert res_ready.status_code == 503
        assert res_ready.headers.get("Retry-After") == "5"
        assert res_ready.json()["code"] == "DATABASE_UNAVAILABLE"

    asyncio.run(_run())


@pytest.mark.integration
@pytest.mark.req("fase-1a:2.1", "fase-1a:2.2")
def test_health_and_readiness_when_database_is_live() -> None:
    """Verifica que con PostgreSQL real operativo, /health y /health/ready dan 200."""

    async def _run() -> None:
        real_config = DatabaseConfig(
            host="127.0.0.1",
            port=5432,
            name="monitorglucosa",
            user="mg_api",
            connect_timeout_s=5,
            password=SecretStr("testpass"),
        )
        real_engine = create_engine(real_config)
        real_probe = SqlDatabaseProbe(real_engine)

        try:
            await real_probe.check()
        except DatabaseUnavailableError:
            pytest.skip(
                "PostgreSQL no disponible en 127.0.0.1:5432 para prueba en vivo"
            )

        live_app = create_app(build_settings(local_env()), database_probe=real_probe)
        live_client = TestClient(live_app)

        res_live_health = live_client.get("/health")
        assert res_live_health.status_code == 200
        assert res_live_health.json() == {"status": "ok"}

        res_live_ready = live_client.get("/health/ready")
        assert res_live_ready.status_code == 200
        assert res_live_ready.json() == {"status": "ready"}

    asyncio.run(_run())
