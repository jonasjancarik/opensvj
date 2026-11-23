"""API pro interní doklady podle operací z katalogu."""

from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from . import interni_doklady
from .db import sezeni
from .domena import katalog, profil
from .nastaveni import nastaveni
from .prihlaseni import Prihlaseny, Zapisujici

router = APIRouter(prefix="/api/interni-doklady")


class Moznost(BaseModel):
    hodnota: str
    nazev: str


class Pole(BaseModel):
    klic: str
    popis: str
    typ: str  # castka, castka_nula, castka_se_znamenkem, text, nebo výběr z `moznosti`
    moznosti: list[Moznost] | None


class Krok(BaseModel):
    id: str
    nazev: str


class Operace(BaseModel):
    id: str
    nazev: str
    kdy: str
    stav: str
    napoveda: str
    kroky: list[Krok]
    pole: list[Pole]


class Nabidka(BaseModel):
    operace: list[Operace]
    nedostupne: list[str]  # názvy operací, pro které v nastavení SVJ chybí účty


class Doklad(BaseModel):
    operace: str
    krok: str | None = None
    vstupy: dict[str, Any]


class NovyDoklad(Doklad):
    datum: date
    popis: str = Field(max_length=500)


class Radek(BaseModel):
    strana: str
    ucet: str
    nazev_uctu: str
    castka: int
    dimenze: dict[str, str]


class Zauctovano(BaseModel):
    cislo: str
    rok: int


def _profil() -> profil.Profil:
    return profil.nacti(nastaveni().profil)


def _chyba(e: Exception) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e))


@router.get("")
def nabidka(_: Prihlaseny) -> Nabidka:
    prof = _profil()
    ops = katalog.nacti()
    dostupne = interni_doklady.dostupne(prof)
    vysledek = []
    for op_id, formular in interni_doklady.FORMULARE.items():
        if not dostupne[op_id]:
            continue
        op = ops[op_id]
        vysledek.append(
            Operace(
                id=op_id,
                nazev=op.nazev,
                kdy=op.data.get("kdy", ""),
                stav=op.stav,
                napoveda=formular.napoveda,
                kroky=[Krok(id=k, nazev=n) for k, n in formular.kroky.items()],
                pole=[
                    Pole(
                        klic=p.klic,
                        popis=p.popis,
                        typ=p.typ,
                        moznosti=None
                        if (m := interni_doklady.moznosti(prof, p.typ)) is None
                        else [Moznost(hodnota=h, nazev=n) for h, n in m.items()],
                    )
                    for p in formular.pole
                ],
            )
        )
    return Nabidka(
        operace=vysledek,
        nedostupne=sorted(ops[i].nazev for i, ok in dostupne.items() if not ok),
    )


@router.post("/nahled")
def nahled(d: Doklad, _: Prihlaseny) -> list[Radek]:
    try:
        radky = interni_doklady.nahled(_profil(), d.operace, d.krok, d.vstupy)
    except (interni_doklady.ChybaDokladu, katalog.ChybaKatalogu) as e:
        raise _chyba(e) from e
    return [
        Radek(
            strana=r.strana,
            ucet=r.ucet,
            nazev_uctu=r.nazev_uctu,
            castka=r.castka,
            dimenze=r.dimenze,
        )
        for r in radky
    ]


@router.post("")
def zauctuj(d: NovyDoklad, uzivatel: Zapisujici) -> Zauctovano:
    with sezeni()() as s:
        try:
            z = interni_doklady.zauctuj(
                s,
                _profil(),
                d.operace,
                d.krok,
                d.vstupy,
                datum=d.datum,
                popis=d.popis,
                zauctoval=uzivatel.email,
            )
        except (interni_doklady.ChybaDokladu, katalog.ChybaKatalogu) as e:
            s.rollback()
            raise _chyba(e) from e
        vysledek = Zauctovano(cislo=f"{z.poradove_cislo}/{z.rok}", rok=z.rok)
        s.commit()
    return vysledek
