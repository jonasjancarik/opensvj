"""Uzavření roku, převod zůstatků do dalšího roku a znovuotevření."""

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from svj import api_uzaverka, denik, dluznici, faktury, predpisy, prihlaseni, uzavreni
from svj.api import app
from svj.db import Obdobi
from svj.domena import katalog
from tests.test_banka import PROFIL
from tests.test_prihlaseni import FalesneJwks, token
from tests.test_vyuctovani_sluzeb import _rok

NAST = predpisy.nacti(PROFIL)
PROC_NEJDE = uzavreni.proc_nejde
DNES = date(2027, 2, 1)


def _platba(session, jednotka, castka, datum):
    denik.zauctuj(
        session,
        PROFIL,
        katalog.nacti()["uhrada-predpisu"],
        {"ucet": "provozni", "jednotka": jednotka, "castka": castka},
        datum=datum,
        popis=f"Platba {jednotka}",
        doklad="BV",
        zauctoval="x",
    )


def _priprav(session, monkeypatch):
    _rok(session)
    _platba(session, "1001/1", "200000.00", date(2026, 6, 1))  # přeplatek
    _platba(session, "1001/2", "5000.00", date(2026, 6, 1))  # část dluhu
    session.commit()
    monkeypatch.setattr(uzavreni, "proc_nejde", lambda *a, **k: [])


def _rozvahove(zust: dict[str, int]) -> dict[str, int]:
    return {u: z for u, z in zust.items() if z and u[0] not in "56" and u[:2] != "96"}


def test_uzavreni_a_navaznost(session, monkeypatch):
    _priprav(session, monkeypatch)
    pred = denik.zustatky(session, 2026)
    saldo = {x.jednotka: x.saldo for x in predpisy.saldo(session, PROFIL, 2026)}
    zbyva = {f.faktura.cislo: f.zbyva for f in faktury.prehled(session, rok=2026)}
    assert any(zbyva.values())

    st = uzavreni.uzavri(session, PROFIL, NAST, 2026, zauctoval="x", dnes=DNES)
    session.commit()
    assert st.uzavreny and st.dalsi == "otevrene"
    assert st.vysledkove is None  # ukázka nemá v roce náklady ani výnosy
    assert st.rozvahove is not None and st.otevreni is not None

    # Rok je po uzávěrkových zápisech vynulovaný, výkazy ale vidí stav před nimi.
    assert not any(denik.zustatky(session, 2026, vcetne_uzaverky=True).values())
    assert denik.zustatky(session, 2026) == pred

    # Počáteční stavy navazují na konečné zůstatky účet po účtu.
    assert _rozvahove(denik.zustatky(session, 2027)) == _rozvahove(pred)
    assert {x.jednotka: x.pocatek for x in predpisy.saldo(session, PROFIL, 2027)} == saldo

    # Dluhy přešly po položkách i se splatností, přeplatek jako přeplatek.
    d = {x.jednotka: x for x in dluznici.prehled(session, PROFIL, NAST, 2027, date(2027, 1, 5))}
    assert d["1001/1"].preplatek > 0 and not d["1001/1"].polozky
    prosinec = next(p for p in d["1001/3"].polozky if p.popis == "Zálohy za prosinec 2026")
    assert prosinec.splatnost.year == 2026 and prosinec.urok(date(2027, 1, 5)) is not None
    assert d["1001/3"].z_minulych_let
    for j, x in d.items():
        assert x.saldo == saldo[j]

    # Nezaplacené faktury zůstávají nezaplacené, nic se nezdvojilo.
    assert {f.faktura.cislo: f.zbyva for f in faktury.prehled(session, rok=2026)} == zbyva

    with pytest.raises(denik.ChybaUctovani, match="není otevřené"):
        _platba(session, "1001/1", "1.00", date(2026, 12, 31))
    assert PROC_NEJDE(session, PROFIL, NAST, 2026, DNES) == ["Rok 2026 už je uzavřený."]


def test_znovu_otevreni_a_nove_uzavreni(session, monkeypatch):
    _priprav(session, monkeypatch)
    zbyva = {f.faktura.cislo: f.zbyva for f in faktury.prehled(session, rok=2026)}
    uzavreni.uzavri(session, PROFIL, NAST, 2026, zauctoval="x", dnes=DNES)
    _platba(session, "1001/2", "1000.00", date(2027, 1, 10))  # v novém roce se dál účtuje
    session.commit()

    with pytest.raises(uzavreni.ChybaUzavreni, match="proč"):
        uzavreni.znovu_otevri(session, 2026, duvod=" ", zauctoval="x")
    st = uzavreni.znovu_otevri(session, 2026, duvod="Chybí faktura", zauctoval="x")
    session.commit()
    assert st.stav == "otevrene" and st.otevreni is None and st.rozvahove is None
    assert {f.faktura.cislo: f.zbyva for f in faktury.prehled(session, rok=2026)} == zbyva

    _platba(session, "1001/2", "500.00", date(2026, 12, 20))  # oprava v otevřeném roce
    saldo = {x.jednotka: x.saldo for x in predpisy.saldo(session, PROFIL, 2026)}
    st = uzavreni.uzavri(session, PROFIL, NAST, 2026, zauctoval="x", dnes=DNES)
    session.commit()
    assert st.uzavreny
    assert {x.jednotka: x.pocatek for x in predpisy.saldo(session, PROFIL, 2027)} == saldo


def test_kdy_uzavrit_nejde(session):
    _rok(session)
    duvody = uzavreni.proc_nejde(session, PROFIL, NAST, 2026, date(2026, 12, 31))
    assert duvody == ["Rok jde uzavřít až po 31. 12. 2026."]
    duvody = uzavreni.proc_nejde(session, PROFIL, NAST, 2026, DNES)
    assert any(d.startswith("Zálohy na služby jsou vyúčtované") for d in duvody)
    assert any(d.startswith("Není odškrtnuté") for d in duvody)
    with pytest.raises(uzavreni.ChybaUzavreni):
        uzavreni.uzavri(session, PROFIL, NAST, 2026, zauctoval="x", dnes=DNES)


def test_dalsi_rok_jde_zacit_pred_uzaverkou(session):
    _rok(session)
    uzavreni.zacni_dalsi_rok(session, 2026)
    uzavreni.zacni_dalsi_rok(session, 2026)  # podruhé nic nezmění
    assert session.get(Obdobi, 2027).stav == "otevrene"
    _platba(session, "1001/1", "100.00", date(2027, 1, 5))


@pytest.fixture
def klient(session, monkeypatch):
    monkeypatch.setattr(prihlaseni, "_jwks", lambda: FalesneJwks())
    monkeypatch.setattr(api_uzaverka, "sezeni", lambda: sessionmaker(session.get_bind()))
    c = TestClient(app)
    c.headers["Authorization"] = f"Bearer {token()}"
    return c


def test_api(session, klient, monkeypatch):
    _rok(session)
    session.commit()
    r = klient.get("/api/uzaverka/2026")
    assert r.status_code == 200, r.text
    u = r.json()["uzavreni"]
    assert u["stav"] == "otevrene" and u["dalsi"] is None and u["proc_nejde"]

    r = klient.post("/api/uzaverka/2026/dalsi-rok")
    assert r.json()["uzavreni"]["dalsi"] == "otevrene"
    r = klient.post("/api/uzaverka/2026/uzavrit")
    assert r.status_code == 422

    monkeypatch.setattr(uzavreni, "proc_nejde", lambda *a, **k: [])
    r = klient.post("/api/uzaverka/2026/uzavrit")
    assert r.status_code == 200, r.text
    u = r.json()["uzavreni"]
    assert u["stav"] == "uzavrene" and len(u["zapisy"]) == 2 and u["proc_nejde"] == []

    r = klient.post("/api/uzaverka/2026/znovu-otevrit", json={"duvod": "Oprava faktury"})
    assert r.status_code == 200, r.text
    assert r.json()["uzavreni"]["stav"] == "otevrene"
