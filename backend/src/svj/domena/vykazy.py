"""Rozvaha a výkaz zisku a ztráty ve zkráceném rozsahu podle vyhlášky 504/2002 Sb.

Zkrácený rozsah obsahuje jen položky označené velkými písmeny a římskými číslicemi
(§ 3a, přílohy č. 1 a 2). Položky se vykazují v celých tisících Kč (§ 4 odst. 3).
Řádek se určuje podle účtové skupiny (první dvě číslice účtu).
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

# (strana, řádek) podle účtové skupiny. Ověřeno proti příloze č. 1 a 2 vyhlášky 504/2002
# v aktuálním znění (verze 10, od 1. 1. 2024).
ROZVAHA: dict[str, tuple[str, str]] = {
    "01": ("aktiva", "A.I"),
    "02": ("aktiva", "A.II"),
    "03": ("aktiva", "A.II"),
    "06": ("aktiva", "A.III"),
    "07": ("aktiva", "A.IV"),
    "08": ("aktiva", "A.IV"),
    "11": ("aktiva", "B.I"),
    "12": ("aktiva", "B.I"),
    "13": ("aktiva", "B.I"),
    "21": ("aktiva", "B.III"),
    "22": ("aktiva", "B.III"),
    "26": ("aktiva", "B.III"),
    "31": ("aktiva", "B.II"),
    "37_md": ("aktiva", "B.II"),
    "38_md": ("aktiva", "B.IV"),
    "32": ("pasiva", "B.III"),
    "33": ("pasiva", "B.III"),
    "34_md": ("aktiva", "B.II"),  # nároky na dotace, B.II.11–12
    "34_d": ("pasiva", "B.III"),
    "37_d": ("pasiva", "B.III"),
    "38_d": ("pasiva", "B.IV"),
    "94": ("pasiva", "B.I"),
    "95": ("pasiva", "B.II"),
    "90": ("pasiva", "A.I"),
    "91": ("pasiva", "A.I"),
    "93": ("pasiva", "A.II"),
}
# Účty, které v rozvaze mají jiný řádek, než napovídá skupina.
ROZVAHA_UCTY: dict[str, tuple[str, str]] = {
    "041": ("aktiva", "A.I"),  # nedokončený dlouhodobý nehmotný majetek
    "042": ("aktiva", "A.II"),  # nedokončený dlouhodobý hmotný majetek
    "043": ("aktiva", "A.III"),  # pořizovaný dlouhodobý finanční majetek
    "391": ("aktiva", "B.II"),  # opravná položka snižuje pohledávky, B.II.19
    "314": ("aktiva", "B.II"),  # poskytnuté provozní zálohy, B.II.4
    "315": ("aktiva", "B.II"),  # ostatní pohledávky, B.II.5
    "381": ("aktiva", "B.IV"),
    "385": ("aktiva", "B.IV"),
    "383": ("pasiva", "B.IV"),
    "384": ("pasiva", "B.IV"),
    "388": ("aktiva", "B.II"),  # dohadné účty aktivní, B.II.18
    "389": ("pasiva", "B.III"),  # dohadné účty pasivní, B.III.22
    "378": ("aktiva", "B.II"),
    "379": ("pasiva", "B.III"),
}
VZZ: dict[str, tuple[str, str]] = {
    "50": ("naklady", "A.I"),
    "51": ("naklady", "A.I"),
    "52": ("naklady", "A.III"),
    "53": ("naklady", "A.IV"),
    "54": ("naklady", "A.V"),
    "55": ("naklady", "A.VI"),
    "58": ("naklady", "A.VII"),
    "59": ("naklady", "A.VIII"),
    "69": ("vynosy", "B.I"),
    "68": ("vynosy", "B.II"),
    "60": ("vynosy", "B.III"),
    "64": ("vynosy", "B.IV"),
    "65": ("vynosy", "B.V"),
}
NEVYKAZUJE_SE = {"39", "96"}  # vnitřní zúčtování a závěrkové účty musí mít nulový zůstatek


class ChybaVykazu(ValueError):
    pass


@dataclass
class Vykaz:
    radky: dict[tuple[str, str], int]  # (strana, řádek) -> haléře
    celkem: dict[str, int]  # strana -> haléře

    def v_tisicich(self) -> dict[tuple[str, str], int]:
        return {k: zaokrouhli_na_tisice(v) for k, v in self.radky.items()}

    def celkem_v_tisicich(self) -> dict[str, int]:
        return {k: zaokrouhli_na_tisice(v) for k, v in self.celkem.items()}


def zaokrouhli_na_tisice(halire: int) -> int:
    """Matematické zaokrouhlení na celé tisíce Kč (polovina nahoru, od nuly)."""
    tisic = 100_000
    znamenko = -1 if halire < 0 else 1
    return znamenko * ((abs(halire) + tisic // 2) // tisic)


def _radek_rozvahy(ucet: str, zustatek: int) -> tuple[str, str]:
    if ucet[:3] in ROZVAHA_UCTY:
        return ROZVAHA_UCTY[ucet[:3]]
    skupina = ucet[:2]
    if skupina in ("34", "37", "38"):
        return ROZVAHA[f"{skupina}_{'md' if zustatek >= 0 else 'd'}"]
    if skupina not in ROZVAHA:
        raise ChybaVykazu(f"účet {ucet} nemá přiřazený řádek rozvahy")
    return ROZVAHA[skupina]


def _casti(ucet: str, z: int, rozpad: Mapping[str, Iterable[int]]) -> list[int]:
    """Zůstatek účtu rozdělený na analytiky (např. po vlastnících). Co se do analytik
    nevejde, zůstane jako jedna část, takže součet vždy sedí se zůstatkem účtu."""
    casti = [c for c in rozpad.get(ucet, ()) if c]
    zbytek = z - sum(casti)
    return [*casti, zbytek] if zbytek or not casti else casti


def rozvaha(zustatky: Mapping[str, int], rozpad: Mapping[str, Iterable[int]] = {}) -> Vykaz:
    """`zustatky`: účet -> zůstatek v haléřích, kladný na straně MD.

    `rozpad`: účet -> zůstatky jeho analytik (např. pohledávky po vlastnících). Analytika se
    zůstatkem na opačné straně, než účet obvykle má, se vykáže na druhé straně rozvahy:
    přeplatek vlastníka na 311 je závazek, ne snížení pohledávek za ostatními (aktiva
    a pasiva se podle § 7 odst. 6 zákona o účetnictví vzájemně nezúčtovávají).
    """
    radky: dict[tuple[str, str], int] = {}
    # Před uzavřením roku leží výsledek hospodaření ještě na nákladech a výnosech; v rozvaze
    # patří do vlastních zdrojů (A.II), jinak by se aktiva a pasiva nerovnala.
    vysledek = -sum(z for ucet, z in zustatky.items() if ucet[0] in "56")
    if vysledek:
        radky[("pasiva", "A.II")] = vysledek
    for ucet, z in zustatky.items():
        if ucet[0] in "56":
            continue
        if ucet[:2] in NEVYKAZUJE_SE and ucet[:3] not in ROZVAHA_UCTY:
            if z:
                raise ChybaVykazu(f"účet {ucet} musí mít k rozvahovému dni nulový zůstatek, má {z}")
            continue
        for cast in _casti(ucet, z, rozpad):
            strana, radek = _radek_rozvahy(ucet, cast)
            if ucet in rozpad:
                if strana == "aktiva" and cast < 0:
                    strana, radek = "pasiva", "B.III"
                elif strana == "pasiva" and cast > 0:
                    strana, radek = "aktiva", "B.II"
            hodnota = cast if strana == "aktiva" else -cast
            radky[(strana, radek)] = radky.get((strana, radek), 0) + hodnota
    celkem = {s: sum(v for (st, _), v in radky.items() if st == s) for s in ("aktiva", "pasiva")}
    return Vykaz(radky, celkem)


def vysledovka(zustatky: Mapping[str, int]) -> Vykaz:
    radky: dict[tuple[str, str], int] = {}
    for ucet, z in zustatky.items():
        if ucet[0] not in "56":
            continue
        if ucet[:2] not in VZZ:
            raise ChybaVykazu(f"účet {ucet} nemá přiřazený řádek výkazu zisku a ztráty")
        strana, radek = VZZ[ucet[:2]]
        hodnota = z if strana == "naklady" else -z
        radky[(strana, radek)] = radky.get((strana, radek), 0) + hodnota
    celkem = {s: sum(v for (st, _), v in radky.items() if st == s) for s in ("naklady", "vynosy")}
    celkem["vysledek"] = celkem["vynosy"] - celkem["naklady"]
    return Vykaz(radky, celkem)
