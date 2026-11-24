"""Dlouhodobý majetek SVJ: evidence, odpisový plán, odpisy a vyřazení (příručka, kapitola 6).

Majetek se pořizuje fakturou na účet nedokončeného majetku (042, u nehmotného 041)
a zařazením do užívání vznikne karta. Zařazení převede cenu na účet majetku a určí, z čeho
je pořízení kryté:

- **fond oprav**: pořízení se uhradí z fondu (955/901) a ve výši ročních odpisů se zdroj
  vrací (901/955); odpis zároveň uhradí fond (955/649), takže fond oprav se kvůli majetku
  sníží jen jednou a výsledek hospodaření je nulový (Durec s. 70–71),
- **fond ze zisku** (nezálohové příspěvky): 911/901 a ve výši odpisů 901/911,
- **položka správy**: bez vlastního jmění; odpisy jsou nákladem položky a vlastníci je
  zaplatí ve vyúčtování záloh na správu podle klíče položky.

Odepisuje se rovnoměrně po měsících od měsíce po zařazení, kumulativně zaokrouhleno na
celé koruny, takže součet odpisů přesně dá cenu. Pozemky se neodepisují. Majetek převzatý
z počátečních stavů zápis o zařazení nemá; jeho zůstatková cena k převzetí se odepisuje
rovnoměrně ve zbývajících měsících plánu.

Řádky zápisů majetku nesou kód karty (`MAJ-<id>`) v dimenzi služby, kromě nákladu na
odpisy hrazeného položkou správy, který nese kód položky.
"""

from dataclasses import dataclass, replace
from datetime import date

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from . import denik, fond_ze_zisku
from .db import Majetek, RadekZapisu, Zapis
from .domena import katalog
from .domena.penize import kc, na_text
from .domena.profil import NeznamaRole, Profil

OPERACE_ZARAZENI = denik.OPERACE_ZARAZENI_MAJETKU
OPERACE_ODPISU = "majetek-odpisy"
OPERACE_VYRAZENI = "majetek-vyrazeni"
NEJDELE_MESICU = 100 * 12


@dataclass(frozen=True)
class Druh:
    nazev: str
    majetek: str
    opravky: str | None  # pozemky se neodepisují
    porizovani: str


DRUHY = {
    "movity": Druh("Hmotná movitá věc", "majetek", "opravky_majetku", "majetek_porizovani"),
    "stavba": Druh(
        "Stavba nebo jednotka", "majetek_stavby", "opravky_staveb", "majetek_porizovani"
    ),
    "pozemek": Druh("Pozemek", "majetek_pozemky", None, "majetek_porizovani"),
    "nehmotny": Druh(
        "Nehmotný majetek (software na zakázku)",
        "majetek_nehmotny",
        "opravky_nehmotneho",
        "majetek_nehmotny_porizovani",
    ),
}
# Z čeho je pořízení kryté (mimo položky správy): role fondu a název pro lidi.
FONDY = {
    "fond_oprav": ("zalohy_dlouhodobe", "fond oprav"),
    "fond_ze_zisku": ("fond_ze_zisku", "fond ze zisku"),
}
ROLE = ("zdroj_majetku", "naklady.odpisy")


class ChybaMajetku(ValueError):
    pass


def _ma(profil: Profil, *role: str | None) -> bool:
    return all(r is None or r in profil.role for r in role)


def druhy(profil: Profil) -> dict[str, Druh]:
    """Druhy majetku, pro které má SVJ v profilu účty."""
    if not _ma(profil, *ROLE):
        return {}
    return {k: d for k, d in DRUHY.items() if _ma(profil, d.majetek, d.opravky, d.porizovani)}


def kryti(profil: Profil) -> dict[str, str]:
    """Kód → název možností krytí, které SVJ má."""
    vysledek = {k: n for k, (role, n) in FONDY.items() if role in profil.role}
    if "vynosy.zuctovani_dlouhodobych_zaloh" not in profil.role:
        vysledek.pop("fond_oprav", None)
    for k, u in profil.sprava.items():
        vysledek[k] = f"provozní zálohy: {u.get('nazev', k)}"
    return vysledek


def _d(d: date) -> str:
    return f"{d.day}. {d.month}. {d.year}"


def _mesic_po(d: date) -> date:
    return date(d.year + d.month // 12, d.month % 12 + 1, 1)


def _mesicu(od: date, do: date) -> int:
    """Počet celých měsíců od prvního dne `od` do prvního dne `do`."""
    return (do.year - od.year) * 12 + do.month - od.month


# ---------- Odpisový plán ----------


@dataclass(frozen=True)
class Plan:
    """Rovnoměrné odpisování `zaklad` haléřů v `mesicu` měsících od měsíce `od`."""

    od: date | None  # první měsíc odpisování; None = neodepisuje se
    mesicu: int
    zaklad: int

    def kumulativne(self, n: int) -> int:
        """Odepsáno za prvních `n` měsíců, na celé koruny, poslední měsíc dorovná."""
        n = max(0, min(n, self.mesicu))
        if n == self.mesicu:
            return self.zaklad
        return (2 * self.zaklad * n + self.mesicu * 100) // (2 * self.mesicu * 100) * 100

    def do_konce(self, rok: int, mesic: int = 12) -> int:
        """Odepsáno podle plánu do konce měsíce `mesic` roku `rok` (včetně)."""
        if self.od is None:
            return 0
        return self.kumulativne(_mesicu(self.od, date(rok, mesic, 1)) + 1)

    def za_rok(self, rok: int) -> int:
        return self.do_konce(rok) - self.do_konce(rok - 1)

    @property
    def posledni_rok(self) -> int | None:
        if self.od is None or not self.mesicu:
            return None
        konec = self.od.month - 1 + self.mesicu - 1
        return self.od.year + konec // 12


def plan(m: Majetek) -> Plan:
    if m.doba_mesicu is None:
        return Plan(None, 0, 0)
    od = _mesic_po(m.zarazeno)
    if m.prevzato_k is None:
        return Plan(od, m.doba_mesicu, m.cena)
    # Převzatý majetek: zbytek ceny rovnoměrně ve zbývajících měsících plánu (aspoň jeden).
    uplynulo = max(0, _mesicu(od, m.prevzato_k))
    zbyva = m.cena - m.opravky_prevzate
    if zbyva <= 0:
        return Plan(None, 0, 0)
    start = max(od, m.prevzato_k)
    return Plan(start, max(1, m.doba_mesicu - uplynulo), zbyva)


# ---------- Stav podle deníku ----------


def _klic_odpisu(m: Majetek, rok: int) -> str:
    return f"{OPERACE_ODPISU}:{m.id}:{rok}"


def _klic_vyrazeni(m: Majetek) -> str:
    return f"{OPERACE_VYRAZENI}:{m.id}"


def vyrazeni(s: Session, m: Majetek) -> Zapis | None:
    return denik.aktivni(s, _klic_vyrazeni(m))


def odpis_zauctovany(s: Session, m: Majetek, rok: int) -> Zapis | None:
    return denik.aktivni(s, _klic_odpisu(m, rok))


def _opravky(s: Session, profil: Profil, m: Majetek, do: date | None = None) -> int:
    """Oprávky karty podle deníku (D − MD na účtu oprávek s kódem karty) a k převzetí."""
    role = DRUHY[m.druh].opravky
    if role is None:
        return 0
    d_minus_md = func.sum(
        case((RadekZapisu.strana == "d", RadekZapisu.castka), else_=-RadekZapisu.castka)
    )
    podminky = [
        RadekZapisu.ucet == profil.ucet(role),
        RadekZapisu.sluzba == m.kod,
        denik.nestornovany(),
    ]
    if do is not None:
        podminky.append(Zapis.datum <= do)
    z = s.scalar(select(d_minus_md).join(Zapis).where(*podminky)) or 0
    # Vyřazení oprávky odúčtuje; pro stav karty před vyřazením je počítat nechceme.
    if (v := vyrazeni(s, m)) is not None and (do is None or v.datum <= do):
        z += m.cena
    return int(z) + m.opravky_prevzate


@dataclass
class RokPlanu:
    rok: int
    odpis: int
    opravky: int  # na konci roku
    zustatek: int


@dataclass
class StavMajetku:
    majetek: Majetek
    druh: str
    kryti: str
    opravky: int  # k datu
    zustatkova: int
    odpis_roku: int  # podle plánu (nebo zaúčtovaný)
    odpis_zauctovan: bool
    vyrazeno: date | None
    plan: list[RokPlanu]


def nazev_kryti(profil: Profil, kod: str) -> str:
    return kryti(profil).get(kod, kod)


def stav(s: Session, profil: Profil, m: Majetek, rok: int, k_datu: date) -> StavMajetku:
    p = plan(m)
    v = vyrazeni(s, m)
    opravky = _opravky(s, profil, m, k_datu)
    zapis_odpisu = odpis_zauctovany(s, m, rok)
    if zapis_odpisu is not None:
        odpis = sum(
            r.castka for r in zapis_odpisu.radky if r.role == "naklady.odpisy" and r.strana == "md"
        )
    elif v is not None and v.datum.year <= rok:
        odpis = 0
    else:
        odpis = p.za_rok(rok)
    radky: list[RokPlanu] = []
    if p.od is not None and p.posledni_rok is not None:
        for r in range(p.od.year, p.posledni_rok + 1):
            kum = m.opravky_prevzate + p.do_konce(r)
            radky.append(RokPlanu(r, p.za_rok(r), kum, m.cena - kum))
    return StavMajetku(
        majetek=m,
        druh=DRUHY[m.druh].nazev,
        kryti=nazev_kryti(profil, m.kryti),
        opravky=opravky,
        zustatkova=m.cena - opravky if v is None or v.datum > k_datu else 0,
        odpis_roku=odpis,
        odpis_zauctovan=zapis_odpisu is not None,
        vyrazeno=v.datum if v is not None else None,
        plan=radky,
    )


def karty(s: Session) -> list[Majetek]:
    return [
        m
        for m in s.scalars(select(Majetek).order_by(Majetek.zarazeno, Majetek.id)).all()
        if m.platny
    ]


def k_zarazeni(s: Session, profil: Profil) -> dict[str, int]:
    """Role pořizování → částka na nedokončeném majetku, která ještě není zařazená."""
    vysledek = {}
    for role in {d.porizovani for d in druhy(profil).values()}:
        md_minus_d = func.sum(
            case((RadekZapisu.strana == "md", RadekZapisu.castka), else_=-RadekZapisu.castka)
        )
        z = s.scalar(
            select(md_minus_d)
            .join(Zapis)
            .where(
                RadekZapisu.ucet == profil.ucet(role),
                denik.nestornovany(),
                Zapis.operace.not_in(denik.UZAVERKA),
            )
        )
        vysledek[role] = int(z or 0)
    return vysledek


# ---------- Účtování ----------


def _zauctuj(s: Session, profil: Profil, operace: str, vstupy, radky, **kw) -> Zapis:
    try:
        return denik.zauctuj(s, profil, katalog.nacti()[operace], vstupy, radky=radky, **kw)
    except (denik.ChybaUctovani, NeznamaRole) as e:
        raise ChybaMajetku(str(e)) from e


def _s_kodem(radky: list[katalog.Radek], m: Majetek) -> list[katalog.Radek]:
    """Doplní kód karty do dimenze služby; náklad hrazený položkou správy nechá s položkou."""
    polozka = m.kryti not in FONDY
    return [
        r
        if polozka and r.role == "naklady.odpisy"
        else replace(r, dimenze={**r.dimenze, "sluzba": m.kod})
        for r in radky
    ]


def _vstupy_kryti(m: Majetek, castka: int) -> dict[str, str]:
    """Vstupy pro odpis nebo doodepsání `castka` podle toho, z čeho je majetek kryty."""
    if m.kryti in FONDY:
        return {
            "sluzba": "",
            "zdroj": FONDY[m.kryti][0],
            "vraceni": na_text(castka),
            "kryti": na_text(castka if m.kryti == "fond_oprav" else 0),
        }
    return {"sluzba": m.kryti, "zdroj": "", "vraceni": "0", "kryti": "0"}


def zarad(
    s: Session,
    profil: Profil,
    *,
    nazev: str,
    druh: str,
    zarazeno: date,
    cena: int,
    doba_mesicu: int | None,
    kryti_kod: str,
    inventarni_cislo: str = "",
    poznamka: str = "",
    prevzato_k: date | None = None,
    opravky_prevzate: int = 0,
    zauctoval: str,
) -> Majetek:
    """Zařadí majetek do užívání (nebo ho převezme z počátečních stavů) a založí kartu."""
    if druh not in druhy(profil):
        raise ChybaMajetku("Vyberte, o jaký majetek jde.")
    nazev = " ".join(nazev.split())
    if not nazev:
        raise ChybaMajetku("Napište, co SVJ pořídilo (třeba „robotická sekačka“).")
    if cena <= 0:
        raise ChybaMajetku("Pořizovací cena musí být kladná.")
    d = DRUHY[druh]
    if d.opravky is None:
        doba_mesicu = None
    elif doba_mesicu is None or not 1 <= doba_mesicu <= NEJDELE_MESICU:
        raise ChybaMajetku(
            "Napište, kolik let se má majetek odepisovat podle odpisového plánu SVJ."
        )
    if kryti_kod not in kryti(profil):
        raise ChybaMajetku("Vyberte, z čeho je pořízení majetku kryté.")
    if prevzato_k is not None:
        if prevzato_k.month != 1 or prevzato_k.day != 1:
            raise ChybaMajetku("Majetek se přebírá z počátečních stavů k 1. 1.")
        if zarazeno >= prevzato_k:
            raise ChybaMajetku(
                f"Převzít jde jen majetek zařazený před {_d(prevzato_k)}. Nový majetek "
                "zařaďte z faktury za pořízení."
            )
        if d.opravky is None:
            opravky_prevzate = 0
        if not 0 <= opravky_prevzate <= cena:
            raise ChybaMajetku("Oprávky k převzetí musí být od nuly do pořizovací ceny.")
    else:
        opravky_prevzate = 0
        volne = k_zarazeni(s, profil).get(d.porizovani, 0)
        if cena > volne:
            raise ChybaMajetku(
                f"Na pořizování majetku je nezařazeno jen {kc(volne)}. Nejdřív zadejte "
                "faktury za pořízení na stránce Faktury jako pořízení majetku."
            )
        if kryti_kod == "fond_ze_zisku":
            try:
                fond_ze_zisku.zkontroluj_cerpani(s, profil, cena, zarazeno)
            except fond_ze_zisku.ChybaFondu as e:
                raise ChybaMajetku(str(e)) from e
    m = Majetek(
        nazev=nazev[:150],
        inventarni_cislo=inventarni_cislo.strip()[:32],
        poznamka=poznamka.strip(),
        druh=druh,
        zarazeno=zarazeno,
        cena=cena,
        doba_mesicu=doba_mesicu,
        kryti=kryti_kod,
        prevzato_k=prevzato_k,
        opravky_prevzate=opravky_prevzate,
        upravil=zauctoval,
    )
    s.add(m)
    s.flush()
    if prevzato_k is not None:
        return m
    fond = FONDY.get(kryti_kod)
    vstupy = {
        "majetek": d.majetek,
        "porizovani": d.porizovani,
        "castka": na_text(cena),
        "zdroj": fond[0] if fond else "",
        "kryti": na_text(cena if fond else 0),
    }
    op = katalog.nacti()[OPERACE_ZARAZENI]
    z = _zauctuj(
        s,
        profil,
        OPERACE_ZARAZENI,
        vstupy,
        _s_kodem(katalog.sestav(op, vstupy), m),
        datum=zarazeno,
        popis=f"Zařazení majetku: {m.nazev}",
        doklad="ID",
        zauctoval=zauctoval,
    )
    m.zapis_id = z.id
    m.zapis = z
    return m


def _karta(s: Session, majetek_id: int) -> Majetek:
    m = s.get(Majetek, majetek_id)
    if m is None or not m.platny:
        raise ChybaMajetku("Tento majetek v evidenci není, nebo bylo jeho zařazení stornované.")
    return m


def k_odepsani(s: Session, rok: int) -> list[tuple[Majetek, int]]:
    """Karty s nezaúčtovaným odpisem za rok a výše odpisu podle plánu."""
    vysledek = []
    for m in karty(s):
        if DRUHY[m.druh].opravky is None or odpis_zauctovany(s, m, rok) is not None:
            continue
        v = vyrazeni(s, m)
        if v is not None and v.datum.year <= rok:
            continue
        castka = plan(m).za_rok(rok)
        if castka:
            vysledek.append((m, castka))
    return vysledek


def zauctuj_odpisy(
    s: Session, profil: Profil, rok: int, *, zauctoval: str, dnes: date
) -> list[Zapis]:
    """Zaúčtuje k 31. 12. roční odpisy všech karet, které je ještě nemají."""
    if dnes < date(rok, 12, 31):
        raise ChybaMajetku(f"Odpisy za rok {rok} půjde zaúčtovat od 31. 12. {rok}.")
    od = min((m.zarazeno.year for m in karty(s)), default=rok)
    for r in range(od, rok):
        if k_odepsani(s, r):
            raise ChybaMajetku(f"Nejdřív zaúčtujte odpisy za rok {r}.")
    seznam = k_odepsani(s, rok)
    if not seznam:
        raise ChybaMajetku(f"Za rok {rok} není co odepsat.")
    op = katalog.nacti()[OPERACE_ODPISU]
    zapisy = []
    for m, castka in seznam:
        vstupy = {"opravky": DRUHY[m.druh].opravky, "castka": na_text(castka)}
        vstupy |= _vstupy_kryti(m, castka)
        zapisy.append(
            _zauctuj(
                s,
                profil,
                OPERACE_ODPISU,
                vstupy,
                _s_kodem(katalog.sestav(op, vstupy), m),
                datum=date(rok, 12, 31),
                popis=f"Odpis majetku za rok {rok}: {m.nazev}",
                doklad="ID",
                zauctoval=zauctoval,
                idempotencni_klic=_klic_odpisu(m, rok),
            )
        )
    return zapisy


def vyrad(
    s: Session, profil: Profil, majetek_id: int, *, datum: date, duvod: str, zauctoval: str
) -> Zapis:
    """Vyřadí majetek: doodepíše zůstatkovou cenu a odúčtuje ho proti oprávkám."""
    m = _karta(s, majetek_id)
    d = DRUHY[m.druh]
    if d.opravky is None:
        raise ChybaMajetku(
            "Prodej nebo vyřazení pozemku aplikace nezaúčtuje. Postup proberte s účetní."
        )
    if vyrazeni(s, m) is not None:
        raise ChybaMajetku("Majetek už je vyřazený.")
    duvod = " ".join(duvod.split())
    if not duvod:
        raise ChybaMajetku("Napište, proč se majetek vyřazuje (prodej, zničení, ztráta…).")
    if datum < m.zarazeno:
        raise ChybaMajetku("Vyřadit majetek jde až po dni zařazení.")
    for r in range(m.zarazeno.year, datum.year):
        if plan(m).za_rok(r) and odpis_zauctovany(s, m, r) is None:
            raise ChybaMajetku(f"Nejdřív zaúčtujte odpisy za rok {r}.")
    zbyva = m.cena - _opravky(s, profil, m)
    vstupy = {
        "majetek": d.majetek,
        "opravky": d.opravky,
        "cena": na_text(m.cena),
        "zbyva": na_text(zbyva),
    } | _vstupy_kryti(m, zbyva)
    op = katalog.nacti()[OPERACE_VYRAZENI]
    return _zauctuj(
        s,
        profil,
        OPERACE_VYRAZENI,
        vstupy,
        _s_kodem(katalog.sestav(op, vstupy), m),
        datum=datum,
        popis=f"Vyřazení majetku: {m.nazev}. {duvod}"[:500],
        doklad="ID",
        zauctoval=zauctoval,
        idempotencni_klic=_klic_vyrazeni(m),
    )


def uprav(
    s: Session, majetek_id: int, *, nazev: str, inventarni_cislo: str, poznamka: str, upravil: str
) -> Majetek:
    """Popisné údaje karty; částky se opravují stornem zařazení."""
    m = _karta(s, majetek_id)
    nazev = " ".join(nazev.split())
    if not nazev:
        raise ChybaMajetku("Název majetku nesmí být prázdný.")
    m.nazev = nazev[:150]
    m.inventarni_cislo = inventarni_cislo.strip()[:32]
    m.poznamka = poznamka.strip()
    m.upravil = upravil
    return m


def smaz_prevzaty(s: Session, majetek_id: int) -> None:
    """Smaže kartu převzatou z počátečních stavů, dokud k ní není zaúčtovaný žádný zápis."""
    m = _karta(s, majetek_id)
    if m.prevzato_k is None:
        raise ChybaMajetku("Zařazený majetek se ruší stornem zápisu o zařazení na stránce Deník.")
    navazuje = s.scalar(
        select(Zapis.id)
        .join(RadekZapisu)
        .where(RadekZapisu.sluzba == m.kod, denik.nestornovany())
        .limit(1)
    )
    if navazuje is not None:
        raise ChybaMajetku(
            "K majetku už jsou zaúčtované odpisy. Nejdřív je stornujte na stránce Deník."
        )
    s.delete(m)


# ---------- Kontrola proti účtům ----------


@dataclass
class Nesoulad:
    ucet: str
    nazev: str
    v_evidenci: int
    v_ucetnictvi: int


def soupis(s: Session, profil: Profil, k_datu: date) -> dict[str, list[tuple[str, int]]]:
    """Účet → karty s cenou (u majetku) nebo oprávkami (u oprávek, záporně) k datu."""
    vysledek: dict[str, list[tuple[str, int]]] = {}
    for m in karty(s):
        if m.zarazeno > k_datu:
            continue
        v = vyrazeni(s, m)
        if v is not None and v.datum <= k_datu:
            continue
        d = DRUHY[m.druh]
        popis = " · ".join(x for x in (m.inventarni_cislo, m.nazev) if x)
        vysledek.setdefault(profil.ucet(d.majetek), []).append((popis, m.cena))
        if d.opravky is not None:
            o = _opravky(s, profil, m, k_datu)
            if o:
                vysledek.setdefault(profil.ucet(d.opravky), []).append((popis, -o))
    return vysledek


def nesoulad(s: Session, profil: Profil, zustatky: dict[str, int], k_datu: date) -> list[Nesoulad]:
    """Účty majetku a oprávek, na kterých se evidence nerovná zůstatku v účetnictví."""
    evidence = {u: sum(c for _, c in p) for u, p in soupis(s, profil, k_datu).items()}
    ucty = {
        profil.ucet(r)
        for d in druhy(profil).values()
        for r in (d.majetek, d.opravky)
        if r is not None
    }
    return [
        Nesoulad(u, profil.nazvy_uctu.get(u, u), evidence.get(u, 0), zustatky.get(u, 0))
        for u in sorted(ucty)
        if evidence.get(u, 0) != zustatky.get(u, 0)
    ]
