import { useEffect, useState } from 'react'
import { authClient, zapomenToken } from './auth'
import { Banka } from './Banka'
import { Znacka } from './Dum'
import { PrepinacVzhledu } from './Vzhled'
import { Denik } from './Denik'
import { Dluznici } from './Dluznici'
import { Faktury } from './Faktury'
import { Oznameni } from './Oznameni'
import { Pocatecni } from './Pocatecni'
import { Predpisy } from './Predpisy'
import { Prehled } from './Prehled'
import { Prihlaseni } from './Prihlaseni'
import { Uzaverka } from './Uzaverka'
import { Vlastnici } from './Vlastnici'
import { Vyuctovani } from './Vyuctovani'

const STRANKY = {
  prehled: 'Přehled',
  predpisy: 'Předpisy',
  dluznici: 'Dlužníci',
  vlastnici: 'Vlastníci',
  faktury: 'Faktury',
  banka: 'Banka',
  vyuctovani: 'Vyúčtování',
  uzaverka: 'Uzávěrka',
  denik: 'Deník',
} as const
// Stránky, které nejsou v menu (jednorázové nastavení); vedou na ně odkazy z jiných stránek.
const SKRYTE = { pocatecni: 'Počáteční stavy', oznameni: 'Oznámení o zálohách' } as const
type Stranka = keyof typeof STRANKY | keyof typeof SKRYTE

function zAdresy(): Stranka {
  const h = window.location.hash.slice(1).split('?')[0]
  return h in STRANKY || h in SKRYTE ? (h as Stranka) : 'prehled'
}

export default function App() {
  const { data: session, isPending } = authClient.useSession()
  const [stranka, setStranka] = useState<Stranka>(zAdresy)

  useEffect(() => {
    const zmena = () => {
      setStranka(zAdresy())
      window.scrollTo({ top: 0 })
    }
    window.addEventListener('hashchange', zmena)
    return () => window.removeEventListener('hashchange', zmena)
  }, [])

  useEffect(() => {
    // Na úzké obrazovce se nabídka posouvá do strany; aktuální stránka má být vidět.
    document
      .querySelector('nav.hlavni [aria-current="page"]')
      ?.scrollIntoView({ block: 'nearest', inline: 'center' })
  }, [stranka, session])

  if (isPending) return null
  if (!session) return <Prihlaseni />

  async function odhlasit() {
    zapomenToken()
    await authClient.signOut()
  }

  return (
    <div className="aplikace">
      <header>
        <a className="znacka-odkaz" href="#prehled">
          <Znacka />
          <span className="znacka-tekst">OpenSVJ</span>
        </a>
        <nav className="hlavni" aria-label="Hlavní nabídka">
          {Object.entries(STRANKY).map(([klic, nazev]) => (
            <a key={klic} href={`#${klic}`} aria-current={stranka === klic ? 'page' : undefined}>
              {nazev}
            </a>
          ))}
        </nav>
        <div className="uzivatel">
          <PrepinacVzhledu />
          <span className="avatar" aria-hidden="true">
            {session.user.email.slice(0, 1).toUpperCase()}
          </span>
          <span>{session.user.email}</span>
          <button className="odkaz" onClick={odhlasit}>
            Odhlásit se
          </button>
        </div>
      </header>
      <main key={stranka}>
        {stranka === 'banka' ? (
          <Banka />
        ) : stranka === 'predpisy' ? (
          <Predpisy />
        ) : stranka === 'pocatecni' ? (
          <Pocatecni />
        ) : stranka === 'oznameni' ? (
          <Oznameni />
        ) : stranka === 'dluznici' ? (
          <Dluznici />
        ) : stranka === 'vlastnici' ? (
          <Vlastnici />
        ) : stranka === 'faktury' ? (
          <Faktury />
        ) : stranka === 'denik' ? (
          <Denik />
        ) : stranka === 'vyuctovani' ? (
          <Vyuctovani />
        ) : stranka === 'uzaverka' ? (
          <Uzaverka />
        ) : (
          <Prehled />
        )}
      </main>
    </div>
  )
}
