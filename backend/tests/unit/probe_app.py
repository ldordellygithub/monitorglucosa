"""App de prueba con rutas tipadas, el middleware de logs y los manejadores de error."""

import io
import logging
from collections.abc import Generator
from contextlib import contextmanager

from fastapi import FastAPI, Query
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict, Field

from src.api.errors import register_error_handlers
from src.api.middleware import RequestLogMiddleware
from src.application.errors import DatabaseUnavailableError
from src.application.identity import UnauthenticatedError
from src.infrastructure.observability import JsonFormatter


class Item(BaseModel):
    model_config = ConfigDict(extra="forbid")

    count: int
    name: str = Field(max_length=3)


def build_probe_app() -> FastAPI:
    app = FastAPI()

    @app.get("/items/{item_id}")
    def read_item(item_id: int, limit: int = Query(10, ge=1, le=100)) -> dict[str, int]:
        return {"item_id": item_id, "limit": limit}

    @app.post("/items")
    def create_item(item: Item) -> dict[str, int]:
        return {"count": item.count}

    @app.get("/unauthenticated")
    def unauthenticated() -> None:
        raise UnauthenticatedError

    @app.get("/database")
    def database() -> None:
        raise DatabaseUnavailableError

    @app.get("/boom")
    def boom(q: str = "") -> None:
        raise RuntimeError(f"fallo con {q}")

    register_error_handlers(app)
    app.add_middleware(RequestLogMiddleware)
    return app


def probe_client() -> TestClient:
    """Cliente que devuelve el 500 en lugar de relanzar la excepción del servidor."""
    return TestClient(build_probe_app(), raise_server_exceptions=False)


@contextmanager
def captured_logs() -> Generator[io.StringIO]:
    """Captura lo que escriben los loggers `api.*` con el formateador JSON real."""
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    api_logger = logging.getLogger("api")
    previous_level = api_logger.level
    api_logger.addHandler(handler)
    api_logger.setLevel(logging.INFO)
    try:
        yield stream
    finally:
        api_logger.removeHandler(handler)
        api_logger.setLevel(previous_level)
