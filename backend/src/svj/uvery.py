"""Úvěr SVJ splácený vlastníky mimořádnými zálohami podle podílů (příručka, kapitola 5).

Shromáždění schválí úvěr (§ 1208 písm. f) bod 3 OZ) a to, že jistinu splatí vlastníci podle
podílů na společných částech. Podíl každé jednotky na jistině se předepíše najednou jako
pohledávka (378) proti záloze na úvěr (955) a do měsíčních předpisů se pak přidává splátka
(311/378), dokud jednotka svůj podíl nesplatí. V rozvaze tak proti sobě stojí úvěr (951)
a dosud nesplacené podíly vlastníků (378).

Všechny řádky úvěru v deníku nesou kód úvěru (`UVER-<id>`) v dimenzi služby: podle něj se
počítá, kolik zbývá splatit bance a kolik dluží jednotky, i když je úvěrů víc, a kód se
přenáší s rozpisem zůstatků do dalšího roku. Oprava placená z úvěru snižuje přímo zálohu
na úvěr (`cerpani-zalohy-na-uver`), stejně jako oprava z fondu oprav. Úroky jsou náklad;
když je podle rozhodnutí neplatí provozní zálohy, pokryje je k 31. 12. fond oprav nebo
záloha na úvěr (`uver-kryti-uroku`).
"""

from dataclasses import dataclass, replace
from datetime import date

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from . import denik, faktury, podily, predpisy, rozhodnuti
from .db import RadekZapisu, Rozhodnuti, Uver, Zapis
from .domena import katalog
from .domena.penize import kc, na_text
from .domena.profil import NeznamaRole, Profil
from .domena.rozdeleni import rozdel

OPERACE_PODILU = denik.OPERACE_PODILU_UVERU
OPERACE_KRYTI = "uver-kryti-uroku"
# Kdo platí úroky (mimo položky správy, které jdou do vyúčtování záloh na správu).
UROKY_HRADI = {
    "fond_oprav": ("zalohy_dlouhodobe", "fond oprav"),
    "zaloha_na_uver": ("zalohy_dlouhodobe_uver", "záloha na úvěr"),
}
ROLE = ("uvery", "pohledavky_uver", "zalohy_dlouhodobe_uver", "naklady.uroky_uver")
NEJVIC_SPLATEK = 600


class ChybaUveru(ValueError):
    pass


def nastaveno(profil: Profil) -> bool:
    return all(r in profil.role for r in ROLE)


def _d(d: date) -> str:
    return f"{d.day}. {d.month}. {d.year}"


def rozdel_jistinu(s: Session, profil: Profil, jistina: int, datum: date) -> dict[str, int]:
    """Jednotka → podíl na jistině podle podílů na společných částech platných v den `datum`.

    Na celé koruny, když je jistina v celých korunách; součet je vždy přesně jistina."""
    if jistina <= 0:
        raise ChybaUveru("Jistina musí být kladná.")
    sada = podily.nacti(s, profil).k_datu(datum)
    krok = 100 if jistina % 100 == 0 else 1
    return rozdel(jistina, {j: sada.podily[j] for j in profil.jednotky}, krok=krok)


def _s_kodem(radky: list[katalog.Radek], kod: str, role: str | None = None) -> list[katalog.Radek]:
    """Doplní kód úvěru do dimenze služby (jen řádkům dané role, když je zadaná)."""
    return [
        replace(r, dimenze={**r.dimenze, "sluzba": kod}) if role in (None, r.role) else r
        for r in radky
    ]


def _zauctuj(s: Session, profil: Profil, operace: str, vstupy, radky=None, **kw) -> Zapis:
    try:
        return denik.zauctuj(s, profil, katalog.nacti()[operace], vstupy, radky=radky, **kw)
    except (denik.ChybaUctovani, NeznamaRole) as e:
        raise ChybaUveru(str(e)) from e


def _uver(s: Session, uver_id: int) -> Uver:
    u = s.get(Uver, uver_id)
    if u is None or not u.platny:
        raise ChybaUveru("Tento úvěr v aplikaci není, nebo byl zrušený stornem předpisu podílů.")
    return u


def zaloz(
    s: Session,
    profil: Profil,
    *,
    nazev: str,
    cislo_uctu: str = "",
    jistina: int,
    rozhodnuti_id: int,
    predepsano_dne: date,
    prvni_splatka: date,
    pocet_splatek: int,
    uroky_hradi: str,
    zauctoval: str,
) -> Uver:
    """Založí úvěr a zaúčtuje předpis podílů jednotek na jistině."""
    if not nastaveno(profil):
        raise ChybaUveru("Společenství nemá v nastavení účty pro úvěr.")
    nazev = " ".join(nazev.split())
    if not nazev:
        raise ChybaUveru("Napište, na co si SVJ úvěr vzalo (třeba „zateplení fasády“).")
    if not 1 <= pocet_splatek <= NEJVIC_SPLATEK:
        raise ChybaUveru(f"Počet měsíčních splátek musí být od 1 do {NEJVIC_SPLATEK}.")
    if prvni_splatka.day != 1:
        raise ChybaUveru("Splácet se začíná od prvního dne měsíce.")
    if prvni_splatka < predepsano_dne.replace(day=1):
        raise ChybaUveru("První splátka nemůže být dřív než předpis podílů na jistině.")
    od = predpisy.prvni_mesic_ke_zmene(s)
    if prvni_splatka < od:
        raise ChybaUveru(
            f"Předpis za {predpisy.MESICE[prvni_splatka.month - 1]} {prvni_splatka.year} "
            f"už je zaúčtovaný. Splátky mohou začít nejdřív od {_d(od)}."
        )
    if uroky_hradi not in UROKY_HRADI and uroky_hradi not in profil.sprava:
        raise ChybaUveru("Vyberte, z čeho se platí úroky z úvěru.")
    r = s.get(Rozhodnuti, rozhodnuti_id)
    if r is None or r.organ != "shromazdeni":
        raise ChybaUveru(
            "Vyberte rozhodnutí shromáždění, které úvěr schválilo (§ 1208 písm. f) OZ). "
            "Když v seznamu není, zapište ho na stránce Rozhodnutí."
        )
    if r.datum > predepsano_dne:
        raise ChybaUveru("Předepsat podíly jde až po dni, kdy o úvěru rozhodlo shromáždění.")
    casti = rozdel_jistinu(s, profil, jistina, predepsano_dne)
    u = Uver(
        nazev=nazev[:150],
        cislo_uctu=cislo_uctu.strip()[:64],
        jistina=jistina,
        rozhodnuti_id=r.id,
        predepsano_dne=predepsano_dne,
        prvni_splatka=prvni_splatka,
        pocet_splatek=pocet_splatek,
        uroky_hradi=uroky_hradi,
        podily={j: c for j, c in casti.items() if c},
        upravil=zauctoval,
    )
    s.add(u)
    s.flush()  # kvůli kódu úvěru
    op = katalog.nacti()[OPERACE_PODILU]
    vstupy = {"podily": [{"jednotka": j, "castka": na_text(c)} for j, c in u.podily.items()]}
    zapis = _zauctuj(
        s,
        profil,
        OPERACE_PODILU,
        vstupy,
        _s_kodem(katalog.sestav(op, vstupy), u.kod),
        datum=predepsano_dne,
        popis=f"Podíly jednotek na jistině úvěru: {nazev} ({rozhodnuti.popis(r)})",
        doklad="ID",
        zauctoval=zauctoval,
    )
    u.zapis_id = zapis.id
    s.flush()
    s.refresh(u)
    return u


# ---------- zůstatky ----------


def _zustatky(s: Session, kod: str, role: str, do: date | None = None) -> dict[str | None, int]:
    """Zůstatky řádků s kódem úvěru po jednotkách (MD kladně), přes všechny roky.

    Uzavření roku a počáteční stav dalšího se navzájem vyruší, takže součet přes roky je
    zůstatek ke dni `do`."""
    znamenko = func.sum(
        case((RadekZapisu.strana == "md", RadekZapisu.castka), else_=-RadekZapisu.castka)
    )
    dotaz = (
        select(RadekZapisu.jednotka, znamenko)
        .join(Zapis)
        .where(RadekZapisu.sluzba == kod, RadekZapisu.role == role, denik.nestornovany())
        .group_by(RadekZapisu.jednotka)
    )
    if do is not None:
        dotaz = dotaz.where(Zapis.datum <= do)
    return {j: int(z) for j, z in s.execute(dotaz)}


def _uroky_roku(s: Session, kod: str, rok: int) -> int:
    return sum(_zustatky_roku(s, kod, "naklady.uroky_uver", rok).values())


def _zustatky_roku(s: Session, kod: str, role: str, rok: int) -> dict[str | None, int]:
    znamenko = func.sum(
        case((RadekZapisu.strana == "md", RadekZapisu.castka), else_=-RadekZapisu.castka)
    )
    return {
        j: int(z)
        for j, z in s.execute(
            select(RadekZapisu.jednotka, znamenko)
            .join(Zapis)
            .where(
                RadekZapisu.sluzba == kod,
                RadekZapisu.role == role,
                Zapis.rok == rok,
                denik.platny(),
            )
            .group_by(RadekZapisu.jednotka)
        )
    }


def _kryto_roku(s: Session, kod: str, rok: int) -> int:
    return -sum(_zustatky_roku(s, kod, "vynosy.zuctovani_dlouhodobych_zaloh", rok).values())


@dataclass
class Jednotka:
    jednotka: str
    podil: int  # předepsaný podíl na jistině
    mesicne: int  # běžná měsíční splátka
    zbyva: int  # nesplaceno (zůstatek 378)


@dataclass
class StavUveru:
    uver: Uver
    rozhodnuti: str
    zbyva_bance: int  # nesplacený úvěr (zůstatek 951, kladně)
    nesplaceno: int  # nesplacené podíly vlastníků (zůstatek 378)
    jednotky: list[Jednotka]
    uroky: int  # úroky roku
    kryto: int  # z nich už pokryto z dlouhodobých záloh
    posledni_splatka: date


def stav(s: Session, profil: Profil, u: Uver, rok: int) -> StavUveru:
    plan = predpisy.plan_uveru(u)
    dluzi = _zustatky(s, u.kod, "pohledavky_uver")
    r = s.get(Rozhodnuti, u.rozhodnuti_id)
    return StavUveru(
        uver=u,
        rozhodnuti=rozhodnuti.popis(r) if r else "",
        zbyva_bance=-sum(_zustatky(s, u.kod, "uvery").values()),
        nesplaceno=sum(dluzi.values()),
        jednotky=[
            Jednotka(j, int(u.podily.get(j, 0)), plan.mesicne(j), dluzi.get(j, 0))
            for j in profil.jednotky
            if u.podily.get(j)
        ],
        uroky=_uroky_roku(s, u.kod, rok),
        kryto=_kryto_roku(s, u.kod, rok),
        posledni_splatka=predpisy.plus_mesicu(max(plan.zmeny()), -1),
    )


def nevycerpana_zaloha(s: Session, profil: Profil, do: date | None = None) -> int:
    """Zálohy na úvěry, které ještě nepokryly opravy (zůstatek 955 úvěrů, kladně).

    Faktura placená z úvěru se k úvěru neváže, proto jde o součet za všechny úvěry."""
    znamenko = func.sum(
        case((RadekZapisu.strana == "d", RadekZapisu.castka), else_=-RadekZapisu.castka)
    )
    dotaz = (
        select(znamenko)
        .join(Zapis)
        .where(RadekZapisu.ucet == profil.ucet("zalohy_dlouhodobe_uver"), denik.nestornovany())
    )
    if do is not None:
        dotaz = dotaz.where(Zapis.datum <= do)
    return int(s.scalar(dotaz) or 0)


def uvery(s: Session) -> list[Uver]:
    return list(s.scalars(select(Uver).order_by(Uver.id)))


@dataclass
class ZbytekJednotky:
    nazev: str
    zbyva: int
    mesicne: int


def zbytky_jednotky(s: Session, jednotka: str, do: date | None = None) -> list[ZbytekJednotky]:
    """Nesplacené podíly jednotky na úvěrech ke dni `do`, pro potvrzení o dluzích.

    Nejsou to dluhy vlastníka (nejsou splatné); s jednotkou přecházejí na kupujícího, který
    je dál splácí v měsíčních předpisech."""
    vysledek = []
    for u in uvery(s):
        if not u.platny or not u.podily.get(jednotka):
            continue
        zbyva = _zustatky(s, u.kod, "pohledavky_uver", do).get(jednotka, 0)
        if zbyva > 0:
            mesicne = predpisy.plan_uveru(u).mesicne(jednotka)
            vysledek.append(ZbytekJednotky(u.nazev, zbyva, mesicne))
    return vysledek


# ---------- operace úvěru ----------


def uhrada_faktury(
    s: Session,
    profil: Profil,
    uver_id: int,
    *,
    faktura: str,
    castka: int,
    datum: date,
    zauctoval: str,
) -> Zapis:
    """Banka zaplatila fakturu dodavatele přímo z úvěrového účtu."""
    u = _uver(s, uver_id)
    if castka <= 0:
        raise ChybaUveru("Částka musí být kladná.")
    try:
        st = faktury.otevrena(s, faktura)
        faktury.zkontroluj_uhradu(st, castka)
    except faktury.ChybaFaktury as e:
        raise ChybaUveru(str(e)) from e
    op = katalog.nacti()["uver-uhrada-faktury"]
    vstupy = {"protistrana": st.faktura.dodavatel, "castka": na_text(castka)}
    radky = _s_kodem(
        faktury.s_parovacim_symbolem(katalog.sestav(op, vstupy), st.faktura.cislo),
        u.kod,
        "uvery",
    )
    return _zauctuj(
        s,
        profil,
        op.id,
        vstupy,
        radky,
        datum=datum,
        popis=f"Úhrada faktury {st.faktura.cislo} ({st.faktura.dodavatel}) z úvěru: {u.nazev}",
        doklad="výpis z úvěrového účtu",
        zauctoval=zauctoval,
    )


def uroky(
    s: Session,
    profil: Profil,
    uver_id: int,
    *,
    uroky: int,
    poplatky: int,
    datum: date,
    sluzba_poplatku: str,
    zauctoval: str,
) -> Zapis:
    """Úroky a poplatky, které banka připsala na úvěrový účet."""
    u = _uver(s, uver_id)
    if uroky < 0 or poplatky < 0 or uroky + poplatky == 0:
        raise ChybaUveru("Zadejte úroky nebo poplatky z výpisu úvěrového účtu.")
    if sluzba_poplatku and sluzba_poplatku not in profil.sprava:
        raise ChybaUveru("Vyberte položku správy z nabídky.")
    op = katalog.nacti()["uver-urok"]
    vstupy = {
        "uroky": na_text(uroky),
        "poplatky": na_text(poplatky),
        "sluzba_uroku": u.kod if u.uroky_hradi in UROKY_HRADI else u.uroky_hradi,
        "sluzba_poplatku": sluzba_poplatku,
    }
    return _zauctuj(
        s,
        profil,
        op.id,
        vstupy,
        _s_kodem(katalog.sestav(op, vstupy), u.kod, "uvery"),
        datum=datum,
        popis=f"Úroky a poplatky z úvěru: {u.nazev}",
        doklad="výpis z úvěrového účtu",
        zauctoval=zauctoval,
    )


def prichod_splatky(
    s: Session, profil: Profil, uver_id: int, *, castka: int, datum: date, zauctoval: str
) -> Zapis:
    """Splátka odešlá z běžného účtu (v Bance na peníze na cestě) dorazila na úvěrový účet."""
    u = _uver(s, uver_id)
    if castka <= 0:
        raise ChybaUveru("Částka musí být kladná.")
    na_ceste = denik.zustatky(s, datum.year, datum).get(profil.ucet("penize_na_ceste"), 0)
    if castka > na_ceste:
        raise ChybaUveru(
            f"Na cestě je k tomuto dni jen {kc(max(na_ceste, 0))}. Odchod splátky z běžného "
            "účtu nejdřív zaúčtujte v Bance jako splátku úvěru."
        )
    zbyva = -sum(_zustatky(s, u.kod, "uvery", datum).values())
    if castka > zbyva:
        raise ChybaUveru(f"Z úvěru zbývá k tomuto dni splatit jen {kc(max(zbyva, 0))}.")
    op = katalog.nacti()["uver-splatka"]
    vstupy = {"ucet": "", "castka": na_text(castka)}
    return _zauctuj(
        s,
        profil,
        op.id,
        vstupy,
        _s_kodem(katalog.sestav(op, vstupy, "prichod"), u.kod, "uvery"),
        datum=datum,
        popis=f"Splátka připsaná na úvěrový účet: {u.nazev}",
        doklad="výpis z úvěrového účtu",
        zauctoval=zauctoval,
        krok="prichod",
    )


def kryti_uroku(
    s: Session, profil: Profil, uver_id: int, rok: int, *, zauctoval: str, dnes: date
) -> Zapis:
    """K 31. 12. pokryje úroky roku z fondu oprav nebo ze zálohy na úvěr podle rozhodnutí."""
    u = _uver(s, uver_id)
    if u.uroky_hradi not in UROKY_HRADI:
        raise ChybaUveru(
            "Úroky tohoto úvěru platí provozní zálohy; započtou se ve vyúčtování záloh na správu."
        )
    if dnes < date(rok, 12, 31):
        raise ChybaUveru(f"Úroky za rok {rok} jde pokrýt k 31. 12. {rok}, až budou známé celé.")
    castka = _uroky_roku(s, u.kod, rok) - _kryto_roku(s, u.kod, rok)
    if castka <= 0:
        raise ChybaUveru(f"Za rok {rok} nejsou žádné úroky, které by ještě nebyly pokryté.")
    role, odkud = UROKY_HRADI[u.uroky_hradi]
    return _zauctuj(
        s,
        profil,
        OPERACE_KRYTI,
        {"zdroj": role, "uver": u.kod, "castka": na_text(castka)},
        datum=date(rok, 12, 31),
        popis=f"Úroky z úvěru {u.nazev} za rok {rok} hradí {odkud}",
        doklad="ID",
        zauctoval=zauctoval,
    )
