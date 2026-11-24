"""Pruebas unitarias de autenticación: puerto, adaptadores y GET /api/v1/me."""

import json
import logging
import time
from typing import Any
from unittest import mock

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import APIRouter
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict, ValidationError

from src.application.identity import Identity, UnauthenticatedError
from src.infrastructure.auth import (
    ApiGatewayClaimsAuthenticator,
    LocalJwksAuthenticator,
)
from src.main import create_app
from tests.unit.probe_app import captured_logs
from tests.unit.settings_env import build_settings, local_env, prod_env


class DummySigningKey:
    def __init__(self, key: Any) -> None:
        self.key = key


class DummyJWKClient:
    def __init__(self, public_key: Any) -> None:
        self.public_key = public_key

    def get_signing_key_from_jwt(self, token: str) -> DummySigningKey:
        return DummySigningKey(self.public_key)


class FailingJWKClient:
    def get_signing_key_from_jwt(self, token: str) -> DummySigningKey:
        raise RuntimeError("No se puede conectar con JWKS")


@pytest.fixture(scope="module")
def rsa_keys() -> tuple[rsa.RSAPrivateKey, Any]:
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    public_key = private_key.public_key()
    return private_key, public_key


def make_token(
    private_key: rsa.RSAPrivateKey,
    *,
    sub: str = "8f3c2a1e-5b7d-4c9a-9e2f-1a2b3c4d5e6f",
    iss: str = "http://jwt-issuer:9000",
    client_id: str = "web",
    use_claim: str = "access",
    expires_in: int = 3600,
    alg: str = "RS256",
) -> str:
    now = int(time.time())
    payload = {
        "sub": sub,
        "iss": iss,
        "client_id": client_id,
        "token_use": use_claim,
        "iat": now,
        "exp": now + expires_in,
    }
    return jwt.encode(payload, private_key, algorithm=alg, headers={"kid": "k1"})


# --- ApiGatewayClaimsAuthenticator ---


@pytest.mark.req("fase-1a:3.1", "fase-1a:3.2")
def test_prod_autenticador_extrae_sub_con_contexto_valido() -> None:
    auth = ApiGatewayClaimsAuthenticator()
    context = {
        "requestId": "req-123",
        "authorizer": {
            "jwt": {
                "claims": {
                    "sub": "user-uuid-1",
                    "token_use": "access",
                    "client_id": "web",
                }
            }
        },
    }
    identity = auth.authenticate({"x-amzn-request-context": json.dumps(context)})
    assert identity == Identity(subject="user-uuid-1")


@pytest.mark.req("fase-1a:3.1")
def test_prod_autenticador_admite_request_context_envolvente() -> None:
    auth = ApiGatewayClaimsAuthenticator()
    context = {
        "requestContext": {
            "authorizer": {
                "jwt": {
                    "claims": {
                        "sub": "user-uuid-2",
                        "token_use": "access",
                    }
                }
            }
        }
    }
    identity = auth.authenticate({"x-amzn-request-context": json.dumps(context)})
    assert identity.subject == "user-uuid-2"


@pytest.mark.req("fase-1a:3.2")
def test_prod_autenticador_rechaza_claves_intermedias_ausentes() -> None:
    auth = ApiGatewayClaimsAuthenticator()
    # Sin authorizer
    with pytest.raises(UnauthenticatedError):
        auth.authenticate({"x-amzn-request-context": json.dumps({})})

    # Sin jwt
    with pytest.raises(UnauthenticatedError):
        auth.authenticate({"x-amzn-request-context": json.dumps({"authorizer": {}})})

    # Sin claims
    with pytest.raises(UnauthenticatedError):
        auth.authenticate(
            {"x-amzn-request-context": json.dumps({"authorizer": {"jwt": {}}})}
        )


@pytest.mark.req("fase-1a:3.2")
def test_prod_autenticador_rechaza_cabecera_ausente_o_vacia() -> None:
    auth = ApiGatewayClaimsAuthenticator()
    with pytest.raises(UnauthenticatedError):
        auth.authenticate({})

    with pytest.raises(UnauthenticatedError):
        auth.authenticate({"x-amzn-request-context": ""})


@pytest.mark.req("fase-1a:3.2")
def test_prod_autenticador_rechaza_json_invalido_o_no_objeto() -> None:
    auth = ApiGatewayClaimsAuthenticator()
    with pytest.raises(UnauthenticatedError):
        auth.authenticate({"x-amzn-request-context": "no-es-json"})

    with pytest.raises(UnauthenticatedError):
        auth.authenticate({"x-amzn-request-context": '["array"]'})


@pytest.mark.req("fase-1a:3.2")
def test_prod_autenticador_rechaza_token_use_distinto_de_access() -> None:
    auth = ApiGatewayClaimsAuthenticator()
    for bad_use in ("id", "refresh", "", None):
        context = {
            "authorizer": {
                "jwt": {
                    "claims": {
                        "sub": "user-uuid",
                        "token_use": bad_use,
                    }
                }
            }
        }
        with pytest.raises(UnauthenticatedError):
            auth.authenticate({"x-amzn-request-context": json.dumps(context)})


@pytest.mark.req("fase-1a:3.2")
def test_prod_autenticador_rechaza_sub_vacio_o_ausente() -> None:
    auth = ApiGatewayClaimsAuthenticator()
    for bad_sub in ("", "   ", None):
        context = {
            "authorizer": {
                "jwt": {
                    "claims": {
                        "sub": bad_sub,
                        "token_use": "access",
                    }
                }
            }
        }
        with pytest.raises(UnauthenticatedError):
            auth.authenticate({"x-amzn-request-context": json.dumps(context)})


# --- LocalJwksAuthenticator ---


@pytest.mark.req("fase-1a:3.3")
def test_local_autenticador_acepta_token_valido(
    rsa_keys: tuple[rsa.RSAPrivateKey, Any],
) -> None:
    priv, pub = rsa_keys
    auth = LocalJwksAuthenticator(
        issuer="http://jwt-issuer:9000",
        jwks_url="http://jwt-issuer:9000/.well-known/jwks.json",
        client_ids=["web", "collector"],
        jwk_client=DummyJWKClient(pub),  # type: ignore[arg-type]
    )
    token = make_token(priv, sub="local-user-1")
    identity = auth.authenticate({"Authorization": f"Bearer {token}"})
    assert identity == Identity(subject="local-user-1")


@pytest.mark.req("fase-1a:3.3")
def test_local_autenticador_acepta_aud_como_lista(
    rsa_keys: tuple[rsa.RSAPrivateKey, Any],
) -> None:
    priv, pub = rsa_keys
    auth = LocalJwksAuthenticator(
        issuer="http://jwt-issuer:9000",
        jwks_url="http://jwt-issuer:9000/.well-known/jwks.json",
        client_ids=["web", "collector"],
        jwk_client=DummyJWKClient(pub),  # type: ignore[arg-type]
    )
    # Token sin client_id pero con aud = ["app", "web"]
    now = int(time.time())
    payload = {
        "sub": "user-list-aud",
        "iss": "http://jwt-issuer:9000",
        "aud": ["other-app", "web"],
        "token_use": "access",
        "iat": now,
        "exp": now + 3600,
    }
    token = jwt.encode(payload, priv, algorithm="RS256", headers={"kid": "k1"})
    identity = auth.authenticate({"Authorization": f"Bearer {token}"})
    assert identity.subject == "user-list-aud"


@pytest.mark.req("fase-1a:3.3")
def test_local_autenticador_rechaza_cabecera_ausente_o_no_bearer(
    rsa_keys: tuple[rsa.RSAPrivateKey, Any],
) -> None:
    _, pub = rsa_keys
    auth = LocalJwksAuthenticator(
        issuer="http://jwt-issuer:9000",
        jwks_url="http://jwt-issuer:9000/.well-known/jwks.json",
        client_ids=["web"],
        jwk_client=DummyJWKClient(pub),  # type: ignore[arg-type]
    )
    with pytest.raises(UnauthenticatedError):
        auth.authenticate({})

    with pytest.raises(UnauthenticatedError):
        auth.authenticate({"Authorization": "Basic 1234"})

    with pytest.raises(UnauthenticatedError):
        auth.authenticate({"Authorization": "Bearer "})


@pytest.mark.req("fase-1a:3.3")
def test_local_autenticador_rechaza_token_expirado(
    rsa_keys: tuple[rsa.RSAPrivateKey, Any],
) -> None:
    priv, pub = rsa_keys
    auth = LocalJwksAuthenticator(
        issuer="http://jwt-issuer:9000",
        jwks_url="http://jwt-issuer:9000/.well-known/jwks.json",
        client_ids=["web"],
        jwk_client=DummyJWKClient(pub),  # type: ignore[arg-type]
    )
    expired_token = make_token(priv, expires_in=-10)
    with pytest.raises(UnauthenticatedError):
        auth.authenticate({"Authorization": f"Bearer {expired_token}"})


@pytest.mark.req("fase-1a:3.3")
def test_local_autenticador_rechaza_firma_invalida(
    rsa_keys: tuple[rsa.RSAPrivateKey, Any],
) -> None:
    other_priv = rsa.generate_private_key(65537, 2048)
    _, pub = rsa_keys
    auth = LocalJwksAuthenticator(
        issuer="http://jwt-issuer:9000",
        jwks_url="http://jwt-issuer:9000/.well-known/jwks.json",
        client_ids=["web"],
        jwk_client=DummyJWKClient(pub),  # type: ignore[arg-type]
    )
    token_wrong_key = make_token(other_priv)
    with pytest.raises(UnauthenticatedError):
        auth.authenticate({"Authorization": f"Bearer {token_wrong_key}"})


@pytest.mark.req("fase-1a:3.3")
def test_local_autenticador_rechaza_emisor_o_cliente_ajeno(
    rsa_keys: tuple[rsa.RSAPrivateKey, Any],
) -> None:
    priv, pub = rsa_keys
    auth = LocalJwksAuthenticator(
        issuer="http://jwt-issuer:9000",
        jwks_url="http://jwt-issuer:9000/.well-known/jwks.json",
        client_ids=["web"],
        jwk_client=DummyJWKClient(pub),  # type: ignore[arg-type]
    )
    token_wrong_iss = make_token(priv, iss="http://evil-issuer:9000")
    with pytest.raises(UnauthenticatedError):
        auth.authenticate({"Authorization": f"Bearer {token_wrong_iss}"})

    token_wrong_client = make_token(priv, client_id="unauthorized-client")
    with pytest.raises(UnauthenticatedError):
        auth.authenticate({"Authorization": f"Bearer {token_wrong_client}"})


@pytest.mark.req("fase-1a:3.3")
def test_local_autenticador_rechaza_token_use_no_access(
    rsa_keys: tuple[rsa.RSAPrivateKey, Any],
) -> None:
    priv, pub = rsa_keys
    auth = LocalJwksAuthenticator(
        issuer="http://jwt-issuer:9000",
        jwks_url="http://jwt-issuer:9000/.well-known/jwks.json",
        client_ids=["web"],
        jwk_client=DummyJWKClient(pub),  # type: ignore[arg-type]
    )
    id_token = make_token(priv, use_claim="id")
    with pytest.raises(UnauthenticatedError):
        auth.authenticate({"Authorization": f"Bearer {id_token}"})


@pytest.mark.req("fase-1a:3.3")
def test_local_autenticador_falla_si_jwks_inaccesible(
    rsa_keys: tuple[rsa.RSAPrivateKey, Any],
) -> None:
    priv, _ = rsa_keys
    auth = LocalJwksAuthenticator(
        issuer="http://jwt-issuer:9000",
        jwks_url="http://jwt-issuer:9000/.well-known/jwks.json",
        client_ids=["web"],
        jwk_client=FailingJWKClient(),  # type: ignore[arg-type]
    )
    token = make_token(priv)
    with pytest.raises(UnauthenticatedError):
        auth.authenticate({"Authorization": f"Bearer {token}"})


# --- create_app y selección por ENVIRONMENT ---


@pytest.mark.req("fase-1a:3.4")
def test_create_app_en_prod_nunca_construye_local_jwks_authenticator() -> None:
    settings = build_settings(prod_env())
    with mock.patch("src.main.LocalJwksAuthenticator") as mock_local_auth:
        app = create_app(settings)
        mock_local_auth.assert_not_called()
        assert isinstance(app.state.authenticator, ApiGatewayClaimsAuthenticator)


@pytest.mark.req("fase-1a:3.4")
def test_create_app_en_local_construye_local_jwks_authenticator() -> None:
    settings = build_settings(local_env())
    app = create_app(settings)
    assert isinstance(app.state.authenticator, LocalJwksAuthenticator)


@pytest.mark.req("fase-1a:1.4")
def test_create_app_sin_settings_falla_si_falta_configuracion() -> None:
    with mock.patch.dict("os.environ", {}, clear=True), pytest.raises(ValidationError):
        create_app()


# --- GET /api/v1/me y End-to-End ---


@pytest.mark.req("fase-1a:3.1", "fase-1a:3.5")
def test_me_en_prod_devuelve_sub_con_contexto_valido() -> None:
    settings = build_settings(prod_env())
    app = create_app(settings)
    client = TestClient(app)

    headers = {
        "x-amzn-request-context": json.dumps(
            {
                "requestId": "lambda-req-1",
                "authorizer": {
                    "jwt": {
                        "claims": {
                            "sub": "8f3c2a1e-5b7d-4c9a-9e2f-1a2b3c4d5e6f",
                            "token_use": "access",
                        }
                    }
                },
            }
        )
    }
    response = client.get("/api/v1/me", headers=headers)
    assert response.status_code == 200
    assert response.json() == {"sub": "8f3c2a1e-5b7d-4c9a-9e2f-1a2b3c4d5e6f"}
    assert response.headers["x-request-id"] == "lambda-req-1"


@pytest.mark.req("fase-1a:3.2")
def test_me_en_prod_responde_401_sin_contexto() -> None:
    settings = build_settings(prod_env())
    app = create_app(settings)
    client = TestClient(app)

    response = client.get("/api/v1/me")
    assert response.status_code == 401
    assert response.json() == {
        "code": "UNAUTHENTICATED",
        "message": "Se requiere autenticación.",
        "details": [],
    }
    assert "x-request-id" in response.headers


@pytest.mark.req("fase-1a:3.3", "fase-1a:3.5")
def test_me_en_local_devuelve_sub_con_bearer_token(
    rsa_keys: tuple[rsa.RSAPrivateKey, Any],
) -> None:
    priv, pub = rsa_keys
    settings = build_settings(local_env())
    auth = LocalJwksAuthenticator(
        issuer=settings.local_jwt_issuer or "",
        jwks_url=str(settings.local_jwks_url or ""),
        client_ids=settings.local_jwt_client_ids or [],
        jwk_client=DummyJWKClient(pub),  # type: ignore[arg-type]
    )
    app = create_app(settings, authenticator=auth)
    client = TestClient(app)

    token = make_token(priv, sub="local-sub-99")
    response = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json() == {"sub": "local-sub-99"}


@pytest.mark.req("fase-1a:3.3")
def test_me_en_local_responde_401_con_token_invalido(
    rsa_keys: tuple[rsa.RSAPrivateKey, Any],
) -> None:
    _, pub = rsa_keys
    settings = build_settings(local_env())
    auth = LocalJwksAuthenticator(
        issuer=settings.local_jwt_issuer or "",
        jwks_url=str(settings.local_jwks_url or ""),
        client_ids=settings.local_jwt_client_ids or [],
        jwk_client=DummyJWKClient(pub),  # type: ignore[arg-type]
    )
    app = create_app(settings, authenticator=auth)
    client = TestClient(app)

    response = client.get(
        "/api/v1/me", headers={"Authorization": "Bearer token-invalido"}
    )
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHENTICATED"


# --- Pruebas de punta a punta de create_app: 404, 422 y logs ---


class StrictPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    count: int


@pytest.mark.req("fase-1a:2.3", "fase-1a:2.4")
def test_create_app_peticion_404_devuelve_cuerpo_uniforme_y_registra_log() -> None:
    settings = build_settings(prod_env())
    app = create_app(settings)
    client = TestClient(app)

    with captured_logs() as stream:
        response = client.get("/ruta/no/existente")

    assert response.status_code == 404
    assert response.json() == {
        "code": "NOT_FOUND",
        "message": "Recurso no encontrado.",
        "details": [],
    }
    assert "x-request-id" in response.headers

    lines = [json.loads(line) for line in stream.getvalue().splitlines()]
    assert len(lines) == 1
    assert lines[0]["status"] == 404
    assert lines[0]["route"] == "-"
    assert lines[0]["request_id"] == response.headers["x-request-id"]


@pytest.mark.req("fase-1a:2.3", "fase-1a:2.4")
def test_create_app_peticion_422_devuelve_cuerpo_uniforme_y_registra_log() -> None:
    settings = build_settings(prod_env())
    app = create_app(settings)

    # Añadimos un router temporal para probar validación
    test_router = APIRouter()

    @test_router.post("/test-validation")
    def post_strict(data: StrictPayload) -> dict[str, int]:
        return {"count": data.count}

    app.include_router(test_router)
    client = TestClient(app)

    with captured_logs() as stream:
        response = client.post("/test-validation", json={"count": "no-es-int"})

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert body["message"] == "La petición no es válida."
    assert body["details"] == [{"field": "body.count", "problem": "formato no válido"}]
    assert "x-request-id" in response.headers

    lines = [json.loads(line) for line in stream.getvalue().splitlines()]
    assert len(lines) == 1
    assert lines[0]["status"] == 422
    assert lines[0]["request_id"] == response.headers["x-request-id"]


@pytest.mark.req("fase-1a:2.3", "fase-1a:2.4")
def test_create_app_configura_uvicorn_error_con_json_formatter() -> None:
    settings = build_settings(prod_env())
    create_app(settings)
    uvicorn_logger = logging.getLogger("uvicorn.error")
    assert any(
        handler.formatter.__class__.__name__ == "JsonFormatter"
        for handler in uvicorn_logger.handlers
    )
