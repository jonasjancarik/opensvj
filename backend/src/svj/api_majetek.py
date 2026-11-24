"""API pro evidenci dlouhodobého majetku, odpisy a vyřazení."""

from datetime import date

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from . import majetek
from .db import Majetek, sezeni
from .domena import profil
from .nastaveni import nastaveni
from .prihlaseni import Prihlaseny, Zapisujici

router = APIRouter(prefix="/api/majetek")


class RokPlanu(BaseModel):
    rok: int
    odpis: int
    opravky: int
    zustatek: int


class KartaVen(BaseModel):
    id: int
    nazev: str
    inventarni_cislo: str
    poznamka: str
    druh: str
    druh_nazev: str
    zarazeno: date
    cena: int
    doba_mesicu: int | None
    kryti: str
    kryti_nazev: str
    prevzato_k: date | None
    opravky_prevzate: int
    zapis: str | None  # zařazení "n/rok"
    opravky: int  # k 31. 12. roku (nebo k dnešku v běžném roce)
    zustatkova: int
    odpis_roku: int
    odpis_zauctovan: bool
    vyrazeno: date | None
    plan: list[RokPlanu]


class Prehled(BaseModel):
    rok: int
    dnes: date
    druhy: dict[str, str]
    kryti: dict[str, str]
    fondy: list[str]  # kódy krytí, které jsou fondy (ne položky správy)
    k_zarazeni: dict[str, int]  # druh → nezařazená částka na pořizování
    odpisy_k_zauctovani: int
    lze_odpisy: str | None  # proč odpisy roku ještě nejde zaúčtovat (None = jde)
    karty: list[KartaVen]


class NovaKarta(BaseModel):
    nazev: str = Field(max_length=150)
    inventarni_cislo: str = Field(default="", max_length=32)
    poznamka: str = Field(default="", max_length=2000)
    druh: str
    zarazeno: date
    cena: int = Field(gt=0)
    doba_mesicu: int | None = Field(default=None, ge=1, le=majetek.NEJDELE_MESICU)
    kryti: str = Field(max_length=32)
    prevzato_k: date | None = None
    opravky_prevzate: int = Field(default=0, ge=0)


class Popis(BaseModel):
    nazev: str = Field(max_length=150)
    inventarni_cislo: str = Field(default="", max_length=32)
    poznamka: str = Field(default="", max_length=2000)


class Vyrazeni(BaseModel):
    datum: date
    duvod: str = Field(max_length=300)


def _profil() -> profil.Profil:
    return profil.nacti(nastaveni().profil)


def _k_datu(rok: int, dnes: date) -> date:
    return min(date(rok, 12, 31), max(dnes, date(rok, 1, 1)))


def _ven(s, prof: profil.Profil, m: Majetek, rok: int, k_datu: date) -> KartaVen:
    st = majetek.stav(s, prof, m, rok, k_datu)
    z = m.zapis
    return KartaVen(
        id=m.id,
        nazev=m.nazev,
        inventarni_cislo=m.inventarni_cislo,
        poznamka=m.poznamka,
        druh=m.druh,
        druh_nazev=st.druh,
        zarazeno=m.zarazeno,
        cena=m.cena,
        doba_mesicu=m.doba_mesicu,
        kryti=m.kryti,
        kryti_nazev=st.kryti,
        prevzato_k=m.prevzato_k,
        opravky_prevzate=m.opravky_prevzate,
        zapis=f"{z.poradove_cislo}/{z.rok}" if z else None,
        opravky=st.opravky,
        zustatkova=st.zustatkova,
        odpis_roku=st.odpis_roku,
        odpis_zauctovan=st.odpis_zauctovan,
        vyrazeno=st.vyrazeno,
        plan=[RokPlanu(**r.__dict__) for r in st.plan],
    )


def _prehled(rok: int) -> Prehled:
    prof = _profil()
    dnes = date.today()
    k_datu = _k_datu(rok, dnes)
    druhy = majetek.druhy(prof)
    with sezeni()() as s:
        volne = majetek.k_zarazeni(s, prof)
        k_odepsani = majetek.k_odepsani(s, rok)
        lze = None
        if not k_odepsani:
            lze = f"Za rok {rok} není co odepsat."
        elif dnes < date(rok, 12, 31):
            lze = f"Odpisy za rok {rok} půjde zaúčtovat od 31. 12. {rok}."
        return Prehled(
            rok=rok,
            dnes=dnes,
            druhy={k: d.nazev for k, d in druhy.items()},
            kryti=majetek.kryti(prof),
            fondy=[k for k in majetek.FONDY if k in majetek.kryti(prof)],
            k_zarazeni={k: volne.get(d.porizovani, 0) for k, d in druhy.items()},
            odpisy_k_zauctovani=sum(c for _, c in k_odepsani),
            lze_odpisy=lze,
            karty=[
                _ven(s, prof, m, rok, k_datu)
                for m in majetek.karty(s)
                if m.zarazeno <= date(rok, 12, 31)
            ],
        )


def _proved(rok: int, akce) -> Prehled:
    with sezeni()() as s:
        try:
            akce(s, _profil())
        except majetek.ChybaMajetku as e:
            s.rollback()
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from e
        s.commit()
    return _prehled(rok)


Rok = Query(default_factory=lambda: date.today().year)


@router.get("/{rok}")
def prehled(rok: int, _: Prihlaseny) -> Prehled:
    return _prehled(rok)


@router.post("")
def zarad(k: NovaKarta, uzivatel: Zapisujici, rok: int = Rok) -> Prehled:
    return _proved(
        rok,
        lambda s, prof: majetek.zarad(
            s,
            prof,
            nazev=k.nazev,
            druh=k.druh,
            zarazeno=k.zarazeno,
            cena=k.cena,
            doba_mesicu=k.doba_mesicu,
            kryti_kod=k.kryti,
            inventarni_cislo=k.inventarni_cislo,
            poznamka=k.poznamka,
            prevzato_k=k.prevzato_k,
            opravky_prevzate=k.opravky_prevzate,
            zauctoval=uzivatel.email,
        ),
    )


@router.put("/{majetek_id}")
def uprav(majetek_id: int, p: Popis, uzivatel: Zapisujici, rok: int = Rok) -> Prehled:
    return _proved(
        rok,
        lambda s, prof: majetek.uprav(
            s,
            majetek_id,
            nazev=p.nazev,
            inventarni_cislo=p.inventarni_cislo,
            poznamka=p.poznamka,
            upravil=uzivatel.email,
        ),
    )


@router.delete("/{majetek_id}")
def smaz(majetek_id: int, _: Zapisujici, rok: int = Rok) -> Prehled:
    return _proved(rok, lambda s, prof: majetek.smaz_prevzaty(s, majetek_id))


@router.post("/odpisy/{rok_odpisu}")
def odpisy(rok_odpisu: int, uzivatel: Zapisujici) -> Prehled:
    return _proved(
        rok_odpisu,
        lambda s, prof: majetek.zauctuj_odpisy(
            s, prof, rok_odpisu, zauctoval=uzivatel.email, dnes=date.today()
        ),
    )


@router.post("/{majetek_id}/vyrazeni")
def vyrad(majetek_id: int, v: Vyrazeni, uzivatel: Zapisujici, rok: int = Rok) -> Prehled:
    return _proved(
        rok,
        lambda s, prof: majetek.vyrad(
            s, prof, majetek_id, datum=v.datum, duvod=v.duvod, zauctoval=uzivatel.email
        ),
    )
