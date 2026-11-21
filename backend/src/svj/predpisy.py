"""Předpisy záloh: výpočet měsíčních částek po jednotkách, zaúčtování měsíce a saldo.

Nastavení předpisu je v `<profil>-predpisy.yaml` ve složce profilů (složky, klíče, sazby,
pevné částky a počty osob, vše s platností od). Další verze zadává výbor v aplikaci
(tabulka `verze_predpisu`); verze z aplikace se stejným datem nahradí verzi ze souboru.
Výpočet je deterministický: stejné nastavení dá stejné haléře. Předpis měsíce je jeden
zápis v deníku s řádky po jednotkách a složkách; saldo jednotek se počítá z deníku, takže
nevzniká druhá evidence.
"""

from dataclasses import dataclass, field
from datetime import date
from fractions import Fraction
from pathlib import Path

import yaml
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from . import denik, pocatecni
from .db import RadekZapisu, VerzePredpisu, Zapis
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
    v_aplikaci: bool = False  # zadaná v aplikaci, ne v souboru profilu
    upravil: str = ""


@dataclass
class Nastaveni:
    poznamka: str
    splatnost_den: int
    verze: list[Verze] = field(default_factory=list)

    def pro_mesic(self, rok: int, mesic: int) -> Verze | None:
        den = date(rok, mesic, 1)
        platne = [v for v in self.verze if v.plati_od <= den]
        return max(platne, key=lambda v: v.plati_od) if platne else None


def nacti(profil: Profil, session: Session | None = None, cesta: Path | None = None) -> Nastaveni:
    """Nastavení předpisu ze souboru profilu; se sezením i s verzemi zadanými v aplikaci."""
    soubor = (cesta or vychozi_cesta()) / f"{profil.id}-predpisy.yaml"
    d = yaml.safe_load(soubor.read_text(encoding="utf-8")) if soubor.exists() else {}
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
    if session is not None:
        z_aplikace = {
            v.plati_od: v for v in map(_z_databaze, session.scalars(select(VerzePredpisu)))
        }
        n.verze = [v for v in n.verze if v.plati_od not in z_aplikace] + list(z_aplikace.values())
    n.verze.sort(key=lambda v: v.plati_od)
    return n


def nacti_s(profil: Profil, tovarna) -> Nastaveni:
    """Nastavení předpisu včetně verzí z aplikace; `tovarna` vrací sessionmaker."""
    with tovarna()() as s:
        return nacti(profil, s)


def _z_databaze(r: VerzePredpisu) -> Verze:
    return Verze(
        plati_od=r.plati_od,
        zdroj=r.zdroj,
        slozky=[Slozka(**x) for x in r.slozky],
        pevne={j: {k: int(c) for k, c in castky.items()} for j, castky in r.pevne.items()},
        osoby={j: int(p) for j, p in r.osoby.items()},
        v_aplikaci=True,
        upravil=r.upravil,
    )


def prvni_mesic_ke_zmene(session: Session) -> date:
    """Od kdy jde předpis měnit: první měsíc po posledním zaúčtovaném předpisu.

    Zaúčtované měsíce se zpětně nepřepočítávají; změna by rozbila jejich vazbu na deník.
    """
    posledni = session.scalar(
        select(func.max(Zapis.datum)).where(Zapis.operace == "predpis-mesicni", denik.platny())
    )
    if posledni is None:
        return date(1900, 1, 1)
    return date(posledni.year + posledni.month // 12, posledni.month % 12 + 1, 1)


def uloz_verzi(session: Session, profil: Profil, v: Verze, kdo: str, puvodni: date | None) -> None:
    """Uloží verzi zadanou v aplikaci. `puvodni` je datum upravované verze (None = nová)."""
    od = prvni_mesic_ke_zmene(session)
    for datum in {v.plati_od, puvodni} - {None}:
        if datum < od:
            raise ChybaPredpisu(
                f"Předpis od {datum.day}. {datum.month}. {datum.year} už jde do zaúčtovaných "
                f"měsíců. Změna může platit nejdřív od {od.day}. {od.month}. {od.year}."
            )
    zkontroluj(profil, v)
    spocitej(profil, v)  # ověří, že u pevných částek nic nechybí
    if puvodni is not None and puvodni != v.plati_od:
        stara = session.get(VerzePredpisu, puvodni)
        if stara is None:
            raise ChybaPredpisu("Tato verze předpisu v aplikaci není. Načtěte stránku znovu.")
        session.delete(stara)
        session.flush()
    elif puvodni is None and session.get(VerzePredpisu, v.plati_od) is not None:
        raise ChybaPredpisu(
            f"Předpis od {v.plati_od.day}. {v.plati_od.month}. {v.plati_od.year} už v aplikaci "
            "je. Upravte ten."
        )
    r = session.get(VerzePredpisu, v.plati_od) or VerzePredpisu(plati_od=v.plati_od)
    r.zdroj = v.zdroj.strip()[:200]
    r.slozky = [
        {"kod": x.kod, "nazev": x.nazev, "role": x.role, "klic": x.klic, "sazba": x.sazba}
        for x in v.slozky
    ]
    r.pevne = v.pevne
    r.osoby = v.osoby
    r.upravil = kdo
    session.add(r)
    session.flush()


def smaz_verzi(session: Session, plati_od: date) -> None:
    r = session.get(VerzePredpisu, plati_od)
    if r is None:
        raise ChybaPredpisu("Smazat jde jen předpis zadaný v aplikaci.")
    if plati_od < prvni_mesic_ke_zmene(session):
        raise ChybaPredpisu("Předpis už jde do zaúčtovaných měsíců, smazat ho nejde.")
    session.delete(r)
    session.flush()


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


# Operace z katalogu, kterou se dluh při převodu jednotky přesouvá na převodce (viz prevody.py).
OPERACE_PREVODU = "dluh-zustava-prevodci"


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
    # Dluh přesunutý na převodce snižuje to, co má platit současný vlastník; platba to není.
    prevod = Zapis.operace == OPERACE_PREVODU
    radky = session.execute(
        _radky_vlastniku(rok, RadekZapisu.jednotka, otevreni, prevod, md, d)
        .where(RadekZapisu.protistrana.is_(None))
        .group_by(RadekZapisu.jednotka, otevreni, prevod)
    ).all()
    podle: dict[str | None, list[int]] = {}
    for j, je_pocatek, je_prevod, m, p in radky:
        x = podle.setdefault(j, [0, 0, 0])
        if je_pocatek:
            x[0] += int(m) - int(p)
        elif je_prevod:
            x[1] += int(m) - int(p)
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
        .order_by(RadekZapisu.jednotka, RadekZapisu.protistrana, func.min(RadekZapisu.id))
    ).all()
    # Jeden řádek za dřívějšího vlastníka jednotky: dluhy i jeho pozdější platby dohromady.
    podle: dict[tuple[str, str], tuple[list[str], int]] = {}
    for j, v, p, c in radky:
        popisy, castka = podle.get((j or "", v), ([], 0))
        if p and c and p not in popisy:
            popisy.append(p)
        podle[(j or "", v)] = (popisy, castka + int(c))
    return [
        DluhDrivejsiho(j, v, ", ".join(popisy), c) for (j, v), (popisy, c) in podle.items() if c
    ]


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
