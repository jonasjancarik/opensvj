"""Dluhy při převodu jednotky.

Dluhy na příspěvcích a zálohách jdou s jednotkou: na nabyvatele přecházejí, pokud o nich
věděl nebo mohl vědět, a převodce za ně ručí (§ 1186 odst. 2 OZ). Saldo se proto vede na
jednotku. Dluh, který na nabyvatele nepřešel, se samostatným zápisem přesune na dřívějšího
vlastníka (jméno v dimenzi `protistrana`), takže se dál vymáhá po něm a v saldu současného
vlastníka už není.
"""

from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy.orm import Session

from . import denik, dluznici, lide, predpisy
from .db import Vlastnictvi, Zapis
from .domena import katalog
from .domena.katalog import Radek
from .domena.penize import na_text
from .domena.profil import Profil

OPERACE = predpisy.OPERACE_PREVODU


class ChybaPrevodu(ValueError):
    pass


@dataclass
class DluhPriPrevodu:
    klic: str  # stálý identifikátor položky pro výběr v rozhraní
    popis: str
    role: str
    zbyva: int
    splatnost: date | None
    navrh: bool  # podle data převodu a volby v profilu patří převodci


@dataclass
class Prevod:
    vlastnictvi: Vlastnictvi
    predchozi: Vlastnictvi
    prevodce: str  # jména dřívějších vlastníků
    rok: int
    dluhy: list[DluhPriPrevodu]
    zapis: Zapis | None  # už zaúčtované ponechání dluhů převodci


def _klic(vlastnictvi_id: int) -> str:
    return f"prevod-dluhu:{vlastnictvi_id}"


def _patri_prevodci(p: dluznici.Polozka, od: date, volba: str, rok: int) -> bool:
    if p.splatnost is None:  # z minulých let
        return od >= date(rok, 1, 1)
    if p.mesic is not None:
        mesic_prevodu = od.replace(day=1)
        return p.mesic < mesic_prevodu or (p.mesic == mesic_prevodu and volba == "dosavadni")
    return p.vznik is not None and p.vznik < od


def _s_predchozim(s: Session, vlastnictvi_id: int) -> tuple[Vlastnictvi, Vlastnictvi]:
    v = s.get(Vlastnictvi, vlastnictvi_id)
    if v is None:
        raise ChybaPrevodu("Takové vlastnictví v evidenci není.")
    historie = lide.vlastnictvi(s, v.jednotka)
    i = next(k for k, x in enumerate(historie) if x.id == v.id)
    if i == 0:
        raise ChybaPrevodu("Tohle je první zapsané vlastnictví jednotky, žádný převodce není.")
    return v, historie[i - 1]


@dataclass
class PotvrzeniPrevodce:
    vlastnictvi: Vlastnictvi
    predchozi: Vlastnictvi
    k_datu: date  # poslední den, kdy jednotku vlastnil převodce (nejpozději dnes)
    dluhy: dluznici.DluhJednotky


def potvrzeni_k_prevodu(
    s: Session,
    profil: Profil,
    nastaveni: predpisy.Nastaveni,
    vlastnictvi_id: int,
    dnes: date | None = None,
) -> PotvrzeniPrevodce:
    """Dluhy převodce k poslednímu dni jeho vlastnictví, pro potvrzení o dluzích vydané
    i po převodu. Bere jen zápisy do toho dne a z měsíčních záloh jen ty, které podle
    volby `predpis_mesice_prevodu` platil převodce."""
    dnes = dnes or date.today()
    v, predchozi = _s_predchozim(s, vlastnictvi_id)
    k = min(v.plati_od - timedelta(days=1), dnes)
    d = next(
        x
        for x in dluznici.prehled(s, profil, nastaveni, k.year, k, do=k)
        if x.jednotka == v.jednotka
    )
    d.polozky = [
        p
        for p in d.polozky
        if _patri_prevodci(p, v.plati_od, profil.predpis_mesice_prevodu, k.year)
    ]
    return PotvrzeniPrevodce(v, predchozi, k, d)


def prevod(
    s: Session,
    profil: Profil,
    nastaveni: predpisy.Nastaveni,
    vlastnictvi_id: int,
    dnes: date | None = None,
) -> Prevod:
    """Nezaplacené dluhy jednotky a návrh, které z nich zůstávají převodci."""
    dnes = dnes or date.today()
    v, predchozi = _s_predchozim(s, vlastnictvi_id)
    prevodce = ", ".join(c.osoba.jmeno for c in predchozi.vlastnici)
    rok = dnes.year  # dluhy, jak je jednotka má teď, v otevřeném roce
    zapis = denik.aktivni(s, _klic(v.id))
    dluhy: list[DluhPriPrevodu] = []
    if zapis is None:
        jednotka = next(
            (
                d
                for d in dluznici.prehled(s, profil, nastaveni, rok, dnes)
                if d.jednotka == v.jednotka
            ),
            None,
        )
        for n, p in enumerate(jednotka.polozky if jednotka else []):
            dluhy.append(
                DluhPriPrevodu(
                    klic=f"{n}:{p.role}:{p.zbyva}",
                    popis=p.popis,
                    role=p.role,
                    zbyva=p.zbyva,
                    splatnost=p.splatnost,
                    navrh=_patri_prevodci(p, v.plati_od, profil.predpis_mesice_prevodu, rok),
                )
            )
    return Prevod(v, predchozi, prevodce, rok, dluhy, zapis)


def ponech_prevodci(
    s: Session,
    profil: Profil,
    nastaveni: predpisy.Nastaveni,
    vlastnictvi_id: int,
    klice: list[str],
    kdo: str,
    dnes: date | None = None,
) -> Zapis:
    """Zaúčtuje vybrané dluhy jako dluhy převodce (operace `dluh-zustava-prevodci`)."""
    dnes = dnes or date.today()
    p = prevod(s, profil, nastaveni, vlastnictvi_id, dnes)
    if p.zapis is not None:
        raise ChybaPrevodu(
            "Dluhy při tomto převodu už jsou zapsané. "
            "Opravit je jde stornem zápisu na stránce Deník."
        )
    vybrane = [d for d in p.dluhy if d.klic in set(klice)]
    if not vybrane:
        raise ChybaPrevodu("Vyberte aspoň jeden dluh, který zůstává prodávajícímu.")
    if len(vybrane) != len(set(klice)):
        raise ChybaPrevodu("Dluhy se mezitím změnily. Načtěte stránku znovu.")
    jednotka = p.vlastnictvi.jednotka
    radky: list[Radek] = []
    for d in vybrane:
        popis = d.popis[:200]
        radky.append(
            Radek(
                "md",
                d.role,
                d.zbyva,
                {"jednotka": jednotka, "protistrana": p.prevodce[:128], "popis": popis},
            )
        )
        radky.append(Radek("d", d.role, d.zbyva, {"jednotka": jednotka, "popis": popis}))
    datum = dnes
    celkem = sum(d.zbyva for d in vybrane)
    try:
        return denik.zauctuj(
            s,
            profil,
            katalog.nacti()[OPERACE],
            {},
            datum=datum,
            popis=(
                f"Dluh jednotky {jednotka} {na_text(celkem)} Kč zůstává převodci "
                f"({p.prevodce}), převod k {lide._d(p.vlastnictvi.plati_od)}"
            ),
            doklad=f"ID prevod {jednotka}",
            zauctoval=kdo,
            idempotencni_klic=_klic(p.vlastnictvi.id),
            radky=radky,
        )
    except denik.ChybaUctovani as e:
        raise ChybaPrevodu(str(e)) from e
