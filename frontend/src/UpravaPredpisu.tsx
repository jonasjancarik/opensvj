import { useEffect, useMemo, useState } from 'react'
import { api } from './auth'
import { potvrdit } from './potvrdit'
import { kc, naHalire } from './penize'
import { SKUPINY } from './Predpisy'

type Klic = 'plocha' | 'osoby' | 'pevna' | 'podil' | 'jednotka'
type SlozkaApi = { kod: string; nazev: string; role: string; klic: Klic; sazba: number | null }
type VerzeApi = {
  plati_od: string
  zdroj: string
  slozky: SlozkaApi[]
  pevne: Record<string, Record<string, number>>
  osoby: Record<string, number>
}
type Verze = VerzeApi & { v_aplikaci: boolean; upravitelna: boolean; upravil: string; mesicne: Record<string, number> }
type Role = { role: string; nazev: string; skupina: 'fond_oprav' | 'sprava' | 'sluzby' }
type Prehled = {
  dnes: string
  prvni_mesic: string
  jednotky: { oznaceni: string; plocha: number; podil: string }[]
  role: Role[]
  verze: Verze[]
}
type Nahled = { mesicne: Record<string, number>; chyba: string | null }

const KLICE: { id: Klic; nazev: string; castka: string }[] = [
  { id: 'plocha', nazev: 'podle plochy', castka: 'Kč za m² měsíčně' },
  { id: 'osoby', nazev: 'podle počtu osob', castka: 'Kč za osobu měsíčně' },
  { id: 'pevna', nazev: 'pevná částka', castka: 'Kč měsíčně za jednotku' },
  { id: 'podil', nazev: 'za dům podle podílů', castka: 'Kč měsíčně za celý dům' },
  { id: 'jednotka', nazev: 'za dům rovným dílem', castka: 'Kč měsíčně za celý dům' },
]

type RadekSlozky = { kod: string; nazev: string; role: string; klic: Klic; castka: string }
type Vyjimka = { jednotka: string; kod: string; castka: string }
type Rozpracovana = {
  puvodni: string | null
  mesic: string // YYYY-MM
  zdroj: string
  slozky: RadekSlozky[]
  vyjimky: Vyjimka[]
  osoby: Record<string, string>
}

const datum = (iso: string) => new Date(iso).toLocaleDateString('cs-CZ')
const naText = (h: number | undefined) =>
  h === undefined ? '' : (h / 100).toLocaleString('cs-CZ', { minimumFractionDigits: 2, useGrouping: false })
const plusMesic = (iso: string) => {
  const [r, m] = iso.split('-').map(Number)
  return m === 12 ? `${r + 1}-01` : `${r}-${String(m + 1).padStart(2, '0')}`
}
const soucet = (m: Record<string, number>) => Object.values(m).reduce((a, b) => a + b, 0)

function zVerze(p: Prehled, v: Verze, puvodni: string | null, mesic: string): Rozpracovana {
  const vychozi = v.pevne.vychozi ?? {}
  return {
    puvodni,
    mesic,
    zdroj: puvodni ? v.zdroj : '',
    slozky: v.slozky.map((s) => ({
      kod: s.kod,
      nazev: s.nazev,
      role: s.role,
      klic: s.klic,
      castka: naText(s.klic === 'pevna' ? vychozi[s.kod] : (s.sazba ?? undefined)),
    })),
    vyjimky: Object.entries(v.pevne)
      .filter(([j]) => j !== 'vychozi')
      .flatMap(([j, c]) => Object.entries(c).map(([kod, h]) => ({ jednotka: j, kod, castka: naText(h) }))),
    osoby: Object.fromEntries(p.jednotky.map((j) => [j.oznaceni, String(v.osoby[j.oznaceni] ?? v.osoby.vychozi ?? 0)])),
  }
}

/** Rozpracovaná verze pro API, nebo seznam polí, která nejdou přečíst. */
function doApi(r: Rozpracovana): { verze: VerzeApi | null; spatne: Set<string> } {
  const spatne = new Set<string>()
  const pevne: Record<string, Record<string, number>> = { vychozi: {} }
  const slozky = r.slozky.map((s, i) => {
    const h = s.castka.trim() === '' && s.klic === 'pevna' ? null : naHalire(s.castka)
    if (s.castka.trim() !== '' || s.klic !== 'pevna') if (h === null || h < 0) spatne.add(`s${i}`)
    if (s.klic === 'pevna' && h !== null) pevne.vychozi[s.kod] = h
    return { kod: s.kod, nazev: s.nazev.trim(), role: s.role, klic: s.klic, sazba: s.klic === 'pevna' ? null : h }
  })
  r.slozky.forEach((s, i) => s.nazev.trim() === '' && spatne.add(`n${i}`))
  r.vyjimky.forEach((x, i) => {
    const h = naHalire(x.castka)
    if (h === null || h < 0) spatne.add(`v${i}`)
    else (pevne[x.jednotka] ??= {})[x.kod] = h
  })
  const osoby: Record<string, number> = {}
  for (const [j, t] of Object.entries(r.osoby)) {
    if (!/^\d{1,3}$/.test(t.trim())) spatne.add(`o${j}`)
    else osoby[j] = Number(t)
  }
  if (!/^\d{4}-\d{2}$/.test(r.mesic)) spatne.add('mesic')
  if (spatne.size > 0) return { verze: null, spatne }
  return { verze: { plati_od: `${r.mesic}-01`, zdroj: r.zdroj.trim(), slozky, pevne, osoby }, spatne }
}

function novyKod(role: string, obsazene: string[]) {
  const zaklad =
    role
      .split('.')
      .pop()!
      .toUpperCase()
      .replace(/[^A-Z0-9_]/g, '_')
      .slice(0, 28) || 'SLOZKA'
  let kod = zaklad
  for (let i = 2; obsazene.includes(kod); i++) kod = `${zaklad}_${i}`
  return kod
}

export function UpravaPredpisu({ zmeneno }: { zmeneno: () => void }) {
  const [data, setData] = useState<Prehled | null>(null)
  const [chyba, setChyba] = useState<string | null>(null)
  const [uprava, setUprava] = useState<Rozpracovana | null>(null)

  useEffect(() => {
    api<Prehled>('/api/verze-predpisu')
      .then(setData)
      .catch((e) => setChyba(e.message))
  }, [])

  if (!data) return chyba ? <p className="chyba">{chyba}</p> : null

  const posledni = data.verze[data.verze.length - 1]

  function nova() {
    if (!data || !posledni) return
    const dnes = data.dnes.slice(0, 7)
    const kandidati = [plusMesic(dnes), data.prvni_mesic.slice(0, 7), plusMesic(posledni.plati_od.slice(0, 7))]
    setUprava(zVerze(data, posledni, null, kandidati.sort().pop()!))
  }

  async function smazat(v: Verze) {
    const ano = await potvrdit({
      nadpis: `Smazat předpis od ${datum(v.plati_od)}?`,
      text: 'Od toho data bude dál platit předchozí předpis.',
      ano: 'Smazat',
    })
    if (!ano) return
    setChyba(null)
    try {
      setData(await api<Prehled>(`/api/verze-predpisu/${v.plati_od}`, { method: 'DELETE' }))
      zmeneno()
    } catch (e) {
      setChyba((e as Error).message)
    }
  }

  if (uprava)
    return (
      <Editor
        data={data}
        uprava={uprava}
        setUprava={setUprava}
        ulozeno={(p) => {
          setData(p)
          setUprava(null)
          zmeneno()
        }}
      />
    )

  return (
    <>
      <h2>Změny předpisu</h2>
      <p className="tlumene">
        Když shromáždění nebo výbor schválí nové zálohy, zadejte je tady s datem, od kdy platí. Do té doby se dál účtuje
        podle dosavadního předpisu. Předpis pro měsíce, které už jsou zaúčtované, změnit nejde.
      </p>
      <div className="tabulka-posun">
        <table>
          <thead>
            <tr>
              <th>Platí od</th>
              <th>Podklad</th>
              <th className="cislo">Dům měsíčně</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {data.verze.map((v) => (
              <tr key={v.plati_od}>
                <td>{datum(v.plati_od)}</td>
                <td>
                  {v.zdroj || <span className="tlumene">bez podkladu</span>}
                  {v.v_aplikaci && <div className="tlumene">Zadáno v aplikaci{v.upravil && `, ${v.upravil}`}</div>}
                </td>
                <td className="cislo">{kc(soucet(v.mesicne))}</td>
                <td>
                  {v.upravitelna && (
                    <span className="radek">
                      <button
                        className="vedlejsi"
                        onClick={() => setUprava(zVerze(data, v, v.plati_od, v.plati_od.slice(0, 7)))}
                      >
                        Upravit
                      </button>
                      <button className="vedlejsi" onClick={() => smazat(v)}>
                        Smazat
                      </button>
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {chyba && <p className="chyba">{chyba}</p>}
      {posledni && (
        <p>
          <button onClick={nova}>Zadat nový předpis</button>
        </p>
      )}
    </>
  )
}

function Editor({
  data,
  uprava: r,
  setUprava,
  ulozeno,
}: {
  data: Prehled
  uprava: Rozpracovana
  setUprava: (r: Rozpracovana | null) => void
  ulozeno: (p: Prehled) => void
}) {
  const [nahled, setNahled] = useState<Nahled | null>(null)
  const [chyba, setChyba] = useState<string | null>(null)
  const [pracuji, setPracuji] = useState(false)
  const { verze, spatne } = useMemo(() => doApi(r), [r])
  const klic = JSON.stringify(verze)

  useEffect(() => {
    if (!verze) return
    const t = setTimeout(() => {
      api<Nahled>('/api/verze-predpisu/nahled', { method: 'POST', json: verze })
        .then(setNahled)
        .catch((e) => setNahled({ mesicne: {}, chyba: (e as Error).message }))
    }, 300)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [klic])

  const nazvyRoli = Object.fromEntries(data.role.map((x) => [x.role, x]))
  const pevne = r.slozky.filter((s) => s.klic === 'pevna')
  const sOsobami = r.slozky.some((s) => s.klic === 'osoby')
  const plati = `${r.mesic}-01`
  const dosud = data.verze.filter((v) => v.plati_od < plati && v.plati_od !== r.puvodni).pop()
  const nejdrive = data.prvni_mesic.slice(0, 7)

  const zmen = (zmena: Partial<Rozpracovana>) => setUprava({ ...r, ...zmena })
  const zmenSlozku = (i: number, zmena: Partial<RadekSlozky>) =>
    zmen({ slozky: r.slozky.map((s, j) => (j === i ? { ...s, ...zmena } : s)) })

  function zmenRoli(i: number, role: string) {
    const s = r.slozky[i]
    const puvodniNazev = nazvyRoli[s.role]?.nazev
    zmenSlozku(i, {
      role,
      nazev: !s.nazev || s.nazev === puvodniNazev ? (nazvyRoli[role]?.nazev ?? s.nazev) : s.nazev,
    })
  }

  function pridatSlozku() {
    const pouzite = new Set(r.slozky.map((s) => s.role))
    const role = data.role.find((x) => !pouzite.has(x.role)) ?? data.role[0]
    const kod = novyKod(
      role.role,
      r.slozky.map((s) => s.kod),
    )
    zmen({ slozky: [...r.slozky, { kod, nazev: role.nazev, role: role.role, klic: 'pevna', castka: '' }] })
  }

  function odebratSlozku(i: number) {
    const kod = r.slozky[i].kod
    zmen({ slozky: r.slozky.filter((_, j) => j !== i), vyjimky: r.vyjimky.filter((x) => x.kod !== kod) })
  }

  async function ulozit(e: React.FormEvent) {
    e.preventDefault()
    if (!verze) return
    const ano = await potvrdit({
      nadpis: `Uložit předpis od ${datum(plati)}?`,
      text:
        `Od ${datum(plati)} se zálohy budou účtovat podle něj, dům dohromady ${kc(soucet(nahled?.mesicne ?? {}))} měsíčně. ` +
        'Vlastníkům pošlete nové oznámení o výši záloh.',
      ano: 'Uložit',
    })
    if (!ano) return
    setPracuji(true)
    setChyba(null)
    try {
      ulozeno(
        await api<Prehled>('/api/verze-predpisu', {
          method: 'PUT',
          json: { puvodni: r.puvodni, verze },
        }),
      )
    } catch (e) {
      setChyba((e as Error).message)
    } finally {
      setPracuji(false)
    }
  }

  const neplatne = (k: string) => (spatne.has(k) ? 'neplatne' : undefined)

  return (
    <form className="uprava-predpisu" onSubmit={ulozit}>
      <h2>{r.puvodni ? `Úprava předpisu od ${datum(r.puvodni)}` : 'Nový předpis záloh'}</h2>
      <p className="tlumene">
        Formulář je předvyplněný podle {r.puvodni ? 'uloženého' : 'posledního'} předpisu, stačí změnit, co se mění.
        Částky jednotek se dopočítají dole.
      </p>
      <div className="faktura-formular">
        <label>
          Platí od
          <input
            type="month"
            value={r.mesic}
            min={nejdrive > '1900-01' ? nejdrive : undefined}
            onChange={(e) => zmen({ mesic: e.target.value })}
            className={neplatne('mesic')}
            required
          />
          {nejdrive > '1900-01' && <span className="tlumene">Nejdřív od {datum(data.prvni_mesic)}</span>}
        </label>
        <label>
          Podklad
          <input
            value={r.zdroj}
            maxLength={200}
            onChange={(e) => zmen({ zdroj: e.target.value })}
            placeholder="třeba Usnesení shromáždění z 12. 11. 2026"
          />
        </label>
      </div>

      <h3>Složky předpisu</h3>
      <div className="tabulka-posun">
        <table>
          <thead>
            <tr>
              <th>Za co</th>
              <th>Název pro vlastníky</th>
              <th>Jak se počítá</th>
              <th>Částka</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {r.slozky.map((s, i) => (
              <tr key={s.kod}>
                <td>
                  <select value={s.role} onChange={(e) => zmenRoli(i, e.target.value)} aria-label="Za co">
                    {SKUPINY.map((sk) => (
                      <optgroup key={sk.id} label={sk.nazev}>
                        {data.role
                          .filter((x) => x.skupina === sk.id)
                          .map((x) => (
                            <option key={x.role} value={x.role}>
                              {x.nazev}
                            </option>
                          ))}
                      </optgroup>
                    ))}
                  </select>
                </td>
                <td>
                  <input
                    value={s.nazev}
                    maxLength={100}
                    onChange={(e) => zmenSlozku(i, { nazev: e.target.value })}
                    className={neplatne(`n${i}`)}
                    aria-label="Název pro vlastníky"
                  />
                </td>
                <td>
                  <select
                    value={s.klic}
                    onChange={(e) => zmenSlozku(i, { klic: e.target.value as Klic })}
                    aria-label="Jak se počítá"
                  >
                    {KLICE.map((k) => (
                      <option key={k.id} value={k.id}>
                        {k.nazev}
                      </option>
                    ))}
                  </select>
                </td>
                <td>
                  <input
                    inputMode="decimal"
                    value={s.castka}
                    onChange={(e) => zmenSlozku(i, { castka: e.target.value })}
                    className={neplatne(`s${i}`)}
                    placeholder="0,00"
                    aria-label="Částka"
                  />
                  <div className="tlumene">{KLICE.find((k) => k.id === s.klic)?.castka}</div>
                </td>
                <td>
                  <button type="button" className="vedlejsi" onClick={() => odebratSlozku(i)}>
                    Odebrat
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p>
        <button type="button" className="vedlejsi" onClick={pridatSlozku}>
          Přidat složku
        </button>
      </p>

      {pevne.length > 0 && (
        <>
          <h3>Jednotky s jinou pevnou částkou</h3>
          <p className="tlumene">
            Pevná částka platí pro všechny jednotky stejně. Kde má některá jednotka jinou (třeba nebytový prostor bez
            teplé vody), zadejte ji tady.
          </p>
          {r.vyjimky.length > 0 && (
            <div className="tabulka-posun">
              <table>
                <thead>
                  <tr>
                    <th>Jednotka</th>
                    <th>Složka</th>
                    <th>Kč měsíčně</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {r.vyjimky.map((x, i) => {
                    const zmenVyjimku = (zmena: Partial<Vyjimka>) =>
                      zmen({ vyjimky: r.vyjimky.map((y, j) => (j === i ? { ...y, ...zmena } : y)) })
                    return (
                      <tr key={i}>
                        <td>
                          <select
                            value={x.jednotka}
                            onChange={(e) => zmenVyjimku({ jednotka: e.target.value })}
                            aria-label="Jednotka"
                          >
                            {data.jednotky.map((j) => (
                              <option key={j.oznaceni}>{j.oznaceni}</option>
                            ))}
                          </select>
                        </td>
                        <td>
                          <select
                            value={x.kod}
                            onChange={(e) => zmenVyjimku({ kod: e.target.value })}
                            aria-label="Složka"
                          >
                            {pevne.map((s) => (
                              <option key={s.kod} value={s.kod}>
                                {s.nazev}
                              </option>
                            ))}
                          </select>
                        </td>
                        <td>
                          <input
                            inputMode="decimal"
                            value={x.castka}
                            onChange={(e) => zmenVyjimku({ castka: e.target.value })}
                            className={neplatne(`v${i}`)}
                            placeholder="0,00"
                            aria-label="Kč měsíčně"
                          />
                        </td>
                        <td>
                          <button
                            type="button"
                            className="vedlejsi"
                            onClick={() => zmen({ vyjimky: r.vyjimky.filter((_, j) => j !== i) })}
                          >
                            Odebrat
                          </button>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
          <p>
            <button
              type="button"
              className="vedlejsi"
              onClick={() =>
                zmen({
                  vyjimky: [...r.vyjimky, { jednotka: data.jednotky[0].oznaceni, kod: pevne[0].kod, castka: '' }],
                })
              }
            >
              Přidat jinou částku jednotky
            </button>
          </p>
        </>
      )}

      {sOsobami && (
        <>
          <h3>Počet osob v jednotkách</h3>
          <div className="faktura-formular osoby-predpisu">
            {data.jednotky.map((j) => (
              <label key={j.oznaceni}>
                {j.oznaceni}
                <input
                  inputMode="numeric"
                  value={r.osoby[j.oznaceni] ?? ''}
                  onChange={(e) => zmen({ osoby: { ...r.osoby, [j.oznaceni]: e.target.value } })}
                  className={neplatne(`o${j.oznaceni}`)}
                />
              </label>
            ))}
          </div>
        </>
      )}

      <h3>Měsíční zálohy jednotek</h3>
      {spatne.size > 0 ? (
        <p className="chyba">Opravte zvýrazněná pole, pak se částky dopočítají.</p>
      ) : nahled?.chyba ? (
        <p className="chyba">{nahled.chyba}</p>
      ) : (
        nahled && (
          <div className="tabulka-posun">
            <table>
              <thead>
                <tr>
                  <th>Jednotka</th>
                  {dosud && <th className="cislo">Dosud</th>}
                  <th className="cislo">Nově</th>
                  {dosud && <th className="cislo">Rozdíl</th>}
                </tr>
              </thead>
              <tbody>
                {data.jednotky.map((j) => {
                  const nove = nahled.mesicne[j.oznaceni] ?? 0
                  const stare = dosud?.mesicne[j.oznaceni] ?? 0
                  return (
                    <tr key={j.oznaceni}>
                      <td>{j.oznaceni}</td>
                      {dosud && <td className="cislo">{kc(stare)}</td>}
                      <td className="cislo">{kc(nove)}</td>
                      {dosud && (
                        <td className="cislo">{nove === stare ? '–' : (nove > stare ? '+' : '') + kc(nove - stare)}</td>
                      )}
                    </tr>
                  )
                })}
                <tr className="soucet">
                  <th>Celý dům</th>
                  {dosud && <th className="cislo">{kc(soucet(dosud.mesicne))}</th>}
                  <th className="cislo">{kc(soucet(nahled.mesicne))}</th>
                  {dosud && (
                    <th className="cislo">
                      {(soucet(nahled.mesicne) > soucet(dosud.mesicne) ? '+' : '') +
                        kc(soucet(nahled.mesicne) - soucet(dosud.mesicne))}
                    </th>
                  )}
                </tr>
              </tbody>
            </table>
          </div>
        )
      )}

      <div className="radek">
        <button type="submit" disabled={pracuji || !verze || !nahled || !!nahled.chyba}>
          {pracuji ? 'Ukládám…' : 'Uložit předpis'}
        </button>
        <button type="button" className="vedlejsi" onClick={() => setUprava(null)}>
          Zrušit
        </button>
        {chyba && <span className="chyba">{chyba}</span>}
      </div>
    </form>
  )
}
