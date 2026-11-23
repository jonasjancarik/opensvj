"""Naplní prázdnou databázi rokem 2026 ukázkového SVJ, aby šla aplikace vyzkoušet.

    DATABASE_URL=postgresql+psycopg://svj:svj@localhost:5440/svj_ukazka \
        PROFIL=ukazka PROFILY=profiles uv run python -m tests.naplneni

Vlastníci, platby i faktury jsou vymyšlené. Do databáze, ve které už něco je, nezapíše nic.
"""

import os
import sys
from calendar import monthrange
from datetime import date

from sqlalchemy import func, select

from svj import banka, faktury, lide, pocatecni, predpisy, rozhodnuti
from svj.db import BankovniPohyb, BankovniUcet, Obdobi, PravidloParovani, Zapis, sezeni
from svj.domena import profil as profily
from svj.nastaveni import nastaveni
from tests.gpc_pomoc import pohyb, vypis

PROVOZNI, FOND = "2800000001", "2800000002"
KDO = "vybor@ukazkova12.example"
DNES = date(2026, 11, 23)
PRVNI_PREDPIS = 3  # ukázkový předpis záloh platí od března
POSLEDNI_VYPIS = 11  # poslední výpis je průběžný, do 20. 11.; část plateb čeká na zaúčtování
ZAUCTOVANO_Z_POSLEDNIHO = 7

# Zůstatky k 31. 12. 2025 v haléřích, kladné na straně MD; dohromady dávají nulu.
POCATECNI = pocatecni.PocatecniStav(
    rok=2026,
    zustatky={
        "221100": 42_000_000,  # provozní účet
        "221200": 86_000_000,  # účet fondu oprav
        "311200": 75_000,  # vyúčtování 2025
        "311300": 2_548_000,  # starší pohledávky za vlastníky
        "381100": 1_850_000,  # pojistné zaplacené dopředu
        "321100": -4_500_000,  # nezaplacené faktury dodavatelů
        "955100": -117_973_000,  # fond oprav
        "955200": -10_000_000,  # fond na mimořádné opravy
    },
    polozky=[
        pocatecni.Polozka("311200", 325_000, "1001/1", "Vyúčtování 2025"),
        pocatecni.Polozka("311200", -250_000, "1001/2", "Vyúčtování 2025"),
        pocatecni.Polozka("311300", 2_548_000, "1001/10", "Předpisy 2025"),
    ],
)

# Jednotka → (vlastníci, účet, ze kterého platí, e-mail prvního vlastníka)
VLASTNICI: dict[str, tuple[list[str], str, str | None]] = {
    "1001/1": (["Jan Novák", "Marie Nováková"], "19-123457/0800", "novakovi@example.cz"),
    "1001/2": (["Petr Dvořák"], "1234567890/3030", "petr.dvorak@example.cz"),
    "1001/3": (["Alena Králová"], "2201234561/2010", None),
    "1001/4": (["Tomáš Procházka"], "115-4410227/0100", "prochazka@example.cz"),
    "1001/5": (["Lucie Veselá", "Martin Veselý"], "2201234565/2010", "vesela@example.cz"),
    "1001/6": (["Hana Marková"], "670100-2201234567/6210", "markova@example.cz"),
    "1001/7": (["Jiří Kučera"], "2201234567/2010", None),
    "1001/8": (["Eva Svobodová"], "1023456789/5500", "svobodova@example.cz"),
    "1001/9": (["Pavel Černý", "Jana Černá"], "2201234569/2010", "cerni@example.cz"),
    "1001/10": (["Ondřej Beneš"], "1987654321/0300", None),
    "1001/11": (["Kavárna Na rohu s.r.o."], "2901234511/2010", "ucetni@kavarnanarohu.example"),
    "1001/12": (["Zuzana Horáková"], "2201234512/2010", "horakova@example.cz"),
}
# Kdo některé měsíce nezaplatil: jednotka → měsíce bez platby.
NEZAPLACENO = {"1001/10": {6, 7, 8, 9}, "1001/4": {9}, "1001/7": {8}}

# (dodavatel, druh, částka v haléřích, účet dodavatele, popis)
MESICNI_FAKTURY = [
    ("Úklid Jasný s.r.o.", "UKLID", 484_000, "999563/5500", "úklid společných prostor"),
    ("Správa domů s.r.o.", "SPRAVA", 868_780, "999395/5500", "správa a účetnictví"),
    ("Pražská teplárenská a.s.", "TEPLO", 3_150_000, "1700441/0100", "dodávka tepla"),
    ("Vodárny hl. m. Prahy a.s.", "VODA", 1_240_000, "5000112/0100", "vodné a stočné"),
]
JEDNOTLIVE_FAKTURY = [
    (2, "Pojišťovna Domov a.s.", "POJISTENI", 4_650_000, "3300915/0800", "pojištění domu 2026"),
    (3, "Výtahy Servis s.r.o.", "VYTAH", 1_452_000, "4400278/0300", "servis výtahu 1. čtvrtletí"),
    (5, "Revize Kolář", "OSTATNI", 786_500, "2600331/2010", "revize elektroinstalace"),
    (6, "Výtahy Servis s.r.o.", "VYTAH", 1_452_000, "4400278/0300", "servis výtahu 2. čtvrtletí"),
    (9, "Výtahy Servis s.r.o.", "VYTAH", 1_452_000, "4400278/0300", "servis výtahu 3. čtvrtletí"),
    (10, "Klempířství Vrba s.r.o.", "FOND_OPRAV", 18_634_000, "7700123/0600", "oprava střechy"),
]
PREVOD_DO_FONDU = 4_000_000  # měsíčně z provozního účtu na účet fondu oprav


def _vs(jednotka: str) -> str:
    return f"1001{int(jednotka.split('/')[1]):03d}01"


def _ucet(cely: str) -> tuple[str, str]:
    cislo, kod = cely.split("/")
    return cislo, kod


def _konec_mesice(m: int) -> date:
    return min(date(2026, m, monthrange(2026, m)[1]), date(2026, 11, 20))


def _lide(s, profil) -> None:
    for jednotka, (jmena, ucet, email) in VLASTNICI.items():
        clenove = []
        for i, jmeno in enumerate(jmena):
            osoba = lide.pridej_osobu(
                s,
                lide.UdajeOsoby(
                    jmeno=jmeno,
                    adresa="Ukázková 1001/12, 120 00 Praha 2",
                    email=email if i == 0 else None,
                    ucet=ucet if i == 0 else None,
                    souhlas_email=date(2025, 11, 12) if i == 0 and email else None,
                ),
                KDO,
            )
            clenove.append(lide.ClenVlastnictvi(osoba_id=osoba.id))
        lide.zapis_vlastnictvi(
            s, profil, jednotka, date(2019, 3, 1), clenove, "výpis z katastru", KDO
        )


def _faktury_mesice(s, profil, m: int) -> list[tuple[str, int, str, str]]:
    """Zaúčtuje faktury měsíce a vrátí, co se za ně v tom měsíci platí."""
    k_uhrade = []
    polozky = [(m, *f) for f in MESICNI_FAKTURY] + [f for f in JEDNOTLIVE_FAKTURY if f[0] == m]
    for i, (_, dodavatel, druh, castka, ucet, popis) in enumerate(polozky):
        duzp = date(2026, m, 3 + i)
        vs = f"26{m:02d}{i + 1:02d}"
        faktury.zauctuj(
            s,
            profil,
            faktury.NovaFaktura(
                dodavatel=dodavatel,
                castka=castka,
                duzp=duzp,
                splatnost=date(2026, 11, 30) if druh == "FOND_OPRAV" else date(2026, m, 17 + i),
                druh=druh,
                popis=popis,
                cislo_dodavatele=f"FV{vs}",
                vs=vs,
                ucet_dodavatele=ucet,
                rozhodnuti="shromáždění 12. 11. 2025, bod 4" if druh == "FOND_OPRAV" else None,
            ),
            zadal=KDO,
        )
        # Oprava střechy se platí z fondu oprav až v listopadu; ostatní z provozního účtu.
        if druh != "FOND_OPRAV":
            k_uhrade.append((dodavatel, castka, ucet, vs))
    return k_uhrade


def _vypisy_mesice(profil, nast, m: int, k_uhrade, stavy: dict[str, int]) -> list[bytes]:
    pohyby = []
    n = 0

    def dalsi() -> str:
        nonlocal n
        n += 1
        return f"26{m:02d}{n:03d}"

    mesicni = predpisy.mesicni_celkem(profil, nast, 2026, m) if m >= PRVNI_PREDPIS else {}
    for i, (jednotka, (jmena, ucet, _)) in enumerate(VLASTNICI.items()):
        if not mesicni or m in NEZAPLACENO.get(jednotka, ()):
            continue
        cislo, kod = _ucet(ucet)
        pohyby.append(
            pohyb(
                PROVOZNI,
                mesicni[jednotka],
                doklad=dalsi(),
                protiucet=cislo,
                banka=kod,
                # Paní Králová variabilní symbol nepíše; platbu pozná aplikace podle účtu.
                vs="" if jednotka == "1001/3" else _vs(jednotka),
                nazev=jmena[0],
                datum=date(2026, m, 4 + i),
                zprava=f"zálohy {m}/2026",
            )
        )
    for dodavatel, castka, ucet, vs in k_uhrade:
        cislo, kod = _ucet(ucet)
        pohyby.append(
            pohyb(
                PROVOZNI,
                -castka,
                doklad=dalsi(),
                protiucet=cislo,
                banka=kod,
                vs=vs,
                nazev=dodavatel,
                datum=date(2026, m, 20),
            )
        )
    pohyby.append(
        pohyb(
            PROVOZNI,
            -PREVOD_DO_FONDU,
            doklad=dalsi(),
            protiucet=FOND,
            banka="5500",
            nazev="Převod fond oprav",
            datum=min(date(2026, m, 25), _konec_mesice(m)),
        )
    )
    konec = _konec_mesice(m)
    pohyby.append(pohyb(PROVOZNI, -5_000, doklad=dalsi(), nazev="Poplatek za vedení", datum=konec))
    od = date(2025, 12, 31) if m == 1 else _konec_mesice(m - 1)
    provozni = vypis(
        PROVOZNI, m, od=od, datum=konec, stary=stavy[PROVOZNI], pohyby=pohyby, nazev="SVJ PROVOZNI"
    )
    stavy[PROVOZNI] += sum((1 if p[0][60] == "2" else -1) * int(p[0][48:60]) for p in pohyby)
    fond = vypis(
        FOND,
        m,
        od=od,
        datum=konec,
        stary=stavy[FOND],
        pohyby=[
            pohyb(
                FOND,
                PREVOD_DO_FONDU,
                doklad=f"26{m:02d}900",
                protiucet=PROVOZNI,
                banka="5500",
                nazev="Převod fond oprav",
                datum=min(date(2026, m, 25), konec),
            )
        ],
        nazev="SVJ FOND OPRAV",
    )
    stavy[FOND] += PREVOD_DO_FONDU
    return [provozni, fond]


def _zauctuj_pohyby(s, profil, nast, m: int, nejvys: int | None = None) -> None:
    ucty = list(s.scalars(select(BankovniUcet)))
    kontext = banka.KontextNavrhu(
        profil=profil,
        mesicni=predpisy.mesicni_celkem(profil, nast, 2026, max(m, PRVNI_PREDPIS)),
        otevrene_faktury=faktury.prehled(s, rok=2026, jen_otevrene=True),
        ucty_vlastniku=lide.jednotky_podle_uctu(s, date(2026, m, 15)),
    )
    for p in s.scalars(select(BankovniPohyb).order_by(BankovniPohyb.id)):
        if p.parovani is not None:
            continue
        if nejvys is not None:
            if nejvys == 0:
                break
            nejvys -= 1
        navrh = banka.navrhni(p, ucty, list(s.scalars(select(PravidloParovani))), kontext)
        if navrh is None:
            raise SystemExit(f"Pro pohyb {p.nazev} {p.castka} není návrh zaúčtování.")
        banka.zauctuj_pohyb(
            s, profil, p.id, navrh.operace, navrh.vstupy, zauctoval=KDO, zapamatovat=True
        )


def main() -> None:
    if os.environ.get("PROFIL", nastaveni().profil) != "ukazka":
        sys.exit("Ukázková data patří jen k profilu ukazka (nastavte PROFIL=ukazka).")
    profil = profily.nacti("ukazka")
    with sezeni()() as s:
        if s.scalar(select(func.count()).select_from(Zapis)) or s.scalar(
            select(func.count()).select_from(Obdobi)
        ):
            sys.exit("Databáze není prázdná, ukázková data se do ní nezapíšou.")
        s.add_all([Obdobi(rok=2025, stav="uzavrene"), Obdobi(rok=2026, stav="otevrene")])
        s.flush()
        pocatecni.zauctuj(s, profil, POCATECNI, zauctoval=KDO)
        _lide(s, profil)
        rozhodnuti.pridej(
            s,
            rozhodnuti.UdajeRozhodnuti(
                organ="shromazdeni",
                datum=date(2025, 11, 12),
                nazev="Výše záloh a rozpočet na rok 2026",
                bod="4",
                text="Shromáždění schvaluje rozpočet na rok 2026, výši záloh od 1. 1. 2026"
                " a opravu střechy z fondu oprav do 200 000 Kč.",
                hlasovani="pro 7 420/8 600, proti 0, zdrželo se 543/8 600",
                ulozeni="zápis ze shromáždění, složka Shromáždění 2025",
            ),
            KDO,
        )
        nast = predpisy.nacti(profil, s)
        stavy = {PROVOZNI: 42_000_000, FOND: 86_000_000}
        for m in range(1, DNES.month + 1):
            if m >= PRVNI_PREDPIS:
                predpisy.vygeneruj(s, profil, nast, 2026, m, zauctoval=KDO, dnes=DNES)
            k_uhrade = _faktury_mesice(s, profil, m)
            for i, data in enumerate(_vypisy_mesice(profil, nast, m, k_uhrade, stavy)):
                banka.nahraj(
                    s,
                    profil,
                    data,
                    nazev_souboru=f"vypis-{'fond' if i else 'provozni'}-2026-{m:02d}.gpc",
                    nahral=KDO,
                    ucel="fond_oprav" if i else "provozni",
                )
            posledni = m == POSLEDNI_VYPIS
            _zauctuj_pohyby(s, profil, nast, m, ZAUCTOVANO_Z_POSLEDNIHO if posledni else None)
        s.commit()
    print("Ukázková data za rok 2026 jsou v databázi.")


if __name__ == "__main__":
    main()
