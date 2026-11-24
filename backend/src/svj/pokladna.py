"""Hotovostní pokladna: pokladní kniha a pokladní doklady.

Hotovost se do pokladny dostane výběrem z účtu: v Bance se výběr zaúčtuje na peníze na
cestě (`pokladna-vyber`, krok `vyber`) a příjmovým dokladem se převede do pokladny (krok
`prijem`). Z pokladny se platí drobné výdaje (`pokladna-vydaj`) a vlastník může zaplatit
hotově (`pokladna-platba-vlastnika`). Pokladna nesmí jít do minusu, a to ani zpětně:
výdaj s dřívějším datem nesmí snížit zůstatek pod nulu v žádný pozdější den.
"""

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import denik
from .db import RadekZapisu, Zapis
from .domena import katalog
from .domena.penize import kc, na_text
from .domena.profil import NeznamaRole, Profil

# Druh dokladu → (operace, krok)
DRUHY = {
    "prijem_z_uctu": ("pokladna-vyber", "prijem"),
    "vydaj": ("pokladna-vydaj", None),
    "platba_vlastnika": ("pokladna-platba-vlastnika", None),
}


class ChybaPokladny(ValueError):
    pass


@dataclass
class Polozka:
    datum: date
    cislo: str  # číslo zápisu v deníku "n/rok"
    doklad: str
    popis: str
    prijem: int
    vydaj: int
    zustatek: int  # po této položce


@dataclass
class Kniha:
    rok: int
    polozky: list[Polozka]
    zustatek: int  # po poslední položce roku
    na_ceste: int  # vybráno z účtu, ještě nepřijato do pokladny


def nastavena(profil: Profil) -> bool:
    return "pokladna" in profil.role


def kniha(s: Session, profil: Profil, rok: int) -> Kniha:
    ucet = profil.ucet("pokladna")
    radky = s.execute(
        select(Zapis, RadekZapisu.strana, RadekZapisu.castka)
        .join(RadekZapisu)
        .where(Zapis.rok == rok, RadekZapisu.ucet == ucet, denik.platny())
        .order_by(Zapis.datum, Zapis.poradove_cislo, RadekZapisu.id)
    ).all()
    polozky: list[Polozka] = []
    zustatek = 0
    for z, strana, castka in radky:
        prijem, vydaj = (castka, 0) if strana == "md" else (0, castka)
        zustatek += prijem - vydaj
        polozky.append(
            Polozka(
                z.datum, f"{z.poradove_cislo}/{z.rok}", z.doklad, z.popis, prijem, vydaj, zustatek
            )
        )
    na_ceste = (
        denik.zustatky(s, rok).get(profil.ucet("penize_na_ceste"), 0)
        if "penize_na_ceste" in profil.role
        else 0
    )
    return Kniha(rok, polozky, zustatek, na_ceste)


def _nejnizsi_od(k: Kniha, datum: date) -> int:
    """Nejnižší zůstatek pokladny ode dne `datum` do konce roku."""
    pred = [p.zustatek for p in k.polozky if p.datum <= datum]
    po = [p.zustatek for p in k.polozky if p.datum > datum]
    return min([pred[-1] if pred else 0, *po])


def zauctuj(
    s: Session,
    profil: Profil,
    druh: str,
    *,
    castka: int,
    datum: date,
    popis: str,
    zauctoval: str,
    jednotka: str = "",
    sluzba: str = "",
) -> Zapis:
    if not nastavena(profil):
        raise ChybaPokladny("Společenství nemá v nastavení účet pokladny.")
    if druh not in DRUHY:
        raise ChybaPokladny("Neznámý druh pokladního dokladu.")
    popis = popis.strip()
    if not popis:
        raise ChybaPokladny("Napište, čeho se doklad týká.")
    if castka <= 0:
        raise ChybaPokladny("Částka musí být kladná.")
    operace_id, krok = DRUHY[druh]
    vstupy = {"castka": na_text(castka)}
    k = kniha(s, profil, datum.year)
    if druh == "prijem_z_uctu":
        na_ceste = denik.zustatky(s, datum.year, datum).get(profil.ucet("penize_na_ceste"), 0)
        if castka > na_ceste:
            raise ChybaPokladny(
                "Z účtu je k tomuto dni vybráno a do pokladny nepřijato jen "
                f"{kc(max(na_ceste, 0))}. Výběr nejdřív zaúčtujte v Bance jako výběr "
                "hotovosti do pokladny."
            )
    elif druh == "vydaj":
        if sluzba and sluzba not in profil.sprava:
            raise ChybaPokladny("Vyberte položku správy z nabídky.")
        nejnizsi = _nejnizsi_od(k, datum)
        if castka > nejnizsi:
            raise ChybaPokladny(
                f"V pokladně by nebylo dost hotovosti: od tohoto dne v ní je nejméně "
                f"{kc(max(nejnizsi, 0))}."
            )
        vstupy["sluzba"] = sluzba
    else:
        if jednotka not in profil.jednotky:
            raise ChybaPokladny("Vyberte jednotku, za kterou vlastník platí.")
        vstupy["jednotka"] = jednotka
    try:
        return denik.zauctuj(
            s,
            profil,
            katalog.nacti()[operace_id],
            vstupy,
            datum=datum,
            popis=popis,
            doklad="PD",
            zauctoval=zauctoval,
            krok=krok,
        )
    except (denik.ChybaUctovani, NeznamaRole) as e:
        raise ChybaPokladny(str(e)) from e
