"""Roční vyúčtování záloh na správu domu (pojištění, správce, revize, drobné opravy).

Náklady roku označené položkou správy se rozdělí na jednotky podle klíče z profilu (podíl
na společných částech, nebo rovným dílem) a porovnají se s předepsanými zálohami jednotky
na tutéž položku. Rozdíl je nedoplatek nebo přeplatek. Služby se vyúčtovávají zvlášť.

Výnosy označené položkou správy (pojistné plnění na opravu, dotace na úroky, bankovní úroky
na poplatky) náklady té položky snižují: vlastníci nesou jen to, co výnosy nepokryly
(Durec s. 55–61, souhrnné příklady 1 a 2).
"""

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from fractions import Fraction

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from . import denik, podily, predpisy, vlastnicka_obdobi
from .db import RadekZapisu, Zapis
from .domena import katalog
from .domena.penize import na_text
from .domena.profil import Profil
from .domena.rozdeleni import rozdel

OPERACE = "vyuctovani-spravy"
# Zápisy, jejichž výnosy s položkou správy nejsou skutečné výnosy SVJ, ale technika vyúčtování.
TECHNICKE = (OPERACE, "prevod-spravnich-nakladu")
KLICE = {"podil": "podle podílů na společných částech", "jednotka": "každá jednotka stejně"}
# Náklady bez položky správy, které se do vyúčtování nezahrnou: jak je ukázat lidem.
NAZVY_NAKLADU = {
    "naklady.banka": "Bankovní poplatky",
    "naklady.dan_srazkova": "Srážková daň z úroků",
    "naklady.dan_z_prijmu": "Daň z příjmů bez určené položky",
    "naklady.prevod_do_fo": "Převod výnosů do fondu oprav",
    "naklady.opravy": "Opravy bez určené položky",
    "naklady.sprava": "Správa bez určené položky",
    "naklady.pojisteni": "Pojištění bez určené položky",
    "naklady.ostatni": "Ostatní náklady bez určené položky",
}


class ChybaVyuctovani(ValueError):
    pass


@dataclass
class Polozka:
    kod: str
    nazev: str
    klic: str  # podil | jednotka
    naklady: int = 0  # náklady třídy 5
    vynosy: int = 0  # výnosy, které náklady položky snižují
    zalohy: int = 0

    @property
    def k_rozdeleni(self) -> int:
        """Co ponesou vlastníci: náklady snížené o související výnosy."""
        return self.naklady - self.vynosy


@dataclass
class Jednotka:
    jednotka: str
    podil: Fraction
    zalohy: dict[str, int] = field(default_factory=dict)
    naklady: dict[str, int] = field(default_factory=dict)
    # Jen když se vyúčtování dělí na vlastnická období a jednotka v roce změnila vlastníka.
    obdobi: list[vlastnicka_obdobi.Obdobi] = field(default_factory=list)

    @property
    def rozdil(self) -> int:
        """Kladný = nedoplatek, záporný = přeplatek."""
        return sum(self.naklady.values()) - sum(self.zalohy.values())


@dataclass
class Nezahrnuto:
    popis: str
    castka: int


@dataclass
class Vyuctovani:
    rok: int
    polozky: list[Polozka]
    jednotky: list[Jednotka]
    nezahrnuto: list[Nezahrnuto]
    zapis: Zapis | None

    @property
    def splatnost(self) -> date:
        return splatnost(self.rok)


def splatnost(rok: int) -> date:
    """Stanovy lhůtu neurčují; bereme stejnou jako u služeb (vyrovnání do 4 měsíců,
    § 7 zákona 67/2013), počítanou od konce roku. Výbor ji může určit jinak."""
    return date(rok + 1, 4, 30)


def klic(rok: int) -> str:
    return f"{OPERACE}:{rok}"


def spocitej(session: Session, profil: Profil, rok: int) -> Vyuctovani:
    polozky = {
        kod: Polozka(kod, u.get("nazev", kod), u.get("klic", "podil"))
        for kod, u in profil.sprava.items()
    }
    zapis = denik.aktivni(session, klic(rok))
    v_roce = (Zapis.rok == rok, denik.platny())

    md_minus_d = func.sum(
        case((RadekZapisu.strana == "md", RadekZapisu.castka), else_=-RadekZapisu.castka)
    )
    naklady = session.execute(
        select(RadekZapisu.sluzba, RadekZapisu.role, md_minus_d)
        .join(Zapis)
        .where(*v_roce, RadekZapisu.ucet.like("5%"))
        .group_by(RadekZapisu.sluzba, RadekZapisu.role)
    ).all()
    vynosy = session.execute(
        select(RadekZapisu.sluzba, -md_minus_d)
        .join(Zapis)
        .where(
            *v_roce,
            RadekZapisu.ucet.like("6%"),
            RadekZapisu.sluzba.in_(list(polozky)),
            Zapis.operace.not_in(TECHNICKE),
        )
        .group_by(RadekZapisu.sluzba)
    ).all()
    for sluzba, castka in vynosy:
        polozky[sluzba].vynosy += int(castka)
    nezahrnuto: dict[str, int] = {}
    for sluzba, role, castka in naklady:
        if sluzba in polozky:
            polozky[sluzba].naklady += int(castka)
        elif castka:
            popis = NAZVY_NAKLADU.get(role, role)
            nezahrnuto[popis] = nezahrnuto.get(popis, 0) + int(castka)

    # Zálohy = předepsané (D) minus případné opravy (MD), bez samotného vyúčtování. Hledají se
    # podle účtu, ne role: dřívější zápisy vedly tytéž zálohy pod rolí služby.
    ucty_zaloh = {profil.ucet(f"zalohy_sprava.{kod}") for kod in polozky}
    mesic = func.extract("month", Zapis.datum)
    zalohy = session.execute(
        select(RadekZapisu.jednotka, RadekZapisu.sluzba, mesic, -md_minus_d)
        .join(Zapis)
        .where(
            *v_roce,
            RadekZapisu.ucet.in_(ucty_zaloh),
            RadekZapisu.jednotka.is_not(None),
            Zapis.operace != OPERACE,
        )
        .group_by(RadekZapisu.jednotka, RadekZapisu.sluzba, mesic)
    ).all()
    # Podíl za rok: průměr podílů za měsíce, stejně jako se z nich počítaly zálohy.
    pod = podily.nacti(session, profil)
    za_rok = pod.v_roce(rok)
    jednotky = {j: Jednotka(j, za_rok[j]) for j in profil.jednotky}
    zalohy_mesicu: dict[str, dict[tuple[str, int], int]] = {}
    for jednotka, sluzba, m, castka in zalohy:
        if jednotka in jednotky and sluzba in polozky and castka:
            u = jednotky[jednotka]
            u.zalohy[sluzba] = u.zalohy.get(sluzba, 0) + int(castka)
            polozky[sluzba].zalohy += int(castka)
            zalohy_mesicu.setdefault(jednotka, {})[(sluzba, int(m))] = int(castka)
    for u in jednotky.values():  # opravy záloh v jiném měsíci je mohou v součtu vynulovat
        u.zalohy = {k: c for k, c in u.zalohy.items() if c}

    rozpocitej(polozky.values(), jednotky)
    if profil.vyuctovani_pri_prevodu == vlastnicka_obdobi.PO_OBDOBICH:
        klice = {p.kod: p.klic for p in polozky.values()}
        for j, obdobi in vlastnicka_obdobi.obdobi(session, profil, rok).items():

            def vahy(kod: str, j: str = j) -> list[Fraction | int]:
                if klice.get(kod) == "podil":
                    return [pod.k_mesici(rok, m).podily[j] for m in range(1, 13)]
                return [1] * 12

            vlastnicka_obdobi.rozdel_jednotku(
                obdobi, jednotky[j].naklady, zalohy_mesicu.get(j, {}), vahy
            )
            jednotky[j].obdobi = obdobi
    return Vyuctovani(
        rok=rok,
        polozky=list(polozky.values()),
        jednotky=list(jednotky.values()),
        nezahrnuto=[Nezahrnuto(p, c) for p, c in sorted(nezahrnuto.items())],
        zapis=zapis,
    )


def rozpocitej(polozky: Iterable[Polozka], jednotky: dict[str, Jednotka]) -> None:
    """Rozdělí náklady položek (po odečtení výnosů) na jednotky podle klíče položky."""
    for p in polozky:
        if p.klic == "jednotka":
            vahy: dict[str, Fraction | int] = dict.fromkeys(jednotky, 1)
        else:
            vahy = {j: x.podil for j, x in jednotky.items()}
        if p.k_rozdeleni:
            for j, castka in rozdel(p.k_rozdeleni, vahy).items():
                jednotky[j].naklady[p.kod] = castka


def proc_nejde(
    session: Session, nastaveni: predpisy.Nastaveni, v: Vyuctovani, dnes: date
) -> str | None:
    """Důvod, proč vyúčtování ještě nejde zaúčtovat (None = jde)."""
    if v.zapis is not None:
        return None
    if dnes < date(v.rok, 12, 31):
        return f"Vyúčtování půjde zaúčtovat od 31. 12. {v.rok}, až budou známé náklady celého roku."
    chybi = predpisy.dalsi_k_zauctovani(session, nastaveni, v.rok)
    if chybi is not None:
        mesic = predpisy.MESICE[chybi - 1]
        return f"Nejdřív zaúčtujte předpis záloh za {mesic} {v.rok} na stránce Předpisy."
    if not any(p.naklady or p.vynosy or p.zalohy for p in v.polozky):
        return f"Za rok {v.rok} nejsou žádné náklady ani zálohy na správu."
    return None


def zauctuj(
    session: Session,
    profil: Profil,
    nastaveni: predpisy.Nastaveni,
    rok: int,
    *,
    zauctoval: str,
    dnes: date | None = None,
) -> Zapis:
    v = spocitej(session, profil, rok)
    if v.zapis is not None:
        return v.zapis
    duvod = proc_nejde(session, nastaveni, v, dnes or date.today())
    if duvod:
        raise ChybaVyuctovani(duvod)
    vstupy = {
        "zalohy": [
            {"jednotka": j.jednotka, "sluzba": kod, "castka": na_text(c)}
            for j in v.jednotky
            for kod, c in j.zalohy.items()
        ],
        "naklady": [{"sluzba": p.kod, "castka": na_text(p.k_rozdeleni)} for p in v.polozky],
        "vysledky": [
            x
            for j in v.jednotky
            for x in vlastnicka_obdobi.vysledky(j.jednotka, j.rozdil, j.obdobi)
        ],
    }
    try:
        return denik.zauctuj(
            session,
            profil,
            katalog.nacti()[OPERACE],
            vstupy,
            datum=date(rok, 12, 31),
            popis=f"Vyúčtování záloh na správu domu {rok}",
            doklad=f"VY S {rok}",
            zauctoval=zauctoval,
            idempotencni_klic=klic(rok),
        )
    except denik.ChybaUctovani as e:
        raise ChybaVyuctovani(str(e)) from e
