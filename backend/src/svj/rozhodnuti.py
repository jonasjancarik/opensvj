"""Rozhodnutí orgánů SVJ a co dokládají.

Výši záloh a příspěvků schvaluje shromáždění (§ 1208 písm. d) OZ), klíče a další volby
společenství určují stanovy, shromáždění nebo výbor. Aplikace u každé takové položky ukáže,
o které rozhodnutí se opírá, nebo že rozhodnutí doložené není.

Položky vznikají z profilu SVJ a z předpisu záloh. Klíč položky obsahuje i zvolenou hodnotu
(třeba `klic-spravy:SPRAVA:jednotka`), takže když se v profilu změní, položka znovu čeká
na doložení.

Přiřazení si pamatuje otisk (SHA-256) schválené podoby položky. Když se verze předpisu
po schválení změní, otisk nesedí: schválení přestane platit, uzávěrka na to upozorní
a v rozhraní je vidět „Změněno po schválení“ s tím, kdo a proč předpis změnil. Rozhodnutí
jde k nové podobě znovu potvrdit.
"""

from dataclasses import dataclass, replace
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import audit, meridla, predpisy
from .db import AuditniZaznam, Rozhodnuti, RozhodnutiPro
from .domena.profil import Profil

ORGANY: dict[str, str] = {
    "shromazdeni": "Shromáždění",
    "per_rollam": "Shromáždění per rollam",
    "vybor": "Výbor",
    "predseda": "Předseda společenství",
}

_KLICE_SPRAVY = {
    "podil": "podle podílu na společných částech",
    "jednotka": "rovným dílem na jednotku",
}
_KLICE_SLUZEB = {
    "osoby": "podle počtu osob",
    "jednotka": "rovným dílem na jednotku",
    "plocha": "podle podlahové plochy",
    "podil": "podle podílu na společných částech",
    "meridla": "podle spotřeby na měřidlech",
    "zuctovatel": "podle výsledků od zúčtovatele",
}
_MESIC_PREVODU = {"dosavadni": "dosavadní vlastník", "novy": "nový vlastník"}
_PRISPEVKY = {"zalohove": "zálohové", "nezalohove": "nezálohové"}


class ChybaRozhodnuti(ValueError):
    pass


@dataclass
class UdajeRozhodnuti:
    organ: str
    datum: date
    nazev: str
    bod: str = ""
    text: str = ""
    hlasovani: str = ""
    ulozeni: str = ""


@dataclass
class Polozka:
    klic: str
    skupina: str
    nazev: str
    popis: str
    od: date | None = None  # verze předpisu: odkdy platí
    do: date | None = None
    otisk: str = ""  # podoba položky, ke které se schválení váže
    # Kde v auditním záznamu hledat změny položky (druh, klíč).
    zmeny: tuple[str, str] | None = None
    zmeneno_po_schvaleni: bool = False

    def __post_init__(self) -> None:
        if not self.otisk:
            # Klíč obsahuje zvolenou hodnotu, takže sám určuje podobu položky.
            self.otisk = audit.otisk(self.klic)


@dataclass
class Dolozeni:
    """Přiřazené rozhodnutí; `platne` je False, když se položka po schválení změnila."""

    rozhodnuti_id: int
    platne: bool
    prirazeno: datetime
    zmena: AuditniZaznam | None = None  # poslední změna položky po schválení


def _d(d: date) -> str:
    return f"{d.day}. {d.month}. {d.year}"


def popis(r: Rozhodnuti) -> str:
    """„Shromáždění 12. 2. 2026, bod 4: Výše záloh“."""
    bod = f", bod {r.bod}" if r.bod else ""
    return f"{ORGANY.get(r.organ, r.organ)} {_d(r.datum)}{bod}: {r.nazev}"


def polozky(profil: Profil, nastaveni: predpisy.Nastaveni) -> list[Polozka]:
    """Co v nastavení SVJ potřebuje doložené rozhodnutí."""
    vysledek: list[Polozka] = []
    verze = sorted(nastaveni.verze, key=lambda v: v.plati_od)
    for i, v in enumerate(verze):
        do = verze[i + 1].plati_od if i + 1 < len(verze) else None
        vysledek.append(
            Polozka(
                klic=f"predpis:{v.plati_od.isoformat()}",
                skupina="Předpis záloh",
                nazev=f"Výše záloh od {_d(v.plati_od)}",
                popis=", ".join(s.nazev for s in v.slozky),
                od=v.plati_od,
                do=do,
                otisk=v.otisk,
                zmeny=("verze_predpisu", v.plati_od.isoformat()),
            )
        )
    if verze:
        vysledek.append(
            Polozka(
                klic=f"splatnost:{nastaveni.splatnost_den}",
                skupina="Předpis záloh",
                nazev=f"Zálohy jsou splatné do {nastaveni.splatnost_den}. dne v měsíci",
                popis="",
            )
        )
    for kod, u in profil.sprava.items():
        k = u.get("klic", "podil")
        vysledek.append(
            Polozka(
                klic=f"klic-spravy:{kod}:{k}",
                skupina="Vyúčtování záloh na správu",
                nazev=f"{u.get('nazev', kod)}: rozúčtování {_KLICE_SPRAVY.get(k, k)}",
                popis="",
            )
        )
    for kod, u in profil.sluzby.items():
        k = u.get("klic", "osoby")
        druh = u.get("meridlo")
        nazev_druhu = meridla.DRUHY.get(druh, (druh,))[0].lower() if druh else ""
        jak = _KLICE_SLUZEB.get(k, k) + (f" ({nazev_druhu})" if druh else "")
        vysledek.append(
            Polozka(
                klic=f"klic-sluzby:{kod}:{k}" + (f":{druh}" if druh else ""),
                skupina="Vyúčtování služeb",
                nazev=f"{u.get('nazev', kod)}: rozúčtování {jak}",
                popis="výchozí klíč podle zákona" if "klic" not in u else "",
            )
        )
    vysledek.append(
        Polozka(
            klic=f"volba:predpis_mesice_prevodu:{profil.predpis_mesice_prevodu}",
            skupina="Volby společenství",
            nazev="Předpis za měsíc převodu jednotky platí "
            + _MESIC_PREVODU[profil.predpis_mesice_prevodu],
            popis="",
        )
    )
    if profil.prispevky:
        vysledek.append(
            Polozka(
                klic=f"volba:prispevky:{profil.prispevky}",
                skupina="Volby společenství",
                nazev="Příspěvky na správu jsou "
                + _PRISPEVKY.get(profil.prispevky, profil.prispevky),
                popis="",
            )
        )
    return vysledek


def rozhodnuti(s: Session) -> list[Rozhodnuti]:
    return list(s.scalars(select(Rozhodnuti).order_by(Rozhodnuti.datum.desc(), Rozhodnuti.id)))


def prirazeni(s: Session) -> dict[str, int]:
    return {p.klic: p.rozhodnuti_id for p in s.scalars(select(RozhodnutiPro))}


def dolozeni(s: Session, polozky_: list[Polozka]) -> dict[str, Dolozeni]:
    """Přiřazená rozhodnutí a zda pořád platí pro současnou podobu položky."""
    podle_klice = {p.klic: p for p in polozky_}
    vysledek = {}
    for p in s.scalars(select(RozhodnutiPro)):
        polozka = podle_klice.get(p.klic)
        if polozka is None:
            continue
        platne = p.otisk is None or p.otisk == polozka.otisk
        zmena = None
        if not platne and polozka.zmeny:
            zmena = audit.posledni_zmena(s, *polozka.zmeny, po=p.upraveno)
        vysledek[p.klic] = Dolozeni(p.rozhodnuti_id, platne, p.upraveno, zmena)
    return vysledek


def schvaleni_verze(
    s: Session, profil: Profil, nastaveni: predpisy.Nastaveni
) -> dict[date, tuple[Rozhodnuti, Dolozeni]]:
    """Verze předpisu, ke kterým je přiřazené rozhodnutí, podle data platnosti."""
    pol = polozky(profil, nastaveni)
    d = dolozeni(s, pol)
    vysledek = {}
    for p in pol:
        if p.od is not None and p.klic in d:
            r = s.get(Rozhodnuti, d[p.klic].rozhodnuti_id)
            if r is not None:
                vysledek[p.od] = (r, d[p.klic])
    return vysledek


def _over(u: UdajeRozhodnuti) -> UdajeRozhodnuti:
    if u.organ not in ORGANY:
        raise ChybaRozhodnuti("Neznámý orgán.")
    nazev = u.nazev.strip()
    if not nazev:
        raise ChybaRozhodnuti("Chybí, o čem se rozhodlo.")
    for hodnota, delka, co in (
        (nazev, 200, "název"),
        (u.bod.strip(), 32, "bod"),
        (u.hlasovani.strip(), 200, "hlasování"),
        (u.ulozeni.strip(), 500, "uložení zápisu"),
    ):
        if len(hodnota) > delka:
            raise ChybaRozhodnuti(f"Údaj „{co}“ je příliš dlouhý (nejvýš {delka} znaků).")
    return UdajeRozhodnuti(
        organ=u.organ,
        datum=u.datum,
        nazev=nazev,
        bod=u.bod.strip(),
        text=u.text.strip(),
        hlasovani=u.hlasovani.strip(),
        ulozeni=u.ulozeni.strip(),
    )


def pridej(s: Session, u: UdajeRozhodnuti, kdo: str) -> Rozhodnuti:
    r = Rozhodnuti(**vars(_over(u)), upravil=kdo)
    s.add(r)
    s.flush()
    return r


def uprav(s: Session, rozhodnuti_id: int, u: UdajeRozhodnuti, kdo: str) -> Rozhodnuti:
    r = s.get(Rozhodnuti, rozhodnuti_id)
    if r is None:
        raise ChybaRozhodnuti("Takové rozhodnutí v evidenci není.")
    for k, v in vars(_over(u)).items():
        setattr(r, k, v)
    r.upravil = kdo
    return r


def smaz(s: Session, rozhodnuti_id: int) -> None:
    """Smaže rozhodnutí; položky, které dokládalo, budou zase bez doložení."""
    r = s.get(Rozhodnuti, rozhodnuti_id)
    if r is None:
        raise ChybaRozhodnuti("Takové rozhodnutí v evidenci není.")
    for p in s.scalars(select(RozhodnutiPro).where(RozhodnutiPro.rozhodnuti_id == r.id)):
        s.delete(p)
    # Přiřazení napřed: jinak je smaže databáze kaskádou dřív a ORM je pak nenajde.
    s.flush()
    s.delete(r)


def prirad(
    s: Session,
    profil: Profil,
    nastaveni: predpisy.Nastaveni,
    klic: str,
    rozhodnuti_id: int | None,
    kdo: str,
) -> None:
    """Přiřadí položce rozhodnutí; None přiřazení zruší."""
    polozka = next((p for p in polozky(profil, nastaveni) if p.klic == klic), None)
    if polozka is None:
        raise ChybaRozhodnuti("Tato položka v nastavení SVJ už není. Načtěte stránku znovu.")
    audit.pojmenuj(s, "prirazeni_rozhodnuti", klic, polozka.nazev)
    p = s.get(RozhodnutiPro, klic)
    if rozhodnuti_id is None:
        if p is not None:
            s.delete(p)
        return
    if s.get(Rozhodnuti, rozhodnuti_id) is None:
        raise ChybaRozhodnuti("Takové rozhodnutí v evidenci není.")
    if p is None:
        s.add(
            RozhodnutiPro(klic=klic, rozhodnuti_id=rozhodnuti_id, otisk=polozka.otisk, upravil=kdo)
        )
    elif p.rozhodnuti_id != rozhodnuti_id or p.otisk != polozka.otisk:
        if p.rozhodnuti_id == rozhodnuti_id:
            audit.duvod(s, "Rozhodnutí potvrzené i pro změněnou podobu.")
        p.rozhodnuti_id = rozhodnuti_id
        p.otisk = polozka.otisk
        p.upravil = kdo


def presun_schvaleni(s: Session, stary: str, novy: str, nazev: str) -> None:
    """Přenese přiřazené rozhodnutí na položku s novým klíčem (předpis s jiným datem).
    Otisk zůstane původní, takže schválení neplatí, dokud ho někdo znovu nepotvrdí."""
    p = s.get(RozhodnutiPro, stary)
    if p is None or s.get(RozhodnutiPro, novy) is not None:
        return
    audit.pojmenuj(s, "prirazeni_rozhodnuti", novy, nazev)
    p.klic = novy
    s.flush()


def bez_rozhodnuti(
    s: Session, profil: Profil, nastaveni: predpisy.Nastaveni, rok: int | None = None
) -> list[Polozka]:
    """Položky bez platného rozhodnutí (i ty změněné po schválení); s rokem jen verze
    předpisu, které v roce platily."""
    pol = polozky(profil, nastaveni)
    hotove = dolozeni(s, pol)
    vysledek = []
    for p in pol:
        if p.klic in hotove:
            if hotove[p.klic].platne:
                continue
            p = replace(p, zmeneno_po_schvaleni=True)
        if rok is not None and p.od is not None:
            if p.od > date(rok, 12, 31) or (p.do is not None and p.do <= date(rok, 1, 1)):
                continue
        vysledek.append(p)
    return vysledek
