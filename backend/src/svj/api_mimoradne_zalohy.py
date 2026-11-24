"""API pro mimořádnou zálohu pro všechny jednotky podle podílů."""

from datetime import date

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from . import mimoradne_zalohy, rozhodnuti
from .db import sezeni
from .domena import profil
from .nastaveni import nastaveni
from .prihlaseni import Prihlaseny, Zapisujici

router = APIRouter(prefix="/api/mimoradne-zalohy")


class RozhodnutiVen(BaseModel):
    id: int
    datum: date
    popis: str


class Predepsana(BaseModel):
    cislo: str  # číslo zápisu v deníku "n/rok"
    datum: date
    popis: str
    celkem: int
    splatnost: date | None


class Prehled(BaseModel):
    dnes: date
    nastavena: bool  # profil má účet mimořádných záloh
    rozhodnuti: list[RozhodnutiVen]  # rozhodnutí shromáždění, od nejnovějšího
    predepsane: list[Predepsana]


class Navrh(BaseModel):
    celkem: int = Field(gt=0)  # haléře
    datum: date


class Nahled(BaseModel):
    casti: dict[str, int]  # jednotka → haléře


class Predpis(Navrh):
    splatnost: date
    rozhodnuti_id: int
    ucel: str = Field(max_length=150)


def _profil() -> profil.Profil:
    return profil.nacti(nastaveni().profil)


def _prehled() -> Prehled:
    prof = _profil()
    with sezeni()() as s:
        return Prehled(
            dnes=date.today(),
            nastavena="zalohy_dlouhodobe_mimoradne" in prof.role,
            rozhodnuti=[
                RozhodnutiVen(id=r.id, datum=r.datum, popis=rozhodnuti.popis(r))
                for r in mimoradne_zalohy.rozhodnuti_shromazdeni(s)
            ],
            predepsane=[
                Predepsana(
                    cislo=f"{p.zapis.poradove_cislo}/{p.zapis.rok}",
                    datum=p.zapis.datum,
                    popis=p.zapis.popis,
                    celkem=p.celkem,
                    splatnost=p.splatnost,
                )
                for p in mimoradne_zalohy.predepsane(s)
            ],
        )


@router.get("")
def prehled(_: Prihlaseny) -> Prehled:
    return _prehled()


@router.post("/nahled")
def nahled(n: Navrh, _: Prihlaseny) -> Nahled:
    """Jak se celková částka rozdělí na jednotky podle podílů ke dni předpisu."""
    with sezeni()() as s:
        return Nahled(casti=mimoradne_zalohy.rozdel_podle_podilu(s, _profil(), n.celkem, n.datum))


@router.post("")
def predepis(p: Predpis, uzivatel: Zapisujici) -> Prehled:
    with sezeni()() as s:
        try:
            mimoradne_zalohy.zauctuj(
                s,
                _profil(),
                celkem=p.celkem,
                datum=p.datum,
                splatnost=p.splatnost,
                rozhodnuti_id=p.rozhodnuti_id,
                ucel=p.ucel,
                zauctoval=uzivatel.email,
            )
        except mimoradne_zalohy.ChybaZalohy as e:
            s.rollback()
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from e
        s.commit()
    return _prehled()
