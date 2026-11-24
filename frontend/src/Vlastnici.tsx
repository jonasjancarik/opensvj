import { useEffect, useState, type FormEvent } from 'react'
import { api } from './auth'
import { kc } from './penize'
import { potvrdit } from './potvrdit'
import { Chyba, Nacitani } from './ui'
import './vlastnici.css'

export type Osoba = {
  id: number
  jmeno: string
  ico: string | null
  adresa: string
  email: string | null
  telefon: string | null
  ucet: string | null
  souhlas_email: string | null
  poznamka: string
  upravil: string
  upraveno: string
}
type Clen = { osoba_id: number; podil: string | null }
type Vlastnictvi = {
  id: number
  plati_od: string
  plati_do: string | null
  zdroj: string
  vlastnici: Clen[]
  upravil: string
}
type Jednotka = { jednotka: string; plocha: number; podil: string; vlastnictvi: Vlastnictvi[] }
type Data = { dnes: string; jednotky: Jednotka[]; osoby: Osoba[] }

/** Vlastník do hlavičky dopisu, jak ho posílá backend u upomínek, oznámení a vyúčtování. */
export type Adresat = { jmeno: string; adresa: string; email: string | null; souhlas_email: boolean }

const datum = (d: string) => new Date(d).toLocaleDateString('cs-CZ')
const plocha = (setiny: number) => `${(setiny / 100).toLocaleString('cs-CZ')} m²`

function platne(j: Jednotka, dnes: string): Vlastnictvi | undefined {
  return j.vlastnictvi.find((v) => v.plati_od <= dnes && (v.plati_do === null || dnes <= v.plati_do))
}

function jmena(v: Vlastnictvi, osoby: Map<number, Osoba>) {
  return v.vlastnici.map((c) => osoby.get(c.osoba_id)?.jmeno ?? '?').join(', ')
}

/** Hlavička dopisu: jména a adresa vlastníků, nebo aspoň číslo jednotky. */
export function HlavickaVlastnika({ jednotka, vlastnici }: { jednotka: string; vlastnici: Adresat[] }) {
  if (vlastnici.length === 0) return <p>Vlastník jednotky {jednotka}</p>
  const adresy = [...new Set(vlastnici.map((v) => v.adresa.trim()).filter(Boolean))]
  return (
    <p className="adresat">
      {vlastnici.map((v) => v.jmeno).join(', ')}
      {adresy.map((a) => (
        <span key={a}>
          {a.split('\n').map((radek, i) => (
            <span key={i}>
              <br />
              {radek}
            </span>
          ))}
        </span>
      ))}
      <br />
      <span className="tlumene">vlastník jednotky {jednotka}</span>
    </p>
  )
}

/** Upozornění nad tiskem, když některé jednotce chybí zapsaný vlastník. */
export function ChybiVlastnici({ jednotky }: { jednotky: { vlastnici: Adresat[] }[] }) {
  const bez = jednotky.filter((j) => j.vlastnici.length === 0).length
  if (bez === 0) return null
  return (
    <p className="tlumene neni-v-tisku">
      {bez === jednotky.length
        ? 'Aplikace zatím nezná vlastníky, v dopise bude jen číslo jednotky.'
        : `U ${bez === 1 ? 'jedné jednotky' : `${bez} jednotek`} chybí zapsaný vlastník, v dopise bude jen číslo jednotky.`}{' '}
      Vlastníky doplníte na stránce <a href="#vlastnici">Vlastníci</a>.
    </p>
  )
}

export function Vlastnici() {
  const [data, setData] = useState<Data | null>(null)
  const [chyba, setChyba] = useState<string | null>(null)
  const [vybrana, setVybrana] = useState<string | null>(null)

  useEffect(() => {
    api<Data>('/api/vlastnici').then(setData).catch((e) => setChyba(e.message))
  }, [])

  if (!data) return chyba ? <Chyba text={chyba} /> : <Nacitani />

  const osoby = new Map(data.osoby.map((o) => [o.id, o]))
  const jednotka = data.jednotky.find((j) => j.jednotka === vybrana)
  if (jednotka) {
    return (
      <DetailJednotky
        data={data}
        j={jednotka}
        osoby={osoby}
        zmena={setData}
        zpet={() => {
          setVybrana(null)
          window.scrollTo({ top: 0 })
        }}
      />
    )
  }

  const bez = data.jednotky.filter((j) => !platne(j, data.dnes)).length

  return (
    <>
      <h1>Vlastníci jednotek</h1>
      <p className="tlumene">
        Vlastníky zapisujte podle katastru nemovitostí. Jejich jména a adresy se pak objeví
        v upomínkách, oznámeních o zálohách a vyúčtováních. Když u vlastníka vyplníte číslo
        účtu, aplikace pozná jeho platby, i když zapomene na variabilní symbol. Podíly jednotek na společných částech
        a jejich změny jsou na stránce <a href="#podily">Podíly na společných částech</a>.
      </p>
      {bez > 0 && (
        <p className="upozorneni">
          {bez === data.jednotky.length
            ? 'Zatím tu není zapsaný žádný vlastník. Začněte kliknutím na jednotku.'
            : `${bez === 1 ? 'Jedna jednotka nemá' : `${bez} jednotek nemá`} zapsaného vlastníka.`}
        </p>
      )}
      <div className="tabulka-posun">
        <table className="vlastnici">
          <thead>
            <tr>
              <th>Jednotka</th>
              <th>Vlastník</th>
              <th>Kontakt</th>
              <th>Vlastní od</th>
            </tr>
          </thead>
          <tbody>
            {data.jednotky.map((j) => {
              const v = platne(j, data.dnes)
              const lide = v ? v.vlastnici.map((c) => osoby.get(c.osoba_id)).filter((o) => o !== undefined) : []
              return (
                <tr key={j.jednotka}>
                  <td>
                    <button className="odkaz" onClick={() => setVybrana(j.jednotka)}>
                      {j.jednotka}
                    </button>
                    <br />
                    <span className="tlumene">{plocha(j.plocha)}</span>
                  </td>
                  <td>{v ? jmena(v, osoby) : <span className="tlumene">nezapsáno</span>}</td>
                  <td>
                    {lide.map((o) => (
                      <div key={o.id} className="kontakt">
                        {o.email ?? (o.adresa ? o.adresa.split('\n')[0] : <span className="tlumene">bez kontaktu</span>)}
                      </div>
                    ))}
                  </td>
                  <td>{v ? datum(v.plati_od) : ''}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </>
  )
}

function DetailJednotky({
  data,
  j,
  osoby,
  zmena,
  zpet,
}: {
  data: Data
  j: Jednotka
  osoby: Map<number, Osoba>
  zmena: (d: Data) => void
  zpet: () => void
}) {
  const [upravuji, setUpravuji] = useState<number | null>(null)
  const [opravuji, setOpravuji] = useState<number | null>(null)
  const [dluhy, setDluhy] = useState<number | null>(null)
  const [chyba, setChyba] = useState<string | null>(null)
  const v = platne(j, data.dnes)
  const historie = [...j.vlastnictvi].reverse()
  const nejnovejsi = j.vlastnictvi.at(-1)
  const budouci = nejnovejsi && nejnovejsi.plati_od > data.dnes ? nejnovejsi : null

  async function smaz(x: Vlastnictvi) {
    const ok = await potvrdit({
      nadpis: 'Smazat záznam o vlastnictví?',
      text: `Záznam ${jmena(x, osoby)} od ${datum(x.plati_od)} zmizí z historie jednotky ${j.jednotka}. Hodí se jen, když byl zapsaný omylem. Osoby zůstanou v evidenci.`,
      ano: 'Smazat záznam',
    })
    if (!ok) return
    setChyba(null)
    try {
      zmena(await api<Data>(`/api/vlastnici/vlastnictvi/${x.id}`, { method: 'DELETE' }))
    } catch (e) {
      setChyba((e as Error).message)
    }
  }

  return (
    <>
      <div className="radek">
        <button className="vedlejsi" onClick={zpet}>
          Zpět na vlastníky
        </button>
      </div>
      <h1>Jednotka {j.jednotka}</h1>
      <p className="tlumene">
        Plocha {plocha(j.plocha)}, podíl na společných částech {j.podil} (<a href="#podily">změny podílů</a>).
      </p>

      <h2>{v ? `Vlastní od ${datum(v.plati_od)}` : 'Současný vlastník'}</h2>
      {!v && <p className="tlumene">Jednotka zatím nemá zapsaného vlastníka.</p>}
      {budouci && budouci !== v && (
        <p className="upozorneni">
          Od {datum(budouci.plati_od)} je zapsaný nový vlastník: {jmena(budouci, osoby)}.
        </p>
      )}
      <div className="osoby">
        {v?.vlastnici.map((c) => {
          const o = osoby.get(c.osoba_id)
          if (!o) return null
          return upravuji === o.id ? (
            <section key={o.id} className="osoba">
              <FormularOsoby
                osoba={o}
                dnes={data.dnes}
                ulozeno={(d) => {
                  zmena(d)
                  setUpravuji(null)
                }}
                zrusit={() => setUpravuji(null)}
              />
            </section>
          ) : (
            <KartaOsoby key={o.id} o={o} podil={c.podil} upravit={() => setUpravuji(o.id)} />
          )
        })}
      </div>

      <NoveVlastnictvi data={data} j={j} zmena={zmena} />

      {historie.length > 0 && (
        <>
          <h2>Historie vlastnictví</h2>
          {chyba && <p className="chyba">{chyba}</p>}
          <ul className="historie">
            {historie.map((x, i) => (
              <li key={x.id}>
                {opravuji === x.id ? (
                  <OpravaVlastnictvi
                    data={data}
                    x={x}
                    ulozeno={(d) => {
                      zmena(d)
                      setOpravuji(null)
                    }}
                    zrusit={() => setOpravuji(null)}
                  />
                ) : (
                  <>
                    <div>
                      <strong>{jmena(x, osoby)}</strong>
                      <br />
                      <span className="tlumene">
                        {datum(x.plati_od)} – {x.plati_do ? datum(x.plati_do) : 'dosud'}
                        {x.zdroj && ` · ${x.zdroj}`}
                      </span>
                    </div>
                    <div className="radek">
                      {i < historie.length - 1 && (
                        <button className="vedlejsi" onClick={() => setDluhy(dluhy === x.id ? null : x.id)}>
                          Dluhy při převodu
                        </button>
                      )}
                      <button className="vedlejsi" onClick={() => setOpravuji(x.id)}>
                        Opravit
                      </button>
                      {(i === 0 || i === historie.length - 1) && (
                        <button className="vedlejsi" onClick={() => smaz(x)}>
                          Smazat
                        </button>
                      )}
                    </div>
                    {dluhy === x.id && <DluhyPriPrevodu vlastnictviId={x.id} />}
                  </>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
    </>
  )
}

function KartaOsoby({ o, podil, upravit }: { o: Osoba; podil: string | null; upravit: () => void }) {
  return (
    <section className="osoba">
      <h3>
        {o.jmeno}
        {podil && <span className="tlumene"> · podíl {podil}</span>}
      </h3>
      <dl>
        <dt>Adresa pro doručování</dt>
        <dd>{o.adresa || <span className="tlumene">nevyplněno</span>}</dd>
        <dt>E-mail</dt>
        <dd>
          {o.email || <span className="tlumene">nevyplněno</span>}
          {o.email && (
            <span className="tlumene">
              {o.souhlas_email
                ? ` · souhlasí s doručováním e-mailem od ${datum(o.souhlas_email)}`
                : ' · dokumenty jen poštou'}
            </span>
          )}
        </dd>
        {o.telefon && (
          <>
            <dt>Telefon</dt>
            <dd>{o.telefon}</dd>
          </>
        )}
        <dt>Účet</dt>
        <dd>{o.ucet || <span className="tlumene">nevyplněno</span>}</dd>
        {o.ico && (
          <>
            <dt>IČO</dt>
            <dd>{o.ico}</dd>
          </>
        )}
        {o.poznamka && (
          <>
            <dt>Poznámka</dt>
            <dd>{o.poznamka}</dd>
          </>
        )}
      </dl>
      <button className="vedlejsi" onClick={upravit}>
        Upravit údaje
      </button>
    </section>
  )
}

type UdajeOsoby = {
  jmeno: string
  adresa: string
  email: string
  telefon: string
  ucet: string
  ico: string
  souhlas: boolean
  poznamka: string
}
const PRAZDNA_OSOBA: UdajeOsoby = {
  jmeno: '',
  adresa: '',
  email: '',
  telefon: '',
  ucet: '',
  ico: '',
  souhlas: false,
  poznamka: '',
}

function zOsoby(o: Osoba): UdajeOsoby {
  return {
    jmeno: o.jmeno,
    adresa: o.adresa,
    email: o.email ?? '',
    telefon: o.telefon ?? '',
    ucet: o.ucet ?? '',
    ico: o.ico ?? '',
    souhlas: o.souhlas_email !== null,
    poznamka: o.poznamka,
  }
}

/** Údaje osoby pro API. Souhlas s e-mailem se zapíše s dnešním datem, dřívější datum zůstane. */
function proApi(u: UdajeOsoby, dnes: string, puvodni?: Osoba) {
  return {
    jmeno: u.jmeno,
    adresa: u.adresa,
    email: u.email || null,
    telefon: u.telefon || null,
    ucet: u.ucet || null,
    ico: u.ico || null,
    souhlas_email: u.souhlas && u.email ? (puvodni?.souhlas_email ?? dnes) : null,
    poznamka: u.poznamka,
  }
}

function PoleOsoby({ u, nastav }: { u: UdajeOsoby; nastav: (u: UdajeOsoby) => void }) {
  const pole = (k: keyof UdajeOsoby) => (e: { target: { value: string } }) => nastav({ ...u, [k]: e.target.value })
  return (
    <div className="faktura-formular">
      <label>
        Jméno a příjmení, nebo název firmy
        <input value={u.jmeno} maxLength={200} onChange={pole('jmeno')} />
      </label>
      <label>
        <span>
          E-mail <span className="tlumene">(nepovinné)</span>
        </span>
        <input type="email" value={u.email} maxLength={254} onChange={pole('email')} />
      </label>
      <label className="cely-radek">
        <span>
          Adresa pro doručování <span className="tlumene">(kam posílat dopisy)</span>
        </span>
        <textarea rows={2} value={u.adresa} maxLength={500} onChange={pole('adresa')} />
      </label>
      <label>
        <span>
          Číslo účtu <span className="tlumene">(nepovinné)</span>
        </span>
        <input value={u.ucet} maxLength={40} placeholder="123456789/0800" onChange={pole('ucet')} />
      </label>
      <label>
        <span>
          Telefon <span className="tlumene">(nepovinné)</span>
        </span>
        <input type="tel" value={u.telefon} maxLength={40} onChange={pole('telefon')} />
      </label>
      <label>
        <span>
          IČO <span className="tlumene">(jen u firmy)</span>
        </span>
        <input inputMode="numeric" value={u.ico} maxLength={10} onChange={pole('ico')} />
      </label>
      <label className="zaskrtavatko">
        <input
          type="checkbox"
          checked={u.souhlas}
          disabled={!u.email.trim()}
          onChange={(e) => nastav({ ...u, souhlas: e.target.checked })}
        />
        <span>
          Souhlasí s doručováním dokumentů e-mailem
          {!u.email.trim() && <span className="tlumene"> (nejdřív vyplňte e-mail)</span>}
        </span>
      </label>
      <label className="cely-radek">
        <span>
          Poznámka <span className="tlumene">(nepovinné)</span>
        </span>
        <input value={u.poznamka} maxLength={2000} onChange={pole('poznamka')} />
      </label>
    </div>
  )
}

function FormularOsoby({
  osoba,
  dnes,
  ulozeno,
  zrusit,
}: {
  osoba: Osoba
  dnes: string
  ulozeno: (d: Data) => void
  zrusit: () => void
}) {
  const [u, setU] = useState(zOsoby(osoba))
  const [pracuji, setPracuji] = useState(false)
  const [chyba, setChyba] = useState<string | null>(null)

  async function ulozit(e: FormEvent) {
    e.preventDefault()
    setPracuji(true)
    setChyba(null)
    try {
      ulozeno(await api<Data>(`/api/vlastnici/osoby/${osoba.id}`, { method: 'PUT', json: proApi(u, dnes, osoba) }))
    } catch (e) {
      setChyba((e as Error).message)
    } finally {
      setPracuji(false)
    }
  }

  return (
    <form onSubmit={ulozit}>
      <h3>Údaje: {osoba.jmeno}</h3>
      <PoleOsoby u={u} nastav={setU} />
      <div className="radek">
        <button type="submit" disabled={pracuji || !u.jmeno.trim()}>
          {pracuji ? 'Ukládám…' : 'Uložit'}
        </button>
        <button type="button" className="vedlejsi" onClick={zrusit}>
          Zrušit
        </button>
        {chyba && <span className="chyba">{chyba}</span>}
      </div>
      <p className="tlumene">
        Změna platí i pro ostatní jednotky, které tato osoba vlastní, a pro dřívější záznamy
        v historii.
      </p>
    </form>
  )
}

type RadekClena = { osoba_id: number | null; nova: UdajeOsoby; podil: string }
const novyRadek = (): RadekClena => ({ osoba_id: null, nova: { ...PRAZDNA_OSOBA }, podil: '' })

function clenoveProApi(radky: RadekClena[], dnes: string) {
  return radky.map((r) => ({
    osoba_id: r.osoba_id,
    nova: r.osoba_id === null ? proApi(r.nova, dnes) : null,
    podil: r.podil.trim() || null,
  }))
}

function EditorClenu({
  radky,
  nastav,
  osoby,
}: {
  radky: RadekClena[]
  nastav: (r: RadekClena[]) => void
  osoby: Osoba[]
}) {
  const zmen = (i: number, r: Partial<RadekClena>) => nastav(radky.map((x, k) => (k === i ? { ...x, ...r } : x)))
  return (
    <>
      {radky.map((r, i) => (
        <fieldset key={i} className="clen">
          <legend>{radky.length > 1 ? `Vlastník ${i + 1}` : 'Vlastník'}</legend>
          <div className="faktura-formular">
            <label>
              Kdo
              <select
                value={r.osoba_id ?? ''}
                onChange={(e) => zmen(i, { osoba_id: e.target.value ? Number(e.target.value) : null })}
              >
                <option value="">Nová osoba…</option>
                {osoby.map((o) => (
                  <option key={o.id} value={o.id}>
                    {o.jmeno}
                    {o.email ? ` (${o.email})` : ''}
                  </option>
                ))}
              </select>
            </label>
            {radky.length > 1 && (
              <label>
                <span>
                  Spoluvlastnický podíl <span className="tlumene">(u manželů nechte prázdné)</span>
                </span>
                <input value={r.podil} maxLength={20} placeholder="1/2" onChange={(e) => zmen(i, { podil: e.target.value })} />
              </label>
            )}
          </div>
          {r.osoba_id === null && <PoleOsoby u={r.nova} nastav={(nova) => zmen(i, { nova })} />}
          {radky.length > 1 && (
            <button type="button" className="vedlejsi" onClick={() => nastav(radky.filter((_, k) => k !== i))}>
              Odebrat
            </button>
          )}
        </fieldset>
      ))}
      <button type="button" className="vedlejsi" onClick={() => nastav([...radky, novyRadek()])}>
        Přidat spoluvlastníka
      </button>
    </>
  )
}

function lzeOdeslatCleny(radky: RadekClena[]) {
  return radky.length > 0 && radky.every((r) => r.osoba_id !== null || r.nova.jmeno.trim())
}

function NoveVlastnictvi({ data, j, zmena }: { data: Data; j: Jednotka; zmena: (d: Data) => void }) {
  const prvni = j.vlastnictvi.length === 0
  const [otevreno, setOtevreno] = useState(prvni)
  const [od, setOd] = useState(prvni ? '' : data.dnes)
  const [zdroj, setZdroj] = useState('')
  const [radky, setRadky] = useState<RadekClena[]>([novyRadek()])
  const [pracuji, setPracuji] = useState(false)
  const [chyba, setChyba] = useState<string | null>(null)
  const [hotovo, setHotovo] = useState<string | null>(null)

  async function odeslat(e: FormEvent) {
    e.preventDefault()
    setPracuji(true)
    setChyba(null)
    setHotovo(null)
    try {
      const d = await api<Data>('/api/vlastnici/vlastnictvi', {
        method: 'POST',
        json: { jednotka: j.jednotka, plati_od: od, zdroj, vlastnici: clenoveProApi(radky, data.dnes) },
      })
      zmena(d)
      setRadky([novyRadek()])
      setZdroj('')
      setOd(data.dnes)
      setOtevreno(false)
      setHotovo(`Vlastnictví od ${datum(od)} je zapsané.`)
    } catch (e) {
      setChyba((e as Error).message)
    } finally {
      setPracuji(false)
    }
  }

  if (!otevreno) {
    return (
      <div className="radek">
        <button onClick={() => setOtevreno(true)}>Zapsat nového vlastníka</button>
        {hotovo && <span className="uspech">{hotovo}</span>}
      </div>
    )
  }

  return (
    <section className="nahrani">
      <h2>{prvni ? 'Zapsat vlastníka' : 'Zapsat nového vlastníka'}</h2>
      <p className="tlumene">
        {prvni
          ? 'Datum je den, od kdy vlastník jednotku vlastní podle katastru. Když přesné datum neznáte, napište den, od kterého aplikaci používáte.'
          : 'Po prodeji nebo jiném převodu jednotky. Rozhoduje den zápisu do katastru; dosavadnímu vlastníkovi vlastnictví skončí den předtím.'}
      </p>
      <form onSubmit={odeslat} className="vlastnictvi-formular">
        <div className="faktura-formular">
          <label>
            Vlastní od
            <input type="date" value={od} onChange={(e) => setOd(e.target.value)} />
          </label>
          <label>
            <span>
              Podle čeho <span className="tlumene">(nepovinné)</span>
            </span>
            <input
              value={zdroj}
              maxLength={500}
              placeholder="např. výpis z katastru, vklad V-1234/2025"
              onChange={(e) => setZdroj(e.target.value)}
            />
          </label>
        </div>
        <EditorClenu radky={radky} nastav={setRadky} osoby={data.osoby} />
        <div className="radek">
          <button type="submit" disabled={pracuji || !od || !lzeOdeslatCleny(radky)}>
            {pracuji ? 'Zapisuji…' : 'Zapsat vlastnictví'}
          </button>
          {!prvni && (
            <button type="button" className="vedlejsi" onClick={() => setOtevreno(false)}>
              Zrušit
            </button>
          )}
          {chyba && <span className="chyba">{chyba}</span>}
        </div>
      </form>
    </section>
  )
}

function OpravaVlastnictvi({
  data,
  x,
  ulozeno,
  zrusit,
}: {
  data: Data
  x: Vlastnictvi
  ulozeno: (d: Data) => void
  zrusit: () => void
}) {
  const [od, setOd] = useState(x.plati_od)
  const [zdroj, setZdroj] = useState(x.zdroj)
  const [radky, setRadky] = useState<RadekClena[]>(
    x.vlastnici.map((c) => ({ osoba_id: c.osoba_id, nova: { ...PRAZDNA_OSOBA }, podil: c.podil ?? '' })),
  )
  const [pracuji, setPracuji] = useState(false)
  const [chyba, setChyba] = useState<string | null>(null)

  async function ulozit(e: FormEvent) {
    e.preventDefault()
    setPracuji(true)
    setChyba(null)
    try {
      ulozeno(
        await api<Data>(`/api/vlastnici/vlastnictvi/${x.id}`, {
          method: 'PUT',
          json: { plati_od: od, zdroj, vlastnici: clenoveProApi(radky, data.dnes) },
        }),
      )
    } catch (e) {
      setChyba((e as Error).message)
    } finally {
      setPracuji(false)
    }
  }

  return (
    <form onSubmit={ulozit} className="vlastnictvi-formular oprava">
      <p className="tlumene">
        Oprava chyby v záznamu. Při změně data se posune i konec předchozího vlastnictví.
      </p>
      <div className="faktura-formular">
        <label>
          Vlastní od
          <input type="date" value={od} onChange={(e) => setOd(e.target.value)} />
        </label>
        <label>
          <span>
            Podle čeho <span className="tlumene">(nepovinné)</span>
          </span>
          <input value={zdroj} maxLength={500} onChange={(e) => setZdroj(e.target.value)} />
        </label>
      </div>
      <EditorClenu radky={radky} nastav={setRadky} osoby={data.osoby} />
      <div className="radek">
        <button type="submit" disabled={pracuji || !od || !lzeOdeslatCleny(radky)}>
          {pracuji ? 'Ukládám…' : 'Uložit opravu'}
        </button>
        <button type="button" className="vedlejsi" onClick={zrusit}>
          Zrušit
        </button>
        {chyba && <span className="chyba">{chyba}</span>}
      </div>
    </form>
  )
}

type Prevod = {
  jednotka: string
  plati_od: string
  prevodce: string
  nabyvatel: string
  volba: 'dosavadni' | 'novy'
  dluhy: { klic: string; popis: string; zbyva: number; splatnost: string | null; navrh: boolean }[]
  zapis: string | null
  zauctovano: number
}

/** Dluhy jednotky při převodu: které z nich zůstávají prodávajícímu. */
function DluhyPriPrevodu({ vlastnictviId }: { vlastnictviId: number }) {
  const [p, setP] = useState<Prevod | null>(null)
  const [vybrane, setVybrane] = useState<Set<string>>(new Set())
  const [chyba, setChyba] = useState<string | null>(null)
  const [pracuji, setPracuji] = useState(false)

  useEffect(() => {
    api<Prevod>(`/api/vlastnici/prevody/${vlastnictviId}`)
      .then((d) => {
        setP(d)
        setVybrane(new Set(d.dluhy.filter((x) => x.navrh).map((x) => x.klic)))
      })
      .catch((e) => setChyba(e.message))
  }, [vlastnictviId])

  if (!p) return chyba ? <p className="chyba">{chyba}</p> : <p className="tlumene">Načítám…</p>

  async function ponechat() {
    if (!p) return
    const celkem = p.dluhy.filter((d) => vybrane.has(d.klic)).reduce((a, d) => a + d.zbyva, 0)
    const ok = await potvrdit({
      nadpis: 'Ponechat dluhy prodávajícímu?',
      text: `Dluh ${kc(celkem)} se přesune z jednotky ${p.jednotka} na prodávajícího (${p.prevodce}). Kupujícímu se z jeho dluhů odečte a dál se bude vymáhat po prodávajícím.`,
      ano: 'Zaúčtovat',
    })
    if (!ok) return
    setPracuji(true)
    setChyba(null)
    try {
      setP(await api<Prevod>(`/api/vlastnici/prevody/${vlastnictviId}`, { method: 'POST', json: { klice: [...vybrane] } }))
    } catch (e) {
      setChyba((e as Error).message)
    } finally {
      setPracuji(false)
    }
  }

  return (
    <div className="dluhy-prevodu">
      {p.zapis ? (
        <p className="uspech">
          Prodávajícímu ({p.prevodce}) zůstal dluh {kc(p.zauctovano)}, zápis {p.zapis}. Je vidět
          na stránce Předpisy mezi dluhy dřívějších vlastníků. Opravit ho jde stornem zápisu na
          stránce Deník.
        </p>
      ) : p.dluhy.length === 0 ? (
        <p className="tlumene">Jednotka teď nemá žádné nezaplacené dluhy.</p>
      ) : (
        <>
          <p className="tlumene">
            Dluhy prodávajícího přecházejí na kupujícího, pokud o nich věděl nebo mohl vědět,
            typicky z potvrzení o dluzích (§ 1186 občanského zákoníku). Tady zapište jen dluhy,
            které na kupujícího nepřešly; ty se pak budou vymáhat po prodávajícím. Zálohy za
            měsíc převodu platí podle nastavení společenství{' '}
            {p.volba === 'dosavadni' ? 'dosavadní vlastník' : 'nový vlastník'}.
          </p>
          <ul className="dluhy-seznam">
            {p.dluhy.map((d) => (
              <li key={d.klic}>
                <label className="zaskrtavatko">
                  <input
                    type="checkbox"
                    checked={vybrane.has(d.klic)}
                    onChange={(e) => {
                      const n = new Set(vybrane)
                      if (e.target.checked) n.add(d.klic)
                      else n.delete(d.klic)
                      setVybrane(n)
                    }}
                  />
                  <span>
                    {d.popis}
                    {d.splatnost && <span className="tlumene"> · splatné {datum(d.splatnost)}</span>}
                  </span>
                </label>
                <span>{kc(d.zbyva)}</span>
              </li>
            ))}
          </ul>
          <div className="radek">
            <button disabled={pracuji || vybrane.size === 0} onClick={ponechat}>
              {pracuji ? 'Účtuji…' : 'Ponechat vybrané dluhy prodávajícímu'}
            </button>
            {chyba && <span className="chyba">{chyba}</span>}
          </div>
        </>
      )}
    </div>
  )
}
