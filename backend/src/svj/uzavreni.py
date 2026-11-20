"""Uzavření účetního roku a otevření dalšího z konečných zůstatků.

Kroky k 31. 12. roku:

1. `uzavreni-vysledkovych`: zůstatky nákladů (5) a výnosů (6) na účet výsledku (963).
2. `uzavreni-rozvahovych`: každý rozvahový zůstatek i s rozpisem (jednotka, služba,
   faktura, dřívější vlastník) na konečný účet rozvažný (962); účet výsledku také.
3. K 1. 1. dalšího roku zrcadlově počáteční stavy (`otevreni-pocatecnimi-stavy`) proti
   počátečnímu účtu rozvažnému (961). Výsledek roku se otevře jako výsledek ve schvalovacím
   řízení (931). Součet otevření přesně odpovídá uzavření (§ 19 odst. 4 ZoÚ).

Dluhy vlastníků se převádějí po položkách (zálohy za měsíc, nedoplatek z vyúčtování)
i se splatností, aby v novém roce šlo poznat, co je po splatnosti, a spočítat úrok.
Platby se přitom započítávají jen v rámci účtu, takže zůstatek každého účtu navazuje.

Rok jde uzavřít, až uzávěrka nehlásí nic chybějícího a ruční body jsou odškrtnuté. Do
uzavřeného roku databáze nic nepustí. Než shromáždění závěrku schválí, jde rok znovu
otevřít (§ 17 odst. 7 ZoÚ): uzávěrkové zápisy i počáteční stavy dalšího roku se stornují.
"""

from dataclasses import dataclass
from datetime import date

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from . import denik, dluznici, pocatecni, predpisy, ulozene, uzaverka
from .db import Obdobi, RadekZapisu, Zapis
from .domena import katalog
from .domena.katalog import Radek
from .domena.penize import kc
from .domena.profil import NeznamaRole, Profil

VYSLEDKOVE = "uzavreni-vysledkovych"
ROZVAHOVE = "uzavreni-rozvahovych"
ROLE_VLASTNIKU = set(pocatecni.ROLE_VLASTNIKU)


class ChybaUzavreni(ValueError):
    pass


@dataclass
class Polozka:
    """Konečný zůstatek, který se převádí: kladný na straně MD."""

    role: str
    castka: int
    dimenze: dict[str, str]


@dataclass
class Stav:
    rok: int
    stav: str | None  # stav období roku: otevrene | uzavrene | None (není založené)
    dalsi: str | None  # stav období dalšího roku
    vysledkove: Zapis | None
    rozvahove: Zapis | None
    otevreni: Zapis | None  # počáteční stavy dalšího roku

    @property
    def uzavreny(self) -> bool:
        return self.stav == "uzavrene"


def klic(rok: int, krok: str) -> str:
    return f"{krok}:{rok}"


def stav(s: Session, rok: int) -> Stav:
    o = s.get(Obdobi, rok)
    d = s.get(Obdobi, rok + 1)
    return Stav(
        rok=rok,
        stav=o.stav if o else None,
        dalsi=d.stav if d else None,
        vysledkove=denik.aktivni(s, klic(rok, VYSLEDKOVE)),
        rozvahove=denik.aktivni(s, klic(rok, ROZVAHOVE)),
        otevreni=pocatecni.zauctovany(s, rok + 1) if d else None,
    )


def zacni_dalsi_rok(s: Session, rok: int) -> None:
    """Založí období dalšího roku, aby šlo účtovat předpisy a výpisy ještě před uzávěrkou."""
    if s.get(Obdobi, rok) is None:
        raise ChybaUzavreni(f"Rok {rok} v aplikaci není.")
    if s.get(Obdobi, rok + 1) is None:
        s.add(Obdobi(rok=rok + 1, stav="otevrene"))
        s.flush()


def _role(profil: Profil, role: str) -> str:
    try:
        return profil.ucet(role)
    except NeznamaRole as e:
        raise ChybaUzavreni(
            f"Profil SVJ nemá účet pro roli {role!r}, uzavřít rok nejde. Doplňte ji do profilu."
        ) from e


def proc_nejde(
    s: Session, profil: Profil, nastaveni: predpisy.Nastaveni, rok: int, dnes: date
) -> list[str]:
    """Proč rok zatím nejde uzavřít (prázdný seznam = jde)."""
    st = stav(s, rok)
    if st.stav is None:
        return [f"Rok {rok} v aplikaci není."]
    if st.uzavreny:
        return [f"Rok {rok} už je uzavřený."]
    if dnes <= date(rok, 12, 31):
        return [f"Rok jde uzavřít až po 31. 12. {rok}."]
    if st.dalsi == "uzavrene":
        return [f"Rok {rok + 1} je uzavřený, počáteční stavy do něj zapsat nejde."]
    duvody = []
    if st.otevreni is not None:
        duvody.append(
            f"Počáteční stavy roku {rok + 1} už jsou zaúčtované (zápis "
            f"{st.otevreni.poradove_cislo}/{st.otevreni.rok}). Při uzavření je aplikace "
            "zaúčtuje sama z konečných zůstatků; ty ruční nejdřív stornujte v Deníku."
        )
    odskrtnute = ulozene.odskrtnute(s, rok)
    for k in uzaverka.kontroly(s, profil, nastaveni, rok, date(rok, 12, 31)):
        if k.stav == "chybi":
            duvody.append(f"{k.nazev}: {k.detail}" if k.detail else k.nazev)
        elif k.stav == "rucne" and k.kod not in odskrtnute:
            duvody.append(f"Není odškrtnuté: {k.nazev}.")
    return duvody


def _zustatky(s: Session, rok: int) -> list[tuple]:
    """Zůstatky roku po účtech a rozpisu, bez uzávěrkových zápisů."""
    znamenko = func.sum(
        case((RadekZapisu.strana == "md", RadekZapisu.castka), else_=-RadekZapisu.castka)
    )
    vlastnik_s_protistranou = RadekZapisu.role.in_(ROLE_VLASTNIKU) & RadekZapisu.protistrana.is_not(
        None
    )
    popis = case((vlastnik_s_protistranou, RadekZapisu.popis), else_=None)
    return s.execute(
        select(
            RadekZapisu.role,
            RadekZapisu.ucet,
            RadekZapisu.jednotka,
            RadekZapisu.sluzba,
            RadekZapisu.protistrana,
            popis,
            RadekZapisu.parovaci_symbol,
            znamenko,
        )
        .join(Zapis)
        .where(Zapis.rok == rok, denik.bez_uzaverky())
        .group_by(
            RadekZapisu.role,
            RadekZapisu.ucet,
            RadekZapisu.jednotka,
            RadekZapisu.sluzba,
            RadekZapisu.protistrana,
            popis,
            RadekZapisu.parovaci_symbol,
        )
        .order_by(RadekZapisu.ucet, RadekZapisu.jednotka, RadekZapisu.parovaci_symbol)
    ).all()


def _dim(**d) -> dict[str, str]:
    return {k: str(v) for k, v in d.items() if v}


def spocitej(
    s: Session, profil: Profil, nastaveni: predpisy.Nastaveni, rok: int
) -> tuple[list[Polozka], list[Polozka]]:
    """Výsledkové zůstatky (náklady, výnosy) a rozvahové položky k převodu."""
    for role in ("konecny_rozvazny", "ucet_vysledku", "vysledek_ve_schvalovani"):
        _role(profil, role)
    vysledkove: list[Polozka] = []
    rozvahove: list[Polozka] = []
    vlastnici: dict[tuple[str, str], int] = {}  # (role, jednotka) → zůstatek bez protistrany
    chybne: dict[str, int] = {}
    for role, ucet, jednotka, sluzba, protistrana, popis, symbol, z in _zustatky(s, rok):
        z = int(z)
        if not z:
            continue
        if ucet[0] in "56":
            vysledkove.append(Polozka(role, z, {}))
        elif ucet[:2] in ("39", "96"):
            chybne[ucet] = chybne.get(ucet, 0) + z
        elif role in ROLE_VLASTNIKU and protistrana is None and jednotka in profil.jednotky:
            vlastnici[(role, jednotka)] = vlastnici.get((role, jednotka), 0) + z
        else:
            rozvahove.append(
                Polozka(
                    role,
                    z,
                    _dim(
                        jednotka=jednotka,
                        sluzba=sluzba,
                        protistrana=protistrana,
                        popis=popis,
                        parovaci_symbol=symbol,
                    ),
                )
            )
    chybne = {u: z for u, z in chybne.items() if z}
    if chybne:
        seznam = ", ".join(f"{u} ({kc(abs(z))})" for u, z in sorted(chybne.items()))
        raise ChybaUzavreni(
            f"Vnitřní zúčtování a závěrkové účty mají mít nulový zůstatek: {seznam}."
        )

    # Dluhy a přeplatky současných vlastníků po položkách se splatností.
    for jednotka, role, polozky, kredit in dluznici.k_prevodu(s, profil, nastaveni, rok):
        zustatek = vlastnici.pop((role, jednotka), 0)
        if sum(p.zbyva for p in polozky) - kredit != zustatek:
            raise ChybaUzavreni(
                f"Rozpis dluhů jednotky {jednotka} na účtu {profil.ucet(role)} nesedí na "
                "zůstatek účtu. Ozvěte se prosím správci aplikace."
            )
        for p in polozky:
            rozvahove.append(
                Polozka(
                    role,
                    p.zbyva,
                    _dim(
                        jednotka=jednotka,
                        popis=p.popis[:200],
                        splatnost=p.splatnost.isoformat() if p.splatnost else None,
                    ),
                )
            )
        if kredit:
            rozvahove.append(
                Polozka(role, -kredit, _dim(jednotka=jednotka, popis=f"Přeplatek k 31. 12. {rok}"))
            )
    for (role, jednotka), z in vlastnici.items():
        if z:
            rozvahove.append(Polozka(role, z, _dim(jednotka=jednotka)))
    vysledek = sum(p.castka for p in vysledkove)
    if vysledek:
        rozvahove.append(Polozka("ucet_vysledku", vysledek, {}))
    return vysledkove, rozvahove


def _radek(castka: int, role: str, dimenze: dict[str, str]) -> Radek:
    return Radek(strana="md" if castka > 0 else "d", role=role, castka=abs(castka), dimenze=dimenze)


def _protistrana(polozky: list[Polozka], role: str, opacne: bool) -> list[Radek]:
    """Dva souhrnné řádky protiúčtu: kladné a záporné zůstatky zvlášť."""
    kladne = sum(p.castka for p in polozky if p.castka > 0)
    zaporne = sum(p.castka for p in polozky if p.castka < 0)
    znak = -1 if opacne else 1
    return [_radek(znak * c, role, {}) for c in (kladne, zaporne) if c]


def vysledek(vysledkove: list[Polozka]) -> int:
    """Výsledek hospodaření roku: kladný = zisk."""
    return -sum(p.castka for p in vysledkove)


def uzavri(
    s: Session,
    profil: Profil,
    nastaveni: predpisy.Nastaveni,
    rok: int,
    *,
    zauctoval: str,
    dnes: date | None = None,
) -> Stav:
    dnes = dnes or date.today()
    duvody = proc_nejde(s, profil, nastaveni, rok, dnes)
    if duvody:
        raise ChybaUzavreni(" ".join(duvody))
    vysledkove, rozvahove = spocitej(s, profil, nastaveni, rok)
    ops = katalog.nacti()
    konec = date(rok, 12, 31)
    if vysledkove:
        denik.zauctuj(
            s,
            profil,
            ops[VYSLEDKOVE],
            {},
            datum=konec,
            popis=f"Uzavření nákladů a výnosů {rok}",
            doklad=f"UZ {rok}",
            zauctoval=zauctoval,
            idempotencni_klic=klic(rok, VYSLEDKOVE),
            radky=[_radek(-p.castka, p.role, p.dimenze) for p in vysledkove]
            + _protistrana(vysledkove, "ucet_vysledku", opacne=False),
        )
    if not rozvahove:
        raise ChybaUzavreni(f"Rok {rok} nemá žádné zůstatky, není co převádět.")
    denik.zauctuj(
        s,
        profil,
        ops[ROZVAHOVE],
        {},
        datum=konec,
        popis=f"Uzavření rozvahových účtů {rok}",
        doklad=f"UZ {rok}",
        zauctoval=zauctoval,
        idempotencni_klic=klic(rok, ROZVAHOVE),
        radky=[_radek(-p.castka, p.role, p.dimenze) for p in rozvahove]
        + _protistrana(rozvahove, "konecny_rozvazny", opacne=False),
    )
    zacni_dalsi_rok(s, rok)
    otevreni = [
        Polozka(
            "vysledek_ve_schvalovani" if p.role == "ucet_vysledku" else p.role, p.castka, p.dimenze
        )
        for p in rozvahove
    ]
    denik.zauctuj(
        s,
        profil,
        ops[pocatecni.OPERACE],
        {},
        datum=date(rok + 1, 1, 1),
        popis=f"Počáteční stavy k 1. 1. {rok + 1} z uzavřeného roku {rok}",
        doklad=f"PS {rok + 1}",
        zauctoval=zauctoval,
        idempotencni_klic=pocatecni.klic(rok + 1),
        radky=[_radek(p.castka, p.role, p.dimenze) for p in otevreni]
        + _protistrana(otevreni, "pocatecni_rozvazny", opacne=True),
    )
    s.get(Obdobi, rok).stav = "uzavrene"
    s.flush()
    return stav(s, rok)


def znovu_otevri(s: Session, rok: int, *, duvod: str, zauctoval: str) -> Stav:
    """Otevře uzavřený rok kvůli opravě: stornuje uzávěrkové zápisy a počáteční stavy
    dalšího roku. Po opravě se rok uzavře znovu."""
    duvod = " ".join(duvod.split())
    if not duvod:
        raise ChybaUzavreni("Napište, proč se rok znovu otevírá.")
    st = stav(s, rok)
    if not st.uzavreny:
        raise ChybaUzavreni(f"Rok {rok} není uzavřený.")
    if st.dalsi == "uzavrene":
        raise ChybaUzavreni(
            f"Rok {rok + 1} je už také uzavřený. Chybu opravte v běžném roce a popište ji "
            "v příloze k závěrce."
        )
    s.get(Obdobi, rok).stav = "otevrene"
    s.flush()
    text = f"Znovu otevřený rok {rok}: {duvod}"
    if st.otevreni is not None:
        denik.storno(
            s, st.otevreni.id, duvod=text, zauctoval=zauctoval, kontrolovat_navaznost=False
        )
    for z in (st.rozvahove, st.vysledkove):
        if z is not None:
            denik.storno(s, z.id, duvod=text, zauctoval=zauctoval, kontrolovat_navaznost=False)
    return stav(s, rok)
