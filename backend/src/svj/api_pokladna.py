"""API pro hotovostní pokladnu: pokladní kniha a pokladní doklady."""

from datetime import date

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from . import pokladna
from .db import sezeni
from .domena import profil
from .nastaveni import nastaveni
from .prihlaseni import Prihlaseny, Zapisujici

router = APIRouter(prefix="/api/pokladna")


class Polozka(BaseModel):
    datum: date
    cislo: str
    doklad: str
    popis: str
    prijem: int
    vydaj: int
    zustatek: int


class Prehled(BaseModel):
    rok: int
    dnes: date
    nastavena: bool
    zustatek: int
    na_ceste: int  # vybráno z účtu, ještě nepřijato do pokladny
    polozky: list[Polozka]
    jednotky: list[str]
    polozky_spravy: dict[str, str]  # kód → název


class Doklad(BaseModel):
    druh: str
    castka: int = Field(gt=0)  # haléře
    datum: date
    popis: str = Field(max_length=200)
    jednotka: str = ""
    sluzba: str = ""


def _profil() -> profil.Profil:
    return profil.nacti(nastaveni().profil)


def _prehled(rok: int) -> Prehled:
    prof = _profil()
    nastavena = pokladna.nastavena(prof)
    with sezeni()() as s:
        k = pokladna.kniha(s, prof, rok) if nastavena else None
    return Prehled(
        rok=rok,
        dnes=date.today(),
        nastavena=nastavena,
        zustatek=k.zustatek if k else 0,
        na_ceste=k.na_ceste if k else 0,
        polozky=[Polozka(**vars(p)) for p in k.polozky] if k else [],
        jednotky=prof.jednotky,
        polozky_spravy={kod: u.get("nazev", kod) for kod, u in prof.sprava.items()},
    )


@router.get("/{rok}")
def prehled(rok: int, _: Prihlaseny) -> Prehled:
    return _prehled(rok)


@router.post("/{rok}")
def zauctuj(rok: int, d: Doklad, uzivatel: Zapisujici) -> Prehled:
    if d.datum.year != rok:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"Datum dokladu musí být v roce {rok}."
        )
    with sezeni()() as s:
        try:
            pokladna.zauctuj(
                s,
                _profil(),
                d.druh,
                castka=d.castka,
                datum=d.datum,
                popis=d.popis,
                jednotka=d.jednotka,
                sluzba=d.sluzba,
                zauctoval=uzivatel.email,
            )
        except pokladna.ChybaPokladny as e:
            s.rollback()
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from e
        s.commit()
    return _prehled(rok)
