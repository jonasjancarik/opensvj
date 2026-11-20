"""Splatnost na řádku zápisu.

Počáteční stavy převzaté z uzavřeného roku v aplikaci rozepisují dluhy vlastníků po
položkách (zálohy za měsíc, nedoplatek z vyúčtování). Splatnost položky se přenáší s ní,
aby se v novém roce správně poznalo, co je po splatnosti, a počítal úrok z prodlení.

Revision ID: 0012
"""

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("radek_zapisu", sa.Column("splatnost", sa.Date, nullable=True))


def downgrade() -> None:
    op.drop_column("radek_zapisu", "splatnost")
