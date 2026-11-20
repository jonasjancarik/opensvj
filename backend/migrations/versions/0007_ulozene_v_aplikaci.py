"""Odškrtnuté body uzávěrky a rozepsané formuláře v databázi místo v prohlížeči.

Odškrtnutí bodu uzávěrky je jen pro připisování: každé zaškrtnutí i zrušení je nový řádek
s tím, kdo a kdy, takže je vidět celá historie. Platí poslední řádek pro daný rok a bod.

Rozepsaný formulář (odůvodnění oznámení o zálohách, počáteční stavy před zaúčtováním) je
jeden řádek s číslem verze. Kdo ukládá, posílá verzi, kterou viděl; když ji mezitím někdo
změnil, uložení se odmítne a nic se nepřepíše.

Revision ID: 0007
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "odskrtnuti_uzaverky",
        sa.Column("id", sa.BigInteger, sa.Identity(always=True), primary_key=True),
        sa.Column("rok", sa.Integer, nullable=False),
        sa.Column("kod", sa.String(64), nullable=False),
        sa.Column("hotovo", sa.Boolean, nullable=False),
        sa.Column("kdo", sa.String(128), nullable=False),
        sa.Column("jmeno", sa.String(128), nullable=False, server_default=""),
        sa.Column("kdy", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("odskrtnuti_podle_bodu", "odskrtnuti_uzaverky", ["rok", "kod", "id"])
    op.execute(
        """
        CREATE TRIGGER odskrtnuti_jen_pripisovani BEFORE UPDATE OR DELETE ON odskrtnuti_uzaverky
          FOR EACH ROW EXECUTE FUNCTION zakaz_zmeny();
        """
    )
    op.create_table(
        "ulozeny_formular",
        sa.Column("druh", sa.String(32), primary_key=True),
        sa.Column("klic", sa.String(64), primary_key=True),
        sa.Column("obsah", JSONB, nullable=False),
        sa.Column("verze", sa.Integer, nullable=False),
        sa.Column("upravil", sa.String(128), nullable=False),
        sa.Column("jmeno", sa.String(128), nullable=False, server_default=""),
        sa.Column(
            "upraveno", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("verze > 0", name="kladna_verze"),
    )


def downgrade() -> None:
    op.drop_table("ulozeny_formular")
    op.drop_table("odskrtnuti_uzaverky")
