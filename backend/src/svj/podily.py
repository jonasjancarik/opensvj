"""Podíly jednotek na společných částech s platností v čase.

Podíly z profilu SVJ platí do první změny zadané v aplikaci (tabulka `zmena_podilu`).
Změna podílů (typicky změna prohlášení vlastníka zapsaná do katastru) je vždy celá sada
podílů všech jednotek a jejich součet je přesně 1.

Předpis záloh se počítá po celých měsících, proto se nové podíly použijí od prvního celého
měsíce, ve kterém platí: změna od 1. 7. platí od července, změna od 15. 7. až od srpna.
Roční vyúčtování dělí náklady podle průměru podílů za měsíce roku, takže sedí s tím,
z čeho se počítaly zálohy.
"""

import math
from dataclasses import dataclass, field
from datetime import date, datetime
from fractions import Fraction

from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import Obdobi, ZmenaPodilu
from .domena.profil import Profil

MESICE_OD = [
    "od ledna", "od února", "od března", "od dubna", "od května", "od června",
    "od července", "od srpna", "od září", "od října", "od listopadu", "od prosince",
]  # fmt: skip


class ChybaPodilu(ValueError):
    pass


def prvni_mesic(d: date) -> date:
    """První den prvního celého měsíce od data `d`."""
    if d.day == 1:
        return d
    return date(d.year + d.month // 12, d.month % 12 + 1, 1)


def zlomek(text: str) -> Fraction:
    """„543/8600“ → Fraction(543, 8600). Podíl musí být kladný zlomek celých čísel."""
    t = text.replace(" ", "").replace(" ", "")
    citatel, lomitko, jmenovatel = t.partition("/")
    if not citatel.isdigit() or (lomitko and not jmenovatel.isdigit()):
        raise ChybaPodilu(f"„{text}“ není podíl. Zapište ho jako zlomek, třeba 543/8600.")
    x = Fraction(int(citatel), int(jmenovatel or 1)) if int(jmenovatel or 1) else None
    if not x:
        raise ChybaPodilu(f"Podíl „{text}“ musí být větší než nula.")
    return x


def _datum(d: date) -> str:
    return f"{d.day}. {d.month}. {d.year}"


@dataclass(frozen=True)
class Sada:
    """Podíly všech jednotek: zlomky pro výpočet a zápis tak, jak je v prohlášení."""

    podily: dict[str, Fraction]
    texty: dict[str, str]


@dataclass(frozen=True)
class Zmena:
    plati_od: date
    sada: Sada
    zdroj: str
    upravil: str = ""
    upraveno: datetime | None = None

    @property
    def od_mesice(self) -> date:
        return prvni_mesic(self.plati_od)


@dataclass
class Podily:
    zakladni: Sada
    zmeny: list[Zmena] = field(default_factory=list)  # podle data platnosti

    def k_datu(self, d: date) -> Sada:
        """Podíly, které podle prohlášení platí v den `d`."""
        platne = [z for z in self.zmeny if z.plati_od <= d]
        return platne[-1].sada if platne else self.zakladni

    def k_mesici(self, rok: int, mesic: int) -> Sada:
        """Podíly, se kterými se počítá předpis záloh za měsíc."""
        den = date(rok, mesic, 1)
        platne = [z for z in self.zmeny if z.od_mesice <= den]
        return platne[-1].sada if platne else self.zakladni

    def obdobi_roku(self, rok: int) -> list[tuple[int, int, Sada]]:
        """Měsíce roku se stejnými podíly: (od měsíce, do měsíce, podíly)."""
        vysledek: list[tuple[int, int, Sada]] = []
        for m in range(1, 13):
            sada = self.k_mesici(rok, m)
            if vysledek and vysledek[-1][2] is sada:
                vysledek[-1] = (vysledek[-1][0], m, sada)
            else:
                vysledek.append((m, m, sada))
        return vysledek

    def v_roce(self, rok: int) -> dict[str, Fraction]:
        """Průměrný podíl jednotek za měsíce roku; součet je pořád přesně 1."""
        vysledek: dict[str, Fraction] = dict.fromkeys(self.zakladni.podily, Fraction(0))
        for od, do, sada in self.obdobi_roku(rok):
            for j in vysledek:
                vysledek[j] += sada.podily[j] * (do - od + 1)
        return {j: x / 12 for j, x in vysledek.items()}

    def zmeny_v_roce(self, rok: int) -> bool:
        return len(self.obdobi_roku(rok)) > 1


def _sada_z_profilu(profil: Profil) -> Sada:
    return Sada(
        {j.oznaceni: j.podil for j in profil.udaje_jednotek},
        {j.oznaceni: j.podil_text for j in profil.udaje_jednotek},
    )


def _zmena(profil: Profil, r: ZmenaPodilu) -> Zmena:
    jednotky = set(profil.jednotky)
    if set(r.podily) != jednotky:
        chybi = sorted(jednotky - set(r.podily))
        raise ChybaPodilu(
            f"Změna podílů od {_datum(r.plati_od)} nemá podíl jednotek {', '.join(chybi)}. "
            "Jednotky v profilu SVJ se od té doby změnily; podíly je potřeba zadat znovu."
            if chybi
            else f"Změna podílů od {_datum(r.plati_od)} má podíl jednotky, kterou SVJ nemá."
        )
    return Zmena(
        plati_od=r.plati_od,
        sada=Sada({j: zlomek(t) for j, t in r.podily.items()}, dict(r.podily)),
        zdroj=r.zdroj,
        upravil=r.upravil,
        upraveno=r.upraveno,
    )


def ze_souboru(profil: Profil) -> Podily:
    return Podily(_sada_z_profilu(profil))


def nacti(s: Session, profil: Profil) -> Podily:
    radky = s.scalars(select(ZmenaPodilu).order_by(ZmenaPodilu.plati_od))
    return Podily(_sada_z_profilu(profil), [_zmena(profil, r) for r in radky])


def zkontroluj_sadu(profil: Profil, texty: dict[str, str]) -> Sada:
    """Ověří, že sada má podíl každé jednotky a součet je přesně 1."""
    jednotky = profil.jednotky
    navic = [j for j in texty if j not in jednotky]
    if navic:
        raise ChybaPodilu(f"Jednotku {', '.join(navic)} SVJ nemá.")
    chybi = [j for j in jednotky if not (texty.get(j) or "").strip()]
    if chybi:
        raise ChybaPodilu(f"Chybí podíl jednotky {', '.join(chybi)}.")
    podily: dict[str, Fraction] = {}
    for j in jednotky:
        try:
            podily[j] = zlomek(texty[j])
        except ChybaPodilu as e:
            raise ChybaPodilu(f"Jednotka {j}: {e}") from e
    soucet = sum(podily.values())
    if soucet != 1:
        # Rozdíl ve jmenovateli, jaký je v prohlášení (100/8600, ne zkrácených 1/86).
        rozdil = abs(1 - soucet)
        jmenovatel = math.lcm(*(int(t.partition("/")[2] or 1) for t in _cista(texty).values()))
        kolik = (
            f"{rozdil.numerator * jmenovatel // rozdil.denominator}/{jmenovatel}"
            if jmenovatel % rozdil.denominator == 0
            else f"{rozdil.numerator}/{rozdil.denominator}"
        )
        raise ChybaPodilu(
            f"Součet podílů musí být přesně 1. Teď {'chybí' if soucet < 1 else 'přebývá'} {kolik}."
        )
    return Sada(podily, _cista(texty))


def _cista(texty: dict[str, str]) -> dict[str, str]:
    return {j: t.replace(" ", "").replace("\u00a0", "") for j, t in texty.items()}


def nejdrive_od(s: Session) -> date:
    """Od kterého měsíce může změna podílů nejdřív platit: zaúčtované předpisy se nemění."""
    from . import predpisy

    return predpisy.prvni_mesic_ke_zmene(s)


def _over_datum(s: Session, d: date) -> None:
    od = nejdrive_od(s)
    if prvni_mesic(d) < od:
        raise ChybaPodilu(
            f"Předpisy záloh do {_datum(date.fromordinal(od.toordinal() - 1))} už jsou zaúčtované "
            f"s dosavadními podíly. Změna může platit nejdřív od {_datum(od)}. Jestli platí "
            "dřív, stornujte nejdřív v Deníku předpisy od toho měsíce."
        )
    o = s.get(Obdobi, d.year)
    if o is not None and o.stav == "uzavrene":
        raise ChybaPodilu(f"Rok {d.year} je uzavřený, podíly v něm měnit nejde.")


def uloz(
    s: Session,
    profil: Profil,
    plati_od: date,
    texty: dict[str, str],
    zdroj: str,
    kdo: str,
    puvodni: date | None = None,
) -> None:
    """Uloží změnu podílů. `puvodni` je datum upravované změny (None = nová)."""
    zdroj = zdroj.strip()
    if not zdroj:
        raise ChybaPodilu(
            "Napište, podle čeho se podíly mění, třeba změna prohlášení vlastníka a číslo vkladu "
            "do katastru."
        )
    sada = zkontroluj_sadu(profil, texty)
    for d in {plati_od, puvodni} - {None}:
        _over_datum(s, d)  # type: ignore[arg-type]
    if puvodni is not None and s.get(ZmenaPodilu, puvodni) is None:
        raise ChybaPodilu("Tato změna podílů v aplikaci není. Načtěte stránku znovu.")
    if puvodni != plati_od and s.get(ZmenaPodilu, plati_od) is not None:
        raise ChybaPodilu(f"Změna podílů od {_datum(plati_od)} už je zapsaná. Upravte tu.")

    ostatni = [z for z in nacti(s, profil).zmeny if z.plati_od != puvodni]
    stejny_mesic = next((z for z in ostatni if z.od_mesice == prvni_mesic(plati_od)), None)
    if stejny_mesic is not None:
        raise ChybaPodilu(
            f"Předpis se od {_datum(prvni_mesic(plati_od))} už počítá se změnou podílů od "
            f"{_datum(stejny_mesic.plati_od)}. V jednom měsíci může začít platit jen jedna změna."
        )
    pred = Podily(_sada_z_profilu(profil), ostatni).k_datu(
        date.fromordinal(plati_od.toordinal() - 1)
    )
    if pred.podily == sada.podily:
        raise ChybaPodilu("Podíly jsou stejné jako dosud, není co měnit.")

    if puvodni is not None and puvodni != plati_od:
        stara = s.get(ZmenaPodilu, puvodni)
        s.delete(stara)
        s.flush()
    r = s.get(ZmenaPodilu, plati_od) or ZmenaPodilu(plati_od=plati_od)
    r.podily = sada.texty
    r.zdroj = zdroj[:200]
    r.upravil = kdo
    s.add(r)
    s.flush()


def smaz(s: Session, plati_od: date) -> None:
    r = s.get(ZmenaPodilu, plati_od)
    if r is None:
        raise ChybaPodilu("Tato změna podílů v aplikaci není. Načtěte stránku znovu.")
    _over_datum(s, plati_od)
    s.delete(r)
    s.flush()
