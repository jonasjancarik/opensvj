"""API pro roční vyúčtování záloh na správu domu."""

from datetime import date

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from . import predpisy, vyuctovani_spravy
from .api_lide import Adresat, adresati
from .db import BankovniUcet, sezeni
from .domena import profil
from .nastaveni import nastaveni
from .prihlaseni import Prihlaseny, Zapisujici

router = APIRouter(prefix="/api/vyuctovani-spravy")


class Polozka(BaseModel):
    kod: str
    nazev: str
    klic: str
    jak_se_deli: str
    naklady: int  # co ponesou vlastníci (náklady snížené o související výnosy)
    vynosy: int  # výnosy, o které se náklady snížily
    zalohy: int


class PolozkaJednotky(BaseModel):
    kod: str
    naklady: int
    zalohy: int


class Jednotka(BaseModel):
    jednotka: str
    podil: str  # "543/8600"
    zalohy: int
    naklady: int
    rozdil: int  # kladný = nedoplatek
    polozky: list[PolozkaJednotky]
    vlastnici: list[Adresat]  # k dnešku


class Nezahrnuto(BaseModel):
    popis: str
    castka: int


class Vyuctovani(BaseModel):
    rok: int
    dnes: date
    svj: str
    ucet: str | None
    splatnost: date
    polozky: list[Polozka]
    jednotky: list[Jednotka]
    nezahrnuto: list[Nezahrnuto]
    zapis: str | None  # "n/rok", když je zaúčtované
    proc_nejde: str | None


def _prehled(rok: int) -> Vyuctovani:
    prof = profil.nacti(nastaveni().profil)
    nast = predpisy.nacti_s(prof, sezeni)
    dnes = date.today()
    with sezeni()() as s:
        v = vyuctovani_spravy.spocitej(s, prof, rok)
        duvod = vyuctovani_spravy.proc_nejde(s, nast, v, dnes)
        ucet = s.scalar(select(BankovniUcet.cislo).where(BankovniUcet.ucel == "provozni"))
        zapis = f"{v.zapis.poradove_cislo}/{v.zapis.rok}" if v.zapis else None
        kdo = adresati(s, dnes)
    return Vyuctovani(
        rok=rok,
        dnes=dnes,
        svj=prof.nazev,
        ucet=ucet,
        splatnost=v.splatnost,
        polozky=[
            Polozka(
                kod=p.kod,
                nazev=p.nazev,
                klic=p.klic,
                jak_se_deli=vyuctovani_spravy.KLICE.get(p.klic, p.klic),
                naklady=p.k_rozdeleni,
                vynosy=p.vynosy,
                zalohy=p.zalohy,
            )
            for p in v.polozky
        ],
        jednotky=[
            Jednotka(
                jednotka=j.jednotka,
                podil=f"{j.podil.numerator}/{j.podil.denominator}",
                zalohy=sum(j.zalohy.values()),
                naklady=sum(j.naklady.values()),
                rozdil=j.rozdil,
                polozky=[
                    PolozkaJednotky(
                        kod=p.kod, naklady=j.naklady.get(p.kod, 0), zalohy=j.zalohy.get(p.kod, 0)
                    )
                    for p in v.polozky
                ],
                vlastnici=kdo.get(j.jednotka, []),
            )
            for j in v.jednotky
        ],
        nezahrnuto=[Nezahrnuto(popis=n.popis, castka=n.castka) for n in v.nezahrnuto],
        zapis=zapis,
        proc_nejde=duvod,
    )


@router.get("/{rok}")
def prehled(rok: int, _: Prihlaseny) -> Vyuctovani:
    return _prehled(rok)


@router.post("/{rok}")
def zauctuj(rok: int, uzivatel: Zapisujici) -> Vyuctovani:
    prof = profil.nacti(nastaveni().profil)
    with sezeni()() as s:
        try:
            vyuctovani_spravy.zauctuj(
                s, prof, predpisy.nacti(prof, s), rok, zauctoval=uzivatel.email
            )
        except vyuctovani_spravy.ChybaVyuctovani as e:
            s.rollback()
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e
        s.commit()
    return _prehled(rok)
