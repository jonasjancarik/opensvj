"""Úrok z prodlení podle NV 351/2013 Sb.: repo sazba ČNB k 1. dni pololetí + 8 p. b."""

from datetime import date

from svj.domena import urok


def test_sazba_podle_pololeti_kdy_prodleni_zacalo():
    # 1. 1. 2026 platila repo 3,50 % (od 9. 5. 2025).
    assert urok.sazba(date(2026, 3, 16)) == 1150
    # 1. 7. 2026 platila repo 3,75 % (od 19. 6. 2026); zvýšení 6. 11. 2026 se projeví až od 2027.
    assert urok.sazba(date(2026, 7, 16)) == 1175
    assert urok.sazba(date(2026, 11, 20)) == 1175
    # 1. 1. 2024 platila repo 6,75 % (od 22. 12. 2023).
    assert urok.sazba(date(2024, 1, 5)) == 1475
    # 1. 1. 2014: 0,05 % → zákonných 8,05 %.
    assert urok.sazba(date(2014, 1, 1)) == 805


def test_sazbu_neznamo():
    assert urok.sazba(date(2013, 12, 31)) is None  # starší předpis
    assert urok.sazba(date(2027, 1, 5)) is None  # pololetí po poslední aktualizaci tabulky


def test_vypocet_uroku():
    # 1 000 Kč splatných 15. 3. 2026, k 14. 4. 2026 je to 30 dní prodlení při 11,5 % ročně.
    assert urok.urok(100_000, date(2026, 3, 15), date(2026, 4, 14)) == 945
    assert urok.urok(100_000, date(2026, 3, 15), date(2026, 3, 15)) == 0  # ještě není v prodlení
    assert urok.urok(100_000, date(2013, 12, 1), date(2014, 1, 1)) is None
    # Sazba se nemění ani přes hranici pololetí: celý rok 2026 za 11,5 %.
    assert urok.urok(100_000, date(2025, 12, 31), date(2026, 12, 31)) == 11_500
