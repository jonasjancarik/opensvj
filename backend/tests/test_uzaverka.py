"""Uzávěrka roku: kontrolní seznam, inventurní soupisy, daň z příjmů a příloha."""

from datetime import date

from svj import denik, pocatecni, predpisy, uzaverka, vyuctovani_spravy
from svj.domena import katalog
from tests.test_banka import PROFIL
from tests.test_pocatecni import _otevri_2026, _stav
from tests.test_vyuctovani_spravy import _faktura

NAST = predpisy.nacti(PROFIL)
KONEC = date(2026, 12, 31)


def _stavy(k):
    return {x.nazev: x.stav for x in k}


def test_kontrolni_seznam(session):
    _otevri_2026(session)
    session.commit()
    k = _stavy(uzaverka.kontroly(session, PROFIL, NAST, 2026, KONEC))
    assert k["Počáteční stavy k 1. 1. jsou zaúčtované"] == "chybi"
    assert k["Předpisy záloh za všechny měsíce jsou zaúčtované"] == "chybi"
    assert k["Vnitřní zúčtování je vyrovnané"] == "hotovo"

    pocatecni.zauctuj(session, PROFIL, _stav(), zauctoval="x")
    for m in range(3, 13):
        predpisy.vygeneruj(session, PROFIL, NAST, 2026, m, zauctoval="x", dnes=KONEC)
    _faktura(session, "POJISTENI", 4_500_000, date(2026, 3, 5))
    vyuctovani_spravy.zauctuj(session, PROFIL, NAST, 2026, zauctoval="x", dnes=KONEC)
    session.commit()
    k = _stavy(uzaverka.kontroly(session, PROFIL, NAST, 2026, KONEC))
    assert k["Počáteční stavy k 1. 1. jsou zaúčtované"] == "hotovo"
    assert k["Předpisy záloh za všechny měsíce jsou zaúčtované"] == "hotovo"
    assert k["Zálohy na správu domu jsou vyúčtované"] == "hotovo"
    assert k["Zálohy na služby jsou vyúčtované"] == "rucne"  # vyúčtování služeb zatím chybí
    assert k["Nezaplacené faktury odpovídají závazkům"] == "info"


def test_nepotvrzeny_postup_je_v_kontrolnim_seznamu(session):
    """Postup ve stavu `overit` se zaúčtuje a uzávěrka ho jen připomene k posouzení."""
    _otevri_2026(session)
    op = katalog.nacti()["urok-a-srazkova-dan"]
    zapis = denik.zauctuj(
        session,
        PROFIL,
        op,
        {"ucet": "provozni", "urok_hruby": "100.00", "dan": "15.00"},
        datum=date(2026, 6, 30),
        popis="úrok",
        doklad="BV",
        zauctoval="x",
    )
    session.commit()
    k = {x.kod: x for x in uzaverka.kontroly(session, PROFIL, NAST, 2026, KONEC)}
    assert k["postupy-k-overeni"].stav == "rucne"
    assert f"{op.nazev} (1×)" in k["postupy-k-overeni"].detail

    denik.storno(session, zapis.id, duvod="omyl", zauctoval="x")
    session.commit()
    k = {x.kod: x for x in uzaverka.kontroly(session, PROFIL, NAST, 2026, KONEC)}
    assert "postupy-k-overeni" not in k


def test_soupisy_a_vykazy(session):
    _otevri_2026(session)
    pocatecni.zauctuj(session, PROFIL, _stav(), zauctoval="x")
    _faktura(session, "POJISTENI", 4_500_000, date(2026, 3, 5))
    session.commit()
    s = {x.ucet: x for x in uzaverka.soupisy(session, PROFIL, 2026, KONEC)}
    zust = denik.zustatky(session, 2026, KONEC)
    assert all(x.zustatek == zust[u] for u, x in s.items())
    assert "výpisu" in s["221100"].zpusob
    # Pohledávky po jednotkách včetně dřívějšího vlastníka; součet sedí na zůstatek účtu.
    assert sum(p.castka for p in s["311300"].polozky) == zust["311300"]
    assert any("dřívější vlastník" in p.popis for p in s["311300"].polozky)
    # Závazky po fakturách: nová faktura zvlášť, převzatý zůstatek zvlášť.
    assert sum(p.castka for p in s["321100"].polozky) == zust["321100"]
    assert any("Dodavatel POJISTENI" in p.popis for p in s["321100"].polozky)
    assert "395100" not in s and "961000" not in s

    rozvaha, vzz = uzaverka.vykazy_roku(session, 2026, KONEC)
    radky = {(r.strana, r.radek): r.nazev for r in uzaverka.vykaz_radky(rozvaha)}
    assert radky[("pasiva", "B.III")] == "Krátkodobé závazky"
    assert rozvaha.celkem["aktiva"] == rozvaha.celkem["pasiva"]


def test_dan_z_prijmu(session):
    _otevri_2026(session)
    session.commit()
    assert uzaverka.dan(session, PROFIL, 2026).musi_podat is False

    op = katalog.nacti()["urok-a-srazkova-dan"]
    denik.zauctuj(
        session,
        PROFIL,
        op,
        {"ucet": "provozni", "urok_hruby": "100.00", "dan": "15.00"},
        datum=date(2026, 6, 30),
        popis="úrok",
        doklad="BV",
        zauctoval="x",
    )
    session.commit()
    d = uzaverka.dan(session, PROFIL, 2026)
    assert [v.zdaneni for v in d.vynosy] == ["srazkova"] and d.musi_podat is False

    denik.zauctuj(
        session,
        PROFIL,
        op,
        {},
        datum=date(2026, 7, 1),
        popis="pacht",
        doklad="BV",
        zauctoval="x",
        radky=[
            katalog.Radek("md", "banka.provozni", 120_000, {}),
            katalog.Radek("d", "vynosy.pacht", 120_000, {}),
        ],
    )
    session.commit()
    d = uzaverka.dan(session, PROFIL, 2026)
    assert d.musi_podat is True
    pacht = next(v for v in d.vynosy if "602100" in v.popis)
    assert pacht.zdaneni == "predmetne" and "s. 77–79" in pacht.poznamka


def test_priloha(session):
    _otevri_2026(session)
    pocatecni.zauctuj(session, PROFIL, _stav(), zauctoval="x")
    session.commit()
    o = {x.nadpis: x.odstavce for x in uzaverka.priloha(session, PROFIL, NAST, 2026, KONEC)}
    assert f"IČ {PROFIL.ico}" in o["Údaje o účetní jednotce"][0]
    assert any("zálohově" in t for t in o["Účetní metody"])
    assert "k 1. 1. 1 293 683,00 Kč" in o["Významné položky rozvahy a výsledovky"][0]
    assert any("[doplňte]" in t for t in o["Ostatní údaje"])


def test_operace_z_knihy_jdou_zauctovat_a_vykazat(session):
    """Úrok z prodlení a dotace z katalogu: zápis projde, rozvaha sedí, daň je rozlišená."""
    _otevri_2026(session)
    session.commit()
    ops = katalog.nacti()
    for op, vstupy in [
        ("urok-z-prodleni", {"jednotka": "1001/3", "castka": "1000.00"}),
        ("dotace-rozhodnuti", {"poskytovatel": "mesto", "castka": "50000.00"}),
        ("dotace-pouziti", {"poskytovatel": "mesto", "castka": "50000.00"}),
    ]:
        denik.zauctuj(
            session, PROFIL, ops[op], vstupy, datum=date(2026, 6, 1), popis=op, doklad="ID",
            zauctoval="x",
        )  # fmt: skip
    session.commit()

    vynosy = {v.popis: v.zdaneni for v in uzaverka.dan(session, PROFIL, 2026).vynosy}
    assert vynosy["Úroky z prodlení od vlastníků (641100)"] == "predmetne"
    assert vynosy["Dotace (691100)"] == "nepredmetne"
    rozvaha, _ = uzaverka.vykazy_roku(session, 2026, KONEC)
    assert rozvaha.celkem["aktiva"] == rozvaha.celkem["pasiva"]
    assert rozvaha.radky[("aktiva", "B.II")] == 100_000 + 5_000_000  # 311400 a 378200
