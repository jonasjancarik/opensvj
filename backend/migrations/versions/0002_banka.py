"""Banka: účty SVJ, nahrané výpisy, pohyby, jejich zaúčtování a naučená pravidla párování.

Revision ID: 0002
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bankovni_ucet",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("cislo", sa.String(32), nullable=False, unique=True),
        sa.Column("ucel", sa.String(32), nullable=False, unique=True),
        sa.Column(
            "vytvoreno", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_table(
        "bankovni_vypis",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("ucet_id", sa.Integer, sa.ForeignKey("bankovni_ucet.id"), nullable=False),
        sa.Column("rok", sa.Integer, nullable=False),
        sa.Column("cislo", sa.Integer, nullable=False),
        sa.Column("datum", sa.Date, nullable=False),
        sa.Column("datum_stareho_zustatku", sa.Date, nullable=False),
        sa.Column("stary_zustatek", sa.BigInteger, nullable=False),
        sa.Column("novy_zustatek", sa.BigInteger, nullable=False),
        sa.Column("obraty_debet", sa.BigInteger, nullable=False),
        sa.Column("obraty_kredit", sa.BigInteger, nullable=False),
        sa.Column("format", sa.String(16), nullable=False),
        sa.Column("nazev_souboru", sa.Text, nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("nahral", sa.String(128), nullable=False),
        sa.Column(
            "nahrano", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("ucet_id", "rok", "cislo", name="vypis_jednou"),
    )
    op.create_table(
        "bankovni_pohyb",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("vypis_id", sa.BigInteger, sa.ForeignKey("bankovni_vypis.id"), nullable=False),
        sa.Column("ucet_id", sa.Integer, sa.ForeignKey("bankovni_ucet.id"), nullable=False),
        sa.Column("poradi", sa.Integer, nullable=False),
        sa.Column("klic", sa.String(160), nullable=False),
        sa.Column("datum", sa.Date, nullable=False),
        sa.Column("valuta", sa.Date),
        sa.Column("castka", sa.BigInteger, nullable=False),
        sa.Column("kod_uctovani", sa.String(1), nullable=False),
        sa.Column("protiucet", sa.String(32)),
        sa.Column("kod_banky", sa.String(4)),
        sa.Column("nazev", sa.Text, nullable=False),
        sa.Column("vs", sa.String(10)),
        sa.Column("ks", sa.String(10)),
        sa.Column("ss", sa.String(10)),
        sa.Column("zprava", sa.Text, nullable=False),
        sa.UniqueConstraint("ucet_id", "klic", name="pohyb_jednou"),
        sa.CheckConstraint("castka <> 0", name="nenulova_castka"),
    )
    op.create_table(
        "parovani_pohybu",
        sa.Column("pohyb_id", sa.BigInteger, sa.ForeignKey("bankovni_pohyb.id"), primary_key=True),
        sa.Column(
            "zapis_id", sa.BigInteger, sa.ForeignKey("zapis.id"), nullable=False, unique=True
        ),
        sa.Column("operace", sa.String(64), nullable=False),
        sa.Column("vstupy", JSONB, nullable=False),
        sa.Column("zauctoval", sa.String(128), nullable=False),
        sa.Column(
            "vytvoreno", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_table(
        "pravidlo_parovani",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("smer", sa.String(6), nullable=False),
        sa.Column("protiucet", sa.String(32)),
        sa.Column("vs", sa.String(10)),
        sa.Column("operace", sa.String(64), nullable=False),
        sa.Column("parametry", JSONB, nullable=False),
        sa.Column("vytvoril", sa.String(128), nullable=False),
        sa.Column(
            "zmeneno", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("smer in ('prijem', 'vydaj')", name="smer"),
        sa.CheckConstraint("protiucet is not null or vs is not null", name="neco_k_porovnani"),
    )
    op.execute(
        """
        CREATE UNIQUE INDEX pravidlo_jednou
          ON pravidlo_parovani (smer, protiucet, vs) NULLS NOT DISTINCT;

        -- Nahraný výpis a jeho pohyby jsou kopie dokladu banky; nemění se.
        CREATE FUNCTION zakaz_zmeny_vypisu() RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION 'nahraný bankovní výpis nejde změnit ani smazat';
        END $$ LANGUAGE plpgsql;

        CREATE TRIGGER vypis_beze_zmen BEFORE UPDATE OR DELETE ON bankovni_vypis
          FOR EACH ROW EXECUTE FUNCTION zakaz_zmeny_vypisu();
        CREATE TRIGGER pohyb_beze_zmen BEFORE UPDATE OR DELETE ON bankovni_pohyb
          FOR EACH ROW EXECUTE FUNCTION zakaz_zmeny_vypisu();
        -- Zaúčtování pohybu se ruší jen stornem zápisu, stejně jako zápis sám.
        CREATE TRIGGER parovani_jen_pripisovani BEFORE UPDATE OR DELETE ON parovani_pohybu
          FOR EACH ROW EXECUTE FUNCTION zakaz_zmeny();
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE pravidlo_parovani; DROP TABLE parovani_pohybu; DROP TABLE bankovni_pohyb;
        DROP TABLE bankovni_vypis; DROP TABLE bankovni_ucet;
        DROP FUNCTION zakaz_zmeny_vypisu();
        """
    )
