"""Interní doklady podle operací z katalogu: kontrola polí, náhled a zaúčtování."""

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from svj import api_interni_doklady, interni_doklady, prihlaseni, vyuctovani_spravy
from svj.api import app
from svj.db import RadekZapisu
from tests.test_banka import PROFIL
from tests.test_pocatecni import _otevri_2026
from tests.test_prihlaseni import FalesneJwks, token


def test_vsechny_operace_formulare_jdou_v_ukazce_zauctovat():
    assert all(interni_doklady.dostupne(PROFIL).values())


def test_casove_rozliseni_nese_polozku_spravy(session):
    """Odložený náklad pojištění sníží náklady položky Pojištění ve vyúčtování záloh."""
    _otevri_2026(session)
    radky = interni_doklady.nahled(
        PROFIL,
        "casove-rozliseni",
        "k_rozvahovemu_dni",
        {"sluzba": "POJISTENI", "castka": 1_850_000},
    )
    assert [(r.strana, r.ucet, r.castka, r.dimenze) for r in radky] == [
        ("md", "381100", 1_850_000, {"sluzba": "POJISTENI"}),
        ("d", PROFIL.ucet("naklady.pojisteni"), 1_850_000, {"sluzba": "POJISTENI"}),
    ]
    z = interni_doklady.zauctuj(
        session, PROFIL, "casove-rozliseni", "k_rozvahovemu_dni",
        {"sluzba": "POJISTENI", "castka": 1_850_000},
        datum=date(2026, 12, 31), popis="Pojištění 7/2026–6/2027", zauctoval="x",
    )  # fmt: skip
    session.commit()
    assert z.doklad == "ID"
    pojisteni = next(
        p for p in vyuctovani_spravy.spocitej(session, PROFIL, 2026).polozky if p.kod == "POJISTENI"
    )
    assert pojisteni.naklady == -1_850_000


@pytest.mark.parametrize(
    ("operace", "krok", "vstupy", "chyba"),
    [
        ("casove-rozliseni", None, {"sluzba": "POJISTENI", "castka": 100}, "krok"),
        ("casove-rozliseni", "rozpusteni", {"sluzba": "VODA", "castka": 100}, "z nabídky"),
        ("prevod-vynosu-do-fo", None, {"castka": 0}, "nula"),
        ("prevod-vynosu-do-fo", None, {"castka": -100}, "záporná"),
        ("dotace-rozhodnuti", None, {"poskytovatel": " ", "castka": 100}, "Vyplňte"),
        (
            "odmena-vyboru",
            None,
            {"clen": "předseda", "hruba": 100, "dan": 80, "pojistne_clen": 30, "pojistne_svj": 0},
            "vyšší než hrubá",
        ),
        (
            "preuctovani-mezi-sluzbami",
            None,
            {"z_sluzby": "TEPLO", "do_sluzby": "TEPLO", "castka": 100},
            "různé",
        ),
        ("uhrada-predpisu", None, {}, "nejde"),
    ],
)
def test_kontrola_poli(operace, krok, vstupy, chyba):
    with pytest.raises(interni_doklady.ChybaDokladu, match=chyba):
        interni_doklady.nahled(PROFIL, operace, krok, vstupy)


def test_zasoby_se_znamenkem_prohodi_strany():
    radky = interni_doklady.nahled(PROFIL, "zasoby-konec-roku", None, {"castka": -50_000})
    assert [(r.strana, r.ucet) for r in radky] == [
        ("md", PROFIL.ucet("naklady.spotreba")),
        ("d", PROFIL.ucet("zasoby")),
    ]


@pytest.fixture
def klient(session, monkeypatch):
    monkeypatch.setattr(prihlaseni, "_jwks", lambda: FalesneJwks())
    monkeypatch.setattr(api_interni_doklady, "sezeni", lambda: sessionmaker(session.get_bind()))
    monkeypatch.setattr(api_interni_doklady, "_profil", lambda: PROFIL)
    c = TestClient(app)
    c.headers["Authorization"] = f"Bearer {token()}"
    return c


def test_api_interniho_dokladu(session, klient):
    _otevri_2026(session)
    session.commit()
    nabidka = klient.get("/api/interni-doklady").json()
    odmena = next(o for o in nabidka["operace"] if o["id"] == "odmena-vyboru")
    assert odmena["stav"] == "overit" and [p["klic"] for p in odmena["pole"]][0] == "clen"
    vstupy = {"poskytovatel": "Kraj", "castka": 5_000_000}
    nahled = klient.post(
        "/api/interni-doklady/nahled", json={"operace": "dotace-rozhodnuti", "vstupy": vstupy}
    )
    assert nahled.status_code == 200, nahled.text
    assert [r["strana"] for r in nahled.json()] == ["md", "d"]
    r = klient.post(
        "/api/interni-doklady",
        json={
            "operace": "dotace-rozhodnuti",
            "vstupy": vstupy,
            "datum": "2026-04-01",
            "popis": " ",
        },
    )
    assert r.status_code == 422 and "týká" in r.json()["detail"]
    r = klient.post(
        "/api/interni-doklady",
        json={
            "operace": "dotace-rozhodnuti",
            "vstupy": vstupy,
            "datum": "2026-04-01",
            "popis": "Rozhodnutí o dotaci na zateplení",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["rok"] == 2026
    protistrany = session.scalars(select(RadekZapisu.protistrana)).all()
    assert protistrany == ["Kraj", "Kraj"]
    r = klient.post(
        "/api/interni-doklady",
        json={
            "operace": "dotace-rozhodnuti",
            "vstupy": vstupy,
            "datum": "2024-04-01",
            "popis": "x",
        },
    )
    assert r.status_code == 422 and "není otevřené" in r.json()["detail"]
