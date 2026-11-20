from datetime import date

import pytest

from svj import banka, denik, predpisy
from svj.domena import profil as profily
from tests.test_banka import PROFIL, _nahraj, _pohyby

NAST = predpisy.nacti(PROFIL)


def test_predpis_jednotky():
    """Ukázkový předpis od 03/2026, jednotka 1001/6 (62,40 m², 1 osoba)."""
    v = NAST.pro_mesic(2026, 3)
    c = predpisy.spocitej(PROFIL, v)["1001/6"]
    assert c["FOND_OPRAV"] == 280_800  # 45 Kč × 62,40 m²
    assert c["DROBNE_OPRAVY"] == 6_200  # 1 Kč × 62,40 m² = 62,40 → 62 Kč
    assert (c["ELEKTRINA"], c["ODPAD"], c["VYTAH"]) == (8_000, 60_000, 12_000)
    # 2 808 + 62 + výtah 120 + pevné složky 9 750 Kč
    assert sum(c.values()) == 1_274_000


def test_zaokrouhleni_poloviny_nahoru():
    """1001/10 má 47,50 m²: fond 45 × 47,50 = 2 137,50 → 2 138 Kč, drobné 47,50 → 48 Kč."""
    c = predpisy.spocitej(PROFIL, NAST.pro_mesic(2026, 3))["1001/10"]
    assert (c["FOND_OPRAV"], c["DROBNE_OPRAVY"]) == (213_800, 4_800)


def test_vlastni_pevne_castky_jednotky():
    """Nebytový prostor 1001/11 má vlastní teplo a vodu, ostatní pevné složky výchozí."""
    c = predpisy.spocitej(PROFIL, NAST.pro_mesic(2026, 3))["1001/11"]
    assert (c["TEPLO"], c["VODA"], c["ODPAD"]) == (150_000, 50_000, 60_000)
    assert c.get("OHREV_TUV", 0) == 0


def test_podle_osob_jen_vytah():
    v = NAST.pro_mesic(2026, 3)
    vse = predpisy.spocitej(PROFIL, v)
    assert [s.kod for s in v.slozky if s.klic == "osoby"] == ["VYTAH"]
    assert (predpisy.osob(v, "1001/3"), predpisy.osob(v, "1001/5")) == (1, 4)
    assert (vse["1001/3"]["VYTAH"], vse["1001/5"]["VYTAH"]) == (12_000, 48_000)
    assert vse["1001/3"]["ODPAD"] == vse["1001/5"]["ODPAD"] == 60_000  # pevná částka


def test_chybi_pocet_osob():
    vytah = predpisy.Slozka("VYTAH", "Výtah", "zalohy_sluzby.VYTAH", "osoby", 15_000)
    v = predpisy.Verze(date(2026, 1, 1), "", [vytah], {}, {"1001/1": 2})
    with pytest.raises(predpisy.ChybaPredpisu, match="1001/2.*počet osob"):
        predpisy.zkontroluj(PROFIL, v)
    predpisy.zkontroluj(PROFIL, predpisy.Verze(date(2026, 1, 1), "", [vytah], {}, {"vychozi": 1}))


def test_predpis_neplati_pred_brezen_2026():
    assert NAST.pro_mesic(2026, 2) is None
    assert predpisy.mesicni_celkem(PROFIL, NAST, 2026, 1) == {}


def test_klice_podil_a_jednotka():
    v = predpisy.Verze(
        plati_od=date(2026, 1, 1),
        zdroj="test",
        slozky=[
            predpisy.Slozka("POJISTENI", "Pojištění", "zalohy_sprava.POJISTENI", "podil", 400_000),
            predpisy.Slozka("SPRAVA", "Správa", "zalohy_sprava.SPRAVA", "jednotka", 1_000_000),
        ],
        pevne={},
        osoby={},
    )
    predpisy.zkontroluj(PROFIL, v)
    c = predpisy.spocitej(PROFIL, v)
    assert sum(x["POJISTENI"] for x in c.values()) == 400_000
    assert all(x["POJISTENI"] % 100 == 0 for x in c.values())  # celé koruny
    assert c["1001/9"]["POJISTENI"] > c["1001/1"]["POJISTENI"]  # větší podíl
    assert sorted({x["SPRAVA"] for x in c.values()}) == [83_300, 83_400]  # 10 000 / 12


def test_spatne_nastaveni():
    v = predpisy.Verze(date(2026, 1, 2), "", [], {}, {})
    with pytest.raises(predpisy.ChybaPredpisu, match="prvního dne"):
        predpisy.zkontroluj(PROFIL, v)
    v = predpisy.Verze(
        date(2026, 1, 1), "", [predpisy.Slozka("X", "X", "nic", "plocha", 1)], {}, {}
    )
    with pytest.raises(profily.NeznamaRole):
        predpisy.zkontroluj(PROFIL, v)


def _otevri_2026(session):
    from svj.db import Obdobi

    session.add(Obdobi(rok=2026, stav="otevrene"))
    session.flush()


def test_vygeneruj_mesic_a_saldo(session):
    _otevri_2026(session)
    with pytest.raises(predpisy.ChybaPredpisu, match="únor 2026"):
        predpisy.vygeneruj(session, PROFIL, NAST, 2026, 2, zauctoval="x")
    z = predpisy.vygeneruj(session, PROFIL, NAST, 2026, 3, zauctoval="x")
    assert predpisy.vygeneruj(session, PROFIL, NAST, 2026, 3, zauctoval="x").id == z.id
    with pytest.raises(predpisy.ChybaPredpisu, match="Nejdřív .* duben 2026"):
        predpisy.vygeneruj(session, PROFIL, NAST, 2026, 5, zauctoval="x")
    with pytest.raises(predpisy.ChybaPredpisu, match="zatím nejde"):
        predpisy.vygeneruj(session, PROFIL, NAST, 2026, 4, zauctoval="x", dnes=date(2026, 3, 31))
    assert predpisy.dalsi_k_zauctovani(session, NAST, 2026) == 4
    session.commit()

    celkem = sum(predpisy.mesicni_celkem(PROFIL, NAST, 2026, 3).values())
    zust = denik.zustatky(session, 2026)
    assert zust["311100"] == celkem
    assert zust["955100"] == -sum(
        predpisy.spocitej(PROFIL, NAST.pro_mesic(2026, 3))[j]["FOND_OPRAV"] for j in PROFIL.jednotky
    )
    # 45 Kč × 860 m² = 38 700 Kč; po jednotkách zaokrouhleno na koruny o 2 Kč víc.
    assert zust["955100"] == -3_870_200
    assert zust["324006"] < 0  # záloha na teplo

    s = {x.jednotka: x for x in predpisy.saldo(session, PROFIL, 2026)}
    assert (s["1001/6"].predepsano, s["1001/6"].zaplaceno, s["1001/6"].saldo) == (
        1_274_000,
        0,
        1_274_000,
    )


def test_vs_jednotky():
    assert PROFIL.jednotka_podle_vs("100100601") == "1001/6"
    assert PROFIL.jednotka_podle_vs("100101201") == "1001/12"
    assert PROFIL.jednotka_podle_vs("100102") == "1001/2"
    assert PROFIL.jednotka_podle_vs("1001007") == "1001/7"
    assert PROFIL.jednotka_podle_vs("100111422") is None  # jednotka 114 neexistuje
    assert PROFIL.jednotka_podle_vs("1101006") is None


def test_navrh_platby_podle_vs_a_castky(session):
    _nahraj(session)  # leden 2025: platba VS 5 z 19-123457
    p = _pohyby(session)["101"]
    kontext = banka.KontextNavrhu(profil=PROFIL, mesicni={"1001/5": 1_038_000, "1001/6": 1_274_000})
    n = banka.navrhni(p, [], [], kontext)
    assert (n.operace, n.vstupy) == ("uhrada-predpisu", {"jednotka": "1001/5"})
    assert "odpovídá" in n.duvod

    p.vs = "100100601"  # jen v paměti, necommitujeme
    n = banka.navrhni(p, [], [], kontext)
    assert n.vstupy == {"jednotka": "1001/6"} and "VS" in n.duvod
    session.rollback()
