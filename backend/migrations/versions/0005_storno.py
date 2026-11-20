"""Storno zápisu a opakované zaúčtování bankovního pohybu po stornu.

Párování pohybu se nemaže (tabulka je jen pro připisování), proto může mít pohyb víc
párování; platné je to, jehož zápis není stornovaný. Zápis jde stornovat jen jednou.

Revision ID: 0005
"""

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE parovani_pohybu DROP CONSTRAINT parovani_pohybu_pkey;
        ALTER TABLE parovani_pohybu ADD COLUMN id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY;
        CREATE INDEX parovani_podle_pohybu ON parovani_pohybu (pohyb_id);
        CREATE UNIQUE INDEX storno_jednou ON zapis (opravuje_zapis) WHERE operace = 'storno';
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP INDEX storno_jednou;
        DROP INDEX parovani_podle_pohybu;
        ALTER TABLE parovani_pohybu DROP COLUMN id;
        ALTER TABLE parovani_pohybu ADD PRIMARY KEY (pohyb_id);
        """
    )
