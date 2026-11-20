/**
 * Kresba bytového domu, kde každé okno je jedna jednotka.
 *
 * Počet oken (a tím šířka a výška domu) se řídí počtem jednotek, takže kresba sedí na
 * malý dům i na velký panelák. Okno svítí, když má vlastník zaplaceno; tmavé je, když
 * dluží po splatnosti; s truhlíkem květin, když má přeplatek.
 */

export type StavOkna = 'zaplaceno' | 'dluh' | 'preplatek'
export type Okno = { jednotka: string; stav: StavOkna; popis: string; odkaz?: string }

const ROZTEC_X = 44 // vzdálenost oken vedle sebe
const ROZTEC_Y = 50 // výška patra
const OKNO_S = 20
const OKNO_V = 30
const OKRAJ = 20 // od kraje kresby k fasádě
const VNITRNI = 10 // od kraje fasády k prvnímu oknu
const STRECHA = 36 // štít a římsa nad fasádou
const PRIZEMI = 58

/** Kolik oken vedle sebe: malé domy spíš vysoké, velké spíš široké. */
function sloupcu(pocet: number) {
  return Math.max(2, Math.min(12, Math.ceil(Math.sqrt(pocet / 1.4))))
}

export function Dum({ okna, className, blikani = false }: { okna: Okno[]; className?: string; blikani?: boolean }) {
  const n = Math.max(okna.length, 1)
  const sl = sloupcu(n)
  const pater = Math.ceil(n / sl)
  const fasadaS = sl * ROZTEC_X + 2 * VNITRNI - (ROZTEC_X - OKNO_S)
  const sirka = fasadaS + 2 * OKRAJ
  const zacatekOken = STRECHA + 16
  const prizemiY = zacatekOken + pater * ROZTEC_Y
  const vyska = prizemiY + PRIZEMI + 4
  const stred = sirka / 2
  const stit = Math.min(64, fasadaS * 0.4)

  // Jednotky se číslují zdola: první jednotka vlevo v nejnižším patře.
  const pozice = okna.map((o, i) => {
    const patro = Math.floor(i / sl)
    const vPatre = Math.min(sl, okna.length - patro * sl)
    const odsazeni = ((sl - vPatre) * ROZTEC_X) / 2
    const x = OKRAJ + VNITRNI + odsazeni + (i % sl) * ROZTEC_X
    const y = zacatekOken + (pater - 1 - patro) * ROZTEC_Y
    return { o, x, y, i }
  })

  return (
    <svg
      className={className}
      viewBox={`0 0 ${sirka} ${vyska}`}
      role={okna.some((o) => o.odkaz) ? 'group' : 'img'}
      aria-label={`Dům s ${okna.length} jednotkami`}
    >
      <defs>
        <radialGradient id="zare" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="var(--okno-svetlo)" stopOpacity="0.5" />
          <stop offset="100%" stopColor="var(--okno-svetlo)" stopOpacity="0" />
        </radialGradient>
      </defs>
      {/* štít a římsa */}
      <path d={`M${stred - stit / 2} ${STRECHA - 10} Q${stred} ${STRECHA - 36} ${stred + stit / 2} ${STRECHA - 10}Z`} className="dum-stit" />
      <circle cx={stred} cy={STRECHA - 19} r="4.5" className="dum-okno" />
      <rect x={OKRAJ - 8} y={STRECHA - 10} width={fasadaS + 16} height="10" rx="2" className="dum-rimsa" />
      <rect x={OKRAJ} y={STRECHA} width={fasadaS} height={vyska - STRECHA - 4} className="dum-fasada" />
      {Array.from({ length: pater - 1 }, (_, p) => (
        <rect key={p} x={OKRAJ} y={zacatekOken + (p + 1) * ROZTEC_Y - 9} width={fasadaS} height="2.5" className="dum-linka" />
      ))}
      <rect x={OKRAJ} y={prizemiY - 9} width={fasadaS} height="4" className="dum-linka" />

      {/* záře za rozsvícenými okny */}
      {pozice.map(({ o, x, y, i }) =>
        o.stav === 'dluh' ? null : (
          <ellipse
            key={`z${i}`}
            cx={x + OKNO_S / 2}
            cy={y + OKNO_V / 2}
            rx="25"
            ry="27"
            fill="url(#zare)"
          />
        ),
      )}

      {pozice.map(({ o, x, y, i }) => {
        const okno = (
          <g className={`dum-jednotka dum-${o.stav}`}>
            <rect x={x} y={y} width={OKNO_S} height={OKNO_V} rx="1.5" className="dum-okno" />
            {blikani && o.stav === 'dluh' && i % 3 === 0 && (
              <rect x={x} y={y} width={OKNO_S} height={OKNO_V} rx="1.5" className={`dum-okno sviti dum-blika dum-blika-${(i / 3) % 4}`} />
            )}
            <path d={`M${x + OKNO_S / 2} ${y}v${OKNO_V}M${x} ${y + 12}h${OKNO_S}`} className="dum-priecka" />
            <rect x={x - 2} y={y + OKNO_V} width={OKNO_S + 4} height="3" rx="1" className="dum-parapet" />
            {o.stav === 'preplatek' && (
              <g className="dum-truhlik">
                <rect x={x} y={y + OKNO_V - 4} width={OKNO_S} height="4" rx="1" />
                <circle cx={x + 4} cy={y + OKNO_V - 5} r="2" className="kvet" />
                <circle cx={x + 10} cy={y + OKNO_V - 6} r="2" className="kvet" />
                <circle cx={x + 16} cy={y + OKNO_V - 5} r="2" className="kvet" />
              </g>
            )}
            {/* neviditelná plocha, aby se dalo trefit i mezi příčky */}
            <rect x={x - 6} y={y - 6} width={OKNO_S + 12} height={OKNO_V + 12} className="dum-terc" />
          </g>
        )
        return o.odkaz ? (
          <a key={i} href={o.odkaz} aria-label={o.popis}>
            <title>{o.popis}</title>
            {okno}
          </a>
        ) : (
          <g key={i}>{okno}</g>
        )
      })}

      {/* přízemí se vchodem */}
      <path d={`M${stred - 16} ${vyska - 4}v-38a16 16 0 0 1 32 0v38Z`} className="dum-dvere" />
      <circle cx={stred + 11} cy={vyska - 22} r="1.6" className="dum-klika" />
      {fasadaS > 140 && (
        <>
          <rect x={OKRAJ + VNITRNI} y={prizemiY + 14} width="30" height="22" rx="1.5" className="dum-okno-prizemi" />
          <rect x={OKRAJ + fasadaS - VNITRNI - 30} y={prizemiY + 14} width="30" height="22" rx="1.5" className="dum-okno-prizemi" />
        </>
      )}
      <rect x={OKRAJ - 10} y={vyska - 4} width={fasadaS + 20} height="3" rx="1.5" className="dum-zem" />
    </svg>
  )
}

/** Ozdobný dům bez dat (přihlašovací stránka): několik oken svítí a pomalu se střídají. */
export function OzdobnyDum({ className }: { className?: string }) {
  const tma = new Set([0, 2, 3, 5, 7, 8, 11])
  const okna: Okno[] = Array.from({ length: 12 }, (_, i) => ({
    jednotka: String(i + 1),
    stav: tma.has(i) ? 'dluh' : 'zaplaceno',
    popis: '',
  }))
  return <Dum okna={okna} className={className} blikani />
}

/** Malá značka aplikace do hlavičky. */
export function Znacka() {
  return (
    <svg className="znacka" viewBox="0 0 28 28" aria-hidden="true">
      <path d="M10 6.5 Q14 2.5 18 6.5Z" className="dum-stit" />
      <rect x="4" y="6.5" width="20" height="2.4" rx="0.8" className="dum-rimsa" />
      <rect x="5.5" y="8.9" width="17" height="17.6" rx="0.6" className="dum-fasada" />
      <rect x="8.5" y="11.5" width="3.8" height="5" rx="0.5" className="dum-okno" />
      <rect x="15.7" y="11.5" width="3.8" height="5" rx="0.5" className="dum-okno sviti" />
      <rect x="8.5" y="19" width="3.8" height="5" rx="0.5" className="dum-okno" />
      <rect x="15.7" y="19" width="3.8" height="7.5" rx="0.5" className="dum-dvere" />
    </svg>
  )
}
