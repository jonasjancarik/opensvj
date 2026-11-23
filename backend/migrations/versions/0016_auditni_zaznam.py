"""Auditní záznam změn a otisk schválené verze.

Každá změna vlastníků, rozhodnutí, předpisu, měřidel, výsledků zúčtovatele a stavu
účetního období se zapíše do `auditni_zaznam`: kdo, kdy, co, proč, stav před a po. Záznam
jde jen připisovat (trigger), stejně jako deník.

Přiřazení rozhodnutí k položce si pamatuje otisk (SHA-256) schválené podoby položky.
Když se položka po schválení změní, otisk nesedí a schválení přestane platit.

Revision ID: 0016
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None

TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "auditni_zaznam",
        sa.Column("id", sa.BigInteger, sa.Identity(always=True), primary_key=True),
        sa.Column("kdy", TS, server_default=sa.func.now(), nullable=False),
        # Změny uložené jedním kliknutím mají stejnou transakci.
        sa.Column(
            "transakce",
            sa.BigInteger,
            server_default=sa.text("txid_current()"),
            nullable=False,
        ),
        sa.Column("kdo", sa.String(128), nullable=False),
        sa.Column("jmeno", sa.String(128), nullable=False, server_default=""),
        sa.Column("druh", sa.String(32), nullable=False),
        sa.Column("klic", sa.String(128), nullable=False),
        sa.Column("akce", sa.String(16), nullable=False),
        sa.Column("nazev", sa.String(300), nullable=False),
        sa.Column("duvod", sa.Text, nullable=False, server_default=""),
        sa.Column("pred", JSONB, nullable=True),
        sa.Column("po", JSONB, nullable=True),
        sa.CheckConstraint(
            "akce in ('pridani', 'uprava', 'smazani')", name="akce_auditu"
        ),
    )
    op.create_index("auditni_zaznam_veci", "auditni_zaznam", ["druh", "klic", "id"])
    op.execute(
        """
        CREATE FUNCTION auditni_zaznam_nemenny() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          RAISE EXCEPTION 'auditní záznam nejde změnit ani smazat';
        END $$;
        CREATE TRIGGER auditni_zaznam_nemenny BEFORE UPDATE OR DELETE ON auditni_zaznam
          FOR EACH ROW EXECUTE FUNCTION auditni_zaznam_nemenny();
        """
    )
    op.add_column("rozhodnuti_pro", sa.Column("otisk", sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column("rozhodnuti_pro", "otisk")
    op.execute(
        "DROP TRIGGER auditni_zaznam_nemenny ON auditni_zaznam;"
        " DROP FUNCTION auditni_zaznam_nemenny();"
    )
    op.drop_table("auditni_zaznam")
