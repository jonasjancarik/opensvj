"""Odškrtnuté body uzávěrky a rozepsané formuláře uložené v databázi pro celý výbor."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker

from svj import api_formulare, api_pocatecni, api_uzaverka, prihlaseni, ulozene
from svj.api import app
from svj.prihlaseni import Uzivatel
from tests.test_prihlaseni import FalesneJwks, token

ANNA = Uzivatel(id="a", email="anna@example.test", jmeno="Anna")
PETR = Uzivatel(id="p", email="petr@example.test", jmeno="Petr")


def test_odskrtnuti_je_historie_a_plati_posledni(session):
    assert ulozene.odskrtnute(session, 2025) == {}
    z = ulozene.odskrtni(session, 2025, "majetek", True, ANNA)
    assert z is not None and z.kdo == "anna@example.test" and z.jmeno == "Anna"
    # Opakované odškrtnutí nic nepřidá a ponechá původního autora.
    assert ulozene.odskrtni(session, 2025, "majetek", True, PETR).kdo == "anna@example.test"
    assert ulozene.odskrtni(session, 2025, "majetek", False, PETR) is None
    assert ulozene.odskrtnute(session, 2025) == {}
    ulozene.odskrtni(session, 2025, "majetek", True, PETR)
    session.commit()
    assert ulozene.odskrtnute(session, 2025)["majetek"].kdo == "petr@example.test"
    assert ulozene.odskrtnute(session, 2024) == {}
    pocet = session.scalar(text("SELECT count(*) FROM odskrtnuti_uzaverky"))
    assert pocet == 3  # zaškrtnutí, zrušení, zaškrtnutí

    with pytest.raises(DBAPIError):
        session.execute(text("DELETE FROM odskrtnuti_uzaverky"))
    session.rollback()


def test_formular_neprepise_cizi_zmenu(session):
    assert ulozene.nacti_formular(session, "oznameni-zaloh", "2026-07-01") is None
    f = ulozene.uloz_formular(session, "oznameni-zaloh", "2026-07-01", {"oduvodneni": "A"}, 0, ANNA)
    assert f.verze == 1 and f.upravil == "anna@example.test"
    session.commit()

    # Petr i Anna viděli verzi 1. Petr uloží první, Annino uložení se odmítne.
    f = ulozene.uloz_formular(session, "oznameni-zaloh", "2026-07-01", {"oduvodneni": "P"}, 1, PETR)
    assert f.verze == 2
    session.commit()
    with pytest.raises(ulozene.Konflikt) as e:
        ulozene.uloz_formular(
            session, "oznameni-zaloh", "2026-07-01", {"oduvodneni": "A2"}, 1, ANNA
        )
    assert e.value.aktualni.obsah == {"oduvodneni": "P"}
    assert e.value.aktualni.jmeno == "Petr"
    session.rollback()

    # Dva lidé zakládají stejný formulář naráz: druhý dostane konflikt.
    with pytest.raises(ulozene.Konflikt):
        ulozene.uloz_formular(session, "oznameni-zaloh", "2026-07-01", {"oduvodneni": "B"}, 0, ANNA)
    session.rollback()

    with pytest.raises(ulozene.ChybaFormulare):
        ulozene.nacti_formular(session, "neco", "1")
    with pytest.raises(ulozene.ChybaFormulare):
        ulozene.nacti_formular(session, "pocatecni-stavy", "../x")


@pytest.fixture
def klient(session, monkeypatch):
    monkeypatch.setattr(prihlaseni, "_jwks", lambda: FalesneJwks())
    for modul in (api_formulare, api_uzaverka, api_pocatecni):
        monkeypatch.setattr(modul, "sezeni", lambda: sessionmaker(session.get_bind()))
    c = TestClient(app)
    c.headers["Authorization"] = f"Bearer {token()}"
    return c


def test_api_formulare(klient):
    r = klient.get("/api/formulare/pocatecni-stavy/2025")
    assert r.status_code == 200 and r.json()["verze"] == 0 and r.json()["obsah"] is None

    r = klient.put("/api/formulare/pocatecni-stavy/2025", json={"obsah": {"a": 1}, "verze": 0})
    assert r.status_code == 200, r.text
    assert r.json()["verze"] == 1 and r.json()["upravil"] == "vybor@example.test"

    r = klient.put("/api/formulare/pocatecni-stavy/2025", json={"obsah": {"a": 2}, "verze": 0})
    assert r.status_code == 409
    assert r.json()["detail"]["aktualni"]["obsah"] == {"a": 1}

    assert klient.get("/api/formulare/neco/1").status_code == 404
    velky = {"x": "a" * (ulozene.MAX_VELIKOST + 1)}
    r = klient.put("/api/formulare/pocatecni-stavy/2025", json={"obsah": velky, "verze": 1})
    assert r.status_code == 413


def test_api_odskrtnuti_uzaverky(klient):
    kontroly = {k["kod"]: k for k in klient.get("/api/uzaverka/2025").json()["kontroly"]}
    assert kontroly["majetek"]["stav"] == "rucne" and kontroly["majetek"]["odskrtnuti"] is None

    r = klient.post("/api/uzaverka/2025/odskrtnuti", json={"kod": "majetek", "hotovo": True})
    assert r.status_code == 200, r.text
    assert r.json()["jmeno"] == "Výbor"
    kontroly = {k["kod"]: k for k in klient.get("/api/uzaverka/2025").json()["kontroly"]}
    assert kontroly["majetek"]["odskrtnuti"]["kdo"] == "vybor@example.test"

    r = klient.post("/api/uzaverka/2025/odskrtnuti", json={"kod": "majetek", "hotovo": False})
    assert r.status_code == 200 and r.json() is None

    # Body, které aplikace ověřuje sama, ručně odškrtnout nejde.
    r = klient.post("/api/uzaverka/2025/odskrtnuti", json={"kod": "pocatecni", "hotovo": True})
    assert r.status_code == 422
    r = klient.post("/api/uzaverka/2025/odskrtnuti", json={"kod": "nic", "hotovo": True})
    assert r.status_code == 404


def test_rozepsane_pocatecni_stavy_se_po_zauctovani_smazou(klient, session):
    from tests.test_pocatecni import _otevri_2026, _stav

    _otevri_2026(session)
    session.commit()
    r = klient.put("/api/formulare/pocatecni-stavy/2026", json={"obsah": {"x": 1}, "verze": 0})
    assert r.status_code == 200

    stav = _stav()
    telo = {
        "zustatky": [{"ucet": u, "castka": c} for u, c in stav.zustatky.items()],
        "polozky": [
            {"ucet": p.ucet, "castka": p.castka, "jednotka": p.jednotka, "popis": p.popis}
            for p in stav.polozky
        ],
    }
    r = klient.post("/api/pocatecni/2026", json=telo)
    assert r.status_code == 200, r.text
    assert klient.get("/api/formulare/pocatecni-stavy/2026").json()["verze"] == 0
