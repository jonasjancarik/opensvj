"""Ověření přihlášeného uživatele.

Frontend posílá krátkodobý JWT vydaný službou Better Auth v hlavičce Authorization.
Backend ověří podpis veřejnými klíči z JWKS (EdDSA), vydavatele, příjemce a platnost
a potom, že e-mail je pořád na seznamu povolených (AUTH_ALLOWED_EMAILS). Kdo ze seznamu
vypadne, ztratí přístup nejpozději s vypršením tokenu, i když mu přihlášení ještě trvá.
Adresy v AUTH_READONLY_EMAILS smějí jen nahlížet.
"""

import threading
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from . import audit
from .nastaveni import nastaveni

_bearer = HTTPBearer(auto_error=False)

# Jak často nejvýš se kvůli neznámému klíči ptáme přihlašovací služby znovu. Bez toho by
# kdokoli mohl tokeny s vymyšleným `kid` vyvolat dotaz při každém požadavku.
OBNOVA_KLICU_PO = 30.0
_zamek = threading.Lock()
_posledni_obnova = 0.0


@dataclass(frozen=True)
class Uzivatel:
    id: str
    email: str
    jmeno: str


def _seznam(text: str) -> frozenset[str]:
    return frozenset(e.strip().lower() for e in text.split(",") if e.strip())


def je_povoleny(email: str) -> bool:
    return email.lower() in _seznam(nastaveni().auth_allowed_emails)


def jen_cteni(uzivatel: Uzivatel) -> bool:
    return uzivatel.email in _seznam(nastaveni().auth_readonly_emails)


@lru_cache
def _jwks() -> jwt.PyJWKClient:
    return jwt.PyJWKClient(nastaveni().jwks_url, cache_keys=True, lifespan=300, timeout=5)


def _podpisovy_klic(token: str) -> jwt.PyJWK:
    global _posledni_obnova
    kid = jwt.get_unverified_header(token).get("kid")
    if not kid:
        raise jwt.InvalidTokenError("token nemá kid")
    klient = _jwks()
    klic = klient.match_kid(klient.get_signing_keys(), kid)
    if klic is None:
        with _zamek:
            smi = time.monotonic() - _posledni_obnova >= OBNOVA_KLICU_PO
            if smi:
                _posledni_obnova = time.monotonic()
        if smi:
            klic = klient.match_kid(klient.get_signing_keys(refresh=True), kid)
    if klic is None:
        raise jwt.InvalidTokenError("neznámý podpisový klíč")
    return klic


def over_token(token: str) -> Uzivatel:
    n = nastaveni()
    try:
        klic = _podpisovy_klic(token)
        data = jwt.decode(
            token,
            klic.key,
            algorithms=["EdDSA"],
            issuer=n.jwt_issuer,
            audience=n.jwt_audience,
            options={"require": ["exp", "iat", "sub"]},
        )
    except jwt.PyJWKClientError as e:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Přihlašovací služba neodpovídá."
        ) from e
    except jwt.PyJWTError as e:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Přihlášení vypršelo nebo je neplatné."
        ) from e
    email = data.get("email")
    if not email:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token neobsahuje e-mail.")
    if not je_povoleny(email):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "K této aplikaci už nemáte přístup.")
    return Uzivatel(id=data["sub"], email=email.lower(), jmeno=data.get("name") or "")


def prihlaseny(
    cred: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> Uzivatel:
    if cred is None or cred.scheme.lower() != "bearer":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Nejste přihlášeni.")
    return over_token(cred.credentials)


Prihlaseny = Annotated[Uzivatel, Depends(prihlaseny)]


async def zapisujici(uzivatel: Prihlaseny) -> Uzivatel:
    # Asynchronní závislost běží v kontextu požadavku, takže uživatele pro auditní záznam
    # uvidí i obsluha požadavku, kterou FastAPI spouští v jiném vlákně.
    if jen_cteni(uzivatel):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Máte přístup jen pro čtení, změny ukládat nemůžete."
        )
    audit.nastav_uzivatele(uzivatel.email, uzivatel.jmeno)
    return uzivatel


Zapisujici = Annotated[Uzivatel, Depends(zapisujici)]
