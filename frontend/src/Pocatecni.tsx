import { type ReactNode, useEffect, useMemo, useState } from 'react'
import { api } from './auth'
import { potvrdit } from './potvrdit'
import { StavFormulare, useSdilenyFormular } from './sdilenyFormular'
import { Chyba, Nacitani } from './ui'
import { kc, naHalire } from './penize'

type Ucet = { ucet: string; nazev: string; vlastnici: boolean }
type Zustatek = { ucet: string; castka: number }
type Polozka = {
  ucet: string
  castka: number
  jednotka: string | null
  popis: string
  drivejsi_vlastnik: string | null
}
type Banka = { ucet: string; nazev: string; zacatek_vypisu: number | null; vypis: string | null }
type Data = {
  rok: number
  ucty: Ucet[]
  jednotky: string[]
  zauctovano: { zapis: string; datum: string; zauctoval: string } | null
  zustatky: Zustatek[]
  polozky: Polozka[]
  banka: Banka[]
}

type Strana = 'aktiva' | 'pasiva'
type RadekZustatku = { id: number; strana: Strana; ucet: string; castka: string }
type RadekRozpisu = {
  id: number
  ucet: string
  jednotka: string
  popis: string
  drivejsi: string
  castka: string
}
type Koncept = { zustatky: RadekZustatku[]; rozpis: RadekRozpisu[] }

let posledniId = 0
const noveId = () => ++posledniId

function prazdnyKoncept(): Koncept {
  return {
    zustatky: [
      { id: noveId(), strana: 'aktiva', ucet: '', castka: '' },
      { id: noveId(), strana: 'pasiva', ucet: '', castka: '' },
    ],
    rozpis: [],
  }
}

/** Po načtení uloženého konceptu musí nová id řádků navazovat na ta uložená. */
function srovnejId(k: Koncept): Koncept {
  posledniId = Math.max(posledniId, ...k.zustatky.map((r) => r.id), ...k.rozpis.map((r) => r.id))
  return k
}

function zPrehlizece(t: string): Koncept {
  const k = JSON.parse(t) as Koncept | null
  return k?.zustatky && k.rozpis ? k : prazdnyKoncept()
}

export function Pocatecni() {
  const rok = new Date().getFullYear()
  const [data, setData] = useState<Data | null>(null)
  const [chyba, setChyba] = useState<string | null>(null)
  const [odesilam, setOdesilam] = useState(false)
  // Koncept je potřeba jen do zaúčtování; potom ho server smaže.
  const formular = useSdilenyFormular<Koncept>(
    'pocatecni-stavy',
    data && !data.zauctovano ? String(rok) : null,
    prazdnyKoncept,
    { nacteno: srovnejId, zPrehlizece: { klic: `pocatecni-stavy-${rok}`, preved: zPrehlizece } },
  )

  useEffect(() => {
    api<Data>(`/api/pocatecni/${rok}`).then(setData).catch((e) => setChyba(e.message))
  }, [rok])

  if (!data) return chyba ? <Chyba text={chyba} /> : <Nacitani />

  return (
    <>
      <h1>Počáteční stavy k 1. 1. {rok}</h1>
      {data.zauctovano ? (
        <Zauctovane data={data} />
      ) : formular.obsah === null ? (
        formular.stav === 'chyba' ? <Chyba text={formular.chyba ?? ''} /> : <Nacitani />
      ) : (
        <Formular
          data={data}
          koncept={formular.obsah}
          setKoncept={formular.zmen}
          stavKonceptu={<StavFormulare f={formular} />}
          konflikt={formular.stav === 'konflikt'}
          odesilam={odesilam}
          chyba={chyba}
          odeslat={async (telo) => {
            setOdesilam(true)
            setChyba(null)
            try {
              const nova = await api<Data>(`/api/pocatecni/${rok}`, { method: 'POST', json: telo })
              formular.zahodit()
              setData(nova)
              window.scrollTo(0, 0)
            } catch (e) {
              setChyba((e as Error).message)
            } finally {
              setOdesilam(false)
            }
          }}
        />
      )}
    </>
  )
}

function Formular({
  data,
  koncept,
  setKoncept,
  stavKonceptu,
  konflikt,
  odesilam,
  chyba,
  odeslat,
}: {
  data: Data
  koncept: Koncept
  setKoncept: (k: Koncept) => void
  stavKonceptu: ReactNode
  konflikt: boolean
  odesilam: boolean
  chyba: string | null
  odeslat: (telo: { zustatky: Zustatek[]; polozky: Polozka[] }) => void
}) {
  const rok = data.rok
  const nazvy = Object.fromEntries(data.ucty.map((u) => [u.ucet, u.nazev]))
  const vlastnici = useMemo(
    () => new Set(data.ucty.filter((u) => u.vlastnici).map((u) => u.ucet)),
    [data.ucty],
  )

  const vypocet = useMemo(() => {
    const zustatky = new Map<string, number>()
    let aktiva = 0
    let pasiva = 0
    let spatne = false
    for (const r of koncept.zustatky) {
      if (!r.ucet && !r.castka.trim()) continue
      const h = naHalire(r.castka)
      if (!r.ucet || h === null) {
        spatne = true
        continue
      }
      if (r.strana === 'aktiva') aktiva += h
      else pasiva += h
      const znamenko = r.strana === 'aktiva' ? 1 : -1
      zustatky.set(r.ucet, (zustatky.get(r.ucet) ?? 0) + znamenko * h)
    }
    const rozpis = new Map<string, number>()
    for (const r of koncept.rozpis) {
      const h = naHalire(r.castka)
      if (h === null || !r.ucet || !r.jednotka) {
        spatne = true
        continue
      }
      rozpis.set(r.ucet, (rozpis.get(r.ucet) ?? 0) + h)
    }
    const kRozpisu = [...zustatky]
      .filter(([u, z]) => z !== 0 && (vlastnici.has(u) || rozpis.has(u)))
      .map(([u, z]) => ({ ucet: u, zustatek: z, rozepsano: rozpis.get(u) ?? 0 }))
    return { zustatky, aktiva, pasiva, spatne, kRozpisu }
  }, [koncept, vlastnici])

  const uctyVlastniku = [...vypocet.zustatky.keys()].filter((u) => vlastnici.has(u))
  const rozpisSedi = vypocet.kRozpisu.every((k) => k.zustatek === k.rozepsano)
  const lzeOdeslat =
    !odesilam &&
    !konflikt &&
    !vypocet.spatne &&
    vypocet.zustatky.size > 0 &&
    vypocet.aktiva === vypocet.pasiva &&
    rozpisSedi

  function zmenZustatek(id: number, zmena: Partial<RadekZustatku>) {
    setKoncept({
      ...koncept,
      zustatky: koncept.zustatky.map((r) => (r.id === id ? { ...r, ...zmena } : r)),
    })
  }
  function zmenRozpis(id: number, zmena: Partial<RadekRozpisu>) {
    setKoncept({
      ...koncept,
      rozpis: koncept.rozpis.map((r) => (r.id === id ? { ...r, ...zmena } : r)),
    })
  }

  async function odeslatFormular() {
    const ano = await potvrdit({
      nadpis: `Zaúčtovat počáteční stavy k 1. 1. ${rok}?`,
      text:
        `Aktiva i pasiva shodně ${kc(vypocet.aktiva)}. ` +
        'Zaúčtované stavy půjde opravit jen stornem v Deníku.',
      ano: 'Zaúčtovat',
    })
    if (!ano) return
    odeslat({
      zustatky: [...vypocet.zustatky].map(([ucet, castka]) => ({ ucet, castka })),
      polozky: koncept.rozpis.map((r) => ({
        ucet: r.ucet,
        castka: naHalire(r.castka) ?? 0,
        jednotka: r.jednotka || null,
        popis: r.popis,
        drivejsi_vlastnik: r.drivejsi || null,
      })),
    })
  }

  const sekce = (strana: Strana, nadpis: string, napoveda: string) => (
    <section className="pocatecni-sekce">
      <h3>{nadpis}</h3>
      <p className="tlumene">{napoveda}</p>
      {koncept.zustatky
        .filter((r) => r.strana === strana)
        .map((r) => {
          const banka = data.banka.find((b) => b.ucet === r.ucet)
          const h = naHalire(r.castka)
          return (
            <div key={r.id} className="pocatecni-radek">
              <select
                aria-label="Účet"
                value={r.ucet}
                onChange={(e) => zmenZustatek(r.id, { ucet: e.target.value })}
              >
                <option value="">Vyberte účet…</option>
                {data.ucty.map((u) => (
                  <option key={u.ucet} value={u.ucet}>
                    {u.ucet} {u.nazev}
                  </option>
                ))}
              </select>
              <input
                aria-label="Částka v Kč"
                inputMode="decimal"
                placeholder="0,00"
                className={r.castka.trim() && h === null ? 'neplatne' : undefined}
                value={r.castka}
                onChange={(e) => zmenZustatek(r.id, { castka: e.target.value })}
              />
              <button
                type="button"
                className="vedlejsi"
                aria-label="Odebrat řádek"
                onClick={() =>
                  setKoncept({
                    ...koncept,
                    zustatky: koncept.zustatky.filter((x) => x.id !== r.id),
                  })
                }
              >
                ×
              </button>
              {banka?.zacatek_vypisu != null && h !== null && h !== banka.zacatek_vypisu && (
                <p className="varovani-text">
                  Výpis {banka.vypis} začíná na {kc(banka.zacatek_vypisu)}, tady je {kc(h)}.
                </p>
              )}
            </div>
          )
        })}
      <button
        type="button"
        className="vedlejsi"
        onClick={() =>
          setKoncept({
            ...koncept,
            zustatky: [...koncept.zustatky, { id: noveId(), strana, ucet: '', castka: '' }],
          })
        }
      >
        Přidat účet
      </button>
      <p>
        Celkem <strong>{kc(strana === 'aktiva' ? vypocet.aktiva : vypocet.pasiva)}</strong>
      </p>
    </section>
  )

  return (
    <>
      <p>
        Aplikace vede účetnictví od roku {rok}. Aby souhlasily zůstatky účtů a dluhy vlastníků,
        potřebuje stav ke konci roku {rok - 1}. Opište ho z rozvahy k 31. 12. {rok - 1}, kterou
        sestavil dřívější správce nebo účetní. Stačí účty s nenulovým zůstatkem.
      </p>
      <p className="tlumene">
        Rozepsané údaje se průběžně ukládají a ostatní členové výboru je uvidí, než je někdo
        zaúčtuje.
      </p>
      {stavKonceptu}

      <h2>Zůstatky účtů k 31. 12. {rok - 1}</h2>
      <div className="pocatecni-strany">
        {sekce('aktiva', 'Aktiva', 'Peníze na účtech, pohledávky, náklady příštích období.')}
        {sekce('pasiva', 'Pasiva', 'Fond oprav, přijaté zálohy, dluhy u dodavatelů.')}
      </div>
      {vypocet.aktiva !== vypocet.pasiva && (
        <p className="varovani-text">
          Aktiva a pasiva se liší o {kc(Math.abs(vypocet.aktiva - vypocet.pasiva))}. Musí se
          rovnat.
        </p>
      )}

      <h2>Dluhy a přeplatky vlastníků</h2>
      <p>
        Pohledávky za vlastníky rozepište po jednotkách, aby aplikace věděla, kdo kolik dluží.
        Rozpis bývá ve zprávě o hospodaření nebo v saldu od správce. Přeplatek zapište se
        znaménkem minus. Když dluh patří dřívějšímu vlastníkovi, napište jeho jméno; současnému
        vlastníkovi se pak nezapočítá.
      </p>
      {uctyVlastniku.length === 0 ? (
        <p className="tlumene">
          Nejdřív zadejte zůstatek některého účtu pohledávek za vlastníky (účty 311).
        </p>
      ) : (
        <>
          {koncept.rozpis.length > 0 && (
            <div className="rozpis-hlavicka" aria-hidden="true">
              <span>Jednotka</span>
              <span>Účet</span>
              <span>Za co</span>
              <span>Dřívější vlastník</span>
              <span>Částka v Kč</span>
            </div>
          )}
          {koncept.rozpis.map((r) => (
            <div key={r.id} className="rozpis-radek">
              <select
                aria-label="Jednotka"
                value={r.jednotka}
                onChange={(e) => zmenRozpis(r.id, { jednotka: e.target.value })}
              >
                <option value="">Jednotka…</option>
                {data.jednotky.map((j) => (
                  <option key={j}>{j}</option>
                ))}
              </select>
              <select
                aria-label="Účet"
                value={r.ucet}
                onChange={(e) => zmenRozpis(r.id, { ucet: e.target.value })}
              >
                <option value="">Účet…</option>
                {uctyVlastniku.map((u) => (
                  <option key={u} value={u}>
                    {u} {nazvy[u]}
                  </option>
                ))}
              </select>
              <input
                aria-label="Za co"
                placeholder="např. Vyúčtování 2024"
                value={r.popis}
                onChange={(e) => zmenRozpis(r.id, { popis: e.target.value })}
              />
              <input
                aria-label="Dřívější vlastník"
                placeholder="jen u dřívějšího vlastníka"
                value={r.drivejsi}
                onChange={(e) => zmenRozpis(r.id, { drivejsi: e.target.value })}
              />
              <input
                aria-label="Částka v Kč"
                inputMode="decimal"
                placeholder="0,00"
                className={r.castka.trim() && naHalire(r.castka) === null ? 'neplatne' : undefined}
                value={r.castka}
                onChange={(e) => zmenRozpis(r.id, { castka: e.target.value })}
              />
              <button
                type="button"
                className="vedlejsi"
                aria-label="Odebrat řádek"
                onClick={() =>
                  setKoncept({ ...koncept, rozpis: koncept.rozpis.filter((x) => x.id !== r.id) })
                }
              >
                ×
              </button>
            </div>
          ))}
          <button
            type="button"
            className="vedlejsi"
            onClick={() => {
              const posledni = koncept.rozpis.at(-1)
              setKoncept({
                ...koncept,
                rozpis: [
                  ...koncept.rozpis,
                  {
                    id: noveId(),
                    ucet: posledni?.ucet ?? (uctyVlastniku.length === 1 ? uctyVlastniku[0] : ''),
                    jednotka: '',
                    popis: posledni?.popis ?? '',
                    drivejsi: '',
                    castka: '',
                  },
                ],
              })
            }}
          >
            Přidat řádek
          </button>
          <ul className="kontroly">
            {vypocet.kRozpisu.map((k) => (
              <li key={k.ucet} className={k.zustatek === k.rozepsano ? 'uspech' : 'varovani-text'}>
                {k.ucet} {nazvy[k.ucet]}:{' '}
                {k.zustatek === k.rozepsano
                  ? `rozepsáno celých ${kc(k.zustatek)}`
                  : `rozepsáno ${kc(k.rozepsano)} z ${kc(k.zustatek)}, zbývá ${kc(k.zustatek - k.rozepsano)}`}
              </li>
            ))}
          </ul>
        </>
      )}

      {chyba && <p className="chyba">{chyba}</p>}
      {vypocet.spatne && (
        <p className="varovani-text">
          Některý řádek nemá vybraný účet nebo jednotku, nebo částka není číslo.
        </p>
      )}
      <p>
        <button disabled={!lzeOdeslat} onClick={odeslatFormular}>
          {odesilam ? 'Účtuji…' : 'Zaúčtovat počáteční stavy'}
        </button>
      </p>
    </>
  )
}

function Zauctovane({ data }: { data: Data }) {
  const z = data.zauctovano!
  const nazvy = Object.fromEntries(data.ucty.map((u) => [u.ucet, u.nazev]))
  const aktiva = data.zustatky.filter((x) => x.castka > 0)
  const pasiva = data.zustatky.filter((x) => x.castka < 0)
  const nesedi = data.banka.filter((b) => {
    const zust = data.zustatky.find((x) => x.ucet === b.ucet)?.castka ?? 0
    return b.zacatek_vypisu !== null && b.zacatek_vypisu !== zust
  })
  const tabulka = (nadpis: string, radky: Zustatek[]) => (
    <table>
      <thead>
        <tr>
          <th>{nadpis}</th>
          <th className="cislo">Částka</th>
        </tr>
      </thead>
      <tbody>
        {radky.map((x) => (
          <tr key={x.ucet}>
            <td>
              {x.ucet} {nazvy[x.ucet] ?? ''}
            </td>
            <td className="cislo">{kc(Math.abs(x.castka))}</td>
          </tr>
        ))}
        <tr>
          <td>
            <strong>Celkem</strong>
          </td>
          <td className="cislo">
            <strong>{kc(Math.abs(radky.reduce((a, x) => a + x.castka, 0)))}</strong>
          </td>
        </tr>
      </tbody>
    </table>
  )
  return (
    <>
      <p className="uspech">
        Zaúčtováno zápisem {z.zapis} k {new Date(z.datum).toLocaleDateString('cs-CZ')} (
        {z.zauctoval}). Opravit je jde jen stornem.
      </p>
      {nesedi.map((b) => (
        <p key={b.ucet} className="upozorneni">
          {b.nazev}: výpis {b.vypis} začíná na {kc(b.zacatek_vypisu!)}, počáteční stav je{' '}
          {kc(data.zustatky.find((x) => x.ucet === b.ucet)?.castka ?? 0)}. Jeden z údajů nesedí.
        </p>
      ))}
      <div className="pocatecni-strany">
        {tabulka('Aktiva', aktiva)}
        {tabulka('Pasiva', pasiva)}
      </div>
      {data.polozky.length > 0 && (
        <>
          <h2>Dluhy a přeplatky vlastníků k 1. 1. {data.rok}</h2>
          <table>
            <thead>
              <tr>
                <th>Jednotka</th>
                <th>Za co</th>
                <th className="siroke">Účet</th>
                <th className="cislo">Stav</th>
              </tr>
            </thead>
            <tbody>
              {data.polozky.map((p, i) => (
                <tr key={i}>
                  <td>{p.jednotka}</td>
                  <td>
                    {p.popis}
                    {p.drivejsi_vlastnik && (
                      <span className="tlumene"> (dřívější vlastník {p.drivejsi_vlastnik})</span>
                    )}
                  </td>
                  <td className="siroke">{p.ucet}</td>
                  <td className="cislo">
                    {p.castka > 0 ? `dluh ${kc(p.castka)}` : `přeplatek ${kc(-p.castka)}`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </>
  )
}
