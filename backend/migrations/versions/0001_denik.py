"""Účetní deník: období, zápisy, řádky a ochranné triggery.

Revision ID: 0001
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "obdobi",
        sa.Column("rok", sa.Integer, primary_key=True, autoincrement=False),
        sa.Column("stav", sa.String(16), nullable=False, server_default="otevrene"),
        sa.CheckConstraint("stav in ('otevrene', 'v_uzaverce', 'uzavrene')", name="stav_obdobi"),
    )
    op.create_table(
        "zapis",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("rok", sa.Integer, sa.ForeignKey("obdobi.rok"), nullable=False),
        sa.Column("poradove_cislo", sa.Integer, nullable=False),
        sa.Column("datum", sa.Date, nullable=False),
        sa.Column("doklad", sa.String(32), nullable=False),
        sa.Column("operace", sa.String(64), nullable=False),
        sa.Column("popis", sa.Text, nullable=False),
        sa.Column("opravuje_zapis", sa.BigInteger, sa.ForeignKey("zapis.id")),
        sa.Column("idempotencni_klic", sa.String(128), unique=True),
        sa.Column("zauctoval", sa.String(128), nullable=False),
        sa.Column(
            "vytvoreno", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("rok", "poradove_cislo", name="poradove_cislo_v_roce"),
        sa.CheckConstraint("extract(year from datum) = rok", name="datum_v_roce"),
    )
    op.create_table(
        "radek_zapisu",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("zapis_id", sa.BigInteger, sa.ForeignKey("zapis.id"), nullable=False, index=True),
        sa.Column("strana", sa.String(2), nullable=False),
        sa.Column("role", sa.String(64), nullable=False),
        sa.Column("ucet", sa.String(16), nullable=False, index=True),
        sa.Column("castka", sa.BigInteger, nullable=False),
        sa.Column("jednotka", sa.String(32)),
        sa.Column("sluzba", sa.String(32)),
        sa.Column("protistrana", sa.String(128)),
        sa.CheckConstraint("strana in ('md', 'd')", name="strana"),
        sa.CheckConstraint("castka > 0", name="kladna_castka"),
    )
    op.execute(
        """
        -- Zápis musí být vyrovnaný; kontroluje se až při commitu, aby šlo vložit řádky postupně.
        CREATE FUNCTION zkontroluj_vyrovnanost() RETURNS trigger AS $$
        DECLARE rozdil bigint; pocet int;
        BEGIN
          SELECT coalesce(sum(CASE WHEN strana = 'md' THEN castka ELSE -castka END), 0), count(*)
            INTO rozdil, pocet FROM radek_zapisu WHERE zapis_id = NEW.zapis_id;
          IF pocet < 2 OR rozdil <> 0 THEN
            RAISE EXCEPTION 'zápis % není vyrovnaný (rozdíl % haléřů, řádků %)',
              NEW.zapis_id, rozdil, pocet;
          END IF;
          RETURN NULL;
        END $$ LANGUAGE plpgsql;

        CREATE CONSTRAINT TRIGGER vyrovnanost AFTER INSERT ON radek_zapisu
          DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION zkontroluj_vyrovnanost();

        -- Deník je jen pro připisování.
        CREATE FUNCTION zakaz_zmeny() RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION 'zaúčtovaný zápis nejde změnit ani smazat; použijte storno';
        END $$ LANGUAGE plpgsql;

        CREATE TRIGGER denik_jen_pripisovani BEFORE UPDATE OR DELETE ON zapis
          FOR EACH ROW EXECUTE FUNCTION zakaz_zmeny();
        CREATE TRIGGER radky_jen_pripisovani BEFORE UPDATE OR DELETE ON radek_zapisu
          FOR EACH ROW EXECUTE FUNCTION zakaz_zmeny();

        -- Do uzavřeného období nejde zapisovat.
        CREATE FUNCTION zkontroluj_obdobi() RETURNS trigger AS $$
        DECLARE s text;
        BEGIN
          SELECT stav INTO s FROM obdobi WHERE rok = NEW.rok;
          IF s IS DISTINCT FROM 'otevrene' THEN
            RAISE EXCEPTION 'období % není otevřené (stav %)', NEW.rok, s;
          END IF;
          RETURN NEW;
        END $$ LANGUAGE plpgsql;

        CREATE TRIGGER zapis_do_otevreneho BEFORE INSERT ON zapis
          FOR EACH ROW EXECUTE FUNCTION zkontroluj_obdobi();
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE radek_zapisu; DROP TABLE zapis; DROP TABLE obdobi;
        DROP FUNCTION zkontroluj_vyrovnanost(); DROP FUNCTION zakaz_zmeny();
        DROP FUNCTION zkontroluj_obdobi();
        """
    )
