from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

KOREN = Path(__file__).resolve().parents[3]


class Nastaveni(BaseSettings):
    model_config = SettingsConfigDict(env_file=KOREN / ".env", extra="ignore")

    database_url: str = "postgresql+psycopg://svj:svj@localhost:5440/svj"
    test_database_url: str = "postgresql+psycopg://svj:svj@localhost:5440/svj_test"
    # Profil SVJ (účty, jednotky, předpis) a složka, ve které leží. Údaje skutečného SVJ do
    # repozitáře nepatří; pro vývoj je čte aplikace ze soukromé složky (viz README).
    profil: str = "ukazka"
    profily: Path = KOREN / "profiles"
    jwks_url: str = "http://localhost:3010/api/auth/jwks"
    jwt_issuer: str = "http://localhost:5180"
    jwt_audience: str = "http://localhost:5180"


@lru_cache
def nastaveni() -> Nastaveni:
    n = Nastaveni()
    if not n.profily.is_absolute():
        n.profily = (KOREN / n.profily).resolve()
    return n
