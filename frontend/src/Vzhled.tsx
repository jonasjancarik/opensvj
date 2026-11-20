import { useState } from 'react'

type Vzhled = 'system' | 'svetly' | 'tmavy'
const KLIC = 'vzhled'

function ulozeny(): Vzhled {
  try {
    const v = localStorage.getItem(KLIC)
    return v === 'svetly' || v === 'tmavy' ? v : 'system'
  } catch {
    return 'system'
  }
}

const IKONY: Record<Vzhled, { popis: string; kresba: React.ReactNode }> = {
  system: {
    popis: 'Podle systému',
    kresba: (
      <>
        <rect x="3" y="4.5" width="18" height="12" rx="2" />
        <path d="M8.5 20h7M12 16.5V20" />
      </>
    ),
  },
  svetly: {
    popis: 'Světlý vzhled',
    kresba: (
      <>
        <circle cx="12" cy="12" r="4" />
        <path d="M12 2.5v2M12 19.5v2M4.6 4.6l1.4 1.4M18 18l1.4 1.4M2.5 12h2M19.5 12h2M4.6 19.4 6 18M18 6l1.4-1.4" />
      </>
    ),
  },
  tmavy: {
    popis: 'Tmavý vzhled',
    kresba: <path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5Z" />,
  },
}

/** Přepínač světlého a tmavého vzhledu. Volba se pamatuje v prohlížeči. */
export function PrepinacVzhledu({ className = '' }: { className?: string }) {
  const [vzhled, setVzhled] = useState<Vzhled>(ulozeny)

  function zvol(v: Vzhled) {
    setVzhled(v)
    if (v === 'system') document.documentElement.removeAttribute('data-vzhled')
    else document.documentElement.dataset.vzhled = v
    try {
      if (v === 'system') localStorage.removeItem(KLIC)
      else localStorage.setItem(KLIC, v)
    } catch {
      /* volba platí jen do zavření stránky */
    }
  }

  return (
    <div className={`vzhled ${className}`} role="group" aria-label="Vzhled">
      {(Object.keys(IKONY) as Vzhled[]).map((v) => (
        <button
          key={v}
          type="button"
          aria-pressed={vzhled === v}
          aria-label={IKONY[v].popis}
          title={IKONY[v].popis}
          onClick={() => zvol(v)}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            {IKONY[v].kresba}
          </svg>
        </button>
      ))}
    </div>
  )
}
