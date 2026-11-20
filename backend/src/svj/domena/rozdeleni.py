"""Rozdělení částky podle vah metodou největšího zbytku.

Používá se pro předpisy podle podílů na společných částech, rovným dílem na jednotku
i pro vyúčtování. Výsledek je deterministický: při shodě zbytků rozhoduje pořadí klíčů.
"""

from collections.abc import Mapping
from fractions import Fraction


def zkontroluj_podily(podily: Mapping[str, Fraction]) -> None:
    """Podíly všech jednotek musí dát přesně 1."""
    soucet = sum(podily.values(), Fraction(0))
    if soucet != 1:
        raise ValueError(f"součet podílů je {soucet}, ne 1")
    for k, p in podily.items():
        if p <= 0:
            raise ValueError(f"podíl jednotky {k} musí být kladný, je {p}")


def rozdel[K](celkem: int, vahy: Mapping[K, Fraction | int], krok: int = 1) -> dict[K, int]:
    """Rozdělí `celkem` haléřů podle `vah` na násobky `krok` (100 = celé koruny).

    Každý díl je zaokrouhlen dolů na `krok`, zbylé kroky dostanou díly s největším
    zbytkem. Součet výsledku je vždy přesně `celkem`.
    """
    if krok <= 0:
        raise ValueError("krok musí být kladný")
    if celkem % krok:
        raise ValueError(f"částku {celkem} nelze rozdělit na násobky {krok} haléřů")
    if not vahy:
        raise ValueError("chybí váhy")
    vahy_f = {k: Fraction(v) for k, v in vahy.items()}
    if any(v < 0 for v in vahy_f.values()):
        raise ValueError("váhy nesmějí být záporné")
    soucet = sum(vahy_f.values(), Fraction(0))
    if soucet == 0:
        raise ValueError("součet vah je nula")

    znamenko = -1 if celkem < 0 else 1
    kroku = abs(celkem) // krok
    presne = {k: kroku * v / soucet for k, v in vahy_f.items()}
    zaklad = {k: int(p) for k, p in presne.items()}  # Fraction >= 0, int() zaokrouhlí dolů
    zbyva = kroku - sum(zaklad.values())
    poradi = {k: i for i, k in enumerate(vahy_f)}
    podle_zbytku = sorted(presne, key=lambda k: (-(presne[k] - zaklad[k]), poradi[k]))
    for k in podle_zbytku[:zbyva]:
        zaklad[k] += 1
    return {k: znamenko * n * krok for k, n in zaklad.items()}
