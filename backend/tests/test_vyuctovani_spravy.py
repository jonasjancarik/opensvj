"""Roční vyúčtování záloh na správu domu: rozdělení nákladů, porovnání se zálohami, zápis."""

from datetime import date

import pytest

from svj import denik, dluznici, faktury, predpisy, vyuctovani_spravy
from svj.domena import katalog
from tests.test_banka import PROFIL
from tests.test_pocatecni import _otevri_2026

NAST = predpisy.nacti(PROFIL)
KONEC = date(2026, 12, 31)


def _faktura(session, druh, castka, duzp):
    faktury.zauctuj(
        session,
        PROFIL,
        faktury.NovaFaktura(
            dodavatel=f"Dodavatel {druh}", castka=castka, duzp=duzp, splatnost=duzp, druh=druh
        ),
        zadal="x",
    )


def _rok(session, mesice=range(3, 13)):
    _otevri_2026(session)
    for m in mesice:
        predpisy.vygeneruj(session, PROFIL, NAST, 2026, m, zauctoval="x", dnes=KONEC)
    _faktura(session, "POJISTENI", 4_500_000, date(2026, 3, 5))  # 45 000 Kč
    _faktura(session, "SPRAVA", 24_000_000, date(2026, 6, 30))  # 240 000 Kč
    _faktura(session, "UKLID", 300_000, date(2026, 4, 1))  # služba, do správy nepatří
    denik.zauctuj(
        session,
        PROFIL,
        katalog.nacti()["poplatek-banky"],
        {"ucet": "provozni", "castka": "120.00"},
        datum=date(2026, 5, 31),
        popis="poplatek",
        doklad="BV",
        zauctoval="x",
    )
    session.commit()


def test_vypocet(session):
    _rok(session)
    v = vyuctovani_spravy.spocitej(session, PROFIL, 2026)
    p = {x.kod: x for x in v.polozky}
    assert (p["POJISTENI"].naklady, p["SPRAVA"].naklady, p["OSTATNI"].naklady) == (
        4_500_000,
        24_000_000,
        0,
    )
    # Pojištění 400 Kč a správa 850 Kč měsíčně, deset měsíců, 12 jednotek.
    assert p["POJISTENI"].zalohy == 12 * 10 * 40_000
    assert p["SPRAVA"].zalohy == 12 * 10 * 85_000
    assert [n.popis for n in v.nezahrnuto] == ["Bankovní poplatky"]

    j = {x.jednotka: x for x in v.jednotky}
    # Správa rovným dílem: 240 000 / 12 = 20 000 Kč každé jednotce.
    assert {x.naklady["SPRAVA"] for x in v.jednotky} == {2_000_000}
    # Pojištění podle podílů: větší jednotka platí víc, součet přesně sedí.
    assert sum(x.naklady["POJISTENI"] for x in v.jednotky) == 4_500_000
    assert j["1001/9"].naklady["POJISTENI"] > j["1001/1"].naklady["POJISTENI"]
    # 45 000 × 543/8600 = 2 841,279… Kč (zbytek haléře dostane jednotka s největším zbytkem).
    assert j["1001/1"].naklady["POJISTENI"] in (284_127, 284_128)
    # Zálohy 1001/1: deset měsíců × (pojištění 400 + správa 850 + ostatní 300 + drobné opravy 54).
    assert sum(j["1001/1"].zalohy.values()) == 10 * (40_000 + 85_000 + 30_000 + 5_400)
    assert j["1001/1"].rozdil == j["1001/1"].naklady["POJISTENI"] + 2_000_000 - 1_604_000


def test_zauctovani(session):
    _rok(session)
    v = vyuctovani_spravy.spocitej(session, PROFIL, 2026)
    assert "31. 12. 2026" in vyuctovani_spravy.proc_nejde(session, NAST, v, date(2026, 11, 20))
    z = vyuctovani_spravy.zauctuj(session, PROFIL, NAST, 2026, zauctoval="x", dnes=KONEC)
    session.commit()
    assert (z.datum, z.doklad, z.operace) == (KONEC, "VY S 2026", "vyuctovani-spravy")

    zust = denik.zustatky(session, 2026)
    for kod in PROFIL.sprava:  # zálohy na správu jsou vyúčtované do nuly
        assert zust.get(PROFIL.ucet(f"zalohy_sprava.{kod}"), 0) == 0
    assert zust.get("395100", 0) == 0
    assert zust["311200"] == sum(j.rozdil for j in v.jednotky)
    # Služby (teplo atd.) se nevyúčtovaly.
    assert zust["324006"] < 0

    # Opakované zaúčtování vrátí stejný zápis; výpočet po zaúčtování ukazuje stejná čísla.
    assert vyuctovani_spravy.zauctuj(session, PROFIL, NAST, 2026, zauctoval="x", dnes=KONEC) is z
    po = vyuctovani_spravy.spocitej(session, PROFIL, 2026)
    assert [j.rozdil for j in po.jednotky] == [j.rozdil for j in v.jednotky]

    # Nedoplatek je v dlužnících se splatností 30. 4. dalšího roku.
    d = {x.jednotka: x for x in dluznici.prehled(session, PROFIL, NAST, 2026, KONEC)}
    j1 = next(j for j in v.jednotky if j.jednotka == "1001/1")
    polozka = next(p for p in d["1001/1"].polozky if p.popis.startswith("Vyúčtování záloh"))
    assert (polozka.castka, polozka.splatnost) == (j1.rozdil, date(2027, 4, 30))


def test_nejde_bez_vsech_predpisu(session):
    _rok(session, mesice=range(3, 12))
    with pytest.raises(vyuctovani_spravy.ChybaVyuctovani, match="prosinec"):
        vyuctovani_spravy.zauctuj(session, PROFIL, NAST, 2026, zauctoval="x", dnes=KONEC)


def _ctyri_vlastnici(polozky, zalohy):
    """Čtyři vlastníci s podíly 150, 200, 300 a 350 z 1 000 (vymyšlené pro testy)."""
    from fractions import Fraction

    podily = [150, 200, 300, 350]
    jednotky = {
        f"V{i + 1}": vyuctovani_spravy.Jednotka(f"V{i + 1}", Fraction(p, 1000))
        for i, p in enumerate(podily)
    }
    for kod, castky in zalohy.items():
        for j, c in zip(jednotky.values(), castky, strict=True):
            j.zalohy[kod] = c
    vyuctovani_spravy.rozpocitej(polozky, jednotky)
    return jednotky


def _p(kod, klic, naklady, vynosy=0):
    return vyuctovani_spravy.Polozka(kod, kod, klic, naklady * 100, vynosy * 100)


ZALOHY_POJISTENI = [150_000, 250_000, 350_000, 400_000]


def test_pojistne_plneni_a_uroky_snizuji_naklady():
    """Postup podle Durec s. 55–58, čísla jsou vlastní."""
    # Oprava 120 000 Kč, pojistné plnění 90 000 Kč: vlastníci nesou 30 000 podle podílů.
    j = _ctyri_vlastnici([_p("OPRAVA", "podil", 120_000, 90_000)], {})
    assert [x.naklady["OPRAVA"] for x in j.values()] == [450_000, 600_000, 900_000, 1_050_000]

    # Pojištění 12 000 Kč podle podílů; provoz 60 000 Kč snížený o úroky 4 000 Kč rovným
    # dílem, tedy 14 000 Kč na vlastníka.
    j = _ctyri_vlastnici(
        [_p("POJISTENI", "podil", 12_000), _p("PROVOZ", "jednotka", 60_000, 4_000)],
        {"POJISTENI": ZALOHY_POJISTENI, "PROVOZ": [1_350_000] * 4},
    )
    assert [x.naklady["POJISTENI"] for x in j.values()] == [180_000, 240_000, 360_000, 420_000]
    assert [x.naklady["PROVOZ"] for x in j.values()] == [1_400_000] * 4
    assert [x.rozdil for x in j.values()] == [80_000, 40_000, 60_000, 70_000]


def test_dotace_snizuje_uroky_z_uveru():
    """Postup podle Durec s. 59–62, čísla jsou vlastní. Daň z příjmů do vyúčtování
    nepatří (hradí se ze zdanitelných výnosů)."""
    j = _ctyri_vlastnici(
        [
            _p("POJISTENI", "podil", 12_000),
            _p("UROKY", "podil", 24_000, 10_000),
            _p("PROVOZ", "jednotka", 60_000),
        ],
        {"POJISTENI": ZALOHY_POJISTENI, "PROVOZ": [1_350_000] * 4},
    )
    assert [x.naklady["UROKY"] for x in j.values()] == [210_000, 280_000, 420_000, 490_000]
    assert [x.rozdil for x in j.values()] == [390_000, 420_000, 580_000, 660_000]
    # Náklady 86 000 Kč, zálohy 11 500 + 4 × 13 500 = 65 500 Kč.
    assert sum(x.rozdil for x in j.values()) == 2_050_000


def test_vynos_s_polozkou_snizuje_naklady(session):
    """Pojistné plnění označené položkou správy se odečte od nákladů té položky."""
    _rok(session)
    op = katalog.Operace(
        id="pojistne-plneni-na-polozku",
        nazev="test",
        stav="praxe",
        doklad="BV",
        zapisy=[
            {
                "md": "banka.provozni",
                "d": "vynosy.pojistne_plneni",
                "castka": "{castka}",
                "dimenze": {"sluzba": "POJISTENI"},
            }
        ],
        zdroje=[{"typ": "test"}],
        priklady=[],
    )
    denik.zauctuj(
        session, PROFIL, op, {"castka": "5000.00"}, datum=date(2026, 8, 1), popis="plnění",
        doklad="BV", zauctoval="x",
    )  # fmt: skip
    session.commit()
    p = {x.kod: x for x in vyuctovani_spravy.spocitej(session, PROFIL, 2026).polozky}
    assert (p["POJISTENI"].naklady, p["POJISTENI"].vynosy) == (4_500_000, 500_000)
    assert p["POJISTENI"].k_rozdeleni == 4_000_000

    z = vyuctovani_spravy.zauctuj(session, PROFIL, NAST, 2026, zauctoval="x", dnes=KONEC)
    session.commit()
    # Po zaúčtování je vnitřní zúčtování vyrovnané i s odečteným výnosem.
    s395 = sum(r.castka if r.strana == "md" else -r.castka for r in z.radky if r.ucet == "395100")
    assert s395 == 0
