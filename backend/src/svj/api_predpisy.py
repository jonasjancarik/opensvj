"""API pro předpisy záloh a saldo jednotek."""

from datetime import date

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from . import pocatecni, predpisy
from .db import sezeni
from .domena import profil
from .nastaveni import nastaveni
from .prihlaseni import Prihlaseny

router = APIRouter(prefix="/api/predpisy")


class Slozka(BaseModel):
    kod: str
    nazev: str
    klic: str
    sazba: int | None
    skupina: str  # fond_oprav | sprava | sluzby


def _skupina(prof: profil.Profil, role: str) -> str:
    if role.startswith("zalohy_dlouhodobe"):
        return "fond_oprav"
    return "sprava" if prof.je_sprava(role) else "sluzby"


class Dluh(BaseModel):
    popis: str
    castka: int  # kladné = dluží, záporné = přeplatek


class DluhDrivejsiho(Dluh):
    jednotka: str
    vlastnik: str


class Jednotka(BaseModel):
    oznaceni: str
    plocha: int  # setiny m²
    osob: int
    castky: dict[str, int]
    mesicne: int
    pocatek: int
    pocatek_rozpis: list[Dluh]
    predepsano: int
    zaplaceno: int
    saldo: int


class Mesic(BaseModel):
    mesic: int
    nazev: str
    stav: str  # zauctovano | lze | pozdeji | bez_predpisu
    zapis: str | None
    celkem: int


class Predpisy(BaseModel):
    rok: int
    poznamka: str
    splatnost_den: int
    plati_od: date | None
    zdroj: str | None
    slozky: list[Slozka]
    jednotky: list[Jednotka]
    mesice: list[Mesic]
    mesicne_celkem: int
    pocatecni_stavy: bool
    drivejsi_vlastnici: list[DluhDrivejsiho]


def _profil() -> profil.Profil:
    return profil.nacti(nastaveni().profil)


def _prehled(rok: int) -> Predpisy:
    prof = _profil()
    nast = predpisy.nacti(prof)
    dnes = date.today()
    # Ukazujeme předpis platný v aktuálním měsíci; u jiného roku poslední platný v tom roce.
    mesic = dnes.month if dnes.year == rok else 12
    verze = nast.pro_mesic(rok, mesic)
    castky = predpisy.spocitej(prof, verze) if verze else {}
    with sezeni()() as s:
        saldo = {x.jednotka: x for x in predpisy.saldo(s, prof, rok)}
        drivejsi = predpisy.drivejsi_vlastnici(s, rok)
        pocatek = pocatecni.nacti(s, prof, rok)
        zapisy = predpisy.zauctovane_mesice(s, rok)
        dalsi = predpisy.dalsi_k_zauctovani(s, nast, rok)
    mesice = []
    for m in range(1, 13):
        celkem = sum(predpisy.mesicni_celkem(prof, nast, rok, m).values())
        z = zapisy.get(m)
        if z:
            stav = "zauctovano"
        elif not celkem:
            stav = "bez_predpisu"
        elif m == dalsi and date(rok, m, 1) <= dnes:
            stav = "lze"
        else:
            stav = "pozdeji"
        mesice.append(
            Mesic(
                mesic=m,
                nazev=predpisy.MESICE[m - 1],
                stav=stav,
                zapis=f"{z.poradove_cislo}/{z.rok}" if z else None,
                celkem=celkem,
            )
        )
    jednotky = []
    for j in prof.udaje_jednotek:
        c = castky.get(j.oznaceni, {})
        sj = saldo[j.oznaceni]
        jednotky.append(
            Jednotka(
                oznaceni=j.oznaceni,
                plocha=j.plocha,
                osob=predpisy.osob(verze, j.oznaceni) if verze else 0,
                castky=c,
                mesicne=sum(c.values()),
                pocatek=sj.pocatek,
                pocatek_rozpis=[
                    Dluh(popis=p.popis, castka=p.castka)
                    for p in (pocatek.polozky if pocatek else [])
                    if p.jednotka == j.oznaceni and not p.drivejsi_vlastnik
                ],
                predepsano=sj.predepsano,
                zaplaceno=sj.zaplaceno,
                saldo=sj.saldo,
            )
        )
    return Predpisy(
        rok=rok,
        poznamka=nast.poznamka,
        splatnost_den=nast.splatnost_den,
        plati_od=verze.plati_od if verze else None,
        zdroj=verze.zdroj if verze else None,
        slozky=[
            Slozka(
                kod=x.kod, nazev=x.nazev, klic=x.klic, sazba=x.sazba, skupina=_skupina(prof, x.role)
            )
            for x in verze.slozky
        ]
        if verze
        else [],
        jednotky=jednotky,
        mesice=mesice,
        mesicne_celkem=sum(j.mesicne for j in jednotky),
        pocatecni_stavy=pocatek is not None,
        drivejsi_vlastnici=[
            DluhDrivejsiho(jednotka=d.jednotka, vlastnik=d.vlastnik, popis=d.popis, castka=d.castka)
            for d in sorted(drivejsi, key=lambda d: prof.jednotky.index(d.jednotka))
        ],
    )


@router.get("/{rok}")
def prehled(rok: int, _: Prihlaseny) -> Predpisy:
    return _prehled(rok)


@router.post("/{rok}/{mesic}")
def vygeneruj(rok: int, mesic: int, uzivatel: Prihlaseny) -> Predpisy:
    if not 1 <= mesic <= 12:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Neplatný měsíc.")
    prof = _profil()
    with sezeni()() as s:
        try:
            predpisy.vygeneruj(s, prof, predpisy.nacti(prof), rok, mesic, zauctoval=uzivatel.email)
        except predpisy.ChybaPredpisu as e:
            s.rollback()
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e
        s.commit()
    return _prehled(rok)
