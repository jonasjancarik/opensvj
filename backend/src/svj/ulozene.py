"""Co uživatelé rozpracují v aplikaci a má to vidět celý výbor: odškrtnuté body uzávěrky
a rozepsané formuláře.

Odškrtnutí se jen připisuje (každá změna je nový řádek s tím, kdo a kdy); platí poslední.
Formulář má číslo verze. Kdo ukládá, posílá verzi, kterou naposledy viděl; když mezitím
uložil někdo jiný, uložení se odmítne a cizí změna se nepřepíše.
"""

import re

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from .db import OdskrtnutiUzaverky, UlozenyFormular
from .prihlaseni import Uzivatel

# Druhy formulářů a tvar jejich klíče.
DRUHY = {
    "oznameni-zaloh": re.compile(r"\d{4}-\d{2}-\d{2}"),  # od kdy platí nový předpis
    "pocatecni-stavy": re.compile(r"\d{4}"),  # rok
}
MAX_VELIKOST = 200_000  # znaků v JSON; víc formulář rozumně mít nemůže


class ChybaFormulare(ValueError):
    pass


class Konflikt(Exception):
    """Formulář mezitím uložil někdo jiný."""

    def __init__(self, aktualni: UlozenyFormular | None):
        super().__init__("formulář mezitím změnil někdo jiný")
        self.aktualni = aktualni


# ---------- Odškrtnuté body uzávěrky ----------


def odskrtnute(session: Session, rok: int) -> dict[str, OdskrtnutiUzaverky]:
    """Poslední záznam ke každému bodu, jen u bodů, které jsou teď odškrtnuté."""
    posledni: dict[str, OdskrtnutiUzaverky] = {}
    for z in session.scalars(
        select(OdskrtnutiUzaverky)
        .where(OdskrtnutiUzaverky.rok == rok)
        .order_by(OdskrtnutiUzaverky.id)
    ):
        posledni[z.kod] = z
    return {k: z for k, z in posledni.items() if z.hotovo}


def odskrtni(
    session: Session, rok: int, kod: str, hotovo: bool, uzivatel: Uzivatel
) -> OdskrtnutiUzaverky | None:
    """Zapíše nový stav bodu. Když už v tom stavu je, nic nepřidá. Vrací platné odškrtnutí."""
    soucasne = odskrtnute(session, rok).get(kod)
    if (soucasne is not None) == hotovo:
        return soucasne
    z = OdskrtnutiUzaverky(
        rok=rok, kod=kod, hotovo=hotovo, kdo=uzivatel.email, jmeno=uzivatel.jmeno
    )
    session.add(z)
    session.flush()
    session.refresh(z)
    return z if hotovo else None


# ---------- Rozepsané formuláře ----------


def _over(druh: str, klic: str) -> None:
    vzor = DRUHY.get(druh)
    if vzor is None:
        raise ChybaFormulare(f"Neznámý druh formuláře „{druh}“.")
    if not vzor.fullmatch(klic):
        raise ChybaFormulare(f"Neplatný klíč formuláře „{klic}“.")


def nacti_formular(session: Session, druh: str, klic: str) -> UlozenyFormular | None:
    _over(druh, klic)
    return session.get(UlozenyFormular, (druh, klic))


def uloz_formular(
    session: Session, druh: str, klic: str, obsah: dict, verze: int, uzivatel: Uzivatel
) -> UlozenyFormular:
    """Uloží obsah, pokud je v databázi pořád `verze` (0 = formulář ještě neexistuje)."""
    _over(druh, klic)
    hodnoty = {"obsah": obsah, "upravil": uzivatel.email, "jmeno": uzivatel.jmeno}
    if verze == 0:
        vlozeno = session.execute(
            pg_insert(UlozenyFormular)
            .values(druh=druh, klic=klic, verze=1, **hodnoty)
            .on_conflict_do_nothing()
            .returning(UlozenyFormular.verze)
        ).scalar()
        ok = vlozeno is not None
    else:
        ok = (
            session.execute(
                update(UlozenyFormular)
                .where(
                    UlozenyFormular.druh == druh,
                    UlozenyFormular.klic == klic,
                    UlozenyFormular.verze == verze,
                )
                .values(verze=verze + 1, upraveno=func.now(), **hodnoty)
                .returning(UlozenyFormular.verze)
            ).scalar()
            is not None
        )
    session.expire_all()
    aktualni = session.get(UlozenyFormular, (druh, klic))
    if not ok:
        raise Konflikt(aktualni)
    assert aktualni is not None
    return aktualni


def smaz_formular(session: Session, druh: str, klic: str) -> None:
    """Formulář už není potřeba (např. počáteční stavy jsou zaúčtované)."""
    _over(druh, klic)
    session.execute(
        delete(UlozenyFormular).where(UlozenyFormular.druh == druh, UlozenyFormular.klic == klic)
    )
