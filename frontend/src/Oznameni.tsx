import { useEffect, useState } from 'react'
import { api } from './auth'
import { StavFormulare, useSdilenyFormular } from './sdilenyFormular'
import { kc } from './penize'
import { SKUPINY } from './Predpisy'
import { Chyba, Nacitani } from './ui'
import { Rozeslat } from './Rozeslat'
import { ChybiVlastnici, HlavickaVlastnika, type Adresat } from './Vlastnici'
import './oznameni.css'

type Slozka = {
  kod: string
  nazev: string
  skupina: 'fond_oprav' | 'sprava' | 'sluzby'
  puvodne: number | null
  nove: number | null
}
type Jednotka = {
  jednotka: string
  puvodne: number
  nove: number
  zmenena: boolean
  slozky: Slozka[]
  vlastnici: Adresat[]
  doruceno: string | null
  sluzby_od: string | null
}
type Data = {
  svj: string
  ico: string | null
  sidlo: string | null
  dnes: string
  splatnost_den: number
  verze: string[]
  plati_od: string
  predchozi_od: string | null
  dorucit_do: string
  zdroj: string
  jednotky: Jednotka[]
  rozeslani: string
}

const datum = (d: string) => new Date(d).toLocaleDateString('cs-CZ')
const castka = (h: number | null) => (h === null ? '–' : kc(h))

function rozdil(h: number) {
  if (h === 0) return 'beze změny'
  return h > 0 ? `+${kc(h)}` : `−${kc(-h)}`
}

export function Oznameni() {
  const [verze, setVerze] = useState<string | null>(null)
  const [data, setData] = useState<Data | null>(null)
  const [chyba, setChyba] = useState<string | null>(null)
  const [tisk, setTisk] = useState<Jednotka[] | null>(null)
  const formular = useSdilenyFormular<{ oduvodneni: string }>(
    'oznameni-zaloh',
    data?.plati_od ?? null,
    () => ({ oduvodneni: '' }),
    {
      zPrehlizece: data ? {
        klic: `oznameni-oduvodneni-${data.plati_od}`,
        preved: (t) => ({ oduvodneni: t }),
      } : undefined,
    },
  )
  const oduvodneni = formular.obsah?.oduvodneni ?? ''

  useEffect(() => {
    api<Data>(verze ? `/api/oznameni-zaloh/${verze}` : '/api/oznameni-zaloh')
      .then(setData)
      .catch((e) => setChyba(e.message))
  }, [verze])

  useEffect(() => {
    window.scrollTo(0, 0)
  }, [tisk])

  if (!data) return chyba ? <Chyba text={chyba} /> : <Nacitani />
  if (tisk)
    return <Tisk data={data} jednotky={tisk} oduvodneni={oduvodneni} zpet={() => setTisk(null)} />

  const prvni = data.predchozi_od === null
  const pozde = !prvni && new Date(data.dnes) > new Date(data.dorucit_do)
  const zmenene = data.jednotky.filter((j) => j.zmenena)

  return (
    <>
      <p>
        <a href="#predpisy">← Předpisy</a>
      </p>
      <h1>Oznámení vlastníkům o výši záloh</h1>
      <p>
        Když se mění měsíční zálohy, musí to vlastníci dostat písemně a s odůvodněním. Novou
        zálohu na služby lze požadovat nejdřív od prvního dne měsíce, který následuje po doručení
        oznámení. Výši příspěvků do fondu oprav a na správu domu určuje shromáždění nebo výbor
        podle stanov; je rozumné oznámit všechny změny najednou.
      </p>
      {data.verze.length > 1 && (
        <label className="vyber-roku">
          Předpis platný od{' '}
          <select value={data.plati_od} onChange={(e) => setVerze(e.target.value)}>
            {data.verze.map((v) => (
              <option key={v} value={v}>
                {datum(v)}
              </option>
            ))}
          </select>
        </label>
      )}
      <p className={pozde ? 'upozorneni' : undefined}>
        Aby nová výše platila od {datum(data.plati_od)}, musí oznámení vlastníkům dojít nejpozději{' '}
        {datum(data.dorucit_do)}.
        {pozde &&
          ' Ten den už minul: zálohy na služby v nové výši lze požadovat až od prvního dne měsíce po doručení oznámení.'}
      </p>
      {prvni ? (
        <p className="tlumene">
          Tohle je první předpis v aplikaci, není s čím porovnat. Oznámení uvede jen novou výši
          záloh.
        </p>
      ) : (
        <p className="tlumene">
          Ve srovnání s předpisem od {datum(data.predchozi_od!)} se zálohy mění u{' '}
          {zmenene.length} z {data.jednotky.length} jednotek.
        </p>
      )}

      <label className="oduvodneni">
        <strong>Odůvodnění změny</strong>
        <span className="tlumene">
          Vytiskne se v každém oznámení. Bez odůvodnění nemusí vlastník zvýšenou zálohu na služby
          platit. Text se ukládá průběžně a uvidí ho i ostatní členové výboru.
        </span>
        <textarea
          rows={4}
          value={oduvodneni}
          disabled={formular.obsah === null}
          placeholder="Např. Od 1. 7. zdražuje dodavatel tepla o 20 %. Výbor proto zvyšuje zálohu na teplo."
          onChange={(e) => formular.zmen({ oduvodneni: e.target.value })}
        />
      </label>
      <StavFormulare f={formular} />

      <div className="radek">
        <button onClick={() => setTisk(prvni ? data.jednotky : zmenene)} disabled={!prvni && zmenene.length === 0}>
          {prvni ? 'Vytisknout oznámení všem' : `Vytisknout oznámení (${zmenene.length})`}
        </button>
      </div>

      <div className="tabulka-posun">
        <table>
          <thead>
            <tr>
              <th>Jednotka</th>
              {!prvni && <th className="cislo">Dosud měsíčně</th>}
              <th className="cislo">Nově měsíčně</th>
              {!prvni && <th className="cislo">Změna</th>}
              <th>Doručeno</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {data.jednotky.map((j) => (
              <tr key={j.jednotka}>
                <td>{j.jednotka}</td>
                {!prvni && <td className="cislo">{kc(j.puvodne)}</td>}
                <td className="cislo">{kc(j.nove)}</td>
                {!prvni && <td className="cislo">{rozdil(j.nove - j.puvodne)}</td>}
                <td>
                  {j.doruceno ? datum(j.doruceno) : <span className="tlumene">zatím ne</span>}
                  {j.sluzby_od && (
                    <div className="varovani-text">zálohy na služby v nové výši až od {datum(j.sluzby_od)}</div>
                  )}
                </td>
                <td>
                  <button className="odkaz" onClick={() => setTisk([j])}>
                    Oznámení
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}

function Tisk({
  data,
  jednotky,
  oduvodneni,
  zpet,
}: {
  data: Data
  jednotky: Jednotka[]
  oduvodneni: string
  zpet: () => void
}) {
  const prvni = data.predchozi_od === null
  return (
    <>
      <div className="radek neni-v-tisku">
        <button className="vedlejsi" onClick={zpet}>
          Zpět
        </button>
        <button onClick={() => window.print()}>Vytisknout</button>
      </div>
      {!oduvodneni.trim() && !prvni && (
        <p className="upozorneni neni-v-tisku">
          Chybí odůvodnění změny. Doplňte ho na předchozí stránce.
        </p>
      )}
      <Rozeslat
        druh="oznameni"
        klic={data.rozeslani}
        nazev={`${prvni ? 'Oznámení o výši měsíčních záloh' : 'Oznámení o nové výši měsíčních záloh'} od ${datum(data.plati_od)}`}
      />
      <p className="tlumene neni-v-tisku">Každá jednotka je na samostatné stránce.</p>
      <ChybiVlastnici jednotky={jednotky} />
      {jednotky.map((j) => (
        <article key={j.jednotka} className="upominka oznameni" data-jednotka={j.jednotka}>
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
          <HlavickaVlastnika jednotka={j.jednotka} vlastnici={j.vlastnici} />
          <p className="vpravo">Dne {datum(data.dnes)}</p>
          <h2>
            {prvni ? 'Oznámení o výši měsíčních záloh' : 'Oznámení o nové výši měsíčních záloh'} od{' '}
            {datum(data.plati_od)}
          </h2>
          <p>Vážená paní, vážený pane,</p>
          <p>
            od {datum(data.plati_od)} budou měsíční zálohy za jednotku {j.jednotka}{' '}
            {kc(j.nove)}
            {!prvni && <> (dosud {kc(j.puvodne)})</>}. Rozpis:
          </p>
          <table className="polozky-dluhu">
            <thead>
              <tr>
                <th>Za co</th>
                {!prvni && <th className="cislo">Dosud</th>}
                <th className="cislo">Nově</th>
              </tr>
            </thead>
            {SKUPINY.map((sk) => {
              const radky = j.slozky.filter((s) => s.skupina === sk.id)
              if (radky.length === 0) return null
              return (
                <tbody key={sk.id}>
                  <tr className="skupina-oznameni">
                    <th colSpan={prvni ? 2 : 3}>{sk.nazev}</th>
                  </tr>
                  {radky.map((s) => (
                    <tr key={s.kod} className={s.puvodne !== s.nove && !prvni ? 'zmena' : undefined}>
                      <td>{s.nazev}</td>
                      {!prvni && <td className="cislo">{castka(s.puvodne)}</td>}
                      <td className="cislo">{castka(s.nove)}</td>
                    </tr>
                  ))}
                </tbody>
              )
            })}
            <tbody>
              <tr className="soucet">
                <td>Celkem měsíčně</td>
                {!prvni && <td className="cislo">{kc(j.puvodne)}</td>}
                <td className="cislo">{kc(j.nove)}</td>
              </tr>
            </tbody>
          </table>
          {oduvodneni.trim() && (
            <>
              <h3>Odůvodnění</h3>
              {oduvodneni
                .trim()
                .split(/\n\s*\n/)
                .map((odstavec, i) => (
                  <p key={i}>{odstavec}</p>
                ))}
            </>
          )}
          <p>
            Zálohy plaťte jako dosud do {data.splatnost_den}. dne v měsíci se stejným variabilním
            symbolem. Pokud máte trvalý příkaz, upravte prosím jeho částku.
          </p>
          <p>Za výbor společenství</p>
        </article>
      ))}
    </>
  )
}
