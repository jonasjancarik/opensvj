"""Nahrání bankovních výpisů, návrhy párování a zaúčtování pohybů.

Postup: výpis se přečte a zkontroluje (součty, navázání na předchozí výpis), pohyby se
uloží beze změny. Ke každému nezaúčtovanému pohybu aplikace navrhne operaci z katalogu;
uživatel návrh potvrdí nebo upraví a pohyb se zaúčtuje do deníku. Když si to přeje,
aplikace si párování zapamatuje pro další platby ze stejného protiúčtu.
"""

import hashlib
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy import ColumnElement, and_, exists, func, select
from sqlalchemy.orm import Session

from . import denik, faktury
from .db import (
    BankovniPohyb,
    BankovniUcet,
    BankovniVypis,
    ParovaniPohybu,
    PravidloParovani,
    Zapis,
)
from .domena import gpc, katalog, rb_csv
from .domena.penize import na_text
from .domena.profil import Profil

# Operace, které jde vybrat k pohybu, podle směru platby. Klíč je id operace v katalogu,
# hodnota jsou vstupy, které zadává uživatel (ostatní doplní aplikace z pohybu).
OPERACE = {
    "prijem": {
        "uhrada-predpisu": ["jednotka"],
        "prevod-mezi-ucty": ["druhy_ucet"],
        "prijem-nesparovany": [],
    },
    "vydaj": {
        "uhrada-faktury": ["faktura"],
        "poplatek-banky": [],
        "prevod-mezi-ucty": ["druhy_ucet"],
    },
}


class ChybaBanky(ValueError):
    pass


class NeznamyUcet(ChybaBanky):
    def __init__(self, cislo: str):
        super().__init__(f"účet {cislo} zatím aplikace nezná")
        self.cislo = cislo


@dataclass
class Nahrano:
    """Co se nahrálo z jednoho výpisu nebo přehledu pohybů."""

    druh: str  # "vypis" nebo "export" (přehled pohybů bez zůstatků)
    ucel: str
    rok: int
    cislo: int | None
    od: date | None
    do: date
    pocet_pohybu: int
    novych: int
    uz_nahranych: int
    novy_zustatek: int | None
    uz_byl_nahrany: bool = False


@dataclass
class Navrh:
    operace: str
    vstupy: dict[str, str]
    duvod: str


@dataclass
class VysledekNahrani:
    vypisy: list[Nahrano] = field(default_factory=list)


def nahraj(
    session: Session,
    profil: Profil,
    data: bytes,
    *,
    nazev_souboru: str,
    nahral: str,
    ucel: str | None = None,
) -> VysledekNahrani:
    """Uloží výpis(y) GPC nebo přehled pohybů RB (CSV). Nic nezapíše, pokud cokoli nesedí.

    Neznámý účet SVJ vyvolá `NeznamyUcet`; volající se zeptá uživatele na účel účtu
    a zavolá znovu s `ucel`.
    """
    ucty = {u.cislo: u for u in session.scalars(select(BankovniUcet))}
    sha = hashlib.sha256(data).hexdigest()
    vysledek = VysledekNahrani()

    def ucet_pro(cislo: str) -> BankovniUcet:
        nonlocal ucel
        if cislo in ucty:
            return ucty[cislo]
        if ucel is None:
            raise NeznamyUcet(cislo)
        ucty[cislo] = _novy_ucet(session, profil, cislo, ucel)
        ucel = None  # účel platí jen pro jeden neznámý účet
        return ucty[cislo]

    if rb_csv.je_rb_csv(data):
        try:
            prehled = rb_csv.cti(data)
        except gpc.ChybaVypisu as e:
            raise ChybaBanky(f"Přehled pohybů se nepodařilo přečíst: {e}") from e
        ucet = ucet_pro(prehled.ucet)
        vysledek.vypisy.append(_uloz_prehled(session, ucet, prehled, nazev_souboru, sha, nahral))
    else:
        try:
            vypisy = gpc.cti(data, znama_cisla=set(ucty))
        except gpc.ChybaVypisu as e:
            raise ChybaBanky(f"Výpis se nepodařilo přečíst: {e}") from e
        for v in sorted(vypisy, key=lambda v: (v.ucet, v.datum, v.cislo)):
            ucet = ucet_pro(v.ucet)
            vysledek.vypisy.append(_uloz_vypis(session, ucet, v, nazev_souboru, sha, nahral))
    session.flush()
    return vysledek


def _novy_ucet(session: Session, profil: Profil, cislo: str, ucel: str) -> BankovniUcet:
    if ucel not in profil.bankovni_ucty:
        raise ChybaBanky(f"neznámý účel účtu {ucel!r}")
    jiny = session.scalar(select(BankovniUcet).where(BankovniUcet.ucel == ucel))
    if jiny is not None:
        raise ChybaBanky(f"Tento účel už má účet {jiny.cislo}.")
    ucet = BankovniUcet(cislo=cislo, ucel=ucel)
    session.add(ucet)
    session.flush()
    return ucet


def _uloz_vypis(
    session: Session, ucet: BankovniUcet, v: gpc.Vypis, nazev: str, sha: str, nahral: str
) -> Nahrano:
    rok = v.datum.year
    existujici = session.scalar(
        select(BankovniVypis).where(
            BankovniVypis.ucet_id == ucet.id,
            BankovniVypis.rok == rok,
            BankovniVypis.cislo == v.cislo,
        )
    )
    if existujici is not None:
        if (existujici.stary_zustatek, existujici.novy_zustatek) != (
            v.stary_zustatek,
            v.novy_zustatek,
        ):
            raise ChybaBanky(
                f"Výpis {v.cislo}/{rok} je už nahraný, ale s jinými zůstatky. Zkontrolujte soubor."
            )
        return Nahrano(
            "vypis",
            ucet.ucel,
            rok,
            v.cislo,
            v.datum_stareho_zustatku,
            v.datum,
            len(v.pohyby),
            0,
            len(v.pohyby),
            v.novy_zustatek,
            uz_byl_nahrany=True,
        )

    posledni = session.scalar(
        select(BankovniVypis)
        .where(BankovniVypis.ucet_id == ucet.id, BankovniVypis.druh == "vypis")
        .order_by(BankovniVypis.datum.desc(), BankovniVypis.cislo.desc())
        .limit(1)
    )
    if posledni is not None:
        if v.datum < posledni.datum:
            raise ChybaBanky(
                f"Výpis {v.cislo}/{rok} je starší než poslední nahraný "
                f"({posledni.cislo}/{posledni.rok}). Nahrávejte výpisy postupně od nejstaršího."
            )
        if v.stary_zustatek != posledni.novy_zustatek:
            raise ChybaBanky(
                f"Výpis {v.cislo}/{rok} nenavazuje na výpis {posledni.cislo}/{posledni.rok}: "
                f"začíná zůstatkem {na_text(v.stary_zustatek)} Kč, předchozí končil "
                f"{na_text(posledni.novy_zustatek)} Kč. Nechybí mezi nimi výpis?"
            )

    vypis = BankovniVypis(
        ucet_id=ucet.id,
        rok=rok,
        cislo=v.cislo,
        datum=v.datum,
        datum_stareho_zustatku=v.datum_stareho_zustatku,
        stary_zustatek=v.stary_zustatek,
        novy_zustatek=v.novy_zustatek,
        obraty_debet=v.obraty_debet,
        obraty_kredit=v.obraty_kredit,
        format="gpc-vnitrni" if v.vnitrni_format else "gpc",
        nazev_souboru=nazev,
        sha256=sha,
        nahral=nahral,
    )
    session.add(vypis)
    session.flush()
    novych, uz = _uloz_pohyby(
        session,
        ucet,
        vypis,
        [(gpc.datum_pohybu(v, p), p) for p in v.pohyby],
        zdroj=f"výpisu {v.cislo}/{rok}",
    )
    return Nahrano(
        "vypis",
        ucet.ucel,
        rok,
        v.cislo,
        v.datum_stareho_zustatku,
        v.datum,
        len(v.pohyby),
        novych,
        uz,
        v.novy_zustatek,
    )


def _uloz_prehled(
    session: Session,
    ucet: BankovniUcet,
    prehled: rb_csv.PrehledPohybu,
    nazev: str,
    sha: str,
    nahral: str,
) -> Nahrano:
    """Přehled pohybů nemá zůstatky; uloží se jen pohyby, které ještě nejsou nahrané."""
    stejny = session.scalar(
        select(BankovniVypis).where(BankovniVypis.ucet_id == ucet.id, BankovniVypis.sha256 == sha)
    )
    pocet = len(prehled.pohyby)
    if stejny is not None:
        return Nahrano(
            "export",
            ucet.ucel,
            prehled.do.year,
            None,
            prehled.od,
            prehled.do,
            pocet,
            0,
            pocet,
            None,
            uz_byl_nahrany=True,
        )
    zaznam = BankovniVypis(
        ucet_id=ucet.id,
        druh="export",
        rok=prehled.do.year,
        datum=prehled.do,
        datum_stareho_zustatku=prehled.od,
        format="rb-csv",
        nazev_souboru=nazev,
        sha256=sha,
        nahral=nahral,
    )
    session.add(zaznam)
    session.flush()
    novych, uz = _uloz_pohyby(
        session,
        ucet,
        zaznam,
        [(p.datum or prehled.do, p) for p in prehled.pohyby],
        zdroj="přehledu pohybů",
    )
    return Nahrano(
        "export",
        ucet.ucel,
        prehled.do.year,
        None,
        prehled.od,
        prehled.do,
        pocet,
        novych,
        uz,
        None,
    )


def _uloz_pohyby(
    session: Session,
    ucet: BankovniUcet,
    zaznam: BankovniVypis,
    pohyby: list[tuple[date, gpc.Pohyb]],
    *,
    zdroj: str,
) -> tuple[int, int]:
    """Uloží pohyby, které ještě nejsou nahrané. Vrátí (nových, už nahraných).

    Pohyb, který už přišel z přehledu pohybů, se přeskočí; výpis ho jen potvrdí.
    Pohyb, který už přišel z jiného výpisu, znamená chybu v souborech.
    """
    novych = uz = 0
    for datum, p in pohyby:
        klic = p.id_banky or (
            f"{datum}|{p.castka}|{p.protiucet}|{p.vs}|{zaznam.rok}/{zaznam.cislo}|{p.poradi}"
        )
        drivejsi = session.scalar(
            select(BankovniVypis.druh)
            .join(BankovniPohyb, BankovniPohyb.vypis_id == BankovniVypis.id)
            .where(BankovniPohyb.ucet_id == ucet.id, BankovniPohyb.klic == klic)
        )
        if drivejsi is not None:
            if zaznam.druh == "vypis" and drivejsi == "vypis":
                raise ChybaBanky(f"Pohyb {klic} z {zdroj} už je nahraný z jiného výpisu.")
            uz += 1
            continue
        session.add(
            BankovniPohyb(
                vypis_id=zaznam.id,
                ucet_id=ucet.id,
                poradi=p.poradi,
                klic=klic,
                datum=datum,
                valuta=p.valuta,
                castka=p.castka,
                kod_uctovani=p.kod_uctovani,
                protiucet=p.protiucet,
                kod_banky=p.kod_banky,
                nazev=p.nazev,
                vs=p.vs,
                ks=p.ks,
                ss=p.ss,
                zprava="\n".join(p.zprava),
            )
        )
        novych += 1
    session.flush()
    return novych, uz


# --- návrhy ---------------------------------------------------------------


@dataclass
class KontextNavrhu:
    """Co o SVJ potřebují návrhy plateb vlastníků: VS jednotek a měsíční předpisy."""

    profil: Profil | None = None
    mesicni: dict[str, int] = field(default_factory=dict)  # jednotka → měsíční předpis
    otevrene_faktury: list[faktury.StavFaktury] = field(default_factory=list)


def navrhni(
    pohyb: BankovniPohyb,
    ucty: list[BankovniUcet],
    pravidla: list[PravidloParovani],
    kontext: KontextNavrhu | None = None,
) -> Navrh | None:
    """Navrhne zaúčtování pohybu. Návrh vždy potvrzuje člověk."""
    smer = pohyb.smer
    vlastni = {u.cislo: u.ucel for u in ucty}
    if pohyb.protiucet in vlastni and vlastni[pohyb.protiucet] != pohyb.ucet.ucel:
        return Navrh(
            "prevod-mezi-ucty",
            {"druhy_ucet": vlastni[pohyb.protiucet]},
            "Protiúčet je jiný účet SVJ.",
        )
    if smer == "vydaj" and kontext is not None and kontext.otevrene_faktury:
        navrh = _navrh_uhrady_faktury(pohyb, kontext.otevrene_faktury)
        if navrh is not None:
            return navrh
    # Úhrada faktury se nepamatuje: příště jde o jinou fakturu.
    kandidati = [p for p in pravidla if p.smer == smer and p.operace != "uhrada-faktury"]
    for pr in kandidati:  # nejdřív protiúčet i VS
        if pr.protiucet and pr.protiucet == pohyb.protiucet and pr.vs and pr.vs == pohyb.vs:
            return Navrh(pr.operace, dict(pr.parametry), "Stejně jako dřív: protiúčet a VS.")
    for pr in kandidati:
        if pr.protiucet and pr.protiucet == pohyb.protiucet and not pr.vs:
            return Navrh(pr.operace, dict(pr.parametry), "Stejně jako dřív platby z tohoto účtu.")
    for pr in kandidati:
        if not pr.protiucet and pr.vs and pr.vs == pohyb.vs:
            return Navrh(pr.operace, dict(pr.parametry), "Stejně jako dřív platby s tímto VS.")
    if smer == "prijem" and kontext is not None:
        navrh = _navrh_platby_vlastnika(pohyb, kontext)
        if navrh is not None:
            return navrh
    text = f"{pohyb.nazev} {pohyb.zprava}".lower()
    if smer == "vydaj" and pohyb.protiucet is None and "poplat" in text:
        return Navrh("poplatek-banky", {}, "Bankovní poplatek podle popisu na výpisu.")
    return None


def _navrh_uhrady_faktury(
    pohyb: BankovniPohyb, otevrene: list[faktury.StavFaktury]
) -> Navrh | None:
    castka = -pohyb.castka

    def navrh(f: faktury.StavFaktury, duvod: str) -> Navrh:
        return Navrh("uhrada-faktury", {"faktura": f.faktura.cislo}, duvod)

    if pohyb.vs:
        podle_vs = [f for f in otevrene if f.faktura.vs == pohyb.vs and f.zbyva >= castka]
        if len(podle_vs) == 1:
            return navrh(podle_vs[0], f"VS odpovídá faktuře {podle_vs[0].faktura.cislo}.")
    if pohyb.protiucet:
        podle_uctu = [
            f
            for f in otevrene
            if f.zbyva == castka and _stejny_ucet(f.faktura.ucet_dodavatele, pohyb)
        ]
        if len(podle_uctu) == 1:
            return navrh(podle_uctu[0], "Účet dodavatele i částka odpovídají faktuře.")
    podle_castky = [f for f in otevrene if f.zbyva == castka]
    if len(podle_castky) == 1:
        return navrh(podle_castky[0], "Částka odpovídá jediné nezaplacené faktuře.")
    return None


def _stejny_ucet(ucet: str | None, pohyb: BankovniPohyb) -> bool:
    if not ucet:
        return False
    cislo, _, banka = ucet.strip().partition("/")
    try:
        cislo = gpc.normalizuj_cislo(cislo)
    except gpc.ChybaVypisu:
        return False
    return cislo == pohyb.protiucet and (
        not banka or not pohyb.kod_banky or banka == pohyb.kod_banky
    )


def _navrh_platby_vlastnika(pohyb: BankovniPohyb, k: KontextNavrhu) -> Navrh | None:
    jednotka = k.profil.jednotka_podle_vs(pohyb.vs) if k.profil else None
    if jednotka is not None:
        sedi = k.mesicni.get(jednotka) == pohyb.castka
        return Navrh(
            "uhrada-predpisu",
            {"jednotka": jednotka},
            f"VS patří jednotce {jednotka}"
            + (" a částka odpovídá jejímu měsíčnímu předpisu." if sedi else "."),
        )
    shodne = [j for j, c in k.mesicni.items() if c == pohyb.castka]
    if len(shodne) == 1:
        return Navrh(
            "uhrada-predpisu",
            {"jednotka": shodne[0]},
            f"Částka odpovídá měsíčnímu předpisu jednotky {shodne[0]}.",
        )
    return None


# --- zaúčtování -----------------------------------------------------------


def _vstupy(
    profil: Profil, pohyb: BankovniPohyb, operace: str, zadane: dict[str, Any]
) -> tuple[dict[str, str], str | None]:
    smer = pohyb.smer
    povolene = OPERACE[smer]
    if operace not in povolene:
        raise ChybaBanky("Tuto operaci u tohoto pohybu nejde použít.")
    vstupy = {"castka": na_text(abs(pohyb.castka)), "ucet": pohyb.ucet.ucel}
    krok = None
    for pole in povolene[operace]:
        hodnota = str(zadane.get(pole) or "").strip()
        if not hodnota:
            raise ChybaBanky(f"Chybí údaj „{POPISKY[pole]}“.")
        if pole == "jednotka" and hodnota not in profil.jednotky:
            raise ChybaBanky(f"Jednotku {hodnota} SVJ nemá.")
        if pole == "druhy_ucet":
            if hodnota not in profil.bankovni_ucty or hodnota == pohyb.ucet.ucel:
                raise ChybaBanky("Vyberte druhý účet SVJ.")
            z, na = (hodnota, pohyb.ucet.ucel) if smer == "prijem" else (pohyb.ucet.ucel, hodnota)
            vstupy |= {"z": z, "na": na}
            krok = "prichod" if smer == "prijem" else "odchod"
            continue
        if len(hodnota) > 128:
            raise ChybaBanky(f"Údaj „{POPISKY[pole]}“ je příliš dlouhý.")
        vstupy[pole] = hodnota
    return vstupy, krok


POPISKY = {
    "jednotka": "jednotka",
    "protistrana": "dodavatel",
    "druhy_ucet": "druhý účet",
    "faktura": "faktura",
}


def zauctovano(pohyb_id: Any) -> ColumnElement[bool]:
    """Pohyb má platné zaúčtování (jeho zápis nikdo nestornoval)."""
    return and_(
        ParovaniPohybu.pohyb_id == pohyb_id,
        ParovaniPohybu.zapis_id == Zapis.id,
        denik.platny(),
    )


def zauctuj_pohyb(
    session: Session,
    profil: Profil,
    pohyb_id: int,
    operace_id: str,
    zadane: dict[str, Any],
    *,
    zauctoval: str,
    zapamatovat: bool = False,
) -> ParovaniPohybu:
    pohyb = session.scalar(
        select(BankovniPohyb).where(BankovniPohyb.id == pohyb_id).with_for_update()
    )
    if pohyb is None:
        raise ChybaBanky("Pohyb neexistuje.")
    if session.scalar(select(exists().where(zauctovano(pohyb.id)))):
        raise ChybaBanky("Pohyb už je zaúčtovaný.")
    vstupy, krok = _vstupy(profil, pohyb, operace_id, zadane)
    operace = katalog.nacti()[operace_id]
    radky = None
    if operace_id == "uhrada-faktury":
        try:
            stav = faktury.otevrena(session, vstupy["faktura"])
            faktury.zkontroluj_uhradu(stav, abs(pohyb.castka))
        except faktury.ChybaFaktury as e:
            raise ChybaBanky(str(e)) from e
        vstupy["protistrana"] = stav.faktura.dodavatel
        radky = faktury.s_parovacim_symbolem(
            katalog.sestav(operace, vstupy, krok), stav.faktura.cislo
        )
    vypis = pohyb.vypis
    popis = " · ".join(
        x for x in (operace.nazev, pohyb.nazev, f"VS {pohyb.vs}" if pohyb.vs else "") if x
    )
    try:
        zapis = denik.zauctuj(
            session,
            profil,
            operace,
            vstupy,
            datum=pohyb.datum,
            popis=popis,
            doklad=(
                f"výpis {vypis.cislo}/{vypis.rok} {pohyb.ucet.ucel}"
                if vypis.druh == "vypis"
                else f"pohyb {pohyb.klic}"
            )[:32],
            zauctoval=zauctoval,
            krok=krok,
            idempotencni_klic=f"bankovni-pohyb:{pohyb.id}",
            radky=radky,
        )
    except denik.ChybaUctovani as e:
        raise ChybaBanky(str(e)) from e
    parovani = ParovaniPohybu(
        pohyb_id=pohyb.id,
        zapis_id=zapis.id,
        operace=operace_id,
        vstupy={k: v for k, v in zadane.items() if k in OPERACE[pohyb.smer][operace_id]},
        zauctoval=zauctoval,
    )
    session.add(parovani)
    if zapamatovat and (pohyb.protiucet or pohyb.vs) and operace_id != "uhrada-faktury":
        _zapamatuj(session, pohyb, operace_id, parovani.vstupy, zauctoval)
    session.flush()
    return parovani


def _zapamatuj(
    session: Session, pohyb: BankovniPohyb, operace: str, parametry: dict, kdo: str
) -> None:
    # Podle protiúčtu, když ho platba má; jinak podle VS.
    protiucet = pohyb.protiucet
    vs = None if protiucet else pohyb.vs
    pravidlo = session.scalar(
        select(PravidloParovani).where(
            PravidloParovani.smer == pohyb.smer,
            PravidloParovani.protiucet.is_not_distinct_from(protiucet),
            PravidloParovani.vs.is_not_distinct_from(vs),
        )
    )
    if pravidlo is None:
        pravidlo = PravidloParovani(smer=pohyb.smer, protiucet=protiucet, vs=vs, vytvoril=kdo)
        session.add(pravidlo)
    pravidlo.operace = operace
    pravidlo.parametry = parametry
    pravidlo.vytvoril = kdo
    pravidlo.zmeneno = func.now()
