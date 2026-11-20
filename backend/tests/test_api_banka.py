"""API banky přes HTTP, nad testovací databází."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from svj import api_banka, prihlaseni
from svj.api import app
from tests.test_banka import PROFIL, _leden
from tests.test_prihlaseni import FalesneJwks, token


@pytest.fixture
def klient(session, monkeypatch):
    monkeypatch.setattr(prihlaseni, "_jwks", lambda: FalesneJwks())
    monkeypatch.setattr(api_banka, "sezeni", lambda: sessionmaker(session.get_bind()))
    c = TestClient(app)
    c.headers["Authorization"] = f"Bearer {token()}"
    return c


def test_nahrani_a_zauctovani(klient):
    r = klient.post("/api/banka/vypisy?nazev=leden.gpc", content=_leden())
    assert r.status_code == 409
    assert r.json()["detail"] == {"kod": "neznamy_ucet", "cislo": "2800000001"}

    r = klient.post("/api/banka/vypisy?nazev=leden.gpc&ucel=provozni", content=_leden())
    assert r.status_code == 200, r.text
    assert r.json()[0]["pocet_pohybu"] == 4

    b = klient.get("/api/banka").json()
    assert b["nezauctovano"] == 4
    assert [u["ucel"] for u in b["ucty"]] == ["provozni", "fond_oprav"]
    assert b["ucty"][0]["posledni_vypis"] == "1/2025"
    assert b["ucty"][0]["pohyby_do"] == "2025-01-15"
    assert "1001/12" in b["jednotky"]
    poplatek = next(p for p in b["pohyby"] if p["castka"] == -5000)
    assert poplatek["navrh"]["operace"] == "poplatek-banky"
    platba = next(p for p in b["pohyby"] if p["castka"] == 1_038_000)
    assert platba["protiucet"] == "19-123457/0800"

    r = klient.post(
        f"/api/banka/pohyby/{platba['id']}",
        json={"operace": "uhrada-predpisu", "vstupy": {"jednotka": "1001/5"}},
    )
    assert r.status_code == 200, r.text
    assert r.json()["zauctovano"]["zapis"] == "1/2025"

    r = klient.post(
        f"/api/banka/pohyby/{platba['id']}",
        json={"operace": "uhrada-predpisu", "vstupy": {"jednotka": "1001/5"}},
    )
    assert r.status_code == 422 and "už je zaúčtovaný" in r.json()["detail"]
    assert klient.get("/api/banka").json()["nezauctovano"] == 3
    assert len(klient.get("/api/banka?vse=true").json()["pohyby"]) == 4


def test_vadny_soubor(klient):
    r = klient.post("/api/banka/vypisy", content=b"nesmysl")
    assert r.status_code == 422 and "nepodařilo přečíst" in r.json()["detail"]


def test_predpisy_api(klient, session, monkeypatch):
    from svj import api_predpisy
    from svj.db import Obdobi

    monkeypatch.setattr(api_predpisy, "sezeni", lambda: sessionmaker(session.get_bind()))
    session.add(Obdobi(rok=2026, stav="otevrene"))
    session.commit()
    p = klient.get("/api/predpisy/2026").json()
    assert [m["stav"] for m in p["mesice"][:4]] == [
        "bez_predpisu",
        "bez_predpisu",
        "lze",
        "pozdeji",
    ]
    j6 = next(j for j in p["jednotky"] if j["oznaceni"] == "1001/6")
    assert (j6["mesicne"], j6["osob"], j6["saldo"]) == (1_274_000, 1, 0)
    assert klient.post("/api/predpisy/2026/2").status_code == 422
    p = klient.post("/api/predpisy/2026/3").json()
    assert p["mesice"][2] == {**p["mesice"][2], "stav": "zauctovano", "zapis": "1/2026"}
    assert [m["stav"] for m in p["mesice"][3:5]] == ["lze", "pozdeji"]
    assert klient.post("/api/predpisy/2026/5").status_code == 422
    j6 = next(j for j in p["jednotky"] if j["oznaceni"] == "1001/6")
    assert (j6["predepsano"], j6["saldo"]) == (1_274_000, 1_274_000)


def test_pocatecni_stavy_api(klient, session, monkeypatch):
    from svj import api_pocatecni, api_predpisy
    from svj.db import Obdobi
    from tests.test_pocatecni import POLOZKY, ROZVAHOVE

    for modul in (api_pocatecni, api_predpisy):
        monkeypatch.setattr(modul, "sezeni", lambda: sessionmaker(session.get_bind()))
    session.add(Obdobi(rok=2026, stav="otevrene"))
    session.commit()

    p = klient.get("/api/pocatecni/2026").json()
    assert p["zauctovano"] is None and p["zustatky"] == []
    assert {
        "ucet": "311300",
        "nazev": "Pohledávky z vyúčtování minulých let",
        "vlastnici": True,
    } in p["ucty"]
    assert [b["ucet"] for b in p["banka"]] == ["221100", "221200"]

    telo = {
        "zustatky": [{"ucet": u, "castka": c} for u, c in ROZVAHOVE.items()],
        "polozky": [
            {
                "ucet": x.ucet,
                "castka": x.castka,
                "jednotka": x.jednotka,
                "popis": x.popis,
                "drivejsi_vlastnik": x.drivejsi_vlastnik,
            }
            for x in POLOZKY
        ],
    }
    r = klient.post("/api/pocatecni/2026", json={**telo, "polozky": telo["polozky"][1:]})
    assert r.status_code == 422 and "Rozpis účtu 311200" in r.json()["detail"]
    r = klient.post("/api/pocatecni/2026", json=telo)
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["zauctovano"]["zapis"] == "1/2026"
    assert {z["ucet"]: z["castka"] for z in p["zustatky"]} == ROZVAHOVE
    assert len(p["polozky"]) == 5
    assert klient.post("/api/pocatecni/2026", json=telo).status_code == 422

    p = klient.get("/api/predpisy/2026").json()
    assert p["pocatecni_stavy"] is True
    j3 = next(j for j in p["jednotky"] if j["oznaceni"] == "1001/3")
    assert (j3["pocatek"], j3["saldo"]) == (10_000_000, 10_000_000)
    assert j3["pocatek_rozpis"] == [{"popis": "Vyúčtování 2024", "castka": 10_000_000}]
    assert p["drivejsi_vlastnici"] == [
        {
            "popis": "Vyúčtování 2023",
            "castka": -731_700,
            "jednotka": "1001/3",
            "vlastnik": "Původní vlastník",
        }
    ]


def test_denik_a_storno_api(klient, session, monkeypatch):
    from svj import api_denik, api_predpisy
    from svj.db import Obdobi

    for modul in (api_denik, api_predpisy):
        monkeypatch.setattr(modul, "sezeni", lambda: sessionmaker(session.get_bind()))
    session.add(Obdobi(rok=2026, stav="otevrene"))
    session.commit()
    klient.post("/api/predpisy/2026/3")
    d = klient.get("/api/denik/2026").json()
    (z,) = d["zapisy"]
    assert (z["cislo"], z["nazev_operace"], z["stornovan_zapisem"]) == (
        "1/2026",
        "Měsíční předpis záloh",
        None,
    )
    assert z["castka"] == 15_483_200 and z["radky"][0]["nazev_uctu"]

    r = klient.post(f"/api/denik/zapisy/{z['id']}/storno", json={"duvod": ""})
    assert r.status_code == 422 and "proč" in r.json()["detail"]
    r = klient.post(f"/api/denik/zapisy/{z['id']}/storno", json={"duvod": "špatné osoby"})
    assert r.status_code == 200, r.text
    storno, puvodni = r.json()["zapisy"]
    assert (storno["cislo"], storno["stornuje_zapis"], puvodni["stornovan_zapisem"]) == (
        "2/2026",
        "1/2026",
        "2/2026",
    )
    p = klient.get("/api/predpisy/2026").json()
    assert p["mesice"][2]["stav"] == "lze"


def test_faktury_api(klient, session, monkeypatch):
    from svj import api_faktury

    monkeypatch.setattr(api_faktury, "sezeni", lambda: sessionmaker(session.get_bind()))
    telo = {
        "dodavatel": "Úklid Šťastný",
        "castka": 484_000,
        "duzp": "2025-01-02",
        "splatnost": "2025-01-14",
        "druh": "UKLID",
        "vs": "2213243",
        "cislo_dodavatele": "FV-1",
    }
    r = klient.post("/api/faktury", json={**telo, "druh": "FOND_OPRAV"})
    assert r.status_code == 422 and "kdo ji schválil" in r.json()["detail"]
    r = klient.post("/api/faktury", json=telo)
    assert r.status_code == 200, r.text
    p = r.json()
    (f,) = p["faktury"]
    assert (f["cislo"], f["stav"], f["zbyva"], f["nazev_druhu"]) == (
        "2025001",
        "po_splatnosti",
        484_000,
        "Úklid",
    )
    assert p["k_uhrade"] == 484_000 and p["dodavatele"] == ["Úklid Šťastný"]
    assert {
        "id": "FOND_OPRAV",
        "nazev": "Oprava hrazená z fondu oprav",
        "skupina": "Fond oprav",
    } in p["druhy"]

    klient.post("/api/banka/vypisy?nazev=leden.gpc&ucel=provozni", content=_leden())
    b = klient.get("/api/banka").json()
    assert [x["cislo"] for x in b["faktury"]] == ["2025001"]
    vydaj = next(x for x in b["pohyby"] if x["castka"] == -484_000)
    assert vydaj["navrh"]["vstupy"] == {"faktura": "2025001"}
    r = klient.post(f"/api/banka/pohyby/{vydaj['id']}", json=vydaj["navrh"])
    assert r.status_code == 200, r.text
    assert klient.get("/api/faktury/2025").json()["faktury"][0]["stav"] == "uhrazena"


def test_dluznici_api(klient, session, monkeypatch):
    from svj import api_dluznici, api_predpisy
    from svj.db import Obdobi

    for modul in (api_dluznici, api_predpisy):
        monkeypatch.setattr(modul, "sezeni", lambda: sessionmaker(session.get_bind()))
    session.add(Obdobi(rok=2026, stav="otevrene"))
    session.commit()
    assert klient.post("/api/predpisy/2026/3").status_code == 200
    d = klient.get("/api/dluznici/2026").json()
    assert d["svj"] == PROFIL.nazev and d["ucet"] is None
    j = d["jednotky"][0]
    assert j["jednotka"] == "1001/1" and j["od"] == "2026-03-15"
    assert j["polozky"][0]["popis"] == "Zálohy za březen 2026"
    assert d["celkem_po_splatnosti"] == sum(x["po_splatnosti"] for x in d["jednotky"]) > 0


def test_vyuctovani_spravy_api(klient, session, monkeypatch):
    from svj import api_predpisy, api_vyuctovani
    from svj.db import Obdobi

    for modul in (api_vyuctovani, api_predpisy):
        monkeypatch.setattr(modul, "sezeni", lambda: sessionmaker(session.get_bind()))
    session.add(Obdobi(rok=2026, stav="otevrene"))
    session.commit()
    assert klient.post("/api/predpisy/2026/3").status_code == 200
    v = klient.get("/api/vyuctovani-spravy/2026").json()
    assert [p["kod"] for p in v["polozky"]] == ["DROBNE_OPRAVY", "OSTATNI", "POJISTENI", "SPRAVA"]
    assert v["polozky"][3]["jak_se_deli"] == "každá jednotka stejně"
    j = v["jednotky"][0]
    assert j["podil"] == "543/8600" and j["zalohy"] == 5_400 + 30_000 + 40_000 + 85_000
    assert j["rozdil"] == -j["zalohy"]  # zatím žádné náklady
    assert v["zapis"] is None and v["proc_nejde"]
    r = klient.post("/api/vyuctovani-spravy/2026")
    assert r.status_code == 422
