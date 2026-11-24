"""Property 4: los logs no contienen credenciales ni contenido."""

import json
import string

import pytest
from fastapi.testclient import TestClient
from hypothesis import given, settings
from hypothesis import strategies as st

from src.main import create_app
from tests.unit.probe_app import captured_logs, probe_client
from tests.unit.settings_env import build_settings, prod_env

CLIENT = probe_client()
PROD_CLIENT = TestClient(create_app(build_settings(prod_env())))

ALLOWED_FIELDS = {
    "timestamp",
    "level",
    "logger",
    "request_id",
    "method",
    "route",
    "status",
    "duration_ms",
    "traceback",
}

# El prefijo `valor~` no aparece en ninguna línea de log legítima: si aparece, el log
# arrastró algo de la petición. El resto es arbitrario.
VALUES = st.text(
    alphabet=string.ascii_letters + string.digits + "-._",
    min_size=4,
    max_size=30,
).map(lambda text: f"valor~{text}")

LAMBDA_REQUEST_ID = "Jw0yzgtkNjMEPNA="


@pytest.mark.req("fase-1a:2.4", "fase-1a:NFR-5")
@settings(deadline=None)
@given(
    authorization=VALUES,
    body_value=VALUES,
    query_value=VALUES,
    path_value=VALUES,
    claim_subject=VALUES,
    claim_client=VALUES,
    client_request_id=VALUES,
)
def test_logs_nunca_contienen_valores_de_la_peticion_y_solo_los_campos_permitidos(
    authorization: str,
    body_value: str,
    query_value: str,
    path_value: str,
    claim_subject: str,
    claim_client: str,
    client_request_id: str,
) -> None:
    headers = {
        "authorization": f"Bearer {authorization}",
        "x-request-id": client_request_id,
        "x-amzn-request-context": json.dumps(
            {
                "requestId": LAMBDA_REQUEST_ID,
                "authorizer": {
                    "jwt": {"claims": {"sub": claim_subject, "client_id": claim_client}}
                },
            }
        ),
    }
    injected = [
        authorization,
        body_value,
        query_value,
        path_value,
        claim_subject,
        claim_client,
        client_request_id,
    ]

    with captured_logs() as stream:
        CLIENT.get(
            f"/items/{path_value}", params={"limit": query_value}, headers=headers
        )
        CLIENT.post(
            "/items", json={"count": body_value, "name": body_value}, headers=headers
        )
        CLIENT.get("/boom", params={"q": query_value}, headers=headers)
        CLIENT.get("/items/5", headers=headers)

    lines = [json.loads(line) for line in stream.getvalue().splitlines()]
    assert len(lines) == 5  # una por petición, más la del error no controlado
    assert all(set(line) <= ALLOWED_FIELDS for line in lines)
    assert all(line["request_id"] == LAMBDA_REQUEST_ID for line in lines)
    assert not any(value in stream.getvalue() for value in injected)


@pytest.mark.req("fase-1a:2.4", "fase-1a:NFR-5")
@settings(deadline=None)
@given(
    claim_subject=VALUES,
    claim_client=VALUES,
    authorization=VALUES,
    client_request_id=VALUES,
)
def test_logs_ruta_autenticada_nunca_contienen_claims_ni_credenciales(
    claim_subject: str,
    claim_client: str,
    authorization: str,
    client_request_id: str,
) -> None:
    headers = {
        "authorization": f"Bearer {authorization}",
        "x-request-id": client_request_id,
        "x-amzn-request-context": json.dumps(
            {
                "requestId": LAMBDA_REQUEST_ID,
                "authorizer": {
                    "jwt": {
                        "claims": {
                            "sub": claim_subject,
                            "client_id": claim_client,
                            "token_use": "access",
                        }
                    }
                },
            }
        ),
    }
    injected = [claim_subject, claim_client, authorization, client_request_id]

    with captured_logs() as stream:
        response = PROD_CLIENT.get("/api/v1/me", headers=headers)

    assert response.status_code == 200
    [line] = [json.loads(line_text) for line_text in stream.getvalue().splitlines()]
    assert set(line) <= ALLOWED_FIELDS
    assert line["request_id"] == LAMBDA_REQUEST_ID
    assert line["route"] == "/api/v1/me"
    assert not any(value in stream.getvalue() for value in injected)
