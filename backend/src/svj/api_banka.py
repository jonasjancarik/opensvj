"""API pro banku: nahrání výpisu, seznam pohybů s návrhy a zaúčtování pohybu."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session, selectinload

from . import banka, dluznici, faktury, lide, predpisy
from .db import (
    BankovniPohyb,
    BankovniUcet,
    BankovniVypis,
    ParovaniPohybu,
    PravidloParovani,
    Zapis,
    sezeni,
)
from .domena import katalog, profil
from .nastaveni import nastaveni
from .prihlaseni import Prihlaseny, Zapisujici

router = APIRouter(prefix="/api/banka")
MAX_VELIKOST = 5 * 1024 * 1024

NAZVY_UCTU = {"provozni": "Provozní účet", "fond_oprav": "Účet fondu oprav"}


def _session() -> Session:
    return sezeni()()


def _profil() -> profil.Profil:
    return profil.nacti(nastaveni().profil)


class Ucet(BaseModel):
    ucel: str
    nazev: str
    cislo: str | None
    zustatek: int | None
    posledni_vypis: str | None
    datum_vypisu: date | None
    pohyby_do: date | None  # nejnovější nahraný pohyb (i z přehledu pohybů)


class Moznost(BaseModel):
    id: str
    nazev: str
    stav: str
    pole: list[str]
    volitelna: list[str] = []  # nepovinné vstupy (dluh, který vlastník platbou určil)


class DluhJednotky(BaseModel):
    radek: int  # řádek zápisu, kterým dluh vznikl
    popis: str
    splatnost: date | None
    zbyva: int


class Navrh(BaseModel):
    operace: str
    vstupy: dict[str, str]
    duvod: str


class Zauctovani(BaseModel):
    operace: str
    nazev: str
    vstupy: dict[str, str]
    zapis: str
    zauctoval: str


class Pohyb(BaseModel):
    id: int
    datum: date
    castka: int
    ucel: str
    zdroj: str
    protiucet: str | None
    nazev: str
    vs: str | None
    ks: str | None
    ss: str | None
    zprava: str
    navrh: Navrh | None
    zauctovano: Zauctovani | None


class OtevrenaFaktura(BaseModel):
    cislo: str
    dodavatel: str
    cislo_dodavatele: str | None
    zbyva: int
    splatnost: date


class DluhDrivejsiho(BaseModel):
    jednotka: str
    vlastnik: str
    castka: int


class OdepsanyDluh(BaseModel):
    jednotka: str
    zbyva: int


class Banka(BaseModel):
    ucty: list[Ucet]
    jednotky: list[str]
    drivejsi: list[DluhDrivejsiho]  # dluhy dřívějších vlastníků pro jejich platby
    odepsane: list[OdepsanyDluh]  # odepsané dluhy, které zbývá zaplatit
    faktury: list[OtevrenaFaktura]
    moznosti: dict[str, list[Moznost]]
    pohyby: list[Pohyb]
    nezauctovano: int


class Nahrano(BaseModel):
    druh: str
    ucel: str
    nazev_uctu: str
    cislo: int | None
    rok: int
    od: date | None
    do: date
    pocet_pohybu: int
    novych: int
    uz_nahranych: int
    novy_zustatek: int | None
    uz_byl_nahrany: bool


class Pozadavek(BaseModel):
    operace: str
    vstupy: dict[str, str] = Field(default_factory=dict)
    zapamatovat: bool = False


def _zdroj(v: BankovniVypis) -> str:
    if v.druh == "vypis":
        return f"výpis {v.cislo}/{v.rok}"
    return f"přehled pohybů z {v.nahrano:%-d. %-m. %Y}"


def _pohyb(
    p: BankovniPohyb,
    ops: dict[str, katalog.Operace],
    ucty: list[BankovniUcet],
    pravidla: list[PravidloParovani],
    poradi_zapisu: dict[int, str],
    kontext: banka.KontextNavrhu | None = None,
) -> Pohyb:
    zauct = None
    navrh = None
    if p.parovani is not None:
        par = p.parovani
        zauct = Zauctovani(
            operace=par.operace,
            nazev=ops[par.operace].nazev,
            vstupy=par.vstupy,
            zapis=poradi_zapisu.get(par.zapis_id, ""),
            zauctoval=par.zauctoval,
        )
    else:
        n = banka.navrhni(p, ucty, pravidla, kontext)
        if n is not None:
            navrh = Navrh(operace=n.operace, vstupy=n.vstupy, duvod=n.duvod)
    return Pohyb(
        id=p.id,
        datum=p.datum,
        castka=p.castka,
        ucel=p.ucet.ucel,
        zdroj=_zdroj(p.vypis),
        protiucet=f"{p.protiucet}/{p.kod_banky}" if p.protiucet and p.kod_banky else p.protiucet,
        nazev=p.nazev,
        vs=p.vs,
        ks=p.ks,
        ss=p.ss,
        zprava=p.zprava,
        navrh=navrh,
        zauctovano=zauct,
    )


@router.get("")
def prehled(_: Prihlaseny, vse: bool = False) -> Banka:
    prof = _profil()
    ops = katalog.nacti()
    with _session() as s:
        ucty = list(s.scalars(select(BankovniUcet)))
        pravidla = list(s.scalars(select(PravidloParovani)))
        dotaz = (
            select(BankovniPohyb)
            .options(
                selectinload(BankovniPohyb.parovani_vse)
                .selectinload(ParovaniPohybu.zapis)
                .selectinload(Zapis.opravy),
                selectinload(BankovniPohyb.ucet),
                selectinload(BankovniPohyb.vypis),
            )
            .order_by(BankovniPohyb.datum, BankovniPohyb.id)
        )
        dnes = date.today()
        otevrene = faktury.prehled(s, jen_otevrene=True)
        kontext = banka.KontextNavrhu(
            profil=prof,
            mesicni=predpisy.mesicni_celkem(prof, predpisy.nacti(prof, s), dnes.year, dnes.month),
            otevrene_faktury=otevrene,
            ucty_vlastniku=lide.jednotky_podle_uctu(s, dnes),
        )
        nezauctovane = ~exists().where(banka.zauctovano(BankovniPohyb.id))
        pocet = len(s.scalars(select(BankovniPohyb.id).where(nezauctovane)).all())
        if not vse:
            dotaz = dotaz.where(nezauctovane)
        pohyby = list(s.scalars(dotaz))
        zapisy = {
            z.id: f"{z.poradove_cislo}/{z.rok}"
            for z in s.scalars(
                select(Zapis).join(ParovaniPohybu, ParovaniPohybu.zapis_id == Zapis.id)
            )
        }
        vysledek_ucty = []
        podle_uceli = {u.ucel: u for u in ucty}
        for ucel in prof.bankovni_ucty:
            u = podle_uceli.get(ucel)
            posledni = (
                s.scalar(
                    select(BankovniVypis)
                    .where(BankovniVypis.ucet_id == u.id, BankovniVypis.druh == "vypis")
                    .order_by(BankovniVypis.datum.desc(), BankovniVypis.cislo.desc())
                    .limit(1)
                )
                if u
                else None
            )
            vysledek_ucty.append(
                Ucet(
                    ucel=ucel,
                    nazev=NAZVY_UCTU.get(ucel, ucel),
                    cislo=u.cislo if u else None,
                    zustatek=posledni.novy_zustatek if posledni else None,
                    posledni_vypis=f"{posledni.cislo}/{posledni.rok}" if posledni else None,
                    datum_vypisu=posledni.datum if posledni else None,
                    pohyby_do=s.scalar(
                        select(func.max(BankovniPohyb.datum)).where(BankovniPohyb.ucet_id == u.id)
                    )
                    if u
                    else None,
                )
            )
        return Banka(
            ucty=vysledek_ucty,
            jednotky=prof.jednotky,
            drivejsi=[
                DluhDrivejsiho(jednotka=d.jednotka, vlastnik=d.vlastnik, castka=d.castka)
                for d in predpisy.drivejsi_vlastnici(s, dnes.year)
            ],
            odepsane=[
                OdepsanyDluh(jednotka=o.jednotka, zbyva=o.zbyva)
                for o in dluznici.odepsane(s).values()
                if o.zbyva > 0
            ],
            faktury=[
                OtevrenaFaktura(
                    cislo=x.faktura.cislo,
                    dodavatel=x.faktura.dodavatel,
                    cislo_dodavatele=x.faktura.cislo_dodavatele,
                    zbyva=x.zbyva,
                    splatnost=x.faktura.splatnost,
                )
                for x in sorted(otevrene, key=lambda x: x.faktura.splatnost)
            ],
            moznosti={
                smer: [
                    Moznost(
                        id=i,
                        nazev=ops[i].nazev,
                        stav=ops[i].stav,
                        pole=pole,
                        volitelna=banka.VOLITELNE.get(i, []),
                    )
                    for i, pole in mozne.items()
                ]
                for smer, mozne in banka.OPERACE.items()
            },
            pohyby=[_pohyb(p, ops, ucty, pravidla, zapisy, kontext) for p in pohyby],
            nezauctovano=pocet,
        )


@router.get("/dluhy/{rok}")
def dluhy(rok: int, jednotka: str, _: Prihlaseny) -> list[DluhJednotky]:
    """Nezaplacené dluhy jednotky v roce platby, aby u ní šlo určit, na který dluh platí."""
    prof = _profil()
    nast = predpisy.nacti_s(prof, sezeni)
    with _session() as s:
        vse = dluznici.prehled(s, prof, nast, rok)
    d = next((x for x in vse if x.jednotka == jednotka), None)
    if d is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Jednotku {jednotka} SVJ nemá.")
    return [
        DluhJednotky(radek=p.radek, popis=p.popis, splatnost=p.splatnost, zbyva=p.zbyva)
        for p in d.polozky
        if p.radek is not None
    ]


@router.post("/vypisy")
async def nahraj_vypis(
    request: Request,
    uzivatel: Zapisujici,
    nazev: Annotated[str, Query(max_length=255)] = "vypis.gpc",
    ucel: str | None = None,
) -> list[Nahrano]:
    # Velikost hlídáme už při čtení, aby se velký soubor vůbec nenačetl do paměti.
    prilis_velky = HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "Soubor je příliš velký.")
    delka = request.headers.get("content-length", "")
    if delka.isdigit() and int(delka) > MAX_VELIKOST:
        raise prilis_velky
    casti = bytearray()
    async for cast in request.stream():
        casti += cast
        if len(casti) > MAX_VELIKOST:
            raise prilis_velky
    data = bytes(casti)
    if not data:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Soubor je prázdný.")
    with _session() as s:
        try:
            v = banka.nahraj(
                s, _profil(), data, nazev_souboru=nazev, nahral=uzivatel.email, ucel=ucel
            )
        except banka.NeznamyUcet as e:
            s.rollback()
            raise HTTPException(
                status.HTTP_409_CONFLICT, {"kod": "neznamy_ucet", "cislo": e.cislo}
            ) from e
        except banka.ChybaBanky as e:
            s.rollback()
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e
        s.commit()
    return [
        Nahrano(
            druh=x.druh,
            ucel=x.ucel,
            nazev_uctu=NAZVY_UCTU.get(x.ucel, x.ucel),
            cislo=x.cislo,
            rok=x.rok,
            od=x.od,
            do=x.do,
            pocet_pohybu=x.pocet_pohybu,
            novych=x.novych,
            uz_nahranych=x.uz_nahranych,
            novy_zustatek=x.novy_zustatek,
            uz_byl_nahrany=x.uz_byl_nahrany,
        )
        for x in v.vypisy
    ]


@router.post("/pohyby/{pohyb_id}")
def zauctuj(pohyb_id: int, pozadavek: Pozadavek, uzivatel: Zapisujici) -> Pohyb:
    with _session() as s:
        try:
            banka.zauctuj_pohyb(
                s,
                _profil(),
                pohyb_id,
                pozadavek.operace,
                pozadavek.vstupy,
                zauctoval=uzivatel.email,
                zapamatovat=pozadavek.zapamatovat,
            )
        except banka.ChybaBanky as e:
            s.rollback()
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e
        s.commit()
        p = s.get(BankovniPohyb, pohyb_id)
        s.refresh(p)
        zapis = s.get(Zapis, p.parovani.zapis_id)
        return _pohyb(
            p,
            katalog.nacti(),
            [],
            [],
            {zapis.id: f"{zapis.poradove_cislo}/{zapis.rok}"},
        )
