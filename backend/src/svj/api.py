"""HTTP API pro frontend. Částky jsou v celých haléřích."""

from datetime import date

from fastapi import FastAPI
from pydantic import BaseModel
from sqlalchemy import select

from . import denik, pocatecni, predpisy
from .api_banka import router as banka_router
from .api_denik import router as denik_router
from .api_dluznici import router as dluznici_router
from .api_faktury import router as faktury_router
from .api_formulare import router as formulare_router
from .api_oznameni import router as oznameni_router
from .api_pocatecni import router as pocatecni_router
from .api_predpisy import router as predpisy_router
from .api_uzaverka import router as uzaverka_router
from .api_vyuctovani import router as vyuctovani_router
from .db import Zapis, sezeni
from .domena import katalog, profil, vykazy
from .nastaveni import nastaveni
from .prihlaseni import Prihlaseny

app = FastAPI(title="SVJ hospodaření", docs_url="/api/docs", openapi_url="/api/openapi.json")
app.include_router(banka_router)
app.include_router(predpisy_router)
app.include_router(vyuctovani_router)
app.include_router(uzaverka_router)
app.include_router(pocatecni_router)
app.include_router(denik_router)
app.include_router(faktury_router)
app.include_router(dluznici_router)
app.include_router(oznameni_router)
app.include_router(formulare_router)


class Ja(BaseModel):
    id: str
    email: str
    jmeno: str


class OperaceVKatalogu(BaseModel):
    id: str
    nazev: str
    stav: str
    doklad: str
    oblast: str


class RadekVykazu(BaseModel):
    strana: str
    radek: str
    castka: int
    tisice: int


class Vykazy(BaseModel):
    rok: int
    rozvaha: list[RadekVykazu]
    vysledovka: list[RadekVykazu]
    pocet_zapisu: int
    pocatecni_stavy: bool


@app.get("/api/health")
def health() -> dict[str, bool]:
    return {"ok": True}


@app.get("/api/me")
def ja(uzivatel: Prihlaseny) -> Ja:
    return Ja(id=uzivatel.id, email=uzivatel.email, jmeno=uzivatel.jmeno)


@app.get("/api/katalog")
def seznam_operaci(_: Prihlaseny) -> list[OperaceVKatalogu]:
    return [
        OperaceVKatalogu(
            id=o.id,
            nazev=o.nazev,
            stav=o.stav,
            doklad=o.doklad,
            oblast=o.soubor.removesuffix(".yaml"),
        )
        for o in katalog.nacti().values()
    ]


def _radky(v: vykazy.Vykaz) -> list[RadekVykazu]:
    tisice = v.v_tisicich()
    return [
        RadekVykazu(strana=s, radek=r, castka=c, tisice=tisice[(s, r)])
        for (s, r), c in sorted(v.radky.items())
    ]


@app.get("/api/vykazy/{rok}")
def vykazy_roku(rok: int, _: Prihlaseny) -> Vykazy:
    profil.nacti(nastaveni().profil)  # ověří, že profil existuje
    with sezeni()() as s:
        z = denik.zustatky(s, rok, date(rok, 12, 31))
        vlastnici = predpisy.zustatky_vlastniku(s, rok, date(rok, 12, 31))
        pocet = len(s.scalars(select(Zapis.id).where(Zapis.rok == rok)).all())
        otevreno = pocatecni.zauctovany(s, rok) is not None
    return Vykazy(
        rok=rok,
        rozvaha=_radky(vykazy.rozvaha(z, vlastnici)),
        vysledovka=_radky(vykazy.vysledovka(z)),
        pocet_zapisu=pocet,
        pocatecni_stavy=otevreno,
    )
