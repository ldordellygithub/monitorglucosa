"""Property 8: la API cumple su contrato (Schemathesis en proceso y comparador)."""

from __future__ import annotations

import asyncio
import json
import os
import string
import time
import uuid
from copy import deepcopy
from typing import Any

import asyncpg  # type: ignore[import-untyped]
import jwt
import pytest
import schemathesis
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import SecretStr
from schemathesis.checks import (
    CheckFunction,
    content_type_conformance,
    not_a_server_error,
    response_headers_conformance,
    response_schema_conformance,
    status_code_conformance,
)
from schemathesis.core.result import Ok
from schemathesis.generation.case import Case

from src.application.errors import DatabaseUnavailableError
from src.infrastructure.auth import LocalJwksAuthenticator
from src.infrastructure.db.config import DatabaseConfig
from src.infrastructure.db.engine import create_engine
from src.infrastructure.db.probe import SqlDatabaseProbe
from src.main import create_app
from tests.contract.openapi_comparator import compare_contracts, load_spec_contracts
from tests.unit.settings_env import build_settings, local_env
from tools.export_openapi import OPENAPI_JSON_PATH, SPECS_DIR

RAW_OPENAPI: dict[str, Any] = json.loads(OPENAPI_JSON_PATH.read_text(encoding="utf-8"))
SPEC_CONTRACTS = load_spec_contracts(SPECS_DIR)
SCHEMATHESIS_SCHEMA = schemathesis.openapi.from_dict(RAW_OPENAPI)

CONTRACT_CHECKS: list[CheckFunction] = [
    status_code_conformance,
    content_type_conformance,
    response_headers_conformance,
    response_schema_conformance,
]
HEALTHY_CHECKS: list[CheckFunction] = [not_a_server_error, *CONTRACT_CHECKS]

_RSA_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_RSA_PUBLIC_KEY = _RSA_PRIVATE_KEY.public_key()
_TEST_ISSUER = "http://jwt-issuer:9000"
_TEST_CLIENT_ID = "web"


class _InMemorySigningKey:
    def __init__(self, key: Any) -> None:
        self.key = key


class _InMemoryJWKClient:
    def get_signing_key_from_jwt(self, token: str) -> _InMemorySigningKey:
        return _InMemorySigningKey(_RSA_PUBLIC_KEY)


def _issue_valid_access_token() -> str:
    now = int(time.time())
    payload = {
        "iss": _TEST_ISSUER,
        "sub": str(uuid.uuid4()),
        "client_id": _TEST_CLIENT_ID,
        "token_use": "access",
        "scope": "openid",
        "iat": now,
        "exp": now + 300,
    }
    return jwt.encode(payload, _RSA_PRIVATE_KEY, algorithm="RS256")


class _ToggleProbe:
    def __init__(self, *, available: bool) -> None:
        self._available = available

    async def check(self) -> None:
        if not self._available:
            raise DatabaseUnavailableError("Aurora en pausa")


def _build_local_auth() -> LocalJwksAuthenticator:
    return LocalJwksAuthenticator(
        issuer=_TEST_ISSUER,
        jwks_url=f"{_TEST_ISSUER}/.well-known/jwks.json",
        client_ids=[_TEST_CLIENT_ID, "collector"],
        jwk_client=_InMemoryJWKClient(),  # type: ignore[arg-type]
    )


def _operation_strategies() -> list[st.SearchStrategy[Case[Any]]]:
    strategies: list[st.SearchStrategy[Case[Any]]] = []
    for result in SCHEMATHESIS_SCHEMA.get_all_operations():
        assert isinstance(result, Ok)
        strategies.append(result.ok().as_strategy())
    assert len(strategies) >= 3
    return strategies


OPERATION_CASE_STRATEGY: st.SearchStrategy[Case[Any]] = st.one_of(
    *_operation_strategies()
)

_APP_UP = create_app(
    build_settings(local_env()),
    authenticator=_build_local_auth(),
    database_probe=_ToggleProbe(available=True),
)
_APP_DOWN = create_app(
    build_settings(local_env()),
    authenticator=_build_local_auth(),
    database_probe=_ToggleProbe(available=False),
)
_CLIENT_UP = TestClient(_APP_UP, raise_server_exceptions=False)
_CLIENT_DOWN = TestClient(_APP_DOWN, raise_server_exceptions=False)

_ASCII_TEXT = st.text(
    alphabet=string.ascii_letters + string.digits + "-_",
    min_size=5,
    max_size=24,
)
_EXTRA_QUERY = st.dictionaries(
    keys=_ASCII_TEXT,
    values=_ASCII_TEXT.map(lambda val: f"qval~{val}"),
    max_size=2,
)


def _prepare_headers(
    case: Case[Any], auth_mode: str
) -> tuple[dict[str, str], str | None]:
    headers: dict[str, str] = {}
    if case.headers:
        for key, value in case.headers.items():
            # Filtramos valores no codificables en HTTP/1.1 (control/no-ASCII)
            try:
                encoded = str(value).encode("latin-1")
            except UnicodeEncodeError:
                continue
            if b"\r" not in encoded and b"\n" not in encoded:
                headers[str(key)] = str(value)

    secret_token: str | None = None
    if auth_mode == "valid_token":
        secret_token = _issue_valid_access_token()
        headers["Authorization"] = f"Bearer {secret_token}"
    elif auth_mode == "missing_token":
        headers = {k: v for k, v in headers.items() if k.lower() != "authorization"}
    return headers, secret_token


def _apply_headers(case: Case[Any], headers: dict[str, str]) -> None:
    if case.headers is not None:
        case.headers.clear()
        case.headers.update(headers)


@pytest.mark.req("fase-1a:2.3", "fase-1a:NFR-6")
@settings(max_examples=40, deadline=None)
@given(
    case=OPERATION_CASE_STRATEGY,
    auth_mode=st.sampled_from(["generated", "valid_token", "missing_token"]),
    db_available=st.booleans(),
    extra_query=_EXTRA_QUERY,
)
def test_schemathesis_peticiones_generadas_cumplen_el_contrato(
    case: Case[Any],
    auth_mode: str,
    db_available: bool,
    extra_query: dict[str, str],
) -> None:
    """Property 8 (API): cualquier petición generada cumple códigos, headers y body."""
    headers, _token = _prepare_headers(case, auth_mode)
    _apply_headers(case, headers)
    client = _CLIENT_UP if db_available else _CLIENT_DOWN
    checks = HEALTHY_CHECKS if db_available else CONTRACT_CHECKS

    response = client.request(
        method=case.method,
        url=case.formatted_path,
        params=extra_query or None,
        headers=headers,
    )

    case.validate_response(response, checks=checks)

    # Criterio 2.3: cualquier error de la API es uniforme y nunca repite inputs
    if response.status_code >= 400:
        body = response.json()
        assert set(body) == {"code", "message", "details"}
        for injected in extra_query.values():
            assert injected not in response.text


@pytest.mark.req("fase-1a:NFR-6")
@settings(max_examples=30, deadline=None)
@given(
    random_title=_ASCII_TEXT,
    random_desc=_ASCII_TEXT,
    random_example=_ASCII_TEXT,
    reverse_required=st.booleans(),
    reverse_anyof=st.booleans(),
    reverse_enum=st.booleans(),
)
def test_comparador_es_invariante_ante_metadatos_y_orden_de_esquemas(
    random_title: str,
    random_desc: str,
    random_example: str,
    reverse_required: bool,
    reverse_anyof: bool,
    reverse_enum: bool,
) -> None:
    """Property 8 (comparador): metadatos textuales y orden no rompen la conformidad."""
    mutated = deepcopy(RAW_OPENAPI)

    for schema_def in mutated["components"]["schemas"].values():
        schema_def["title"] = random_title
        schema_def["description"] = random_desc
        schema_def["example"] = random_example
        if reverse_required and isinstance(schema_def.get("required"), list):
            schema_def["required"] = list(reversed(schema_def["required"]))
        if reverse_enum and isinstance(schema_def.get("enum"), list):
            schema_def["enum"] = list(reversed(schema_def["enum"]))

    for resp_def in mutated["components"]["responses"].values():
        json_schema = (
            resp_def.get("content", {}).get("application/json", {}).get("schema", {})
        )
        if reverse_anyof and isinstance(json_schema.get("anyOf"), list):
            json_schema["anyOf"] = list(reversed(json_schema["anyOf"]))

    assert compare_contracts(mutated, SPEC_CONTRACTS) == []


@pytest.mark.req("fase-1a:NFR-6")
@settings(max_examples=30, deadline=None)
@given(
    mutation_kind=st.sampled_from(["operation_id", "drop_status", "change_type"]),
    new_id=_ASCII_TEXT.map(lambda s: f"mutated_{s}"),
    wrong_type=st.sampled_from(["integer", "boolean", "array"]),
    target_path=st.sampled_from(["/health", "/health/ready", "/api/v1/me"]),
)
def test_comparador_detecta_cualquier_divergencia_estructural(
    mutation_kind: str,
    new_id: str,
    wrong_type: str,
    target_path: str,
) -> None:
    """Property 8 (comparador): toda rotura estructural produce al menos un fallo."""
    broken = deepcopy(RAW_OPENAPI)

    if mutation_kind == "operation_id":
        broken["paths"][target_path]["get"]["operationId"] = new_id
    elif mutation_kind == "drop_status":
        responses = broken["paths"][target_path]["get"]["responses"]
        removable = [code for code in sorted(responses) if code != "200"]
        del responses[removable[0]]
    else:
        broken["components"]["schemas"]["ErrorDetail"]["properties"]["field"][
            "type"
        ] = wrong_type

    differences = compare_contracts(broken, SPEC_CONTRACTS)
    assert len(differences) >= 1


@pytest.mark.integration
@pytest.mark.req("fase-1a:2.3", "fase-1a:NFR-6")
def test_schemathesis_en_proceso_con_postgresql_real_y_bd_inaccesible() -> None:
    """Property 8 (integración): Schemathesis contra PostgreSQL 16 real y BD caída."""
    host = os.environ.get("TEST_POSTGRES_HOST", "127.0.0.1")
    port = int(os.environ.get("TEST_POSTGRES_PORT", "5432"))
    user = os.environ.get("TEST_POSTGRES_USER", "mg_api")
    password = os.environ.get("TEST_POSTGRES_PASSWORD", "testpass")
    db_name = os.environ.get("TEST_POSTGRES_DB", "monitorglucosa")

    async def _pg_available() -> bool:
        try:
            conn = await asyncpg.connect(
                host=host,
                port=port,
                user=user,
                password=password,
                database=db_name,
                timeout=2,
            )
            await conn.close()
            return True
        except (OSError, TimeoutError, asyncpg.PostgresError):
            return False

    if not asyncio.run(_pg_available()):
        pytest.skip(
            f"PostgreSQL 16 no disponible en {host}:{port} como {user} "
            "para Property 8 de integración"
        )

    live_probe = SqlDatabaseProbe(
        create_engine(
            DatabaseConfig(
                host=host,
                port=port,
                name=db_name,
                user=user,
                connect_timeout_s=5,
                password=SecretStr(password),
            )
        )
    )
    dead_probe = SqlDatabaseProbe(
        create_engine(
            DatabaseConfig(
                host="127.0.0.1",
                port=54321,
                name=db_name,
                user=user,
                connect_timeout_s=1,
                password=SecretStr(password),
            )
        )
    )
    live_client = TestClient(
        create_app(
            build_settings(local_env()),
            authenticator=_build_local_auth(),
            database_probe=live_probe,
        ),
        raise_server_exceptions=False,
    )
    dead_client = TestClient(
        create_app(
            build_settings(local_env()),
            authenticator=_build_local_auth(),
            database_probe=dead_probe,
        ),
        raise_server_exceptions=False,
    )

    @settings(max_examples=12, deadline=None)
    @given(
        case=OPERATION_CASE_STRATEGY,
        auth_mode=st.sampled_from(["generated", "valid_token", "missing_token"]),
        db_available=st.booleans(),
    )
    def _run(case: Case[Any], auth_mode: str, db_available: bool) -> None:
        headers, _token = _prepare_headers(case, auth_mode)
        _apply_headers(case, headers)
        client = live_client if db_available else dead_client
        checks = HEALTHY_CHECKS if db_available else CONTRACT_CHECKS
        response = client.request(
            method=case.method,
            url=case.formatted_path,
            headers=headers,
        )
        case.validate_response(response, checks=checks)
        if response.status_code >= 400:
            assert set(response.json()) == {"code", "message", "details"}

    _run()
