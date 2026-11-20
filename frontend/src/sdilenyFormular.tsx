import { useCallback, useEffect, useRef, useState } from 'react'
import { api, ChybaApi } from './auth'

/**
 * Rozepsaný formulář uložený v databázi, aby ho viděl celý výbor.
 *
 * Změny se ukládají samy chvíli po posledním psaní. Server uloží jen tehdy, když od načtení
 * nikdo jiný neuložil novější verzi; jinak hook ohlásí konflikt a nechá uživatele vybrat,
 * kterou verzi ponechat. Nic se tak nepřepíše potichu.
 */

type Ulozeny<T> = {
  obsah: T | null
  verze: number
  upravil: string | null
  jmeno: string | null
  upraveno: string | null
}

export type StavUlozeni = 'nacitam' | 'ulozeno' | 'neulozeno' | 'ukladam' | 'chyba' | 'konflikt'

export type Posledni = { jmeno: string; upraveno: string } | null

const PRODLEVA = 800

function posledni<T>(u: Ulozeny<T>): Posledni {
  return u.upraveno ? { jmeno: u.jmeno || u.upravil || '', upraveno: u.upraveno } : null
}

export function useSdilenyFormular<T>(
  druh: string,
  klic: string | null,
  vychozi: () => T,
  moznosti: {
    /** Úprava načteného obsahu (např. srovnání čítače řádků). */
    nacteno?: (t: T) => T
    /** Kde si formulář dřív pamatoval jen prohlížeč; obsah se jednou přenese do databáze. */
    zPrehlizece?: { klic: string; preved: (ulozeno: string) => T }
  } = {},
) {
  // Všechen stav patří k jednomu klíči; po přepnutí klíče se starý stav nezobrazí a pozdě
  // doběhlé uložení pro starý klíč nic nepřepíše.
  type Stav = {
    klic: string | null
    obsah: T | null
    stav: StavUlozeni
    chyba: string | null
    naposledy: Posledni
    cizi: Ulozeny<T> | null
  }
  const [s, setS] = useState<Stav>({
    klic: null,
    obsah: null,
    stav: 'nacitam',
    chyba: null,
    naposledy: null,
    cizi: null,
  })
  const aktualni: Stav =
    s.klic === klic
      ? s
      : { klic, obsah: null, stav: 'nacitam', chyba: null, naposledy: null, cizi: null }
  const zmenStav = useCallback(
    (k: string, zmena: Partial<Stav>) => setS((x) => (x.klic === k ? { ...x, ...zmena } : x)),
    [],
  )

  const verze = useRef(0)
  const cekajici = useRef<T | null>(null)
  const casovac = useRef<number | undefined>(undefined)
  const bezi = useRef(false)
  const zahozeno = useRef(false)
  const platnyKlic = useRef<string | null>(null)
  const moz = useRef(moznosti)
  const vych = useRef(vychozi)
  useEffect(() => {
    moz.current = moznosti
    vych.current = vychozi
  })
  const pripravit = (t: T | null) => (moz.current.nacteno ?? ((x: T) => x))(t ?? vych.current())

  const ulozRef = useRef<(k: string) => Promise<void>>(async () => {})
  useEffect(() => {
    ulozRef.current = async (k: string) => {
      window.clearTimeout(casovac.current)
      if (zahozeno.current || cekajici.current === null || platnyKlic.current !== k) return
      if (bezi.current) return // po dokončení běžícího uložení se spustí znovu
      const t = cekajici.current
      cekajici.current = null
      bezi.current = true
      zmenStav(k, { stav: 'ukladam' })
      try {
        const r = await api<Ulozeny<T>>(`/api/formulare/${druh}/${k}`, {
          method: 'PUT',
          json: { obsah: t, verze: verze.current },
        })
        bezi.current = false
        if (platnyKlic.current !== k) return
        verze.current = r.verze
        const stary = moz.current.zPrehlizece
        if (stary) {
          try {
            localStorage.removeItem(stary.klic)
          } catch {
            /* nic */
          }
        }
        const dalsi = cekajici.current !== null
        zmenStav(k, { naposledy: posledni(r), chyba: null, stav: dalsi ? 'neulozeno' : 'ulozeno' })
        if (dalsi) void ulozRef.current(k)
      } catch (e) {
        bezi.current = false
        if (platnyKlic.current !== k) return
        if (cekajici.current === null) cekajici.current = t
        if (e instanceof ChybaApi && e.status === 409) {
          const d = e.detail as { aktualni?: Ulozeny<T> } | null
          zmenStav(k, { cizi: d?.aktualni ?? null, stav: 'konflikt' })
        } else zmenStav(k, { chyba: (e as Error).message, stav: 'chyba' })
      }
    }
  }, [druh, zmenStav])

  useEffect(() => {
    zahozeno.current = false
    cekajici.current = null
    platnyKlic.current = klic
    if (!klic) return
    let platne = true
    api<Ulozeny<T>>(`/api/formulare/${druh}/${klic}`)
      .then((r) => {
        if (!platne) return
        verze.current = r.verze
        let nacteny = r.obsah
        let zPrehlizece = false
        const stary = moz.current.zPrehlizece
        if (nacteny === null && stary) {
          try {
            const ulozeny = localStorage.getItem(stary.klic)
            if (ulozeny !== null) {
              nacteny = stary.preved(ulozeny)
              zPrehlizece = true
            }
          } catch {
            /* nic k přenesení */
          }
        }
        const t = pripravit(nacteny)
        setS({
          klic,
          obsah: t,
          stav: zPrehlizece ? 'neulozeno' : 'ulozeno',
          chyba: null,
          naposledy: posledni(r),
          cizi: null,
        })
        if (zPrehlizece) {
          cekajici.current = t
          void ulozRef.current(klic)
        }
      })
      .catch((e) => {
        if (!platne) return
        setS({
          klic,
          obsah: null,
          stav: 'chyba',
          chyba: (e as Error).message,
          naposledy: null,
          cizi: null,
        })
      })
    return () => {
      platne = false
      // Rozepsané změny se před odchodem ze stránky ještě uloží.
      if (cekajici.current !== null && !zahozeno.current) void ulozRef.current(klic)
      platnyKlic.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [druh, klic])

  const stav = aktualni.stav
  useEffect(() => {
    const neulozene =
      stav === 'neulozeno' || stav === 'ukladam' || stav === 'chyba' || stav === 'konflikt'
    if (!neulozene) return
    const varuj = (e: BeforeUnloadEvent) => e.preventDefault()
    window.addEventListener('beforeunload', varuj)
    return () => window.removeEventListener('beforeunload', varuj)
  }, [stav])

  function zmen(t: T) {
    if (!klic) return
    cekajici.current = t
    if (stav === 'konflikt') {
      zmenStav(klic, { obsah: t }) // čeká na rozhodnutí, kterou verzi ponechat
      return
    }
    zmenStav(klic, { obsah: t, stav: 'neulozeno' })
    window.clearTimeout(casovac.current)
    const k = klic
    casovac.current = window.setTimeout(() => void ulozRef.current(k), PRODLEVA)
  }

  /** Konflikt: zahodit své změny a načíst verzi, kterou uložil někdo jiný. */
  function prevzitCizi() {
    const cizi = aktualni.cizi
    if (!klic || !cizi) return
    cekajici.current = null
    verze.current = cizi.verze
    zmenStav(klic, {
      obsah: pripravit(cizi.obsah),
      naposledy: posledni(cizi),
      cizi: null,
      stav: 'ulozeno',
    })
  }

  /** Konflikt: ponechat svou verzi a uložit ji přes tu cizí. */
  function ponechatSvou() {
    const cizi = aktualni.cizi
    if (!klic || !cizi || aktualni.obsah === null) return
    verze.current = cizi.verze
    cekajici.current = aktualni.obsah
    zmenStav(klic, { cizi: null })
    void ulozRef.current(klic)
  }

  function zkusitZnovu() {
    if (!klic || aktualni.obsah === null) return
    cekajici.current = aktualni.obsah
    void ulozRef.current(klic)
  }

  /** Formulář už není potřeba (server ho smazal); nic dalšího se neuloží. */
  function zahodit() {
    zahozeno.current = true
    window.clearTimeout(casovac.current)
    cekajici.current = null
  }

  return {
    obsah: aktualni.obsah,
    zmen,
    stav,
    chyba: aktualni.chyba,
    naposledy: aktualni.naposledy,
    cizi: aktualni.cizi ? posledni(aktualni.cizi) : null,
    prevzitCizi,
    ponechatSvou,
    zkusitZnovu,
    zahodit,
  }
}

const kdy = (d: string) =>
  new Date(d).toLocaleString('cs-CZ', { day: 'numeric', month: 'numeric', hour: '2-digit', minute: '2-digit' })

/** Řádek pod formulářem: jestli je uloženo a kdo naposledy ukládal. */
type StavProZobrazeni = Pick<
  ReturnType<typeof useSdilenyFormular<unknown>>,
  'stav' | 'chyba' | 'naposledy' | 'cizi' | 'prevzitCizi' | 'ponechatSvou' | 'zkusitZnovu'
>

export function StavFormulare({ f }: { f: StavProZobrazeni }) {
  if (f.stav === 'konflikt') {
    return (
      <div className="upozorneni stav-formulare" role="alert">
        <p>
          Mezitím se tu uložila jiná verze
          {f.cizi && (
            <>
              {' '}
              ({f.cizi.jmeno}, {kdy(f.cizi.upraveno)})
            </>
          )}
          . Vaše poslední změny zatím uložené nejsou.
        </p>
        <div className="radek">
          <button type="button" className="vedlejsi" onClick={f.prevzitCizi}>
            Načíst uloženou verzi
          </button>
          <button type="button" onClick={f.ponechatSvou}>
            Uložit moji verzi
          </button>
        </div>
      </div>
    )
  }
  if (f.stav === 'chyba') {
    return (
      <p className="upozorneni stav-formulare" role="alert">
        Změny se nepodařilo uložit{f.chyba ? `: ${f.chyba}` : '.'}{' '}
        <button type="button" className="odkaz" onClick={f.zkusitZnovu}>
          Zkusit znovu
        </button>
      </p>
    )
  }
  return (
    <p className="tlumene stav-formulare" aria-live="polite">
      {f.stav === 'nacitam' && 'Načítám…'}
      {(f.stav === 'neulozeno' || f.stav === 'ukladam') && 'Ukládám…'}
      {f.stav === 'ulozeno' &&
        (f.naposledy
          ? `Uloženo pro celý výbor. Naposledy ${f.naposledy.jmeno}, ${kdy(f.naposledy.upraveno)}.`
          : 'Zatím nic neuloženo.')}
    </p>
  )
}
