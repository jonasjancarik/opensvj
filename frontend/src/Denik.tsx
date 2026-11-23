import { useEffect, useState } from 'react'
import { api } from './auth'
import { Chyba, Nacitani } from './ui'
import { kc } from './penize'
import { InterniDoklad } from './InterniDoklad'

type Radek = {
  strana: 'md' | 'd'
  ucet: string
  nazev_uctu: string
  castka: number
  jednotka: string | null
  sluzba: string | null
  protistrana: string | null
  popis: string | null
}
type Zapis = {
  id: number
  cislo: string
  datum: string
  doklad: string
  operace: string
  nazev_operace: string
  popis: string
  zauctoval: string
  castka: number
  radky: Radek[]
  stornovan_zapisem: string | null
  stornuje_zapis: string | null
}
type Data = { rok: number; zapisy: Zapis[] }

const datum = (d: string) => new Date(d).toLocaleDateString('cs-CZ')

export function Denik() {
  const rok = new Date().getFullYear()
  const [data, setData] = useState<Data | null>(null)
  const [chyba, setChyba] = useState<string | null>(null)
  const [otevreny, setOtevreny] = useState<number | null>(null)
  const [zprava, setZprava] = useState<string | null>(null)

  useEffect(() => {
    api<Data>(`/api/denik/${rok}`).then(setData).catch((e) => setChyba(e.message))
  }, [rok])

  if (!data) return chyba ? <Chyba text={chyba} /> : <Nacitani />

  return (
    <>
      <h1>Deník {rok}</h1>
      <p className="tlumene">
        Všechny zaúčtované zápisy roku od nejnovějšího. Zaúčtovaný zápis nejde změnit ani smazat;
        chybu opraví storno, které zápis vyruší. Potom jde stejnou věc (předpis, platbu, počáteční
        stavy) zaúčtovat znovu.
      </p>
      <InterniDoklad
        zauctovano={(cislo, r) => {
          setZprava(
            r === rok
              ? `Zaúčtováno jako zápis ${cislo}.`
              : `Zaúčtováno jako zápis ${cislo} v deníku roku ${r}.`,
          )
          if (r === rok) api<Data>(`/api/denik/${rok}`).then(setData)
        }}
      />
      {zprava && <p className="uspech">{zprava}</p>}
      {data.zapisy.length === 0 && <p>Za rok {rok} zatím není nic zaúčtováno.</p>}
      <ul className="zapisy">
        {data.zapisy.map((z) => (
          <li
            key={z.id}
            className={`zapis${z.stornovan_zapisem || z.stornuje_zapis ? ' zapis-zruseny' : ''}`}
          >
            <button
              className="zapis-hlavicka"
              aria-expanded={otevreny === z.id}
              onClick={() => setOtevreny(otevreny === z.id ? null : z.id)}
            >
              <span className="zapis-cislo">{z.cislo}</span>
              <span className="zapis-datum">{datum(z.datum)}</span>
              <span className="zapis-nazev">
                {z.nazev_operace}
                {z.stornovan_zapisem && (
                  <span className="stitek">stornováno zápisem {z.stornovan_zapisem}</span>
                )}
                {z.stornuje_zapis && (
                  <span className="stitek">storno zápisu {z.stornuje_zapis}</span>
                )}
              </span>
              <span className="cislo">{kc(z.castka)}</span>
            </button>
            {otevreny === z.id && (
              <Detail
                zapis={z}
                stornovano={(d) => {
                  setData(d)
                  setOtevreny(null)
                }}
              />
            )}
          </li>
        ))}
      </ul>
    </>
  )
}

function Detail({ zapis: z, stornovano }: { zapis: Zapis; stornovano: (d: Data) => void }) {
  const [duvod, setDuvod] = useState('')
  const [formular, setFormular] = useState(false)
  const [pracuji, setPracuji] = useState(false)
  const [chyba, setChyba] = useState<string | null>(null)
  const lzeStornovat = !z.stornovan_zapisem && !z.stornuje_zapis

  async function stornovat() {
    setPracuji(true)
    setChyba(null)
    try {
      stornovano(
        await api<Data>(`/api/denik/zapisy/${z.id}/storno`, {
          method: 'POST',
          json: { duvod },
        }),
      )
    } catch (e) {
      setChyba((e as Error).message)
      setPracuji(false)
    }
  }

  return (
    <div className="zapis-detail">
      <p>{z.popis}</p>
      <p className="tlumene">
        Doklad {z.doklad} · zaúčtoval {z.zauctoval}
      </p>
      <div className="tabulka-posun">
        <table>
          <thead>
            <tr>
              <th>Účet</th>
              <th>Podrobnosti</th>
              <th className="cislo">Má dáti</th>
              <th className="cislo">Dal</th>
            </tr>
          </thead>
          <tbody>
            {z.radky.map((r, i) => (
              <tr key={i}>
                <td>
                  {r.ucet} <span className="tlumene">{r.nazev_uctu !== r.ucet && r.nazev_uctu}</span>
                </td>
                <td>
                  {[
                    r.jednotka && `jednotka ${r.jednotka}`,
                    r.protistrana,
                    r.popis,
                  ]
                    .filter(Boolean)
                    .join(' · ')}
                </td>
                <td className="cislo">{r.strana === 'md' ? kc(r.castka) : ''}</td>
                <td className="cislo">{r.strana === 'd' ? kc(r.castka) : ''}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {lzeStornovat &&
        (formular ? (
          <div className="storno-formular">
            <label>
              Proč se zápis stornuje
              <textarea
                rows={2}
                maxLength={500}
                value={duvod}
                placeholder="např. předpis spočítaný se špatným počtem osob"
                onChange={(e) => setDuvod(e.target.value)}
              />
            </label>
            <p className="tlumene">
              Vznikne nový zápis, který tenhle vyruší. Důvod a vaše jméno se uloží k zápisu.
            </p>
            <div className="radek">
              <button disabled={pracuji || !duvod.trim()} onClick={stornovat}>
                {pracuji ? 'Stornuji…' : `Stornovat zápis ${z.cislo}`}
              </button>
              <button className="vedlejsi" onClick={() => setFormular(false)}>
                Zpět
              </button>
            </div>
            {chyba && <p className="chyba">{chyba}</p>}
          </div>
        ) : (
          <button className="vedlejsi" onClick={() => setFormular(true)}>
            Stornovat…
          </button>
        ))}
    </div>
  )
}
