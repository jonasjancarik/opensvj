"""Přijaté faktury: zadání se zaúčtováním a stav úhrady.

Faktura se zaúčtuje hned při zadání (zadáním ji člen výboru schvaluje) podle druhu nákladu.
Řádek závazku na účtu dodavatelů nese párovací symbol = interní číslo faktury; stejný
symbol dostane úhrada z banky. Zbývá zaplatit = D − MD na řádcích s tímto symbolem.
"""

import re
from dataclasses import dataclass, replace
from datetime import date

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, selectinload

from . import denik
from .db import Faktura, RadekZapisu, Zapis
from .domena import katalog
from .domena.penize import kc, na_text
from .domena.profil import Profil


class ChybaFaktury(ValueError):
    pass


@dataclass(frozen=True)
class Druh:
    nazev: str
    operace: str
    vstupy: dict[str, str]
    skupina: str


def _sluzba(kod: str, nazev: str) -> Druh:
    return Druh(nazev, "faktura-sluzba", {"sluzba": kod}, "Služby rozúčtované vlastníkům")


def _sprava(kategorie: str, kod: str, nazev: str) -> Druh:
    return Druh(
        nazev,
        "faktura-spravni-naklad",
        {"kategorie": kategorie, "sluzba": kod},
        "Správa domu",
    )


# Na co faktura je: pojmenované tak, jak to vidí výbor, ne podle účtů.
DRUHY: dict[str, Druh] = {
    "TEPLO": _sluzba("TEPLO", "Teplo"),
    "OHREV_TUV": _sluzba("OHREV_TUV", "Ohřev teplé vody"),
    "SV_TUV": _sluzba("SV_TUV", "Studená voda pro teplou vodu"),
    "VODA": _sluzba("VODA", "Vodné a stočné"),
    "ELEKTRINA": _sluzba("ELEKTRINA", "Elektřina společných prostor"),
    "ELEKTRINA_VYTAH": _sluzba("ELEKTRINA_VYTAH", "Elektřina výtahu"),
    "VYTAH": _sluzba("VYTAH", "Provoz a servis výtahu"),
    "UKLID": _sluzba("UKLID", "Úklid"),
    "ODPAD": _sluzba("ODPAD", "Odpad"),
    "ROZUCTOVANI": _sluzba("ROZUCTOVANI", "Rozúčtování (měřiče, ISTA)"),
    "SPRAVA": _sprava("sprava", "SPRAVA", "Správa domu a účetnictví"),
    "POJISTENI": _sprava("pojisteni", "POJISTENI", "Pojištění domu"),
    "DROBNE_OPRAVY": _sprava("opravy", "DROBNE_OPRAVY", "Drobné opravy a údržba"),
    "OSTATNI": _sprava("ostatni", "OSTATNI", "Ostatní (revize, software, právní služby)"),
    "FOND_OPRAV": Druh("Oprava hrazená z fondu oprav", "cerpani-fo", {}, "Fond oprav"),
}


@dataclass
class NovaFaktura:
    dodavatel: str
    castka: int  # haléře
    duzp: date
    splatnost: date
    druh: str
    popis: str = ""
    cislo_dodavatele: str | None = None
    vs: str | None = None
    ico: str | None = None
    ucet_dodavatele: str | None = None
    vystaveno: date | None = None
    rozhodnuti: str | None = None


def _zkontroluj(session: Session, profil: Profil, f: NovaFaktura) -> None:
    if not f.dodavatel.strip():
        raise ChybaFaktury("Chybí dodavatel.")
    if f.castka <= 0:
        raise ChybaFaktury("Částka faktury musí být kladná. Dobropisy aplikace zatím neumí.")
    if f.druh not in DRUHY:
        raise ChybaFaktury("Vyberte, za co faktura je.")
    druh = DRUHY[f.druh]
    if "sluzba" in druh.vstupy and druh.vstupy["sluzba"] not in {**profil.sluzby, **profil.sprava}:
        raise ChybaFaktury(f"SVJ nemá službu „{druh.nazev}“.")
    if f.druh == "FOND_OPRAV" and not (f.rozhodnuti or "").strip():
        raise ChybaFaktury("U opravy z fondu oprav napište, kdo ji schválil (např. výbor 3/2026).")
    if f.vystaveno and f.splatnost < f.vystaveno:
        raise ChybaFaktury("Splatnost je dřív než vystavení faktury.")
    if f.vs and not re.fullmatch(r"\d{1,10}", f.vs):
        raise ChybaFaktury("Variabilní symbol může mít jen číslice (nejvýš 10).")
    if f.ico and not re.fullmatch(r"\d{8}", f.ico):
        raise ChybaFaktury("IČO má 8 číslic.")
    if f.cislo_dodavatele:
        stejna = session.scalar(
            select(Faktura)
            .join(Zapis, Zapis.id == Faktura.zapis_id)
            .where(
                func.lower(Faktura.dodavatel) == f.dodavatel.strip().lower(),
                Faktura.cislo_dodavatele == f.cislo_dodavatele,
                denik.platny(),
            )
        )
        if stejna is not None:
            raise ChybaFaktury(
                f"Fakturu {f.cislo_dodavatele} od dodavatele {stejna.dodavatel} už aplikace má"
                f" (doklad {stejna.cislo})."
            )


def s_parovacim_symbolem(radky: list[katalog.Radek], symbol: str) -> list[katalog.Radek]:
    """Řádkům na účtu dodavatelů doplní párovací symbol (katalog sdílí slovník dimenzí
    mezi stranami MD a D, proto kopie)."""
    return [
        replace(r, dimenze={**r.dimenze, "parovaci_symbol": symbol})
        if r.role == "dodavatele"
        else r
        for r in radky
    ]


def zauctuj(session: Session, profil: Profil, f: NovaFaktura, *, zadal: str) -> Faktura:
    f.dodavatel = " ".join(f.dodavatel.split())
    _zkontroluj(session, profil, f)
    druh = DRUHY[f.druh]
    rok = f.duzp.year
    poradi = (
        session.scalar(select(func.count()).select_from(Faktura).where(Faktura.rok == rok)) or 0
    ) + 1
    cislo = f"{rok}{poradi:03d}"
    operace = katalog.nacti()[druh.operace]
    vstupy = {
        **druh.vstupy,
        "castka": na_text(f.castka),
        "protistrana": f.dodavatel,
        "rozhodnuti": f.rozhodnuti or "",
    }
    radky = s_parovacim_symbolem(katalog.sestav(operace, vstupy), cislo)
    popis = " · ".join(
        x
        for x in (
            druh.nazev,
            f.dodavatel,
            f"faktura {f.cislo_dodavatele}" if f.cislo_dodavatele else "",
            f.popis.strip(),
        )
        if x
    )
    try:
        zapis = denik.zauctuj(
            session,
            profil,
            operace,
            vstupy,
            datum=f.duzp,
            popis=popis,
            doklad=f"FP {cislo}",
            zauctoval=zadal,
            idempotencni_klic=f"faktura:{cislo}",
            radky=radky,
        )
    except denik.ChybaUctovani as e:
        raise ChybaFaktury(str(e)) from e
    faktura = Faktura(
        cislo=cislo,
        rok=rok,
        dodavatel=f.dodavatel,
        ico=f.ico or None,
        ucet_dodavatele=f.ucet_dodavatele or None,
        cislo_dodavatele=f.cislo_dodavatele or None,
        vs=f.vs or None,
        vystaveno=f.vystaveno,
        duzp=f.duzp,
        splatnost=f.splatnost,
        castka=f.castka,
        druh=f.druh,
        popis=f.popis.strip(),
        rozhodnuti=(f.rozhodnuti or "").strip() or None,
        zapis_id=zapis.id,
        zadal=zadal,
    )
    session.add(faktura)
    session.flush()
    return faktura


@dataclass
class StavFaktury:
    faktura: Faktura
    zbyva: int
    stornovana: bool

    @property
    def uhrazeno(self) -> int:
        return self.faktura.castka - self.zbyva

    def stav(self, dnes: date | None = None) -> str:
        if self.stornovana:
            return "stornovana"
        if self.zbyva <= 0:
            return "uhrazena"
        if self.faktura.splatnost < (dnes or date.today()):
            return "po_splatnosti"
        return "castecne" if self.zbyva < self.faktura.castka else "k_uhrade"


def _zbyva(session: Session, symboly: list[str]) -> dict[str, int]:
    if not symboly:
        return {}
    znamenko = func.sum(
        case((RadekZapisu.strana == "d", RadekZapisu.castka), else_=-RadekZapisu.castka)
    )
    radky = session.execute(
        select(RadekZapisu.parovaci_symbol, znamenko)
        .join(Zapis)
        .where(
            RadekZapisu.role == "dodavatele",
            RadekZapisu.parovaci_symbol.in_(symboly),
            denik.platny(),
        )
        .group_by(RadekZapisu.parovaci_symbol)
    )
    return {s: int(z) for s, z in radky}


def prehled(
    session: Session, *, rok: int | None = None, jen_otevrene: bool = False
) -> list[StavFaktury]:
    dotaz = (
        select(Faktura)
        .options(selectinload(Faktura.zapis).selectinload(Zapis.opravy))
        .order_by(Faktura.duzp.desc(), Faktura.cislo.desc())
    )
    if rok is not None:
        dotaz = dotaz.where(Faktura.rok == rok)
    faktury = list(session.scalars(dotaz))
    zbyva = _zbyva(session, [f.cislo for f in faktury])
    vysledek = [StavFaktury(f, zbyva.get(f.cislo, 0), f.zapis.stornovany) for f in faktury]
    if jen_otevrene:
        vysledek = [x for x in vysledek if not x.stornovana and x.zbyva > 0]
    return vysledek


def otevrena(session: Session, cislo: str) -> StavFaktury:
    """Faktura k úhradě podle interního čísla; chyba, když není nebo je zaplacená."""
    f = session.scalar(
        select(Faktura)
        .where(Faktura.cislo == cislo)
        .options(selectinload(Faktura.zapis).selectinload(Zapis.opravy))
    )
    if f is None:
        raise ChybaFaktury(f"Faktura {cislo} neexistuje.")
    stav = StavFaktury(f, _zbyva(session, [cislo]).get(cislo, 0), f.zapis.stornovany)
    if stav.stornovana:
        raise ChybaFaktury(f"Faktura {cislo} je stornovaná.")
    if stav.zbyva <= 0:
        raise ChybaFaktury(f"Faktura {cislo} je už zaplacená.")
    return stav


def zkontroluj_uhradu(stav: StavFaktury, castka: int) -> None:
    if castka > stav.zbyva:
        raise ChybaFaktury(
            f"Platba {kc(castka)} je vyšší, než kolik z faktury {stav.faktura.cislo} zbývá"
            f" zaplatit ({kc(stav.zbyva)})."
        )
