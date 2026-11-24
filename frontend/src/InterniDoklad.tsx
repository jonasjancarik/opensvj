import { useState, type FormEvent } from 'react'
import { api } from './auth'
import { kc, naHalire } from './penize'

type Pole = {
  klic: string
  popis: string
  typ: string
  moznosti: { hodnota: string; nazev: string }[] | null
}
type Operace = {
  id: string
  nazev: string
  kdy: string
  stav: string
  napoveda: string
  kroky: { id: string; nazev: string }[]
  pole: Pole[]
}
type Nabidka = { operace: Operace[]; nedostupne: string[] }
type Radek = {
  strana: 'md' | 'd'
  ucet: string
  nazev_uctu: string
  castka: number
  dimenze: Record<string, string>
}

const CASTKY = ['castka', 'castka_nula', 'castka_se_znamenkem']

/** Rok, jehož konec se právě účtuje: do konce března ještě minulý rok. */
function rokUzaverky() {
  const dnes = new Date()
  return dnes.getMonth() < 3 ? dnes.getFullYear() - 1 : dnes.getFullYear()
}

function datumKroku(krok: string): string | null {
  if (krok === 'k_rozvahovemu_dni') return `${rokUzaverky()}-12-31`
  if (krok === 'rozpusteni') return `${rokUzaverky() + 1}-01-01`
  return null
}

function dnes() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

/**
 * Interní doklad podle operace z katalogu: pro věci, které nemají vlastní stránku
 * (časové rozlišení, zásoby, dotace, odměny výboru…). Před zaúčtováním ukáže, na které
 * účty se zápis zapíše.
 */
export function InterniDoklad({ zauctovano }: { zauctovano: (cislo: string, rok: number) => void }) {
  const [nabidka, setNabidka] = useState<Nabidka | null>(null)
  const [otevreno, setOtevreno] = useState(false)
  const [operace, setOperace] = useState('')
  const [krok, setKrok] = useState('')
  const [hodnoty, setHodnoty] = useState<Record<string, string>>({})
  const [datum, setDatum] = useState(dnes)
  const [popis, setPopis] = useState('')
  const [nahled, setNahled] = useState<Radek[] | null>(null)
  const [chyba, setChyba] = useState<string | null>(null)
  const [pracuji, setPracuji] = useState(false)
  const op = nabidka?.operace.find((o) => o.id === operace)

  async function otevrit() {
    setOtevreno(true)
    if (!nabidka) {
      try {
        const n = await api<Nabidka>('/api/interni-doklady')
        n.operace.sort((a, b) => a.nazev.localeCompare(b.nazev, 'cs'))
        setNabidka(n)
      } catch (e) {
        setChyba((e as Error).message)
      }
    }
  }

  function zmenit(zmena: () => void) {
    zmena()
    setNahled(null)
    setChyba(null)
  }

  function vybratOperaci(id: string) {
    const nova = nabidka?.operace.find((o) => o.id === id)
    zmenit(() => {
      setOperace(id)
      setHodnoty({})
      setPopis(nova?.nazev ?? '')
      const prvniKrok = nova?.kroky.length === 1 ? nova.kroky[0].id : ''
      setKrok(prvniKrok)
      setDatum(datumKroku(prvniKrok) ?? dnes())
    })
  }

  function vstupy(): Record<string, string | number> | null {
    if (!op) return null
    const v: Record<string, string | number> = {}
    for (const p of op.pole) {
      const text = (hodnoty[p.klic] ?? '').trim()
      if (CASTKY.includes(p.typ)) {
        const h = naHalire(text === '' && p.typ === 'castka_nula' ? '0' : text)
        if (h === null) return null
        v[p.klic] = h
      } else {
        if (!text) return null
        v[p.klic] = text
      }
    }
    return v
  }

  const v = vstupy()
  const lzeZkontrolovat = !!op && !!v && (op.kroky.length === 0 || !!krok)

  async function zkontrolovat(e: FormEvent) {
    e.preventDefault()
    if (!lzeZkontrolovat) return
    setPracuji(true)
    setChyba(null)
    try {
      setNahled(
        await api<Radek[]>('/api/interni-doklady/nahled', {
          method: 'POST',
          json: { operace, krok: krok || null, vstupy: v },
        }),
      )
    } catch (e) {
      setChyba((e as Error).message)
    } finally {
      setPracuji(false)
    }
  }

  async function zauctovat() {
    setPracuji(true)
    setChyba(null)
    try {
      const z = await api<{ cislo: string; rok: number }>('/api/interni-doklady', {
        method: 'POST',
        json: { operace, krok: krok || null, vstupy: v, datum, popis },
      })
      setOtevreno(false)
      setOperace('')
      setNahled(null)
      zauctovano(z.cislo, z.rok)
    } catch (e) {
      setChyba((e as Error).message)
    } finally {
      setPracuji(false)
    }
  }

  if (!otevreno)
    return (
      <div className="radek">
        <button className="vedlejsi" onClick={otevrit}>
          Zaúčtovat interní doklad
        </button>
      </div>
    )

  return (
    <form className="interni-doklad" onSubmit={zkontrolovat}>
      <h2>Interní doklad</h2>
      <p className="tlumene">
        Pro účetní případy, které nemají vlastní stránku. Předpisy, faktury, platby, úrok
        z prodlení, odpis dluhu nebo daň účtujte na jejich stránkách, kde aplikace hlídá víc.
      </p>
      {!nabidka && !chyba && <p className="tlumene">Načítám…</p>}
      {nabidka && (
        <label>
          Co účtujete
          <select value={operace} onChange={(e) => vybratOperaci(e.target.value)}>
            <option value="">Vyberte…</option>
            {nabidka.operace.map((o) => (
              <option key={o.id} value={o.id}>
                {o.nazev}
              </option>
            ))}
          </select>
        </label>
      )}
      {op && (
        <>
          <p className="tlumene">
            {op.kdy} {op.napoveda}
          </p>
          {op.stav === 'overit' && (
            <p className="varovani-text">
              Tento postup zatím nepotvrdila účetní. Zápis s ní před uzávěrkou zkontrolujte.
            </p>
          )}
          {op.kroky.length > 1 && (
            <label>
              Který krok účtujete
              <select
                value={krok}
                onChange={(e) =>
                  zmenit(() => {
                    setKrok(e.target.value)
                    setDatum(datumKroku(e.target.value) ?? datum)
                  })
                }
              >
                <option value="">Vyberte…</option>
                {op.kroky.map((k) => (
                  <option key={k.id} value={k.id}>
                    {k.nazev}
                  </option>
                ))}
              </select>
            </label>
          )}
          <div className="interni-doklad-pole">
            {op.pole.map((p) => (
              <label key={p.klic}>
                {p.popis}
                {p.moznosti ? (
                  <select
                    value={hodnoty[p.klic] ?? ''}
                    onChange={(e) => zmenit(() => setHodnoty({ ...hodnoty, [p.klic]: e.target.value }))}
                  >
                    <option value="">Vyberte…</option>
                    {p.moznosti.map((m) => (
                      <option key={m.hodnota} value={m.hodnota}>
                        {m.nazev}
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    value={hodnoty[p.klic] ?? ''}
                    onChange={(e) => zmenit(() => setHodnoty({ ...hodnoty, [p.klic]: e.target.value }))}
                    inputMode={CASTKY.includes(p.typ) ? 'decimal' : undefined}
                    placeholder={p.typ === 'castka_nula' ? '0' : undefined}
                    maxLength={128}
                  />
                )}
              </label>
            ))}
            <label>
              Datum
              <input type="date" value={datum} onChange={(e) => zmenit(() => setDatum(e.target.value))} />
            </label>
            <label>
              Popis v deníku
              <input value={popis} onChange={(e) => setPopis(e.target.value)} maxLength={500} />
            </label>
          </div>
        </>
      )}
      {nahled && (
        <div className="tabulka-posun">
          <table>
            <thead>
              <tr>
                <th>Účet</th>
                <th className="cislo">Má dáti</th>
                <th className="cislo">Dal</th>
              </tr>
            </thead>
            <tbody>
              {nahled.map((r, i) => (
                <tr key={i}>
                  <td>
                    {r.ucet}{' '}
                    <span className="tlumene">{r.nazev_uctu !== r.ucet && r.nazev_uctu}</span>
                  </td>
                  <td className="cislo">{r.strana === 'md' ? kc(r.castka) : ''}</td>
                  <td className="cislo">{r.strana === 'd' ? kc(r.castka) : ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {nabidka && nabidka.nedostupne.length > 0 && !op && (
        <p className="tlumene">
          Tyto operace potřebují doplnit účty v nastavení společenství: {nabidka.nedostupne.join(', ')}.
        </p>
      )}
      <div className="radek">
        {nahled ? (
          <button type="button" disabled={pracuji || !popis.trim()} onClick={zauctovat}>
            {pracuji ? 'Účtuji…' : 'Zaúčtovat'}
          </button>
        ) : (
          <button type="submit" disabled={pracuji || !lzeZkontrolovat}>
            {pracuji ? 'Počítám…' : 'Ukázat zápis'}
          </button>
        )}
        <button type="button" className="vedlejsi" onClick={() => setOtevreno(false)}>
          Zrušit
        </button>
        {chyba && <span className="chyba">{chyba}</span>}
      </div>
    </form>
  )
}
