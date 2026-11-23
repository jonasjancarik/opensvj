"""Dlužníci: co který vlastník nezaplatil a od kdy.

Platby se přiřazují k nejstarším dluhům (FIFO): nejdřív zůstatky z minulých let, potom
měsíční předpisy a další pohledávky podle splatnosti. Součet nezaplacených položek minus
přeplatek je vždy rovný saldu jednotky z `predpisy.saldo`.
"""

import calendar
from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import denik, pocatecni, predpisy, vyuctovani_spravy
from .db import RadekZapisu, Zapis
from .domena import urok as urok_z_prodleni
from .domena.profil import Profil

POPIS_ROLE = {
    "pohledavky_vlastnici": "Nezaplacené zálohy z minulých let",
    "pohledavky_vyuctovani": "Nedoplatek z vyúčtování",
    "pohledavky_vyuctovani_minule": "Nedoplatek z vyúčtování dřívějších let",
}
# Pořadí dluhů z minulých let, od nejstaršího.
STARI = {"pohledavky_vyuctovani_minule": 0, "pohledavky_vlastnici": 1, "pohledavky_vyuctovani": 2}


@dataclass
class Polozka:
    popis: str
    splatnost: date | None  # None = z minulých let, splatné už před začátkem roku
    castka: int
    zbyva: int = 0
    poradi: tuple = field(default=(), repr=False, compare=False)
    role: str = "pohledavky_vlastnici"
    vznik: date | None = None  # datum zápisu, ze kterého dluh vznikl
    mesic: date | None = None  # u měsíčního předpisu první den měsíce

    def po_splatnosti(self, dnes: date) -> bool:
        return self.splatnost is None or self.splatnost < dnes

    def urok(self, dnes: date, od: date | None = None) -> int | None:
        """Zákonný úrok z prodlení z dosud nezaplacené části k `dnes` (None = neumíme spočítat,
        např. u dluhu z minulých let bez známé splatnosti). S `od` jen za dobu po `od`,
        protože úrok do toho dne už SVJ předepsalo."""
        if self.splatnost is None:
            return None
        return urok_z_prodleni.urok(self.zbyva, self.splatnost, dnes, od)

    def sazba(self) -> int | None:
        if self.splatnost is None:
            return None
        return urok_z_prodleni.sazba(self.splatnost + timedelta(days=1))


@dataclass
class DluhJednotky:
    jednotka: str
    polozky: list[Polozka] = field(default_factory=list)  # jen nezaplacené, od nejstarší
    preplatek: int = 0
    dnes: date = field(default_factory=date.today)
    urok_do: date | None = None  # do kdy už SVJ úrok z prodlení předepsalo
    sankce: int = 0  # předepsaný úrok z prodlení a pokuty, které zbývá zaplatit

    @property
    def po_splatnosti(self) -> int:
        return sum(p.zbyva for p in self.polozky if p.po_splatnosti(self.dnes))

    @property
    def nesplatne(self) -> int:
        return sum(p.zbyva for p in self.polozky if not p.po_splatnosti(self.dnes))

    @property
    def od(self) -> date | None:
        """Splatnost nejstarší nezaplacené položky po splatnosti (None i u dluhu z minulých let
        – ten poznáte podle `z_minulych_let`)."""
        prvni = next((p for p in self.polozky if p.po_splatnosti(self.dnes)), None)
        return prvni.splatnost if prvni else None

    @property
    def z_minulych_let(self) -> bool:
        return any(p.splatnost is None or p.vznik is None for p in self.polozky)

    @property
    def urok(self) -> int:
        """Součet úroků z prodlení, které umíme spočítat."""
        return sum(p.urok(self.dnes, self.urok_do) or 0 for p in self.polozky)

    @property
    def urok_neuplny(self) -> bool:
        """Některá položka po splatnosti nemá spočitatelný úrok."""
        return any(
            p.po_splatnosti(self.dnes) and p.urok(self.dnes, self.urok_do) is None
            for p in self.polozky
        )

    @property
    def saldo(self) -> int:
        return sum(p.zbyva for p in self.polozky) - self.preplatek


def splatnost_mesice(rok: int, mesic: int, den: int) -> date:
    return date(rok, mesic, min(den, calendar.monthrange(rok, mesic)[1]))


def _rozpis(
    session: Session,
    profil: Profil,
    nastaveni: predpisy.Nastaveni,
    rok: int,
    podle_uctu: bool,
) -> tuple[dict, dict]:
    """Dluhy a nevyčerpané platby po jednotkách (nebo po jednotkách a účtech).

    Vrací (skupina → klíč → položka, skupina → kredit). Skupina je jednotka, nebo
    dvojice (jednotka, role), když se platby započítávají jen v rámci účtu.
    """
    radky = session.execute(
        predpisy._radky_vlastniku(
            rok,
            RadekZapisu.jednotka,
            RadekZapisu.role,
            RadekZapisu.popis,
            RadekZapisu.splatnost,
            RadekZapisu.strana,
            RadekZapisu.castka,
            Zapis.id,
            Zapis.operace,
            Zapis.datum,
            Zapis.popis,
        )
        .where(RadekZapisu.protistrana.is_(None))
        .order_by(Zapis.datum, Zapis.id)
    ).all()

    dluhy: dict = {}
    kredit: dict = {}
    for (
        jednotka,
        role,
        popis_radku,
        splatnost_radku,
        strana,
        castka,
        zapis_id,
        operace,
        datum,
        popis,
    ) in radky:
        if jednotka not in profil.jednotky:
            continue
        skupina = (jednotka, role) if podle_uctu else jednotka
        dluhy.setdefault(skupina, {})
        kredit.setdefault(skupina, 0)
        znamenko = 1 if strana == "md" else -1
        if operace == pocatecni.OPERACE:
            # Počáteční stav převzatý z minulého roku v aplikaci nese splatnost položky;
            # u zůstatků z dřívějšího účetnictví ji neznáme.
            text = popis_radku or POPIS_ROLE.get(role, role)
            klic = ("pocatek", role, text, splatnost_radku)
            poradi = (STARI.get(role, 9), text)
            p = dluhy[skupina].setdefault(
                klic, Polozka(text, splatnost_radku, 0, poradi=poradi, role=role)
            )
            p.castka += znamenko * castka
        elif strana == "d":
            kredit[skupina] += castka
        else:
            mesic = None
            if operace == "predpis-mesicni":
                splatnost = splatnost_mesice(datum.year, datum.month, nastaveni.splatnost_den)
                text = f"Zálohy za {predpisy.MESICE[datum.month - 1]} {datum.year}"
                mesic = datum.replace(day=1)
            elif operace in (vyuctovani_spravy.OPERACE, "vyuctovani-sluzeb"):
                splatnost, text = vyuctovani_spravy.splatnost(datum.year), popis
            else:
                splatnost, text = datum, popis
            p = dluhy[skupina].setdefault(
                ("zapis", zapis_id, role),
                Polozka(text, splatnost, 0, role=role, vznik=datum, mesic=mesic),
            )
            p.castka += castka

    for skupina, polozky in dluhy.items():
        zbyva_kreditu = kredit[skupina]
        kladne = []
        for p in polozky.values():
            if p.castka < 0:  # přeplatek z minulých let se chová jako platba
                zbyva_kreditu -= p.castka
            elif p.castka > 0:
                kladne.append(p)
        kladne.sort(key=lambda p: (p.splatnost is not None, p.splatnost or date.min, p.poradi))
        for p in kladne:
            uhrazeno = min(p.castka, zbyva_kreditu)
            zbyva_kreditu -= uhrazeno
            p.zbyva = p.castka - uhrazeno
        dluhy[skupina] = {k: p for k, p in polozky.items() if p.castka > 0}
        kredit[skupina] = zbyva_kreditu
    return dluhy, kredit


OPERACE_UROKU = "urok-z-prodleni"
ROLE_SANKCI = "pohledavky_vlastnici_sankce"


def urok_predepsan_do(session: Session) -> dict[str, date]:
    """Po jednotkách datum posledního předpisu úroku z prodlení (přes všechny roky)."""
    radky = session.execute(
        select(RadekZapisu.jednotka, func.max(Zapis.datum))
        .join(Zapis)
        .where(
            Zapis.operace == OPERACE_UROKU,
            RadekZapisu.role == ROLE_SANKCI,
            RadekZapisu.jednotka.is_not(None),
            denik.nestornovany(),
        )
        .group_by(RadekZapisu.jednotka)
    ).all()
    return {j: d for j, d in radky}


def nezaplacene_sankce(session: Session, rok: int) -> dict[str, int]:
    """Po jednotkách zůstatek předepsaných sankcí (úrok z prodlení, pokuty) v roce."""
    radky = session.execute(
        select(RadekZapisu.jednotka, RadekZapisu.strana, func.sum(RadekZapisu.castka))
        .join(Zapis)
        .where(
            Zapis.rok == rok,
            RadekZapisu.role == ROLE_SANKCI,
            RadekZapisu.jednotka.is_not(None),
            denik.platny(),
        )
        .group_by(RadekZapisu.jednotka, RadekZapisu.strana)
    ).all()
    vysledek: dict[str, int] = {}
    for jednotka, strana, castka in radky:
        vysledek[jednotka] = vysledek.get(jednotka, 0) + (castka if strana == "md" else -castka)
    return {j: c for j, c in vysledek.items() if c}


def prehled(
    session: Session,
    profil: Profil,
    nastaveni: predpisy.Nastaveni,
    rok: int,
    dnes: date | None = None,
) -> list[DluhJednotky]:
    dnes = dnes or date.today()
    dluhy, kredit = _rozpis(session, profil, nastaveni, rok, podle_uctu=False)
    urok_do = urok_predepsan_do(session)
    sankce = nezaplacene_sankce(session, rok)
    vysledek = []
    for jednotka in profil.jednotky:
        polozky = sorted(
            dluhy.get(jednotka, {}).values(),
            key=lambda p: (p.splatnost is not None, p.splatnost or date.min, p.poradi),
        )
        nezaplacene = [p for p in polozky if p.zbyva]
        vysledek.append(
            DluhJednotky(
                jednotka,
                nezaplacene,
                kredit.get(jednotka, 0),
                dnes,
                urok_do.get(jednotka),
                sankce.get(jednotka, 0),
            )
        )
    return vysledek


def k_prevodu(
    session: Session, profil: Profil, nastaveni: predpisy.Nastaveni, rok: int
) -> list[tuple[str, str, list[Polozka], int]]:
    """Co se k 31. 12. převádí do dalšího roku: po jednotkách a účtech nezaplacené položky
    a nevyčerpaný přeplatek. Platby se tu započítávají jen v rámci účtu, aby počáteční stav
    každého účtu navazoval na jeho konečný zůstatek."""
    dluhy, kredit = _rozpis(session, profil, nastaveni, rok, podle_uctu=True)
    vysledek = []
    for (jednotka, role), polozky in sorted(dluhy.items()):
        nezaplacene = sorted(
            (p for p in polozky.values() if p.zbyva),
            key=lambda p: (p.splatnost is not None, p.splatnost or date.min, p.poradi),
        )
        vysledek.append((jednotka, role, nezaplacene, kredit[(jednotka, role)]))
    return vysledek
