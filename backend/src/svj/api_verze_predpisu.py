"""API pro úpravu předpisu záloh v aplikaci: verze s platností od, složky, sazby a částky."""

from datetime import date

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from . import predpisy
from .api_predpisy import _skupina
from .db import sezeni
from .domena import profil
from .nastaveni import nastaveni
from .prihlaseni import Prihlaseny, Zapisujici

router = APIRouter(prefix="/api/verze-predpisu")

KLICE = {
    "plocha": "sazba za m² podlahové plochy",
    "osoby": "sazba za osobu",
    "pevna": "částka zadaná u každé jednotky",
    "podil": "měsíční částka za dům, dělí se podle podílů",
    "jednotka": "měsíční částka za dům, každá jednotka stejně",
}
NAZVY_FONDU = {
    "zalohy_dlouhodobe": "Fond oprav",
    "zalohy_dlouhodobe_mimoradne": "Mimořádné zálohy do fondu oprav",
    "zalohy_dlouhodobe_uver": "Zálohy na splátky úvěru",
}


class Slozka(BaseModel):
    kod: str = Field(min_length=1, max_length=32, pattern=r"^[A-Z0-9_]+$")
    nazev: str = Field(min_length=1, max_length=100)
    role: str = Field(max_length=64)
    klic: str
    sazba: int | None = Field(default=None, ge=0)


class Verze(BaseModel):
    plati_od: date
    zdroj: str = Field(default="", max_length=200)
    slozky: list[Slozka] = Field(min_length=1, max_length=50)
    pevne: dict[str, dict[str, int]] = Field(default_factory=dict)
    osoby: dict[str, int] = Field(default_factory=dict)


class VerzeVPrehledu(Verze):
    v_aplikaci: bool
    upravitelna: bool
    upravil: str
    mesicne: dict[str, int]  # jednotka → měsíčně celkem


class Role(BaseModel):
    role: str
    nazev: str
    skupina: str  # fond_oprav | sprava | sluzby


class Klic(BaseModel):
    kod: str
    popis: str


class JednotkaDomu(BaseModel):
    oznaceni: str
    plocha: int  # setiny m²
    podil: str


class Prehled(BaseModel):
    dnes: date
    prvni_mesic: date  # nejdřívější možné „platí od“ nové nebo upravené verze
    splatnost_den: int
    jednotky: list[JednotkaDomu]
    role: list[Role]
    klice: list[Klic]
    verze: list[VerzeVPrehledu]


class Ulozeni(BaseModel):
    puvodni: date | None  # datum upravované verze; None = nová
    verze: Verze


class Nahled(BaseModel):
    mesicne: dict[str, int]
    chyba: str | None


def _profil() -> profil.Profil:
    return profil.nacti(nastaveni().profil)


def _role(prof: profil.Profil) -> list[Role]:
    vysledek = [
        Role(role=r, nazev=NAZVY_FONDU.get(r, r), skupina="fond_oprav")
        for r in prof.role
        if r.startswith("zalohy_dlouhodobe") and not r.endswith(".*")
    ]
    for zaklad in ("zalohy_sprava", "zalohy_sluzby"):
        vysledek += [
            Role(
                role=f"{zaklad}.{kod}",
                nazev=u.get("nazev", kod),
                skupina=_skupina(prof, f"{zaklad}.{kod}"),
            )
            for kod, u in prof.polozky(zaklad).items()
        ]
    return vysledek


def _do_domeny(v: Verze) -> predpisy.Verze:
    return predpisy.Verze(
        plati_od=v.plati_od,
        zdroj=v.zdroj,
        slozky=[predpisy.Slozka(**x.model_dump()) for x in v.slozky],
        pevne=v.pevne,
        osoby=v.osoby,
    )


def _mesicne(prof: profil.Profil, v: predpisy.Verze) -> dict[str, int]:
    return {j: sum(c.values()) for j, c in predpisy.spocitej(prof, v).items()}


def _prehled() -> Prehled:
    prof = _profil()
    with sezeni()() as s:
        nast = predpisy.nacti(prof, s)
        od = predpisy.prvni_mesic_ke_zmene(s)
    return Prehled(
        dnes=date.today(),
        prvni_mesic=od,
        splatnost_den=nast.splatnost_den,
        jednotky=[
            JednotkaDomu(
                oznaceni=j.oznaceni,
                plocha=j.plocha,
                podil=f"{j.podil.numerator}/{j.podil.denominator}",
            )
            for j in prof.udaje_jednotek
        ],
        role=_role(prof),
        klice=[Klic(kod=k, popis=p) for k, p in KLICE.items()],
        verze=[
            VerzeVPrehledu(
                plati_od=v.plati_od,
                zdroj=v.zdroj,
                slozky=[Slozka(**vars(x)) for x in v.slozky],
                pevne=v.pevne,
                osoby=v.osoby,
                v_aplikaci=v.v_aplikaci,
                upravitelna=v.v_aplikaci and v.plati_od >= od,
                upravil=v.upravil,
                mesicne=_mesicne(prof, v),
            )
            for v in nast.verze
        ],
    )


@router.get("")
def prehled(_: Prihlaseny) -> Prehled:
    return _prehled()


@router.post("/nahled")
def nahled(v: Verze, _: Prihlaseny) -> Nahled:
    """Měsíční předpis jednotek podle rozpracované verze, bez uložení."""
    prof = _profil()
    d = _do_domeny(v)
    try:
        predpisy.zkontroluj(prof, d)
        return Nahled(mesicne=_mesicne(prof, d), chyba=None)
    except (predpisy.ChybaPredpisu, KeyError) as e:
        return Nahled(mesicne={}, chyba=str(e).strip("'\""))


@router.put("")
def uloz(z: Ulozeni, uzivatel: Zapisujici) -> Prehled:
    prof = _profil()
    with sezeni()() as s:
        try:
            predpisy.uloz_verzi(s, prof, _do_domeny(z.verze), uzivatel.email, z.puvodni)
        except (predpisy.ChybaPredpisu, KeyError) as e:
            s.rollback()
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e).strip("'\"")) from e
        s.commit()
    return _prehled()


@router.delete("/{plati_od}")
def smaz(plati_od: date, _: Zapisujici) -> Prehled:
    with sezeni()() as s:
        try:
            predpisy.smaz_verzi(s, plati_od)
        except predpisy.ChybaPredpisu as e:
            s.rollback()
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from e
        s.commit()
    return _prehled()
