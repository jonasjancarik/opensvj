# Katalog účetních operací

Katalog popisuje, jak se která hospodářská operace SVJ účtuje. Aplikace podle něj
sestavuje zápisy do deníku, ukazuje ho výboru a účetní na stránce Přehled a testy z něj
ověřují, že každý příklad dává přesně očekávané řádky. Předkontace se nepíšou do kódu.

Každý soubor pokrývá jednu oblast:

| Soubor | Co v něm je |
| --- | --- |
| `predpisy.yaml` | měsíční předpis záloh, mimořádná záloha |
| `banka.yaml` | úhrady vlastníků, nespárované platby, převody mezi účty, úhrady faktur, poplatky a úroky |
| `dodavatele.yaml` | faktury za služby a správu, zálohy dodavatelům, časové rozlišení, dohadné položky |
| `fond-oprav.yaml` | opravy z fondu oprav, převod výnosů do fondu, pojistné plnění (i v roce škody a odhadem) |
| `fond-ze-zisku.yaml` | rozdělení výsledku minulého roku, opravy z fondu ze zisku |
| `vyuctovani.yaml` | vyúčtování služeb a správy, přeúčtování mezi službami, zaokrouhlovací rozdíl |
| `pohledavky.yaml` | úrok z prodlení, smluvní pokuta dodavateli, pochybné a nedobytné pohledávky |
| `majetek-pokladna.yaml` | majetek, zásoby, hotovostní pokladna |
| `uvery-dotace.yaml` | úvěr na opravy a jeho splácení, dotace |
| `prijmy-vlastniku.yaml` | nájemné ze společných částí a jiné příjmy vlastníků, které SVJ vybírá |
| `organy.yaml` | odměny členů výboru |
| `uzaverka.yaml` | uzavření a otevření roku, daň z příjmů, storno |

## Jak vypadá operace

```yaml
- id: uhrada-predpisu          # stálý identifikátor, nemění se
  nazev: Úhrada předpisu vlastníkem
  kdy: Příchozí platba spárovaná s jednotkou.
  stav: praxe                  # praxe | navrh | overit
  doklad: BV                   # řada dokladu
  vstupy: {ucet: bankovní účet SVJ, jednotka: označení jednotky, castka: částka platby}
  zapisy:
    - md: "banka.{ucet}"       # role účtu, ne číslo účtu
      d: pohledavky_vlastnici
      castka: "{castka}"
      dimenze: {jednotka: "{jednotka}"}
  pravidla:
    - Datum zápisu je datum zaúčtování na výpisu.
  zdroje:
    - {typ: zakon, odkaz: "OZ § 1932, § 1933"}
  platnost: {od: 2014-01-01}
  priklady:
    - nazev: Platba s VS jednotky
      vstupy: {castka: "10000.00", ucet: provozni, jednotka: "1001/8"}
      ocekavane:
        - [md, banka.provozni, "10000.00", {}]
        - [d, pohledavky_vlastnici, "10000.00", {jednotka: "1001/8"}]
```

- Zápisy pracují s rolemi účtů (`pohledavky_vlastnici`, `zalohy_dlouhodobe`…). Na čísla
  účtů je převádí profil SVJ ve složce `profiles/`, takže stejný katalog funguje pro různá
  SVJ s různou analytikou.
- `{nazev}` se nahradí vstupem. Zápis s `pro_kazde: seznam` se zopakuje pro každou položku
  seznamu. Záporná částka prohodí strany MD a D, nulový řádek se vynechá.
- Operace o více krocích (třeba časové rozlišení k 31. 12. a jeho rozpuštění 1. 1.) mají
  u zápisů `krok` a příklad říká, který krok ověřuje.
- `varianty` popisují jiný postup, který si SVJ může zvolit v profilu.
- Operace, kterou nejde popsat šablonou, má `zpusob` jiný než `sablona` a v `postup`
  popisuje, co dělá kód.

### Stav operace

- `praxe`: takhle SVJ běžně účtují. Neznamená to, že je to jediný správný postup.
- `navrh`: odvozeno ze zákona a z obecné účetní logiky, v praxi zatím neověřeno.
- `overit`: předkontaci by měla potvrdit účetní. Aplikace ji zaúčtuje, ale připomene ji
  v kontrolním seznamu uzávěrky.

Stav říká, jak dobře je postup podložený. O tom, jestli se smí použít, nerozhoduje.

### Zdroje

Každá operace má aspoň jeden zdroj: `zakon` nebo `vyhlaska` s paragrafem, `literatura`
s autorem, vydáním a stranou, nebo `praxe` s popisem, jak se to v SVJ obvykle dělá.
Z literatury se cituje jen číslo strany a vlastní shrnutí, ne opsaný text.

### Částky v příkladech

Částky jsou řetězce s tečkou a dvěma desetinnými místy (`"10000.00"`), aby je YAML
nepřevedl na desetinné číslo. Řádek příkladu je `[strana, role, částka, dimenze]`.
Částky i jednotky v příkladech jsou vymyšlené; jednotky odpovídají ukázkovému SVJ
v `profiles/ukazka.yaml`.

## Kontroly

Test katalogu ověří, že každá operace má známý stav, aspoň jeden zdroj a příklad, že každý
příklad dá vyrovnaný zápis s přesně očekávanými řádky a že se žádné `id` neopakuje.
Ručně se dá spustit takto:

```bash
cd backend && uv run python -c "from svj.domena import katalog; print(katalog.zkontroluj(katalog.nacti()))"
```
