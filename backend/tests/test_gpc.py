from datetime import date

import pytest

from svj.domena import gpc
from tests.gpc_pomoc import pohyb, vypis

UCET = "2804357004"


def _vzor(**kw):
    d = date(2026, 1, 15)
    return vypis(
        UCET,
        1,
        od=date(2025, 12, 31),
        datum=date(2026, 1, 31),
        stary=29_235_950,
        pohyby=[
            pohyb(
                UCET,
                1_038_000,
                doklad="111",
                protiucet="19-123457",
                banka="0800",
                vs="5",
                nazev="Novákovi",
                datum=d,
                zprava="záloha leden 1001/5",
            ),
            pohyb(
                UCET,
                -484_000,
                doklad="112",
                protiucet="999563",
                banka="5500",
                vs="2213243",
                ks="308",
                nazev="Úklid Šťastný",
                datum=d,
            ),
            pohyb(UCET, -5_000, doklad="113", nazev="Poplatek za vedení", datum=d),
        ],
        **kw,
    )


def test_precte_hlavicku_a_pohyby():
    [v] = gpc.cti(_vzor())
    assert (v.ucet, v.cislo, v.datum) == (UCET, 1, date(2026, 1, 31))
    assert (v.stary_zustatek, v.novy_zustatek) == (29_235_950, 29_784_950)
    assert (v.obraty_debet, v.obraty_kredit) == (489_000, 1_038_000)
    prijem, uklid, poplatek = v.pohyby
    assert prijem.castka == 1_038_000 and prijem.protiucet == "19-123457"
    assert (prijem.kod_banky, prijem.vs, prijem.zprava) == ("0800", "5", ["záloha leden 1001/5"])
    assert (uklid.castka, uklid.ks, uklid.nazev) == (-484_000, "308", "Úklid Šťastný")
    assert poplatek.protiucet is None and poplatek.kod_banky is None
    assert gpc.datum_pohybu(v, prijem) == date(2026, 1, 15)


def test_vnitrni_poradi_cislic():
    # Příklad z popisu RB: 13825001 je ve vnitřním tvaru 1002001385000000.
    assert gpc.citelne_cislo(gpc.z_vnitrniho("1002001385000000")) == "13825001"
    [v] = gpc.cti(_vzor(vnitrni=False))
    assert not v.vnitrni_format
    data = vypis(
        UCET,
        2,
        od=date(2026, 1, 31),
        datum=date(2026, 2, 28),
        stary=0,
        vnitrni=True,
        pohyby=[
            pohyb(
                UCET,
                100,
                doklad="1",
                protiucet="19-123457",
                banka="0800",
                datum=date(2026, 2, 1),
                vnitrni=True,
            )
        ],
    )
    [v] = gpc.cti(data, znama_cisla={UCET})
    assert v.vnitrni_format and v.ucet == UCET
    assert v.pohyby[0].protiucet == "19-123457"


def test_storno():
    d = date(2026, 3, 2)
    data = vypis(
        UCET,
        3,
        od=d,
        datum=d,
        stary=10_000,
        pohyby=[
            pohyb(UCET, -2_000, doklad="1", datum=d),
            pohyb(UCET, 2_000, doklad="2", datum=d, kod="4"),
        ],
    )
    [v] = gpc.cti(data)
    assert [p.castka for p in v.pohyby] == [-2_000, 2_000]
    assert v.pohyby[1].storno and v.obraty_debet == 0 and v.novy_zustatek == 10_000


def test_nesouhlasici_obraty():
    data = bytearray(_vzor())
    data[61:74] = b"0000099999999"  # pokažený nový zůstatek
    with pytest.raises(gpc.ChybaVypisu, match="nový zůstatek"):
        gpc.cti(bytes(data))


def test_neznamy_zaznam():
    with pytest.raises(gpc.ChybaVypisu, match="řádek 1"):
        gpc.cti(b"999 nesmysl\r\n")


@pytest.mark.parametrize(
    "vstup,vystup",
    [
        ("000019-2784000277/0100", "19-2784000277"),
        ("2804357004/5500", "2804357004"),
        ("2804357004", "2804357004"),
    ],
)
def test_normalizuj_cislo(vstup, vystup):
    assert gpc.normalizuj_cislo(vstup) == vystup
