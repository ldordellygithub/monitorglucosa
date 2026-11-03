"""Log de acceso, identificador de correlación y formateador JSON."""

import json
import logging
import re
import uuid
from typing import Any

import pytest

from src.infrastructure.observability import LOG_FIELDS, JsonFormatter
from tests.unit.probe_app import captured_logs, probe_client

CLIENT = probe_client()

ACCESS_FIELDS = {
    "timestamp",
    "level",
    "logger",
    "request_id",
    "method",
    "route",
    "status",
    "duration_ms",
}
TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z")


def log_lines(stream: Any) -> list[dict[str, Any]]:
    return [json.loads(line) for line in stream.getvalue().splitlines()]


def context_header(request_id: object) -> dict[str, str]:
    return {"x-amzn-request-context": json.dumps({"requestId": request_id})}


@pytest.mark.req("fase-1a:2.4")
def test_peticion_correcta_escribe_una_linea_con_los_campos_de_la_lista_blanca() -> (
    None
):
    with captured_logs() as stream:
        response = CLIENT.get("/items/42")

    [line] = log_lines(stream)
    assert response.status_code == 200
    assert set(line) == ACCESS_FIELDS
    assert line["level"] == "INFO"
    assert line["logger"] == "api.access"
    assert line["method"] == "GET"
    assert line["status"] == 200
    assert isinstance(line["duration_ms"], int)
    assert line["duration_ms"] >= 0
    assert TIMESTAMP.fullmatch(line["timestamp"])
    assert line["request_id"] == response.headers["x-request-id"]


@pytest.mark.req("fase-1a:2.4")
def test_log_de_acceso_usa_la_ruta_plantilla_y_no_la_url_real() -> None:
    with captured_logs() as stream:
        CLIENT.get("/items/4242", params={"limit": "7", "clave": "privada"})

    [line] = log_lines(stream)
    assert line["route"] == "/items/{item_id}"
    assert "4242" not in stream.getvalue()
    assert "privada" not in stream.getvalue()


@pytest.mark.req("fase-1a:2.4")
def test_log_de_ruta_inexistente_no_registra_la_url_real() -> None:
    with captured_logs() as stream:
        response = CLIENT.get("/ruta-secreta/123")

    [line] = log_lines(stream)
    assert response.status_code == 404
    assert line["route"] == "-"
    assert line["status"] == 404
    assert "secreta" not in stream.getvalue()


@pytest.mark.req("fase-1a:2.4")
def test_log_de_error_de_validacion_registra_el_estado_422() -> None:
    with captured_logs() as stream:
        CLIENT.post("/items", json={"count": "dato-privado", "name": "ab"})

    [line] = log_lines(stream)
    assert line["status"] == 422
    assert "dato-privado" not in stream.getvalue()


@pytest.mark.req("fase-1a:2.4")
def test_toda_respuesta_lleva_x_request_id_distinto_en_cada_peticion() -> None:
    urls = ["/items/1", "/items/x", "/ruta/inexistente", "/unauthenticated", "/boom"]

    ids = [CLIENT.get(url).headers["x-request-id"] for url in urls]

    assert all(uuid.UUID(request_id).version == 4 for request_id in ids)
    assert len(set(ids)) == len(urls)


@pytest.mark.req("fase-1a:2.4")
def test_x_request_id_enviado_por_el_cliente_se_ignora() -> None:
    sent = "mi-id-de-cliente-123"

    with captured_logs() as stream:
        response = CLIENT.get("/items/1", headers={"x-request-id": sent})

    assert response.headers["x-request-id"] != sent
    assert sent not in stream.getvalue()


@pytest.mark.req("fase-1a:2.4")
def test_request_id_sale_del_contexto_de_lambda_web_adapter() -> None:
    with captured_logs() as stream:
        response = CLIENT.get("/items/1", headers=context_header("Jw0yzgtkNjMEPNA="))

    [line] = log_lines(stream)
    assert response.headers["x-request-id"] == "Jw0yzgtkNjMEPNA="
    assert line["request_id"] == "Jw0yzgtkNjMEPNA="


@pytest.mark.req("fase-1a:2.4")
@pytest.mark.parametrize(
    "header",
    [
        context_header("con/barra"),
        context_header("x" * 129),
        context_header(""),
        context_header(12345),
        context_header(None),
        {"x-amzn-request-context": "no es json"},
        {"x-amzn-request-context": '["requestId"]'},
        {"x-amzn-request-context": "{}"},
    ],
    ids=[
        "caracter-no-permitido",
        "demasiado-largo",
        "vacio",
        "numero",
        "nulo",
        "json-roto",
        "json-sin-objeto",
        "sin-request-id",
    ],
)
def test_request_id_invalido_en_el_contexto_se_sustituye_por_un_uuid(
    header: dict[str, str],
) -> None:
    response = CLIENT.get("/items/1", headers=header)

    assert uuid.UUID(response.headers["x-request-id"]).version == 4


@pytest.mark.req("fase-1a:2.4", "fase-1a:NFR-5")
def test_error_no_controlado_registra_la_traza_sin_el_mensaje_de_la_excepcion() -> None:
    with captured_logs() as stream:
        response = CLIENT.get("/boom", params={"q": "dato-privado-123"})

    access, failure = log_lines(stream)
    assert response.status_code == 500
    assert access["logger"] == "api.access"
    assert access["status"] == 500
    assert failure["logger"] == "api.errors"
    assert failure["level"] == "ERROR"
    assert failure["route"] == "/boom"
    assert failure["request_id"] == access["request_id"]
    assert failure["request_id"] == response.headers["x-request-id"]
    assert failure["traceback"].startswith("builtins.RuntimeError\n")
    assert "boom" in failure["traceback"]
    assert "dato-privado-123" not in stream.getvalue()


@pytest.mark.req("fase-1a:NFR-5")
def test_json_formatter_descarta_mensaje_excepcion_y_campos_ajenos() -> None:
    record = logging.LogRecord(
        name="api.access",
        level=logging.WARNING,
        pathname=__file__,
        lineno=1,
        msg="token %s",
        args=("secreto",),
        exc_info=(ValueError, ValueError("mensaje-privado"), None),
    )
    record.__dict__.update(
        {"request_id": "abc", "status": 200, "password": "p", "authorization": "a"}
    )

    line = json.loads(JsonFormatter().format(record))

    assert set(line) == {"timestamp", "level", "logger", "request_id", "status"}
    assert line["level"] == "WARNING"
    output = json.dumps(line)
    assert all(word not in output for word in ("secreto", "mensaje-privado", "token"))


@pytest.mark.req("fase-1a:NFR-5")
def test_json_formatter_solo_admite_los_campos_declarados() -> None:
    assert LOG_FIELDS == (
        "request_id",
        "method",
        "route",
        "status",
        "duration_ms",
        "traceback",
    )
