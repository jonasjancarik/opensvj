import { useEffect, useState, type FormEvent } from 'react'
import { api } from './auth'
import { potvrdit } from './potvrdit'
import { Chyba, Nacitani, ZmenenoPoSchvaleni, type ZmenaPoSchvaleni } from './ui'
import './vlastnici.css'

type Organ = { kod: string; nazev: string }
type Rozhodnuti = {
  id: number
  organ: string
  datum: string
  bod: string
  nazev: string
  text: string
  hlasovani: string
  ulozeni: string
  popis: string
  upravil: string
}
type Polozka = {
  klic: string
  skupina: string
  nazev: string
  popis: string
  rozhodnuti_id: number | null
  zmeneno_po_schvaleni: ZmenaPoSchvaleni | null
}
type Data = { dnes: string; organy: Organ[]; rozhodnuti: Rozhodnuti[]; polozky: Polozka[] }
type Udaje = Omit<Rozhodnuti, 'id' | 'popis' | 'upravil'>

const datum = (d: string) => new Date(d).toLocaleDateString('cs-CZ')

export function RozhodnutiOrganu() {
  const [data, setData] = useState<Data | null>(null)
  const [chyba, setChyba] = useState<string | null>(null)
  const [upravovane, setUpravovane] = useState<number | 'nove' | null>(null)

  useEffect(() => {
    api<Data>('/api/rozhodnuti').then(setData).catch((e) => setChyba(e.message))
  }, [])

  if (!data) return chyba ? <Chyba text={chyba} /> : <Nacitani />

  const bez = data.polozky.filter((p) => p.rozhodnuti_id === null).length
  const zmenene = data.polozky.filter((p) => p.zmeneno_po_schvaleni).length
  const skupiny = [...new Set(data.polozky.map((p) => p.skupina))]

  async function prirad(klic: string, rozhodnuti_id: number | null) {
    setChyba(null)
    try {
      setData(await api<Data>('/api/rozhodnuti/prirazeni', { method: 'PUT', json: { klic, rozhodnuti_id } }))
    } catch (e) {
      setChyba((e as Error).message)
    }
  }

  async function smazat(r: Rozhodnuti) {
    const dokladalo = data!.polozky.filter((p) => p.rozhodnuti_id === r.id).length
    const ok = await potvrdit({
      nadpis: 'Smazat rozhodnutí?',
      text:
        `${r.popis} zmizí z evidence.` +
        (dokladalo ? ` ${dokladalo === 1 ? 'Jedna položka' : `Položky (${dokladalo})`}, které dokládalo, budou zase bez doloženého rozhodnutí.` : ''),
      ano: 'Smazat',
    })
    if (!ok) return
    setChyba(null)
    try {
      setData(await api<Data>(`/api/rozhodnuti/${r.id}`, { method: 'DELETE' }))
    } catch (e) {
      setChyba((e as Error).message)
    }
  }

  return (
    <>
      <h1>Rozhodnutí orgánů</h1>
      <p className="tlumene">
        Usnesení shromáždění a výboru, o která se opírá výše záloh, klíče vyúčtování a další volby
        společenství. Když se vlastník nebo kontrola zeptá, proč se platí právě tolik, najdete tu, kdo
        o tom rozhodl, kdy a kde je zápis uložený.
      </p>

      <h2>Co má mít doložené rozhodnutí</h2>
      {bez > 0 || zmenene > 0 ? (
        <p className="upozorneni">
          {bez > 0 &&
            `${bez === 1 ? 'Jedna položka nemá' : bez < 5 ? `${bez} položky nemají` : `${bez} položek nemá`} doložené rozhodnutí. `}
          {zmenene > 0 &&
            (zmenene === 1
              ? 'Jedna položka se změnila po schválení, takže rozhodnutí pro ni přestalo platit. '
              : `Položky (${zmenene}) se změnily po schválení, takže rozhodnutí pro ně přestalo platit. `)}
          Uzávěrka roku na to upozorní.
        </p>
      ) : (
        <p className="uspech">Všechno má doložené rozhodnutí.</p>
      )}
      {data.rozhodnuti.length === 0 && (
        <p className="tlumene">Nejdřív zapište rozhodnutí níže, pak ho tu půjde přiřadit.</p>
      )}
      {chyba && <p className="chyba">{chyba}</p>}
      {skupiny.map((sk) => (
        <div key={sk}>
          <h3>{sk}</h3>
          <div className="tabulka-posun">
            <table className="vlastnici polozky-rozhodnuti">
              <tbody>
                {data.polozky
                  .filter((p) => p.skupina === sk)
                  .map((p) => (
                    <tr key={p.klic}>
                      <td>
                        {p.nazev}
                        {p.popis && (
                          <>
                            <br />
                            <span className="tlumene">{p.popis}</span>
                          </>
                        )}
                        {p.zmeneno_po_schvaleni && (
                          <ZmenenoPoSchvaleni zmena={p.zmeneno_po_schvaleni}>
                            <p>
                              Schválení přestalo platit. Když rozhodnutí pokrývá i novou podobu, potvrďte ho znovu.
                              Jinak vyberte nové rozhodnutí.
                            </p>
                            <div className="radek">
                              <button className="vedlejsi" onClick={() => prirad(p.klic, p.rozhodnuti_id)}>
                                Rozhodnutí platí i pro změnu
                              </button>
                            </div>
                          </ZmenenoPoSchvaleni>
                        )}
                      </td>
                      <td>
                        <select
                          aria-label={`Rozhodnutí: ${p.nazev}`}
                          value={p.rozhodnuti_id ?? ''}
                          disabled={data.rozhodnuti.length === 0}
                          onChange={(e) => prirad(p.klic, e.target.value ? Number(e.target.value) : null)}
                        >
                          <option value="">bez doloženého rozhodnutí</option>
                          {data.rozhodnuti.map((r) => (
                            <option key={r.id} value={r.id}>
                              {r.popis}
                            </option>
                          ))}
                        </select>
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}
      <p className="tlumene">
        Když se v nastavení SVJ změní klíč nebo volba, položka se tu objeví znovu jako nová a čeká na
        nové rozhodnutí. Když se po schválení změní předpis záloh, rozhodnutí u něj zůstane, ale přestane platit,
        dokud ho znovu nepotvrdíte.
      </p>

      <h2>Zapsaná rozhodnutí</h2>
      <div className="radek">
        <button onClick={() => setUpravovane(upravovane === 'nove' ? null : 'nove')}>Zapsat rozhodnutí</button>
      </div>
      {upravovane === 'nove' && (
        <FormularRozhodnuti
          data={data}
          ulozeno={(d) => (setData(d), setUpravovane(null))}
          zrusit={() => setUpravovane(null)}
        />
      )}
      {data.rozhodnuti.length === 0 ? (
        <p className="tlumene">Zatím tu žádné rozhodnutí není.</p>
      ) : (
        <div className="osoby">
          {data.rozhodnuti.map((r) =>
            upravovane === r.id ? (
              <div key={r.id} className="osoba">
                <FormularRozhodnuti
                  data={data}
                  r={r}
                  ulozeno={(d) => (setData(d), setUpravovane(null))}
                  zrusit={() => setUpravovane(null)}
                />
              </div>
            ) : (
              <div key={r.id} className="osoba">
                <h3>{r.nazev}</h3>
                <dl>
                  <dt>Kdo rozhodl</dt>
                  <dd>
                    {data.organy.find((o) => o.kod === r.organ)?.nazev ?? r.organ}, {datum(r.datum)}
                    {r.bod && `, bod ${r.bod}`}
                  </dd>
                  {r.hlasovani && (
                    <>
                      <dt>Hlasování</dt>
                      <dd>{r.hlasovani}</dd>
                    </>
                  )}
                  {r.text && (
                    <>
                      <dt>Znění</dt>
                      <dd>{r.text}</dd>
                    </>
                  )}
                  <dt>Zápis</dt>
                  <dd>{r.ulozeni || <span className="tlumene">neuvedeno, kde je uložený</span>}</dd>
                  <dt>Dokládá</dt>
                  <dd>
                    {data.polozky
                      .filter((p) => p.rozhodnuti_id === r.id)
                      .map((p) => p.nazev)
                      .join('\n') || <span className="tlumene">zatím nic</span>}
                  </dd>
                </dl>
                <div className="radek">
                  <button className="vedlejsi" onClick={() => setUpravovane(r.id)}>
                    Opravit
                  </button>
                  <button className="vedlejsi" onClick={() => smazat(r)}>
                    Smazat
                  </button>
                </div>
              </div>
            ),
          )}
        </div>
      )}
    </>
  )
}

function FormularRozhodnuti({
  data,
  r,
  ulozeno,
  zrusit,
}: {
  data: Data
  r?: Rozhodnuti
  ulozeno: (d: Data) => void
  zrusit: () => void
}) {
  const [u, setU] = useState<Udaje>(
    r
      ? { organ: r.organ, datum: r.datum, bod: r.bod, nazev: r.nazev, text: r.text, hlasovani: r.hlasovani, ulozeni: r.ulozeni }
      : { organ: 'shromazdeni', datum: data.dnes, bod: '', nazev: '', text: '', hlasovani: '', ulozeni: '' },
  )
  const [pracuji, setPracuji] = useState(false)
  const [chyba, setChyba] = useState<string | null>(null)

  async function ulozit(e: FormEvent) {
    e.preventDefault()
    setPracuji(true)
    setChyba(null)
    try {
      ulozeno(await api<Data>(r ? `/api/rozhodnuti/${r.id}` : '/api/rozhodnuti', { method: r ? 'PUT' : 'POST', json: u }))
    } catch (e) {
      setChyba((e as Error).message)
    } finally {
      setPracuji(false)
    }
  }

  return (
    <form className="vlastnictvi-formular" onSubmit={ulozit}>
      {!r && <h3>Nové rozhodnutí</h3>}
      <div className="faktura-formular">
        <label>
          Kdo rozhodl
          <select value={u.organ} onChange={(e) => setU({ ...u, organ: e.target.value })}>
            {data.organy.map((o) => (
              <option key={o.kod} value={o.kod}>
                {o.nazev}
              </option>
            ))}
          </select>
        </label>
        <label>
          Kdy
          <input type="date" value={u.datum} onChange={(e) => setU({ ...u, datum: e.target.value })} required />
        </label>
        <label>
          Bod programu
          <input value={u.bod} onChange={(e) => setU({ ...u, bod: e.target.value })} placeholder="třeba 4" />
        </label>
        <label className="cely-radek">
          O čem se rozhodlo
          <input value={u.nazev} onChange={(e) => setU({ ...u, nazev: e.target.value })} placeholder="třeba Výše záloh od 1. 3. 2026" required />
        </label>
        <label className="cely-radek">
          Znění usnesení
          <textarea value={u.text} onChange={(e) => setU({ ...u, text: e.target.value })} rows={3} />
        </label>
        <label>
          Hlasování
          <input value={u.hlasovani} onChange={(e) => setU({ ...u, hlasovani: e.target.value })} placeholder="třeba pro 68 % hlasů" />
        </label>
        <label>
          Kde je zápis uložený
          <input value={u.ulozeni} onChange={(e) => setU({ ...u, ulozeni: e.target.value })} placeholder="třeba šanon Shromáždění 2026" />
        </label>
      </div>
      <div className="radek">
        <button type="submit" disabled={pracuji || !u.nazev.trim()}>
          {pracuji ? 'Ukládám…' : 'Uložit'}
        </button>
        <button type="button" className="vedlejsi" onClick={zrusit}>
          Zrušit
        </button>
        {chyba && <span className="chyba">{chyba}</span>}
      </div>
    </form>
  )
}
