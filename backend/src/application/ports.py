"""Puertos de aplicación (protocolos)."""

from collections.abc import Mapping
from typing import Protocol

from src.application.identity import Identity


class Authenticator(Protocol):
    """Puerto de autenticación que valida cabeceras y devuelve la identidad."""

    def authenticate(self, headers: Mapping[str, str]) -> Identity:
        """Autentica la petición a partir de sus cabeceras HTTP.

        Raises:
            UnauthenticatedError: si las credenciales son inválidas, faltan o no tienen
                los permisos necesarios.
        """
        ...
