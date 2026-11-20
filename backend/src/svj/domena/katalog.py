"""Katalog účetních operací.

Předkontace žijí jen v YAML souborech ve složce `catalogue/`. Tento modul je načte,
zkontroluje a z operace a vstupů sestaví řádky zápisu. Čísla účtů tu nejsou: řádek nese
roli účtu a teprve profil SVJ (`profil.py`) z role udělá konkrétní účet.
"""

import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml

from .penize import halire

Strana = Literal["md", "d"]
STAVY = {"praxe", "navrh", "overit"}
_PROMENNA = re.compile(r"\{([a-z_][a-z0-9_]*)\}")


@dataclass(frozen=True)
class Radek:
    strana: Strana
    role: str
    castka: int  # haléře, vždy kladné
    dimenze: dict[str, str] = field(default_factory=dict)

    def klic(self) -> tuple[str, str, int]:
        return (self.strana, self.role, self.castka)


@dataclass
class Operace:
    id: str
    nazev: str
    stav: str
    doklad: str
    zapisy: list[dict[str, Any]]
    zdroje: list[dict[str, Any]]
    priklady: list[dict[str, Any]]
    zpusob: str = "sablona"
    soubor: str = ""
    data: dict[str, Any] = field(default_factory=dict)


class ChybaKatalogu(ValueError):
    pass


def vychozi_cesta() -> Path:
    return Path(__file__).resolve().parents[4] / "catalogue"


def nacti(cesta: Path | None = None) -> dict[str, Operace]:
    cesta = cesta or vychozi_cesta()
    operace: dict[str, Operace] = {}
    for soubor in sorted(cesta.glob("*.yaml")):
        for d in yaml.safe_load(soubor.read_text(encoding="utf-8")) or []:
            op = Operace(
                id=d["id"],
                nazev=d["nazev"],
                stav=d["stav"],
                doklad=d["doklad"],
                zapisy=d.get("zapisy") or [],
                zdroje=d.get("zdroje") or [],
                priklady=d.get("priklady") or [],
                zpusob=d.get("zpusob", "sablona"),
                soubor=soubor.name,
                data=d,
            )
            if op.id in operace:
                raise ChybaKatalogu(f"operace {op.id} je v katalogu dvakrát")
            operace[op.id] = op
    return operace


def _dosad(sablona: Any, kontext: dict[str, Any]) -> str:
    text = str(sablona)

    def nahrad(m: re.Match[str]) -> str:
        nazev = m.group(1)
        if nazev not in kontext:
            raise ChybaKatalogu(f"chybí vstup {nazev!r} pro šablonu {text!r}")
        return str(kontext[nazev])

    return _PROMENNA.sub(nahrad, text)


def sestav(op: Operace, vstupy: dict[str, Any], krok: str | None = None) -> list[Radek]:
    """Z operace a vstupů sestaví řádky zápisu (MD i D zvlášť).

    Záporná částka prohodí strany. Nulové řádky se vynechají.
    """
    if op.zpusob != "sablona":
        raise ChybaKatalogu(f"operace {op.id} se neprovádí šablonou, ale kódem")
    radky: list[Radek] = []
    for z in op.zapisy:
        if krok is not None and z.get("krok") != krok:
            continue
        if z.get("pro_kazde"):
            polozky = vstupy.get(z["pro_kazde"])
            if not isinstance(polozky, list):
                raise ChybaKatalogu(f"vstup {z['pro_kazde']!r} musí být seznam")
            kontexty = [{**vstupy, **p} for p in polozky]
        else:
            kontexty = [vstupy]
        for k in kontexty:
            castka = halire(_dosad(z["castka"], k))
            if castka == 0:
                continue
            md, d = _dosad(z["md"], k), _dosad(z["d"], k)
            if castka < 0:
                md, d, castka = d, md, -castka
            dimenze = {n: _dosad(v, k) for n, v in (z.get("dimenze") or {}).items()}
            radky.append(Radek("md", md, castka, dimenze))
            radky.append(Radek("d", d, castka, dimenze))
    zkontroluj_vyrovnanost(radky)
    return radky


def zkontroluj_vyrovnanost(radky: list[Radek]) -> None:
    md = sum(r.castka for r in radky if r.strana == "md")
    d = sum(r.castka for r in radky if r.strana == "d")
    if md != d:
        raise ChybaKatalogu(f"zápis není vyrovnaný: MD {md}, D {d}")


def ocekavane_radky(priklad: dict[str, Any]) -> list[Radek]:
    return [
        Radek(strana, role, halire(castka), dict(dimenze or {}))
        for strana, role, castka, dimenze in priklad["ocekavane"]
    ]


def porovnej(skutecne: list[Radek], ocekavane: list[Radek]) -> list[str]:
    """Vrátí popis rozdílů. Dimenze v očekávaném řádku musí být podmnožinou skutečných."""
    chyby: list[str] = []
    if Counter(r.klic() for r in skutecne) != Counter(r.klic() for r in ocekavane):
        chyby.append(
            f"řádky se liší:\n  skutečné:  {sorted(r.klic() for r in skutecne)}\n"
            f"  očekávané: {sorted(r.klic() for r in ocekavane)}"
        )
        return chyby
    zbyvajici = list(skutecne)
    for o in ocekavane:
        shoda = next(
            (
                s
                for s in zbyvajici
                if s.klic() == o.klic() and all(s.dimenze.get(k) == v for k, v in o.dimenze.items())
            ),
            None,
        )
        if shoda is None:
            chyby.append(f"chybí řádek s dimenzemi {o}")
        else:
            zbyvajici.remove(shoda)
    return chyby


def zkontroluj(operace: dict[str, Operace]) -> list[str]:
    """Kontroly katalogu podle specifikace (03-katalog-operaci.md)."""
    chyby: list[str] = []
    for op in operace.values():
        misto = f"{op.soubor}:{op.id}"
        if op.stav not in STAVY:
            chyby.append(f"{misto}: neznámý stav {op.stav!r}")
        if not op.zdroje:
            chyby.append(f"{misto}: chybí zdroj")
        if op.zpusob == "sablona":
            if not op.zapisy:
                chyby.append(f"{misto}: šablonová operace bez zápisů")
            if not op.priklady:
                chyby.append(f"{misto}: chybí příklad")
            for p in op.priklady:
                try:
                    skutecne = sestav(op, p.get("vstupy") or {}, p.get("krok"))
                except (ChybaKatalogu, ValueError) as e:
                    chyby.append(f"{misto} / {p.get('nazev')}: {e}")
                    continue
                for c in porovnej(skutecne, ocekavane_radky(p)):
                    chyby.append(f"{misto} / {p.get('nazev')}: {c}")
        elif not op.data.get("postup"):
            chyby.append(f"{misto}: operace prováděná kódem musí popsat postup")
    return chyby
