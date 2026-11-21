"""Verze předpisu zadané v aplikaci: uložení, přednost před souborem, zaúčtované měsíce."""

import dataclasses
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from svj import api_verze_predpisu, predpisy, prihlaseni
from svj.api import app
from svj.db import Obdobi
from tests.test_banka import PROFIL
from tests.test_prihlaseni import FalesneJwks, token

ZE_SOUBORU = predpisy.nacti(PROFIL).verze[-1]


def _nova(plati_od: date, fond: int) -> predpisy.Verze:
    slozky = [
        dataclasses.replace(s, sazba=fond) if s.kod == "FOND_OPRAV" else s
        for s in ZE_SOUBORU.slozky
    ]
    return dataclasses.replace(ZE_SOUBORU, plati_od=plati_od, zdroj="Shromáždění", slozky=slozky)


def _rok(session):
    session.add(Obdobi(rok=2026, stav="otevrene"))
    session.commit()


def test_verze_z_aplikace_plati_od_data(session):
    _rok(session)
    predpisy.uloz_verzi(session, PROFIL, _nova(date(2027, 1, 1), 6_000), "x", None)
    session.commit()
    nast = predpisy.nacti(PROFIL, session)
    assert [v.plati_od for v in nast.verze] == [date(2026, 3, 1), date(2027, 1, 1)]
    assert nast.verze[-1].v_aplikaci and nast.verze[-1].upravil == "x"
    j6 = "1001/6"  # 62,40 m²
    assert predpisy.spocitej(PROFIL, nast.pro_mesic(2026, 12))[j6]["FOND_OPRAV"] == 280_800
    assert predpisy.spocitej(PROFIL, nast.pro_mesic(2027, 1))[j6]["FOND_OPRAV"] == 374_400

    with pytest.raises(predpisy.ChybaPredpisu, match="už v aplikaci je"):
        predpisy.uloz_verzi(session, PROFIL, _nova(date(2027, 1, 1), 1), "x", None)

    # Posunutí data přepíše tutéž verzi, nepřidá další.
    predpisy.uloz_verzi(session, PROFIL, _nova(date(2027, 2, 1), 6_000), "y", date(2027, 1, 1))
    session.commit()
    assert [v.plati_od for v in predpisy.nacti(PROFIL, session).verze][-1] == date(2027, 2, 1)
    assert len(predpisy.nacti(PROFIL, session).verze) == 2


def test_verze_z_aplikace_nahradi_soubor_se_stejnym_datem(session):
    _rok(session)
    predpisy.uloz_verzi(session, PROFIL, _nova(date(2026, 3, 1), 5_000), "x", None)
    session.commit()
    [v] = predpisy.nacti(PROFIL, session).verze
    assert v.v_aplikaci and v.zdroj == "Shromáždění"


def test_zauctovane_mesice_se_nemeni(session):
    _rok(session)
    nast = predpisy.nacti(PROFIL, session)
    predpisy.vygeneruj(session, PROFIL, nast, 2026, 3, zauctoval="x", dnes=date(2026, 3, 1))
    session.commit()
    assert predpisy.prvni_mesic_ke_zmene(session) == date(2026, 4, 1)
    with pytest.raises(predpisy.ChybaPredpisu, match="nejdřív od 1. 4. 2026"):
        predpisy.uloz_verzi(session, PROFIL, _nova(date(2026, 3, 1), 5_000), "x", None)
    predpisy.uloz_verzi(session, PROFIL, _nova(date(2026, 4, 1), 5_000), "x", None)
    session.commit()
    predpisy.smaz_verzi(session, date(2026, 4, 1))
    with pytest.raises(predpisy.ChybaPredpisu, match="jen předpis zadaný v aplikaci"):
        predpisy.smaz_verzi(session, date(2026, 3, 1))


def test_neuplna_verze_se_neulozi(session):
    _rok(session)
    v = _nova(date(2027, 1, 1), 6_000)
    v = dataclasses.replace(v, pevne={})  # chybí pevné částky
    with pytest.raises((predpisy.ChybaPredpisu, KeyError)):
        predpisy.uloz_verzi(session, PROFIL, v, "x", None)


@pytest.fixture
def klient(session, monkeypatch):
    monkeypatch.setattr(prihlaseni, "_jwks", lambda: FalesneJwks())
    monkeypatch.setattr(api_verze_predpisu, "sezeni", lambda: sessionmaker(session.get_bind()))
    c = TestClient(app)
    c.headers["Authorization"] = f"Bearer {token()}"
    return c


def test_api(session, klient):
    _rok(session)
    p = klient.get("/api/verze-predpisu").json()
    [v] = p["verze"]
    assert not v["v_aplikaci"] and not v["upravitelna"]
    assert v["mesicne"]["1001/6"] == 1_274_000
    assert {"role": "zalohy_dlouhodobe", "nazev": "Fond oprav", "skupina": "fond_oprav"} in p[
        "role"
    ]
    assert any(r["role"] == "zalohy_sluzby.TEPLO" and r["skupina"] == "sluzby" for r in p["role"])

    nova = {k: v[k] for k in ("slozky", "pevne", "osoby")} | {"plati_od": "2027-01-01"}
    nova["slozky"][0]["sazba"] = 6_000
    n = klient.post("/api/verze-predpisu/nahled", json=nova).json()
    assert n["chyba"] is None and n["mesicne"]["1001/6"] == 1_274_000 + 93_600

    spatna = nova | {"slozky": [{**nova["slozky"][0], "role": "neexistuje"}]}
    assert klient.post("/api/verze-predpisu/nahled", json=spatna).json()["chyba"]
    assert (
        klient.put("/api/verze-predpisu", json={"puvodni": None, "verze": spatna}).status_code
        == 422
    )

    r = klient.put("/api/verze-predpisu", json={"puvodni": None, "verze": nova})
    assert r.status_code == 200, r.text
    posledni = r.json()["verze"][-1]
    assert (
        posledni["v_aplikaci"] and posledni["upravitelna"] and posledni["plati_od"] == "2027-01-01"
    )

    r = klient.delete("/api/verze-predpisu/2027-01-01")
    assert r.status_code == 200 and len(r.json()["verze"]) == 1
