# Doménový model

Model má pět oblastí: **dům a lidé**, **předpisy**, **banka**, **doklady** a
**účetnictví**. Vyúčtování a uzávěrka nad nimi jen počítají a výsledek zapisují zpět jako
zápisy do deníku. Rozesílání z nich připravuje dokumenty a upozornění a eviduje, komu
a kdy odešly.

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
- Podíl se může změnit (změna prohlášení vlastníka), proto má platnost. Podíly z profilu
  platí do první změny; změna je `zmena_podilu(plati_od, podily, zdroj)` s podíly všech
  jednotek (zápis jako v prohlášení, „718/8600“), jejichž součet je přesně 1. Platí do
  další změny.
- Předpis i vyúčtování počítají po celých měsících: měsíc má podíly platné k jeho prvnímu
  dni, takže změna od 15. 7. se v předpisu projeví od srpna. Roční vyúčtování dělí náklady
  podle průměru podílů za měsíce roku (součet zůstává 1). Změnu, která by zasáhla
  zaúčtované předpisy nebo uzavřený rok, aplikace odmítne; v jednom měsíci smí začít platit
  jen jedna změna.

### Osoba

Fyzická nebo právnická osoba: jméno, adresa pro doručování, e-mail, souhlas s doručováním
e-mailem (oddíl 7) a účet pro vracení přeplatků. Osobní údaje jsou oddělené od účetních dat, aby šlo plnit GDPR, třeba smazat
kontakty po uplynutí archivační doby (§ 31 zákona o účetnictví).

### Vlastnictvi

`Vlastnictvi(jednotka, osoby[], podily_osob, plati_od, plati_do, zdroj)`

- Spoluvlastníci a společné jmění manželů jsou jedna položka s více osobami. Vůči SVJ ručí
  společně a nerozdílně a mají jeden hlas, proto předpis a saldo vznikají **na jednotku**,
  ne na osobu.
- Období vlastnictví jedné jednotky se nesmějí překrývat ani mít mezeru.
- Při změně vlastníka rozhoduje den zápisu do katastru. Kdo platí předpis za měsíc
  převodu, je volba SVJ v profilu (`predpis_mesice_prevodu`): dosavadní vlastník
  (`dosavadni`, výchozí), nebo nový vlastník (`novy`). Rozdělení poměrně podle dnů
  aplikace nenabízí.
- **Dluhy jdou s jednotkou.** Dluhy převodce na příspěvcích a zálohách přecházejí na
  nabyvatele, pokud o nich věděl nebo mohl vědět, a převodce za ně ručí (§ 1186 odst. 2
  OZ). Saldo se proto vede dál na jednotku a převodem se nijak nedělí. Dluh, který na
  nabyvatele nepřešel, se přesune na převodce operací `dluh-zustava-prevodci`: řádek
  pohledávky dostane jméno převodce v dimenzi `protistrana`, takže ze salda současného
  vlastníka zmizí a dál se vymáhá po převodci. Jeho pozdější platbu zaúčtuje
  `uhrada-dluhu-drivejsiho`. Přesun není automatika; aplikace jen navrhne položky podle
  data převodu a volby v profilu a výbor vybere, co skutečně nepřešlo, typicky podle
  potvrzení o dluzích (§ 1186 odst. 3 OZ).
- Potvrzení o dluzích jde vydat i k datu převodu (poslední den vlastnictví převodce,
  nejpozději dnes): bere jen zápisy s datem do toho dne a z měsíčních záloh jen ty, které
  podle `predpis_mesice_prevodu` platil převodce. Jde převodci, i když už jednotku
  nevlastní.

### OsobyRozhodne

`OsobyRozhodne(jednotka, pocet, plati_od, plati_do, zdroj)` pro klíče podle § 5 zákona
67/2013 Sb. Počítají se osoby, u kterých lze čekat, že budou jednotku užívat déle než
2 měsíce v zúčtovacím období (§ 2 odst. 1 písm. g)). Pro rozúčtování se počet přepočte na
osobo-měsíce; jak zaokrouhlit načaté měsíce, je volba SVJ.

### Meridlo a Odecet

`Meridlo(jednotka nebo dům, druh, vyrobni_cislo, osazeno_od, odstraneno_do)` a
`Odecet(meridlo, datum, stav, zdroj)`. Výměna měřidla jedno uzavře a druhé otevře;
spotřeba v roce je součet obou.

**V aplikaci:** stránka Měřidla, tabulky `meridlo` a `odecet` (osobní údaje ani deník se
jich netýkají). Druhy jsou studená a teplá voda, teplo, indikátor topných nákladů,
elektřina a plyn. Stav s časem neklesá a jeden den má nejvýš jeden odečet. Výměna zapíše
konečný stav starého měřidla a počáteční stav nového ve stejný den; nové si pamatuje,
které nahradilo. Roční spotřeba bere odečet nejblíž 31. 12. předchozího roku (nebo dni
osazení) a nejblíž 31. 12. roku (nebo dni odstranění), oba nejvýš 31 dní vedle; bez nich
spotřebu nespočítá. Roční spotřeba slouží jako klíč `meridla` ve vyúčtování služeb.

Pro teplo a teplou vodu v první verzi stačí **převzít výsledky zúčtovatele po
jednotkách** (`VysledekZuctovatele(rok, sluzba, jednotka, castka, zdroj)`), ne počítat
rozúčtování podle vyhlášky 269/2015 Sb.

### Rozhodnuti

`Rozhodnuti(organ, datum, bod, text, priloha)`: usnesení shromáždění nebo výboru. Odkazuje
na něj každá složka předpisu, klíč vyúčtování a volba v profilu. Bez odkazu se uloží jako
„bez doloženého rozhodnutí“ a ukáže se mezi upozorněními.

**V aplikaci:** stránka Rozhodnutí, tabulky `rozhodnuti` a `rozhodnuti_pro`. Orgánem je
shromáždění, shromáždění per rollam, výbor nebo předseda společenství. Přílohu (zápis)
aplikace zatím neukládá, jen text, kde je uložený. Rozhodnutí se přiřazuje k **verzi
předpisu** jako celku, ne ke každé složce zvlášť, protože shromáždění obvykle schvaluje
celý předpis najednou. Dál se přiřazuje ke splatnosti záloh, ke klíči každé položky
vyúčtování správy a k volbám `predpis_mesice_prevodu` a `prispevky` z profilu. Přiřazení
je v databázi, ne v profilu, takže ho jde měnit v rozhraní. Klíč položky obsahuje
zvolenou hodnotu (`klic-spravy:SPRAVA:jednotka`); po změně profilu proto položka čeká na
nové rozhodnutí. Kontrolní seznam uzávěrky má bod „Výše záloh, klíče a volby mají
doložené rozhodnutí“ s verzemi předpisu, které v roce platily. Klíče vyúčtování služeb
přibudou s vyúčtováním služeb.

Přiřazení (`rozhodnuti_pro.otisk`) si pamatuje SHA-256 schválené podoby položky: u verze
předpisu kanonický JSON složek, pevných částek a počtů osob (bez podkladu), u ostatních
položek klíč, který zvolenou hodnotu už obsahuje. Když se verze po schválení změní, otisk
nesedí a schválení neplatí: kontrola v uzávěrce ho počítá jako nedoložené a rozhraní
ukáže „Změněno po schválení“ s poslední změnou z auditního záznamu. Schválený předpis jde
změnit nebo smazat jen s důvodem. Opětovné přiřazení téhož rozhodnutí uloží nový otisk.
Při posunu data verze jde přiřazení s ní, s původním otiskem.

### Auditní záznam

`auditni_zaznam(kdy, transakce, kdo, jmeno, druh, klic, akce, nazev, duvod, pred, po)`:
změny údajů mimo deník. Zachytí je posluchač sezení SQLAlchemy po každém flush a zapíše
při commitu jeden řádek za věc a transakci (stav před prvním a po posledním zápisu); co
vzniklo a zaniklo v jedné transakci, se nezapíše. Sledované jsou `osoba`, `vlastnictvi`
(i se seznamem vlastníků a podílů), `meridlo`, `odecet`, `rozhodnuti`, `rozhodnuti_pro`,
`verze_predpisu`, `zmena_podilu`, `vysledek_zuctovatele` a `obdobi`. Kdo změnu udělal, bere aplikace
z přihlášeného uživatele, důvod z `audit.duvod()`. Trigger nedovolí záznam změnit ani
smazat. Rozepsané formuláře, odškrtnutí uzávěrky (má vlastní záznam), naučená párování
plateb a odeslané dokumenty se nesledují.

**V aplikaci:** SVJ, jednotky (označení, plocha, podíl) a služby jsou v profilu SVJ
(`profiles/<id>.yaml`); podíl zatím nemá platnost v čase. Počty osob jsou u verze předpisu.
Osoby a vlastnictví jsou v databázi (stránka Vlastníci). Nové vlastnictví po posledním
zapsaném ho uzavře den před svým začátkem, takže mezera nevznikne; překryv odmítne
i databáze. Smazat jde jen první nebo poslední záznam jednotky. Spoluvlastnické podíly osob
jsou nepovinné a musí dát celek. Souhlas s doručováním e-mailem se ukládá s datem. Potvrzení
o dluzích aplikace vydá na jednotku, jen s jménem vlastníka. Dluhy, které při
převodu zůstávají prodávajícímu, se zapisují u záznamu kupujícího v historii vlastnictví
(tlačítko Dluhy při převodu); jeden převod jde zaúčtovat jednou, oprava je storno
v deníku. Jméno dřívějšího vlastníka u počátečních stavů je pořád jen text.

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

### Uver

`Uver(nazev, cislo_uctu, jistina, rozhodnuti, predepsano_dne, prvni_splatka,
pocet_splatek, uroky_hradi, podily)`

- Jistina se rozdělí na jednotky podle podílů platných v den předpisu, metodou největšího
  zbytku po celých korunách (u jistiny v haléřích na haléře). Podíly se uloží s úvěrem,
  takže pozdější změna podílů splátky nemění.
- Celý podíl se předepíše jedním zápisem (`uver-predpis-mimoradnych-zaloh`, 378100 /
  955300). Splátka jednotky je podíl dělený počtem splátek zaokrouhlený nahoru na koruny,
  poslední splátka je zbytek a po splacení podílu se už nepředepisuje. V měsíčním předpisu
  je to složka s kódem `UVER-<id>` a rolí `pohledavky_uver` (311 / 378).
- Všechny řádky úvěru nesou kód `UVER-<id>` v dimenzi služby, takže zůstatky jdou sečíst po
  úvěru i po jednotce přes všechny roky. Párovací symbol se nepoužívá, aby šly stornovat
  jednotlivé měsíční předpisy.
- První splátka musí být v měsíci, jehož předpis ještě není zaúčtovaný, a rozhodnutí musí
  být rozhodnutím shromáždění. Předpis podílů nejde stornovat, když na něj navazuje
  jiný platný zápis se stejným kódem (splátka, úroky, úhrada faktury).
- Faktura druhu `UVER` se čerpá přímo ze záloh na úvěr (`cerpani-zalohy-na-uver`,
  955300 / 321), stejně jako oprava z fondu oprav. Banka ji zaplatí z úvěru (321 / 951).
- Úroky jsou náklad (544100) a poplatky ostatní náklad položky správy. Když úroky podle
  rozhodnutí platí fond oprav nebo zálohy na úvěr, `uver-kryti-uroku` je k 31. 12. pokryje
  (955100 nebo 955300 / 649400) a vyúčtování správy je pak mezi nezahrnutými náklady nemá.

### Saldo

Saldo jednotky = předpisy + výsledky vyúčtování + ostatní pohledávky − přiřazené platby.
Počítá se **z deníku** (řádky rolí pohledávek za vlastníky s dimenzí jednotky), ne
zvlášť, aby nevznikla druhá evidence.

Na který dluh se platba započte: dlužník může při platbě určit, na který dluh plní. Když
nic neurčí, započte se podle § 1933 odst. 1 OZ nejdřív na dluh, o jehož splnění už byl
upomenut, jinak na nejméně zajištěný a při stejném zajištění na nejdříve splatný. U jednoho
dluhu se platba započte nejdřív na náklady, pak na úroky z prodlení a pak na jistinu
(§ 1932 OZ).

**V aplikaci:** výchozí předpis je v `profiles/<id>-predpisy.yaml`. Další verze se zadávají
na stránce Předpisy (tabulka `verze_predpisu`); verze z aplikace se stejným `plati_od`
nahradí verzi ze souboru. Verzi, která by zasáhla už zaúčtovaný měsíc, nejde změnit ani
smazat. Splatnost a poznámka zůstávají v souboru. Předpis se zaúčtuje na stránce
Předpisy po měsících. Saldo se počítá z deníku. Na stránce Dlužníci se platby započítávají
na dluh, který vlastník určil (sloupec `RadekZapisu.urceno_na` u platby odkazuje na řádek,
kterým dluh vznikl), a jinak na nejdřív splatné dluhy: nejdřív zůstatky z minulých let,
pak měsíční zálohy. Upomínka obsahuje všechny dluhy po splatnosti, takže pořadí podle
upomenutí dává totéž. Pořadí náklady, úrok, jistina (§ 1932 OZ) aplikace sama
nepoužije: platba zaúčtovaná jako úhrada předpisu jde vždy na zálohy. Úrok z prodlení
(nařízení vlády 351/2013 Sb.) se počítá do přehledu a upomínky; zaúčtuje se, až ho SVJ
skutečně požaduje (tlačítko na stránce Dlužníci, předpis k dnešku na 311400). Po předpisu
se počítá jen za dobu potom. Předpis i saldo jsou zatím na jednotku, ne na vlastnické období.

**Mimořádná záloha** (`mimoradna-zaloha`) je jednorázový příspěvek do fondu oprav podle
rozhodnutí shromáždění (§ 1180 odst. 1 OZ). Celková částka domu se rozdělí na jednotky
podle podílů na společných částech platných v den předpisu metodou největšího zbytku.
Předpis je jeden zápis (doklad `PR`) s řádkem za jednotku; každý řádek nese splatnost,
kterou určilo shromáždění (`RadekZapisu.splatnost`), a v dlužnících je samostatný dluh.
Rozhodnutí musí být rozhodnutí shromáždění ze dne předpisu nebo dřívějšího a jeho popis
je v popisu zápisu. Splatnost nesmí být dřív než den předpisu.

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

### Odkud pohyby přicházejí

Návrh. Dnes se výpis nahrává ručně. Další zdroje podle spolehlivosti:

1. **Výpis e-mailem.** Banka posílá denní nebo měsíční výpis ve zvoleném formátu (GPC/ABO,
   CAMT.053) na adresu SVJ v aplikaci. Výpis má zůstatky i čísla transakcí a projde stejným
   importem jako nahraný soubor. Které banky to umějí a v jakém formátu, je potřeba ověřit.
2. **API banky.** Fio dává klientům token k API zdarma a vrací plnohodnotné pohyby se
   zůstatky. Firemní API dalších bank a agregátory PSD2 mají jiné podmínky a obvykle stojí
   peníze.
3. **Avízo o platbě e-mailem.** Banka pošle upozornění na každou příchozí platbu a aplikace
   z něj přečte částku, datum, VS, protiúčet a zprávu. Přehled o platbách je tak skoro
   okamžitý, ale avízo nemá zůstatek, často ani číslo transakce, může se ztratit a jeho
   podobu banka mění bez ohlášení. Čtení se proto píše pro každou banku zvlášť.

Avízo vytvoří **předběžný pohyb**, ne `BankovniPohyb`. Předběžný pohyb jde spárovat
a ukázat v saldu vlastníka jako přijatou platbu, ale nezaúčtuje se. Po importu výpisu se
připojí k odpovídajícímu pohybu (účet, datum, částka, VS, protiúčet) a návrh párování
přejde na něj. Předběžný pohyb, ke kterému se do konce měsíce nenajde pohyb ve výpisu,
uzávěrka měsíce připomene.

E-mail na adresu SVJ může poslat kdokoli. Aplikace přijme výpis i avízo jen od domény
banky s platným SPF, DKIM a DMARC a adresa má nehádatelnou část. Přijatý e-mail se uloží
jako neměnný podklad se SHA-256 stejně jako nahraný výpis.

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
jednotka podle VS, účtu vlastníka nebo částky předpisu a naučené zaúčtování podle dřívější platby ze
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
`PR` předpisy, `PS` počáteční stavy, `VY` vyúčtování, `UZ` uzávěrkové operace,
`PD` pokladní doklady.

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

Výdaj bez dokladu od dodavatele má dva kroky (`vydaj-bez-faktury`): platba v Bance jde na
nevyjasněné výdaje, náhradní doklad interním dokladem přeúčtuje částku na náklad
s položkou správy. Dohadná položka (`dohadna-polozka`) se po doručení faktury rozpustí
proti nákladu, faktura se pak zaúčtuje běžně. Náhradní doklad ani rozpuštění nesmí být
vyšší než zůstatek nevyjasněných výdajů nebo dohadných položek k danému dni.

Pokladna: výběr z účtu jde v Bance na peníze na cestě (`pokladna-vyber`, krok `vyber`),
příjmový pokladní doklad je převede do pokladny (krok `prijem`) a nesmí být vyšší než
jejich zůstatek k danému dni. Výdaj (`pokladna-vydaj`) nese položku správy, aby ho
vyúčtování záloh na správu započítalo, a nesmí snížit zůstatek pokladny pod nulu v den
výdaje ani v žádný pozdější den roku. Hotová platba vlastníka
(`pokladna-platba-vlastnika`) snižuje dluh jednotky jako platba na účet. Pokladní doklady
mají řadu `PD`, ale zatím bez vlastního číslování příjmů a výdajů.

## 5. Účetnictví

### Obdobi

`Obdobi(rok, stav)`: `otevrene → v_uzaverce → uzavrene`. Do uzavřeného období nejde zapsat
nic. Měsíce mají jen informativní kontrolu (výpisy a předpisy), zamyká se celý rok.
Aplikace zatím používá jen `otevrene` a `uzavrene`; znovuotevření vrací rok do `otevrene`.
Další rok jde založit dřív, než je předchozí uzavřený, aby se v lednu dalo účtovat.

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

### Výměna dat s programy účetních

Návrh. Účetní, kteří SVJ vedou, mají většinou vlastní program (Pohoda, Money S3, ABRA
Flexi a jiné). Jednotný český standard pro předání účetního deníku neexistuje, každý
program má vlastní formát. Export proto vychází z rolí účtů: profil SVJ určí účtový
rozvrh účetní a analytiky se složí z dimenzí řádků.

Rozhodnout je potřeba, kde se knihy vedou:

1. **Knihy vede OpenSVJ.** Účetní deník kontroluje a dělá závěrku. Stačí čitelný export
   deníku, hlavní knihy, předvahy a saldokonta vlastníků a dodavatelů (CSV a XLSX).
2. **Knihy vede účetní ve svém programu.** OpenSVJ připraví předpisy, párování plateb
   a vyúčtování a předá je jako doklady. Export pak musí:
   - jít opakovat bez zdvojení: doklad má stálé číslo a exportuje se po dávkách od
     poslední předané,
   - opravu předat jako storno a nový doklad, nikdy jako změnu už předaného dokladu,
   - počítat s tím, že změny udělané v programu účetní se do OpenSVJ nevrátí. Uzavřený
     rok se proto porovná podle předvahy z obou stran.

Formáty podle pořadí užitku:

| Formát | Směr | Obsah |
| --- | --- | --- |
| CSV a XLSX | export | deník, hlavní kniha, předvaha, saldokonto |
| CSV předvahy a saldokonta | import | počáteční zůstatky a otevřené pohledávky a závazky při přechodu z jiného programu |
| Pohoda XML | export | interní doklady s rozúčtováním MD/D, bankovní doklady, přijaté faktury, adresář |
| ISDOC | import | přijaté faktury z PDF s vloženým ISDOC nebo ze samostatného souboru jako strukturovaný podklad |
| Money S3 XML | export | stejné typy dokladů jako u Pohody |

Bankovní doklad se v programu účetní dá spárovat s výpisem, který si účetní naimportuje
z banky. Export proto nese číslo výpisu a klíč pohybu. Před prací na formátech pro konkrétní
programy je potřeba ověřit s několika účetními SVJ, co opravdu používají.

### Majetek

`Majetek(nazev, inventarni_cislo, druh, zarazeno, cena, doba_mesicu, kryti, prevzato_k,
opravky_prevzate)`

- Druh určí účty: movitá věc 022/082, stavba nebo jednotka 021/081, pozemek 031 (neodepisuje
  se), nehmotný majetek 013/073; pořizuje se na 042, nehmotný na 041.
- Zařazení (`majetek-zarazeni`) převede cenu z pořizování na majetek; víc, než kolik je na
  pořizování nezařazeno, zařadit nejde. Kryje-li pořízení fond oprav nebo fond ze zisku,
  zařazení zároveň zaúčtuje 955 nebo 911 / 901.
- Odpisy jsou rovnoměrné po měsících od měsíce po zařazení, kumulativně zaokrouhlené na
  celé koruny, poslední měsíc dorovná cenu. Roční odpis (`majetek-odpisy`) je jeden zápis
  na kartu a rok k 31. 12.: 551 / oprávky, u fondu 901 / fond a u fondu oprav ještě 955 /
  649, takže výsledek je nulový a fond oprav se sníží jen jednou. U provozních záloh nese
  náklad 551 kód položky správy a jde do vyúčtování.
- Řádky karty nesou kód `MAJ-<id>` v dimenzi služby (kromě nákladu s položkou). Zařazení
  nejde stornovat, když na něj navazuje odpis nebo vyřazení.
- Převzatý majetek nemá zápis o zařazení; zůstatková cena k převzetí se odepisuje ve
  zbývajících měsících plánu.
- Vyřazení (`majetek-vyrazeni`) doodepíše zůstatkovou cenu a odúčtuje majetek proti
  oprávkám; předtím musí být zaúčtované odpisy minulých let.
- Uzávěrka porovná součet karet s účty majetku a oprávek.

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
Bod 8 je hotový: tlačítko Uzavřít rok jde použít po 31. 12., když uzávěrka nehlásí nic
chybějícího a ruční body jsou odškrtnuté. Zaúčtuje `uzavreni-vysledkovych` (5 a 6 na 963),
`uzavreni-rozvahovych` (rozvahové účty i s rozpisem na 962) a k 1. 1. dalšího roku
počáteční stavy proti 961; výsledek roku se otevře na 931. Dluhy současných vlastníků
se převádějí po položkách se splatností (sloupec `RadekZapisu.splatnost`) a platby se
přitom započítávají jen v rámci účtu, takže zůstatek každého účtu navazuje. Do schválení
závěrky jde rok znovu otevřít s důvodem; uzávěrkové zápisy i počáteční stavy dalšího
roku se stornují. Přehledy a výkazy roku uzávěrkové zápisy nevidí, deník ano.
Zpráva o hospodaření a evidence schválení závěrky zatím chybí. Po schválení bude aplikace
nabízet opravu v běžném roce: opravný zápis do roku, kdy se chyba zjistila, s odkazem na
opravovaný rok a s bodem do přílohy. Znovuotevření schváleného roku zůstane možné, ale
s upozorněním, že jde proti § 17 odst. 7 ZoÚ, se zápisem do auditního záznamu a se
zneplatněním schválení.
První rok se otevírá zadáním počátečních stavů.

## 6. Vyúčtování

### Vyúčtování záloh na správu

Náklady roku přiřazené k položce správy (pojištění, správa, revize, drobné opravy) se
rozdělí na jednotky podle klíče položky v profilu, metodou největšího zbytku na haléře.
Porovnají se s předepsanými zálohami jednotky na tutéž položku a rozdíl je nedoplatek
nebo přeplatek jednotky. Výnosy přiřazené k položce (pojistné plnění na opravu, dotace na
úroky) náklady té položky snižují. Nedoplatek je splatný 30. 4. dalšího roku, stejně jako
u služeb (§ 7 zákona 67/2013), pokud stanovy neurčí jinak.

Opravy hrazené z fondu oprav a ze záloh na úvěr a úroky z úvěru pokryté z dlouhodobých
záloh se do vyúčtování nezahrnují, ale vypíšou se zvlášť podle zdroje.

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

**V aplikaci:** výpočet a zaúčtování jsou hotové, stránka Vyúčtování (záložka Služby)
a zápis `vyuctovani-sluzeb`. Proti návrhu výše se liší:

- Klíč služby je v profilu (`klic`): `osoby` (výchozí, osobo-měsíce podle počtu osob
  v předpisu), `jednotka`, `plocha`, `podil`, `meridla` (roční spotřeba z odečtů měřidel
  druhu `meridlo`) a `zuctovatel` (náklad jednotky opsaný z rozúčtování zúčtovatele, tabulka
  `vysledek_zuctovatele`). Klíče se dokládají rozhodnutím na stránce Rozhodnutí.
- Náklady se dělí přesně na haléře metodou největších zbytků, takže součet nákladů jednotek
  vždy dá náklady služby. Zaokrouhlení na koruny ani operace `vyuctovani-zaokrouhleni`
  proto nejsou potřeba.
- Porovnává se s **předepsanými** zálohami, stejně jako u správy. Nezaplacené zálohy
  zůstávají v saldu jako samostatný dluh a vyúčtování pro vlastníka je uvádí zvlášť.
  Vlastník tak dluží stejnou částku jako při porovnání s přijatými zálohami, jen se
  nemíchá dluh na zálohách s výsledkem vyúčtování.
- Vyúčtování jde současnému vlastníkovi jednotky; s předchozím vlastníkem se vyrovná
  sám (§ 1186 odst. 1 OZ). Profil může zvolit `vyuctovani_pri_prevodu: po_obdobich`
  (platí pro služby i správu): jednotka, která v roce změnila vlastníka, se vyúčtuje po
  vlastnických obdobích. Období tvoří měsíce, za které vlastník platil předpis
  (`predpis_mesice_prevodu`); měsíce před prvním zapsaným vlastníkem připadnou nejbližšímu
  známému. Zálohy období jsou předepsané zálohy jeho měsíců, náklad jednotky na položku se
  rozdělí podle vah měsíců (osobo-měsíce u klíče `osoby`, podíl měsíce u `podil`, jinak
  počet měsíců) metodou největších zbytků, takže období dají přesně výsledek jednotky.
  Měřidla a zúčtovatel se dělí také podle měsíců, odečet ke dni převodu aplikace nepoužívá.
  Výsledek dřívějšího vlastníka nese jeho jméno v dimenzi `protistrana`, takže je mezi
  dluhy dřívějších vlastníků a saldo jednotky neovlivní. Dokument pro něj má vybrané
  adresáty (`dokument.osoby`) a do lhůt doručení jednotky se nepočítá.
- Zaúčtovat jde od 31. 12., když jsou zaúčtované předpisy všech měsíců a žádná služba nemá
  problém: chybějící měřidlo nebo odečet, výsledky zúčtovatele, které nesedí na náklady
  v účetnictví. Nedoplatek i přeplatek jsou splatné 30. 4. dalšího roku.
- Doručení se bere ze zásilek (oddíl 7). U každé jednotky stránka ukáže datum doručení
  a z něj konec lhůty pro námitky (30 dní) a pro vyrovnání (4 měsíce). Námitky samotné
  a stav vyrovnání aplikace zatím nevede. Oprava po zaúčtování je storno a nové
  zaúčtování; nově rozeslané vyúčtování je nový dokument a lhůty běží od jeho doručení.

## 7. Rozesílání a upozornění

Aplikace posílá dva druhy zpráv a každý má jiná pravidla:

- **Dokumenty pro vlastníky**: předpis záloh, oznámení o změně zálohy, vyúčtování,
  upomínka a potvrzení o dluzích. Mají právní účinky a lhůty se u nich počítají od
  doručení, proto je odesílá vždy člověk po kontrole.
- **Upozornění pro výbor a účetní** pomáhají nic nepropásnout a chodí automaticky.

### Zasilka

`Zasilka(dokument, verze, prijemce, kanal, stav, odeslal, odeslano, doruceno)`

- Dokument se před odesláním uloží jako neměnný podklad (PDF se SHA-256) a zásilka na něj
  odkazuje. Vždy jde doložit, co přesně komu odešlo. Oprava je nová verze dokumentu
  a nová zásilka.
- `kanal` je `email`, nebo `posta`. E-mailem jen osobě, která s tím souhlasila. Souhlas
  se ukládá s datem a odkud pochází (formulář, písemná žádost, rozhodnutí podle stanov).
  Ostatním aplikace připraví tiskovou sestavu a datum odeslání a doručení se zapíše ručně.
- Stav: `pripravena → odeslana → dorucena`, nebo `odeslana → nedorucena` (odmítnutí
  poštovním serverem, vrácená obálka) a pak náhradní cesta.
- Projev vůle je účinný, jakmile adresátovi dojde (§ 570 OZ). Co se u e-mailu bere jako
  doručení (přijetí serverem příjemce, otevření odkazu, potvrzení vlastníkem), musí
  potvrdit právní posouzení. Aplikace ukládá všechny tři události.
- Datum doručení řídí lhůty: u vyúčtování služeb vyrovnání a námitky (oddíl 6), u změny
  zálohy účinnost od prvního dne dalšího měsíce (§ 4 odst. 4 zákona 67/2013), u upomínky
  pořadí, ve kterém se platby započítávají na dluhy (§ 1933 OZ). Změna zálohy potřebuje
  písemné oznámení; jestli stačí e-mail (§ 562 OZ), je potřeba ověřit.
- Hromadné rozeslání (předpisy na nový rok, vyúčtování všem) se připraví jako dávka.
  Výbor ji prohlédne, vidí, kdo dostane e-mail a komu se posílá poštou, a teprve pak
  odeslání potvrdí.
- Aplikace posílá z domény s platným SPF, DKIM a DMARC, aby zprávy nekončily ve spamu
  a příjemce mohl ověřit, že jsou od SVJ.

### Upozornění pro výbor

Události, o kterých aplikace dá vědět:

- nová přijatá faktura ke schválení a blížící se splatnost faktury,
- platba, kterou se nepodařilo spárovat, a předběžný pohyb bez potvrzení výpisem,
- vlastník, jehož dluh přesáhl hranici z profilu SVJ,
- chybějící výpis za uplynulý měsíc,
- blížící se lhůta: doručení vyúčtování, konec lhůty pro námitky, uzávěrka.

Každý člen výboru si nastaví, která upozornění chce a jestli hned, nebo v denním souhrnu.
E-mail nese jen stručný popis a odkaz. Jména dlužníků a částky zůstávají v aplikaci za
přihlášením.

### Ochrana osobních údajů

Vlastník dostává jen dokumenty své jednotky. Údaje o jiných vlastnících, třeba přehled
dlužníků, jdou jen výboru. Odeslaný dokument se archivuje spolu s dokladem, ke kterému
patří, a kontakty se mažou stejně jako u osoby (oddíl 1).

**V aplikaci:** dokumenty pro vlastníky ano, upozornění pro výbor zatím ne.

- Oznámení o zálohách, obě vyúčtování, upomínka a potvrzení o dluzích mají tlačítko
  Rozeslat vlastníkům. Dokument se neukládá jako PDF, ale jako samostatné HTML tak, jak ho
  vykreslí aplikace (bez skriptů, se styly), s otiskem SHA-256 (tabulka `dokument`; změnu
  zakazuje trigger). Zásilky jsou v tabulce `zasilka`, každá patří do dávky.
- Dávka se nejdřív připraví a ukáže ke kontrole; e-maily odejdou až potvrzením. Kanál
  určuje souhlas osoby s doručováním e-mailem k dnešku. Odkud souhlas pochází, se zatím
  neukládá, jen od kdy platí.
- E-mail nese dokument v příloze a odkaz s náhodným tokenem (v databázi je jen jeho otisk)
  na veřejnou stránku. Otevření stránky se zapíše jako otevření, tlačítko na ní (POST) jako
  potvrzení. Za doručení aplikace bere potvrzení vlastníkem nebo ruční zápis výboru;
  otevření ne, protože odkazy otevírají i antivirové kontroly pošty. Jako „přijetí
  serverem“ se ukládá převzetí zprávy odesílacím SMTP serverem; vrácené zprávy (bounce)
  se zatím nezpracovávají a nedoručení zapisuje výbor ručně.
- Datum doručení řídí lhůty u vyúčtování služeb a u oznámení o změně záloh. U upomínky
  se zatím jen eviduje; pořadí započtení plateb podle upomínek (§ 1933 OZ) aplikace neřeší.
- Odesílá se přes SMTP (nastavení `SMTP_*`), stejně jako přihlašovací odkaz.
