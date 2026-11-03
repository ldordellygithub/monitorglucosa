"""Errores de aplicación que `api` traduce a respuestas HTTP."""


class DatabaseUnavailableError(Exception):
    """La base de datos no responde (por ejemplo, está reanudándose tras una pausa)."""
