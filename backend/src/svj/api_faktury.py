"""API pro přijaté faktury."""

from datetime import date

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from . import faktury, fond_ze_zisku, majetek, uvery
from .db import sezeni
from .domena import profil
from .nastaveni import nastaveni
from .prihlaseni import Prihlaseny, Zapisujici

router = APIRouter(prefix="/api/faktury")


class Druh(BaseModel):
    id: str
    nazev: str
    skupina: str


class Faktura(BaseModel):
    cislo: str
    dodavatel: str
    ico: str | None
    ucet_dodavatele: str | None
    cislo_dodavatele: str | None
    vs: str | None
    vystaveno: date | None
    duzp: date
    splatnost: date
    castka: int
    uhrazeno: int
    zbyva: int
    stav: str  # k_uhrade | castecne | po_splatnosti | uhrazena | stornovana
    druh: str
    nazev_druhu: str
    popis: str
    rozhodnuti: str | None
    zapis: str
    zadal: str


class Faktury(BaseModel):
    rok: int
    druhy: list[Druh]
    dodavatele: list[str]  # pro našeptávání
    faktury: list[Faktura]
    k_uhrade: int


class NovaFaktura(BaseModel):
    dodavatel: str = Field(max_length=128)
    castka: int
    duzp: date
    splatnost: date
    druh: str
    popis: str = Field(default="", max_length=500)
    cislo_dodavatele: str | None = Field(default=None, max_length=40)
    vs: str | None = Field(default=None, max_length=10)
    ico: str | None = Field(default=None, max_length=10)
    ucet_dodavatele: str | None = Field(default=None, max_length=40)
    vystaveno: date | None = None
    rozhodnuti: str | None = Field(default=None, max_length=200)


def model(x: faktury.StavFaktury) -> Faktura:
    f = x.faktura
    return Faktura(
        cislo=f.cislo,
        dodavatel=f.dodavatel,
        ico=f.ico,
        ucet_dodavatele=f.ucet_dodavatele,
        cislo_dodavatele=f.cislo_dodavatele,
        vs=f.vs,
        vystaveno=f.vystaveno,
        duzp=f.duzp,
        splatnost=f.splatnost,
        castka=f.castka,
        uhrazeno=x.uhrazeno if not x.stornovana else 0,
        zbyva=x.zbyva,
        stav=x.stav(),
        druh=f.druh,
        nazev_druhu=faktury.DRUHY[f.druh].nazev if f.druh in faktury.DRUHY else f.druh,
        popis=f.popis,
        rozhodnuti=f.rozhodnuti,
        zapis=f"{f.zapis.poradove_cislo}/{f.zapis.rok}",
        zadal=f.zadal,
    )


def _nabizet(kod: str, d: faktury.Druh, prof: profil.Profil) -> bool:
    """Druhy pro úvěr, fond ze zisku a majetek jen u SVJ, které pro ně má v nastavení účty."""
    if kod == "UVER":
        return uvery.nastaveno(prof)
    if kod == "FOND_ZE_ZISKU":
        return fond_ze_zisku.nastaveno(prof) and "vynosy.cerpani_fondu" in prof.role
    porizovani = d.vstupy.get("porizovani")
    if porizovani:
        return porizovani in prof.role and majetek.druhy(prof) != {}
    return True


def _prehled(rok: int) -> Faktury:
    prof = profil.nacti(nastaveni().profil)
    with sezeni()() as s:
        vse = faktury.prehled(s)
    roku = [x for x in vse if x.faktura.rok == rok or (x.zbyva > 0 and not x.stornovana)]
    return Faktury(
        rok=rok,
        druhy=[
            Druh(id=k, nazev=d.nazev, skupina=d.skupina)
            for k, d in faktury.DRUHY.items()
            if _nabizet(k, d, prof)
        ],
        dodavatele=sorted({x.faktura.dodavatel for x in vse}, key=str.lower),
        faktury=[model(x) for x in roku],
        k_uhrade=sum(x.zbyva for x in vse if not x.stornovana and x.zbyva > 0),
    )


@router.get("/{rok}")
def prehled(rok: int, _: Prihlaseny) -> Faktury:
    return _prehled(rok)


@router.post("")
def zadej(nova: NovaFaktura, uzivatel: Zapisujici) -> Faktury:
    prof = profil.nacti(nastaveni().profil)
    with sezeni()() as s:
        try:
            f = faktury.zauctuj(
                s,
                prof,
                faktury.NovaFaktura(
                    dodavatel=nova.dodavatel,
                    castka=nova.castka,
                    duzp=nova.duzp,
                    splatnost=nova.splatnost,
                    druh=nova.druh,
                    popis=nova.popis,
                    cislo_dodavatele=(nova.cislo_dodavatele or "").strip() or None,
                    vs=(nova.vs or "").strip() or None,
                    ico=(nova.ico or "").strip() or None,
                    ucet_dodavatele=(nova.ucet_dodavatele or "").strip() or None,
                    vystaveno=nova.vystaveno,
                    rozhodnuti=nova.rozhodnuti,
                ),
                zadal=uzivatel.email,
            )
        except faktury.ChybaFaktury as e:
            s.rollback()
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e
        rok = f.rok
        s.commit()
    return _prehled(rok)
