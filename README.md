# OpenSVJ

Aplikace pro účetnictví a hospodaření společenství vlastníků jednotek. Vychází ze
specifikace v repozitáři `opensvj-research` (složka `spec/`). Vyvíjí se na datech jednoho
skutečného (pilotního) SVJ za rok 2025; ta v repozitáři nejsou. Testy a první spuštění
stojí na vymyšleném ukázkovém SVJ, viz [Ukázkové a pilotní SVJ](#ukázkové-a-pilotní-svj).

Zatím umí:

- zaúčtovat operace z katalogu do podvojného deníku v PostgreSQL,
- sestavit rozvahu a výkaz zisku a ztráty ve zkráceném rozsahu (v tisících Kč); přeplatky jednotlivých vlastníků jsou v rozvaze mezi závazky a během roku je v ní i výsledek hospodaření běžného roku,
- přihlásit uživatele odkazem poslaným e-mailem (bez hesla),
- nahrát výpis z banky ve formátu GPC (ABO) nebo přehled pohybů z Raiffeisenbank (CSV), navrhnout k platbám zaúčtování a zaúčtovat je,
- převzít počáteční stavy k 1. 1. z rozvahy dřívějšího správce, včetně dluhů vlastníků po jednotkách,
- spočítat měsíční předpis záloh pro jednotky, zaúčtovat ho a ukázat, kolik která jednotka dluží, včetně zákonného úroku z prodlení,
- vytisknout upomínku, potvrzení o dluzích pro prodej jednotky a oznámení o nové výši záloh,
- vyúčtovat zálohy na správu domu,
- připravit uzávěrku roku: kontrolní seznam, rozvahu a výsledovku, inventurní soupisy, posouzení daně z příjmů a návrh přílohy,
- ukázat přehled roku a katalog operací ve webovém rozhraní.

## Jak to spustit

Potřebujete Docker (OrbStack), `uv` a `pnpm`.

```bash
cp .env.example .env          # a do AUTH_ALLOWED_EMAILS doplňte svůj e-mail
                              # a do BETTER_AUTH_SECRET výstup `openssl rand -base64 32`
docker compose up -d          # PostgreSQL na portu 5440
pnpm install
(cd backend && uv sync && uv run alembic upgrade head)
(cd backend && uv run python -m svj.sprava otevri-obdobi 2025 2026)  # účetní roky
pnpm --dir auth migrate       # tabulky Better Auth ve schématu auth
```

Pak ve třech terminálech:

```bash
pnpm --dir auth dev                                                   # přihlašování, port 3010
(cd backend && uv run uvicorn svj.api:app --host 0.0.0.0 --port 8010 --reload)  # API, port 8010
pnpm --dir frontend dev                                               # web, port 5180
```

Aplikace běží na <http://localhost:5180>. Vite předává `/api/auth` službě Better Auth
a zbytek `/api` backendu, takže prohlížeč vidí jen jednu adresu.

Ve vývoji se e-maily neposílají: přihlašovací odkaz se vypíše do výstupu služby `auth`
(řádek `[auth] přihlašovací odkaz pro …`), pokud je v `.env` `AUTH_LINKS_TO_CONSOLE=1`.
Bez toho, a vždy v produkčním režimu (`NODE_ENV=production`), odeslání odkazu zatím skončí
chybou, dokud se nenapojí skutečné odesílání pošty.

Do aplikace smějí jen adresy z `AUTH_ALLOWED_EMAILS`. Kdo ze seznamu vypadne, ztratí přístup
k datům do pěti minut; po restartu služby `auth` se mu ukončí i přihlášení. Adresy uvedené
navíc v `AUTH_READONLY_EMAILS` mohou jen nahlížet. Po změně seznamů restartujte `auth`
i backend.

Databáze z `compose.yaml` má vývojové heslo, proto poslouchá jen na `127.0.0.1`.

Při otevření z jiného počítače (adresa `.local` nebo Tailscale) je potřeba nastavit
`APP_URL`, `BETTER_AUTH_URL`, `JWT_ISSUER` a `JWT_AUDIENCE` na tu adresu, jinak
přihlášení neprojde kontrolou původu.


## Ukázkové a pilotní SVJ

V repozitáři je profil vymyšleného SVJ „Ukázková 12“ (`profiles/ukazka.yaml` a
`profiles/ukazka-predpisy.yaml`): dvanáct jednotek o celkové ploše 860 m², fond oprav
podle plochy, výtah podle počtu osob a jedna nebytová jednotka s vlastními zálohami. Na
něm běží všechny testy a s ním se aplikace spustí, když v `.env` není nastaveno jinak.
Čísla v testech jsou spočítaná ručně z tohoto profilu.

Aplikace se vyvíjí na datech jednoho skutečného SVJ: účty, jednotky s podíly a plochami,
předpis záloh a čísla ze závěrky 2025. Název, IČ, adresa, správci a dodavatelé do
repozitáře nepatří. Profil pilotního SVJ (`pilot.yaml` a `pilot-predpisy.yaml`) a test
nad jeho skutečnými zůstatky za rok 2025 jsou v samostatném soukromém repozitáři
`opensvj-pilot`, který se naklonuje vedle tohoto:

```bash
git clone <adresa soukromého repozitáře> ../opensvj-pilot
```

Pro práci nad pilotními daty se v `.env` nastaví `PROFIL=pilot` a
`PROFILY=../opensvj-pilot/profiles` (cesta je relativně ke kořeni repozitáře). Testy
s pilotními čísly se spouštějí zvlášť:

```bash
cd backend && uv run pytest ../../opensvj-pilot/tests
```

## Banka

Na stránce Banka se nahraje výpis ve formátu GPC (ABO), který umí stáhnout internetové
bankovnictví Raiffeisenbank, Fio i ostatních českých bank, nebo přehled pohybů
z Raiffeisenbank (`Pohyby_<účet>_<datum>.csv`). Přehled pohybů nemá zůstatky, takže
slouží k průběžnému zaúčtování plateb; navázání zůstatků ověří až výpis. Překrývající se
přehledy ani pozdější výpis platby nezdvojí (shoda podle čísla transakce banky). Na vyzkoušení je v `ukazky/`
vymyšlený výpis provozního účtu (vytváří ho `uv run python -m tests.ukazka` v `backend/`).

- Když aplikace číslo účtu ještě nezná, zeptá se, jestli jde o provozní účet, nebo účet
  fondu oprav, a zapamatuje si to.
- Výpis musí navazovat na předchozí (počáteční zůstatek = konečný zůstatek minulého
  výpisu) a součet plateb musí sedět na obraty v hlavičce. Jinak se nic neuloží.
- Stejný výpis podruhé nic nezdvojí. Nahrané výpisy a platby nejde měnit.
- K platbě aplikace navrhne zaúčtování: převod mezi účty SVJ, bankovní poplatek, nebo
  stejné zaúčtování jako u dřívější platby ze stejného účtu či se stejným VS. Návrh vždy
  potvrzuje člověk; při potvrzení si může aplikace volbu zapamatovat.
- Operace, které musí potvrdit účetní (např. nespárovaný příjem), zatím zaúčtovat nejde.
- U odchozí platby za fakturu se vybírá z nezaplacených faktur (stránka Faktury). Aplikace
  ji navrhne podle VS faktury, potom podle účtu dodavatele a částky. Platbu vyšší, než
  kolik z faktury zbývá, odmítne.

## Faktury

Přijatá faktura se zadá na stránce Faktury: dodavatel, za co je (teplo, úklid, správa,
oprava z fondu oprav…), částka, DUZP a splatnost; nepovinně číslo faktury, VS, účet a IČO
dodavatele. Zadáním se faktura schvaluje a hned se zaúčtuje podle druhu nákladu; u opravy
z fondu oprav se musí napsat, kdo ji schválil. Stejné číslo faktury od stejného dodavatele
podruhé zadat nejde. Seznam ukazuje, kolik z každé faktury zbývá zaplatit a co je po
splatnosti. Závazek a úhrada se párují interním číslem faktury (`radek_zapisu.parovaci_symbol`).

## Počáteční stavy

Když SVJ začne účtovat v aplikaci, potřebuje konečné zůstatky předchozího roku. Stránka
`#pocatecni` (odkaz je na Přehledu a u Předpisů) je převezme z rozvahy k 31. 12., kterou
sestavil dřívější správce: zůstatky účtů rozdělené na aktiva a pasiva (musí se rovnat) a
rozpis pohledávek za vlastníky po jednotkách. U každé položky jde napsat, za co je
(„Vyúčtování 2024“), a u dluhů dřívějších vlastníků jejich jméno; ty se současnému
vlastníkovi nezapočítají a stránka Předpisy je ukazuje zvlášť. Zaúčtuje se jeden zápis
k 1. 1. proti počátečnímu účtu rozvažnému (961); v roce jde jen jednou. U bankovních účtů
aplikace porovná zadaný zůstatek s prvním výpisem roku. Rozepsaný formulář se průběžně
ukládá do databáze, takže na něm může pokračovat i jiný člen výboru; po zaúčtování se
smaže. Seznam účtů a jejich názvy jsou v profilu SVJ (`nazvy_uctu`).

## Předpisy

Předpis záloh je v `profiles/<id>-predpisy.yaml`: od kdy platí, den splatnosti a složky
(fond oprav, teplo, voda, správa…). Každá složka má způsob výpočtu: sazba za m² podlahové
plochy, sazba za osobu, částka za dům rozdělená podle podílů nebo rovným dílem, nebo
pevná částka u každé jednotky. Plochy a podíly jednotek jsou v profilu SVJ. Při změně
předpisu se přidá nová verze s pozdějším datem; staré měsíce zůstanou podle staré verze.

Složky jsou ve třech skupinách podle role účtu: fond oprav (`zalohy_dlouhodobe`), zálohy na
správu domu (`zalohy_sprava.*`: pojištění, správce, revize, drobné opravy) a zálohy na služby
(`zalohy_sluzby.*`). Položky správy jsou v profilu v oddílu `sprava`, služby v `sluzby`.
Zálohy na správu nejsou služby podle § 2 zákona 67/2013, takže se nevyúčtovávají ve
vyúčtování služeb, ale zvlášť jako správa. Pilotní
SVJ je do roku 2025 vedlo mezi službami; účty 324001 a 324008–010 zůstaly stejné.

Na stránce Předpisy se zaúčtuje předpis za měsíc jedním zápisem pro všechny jednotky.
Měsíce jdou postupně a nejdřív od prvního dne měsíce; opakované zaúčtování nic nezdvojí.
U jednotek je vidět rozpis složek a předepsáno, zaplaceno a dluh nebo přeplatek za rok.
Platbu vlastníka aplikace na stránce Banka přiřadí k jednotce podle VS (předpona
z profilu SVJ + číslo jednotky + pořadí vlastníka), a když VS chybí, podle částky měsíčního předpisu.

V předpisu pilotního SVJ zatím odpovídá skutečnosti jen jedna jednotka. Pevné částky
ostatních jednotek a počty osob jsou dočasné a před ostrým použitím je potřeba je doplnit.

## Dlužníci

Stránka Dlužníci ukazuje po jednotkách, kolik je po splatnosti, od kdy a co ještě splatné
není. Platby se započítají na nejdřív splatné dluhy (OZ § 1932): nejdřív zůstatky
z minulých let, pak měsíční zálohy. Splatnost zálohy je den splatnosti z nastavení
předpisu. U jednotky s dluhem jde zobrazit a vytisknout text upomínky; jméno a adresu
vlastníka aplikace zatím nezná.

U každé položky po splatnosti je zákonný úrok z prodlení (nařízení vlády 351/2013 Sb.):
repo sazba ČNB k prvnímu dni pololetí, kdy prodlení začalo, plus 8 procentních bodů.
Tabulka repo sazeb je v `backend/src/svj/domena/urok.py` s odkazem na ČNB a datem ověření;
po každé změně sazby ČNB je potřeba ji doplnit, jinak aplikace úrok pro nové pololetí
nepočítá. Úrok se počítá jen ze zbývající nezaplacené části a u dluhů z minulých let bez
známé splatnosti chybí. V upomínce ho jde zapnout. Do účetnictví se nic nezapisuje; až ho
SVJ skutečně požaduje, zaúčtuje se operací `urok-z-prodleni` (311400/641).

Ke každé jednotce jde vytisknout potvrzení o dluzích pro prodej (§ 1186 odst. 3 OZ). Na
kupujícího přejdou jen dluhy uvedené v potvrzení, proto stránka varuje, když nejsou
zaúčtované všechny bankovní pohyby nebo je poslední výpis starší než týden.

## Oznámení o výši záloh

Stránka `#oznameni` (odkaz na stránce Předpisy) porovná verzi předpisu s předchozí po
jednotkách a složkách a připraví oznámení pro každou jednotku. Změněnou zálohu na služby
lze požadovat nejdřív od prvního dne měsíce po doručení písemného odůvodněného oznámení
(zákon 67/2013 § 4 odst. 3), takže stránka ukáže, do kdy musí oznámení dojít. Odůvodnění se
píše na stránce, ukládá se do databáze ke konkrétní verzi předpisu a tiskne se v každém
oznámení.

## Vyúčtování správy

Stránka Vyúčtování (`#vyuctovani`) porovná náklady roku na správu domu (pojištění, správa,
revize, drobné opravy) se zálohami na správu v předpisu. Náklad se k položce přiřadí podle
druhu faktury. Náklady položky se rozdělí na jednotky podle klíče z profilu (`klic` v oddílu
`sprava`): podle podílů na společných částech, správa nemovitosti rovným dílem na jednotku.
Výsledkem je nedoplatek nebo přeplatek jednotky a tisková verze vyúčtování pro vlastníka.

Před koncem roku jsou čísla průběžná. Zaúčtovat jde od 31. 12., když jsou zaúčtované
předpisy všech měsíců. Zápis `vyuctovani-spravy` vyúčtuje zálohy na správu do nuly a rozdíl
každé jednotky dá na pohledávky z vyúčtování (311200). Nedoplatek je pak na stránce Dlužníci
se splatností 30. 4. dalšího roku. Stanovy lhůtu neurčují, takže je převzatá ze služeb
(§ 7 zákona 67/2013). Náklady bez položky správy (bankovní poplatky, převod do fondu oprav)
se nezahrnují a stránka je vypíše; kam patří, rozhodne účetní. Výnosy označené položkou
správy (pojistné plnění na opravu, dotace na úroky) náklady té položky snižují, jak to
počítá Durec v souhrnných příkladech; ty jsou převedené na testy.

## Uzávěrka roku

Stránka Uzávěrka (`#uzaverka`) má pět částí:

- co zbývá udělat: kontroly z účetnictví (počáteční stavy, předpisy, nezaúčtované pohyby,
  zůstatek proti výpisu, vyrovnané pomocné účty, vyúčtování) a ruční body k odškrtnutí,
- rozvaha a výsledovka ve zkráceném rozsahu, v tisících i přesně,
- inventura: zůstatky rozvahových účtů s rozpisem po jednotkách nebo fakturách a tisk
  inventurních soupisů se zákonnými náležitostmi (každý účet na samostatné stránce),
- daň z příjmů: jestli SVJ musí podat přiznání (§ 38mb ZDP) a jak se který výnos daní,
- návrh přílohy k účetní závěrce s vyznačenými místy k doplnění.

Ruční odškrtnutí se ukládá do databáze pro celý výbor i s tím, kdo bod odškrtl a kdy.
Každé zaškrtnutí i zrušení je nový řádek (`odskrtnuti_uzaverky`, jen pro připisování),
takže zůstává celá historie. Body, které aplikace ověřuje z účetnictví, ručně odškrtnout
nejde.

## Deník a storno

Stránka Deník ukazuje zápisy roku s řádky. Zaúčtovaný zápis nejde změnit ani smazat;
chybu opraví storno (protizápis ke stejnému dni s uvedeným důvodem). Po stornu jde
stejnou věc (předpis měsíce, platbu, počáteční stavy, fakturu) zaúčtovat znovu. Fakturu
s úhradou jde stornovat až po stornu úhrady.

## Testy

```bash
(cd backend && uv run pytest)                 # potřebuje běžící databázi (svj_test)
(cd backend && uv run ruff check .)
pnpm --dir auth typecheck
pnpm --dir frontend exec tsc -b
```

Testy ověřují mimo jiné, že každý příklad v katalogu operací dává očekávané řádky,
že scénáře z roku 2025 vedou na výkazy shodné s účetní závěrkou SVJ a že databáze
sama odmítne nevyrovnaný zápis, změnu zaúčtovaného zápisu i zápis do uzavřeného období.

## Jak je to poskládané

| Část | Co dělá |
| --- | --- |
| `catalogue/` | Katalog účetních operací v YAML: šablony zápisů podle rolí a spustitelné příklady. Kromě praxe pilotního SVJ obsahuje obecné operace podle knihy Durec (úvěr, dotace, úrok z prodlení, pochybné pohledávky, majetek, pokladna, odměny výboru) s odkazem na stranu. |
| `profiles/` | Převod rolí na účty konkrétního SVJ. Profil pilotního SVJ je mimo repozitář. |
| `backend/` | Python 3.13, FastAPI, SQLAlchemy, Alembic. Doména (`svj/domena`), deník, výkazy, API. |
| `auth/` | Better Auth na Node (Hono): přihlášení odkazem a krátkodobé JWT (EdDSA). |
| `frontend/` | React + TypeScript + Vite. |
| `deploy/db-init/` | Inicializace databáze: schéma `auth` a testovací databáze. |

Hlavní pravidla:

- Částky jsou celé haléře (`int`), nikdy desetinná čísla. API je posílá taky v haléřích.
- Podíly na společných částech jsou zlomky; dělení částek používá metodu největšího
  zbytku, takže součet vždy sedí na haléř.
- Deník je jen pro připisování. Opravy se dělají stornem; vyrovnanost a uzavřená období
  hlídají triggery v databázi.
- Operace, které ještě musí potvrdit účetní (stav `overit`), nejdou v produkčním režimu
  zaúčtovat.
- Co uživatelé rozpracují (odškrtnuté body uzávěrky, rozepsané formuláře), se ukládá do
  databáze, ne do prohlížeče. Rozepsaný formulář (`ulozeny_formular`) má číslo verze:
  uložení projde, jen když od načtení nikdo jiný neuložil novější verzi, jinak stránka
  nabídne načíst uloženou verzi nebo uložit svou. V prohlížeči zůstává jen vzhled
  (světlý nebo tmavý).
- Identitu ověřuje Better Auth, backend kontroluje podpis tokenu přes JWKS. Role a
  oprávnění budou v databázi aplikace.

## Co chybí

Formáty výpisů jiné než GPC (camt.053, MT940), úprava předpisů v rozhraní, dobropisy,
jména a adresy vlastníků, role a oprávnění, odesílání e-mailů, export do Beancount a celé vyúčtování služeb (vyúčtování správy už aplikace umí). Otevřené účetní otázky
jsou v `opensvj-research/notes/07-zjisteni-a-otazky.md`.
