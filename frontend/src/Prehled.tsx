import { useEffect, useState, type ReactNode } from 'react'
import { api } from './auth'
import { Dum, type Okno } from './Dum'
import { kc } from './penize'
import { Chyba, Nacitani } from './ui'

type Operace = { id: string; nazev: string; stav: string; doklad: string; oblast: string }
type Vykazy = { rok: number; pocet_zapisu: number; pocatecni_stavy: boolean }
type Banka = {
  ucty: {
    ucel: string
    nazev: string
    cislo: string | null
    zustatek: number | null
    posledni_vypis: string | null
    pohyby_do: string | null
  }[]
  nezauctovano: number
}
type Dluznici = {
  celkem_po_splatnosti: number
  jednotky: { jednotka: string; po_splatnosti: number; preplatek: number }[]
}
type Faktury = { k_uhrade: number; faktury: { stav: string; zbyva: number }[] }
type Predpisy = {
  mesice: { mesic: number; nazev: string; stav: 'zauctovano' | 'lze' | 'pozdeji' | 'bez_predpisu'; celkem: number }[]
}

type Data = {
  vykazy: Vykazy
  operace: Operace[] | null
  banka: Banka | null
  dluznici: Dluznici | null
  faktury: Faktury | null
  predpisy: Predpisy | null
}

type Ukol = { odkaz: string; nadpis: string; popis: string; ton?: 'varovani' | 'chyba'; ikona: ReactNode }

const STAV: Record<string, string> = {
  praxe: 'podle dosavadní praxe',
  navrh: 'návrh',
  overit: 'čeká na potvrzení účetní',
}

const OBLAST: Record<string, string> = {
  predpisy: 'Předpisy',
  banka: 'Banka',
  dodavatele: 'Faktury a doklady',
  'fond-oprav': 'Fond oprav',
  vyuctovani: 'Vyúčtování',
  uzaverka: 'Uzávěrka',
}

const datum = (d: string) => new Date(d).toLocaleDateString('cs-CZ')

/** České tvary podle počtu: (1, 2–4, 5+). */
function pocet(n: number, jeden: string, dva: string, pet: string) {
  return `${n} ${n === 1 ? jeden : n >= 2 && n <= 4 ? dva : pet}`
}

function pozdrav() {
  const h = new Date().getHours()
  if (h < 10) return 'Dobré ráno'
  if (h < 18) return 'Dobrý den'
  return 'Dobrý večer'
}

const ikony = {
  banka: (
    <path d="M3 10h18M5 10v8m4.67-8v8m4.66-8v8M19 10v8M3 20h18M12 3 3 8h18l-9-5Z" />
  ),
  kalendar: (
    <>
      <rect x="3.5" y="5" width="17" height="15.5" rx="2.5" />
      <path d="M3.5 10h17M8 3v4m8-4v4" />
    </>
  ),
  faktura: (
    <>
      <path d="M6 3h9l4 4v14H6z" />
      <path d="M14.5 3v4.5H19M9 12h6.5M9 16h6.5" />
    </>
  ),
  lide: (
    <>
      <circle cx="9" cy="8.5" r="3.2" />
      <path d="M3.5 19.5c.6-3.2 2.8-5 5.5-5s4.9 1.8 5.5 5M15.5 5.6a3.2 3.2 0 0 1 0 5.8M17.5 14.8c1.6.6 2.7 2.2 3 4.7" />
    </>
  ),
  start: <path d="M5 21V4m0 0h11l-2 4 2 4H5" />,
  hotovo: <path d="m5 12.5 4.5 4.5L19 7.5" />,
}

function Ikona({ children }: { children: ReactNode }) {
  return (
    <span className="ukol-ikona" aria-hidden="true">
      <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
        {children}
      </svg>
    </span>
  )
}

export function Prehled() {
  const rok = new Date().getFullYear()
  const [data, setData] = useState<Data | null>(null)
  const [chyba, setChyba] = useState<string | null>(null)

  useEffect(() => {
    // Přehled skládá souhrn z ostatních stránek; když jedna část selže, ostatní se ukážou.
    const volitelne = <T,>(cesta: string) => api<T>(cesta).catch(() => null)
    Promise.all([
      api<Vykazy>(`/api/vykazy/${rok}`),
      volitelne<Operace[]>('/api/katalog'),
      volitelne<Banka>('/api/banka'),
      volitelne<Dluznici>(`/api/dluznici/${rok}`),
      volitelne<Faktury>(`/api/faktury/${rok}`),
      volitelne<Predpisy>(`/api/predpisy/${rok}`),
    ])
      .then(([vykazy, operace, banka, dluznici, faktury, predpisy]) =>
        setData({ vykazy, operace, banka, dluznici, faktury, predpisy }),
      )
      .catch((e) => setChyba(e.message))
  }, [rok])

  if (chyba) return <Chyba text={chyba} />
  if (!data) return <Nacitani radku={6} />

  const { vykazy, operace, banka, dluznici, faktury, predpisy } = data
  const ucty = banka?.ucty.filter((u) => u.posledni_vypis) ?? []
  const naUctech = ucty.reduce((a, u) => a + (u.zustatek ?? 0), 0)
  const dluzi = dluznici?.jednotky.filter((j) => j.po_splatnosti > 0).length ?? 0
  const otevreneFaktury = faktury?.faktury.filter((f) => f.zbyva > 0 && f.stav !== 'stornovana') ?? []
  const poSplatnosti = otevreneFaktury.filter((f) => f.stav === 'po_splatnosti').length
  const mesice = predpisy?.mesice ?? []
  const zauctovanychMesicu = mesice.filter((m) => m.stav === 'zauctovano').length
  const kZauctovani = mesice.filter((m) => m.stav === 'lze')

  const okna: Okno[] = (dluznici?.jednotky ?? []).map((j) => ({
    jednotka: j.jednotka,
    stav: j.po_splatnosti > 0 ? 'dluh' : j.preplatek > 0 ? 'preplatek' : 'zaplaceno',
    popis:
      j.po_splatnosti > 0
        ? `Jednotka ${j.jednotka}: dluží ${kc(j.po_splatnosti)} po splatnosti`
        : j.preplatek > 0
          ? `Jednotka ${j.jednotka}: přeplatek ${kc(j.preplatek)}`
          : `Jednotka ${j.jednotka}: má zaplaceno`,
    odkaz: `#dluznici?jednotka=${encodeURIComponent(j.jednotka)}`,
  }))
  const sviti = okna.filter((o) => o.stav !== 'dluh').length

  const ukoly: Ukol[] = []
  if (!vykazy.pocatecni_stavy)
    ukoly.push({
      odkaz: '#pocatecni',
      nadpis: `Zadat počáteční stavy k 1. 1. ${rok}`,
      popis: 'Bez nich nesedí zůstatky účtů ani dluhy z minulých let.',
      ikona: ikony.start,
    })
  if (banka && banka.nezauctovano > 0)
    ukoly.push({
      odkaz: '#banka',
      nadpis: `Zaúčtovat ${pocet(banka.nezauctovano, 'platbu', 'platby', 'plateb')} z banky`,
      popis: 'U většiny plateb aplikace navrhne, kam patří. Stačí zkontrolovat a potvrdit.',
      ikona: ikony.banka,
    })
  if (kZauctovani.length > 0)
    ukoly.push({
      odkaz: '#predpisy',
      nadpis: `Zaúčtovat předpis za ${kZauctovani[0].nazev}`,
      popis: `Vlastníkům vznikne pohledávka za měsíc, celkem ${kc(kZauctovani[0].celkem)}.`,
      ikona: ikony.kalendar,
    })
  if (poSplatnosti > 0)
    ukoly.push({
      odkaz: '#faktury',
      nadpis: `${pocet(poSplatnosti, 'faktura je', 'faktury jsou', 'faktur je')} po splatnosti`,
      popis: 'Zaplaťte je v bankovnictví, potom platbu zaúčtujte na stránce Banka.',
      ton: 'chyba',
      ikona: ikony.faktura,
    })
  const staryVypis = ucty.filter(
    (u) => u.pohyby_do && Date.now() - new Date(u.pohyby_do).getTime() > 35 * 86_400_000,
  )
  if (staryVypis.length > 0)
    ukoly.push({
      odkaz: '#banka',
      nadpis: 'Nahrát novější pohyby z banky',
      popis: staryVypis.map((u) => `${u.nazev}: platby jen do ${datum(u.pohyby_do!)}`).join(' · '),
      ikona: ikony.banka,
    })
  if (dluzi > 0)
    ukoly.push({
      odkaz: '#dluznici',
      nadpis: `Projít dlužníky (${pocet(dluzi, 'jednotka', 'jednotky', 'jednotek')})`,
      popis: 'Ke každé jednotce aplikace připraví podklad pro upomínku.',
      ton: 'varovani',
      ikona: ikony.lide,
    })

  return (
    <>
      <section className="uvod">
        <div>
          <p className="nadtitulek">{pozdrav()}</p>
          <h1>
            Hospodaření <em>{rok}</em>
          </h1>
          <p>
            {vykazy.pocet_zapisu === 0
              ? `Za rok ${rok} zatím není nic zaúčtováno.`
              : `Zaúčtováno ${pocet(vykazy.pocet_zapisu, 'zápis', 'zápisy', 'zápisů')}. `}
            {ukoly.length > 0
              ? 'Níže najdete, co je potřeba udělat.'
              : vykazy.pocet_zapisu > 0 && 'Všechno je zaúčtované.'}
            {vykazy.pocatecni_stavy && (
              <>
                {' '}
                <a href="#pocatecni">Počáteční stavy k 1. 1. {rok}</a>
              </>
            )}
          </p>
        </div>
        {okna.length > 0 && (
          <figure className="uvod-dum">
            <Dum okna={okna} />
            <figcaption>
              Svítí {sviti} z {okna.length} {okna.length === 1 ? 'okna' : 'oken'} · okno = jednotka
            </figcaption>
          </figure>
        )}
      </section>

      <div className="dlazdice-mrizka">
        <a className="dlazdice" href="#banka">
          <span className="dlazdice-popis">Na účtech SVJ</span>
          {ucty.length > 0 ? (
            <>
              <span className="dlazdice-hodnota">{kc(naUctech)}</span>
              {ucty.length > 1 && (
                <ul className="ucty-mini">
                  {ucty.map((u) => (
                    <li key={u.ucel}>
                      <span>{u.nazev}</span>
                      <span>{kc(u.zustatek ?? 0)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </>
          ) : (
            <>
              <span className="dlazdice-hodnota">–</span>
              <span className="dlazdice-pod">Zůstatek ukáže první výpis z banky.</span>
            </>
          )}
        </a>

        <a className={`dlazdice ${dluzi > 0 ? 'ton-varovani' : 'ton-uspech'}`} href="#dluznici">
          <span className="dlazdice-popis">Vlastníci dluží po splatnosti</span>
          <span className="dlazdice-hodnota">
            {dluznici ? kc(dluznici.celkem_po_splatnosti) : '–'}
          </span>
          <span className="dlazdice-pod">
            {dluzi > 0 ? pocet(dluzi, 'jednotka', 'jednotky', 'jednotek') : 'Nikdo nedluží'}
          </span>
        </a>

        <a className={`dlazdice ${poSplatnosti > 0 ? 'ton-chyba' : ''}`} href="#faktury">
          <span className="dlazdice-popis">Faktury k zaplacení</span>
          <span className="dlazdice-hodnota">{faktury ? kc(faktury.k_uhrade) : '–'}</span>
          <span className="dlazdice-pod">
            {otevreneFaktury.length === 0
              ? 'Žádná nečeká'
              : `${pocet(otevreneFaktury.length, 'faktura', 'faktury', 'faktur')}${poSplatnosti ? `, ${poSplatnosti} po splatnosti` : ''}`}
          </span>
        </a>

        <a className="dlazdice" href="#predpisy">
          <span className="dlazdice-popis">Měsíční předpisy</span>
          <span className="dlazdice-hodnota">
            {zauctovanychMesicu}
            <small>z 12 měsíců</small>
          </span>
          {mesice.length > 0 && (
            <>
              <div className="rok-pruh" aria-hidden="true">
                {mesice.map((m) => (
                  <span key={m.mesic} className={m.stav} title={m.nazev} />
                ))}
              </div>
              <div className="rok-pruh-popisky" aria-hidden="true">
                <span>leden</span>
                <span>prosinec</span>
              </div>
            </>
          )}
        </a>
      </div>

      <section className="ukoly">
        <h2>Co je potřeba udělat</h2>
        {ukoly.length === 0 ? (
          <div className="vse-hotovo">
            <Ikona>{ikony.hotovo}</Ikona>
            <span>Nic nečeká. Až přijdou nové platby nebo faktury, objeví se tady.</span>
          </div>
        ) : (
          <ul>
            {ukoly.map((u) => (
              <li key={u.nadpis}>
                <a className={`ukol${u.ton ? ` ton-${u.ton}` : ''}`} href={u.odkaz}>
                  <Ikona>{u.ikona}</Ikona>
                  <span>
                    <strong>{u.nadpis}</strong>
                    <span className="tlumene">{u.popis}</span>
                  </span>
                  <span className="ukol-sipka" aria-hidden="true">
                    →
                  </span>
                </a>
              </li>
            ))}
          </ul>
        )}
      </section>

      {operace && (
        <details className="katalog">
          <summary>
            Jak aplikace účtuje <span className="tlumene">{pocet(operace.length, 'operace', 'operace', 'operací')}</span>
          </summary>
          <p className="tlumene">
            U každé operace je vidět, jestli odpovídá dosavadní praxi, nebo ji ještě musí potvrdit
            účetní.
          </p>
          <div className="tabulka-posun">
            <table>
              <thead>
                <tr>
                  <th>Oblast</th>
                  <th>Operace</th>
                  <th>Stav</th>
                </tr>
              </thead>
              <tbody>
                {operace.map((o) => (
                  <tr key={o.id}>
                    <td>{OBLAST[o.oblast] ?? o.oblast}</td>
                    <td>{o.nazev}</td>
                    <td className={`stav stav-${o.stav}`}>{STAV[o.stav] ?? o.stav}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}
    </>
  )
}
