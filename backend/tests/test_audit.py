"""Auditní záznam změn a upozornění na změnu po schválení."""

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker

from svj import (
    api_historie,
    api_rozhodnuti,
    api_verze_predpisu,
    audit,
    lide,
    predpisy,
    prihlaseni,
    rozhodnuti,
)
from svj.api import app
from svj.db import AuditniZaznam, Obdobi
from tests.test_lide import KDO, PROFIL, _clen, _osoba
from tests.test_prihlaseni import FalesneJwks, token
from tests.test_rozhodnuti import _zalohy
from tests.test_verze_predpisu import _nova


def _zaznamy(s, druh=None):
    return list(reversed(audit.zaznamy(s, druh=druh)))


def _rozdily(z):
    return {r.pole: (r.pred, r.po) for r in audit.rozdily(z)}


def test_zmena_osoby_a_vlastniku(session):
    novak = _osoba(session, "Jan Novák", email="jan@example.cz")
    svoboda = _osoba(session, "Eva Svobodová")
    session.commit()
    lide.uprav_osobu(
        session, novak.id, lide.UdajeOsoby(jmeno="Jan Novák", email="novak@example.cz"), "eva@x"
    )
    lide.zapis_vlastnictvi(session, PROFIL, "1001/3", date(2020, 1, 1), _clen(novak), "", KDO)
    session.commit()
    v = lide.vlastnictvi(session, "1001/3")[0]
    clenove = [lide.ClenVlastnictvi(novak.id, "1/2"), lide.ClenVlastnictvi(svoboda.id, "1/2")]
    audit.duvod(session, "Oprava podle výpisu z katastru")
    lide.uprav_vlastnictvi(session, v.id, v.plati_od, clenove, "LV 123", KDO)
    session.commit()

    pridani, _, uprava = _zaznamy(session, "osoba")
    assert (pridani.akce, pridani.nazev, pridani.kdo, pridani.pred) == (
        "pridani",
        "Jan Novák",
        KDO,
        None,
    )
    assert uprava.kdo == "eva@x"
    assert _rozdily(uprava) == {"E-mail": ("jan@example.cz", "novak@example.cz")}

    zapis, zmena = _zaznamy(session, "vlastnictvi")
    assert zapis.nazev == "Vlastníci jednotky 1001/3 od 1. 1. 2020"
    assert _rozdily(zapis)["Vlastníci"] == ("—", "Jan Novák")
    assert zmena.duvod == "Oprava podle výpisu z katastru"
    assert _rozdily(zmena) == {
        "Vlastníci": ("Jan Novák", "Jan Novák (1/2), Eva Svobodová (1/2)"),
        "Podle čeho": ("—", "LV 123"),
    }

    # Důvod platí jen do konce transakce. Věc, která vznikla a zanikla v jedné transakci,
    # v historii není.
    docasny = _osoba(session, "Petr Dočasný")
    lide.smaz_osobu(session, _osoba(session, "Pavel Omyl").id)
    session.commit()
    lide.smaz_osobu(session, docasny.id)
    session.commit()
    *_, pridani, smazani = _zaznamy(session, "osoba")
    assert (pridani.akce, pridani.nazev) == ("pridani", "Petr Dočasný")
    assert (smazani.akce, smazani.nazev, smazani.duvod, smazani.po) == (
        "smazani",
        "Petr Dočasný",
        "",
        None,
    )
    assert "Pavel Omyl" not in {z.nazev for z in _zaznamy(session)}


def test_zaznam_nejde_zmenit(session):
    _osoba(session, "Jan Novák")
    session.commit()
    for prikaz in ("UPDATE auditni_zaznam SET kdo = 'jiny'", "DELETE FROM auditni_zaznam"):
        with pytest.raises(DBAPIError, match="nejde změnit"):
            session.execute(text(prikaz))
        session.rollback()


def test_zmena_schvaleneho_predpisu(session):
    session.add(Obdobi(rok=2026, stav="otevrene"))
    predpisy.uloz_verzi(session, PROFIL, _nova(date(2027, 1, 1), 6_000), KDO, None)
    r = _zalohy(session)
    session.commit()
    klic = "predpis:2027-01-01"
    rozhodnuti.prirad(session, PROFIL, predpisy.nacti(PROFIL, session), klic, r.id, KDO)
    session.commit()
    assert klic not in {p.klic for p in rozhodnuti.bez_rozhodnuti(session, PROFIL, _nast(session))}

    audit.kdo(session, "eva@x")
    audit.duvod(session, "Překlep v sazbě fondu oprav")
    predpisy.uloz_verzi(session, PROFIL, _nova(date(2027, 1, 1), 6_500), KDO, date(2027, 1, 1))
    session.commit()

    nast = _nast(session)
    [zmeneny] = [p for p in rozhodnuti.bez_rozhodnuti(session, PROFIL, nast) if p.klic == klic]
    assert zmeneny.zmeneno_po_schvaleni
    d = rozhodnuti.dolozeni(session, rozhodnuti.polozky(PROFIL, nast))[klic]
    assert not d.platne and d.rozhodnuti_id == r.id
    assert (d.zmena.kdo, d.zmena.duvod) == ("eva@x", "Překlep v sazbě fondu oprav")
    assert _rozdily(d.zmena) == {"Složka Fond oprav": ("60,00 Kč za m²", "65,00 Kč za m²")}

    # Výbor ověří, že shromáždění schválilo i tuto podobu, a rozhodnutí potvrdí znovu.
    rozhodnuti.prirad(session, PROFIL, nast, klic, r.id, KDO)
    session.commit()
    assert rozhodnuti.dolozeni(session, rozhodnuti.polozky(PROFIL, nast))[klic].platne
    potvrzeni = _zaznamy(session, "prirazeni_rozhodnuti")[-1]
    assert potvrzeni.nazev == "Výše záloh od 1. 1. 2027"
    assert potvrzeni.duvod == "Rozhodnutí potvrzené i pro změněnou podobu."
    assert list(_rozdily(potvrzeni)) == ["Otisk schválené podoby"]


def _nast(s):
    return predpisy.nacti(PROFIL, s)


def test_znovuotevreni_roku_je_v_historii(session):
    from svj import uzavreni

    session.get(Obdobi, 2024).stav = "uzavrene"
    session.add(Obdobi(rok=2026, stav="otevrene"))
    session.commit()
    # Uzavřený rok bez zápisů (počáteční stav testů) jde znovu otevřít.
    uzavreni.znovu_otevri(session, 2024, duvod="Chybí faktura za prosinec", zauctoval="eva@x")
    session.commit()
    z = _zaznamy(session, "obdobi")[-1]
    assert (z.nazev, z.kdo, z.duvod) == ("Účetní rok 2024", "eva@x", "Chybí faktura za prosinec")
    assert _rozdily(z) == {"Stav roku": ("uzavřený", "otevřený")}


@pytest.fixture
def klient(session, monkeypatch):
    monkeypatch.setattr(prihlaseni, "_jwks", lambda: FalesneJwks())
    for modul in (api_historie, api_rozhodnuti, api_verze_predpisu):
        monkeypatch.setattr(modul, "sezeni", lambda: sessionmaker(session.get_bind()))
    c = TestClient(app)
    c.headers["Authorization"] = f"Bearer {token()}"
    return c


def test_api_zmena_po_schvaleni(klient, session):
    session.add(Obdobi(rok=2026, stav="otevrene"))
    predpisy.uloz_verzi(session, PROFIL, _nova(date(2027, 1, 1), 6_000), KDO, None)
    r = _zalohy(session)
    session.commit()
    ok = klient.put(
        "/api/rozhodnuti/prirazeni", json={"klic": "predpis:2027-01-01", "rozhodnuti_id": r.id}
    )
    assert ok.status_code == 200, ok.text

    verze = next(
        v
        for v in klient.get("/api/verze-predpisu").json()["verze"]
        if v["plati_od"] == "2027-01-01"
    )
    assert verze["schvaleni"]["rozhodnuti"].startswith("Shromáždění 12. 2. 2026, bod 4")
    assert verze["schvaleni"]["zmeneno_po_schvaleni"] is None
    zmena = {k: verze[k] for k in ("plati_od", "zdroj", "slozky", "pevne", "osoby")}
    zmena["slozky"] = [
        s | {"sazba": 6_500} if s["kod"] == "FOND_OPRAV" else s for s in zmena["slozky"]
    ]

    bez = klient.put("/api/verze-predpisu", json={"puvodni": "2027-01-01", "verze": zmena})
    assert bez.status_code == 422 and "proč ho po schválení měníte" in bez.json()["detail"]
    s_duvodem = klient.put(
        "/api/verze-predpisu",
        json={"puvodni": "2027-01-01", "verze": zmena, "duvod": "Překlep v sazbě"},
    )
    assert s_duvodem.status_code == 200, s_duvodem.text
    verze = next(v for v in s_duvodem.json()["verze"] if v["plati_od"] == "2027-01-01")
    zmeneno = verze["schvaleni"]["zmeneno_po_schvaleni"]
    assert (zmeneno["kdo"], zmeneno["jmeno"], zmeneno["duvod"]) == (
        "vybor@example.test",
        "Výbor",
        "Překlep v sazbě",
    )
    assert (zmeneno["druh"], zmeneno["klic"]) == ("verze_predpisu", "2027-01-01")

    polozka = next(
        p
        for p in klient.get("/api/rozhodnuti").json()["polozky"]
        if p["klic"] == "predpis:2027-01-01"
    )
    assert polozka["rozhodnuti_id"] == r.id
    assert polozka["zmeneno_po_schvaleni"]["duvod"] == "Překlep v sazbě"

    smazat = klient.delete("/api/verze-predpisu/2027-01-01")
    assert smazat.status_code == 422

    h = klient.get("/api/historie?druh=verze_predpisu&klic=2027-01-01").json()
    [zmena_h, pridani] = h["zaznamy"]
    assert (zmena_h["akce_nazev"], zmena_h["kdo"], zmena_h["duvod"]) == (
        "Změněno",
        "vybor@example.test",
        "Překlep v sazbě",
    )
    assert zmena_h["zmeny"] == [
        {"pole": "Složka Fond oprav", "pred": "60,00 Kč za m²", "po": "65,00 Kč za m²"}
    ]
    assert pridani["akce"] == "pridani" and not h["dalsi"]
    assert {"kod": "verze_predpisu", "nazev": "Předpis záloh"} in h["druhy"]
    assert session.scalar(select(AuditniZaznam.transakce).limit(1)) > 0


def test_starsi_schvaleni_bez_otisku(klient, session):
    """Schválení zapsané před otisky platí, dokud se předpis v aplikaci nezmění."""
    session.add(Obdobi(rok=2026, stav="otevrene"))
    predpisy.uloz_verzi(session, PROFIL, _nova(date(2027, 1, 1), 6_000), KDO, None)
    r = _zalohy(session)
    session.commit()
    session.execute(
        text(
            "INSERT INTO rozhodnuti_pro (klic, rozhodnuti_id, upravil)"
            " VALUES ('predpis:2027-01-01', :r, 'x')"
        ),
        {"r": r.id},
    )
    session.commit()
    pol = rozhodnuti.polozky(PROFIL, _nast(session))
    assert rozhodnuti.dolozeni(session, pol)["predpis:2027-01-01"].platne

    verze = next(
        v
        for v in klient.get("/api/verze-predpisu").json()["verze"]
        if v["plati_od"] == "2027-01-01"
    )
    zmena = {k: verze[k] for k in ("plati_od", "zdroj", "slozky", "pevne", "osoby")}
    zmena["zdroj"] = "Opravený podklad"  # podklad otisk nemění
    ok = klient.put(
        "/api/verze-predpisu", json={"puvodni": "2027-01-01", "verze": zmena, "duvod": "Podklad"}
    )
    assert ok.status_code == 200, ok.text
    verze = next(v for v in ok.json()["verze"] if v["plati_od"] == "2027-01-01")
    assert verze["schvaleni"]["zmeneno_po_schvaleni"] is None

    zmena["slozky"] = [
        s | {"sazba": 6_500} if s["kod"] == "FOND_OPRAV" else s for s in zmena["slozky"]
    ]
    ok = klient.put(
        "/api/verze-predpisu", json={"puvodni": "2027-01-01", "verze": zmena, "duvod": "Sazba"}
    )
    verze = next(v for v in ok.json()["verze"] if v["plati_od"] == "2027-01-01")
    assert verze["schvaleni"]["zmeneno_po_schvaleni"]["duvod"] == "Sazba"
    assert not [z for z in _zaznamy(session, "prirazeni_rozhodnuti")]
