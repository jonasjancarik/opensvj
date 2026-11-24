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

Auditní záznam (stránka Historie změn) a upozornění „Změněno po schválení“ u předpisu
záloh už aplikace má. Schvalování dokladů, podpisy a schválení závěrky na nich stavějí.

## 1. Účetní oblasti

- **Nezálohové příspěvky:** předpis a účtování příspěvků jako výnosů, fond ze zisku 911.
- **Ostatní výnosy:** smluvní pokuta dodavateli v katalogu; pohledávka z pojistného plnění
  v roce škody a dohad; rozpouštění dotace do více let; podíly vlastníků na nájemném
  a potvrzení pro jejich daňové přiznání.
- **Vyúčtování služeb:** evidence námitek vlastníků a jejich vyřízení; přeúčtování mezi
  službami jako operace místo ručního zápisu.
- **Účetní období a archiv:** hospodářský rok a první období delší než 12 měsíců; export
  deníku, hlavní knihy a dokladů pro archiv (PDF a CSV); hlídání lhůt úschovy.

## 2. Doklady, schvalování a závěrka

- **Podklady a přílohy:** soubory k fakturám, rozhodnutím (zápisy ze shromáždění)
  a ostatním dokladům, neměnné se SHA-256; stav podkladu `chybi → vyzadan → doplnen`
  nebo `nahrazen`.
- **Role a podpisové záznamy:** role v databázi aplikace (předseda, člen výboru, účetní,
  správce), podpisový záznam vázaný k otisku verze dokladu a podkladů, schvalování více
  lidmi nad nastavenou částku, kdo žádá o proplacení, nesmí ho sám schválit; tisk
  podpisového řádu (§ 33a odst. 10). Podpisy u náhradního dokladu k výdaji bez faktury
  a u pokladních dokladů, které dostanou vlastní číselné řady příjmů a výdajů.
- **Zpráva o hospodaření** a **evidence schválení závěrky** (orgán, datum, rozhodnutí,
  otisk schválené verze). Po schválení oprava v běžném roce: operace v katalogu (stav
  `overit`, účet potvrdí účetní), odkaz na opravovaný rok a bod do přílohy. Znovuotevření
  schváleného roku zůstane možné podle zásady výše.
- **Dobropisy** k přijatým fakturám.
- **Další formáty výpisů:** camt.053 a MT940.

## 3. Až nakonec

- Upozornění pro výbor e-mailem (blížící se lhůty, nové faktury, dluhy).
- Automatický zápis vrácených e-mailů (bounce) do zásilek.
- Export do Beancountu a pro programy účetních.
