# OpenSVJ

OpenSVJ je aplikace pro účetnictví a hospodaření společenství vlastníků jednotek (SVJ).
Je určená výboru a účetní: z bankovních výpisů a faktur vede podvojné účetnictví, počítá
předpisy záloh, hlídá dlužníky, vyúčtovává zálohy na správu domu a připravuje roční
uzávěrku.

Aplikace je ve vývoji. Postupy, které ještě musí potvrdit účetní, jsou v ní tak označené.
Zaúčtovat je jde a kontrolní seznam uzávěrky je připomene k posouzení.

Co má aplikace dělat a podle jakých pravidel, popisuje [specifikace](docs/spec/README.md).
Proč se v SVJ účtuje tak, jak se účtuje, vysvětluje [příručka](docs/prirucka/README.md).

## Co umí

- vést podvojný deník v PostgreSQL podle katalogu účetních operací,
- nahrát výpis z banky ve formátu GPC (ABO) nebo přehled pohybů z Raiffeisenbank (CSV),
  navrhnout zaúčtování plateb a zaúčtovat je,
- zadat a zaúčtovat přijaté faktury a spárovat je s platbami,
- převzít počáteční stavy k 1. 1. od dřívějšího správce, včetně dluhů vlastníků po jednotkách,
- spočítat a zaúčtovat měsíční předpis záloh a ukázat, kolik která jednotka dluží, včetně
  zákonného úroku z prodlení,
- vytisknout upomínku, potvrzení o dluzích pro prodej jednotky a oznámení o nové výši záloh,
- vyúčtovat zálohy na správu domu,
- sestavit rozvahu a výkaz zisku a ztráty ve zkráceném rozsahu,
- připravit uzávěrku roku: kontrolní seznam, inventurní soupisy, posouzení daně z příjmů
  a návrh přílohy,
- přihlásit uživatele odkazem poslaným e-mailem, bez hesla.

## Spuštění pro vývoj

Potřebujete Docker (například OrbStack), `uv` a `pnpm`.

```bash
cp .env.example .env          # do AUTH_ALLOWED_EMAILS doplňte svůj e-mail
                              # a do BETTER_AUTH_SECRET výstup `openssl rand -base64 32`
docker compose up -d          # PostgreSQL na portu 5440
pnpm install
(cd backend && uv sync && uv run alembic upgrade head)
(cd backend && uv run python -m svj.sprava otevri-obdobi 2025 2026)  # účetní roky
pnpm --dir auth migrate       # tabulky Better Auth ve schématu auth
```

Pak ve třech terminálech:

```bash
pnpm --dir auth dev                                                             # přihlašování, port 3010
(cd backend && uv run uvicorn svj.api:app --host 0.0.0.0 --port 8010 --reload)  # API, port 8010
pnpm --dir frontend dev                                                         # web, port 5180
```

Aplikace běží na <http://localhost:5180>. Vite předává `/api/auth` službě přihlašování
a zbytek `/api` backendu, takže prohlížeč vidí jen jednu adresu.

Ve vývoji se e-maily neposílají. Když je v `.env` `AUTH_LINKS_TO_CONSOLE=1`, přihlašovací
odkaz se vypíše do výstupu služby `auth` (řádek `[auth] přihlašovací odkaz pro …`). Bez
toho, a vždy v produkčním režimu (`NODE_ENV=production`), odeslání odkazu zatím skončí
chybou, protože skutečné odesílání pošty ještě není napojené.

Do aplikace smějí jen adresy z `AUTH_ALLOWED_EMAILS`; adresy v `AUTH_READONLY_EMAILS` mohou
jen nahlížet. Kdo ze seznamu vypadne, ztratí přístup k datům do pěti minut a po restartu
služby `auth` se mu ukončí i přihlášení. Po změně seznamů restartujte `auth` i backend.

Databáze z `compose.yaml` má vývojové heslo, proto poslouchá jen na `127.0.0.1`. Při
otevření z jiného počítače (adresa `.local` nebo Tailscale) je potřeba nastavit `APP_URL`,
`BETTER_AUTH_URL`, `JWT_ISSUER` a `JWT_AUDIENCE` na tu adresu, jinak přihlášení neprojde
kontrolou původu.

## Ukázkové SVJ a vlastní data

Bez dalšího nastavení aplikace pracuje s vymyšleným SVJ „Ukázková 12“
(`profiles/ukazka.yaml` a `profiles/ukazka-predpisy.yaml`). Má dvanáct jednotek o celkové
ploše 860 m², fond oprav podle plochy, výtah podle počtu osob a jednu nebytovou jednotku
s vlastními zálohami. Na něm běží i všechny testy; očekávané částky jsou z tohoto profilu
spočítané ručně. Na vyzkoušení banky je v `ukazky/` vymyšlený výpis provozního účtu
(vytváří ho `uv run python -m tests.ukazka` v `backend/`).

Profil skutečného SVJ obsahuje jednotky, podíly a předpis záloh, a proto do repozitáře
nepatří. Uložte ho do samostatné soukromé složky a v `.env` nastavte `PROFILY` (cesta
ke složce, relativně ke kořeni repozitáře) a `PROFIL` (název profilu). Jak profil vypadá,
popisuje `profiles/README.md`.

Aplikace se vyvíjí na datech jednoho skutečného SVJ. Jeho profil a test nad skutečnými
čísly za rok 2025 jsou v soukromém repozitáři `opensvj-pilot`; kdo k němu má přístup,
naklonuje ho vedle tohoto a testy spustí příkazem
`cd backend && uv run pytest ../../opensvj-pilot/tests`.

## Jak se s aplikací pracuje

### Banka

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
  jednotky a pořadí vlastníka), a když VS chybí, podle částky měsíčního předpisu.
- U odchozí platby za fakturu se vybírá z nezaplacených faktur. Aplikace ji navrhne podle
  VS faktury, potom podle účtu dodavatele a částky. Platbu vyšší, než kolik z faktury
  zbývá, odmítne.
- Operace, které musí potvrdit účetní (například nespárovaný příjem), zatím zaúčtovat nejde.

### Faktury

Přijatá faktura se zadá na stránce Faktury: dodavatel, za co je (teplo, úklid, správa,
oprava z fondu oprav…), částka, DUZP a splatnost, nepovinně číslo faktury, VS, účet a IČO
dodavatele. Zadáním se faktura schvaluje a hned se zaúčtuje podle druhu nákladu; u opravy
z fondu oprav se musí uvést, kdo ji schválil. Stejné číslo faktury od stejného dodavatele
podruhé zadat nejde. Seznam ukazuje, kolik z každé faktury zbývá zaplatit a co je po
splatnosti.

### Počáteční stavy

Když SVJ začne účtovat v aplikaci, potřebuje konečné zůstatky předchozího roku. Stránka
Počáteční stavy (odkaz je na Přehledu a u Předpisů) je převezme z rozvahy k 31. 12.
od dřívějšího správce: zůstatky účtů rozdělené na aktiva a pasiva, které se musí rovnat,
a rozpis pohledávek za vlastníky po jednotkách. U každé položky jde napsat, za co je
(„Vyúčtování 2024“), a u dluhů dřívějších vlastníků jejich jméno; ty se současnému
vlastníkovi nezapočítají a stránka Předpisy je ukazuje zvlášť. Zaúčtuje se jeden zápis
k 1. 1. proti počátečnímu účtu rozvažnému (961), v každém roce jen jednou. U bankovních
účtů aplikace porovná zadaný zůstatek s prvním výpisem roku. Rozepsaný formulář se
průběžně ukládá, takže na něm může pokračovat i jiný člen výboru.

### Předpisy

Předpis záloh je v `profiles/<id>-predpisy.yaml`: od kdy platí, den splatnosti a složky
(fond oprav, teplo, voda, správa…). Každá složka má způsob výpočtu: sazba za m² podlahové
plochy, sazba za osobu, částka za dům rozdělená podle podílů nebo rovným dílem, nebo pevná
částka u každé jednotky. Plochy a podíly jednotek jsou v profilu SVJ. Při změně předpisu
se přidá nová verze s pozdějším datem a starší měsíce zůstanou podle staré verze.

Složky jsou ve třech skupinách: fond oprav, zálohy na správu domu (pojištění, správce,
revize, drobné opravy) a zálohy na služby. Zálohy na správu nejsou služby podle § 2 zákona
67/2013, a proto se nevyúčtovávají spolu se službami, ale zvlášť.

Na stránce Předpisy se zaúčtuje předpis za měsíc jedním zápisem pro všechny jednotky.
Měsíce jdou postupně a opakované zaúčtování nic nezdvojí. U jednotek je vidět rozpis
složek a za rok předepsáno, zaplaceno a dluh nebo přeplatek.

### Dlužníci

Stránka Dlužníci ukazuje po jednotkách, kolik je po splatnosti, od kdy a co ještě splatné
není. Platby se započítají na nejdřív splatné dluhy (OZ § 1932): nejdřív zůstatky
z minulých let, pak měsíční zálohy. U jednotky s dluhem jde zobrazit a vytisknout text
upomínky; jméno a adresu vlastníka aplikace zatím nezná.

U každé položky po splatnosti je zákonný úrok z prodlení (nařízení vlády 351/2013 Sb.):
repo sazba ČNB k prvnímu dni pololetí, kdy prodlení začalo, plus 8 procentních bodů.
Tabulka repo sazeb je v `backend/src/svj/domena/urok.py` a po každé změně sazby ČNB je
potřeba ji doplnit, jinak aplikace úrok pro nové pololetí nespočítá. Úrok se počítá jen
ze zbývající nezaplacené části a u dluhů z minulých let bez známé splatnosti chybí.
V upomínce ho jde zapnout. Do účetnictví se zapíše, až ho SVJ skutečně požaduje.

Ke každé jednotce jde vytisknout potvrzení o dluzích pro prodej (§ 1186 odst. 3 OZ). Na
kupujícího přejdou jen dluhy uvedené v potvrzení, proto stránka varuje, když nejsou
zaúčtované všechny bankovní pohyby nebo je poslední výpis starší než týden.

### Oznámení o výši záloh

Stránka Oznámení o zálohách (odkaz je na stránce Předpisy) porovná novou verzi předpisu s předchozí
po jednotkách a složkách a připraví oznámení pro každou jednotku. Změněnou zálohu na služby
lze požadovat nejdřív od prvního dne měsíce po doručení písemného odůvodněného oznámení
(zákon 67/2013 § 4 odst. 3), takže stránka ukáže, do kdy musí oznámení dojít. Odůvodnění
se napíše na stránce, uloží se ke konkrétní verzi předpisu a vytiskne se v každém oznámení.

### Vyúčtování správy

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

### Uzávěrka roku

Stránka Uzávěrka má pět částí:

- co zbývá udělat: kontroly, které aplikace ověří sama z účetnictví (počáteční stavy,
  předpisy, nezaúčtované pohyby, zůstatky proti výpisům, vyrovnané pomocné účty,
  vyúčtování), a body, které se odškrtávají ručně,
- rozvaha a výsledovka ve zkráceném rozsahu, v tisících Kč i přesně,
- inventura: zůstatky rozvahových účtů s rozpisem po jednotkách nebo fakturách a tisk
  inventurních soupisů se zákonnými náležitostmi,
- daň z příjmů: jestli SVJ musí podat přiznání (§ 38mb ZDP) a jak se který výnos daní,
- návrh přílohy k účetní závěrce s vyznačenými místy k doplnění.

Ruční odškrtnutí vidí celý výbor i s tím, kdo bod odškrtl a kdy, a zůstává celá historie
zaškrtnutí i zrušení.

### Deník a storno

Stránka Deník ukazuje zápisy roku s řádky. Zaúčtovaný zápis nejde změnit ani smazat;
chybu opraví storno, tedy protizápis ke stejnému dni s uvedeným důvodem. Po stornu jde
stejnou věc (předpis měsíce, platbu, počáteční stavy, fakturu) zaúčtovat znovu. Fakturu
s úhradou jde stornovat až po stornu úhrady.

## Katalog operací

Jak se která operace účtuje, popisuje katalog v `catalogue/`: šablony zápisů podle rolí
účtů, pravidla, zdroje v zákonech a literatuře a spustitelné příklady. Profil SVJ pak role
převede na konkrétní účty. Formát popisuje `catalogue/README.md`.

## Testy

```bash
(cd backend && uv run pytest)                 # potřebuje běžící databázi (svj_test)
(cd backend && uv run ruff check .)
pnpm --dir auth typecheck
pnpm --dir frontend exec tsc -b
```

Testy mimo jiné ověřují, že každý příklad v katalogu dává očekávané řádky, že předpisy,
vyúčtování a výkazy ukázkového SVJ vycházejí na ručně spočítané částky a že databáze sama
odmítne nevyrovnaný zápis, změnu zaúčtovaného zápisu i zápis do uzavřeného období.

## Jak je to poskládané

| Část | Co dělá |
| --- | --- |
| `docs/spec/` | Specifikace: doménový model, účtová osnova a výkazy, testovací scénáře. |
| `docs/prirucka/` | Příručka: účetní a právní pravidla SVJ s odkazy na předpisy a příklady. |
| `catalogue/` | Katalog účetních operací v YAML: šablony zápisů podle rolí účtů a spustitelné příklady. |
| `profiles/` | Profily SVJ: převod rolí na účty, jednotky, služby a předpis záloh. V repozitáři je jen ukázkové SVJ. |
| `backend/` | Python 3.13, FastAPI, SQLAlchemy, Alembic. Doména (`svj/domena`), deník, výkazy, API. |
| `auth/` | Better Auth na Node (Hono): přihlášení odkazem a krátkodobé tokeny JWT (EdDSA). |
| `frontend/` | React, TypeScript a Vite. |
| `deploy/db-init/` | Inicializace databáze: schéma `auth` a testovací databáze. |
| `ukazky/` | Vymyšlený bankovní výpis na vyzkoušení. |

Hlavní pravidla:

- Částky jsou celé haléře (`int`), nikdy desetinná čísla. API je posílá taky v haléřích.
- Podíly na společných částech jsou zlomky. Dělení částek používá metodu největšího
  zbytku, takže součet vždy sedí na haléř.
- Do deníku se jen připisuje. Opravy se dělají stornem; vyrovnanost a uzavřená období
  hlídají triggery v databázi.
- Aplikace blokuje jen to, co by zkreslilo čísla. Postupy, které ještě musí potvrdit
  účetní (stav `overit`), jde zaúčtovat; uzávěrka je připomene k posouzení.
- Co uživatelé rozpracují (odškrtnuté body uzávěrky, rozepsané formuláře), se ukládá do
  databáze, ne do prohlížeče. Rozepsaný formulář má číslo verze: uložení projde, jen když
  od načtení nikdo jiný neuložil novější verzi, jinak stránka nabídne načíst uloženou
  verzi nebo uložit svou. Prohlížeč si pamatuje jen světlý nebo tmavý vzhled.
- Identitu ověřuje Better Auth a backend kontroluje podpis tokenu přes JWKS. Role
  a oprávnění budou v databázi aplikace.

## Co zatím chybí

- jiné formáty výpisů než GPC (camt.053, MT940),
- úprava předpisů v rozhraní,
- dobropisy,
- jména a adresy vlastníků,
- role a oprávnění,
- odesílání e-mailů,
- celé vyúčtování služeb (vyúčtování správy už aplikace umí),
- export do Beancount.
