"""Auditní záznam: kdo, kdy, co a proč změnil mimo deník.

Deník zápisy nemění, opravuje je stornem, takže historii nese sám. Ostatní údaje jdou
upravit i smazat: vlastníci a vlastnictví jednotek, rozhodnutí a jejich přiřazení,
předpis záloh zadaný v aplikaci, měřidla a odečty, výsledky zúčtovatele a stav účetního
roku. Každou jejich změnu zachytí posluchač sezení po zápisu do databáze (flush), takže
na ni nejde zapomenout v žádném místě aplikace. Záznam nese stav před změnou i po ní;
databáze ho nedovolí změnit ani smazat.

Změny se sbírají po každém flush a zapíšou se při commitu, jeden záznam za věc a transakci
(stav před prvním a po posledním zápisu). Když se transakce vrátí, nezapíše se nic.

Kdo změnu udělal, se bere z `kdo()` nastaveného na sezení, jinak z přihlášeného uživatele
(nastaví ho `prihlaseni.zapisujici`), jinak z údaje `upravil` u změněné věci. Důvod změny
nastaví `duvod()` a platí do konce transakce.
"""

import hashlib
import json
from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import event, insert, inspect, select
from sqlalchemy.orm import Session
from sqlalchemy.orm.util import identity_key

from .db import (
    AuditniZaznam,
    Meridlo,
    Obdobi,
    Odecet,
    Osoba,
    Rozhodnuti,
    RozhodnutiPro,
    VerzePredpisu,
    Vlastnictvi,
    VlastnikJednotky,
    VysledekZuctovatele,
    ZmenaPodilu,
)
from .domena.penize import kc

_uzivatel: ContextVar[tuple[str, str] | None] = ContextVar("auditni_uzivatel", default=None)

_KDO = "audit_kdo"
_DUVOD = "audit_duvod"
_NAZVY = "audit_nazvy"
_CEKA = "audit_ceka"


def nastav_uzivatele(email: str, jmeno: str = "") -> None:
    """Přihlášený uživatel, kterému se připíšou změny v tomto požadavku."""
    _uzivatel.set((email, jmeno))


def kdo(s: Session, email: str, jmeno: str = "") -> None:
    s.info[_KDO] = (email, jmeno)


def duvod(s: Session, text: str) -> None:
    """Proč se věc mění; připíše se ke všem změnám do konce transakce."""
    s.info[_DUVOD] = " ".join(text.split())


def pojmenuj(s: Session, druh: str, klic: str, nazev: str) -> None:
    """Čitelný název věci, který posluchač sám nezjistí (třeba položky doložení)."""
    s.info.setdefault(_NAZVY, {})[(druh, klic)] = nazev


def otisk(data: Any) -> str:
    """SHA-256 kanonického JSON: stejný obsah dá vždy stejný otisk."""
    text = json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    return hashlib.sha256(text.encode()).hexdigest()


def _d(d: date | str | None) -> str:
    if d is None or d == "":
        return "—"
    if isinstance(d, str):
        d = date.fromisoformat(d)
    return f"{d.day}. {d.month}. {d.year}"


# --- co se sleduje ------------------------------------------------------------------


@dataclass
class Pole:
    popisek: str
    format: Callable[[Any], str] | None = None


@dataclass
class Sledovani:
    druh: str
    nazev_druhu: str
    klic: Callable[[Any], str]
    nazev: Callable[[Session, Any], str]
    pole: dict[str, Pole]
    # Doplní do stavu údaje, které nejsou sloupcem (třeba seznam vlastníků).
    navic: Callable[[Session, Any, bool], dict[str, Any]] | None = None
    # Převede stav na dvojice popisek → hodnota pro zobrazení změn.
    ploche: Callable[[dict[str, Any]], dict[str, str]] | None = None


def _jmeno_osoby(s: Session, osoba_id: int | None) -> str:
    if osoba_id is None:
        return "—"
    o = s.identity_map.get(identity_key(Osoba, osoba_id)) or s.get(Osoba, osoba_id)
    return o.jmeno if o else f"osoba č. {osoba_id}"


def _clenove(s: Session, v: Vlastnictvi, pred: bool) -> dict[str, Any]:
    """Vlastníci jednotky před změnou nebo po ní, i se spoluvlastnickými podíly."""
    h = inspect(v).attrs.vlastnici.history
    if pred:
        radky = list(h.unchanged or ()) + list(h.deleted or ())
    else:
        radky = list(h.unchanged or ()) + list(h.added or ())
    vysledek = []
    for c in sorted(radky, key=lambda c: c.poradi if c.poradi is not None else 0):
        podil = c.podil
        if pred:
            hp = inspect(c).attrs.podil.history
            if hp.deleted:
                podil = hp.deleted[0]
        vysledek.append(
            {"osoba_id": c.osoba_id, "jmeno": _jmeno_osoby(s, c.osoba_id), "podil": podil}
        )
    return {"vlastnici": vysledek}


def _vlastnici(hodnota: list[dict]) -> str:
    return (
        ", ".join(v["jmeno"] + (f" ({v['podil']})" if v.get("podil") else "") for v in hodnota)
        or "—"
    )


def _popis_rozhodnuti(s: Session, rozhodnuti_id: int | None) -> str:
    if rozhodnuti_id is None:
        return ""
    from .rozhodnuti import popis

    r = s.identity_map.get(identity_key(Rozhodnuti, rozhodnuti_id)) or s.get(
        Rozhodnuti, rozhodnuti_id
    )
    return popis(r) if r else f"rozhodnutí č. {rozhodnuti_id}"


def _rozhodnuti_pro(s: Session, p: RozhodnutiPro, pred: bool) -> dict[str, Any]:
    rid = p.rozhodnuti_id
    if pred:
        h = inspect(p).attrs.rozhodnuti_id.history
        if h.deleted:
            rid = h.deleted[0]
    return {"rozhodnuti": _popis_rozhodnuti(s, rid)}


def _organ(kod: str) -> str:
    from .rozhodnuti import ORGANY

    return ORGANY.get(kod, kod)


def _druh_meridla(kod: str) -> str:
    from .meridla import DRUHY

    return DRUHY.get(kod, (kod,))[0]


_STAV_ROKU = {"otevrene": "otevřený", "v_uzaverce": "v uzávěrce", "uzavrene": "uzavřený"}
_KLICE_PREDPISU = {
    "plocha": "za m²",
    "osoby": "za osobu",
    "pevna": "částka u každé jednotky",
    "podil": "za dům, dělí se podle podílů",
    "jednotka": "za dům, každá jednotka stejně",
}


def _verze_ploche(stav: dict[str, Any]) -> dict[str, str]:
    """Předpis po jednotlivých částkách, aby u změny bylo vidět, co přesně se změnilo."""
    vysledek = {"Podklad": stav.get("zdroj") or "—"}
    nazvy = {x["kod"]: x["nazev"] for x in stav.get("slozky") or []}
    for x in stav.get("slozky") or []:
        jak = _KLICE_PREDPISU.get(x["klic"], x["klic"])
        sazba = f"{kc(x['sazba'])} {jak}" if x.get("sazba") is not None else jak
        vysledek[f"Složka {x['nazev']}"] = sazba
    for j, castky in sorted((stav.get("pevne") or {}).items()):
        komu = "ostatní jednotky" if j == "vychozi" else f"jednotka {j}"
        for kod, c in castky.items():
            vysledek[f"{nazvy.get(kod, kod)}, {komu}"] = kc(c)
    for j, pocet in sorted((stav.get("osoby") or {}).items()):
        komu = "ostatní jednotky" if j == "vychozi" else f"jednotka {j}"
        vysledek[f"Počet osob, {komu}"] = str(pocet)
    return vysledek


def _podily_ploche(stav: dict[str, Any]) -> dict[str, str]:
    vysledek = {"Podle čeho": stav.get("zdroj") or "—"}
    for j, podil in (stav.get("podily") or {}).items():
        vysledek[f"Podíl jednotky {j}"] = podil
    return vysledek


SLEDOVANE: dict[type, Sledovani] = {
    Osoba: Sledovani(
        "osoba",
        "Lidé",
        klic=lambda o: str(o.id),
        nazev=lambda s, o: o.jmeno,
        pole={
            "jmeno": Pole("Jméno"),
            "ico": Pole("IČO"),
            "adresa": Pole("Adresa pro doručování"),
            "email": Pole("E-mail"),
            "telefon": Pole("Telefon"),
            "ucet": Pole("Číslo účtu"),
            "souhlas_email": Pole("Souhlas s doručováním e-mailem od", _d),
            "poznamka": Pole("Poznámka"),
        },
    ),
    Vlastnictvi: Sledovani(
        "vlastnictvi",
        "Vlastnictví jednotek",
        klic=lambda v: str(v.id),
        nazev=lambda s, v: f"Vlastníci jednotky {v.jednotka} od {_d(v.plati_od)}",
        pole={
            "jednotka": Pole("Jednotka"),
            "plati_od": Pole("Vlastní od", _d),
            "plati_do": Pole("Vlastní do", _d),
            "vlastnici": Pole("Vlastníci", _vlastnici),
            "zdroj": Pole("Podle čeho"),
        },
        navic=_clenove,
    ),
    Meridlo: Sledovani(
        "meridlo",
        "Měřidla",
        klic=lambda m: str(m.id),
        nazev=lambda s, m: (
            f"Měřidlo {m.vyrobni_cislo}"
            + (f", jednotka {m.jednotka}" if m.jednotka else ", celý dům")
        ),
        pole={
            "jednotka": Pole("Jednotka"),
            "druh": Pole("Druh", _druh_meridla),
            "vyrobni_cislo": Pole("Výrobní číslo"),
            "umisteni": Pole("Umístění"),
            "osazeno_od": Pole("Osazeno od", _d),
            "odstraneno_do": Pole("Odstraněno", _d),
            "poznamka": Pole("Poznámka"),
        },
    ),
    Odecet: Sledovani(
        "odecet",
        "Odečty měřidel",
        klic=lambda o: str(o.id),
        nazev=lambda s, o: f"Odečet měřidla {_meridlo(s, o.meridlo_id)} k {_d(o.datum)}",
        pole={
            "datum": Pole("Datum", _d),
            "stav": Pole("Stav měřidla", lambda x: str(x).replace(".", ",")),
            "zdroj": Pole("Kdo odečetl"),
        },
    ),
    Rozhodnuti: Sledovani(
        "rozhodnuti",
        "Rozhodnutí",
        klic=lambda r: str(r.id),
        nazev=lambda s, r: _popis_rozhodnuti_obj(r),
        pole={
            "organ": Pole("Kdo rozhodl", _organ),
            "datum": Pole("Datum", _d),
            "bod": Pole("Bod"),
            "nazev": Pole("O čem"),
            "text": Pole("Text usnesení"),
            "hlasovani": Pole("Hlasování"),
            "ulozeni": Pole("Kde je zápis uložený"),
        },
    ),
    RozhodnutiPro: Sledovani(
        "prirazeni_rozhodnuti",
        "Doložení rozhodnutím",
        klic=lambda p: p.klic,
        nazev=lambda s, p: _drivejsi_nazev(s, "prirazeni_rozhodnuti", p.klic) or p.klic,
        pole={
            "rozhodnuti": Pole("Doloženo rozhodnutím"),
            "otisk": Pole("Otisk schválené podoby", lambda x: x[:12]),
        },
        navic=_rozhodnuti_pro,
    ),
    VerzePredpisu: Sledovani(
        "verze_predpisu",
        "Předpis záloh",
        klic=lambda v: v.plati_od.isoformat(),
        nazev=lambda s, v: f"Předpis záloh od {_d(v.plati_od)}",
        pole={"zdroj": Pole("Podklad"), "slozky": Pole(""), "pevne": Pole(""), "osoby": Pole("")},
        ploche=_verze_ploche,
    ),
    VysledekZuctovatele: Sledovani(
        "vysledek_zuctovatele",
        "Výsledky zúčtovatele",
        klic=lambda v: f"{v.rok}:{v.sluzba}:{v.jednotka}",
        nazev=lambda s, v: f"Výsledek zúčtovatele za {v.rok}, {v.sluzba}, jednotka {v.jednotka}",
        pole={"castka": Pole("Náklad jednotky", kc), "zdroj": Pole("Podle čeho")},
    ),
    ZmenaPodilu: Sledovani(
        "zmena_podilu",
        "Podíly na společných částech",
        klic=lambda z: z.plati_od.isoformat(),
        nazev=lambda s, z: f"Podíly jednotek od {_d(z.plati_od)}",
        pole={"zdroj": Pole("Podle čeho"), "podily": Pole("")},
        ploche=_podily_ploche,
    ),
    Obdobi: Sledovani(
        "obdobi",
        "Účetní roky",
        klic=lambda o: str(o.rok),
        nazev=lambda s, o: f"Účetní rok {o.rok}",
        pole={"stav": Pole("Stav roku", lambda x: _STAV_ROKU.get(x, x))},
    ),
}
PODLE_DRUHU = {sl.druh: sl for sl in SLEDOVANE.values()}


def _meridlo(s: Session, meridlo_id: int) -> str:
    m = s.identity_map.get(identity_key(Meridlo, meridlo_id)) or s.get(Meridlo, meridlo_id)
    return m.vyrobni_cislo if m else f"č. {meridlo_id}"


def _drivejsi_nazev(s: Session, druh: str, klic: str) -> str | None:
    """Název, pod kterým se věc zapsala naposled (když ji teď nejde pojmenovat)."""
    return s.scalar(
        select(AuditniZaznam.nazev)
        .where(AuditniZaznam.druh == druh, AuditniZaznam.klic == klic)
        .order_by(AuditniZaznam.id.desc())
        .limit(1)
    )


def _popis_rozhodnuti_obj(r: Rozhodnuti) -> str:
    from .rozhodnuti import popis

    return popis(r)


# --- zachycení změn -----------------------------------------------------------------


def _json(hodnota: Any) -> Any:
    if isinstance(hodnota, datetime | date):
        return hodnota.isoformat()
    if isinstance(hodnota, Decimal):
        return format(hodnota.normalize(), "f")
    return hodnota


def _stav(s: Session, sl: Sledovani, obj: Any, pred: bool) -> dict[str, Any]:
    st = inspect(obj)
    vysledek: dict[str, Any] = {}
    for nazev in sl.pole:
        if nazev not in st.mapper.column_attrs:
            continue
        hodnota = getattr(obj, nazev)
        if pred:
            h = st.attrs[nazev].history
            if h.deleted:
                hodnota = h.deleted[0]
        vysledek[nazev] = _json(hodnota)
    if sl.navic:
        vysledek |= sl.navic(s, obj, pred)
    return vysledek


def _kdo(s: Session, obj: Any) -> tuple[str, str]:
    return (
        s.info.get(_KDO)
        or _uzivatel.get()
        or ((obj.upravil, "") if getattr(obj, "upravil", None) else None)
        or ("neznámý", "")
    )


@event.listens_for(Session, "after_flush")
def _po_flush(s: Session, _kontext) -> None:
    """Zapamatuje si změny sledovaných věcí; zapíšou se až při commitu (`_pred_commitem`)."""
    zmenene: dict[int, tuple[str, Any]] = {}
    for akce, objekty in (("pridani", s.new), ("uprava", s.dirty), ("smazani", s.deleted)):
        for obj in objekty:
            if type(obj) in SLEDOVANE:
                zmenene.setdefault(id(obj), (akce, obj))
            elif isinstance(obj, VlastnikJednotky):
                # Změna vlastníků je změnou vlastnictví jednotky.
                v = obj.vlastnictvi
                if v is not None and id(v) not in zmenene and v not in s.deleted:
                    zmenene[id(v)] = ("pridani" if v in s.new else "uprava", v)
    nazvy = s.info.get(_NAZVY, {})
    ceka = s.info.setdefault(_CEKA, {})
    for akce, obj in zmenene.values():
        sl = SLEDOVANE[type(obj)]
        klic = sl.klic(obj)
        pred = None if akce == "pridani" else _stav(s, sl, obj, pred=True)
        po = None if akce == "smazani" else _stav(s, sl, obj, pred=False)
        email, jmeno = _kdo(s, obj)
        radek = {
            "kdo": email,
            "jmeno": jmeno,
            "druh": sl.druh,
            "klic": klic,
            "nazev": (nazvy.get((sl.druh, klic)) or sl.nazev(s, obj))[:300],
            "duvod": s.info.get(_DUVOD, ""),
            "pred": pred,
            "po": po,
        }
        drivejsi = ceka.get((sl.druh, klic))
        if drivejsi is not None:
            # Jedno uložení se někdy zapíše na několikrát (třeba vlastníci jednotky):
            # do záznamu jde stav před prvním a po posledním zápisu.
            radek["pred"] = drivejsi["pred"]
            radek["duvod"] = radek["duvod"] or drivejsi["duvod"]
        ceka[(sl.druh, klic)] = radek


@event.listens_for(Session, "before_commit")
def _pred_commitem(s: Session) -> None:
    s.flush()
    ceka = s.info.pop(_CEKA, {})
    radky = []
    for r in ceka.values():
        if r["pred"] == r["po"]:
            continue  # nic se nezměnilo, nebo věc vznikla a zase zanikla
        akce = "pridani" if r["pred"] is None else "smazani" if r["po"] is None else "uprava"
        radky.append(r | {"akce": akce})
    if radky:
        s.connection().execute(insert(AuditniZaznam), radky)


@event.listens_for(Session, "after_commit")
@event.listens_for(Session, "after_rollback")
def _konec_transakce(s: Session) -> None:
    for k in (_DUVOD, _NAZVY, _CEKA):
        s.info.pop(k, None)


# --- čtení --------------------------------------------------------------------------


DELKA_HODNOTY = 400


@dataclass
class Rozdil:
    pole: str
    pred: str
    po: str


def _ploche(sl: Sledovani, stav: dict[str, Any] | None) -> dict[str, str]:
    if stav is None:
        return {}
    if sl.ploche:
        return sl.ploche(stav)
    vysledek = {}
    for nazev, p in sl.pole.items():
        hodnota = stav.get(nazev)
        if hodnota is None or hodnota == "" or hodnota == []:
            text = "—"
        else:
            text = p.format(hodnota) if p.format else str(hodnota)
        if len(text) > DELKA_HODNOTY:
            text = text[: DELKA_HODNOTY - 1] + "…"
        vysledek[p.popisek] = text
    return vysledek


def rozdily(z: AuditniZaznam) -> list[Rozdil]:
    """Co se změnilo, po polích s čitelnými hodnotami."""
    sl = PODLE_DRUHU.get(z.druh)
    if sl is None:
        return []
    pred, po = _ploche(sl, z.pred), _ploche(sl, z.po)
    vysledek = []
    for pole in list(pred) + [p for p in po if p not in pred]:
        a, b = pred.get(pole, "—"), po.get(pole, "—")
        if a != b:
            vysledek.append(Rozdil(pole, a, b))
    return vysledek


def zaznamy(
    s: Session,
    *,
    druh: str | None = None,
    klic: str | None = None,
    pred_id: int | None = None,
    pocet: int = 50,
) -> list[AuditniZaznam]:
    """Nejnovější záznamy; `pred_id` vrátí starší než daný záznam (stránkování)."""
    q = select(AuditniZaznam).order_by(AuditniZaznam.id.desc()).limit(pocet)
    if druh:
        q = q.where(AuditniZaznam.druh == druh)
    if klic:
        q = q.where(AuditniZaznam.klic == klic)
    if pred_id:
        q = q.where(AuditniZaznam.id < pred_id)
    return list(s.scalars(q))


def posledni_zmena(
    s: Session, druh: str, klic: str, po: datetime | None = None
) -> AuditniZaznam | None:
    """Poslední změna věci, volitelně jen pozdější než `po`."""
    q = (
        select(AuditniZaznam)
        .where(AuditniZaznam.druh == druh, AuditniZaznam.klic == klic)
        .order_by(AuditniZaznam.id.desc())
        .limit(1)
    )
    if po is not None:
        # `now()` v Postgresu je začátek transakce: změna ve stejné transakci se počítá.
        q = q.where(AuditniZaznam.kdy >= po)
    return s.scalar(q)
