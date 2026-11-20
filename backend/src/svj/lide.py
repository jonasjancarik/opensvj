"""Osoby a vlastnictví jednotek.

Vlastnictví jednotky jsou období, která na sebe navazují bez mezery a nepřekrývají se;
poslední období je otevřené (bez data konce). Nové vlastnictví proto vždy uzavře
předchozí den před svým začátkem. Rozhoduje den zápisu do katastru.

Předpis a saldo zatím zůstávají na jednotku; vlastníci slouží pro dopisy, upomínky,
potvrzení o dluzích a párování plateb podle účtu vlastníka.
"""

import re
from dataclasses import dataclass
from datetime import date, timedelta
from fractions import Fraction

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .db import Osoba, Vlastnictvi, VlastnikJednotky
from .domena import gpc
from .domena.profil import Profil


class ChybaLidi(ValueError):
    pass


@dataclass
class UdajeOsoby:
    jmeno: str
    adresa: str = ""
    ico: str | None = None
    email: str | None = None
    telefon: str | None = None
    ucet: str | None = None
    souhlas_email: date | None = None
    poznamka: str = ""


@dataclass
class ClenVlastnictvi:
    osoba_id: int
    podil: str | None = None  # "1/2"; u společného jmění manželů prázdné


_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_UCET = re.compile(r"^(\d{1,6}-)?\d{1,10}/\d{4}$")


def _text(hodnota: str | None, nazev: str, delka: int) -> str | None:
    t = (hodnota or "").strip()
    if len(t) > delka:
        raise ChybaLidi(f"Údaj „{nazev}“ je příliš dlouhý (nejvýš {delka} znaků).")
    return t or None


def _over_osobu(u: UdajeOsoby) -> UdajeOsoby:
    jmeno = _text(u.jmeno, "jméno", 200)
    if not jmeno:
        raise ChybaLidi("Chybí jméno.")
    email = _text(u.email, "e-mail", 254)
    if email and not _EMAIL.match(email):
        raise ChybaLidi(f"E-mail {email} nevypadá platně.")
    ucet = _text(u.ucet, "účet", 40)
    if ucet:
        ucet = ucet.replace(" ", "")
        if not _UCET.match(ucet):
            raise ChybaLidi(
                f"Číslo účtu {ucet} nemá správný tvar. Napište ho jako 123456789/0800 "
                "nebo 19-123456789/0800."
            )
    ico = _text(u.ico, "IČO", 10)
    if ico and not ico.isdigit():
        raise ChybaLidi("IČO má obsahovat jen číslice.")
    if u.souhlas_email and not email:
        raise ChybaLidi("Souhlas s doručováním e-mailem jde zapsat jen s e-mailovou adresou.")
    return UdajeOsoby(
        jmeno=jmeno,
        adresa=(u.adresa or "").strip()[:500],
        ico=ico,
        email=email.lower() if email else None,
        telefon=_text(u.telefon, "telefon", 40),
        ucet=ucet,
        souhlas_email=u.souhlas_email,
        poznamka=(u.poznamka or "").strip()[:2000],
    )


def osoby(s: Session) -> list[Osoba]:
    return list(s.scalars(select(Osoba).order_by(Osoba.jmeno, Osoba.id)))


def pridej_osobu(s: Session, udaje: UdajeOsoby, kdo: str) -> Osoba:
    u = _over_osobu(udaje)
    o = Osoba(**u.__dict__, upravil=kdo)
    s.add(o)
    s.flush()
    return o


def uprav_osobu(s: Session, osoba_id: int, udaje: UdajeOsoby, kdo: str) -> Osoba:
    o = s.get(Osoba, osoba_id)
    if o is None:
        raise ChybaLidi("Taková osoba v evidenci není.")
    for k, v in _over_osobu(udaje).__dict__.items():
        setattr(o, k, v)
    o.upravil = kdo
    s.flush()
    return o


def smaz_osobu(s: Session, osoba_id: int) -> None:
    o = s.get(Osoba, osoba_id)
    if o is None:
        raise ChybaLidi("Taková osoba v evidenci není.")
    if s.scalar(select(VlastnikJednotky.osoba_id).where(VlastnikJednotky.osoba_id == osoba_id)):
        raise ChybaLidi(
            f"{o.jmeno} je zapsaný jako vlastník jednotky. Nejdřív ho odeberte z vlastnictví."
        )
    s.delete(o)
    s.flush()


def vlastnictvi(s: Session, jednotka: str | None = None) -> list[Vlastnictvi]:
    """Vlastnictví podle jednotky a data, od nejstaršího."""
    dotaz = (
        select(Vlastnictvi)
        .options(selectinload(Vlastnictvi.vlastnici).selectinload(VlastnikJednotky.osoba))
        .order_by(Vlastnictvi.jednotka, Vlastnictvi.plati_od)
    )
    if jednotka is not None:
        dotaz = dotaz.where(Vlastnictvi.jednotka == jednotka)
    return list(s.scalars(dotaz))


def _over_cleny(s: Session, clenove: list[ClenVlastnictvi]) -> list[VlastnikJednotky]:
    if not clenove:
        raise ChybaLidi("Vyberte aspoň jednoho vlastníka.")
    ids = [c.osoba_id for c in clenove]
    if len(set(ids)) != len(ids):
        raise ChybaLidi("Stejná osoba je u vlastnictví zapsaná dvakrát.")
    zname = set(s.scalars(select(Osoba.id).where(Osoba.id.in_(ids))))
    if len(zname) != len(ids):
        raise ChybaLidi("Některá z vybraných osob v evidenci není.")
    podily = [c.podil.strip() if c.podil and c.podil.strip() else None for c in clenove]
    if any(podily):
        if not all(podily):
            raise ChybaLidi("Když zapisujete spoluvlastnické podíly, vyplňte je u všech.")
        try:
            zlomky = [Fraction(p.replace(" ", "")) for p in podily]  # type: ignore[union-attr]
        except (ValueError, ZeroDivisionError) as e:
            raise ChybaLidi("Podíl napište jako zlomek, třeba 1/2.") from e
        if any(z <= 0 for z in zlomky) or sum(zlomky) != 1:
            raise ChybaLidi(
                "Spoluvlastnické podíly musí dát dohromady celek (například 1/2 a 1/2)."
            )
    return [
        VlastnikJednotky(osoba_id=c.osoba_id, poradi=i, podil=p)
        for i, (c, p) in enumerate(zip(clenove, podily, strict=True))
    ]


def _d(d: date) -> str:
    return f"{d.day}. {d.month}. {d.year}"


def _den_pred(d: date) -> date:
    return d - timedelta(days=1)


def zapis_vlastnictvi(
    s: Session,
    profil: Profil,
    jednotka: str,
    plati_od: date,
    clenove: list[ClenVlastnictvi],
    zdroj: str,
    kdo: str,
) -> Vlastnictvi:
    """Zapíše nové vlastnictví jednotky.

    Nové vlastnictví po posledním zapsaném ho uzavře den před svým začátkem (převod
    jednotky). Starší vlastnictví před prvním zapsaným (doplnění historie) skončí den před
    začátkem prvního. Doprostřed historie zapisovat nejde, tam je potřeba upravit datum.
    """
    if jednotka not in profil.jednotky:
        raise ChybaLidi(f"Jednotku {jednotka} SVJ nemá.")
    radky = _over_cleny(s, clenove)
    dosavadni = vlastnictvi(s, jednotka)
    plati_do = None
    if dosavadni:
        prvni, posledni = dosavadni[0], dosavadni[-1]
        if plati_od > posledni.plati_od:
            posledni.plati_do = _den_pred(plati_od)
            posledni.upravil = kdo
            s.flush()
        elif plati_od < prvni.plati_od:
            plati_do = _den_pred(prvni.plati_od)
        else:
            raise ChybaLidi(
                f"Jednotka {jednotka} má od {_d(prvni.plati_od)} zapsané vlastníky. "
                "Nové vlastnictví musí začít po začátku posledního zapsaného, nebo před "
                "prvním. Když jde o opravu, upravte datum u stávajícího záznamu."
            )
    v = Vlastnictvi(
        jednotka=jednotka,
        plati_od=plati_od,
        plati_do=plati_do,
        zdroj=(zdroj or "").strip()[:500],
        upravil=kdo,
        vlastnici=radky,
    )
    s.add(v)
    s.flush()
    return v


def uprav_vlastnictvi(
    s: Session,
    vlastnictvi_id: int,
    plati_od: date,
    clenove: list[ClenVlastnictvi],
    zdroj: str,
    kdo: str,
) -> Vlastnictvi:
    """Opraví osoby, zdroj nebo začátek vlastnictví; předchozí se posune s ním."""
    v = s.get(Vlastnictvi, vlastnictvi_id)
    if v is None:
        raise ChybaLidi("Takové vlastnictví v evidenci není.")
    vse = vlastnictvi(s, v.jednotka)
    i = next(k for k, x in enumerate(vse) if x.id == v.id)
    predchozi = vse[i - 1] if i > 0 else None
    dalsi = vse[i + 1] if i + 1 < len(vse) else None
    if predchozi and plati_od <= predchozi.plati_od:
        raise ChybaLidi(
            f"Začátek musí být po začátku předchozího vlastnictví ({_d(predchozi.plati_od)})."
        )
    if dalsi and plati_od >= dalsi.plati_od:
        raise ChybaLidi(
            f"Začátek musí být před začátkem dalšího vlastnictví ({_d(dalsi.plati_od)})."
        )
    radky = _over_cleny(s, clenove)
    # Omezení proti překryvu kontroluje databáze u každého řádku hned, takže pořadí změn
    # musí zajistit, že se období nepřekrývají ani mezi nimi: při posunu začátku na pozdější
    # datum se nejdřív posune toto a pak prodlouží předchozí, při posunu na dřívější naopak.
    if plati_od > v.plati_od:
        v.plati_od = plati_od
        s.flush()
    if predchozi and predchozi.plati_do != _den_pred(plati_od):
        predchozi.plati_do = _den_pred(plati_od)
        predchozi.upravil = kdo
        s.flush()
    v.plati_od = plati_od
    v.zdroj = (zdroj or "").strip()[:500]
    v.upravil = kdo
    v.vlastnici.clear()
    s.flush()
    v.vlastnici.extend(radky)
    s.flush()
    return v


def smaz_vlastnictvi(s: Session, vlastnictvi_id: int) -> None:
    """Smaže omylem zapsané vlastnictví. Jde jen první nebo poslední, ať nevznikne mezera."""
    v = s.get(Vlastnictvi, vlastnictvi_id)
    if v is None:
        raise ChybaLidi("Takové vlastnictví v evidenci není.")
    vse = vlastnictvi(s, v.jednotka)
    i = next(k for k, x in enumerate(vse) if x.id == v.id)
    if 0 < i < len(vse) - 1:
        raise ChybaLidi(
            "Vlastnictví uprostřed historie jednotky smazat nejde, vznikla by mezera. "
            "Opravte místo toho osoby nebo datum."
        )
    s.delete(v)
    s.flush()
    if i == len(vse) - 1 and i > 0:
        vse[i - 1].plati_do = None
        s.flush()


def vlastnici_k(s: Session, datum: date) -> dict[str, list[Osoba]]:
    """Jednotka → osoby, které ji k datu vlastní (v pořadí zápisu)."""
    vysledek: dict[str, list[Osoba]] = {}
    for v in vlastnictvi(s):
        if v.plati_od <= datum and (v.plati_do is None or datum <= v.plati_do):
            vysledek[v.jednotka] = [c.osoba for c in v.vlastnici]
    return vysledek


def jednotky_podle_uctu(s: Session, datum: date) -> dict[str, list[str]]:
    """Normalizované číslo účtu se směrovým kódem → jednotky, jejichž vlastník ho má."""
    vysledek: dict[str, list[str]] = {}
    for jednotka, lide in vlastnici_k(s, datum).items():
        for o in lide:
            if not o.ucet:
                continue
            cislo, _, banka = o.ucet.partition("/")
            try:
                klic = f"{gpc.normalizuj_cislo(cislo)}/{banka}"
            except gpc.ChybaVypisu:
                continue
            if jednotka not in vysledek.setdefault(klic, []):
                vysledek[klic].append(jednotka)
    return vysledek
