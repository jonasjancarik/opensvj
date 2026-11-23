# Plán další práce

Pořadí, ve kterém se doplňuje to, co aplikaci chybí. Přednost má správnost čísel a úplnost
účetní agendy. E-maily pro výbor přijdou až na konec, protože je zatím nikdo nevyužije.
Podrobný stav po oblastech je v tabulce
[Co z toho aplikace umí](spec/README.md#co-z-toho-aplikace-umí). Hotový bod se odsud
smaže a tabulka se upraví.

## Zásada: schválené jde změnit, ale je to vidět

Schválení (závěrky shromážděním, dokladu výborem, verze předpisu) nic nezamyká. Doklad
jde opravit i po podpisu a rok jde znovu otevřít i po schválení závěrky. U závěrky je
ale potřeba počítat se zákonem: po schválení už do uzavřených knih nesmí přibýt zápis
a znovu otevřít je jde jen do schválení, nejpozději do konce následujícího roku (§ 17
odst. 7 ZoÚ). Chyba zjištěná po schválení se běžně opraví v roce, kdy ji SVJ zjistí,
a popíše se v příloze. Po schválení proto aplikace nabídne hlavně opravu v běžném roce
a znovuotevření ukáže jako krok proti § 17 odst. 7 s výslovným upozorněním. Každá
změna schválené věci:

- se zapíše do auditního záznamu (kdo, kdy, co, proč, předchozí stav),
- schválení, kterého se týká, označí jako neplatné, protože schválení se váže k otisku
  (SHA-256) konkrétní verze,
- je vidět na stránce, kde se schválená věc zobrazuje: jasné upozornění „Změněno po
  schválení“ s datem, autorem a důvodem a s odkazem na to, co se změnilo.

Auditní záznam proto vzniká dřív než schvalování a podpisy, které na něm stojí.

## 1. Opravy správnosti

- Daň z příjmů: čerpání fondu ze zisku (648) nepočítat mezi zdaňované výnosy
  (§ 23 odst. 4 písm. e) a g) ZDP); odlišit předepsané a zaplacené sankce
  (řádky 30 a 111 přiznání); operace pro předpis daně (591/341) a pro zvýšení příspěvků
  o daň.
- Dlužníci: ukázat předepsaný úrok z prodlení (311400); přiřazovat platbu k dluhu, který
  určil vlastník, a jinak podle § 1933 OZ; odepsané dluhy vést na podrozvaze.

## 2. Základy, na kterých stojí další oblasti

- **Auditní záznam** obecně pro změny v aplikaci (vlastníci, rozhodnutí, předpisy, uzávěrka,
  znovuotevření roku) a upozornění „Změněno po schválení“ podle zásady výše.
- **Podíly s platností v čase:** změna podílů prohlášením vlastníka během roku, předpisy
  od data změny, součet podílů vždy přesně 1. Potřebují ji úvěr, nájemné i vyúčtování.
- **Převod jednotky uprostřed měsíce:** vyúčtování na dvě vlastnická období a potvrzení
  o dluzích k datu převodu.

## 3. Účetní oblasti

- **Úvěr:** výpočet podílů jednotek na jistině, splátka jako složka měsíčního předpisu,
  ve vyúčtování záloh na správu odlišit náklady kryté zálohou na úvěr (955300) od běžného
  fondu oprav, v potvrzení o dluzích při prodeji ukázat nesplacený zbytek podílu na úvěru.
- **Majetek:** evidence hmotného i nehmotného majetku, odpisový plán, výpočet a zaúčtování
  odpisů, krytí přes fond 911.
- **Nezálohové příspěvky:** předpis a účtování příspěvků jako výnosů, fond ze zisku 911.
- **Ostatní výnosy:** smluvní pokuta dodavateli v katalogu; pohledávka z pojistného plnění
  v roce škody a dohad; rozpouštění dotace do více let; podíly vlastníků na nájemném
  a potvrzení pro jejich daňové přiznání.
- **Vyúčtování služeb:** evidence námitek vlastníků a jejich vyřízení; přeúčtování mezi
  službami jako operace místo ručního zápisu.
- **Účetní období a archiv:** hospodářský rok a první období delší než 12 měsíců; export
  deníku, hlavní knihy a dokladů pro archiv (PDF a CSV); hlídání lhůt úschovy.

## 4. Doklady, schvalování a závěrka

- **Podklady a přílohy:** soubory k fakturám, rozhodnutím (zápisy ze shromáždění)
  a ostatním dokladům, neměnné se SHA-256; stav podkladu `chybi → vyzadan → doplnen`
  nebo `nahrazen`.
- **Role a podpisové záznamy:** role v databázi aplikace (předseda, člen výboru, účetní,
  správce), podpisový záznam vázaný k otisku verze dokladu a podkladů, schvalování více
  lidmi nad nastavenou částku, kdo žádá o proplacení, nesmí ho sám schválit; tisk
  podpisového řádu (§ 33a odst. 10). Výdaj bez faktury proplacený členovi výboru
  s náhradním dokladem.
- **Zpráva o hospodaření** a **evidence schválení závěrky** (orgán, datum, rozhodnutí,
  otisk schválené verze). Po schválení oprava v běžném roce: operace v katalogu (stav
  `overit`, účet potvrdí účetní), odkaz na opravovaný rok a bod do přílohy. Znovuotevření
  schváleného roku zůstane možné podle zásady výše.
- **Dobropisy** k přijatým fakturám.
- **Další formáty výpisů:** camt.053 a MT940.

## 5. Až nakonec

- Upozornění pro výbor e-mailem (blížící se lhůty, nové faktury, dluhy).
- Automatický zápis vrácených e-mailů (bounce) do zásilek.
- Export do Beancountu a pro programy účetních.
