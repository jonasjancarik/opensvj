"""Měřidla a odečty.

Měřidlo patří jednotce, nebo domu (jednotka je prázdná). Platí od osazení do odstranění;
výměna jedno měřidlo uzavře a druhé otevře, spotřeba v roce je součet obou. Odečet je stav
měřidla k datu, nejvýš jeden za den.

Revision ID: 0009
"""

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "meridlo",
        sa.Column("id", sa.BigInteger, sa.Identity(always=True), primary_key=True),
        sa.Column("jednotka", sa.String(32)),  # prázdná = společné měřidlo domu
        sa.Column("druh", sa.String(32), nullable=False),
        sa.Column("vyrobni_cislo", sa.String(64), nullable=False),
        sa.Column("umisteni", sa.String(200), nullable=False, server_default=""),
        sa.Column("osazeno_od", sa.Date, nullable=False),
        sa.Column("odstraneno_do", sa.Date),
        sa.Column("nahrazuje_id", sa.BigInteger, sa.ForeignKey("meridlo.id")),
        sa.Column("poznamka", sa.Text, nullable=False, server_default=""),
        sa.Column("upravil", sa.String(128), nullable=False),
        sa.Column(
            "upraveno", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "odstraneno_do is null or odstraneno_do >= osazeno_od", name="meridlo_od_do"
        ),
        sa.CheckConstraint("length(trim(vyrobni_cislo)) > 0", name="meridlo_ma_cislo"),
    )
    op.create_table(
        "odecet",
        sa.Column("id", sa.BigInteger, sa.Identity(always=True), primary_key=True),
        sa.Column(
            "meridlo_id",
            sa.BigInteger,
            sa.ForeignKey("meridlo.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("datum", sa.Date, nullable=False),
        sa.Column("stav", sa.Numeric(14, 3), nullable=False),
        sa.Column("zdroj", sa.String(200), nullable=False, server_default=""),
        sa.Column("upravil", sa.String(128), nullable=False),
        sa.Column(
            "upraveno", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("stav >= 0", name="odecet_nezaporny"),
        sa.UniqueConstraint("meridlo_id", "datum", name="odecet_jeden_za_den"),
    )


def downgrade() -> None:
    op.drop_table("odecet")
    op.drop_table("meridlo")
