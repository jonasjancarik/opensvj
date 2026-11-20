import { useEffect, useState, type FormEvent } from 'react'
import { api } from './auth'
import { potvrdit } from './potvrdit'
import { Chyba, Nacitani } from './ui'
import './vlastnici.css'

type Druh = { kod: string; nazev: string; jednotka: string }
type Odecet = { id: number; datum: string; stav: string; zdroj: string; upravil: string }
type Meridlo = {
  id: number
  jednotka: string | null
  druh: string
  vyrobni_cislo: string
  umisteni: string
  osazeno_od: string
  odstraneno_do: string | null
  nahrazuje_id: number | null
  poznamka: string
  odecty: Odecet[]
}
type Data = { dnes: string; jednotky: string[]; druhy: Druh[]; meridla: Meridlo[] }
type Cast = { meridlo_id: number; vyrobni_cislo: string; od: Odecet | null; do: Odecet | null; spotreba: string | null }
type Spotreba = { jednotka: string | null; druh: string; spotreba: string | null; casti: Cast[]; upozorneni: string[] }

const datum = (d: string) => new Date(d).toLocaleDateString('cs-CZ')
const cislo = (s: string) => Number(s).toLocaleString('cs-CZ', { maximumFractionDigits: 3 })
const kde = (j: string | null) => j ?? 'Dům'
const posledni = (m: Meridlo) => m.odecty[m.odecty.length - 1]
const vProvozu = (m: Meridlo, den: string) => m.osazeno_od <= den && (m.odstraneno_do === null || den <= m.odstraneno_do)

export function Meridla() {
  const [data, setData] = useState<Data | null>(null)
  const [chyba, setChyba] = useState<string | null>(null)
  const [vybrane, setVybrane] = useState<number | null>(null)
  const [rezim, setRezim] = useState<'odecty' | 'nove' | null>(null)

  useEffect(() => {
    api<Data>('/api/meridla').then(setData).catch((e) => setChyba(e.message))
  }, [])

  if (!data) return chyba ? <Chyba text={chyba} /> : <Nacitani />

  const druhy = new Map(data.druhy.map((d) => [d.kod, d]))
  const meridlo = data.meridla.find((m) => m.id === vybrane)
  if (meridlo) {
    return (
      <DetailMeridla
        data={data}
        m={meridlo}
        druhy={druhy}
        zmena={setData}
        zpet={() => {
          setVybrane(null)
          window.scrollTo({ top: 0 })
        }}
      />
    )
  }

  return (
    <>
      <h1>Měřidla a odečty</h1>
      <p className="tlumene">
        Vodoměry, měřiče tepla a indikátory topných nákladů v jednotkách i společná měřidla domu.
        Odečty se zapisují hromadně k jednomu dni, obvykle k 31. 12. Ze dvou odečtů aplikace spočítá
        roční spotřebu, i když se během roku měřidlo vyměnilo. Rozúčtování tepla a vody podle
        vyhlášky dělá zúčtovatel; odečty mu slouží jako podklad a pomohou zkontrolovat jeho výsledky.
      </p>
      <div className="radek">
        <button onClick={() => setRezim(rezim === 'odecty' ? null : 'odecty')} disabled={data.meridla.length === 0}>
          Zapsat odečty
        </button>
        <button className="vedlejsi" onClick={() => setRezim(rezim === 'nove' ? null : 'nove')}>
          Přidat měřidlo
        </button>
      </div>
      {rezim === 'odecty' && (
        <HromadnyOdecet data={data} druhy={druhy} hotovo={(d) => (setData(d), setRezim(null))} zrusit={() => setRezim(null)} />
      )}
      {rezim === 'nove' && (
        <NoveMeridlo data={data} hotovo={(d) => (setData(d), setRezim(null))} zrusit={() => setRezim(null)} />
      )}

      <h2>Měřidla</h2>
      {data.meridla.length === 0 ? (
        <p className="tlumene">Zatím tu není žádné měřidlo. Začněte tlačítkem Přidat měřidlo.</p>
      ) : (
        <div className="tabulka-posun">
          <table>
            <thead>
              <tr>
                <th>Kde</th>
                <th>Druh</th>
                <th>Výrobní číslo</th>
                <th>V provozu</th>
                <th className="cislo">Poslední odečet</th>
              </tr>
            </thead>
            <tbody>
              {data.meridla.map((m) => {
                const o = posledni(m)
                const d = druhy.get(m.druh)
                return (
                  <tr key={m.id}>
                    <td>
                      {kde(m.jednotka)}
                      {m.umisteni && <span className="tlumene"> · {m.umisteni}</span>}
                    </td>
                    <td>{d?.nazev ?? m.druh}</td>
                    <td>
                      <button className="odkaz" onClick={() => setVybrane(m.id)}>
                        {m.vyrobni_cislo}
                      </button>
                    </td>
                    <td>
                      {datum(m.osazeno_od)} – {m.odstraneno_do ? datum(m.odstraneno_do) : 'dosud'}
                    </td>
                    <td className="cislo">
                      {o ? (
                        <>
                          {cislo(o.stav)} {d?.jednotka}
                          <br />
                          <span className="tlumene">{datum(o.datum)}</span>
                        </>
                      ) : (
                        <span className="tlumene">žádný</span>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {data.meridla.length > 0 && <SpotrebaZaRok dnes={data.dnes} druhy={druhy} otevrit={setVybrane} />}
    </>
  )
}

function HromadnyOdecet({
  data,
  druhy,
  hotovo,
  zrusit,
}: {
  data: Data
  druhy: Map<string, Druh>
  hotovo: (d: Data) => void
  zrusit: () => void
}) {
  const [den, setDen] = useState(data.dnes)
  const [zdroj, setZdroj] = useState('')
  const [stavy, setStavy] = useState<Record<number, string>>({})
  const [pracuji, setPracuji] = useState(false)
  const [chyba, setChyba] = useState<string | null>(null)
  const meridla = data.meridla.filter((m) => vProvozu(m, den))
  const vyplneno = meridla.filter((m) => (stavy[m.id] ?? '').trim()).length

  async function ulozit(e: FormEvent) {
    e.preventDefault()
    setPracuji(true)
    setChyba(null)
    try {
      const vstup = meridla.map((m) => ({ meridlo_id: m.id, stav: stavy[m.id] ?? '' })).filter((x) => x.stav.trim())
      hotovo(await api<Data>('/api/meridla/odecty', { method: 'POST', json: { datum: den, zdroj, stavy: vstup } }))
    } catch (e) {
      setChyba((e as Error).message)
    } finally {
      setPracuji(false)
    }
  }

  return (
    <form className="vlastnictvi-formular" onSubmit={ulozit}>
      <h2>Zapsat odečty</h2>
      <div className="faktura-formular">
        <label>
          Ke dni
          <input type="date" value={den} onChange={(e) => setDen(e.target.value)} required />
        </label>
        <label>
          Kdo odečítal
          <input value={zdroj} onChange={(e) => setZdroj(e.target.value)} placeholder="třeba výbor, samoodečet, firma" />
        </label>
      </div>
      {meridla.length === 0 ? (
        <p className="tlumene">K tomuto dni není žádné měřidlo v provozu.</p>
      ) : (
        <div className="tabulka-posun">
          <table>
            <thead>
              <tr>
                <th>Kde</th>
                <th>Měřidlo</th>
                <th className="cislo">Předchozí stav</th>
                <th>Nový stav</th>
              </tr>
            </thead>
            <tbody>
              {meridla.map((m) => {
                const pred = m.odecty.filter((o) => o.datum <= den).pop()
                const d = druhy.get(m.druh)
                return (
                  <tr key={m.id}>
                    <td>{kde(m.jednotka)}</td>
                    <td>
                      {d?.nazev ?? m.druh} <span className="tlumene">{m.vyrobni_cislo}</span>
                    </td>
                    <td className="cislo">
                      {pred ? (
                        <>
                          {cislo(pred.stav)} {d?.jednotka}
                          <br />
                          <span className="tlumene">{datum(pred.datum)}</span>
                        </>
                      ) : (
                        <span className="tlumene">žádný</span>
                      )}
                    </td>
                    <td>
                      <input
                        inputMode="decimal"
                        aria-label={`Nový stav měřidla ${m.vyrobni_cislo}`}
                        value={stavy[m.id] ?? ''}
                        onChange={(e) => setStavy({ ...stavy, [m.id]: e.target.value })}
                        size={10}
                      />{' '}
                      {d?.jednotka}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
      <p className="tlumene">
        Prázdná pole se přeskočí. Když už k tomuto dni odečet je, nový stav ho přepíše.
      </p>
      <div className="radek">
        <button type="submit" disabled={pracuji || vyplneno === 0}>
          {pracuji ? 'Ukládám…' : vyplneno ? `Uložit ${vyplneno} ${vyplneno === 1 ? 'odečet' : vyplneno < 5 ? 'odečty' : 'odečtů'}` : 'Uložit odečty'}
        </button>
        <button type="button" className="vedlejsi" onClick={zrusit}>
          Zrušit
        </button>
        {chyba && <span className="chyba">{chyba}</span>}
      </div>
    </form>
  )
}

function NoveMeridlo({ data, hotovo, zrusit }: { data: Data; hotovo: (d: Data) => void; zrusit: () => void }) {
  const [u, setU] = useState({
    jednotka: data.jednotky[0] ?? '',
    druh: data.druhy[0]?.kod ?? '',
    vyrobni_cislo: '',
    umisteni: '',
    osazeno_od: data.dnes,
    pocatecni_stav: '',
  })
  const [pracuji, setPracuji] = useState(false)
  const [chyba, setChyba] = useState<string | null>(null)
  const jednotkaMereni = data.druhy.find((d) => d.kod === u.druh)?.jednotka

  async function ulozit(e: FormEvent) {
    e.preventDefault()
    setPracuji(true)
    setChyba(null)
    try {
      hotovo(
        await api<Data>('/api/meridla', {
          method: 'POST',
          json: { ...u, jednotka: u.jednotka || null, pocatecni_stav: u.pocatecni_stav.trim() || null },
        }),
      )
    } catch (e) {
      setChyba((e as Error).message)
    } finally {
      setPracuji(false)
    }
  }

  return (
    <form className="vlastnictvi-formular" onSubmit={ulozit}>
      <h2>Nové měřidlo</h2>
      <div className="faktura-formular">
        <label>
          Kde
          <select value={u.jednotka} onChange={(e) => setU({ ...u, jednotka: e.target.value })}>
            {data.jednotky.map((j) => (
              <option key={j} value={j}>
                jednotka {j}
              </option>
            ))}
            <option value="">společné měřidlo domu</option>
          </select>
        </label>
        <label>
          Druh
          <select value={u.druh} onChange={(e) => setU({ ...u, druh: e.target.value })}>
            {data.druhy.map((d) => (
              <option key={d.kod} value={d.kod}>
                {d.nazev} ({d.jednotka})
              </option>
            ))}
          </select>
        </label>
        <label>
          Výrobní číslo
          <input value={u.vyrobni_cislo} onChange={(e) => setU({ ...u, vyrobni_cislo: e.target.value })} required />
        </label>
        <label>
          Umístění
          <input value={u.umisteni} onChange={(e) => setU({ ...u, umisteni: e.target.value })} placeholder="třeba koupelna" />
        </label>
        <label>
          Osazeno od
          <input type="date" value={u.osazeno_od} onChange={(e) => setU({ ...u, osazeno_od: e.target.value })} required />
        </label>
        <label>
          Stav při osazení{jednotkaMereni ? ` (${jednotkaMereni})` : ''}
          <input inputMode="decimal" value={u.pocatecni_stav} onChange={(e) => setU({ ...u, pocatecni_stav: e.target.value })} />
        </label>
      </div>
      <p className="tlumene">
        U měřidla, které v domě už je, zadejte jako den osazení začátek evidence a stav k tomu dni.
      </p>
      <div className="radek">
        <button type="submit" disabled={pracuji || !u.vyrobni_cislo.trim()}>
          {pracuji ? 'Ukládám…' : 'Přidat měřidlo'}
        </button>
        <button type="button" className="vedlejsi" onClick={zrusit}>
          Zrušit
        </button>
        {chyba && <span className="chyba">{chyba}</span>}
      </div>
    </form>
  )
}

function DetailMeridla({
  data,
  m,
  druhy,
  zmena,
  zpet,
}: {
  data: Data
  m: Meridlo
  druhy: Map<string, Druh>
  zmena: (d: Data) => void
  zpet: () => void
}) {
  const [rezim, setRezim] = useState<'uprava' | 'vymena' | null>(null)
  const [chyba, setChyba] = useState<string | null>(null)
  const d = druhy.get(m.druh)
  const puvodni = data.meridla.find((x) => x.id === m.nahrazuje_id)
  const nahrada = data.meridla.find((x) => x.nahrazuje_id === m.id)

  async function akce(cesta: string, nadpis: string, text: string, ano: string, poSmazani = false) {
    if (!(await potvrdit({ nadpis, text, ano }))) return
    setChyba(null)
    try {
      zmena(await api<Data>(cesta, { method: 'DELETE' }))
      if (poSmazani) zpet()
    } catch (e) {
      setChyba((e as Error).message)
    }
  }

  return (
    <>
      <p>
        <button className="odkaz" onClick={zpet}>
          Zpět na měřidla
        </button>
      </p>
      <h1>
        {d?.nazev ?? m.druh} {m.vyrobni_cislo}
      </h1>
      <p className="tlumene">
        {m.jednotka ? `Jednotka ${m.jednotka}` : 'Společné měřidlo domu'}
        {m.umisteni && `, ${m.umisteni}`}. V provozu {datum(m.osazeno_od)} –{' '}
        {m.odstraneno_do ? datum(m.odstraneno_do) : 'dosud'}.
        {puvodni && ` Nahradilo měřidlo ${puvodni.vyrobni_cislo}.`}
        {nahrada && ` Nahradilo ho měřidlo ${nahrada.vyrobni_cislo}.`}
      </p>
      {m.poznamka && <p>{m.poznamka}</p>}
      <div className="radek">
        <button className="vedlejsi" onClick={() => setRezim(rezim === 'uprava' ? null : 'uprava')}>
          Opravit údaje
        </button>
        {m.odstraneno_do === null && (
          <button className="vedlejsi" onClick={() => setRezim(rezim === 'vymena' ? null : 'vymena')}>
            Vyměnit měřidlo
          </button>
        )}
        {!nahrada && (
          <button
            className="vedlejsi"
            onClick={() =>
              akce(
                `/api/meridla/${m.id}`,
                'Smazat měřidlo?',
                puvodni
                  ? `Měřidlo ${m.vyrobni_cislo} i jeho odečty zmizí z evidence a měřidlo ${puvodni.vyrobni_cislo} bude zase v provozu.`
                  : `Měřidlo ${m.vyrobni_cislo} i jeho odečty zmizí z evidence. Hodí se jen pro měřidlo zapsané omylem.`,
                'Smazat',
                true,
              )
            }
          >
            Smazat
          </button>
        )}
        {chyba && <span className="chyba">{chyba}</span>}
      </div>
      {rezim === 'uprava' && <UpravaMeridla m={m} hotovo={(x) => (zmena(x), setRezim(null))} zrusit={() => setRezim(null)} />}
      {rezim === 'vymena' && (
        <Vymena m={m} dnes={data.dnes} jednotka={d?.jednotka} hotovo={(x) => (zmena(x), setRezim(null))} zrusit={() => setRezim(null)} />
      )}

      <h2>Odečty</h2>
      {m.odecty.length === 0 ? (
        <p className="tlumene">Zatím žádný odečet. Zapíšete ho na stránce měřidel tlačítkem Zapsat odečty.</p>
      ) : (
        <div className="tabulka-posun">
          <table>
            <thead>
              <tr>
                <th>Den</th>
                <th className="cislo">Stav</th>
                <th className="cislo">Od předchozího</th>
                <th>Kdo odečítal</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {m.odecty.map((o, i) => (
                <tr key={o.id}>
                  <td>{datum(o.datum)}</td>
                  <td className="cislo">
                    {cislo(o.stav)} {d?.jednotka}
                  </td>
                  <td className="cislo">{i > 0 ? `${cislo(String(Number(o.stav) - Number(m.odecty[i - 1].stav)))} ${d?.jednotka}` : ''}</td>
                  <td>{o.zdroj || <span className="tlumene">neuvedeno</span>}</td>
                  <td className="vpravo">
                    <button
                      className="vedlejsi"
                      onClick={() =>
                        akce(
                          `/api/meridla/odecty/${o.id}`,
                          'Smazat odečet?',
                          `Odečet ${cislo(o.stav)} ${d?.jednotka ?? ''} z ${datum(o.datum)} zmizí z evidence.`,
                          'Smazat',
                        )
                      }
                    >
                      Smazat
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}

function UpravaMeridla({ m, hotovo, zrusit }: { m: Meridlo; hotovo: (d: Data) => void; zrusit: () => void }) {
  const [u, setU] = useState({ vyrobni_cislo: m.vyrobni_cislo, umisteni: m.umisteni, osazeno_od: m.osazeno_od, poznamka: m.poznamka })
  const [pracuji, setPracuji] = useState(false)
  const [chyba, setChyba] = useState<string | null>(null)

  async function ulozit(e: FormEvent) {
    e.preventDefault()
    setPracuji(true)
    setChyba(null)
    try {
      hotovo(await api<Data>(`/api/meridla/${m.id}`, { method: 'PUT', json: u }))
    } catch (e) {
      setChyba((e as Error).message)
    } finally {
      setPracuji(false)
    }
  }

  return (
    <form className="vlastnictvi-formular" onSubmit={ulozit}>
      <div className="faktura-formular">
        <label>
          Výrobní číslo
          <input value={u.vyrobni_cislo} onChange={(e) => setU({ ...u, vyrobni_cislo: e.target.value })} required />
        </label>
        <label>
          Umístění
          <input value={u.umisteni} onChange={(e) => setU({ ...u, umisteni: e.target.value })} />
        </label>
        <label>
          Osazeno od
          <input type="date" value={u.osazeno_od} onChange={(e) => setU({ ...u, osazeno_od: e.target.value })} required />
        </label>
        <label className="cely-radek">
          Poznámka
          <textarea value={u.poznamka} onChange={(e) => setU({ ...u, poznamka: e.target.value })} rows={2} />
        </label>
      </div>
      <div className="radek">
        <button type="submit" disabled={pracuji || !u.vyrobni_cislo.trim()}>
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

function Vymena({
  m,
  dnes,
  jednotka,
  hotovo,
  zrusit,
}: {
  m: Meridlo
  dnes: string
  jednotka?: string
  hotovo: (d: Data) => void
  zrusit: () => void
}) {
  const [u, setU] = useState({ datum: dnes, konecny_stav: '', vyrobni_cislo: '', pocatecni_stav: '0' })
  const [pracuji, setPracuji] = useState(false)
  const [chyba, setChyba] = useState<string | null>(null)
  const j = jednotka ? ` (${jednotka})` : ''

  async function ulozit(e: FormEvent) {
    e.preventDefault()
    setPracuji(true)
    setChyba(null)
    try {
      hotovo(await api<Data>(`/api/meridla/${m.id}/vymena`, { method: 'POST', json: u }))
    } catch (e) {
      setChyba((e as Error).message)
    } finally {
      setPracuji(false)
    }
  }

  return (
    <form className="vlastnictvi-formular" onSubmit={ulozit}>
      <h2>Výměna měřidla</h2>
      <p className="tlumene">
        Staré měřidlo se k tomuto dni uzavře s konečným stavem a nové začne počítat od svého
        počátečního stavu. Roční spotřeba se pak sečte z obou.
      </p>
      <div className="faktura-formular">
        <label>
          Den výměny
          <input type="date" value={u.datum} onChange={(e) => setU({ ...u, datum: e.target.value })} required />
        </label>
        <label>
          Konečný stav starého{j}
          <input inputMode="decimal" value={u.konecny_stav} onChange={(e) => setU({ ...u, konecny_stav: e.target.value })} required />
        </label>
        <label>
          Výrobní číslo nového
          <input value={u.vyrobni_cislo} onChange={(e) => setU({ ...u, vyrobni_cislo: e.target.value })} required />
        </label>
        <label>
          Počáteční stav nového{j}
          <input inputMode="decimal" value={u.pocatecni_stav} onChange={(e) => setU({ ...u, pocatecni_stav: e.target.value })} required />
        </label>
      </div>
      <div className="radek">
        <button type="submit" disabled={pracuji || !u.konecny_stav.trim() || !u.vyrobni_cislo.trim()}>
          {pracuji ? 'Ukládám…' : 'Zapsat výměnu'}
        </button>
        <button type="button" className="vedlejsi" onClick={zrusit}>
          Zrušit
        </button>
        {chyba && <span className="chyba">{chyba}</span>}
      </div>
    </form>
  )
}

function SpotrebaZaRok({ dnes, druhy, otevrit }: { dnes: string; druhy: Map<string, Druh>; otevrit: (id: number) => void }) {
  const letos = Number(dnes.slice(0, 4))
  // Letošní spotřeba jde spočítat až po odečtech na konci roku.
  const [rok, setRok] = useState(dnes.slice(5) === '12-31' ? letos : letos - 1)
  const [radky, setRadky] = useState<Spotreba[] | null>(null)
  const [chyba, setChyba] = useState<string | null>(null)

  useEffect(() => {
    setRadky(null)
    api<Spotreba[]>(`/api/meridla/spotreba?rok=${rok}`).then(setRadky).catch((e) => setChyba(e.message))
  }, [rok])

  return (
    <>
      <h2>Spotřeba za rok</h2>
      <div className="radek">
        <label>
          Rok{' '}
          <select value={rok} onChange={(e) => setRok(Number(e.target.value))}>
            {[letos, letos - 1, letos - 2, letos - 3].map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
        </label>
      </div>
      <p className="tlumene">
        Spotřeba je rozdíl odečtu kolem 31. 12. předchozího roku a odečtu kolem 31. 12. tohoto roku.
        U měřidla osazeného nebo vyměněného během roku se počítá od stavu při osazení.
      </p>
      {chyba && <Chyba text={chyba} />}
      {!radky ? (
        !chyba && <Nacitani />
      ) : radky.length === 0 ? (
        <p className="tlumene">V roce {rok} nebylo v provozu žádné měřidlo.</p>
      ) : (
        <div className="tabulka-posun">
          <table>
            <thead>
              <tr>
                <th>Kde</th>
                <th>Druh</th>
                <th className="cislo">Spotřeba</th>
                <th>Z odečtů</th>
              </tr>
            </thead>
            <tbody>
              {radky.map((x) => {
                const d = druhy.get(x.druh)
                return (
                  <tr key={`${x.jednotka}-${x.druh}`}>
                    <td>{kde(x.jednotka)}</td>
                    <td>{d?.nazev ?? x.druh}</td>
                    <td className="cislo">
                      {x.spotreba !== null ? `${cislo(x.spotreba)} ${d?.jednotka ?? ''}` : <span className="tlumene">nejde spočítat</span>}
                    </td>
                    <td>
                      {x.casti.map((c) => (
                        <div key={c.meridlo_id}>
                          <button className="odkaz" onClick={() => otevrit(c.meridlo_id)}>
                            {c.vyrobni_cislo}
                          </button>
                          <span className="tlumene">
                            {': '}
                            {c.od ? `${cislo(c.od.stav)} (${datum(c.od.datum)})` : '?'} →{' '}
                            {c.do ? `${cislo(c.do.stav)} (${datum(c.do.datum)})` : '?'}
                          </span>
                        </div>
                      ))}
                      {x.upozorneni.map((u) => (
                        <div key={u} className="upozorneni">
                          {u}
                        </div>
                      ))}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}
