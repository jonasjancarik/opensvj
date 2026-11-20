import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from svj.nastaveni import KOREN, nastaveni

# Testy běží nad ukázkovým fiktivním SVJ z repozitáře, ať je v .env nastavené cokoli.
os.environ["PROFIL"] = "ukazka"
os.environ["PROFILY"] = str(KOREN / "profiles")
nastaveni.cache_clear()


@pytest.fixture(scope="session")
def db_url():
    url = nastaveni().test_database_url
    try:
        eng = create_engine(url)
        with eng.begin() as c:
            c.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
    except Exception as e:  # pragma: no cover
        pytest.skip(f"testovací databáze není dostupná ({e}); spusťte docker compose up -d")
    cfg = Config(str(KOREN / "backend" / "alembic.ini"))
    cfg.attributes["url"] = url
    command.upgrade(cfg, "head")
    return url


@pytest.fixture
def session(db_url):
    eng = create_engine(db_url)
    with eng.begin() as c:
        c.execute(
            text(
                "TRUNCATE odecet, meridlo, vlastnictvi_osoba, vlastnictvi, osoba,"
                " odskrtnuti_uzaverky, ulozeny_formular, faktura, pravidlo_parovani,"
                " parovani_pohybu, bankovni_pohyb,"
                " bankovni_vypis, bankovni_ucet, radek_zapisu, zapis, obdobi"
                " RESTART IDENTITY CASCADE"
            )
        )
        c.execute(
            text("INSERT INTO obdobi (rok, stav) VALUES (2025, 'otevrene'), (2024, 'uzavrene')")
        )
    s = sessionmaker(eng, expire_on_commit=False)()
    yield s
    s.rollback()
    s.close()
