import re
from fractions import Fraction

import pytest

from svj.domena import katalog, profil
from svj.domena.penize import halire, kc, na_text
from svj.domena.rozdeleni import rozdel, zkontroluj_podily


class TestPenize:
    def test_prevod(self):
        assert halire("12345.00") == 1_234_500
        assert halire("12.40") == 1240
        assert halire("-99") == -9900
        assert halire("0.5") == 50
        assert halire(12) == 1200
        assert na_text(-1240) == "-12.40"
        assert kc(123456789) == "1 234 567,89 Kč"

    @pytest.mark.parametrize("spatne", ["1,50", "1.505", "abc", "", "1e3"])
    def test_odmitne_neplatne(self, spatne):
        with pytest.raises(ValueError):
            halire(spatne)

    def test_odmitne_float(self):
        with pytest.raises(TypeError):
            halire(0.1)  # type: ignore[arg-type]


class TestRozdeleni:
    def test_tretiny_na_koruny(self):
        # Příklad ze specifikace: 100 Kč na tři stejné podíly.
        third = Fraction(1, 3)
        vysledek = rozdel(10_000, {"A": third, "B": third, "C": third}, krok=100)
        assert vysledek == {"A": 3_400, "B": 3_300, "C": 3_300}

    def test_soucet_vzdy_sedi(self):
        # Různé jmenovatele, jak se v katastru u jednoho domu běžně střídají.
        podily = {
            "1": Fraction(543, 8600),
            "2": Fraction(1201, 8600),
            "3": Fraction(359, 4300),
            "4": Fraction(907, 17200),
            "5": Fraction(225, 2150),
        }
        for celkem in (3_870_200, 100, 99_900, 1):
            v = rozdel(celkem, podily)
            assert sum(v.values()) == celkem

    def test_zaporna_castka(self):
        assert rozdel(-10_000, {"A": 1, "B": 1, "C": 1}, krok=100) == {
            "A": -3_400,
            "B": -3_300,
            "C": -3_300,
        }

    def test_nedelitelna_castka(self):
        with pytest.raises(ValueError):
            rozdel(150, {"A": 1}, krok=100)

    def test_podily_musi_dat_jedna(self):
        zkontroluj_podily({"A": Fraction(1, 2), "B": Fraction(1, 2)})
        with pytest.raises(ValueError):
            zkontroluj_podily({"A": Fraction(1, 2), "B": Fraction(1, 3)})


class TestKatalog:
    def test_vsechny_priklady_projdou(self):
        operace = katalog.nacti()
        assert len(operace) >= 20
        assert katalog.zkontroluj(operace) == []

    def test_role_existuji_v_profilu(self):
        p = profil.nacti("ukazka")
        for op in katalog.nacti().values():
            for priklad in op.priklady:
                for r in katalog.sestav(op, priklad.get("vstupy") or {}, priklad.get("krok")):
                    assert p.ucet(r.role), (op.id, r.role)

    def test_vstupy_jsou_pojmenovane(self):
        """Každá proměnná v šabloně zápisu je mezi vstupy a vstupy mají platná jména
        (popis s čárkou bez uvozovek by YAML rozdělil na falešné vstupy)."""
        jmeno = re.compile(r"^[a-z_][a-z0-9_]*$")
        for op in katalog.nacti().values():
            vstupy = op.data.get("vstupy") or {}
            assert all(jmeno.match(k) for k in vstupy), (op.id, list(vstupy))
            for z in op.zapisy:
                if z.get("pro_kazde"):
                    continue
                sablony = [z["md"], z["d"], z["castka"], *(z.get("dimenze") or {}).values()]
                for promenna in re.findall(r"\{([a-z_0-9]+)\}", " ".join(map(str, sablony))):
                    assert promenna in vstupy, (op.id, promenna)

    def test_zaporna_castka_prohodi_strany(self):
        op = katalog.nacti()["uhrada-predpisu"]
        radky = katalog.sestav(op, {"ucet": "provozni", "jednotka": "1001/1", "castka": "-10.00"})
        assert [r.klic() for r in radky] == [
            ("md", "pohledavky_vlastnici", 1000),
            ("d", "banka.provozni", 1000),
        ]

    def test_chybejici_vstup(self):
        op = katalog.nacti()["uhrada-predpisu"]
        with pytest.raises(katalog.ChybaKatalogu, match="jednotka"):
            katalog.sestav(op, {"ucet": "provozni", "castka": "1.00"})

    def test_profil_sluzby(self):
        p = profil.nacti("ukazka")
        assert p.ucet("naklady_sluzeb.TEPLO") == "315006"
        assert p.ucet("zalohy_sluzby.VYTAH") == "324014"
        assert p.ucet("zalohy_dodavatelum.VODA") == "314200"
        assert p.ucet("zalohy_dodavatelum.ODPAD") == "314999"
        with pytest.raises(profil.NeznamaRole):
            p.ucet("naklady_sluzeb.NEEXISTUJE")

    def test_zalohy_na_spravu_nejsou_sluzby(self):
        # Pojištění, správce, revize a drobné opravy nejsou služby (zákon 67/2013 § 2 odst. 1).
        p = profil.nacti("ukazka")
        assert p.ucet("zalohy_sprava.POJISTENI") == "324009"
        assert p.ucet("naklady_spravy.SPRAVA") == "315010"
        for kod in ("POJISTENI", "SPRAVA", "OSTATNI", "DROBNE_OPRAVY"):
            assert kod not in p.sluzby
            with pytest.raises(profil.NeznamaRole, match="službu"):
                p.ucet(f"zalohy_sluzby.{kod}")
        assert p.role_uctu()["324009"] == "zalohy_sprava.POJISTENI"
        assert p.role_uctu()["324006"] == "zalohy_sluzby.TEPLO"
