"""Dlouhodobý majetek: příklad se sekačkou z příručky (kapitola 6) a další způsoby krytí."""

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from svj import (
    api_majetek,
    denik,
    faktury,
    majetek,
    predpisy,
    prihlaseni,
    uzaverka,
    vyuctovani_spravy,
)
from svj.api import app
from tests.test_banka import PROFIL
from tests.test_pocatecni import _otevri_2026
from tests.test_prihlaseni import FalesneJwks, token

KDO = "vybor@example.test"
KONEC = date(2026, 12, 31)


def _faktura(session, castka, druh="MAJETEK", duzp=date(2026, 5, 20)):
    return faktury.zauctuj(
        session,
        PROFIL,
        faktury.NovaFaktura(
            dodavatel="Zahrada s.r.o.", castka=castka, duzp=duzp, splatnost=duzp, druh=druh
        ),
        zadal=KDO,
    )


def _sekacka(session, **kw):
    zadani = dict(
        nazev="robotická sekačka",
        druh="movity",
        zarazeno=date(2026, 6, 1),
        cena=3_840_000,
        doba_mesicu=72,
        kryti_kod="fond_oprav",
        inventarni_cislo="M-1",
        zauctoval=KDO,
    )
    return majetek.zarad(session, PROFIL, **(zadani | kw))


def _radky(zapis):
    return sorted((r.strana, r.role, r.castka, r.sluzba) for r in zapis.radky)


def test_plan_odpisu_po_mesicich():
    p = majetek.Plan(date(2026, 7, 1), 72, 3_840_000)
    assert [p.za_rok(r) for r in range(2026, 2033)] == [
        320_000,
        640_000,
        640_000,
        640_000,
        640_000,
        640_000,
        320_000,
    ]
    assert p.posledni_rok == 2032
    # Po korunách kumulativně, poslední měsíc dorovná haléře.
    q = majetek.Plan(date(2026, 1, 1), 3, 100_050)
    assert [q.kumulativne(n) for n in (1, 2, 3)] == [33_400, 66_700, 100_050]


def test_sekacka_z_fondu_oprav(session):
    _otevri_2026(session)
    _faktura(session, 3_600_000)
    with pytest.raises(majetek.ChybaMajetku, match="nezařazeno jen 36 000"):
        _sekacka(session)
    _faktura(session, 240_000)
    m = _sekacka(session)
    session.commit()
    assert m.kod == f"MAJ-{m.id}"
    assert _radky(m.zapis) == [
        ("d", "majetek_porizovani", 3_840_000, m.kod),
        ("d", "zdroj_majetku", 3_840_000, m.kod),
        ("md", "majetek", 3_840_000, m.kod),
        ("md", "zalohy_dlouhodobe", 3_840_000, m.kod),
    ]
    assert majetek.k_zarazeni(session, PROFIL)["majetek_porizovani"] == 0

    with pytest.raises(majetek.ChybaMajetku, match="od 31. 12. 2026"):
        majetek.zauctuj_odpisy(session, PROFIL, 2026, zauctoval=KDO, dnes=date(2026, 12, 30))
    v = vyuctovani_spravy.spocitej(session, PROFIL, 2026)
    assert [(x.zdroj, x.popis, x.castka) for x in v.z_dlouhodobych] == [
        ("fond oprav", "Pořízení majetku", 3_840_000)
    ]
    (z,) = majetek.zauctuj_odpisy(session, PROFIL, 2026, zauctoval=KDO, dnes=KONEC)
    session.commit()
    assert _radky(z) == [
        ("d", "opravky_majetku", 320_000, m.kod),
        ("d", "vynosy.zuctovani_dlouhodobych_zaloh", 320_000, m.kod),
        ("d", "zalohy_dlouhodobe", 320_000, m.kod),
        ("md", "naklady.odpisy", 320_000, m.kod),
        ("md", "zalohy_dlouhodobe", 320_000, m.kod),
        ("md", "zdroj_majetku", 320_000, m.kod),
    ]
    with pytest.raises(majetek.ChybaMajetku, match="není co odepsat"):
        majetek.zauctuj_odpisy(session, PROFIL, 2026, zauctoval=KDO, dnes=KONEC)

    st = majetek.stav(session, PROFIL, m, 2026, KONEC)
    assert (st.opravky, st.zustatkova, st.odpis_zauctovan) == (320_000, 3_520_000, True)
    assert st.plan[0].__dict__ == {
        "rok": 2026,
        "odpis": 320_000,
        "opravky": 320_000,
        "zustatek": 3_520_000,
    }
    assert sum(r.odpis for r in st.plan) == 3_840_000

    # Odpis už vlastníci zaplatili při pořízení: ve vyúčtování správy není a výsledek je nulový.
    v = vyuctovani_spravy.spocitej(session, PROFIL, 2026)
    assert v.nezahrnuto == []
    zust = denik.zustatky(session, 2026)
    assert zust[PROFIL.ucet("naklady.odpisy")] == 320_000
    assert zust[PROFIL.ucet("vynosy.zuctovani_dlouhodobych_zaloh")] == -320_000
    assert zust[PROFIL.ucet("zdroj_majetku")] == -3_520_000

    # Zařazení nejde stornovat, dokud na něj navazuje odpis.
    with pytest.raises(denik.ChybaUctovani, match="Na zařazení majetku navazuje"):
        denik.storno(session, m.zapis_id, duvod="omyl", zauctoval=KDO)

    # Uzávěrka: evidence sedí na účty, inventurní soupis má kartu.
    nast = predpisy.nacti(PROFIL, session)
    kontroly = {k.kod: k for k in uzaverka.kontroly(session, PROFIL, nast, 2026, KONEC)}
    assert kontroly["odpisy"].stav == "hotovo"
    assert kontroly["evidence-majetku"].stav == "hotovo"
    soupisy = {x.ucet: x for x in uzaverka.soupisy(session, PROFIL, 2026, KONEC)}
    assert [(p.popis, p.castka) for p in soupisy["022100"].polozky] == [
        ("M-1 · robotická sekačka", 3_840_000)
    ]
    assert [(p.popis, p.castka) for p in soupisy["082100"].polozky] == [
        ("M-1 · robotická sekačka", -320_000)
    ]

    # Vyřazení doodepíše zůstatkovou cenu a odúčtuje majetek proti oprávkám.
    with pytest.raises(majetek.ChybaMajetku, match="proč"):
        majetek.vyrad(session, PROFIL, m.id, datum=KONEC, duvod=" ", zauctoval=KDO)
    z = majetek.vyrad(session, PROFIL, m.id, datum=KONEC, duvod="Ukradena.", zauctoval=KDO)
    session.commit()
    assert ("md", "naklady.odpisy", 3_520_000, m.kod) in _radky(z)
    assert ("md", "opravky_majetku", 3_840_000, m.kod) in _radky(z)
    zust = denik.zustatky(session, 2026)
    for role in ("majetek", "opravky_majetku", "zdroj_majetku"):
        assert zust[PROFIL.ucet(role)] == 0
    assert majetek.stav(session, PROFIL, m, 2026, KONEC).zustatkova == 0
    assert majetek.soupis(session, PROFIL, KONEC) == {}


def test_software_odepisovany_pres_spravu(session):
    _otevri_2026(session)
    _faktura(session, 9_000_000, druh="MAJETEK_NEHMOTNY", duzp=date(2026, 2, 10))
    with pytest.raises(majetek.ChybaMajetku, match="nezařazeno jen 0"):
        _sekacka(session)  # hmotný majetek nemá na 042 nic
    m = majetek.zarad(
        session,
        PROFIL,
        nazev="evidenční program",
        druh="nehmotny",
        zarazeno=date(2026, 3, 31),
        cena=9_000_000,
        doba_mesicu=36,
        kryti_kod="SPRAVA",
        zauctoval=KDO,
    )
    session.commit()
    assert {r.role for r in m.zapis.radky} == {"majetek_nehmotny", "majetek_nehmotny_porizovani"}

    # Vyúčtování správy čeká na odpisy, protože patří k položce Správa.
    nast = predpisy.nacti(PROFIL, session)
    v = vyuctovani_spravy.spocitej(session, PROFIL, 2026)
    assert "odpisy majetku" in vyuctovani_spravy.proc_nejde(session, nast, v, KONEC)
    (z,) = majetek.zauctuj_odpisy(session, PROFIL, 2026, zauctoval=KDO, dnes=KONEC)
    session.commit()
    # Duben až prosinec: 9 z 36 měsíců.
    assert _radky(z) == [
        ("d", "opravky_nehmotneho", 2_250_000, m.kod),
        ("md", "naklady.odpisy", 2_250_000, "SPRAVA"),
    ]
    v = vyuctovani_spravy.spocitej(session, PROFIL, 2026)
    assert next(p for p in v.polozky if p.kod == "SPRAVA").naklady == 2_250_000
    assert "odpisy" not in (vyuctovani_spravy.proc_nejde(session, nast, v, KONEC) or "")


def test_prevzaty_a_pozemek(session):
    _otevri_2026(session)
    with pytest.raises(majetek.ChybaMajetku, match="před 1. 1. 2026"):
        _sekacka(session, prevzato_k=date(2026, 1, 1))
    m = _sekacka(
        session,
        nazev="traktor",
        zarazeno=date(2023, 6, 15),
        cena=6_000_000,
        doba_mesicu=60,
        prevzato_k=date(2026, 1, 1),
        opravky_prevzate=1_800_000,
    )
    session.commit()
    assert m.zapis_id is None
    # Od července 2023 uplynulo 30 měsíců; zbývá 42 000 Kč na 30 měsíců, 1 400 Kč měsíčně.
    assert majetek.plan(m).za_rok(2026) == 1_680_000
    st = majetek.stav(session, PROFIL, m, 2026, KONEC)
    assert (st.opravky, st.zustatkova) == (1_800_000, 4_200_000)
    assert st.plan[-1].rok == 2028 and st.plan[-1].zustatek == 0

    # Bez počátečních stavů evidence nesedí na účty.
    nast = predpisy.nacti(PROFIL, session)
    k = {x.kod: x for x in uzaverka.kontroly(session, PROFIL, nast, 2026, KONEC)}
    assert k["evidence-majetku"].stav == "chybi"
    assert "v evidenci 60 000,00 Kč" in k["evidence-majetku"].detail

    majetek.smaz_prevzaty(session, m.id)
    session.commit()
    assert majetek.karty(session) == []

    _faktura(session, 50_000_000)
    p = _sekacka(session, nazev="parkoviště", druh="pozemek", cena=50_000_000, doba_mesicu=None)
    session.commit()
    assert p.doba_mesicu is None
    assert majetek.k_odepsani(session, 2026) == []
    with pytest.raises(majetek.ChybaMajetku, match="pozemku"):
        majetek.vyrad(session, PROFIL, p.id, datum=KONEC, duvod="prodej", zauctoval=KDO)


@pytest.fixture
def klient(session, monkeypatch):
    monkeypatch.setattr(prihlaseni, "_jwks", lambda: FalesneJwks())
    monkeypatch.setattr(api_majetek, "sezeni", lambda: sessionmaker(session.get_bind()))
    c = TestClient(app)
    c.headers["Authorization"] = f"Bearer {token()}"
    return c


def test_api(session, klient):
    _otevri_2026(session)
    _faktura(session, 3_840_000)
    session.commit()
    p = klient.get("/api/majetek/2026").json()
    assert p["k_zarazeni"]["movity"] == 3_840_000
    assert p["fondy"] == ["fond_oprav", "fond_ze_zisku"]
    zadani = {
        "nazev": "robotická sekačka",
        "druh": "movity",
        "zarazeno": "2026-06-01",
        "cena": 3_840_000,
        "doba_mesicu": 72,
        "kryti": "nevim",
    }
    chyba = klient.post("/api/majetek?rok=2026", json=zadani)
    assert chyba.status_code == 422
    assert "kryté" in chyba.json()["detail"]
    ok = klient.post("/api/majetek?rok=2026", json=zadani | {"kryti": "fond_oprav"})
    assert ok.status_code == 200, ok.text
    (k,) = ok.json()["karty"]
    assert (k["odpis_roku"], k["odpis_zauctovan"], k["zustatkova"]) == (320_000, False, 3_840_000)
    assert ok.json()["odpisy_k_zauctovani"] == 320_000
    popis = {"nazev": "sekačka", "poznamka": "dvůr"}
    u = klient.put(f"/api/majetek/{k['id']}?rok=2026", json=popis)
    assert u.json()["karty"][0]["nazev"] == "sekačka"
    druhy = {d["id"] for d in klient.get("/api/faktury/2026").json()["druhy"]}
    assert {"MAJETEK", "MAJETEK_NEHMOTNY"} <= druhy
