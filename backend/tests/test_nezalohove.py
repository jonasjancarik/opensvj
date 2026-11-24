"""Nezálohové příspěvky a fond ze zisku: příklad Ukázkové 12 z příručky (kapitola 2)."""

from dataclasses import replace
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from svj import (
    api_faktury,
    api_fond_ze_zisku,
    denik,
    faktury,
    fond_ze_zisku,
    pocatecni,
    predpisy,
    prihlaseni,
    uzaverka,
    vyuctovani_spravy,
)
from svj.api import app
from svj.domena import katalog
from tests.test_banka import PROFIL
from tests.test_pocatecni import _otevri_2026
from tests.test_prihlaseni import FalesneJwks, token

KDO = "vybor@example.test"
KONEC = date(2026, 12, 31)
NEZALOHOVE = replace(PROFIL, prispevky="nezalohove")
# Ukázkový předpis platí od března; příklad z příručky počítá s celým rokem.
NAST = predpisy.nacti(PROFIL)
NAST.verze = [replace(NAST.verze[0], plati_od=date(2026, 1, 1))]


def _pocatek(session, **zustatky):
    _otevri_2026(session)
    pocatecni.zauctuj(
        session,
        NEZALOHOVE,
        pocatecni.PocatecniStav(
            rok=2026,
            zustatky={"221100": -sum(zustatky.values()), **zustatky},
            polozky=[],
        ),
        zauctoval=KDO,
    )


def _faktura(session, castka, druh, rozhodnuti=None, profil=NEZALOHOVE):
    return faktury.zauctuj(
        session,
        profil,
        faktury.NovaFaktura(
            dodavatel="Střechy s.r.o.",
            castka=castka,
            duzp=date(2026, 6, 10),
            splatnost=date(2026, 6, 24),
            druh=druh,
            rozhodnuti=rozhodnuti,
        ),
        zadal=KDO,
    )


def _soucet(session, role):
    return -denik.zustatky(session, 2026).get(NEZALOHOVE.ucet(role), 0)


def test_predpis_jde_rovnou_do_vynosu(session):
    _otevri_2026(session)
    z = predpisy.vygeneruj(session, NEZALOHOVE, NAST, 2026, 1, zauctoval=KDO, dnes=KONEC)
    session.commit()
    assert z.popis == "Předpis příspěvků a záloh za leden 2026"
    role = {NEZALOHOVE.role_uctu()[r.ucet] for r in z.radky if r.strana == "d"}
    assert "vynosy.prispevky" in role
    assert not any(r.startswith(("zalohy_sprava", "zalohy_dlouhodobe")) for r in role)
    assert any(r.startswith("zalohy_sluzby.") for r in role)
    # Analytika výnosu nese složku předpisu, takže je vidět, co je fond oprav a co správa.
    slozky = {r.sluzba for r in z.radky if r.ucet == NEZALOHOVE.ucet("vynosy.prispevky")}
    assert {"FOND_OPRAV", "POJISTENI", "SPRAVA"} <= slozky


def test_priklad_z_prirucky(session):
    """Příspěvky 697 920 Kč, oprava střechy 260 000 Kč z fondu, ostatní náklady 219 000 Kč."""
    _pocatek(session, **{"911100": -50_000_000})
    for mesic in range(1, 13):
        predpisy.vygeneruj(session, NEZALOHOVE, NAST, 2026, mesic, zauctoval=KDO, dnes=KONEC)
    # Příručka počítá s celkem za dům (697 920 Kč); předpis zaokrouhluje každou jednotku na
    # celé koruny (54,3 m² × 45 Kč = 2 443,50 → 2 444 Kč), za rok je to o 24 Kč víc.
    assert _soucet(session, "vynosy.prispevky") == 69_794_400

    for druh, castka in (
        ("POJISTENI", 5_400_000),
        ("SPRAVA", 12_000_000),
        ("OSTATNI", 3_000_000),
        ("DROBNE_OPRAVY", 900_000),
    ):
        _faktura(session, castka, druh)
    denik.zauctuj(
        session,
        NEZALOHOVE,
        katalog.nacti()["poplatek-banky"],
        {"ucet": "provozni", "castka": "6000.00"},
        datum=KONEC,
        popis="Poplatky za vedení účtu",
        doklad="BV",
        zauctoval=KDO,
    )
    with pytest.raises(faktury.ChybaFaktury, match="kdo ji schválil"):
        _faktura(session, 26_000_000, "FOND_ZE_ZISKU")
    with pytest.raises(faktury.ChybaFaktury, match="jen 500 000,00 Kč"):
        _faktura(session, 60_000_000, "FOND_ZE_ZISKU", "shromáždění 12. 3. 2026")
    f = _faktura(session, 26_000_000, "FOND_ZE_ZISKU", "shromáždění 12. 3. 2026")
    session.commit()
    assert sorted((r.strana, NEZALOHOVE.role_uctu()[r.ucet], r.castka) for r in f.zapis.radky) == [
        ("d", "dodavatele", 26_000_000),
        ("d", "vynosy.cerpani_fondu", 26_000_000),
        ("md", "fond_ze_zisku", 26_000_000),
        ("md", "naklady.opravy", 26_000_000),
    ]

    zust = denik.zustatky(session, 2026)
    vynosy = -sum(c for u, c in zust.items() if u.startswith("6"))
    naklady = sum(c for u, c in zust.items() if u.startswith("5"))
    assert (vynosy, naklady, vynosy - naklady) == (95_794_400, 47_900_000, 47_894_400)

    st = fond_ze_zisku.stav(session, NEZALOHOVE, 2026)
    assert (st.pocatek, st.konec) == (50_000_000, 24_000_000)
    assert [(p.castka, p.doklad) for p in st.pohyby] == [(-26_000_000, f"FP {f.cislo}")]

    v = vyuctovani_spravy.spocitej(session, NEZALOHOVE, 2026)
    assert "nevyúčtovávají" in vyuctovani_spravy.proc_nejde(session, NAST, v, KONEC)
    kody = {k.kod for k in uzaverka.kontroly(session, NEZALOHOVE, NAST, 2026, KONEC)}
    assert "vyuctovani-spravy" not in kody and "fond-ze-zisku" not in kody
    priloha = uzaverka.priloha(session, NEZALOHOVE, NAST, 2026, KONEC)
    assert any("fondu ze zisku" in t for oddil in priloha for t in oddil.odstavce)


def test_rozdeleni_zisku(session):
    """Zisk 478 920 Kč z roku 2025 převede shromáždění do fondu ze zisku."""
    _pocatek(session, **{"931000": -47_892_000})
    st = fond_ze_zisku.stav(session, NEZALOHOVE, 2026)
    assert st.vysledek == 47_892_000
    assert st.navrh == fond_ze_zisku.Rozdeleni(47_892_000, 0, 0)
    kontroly = {k.kod: k for k in uzaverka.kontroly(session, NEZALOHOVE, NAST, 2026, KONEC)}
    assert kontroly["rozdeleni-vysledku"].stav == "chybi"
    with pytest.raises(faktury.ChybaFaktury, match="ještě není převedený"):
        _faktura(session, 26_000_000, "FOND_ZE_ZISKU", "výbor 2/2026")
    with pytest.raises(fond_ze_zisku.ChybaFondu, match="shromáždění"):
        fond_ze_zisku.rozdel(
            session, NEZALOHOVE, 2026, datum=date(2026, 4, 15), rozhodnuti=" ", zauctoval=KDO
        )

    z = fond_ze_zisku.rozdel(
        session,
        NEZALOHOVE,
        2026,
        datum=date(2026, 4, 15),
        rozhodnuti="shromáždění 15. 4. 2026, bod 3",
        zauctoval=KDO,
    )
    session.commit()
    assert sorted((r.strana, r.ucet, r.castka) for r in z.radky) == [
        ("d", "911100", 47_892_000),
        ("md", "931000", 47_892_000),
    ]
    with pytest.raises(fond_ze_zisku.ChybaFondu, match="už rozdělený"):
        fond_ze_zisku.rozdel(
            session, NEZALOHOVE, 2026, datum=date(2026, 4, 16), rozhodnuti="x", zauctoval=KDO
        )
    st = fond_ze_zisku.stav(session, NEZALOHOVE, 2026)
    assert (st.vysledek, st.navrh, st.konec) == (0, None, 47_892_000)
    kontroly = {k.kod: k for k in uzaverka.kontroly(session, NEZALOHOVE, NAST, 2026, KONEC)}
    assert kontroly["rozdeleni-vysledku"].stav == "hotovo"
    _faktura(session, 26_000_000, "FOND_ZE_ZISKU", "výbor 2/2026")


def test_zisk_nejdriv_uhradi_ztraty_a_ztrata_jde_na_932(session):
    assert fond_ze_zisku.navrhni(5_000_000, 3_000_000) == fond_ze_zisku.Rozdeleni(
        2_000_000, 3_000_000, 0
    )
    assert fond_ze_zisku.navrhni(2_000_000, 3_000_000) == fond_ze_zisku.Rozdeleni(0, 2_000_000, 0)
    assert fond_ze_zisku.navrhni(-12_000_000, 0) == fond_ze_zisku.Rozdeleni(0, 0, 12_000_000)

    _pocatek(session, **{"931000": 12_000_000})
    z = fond_ze_zisku.rozdel(
        session, NEZALOHOVE, 2026, datum=date(2026, 4, 15), rozhodnuti="shromáždění", zauctoval=KDO
    )
    session.commit()
    assert "ztráta 120 000,00 Kč" in z.popis
    st = fond_ze_zisku.stav(session, NEZALOHOVE, 2026)
    assert (st.vysledek, st.neuhrazena_ztrata) == (0, 12_000_000)


def test_api(session, monkeypatch):
    monkeypatch.setattr(prihlaseni, "_jwks", lambda: FalesneJwks())
    for modul in (api_faktury, api_fond_ze_zisku):
        monkeypatch.setattr(modul, "sezeni", lambda: sessionmaker(session.get_bind()))
    klient = TestClient(app)
    klient.headers["Authorization"] = f"Bearer {token()}"
    _pocatek(session, **{"931000": -47_892_000})
    session.commit()

    p = klient.get("/api/fond-ze-zisku/2026").json()
    assert (p["nastaveno"], p["nezalohove"], p["vysledek"]) == (True, False, 47_892_000)
    assert p["navrh"] == {"zisk_do_fondu": 47_892_000, "zisk_na_ztraty": 0, "ztrata": 0}
    chyba = klient.post(
        "/api/fond-ze-zisku/2026/rozdeleni", json={"datum": "2027-04-15", "rozhodnuti": "x"}
    )
    assert chyba.status_code == 422 and "2026" in chyba.json()["detail"]
    ok = klient.post(
        "/api/fond-ze-zisku/2026/rozdeleni",
        json={"datum": "2026-04-15", "rozhodnuti": "shromáždění 15. 4. 2026"},
    )
    assert ok.status_code == 200, ok.text
    p = ok.json()
    assert p["navrh"] is None and p["rozdeleni"]["zapis"].endswith("/2026")
    assert (p["konec"], [x["castka"] for x in p["pohyby"]]) == (47_892_000, [47_892_000])
    druhy = {d["id"] for d in klient.get("/api/faktury/2026").json()["druhy"]}
    assert "FOND_ZE_ZISKU" in druhy
