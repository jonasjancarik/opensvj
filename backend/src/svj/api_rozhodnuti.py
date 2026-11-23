"""API pro rozhodnutí orgánů a jejich přiřazení k nastavení SVJ."""

from datetime import date

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from . import predpisy, rozhodnuti
from .api_historie import ZmenaPoSchvaleni, zmena_po_schvaleni
from .db import Rozhodnuti as RozhodnutiDb
from .db import sezeni
from .domena import profil
from .nastaveni import nastaveni
from .prihlaseni import Prihlaseny, Zapisujici

router = APIRouter(prefix="/api/rozhodnuti")


class Organ(BaseModel):
    kod: str
    nazev: str


class Rozhodnuti(BaseModel):
    id: int
    organ: str
    datum: date
    bod: str
    nazev: str
    text: str
    hlasovani: str
    ulozeni: str
    popis: str
    upravil: str


class Polozka(BaseModel):
    klic: str
    skupina: str
    nazev: str
    popis: str
    rozhodnuti_id: int | None
    # Přiřazené rozhodnutí přestalo platit, protože se položka po schválení změnila.
    zmeneno_po_schvaleni: ZmenaPoSchvaleni | None


class Prehled(BaseModel):
    dnes: date
    organy: list[Organ]
    rozhodnuti: list[Rozhodnuti]
    polozky: list[Polozka]


class UdajeRozhodnuti(BaseModel):
    organ: str
    datum: date
    nazev: str = Field(max_length=200)
    bod: str = Field(default="", max_length=32)
    text: str = Field(default="", max_length=20000)
    hlasovani: str = Field(default="", max_length=200)
    ulozeni: str = Field(default="", max_length=500)


class Prirazeni(BaseModel):
    klic: str = Field(max_length=128)
    rozhodnuti_id: int | None


def _rozhodnuti(r: RozhodnutiDb) -> Rozhodnuti:
    return Rozhodnuti(
        id=r.id,
        organ=r.organ,
        datum=r.datum,
        bod=r.bod,
        nazev=r.nazev,
        text=r.text,
        hlasovani=r.hlasovani,
        ulozeni=r.ulozeni,
        popis=rozhodnuti.popis(r),
        upravil=r.upravil,
    )


def _prehled(s) -> Prehled:
    prof = profil.nacti(nastaveni().profil)
    polozky = rozhodnuti.polozky(prof, predpisy.nacti(prof, s))
    dolozeni = rozhodnuti.dolozeni(s, polozky)
    return Prehled(
        dnes=date.today(),
        organy=[Organ(kod=k, nazev=n) for k, n in rozhodnuti.ORGANY.items()],
        rozhodnuti=[_rozhodnuti(r) for r in rozhodnuti.rozhodnuti(s)],
        polozky=[
            Polozka(
                klic=p.klic,
                skupina=p.skupina,
                nazev=p.nazev,
                popis=p.popis,
                rozhodnuti_id=d.rozhodnuti_id if (d := dolozeni.get(p.klic)) else None,
                zmeneno_po_schvaleni=zmena_po_schvaleni(d, p),
            )
            for p in polozky
        ],
    )


def _proved(akce) -> Prehled:
    with sezeni()() as s:
        try:
            akce(s)
            s.flush()
        except rozhodnuti.ChybaRozhodnuti as e:
            s.rollback()
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from e
        s.commit()
        return _prehled(s)


def _udaje(u: UdajeRozhodnuti) -> rozhodnuti.UdajeRozhodnuti:
    return rozhodnuti.UdajeRozhodnuti(**u.model_dump())


@router.get("")
def prehled(_: Prihlaseny) -> Prehled:
    with sezeni()() as s:
        return _prehled(s)


@router.post("")
def pridej(u: UdajeRozhodnuti, uzivatel: Zapisujici) -> Prehled:
    return _proved(lambda s: rozhodnuti.pridej(s, _udaje(u), uzivatel.email))


@router.put("/prirazeni")
def prirad(z: Prirazeni, uzivatel: Zapisujici) -> Prehled:
    prof = profil.nacti(nastaveni().profil)
    return _proved(
        lambda s: rozhodnuti.prirad(
            s, prof, predpisy.nacti(prof, s), z.klic, z.rozhodnuti_id, uzivatel.email
        )
    )


@router.put("/{rozhodnuti_id}")
def uprav(rozhodnuti_id: int, u: UdajeRozhodnuti, uzivatel: Zapisujici) -> Prehled:
    return _proved(lambda s: rozhodnuti.uprav(s, rozhodnuti_id, _udaje(u), uzivatel.email))


@router.delete("/{rozhodnuti_id}")
def smaz(rozhodnuti_id: int, _: Zapisujici) -> Prehled:
    return _proved(lambda s: rozhodnuti.smaz(s, rozhodnuti_id))
