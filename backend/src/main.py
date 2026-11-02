"""Composition root de la API: el único punto donde se conectan las capas."""

from fastapi import FastAPI


def create_app() -> FastAPI:
    """Crea la aplicación; las tareas siguientes le añaden rutas y adaptadores."""
    return FastAPI(title="monitorglucosa")
