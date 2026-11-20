import { createAuthClient } from 'better-auth/react'
import { jwtClient, magicLinkClient } from 'better-auth/client/plugins'

export const authClient = createAuthClient({
  plugins: [magicLinkClient(), jwtClient()],
})

let token: { hodnota: string; platiDo: number } | null = null
let probiha: Promise<string> | null = null

/** Krátkodobý token pro backend. Obnoví se chvíli před vypršením; souběžné žádosti sdílí jeden dotaz. */
function ziskejToken(): Promise<string> {
  if (token && token.platiDo - Date.now() > 30_000) return Promise.resolve(token.hodnota)
  probiha ??= novyToken().finally(() => {
    probiha = null
  })
  return probiha
}

async function novyToken(): Promise<string> {
  const { data, error } = await authClient.token()
  if (error || !data) throw new Error('Nejste přihlášeni.')
  const exp = JSON.parse(atob(data.token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/'))).exp
  token = { hodnota: data.token, platiDo: exp * 1000 }
  return data.token
}

export function zapomenToken() {
  token = null
}

/** Chyba z API. `detail` je text pro uživatele, nebo objekt u chyb, na které aplikace reaguje. */
export class ChybaApi extends Error {
  status: number
  detail: unknown
  constructor(status: number, detail: unknown) {
    super(typeof detail === 'string' ? detail : `Server vrátil chybu ${status}.`)
    this.status = status
    this.detail = detail
  }
}

export async function api<T>(cesta: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const { json, headers, ...zbytek } = init
  const r = await fetch(cesta, {
    ...zbytek,
    body: json !== undefined ? JSON.stringify(json) : zbytek.body,
    headers: {
      Authorization: `Bearer ${await ziskejToken()}`,
      ...(json !== undefined ? { 'Content-Type': 'application/json' } : {}),
      ...headers,
    },
  })
  if (!r.ok) {
    const telo = await r.json().catch(() => null)
    throw new ChybaApi(r.status, telo?.detail ?? null)
  }
  return r.json() as Promise<T>
}
