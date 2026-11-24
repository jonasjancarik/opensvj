"""Výdaj bez faktury, rozpuštění dohadné položky, mimořádná záloha podle podílů a pokladna."""

from datetime import date

import pytest
from sqlalchemy import select

from svj import (
    banka,
    denik,
    dluznici,
    interni_doklady,
    mimoradne_zalohy,
    pokladna,
    predpisy,
    rozhodnuti,
    vyuctovani_spravy,
)
from svj.db import RadekZapisu
from tests.test_banka import PROFIL, _nahraj, _pohyby
from tests.test_pocatecni import _otevri_2026

KDO = "vybor@example.test"
NAST = predpisy.nacti(PROFIL)


def _radky(session, zapis_id):
    return sorted(
        (r.strana, r.role, r.castka, r.sluzba or "")
        for r in session.scalars(select(RadekZapisu).where(RadekZapisu.zapis_id == zapis_id))
    )


def test_vydaj_bez_faktury_a_nahradni_doklad(session):
    _nahraj(session)
    p = _pohyby(session)
    par = banka.zauctuj_pohyb(session, PROFIL, p["103"].id, "vydaj-bez-faktury", {}, zauctoval=KDO)
    # V Bance jen platba na nevyjasněné výdaje, náhradní doklad přijde zvlášť.
    assert _radky(session, par.zapis_id) == [
        ("d", "banka.provozni", 5_000, ""),
        ("md", "nevyjasnene_vydaje", 5_000, ""),
    ]
    zadane = {"sluzba": "DROBNE_OPRAVY", "castka": 6_000}
    with pytest.raises(interni_doklady.ChybaDokladu, match="zbývá vyřešit 50,00 Kč"):
        interni_doklady.zauctuj(
            session, PROFIL, "vydaj-bez-faktury", "nahradni_doklad", zadane,
            datum=date(2025, 1, 20), popis="Žárovka", zauctoval=KDO,
        )  # fmt: skip
    z = interni_doklady.zauctuj(
        session, PROFIL, "vydaj-bez-faktury", "nahradni_doklad", zadane | {"castka": 5_000},
        datum=date(2025, 1, 20), popis="Žárovka do sklepa", zauctoval=KDO,
    )  # fmt: skip
    assert _radky(session, z.id) == [
        ("d", "nevyjasnene_vydaje", 5_000, "DROBNE_OPRAVY"),
        ("md", "naklady.opravy", 5_000, "DROBNE_OPRAVY"),
    ]
    session.commit()
    # Náklad patří do vyúčtování správy u drobných oprav.
    v = vyuctovani_spravy.spocitej(session, PROFIL, 2025)
    assert next(x for x in v.polozky if x.kod == "DROBNE_OPRAVY").naklady == 5_000
    assert denik.zustatky(session, 2025).get(PROFIL.ucet("nevyjasnene_vydaje"), 0) == 0


def test_dohadna_polozka_se_rozpusti(session):
    _otevri_2026(session)
    odhad = {"sluzba": "ELEKTRINA", "castka": 300_000}
    interni_doklady.zauctuj(
        session, PROFIL, "dohadna-polozka", "k_rozvahovemu_dni", odhad,
        datum=date(2026, 3, 31), popis="Odhad elektřiny", zauctoval=KDO,
    )  # fmt: skip
    with pytest.raises(interni_doklady.ChybaDokladu, match="3 000,00 Kč odhadů"):
        interni_doklady.zauctuj(
            session, PROFIL, "dohadna-polozka", "po_doruceni_faktury", odhad | {"castka": 300_001},
            datum=date(2026, 4, 10), popis="Faktura přišla", zauctoval=KDO,
        )  # fmt: skip
    z = interni_doklady.zauctuj(
        session, PROFIL, "dohadna-polozka", "po_doruceni_faktury", odhad,
        datum=date(2026, 4, 10), popis="Faktura přišla", zauctoval=KDO,
    )  # fmt: skip
    assert _radky(session, z.id) == [
        ("d", "naklady_sluzeb.ELEKTRINA", 300_000, "ELEKTRINA"),
        ("md", "dohadne_pasivni", 300_000, "ELEKTRINA"),
    ]
    zust = denik.zustatky(session, 2026)
    assert zust.get(PROFIL.ucet("dohadne_pasivni"), 0) == 0


def _shromazdeni(session, datum=date(2026, 3, 10), organ="shromazdeni"):
    return rozhodnuti.pridej(
        session,
        rozhodnuti.UdajeRozhodnuti(organ=organ, datum=datum, nazev="Výměna oken", bod="4"),
        KDO,
    )


def test_mimoradna_zaloha_podle_podilu(session):
    _otevri_2026(session)
    r = _shromazdeni(session)
    casti = mimoradne_zalohy.rozdel_podle_podilu(session, PROFIL, 10_000_001, date(2026, 4, 1))
    assert sum(casti.values()) == 10_000_001
    assert casti["1001/9"] > casti["1001/1"]  # větší podíl, víc platí
    kw = dict(celkem=10_000_001, datum=date(2026, 4, 1), ucel="výměna oken", zauctoval=KDO)
    vybor = _shromazdeni(session, organ="vybor")
    with pytest.raises(mimoradne_zalohy.ChybaZalohy, match="rozhodnutí shromáždění"):
        mimoradne_zalohy.zauctuj(
            session, PROFIL, splatnost=date(2026, 6, 30), rozhodnuti_id=vybor.id, **kw
        )
    with pytest.raises(mimoradne_zalohy.ChybaZalohy, match="Splatnost"):
        mimoradne_zalohy.zauctuj(
            session, PROFIL, splatnost=date(2026, 3, 1), rozhodnuti_id=r.id, **kw
        )
    z = mimoradne_zalohy.zauctuj(
        session, PROFIL, splatnost=date(2026, 6, 30), rozhodnuti_id=r.id, **kw
    )
    session.commit()
    md = [x for x in z.radky if x.strana == "md"]
    assert {x.jednotka: x.castka for x in md} == {j: c for j, c in casti.items() if c}
    assert {x.splatnost for x in md} == {date(2026, 6, 30)}
    assert "Shromáždění 10. 3. 2026, bod 4" in z.popis
    (p,) = mimoradne_zalohy.predepsane(session)
    assert (p.celkem, p.splatnost) == (10_000_001, date(2026, 6, 30))

    # V dlužnících je dluh se splatností od shromáždění, do té doby není po splatnosti.
    def dluh(dnes):
        d = next(
            x for x in dluznici.prehled(session, PROFIL, NAST, 2026, dnes) if x.jednotka == "1001/1"
        )
        return [(x.popis, x.splatnost, x.po_splatnosti(dnes)) for x in d.polozky]

    assert dluh(date(2026, 5, 1)) == [(z.popis, date(2026, 6, 30), False)]
    assert dluh(date(2026, 7, 1))[0][2] is True


def test_pokladna(session):
    _nahraj(session)
    p = _pohyby(session)
    banka.zauctuj_pohyb(session, PROFIL, p["104"].id, "pokladna-vyber", {}, zauctoval=KDO)
    kw = dict(popis="Příjem z účtu", zauctoval=KDO)
    with pytest.raises(pokladna.ChybaPokladny, match="nepřijato jen 2 000,00 Kč"):
        pokladna.zauctuj(
            session, PROFIL, "prijem_z_uctu", castka=200_001, datum=date(2025, 1, 15), **kw
        )
    pokladna.zauctuj(
        session, PROFIL, "prijem_z_uctu", castka=200_000, datum=date(2025, 1, 15), **kw
    )
    pokladna.zauctuj(
        session, PROFIL, "vydaj", castka=150_000, datum=date(2025, 1, 25),
        popis="Kolky", sluzba="OSTATNI", zauctoval=KDO,
    )  # fmt: skip
    # Zpětný výdaj, po kterém by pokladna 25. 1. šla do minusu, neprojde.
    with pytest.raises(pokladna.ChybaPokladny, match="nejméně 500,00 Kč"):
        pokladna.zauctuj(
            session, PROFIL, "vydaj", castka=60_000, datum=date(2025, 1, 20),
            popis="Žárovky", zauctoval=KDO,
        )  # fmt: skip
    pokladna.zauctuj(
        session, PROFIL, "platba_vlastnika", castka=30_000, datum=date(2025, 1, 26),
        popis="Záloha hotově", jednotka="1001/2", zauctoval=KDO,
    )  # fmt: skip
    session.commit()
    k = pokladna.kniha(session, PROFIL, 2025)
    assert [(x.prijem, x.vydaj, x.zustatek) for x in k.polozky] == [
        (200_000, 0, 200_000),
        (0, 150_000, 50_000),
        (30_000, 0, 80_000),
    ]
    assert (k.zustatek, k.na_ceste) == (80_000, 0)
    # Výdaj s položkou správy jde do vyúčtování správy, bez ní mezi nezahrnuté.
    v = vyuctovani_spravy.spocitej(session, PROFIL, 2025)
    assert next(x for x in v.polozky if x.kod == "OSTATNI").naklady == 150_000
    with pytest.raises(pokladna.ChybaPokladny, match="jednotku"):
        pokladna.zauctuj(
            session, PROFIL, "platba_vlastnika", castka=1, datum=date(2025, 1, 26),
            popis="x", jednotka="9/9", zauctoval=KDO,
        )  # fmt: skip
