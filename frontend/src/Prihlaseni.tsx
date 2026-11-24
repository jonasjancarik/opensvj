import { useState, type FormEvent } from 'react'
import { authClient } from './auth'
import { OzdobnyDum, Znacka } from './Dum'
import { PrepinacVzhledu } from './Vzhled'

export function Prihlaseni() {
  const [email, setEmail] = useState('')
  const [stav, setStav] = useState<'zadani' | 'odesilam' | 'odeslano'>('zadani')
  const [chyba, setChyba] = useState<string | null>(null)

  async function odeslat(e: FormEvent) {
    e.preventDefault()
    setStav('odesilam')
    setChyba(null)
    const { error } = await authClient.signIn.magicLink({ email, callbackURL: '/' })
    if (error) {
      setChyba('Odkaz se nepodařilo odeslat. Zkuste to prosím znovu za chvíli.')
      setStav('zadani')
      return
    }
    setStav('odeslano')
  }

  return (
    <div className="prihlaseni">
      <PrepinacVzhledu className="prihlaseni-vzhled" />
      <main className="prihlaseni-formular">
        <span className="znacka-odkaz">
          <Znacka />
          OpenSVJ
        </span>
        {stav === 'odeslano' ? (
          <div>
            <div className="odeslano-ikona" aria-hidden="true">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <rect x="3" y="5" width="18" height="14" rx="2.5" />
                <path d="m4 7 8 6 8-6" />
              </svg>
            </div>
            <h1>Zkontrolujte e-mail</h1>
            <p>
              Pokud je adresa <strong>{email}</strong> v aplikaci povolená, přišel na ni odkaz pro
              přihlášení. Platí 15 minut a dá se použít jen jednou.
            </p>
            <button className="vedlejsi" onClick={() => setStav('zadani')}>
              Zadat jinou adresu
            </button>
          </div>
        ) : (
          <div>
            <h1>Dobrý den</h1>
            <p>
              Zadejte svůj e-mail a pošleme vám odkaz, kterým se přihlásíte. Heslo nepotřebujete.
            </p>
            <form onSubmit={odeslat}>
              <label htmlFor="email">E-mail</label>
              <input
                id="email"
                type="email"
                autoComplete="email"
                placeholder="jmeno@example.cz"
                required
                autoFocus
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
              <button type="submit" disabled={stav === 'odesilam'}>
                {stav === 'odesilam' ? 'Odesílám…' : 'Poslat přihlašovací odkaz'}
              </button>
            </form>
            {chyba && <p className="chyba">{chyba}</p>}
          </div>
        )}
      </main>
      <div className="prihlaseni-obraz" aria-hidden="true">
        <p className="prihlaseni-citat">Správa domu, ve které se dá vyznat.</p>
        <OzdobnyDum />
      </div>
    </div>
  )
}
