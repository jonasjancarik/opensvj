"""Výsledky zúčtovatele tepla a teplé vody po jednotkách.

Zúčtovatel rozúčtuje teplo a teplou vodu podle vyhlášky 269/2015 Sb. a SVJ převezme jeho
náklad na každou jednotku. Součet za službu musí sedět na náklady služby v účetnictví.

Revision ID: 0011
"""

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "vysledek_zuctovatele",
        sa.Column("rok", sa.Integer, primary_key=True),
        sa.Column("sluzba", sa.String(32), primary_key=True),
        sa.Column("jednotka", sa.String(32), primary_key=True),
        sa.Column("castka", sa.BigInteger, nullable=False),  # haléře
        sa.Column("zdroj", sa.String(200), nullable=False, server_default=""),
        sa.Column("upravil", sa.String(128), nullable=False),
        sa.Column(
            "upraveno", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("castka >= 0", name="vysledek_zuctovatele_nezaporny"),
    )


def downgrade() -> None:
    op.drop_table("vysledek_zuctovatele")
