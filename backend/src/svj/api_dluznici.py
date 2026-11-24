"""API pro přehled dlužníků, podklad pro upomínku a potvrzení o dluzích při prodeji."""

from datetime import date

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import exists, func, select

from . import banka, denik, dluznici, predpisy, prevody, uvery
from .api_lide import Adresat, adresati, adresati_osob
from .db import BankovniPohyb, BankovniUcet, sezeni
from .domena import katalog, profil
from .domena import urok as urok_z_prodleni
from .domena.penize import na_text
from .nastaveni import nastaveni
from .prihlaseni import Prihlaseny, Zapisujici

router = APIRouter(prefix="/api/dluznici")


class Polozka(BaseModel):
    popis: str
    splatnost: date | None  # None = z minulých let
    castka: int
    zbyva: int
    po_splatnosti: bool
    urok: int | None  # úrok z prodlení ze zbývající částky k dnešku; None = neumíme
    sazba: int | None  # roční sazba úroku v setinách procenta


class ZbytekUveru(BaseModel):
    """Nesplacený podíl jednotky na úvěru: není to dluh, přechází s jednotkou."""

    nazev: str
    zbyva: int
    mesicne: int


class Jednotka(BaseModel):
    jednotka: str
    po_splatnosti: int
    nesplatne: int
    preplatek: int
    od: date | None
    z_minulych_let: bool
    urok: int
    urok_neuplny: bool
    urok_do: date | None  # do kdy už SVJ úrok z prodlení předepsalo
    sankce: int  # předepsaný úrok z prodlení a pokuty, které zbývá zaplatit
    polozky: list[Polozka]
    vlastnici: list[Adresat]  # k dnešku; prázdné, když je aplikace nezná
    uvery: list[ZbytekUveru]  # nesplacené podíly na úvěrech (k datu potvrzení)


class Odpis(BaseModel):
    datum: date
    castka: int
    polozka: str  # název položky správy
    rozhodnuti: str
    dluhy: list[str]
    zbyva: int


class OdepsanaJednotka(BaseModel):
    jednotka: str
    odepsano: int
    uhrazeno: int
    zbyva: int
    odpisy: list[Odpis]


class PolozkaSpravy(BaseModel):
    kod: str
    nazev: str


class Dluznici(BaseModel):
    rok: int
    dnes: date
    svj: str
    ico: str | None
    sidlo: str | None
    ucet: str | None  # provozní účet pro platby, když ho aplikace zná z výpisu
    posledni_vypis: date | None  # datum posledního pohybu na účtech
    nezauctovane_pohyby: int
    sazby_overeny_k: date
    zdroj_sazeb: str
    celkem_po_splatnosti: int
    jednotky: list[Jednotka]
    odepsane: list[OdepsanaJednotka]  # odepsané dluhy přes všechny roky
    polozky_spravy: list[PolozkaSpravy]
    # Potvrzení pro prodávajícího po převodu: k jakému dni a komu (jinak k dnešku vlastníkům).
    k_datu: date | None = None
    osoby: list[int] = []


@router.get("/prevod/{vlastnictvi_id}")
def k_prevodu(vlastnictvi_id: int, _: Prihlaseny) -> Dluznici:
    """Dluhy prodávajícího k poslednímu dni jeho vlastnictví, pro potvrzení o dluzích."""
    return _prehled(None, vlastnictvi_id)


@router.get("/{rok}")
def prehled(rok: int, _: Prihlaseny) -> Dluznici:
    return _prehled(rok)


def _prehled(rok: int | None, prevod_id: int | None = None) -> Dluznici:
    """Přehled za rok k dnešku, nebo (s `prevod_id`) jen jednotka převodu k jeho datu."""
    prof = profil.nacti(nastaveni().profil)
    nast = predpisy.nacti_s(prof, sezeni)
    dnes = date.today()
    with sezeni()() as s:
        k_datu, osoby = None, []
        if prevod_id is None:
            vse = dluznici.prehled(s, prof, nast, rok, dnes)
            kdo = adresati(s, dnes)
        else:
            try:
                p = prevody.potvrzeni_k_prevodu(s, prof, nast, prevod_id, dnes)
            except prevody.ChybaPrevodu as e:
                raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e
            k_datu, rok, vse = p.k_datu, p.k_datu.year, [p.dluhy]
            osoby = [c.osoba_id for c in p.predchozi.vlastnici]
            kdo = {p.dluhy.jednotka: adresati_osob(s, osoby, dnes)}
        ucet = s.scalar(select(BankovniUcet.cislo).where(BankovniUcet.ucel == "provozni"))
        posledni = s.scalar(select(func.max(BankovniPohyb.datum)))
        odepsane = dluznici.odepsane(s)
        zbytky = {d.jednotka: uvery.zbytky_jednotky(s, d.jednotka, k_datu) for d in vse}
        nezauctovane = s.scalar(
            select(func.count())
            .select_from(BankovniPohyb)
            .where(~exists().where(banka.zauctovano(BankovniPohyb.id)))
        )
    jednotky = [
        Jednotka(
            jednotka=d.jednotka,
            po_splatnosti=d.po_splatnosti,
            nesplatne=d.nesplatne,
            preplatek=d.preplatek,
            od=d.od,
            z_minulych_let=d.z_minulych_let,
            urok=d.urok,
            urok_neuplny=d.urok_neuplny,
            urok_do=d.urok_do,
            sankce=d.sankce,
            polozky=[
                Polozka(
                    popis=p.popis,
                    splatnost=p.splatnost,
                    castka=p.castka,
                    zbyva=p.zbyva,
                    po_splatnosti=p.po_splatnosti(d.dnes),
                    urok=p.urok(d.dnes, d.urok_do),
                    sazba=p.sazba(),
                )
                for p in d.polozky
            ],
            vlastnici=kdo.get(d.jednotka, []),
            uvery=[
                ZbytekUveru(nazev=z.nazev, zbyva=z.zbyva, mesicne=z.mesicne)
                for z in zbytky[d.jednotka]
            ],
        )
        for d in vse
    ]
    return Dluznici(
        rok=rok,
        dnes=dnes,
        svj=prof.nazev,
        ico=prof.ico,
        sidlo=prof.sidlo,
        ucet=ucet,
        posledni_vypis=posledni,
        nezauctovane_pohyby=nezauctovane or 0,
        sazby_overeny_k=urok_z_prodleni.OVERENO_K,
        zdroj_sazeb=urok_z_prodleni.ZDROJ,
        celkem_po_splatnosti=sum(j.po_splatnosti for j in jednotky),
        jednotky=jednotky,
        odepsane=[
            OdepsanaJednotka(
                jednotka=o.jednotka,
                odepsano=o.odepsano,
                uhrazeno=o.uhrazeno,
                zbyva=o.zbyva,
                odpisy=[
                    Odpis(
                        datum=x.datum,
                        castka=x.castka,
                        polozka=prof.sprava.get(x.polozka, {}).get("nazev", x.polozka),
                        rozhodnuti=x.rozhodnuti,
                        dluhy=x.dluhy,
                        zbyva=x.zbyva,
                    )
                    for x in o.odpisy
                ],
            )
            for o in odepsane.values()
        ],
        polozky_spravy=[
            PolozkaSpravy(kod=k, nazev=u.get("nazev", k)) for k, u in prof.sprava.items()
        ],
        k_datu=k_datu,
        osoby=osoby,
    )


class PredpisUroku(BaseModel):
    jednotka: str
    castka: int  # haléře


@router.post("/{rok}/urok")
def predepis_urok(rok: int, z: PredpisUroku, uzivatel: Zapisujici) -> Dluznici:
    """Předepíše vlastníkovi úrok z prodlení k dnešku: SVJ ho od této chvíle požaduje."""
    prof = profil.nacti(nastaveni().profil)
    dnes = date.today()
    jednotka = z.jednotka
    if jednotka not in prof.jednotky:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Jednotka {jednotka} není v profilu.")
    if z.castka <= 0:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Úrok musí být kladný.")
    if dnes.year != rok:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Úrok jde předepsat jen v běžném roce {dnes.year}.",
        )
    with sezeni()() as s:
        try:
            denik.zauctuj(
                s,
                prof,
                katalog.nacti()[dluznici.OPERACE_UROKU],
                {"jednotka": jednotka, "castka": na_text(z.castka)},
                datum=dnes,
                popis=f"Úrok z prodlení do {dnes.day}. {dnes.month}. {dnes.year}",
                doklad="ID",
                zauctoval=uzivatel.email,
            )
        except denik.ChybaUctovani as e:
            s.rollback()
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from e
        s.commit()
    return prehled(rok, None)


class OdpisDluhu(BaseModel):
    jednotka: str
    castka: int  # haléře
    polozka: str
    rozhodnuti: str


@router.post("/{rok}/odpis")
def odepis(rok: int, z: OdpisDluhu, uzivatel: Zapisujici) -> Dluznici:
    """Odepíše nedobytný dluh jednotky; aplikace ho dál vede mezi odepsanými."""
    prof = profil.nacti(nastaveni().profil)
    nast = predpisy.nacti_s(prof, sezeni)
    with sezeni()() as s:
        try:
            dluznici.zauctuj_odpis(
                s,
                prof,
                nast,
                rok,
                jednotka=z.jednotka,
                castka=z.castka,
                polozka=z.polozka,
                rozhodnuti=z.rozhodnuti,
                zauctoval=uzivatel.email,
            )
        except (dluznici.ChybaOdpisu, denik.ChybaUctovani) as e:
            s.rollback()
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from e
        s.commit()
    return prehled(rok, None)
