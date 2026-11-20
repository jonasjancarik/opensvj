"""Rozhodnutí orgánů SVJ a jejich přiřazení k tomu, co dokládají.

Rozhodnutí je usnesení shromáždění, výboru nebo předsedy. Přiřazení spojuje položku, která
rozhodnutí potřebuje (verze předpisu, klíč vyúčtování, volba v profilu), s rozhodnutím.
Klíč položky obsahuje i zvolenou hodnotu, takže po změně profilu položka znovu čeká na
doložení.

Revision ID: 0010
"""

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rozhodnuti",
        sa.Column("id", sa.BigInteger, sa.Identity(always=True), primary_key=True),
        sa.Column("organ", sa.String(32), nullable=False),
        sa.Column("datum", sa.Date, nullable=False),
        sa.Column("bod", sa.String(32), nullable=False, server_default=""),
        sa.Column("nazev", sa.String(200), nullable=False),
        sa.Column("text", sa.Text, nullable=False, server_default=""),
        sa.Column("hlasovani", sa.String(200), nullable=False, server_default=""),
        sa.Column("ulozeni", sa.String(500), nullable=False, server_default=""),
        sa.Column("upravil", sa.String(128), nullable=False),
        sa.Column(
            "upraveno", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("length(trim(nazev)) > 0", name="rozhodnuti_ma_nazev"),
    )
    op.create_table(
        "rozhodnuti_pro",
        sa.Column("klic", sa.String(128), primary_key=True),
        sa.Column(
            "rozhodnuti_id",
            sa.BigInteger,
            sa.ForeignKey("rozhodnuti.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("upravil", sa.String(128), nullable=False),
        sa.Column(
            "upraveno", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )


def downgrade() -> None:
    op.drop_table("rozhodnuti_pro")
    op.drop_table("rozhodnuti")
