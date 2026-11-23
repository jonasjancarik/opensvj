"""Zákonný úrok z prodlení podle nařízení vlády č. 351/2013 Sb.

Roční sazba = 2T repo sazba ČNB platná v první den kalendářního pololetí, v němž prodlení
začalo, zvýšená o 8 procentních bodů (§ 2). Sazba se pak po celou dobu prodlení nemění.
Prodlení začíná dnem po splatnosti. Pravidlo platí pro prodlení od 1. 1. 2014; dřívější
prodlení se řídí starším předpisem a aplikace je nepočítá.

Repo sazby jsou převzaté z ČNB, „Jak se vyvíjela dvoutýdenní repo sazba ČNB?“
(https://www.cnb.cz/cs/casto-kladene-dotazy/Jak-se-vyvijela-dvoutydenni-repo-sazba-CNB/),
ověřeno k datu OVERENO_K. Pro pololetí začínající po tomto datu sazbu neznáme, dokud se
tabulka nedoplní.
"""

from datetime import date, timedelta

ZDROJ = "https://www.cnb.cz/cs/casto-kladene-dotazy/Jak-se-vyvijela-dvoutydenni-repo-sazba-CNB/"
OVERENO_K = date(2026, 11, 20)
PRIRAZKA = 800  # 8 procentních bodů, v setinách procenta
OD = date(2014, 1, 1)  # účinnost § 2 v tomto znění

# (platná od, sazba v setinách procenta)
REPO_SAZBY: list[tuple[date, int]] = [
    (date(2012, 11, 2), 5),
    (date(2017, 8, 4), 25),
    (date(2017, 11, 3), 50),
    (date(2018, 2, 2), 75),
    (date(2018, 6, 28), 100),
    (date(2018, 8, 3), 125),
    (date(2018, 9, 27), 150),
    (date(2018, 11, 2), 175),
    (date(2019, 5, 3), 200),
    (date(2020, 2, 7), 225),
    (date(2020, 3, 17), 175),
    (date(2020, 3, 27), 100),
    (date(2020, 5, 11), 25),
    (date(2021, 6, 24), 50),
    (date(2021, 8, 6), 75),
    (date(2021, 10, 1), 150),
    (date(2021, 11, 5), 275),
    (date(2021, 12, 23), 375),
    (date(2022, 2, 4), 450),
    (date(2022, 4, 1), 500),
    (date(2022, 5, 6), 575),
    (date(2022, 6, 23), 700),
    (date(2023, 12, 22), 675),
    (date(2024, 2, 9), 625),
    (date(2024, 3, 21), 575),
    (date(2024, 5, 3), 525),
    (date(2024, 6, 28), 475),
    (date(2024, 8, 2), 450),
    (date(2024, 9, 26), 425),
    (date(2024, 11, 8), 400),
    (date(2025, 2, 7), 375),
    (date(2025, 5, 9), 350),
    (date(2026, 6, 19), 375),
    (date(2026, 11, 6), 400),
]


def zacatek_pololeti(d: date) -> date:
    return date(d.year, 1 if d.month <= 6 else 7, 1)


def repo_sazba(den: date) -> int:
    return next(s for od, s in reversed(REPO_SAZBY) if od <= den)


def sazba(prvni_den_prodleni: date) -> int | None:
    """Roční sazba úroku z prodlení v setinách procenta (1175 = 11,75 %), nebo None, když ji
    aplikace neumí určit (prodlení před rokem 2014 nebo pololetí po poslední aktualizaci)."""
    pololeti = zacatek_pololeti(prvni_den_prodleni)
    if prvni_den_prodleni < OD or pololeti > OVERENO_K:
        return None
    return repo_sazba(pololeti) + PRIRAZKA


def urok(castka: int, splatnost: date, do: date, od: date | None = None) -> int | None:
    """Úrok z prodlení v haléřích z dlužné částky od dne po splatnosti do `do` včetně.

    S `od` se počítá až ode dne po `od` (úrok do toho dne už SVJ předepsalo); sazba se
    řídí pořád začátkem prodlení. 0 = není v prodlení; None = sazbu neznáme. Zaokrouhluje
    se na celé haléře.
    """
    dni = (do - max(splatnost, od or splatnost)).days
    if dni <= 0 or castka <= 0:
        return 0
    s = sazba(splatnost + timedelta(days=1))
    if s is None:
        return None
    citatel = castka * s * dni
    jmenovatel = 10_000 * 365
    return (2 * citatel + jmenovatel) // (2 * jmenovatel)
