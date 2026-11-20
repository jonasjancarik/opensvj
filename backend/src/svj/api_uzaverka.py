"""API pro uzávěrku roku: kontrolní seznam, výkazy, inventura, daň z příjmů a příloha."""

from datetime import date, datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from . import denik, predpisy, ulozene, uzaverka, uzavreni
from .db import sezeni
from .domena import profil
from .nastaveni import nastaveni
from .prihlaseni import Prihlaseny, Zapisujici

router = APIRouter(prefix="/api/uzaverka")


class Odskrtnuti(BaseModel):
    kdo: str
    jmeno: str
    kdy: datetime


class Kontrola(BaseModel):
    kod: str
    nazev: str
    stav: str
    detail: str
    odkaz: str | None
    odskrtnuti: Odskrtnuti | None  # jen u bodů, které se odškrtávají ručně


class ZmenaOdskrtnuti(BaseModel):
    kod: str
    hotovo: bool


class RadekVykazu(BaseModel):
    strana: str
    radek: str
    nazev: str
    castka: int
    tisice: int


class PolozkaSoupisu(BaseModel):
    popis: str
    castka: int


class Soupis(BaseModel):
    ucet: str
    nazev: str
    zustatek: int
    zpusob: str
    polozky: list[PolozkaSoupisu]


class VynosProDan(BaseModel):
    popis: str
    castka: int
    zdaneni: str
    poznamka: str


class Dan(BaseModel):
    musi_podat: bool
    vynosy: list[VynosProDan]


class OddilPrilohy(BaseModel):
    nadpis: str
    odstavce: list[str]


class Uzavreni(BaseModel):
    stav: str | None  # otevrene | uzavrene | None, když rok v aplikaci není
    dalsi: str | None  # stav dalšího roku
    zapisy: list[str]  # uzávěrkové zápisy a počáteční stavy dalšího roku, "n/rok"
    proc_nejde: list[str]  # proč rok zatím nejde uzavřít


class ZnovuOtevreni(BaseModel):
    duvod: str = Field(max_length=500)


class Uzaverka(BaseModel):
    rok: int
    k_datu: date
    dnes: date
    svj: str
    ico: str | None
    sidlo: str | None
    kontroly: list[Kontrola]
    rozvaha: list[RadekVykazu]
    vysledovka: list[RadekVykazu]
    vysledek: int
    soupisy: list[Soupis]
    dan: Dan
    priloha: list[OddilPrilohy]
    uzavreni: Uzavreni


def _radky(v) -> list[RadekVykazu]:
    return [RadekVykazu(**r.__dict__) for r in uzaverka.vykaz_radky(v)]


def _odskrtnuti(z) -> Odskrtnuti | None:
    return None if z is None else Odskrtnuti(kdo=z.kdo, jmeno=z.jmeno, kdy=z.kdy)


def _kontrola(k: uzaverka.Kontrola, odskrtnute: dict) -> Kontrola:
    return Kontrola(
        **k.__dict__,
        odskrtnuti=_odskrtnuti(odskrtnute.get(k.kod)) if k.stav == "rucne" else None,
    )


@router.get("/{rok}")
def prehled(rok: int, _: Prihlaseny) -> Uzaverka:
    prof = profil.nacti(nastaveni().profil)
    nast = predpisy.nacti(prof)
    k_datu = date(rok, 12, 31)
    with sezeni()() as s:
        kontroly = uzaverka.kontroly(s, prof, nast, rok, k_datu)
        odskrtnute = ulozene.odskrtnute(s, rok)
        rozvaha, vzz = uzaverka.vykazy_roku(s, rok, k_datu)
        soupisy = uzaverka.soupisy(s, prof, rok, k_datu)
        dan = uzaverka.dan(s, prof, rok)
        priloha = uzaverka.priloha(s, prof, nast, rok, k_datu)
        st = uzavreni.stav(s, rok)
        zapisy = [
            f"{z.poradove_cislo}/{z.rok}"
            for z in (st.vysledkove, st.rozvahove, st.otevreni)
            if z is not None and st.uzavreny
        ]
        proc = [] if st.uzavreny else uzavreni.proc_nejde(s, prof, nast, rok, date.today())
    return Uzaverka(
        rok=rok,
        k_datu=k_datu,
        dnes=date.today(),
        svj=prof.nazev,
        ico=prof.ico,
        sidlo=prof.sidlo,
        kontroly=[_kontrola(k, odskrtnute) for k in kontroly],
        rozvaha=_radky(rozvaha),
        vysledovka=_radky(vzz),
        vysledek=vzz.celkem["vysledek"],
        soupisy=[
            Soupis(
                ucet=x.ucet,
                nazev=x.nazev,
                zustatek=x.zustatek,
                zpusob=x.zpusob,
                polozky=[PolozkaSoupisu(**p.__dict__) for p in x.polozky],
            )
            for x in soupisy
        ],
        dan=Dan(musi_podat=dan.musi_podat, vynosy=[VynosProDan(**v.__dict__) for v in dan.vynosy]),
        priloha=[OddilPrilohy(**o.__dict__) for o in priloha],
        uzavreni=Uzavreni(stav=st.stav, dalsi=st.dalsi, zapisy=zapisy, proc_nejde=proc),
    )


def _proved(rok: int, akce) -> Uzaverka:
    prof = profil.nacti(nastaveni().profil)
    with sezeni()() as s:
        try:
            akce(s, prof)
        except (uzavreni.ChybaUzavreni, denik.ChybaUctovani) as e:
            s.rollback()
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from e
        s.commit()
    return prehled(rok, None)


@router.post("/{rok}/dalsi-rok")
def zacni_dalsi_rok(rok: int, _: Zapisujici) -> Uzaverka:
    """Založí další rok, aby šlo účtovat ještě před uzávěrkou tohoto."""
    return _proved(rok, lambda s, prof: uzavreni.zacni_dalsi_rok(s, rok))


@router.post("/{rok}/uzavrit")
def uzavri(rok: int, uzivatel: Zapisujici) -> Uzaverka:
    return _proved(
        rok,
        lambda s, prof: uzavreni.uzavri(
            s, prof, predpisy.nacti(prof), rok, zauctoval=uzivatel.email
        ),
    )


@router.post("/{rok}/znovu-otevrit")
def znovu_otevri(rok: int, z: ZnovuOtevreni, uzivatel: Zapisujici) -> Uzaverka:
    return _proved(
        rok,
        lambda s, prof: uzavreni.znovu_otevri(s, rok, duvod=z.duvod, zauctoval=uzivatel.email),
    )


@router.post("/{rok}/odskrtnuti")
def odskrtni(rok: int, zmena: ZmenaOdskrtnuti, uzivatel: Zapisujici) -> Odskrtnuti | None:
    """Ručně odškrtne bod uzávěrky (nebo odškrtnutí zruší) pro celý výbor."""
    prof = profil.nacti(nastaveni().profil)
    nast = predpisy.nacti(prof)
    with sezeni()() as s:
        kontrola = next(
            (
                k
                for k in uzaverka.kontroly(s, prof, nast, rok, date(rok, 12, 31))
                if k.kod == zmena.kod
            ),
            None,
        )
        if kontrola is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Takový bod uzávěrky neexistuje.")
        if kontrola.stav != "rucne":
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "Tenhle bod aplikace ověřuje sama z účetnictví, ručně se neodškrtává.",
            )
        z = ulozene.odskrtni(s, rok, zmena.kod, zmena.hotovo, uzivatel)
        vysledek = _odskrtnuti(z)
        s.commit()
    return vysledek
