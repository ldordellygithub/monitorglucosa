"""Sonda de base de datos para comprobaciones de disponibilidad."""

import logging
from typing import Final

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine

from src.application.errors import DatabaseUnavailableError
from src.application.ports import DatabaseProbe

logger = logging.getLogger("infrastructure.db")

_PING_QUERY: Final = text("SELECT 1")


class SqlDatabaseProbe(DatabaseProbe):
    """Ejecuta SELECT 1 en una conexión efímera para verificar la disponibilidad."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def check(self) -> None:
        """Comprueba que la base de datos responde.

        Raises:
            DatabaseUnavailableError: si la base de datos no responde, agota el tiempo
                o se produce un error de conexión.
        """
        try:
            async with self._engine.connect() as conn:
                await conn.execute(_PING_QUERY)
        except (SQLAlchemyError, TimeoutError, OSError) as exc:
            logger.warning(
                "comprobación de base de datos fallida (%s)",
                type(exc).__name__,
            )
            raise DatabaseUnavailableError(
                "La base de datos se está despertando. Reintenta en unos segundos."
            ) from exc
