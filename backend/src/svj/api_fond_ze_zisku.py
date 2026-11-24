"""API pro výsledek hospodaření minulého roku a fond ze zisku."""

from datetime import date

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from . import fond_ze_zisku
from .db import sezeni
from .domena import profil
from .nastaveni import nastaveni
from .prihlaseni import Prihlaseny, Zapisujici

router = APIRouter(prefix="/api/fond-ze-zisku")


class Pohyb(BaseModel):
    datum: date
    doklad: str
    popis: str
    castka: int
    zapis: str


class Navrh(BaseModel):
    zisk_do_fondu: int
    zisk_na_ztraty: int
    ztrata: int


class Rozdeleni(BaseModel):
    datum: date
    popis: str
    zapis: str


class Prehled(BaseModel):
    rok: int
    nastaveno: bool
    nezalohove: bool
    otevreno: bool
    vysledek: int
    navrh: Navrh | None
    rozdeleni: Rozdeleni | None
    pocatek: int
    pohyby: list[Pohyb]
    konec: int
    neuhrazena_ztrata: int


class NoveRozdeleni(BaseModel):
    datum: date
    rozhodnuti: str = Field(max_length=300)


def _profil() -> profil.Profil:
    return profil.nacti(nastaveni().profil)


def _prehled(rok: int) -> Prehled:
    prof = _profil()
    with sezeni()() as s:
        st = fond_ze_zisku.stav(s, prof, rok)
        r = st.rozdeleni
        return Prehled(
            rok=rok,
            nastaveno=st.nastaveno,
            nezalohove=prof.nezalohove,
            otevreno=st.otevreno,
            vysledek=st.vysledek,
            navrh=Navrh(**st.navrh.__dict__) if st.navrh else None,
            rozdeleni=Rozdeleni(datum=r.datum, popis=r.popis, zapis=f"{r.poradove_cislo}/{r.rok}")
            if r
            else None,
            pocatek=st.pocatek,
            pohyby=[Pohyb(**p.__dict__) for p in st.pohyby],
            konec=st.konec,
            neuhrazena_ztrata=st.neuhrazena_ztrata,
        )


@router.get("/{rok}")
def prehled(rok: int, _: Prihlaseny) -> Prehled:
    return _prehled(rok)


@router.post("/{rok}/rozdeleni")
def rozdel(rok: int, r: NoveRozdeleni, uzivatel: Zapisujici) -> Prehled:
    with sezeni()() as s:
        try:
            fond_ze_zisku.rozdel(
                s, _profil(), rok, datum=r.datum, rozhodnuti=r.rozhodnuti, zauctoval=uzivatel.email
            )
        except fond_ze_zisku.ChybaFondu as e:
            s.rollback()
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from e
        s.commit()
    return _prehled(rok)
