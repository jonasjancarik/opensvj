"""Čtečka přehledu pohybů z internetového bankovnictví Raiffeisenbank (CSV).

Soubor `Pohyby_<účet>_<datum>.csv` je seznam plateb, ne bankovní výpis: nemá číslo výpisu
ani počáteční a konečný zůstatek. Hodí se pro průběžné párování plateb; navázání
zůstatků ověří až výpis (GPC). Pohyby nese stejné `Id transakce`, takže překrývající
se přehledy nic nezdvojí.

Formát (ověřeno na exportu z listopadu 2026): UTF-8 s BOM, oddělovač středník, hodnoty
v uvozovkách, datum `DD.MM.RRRR`, datum zaúčtování s časem, částka s desetinnou čárkou
a znaménkem (výdaj záporně).
"""

import csv
import io
import re
from dataclasses import dataclass
from datetime import date

from .gpc import ChybaVypisu, Pohyb, normalizuj_cislo

SLOUPCE = (
    "Datum provedení",
    "Datum zaúčtování",
    "Číslo účtu",
    "Číslo protiúčtu",
    "Název protiúčtu",
    "Zpráva",
    "VS",
    "KS",
    "SS",
    "Zaúčtovaná částka",
    "Měna účtu",
    "Id transakce",
)


@dataclass
class PrehledPohybu:
    ucet: str
    nazev_uctu: str
    od: date
    do: date
    pohyby: list[Pohyb]


def je_rb_csv(data: bytes) -> bool:
    zacatek = data[:200].decode("utf-8-sig", errors="ignore")
    return zacatek.startswith("Datum provedení;") or zacatek.startswith('"Datum provedení"')


def _datum(text: str) -> date:
    m = re.fullmatch(r"(\d{1,2})\.(\d{1,2})\.(\d{4})(?: \d{1,2}:\d{2}(?::\d{2})?)?", text.strip())
    if not m:
        raise ChybaVypisu(f"neplatné datum {text!r}")
    return date(int(m[3]), int(m[2]), int(m[1]))


def _castka(text: str) -> int:
    t = text.replace(" ", "").replace(" ", "").replace(",", ".")
    m = re.fullmatch(r"(-?)(\d+)(?:\.(\d{1,2}))?", t)
    if not m:
        raise ChybaVypisu(f"neplatná částka {text!r}")
    halire = int(m[2]) * 100 + int((m[3] or "0").ljust(2, "0"))
    return -halire if m[1] else halire


def _symbol(text: str) -> str | None:
    return text.strip().lstrip("0") or None


def _ucet(text: str) -> tuple[str | None, str | None]:
    text = text.strip()
    if not text:
        return None, None
    cislo, _, banka = text.partition("/")
    return normalizuj_cislo(cislo), banka or None


def cti(data: bytes) -> PrehledPohybu:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("cp1250")
    radky = list(csv.reader(io.StringIO(text, newline=""), delimiter=";"))
    if not radky:
        raise ChybaVypisu("soubor je prázdný")
    hlavicka = [h.strip() for h in radky[0]]
    chybi = [s for s in SLOUPCE if s not in hlavicka]
    if chybi:
        raise ChybaVypisu(f"chybí sloupce {', '.join(chybi)}")
    i = {nazev: hlavicka.index(nazev) for nazev in hlavicka}

    def pole(r: list[str], nazev: str) -> str:
        return r[i[nazev]].strip() if nazev in i and i[nazev] < len(r) else ""

    ucty: set[str] = set()
    nazev_uctu = ""
    pohyby: list[Pohyb] = []
    # Export je od nejnovějších; pořadí v aplikaci bereme od nejstarších.
    for n, r in reversed(list(enumerate(radky[1:], start=2))):
        if not any(x.strip() for x in r):
            continue
        try:
            if pole(r, "Měna účtu") not in ("", "CZK"):
                raise ChybaVypisu("aplikace zatím umí jen účty v korunách")
            ucet, _ = _ucet(pole(r, "Číslo účtu"))
            if ucet is None:
                raise ChybaVypisu("chybí číslo účtu")
            ucty.add(ucet)
            nazev_uctu = pole(r, "Název účtu") or nazev_uctu
            castka = _castka(pole(r, "Zaúčtovaná částka"))
            if castka == 0:
                continue
            protiucet, kod_banky = _ucet(pole(r, "Číslo protiúčtu"))
            zprava = [
                x
                for x in dict.fromkeys(
                    (pole(r, "Zpráva"), pole(r, "Poznámka"), pole(r, "Typ transakce"))
                )
                if x
            ]
            pohyby.append(
                Pohyb(
                    poradi=len(pohyby) + 1,
                    id_banky=pole(r, "Id transakce").lstrip("0") or None,
                    castka=castka,
                    kod_uctovani="2" if castka > 0 else "1",
                    protiucet=protiucet,
                    kod_banky=kod_banky,
                    vs=_symbol(pole(r, "VS")),
                    ks=_symbol(pole(r, "KS")),
                    ss=_symbol(pole(r, "SS")),
                    nazev=pole(r, "Název protiúčtu") or pole(r, "Název obchodníka"),
                    valuta=_datum(pole(r, "Datum provedení")),
                    datum=_datum(pole(r, "Datum zaúčtování")),
                    zprava=zprava,
                )
            )
        except ChybaVypisu as e:
            raise ChybaVypisu(f"řádek {n}: {e}") from e
    if len(ucty) != 1:
        raise ChybaVypisu("soubor musí obsahovat pohyby právě jednoho účtu")
    if not pohyby:
        raise ChybaVypisu("soubor neobsahuje žádné pohyby")
    datumy = [p.datum for p in pohyby if p.datum]
    return PrehledPohybu(
        ucet=ucty.pop(), nazev_uctu=nazev_uctu, od=min(datumy), do=max(datumy), pohyby=pohyby
    )
