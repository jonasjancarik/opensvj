"""Počáteční stavy k 1. 1. 2026 pro ukázkové SVJ.

Zůstatky i rozpis pohledávek po jednotkách jsou vymyšlené; rozpis sedí na zůstatky účtů
a zůstatky dohromady dávají nulu (rok skončil bez zisku i ztráty).
"""

from datetime import date

import pytest

from svj import denik, pocatecni, predpisy
from svj.domena.vykazy import rozvaha
from tests.test_banka import PROFIL

# Zůstatky k 31. 12. 2025 v haléřích, kladné na straně MD.
ROZVAHOVE = {
    "221100": 42_000_000,  # provozní účet
    "221200": 25_000_000,  # účet fondu oprav
    "311200": 49_750_000,  # nedoplatky z vyúčtování 2025
    "311300": 15_268_300,  # starší pohledávky za vlastníky
    "381100": 1_850_000,  # pojistné zaplacené dopředu
    "321100": -4_500_000,  # nezaplacené faktury dodavatelů
    "955100": -119_368_300,  # fond oprav
    "955200": -10_000_000,  # fond na mimořádné opravy
}
POLOZKY = [
    pocatecni.Polozka("311200", 50_000_000, "1001/1", "Vyúčtování 2025"),
    pocatecni.Polozka("311200", -250_000, "1001/2", "Vyúčtování 2025"),
    pocatecni.Polozka("311300", 10_000_000, "1001/3", "Vyúčtování 2024"),
    pocatecni.Polozka("311300", -731_700, "1001/3", "Vyúčtování 2023", "Původní vlastník"),
    pocatecni.Polozka("311300", 6_000_000, "1001/10", "Předpisy 2025"),
]


def _stav(**zmeny) -> pocatecni.PocatecniStav:
    vychozi = {"zustatky": dict(ROZVAHOVE), "polozky": list(POLOZKY)}
    return pocatecni.PocatecniStav(rok=2026, **{**vychozi, **zmeny})


def _otevri_2026(session):
    from svj.db import Obdobi

    session.add(Obdobi(rok=2026, stav="otevrene"))
    session.flush()


def test_zaucovani_pocatecnich_stavu(session):
    _otevri_2026(session)
    z = pocatecni.zauctuj(session, PROFIL, _stav(), zauctoval="ucetni@example.test")
    session.commit()
    assert (z.doklad, z.datum.isoformat(), z.operace) == (
        "PS 2026",
        "2026-01-01",
        "otevreni-pocatecnimi-stavy",
    )
    zust = {u: c for u, c in denik.zustatky(session, 2026).items() if c or u == "961000"}
    assert zust == {**ROZVAHOVE, "961000": 0}
    assert rozvaha(zust).celkem["aktiva"] == rozvaha(ROZVAHOVE).celkem["aktiva"]

    zpet = pocatecni.nacti(session, PROFIL, 2026)
    assert zpet.zustatky == ROZVAHOVE
    assert sorted((p.ucet, p.castka, p.jednotka) for p in zpet.polozky) == sorted(
        (p.ucet, p.castka, p.jednotka) for p in POLOZKY
    )

    with pytest.raises(pocatecni.ChybaPocatku, match="už jsou zaúčtované"):
        pocatecni.zauctuj(session, PROFIL, _stav(), zauctoval="x")


def test_saldo_s_pocatecnim_stavem(session):
    _otevri_2026(session)
    pocatecni.zauctuj(session, PROFIL, _stav(), zauctoval="x")
    nast = predpisy.nacti(PROFIL)
    predpisy.vygeneruj(session, PROFIL, nast, 2026, 3, zauctoval="x")
    session.commit()
    s = {x.jednotka: x for x in predpisy.saldo(session, PROFIL, 2026)}
    assert (s["1001/1"].pocatek, s["1001/1"].saldo) == (50_000_000, 50_000_000 + 1_248_800)
    assert s["1001/2"].pocatek == -250_000
    assert s["1001/3"].pocatek == 10_000_000  # přeplatek dřívějšího vlastníka sem nepatří
    assert s["1001/6"].pocatek == 0
    assert [
        (d.jednotka, d.vlastnik, d.castka) for d in predpisy.drivejsi_vlastnici(session, 2026)
    ] == [("1001/3", "Původní vlastník", -731_700)]


@pytest.mark.parametrize(
    ("zmena", "chyba"),
    [
        ({"zustatky": {**ROZVAHOVE, "221100": ROZVAHOVE["221100"] + 1}}, "rozdíl je 0,01 Kč"),
        ({"zustatky": {**ROZVAHOVE, "518100": 100}}, "518100 není mezi rozvahovými"),
        ({"polozky": POLOZKY[2:]}, "Rozpis účtu 311200"),
        ({"polozky": [*POLOZKY, pocatecni.Polozka("311200", 100, "1001/1")]}, "Rozpis účtu 311200"),
        (
            {"polozky": [*POLOZKY[:4], pocatecni.Polozka("311300", 6_000_000, None)]},
            "chybí jednotka",
        ),
        ({"polozky": [*POLOZKY, pocatecni.Polozka("221200", 5, "1001/1")]}, "Rozpis účtu 221200"),
        ({"zustatky": {}}, "žádné zůstatky"),
    ],
)
def test_spatne_pocatecni_stavy(zmena, chyba):
    with pytest.raises(pocatecni.ChybaPocatku, match=chyba):
        pocatecni.zkontroluj(PROFIL, _stav(**zmena))


def test_rozvahove_ucty_profilu():
    ucty = pocatecni.rozvahove_ucty(PROFIL)
    assert ucty["311300"] == "pohledavky_vyuctovani_minule"
    assert ucty["324006"] == "zalohy_sluzby.TEPLO"
    assert ucty["955200"] == "zalohy_dlouhodobe_mimoradne"
    assert not {"518100", "602000", "961000", "395100"} & set(ucty)
    assert pocatecni.ucty_vlastniku(PROFIL) == {"311100", "311200", "311300"}


def test_preplatky_vlastniku_v_rozvaze_jako_zavazky(session):
    """Přeplatek vlastníka se nezapočte proti dluhům ostatních (Durec s. 30, § 7 odst. 6 ZoÚ)."""
    _otevri_2026(session)
    pocatecni.zauctuj(session, PROFIL, _stav(), zauctoval="x")
    session.commit()

    zust = denik.zustatky(session, 2026)
    vlastnici = predpisy.zustatky_vlastniku(session, 2026, date(2026, 12, 31))
    assert sorted(vlastnici["311300"]) == [-731_700, 6_000_000, 10_000_000]

    bez = rozvaha(zust)
    s = rozvaha(zust, vlastnici)
    preplatky = 250_000 + 731_700
    assert s.radky[("aktiva", "B.II")] == bez.radky[("aktiva", "B.II")] + preplatky
    assert s.radky[("pasiva", "B.III")] == bez.radky[("pasiva", "B.III")] + preplatky
    assert s.celkem["aktiva"] == s.celkem["pasiva"] == bez.celkem["aktiva"] + preplatky


def test_rozpad_zustatku_po_analytikach():
    zust = {"311200": 1000, "324100": -400, "221100": 600, "955100": -1200}
    assert rozvaha(zust).radky == rozvaha(zust, {}).radky
    # Rozpis nepokrývá celý zůstatek (1 500 − 300 ≠ 1 000): zbytek −200 je další část.
    r = rozvaha(zust, {"311200": [1500, -300]})
    assert r.radky[("aktiva", "B.II")] == 1500
    assert r.radky[("pasiva", "B.III")] == 400 + 300 + 200
    assert r.celkem == {"aktiva": 2100, "pasiva": 2100}


def test_rozvaha_pred_uzavrenim_obsahuje_vysledek_roku():
    # Náklad 300 zaplacený z banky, výnos 500 z předpisu: zisk 200 do A.II.
    zust = {"221100": -300, "311200": 500, "518200": 300, "602000": -500}
    r = rozvaha(zust)
    assert r.radky[("pasiva", "A.II")] == 200
    assert r.celkem["aktiva"] == r.celkem["pasiva"]


def test_rozvaha_majetek_zasoby_dotace_a_opravne_polozky():
    """Účty, které přinesly operace z knihy (majetek, zásoby, úvěr, dotace, opravná položka)."""
    from svj.domena import vykazy

    v = vykazy.rozvaha(
        {
            "022100": 6_400_000,  # sekačka
            "082100": -500_000,  # oprávky
            "112100": 30_000,  # zásoby
            "221100": 10_000_000,
            "311100": 3_000_000,
            "391100": -1_000_000,  # opravná položka snižuje pohledávky
            "346100": 2_000_000,  # nárok na dotaci (MD) je pohledávka
            "901100": -7_900_000,
            "951100": -8_000_000,
            "955100": -4_030_000,
        }
    )
    r = v.radky
    assert r[("aktiva", "A.II")] == 6_400_000 and r[("aktiva", "A.IV")] == -500_000
    assert r[("aktiva", "B.I")] == 30_000
    assert r[("aktiva", "B.II")] == 3_000_000 - 1_000_000 + 2_000_000
    assert r[("pasiva", "B.II")] == 8_000_000 + 4_030_000
    assert v.celkem["aktiva"] == v.celkem["pasiva"]
