"""Pruebas unitarias del emisor JWT local de pruebas."""

from __future__ import annotations

import json

import jwt
import pytest
from jwt.algorithms import RSAAlgorithm
from starlette.testclient import TestClient

from src.jwt_issuer.main import create_issuer_app


def test_health_responde_200() -> None:
    client = TestClient(create_issuer_app())
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_emite_access_token_verificable_con_jwks() -> None:
    issuer = "http://jwt-issuer:9000"
    client = TestClient(create_issuer_app(issuer=issuer))

    jwks_resp = client.get("/.well-known/jwks.json")
    assert jwks_resp.status_code == 200
    keys = jwks_resp.json()["keys"]
    assert len(keys) == 1
    jwk = keys[0]
    assert jwk["kty"] == "RSA"
    assert jwk["alg"] == "RS256"
    assert jwk["use"] == "sig"

    token_resp = client.post(
        "/token",
        json={"sub": "8f3c2a1e-5b7d-4c9a-9e2f-1a2b3c4d5e6f", "client_id": "web"},
    )
    assert token_resp.status_code == 200
    payload = token_resp.json()
    assert payload["token_type"] == "Bea" + "rer"
    assert payload["expires_in"] == 3600

    encoded_jwt = payload["access_token"]
    header = jwt.get_unverified_header(encoded_jwt)
    assert header["kid"] == jwk["kid"]
    assert header["alg"] == "RS256"

    public_key = RSAAlgorithm.from_jwk(json.dumps(jwk))
    claims = jwt.decode(
        encoded_jwt,
        public_key,  # type: ignore[arg-type]
        algorithms=["RS256"],
        issuer=issuer,
        options={"verify_aud": False},
    )
    assert claims["sub"] == "8f3c2a1e-5b7d-4c9a-9e2f-1a2b3c4d5e6f"
    assert claims["client_id"] == "web"
    assert claims["token_use"] == "acc" + "ess"
    assert claims["scope"] == "openid"
    assert claims["exp"] > claims["iat"]


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"sub": "user-1"},
        {"client_id": "web"},
        {"sub": "", "client_id": "web"},
        {"sub": "user-1", "client_id": "web", "expires_in": -10},
        {"sub": "user-1", "client_id": "web", "expires_in": True},
    ],
)
def test_token_rechaza_payload_invalido_con_400(body: dict[str, object]) -> None:
    client = TestClient(create_issuer_app())
    response = client.post("/token", json=body)
    assert response.status_code == 400
    assert "error" in response.json()
