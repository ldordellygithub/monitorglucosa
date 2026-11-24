"""Servidor Starlette con clave RSA efímera que emite access tokens de prueba.

Expone:
- `GET /health` -> 200 `{"status": "ok"}`
- `GET /.well-known/jwks.json` -> clave pública RSA en formato JWKS
- `POST /token` -> access token RS256 con forma de claims de Cognito
"""

from __future__ import annotations

import json
import os
import secrets
import time
from typing import Any

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

DEFAULT_ISSUER = "http://jwt-issuer:9000"
DEFAULT_EXPIRES_IN_S = 3600


def _generate_signing_material() -> tuple[rsa.RSAPrivateKey, dict[str, Any], str]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    kid = f"local-{secrets.token_hex(6)}"
    jwk_json = RSAAlgorithm.to_jwk(private_key.public_key())
    jwk: dict[str, Any] = json.loads(jwk_json)
    jwk["kid"] = kid
    jwk["use"] = "sig"
    jwk["alg"] = "RS256"
    return private_key, jwk, kid


def create_issuer_app(issuer: str | None = None) -> Starlette:
    """Crea la aplicación Starlette del emisor JWT local con clave RSA efímera."""
    issuer_url = issuer or os.environ.get("JWT_ISSUER_URL", DEFAULT_ISSUER)
    private_key, public_jwk, kid = _generate_signing_material()

    async def health(_request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    async def jwks(_request: Request) -> JSONResponse:
        return JSONResponse({"keys": [public_jwk]})

    async def issue_token(request: Request) -> JSONResponse:
        try:
            body: Any = await request.json()
        except Exception:
            return JSONResponse({"error": "Cuerpo JSON inválido"}, status_code=400)

        if not isinstance(body, dict):
            return JSONResponse(
                {"error": "Se esperaba un objeto JSON"}, status_code=400
            )

        sub = body.get("sub")
        client_id = body.get("client_id")
        if not isinstance(sub, str) or not sub.strip():
            return JSONResponse(
                {"error": "`sub` es obligatorio y debe ser texto no vacío"},
                status_code=400,
            )
        if not isinstance(client_id, str) or not client_id.strip():
            return JSONResponse(
                {"error": "`client_id` es obligatorio y debe ser texto no vacío"},
                status_code=400,
            )

        raw_ttl = body.get("expires_in", DEFAULT_EXPIRES_IN_S)
        if isinstance(raw_ttl, bool) or not isinstance(raw_ttl, int) or raw_ttl <= 0:
            return JSONResponse(
                {"error": "`expires_in` debe ser un entero positivo"},
                status_code=400,
            )

        use_claim = body.get("token_use", "access")
        scope = body.get("scope", "openid")
        if not isinstance(use_claim, str) or not isinstance(scope, str):
            return JSONResponse(
                {"error": "`token_use` y `scope` deben ser texto"},
                status_code=400,
            )

        now = int(time.time())
        claims = {
            "iss": issuer_url,
            "sub": sub.strip(),
            "client_id": client_id.strip(),
            "token_use": use_claim,
            "scope": scope,
            "iat": now,
            "exp": now + raw_ttl,
        }
        encoded = jwt.encode(
            claims,
            private_key,
            algorithm="RS256",
            headers={"kid": kid},
        )
        return JSONResponse(
            {
                "access_token": encoded,
                "token_type": "Bearer",
                "expires_in": raw_ttl,
            }
        )

    routes = [
        Route("/health", health, methods=["GET"]),
        Route("/.well-known/jwks.json", jwks, methods=["GET"]),
        Route("/token", issue_token, methods=["POST"]),
    ]
    return Starlette(routes=routes)
