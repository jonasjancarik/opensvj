"""API pro počáteční stavy roku převzaté z dřívějšího účetnictví."""

from datetime import date

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from . import pocatecni, ulozene
from .db import sezeni
from .domena import profil
from .nastaveni import nastaveni
from .prihlaseni import Prihlaseny

router = APIRouter(prefix="/api/pocatecni")


def _profil() -> profil.Profil:
    return profil.nacti(nastaveni().profil)


class Ucet(BaseModel):
    ucet: str
    nazev: str
    vlastnici: bool  # zůstatek se rozepisuje po jednotkách


class Zustatek(BaseModel):
    ucet: str
    castka: int = Field(description="haléře, kladné = aktiva, záporné = pasiva")


class Polozka(BaseModel):
    ucet: str
    castka: int
    jednotka: str | None = None
    popis: str = Field(default="", max_length=200)
    drivejsi_vlastnik: str | None = Field(default=None, max_length=128)


class Zauctovano(BaseModel):
    zapis: str
    datum: date
    zauctoval: str


class Banka(BaseModel):
    ucet: str
    nazev: str
    zacatek_vypisu: int | None
    vypis: str | None


class PocatecniStavy(BaseModel):
    rok: int
    ucty: list[Ucet]
    jednotky: list[str]
    zauctovano: Zauctovano | None
    zustatky: list[Zustatek]
    polozky: list[Polozka]
    banka: list[Banka]


class Pozadavek(BaseModel):
    zustatky: list[Zustatek]
    polozky: list[Polozka] = Field(default_factory=list)


def _prehled(rok: int) -> PocatecniStavy:
    prof = _profil()
    vlastnici = pocatecni.ucty_vlastniku(prof)
    with sezeni()() as s:
        z = pocatecni.zauctovany(s, rok)
        stav = pocatecni.nacti(s, prof, rok)
        banka = pocatecni.kontrola_banky(s, prof, rok)
    return PocatecniStavy(
        rok=rok,
        ucty=[
            Ucet(ucet=u, nazev=prof.nazev_uctu(u), vlastnici=u in vlastnici)
            for u in pocatecni.rozvahove_ucty(prof)
        ],
        jednotky=prof.jednotky,
        zauctovano=Zauctovano(
            zapis=f"{z.poradove_cislo}/{z.rok}", datum=z.datum, zauctoval=z.zauctoval
        )
        if z
        else None,
        zustatky=[Zustatek(ucet=u, castka=c) for u, c in stav.zustatky.items() if c]
        if stav
        else [],
        polozky=[
            Polozka(
                ucet=p.ucet,
                castka=p.castka,
                jednotka=p.jednotka,
                popis=p.popis,
                drivejsi_vlastnik=p.drivejsi_vlastnik,
            )
            for p in stav.polozky
        ]
        if stav
        else [],
        banka=[
            Banka(
                ucet=b.ucet,
                nazev=prof.nazev_uctu(b.ucet),
                zacatek_vypisu=b.zacatek_vypisu,
                vypis=b.vypis,
            )
            for b in banka
        ],
    )


@router.get("/{rok}")
def prehled(rok: int, _: Prihlaseny) -> PocatecniStavy:
    return _prehled(rok)


@router.post("/{rok}")
def zauctuj(rok: int, pozadavek: Pozadavek, uzivatel: Prihlaseny) -> PocatecniStavy:
    zustatky: dict[str, int] = {}
    for z in pozadavek.zustatky:
        zustatky[z.ucet] = zustatky.get(z.ucet, 0) + z.castka
    stav = pocatecni.PocatecniStav(
        rok=rok,
        zustatky=zustatky,
        polozky=[
            pocatecni.Polozka(
                ucet=p.ucet,
                castka=p.castka,
                jednotka=p.jednotka or None,
                popis=p.popis.strip(),
                drivejsi_vlastnik=(p.drivejsi_vlastnik or "").strip() or None,
            )
            for p in pozadavek.polozky
        ],
    )
    with sezeni()() as s:
        try:
            pocatecni.zauctuj(s, _profil(), stav, zauctoval=uzivatel.email)
        except pocatecni.ChybaPocatku as e:
            s.rollback()
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e
        # Rozepsaný formulář už není potřeba; smaže se ve stejné transakci jako zaúčtování.
        ulozene.smaz_formular(s, "pocatecni-stavy", str(rok))
        s.commit()
    return _prehled(rok)
