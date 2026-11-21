"""API pro roční vyúčtování služeb (teplo, voda, výtah, úklid…)."""

from datetime import date, timedelta

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from . import meridla, predpisy, vyuctovani_sluzeb, zasilky
from .api_lide import Adresat, adresati
from .db import BankovniUcet, VysledekZuctovatele, sezeni
from .domena import profil
from .nastaveni import nastaveni
from .prihlaseni import Prihlaseny, Zapisujici

router = APIRouter(prefix="/api/vyuctovani-sluzeb")


class Zuctovatel(BaseModel):
    castky: dict[str, int]  # jednotka → náklad v haléřích
    zdroj: str


class Sluzba(BaseModel):
    kod: str
    nazev: str
    klic: str
    jak_se_deli: str
    naklady: int
    zalohy: int
    merna_jednotka: str | None  # m³, GJ… u klíče `meridla`
    problem: str | None
    zuctovatel: Zuctovatel | None  # jen u klíče `zuctovatel`


class PolozkaJednotky(BaseModel):
    kod: str
    naklady: int
    zalohy: int
    spotreba: str | None  # z měřidel, u klíče `meridla`


class Jednotka(BaseModel):
    jednotka: str
    osobomesice: int
    zalohy: int
    naklady: int
    rozdil: int  # kladný = nedoplatek
    nezaplacene: int
    polozky: list[PolozkaJednotky]
    vlastnici: list[Adresat]
    doruceno: date | None  # kdy vlastníkovi došlo vyúčtování
    namitky_do: date | None  # 30 dní od doručení (§ 8 odst. 1 zákona 67/2013)
    vyrovnani_do: date | None  # 4 měsíce od doručení (§ 7 odst. 1 zákona 67/2013)


class Vyuctovani(BaseModel):
    rok: int
    dnes: date
    svj: str
    ucet: str | None
    splatnost: date
    doruceni: date
    sluzby: list[Sluzba]
    jednotky: list[Jednotka]
    zapis: str | None
    proc_nejde: str | None
    rozeslani: str  # klíč zásilek s tímto vyúčtováním


def klic_rozeslani(rok: int) -> str:
    return f"vyuctovani_sluzeb:{rok}"


class VysledkyZuctovatele(BaseModel):
    castky: dict[str, int] = Field(max_length=10000)
    zdroj: str = Field(default="", max_length=200)


def _zuctovatel(s, rok: int) -> dict[str, Zuctovatel]:
    vysledek: dict[str, Zuctovatel] = {}
    for v in s.scalars(select(VysledekZuctovatele).where(VysledekZuctovatele.rok == rok)):
        z = vysledek.setdefault(v.sluzba, Zuctovatel(castky={}, zdroj=v.zdroj))
        z.castky[v.jednotka] = v.castka
    return vysledek


def _prehled(rok: int) -> Vyuctovani:
    prof = profil.nacti(nastaveni().profil)
    nast = predpisy.nacti_s(prof, sezeni)
    dnes = date.today()
    with sezeni()() as s:
        v = vyuctovani_sluzeb.spocitej(s, prof, nast, rok, dnes)
        duvod = vyuctovani_sluzeb.proc_nejde(s, nast, v, dnes)
        ucet = s.scalar(select(BankovniUcet.cislo).where(BankovniUcet.ucel == "provozni"))
        zapis = f"{v.zapis.poradove_cislo}/{v.zapis.rok}" if v.zapis else None
        kdo = adresati(s, dnes)
        zuctovatel = _zuctovatel(s, rok)
        doruceno = zasilky.doruceni_jednotek(s, klic_rozeslani(rok))
    return Vyuctovani(
        rok=rok,
        dnes=dnes,
        svj=prof.nazev,
        ucet=ucet,
        splatnost=v.splatnost,
        doruceni=v.doruceni,
        sluzby=[
            Sluzba(
                kod=x.kod,
                nazev=x.nazev,
                klic=x.klic,
                jak_se_deli=x.jak_se_deli,
                naklady=x.naklady,
                zalohy=x.zalohy,
                merna_jednotka=meridla.DRUHY[x.meridlo][1] if x.meridlo in meridla.DRUHY else None,
                problem=x.problem,
                zuctovatel=(
                    zuctovatel.get(x.kod, Zuctovatel(castky={}, zdroj=""))
                    if x.klic == "zuctovatel"
                    else None
                ),
            )
            for x in v.sluzby
        ],
        jednotky=[
            Jednotka(
                jednotka=j.jednotka,
                osobomesice=j.osobomesice,
                zalohy=sum(j.zalohy.values()),
                naklady=sum(j.naklady.values()),
                rozdil=j.rozdil,
                nezaplacene=j.nezaplacene,
                polozky=[
                    PolozkaJednotky(
                        kod=x.kod,
                        naklady=j.naklady.get(x.kod, 0),
                        zalohy=j.zalohy.get(x.kod, 0),
                        spotreba=str(j.spotreba[x.kod]) if x.kod in j.spotreba else None,
                    )
                    for x in v.sluzby
                ],
                vlastnici=kdo.get(j.jednotka, []),
                doruceno=doruceno.get(j.jednotka),
                namitky_do=(
                    doruceno[j.jednotka] + timedelta(days=30) if j.jednotka in doruceno else None
                ),
                vyrovnani_do=(
                    zasilky.plus_mesice(doruceno[j.jednotka], 4) if j.jednotka in doruceno else None
                ),
            )
            for j in v.jednotky
        ],
        zapis=zapis,
        proc_nejde=duvod,
        rozeslani=klic_rozeslani(rok),
    )


def _chyba(s, e: Exception) -> HTTPException:
    s.rollback()
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e))


@router.get("/{rok}")
def prehled(rok: int, _: Prihlaseny) -> Vyuctovani:
    return _prehled(rok)


@router.post("/{rok}")
def zauctuj(rok: int, uzivatel: Zapisujici) -> Vyuctovani:
    prof = profil.nacti(nastaveni().profil)
    with sezeni()() as s:
        try:
            vyuctovani_sluzeb.zauctuj(
                s, prof, predpisy.nacti(prof, s), rok, zauctoval=uzivatel.email
            )
        except vyuctovani_sluzeb.ChybaVyuctovani as e:
            raise _chyba(s, e) from e
        s.commit()
    return _prehled(rok)


@router.put("/{rok}/zuctovatel/{sluzba}")
def uloz_zuctovatele(
    rok: int, sluzba: str, z: VysledkyZuctovatele, uzivatel: Zapisujici
) -> Vyuctovani:
    prof = profil.nacti(nastaveni().profil)
    with sezeni()() as s:
        try:
            vyuctovani_sluzeb.uloz_vysledky(
                s, prof, rok, sluzba, z.castky, z.zdroj.strip(), uzivatel.email
            )
        except vyuctovani_sluzeb.ChybaVyuctovani as e:
            raise _chyba(s, e) from e
        s.commit()
    return _prehled(rok)
