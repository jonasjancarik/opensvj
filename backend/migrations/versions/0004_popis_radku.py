"""Popis řádku zápisu: u počátečních stavů říká, za co dluh je (např. „Vyúčtování 2024“).

Revision ID: 0004
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("radek_zapisu", sa.Column("popis", sa.String(200), nullable=True))


def downgrade() -> None:
    op.drop_column("radek_zapisu", "popis")
