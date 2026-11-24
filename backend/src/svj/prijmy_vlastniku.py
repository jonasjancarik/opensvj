"""Příjmy vlastníků ze společných částí: nájemné a pacht, které SVJ vybírá za vlastníky
(NV 366/2013 § 16 odst. 2; příručka, kapitola 4).

Podíl vlastníka vychází z plateb, které SVJ od nájemců v roce skutečně dostalo. Každá
platba se rozdělí podle podílů na společných částech platných v den platby a připadne
tomu, kdo jednotku v ten den vlastnil. Vlastníkům, kteří vedou účetnictví, se do potvrzení
přidá i podíl na nájemném předepsaném v roce. Vypořádání (výplata z banky, převod do
fondu oprav) se vede na účtu příjmů vlastníků po jednotkách.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import denik, lide, podily
from .db import RadekZapisu, Vlastnictvi, Zapis
from .domena import katalog
from .domena.penize import kc, na_text
from .domena.profil import Profil
from .domena.rozdeleni import rozdel

ROLE = "prijmy_vlastniku"
POHLEDAVKY = "pohledavky_najemci"
OPERACE_PREDPISU = "najem-predpis"
OPERACE_UHRADY = "najem-uhrada"
OPERACE_VYPLATY = "prijmy-vlastniku-vyplata"
OPERACE_PREVODU = "prijmy-vlastniku-prevod-do-fo"


class ChybaPrijmu(ValueError):
    pass


@dataclass
class Platba:
    datum: date
    najemce: str
    castka: int
    zapis: str
    popis: str


@dataclass
class Vlastnik:
    """Jedno vlastnictví jednotky a jeho podíl za rok."""

    vlastnictvi: int | None
    jmena: list[str]
    adresa: str
    od: date | None
    do: date | None
    prijato: int = 0  # podíl na platbách, které SVJ v roce dostalo
    predepsano: int = 0  # podíl na nájemném předepsaném v roce


@dataclass
class Jednotka:
    jednotka: str
    podil: str
    vlastnici: list[Vlastnik] = field(default_factory=list)
    prijato: int = 0
    vyplaceno: int = 0
    do_fondu: int = 0
    zbyva: int = 0  # nevypořádáno ke konci roku, i z minulých let


@dataclass
class Prehled:
    rok: int
    platby: list[Platba]
    predepsano: int
    jednotky: list[Jednotka]
    jako_vynos: list[str]  # nájemci, jejichž nájemné SVJ vede jako svůj výnos


def nastaveno(profil: Profil) -> bool:
    return ROLE in profil.role and POHLEDAVKY in profil.role


def _najemci_vlastniku(s: Session, profil: Profil) -> set[str]:
    """Nájemci, jejichž nájemné je předepsané jako příjem vlastníků (ne jako výnos SVJ)."""
    return set(
        s.scalars(
            select(RadekZapisu.protistrana)
            .join(Zapis)
            .where(
                RadekZapisu.ucet == profil.ucet(ROLE),
                RadekZapisu.strana == "d",
                RadekZapisu.protistrana.is_not(None),
                denik.nestornovany(),
                denik.bez_uzaverky(),
            )
        )
    )


def _radky(s: Session, ucet: str, strana: str, *podminky):
    return s.execute(
        select(RadekZapisu, Zapis)
        .join(Zapis)
        .where(
            RadekZapisu.ucet == ucet,
            RadekZapisu.strana == strana,
            denik.nestornovany(),
            denik.bez_uzaverky(),
            *podminky,
        )
        .order_by(Zapis.datum, Zapis.id)
    ).all()


def _vlastnictvi_k(historie: list[Vlastnictvi], jednotka: str, den: date) -> Vlastnictvi | None:
    return next(
        (
            v
            for v in historie
            if v.jednotka == jednotka
            and v.plati_od <= den
            and (v.plati_do is None or den <= v.plati_do)
        ),
        None,
    )


def _rozdel(profil: Profil, castka: int, den: date, sady: podily.Podily) -> dict[str, int]:
    sada = sady.k_datu(den)
    return rozdel(castka, {j: sada.podily[j] for j in profil.jednotky})


def prehled(s: Session, profil: Profil, rok: int, *, do: date | None = None) -> Prehled:
    """Platby od nájemců v roce, podíly jednotek a vlastníků a stav vypořádání.

    `do` omezí stav vypořádání (`zbyva`) na zápisy do toho dne, třeba při převodu."""
    konec = do or date(rok, 12, 31)
    sady = podily.nacti(s, profil)
    historie = lide.vlastnictvi(s)
    pro_vlastniky = _najemci_vlastniku(s, profil)
    jednotky = {j: Jednotka(j, sady.k_datu(konec).texty.get(j, "")) for j in profil.jednotky}
    vlastnici: dict[tuple[str, int | None], Vlastnik] = {}

    def vlastnik(jednotka: str, den: date) -> Vlastnik:
        v = _vlastnictvi_k(historie, jednotka, den)
        klic = (jednotka, v.id if v else None)
        if klic not in vlastnici:
            osoby = [c.osoba for c in v.vlastnici] if v else []
            vlastnici[klic] = Vlastnik(
                v.id if v else None,
                [o.jmeno for o in osoby],
                next((o.adresa for o in osoby if o.adresa), ""),
                v.plati_od if v else None,
                v.plati_do if v else None,
            )
            jednotky[jednotka].vlastnici.append(vlastnici[klic])
        return vlastnici[klic]

    platby: list[Platba] = []
    jako_vynos: set[str] = set()
    kumulativne: dict[str, int] = defaultdict(int)
    for r, z in _radky(
        s, profil.ucet(POHLEDAVKY), "d", Zapis.datum <= konec, Zapis.operace == OPERACE_UHRADY
    ):
        najemce = r.protistrana or ""
        if najemce not in pro_vlastniky:
            if z.rok == rok:
                jako_vynos.add(najemce or "bez určení")
            continue
        dily = _rozdel(profil, r.castka, z.datum, sady)
        for j, c in dily.items():
            kumulativne[j] += c
        if z.rok != rok:
            continue
        platby.append(Platba(z.datum, najemce, r.castka, f"{z.poradove_cislo}/{z.rok}", z.popis))
        for j, c in dily.items():
            jednotky[j].prijato += c
            if c:
                vlastnik(j, z.datum).prijato += c

    predepsano = 0
    for r, z in _radky(
        s, profil.ucet(ROLE), "d", Zapis.rok == rok, RadekZapisu.protistrana.is_not(None)
    ):
        predepsano += r.castka
        for j, c in _rozdel(profil, r.castka, z.datum, sady).items():
            if c:
                vlastnik(j, z.datum).predepsano += c

    # Vypořádání po jednotkách: výplaty, převody do záloh a ruční opravy na účtu 379.
    for r, z in _radky(
        s, profil.ucet(ROLE), "md", Zapis.datum <= konec, RadekZapisu.jednotka.is_not(None)
    ):
        j = jednotky.get(r.jednotka or "")
        if j is None:
            continue
        kumulativne[j.jednotka] -= r.castka
        if z.rok == rok:
            if z.operace == OPERACE_PREVODU:
                j.do_fondu += r.castka
            else:
                j.vyplaceno += r.castka
    # Počáteční stavy a jiné připsání po jednotkách (D s jednotkou).
    for r, _z in _radky(
        s, profil.ucet(ROLE), "d", Zapis.datum <= konec, RadekZapisu.jednotka.is_not(None)
    ):
        if r.jednotka in jednotky:
            kumulativne[r.jednotka] += r.castka
    for j in jednotky.values():
        j.zbyva = kumulativne[j.jednotka]
        j.vlastnici.sort(key=lambda v: v.od or date.min)

    return Prehled(
        rok=rok,
        platby=platby,
        predepsano=predepsano,
        jednotky=list(jednotky.values()),
        jako_vynos=sorted(jako_vynos),
    )


def prevod_do_fondu(
    s: Session,
    profil: Profil,
    *,
    jednotka: str,
    castka: int,
    datum: date,
    zadost: str,
    zauctoval: str,
) -> Zapis:
    """Převede podíl jednotky do jejích záloh na fond oprav, když o to vlastník požádal."""
    if jednotka not in profil.jednotky:
        raise ChybaPrijmu(f"Jednotka {jednotka} v domě není.")
    if castka <= 0:
        raise ChybaPrijmu("Převáděná částka musí být kladná.")
    zadost = " ".join(zadost.split())
    if not zadost:
        raise ChybaPrijmu(
            "Napište, kdy a jak vlastník o převod požádal. Bez jeho souhlasu podíl převést nejde."
        )
    stav = prehled(s, profil, datum.year, do=datum)
    zbyva = next(j.zbyva for j in stav.jednotky if j.jednotka == jednotka)
    if castka > zbyva:
        raise ChybaPrijmu(
            f"Jednotce {jednotka} zbývá k {datum.day}. {datum.month}. {datum.year} vypořádat "
            f"jen {kc(max(zbyva, 0))}."
        )
    op = katalog.nacti()[OPERACE_PREVODU]
    try:
        return denik.zauctuj(
            s,
            profil,
            op,
            {"jednotka": jednotka, "castka": na_text(castka)},
            datum=datum,
            popis=f"Podíl na nájemném jednotky {jednotka} do fondu oprav · {zadost}"[:500],
            doklad=op.doklad,
            zauctoval=zauctoval,
        )
    except denik.ChybaUctovani as e:
        raise ChybaPrijmu(str(e)) from e
