"""Dlužníci: co který vlastník nezaplatil a od kdy.

Platba, u které vlastník určil, na který dluh platí, jde nejdřív na ten dluh (§ 1933
odst. 1 OZ). Ostatní platby se přiřazují k nejstarším dluhům (FIFO): nejdřív zůstatky
z minulých let, potom měsíční předpisy a další pohledávky podle splatnosti. Upomínka
v aplikaci vždy obsahuje všechny dluhy po splatnosti, takže pořadí podle upomenutí
(§ 1933 odst. 1 OZ) dává totéž. Součet nezaplacených položek minus přeplatek je vždy
rovný saldu jednotky z `predpisy.saldo`.

Odepsaný dluh se z pohledávek odúčtuje, ale nezaniká. Aplikace ho dál vede po jednotkách
přes všechny roky (`odepsane`), dokud ho dlužník nezaplatí. Formální podrozvahové účty
vyhláška 504 (§ 37 odst. 4) vyžaduje jen u pohledávek odepsaných po stoprocentní opravné
položce; ty SVJ obvykle netvoří.
"""

import calendar
from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import denik, pocatecni, predpisy, vyuctovani_spravy
from .db import RadekZapisu, Zapis
from .domena import katalog
from .domena import urok as urok_z_prodleni
from .domena.penize import halire, kc, na_text
from .domena.profil import Profil

POPIS_ROLE = {
    "pohledavky_vlastnici": "Nezaplacené zálohy z minulých let",
    "pohledavky_vyuctovani": "Nedoplatek z vyúčtování",
    "pohledavky_vyuctovani_minule": "Nedoplatek z vyúčtování dřívějších let",
}
# Pořadí dluhů z minulých let, od nejstaršího.
STARI = {"pohledavky_vyuctovani_minule": 0, "pohledavky_vlastnici": 1, "pohledavky_vyuctovani": 2}


@dataclass
class Polozka:
    popis: str
    splatnost: date | None  # None = z minulých let, splatné už před začátkem roku
    castka: int
    zbyva: int = 0
    poradi: tuple = field(default=(), repr=False, compare=False)
    role: str = "pohledavky_vlastnici"
    vznik: date | None = None  # datum zápisu, ze kterého dluh vznikl
    mesic: date | None = None  # u měsíčního předpisu první den měsíce
    radky: list[int] = field(default_factory=list, repr=False, compare=False)

    @property
    def radek(self) -> int | None:
        """Řádek zápisu, kterým dluh vznikl; na něj odkazuje platba, která ho určuje."""
        return self.radky[0] if self.radky else None

    def po_splatnosti(self, dnes: date) -> bool:
        return self.splatnost is None or self.splatnost < dnes

    def urok(self, dnes: date, od: date | None = None) -> int | None:
        """Zákonný úrok z prodlení z dosud nezaplacené části k `dnes` (None = neumíme spočítat,
        např. u dluhu z minulých let bez známé splatnosti). S `od` jen za dobu po `od`,
        protože úrok do toho dne už SVJ předepsalo."""
        if self.splatnost is None:
            return None
        return urok_z_prodleni.urok(self.zbyva, self.splatnost, dnes, od)

    def sazba(self) -> int | None:
        if self.splatnost is None:
            return None
        return urok_z_prodleni.sazba(self.splatnost + timedelta(days=1))


@dataclass
class DluhJednotky:
    jednotka: str
    polozky: list[Polozka] = field(default_factory=list)  # jen nezaplacené, od nejstarší
    preplatek: int = 0
    dnes: date = field(default_factory=date.today)
    urok_do: date | None = None  # do kdy už SVJ úrok z prodlení předepsalo
    sankce: int = 0  # předepsaný úrok z prodlení a pokuty, které zbývá zaplatit

    @property
    def po_splatnosti(self) -> int:
        return sum(p.zbyva for p in self.polozky if p.po_splatnosti(self.dnes))

    @property
    def nesplatne(self) -> int:
        return sum(p.zbyva for p in self.polozky if not p.po_splatnosti(self.dnes))

    @property
    def od(self) -> date | None:
        """Splatnost nejstarší nezaplacené položky po splatnosti (None i u dluhu z minulých let
        – ten poznáte podle `z_minulych_let`)."""
        prvni = next((p for p in self.polozky if p.po_splatnosti(self.dnes)), None)
        return prvni.splatnost if prvni else None

    @property
    def z_minulych_let(self) -> bool:
        return any(p.splatnost is None or p.vznik is None for p in self.polozky)

    @property
    def urok(self) -> int:
        """Součet úroků z prodlení, které umíme spočítat."""
        return sum(p.urok(self.dnes, self.urok_do) or 0 for p in self.polozky)

    @property
    def urok_neuplny(self) -> bool:
        """Některá položka po splatnosti nemá spočitatelný úrok."""
        return any(
            p.po_splatnosti(self.dnes) and p.urok(self.dnes, self.urok_do) is None
            for p in self.polozky
        )

    @property
    def saldo(self) -> int:
        return sum(p.zbyva for p in self.polozky) - self.preplatek


def splatnost_mesice(rok: int, mesic: int, den: int) -> date:
    return date(rok, mesic, min(den, calendar.monthrange(rok, mesic)[1]))


def _rozpis(
    session: Session,
    profil: Profil,
    nastaveni: predpisy.Nastaveni,
    rok: int,
    podle_uctu: bool,
) -> tuple[dict, dict]:
    """Dluhy a nevyčerpané platby po jednotkách (nebo po jednotkách a účtech).

    Vrací (skupina → klíč → položka, skupina → kredit). Skupina je jednotka, nebo
    dvojice (jednotka, role), když se platby započítávají jen v rámci účtu.
    """
    radky = session.execute(
        predpisy._radky_vlastniku(
            rok,
            RadekZapisu.jednotka,
            RadekZapisu.role,
            RadekZapisu.popis,
            RadekZapisu.splatnost,
            RadekZapisu.strana,
            RadekZapisu.castka,
            RadekZapisu.id,
            RadekZapisu.urceno_na,
            Zapis.id,
            Zapis.operace,
            Zapis.datum,
            Zapis.popis,
        )
        .where(RadekZapisu.protistrana.is_(None))
        .order_by(Zapis.datum, Zapis.id)
    ).all()

    dluhy: dict = {}
    kredit: dict = {}
    urcene: dict = {}  # skupina → [(řádek určeného dluhu, částka)]
    for (
        jednotka,
        role,
        popis_radku,
        splatnost_radku,
        strana,
        castka,
        radek_id,
        urceno_na,
        zapis_id,
        operace,
        datum,
        popis,
    ) in radky:
        if jednotka not in profil.jednotky:
            continue
        skupina = (jednotka, role) if podle_uctu else jednotka
        dluhy.setdefault(skupina, {})
        kredit.setdefault(skupina, 0)
        znamenko = 1 if strana == "md" else -1
        if operace == pocatecni.OPERACE:
            # Počáteční stav převzatý z minulého roku v aplikaci nese splatnost položky;
            # u zůstatků z dřívějšího účetnictví ji neznáme.
            text = popis_radku or POPIS_ROLE.get(role, role)
            klic = ("pocatek", role, text, splatnost_radku)
            poradi = (STARI.get(role, 9), text)
            p = dluhy[skupina].setdefault(
                klic, Polozka(text, splatnost_radku, 0, poradi=poradi, role=role)
            )
            p.castka += znamenko * castka
            if strana == "md":
                p.radky.append(radek_id)
        elif strana == "d":
            if urceno_na is not None:
                urcene.setdefault(skupina, []).append((urceno_na, castka))
            else:
                kredit[skupina] += castka
        else:
            mesic = None
            if operace == "predpis-mesicni":
                splatnost = splatnost_mesice(datum.year, datum.month, nastaveni.splatnost_den)
                text = f"Zálohy za {predpisy.MESICE[datum.month - 1]} {datum.year}"
                mesic = datum.replace(day=1)
            elif operace in (vyuctovani_spravy.OPERACE, "vyuctovani-sluzeb"):
                splatnost, text = vyuctovani_spravy.splatnost(datum.year), popis
            else:
                splatnost, text = datum, popis
            p = dluhy[skupina].setdefault(
                ("zapis", zapis_id, role),
                Polozka(text, splatnost, 0, role=role, vznik=datum, mesic=mesic),
            )
            p.castka += castka
            p.radky.append(radek_id)

    for skupina, polozky in dluhy.items():
        zbyva_kreditu = kredit[skupina]
        kladne = []
        for p in polozky.values():
            if p.castka < 0:  # přeplatek z minulých let se chová jako platba
                zbyva_kreditu -= p.castka
            elif p.castka > 0:
                kladne.append(p)
        kladne.sort(key=lambda p: (p.splatnost is not None, p.splatnost or date.min, p.poradi))
        for p in kladne:
            p.zbyva = p.castka
        # Platby, u kterých vlastník určil dluh, jdou nejdřív na něj (§ 1933 odst. 1 OZ);
        # co z nich zbude, se započte jako ostatní platby.
        podle_radku = {r: p for p in kladne for r in p.radky}
        for radek, castka in urcene.get(skupina, []):
            p = podle_radku.get(radek)
            uhrazeno = min(p.zbyva, castka) if p else 0
            if p:
                p.zbyva -= uhrazeno
            zbyva_kreditu += castka - uhrazeno
        for p in kladne:
            uhrazeno = min(p.zbyva, zbyva_kreditu)
            zbyva_kreditu -= uhrazeno
            p.zbyva -= uhrazeno
        dluhy[skupina] = {k: p for k, p in polozky.items() if p.castka > 0}
        kredit[skupina] = zbyva_kreditu
    return dluhy, kredit


OPERACE_UROKU = "urok-z-prodleni"
ROLE_SANKCI = "pohledavky_vlastnici_sankce"


def urok_predepsan_do(session: Session) -> dict[str, date]:
    """Po jednotkách datum posledního předpisu úroku z prodlení (přes všechny roky)."""
    radky = session.execute(
        select(RadekZapisu.jednotka, func.max(Zapis.datum))
        .join(Zapis)
        .where(
            Zapis.operace == OPERACE_UROKU,
            RadekZapisu.role == ROLE_SANKCI,
            RadekZapisu.jednotka.is_not(None),
            denik.nestornovany(),
        )
        .group_by(RadekZapisu.jednotka)
    ).all()
    return {j: d for j, d in radky}


def nezaplacene_sankce(session: Session, rok: int) -> dict[str, int]:
    """Po jednotkách zůstatek předepsaných sankcí (úrok z prodlení, pokuty) v roce."""
    radky = session.execute(
        select(RadekZapisu.jednotka, RadekZapisu.strana, func.sum(RadekZapisu.castka))
        .join(Zapis)
        .where(
            Zapis.rok == rok,
            RadekZapisu.role == ROLE_SANKCI,
            RadekZapisu.jednotka.is_not(None),
            denik.platny(),
        )
        .group_by(RadekZapisu.jednotka, RadekZapisu.strana)
    ).all()
    vysledek: dict[str, int] = {}
    for jednotka, strana, castka in radky:
        vysledek[jednotka] = vysledek.get(jednotka, 0) + (castka if strana == "md" else -castka)
    return {j: c for j, c in vysledek.items() if c}


def prehled(
    session: Session,
    profil: Profil,
    nastaveni: predpisy.Nastaveni,
    rok: int,
    dnes: date | None = None,
) -> list[DluhJednotky]:
    dnes = dnes or date.today()
    dluhy, kredit = _rozpis(session, profil, nastaveni, rok, podle_uctu=False)
    urok_do = urok_predepsan_do(session)
    sankce = nezaplacene_sankce(session, rok)
    vysledek = []
    for jednotka in profil.jednotky:
        polozky = sorted(
            dluhy.get(jednotka, {}).values(),
            key=lambda p: (p.splatnost is not None, p.splatnost or date.min, p.poradi),
        )
        nezaplacene = [p for p in polozky if p.zbyva]
        vysledek.append(
            DluhJednotky(
                jednotka,
                nezaplacene,
                kredit.get(jednotka, 0),
                dnes,
                urok_do.get(jednotka),
                sankce.get(jednotka, 0),
            )
        )
    return vysledek


def k_prevodu(
    session: Session, profil: Profil, nastaveni: predpisy.Nastaveni, rok: int
) -> list[tuple[str, str, list[Polozka], int]]:
    """Co se k 31. 12. převádí do dalšího roku: po jednotkách a účtech nezaplacené položky
    a nevyčerpaný přeplatek. Platby se tu započítávají jen v rámci účtu, aby počáteční stav
    každého účtu navazoval na jeho konečný zůstatek."""
    dluhy, kredit = _rozpis(session, profil, nastaveni, rok, podle_uctu=True)
    vysledek = []
    for (jednotka, role), polozky in sorted(dluhy.items()):
        nezaplacene = sorted(
            (p for p in polozky.values() if p.zbyva),
            key=lambda p: (p.splatnost is not None, p.splatnost or date.min, p.poradi),
        )
        vysledek.append((jednotka, role, nezaplacene, kredit[(jednotka, role)]))
    return vysledek


OPERACE_ODPISU = "odpis-nedobytne-pohledavky"
OPERACE_UHRADY_ODPISU = "uhrada-odepsane-pohledavky"
ROLE_ODPISU = "naklady.odpis_pohledavky"
ROLE_UHRADY_ODPISU = "vynosy.odepsane_pohledavky"


class ChybaOdpisu(ValueError):
    pass


@dataclass
class Odpis:
    datum: date
    castka: int = 0
    polozka: str = ""  # položka správy, do jejíchž nákladů odpis šel
    rozhodnuti: str = ""
    dluhy: list[str] = field(default_factory=list)  # co přesně se odepsalo
    zbyva: int = 0  # co z odpisu dlužník ještě nezaplatil


@dataclass
class Odepsane:
    jednotka: str
    odpisy: list[Odpis] = field(default_factory=list)  # od nejstaršího
    uhrazeno: int = 0

    @property
    def odepsano(self) -> int:
        return sum(o.castka for o in self.odpisy)

    @property
    def zbyva(self) -> int:
        return sum(o.zbyva for o in self.odpisy)


def odepsane(session: Session) -> dict[str, Odepsane]:
    """Odepsané dluhy po jednotkách přes všechny roky a co z nich dlužníci zaplatili.
    Úhrady se započítávají na nejstarší odpis."""
    radky = session.execute(
        select(
            Zapis.id,
            Zapis.datum,
            Zapis.operace,
            RadekZapisu.strana,
            RadekZapisu.role,
            RadekZapisu.jednotka,
            RadekZapisu.sluzba,
            RadekZapisu.popis,
            RadekZapisu.castka,
        )
        .join(Zapis)
        .where(
            Zapis.operace.in_((OPERACE_ODPISU, OPERACE_UHRADY_ODPISU)),
            RadekZapisu.jednotka.is_not(None),
            denik.nestornovany(),
        )
        .order_by(Zapis.datum, Zapis.id, RadekZapisu.id)
    ).all()
    vysledek: dict[str, Odepsane] = {}
    odpisy: dict[int, Odpis] = {}
    for zapis_id, datum, operace, strana, role, jednotka, sluzba, popis, castka in radky:
        o = vysledek.setdefault(jednotka, Odepsane(jednotka))
        if operace == OPERACE_UHRADY_ODPISU:
            if role == ROLE_UHRADY_ODPISU:
                o.uhrazeno += castka if strana == "d" else -castka
            continue
        if zapis_id not in odpisy:
            odpisy[zapis_id] = Odpis(datum)
            o.odpisy.append(odpisy[zapis_id])
        odpis = odpisy[zapis_id]
        if role == ROLE_ODPISU and strana == "md":
            odpis.castka += castka
            odpis.polozka = sluzba or ""
            odpis.rozhodnuti = popis or ""
        elif role in pocatecni.ROLE_VLASTNIKU and strana == "d" and popis:
            odpis.dluhy.append(popis)
    for o in vysledek.values():
        zaplaceno = o.uhrazeno
        for odpis in o.odpisy:
            odpis.zbyva = odpis.castka - min(odpis.castka, zaplaceno)
            zaplaceno -= odpis.castka - odpis.zbyva
    return {j: o for j, o in vysledek.items() if o.odpisy}


def zauctuj_odpis(
    session: Session,
    profil: Profil,
    nastaveni: predpisy.Nastaveni,
    rok: int,
    *,
    jednotka: str,
    castka: int,
    polozka: str,
    rozhodnuti: str,
    zauctoval: str,
    dnes: date | None = None,
) -> Zapis:
    """Odepíše nedobytný dluh jednotky, od nejstaršího. Každá odepsaná část odkazuje
    na dluh, ze kterého je, takže ji pozdější platby neberou za nezaplacenou."""
    dnes = dnes or date.today()
    rozhodnuti = rozhodnuti.strip()
    if jednotka not in profil.jednotky:
        raise ChybaOdpisu(f"Jednotku {jednotka} SVJ nemá.")
    if polozka not in profil.sprava:
        raise ChybaOdpisu("Vyberte položku správy, do jejíchž nákladů odpis patří.")
    if not rozhodnuti:
        raise ChybaOdpisu("Napište, kdo a kdy o odpisu rozhodl.")
    if len(rozhodnuti) > 200:
        raise ChybaOdpisu("Popis rozhodnutí je příliš dlouhý, zkraťte ho na 200 znaků.")
    if castka <= 0:
        raise ChybaOdpisu("Odepisovaná částka musí být kladná.")
    if rok > dnes.year:
        raise ChybaOdpisu(f"Rok {rok} ještě nezačal.")
    if denik.aktivni(session, vyuctovani_spravy.klic(rok)) is not None:
        raise ChybaOdpisu(
            f"Vyúčtování záloh na správu za rok {rok} už je zaúčtované, takže by odpis mezi "
            "vlastníky nerozdělilo. Stornujte ho v Deníku, odepište dluh a zálohy vyúčtujte "
            "znovu."
        )
    dluh = next(d for d in prehled(session, profil, nastaveni, rok, dnes) if d.jednotka == jednotka)
    if castka > dluh.saldo:
        raise ChybaOdpisu(
            f"Jednotka {jednotka} dluží jen {kc(dluh.saldo)}."
            if dluh.saldo > 0
            else f"Jednotka {jednotka} nic nedluží."
        )
    radky = [
        katalog.Radek(
            "md",
            ROLE_ODPISU,
            castka,
            {"jednotka": jednotka, "sluzba": polozka, "popis": rozhodnuti},
        )
    ]
    zbyva = castka
    for p in dluh.polozky:
        cast = min(p.zbyva, zbyva)
        if cast <= 0:
            continue
        dimenze = {"jednotka": jednotka, "popis": p.popis[:200]}
        if p.radek is not None:
            dimenze["urceno_na"] = str(p.radek)
        radky.append(katalog.Radek("d", p.role, cast, dimenze))
        zbyva -= cast
        if not zbyva:
            break
    return denik.zauctuj(
        session,
        profil,
        katalog.nacti()[OPERACE_ODPISU],
        {
            "jednotka": jednotka,
            "castka": na_text(castka),
            "polozka": polozka,
            "rozhodnuti": rozhodnuti,
        },
        datum=dnes if rok == dnes.year else date(rok, 12, 31),
        popis=f"Odpis nedobytného dluhu jednotky {jednotka}",
        doklad="ID",
        zauctoval=zauctoval,
        radky=radky,
    )


def radky_uhrady_odpisu(
    session: Session, operace: katalog.Operace, vstupy: dict[str, str], krok: str | None = None
) -> list[katalog.Radek]:
    """Řádky platby dříve odepsaného dluhu: výnos jde do položky správy, do které šel
    odpis (od nejstaršího odpisu), aby ji vyúčtování záloh na správu zase snížilo."""
    jednotka = vstupy["jednotka"]
    castka = halire(vstupy["castka"])
    o = odepsane(session).get(jednotka)
    if o is None or o.zbyva <= 0:
        raise ChybaOdpisu(f"Jednotka {jednotka} nemá odepsaný dluh, který by zbýval zaplatit.")
    if castka > o.zbyva:
        raise ChybaOdpisu(
            f"Platba je vyšší než odepsaný dluh jednotky {jednotka}, který zbývá zaplatit "
            f"({kc(o.zbyva)})."
        )
    podle_polozky: dict[str, int] = {}
    zbyva = castka
    for odpis in o.odpisy:
        cast = min(odpis.zbyva, zbyva)
        if cast:
            podle_polozky[odpis.polozka] = podle_polozky.get(odpis.polozka, 0) + cast
            zbyva -= cast
    return [
        r
        for polozka, cast in podle_polozky.items()
        for r in katalog.sestav(
            operace, {**vstupy, "polozka": polozka, "castka": na_text(cast)}, krok
        )
    ]
