"""Identidad de quien hace la petición."""


class UnauthenticatedError(Exception):
    """La petición no trae una identidad válida."""
