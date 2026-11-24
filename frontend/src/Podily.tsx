import { useEffect, useState } from 'react'
import { api } from './auth'
import { odkazNaHistorii } from './odkazyHistorie'
import { kc } from './penize'
import { potvrdit } from './potvrdit'
import { Chyba, Nacitani } from './ui'

type Jednotka = { oznaceni: string; plocha: number; podil: string }
type Zmena = {
  plati_od: string
  od_mesice: string
  zdroj: string
  podily: Record<string, string>
  upravil: string
  upraveno: string | null
  upravitelna: boolean
}
type Data = {
  dnes: string
  nejdrive_od: string
  jednotky: Jednotka[]
  podle_profilu: Record<string, string>
  zmeny: Zmena[] // od nejnovější
  predpis_podle_podilu: boolean
}
type Nahled = { chyba: string | null; od_mesice: string; mesicne: Record<string, { dosud: number; nove: number }> }
type Rozpracovana = { puvodni: string | null; plati_od: string; zdroj: string; podily: Record<string, string> }

const datum = (d: string) => new Date(d).toLocaleDateString('cs-CZ')
const MESICE = ['leden', 'únor', 'březen', 'duben', 'květen', 'červen', 'červenec', 'srpen', 'září', 'říjen', 'listopad', 'prosinec']
const mesic = (d: string) => `${MESICE[Number(d.slice(5, 7)) - 1]} ${d.slice(0, 4)}`

function procent(podil: string) {
  const [a, b] = podil.split('/').map(Number)
  if (!a || !(b ?? 1)) return ''
  return `${((a / (b ?? 1)) * 100).toLocaleString('cs-CZ', { maximumFractionDigits: 3 })} %`
}

/** Podíly platné den před `plati_od`, bez upravované změny. */
function dosavadni(data: Data, plati_od: string, puvodni: string | null): Record<string, string> {
  const drivejsi = data.zmeny.find((z) => z.plati_od < plati_od && z.plati_od !== puvodni)
  return drivejsi?.podily ?? data.podle_profilu
}

/** Podíly na společných částech a jejich změny podle prohlášení vlastníka. */
export function Podily() {
  const [data, setData] = useState<Data | null>(null)
  const [chyba, setChyba] = useState<string | null>(null)
  const [uprava, setUprava] = useState<Rozpracovana | null>(null)
  const [ulozeno, setUlozeno] = useState<string | null>(null)

  useEffect(() => {
    api<Data>('/api/podily')
      .then(setData)
      .catch((e) => setChyba(e.message))
  }, [])

  if (!data) return chyba ? <Chyba text={chyba} /> : <Nacitani />

  function nova() {
    if (!data) return
    const posledni = data.zmeny[0]?.podily ?? data.podle_profilu
    setUlozeno(null)
    setUprava({ puvodni: null, plati_od: data.nejdrive_od, zdroj: '', podily: { ...posledni } })
  }

  async function smazat(z: Zmena) {
    const ano = await potvrdit({
      nadpis: `Smazat změnu podílů od ${datum(z.plati_od)}?`,
      text:
        'Hodí se jen, když byla zapsaná omylem. Předpis záloh a vyúčtování se pak budou počítat s dosavadními podíly. ' +
        'V historii změn zůstane záznam, kdo ji smazal.',
      ano: 'Smazat',
    })
    if (!ano) return
    setChyba(null)
    try {
      setData(await api<Data>(`/api/podily/${z.plati_od}`, { method: 'DELETE' }))
      setUlozeno(null)
    } catch (e) {
      setChyba((e as Error).message)
    }
  }

  if (uprava)
    return (
      <Editor
        data={data}
        r={uprava}
        zmen={setUprava}
        ulozeno={(d, od) => {
          setData(d)
          setUprava(null)
          setUlozeno(od)
          window.scrollTo({ top: 0 })
        }}
      />
    )

  return (
    <>
      <p>
        <a href="#vlastnici">← Vlastníci</a>
      </p>
      <h1>Podíly na společných částech</h1>
      <p className="tlumene">
        Podíl každé jednotky na společných částech domu určuje prohlášení vlastníka. Podle podílů se dělí zálohy
        a náklady, u kterých je to v předpisu nebo ve vyúčtování nastavené. Když se prohlášení změní, zapište tady nové
        podíly s datem, od kdy platí, obvykle dnem zápisu do katastru.
      </p>
      {ulozeno && (
        <p className="uspech">
          Změna podílů je uložená.{' '}
          {data.predpis_podle_podilu ? (
            <>
              Předpis záloh s ní počítá od {datum(ulozeno)}. Vlastníkům, kterým se zálohy mění, pošlete{' '}
              <a href="#oznameni">oznámení o nové výši záloh</a>.
            </>
          ) : (
            'Předpis záloh se nemění, žádná jeho složka se nedělí podle podílů. Nové podíly použije roční vyúčtování.'
          )}
        </p>
      )}

      <h2>Podíly k {datum(data.dnes)}</h2>
      <div className="tabulka-posun">
        <table className="podily">
          <thead>
            <tr>
              <th>Jednotka</th>
              <th className="cislo">Podíl</th>
              <th className="cislo">V procentech</th>
            </tr>
          </thead>
          <tbody>
            {data.jednotky.map((j) => (
              <tr key={j.oznaceni}>
                <td>{j.oznaceni}</td>
                <td className="cislo">{j.podil}</td>
                <td className="cislo">{procent(j.podil)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h2>Změny podílů</h2>
      {data.zmeny.length === 0 ? (
        <p className="tlumene">Podíly se zatím neměnily. Platí podíly z nastavení společenství.</p>
      ) : (
        <div className="tabulka-posun">
          <table className="podily">
            <thead>
              <tr>
                <th>Platí od</th>
                <th>Co se změnilo</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {data.zmeny.map((z) => {
                const pred = dosavadni(data, z.plati_od, z.plati_od)
                const zmenene = data.jednotky.filter((j) => pred[j.oznaceni] !== z.podily[j.oznaceni])
                return (
                  <tr key={z.plati_od}>
                    <td>
                      {datum(z.plati_od)}
                      {z.od_mesice !== z.plati_od && (
                        <div className="tlumene">v předpisu od {datum(z.od_mesice)}</div>
                      )}
                    </td>
                    <td>
                      {zmenene.map((j) => (
                        <div key={j.oznaceni}>
                          {j.oznaceni}: {pred[j.oznaceni]} → {z.podily[j.oznaceni]}
                        </div>
                      ))}
                      <div className="tlumene">
                        {z.zdroj} · zapsal {z.upravil} ·{' '}
                        <a href={odkazNaHistorii('zmena_podilu', z.plati_od)}>historie</a>
                      </div>
                    </td>
                    <td>
                      {z.upravitelna && (
                        <span className="radek">
                          <button
                            className="vedlejsi"
                            onClick={() => {
                              setUlozeno(null)
                              setUprava({ puvodni: z.plati_od, plati_od: z.plati_od, zdroj: z.zdroj, podily: { ...z.podily } })
                            }}
                          >
                            Upravit
                          </button>
                          <button className="vedlejsi" onClick={() => smazat(z)}>
                            Smazat
                          </button>
                        </span>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
      {chyba && <p className="chyba">{chyba}</p>}
      <p>
        <button onClick={nova}>Zapsat změnu podílů</button>
      </p>
    </>
  )
}

function Editor({
  data,
  r,
  zmen,
  ulozeno,
}: {
  data: Data
  r: Rozpracovana
  zmen: (r: Rozpracovana | null) => void
  ulozeno: (d: Data, odMesice: string) => void
}) {
  const [nahled, setNahled] = useState<Nahled | null>(null)
  const [chyba, setChyba] = useState<string | null>(null)
  const [pracuji, setPracuji] = useState(false)
  const pred = dosavadni(data, r.plati_od, r.puvodni)
  const klic = JSON.stringify([r.plati_od, r.podily, r.puvodni])

  useEffect(() => {
    if (!r.plati_od) return
    const t = setTimeout(() => {
      api<Nahled>('/api/podily/nahled', {
        method: 'POST',
        json: { plati_od: r.plati_od, podily: r.podily, puvodni: r.puvodni },
      })
        .then(setNahled)
        .catch((e) => setNahled({ chyba: (e as Error).message, od_mesice: r.plati_od, mesicne: {} }))
    }, 300)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [klic])

  const mesicne = nahled && !nahled.chyba ? nahled.mesicne : {}
  const sPredpisem = data.predpis_podle_podilu && Object.keys(mesicne).length > 0

  async function ulozit(e: React.FormEvent) {
    e.preventDefault()
    if (!nahled || nahled.chyba) return
    const od = nahled.od_mesice
    const ano = await potvrdit({
      nadpis: `Uložit nové podíly od ${datum(r.plati_od)}?`,
      text: data.predpis_podle_podilu
        ? `Předpis záloh s nimi bude počítat od ${datum(od)}, roční vyúčtování podle toho, kolik měsíců v roce platily.`
        : 'Roční vyúčtování s nimi bude počítat podle toho, kolik měsíců v roce platily.',
      ano: 'Uložit',
    })
    if (!ano) return
    setPracuji(true)
    setChyba(null)
    try {
      const d = await api<Data>('/api/podily', {
        method: 'PUT',
        json: { puvodni: r.puvodni, plati_od: r.plati_od, zdroj: r.zdroj, podily: r.podily },
      })
      ulozeno(d, od)
    } catch (e) {
      setChyba((e as Error).message)
    } finally {
      setPracuji(false)
    }
  }

  return (
    <form className="uprava-predpisu" onSubmit={ulozit}>
      <h2>{r.puvodni ? `Úprava změny podílů od ${datum(r.puvodni)}` : 'Změna podílů'}</h2>
      <p className="tlumene">
        {r.puvodni
          ? 'Formulář ukazuje uloženou změnu. '
          : 'Formulář je předvyplněný dosavadními podíly, stačí přepsat ty, které se mění. '}
        Součet podílů všech jednotek musí dát přesně celek.
      </p>
      <div className="faktura-formular">
        <label>
          Platí od
          <input type="date" value={r.plati_od} onChange={(e) => zmen({ ...r, plati_od: e.target.value })} required />
          <span className="tlumene">
            Zálohy i vyúčtování počítají s podíly po celých měsících
            {nahled && nahled.od_mesice !== r.plati_od ? `, s novými až od ${datum(nahled.od_mesice)}.` : '.'}
          </span>
        </label>
        <label>
          Podle čeho
          <input
            value={r.zdroj}
            maxLength={200}
            onChange={(e) => zmen({ ...r, zdroj: e.target.value })}
            placeholder="třeba Změna prohlášení vlastníka, vklad V-1234/2026"
            required
          />
        </label>
      </div>

      <div className="tabulka-posun">
        <table className="podily">
          <thead>
            <tr>
              <th>Jednotka</th>
              <th className="cislo">Dosud</th>
              <th>Nově</th>
              {sPredpisem && <th className="cislo">Záloha měsíčně dosud</th>}
              {sPredpisem && <th className="cislo">Nově</th>}
            </tr>
          </thead>
          <tbody>
            {data.jednotky.map((j) => {
              const m = mesicne[j.oznaceni]
              return (
                <tr key={j.oznaceni}>
                  <td>{j.oznaceni}</td>
                  <td className="cislo">{pred[j.oznaceni]}</td>
                  <td>
                    <input
                      value={r.podily[j.oznaceni] ?? ''}
                      maxLength={20}
                      inputMode="numeric"
                      onChange={(e) => zmen({ ...r, podily: { ...r.podily, [j.oznaceni]: e.target.value } })}
                      aria-label={`Nový podíl jednotky ${j.oznaceni}`}
                    />
                  </td>
                  {sPredpisem && <td className="cislo">{m ? kc(m.dosud) : ''}</td>}
                  {sPredpisem && (
                    <td className="cislo">
                      {m ? kc(m.nove) : ''}
                      {m && m.nove !== m.dosud && (
                        <div className="tlumene">
                          {m.nove > m.dosud ? '+' : ''}
                          {kc(m.nove - m.dosud)}
                        </div>
                      )}
                    </td>
                  )}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      {nahled?.chyba ? (
        <p className="chyba">{nahled.chyba}</p>
      ) : (
        nahled && (
          <p className="tlumene">
            Součet podílů sedí.
            {sPredpisem
              ? ` Zálohy jsou za ${mesic(nahled.od_mesice)}, první měsíc s novými podíly.`
              : data.predpis_podle_podilu
                ? ''
                : ' Předpis záloh se nezmění, žádná jeho složka se nedělí podle podílů.'}
          </p>
        )
      )}
      {chyba && <p className="chyba">{chyba}</p>}
      <div className="radek">
        <button type="submit" disabled={pracuji || !nahled || !!nahled.chyba || !r.zdroj.trim()}>
          {pracuji ? 'Ukládám…' : 'Uložit podíly'}
        </button>
        <button type="button" className="vedlejsi" onClick={() => zmen(null)}>
          Zrušit
        </button>
      </div>
    </form>
  )
}
