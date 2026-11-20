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
    def __init__(self):
        self.obnoveno = 0

    def get_signing_keys(self, refresh=False):
        self.obnoveno += refresh
        jwk = jwt.algorithms.OKPAlgorithm.to_jwk(KLIC.public_key(), as_dict=True)
        return [jwt.PyJWK.from_dict({**jwk, "alg": "EdDSA", "kid": "k1"})]

    match_kid = staticmethod(jwt.PyJWKClient.match_kid)


@pytest.fixture(autouse=True)
def jwks(monkeypatch):
    falesne = FalesneJwks()
    monkeypatch.setattr(prihlaseni, "_jwks", lambda: falesne)
    monkeypatch.setattr(prihlaseni, "_posledni_obnova", 0.0)
    monkeypatch.setattr(
        nastaveni(), "auth_allowed_emails", "vybor@example.test, ctenar@example.test"
    )
    monkeypatch.setattr(nastaveni(), "auth_readonly_emails", "Ctenar@example.test")
    return falesne


def token(klic=KLIC, kid="k1", **zmeny):
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
    return jwt.encode(data, klic, algorithm="EdDSA", headers={"kid": kid})


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


def test_kdo_neni_na_seznamu_nema_pristup():
    with pytest.raises(HTTPException) as e:
        prihlaseni.over_token(token(email="byvaly@example.test"))
    assert e.value.status_code == 403


def test_neznamy_klic_se_neoveruje_pri_kazdem_pozadavku(jwks):
    for _ in range(3):
        with pytest.raises(HTTPException) as e:
            prihlaseni.over_token(token(kid="vymysleny"))
        assert e.value.status_code == 401
    assert jwks.obnoveno == 1


def test_jen_pro_cteni_nic_neulozi():
    c = TestClient(app)
    hlavicky = {"Authorization": f"Bearer {token(email='ctenar@example.test')}"}
    r = c.get("/api/me", headers=hlavicky)
    assert r.status_code == 200 and r.json()["jen_cteni"] is True
    r = c.post("/api/uzaverka/2026/odskrtnuti", json={"kod": "x", "hotovo": True}, headers=hlavicky)
    assert r.status_code == 403


def test_velky_soubor_se_odmitne():
    c = TestClient(app)
    hlavicky = {"Authorization": f"Bearer {token()}"}
    r = c.post("/api/banka/vypisy", content=b"x" * (5 * 1024 * 1024 + 1), headers=hlavicky)
    assert r.status_code == 413
