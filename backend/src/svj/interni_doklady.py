"""Interní doklady podle operací z katalogu.

Operace, které nemají vlastní stránku (časové rozlišení, dohadná položka, zásoby, dotace,
odměny výboru…), jde zaúčtovat obecným formulářem. U každé je tu popsané, jaká pole
formulář ukáže a co v nich jde vybrat; hodnoty se před zaúčtováním zkontrolují. Operace,
pro kterou profil SVJ nemá všechny účty, se nenabízí.

Operace s vlastní stránkou (předpisy, faktury, úvěr, majetek, úrok z prodlení, odpis dluhu,
daň, vyúčtování, uzávěrka) se tu záměrně nenabízejí: tam aplikace hlídá víc než formulář.
"""

from dataclasses import dataclass, field
from datetime import date

from sqlalchemy.orm import Session

from . import denik, faktury
from .db import Zapis
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


@dataclass(frozen=True)
class Formular:
    pole: tuple[Pole, ...]
    kroky: dict[str, str] = field(default_factory=dict)  # krok → co znamená
    napoveda: str = ""


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
            Pole("poskytovatel", "Kdo dotaci poskytl", "text"),
            Pole("castka", "Část dotace na náklady tohoto roku"),
        ),
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


def moznosti(profil: Profil, typ: str) -> dict[str, str] | None:
    """Hodnoty, ze kterých se v poli vybírá (hodnota → popis); None u volného pole."""
    if typ == "jednotka":
        return {j: j for j in profil.jednotky}
    if typ == "sluzba":
        return {k: u.get("nazev", k) for k, u in profil.sluzby.items()}
    if typ == "naklad_spravy":
        return {k: profil.sprava[k].get("nazev", k) for k in _naklady_spravy(profil)}
    return None


def _vstupy(profil: Profil, formular: Formular, zadane: dict[str, object]) -> dict[str, str]:
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
        mozne = moznosti(profil, pole.typ)
        if mozne is not None and text not in mozne:
            raise ChybaDokladu(f"Vyberte „{pole.popis}“ z nabídky.")
        if pole.typ == "naklad_spravy":
            vstupy["kategorie"] = _naklady_spravy(profil)[text].vstupy["kategorie"]
        vstupy[pole.klic] = text
    if "hruba" in castky and castky["dan"] + castky["pojistne_clen"] > castky["hruba"]:
        raise ChybaDokladu("Daň a pojištění sražené členovi nemůžou být vyšší než hrubá odměna.")
    if vstupy.get("z_sluzby") and vstupy.get("z_sluzby") == vstupy.get("do_sluzby"):
        raise ChybaDokladu("Vyberte dvě různé služby.")
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
    profil: Profil, operace_id: str, krok: str | None, zadane: dict[str, object]
) -> list[Radek]:
    """Řádky, které by se zaúčtovaly: účty z profilu SVJ a částky."""
    op, formular = _formular(operace_id)
    radky = katalog.sestav(op, _vstupy(profil, formular, zadane), _krok(formular, krok))
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
    vstupy = _vstupy(profil, formular, zadane)
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
