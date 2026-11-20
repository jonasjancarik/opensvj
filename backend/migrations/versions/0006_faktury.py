"""Přijaté faktury a párovací symbol na řádku zápisu.

Párovací symbol spojí závazek z faktury s jejími úhradami na účtu dodavatelů, takže jde
spočítat, kolik z faktury zbývá zaplatit. Faktura je jen pro připisování; ruší se stornem
jejího zápisu.

Revision ID: 0006
"""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("radek_zapisu", sa.Column("parovaci_symbol", sa.String(40), nullable=True))
    op.create_index("radek_podle_symbolu", "radek_zapisu", ["parovaci_symbol"])
    op.create_table(
        "faktura",
        sa.Column("id", sa.BigInteger, sa.Identity(always=True), primary_key=True),
        sa.Column("cislo", sa.String(16), nullable=False, unique=True),
        sa.Column("rok", sa.Integer, nullable=False),
        sa.Column("dodavatel", sa.String(128), nullable=False),
        sa.Column("ico", sa.String(10)),
        sa.Column("ucet_dodavatele", sa.String(40)),
        sa.Column("cislo_dodavatele", sa.String(40)),
        sa.Column("vs", sa.String(10)),
        sa.Column("vystaveno", sa.Date),
        sa.Column("duzp", sa.Date, nullable=False),
        sa.Column("splatnost", sa.Date, nullable=False),
        sa.Column("castka", sa.BigInteger, nullable=False),
        sa.Column("druh", sa.String(32), nullable=False),
        sa.Column("popis", sa.Text, nullable=False, server_default=""),
        sa.Column("rozhodnuti", sa.String(200)),
        sa.Column(
            "zapis_id", sa.BigInteger, sa.ForeignKey("zapis.id"), nullable=False, unique=True
        ),
        sa.Column("zadal", sa.String(128), nullable=False),
        sa.Column(
            "vytvoreno", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("castka > 0", name="kladna_castka_faktury"),
    )
    op.execute(
        """
        CREATE TRIGGER faktura_jen_pripisovani BEFORE UPDATE OR DELETE ON faktura
          FOR EACH ROW EXECUTE FUNCTION zakaz_zmeny();
        """
    )


def downgrade() -> None:
    op.drop_table("faktura")
    op.drop_index("radek_podle_symbolu", "radek_zapisu")
    op.drop_column("radek_zapisu", "parovaci_symbol")
