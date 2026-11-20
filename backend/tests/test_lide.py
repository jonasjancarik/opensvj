"""Evidence vlastníků: osoby, navazující období vlastnictví a použití v párování plateb."""

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from svj import api_dluznici, api_lide, banka, lide, prihlaseni
from svj.api import app
from svj.db import Vlastnictvi
from svj.domena import profil
from tests.test_prihlaseni import FalesneJwks, token

PROFIL = profil.nacti("ukazka")
KDO = "vybor@example.cz"


def _osoba(s, jmeno, **kw):
    return lide.pridej_osobu(s, lide.UdajeOsoby(jmeno=jmeno, **kw), KDO)


def _clen(o, podil=None):
    return [lide.ClenVlastnictvi(o.id, podil)]


def test_prevod_uzavre_predchozi_vlastnictvi(session):
    novak = _osoba(session, "Jan Novák", adresa="Ukázková 12, Praha")
    svoboda = _osoba(session, "Eva Svobodová")
    lide.zapis_vlastnictvi(session, PROFIL, "1001/3", date(2020, 1, 1), _clen(novak), "", KDO)
    lide.zapis_vlastnictvi(
        session, PROFIL, "1001/3", date(2025, 6, 15), _clen(svoboda), "vklad V-1/2025", KDO
    )

    prvni, druhe = lide.vlastnictvi(session, "1001/3")
    assert (prvni.plati_od, prvni.plati_do) == (date(2020, 1, 1), date(2025, 6, 14))
    assert (druhe.plati_od, druhe.plati_do) == (date(2025, 6, 15), None)
    assert [o.jmeno for o in lide.vlastnici_k(session, date(2025, 6, 14))["1001/3"]] == [
        "Jan Novák"
    ]
    assert [o.jmeno for o in lide.vlastnici_k(session, date(2025, 6, 15))["1001/3"]] == [
        "Eva Svobodová"
    ]


def test_doplneni_starsi_historie_a_zakaz_doprostred(session):
    a, b, c = (_osoba(session, j) for j in ("A", "B", "C"))
    lide.zapis_vlastnictvi(session, PROFIL, "1001/1", date(2022, 1, 1), _clen(b), "", KDO)
    lide.zapis_vlastnictvi(session, PROFIL, "1001/1", date(2024, 1, 1), _clen(c), "", KDO)
    lide.zapis_vlastnictvi(session, PROFIL, "1001/1", date(2015, 3, 1), _clen(a), "", KDO)
    assert [(v.plati_od, v.plati_do) for v in lide.vlastnictvi(session, "1001/1")] == [
        (date(2015, 3, 1), date(2021, 12, 31)),
        (date(2022, 1, 1), date(2023, 12, 31)),
        (date(2024, 1, 1), None),
    ]
    with pytest.raises(lide.ChybaLidi, match="Nové vlastnictví musí začít"):
        lide.zapis_vlastnictvi(session, PROFIL, "1001/1", date(2023, 1, 1), _clen(a), "", KDO)


def test_uprava_data_posune_predchozi(session):
    a, b = _osoba(session, "A"), _osoba(session, "B")
    lide.zapis_vlastnictvi(session, PROFIL, "1001/2", date(2020, 1, 1), _clen(a), "", KDO)
    druhe = lide.zapis_vlastnictvi(session, PROFIL, "1001/2", date(2025, 3, 1), _clen(b), "", KDO)

    lide.uprav_vlastnictvi(session, druhe.id, date(2025, 5, 1), _clen(b), "oprava", KDO)
    assert lide.vlastnictvi(session, "1001/2")[0].plati_do == date(2025, 4, 30)
    lide.uprav_vlastnictvi(session, druhe.id, date(2025, 2, 1), _clen(b), "oprava", KDO)
    assert lide.vlastnictvi(session, "1001/2")[0].plati_do == date(2025, 1, 31)
    with pytest.raises(lide.ChybaLidi, match="po začátku předchozího"):
        lide.uprav_vlastnictvi(session, druhe.id, date(2019, 1, 1), _clen(b), "", KDO)


def test_smazani_posledniho_otevre_predchozi(session):
    a, b, c = (_osoba(session, j) for j in ("A", "B", "C"))
    for od, o in ((date(2020, 1, 1), a), (date(2022, 1, 1), b), (date(2024, 1, 1), c)):
        lide.zapis_vlastnictvi(session, PROFIL, "1001/4", od, _clen(o), "", KDO)
    prostredni = lide.vlastnictvi(session, "1001/4")[1]
    with pytest.raises(lide.ChybaLidi, match="uprostřed"):
        lide.smaz_vlastnictvi(session, prostredni.id)
    lide.smaz_vlastnictvi(session, lide.vlastnictvi(session, "1001/4")[-1].id)
    assert lide.vlastnictvi(session, "1001/4")[-1].plati_do is None
    with pytest.raises(lide.ChybaLidi, match="vlastník jednotky"):
        lide.smaz_osobu(session, b.id)
    lide.smaz_osobu(session, c.id)


def test_spoluvlastnici_a_kontroly(session):
    a, b = _osoba(session, "A"), _osoba(session, "B")
    oba = [lide.ClenVlastnictvi(a.id, "1/2"), lide.ClenVlastnictvi(b.id, "1/3")]
    with pytest.raises(lide.ChybaLidi, match="celek"):
        lide.zapis_vlastnictvi(session, PROFIL, "1001/5", date(2020, 1, 1), oba, "", KDO)
    with pytest.raises(lide.ChybaLidi, match="u všech"):
        lide.zapis_vlastnictvi(
            session,
            PROFIL,
            "1001/5",
            date(2020, 1, 1),
            [lide.ClenVlastnictvi(a.id, "1/2"), lide.ClenVlastnictvi(b.id)],
            "",
            KDO,
        )
    manzele = [lide.ClenVlastnictvi(a.id), lide.ClenVlastnictvi(b.id)]
    lide.zapis_vlastnictvi(session, PROFIL, "1001/5", date(2020, 1, 1), manzele, "SJM", KDO)
    assert [o.jmeno for o in lide.vlastnici_k(session, date(2025, 1, 1))["1001/5"]] == ["A", "B"]
    with pytest.raises(lide.ChybaLidi, match="SVJ nemá"):
        lide.zapis_vlastnictvi(session, PROFIL, "9999/1", date(2020, 1, 1), _clen(a), "", KDO)


def test_neplatne_udaje_osoby(session):
    with pytest.raises(lide.ChybaLidi, match="jméno"):
        _osoba(session, "  ")
    with pytest.raises(lide.ChybaLidi, match="E-mail"):
        _osoba(session, "A", email="bez-zavinace")
    with pytest.raises(lide.ChybaLidi, match="tvar"):
        _osoba(session, "A", ucet="12345")
    with pytest.raises(lide.ChybaLidi, match="e-mailovou adresou"):
        _osoba(session, "A", souhlas_email=date(2025, 1, 1))
    o = _osoba(session, "A", email="Jan@Example.CZ", ucet="19-123 457/0800")
    assert (o.email, o.ucet) == ("jan@example.cz", "19-123457/0800")


def test_databaze_nepusti_prekryv(session):
    a = _osoba(session, "A")
    lide.zapis_vlastnictvi(session, PROFIL, "1001/6", date(2020, 1, 1), _clen(a), "", KDO)
    session.add(
        Vlastnictvi(jednotka="1001/6", plati_od=date(2024, 1, 1), plati_do=None, upravil=KDO)
    )
    with pytest.raises(Exception, match="vlastnictvi_neprekryva"):
        session.flush()


def test_navrh_platby_podle_uctu_vlastnika(session):
    a = _osoba(session, "A", ucet="19-123457/0800")
    lide.zapis_vlastnictvi(session, PROFIL, "1001/7", date(2020, 1, 1), _clen(a), "", KDO)
    ucty = lide.jednotky_podle_uctu(session, date(2025, 1, 10))
    assert ucty == {"19-123457/0800": ["1001/7"]}

    class Pohyb:
        castka = 99_900
        vs = None
        protiucet = "19-123457"
        kod_banky = "0800"
        smer = "prijem"

    navrh = banka._navrh_platby_vlastnika(
        Pohyb(), banka.KontextNavrhu(profil=PROFIL, ucty_vlastniku=ucty)
    )
    assert navrh is not None
    assert navrh.vstupy == {"jednotka": "1001/7"}
    assert "účtu vlastníka" in navrh.duvod


@pytest.fixture
def klient(session, monkeypatch):
    monkeypatch.setattr(prihlaseni, "_jwks", lambda: FalesneJwks())
    tovarna = lambda: sessionmaker(session.get_bind())  # noqa: E731
    monkeypatch.setattr(api_lide, "sezeni", tovarna)
    monkeypatch.setattr(api_dluznici, "sezeni", tovarna)
    c = TestClient(app)
    c.headers["Authorization"] = f"Bearer {token()}"
    return c


def test_api_vlastniku(klient):
    r = klient.get("/api/vlastnici")
    assert r.status_code == 200, r.text
    assert len(r.json()["jednotky"]) == 12
    assert r.json()["osoby"] == []

    r = klient.post("/api/vlastnici/osoby", json={"jmeno": "Jan Novák", "adresa": "Praha"})
    assert r.status_code == 200, r.text
    novak = r.json()["osoby"][0]["id"]
    r = klient.post(
        "/api/vlastnici/vlastnictvi",
        json={"jednotka": "1001/1", "plati_od": "2020-01-01", "vlastnici": [{"osoba_id": novak}]},
    )
    assert r.status_code == 200, r.text
    jednotka = next(j for j in r.json()["jednotky"] if j["jednotka"] == "1001/1")
    assert jednotka["vlastnictvi"][0]["vlastnici"] == [{"osoba_id": novak, "podil": None}]

    r = klient.post(
        "/api/vlastnici/vlastnictvi",
        json={"jednotka": "1001/1", "plati_od": "2020-01-01", "vlastnici": [{"osoba_id": novak}]},
    )
    assert r.status_code == 422
    assert "musí začít" in r.json()["detail"]

    r = klient.post("/api/vlastnici/osoby", json={"jmeno": "X", "email": "spatne"})
    assert r.status_code == 422

    r = klient.post(
        "/api/vlastnici/vlastnictvi",
        json={
            "jednotka": "1001/2",
            "plati_od": "2021-05-01",
            "vlastnici": [{"nova": {"jmeno": "Eva Malá"}}, {"osoba_id": novak}],
        },
    )
    assert r.status_code == 200, r.text
    assert sorted(o["jmeno"] for o in r.json()["osoby"]) == ["Eva Malá", "Jan Novák"]

    d = klient.get("/api/dluznici/2025").json()
    j = next(x for x in d["jednotky"] if x["jednotka"] == "1001/1")
    assert j["vlastnici"] == [
        {"jmeno": "Jan Novák", "adresa": "Praha", "email": None, "souhlas_email": False}
    ]


def _predpis_mesice(session, mesic):
    from svj import predpisy
    from svj.db import Obdobi

    if session.get(Obdobi, 2026) is None:
        session.add(Obdobi(rok=2026, stav="otevrene"))
        session.flush()
    nast = predpisy.nacti(PROFIL)
    return predpisy.vygeneruj(
        session, PROFIL, nast, 2026, mesic, zauctoval=KDO, dnes=date(2026, 6, 1)
    )


def test_dluh_zustava_prevodci(session):
    from svj import dluznici, predpisy, prevody

    nast = predpisy.nacti(PROFIL)
    for m in (3, 4, 5):
        _predpis_mesice(session, m)
    dvorak, novak = _osoba(session, "Petr Dvořák"), _osoba(session, "Jan Novák")
    lide.zapis_vlastnictvi(session, PROFIL, "1001/3", date(2020, 1, 1), _clen(dvorak), "", KDO)
    v = lide.zapis_vlastnictvi(session, PROFIL, "1001/3", date(2026, 4, 15), _clen(novak), "", KDO)

    p = prevody.prevod(session, PROFIL, nast, v.id, date(2026, 5, 10))
    assert p.prevodce == "Petr Dvořák"
    # Březen a duben patří převodci (duben podle volby "dosavadni"), květen novému vlastníkovi.
    assert [(d.popis, d.navrh) for d in p.dluhy] == [
        ("Zálohy za březen 2026", True),
        ("Zálohy za duben 2026", True),
        ("Zálohy za květen 2026", False),
    ]
    mesicni = p.dluhy[0].zbyva

    prevody.ponech_prevodci(
        session, PROFIL, nast, v.id, [d.klic for d in p.dluhy if d.navrh], KDO, date(2026, 5, 10)
    )
    jednotka = next(
        d
        for d in dluznici.prehled(session, PROFIL, nast, 2026, date(2026, 5, 10))
        if d.jednotka == "1001/3"
    )
    assert jednotka.saldo == mesicni
    drivejsi = predpisy.drivejsi_vlastnici(session, 2026)
    assert [(d.jednotka, d.vlastnik, d.castka) for d in drivejsi] == [
        ("1001/3", "Petr Dvořák", 2 * mesicni)
    ]
    assert drivejsi[0].popis.startswith("Zálohy za březen 2026, Zálohy za duben 2026")
    # Přesun dluhu není platba: snižuje předepsané, zaplaceno zůstává nula.
    s = next(x for x in predpisy.saldo(session, PROFIL, 2026) if x.jednotka == "1001/3")
    assert (s.predepsano, s.zaplaceno) == (mesicni, 0)
    with pytest.raises(prevody.ChybaPrevodu, match="už jsou zapsané"):
        prevody.ponech_prevodci(session, PROFIL, nast, v.id, ["x"], KDO, date(2026, 5, 10))
    assert prevody.prevod(session, PROFIL, nast, v.id, date(2026, 5, 10)).zapis is not None


def test_volba_novy_vlastnik_plati_mesic_prevodu(session):
    from dataclasses import replace

    from svj import predpisy, prevody

    profil_novy = replace(PROFIL, predpis_mesice_prevodu="novy")
    nast = predpisy.nacti(PROFIL)
    for m in (3, 4):
        _predpis_mesice(session, m)
    a, b = _osoba(session, "A"), _osoba(session, "B")
    lide.zapis_vlastnictvi(session, PROFIL, "1001/4", date(2020, 1, 1), _clen(a), "", KDO)
    v = lide.zapis_vlastnictvi(session, PROFIL, "1001/4", date(2026, 4, 15), _clen(b), "", KDO)
    p = prevody.prevod(session, profil_novy, nast, v.id, date(2026, 4, 20))
    assert [d.navrh for d in p.dluhy] == [True, False]
