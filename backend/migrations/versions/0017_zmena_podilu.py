"""Změny podílů na společných částech s platností od data.

Podíly podle profilu SVJ platí do první změny. Každá změna (typicky změna prohlášení
vlastníka zapsaná do katastru) je celá sada podílů všech jednotek, jejichž součet je
přesně 1. Předpis záloh počítá s novými podíly od prvního celého měsíce jejich platnosti.

Revision ID: 0017
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "zmena_podilu",
        sa.Column("plati_od", sa.Date, primary_key=True),
        # Označení jednotky → podíl jako zlomek "citatel/jmenovatel".
        sa.Column("podily", JSONB, nullable=False),
        sa.Column("zdroj", sa.String(200), nullable=False),
        sa.Column("upravil", sa.String(128), nullable=False),
        sa.Column(
            "upraveno", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )


def downgrade() -> None:
    op.drop_table("zmena_podilu")
