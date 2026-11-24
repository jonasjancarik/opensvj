"""Oznámení vlastníkům o nové výši měsíčních záloh.

Porovná verzi předpisu s tou předchozí po jednotkách a složkách. Změněnou zálohu na služby
lze požadovat nejdřív od prvního dne měsíce po doručení písemného, odůvodněného oznámení
(zákon č. 67/2013 Sb., § 4 odst. 3; Durec s. 27). Oznámení proto musí vlastníkům dojít
nejpozději poslední den měsíce před platností nové verze.
"""

from dataclasses import dataclass
from datetime import date, timedelta

from . import podily, predpisy
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
    # Změna podílů na společných částech, se kterou se od `plati_od` počítá (jinak None).
    zmena_podilu: podily.Zmena | None = None

    @property
    def dorucit_do(self) -> date:
        return self.plati_od - timedelta(days=1)


def _mesic_pred(d: date) -> tuple[int, int]:
    return (d.year, d.month - 1) if d.month > 1 else (d.year - 1, 12)


def oznameni(profil: Profil, nastaveni: predpisy.Nastaveni, plati_od: date) -> Oznameni:
    """Porovná předpis od `plati_od` s předpisem v předchozím měsíci.

    Předpis se mění s novou verzí i se změnou podílů, když má verze složku podle podílů.
    """
    zmeny = nastaveni.zmeny_predpisu()
    if plati_od not in zmeny:
        raise ChybaOznameni(f"Předpis platný od {plati_od:%d. %m. %Y} neexistuje.")
    poradi = zmeny.index(plati_od)
    nova = nastaveni.pro_mesic(plati_od.year, plati_od.month)
    assert nova is not None
    rok, mesic = _mesic_pred(plati_od)
    stara = nastaveni.pro_mesic(rok, mesic) if poradi else None

    nove = predpisy.castky_mesice(profil, nastaveni, plati_od.year, plati_od.month)
    puvodni = predpisy.castky_mesice(profil, nastaveni, rok, mesic) if stara else {}
    slozky = {s.kod: s for s in nastaveni.slozky_mesice(plati_od.year, plati_od.month)}
    if stara:
        for s in nastaveni.slozky_mesice(rok, mesic):
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
    zmeny_podilu = nastaveni.podily.zmeny if nastaveni.podily else []
    zmena_podilu = next((z for z in zmeny_podilu if z.od_mesice == plati_od), None)
    zdroje = [nova.zdroj] if nova.plati_od == plati_od and nova.zdroj else []
    if zmena_podilu is not None:
        zdroje.append(zmena_podilu.zdroj)
    return Oznameni(
        plati_od,
        "; ".join(zdroje),
        zmeny[poradi - 1] if poradi else None,
        jednotky,
        zmena_podilu,
    )
