"""Ostatní výnosy SVJ: smluvní pokuty od dodavatelů, pojistné plnění a dotace (příručka,
kapitola 4).

Pohledávky z těchto výnosů se vedou po protistraně (dodavatel, pojistná událost, poskytovatel
dotace) v dimenzi `protistrana`. Odtud se nabízí, co je ještě otevřené: pokuta k zápočtu
nebo úhradě, odhad pojistného plnění k oznámení, nevyčerpaná dotace k použití.
"""

from datetime import date

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from . import denik, faktury
from .db import RadekZapisu, Zapis
from .domena import katalog
from .domena.penize import kc, na_text
from .domena.profil import Profil

# Co je otevřené: role → strana, na které je zůstatek kladný.
POKUTY = "pohledavky_sankce_dodavatele"
POJISTNE = "pohledavky_pojistne"
ODHADY_POJISTNEHO = "dohadne_aktivni"
DOTACE_POHLEDAVKY = "pohledavky_dotace"
DOTACE_NAROK = "narok_dotace"
STRANA = {
    POKUTY: "md",
    POJISTNE: "md",
    ODHADY_POJISTNEHO: "md",
    DOTACE_POHLEDAVKY: "md",
    DOTACE_NAROK: "d",
}
OPERACE_ZAPOCTU = "smluvni-pokuta-zapocet"


class ChybaVynosu(ValueError):
    pass


def otevrene(
    s: Session, profil: Profil, role: str, *, rok: int | None = None, do: date | None = None
) -> dict[str, int]:
    """Protistrana → kladný zůstatek role.

    Bez roku přes všechny roky (uzavření roku a otevření dalšího se navzájem vyruší), s rokem
    jen zápisy toho roku včetně počátečního stavu, volitelně do data."""
    if role not in profil.role:
        return {}
    znamenko = 1 if STRANA[role] == "md" else -1
    soucet = func.sum(
        case((RadekZapisu.strana == "md", RadekZapisu.castka), else_=-RadekZapisu.castka)
    )
    dotaz = (
        select(RadekZapisu.protistrana, soucet)
        .join(Zapis)
        .where(RadekZapisu.ucet == profil.ucet(role), denik.nestornovany())
        .group_by(RadekZapisu.protistrana)
    )
    if rok is not None:
        dotaz = dotaz.where(Zapis.rok == rok, denik.bez_uzaverky())
    if do is not None:
        dotaz = dotaz.where(Zapis.datum <= do)
    vysledek = {}
    for protistrana, z in s.execute(dotaz):
        if z and znamenko * int(z) > 0:
            vysledek[protistrana or ""] = znamenko * int(z)
    return dict(sorted(vysledek.items()))


def popisky(otevrene_polozky: dict[str, int], co: str) -> dict[str, str]:
    """Hodnoty pro výběr ve formuláři: protistrana → „protistrana (co 12 000,00 Kč)“."""
    return {p: f"{p or 'bez určení'} ({co} {kc(c)})" for p, c in otevrene_polozky.items() if p}


def _stejny(a: str, b: str) -> bool:
    return " ".join(a.split()).lower() == " ".join(b.split()).lower()


def pokuty_dodavatele(s: Session, profil: Profil, dodavatel: str) -> int:
    """Kolik z uplatněných smluvních pokut dodavatel ještě nezaplatil ani nemá započteno."""
    return sum(c for p, c in otevrene(s, profil, POKUTY).items() if _stejny(p, dodavatel))


def zapocti_pokutu(
    s: Session,
    profil: Profil,
    cislo_faktury: str,
    castka: int,
    *,
    datum: date,
    zauctoval: str,
) -> Zapis:
    """Započte uplatněnou smluvní pokutu proti faktuře téhož dodavatele."""
    try:
        stav = faktury.otevrena(s, cislo_faktury)
    except faktury.ChybaFaktury as e:
        raise ChybaVynosu(str(e)) from e
    f = stav.faktura
    if castka <= 0:
        raise ChybaVynosu("Započítávaná částka musí být kladná.")
    if castka > stav.zbyva:
        raise ChybaVynosu(
            f"Z faktury {f.cislo} zbývá zaplatit jen {kc(stav.zbyva)}, víc započíst nejde."
        )
    pokuty = pokuty_dodavatele(s, profil, f.dodavatel)
    if castka > pokuty:
        raise ChybaVynosu(
            f"Dodavatel {f.dodavatel} má nezaplacené smluvní pokuty jen {kc(pokuty)}. "
            "Pokutu nejdřív uplatněte interním dokladem „Smluvní pokuta dodavateli“."
        )
    if datum < f.duzp:
        raise ChybaVynosu("Zápočet nemůže být dřív, než vznikla faktura.")
    # Protistrana podle uplatněné pokuty, aby se pohledávka vyrovnala i při jiném zápisu jména.
    protistrana = next(p for p in otevrene(s, profil, POKUTY) if _stejny(p, f.dodavatel))
    op = katalog.nacti()[OPERACE_ZAPOCTU]
    vstupy = {"protistrana": protistrana, "castka": na_text(castka)}
    radky = faktury.s_parovacim_symbolem(katalog.sestav(op, vstupy), f.cislo)
    try:
        return denik.zauctuj(
            s,
            profil,
            op,
            vstupy,
            datum=datum,
            popis=f"Zápočet smluvní pokuty proti faktuře FP {f.cislo} · {f.dodavatel}",
            doklad="ID",
            zauctoval=zauctoval,
            radky=radky,
        )
    except denik.ChybaUctovani as e:
        raise ChybaVynosu(str(e)) from e
