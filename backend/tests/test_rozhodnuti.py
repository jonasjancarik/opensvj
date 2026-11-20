"""Rozhodnutí orgánů a jejich přiřazení k předpisu, klíčům a volbám v profilu."""

from dataclasses import replace
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from svj import api_rozhodnuti, predpisy, prihlaseni, rozhodnuti, uzaverka
from svj.api import app
from svj.domena import profil
from tests.test_prihlaseni import FalesneJwks, token

PROFIL = profil.nacti("ukazka")
NAST = predpisy.nacti(PROFIL)
KDO = "vybor@example.cz"


def _zalohy(s):
    return rozhodnuti.pridej(
        s,
        rozhodnuti.UdajeRozhodnuti(
            "shromazdeni", date(2026, 2, 12), "Výše záloh od března 2026", bod="4"
        ),
        KDO,
    )


def test_polozky_z_profilu_a_predpisu():
    klice = [p.klic for p in rozhodnuti.polozky(PROFIL, NAST)]
    assert "predpis:2026-03-01" in klice
    assert "klic-spravy:SPRAVA:jednotka" in klice
    assert "volba:predpis_mesice_prevodu:dosavadni" in klice


def test_prirazeni_a_zmena_volby(session):
    r = _zalohy(session)
    assert rozhodnuti.popis(r) == "Shromáždění 12. 2. 2026, bod 4: Výše záloh od března 2026"
    vsechny = len(rozhodnuti.polozky(PROFIL, NAST))
    assert len(rozhodnuti.bez_rozhodnuti(session, PROFIL, NAST)) == vsechny

    rozhodnuti.prirad(session, PROFIL, NAST, "predpis:2026-03-01", r.id, KDO)
    k = "volba:predpis_mesice_prevodu:dosavadni"
    rozhodnuti.prirad(session, PROFIL, NAST, k, r.id, KDO)
    session.flush()
    assert len(rozhodnuti.bez_rozhodnuti(session, PROFIL, NAST)) == vsechny - 2

    # Po změně volby v profilu čeká položka znovu na doložení.
    jiny = replace(PROFIL, predpis_mesice_prevodu="novy")
    bez = {p.klic for p in rozhodnuti.bez_rozhodnuti(session, jiny, NAST)}
    assert "volba:predpis_mesice_prevodu:novy" in bez

    with pytest.raises(rozhodnuti.ChybaRozhodnuti, match="už není"):
        rozhodnuti.prirad(session, PROFIL, NAST, "predpis:1999-01-01", r.id, KDO)

    # Smazané rozhodnutí přestane cokoli dokládat.
    rozhodnuti.smaz(session, r.id)
    session.flush()
    assert len(rozhodnuti.bez_rozhodnuti(session, PROFIL, NAST)) == vsechny


def test_verze_predpisu_jen_v_roce_platnosti(session):
    bez_2025 = {p.klic for p in rozhodnuti.bez_rozhodnuti(session, PROFIL, NAST, 2025)}
    assert "predpis:2026-03-01" not in bez_2025
    bez_2026 = {p.klic for p in rozhodnuti.bez_rozhodnuti(session, PROFIL, NAST, 2026)}
    assert "predpis:2026-03-01" in bez_2026


def test_kontrola_v_uzaverce(session):
    def kontrola():
        k = uzaverka.kontroly(session, PROFIL, NAST, 2025, date(2025, 12, 31))
        return next(x for x in k if x.kod == "rozhodnuti")

    assert kontrola().stav == "chybi"
    r = _zalohy(session)
    for p in rozhodnuti.bez_rozhodnuti(session, PROFIL, NAST, 2025):
        rozhodnuti.prirad(session, PROFIL, NAST, p.klic, r.id, KDO)
    session.flush()
    assert kontrola().stav == "hotovo"


@pytest.fixture
def klient(session, monkeypatch):
    monkeypatch.setattr(prihlaseni, "_jwks", lambda: FalesneJwks())
    monkeypatch.setattr(api_rozhodnuti, "sezeni", lambda: sessionmaker(session.get_bind()))
    c = TestClient(app)
    c.headers["Authorization"] = f"Bearer {token()}"
    return c


def test_api_rozhodnuti(klient):
    r = klient.post(
        "/api/rozhodnuti",
        json={"organ": "vybor", "datum": "2026-01-10", "nazev": "Klíč pro správu", "bod": "2"},
    )
    assert r.status_code == 200, r.text
    [x] = r.json()["rozhodnuti"]
    assert x["popis"] == "Výbor 10. 1. 2026, bod 2: Klíč pro správu"

    r = klient.put(
        "/api/rozhodnuti/prirazeni",
        json={"klic": "klic-spravy:SPRAVA:jednotka", "rozhodnuti_id": x["id"]},
    )
    assert r.status_code == 200, r.text
    p = next(p for p in r.json()["polozky"] if p["klic"] == "klic-spravy:SPRAVA:jednotka")
    assert p["rozhodnuti_id"] == x["id"]

    r = klient.post("/api/rozhodnuti", json={"organ": "x", "datum": "2026-01-10", "nazev": "A"})
    assert r.status_code == 422
