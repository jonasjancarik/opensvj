"""API pro oznámení vlastníkům o nové výši záloh."""

from datetime import date

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from . import oznameni, predpisy
from .api_lide import Adresat, adresati
from .api_predpisy import _skupina
from .db import sezeni
from .domena import profil
from .nastaveni import nastaveni
from .prihlaseni import Prihlaseny

router = APIRouter(prefix="/api/oznameni-zaloh")


class Slozka(BaseModel):
    kod: str
    nazev: str
    skupina: str  # fond_oprav | sprava | sluzby
    puvodne: int | None
    nove: int | None


class Jednotka(BaseModel):
    jednotka: str
    puvodne: int
    nove: int
    zmenena: bool
    slozky: list[Slozka]
    vlastnici: list[Adresat]  # k dnešku


class Oznameni(BaseModel):
    svj: str
    ico: str | None
    sidlo: str | None
    dnes: date
    splatnost_den: int
    verze: list[date]  # všechny verze předpisu, od nejnovější
    plati_od: date
    predchozi_od: date | None
    dorucit_do: date
    zdroj: str
    jednotky: list[Jednotka]


@router.get("")
def nejnovejsi(_: Prihlaseny) -> Oznameni:
    nast = predpisy.nacti(_profil())
    if not nast.verze:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "SVJ zatím nemá žádný předpis záloh.")
    return _oznameni(max(v.plati_od for v in nast.verze))


@router.get("/{plati_od}")
def pro_verzi(plati_od: date, _: Prihlaseny) -> Oznameni:
    return _oznameni(plati_od)


def _profil() -> profil.Profil:
    return profil.nacti(nastaveni().profil)


def _oznameni(plati_od: date) -> Oznameni:
    prof = _profil()
    nast = predpisy.nacti(prof)
    try:
        o = oznameni.oznameni(prof, nast, plati_od)
    except oznameni.ChybaOznameni as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e
    with sezeni()() as s:
        kdo = adresati(s, date.today())
    return Oznameni(
        svj=prof.nazev,
        ico=prof.ico,
        sidlo=prof.sidlo,
        dnes=date.today(),
        splatnost_den=nast.splatnost_den,
        verze=sorted((v.plati_od for v in nast.verze), reverse=True),
        plati_od=o.plati_od,
        predchozi_od=o.predchozi_od,
        dorucit_do=o.dorucit_do,
        zdroj=o.zdroj,
        jednotky=[
            Jednotka(
                jednotka=j.jednotka,
                puvodne=j.puvodne,
                nove=j.nove,
                zmenena=j.zmenena,
                slozky=[
                    Slozka(
                        kod=s.kod,
                        nazev=s.nazev,
                        skupina=_skupina(prof, s.role),
                        puvodne=s.puvodne,
                        nove=s.nove,
                    )
                    for s in j.slozky
                ],
                vlastnici=kdo.get(j.jednotka, []),
            )
            for j in o.jednotky
        ],
    )
