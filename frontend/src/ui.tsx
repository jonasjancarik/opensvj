/** Drobné společné prvky rozhraní: načítání, chyba, upozornění na změnu po schválení. */
import type { ReactNode } from 'react'
import { casZmeny, odkazNaHistorii } from './odkazyHistorie'

export function Nacitani({ radku = 4 }: { radku?: number }) {
  return (
    <div className="nacitani" role="status" aria-live="polite">
      <span className="skryte">Načítám…</span>
      <div className="kostra kostra-nadpis" />
      {Array.from({ length: radku }, (_, i) => (
        <div key={i} className="kostra" style={{ width: `${92 - i * 11}%` }} />
      ))}
    </div>
  )
}

export function Chyba({ text }: { text: string }) {
  return (
    <div className="chybova-karta" role="alert">
      <strong>Něco se nepovedlo</strong>
      <p>{text}</p>
      <button className="vedlejsi" onClick={() => window.location.reload()}>
        Zkusit znovu
      </button>
    </div>
  )
}

/** Kdo a proč změnil schválenou věc; bez autora, když se změnila mimo aplikaci. */
export type ZmenaPoSchvaleni = {
  kdy: string | null
  kdo: string
  jmeno: string
  duvod: string
  druh: string | null
  klic: string | null
}

export function ZmenenoPoSchvaleni({ zmena, children }: { zmena: ZmenaPoSchvaleni; children?: ReactNode }) {
  return (
    <div className="zmeneno-po-schvaleni" role="note">
      <strong>Změněno po schválení</strong>
      <p>
        {zmena.kdy ? (
          <>
            {casZmeny(zmena.kdy)} · {zmena.jmeno || zmena.kdo}
            {zmena.duvod && <> · Důvod: {zmena.duvod}</>}
          </>
        ) : (
          'Změnilo se v souboru s nastavením společenství, mimo aplikaci.'
        )}
      </p>
      {children}
      {zmena.kdy && zmena.druh && (
        <a href={odkazNaHistorii(zmena.druh, zmena.klic)}>Co přesně se změnilo</a>
      )}
    </div>
  )
}
