"""Dependencias inyectables para los routers de la API."""

from typing import Annotated

from fastapi import Depends, Request

from src.application.identity import Identity
from src.application.ports import Authenticator


def get_authenticator(request: Request) -> Authenticator:
    """Obtiene el autenticador configurado en el estado de la aplicación."""
    authenticator = getattr(request.app.state, "authenticator", None)
    if authenticator is None:
        raise RuntimeError("Authenticator no configurado en app.state")
    return authenticator  # type: ignore[no-any-return]


def get_current_identity(
    request: Request,
    authenticator: Annotated[Authenticator, Depends(get_authenticator)],
) -> Identity:
    """Extrae y valida la identidad a partir de las cabeceras HTTP."""
    return authenticator.authenticate(request.headers)


current_identity = Depends(get_current_identity)
