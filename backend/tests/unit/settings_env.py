"""Entornos de ejemplo y un constructor de `Settings` aislado del entorno real."""

import os
from collections.abc import Mapping
from unittest import mock

from src.config import Settings

# Variables locales: prohibidas en prod, obligatorias en local y test. Se repiten aquí
# a propósito, para que una errata en `src.config` no pase desapercibida.
LOCAL_ONLY_VARIABLES = (
    "DATABASE_PASSWORD",
    "LOCAL_JWT_ISSUER",
    "LOCAL_JWKS_URL",
    "LOCAL_JWT_CLIENT_IDS",
)

SHARED_ENV = {
    "DATABASE_HOST": "db.internal",
    "DATABASE_PORT": "5432",
    "DATABASE_NAME": "monitorglucosa",
    "DATABASE_USER": "mg_api",
}

LOCAL_ONLY_ENV = {
    "DATABASE_PASSWORD": "local-password",
    "LOCAL_JWT_ISSUER": "http://jwt-issuer:9000",
    "LOCAL_JWKS_URL": "http://jwt-issuer:9000/.well-known/jwks.json",
    "LOCAL_JWT_CLIENT_IDS": "web,collector",
}


def local_env(environment: str = "local") -> dict[str, str]:
    return {"ENVIRONMENT": environment, **SHARED_ENV, **LOCAL_ONLY_ENV}


def prod_env() -> dict[str, str]:
    return {"ENVIRONMENT": "prod", **SHARED_ENV}


def build_settings(env: Mapping[str, str]) -> Settings:
    """Construye `Settings` solo con `env`, sin las variables del proceso."""
    with mock.patch.dict(os.environ, dict(env), clear=True):
        return Settings()
