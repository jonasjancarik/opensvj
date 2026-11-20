"""API pro evidenci vlastníků: osoby a vlastnictví jednotek."""

from datetime import date, datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError

from . import lide, predpisy, prevody
from .db import Osoba as OsobaDb
from .db import Vlastnictvi as VlastnictviDb
from .db import sezeni
from .domena import profil
from .nastaveni import nastaveni
from .prihlaseni import Prihlaseny, Zapisujici

router = APIRouter(prefix="/api/vlastnici")


class Osoba(BaseModel):
    id: int
    jmeno: str
    ico: str | None
    adresa: str
    email: str | None
    telefon: str | None
    ucet: str | None
    souhlas_email: date | None
    poznamka: str
    upravil: str
    upraveno: datetime


class UdajeOsoby(BaseModel):
    jmeno: str = Field(max_length=200)
    adresa: str = Field(default="", max_length=500)
    ico: str | None = None
    email: str | None = None
    telefon: str | None = None
    ucet: str | None = None
    souhlas_email: date | None = None
    poznamka: str = Field(default="", max_length=2000)


class Clen(BaseModel):
    osoba_id: int
    podil: str | None = None


class NovyClen(BaseModel):
    """Vlastník při zápisu: osoba z evidence, nebo nová osoba, která se rovnou založí."""

    osoba_id: int | None = None
    nova: UdajeOsoby | None = None
    podil: str | None = None


class Vlastnictvi(BaseModel):
    id: int
    plati_od: date
    plati_do: date | None
    zdroj: str
    vlastnici: list[Clen]
    upravil: str


class Jednotka(BaseModel):
    jednotka: str
    plocha: int  # setiny m²
    podil: str
    vlastnictvi: list[Vlastnictvi]  # od nejstaršího


class Prehled(BaseModel):
    dnes: date
    jednotky: list[Jednotka]
    osoby: list[Osoba]


class ZapisVlastnictvi(BaseModel):
    jednotka: str
    plati_od: date
    vlastnici: list[NovyClen] = Field(min_length=1, max_length=20)
    zdroj: str = Field(default="", max_length=500)


class UpravaVlastnictvi(BaseModel):
    plati_od: date
    vlastnici: list[NovyClen] = Field(min_length=1, max_length=20)
    zdroj: str = Field(default="", max_length=500)


class Adresat(BaseModel):
    """Vlastník jednotky do hlavičky dopisu."""

    jmeno: str
    adresa: str
    email: str | None
    souhlas_email: bool


def adresati(s, datum: date) -> dict[str, list[Adresat]]:
    """Jednotka → vlastníci k datu, pro dopisy, upomínky a potvrzení."""
    return {
        j: [
            Adresat(
                jmeno=o.jmeno,
                adresa=o.adresa,
                email=o.email,
                souhlas_email=o.souhlas_email is not None and o.souhlas_email <= datum,
            )
            for o in lide_
        ]
        for j, lide_ in lide.vlastnici_k(s, datum).items()
    }


def _osoba(o: OsobaDb) -> Osoba:
    return Osoba(
        id=o.id,
        jmeno=o.jmeno,
        ico=o.ico,
        adresa=o.adresa,
        email=o.email,
        telefon=o.telefon,
        ucet=o.ucet,
        souhlas_email=o.souhlas_email,
        poznamka=o.poznamka,
        upravil=o.upravil,
        upraveno=o.upraveno,
    )


def _vlastnictvi(v: VlastnictviDb) -> Vlastnictvi:
    return Vlastnictvi(
        id=v.id,
        plati_od=v.plati_od,
        plati_do=v.plati_do,
        zdroj=v.zdroj,
        vlastnici=[Clen(osoba_id=c.osoba_id, podil=c.podil) for c in v.vlastnici],
        upravil=v.upravil,
    )


def _prehled(s) -> Prehled:
    prof = profil.nacti(nastaveni().profil)
    podle_jednotky: dict[str, list[Vlastnictvi]] = {}
    for v in lide.vlastnictvi(s):
        podle_jednotky.setdefault(v.jednotka, []).append(_vlastnictvi(v))
    return Prehled(
        dnes=date.today(),
        jednotky=[
            Jednotka(
                jednotka=j.oznaceni,
                plocha=j.plocha,
                podil=f"{j.podil.numerator}/{j.podil.denominator}",
                vlastnictvi=podle_jednotky.get(j.oznaceni, []),
            )
            for j in prof.udaje_jednotek
        ],
        osoby=[_osoba(o) for o in lide.osoby(s)],
    )


def _clenove(s, c: list[NovyClen], kdo: str) -> list[lide.ClenVlastnictvi]:
    vysledek = []
    for x in c:
        if x.nova is not None:
            osoba_id = lide.pridej_osobu(s, lide.UdajeOsoby(**x.nova.model_dump()), kdo).id
        elif x.osoba_id is not None:
            osoba_id = x.osoba_id
        else:
            raise lide.ChybaLidi("U vlastníka chybí osoba.")
        vysledek.append(lide.ClenVlastnictvi(osoba_id=osoba_id, podil=x.podil))
    return vysledek


def _proved(akce) -> Prehled:
    """Provede změnu a vrátí nový přehled; chyby převede na srozumitelnou odpověď."""
    with sezeni()() as s:
        try:
            akce(s)
            s.flush()
        except lide.ChybaLidi as e:
            s.rollback()
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from e
        except IntegrityError as e:
            s.rollback()
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Vlastnictví by se překrývalo s jiným obdobím téže jednotky. Načtěte stránku "
                "znovu, mohl ji mezitím změnit někdo jiný.",
            ) from e
        s.commit()
        return _prehled(s)


@router.get("")
def prehled(_: Prihlaseny) -> Prehled:
    with sezeni()() as s:
        return _prehled(s)


@router.post("/osoby")
def pridej_osobu(udaje: UdajeOsoby, uzivatel: Zapisujici) -> Prehled:
    u = lide.UdajeOsoby(**udaje.model_dump())
    return _proved(lambda s: lide.pridej_osobu(s, u, uzivatel.email))


@router.put("/osoby/{osoba_id}")
def uprav_osobu(osoba_id: int, udaje: UdajeOsoby, uzivatel: Zapisujici) -> Prehled:
    u = lide.UdajeOsoby(**udaje.model_dump())
    return _proved(lambda s: lide.uprav_osobu(s, osoba_id, u, uzivatel.email))


@router.delete("/osoby/{osoba_id}")
def smaz_osobu(osoba_id: int, _: Zapisujici) -> Prehled:
    return _proved(lambda s: lide.smaz_osobu(s, osoba_id))


@router.post("/vlastnictvi")
def zapis_vlastnictvi(z: ZapisVlastnictvi, uzivatel: Zapisujici) -> Prehled:
    prof = profil.nacti(nastaveni().profil)
    return _proved(
        lambda s: lide.zapis_vlastnictvi(
            s,
            prof,
            z.jednotka,
            z.plati_od,
            _clenove(s, z.vlastnici, uzivatel.email),
            z.zdroj,
            uzivatel.email,
        )
    )


@router.put("/vlastnictvi/{vlastnictvi_id}")
def uprav_vlastnictvi(vlastnictvi_id: int, z: UpravaVlastnictvi, uzivatel: Zapisujici) -> Prehled:
    return _proved(
        lambda s: lide.uprav_vlastnictvi(
            s,
            vlastnictvi_id,
            z.plati_od,
            _clenove(s, z.vlastnici, uzivatel.email),
            z.zdroj,
            uzivatel.email,
        )
    )


@router.delete("/vlastnictvi/{vlastnictvi_id}")
def smaz_vlastnictvi(vlastnictvi_id: int, _: Zapisujici) -> Prehled:
    return _proved(lambda s: lide.smaz_vlastnictvi(s, vlastnictvi_id))


class DluhPriPrevodu(BaseModel):
    klic: str
    popis: str
    zbyva: int
    splatnost: date | None
    navrh: bool


class Prevod(BaseModel):
    jednotka: str
    plati_od: date
    prevodce: str
    nabyvatel: str
    volba: str  # predpis_mesice_prevodu z profilu
    dluhy: list[DluhPriPrevodu]
    zapis: str | None  # "n/rok", když už je ponechání dluhů zaúčtované
    zauctovano: int  # kolik převodci zůstalo podle zápisu


class PonechaniDluhu(BaseModel):
    klice: list[str] = Field(min_length=1, max_length=200)


def _prevod(s, vlastnictvi_id: int) -> Prevod:
    prof = profil.nacti(nastaveni().profil)
    try:
        p = prevody.prevod(s, prof, predpisy.nacti(prof), vlastnictvi_id)
    except prevody.ChybaPrevodu as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e
    return Prevod(
        jednotka=p.vlastnictvi.jednotka,
        plati_od=p.vlastnictvi.plati_od,
        prevodce=p.prevodce,
        nabyvatel=", ".join(c.osoba.jmeno for c in p.vlastnictvi.vlastnici),
        volba=prof.predpis_mesice_prevodu,
        dluhy=[
            DluhPriPrevodu(
                klic=d.klic, popis=d.popis, zbyva=d.zbyva, splatnost=d.splatnost, navrh=d.navrh
            )
            for d in p.dluhy
        ],
        zapis=f"{p.zapis.poradove_cislo}/{p.zapis.rok}" if p.zapis else None,
        zauctovano=sum(r.castka for r in p.zapis.radky if r.strana == "md") if p.zapis else 0,
    )


@router.get("/prevody/{vlastnictvi_id}")
def prevod(vlastnictvi_id: int, _: Prihlaseny) -> Prevod:
    with sezeni()() as s:
        return _prevod(s, vlastnictvi_id)


@router.post("/prevody/{vlastnictvi_id}")
def ponech_prevodci(vlastnictvi_id: int, z: PonechaniDluhu, uzivatel: Zapisujici) -> Prevod:
    prof = profil.nacti(nastaveni().profil)
    with sezeni()() as s:
        try:
            prevody.ponech_prevodci(
                s, prof, predpisy.nacti(prof), vlastnictvi_id, z.klice, uzivatel.email
            )
        except prevody.ChybaPrevodu as e:
            s.rollback()
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from e
        s.commit()
        return _prevod(s, vlastnictvi_id)
