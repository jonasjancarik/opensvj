"""API pro podíly jednotek na společných částech a jejich změny v čase."""

from datetime import date, datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from . import podily, predpisy
from .db import sezeni
from .domena import profil
from .nastaveni import nastaveni
from .prihlaseni import Prihlaseny, Zapisujici

router = APIRouter(prefix="/api/podily")


class JednotkaPodilu(BaseModel):
    oznaceni: str
    plocha: int  # setiny m²
    podil: str  # platný dnes, jak je v prohlášení ("543/8600")


class Zmena(BaseModel):
    plati_od: date
    od_mesice: date  # od kterého měsíce s ní počítá předpis záloh
    zdroj: str
    podily: dict[str, str]
    upravil: str
    upraveno: datetime | None
    upravitelna: bool  # ještě nejde do zaúčtovaných předpisů


class Prehled(BaseModel):
    dnes: date
    nejdrive_od: date  # nejdřívější měsíc, od kterého může nová změna platit
    jednotky: list[JednotkaPodilu]
    podle_profilu: dict[str, str]  # podíly ze souboru profilu, platí do první změny
    zmeny: list[Zmena]
    predpis_podle_podilu: bool  # předpis má složku, která se dělí podle podílů


class Navrh(BaseModel):
    plati_od: date
    podily: dict[str, str]
    puvodni: date | None = None  # datum upravované změny


class Ulozeni(Navrh):
    zdroj: str = Field("", max_length=200)


class MesicniPredpis(BaseModel):
    dosud: int
    nove: int


class Nahled(BaseModel):
    chyba: str | None
    od_mesice: date
    mesicne: dict[str, MesicniPredpis]  # prázdné, když pro ten měsíc není předpis


def _profil() -> profil.Profil:
    return profil.nacti(nastaveni().profil)


def _prehled() -> Prehled:
    prof = _profil()
    with sezeni()() as s:
        nast = predpisy.nacti(prof, s)
        od = podily.nejdrive_od(s)
    pod = nast.podily or podily.ze_souboru(prof)
    dnes = date.today()
    platne = pod.k_datu(dnes)
    return Prehled(
        dnes=dnes,
        nejdrive_od=od,
        jednotky=[
            JednotkaPodilu(oznaceni=j.oznaceni, plocha=j.plocha, podil=platne.texty[j.oznaceni])
            for j in prof.udaje_jednotek
        ],
        podle_profilu=pod.zakladni.texty,
        zmeny=[
            Zmena(
                plati_od=z.plati_od,
                od_mesice=z.od_mesice,
                zdroj=z.zdroj,
                podily=z.sada.texty,
                upravil=z.upravil,
                upraveno=z.upraveno,
                upravitelna=z.od_mesice >= od,
            )
            for z in reversed(pod.zmeny)
        ],
        predpis_podle_podilu=any(x.klic == "podil" for v in nast.verze for x in v.slozky),
    )


@router.get("")
def prehled(_: Prihlaseny) -> Prehled:
    return _prehled()


@router.post("/nahled")
def nahled(n: Navrh, _: Prihlaseny) -> Nahled:
    """Jak se změní měsíční předpis jednotek v prvním měsíci s novými podíly, bez uložení."""
    prof = _profil()
    od = podily.prvni_mesic(n.plati_od)
    with sezeni()() as s:
        nast = predpisy.nacti(prof, s)
    pod = nast.podily or podily.ze_souboru(prof)
    try:
        nova = podily.zkontroluj_sadu(prof, n.podily)
    except podily.ChybaPodilu as e:
        return Nahled(chyba=str(e), od_mesice=od, mesicne={})
    v = nast.pro_mesic(od.year, od.month)
    if v is None:
        return Nahled(chyba=None, od_mesice=od, mesicne={})
    ostatni = podily.Podily(pod.zakladni, [z for z in pod.zmeny if z.plati_od != n.puvodni])
    dosud = predpisy.spocitej(prof, v, ostatni.k_mesici(od.year, od.month).podily)
    nove = predpisy.spocitej(prof, v, nova.podily)
    return Nahled(
        chyba=None,
        od_mesice=od,
        mesicne={
            j: MesicniPredpis(dosud=sum(dosud[j].values()), nove=sum(nove[j].values()))
            for j in prof.jednotky
        },
    )


@router.put("")
def uloz(z: Ulozeni, uzivatel: Zapisujici) -> Prehled:
    with sezeni()() as s:
        try:
            podily.uloz(s, _profil(), z.plati_od, z.podily, z.zdroj, uzivatel.email, z.puvodni)
        except podily.ChybaPodilu as e:
            s.rollback()
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from e
        s.commit()
    return _prehled()


@router.delete("/{plati_od}")
def smaz(plati_od: date, _: Zapisujici) -> Prehled:
    with sezeni()() as s:
        try:
            podily.smaz(s, plati_od)
        except podily.ChybaPodilu as e:
            s.rollback()
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from e
        s.commit()
    return _prehled()
