"""Převod jednotky během roku: vyúčtování po vlastnických obdobích a potvrzení o dluzích
k datu převodu."""

from dataclasses import replace
from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from svj import (
    api_dluznici,
    dluznici,
    lide,
    predpisy,
    prevody,
    prihlaseni,
    vlastnicka_obdobi,
    vyuctovani_sluzeb,
    vyuctovani_spravy,
    zasilky,
)
from svj.api import app
from svj.db import Dokument, RadekZapisu
from tests.test_banka import PROFIL
from tests.test_prihlaseni import FalesneJwks, token
from tests.test_vyuctovani_spravy import _rok

NAST = predpisy.nacti(PROFIL)
KONEC = date(2026, 12, 31)
PO_OBDOBICH = replace(PROFIL, vyuctovani_pri_prevodu="po_obdobich")
KDO = "vybor@example.cz"


def _prevod(session, od=date(2026, 7, 15), jednotka="1001/3"):
    a = lide.pridej_osobu(session, lide.UdajeOsoby(jmeno="Petr Dvořák"), KDO)
    b = lide.pridej_osobu(session, lide.UdajeOsoby(jmeno="Jan Novák"), KDO)
    lide.zapis_vlastnictvi(
        session, PROFIL, jednotka, date(2020, 1, 1), [lide.ClenVlastnictvi(a.id)], "", KDO
    )
    v = lide.zapis_vlastnictvi(session, PROFIL, jednotka, od, [lide.ClenVlastnictvi(b.id)], "", KDO)
    session.commit()
    return a, b, v


def _soucty_sedi(j):
    for kod, c in j.naklady.items():
        assert sum(o.naklady.get(kod, 0) for o in j.obdobi) == c
    for kod, c in j.zalohy.items():
        assert sum(o.zalohy.get(kod, 0) for o in j.obdobi) == c
    assert sum(o.rozdil for o in j.obdobi) == j.rozdil


def test_mesice_podle_volby_predpisu():
    class V:  # stačí id a data platnosti
        def __init__(self, id, od, do):
            self.id, self.plati_od, self.plati_do = id, od, do

    historie = [V(1, date(2020, 1, 1), date(2026, 7, 14)), V(2, date(2026, 7, 15), None)]
    dosavadni = vlastnicka_obdobi.platici_mesicu(PROFIL, historie, 2026)
    assert [v.id for v in dosavadni] == [1] * 7 + [2] * 5
    novy = replace(PROFIL, predpis_mesice_prevodu="novy")
    assert [v.id for v in vlastnicka_obdobi.platici_mesicu(novy, historie, 2026)] == [1] * 6 + [
        2
    ] * 6
    # Před prvním zapsaným vlastníkem platí měsíce nejbližší známý vlastník.
    pozde = [V(3, date(2026, 3, 10), None)]
    assert vlastnicka_obdobi.platici_mesicu(PROFIL, pozde, 2026) == [pozde[0]] * 12


def test_bez_volby_dostane_vyuctovani_soucasny_vlastnik(session):
    _rok(session)
    _prevod(session)
    v = vyuctovani_spravy.spocitej(session, PROFIL, 2026)
    assert all(j.obdobi == [] for j in v.jednotky)


def test_sprava_po_obdobich(session):
    _rok(session)  # předpisy březen až prosinec
    a, b, prevod = _prevod(session)
    v = vyuctovani_spravy.spocitej(session, PO_OBDOBICH, 2026)
    j = next(x for x in v.jednotky if x.jednotka == "1001/3")
    assert [x.jednotka for x in v.jednotky if x.obdobi] == ["1001/3"]
    prodavajici, kupujici = j.obdobi
    # Červenec podle volby "dosavadni" platí ještě prodávající.
    assert prodavajici.mesice == list(range(1, 8)) and kupujici.mesice == list(range(8, 13))
    assert (prodavajici.osoby, prodavajici.soucasny) == ([a.id], False)
    assert (kupujici.osoby, kupujici.soucasny) == ([b.id], True)
    assert (prodavajici.od, prodavajici.do) == (date(2026, 1, 1), date(2026, 7, 14))
    assert (kupujici.od, kupujici.do) == (date(2026, 7, 15), KONEC)
    _soucty_sedi(j)
    # Zálohy: oba platili pět měsíců předpisu (březen až červenec, srpen až prosinec).
    assert sum(prodavajici.zalohy.values()) == sum(kupujici.zalohy.values())
    # Náklady se dělí podle měsíců: prodávající nese 7/12 správy (rovným dílem).
    assert abs(prodavajici.naklady["SPRAVA"] - j.naklady["SPRAVA"] * 7 / 12) <= 1

    vyuctovani_spravy.zauctuj(session, PO_OBDOBICH, NAST, 2026, zauctoval="x", dnes=KONEC)
    session.commit()
    radky = session.scalars(
        select(RadekZapisu).where(
            RadekZapisu.jednotka == "1001/3", RadekZapisu.role.like("pohledavky_%")
        )
    ).all()
    vysledky = {
        r.protistrana: (r.castka if r.strana == "md" else -r.castka)
        for r in radky
        if r.zapis.operace == vyuctovani_spravy.OPERACE
    }
    assert vysledky == {"Petr Dvořák": prodavajici.rozdil, None: kupujici.rozdil}
    # Výsledek prodávajícího se vede u dřívějších vlastníků, v dluzích jednotky je jen kupující.
    drivejsi = predpisy.drivejsi_vlastnici(session, 2026)
    assert [(d.jednotka, d.vlastnik, d.castka) for d in drivejsi] == [
        ("1001/3", "Petr Dvořák", prodavajici.rozdil)
    ]
    dluh = next(
        d for d in dluznici.prehled(session, PROFIL, NAST, 2026, KONEC) if d.jednotka == "1001/3"
    )
    vyuctovani = [p for p in dluh.polozky if p.popis.startswith("Vyúčtování")]
    assert sum(p.castka for p in vyuctovani) == max(kupujici.rozdil, 0)
    # Po zaúčtování dává výpočet stejná čísla.
    po = vyuctovani_spravy.spocitej(session, PO_OBDOBICH, 2026)
    assert [o.rozdil for o in next(x for x in po.jednotky if x.jednotka == "1001/3").obdobi] == [
        prodavajici.rozdil,
        kupujici.rozdil,
    ]


def test_sluzby_po_obdobich_novy_vlastnik(session):
    from tests.test_vyuctovani_sluzeb import _rok as rok_sluzeb
    from tests.test_vyuctovani_sluzeb import _teplo, _vodomery

    rok_sluzeb(session)
    _vodomery(session)
    _teplo(session)
    _prevod(session, od=date(2026, 9, 10))
    profil = replace(PO_OBDOBICH, predpis_mesice_prevodu="novy")
    v = vyuctovani_sluzeb.spocitej(session, profil, NAST, 2026, KONEC)
    j = next(x for x in v.jednotky if x.jednotka == "1001/3")
    prodavajici, kupujici = j.obdobi
    # Září podle volby "novy" platí už kupující.
    assert prodavajici.mesice == list(range(1, 9)) and kupujici.mesice == list(range(9, 13))
    _soucty_sedi(j)
    z = vyuctovani_sluzeb.zauctuj(session, profil, NAST, 2026, zauctoval="x", dnes=KONEC)
    session.commit()
    jmena = {
        r.protistrana
        for r in z.radky
        if r.jednotka == "1001/3" and r.role.startswith("pohledavky_")
    }
    assert jmena == {"Petr Dvořák", None}


def test_cast_vyuctovani_jde_prodavajicimu(session):
    a, b, _ = _prevod(session)
    davka = zasilky.priprav(
        session,
        "vyuctovani_spravy",
        "vyuctovani_spravy:2026",
        "Vyúčtování",
        [
            zasilky.NovyDokument("1001/3", "<article>prodávající</article>", [a.id]),
            zasilky.NovyDokument("1001/3", "<article>kupující</article>"),
        ],
        KDO,
        dnes=date(2026, 11, 1),
    )
    z = zasilky.v_davce(session, davka)
    assert [x.jmeno for x in z] == ["Petr Dvořák", "Jan Novák"]
    # Doručení prodávajícímu nespouští lhůty vyúčtování jednotky.
    zasilky.zapis_doruceni(session, z[0].id, date(2026, 11, 3), "dodejka", KDO)
    assert zasilky.doruceni_jednotek(session, "vyuctovani_spravy:2026") == {}
    zasilky.zapis_doruceni(session, z[1].id, date(2026, 11, 5), "dodejka", KDO)
    assert zasilky.doruceni_jednotek(session, "vyuctovani_spravy:2026") == {
        "1001/3": date(2026, 11, 5)
    }
    dok = session.get(Dokument, z[0].dokument_id)
    assert dok.osoby == [a.id]

    cizi = lide.pridej_osobu(session, lide.UdajeOsoby(jmeno="Někdo jiný"), KDO)
    try:
        zasilky.priprav(
            session,
            "vyuctovani_spravy",
            "k",
            "n",
            [zasilky.NovyDokument("1001/3", "<p>x</p>", [cizi.id])],
            KDO,
        )
    except zasilky.ChybaZasilky as e:
        assert "nevlastnil" in str(e)
    else:
        raise AssertionError("dokument nesmí jít někomu, kdo jednotku nevlastnil")


def _predpisy(session, mesice):
    from tests.test_pocatecni import _otevri_2026

    _otevri_2026(session)
    for m in mesice:
        predpisy.vygeneruj(session, PROFIL, NAST, 2026, m, zauctoval="x", dnes=date(2026, m, 1))
    session.commit()


def test_potvrzeni_k_datu_prevodu(session):
    _predpisy(session, range(3, 10))
    a, _, v = _prevod(session, od=date(2026, 7, 15))
    p = prevody.potvrzeni_k_prevodu(session, PROFIL, NAST, v.id, dnes=date(2026, 9, 20))
    assert p.k_datu == date(2026, 7, 14)
    # Březen až červenec (červenec podle volby "dosavadni"), srpen a září už ne.
    assert [x.popis for x in p.dluhy.polozky] == [
        f"Zálohy za {m} 2026" for m in ("březen", "duben", "květen", "červen", "červenec")
    ]
    assert [c.osoba_id for c in p.predchozi.vlastnici] == [a.id]

    novy = replace(PROFIL, predpis_mesice_prevodu="novy")
    p = prevody.potvrzeni_k_prevodu(session, novy, NAST, v.id, dnes=date(2026, 9, 20))
    assert p.dluhy.polozky[-1].popis == "Zálohy za červen 2026"

    # Převod zapsaný dopředu: potvrzení je k dnešku.
    p = prevody.potvrzeni_k_prevodu(session, PROFIL, NAST, v.id, dnes=date(2026, 6, 2))
    assert p.k_datu == date(2026, 6, 2)


def test_api_potvrzeni_k_datu_prevodu(session, monkeypatch):
    _predpisy(session, range(3, 6))
    a, _, v = _prevod(session, od=date(2026, 4, 15))
    monkeypatch.setattr(prihlaseni, "_jwks", lambda: FalesneJwks())
    monkeypatch.setattr(api_dluznici, "sezeni", lambda: sessionmaker(session.get_bind()))
    klient = TestClient(app)
    klient.headers["Authorization"] = f"Bearer {token()}"
    d = klient.get(f"/api/dluznici/prevod/{v.id}").json()
    assert d["k_datu"] == "2026-04-14"
    assert d["osoby"] == [a.id]
    (j,) = d["jednotky"]
    assert j["jednotka"] == "1001/3"
    assert [x["jmeno"] for x in j["vlastnici"]] == ["Petr Dvořák"]
    assert [x["popis"] for x in j["polozky"]] == ["Zálohy za březen 2026", "Zálohy za duben 2026"]
    assert klient.get("/api/dluznici/prevod/999999").status_code == 404
