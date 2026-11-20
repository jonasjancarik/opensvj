"""Přijaté faktury: zaúčtování podle druhu, kontrolní pravidla, úhrady a storno."""

from dataclasses import replace
from datetime import date

import pytest

from svj import banka, denik, faktury
from tests.test_banka import PROFIL, UKLID_LEDEN, _nahraj, _pohyby


def test_faktura_za_sluzbu_a_spravu(session):
    f = faktury.zauctuj(session, PROFIL, UKLID_LEDEN, zadal="vybor")
    assert (f.cislo, f.rok, f.zapis.doklad, f.zapis.datum) == (
        "2025001",
        2025,
        "FP 2025001",
        date(2025, 1, 2),
    )
    radky = {(r.strana, r.ucet): r for r in f.zapis.radky}
    assert radky[("d", "321100")].parovaci_symbol == "2025001"
    assert radky[("md", "315012")].parovaci_symbol is None  # symbol jen na závazku
    assert radky[("d", "321100")].protistrana == "Úklid Šťastný"

    s = faktury.zauctuj(
        session,
        PROFIL,
        faktury.NovaFaktura(
            dodavatel="Správce s.r.o.",
            castka=467_544,
            duzp=date(2025, 1, 31),
            splatnost=date(2025, 2, 14),
            druh="SPRAVA",
        ),
        zadal="vybor",
    )
    assert s.cislo == "2025002"
    assert {(r.strana, r.ucet) for r in s.zapis.radky} == {("md", "518100"), ("d", "321100")}

    fo = faktury.zauctuj(
        session,
        PROFIL,
        faktury.NovaFaktura(
            dodavatel="Výtahy a.s.",
            castka=12_055_680,
            duzp=date(2025, 6, 30),
            splatnost=date(2025, 7, 14),
            druh="FOND_OPRAV",
            rozhodnuti="výbor 5/2025",
        ),
        zadal="vybor",
    )
    assert {(r.strana, r.ucet) for r in fo.zapis.radky} == {("md", "955100"), ("d", "321100")}
    session.commit()

    stavy = {x.faktura.cislo: x for x in faktury.prehled(session, rok=2025)}
    assert stavy["2025001"].zbyva == 484_000
    assert stavy["2025001"].stav(date(2025, 1, 10)) == "k_uhrade"
    assert stavy["2025001"].stav(date(2025, 2, 1)) == "po_splatnosti"


@pytest.mark.parametrize(
    ("zmena", "chyba"),
    [
        ({"dodavatel": " "}, "Chybí dodavatel"),
        ({"castka": 0}, "musí být kladná"),
        ({"druh": "NIC"}, "za co faktura je"),
        ({"druh": "FOND_OPRAV"}, "kdo ji schválil"),
        ({"vystaveno": date(2025, 2, 1)}, "Splatnost je dřív"),
        ({"vs": "12a"}, "jen číslice"),
        ({"ico": "123"}, "IČO má 8 číslic"),
    ],
)
def test_spatna_faktura(session, zmena, chyba):
    with pytest.raises(faktury.ChybaFaktury, match=chyba):
        faktury.zauctuj(session, PROFIL, replace(UKLID_LEDEN, **zmena), zadal="x")


def test_dvakrat_stejna_faktura_az_po_stornu(session):
    f = faktury.zauctuj(session, PROFIL, replace(UKLID_LEDEN), zadal="x")
    with pytest.raises(faktury.ChybaFaktury, match="už aplikace má"):
        faktury.zauctuj(
            session, PROFIL, replace(UKLID_LEDEN, dodavatel="úklid  šťastný"), zadal="x"
        )
    denik.storno(session, f.zapis_id, duvod="špatná částka", zauctoval="x")
    session.expire_all()
    znovu = faktury.zauctuj(session, PROFIL, replace(UKLID_LEDEN, castka=480_000), zadal="x")
    assert znovu.cislo == "2025002"
    stavy = {x.faktura.cislo: x for x in faktury.prehled(session)}
    assert stavy["2025001"].stav() == "stornovana" and stavy["2025001"].zbyva == 0
    assert [x.faktura.cislo for x in faktury.prehled(session, jen_otevrene=True)] == ["2025002"]


def test_uhrada_faktury_z_banky(session):
    _nahraj(session)
    p = _pohyby(session)["102"]  # výdaj 4 840 Kč
    mala = faktury.zauctuj(session, PROFIL, replace(UKLID_LEDEN, castka=300_000), zadal="x")
    with pytest.raises(banka.ChybaBanky, match="vyšší, než kolik"):
        banka.zauctuj_pohyb(
            session, PROFIL, p.id, "uhrada-faktury", {"faktura": mala.cislo}, zauctoval="x"
        )
    with pytest.raises(banka.ChybaBanky, match="neexistuje"):
        banka.zauctuj_pohyb(
            session, PROFIL, p.id, "uhrada-faktury", {"faktura": "1999001"}, zauctoval="x"
        )
    velka = faktury.zauctuj(
        session,
        PROFIL,
        replace(UKLID_LEDEN, castka=1_000_000, cislo_dodavatele="FV-2025-002"),
        zadal="x",
    )
    banka.zauctuj_pohyb(
        session, PROFIL, p.id, "uhrada-faktury", {"faktura": velka.cislo}, zauctoval="x"
    )
    session.commit()
    stav = {x.faktura.cislo: x for x in faktury.prehled(session)}[velka.cislo]
    assert (stav.uhrazeno, stav.zbyva, stav.stav(date(2025, 1, 10))) == (
        484_000,
        516_000,
        "castecne",
    )

    # Uhrazenou fakturu nejde stornovat dřív než její úhradu.
    with pytest.raises(denik.ChybaUctovani, match="Nejdřív stornujte ten"):
        denik.storno(session, velka.zapis_id, duvod="chyba", zauctoval="x")
    uhrada = _pohyby(session)["102"].parovani
    denik.storno(session, uhrada.zapis_id, duvod="jiná faktura", zauctoval="x")
    denik.storno(session, velka.zapis_id, duvod="chyba", zauctoval="x")
    session.expire_all()
    assert {x.faktura.cislo: x for x in faktury.prehled(session)}[velka.cislo].stornovana
