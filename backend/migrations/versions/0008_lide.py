"""Osoby a vlastnictví jednotek.

Osobní údaje jsou v samostatných tabulkách, oddělené od účetních dat (GDPR): jdou opravit
i smazat, aniž by se sáhlo do deníku. Deník dál pracuje s jednotkou.

Vlastnictví jednotky má platnost od–do. Období jedné jednotky se nesmějí překrývat; hlídá to
vylučovací omezení nad rozsahem dat (proto rozšíření btree_gist). Že na sebe období navazují
bez mezery, zajišťuje aplikace: nové vlastnictví uzavře předchozí den před svým začátkem.

Revision ID: 0008
"""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.create_table(
        "osoba",
        sa.Column("id", sa.BigInteger, sa.Identity(always=True), primary_key=True),
        sa.Column("jmeno", sa.String(200), nullable=False),
        sa.Column("ico", sa.String(10)),
        sa.Column("adresa", sa.Text, nullable=False, server_default=""),
        sa.Column("email", sa.String(254)),
        sa.Column("telefon", sa.String(40)),
        sa.Column("ucet", sa.String(40)),
        sa.Column("souhlas_email", sa.Date),
        sa.Column("poznamka", sa.Text, nullable=False, server_default=""),
        sa.Column("upravil", sa.String(128), nullable=False),
        sa.Column(
            "upraveno", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("length(trim(jmeno)) > 0", name="osoba_ma_jmeno"),
    )
    op.create_table(
        "vlastnictvi",
        sa.Column("id", sa.BigInteger, sa.Identity(always=True), primary_key=True),
        sa.Column("jednotka", sa.String(32), nullable=False),
        sa.Column("plati_od", sa.Date, nullable=False),
        sa.Column("plati_do", sa.Date),
        sa.Column("zdroj", sa.Text, nullable=False, server_default=""),
        sa.Column("upravil", sa.String(128), nullable=False),
        sa.Column(
            "upraveno", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("plati_do is null or plati_do >= plati_od", name="vlastnictvi_od_do"),
    )
    op.execute(
        """
        ALTER TABLE vlastnictvi ADD CONSTRAINT vlastnictvi_neprekryva
          EXCLUDE USING gist (jednotka WITH =, daterange(plati_od, plati_do, '[]') WITH &&)
        """
    )
    op.create_table(
        "vlastnictvi_osoba",
        sa.Column(
            "vlastnictvi_id",
            sa.BigInteger,
            sa.ForeignKey("vlastnictvi.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("osoba_id", sa.BigInteger, sa.ForeignKey("osoba.id"), primary_key=True),
        sa.Column("poradi", sa.Integer, nullable=False),
        # Spoluvlastnický podíl jako text zlomku ("1/2"); u společného jmění manželů prázdný.
        sa.Column("podil", sa.String(20)),
    )


def downgrade() -> None:
    op.drop_table("vlastnictvi_osoba")
    op.drop_table("vlastnictvi")
    op.drop_table("osoba")
