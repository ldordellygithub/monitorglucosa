"""Adaptadores de autenticación para producción y local."""

import json
import logging
from collections.abc import Mapping, Sequence

import jwt
from jwt import PyJWKClient, PyJWKClientError

from src.application.identity import Identity, UnauthenticatedError

logger = logging.getLogger("infrastructure.auth")


class ApiGatewayClaimsAuthenticator:
    """Autenticador de producción.

    Lee los claims del autorizador JWT de API Gateway que Lambda Web Adapter entrega en
    la cabecera `x-amzn-request-context`.
    """

    def authenticate(self, headers: Mapping[str, str]) -> Identity:
        raw_context: str | None = None
        for key, value in headers.items():
            if key.lower() == "x-amzn-request-context":
                raw_context = value
                break

        if not raw_context:
            raise UnauthenticatedError("Cabecera x-amzn-request-context ausente")

        try:
            data = json.loads(raw_context)
        except Exception as exc:
            raise UnauthenticatedError("Contexto no es JSON válido") from exc

        if not isinstance(data, dict):
            raise UnauthenticatedError("Contexto debe ser un objeto JSON")

        req_context = data.get("requestContext")
        context = req_context if isinstance(req_context, dict) else data

        authorizer = context.get("authorizer")
        if not isinstance(authorizer, dict):
            raise UnauthenticatedError("authorizer ausente en el contexto")

        jwt_data = authorizer.get("jwt")
        if not isinstance(jwt_data, dict):
            raise UnauthenticatedError("jwt ausente en authorizer")

        claims = jwt_data.get("claims")
        if not isinstance(claims, dict):
            raise UnauthenticatedError("claims ausente en jwt")

        claim_use = claims.get("token_use")
        if claim_use != "access":
            raise UnauthenticatedError(
                f"token_use debe ser 'access', recibido: {claim_use!r}"
            )

        sub = claims.get("sub")
        if not isinstance(sub, str) or not sub.strip():
            raise UnauthenticatedError("claim 'sub' ausente o vacío")

        return Identity(subject=sub.strip())


class LocalJwksAuthenticator:
    """Autenticador para entornos local y de pruebas.

    Valida firma RS256, emisor, client_id, expiración (sin margen) y token_use = access
    contra un endpoint JWKS.
    """

    def __init__(
        self,
        issuer: str,
        jwks_url: str,
        client_ids: Sequence[str],
        *,
        jwk_client: PyJWKClient | None = None,
    ) -> None:
        self._issuer = issuer
        self._client_ids = set(client_ids)
        self._jwk_client = jwk_client or PyJWKClient(
            uri=jwks_url, cache_keys=True, cache_jwk_set=True
        )

    def authenticate(self, headers: Mapping[str, str]) -> Identity:
        auth_header: str | None = None
        for key, value in headers.items():
            if key.lower() == "authorization":
                auth_header = value
                break

        if not auth_header:
            raise UnauthenticatedError("Cabecera Authorization ausente")

        parts = auth_header.split(maxsplit=1)
        if len(parts) != 2 or parts[0].lower() != "bearer":
            raise UnauthenticatedError(
                "Esquema de autorización inválido; se espera Bearer"
            )

        token = parts[1].strip()
        if not token:
            raise UnauthenticatedError("Token Bearer vacío")

        try:
            signing_key = self._jwk_client.get_signing_key_from_jwt(token)
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                issuer=self._issuer,
                leeway=0,
                options={
                    "verify_signature": True,
                    "verify_exp": True,
                    "verify_iss": True,
                    "verify_aud": False,
                    "require": ["exp", "iss", "sub", "token_use"],
                },
            )
        except Exception as exc:
            if isinstance(exc, (PyJWKClientError, Exception)):
                logger.error(
                    "error validando token o conectando con JWKS", exc_info=exc
                )
            raise UnauthenticatedError("Token inválido o expirado") from exc

        token_client = payload.get("client_id")
        if token_client is None:
            token_client = payload.get("aud")

        if token_client not in self._client_ids:
            raise UnauthenticatedError(f"client_id {token_client!r} no autorizado")

        claim_use = payload.get("token_use")
        if claim_use != "access":
            raise UnauthenticatedError(
                f"token_use debe ser 'access', recibido: {claim_use!r}"
            )

        sub = payload.get("sub")
        if not isinstance(sub, str) or not sub.strip():
            raise UnauthenticatedError("claim 'sub' ausente o vacío")

        return Identity(subject=sub.strip())
