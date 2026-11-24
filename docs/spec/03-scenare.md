# Testovací scénáře

Testy běží nad vymyšleným SVJ „Ukázková 12“ (`profiles/ukazka.yaml`
a `profiles/ukazka-predpisy.yaml`). Očekávané částky jsou z profilu spočítané ručně, takže
test ověřuje výpočet, ne jen to, že aplikace dává pořád stejné číslo. Kdo profil změní,
musí přepočítat i očekávané částky.

Aplikace se navíc ověřuje nad souhrnnými čísly jednoho skutečného SVJ za celý rok: předpisy,
fond oprav, výsledovka a zkrácené výkazy musí sedět se závěrkou od jeho správce. Tyto
testy a data jsou mimo veřejný repozitář.

## Ukázkové SVJ

| | |
| --- | --- |
| Jednotky | 12 (1001/1 až 1001/12), z toho 1001/11 nebytový prostor |
| Plocha | 860 m² celkem; podíly podle plochy, jmenovatel 8600 |
| Fond oprav | 45 Kč za m² měsíčně |
| Drobné opravy | 1 Kč za m² měsíčně (záloha na správu) |
| Výtah | 120 Kč za osobu měsíčně, 26 osob |
| Ostatní složky | pevné částky, u všech jednotek stejné; 1001/11 má vlastní zálohu na teplo a vodu a nemá teplou vodu |
| Předpis platí | od 1. 3. 2026 |
| Variabilní symbol | 1001 + číslo jednotky (3 číslice) + pořadí vlastníka (2 číslice) |

## Co testy ověřují

### Předpisy

- Předpis jednotky po složkách, třeba 1001/6 celkem 12 740 Kč měsíčně.
- Zaokrouhlení složky na celé koruny polovinou nahoru (fond oprav 1001/10:
  47,50 m² × 45 Kč = 2 137,50 → 2 138 Kč).
- Klíč podle osob platí jen pro výtah; jednotka s jednou osobou platí 120 Kč, se čtyřmi
  480 Kč.
- Vlastní pevné částky jednotky mají přednost před výchozími.
- Klíče `podil` a `jednotka` dělí částku domu metodou největšího zbytku a součet sedí na
  haléř.
- Před datem platnosti předpis neexistuje; neznámá verze a chybné nastavení se odmítnou
  se srozumitelnou chybou.
- Zaúčtování měsíce je jeden zápis s řádky po jednotkách a složkách, opakované
  zaúčtování nic nepřidá a měsíce jdou postupně.

### Banka

- Přečtení hlavičky a pohybů GPC i přehledu pohybů v CSV, vadný a příliš velký soubor se
  odmítne.
- Výpis musí navazovat zůstatkem na předchozí a součet pohybů musí sedět na obraty.
- Opakované nahrání téhož výpisu a překrývající se přehledy nic nezdvojí; nahraný pohyb
  nejde změnit.
- Neznámý bankovní účet: aplikace se zeptá na účel.
- Návrhy zaúčtování podle VS, částky předpisu, faktury a dřívějších plateb; jednotka
  podle VS ve všech podporovaných tvarech.
- Převod mezi účty zůstane na penězích na cestě, dokud nepřijde výpis druhého účtu.
- Storno platby vrátí pohyb k zaúčtování.

### Deník a storno

- Databáze odmítne nevyrovnaný zápis, změnu zaúčtovaného zápisu a zápis do uzavřeného
  období.
- Pořadová čísla jsou bez mezer, idempotenční klíč brání dvojímu zaúčtování.
- Storno jde jen jednou a s důvodem; po stornu jde předpis, platbu, počáteční stavy
  i fakturu zaúčtovat znovu. Stejnou fakturu jde zadat podruhé až po stornu první.
- Operace se stavem `overit` jde zaúčtovat; uzávěrka ji připomene k posouzení
  a stornované zápisy nepočítá.

### Počáteční stavy, dlužníci, vyúčtování

- Počáteční stavy: zůstatky musí být vyrovnané a rozpis pohledávek sedět na zůstatky
  účtů; dluhy dřívějších vlastníků se současnému vlastníkovi nezapočítají.
- Saldo jednotky = počáteční stav + předpisy − platby.
- Dlužníci: platby jdou na nejstarší dluhy, nejdřív zůstatky z minulých let; úrok
  z prodlení podle repo sazby ČNB k prvnímu dni pololetí, kdy prodlení začalo.
- Vyúčtování správy: klíč podle podílu i rovným dílem, výnosy přiřazené k položce snižují
  její náklady, zaúčtovat jde až se všemi předpisy roku.
- Převod jednotky: dluhy splatné před převodem a předpis za měsíc převodu podle profilu
  se navrhnou převodci; po přesunu je saldo současného vlastníka bez nich a přesun se
  nepočítá jako platba. Převod 15. dne v měsíci: vyúčtování správy i služeb po
  vlastnických obdobích podle obou voleb měsíce převodu, součet období přesně sedí na
  jednotku, výsledek prodávajícího je mezi dřívějšími vlastníky; potvrzení o dluzích k datu
  převodu bere jen zápisy do toho dne; část vyúčtování jde prodávajícímu a jeho doručení
  nespouští lhůty jednotky.

### Výdaje bez faktury, odhady, mimořádná záloha a pokladna

- Výdaj bez faktury: platba z Banky jde na nevyjasněné výdaje, náhradní doklad vyšší než
  zbývající částka neprojde a zaúčtovaný náhradní doklad dá náklad do vyúčtování správy
  u vybrané položky.
- Dohadná položka se po doručení faktury rozpustí proti nákladu služby, nejvýš do výše
  odhadu.
- Mimořádná záloha se rozdělí podle podílů přesně na haléře, rozhodnutí výboru ani
  splatnost před dnem předpisu neprojdou a v dlužnících je dluh po splatnosti až po dni
  určeném shromážděním.
- Pokladna: příjem nejvýš do částky vybrané z účtu, výdaj, po kterém by pokladna v některý
  pozdější den šla do minusu, neprojde, pokladní kniha má průběžný zůstatek a výdaj
  s položkou správy je ve vyúčtování správy.

### Úvěr

Příklad zateplení z příručky (kapitola 5):

- Jistina 1 032 000 Kč na 120 splátek: na 1/8 600 podílu připadne 120 Kč, jednotka 1001/6
  splatí 74 880 Kč po 624 Kč měsíčně, dům 8 600 Kč měsíčně. Rozhodnutí výboru a první
  splátka v už zaúčtovaném měsíci neprojdou.
- Splátka je v předpisu od zvoleného měsíce, oznámení o zálohách ji ukáže jako změnu
  a zbytek podílu jednotky k datu bere jen zaúčtované splátky.
- Jednotka s malým podílem splácí zaokrouhleně nahoru a poslední splátka je zbytek.
- Předpis podílů nejde stornovat, když na něj navazují splátky.
- Faktura z úvěru se čerpá ze záloh na úvěr, úhrada víc, než kolik z faktury zbývá,
  neprojde, splátka bez peněz na cestě neprojde, úroky jde pokrýt až k 31. 12. a jen
  jednou. Vyúčtování správy pak úroky mezi nezahrnutými nemá a ukáže, co platil fond
  oprav a co zálohy na úvěr.

### Majetek

Příklad se sekačkou z příručky (kapitola 6):

- Faktury 36 000 a 2 400 Kč na pořizování; zařadit víc, než je nezařazeno, nejde. Zařazení
  1. 6. 2026 z fondu oprav: 022/042 a 955/901.
- Odpisový plán na 6 let po měsících: 3 200 Kč za rok 2026, pak 6 400 Kč, v roce 2032
  zbytek 3 200 Kč; kumulativní zaokrouhlení dorovná haléře.
- Odpisy jdou zaúčtovat až 31. 12. a jen jednou; výsledek je nulový, ve vyúčtování správy
  odpis není a pořízení je mezi platbami z fondu oprav. Zařazení pak nejde stornovat.
- Uzávěrka: evidence sedí na účty, inventurní soupis má kartu u majetku i oprávek.
- Vyřazení doodepíše zůstatkovou cenu a vynuluje majetek, oprávky i 901.
- Software placený ze správy: odpis je nákladem položky Správa a vyúčtování správy čeká,
  dokud odpis není zaúčtovaný.
- Převzatý majetek: zbytek ceny ve zbývajících měsících, bez počátečních stavů uzávěrka
  hlásí nesoulad, kartu bez odpisů jde odebrat. Pozemek se neodepisuje a vyřadit nejde.

### Vlastníci, měřidla a rozhodnutí

- Období vlastnictví jedné jednotky na sebe navazují a nepřekrývají se.
- Odečet nesmí klesnout pod předchozí ani přesáhnout pozdější stav a musí být v době, kdy
  bylo měřidlo osazené.
- Spotřeba s výměnou vodoměru během roku je součet obou měřidel; když chybí odečet na
  začátku nebo konci roku, spotřeba se nespočítá a aplikace řekne, který odečet chybí.
- Rozhodnutí přiřazené k verzi předpisu nebo volbě ji dokládá; po změně volby v profilu
  položka čeká na nové rozhodnutí a smazané rozhodnutí přestane cokoli dokládat.
  Uzávěrka hlásí verze předpisu platné v roce bez doloženého rozhodnutí.

### Výkazy a uzávěrka

- Rozvaha během roku obsahuje výsledek běžného roku a přeplatky vlastníků jsou mezi
  závazky.
- Rozvaha s majetkem, zásobami, úvěrem, dotací a opravnou položkou je vyrovnaná.
- Kontrolní seznam uzávěrky, inventurní soupisy, posouzení daně z příjmů a návrh přílohy.
- Ruční odškrtnutí bodů uzávěrky se ukládá jako historie a body, které aplikace ověřuje
  sama, ručně odškrtnout nejde.

### Katalog

Každý příklad v `catalogue/` musí dát vyrovnaný zápis s přesně očekávanými řádky a každá
operace musí mít zdroj a známý stav.

## Případy, které ještě nemají test

Tyto situace v provozu nastanou, ale aplikace je zatím neumí, nebo je umí jen zčásti:

| Případ | Co se má ověřit |
| --- | --- |
| Platba bez VS od neznámého účtu | `prijem-nesparovany`, uzávěrka zablokovaná, po vyjasnění `prijem-vyjasneni` |
| Výdaj 150 Kč bez faktury proplacený členovi výboru | kdo o proplacení žádá, nemůže ho sám schválit; podpisové záznamy u náhradního dokladu (zaúčtování platby a náhradního dokladu už test má) |
| Duplicitně zaúčtovaná faktura po doručení vyúčtování | storno, nová verze vyúčtování, původní verze zůstane dohledatelná |
| Změna podkladu po podpisu | podpisový záznam se zneplatní a doklad se vrátí do stavu `uplny` |
| Revize přiřazená ke službě | odmítnuto s odkazem na § 2 odst. 1 písm. d) zákona 67/2013 |
| Vyúčtování služeb | porovnání s předepsanými zálohami, nezaplacené zálohy zvlášť, rozdělení přesně na haléře, výsledky zúčtovatele musí sedět na účetnictví, chybějící odečet zaúčtování zablokuje; lhůty podle § 7 a 8 zákona 67/2013 až se zásilkami |
| Uzavření a otevření roku | uzávěrkové zápisy a počáteční stavy dalšího roku z konečných zůstatků, účet po účtu stejné; dluhy vlastníků po položkách se splatností, přeplatek jako přeplatek; nezaplacené faktury se nezdvojí; znovuotevření stornuje obojí a nové uzavření dá stejný výsledek |
