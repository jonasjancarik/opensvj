import { useEffect, useState, type FormEvent } from 'react'
import { api } from './auth'
import { Chyba, Nacitani } from './ui'
import { kc, naHalire } from './penize'

type Druh = { id: string; nazev: string; skupina: string }
type Faktura = {
  cislo: string
  dodavatel: string
  ico: string | null
  ucet_dodavatele: string | null
  cislo_dodavatele: string | null
  vs: string | null
  vystaveno: string | null
  duzp: string
  splatnost: string
  castka: number
  uhrazeno: number
  zbyva: number
  stav: 'k_uhrade' | 'castecne' | 'po_splatnosti' | 'uhrazena' | 'stornovana'
  druh: string
  nazev_druhu: string
  popis: string
  rozhodnuti: string | null
  zapis: string
  zadal: string
}
type Data = {
  rok: number
  druhy: Druh[]
  dodavatele: string[]
  faktury: Faktura[]
  k_uhrade: number
}

const STAV: Record<Faktura['stav'], string> = {
  k_uhrade: 'k úhradě',
  castecne: 'zaplacená zčásti',
  po_splatnosti: 'po splatnosti',
  uhrazena: 'zaplacená',
  stornovana: 'stornovaná',
}

const datum = (d: string) => new Date(d).toLocaleDateString('cs-CZ')
const dnes = () => new Date().toISOString().slice(0, 10)

const PRAZDNA = {
  dodavatel: '',
  cislo_dodavatele: '',
  castka: '',
  duzp: dnes(),
  splatnost: '',
  druh: '',
  rozhodnuti: '',
  vs: '',
  ucet_dodavatele: '',
  ico: '',
  popis: '',
}
type Formular = typeof PRAZDNA

export function Faktury() {
  const rok = new Date().getFullYear()
  const [data, setData] = useState<Data | null>(null)
  const [chyba, setChyba] = useState<string | null>(null)

  useEffect(() => {
    api<Data>(`/api/faktury/${rok}`).then(setData).catch((e) => setChyba(e.message))
  }, [rok])

  if (!data) return chyba ? <Chyba text={chyba} /> : <Nacitani />

  const otevrene = data.faktury.filter((f) => f.zbyva > 0 && f.stav !== 'stornovana')

  return (
    <>
      <h1>Přijaté faktury</h1>
      <p className="tlumene">
        {otevrene.length === 0
          ? 'Žádná faktura nečeká na zaplacení.'
          : `Na zaplacení čeká ${otevrene.length === 1 ? '1 faktura' : `${otevrene.length} faktur${otevrene.length < 5 ? 'y' : ''}`} za ${kc(data.k_uhrade)}.`}{' '}
        Faktury se platí z bankovnictví jako obvykle. Při zaúčtování odchozí platby na stránce
        Banka pak vyberete, kterou fakturu platba platí.
      </p>

      <NovaFaktura data={data} poZadani={setData} />

      <h2>Faktury</h2>
      {data.faktury.length === 0 ? (
        <p className="tlumene">Zatím tu žádná faktura není.</p>
      ) : (
        <div className="tabulka-posun">
          <table className="faktury">
            <thead>
              <tr>
                <th>Splatnost</th>
                <th>Dodavatel a za co</th>
                <th className="cislo">Částka</th>
                <th className="cislo">Zbývá zaplatit</th>
                <th>Stav</th>
              </tr>
            </thead>
            <tbody>
              {data.faktury.map((f) => (
                <tr key={f.cislo} className={f.stav === 'stornovana' ? 'zrusena' : undefined}>
                  <td>{datum(f.splatnost)}</td>
                  <td>
                    <strong>{f.dodavatel}</strong>
                    <span className="tlumene">
                      {' · '}
                      {f.nazev_druhu}
                      {f.popis && ` · ${f.popis}`}
                    </span>
                    <br />
                    <span className="tlumene">
                      {[
                        f.cislo_dodavatele && `faktura ${f.cislo_dodavatele}`,
                        f.vs && `VS ${f.vs}`,
                        `doklad FP ${f.cislo}`,
                        `zápis ${f.zapis}`,
                      ]
                        .filter(Boolean)
                        .join(' · ')}
                    </span>
                  </td>
                  <td className="cislo">{kc(f.castka)}</td>
                  <td className="cislo">{f.stav === 'stornovana' ? '' : kc(f.zbyva)}</td>
                  <td className={`stav-faktury stav-${f.stav}`}>{STAV[f.stav]}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}

function NovaFaktura({ data, poZadani }: { data: Data; poZadani: (d: Data) => void }) {
  const [f, setF] = useState<Formular>(PRAZDNA)
  const [pracuji, setPracuji] = useState(false)
  const [chyba, setChyba] = useState<string | null>(null)
  const [hotovo, setHotovo] = useState<string | null>(null)
  const castka = naHalire(f.castka)
  const skupiny = [...new Set(data.druhy.map((d) => d.skupina))]
  const zFonduOprav = f.druh === 'FOND_OPRAV'
  const lzeOdeslat =
    f.dodavatel.trim() && castka !== null && castka > 0 && f.duzp && f.splatnost && f.druh &&
    (!zFonduOprav || f.rozhodnuti.trim())

  const nastav = (pole: keyof Formular) => (e: { target: { value: string } }) =>
    setF((x) => ({ ...x, [pole]: e.target.value }))

  function zmenDodavatele(dodavatel: string) {
    // Známý dodavatel: doplní údaje z jeho poslední faktury, pokud je uživatel ještě nevyplnil.
    const minula = data.faktury.find((x) => x.dodavatel.toLowerCase() === dodavatel.trim().toLowerCase())
    setF((x) => ({
      ...x,
      dodavatel,
      ...(minula && {
        druh: x.druh || minula.druh,
        ico: x.ico || minula.ico || '',
        ucet_dodavatele: x.ucet_dodavatele || minula.ucet_dodavatele || '',
      }),
    }))
  }

  async function odeslat(e: FormEvent) {
    e.preventDefault()
    if (!lzeOdeslat) return
    setPracuji(true)
    setChyba(null)
    setHotovo(null)
    try {
      const nova = await api<Data>('/api/faktury', {
        method: 'POST',
        json: { ...f, castka, rozhodnuti: zFonduOprav ? f.rozhodnuti : null },
      })
      const drive = new Set(data.faktury.map((x) => x.cislo))
      const zadana = nova.faktury.find((x) => !drive.has(x.cislo))
      poZadani(nova)
      setF({ ...PRAZDNA, duzp: f.duzp })
      setHotovo(
        zadana
          ? `Faktura od ${zadana.dodavatel} na ${kc(zadana.castka)} je zaúčtovaná (doklad FP ${zadana.cislo}). Po zaplacení ji vyberte u odchozí platby na stránce Banka.`
          : 'Faktura je zaúčtovaná.',
      )
    } catch (e) {
      setChyba((e as Error).message)
    } finally {
      setPracuji(false)
    }
  }

  return (
    <section className="nahrani">
      <h2>Zadat fakturu</h2>
      <form className="faktura-formular" onSubmit={odeslat}>
        <label>
          Dodavatel
          <input
            list="znami-dodavatele"
            value={f.dodavatel}
            maxLength={128}
            onChange={(e) => zmenDodavatele(e.target.value)}
          />
          <datalist id="znami-dodavatele">
            {data.dodavatele.map((d) => (
              <option key={d} value={d} />
            ))}
          </datalist>
        </label>
        <label>
          Za co faktura je
          <select value={f.druh} onChange={nastav('druh')}>
            <option value="">Vyberte…</option>
            {skupiny.map((s) => (
              <optgroup key={s} label={s}>
                {data.druhy
                  .filter((d) => d.skupina === s)
                  .map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.nazev}
                    </option>
                  ))}
              </optgroup>
            ))}
          </select>
        </label>
        <label>
          Částka celkem s DPH
          <input
            inputMode="decimal"
            value={f.castka}
            placeholder="např. 4 840"
            className={f.castka.trim() && (castka === null || castka <= 0) ? 'neplatne' : undefined}
            onChange={nastav('castka')}
          />
        </label>
        <label>
          Číslo faktury od dodavatele
          <input value={f.cislo_dodavatele} maxLength={40} onChange={nastav('cislo_dodavatele')} />
        </label>
        <label>
          Datum zdanitelného plnění
          <input type="date" value={f.duzp} onChange={nastav('duzp')} />
        </label>
        <label>
          Splatnost
          <input type="date" value={f.splatnost} min={f.duzp} onChange={nastav('splatnost')} />
        </label>
        {zFonduOprav && (
          <label className="cely-radek">
            Kdo opravu schválil
            <input
              value={f.rozhodnuti}
              maxLength={200}
              placeholder="např. shromáždění 4/2026, bod 3"
              onChange={nastav('rozhodnuti')}
            />
          </label>
        )}
        <label>
          <span>Variabilní symbol <span className="tlumene">(nepovinné)</span></span>
          <input inputMode="numeric" value={f.vs} maxLength={10} onChange={nastav('vs')} />
        </label>
        <label>
          <span>Účet dodavatele <span className="tlumene">(nepovinné)</span></span>
          <input
            value={f.ucet_dodavatele}
            maxLength={40}
            placeholder="123456789/0100"
            onChange={nastav('ucet_dodavatele')}
          />
        </label>
        <label>
          <span>IČO dodavatele <span className="tlumene">(nepovinné)</span></span>
          <input inputMode="numeric" value={f.ico} maxLength={10} onChange={nastav('ico')} />
        </label>
        <label className="cely-radek">
          <span>Poznámka <span className="tlumene">(nepovinné)</span></span>
          <input
            value={f.popis}
            maxLength={500}
            placeholder="např. úklid za leden"
            onChange={nastav('popis')}
          />
        </label>
        <p className="tlumene cely-radek">
          Variabilní symbol a účet dodavatele pomůžou aplikaci poznat platbu, kterou fakturu
          zaplatíte. Zadáním fakturu schvalujete a hned se zaúčtuje jako náklad; chybu opraví
          storno na stránce Deník.
        </p>
        <div className="radek cely-radek">
          <button type="submit" disabled={!lzeOdeslat || pracuji}>
            {pracuji ? 'Účtuji…' : 'Zaúčtovat fakturu'}
          </button>
          {chyba && <span className="chyba">{chyba}</span>}
        </div>
        {hotovo && <p className="uspech cely-radek">{hotovo}</p>}
      </form>
    </section>
  )
}
