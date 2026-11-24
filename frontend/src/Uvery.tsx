import { useEffect, useState, type FormEvent } from 'react'
import { api } from './auth'
import { kc, naHalire } from './penize'
import { potvrdit } from './potvrdit'
import { Chyba, Nacitani } from './ui'

type JednotkaUveru = { jednotka: string; podil: number; mesicne: number; zbyva: number }
type Uver = {
  id: number
  nazev: string
  cislo_uctu: string
  jistina: number
  rozhodnuti: string
  predepsano_dne: string
  prvni_splatka: string
  posledni_splatka: string
  pocet_splatek: number
  uroky_hradi: string
  platny: boolean
  zapis: string | null
  zbyva_bance: number
  nesplaceno: number
  uroky: number
  kryto: number
  jednotky: JednotkaUveru[]
}
type Data = {
  rok: number
  dnes: string
  nastaveno: boolean
  rozhodnuti: { id: number; datum: string; popis: string }[]
  polozky_spravy: Record<string, string>
  faktury: { cislo: string; dodavatel: string; zbyva: number }[]
  na_ceste: number
  nevycerpano: number
  prvni_mozna_splatka: string
  uvery: Uver[]
}

const datum = (d: string) => new Date(d).toLocaleDateString('cs-CZ')
const mesic = (d: string) => new Date(d).toLocaleDateString('cs-CZ', { month: 'long', year: 'numeric' })

function kdoPlatiUroky(data: Data, kod: string) {
  if (kod === 'fond_oprav') return 'z fondu oprav'
  if (kod === 'zaloha_na_uver') return 'ze záloh na úvěr (mimořádných záloh vlastníků)'
  return `z provozních záloh na správu (${data.polozky_spravy[kod] ?? kod})`
}

export function Uvery() {
  const [letos] = useState(() => new Date().getFullYear())
  const [rok, setRok] = useState(letos)
  return (
    <>
      <h1>Úvěry</h1>
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
      <UveryRoku key={rok} rok={rok} />
    </>
  )
}

function UveryRoku({ rok }: { rok: number }) {
  const [data, setData] = useState<Data | null>(null)
  const [chyba, setChyba] = useState<string | null>(null)

  useEffect(() => {
    api<Data>(`/api/uvery/${rok}`)
      .then(setData)
      .catch((e) => setChyba(e.message))
  }, [rok])

  if (!data) return chyba ? <Chyba text={chyba} /> : <Nacitani />
  if (!data.nastaveno)
    return (
      <p className="upozorneni">
        Společenství nemá v nastavení účty pro úvěr. Pokud si úvěr bere, požádejte správce aplikace o jejich
        doplnění.
      </p>
    )
  return (
    <>
      <p className="tlumene">
        Úvěr na opravu nebo investici schvaluje shromáždění. Vlastníci ho obvykle splácejí podle podílů na
        společných částech: podíl každé jednotky na jistině se předepíše najednou a splácí se v měsíčních
        předpisech, dokud není splacený. Fakturu za opravu zadejte na stránce Faktury jako opravu hrazenou
        z úvěru.
      </p>
      {data.nevycerpano > 0 && (
        <p>
          Ze záloh na úvěry zbývá na opravy a investice {kc(data.nevycerpano)}, které ještě nepokryla žádná
          faktura.
        </p>
      )}
      {data.uvery.map((u) => (
        <DetailUveru key={u.id} data={data} uver={u} setData={setData} />
      ))}
      <NovyUver data={data} setData={setData} />
    </>
  )
}

function DetailUveru({ data, uver: u, setData }: { data: Data; uver: Uver; setData: (d: Data) => void }) {
  const zDlouhodobych = u.uroky_hradi === 'fond_oprav' || u.uroky_hradi === 'zaloha_na_uver'
  const zbyvaPokryt = u.uroky - u.kryto
  const [chyba, setChyba] = useState<string | null>(null)
  const [pracuji, setPracuji] = useState(false)

  async function pokryt() {
    const ano = await potvrdit({
      nadpis: `Uhradit úroky za rok ${data.rok}?`,
      text: `Úroky ${kc(zbyvaPokryt)} se k 31. 12. ${data.rok} zaplatí ${kdoPlatiUroky(data, u.uroky_hradi)}, jak rozhodlo shromáždění.`,
      ano: 'Uhradit',
    })
    if (!ano) return
    setPracuji(true)
    setChyba(null)
    try {
      setData(await api<Data>(`/api/uvery/${u.id}/kryti/${data.rok}`, { method: 'POST' }))
    } catch (e) {
      setChyba((e as Error).message)
    } finally {
      setPracuji(false)
    }
  }

  return (
    <section className="uver">
      <h2>
        {u.nazev}
        {!u.platny && <span className="tlumene"> (zrušený stornem)</span>}
      </h2>
      <dl className="udaje-uveru">
        <dt>Jistina</dt>
        <dd>{kc(u.jistina)}</dd>
        <dt>Schválilo</dt>
        <dd>{u.rozhodnuti}</dd>
        <dt>Podíly jednotek předepsané</dt>
        <dd>
          {datum(u.predepsano_dne)}
          {u.zapis && <span className="tlumene"> (zápis {u.zapis})</span>}
        </dd>
        <dt>Splácí se</dt>
        <dd>
          v předpisech za {mesic(u.prvni_splatka)} až {mesic(u.posledni_splatka)}, nejvýš {u.pocet_splatek} měsíčních
          splátek
        </dd>
        <dt>Úroky platí</dt>
        <dd>{kdoPlatiUroky(data, u.uroky_hradi)}</dd>
        {u.cislo_uctu && (
          <>
            <dt>Úvěrový účet</dt>
            <dd>{u.cislo_uctu}</dd>
          </>
        )}
        <dt>Zbývá splatit bance</dt>
        <dd>
          <strong>{kc(u.zbyva_bance)}</strong>
        </dd>
        <dt>Vlastníci ještě nesplatili</dt>
        <dd>{kc(u.nesplaceno)}</dd>
        <dt>Úroky v roce {data.rok}</dt>
        <dd>{kc(u.uroky)}</dd>
      </dl>
      {u.platny && zDlouhodobych && zbyvaPokryt > 0 && (
        <div className="radek">
          <button className="vedlejsi" onClick={pokryt} disabled={pracuji}>
            Uhradit úroky za rok {data.rok} {u.uroky_hradi === 'fond_oprav' ? 'z fondu oprav' : 'ze záloh na úvěr'}
          </button>
          {chyba && <span className="chyba">{chyba}</span>}
        </div>
      )}
      {u.platny && <NovyPohyb data={data} uver={u} setData={setData} />}
      <details>
        <summary>Splátky jednotek</summary>
        <div className="tabulka-posun">
          <table className="splatky-uveru">
            <thead>
              <tr>
                <th>Jednotka</th>
                <th className="cislo">Podíl na jistině</th>
                <th className="cislo">Měsíčně</th>
                <th className="cislo">Zbývá splatit</th>
              </tr>
            </thead>
            <tbody>
              {u.jednotky.map((j) => (
                <tr key={j.jednotka}>
                  <td>{j.jednotka}</td>
                  <td className="cislo">{kc(j.podil)}</td>
                  <td className="cislo">{kc(j.mesicne)}</td>
                  <td className="cislo">{kc(j.zbyva)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="tlumene">
          Poslední splátka jednotky bývá nižší, zbytek do jejího podílu. Při prodeji jednotky zbytek přechází na
          kupujícího; potvrzení o dluzích ho uvádí.
        </p>
      </details>
    </section>
  )
}

type Druh = 'faktura' | 'uroky' | 'splatka'
const DRUHY: Record<Druh, string> = {
  faktura: 'Banka zaplatila fakturu z úvěru',
  uroky: 'Banka připsala úroky nebo poplatky',
  splatka: 'Splátka dorazila na úvěrový účet',
}

function NovyPohyb({ data, uver: u, setData }: { data: Data; uver: Uver; setData: (d: Data) => void }) {
  const [druh, setDruh] = useState<Druh | ''>('')
  const [faktura, setFaktura] = useState('')
  const [castka, setCastka] = useState('')
  const [uroky, setUroky] = useState('')
  const [poplatky, setPoplatky] = useState('')
  const [sluzba, setSluzba] = useState('')
  const [den, setDen] = useState(data.dnes)
  const [chyba, setChyba] = useState<string | null>(null)
  const [hotovo, setHotovo] = useState<string | null>(null)
  const [pracuji, setPracuji] = useState(false)

  const halire = naHalire(castka.trim())
  const halireUroku = uroky.trim() ? naHalire(uroky.trim()) : 0
  const halirePoplatku = poplatky.trim() ? naHalire(poplatky.trim()) : 0
  const lze =
    !!den &&
    (druh === 'faktura'
      ? !!faktura && halire !== null && halire > 0
      : druh === 'splatka'
        ? halire !== null && halire > 0
        : druh === 'uroky'
          ? halireUroku !== null && halirePoplatku !== null && halireUroku + halirePoplatku > 0
          : false)

  async function zauctovat(e: FormEvent) {
    e.preventDefault()
    if (!lze || !druh) return
    setPracuji(true)
    setChyba(null)
    setHotovo(null)
    const telo =
      druh === 'faktura'
        ? { faktura, castka: halire, datum: den }
        : druh === 'splatka'
          ? { castka: halire, datum: den }
          : { uroky: halireUroku, poplatky: halirePoplatku, datum: den, sluzba_poplatku: sluzba }
    try {
      setData(await api<Data>(`/api/uvery/${u.id}/${druh}?rok=${data.rok}`, { method: 'POST', json: telo }))
      setHotovo(`Zaúčtováno: ${DRUHY[druh].toLowerCase()}.`)
      setDruh('')
      setFaktura('')
      setCastka('')
      setUroky('')
      setPoplatky('')
    } catch (e) {
      setChyba((e as Error).message)
    } finally {
      setPracuji(false)
    }
  }

  return (
    <form className="interni-doklad" onSubmit={zauctovat}>
      <h3>Zapsat z výpisu úvěrového účtu</h3>
      <div className="interni-doklad-pole">
        <label>
          Co se stalo
          <select
            value={druh}
            onChange={(e) => {
              setDruh(e.target.value as Druh | '')
              setChyba(null)
              setHotovo(null)
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
        {druh === 'faktura' && (
          <label>
            Faktura
            <select
              value={faktura}
              onChange={(e) => {
                setFaktura(e.target.value)
                const f = data.faktury.find((x) => x.cislo === e.target.value)
                if (f) setCastka((f.zbyva / 100).toFixed(2).replace('.', ','))
              }}
            >
              <option value="">Vyberte…</option>
              {data.faktury.map((f) => (
                <option key={f.cislo} value={f.cislo}>
                  {f.cislo} · {f.dodavatel} · zbývá {kc(f.zbyva)}
                </option>
              ))}
            </select>
          </label>
        )}
        {(druh === 'faktura' || druh === 'splatka') && (
          <label>
            Částka
            <input value={castka} onChange={(e) => setCastka(e.target.value)} inputMode="decimal" />
          </label>
        )}
        {druh === 'uroky' && (
          <>
            <label>
              Úroky
              <input value={uroky} onChange={(e) => setUroky(e.target.value)} inputMode="decimal" />
            </label>
            <label>
              Poplatky za vedení úvěru
              <input value={poplatky} onChange={(e) => setPoplatky(e.target.value)} inputMode="decimal" />
            </label>
            <label>
              Ze které položky správy se platí poplatky
              <select value={sluzba} onChange={(e) => setSluzba(e.target.value)}>
                <option value="">Žádná (zeptám se účetní)</option>
                {Object.entries(data.polozky_spravy).map(([k, n]) => (
                  <option key={k} value={k}>
                    {n}
                  </option>
                ))}
              </select>
            </label>
          </>
        )}
        {druh && (
          <label>
            Datum na výpisu
            <input type="date" value={den} onChange={(e) => setDen(e.target.value)} />
          </label>
        )}
      </div>
      {druh === 'splatka' && (
        <p className="tlumene">
          Odchod splátky z běžného účtu se zaúčtuje v Bance jako splátka úvěru. Tady se zapíše, že peníze dorazily
          na úvěrový účet.
          {data.na_ceste > 0 ? ` Teď je na cestě ${kc(data.na_ceste)}.` : ' Teď nejsou žádné peníze na cestě.'}
        </p>
      )}
      {druh === 'faktura' && data.faktury.length === 0 && (
        <p className="upozorneni">
          Žádná faktura není k úhradě. Fakturu nejdřív zadejte na stránce <a href="#faktury">Faktury</a>.
        </p>
      )}
      {druh && (
        <div className="radek">
          <button disabled={!lze || pracuji}>{pracuji ? 'Zapisuji…' : 'Zaúčtovat'}</button>
          {chyba && <span className="chyba">{chyba}</span>}
        </div>
      )}
      {hotovo && <span className="uspech">{hotovo}</span>}
    </form>
  )
}

function NovyUver({ data, setData }: { data: Data; setData: (d: Data) => void }) {
  const [nazev, setNazev] = useState('')
  const [jistina, setJistina] = useState('')
  const [rozhodnuti, setRozhodnuti] = useState('')
  const [cisloUctu, setCisloUctu] = useState('')
  const [predepsano, setPredepsano] = useState(data.dnes)
  const [prvni, setPrvni] = useState(data.prvni_mozna_splatka.slice(0, 7))
  const [pocet, setPocet] = useState('120')
  const [uroky, setUroky] = useState('fond_oprav')
  const [nahled, setNahled] = useState<Record<string, { podil: number; mesicne: number }> | null>(null)
  const [chyba, setChyba] = useState<string | null>(null)
  const [hotovo, setHotovo] = useState<string | null>(null)
  const [pracuji, setPracuji] = useState(false)

  const halire = naHalire(jistina.trim())
  const splatek = Number(pocet)
  const platne = halire !== null && halire > 0 && !!predepsano && Number.isInteger(splatek) && splatek >= 1

  useEffect(() => {
    if (!platne) return
    const t = window.setTimeout(() => {
      api<Record<string, { podil: number; mesicne: number }>>('/api/uvery/nahled', {
        method: 'POST',
        json: { jistina: halire, predepsano_dne: predepsano, pocet_splatek: splatek },
      })
        .then(setNahled)
        .catch((e) => setChyba(e.message))
    }, 300)
    return () => window.clearTimeout(t)
  }, [halire, predepsano, splatek, platne])

  const lze = platne && !!nazev.trim() && !!rozhodnuti && !!prvni

  async function zalozit(e: FormEvent) {
    e.preventDefault()
    if (!lze) return
    const ano = await potvrdit({
      nadpis: 'Předepsat podíly na úvěru?',
      text:
        `Jednotkám se předepíšou podíly na jistině ${kc(halire!)} a splátky se přidají do měsíčních předpisů, ` +
        `poprvé do předpisu za ${mesic(`${prvni}-01`)}. Opravit to půjde stornem předpisu podílů v Deníku, ` +
        'dokud není zaúčtovaná žádná splátka.',
      ano: 'Předepsat',
    })
    if (!ano) return
    setPracuji(true)
    setChyba(null)
    try {
      setData(
        await api<Data>(`/api/uvery?rok=${data.rok}`, {
          method: 'POST',
          json: {
            nazev,
            jistina: halire,
            rozhodnuti_id: Number(rozhodnuti),
            cislo_uctu: cisloUctu,
            predepsano_dne: predepsano,
            prvni_splatka: `${prvni}-01`,
            pocet_splatek: splatek,
            uroky_hradi: uroky,
          },
        }),
      )
      setHotovo(`Úvěr „${nazev.trim()}“ je založený a podíly jednotek předepsané.`)
      setNazev('')
      setJistina('')
      setNahled(null)
    } catch (e) {
      setChyba((e as Error).message)
    } finally {
      setPracuji(false)
    }
  }

  return (
    <form className="interni-doklad" onSubmit={zalozit}>
      <h2>Nový úvěr</h2>
      <div className="interni-doklad-pole">
        <label>
          Na co
          <input value={nazev} onChange={(e) => setNazev(e.target.value)} maxLength={150} placeholder="třeba zateplení fasády" />
        </label>
        <label>
          Jistina
          <input value={jistina} onChange={(e) => setJistina(e.target.value)} inputMode="decimal" />
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
          <span>
            Číslo úvěrového účtu <span className="tlumene">(nepovinné)</span>
          </span>
          <input value={cisloUctu} onChange={(e) => setCisloUctu(e.target.value)} maxLength={64} />
        </label>
        <label>
          Den předpisu podílů
          <input type="date" value={predepsano} onChange={(e) => setPredepsano(e.target.value)} />
        </label>
        <label>
          První splátka v předpisu za
          <input type="month" value={prvni} min={data.prvni_mozna_splatka.slice(0, 7)} onChange={(e) => setPrvni(e.target.value)} />
        </label>
        <label>
          Počet měsíčních splátek
          <input value={pocet} onChange={(e) => setPocet(e.target.value)} inputMode="numeric" />
        </label>
        <label>
          Úroky platí
          <select value={uroky} onChange={(e) => setUroky(e.target.value)}>
            <option value="fond_oprav">Fond oprav</option>
            <option value="zaloha_na_uver">Mimořádné zálohy na úvěr</option>
            {Object.entries(data.polozky_spravy).map(([k, n]) => (
              <option key={k} value={k}>
                Provozní zálohy: {n}
              </option>
            ))}
          </select>
        </label>
      </div>
      {data.rozhodnuti.length === 0 && (
        <p className="upozorneni">
          Zatím není zapsané žádné rozhodnutí shromáždění. Zapište ho na stránce <a href="#rozhodnuti">Rozhodnutí</a>.
        </p>
      )}
      <p className="tlumene">
        Jistina se rozdělí podle podílů na společných částech platných v den předpisu. Měsíční splátka jednotky je
        její podíl dělený počtem splátek, zaokrouhlený nahoru na koruny.
      </p>
      {platne && nahled && (
        <div className="tabulka-posun">
          <table className="splatky-uveru">
            <thead>
              <tr>
                <th>Jednotka</th>
                <th className="cislo">Podíl na jistině</th>
                <th className="cislo">Měsíčně</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(nahled).map(([j, c]) => (
                <tr key={j}>
                  <td>{j}</td>
                  <td className="cislo">{kc(c.podil)}</td>
                  <td className="cislo">{kc(c.mesicne)}</td>
                </tr>
              ))}
              <tr className="soucet">
                <td>Celkem</td>
                <td className="cislo">{kc(Object.values(nahled).reduce((a, c) => a + c.podil, 0))}</td>
                <td className="cislo">{kc(Object.values(nahled).reduce((a, c) => a + c.mesicne, 0))}</td>
              </tr>
            </tbody>
          </table>
        </div>
      )}
      <div className="radek">
        <button disabled={!lze || pracuji}>{pracuji ? 'Předepisuji…' : 'Založit úvěr a předepsat podíly'}</button>
        {hotovo && <span className="uspech">{hotovo}</span>}
        {chyba && <span className="chyba">{chyba}</span>}
      </div>
    </form>
  )
}
