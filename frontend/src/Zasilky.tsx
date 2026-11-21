import { type FormEvent, useEffect, useState } from 'react'
import { api, ziskejToken } from './auth'
import { datum, type Zasilka } from './Rozeslat'
import { Chyba, Nacitani } from './ui'

type Prehled = { odesilani_nastaveno: boolean; zasilky: Zasilka[] }
type Filtr = 'ceka' | 'vse'

const dnes = () => new Date().toLocaleDateString('sv-SE')

function Stav({ z }: { z: Zasilka }) {
  if (z.stav === 'dorucena')
    return (
      <span className="uspech" title={z.doruceni_zdroj}>
        Doručeno {datum(z.doruceno!)}
        <div className="tlumene">{z.doruceni_zdroj}</div>
      </span>
    )
  if (z.stav === 'nedorucena')
    return (
      <span className="chyba">
        Nedoručeno
        <div className="tlumene">{z.chyba}</div>
      </span>
    )
  if (z.stav === 'pripravena')
    return <span className="tlumene">{z.kanal === 'posta' ? 'Čeká na vytištění a odeslání' : 'Neodesláno'}</span>
  return (
    <span>
      Odesláno {datum(z.odeslano!)}
      {z.otevreno && <div className="tlumene">Odkaz otevřen {datum(z.otevreno)}, převzetí zatím nepotvrzeno</div>}
    </span>
  )
}

async function otevriDokument(id: number) {
  const okno = window.open('', '_blank')
  const r = await fetch(`/api/zasilky/dokument/${id}`, { headers: { Authorization: `Bearer ${await ziskejToken()}` } })
  const url = URL.createObjectURL(new Blob([await r.text()], { type: 'text/html' }))
  if (okno) okno.location.href = url
}

export function Zasilky() {
  const [data, setData] = useState<Prehled | null>(null)
  const [chyba, setChyba] = useState<string | null>(null)
  const [filtr, setFiltr] = useState<Filtr>('ceka')
  const [doruceni, setDoruceni] = useState<Zasilka | null>(null)

  const nacti = () =>
    api<Prehled>('/api/zasilky')
      .then(setData)
      .catch((e) => setChyba(e.message))
  useEffect(() => {
    nacti()
  }, [])

  if (!data) return chyba ? <Chyba text={chyba} /> : <Nacitani />

  const vyber = data.zasilky.filter((z) => filtr === 'vse' || z.stav !== 'dorucena')
  const dokumenty = new Map<string, Zasilka[]>()
  for (const z of vyber) {
    const k = `${z.klic}|${z.nazev}`
    dokumenty.set(k, [...(dokumenty.get(k) ?? []), z])
  }

  async function odeslanoDnes(z: Zasilka) {
    try {
      await api('/api/zasilky/odeslano', { method: 'POST', json: { ids: [z.id], datum: dnes() } })
      nacti()
    } catch (e) {
      setChyba((e as Error).message)
    }
  }

  return (
    <>
      <h1>Zásilky vlastníkům</h1>
      <p className="tlumene">
        Co komu odešlo a kdy to došlo. Od doručení se počítají lhůty, třeba pro námitky a vyrovnání u vyúčtování služeb.
        E-mail se počítá jako doručený, když vlastník převzetí potvrdí odkazem; dopis, když zapíšete datum z dodejky
        nebo předání.
      </p>
      {!data.odesilani_nastaveno && (
        <p className="upozorneni">
          Odesílání e-mailů zatím není nastavené, dokumenty jde jen vytisknout. Nastavení doplní správce aplikace.
        </p>
      )}
      <div className="zalozky" role="tablist">
        <button className={filtr === 'ceka' ? 'aktivni' : undefined} onClick={() => setFiltr('ceka')}>
          Čeká na doručení
        </button>
        <button className={filtr === 'vse' ? 'aktivni' : undefined} onClick={() => setFiltr('vse')}>
          Všechny
        </button>
      </div>
      {chyba && <p className="chyba">{chyba}</p>}
      {doruceni && (
        <ZapisDoruceni
          z={doruceni}
          hotovo={() => {
            setDoruceni(null)
            nacti()
          }}
        />
      )}
      {dokumenty.size === 0 && (
        <p className="tlumene">
          {filtr === 'ceka'
            ? 'Všechno, co odešlo, už došlo.'
            : 'Zatím se nic nerozesílalo. Rozeslat jde oznámení o zálohách, vyúčtování, upomínky a potvrzení o dluzích z jejich stránek.'}
        </p>
      )}
      {[...dokumenty.entries()].map(([k, zasilky]) => (
        <section key={k} className="zasilky-dokumentu">
          <h2>{zasilky[0].nazev}</h2>
          <div className="tabulka-posun">
            <table>
              <thead>
                <tr>
                  <th>Jednotka</th>
                  <th>Komu</th>
                  <th>Stav</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {zasilky.map((z) => (
                  <tr key={z.id}>
                    <td>{z.jednotka}</td>
                    <td>
                      {z.jmeno}
                      <div className="tlumene">
                        {z.kanal === 'email' ? `e-mailem, ${z.email}` : `dopisem${z.adresa ? `, ${z.adresa}` : ''}`}
                      </div>
                    </td>
                    <td>
                      <Stav z={z} />
                    </td>
                    <td>
                      <span className="radek">
                        <button className="odkaz" onClick={() => otevriDokument(z.dokument_id)}>
                          Dokument
                        </button>
                        {z.kanal === 'posta' && z.stav === 'pripravena' && (
                          <button className="odkaz" onClick={() => odeslanoDnes(z)}>
                            Odesláno dnes
                          </button>
                        )}
                        {z.stav !== 'dorucena' && (
                          <button className="odkaz" onClick={() => setDoruceni(z)}>
                            Zapsat doručení
                          </button>
                        )}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ))}
    </>
  )
}

function ZapisDoruceni({ z, hotovo }: { z: Zasilka; hotovo: () => void }) {
  const [den, setDen] = useState(z.otevreno ? z.otevreno.slice(0, 10) : dnes())
  const [zdroj, setZdroj] = useState(
    z.kanal === 'posta' ? 'Dodejka' : z.otevreno ? 'Vlastník otevřel odkaz v e-mailu' : '',
  )
  const [nedoruceno, setNedoruceno] = useState(false)
  const [chyba, setChyba] = useState<string | null>(null)

  async function uloz(e: FormEvent) {
    e.preventDefault()
    setChyba(null)
    try {
      if (nedoruceno) await api(`/api/zasilky/${z.id}/nedoruceno`, { method: 'POST', json: { duvod: zdroj } })
      else await api(`/api/zasilky/${z.id}/doruceni`, { method: 'POST', json: { datum: den, zdroj } })
      hotovo()
    } catch (e) {
      setChyba((e as Error).message)
    }
  }

  return (
    <form className="vlastnictvi-formular" onSubmit={uloz}>
      <h3>
        {z.nazev}, jednotka {z.jednotka}: {z.jmeno}
      </h3>
      <div className="faktura-formular">
        <label>
          Co se stalo
          <select value={nedoruceno ? 'ne' : 'ano'} onChange={(e) => setNedoruceno(e.target.value === 'ne')}>
            <option value="ano">Zásilka došla</option>
            <option value="ne">Zásilka nedošla (vrácená obálka, neplatná adresa)</option>
          </select>
        </label>
        {!nedoruceno && (
          <label>
            Kdy došla
            <input type="date" value={den} max={dnes()} onChange={(e) => setDen(e.target.value)} required />
          </label>
        )}
        <label className="cely-radek">
          {nedoruceno ? 'Proč nedošla' : 'Podle čeho to víte'}
          <input
            value={zdroj}
            maxLength={150}
            onChange={(e) => setZdroj(e.target.value)}
            placeholder={nedoruceno ? 'třeba Obálka se vrátila, adresát neznámý' : 'třeba Dodejka, převzal osobně'}
            required
          />
        </label>
      </div>
      <div className="radek">
        <button type="submit">Uložit</button>
        <button type="button" className="vedlejsi" onClick={hotovo}>
          Zrušit
        </button>
        {chyba && <span className="chyba">{chyba}</span>}
      </div>
    </form>
  )
}
