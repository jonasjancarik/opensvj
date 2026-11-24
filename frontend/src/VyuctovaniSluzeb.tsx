import { Fragment, useEffect, useState, type FormEvent, type ReactNode } from 'react'
import { api } from './auth'
import { kc, naHalire } from './penize'
import { potvrdit } from './potvrdit'
import { Chyba, Nacitani } from './ui'
import { Rozeslat } from './Rozeslat'
import { ChybiVlastnici, HlavickaVlastnika, type Adresat } from './Vlastnici'
import { ObdobiVRozpisu, UvodObdobi, type ObdobiVlastnika } from './VlastnickaObdobi'
import './vyuctovani.css'

type Sluzba = {
  kod: string
  nazev: string
  klic: string
  jak_se_deli: string
  naklady: number
  zalohy: number
  merna_jednotka: string | null
  problem: string | null
  zuctovatel: { castky: Record<string, number>; zdroj: string } | null
}
type PolozkaJednotky = {
  kod: string
  naklady: number
  zalohy: number
  spotreba: string | null
}
type Jednotka = {
  jednotka: string
  osobomesice: number
  zalohy: number
  naklady: number
  rozdil: number
  nezaplacene: number
  polozky: PolozkaJednotky[]
  vlastnici: Adresat[]
  doruceno: string | null
  namitky_do: string | null
  vyrovnani_do: string | null
  obdobi: ObdobiVlastnika[] // jen když se vyúčtování dělí mezi vlastníky
}
type Data = {
  rok: number
  dnes: string
  svj: string
  ucet: string | null
  splatnost: string
  doruceni: string
  sluzby: Sluzba[]
  jednotky: Jednotka[]
  zapis: string | null
  proc_nejde: string | null
  rozeslani: string
}

const datum = (d: string) => new Date(d).toLocaleDateString('cs-CZ')
const cislo = (x: string | number, mista = 3) => Number(x).toLocaleString('cs-CZ', { maximumFractionDigits: mista })

function osoby(osobomesice: number) {
  const prumer = cislo(osobomesice / 12, 1)
  return `${prumer} ${osobomesice / 12 > 1 && osobomesice / 12 < 5 ? 'osoby' : osobomesice === 12 ? 'osoba' : 'osob'}`
}

function Vysledek({ rozdil }: { rozdil: number }) {
  if (rozdil > 0) return <span className="dluh">nedoplatek {kc(rozdil)}</span>
  if (rozdil < 0) return <span>přeplatek {kc(-rozdil)}</span>
  return <span className="uspech">vyrovnáno</span>
}

export function VyuctovaniSluzeb({ rok, zahlavi }: { rok: number; zahlavi: ReactNode }) {
  const [data, setData] = useState<Data | null>(null)
  const [chyba, setChyba] = useState<string | null>(null)
  const [otevrena, setOtevrena] = useState<string | null>(null)
  const [zadavana, setZadavana] = useState<string | null>(null)
  const [tisk, setTisk] = useState<Jednotka[] | null>(null)
  const [pracuji, setPracuji] = useState(false)

  useEffect(() => {
    api<Data>(`/api/vyuctovani-sluzeb/${rok}`)
      .then(setData)
      .catch((e) => setChyba(e.message))
  }, [rok])

  if (!data)
    return (
      <>
        {zahlavi}
        {chyba ? <Chyba text={chyba} /> : <Nacitani />}
      </>
    )
  if (tisk) return <ProVlastnika data={data} jednotky={tisk} zpet={() => setTisk(null)} />

  const nazvy = Object.fromEntries(data.sluzby.map((x) => [x.kod, x.nazev]))
  const naklady = data.sluzby.reduce((a, x) => a + x.naklady, 0)
  const zalohy = data.sluzby.reduce((a, x) => a + x.zalohy, 0)
  const prubezne = !data.zapis && new Date(data.dnes) < new Date(data.rok, 11, 31)
  const sOsobami = data.sluzby.some((x) => x.klic === 'osoby')

  async function zauctovat() {
    const ok = await potvrdit({
      nadpis: `Zaúčtovat vyúčtování služeb za rok ${data!.rok}?`,
      text: 'Nedoplatky a přeplatky se připíšou jednotkám a objeví se na stránce Dlužníci. Opravit to půjde jen stornem v Deníku.',
      ano: 'Zaúčtovat',
    })
    if (!ok) return
    setPracuji(true)
    setChyba(null)
    try {
      setData(
        await api<Data>(`/api/vyuctovani-sluzeb/${data!.rok}`, {
          method: 'POST',
        }),
      )
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
        Teplo, voda, výtah, úklid a další služby se platí z měsíčních záloh. Po skončení roku se náklady každé služby
        rozdělí mezi jednotky podle dohodnutého způsobu a porovnají se se zálohami v předpisu. Vlastníkům musí
        vyúčtování dojít do {datum(data.doruceni)}.
      </p>
      {data.zapis ? (
        <p className="uspech">
          Vyúčtování je zaúčtované, zápis <a href="#denik">{data.zapis}</a>. Nedoplatky a přeplatky jsou splatné do{' '}
          {datum(data.splatnost)}.
        </p>
      ) : prubezne ? (
        <p className="upozorneni">Rok ještě neskončil, čísla jsou průběžná: náklady a předpisy zaúčtované do dneška.</p>
      ) : null}

      <h2>Náklady a zálohy domu</h2>
      {data.sluzby.length === 0 ? (
        <p className="tlumene">Za rok {data.rok} nejsou zaúčtované žádné náklady ani zálohy na služby.</p>
      ) : (
        <div className="tabulka-posun">
          <table>
            <thead>
              <tr>
                <th>Služba</th>
                <th>Jak se dělí</th>
                <th className="cislo">Náklady</th>
                <th className="cislo">Zálohy v předpisu</th>
                <th className="cislo">Rozdíl</th>
              </tr>
            </thead>
            <tbody>
              {data.sluzby.map((x) => (
                <Fragment key={x.kod}>
                  <tr>
                    <td>{x.nazev}</td>
                    <td>
                      {x.jak_se_deli}
                      {x.zuctovatel && !data.zapis && (
                        <>
                          <br />
                          <button className="odkaz" onClick={() => setZadavana(zadavana === x.kod ? null : x.kod)}>
                            {Object.keys(x.zuctovatel.castky).length
                              ? 'Opravit výsledky zúčtovatele'
                              : 'Zadat výsledky zúčtovatele'}
                          </button>
                        </>
                      )}
                    </td>
                    <td className="cislo">{kc(x.naklady)}</td>
                    <td className="cislo">{kc(x.zalohy)}</td>
                    <td className="cislo">{kc(x.naklady - x.zalohy)}</td>
                  </tr>
                  {x.problem && (
                    <tr>
                      <td colSpan={5}>
                        <p className="upozorneni">{x.problem}</p>
                      </td>
                    </tr>
                  )}
                  {zadavana === x.kod && (
                    <tr>
                      <td colSpan={5}>
                        <VysledkyZuctovatele
                          data={data}
                          sluzba={x}
                          ulozeno={(d) => (setData(d), setZadavana(null))}
                          zrusit={() => setZadavana(null)}
                        />
                      </td>
                    </tr>
                  )}
                </Fragment>
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
      )}
      <p className="tlumene">
        Způsob rozdělení se nastavuje v profilu SVJ a má ho schválit shromáždění. Které rozhodnutí ho dokládá, zapíšete
        na stránce <a href="#rozhodnuti">Rozhodnutí</a>.
      </p>

      {data.sluzby.length > 0 && (
        <>
          <h2>Jednotky</h2>
          <p className="tlumene">
            Porovnávají se zálohy podle předpisu. Měsíční zálohy, které vlastník nezaplatil, dluží zvlášť a jsou na
            stránce Dlužníci.
            {data.zapis &&
              ' Lhůta pro námitky (30 dní) a pro vyrovnání nedoplatků a přeplatků (4 měsíce) běží od doručení vyúčtování.'}
          </p>
          {data.zapis && (
            <div className="radek">
              <button onClick={() => setTisk(data.jednotky)}>Vyúčtování všem vlastníkům</button>
            </div>
          )}
          {data.sluzby.some((x) => x.problem) && (
            <p className="upozorneni">Služby s upozorněním výše zatím nejsou v nákladech jednotek započtené.</p>
          )}
          <div className="tabulka-posun">
            <table className="jednotky">
              <thead>
                <tr>
                  <th>Jednotka</th>
                  {sOsobami && <th className="cislo">Osob v průměru</th>}
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
                      {sOsobami && <td className="cislo">{cislo(j.osobomesice / 12, 1)}</td>}
                      <td className="cislo">{kc(j.naklady)}</td>
                      <td className="cislo">{kc(j.zalohy)}</td>
                      <td className="cislo">
                        <Vysledek rozdil={j.rozdil} />
                        {j.nezaplacene > 0 && (
                          <>
                            <br />
                            <span className="tlumene">nezaplacené zálohy za rok {kc(j.nezaplacene)}</span>
                          </>
                        )}
                      </td>
                      {data.zapis && (
                        <td>
                          {j.doruceno ? (
                            <>
                              {datum(j.doruceno)}
                              <div className="tlumene">
                                námitky do {datum(j.namitky_do!)}, vyrovnání do {datum(j.vyrovnani_do!)}
                              </div>
                            </>
                          ) : (
                            <span className="tlumene">zatím ne</span>
                          )}
                        </td>
                      )}
                    </tr>
                    {otevrena === j.jednotka && (
                      <tr className="rozpis">
                        <td colSpan={(sOsobami ? 5 : 4) + (data.zapis ? 1 : 0)}>
                          <ul>
                            {j.polozky
                              .filter((p) => p.naklady || p.zalohy)
                              .map((p) => (
                                <li key={p.kod}>
                                  <span>
                                    {nazvy[p.kod]}
                                    {p.spotreba !== null && (
                                      <span className="tlumene">
                                        {' '}
                                        (spotřeba {cislo(p.spotreba)}{' '}
                                        {data.sluzby.find((x) => x.kod === p.kod)?.merna_jednotka})
                                      </span>
                                    )}
                                  </span>
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
        </>
      )}

      {!data.zapis && data.sluzby.length > 0 && (
        <div className="radek">
          <button disabled={pracuji || data.proc_nejde !== null} onClick={zauctovat}>
            {pracuji ? 'Účtuji…' : `Zaúčtovat vyúčtování služeb k 31. 12. ${data.rok}`}
          </button>
          {data.proc_nejde && <span className="tlumene">{data.proc_nejde}</span>}
        </div>
      )}
      {chyba && <p className="chyba">{chyba}</p>}
    </>
  )
}

function VysledkyZuctovatele({
  data,
  sluzba,
  ulozeno,
  zrusit,
}: {
  data: Data
  sluzba: Sluzba
  ulozeno: (d: Data) => void
  zrusit: () => void
}) {
  const puvodni = sluzba.zuctovatel!
  const [castky, setCastky] = useState<Record<string, string>>(() =>
    Object.fromEntries(
      data.jednotky.map((j) => [
        j.jednotka,
        j.jednotka in puvodni.castky ? (puvodni.castky[j.jednotka] / 100).toFixed(2).replace('.', ',') : '',
      ]),
    ),
  )
  const [zdroj, setZdroj] = useState(puvodni.zdroj)
  const [pracuji, setPracuji] = useState(false)
  const [chyba, setChyba] = useState<string | null>(null)

  const halire = Object.fromEntries(Object.entries(castky).map(([j, t]) => [j, t.trim() ? naHalire(t) : 0]))
  const spatne = Object.entries(halire)
    .filter(([, h]) => h === null || h < 0)
    .map(([j]) => j)
  const soucet = Object.values(halire).reduce<number>((a, h) => a + (h ?? 0), 0)

  async function ulozit(e: FormEvent) {
    e.preventDefault()
    setPracuji(true)
    setChyba(null)
    try {
      const vyplnene = Object.fromEntries(Object.entries(halire).filter(([j]) => castky[j].trim()))
      ulozeno(
        await api<Data>(`/api/vyuctovani-sluzeb/${data.rok}/zuctovatel/${sluzba.kod}`, {
          method: 'PUT',
          json: { castky: vyplnene, zdroj },
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
      <h3>{sluzba.nazev}: výsledky od zúčtovatele</h3>
      <p className="tlumene">
        Opište náklad každé jednotky z rozúčtování, které poslal zúčtovatel (dodavatel měřičů nebo správce). Součet musí
        přesně odpovídat nákladům v účetnictví, tedy {kc(sluzba.naklady)}.
      </p>
      <div className="faktura-formular">
        {data.jednotky.map((j) => (
          <label key={j.jednotka}>
            Jednotka {j.jednotka}
            <input
              inputMode="decimal"
              value={castky[j.jednotka]}
              onChange={(e) => setCastky({ ...castky, [j.jednotka]: e.target.value })}
              className={spatne.includes(j.jednotka) ? 'neplatne' : undefined}
              placeholder="0,00"
            />
          </label>
        ))}
        <label className="cely-radek">
          Odkud čísla jsou
          <input
            value={zdroj}
            onChange={(e) => setZdroj(e.target.value)}
            maxLength={200}
            placeholder="třeba Rozúčtování tepla 2026 od firmy Techem"
          />
        </label>
      </div>
      <p className={soucet === sluzba.naklady ? 'uspech' : 'tlumene'}>
        Součet {kc(soucet)}
        {soucet !== sluzba.naklady && `, do nákladů v účetnictví chybí ${kc(sluzba.naklady - soucet)}`}
        {soucet === sluzba.naklady && ', sedí na náklady v účetnictví'}
      </p>
      <div className="radek">
        <button type="submit" disabled={pracuji || spatne.length > 0}>
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
          ? `Text si můžete upravit: zkopírujte ho do dopisu nebo e-mailu. Vlastníkovi musí dojít do ${datum(data.doruceni)}.`
          : 'Vyúčtování ještě není zaúčtované a čísla se můžou změnit. Vlastníkům ho posílejte až po zaúčtování.'}
      </p>
      {data.zapis && (
        <Rozeslat druh="vyuctovani_sluzeb" klic={data.rozeslani} nazev={`Vyúčtování služeb za rok ${data.rok}`} />
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
  const sluzby = Object.fromEntries(data.sluzby.map((x) => [x.kod, x]))
  const sOsobami = data.sluzby.some((x) => x.klic === 'osoby')
  // Část vyúčtování za vlastnické období: spotřeba za celý rok by tu byla zavádějící
  // a nezaplacené zálohy dřívějšího vlastníka se vedou zvlášť.
  const j = o
    ? {
        ...jednotka,
        ...o,
        polozky: o.polozky.map((p) => ({ ...p, spotreba: null })),
        nezaplacene: o.soucasny ? jednotka.nezaplacene : 0,
      }
    : jednotka
  const drivejsi = o !== null && !o.soucasny
  return (
    <>
      <article className="upominka" data-jednotka={j.jednotka} data-osoby={drivejsi ? o.osoby.join(',') : undefined}>
        <p>
          <strong>{data.svj}</strong>
        </p>
        <HlavickaVlastnika jednotka={j.jednotka} vlastnici={j.vlastnici} drivejsi={drivejsi} />
        <p className="vpravo">Dne {datum(data.dnes)}</p>
        <h2>Vyúčtování služeb za rok {data.rok}</h2>
        {o ? (
          <UvodObdobi o={o} jednotka={j.jednotka} rok={data.rok} />
        ) : (
          <p>
            Posíláme vyúčtování záloh na služby spojené s užíváním jednotky {j.jednotka} za období od 1. 1. do 31.
            12. {data.rok}
            {sOsobami && `. V jednotce bylo podle předpisu záloh v průměru ${osoby(j.osobomesice)}`}.
          </p>
        )}
        <table className="polozky-dluhu">
          <thead>
            <tr>
              <th>Služba</th>
              <th className="cislo">Náklady domu</th>
              <th className="cislo">Na vaši jednotku</th>
              <th className="cislo">Vaše zálohy</th>
            </tr>
          </thead>
          <tbody>
            {j.polozky
              .filter((p) => p.naklady || p.zalohy || sluzby[p.kod].naklady)
              .map((p) => (
                <tr key={p.kod}>
                  <td>
                    {sluzby[p.kod].nazev}
                    <br />
                    <span className="tlumene">
                      {sluzby[p.kod].jak_se_deli}
                      {p.spotreba !== null && `, vaše spotřeba ${cislo(p.spotreba)} ${sluzby[p.kod].merna_jednotka}`}
                    </span>
                  </td>
                  <td className="cislo">{kc(sluzby[p.kod].naklady)}</td>
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
            Přeplatek vám vrátíme do {datum(data.splatnost)}
            {j.nezaplacene > 0 ? ', nejdřív ho ale započteme na nezaplacené zálohy' : ''}.
          </p>
        )}
        {j.nezaplacene > 0 ? (
          <p>
            Zálohy v tabulce jsou podle předpisu. Za rok {data.rok} u nás evidujeme nezaplacené měsíční zálohy{' '}
            {kc(j.nezaplacene)}; ty dlužíte zvlášť, nad rámec tohoto vyúčtování.
          </p>
        ) : (
          <p>Zálohy v tabulce jsou podle předpisu.</p>
        )}
        <p>
          Pokud chcete vidět podklady, ze kterých vyúčtování vychází, nebo s ním nesouhlasíte, napište nám do 30 dnů od
          doručení. Na námitky odpovíme do 30 dnů od jejich doručení.
        </p>
        <p>Za výbor společenství</p>
      </article>
    </>
  )
}
