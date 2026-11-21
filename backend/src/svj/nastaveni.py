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
    # Kdo smí do aplikace (čárkou oddělené e-maily); stejný seznam čte přihlašovací služba.
    auth_allowed_emails: str = ""
    # Kdo z nich smí jen nahlížet (např. kontrolní komise nebo účetní).
    auth_readonly_emails: str = ""
    # Popis API na /api/docs; zapíná se jen pro vývoj.
    api_docs: bool = False
    # Adresa aplikace pro odkazy v e-mailech vlastníkům.
    app_url: str = "http://localhost:5180"
    # Odesílání e-mailů (dokumenty vlastníkům). Bez SMTP_HOST se e-maily jen uloží jako
    # soubory .eml do MAIL_DIR (pro vývoj); bez obojího aplikace e-maily neposílá.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_tls: str = "starttls"  # starttls | ssl | none
    # Odesílatel, např. „SVJ Ukázková 12 <vybor@ukazkova12.cz>“.
    smtp_from: str = ""
    mail_dir: Path | None = None


@lru_cache
def nastaveni() -> Nastaveni:
    n = Nastaveni()
    if not n.profily.is_absolute():
        n.profily = (KOREN / n.profily).resolve()
    return n
