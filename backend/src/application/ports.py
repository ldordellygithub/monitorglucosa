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


class DatabaseProbe(Protocol):
    """Puerto de comprobación de conectividad con la base de datos."""

    async def check(self) -> None:
        """Comprueba que la base de datos responde.

        Raises:
            DatabaseUnavailableError: si la base de datos no responde o la
                conexión falla.
        """
        ...
