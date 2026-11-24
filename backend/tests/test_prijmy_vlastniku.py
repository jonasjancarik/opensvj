"""Příjmy vlastníků z nájmu společných částí: příklad Ukázkové 12 z příručky (kapitola 4)."""

from datetime import date

import pytest

from svj import banka, denik, interni_doklady, prijmy_vlastniku
from svj.domena import katalog
from tests.test_banka import PROFIL
from tests.test_pocatecni import _otevri_2026

KDO = "vybor@example.test"


def _bv(session, operace, vstupy, datum):
    return denik.zauctuj(
        session,
        PROFIL,
        katalog.nacti()[operace],
        vstupy,
        datum=datum,
        popis=operace,
        doklad="BV",
        zauctoval=KDO,
    )


def _jednotka(prehled, cislo):
    return next(j for j in prehled.jednotky if j.jednotka == cislo)


def test_najem_strechy_podily_a_prevod_do_fondu(session):
    _otevri_2026(session)
    interni_doklady.zauctuj(
        session,
        PROFIL,
        "najem-predpis",
        None,
        {"najemce": "Operátor", "castka": 2_580_000},
        datum=date(2026, 1, 15),
        popis="Nájem střechy 2026",
        zauctoval=KDO,
    )
    session.commit()
    assert banka.moznosti_pole(PROFIL, "najemce", session) == {
        "Operátor": "Operátor (dluží nájemné 25 800,00 Kč)"
    }
    _bv(
        session,
        "najem-uhrada",
        {"ucet": "provozni", "najemce": "Operátor", "castka": "25800.00"},
        date(2026, 2, 1),
    )
    # Platba od nájemce bez předpisu do příjmů vlastníků: vede se jako výnos SVJ.
    _bv(
        session,
        "najem-uhrada",
        {"ucet": "provozni", "najemce": "Reklama", "castka": "1000.00"},
        date(2026, 3, 1),
    )
    session.commit()

    p = prijmy_vlastniku.prehled(session, PROFIL, 2026)
    assert [(x.najemce, x.castka) for x in p.platby] == [("Operátor", 2_580_000)]
    assert p.jako_vynos == ["Reklama"]
    assert p.predepsano == 2_580_000
    assert sum(j.prijato for j in p.jednotky) == 2_580_000
    j6 = _jednotka(p, "1001/6")
    assert (j6.podil, j6.prijato, j6.zbyva) == ("624/8600", 187_200, 187_200)
    assert sum(v.prijato for v in j6.vlastnici) == 187_200
    assert sum(v.predepsano for v in j6.vlastnici) == 187_200

    with pytest.raises(prijmy_vlastniku.ChybaPrijmu, match="požádal"):
        prijmy_vlastniku.prevod_do_fondu(
            session,
            PROFIL,
            jednotka="1001/6",
            castka=187_200,
            datum=date(2026, 3, 10),
            zadost="  ",
            zauctoval=KDO,
        )
    with pytest.raises(prijmy_vlastniku.ChybaPrijmu, match="jen 1 872,00 Kč"):
        prijmy_vlastniku.prevod_do_fondu(
            session,
            PROFIL,
            jednotka="1001/6",
            castka=187_300,
            datum=date(2026, 3, 10),
            zadost="písemná žádost z 5. 3. 2026",
            zauctoval=KDO,
        )
    z = prijmy_vlastniku.prevod_do_fondu(
        session,
        PROFIL,
        jednotka="1001/6",
        castka=187_200,
        datum=date(2026, 3, 10),
        zadost="písemná žádost z 5. 3. 2026",
        zauctoval=KDO,
    )
    j3 = _jednotka(p, "1001/3")
    _bv(
        session,
        "prijmy-vlastniku-vyplata",
        {"ucet": "provozni", "jednotka": "1001/3", "castka": f"{j3.prijato / 100:.2f}"},
        date(2026, 3, 15),
    )
    session.commit()
    assert "písemná žádost" in z.popis
    assert sorted((r.role, r.jednotka) for r in z.radky) == [
        ("prijmy_vlastniku", "1001/6"),
        ("zalohy_dlouhodobe", "1001/6"),
    ]

    p = prijmy_vlastniku.prehled(session, PROFIL, 2026)
    j6, j3 = _jednotka(p, "1001/6"), _jednotka(p, "1001/3")
    assert (j6.do_fondu, j6.vyplaceno, j6.zbyva) == (187_200, 0, 0)
    assert (j3.do_fondu, j3.vyplaceno, j3.zbyva) == (0, j3.prijato, 0)
    # Do potvrzení jde, co SVJ v roce dostalo, ne kdy to vlastníkům vyplatilo.
    assert j6.prijato == 187_200
    assert "prijmy-vlastniku-prevod-do-fo" not in interni_doklady.FORMULARE
