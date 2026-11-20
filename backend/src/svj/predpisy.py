"""Předpisy záloh: výpočet měsíčních částek po jednotkách, zaúčtování měsíce a saldo.

Nastavení předpisu je v `<profil>-predpisy.yaml` ve složce profilů (složky, klíče, sazby,
pevné částky a počty osob, vše s platností od). Výpočet je deterministický: stejné nastavení
dá stejné haléře. Předpis měsíce je jeden zápis v deníku s řádky po jednotkách a složkách;
saldo jednotek se počítá z deníku, takže nevzniká druhá evidence.
"""

from dataclasses import dataclass, field
from datetime import date
from fractions import Fraction
from pathlib import Path

import yaml
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from . import denik, pocatecni
from .db import RadekZapisu, Zapis
from .domena import katalog
from .domena.penize import halire, na_text
from .domena.profil import Profil, vychozi_cesta
from .domena.rozdeleni import rozdel

KLICE = {"plocha", "osoby", "pevna", "podil", "jednotka"}
MESICE = [
    "leden", "únor", "březen", "duben", "květen", "červen",
    "červenec", "srpen", "září", "říjen", "listopad", "prosinec",
]  # fmt: skip


class ChybaPredpisu(ValueError):
    pass


@dataclass(frozen=True)
class Slozka:
    kod: str
    nazev: str
    role: str
    klic: str
    sazba: int | None  # haléře za m², za osobu, nebo měsíčně za dům (podil, jednotka)


@dataclass
class Verze:
    plati_od: date
    zdroj: str
    slozky: list[Slozka]
    pevne: dict[str, dict[str, int]]  # jednotka nebo "vychozi" → kód složky → haléře
    osoby: dict[str, int]  # jednotka nebo "vychozi" → počet osob


@dataclass
class Nastaveni:
    poznamka: str
    splatnost_den: int
    verze: list[Verze] = field(default_factory=list)

    def pro_mesic(self, rok: int, mesic: int) -> Verze | None:
        den = date(rok, mesic, 1)
        platne = [v for v in self.verze if v.plati_od <= den]
        return max(platne, key=lambda v: v.plati_od) if platne else None


def nacti(profil: Profil, cesta: Path | None = None) -> Nastaveni:
    soubor = (cesta or vychozi_cesta()) / f"{profil.id}-predpisy.yaml"
    if not soubor.exists():
        return Nastaveni(poznamka="", splatnost_den=15)
    d = yaml.safe_load(soubor.read_text(encoding="utf-8"))
    n = Nastaveni(poznamka=d.get("poznamka", ""), splatnost_den=int(d.get("splatnost_den", 15)))
    for v in d.get("verze") or []:
        slozky = [
            Slozka(
                kod=s["kod"],
                nazev=s["nazev"],
                role=s["role"],
                klic=s["klic"],
                sazba=halire(str(s["sazba"])) if "sazba" in s else None,
            )
            for s in v["slozky"]
        ]
        verze = Verze(
            plati_od=v["plati_od"],
            zdroj=v.get("zdroj", ""),
            slozky=slozky,
            pevne={
                j: {k: halire(str(c)) for k, c in castky.items()}
                for j, castky in (v.get("pevne") or {}).items()
            },
            osoby={j: int(p) for j, p in (v.get("osoby") or {}).items()},
        )
        zkontroluj(profil, verze)
        n.verze.append(verze)
    return n


def zkontroluj(profil: Profil, v: Verze) -> None:
    if v.plati_od.day != 1:
        raise ChybaPredpisu(f"předpis musí platit od prvního dne měsíce ({v.plati_od})")
    kody = [s.kod for s in v.slozky]
    if len(set(kody)) != len(kody):
        raise ChybaPredpisu("kód složky je v předpisu dvakrát")
    for s in v.slozky:
        if s.klic not in KLICE:
            raise ChybaPredpisu(f"složka {s.kod}: neznámý klíč {s.klic!r}")
        if (s.klic == "pevna") == (s.sazba is not None):
            raise ChybaPredpisu(f"složka {s.kod}: sazbu má mít právě každý klíč kromě 'pevna'")
        profil.ucet(s.role)  # role musí v profilu existovat
    if any(s.klic == "osoby" for s in v.slozky) and "vychozi" not in v.osoby:
        bez = [j for j in profil.jednotky if j not in v.osoby]
        if bez:
            raise ChybaPredpisu(f"jednotky {', '.join(bez)} nemají zadaný počet osob")
    soucet = sum(j.podil for j in profil.udaje_jednotek)
    if soucet != 1:
        raise ChybaPredpisu(f"součet podílů jednotek je {soucet}, ne 1")


def _pevna(v: Verze, jednotka: str, kod: str) -> int:
    for klic in (jednotka, "vychozi"):
        if kod in v.pevne.get(klic, {}):
            return v.pevne[klic][kod]
    raise ChybaPredpisu(f"jednotka {jednotka} nemá zadanou částku složky {kod}")


def osob(v: Verze, jednotka: str) -> int:
    return v.osoby.get(jednotka, v.osoby.get("vychozi", 0))


def _na_koruny(halire: Fraction) -> int:
    """Zaokrouhlí na celé koruny, polovinu nahoru (jako předchozí správce: 90,9 Kč → 91 Kč)."""
    koruny = halire / 100
    return int(koruny + Fraction(1, 2)) * 100 if koruny >= 0 else -_na_koruny(-halire)


def spocitej(profil: Profil, v: Verze) -> dict[str, dict[str, int]]:
    """Měsíční částky: jednotka → kód složky → haléře (celé koruny)."""
    jednotky = profil.udaje_jednotek
    vysledek: dict[str, dict[str, int]] = {j.oznaceni: {} for j in jednotky}
    for s in v.slozky:
        if s.klic == "podil":
            rozdil = rozdel(s.sazba, {j.oznaceni: j.podil for j in jednotky}, krok=100)
        elif s.klic == "jednotka":
            rozdil = rozdel(s.sazba, {j.oznaceni: 1 for j in jednotky}, krok=100)
        else:
            rozdil = {}
            for j in jednotky:
                if s.klic == "plocha":
                    rozdil[j.oznaceni] = _na_koruny(Fraction(s.sazba * j.plocha, 100))
                elif s.klic == "osoby":
                    rozdil[j.oznaceni] = s.sazba * osob(v, j.oznaceni)
                else:
                    rozdil[j.oznaceni] = _pevna(v, j.oznaceni, s.kod)
        for j, castka in rozdil.items():
            vysledek[j][s.kod] = castka
    return vysledek


def mesicni_celkem(profil: Profil, nastaveni: Nastaveni, rok: int, mesic: int) -> dict[str, int]:
    """Měsíční předpis jednotek celkem (prázdné, když pro měsíc předpis není)."""
    v = nastaveni.pro_mesic(rok, mesic)
    if v is None:
        return {}
    return {j: sum(c.values()) for j, c in spocitej(profil, v).items()}


def klic_mesice(rok: int, mesic: int) -> str:
    return f"predpis:{rok}-{mesic:02d}"


def vygeneruj(
    session: Session,
    profil: Profil,
    nastaveni: Nastaveni,
    rok: int,
    mesic: int,
    *,
    zauctoval: str,
    dnes: date | None = None,
) -> Zapis:
    """Zaúčtuje předpis měsíce jedním zápisem. Opakované volání vrátí existující zápis.

    Měsíce jdou po sobě: předpis nejde zaúčtovat dopředu ani přeskočit dřívější měsíc
    téhož roku, pro který předpis platil.
    """
    v = nastaveni.pro_mesic(rok, mesic)
    if v is None:
        raise ChybaPredpisu(f"Pro {MESICE[mesic - 1]} {rok} není zadaný předpis záloh.")
    hotovo = denik.aktivni(session, klic_mesice(rok, mesic))
    if hotovo is not None:
        return hotovo
    if date(rok, mesic, 1) > (dnes or date.today()):
        raise ChybaPredpisu(f"Předpis za {MESICE[mesic - 1]} {rok} zatím nejde zaúčtovat.")
    chybi = dalsi_k_zauctovani(session, nastaveni, rok)
    if chybi is not None and chybi < mesic:
        raise ChybaPredpisu(f"Nejdřív je potřeba zaúčtovat předpis za {MESICE[chybi - 1]} {rok}.")
    role = {s.kod: s.role for s in v.slozky}
    vstupy = [
        {
            "jednotka": jednotka,
            "slozky": [
                {"slozka": kod, "ucet_zavazku": role[kod], "castka": na_text(c)}
                for kod, c in castky.items()
                if c
            ],
        }
        for jednotka, castky in spocitej(profil, v).items()
    ]
    try:
        return denik.zauctuj(
            session,
            profil,
            katalog.nacti()["predpis-mesicni"],
            vstupy,
            datum=date(rok, mesic, 1),
            popis=f"Předpis záloh za {MESICE[mesic - 1]} {rok}",
            doklad=f"PR {rok}-{mesic:02d}",
            zauctoval=zauctoval,
            idempotencni_klic=klic_mesice(rok, mesic),
        )
    except denik.ChybaUctovani as e:
        raise ChybaPredpisu(str(e)) from e


@dataclass
class SaldoJednotky:
    jednotka: str
    pocatek: int  # dluh (+) nebo přeplatek (−) současného vlastníka k 1. 1.
    predepsano: int
    zaplaceno: int

    @property
    def saldo(self) -> int:
        """Kladné = jednotka dluží, záporné = přeplatek."""
        return self.pocatek + self.predepsano - self.zaplaceno


def _radky_vlastniku(rok: int, *sloupce):
    return (
        select(*sloupce)
        .select_from(RadekZapisu)
        .join(Zapis)
        .where(Zapis.rok == rok, RadekZapisu.role.in_(pocatecni.ROLE_VLASTNIKU), denik.platny())
    )


def zustatky_vlastniku(session: Session, rok: int, do: date) -> dict[str, list[int]]:
    """Zůstatky pohledávek za vlastníky po účtech a jednotkách (i dřívějších vlastnících),
    kladné na straně MD. Pro rozvahu, kde se přeplatek vlastníka vykazuje jako závazek."""
    znamenko = func.sum(
        case((RadekZapisu.strana == "md", RadekZapisu.castka), else_=-RadekZapisu.castka)
    )
    radky = session.execute(
        _radky_vlastniku(rok, RadekZapisu.ucet, znamenko)
        .where(Zapis.datum <= do)
        .group_by(RadekZapisu.ucet, RadekZapisu.jednotka, RadekZapisu.protistrana)
    ).all()
    vysledek: dict[str, list[int]] = {}
    for ucet, z in radky:
        vysledek.setdefault(ucet, []).append(int(z))
    return vysledek


def saldo(session: Session, profil: Profil, rok: int) -> list[SaldoJednotky]:
    """Pohledávky za současné vlastníky po jednotkách: počáteční stav, předpisy (MD), platby (D).

    Řádky se jménem dřívějšího vlastníka sem nepatří, ty ukazuje `drivejsi_vlastnici`.
    """
    md = func.sum(case((RadekZapisu.strana == "md", RadekZapisu.castka), else_=0))
    d = func.sum(case((RadekZapisu.strana == "d", RadekZapisu.castka), else_=0))
    otevreni = Zapis.operace == pocatecni.OPERACE
    radky = session.execute(
        _radky_vlastniku(rok, RadekZapisu.jednotka, otevreni, md, d)
        .where(RadekZapisu.protistrana.is_(None))
        .group_by(RadekZapisu.jednotka, otevreni)
    ).all()
    podle: dict[str | None, list[int]] = {}
    for j, je_pocatek, m, p in radky:
        x = podle.setdefault(j, [0, 0, 0])
        if je_pocatek:
            x[0] += int(m) - int(p)
        else:
            x[1] += int(m)
            x[2] += int(p)
    return [SaldoJednotky(j, *podle.get(j, (0, 0, 0))) for j in profil.jednotky]


@dataclass
class DluhDrivejsiho:
    jednotka: str
    vlastnik: str
    popis: str
    castka: int  # kladné = dluží, záporné = přeplatek


def drivejsi_vlastnici(session: Session, rok: int) -> list[DluhDrivejsiho]:
    znamenko = func.sum(
        case((RadekZapisu.strana == "md", RadekZapisu.castka), else_=-RadekZapisu.castka)
    )
    radky = session.execute(
        _radky_vlastniku(
            rok, RadekZapisu.jednotka, RadekZapisu.protistrana, RadekZapisu.popis, znamenko
        )
        .where(RadekZapisu.protistrana.is_not(None))
        .group_by(RadekZapisu.jednotka, RadekZapisu.protistrana, RadekZapisu.popis)
        .order_by(RadekZapisu.jednotka, RadekZapisu.protistrana)
    ).all()
    return [DluhDrivejsiho(j or "", v, p or "", int(c)) for j, v, p, c in radky if c]


def dalsi_k_zauctovani(session: Session, nastaveni: Nastaveni, rok: int) -> int | None:
    """Nejdřívější měsíc roku s platným předpisem, který ještě není zaúčtovaný."""
    hotove = set(zauctovane_mesice(session, rok))
    return next((m for m in range(1, 13) if m not in hotove and nastaveni.pro_mesic(rok, m)), None)


def zauctovane_mesice(session: Session, rok: int) -> dict[int, Zapis]:
    """Měsíc → platný (nestornovaný) zápis předpisu."""
    klice = {klic_mesice(rok, m): m for m in range(1, 13)}
    zapisy = session.scalars(
        select(Zapis).where(Zapis.rok == rok, Zapis.operace == "predpis-mesicni", denik.platny())
    )
    return {klice[k]: z for z in zapisy if (k := denik.zakladni_klic(z.idempotencni_klic)) in klice}
