"""Podíly na společných částech s platností v čase."""

import dataclasses
from datetime import date
from fractions import Fraction

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from svj import api_podily, audit, oznameni, podily, predpisy, prihlaseni, vyuctovani_spravy
from svj.api import app
from svj.db import Obdobi
from tests.test_banka import PROFIL
from tests.test_prihlaseni import FalesneJwks, token
from tests.test_vyuctovani_spravy import KONEC, _faktura, _rok

ZE_SOUBORU = {j.oznaceni: j.podil_text for j in PROFIL.udaje_jednotek}
PROHLASENI = "Změna prohlášení vlastníka, vklad V-1234/2026"


def _nove(**zmeny: str) -> dict[str, str]:
    """Podíly ze souboru se změnami, např. 1001/1 o 100/8600 víc a 1001/12 o tolik méně."""
    return ZE_SOUBORU | {k.replace("_", "/"): v for k, v in zmeny.items()}


# 1001/1 má o 100/8600 víc, 1001/12 o 100/8600 méně (třeba přesun sklepa mezi jednotkami).
PRESUN = _nove(**{"1001_1": "643/8600", "1001_12": "235/8600"})


def _otevri(session, rok=2026):
    session.add(Obdobi(rok=rok, stav="otevrene"))
    session.flush()


def _sprava_podle_podilu(plati_od: date) -> predpisy.Verze:
    """Verze předpisu, ve které se pojištění 4 000 Kč měsíčně dělí podle podílů."""
    v = predpisy.nacti(PROFIL).verze[-1]
    slozky = [
        dataclasses.replace(s, klic="podil", sazba=400_000) if s.kod == "POJISTENI" else s
        for s in v.slozky
    ]
    pevne = {j: {k: c for k, c in x.items() if k != "POJISTENI"} for j, x in v.pevne.items()}
    return dataclasses.replace(
        v, plati_od=plati_od, zdroj="Shromáždění", slozky=slozky, pevne=pevne
    )


def test_podily_po_mesicich():
    zaklad = podily.ze_souboru(PROFIL).zakladni
    zmena = podily.Zmena(date(2026, 7, 15), podily.zkontroluj_sadu(PROFIL, PRESUN), PROHLASENI)
    p = podily.Podily(zaklad, [zmena])
    # Podle prohlášení platí od 15. 7., předpis s nimi počítá od prvního celého měsíce.
    assert p.k_datu(date(2026, 7, 15)).texty["1001/1"] == "643/8600"
    assert p.k_mesici(2026, 7).texty["1001/1"] == "543/8600"
    assert p.k_mesici(2026, 8).texty["1001/1"] == "643/8600"
    assert [(od, do) for od, do, _ in p.obdobi_roku(2026)] == [(1, 7), (8, 12)]
    za_rok = p.v_roce(2026)
    assert sum(za_rok.values()) == 1
    assert za_rok["1001/1"] == Fraction(7 * 543 + 5 * 643, 12 * 8600)
    assert not p.zmeny_v_roce(2027) and p.v_roce(2027)["1001/1"] == Fraction(643, 8600)
    # Zápis zůstane, jak je v prohlášení; zlomek by se zkrátil na 359/4300.
    assert zaklad.texty["1001/2"] == "718/8600" and zaklad.podily["1001/2"] == Fraction(359, 4300)


@pytest.mark.parametrize(
    ("zmena", "chyba"),
    [
        ({"1001/1": "643/8600"}, "přebývá 100/8600"),
        ({"1001/1": "542/8600"}, "chybí 1/8600"),
        ({"1001/1": ""}, "Chybí podíl jednotky 1001/1"),
        ({"1001/1": "0,063"}, "Jednotka 1001/1: .*zlomek"),
        ({"1001/1": "0/8600"}, "větší než nula"),
        ({"1001/99": "1/2"}, "1001/99 SVJ nemá"),
    ],
)
def test_spatne_podily(zmena, chyba):
    with pytest.raises(podily.ChybaPodilu, match=chyba):
        podily.zkontroluj_sadu(PROFIL, ZE_SOUBORU | zmena)


def test_ulozeni_a_kontroly(session):
    _otevri(session)
    with pytest.raises(podily.ChybaPodilu, match="podle čeho"):
        podily.uloz(session, PROFIL, date(2026, 7, 1), PRESUN, " ", "x")
    with pytest.raises(podily.ChybaPodilu, match="stejné jako dosud"):
        podily.uloz(session, PROFIL, date(2026, 7, 1), ZE_SOUBORU, PROHLASENI, "x")
    podily.uloz(session, PROFIL, date(2026, 7, 1), PRESUN, PROHLASENI, "x")
    session.commit()
    with pytest.raises(podily.ChybaPodilu, match="už je zapsaná"):
        podily.uloz(session, PROFIL, date(2026, 7, 1), ZE_SOUBORU, PROHLASENI, "x")
    # Změna od 10. 6. by se v předpisu projevila až od července, kdy už začíná jiná.
    with pytest.raises(podily.ChybaPodilu, match="jen jedna změna"):
        podily.uloz(session, PROFIL, date(2026, 6, 10), ZE_SOUBORU, PROHLASENI, "x")

    # Posunutí data přepíše tutéž změnu.
    podily.uloz(session, PROFIL, date(2026, 9, 1), PRESUN, PROHLASENI, "y", date(2026, 7, 1))
    session.commit()
    [z] = podily.nacti(session, PROFIL).zmeny
    assert (z.plati_od, z.upravil, z.sada.texty["1001/12"]) == (date(2026, 9, 1), "y", "235/8600")

    historie = list(reversed(audit.zaznamy(session, druh="zmena_podilu")))
    assert [(h.akce, h.klic) for h in historie] == [
        ("pridani", "2026-07-01"),
        ("smazani", "2026-07-01"),
        ("pridani", "2026-09-01"),
    ]
    rozdily = {r.pole: (r.pred, r.po) for r in audit.rozdily(historie[0])}
    assert rozdily["Podíl jednotky 1001/1"] == ("—", "643/8600")
    assert rozdily["Podle čeho"] == ("—", PROHLASENI)

    podily.smaz(session, date(2026, 9, 1))
    session.commit()
    assert podily.nacti(session, PROFIL).zmeny == []


def test_zauctovane_predpisy_a_uzavreny_rok(session):
    _rok(session)  # předpisy březen až prosinec 2026 jsou zaúčtované
    with pytest.raises(podily.ChybaPodilu, match="nejdřív od 1. 1. 2027"):
        podily.uloz(session, PROFIL, date(2026, 12, 1), PRESUN, PROHLASENI, "x")
    # Od 15. 12. jde: předpis s novými podíly počítá až od ledna.
    podily.uloz(session, PROFIL, date(2026, 12, 15), PRESUN, PROHLASENI, "x")
    podily.smaz(session, date(2026, 12, 15))
    session.add(Obdobi(rok=2027, stav="uzavrene"))
    session.flush()
    with pytest.raises(podily.ChybaPodilu, match="Rok 2027 je uzavřený"):
        podily.uloz(session, PROFIL, date(2027, 2, 1), PRESUN, PROHLASENI, "x")


def test_predpis_od_zmeny_podilu(session):
    _otevri(session)
    _otevri(session, 2027)
    predpisy.uloz_verzi(session, PROFIL, _sprava_podle_podilu(date(2027, 1, 1)), "x", None)
    podily.uloz(session, PROFIL, date(2027, 6, 15), PRESUN, PROHLASENI, "x")
    session.commit()
    nast = predpisy.nacti(PROFIL, session)

    cerven = predpisy.castky_mesice(PROFIL, nast, 2027, 6)
    cervenec = predpisy.castky_mesice(PROFIL, nast, 2027, 7)
    # 4 000 Kč × 543/8600 = 252,56 → 253 Kč; × 643/8600 = 299,07 → 299 Kč (celé koruny).
    assert (cerven["1001/1"]["POJISTENI"], cervenec["1001/1"]["POJISTENI"]) == (25_300, 29_900)
    assert cervenec["1001/12"]["POJISTENI"] < cerven["1001/12"]["POJISTENI"]
    assert cervenec["1001/5"]["POJISTENI"] == cerven["1001/5"]["POJISTENI"]
    for mesic in (cerven, cervenec):  # součet přesně sedí na částku za dům
        assert sum(x["POJISTENI"] for x in mesic.values()) == 400_000

    # Zaúčtovaný předpis za červenec je s novými podíly.
    for m in range(1, 8):
        z = predpisy.vygeneruj(session, PROFIL, nast, 2027, m, zauctoval="x", dnes=date(2027, 7, 1))
    radky = [r for r in z.radky if r.jednotka == "1001/1" and r.sluzba == "POJISTENI"]
    assert [r.castka for r in radky if r.strana == "d"] == [29_900]

    # Změna podílů je změna předpisu: vlastníkům se oznamuje jako nová verze.
    assert nast.zmeny_predpisu() == [date(2026, 3, 1), date(2027, 1, 1), date(2027, 7, 1)]
    o = oznameni.oznameni(PROFIL, nast, date(2027, 7, 1))
    assert o.predchozi_od == date(2027, 1, 1) and o.zdroj == PROHLASENI
    assert o.zmena_podilu is not None and o.zmena_podilu.plati_od == date(2027, 6, 15)
    j = {x.jednotka: x for x in o.jednotky}
    assert (j["1001/1"].puvodne, j["1001/1"].nove - j["1001/1"].puvodne) == (
        sum(cerven["1001/1"].values()),
        4_600,
    )
    assert not j["1001/5"].zmenena


def test_vyuctovani_podle_podilu_za_rok(session):
    _otevri(session)
    podily.uloz(session, PROFIL, date(2026, 7, 1), PRESUN, PROHLASENI, "x")
    session.flush()
    for m in range(3, 13):
        predpisy.vygeneruj(
            session, PROFIL, predpisy.nacti(PROFIL), 2026, m, zauctoval="x", dnes=KONEC
        )
    _faktura(session, "POJISTENI", 4_500_000, date(2026, 3, 5))  # 45 000 Kč
    session.commit()

    v = vyuctovani_spravy.spocitej(session, PROFIL, 2026)
    j = {x.jednotka: x for x in v.jednotky}
    # Půl roku 543/8600, půl roku 643/8600: 45 000 × 593/8600 = 3 102,906… Kč.
    assert j["1001/1"].podil == Fraction(593, 8600)
    assert j["1001/1"].naklady["POJISTENI"] in (310_290, 310_291)
    assert sum(x.naklady["POJISTENI"] for x in v.jednotky) == 4_500_000


@pytest.fixture
def klient(session, monkeypatch):
    monkeypatch.setattr(prihlaseni, "_jwks", lambda: FalesneJwks())
    monkeypatch.setattr(api_podily, "sezeni", lambda: sessionmaker(session.get_bind()))
    c = TestClient(app)
    c.headers["Authorization"] = f"Bearer {token()}"
    return c


def test_api(session, klient):
    _otevri(session)
    _otevri(session, 2027)
    predpisy.uloz_verzi(session, PROFIL, _sprava_podle_podilu(date(2027, 1, 1)), "x", None)
    session.commit()

    p = klient.get("/api/podily").json()
    assert p["zmeny"] == [] and p["predpis_podle_podilu"]
    assert p["podle_profilu"]["1001/2"] == "718/8600"
    assert {j["oznaceni"]: j["podil"] for j in p["jednotky"]} == ZE_SOUBORU

    navrh = {"plati_od": "2027-06-15", "podily": PRESUN}
    n = klient.post("/api/podily/nahled", json=navrh).json()
    assert n["chyba"] is None and n["od_mesice"] == "2027-07-01"
    assert n["mesicne"]["1001/1"]["nove"] - n["mesicne"]["1001/1"]["dosud"] == 4_600
    spatny = navrh | {"podily": ZE_SOUBORU | {"1001/1": "643/8600"}}
    assert "Součet" in klient.post("/api/podily/nahled", json=spatny).json()["chyba"]

    assert klient.put("/api/podily", json=navrh).status_code == 422  # chybí podle čeho
    r = klient.put("/api/podily", json=navrh | {"zdroj": PROHLASENI})
    assert r.status_code == 200, r.text
    [z] = r.json()["zmeny"]
    assert (z["plati_od"], z["od_mesice"], z["upravitelna"]) == ("2027-06-15", "2027-07-01", True)
    assert z["upravil"] == "vybor@example.test"
    [h] = audit.zaznamy(session, druh="zmena_podilu")
    assert (h.kdo, h.jmeno) == ("vybor@example.test", "Výbor")

    assert klient.delete("/api/podily/2027-06-15").json()["zmeny"] == []
