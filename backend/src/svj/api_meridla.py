"""API pro měřidla, odečty a roční spotřebu."""

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError

from . import meridla
from .db import Meridlo as MeridloDb
from .db import sezeni
from .domena import profil
from .nastaveni import nastaveni
from .prihlaseni import Prihlaseny, Zapisujici

router = APIRouter(prefix="/api/meridla")


class Druh(BaseModel):
    kod: str
    nazev: str
    jednotka: str  # jednotka měření (m³, GJ…)


class Odecet(BaseModel):
    id: int
    datum: date
    stav: Decimal
    zdroj: str
    upravil: str


class Meridlo(BaseModel):
    id: int
    jednotka: str | None
    druh: str
    vyrobni_cislo: str
    umisteni: str
    osazeno_od: date
    odstraneno_do: date | None
    nahrazuje_id: int | None
    poznamka: str
    odecty: list[Odecet]


class CastSpotreby(BaseModel):
    meridlo_id: int
    vyrobni_cislo: str
    od: Odecet | None
    do: Odecet | None
    spotreba: Decimal | None


class Spotreba(BaseModel):
    jednotka: str | None
    druh: str
    spotreba: Decimal | None
    casti: list[CastSpotreby]
    upozorneni: list[str]


class Prehled(BaseModel):
    dnes: date
    jednotky: list[str]
    druhy: list[Druh]
    meridla: list[Meridlo]


class NoveMeridlo(BaseModel):
    jednotka: str | None = None
    druh: str
    vyrobni_cislo: str = Field(max_length=64)
    umisteni: str = Field(default="", max_length=200)
    osazeno_od: date
    poznamka: str = Field(default="", max_length=2000)
    pocatecni_stav: str | None = Field(default=None, max_length=32)


class UpravaMeridla(BaseModel):
    vyrobni_cislo: str = Field(max_length=64)
    umisteni: str = Field(default="", max_length=200)
    osazeno_od: date
    poznamka: str = Field(default="", max_length=2000)


class Vymena(BaseModel):
    datum: date
    konecny_stav: str = Field(max_length=32)
    vyrobni_cislo: str = Field(max_length=64)
    pocatecni_stav: str = Field(max_length=32)


class StavMeridla(BaseModel):
    meridlo_id: int
    stav: str = Field(max_length=32)


class HromadnyOdecet(BaseModel):
    datum: date
    zdroj: str = Field(default="", max_length=200)
    stavy: list[StavMeridla] = Field(max_length=2000)


def _odecet(o) -> Odecet:
    return Odecet(id=o.id, datum=o.datum, stav=o.stav, zdroj=o.zdroj, upravil=o.upravil)


def _meridlo(m: MeridloDb) -> Meridlo:
    return Meridlo(
        id=m.id,
        jednotka=m.jednotka,
        druh=m.druh,
        vyrobni_cislo=m.vyrobni_cislo,
        umisteni=m.umisteni,
        osazeno_od=m.osazeno_od,
        odstraneno_do=m.odstraneno_do,
        nahrazuje_id=m.nahrazuje_id,
        poznamka=m.poznamka,
        odecty=[_odecet(o) for o in m.odecty],
    )


def _prehled(s) -> Prehled:
    prof = profil.nacti(nastaveni().profil)
    return Prehled(
        dnes=date.today(),
        jednotky=prof.jednotky,
        druhy=[Druh(kod=k, nazev=n, jednotka=j) for k, (n, j) in meridla.DRUHY.items()],
        meridla=[_meridlo(m) for m in meridla.meridla(s)],
    )


def _proved(akce) -> Prehled:
    with sezeni()() as s:
        try:
            akce(s)
            s.flush()
        except meridla.ChybaMeridel as e:
            s.rollback()
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from e
        except IntegrityError as e:
            s.rollback()
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Změnu nejde uložit, data se mezitím změnila. Načtěte stránku znovu.",
            ) from e
        s.commit()
        s.expire_all()
        return _prehled(s)


@router.get("")
def prehled(_: Prihlaseny) -> Prehled:
    with sezeni()() as s:
        return _prehled(s)


@router.get("/spotreba")
def spotreba(rok: int, _: Prihlaseny) -> list[Spotreba]:
    with sezeni()() as s:
        return [
            Spotreba(
                jednotka=x.jednotka,
                druh=x.druh,
                spotreba=x.spotreba,
                casti=[
                    CastSpotreby(
                        meridlo_id=c.meridlo.id,
                        vyrobni_cislo=c.meridlo.vyrobni_cislo,
                        od=_odecet(c.od) if c.od else None,
                        do=_odecet(c.do) if c.do else None,
                        spotreba=c.spotreba,
                    )
                    for c in x.casti
                ],
                upozorneni=x.upozorneni,
            )
            for x in meridla.spotreba(s, rok)
        ]


@router.post("")
def pridej(z: NoveMeridlo, uzivatel: Zapisujici) -> Prehled:
    prof = profil.nacti(nastaveni().profil)

    def akce(s):
        pocatecni = meridla.stav(z.pocatecni_stav) if z.pocatecni_stav else None
        u = meridla.UdajeMeridla(
            jednotka=z.jednotka or None,
            druh=z.druh,
            vyrobni_cislo=z.vyrobni_cislo,
            osazeno_od=z.osazeno_od,
            umisteni=z.umisteni,
            poznamka=z.poznamka,
        )
        meridla.pridej_meridlo(s, prof, u, pocatecni, uzivatel.email)

    return _proved(akce)


@router.put("/{meridlo_id}")
def uprav(meridlo_id: int, z: UpravaMeridla, uzivatel: Zapisujici) -> Prehled:
    prof = profil.nacti(nastaveni().profil)
    return _proved(
        lambda s: meridla.uprav_meridlo(
            s,
            prof,
            meridlo_id,
            z.vyrobni_cislo,
            z.umisteni,
            z.osazeno_od,
            z.poznamka,
            uzivatel.email,
        )
    )


@router.delete("/{meridlo_id}")
def smaz(meridlo_id: int, _: Zapisujici) -> Prehled:
    return _proved(lambda s: meridla.smaz_meridlo(s, meridlo_id))


@router.post("/{meridlo_id}/vymena")
def vymen(meridlo_id: int, z: Vymena, uzivatel: Zapisujici) -> Prehled:
    return _proved(
        lambda s: meridla.vymen(
            s,
            meridlo_id,
            z.datum,
            meridla.stav(z.konecny_stav),
            z.vyrobni_cislo,
            meridla.stav(z.pocatecni_stav),
            uzivatel.email,
        )
    )


@router.post("/odecty")
def zapis_odecty(z: HromadnyOdecet, uzivatel: Zapisujici) -> Prehled:
    def akce(s):
        stavy = {x.meridlo_id: meridla.stav(x.stav) for x in z.stavy if x.stav.strip()}
        meridla.zapis_odecty(s, z.datum, stavy, z.zdroj, uzivatel.email)

    return _proved(akce)


@router.delete("/odecty/{odecet_id}")
def smaz_odecet(odecet_id: int, _: Zapisujici) -> Prehled:
    return _proved(lambda s: meridla.smaz_odecet(s, odecet_id))
