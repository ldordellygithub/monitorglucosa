"""Errores uniformes: cuerpo, códigos, mensajes y traducción de problemas."""

from typing import Any

import pytest

from src.api.errors import field_of, problem_of
from tests.unit.probe_app import probe_client

CLIENT = probe_client()


def error_body(code: str, message: str, *details: tuple[str, str]) -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "details": [{"field": field, "problem": problem} for field, problem in details],
    }


def validation(*details: tuple[str, str]) -> dict[str, Any]:
    return error_body("VALIDATION_ERROR", "La petición no es válida.", *details)


@pytest.mark.req("fase-1a:2.3")
@pytest.mark.parametrize(
    ("method", "url", "kwargs", "expected"),
    [
        ("GET", "/items/abc", {}, validation(("path.item_id", "formato no válido"))),
        (
            "GET",
            "/items/1",
            {"params": {"limit": "0"}},
            validation(("query.limit", "fuera de rango")),
        ),
        (
            "GET",
            "/items/1",
            {"params": {"limit": "101"}},
            validation(("query.limit", "fuera de rango")),
        ),
        (
            "POST",
            "/items",
            {"json": {}},
            validation(("body.count", "obligatorio"), ("body.name", "obligatorio")),
        ),
        (
            "POST",
            "/items",
            {"json": {"count": "x", "name": "ab"}},
            validation(("body.count", "formato no válido")),
        ),
        (
            "POST",
            "/items",
            {"json": {"count": [], "name": "ab"}},
            validation(("body.count", "tipo no válido")),
        ),
        (
            "POST",
            "/items",
            {"json": {"count": 1, "name": "abcd"}},
            validation(("body.name", "longitud no válida")),
        ),
        (
            "POST",
            "/items",
            {"json": {"count": 1, "name": "ab", "otro": 1}},
            validation(("body", "valor no válido")),
        ),
        (
            "POST",
            "/items",
            {"content": "{no es json", "headers": {"content-type": "application/json"}},
            validation(("body", "valor no válido")),
        ),
    ],
    ids=[
        "path-no-entero",
        "query-bajo-el-minimo",
        "query-sobre-el-maximo",
        "body-sin-campos",
        "body-entero-con-texto",
        "body-entero-con-lista",
        "body-texto-demasiado-largo",
        "body-campo-no-permitido",
        "body-json-roto",
    ],
)
def test_validacion_invalida_responde_422_con_campo_y_problema(
    method: str, url: str, kwargs: dict[str, Any], expected: dict[str, Any]
) -> None:
    response = CLIENT.request(method, url, **kwargs)

    assert response.status_code == 422
    assert response.json() == expected


@pytest.mark.req("fase-1a:2.3")
def test_no_autenticado_responde_401_con_el_cuerpo_uniforme() -> None:
    response = CLIENT.get("/unauthenticated")

    assert response.status_code == 401
    assert response.json() == error_body(
        "UNAUTHENTICATED", "Se requiere autenticación."
    )


@pytest.mark.req("fase-1a:2.3")
def test_base_de_datos_no_disponible_responde_503_con_retry_after() -> None:
    response = CLIENT.get("/database")

    assert response.status_code == 503
    assert response.headers["retry-after"] == "5"
    assert response.json() == error_body(
        "DATABASE_UNAVAILABLE",
        "La base de datos se está despertando. Reintenta en unos segundos.",
    )


@pytest.mark.req("fase-1a:2.3")
def test_ruta_inexistente_responde_404_sin_repetir_la_ruta() -> None:
    response = CLIENT.get("/ruta-que-no-existe-secreta")

    assert response.status_code == 404
    assert response.json() == error_body("NOT_FOUND", "Recurso no encontrado.")


@pytest.mark.req("fase-1a:2.3")
def test_metodo_no_permitido_responde_405_y_conserva_la_cabecera_allow() -> None:
    response = CLIENT.put("/items/1")

    assert response.status_code == 405
    assert "GET" in response.headers["allow"]
    assert response.json() == error_body("METHOD_NOT_ALLOWED", "Método no permitido.")


@pytest.mark.req("fase-1a:2.3")
def test_excepcion_no_controlada_responde_500_sin_su_mensaje() -> None:
    response = CLIENT.get("/boom", params={"q": "dato-privado-123"})

    assert response.status_code == 500
    assert response.json() == error_body("INTERNAL_ERROR", "Error interno.")
    assert "dato-privado-123" not in response.text


@pytest.mark.req("fase-1a:2.3")
@pytest.mark.parametrize(
    ("error_type", "problem"),
    [
        ("missing", "obligatorio"),
        ("int_type", "tipo no válido"),
        ("string_type", "tipo no válido"),
        ("string_too_short", "longitud no válida"),
        ("string_too_long", "longitud no válida"),
        ("too_short", "longitud no válida"),
        ("too_long", "longitud no válida"),
        ("greater_than", "fuera de rango"),
        ("greater_than_equal", "fuera de rango"),
        ("less_than", "fuera de rango"),
        ("less_than_equal", "fuera de rango"),
        ("int_parsing", "formato no válido"),
        ("datetime_parsing", "formato no válido"),
        ("json_invalid", "valor no válido"),
        ("extra_forbidden", "valor no válido"),
        ("literal_error", "valor no válido"),
    ],
)
def test_problem_of_traduce_el_tipo_de_error_de_pydantic(
    error_type: str, problem: str
) -> None:
    assert problem_of(error_type) == problem


@pytest.mark.req("fase-1a:2.3")
@pytest.mark.parametrize(
    ("error", "field"),
    [
        ({"type": "missing", "loc": ("query", "limit")}, "query.limit"),
        ({"type": "missing", "loc": ("body", "items", 3, "value")}, "body.items.value"),
        ({"type": "extra_forbidden", "loc": ("body", "campo-ajeno")}, "body"),
    ],
    ids=["campo", "indice-omitido", "campo-no-permitido-sin-su-nombre"],
)
def test_field_of_ubica_el_error_sin_indices_ni_nombres_del_cliente(
    error: dict[str, Any], field: str
) -> None:
    assert field_of(error) == field
