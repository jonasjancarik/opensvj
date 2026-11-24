"""Dokument s vybranými adresáty.

Při vyúčtování po vlastnických obdobích dostane dřívější vlastník svou část vyúčtování,
i když už jednotku nevlastní. Dokument si pamatuje, komu byl určen; prázdné pole znamená
vlastníky jednotky ke dni přípravy.

Revision ID: 0018
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("dokument", sa.Column("osoby", ARRAY(sa.BigInteger), nullable=True))


def downgrade() -> None:
    op.drop_column("dokument", "osoby")
