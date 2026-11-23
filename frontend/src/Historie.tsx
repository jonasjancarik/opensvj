import { useEffect, useState } from 'react'
import { api } from './auth'
import { casZmeny, odkazNaHistorii } from './odkazyHistorie'
import { Chyba, Nacitani } from './ui'

type Rozdil = { pole: string; pred: string; po: string }
type Zaznam = {
  id: number
  kdy: string
  kdo: string
  jmeno: string
  druh: string
  druh_nazev: string
  klic: string
  akce: 'pridani' | 'uprava' | 'smazani'
  akce_nazev: string
  nazev: string
  duvod: string
  zmeny: Rozdil[]
}
type Data = { zaznamy: Zaznam[]; druhy: { kod: string; nazev: string }[]; dalsi: boolean }

function zAdresy() {
  const q = new URLSearchParams(window.location.hash.split('?')[1] ?? '')
  return { druh: q.get('druh') ?? '', klic: q.get('klic') ?? '' }
}

/** Historie změn mimo deník: kdo, kdy, co a proč změnil. Zápisy v deníku mají historii samy. */
export function Historie() {
  const [{ druh, klic }, setFiltr] = useState(zAdresy)
  const filtr = new URLSearchParams({ ...(druh ? { druh } : {}), ...(klic ? { klic } : {}) }).toString()
  // Načtená data patří k filtru; po změně filtru se nezobrazují, dokud nepřijdou nová.
  const [nactene, setNactene] = useState<{ filtr: string; data: Data } | null>(null)
  const [chyba, setChyba] = useState<{ filtr: string; text: string } | null>(null)
  const [nacitam, setNacitam] = useState(false)
  const data = nactene?.filtr === filtr ? nactene.data : null

  useEffect(() => {
    const zmena = () => setFiltr(zAdresy())
    window.addEventListener('hashchange', zmena)
    return () => window.removeEventListener('hashchange', zmena)
  }, [])

  useEffect(() => {
    api<Data>(`/api/historie?${filtr}`)
      .then((d) => setNactene({ filtr, data: d }))
      .catch((e) => setChyba({ filtr, text: e.message }))
  }, [filtr])

  async function starsi() {
    if (!data) return
    setNacitam(true)
    try {
      const q = new URLSearchParams(filtr)
      q.set('pred', String(data.zaznamy[data.zaznamy.length - 1].id))
      const dalsi = await api<Data>(`/api/historie?${q}`)
      setNactene({ filtr, data: { ...dalsi, zaznamy: [...data.zaznamy, ...dalsi.zaznamy] } })
    } catch (e) {
      setChyba({ filtr, text: (e as Error).message })
    } finally {
      setNacitam(false)
    }
  }

  function vybrat(novy: string) {
    window.location.hash = novy ? odkazNaHistorii(novy).slice(1) : 'historie'
  }

  return (
    <>
      <h1>Historie změn</h1>
      <p className="tlumene">
        Kdo a kdy změnil vlastníky, rozhodnutí, předpis záloh, měřidla, výsledky od zúčtovatele nebo stav účetního
        roku, a jak to vypadalo předtím. Záznamy nejde upravit ani smazat. Zaúčtované doklady se neupravují, opravují se
        stornem, takže jejich historie je v deníku.
      </p>
      <div className="historie-filtr">
        <label>
          Zobrazit změny
          <select value={druh} onChange={(e) => vybrat(e.target.value)}>
            <option value="">Všechno</option>
            {nactene?.data.druhy.map((d) => (
              <option key={d.kod} value={d.kod}>
                {d.nazev}
              </option>
            ))}
          </select>
        </label>
        {klic && (
          <p className="tlumene">
            Jen změny: {data?.zaznamy[0]?.nazev ?? klic}.{' '}
            <a href={druh ? odkazNaHistorii(druh) : '#historie'}>Ukázat všechny</a>
          </p>
        )}
      </div>
      {chyba?.filtr === filtr && <Chyba text={chyba.text} />}
      {!data && chyba?.filtr !== filtr && <Nacitani />}
      {data && data.zaznamy.length === 0 && <p className="tlumene">Zatím tu žádná změna není.</p>}
      {data && (
        <div className="historie">
          {data.zaznamy.map((z) => (
            <article key={z.id} className="historie-zaznam">
              <div className="historie-hlavicka">
                <strong>
                  {z.akce_nazev}: {z.nazev}
                </strong>
                <span className="tlumene">
                  {casZmeny(z.kdy)} · {z.jmeno || z.kdo}
                  {!druh && ` · ${z.druh_nazev}`}
                </span>
              </div>
              {z.duvod && <p>Důvod: {z.duvod}</p>}
              {z.zmeny.length > 0 && (
                <div className="tabulka-posun">
                  <table className="historie-zmeny">
                    <thead>
                      <tr>
                        <th>Údaj</th>
                        {z.akce !== 'pridani' && <th>Předtím</th>}
                        {z.akce !== 'smazani' && <th>{z.akce === 'pridani' ? 'Hodnota' : 'Nově'}</th>}
                      </tr>
                    </thead>
                    <tbody>
                      {z.zmeny.map((r) => (
                        <tr key={r.pole}>
                          <td>{r.pole}</td>
                          {z.akce !== 'pridani' && <td>{r.pred}</td>}
                          {z.akce !== 'smazani' && <td>{r.po}</td>}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </article>
          ))}
        </div>
      )}
      {data?.dalsi && (
        <div className="radek">
          <button className="vedlejsi" disabled={nacitam} onClick={starsi}>
            {nacitam ? 'Načítám…' : 'Načíst starší'}
          </button>
        </div>
      )}
    </>
  )
}
