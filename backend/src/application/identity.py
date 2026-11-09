"""Identidad de quien hace la petición."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Identity:
    """Identidad de quien hace la petición (claim `sub`)."""

    subject: str


class UnauthenticatedError(Exception):
    """La petición no trae una identidad válida."""
