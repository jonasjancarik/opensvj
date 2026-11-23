"""API dlužníků a dluhů jednotky přes HTTP. Označení jednotky obsahuje lomítko."""

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from svj import api_banka, api_dluznici, predpisy, prihlaseni
from svj.api import app
from svj.db import Obdobi
from tests.test_banka import PROFIL
from tests.test_prihlaseni import FalesneJwks, token


@pytest.fixture
def klient(session, monkeypatch):
    monkeypatch.setattr(prihlaseni, "_jwks", lambda: FalesneJwks())
    for modul in (api_banka, api_dluznici):
        monkeypatch.setattr(modul, "sezeni", lambda: sessionmaker(session.get_bind()))
    c = TestClient(app)
    c.headers["Authorization"] = f"Bearer {token()}"
    return c


def test_predpis_uroku_a_dluhy_jednotky(session, klient):
    rok = date.today().year  # úrok se předepisuje k dnešku, jen v běžném roce
    session.add(Obdobi(rok=rok, stav="otevrene"))
    session.flush()
    nast = predpisy.nacti(PROFIL)
    predpisy.vygeneruj(session, PROFIL, nast, rok, 3, zauctoval="x", dnes=date(rok, 5, 1))
    predpisy.vygeneruj(session, PROFIL, nast, rok, 4, zauctoval="x", dnes=date(rok, 5, 1))
    session.commit()

    dluhy = klient.get(f"/api/banka/dluhy/{rok}", params={"jednotka": "1001/1"})
    assert dluhy.status_code == 200, dluhy.text
    assert [d["popis"] for d in dluhy.json()] == [
        f"Zálohy za březen {rok}",
        f"Zálohy za duben {rok}",
    ]

    r = klient.post(f"/api/dluznici/{rok}/urok", json={"jednotka": "1001/1", "castka": 12_345})
    assert r.status_code == 200, r.text
    j = next(x for x in r.json()["jednotky"] if x["jednotka"] == "1001/1")
    assert j["sankce"] == 12_345 and j["urok_do"] == date.today().isoformat()


def test_odpis_dluhu(session, klient):
    rok = date.today().year
    session.add(Obdobi(rok=rok, stav="otevrene"))
    session.flush()
    nast = predpisy.nacti(PROFIL)
    predpisy.vygeneruj(session, PROFIL, nast, rok, 3, zauctoval="x", dnes=date(rok, 5, 1))
    session.commit()

    r = klient.post(
        f"/api/dluznici/{rok}/odpis",
        json={"jednotka": "1001/1", "castka": 10_000, "polozka": "SPRAVA", "rozhodnuti": " "},
    )
    assert r.status_code == 422 and "rozhodl" in r.json()["detail"]
    r = klient.post(
        f"/api/dluznici/{rok}/odpis",
        json={
            "jednotka": "1001/1",
            "castka": 10_000,
            "polozka": "SPRAVA",
            "rozhodnuti": "Usnesení výboru",
        },
    )
    assert r.status_code == 200, r.text
    [o] = r.json()["odepsane"]
    assert (o["jednotka"], o["zbyva"]) == ("1001/1", 10_000)
    assert o["odpisy"][0]["polozka"] == "Správa nemovitosti"
    assert o["odpisy"][0]["dluhy"] == [f"Zálohy za březen {rok}"]
