"""Ostatní výnosy: příklad Ukázkové 12 z příručky (kapitola 4)."""

from datetime import date

import pytest

from svj import banka, denik, faktury, interni_doklady, ostatni_vynosy, uzaverka
from svj.domena import katalog
from tests.test_banka import PROFIL
from tests.test_pocatecni import _otevri_2026

KDO = "vybor@example.test"
OKNAR = "Okna Praha s.r.o."


def _doklad(session, operace, zadane, datum, krok=None, popis="doklad"):
    return interni_doklady.zauctuj(
        session, PROFIL, operace, krok, zadane, datum=datum, popis=popis, zauctoval=KDO
    )


def _faktura(session, castka, dodavatel=OKNAR, duzp=date(2026, 11, 20)):
    return faktury.zauctuj(
        session,
        PROFIL,
        faktury.NovaFaktura(
            dodavatel=dodavatel,
            castka=castka,
            duzp=duzp,
            splatnost=date(2026, 12, 20),
            druh="DROBNE_OPRAVY",
        ),
        zadal=KDO,
    )


def _dan_radek(session, cislo):
    d = uzaverka.dan(session, PROFIL, 2026)
    return next(r.castka for r in d.vypocet if r.radek == cislo)


def test_smluvni_pokuta_zapocet_a_dan(session):
    _otevri_2026(session)
    _doklad(
        session,
        "smluvni-pokuta",
        {"protistrana": OKNAR, "castka": 1_200_000},
        date(2026, 10, 15),
        popis="Pokuta za pozdě předaná okna",
    )
    f = _faktura(session, 2_000_000, dodavatel="okna praha  s.r.o.")
    jina = _faktura(session, 500_000, dodavatel="Instalatér Novák")
    session.commit()
    assert ostatni_vynosy.pokuty_dodavatele(session, PROFIL, f.dodavatel) == 1_200_000
    # Pokuta je výnos, ale nezaplacená základ daně nezvyšuje.
    assert _dan_radek(session, "111") == -1_200_000

    with pytest.raises(ostatni_vynosy.ChybaVynosu, match="jen 0,00 Kč"):
        ostatni_vynosy.zapocti_pokutu(
            session, PROFIL, jina.cislo, 100_000, datum=date(2026, 12, 1), zauctoval=KDO
        )
    with pytest.raises(ostatni_vynosy.ChybaVynosu, match="jen 12 000,00 Kč"):
        ostatni_vynosy.zapocti_pokutu(
            session, PROFIL, f.cislo, 1_300_000, datum=date(2026, 12, 1), zauctoval=KDO
        )
    z = ostatni_vynosy.zapocti_pokutu(
        session, PROFIL, f.cislo, 700_000, datum=date(2026, 12, 1), zauctoval=KDO
    )
    session.commit()
    assert sorted((r.strana, r.role, r.castka, r.parovaci_symbol) for r in z.radky) == [
        ("d", "pohledavky_sankce_dodavatele", 700_000, None),
        ("md", "dodavatele", 700_000, f.cislo),
    ]
    assert faktury.otevrena(session, f.cislo).zbyva == 1_300_000
    assert ostatni_vynosy.pokuty_dodavatele(session, PROFIL, OKNAR) == 500_000
    assert _dan_radek(session, "111") == -500_000

    # Zbytek dodavatel zaplatí; v Bance se nabídne jeho otevřená pokuta.
    assert banka.moznosti_pole(PROFIL, "dodavatel", session) == {
        OKNAR: f"{OKNAR} (nezaplacená pokuta 5 000,00 Kč)"
    }
    assert banka.moznosti_pole(PROFIL, "dodavatel") is None
    denik.zauctuj(
        session,
        PROFIL,
        katalog.nacti()["smluvni-pokuta-uhrada"],
        {"ucet": "provozni", "dodavatel": OKNAR, "castka": "5000.00"},
        datum=date(2026, 12, 10),
        popis="Úhrada pokuty",
        doklad="BV",
        zauctoval=KDO,
    )
    session.commit()
    assert ostatni_vynosy.pokuty_dodavatele(session, PROFIL, OKNAR) == 0
    assert banka.moznosti_pole(PROFIL, "dodavatel", session) is None
    assert _dan_radek(session, "111") == 0
    vynos = next(v for v in uzaverka.dan(session, PROFIL, 2026).vynosy if "641200" in v.popis)
    assert (vynos.castka, vynos.zdaneni) == (1_200_000, "predmetne")


def _zustatek(session, role):
    return denik.zustatky(session, 2026).get(PROFIL.ucet(role), 0)


def test_pojistne_plneni_odhad_oznameni_a_uhrada(session):
    """Odhad 41 000 Kč k vytopenému sklepu, pojišťovna oznámí 40 000 Kč a zaplatí je."""
    _otevri_2026(session)
    assert interni_doklady.dostupne(PROFIL)["pojistne-plneni-oznameni"]
    assert interni_doklady.moznosti(PROFIL, "odhad_pojistneho") is None
    assert interni_doklady.moznosti(PROFIL, "odhad_pojistneho", session) == {}
    _doklad(
        session,
        "pojistne-plneni-narok",
        {"udalost": "Sklep 11/2026", "sluzba": "DROBNE_OPRAVY", "castka": 4_100_000},
        date(2026, 11, 30),
        krok="odhad",
    )
    session.commit()
    assert interni_doklady.moznosti(PROFIL, "odhad_pojistneho", session) == {
        "Sklep 11/2026": "Sklep 11/2026 (odhad 41 000,00 Kč)"
    }
    with pytest.raises(interni_doklady.ChybaDokladu, match="z nabídky"):
        interni_doklady.nahled(
            PROFIL, "pojistne-plneni-oznameni", None, {"udalost": "Jiná", "castka": 1}, session
        )

    radky = interni_doklady.nahled(
        PROFIL,
        "pojistne-plneni-oznameni",
        None,
        {"udalost": "Sklep 11/2026", "castka": 4_000_000},
        session,
    )
    assert sorted((r.strana, r.ucet, r.castka) for r in radky) == [
        ("d", PROFIL.ucet("dohadne_aktivni"), 100_000),
        ("d", PROFIL.ucet("dohadne_aktivni"), 4_000_000),
        ("md", PROFIL.ucet("pohledavky_pojistne"), 4_000_000),
        ("md", PROFIL.ucet("naklady.jine"), 100_000),
    ]
    assert {r.dimenze.get("sluzba") for r in radky} == {"DROBNE_OPRAVY"}
    _doklad(
        session,
        "pojistne-plneni-oznameni",
        {"udalost": "Sklep 11/2026", "castka": 4_000_000},
        date(2026, 12, 15),
    )
    session.commit()
    assert _zustatek(session, "dohadne_aktivni") == 0
    assert interni_doklady.moznosti(PROFIL, "odhad_pojistneho", session) == {}
    assert banka.moznosti_pole(PROFIL, "udalost", session) == {
        "Sklep 11/2026": "Sklep 11/2026 (pojišťovna dluží 40 000,00 Kč)"
    }
    denik.zauctuj(
        session,
        PROFIL,
        katalog.nacti()["pojistne-plneni-uhrada"],
        {"ucet": "provozni", "udalost": "Sklep 11/2026", "castka": "40000.00"},
        datum=date(2026, 12, 20),
        popis="Plnění od pojišťovny",
        doklad="BV",
        zauctoval=KDO,
    )
    session.commit()
    assert _zustatek(session, "pohledavky_pojistne") == 0
    assert -_zustatek(session, "vynosy.pojistne_plneni") == 4_100_000
    assert _zustatek(session, "naklady.jine") == 100_000


def test_pojistne_plneni_vyssi_nez_odhad(session):
    _otevri_2026(session)
    _doklad(
        session,
        "pojistne-plneni-narok",
        {"udalost": "Krupobití", "sluzba": "DROBNE_OPRAVY", "castka": 4_100_000},
        date(2026, 11, 30),
        krok="odhad",
    )
    _doklad(
        session,
        "pojistne-plneni-oznameni",
        {"udalost": "Krupobití", "castka": 4_300_000},
        date(2026, 12, 15),
    )
    session.commit()
    assert _zustatek(session, "dohadne_aktivni") == 0
    assert _zustatek(session, "pohledavky_pojistne") == 4_300_000
    assert -_zustatek(session, "vynosy.pojistne_plneni") == 4_300_000


def test_dotace_pouziti_po_letech(session):
    """Dotace 450 000 Kč na akci za 1 000 000 Kč: letos 400 000 Kč nákladů, použije se 180 000."""
    _otevri_2026(session)
    assert interni_doklady.moznosti(PROFIL, "dotace") is None
    _doklad(
        session,
        "dotace-rozhodnuti",
        {"poskytovatel": "Město", "castka": 45_000_000},
        date(2026, 6, 1),
    )
    session.commit()
    assert interni_doklady.moznosti(PROFIL, "dotace", session) == {
        "Město": "Město (zbývá použít 450 000,00 Kč)"
    }
    _doklad(
        session,
        "dotace-pouziti",
        {"poskytovatel": "Město", "castka": 18_000_000},
        date(2026, 12, 31),
    )
    session.commit()
    assert ostatni_vynosy.otevrene(session, PROFIL, ostatni_vynosy.DOTACE_NAROK) == {
        "Město": 27_000_000
    }
    with pytest.raises(interni_doklady.ChybaDokladu, match="zbývá použít jen 270 000,00 Kč"):
        _doklad(
            session,
            "dotace-pouziti",
            {"poskytovatel": "Město", "castka": 30_000_000},
            date(2026, 12, 31),
        )
    with pytest.raises(interni_doklady.ChybaDokladu, match="z nabídky"):
        _doklad(
            session, "dotace-pouziti", {"poskytovatel": "Kraj", "castka": 100}, date(2026, 12, 31)
        )


def test_uzaverka_pripomene_dotaci_a_stary_odhad(session):
    from svj import predpisy
    from svj.db import Obdobi

    _otevri_2026(session)
    _doklad(
        session, "dotace-rozhodnuti", {"poskytovatel": "Město", "castka": 100_000}, date(2026, 6, 1)
    )
    rok_2025 = session.get(Obdobi, 2025) or Obdobi(rok=2025)
    puvodni, rok_2025.stav = rok_2025.stav, "otevrene"
    session.add(rok_2025)
    session.flush()
    _doklad(
        session,
        "pojistne-plneni-narok",
        {"udalost": "Sklep", "sluzba": "DROBNE_OPRAVY", "castka": 50_000},
        date(2025, 12, 31),
        krok="odhad",
    )
    if puvodni:
        rok_2025.stav = puvodni
    session.commit()
    nastaveni = predpisy.nacti(PROFIL, session)
    k = {x.kod: x for x in uzaverka.kontroly(session, PROFIL, nastaveni, 2026, date(2026, 12, 31))}
    assert "Město 1 000,00 Kč" in k["dotace"].detail
    assert "Sklep 500,00 Kč" in k["odhady-pojistneho"].detail

    # Pojišťovna nárok odmítla: celý odhad jde do nákladů.
    _doklad(
        session, "pojistne-plneni-oznameni", {"udalost": "Sklep", "castka": 0}, date(2026, 3, 1)
    )
    session.commit()
    k = {x.kod for x in uzaverka.kontroly(session, PROFIL, nastaveni, 2026, date(2026, 12, 31))}
    assert "odhady-pojistneho" not in k
    assert _zustatek(session, "naklady.jine") == 50_000
