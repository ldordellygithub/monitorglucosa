"""Caso de uso de comprobación de salud de la base de datos (/health/ready)."""

from src.application.ports import DatabaseProbe


class CheckReadiness:
    """Ejecuta la sonda de base de datos para verificar que el almacenamiento
    responde.
    """

    def __init__(self, probe: DatabaseProbe) -> None:
        self._probe = probe

    async def execute(self) -> None:
        """Verifica la conectividad con la base de datos.

        Raises:
            DatabaseUnavailableError: si la base de datos no responde.
        """
        await self._probe.check()
