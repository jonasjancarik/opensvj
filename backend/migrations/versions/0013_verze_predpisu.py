"""Verze předpisu záloh zadané v aplikaci.

Dosud byl předpis jen v souboru `<profil>-predpisy.yaml`. Novou výši záloh (typicky po
shromáždění od nového roku) teď výbor zadá v aplikaci. Verze ze souboru platí dál; verze
z aplikace se stejným datem ji nahradí. Částky jsou v haléřích.

Revision ID: 0013
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "verze_predpisu",
        sa.Column("plati_od", sa.Date, primary_key=True),
        sa.Column("zdroj", sa.String(200), nullable=False, server_default=""),
        sa.Column("slozky", JSONB, nullable=False),
        sa.Column("pevne", JSONB, nullable=False),
        sa.Column("osoby", JSONB, nullable=False),
        sa.Column("upravil", sa.String(128), nullable=False),
        sa.Column(
            "upraveno", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("extract(day from plati_od) = 1", name="verze_od_prvniho"),
    )


def downgrade() -> None:
    op.drop_table("verze_predpisu")
