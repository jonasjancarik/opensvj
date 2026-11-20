"""Oznámení o nové výši záloh: porovnání verzí předpisu po jednotkách."""

import copy
from datetime import date

import pytest

from svj import oznameni, predpisy
from tests.test_banka import PROFIL

NAST = predpisy.nacti(PROFIL)


def _se_zmenou():
    """Druhá verze od 1. 7. 2026: dražší teplo u 1001/6, pojištění zrušené, nový úklid schodů."""
    n = copy.deepcopy(NAST)
    v = copy.deepcopy(n.verze[0])
    v.plati_od, v.zdroj = date(2026, 7, 1), "rozhodnutí výboru"
    v.slozky = [s for s in v.slozky if s.kod != "POJISTENI"]
    v.slozky.append(
        predpisy.Slozka("SCHODY", "Úklid schodů", "zalohy_sluzby.UKLID", "jednotka", 120_000)
    )
    v.pevne = {**v.pevne, "1001/6": {**v.pevne["vychozi"], "TEPLO": 300_000}}
    n.verze.append(v)
    return n


def test_prvni_verze_nema_s_cim_porovnat():
    o = oznameni.oznameni(PROFIL, NAST, date(2026, 3, 1))
    assert o.predchozi_od is None and o.dorucit_do == date(2026, 2, 28)
    j = next(x for x in o.jednotky if x.jednotka == "1001/6")
    assert j.puvodne == 0 and j.nove == predpisy.mesicni_celkem(PROFIL, NAST, 2026, 3)["1001/6"]


def test_zmeny_po_slozkach():
    o = oznameni.oznameni(PROFIL, _se_zmenou(), date(2026, 7, 1))
    assert o.predchozi_od == date(2026, 3, 1) and o.dorucit_do == date(2026, 6, 30)
    j = {x.jednotka: x for x in o.jednotky}
    s6 = {s.kod: s for s in j["1001/6"].slozky}
    assert (s6["TEPLO"].puvodne, s6["TEPLO"].nove) == (260_000, 300_000)
    assert (s6["POJISTENI"].puvodne, s6["POJISTENI"].nove) == (40_000, None)
    assert (s6["SCHODY"].puvodne, s6["SCHODY"].nove) == (None, 10_000)
    assert j["1001/6"].nove - j["1001/6"].puvodne == 300_000 - 260_000 - 40_000 + 10_000
    s1 = {s.kod: s for s in j["1001/1"].slozky}
    assert s1["TEPLO"].puvodne == s1["TEPLO"].nove  # ostatním se teplo nemění
    assert all(x.zmenena for x in o.jednotky)


def test_neznama_verze():
    with pytest.raises(oznameni.ChybaOznameni):
        oznameni.oznameni(PROFIL, NAST, date(2026, 4, 1))
