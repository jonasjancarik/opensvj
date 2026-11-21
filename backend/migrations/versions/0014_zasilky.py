"""Rozesílání dokumentů vlastníkům: neměnné dokumenty a zásilky s doručením.

Dokument je přesně to, co vlastník dostal (HTML s otiskem SHA-256), a po uložení se nemění;
oprava je nový dokument. Zásilka je jedno odeslání dokumentu jednomu vlastníkovi e-mailem
nebo poštou. U e-mailu se ukládají tři události: přijetí serverem příjemce, otevření odkazu
a potvrzení vlastníkem. Datum doručení řídí lhůty (vyúčtování, změna záloh, upomínky).

Revision ID: 0014
"""

import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "dokument",
        sa.Column("id", sa.BigInteger, sa.Identity(always=True), primary_key=True),
        sa.Column("druh", sa.String(32), nullable=False),
        sa.Column("klic", sa.String(64), nullable=False),  # např. vyuctovani_sluzeb:2026
        sa.Column("jednotka", sa.String(32), nullable=False),
        sa.Column("nazev", sa.String(200), nullable=False),
        sa.Column("html", sa.Text, nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("vytvoril", sa.String(128), nullable=False),
        sa.Column("vytvoreno", TS, server_default=sa.func.now(), nullable=False),
    )
    op.create_index("dokument_klic", "dokument", ["klic", "jednotka"])
    op.execute(
        """
        CREATE FUNCTION dokument_nemenny() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          RAISE EXCEPTION 'odeslaný dokument nejde změnit';
        END $$;
        CREATE TRIGGER dokument_nemenny BEFORE UPDATE ON dokument
          FOR EACH ROW EXECUTE FUNCTION dokument_nemenny();
        """
    )
    op.create_table(
        "zasilka",
        sa.Column("id", sa.BigInteger, sa.Identity(always=True), primary_key=True),
        sa.Column(
            "dokument_id", sa.BigInteger, sa.ForeignKey("dokument.id"), nullable=False
        ),
        sa.Column("davka", sa.String(36), nullable=False),
        sa.Column("osoba_id", sa.BigInteger, sa.ForeignKey("osoba.id", ondelete="SET NULL")),
        sa.Column("jmeno", sa.String(200), nullable=False),
        sa.Column("email", sa.String(254)),
        sa.Column("adresa", sa.Text, nullable=False, server_default=""),
        sa.Column("kanal", sa.String(8), nullable=False),
        sa.Column("stav", sa.String(16), nullable=False, server_default="pripravena"),
        sa.Column("pripravil", sa.String(128), nullable=False),
        sa.Column("pripraveno", TS, server_default=sa.func.now(), nullable=False),
        sa.Column("odeslal", sa.String(128)),
        sa.Column("odeslano", TS),
        sa.Column("prijato_serverem", TS),
        sa.Column("otevreno", TS),
        sa.Column("potvrzeno", TS),
        sa.Column("doruceno", sa.Date),
        sa.Column("doruceni_zdroj", sa.String(200), nullable=False, server_default=""),
        sa.Column("token_hash", sa.String(64), unique=True),
        sa.Column("chyba", sa.Text, nullable=False, server_default=""),
        sa.CheckConstraint("kanal IN ('email', 'posta')", name="zasilka_kanal"),
        sa.CheckConstraint(
            "stav IN ('pripravena', 'odeslana', 'dorucena', 'nedorucena')", name="zasilka_stav"
        ),
        sa.CheckConstraint("kanal = 'posta' OR email IS NOT NULL", name="zasilka_email"),
    )
    op.create_index("zasilka_davka", "zasilka", ["davka"])
    op.create_index("zasilka_dokument", "zasilka", ["dokument_id"])


def downgrade() -> None:
    op.drop_table("zasilka")
    op.execute("DROP TRIGGER dokument_nemenny ON dokument; DROP FUNCTION dokument_nemenny();")
    op.drop_table("dokument")
