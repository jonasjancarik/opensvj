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
