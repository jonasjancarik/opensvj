# Doménový model

Model má pět oblastí: **dům a lidé**, **předpisy**, **banka**, **doklady** a
**účetnictví**. Vyúčtování a uzávěrka nad nimi jen počítají a výsledek zapisují zpět jako
zápisy do deníku.

Názvy jsou česky bez diakritiky, aby šly přímo použít v kódu (`Jednotka`,
`SlozkaPredpisu`). Na konci každé oblasti je odstavec **V aplikaci**: co z popsaného
aplikace už dělá a v čem se zatím liší.

## 1. Dům a lidé

### Spolecenstvi

Jedna instalace obsluhuje jedno SVJ. Nese IČ, název, sídlo, statutární orgán, účetní
období (kalendářní rok), rozsah účetnictví (zjednodušený podle § 13a zákona o účetnictví),
kategorii účetní jednotky (mikro) a profil účtové osnovy (viz
[osnova](02-ucetni-osnova.md#role-účtů)).

### Jednotka

- Označení podle katastru (`1001/1`), druh (byt, nebytový prostor) a podlahová plocha.
- Podíl na společných částech jako zlomek. **Součet podílů všech jednotek musí dát
  přesně 1**, jinak předpis nejde spočítat.
- Variabilní symbol pro platby: předpona SVJ, číslo jednotky a pořadí vlastníka.
- Podíl se může změnit (změna prohlášení vlastníka), proto má platnost:
  `PodilJednotky(jednotka, citatel, jmenovatel, plati_od, plati_do, zdroj)`.

### Osoba

Fyzická nebo právnická osoba: jméno, adresa pro doručování, e-mail a účet pro vracení
přeplatků. Osobní údaje jsou oddělené od účetních dat, aby šlo plnit GDPR, třeba smazat
kontakty po uplynutí archivační doby (§ 31 zákona o účetnictví).

### Vlastnictvi

`Vlastnictvi(jednotka, osoby[], podily_osob, plati_od, plati_do, zdroj)`

- Spoluvlastníci a společné jmění manželů jsou jedna položka s více osobami. Vůči SVJ ručí
  společně a nerozdílně a mají jeden hlas, proto předpis a saldo vznikají **na jednotku
  a vlastnické období**, ne na osobu.
- Období vlastnictví jedné jednotky se nesmějí překrývat ani mít mezeru.
- Při změně vlastníka rozhoduje den zápisu do katastru. Kdo platí předpis za měsíc
  převodu, je volba SVJ: dosavadní vlastník, nový vlastník, nebo poměrně podle dnů.
- Dluhy převodce na příspěvcích a zálohách přecházejí na nabyvatele, pokud o nich věděl
  nebo mohl vědět, a převodce za ně ručí (§ 1186 odst. 2 OZ). Přechod je samostatná
  operace s odkazem na potvrzení o dluzích, ne automatika. Aplikace vydá potvrzení
  o dluzích jednotky k datu podle § 1186 odst. 3 OZ.

### OsobyRozhodne

`OsobyRozhodne(jednotka, pocet, plati_od, plati_do, zdroj)` pro klíče podle § 5 zákona
67/2013 Sb. Počítají se osoby, u kterých lze čekat, že budou jednotku užívat déle než
2 měsíce v zúčtovacím období (§ 2 odst. 1 písm. g)). Pro rozúčtování se počet přepočte na
osobo-měsíce; jak zaokrouhlit načaté měsíce, je volba SVJ.

### Meridlo a Odecet

`Meridlo(jednotka nebo dům, druh, vyrobni_cislo, osazeno_od, odstraneno_do)` a
`Odecet(meridlo, datum, stav, zdroj)`. Výměna měřidla jedno uzavře a druhé otevře;
spotřeba v roce je součet obou.

Pro teplo a teplou vodu v první verzi stačí **převzít výsledky zúčtovatele po
jednotkách** (`VysledekZuctovatele(rok, sluzba, jednotka, castka, zdroj)`), ne počítat
rozúčtování podle vyhlášky 269/2015 Sb.

### Rozhodnuti

`Rozhodnuti(organ, datum, bod, text, priloha)`: usnesení shromáždění nebo výboru. Odkazuje
na něj každá složka předpisu, klíč vyúčtování a volba v profilu. Bez odkazu se uloží jako
„bez doloženého rozhodnutí“ a ukáže se mezi upozorněními.

**V aplikaci:** SVJ, jednotky (označení, plocha, podíl) a služby jsou v profilu SVJ
(`profiles/<id>.yaml`); podíl zatím nemá platnost v čase. Počty osob jsou u verze předpisu.
Osoby, vlastnictví, měřidla a rozhodnutí v aplikaci zatím nejsou. Jméno dřívějšího
vlastníka jde zadat jen u počátečních stavů a u faktury za opravu z fondu oprav se píše,
kdo ji schválil. Potvrzení o dluzích aplikace vydá na jednotku.

## 2. Předpisy

### SlozkaPredpisu

| Pole | Význam a příklad |
| --- | --- |
| `kod` | `FOND_OPRAV`, `TEPLO`, `VODA`, `VYTAH`, `UKLID`, `POJISTENI`, `SPRAVA`… |
| `role` | role závazku: `zalohy_dlouhodobe` (fond oprav), `zalohy_sprava.<položka>`, `zalohy_sluzby.<služba>`, případně výnos |
| `klic` | `plocha` (sazba za m²), `osoby` (sazba za osobu), `podil` (částka domu podle podílů), `jednotka` (částka domu rovným dílem), `pevna` (zadaná částka u jednotky) |
| `sazba` | u všech klíčů kromě `pevna` |
| `plati_od`, `zdroj` | od kdy verze platí a odkud je (rozhodnutí) |

Složky jsou ve třech skupinách podle role:

- **fond oprav** (dlouhodobé zálohy, 955),
- **zálohy na správu domu** (pojištění, správce, revize, drobné opravy): vyúčtují se
  ročně jako správa, ne jako služby,
- **zálohy na služby** podle zákona 67/2013 Sb.: vyúčtují se podle tohoto zákona,
  s jeho lhůtami.

Dvě pravidla omezují, kam se náklad smí zařadit:

- **Revize zařízení a součástí domu a odpisy nejsou nákladem na služby** (§ 2 odst. 1
  písm. d) zákona 67/2013). Patří do správy domu (fond oprav nebo zálohy na správu).
- **Náklady vlastní správní činnosti se rozvrhují na každou jednotku stejně** (§ 1180
  odst. 2 OZ, § 17 nařízení vlády 366/2013). Patří sem odměna správce a členů výboru,
  vedení účetnictví, bankovní účty, rozúčtování a vyúčtování služeb včetně odečtů,
  software a právní služby ke správě domu. Položka správy s touto povahou proto musí mít
  klíč `jednotka`.

### Predpis

`Predpis(jednotka, vlastnicke_obdobi, mesic, slozka, castka, splatnost, variabilni_symbol)`

- Měsíční částky se počítají z verze předpisu a údajů jednotek. Výpočet je
  deterministický: stejné vstupy dají stejné haléře.
- Každá složka se u jednotky zaokrouhlí na celé koruny. U klíčů `plocha` a `osoby`
  polovina nahoru; u klíčů `podil` a `jednotka` se částka domu rozdělí metodou největšího
  zbytku, takže součet jednotek přesně sedí na částku domu.
- Změna předpisu je nová verze s pozdějším `plati_od`. Starší měsíce zůstávají podle
  staré verze.
- Každý měsíc je jeden zápis v deníku (doklad `PR <rok>-<měsíc>`) s řádky po jednotkách
  a složkách. Opakované zaúčtování téhož měsíce nic nezdvojí.

### Saldo

Saldo jednotky = předpisy + výsledky vyúčtování + ostatní pohledávky − přiřazené platby.
Počítá se **z deníku** (řádky rolí pohledávek za vlastníky s dimenzí jednotky), ne
zvlášť, aby nevznikla druhá evidence.

Na který dluh se platba započte: dlužník může při platbě určit, na který dluh plní. Když
nic neurčí, započte se podle § 1933 odst. 1 OZ nejdřív na dluh, o jehož splnění už byl
upomenut, jinak na nejméně zajištěný a při stejném zajištění na nejdříve splatný. U jednoho
dluhu se platba započte nejdřív na náklady, pak na úroky z prodlení a pak na jistinu
(§ 1932 OZ).

**V aplikaci:** předpis je v `profiles/<id>-predpisy.yaml` a zaúčtuje se na stránce
Předpisy po měsících. Saldo se počítá z deníku. Na stránce Dlužníci se platby započítávají
na nejdřív splatné dluhy: nejdřív zůstatky z minulých let, pak měsíční zálohy. Určení
dluhu dlužníkem ani pořadí podle upomínek zatím aplikace nezná. Úrok z prodlení
(nařízení vlády 351/2013 Sb.) se počítá jen do přehledu a upomínky; zaúčtuje se, až ho SVJ
skutečně požaduje. Vlastnická období zatím chybí, takže předpis i saldo jsou na jednotku.

## 3. Banka

### BankovniUcet

Číslo účtu, účel (`provozni`, `fond_oprav`) a z něj role `banka.<účel>`, kterou profil
převede na účet ve skupině 22. Účel se bere z nastavení, ne z názvu účtu na výpisu.

### Vypis a BankovniPohyb

- `Vypis(ucet, cislo, obdobi, pocatecni_zustatek, konecny_zustatek, obraty, soubor, hash)`
- `BankovniPohyb(vypis, klic, datum, valuta, castka, protiucet, vs, ks, ss, zprava, nazev)`
- **Pohyb je neměnný.** Opakovaný import nic nezdvojí: klíčem je číslo transakce banky,
  a kde chybí, kombinace účtu, data, částky, protiúčtu, VS a pořadí ve výpisu.
- Výpis musí navazovat na předchozí (počáteční zůstatek = konečný zůstatek minulého
  výpisu) a součet pohybů musí dát obraty a rozdíl zůstatků. Nesoulad zastaví import.
- Formát výpisu je výměnný. Přehled pohybů bez zůstatků slouží k průběžnému zaúčtování,
  navázání zůstatků ověří až výpis.

### Stav pohybu

`nezpracovany → sparovany` (předpis, faktura, převod mezi účty, poplatek, úrok), nebo
`nezpracovany → nevyjasneny`. Nevyjasněný pohyb se zaúčtuje na účet nevyjasněných položek
(role `nevyjasnene_prijmy`, `nevyjasnene_vydaje`), protože každý účetní případ musí být
zaúčtovaný (§ 8 odst. 3 zákona o účetnictví). Z nevyjasněného stavu vede cesta jen přes
rozhodnutí osoby s oprávněním a nový zápis.

### Párování

Pořadí pokusů:

1. VS patří jednotce a částka sedí s otevřenými předpisy,
2. VS patří jednotce a částka nesedí: přiřadit jednotce, přeplatek nechat na saldu,
3. protiúčet je známý účet vlastníka,
4. VS nebo protiúčet patří faktuře dodavatele,
5. převod mezi vlastními účty,
6. fronta k ručnímu přiřazení.

Každý návrh nese důvod a potvrzuje ho člověk. Převod mezi vlastními účty jde přes peníze na
cestě (261), protože odchod a příchod můžou být v různých dnech a na různých výpisech.

**V aplikaci:** hotové pro formát GPC (ABO) a přehled pohybů Raiffeisenbank (CSV). Návrhy:
převod mezi účty SVJ, bankovní poplatek, faktura podle VS nebo účtu dodavatele a částky,
jednotka podle VS nebo částky předpisu a naučené zaúčtování podle dřívější platby ze
stejného protiúčtu nebo se stejným VS. Zaúčtovaná platba jde stornovat a pohyb se vrátí
k zaúčtování. Operace k ověření (nespárovaný příjem) jde zaúčtovat; uzávěrka ji připomene.

## 4. Doklady

Evidence má pět oddělených vrstev:

```
BankovniPohyb ─┐
               ├─> UcetniPripad ──> UcetniDoklad ──> Zapis(y)
Podklad(y) ────┘                        │
                                        └──> Schvaleni / PodpisovyZaznam
```

### UcetniPripad

Co se hospodářsky stalo: operace z katalogu, datum uskutečnění, popis, částka a vazby na
jednotku, dodavatele a službu. Stav: `rozpracovany → pripraveny → zauctovany`, navíc
`zpochybneny` a `opraveny`.

### UcetniDoklad

Nositel náležitostí podle § 11 odst. 1 zákona o účetnictví:

| § 11 odst. 1 | Pole |
| --- | --- |
| a) označení dokladu | řada a číslo (`FP 2026001`), bez mezer v rámci řady a roku |
| b) obsah případu a jeho účastníci | popis, protistrana |
| c) peněžní částka nebo cena a množství | částka, případně množství a jednotková cena |
| d) okamžik vyhotovení | vyhotoven |
| e) okamžik uskutečnění, liší-li se | uskutečněno |
| f) podpisové záznamy odpovědných osob | vazba na podpisové záznamy (za případ a za zaúčtování) |

Doklad se může skládat z více záznamů propojených identifikátorem, třeba faktura
dodavatele, bankovní pohyb a schválení výboru. Úplný je, když jsou náležitosti a) až f)
vyplněné přímo nebo v některém připojeném záznamu.

Řady dokladů: `FP` přijaté faktury, `BV` bankovní výpisy, `ID` interní doklady,
`PR` předpisy, `PS` počáteční stavy, `VY` vyúčtování, `UZ` uzávěrkové operace.

Stavy dokladu: `koncept → uplny → schvaleny → zauctovany`, z kteréhokoli stavu
`zpochybneny` (§ 33a odst. 2) a ze zpochybněného `opraveny` (nový doklad nebo opravný
zápis s odkazem).

### Podklad

Soubor (PDF, obrázek, e-mail, CSV) nebo strukturovaný záznam. Ukládá se obsah, SHA-256,
čas vložení, kdo ho vložil a odkud (e-mail, nahrání, import). Po vložení se nemění; nová
verze je nový podklad. Stav vůči dokladu: `chybi → vyzadan → doplnen`, nebo `nahrazen`
(náhradní vnitřní doklad s prohlášením).

### Schvaleni a PodpisovyZaznam

`PodpisovyZaznam(osoba, role, cas, objekt, hash_verze, zpusob)`, kde `zpusob` je podpis
v aplikaci (přihlášení a auditní záznam), uznávaný elektronický podpis nebo sken
vlastnoručního podpisu. Podpis se váže k hashi konkrétní verze dokladu a podkladů; změna
po podpisu ho zneplatní.

Návrhová pravidla: kdo žádá o proplacení, nemůže žádost sám schválit; nad nastavenou
částku jsou potřeba podpisy dvou členů výboru. Kdo co smí podepisovat, vychází z rolí
v aplikaci a aplikace z nich vytiskne podpisový řád jako vnitřní předpis podle § 33a
odst. 10.

**V aplikaci:** přijatá faktura je jeden záznam s dodavatelem, druhem nákladu, částkou,
DUZP a splatností a zaúčtuje se hned při zadání. Zadání faktury je zároveň schválení.
Bankovní výpis se ukládá jako neměnná kopie se SHA-256. Účetní případy, podklady, stavy
dokladu a podpisové záznamy zatím v aplikaci nejsou; kdo co zaúčtoval, nese každý zápis.

## 5. Účetnictví

### Obdobi

`Obdobi(rok, stav)`: `otevrene → v_uzaverce → uzavrene`. Do uzavřeného období nejde zapsat
nic. Měsíce mají jen informativní kontrolu (výpisy a předpisy), zamyká se celý rok.

### Zapis a RadekZapisu

- `Zapis(rok, poradove_cislo, datum, doklad, operace, popis, opravuje_zapis,
  idempotencni_klic, zauctoval)`
- `RadekZapisu(zapis, strana, role, ucet, castka, jednotka, sluzba, protistrana, popis,
  parovaci_symbol)`
- Součet MD = součet D, kontrola v databázové transakci.
- Pořadové číslo bez mezer v rámci roku.
- Idempotenční klíč (`predpis:2026-03`, `bankovni-pohyb:<id>`) brání dvojímu zaúčtování
  při opakovaném běhu.
- Storno je nový zápis s opačnými stranami a důvodem, `opravuje_zapis` ukazuje na
  původní. Původní zápis se nemaže ani nepřepisuje. Po stornu jde stejnou věc zaúčtovat
  znovu.

### Analytika

Místo stovek analytických účtů nese řádek **dimenze**: jednotku, službu nebo položku
správy a protistranu. Analytické účty ve výkazech a exportech (pohledávka za jednotku,
náklady na teplo) se z dimenzí odvozují. Závazek a jeho úhrady spojuje párovací symbol,
třeba interní číslo faktury.

### Hlavní kniha

Zdrojem pravdy je deník v databázi aplikace. Zůstatky a obraty se z něj počítají dotazem.
Návrh do budoucna: každý zaúčtovaný zápis exportovat i do Beancountu s metadaty (doklad,
jednotka) a uzavřený rok uložit s hashem. Beancount pak poslouží jako nezávislá kontrola
a Fava jako prohlížeč.

### Uzávěrka

Kroky, které aplikace vede a které blokují uzavření roku, dokud nejsou splněné:

1. Výpisy roku jsou nahrané a navazují; zůstatky bankovních účtů souhlasí s výpisy
   k 31. 12.
2. Žádný bankovní pohyb není nezpracovaný. Nevyjasněné jsou rozhodnuté, nebo vědomě
   přenesené s komentářem do přílohy.
3. Doklady roku jsou zaúčtované a podepsané.
4. Předpisy za všech dvanáct měsíců existují.
5. Vyúčtování záloh na správu a služeb je zaúčtované, nebo jsou náklady a zálohy
   převedené tak, aby byl výsledek hospodaření nulový.
6. Časové rozlišení (381, 383, 384, 385) a dohadné položky (388, 389) jsou zaúčtované.
7. Inventura (§ 29–30 zákona o účetnictví): u každého rozvahového účtu zůstatek, jeho
   doložení (výpis, saldokonto, soupis faktur) a podpis inventarizační komise.
8. Uzávěrkové zápisy: náklady a výnosy na účet výsledku, výsledek na 931, zůstatky na 962.
   Další rok se otevře přes 961.

Výstupy: zkrácená rozvaha a výkaz zisku a ztráty v celých tisících Kč (§ 4 odst. 3
vyhlášky 504/2002 Sb.), příloha, zpráva o hospodaření, inventurní soupisy a deník
a hlavní kniha jako PDF a CSV.

**V aplikaci:** deník, storno, idempotence, číslování a uzavřené období jsou hotové
a hlídají je triggery v databázi. Stránka Uzávěrka ověří z dat body 1, 2, 4 a 5 a zůstatky
pomocných účtů. Ostatní body se odškrtávají ručně a odškrtnutí se ukládá s tím, kdo a kdy.
Výkazy, inventurní soupisy, posouzení daně z příjmů a návrh přílohy aplikace sestaví.
Uzávěrkové zápisy, otevření dalšího roku z konečných zůstatků a zpráva o hospodaření
zatím chybí; první rok se otevírá zadáním počátečních stavů.

## 6. Vyúčtování

### Vyúčtování záloh na správu

Náklady roku přiřazené k položce správy (pojištění, správa, revize, drobné opravy) se
rozdělí na jednotky podle klíče položky v profilu, metodou největšího zbytku na haléře.
Porovnají se s předepsanými zálohami jednotky na tutéž položku a rozdíl je nedoplatek
nebo přeplatek jednotky. Výnosy přiřazené k položce (pojistné plnění na opravu, dotace na
úroky) náklady té položky snižují. Nedoplatek je splatný 30. 4. dalšího roku, stejně jako
u služeb (§ 7 zákona 67/2013), pokud stanovy neurčí jinak.

**V aplikaci:** hotové, stránka Vyúčtování a zápis `vyuctovani-spravy`.

### Vyúčtování služeb

`Vyuctovani(rok, stav)` se skládá z `VyuctovaniSluzby(sluzba, naklady, zalohy_predepsane,
zalohy_prijate, klic, rozdeleni[])` a výsledku na jednotku a vlastnické období.

- Náklady služby se berou z deníku (sběrný účet služby, viz
  [osnova](02-ucetni-osnova.md)) a z výsledků zúčtovatele. Rozdíl mezi nimi je chyba,
  ne zaokrouhlení.
- Porovnává se s **přijatými** zálohami (§ 7 odst. 1 zákona 67/2013). Nezaplacené zálohy
  zůstávají v saldu jako dluh.
- Výsledek jednotky se zaokrouhlí na celé koruny. Součet výsledků proto nemusí přesně dát
  náklady a rozdíl se zaúčtuje viditelně (operace `vyuctovani-zaokrouhleni`).
- Lhůty: doručit do 4 měsíců od konce zúčtovacího období (§ 7 odst. 1), vyrovnat do
  4 měsíců od doručení (§ 7 odst. 2), námitky do 30 dnů (§ 8). Aplikace je spočítá z data
  doručení a hlídá.
- Stav: `koncept → zkontrolovane → dorucene → (namitky) → vyrovnane`. Oprava po doručení je
  nová verze vyúčtování, ne přepis.

**V aplikaci:** zatím ne. Předkontace jsou v katalogu (`vyuctovani-sluzeb`,
`preuctovani-mezi-sluzbami`, `vyuctovani-zaokrouhleni`).
