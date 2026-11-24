import { useEffect, useState } from 'react'
import { api } from './auth'

export type Zasilka = {
  id: number
  davka: string
  druh: string
  klic: string
  nazev: string
  jednotka: string
  dokument_id: number
  sha256: string
  jmeno: string
  email: string | null
  adresa: string
  kanal: 'email' | 'posta'
  stav: 'pripravena' | 'odeslana' | 'dorucena' | 'nedorucena'
  pripraveno: string
  odeslano: string | null
  prijato_serverem: string | null
  otevreno: string | null
  potvrzeno: string | null
  doruceno: string | null
  doruceni_zdroj: string
  chyba: string
}
type Prehled = { odesilani_nastaveno: boolean; zasilky: Zasilka[] }
type Davka = { davka: string; zasilky: Zasilka[] }

export const datum = (iso: string) => new Date(iso).toLocaleDateString('cs-CZ')

/** Styly aplikace bez písem (ta se v uloženém dokumentu stejně nenačtou). */
function styly(): string {
  const casti: string[] = []
  for (const list of Array.from(document.styleSheets)) {
    try {
      for (const pravidlo of Array.from(list.cssRules)) {
        if (!(pravidlo instanceof CSSFontFaceRule)) casti.push(pravidlo.cssText)
      }
    } catch {
      // cizí styly (bez CORS) se přeskočí
    }
  }
  return casti.join('\n')
}

const escHtml = (t: string) => t.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')

/** Samostatná HTML stránka s dokumentem jedné jednotky, jak ji uvidí vlastník. */
function dokument(el: HTMLElement, nazev: string, css: string): string {
  const kopie = el.cloneNode(true) as HTMLElement
  kopie.querySelectorAll('.neni-v-tisku, button').forEach((x) => x.remove())
  return (
    '<!doctype html><html lang="cs" data-vzhled="svetly"><head><meta charset="utf-8">' +
    '<meta name="viewport" content="width=device-width, initial-scale=1">' +
    `<title>${escHtml(nazev)}</title><style>${css}\n` +
    'body{background:#fff;margin:0;padding:24px 16px}body::before{display:none}' +
    '.upominka{max-width:820px;margin:0 auto;box-shadow:none}</style></head>' +
    `<body>${kopie.outerHTML}</body></html>`
  )
}

function shrnuti(z: Zasilka[]) {
  const doruceno = z.filter((x) => x.stav === 'dorucena').length
  const odeslano = z.filter((x) => x.stav !== 'pripravena').length
  const nedoruceno = z.filter((x) => x.stav === 'nedorucena').length
  const casti = [`odesláno ${odeslano} z ${z.length}`, `doručeno ${doruceno}`]
  if (nedoruceno) casti.push(`nedoručeno ${nedoruceno}`)
  return casti.join(', ')
}

/** Vytiskne jen dokumenty (podle pořadí na stránce), které jdou dopisem. */
function tiskniJen(poradi: number[]) {
  const styl = document.createElement('style')
  styl.media = 'print'
  styl.textContent = `article[data-jednotka]:not(${poradi
    .map((i) => `[data-poradi="${i}"]`)
    .join(',')}){display:none!important}`
  document.head.appendChild(styl)
  window.addEventListener('afterprint', () => styl.remove(), { once: true })
  window.print()
}

/**
 * Rozeslání dokumentů zobrazených na stránce (prvky `article[data-jednotka]`) vlastníkům.
 * Nejdřív se dávka připraví a ukáže ke kontrole, odešle se až potvrzením.
 */
export function Rozeslat({ druh, klic, nazev }: { druh: string; klic: string; nazev: string }) {
  const [dosud, setDosud] = useState<Prehled | null>(null)
  const [davka, setDavka] = useState<Davka | null>(null)
  const [odeslano, setOdeslano] = useState(false)
  const [pracuji, setPracuji] = useState(false)
  const [chyba, setChyba] = useState<string | null>(null)

  const nacti = () =>
    api<Prehled>(`/api/zasilky?klic=${encodeURIComponent(klic)}`)
      .then(setDosud)
      .catch((e) => setChyba(e.message))
  useEffect(() => {
    nacti()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [klic])

  async function priprav() {
    const clanky = Array.from(document.querySelectorAll<HTMLElement>('article[data-jednotka]'))
    if (clanky.length === 0) return
    clanky.forEach((el, i) => (el.dataset.poradi = String(i)))
    setPracuji(true)
    setChyba(null)
    try {
      const css = styly()
      setDavka(
        await api<Davka>('/api/zasilky/priprav', {
          method: 'POST',
          json: {
            druh,
            klic,
            nazev,
            dokumenty: clanky.map((el) => ({
              jednotka: el.dataset.jednotka,
              html: dokument(el, nazev, css),
              // část vyúčtování pro dřívějšího vlastníka jde jemu, ne dnešnímu vlastníkovi
              osoby: el.dataset.osoby ? el.dataset.osoby.split(',').map(Number) : [],
            })),
          },
        }),
      )
      setOdeslano(false)
    } catch (e) {
      setChyba((e as Error).message)
    } finally {
      setPracuji(false)
    }
  }

  async function odesli() {
    if (!davka) return
    setPracuji(true)
    setChyba(null)
    try {
      setDavka(await api<Davka>(`/api/zasilky/davka/${davka.davka}/odeslat`, { method: 'POST' }))
      setOdeslano(true)
      nacti()
    } catch (e) {
      setChyba((e as Error).message)
    } finally {
      setPracuji(false)
    }
  }

  async function zrus() {
    if (!davka) return
    setPracuji(true)
    try {
      if (!odeslano) await api(`/api/zasilky/davka/${davka.davka}`, { method: 'DELETE' })
      setDavka(null)
      nacti()
    } catch (e) {
      setChyba((e as Error).message)
    } finally {
      setPracuji(false)
    }
  }

  async function dopisyOdeslany() {
    if (!davka) return
    const ids = davka.zasilky.filter((z) => z.kanal === 'posta' && z.stav === 'pripravena').map((z) => z.id)
    setPracuji(true)
    try {
      await api('/api/zasilky/odeslano', {
        method: 'POST',
        json: { ids, datum: new Date().toLocaleDateString('sv-SE') },
      })
      setDavka(null)
      nacti()
    } catch (e) {
      setChyba((e as Error).message)
    } finally {
      setPracuji(false)
    }
  }

  const odeslane = dosud?.zasilky.filter((z) => z.stav !== 'pripravena') ?? []

  if (!davka)
    return (
      <div className="rozeslat neni-v-tisku">
        <button onClick={priprav} disabled={pracuji}>
          {pracuji ? 'Připravuji…' : 'Rozeslat vlastníkům'}
        </button>
        {odeslane.length > 0 && (
          <span className="tlumene">
            Už rozesláno: {shrnuti(odeslane)}. <a href="#zasilky">Zásilky</a>
          </span>
        )}
        {chyba && <span className="chyba">{chyba}</span>}
      </div>
    )

  const emaily = davka.zasilky.filter((z) => z.kanal === 'email')
  const dopisy = davka.zasilky.filter((z) => z.kanal === 'posta')
  const kOdeslani = emaily.filter((z) => z.stav === 'pripravena')
  const nepovedlo = emaily.filter((z) => z.stav === 'nedorucena')
  // Dokumenty dávky vznikají v pořadí článků na stránce, takže n-tý dokument je n-tý článek.
  const dokumentyDavky = [...new Set(davka.zasilky.map((z) => z.dokument_id))].sort((a, b) => a - b)
  const dopisyPoradi = [...new Set(dopisy.map((z) => dokumentyDavky.indexOf(z.dokument_id)))]

  return (
    <section className="rozeslat-davka neni-v-tisku">
      <h2>{odeslano ? 'Rozesláno' : 'Kontrola před odesláním'}</h2>
      {!odeslano && (
        <p className="tlumene">
          Dokumenty jsou uložené přesně v podobě, v jaké je vlastníci dostanou. E-mailem půjdou jen těm, kdo s tím
          souhlasili; ostatním je potřeba je vytisknout a poslat poštou.
        </p>
      )}
      {odeslano && (
        <p className={nepovedlo.length ? 'upozorneni' : 'uspech'}>
          {emaily.length - nepovedlo.length > 0 && `E-mailem odesláno ${emaily.length - nepovedlo.length}. `}
          {nepovedlo.length > 0 && `Nepodařilo se ${nepovedlo.length}, viz tabulka. `}
          Doručení uvidíte v <a href="#zasilky">Zásilkách</a>, jakmile vlastník převzetí potvrdí.
        </p>
      )}
      <div className="tabulka-posun">
        <table>
          <thead>
            <tr>
              <th>Jednotka</th>
              <th>Komu</th>
              <th>Jak</th>
            </tr>
          </thead>
          <tbody>
            {davka.zasilky.map((z) => (
              <tr key={z.id}>
                <td>{z.jednotka}</td>
                <td>{z.jmeno}</td>
                <td>
                  {z.kanal === 'email' ? `E-mailem na ${z.email}` : 'Dopisem'}
                  {z.kanal === 'posta' && (z.adresa ? `, ${z.adresa}` : <span className="chyba">, chybí adresa</span>)}
                  {z.stav === 'nedorucena' && <div className="chyba">{z.chyba}</div>}
                  {z.stav === 'odeslana' && <div className="uspech">Odesláno</div>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!odeslano && kOdeslani.length > 0 && dosud && !dosud.odesilani_nastaveno && (
        <p className="upozorneni">
          Odesílání e-mailů zatím není nastavené. Požádejte správce aplikace, nebo dokumenty vytiskněte všem.
        </p>
      )}
      <div className="radek">
        {!odeslano && kOdeslani.length > 0 && (
          <button onClick={odesli} disabled={pracuji || !dosud?.odesilani_nastaveno}>
            {pracuji ? 'Odesílám…' : `Odeslat e-maily (${kOdeslani.length})`}
          </button>
        )}
        {dopisy.length > 0 && (
          <>
            <button className={kOdeslani.length ? 'vedlejsi' : undefined} onClick={() => tiskniJen(dopisyPoradi)}>
              Vytisknout dopisy ({dopisy.length})
            </button>
            <button className="vedlejsi" onClick={dopisyOdeslany} disabled={pracuji}>
              Označit dopisy jako odeslané dnes
            </button>
          </>
        )}
        <button className="vedlejsi" onClick={zrus} disabled={pracuji}>
          {odeslano ? 'Hotovo' : 'Zrušit'}
        </button>
        {chyba && <span className="chyba">{chyba}</span>}
      </div>
    </section>
  )
}
