"""Dlužníci: platby se započítají na nejdřív splatné dluhy (OZ § 1932)."""

from datetime import date

from svj import denik, dluznici, pocatecni, predpisy
from svj.domena import katalog
from tests.test_banka import PROFIL
from tests.test_pocatecni import _otevri_2026, _stav

NAST = predpisy.nacti(PROFIL)


def _platba(session, jednotka, castka, datum):
    denik.zauctuj(
        session,
        PROFIL,
        katalog.nacti()["uhrada-predpisu"],
        {"ucet": "provozni", "jednotka": jednotka, "castka": f"{castka / 100:.2f}"},
        datum=datum,
        popis="platba",
        doklad="BV",
        zauctoval="x",
    )


def test_platby_na_nejstarsi_dluhy(session):
    _otevri_2026(session)
    pocatecni.zauctuj(session, PROFIL, _stav(), zauctoval="x")
    for m in (3, 4, 5):
        predpisy.vygeneruj(session, PROFIL, NAST, 2026, m, zauctoval="x", dnes=date(2026, 5, 1))
    mesic = predpisy.mesicni_celkem(PROFIL, NAST, 2026, 3)
    # 1001/1: dluh z minulých let 500 000 Kč, zaplatí ho celý a k tomu březen.
    _platba(session, "1001/1", 50_000_000 + mesic["1001/1"], date(2026, 3, 20))
    # 1001/2: přeplatek 1 702 Kč z minulých let pokryje část března, jinak neplatí.
    # 1001/6: platí včas a celé.
    for m in (3, 4, 5):
        _platba(session, "1001/6", predpisy.mesicni_celkem(PROFIL, NAST, 2026, m)["1001/6"],
                date(2026, m, 10))  # fmt: skip
    session.commit()

    vse = {d.jednotka: d for d in dluznici.prehled(session, PROFIL, NAST, 2026, date(2026, 5, 10))}
    saldo = {s.jednotka: s.saldo for s in predpisy.saldo(session, PROFIL, 2026)}
    assert {j: d.saldo for j, d in vse.items()} == saldo

    d1 = vse["1001/1"]
    assert [(p.popis, p.zbyva) for p in d1.polozky] == [
        ("Zálohy za duben 2026", mesic["1001/1"]),
        ("Zálohy za květen 2026", mesic["1001/1"]),
    ]
    assert (d1.po_splatnosti, d1.nesplatne, d1.od) == (
        mesic["1001/1"],
        mesic["1001/1"],
        date(2026, 4, 15),
    )
    # Úrok jen z dubna (25 dní při 11,5 % ročně), květen ještě není splatný.
    assert d1.urok == round(mesic["1001/1"] * 0.115 * 25 / 365) and not d1.urok_neuplny

    d2 = vse["1001/2"]
    assert d2.polozky[0].popis == "Zálohy za březen 2026"
    assert d2.polozky[0].zbyva == mesic["1001/2"] - 250_000
    assert d2.od == date(2026, 3, 15) and not d2.z_minulych_let

    d3 = vse["1001/3"]  # dluh z minulých let, přeplatek dřívějšího vlastníka se nepočítá
    assert d3.z_minulych_let and d3.polozky[0].zbyva == 10_000_000 and d3.od is None
    assert d3.urok_neuplny  # u dluhu z minulých let neznáme splatnost
    assert vse["1001/6"].polozky == [] and vse["1001/6"].preplatek == 0


def test_dluhy_z_minulych_let_od_nejstarsiho(session):
    _otevri_2026(session)
    pocatecni.zauctuj(session, PROFIL, _stav(), zauctoval="x")
    session.commit()
    _platba(session, "1001/3", 100, date(2026, 2, 1))
    d = {x.jednotka: x for x in dluznici.prehled(session, PROFIL, NAST, 2026, date(2026, 2, 2))}
    # 311300 (dřívější roky) se platí před 311200 (vyúčtování minulého roku).
    assert [p.popis for p in d["1001/3"].polozky] == ["Vyúčtování 2024"]
    assert d["1001/3"].polozky[0].zbyva == 10_000_000 - 100


def test_predepsany_urok_se_nepocita_znovu(session):
    """Po předpisu úroku z prodlení se úrok počítá jen za dobu potom; předepsaný úrok je
    vedený zvlášť, dokud ho vlastník nezaplatí."""
    _otevri_2026(session)
    predpisy.vygeneruj(session, PROFIL, NAST, 2026, 3, zauctoval="x", dnes=date(2026, 5, 1))
    mesic = predpisy.mesicni_celkem(PROFIL, NAST, 2026, 3)["1001/1"]

    def prehled(dnes):
        vse = dluznici.prehled(session, PROFIL, NAST, 2026, dnes)
        return next(d for d in vse if d.jednotka == "1001/1")

    pred = prehled(date(2026, 5, 15))
    assert pred.urok == round(mesic * 0.115 * 61 / 365) and pred.urok_do is None  # 16. 3.–15. 5.

    ops = katalog.nacti()
    for op, vstupy, datum in [
        ("urok-z-prodleni", {"castka": f"{pred.urok / 100:.2f}"}, date(2026, 5, 15)),
        ("uhrada-uroku-z-prodleni", {"castka": "1.00", "ucet": "provozni"}, date(2026, 5, 20)),
    ]:
        denik.zauctuj(
            session, PROFIL, ops[op], {"jednotka": "1001/1", **vstupy}, datum=datum,
            popis=op, doklad="ID", zauctoval="x",
        )  # fmt: skip
    session.commit()

    po = prehled(date(2026, 5, 25))
    assert po.urok_do == date(2026, 5, 15)
    assert po.urok == round(mesic * 0.115 * 10 / 365)  # jen 16.–25. 5.
    assert po.sankce == pred.urok - 100
    assert po.saldo == pred.saldo  # úrok se do dluhů na zálohách nepočítá
