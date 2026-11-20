"""Oznámení vlastníkům o nové výši měsíčních záloh.

Porovná verzi předpisu s tou předchozí po jednotkách a složkách. Změněnou zálohu na služby
lze požadovat nejdřív od prvního dne měsíce po doručení písemného, odůvodněného oznámení
(zákon č. 67/2013 Sb., § 4 odst. 3; Durec s. 27). Oznámení proto musí vlastníkům dojít
nejpozději poslední den měsíce před platností nové verze.
"""

from dataclasses import dataclass
from datetime import date, timedelta

from . import predpisy
from .domena.profil import Profil


class ChybaOznameni(ValueError):
    pass


@dataclass
class ZmenaSlozky:
    kod: str
    nazev: str
    role: str
    puvodne: int | None  # None = složka v předchozí verzi nebyla
    nove: int | None  # None = složka v nové verzi už není


@dataclass
class OznameniJednotky:
    jednotka: str
    slozky: list[ZmenaSlozky]

    @property
    def puvodne(self) -> int:
        return sum(s.puvodne or 0 for s in self.slozky)

    @property
    def nove(self) -> int:
        return sum(s.nove or 0 for s in self.slozky)

    @property
    def zmenena(self) -> bool:
        return any(s.puvodne != s.nove for s in self.slozky)


@dataclass
class Oznameni:
    plati_od: date
    zdroj: str
    predchozi_od: date | None
    jednotky: list[OznameniJednotky]

    @property
    def dorucit_do(self) -> date:
        return self.plati_od - timedelta(days=1)


def oznameni(profil: Profil, nastaveni: predpisy.Nastaveni, plati_od: date) -> Oznameni:
    verze = sorted(nastaveni.verze, key=lambda v: v.plati_od)
    poradi = next((i for i, v in enumerate(verze) if v.plati_od == plati_od), None)
    if poradi is None:
        raise ChybaOznameni(f"Předpis platný od {plati_od:%d. %m. %Y} neexistuje.")
    nova = verze[poradi]
    stara = verze[poradi - 1] if poradi else None

    nove = predpisy.spocitej(profil, nova)
    puvodni = predpisy.spocitej(profil, stara) if stara else {}
    slozky = {s.kod: s for s in nova.slozky}
    if stara:
        for s in stara.slozky:
            slozky.setdefault(s.kod, s)

    jednotky = [
        OznameniJednotky(
            j,
            [
                ZmenaSlozky(
                    s.kod,
                    s.nazev,
                    s.role,
                    puvodni.get(j, {}).get(s.kod) if stara else None,
                    nove[j].get(s.kod),
                )
                for s in slozky.values()
            ],
        )
        for j in nove
    ]
    return Oznameni(nova.plati_od, nova.zdroj, stara.plati_od if stara else None, jednotky)
