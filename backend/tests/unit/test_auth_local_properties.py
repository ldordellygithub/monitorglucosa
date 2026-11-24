"""Property 3: un token alterado nunca autentica en local."""

import time
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from hypothesis import given, settings
from hypothesis import strategies as st

from src.application.identity import UnauthenticatedError
from src.infrastructure.auth import LocalJwksAuthenticator
from tests.unit.test_auth import DummyJWKClient

VALID_ISSUER = "http://jwt-issuer:9000"
VALID_CLIENT_IDS = ["web", "collector"]

PRIVATE_KEY = rsa.generate_private_key(65537, 2048)
PUBLIC_KEY = PRIVATE_KEY.public_key()
OTHER_PRIVATE_KEY = rsa.generate_private_key(65537, 2048)

AUTHENTICATOR = LocalJwksAuthenticator(
    issuer=VALID_ISSUER,
    jwks_url="http://jwt-issuer:9000/.well-known/jwks.json",
    client_ids=VALID_CLIENT_IDS,
    jwk_client=DummyJWKClient(PUBLIC_KEY),  # type: ignore[arg-type]
)


def encode_token(
    payload: dict[str, Any],
    key: Any = PRIVATE_KEY,
    algorithm: str = "RS256",
) -> str:
    headers = {"kid": "k1"} if algorithm.startswith("RS") else {}
    return jwt.encode(payload, key, algorithm=algorithm, headers=headers)


@pytest.mark.req("fase-1a:3.3")
@settings(deadline=None)
@given(
    sub=st.text(min_size=1, max_size=30).filter(lambda s: bool(s.strip())),
    alteration=st.sampled_from(
        ["firma", "iss", "client_id", "exp", "token_use", "alg"]
    ),
    bad_iss=st.text(min_size=1, max_size=30).filter(lambda s: s != VALID_ISSUER),
    bad_client=st.text(min_size=1, max_size=30).filter(
        lambda s: s not in VALID_CLIENT_IDS
    ),
    bad_use=st.text(min_size=1, max_size=30).filter(lambda s: s != "access"),
    expired_delta=st.integers(min_value=1, max_value=86400),
    bad_alg=st.sampled_from(["HS256"]),
)
def test_token_con_un_elemento_alterado_siempre_es_rechazado(
    sub: str,
    alteration: str,
    bad_iss: str,
    bad_client: str,
    bad_use: str,
    expired_delta: int,
    bad_alg: str,
) -> None:
    now = int(time.time())
    payload: dict[str, Any] = {
        "sub": sub,
        "iss": VALID_ISSUER,
        "client_id": "web",
        "token_use": "access",
        "iat": now,
        "exp": now + 3600,
    }
    signing_key = PRIVATE_KEY
    alg = "RS256"

    if alteration == "firma":
        signing_key = OTHER_PRIVATE_KEY
    elif alteration == "iss":
        payload["iss"] = bad_iss
    elif alteration == "client_id":
        payload["client_id"] = bad_client
    elif alteration == "exp":
        payload["exp"] = now - expired_delta
    elif alteration == "token_use":
        payload["token_use"] = bad_use
    elif alteration == "alg":
        alg = bad_alg
        signing_key = "clave-secreta-simetrica-de-mas-de-32-bytes"  # type: ignore[assignment]

    token = encode_token(payload, key=signing_key, algorithm=alg)

    with pytest.raises(UnauthenticatedError):
        AUTHENTICATOR.authenticate({"Authorization": f"Bearer {token}"})
