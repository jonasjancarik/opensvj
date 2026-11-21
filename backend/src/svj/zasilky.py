"""Rozesílání dokumentů vlastníkům a evidence doručení.

Postup: výbor připraví dávku (dokument každé jednotky se uloží jako neměnné HTML s otiskem
SHA-256 a pro každého vlastníka vznikne zásilka), prohlédne si, komu půjde e-mail a komu
dopis, a dávku odešle. E-mail jde jen vlastníkovi, který s doručováním e-mailem souhlasil;
ostatním se dokument vytiskne a datum odeslání a doručení se zapíše ručně.

U e-mailu se ukládají tři události: předání poštovnímu serveru, otevření odkazu a potvrzení
převzetí vlastníkem. Za doručení se bere jen potvrzení vlastníkem nebo ruční zápis výboru
(dodejka, převzetí osobně). Otevření odkazu může způsobit i antivirová kontrola pošty,
proto samo doručení nezakládá; výbor ho podle něj může zapsat ručně.
"""

import hashlib
import secrets
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import lide, posta
from .db import Dokument, Zasilka
from .nastaveni import nastaveni

DRUHY = {
    "oznameni": "Oznámení o výši záloh",
    "vyuctovani_sluzeb": "Vyúčtování služeb",
    "vyuctovani_spravy": "Vyúčtování záloh na správu domu",
    "upominka": "Upomínka",
    "potvrzeni": "Potvrzení o dluzích",
}
MAX_HTML = 2_000_000


class ChybaZasilky(ValueError):
    pass


@dataclass
class NovyDokument:
    jednotka: str
    html: str


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _ted() -> datetime:
    return datetime.now().astimezone()


def priprav(
    s: Session,
    druh: str,
    klic: str,
    nazev: str,
    dokumenty: list[NovyDokument],
    kdo: str,
    dnes: date | None = None,
) -> str:
    """Uloží dokumenty a připraví zásilky všem vlastníkům. Vrátí označení dávky."""
    if druh not in DRUHY:
        raise ChybaZasilky(f"Neznámý druh dokumentu {druh!r}.")
    if not dokumenty:
        raise ChybaZasilky("Není co rozeslat.")
    dnes = dnes or date.today()
    vlastnici = lide.vlastnici_k(s, dnes)
    bez = [d.jednotka for d in dokumenty if not vlastnici.get(d.jednotka)]
    if bez:
        raise ChybaZasilky(
            f"Jednotky {', '.join(bez)} nemají k dnešku zapsaného vlastníka. "
            "Doplňte ho na stránce Vlastníci."
        )
    davka = str(uuid.uuid4())
    for d in dokumenty:
        if len(d.html) > MAX_HTML:
            raise ChybaZasilky(f"Dokument jednotky {d.jednotka} je příliš velký.")
        dok = Dokument(
            druh=druh,
            klic=klic,
            jednotka=d.jednotka,
            nazev=nazev,
            html=d.html,
            sha256=hashlib.sha256(d.html.encode()).hexdigest(),
            vytvoril=kdo,
        )
        s.add(dok)
        s.flush()
        emaily: set[str] = set()
        for o in vlastnici[d.jednotka]:
            email = (o.email or "").strip().lower() or None
            souhlas = o.souhlas_email is not None and o.souhlas_email <= dnes
            kanal = "email" if email and souhlas else "posta"
            if kanal == "email":
                if email in emaily:  # manželé se společnou adresou dostanou jeden e-mail
                    continue
                emaily.add(email)
            s.add(
                Zasilka(
                    dokument_id=dok.id,
                    davka=davka,
                    osoba_id=o.id,
                    jmeno=o.jmeno,
                    email=email if kanal == "email" else None,
                    adresa=o.adresa,
                    kanal=kanal,
                    stav="pripravena",
                    pripravil=kdo,
                )
            )
    s.flush()
    return davka


def v_davce(s: Session, davka: str) -> list[Zasilka]:
    return list(s.scalars(select(Zasilka).where(Zasilka.davka == davka).order_by(Zasilka.id)))


def zrus_davku(s: Session, davka: str) -> None:
    """Zahodí připravenou dávku. Co už odešlo, zůstává."""
    zasilky = v_davce(s, davka)
    if not zasilky:
        raise ChybaZasilky("Dávka neexistuje.")
    dokumenty = {z.dokument_id for z in zasilky}
    for z in zasilky:
        if z.stav == "pripravena":
            s.delete(z)
    s.flush()
    for dok_id in dokumenty:
        if s.scalar(select(Zasilka.id).where(Zasilka.dokument_id == dok_id).limit(1)) is None:
            s.delete(s.get(Dokument, dok_id))
    s.flush()


def _text_emailu(svj: str, dok: Dokument, odkaz: str) -> str:
    return (
        "Dobrý den,\n\n"
        f"posíláme vám dokument „{dok.nazev}“ pro jednotku {dok.jednotka}. "
        "Najdete ho v příloze tohoto e-mailu a také na této adrese:\n\n"
        f"{odkaz}\n\n"
        "Prosíme, otevřete odkaz a potvrďte, že jste dokument dostali. "
        "Od převzetí se počítají lhůty, které dokument uvádí.\n\n"
        "Děkujeme.\n"
        f"{svj}\n"
    )


def odesli_davku(
    s: Session,
    davka: str,
    svj: str,
    kdo: str,
    odeslat: Callable[..., str] = posta.odesli,
) -> list[Zasilka]:
    """Odešle e-maily připravené dávky. Dopisy zůstanou připravené k vytištění.

    Po každém odeslaném e-mailu se zapíše stav (commit), aby se při chybě uprostřed dávky
    nic neposlalo dvakrát.
    """
    zasilky = v_davce(s, davka)
    if not zasilky:
        raise ChybaZasilky("Dávka neexistuje.")
    for z in zasilky:
        if z.kanal != "email" or z.stav != "pripravena":
            continue
        token = secrets.token_urlsafe(32)
        odkaz = f"{nastaveni().app_url.rstrip('/')}/api/verejne/zasilka/{token}"
        dok = z.dokument
        try:
            odeslat(
                z.jmeno,
                z.email,
                f"{dok.nazev}, jednotka {dok.jednotka}",
                _text_emailu(svj, dok, odkaz),
                [
                    posta.Priloha(
                        f"{dok.nazev} {dok.jednotka}.html".replace("/", "-"), dok.html.encode()
                    )
                ],
            )
        except posta.OdmitnutyPrijemce as e:
            z.stav, z.chyba = "nedorucena", str(e)
            z.odeslal, z.odeslano = kdo, _ted()
            s.commit()
            continue
        z.stav = "odeslana"
        z.token_hash = _hash(token)
        z.odeslal, z.odeslano = kdo, _ted()
        z.prijato_serverem = z.odeslano
        z.chyba = ""
        s.commit()
    return v_davce(s, davka)


def _zasilka(s: Session, zasilka_id: int) -> Zasilka:
    z = s.get(Zasilka, zasilka_id)
    if z is None:
        raise ChybaZasilky("Zásilka neexistuje.")
    return z


def oznac_odeslane(s: Session, ids: list[int], datum: date, kdo: str) -> None:
    """Dopisy, které výbor vytiskl a poslal poštou nebo předal."""
    for i in ids:
        z = _zasilka(s, i)
        if z.kanal != "posta":
            raise ChybaZasilky("Ručně jde zapsat odeslání jen u dopisu.")
        if z.stav == "pripravena":
            z.stav = "odeslana"
        z.odeslal = kdo
        z.odeslano = datetime.combine(datum, datetime.min.time()).astimezone()
    s.flush()


def zapis_doruceni(s: Session, zasilka_id: int, datum: date, zdroj: str, kdo: str) -> None:
    z = _zasilka(s, zasilka_id)
    if not zdroj.strip():
        raise ChybaZasilky("Napište, podle čeho víte, že zásilka došla (třeba dodejka).")
    if datum > date.today():
        raise ChybaZasilky("Datum doručení nemůže být v budoucnu.")
    if z.odeslano and datum < z.odeslano.date():
        raise ChybaZasilky("Zásilka nemohla dojít dřív, než odešla.")
    if z.stav == "pripravena" and z.kanal == "posta":
        z.odeslal = kdo
        z.odeslano = datetime.combine(datum, datetime.min.time()).astimezone()
    z.stav = "dorucena"
    z.doruceno = datum
    z.doruceni_zdroj = f"{zdroj.strip()[:150]} (zapsal {kdo})"
    s.flush()


def zapis_nedoruceni(s: Session, zasilka_id: int, duvod: str) -> None:
    z = _zasilka(s, zasilka_id)
    if not duvod.strip():
        raise ChybaZasilky("Napište, proč zásilka nedošla (třeba vrácená obálka).")
    z.stav = "nedorucena"
    z.chyba = duvod.strip()[:500]
    s.flush()


def podle_tokenu(s: Session, token: str) -> Zasilka | None:
    return s.scalar(select(Zasilka).where(Zasilka.token_hash == _hash(token)))


def otevreno(s: Session, z: Zasilka) -> None:
    if z.otevreno is None:
        z.otevreno = _ted()
        s.flush()


def potvrzeno(s: Session, z: Zasilka) -> None:
    if z.potvrzeno is None:
        z.potvrzeno = _ted()
    if z.doruceno is None:
        z.doruceno = z.potvrzeno.date()
        z.doruceni_zdroj = "Vlastník potvrdil převzetí odkazem v e-mailu"
        z.stav = "dorucena"
    s.flush()


def doruceni_jednotek(s: Session, klic: str) -> dict[str, date]:
    """Jednotka → kdy došel poslední rozeslaný dokument s tímto klíčem (nejdřív doručená
    zásilka). Jednotky, kterým zatím nic nedošlo, chybí."""
    posledni: dict[str, int] = {}
    for dok_id, jednotka in s.execute(
        select(Dokument.id, Dokument.jednotka).where(Dokument.klic == klic).order_by(Dokument.id)
    ):
        posledni[jednotka] = dok_id
    vysledek: dict[str, date] = {}
    for jednotka, dok_id in posledni.items():
        data = s.scalars(
            select(Zasilka.doruceno).where(
                Zasilka.dokument_id == dok_id, Zasilka.doruceno.is_not(None)
            )
        ).all()
        if data:
            vysledek[jednotka] = min(data)
    return vysledek


def plus_mesice(d: date, mesicu: int) -> date:
    """Stejný den o `mesicu` měsíců později; když takový den není, poslední den měsíce
    (§ 605 odst. 2 OZ)."""
    m = d.month - 1 + mesicu
    rok, mesic = d.year + m // 12, m % 12 + 1
    dalsi = date(rok + (mesic == 12), mesic % 12 + 1, 1)
    return min(date(rok, mesic, 1) + timedelta(days=d.day - 1), dalsi - timedelta(days=1))
