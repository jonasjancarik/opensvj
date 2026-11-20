"""Vytvoří ukázkový výpis GPC s vymyšlenými daty: uv run python -m tests.ukazka"""

from datetime import date
from pathlib import Path

from tests.gpc_pomoc import pohyb, vypis

UCET = "2800000001"
FOND = "2800000002"


def main() -> None:
    d = date(2026, 1, 15)
    platby = [
        pohyb(
            UCET,
            1_038_000,
            doklad="2601001",
            protiucet="19-123457",
            banka="0800",
            vs="100100501",
            nazev="Novák Jan",
            datum=date(2026, 1, 5),
            zprava="zaloha leden",
        ),
        pohyb(
            UCET,
            612_500,
            doklad="2601002",
            protiucet="670100-2201234567",
            banka="6210",
            vs="100100801",
            nazev="Svobodová Eva",
            datum=date(2026, 1, 6),
        ),
        pohyb(
            UCET,
            845_000,
            doklad="2601003",
            protiucet="1234567890",
            banka="3030",
            nazev="Dvořák Petr",
            datum=date(2026, 1, 8),
            zprava="SVJ leden byt 2",
        ),
        pohyb(
            UCET,
            -484_000,
            doklad="2601004",
            protiucet="999563",
            banka="5500",
            vs="2601",
            nazev="Úklid Jasný s.r.o.",
            datum=d,
            zprava="úklid 12/2025",
        ),
        pohyb(
            UCET,
            -868_780,
            doklad="2601005",
            protiucet="999395",
            banka="5500",
            vs="2601014",
            nazev="Správa domů s.r.o.",
            datum=d,
        ),
        pohyb(
            UCET,
            -20_000_000,
            doklad="2601006",
            protiucet=FOND,
            banka="5500",
            nazev="Převod fond oprav",
            datum=date(2026, 1, 20),
        ),
        pohyb(UCET, -5_000, doklad="2601007", nazev="Poplatek za vedení", datum=date(2026, 1, 31)),
    ]
    data = vypis(
        UCET,
        1,
        od=date(2025, 12, 31),
        datum=date(2026, 1, 31),
        stary=42_000_000,
        pohyby=platby,
        nazev="SVJ PROVOZNI",
    )
    cesta = Path(__file__).resolve().parents[2] / "ukazky" / "vypis-provozni-2026-01.gpc"
    cesta.write_bytes(data)
    print(cesta)


if __name__ == "__main__":
    main()
