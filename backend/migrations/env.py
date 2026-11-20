from alembic import context
from sqlalchemy import create_engine

from svj.db import Zaklad
from svj.nastaveni import nastaveni

target_metadata = Zaklad.metadata


def run_migrations_online() -> None:
    url = context.config.attributes.get("url") or nastaveni().database_url
    with create_engine(url).connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    raise SystemExit("Offline migrace se nepoužívají.")
run_migrations_online()
