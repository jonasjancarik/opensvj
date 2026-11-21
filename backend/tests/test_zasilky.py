"""Rozesílání dokumentů: dávka, odeslání e-mailem, potvrzení vlastníkem, ruční doručení."""

import email
import email.policy
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from svj import api_zasilky, lide, posta, prihlaseni, zasilky
from svj.api import app
from svj.nastaveni import nastaveni
from tests.test_banka import PROFIL
from tests.test_prihlaseni import FalesneJwks, token

KDO = "vybor@example.test"
DNES = date(2026, 11, 20)


def _vlastnici(session):
    s_e = lide.pridej_osobu(
        session,
        lide.UdajeOsoby(
            jmeno="Jana Nováková",
            email="Jana@Example.test",
            adresa="Ukázková 12, Praha",
            souhlas_email=date(2025, 1, 1),
        ),
        KDO,
    )
    manzel = lide.pridej_osobu(
        session,
        lide.UdajeOsoby(
            jmeno="Petr Novák", email="jana@example.test", souhlas_email=date(2025, 1, 1)
        ),
        KDO,
    )
    bez = lide.pridej_osobu(
        session,
        lide.UdajeOsoby(jmeno="Karel Dvořák", email="karel@example.test", adresa="Jinde 1"),
        KDO,
    )
    clenove = [lide.ClenVlastnictvi(s_e.id, "1/2"), lide.ClenVlastnictvi(manzel.id, "1/2")]
    lide.zapis_vlastnictvi(session, PROFIL, "1001/1", date(2020, 1, 1), clenove, "", KDO)
    lide.zapis_vlastnictvi(
        session, PROFIL, "1001/2", date(2020, 1, 1), [lide.ClenVlastnictvi(bez.id, None)], "", KDO
    )
    session.commit()


class Schranka:
    def __init__(self):
        self.zpravy = []

    def __call__(self, jmeno, email, predmet, text, prilohy=()):
        if email.startswith("spatna"):
            raise posta.OdmitnutyPrijemce("Server adresu odmítl (550 no such user).")
        self.zpravy.append((jmeno, email, predmet, text, prilohy))
        return "<id@example.test>"


def _dokumenty():
    return [
        zasilky.NovyDokument("1001/1", "<article>Vyúčtování 1001/1</article>"),
        zasilky.NovyDokument("1001/2", "<article>Vyúčtování 1001/2</article>"),
    ]


def test_davka_e_mailem_jen_se_souhlasem(session):
    _vlastnici(session)
    davka = zasilky.priprav(
        session, "vyuctovani_sluzeb", "vyuctovani_sluzeb:2026", "Vyúčtování služeb 2026",
        _dokumenty(), KDO, DNES,
    )  # fmt: skip
    z = zasilky.v_davce(session, davka)
    # Manželé se společnou adresou dostanou jeden e-mail; bez souhlasu jde dopis.
    assert [(x.jmeno, x.kanal, x.email) for x in z] == [
        ("Jana Nováková", "email", "jana@example.test"),
        ("Karel Dvořák", "posta", None),
    ]
    assert len(z[0].dokument.sha256) == 64

    schranka = Schranka()
    zasilky.odesli_davku(session, davka, "SVJ Ukázková 12", KDO, schranka)
    [(jmeno, email, predmet, telo, [priloha])] = schranka.zpravy
    assert predmet == "Vyúčtování služeb 2026, jednotka 1001/1"
    assert "/api/verejne/zasilka/" in telo and priloha.obsah.startswith(b"<article>")
    z = zasilky.v_davce(session, davka)
    assert [x.stav for x in z] == ["odeslana", "pripravena"]
    assert z[0].prijato_serverem and z[0].doruceno is None

    # Dopis se vytiskne a odeslání i doručení zapíše výbor.
    zasilky.oznac_odeslane(session, [z[1].id], date(2026, 11, 20), KDO)
    with pytest.raises(zasilky.ChybaZasilky, match="dřív, než odešla"):
        zasilky.zapis_doruceni(session, z[1].id, date(2026, 11, 19), "Dodejka", KDO)
    zasilky.zapis_doruceni(session, z[1].id, date(2026, 11, 21), "Dodejka", KDO)
    assert zasilky.doruceni_jednotek(session, "vyuctovani_sluzeb:2026") == {
        "1001/2": date(2026, 11, 21)
    }

    # Upravený dokument je nový dokument; lhůty se počítají od jeho doručení.
    zasilky.priprav(
        session, "vyuctovani_sluzeb", "vyuctovani_sluzeb:2026", "Oprava",
        _dokumenty()[1:], KDO, DNES,
    )  # fmt: skip
    assert zasilky.doruceni_jednotek(session, "vyuctovani_sluzeb:2026") == {}


def test_dokument_nejde_zmenit(session):
    _vlastnici(session)
    davka = zasilky.priprav(session, "upominka", "upominka:1", "Upomínka", _dokumenty(), KDO, DNES)
    session.commit()
    dok_id = zasilky.v_davce(session, davka)[0].dokument_id
    with pytest.raises(Exception, match="nejde změnit"):
        session.execute(text("UPDATE dokument SET html = 'jinak' WHERE id = :i"), {"i": dok_id})
    session.rollback()


def test_zruseni_davky_a_odmitnuta_adresa(session):
    _vlastnici(session)
    davka = zasilky.priprav(session, "upominka", "upominka:1", "Upomínka", _dokumenty(), KDO, DNES)
    zasilky.zrus_davku(session, davka)
    assert zasilky.v_davce(session, davka) == []

    session.execute(text("UPDATE osoba SET email = 'spatna@example.test'"))
    session.expire_all()
    davka = zasilky.priprav(session, "upominka", "upominka:1", "Upomínka", _dokumenty(), KDO, DNES)
    zasilky.odesli_davku(session, davka, "SVJ", KDO, Schranka())
    z = zasilky.v_davce(session, davka)[0]
    assert z.stav == "nedorucena" and "550" in z.chyba


def test_jednotka_bez_vlastnika(session):
    with pytest.raises(zasilky.ChybaZasilky, match="nemají k dnešku zapsaného vlastníka"):
        zasilky.priprav(session, "upominka", "u", "Upomínka", _dokumenty(), KDO, DNES)


def test_plus_mesice():
    assert zasilky.plus_mesice(date(2026, 10, 31), 4) == date(2027, 2, 28)
    assert zasilky.plus_mesice(date(2026, 11, 21), 4) == date(2027, 3, 21)
    assert zasilky.plus_mesice(date(2026, 1, 15), 11) == date(2026, 12, 15)


@pytest.fixture
def klient(session, monkeypatch, tmp_path):
    monkeypatch.setattr(prihlaseni, "_jwks", lambda: FalesneJwks())
    monkeypatch.setattr(api_zasilky, "sezeni", lambda: sessionmaker(session.get_bind()))
    monkeypatch.setattr(nastaveni(), "smtp_host", "")
    monkeypatch.setattr(nastaveni(), "smtp_from", "SVJ <vybor@example.test>")
    monkeypatch.setattr(nastaveni(), "mail_dir", tmp_path)
    c = TestClient(app)
    c.headers["Authorization"] = f"Bearer {token()}"
    return c


def test_api_a_potvrzeni_vlastnikem(session, klient, tmp_path):
    _vlastnici(session)
    r = klient.post(
        "/api/zasilky/priprav",
        json={
            "druh": "oznameni",
            "klic": "oznameni:2027-01-01",
            "nazev": "Oznámení o nové výši záloh",
            "dokumenty": [{"jednotka": "1001/1", "html": "<article>Oznámení</article>"}],
        },
    )
    assert r.status_code == 200, r.text
    davka = r.json()["davka"]
    r = klient.post(f"/api/zasilky/davka/{davka}/odeslat")
    assert r.status_code == 200, r.text
    [eml] = tmp_path.glob("*.eml")
    zprava = email.message_from_bytes(eml.read_bytes(), policy=email.policy.default)
    assert zprava["To"] == "Jana Nováková <jana@example.test>"
    obsah = zprava.get_body(("plain",)).get_content()
    cesta = next(radek for radek in obsah.splitlines() if "/api/verejne/zasilka/" in radek)
    cesta = cesta[cesta.index("/api/verejne/") :].strip()

    verejny = TestClient(app)  # bez přihlášení
    stranka = verejny.get(cesta)
    assert stranka.status_code == 200 and "Potvrzuji převzetí" in stranka.text
    dok = verejny.get(f"{cesta}/dokument")
    assert "sandbox" in dok.headers["content-security-policy"] and "Oznámení" in dok.text

    [z] = klient.get("/api/zasilky?klic=oznameni:2027-01-01").json()["zasilky"]
    assert z["otevreno"] and z["doruceno"] is None  # otevření samo doručení nezakládá

    assert "Převzetí jste potvrdili" in verejny.post(f"{cesta}/potvrdit").text
    [z] = klient.get("/api/zasilky").json()["zasilky"]
    assert z["stav"] == "dorucena" and z["doruceno"] and z["potvrzeno"]

    assert verejny.get("/api/verejne/zasilka/neplatny").status_code == 404
    assert klient.get(f"/api/zasilky/dokument/{z['dokument_id']}").status_code == 200


def test_zaloha_na_sluzby_od_mesice_po_doruceni():
    from svj.api_oznameni import _sluzby_od

    assert _sluzby_od(date(2027, 1, 1), date(2026, 12, 20)) is None
    assert _sluzby_od(date(2027, 1, 1), date(2027, 1, 5)) == date(2027, 2, 1)
    assert _sluzby_od(date(2027, 1, 1), None) is None
