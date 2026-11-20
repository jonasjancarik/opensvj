# Příručka účetnictví SVJ

Příručka vysvětluje, jak se v SVJ účtuje a podle čeho. Je pro člena výboru, který chce
rozumět číslům od správce, pro účetní, která aplikaci nastavuje, i pro každého, kdo do
aplikace přispívá kódem. Co přesně aplikace dělá, popisuje [specifikace](../spec/README.md);
jednotlivé předkontace jsou strojově čitelné v [katalogu](../../catalogue/README.md).

## Kapitoly

| | Kapitola | Stav |
| --- | --- | --- |
| 1 | [SVJ jako účetní jednotka](01-svj.md) | hotovo |
| 2 | [Příspěvky na správu domu](02-prispevky.md) | hotovo |
| 3 | [Služby a jejich vyúčtování](03-sluzby.md) | hotovo |
| 4 | [Ostatní výnosy: úroky, sankce, pojistné plnění, dotace, pronájem, fotovoltaika](04-vynosy.md) | hotovo |
| 5 | [Úvěry](05-uvery.md) | hotovo |
| 6 | [Majetek a zásoby](06-majetek.md) | hotovo |
| 7 | [Dluhy vlastníků](07-dluhy.md) | hotovo |
| 8 | Doklady a průkaznost | připravuje se |
| 9 | Uzávěrka a účetní závěrka | připravuje se |
| 10 | Daně | připravuje se |
| 11 | Odměny členů orgánů | připravuje se |

## Jak jsou kapitoly napsané

Každá kapitola začíná krátkým shrnutím. Pak následují pravidla, u každého s odkazem na
předpis, volby, o kterých rozhoduje SVJ, popis toho, co z toho umí aplikace, a příklad.
Příklady používají vymyšlené SVJ Ukázková 12 ze složky `profiles/`.

U každého tvrzení je vidět, odkud pochází:

- **Zákon** nebo **vyhláška**: pravidlo stojí přímo v předpisu a odkaz vede na konkrétní
  paragraf. Platí pro každé SVJ.
- **Výklad**: předpis to výslovně neříká, ale vyplývá to z literatury nebo stanoviska
  úřadu. Uvádíme autora a stranu. Účetní může mít odůvodněně jiný názor.
- **Praxe**: obvyklý postup, který žádný předpis ani výklad nevyžaduje.

Kde se výklad a běžná praxe rozcházejí, kapitola to řekne a nechá rozhodnutí na SVJ
a jeho účetní.

## Zdroje

Předpisy jsou citované v aktuálním znění, ověřeném na [Zákonech pro lidi](https://www.zakonyprolidi.cz).
Ověřeno 20. 11. 2026.

| Zkratka | Předpis |
| --- | --- |
| OZ | [zákon č. 89/2012 Sb., občanský zákoník](https://www.zakonyprolidi.cz/cs/2012-89), § 1158–1222 o bytovém spoluvlastnictví |
| NV 366/2013 | [nařízení vlády č. 366/2013 Sb.](https://www.zakonyprolidi.cz/cs/2013-366), o úpravě některých záležitostí souvisejících s bytovým spoluvlastnictvím |
| zákon 67/2013 | [zákon č. 67/2013 Sb.](https://www.zakonyprolidi.cz/cs/2013-67), o službách spojených s užíváním bytů |
| ZoÚ | [zákon č. 563/1991 Sb., o účetnictví](https://www.zakonyprolidi.cz/cs/1991-563) |
| ZDP | [zákon č. 586/1992 Sb., o daních z příjmů](https://www.zakonyprolidi.cz/cs/1992-586) |
| vyhláška 504 | [vyhláška č. 504/2002 Sb.](https://www.zakonyprolidi.cz/cs/2002-504) pro nevýdělečné účetní jednotky, mezi které patří SVJ (§ 1 odst. 1 písm. g)) |
| ČÚS 4xx | České účetní standardy pro účetní jednotky podle vyhlášky 504 |

Nejpodrobnější výklad účetnictví SVJ je kniha Martin Durec, *Účetnictví společenství
vlastníků jednotek*, 3. vydání, Grada 2026. Příručka se jí řídí při výběru témat a odkazuje
na ni u výkladů („Durec s. 40“). Text příručky je ale psaný vlastními slovy, příklady jsou
vlastní a pravidla jsou ověřená v předpisech. Kdo potřebuje víc, má sáhnout po knize.
