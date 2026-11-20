/** Částky přicházejí z API v celých haléřích. */
export function kc(halire: number): string {
  const znamenko = halire < 0 ? '−' : ''
  const a = Math.abs(halire)
  const koruny = Math.floor(a / 100).toLocaleString('cs-CZ')
  return `${znamenko}${koruny},${String(a % 100).padStart(2, '0')} Kč`
}

/** Částka napsaná člověkem („1 234,50“, „1234.5 Kč“) v haléřích; null, když to částka není. */
export function naHalire(text: string): number | null {
  const t = text.replace(/[\s ]/g, '').replace('−', '-').replace(/Kč$/i, '').replace(',', '.')
  const m = /^(-?)(\d+)(?:\.(\d{1,2}))?$/.exec(t)
  if (!m) return null
  const h = Number(m[2]) * 100 + Number((m[3] ?? '0').padEnd(2, '0'))
  return m[1] ? -h : h
}
