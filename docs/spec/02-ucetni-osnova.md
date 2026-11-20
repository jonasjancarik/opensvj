# Účtová osnova a výkazy

## Co říká vyhláška 504/2002 Sb.

- Směrná účtová osnova je v příloze č. 3 a je členěná na třídy a skupiny. Při účetnictví
  ve zjednodušeném rozsahu smí účtový rozvrh obsahovat **jen účtové skupiny**, musí ale
  vycházet z jejich označení a uspořádání (§ 31 odst. 3). Analytické účty si účetní
  jednotka vytváří podle potřeb závěrky a předpisů (§ 31 odst. 4).
- Mikro a malá účetní jednotka bez povinného auditu smí sestavit rozvahu a výkaz zisku
  a ztráty **ve zkráceném rozsahu**: jen položky označené velkými písmeny a římskými
  číslicemi z příloh č. 1 a 2 (§ 3a). Vykazuje se v celých tisících Kč a aktiva se musí
  rovnat pasivům (§ 4).

Ověřeno v aktuálním znění vyhlášky (verze 10, účinná od 1. 1. 2024).

### Skupiny, které SVJ obvykle používá

| Třída | Skupiny |
| --- | --- |
| 0 Dlouhodobý majetek | 02 hmotný majetek, 04 nedokončený majetek, 08 oprávky (jen SVJ, které majetek vlastní) |
| 1 Zásoby | 11 materiál |
| 2 Finanční účty | 21 pokladna, 22 účty v bankách, 26 převody mezi finančními účty |
| 3 Zúčtovací vztahy | 31 pohledávky, 32 závazky, 33 zúčtování s institucemi, 34 daně a dotace, 37 jiné pohledávky a závazky, 38 přechodné účty aktiv a pasiv, 39 vnitřní zúčtování a opravné položky |
| 5 Náklady | 50 spotřebované nákupy, 51 služby, 52 osobní náklady, 53 daně a poplatky, 54 ostatní náklady, 55 odpisy a opravné položky, 59 daň z příjmů |
| 6 Výnosy | 60 tržby za vlastní výkony, 64 ostatní výnosy, 68 přijaté příspěvky, 69 provozní dotace |
| 9 Vlastní zdroje a závěrkové účty | 90 vlastní jmění, 93 výsledek hospodaření, 95 dlouhodobé závazky (fond oprav, úvěry), 96 závěrkové účty |

## Role účtů

Kód aplikace nikdy nepracuje s číslem účtu napevno. Pracuje s **rolí** a profil SVJ určí,
který účet roli odpovídá. Díky tomu jde podporovat jiný účtový rozvrh, jiného správce
i export do jeho programu.

Role s hvězdičkou (`zalohy_sluzby.*`) platí pro všechny služby nebo položky správy; účet
se složí ze syntetického účtu a analytiky služby z profilu. Konkrétní role
(`zalohy_dodavatelum.VODA`) má přednost před hvězdičkou.

Účty ve třetím sloupci jsou z ukázkového profilu (`profiles/ukazka.yaml`). Jiné SVJ může
mít jiné analytiky nebo jiný účet ze stejné skupiny.

| Role | Význam | Ukázkový profil | Obvyklá alternativa |
| --- | --- | --- | --- |
| `banka.<účel>` | běžné účty (`provozni`, `fond_oprav`) | 221100, 221200 | |
| `penize_na_ceste` | převody mezi vlastními účty | 261100 | |
| `pohledavky_vlastnici` | předpisy záloh a jejich úhrady | 311100 | 315 |
| `pohledavky_vyuctovani` | nedoplatky a přeplatky z vyúčtování minulého roku | 311200 | 315 s analytikou |
| `pohledavky_vyuctovani_minule` | nevyrovnané výsledky starších vyúčtování | 311300 | |
| `zalohy_dodavatelum.<služba>` | zálohy placené dodavatelům energií a vody | 314100–314999 | |
| `naklady_sluzeb.<služba>` | sběrný účet skutečných nákladů služby pro vyúčtování | 315 + analytika | 5xx s analytikou služby |
| `naklady_spravy.<položka>` | sběrný účet nákladů na správu pro vyúčtování záloh na správu | 315 + analytika | 5xx s analytikou položky |
| `dodavatele` | přijaté faktury | 321100 | |
| `zalohy_sluzby.<služba>` | přijaté zálohy na služby | 324 + analytika | |
| `zalohy_sprava.<položka>` | krátkodobé zálohy na správu domu; vyúčtují se zvlášť od služeb | 324 + analytika | |
| `nevyjasnene_prijmy`, `nevyjasnene_vydaje` | nespárované a nedoložené pohyby | 379900, 378900 | **ověřit** s účetní |
| `naklady_pristich_obdobi` | časové rozlišení (pojištění placené dopředu) | 381100 | |
| `dohadne_pasivni` | nevyfakturované náklady k rozvahovému dni | 389100 | |
| `vnitrni_zuctovani` | technický účet pro vyúčtování | 395100 | |
| `naklady.opravy` | drobné opravy | 511100 | |
| `naklady.sprava`, `naklady.pojisteni`, `naklady.ostatni` | správní náklady | 518100, 518200, 518300 | |
| `naklady.banka`, `naklady.dan_srazkova` | bankovní poplatky, srážková daň z úroků (jen při hrubém účtování úroků) | 549100, 591100 | |
| `naklady.prevod_do_fo` | převod výnosů do fondu oprav | 549300 | |
| `vynosy.predpis`, `vynosy.pausal`, `vynosy.pacht` | předepsané výnosy, paušální poplatky, pacht účtovaný jako výnos SVJ | 602000, 602200, 602100 | |
| `vynosy.uroky`, `vynosy.pojistne_plneni` | bankovní úroky po srážce daně, pojistné plnění | 644100, 649200 | |
| `vynosy.prevod_do_vyuctovani` | protipoložka k převodu správních nákladů do vyúčtování | 649100 | |
| `zalohy_dlouhodobe` | fond oprav | 955100 | |
| `zalohy_dlouhodobe_mimoradne` | mimořádné zálohy na konkrétní akci | 955200 | |
| `pocatecni_rozvazny` | otevření roku počátečními stavy | 961000 | |
| `konecny_rozvazny` | uzavření rozvahových účtů k 31. 12. | 962000 | |
| `ucet_vysledku` | uzavření nákladů a výnosů k 31. 12. | 963000 | |
| `vysledek_ve_schvalovani` | výsledek minulého roku po otevření dalšího roku | 931000 | |

Role pro operace, které malé SVJ potřebuje jen někdy (majetek, úvěr, dotace, odměny
výboru, sankce a pochybné pohledávky). Účty jsou z ukázkového profilu podle vzorového
účtového rozvrhu pro SVJ a před ostrým použitím je musí potvrdit účetní:

| Role | Význam | Ukázkový profil |
| --- | --- | --- |
| `majetek`, `majetek_porizovani`, `opravky_majetku` | dlouhodobý hmotný majetek, jeho pořízení a oprávky | 022100, 042100, 082100 |
| `zdroj_majetku` | zdroj krytí majetku placeného ze záloh vlastníků | 901100 |
| `naklady.odpisy` | účetní odpisy | 551100 |
| `zasoby` | nespotřebované zásoby k 31. 12. | 112100 |
| `pokladna`, `naklady.spotreba` | hotovostní pokladna a drobný materiál | 211100, 501100 |
| `pohledavky_vlastnici_sankce`, `vynosy.urok_z_prodleni` | předepsaný úrok z prodlení | 311400, 641100 |
| `zalohy_dlouhodobe_pochybne` | vyčleněný zdroj krytí pochybných pohledávek ve fondu oprav | 955900 |
| `opravne_polozky`, `naklady.opravne_polozky` | opravná položka k pohledávce | 391100, 559100 |
| `naklady.odpis_pohledavky` | odpis nedobytné pohledávky | 543100 |
| `uvery`, `naklady.uroky_uver` | dlouhodobý úvěr a jeho úroky | 951100, 544100 |
| `pohledavky_uver`, `zalohy_dlouhodobe_uver` | podíly vlastníků na splácení úvěru a zálohy na něj | 378100, 955300 |
| `pohledavky_dotace`, `narok_dotace`, `vynosy.dotace` | nárok na dotaci a její použití | 378200, 346100, 691100 |
| `pohledavky_najemci`, `prijmy_vlastniku` | nájemné ze společných částí a závazek vůči vlastníkům, kterým patří | 378300, 379200 |
| `naklady.odmeny`, `zavazky_odmeny` | odměny členů výboru | 523100, 379100 |
| `naklady.odvody`, `zavazky_pojistne`, `zavazky_dan_odmeny` | pojistné a daň z odměn | 524100, 336100, 342100 |

Analytika podle jednotky a služby je v aplikaci **dimenze řádku**, ne samostatný účet
(viz [doménový model](01-domena.md#analytika)). Účet jako „náklady na teplo“ nebo
pohledávka za jednotku 1001/3 vzniká až při výkazu nebo exportu.

## Dva obvyklé způsoby účtování

SVJ, které vede služby rozvahově, účtuje zhruba takhle:

1. **Předpis** (měsíčně): MD pohledávky za vlastníky / D fond oprav (955), D zálohy na
   služby a na správu (324) a D předepsané výnosy (602).
2. **Faktura za službu** (teplo, voda, odpad, elektřina, výtah, úklid, rozúčtování):
   MD sběrný účet služby (315) / D dodavatelé. Náklad služby jde rovnou na rozvahový účet
   a výsledovkou neprochází.
3. **Správní náklady** (správa, pojištění, ostatní, drobné opravy): MD 5xx / D dodavatelé.
   Na konci roku se převedou do vyúčtování: MD sběrný účet (315) / D 649.
4. **Čerpání fondu oprav**: MD fond oprav (955) / D dodavatelé. Opravy z fondu
   výsledovkou neprocházejí.
5. **Výnosy SVJ** (paušály, pacht, úroky) se převedou do fondu oprav: MD 549 / D 955.
6. **Vyúčtování**: zálohy (324) a náklady (315) se vyrovnají přes vnitřní zúčtování (395)
   a rozdíl po jednotkách jde na pohledávky z vyúčtování (311).

Výsledek hospodaření takového SVJ je nulový. Literatura uvádí i druhou variantu, kdy
všechny náklady procházejí třídou 5 a jejich krytí zálohami třídou 6. Katalog má obě
a profil SVJ volí jednu (`varianty` u operace). Proč literatura doporučuje druhou
variantu a jak se liší zálohové a nezálohové příspěvky, vysvětluje
[příručka](../prirucka/02-prispevky.md).

## Převod na zkrácené výkazy

Řádek výkazu se určuje podle účtové skupiny (první dvě číslice účtu). U skupin, které
mohou být na obou stranách (34, 37, 38), rozhoduje strana zůstatku. Několik syntetických
účtů má jiný řádek, než napovídá skupina. Úplný převod je v `backend/src/svj/domena/vykazy.py`.

### Rozvaha ve zkráceném rozsahu (příloha č. 1)

| Řádek | Účty |
| --- | --- |
| A.I. Dlouhodobý nehmotný majetek | 01, 041 |
| A.II. Dlouhodobý hmotný majetek | 02, 03, 042 |
| A.III. Dlouhodobý finanční majetek | 06, 043 |
| A.IV. Oprávky k dlouhodobému majetku | 07, 08 |
| B.I. Zásoby | 11, 12, 13 |
| B.II. Pohledávky | 31, 314, 315, 34 (MD), 37 (MD), 378, 388, 391 (snižuje) |
| B.III. Krátkodobý finanční majetek | 21, 22, 26 |
| B.IV. Jiná aktiva | 381, 385, 38 (MD) |
| A.I. Jmění | 90, 91 |
| A.II. Výsledek hospodaření | 93 a během roku výsledek běžného roku |
| B.I. Rezervy | 94 |
| B.II. Dlouhodobé závazky | 95 (fond oprav, úvěry) |
| B.III. Krátkodobé závazky | 32, 33, 34 (D), 37 (D), 379, 389 |
| B.IV. Jiná pasiva | 383, 384, 38 (D) |

Skupiny 39 (vnitřní zúčtování) a 96 (závěrkové účty) se nevykazují a k rozvahovému dni
musí mít nulový zůstatek. Dohadné účty pasivní (389) patří mezi krátkodobé závazky
(B.III.22), ne mezi jiná pasiva; dohadné účty aktivní (388) jsou v B.II.18.

**Přeplatky vlastníků** se nezapočítávají proti dluhům ostatních. Pohledávky za vlastníky
se v rozvaze rozpadnou po jednotkách: nedoplatky jdou do pohledávek (B.II), přeplatky do
krátkodobých závazků (B.III).

### Výkaz zisku a ztráty ve zkráceném rozsahu (příloha č. 2)

| Řádek | Účty |
| --- | --- |
| A.I. Spotřebované nákupy a nakupované služby | 50, 51 |
| A.III. Osobní náklady | 52 |
| A.IV. Daně a poplatky | 53 |
| A.V. Ostatní náklady | 54 |
| A.VI. Odpisy, prodaný majetek, tvorba a použití rezerv a opravných položek | 55 |
| A.VII. Poskytnuté příspěvky | 58 |
| A.VIII. Daň z příjmů | 59 |
| B.I. Provozní dotace | 69 |
| B.II. Přijaté příspěvky | 68 |
| B.III. Tržby za vlastní výkony a za zboží | 60 |
| B.IV. Ostatní výnosy | 64 |
| B.V. Tržby z prodeje majetku | 65 |
| C. Výsledek hospodaření před zdaněním | výnosy − náklady |

V příloze č. 2 vyhlášky 504 jsou daně a poplatky pod A.IV a ostatní náklady pod A.V, ne
jako ve vyhlášce 500. Převod proto vždy odkazuje na znění vyhlášky 504.

### Zaokrouhlení na tisíce

Každý řádek se zaokrouhlí na celé tisíce Kč (polovina od nuly). Součet zaokrouhlených
řádků se pak nemusí rovnat zaokrouhlenému celku, ale vyhláška vyžaduje, aby se aktiva
rovnala pasivům. Pravidlo pro dorovnání (na největší položku, nebo zaokrouhlit celek
a dopočítat) musí potvrdit účetní. Aplikace ho musí udělat viditelně a uvést v příloze.
Výkazy aplikace ukazují v tisících i přesně.

## Účty, o kterých musí rozhodnout účetní

1. **Nevyjasněné položky:** 378 (jiné pohledávky) pro nedoložený výdaj a 379 (jiné
   závazky) pro nespárovaný příjem, nebo 395. Skupina 39 se v rozvaze nevykazuje, takže
   nevyjasněná položka na 395 by k rozvahovému dni z výkazů zmizela. Návrh: 378 a 379.
2. **Čerpání fondu oprav:** přímo 955/321, nebo přes náklady (547/321) a stanovení
   příspěvků (311/649, 955/311). Podle stanoviska GFŘ z roku 2023 a literatury jsou
   náklady na správu domu včetně oprav náklady SVJ a patří do výsledovky; přímý zápis
   955/321 je běžná praxe, ale literatura ho odmítá. Rozbor je v příručce, kapitola
   [Příspěvky na správu domu](../prirucka/02-prispevky.md).
3. **Pojistné plnění:** jako výnos na 64x, nebo jako snížení nákladu na pojištění.
   Pojistné plnění z pojistek SVJ za škody na společných částech je příjmem společenství
   (§ 16 odst. 1 písm. f) nařízení vlády 366/2013). Jestli výnos zvýší fond oprav, nebo sníží
   náklad opravy, kterou škoda vyvolala, rozhodne účetní.
4. **Příjmy z nakládání se společnými částmi** (pacht, nájem): podle § 16 odst. 2 písm. a)
   nařízení vlády 366/2013 nejsou příjmem společenství, i když přijdou na jeho účet.
   Záleží na tom, co je předmětem pachtu a jak to SVJ zdaňuje a vykazuje. Pro takové
   příjmy bude potřeba role mimo výnosy SVJ.
