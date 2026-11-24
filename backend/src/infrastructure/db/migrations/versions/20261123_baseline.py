"""Revisión base vacía para verificar Alembic de punta a punta (7.1, 7.4).

Revision ID: 20261123_baseline
Revises:
Create Date: 2026-11-23
"""

from collections.abc import Sequence

revision: str = "20261123_baseline"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Sin tablas de negocio en fase-1a; crea solo el estado base de Alembic."""


def downgrade() -> None:
    """Reversión simétrica de la revisión base vacía."""
