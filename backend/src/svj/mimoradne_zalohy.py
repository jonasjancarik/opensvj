"""Mimořádná dlouhodobá záloha pro všechny jednotky podle podílů.

Shromáždění rozhodne o jednorázovém příspěvku na konkrétní opravu nebo investici
(§ 1180 odst. 1 OZ). Celková částka se rozdělí na jednotky podle podílů na společných
částech platných ke dni předpisu, přesně na haléře (metoda největších zbytků). Předpis je
jeden zápis `mimoradna-zaloha` s řádkem za každou jednotku a se splatností, kterou určilo
shromáždění; v dlužnících se objeví jako samostatný dluh jednotky.
"""

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import denik, podily, rozhodnuti
from .db import Rozhodnuti, Zapis
from .domena import katalog
from .domena.penize import na_text
from .domena.profil import NeznamaRole, Profil
from .domena.rozdeleni import rozdel

OPERACE = "mimoradna-zaloha"


class ChybaZalohy(ValueError):
    pass


def rozdel_podle_podilu(s: Session, profil: Profil, celkem: int, datum: date) -> dict[str, int]:
    """Jednotka → část celkové částky podle podílů platných v den `datum`."""
    if celkem <= 0:
        raise ChybaZalohy("Celková částka musí být kladná.")
    sada = podily.nacti(s, profil).k_datu(datum)
    return rozdel(celkem, {j: sada.podily[j] for j in profil.jednotky})


def rozhodnuti_shromazdeni(s: Session) -> list[Rozhodnuti]:
    return [r for r in rozhodnuti.rozhodnuti(s) if r.organ == "shromazdeni"]


@dataclass
class Predepsana:
    zapis: Zapis
    celkem: int
    splatnost: date | None


def predepsane(s: Session) -> list[Predepsana]:
    """Platné předpisy mimořádných záloh, od nejnovějšího."""
    vysledek = []
    for z in s.scalars(
        select(Zapis)
        .where(Zapis.operace == OPERACE, denik.nestornovany())
        .order_by(Zapis.datum.desc(), Zapis.id.desc())
    ):
        md = [r for r in z.radky if r.strana == "md"]
        vysledek.append(
            Predepsana(z, sum(r.castka for r in md), next((r.splatnost for r in md), None))
        )
    return vysledek


def zauctuj(
    s: Session,
    profil: Profil,
    *,
    celkem: int,
    datum: date,
    splatnost: date,
    rozhodnuti_id: int,
    ucel: str,
    zauctoval: str,
) -> Zapis:
    ucel = ucel.strip()
    if not ucel:
        raise ChybaZalohy("Napište, na co je záloha (třeba „výměna oken“).")
    if splatnost < datum:
        raise ChybaZalohy("Splatnost nemůže být dřív než den předpisu.")
    r = s.get(Rozhodnuti, rozhodnuti_id)
    if r is None or r.organ != "shromazdeni":
        raise ChybaZalohy(
            "Vyberte rozhodnutí shromáždění, které mimořádnou zálohu schválilo. "
            "Když v seznamu není, zapište ho na stránce Rozhodnutí."
        )
    if r.datum > datum:
        raise ChybaZalohy("Předepsat zálohu jde až po dni, kdy o ní shromáždění rozhodlo.")
    casti = rozdel_podle_podilu(s, profil, celkem, datum)
    vstupy = {
        "jednotky": [{"jednotka": j, "castka": na_text(c)} for j, c in casti.items() if c],
        "splatnost": splatnost.isoformat(),
        "rozhodnuti": rozhodnuti.popis(r),
    }
    try:
        return denik.zauctuj(
            s,
            profil,
            katalog.nacti()[OPERACE],
            vstupy,
            datum=datum,
            popis=f"Mimořádná záloha: {ucel} ({rozhodnuti.popis(r)})",
            doklad="PR",
            zauctoval=zauctoval,
        )
    except (denik.ChybaUctovani, NeznamaRole) as e:
        raise ChybaZalohy(str(e)) from e
