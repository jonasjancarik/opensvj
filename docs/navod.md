# Jak se s aplikací pracuje

Návod prochází stránky aplikace v pořadí, v jakém se obvykle používají během roku: od
nahrání výpisu z banky po roční uzávěrku. Proč se v SVJ účtuje tak, jak se účtuje,
vysvětluje [příručka](prirucka/README.md); co aplikace zatím neumí, je v tabulce
[Co z toho aplikace umí](spec/README.md#co-z-toho-aplikace-umí).

| Kdy | Stránka |
| --- | --- |
| Jednou na začátku | [Počáteční stavy](#počáteční-stavy), [Vlastníci](#vlastníci), [Měřidla](#měřidla), [Rozhodnutí](#rozhodnutí) |
| Každý měsíc | [Předpisy](#předpisy), [Banka](#banka), [Faktury](#faktury), [Pokladna](#pokladna), [Dlužníci](#dlužníci) |
| Při změně záloh | [Oznámení o výši záloh](#oznámení-o-výši-záloh), [Mimořádná záloha](#mimořádná-záloha), [Rozesílání dokumentů](#rozesílání-dokumentů) |
| Když si SVJ vezme úvěr | [Úvěry](#úvěry) |
| Když SVJ koupí dražší věc, pozemek nebo jednotku | [Majetek](#majetek) |
| Po skončení roku | [Vyúčtování správy](#vyúčtování-správy), [Vyúčtování služeb](#vyúčtování-služeb), [Uzávěrka roku](#uzávěrka-roku) |
| Když shromáždění rozhodne o zisku nebo ztrátě | [Fond ze zisku](#fond-ze-zisku) |
| Když SVJ pronajímá společné části (střechu, sušárnu) | [Příjmy vlastníků](#příjmy-vlastníků) |
| Když se něco zaúčtuje špatně | [Deník a storno](#deník-a-storno) |
| Kdo co změnil | [Historie změn](#historie-změn) |

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
- Když vlastník při platbě řekl, na který dluh platí (třeba nedoplatek z vyúčtování
  místo záloh), vybere se ten dluh u platby v poli Na který dluh vlastník platí. Platba
  se pak zaúčtuje na jeho účet a na stránce Dlužníci jde nejdřív na něj (§ 1933 OZ).
- Kromě plateb vlastníků a faktur jde platbu zaúčtovat jako úrok od banky, pojistné
  plnění (rovnou do výnosů, nebo jako úhradu plnění zaúčtovaného už v roce škody),
  nájemné ze společných částí, přijatou dotaci, zaplacenou smluvní pokutu od dodavatele,
  úhradu dříve odepsaného dluhu, vrácení přeplatku vlastníkovi (s výběrem, jestli jde
  o přeplatek z vyúčtování, nebo na zálohách), zálohu dodavateli energie nebo vody
  a výplatu podílu na příjmech ze společných částí.
- U úhrady nájemného, pojistného plnění z roku škody, smluvní pokuty a dotace aplikace
  nabídne, kdo ještě dluží a kolik. Když nikdo nedluží, jméno se napíše ručně.
- U odchozí platby za fakturu se vybírá z nezaplacených faktur. Aplikace ji navrhne podle
  VS faktury, potom podle účtu dodavatele a částky. Platbu vyšší, než kolik z faktury
  zbývá, odmítne.
- Výdaj, ke kterému chybí doklad od dodavatele (třeba drobný nákup proplacený členovi
  výboru), se v Bance zaúčtuje jako výdaj bez dokladu. Peníze tím odešly, ale náklad ještě
  ne: na stránce Deník se k němu interním dokladem zapíše náhradní doklad, tedy co se
  koupilo, kdo nákup zadal a kdo ho schválil, a vybere se položka správy, ze které se
  platí. Dokud náhradní doklad chybí, uzávěrka roku na výdaj upozorní.
- Splátka úvěru odchází z běžného účtu jako splátka úvěru z provozního účtu. Peníze
  jsou pak na cestě, dokud se na stránce Úvěry nezapíše, že dorazily na úvěrový účet.
- Výběr hotovosti z účtu do pokladny se v Bance zaúčtuje jako výběr do pokladny. Na
  stránce Pokladna se pak stejná částka zapíše jako příjem.
- Operace, které musí potvrdit účetní (například nespárovaný příjem), zatím zaúčtovat nejde.

## Pokladna

Stránka Pokladna je pro SVJ, které vede hotovost. Ukazuje, kolik je v pokladně, a pokladní
knihu roku: každý příjem a výdaj s průběžným zůstatkem. Nový pokladní doklad je jeden ze
tří druhů:

- **Příjem hotovosti vybrané z účtu.** Výběr se nejdřív zaúčtuje v Bance jako výběr
  hotovosti do pokladny. Příjem nemůže být vyšší, než kolik je z účtu vybráno a do
  pokladny ještě nepřijato; stránka tuto částku ukazuje.
- **Drobný výdaj** s popisem, co se koupilo, a s položkou správy, ze které se platí.
  Výdaj bez položky správy se do vyúčtování záloh na správu nezapočte, dokud ho účetní
  nezařadí. Pokladna nesmí jít do minusu ani zpětně: výdaj s dřívějším datem neprojde,
  když by zůstatek v některý pozdější den klesl pod nulu.
- **Vlastník platí hotově** za vybranou jednotku. Platba sníží jeho dluh stejně jako
  platba na účet.

Každý příjem a výdaj potřebuje pokladní doklad s podpisem. Zůstatek pokladny se k 31. 12.
ověřuje inventurou, tedy spočítáním hotovosti. Dokud SVJ nemá v nastavení účet pokladny,
stránka jen upozorní, že je potřeba ho doplnit.

## Faktury

Přijatá faktura se zadá na stránce Faktury: dodavatel, za co je (teplo, úklid, správa,
oprava z fondu oprav…), částka, DUZP a splatnost, nepovinně číslo faktury, VS, účet a IČO
dodavatele. Zadáním se faktura schvaluje a hned se zaúčtuje podle druhu nákladu; u opravy
z fondu oprav, z fondu ze zisku nebo z úvěru se musí uvést, kdo ji schválil. Opravu z fondu
ze zisku aplikace nezaúčtuje, když ve fondu není dost peněz (viz [Fond ze zisku](#fond-ze-zisku)). Oprava hrazená
z úvěru se nabízí, jen když má SVJ v profilu účty pro úvěr; platí se ze záloh vlastníků
na úvěr, ne z běžného fondu oprav, a zaplatí ji banka (viz [Úvěry](#úvěry)). Faktura za
pořízení dlouhodobého majetku jde na pořizování majetku a do nákladů se dostane až
odpisy (viz [Majetek](#majetek)). Stejné číslo faktury od stejného dodavatele
podruhé zadat nejde. Seznam ukazuje, kolik z každé faktury zbývá zaplatit a co je po
splatnosti.

Když má dodavatel nezaplacenou smluvní pokutu (uplatněnou interním dokladem v Deníku),
u jeho faktury se objeví upozornění a tlačítko Započíst proti této faktuře. Zápočet
sníží, kolik z faktury zbývá zaplatit, a nejde započíst víc, než zbývá z faktury
nebo z pokut. Pokuta je výnos SVJ a daní se, až když ji dodavatel zaplatí nebo se
započte (viz [Uzávěrka roku](#uzávěrka-roku)).

## Počáteční stavy

Když SVJ začne účtovat v aplikaci, potřebuje konečné zůstatky předchozího roku. Stránka
Počáteční stavy (odkaz je na Přehledu a u Předpisů) je převezme z rozvahy k 31. 12.
od dřívějšího správce: zůstatky účtů rozdělené na aktiva a pasiva, které se musí rovnat,
a rozpis pohledávek za vlastníky po jednotkách. U každé položky jde napsat, za co je
(„Vyúčtování 2024“), a u dluhů dřívějších vlastníků jejich jméno; ty se současnému
vlastníkovi nezapočítají a stránka Předpisy je ukazuje zvlášť. Zaúčtuje se jeden zápis
k 1. 1. proti počátečnímu účtu rozvažnému (961), v každém roce jen jednou. U bankovních
účtů aplikace porovná zadaný zůstatek s prvním výpisem roku. Nerozdělený výsledek
minulého roku se zadá na účet 931 a neuhrazená ztráta z dřívějších let na 932; rozdělení
výsledku se pak zaúčtuje na stránce [Fond ze zisku](#fond-ze-zisku). Rozepsaný formulář se
průběžně ukládá, takže na něm může pokračovat i jiný člen výboru.

## Předpisy

Předpis záloh je v `profiles/<id>-predpisy.yaml`: od kdy platí, den splatnosti a složky
(fond oprav, teplo, voda, správa…). Každá složka má způsob výpočtu: sazba za m² podlahové
plochy, sazba za osobu, částka za dům rozdělená podle podílů nebo rovným dílem, nebo pevná
částka u každé jednotky. Plochy a výchozí podíly jednotek jsou v profilu SVJ, změny podílů
se zapisují na stránce Podíly na společných částech (viz Vlastníci). Při změně předpisu
se přidá nová verze s pozdějším datem a starší měsíce zůstanou podle staré verze.

Novou verzi (třeba po shromáždění od 1. ledna) jde zadat přímo na stránce Předpisy v části
Změny předpisu. Formulář se předvyplní podle posledního předpisu a pod ním je vidět, kolik
bude každá jednotka platit nově a o kolik víc nebo míň než dosud. Uložená verze se ukáže i
v Oznámení vlastníkům a v Rozhodnutích. Upravit nebo smazat jde jen verzi zadanou
v aplikaci, a to jen dokud podle ní není zaúčtovaný žádný měsíc.

Složky jsou ve třech skupinách: fond oprav, zálohy na správu domu (pojištění, správce,
revize, drobné opravy) a zálohy na služby. Splátky úvěru jsou čtvrtá skupina; nezadávají
se tady, ale přidá je stránka [Úvěry](#úvěry). Zálohy na správu nejsou služby podle § 2 zákona
67/2013, a proto se nevyúčtovávají spolu se službami, ale zvlášť.

Když stanovy určují, že příspěvky na správu nejsou zálohové (v profilu SVJ
`prispevky: nezalohove`), složky správy a fondu oprav se předepisují rovnou jako výnos
SVJ (příspěvky vlastníků, 649) a nevyúčtovávají se. Zálohy na služby se předepisují
a vyúčtovávají stejně jako jinde. Předpis vypadá pro vlastníky stejně, mění se jen
účtování; nevyčerpané peníze pak nejsou ve fondu oprav, ale ve fondu ze zisku.

Na stránce Předpisy se zaúčtuje předpis za měsíc jedním zápisem pro všechny jednotky.
Měsíce jdou postupně a opakované zaúčtování nic nezdvojí. U jednotek je vidět rozpis
složek a za rok předepsáno, zaplaceno a dluh nebo přeplatek.

### Mimořádná záloha

Když shromáždění rozhodne o jednorázovém příspěvku na opravu nebo investici (třeba výměnu
oken), předepíše se odkazem Mimořádná záloha podle podílů na stránce Předpisy. Zadá se,
na co záloha je, celková částka za dům, rozhodnutí shromáždění, den předpisu a splatnost.
Formulář hned ukáže, kolik připadne na každou jednotku: částka se rozdělí podle podílů na
společných částech platných v den předpisu, na haléře přesně. Rozhodnutí musí být
zapsané na stránce Rozhodnutí a jde vybrat jen rozhodnutí shromáždění. Předepsaná záloha
jde do fondu oprav a u každé jednotky se na stránce Dlužníci objeví jako samostatný dluh
se splatností, kterou určilo shromáždění. Opravit ji jde stornem zápisu na stránce Deník.

## Úvěry

Když shromáždění schválí úvěr na opravu nebo investici, jehož jistinu splatí vlastníci
podle podílů, zadá se na stránce Úvěry: na co je, jistina, rozhodnutí shromáždění, den
předpisu podílů, od kterého měsíce se splácí, počet měsíčních splátek a z čeho se platí
úroky (fond oprav, mimořádné zálohy na úvěr, nebo některá položka správy). Formulář hned
ukáže, kolik jistiny připadne na každou jednotku podle podílů platných v den předpisu
a kolik bude měsíčně splácet. Splátka je podíl jednotky dělený počtem splátek,
zaokrouhlený nahoru na koruny, poslední splátka je zbytek. Jednotka s malým podílem proto
může mít splaceno o něco dřív než ostatní.

Založením se celý podíl každé jednotky předepíše najednou jako mimořádná záloha na úvěr
a splátka se od zvoleného měsíce sama přidá do měsíčního předpisu jako složka Splátka
úvěru. Na stránce Předpisy je ve skupině Splátky úvěru a v oznámení o výši záloh se ukáže
jako změna. Začít jde jen měsícem, jehož předpis ještě není zaúčtovaný. Založený úvěr
nejde upravit: když je v něm chyba, stornuje se předpis podílů na stránce Deník a úvěr se
zadá znovu. To jde jen do zaúčtování první splátky.

U úvěru se zapisuje, co je na výpisu z úvěrového účtu:

- banka zaplatila fakturu z úvěru (faktura se nejdřív zadá na stránce Faktury jako oprava
  hrazená z úvěru),
- banka připsala úroky a poplatky; u poplatků se vybírá položka správy, ze které se platí,
- splátka dorazila na úvěrový účet; odejít z běžného účtu musí nejdřív v Bance.

Stránka ukazuje, kolik zbývá splatit bance, kolik vlastníci ještě nesplatili a rozpis po
jednotkách. Úroky, které podle rozhodnutí platí fond oprav nebo mimořádné zálohy na úvěr,
se po skončení roku uhradí tlačítkem Uhradit úroky za rok; do té doby je vyúčtování
správy ukazuje mezi náklady, které k žádné položce nepatří.

## Majetek

Na stránce Majetek se vede dlouhodobý majetek SVJ: věci, které se používají déle než rok
a stojí víc než hranice z vnitřního předpisu SVJ (třeba robotická sekačka), a vždy pozemky
a jednotky. Levnější věci jdou rovnou do nákladů a v evidenci nejsou. Společné části domu
majetkem SVJ nejsou.

Majetek se kupuje fakturou, která se na stránce Faktury zadá jako pořízení dlouhodobého
majetku (u softwaru na zakázku jako pořízení nehmotného majetku). Až se majetek začne
používat, zařadí se na stránce Majetek: co to je, druh, den zařazení, pořizovací cena (nejvýš
kolik z faktur za pořízení čeká na zařazení), na kolik let se odepisuje podle odpisového
plánu SVJ a z čeho se platí:

- **fond oprav**: vlastníci majetek zaplatí najednou při zařazení a odpisy je už znovu
  nezatíží,
- **fond ze zisku**: totéž u SVJ, které má fond ze zisku minulých let,
- **provozní zálohy na některou položku správy**: vlastníci majetek zaplatí postupně,
  protože odpisy jdou do vyúčtování záloh na správu podle klíče položky (počítač pro
  výbor rovným dílem, sekačka podle podílů).

Odepisuje se rovnoměrně po měsících od měsíce po zařazení, po celých korunách. Pozemky se
neodepisují. Karta ukazuje odpisový plán po letech a zůstatkovou cenu. Odpisy za rok se
zaúčtují tlačítkem od 31. 12.; u majetku placeného z provozních záloh to musí být před
vyúčtováním správy, jinak ho aplikace nezaúčtuje.

Majetek, který SVJ mělo už před začátkem účtování v aplikaci a který je v počátečních
stavech, se převezme do evidence k 1. 1. s oprávkami k tomu dni. Co z ceny zbývá, se
rozloží rovnoměrně do konce odpisové doby. Uzávěrka roku hlídá, že evidence sedí na účty
majetku a oprávek.

Název, inventární číslo a poznámku jde upravit kdykoli. Když je špatně cena, datum nebo
doba odpisování, stornuje se zápis o zařazení na stránce Deník (jde to, dokud nejsou
zaúčtované odpisy) a majetek se zařadí znovu. Majetek, který se prodá, zničí nebo ztratí,
se vyřadí: zbytek ceny se odepíše najednou a majetek se odúčtuje. Peníze z prodeje se
zaúčtují zvlášť u platby v Bance.

## Dlužníci

Stránka Dlužníci ukazuje po jednotkách, kolik je po splatnosti, od kdy a co ještě splatné
není. Platba, u které vlastník určil dluh, jde nejdřív na ten dluh. Ostatní platby se
započítají na nejdřív splatné dluhy (§ 1933 OZ): nejdřív zůstatky z minulých let, pak
měsíční zálohy. U jednotky s dluhem jde zobrazit a vytisknout text upomínky se jménem
a adresou vlastníka.

Když má vlastník předepsaný úrok z prodlení a platbu nijak neurčil, jde podle § 1932
OZ nejdřív na úrok a teprve potom na zálohy. Aplikace platbu zaúčtovanou jako úhradu
předpisu vždy počítá na zálohy; v takovém případě ji v Bance zaúčtujte jako úhradu úroku
z prodlení.

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

Tamtéž je odkaz na potvrzení o dluzích prodávajícího k datu převodu, tedy k poslednímu
dni, kdy jednotku vlastnil. Hodí se, když potvrzení chce prodávající nebo kupující až po
převodu. Počítá se s předpisy a platbami zaúčtovanými s datem do toho dne a ze záloh za
měsíc převodu jen s těmi, které podle profilu platil prodávající. Rozeslat ho jde
prodávajícímu, i když už jednotku nevlastní.

U každé položky po splatnosti je zákonný úrok z prodlení (nařízení vlády 351/2013 Sb.):
repo sazba ČNB k prvnímu dni pololetí, kdy prodlení začalo, plus 8 procentních bodů.
Tabulka repo sazeb je v `backend/src/svj/domena/urok.py` a po každé změně sazby ČNB je
potřeba ji doplnit, jinak aplikace úrok pro nové pololetí nespočítá. Úrok se počítá jen
ze zbývající nezaplacené části a u dluhů z minulých let bez známé splatnosti chybí.
V upomínce ho jde zapnout. Do účetnictví se zapíše, až ho SVJ skutečně požaduje:
tlačítko Požadovat úrok z prodlení u jednotky ho předepíše k dnešku (částku jde snížit).
Předepsaný úrok je pak vidět zvlášť od dluhů na zálohách, upomínka ho přičte k úhradě
a spočtený úrok se dál počítá jen za dobu po předpisu. Platbu úroku jde v Bance zaúčtovat
jako úhradu úroku z prodlení.

Podíly jednotek na společných částech jsou na stránce Podíly na společných částech
(odkaz je na stránce Vlastníci). Podíly z profilu SVJ platí, dokud se nezapíše změna:
celá nová sada podílů všech jednotek s datem, od kdy platí (obvykle den zápisu změny
prohlášení vlastníka do katastru), a s tím, podle čeho se mění. Součet podílů musí dát
přesně 1, formulář hned ukáže, kolik chybí nebo přebývá, a když předpis dělí některou
složku podle podílů, i jak se změní měsíční zálohy jednotek. Předpis a vyúčtování počítají
po celých měsících, takže změna od 15. 7. se v předpisu projeví od srpna. Roční vyúčtování
dělí náklady podle průměrného podílu za měsíce roku a vlastníkovi vypíše, jaký podíl kdy
platil. Změnu, která by šla do už zaúčtovaných předpisů nebo do uzavřeného roku, aplikace
neuloží; pokud opravdu platí dřív, je potřeba nejdřív stornovat předpisy od toho měsíce.
Změna podílů se zapíše do historie změn.

Ke každé jednotce jde vytisknout potvrzení o dluzích pro prodej (§ 1186 odst. 3 OZ). Na
kupujícího přejdou jen dluhy uvedené v potvrzení, proto stránka varuje, když nejsou
zaúčtované všechny bankovní pohyby nebo je poslední výpis starší než týden. Když jednotka
splácí podíl na úvěru, potvrzení uvede i nesplacený zbytek podílu a měsíční splátku.
Dluhem prodávajícího nejsou, ale kupující s jednotkou převezme povinnost je splácet.

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

Schválený předpis záloh jde dál upravit nebo smazat, ale jen s napsaným důvodem. Změna se
zapíše do historie změn a schválení přestane platit: u předpisu i na stránce Rozhodnutí se
objeví „Změněno po schválení“ s datem, autorem a důvodem a s odkazem na to, co přesně se
změnilo. Když rozhodnutí pokrývá i novou podobu (třeba šlo o překlep), stačí tlačítko
Rozhodnutí platí i pro změnu. Jinak se k předpisu vybere nové rozhodnutí. Dokud schválení
neplatí, upozorní na to i kontrolní seznam uzávěrky.

## Oznámení o výši záloh

Stránka Oznámení o zálohách (odkaz je na stránce Předpisy) porovná novou verzi předpisu s předchozí
po jednotkách a složkách a připraví oznámení pro každou jednotku. Změněnou zálohu na služby
lze požadovat nejdřív od prvního dne měsíce po doručení písemného odůvodněného oznámení
(zákon 67/2013 § 4 odst. 3), takže stránka ukáže, do kdy musí oznámení dojít. Odůvodnění
se napíše na stránce, uloží se ke konkrétní verzi předpisu a vytiskne se v každém oznámení.
Když předpis dělí některou složku podle podílů, je změna podílů také změnou předpisu: stránka
ji nabídne mezi verzemi od prvního měsíce, kdy se s novými podíly počítá.

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

U nezálohových příspěvků se správa nevyúčtovává a stránka to jen oznámí. Jinak stránka
Vyúčtování porovná náklady roku na správu domu (pojištění, správa, revize, drobné
opravy) se zálohami na správu v předpisu. Náklady každé položky se rozdělí na jednotky
podle klíče z profilu SVJ, například pojištění podle podílů na společných částech
a odměna správce rovným dílem. Výsledkem je nedoplatek nebo přeplatek jednotky a tisková
verze vyúčtování pro vlastníka. Když se podíly během roku změnily, dělí se podle průměrného
podílu za měsíce roku a vyúčtování pro vlastníka uvede, jaký podíl kdy platil.

Když jednotka během roku změnila vlastníka, dostane obě vyúčtování (správy i služeb)
vlastník k 31. 12. a s prodávajícím se vyrovná sám. SVJ si ale v profilu může zvolit
`vyuctovani_pri_prevodu: po_obdobich`: pak každý vlastník dostane vyúčtování za měsíce,
za které platil předpis (měsíc převodu podle `predpis_mesice_prevodu`). Jeho zálohy jsou
zálohy předepsané za ty měsíce a náklady jednotky se rozdělí podle měsíců: u klíče podle
podílů podle podílu v každém měsíci, u klíče podle osob podle osob v předpisu, jinak
rovným dílem na měsíc. Spotřeba z měřidel a výsledky zúčtovatele se tak dělí také podle
měsíců, ne podle odečtu ke dni převodu. Rozpis je v rozbaleném řádku jednotky a každý
vlastník má vlastní dokument; prodávajícímu se rozešle na jeho adresu. Nedoplatek nebo
přeplatek prodávajícího se zaúčtuje na jeho jméno, takže je na stránce Předpisy mezi
dřívějšími vlastníky a do dluhů kupujícího se nepočítá. Lhůty pro námitky a vyrovnání
v tabulce jednotek běží od doručení kupujícímu.

Před koncem roku jsou čísla průběžná. Zaúčtovat jde od 31. 12., když jsou zaúčtované
předpisy všech měsíců. Nedoplatek se pak objeví na stránce Dlužníci se splatností 30. 4.
dalšího roku, stejně jako u vyúčtování služeb (§ 7 zákona 67/2013). Náklady, které k žádné
položce správy nepatří (bankovní poplatky, převod do fondu oprav), stránka vypíše zvlášť
a kam patří, rozhodne účetní. Odpisy majetku placeného z provozních záloh jsou nákladem
své položky. Výnosy přiřazené k položce správy, třeba pojistné plnění
na opravu, náklady té položky snižují.

Opravy placené z fondu oprav nebo z úvěru do vyúčtování záloh na správu nepatří, protože
je vlastníci zaplatili dlouhodobými zálohami. Stránka je přesto vypíše v části Zaplaceno
z fondu oprav (a ze záloh na úvěr, když nějaký úvěr je), aby bylo vidět, co z kterých
peněz šlo. Úroky z úvěru, které podle rozhodnutí platí fond oprav nebo zálohy na úvěr, jsou
mezi nezahrnutými náklady, dokud se na stránce Úvěry neuhradí k 31. 12.

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
  vyúčtování, odpisy a evidence majetku, rozdělení výsledku minulého roku, fond ze zisku,
  doložená rozhodnutí), a body, které se odškrtávají ručně, mezi nimi nevyčerpané dotace
  a odhady pojistného plnění z minulých let, ke kterým pojišťovna ještě neoznámila
  plnění,
- rozvaha a výsledovka ve zkráceném rozsahu, v tisících Kč i přesně,
- inventura: zůstatky rozvahových účtů s rozpisem po jednotkách nebo fakturách a tisk
  inventurních soupisů se zákonnými náležitostmi,
- daň z příjmů: jestli SVJ musí podat přiznání (§ 38mb ZDP), jak se který výnos daní
  a návrh výpočtu daně po řádcích přiznání. Úroky z prodlení a smluvní pokuty od
  dodavatelů se daní až po zaplacení,
  takže nezaplacené letošní základ snižují a loňské zaplacené letos ho zvyšují. Daň jde
  tlačítkem zaúčtovat k 31. 12. jako náklad na správu domu; udělejte to před vyúčtováním
  záloh na správu, které ji pak rozdělí mezi vlastníky. Zaplacení daně a úhradu úroku
  z prodlení jde vybrat u platby na stránce Banka,
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

## Fond ze zisku

Výsledek hospodaření roku se při jeho uzavření převede do dalšího roku jako výsledek
čekající na rozhodnutí shromáždění (931). U zálohových příspěvků bývá nulový, u
nezálohových je to obvykle zisk. Stránka Fond ze zisku ukáže, kolik z minulého roku
čeká, a po rozhodnutí shromáždění ho jedním tlačítkem zaúčtuje: zadá se den a odkaz na
rozhodnutí. Zisk nejdřív uhradí neuhrazené ztráty z minulých let a zbytek jde do fondu ze
zisku (911); ztráta se převede mezi neuhrazené ztráty (932) a uhradí ji zisky dalších let.
Do fondu oprav zisk nepatří: fond oprav jsou zálohy jednotlivých vlastníků. Opravit
rozdělení jde stornem v Deníku.

Pod tím je přehled fondu v roce: stav na začátku, co do něj přibylo a co se z něj čerpalo,
a stav teď nebo na konci roku. Z fondu se platí opravy zadané na stránce Faktury jako
„Oprava hrazená z fondu ze zisku“: oprava jde do nákladů a fond se ve stejné výši
rozpustí do výnosů, takže výsledek roku nezhorší. Fondem ze zisku jde krýt i pořízení
majetku (viz [Majetek](#majetek)). Fond nesmí jít do záporu; aplikace takovou fakturu ani
zařazení majetku nezaúčtuje a uzávěrka hlásí nerozdělený výsledek i fond v záporu.

## Příjmy vlastníků

Nájemné za společné části domu (střecha pro anténu, sušárna pronajatá jako sklad) patří
vlastníkům, ne společenství. Nájemné se předepíše interním dokladem v Deníku („Předpis
nájemného ze společných částí“) a platba od nájemce se zaúčtuje v Bance jako úhrada
nájemného. Nájemce pište pokaždé stejně, podle něj se platby párují.

Stránka Příjmy vlastníků za vybraný rok ukáže platby od nájemců a jejich rozdělení na
jednotky. Každá platba se dělí podle podílů na společných částech platných v den platby
a připadne tomu, kdo jednotku v ten den vlastnil. U jednotky je vidět, kolik se v roce
vyplatilo, převedlo do fondu oprav a kolik zbývá vypořádat, i z minulých let. Vypořádání
z doby před začátkem účtování v aplikaci se tu ukáže, jen když jsou počáteční stavy účtu
příjmů vlastníků zadané po jednotkách.

- Výplata podílu se zaúčtuje v Bance jako výplata podílu na příjmech ze společných částí.
- Převod do fondu oprav jde tlačítkem u jednotky. Potřebuje výslovný, nejlépe písemný
  souhlas vlastníka: do formuláře se napíše, kdy a jak o převod požádal, a souhlas se
  potvrdí zaškrtnutím. Víc, než jednotce zbývá, převést nejde.
- Potvrzení pro daňové přiznání vlastníka jde vytisknout u každé jednotky. Obsahuje podíl
  na platbách, které SVJ v roce od nájemců skutečně dostalo, a pro vlastníky, kteří vedou
  účetnictví, i podíl na nájemném předepsaném na rok. Když jednotka v roce změnila
  vlastníka, má každý z nich vlastní potvrzení jen za dobu, kdy jednotku vlastnil.

Nájemné předepsané jako výnos SVJ (dosavadní praxe některých SVJ) se na stránce nepočítá
a stránka na ně upozorní.

## Historie změn

Stránka Historie změn ukazuje, kdo a kdy přidal, změnil nebo smazal vlastníka nebo
vlastnictví jednotky, podíly na společných částech, rozhodnutí a jeho přiřazení, předpis
záloh, měřidlo, odečet, výsledek
od zúčtovatele nebo stav účetního roku (uzavření a znovuotevření). U každé změny je stav
předtím a potom a důvod, pokud ho aplikace vyžaduje. Záznamy nejde upravit ani smazat.
Zaúčtované doklady se v deníku nemění, opravují se stornem, takže jejich historie je
v Deníku.

## Deník a storno

Stránka Deník ukazuje zápisy roku s řádky. Zaúčtovaný zápis nejde změnit ani smazat;
chybu opraví storno, tedy protizápis ke stejnému dni s uvedeným důvodem. Po stornu jde
stejnou věc (předpis měsíce, platbu, počáteční stavy, fakturu) zaúčtovat znovu. Fakturu
s úhradou jde stornovat až po stornu úhrady.

Účetní případy, které nemají vlastní stránku, se zaúčtují interním dokladem: na stránce
Deník tlačítko Zaúčtovat interní doklad. Nabízí časové rozlišení (náklad příštích období,
s položkou správy, aby ho vyúčtování záloh započítalo do správného roku), dohadnou
položku k 31. 12. a její zrušení po doručení faktury (krok Faktura přišla: zrušit odhad;
fakturu samotnou pak zadejte na stránce Faktury), náhradní doklad k výdaji bez dokladu
z Banky, zásoby, dotace (rozhodnutí a použití na náklady roku s nabídkou nevyčerpaných
dotací), pojistné plnění v roce škody (přiznané, nebo odhad) a oznámení plnění k odhadu,
smluvní pokutu dodavateli, předpis nájemného ze společných částí, převod výnosů do fondu
oprav, vyčlenění pochybných dluhů, opravné položky, odměny
výboru, přeúčtování mezi službami a vyjasnění nespárované platby. Před zaúčtováním
formulář ukáže, na které účty a jakými částkami se zápis zapíše. Odhad ani výdaj bez
dokladu nejde vyřešit vyšší částkou, než kolik k danému dni zbývá, a dotaci nejde použít
nad to, co z ní zbývá. U oznámení plnění se vybere událost s odhadem a zadá se jen
oznámená částka: rozdíl proti odhadu jde do nákladů, nebo výnosů letošního roku. Operace, pro kterou
v profilu SVJ chybí účet, se nenabízí a formulář ji vypíše.
