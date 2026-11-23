"""API uzávěrky přes HTTP: návrh výpočtu daně a její zaúčtování."""

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from svj import api_uzaverka, prihlaseni
from svj.api import app
from tests.test_pocatecni import _otevri_2026
from tests.test_prihlaseni import FalesneJwks, token
from tests.test_uzaverka import _urok


@pytest.fixture
def klient(session, monkeypatch):
    monkeypatch.setattr(prihlaseni, "_jwks", lambda: FalesneJwks())
    monkeypatch.setattr(api_uzaverka, "sezeni", lambda: sessionmaker(session.get_bind()))
    c = TestClient(app)
    c.headers["Authorization"] = f"Bearer {token()}"
    return c


def test_dan_v_prehledu_a_zauctovani(session, klient):
    _otevri_2026(session)
    _urok(session, "urok-z-prodleni", "12000.00", date(2026, 3, 1))
    _urok(session, "uhrada-uroku-z-prodleni", "12000.00", date(2026, 5, 1), ucet="provozni")
    session.commit()

    dan = klient.get("/api/uzaverka/2026").json()["dan"]
    assert dan["musi_podat"] is True and dan["dan"] == 252_000
    assert dan["zauctovano"] is None
    assert {"kod": "SPRAVA", "nazev": "Správa nemovitosti"} in dan["polozky_spravy"]
    assert [r["radek"] for r in dan["vypocet"]][-3:] == ["250", "270", "290"]

    r = klient.post("/api/uzaverka/2026/dan", json={"polozka": "SPRAVA"})
    assert r.status_code == 200, r.text
    assert r.json()["dan"]["zauctovano"] == 252_000
    r = klient.post("/api/uzaverka/2026/dan", json={"polozka": "SPRAVA"})
    assert r.status_code == 422 and "už je zaúčtovaná" in r.json()["detail"]
