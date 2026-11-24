"""API pro oznámení vlastníkům o nové výši záloh."""

from datetime import date

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from . import oznameni, predpisy, zasilky
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
    doruceno: date | None  # kdy vlastníkovi došlo oznámení
    # Od kdy jde novou zálohu na služby požadovat, když oznámení došlo pozdě
    # (první den měsíce po doručení, § 4 odst. 4 zákona 67/2013); jinak None.
    sluzby_od: date | None


class Oznameni(BaseModel):
    svj: str
    ico: str | None
    sidlo: str | None
    dnes: date
    splatnost_den: int
    verze: list[date]  # všechny změny předpisu (verze i změny podílů), od nejnovější
    plati_od: date
    predchozi_od: date | None
    dorucit_do: date
    zdroj: str
    # Od tohoto data se předpis počítá s novými podíly na společných částech.
    zmena_podilu: date | None
    jednotky: list[Jednotka]
    rozeslani: str  # klíč zásilek s tímto oznámením


@router.get("")
def nejnovejsi(_: Prihlaseny) -> Oznameni:
    nast = predpisy.nacti_s(_profil(), sezeni)
    if not nast.verze:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "SVJ zatím nemá žádný předpis záloh.")
    return _oznameni(nast.zmeny_predpisu()[-1])


@router.get("/{plati_od}")
def pro_verzi(plati_od: date, _: Prihlaseny) -> Oznameni:
    return _oznameni(plati_od)


def _profil() -> profil.Profil:
    return profil.nacti(nastaveni().profil)


def _oznameni(plati_od: date) -> Oznameni:
    prof = _profil()
    nast = predpisy.nacti_s(prof, sezeni)
    try:
        o = oznameni.oznameni(prof, nast, plati_od)
    except oznameni.ChybaOznameni as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e
    with sezeni()() as s:
        kdo = adresati(s, date.today())
        klic = f"oznameni:{o.plati_od.isoformat()}"
        doruceno = zasilky.doruceni_jednotek(s, klic)
    return Oznameni(
        svj=prof.nazev,
        ico=prof.ico,
        sidlo=prof.sidlo,
        dnes=date.today(),
        splatnost_den=nast.splatnost_den,
        verze=sorted(nast.zmeny_predpisu(), reverse=True),
        plati_od=o.plati_od,
        predchozi_od=o.predchozi_od,
        dorucit_do=o.dorucit_do,
        zdroj=o.zdroj,
        zmena_podilu=o.zmena_podilu.plati_od if o.zmena_podilu else None,
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
                doruceno=doruceno.get(j.jednotka),
                sluzby_od=_sluzby_od(o.plati_od, doruceno.get(j.jednotka)),
            )
            for j in o.jednotky
        ],
        rozeslani=klic,
    )


def _sluzby_od(plati_od: date, doruceno: date | None) -> date | None:
    if doruceno is None:
        return None
    od = zasilky.plus_mesice(doruceno.replace(day=1), 1)
    return od if od > plati_od else None
