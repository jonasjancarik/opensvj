import { Fragment, useEffect, useState, type FormEvent } from 'react'
import { api } from './auth'
import { kc } from './penize'
import { potvrdit } from './potvrdit'
import { Chyba, Nacitani } from './ui'
import './tisk.css'
import './uzaverka.css'

type Odskrtnuti = { kdo: string; jmeno: string; kdy: string }
type Kontrola = {
  kod: string
  nazev: string
  stav: 'hotovo' | 'chybi' | 'rucne' | 'info'
  detail: string
  odkaz: string | null
  odskrtnuti: Odskrtnuti | null
}
type RadekVykazu = { strana: string; radek: string; nazev: string; castka: number; tisice: number }
type Soupis = {
  ucet: string
  nazev: string
  zustatek: number
  zpusob: string
  polozky: { popis: string; castka: number }[]
}
type Vynos = {
  popis: string
  castka: number
  zdaneni: 'nepredmetne' | 'srazkova' | 'predmetne' | 'nezname'
  poznamka: string
}
type Data = {
  rok: number
  k_datu: string
  dnes: string
  svj: string
  ico: string | null
  sidlo: string | null
  kontroly: Kontrola[]
  rozvaha: RadekVykazu[]
  vysledovka: RadekVykazu[]
  vysledek: number
  soupisy: Soupis[]
  dan: { musi_podat: boolean; vynosy: Vynos[] }
  priloha: { nadpis: string; odstavce: string[] }[]
  uzavreni: {
    stav: 'otevrene' | 'uzavrene' | null
    dalsi: 'otevrene' | 'uzavrene' | null
    zapisy: string[]
    proc_nejde: string[]
  }
}

const ZALOZKY = {
  kontroly: 'Co zbývá udělat',
  vykazy: 'Rozvaha a výsledovka',
  inventura: 'Inventura',
  dan: 'Daň z příjmů',
  priloha: 'Příloha k závěrce',
} as const
type Zalozka = keyof typeof ZALOZKY

const STAV: Record<Kontrola['stav'], string> = {
  hotovo: 'Hotovo',
  chybi: 'Chybí',
  rucne: 'Zkontrolujte',
  info: 'Pro informaci',
}
const ZDANENI: Record<Vynos['zdaneni'], string> = {
  nepredmetne: 'nedaní se',
  srazkova: 'daň už srazila banka',
  predmetne: 'daní se',
  nezname: 'nevíme, ověřte',
}

const datum = (d: string) => new Date(d).toLocaleDateString('cs-CZ')

/**
 * Ručně odškrtnuté body seznamu. Ukládají se v databázi, takže je vidí celý výbor;
 * u každého je vidět, kdo ho odškrtl a kdy.
 */
function useOdskrtnute(data: Data, poZmene: () => void) {
  const [odskrtnute, setOdskrtnute] = useState<Record<string, Odskrtnuti | null>>(() =>
    Object.fromEntries(data.kontroly.map((k) => [k.kod, k.odskrtnuti])),
  )
  const [ukladam, setUkladam] = useState<Set<string>>(new Set())
  const [chyba, setChyba] = useState<string | null>(null)

  async function nastav(kod: string, hotovo: boolean) {
    setUkladam((u) => new Set(u).add(kod))
    setChyba(null)
    try {
      const z = await api<Odskrtnuti | null>(`/api/uzaverka/${data.rok}/odskrtnuti`, {
        method: 'POST',
        json: { kod, hotovo },
      })
      setOdskrtnute((o) => ({ ...o, [kod]: z }))
      poZmene()
    } catch (e) {
      setChyba((e as Error).message)
    } finally {
      setUkladam((u) => {
        const n = new Set(u)
        n.delete(kod)
        return n
      })
    }
  }

  // Dřív si odškrtnutí pamatoval jen prohlížeč; jednou je přeneseme do databáze.
  useEffect(() => {
    const klic = `uzaverka-${data.rok}`
    let stare: string[] = []
    try {
      stare = JSON.parse(localStorage.getItem(klic) ?? '[]')
    } catch {
      return
    }
    if (!Array.isArray(stare) || stare.length === 0) return
    const kody = data.kontroly
      .filter((k) => k.stav === 'rucne' && !k.odskrtnuti && stare.includes(k.nazev))
      .map((k) => k.kod)
    Promise.all(kody.map((k) => nastav(k, true))).then(() => {
      try {
        localStorage.removeItem(klic)
      } catch {
        /* nic */
      }
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data])

  return { odskrtnute, nastav, ukladam, chyba }
}

const kdy = (d: string) => new Date(d).toLocaleDateString('cs-CZ')

export function Uzaverka() {
  // Uzávěrka se dělá v prvních měsících po konci roku, proto do června ukazuje minulý rok.
  const dnes = new Date()
  const [rok, setRok] = useState(dnes.getMonth() < 6 ? dnes.getFullYear() - 1 : dnes.getFullYear())
  const [data, setData] = useState<Data | null>(null)
  const [chyba, setChyba] = useState<string | null>(null)
  const [zalozka, setZalozka] = useState<Zalozka>('kontroly')
  const [tisk, setTisk] = useState<'soupisy' | 'priloha' | null>(null)

  useEffect(() => {
    setData(null)
    api<Data>(`/api/uzaverka/${rok}`).then(setData).catch((e) => setChyba(e.message))
  }, [rok])

  if (!data) return chyba ? <Chyba text={chyba} /> : <Nacitani />
  if (tisk === 'soupisy') return <TiskSoupisu data={data} zpet={() => setTisk(null)} />
  if (tisk === 'priloha') return <TiskPrilohy data={data} zpet={() => setTisk(null)} />

  return (
    <>
      <h1>Uzávěrka roku {data.rok}</h1>
      <p>
        Na konci roku je potřeba dotáhnout účtování, zkontrolovat stav účtů a dluhů
        (inventura), sestavit účetní závěrku a zjistit, jestli SVJ musí podat daňové přiznání.
        Závěrku schvaluje shromáždění a do 30 dnů od schválení se ukládá do sbírky listin.
      </p>
      <div className="radek">
        <label className="vyber-roku">
          Rok{' '}
          <select value={rok} onChange={(e) => setRok(Number(e.target.value))}>
            {[dnes.getFullYear(), dnes.getFullYear() - 1].map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
        </label>
      </div>
      <nav className="zalozky" aria-label="Části uzávěrky">
        {(Object.keys(ZALOZKY) as Zalozka[]).map((z) => (
          <button
            key={z}
            className={zalozka === z ? 'aktivni' : undefined}
            aria-current={zalozka === z ? 'page' : undefined}
            onClick={() => setZalozka(z)}
          >
            {ZALOZKY[z]}
          </button>
        ))}
      </nav>
      {data.uzavreni.stav === 'uzavrene' && (
        <p className="uspech">
          Rok {data.rok} je uzavřený a zápisy do něj už nejdou. Zůstatky jsou převedené do roku{' '}
          {data.rok + 1}.
        </p>
      )}
      {zalozka === 'kontroly' && <Kontroly data={data} setData={setData} />}
      {zalozka === 'vykazy' && <Vykazy data={data} />}
      {zalozka === 'inventura' && <Inventura data={data} tisk={() => setTisk('soupisy')} />}
      {zalozka === 'dan' && <Dan data={data} />}
      {zalozka === 'priloha' && <Priloha data={data} tisk={() => setTisk('priloha')} />}
    </>
  )
}

function Kontroly({ data, setData }: { data: Data; setData: (d: Data) => void }) {
  const obnovit = () => {
    api<Data>(`/api/uzaverka/${data.rok}`)
      .then(setData)
      .catch(() => undefined)
  }
  const { odskrtnute, nastav, ukladam, chyba } = useOdskrtnute(data, obnovit)
  const zbyva = data.kontroly.filter(
    (k) => k.stav === 'chybi' || (k.stav === 'rucne' && !odskrtnute[k.kod]),
  ).length
  return (
    <>
      <DalsiRok data={data} setData={setData} />
      <p className="tlumene">
        {zbyva === 0
          ? 'Všechno je hotové nebo odškrtnuté.'
          : `Zbývá ${zbyva} ${zbyva === 1 ? 'bod' : zbyva < 5 ? 'body' : 'bodů'}. Co jde ověřit z účetnictví, aplikace ověřila sama; ostatní body odškrtněte, až je zkontrolujete. Odškrtnutí uvidí celý výbor.`}
      </p>
      {chyba && (
        <p className="upozorneni" role="alert">
          Odškrtnutí se nepodařilo uložit: {chyba}
        </p>
      )}
      <ul className="kontroly-uzaverky">
        {data.kontroly.map((k) => {
          const z = k.stav === 'rucne' ? odskrtnute[k.kod] : null
          const odskrtnuto = !!z
          return (
            <li key={k.kod} className={`kontrola kontrola-${odskrtnuto ? 'hotovo' : k.stav}`}>
              <span className="kontrola-stav">{odskrtnuto ? 'Zkontrolováno' : STAV[k.stav]}</span>
              <div>
                <strong>{k.nazev}</strong>
                {k.detail && <p>{k.detail}</p>}
                <div className="radek">
                  {k.odkaz && k.stav !== 'hotovo' && <a href={`#${k.odkaz}`}>Otevřít</a>}
                  {k.stav === 'rucne' && (
                    <label className="odskrtnout">
                      <input
                        type="checkbox"
                        checked={odskrtnuto}
                        disabled={ukladam.has(k.kod)}
                        onChange={() => void nastav(k.kod, !odskrtnuto)}
                      />{' '}
                      Zkontrolováno
                    </label>
                  )}
                  {z && (
                    <span className="tlumene kdo-odskrtl">
                      {z.jmeno || z.kdo}, {kdy(z.kdy)}
                    </span>
                  )}
                </div>
              </div>
            </li>
          )
        })}
      </ul>
      <UzavreniRoku data={data} setData={setData} />
    </>
  )
}

function TabulkaVykazu({ nadpis, radky, strany }: { nadpis: string; radky: RadekVykazu[]; strany: [string, string][] }) {
  return (
    <>
      <h2>{nadpis}</h2>
      <div className="tabulka-posun">
        <table>
          <thead>
            <tr>
              <th>Řádek</th>
              <th className="cislo">v tis. Kč</th>
              <th className="cislo">přesně</th>
            </tr>
          </thead>
          {strany.map(([strana, nazev]) => {
            const r = radky.filter((x) => x.strana === strana)
            return (
              <tbody key={strana}>
                <tr className="soucet-vykazu">
                  <td>{nazev}</td>
                  <td className="cislo">{r.reduce((a, x) => a + x.tisice, 0)}</td>
                  <td className="cislo">{kc(r.reduce((a, x) => a + x.castka, 0))}</td>
                </tr>
                {r.map((x) => (
                  <tr key={x.radek}>
                    <td>
                      {x.radek} {x.nazev}
                    </td>
                    <td className="cislo">{x.tisice}</td>
                    <td className="cislo">{kc(x.castka)}</td>
                  </tr>
                ))}
              </tbody>
            )
          })}
        </table>
      </div>
    </>
  )
}

function Vykazy({ data }: { data: Data }) {
  return (
    <>
      <p className="tlumene">
        Zkrácený rozsah podle vyhlášky č. 504/2002 Sb., stav k {datum(data.k_datu)} podle toho,
        co je zatím zaúčtované. Přeplatky vlastníků jsou mezi závazky, ne odečtené od dluhů
        ostatních. Výkaz zisku a ztráty se do sbírky listin ukládat nemusí.
      </p>
      <TabulkaVykazu
        nadpis="Rozvaha"
        radky={data.rozvaha}
        strany={[
          ['aktiva', 'Aktiva celkem'],
          ['pasiva', 'Pasiva celkem'],
        ]}
      />
      <TabulkaVykazu
        nadpis="Výkaz zisku a ztráty"
        radky={data.vysledovka}
        strany={[
          ['naklady', 'Náklady celkem'],
          ['vynosy', 'Výnosy celkem'],
        ]}
      />
      <p>
        Výsledek hospodaření: <strong>{kc(data.vysledek)}</strong>
        {data.vysledek !== 0 && (
          <span className="tlumene">
            {' '}
            U zálohových příspěvků po vyúčtování správy obvykle vyjde nula; rozdíl dělají
            náklady, které do vyúčtování nepatří.
          </span>
        )}
      </p>
    </>
  )
}

/** Zůstatek ve směru, jaký účet obvykle má: pohledávky a peníze kladně, závazky a zálohy kladně. */
function smer(s: Soupis) {
  return s.zustatek < 0 ? -1 : 1
}

function Inventura({ data, tisk }: { data: Data; tisk: () => void }) {
  const [otevreny, setOtevreny] = useState<string | null>(null)
  return (
    <>
      <p className="tlumene">
        Inventurou se ověřuje, že stav v účetnictví odpovídá skutečnosti: zůstatek na výpisu,
        dluhy a přeplatky vlastníků, nezaplacené faktury. Bez inventury je účetnictví
        neprůkazné. Inventura se dělá nejdřív 4 měsíce před a nejpozději 2 měsíce po konci roku
        a soupisy se uchovávají 5 let.
      </p>
      <div className="radek">
        <button onClick={tisk}>Vytisknout inventurní soupisy</button>
      </div>
      <div className="tabulka-posun">
        <table className="jednotky">
          <thead>
            <tr>
              <th>Účet</th>
              <th>Co to je</th>
              <th className="cislo">Stav k {datum(data.k_datu)}</th>
            </tr>
          </thead>
          <tbody>
            {data.soupisy.map((s) => (
              <Fragment key={s.ucet}>
                <tr
                  className={s.polozky.length ? 'klikaci' : undefined}
                  onClick={() => s.polozky.length && setOtevreny(otevreny === s.ucet ? null : s.ucet)}
                  aria-expanded={s.polozky.length ? otevreny === s.ucet : undefined}
                >
                  <td>{s.ucet}</td>
                  <td>
                    {s.nazev}
                    {s.polozky.length > 0 && <span className="tlumene"> · rozpis</span>}
                  </td>
                  <td className="cislo">{kc(Math.abs(s.zustatek))}</td>
                </tr>
                {otevreny === s.ucet && (
                  <tr className="rozpis">
                    <td colSpan={3}>
                      <ul>
                        {s.polozky.map((p, i) => (
                          <li key={i}>
                            <span>{p.popis}</span>
                            <span>{kc(p.castka * smer(s))}</span>
                          </li>
                        ))}
                      </ul>
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}

function TiskSoupisu({ data, zpet }: { data: Data; zpet: () => void }) {
  return (
    <>
      <div className="radek neni-v-tisku">
        <button className="vedlejsi" onClick={zpet}>
          Zpět na uzávěrku
        </button>
        <button onClick={() => window.print()}>Vytisknout</button>
      </div>
      <p className="tlumene neni-v-tisku">
        Každý účet je na samostatné stránce. Skutečný stav, okamžik zahájení a ukončení inventury
        a podpisy doplňte ručně.
      </p>
      {data.soupisy.map((s) => (
        <article key={s.ucet} className="upominka soupis">
          <p>
            <strong>{data.svj}</strong>
            {data.ico && <>, IČ {data.ico}</>}
          </p>
          <h2>
            Inventurní soupis: {s.ucet} {s.nazev}
          </h2>
          <dl className="udaje-soupisu">
            <dt>Rozvahový den</dt>
            <dd>{datum(data.k_datu)} (periodická inventarizace)</dd>
            <dt>Ocenění</dt>
            <dd>v Kč, jmenovitou hodnotou podle účetnictví</dd>
            <dt>Způsob zjištění skutečného stavu</dt>
            <dd>{s.zpusob}</dd>
          </dl>
          {s.polozky.length > 0 && (
            <table className="polozky-dluhu">
              <thead>
                <tr>
                  <th>Položka</th>
                  <th className="cislo">Stav v účetnictví</th>
                  <th className="cislo">Skutečný stav</th>
                </tr>
              </thead>
              <tbody>
                {s.polozky.map((p, i) => (
                  <tr key={i}>
                    <td>{p.popis}</td>
                    <td className="cislo">{kc(p.castka * smer(s))}</td>
                    <td className="cislo vyplnit"></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <table className="polozky-dluhu">
            <tbody>
              <tr>
                <td>Stav v účetnictví celkem</td>
                <td className="cislo">{kc(Math.abs(s.zustatek))}</td>
              </tr>
              <tr>
                <td>Skutečný stav celkem</td>
                <td className="cislo vyplnit"></td>
              </tr>
              <tr>
                <td>Inventarizační rozdíl (manko / přebytek)</td>
                <td className="cislo vyplnit"></td>
              </tr>
            </tbody>
          </table>
          <dl className="udaje-soupisu">
            <dt>Inventura zahájena</dt>
            <dd className="vyplnit">dne ………………… v …… hod.</dd>
            <dt>Inventura ukončena</dt>
            <dd className="vyplnit">dne ………………… v …… hod.</dd>
          </dl>
          <div className="podpisy">
            <p>
              Skutečný stav zjistil(a)
              <br />
              <span className="podpis">jméno a podpis</span>
            </p>
            <p>
              Za inventarizaci odpovídá
              <br />
              <span className="podpis">jméno a podpis</span>
            </p>
          </div>
        </article>
      ))}
    </>
  )
}

function Dan({ data }: { data: Data }) {
  const { musi_podat, vynosy } = data.dan
  return (
    <>
      <p className={musi_podat ? 'upozorneni' : 'uspech'}>
        {musi_podat
          ? `Za rok ${data.rok} má SVJ výnosy, které se daní nebo o kterých aplikace neví, jak se daní. Daňové přiznání k dani z příjmů právnických osob nejspíš podat musí; ověřte to s účetní.`
          : vynosy.length === 0
            ? `Za rok ${data.rok} zatím nejsou žádné výnosy, které by se danily. Pokud to tak zůstane, daňové přiznání SVJ podávat nemusí.`
            : `Za rok ${data.rok} má SVJ jen výnosy, které se nedaní, nebo úroky, ze kterých daň srazila banka. Daňové přiznání podávat nemusí (§ 38mb písm. b) zákona o daních z příjmů).`}
      </p>
      <p className="tlumene">
        Příspěvky vlastníků, úhrady za služby, dotace a pojistné plnění z pojištění domu nejsou
        předmětem daně. Daní se hlavně úroky z prodlení a pokuty, které vlastníci zaplatí, příjmy
        z prodeje majetku SVJ a čerpání fondů ze zisku. Kdo začne mít takové příjmy, musí se
        k dani zaregistrovat.
      </p>
      {vynosy.length === 0 ? (
        <p className="tlumene">Za rok {data.rok} zatím nejsou zaúčtované žádné výnosy.</p>
      ) : (
        <div className="tabulka-posun">
          <table>
            <thead>
              <tr>
                <th>Výnos</th>
                <th className="cislo">Částka</th>
                <th>Daň</th>
              </tr>
            </thead>
            <tbody>
              {vynosy.map((v) => (
                <tr key={v.popis}>
                  <td>
                    {v.popis}
                    {v.poznamka && (
                      <>
                        <br />
                        <span className="tlumene">{v.poznamka}</span>
                      </>
                    )}
                  </td>
                  <td className="cislo">{kc(v.castka)}</td>
                  <td className={`zdaneni-${v.zdaneni}`}>{ZDANENI[v.zdaneni]}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}

function TextPrilohy({ text }: { text: string }) {
  const casti = text.split('[doplňte]')
  return (
    <>
      {casti.map((c, i) => (
        <span key={i}>
          {c}
          {i < casti.length - 1 && <mark className="doplnit">[doplňte]</mark>}
        </span>
      ))}
    </>
  )
}

function ObsahPrilohy({ data }: { data: Data }) {
  return (
    <>
      {data.priloha.map((o) => (
        <section key={o.nadpis}>
          <h3>{o.nadpis}</h3>
          {o.odstavce.map((t, i) => (
            <p key={i}>
              <TextPrilohy text={t} />
            </p>
          ))}
        </section>
      ))}
    </>
  )
}

function Priloha({ data, tisk }: { data: Data; tisk: () => void }) {
  return (
    <>
      <p className="tlumene">
        Návrh přílohy k účetní závěrce sestavený z účetnictví. Co aplikace neví, je označené
        [doplňte]. Přílohu i rozvahu je potřeba uložit do sbírky listin.
      </p>
      <div className="radek">
        <button onClick={tisk}>Vytisknout návrh přílohy</button>
      </div>
      <div className="karta-prilohy">
        <ObsahPrilohy data={data} />
      </div>
    </>
  )
}

function TiskPrilohy({ data, zpet }: { data: Data; zpet: () => void }) {
  return (
    <>
      <div className="radek neni-v-tisku">
        <button className="vedlejsi" onClick={zpet}>
          Zpět na uzávěrku
        </button>
        <button onClick={() => window.print()}>Vytisknout</button>
      </div>
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
        <h2>Příloha k účetní závěrce k {datum(data.k_datu)}</h2>
        <ObsahPrilohy data={data} />
        <p>Sestaveno dne ………………… Podpis statutárního orgánu ……………………………</p>
      </article>
    </>
  )
}

/** Další rok jde založit už v prosinci, aby šly v lednu účtovat předpisy a výpisy. */
function DalsiRok({ data, setData }: { data: Data; setData: (d: Data) => void }) {
  const [pracuji, setPracuji] = useState(false)
  const [chyba, setChyba] = useState<string | null>(null)
  if (data.uzavreni.stav !== 'otevrene' || data.uzavreni.dalsi !== null) return null
  if (new Date(data.dnes) < new Date(data.rok, 11, 1)) return null

  async function zacit() {
    setPracuji(true)
    setChyba(null)
    try {
      setData(await api<Data>(`/api/uzaverka/${data.rok}/dalsi-rok`, { method: 'POST' }))
    } catch (e) {
      setChyba((e as Error).message)
    } finally {
      setPracuji(false)
    }
  }

  return (
    <div className="upozorneni">
      <p>
        Rok {data.rok + 1} v aplikaci zatím není, takže do něj nejde zaúčtovat lednový předpis
        ani výpisy. Začněte ho, uzávěrka roku {data.rok} může počkat. Zůstatky se do nového roku
        převedou, až rok {data.rok} uzavřete.
      </p>
      <div className="radek">
        <button onClick={zacit} disabled={pracuji}>
          {pracuji ? 'Zakládám…' : `Začít účtovat rok ${data.rok + 1}`}
        </button>
        {chyba && <span className="chyba">{chyba}</span>}
      </div>
    </div>
  )
}

function UzavreniRoku({ data, setData }: { data: Data; setData: (d: Data) => void }) {
  const u = data.uzavreni
  const [pracuji, setPracuji] = useState(false)
  const [chyba, setChyba] = useState<string | null>(null)
  const [otevirani, setOtevirani] = useState(false)
  const [duvod, setDuvod] = useState('')
  if (u.stav === null) return null

  async function proved(cesta: string, json?: object) {
    setPracuji(true)
    setChyba(null)
    try {
      setData(await api<Data>(`/api/uzaverka/${data.rok}/${cesta}`, { method: 'POST', json }))
      setOtevirani(false)
      setDuvod('')
    } catch (e) {
      setChyba((e as Error).message)
    } finally {
      setPracuji(false)
    }
  }

  async function uzavrit() {
    const ok = await potvrdit({
      nadpis: `Uzavřít rok ${data.rok}?`,
      text:
        `Aplikace zaúčtuje uzávěrkové zápisy k 31. 12. ${data.rok} a převede zůstatky do roku ${data.rok + 1}, ` +
        'dluhy vlastníků i se splatností. Do uzavřeného roku už nepůjde nic zaúčtovat. ' +
        'Než shromáždění závěrku schválí, jde rok znovu otevřít.',
      ano: 'Uzavřít rok',
    })
    if (ok) await proved('uzavrit')
  }

  function otevrit(e: FormEvent) {
    e.preventDefault()
    void proved('znovu-otevrit', { duvod })
  }

  return (
    <section className="uzavreni-roku">
      <h2>Uzavření roku</h2>
      {u.stav === 'uzavrene' ? (
        <>
          <p>
            Rok {data.rok} je uzavřený. Uzávěrkové zápisy a počáteční stavy roku {data.rok + 1}{' '}
            jsou v <a href="#denik">Deníku</a> pod čísly {u.zapisy.join(', ')}.
          </p>
          <p className="tlumene">
            Pokud se před schválením závěrky najde chyba, rok jde znovu otevřít. Uzávěrkové zápisy
            i počáteční stavy roku {data.rok + 1} se stornují, po opravě rok uzavřete znovu. Po
            schválení závěrky se chyby opravují v běžném roce.
          </p>
          {u.dalsi === 'otevrene' &&
            (otevirani ? (
              <form className="vlastnictvi-formular" onSubmit={otevrit}>
                <div className="faktura-formular">
                  <label className="cely-radek">
                    Proč rok znovu otevíráte
                    <textarea
                      value={duvod}
                      onChange={(e) => setDuvod(e.target.value)}
                      rows={2}
                      maxLength={500}
                      placeholder="třeba Dodatečně došlá faktura za prosinec"
                      required
                    />
                  </label>
                </div>
                <div className="radek">
                  <button type="submit" disabled={pracuji || !duvod.trim()}>
                    {pracuji ? 'Otevírám…' : `Znovu otevřít rok ${data.rok}`}
                  </button>
                  <button type="button" className="vedlejsi" onClick={() => setOtevirani(false)}>
                    Zrušit
                  </button>
                </div>
              </form>
            ) : (
              <div className="radek">
                <button className="vedlejsi" onClick={() => setOtevirani(true)}>
                  Znovu otevřít rok
                </button>
              </div>
            ))}
        </>
      ) : (
        <>
          <p>
            Až bude všechno výše hotové nebo odškrtnuté, aplikace uzavře účty k 31. 12. {data.rok}{' '}
            a převede zůstatky do roku {data.rok + 1}: peníze na účtech, nezaplacené faktury
            a dluhy vlastníků po jednotlivých položkách i se splatností.
          </p>
          {u.proc_nejde.length > 0 && (
            <div className="tlumene">
              <p>Zatím to nejde:</p>
              <ul>
                {u.proc_nejde.map((d) => (
                  <li key={d}>{d}</li>
                ))}
              </ul>
            </div>
          )}
          <div className="radek">
            <button onClick={uzavrit} disabled={pracuji || u.proc_nejde.length > 0}>
              {pracuji ? 'Uzavírám…' : `Uzavřít rok ${data.rok}`}
            </button>
          </div>
        </>
      )}
      {chyba && <p className="chyba">{chyba}</p>}
    </section>
  )
}
