# Specifikace OpenSVJ

Specifikace popisuje, co má OpenSVJ dělat a podle jakých pravidel. Technologii určuje jen
tam, kde na ní závisí správnost: přesné částky a podíly, neměnné zápisy, kontrola
vyrovnanosti v databázi. U každé části je vidět, co aplikace už umí a co je zatím záměr.

## Části

1. [Doménový model](01-domena.md): z čeho se evidence skládá, jaké stavy věci mají a jaká
   pravidla musí platit vždy.
2. [Účtová osnova a výkazy](02-ucetni-osnova.md): účtové skupiny podle vyhlášky
   504/2002 Sb., role účtů a převod zůstatků na zkrácenou rozvahu a výkaz zisku a ztráty.
3. [Katalog účetních operací](../../catalogue/README.md): formát předkontací. Samotné
   operace jsou strojově čitelné v `catalogue/`.
4. [Testovací scénáře](03-scenare.md): co ověřují testy nad ukázkovým SVJ a které případy
   z provozu ještě testy nemají.

Proč se účtuje tak, jak se účtuje, s odkazy na předpisy a literaturu, vysvětluje
[příručka](../prirucka/README.md). Jak se s hotovými částmi pracuje, popisuje
[návod](../navod.md).

## Rozsah první verze

První verze má zvládnout celý účetní rok malého SVJ bez další účetní aplikace:

- jednotky, podíly na společných částech, vlastníci a počty osob pro rozúčtování,
- předpisy záloh na správu domu (fond oprav, zálohy na správu) a na služby,
- import bankovních výpisů, párování plateb, salda vlastníků a dodavatelů,
- přijaté faktury a ostatní doklady s přílohami, schvalováním a podpisovými záznamy,
- podvojný deník, hlavní kniha a analytická evidence,
- vyúčtování záloh na správu domu a vyúčtování služeb podle zákona 67/2013 Sb.
  s výsledky od externího zúčtovatele tepla a vody,
- roční uzávěrka: inventura, zkrácená rozvaha a výkaz zisku a ztráty, příloha, zpráva
  o hospodaření a export deníku,
- rozesílání předpisů, vyúčtování a upomínek vlastníkům se záznamem o odeslání
  a doručení a upozornění pro výbor.

Mimo první verzi zůstávají hlasování, novinky a další komunikace s vlastníky, mzdy
a dohody o provedení práce, cizí měny, DPH a více domů v jedné
instalaci. Datový model je nesmí znemožnit, ale nemusí je řešit.

### Co z toho aplikace umí

| Oblast | Stav |
| --- | --- |
| Jednotky, plochy, podíly, počty osob | Jednotky, plochy a výchozí podíly v profilu SVJ (YAML). Změny podílů s platností od data se zadávají v aplikaci (stránka Podíly na společných částech): vždy celá sada se součtem přesně 1, předpis s ní počítá od prvního celého měsíce, roční vyúčtování podle průměru podílů za měsíce roku. Změna podílů je i změnou předpisu pro oznámení o zálohách. |
| Vlastníci | Osoby a vlastnictví jednotek s platností od–do, stránka Vlastníci. Jméno a adresa se tisknou v upomínce, oznámení o zálohách, vyúčtování a potvrzení o dluzích; účet vlastníka pomáhá párovat platby. Dluhy jdou s jednotkou; ty, které na kupujícího nepřešly, jde při převodu přesunout na prodávajícího a jeho pozdější platbu zaúčtovat v Bance. Kdo platí předpis za měsíc převodu, určuje profil. Potvrzení o dluzích jde vydat i k datu převodu. |
| Rozhodnutí orgánů | Stránka Rozhodnutí: evidence usnesení a jejich přiřazení k verzím předpisu, splatnosti, klíčům vyúčtování správy a volbám v profilu. Přiřazení si pamatuje otisk schválené podoby; změněný předpis ukáže „Změněno po schválení“ a rozhodnutí jde potvrdit znovu. Chybějící nebo neplatné doložení hlásí uzávěrka. Zápis jako přílohu aplikace neukládá. |
| Historie změn | Auditní záznam změn mimo deník (vlastníci, vlastnictví, podíly na společných částech, rozhodnutí a jejich přiřazení, předpis záloh, měřidla, odečty, výsledky zúčtovatele, stav roku): kdo, kdy, stav před a po, důvod. Databáze záznam nedovolí změnit. Změny profilu SVJ a souborů s předpisem mimo aplikaci v něm nejsou. |
| Měřidla a odečty | Stránka Měřidla: evidence měřidel jednotek i domu, hromadný odečet k datu, výměna měřidla a roční spotřeba. Roční spotřeba slouží jako klíč ve vyúčtování služeb; výsledky zúčtovatele tepla se opisují ručně na stránce Vyúčtování. |
| Účetní období a archiv | Účetní období je jen kalendářní rok; hospodářský rok ani první období delší než 12 měsíců nejdou. Export deníku a dokladů pro archiv chybí a lhůty úschovy aplikace nehlídá. |
| Předpisy záloh | Hotovo: verze s platností od, pět způsobů výpočtu, zaúčtování po měsících. Mimořádná záloha podle rozhodnutí shromáždění se rozdělí na jednotky podle podílů a má vlastní splatnost. |
| Nezálohové příspěvky | Volba `prispevky: nezalohove` v profilu: předpis správy a fondu oprav jde rovnou do výnosů (649), vyúčtování správy se nedělá. Stránka Fond ze zisku zaúčtuje rozdělení výsledku minulého roku (911, neuhrazená ztráta 932) a ukáže pohyby fondu; oprava z fondu ze zisku je druh faktury (911/648) a fond nepustí do záporu. Přechod z jednoho režimu na druhý během roku aplikace neřeší a nezálohové splácení úvěru neumí. |
| Banka | Hotovo pro GPC (ABO) a přehled pohybů Raiffeisenbank (CSV). |
| Přijaté faktury | Hotovo bez příloh a bez schvalování více lidmi. Výdaj bez faktury se zaúčtuje v Bance a náhradní doklad k němu interním dokladem; odhad nákladu (dohadná položka) se po doručení faktury zruší interním dokladem. Podpisy u náhradního dokladu aplikace nevede. |
| Pokladna | Stránka Pokladna: pokladní kniha s průběžným zůstatkem, příjem hotovosti vybrané z účtu, drobný výdaj s položkou správy a hotová platba vlastníka. Pokladna nejde do minusu ani zpětně. Pokladní doklady nemají vlastní číselnou řadu příjmů a výdajů, číslují se zápisem v deníku. |
| Deník, storno, uzavřené období | Hotovo, hlídané triggery v databázi. |
| Dlužníci, úrok z prodlení, potvrzení o dluzích | Přehled, upomínka a potvrzení fungují. Dluhy jsou vedené na jednotku; dluhy prodávajícího, které na kupujícího nepřešly, jsou zvlášť pod jeho jménem. Předepsaný úrok z prodlení (311400) stránka ukazuje zvlášť a předepisuje ho tlačítkem; úrok z pozdě zaplacených částí nepočítá. Platba jde nejdřív na dluh, který vlastník určil, jinak podle splatnosti (§ 1933 OZ); pořadí úrok před jistinou (§ 1932 OZ) aplikace sama nepoužije. Odepsané dluhy se vedou po jednotkách přes všechny roky, dokud je dlužník nezaplatí. |
| Vyúčtování záloh na správu | Hotovo. Při převodu jednotky během roku jde vyúčtování (správy i služeb) rozdělit na vlastnická období, když to SVJ zvolí v profilu. |
| Vyúčtování služeb | Hotovo: klíče podle osob, jednotek, plochy, podílu, měřidel a výsledků zúčtovatele, dokument pro vlastníka. Doručení eviduje a ukáže z něj lhůty pro námitky a vyrovnání (§ 7 a 8 zákona 67/2013); námitky samotné nevede. Přeúčtování mezi službami se zadává interním dokladem na stránce Deník. |
| Ostatní výnosy | Úrok z banky, pojistné plnění, přijatou dotaci, nájemné a smluvní pokutu od dodavatele jde zaúčtovat u bankovní platby, s nabídkou otevřených položek. Smluvní pokuta dodavateli se uplatní interním dokladem a započte proti jeho faktuře; daní se po zaplacení. Pojistné plnění v roce škody jde zaúčtovat jako pohledávku nebo odhad a odhad pak nahradit oznámenou částkou. Použití dotace hlídá, kolik z ní zbývá; poměr nákladů let zadává výbor. Stránka Příjmy vlastníků rozdělí nájemné na vlastníky podle podílů k datu platby, převede podíl do fondu oprav na žádost vlastníka a vytiskne potvrzení pro jeho daňové přiznání. Uzávěrka připomene nevyčerpané dotace a staré odhady pojistného. Fotovoltaiku zvlášť neřeší. |
| Úvěr | Stránka Úvěry: podíly jednotek na jistině podle podílů, splátka jako složka měsíčního předpisu, úhrada faktury, úroky, poplatky a splátky na úvěrovém účtu, úhrada úroků z fondu oprav nebo ze záloh na úvěr k 31. 12. Vyúčtování správy ukazuje zvlášť, co zaplatil fond oprav a co zálohy na úvěr, a potvrzení o dluzích uvede nesplacený zbytek podílu. Jednorázové doplacení podílu, úpravu založeného úvěru a nezálohové splácení aplikace neumí; faktura hrazená z úvěru není vázaná na konkrétní úvěr. |
| Majetek | Stránka Majetek: evidence hmotného i nehmotného majetku, staveb a pozemků, zařazení z faktur za pořízení, rovnoměrný měsíční odpisový plán, roční odpisy, vyřazení a převzetí z počátečních stavů. Pořízení kryje fond oprav, fond ze zisku (901), nebo provozní zálohy přes odpisy ve vyúčtování správy. Uzávěrka hlídá odpisy a shodu evidence s účty, inventurní soupis má rozpis po kartách. Hranici dlouhodobého majetku aplikace nehlídá, jiné než rovnoměrné odpisy, technické zhodnocení majetku a prodej pozemku neumí. |
| Uzávěrka | Kontrolní seznam, výkazy, inventurní soupisy, daň z příjmů a návrh přílohy. Uzavření roku zaúčtuje uzávěrkové zápisy a otevře další rok z konečných zůstatků, dluhy vlastníků po položkách se splatností. Do schválení závěrky jde rok s důvodem znovu otevřít; uzavření i znovuotevření je v historii změn. Schválení závěrky aplikace neeviduje, takže po schválení zatím nenabídne opravu v běžném roce ani neupozorní, že znovuotevření jde proti § 17 odst. 7 ZoÚ. Zpráva o hospodaření zatím chybí. |
| Daň z příjmů | Uzávěrka roztřídí výnosy na nedaněné, zdaněné srážkou, nezahrnované do základu (čerpání fondu ze zisku) a zdaňované, řekne, jestli se podává přiznání, a sestaví návrh výpočtu po řádcích přiznání včetně řádků 30 a 111 u úroků z prodlení od vlastníků. Daň zaúčtuje k 31. 12. na položku správy, takže ji vyúčtování záloh na správu rozdělí mezi vlastníky. Přiznání nesestaví. U sankcí mimo úroky z prodlení od vlastníků nepozná, jestli jsou zaplacené. |
| Odměny členů orgánů a mzdy | Operace `odmena-vyboru` (stav `overit`) jde zaúčtovat interním dokladem na stránce Deník; daň a pojistné do něj účetní zadává ručně. Aplikace je nespočítá a nerozliší člena a nečlena SVJ ani rozhodný příjem. Mzdovou agendu (prohlášení k dani, registrace u ČSSZ a zdravotních pojišťoven, jednotné měsíční hlášení, přehledy o platbě) nevede. Mzdy a dohody jsou mimo první verzi. |
| Rozesílání a upozornění | Dokumenty pro vlastníky jdou rozeslat e-mailem (se souhlasem) nebo vytisknout jako dopis; aplikace eviduje odeslání, otevření, potvrzení a doručení a z doručení počítá lhůty. Přihlašovací odkaz chodí e-mailem. Upozornění pro výbor a zpracování vrácených e-mailů chybí. |
| Podklady, podpisové záznamy, role | Zatím ne. Přístup řídí seznam e-mailů, část uživatelů může jen nahlížet. |

## Zásady

- **Peníze jsou celé haléře** (`int`). Desetinná čísla s plovoucí čárkou se v účetní
  logice nepoužívají. API posílá částky taky v haléřích.
- **Podíly jsou přesné zlomky**, uložené jako čitatel a jmenovatel. Jmenovatelé
  z katastru bývají velká čísla a pro každou jednotku jiná.
- **Zaokrouhlení je pravidlo, ne vedlejší efekt.** Každá operace, která dělí částku, říká,
  na co zaokrouhluje a kam jde rozdíl. Rozdíl musí být vidět v deníku.
- **Zaúčtované se nemění.** Oprava je nový zápis s odkazem na původní a důvodem.
  Uzavřené období je jen ke čtení.
- **Každé pravidlo má zdroj.** U předpisu je to paragraf, u volby SVJ rozhodnutí orgánu
  (datum, bod zápisu), u postupu z literatury titul a strana. Pravidlo bez zdroje je jen
  návrh.
- **Blokuje se jen to, co by zkreslilo čísla.** Nevyrovnaný zápis, změnu zaúčtovaného
  zápisu, zápis do uzavřeného období, výpis, který nenavazuje na předchozí, nebo dvojí
  zaúčtování aplikace nepustí. Metodické volby, ve kterých se praxe a literatura
  rozcházejí, nechá na SVJ: postup, podle kterého dům účtuje, jde zadat, i když ho
  literatura nedoporučuje nebo ho ještě nepotvrdila účetní. Odchylku aplikace ukáže
  jednou, v kontrolním seznamu uzávěrky, s odkazem do příručky. Kdo ji posoudí, zůstane
  o tom záznam.
- **Nic nezmizí.** Nespárovaná platba, chybějící doklad nebo nevysvětlený rozdíl má vlastní
  účet a stav a blokuje uzávěrku, dokud o něm někdo nerozhodne.
- **Výstupy jde porovnat se správcem.** Salda, přehled fondu oprav a výkazy mají tvar,
  ve kterém je obvykle posílá správce, aby šly srovnat řádek po řádku.
- **Účetní logika je v backendu.** Frontend částky jen zobrazuje a sčítá. Dělit (podíly,
  zaokrouhlení) a rozhodovat, co se zaúčtuje, smí jen backend.

## Technologie

| Vrstva | Volba | Proč |
| --- | --- | --- |
| Backend | Python 3.13, FastAPI, Pydantic | doménová logika a účetní pravidla jsou čistý Python bez vazby na webový rámec |
| Databáze | PostgreSQL, SQLAlchemy 2, Alembic | transakce, omezení a triggery přímo v databázi (vyrovnanost zápisu, neměnnost, uzavřené období) |
| Frontend | React, TypeScript, Vite | |
| Přihlášení | Better Auth jako samostatná malá služba | identita a přihlášení; backend ověřuje krátkodobý JWT přes JWKS, oprávnění drží aplikace |
| Nástroje | uv (backend), pnpm (frontend a služba přihlášení) | |

Better Auth řeší identitu, ne oprávnění. Role (předseda, člen výboru, účetní, správce,
vlastník), oprávnění k podpisu a limity budou v databázi aplikace navázané na ID uživatele.
Z nich půjde vytisknout podpisový řád podle § 33a odst. 10 zákona o účetnictví.
Schválení dokladu by mělo vyžadovat čerstvé ověření (passkey nebo druhý faktor), aby
podpisový záznam v aplikaci byl průkazný podle § 33a odst. 4; jestli to stačí, potvrdí
účetní.

## Pojmy

| Pojem | Význam |
| --- | --- |
| příspěvek na správu domu a pozemku | to, co vlastník platí na správu domu; u většiny SVJ hlavně fond oprav (účet 955) |
| předpis | měsíční povinnost vlastníka zaplatit danou složku; vzniká pohledávka SVJ a závazek (záloha) vůči vlastníkovi |
| složka předpisu | jedna položka předpisu (fond oprav, teplo, voda, úklid, správa…) se způsobem výpočtu a rolí účtu |
| klíč | způsob rozdělení částky mezi jednotky: podíl na společných částech, rovným dílem na jednotku, osoby, měřidlo, plocha, pevná částka |
| vyúčtování | roční porovnání skutečných nákladů s přijatými zálohami; u služeb podle zákona 67/2013 Sb., u správy podle stanov |
| zúčtovatel | externí firma, která rozúčtuje teplo a teplou vodu podle měřidel |
| účetní případ | hospodářská událost, kterou je potřeba zaúčtovat |
| doklad | nositel náležitostí podle § 11 zákona o účetnictví; může se skládat z více záznamů |
| podklad | soubor nebo záznam, ze kterého doklad vychází (faktura, výpis, smlouva, prohlášení) |
| role účtu | význam účtu v předkontaci (`pohledavky_vlastnici`, `zalohy_dlouhodobe`…); číslo účtu určí profil SVJ |
| profil SVJ | soubor v `profiles/`, který převádí role na účty a popisuje jednotky, služby a položky správy |

## Co je otevřené

Rozhodnutí, která specifikace nechává volná nebo jen navrhuje:

1. **Metody přihlášení a provoz.** Přihlašuje se odkazem poslaným e-mailem přes
   SMTP. Zbývá rozhodnout o passkey a druhém faktoru a o tom, kde aplikace poběží.
2. **Export hlavní knihy.** Deník v databázi aplikace je zdroj pravdy. Návrh je přidat
   deterministický export do Beancountu: nezávislá kontrola zůstatků (`bean-check`,
   kontrola proti výpisům) a prohlížeč Fava pro výbor.
   Vedle toho export pro programy účetních (CSV a XLSX, Pohoda XML, Money S3 XML), import
   počátečních zůstatků a příjem faktur v ISDOC. Otevřené je, jestli knihy vede OpenSVJ,
   nebo účetní ve svém programu (viz [Výměna dat s programy účetních](01-domena.md#výměna-dat-s-programy-účetních)).
3. **Postupy, které musí potvrdit účetní.** Čerpání fondu oprav (přímo 955/321, nebo přes
   náklady), pojistné plnění, účty pro nevyjasněné položky a zaokrouhlovací rozdíl
   z vyúčtování. V katalogu mají stav `overit`. Aplikace je zaúčtuje a uzávěrka je
   připomene k posouzení.
4. **Volby SVJ dané rozhodnutím orgánů.** Klíče rozúčtování služeb, význam paušálních
   složek předpisu, zařazení revizí a kdo platí předpis za měsíc převodu jednotky. Profil
   SVJ je má mít s odkazem na rozhodnutí.
5. **Příjem pohybů z banky.** Návrh je přijímat výpisy e-mailem, číst pohyby přes API Fio
   a avíza o platbách brát jen jako předběžné pohyby, které potvrdí až výpis (viz
   [Odkud pohyby přicházejí](01-domena.md#odkud-pohyby-přicházejí)).
6. **Doručování e-mailem.** Kdy se e-mail bere jako doručený a jestli stačí jako
   písemné oznámení o změně zálohy. Na tom závisí lhůty u vyúčtování a upomínek (viz
   [Rozesílání a upozornění](01-domena.md#7-rozesílání-a-upozornění)).
