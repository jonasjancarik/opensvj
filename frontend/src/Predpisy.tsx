import { Fragment, useEffect, useState } from 'react'
import { api } from './auth'
import { potvrdit } from './potvrdit'
import { Chyba, Nacitani } from './ui'
import { kc } from './penize'
import { UpravaPredpisu } from './UpravaPredpisu'

type Skupina = 'fond_oprav' | 'sprava' | 'sluzby'
type Slozka = { kod: string; nazev: string; klic: string; sazba: number | null; skupina: Skupina }

export const SKUPINY: { id: Skupina; nazev: string; popis: string }[] = [
  {
    id: 'fond_oprav',
    nazev: 'Fond oprav',
    popis: 'Dlouhodobé zálohy na opravy a údržbu domu. Nevyúčtovávají se každý rok, převádějí se dál.',
  },
  {
    id: 'sprava',
    nazev: 'Zálohy na správu domu',
    popis:
      'Pojištění, správce, revize a drobné opravy. Vyúčtují se jednou ročně zvlášť od služeb, protože podle zákona nejsou službou.',
  },
  {
    id: 'sluzby',
    nazev: 'Zálohy na služby',
    popis: 'Teplo, voda, elektřina, výtah, úklid a další služby. Vyúčtují se jednou ročně ve vyúčtování služeb.',
  },
]
type Jednotka = {
  oznaceni: string
  plocha: number
  osob: number
  castky: Record<string, number>
  mesicne: number
  pocatek: number
  pocatek_rozpis: { popis: string; castka: number }[]
  predepsano: number
  zaplaceno: number
  saldo: number
}
type Mesic = {
  mesic: number
  nazev: string
  stav: 'zauctovano' | 'lze' | 'pozdeji' | 'bez_predpisu'
  zapis: string | null
  celkem: number
}
type Data = {
  rok: number
  poznamka: string
  splatnost_den: number
  plati_od: string | null
  zdroj: string | null
  slozky: Slozka[]
  jednotky: Jednotka[]
  mesice: Mesic[]
  mesicne_celkem: number
  pocatecni_stavy: boolean
  drivejsi_vlastnici: { jednotka: string; vlastnik: string; popis: string; castka: number }[]
}

const plocha = (setiny: number) =>
  `${(setiny / 100).toLocaleString('cs-CZ', { minimumFractionDigits: 2 })} m²`

function jakSePocita(s: Slozka) {
  const sazba = s.sazba === null ? '' : kc(s.sazba)
  switch (s.klic) {
    case 'plocha':
      return `${sazba} za m² podlahové plochy`
    case 'osoby':
      return `${sazba} za osobu`
    case 'podil':
      return `${sazba} měsíčně za celý dům, rozdělí se podle podílů`
    case 'jednotka':
      return `${sazba} měsíčně za celý dům, každá jednotka stejně`
    default:
      return 'pevná částka, u každé jednotky může být jiná'
  }
}

function procPozdeji(rok: number, mesic: number) {
  const dnes = new Date()
  if (rok > dnes.getFullYear() || (rok === dnes.getFullYear() && mesic > dnes.getMonth() + 1))
    return `Půjde zaúčtovat od 1. ${mesic}.`
  return 'Nejdřív předchozí měsíc'
}

export function Predpisy() {
  const rok = new Date().getFullYear()
  const [data, setData] = useState<Data | null>(null)
  const [chyba, setChyba] = useState<string | null>(null)
  const [pracuji, setPracuji] = useState<number | null>(null)
  const [otevrena, setOtevrena] = useState<string | null>(null)

  const nacti = () =>
    api<Data>(`/api/predpisy/${rok}`)
      .then(setData)
      .catch((e) => setChyba(e.message))
  useEffect(() => {
    nacti()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rok])

  async function zauctuj(m: Mesic) {
    const ano = await potvrdit({
      nadpis: `Zaúčtovat předpis za ${m.nazev} ${rok}?`,
      text:
        `Všem jednotkám vznikne pohledávka, dohromady ${kc(m.celkem)}. ` +
        'Zaúčtovaný předpis půjde opravit jen stornem v Deníku.',
      ano: 'Zaúčtovat',
    })
    if (!ano) return
    setPracuji(m.mesic)
    setChyba(null)
    try {
      setData(await api<Data>(`/api/predpisy/${rok}/${m.mesic}`, { method: 'POST' }))
    } catch (e) {
      setChyba((e as Error).message)
    } finally {
      setPracuji(null)
    }
  }

  if (!data) return chyba ? <Chyba text={chyba} /> : <Nacitani />

  return (
    <>
      <h1>Předpisy a platby vlastníků {rok}</h1>
      {data.poznamka && <p className="upozorneni">{data.poznamka}</p>}
      {data.plati_od ? (
        <p>
          Předpis platí od {new Date(data.plati_od).toLocaleDateString('cs-CZ')}, splatný je do{' '}
          {data.splatnost_den}. dne v měsíci. Celý dům platí měsíčně {kc(data.mesicne_celkem)}.{' '}
          <a href="#oznameni">Oznámení vlastníkům o výši záloh</a>
        </p>
      ) : (
        <p>Pro tento rok zatím není zadaný předpis záloh.</p>
      )}
      {chyba && <p className="chyba">{chyba}</p>}

      <h2>Předpisy po měsících</h2>
      <p className="tlumene">
        Zaúčtováním předpisu vznikne každé jednotce pohledávka za daný měsíc. Měsíce se účtují
        postupně a nejdřív prvního dne měsíce. Platby vlastníků se pak odečítají na stránce Banka.
      </p>
      <ul className="mesice">
        {data.mesice.map((m) => (
          <li key={m.mesic} className={`mesic mesic-${m.stav}`}>
            <strong>{m.nazev}</strong>
            {m.stav === 'zauctovano' ? (
              <span className="uspech">
                Zaúčtováno, zápis <a href="#denik">{m.zapis}</a>
              </span>
            ) : m.stav === 'lze' ? (
              <button disabled={pracuji !== null} onClick={() => zauctuj(m)}>
                {pracuji === m.mesic ? 'Účtuji…' : `Zaúčtovat ${kc(m.celkem)}`}
              </button>
            ) : m.stav === 'pozdeji' ? (
              <span className="tlumene">{procPozdeji(rok, m.mesic)}</span>
            ) : (
              <span className="tlumene">Bez předpisu</span>
            )}
          </li>
        ))}
      </ul>

      <h2>Jednotky</h2>
      {data.pocatecni_stavy ? (
        <p className="tlumene">
          Stav zahrnuje dluhy a přeplatky z minulých let (počáteční stav k 1. 1.), předpisy a
          platby za rok {rok}. Rozpis ukáže klepnutí na jednotku.
        </p>
      ) : (
        <p className="tlumene">
          Chybí počáteční stavy k 1. 1. {rok}, takže dluhy a přeplatky z minulých let se
          neukazují. <a href="#pocatecni">Zadat počáteční stavy</a>. Rozpis složek ukáže klepnutí
          na jednotku.
        </p>
      )}
      <table className="jednotky">
        <thead>
          <tr>
            <th>Jednotka</th>
            <th className="siroke">Plocha</th>
            <th className="siroke">Osob</th>
            <th className="cislo">Měsíčně</th>
            <th className="cislo siroke">Z minulých let</th>
            <th className="cislo siroke">Předepsáno</th>
            <th className="cislo siroke">Zaplaceno</th>
            <th className="cislo">Stav</th>
          </tr>
        </thead>
        <tbody>
          {data.jednotky.map((j) => (
            <Fragment key={j.oznaceni}>
              <tr
                className="klikaci"
                onClick={() => setOtevrena(otevrena === j.oznaceni ? null : j.oznaceni)}
                aria-expanded={otevrena === j.oznaceni}
              >
                <td>{j.oznaceni}</td>
                <td className="siroke">{plocha(j.plocha)}</td>
                <td className="siroke">{j.osob}</td>
                <td className="cislo">{kc(j.mesicne)}</td>
                <td className="cislo siroke">{kc(j.pocatek)}</td>
                <td className="cislo siroke">{kc(j.predepsano)}</td>
                <td className="cislo siroke">{kc(j.zaplaceno)}</td>
                <td className="cislo">
                  <Stav j={j} />
                </td>
              </tr>
              {otevrena === j.oznaceni && (
                <tr className="rozpis">
                  <td colSpan={8}>
                    {j.pocatek_rozpis.length > 0 && (
                      <>
                        <strong>Z minulých let</strong>
                        <ul>
                          {j.pocatek_rozpis.map((d, i) => (
                            <li key={i}>
                              <span>{d.popis || 'bez popisu'}</span>
                              <span>
                                {d.castka > 0 ? kc(d.castka) : `přeplatek ${kc(-d.castka)}`}
                              </span>
                            </li>
                          ))}
                        </ul>
                        <strong>Měsíční předpis</strong>
                      </>
                    )}
                    {SKUPINY.map((sk) => {
                      const polozky = data.slozky.filter(
                        (s) => s.skupina === sk.id && j.castky[s.kod] !== undefined,
                      )
                      if (polozky.length === 0) return null
                      const soucet = polozky.reduce((a, s) => a + j.castky[s.kod], 0)
                      return (
                        <Fragment key={sk.id}>
                          <span className="skupina-predpisu">
                            <span>{sk.nazev}</span>
                            <span>{kc(soucet)}</span>
                          </span>
                          <ul>
                            {polozky.map((s) => (
                              <li key={s.kod}>
                                <span>{s.nazev}</span>
                                <span>{kc(j.castky[s.kod])}</span>
                              </li>
                            ))}
                          </ul>
                        </Fragment>
                      )
                    })}
                  </td>
                </tr>
              )}
            </Fragment>
          ))}
        </tbody>
      </table>

      {data.drivejsi_vlastnici.length > 0 && (
        <>
          <h2>Dřívější vlastníci</h2>
          <p className="tlumene">
            Dluhy a přeplatky lidí, kteří jednotku už prodali. Do stavu současných vlastníků se
            nepočítají.
          </p>
          <table>
            <thead>
              <tr>
                <th>Jednotka</th>
                <th>Vlastník</th>
                <th className="siroke">Za co</th>
                <th className="cislo">Stav</th>
              </tr>
            </thead>
            <tbody>
              {data.drivejsi_vlastnici.map((d, i) => (
                <tr key={i}>
                  <td>{d.jednotka}</td>
                  <td>{d.vlastnik}</td>
                  <td className="siroke">{d.popis}</td>
                  <td className="cislo">
                    {d.castka > 0 ? (
                      <span className="dluh">dluží {kc(d.castka)}</span>
                    ) : (
                      <span>přeplatek {kc(-d.castka)}</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      {data.slozky.length > 0 && (
        <>
          <h2>Jak se předpis počítá</h2>
          <table>
            <thead>
              <tr>
                <th>Složka</th>
                <th>Výpočet</th>
              </tr>
            </thead>
            {SKUPINY.map((sk) => {
              const polozky = data.slozky.filter((s) => s.skupina === sk.id)
              if (polozky.length === 0) return null
              return (
                <tbody key={sk.id}>
                  <tr className="skupina-predpisu">
                    <th colSpan={2}>
                      {sk.nazev}
                      <span className="tlumene"> {sk.popis}</span>
                    </th>
                  </tr>
                  {polozky.map((s) => (
                    <tr key={s.kod}>
                      <td>{s.nazev}</td>
                      <td>{jakSePocita(s)}</td>
                    </tr>
                  ))}
                </tbody>
              )
            })}
          </table>
          {data.zdroj && <p className="tlumene">Podklad: {data.zdroj}.</p>}
        </>
      )}

      <UpravaPredpisu zmeneno={nacti} />
    </>
  )
}

function Stav({ j }: { j: Jednotka }) {
  if (j.pocatek === 0 && j.predepsano === 0 && j.zaplaceno === 0) return <span className="tlumene">–</span>
  if (j.saldo > 0) return <span className="dluh">dluží {kc(j.saldo)}</span>
  if (j.saldo < 0) return <span>přeplatek {kc(-j.saldo)}</span>
  return <span className="uspech">vyrovnáno</span>
}
