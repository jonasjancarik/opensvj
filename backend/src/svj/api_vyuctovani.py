"""API pro roční vyúčtování záloh na správu domu."""

from datetime import date

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from . import podily, predpisy, vlastnicka_obdobi, vyuctovani_spravy, zasilky
from .api_lide import Adresat, adresati, adresati_osob
from .db import BankovniUcet, sezeni
from .domena import profil
from .nastaveni import nastaveni
from .prihlaseni import Prihlaseny, Zapisujici

router = APIRouter(prefix="/api/vyuctovani-spravy")


class Polozka(BaseModel):
    kod: str
    nazev: str
    klic: str
    jak_se_deli: str
    naklady: int  # co ponesou vlastníci (náklady snížené o související výnosy)
    vynosy: int  # výnosy, o které se náklady snížily
    zalohy: int


class PolozkaJednotky(BaseModel):
    kod: str
    naklady: int
    zalohy: int


class PolozkaObdobi(BaseModel):
    kod: str
    naklady: int
    zalohy: int


class ObdobiVlastnika(BaseModel):
    """Část vyúčtování jednotky za dobu, kdy ji vlastnil jeden vlastník."""

    od: date
    do: date
    mesice: list[int]  # měsíce, za které platil předpis
    soucasny: bool  # vlastník na konci roku
    osoby: list[int]  # komu se tato část vyúčtování posílá
    vlastnici: list[Adresat]
    zalohy: int
    naklady: int
    rozdil: int  # kladný = nedoplatek
    polozky: list[PolozkaObdobi]


def obdobi_vlastniku(
    s, obdobi: list[vlastnicka_obdobi.Obdobi], kody: list[str], dnes: date
) -> list[ObdobiVlastnika]:
    return [
        ObdobiVlastnika(
            od=o.od,
            do=o.do,
            mesice=o.mesice,
            soucasny=o.soucasny,
            osoby=o.osoby,
            vlastnici=adresati_osob(s, o.osoby, dnes),
            zalohy=sum(o.zalohy.values()),
            naklady=sum(o.naklady.values()),
            rozdil=o.rozdil,
            polozky=[
                PolozkaObdobi(kod=k, naklady=o.naklady.get(k, 0), zalohy=o.zalohy.get(k, 0))
                for k in kody
            ],
        )
        for o in obdobi
    ]


class ObdobiPodilu(BaseModel):
    od_mesice: int
    do_mesice: int
    podil: str  # "543/8600", jak je v prohlášení


class Jednotka(BaseModel):
    jednotka: str
    podil: str  # "543/8600"; když se podíl v roce měnil, průměr za měsíce roku
    # Jen když se podíl během roku měnil: které měsíce platil jaký podíl.
    podily_v_roce: list[ObdobiPodilu]
    # Jen když se vyúčtování dělí na vlastnická období a jednotka v roce změnila vlastníka.
    obdobi: list[ObdobiVlastnika]
    zalohy: int
    naklady: int
    rozdil: int  # kladný = nedoplatek
    polozky: list[PolozkaJednotky]
    vlastnici: list[Adresat]  # k dnešku
    doruceno: date | None  # kdy vlastníkovi došlo vyúčtování


class Nezahrnuto(BaseModel):
    popis: str
    castka: int


class ZDlouhodobych(BaseModel):
    zdroj: str  # fond oprav | záloha na úvěr
    popis: str
    castka: int


class Vyuctovani(BaseModel):
    rok: int
    dnes: date
    svj: str
    ucet: str | None
    splatnost: date
    polozky: list[Polozka]
    jednotky: list[Jednotka]
    nezahrnuto: list[Nezahrnuto]
    z_dlouhodobych: list[ZDlouhodobych]
    zapis: str | None  # "n/rok", když je zaúčtované
    proc_nejde: str | None
    rozeslani: str  # klíč zásilek s tímto vyúčtováním


def _prehled(rok: int) -> Vyuctovani:
    prof = profil.nacti(nastaveni().profil)
    nast = predpisy.nacti_s(prof, sezeni)
    dnes = date.today()
    with sezeni()() as s:
        v = vyuctovani_spravy.spocitej(s, prof, rok)
        pod = podily.nacti(s, prof)
        duvod = vyuctovani_spravy.proc_nejde(s, nast, v, dnes)
        ucet = s.scalar(select(BankovniUcet.cislo).where(BankovniUcet.ucel == "provozni"))
        zapis = f"{v.zapis.poradove_cislo}/{v.zapis.rok}" if v.zapis else None
        kdo = adresati(s, dnes)
        kody = [p.kod for p in v.polozky]
        obdobi = {j.jednotka: obdobi_vlastniku(s, j.obdobi, kody, dnes) for j in v.jednotky}
        doruceno = zasilky.doruceni_jednotek(s, f"vyuctovani_spravy:{rok}")
    return Vyuctovani(
        rok=rok,
        dnes=dnes,
        svj=prof.nazev,
        ucet=ucet,
        splatnost=v.splatnost,
        polozky=[
            Polozka(
                kod=p.kod,
                nazev=p.nazev,
                klic=p.klic,
                jak_se_deli=vyuctovani_spravy.KLICE.get(p.klic, p.klic),
                naklady=p.k_rozdeleni,
                vynosy=p.vynosy,
                zalohy=p.zalohy,
            )
            for p in v.polozky
        ],
        jednotky=[
            Jednotka(
                jednotka=j.jednotka,
                podil=f"{j.podil.numerator}/{j.podil.denominator}",
                podily_v_roce=[
                    ObdobiPodilu(od_mesice=od, do_mesice=do, podil=sada.texty[j.jednotka])
                    for od, do, sada in pod.obdobi_roku(rok)
                ]
                if pod.zmeny_v_roce(rok)
                else [],
                zalohy=sum(j.zalohy.values()),
                naklady=sum(j.naklady.values()),
                rozdil=j.rozdil,
                polozky=[
                    PolozkaJednotky(
                        kod=p.kod, naklady=j.naklady.get(p.kod, 0), zalohy=j.zalohy.get(p.kod, 0)
                    )
                    for p in v.polozky
                ],
                vlastnici=kdo.get(j.jednotka, []),
                doruceno=doruceno.get(j.jednotka),
                obdobi=obdobi[j.jednotka],
            )
            for j in v.jednotky
        ],
        rozeslani=f"vyuctovani_spravy:{rok}",
        nezahrnuto=[Nezahrnuto(popis=n.popis, castka=n.castka) for n in v.nezahrnuto],
        z_dlouhodobych=[
            ZDlouhodobych(zdroj=x.zdroj, popis=x.popis, castka=x.castka) for x in v.z_dlouhodobych
        ],
        zapis=zapis,
        proc_nejde=duvod,
    )


@router.get("/{rok}")
def prehled(rok: int, _: Prihlaseny) -> Vyuctovani:
    return _prehled(rok)


@router.post("/{rok}")
def zauctuj(rok: int, uzivatel: Zapisujici) -> Vyuctovani:
    prof = profil.nacti(nastaveni().profil)
    with sezeni()() as s:
        try:
            vyuctovani_spravy.zauctuj(
                s, prof, predpisy.nacti(prof, s), rok, zauctoval=uzivatel.email
            )
        except vyuctovani_spravy.ChybaVyuctovani as e:
            s.rollback()
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e
        s.commit()
    return _prehled(rok)
