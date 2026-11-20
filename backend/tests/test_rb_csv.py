"""Přehled pohybů Raiffeisenbank (CSV). Data jsou vymyšlená, sloupce podle skutečného exportu."""

from datetime import date

import pytest
from sqlalchemy import select

from svj import banka
from svj.db import BankovniPohyb, BankovniUcet, BankovniVypis
from svj.domena import gpc, rb_csv
from tests.gpc_pomoc import pohyb, vypis
from tests.test_banka import PROFIL

UCET = "5000000001"
HLAVICKA = (
    "Datum provedení;Datum zaúčtování;Číslo účtu;Název účtu;Kategorie transakce;"
    "Číslo protiúčtu;Název protiúčtu;Typ transakce;Zpráva;Poznámka;VS;KS;SS;"
    "Zaúčtovaná částka;Měna účtu;Původní částka;Původní měna;Poplatky;Id transakce;"
    "Vlastní poznámka;Název obchodníka;Město"
)


def radek(datum, cas, protiucet, nazev, castka, id_, vs="", ks="", zprava="", obchodnik=""):
    hodnoty = [
        datum,
        f"{datum} {cas}",
        f"{UCET}/5500",
        "SVJ TEST",
        "Platba",
        protiucet,
        nazev,
        "Příchozí úhrada" if not castka.startswith("-") else "Odchozí úhrada",
        zprava,
        "",
        vs,
        ks,
        "",
        castka,
        "CZK",
        "",
        "",
        "0",
        id_,
        "",
        obchodnik,
        "",
    ]
    return ";".join(f'"{h}"' for h in hodnoty)


def soubor(*radky):
    return ("﻿" + HLAVICKA + "\r\n" + "\r\n".join(radky) + "\r\n").encode("utf-8")


LISTOPAD = soubor(  # od nejnovějších, jako export z banky
    radek(
        "18.11.2026", "13:50", "19-123457/0800", "Novák Jan", "14076", "9800000003", vs="0000000005"
    ),
    radek(
        "16.11.2026",
        "08:33",
        "182-4000505031/0100",
        "",
        "-2989,28",
        "9800000002",
        vs="1234567890",
        zprava="voda záloha",
        obchodnik="Vodárna",
    ),
    radek(
        "02.11.2026",
        "04:16",
        "7720-77628031/0710",
        "",
        "-618",
        "9800000001",
        vs="12345678",
        ks="1148",
        obchodnik="Finanční správa",
    ),
)


def test_precte_prehled():
    assert rb_csv.je_rb_csv(LISTOPAD) and not rb_csv.je_rb_csv(b"074000")
    p = rb_csv.cti(LISTOPAD)
    assert (p.ucet, p.od, p.do) == (UCET, date(2026, 11, 2), date(2026, 11, 18))
    dan, voda, platba = p.pohyby  # od nejstaršího
    assert (dan.castka, dan.protiucet, dan.kod_banky, dan.ks) == (
        -61_800,
        "7720-77628031",
        "0710",
        "1148",
    )
    assert (voda.castka, voda.nazev, voda.zprava) == (
        -298_928,
        "Vodárna",
        ["voda záloha", "Odchozí úhrada"],
    )
    assert (platba.castka, platba.vs, platba.id_banky) == (1_407_600, "5", "9800000003")


def test_chybejici_sloupec():
    with pytest.raises(gpc.ChybaVypisu, match="chybí sloupce"):
        rb_csv.cti("﻿Datum provedení;Něco\r\n".encode())


def _nahraj(session, data, ucel=None):
    return banka.nahraj(session, PROFIL, data, nazev_souboru="pohyby.csv", nahral="x", ucel=ucel)


def test_prekryvajici_prehledy_a_vypis(session):
    [n] = _nahraj(session, LISTOPAD, ucel="provozni").vypisy
    assert (n.druh, n.novych, n.uz_nahranych, n.novy_zustatek) == ("export", 3, 0, None)
    assert _nahraj(session, LISTOPAD).vypisy[0].uz_byl_nahrany

    delsi = soubor(
        radek("19.11.2026", "09:00", "19-123457/0800", "Novák Jan", "100", "9800000004"),
        *LISTOPAD.decode("utf-8-sig").splitlines()[1:],
    )
    [n] = _nahraj(session, delsi).vypisy
    assert (n.novych, n.uz_nahranych) == (1, 3)

    # Pozdější výpis GPC se stejnými čísly transakcí pohyby nezdvojí, jen je potvrdí.
    d = date(2026, 11, 2)
    v = vypis(
        UCET,
        11,
        od=date(2026, 10, 31),
        datum=date(2026, 11, 30),
        stary=0,
        pohyby=[
            pohyb(
                UCET, -61_800, doklad="9800000001", protiucet="7720-77628031", banka="0710", datum=d
            ),
            pohyb(UCET, 5_000, doklad="9800000099", datum=d),
        ],
    )
    [n] = _nahraj(session, v).vypisy
    assert (n.druh, n.novych, n.uz_nahranych) == ("vypis", 1, 1)
    assert len(list(session.scalars(select(BankovniPohyb)))) == 5
    druhy = sorted(session.scalars(select(BankovniVypis.druh)))
    assert druhy == ["export", "export", "vypis"]
    assert session.scalar(select(BankovniUcet.cislo)) == UCET
