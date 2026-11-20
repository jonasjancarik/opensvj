"""Roční vyúčtování služeb podle zákona 67/2013 Sb. (teplo, voda, výtah, úklid, odpad…).

Náklady služby za rok (sběrný účet služby, `naklady_sluzeb.*`) se rozdělí na jednotky podle
klíče služby z profilu a porovnají se s předepsanými zálohami jednotky na tutéž službu.
Rozdíl za všechny služby dohromady je nedoplatek nebo přeplatek jednotky.

Klíče:
- `osoby`: osobo-měsíce podle počtu osob v předpisu (výchozí klíč, § 5 odst. 2),
- `jednotka`, `plocha`, `podil`: rovným dílem, podle podlahové plochy, podle podílu,
- `meridla`: podle roční spotřeby z odečtů měřidel druhu `meridlo`,
- `zuctovatel`: náklad jednotky převzatý od zúčtovatele (teplo a teplá voda podle vyhlášky
  269/2015 Sb.); součet musí přesně sedět na náklady v účetnictví.

Vyúčtování jde jen současnému vlastníkovi jednotky; převodce s nabyvatelem se vyrovnají
mezi sebou (§ 1186 odst. 1 OZ, výklad Durec s. 29).
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from fractions import Fraction

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from . import denik, dluznici, meridla, pocatecni, predpisy, vyuctovani_spravy
from .db import RadekZapisu, VysledekZuctovatele, Zapis
from .domena import katalog
from .domena.penize import na_text
from .domena.profil import Profil
from .domena.rozdeleni import rozdel

OPERACE = "vyuctovani-sluzeb"
KLICE = {
    "osoby": "podle počtu osob",
    "jednotka": "každá jednotka stejně",
    "plocha": "podle podlahové plochy",
    "podil": "podle podílů na společných částech",
    "meridla": "podle spotřeby na měřidlech",
    "zuctovatel": "podle rozúčtování od zúčtovatele",
}


class ChybaVyuctovani(ValueError):
    pass


@dataclass
class Sluzba:
    kod: str
    nazev: str
    klic: str
    meridlo: str | None  # druh měřidla u klíče `meridla`
    naklady: int = 0
    zalohy: int = 0
    problem: str | None = None  # proč náklady nejde rozdělit

    @property
    def jak_se_deli(self) -> str:
        text = KLICE.get(self.klic, self.klic)
        if self.meridlo:
            druh = meridla.DRUHY.get(self.meridlo, (self.meridlo, ""))[0].lower()
            text += f" ({druh})"
        return text


@dataclass
class Jednotka:
    jednotka: str
    osobomesice: int
    zalohy: dict[str, int] = field(default_factory=dict)
    naklady: dict[str, int] = field(default_factory=dict)
    spotreba: dict[str, Decimal] = field(default_factory=dict)  # služba → spotřeba z měřidel
    nezaplacene: int = 0  # nezaplacené měsíční zálohy roku, vedené zvlášť

    @property
    def rozdil(self) -> int:
        """Kladný = nedoplatek, záporný = přeplatek."""
        return sum(self.naklady.values()) - sum(self.zalohy.values())


@dataclass
class Vyuctovani:
    rok: int
    sluzby: list[Sluzba]
    jednotky: list[Jednotka]
    zapis: Zapis | None

    @property
    def splatnost(self) -> date:
        return vyuctovani_spravy.splatnost(self.rok)

    @property
    def doruceni(self) -> date:
        """Do kdy musí vyúčtování dojít vlastníkům (4 měsíce od konce období, § 7 odst. 1)."""
        return date(self.rok + 1, 4, 30)


def klic(rok: int) -> str:
    return f"{OPERACE}:{rok}"


def sluzby(profil: Profil) -> list[Sluzba]:
    return [
        Sluzba(kod, u.get("nazev", kod), u.get("klic", "osoby"), u.get("meridlo"))
        for kod, u in profil.sluzby.items()
    ]


def osobomesice(profil: Profil, nastaveni: predpisy.Nastaveni, rok: int) -> dict[str, int]:
    """Součet osob za 12 měsíců podle verze předpisu platné v měsíci (před první verzí
    se bere první verze)."""
    prvni = min(nastaveni.verze, key=lambda v: v.plati_od, default=None)
    vysledek = dict.fromkeys(profil.jednotky, 0)
    for mesic in range(1, 13):
        v = nastaveni.pro_mesic(rok, mesic) or prvni
        if v is None:
            continue
        for j in profil.jednotky:
            vysledek[j] += predpisy.osob(v, j)
    return vysledek


def vysledky_zuctovatele(s: Session, rok: int) -> dict[str, dict[str, int]]:
    """Služba → jednotka → náklad v haléřích."""
    vysledek: dict[str, dict[str, int]] = {}
    for v in s.scalars(select(VysledekZuctovatele).where(VysledekZuctovatele.rok == rok)):
        vysledek.setdefault(v.sluzba, {})[v.jednotka] = v.castka
    return vysledek


def spocitej(
    s: Session,
    profil: Profil,
    nastaveni: predpisy.Nastaveni,
    rok: int,
    dnes: date | None = None,
) -> Vyuctovani:
    dnes = dnes or date.today()
    vsechny = {x.kod: x for x in sluzby(profil)}
    zapis = denik.aktivni(s, klic(rok))
    v_roce = (
        Zapis.rok == rok,
        denik.platny(),
        Zapis.operace.not_in((OPERACE, pocatecni.OPERACE)),
    )
    md_minus_d = func.sum(
        case((RadekZapisu.strana == "md", RadekZapisu.castka), else_=-RadekZapisu.castka)
    )
    ucty_nakladu = {profil.ucet(f"naklady_sluzeb.{k}"): k for k in vsechny}
    for ucet, castka in s.execute(
        select(RadekZapisu.ucet, md_minus_d)
        .join(Zapis)
        .where(*v_roce, RadekZapisu.ucet.in_(list(ucty_nakladu)))
        .group_by(RadekZapisu.ucet)
    ):
        vsechny[ucty_nakladu[ucet]].naklady += int(castka)

    osoby = osobomesice(profil, nastaveni, rok)
    jednotky = {j: Jednotka(j, osoby[j]) for j in profil.jednotky}
    ucty_zaloh = {profil.ucet(f"zalohy_sluzby.{k}"): k for k in vsechny}
    for jednotka, ucet, castka in s.execute(
        select(RadekZapisu.jednotka, RadekZapisu.ucet, -md_minus_d)
        .join(Zapis)
        .where(
            *v_roce,
            RadekZapisu.ucet.in_(list(ucty_zaloh)),
            RadekZapisu.jednotka.is_not(None),
        )
        .group_by(RadekZapisu.jednotka, RadekZapisu.ucet)
    ):
        kod = ucty_zaloh[ucet]
        if jednotka in jednotky and castka:
            jednotky[jednotka].zalohy[kod] = int(castka)
            vsechny[kod].zalohy += int(castka)

    seznam = [x for x in vsechny.values() if x.naklady or x.zalohy]
    _rozdel(s, profil, rok, seznam, jednotky)

    for d in dluznici.prehled(s, profil, nastaveni, rok, dnes):
        if d.jednotka in jednotky:
            jednotky[d.jednotka].nezaplacene = sum(
                p.zbyva for p in d.polozky if p.mesic is not None and p.mesic.year == rok
            )
    return Vyuctovani(rok, seznam, list(jednotky.values()), zapis)


def _vahy(
    s: Session,
    profil: Profil,
    rok: int,
    x: Sluzba,
    jednotky: dict[str, Jednotka],
    spotreby: dict,
) -> dict[str, Fraction | int] | str:
    """Váhy jednotek pro klíč služby, nebo text, proč je spočítat nejde."""
    udaje = {j.oznaceni: j for j in profil.udaje_jednotek}
    if x.klic == "jednotka":
        return dict.fromkeys(jednotky, 1)
    if x.klic == "plocha":
        return {j: udaje[j].plocha for j in jednotky}
    if x.klic == "podil":
        return {j: udaje[j].podil for j in jednotky}
    if x.klic == "osoby":
        return {j: u.osobomesice for j, u in jednotky.items()}
    if x.klic == "meridla":
        if x.meridlo not in meridla.DRUHY:
            return "V profilu chybí druh měřidla, podle kterého se služba rozúčtuje."
        bez, chybi, vahy = [], [], {}
        for j, u in jednotky.items():
            sp = spotreby.get((j, x.meridlo))
            if sp is None:
                bez.append(j)
            elif sp.spotreba is None:
                chybi.append(j)
            else:
                u.spotreba[x.kod] = sp.spotreba
                vahy[j] = Fraction(str(sp.spotreba))
        if bez:
            return f"Jednotky bez měřidla: {', '.join(bez)}. Doplňte je na stránce Měřidla."
        if chybi:
            return f"Chybí odečty na začátku nebo konci roku: {', '.join(chybi)}."
        return vahy
    return f"Neznámý klíč {x.klic!r} v profilu."


def _rozdel(
    s: Session, profil: Profil, rok: int, seznam: list[Sluzba], jednotky: dict[str, Jednotka]
) -> None:
    spotreby = {(x.jednotka, x.druh): x for x in meridla.spotreba(s, rok)}
    zuctovatel = vysledky_zuctovatele(s, rok)
    for x in seznam:
        if x.klic == "zuctovatel":
            vysledky = zuctovatel.get(x.kod, {})
            soucet = sum(vysledky.values())
            if not vysledky and x.naklady:
                x.problem = "Zadejte výsledky od zúčtovatele."
            elif soucet != x.naklady:
                x.problem = (
                    f"Výsledky zúčtovatele dávají {_kc(soucet)}, v účetnictví je "
                    f"{_kc(x.naklady)} (rozdíl {_kc(soucet - x.naklady)})."
                )
            else:
                for j, c in vysledky.items():
                    if j in jednotky and c:
                        jednotky[j].naklady[x.kod] = c
            continue
        if not x.naklady:
            continue
        vahy = _vahy(s, profil, rok, x, jednotky, spotreby)
        if isinstance(vahy, str):
            x.problem = vahy
        elif not any(vahy.values()):
            x.problem = "Podle klíče nevychází na žádnou jednotku nic (součet je nula)."
        else:
            for j, c in rozdel(x.naklady, vahy).items():
                if c:
                    jednotky[j].naklady[x.kod] = c


def _kc(halire: int) -> str:
    cele, hal = divmod(abs(halire), 100)
    return ("−" if halire < 0 else "") + f"{cele:,}".replace(",", " ") + f",{hal:02d} Kč"


def proc_nejde(s: Session, nastaveni: predpisy.Nastaveni, v: Vyuctovani, dnes: date) -> str | None:
    """Důvod, proč vyúčtování ještě nejde zaúčtovat (None = jde)."""
    if v.zapis is not None:
        return None
    if dnes < date(v.rok, 12, 31):
        return f"Vyúčtování půjde zaúčtovat od 31. 12. {v.rok}, až budou známé náklady celého roku."
    chybi = predpisy.dalsi_k_zauctovani(s, nastaveni, v.rok)
    if chybi is not None:
        mesic = predpisy.MESICE[chybi - 1]
        return f"Nejdřív zaúčtujte předpis záloh za {mesic} {v.rok} na stránce Předpisy."
    if not v.sluzby:
        return f"Za rok {v.rok} nejsou žádné náklady ani zálohy na služby."
    problemy = [x.nazev for x in v.sluzby if x.problem]
    if problemy:
        return "Nejdřív vyřešte služby: " + ", ".join(problemy) + "."
    return None


def uloz_vysledky(
    s: Session,
    profil: Profil,
    rok: int,
    sluzba: str,
    castky: dict[str, int],
    zdroj: str,
    kdo: str,
) -> None:
    """Nahradí výsledky zúčtovatele pro službu a rok."""
    if denik.aktivni(s, klic(rok)) is not None:
        raise ChybaVyuctovani(
            f"Vyúčtování za rok {rok} už je zaúčtované. Změna je možná jen po stornu zápisu."
        )
    x = next((x for x in sluzby(profil) if x.kod == sluzba), None)
    if x is None or x.klic != "zuctovatel":
        raise ChybaVyuctovani("Tato služba se podle zúčtovatele nerozúčtovává.")
    nezname = set(castky) - set(profil.jednotky)
    if nezname:
        raise ChybaVyuctovani(f"Neznámé jednotky: {', '.join(sorted(nezname))}.")
    if any(c < 0 for c in castky.values()):
        raise ChybaVyuctovani("Náklad jednotky nemůže být záporný.")
    for v in s.scalars(
        select(VysledekZuctovatele).where(
            VysledekZuctovatele.rok == rok, VysledekZuctovatele.sluzba == sluzba
        )
    ):
        s.delete(v)
    s.flush()
    for j, c in castky.items():
        s.add(
            VysledekZuctovatele(
                rok=rok, sluzba=sluzba, jednotka=j, castka=c, zdroj=zdroj[:200], upravil=kdo
            )
        )


def zauctuj(
    s: Session,
    profil: Profil,
    nastaveni: predpisy.Nastaveni,
    rok: int,
    *,
    zauctoval: str,
    dnes: date | None = None,
) -> Zapis:
    dnes = dnes or date.today()
    v = spocitej(s, profil, nastaveni, rok, dnes)
    if v.zapis is not None:
        return v.zapis
    duvod = proc_nejde(s, nastaveni, v, dnes)
    if duvod:
        raise ChybaVyuctovani(duvod)
    vstupy = {
        "zalohy": [
            {"jednotka": j.jednotka, "sluzba": kod, "castka": na_text(c)}
            for j in v.jednotky
            for kod, c in j.zalohy.items()
        ],
        "naklady": [{"sluzba": x.kod, "castka": na_text(x.naklady)} for x in v.sluzby],
        "vysledky": [{"jednotka": j.jednotka, "rozdil": na_text(j.rozdil)} for j in v.jednotky],
    }
    try:
        return denik.zauctuj(
            s,
            profil,
            katalog.nacti()[OPERACE],
            vstupy,
            datum=date(rok, 12, 31),
            popis=f"Vyúčtování služeb {rok}",
            doklad=f"VY SL {rok}",
            zauctoval=zauctoval,
            idempotencni_klic=klic(rok),
        )
    except denik.ChybaUctovani as e:
        raise ChybaVyuctovani(str(e)) from e
