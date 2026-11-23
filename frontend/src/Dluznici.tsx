import { Fragment, useEffect, useState, type FormEvent } from 'react'
import { api } from './auth'
import { Chyba, Nacitani } from './ui'
import { ChybiVlastnici, HlavickaVlastnika, type Adresat } from './Vlastnici'
import { kc, naHalire } from './penize'
import { PotvrzeniDluhu } from './PotvrzeniDluhu'
import { Rozeslat } from './Rozeslat'

export type Polozka = {
  popis: string
  splatnost: string | null
  castka: number
  zbyva: number
  po_splatnosti: boolean
  urok: number | null
  sazba: number | null
}
export type Jednotka = {
  jednotka: string
  po_splatnosti: number
  nesplatne: number
  preplatek: number
  od: string | null
  z_minulych_let: boolean
  urok: number
  urok_neuplny: boolean
  urok_do: string | null
  sankce: number
  polozky: Polozka[]
  vlastnici: Adresat[]
}
type Odpis = {
  datum: string
  castka: number
  polozka: string
  rozhodnuti: string
  dluhy: string[]
  zbyva: number
}
type OdepsanaJednotka = {
  jednotka: string
  odepsano: number
  uhrazeno: number
  zbyva: number
  odpisy: Odpis[]
}
export type Data = {
  rok: number
  dnes: string
  svj: string
  ico: string | null
  sidlo: string | null
  ucet: string | null
  posledni_vypis: string | null
  nezauctovane_pohyby: number
  sazby_overeny_k: string
  zdroj_sazeb: string
  celkem_po_splatnosti: number
  jednotky: Jednotka[]
  odepsane: OdepsanaJednotka[]
  polozky_spravy: { kod: string; nazev: string }[]
}

export const datum = (d: string) => new Date(d).toLocaleDateString('cs-CZ')

function jednotek(n: number) {
  if (n === 1) return '1 jednotka'
  if (n >= 2 && n <= 4) return `${n} jednotky`
  return `${n} jednotek`
}

export function Dluznici() {
  const rok = new Date().getFullYear()
  const [data, setData] = useState<Data | null>(null)
  const [chyba, setChyba] = useState<string | null>(null)
  // Odkaz z okna domu na přehledu (#dluznici?jednotka=…) otevře rozpis té jednotky.
  const [otevrena, setOtevrena] = useState<string | null>(() =>
    new URLSearchParams(window.location.hash.split('?')[1] ?? '').get('jednotka'),
  )
  const [upominka, setUpominka] = useState<Jednotka | null>(null)
  const [potvrzeni, setPotvrzeni] = useState<Jednotka | null>(null)

  useEffect(() => {
    api<Data>(`/api/dluznici/${rok}`).then(setData).catch((e) => setChyba(e.message))
  }, [rok])

  useEffect(() => {
    if (data && otevrena)
      document.getElementById(`jednotka-${otevrena}`)?.scrollIntoView({ block: 'center' })
    // Jen po načtení dat; při dalším rozbalování už stránka neskáče.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data])

  if (!data) return chyba ? <Chyba text={chyba} /> : <Nacitani />

  if (upominka)
    return <Upominka data={data} jednotka={upominka} zpet={() => setUpominka(null)} />
  if (potvrzeni)
    return <PotvrzeniDluhu data={data} jednotka={potvrzeni} zpet={() => setPotvrzeni(null)} />

  const dluzi = data.jednotky.filter((j) => j.po_splatnosti > 0)

  return (
    <>
      <h1>Dlužníci</h1>
      <p>
        {dluzi.length === 0
          ? 'Žádná jednotka nemá nezaplacené platby po splatnosti.'
          : `Po splatnosti dluží ${jednotek(dluzi.length)}, celkem ${kc(data.celkem_po_splatnosti)}.`}
      </p>
      <p className="tlumene">
        Platba se vždy započítá na nejstarší dluh: nejdřív na dluhy z minulých let, potom na
        měsíční zálohy od nejstarší. Počítá se jen s platbami, které už jsou zaúčtované na
        stránce Banka.
      </p>
      <div className="tabulka-posun">
        <table className="dluznici">
          <thead>
            <tr>
              <th>Jednotka</th>
              <th className="cislo">Po splatnosti</th>
              <th>Dluží od</th>
              <th className="cislo">Ještě není splatné</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {data.jednotky.map((j) => {
              return (
                <Fragment key={j.jednotka}>
                  <tr id={`jednotka-${j.jednotka}`} className={j.po_splatnosti ? undefined : 'bez-dluhu'}>
                    <td>{j.jednotka}</td>
                    <td className={j.po_splatnosti ? 'cislo dluh' : 'cislo'}>
                      {j.po_splatnosti ? kc(j.po_splatnosti) : '–'}
                      {j.sankce > 0 && (
                        <span className="tlumene">
                          <br />a úrok {kc(j.sankce)}
                        </span>
                      )}
                    </td>
                    <td>
                      {j.z_minulych_let
                        ? 'z minulých let'
                        : j.od
                          ? datum(j.od)
                          : j.preplatek
                            ? `přeplatek ${kc(j.preplatek)}`
                            : 'má zaplaceno'}
                    </td>
                    <td className="cislo">{j.nesplatne ? kc(j.nesplatne) : ''}</td>
                    <td>
                      <button
                        className="odkaz"
                        aria-expanded={otevrena === j.jednotka}
                        onClick={() => setOtevrena(otevrena === j.jednotka ? null : j.jednotka)}
                      >
                        {otevrena === j.jednotka
                          ? 'Skrýt'
                          : j.polozky.length > 0
                            ? 'Co dluží'
                            : 'Podrobnosti'}
                      </button>
                    </td>
                  </tr>
                  {otevrena === j.jednotka && (
                    <tr className="rozpis">
                      <td colSpan={5}>
                        {j.polozky.length > 0 ? (
                          <SeznamPolozek polozky={j.polozky} urok />
                        ) : (
                          <p className="tlumene">Jednotka nemá žádné nezaplacené platby.</p>
                        )}
                        {j.preplatek > 0 && (
                          <p className="tlumene">Navíc má přeplatek {kc(j.preplatek)}.</p>
                        )}
                        {j.sankce > 0 && (
                          <p>
                            Předepsaný úrok z prodlení, který zbývá zaplatit: {kc(j.sankce)}.
                          </p>
                        )}
                        {j.po_splatnosti > 0 && <PoznamkaKUroku data={data} j={j} />}
                        {j.urok > 0 && <PredpisUroku data={data} j={j} setData={setData} />}
                        <OdepsanyDluh data={data} j={j} />
                        {j.po_splatnosti > 0 && <OdpisDluhu data={data} j={j} setData={setData} />}
                        <div className="radek">
                          {j.po_splatnosti > 0 && (
                            <button className="vedlejsi" onClick={() => setUpominka(j)}>
                              Podklad pro upomínku
                            </button>
                          )}
                          <button className="vedlejsi" onClick={() => setPotvrzeni(j)}>
                            Potvrzení o dluzích pro prodej jednotky
                          </button>
                        </div>
                      </td>
                    </tr>
                  )}
                </Fragment>
              )
            })}
          </tbody>
        </table>
      </div>
      <OdepsaneDluhy data={data} />
    </>
  )
}

function OdepsanyDluh({ data, j }: { data: Data; j: Jednotka }) {
  const o = data.odepsane.find((x) => x.jednotka === j.jednotka)
  if (!o) return null
  return (
    <p className="tlumene">
      {o.zbyva > 0
        ? `Odepsaný dluh, který zbývá zaplatit: ${kc(o.zbyva)}. `
        : `Odepsaný dluh ${kc(o.odepsano)} už je zaplacený. `}
      Podrobnosti jsou v části Odepsané dluhy pod tabulkou.
    </p>
  )
}

function OdpisDluhu({
  data,
  j,
  setData,
}: {
  data: Data
  j: Jednotka
  setData: (d: Data) => void
}) {
  const [otevreno, setOtevreno] = useState(false)
  const [castka, setCastka] = useState(() => kc(j.po_splatnosti).replace(' Kč', ''))
  const [polozka, setPolozka] = useState(() =>
    data.polozky_spravy.length === 1 ? data.polozky_spravy[0].kod : '',
  )
  const [rozhodnuti, setRozhodnuti] = useState('')
  const [pracuji, setPracuji] = useState(false)
  const [chyba, setChyba] = useState<string | null>(null)
  const halire = naHalire(castka)
  const lzeOdepsat = !!halire && halire > 0 && !!polozka && !!rozhodnuti.trim()

  async function odepsat(e: FormEvent) {
    e.preventDefault()
    if (!lzeOdepsat) return
    setPracuji(true)
    setChyba(null)
    try {
      setData(
        await api<Data>(`/api/dluznici/${data.rok}/odpis`, {
          method: 'POST',
          json: { jednotka: j.jednotka, castka: halire, polozka, rozhodnuti },
        }),
      )
    } catch (e) {
      setChyba((e as Error).message)
      setPracuji(false)
    }
  }

  if (!otevreno)
    return (
      <div className="radek">
        <button className="vedlejsi" onClick={() => setOtevreno(true)}>
          Odepsat nedobytný dluh
        </button>
      </div>
    )
  return (
    <form className="upozorneni odpis-dluhu" onSubmit={odepsat}>
      <p>
        Dluh, který už nejde vymoci (třeba po skončeném insolvenčním řízení), se odepisuje
        na základě rozhodnutí výboru nebo shromáždění. Odepisuje se od nejstaršího dluhu.
        Odpis je náklad na správu domu, takže ho vyúčtování záloh rozdělí mezi všechny
        vlastníky ve vybrané položce. Dluh tím nezaniká: aplikace ho dál vede mezi
        odepsanými, a když ho dlužník později zaplatí, vyúčtování vlastníkům zase vrátí, co
        za odpis zaplatili.
      </p>
      <label>
        Kdo a kdy o odpisu rozhodl
        <input
          value={rozhodnuti}
          onChange={(e) => setRozhodnuti(e.target.value)}
          placeholder="např. usnesení výboru ze dne 5. 5. 2026"
          maxLength={200}
        />
      </label>
      <label>
        Do které položky správy odpis patří
        <select value={polozka} onChange={(e) => setPolozka(e.target.value)}>
          {data.polozky_spravy.length > 1 && <option value="">Vyberte položku</option>}
          {data.polozky_spravy.map((p) => (
            <option key={p.kod} value={p.kod}>
              {p.nazev}
            </option>
          ))}
        </select>
      </label>
      <div className="radek">
        <label>
          Odepsat{' '}
          <input
            value={castka}
            onChange={(e) => setCastka(e.target.value)}
            inputMode="decimal"
            size={12}
          />{' '}
          Kč
        </label>
        <button type="submit" disabled={pracuji || !lzeOdepsat}>
          {pracuji ? 'Odepisuji…' : 'Odepsat dluh'}
        </button>
        <button type="button" className="vedlejsi" onClick={() => setOtevreno(false)}>
          Zrušit
        </button>
        {chyba && <span className="chyba">{chyba}</span>}
      </div>
    </form>
  )
}

function OdepsaneDluhy({ data }: { data: Data }) {
  if (data.odepsane.length === 0) return null
  return (
    <section className="odepsane-dluhy">
      <h2>Odepsané dluhy</h2>
      <p className="tlumene">
        Odepsaný dluh se v účetnictví už nevykazuje jako pohledávka, ale nezaniká. Když ho
        dlužník nebo jeho dědic zaplatí, zaúčtujte platbu na stránce Banka jako „Úhrada
        dříve odepsaného dluhu“.
      </p>
      <div className="tabulka-posun">
        <table className="dluznici">
          <thead>
            <tr>
              <th>Jednotka</th>
              <th>Odepsáno</th>
              <th>Co se odepsalo</th>
              <th className="cislo">Částka</th>
              <th className="cislo">Zbývá zaplatit</th>
            </tr>
          </thead>
          <tbody>
            {data.odepsane.flatMap((o) =>
              o.odpisy.map((x, i) => (
                <tr key={`${o.jednotka}-${i}`} className={x.zbyva ? undefined : 'bez-dluhu'}>
                  <td>{i === 0 ? o.jednotka : ''}</td>
                  <td>
                    {datum(x.datum)}
                    <span className="tlumene">
                      <br />
                      {x.rozhodnuti}
                    </span>
                  </td>
                  <td>
                    {x.dluhy.join(', ')}
                    <span className="tlumene">
                      <br />
                      položka {x.polozka}
                    </span>
                  </td>
                  <td className="cislo">{kc(x.castka)}</td>
                  <td className="cislo">{x.zbyva ? kc(x.zbyva) : 'zaplaceno'}</td>
                </tr>
              )),
            )}
          </tbody>
        </table>
      </div>
    </section>
  )
}

function procent(setiny: number) {
  return `${(setiny / 100).toLocaleString('cs-CZ', { minimumFractionDigits: 2 })} %`
}

function PoznamkaKUroku({ data, j }: { data: Data; j: Jednotka }) {
  return (
    <p className="tlumene">
      {j.urok > 0 && <>Úrok z prodlení ze zbývajících částek k dnešku: {kc(j.urok)}. </>}
      {j.urok_do && (
        <>
          Úrok do {datum(j.urok_do)} už společenství předepsalo, tady je spočtený jen za dobu
          potom.{' '}
        </>
      )}
      {j.urok_neuplny &&
        'U dluhů z minulých let aplikace nezná splatnost, úrok z nich proto nepočítá. '}
      Zákonný úrok je repo sazba ČNB k prvnímu dni pololetí, kdy prodlení začalo, plus 8 procentních
      bodů (nařízení vlády č. 351/2013 Sb.; sazby ověřené k {datum(data.sazby_overeny_k)}). Počítá
      se jen z toho, co ještě není zaplacené. Do účetnictví se úrok zapíše, až ho společenství
      po vlastníkovi skutečně požaduje.
    </p>
  )
}

function PredpisUroku({
  data,
  j,
  setData,
}: {
  data: Data
  j: Jednotka
  setData: (d: Data) => void
}) {
  const [otevreno, setOtevreno] = useState(false)
  const [castka, setCastka] = useState(() => kc(j.urok).replace(' Kč', ''))
  const [pracuji, setPracuji] = useState(false)
  const [chyba, setChyba] = useState<string | null>(null)
  const halire = naHalire(castka)

  async function predepsat(e: FormEvent) {
    e.preventDefault()
    if (!halire || halire <= 0) return
    setPracuji(true)
    setChyba(null)
    try {
      setData(
        await api<Data>(`/api/dluznici/${data.rok}/urok`, {
          method: 'POST',
          json: { jednotka: j.jednotka, castka: halire },
        }),
      )
    } catch (e) {
      setChyba((e as Error).message)
      setPracuji(false)
    }
  }

  if (!otevreno)
    return (
      <div className="radek">
        <button className="vedlejsi" onClick={() => setOtevreno(true)}>
          Požadovat úrok z prodlení
        </button>
      </div>
    )
  return (
    <form className="upozorneni" onSubmit={predepsat}>
      <p>
        Když společenství úrok po vlastníkovi požaduje, zapíše se do účetnictví jako jeho dluh
        a výnos společenství. Vlastník ho platí zvlášť od záloh a do dluhů, které při prodeji
        přecházejí na kupujícího, se nepočítá. Daní se, až ho vlastník zaplatí. Částku můžete
        snížit, třeba když se výbor rozhodl část odpustit.
      </p>
      <div className="radek">
        <label>
          Úrok k {datum(data.dnes)}{' '}
          <input
            value={castka}
            onChange={(e) => setCastka(e.target.value)}
            inputMode="decimal"
            size={12}
          />{' '}
          Kč
        </label>
        <button type="submit" disabled={pracuji || !halire || halire <= 0}>
          {pracuji ? 'Zapisuji…' : 'Zapsat úrok vlastníkovi'}
        </button>
        <button type="button" className="vedlejsi" onClick={() => setOtevreno(false)}>
          Zrušit
        </button>
        {chyba && <span className="chyba">{chyba}</span>}
      </div>
    </form>
  )
}

export function SeznamPolozek({ polozky, urok = false }: { polozky: Polozka[]; urok?: boolean }) {
  return (
    <table className="polozky-dluhu">
      <thead>
        <tr>
          <th>Za co</th>
          <th>Splatnost</th>
          <th className="cislo">Zbývá zaplatit</th>
          {urok && <th className="cislo">Úrok z prodlení</th>}
        </tr>
      </thead>
      <tbody>
        {polozky.map((p, i) => (
          <tr key={i}>
            <td>{p.popis}</td>
            <td>
              {p.splatnost ? datum(p.splatnost) : 'z minulých let'}
              {!p.po_splatnosti && <span className="tlumene"> (ještě není splatné)</span>}
            </td>
            <td className="cislo">
              {kc(p.zbyva)}
              {p.zbyva < p.castka && <span className="tlumene"> z {kc(p.castka)}</span>}
            </td>
            {urok && (
              <td className="cislo">
                {p.urok ? kc(p.urok) : p.po_splatnosti && p.urok === null ? '?' : ''}
                {p.urok && p.sazba ? <span className="tlumene"> ({procent(p.sazba)})</span> : null}
              </td>
            )}
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function Upominka({ data, jednotka: j, zpet }: { data: Data; jednotka: Jednotka; zpet: () => void }) {
  const doKdy = new Date(data.dnes)
  doKdy.setDate(doKdy.getDate() + 15)
  const polozky = j.polozky.filter((p) => p.po_splatnosti)
  const [sUrokem, setSUrokem] = useState(j.urok > 0)

  return (
    <>
      <div className="radek neni-v-tisku">
        <button className="vedlejsi" onClick={zpet}>
          Zpět na dlužníky
        </button>
        <button onClick={() => window.print()}>Vytisknout</button>
      </div>
      <p className="tlumene neni-v-tisku">
        Text si můžete upravit: zkopírujte ho do dopisu nebo e-mailu.
      </p>
      <Rozeslat druh="upominka" klic={`upominka:${j.jednotka}`} nazev="Upozornění na nezaplacené platby" />
      <ChybiVlastnici jednotky={[j]} />
      {j.urok > 0 && (
        <label className="neni-v-tisku">
          <input type="checkbox" checked={sUrokem} onChange={(e) => setSUrokem(e.target.checked)} />{' '}
          Uvést v upomínce úrok z prodlení ({kc(j.urok)})
        </label>
      )}
      <article className="upominka" data-jednotka={j.jednotka}>
        <p>
          <strong>{data.svj}</strong>
        </p>
        <HlavickaVlastnika jednotka={j.jednotka} vlastnici={j.vlastnici} />
        <p className="vpravo">Dne {datum(data.dnes)}</p>
        <h2>Upozornění na nezaplacené platby</h2>
        <p>Vážená paní, vážený pane,</p>
        <p>
          podle účetnictví společenství k {datum(data.dnes)} evidujeme u jednotky {j.jednotka}{' '}
          tyto platby po splatnosti:
        </p>
        <SeznamPolozek polozky={polozky} urok={sUrokem} />
        {j.sankce > 0 && (
          <p>Dále evidujeme nezaplacený úrok z prodlení, který jsme vám předepsali: {kc(j.sankce)}.</p>
        )}
        <p>
          <strong>Celkem k úhradě: {kc(j.po_splatnosti + j.sankce)}</strong>
        </p>
        {sUrokem && (
          <p>
            Za dobu prodlení vám ke dni {datum(data.dnes)} vznikl zákonný úrok z prodlení podle
            nařízení vlády č. 351/2013 Sb. ve výši {kc(j.urok)}. Úrok dále roste, dokud dluh
            nezaplatíte; společenství ho může požadovat spolu s dlužnou částkou.
          </p>
        )}
        <p>
          Prosíme o zaplacení do {datum(doKdy.toISOString())}
          {data.ucet ? ` na účet ${data.ucet}` : ' na účet společenství'} s variabilním
          symbolem, kterým platíte zálohy. Pokud jste mezitím zaplatili, dejte nám prosím vědět
          a tento dopis neberte v úvahu.
        </p>
        <p>Za výbor společenství</p>
      </article>
    </>
  )
}
