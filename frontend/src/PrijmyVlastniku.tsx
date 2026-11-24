import { useEffect, useState, type FormEvent } from 'react'
import { api } from './auth'
import { kc, naHalire } from './penize'
import { Chyba, Nacitani } from './ui'
import './tisk.css'

type Platba = { datum: string; najemce: string; castka: number; zapis: string; popis: string }
type Vlastnik = {
  jmena: string[]
  adresa: string
  od: string | null
  do: string | null
  prijato: number
  predepsano: number
}
type Jednotka = {
  jednotka: string
  podil: string
  vlastnici: Vlastnik[]
  prijato: number
  vyplaceno: number
  do_fondu: number
  zbyva: number
}
type Data = {
  rok: number
  nastaveno: boolean
  svj: string
  ico: string | null
  sidlo: string | null
  dnes: string
  platby: Platba[]
  predepsano: number
  jednotky: Jednotka[]
  jako_vynos: string[]
}

const datum = (d: string) => new Date(d).toLocaleDateString('cs-CZ')
const dnes = () => new Date().toISOString().slice(0, 10)
const jmena = (v: Vlastnik) => (v.jmena.length ? v.jmena.join(', ') : 'vlastník není zapsaný')

export function PrijmyVlastniku() {
  const [letos] = useState(() => new Date().getFullYear())
  const [rok, setRok] = useState(letos)
  return (
    <>
      <h1>Příjmy vlastníků</h1>
      <div className="radek neni-v-tisku">
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
      <PrijmyRoku key={rok} rok={rok} />
    </>
  )
}

function PrijmyRoku({ rok }: { rok: number }) {
  const [data, setData] = useState<Data | null>(null)
  const [chyba, setChyba] = useState<string | null>(null)
  const [potvrzeni, setPotvrzeni] = useState<{ jednotka: Jednotka; vlastnik: Vlastnik } | null>(null)

  useEffect(() => {
    api<Data>(`/api/prijmy-vlastniku/${rok}`)
      .then(setData)
      .catch((e) => setChyba(e.message))
  }, [rok])

  if (!data) return chyba ? <Chyba text={chyba} /> : <Nacitani />
  if (!data.nastaveno)
    return (
      <p className="upozorneni">
        Společenství nemá v nastavení účty pro nájemné ze společných částí. Pokud je potřebuje, požádejte správce
        aplikace o jejich doplnění.
      </p>
    )
  if (potvrzeni)
    return (
      <Potvrzeni
        data={data}
        jednotka={potvrzeni.jednotka}
        vlastnik={potvrzeni.vlastnik}
        zpet={() => setPotvrzeni(null)}
      />
    )

  const prijato = data.platby.reduce((s, p) => s + p.castka, 0)
  return (
    <>
      <p className="tlumene">
        Nájemné za společné části domu, třeba za střechu pronajatou pro anténu, patří vlastníkům, ne společenství. Každá
        platba od nájemce se rozdělí podle podílů na společných částech a připadne tomu, kdo jednotku v den platby
        vlastnil. Společenství podíly vlastníkům vyplatí, nebo je na jejich žádost převede do fondu oprav.
      </p>
      {data.jako_vynos.length > 0 && (
        <p className="upozorneni">
          {data.jako_vynos.length === 1
            ? `Platby od nájemce ${data.jako_vynos[0]} tu nejsou: jeho nájemné je zaúčtované`
            : `Platby od nájemců ${data.jako_vynos.join(', ')} tu nejsou: jejich nájemné je zaúčtované`}{' '}
          jako výnos společenství, ne jako příjem vlastníků. Pokud jde o nájem společných částí, poraďte se s účetní o
          opravě.
        </p>
      )}
      <section>
        <h2>Platby od nájemců v roce {data.rok}</h2>
        {data.platby.length === 0 ? (
          <p>
            V roce {data.rok} zatím žádný nájemce nezaplatil. Nájemné předepište v <a href="#denik">Deníku</a> interním
            dokladem „Předpis nájemného ze společných částí“ a platbu pak zaúčtujte v <a href="#banka">Bance</a> jako
            úhradu nájemného.
          </p>
        ) : (
          <div className="tabulka-posun">
            <table className="pohyby-fondu">
              <thead>
                <tr>
                  <th>Datum</th>
                  <th>Nájemce</th>
                  <th>Zápis</th>
                  <th className="cislo">Částka</th>
                </tr>
              </thead>
              <tbody>
                {data.platby.map((p) => (
                  <tr key={p.zapis}>
                    <td>{datum(p.datum)}</td>
                    <td>{p.najemce}</td>
                    <td>
                      <a href="#denik">{p.zapis}</a>
                    </td>
                    <td className="cislo">{kc(p.castka)}</td>
                  </tr>
                ))}
                <tr>
                  <td colSpan={3}>
                    <strong>Celkem přijato</strong>
                  </td>
                  <td className="cislo">
                    <strong>{kc(prijato)}</strong>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        )}
      </section>
      <PodilyJednotek
        data={data}
        setData={setData}
        otevritPotvrzeni={(jednotka, vlastnik) => setPotvrzeni({ jednotka, vlastnik })}
      />
    </>
  )
}

function PodilyJednotek({
  data,
  setData,
  otevritPotvrzeni,
}: {
  data: Data
  setData: (d: Data) => void
  otevritPotvrzeni: (j: Jednotka, v: Vlastnik) => void
}) {
  const [prevod, setPrevod] = useState<string | null>(null)
  const zbyva = data.jednotky.reduce((s, j) => s + Math.max(j.zbyva, 0), 0)
  if (data.platby.length === 0 && zbyva === 0) return null
  return (
    <section>
      <h2>Podíly jednotek</h2>
      <div className="tabulka-posun">
        <table className="podily-vlastniku">
          <thead>
            <tr>
              <th>Jednotka</th>
              <th>Vlastník</th>
              <th className="cislo">Přijato v roce</th>
              <th className="cislo">Vyplaceno</th>
              <th className="cislo">Do fondu oprav</th>
              <th className="cislo">Zbývá vypořádat</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {data.jednotky.map((j) => (
              <RadekJednotky
                key={j.jednotka}
                j={j}
                data={data}
                prevadi={prevod === j.jednotka}
                setPrevod={setPrevod}
                setData={setData}
                otevritPotvrzeni={otevritPotvrzeni}
              />
            ))}
          </tbody>
        </table>
      </div>
      <p className="tlumene">
        Výplatu podílu zaúčtujte v <a href="#banka">Bance</a> jako výplatu podílu na příjmech ze společných částí.
        Potvrzení vlastník potřebuje pro své daňové přiznání: nájemné daní sám, ne společenství.
      </p>
    </section>
  )
}

function RadekJednotky({
  j,
  data,
  prevadi,
  setPrevod,
  setData,
  otevritPotvrzeni,
}: {
  j: Jednotka
  data: Data
  prevadi: boolean
  setPrevod: (j: string | null) => void
  setData: (d: Data) => void
  otevritPotvrzeni: (j: Jednotka, v: Vlastnik) => void
}) {
  const vlastnici = j.vlastnici.filter((v) => v.prijato || v.predepsano)
  return (
    <>
      <tr>
        <td>
          {j.jednotka}
          {j.podil && <div className="tlumene">podíl {j.podil}</div>}
        </td>
        <td>
          {vlastnici.length === 0
            ? '–'
            : vlastnici.map((v, i) => (
                <div key={i}>
                  {jmena(v)}
                  {vlastnici.length > 1 && <span className="tlumene"> ({kc(v.prijato)})</span>}
                </div>
              ))}
        </td>
        <td className="cislo">{kc(j.prijato)}</td>
        <td className="cislo">{j.vyplaceno ? kc(j.vyplaceno) : ''}</td>
        <td className="cislo">{j.do_fondu ? kc(j.do_fondu) : ''}</td>
        <td className="cislo">{j.zbyva ? kc(j.zbyva) : ''}</td>
        <td>
          <div className="akce-radku">
            {vlastnici.map((v, i) => (
              <button key={i} className="odkaz" onClick={() => otevritPotvrzeni(j, v)}>
                {vlastnici.length > 1 ? `Potvrzení: ${v.jmena[0] ?? 'vlastník'}` : 'Potvrzení'}
              </button>
            ))}
            {j.zbyva > 0 && !prevadi && (
              <button className="odkaz" onClick={() => setPrevod(j.jednotka)}>
                Převést do fondu oprav
              </button>
            )}
          </div>
        </td>
      </tr>
      {prevadi && (
        <tr>
          <td colSpan={7}>
            <PrevodDoFondu j={j} rok={data.rok} zavrit={() => setPrevod(null)} setData={setData} />
          </td>
        </tr>
      )}
    </>
  )
}

function PrevodDoFondu({
  j,
  rok,
  zavrit,
  setData,
}: {
  j: Jednotka
  rok: number
  zavrit: () => void
  setData: (d: Data) => void
}) {
  const [castka, setCastka] = useState((j.zbyva / 100).toFixed(2).replace('.', ','))
  const [den, setDen] = useState(new Date().getFullYear() === rok ? dnes() : `${rok}-12-31`)
  const [zadost, setZadost] = useState('')
  const [souhlas, setSouhlas] = useState(false)
  const [chyba, setChyba] = useState<string | null>(null)
  const [pracuji, setPracuji] = useState(false)

  async function prevest(e: FormEvent) {
    e.preventDefault()
    const halire = naHalire(castka)
    if (halire === null || halire <= 0) {
      setChyba('Napište částku, kterou chcete převést.')
      return
    }
    setPracuji(true)
    setChyba(null)
    try {
      setData(
        await api<Data>(`/api/prijmy-vlastniku/${rok}/prevod`, {
          method: 'POST',
          json: { jednotka: j.jednotka, castka: halire, datum: den, zadost },
        }),
      )
      zavrit()
    } catch (e) {
      setChyba((e as Error).message)
    } finally {
      setPracuji(false)
    }
  }

  return (
    <form className="interni-doklad" onSubmit={prevest}>
      <p>
        Podíl jednotky {j.jednotka} zůstane v domě a zvýší zálohy vlastníka na fond oprav. Jde to jen s jeho výslovným
        souhlasem, nejlépe písemným: o penězích jednotlivých vlastníků nemůže rozhodnout ani shromáždění.
      </p>
      <div className="interni-doklad-pole">
        <label>
          Částka
          <input inputMode="decimal" value={castka} onChange={(e) => setCastka(e.target.value)} />
        </label>
        <label>
          Ke dni
          <input type="date" value={den} onChange={(e) => setDen(e.target.value)} required />
        </label>
        <label>
          Kdy a jak vlastník požádal
          <input
            value={zadost}
            onChange={(e) => setZadost(e.target.value)}
            placeholder="třeba písemná žádost z 5. 3."
            maxLength={300}
            required
          />
        </label>
      </div>
      <label className="zaskrtavatko">
        <input type="checkbox" checked={souhlas} onChange={(e) => setSouhlas(e.target.checked)} required />
        Vlastník o převod výslovně požádal a žádost je uložená u dokladů.
      </label>
      <div className="radek">
        <button type="submit" disabled={pracuji || !souhlas}>
          Převést do fondu oprav
        </button>
        <button type="button" className="vedlejsi" onClick={zavrit}>
          Zpět
        </button>
        {chyba && <span className="chyba">{chyba}</span>}
      </div>
    </form>
  )
}

function Potvrzeni({
  data,
  jednotka: j,
  vlastnik: v,
  zpet,
}: {
  data: Data
  jednotka: Jednotka
  vlastnik: Vlastnik
  zpet: () => void
}) {
  const zacatek = `${data.rok}-01-01`
  const konec = `${data.rok}-12-31`
  const castRoku = (v.od && v.od > zacatek) || (v.do && v.do < konec)
  const jediny = j.vlastnici.filter((x) => x.prijato || x.predepsano).length === 1
  return (
    <>
      <div className="radek neni-v-tisku">
        <button className="vedlejsi" onClick={zpet}>
          Zpět na příjmy vlastníků
        </button>
        <button onClick={() => window.print()}>Vytisknout</button>
      </div>
      <p className="tlumene neni-v-tisku">
        Než potvrzení vydáte, zkontrolujte, že jsou v Bance zaúčtované všechny platby od nájemců za rok {data.rok}.
      </p>
      <article className="upominka">
        <p>
          <strong>{data.svj}</strong>
          {data.ico && <>, IČ {data.ico}</>}
          {data.sidlo && (
            <>
              <br />
              {data.sidlo}
            </>
          )}
        </p>
        <h2>Potvrzení o podílu na nájemném ze společných částí domu za rok {data.rok}</h2>
        <p>
          Vlastník jednotky č. {j.jednotka}: {jmena(v)}
          {v.adresa && (
            <>
              <br />
              {v.adresa}
            </>
          )}
          {castRoku && (
            <>
              <br />
              Jednotku vlastnil {v.od && v.od > zacatek ? `od ${datum(v.od)}` : ''}
              {v.do && v.do < konec ? ` do ${datum(v.do)}` : ''}.
            </>
          )}
        </p>
        <p>
          Společenství potvrzuje, že v roce {data.rok} přijalo od nájemců společných částí domu nájemné, ze kterého na
          jednotku č. {j.jednotka}
          {j.podil && <> podle podílu na společných částech {j.podil}</>} připadá <strong>{kc(v.prijato)}</strong>.
          Částka vychází z plateb, které společenství od nájemců v roce skutečně přijalo
          {castRoku ? ', a jen z těch, které přišly v době, kdy jednotku vlastnil' : ''}.
        </p>
        {v.predepsano !== v.prijato && (
          <p>
            Z nájemného předepsaného nájemcům na rok {data.rok} připadá na jednotku {kc(v.predepsano)}. Tento údaj
            potřebuje vlastník, který vede účetnictví.
          </p>
        )}
        {jediny && (j.vyplaceno > 0 || j.do_fondu > 0) && (
          <p>
            V roce {data.rok} společenství z podílů jednotky
            {j.vyplaceno > 0 && <> vyplatilo {kc(j.vyplaceno)}</>}
            {j.vyplaceno > 0 && j.do_fondu > 0 && ' a'}
            {j.do_fondu > 0 && <> převedlo na žádost vlastníka do záloh na fond oprav {kc(j.do_fondu)}</>}.
          </p>
        )}
        <p>
          Nájemné ze společných částí není příjmem společenství, ale vlastníků jednotek (§ 16 odst. 2 nařízení vlády č.
          366/2013 Sb.).
        </p>
        <p className="vpravo">Dne {datum(data.dnes)}</p>
        <div className="podpisy">
          <p>
            Za výbor společenství
            <br />
            <span className="podpis">jméno, funkce a podpis</span>
          </p>
          <p>
            <br />
            <span className="podpis">jméno, funkce a podpis</span>
          </p>
        </div>
      </article>
    </>
  )
}
