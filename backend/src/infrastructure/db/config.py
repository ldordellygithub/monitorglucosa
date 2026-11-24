"""Configuración inmutable de la base de datos para la capa de infraestructura."""

from dataclasses import dataclass

from pydantic import SecretStr


@dataclass(frozen=True)
class DatabaseConfig:
    """Parámetros de conexión a la base de datos PostgreSQL/Aurora."""

    host: str
    port: int
    name: str
    user: str
    connect_timeout_s: int = 20
    password: SecretStr | None = None
    region: str = "us-east-1"
    ca_bundle_path: str | None = None
    ssl_mode: str | None = None
