"""API pro úvěry SVJ splácené vlastníky podle podílů."""

from datetime import date

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from . import denik, faktury, mimoradne_zalohy, predpisy, rozhodnuti, uvery
from .db import Uver, sezeni
from .domena import profil
from .nastaveni import nastaveni
from .prihlaseni import Prihlaseny, Zapisujici

router = APIRouter(prefix="/api/uvery")


class RozhodnutiVen(BaseModel):
    id: int
    datum: date
    popis: str


class FakturaVen(BaseModel):
    cislo: str
    dodavatel: str
    zbyva: int


class JednotkaVen(BaseModel):
    jednotka: str
    podil: int  # podíl na jistině
    mesicne: int  # měsíční splátka
    zbyva: int  # nesplaceno


class UverVen(BaseModel):
    id: int
    nazev: str
    cislo_uctu: str
    jistina: int
    rozhodnuti: str
    predepsano_dne: date
    prvni_splatka: date
    posledni_splatka: date
    pocet_splatek: int
    uroky_hradi: str  # fond_oprav | zaloha_na_uver | kód položky správy
    platny: bool  # předpis podílů není stornovaný
    zapis: str | None  # předpis podílů "n/rok"
    zbyva_bance: int
    nesplaceno: int
    uroky: int  # úroky vybraného roku
    kryto: int  # z nich pokryto z dlouhodobých záloh
    jednotky: list[JednotkaVen]


class Prehled(BaseModel):
    rok: int
    dnes: date
    nastaveno: bool
    rozhodnuti: list[RozhodnutiVen]
    polozky_spravy: dict[str, str]
    faktury: list[FakturaVen]  # nezaplacené
    na_ceste: int  # peníze na cestě k dnešku
    nevycerpano: int  # zálohy na úvěry, ze kterých se ještě neplatilo
    prvni_mozna_splatka: date  # první měsíc, jehož předpis ještě není zaúčtovaný
    uvery: list[UverVen]


class Nahled(BaseModel):
    jistina: int = Field(gt=0)
    predepsano_dne: date
    pocet_splatek: int = Field(ge=1, le=uvery.NEJVIC_SPLATEK)


class CastJednotky(BaseModel):
    podil: int
    mesicne: int


class NovyUver(Nahled):
    nazev: str = Field(max_length=150)
    cislo_uctu: str = Field(default="", max_length=64)
    rozhodnuti_id: int
    prvni_splatka: date
    uroky_hradi: str = Field(max_length=32)


class UhradaFaktury(BaseModel):
    faktura: str
    castka: int = Field(gt=0)
    datum: date


class Uroky(BaseModel):
    uroky: int = Field(ge=0)
    poplatky: int = Field(ge=0)
    datum: date
    sluzba_poplatku: str = ""


class Splatka(BaseModel):
    castka: int = Field(gt=0)
    datum: date


def _profil() -> profil.Profil:
    return profil.nacti(nastaveni().profil)


def _ven(s, prof: profil.Profil, u: Uver, rok: int) -> UverVen:
    st = uvery.stav(s, prof, u, rok)
    z = u.zapis
    return UverVen(
        id=u.id,
        nazev=u.nazev,
        cislo_uctu=u.cislo_uctu,
        jistina=u.jistina,
        rozhodnuti=st.rozhodnuti,
        predepsano_dne=u.predepsano_dne,
        prvni_splatka=u.prvni_splatka,
        posledni_splatka=st.posledni_splatka,
        pocet_splatek=u.pocet_splatek,
        uroky_hradi=u.uroky_hradi,
        platny=u.platny,
        zapis=f"{z.poradove_cislo}/{z.rok}" if z else None,
        zbyva_bance=st.zbyva_bance,
        nesplaceno=st.nesplaceno,
        uroky=st.uroky,
        kryto=st.kryto,
        jednotky=[
            JednotkaVen(jednotka=j.jednotka, podil=j.podil, mesicne=j.mesicne, zbyva=j.zbyva)
            for j in st.jednotky
        ],
    )


def _prehled(rok: int) -> Prehled:
    prof = _profil()
    dnes = date.today()
    with sezeni()() as s:
        na_ceste = (
            denik.zustatky(s, dnes.year, dnes).get(prof.ucet("penize_na_ceste"), 0)
            if "penize_na_ceste" in prof.role
            else 0
        )
        return Prehled(
            rok=rok,
            dnes=dnes,
            nastaveno=uvery.nastaveno(prof),
            rozhodnuti=[
                RozhodnutiVen(id=r.id, datum=r.datum, popis=rozhodnuti.popis(r))
                for r in mimoradne_zalohy.rozhodnuti_shromazdeni(s)
            ],
            polozky_spravy={k: u.get("nazev", k) for k, u in prof.sprava.items()},
            faktury=[
                FakturaVen(cislo=f.faktura.cislo, dodavatel=f.faktura.dodavatel, zbyva=f.zbyva)
                for f in faktury.prehled(s, jen_otevrene=True)
            ],
            na_ceste=na_ceste,
            nevycerpano=uvery.nevycerpana_zaloha(s, prof) if uvery.nastaveno(prof) else 0,
            prvni_mozna_splatka=max(
                predpisy.prvni_mesic_ke_zmene(s), date(dnes.year, dnes.month, 1)
            ),
            uvery=[_ven(s, prof, u, rok) for u in uvery.uvery(s)],
        )


def _proved(rok: int, akce) -> Prehled:
    with sezeni()() as s:
        try:
            akce(s, _profil())
        except uvery.ChybaUveru as e:
            s.rollback()
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from e
        s.commit()
    return _prehled(rok)


Rok = Query(default_factory=lambda: date.today().year)


@router.get("/{rok}")
def prehled(rok: int, _: Prihlaseny) -> Prehled:
    return _prehled(rok)


@router.post("/nahled")
def nahled(n: Nahled, _: Prihlaseny) -> dict[str, CastJednotky]:
    """Jak se jistina rozdělí na jednotky a kolik bude každá měsíčně splácet."""
    with sezeni()() as s:
        try:
            casti = uvery.rozdel_jistinu(s, _profil(), n.jistina, n.predepsano_dne)
        except uvery.ChybaUveru as e:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from e
    plan = predpisy.SplaceniUveru("", "", n.predepsano_dne, n.pocet_splatek, casti)
    return {j: CastJednotky(podil=c, mesicne=plan.mesicne(j)) for j, c in casti.items()}


@router.post("")
def zaloz(n: NovyUver, uzivatel: Zapisujici, rok: int = Rok) -> Prehled:
    return _proved(
        rok,
        lambda s, prof: uvery.zaloz(
            s,
            prof,
            nazev=n.nazev,
            cislo_uctu=n.cislo_uctu,
            jistina=n.jistina,
            rozhodnuti_id=n.rozhodnuti_id,
            predepsano_dne=n.predepsano_dne,
            prvni_splatka=n.prvni_splatka,
            pocet_splatek=n.pocet_splatek,
            uroky_hradi=n.uroky_hradi,
            zauctoval=uzivatel.email,
        ),
    )


@router.post("/{uver_id}/faktura")
def uhrada_faktury(uver_id: int, f: UhradaFaktury, uzivatel: Zapisujici, rok: int = Rok) -> Prehled:
    return _proved(
        rok,
        lambda s, prof: uvery.uhrada_faktury(
            s,
            prof,
            uver_id,
            faktura=f.faktura,
            castka=f.castka,
            datum=f.datum,
            zauctoval=uzivatel.email,
        ),
    )


@router.post("/{uver_id}/uroky")
def uroky(uver_id: int, u: Uroky, uzivatel: Zapisujici, rok: int = Rok) -> Prehled:
    return _proved(
        rok,
        lambda s, prof: uvery.uroky(
            s,
            prof,
            uver_id,
            uroky=u.uroky,
            poplatky=u.poplatky,
            datum=u.datum,
            sluzba_poplatku=u.sluzba_poplatku,
            zauctoval=uzivatel.email,
        ),
    )


@router.post("/{uver_id}/splatka")
def splatka(uver_id: int, p: Splatka, uzivatel: Zapisujici, rok: int = Rok) -> Prehled:
    return _proved(
        rok,
        lambda s, prof: uvery.prichod_splatky(
            s, prof, uver_id, castka=p.castka, datum=p.datum, zauctoval=uzivatel.email
        ),
    )


@router.post("/{uver_id}/kryti/{rok_uroku}")
def kryti(uver_id: int, rok_uroku: int, uzivatel: Zapisujici) -> Prehled:
    return _proved(
        rok_uroku,
        lambda s, prof: uvery.kryti_uroku(
            s, prof, uver_id, rok_uroku, zauctoval=uzivatel.email, dnes=date.today()
        ),
    )
