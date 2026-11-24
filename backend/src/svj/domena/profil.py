"""Profil účtové osnovy SVJ: převod role účtu na číslo účtu."""

from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path

import yaml

from .penize import halire


class NeznamaRole(KeyError):
    pass


# Role s hvězdičkou, které se rozvádějí po položkách správy (`sprava` v profilu), ne po službách.
ROLE_SPRAVY = frozenset({"zalohy_sprava", "naklady_spravy"})


@dataclass(frozen=True)
class Jednotka:
    oznaceni: str
    plocha: int  # setiny m² (90,90 m² = 9090)
    podil: Fraction
    # Podíl tak, jak je zapsaný v profilu ("718/8600"); zlomek se sám zkrátí na 359/4300.
    zapis_podilu: str = ""

    @property
    def podil_text(self) -> str:
        return self.zapis_podilu or f"{self.podil.numerator}/{self.podil.denominator}"


@dataclass
class Profil:
    id: str
    nazev: str
    role: dict[str, str]
    sluzby: dict[str, dict[str, str]]
    # Krátkodobé zálohy na správu domu (pojištění, správce, revize…), vedené zvlášť od služeb.
    sprava: dict[str, dict[str, str]] = field(default_factory=dict)
    udaje_jednotek: list[Jednotka] = field(default_factory=list)
    vs_predpona: str | None = None
    nazvy_uctu: dict[str, str] = field(default_factory=dict)
    # Údaje pro účetní závěrku a dopisy vlastníkům.
    ico: str | None = None
    sidlo: str | None = None
    statutarni_organ: str | None = None
    # Příspěvky na správu: "zalohove" (stanoví se k 31. 12. ze záloh) nebo "nezalohove".
    prispevky: str | None = None
    # Kdo platí předpis za měsíc, ve kterém se jednotka převedla: "dosavadni" (vlastník
    # k prvnímu dni měsíce), nebo "novy" (vlastník, kterému jednotka patří od převodu).
    predpis_mesice_prevodu: str = "dosavadni"

    @property
    def jednotky(self) -> list[str]:
        return [j.oznaceni for j in self.udaje_jednotek]

    def jednotka_podle_vs(self, vs: str | None) -> str | None:
        """VS 100100601, 100102 nebo 1001007 → jednotka 1001/6, 1001/2, 1001/7.

        Platí pro `vs_predpona` 1001.
        """
        if not vs or not self.vs_predpona or not vs.startswith(self.vs_predpona):
            return None
        zbytek = vs[len(self.vs_predpona) :]
        if not zbytek.isdigit():
            return None
        if len(zbytek) == 5:
            cislo = int(zbytek[:3])
        elif 1 <= len(zbytek) <= 3:
            cislo = int(zbytek)
        else:
            return None
        return next((j for j in self.jednotky if j.rsplit("/", 1)[-1] == str(cislo)), None)

    @property
    def bankovni_ucty(self) -> list[str]:
        """Účely bankovních účtů podle rolí `banka.<ucel>` (např. provozni, fond_oprav)."""
        return [r.removeprefix("banka.") for r in self.role if r.startswith("banka.")]

    def polozky(self, zaklad: str) -> dict[str, dict[str, str]]:
        """Služby, nebo položky správy, po kterých se rozvádí role `zaklad.*`."""
        return self.sprava if zaklad in ROLE_SPRAVY else self.sluzby

    def je_sprava(self, role: str) -> bool:
        return role.partition(".")[0] in ROLE_SPRAVY

    def role_uctu(self) -> dict[str, str]:
        """Číslo účtu → role (včetně účtů rozvedených po službách a položkách správy)."""
        vysledek: dict[str, str] = {}
        for role, ucet in self.role.items():
            if role.endswith(".*"):
                zaklad = role.removesuffix(".*")
                for sluzba, udaje in self.polozky(zaklad).items():
                    vysledek.setdefault(ucet.format(**udaje), f"{zaklad}.{sluzba}")
            else:
                vysledek.setdefault(ucet, role)
        # Konkrétní role má přednost před rozvedenou hvězdičkou.
        vysledek.update({u: r for r, u in self.role.items() if not r.endswith(".*")})
        return vysledek

    def nazev_uctu(self, ucet: str) -> str:
        return self.nazvy_uctu.get(ucet, ucet)

    def ucet(self, role: str) -> str:
        if role in self.role:
            return self.role[role]
        zaklad, _, sluzba = role.partition(".")
        sablona = self.role.get(f"{zaklad}.*")
        if sablona is None or not sluzba:
            raise NeznamaRole(f"profil {self.id} nezná roli {role!r}")
        polozky = self.polozky(zaklad)
        if sluzba not in polozky:
            druh = "položku správy" if zaklad in ROLE_SPRAVY else "službu"
            raise NeznamaRole(f"profil {self.id} nezná {druh} {sluzba!r} (role {role!r})")
        return sablona.format(**polozky[sluzba])


def vychozi_cesta() -> Path:
    from ..nastaveni import nastaveni

    return nastaveni().profily


class ChybiProfil(FileNotFoundError):
    pass


def nacti(nazev: str, cesta: Path | None = None) -> Profil:
    soubor = (cesta or vychozi_cesta()) / f"{nazev}.yaml"
    if not soubor.exists():
        raise ChybiProfil(
            f"Profil SVJ {nazev!r} nenalezen v {soubor.parent}. Nastavte PROFIL a PROFILY v .env."
        )
    d = yaml.safe_load(soubor.read_text(encoding="utf-8"))
    return Profil(
        id=d["id"],
        nazev=d["nazev"],
        role=d["role"],
        sluzby=d.get("sluzby") or {},
        sprava=d.get("sprava") or {},
        udaje_jednotek=[_jednotka(j) for j in d.get("jednotky") or []],
        vs_predpona=d.get("vs_predpona"),
        nazvy_uctu={str(k): str(v) for k, v in (d.get("nazvy_uctu") or {}).items()},
        ico=d.get("ico"),
        sidlo=d.get("sidlo"),
        statutarni_organ=d.get("statutarni_organ"),
        prispevky=d.get("prispevky"),
        predpis_mesice_prevodu=_volba_prevodu(d.get("predpis_mesice_prevodu")),
    )


def _volba_prevodu(hodnota: str | None) -> str:
    if hodnota in (None, "dosavadni", "novy"):
        return hodnota or "dosavadni"
    raise ValueError(
        f"predpis_mesice_prevodu v profilu musí být dosavadni nebo novy, ne {hodnota!r}"
    )


def _jednotka(d: dict) -> Jednotka:
    zapis = str(d["podil"]).replace(" ", "")
    citatel, _, jmenovatel = zapis.partition("/")
    return Jednotka(
        oznaceni=str(d["oznaceni"]),
        plocha=halire(str(d["plocha"])),
        podil=Fraction(int(citatel), int(jmenovatel or 1)),
        zapis_podilu=zapis,
    )
