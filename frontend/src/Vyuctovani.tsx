import { Fragment, useEffect, useState, type ReactNode } from 'react'
import { api } from './auth'
import { kc } from './penize'
import { potvrdit } from './potvrdit'
import { Chyba, Nacitani } from './ui'
import { Rozeslat } from './Rozeslat'
import { ChybiVlastnici, HlavickaVlastnika, type Adresat } from './Vlastnici'
import { ObdobiVRozpisu, UvodObdobi, type ObdobiVlastnika } from './VlastnickaObdobi'
import { VyuctovaniSluzeb } from './VyuctovaniSluzeb'
import './vyuctovani.css'

type Polozka = {
  kod: string
  nazev: string
  klic: string
  jak_se_deli: string
  naklady: number
  vynosy: number
  zalohy: number
}
type PolozkaJednotky = { kod: string; naklady: number; zalohy: number }
type ObdobiPodilu = { od_mesice: number; do_mesice: number; podil: string }
type Jednotka = {
  jednotka: string
  podil: string
  podily_v_roce: ObdobiPodilu[] // jen když se podíl během roku měnil
  obdobi: ObdobiVlastnika[] // jen když se vyúčtování dělí mezi vlastníky
  zalohy: number
  naklady: number
  rozdil: number
  polozky: PolozkaJednotky[]
  vlastnici: Adresat[]
  doruceno: string | null
}
type Data = {
  rok: number
  dnes: string
  svj: string
  ucet: string | null
  splatnost: string
  polozky: Polozka[]
  jednotky: Jednotka[]
  nezahrnuto: { popis: string; castka: number }[]
  z_dlouhodobych: { zdroj: string; popis: string; castka: number }[]
  zapis: string | null
  proc_nejde: string | null
  rozeslani: string
}

const datum = (d: string) => new Date(d).toLocaleDateString('cs-CZ')

function procent(podil: string) {
  const [a, b] = podil.split('/').map(Number)
  return `${((a / b) * 100).toLocaleString('cs-CZ', { maximumFractionDigits: 3 })} %`
}

const MESICU = ['ledna', 'února', 'března', 'dubna', 'května', 'června', 'července', 'srpna', 'září', 'října', 'listopadu', 'prosince']

function PodilJednotky({ j, rok }: { j: Jednotka; rok: number }) {
  if (j.podily_v_roce.length === 0)
    return (
      <>
        Podíl jednotky {j.jednotka} na společných částech domu je {procent(j.podil)}. Náklady na správu se rozdělují
        podle podílů, odměna správce rovným dílem na každou jednotku.
      </>
    )
  const obdobi = j.podily_v_roce.map(
    (o) => `od ${MESICU[o.od_mesice - 1]} do ${MESICU[o.do_mesice - 1]} ${procent(o.podil)}`,
  )
  return (
    <>
      Podíl jednotky {j.jednotka} na společných částech domu se v roce {rok} měnil: {obdobi.join(', ')}. Náklady na
      správu se proto rozdělují podle průměrného podílu za měsíce roku, {procent(j.podil)}. Odměna správce se dělí
      rovným dílem na každou jednotku.
    </>
  )
}

function Vysledek({ rozdil }: { rozdil: number }) {
  if (rozdil > 0) return <span className="dluh">nedoplatek {kc(rozdil)}</span>
  if (rozdil < 0) return <span>přeplatek {kc(-rozdil)}</span>
  return <span className="uspech">vyrovnáno</span>
}

type Zalozka = 'sluzby' | 'sprava'

export function Vyuctovani() {
  // Vyúčtování za rok se dělá na začátku dalšího roku, proto do června ukazuje minulý rok.
  const dnes = new Date()
  const [rok, setRok] = useState(dnes.getMonth() < 6 ? dnes.getFullYear() - 1 : dnes.getFullYear())
  const [zalozka, setZalozka] = useState<Zalozka>('sluzby')
  const zahlavi = (
    <>
      <h1>Vyúčtování {rok}</h1>
      <div className="radek">
        <label className="vyber-roku">
          Rok{' '}
          <select value={rok} onChange={(e) => setRok(Number(e.target.value))}>
            {[dnes.getFullYear(), dnes.getFullYear() - 1, dnes.getFullYear() - 2].map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
        </label>
      </div>
      <nav className="zalozky" aria-label="Druh vyúčtování">
        {(
          [
            ['sluzby', 'Služby'],
            ['sprava', 'Správa domu'],
          ] as const
        ).map(([z, nazev]) => (
          <button
            key={z}
            className={zalozka === z ? 'aktivni' : undefined}
            aria-current={zalozka === z ? 'page' : undefined}
            onClick={() => setZalozka(z)}
          >
            {nazev}
          </button>
        ))}
      </nav>
    </>
  )
  return zalozka === 'sluzby' ? (
    <VyuctovaniSluzeb key={rok} rok={rok} zahlavi={zahlavi} />
  ) : (
    <VyuctovaniSpravy key={rok} rok={rok} zahlavi={zahlavi} />
  )
}

function VyuctovaniSpravy({ rok, zahlavi }: { rok: number; zahlavi: ReactNode }) {
  const [data, setData] = useState<Data | null>(null)
  const [chyba, setChyba] = useState<string | null>(null)
  const [otevrena, setOtevrena] = useState<string | null>(null)
  const [tisk, setTisk] = useState<Jednotka[] | null>(null)
  const [pracuji, setPracuji] = useState(false)

  useEffect(() => {
    api<Data>(`/api/vyuctovani-spravy/${rok}`).then(setData).catch((e) => setChyba(e.message))
  }, [rok])

  if (!data)
    return (
      <>
        {zahlavi}
        {chyba ? <Chyba text={chyba} /> : <Nacitani />}
      </>
    )
  if (tisk) return <ProVlastnika data={data} jednotky={tisk} zpet={() => setTisk(null)} />

  const nazvy = Object.fromEntries(data.polozky.map((p) => [p.kod, p.nazev]))
  const naklady = data.polozky.reduce((a, p) => a + p.naklady, 0)
  const zalohy = data.polozky.reduce((a, p) => a + p.zalohy, 0)
  const prubezne = !data.zapis && new Date(data.dnes) < new Date(data.rok, 11, 31)

  async function zauctovat() {
    const ok = await potvrdit({
      nadpis: `Zaúčtovat vyúčtování správy za rok ${data!.rok}?`,
      text: 'Nedoplatky a přeplatky se připíšou jednotkám a objeví se na stránce Dlužníci. Opravit to půjde jen stornem v Deníku.',
      ano: 'Zaúčtovat',
    })
    if (!ok) return
    setPracuji(true)
    setChyba(null)
    try {
      setData(await api<Data>(`/api/vyuctovani-spravy/${data!.rok}`, { method: 'POST' }))
    } catch (e) {
      setChyba((e as Error).message)
    } finally {
      setPracuji(false)
    }
  }

  return (
    <>
      {zahlavi}
      <p>
        Pojištění, správa, revize a drobné opravy se platí ze záloh na správu domu. Jednou ročně
        se skutečné náklady porovnají s tím, kolik měla každá jednotka v předpisu, a vyjde
        nedoplatek nebo přeplatek. Služby (teplo, voda, výtah…) se vyúčtovávají zvlášť.
      </p>
      {data.zapis ? (
        <p className="uspech">
          Vyúčtování je zaúčtované, zápis <a href="#denik">{data.zapis}</a>. Nedoplatky jsou
          splatné do {datum(data.splatnost)}.
        </p>
      ) : prubezne ? (
        <p className="upozorneni">
          Rok ještě neskončil, čísla jsou průběžná: náklady a předpisy zaúčtované do dneška.
        </p>
      ) : null}

      <h2>Náklady a zálohy domu</h2>
      <div className="tabulka-posun">
        <table>
          <thead>
            <tr>
              <th>Za co</th>
              <th>Jak se dělí</th>
              <th className="cislo">Náklady</th>
              <th className="cislo">Zálohy v předpisu</th>
              <th className="cislo">Rozdíl</th>
            </tr>
          </thead>
          <tbody>
            {data.polozky.map((p) => (
              <tr key={p.kod}>
                <td>{p.nazev}</td>
                <td>{p.jak_se_deli}</td>
                <td className="cislo">
                  {kc(p.naklady)}
                  {p.vynosy !== 0 && (
                    <>
                      <br />
                      <span className="tlumene">po odečtení výnosů {kc(p.vynosy)}</span>
                    </>
                  )}
                </td>
                <td className="cislo">{kc(p.zalohy)}</td>
                <td className="cislo">{kc(p.naklady - p.zalohy)}</td>
              </tr>
            ))}
            <tr className="soucet">
              <td colSpan={2}>Celkem</td>
              <td className="cislo">{kc(naklady)}</td>
              <td className="cislo">{kc(zalohy)}</td>
              <td className="cislo">{kc(naklady - zalohy)}</td>
            </tr>
          </tbody>
        </table>
      </div>
      {data.nezahrnuto.length > 0 && (
        <div className="upozorneni">
          <p>
            Tyto náklady nemají určené, ze kterých záloh se platí, a do vyúčtování nejsou
            započtené. Zeptejte se účetní, kam patří:
          </p>
          <ul>
            {data.nezahrnuto.map((n) => (
              <li key={n.popis}>
                {n.popis}: {kc(n.castka)}
              </li>
            ))}
          </ul>
          {data.nezahrnuto.some((n) => n.popis === 'Úroky z úvěru') && (
            <p>
              Úroky z úvěru, které podle rozhodnutí shromáždění platí fond oprav nebo záloha na úvěr, se k 31. 12.
              pokryjí na stránce <a href="#uvery">Úvěry</a>.
            </p>
          )}
        </div>
      )}
      {data.z_dlouhodobych.length > 0 && (
        <>
          <h3>
            {data.z_dlouhodobych.some((x) => x.zdroj !== 'fond oprav')
              ? 'Zaplaceno z fondu oprav a ze záloh na úvěr'
              : 'Zaplaceno z fondu oprav'}
          </h3>
          <p className="tlumene">
            Tyto výdaje vlastníci zaplatili z dlouhodobých záloh. Do vyúčtování záloh na správu se nezapočítávají.
          </p>
          <div className="tabulka-posun">
            <table className="z-dlouhodobych">
              <thead>
                <tr>
                  <th>Z čeho</th>
                  <th>Co</th>
                  <th className="cislo">Částka</th>
                </tr>
              </thead>
              <tbody>
                {data.z_dlouhodobych.map((x) => (
                  <tr key={x.zdroj + x.popis}>
                    <td>{x.zdroj === 'fond oprav' ? 'Fond oprav' : 'Záloha na úvěr'}</td>
                    <td>{x.popis}</td>
                    <td className="cislo">{kc(x.castka)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      <h2>Jednotky</h2>
      <p className="tlumene">
        Porovnávají se zálohy podle předpisu. Měsíční zálohy, které vlastník nezaplatil, dluží
        zvlášť a jsou na stránce Dlužníci.
      </p>
      {data.zapis && (
        <div className="radek">
          <button onClick={() => setTisk(data.jednotky)}>Vyúčtování všem vlastníkům</button>
        </div>
      )}
      <div className="tabulka-posun">
        <table className="jednotky">
          <thead>
            <tr>
              <th>Jednotka</th>
              <th className="cislo">Podíl</th>
              <th className="cislo">Náklady jednotky</th>
              <th className="cislo">Zálohy v předpisu</th>
              <th className="cislo">Výsledek</th>
              {data.zapis && <th>Doručeno</th>}
            </tr>
          </thead>
          <tbody>
            {data.jednotky.map((j) => (
              <Fragment key={j.jednotka}>
                <tr
                  className="klikaci"
                  onClick={() => setOtevrena(otevrena === j.jednotka ? null : j.jednotka)}
                  aria-expanded={otevrena === j.jednotka}
                >
                  <td>{j.jednotka}</td>
                  <td className="cislo">{procent(j.podil)}</td>
                  <td className="cislo">{kc(j.naklady)}</td>
                  <td className="cislo">{kc(j.zalohy)}</td>
                  <td className="cislo">
                    <Vysledek rozdil={j.rozdil} />
                  </td>
                  {data.zapis && (
                    <td>{j.doruceno ? datum(j.doruceno) : <span className="tlumene">zatím ne</span>}</td>
                  )}
                </tr>
                {otevrena === j.jednotka && (
                  <tr className="rozpis">
                    <td colSpan={data.zapis ? 6 : 5}>
                      <ul>
                        {j.polozky.map((p) => (
                          <li key={p.kod}>
                            <span>{nazvy[p.kod]}</span>
                            <span>
                              {kc(p.naklady)} <span className="tlumene">/ zálohy {kc(p.zalohy)}</span>
                            </span>
                          </li>
                        ))}
                      </ul>
                      <ObdobiVRozpisu obdobi={j.obdobi} />
                      <button className="vedlejsi" onClick={() => setTisk([j])}>
                        Vyúčtování pro vlastníka
                      </button>
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>

      {!data.zapis && (
        <div className="radek">
          <button disabled={pracuji || data.proc_nejde !== null} onClick={zauctovat}>
            {pracuji ? 'Účtuji…' : `Zaúčtovat vyúčtování k 31. 12. ${data.rok}`}
          </button>
          {data.proc_nejde && <span className="tlumene">{data.proc_nejde}</span>}
        </div>
      )}
      {chyba && <p className="chyba">{chyba}</p>}
    </>
  )
}

function ProVlastnika({ data, jednotky, zpet }: { data: Data; jednotky: Jednotka[]; zpet: () => void }) {
  // Jednotka, která v roce změnila vlastníka, má vyúčtování pro každého z nich.
  const dokumenty = jednotky.flatMap((j): { j: Jednotka; o: ObdobiVlastnika | null; vlastnici: Adresat[] }[] =>
    j.obdobi.length ? j.obdobi.map((o) => ({ j, o, vlastnici: o.vlastnici })) : [{ j, o: null, vlastnici: j.vlastnici }],
  )
  return (
    <>
      <div className="radek neni-v-tisku">
        <button className="vedlejsi" onClick={zpet}>
          Zpět na vyúčtování
        </button>
        <button onClick={() => window.print()}>Vytisknout</button>
      </div>
      <p className="tlumene neni-v-tisku">
        {data.zapis
          ? 'Text si můžete upravit: zkopírujte ho do dopisu nebo e-mailu.'
          : 'Vyúčtování ještě není zaúčtované, čísla se do konce roku můžou změnit. Vlastníkům ho posílejte až po zaúčtování.'}
      </p>
      {data.zapis && (
        <Rozeslat
          druh="vyuctovani_spravy"
          klic={data.rozeslani}
          nazev={`Vyúčtování záloh na správu domu za rok ${data.rok}`}
        />
      )}
      {dokumenty.length > 1 && (
        <p className="tlumene neni-v-tisku">Každý vlastník má vyúčtování na samostatné stránce.</p>
      )}
      <ChybiVlastnici jednotky={dokumenty} />
      {dokumenty.map(({ j, o }) => (
        <Dokument key={`${j.jednotka}-${o?.od ?? ''}`} data={data} j={j} o={o} />
      ))}
    </>
  )
}

function Dokument({ data, j: jednotka, o }: { data: Data; j: Jednotka; o: ObdobiVlastnika | null }) {
  const nazvy = Object.fromEntries(data.polozky.map((p) => [p.kod, p]))
  // Část vyúčtování za vlastnické období má vlastní adresáty, zálohy, náklady a výsledek.
  const j = o ? { ...jednotka, ...o } : jednotka
  const drivejsi = o !== null && !o.soucasny
  return (
    <>
      <article className="upominka" data-jednotka={j.jednotka} data-osoby={drivejsi ? o.osoby.join(',') : undefined}>
        <p>
          <strong>{data.svj}</strong>
        </p>
        <HlavickaVlastnika jednotka={j.jednotka} vlastnici={j.vlastnici} drivejsi={drivejsi} />
        <p className="vpravo">Dne {datum(data.dnes)}</p>
        <h2>Vyúčtování záloh na správu domu a pozemku za rok {data.rok}</h2>
        {o && <UvodObdobi o={o} jednotka={j.jednotka} rok={data.rok} />}
        <p>
          <PodilJednotky j={j} rok={data.rok} />
        </p>
        <table className="polozky-dluhu">
          <thead>
            <tr>
              <th>Za co</th>
              <th className="cislo">Náklady domu</th>
              <th className="cislo">Na vaši jednotku</th>
              <th className="cislo">Vaše zálohy</th>
            </tr>
          </thead>
          <tbody>
            {j.polozky.map((p) => (
              <tr key={p.kod}>
                <td>
                  {nazvy[p.kod].nazev}
                  <br />
                  <span className="tlumene">
                    {nazvy[p.kod].jak_se_deli}
                    {nazvy[p.kod].vynosy !== 0 &&
                      `, po odečtení pojistného plnění, dotací nebo úroků ${kc(nazvy[p.kod].vynosy)}`}
                  </span>
                </td>
                <td className="cislo">{kc(nazvy[p.kod].naklady)}</td>
                <td className="cislo">{kc(p.naklady)}</td>
                <td className="cislo">{kc(p.zalohy)}</td>
              </tr>
            ))}
            <tr className="soucet">
              <td>Celkem</td>
              <td></td>
              <td className="cislo">{kc(j.naklady)}</td>
              <td className="cislo">{kc(j.zalohy)}</td>
            </tr>
          </tbody>
        </table>
        <p>
          <strong>
            {j.rozdil > 0
              ? `Nedoplatek: ${kc(j.rozdil)}`
              : j.rozdil < 0
                ? `Přeplatek: ${kc(-j.rozdil)}`
                : 'Zálohy přesně pokryly náklady.'}
          </strong>
        </p>
        {j.rozdil > 0 && (
          <p>
            Nedoplatek prosíme uhraďte do {datum(data.splatnost)}
            {data.ucet ? ` na účet ${data.ucet}` : ' na účet společenství'} s variabilním symbolem,
            {drivejsi ? ' kterým jste platili zálohy.' : ' kterým platíte zálohy.'}
          </p>
        )}
        {j.rozdil < 0 && (
          <p>
            Přeplatek vám vrátíme do {datum(data.splatnost)}. Pokud máte nezaplacené zálohy,
            započteme ho nejdřív na ně.
            {drivejsi && ' Pokud jste od převodu změnili číslo účtu, dejte nám prosím vědět.'}
          </p>
        )}
        <p>
          Zálohy v tabulce jsou podle předpisu. Pokud jste některou měsíční zálohu nezaplatili,
          dlužíte ji zvlášť.
        </p>
        <p>Za výbor společenství</p>
      </article>
    </>
  )
}
