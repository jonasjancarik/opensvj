"""Ověření JWT bez běžící služby Better Auth: klíče vytvoříme lokálně."""

import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import HTTPException
from fastapi.testclient import TestClient

from svj import prihlaseni
from svj.api import app
from svj.nastaveni import nastaveni

KLIC = Ed25519PrivateKey.generate()
CIZI_KLIC = Ed25519PrivateKey.generate()


class FalesneJwks:
    def get_signing_key_from_jwt(self, token):
        return jwt.PyJWK.from_dict(
            {**jwt.algorithms.OKPAlgorithm.to_jwk(KLIC.public_key(), as_dict=True), "alg": "EdDSA"}
        )


@pytest.fixture(autouse=True)
def jwks(monkeypatch):
    monkeypatch.setattr(prihlaseni, "_jwks", lambda: FalesneJwks())


def token(klic=KLIC, **zmeny):
    n = nastaveni()
    ted = int(time.time())
    data = {
        "sub": "u1",
        "email": "Vybor@Example.test",
        "name": "Výbor",
        "iat": ted,
        "exp": ted + 300,
        "iss": n.jwt_issuer,
        "aud": n.jwt_audience,
        **zmeny,
    }
    return jwt.encode(data, klic, algorithm="EdDSA")


def test_platny_token():
    u = prihlaseni.over_token(token())
    assert (u.id, u.email, u.jmeno) == ("u1", "vybor@example.test", "Výbor")


@pytest.mark.parametrize(
    "zmeny",
    [
        {"exp": int(time.time()) - 10},
        {"iss": "https://jinde.example"},
        {"aud": "https://jinde.example"},
    ],
)
def test_neplatny_token(zmeny):
    with pytest.raises(HTTPException) as e:
        prihlaseni.over_token(token(**zmeny))
    assert e.value.status_code == 401


def test_cizi_podpis():
    with pytest.raises(HTTPException):
        prihlaseni.over_token(token(klic=CIZI_KLIC))


def test_api_vyzaduje_prihlaseni():
    c = TestClient(app)
    assert c.get("/api/me").status_code == 401
    r = c.get("/api/me", headers={"Authorization": f"Bearer {token()}"})
    assert r.status_code == 200
    assert r.json()["email"] == "vybor@example.test"
    r = c.get("/api/katalog", headers={"Authorization": f"Bearer {token()}"})
    assert any(o["id"] == "predpis-mesicni" for o in r.json())
