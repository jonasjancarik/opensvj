"""Peníze v celých haléřích.

Účetní logika pracuje jen s `int` haléřů. Převod z textu a do textu je jediné místo,
kde se objevují desetinná místa; float se nikde nepoužívá.
"""

import re
from decimal import Decimal, InvalidOperation

_CASTKA = re.compile(r"^-?\d+(\.\d{1,2})?$")


def halire(text: str | int) -> int:
    """Převede částku zapsanou jako "1234.50" (nebo celé číslo korun) na haléře."""
    if isinstance(text, bool):
        raise TypeError("logická hodnota není částka")
    if isinstance(text, int):
        return text * 100
    if not isinstance(text, str):
        raise TypeError(f"částka musí být text nebo celé číslo korun, ne {type(text).__name__}")
    s = text.strip().replace(" ", "")
    if not _CASTKA.match(s):
        raise ValueError(f"neplatná částka: {text!r}")
    try:
        hodnota = Decimal(s) * 100
    except InvalidOperation as e:  # pragma: no cover - regulární výraz to vyloučí
        raise ValueError(f"neplatná částka: {text!r}") from e
    return int(hodnota)


def na_text(castka: int) -> str:
    """Haléře na strojový zápis "1234.50"."""
    znamenko = "-" if castka < 0 else ""
    a = abs(castka)
    return f"{znamenko}{a // 100}.{a % 100:02d}"


def kc(castka: int) -> str:
    """Haléře na český zápis "1 234,50 Kč"."""
    znamenko = "−" if castka < 0 else ""
    a = abs(castka)
    koruny = f"{a // 100:,}".replace(",", " ")
    return f"{znamenko}{koruny},{a % 100:02d} Kč"
