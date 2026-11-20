"""API pro přehled dlužníků, podklad pro upomínku a potvrzení o dluzích při prodeji."""

from datetime import date

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import exists, func, select

from . import banka, dluznici, predpisy
from .api_lide import Adresat, adresati
from .db import BankovniPohyb, BankovniUcet, sezeni
from .domena import profil
from .domena import urok as urok_z_prodleni
from .nastaveni import nastaveni
from .prihlaseni import Prihlaseny

router = APIRouter(prefix="/api/dluznici")


class Polozka(BaseModel):
    popis: str
    splatnost: date | None  # None = z minulých let
    castka: int
    zbyva: int
    po_splatnosti: bool
    urok: int | None  # úrok z prodlení ze zbývající částky k dnešku; None = neumíme
    sazba: int | None  # roční sazba úroku v setinách procenta


class Jednotka(BaseModel):
    jednotka: str
    po_splatnosti: int
    nesplatne: int
    preplatek: int
    od: date | None
    z_minulych_let: bool
    urok: int
    urok_neuplny: bool
    polozky: list[Polozka]
    vlastnici: list[Adresat]  # k dnešku; prázdné, když je aplikace nezná


class Dluznici(BaseModel):
    rok: int
    dnes: date
    svj: str
    ico: str | None
    sidlo: str | None
    ucet: str | None  # provozní účet pro platby, když ho aplikace zná z výpisu
    posledni_vypis: date | None  # datum posledního pohybu na účtech
    nezauctovane_pohyby: int
    sazby_overeny_k: date
    zdroj_sazeb: str
    celkem_po_splatnosti: int
    jednotky: list[Jednotka]


@router.get("/{rok}")
def prehled(rok: int, _: Prihlaseny) -> Dluznici:
    prof = profil.nacti(nastaveni().profil)
    nast = predpisy.nacti(prof)
    dnes = date.today()
    with sezeni()() as s:
        vse = dluznici.prehled(s, prof, nast, rok, dnes)
        ucet = s.scalar(select(BankovniUcet.cislo).where(BankovniUcet.ucel == "provozni"))
        posledni = s.scalar(select(func.max(BankovniPohyb.datum)))
        kdo = adresati(s, dnes)
        nezauctovane = s.scalar(
            select(func.count())
            .select_from(BankovniPohyb)
            .where(~exists().where(banka.zauctovano(BankovniPohyb.id)))
        )
    jednotky = [
        Jednotka(
            jednotka=d.jednotka,
            po_splatnosti=d.po_splatnosti,
            nesplatne=d.nesplatne,
            preplatek=d.preplatek,
            od=d.od,
            z_minulych_let=d.z_minulych_let,
            urok=d.urok,
            urok_neuplny=d.urok_neuplny,
            polozky=[
                Polozka(
                    popis=p.popis,
                    splatnost=p.splatnost,
                    castka=p.castka,
                    zbyva=p.zbyva,
                    po_splatnosti=p.po_splatnosti(dnes),
                    urok=p.urok(dnes),
                    sazba=p.sazba(),
                )
                for p in d.polozky
            ],
            vlastnici=kdo.get(d.jednotka, []),
        )
        for d in vse
    ]
    return Dluznici(
        rok=rok,
        dnes=dnes,
        svj=prof.nazev,
        ico=prof.ico,
        sidlo=prof.sidlo,
        ucet=ucet,
        posledni_vypis=posledni,
        nezauctovane_pohyby=nezauctovane or 0,
        sazby_overeny_k=urok_z_prodleni.OVERENO_K,
        zdroj_sazeb=urok_z_prodleni.ZDROJ,
        celkem_po_splatnosti=sum(j.po_splatnosti for j in jednotky),
        jednotky=jednotky,
    )
