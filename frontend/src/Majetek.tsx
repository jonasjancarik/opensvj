import { useEffect, useState, type FormEvent } from 'react'
import { api } from './auth'
import { kc, naHalire } from './penize'
import { potvrdit } from './potvrdit'
import { Chyba, Nacitani } from './ui'

type RokPlanu = { rok: number; odpis: number; opravky: number; zustatek: number }
type Karta = {
  id: number
  nazev: string
  inventarni_cislo: string
  poznamka: string
  druh: string
  druh_nazev: string
  zarazeno: string
  cena: number
  doba_mesicu: number | null
  kryti: string
  kryti_nazev: string
  prevzato_k: string | null
  opravky_prevzate: number
  zapis: string | null
  opravky: number
  zustatkova: number
  odpis_roku: number
  odpis_zauctovan: boolean
  vyrazeno: string | null
  plan: RokPlanu[]
}
type Data = {
  rok: number
  dnes: string
  druhy: Record<string, string>
  kryti: Record<string, string>
  fondy: string[]
  k_zarazeni: Record<string, number>
  odpisy_k_zauctovani: number
  lze_odpisy: string | null
  karty: Karta[]
}

const datum = (d: string) => new Date(d).toLocaleDateString('cs-CZ')

function doba(mesicu: number | null) {
  if (mesicu === null) return 'neodepisuje se'
  if (mesicu % 12 === 0) {
    const roky = mesicu / 12
    return roky === 1 ? '1 rok' : roky < 5 ? `${roky} roky` : `${roky} let`
  }
  return `${mesicu} měsíců`
}

export function Majetek() {
  const [letos] = useState(() => new Date().getFullYear())
  const [rok, setRok] = useState(letos)
  return (
    <>
      <h1>Majetek</h1>
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
      <MajetekRoku key={rok} rok={rok} />
    </>
  )
}

function MajetekRoku({ rok }: { rok: number }) {
  const [data, setData] = useState<Data | null>(null)
  const [chyba, setChyba] = useState<string | null>(null)

  useEffect(() => {
    api<Data>(`/api/majetek/${rok}`)
      .then(setData)
      .catch((e) => setChyba(e.message))
  }, [rok])

  if (!data) return chyba ? <Chyba text={chyba} /> : <Nacitani />
  if (Object.keys(data.druhy).length === 0)
    return (
      <p className="upozorneni">
        Společenství nemá v nastavení účty pro dlouhodobý majetek. Pokud nějaký má, požádejte správce aplikace o jejich
        doplnění.
      </p>
    )
  const ceka = Object.entries(data.k_zarazeni).filter(([, c]) => c > 0)
  return (
    <>
      <p className="tlumene">
        Dlouhodobý majetek je to, co SVJ používá déle než rok a stojí víc než hranice z vnitřního předpisu (třeba
        sekačka nebo počítač pro výbor), a vždy pozemky a jednotky. Fakturu za pořízení zadejte na stránce Faktury jako
        pořízení majetku a tady majetek zařaďte, až se začne používat. Levnější věci jdou rovnou do nákladů a tady se
        neevidují.
      </p>
      {ceka.length > 0 && (
        <p className="upozorneni">
          Z faktur za pořízení čeká na zařazení{' '}
          {ceka.map(([druh, c]) => `${kc(c)} (${data.druhy[druh].toLowerCase()})`).join(', ')}.
        </p>
      )}
      <Odpisy data={data} setData={setData} />
      {data.karty.length === 0 ? (
        <p>V evidenci zatím žádný majetek není.</p>
      ) : (
        data.karty.map((k) => <DetailKarty key={k.id} data={data} karta={k} setData={setData} />)
      )}
      <NovaKarta data={data} setData={setData} />
    </>
  )
}

function Odpisy({ data, setData }: { data: Data; setData: (d: Data) => void }) {
  const [chyba, setChyba] = useState<string | null>(null)
  const [pracuji, setPracuji] = useState(false)
  if (data.odpisy_k_zauctovani === 0) return null

  async function zauctovat() {
    const ano = await potvrdit({
      nadpis: `Zaúčtovat odpisy za rok ${data.rok}?`,
      text:
        `Odpisy majetku ${kc(data.odpisy_k_zauctovani)} se zaúčtují k 31. 12. ${data.rok} podle odpisového plánu. ` +
        'Odpisy majetku placeného z provozních záloh půjdou do vyúčtování správy, proto je zaúčtujte před ním.',
      ano: 'Zaúčtovat',
    })
    if (!ano) return
    setPracuji(true)
    setChyba(null)
    try {
      setData(await api<Data>(`/api/majetek/odpisy/${data.rok}`, { method: 'POST' }))
    } catch (e) {
      setChyba((e as Error).message)
    } finally {
      setPracuji(false)
    }
  }

  return (
    <div className="radek">
      <button onClick={zauctovat} disabled={pracuji || data.lze_odpisy !== null}>
        Zaúčtovat odpisy za rok {data.rok} ({kc(data.odpisy_k_zauctovani)})
      </button>
      {data.lze_odpisy && <span className="tlumene">{data.lze_odpisy}</span>}
      {chyba && <span className="chyba">{chyba}</span>}
    </div>
  )
}

function DetailKarty({ data, karta: k, setData }: { data: Data; karta: Karta; setData: (d: Data) => void }) {
  const [chyba, setChyba] = useState<string | null>(null)
  const [pracuji, setPracuji] = useState(false)

  async function smazat() {
    const ano = await potvrdit({
      nadpis: 'Odebrat majetek z evidence?',
      text: `${k.nazev} zmizí z evidence majetku. V účetnictví se nic nezmění, změna se zapíše do historie změn.`,
      ano: 'Odebrat',
    })
    if (!ano) return
    setPracuji(true)
    setChyba(null)
    try {
      setData(await api<Data>(`/api/majetek/${k.id}?rok=${data.rok}`, { method: 'DELETE' }))
    } catch (e) {
      setChyba((e as Error).message)
      setPracuji(false)
    }
  }

  return (
    <section className="karta-majetku">
      <h2>
        {k.nazev}
        {k.inventarni_cislo && <span className="tlumene"> · {k.inventarni_cislo}</span>}
        {k.vyrazeno && <span className="tlumene"> (vyřazeno {datum(k.vyrazeno)})</span>}
      </h2>
      <dl className="udaje-uveru">
        <dt>Druh</dt>
        <dd>{k.druh_nazev}</dd>
        <dt>Zařazeno do užívání</dt>
        <dd>
          {datum(k.zarazeno)}
          {k.zapis && <span className="tlumene"> (zápis {k.zapis})</span>}
        </dd>
        <dt>Pořizovací cena</dt>
        <dd>{kc(k.cena)}</dd>
        <dt>Odepisuje se</dt>
        <dd>
          {k.doba_mesicu === null
            ? 'neodepisuje se (pozemek)'
            : k.prevzato_k
              ? `${doba(k.doba_mesicu)} od zařazení; co zbývá k ${datum(k.prevzato_k)}, rozloží se do konce té doby`
              : `${doba(k.doba_mesicu)}, od měsíce po zařazení`}
        </dd>
        <dt>Pořízení platí</dt>
        <dd>{k.kryti_nazev}</dd>
        {k.prevzato_k && (
          <>
            <dt>Převzato z počátečních stavů</dt>
            <dd>
              k {datum(k.prevzato_k)}, oprávky {kc(k.opravky_prevzate)}
            </dd>
          </>
        )}
        {k.doba_mesicu !== null && (
          <>
            <dt>Odpis za rok {data.rok}</dt>
            <dd>
              {kc(k.odpis_roku)}
              {k.odpis_roku > 0 && (
                <span className="tlumene">{k.odpis_zauctovan ? ' (zaúčtovaný)' : ' (zatím nezaúčtovaný)'}</span>
              )}
            </dd>
            <dt>Zůstatková cena</dt>
            <dd>
              <strong>{kc(k.zustatkova)}</strong>
            </dd>
          </>
        )}
        {k.poznamka && (
          <>
            <dt>Poznámka</dt>
            <dd>{k.poznamka}</dd>
          </>
        )}
      </dl>
      {k.plan.length > 0 && (
        <details>
          <summary>Odpisový plán</summary>
          <div className="tabulka-posun">
            <table className="plan-odpisu">
              <thead>
                <tr>
                  <th>Rok</th>
                  <th className="cislo">Odpis</th>
                  <th className="cislo">Oprávky na konci roku</th>
                  <th className="cislo">Zůstatková cena</th>
                </tr>
              </thead>
              <tbody>
                {k.plan.map((r) => (
                  <tr key={r.rok}>
                    <td>{r.rok}</td>
                    <td className="cislo">{kc(r.odpis)}</td>
                    <td className="cislo">{kc(r.opravky)}</td>
                    <td className="cislo">{kc(r.zustatek)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="tlumene">
            Odepisuje se rovnoměrně po měsících, po celých korunách. Vyřazením se zbytek ceny odepíše najednou.
          </p>
        </details>
      )}
      {!k.vyrazeno && (
        <>
          <UpravaPopisu data={data} karta={k} setData={setData} />
          {k.doba_mesicu !== null && <Vyrazeni data={data} karta={k} setData={setData} />}
          {k.prevzato_k && k.opravky === k.opravky_prevzate && (
            <div className="radek">
              <button className="vedlejsi" onClick={smazat} disabled={pracuji}>
                Odebrat z evidence
              </button>
              {chyba && <span className="chyba">{chyba}</span>}
            </div>
          )}
        </>
      )}
    </section>
  )
}

function UpravaPopisu({ data, karta: k, setData }: { data: Data; karta: Karta; setData: (d: Data) => void }) {
  const [nazev, setNazev] = useState(k.nazev)
  const [cislo, setCislo] = useState(k.inventarni_cislo)
  const [poznamka, setPoznamka] = useState(k.poznamka)
  const [chyba, setChyba] = useState<string | null>(null)
  const [pracuji, setPracuji] = useState(false)
  const zmeneno = nazev !== k.nazev || cislo !== k.inventarni_cislo || poznamka !== k.poznamka

  async function ulozit(e: FormEvent) {
    e.preventDefault()
    setPracuji(true)
    setChyba(null)
    try {
      setData(
        await api<Data>(`/api/majetek/${k.id}?rok=${data.rok}`, {
          method: 'PUT',
          json: { nazev, inventarni_cislo: cislo, poznamka },
        }),
      )
    } catch (e) {
      setChyba((e as Error).message)
    } finally {
      setPracuji(false)
    }
  }

  return (
    <details>
      <summary>Upravit název a poznámku</summary>
      <form className="interni-doklad" onSubmit={ulozit}>
        <div className="interni-doklad-pole">
          <label>
            Název
            <input value={nazev} onChange={(e) => setNazev(e.target.value)} maxLength={150} />
          </label>
          <label>
            <span>
              Inventární číslo <span className="tlumene">(nepovinné)</span>
            </span>
            <input value={cislo} onChange={(e) => setCislo(e.target.value)} maxLength={32} />
          </label>
          <label>
            <span>
              Poznámka <span className="tlumene">(třeba kde je uložený)</span>
            </span>
            <input value={poznamka} onChange={(e) => setPoznamka(e.target.value)} maxLength={2000} />
          </label>
        </div>
        <p className="tlumene">
          Cenu, datum zařazení ani odpisování tady změnit nejde. Když jsou špatně, stornujte zápis o zařazení na stránce
          Deník a majetek zařaďte znovu.
        </p>
        <div className="radek">
          <button disabled={!zmeneno || !nazev.trim() || pracuji}>Uložit</button>
          {chyba && <span className="chyba">{chyba}</span>}
        </div>
      </form>
    </details>
  )
}

function Vyrazeni({ data, karta: k, setData }: { data: Data; karta: Karta; setData: (d: Data) => void }) {
  const [den, setDen] = useState(data.dnes)
  const [duvod, setDuvod] = useState('')
  const [chyba, setChyba] = useState<string | null>(null)
  const [pracuji, setPracuji] = useState(false)

  async function vyradit(e: FormEvent) {
    e.preventDefault()
    const ano = await potvrdit({
      nadpis: `Vyřadit z užívání „${k.nazev}“?`,
      text:
        'Zbytek ceny, který ještě není odepsaný, se odepíše najednou a majetek se odúčtuje. ' +
        'Peníze z případného prodeje zaúčtujte zvlášť u platby v Bance.',
      ano: 'Vyřadit',
    })
    if (!ano) return
    setPracuji(true)
    setChyba(null)
    try {
      setData(
        await api<Data>(`/api/majetek/${k.id}/vyrazeni?rok=${data.rok}`, {
          method: 'POST',
          json: { datum: den, duvod },
        }),
      )
    } catch (e) {
      setChyba((e as Error).message)
    } finally {
      setPracuji(false)
    }
  }

  return (
    <details>
      <summary>Vyřadit (prodej, zničení, ztráta)</summary>
      <form className="interni-doklad" onSubmit={vyradit}>
        <div className="interni-doklad-pole">
          <label>
            Den vyřazení
            <input type="date" value={den} onChange={(e) => setDen(e.target.value)} />
          </label>
          <label>
            Proč
            <input
              value={duvod}
              onChange={(e) => setDuvod(e.target.value)}
              maxLength={300}
              placeholder="třeba rozbitá, neopravitelná"
            />
          </label>
        </div>
        <div className="radek">
          <button disabled={!den || !duvod.trim() || pracuji}>Vyřadit</button>
          {chyba && <span className="chyba">{chyba}</span>}
        </div>
      </form>
    </details>
  )
}

function NovaKarta({ data, setData }: { data: Data; setData: (d: Data) => void }) {
  const druhy = Object.keys(data.druhy)
  const [druh, setDruh] = useState(druhy[0])
  const [nazev, setNazev] = useState('')
  const [cislo, setCislo] = useState('')
  const [zarazeno, setZarazeno] = useState(data.dnes)
  const [cena, setCena] = useState('')
  const [roku, setRoku] = useState('')
  const [kryti, setKryti] = useState(data.fondy[0] ?? Object.keys(data.kryti)[0])
  const [prevzit, setPrevzit] = useState(false)
  const [opravky, setOpravky] = useState('')
  const [chyba, setChyba] = useState<string | null>(null)
  const [hotovo, setHotovo] = useState<string | null>(null)
  const [pracuji, setPracuji] = useState(false)

  const pozemek = druh === 'pozemek'
  const halire = naHalire(cena.trim())
  const halireOpravek = opravky.trim() ? naHalire(opravky.trim()) : 0
  const let_ = Number(roku.trim().replace(',', '.'))
  const mesicu = pozemek || !roku.trim() || !Number.isFinite(let_) ? null : Math.round(let_ * 12)
  const volne = data.k_zarazeni[druh] ?? 0
  const lze =
    !!nazev.trim() &&
    !!zarazeno &&
    halire !== null &&
    halire > 0 &&
    (pozemek || (mesicu !== null && mesicu >= 1)) &&
    (!prevzit || (halireOpravek !== null && halireOpravek <= halire))
  const rocne = !pozemek && !prevzit && halire && mesicu ? Math.round((halire * 12) / mesicu / 100) * 100 : null

  async function zaradit(e: FormEvent) {
    e.preventDefault()
    if (!lze) return
    const ano = await potvrdit({
      nadpis: prevzit ? 'Převzít majetek do evidence?' : 'Zařadit majetek do užívání?',
      text: prevzit
        ? `${nazev} se doplní do evidence k 1. 1. ${data.rok}. V účetnictví se nic nezaúčtuje: majetek už má být v počátečních stavech.`
        : `${kc(halire!)} se převede z pořizování na majetek` +
          (data.fondy.includes(kryti) ? ` a pořízení se uhradí z: ${data.kryti[kryti]}` : '') +
          '. Opravit to půjde stornem zápisu o zařazení na stránce Deník, dokud nejsou zaúčtované odpisy.',
      ano: prevzit ? 'Převzít' : 'Zařadit',
    })
    if (!ano) return
    setPracuji(true)
    setChyba(null)
    setHotovo(null)
    try {
      setData(
        await api<Data>(`/api/majetek?rok=${data.rok}`, {
          method: 'POST',
          json: {
            nazev,
            inventarni_cislo: cislo,
            druh,
            zarazeno,
            cena: halire,
            doba_mesicu: mesicu,
            kryti,
            prevzato_k: prevzit ? `${data.rok}-01-01` : null,
            opravky_prevzate: prevzit ? halireOpravek : 0,
          },
        }),
      )
      setHotovo(`${nazev} je v evidenci majetku.`)
      setNazev('')
      setCislo('')
      setCena('')
      setOpravky('')
    } catch (e) {
      setChyba((e as Error).message)
    } finally {
      setPracuji(false)
    }
  }

  return (
    <form className="interni-doklad" onSubmit={zaradit}>
      <h2>Zařadit majetek</h2>
      <label className="zaskrtavatko">
        <input type="checkbox" checked={prevzit} onChange={(e) => setPrevzit(e.target.checked)} /> Majetek SVJ mělo už
        před 1. 1. {data.rok} a je v počátečních stavech
      </label>
      <div className="interni-doklad-pole">
        <label>
          Co
          <input
            value={nazev}
            onChange={(e) => setNazev(e.target.value)}
            maxLength={150}
            placeholder="třeba robotická sekačka"
          />
        </label>
        <label>
          Druh
          <select value={druh} onChange={(e) => setDruh(e.target.value)}>
            {druhy.map((d) => (
              <option key={d} value={d}>
                {data.druhy[d]}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>
            Inventární číslo <span className="tlumene">(nepovinné)</span>
          </span>
          <input value={cislo} onChange={(e) => setCislo(e.target.value)} maxLength={32} />
        </label>
        <label>
          Zařazeno do užívání
          <input type="date" value={zarazeno} onChange={(e) => setZarazeno(e.target.value)} />
        </label>
        <label>
          Pořizovací cena
          <input value={cena} onChange={(e) => setCena(e.target.value)} inputMode="decimal" />
          {!prevzit && (
            <span className="tlumene">
              {volne > 0 ? `Z faktur za pořízení čeká ${kc(volne)}.` : 'Z faktur za pořízení zatím nic nečeká.'}
            </span>
          )}
        </label>
        {!pozemek && (
          <label>
            Odepisovat (let)
            <input
              value={roku}
              onChange={(e) => setRoku(e.target.value)}
              inputMode="decimal"
              placeholder="podle odpisového plánu SVJ"
            />
          </label>
        )}
        <label>
          Pořízení platí
          <select value={kryti} onChange={(e) => setKryti(e.target.value)}>
            {Object.entries(data.kryti).map(([k, n]) => (
              <option key={k} value={k}>
                {n.charAt(0).toUpperCase() + n.slice(1)}
              </option>
            ))}
          </select>
        </label>
        {prevzit && !pozemek && (
          <label>
            Oprávky k 1. 1. {data.rok}
            <input value={opravky} onChange={(e) => setOpravky(e.target.value)} inputMode="decimal" />
          </label>
        )}
      </div>
      <p className="tlumene">
        {data.fondy.includes(kryti)
          ? 'Vlastníci zaplatí majetek najednou z fondu, odpisy je pak už znovu nezatíží.'
          : 'Vlastníci zaplatí majetek postupně: odpisy půjdou do vyúčtování záloh na správu podle klíče položky.'}
        {rocne !== null && ` Ročně se odepíše asi ${kc(rocne)}.`}
      </p>
      <div className="radek">
        <button disabled={!lze || pracuji}>{prevzit ? 'Převzít do evidence' : 'Zařadit'}</button>
        {chyba && <span className="chyba">{chyba}</span>}
        {hotovo && <span className="tlumene">{hotovo}</span>}
      </div>
    </form>
  )
}
