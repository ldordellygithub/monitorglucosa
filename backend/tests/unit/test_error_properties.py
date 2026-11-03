"""Property 1: los errores no repiten lo recibido."""

import string
from collections.abc import Callable
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from tests.unit.probe_app import probe_client

CLIENT = probe_client()

# Un valor inválido: texto no numérico (para los enteros) y de más de 3 caracteres
# (para `name`). El prefijo `valor~` no aparece en ningún mensaje de error, así que si
# aparece en la respuesta es que la API repitió lo recibido.
INVALID_VALUES = st.text(
    alphabet=string.ascii_letters + string.digits + "-._",
    min_size=4,
    max_size=30,
).map(lambda text: f"valor~{text}")

type RequestFactory = Callable[[str], tuple[str, str, dict[str, Any]]]

REQUESTS: dict[str, RequestFactory] = {
    "path": lambda v: ("GET", f"/items/{v}", {}),
    "query": lambda v: ("GET", "/items/1", {"params": {"limit": v}}),
    "body-entero": lambda v: ("POST", "/items", {"json": {"count": v, "name": "ab"}}),
    "body-texto-largo": lambda v: ("POST", "/items", {"json": {"count": 1, "name": v}}),
    "body-campo-no-permitido": lambda v: (
        "POST",
        "/items",
        {"json": {"count": 1, "name": "ab", v: 1}},
    ),
    "ruta-inexistente": lambda v: ("GET", f"/{v}/algo", {}),
    "metodo-no-permitido": lambda v: ("PUT", f"/items/{v}", {}),
}


@pytest.mark.req("fase-1a:2.3")
@settings(deadline=None)
@given(value=INVALID_VALUES, where=st.sampled_from(sorted(REQUESTS)))
def test_error_nunca_repite_el_valor_recibido_y_conserva_el_cuerpo_uniforme(
    value: str, where: str
) -> None:
    method, url, kwargs = REQUESTS[where](value)

    response = CLIENT.request(method, url, **kwargs)

    assert response.status_code in {404, 405, 422}
    assert set(response.json()) == {"code", "message", "details"}
    assert value not in response.text
