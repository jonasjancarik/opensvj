/** Pomocné funkce pro historii změn (auditní záznam). */

export function casZmeny(kdy: string) {
  return new Date(kdy).toLocaleString('cs-CZ', { dateStyle: 'medium', timeStyle: 'short' })
}

/** Odkaz na historii změn jednoho druhu věcí, případně jedné věci. */
export function odkazNaHistorii(druh: string, klic?: string | null) {
  const q = new URLSearchParams({ druh, ...(klic ? { klic } : {}) })
  return `#historie?${q}`
}
