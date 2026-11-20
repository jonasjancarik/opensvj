/** Drobné společné prvky rozhraní: načítání, chyba a potvrzovací okno. */

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
