"""Storno zápisu: protizápis ke stejnému datu a možnost zaúčtovat věc znovu."""

import pytest
from sqlalchemy import select

from svj import banka, denik, pocatecni, predpisy
from svj.db import BankovniPohyb, ParovaniPohybu
from tests.test_banka import PROFIL, _nahraj, _pohyby
from tests.test_pocatecni import _otevri_2026, _stav

NAST = predpisy.nacti(PROFIL)


def test_storno_predpisu_a_nove_zauctovani(session):
    _otevri_2026(session)
    z = predpisy.vygeneruj(session, PROFIL, NAST, 2026, 3, zauctoval="x")
    session.commit()
    celkem = sum(predpisy.mesicni_celkem(PROFIL, NAST, 2026, 3).values())

    s = denik.storno(session, z.id, duvod="  špatný počet osob ", zauctoval="ucetni")
    session.commit()
    assert (s.operace, s.opravuje_zapis, s.datum, s.doklad) == (
        "storno",
        z.id,
        z.datum,
        "ID 1/2026",
    )
    assert s.popis.endswith("Důvod: špatný počet osob")
    assert {(r.strana, r.ucet, r.castka) for r in s.radky} == {
        ("d" if r.strana == "md" else "md", r.ucet, r.castka) for r in z.radky
    }
    assert not any(denik.zustatky(session, 2026).values())
    assert predpisy.dalsi_k_zauctovani(session, NAST, 2026) == 3
    assert predpisy.saldo(session, PROFIL, 2026)[0].predepsano == 0

    znovu = predpisy.vygeneruj(session, PROFIL, NAST, 2026, 3, zauctoval="x")
    assert znovu.id != z.id and znovu.idempotencni_klic == "predpis:2026-03#2"
    assert predpisy.vygeneruj(session, PROFIL, NAST, 2026, 3, zauctoval="x").id == znovu.id
    assert predpisy.zauctovane_mesice(session, 2026) == {3: znovu}
    assert sum(x.predepsano for x in predpisy.saldo(session, PROFIL, 2026)) == celkem


def test_storno_jen_jednou_a_s_duvodem(session):
    _otevri_2026(session)
    z = predpisy.vygeneruj(session, PROFIL, NAST, 2026, 3, zauctoval="x")
    with pytest.raises(denik.ChybaUctovani, match="proč"):
        denik.storno(session, z.id, duvod=" ", zauctoval="x")
    s = denik.storno(session, z.id, duvod="chyba", zauctoval="x")
    with pytest.raises(denik.ChybaUctovani, match="už je stornovaný"):
        denik.storno(session, z.id, duvod="chyba", zauctoval="x")
    with pytest.raises(denik.ChybaUctovani, match="sám storno"):
        denik.storno(session, s.id, duvod="chyba", zauctoval="x")


def test_storno_platby_vrati_pohyb_k_zauctovani(session):
    _nahraj(session)
    p = _pohyby(session)["101"]
    par = banka.zauctuj_pohyb(
        session, PROFIL, p.id, "uhrada-predpisu", {"jednotka": "1001/5"}, zauctoval="x"
    )
    session.commit()
    with pytest.raises(banka.ChybaBanky, match="už je zaúčtovaný"):
        banka.zauctuj_pohyb(session, PROFIL, p.id, "poplatek-banky", {}, zauctoval="x")

    denik.storno(session, par.zapis_id, duvod="jiná jednotka", zauctoval="x")
    session.commit()
    session.expire_all()
    p = session.get(BankovniPohyb, p.id)
    assert p.parovani is None
    nezauctovane = session.scalars(
        select(BankovniPohyb.id).where(
            ~select(ParovaniPohybu.pohyb_id).where(banka.zauctovano(BankovniPohyb.id)).exists()
        )
    ).all()
    assert p.id in nezauctovane

    nove = banka.zauctuj_pohyb(
        session, PROFIL, p.id, "uhrada-predpisu", {"jednotka": "1001/6"}, zauctoval="x"
    )
    session.commit()
    session.expire_all()
    p = session.get(BankovniPohyb, p.id)
    assert len(p.parovani_vse) == 2
    assert p.parovani.id == nove.id and p.parovani.vstupy == {"jednotka": "1001/6"}


def test_storno_pocatecnich_stavu(session):
    _otevri_2026(session)
    z = pocatecni.zauctuj(session, PROFIL, _stav(), zauctoval="x")
    denik.storno(session, z.id, duvod="opsáno z neúplné rozvahy", zauctoval="x")
    assert pocatecni.zauctovany(session, 2026) is None
    assert pocatecni.nacti(session, PROFIL, 2026) is None
    assert predpisy.saldo(session, PROFIL, 2026)[0].pocatek == 0
    znovu = pocatecni.zauctuj(session, PROFIL, _stav(), zauctoval="x")
    assert pocatecni.zauctovany(session, 2026).id == znovu.id
