from datetime import date

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from svj import banka, denik, faktury
from svj.db import BankovniPohyb, BankovniUcet, PravidloParovani
from svj.domena import profil as profily
from tests.gpc_pomoc import pohyb, vypis

PROVOZNI, FOND = "2800000001", "2800000002"
VLASTNIK = "19-123457"
UKLID = "999563"
PROFIL = profily.nacti("ukazka")


def _leden(stary=1_000_000):
    d = date(2025, 1, 15)
    return vypis(
        PROVOZNI,
        1,
        od=date(2024, 12, 31),
        datum=date(2025, 1, 31),
        stary=stary,
        pohyby=[
            pohyb(
                PROVOZNI,
                1_038_000,
                doklad="101",
                protiucet=VLASTNIK,
                banka="0800",
                vs="5",
                nazev="Novákovi",
                datum=d,
                zprava="zaloha leden",
            ),
            pohyb(
                PROVOZNI,
                -484_000,
                doklad="102",
                protiucet=UKLID,
                banka="5500",
                vs="2213243",
                nazev="Úklid Šťastný",
                datum=d,
            ),
            pohyb(PROVOZNI, -5_000, doklad="103", nazev="Poplatek za vedení", datum=d),
            pohyb(
                PROVOZNI,
                -200_000,
                doklad="104",
                protiucet=FOND,
                banka="5500",
                nazev="Převod do FO",
                datum=d,
            ),
        ],
    )


def _nahraj(session, data=None, ucel="provozni", **kw):
    return banka.nahraj(
        session,
        PROFIL,
        data or _leden(),
        nazev_souboru="leden.gpc",
        nahral="vybor@example.test",
        ucel=ucel,
        **kw,
    )


def _pohyby(session):
    return {p.klic: p for p in session.scalars(select(BankovniPohyb))}


def test_neznamy_ucet_se_zepta_na_ucel(session):
    with pytest.raises(banka.NeznamyUcet) as e:
        _nahraj(session, ucel=None)
    assert e.value.cislo == PROVOZNI
    v = _nahraj(session)
    assert [(x.ucel, x.cislo, x.pocet_pohybu) for x in v.vypisy] == [("provozni", 1, 4)]
    assert session.scalar(select(BankovniUcet.ucel)) == "provozni"


def test_opakovane_nahrani_nic_nezdvoji(session):
    _nahraj(session)
    v = _nahraj(session, ucel=None)
    assert v.vypisy[0].uz_byl_nahrany
    assert len(_pohyby(session)) == 4


def test_navaznost_vypisu(session):
    _nahraj(session)
    novy = 1_000_000 + 1_038_000 - 484_000 - 5_000 - 200_000
    d = date(2025, 2, 10)
    spatny = vypis(
        PROVOZNI,
        2,
        od=date(2025, 1, 31),
        datum=date(2025, 2, 28),
        stary=novy + 1,
        pohyby=[pohyb(PROVOZNI, 100, doklad="201", datum=d)],
    )
    with pytest.raises(banka.ChybaBanky, match="nenavazuje"):
        _nahraj(session, spatny, ucel=None)
    dobry = vypis(
        PROVOZNI,
        2,
        od=date(2025, 1, 31),
        datum=date(2025, 2, 28),
        stary=novy,
        pohyby=[pohyb(PROVOZNI, 100, doklad="201", datum=d)],
    )
    assert _nahraj(session, dobry, ucel=None).vypisy[0].pocet_pohybu == 1


def test_nahrany_pohyb_nejde_zmenit(session):
    _nahraj(session)
    session.commit()
    with pytest.raises(DBAPIError, match="nejde změnit"):
        session.execute(text("UPDATE bankovni_pohyb SET castka = 1"))
        session.flush()
    session.rollback()


UKLID_LEDEN = faktury.NovaFaktura(
    dodavatel="Úklid Šťastný",
    castka=484_000,
    duzp=date(2025, 1, 2),
    splatnost=date(2025, 1, 14),
    druh="UKLID",
    cislo_dodavatele="FV-2025-001",
    vs="2213243",
    ucet_dodavatele="1234567/5500",
)


def test_navrhy_a_zauctovani(session):
    session.add(BankovniUcet(cislo=FOND, ucel="fond_oprav"))
    _nahraj(session)
    p = _pohyby(session)
    ucty = list(session.scalars(select(BankovniUcet)))

    assert banka.navrhni(p["101"], ucty, []) is None
    assert banka.navrhni(p["103"], ucty, []).operace == "poplatek-banky"
    prevod = banka.navrhni(p["104"], ucty, [])
    assert (prevod.operace, prevod.vstupy) == ("prevod-mezi-ucty", {"druhy_ucet": "fond_oprav"})

    banka.zauctuj_pohyb(
        session,
        PROFIL,
        p["101"].id,
        "uhrada-predpisu",
        {"jednotka": "1001/5"},
        zauctoval="vybor@example.test",
        zapamatovat=True,
    )
    f = faktury.zauctuj(session, PROFIL, UKLID_LEDEN, zadal="vybor@example.test")
    kontext = banka.KontextNavrhu(otevrene_faktury=faktury.prehled(session, jen_otevrene=True))
    n = banka.navrhni(p["102"], ucty, [], kontext)
    assert (n.operace, n.vstupy, n.duvod) == (
        "uhrada-faktury",
        {"faktura": f.cislo},
        "VS odpovídá faktuře 2025001.",
    )
    banka.zauctuj_pohyb(
        session,
        PROFIL,
        p["102"].id,
        "uhrada-faktury",
        n.vstupy,
        zauctoval="vybor@example.test",
    )
    banka.zauctuj_pohyb(
        session, PROFIL, p["103"].id, "poplatek-banky", {}, zauctoval="vybor@example.test"
    )
    banka.zauctuj_pohyb(
        session,
        PROFIL,
        p["104"].id,
        "prevod-mezi-ucty",
        {"druhy_ucet": "fond_oprav"},
        zauctoval="vybor@example.test",
    )
    session.commit()

    z = denik.zustatky(session, 2025)
    assert z["221100"] == 1_038_000 - 484_000 - 5_000 - 200_000
    assert z["311100"] == -1_038_000
    assert z["321100"] == 0  # faktura zaplacená
    assert z["315012"] == 484_000  # náklad na úklid
    assert z["549100"] == 5_000
    assert z["261100"] == 200_000  # peníze na cestě, dokud nepřijde výpis fondu oprav

    pravidla = list(session.scalars(select(PravidloParovani)))
    assert [(r.protiucet, r.operace, r.parametry) for r in pravidla] == [
        (VLASTNIK, "uhrada-predpisu", {"jednotka": "1001/5"})
    ]
    unor = BankovniPohyb(castka=1_038_000, protiucet=VLASTNIK, vs="5", nazev="", zprava="")
    unor.ucet = ucty[0]
    assert banka.navrhni(unor, ucty, pravidla).vstupy == {"jednotka": "1001/5"}


def test_zauctovani_jen_jednou_a_s_kontrolou(session):
    _nahraj(session)
    p = _pohyby(session)
    with pytest.raises(banka.ChybaBanky, match="Jednotku 1001/99"):
        banka.zauctuj_pohyb(
            session, PROFIL, p["101"].id, "uhrada-predpisu", {"jednotka": "1001/99"}, zauctoval="x"
        )
    with pytest.raises(banka.ChybaBanky, match="nejde použít"):
        banka.zauctuj_pohyb(session, PROFIL, p["101"].id, "poplatek-banky", {}, zauctoval="x")
    banka.zauctuj_pohyb(
        session, PROFIL, p["101"].id, "uhrada-predpisu", {"jednotka": "1001/5"}, zauctoval="x"
    )
    with pytest.raises(banka.ChybaBanky, match="už je zaúčtovaný"):
        banka.zauctuj_pohyb(
            session, PROFIL, p["101"].id, "uhrada-predpisu", {"jednotka": "1001/5"}, zauctoval="x"
        )
