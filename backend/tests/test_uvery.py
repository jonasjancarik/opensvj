"""Úvěr splácený vlastníky podle podílů: příklad zateplení z příručky (kapitola 5)."""

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from svj import (
    api_uvery,
    denik,
    faktury,
    oznameni,
    predpisy,
    prihlaseni,
    rozhodnuti,
    uvery,
    vyuctovani_spravy,
)
from svj.api import app
from svj.db import RadekZapisu
from svj.domena import katalog
from tests.test_banka import PROFIL
from tests.test_pocatecni import _otevri_2026
from tests.test_prihlaseni import FalesneJwks, token

KDO = "vybor@example.test"
JISTINA = 103_200_000  # 1 032 000 Kč, 120 splátek po 8 600 Kč za dům


def _rozhodnuti(session, organ="shromazdeni"):
    return rozhodnuti.pridej(
        session,
        rozhodnuti.UdajeRozhodnuti(
            organ=organ, datum=date(2026, 3, 12), nazev="Zateplení fasády a úvěr", bod="4"
        ),
        KDO,
    )


def _predpis(session, *mesice):
    for m in mesice:
        predpisy.vygeneruj(
            session,
            PROFIL,
            predpisy.nacti(PROFIL, session),
            2026,
            m,
            zauctoval=KDO,
            dnes=date(2026, 12, 31),
        )


def _uver(session, **kw):
    r = _rozhodnuti(session)
    zadani = dict(
        nazev="zateplení fasády",
        jistina=JISTINA,
        rozhodnuti_id=r.id,
        predepsano_dne=date(2026, 3, 20),
        prvni_splatka=date(2026, 5, 1),
        pocet_splatek=120,
        uroky_hradi="fond_oprav",
        zauctoval=KDO,
    )
    return uvery.zaloz(session, PROFIL, **(zadani | kw))


def test_podily_a_splatky_v_predpisu(session):
    _otevri_2026(session)
    _predpis(session, 3, 4)
    with pytest.raises(uvery.ChybaUveru, match="rozhodnutí shromáždění"):
        _uver(session, rozhodnuti_id=_rozhodnuti(session, "vybor").id)
    with pytest.raises(uvery.ChybaUveru, match="duben 2026 už je zaúčtovaný"):
        _uver(session, prvni_splatka=date(2026, 4, 1))
    u = _uver(session)
    session.commit()
    assert u.kod == "UVER-1"
    # Na 1/8 600 podílu připadne 120 Kč jistiny, 1001/6 s podílem 624/8 600 splatí 74 880 Kč.
    assert u.podily["1001/6"] == 7_488_000
    assert sum(u.podily.values()) == JISTINA
    radky = u.zapis.radky
    assert {(r.strana, r.role, r.sluzba) for r in radky} == {
        ("md", "pohledavky_uver", "UVER-1"),
        ("d", "zalohy_dlouhodobe_uver", "UVER-1"),
    }

    # Splátka je složkou předpisu od května: 624 Kč u 1001/6, 8 600 Kč za dům.
    nast = predpisy.nacti(PROFIL, session)
    assert "UVER-1" not in predpisy.castky_mesice(PROFIL, nast, 2026, 4)["1001/6"]
    kveten = predpisy.castky_mesice(PROFIL, nast, 2026, 5)
    assert kveten["1001/6"]["UVER-1"] == 62_400
    assert sum(c["UVER-1"] for c in kveten.values()) == 860_000
    assert date(2026, 5, 1) in nast.zmeny_predpisu()
    o = oznameni.oznameni(PROFIL, nast, date(2026, 5, 1))
    zmena = next(
        s for j in o.jednotky if j.jednotka == "1001/6" for s in j.slozky if s.kod == "UVER-1"
    )
    assert (zmena.puvodne, zmena.nove, zmena.nazev) == (
        None,
        62_400,
        "Splátka úvěru: zateplení fasády",
    )

    _predpis(session, 5, 6)
    session.commit()
    radky_kvetna = session.scalars(
        select(RadekZapisu).where(RadekZapisu.sluzba == "UVER-1", RadekZapisu.jednotka == "1001/6")
    ).all()
    assert sorted((r.strana, r.role, r.castka) for r in radky_kvetna)[-2:] == [
        ("md", "pohledavky_vlastnici", 62_400),
        ("md", "pohledavky_vlastnici", 62_400),
    ]
    assert uvery.zbytky_jednotky(session, "1001/6", date(2026, 6, 30))[0].zbyva == 7_363_200
    assert uvery.zbytky_jednotky(session, "1001/6", date(2026, 4, 30))[0].zbyva == 7_488_000
    st = uvery.stav(session, PROFIL, u, 2026)
    assert st.nesplaceno == JISTINA - 2 * 860_000
    assert st.posledni_splatka == date(2036, 4, 1)

    # Předpis podílů nejde stornovat, dokud na něj navazují splátky.
    with pytest.raises(denik.ChybaUctovani, match="navazuje"):
        denik.storno(session, u.zapis_id, duvod="omyl", zauctoval=KDO)


def test_splatka_jednotky_s_malym_podilem_konci_driv():
    plan = predpisy.SplaceniUveru("UVER-1", "x", date(2026, 1, 1), 12, {"a": 100_050})
    # 1 000,50 Kč na 12 měsíců: 84 Kč měsíčně, v prosinci zbytek 76,50 Kč.
    assert plan.mesicne("a") == 8_400
    assert [plan.splatka("a", 2026, m) for m in (1, 11, 12)] == [8_400, 8_400, 7_650]
    assert plan.splatka("a", 2027, 1) == 0
    assert plan.zmeny() == {date(2026, 1, 1), date(2026, 12, 1), date(2027, 1, 1)}


def test_faktura_uroky_splatka_a_kryti(session):
    _otevri_2026(session)
    u = _uver(session)
    f = faktury.zauctuj(
        session,
        PROFIL,
        faktury.NovaFaktura(
            dodavatel="Stavby s.r.o.",
            castka=JISTINA,
            duzp=date(2026, 4, 10),
            splatnost=date(2026, 4, 30),
            druh="UVER",
            rozhodnuti="shromáždění 12. 3. 2026, bod 4",
        ),
        zadal=KDO,
    )
    assert {(r.strana, r.role) for r in f.zapis.radky} == {
        ("md", "zalohy_dlouhodobe_uver"),
        ("d", "dodavatele"),
    }
    with pytest.raises(uvery.ChybaUveru, match="zbývá zaplatit"):
        uvery.uhrada_faktury(
            session, PROFIL, u.id, faktura=f.cislo, castka=JISTINA + 1,
            datum=date(2026, 4, 20), zauctoval=KDO,
        )  # fmt: skip
    uvery.uhrada_faktury(
        session, PROFIL, u.id, faktura=f.cislo, castka=JISTINA,
        datum=date(2026, 4, 20), zauctoval=KDO,
    )  # fmt: skip
    assert f.cislo not in {x.faktura.cislo for x in faktury.prehled(session, jen_otevrene=True)}
    uvery.uroky(
        session, PROFIL, u.id, uroky=2_800_000, poplatky=80_000, datum=date(2026, 12, 31),
        sluzba_poplatku="SPRAVA", zauctoval=KDO,
    )  # fmt: skip

    # Splátka bance: odchod z běžného účtu (v Bance), příchod na úvěrový účet.
    with pytest.raises(uvery.ChybaUveru, match="Na cestě"):
        uvery.prichod_splatky(
            session, PROFIL, u.id, castka=860_000, datum=date(2026, 5, 16), zauctoval=KDO
        )
    denik.zauctuj(
        session, PROFIL, katalog.nacti()["uver-splatka"],
        {"ucet": "provozni", "castka": "8600.00"}, datum=date(2026, 5, 15), popis="Splátka",
        doklad="BV", zauctoval=KDO, krok="odchod",
    )  # fmt: skip
    uvery.prichod_splatky(
        session, PROFIL, u.id, castka=860_000, datum=date(2026, 5, 16), zauctoval=KDO
    )
    session.commit()
    st = uvery.stav(session, PROFIL, u, 2026)
    assert st.zbyva_bance == JISTINA + 2_800_000 + 80_000 - 860_000
    assert (st.uroky, st.kryto) == (2_800_000, 0)
    assert uvery.nevycerpana_zaloha(session, PROFIL) == 0

    with pytest.raises(uvery.ChybaUveru, match="k 31. 12. 2026"):
        uvery.kryti_uroku(session, PROFIL, u.id, 2026, zauctoval=KDO, dnes=date(2026, 12, 30))
    v = vyuctovani_spravy.spocitej(session, PROFIL, 2026)
    assert [(n.popis, n.castka) for n in v.nezahrnuto] == [("Úroky z úvěru", 2_800_000)]
    z = uvery.kryti_uroku(session, PROFIL, u.id, 2026, zauctoval=KDO, dnes=date(2026, 12, 31))
    assert {(r.strana, r.role, r.castka) for r in z.radky} == {
        ("md", "zalohy_dlouhodobe", 2_800_000),
        ("d", "vynosy.zuctovani_dlouhodobych_zaloh", 2_800_000),
    }
    with pytest.raises(uvery.ChybaUveru, match="nejsou žádné úroky"):
        uvery.kryti_uroku(session, PROFIL, u.id, 2026, zauctoval=KDO, dnes=date(2026, 12, 31))
    session.commit()

    # Vyúčtování správy: úroky už nejsou mezi nezahrnutými, poplatky jdou na správu, a co
    # platil fond oprav a záloha na úvěr, je vidět zvlášť.
    v = vyuctovani_spravy.spocitej(session, PROFIL, 2026)
    assert v.nezahrnuto == []
    assert next(p for p in v.polozky if p.kod == "SPRAVA").naklady == 80_000
    assert [(x.zdroj, x.popis, x.castka) for x in v.z_dlouhodobych] == [
        ("fond oprav", "Úroky z úvěru", 2_800_000),
        ("záloha na úvěr", "Opravy a investice placené z úvěru", JISTINA),
    ]


@pytest.fixture
def klient(session, monkeypatch):
    monkeypatch.setattr(prihlaseni, "_jwks", lambda: FalesneJwks())
    monkeypatch.setattr(api_uvery, "sezeni", lambda: sessionmaker(session.get_bind()))
    c = TestClient(app)
    c.headers["Authorization"] = f"Bearer {token()}"
    return c


def test_api(session, klient):
    _otevri_2026(session)
    r = _rozhodnuti(session)
    session.commit()
    n = klient.post(
        "/api/uvery/nahled",
        json={"jistina": JISTINA, "predepsano_dne": "2026-03-20", "pocet_splatek": 120},
    )
    assert n.status_code == 200, n.text
    assert n.json()["1001/6"] == {"podil": 7_488_000, "mesicne": 62_400}
    zadani = {
        "nazev": "zateplení fasády",
        "jistina": JISTINA,
        "rozhodnuti_id": r.id,
        "predepsano_dne": "2026-03-20",
        "prvni_splatka": "2026-05-01",
        "pocet_splatek": 120,
        "uroky_hradi": "nevim",
    }
    chyba = klient.post("/api/uvery?rok=2026", json=zadani)
    assert chyba.status_code == 422
    assert "úroky" in chyba.json()["detail"]
    ok = klient.post("/api/uvery?rok=2026", json=zadani | {"uroky_hradi": "zaloha_na_uver"})
    assert ok.status_code == 200, ok.text
    (u,) = ok.json()["uvery"]
    assert (u["platny"], u["nesplaceno"], u["posledni_splatka"]) == (True, JISTINA, "2036-04-01")
    assert len(u["jednotky"]) == 12
    assert ok.json()["nevycerpano"] == JISTINA
