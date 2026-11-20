"""Přehled pohybů z internetového bankovnictví: zdroj pohybů bez čísla výpisu a zůstatků.

Revision ID: 0003
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

BEZ_ZUSTATKU = (
    "cislo",
    "datum_stareho_zustatku",
    "stary_zustatek",
    "novy_zustatek",
    "obraty_debet",
    "obraty_kredit",
)


def upgrade() -> None:
    op.add_column(
        "bankovni_vypis",
        sa.Column("druh", sa.String(8), nullable=False, server_default="vypis"),
    )
    for sloupec in BEZ_ZUSTATKU:
        op.alter_column("bankovni_vypis", sloupec, nullable=True)
    op.create_check_constraint(
        "druh_vypisu",
        "bankovni_vypis",
        "druh = 'export' OR (druh = 'vypis' AND "
        + " AND ".join(f"{s} IS NOT NULL" for s in BEZ_ZUSTATKU)
        + ")",
    )


def downgrade() -> None:
    op.drop_constraint("druh_vypisu", "bankovni_vypis")
    op.execute("DELETE FROM bankovni_vypis WHERE druh = 'export'")
    for sloupec in BEZ_ZUSTATKU:
        op.alter_column("bankovni_vypis", sloupec, nullable=False)
    op.drop_column("bankovni_vypis", "druh")
