from datetime import date

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from svj import denik
from svj.domena import katalog, profil

PROFIL = profil.nacti("ukazka")
OPERACE = katalog.nacti()


def zauctuj(session, op_id, vstupy, **kw):
    return denik.zauctuj(
        session,
        PROFIL,
        OPERACE[op_id],
        vstupy,
        datum=kw.pop("datum", date(2025, 3, 18)),
        popis=kw.pop("popis", "test"),
        doklad=kw.pop("doklad", "BV2025001"),
        zauctoval="test",
        **kw,
    )


def test_zauctovani_a_zustatky(session):
    zauctuj(
        session, "uhrada-predpisu", {"ucet": "provozni", "jednotka": "1001/8", "castka": "2400.00"}
    )
    zauctuj(
        session, "cerpani-fo", {"protistrana": "vytahy", "castka": "120000.00", "rozhodnuti": "x"}
    )
    session.commit()
    z = denik.zustatky(session, 2025)
    assert z["221100"] == 240000
    assert z["311100"] == -240000
    assert z["955100"] == 12000000
    assert z["321100"] == -12000000
    assert sum(z.values()) == 0


def test_poradova_cisla_bez_mezer(session):
    a = zauctuj(session, "poplatek-banky", {"ucet": "provozni", "castka": "1.00"})
    b = zauctuj(session, "poplatek-banky", {"ucet": "provozni", "castka": "2.00"})
    session.commit()
    assert (a.poradove_cislo, b.poradove_cislo) == (1, 2)


def test_idempotence(session):
    vstupy = {"ucet": "provozni", "jednotka": "1001/1", "castka": "100.00"}
    a = zauctuj(session, "uhrada-predpisu", vstupy, idempotencni_klic="banka:abc")
    b = zauctuj(session, "uhrada-predpisu", vstupy, idempotencni_klic="banka:abc")
    session.commit()
    assert a.id == b.id
    assert session.scalar(text("select count(*) from zapis")) == 1


def test_operace_k_overeni_se_v_produkci_neuctuje(session):
    with pytest.raises(denik.ChybaUctovani, match="potvrzení"):
        zauctuj(session, "prijem-nesparovany", {"ucet": "provozni", "castka": "1.00"})
    zauctuj(session, "prijem-nesparovany", {"ucet": "provozni", "castka": "1.00"}, produkcni=False)


def test_uzavrene_obdobi(session):
    with pytest.raises(denik.ChybaUctovani, match="2024"):
        zauctuj(
            session,
            "poplatek-banky",
            {"ucet": "provozni", "castka": "1.00"},
            datum=date(2024, 5, 1),
        )


def test_databaze_odmitne_nevyrovnany_zapis(session):
    session.execute(
        text(
            "insert into zapis (rok, poradove_cislo, datum, doklad, operace, popis, zauctoval) "
            "values (2025, 99, '2025-01-01', 'X', 'rucne', 'nevyrovnaný', 'test')"
        )
    )
    session.execute(
        text(
            "insert into radek_zapisu (zapis_id, strana, role, ucet, castka) "
            "select id, 'md', 'x', '221100', 100 from zapis where poradove_cislo = 99"
        )
    )
    with pytest.raises(DBAPIError, match="není vyrovnaný"):
        session.commit()


def test_databaze_zakaze_zmenu_zapisu(session):
    zauctuj(session, "poplatek-banky", {"ucet": "provozni", "castka": "1.00"})
    session.commit()
    with pytest.raises(DBAPIError, match="storno"):
        session.execute(text("update radek_zapisu set castka = 999"))
    session.rollback()
    with pytest.raises(DBAPIError, match="storno"):
        session.execute(text("delete from zapis"))
