import { useEffect, useState, type FormEvent } from 'react'
import { api } from './auth'
import { kc, naHalire } from './penize'
import { potvrdit } from './potvrdit'
import { Chyba, Nacitani } from './ui'

type Rozhodnuti = { id: number; datum: string; popis: string }
type Predepsana = { cislo: string; datum: string; popis: string; celkem: number; splatnost: string | null }
type Data = { dnes: string; nastavena: boolean; rozhodnuti: Rozhodnuti[]; predepsane: Predepsana[] }

const datum = (d: string) => new Date(d).toLocaleDateString('cs-CZ')

/** Mimořádná záloha pro všechny jednotky podle podílů (#mimoradna-zaloha). */
export function MimoradnaZaloha() {
  const [data, setData] = useState<Data | null>(null)
  const [chyba, setChyba] = useState<string | null>(null)

  useEffect(() => {
    api<Data>('/api/mimoradne-zalohy')
      .then(setData)
      .catch((e) => setChyba(e.message))
  }, [])

  if (!data) return chyba ? <Chyba text={chyba} /> : <Nacitani />

  return (
    <>
      <p>
        <a href="#predpisy">← Předpisy</a>
      </p>
      <h1>Mimořádná záloha</h1>
      <p className="tlumene">
        Jednorázový příspěvek na konkrétní opravu nebo investici, o kterém rozhodlo shromáždění. Celková částka se
        rozdělí na jednotky podle podílů na společných částech platných v den předpisu. Každé jednotce vznikne dluh se
        splatností, kterou určilo shromáždění, a bude vidět na stránce Dlužníci. Peníze jdou do fondu oprav, vedené
        zvlášť od běžných záloh.
      </p>
      {data.nastavena ? (
        <Formular data={data} setData={setData} />
      ) : (
        <p className="upozorneni">
          Společenství nemá v nastavení účet pro mimořádné zálohy. Požádejte správce aplikace o jeho doplnění.
        </p>
      )}

      <h2>Předepsané mimořádné zálohy</h2>
      {data.predepsane.length === 0 ? (
        <p className="tlumene">Zatím žádné.</p>
      ) : (
        <div className="tabulka-posun">
          <table className="mimoradne-zalohy">
            <thead>
              <tr>
                <th>Předepsáno</th>
                <th>Na co a podle čeho</th>
                <th className="cislo">Celkem</th>
                <th>Splatnost</th>
                <th>Zápis</th>
              </tr>
            </thead>
            <tbody>
              {data.predepsane.map((p) => (
                <tr key={p.cislo}>
                  <td>{datum(p.datum)}</td>
                  <td>{p.popis}</td>
                  <td className="cislo">{kc(p.celkem)}</td>
                  <td>{p.splatnost ? datum(p.splatnost) : ''}</td>
                  <td>{p.cislo}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="tlumene">Opravit předepsanou zálohu jde stornem jejího zápisu na stránce Deník.</p>
    </>
  )
}

function Formular({ data, setData }: { data: Data; setData: (d: Data) => void }) {
  const [ucel, setUcel] = useState('')
  const [castka, setCastka] = useState('')
  const [den, setDen] = useState(data.dnes)
  const [splatnost, setSplatnost] = useState('')
  const [rozhodnuti, setRozhodnuti] = useState('')
  const [casti, setCasti] = useState<Record<string, number> | null>(null)
  const [chyba, setChyba] = useState<string | null>(null)
  const [hotovo, setHotovo] = useState<string | null>(null)
  const [pracuji, setPracuji] = useState(false)

  const celkem = naHalire(castka.trim())
  const platnaCastka = celkem !== null && celkem > 0

  useEffect(() => {
    if (!platnaCastka || !den) return
    const t = window.setTimeout(() => {
      api<{ casti: Record<string, number> }>('/api/mimoradne-zalohy/nahled', {
        method: 'POST',
        json: { celkem, datum: den },
      })
        .then((n) => setCasti(n.casti))
        .catch((e) => setChyba(e.message))
    }, 300)
    return () => window.clearTimeout(t)
  }, [celkem, den, platnaCastka])

  const lze = platnaCastka && !!den && !!splatnost && !!rozhodnuti && !!ucel.trim()

  async function predepsat(e: FormEvent) {
    e.preventDefault()
    if (!lze) return
    const ano = await potvrdit({
      nadpis: 'Předepsat mimořádnou zálohu?',
      text:
        `Všem jednotkám vznikne dluh, dohromady ${kc(celkem!)}, splatný ${datum(splatnost)}. ` +
        'Opravit to půjde jen stornem v Deníku.',
      ano: 'Předepsat',
    })
    if (!ano) return
    setPracuji(true)
    setChyba(null)
    try {
      setData(
        await api<Data>('/api/mimoradne-zalohy', {
          method: 'POST',
          json: { celkem, datum: den, splatnost, rozhodnuti_id: Number(rozhodnuti), ucel },
        }),
      )
      setHotovo(`Mimořádná záloha ${kc(celkem!)} je předepsaná.`)
      setUcel('')
      setCastka('')
      setCasti(null)
    } catch (e) {
      setChyba((e as Error).message)
    } finally {
      setPracuji(false)
    }
  }

  return (
    <form className="interni-doklad" onSubmit={predepsat}>
      <h2>Nová mimořádná záloha</h2>
      <div className="interni-doklad-pole">
        <label>
          Na co
          <input
            value={ucel}
            onChange={(e) => setUcel(e.target.value)}
            maxLength={150}
            placeholder="třeba výměna oken"
          />
        </label>
        <label>
          Celková částka za dům
          <input
            value={castka}
            onChange={(e) => {
              setCastka(e.target.value)
              setHotovo(null)
            }}
            inputMode="decimal"
          />
        </label>
        <label>
          Rozhodnutí shromáždění
          <select value={rozhodnuti} onChange={(e) => setRozhodnuti(e.target.value)}>
            <option value="">Vyberte…</option>
            {data.rozhodnuti.map((r) => (
              <option key={r.id} value={r.id}>
                {r.popis}
              </option>
            ))}
          </select>
        </label>
        <label>
          Den předpisu
          <input type="date" value={den} onChange={(e) => setDen(e.target.value)} />
        </label>
        <label>
          Splatná do
          <input type="date" value={splatnost} onChange={(e) => setSplatnost(e.target.value)} />
        </label>
      </div>
      {data.rozhodnuti.length === 0 && (
        <p className="upozorneni">
          Zatím není zapsané žádné rozhodnutí shromáždění. Zapište ho na stránce{' '}
          <a href="#rozhodnuti">Rozhodnutí</a>.
        </p>
      )}
      {platnaCastka && casti && (
        <div className="tabulka-posun">
          <table className="mimoradne-zalohy">
            <thead>
              <tr>
                <th>Jednotka</th>
                <th className="cislo">Záloha</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(casti).map(([j, c]) => (
                <tr key={j}>
                  <td>{j}</td>
                  <td className="cislo">{kc(c)}</td>
                </tr>
              ))}
              <tr className="soucet">
                <td>Celkem</td>
                <td className="cislo">{kc(Object.values(casti).reduce((a, c) => a + c, 0))}</td>
              </tr>
            </tbody>
          </table>
        </div>
      )}
      <div className="radek">
        <button disabled={!lze || pracuji}>{pracuji ? 'Předepisuji…' : 'Předepsat mimořádnou zálohu'}</button>
        {hotovo && <span className="uspech">{hotovo}</span>}
        {chyba && <span className="chyba">{chyba}</span>}
      </div>
    </form>
  )
}
