"""Zaúčtování operace z katalogu do deníku."""

from datetime import date
from typing import Any

from sqlalchemy import ColumnElement, and_, case, exists, func, or_, select
from sqlalchemy.orm import Session, aliased

from .db import Obdobi, RadekZapisu, Zapis
from .domena import katalog
from .domena.profil import Profil


class ChybaUctovani(ValueError):
    pass


STORNO = "storno"


# Uzávěrkové zápisy k 31. 12. vynulují účty roku. Přehledy a výkazy roku je nevidí, jinak
# by po uzavření ukazovaly samé nuly; deník a dotazy přes víc let (úhrady faktur) ano.
UZAVERKA = ("uzavreni-vysledkovych", "uzavreni-rozvahovych")


def nestornovany() -> ColumnElement[bool]:
    """Zápis, který platí: není to storno a nikdo ho nestornoval."""
    storno = aliased(Zapis)
    return and_(
        Zapis.operace != STORNO,
        ~exists().where(storno.opravuje_zapis == Zapis.id, storno.operace == STORNO),
    )


def bez_uzaverky() -> ColumnElement[bool]:
    """Zápis není uzávěrkový ani storno uzávěrkového (to by po znovuotevření roku zůstatky
    zdvojilo)."""
    puvodni = aliased(Zapis)
    return and_(
        Zapis.operace.not_in(UZAVERKA),
        ~exists().where(puvodni.id == Zapis.opravuje_zapis, puvodni.operace.in_(UZAVERKA)),
    )


def platny() -> ColumnElement[bool]:
    """Podmínka pro přehledy roku: zápis platí a není uzávěrkový.

    Storno a stornovaný zápis se v zůstatcích přesně vyruší; v přehledech (předpisy,
    platby, saldo) je ale nechceme vidět vůbec.
    """
    return and_(nestornovany(), bez_uzaverky())


def _s_klicem(klic: str) -> ColumnElement[bool]:
    # Po stornu se stejná věc účtuje znovu s klíčem „klic#2“, „klic#3“…
    vzor = klic.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "#%"
    return or_(Zapis.idempotencni_klic == klic, Zapis.idempotencni_klic.like(vzor, escape="\\"))


def zakladni_klic(klic: str | None) -> str | None:
    return klic.split("#", 1)[0] if klic else klic


def aktivni(session: Session, klic: str) -> Zapis | None:
    """Platný zápis s daným idempotenčním klíčem (nestornovaný)."""
    return session.scalar(select(Zapis).where(_s_klicem(klic), nestornovany()))


def _volny_klic(session: Session, klic: str) -> str:
    pocet = session.scalar(select(func.count()).select_from(Zapis).where(_s_klicem(klic))) or 0
    return klic if pocet == 0 else f"{klic}#{pocet + 1}"


def _novy_zapis(session: Session, *, datum: date, **udaje: Any) -> Zapis:
    # Zámek na řádku období zajistí pořadová čísla bez mezer i při souběžném účtování.
    obdobi = session.scalar(select(Obdobi).where(Obdobi.rok == datum.year).with_for_update())
    if obdobi is None or obdobi.stav != "otevrene":
        raise ChybaUctovani(f"období {datum.year} není otevřené")
    poradi = (
        session.scalar(select(func.max(Zapis.poradove_cislo)).where(Zapis.rok == datum.year)) or 0
    ) + 1
    return Zapis(rok=datum.year, poradove_cislo=poradi, datum=datum, **udaje)


def zauctuj(
    session: Session,
    profil: Profil,
    operace: katalog.Operace,
    vstupy: dict[str, Any] | list[dict[str, Any]],
    *,
    datum: date,
    popis: str,
    doklad: str,
    zauctoval: str,
    krok: str | None = None,
    idempotencni_klic: str | None = None,
    radky: list[katalog.Radek] | None = None,
) -> Zapis:
    """Sestaví řádky podle katalogu, převede role na účty a zapíše je.

    Opakované volání se stejným idempotenčním klíčem vrátí už existující zápis.
    Stav operace v katalogu zaúčtování neomezuje: postup, který ještě nepotvrdila
    účetní, se jen ukáže v kontrolním seznamu uzávěrky.
    """
    if idempotencni_klic:
        existujici = aktivni(session, idempotencni_klic)
        if existujici is not None:
            return existujici
        idempotencni_klic = _volny_klic(session, idempotencni_klic)
    # Víc sad vstupů = jeden zápis s řádky za všechny (např. předpis měsíce za všechny jednotky).
    # Operace se způsobem `kod` (otevření roku, uzávěrka) sestaví řádky samy.
    if radky is None:
        sady = vstupy if isinstance(vstupy, list) else [vstupy]
        radky = [r for v in sady for r in katalog.sestav(operace, v, krok)]
    zapis = _novy_zapis(
        session,
        datum=datum,
        doklad=doklad,
        operace=operace.id,
        popis=popis,
        idempotencni_klic=idempotencni_klic,
        zauctoval=zauctoval,
    )
    for r in radky:
        zapis.radky.append(
            RadekZapisu(
                strana=r.strana,
                role=r.role,
                ucet=profil.ucet(r.role),
                castka=r.castka,
                jednotka=r.dimenze.get("jednotka"),
                sluzba=r.dimenze.get("sluzba"),
                protistrana=r.dimenze.get("protistrana"),
                popis=r.dimenze.get("popis"),
                parovaci_symbol=r.dimenze.get("parovaci_symbol"),
                splatnost=date.fromisoformat(r.dimenze["splatnost"])
                if r.dimenze.get("splatnost")
                else None,
            )
        )
    session.add(zapis)
    session.flush()
    return zapis


def storno(
    session: Session,
    zapis_id: int,
    *,
    duvod: str,
    zauctoval: str,
    kontrolovat_navaznost: bool = True,
) -> Zapis:
    """Stornuje zápis: kopie řádků s prohozenými stranami ke stejnému datu.

    Původní zápis zůstane beze změny. Co bylo stornované, jde potom zaúčtovat znovu.
    """
    duvod = " ".join(duvod.split())
    if not duvod:
        raise ChybaUctovani("Napište, proč se zápis stornuje.")
    z = session.scalar(select(Zapis).where(Zapis.id == zapis_id).with_for_update())
    if z is None:
        raise ChybaUctovani("Zápis neexistuje.")
    cislo = f"{z.poradove_cislo}/{z.rok}"
    if z.operace == STORNO:
        raise ChybaUctovani(f"Zápis {cislo} je sám storno; stornovat ho nejde.")
    if session.scalar(
        select(Zapis.id).where(Zapis.opravuje_zapis == z.id, Zapis.operace == STORNO)
    ):
        raise ChybaUctovani(f"Zápis {cislo} už je stornovaný.")
    symboly = {r.parovaci_symbol for r in z.radky if r.parovaci_symbol}
    if symboly and kontrolovat_navaznost:
        navazujici = session.execute(
            select(Zapis.poradove_cislo, Zapis.rok)
            .join(RadekZapisu)
            .where(RadekZapisu.parovaci_symbol.in_(symboly), Zapis.id > z.id, nestornovany())
            .order_by(Zapis.id)
        ).first()
        if navazujici:
            raise ChybaUctovani(
                f"Na zápis {cislo} navazuje zápis {navazujici[0]}/{navazujici[1]} (např. úhrada"
                " faktury). Nejdřív stornujte ten."
            )
    novy = _novy_zapis(
        session,
        datum=z.datum,
        doklad=f"ID {cislo}"[:32],
        operace=STORNO,
        popis=f"Storno zápisu {cislo} ({z.popis}). Důvod: {duvod}",
        opravuje_zapis=z.id,
        idempotencni_klic=f"storno:{z.id}",
        zauctoval=zauctoval,
    )
    for r in z.radky:
        novy.radky.append(
            RadekZapisu(
                strana="d" if r.strana == "md" else "md",
                role=r.role,
                ucet=r.ucet,
                castka=r.castka,
                jednotka=r.jednotka,
                sluzba=r.sluzba,
                protistrana=r.protistrana,
                popis=r.popis,
                parovaci_symbol=r.parovaci_symbol,
                splatnost=r.splatnost,
            )
        )
    session.add(novy)
    session.flush()
    return novy


def zustatky(
    session: Session, rok: int, do: date | None = None, *, vcetne_uzaverky: bool = False
) -> dict[str, int]:
    """Zůstatky účtů za rok v haléřích, kladné na straně MD, před uzávěrkovými zápisy."""
    znamenko = func.sum(
        case((RadekZapisu.strana == "md", RadekZapisu.castka), else_=-RadekZapisu.castka)
    )
    dotaz = (
        select(RadekZapisu.ucet, znamenko)
        .join(Zapis)
        .where(Zapis.rok == rok)
        .group_by(RadekZapisu.ucet)
    )
    if do is not None:
        dotaz = dotaz.where(Zapis.datum <= do)
    if not vcetne_uzaverky:
        dotaz = dotaz.where(bez_uzaverky())
    return {ucet: int(z) for ucet, z in session.execute(dotaz)}
