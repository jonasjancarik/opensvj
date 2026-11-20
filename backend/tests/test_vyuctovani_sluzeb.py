"""Roční vyúčtování služeb: klíče, měřidla, výsledky zúčtovatele, zápis a dlužníci."""

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from svj import (
    api_vyuctovani_sluzeb,
    denik,
    dluznici,
    meridla,
    predpisy,
    prihlaseni,
    vyuctovani_sluzeb,
)
from svj.api import app
from tests.test_banka import PROFIL
from tests.test_pocatecni import _otevri_2026
from tests.test_prihlaseni import FalesneJwks, token
from tests.test_vyuctovani_spravy import _faktura

NAST = predpisy.nacti(PROFIL)
KONEC = date(2026, 12, 31)
V = vyuctovani_sluzeb


def _rok(session):
    _otevri_2026(session)
    for m in range(3, 13):
        predpisy.vygeneruj(session, PROFIL, NAST, 2026, m, zauctoval="x", dnes=KONEC)
    _faktura(session, "UKLID", 300_000, date(2026, 4, 1))  # 3 000 Kč
    _faktura(session, "VODA", 2_000_000, date(2026, 9, 30))  # 20 000 Kč
    _faktura(session, "TEPLO", 48_000_000, date(2026, 12, 15))  # 480 000 Kč
    session.commit()


def _vodomery(session):
    for i, j in enumerate(PROFIL.jednotky):
        u = meridla.UdajeMeridla(j, "studena_voda", f"SV-{i}", date(2025, 1, 1))
        m = meridla.pridej_meridlo(session, PROFIL, u, Decimal(0), "x")
        meridla.zapis_odecet(session, m.id, date(2025, 12, 31), Decimal(10), "", "x")
        meridla.zapis_odecet(session, m.id, KONEC, Decimal(10 + 5 * (i + 1)), "", "x")
    session.commit()


def _teplo(session, posun=0):
    castky = dict.fromkeys(PROFIL.jednotky, 3_000_000)  # 30 000 Kč na jednotku
    castky["1001/1"] = 48_000_000 - 11 * 3_000_000 + posun  # 150 000 Kč
    V.uloz_vysledky(session, PROFIL, 2026, "TEPLO", castky, "zúčtovatel", "x")
    session.commit()


def test_osoby_a_chybejici_podklady(session):
    _rok(session)
    v = V.spocitej(session, PROFIL, NAST, 2026, KONEC)
    s = {x.kod: x for x in v.sluzby}
    j = {x.jednotka: x for x in v.jednotky}

    # Úklid podle osob: 26 osob × 12 měsíců = 312 osobo-měsíců, 1001/6 má jednu osobu.
    assert sum(x.osobomesice for x in v.jednotky) == 312
    assert sum(x.naklady["UKLID"] for x in v.jednotky) == 300_000
    assert j["1001/6"].naklady["UKLID"] in (11_538, 11_539)
    assert j["1001/5"].naklady["UKLID"] == pytest.approx(4 * j["1001/6"].naklady["UKLID"], abs=2)
    # Zálohy na úklid 300 Kč měsíčně za deset měsíců.
    assert s["UKLID"].zalohy == 12 * 10 * 30_000

    assert "bez měřidla" in s["VODA"].problem
    assert s["TEPLO"].problem == "Zadejte výsledky od zúčtovatele."
    # Ohřev bez nákladů: zálohy se vrátí celé, výsledky zúčtovatele netřeba.
    assert s["OHREV_TUV"].problem is None and s["OHREV_TUV"].naklady == 0
    duvod = V.proc_nejde(session, NAST, v, KONEC)
    assert "Vodné a stočné" in duvod and "Náklady na teplo" in duvod
    assert "31. 12. 2026" in V.proc_nejde(session, NAST, v, date(2026, 11, 20))


def test_meridla_a_zuctovatel(session):
    _rok(session)
    _vodomery(session)
    _teplo(session, posun=100)
    v = V.spocitej(session, PROFIL, NAST, 2026, KONEC)
    s = {x.kod: x for x in v.sluzby}
    assert s["VODA"].problem is None
    j = {x.jednotka: x for x in v.jednotky}
    # Spotřeba 5, 10, … 60 m³, celkem 390 m³; 1001/1 spotřebovala 5 m³.
    assert j["1001/1"].spotreba["VODA"] == Decimal(5)
    assert j["1001/1"].naklady["VODA"] in (25_641, 25_642)  # 20 000 × 5/390
    assert sum(x.naklady["VODA"] for x in v.jednotky) == 2_000_000
    assert "rozdíl 1,00 Kč" in s["TEPLO"].problem

    _teplo(session)
    v = V.spocitej(session, PROFIL, NAST, 2026, KONEC)
    assert V.proc_nejde(session, NAST, v, KONEC) is None
    assert sum(x.naklady["TEPLO"] for x in v.jednotky) == 48_000_000


def test_zauctovani(session):
    _rok(session)
    _vodomery(session)
    _teplo(session)
    z = V.zauctuj(session, PROFIL, NAST, 2026, zauctoval="x", dnes=KONEC)
    session.commit()
    assert (z.datum, z.doklad, z.operace) == (KONEC, "VY SL 2026", "vyuctovani-sluzeb")
    assert V.zauctuj(session, PROFIL, NAST, 2026, zauctoval="x", dnes=KONEC).id == z.id

    # Zálohy i náklady služeb jsou po vyúčtování nulové.
    zust = denik.zustatky(session, 2026, KONEC)
    role = PROFIL.role_uctu()
    for ucet, c in zust.items():
        if role.get(ucet, "").startswith(("zalohy_sluzby.", "naklady_sluzeb.")):
            assert c == 0, ucet

    v = V.spocitej(session, PROFIL, NAST, 2026, KONEC)
    j = next(x for x in v.jednotky if x.jednotka == "1001/1")
    assert j.rozdil > 0  # teplo 150 000 Kč proti zálohám 26 000 Kč
    d = next(
        x for x in dluznici.prehled(session, PROFIL, NAST, 2026, KONEC) if x.jednotka == "1001/1"
    )
    vy = next(p for p in d.polozky if p.popis == "Vyúčtování služeb 2026")
    assert (vy.splatnost, vy.castka) == (date(2027, 4, 30), j.rozdil)

    with pytest.raises(V.ChybaVyuctovani, match="už je zaúčtované"):
        _teplo(session)


@pytest.fixture
def klient(session, monkeypatch):
    monkeypatch.setattr(prihlaseni, "_jwks", lambda: FalesneJwks())
    monkeypatch.setattr(api_vyuctovani_sluzeb, "sezeni", lambda: sessionmaker(session.get_bind()))
    c = TestClient(app)
    c.headers["Authorization"] = f"Bearer {token()}"
    return c


def test_api(session, klient):
    _rok(session)
    r = klient.get("/api/vyuctovani-sluzeb/2026")
    assert r.status_code == 200, r.text
    teplo = next(x for x in r.json()["sluzby"] if x["kod"] == "TEPLO")
    assert teplo["problem"] == "Zadejte výsledky od zúčtovatele."
    assert teplo["zuctovatel"] == {"castky": {}, "zdroj": ""}

    castky = dict.fromkeys(PROFIL.jednotky, 4_000_000)
    r = klient.put(
        "/api/vyuctovani-sluzeb/2026/zuctovatel/TEPLO",
        json={"castky": castky, "zdroj": " Techem, rozúčtování 2026 "},
    )
    assert r.status_code == 200, r.text
    teplo = next(x for x in r.json()["sluzby"] if x["kod"] == "TEPLO")
    assert teplo["problem"] is None
    assert teplo["zuctovatel"]["zdroj"] == "Techem, rozúčtování 2026"
    j = next(x for x in r.json()["jednotky"] if x["jednotka"] == "1001/1")
    assert next(p for p in j["polozky"] if p["kod"] == "TEPLO")["naklady"] == 4_000_000

    r = klient.put("/api/vyuctovani-sluzeb/2026/zuctovatel/UKLID", json={"castky": {}, "zdroj": ""})
    assert r.status_code == 422
    assert "nerozúčtovává" in r.json()["detail"]
