"""Měřidla, odečty, výměna měřidla a roční spotřeba."""

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from svj import api_meridla, meridla, prihlaseni
from svj.api import app
from svj.domena import profil
from tests.test_prihlaseni import FalesneJwks, token

PROFIL = profil.nacti("ukazka")
KDO = "vybor@example.cz"


def _vodomer(s, jednotka="1001/3", cislo="SV-1", od=date(2024, 1, 1), stav="0"):
    u = meridla.UdajeMeridla(jednotka, "studena_voda", cislo, od)
    return meridla.pridej_meridlo(s, PROFIL, u, Decimal(stav), KDO)


def test_stav_z_textu():
    assert meridla.stav("1 234,5") == Decimal("1234.5")
    assert meridla.stav("12.125") == Decimal("12.125")
    for spatne in ("-1", "abc", "1,2345"):
        with pytest.raises(meridla.ChybaMeridel):
            meridla.stav(spatne)


def test_odecet_nesmi_klesnout_ani_mimo_osazeni(session):
    m = _vodomer(session)
    meridla.zapis_odecet(session, m.id, date(2025, 12, 31), Decimal("50"), "", KDO)
    with pytest.raises(meridla.ChybaMeridel, match="menší než"):
        meridla.zapis_odecet(session, m.id, date(2026, 6, 30), Decimal("40"), "", KDO)
    with pytest.raises(meridla.ChybaMeridel, match="větší než pozdější"):
        meridla.zapis_odecet(session, m.id, date(2025, 6, 30), Decimal("60"), "", KDO)
    with pytest.raises(meridla.ChybaMeridel, match="nepatří"):
        meridla.zapis_odecet(session, m.id, date(2023, 12, 31), Decimal("0"), "", KDO)
    # Odečet ke stejnému dni se přepíše.
    meridla.zapis_odecet(session, m.id, date(2025, 12, 31), Decimal("51"), "", KDO)
    assert [o.stav for o in m.odecty] == [Decimal("0"), Decimal("51")]


def test_spotreba_s_vymenou_je_soucet_obou_meridel(session):
    m = _vodomer(session)
    meridla.zapis_odecet(session, m.id, date(2025, 12, 31), Decimal("100"), "", KDO)
    nove = meridla.vymen(
        session, m.id, date(2026, 5, 10), Decimal("130"), "SV-2", Decimal("0"), KDO
    )
    meridla.zapis_odecet(session, nove.id, date(2027, 1, 3), Decimal("45.5"), "", KDO)
    session.flush()

    [x] = meridla.spotreba(session, 2026)
    assert (x.jednotka, x.druh, x.spotreba, x.upozorneni) == (
        "1001/3",
        "studena_voda",
        Decimal("75.5"),
        [],
    )
    assert [c.spotreba for c in x.casti] == [Decimal("30"), Decimal("45.5")]
    assert m.odstraneno_do == date(2026, 5, 10)

    with pytest.raises(meridla.ChybaMeridel, match="už je odstraněné"):
        meridla.vymen(session, m.id, date(2026, 6, 1), Decimal("1"), "X", Decimal("0"), KDO)
    with pytest.raises(meridla.ChybaMeridel, match="Nejdřív smažte"):
        meridla.smaz_meridlo(session, m.id)

    # Smazání náhrady vrátí staré měřidlo do provozu bez stavu z výměny.
    meridla.smaz_meridlo(session, nove.id)
    session.flush()
    assert m.odstraneno_do is None
    assert [o.datum for o in m.odecty] == [date(2024, 1, 1), date(2025, 12, 31)]


def test_chybejici_odecet_spotrebu_nespocita(session):
    m = _vodomer(session)
    meridla.zapis_odecet(session, m.id, date(2025, 12, 31), Decimal("100"), "", KDO)
    session.flush()
    [x] = meridla.spotreba(session, 2026)
    assert x.spotreba is None
    assert x.upozorneni == ["Měřidlo SV-1: chybí odečet kolem 31. 12. 2026."]


@pytest.fixture
def klient(session, monkeypatch):
    monkeypatch.setattr(prihlaseni, "_jwks", lambda: FalesneJwks())
    monkeypatch.setattr(api_meridla, "sezeni", lambda: sessionmaker(session.get_bind()))
    c = TestClient(app)
    c.headers["Authorization"] = f"Bearer {token()}"
    return c


def test_api_meridel(klient):
    r = klient.post(
        "/api/meridla",
        json={
            "jednotka": "1001/1",
            "druh": "tepla_voda",
            "vyrobni_cislo": "TV-7",
            "osazeno_od": "2025-01-01",
            "pocatecni_stav": "3,2",
        },
    )
    assert r.status_code == 200, r.text
    [m] = r.json()["meridla"]
    assert m["odecty"][0]["stav"] == "3.200"

    r = klient.post(
        "/api/meridla/odecty",
        json={"datum": "2025-12-31", "stavy": [{"meridlo_id": m["id"], "stav": "1"}]},
    )
    assert r.status_code == 422
    assert "menší než" in r.json()["detail"]

    r = klient.post(
        "/api/meridla/odecty",
        json={
            "datum": "2025-12-31",
            "zdroj": "odečet výboru",
            "stavy": [{"meridlo_id": m["id"], "stav": "20,7"}],
        },
    )
    assert r.status_code == 200, r.text

    r = klient.get("/api/meridla/spotreba", params={"rok": 2025})
    assert r.status_code == 200, r.text
    [x] = r.json()
    assert (x["jednotka"], x["spotreba"]) == ("1001/1", "17.500")
