"""Evidence dlouhodobého majetku SVJ.

Karta majetku nese, co je potřeba pro odpisový plán (cena, zařazení, doba odpisování)
a z čeho bylo pořízení kryté. Částky v účetnictví nese deník: zařazení, roční odpisy
a vyřazení jsou zápisy s kódem karty (`MAJ-<id>`) v dimenzi služby. Majetek převzatý
z počátečních stavů zápis o zařazení nemá a místo něj si pamatuje oprávky k převzetí.

Revision ID: 0020
"""

import sqlalchemy as sa
from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "majetek",
        sa.Column("id", sa.BigInteger, sa.Identity(always=True), primary_key=True),
        sa.Column("nazev", sa.String(150), nullable=False),
        sa.Column("inventarni_cislo", sa.String(32), nullable=False, server_default=""),
        sa.Column("poznamka", sa.Text, nullable=False, server_default=""),
        # movity | stavba | pozemek | nehmotny
        sa.Column("druh", sa.String(16), nullable=False),
        sa.Column("zarazeno", sa.Date, nullable=False),
        sa.Column("cena", sa.BigInteger, nullable=False),
        # Doba odpisování v měsících; pozemek se neodepisuje.
        sa.Column("doba_mesicu", sa.Integer, nullable=True),
        # fond_oprav | fond_ze_zisku | kód položky správy
        sa.Column("kryti", sa.String(32), nullable=False),
        # Převzato z počátečních stavů k 1. 1. roku: oprávky k tomu dni.
        sa.Column("prevzato_k", sa.Date, nullable=True),
        sa.Column("opravky_prevzate", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("zapis_id", sa.BigInteger, sa.ForeignKey("zapis.id"), nullable=True),
        sa.Column("upravil", sa.String(128), nullable=False),
        sa.Column(
            "upraveno", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("cena > 0", name="majetek_cena_kladna"),
        sa.CheckConstraint(
            "opravky_prevzate >= 0 and opravky_prevzate <= cena", name="majetek_opravky"
        ),
        sa.CheckConstraint(
            "(druh = 'pozemek') = (doba_mesicu is null)", name="majetek_doba_odpisovani"
        ),
        sa.CheckConstraint("doba_mesicu is null or doba_mesicu > 0", name="majetek_doba_kladna"),
    )


def downgrade() -> None:
    op.drop_table("majetek")
