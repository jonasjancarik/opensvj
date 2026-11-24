"""Interní doklady podle operací z katalogu.

Operace, které nemají vlastní stránku (časové rozlišení, dohadná položka, zásoby, dotace,
odměny výboru…), jde zaúčtovat obecným formulářem. U každé je tu popsané, jaká pole
formulář ukáže a co v nich jde vybrat; hodnoty se před zaúčtováním zkontrolují. Operace,
pro kterou profil SVJ nemá všechny účty, se nenabízí.

Operace s vlastní stránkou (předpisy, faktury, úvěr, majetek, úrok z prodlení, odpis dluhu,
daň, vyúčtování, uzávěrka) se tu záměrně nenabízejí: tam aplikace hlídá víc než formulář.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import denik, faktury, ostatni_vynosy
from .db import RadekZapisu, Zapis
from .domena import katalog
from .domena.penize import kc, na_text
from .domena.profil import NeznamaRole, Profil

TYPY_CASTKY = ("castka", "castka_nula", "castka_se_znamenkem")


class ChybaDokladu(ValueError):
    pass


@dataclass(frozen=True)
class Pole:
    klic: str
    popis: str
    typ: str = "castka"  # castka | castka_nula | castka_se_znamenkem | text | výběr (viz _moznosti)


# Dopočet vstupů, které uživatel nezadává (z otevřených položek v účetnictví). Bez sezení
# (kontrola, jestli má profil účty) dosadí zástupné hodnoty.
Dopocet = Callable[[Session | None, Profil, dict[str, str], dict[str, int]], None]


@dataclass(frozen=True)
class Formular:
    pole: tuple[Pole, ...]
    kroky: dict[str, str] = field(default_factory=dict)  # krok → co znamená
    napoveda: str = ""
    dopocet: Dopocet | None = None


def _oznameni_pojistneho(
    s: Session | None, profil: Profil, vstupy: dict[str, str], castky: dict[str, int]
) -> None:
    """Oznámené plnění proti odhadu z 31. 12.: do výše odhadu, rozdíl do nákladů nebo výnosů."""
    oznameno = castky["castka"]
    if s is None:
        odhad, sluzba = oznameno, next(iter(profil.sprava), "")
    else:
        odhad = ostatni_vynosy.otevrene(s, profil, ostatni_vynosy.ODHADY_POJISTNEHO).get(
            vstupy["udalost"], 0
        )
        if odhad <= 0:
            raise ChybaDokladu("K této pojistné události není zaúčtovaný žádný odhad.")
        sluzba = (
            s.scalar(
                select(RadekZapisu.sluzba)
                .join(Zapis)
                .where(
                    RadekZapisu.ucet == profil.ucet(ostatni_vynosy.ODHADY_POJISTNEHO),
                    RadekZapisu.protistrana == vstupy["udalost"],
                    RadekZapisu.strana == "md",
                    denik.nestornovany(),
                )
                .order_by(Zapis.datum.desc())
            )
            or ""
        )
    vstupy |= {
        "sluzba": sluzba,
        "z_odhadu": na_text(min(oznameno, odhad)),
        "snizeni": na_text(max(odhad - oznameno, 0)),
        "navic": na_text(max(oznameno - odhad, 0)),
    }


def _pouziti_dotace(
    s: Session | None, profil: Profil, vstupy: dict[str, str], castky: dict[str, int]
) -> None:
    """Použít jde jen tolik, kolik z přiznané dotace ještě nešlo do výnosů."""
    if s is None:
        return
    zbyva = ostatni_vynosy.otevrene(s, profil, ostatni_vynosy.DOTACE_NAROK).get(
        vstupy["poskytovatel"], 0
    )
    if castky["castka"] > zbyva:
        raise ChybaDokladu(
            f"Z dotace od poskytovatele {vstupy['poskytovatel']} zbývá použít jen {kc(zbyva)}."
        )


FORMULARE: dict[str, Formular] = {
    "prijem-vyjasneni": Formular(
        (
            Pole("jednotka", "Jednotka, jejíž vlastník platbu poslal", "jednotka"),
            Pole("castka", "Částka"),
        ),
        napoveda="Platba, kterou jste v Bance zaúčtovali jako nespárovanou, se přiřadí vlastníkovi "
        "jednotky jako úhrada jeho záloh.",
    ),
    "casove-rozliseni": Formular(
        (
            Pole("sluzba", "Položka správy, ke které náklad patří", "naklad_spravy"),
            Pole("castka", "Část nákladu, která patří do příštího roku"),
        ),
        kroky={
            "k_rozvahovemu_dni": "K 31. 12.: odložit část nákladu do příštího roku",
            "rozpusteni": "V novém roce: vrátit odloženou část do nákladů",
        },
        napoveda="Typicky roční pojištění placené v průběhu roku: část, která patří do příštího "
        "roku, se k 31. 12. odloží a 1. 1. se vrátí do nákladů.",
    ),
    "dohadna-polozka": Formular(
        (Pole("sluzba", "Služba", "sluzba"), Pole("castka", "Odhad nákladu")),
        kroky={
            "k_rozvahovemu_dni": "K 31. 12.: zapsat odhad nákladu, ke kterému nepřišla faktura",
            "po_doruceni_faktury": "Faktura přišla: zrušit odhad",
        },
        napoveda="Když faktura přijde, zaúčtujte ji celou na stránce Faktury a tady zrušte "
        "odhad stejné služby ve stejné výši, jakou měl k 31. 12. V nákladech nového roku tak "
        "zůstane jen rozdíl mezi fakturou a odhadem.",
    ),
    "vydaj-bez-faktury": Formular(
        (
            Pole("sluzba", "Položka správy, ze které se výdaj platí", "naklad_spravy"),
            Pole("castka", "Částka"),
        ),
        kroky={"nahradni_doklad": "Náhradní doklad k výdaji, ke kterému chybí účtenka"},
        napoveda="Platbu jste v Bance zaúčtovali jako výdaj, ke kterému chybí doklad. Náhradní "
        "doklad ji převede do nákladů. Do popisu napište, co se koupilo, kdo o proplacení "
        "žádal a kdo výdaj schválil; ten, kdo o proplacení žádá, ho nemá schvalovat sám.",
    ),
    "prevod-vynosu-do-fo": Formular(
        (Pole("castka", "Součet výnosů, které se převádějí do fondu oprav"),),
        napoveda="Jen když společenství rozhodlo, že jeho výnosy (úroky, pacht, paušální složky "
        "předpisu) zvyšují fond oprav.",
    ),
    "zasoby-konec-roku": Formular(
        (
            Pole(
                "castka",
                "Hodnota zásob podle inventury (v novém roce stejnou částku se znaménkem minus)",
                "castka_se_znamenkem",
            ),
        ),
    ),
    "odmena-vyboru": Formular(
        (
            Pole("clen", "Člen výboru (funkce, ne jméno)", "text"),
            Pole("hruba", "Hrubá odměna"),
            Pole("dan", "Sražená daň nebo záloha na daň", "castka_nula"),
            Pole("pojistne_clen", "Pojištění sražené členovi", "castka_nula"),
            Pole("pojistne_svj", "Pojištění, které za člena platí společenství", "castka_nula"),
        ),
        napoveda="Jméno člena do deníku nepatří; stačí funkce, třeba „předseda výboru“.",
    ),
    "pochybne-pohledavky-vycleneni": Formular(
        (
            Pole(
                "castka",
                "Výše pochybných dluhů (zrušení vyčlenění se znaménkem minus)",
                "castka_se_znamenkem",
            ),
        ),
    ),
    "opravna-polozka-tvorba": Formular(
        (
            Pole(
                "castka",
                "Výše opravné položky (zrušení se znaménkem minus)",
                "castka_se_znamenkem",
            ),
        ),
    ),
    "smluvni-pokuta": Formular(
        (Pole("protistrana", "Dodavatel", "text"), Pole("castka", "Vyúčtovaná pokuta")),
        napoveda="Pokutu zaúčtujte v den, kdy ji SVJ dodavateli vyúčtovalo, a jen když je dost "
        "jisté, že ji zaplatí. Dodavatele napište stejně jako na jeho fakturách: pokutu pak jde "
        "na stránce Faktury započíst proti jeho faktuře, nebo její úhradu vybrat v Bance.",
    ),
    "najem-predpis": Formular(
        (Pole("najemce", "Nájemce", "text"), Pole("castka", "Nájemné za období")),
    ),
    "prijmy-vlastniku-prevod-do-fo": Formular(
        (
            Pole("jednotka", "Jednotka", "jednotka"),
            Pole("castka", "Podíl vlastníka, který zůstane ve fondu oprav"),
        ),
    ),
    "dotace-rozhodnuti": Formular(
        (Pole("poskytovatel", "Kdo dotaci poskytl", "text"), Pole("castka", "Přiznaná dotace")),
    ),
    "dotace-pouziti": Formular(
        (
            Pole("poskytovatel", "Kdo dotaci poskytl", "dotace"),
            Pole("castka", "Část dotace na náklady tohoto roku"),
        ),
        napoveda="Dotace patří do výnosů toho roku, kdy vznikly náklady, na které je. Když akce "
        "trvá víc let, rozdělte dotaci podle nákladů každého roku: stojí-li akce 1 000 000 Kč, "
        "letos z ní bylo 400 000 Kč nákladů a dotace je 450 000 Kč, letos použijte 180 000 Kč. "
        "Zbytek zůstane na další roky.",
        dopocet=_pouziti_dotace,
    ),
    "pojistne-plneni-narok": Formular(
        (
            Pole("udalost", "Pojistná událost (třeba „vytopený sklep 11/2026“)", "text"),
            Pole("sluzba", "Položka správy, ke které škoda patří", "naklad_spravy"),
            Pole("castka", "Plnění od pojišťovny"),
        ),
        kroky={
            "priznano": "K 31. 12.: pojišťovna už sdělila, kolik zaplatí",
            "odhad": "K 31. 12.: pojišťovna škodu uznala, výši zatím nesdělila (odhad)",
        },
        napoveda="Pojistné plnění patří do roku, kdy škoda vznikla, i když pojišťovna zaplatí "
        "až později. Když pojišťovna nárok zpochybňuje, nezapisujte nic. Odhad je obvykle "
        "škoda snížená o spoluúčast. Platbu od pojišťovny pak v Bance zaúčtujte jako úhradu "
        "pojistného plnění zaúčtovaného v roce škody.",
    ),
    "pojistne-plneni-oznameni": Formular(
        (
            Pole("udalost", "Pojistná událost s odhadem", "odhad_pojistneho"),
            Pole(
                "castka", "Plnění, které pojišťovna oznámila (0, když nárok odmítla)", "castka_nula"
            ),
        ),
        napoveda="Odhad z 31. 12. se nahradí oznámenou částkou. Rozdíl proti odhadu jde do "
        "nákladů, nebo výnosů letošního roku; minulý rok se neopravuje.",
        dopocet=_oznameni_pojistneho,
    ),
    "preuctovani-mezi-sluzbami": Formular(
        (
            Pole("z_sluzby", "Ze které služby", "sluzba"),
            Pole("do_sluzby", "Do které služby", "sluzba"),
            Pole("castka", "Částka podle zúčtovatele"),
        ),
        napoveda="Jedna faktura kryje víc služeb (třeba teplo na vytápění i ohřev vody) "
        "a rozdělení dodá zúčtovatel.",
    ),
}


# Kroky, které jen vyřeší dřívější zápis: nesmí převést víc, než na účtu zbývá.
# (operace, krok) → (role, strana zůstatku, co na účtu je)
ZBYVA = {
    ("vydaj-bez-faktury", "nahradni_doklad"): (
        "nevyjasnene_vydaje",
        "md",
        "výdajů bez dokladu",
    ),
    ("dohadna-polozka", "po_doruceni_faktury"): ("dohadne_pasivni", "d", "odhadů nákladů"),
}


def _zbyva(session: Session, profil: Profil, role: str, strana: str, datum: date) -> int:
    zustatek = denik.zustatky(session, datum.year, datum).get(profil.ucet(role), 0)
    return zustatek if strana == "md" else -zustatek


def _naklady_spravy(profil: Profil) -> dict[str, faktury.Druh]:
    """Položky správy, u kterých aplikace zná druh nákladu (podle faktur)."""
    return {
        d.vstupy["sluzba"]: d
        for d in faktury.DRUHY.values()
        if d.operace == "faktura-spravni-naklad" and d.vstupy["sluzba"] in profil.sprava
    }


# Výběr z otevřených položek v účetnictví: typ pole → (role, co je v popisku).
OTEVRENE = {
    "dotace": (ostatni_vynosy.DOTACE_NAROK, "zbývá použít"),
    "odhad_pojistneho": (ostatni_vynosy.ODHADY_POJISTNEHO, "odhad"),
}


def moznosti(profil: Profil, typ: str, session: Session | None = None) -> dict[str, str] | None:
    """Hodnoty, ze kterých se v poli vybírá (hodnota → popis); None u volného pole.

    Otevřené položky (dotace, odhady pojistného) jen se sezením; bez něj je pole volné."""
    if typ in OTEVRENE:
        if session is None:
            return None
        role, co = OTEVRENE[typ]
        return ostatni_vynosy.popisky(ostatni_vynosy.otevrene(session, profil, role), co)
    if typ == "jednotka":
        return {j: j for j in profil.jednotky}
    if typ == "sluzba":
        return {k: u.get("nazev", k) for k, u in profil.sluzby.items()}
    if typ == "naklad_spravy":
        return {k: profil.sprava[k].get("nazev", k) for k in _naklady_spravy(profil)}
    return None


def _vstupy(
    profil: Profil,
    formular: Formular,
    zadane: dict[str, object],
    session: Session | None = None,
) -> dict[str, str]:
    vstupy: dict[str, str] = {}
    castky: dict[str, int] = {}
    for pole in formular.pole:
        hodnota = zadane.get(pole.klic)
        if pole.typ in TYPY_CASTKY:
            if not isinstance(hodnota, int) or isinstance(hodnota, bool):
                raise ChybaDokladu(f"Vyplňte „{pole.popis}“.")
            if hodnota < 0 and pole.typ != "castka_se_znamenkem":
                raise ChybaDokladu(f"„{pole.popis}“ nesmí být záporná.")
            if hodnota == 0 and pole.typ != "castka_nula":
                raise ChybaDokladu(f"„{pole.popis}“ nesmí být nula.")
            vstupy[pole.klic] = na_text(hodnota)
            castky[pole.klic] = hodnota
            continue
        text = str(hodnota or "").strip()
        if not text:
            raise ChybaDokladu(f"Vyplňte „{pole.popis}“.")
        if len(text) > 128:
            raise ChybaDokladu(f"„{pole.popis}“ je příliš dlouhé.")
        mozne = moznosti(profil, pole.typ, session)
        if mozne is not None and text not in mozne:
            raise ChybaDokladu(f"Vyberte „{pole.popis}“ z nabídky.")
        if pole.typ == "naklad_spravy":
            vstupy["kategorie"] = _naklady_spravy(profil)[text].vstupy["kategorie"]
        vstupy[pole.klic] = text
    if "hruba" in castky and castky["dan"] + castky["pojistne_clen"] > castky["hruba"]:
        raise ChybaDokladu("Daň a pojištění sražené členovi nemůžou být vyšší než hrubá odměna.")
    if vstupy.get("z_sluzby") and vstupy.get("z_sluzby") == vstupy.get("do_sluzby"):
        raise ChybaDokladu("Vyberte dvě různé služby.")
    if formular.dopocet is not None:
        formular.dopocet(session, profil, vstupy, castky)
    return vstupy


@dataclass
class Radek:
    strana: str
    ucet: str
    nazev_uctu: str
    castka: int
    dimenze: dict[str, str]


def _formular(operace_id: str) -> tuple[katalog.Operace, Formular]:
    formular = FORMULARE.get(operace_id)
    op = katalog.nacti().get(operace_id)
    if formular is None or op is None:
        raise ChybaDokladu("Tuto operaci interním dokladem zaúčtovat nejde.")
    return op, formular


def _krok(formular: Formular, krok: str | None) -> str | None:
    if not formular.kroky:
        return None
    if krok not in formular.kroky:
        raise ChybaDokladu("Vyberte, který krok účtujete.")
    return krok


def nahled(
    profil: Profil,
    operace_id: str,
    krok: str | None,
    zadane: dict[str, object],
    session: Session | None = None,
) -> list[Radek]:
    """Řádky, které by se zaúčtovaly: účty z profilu SVJ a částky."""
    op, formular = _formular(operace_id)
    radky = katalog.sestav(op, _vstupy(profil, formular, zadane, session), _krok(formular, krok))
    try:
        return [
            Radek(r.strana, (u := profil.ucet(r.role)), profil.nazev_uctu(u), r.castka, r.dimenze)
            for r in radky
        ]
    except NeznamaRole as e:
        raise ChybaDokladu(f"V nastavení SVJ chybí účet: {e}") from e


def zauctuj(
    session: Session,
    profil: Profil,
    operace_id: str,
    krok: str | None,
    zadane: dict[str, object],
    *,
    datum: date,
    popis: str,
    zauctoval: str,
) -> Zapis:
    op, formular = _formular(operace_id)
    popis = popis.strip()
    if not popis:
        raise ChybaDokladu("Napište, čeho se doklad týká.")
    vstupy = _vstupy(profil, formular, zadane, session)
    krok = _krok(formular, krok)
    if (operace_id, krok) in ZBYVA:
        role, strana, co = ZBYVA[(operace_id, krok)]
        zbyva = _zbyva(session, profil, role, strana, datum)
        if int(zadane["castka"]) > zbyva:  # type: ignore[arg-type]
            raise ChybaDokladu(
                f"K {datum.day}. {datum.month}. {datum.year} zbývá vyřešit {kc(max(zbyva, 0))} "
                f"{co}, víc tímto dokladem vyřešit nejde."
            )
    try:
        return denik.zauctuj(
            session,
            profil,
            op,
            vstupy,
            datum=datum,
            popis=popis,
            doklad=op.doklad,
            zauctoval=zauctoval,
            krok=krok,
        )
    except (denik.ChybaUctovani, NeznamaRole) as e:
        raise ChybaDokladu(str(e)) from e


def dostupne(profil: Profil) -> dict[str, bool]:
    """U každé operace formuláře, jestli pro ni má profil SVJ všechny účty (zkusí sestavit
    zápis s první hodnotou z každého výběru)."""
    vysledek = {}
    for operace_id, formular in FORMULARE.items():
        zadane: dict[str, object] = {}
        for pole in formular.pole:
            mozne = moznosti(profil, pole.typ)
            if pole.typ in TYPY_CASTKY:
                zadane[pole.klic] = 1 if pole.typ == "castka_nula" else 100
            else:
                zadane[pole.klic] = next(iter(mozne), "") if mozne is not None else "x"
        if "z_sluzby" in zadane:
            sluzby = list(moznosti(profil, "sluzba") or {})
            zadane["do_sluzby"] = sluzby[1] if len(sluzby) > 1 else ""
        try:
            for krok in formular.kroky or [None]:
                nahled(profil, operace_id, krok, zadane)
            vysledek[operace_id] = True
        except (ChybaDokladu, katalog.ChybaKatalogu, KeyError):
            vysledek[operace_id] = False
    return vysledek
