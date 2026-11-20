"""Měřidla a odečty.

Měřidlo patří jednotce, nebo domu (jednotka None). Odečet je stav měřidla k datu; stav
s časem neklesá. Výměna měřidla zapíše konečný stav starého, uzavře ho a osadí nové
s počátečním stavem ve stejný den. Spotřeba jednotky za rok je součet spotřeby všech jejích
měřidel daného druhu, která v roce byla osazená.

Odečty slouží jako podklad pro zúčtovatele tepla a vody a pro kontrolu jeho výsledků;
rozúčtování podle vyhlášky 269/2015 Sb. aplikace nepočítá.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .db import Meridlo, Odecet
from .domena.profil import Profil

# Druh měřidla → (název, jednotka měření).
DRUHY: dict[str, tuple[str, str]] = {
    "studena_voda": ("Studená voda", "m³"),
    "tepla_voda": ("Teplá voda", "m³"),
    "teplo": ("Teplo", "GJ"),
    "rozdelovac": ("Indikátor topných nákladů", "dílky"),
    "elektrina": ("Elektřina", "kWh"),
    "plyn": ("Plyn", "m³"),
}

# Jak daleko od začátku nebo konce roku smí být odečet, aby se počítal jako roční.
TOLERANCE = timedelta(days=31)


class ChybaMeridel(ValueError):
    pass


@dataclass
class UdajeMeridla:
    jednotka: str | None
    druh: str
    vyrobni_cislo: str
    osazeno_od: date
    umisteni: str = ""
    poznamka: str = ""


def _d(d: date) -> str:
    return f"{d.day}. {d.month}. {d.year}"


def _cislo(stav: Decimal) -> str:
    t = format(stav.normalize(), "f")
    return t.replace(".", ",")


def stav(hodnota: str | Decimal | int | float) -> Decimal:
    """Stav měřidla z textu: „1 234,5“ i „1234.5“, nejvýš tři desetinná místa."""
    try:
        d = Decimal(str(hodnota).replace(" ", "").replace(" ", "").replace(",", "."))
    except InvalidOperation as e:
        raise ChybaMeridel(f"Stav „{hodnota}“ není číslo.") from e
    if not d.is_finite() or d < 0:
        raise ChybaMeridel("Stav měřidla musí být nezáporné číslo.")
    if d.as_tuple().exponent < -3:  # type: ignore[operator]
        raise ChybaMeridel("Stav měřidla může mít nejvýš tři desetinná místa.")
    if d >= Decimal("100000000000"):
        raise ChybaMeridel("Stav měřidla je příliš velký.")
    return d


def meridla(s: Session) -> list[Meridlo]:
    return list(
        s.scalars(
            select(Meridlo)
            .options(selectinload(Meridlo.odecty))
            .order_by(Meridlo.jednotka.nulls_first(), Meridlo.druh, Meridlo.osazeno_od, Meridlo.id)
        )
    )


def _over(profil: Profil, u: UdajeMeridla) -> UdajeMeridla:
    if u.jednotka is not None and u.jednotka not in profil.jednotky:
        raise ChybaMeridel(f"Jednotka {u.jednotka} v profilu SVJ není.")
    if u.druh not in DRUHY:
        raise ChybaMeridel("Neznámý druh měřidla.")
    cislo = u.vyrobni_cislo.strip()
    if not cislo:
        raise ChybaMeridel("Chybí výrobní číslo měřidla.")
    if len(cislo) > 64 or len(u.umisteni) > 200:
        raise ChybaMeridel("Výrobní číslo nebo umístění je příliš dlouhé.")
    return UdajeMeridla(
        jednotka=u.jednotka,
        druh=u.druh,
        vyrobni_cislo=cislo,
        osazeno_od=u.osazeno_od,
        umisteni=u.umisteni.strip(),
        poznamka=u.poznamka.strip(),
    )


def _meridlo(s: Session, meridlo_id: int) -> Meridlo:
    m = s.get(Meridlo, meridlo_id)
    if m is None:
        raise ChybaMeridel("Takové měřidlo v evidenci není.")
    return m


def pridej_meridlo(
    s: Session, profil: Profil, u: UdajeMeridla, pocatecni: Decimal | None, kdo: str
) -> Meridlo:
    u = _over(profil, u)
    m = Meridlo(
        jednotka=u.jednotka,
        druh=u.druh,
        vyrobni_cislo=u.vyrobni_cislo,
        umisteni=u.umisteni,
        osazeno_od=u.osazeno_od,
        poznamka=u.poznamka,
        upravil=kdo,
    )
    s.add(m)
    s.flush()
    if pocatecni is not None:
        zapis_odecet(s, m.id, u.osazeno_od, pocatecni, "počáteční stav při osazení", kdo)
    return m


def uprav_meridlo(
    s: Session,
    profil: Profil,
    meridlo_id: int,
    vyrobni_cislo: str,
    umisteni: str,
    osazeno_od: date,
    poznamka: str,
    kdo: str,
) -> Meridlo:
    m = _meridlo(s, meridlo_id)
    u = _over(
        profil,
        UdajeMeridla(m.jednotka, m.druh, vyrobni_cislo, osazeno_od, umisteni, poznamka),
    )
    if m.odstraneno_do is not None and osazeno_od > m.odstraneno_do:
        raise ChybaMeridel("Měřidlo nemůže být osazené až po svém odstranění.")
    if m.odecty and m.odecty[0].datum < osazeno_od:
        raise ChybaMeridel(
            f"Měřidlo má odečet z {_d(m.odecty[0].datum)}, osazené muselo být nejpozději tehdy."
        )
    m.vyrobni_cislo = u.vyrobni_cislo
    m.umisteni = u.umisteni
    m.osazeno_od = u.osazeno_od
    m.poznamka = u.poznamka
    m.upravil = kdo
    return m


def smaz_meridlo(s: Session, meridlo_id: int) -> None:
    """Smaže měřidlo i jeho odečty. Smazání náhrady znovu otevře měřidlo, které nahradila."""
    m = _meridlo(s, meridlo_id)
    if s.scalar(select(Meridlo.id).where(Meridlo.nahrazuje_id == m.id)) is not None:
        raise ChybaMeridel("Měřidlo už bylo vyměněné. Nejdřív smažte to, které ho nahradilo.")
    if m.nahrazuje_id is not None:
        puvodni = _meridlo(s, m.nahrazuje_id)
        puvodni.odstraneno_do = None
        # Konečný stav z výměny patří k výměně, ne k běžným odečtům.
        for o in list(puvodni.odecty):
            if o.datum == m.osazeno_od:
                puvodni.odecty.remove(o)
    s.delete(m)


def zapis_odecet(
    s: Session, meridlo_id: int, datum: date, hodnota: Decimal, zdroj: str, kdo: str
) -> Odecet:
    """Zapíše stav k datu; když už k tomu dni odečet je, přepíše ho."""
    m = _meridlo(s, meridlo_id)
    if datum < m.osazeno_od or (m.odstraneno_do is not None and datum > m.odstraneno_do):
        do = _d(m.odstraneno_do) if m.odstraneno_do else "dosud"
        raise ChybaMeridel(
            f"Měřidlo {m.vyrobni_cislo} bylo osazené {_d(m.osazeno_od)} – {do}, "
            f"odečet k {_d(datum)} k němu nepatří."
        )
    hodnota = stav(hodnota)
    pred = [o for o in m.odecty if o.datum < datum]
    po = [o for o in m.odecty if o.datum > datum]
    if pred and hodnota < pred[-1].stav:
        raise ChybaMeridel(
            f"Stav {_cislo(hodnota)} měřidla {m.vyrobni_cislo} je menší než "
            f"{_cislo(pred[-1].stav)} z {_d(pred[-1].datum)}. Pokud bylo měřidlo vyměněné, "
            "zapište výměnu."
        )
    if po and hodnota > po[0].stav:
        raise ChybaMeridel(
            f"Stav {_cislo(hodnota)} měřidla {m.vyrobni_cislo} je větší než pozdější "
            f"{_cislo(po[0].stav)} z {_d(po[0].datum)}."
        )
    o = next((o for o in m.odecty if o.datum == datum), None)
    if o is None:
        o = Odecet(datum=datum, stav=hodnota, zdroj=zdroj.strip()[:200], upravil=kdo)
        m.odecty.append(o)
        m.odecty.sort(key=lambda x: x.datum)
    else:
        o.stav = hodnota
        o.zdroj = zdroj.strip()[:200]
        o.upravil = kdo
    return o


def zapis_odecty(
    s: Session, datum: date, stavy: dict[int, Decimal], zdroj: str, kdo: str
) -> list[Odecet]:
    """Hromadný odečet: stavy více měřidel ke stejnému dni."""
    if not stavy:
        raise ChybaMeridel("Vyplňte stav aspoň u jednoho měřidla.")
    return [zapis_odecet(s, mid, datum, h, zdroj, kdo) for mid, h in stavy.items()]


def smaz_odecet(s: Session, odecet_id: int) -> None:
    o = s.get(Odecet, odecet_id)
    if o is None:
        raise ChybaMeridel("Takový odečet v evidenci není.")
    s.delete(o)


def vymen(
    s: Session,
    meridlo_id: int,
    datum: date,
    konecny: Decimal,
    vyrobni_cislo: str,
    pocatecni: Decimal,
    kdo: str,
) -> Meridlo:
    """Zapíše konečný stav starého měřidla, uzavře ho a osadí nové se stejným druhem."""
    stare = _meridlo(s, meridlo_id)
    if stare.odstraneno_do is not None:
        raise ChybaMeridel("Toto měřidlo už je odstraněné.")
    if datum < stare.osazeno_od:
        raise ChybaMeridel("Výměna nemůže být dřív, než bylo měřidlo osazené.")
    if any(o.datum > datum for o in stare.odecty):
        raise ChybaMeridel("Staré měřidlo má odečet po dni výměny. Opravte datum nebo odečet.")
    cislo = vyrobni_cislo.strip()
    if not cislo:
        raise ChybaMeridel("Chybí výrobní číslo nového měřidla.")
    zapis_odecet(s, stare.id, datum, konecny, "konečný stav při výměně", kdo)
    stare.odstraneno_do = datum
    stare.upravil = kdo
    nove = Meridlo(
        jednotka=stare.jednotka,
        druh=stare.druh,
        vyrobni_cislo=cislo[:64],
        umisteni=stare.umisteni,
        osazeno_od=datum,
        nahrazuje_id=stare.id,
        poznamka="",
        upravil=kdo,
    )
    s.add(nove)
    s.flush()
    zapis_odecet(s, nove.id, datum, pocatecni, "počáteční stav při výměně", kdo)
    return nove


@dataclass
class CastSpotreby:
    meridlo: Meridlo
    od: Odecet | None
    do: Odecet | None
    spotreba: Decimal | None


@dataclass
class Spotreba:
    jednotka: str | None
    druh: str
    spotreba: Decimal | None  # None, když u některého měřidla chybí odečet
    casti: list[CastSpotreby] = field(default_factory=list)
    upozorneni: list[str] = field(default_factory=list)


def _nejblizsi(odecty: list[Odecet], cil: date) -> Odecet | None:
    blizke = [o for o in odecty if abs(o.datum - cil) <= TOLERANCE]
    return min(blizke, key=lambda o: (abs(o.datum - cil), o.datum), default=None)


def spotreba(s: Session, rok: int) -> list[Spotreba]:
    """Spotřeba za rok po jednotkách a druzích.

    Začátek je odečet nejblíž 31. 12. předchozího roku (nebo dni osazení), konec odečet
    nejblíž 31. 12. roku (nebo dni odstranění), oba nejvýš měsíc vedle.
    """
    zacatek_roku, konec_roku = date(rok - 1, 12, 31), date(rok, 12, 31)
    podle: dict[tuple[str | None, str], Spotreba] = {}
    for m in meridla(s):
        if m.osazeno_od > konec_roku or (
            m.odstraneno_do is not None and m.odstraneno_do <= zacatek_roku
        ):
            continue
        x = podle.setdefault((m.jednotka, m.druh), Spotreba(m.jednotka, m.druh, Decimal(0)))
        od_cil = max(zacatek_roku, m.osazeno_od)
        do_cil = min(konec_roku, m.odstraneno_do or konec_roku)
        od = _nejblizsi(m.odecty, od_cil)
        do = _nejblizsi([o for o in m.odecty if od is None or o.datum > od.datum], do_cil)
        cast = CastSpotreby(m, od, do, do.stav - od.stav if od and do else None)
        x.casti.append(cast)
        if od is None:
            x.upozorneni.append(f"Měřidlo {m.vyrobni_cislo}: chybí odečet kolem {_d(od_cil)}.")
        if do is None:
            x.upozorneni.append(f"Měřidlo {m.vyrobni_cislo}: chybí odečet kolem {_d(do_cil)}.")
        if cast.spotreba is None:
            x.spotreba = None
        elif x.spotreba is not None:
            x.spotreba += cast.spotreba
    return list(podle.values())
