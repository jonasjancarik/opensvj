import { useEffect, useState, type FormEvent } from 'react'
import { api } from './auth'
import { kc } from './penize'
import { potvrdit } from './potvrdit'
import { Chyba, Nacitani } from './ui'

type Pohyb = { datum: string; doklad: string; popis: string; castka: number; zapis: string }
type Navrh = { zisk_do_fondu: number; zisk_na_ztraty: number; ztrata: number }
type Data = {
  rok: number
  nastaveno: boolean
  nezalohove: boolean
  otevreno: boolean
  vysledek: number
  navrh: Navrh | null
  rozdeleni: { datum: string; popis: string; zapis: string } | null
  pocatek: number
  pohyby: Pohyb[]
  konec: number
  neuhrazena_ztrata: number
}

const datum = (d: string) => new Date(d).toLocaleDateString('cs-CZ')

export function FondZeZisku() {
  const [letos] = useState(() => new Date().getFullYear())
  const [rok, setRok] = useState(letos)
  return (
    <>
      <h1>Fond ze zisku</h1>
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
      <FondRoku key={rok} rok={rok} />
    </>
  )
}

function FondRoku({ rok }: { rok: number }) {
  const [data, setData] = useState<Data | null>(null)
  const [chyba, setChyba] = useState<string | null>(null)

  useEffect(() => {
    api<Data>(`/api/fond-ze-zisku/${rok}`)
      .then(setData)
      .catch((e) => setChyba(e.message))
  }, [rok])

  if (!data) return chyba ? <Chyba text={chyba} /> : <Nacitani />
  if (!data.nastaveno)
    return (
      <p className="upozorneni">
        Společenství nemá v nastavení účet pro fond ze zisku. Pokud ho potřebuje, požádejte správce aplikace o jeho
        doplnění.
      </p>
    )
  return (
    <>
      <p className="tlumene">
        {data.nezalohove
          ? 'Příspěvky na správu jsou nezálohové, takže SVJ obvykle hospodaří se ziskem. Zisk převádí shromáždění do fondu ze zisku a z fondu se pak platí schválené opravy a majetek.'
          : 'Při zálohových příspěvcích vzniká zisk jen výjimečně, třeba z úroků. I ten patří po rozhodnutí shromáždění do fondu ze zisku, ne do fondu oprav.'}{' '}
        Na rozdíl od fondu oprav peníze ve fondu ze zisku nepatří jednotlivým vlastníkům, ale společenství.
      </p>
      <VysledekMinulehoRoku data={data} setData={setData} />
      <StavFondu data={data} />
    </>
  )
}

function VysledekMinulehoRoku({ data, setData }: { data: Data; setData: (d: Data) => void }) {
  const minuly = data.rok - 1
  const letos = new Date().getFullYear() === data.rok
  const [den, setDen] = useState(letos ? new Date().toISOString().slice(0, 10) : '')
  const [rozhodnuti, setRozhodnuti] = useState('')
  const [chyba, setChyba] = useState<string | null>(null)
  const [pracuji, setPracuji] = useState(false)

  const ztrata =
    data.neuhrazena_ztrata > 0 ? (
      <p>
        Neuhrazené ztráty z minulých let: {kc(data.neuhrazena_ztrata)}. Uhradí je zisky dalších let, ještě než půjdou do
        fondu.
      </p>
    ) : null

  if (!data.otevreno)
    return (
      <section>
        <h2>Výsledek roku {minuly}</h2>
        <p>
          Výsledek roku {minuly} se sem dostane s <a href="#pocatecni">počátečními stavy roku {data.rok}</a>, nebo po
          uzavření roku {minuly} na stránce <a href="#uzaverka">Uzávěrka</a>.
        </p>
      </section>
    )

  if (data.rozdeleni)
    return (
      <section>
        <h2>Výsledek roku {minuly}</h2>
        <p>
          Rozděleno {datum(data.rozdeleni.datum)}, zápis <a href="#denik">{data.rozdeleni.zapis}</a>:{' '}
          {data.rozdeleni.popis}
        </p>
        {ztrata}
      </section>
    )

  const n = data.navrh
  if (!n)
    return (
      <section>
        <h2>Výsledek roku {minuly}</h2>
        <p>Rok {minuly} skončil bez zisku i ztráty, není co rozdělovat.</p>
        {ztrata}
      </section>
    )

  const zisk = data.vysledek > 0
  const coSeStane = zisk
    ? [
        n.zisk_na_ztraty > 0 && `${kc(n.zisk_na_ztraty)} uhradí neuhrazené ztráty z minulých let`,
        n.zisk_do_fondu > 0 && `${kc(n.zisk_do_fondu)} půjde do fondu ze zisku`,
      ]
        .filter(Boolean)
        .join(' a ')
    : `ztráta ${kc(n.ztrata)} se převede mezi neuhrazené ztráty a uhradí ji zisky dalších let`

  async function zauctovat(e: FormEvent) {
    e.preventDefault()
    const ano = await potvrdit({
      nadpis: `Zaúčtovat rozdělení výsledku roku ${minuly}?`,
      text: `Podle rozhodnutí shromáždění ${coSeStane}. Opravit to půjde stornem v Deníku.`,
      ano: 'Zaúčtovat',
    })
    if (!ano) return
    setPracuji(true)
    setChyba(null)
    try {
      setData(
        await api<Data>(`/api/fond-ze-zisku/${data.rok}/rozdeleni`, {
          method: 'POST',
          body: JSON.stringify({ datum: den, rozhodnuti }),
        }),
      )
    } catch (e) {
      setChyba((e as Error).message)
    } finally {
      setPracuji(false)
    }
  }

  return (
    <section>
      <h2>Výsledek roku {minuly}</h2>
      <p className="upozorneni">
        {zisk ? `Zisk ${kc(data.vysledek)}` : `Ztráta ${kc(-data.vysledek)}`} z roku {minuly} čeká na rozhodnutí
        shromáždění. Až shromáždění rozhodne, zaúčtujte ho tady: {coSeStane}.
      </p>
      {ztrata}
      <form className="interni-doklad" onSubmit={zauctovat}>
        <div className="interni-doklad-pole">
          <label>
            Kdy shromáždění rozhodlo
            <input type="date" value={den} onChange={(e) => setDen(e.target.value)} required />
          </label>
          <label>
            Rozhodnutí
            <input
              value={rozhodnuti}
              onChange={(e) => setRozhodnuti(e.target.value)}
              placeholder={`třeba shromáždění 15. 4. ${data.rok}, bod 3`}
              maxLength={300}
              required
            />
          </label>
        </div>
        {zisk && (
          <p className="tlumene">
            Shromáždění by mělo zároveň určit, na co se fond ze zisku smí použít. Do fondu oprav se zisk nepřevádí: fond
            oprav jsou zálohy jednotlivých vlastníků, takže by to byla výplata podílu na zisku.
          </p>
        )}
        <div className="radek">
          <button type="submit" disabled={pracuji}>
            Zaúčtovat rozdělení
          </button>
          {chyba && <span className="chyba">{chyba}</span>}
        </div>
      </form>
    </section>
  )
}

function StavFondu({ data }: { data: Data }) {
  return (
    <section>
      <h2>Fond v roce {data.rok}</h2>
      <div className="tabulka-posun">
        <table className="pohyby-fondu">
          <thead>
            <tr>
              <th>Datum</th>
              <th>Doklad</th>
              <th>Co se stalo</th>
              <th className="cislo">Částka</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td colSpan={3}>Na začátku roku</td>
              <td className="cislo">{kc(data.pocatek)}</td>
            </tr>
            {data.pohyby.map((p) => (
              <tr key={p.zapis}>
                <td>{datum(p.datum)}</td>
                <td>
                  <a href="#denik">{p.doklad}</a>
                </td>
                <td>{p.popis}</td>
                <td className="cislo">{(p.castka > 0 ? '+' : '') + kc(p.castka)}</td>
              </tr>
            ))}
            <tr>
              <td colSpan={3}>
                <strong>{new Date().getFullYear() === data.rok ? 'Teď ve fondu' : 'Na konci roku'}</strong>
              </td>
              <td className="cislo">
                <strong>{kc(data.konec)}</strong>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      {data.konec < 0 && (
        <p className="chyba">
          Z fondu se čerpalo o {kc(-data.konec)} víc, než v něm bylo. Část oprav nebo majetku je potřeba hradit z jiného
          zdroje.
        </p>
      )}
      <p className="tlumene">
        Opravu placenou z fondu zadejte na stránce <a href="#faktury">Faktury</a> jako „Oprava hrazená z fondu ze
        zisku“. Majetek z fondu zařadíte na stránce <a href="#majetek">Majetek</a>.
      </p>
    </section>
  )
}
