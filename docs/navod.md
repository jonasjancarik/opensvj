# Jak se s aplikací pracuje

Návod prochází stránky aplikace v pořadí, v jakém se obvykle používají během roku: od
nahrání výpisu z banky po roční uzávěrku. Proč se v SVJ účtuje tak, jak se účtuje,
vysvětluje [příručka](prirucka/README.md); co aplikace zatím neumí, je v tabulce
[Co z toho aplikace umí](spec/README.md#co-z-toho-aplikace-umí).

| Kdy | Stránka |
| --- | --- |
| Jednou na začátku | [Počáteční stavy](#počáteční-stavy), [Vlastníci](#vlastníci), [Měřidla](#měřidla), [Rozhodnutí](#rozhodnutí) |
| Každý měsíc | [Předpisy](#předpisy), [Banka](#banka), [Faktury](#faktury), [Dlužníci](#dlužníci) |
| Při změně záloh | [Oznámení o výši záloh](#oznámení-o-výši-záloh), [Rozesílání dokumentů](#rozesílání-dokumentů) |
| Po skončení roku | [Vyúčtování správy](#vyúčtování-správy), [Vyúčtování služeb](#vyúčtování-služeb), [Uzávěrka roku](#uzávěrka-roku) |
| Když se něco zaúčtuje špatně | [Deník a storno](#deník-a-storno) |

## Banka

Na stránce Banka se nahraje výpis ve formátu GPC (ABO), který umí stáhnout internetové
bankovnictví českých bank, nebo přehled pohybů z Raiffeisenbank
(`Pohyby_<účet>_<datum>.csv`). Přehled pohybů nemá zůstatky, takže slouží k průběžnému
zaúčtování plateb a navázání zůstatků ověří až výpis. Překrývající se přehledy ani
pozdější výpis platbu nezdvojí, protože se párují podle čísla transakce banky.

- Když aplikace číslo účtu ještě nezná, zeptá se, jestli jde o provozní účet, nebo účet
  fondu oprav, a zapamatuje si to.
- Výpis musí navazovat na předchozí (počáteční zůstatek = konečný zůstatek minulého
  výpisu) a součet plateb musí sedět na obraty v hlavičce. Jinak se nic neuloží.
- Stejný výpis podruhé nic nezdvojí. Nahrané výpisy a platby nejde měnit.
- K platbě aplikace navrhne zaúčtování: převod mezi účty SVJ, bankovní poplatek, nebo
  stejné zaúčtování jako u dřívější platby ze stejného účtu či se stejným VS. Návrh vždy
  potvrzuje člověk a při potvrzení si aplikace může volbu zapamatovat.
- Platbu vlastníka aplikace přiřadí k jednotce podle VS (předpona z profilu SVJ, číslo
  jednotky a pořadí vlastníka), když VS chybí, podle účtu, ze kterého platí vlastník,
  a nakonec podle částky měsíčního předpisu.
- U odchozí platby za fakturu se vybírá z nezaplacených faktur. Aplikace ji navrhne podle
  VS faktury, potom podle účtu dodavatele a částky. Platbu vyšší, než kolik z faktury
  zbývá, odmítne.
- Operace, které musí potvrdit účetní (například nespárovaný příjem), zatím zaúčtovat nejde.

## Faktury

Přijatá faktura se zadá na stránce Faktury: dodavatel, za co je (teplo, úklid, správa,
oprava z fondu oprav…), částka, DUZP a splatnost, nepovinně číslo faktury, VS, účet a IČO
dodavatele. Zadáním se faktura schvaluje a hned se zaúčtuje podle druhu nákladu; u opravy
z fondu oprav se musí uvést, kdo ji schválil. Stejné číslo faktury od stejného dodavatele
podruhé zadat nejde. Seznam ukazuje, kolik z každé faktury zbývá zaplatit a co je po
splatnosti.

## Počáteční stavy

Když SVJ začne účtovat v aplikaci, potřebuje konečné zůstatky předchozího roku. Stránka
Počáteční stavy (odkaz je na Přehledu a u Předpisů) je převezme z rozvahy k 31. 12.
od dřívějšího správce: zůstatky účtů rozdělené na aktiva a pasiva, které se musí rovnat,
a rozpis pohledávek za vlastníky po jednotkách. U každé položky jde napsat, za co je
(„Vyúčtování 2024“), a u dluhů dřívějších vlastníků jejich jméno; ty se současnému
vlastníkovi nezapočítají a stránka Předpisy je ukazuje zvlášť. Zaúčtuje se jeden zápis
k 1. 1. proti počátečnímu účtu rozvažnému (961), v každém roce jen jednou. U bankovních
účtů aplikace porovná zadaný zůstatek s prvním výpisem roku. Rozepsaný formulář se
průběžně ukládá, takže na něm může pokračovat i jiný člen výboru.

## Předpisy

Předpis záloh je v `profiles/<id>-predpisy.yaml`: od kdy platí, den splatnosti a složky
(fond oprav, teplo, voda, správa…). Každá složka má způsob výpočtu: sazba za m² podlahové
plochy, sazba za osobu, částka za dům rozdělená podle podílů nebo rovným dílem, nebo pevná
částka u každé jednotky. Plochy a podíly jednotek jsou v profilu SVJ. Při změně předpisu
se přidá nová verze s pozdějším datem a starší měsíce zůstanou podle staré verze.

Novou verzi (třeba po shromáždění od 1. ledna) jde zadat přímo na stránce Předpisy v části
Změny předpisu. Formulář se předvyplní podle posledního předpisu a pod ním je vidět, kolik
bude každá jednotka platit nově a o kolik víc nebo míň než dosud. Uložená verze se ukáže i
v Oznámení vlastníkům a v Rozhodnutích. Upravit nebo smazat jde jen verzi zadanou
v aplikaci, a to jen dokud podle ní není zaúčtovaný žádný měsíc.

Složky jsou ve třech skupinách: fond oprav, zálohy na správu domu (pojištění, správce,
revize, drobné opravy) a zálohy na služby. Zálohy na správu nejsou služby podle § 2 zákona
67/2013, a proto se nevyúčtovávají spolu se službami, ale zvlášť.

Na stránce Předpisy se zaúčtuje předpis za měsíc jedním zápisem pro všechny jednotky.
Měsíce jdou postupně a opakované zaúčtování nic nezdvojí. U jednotek je vidět rozpis
složek a za rok předepsáno, zaplaceno a dluh nebo přeplatek.

## Dlužníci

Stránka Dlužníci ukazuje po jednotkách, kolik je po splatnosti, od kdy a co ještě splatné
není. Platby se započítají na nejdřív splatné dluhy (OZ § 1932): nejdřív zůstatky
z minulých let, pak měsíční zálohy. U jednotky s dluhem jde zobrazit a vytisknout text
upomínky se jménem a adresou vlastníka.

## Vlastníci

Stránka Vlastníci vede, kdo kterou jednotku vlastní a od kdy, podle katastru. Spoluvlastníci
a manželé jsou jeden zápis s více osobami. Nový vlastník po prodeji uzavře vlastnictví
dosavadního den před svým začátkem, takže na sebe období navazují bez mezery; že se
nepřekrývají, hlídá i databáze. U osoby je adresa pro doručování, e-mail, souhlas
s doručováním e-mailem, telefon a účet. Jméno a adresa se tisknou v hlavičce upomínky,
oznámení o zálohách a vyúčtování a účet pomáhá párovat platby bez VS. Osobní údaje jsou
v samostatných tabulkách, takže jdou opravit nebo smazat bez zásahu do deníku.

Předpisy a dluhy se vedou na jednotku, protože dluhy na příspěvcích a zálohách přecházejí
při prodeji na kupujícího (§ 1186 odst. 2 OZ). Co na něj nepřešlo, třeba dluh, který
nebyl v potvrzení o dluzích, se u jeho záznamu v historii vlastnictví přesune na
prodávajícího (Dluhy při převodu). Aplikace předvybere dluhy splatné před převodem
a předpis za měsíc převodu podle profilu (`predpis_mesice_prevodu`: `dosavadni` nebo
`novy`). Přesunutý dluh je pak na stránce Předpisy mezi dřívějšími vlastníky a jeho
platbu jde v Bance zaúčtovat jako úhradu dluhu dřívějšího vlastníka.

U každé položky po splatnosti je zákonný úrok z prodlení (nařízení vlády 351/2013 Sb.):
repo sazba ČNB k prvnímu dni pololetí, kdy prodlení začalo, plus 8 procentních bodů.
Tabulka repo sazeb je v `backend/src/svj/domena/urok.py` a po každé změně sazby ČNB je
potřeba ji doplnit, jinak aplikace úrok pro nové pololetí nespočítá. Úrok se počítá jen
ze zbývající nezaplacené části a u dluhů z minulých let bez známé splatnosti chybí.
V upomínce ho jde zapnout. Do účetnictví se zapíše, až ho SVJ skutečně požaduje.

Ke každé jednotce jde vytisknout potvrzení o dluzích pro prodej (§ 1186 odst. 3 OZ). Na
kupujícího přejdou jen dluhy uvedené v potvrzení, proto stránka varuje, když nejsou
zaúčtované všechny bankovní pohyby nebo je poslední výpis starší než týden.

## Měřidla

Stránka Měřidla vede vodoměry, měřiče tepla a indikátory topných nákladů v jednotkách
i společná měřidla domu. Odečty se zapisují hromadně k jednomu dni; stav, který je menší
než předchozí odečet, aplikace nepřijme a nabídne zapsat výměnu. Výměna uzavře staré
měřidlo s konečným stavem a osadí nové s počátečním stavem. Spotřeba za rok je rozdíl
odečtů kolem 31. 12. předchozího a 31. 12. daného roku (nejvýš měsíc vedle), u vyměněného
měřidla součet obou. Kde odečet chybí, spotřebu aplikace nespočítá a řekne, který odečet
doplnit. Rozúčtování tepla a vody podle vyhlášky 269/2015 Sb. nedělá; odečty jsou
podklad pro zúčtovatele a kontrolu jeho výsledků.

## Rozhodnutí

Stránka Rozhodnutí vede usnesení shromáždění, výboru a předsedy: kdo a kdy rozhodl, bod
programu, znění, hlasování a kde je zápis uložený. U každé verze předpisu záloh, splatnosti,
klíče vyúčtování správy a voleb z profilu (kdo platí měsíc převodu, zálohové příspěvky)
jde vybrat rozhodnutí, o které se opírá. Co doložené není, ukáže stránka i kontrolní
seznam uzávěrky. Když se v profilu klíč nebo volba změní, položka čeká na nové rozhodnutí.

## Oznámení o výši záloh

Stránka Oznámení o zálohách (odkaz je na stránce Předpisy) porovná novou verzi předpisu s předchozí
po jednotkách a složkách a připraví oznámení pro každou jednotku. Změněnou zálohu na služby
lze požadovat nejdřív od prvního dne měsíce po doručení písemného odůvodněného oznámení
(zákon 67/2013 § 4 odst. 3), takže stránka ukáže, do kdy musí oznámení dojít. Odůvodnění
se napíše na stránce, uloží se ke konkrétní verzi předpisu a vytiskne se v každém oznámení.

## Rozesílání dokumentů

U oznámení o zálohách, obou vyúčtování, upomínky a potvrzení o dluzích je tlačítko
Rozeslat vlastníkům. Aplikace dokument každé jednotky uloží přesně v podobě, v jaké odejde
(HTML s otiskem SHA-256, později už nejde změnit), a ukáže ke kontrole, kdo dostane e-mail
a komu je potřeba poslat dopis. E-mail jde jen vlastníkům, kteří s doručováním e-mailem
souhlasili; manželé se společnou adresou dostanou jeden. Teprve potvrzením se e-maily odešlou.
Dopisy se vytisknou zvlášť a odeslání se zapíše jedním tlačítkem.

E-mail nese dokument v příloze a odkaz na stránku, kde ho vlastník otevře a tlačítkem
potvrdí převzetí. Aplikace ukládá předání poštovnímu serveru, otevření odkazu i potvrzení.
Za doručení bere potvrzení vlastníkem nebo datum, které výbor zapíše ručně na stránce
Zásilky (dodejka, převzetí osobně); samotné otevření odkazu ne, protože ho může způsobit
i antivirová kontrola pošty. Co se u e-mailu má brát jako doručení, ještě potřebuje
právní posouzení.

Od doručení se počítají lhůty: u vyúčtování služeb 30 dní na námitky a 4 měsíce na
vyrovnání, u oznámení o změně záloh měsíc, od kterého jde novou zálohu na služby požadovat,
když oznámení došlo pozdě. Obojí je vidět v tabulce jednotek na stránce dokumentu.

## Vyúčtování správy

Stránka Vyúčtování porovná náklady roku na správu domu (pojištění, správa, revize, drobné
opravy) se zálohami na správu v předpisu. Náklady každé položky se rozdělí na jednotky
podle klíče z profilu SVJ, například pojištění podle podílů na společných částech
a odměna správce rovným dílem. Výsledkem je nedoplatek nebo přeplatek jednotky a tisková
verze vyúčtování pro vlastníka.

Před koncem roku jsou čísla průběžná. Zaúčtovat jde od 31. 12., když jsou zaúčtované
předpisy všech měsíců. Nedoplatek se pak objeví na stránce Dlužníci se splatností 30. 4.
dalšího roku, stejně jako u vyúčtování služeb (§ 7 zákona 67/2013). Náklady, které k žádné
položce správy nepatří (bankovní poplatky, převod do fondu oprav), stránka vypíše zvlášť
a kam patří, rozhodne účetní. Výnosy přiřazené k položce správy, třeba pojistné plnění
na opravu, náklady té položky snižují.

## Vyúčtování služeb

Druhá záložka stránky Vyúčtování rozdělí roční náklady každé služby (teplo, voda, výtah,
úklid…) na jednotky a porovná je se zálohami na tutéž službu v předpisu. Jak se služba
dělí, určuje profil SVJ: podle počtu osob (výchozí podle zákona 67/2013), rovným dílem,
podle plochy nebo podílu, podle spotřeby na měřidlech, nebo podle výsledků od zúčtovatele
tepla, které výbor opíše do formuláře. Dělí se přesně na haléře.

Když službu rozdělit nejde (jednotce chybí měřidlo nebo odečet, výsledky zúčtovatele
nesedí na účetnictví), stránka řekne proč a zaúčtovat nedovolí. Nedoplatky a přeplatky
se zaúčtují k 31. 12. a jsou splatné 30. 4. dalšího roku. Vyúčtování pro vlastníka
rozepíše služby, u měřidel i spotřebu jednotky, a nezaplacené měsíční zálohy uvede
zvlášť.

## Uzávěrka roku

Stránka Uzávěrka má pět částí:

- co zbývá udělat: kontroly, které aplikace ověří sama z účetnictví (počáteční stavy,
  předpisy, nezaúčtované pohyby, zůstatky proti výpisům, vyrovnané pomocné účty,
  vyúčtování, doložená rozhodnutí), a body, které se odškrtávají ručně,
- rozvaha a výsledovka ve zkráceném rozsahu, v tisících Kč i přesně,
- inventura: zůstatky rozvahových účtů s rozpisem po jednotkách nebo fakturách a tisk
  inventurních soupisů se zákonnými náležitostmi,
- daň z příjmů: jestli SVJ musí podat přiznání (§ 38mb ZDP) a jak se který výnos daní,
- návrh přílohy k účetní závěrce s vyznačenými místy k doplnění.

Ruční odškrtnutí vidí celý výbor i s tím, kdo bod odškrtl a kdy, a zůstává celá historie
zaškrtnutí i zrušení.

Od prosince stránka nabídne začít účtovat další rok, aby šly v lednu zaúčtovat předpisy
a výpisy dřív, než je uzávěrka hotová. Když je všechno hotové nebo odškrtnuté, tlačítko
Uzavřít rok zaúčtuje k 31. 12. uzávěrkové zápisy a k 1. 1. převede zůstatky do dalšího roku:
peníze na účtech, nezaplacené faktury i dluhy a přeplatky vlastníků po jednotlivých
položkách se splatností, takže Dlužníci v novém roce správně počítají, co je po splatnosti.
Do uzavřeného roku už nic zaúčtovat nejde. Když se před schválením závěrky najde chyba, rok
jde s uvedením důvodu znovu otevřít a po opravě uzavřít znovu.

## Deník a storno

Stránka Deník ukazuje zápisy roku s řádky. Zaúčtovaný zápis nejde změnit ani smazat;
chybu opraví storno, tedy protizápis ke stejnému dni s uvedeným důvodem. Po stornu jde
stejnou věc (předpis měsíce, platbu, počáteční stavy, fakturu) zaúčtovat znovu. Fakturu
s úhradou jde stornovat až po stornu úhrady.
