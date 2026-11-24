"""Úvěr SVJ splácený vlastníky podle podílů.

Úvěr si pamatuje, jak se jistina rozdělila na jednotky (podíly v haléřích k datu předpisu)
a jak se splácí v měsíčních předpisech. Samotné částky nese deník: předpis podílů je zápis
`uver-predpis-mimoradnych-zaloh` a splátky jsou složkou měsíčního předpisu. Stornem
předpisu podílů úvěr přestane platit.

Revision ID: 0019
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "uver",
        sa.Column("id", sa.BigInteger, sa.Identity(always=True), primary_key=True),
        sa.Column("nazev", sa.String(150), nullable=False),
        sa.Column("cislo_uctu", sa.String(64), nullable=False, server_default=""),
        sa.Column("jistina", sa.BigInteger, nullable=False),
        sa.Column("rozhodnuti_id", sa.BigInteger, sa.ForeignKey("rozhodnuti.id"), nullable=False),
        sa.Column("predepsano_dne", sa.Date, nullable=False),
        sa.Column("prvni_splatka", sa.Date, nullable=False),
        sa.Column("pocet_splatek", sa.Integer, nullable=False),
        # fond_oprav | zaloha_na_uver | kód položky správy
        sa.Column("uroky_hradi", sa.String(32), nullable=False),
        # Označení jednotky → podíl na jistině v haléřích.
        sa.Column("podily", JSONB, nullable=False),
        # Předpis podílů; doplní se ve stejné transakci hned po založení (zápis nese kód úvěru).
        sa.Column("zapis_id", sa.BigInteger, sa.ForeignKey("zapis.id"), nullable=True),
        sa.Column("upravil", sa.String(128), nullable=False),
        sa.Column(
            "upraveno", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("jistina > 0", name="uver_jistina_kladna"),
        sa.CheckConstraint("pocet_splatek > 0", name="uver_pocet_splatek"),
        sa.CheckConstraint("extract(day from prvni_splatka) = 1", name="uver_prvni_den_mesice"),
    )


def downgrade() -> None:
    op.drop_table("uver")
