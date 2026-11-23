"""Dluh, který vlastník při platbě určil.

Když vlastník při platbě řekne, na který dluh platí, započte se platba nejdřív na něj
(§ 1933 odst. 1 OZ). Řádek platby proto odkazuje na řádek zápisu, ze kterého určený dluh
vznikl (předpis měsíce, nedoplatek z vyúčtování, počáteční stav).

Revision ID: 0015
"""

import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "radek_zapisu",
        sa.Column("urceno_na", sa.BigInteger, sa.ForeignKey("radek_zapisu.id"), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("radek_zapisu", "urceno_na")
