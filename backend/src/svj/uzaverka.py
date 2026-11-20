"""Uzávěrka roku: kontrolní seznam, výkazy, inventurní soupisy a posouzení daně z příjmů.

Kontrolní seznam vychází z výčtu uzávěrkových operací a oblastí inventarizace v knize
Durec, Účetnictví SVJ, 3. vyd., s. 80–82. Co jde ověřit z dat, aplikace ověří sama; zbytek
zůstane jako bod, který musí odškrtnout člověk.
"""

from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import case, exists, func, select
from sqlalchemy.orm import Session, aliased

from . import (
    banka,
    denik,
    dluznici,
    pocatecni,
    predpisy,
    rozhodnuti,
    vyuctovani_sluzeb,
    vyuctovani_spravy,
)
from .db import BankovniPohyb, BankovniUcet, BankovniVypis, Faktura, RadekZapisu, Zapis
from .domena import katalog, vykazy
from .domena.profil import Profil

# Názvy řádků zkrácené rozvahy a výkazu zisku a ztráty pro nevýdělečné organizace
# (vyhláška 504/2002 Sb., přílohy č. 1 a 2).
NAZVY_RADKU = {
    ("aktiva", "A.I"): "Dlouhodobý nehmotný majetek",
    ("aktiva", "A.II"): "Dlouhodobý hmotný majetek",
    ("aktiva", "A.III"): "Dlouhodobý finanční majetek",
    ("aktiva", "A.IV"): "Oprávky k dlouhodobému majetku",
    ("aktiva", "B.I"): "Zásoby",
    ("aktiva", "B.II"): "Pohledávky",
    ("aktiva", "B.III"): "Krátkodobý finanční majetek",
    ("aktiva", "B.IV"): "Jiná aktiva",
    ("pasiva", "A.I"): "Jmění",
    ("pasiva", "A.II"): "Výsledek hospodaření",
    ("pasiva", "B.I"): "Rezervy",
    ("pasiva", "B.II"): "Dlouhodobé závazky",
    ("pasiva", "B.III"): "Krátkodobé závazky",
    ("pasiva", "B.IV"): "Jiná pasiva",
    ("naklady", "A.I"): "Spotřebované nákupy a nakupované služby",
    ("naklady", "A.II"): "Změny stavu zásob vlastní činnosti a aktivace",
    ("naklady", "A.III"): "Osobní náklady",
    ("naklady", "A.IV"): "Daně a poplatky",
    ("naklady", "A.V"): "Ostatní náklady",
    ("naklady", "A.VI"): "Odpisy, prodaný majetek, tvorba a použití rezerv a opravných položek",
    ("naklady", "A.VII"): "Poskytnuté příspěvky",
    ("naklady", "A.VIII"): "Daň z příjmů",
    ("vynosy", "B.I"): "Provozní dotace",
    ("vynosy", "B.II"): "Přijaté příspěvky",
    ("vynosy", "B.III"): "Tržby za vlastní výkony a za zboží",
    ("vynosy", "B.IV"): "Ostatní výnosy",
    ("vynosy", "B.V"): "Tržby z prodeje majetku",
}

ROLE_VLASTNIKU = set(pocatecni.ROLE_VLASTNIKU)


# ---------- Kontrolní seznam ----------


@dataclass
class Kontrola:
    kod: str  # stálý identifikátor bodu; podle něj se ukládá ruční odškrtnutí
    nazev: str
    stav: str  # hotovo | chybi | rucne | info
    detail: str = ""
    odkaz: str | None = None  # stránka aplikace, kde se to řeší


def _zustatek_role(profil: Profil, zust: dict[str, int], role: str) -> int:
    try:
        return zust.get(profil.ucet(role), 0)
    except KeyError:
        return 0


def _d(d: date) -> str:
    return f"{d.day}. {d.month}. {d.year}"


def _kc(halire: int) -> str:
    cele, hal = divmod(abs(int(halire)), 100)
    text = f"{cele:,}".replace(",", " ") + f",{hal:02d} Kč"
    return ("−" if halire < 0 else "") + text


def kontroly(
    session: Session, profil: Profil, nastaveni: predpisy.Nastaveni, rok: int, k_datu: date
) -> list[Kontrola]:
    zust = denik.zustatky(session, rok, k_datu)
    vysledek: list[Kontrola] = []

    if pocatecni.zauctovany(session, rok):
        vysledek.append(Kontrola("pocatecni", "Počáteční stavy k 1. 1. jsou zaúčtované", "hotovo"))
    else:
        vysledek.append(
            Kontrola(
                "pocatecni",
                "Počáteční stavy k 1. 1. jsou zaúčtované",
                "chybi",
                "Bez nich nesedí rozvaha ani dluhy vlastníků z minulých let.",
                "pocatecni",
            )
        )

    chybi = predpisy.dalsi_k_zauctovani(session, nastaveni, rok)
    vysledek.append(
        Kontrola("predpisy", "Předpisy záloh za všechny měsíce jsou zaúčtované", "hotovo")
        if chybi is None
        else Kontrola(
            "predpisy",
            "Předpisy záloh za všechny měsíce jsou zaúčtované",
            "chybi",
            f"Chybí předpis za {predpisy.MESICE[chybi - 1]} {rok}.",
            "predpisy",
        )
    )

    nezauctovane = session.scalar(
        select(func.count())
        .select_from(BankovniPohyb)
        .where(
            func.extract("year", BankovniPohyb.datum) == rok,
            BankovniPohyb.datum <= k_datu,
            ~exists().where(banka.zauctovano(BankovniPohyb.id)),
        )
    )
    vysledek.append(
        Kontrola("pohyby", "Všechny pohyby na bankovních účtech jsou zaúčtované", "hotovo")
        if not nezauctovane
        else Kontrola(
            "pohyby",
            "Všechny pohyby na bankovních účtech jsou zaúčtované",
            "chybi",
            f"Nezaúčtovaných pohybů: {nezauctovane}.",
            "banka",
        )
    )

    for b in session.scalars(select(BankovniUcet).order_by(BankovniUcet.id)):
        vysledek.append(_kontrola_vypisu(session, profil, zust, b, rok, k_datu))

    for role, nazev, proc in (
        ("penize_na_ceste", "Peníze na cestě jsou vyrovnané", "Převod mezi účty nedošel."),
        (
            "nevyjasnene_prijmy",
            "Nevyjasněné příjmy jsou vyřešené",
            "Některé příjmy ještě nemají určeno, od koho a za co jsou.",
        ),
        (
            "nevyjasnene_vydaje",
            "Výdaje bez dokladu jsou doložené",
            "Některým výdajům chybí doklad od dodavatele.",
        ),
        (
            "vnitrni_zuctovani",
            "Vnitřní zúčtování je vyrovnané",
            "Po vyúčtování na něm nemá nic zůstat.",
        ),
    ):
        z = _zustatek_role(profil, zust, role)
        vysledek.append(
            Kontrola(role, nazev, "hotovo")
            if z == 0
            else Kontrola(role, nazev, "chybi", f"{proc} Zůstatek {_kc(z)}.")
        )

    v = vyuctovani_spravy.spocitej(session, profil, rok)
    vysledek.append(
        Kontrola("vyuctovani-spravy", "Zálohy na správu domu jsou vyúčtované", "hotovo")
        if v.zapis
        else Kontrola(
            "vyuctovani-spravy",
            "Zálohy na správu domu jsou vyúčtované",
            "chybi",
            "Zaúčtujte vyúčtování správy k 31. 12.",
            "vyuctovani",
        )
    )

    zalohy_sluzeb = sum(
        c for u, c in zust.items() if profil.role_uctu().get(u, "").startswith("zalohy_sluzby.")
    )
    naklady_sluzeb = sum(
        c for u, c in zust.items() if profil.role_uctu().get(u, "").startswith("naklady_sluzeb.")
    )
    vysledek.append(
        Kontrola("vyuctovani-sluzeb", "Zálohy na služby jsou vyúčtované", "hotovo")
        if (zalohy_sluzeb == 0 and naklady_sluzeb == 0)
        or denik.aktivni(session, vyuctovani_sluzeb.klic(rok)) is not None
        else Kontrola(
            "vyuctovani-sluzeb",
            "Zálohy na služby jsou vyúčtované",
            "chybi",
            f"Zálohy na služby {_kc(-zalohy_sluzeb)}, náklady na služby {_kc(naklady_sluzeb)}. "
            "Zaúčtujte vyúčtování služeb k 31. 12.",
            "vyuctovani",
        )
    )

    zavazky = -sum(p.castka for p in _rozpis_dodavatelu(session, profil, rok, k_datu))
    if zavazky:
        vysledek.append(
            Kontrola(
                "faktury",
                "Nezaplacené faktury odpovídají závazkům",
                "info",
                f"K {_d(k_datu)} dluží SVJ dodavatelům {_kc(zavazky)}; rozpis po fakturách je "
                "v inventurním soupisu. U větších částek je dobré stav ověřit u dodavatele.",
                "faktury",
            )
        )

    k_overeni = _postupy_k_overeni(session, rok, k_datu)
    if k_overeni:
        seznam = "; ".join(f"{nazev} ({pocet}×)" for nazev, pocet in k_overeni)
        vysledek.append(
            Kontrola(
                "postupy-k-overeni",
                "Postupy, které nepotvrdila účetní, jsou posouzené",
                "rucne",
                f"Letos se účtovalo i podle postupů, které účetní zatím nepotvrdila: {seznam}. "
                "Zápisy platí. Účetní by měla postup potvrdit, nebo navrhnout jiný pro další rok.",
                "denik",
            )
        )

    dluhy = [
        d for d in dluznici.prehled(session, profil, nastaveni, rok, k_datu) if d.z_minulych_let
    ]
    if dluhy:
        vysledek.append(
            Kontrola(
                "stare-dluhy",
                "Staré dluhy vlastníků jsou posouzené",
                "rucne",
                f"Dluh z minulých let má {len(dluhy)} jednotek. Rozhodněte, zda jsou pochybné a "
                "zda je vymáhat; pochybné pohledávky se uvádějí v příloze k závěrce.",
                "dluznici",
            )
        )

    bez = rozhodnuti.bez_rozhodnuti(session, profil, nastaveni, rok)
    vysledek.append(
        Kontrola("rozhodnuti", "Výše záloh, klíče a volby mají doložené rozhodnutí", "hotovo")
        if not bez
        else Kontrola(
            "rozhodnuti",
            "Výše záloh, klíče a volby mají doložené rozhodnutí",
            "chybi",
            "Bez doloženého rozhodnutí: " + "; ".join(p.nazev for p in bez) + ".",
            "rozhodnuti",
        )
    )

    vysledek.extend(
        Kontrola(k, n, "rucne", d)
        for k, n, d in (
            (
                "casove-rozliseni",
                "Náklady patří do správného roku",
                "Pojištění nebo předplatné placené dopředu na další rok patří do nákladů příštích "
                "období; prosincové dodávky bez faktury se zaúčtují odhadem jako dohadná položka.",
            ),
            (
                "pojistne-udalosti",
                "Pojistné události a dotace jsou zachycené",
                "Opravu po škodě, kterou pojišťovna teprve proplatí, a dotaci, na kterou už vznikl "
                "nárok, je potřeba zaúčtovat do tohoto roku.",
            ),
            (
                "majetek",
                "Majetek společenství je zkontrolovaný",
                "Pokud SVJ vlastní věci (nářadí, vybavení, zásoby), zkontrolujte je fyzicky.",
            ),
        )
    )
    return vysledek


def _postupy_k_overeni(session: Session, rok: int, k_datu: date) -> list[tuple[str, int]]:
    """Operace ve stavu `overit`, podle kterých se v roce účtovalo (bez stornovaných zápisů)."""
    operace = {o.id: o.nazev for o in katalog.nacti().values() if o.stav == "overit"}
    if not operace:
        return []
    oprava = aliased(Zapis)
    pocty = session.execute(
        select(Zapis.operace, func.count())
        .where(
            Zapis.rok == rok,
            Zapis.datum <= k_datu,
            Zapis.operace.in_(operace),
            ~exists().where(oprava.opravuje_zapis == Zapis.id, oprava.operace == "storno"),
        )
        .group_by(Zapis.operace)
        .order_by(Zapis.operace)
    )
    return [(operace[o], int(n)) for o, n in pocty]


def _kontrola_vypisu(
    session: Session, profil: Profil, zust: dict[str, int], b: BankovniUcet, rok: int, k_datu: date
) -> Kontrola:
    kod = f"vypis-{b.ucel}"
    nazev = f"Zůstatek účtu {b.cislo} souhlasí s výpisem"
    try:
        v_ucetnictvi = zust.get(profil.ucet(f"banka.{b.ucel}"), 0)
    except KeyError:
        return Kontrola(kod, nazev, "rucne", "Účet nemá v profilu SVJ určený účet v účetnictví.")
    vypis = session.scalar(
        select(BankovniVypis)
        .where(
            BankovniVypis.ucet_id == b.id,
            BankovniVypis.novy_zustatek.is_not(None),
            BankovniVypis.datum <= k_datu,
            BankovniVypis.rok == rok,
        )
        .order_by(BankovniVypis.datum.desc(), BankovniVypis.id.desc())
    )
    if vypis is None:
        return Kontrola(
            kod, nazev, "rucne", "Chybí výpis se zůstatkem; porovnejte zůstatek ručně.", "banka"
        )
    if vypis.datum < k_datu:
        return Kontrola(
            kod,
            nazev,
            "rucne",
            f"Poslední nahraný výpis je k {_d(vypis.datum)} "
            f"(zůstatek {_kc(vypis.novy_zustatek or 0)}). "
            f"Nahrajte výpis k {_d(k_datu)}.",
            "banka",
        )
    if vypis.novy_zustatek == v_ucetnictvi:
        return Kontrola(kod, nazev, "hotovo", f"Obojí {_kc(v_ucetnictvi)}.")
    return Kontrola(
        kod,
        nazev,
        "chybi",
        f"Výpis {_kc(vypis.novy_zustatek or 0)}, účetnictví {_kc(v_ucetnictvi)}.",
        "banka",
    )


# ---------- Výkazy ----------


@dataclass
class RadekVykazu:
    strana: str
    radek: str
    nazev: str
    castka: int
    tisice: int


def _rozpad_vlastniku(session: Session, rok: int, k_datu: date) -> dict[str, list[int]]:
    return predpisy.zustatky_vlastniku(session, rok, k_datu)


def vykaz_radky(v: vykazy.Vykaz) -> list[RadekVykazu]:
    tisice = v.v_tisicich()
    return [
        RadekVykazu(s, r, NAZVY_RADKU.get((s, r), r), c, tisice[(s, r)])
        for (s, r), c in sorted(v.radky.items())
    ]


def vykazy_roku(session: Session, rok: int, k_datu: date) -> tuple[vykazy.Vykaz, vykazy.Vykaz]:
    zust = denik.zustatky(session, rok, k_datu)
    return vykazy.rozvaha(zust, _rozpad_vlastniku(session, rok, k_datu)), vykazy.vysledovka(zust)


# ---------- Inventurní soupisy ----------


@dataclass
class PolozkaSoupisu:
    popis: str
    castka: int


@dataclass
class Soupis:
    ucet: str
    nazev: str
    zustatek: int  # kladný na straně MD
    zpusob: str
    polozky: list[PolozkaSoupisu] = field(default_factory=list)


def _zpusob(role: str) -> str:
    if role.startswith("banka."):
        return "Dokladová inventura: porovnání se zůstatkem na výpisu z účtu k rozvahovému dni."
    if role.startswith("pokladna"):
        return "Fyzická inventura: přepočítání hotovosti v pokladně."
    if role in ROLE_VLASTNIKU:
        return "Dokladová inventura: rozpis po vlastnících, porovnání předpisů s platbami."
    if role == "dodavatele":
        return (
            "Dokladová inventura: seznam nezaplacených faktur, u vyšších částek ověření "
            "u dodavatele."
        )
    if role.startswith("zalohy_dodavatelum"):
        return "Dokladová inventura: zaplacené zálohy dodavatelům proti jejich vyúčtování."
    if role.startswith("zalohy_dlouhodobe"):
        return "Dokladová inventura: předpisy dlouhodobých záloh a jejich čerpání podle rozhodnutí."
    return "Dokladová inventura podle účetních dokladů."


def _rozpis_dodavatelu(
    session: Session, profil: Profil, rok: int, k_datu: date
) -> list[PolozkaSoupisu]:
    """Zůstatek závazků po fakturách (párovací symbol), kladný na straně MD."""
    znamenko = func.sum(
        case((RadekZapisu.strana == "md", RadekZapisu.castka), else_=-RadekZapisu.castka)
    )
    dotaz = (
        select(RadekZapisu.parovaci_symbol, znamenko)
        .join(Zapis)
        .where(RadekZapisu.ucet == profil.ucet("dodavatele"))
        .group_by(RadekZapisu.parovaci_symbol)
    )
    dotaz = dotaz.where(Zapis.rok == rok, Zapis.datum <= k_datu)
    radky = session.execute(dotaz).all()
    faktury = {f.cislo: f for f in session.scalars(select(Faktura))}
    vysledek = []
    for symbol, z in radky:
        if not z:
            continue
        f = faktury.get(symbol or "")
        if f:
            popis = f"FP {f.cislo} · {f.dodavatel}" + (
                f" · faktura {f.cislo_dodavatele}" if f.cislo_dodavatele else ""
            )
            popis += f" · splatná {_d(f.splatnost)}"
        else:
            popis = (
                f"doklad {symbol}"
                if symbol
                else "převzato v počátečním stavu nebo bez určení faktury"
            )
        vysledek.append(PolozkaSoupisu(popis, int(z)))
    return vysledek


SKUPINY_ROLI = {
    "zalohy_sluzby": "Přijaté zálohy na služby",
    "zalohy_sprava": "Přijaté zálohy na správu domu",
    "naklady_sluzeb": "Náklady na služby k vyúčtování",
    "naklady_spravy": "Náklady na správu k vyúčtování",
    "zalohy_dodavatelum": "Zálohy zaplacené dodavatelům",
}


def _nazev_uctu(profil: Profil, ucet: str, role: str) -> str:
    if ucet in profil.nazvy_uctu:
        return profil.nazvy_uctu[ucet]
    zaklad, _, kod = role.partition(".")
    if zaklad in SKUPINY_ROLI:
        polozka = profil.polozky(zaklad).get(kod, {}).get("nazev", kod)
        return f"{SKUPINY_ROLI[zaklad]}: {polozka}"
    return ucet


def soupisy(session: Session, profil: Profil, rok: int, k_datu: date) -> list[Soupis]:
    znamenko = func.sum(
        case((RadekZapisu.strana == "md", RadekZapisu.castka), else_=-RadekZapisu.castka)
    )
    v_roce = (Zapis.rok == rok, Zapis.datum <= k_datu)
    ucty = session.execute(
        select(RadekZapisu.ucet, func.min(RadekZapisu.role), znamenko)
        .join(Zapis)
        .where(*v_roce)
        .group_by(RadekZapisu.ucet)
        .order_by(RadekZapisu.ucet)
    ).all()
    role_uctu = profil.role_uctu()
    vysledek = []
    for ucet, role_radku, z in ucty:
        if ucet[0] in "56" or ucet[:2] in vykazy.NEVYKAZUJE_SE:
            continue
        role = role_uctu.get(ucet, role_radku)
        s = Soupis(ucet, _nazev_uctu(profil, ucet, role), int(z), _zpusob(role))
        if role in ROLE_VLASTNIKU:
            rozpis = session.execute(
                select(RadekZapisu.jednotka, RadekZapisu.protistrana, znamenko)
                .join(Zapis)
                .where(*v_roce, RadekZapisu.ucet == ucet)
                .group_by(RadekZapisu.jednotka, RadekZapisu.protistrana)
                .order_by(RadekZapisu.jednotka, RadekZapisu.protistrana)
            ).all()
            s.polozky = [
                PolozkaSoupisu(
                    f"jednotka {j}" + (f", dřívější vlastník {p}" if p else "")
                    if j
                    else (p or "bez jednotky"),
                    int(c),
                )
                for j, p, c in rozpis
                if c
            ]
        elif role == "dodavatele":
            s.polozky = _rozpis_dodavatelu(session, profil, rok, k_datu)
        vysledek.append(s)
    return vysledek


# ---------- Daň z příjmů ----------


@dataclass
class VynosProDan:
    popis: str
    castka: int
    zdaneni: str  # nepredmetne | srazkova | predmetne | nezname
    poznamka: str = ""


# Podle role výnosového účtu (kniha s. 85–87; ZDP § 18 odst. 2 písm. f), § 36 odst. 5).
DAN_PODLE_ROLE = {
    "vynosy.predpis": ("nepredmetne", "Příspěvky vlastníků na správu domu"),
    "vynosy.pausal": ("nepredmetne", "Příspěvky vlastníků (paušální složky předpisu)"),
    "vynosy.prevod_do_vyuctovani": (
        "nepredmetne",
        "Příspěvky vlastníků a úhrady za služby z vyúčtování",
    ),
    "vynosy.pojistne_plneni": ("nepredmetne", "Pojistné plnění z pojištění domu"),
    "vynosy.dotace": ("nepredmetne", "Dotace"),
    "vynosy.uroky": ("srazkova", "Úroky z bankovních účtů (daň srazila banka)"),
    "vynosy.urok_z_prodleni": ("predmetne", "Úroky z prodlení od vlastníků"),
    "vynosy.pacht": (
        "predmetne",
        "Pacht nebo nájem společných částí účtovaný jako výnos SVJ",
    ),
}
# Když role nic neřekne, rozhodne účtová skupina.
DAN_PODLE_SKUPINY = {
    "64": ("predmetne", "Ostatní výnosy"),
    "641": ("predmetne", "Smluvní pokuty a úroky z prodlení"),
    "642": ("predmetne", "Ostatní pokuty a penále"),
    "644": ("srazkova", "Úroky"),
    "646": ("predmetne", "Výnosy z prodeje majetku"),
    "648": ("predmetne", "Čerpání fondů"),
    "649": ("nepredmetne", "Příspěvky vlastníků"),
    "65": ("predmetne", "Prodej majetku"),
    "69": ("nepredmetne", "Dotace"),
}
POZNAMKY_DANE = {
    "vynosy.pacht": "Nájemné a pacht ze společných částí jsou příjmem vlastníků, ne SVJ "
    "(NV 366/2013 § 16 odst. 2; kniha s. 77–79), a SVJ je pak nedaní. "
    "Katalog pro ně má operace najem-predpis a prijmy-vlastniku. Vyjasněte s účetní.",
    "vynosy.urok_z_prodleni": "Daní se až po zaplacení (§ 23 odst. 3 ZDP), ne už při vyúčtování.",
}


@dataclass
class Dan:
    musi_podat: bool
    vynosy: list[VynosProDan]


def dan(session: Session, profil: Profil, rok: int) -> Dan:
    zust = denik.zustatky(session, rok)
    role_uctu = profil.role_uctu()
    vynosy: list[VynosProDan] = []
    for ucet, z in sorted(zust.items()):
        if ucet[0] != "6" or z == 0:
            continue
        role = role_uctu.get(ucet, "")
        if role in DAN_PODLE_ROLE:
            zdaneni, popis = DAN_PODLE_ROLE[role]
        else:
            zdaneni, popis = next(
                (DAN_PODLE_SKUPINY[k] for k in (ucet[:3], ucet[:2]) if k in DAN_PODLE_SKUPINY),
                ("nezname", "Výnos, o kterém aplikace neví, jak se daní"),
            )
        vynosy.append(VynosProDan(f"{popis} ({ucet})", -z, zdaneni, POZNAMKY_DANE.get(role, "")))
    return Dan(any(v.zdaneni in ("predmetne", "nezname") for v in vynosy), vynosy)


# ---------- Příloha k účetní závěrce ----------

DOPLNTE = "[doplňte]"


@dataclass
class OddilPrilohy:
    nadpis: str
    odstavce: list[str]


def priloha(
    session: Session, profil: Profil, nastaveni: predpisy.Nastaveni, rok: int, k_datu: date
) -> list[OddilPrilohy]:
    """Návrh přílohy ve zkráceném rozsahu (§ 30 vyhl. 504/2002, obsah podle knihy s. 83–84).

    Co aplikace z účetnictví neví, označí `[doplňte]`.
    """
    zust = denik.zustatky(session, rok, k_datu)
    role_uctu = profil.role_uctu()

    def soucet(predpona: str) -> int:
        return sum(z for u, z in zust.items() if u.startswith(predpona))

    _, vzz = vykazy_roku(session, rok, k_datu)
    vh = vzz.celkem["vysledek"]
    oddily = [
        OddilPrilohy(
            "Údaje o účetní jednotce",
            [
                f"{profil.nazev}, sídlo {profil.sidlo or DOPLNTE}, IČ {profil.ico or DOPLNTE}.",
                "Právní forma: společenství vlastníků jednotek. Účel: správa domu a pozemku "
                "podle § 1194 občanského zákoníku. Společenství nepodniká.",
                f"Statutární orgán: {profil.statutarni_organ or DOPLNTE}.",
            ],
        ),
        OddilPrilohy(
            "Účetní období a rozsah",
            [
                f"Účetním obdobím je kalendářní rok {rok}, rozvahovým dnem {_d(k_datu)}.",
                "Účetní závěrka je sestavena ve zkráceném rozsahu podle vyhlášky č. 504/2002 Sb. "
                "Částky ve výkazech jsou v celých tisících Kč.",
            ],
        ),
    ]

    metody = []
    if any(r.startswith("zalohy_sluzby") for r in role_uctu.values()):
        metody.append(
            "Předpis záloh na služby a na správu domu se účtuje na účtech účtových skupin 31 "
            "(pohledávky za vlastníky) a 32 (přijaté zálohy); dlouhodobé zálohy na opravy "
            "(fond oprav) na účtu 955."
        )
    if profil.prispevky == "zalohove":
        metody.append(
            "Příspěvky vlastníků na správu domu a pozemku se hradí zálohově. K rozvahovému dni "
            "se stanoví ve výši nákladů na správu a uhradí se z přijatých záloh; rozdíl se "
            "vlastníkům vyúčtuje."
        )
    elif profil.prispevky == "nezalohove":
        metody.append("Příspěvky vlastníků na správu domu a pozemku se nehradí zálohově.")
    else:
        metody.append(f"Způsob úhrady příspěvků na správu: {DOPLNTE}.")
    if any(r.startswith("naklady_sluzeb") for r in role_uctu.values()):
        metody.append(
            "Služby se vlastníkům vyúčtovávají podle zákona č. 67/2013 Sb.; náklady na služby "
            "se účtují rozvahově a vyúčtují se k rozvahovému dni."
        )
    if soucet("0") == 0:
        metody.append("Společenství nemá dlouhodobý majetek ani zásoby.")
    else:
        metody.append(f"Dlouhodobý majetek a jeho odpisy: {DOPLNTE}.")
    dluhy = [
        d for d in dluznici.prehled(session, profil, nastaveni, rok, k_datu) if d.po_splatnosti
    ]
    if dluhy:
        metody.append(
            f"Pohledávky za vlastníky po splatnosti k rozvahovému dni činí "
            f"{_kc(sum(d.po_splatnosti for d in dluhy))} u {len(dluhy)} jednotek. "
            f"Opravné položky se netvoří. Pochybné pohledávky: {DOPLNTE}."
        )
    oddily.append(OddilPrilohy("Účetní metody", metody))

    fond = [u for u, r in role_uctu.items() if r.startswith("zalohy_dlouhodobe")]
    obraty = session.execute(
        select(
            func.sum(case((RadekZapisu.strana == "d", RadekZapisu.castka), else_=0)),
            func.sum(case((RadekZapisu.strana == "md", RadekZapisu.castka), else_=0)),
        )
        .join(Zapis)
        .where(
            Zapis.rok == rok,
            Zapis.datum <= k_datu,
            RadekZapisu.ucet.in_(fond),
            Zapis.operace != pocatecni.OPERACE,
            denik.platny(),
        )
    ).one()
    pocatek = -session.scalar(
        select(
            func.coalesce(
                func.sum(
                    case(
                        (RadekZapisu.strana == "md", RadekZapisu.castka), else_=-RadekZapisu.castka
                    )
                ),
                0,
            )
        )
        .join(Zapis)
        .where(Zapis.rok == rok, RadekZapisu.ucet.in_(fond), Zapis.operace == pocatecni.OPERACE)
    )
    konec = -sum(zust.get(u, 0) for u in fond)
    vyznamne = [
        f"Fond oprav (dlouhodobé zálohy vlastníků): k 1. 1. {_kc(pocatek)}, předepsáno a "
        f"převedeno {_kc(obraty[0] or 0)}, čerpáno {_kc(obraty[1] or 0)}, k {_d(k_datu)} "
        f"{_kc(konec)}."
    ]
    if soucet("95") != soucet("955") or soucet("46"):
        vyznamne.append(f"Úvěry: výše, úroková sazba a zajištění {DOPLNTE}.")
    if soucet("69"):
        vyznamne.append(f"Přijaté dotace {_kc(-soucet('69'))}; poskytovatel {DOPLNTE}.")
    oddily.append(OddilPrilohy("Významné položky rozvahy a výsledovky", vyznamne))

    odmeny = soucet("523")
    mzdy = soucet("521")
    oddily.append(
        OddilPrilohy(
            "Zaměstnanci a orgány společenství",
            [
                "Společenství nemělo zaměstnance."
                if mzdy == 0
                else f"Mzdové náklady {_kc(mzdy)}; průměrný počet zaměstnanců {DOPLNTE}.",
                "Členům výboru nebyly za rok vyplaceny odměny."
                if odmeny == 0
                else f"Odměny členům výboru za rok činí {_kc(odmeny)}.",
                f"Smlouvy se členy výboru nebo jejich blízkými osobami: {DOPLNTE}.",
            ],
        )
    )
    oddily.append(
        OddilPrilohy(
            "Ostatní údaje",
            [
                f"Splatné dluhy na pojistném a daňové nedoplatky: {DOPLNTE} (obvykle žádné).",
                f"Dluhy se splatností přes pět let a dluhy mimo rozvahu: {DOPLNTE} "
                "(obvykle žádné).",
                f"Výsledek hospodaření za rok {rok}: {_kc(vh)}. "
                f"Návrh na jeho vypořádání: {DOPLNTE}.",
            ],
        )
    )
    return oddily
