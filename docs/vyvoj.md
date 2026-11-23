# Vývoj a provoz

Jak aplikaci spustit na vlastním počítači, jak je poskládaná a podle jakých pravidel se
do ní přispívá. Co má aplikace dělat, popisuje [specifikace](spec/README.md).

## Spuštění

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

## Ukázková data

Po prvním spuštění je aplikace prázdná. Vymyšlené SVJ „Ukázková 12“ s rokem 2026 (vlastníci,
předpisy, faktury, bankovní výpisy a pár dlužníků) do ní nahraje:

```bash
(cd backend && PROFIL=ukazka PROFILY=profiles uv run python -m tests.naplneni)
```

Zapisuje jen do prázdné databáze a jen s profilem `ukazka`, takže skutečná data nepřepíše.
Kdo už má v hlavní databázi vlastní účetnictví, založí si pro ukázku druhou databázi
a spustí proti ní migrace i naplnění s `DATABASE_URL` nastaveným na ni.

Samotný bankovní výpis na vyzkoušení stránky Banka je v `ukazky/`
(vytváří ho `uv run python -m tests.ukazka` v `backend/`).

## E-maily

E-maily (přihlašovací odkaz i dokumenty pro vlastníky) se posílají přes SMTP podle
`SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_TLS` a `SMTP_FROM` v `.env`.
Ve vývoji stačí `SMTP_FROM` a `MAIL_DIR`: e-maily se pak místo odeslání uloží jako soubory
`.eml` do té složky. Když není nastavené nic z toho a v `.env` je `AUTH_LINKS_TO_CONSOLE=1`,
přihlašovací odkaz se vypíše do výstupu služby `auth` (řádek `[auth] přihlašovací odkaz
pro …`); v produkčním režimu (`NODE_ENV=production`) se do konzole nevypisuje nikdy.
Odesílací doména má mít platné SPF, DKIM a DMARC, jinak zprávy skončí ve spamu.

## Kdo se smí přihlásit

Do aplikace smějí jen adresy z `AUTH_ALLOWED_EMAILS`; adresy v `AUTH_READONLY_EMAILS` mohou
jen nahlížet. Kdo ze seznamu vypadne, ztratí přístup k datům do pěti minut a po restartu
služby `auth` se mu ukončí i přihlášení. Po změně seznamů restartujte `auth` i backend.

Databáze z `compose.yaml` má vývojové heslo, proto poslouchá jen na `127.0.0.1`. Při
otevření z jiného počítače (adresa `.local` nebo Tailscale) je potřeba nastavit `APP_URL`,
`BETTER_AUTH_URL`, `JWT_ISSUER` a `JWT_AUDIENCE` na tu adresu, jinak přihlášení neprojde
kontrolou původu.

## Vlastní SVJ

Bez dalšího nastavení aplikace pracuje s vymyšleným SVJ „Ukázková 12“
(`profiles/ukazka.yaml` a `profiles/ukazka-predpisy.yaml`). Má dvanáct jednotek o celkové
ploše 860 m², fond oprav podle plochy, výtah podle počtu osob a jednu nebytovou jednotku
s vlastními zálohami. Na něm běží i všechny testy; očekávané částky jsou z tohoto profilu
spočítané ručně.

Profil skutečného SVJ obsahuje jednotky, podíly a předpis záloh, a proto do repozitáře
nepatří. Uložte ho do samostatné soukromé složky a v `.env` nastavte `PROFILY` (cesta
ke složce, relativně ke kořeni repozitáře) a `PROFIL` (název profilu). Jak profil vypadá,
popisuje [`profiles/README.md`](../profiles/README.md).

Aplikace se vyvíjí na datech jednoho skutečného SVJ. Jeho profil a test nad skutečnými
čísly za rok 2025 jsou v soukromém repozitáři `opensvj-pilot`; kdo k němu má přístup,
naklonuje ho vedle tohoto a testy spustí příkazem
`cd backend && uv run pytest ../../opensvj-pilot/tests`.

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
| `web/` | Prezentační web: statické HTML, CSS a JavaScript bez sestavování. |

Jak se která operace účtuje, popisuje katalog v `catalogue/`: šablony zápisů podle rolí
účtů, pravidla, zdroje v zákonech a literatuře a spustitelné příklady. Profil SVJ pak role
převede na konkrétní účty. Formát popisuje [`catalogue/README.md`](../catalogue/README.md).

## Pravidla, která kód drží

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

## Prezentační web

Složka `web/` je statická stránka bez závislostí. Lokálně ji ukáže
`python3 -m http.server 5190 --bind 0.0.0.0 --directory web`, na GitHub Pages ji při každé
změně ve `web/` nasadí workflow `.github/workflows/web.yml`.

Snímky aplikace ve `web/img/` jsou pořízené nad ukázkovými daty (viz výše), přihlášený je
vymyšlený uživatel. Po větší změně vzhledu aplikace je potřeba je pořídit znovu, stejně
jako čísla v interaktivních ukázkách ve `web/web.js`.
