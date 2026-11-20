"""Čtečka výpisů ve formátu GPC (ABO).

Formát podporují všechny české banky včetně Fio a Raiffeisenbank. Řádky mají pevnou
délku 128 znaků (bez CR LF), údaje jsou zarovnané nulami zleva a částky jsou v haléřích.

- 074: hlavička výpisu (účet, starý a nový zůstatek, obraty, číslo výpisu, datum),
- 075: pohyb (protiúčet, číslo dokladu, částka, kód účtování, VS, KS s kódem banky, SS),
- 076, 078, 079: doplňující text k předchozímu pohybu (zpráva pro příjemce, název).

Čísla účtů mohou být v „edičním“ (standardním) nebo „vnitřním“ pořadí číslic; vnitřní
pořadí se pozná podle čísla vlastního účtu, které uživatel zná (viz `cti`).

Zdroje: Fio banka, „Struktura GPC formátu (pro elektronické výpisy)“;
Raiffeisenbank, „eKomunikátor – popis datových struktur“, kap. 1.2.
"""

from dataclasses import dataclass, field
from datetime import date


class ChybaVypisu(ValueError):
    pass


# Vnitřní pořadí: i-tý znak vnitřního tvaru je VNITRNI[i]-tý znak standardního tvaru (RB, 1.2).
VNITRNI = (16, 14, 15, 12, 7, 8, 9, 10, 11, 13, 1, 2, 3, 4, 5, 6)


def z_vnitrniho(cislo16: str) -> str:
    """Převede 16 číslic z vnitřního pořadí do standardního."""
    standard = [""] * 16
    for i, j in enumerate(VNITRNI):
        standard[j - 1] = cislo16[i]
    return "".join(standard)


def citelne_cislo(cislo16: str) -> str | None:
    """16 číslic (předčíslí 6 + číslo 10) → „19-2784000277“, nebo None pro samé nuly."""
    predcisli, cislo = cislo16[:6].lstrip("0"), cislo16[6:].lstrip("0")
    if not predcisli and not cislo:
        return None
    return f"{predcisli}-{cislo}" if predcisli else cislo


def normalizuj_cislo(text: str) -> str:
    """Číslo účtu z libovolného zápisu („000019-2784000277/0100“) → „19-2784000277“."""
    cislo = text.split("/")[0].strip()
    predcisli, _, zbytek = cislo.rpartition("-")
    p, z = predcisli.lstrip("0"), zbytek.lstrip("0")
    if (p and not p.isdigit()) or not z.isdigit():
        raise ChybaVypisu(f"neplatné číslo účtu {text!r}")
    return f"{p}-{z}" if p else z


@dataclass
class Pohyb:
    poradi: int
    id_banky: str | None
    castka: int  # haléře; příjem kladně, výdaj záporně
    kod_uctovani: str
    protiucet: str | None
    kod_banky: str | None
    vs: str | None
    ks: str | None
    ss: str | None
    nazev: str
    valuta: date | None
    datum: date | None  # datum splatnosti / připsání z pohybu
    zprava: list[str] = field(default_factory=list)

    @property
    def storno(self) -> bool:
        return self.kod_uctovani in {"4", "5"}


@dataclass
class Vypis:
    ucet: str  # standardní tvar, např. „2804357004“
    nazev_uctu: str
    cislo: int
    datum: date
    datum_stareho_zustatku: date
    stary_zustatek: int
    novy_zustatek: int
    obraty_debet: int
    obraty_kredit: int
    vnitrni_format: bool
    pohyby: list[Pohyb]


def _datum(text: str, povinne: bool = True) -> date | None:
    if text.strip("0 ") == "":
        if povinne:
            raise ChybaVypisu(f"chybí datum ({text!r})")
        return None
    try:
        return date(2000 + int(text[4:6]), int(text[2:4]), int(text[0:2]))
    except ValueError as e:
        raise ChybaVypisu(f"neplatné datum {text!r}") from e


def _cislo(text: str, co: str) -> int:
    if not text.isdigit():
        raise ChybaVypisu(f"{co}: očekávám číslice, je tam {text!r}")
    return int(text)


def _znamenko(znak: str, castka: int, co: str) -> int:
    if znak in "+0":
        return castka
    if znak in "-–":
        return -castka
    raise ChybaVypisu(f"{co}: neznámé znaménko {znak!r}")


def _symbol(text: str) -> str | None:
    s = text.strip().lstrip("0")
    return s or None


def _dekoduj(data: bytes) -> str:
    # Banky deklarují ASCII, české názvy ale bývají ve windows-1250 (Fio, RB) nebo UTF-8.
    for kodovani in ("utf-8", "cp1250"):
        try:
            return data.decode(kodovani)
        except UnicodeDecodeError:
            continue
    raise ChybaVypisu("soubor není textový výpis")


def cti(data: bytes, znama_cisla: set[str] | None = None) -> list[Vypis]:
    """Přečte soubor GPC. Soubor může obsahovat víc výpisů (víc hlaviček 074).

    `znama_cisla` jsou standardní čísla účtů SVJ; podle nich se pozná vnitřní pořadí číslic.
    Bez nich se bere ediční (standardní) pořadí.
    """
    vypisy: list[Vypis] = []
    aktualni: Vypis | None = None
    for n, radek in enumerate(_dekoduj(data).splitlines(), start=1):
        radek = radek.rstrip("\r\n\x1a")
        if not radek.strip():
            continue
        typ = radek[:3]
        try:
            if typ == "074":
                aktualni = _hlavicka(radek, znama_cisla or set())
                vypisy.append(aktualni)
            elif typ == "075":
                if aktualni is None:
                    raise ChybaVypisu("pohyb před hlavičkou výpisu")
                aktualni.pohyby.append(_pohyb(radek, len(aktualni.pohyby) + 1, aktualni))
            elif typ in {"076", "078", "079"}:
                if aktualni is None or not aktualni.pohyby:
                    raise ChybaVypisu("doplňující text bez pohybu")
                # 078 a 079 nesou dvě pole po 35 znacích; 076 má u každé banky jiný tvar.
                text = radek[3:]
                for kus in (text[:35], text[35:70]) if typ != "076" else (text,):
                    if kus.strip():
                        aktualni.pohyby[-1].zprava.append(kus.strip())
            else:
                raise ChybaVypisu(f"neznámý typ záznamu {typ!r}")
        except ChybaVypisu as e:
            raise ChybaVypisu(f"řádek {n}: {e}") from e
    if not vypisy:
        raise ChybaVypisu("soubor neobsahuje žádný výpis (záznam 074)")
    for v in vypisy:
        zkontroluj(v)
    return vypisy


def _hlavicka(r: str, znama: set[str]) -> Vypis:
    if len(r) < 114:
        raise ChybaVypisu(f"hlavička je krátká ({len(r)} znaků, čekám 128)")
    surove = r[3:19]
    ucet = citelne_cislo(surove)
    vnitrni = False
    if ucet not in znama:
        prevedene = citelne_cislo(z_vnitrniho(surove))
        if prevedene in znama:
            ucet, vnitrni = prevedene, True
    if ucet is None:
        raise ChybaVypisu("hlavička neobsahuje číslo účtu")
    return Vypis(
        ucet=ucet,
        nazev_uctu=r[19:39].strip(),
        datum_stareho_zustatku=_datum(r[39:45]),
        stary_zustatek=_znamenko(r[59], _cislo(r[45:59], "starý zůstatek"), "starý zůstatek"),
        novy_zustatek=_znamenko(r[74], _cislo(r[60:74], "nový zůstatek"), "nový zůstatek"),
        obraty_debet=_znamenko(r[89], _cislo(r[75:89], "obraty debet"), "obraty debet"),
        obraty_kredit=_znamenko(r[104], _cislo(r[90:104], "obraty kredit"), "obraty kredit"),
        cislo=_cislo(r[105:108], "číslo výpisu"),
        datum=_datum(r[108:114]),
        vnitrni_format=vnitrni,
        pohyby=[],
    )


def _pohyb(r: str, poradi: int, vypis: Vypis) -> Pohyb:
    if len(r) < 128:
        r = r.ljust(128)
    protiucet16 = r[19:35]
    if vypis.vnitrni_format and protiucet16.strip("0"):
        protiucet16 = z_vnitrniho(protiucet16)
    kod = r[60]
    if kod not in "1245":
        raise ChybaVypisu(f"neznámý kód účtování {kod!r}")
    castka = _cislo(r[48:60], "částka")
    # 1 výdaj, 2 příjem, 4 storno výdaje (peníze se vrací), 5 storno příjmu
    znamenko = 1 if kod in "24" else -1
    ks_pole = r[71:81]
    kod_banky = ks_pole[2:6].strip("0 ") and ks_pole[2:6]
    return Pohyb(
        poradi=poradi,
        id_banky=r[35:48].strip().lstrip("0") or None,
        castka=znamenko * castka,
        kod_uctovani=kod,
        protiucet=citelne_cislo(protiucet16),
        kod_banky=kod_banky or None,
        vs=_symbol(r[61:71]),
        ks=_symbol(ks_pole[6:10]),
        ss=_symbol(r[81:91]),
        valuta=_datum(r[91:97], povinne=False),
        nazev=r[97:117].strip(),
        datum=_datum(r[122:128], povinne=False),
    )


def zkontroluj(v: Vypis) -> None:
    """Součet pohybů musí sedět na obraty i na rozdíl zůstatků."""
    debet = sum(-p.castka for p in v.pohyby if p.kod_uctovani in "14")
    kredit = sum(p.castka for p in v.pohyby if p.kod_uctovani in "25")
    if debet != v.obraty_debet or kredit != v.obraty_kredit:
        raise ChybaVypisu(
            f"výpis {v.cislo}: součet pohybů neodpovídá obratům v hlavičce "
            f"(výdaje {debet} × {v.obraty_debet}, příjmy {kredit} × {v.obraty_kredit} haléřů)"
        )
    if v.stary_zustatek - debet + kredit != v.novy_zustatek:
        raise ChybaVypisu(
            f"výpis {v.cislo}: starý zůstatek a pohyby nedávají nový zůstatek "
            f"({v.stary_zustatek} − {debet} + {kredit} ≠ {v.novy_zustatek} haléřů)"
        )


def datum_pohybu(v: Vypis, p: Pohyb) -> date:
    """Datum zaúčtování pohybu: datum splatnosti/připsání, jinak valuta, jinak datum výpisu."""
    return p.datum or p.valuta or v.datum
