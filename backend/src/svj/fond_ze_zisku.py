"""Výsledek hospodaření minulého roku a fond ze zisku (příručka, kapitola 2).

Výsledek roku se při otevření dalšího roku převede na 931 (výsledek ve schvalovacím řízení).
Shromáždění pak rozhodne, co s ním: zisk nejdřív uhradí neuhrazené ztráty minulých let (932)
a zbytek jde do fondu ze zisku (911); ztráta jde na 932 (`rozdeleni-vysledku`). Do fondu
oprav se zisk nepřevádí.

Z fondu ze zisku se hradí opravy, o kterých rozhodl výbor nebo shromáždění: faktura jde do
nákladů a fond se ve stejné výši rozpustí do výnosů (`cerpani-fondu-ze-zisku`). Fond ze
zisku kryje i pořízení majetku (911/901, viz majetek.py). Do záporu jít nesmí.
"""

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import denik
from .db import RadekZapisu, Zapis
from .domena import katalog
from .domena.penize import kc, na_text
from .domena.profil import Profil

OPERACE_ROZDELENI = "rozdeleni-vysledku"
ROLE_FONDU = "fond_ze_zisku"
ROLE_VYSLEDKU = "vysledek_ve_schvalovani"
ROLE_ZTRATY = "neuhrazena_ztrata"


class ChybaFondu(ValueError):
    pass


def klic_rozdeleni(rok: int) -> str:
    return f"rozdeleni-vysledku:{rok}"


def nastaveno(profil: Profil) -> bool:
    return ROLE_FONDU in profil.role and ROLE_VYSLEDKU in profil.role


def _d(d: date) -> str:
    return f"{d.day}. {d.month}. {d.year}"


def _zustatek(s: Session, profil: Profil, role: str, rok: int, do: date | None) -> int:
    """Zůstatek role na straně D (kladně = pasivum), před uzávěrkovými zápisy."""
    if role not in profil.role:
        return 0
    return -denik.zustatky(s, rok, do).get(profil.ucet(role), 0)


def zustatek_fondu(s: Session, profil: Profil, rok: int, do: date | None = None) -> int:
    return _zustatek(s, profil, ROLE_FONDU, rok, do)


def zkontroluj_cerpani(s: Session, profil: Profil, castka: int, datum: date) -> None:
    """Fond ze zisku nesmí jít do záporu: ani k datu čerpání, ani na konci roku."""
    if not nastaveno(profil):
        raise ChybaFondu("SVJ nemá v nastavení účet pro fond ze zisku.")
    volne = min(zustatek_fondu(s, profil, datum.year, datum), zustatek_fondu(s, profil, datum.year))
    if castka <= volne:
        return
    zprava = f"Ve fondu ze zisku je jen {kc(max(volne, 0))}."
    if _zustatek(s, profil, ROLE_VYSLEDKU, datum.year, None) and not denik.aktivni(
        s, klic_rozdeleni(datum.year)
    ):
        zprava += (
            " Zisk minulého roku ještě není převedený do fondu; zaúčtujte nejdřív jeho "
            "rozdělení na stránce Fond ze zisku."
        )
    raise ChybaFondu(zprava)


@dataclass
class Pohyb:
    datum: date
    doklad: str
    popis: str
    castka: int  # kladně přírůstek fondu, záporně čerpání
    zapis: str  # číslo zápisu v deníku "n/rok"


@dataclass
class Rozdeleni:
    zisk_do_fondu: int
    zisk_na_ztraty: int
    ztrata: int


@dataclass
class Stav:
    rok: int
    nastaveno: bool
    otevreno: bool  # rok má zaúčtované počáteční stavy
    vysledek: int  # výsledek minulého roku, který čeká na rozdělení (kladně zisk)
    navrh: Rozdeleni | None
    rozdeleni: Zapis | None
    pocatek: int
    pohyby: list[Pohyb]
    konec: int
    neuhrazena_ztrata: int  # kladně = ztráta, kterou ještě nic neuhradilo


def navrhni(vysledek: int, neuhrazena_ztrata: int) -> Rozdeleni:
    """Zisk nejdřív uhradí neuhrazené ztráty, zbytek jde do fondu; ztráta jde na 932."""
    if vysledek >= 0:
        na_ztraty = min(vysledek, max(neuhrazena_ztrata, 0))
        return Rozdeleni(vysledek - na_ztraty, na_ztraty, 0)
    return Rozdeleni(0, 0, -vysledek)


def _pohyby(s: Session, profil: Profil, rok: int) -> list[Pohyb]:
    if ROLE_FONDU not in profil.role:
        return []
    radky = s.execute(
        select(RadekZapisu, Zapis)
        .join(Zapis)
        .where(
            Zapis.rok == rok,
            RadekZapisu.ucet == profil.ucet(ROLE_FONDU),
            Zapis.operace != "otevreni-pocatecnimi-stavy",
            denik.platny(),
        )
        .order_by(Zapis.datum, Zapis.poradove_cislo, RadekZapisu.id)
    ).all()
    vysledek: dict[int, Pohyb] = {}
    for r, z in radky:
        castka = r.castka if r.strana == "d" else -r.castka
        if z.id in vysledek:
            vysledek[z.id].castka += castka
        else:
            vysledek[z.id] = Pohyb(
                z.datum, z.doklad, z.popis, castka, f"{z.poradove_cislo}/{z.rok}"
            )
    return [p for p in vysledek.values() if p.castka]


def stav(s: Session, profil: Profil, rok: int) -> Stav:
    from . import pocatecni

    otevreni = pocatecni.zauctovany(s, rok)
    rozdeleni = denik.aktivni(s, klic_rozdeleni(rok))
    ztrata = -_zustatek(s, profil, ROLE_ZTRATY, rok, None)
    vysledek = _zustatek(s, profil, ROLE_VYSLEDKU, rok, None)
    pocatek = 0
    if otevreni is not None and ROLE_FONDU in profil.role:
        ucet = profil.ucet(ROLE_FONDU)
        pocatek = sum(
            (r.castka if r.strana == "d" else -r.castka) for r in otevreni.radky if r.ucet == ucet
        )
    pohyby = _pohyby(s, profil, rok)
    return Stav(
        rok=rok,
        nastaveno=nastaveno(profil),
        otevreno=otevreni is not None,
        vysledek=vysledek,
        navrh=navrhni(vysledek, ztrata) if vysledek and rozdeleni is None else None,
        rozdeleni=rozdeleni,
        pocatek=pocatek,
        pohyby=pohyby,
        konec=pocatek + sum(p.castka for p in pohyby),
        neuhrazena_ztrata=ztrata,
    )


def rozdel(
    s: Session,
    profil: Profil,
    rok: int,
    *,
    datum: date,
    rozhodnuti: str,
    zauctoval: str,
) -> Zapis:
    """Zaúčtuje rozdělení výsledku minulého roku podle rozhodnutí shromáždění."""
    if not nastaveno(profil):
        raise ChybaFondu("SVJ nemá v nastavení účet pro fond ze zisku.")
    if datum.year != rok:
        raise ChybaFondu(f"Datum rozdělení musí být v roce {rok}.")
    rozhodnuti = " ".join(rozhodnuti.split())
    if not rozhodnuti:
        raise ChybaFondu("Napište, kdy o výsledku rozhodlo shromáždění (např. 15. 4. 2027, bod 3).")
    if denik.aktivni(s, klic_rozdeleni(rok)) is not None:
        raise ChybaFondu(f"Výsledek minulého roku je v roce {rok} už rozdělený.")
    st = stav(s, profil, rok)
    if not st.otevreno:
        raise ChybaFondu(f"Nejdřív zaúčtujte počáteční stavy roku {rok}.")
    if st.navrh is None:
        raise ChybaFondu(f"Výsledek roku {rok - 1} je nulový, není co rozdělovat.")
    n = st.navrh
    if (n.zisk_na_ztraty or n.ztrata) and ROLE_ZTRATY not in profil.role:
        raise ChybaFondu("SVJ nemá v nastavení účet pro neuhrazenou ztrátu minulých let (932).")
    vstupy = {
        "zisk_do_fondu": na_text(n.zisk_do_fondu),
        "zisk_na_ztraty": na_text(n.zisk_na_ztraty),
        "ztrata": na_text(n.ztrata),
        "rozhodnuti": rozhodnuti,
    }
    co = f"zisk {kc(st.vysledek)}" if st.vysledek > 0 else f"ztráta {kc(-st.vysledek)}"
    try:
        return denik.zauctuj(
            s,
            profil,
            katalog.nacti()[OPERACE_ROZDELENI],
            vstupy,
            datum=datum,
            popis=f"Rozdělení výsledku roku {rok - 1} ({co}) · {rozhodnuti}",
            doklad="ID",
            zauctoval=zauctoval,
            idempotencni_klic=klic_rozdeleni(rok),
        )
    except denik.ChybaUctovani as e:
        raise ChybaFondu(str(e)) from e
