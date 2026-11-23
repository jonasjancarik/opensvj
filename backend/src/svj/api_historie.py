"""API pro historii změn (auditní záznam) a upozornění „Změněno po schválení“."""

from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel

from . import audit, rozhodnuti
from .db import AuditniZaznam, sezeni
from .prihlaseni import Prihlaseny

router = APIRouter(prefix="/api/historie")

POCET = 50
AKCE = {"pridani": "Přidáno", "uprava": "Změněno", "smazani": "Smazáno"}


class Rozdil(BaseModel):
    pole: str
    pred: str
    po: str


class Zaznam(BaseModel):
    id: int
    kdy: datetime
    kdo: str
    jmeno: str
    druh: str
    druh_nazev: str
    klic: str
    akce: str
    akce_nazev: str
    nazev: str
    duvod: str
    zmeny: list[Rozdil]


class Druh(BaseModel):
    kod: str
    nazev: str


class Historie(BaseModel):
    zaznamy: list[Zaznam]
    druhy: list[Druh]
    dalsi: bool  # jsou ještě starší záznamy


class ZmenaPoSchvaleni(BaseModel):
    """Kdo a proč změnil schválenou věc. Bez autora, když se změnila mimo aplikaci."""

    kdy: datetime | None
    kdo: str
    jmeno: str
    duvod: str
    druh: str | None  # odkaz do historie změn
    klic: str | None


def zaznam(z: AuditniZaznam) -> Zaznam:
    sl = audit.PODLE_DRUHU.get(z.druh)
    return Zaznam(
        id=z.id,
        kdy=z.kdy,
        kdo=z.kdo,
        jmeno=z.jmeno,
        druh=z.druh,
        druh_nazev=sl.nazev_druhu if sl else z.druh,
        klic=z.klic,
        akce=z.akce,
        akce_nazev=AKCE.get(z.akce, z.akce),
        nazev=z.nazev,
        duvod=z.duvod,
        zmeny=[Rozdil(pole=r.pole, pred=r.pred, po=r.po) for r in audit.rozdily(z)],
    )


def zmena_po_schvaleni(
    d: rozhodnuti.Dolozeni | None, polozka: rozhodnuti.Polozka
) -> ZmenaPoSchvaleni | None:
    if d is None or d.platne:
        return None
    druh, klic = polozka.zmeny or (None, None)
    z = d.zmena
    return ZmenaPoSchvaleni(
        kdy=z.kdy if z else None,
        kdo=z.kdo if z else "",
        jmeno=z.jmeno if z else "",
        duvod=z.duvod if z else "",
        druh=druh,
        klic=klic,
    )


@router.get("")
def historie(
    _: Prihlaseny, druh: str | None = None, klic: str | None = None, pred: int | None = None
) -> Historie:
    with sezeni()() as s:
        zaznamy = audit.zaznamy(s, druh=druh, klic=klic, pred_id=pred, pocet=POCET + 1)
        return Historie(
            zaznamy=[zaznam(z) for z in zaznamy[:POCET]],
            druhy=[Druh(kod=sl.druh, nazev=sl.nazev_druhu) for sl in audit.SLEDOVANE.values()],
            dalsi=len(zaznamy) > POCET,
        )
