"""Počáteční stavy roku převzaté z dřívějšího účetnictví.

Když SVJ začne účtovat v aplikaci, konečné zůstatky předchozího roku přicházejí ze sestav
dřívějšího správce (analytická rozvaha). Zaúčtují se jedním zápisem k 1. 1. proti
počátečnímu účtu rozvažnému. Pohledávky za vlastníky se rozepíšou po jednotkách, aby bylo
vidět, kdo kolik dluží; dluhy a přeplatky dřívějších vlastníků nesou jméno vlastníka.
"""

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import denik
from .db import BankovniUcet, BankovniVypis, RadekZapisu, Zapis
from .domena import katalog
from .domena.katalog import Radek
from .domena.penize import kc
from .domena.profil import NeznamaRole, Profil

OPERACE = "otevreni-pocatecnimi-stavy"
# Role, jejichž zůstatek je dluh nebo přeplatek konkrétního vlastníka.
ROLE_VLASTNIKU = ("pohledavky_vlastnici", "pohledavky_vyuctovani", "pohledavky_vyuctovani_minule")


class ChybaPocatku(ValueError):
    pass


@dataclass
class Polozka:
    """Část zůstatku účtu: dluh (kladně) nebo přeplatek (záporně) jednotky."""

    ucet: str
    castka: int  # haléře, kladné = na straně MD
    jednotka: str | None = None
    popis: str = ""
    drivejsi_vlastnik: str | None = None


@dataclass
class PocatecniStav:
    rok: int
    zustatky: dict[str, int]  # účet → haléře, kladné = MD (aktiva), záporné = D (pasiva)
    polozky: list[Polozka]


def klic(rok: int) -> str:
    return f"pocatecni-stavy:{rok}"


def ucty_vlastniku(profil: Profil) -> set[str]:
    return {profil.role[r] for r in ROLE_VLASTNIKU if r in profil.role}


def rozvahove_ucty(profil: Profil) -> dict[str, str]:
    """Účty, na kterých může být počáteční stav: číslo → role. Bez nákladů, výnosů a závěrky."""
    return {
        u: r
        for u, r in sorted(profil.role_uctu().items())
        if u[0] not in "56" and u[:2] not in ("39", "96", "93")
    }


def zkontroluj(profil: Profil, stav: PocatecniStav) -> None:
    ucty = rozvahove_ucty(profil)
    for u in stav.zustatky:
        if u not in ucty:
            raise ChybaPocatku(f"Účet {u} není mezi rozvahovými účty SVJ.")
    rozdil = sum(stav.zustatky.values())
    if rozdil:
        raise ChybaPocatku(
            f"Aktiva a pasiva se neshodují, rozdíl je {kc(abs(rozdil))}. "
            "Zkontrolujte opsané zůstatky."
        )
    if not any(stav.zustatky.values()):
        raise ChybaPocatku("Nejsou zadané žádné zůstatky.")
    vlastnici = ucty_vlastniku(profil)
    for p in stav.polozky:
        if not stav.zustatky.get(p.ucet):
            raise ChybaPocatku(f"Rozpis patří k účtu {p.ucet}, který nemá zadaný zůstatek.")
        if p.ucet in vlastnici and p.jednotka not in profil.jednotky:
            raise ChybaPocatku(f"U dluhu na účtu {p.ucet} chybí jednotka nebo neexistuje.")
        if p.castka == 0:
            raise ChybaPocatku("Rozpis obsahuje nulovou částku.")
    for u, z in stav.zustatky.items():
        casti = [p.castka for p in stav.polozky if p.ucet == u]
        if (u in vlastnici and z) or casti:
            if sum(casti) != z:
                raise ChybaPocatku(
                    f"Rozpis účtu {u} ({profil.nazev_uctu(u)}) dává "
                    f"{kc(sum(casti))}, zůstatek je {kc(z)}."
                )


def _radek(castka: int, role: str, **dimenze: str | None) -> Radek:
    return Radek(
        strana="md" if castka > 0 else "d",
        role=role,
        castka=abs(castka),
        dimenze={k: v for k, v in dimenze.items() if v},
    )


def zauctuj(session: Session, profil: Profil, stav: PocatecniStav, *, zauctoval: str) -> Zapis:
    zkontroluj(profil, stav)
    if zauctovany(session, stav.rok) is not None:
        raise ChybaPocatku(
            f"Počáteční stavy roku {stav.rok} už jsou zaúčtované. Opravit je jde jen stornem."
        )
    try:
        profil.ucet("pocatecni_rozvazny")
    except NeznamaRole as e:
        raise ChybaPocatku("Profil SVJ nemá počáteční účet rozvažný.") from e
    role = rozvahove_ucty(profil)
    radky: list[Radek] = []
    for u, z in stav.zustatky.items():
        if not z:
            continue
        casti = [p for p in stav.polozky if p.ucet == u]
        if casti:
            radky += [
                _radek(
                    p.castka,
                    role[u],
                    jednotka=p.jednotka,
                    protistrana=p.drivejsi_vlastnik,
                    popis=p.popis or None,
                )
                for p in casti
            ]
        else:
            radky.append(_radek(z, role[u]))
    aktiva = sum(z for z in stav.zustatky.values() if z > 0)
    radky += [_radek(-aktiva, "pocatecni_rozvazny"), _radek(aktiva, "pocatecni_rozvazny")]
    try:
        return denik.zauctuj(
            session,
            profil,
            katalog.nacti()[OPERACE],
            {},
            datum=date(stav.rok, 1, 1),
            popis=f"Počáteční stavy k 1. 1. {stav.rok}",
            doklad=f"PS {stav.rok}",
            zauctoval=zauctoval,
            idempotencni_klic=klic(stav.rok),
            radky=radky,
        )
    except denik.ChybaUctovani as e:
        raise ChybaPocatku(str(e)) from e


def zauctovany(session: Session, rok: int) -> Zapis | None:
    return denik.aktivni(session, klic(rok))


def nacti(session: Session, profil: Profil, rok: int) -> PocatecniStav | None:
    """Zaúčtované počáteční stavy zpátky jako zůstatky a rozpis."""
    z = zauctovany(session, rok)
    if z is None:
        return None
    zustatky: dict[str, int] = {}
    polozky: list[Polozka] = []
    for r in session.scalars(select(RadekZapisu).where(RadekZapisu.zapis_id == z.id)):
        if r.role == "pocatecni_rozvazny":
            continue
        castka = r.castka if r.strana == "md" else -r.castka
        zustatky[r.ucet] = zustatky.get(r.ucet, 0) + castka
        if r.jednotka or r.protistrana or r.popis:
            polozky.append(Polozka(r.ucet, castka, r.jednotka, r.popis or "", r.protistrana))
    return PocatecniStav(rok, zustatky, polozky)


@dataclass
class KontrolaBanky:
    ucet: str  # číslo účtu v účetnictví (221100)
    ucel: str
    zacatek_vypisu: int | None  # počáteční zůstatek prvního výpisu roku
    vypis: str | None


def kontrola_banky(session: Session, profil: Profil, rok: int) -> list[KontrolaBanky]:
    """Počáteční zůstatek prvního výpisu roku u každého bankovního účtu SVJ."""
    vysledek = []
    for ucel in profil.bankovni_ucty:
        bu = session.scalar(select(BankovniUcet).where(BankovniUcet.ucel == ucel))
        prvni = (
            session.scalar(
                select(BankovniVypis)
                .where(
                    BankovniVypis.ucet_id == bu.id,
                    BankovniVypis.druh == "vypis",
                    BankovniVypis.rok == rok,
                )
                .order_by(BankovniVypis.datum, BankovniVypis.cislo)
                .limit(1)
            )
            if bu
            else None
        )
        vysledek.append(
            KontrolaBanky(
                ucet=profil.ucet(f"banka.{ucel}"),
                ucel=ucel,
                zacatek_vypisu=prvni.stary_zustatek if prvni else None,
                vypis=f"{prvni.cislo}/{prvni.rok}" if prvni else None,
            )
        )
    return vysledek
