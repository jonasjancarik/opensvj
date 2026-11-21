"""API rozesílání dokumentů vlastníkům a veřejná stránka, na které vlastník potvrdí převzetí."""

from datetime import date, datetime
from html import escape

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import select

from . import posta, zasilky
from .db import Dokument, Zasilka, sezeni
from .domena import profil
from .nastaveni import nastaveni
from .prihlaseni import Prihlaseny, Zapisujici

router = APIRouter(prefix="/api/zasilky")
verejne = APIRouter(prefix="/api/verejne")


class ZasilkaVen(BaseModel):
    id: int
    davka: str
    druh: str
    klic: str
    nazev: str
    jednotka: str
    dokument_id: int
    sha256: str
    jmeno: str
    email: str | None
    adresa: str
    kanal: str
    stav: str
    pripraveno: datetime
    odeslano: datetime | None
    prijato_serverem: datetime | None
    otevreno: datetime | None
    potvrzeno: datetime | None
    doruceno: date | None
    doruceni_zdroj: str
    chyba: str


class Prehled(BaseModel):
    odesilani_nastaveno: bool
    zasilky: list[ZasilkaVen]


class DokumentDovnitr(BaseModel):
    jednotka: str = Field(min_length=1, max_length=32)
    html: str = Field(min_length=1, max_length=zasilky.MAX_HTML)


class Priprava(BaseModel):
    druh: str
    klic: str = Field(min_length=1, max_length=64)
    nazev: str = Field(min_length=1, max_length=200)
    dokumenty: list[DokumentDovnitr] = Field(min_length=1, max_length=500)


class Davka(BaseModel):
    davka: str
    zasilky: list[ZasilkaVen]


class Odeslani(BaseModel):
    ids: list[int] = Field(min_length=1)
    datum: date


class Doruceni(BaseModel):
    datum: date
    zdroj: str = Field(max_length=150)


class Nedoruceni(BaseModel):
    duvod: str = Field(max_length=500)


def _ven(z: Zasilka) -> ZasilkaVen:
    d = z.dokument
    return ZasilkaVen(
        id=z.id,
        davka=z.davka,
        druh=d.druh,
        klic=d.klic,
        nazev=d.nazev,
        jednotka=d.jednotka,
        dokument_id=d.id,
        sha256=d.sha256,
        jmeno=z.jmeno,
        email=z.email,
        adresa=z.adresa,
        kanal=z.kanal,
        stav=z.stav,
        pripraveno=z.pripraveno,
        odeslano=z.odeslano,
        prijato_serverem=z.prijato_serverem,
        otevreno=z.otevreno,
        potvrzeno=z.potvrzeno,
        doruceno=z.doruceno,
        doruceni_zdroj=z.doruceni_zdroj,
        chyba=z.chyba,
    )


def _chyba(s, e: Exception) -> HTTPException:
    s.rollback()
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e))


def _davka(s, davka: str) -> Davka:
    return Davka(davka=davka, zasilky=[_ven(z) for z in zasilky.v_davce(s, davka)])


@router.get("")
def prehled(_: Prihlaseny, klic: str | None = None) -> Prehled:
    with sezeni()() as s:
        dotaz = select(Zasilka).join(Dokument).order_by(Zasilka.id.desc())
        if klic:
            dotaz = dotaz.where(Dokument.klic == klic)
        return Prehled(
            odesilani_nastaveno=posta.nastaveno(),
            zasilky=[_ven(z) for z in s.scalars(dotaz.limit(2000))],
        )


@router.post("/priprav")
def priprav(p: Priprava, uzivatel: Zapisujici) -> Davka:
    with sezeni()() as s:
        try:
            davka = zasilky.priprav(
                s,
                p.druh,
                p.klic,
                p.nazev.strip(),
                [zasilky.NovyDokument(d.jednotka, d.html) for d in p.dokumenty],
                uzivatel.email,
            )
        except zasilky.ChybaZasilky as e:
            raise _chyba(s, e) from e
        s.commit()
        return _davka(s, davka)


@router.post("/davka/{davka}/odeslat")
def odesli(davka: str, uzivatel: Zapisujici) -> Davka:
    prof = profil.nacti(nastaveni().profil)
    with sezeni()() as s:
        try:
            zasilky.odesli_davku(s, davka, prof.nazev, uzivatel.email)
        except (zasilky.ChybaZasilky, posta.ChybaPosty) as e:
            raise _chyba(s, e) from e
        return _davka(s, davka)


@router.delete("/davka/{davka}")
def zrus(davka: str, _: Zapisujici) -> None:
    with sezeni()() as s:
        try:
            zasilky.zrus_davku(s, davka)
        except zasilky.ChybaZasilky as e:
            raise _chyba(s, e) from e
        s.commit()


@router.post("/odeslano")
def odeslano(o: Odeslani, uzivatel: Zapisujici) -> None:
    with sezeni()() as s:
        try:
            zasilky.oznac_odeslane(s, o.ids, o.datum, uzivatel.email)
        except zasilky.ChybaZasilky as e:
            raise _chyba(s, e) from e
        s.commit()


@router.post("/{zasilka_id}/doruceni")
def doruceni(zasilka_id: int, d: Doruceni, uzivatel: Zapisujici) -> ZasilkaVen:
    with sezeni()() as s:
        try:
            zasilky.zapis_doruceni(s, zasilka_id, d.datum, d.zdroj, uzivatel.email)
        except zasilky.ChybaZasilky as e:
            raise _chyba(s, e) from e
        s.commit()
        return _ven(s.get(Zasilka, zasilka_id))


@router.post("/{zasilka_id}/nedoruceno")
def nedoruceno(zasilka_id: int, n: Nedoruceni, _: Zapisujici) -> ZasilkaVen:
    with sezeni()() as s:
        try:
            zasilky.zapis_nedoruceni(s, zasilka_id, n.duvod)
        except zasilky.ChybaZasilky as e:
            raise _chyba(s, e) from e
        s.commit()
        return _ven(s.get(Zasilka, zasilka_id))


# Uložený dokument je HTML, které poskládal prohlížeč člena výboru. Zobrazuje se bez skriptů
# a bez načítání čehokoli zvenku.
CSP_DOKUMENTU = "sandbox; default-src 'none'; style-src 'unsafe-inline'; img-src data:"


@router.get("/dokument/{dokument_id}")
def dokument(dokument_id: int, _: Prihlaseny) -> Response:
    with sezeni()() as s:
        d = s.get(Dokument, dokument_id)
        if d is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Dokument neexistuje.")
        return HTMLResponse(d.html, headers={"Content-Security-Policy": CSP_DOKUMENTU})


# ---------- Veřejná stránka pro vlastníka ----------

STRANKA = """<!doctype html>
<html lang="cs"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>{titulek}</title>
<style>
body {{ margin: 0; font: 16px/1.5 system-ui, sans-serif; background: #f4f1ea; color: #1f1d1a; }}
header {{ padding: 16px; background: #fff; border-bottom: 1px solid #ddd6c8; }}
header > div {{ max-width: 860px; margin: 0 auto; display: flex; flex-wrap: wrap; gap: 12px;
  align-items: center; justify-content: space-between; }}
h1 {{ font-size: 1.15rem; margin: 0; }}
p {{ margin: 4px 0 0; color: #5b554c; }}
button {{ font: inherit; padding: 10px 18px; border: 0; border-radius: 8px; background: #2f5d50;
  color: #fff; cursor: pointer; }}
.hotovo {{ color: #2f5d50; font-weight: 600; }}
iframe {{ display: block; width: 100%; max-width: 860px; height: calc(100vh - 120px);
  margin: 16px auto; border: 1px solid #ddd6c8; background: #fff; }}
</style></head>
<body>
<header><div>
<div><h1>{titulek}</h1><p>{svj}, jednotka {jednotka}</p></div>
{akce}
</div></header>
{obsah}
</body></html>"""


ZAKLAD = "/api/verejne/zasilka"


def _stranka(svj: str, z: Zasilka | None, token: str) -> HTMLResponse:
    if z is None:
        return HTMLResponse(
            STRANKA.format(
                titulek="Odkaz neplatí",
                svj=escape(svj),
                jednotka="–",
                akce="",
                obsah="<p style='max-width:860px;margin:16px auto'>Tento odkaz neexistuje nebo "
                "už neplatí. Ozvěte se prosím výboru SVJ.</p>",
            ),
            status_code=404,
        )
    if z.potvrzeno:
        kdy = f"{z.potvrzeno.day}. {z.potvrzeno.month}. {z.potvrzeno.year}"
        akce = f"<span class='hotovo'>Převzetí jste potvrdili {kdy}. Děkujeme.</span>"
    else:
        akce = (
            f"<form method='post' action='{ZAKLAD}/{token}/potvrdit'>"
            "<button type='submit'>Potvrzuji převzetí dokumentu</button></form>"
        )
    return HTMLResponse(
        STRANKA.format(
            titulek=escape(z.dokument.nazev),
            svj=escape(svj),
            jednotka=escape(z.dokument.jednotka),
            akce=akce,
            obsah=f"<iframe src='{ZAKLAD}/{token}/dokument' title='Dokument'></iframe>",
        ),
        headers={"Referrer-Policy": "no-referrer", "Cache-Control": "no-store"},
    )


@verejne.get("/zasilka/{token}", response_class=HTMLResponse)
def zobraz(token: str) -> HTMLResponse:
    svj = profil.nacti(nastaveni().profil).nazev
    with sezeni()() as s:
        z = zasilky.podle_tokenu(s, token)
        if z is not None:
            zasilky.otevreno(s, z)
            s.commit()
        return _stranka(svj, z, token)


@verejne.get("/zasilka/{token}/dokument")
def dokument_vlastnika(token: str) -> Response:
    with sezeni()() as s:
        z = zasilky.podle_tokenu(s, token)
        if z is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND)
        return HTMLResponse(
            z.dokument.html,
            headers={"Content-Security-Policy": CSP_DOKUMENTU, "Cache-Control": "no-store"},
        )


@verejne.post("/zasilka/{token}/potvrdit", response_class=HTMLResponse)
def potvrd(token: str) -> HTMLResponse:
    svj = profil.nacti(nastaveni().profil).nazev
    with sezeni()() as s:
        z = zasilky.podle_tokenu(s, token)
        if z is not None:
            zasilky.otevreno(s, z)
            zasilky.potvrzeno(s, z)
            s.commit()
        return _stranka(svj, z, token)
