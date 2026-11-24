"""Property 2: la autenticación en `prod` falla cerrada."""

import json
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src.application.identity import Identity, UnauthenticatedError
from src.infrastructure.auth import ApiGatewayClaimsAuthenticator

AUTH = ApiGatewayClaimsAuthenticator()

JSON_PRIMITIVES = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(),
    st.floats(allow_nan=False, allow_infinity=False),
    st.text(),
    st.lists(st.text(), max_size=3),
)


@pytest.mark.req("fase-1a:3.1", "fase-1a:3.2")
@settings(deadline=None)
@given(headers=st.dictionaries(st.text(), st.text(), max_size=5))
def test_cabeceras_sin_contexto_siempre_fallan(
    headers: dict[str, str],
) -> None:
    # Aseguramos que ninguna clave sea x-amzn-request-context (case-insensitive)
    filtered = {
        k: v for k, v in headers.items() if k.lower() != "x-amzn-request-context"
    }
    with pytest.raises(UnauthenticatedError):
        AUTH.authenticate(filtered)


@pytest.mark.req("fase-1a:3.1", "fase-1a:3.2")
@settings(deadline=None)
@given(raw_text=st.text().filter(lambda t: not t.strip().startswith("{")))
def test_contexto_no_json_valido_falla(raw_text: str) -> None:
    with pytest.raises(UnauthenticatedError):
        AUTH.authenticate({"x-amzn-request-context": raw_text})


@pytest.mark.req("fase-1a:3.1", "fase-1a:3.2")
@settings(deadline=None)
@given(primitive=JSON_PRIMITIVES)
def test_contexto_json_que_no_es_objeto_falla(primitive: Any) -> None:
    if isinstance(primitive, dict):
        return
    with pytest.raises(UnauthenticatedError):
        AUTH.authenticate({"x-amzn-request-context": json.dumps(primitive)})


@pytest.mark.req("fase-1a:3.1", "fase-1a:3.2")
@settings(deadline=None)
@given(
    bad_sub=st.one_of(
        st.just(""),
        st.text(alphabet=" \t\n\r"),
        st.none(),
        st.integers(),
        st.booleans(),
    ),
    token_use=st.sampled_from(["access"]),
)
def test_contexto_con_sub_invalido_falla(bad_sub: Any, token_use: str) -> None:
    context = {
        "authorizer": {
            "jwt": {
                "claims": {
                    "sub": bad_sub,
                    "token_use": token_use,
                }
            }
        }
    }
    with pytest.raises(UnauthenticatedError):
        AUTH.authenticate({"x-amzn-request-context": json.dumps(context)})


@pytest.mark.req("fase-1a:3.1", "fase-1a:3.2")
@settings(deadline=None)
@given(
    sub=st.text(min_size=1).filter(lambda s: bool(s.strip())),
    bad_token_use=st.one_of(
        st.text().filter(lambda t: t != "access"),
        st.none(),
        st.integers(),
        st.booleans(),
    ),
)
def test_contexto_con_token_use_distinto_de_access_falla(
    sub: str, bad_token_use: Any
) -> None:
    context = {
        "authorizer": {
            "jwt": {
                "claims": {
                    "sub": sub,
                    "token_use": bad_token_use,
                }
            }
        }
    }
    with pytest.raises(UnauthenticatedError):
        AUTH.authenticate({"x-amzn-request-context": json.dumps(context)})


@pytest.mark.req("fase-1a:3.1", "fase-1a:3.2")
@settings(deadline=None)
@given(
    sub=st.text(min_size=1).filter(lambda s: bool(s.strip())),
    wrap_in_request_context=st.booleans(),
)
def test_contexto_valido_devuelve_identidad(
    sub: str, wrap_in_request_context: bool
) -> None:
    claims = {"sub": sub, "token_use": "access"}
    inner = {"authorizer": {"jwt": {"claims": claims}}}
    payload = {"requestContext": inner} if wrap_in_request_context else inner
    identity = AUTH.authenticate({"x-amzn-request-context": json.dumps(payload)})
    assert identity == Identity(subject=sub.strip())
