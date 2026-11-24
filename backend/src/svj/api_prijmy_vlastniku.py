"""API pro příjmy vlastníků ze společných částí (nájemné) a potvrzení pro jejich daně."""

from datetime import date

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from . import prijmy_vlastniku
from .db import sezeni
from .domena import profil
from .nastaveni import nastaveni
from .prihlaseni import Prihlaseny, Zapisujici

router = APIRouter(prefix="/api/prijmy-vlastniku")


class Platba(BaseModel):
    datum: date
    najemce: str
    castka: int
    zapis: str
    popis: str


class Vlastnik(BaseModel):
    jmena: list[str]
    adresa: str
    od: date | None
    do: date | None
    prijato: int
    predepsano: int


class Jednotka(BaseModel):
    jednotka: str
    podil: str
    vlastnici: list[Vlastnik]
    prijato: int
    vyplaceno: int
    do_fondu: int
    zbyva: int


class Prehled(BaseModel):
    rok: int
    nastaveno: bool
    svj: str
    ico: str | None
    sidlo: str | None
    dnes: date
    platby: list[Platba]
    predepsano: int
    jednotky: list[Jednotka]
    jako_vynos: list[str]


class Prevod(BaseModel):
    jednotka: str = Field(max_length=32)
    castka: int
    datum: date
    zadost: str = Field(max_length=300)


def _profil() -> profil.Profil:
    return profil.nacti(nastaveni().profil)


def _prehled(rok: int) -> Prehled:
    prof = _profil()
    zaklad = {"rok": rok, "svj": prof.nazev, "ico": prof.ico, "sidlo": prof.sidlo}
    if not prijmy_vlastniku.nastaveno(prof):
        return Prehled(
            **zaklad,
            nastaveno=False,
            dnes=date.today(),
            platby=[],
            predepsano=0,
            jednotky=[],
            jako_vynos=[],
        )
    with sezeni()() as s:
        p = prijmy_vlastniku.prehled(s, prof, rok)
        return Prehled(
            **zaklad,
            nastaveno=True,
            dnes=date.today(),
            platby=[Platba(**x.__dict__) for x in p.platby],
            predepsano=p.predepsano,
            jednotky=[
                Jednotka(
                    jednotka=j.jednotka,
                    podil=j.podil,
                    vlastnici=[
                        Vlastnik(
                            jmena=v.jmena,
                            adresa=v.adresa,
                            od=v.od,
                            do=v.do,
                            prijato=v.prijato,
                            predepsano=v.predepsano,
                        )
                        for v in j.vlastnici
                    ],
                    prijato=j.prijato,
                    vyplaceno=j.vyplaceno,
                    do_fondu=j.do_fondu,
                    zbyva=j.zbyva,
                )
                for j in p.jednotky
            ],
            jako_vynos=p.jako_vynos,
        )


@router.get("/{rok}")
def prehled(rok: int, _: Prihlaseny) -> Prehled:
    return _prehled(rok)


@router.post("/{rok}/prevod")
def prevod(rok: int, p: Prevod, uzivatel: Zapisujici) -> Prehled:
    with sezeni()() as s:
        try:
            prijmy_vlastniku.prevod_do_fondu(
                s,
                _profil(),
                jednotka=p.jednotka,
                castka=p.castka,
                datum=p.datum,
                zadost=p.zadost,
                zauctoval=uzivatel.email,
            )
        except prijmy_vlastniku.ChybaPrijmu as e:
            s.rollback()
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from e
        s.commit()
    return _prehled(rok)
