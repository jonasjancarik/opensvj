"""Sestavení testovacích výpisů GPC podle popisu Fio a RB. Data jsou vymyšlená."""

from datetime import date

from svj.domena.gpc import VNITRNI


def _d(d: date | None) -> str:
    return d.strftime("%d%m%y") if d else "000000"


def _ucet16(cislo: str) -> str:
    predcisli, _, zbytek = cislo.rpartition("-")
    return predcisli.zfill(6) + zbytek.zfill(10)


def do_vnitrniho(standard16: str) -> str:
    return "".join(standard16[j - 1] for j in VNITRNI)


def pohyb(
    ucet: str,
    castka: int,
    *,
    doklad: str,
    protiucet: str = "0",
    banka: str = "0000",
    vs: str = "",
    ks: str = "",
    ss: str = "",
    nazev: str = "",
    datum: date,
    kod: str | None = None,
    zprava: str = "",
    vnitrni: bool = False,
) -> list[str]:
    kod = kod or ("2" if castka > 0 else "1")
    u, p = _ucet16(ucet), _ucet16(protiucet)
    if vnitrni:
        u, p = do_vnitrniho(u), do_vnitrniho(p) if p.strip("0") else p
    r = (
        "075"
        + u
        + p
        + doklad.zfill(13)
        + str(abs(castka)).zfill(12)
        + kod
        + vs.zfill(10)
        + "00"
        + banka.zfill(4)
        + ks.zfill(4)
        + ss.zfill(10)
        + _d(datum)
        + nazev.ljust(20)[:20]
        + "0"
        + "0203"
        + _d(datum)
    )
    assert len(r) == 128, len(r)
    radky = [r]
    if zprava:
        radky.append("078" + zprava.ljust(70)[:70])
    return radky


def vypis(
    ucet: str,
    cislo: int,
    *,
    od: date,
    datum: date,
    stary: int,
    pohyby: list[list[str]],
    nazev: str = "SVJ",
    vnitrni: bool = False,
) -> bytes:
    castky = []
    for p in pohyby:
        c, kod = int(p[0][48:60]), p[0][60]
        castky.append((kod, c))
    debet = sum(c for k, c in castky if k == "1") - sum(c for k, c in castky if k == "4")
    kredit = sum(c for k, c in castky if k == "2") - sum(c for k, c in castky if k == "5")
    novy = stary - debet + kredit

    def z(n: int, delka: int, nula: str) -> str:
        return str(abs(n)).zfill(delka) + ("-" if n < 0 else nula)

    u = _ucet16(ucet)
    if vnitrni:
        u = do_vnitrniho(u)
    h = (
        "074"
        + u
        + nazev.ljust(20)[:20]
        + _d(od)
        + z(stary, 14, "+")
        + z(novy, 14, "+")
        + z(debet, 14, "0")
        + z(kredit, 14, "0")
        + str(cislo).zfill(3)
        + _d(datum)
        + " " * 14
    )
    assert len(h) == 128, len(h)
    radky = [h] + [r for p in pohyby for r in p]
    return ("\r\n".join(radky) + "\r\n").encode("cp1250")
