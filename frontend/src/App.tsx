import { useEffect, useState } from 'react'
import { authClient, zapomenToken } from './auth'
import { Banka } from './Banka'
import { Znacka } from './Dum'
import { PrepinacVzhledu } from './Vzhled'
import { Denik } from './Denik'
import { Dluznici } from './Dluznici'
import { MimoradnaZaloha } from './MimoradnaZaloha'
import { Pokladna } from './Pokladna'
import { PotvrzeniPrevodu } from './PotvrzeniDluhu'
import { Faktury } from './Faktury'
import { Historie } from './Historie'
import { Oznameni } from './Oznameni'
import { Pocatecni } from './Pocatecni'
import { Podily } from './Podily'
import { Predpisy } from './Predpisy'
import { Prehled } from './Prehled'
import { Prihlaseni } from './Prihlaseni'
import { Uzaverka } from './Uzaverka'
import { Meridla } from './Meridla'
import { RozhodnutiOrganu } from './Rozhodnuti'
import { Vlastnici } from './Vlastnici'
import { Vyuctovani } from './Vyuctovani'
import { Zasilky } from './Zasilky'

// Pořadí podle toho, jak často se stránky používají: běžný měsíc, konec roku, evidence.
const STRANKY = {
  prehled: 'Přehled',
  banka: 'Banka',
  pokladna: 'Pokladna',
  faktury: 'Faktury',
  predpisy: 'Předpisy',
  dluznici: 'Dlužníci',
  vyuctovani: 'Vyúčtování',
  uzaverka: 'Uzávěrka',
  vlastnici: 'Vlastníci',
  meridla: 'Měřidla',
  rozhodnuti: 'Rozhodnutí',
  zasilky: 'Zásilky',
  denik: 'Deník',
  historie: 'Historie změn',
} as const
// Stránky, kterými v nabídce začíná nová skupina.
const ZACATEK_SKUPINY: ReadonlySet<string> = new Set(['banka', 'vyuctovani', 'vlastnici'])
// Stránky, které nejsou v menu (jednorázové nastavení); vedou na ně odkazy z jiných stránek.
const SKRYTE = {
  pocatecni: 'Počáteční stavy',
  oznameni: 'Oznámení o zálohách',
  podily: 'Podíly na společných částech',
  'mimoradna-zaloha': 'Mimořádná záloha',
  'potvrzeni-prevodu': 'Potvrzení o dluzích k datu převodu',
} as const
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
            <a
              key={klic}
              href={`#${klic}`}
              className={ZACATEK_SKUPINY.has(klic) ? 'nova-skupina' : undefined}
              aria-current={stranka === klic ? 'page' : undefined}
            >
              {nazev}
            </a>
          ))}
        </nav>
        <div className="uzivatel">
          <PrepinacVzhledu />
          <span className="avatar" title={session.user.email} aria-hidden="true">
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
        ) : stranka === 'podily' ? (
          <Podily />
        ) : stranka === 'pokladna' ? (
          <Pokladna />
        ) : stranka === 'mimoradna-zaloha' ? (
          <MimoradnaZaloha />
        ) : stranka === 'potvrzeni-prevodu' ? (
          <PotvrzeniPrevodu />
        ) : stranka === 'dluznici' ? (
          <Dluznici />
        ) : stranka === 'vlastnici' ? (
          <Vlastnici />
        ) : stranka === 'meridla' ? (
          <Meridla />
        ) : stranka === 'rozhodnuti' ? (
          <RozhodnutiOrganu />
        ) : stranka === 'faktury' ? (
          <Faktury />
        ) : stranka === 'denik' ? (
          <Denik />
        ) : stranka === 'vyuctovani' ? (
          <Vyuctovani />
        ) : stranka === 'zasilky' ? (
          <Zasilky />
        ) : stranka === 'uzaverka' ? (
          <Uzaverka />
        ) : stranka === 'historie' ? (
          <Historie />
        ) : (
          <Prehled />
        )}
      </main>
    </div>
  )
}
