"""Ověření přihlášeného uživatele.

Frontend posílá krátkodobý JWT vydaný službou Better Auth v hlavičce Authorization.
Backend ověří podpis veřejnými klíči z JWKS (EdDSA), vydavatele, příjemce a platnost.
Identita pochází z Better Auth, role a oprávnění z databáze aplikace.
"""

from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .nastaveni import nastaveni

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Uzivatel:
    id: str
    email: str
    jmeno: str


@lru_cache
def _jwks() -> jwt.PyJWKClient:
    return jwt.PyJWKClient(nastaveni().jwks_url, cache_keys=True, lifespan=300)


def over_token(token: str) -> Uzivatel:
    n = nastaveni()
    try:
        klic = _jwks().get_signing_key_from_jwt(token)
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
    return Uzivatel(id=data["sub"], email=email.lower(), jmeno=data.get("name") or "")


def prihlaseny(
    cred: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> Uzivatel:
    if cred is None or cred.scheme.lower() != "bearer":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Nejste přihlášeni.")
    return over_token(cred.credentials)


Prihlaseny = Annotated[Uzivatel, Depends(prihlaseny)]
