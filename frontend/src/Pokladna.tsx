import { useEffect, useState, type FormEvent } from 'react'
import { api } from './auth'
import { kc, naHalire } from './penize'
import { Chyba, Nacitani } from './ui'

type Polozka = {
  datum: string
  cislo: string
  doklad: string
  popis: string
  prijem: number
  vydaj: number
  zustatek: number
}
type Data = {
  rok: number
  dnes: string
  nastavena: boolean
  zustatek: number
  na_ceste: number
  polozky: Polozka[]
  jednotky: string[]
  polozky_spravy: Record<string, string>
}
type Druh = 'prijem_z_uctu' | 'vydaj' | 'platba_vlastnika'

const DRUHY: Record<Druh, string> = {
  prijem_z_uctu: 'Příjem hotovosti vybrané z účtu',
  vydaj: 'Drobný výdaj',
  platba_vlastnika: 'Vlastník platí hotově',
}
const POPISY: Record<Druh, string> = {
  prijem_z_uctu: 'Příjem hotovosti z účtu',
  vydaj: '',
  platba_vlastnika: 'Platba vlastníka v hotovosti',
}

const datum = (d: string) => new Date(d).toLocaleDateString('cs-CZ')

export function Pokladna() {
  const [letos] = useState(() => new Date().getFullYear())
  const [rok, setRok] = useState(letos)
  return (
    <>
      <h1>Pokladna</h1>
      <div className="radek">
        <label className="vyber-roku">
          Rok{' '}
          <select value={rok} onChange={(e) => setRok(Number(e.target.value))}>
            {[letos, letos - 1, letos - 2].map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
        </label>
      </div>
      <PokladnaRoku key={rok} rok={rok} />
    </>
  )
}

function PokladnaRoku({ rok }: { rok: number }) {
  const [data, setData] = useState<Data | null>(null)
  const [chyba, setChyba] = useState<string | null>(null)

  useEffect(() => {
    api<Data>(`/api/pokladna/${rok}`)
      .then(setData)
      .catch((e) => setChyba(e.message))
  }, [rok])

  if (!data) return chyba ? <Chyba text={chyba} /> : <Nacitani />
  if (!data.nastavena)
    return (
      <p className="upozorneni">
        Společenství nemá v nastavení účet pro hotovostní pokladnu. Pokud pokladnu vede, požádejte správce aplikace
        o jeho doplnění.
      </p>
    )
  return <Obsah data={data} setData={setData} />
}

function Obsah({ data, setData }: { data: Data; setData: (d: Data) => void }) {
  return (
    <>
      <p>
        {data.rok === new Date(data.dnes).getFullYear() ? 'V pokladně je' : `Na konci roku ${data.rok} bylo v pokladně`}{' '}
        <strong>{kc(data.zustatek)}</strong>.
        {data.na_ceste > 0 &&
          ` Z účtu je vybráno ${kc(data.na_ceste)}, které ještě nejsou zapsané jako příjem do pokladny.`}
      </p>
      <p className="tlumene">
        Hotovost do pokladny se dostane výběrem z účtu: výběr nejdřív zaúčtujte v Bance jako výběr hotovosti do
        pokladny a tady ho pak zapište jako příjem. Každý příjem a výdaj potřebuje pokladní doklad s podpisem; zůstatek
        pokladny se k 31. 12. ověřuje inventurou.
      </p>
      <NovyDoklad data={data} setData={setData} />

      <h2>Pokladní kniha {data.rok}</h2>
      {data.polozky.length === 0 ? (
        <p className="tlumene">V tomto roce v pokladně zatím nic není.</p>
      ) : (
        <div className="tabulka-posun">
          <table className="pokladni-kniha">
            <thead>
              <tr>
                <th>Datum</th>
                <th>Zápis</th>
                <th>Popis</th>
                <th className="cislo">Příjem</th>
                <th className="cislo">Výdaj</th>
                <th className="cislo">Zůstatek</th>
              </tr>
            </thead>
            <tbody>
              {data.polozky.map((p) => (
                <tr key={p.cislo}>
                  <td>{datum(p.datum)}</td>
                  <td>{p.cislo}</td>
                  <td>{p.popis}</td>
                  <td className="cislo">{p.prijem ? kc(p.prijem) : ''}</td>
                  <td className="cislo">{p.vydaj ? kc(p.vydaj) : ''}</td>
                  <td className="cislo">{kc(p.zustatek)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}

function NovyDoklad({ data, setData }: { data: Data; setData: (d: Data) => void }) {
  const [druh, setDruh] = useState<Druh | ''>('')
  const [castka, setCastka] = useState('')
  const [den, setDen] = useState(data.rok === new Date(data.dnes).getFullYear() ? data.dnes : `${data.rok}-12-31`)
  const [popis, setPopis] = useState('')
  const [jednotka, setJednotka] = useState('')
  const [sluzba, setSluzba] = useState('')
  const [chyba, setChyba] = useState<string | null>(null)
  const [hotovo, setHotovo] = useState<string | null>(null)
  const [pracuji, setPracuji] = useState(false)

  const halire = naHalire(castka.trim())
  const lze =
    !!druh && halire !== null && halire > 0 && !!popis.trim() && (druh !== 'platba_vlastnika' || !!jednotka)

  async function zauctovat(e: FormEvent) {
    e.preventDefault()
    if (!lze) return
    setPracuji(true)
    setChyba(null)
    setHotovo(null)
    try {
      const d = await api<Data>(`/api/pokladna/${data.rok}`, {
        method: 'POST',
        json: { druh, castka: halire, datum: den, popis, jednotka, sluzba },
      })
      setData(d)
      setHotovo(`Zapsáno: ${DRUHY[druh as Druh].toLowerCase()} ${kc(halire!)}.`)
      setDruh('')
      setCastka('')
      setPopis('')
      setJednotka('')
      setSluzba('')
    } catch (e) {
      setChyba((e as Error).message)
    } finally {
      setPracuji(false)
    }
  }

  return (
    <form className="interni-doklad" onSubmit={zauctovat}>
      <h2>Nový pokladní doklad</h2>
      <div className="interni-doklad-pole">
        <label>
          Co se stalo
          <select
            value={druh}
            onChange={(e) => {
              const d = e.target.value as Druh | ''
              setDruh(d)
              setPopis(d ? POPISY[d] : '')
              setChyba(null)
            }}
          >
            <option value="">Vyberte…</option>
            {(Object.keys(DRUHY) as Druh[]).map((d) => (
              <option key={d} value={d}>
                {DRUHY[d]}
              </option>
            ))}
          </select>
        </label>
        {druh === 'platba_vlastnika' && (
          <label>
            Za kterou jednotku
            <select value={jednotka} onChange={(e) => setJednotka(e.target.value)}>
              <option value="">Vyberte…</option>
              {data.jednotky.map((j) => (
                <option key={j} value={j}>
                  {j}
                </option>
              ))}
            </select>
          </label>
        )}
        {druh === 'vydaj' && (
          <label>
            Ze které položky správy se platí
            <select value={sluzba} onChange={(e) => setSluzba(e.target.value)}>
              <option value="">Žádná (zeptám se účetní)</option>
              {Object.entries(data.polozky_spravy).map(([k, n]) => (
                <option key={k} value={k}>
                  {n}
                </option>
              ))}
            </select>
          </label>
        )}
        <label>
          Částka
          <input value={castka} onChange={(e) => setCastka(e.target.value)} inputMode="decimal" />
        </label>
        <label>
          Datum
          <input type="date" value={den} onChange={(e) => setDen(e.target.value)} />
        </label>
        <label>
          Popis
          <input
            value={popis}
            onChange={(e) => setPopis(e.target.value)}
            maxLength={200}
            placeholder={druh === 'vydaj' ? 'Co se koupilo, třeba „žárovky do sklepa“' : undefined}
          />
        </label>
      </div>
      {druh === 'vydaj' && !sluzba && (
        <p className="tlumene">
          Výdaj bez položky správy se do vyúčtování záloh na správu nezapočte, dokud ho účetní nezařadí.
        </p>
      )}
      <div className="radek">
        <button disabled={!lze || pracuji}>{pracuji ? 'Zapisuji…' : 'Zapsat doklad'}</button>
        {hotovo && <span className="uspech">{hotovo}</span>}
        {chyba && <span className="chyba">{chyba}</span>}
      </div>
    </form>
  )
}
