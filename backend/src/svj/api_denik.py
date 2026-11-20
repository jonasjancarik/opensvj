"""API pro deník: zápisy roku a jejich storno."""

from datetime import date

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from . import denik
from .db import Zapis, sezeni
from .domena import katalog, profil
from .nastaveni import nastaveni
from .prihlaseni import Prihlaseny, Zapisujici

router = APIRouter(prefix="/api/denik")


class Radek(BaseModel):
    strana: str
    ucet: str
    nazev_uctu: str
    castka: int
    jednotka: str | None
    sluzba: str | None
    protistrana: str | None
    popis: str | None


class ZapisDeniku(BaseModel):
    id: int
    cislo: str
    datum: date
    doklad: str
    operace: str
    nazev_operace: str
    popis: str
    zauctoval: str
    castka: int  # součet strany MD
    radky: list[Radek]
    stornovan_zapisem: str | None
    stornuje_zapis: str | None


class Denik(BaseModel):
    rok: int
    zapisy: list[ZapisDeniku]


class Storno(BaseModel):
    duvod: str = Field(max_length=500)


def _denik(rok: int) -> Denik:
    prof = profil.nacti(nastaveni().profil)
    ops = katalog.nacti()
    with sezeni()() as s:
        zapisy = list(
            s.scalars(
                select(Zapis)
                .where(Zapis.rok == rok)
                .options(selectinload(Zapis.radky), selectinload(Zapis.opravy))
                .order_by(Zapis.poradove_cislo.desc())
            )
        )
    cisla = {z.id: f"{z.poradove_cislo}/{z.rok}" for z in zapisy}
    return Denik(
        rok=rok,
        zapisy=[
            ZapisDeniku(
                id=z.id,
                cislo=cisla[z.id],
                datum=z.datum,
                doklad=z.doklad,
                operace=z.operace,
                nazev_operace=ops[z.operace].nazev if z.operace in ops else z.operace,
                popis=z.popis,
                zauctoval=z.zauctoval,
                castka=sum(r.castka for r in z.radky if r.strana == "md"),
                radky=[
                    Radek(
                        strana=r.strana,
                        ucet=r.ucet,
                        nazev_uctu=prof.nazev_uctu(r.ucet),
                        castka=r.castka,
                        jednotka=r.jednotka,
                        sluzba=r.sluzba,
                        protistrana=r.protistrana,
                        popis=r.popis,
                    )
                    for r in z.radky
                ],
                stornovan_zapisem=next(
                    (cisla.get(o.id) for o in z.opravy if o.operace == denik.STORNO), None
                ),
                stornuje_zapis=cisla.get(z.opravuje_zapis) if z.opravuje_zapis else None,
            )
            for z in zapisy
        ],
    )


@router.get("/{rok}")
def zapisy_roku(rok: int, _: Prihlaseny) -> Denik:
    return _denik(rok)


@router.post("/zapisy/{zapis_id}/storno")
def stornuj(zapis_id: int, pozadavek: Storno, uzivatel: Zapisujici) -> Denik:
    with sezeni()() as s:
        try:
            z = denik.storno(s, zapis_id, duvod=pozadavek.duvod, zauctoval=uzivatel.email)
        except denik.ChybaUctovani as e:
            s.rollback()
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e
        rok = z.rok
        s.commit()
    return _denik(rok)
