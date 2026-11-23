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
a dohody o provedení práce, majetek s odpisy, cizí měny, DPH a více domů v jedné
instalaci. Datový model je nesmí znemožnit, ale nemusí je řešit.

### Co z toho aplikace umí

| Oblast | Stav |
| --- | --- |
| Jednotky, plochy, podíly, počty osob | V profilu SVJ (YAML). Podíly zatím nemají platnost v čase. |
| Vlastníci | Osoby a vlastnictví jednotek s platností od–do, stránka Vlastníci. Jméno a adresa se tisknou v upomínce, oznámení o zálohách, vyúčtování a potvrzení o dluzích; účet vlastníka pomáhá párovat platby. Dluhy jdou s jednotkou; ty, které na kupujícího nepřešly, jde při převodu přesunout na prodávajícího a jeho pozdější platbu zaúčtovat v Bance. Kdo platí předpis za měsíc převodu, určuje profil. |
| Rozhodnutí orgánů | Stránka Rozhodnutí: evidence usnesení a jejich přiřazení k verzím předpisu, splatnosti, klíčům vyúčtování správy a volbám v profilu. Chybějící doložení hlásí uzávěrka. Zápis jako přílohu aplikace neukládá. |
| Měřidla a odečty | Stránka Měřidla: evidence měřidel jednotek i domu, hromadný odečet k datu, výměna měřidla a roční spotřeba. Roční spotřeba slouží jako klíč ve vyúčtování služeb; výsledky zúčtovatele tepla se opisují ručně na stránce Vyúčtování. |
| Účetní období a archiv | Účetní období je jen kalendářní rok; hospodářský rok ani první období delší než 12 měsíců nejdou. Export deníku a dokladů pro archiv chybí a lhůty úschovy aplikace nehlídá. |
| Předpisy záloh | Hotovo: verze s platností od, pět způsobů výpočtu, zaúčtování po měsících. |
| Nezálohové příspěvky | Zatím ne. Volba `prispevky: nezalohove` v profilu mění jen text přílohy; fond ze zisku 911 aplikace nepodporuje. |
| Banka | Hotovo pro GPC (ABO) a přehled pohybů Raiffeisenbank (CSV). |
| Přijaté faktury | Hotovo bez příloh a bez schvalování více lidmi. |
| Deník, storno, uzavřené období | Hotovo, hlídané triggery v databázi. |
| Dlužníci, úrok z prodlení, potvrzení o dluzích | Přehled, upomínka a potvrzení fungují. Dluhy jsou vedené na jednotku; dluhy prodávajícího, které na kupujícího nepřešly, jsou zvlášť pod jeho jménem. Předepsaný úrok z prodlení (311400) stránka ukazuje zvlášť a předepisuje ho tlačítkem; úrok z pozdě zaplacených částí nepočítá. Platby se přiřazují podle splatnosti, bez ohledu na upomínky a na to, který dluh určil vlastník (§ 1933 OZ). Odepsané dluhy se nesledují na podrozvaze. |
| Vyúčtování záloh na správu | Hotovo. |
| Vyúčtování služeb | Hotovo: klíče podle osob, jednotek, plochy, podílu, měřidel a výsledků zúčtovatele, dokument pro vlastníka. Doručení eviduje a ukáže z něj lhůty pro námitky a vyrovnání (§ 7 a 8 zákona 67/2013); námitky samotné nevede. Přeúčtování mezi službami se zadává ručně. |
| Ostatní výnosy | Úrok z banky, úrok z prodlení, pojistné plnění, dotace a nájemné ze společných částí mají operace v katalogu. Smluvní pokuta dodavateli v katalogu chybí. Pohledávku z pojistného plnění v roce škody ani dohad aplikace sama nenabídne. Rozpouštění dotace do více let se dělí ručně. Podíly vlastníků na nájemném aplikace nespočítá a potvrzení pro jejich daňové přiznání nevystaví. Fotovoltaiku zvlášť neřeší. |
| Úvěr | Operace v katalogu jako návrh. Vyúčtování záloh na správu zatím neodliší náklady kryté zálohou na úvěr (955300) od běžného fondu oprav a potvrzení o dluzích při prodeji jednotky neukazuje nesplacený zbytek podílu na úvěru. Podíly jednotek na jistině se počítají ručně a splátka se sama nepřidá do měsíčního předpisu. |
| Majetek | Operace v katalogu jako návrh. Evidence majetku, odpisový plán a výpočet odpisů chybí, odpis se zadává ručně. Nehmotný majetek a krytí přes fond 911 nejsou. |
| Uzávěrka | Kontrolní seznam, výkazy, inventurní soupisy, daň z příjmů a návrh přílohy. Uzavření roku zaúčtuje uzávěrkové zápisy a otevře další rok z konečných zůstatků, dluhy vlastníků po položkách se splatností. Do schválení závěrky jde rok znovu otevřít. Schválení závěrky aplikace neeviduje, takže po schválení zatím nenabídne opravu v běžném roce ani neupozorní, že znovuotevření jde proti § 17 odst. 7 ZoÚ. Zpráva o hospodaření zatím chybí. |
| Daň z příjmů | Uzávěrka roztřídí výnosy na nedaněné, zdaněné srážkou, nezahrnované do základu (čerpání fondu ze zisku) a zdaňované, řekne, jestli se podává přiznání, a sestaví návrh výpočtu po řádcích přiznání včetně řádků 30 a 111 u úroků z prodlení od vlastníků. Daň zaúčtuje k 31. 12. na položku správy, takže ji vyúčtování záloh na správu rozdělí mezi vlastníky. Přiznání nesestaví. U sankcí mimo úroky z prodlení od vlastníků nepozná, jestli jsou zaplacené. |
| Odměny členů orgánů a mzdy | Operace `odmena-vyboru` v katalogu (stav `overit`); daň a pojistné zadává účetní ručně. Aplikace je nespočítá a nerozliší člena a nečlena SVJ ani rozhodný příjem. Mzdovou agendu (prohlášení k dani, registrace u ČSSZ a zdravotních pojišťoven, jednotné měsíční hlášení, přehledy o platbě) nevede. Mzdy a dohody jsou mimo první verzi. |
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
