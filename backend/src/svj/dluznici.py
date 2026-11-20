"""Dlužníci: co který vlastník nezaplatil a od kdy.

Platby se přiřazují k nejstarším dluhům (FIFO): nejdřív zůstatky z minulých let, potom
měsíční předpisy a další pohledávky podle splatnosti. Součet nezaplacených položek minus
přeplatek je vždy rovný saldu jednotky z `predpisy.saldo`.
"""

import calendar
from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy.orm import Session

from . import pocatecni, predpisy, vyuctovani_spravy
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

    def urok(self, dnes: date) -> int | None:
        """Zákonný úrok z prodlení z dosud nezaplacené části k `dnes` (None = neumíme spočítat,
        např. u dluhu z minulých let bez známé splatnosti)."""
        if self.splatnost is None:
            return None
        return urok_z_prodleni.urok(self.zbyva, self.splatnost, dnes)

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
        return any(p.splatnost is None for p in self.polozky)

    @property
    def urok(self) -> int:
        """Součet úroků z prodlení, které umíme spočítat."""
        return sum(p.urok(self.dnes) or 0 for p in self.polozky)

    @property
    def urok_neuplny(self) -> bool:
        """Některá položka po splatnosti nemá spočitatelný úrok."""
        return any(p.po_splatnosti(self.dnes) and p.urok(self.dnes) is None for p in self.polozky)

    @property
    def saldo(self) -> int:
        return sum(p.zbyva for p in self.polozky) - self.preplatek


def splatnost_mesice(rok: int, mesic: int, den: int) -> date:
    return date(rok, mesic, min(den, calendar.monthrange(rok, mesic)[1]))


def prehled(
    session: Session,
    profil: Profil,
    nastaveni: predpisy.Nastaveni,
    rok: int,
    dnes: date | None = None,
) -> list[DluhJednotky]:
    dnes = dnes or date.today()
    radky = session.execute(
        predpisy._radky_vlastniku(
            rok,
            RadekZapisu.jednotka,
            RadekZapisu.role,
            RadekZapisu.popis,
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

    # Pro každou jednotku: dluhy (klíč → položka) a celkem zaplaceno nebo přeplaceno.
    dluhy: dict[str, dict[tuple, Polozka]] = {j: {} for j in profil.jednotky}
    kredit: dict[str, int] = dict.fromkeys(profil.jednotky, 0)
    for jednotka, role, popis_radku, strana, castka, zapis_id, operace, datum, popis in radky:
        if jednotka not in dluhy:
            continue
        znamenko = 1 if strana == "md" else -1
        if operace == pocatecni.OPERACE:
            klic = ("pocatek", popis_radku or POPIS_ROLE.get(role, role))
            poradi = (STARI.get(role, 9), klic[1])
            p = dluhy[jednotka].setdefault(
                klic, Polozka(klic[1], None, 0, poradi=poradi, role=role)
            )
            p.castka += znamenko * castka
        elif strana == "d":
            kredit[jednotka] += castka
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
            p = dluhy[jednotka].setdefault(
                ("zapis", zapis_id, role),
                Polozka(text, splatnost, 0, role=role, vznik=datum, mesic=mesic),
            )
            p.castka += castka

    vysledek = []
    for jednotka in profil.jednotky:
        polozky = []
        zbyva_kreditu = kredit[jednotka]
        for p in dluhy[jednotka].values():
            if p.castka < 0:  # přeplatek z minulých let se chová jako platba
                zbyva_kreditu -= p.castka
            elif p.castka > 0:
                polozky.append(p)
        polozky.sort(key=lambda p: (p.splatnost is not None, p.splatnost or date.min, p.poradi))
        nezaplacene = []
        for p in polozky:
            uhrazeno = min(p.castka, zbyva_kreditu)
            zbyva_kreditu -= uhrazeno
            p.zbyva = p.castka - uhrazeno
            if p.zbyva:
                nezaplacene.append(p)
        vysledek.append(DluhJednotky(jednotka, nezaplacene, zbyva_kreditu, dnes))
    return vysledek
