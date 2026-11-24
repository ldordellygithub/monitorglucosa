"""Pruebas de contrato OpenAPI 3.1, referencia publicada y conformidad con specs."""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
import schemathesis
from fastapi.testclient import TestClient
from openapi_spec_validator import validate
from schemathesis.checks import (
    CheckFunction,
    content_type_conformance,
    not_a_server_error,
    response_headers_conformance,
    response_schema_conformance,
    status_code_conformance,
)
from schemathesis.core.result import Ok

from src.application.errors import DatabaseUnavailableError
from src.application.identity import Identity, UnauthenticatedError
from src.main import create_app
from tests.contract.openapi_comparator import compare_contracts, load_spec_contracts
from tests.unit.settings_env import build_settings, local_env, prod_env
from tools.export_openapi import (
    API_README_PATH,
    BACKEND_DIR,
    OPENAPI_JSON_PATH,
    SPECS_DIR,
    check_artifacts,
)

VALID_SUB_UUID = "8f3c2a1e-5b7d-4c9a-9e2f-1a2b3c4d5e6f"
TEST_BEARER_VALUE = "test-access-jwt-for-contract"


class BearerAuthenticator:
    def authenticate(self, headers: Mapping[str, str]) -> Identity:
        if headers.get("authorization") != f"Bearer {TEST_BEARER_VALUE}":
            raise UnauthenticatedError("token ausente o inválido")
        return Identity(subject=VALID_SUB_UUID)


class StaticProbe:
    def __init__(self, *, available: bool) -> None:
        self._available = available

    async def check(self) -> None:
        if not self._available:
            raise DatabaseUnavailableError("BD en pausa")


@pytest.mark.req("fase-1a:7.1", "fase-1a:NFR-6")
def test_openapi_json_y_docs_api_readme_estan_al_dia() -> None:
    """backend/openapi.json y docs/api/README.md coinciden con lo generado."""
    assert check_artifacts() == []

    completed = subprocess.run(
        [sys.executable, str(BACKEND_DIR / "tools" / "export_openapi.py"), "--check"],
        cwd=BACKEND_DIR,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


@pytest.mark.req("fase-1a:7.1", "fase-1a:NFR-6")
def test_export_openapi_check_falla_si_un_archivo_difiere(tmp_path: Path) -> None:
    """check_artifacts detecta diferencias si openapi.json o README.md difieren."""
    stale_json = tmp_path / "openapi.json"
    stale_readme = tmp_path / "README.md"
    stale_json.write_text('{"openapi": "3.1.0"}\n', encoding="utf-8")
    stale_readme.write_text("# obsoleto\n", encoding="utf-8")

    diffs = check_artifacts(openapi_path=stale_json, readme_path=stale_readme)

    assert str(stale_json) in diffs
    assert str(stale_readme) in diffs


@pytest.mark.req("fase-1a:NFR-6")
def test_openapi_generado_y_contratos_de_specs_son_openapi_3_1_validos() -> None:
    """Tanto backend/openapi.json como los openapi.yaml de las specs son 3.1 válidos."""
    generated: dict[str, Any] = json.loads(
        OPENAPI_JSON_PATH.read_text(encoding="utf-8")
    )
    assert generated["openapi"] == "3.1.0"
    validate(generated)

    spec_contracts = load_spec_contracts(SPECS_DIR)
    assert len(spec_contracts) >= 1
    for _spec_name, contract in spec_contracts:
        assert contract["openapi"] == "3.1.0"
        validate(contract)


@pytest.mark.req("fase-1a:NFR-6")
def test_openapi_generado_es_conforme_con_la_union_de_los_contratos_de_specs() -> None:
    """backend/openapi.json cumple la unión de rutas, seguridad y esquemas de specs."""
    generated: dict[str, Any] = json.loads(
        OPENAPI_JSON_PATH.read_text(encoding="utf-8")
    )
    spec_contracts = load_spec_contracts(SPECS_DIR)

    differences = compare_contracts(generated, spec_contracts)

    assert differences == []


@pytest.mark.req("fase-1a:NFR-6")
def test_comparador_detecta_divergencias_en_rutas_codigos_seguridad_y_esquemas() -> (
    None
):
    """El comparador falla si cambia operationId, security, códigos o esquemas."""
    generated: dict[str, Any] = json.loads(
        OPENAPI_JSON_PATH.read_text(encoding="utf-8")
    )
    spec_contracts = load_spec_contracts(SPECS_DIR)

    # 1. operationId cambiado
    altered_op = deepcopy(generated)
    altered_op["paths"]["/health"]["get"]["operationId"] = "wrongId"
    assert any(
        "operationId" in diff for diff in compare_contracts(altered_op, spec_contracts)
    )

    # 2. Seguridad cambiada
    altered_sec = deepcopy(generated)
    altered_sec["paths"]["/api/v1/me"]["get"]["security"] = []
    assert any(
        "security" in diff for diff in compare_contracts(altered_sec, spec_contracts)
    )

    # 3. Falta un código de respuesta
    altered_code = deepcopy(generated)
    del altered_code["paths"]["/health/ready"]["get"]["responses"]["503"]
    assert any(
        "códigos de respuesta" in diff
        for diff in compare_contracts(altered_code, spec_contracts)
    )

    # 4. Falta una ruta completa
    altered_path = deepcopy(generated)
    del altered_path["paths"]["/health"]
    assert any(
        "Falta la operación" in diff
        for diff in compare_contracts(altered_path, spec_contracts)
    )

    # 5. Cambia un esquema de cuerpo
    altered_schema = deepcopy(generated)
    altered_schema["components"]["schemas"]["Me"]["properties"]["sub"]["type"] = (
        "integer"
    )
    assert any(
        "esquema de cuerpo" in diff
        for diff in compare_contracts(altered_schema, spec_contracts)
    )


@pytest.mark.req("fase-1a:NFR-6")
def test_docs_redoc_y_openapi_desactivados_en_prod_y_activos_en_local() -> None:
    """En prod /docs, /redoc y /openapi.json responden 404; en local responden 200."""
    prod_client = TestClient(create_app(build_settings(prod_env())))
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert prod_client.get(path).status_code == 404

    local_client = TestClient(create_app(build_settings(local_env())))
    for path in ("/docs", "/redoc", "/openapi.json"):
        response = local_client.get(path)
        assert response.status_code == 200

    assert API_README_PATH.exists()
    readme_text = API_README_PATH.read_text(encoding="utf-8")
    assert "fase-1a-infraestructura-y-auth" in readme_text
    assert "`GET /health`" in readme_text
    assert "`GET /health/ready`" in readme_text
    assert "`GET /api/v1/me`" in readme_text


@pytest.mark.req("fase-1a:2.3", "fase-1a:NFR-6")
@pytest.mark.parametrize(
    ("send_auth", "db_available"),
    [(True, True), (False, False)],
    ids=["bd-activa-y-autenticado", "bd-en-pausa-y-sin-token"],
)
def test_schemathesis_valida_respuestas_de_todas_las_operaciones(
    send_auth: bool,
    db_available: bool,
) -> None:
    """Schemathesis valida que cada operación cumple su contrato OpenAPI 3.1 en vivo."""
    raw_schema: dict[str, Any] = json.loads(
        OPENAPI_JSON_PATH.read_text(encoding="utf-8")
    )
    app = create_app(
        build_settings(local_env()),
        authenticator=BearerAuthenticator(),
        database_probe=StaticProbe(available=db_available),
    )
    client = TestClient(app, raise_server_exceptions=False)
    schema = schemathesis.openapi.from_dict(raw_schema)

    contract_checks: list[CheckFunction] = [
        status_code_conformance,
        content_type_conformance,
        response_headers_conformance,
        response_schema_conformance,
    ]
    checks = [not_a_server_error, *contract_checks] if db_available else contract_checks

    for op_result in schema.get_all_operations():
        assert isinstance(op_result, Ok)
        operation = op_result.ok()
        headers = {"Authorization": f"Bearer {TEST_BEARER_VALUE}"} if send_auth else {}
        case = operation.Case(headers=headers)
        response = client.request(
            method=case.method,
            url=case.formatted_path,
            headers=case.headers,
        )
        case.validate_response(response, checks=checks)
