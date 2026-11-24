"""Vyúčtování jednotky, která během roku změnila vlastníka, po vlastnických obdobích.

Při převodu se zálohy nevypořádávají (§ 1186 odst. 1 OZ) a literatura dovozuje, že stačí
jedno vyúčtování současnému vlastníkovi (Durec s. 29). SVJ si ale může zvolit rozdělení
(profil `vyuctovani_pri_prevodu: po_obdobich`, výchozí je `soucasnemu`).

Při rozdělení patří každý měsíc roku tomu, kdo za něj platil předpis (volba
`predpis_mesice_prevodu`): dosavadnímu vlastníkovi k prvnímu dni měsíce, nebo novému
vlastníkovi. Zálohy vlastnického období jsou předepsané zálohy jeho měsíců. Náklad jednotky
na položku se rozdělí mezi období podle vah měsíců: osobo-měsíce u klíče podle osob, podíl
měsíce u klíče podle podílů, jinak počet měsíců. Spotřeba z měřidel a výsledky zúčtovatele
se tedy také dělí podle měsíců. Součet období dá přesně výsledek celé jednotky.
"""

import calendar
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from fractions import Fraction

from sqlalchemy.orm import Session

from . import lide
from .db import Vlastnictvi
from .domena.penize import na_text
from .domena.profil import Profil
from .domena.rozdeleni import rozdel

PO_OBDOBICH = "po_obdobich"


@dataclass
class Obdobi:
    vlastnictvi_id: int
    osoby: list[int]
    jmena: str
    od: date  # první den vlastnictví v roce
    do: date  # poslední den vlastnictví v roce
    mesice: list[int]  # měsíce, za které tento vlastník platil předpis
    soucasny: bool  # vlastník na konci roku; vyúčtování dostává bez jména v deníku
    zalohy: dict[str, int] = field(default_factory=dict)
    naklady: dict[str, int] = field(default_factory=dict)

    @property
    def rozdil(self) -> int:
        """Kladný = nedoplatek, záporný = přeplatek."""
        return sum(self.naklady.values()) - sum(self.zalohy.values())


def _konec_mesice(rok: int, mesic: int) -> date:
    return date(rok, mesic, calendar.monthrange(rok, mesic)[1])


def _vlastnik_k(historie: list[Vlastnictvi], den: date) -> Vlastnictvi | None:
    return next(
        (v for v in historie if v.plati_od <= den and (v.plati_do is None or den <= v.plati_do)),
        None,
    )


def platici_mesicu(profil: Profil, historie: list[Vlastnictvi], rok: int) -> list[Vlastnictvi]:
    """Pro každý měsíc roku vlastnictví, které za něj platilo předpis.

    Měsíce, pro které aplikace vlastníka nezná, se přidají k nejbližšímu známému
    (nejdřív k předchozímu). Prázdný seznam, když jednotka nemá v roce žádného vlastníka.
    """
    novy = profil.predpis_mesice_prevodu == "novy"
    platici: list[Vlastnictvi | None] = [
        _vlastnik_k(historie, _konec_mesice(rok, m) if novy else date(rok, m, 1))
        for m in range(1, 13)
    ]
    znami = [v for v in platici if v is not None]
    if not znami:
        return []
    vysledek: list[Vlastnictvi] = []
    for v in platici:
        vysledek.append(v if v is not None else (vysledek[-1] if vysledek else znami[0]))
    return vysledek


def obdobi(s: Session, profil: Profil, rok: int) -> dict[str, list[Obdobi]]:
    """Vlastnická období jednotek, které v roce měly víc než jednoho vlastníka."""
    vysledek: dict[str, list[Obdobi]] = {}
    podle_jednotky: dict[str, list[Vlastnictvi]] = {}
    for v in lide.vlastnictvi(s):
        podle_jednotky.setdefault(v.jednotka, []).append(v)
    for jednotka in profil.jednotky:
        platici = platici_mesicu(profil, podle_jednotky.get(jednotka, []), rok)
        if len({v.id for v in platici}) < 2:
            continue
        podle: dict[int, Obdobi] = {}
        for m, v in enumerate(platici, start=1):
            if v.id not in podle:
                podle[v.id] = Obdobi(
                    vlastnictvi_id=v.id,
                    osoby=[c.osoba_id for c in v.vlastnici],
                    jmena=", ".join(c.osoba.jmeno for c in v.vlastnici),
                    od=max(date(rok, 1, 1), v.plati_od),
                    do=min(date(rok, 12, 31), v.plati_do or date(rok, 12, 31)),
                    mesice=[],
                    soucasny=False,
                )
            podle[v.id].mesice.append(m)
        seznam = sorted(podle.values(), key=lambda o: o.mesice[0])
        seznam[-1].soucasny = True
        vysledek[jednotka] = seznam
    return vysledek


def rozdel_jednotku(
    seznam: list[Obdobi],
    naklady: dict[str, int],
    zalohy_mesicu: dict[tuple[str, int], int],
    vahy_mesicu: Callable[[str], list[Fraction | int]],
) -> None:
    """Rozdělí náklady a zálohy jednotky na vlastnická období.

    `zalohy_mesicu` je (položka, měsíc) → zálohy, `vahy_mesicu(položka)` dvanáct vah měsíců.
    """
    for o in seznam:
        o.zalohy, o.naklady = {}, {}
        for (kod, mesic), castka in zalohy_mesicu.items():
            if mesic in o.mesice and castka:
                o.zalohy[kod] = o.zalohy.get(kod, 0) + castka
    for kod, castka in naklady.items():
        if not castka:
            continue
        vahy_m = vahy_mesicu(kod)
        vahy = {i: sum(vahy_m[m - 1] for m in o.mesice) for i, o in enumerate(seznam)}
        if not any(vahy.values()):
            vahy = {i: len(o.mesice) for i, o in enumerate(seznam)}
        for i, c in rozdel(castka, vahy).items():
            if c:
                seznam[i].naklady[kod] = c


def vysledky(jednotka: str, rozdil: int, seznam: list[Obdobi]) -> list[dict[str, str]]:
    """Vstup `vysledky` pro zápis vyúčtování. Výsledek dřívějšího vlastníka nese jeho jméno
    (dimenze `protistrana`), takže se vede a vymáhá nebo vrací zvlášť od jednotky."""
    if not seznam:
        return [{"jednotka": jednotka, "rozdil": na_text(rozdil), "protistrana": ""}]
    return [
        {
            "jednotka": jednotka,
            "rozdil": na_text(o.rozdil),
            "protistrana": "" if o.soucasny else o.jmena[:128],
        }
        for o in seznam
    ]
