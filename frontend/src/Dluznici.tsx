import { Fragment, useEffect, useState } from 'react'
import { api } from './auth'
import { Chyba, Nacitani } from './ui'
import { kc } from './penize'
import { PotvrzeniDluhu } from './PotvrzeniDluhu'

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
  polozky: Polozka[]
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
                  <tr id={`jednotka-${j.jednotka}`}>
                    <td>{j.jednotka}</td>
                    <td className={j.po_splatnosti ? 'cislo dluh' : 'cislo'}>
                      {j.po_splatnosti ? kc(j.po_splatnosti) : '–'}
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
                        {j.po_splatnosti > 0 && <PoznamkaKUroku data={data} j={j} />}
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
    </>
  )
}

function procent(setiny: number) {
  return `${(setiny / 100).toLocaleString('cs-CZ', { minimumFractionDigits: 2 })} %`
}

function PoznamkaKUroku({ data, j }: { data: Data; j: Jednotka }) {
  return (
    <p className="tlumene">
      {j.urok > 0 && <>Úrok z prodlení ze zbývajících částek k dnešku: {kc(j.urok)}. </>}
      {j.urok_neuplny &&
        'U dluhů z minulých let aplikace nezná splatnost, úrok z nich proto nepočítá. '}
      Zákonný úrok je repo sazba ČNB k prvnímu dni pololetí, kdy prodlení začalo, plus 8 procentních
      bodů (nařízení vlády č. 351/2013 Sb.; sazby ověřené k {datum(data.sazby_overeny_k)}). Počítá
      se jen z toho, co ještě není zaplacené. Do účetnictví se úrok zapíše, až ho společenství
      po vlastníkovi skutečně požaduje.
    </p>
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
        Text si můžete upravit: zkopírujte ho do dopisu nebo e-mailu. Jméno a adresu vlastníka
        aplikace zatím nezná.
      </p>
      {j.urok > 0 && (
        <label className="neni-v-tisku">
          <input type="checkbox" checked={sUrokem} onChange={(e) => setSUrokem(e.target.checked)} />{' '}
          Uvést v upomínce úrok z prodlení ({kc(j.urok)})
        </label>
      )}
      <article className="upominka">
        <p>
          <strong>{data.svj}</strong>
        </p>
        <p>Vlastník jednotky {j.jednotka}</p>
        <p className="vpravo">Dne {datum(data.dnes)}</p>
        <h2>Upozornění na nezaplacené platby</h2>
        <p>Vážená paní, vážený pane,</p>
        <p>
          podle účetnictví společenství k {datum(data.dnes)} evidujeme u jednotky {j.jednotka}{' '}
          tyto platby po splatnosti:
        </p>
        <SeznamPolozek polozky={polozky} urok={sUrokem} />
        <p>
          <strong>Celkem k úhradě: {kc(j.po_splatnosti)}</strong>
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
