import { useCallback, useEffect, useState } from 'react'
import { api, ChybaApi } from './auth'
import { Chyba, Nacitani } from './ui'
import { kc } from './penize'

type Ucet = {
  ucel: string
  nazev: string
  cislo: string | null
  zustatek: number | null
  posledni_vypis: string | null
  datum_vypisu: string | null
  pohyby_do: string | null
}
type Moznost = { id: string; nazev: string; stav: string; pole: string[]; volitelna: string[] }
type DluhJednotky = { radek: number; popis: string; splatnost: string | null; zbyva: number }
type Navrh = { operace: string; vstupy: Record<string, string>; duvod: string }
type Zauctovani = {
  operace: string
  nazev: string
  vstupy: Record<string, string>
  zapis: string
  zauctoval: string
}
type Pohyb = {
  id: number
  datum: string
  castka: number
  ucel: string
  zdroj: string
  protiucet: string | null
  nazev: string
  vs: string | null
  ks: string | null
  ss: string | null
  zprava: string
  navrh: Navrh | null
  zauctovano: Zauctovani | null
}
type OtevrenaFaktura = {
  cislo: string
  dodavatel: string
  cislo_dodavatele: string | null
  zbyva: number
  splatnost: string
}
type Banka = {
  ucty: Ucet[]
  jednotky: string[]
  drivejsi: { jednotka: string; vlastnik: string; castka: number }[]
  odepsane: { jednotka: string; zbyva: number }[]
  faktury: OtevrenaFaktura[]
  moznosti: Record<'prijem' | 'vydaj', Moznost[]>
  pohyby: Pohyb[]
  nezauctovano: number
}
type Nahrano = {
  druh: 'vypis' | 'export'
  nazev_uctu: string
  cislo: number | null
  rok: number
  od: string | null
  do: string
  pocet_pohybu: number
  novych: number
  uz_nahranych: number
  uz_byl_nahrany: boolean
}

const datum = (d: string) => new Date(d).toLocaleDateString('cs-CZ')

export function Banka() {
  const [data, setData] = useState<Banka | null>(null)
  const [vse, setVse] = useState(false)
  const [chyba, setChyba] = useState<string | null>(null)

  const nacti = useCallback(() => {
    api<Banka>(`/api/banka${vse ? '?vse=true' : ''}`)
      .then((d) => {
        setData(d)
        setChyba(null)
      })
      .catch((e) => setChyba(e.message))
  }, [vse])

  useEffect(nacti, [nacti])

  function zauctovano(p: Pohyb) {
    setData((d) =>
      d && {
        ...d,
        nezauctovano: d.nezauctovano - 1,
        pohyby: d.pohyby.map((x) => (x.id === p.id ? p : x)),
      },
    )
  }

  if (chyba && !data) return <Chyba text={chyba} />
  if (!data) return <Nacitani />

  return (
    <>
      <h1>Banka</h1>
      <div className="ucty">
        {data.ucty.map((u) => (
          <div key={u.ucel} className="ucet">
            <strong>{u.nazev}</strong>
            {u.cislo ? (
              <>
                <span className="tlumene">{u.cislo}</span>
                {u.posledni_vypis ? (
                  <>
                    <span className="ucet-zustatek">{kc(u.zustatek ?? 0)}</span>
                    <span className="tlumene">
                      podle výpisu {u.posledni_vypis} ze dne {datum(u.datum_vypisu!)}
                    </span>
                  </>
                ) : (
                  <span className="tlumene">
                    Zůstatek zatím neznáme, ukáže ho až výpis z banky.
                  </span>
                )}
                {u.pohyby_do && (
                  <span className="tlumene">Platby nahrané do {datum(u.pohyby_do)}</span>
                )}
              </>
            ) : (
              <span className="tlumene">Zatím nebyl nahrán žádný výpis.</span>
            )}
          </div>
        ))}
      </div>

      <NahraniVypisu ucty={data.ucty} poNahrani={nacti} />

      <div className="nadpis-radek">
        <h2>
          {data.nezauctovano === 0 && data.ucty.some((u) => u.cislo)
            ? 'Všechny platby jsou zaúčtované'
            : data.nezauctovano === 0
              ? 'Platby k zaúčtování'
            : `Platby k zaúčtování (${data.nezauctovano})`}
        </h2>
        <label className="zaskrtavatko">
          <input type="checkbox" checked={vse} onChange={(e) => setVse(e.target.checked)} />
          Zobrazit i zaúčtované
        </label>
      </div>
      {data.pohyby.length === 0 ? (
        <p className="tlumene">
          {data.ucty.some((u) => u.cislo)
            ? 'Nic tu není. Nové platby přibudou po nahrání dalšího výpisu.'
            : 'Začněte nahráním výpisu z banky.'}
        </p>
      ) : (
        <ul className="pohyby">
          {data.pohyby.map((p) => (
            <PolozkaPohybu key={p.id} pohyb={p} data={data} poZauctovani={zauctovano} />
          ))}
        </ul>
      )}
    </>
  )
}

function NahraniVypisu({ ucty, poNahrani }: { ucty: Ucet[]; poNahrani: () => void }) {
  const [soubor, setSoubor] = useState<File | null>(null)
  const [neznamy, setNeznamy] = useState<string | null>(null)
  const [zprava, setZprava] = useState<{ text: string; chyba: boolean } | null>(null)
  const [pracuji, setPracuji] = useState(false)
  const [klicPole, setKlicPole] = useState(0)
  const volne = ucty.filter((u) => !u.cislo)

  async function nahraj(f: File, ucel?: string) {
    setPracuji(true)
    setZprava(null)
    const parametry = new URLSearchParams({ nazev: f.name })
    if (ucel) parametry.set('ucel', ucel)
    try {
      const vysledek = await api<Nahrano[]>(`/api/banka/vypisy?${parametry}`, {
        method: 'POST',
        body: await f.arrayBuffer(),
        headers: { 'Content-Type': 'application/octet-stream' },
      })
      setNeznamy(null)
      setSoubor(null)
      setKlicPole((k) => k + 1)
      setZprava({
        chyba: false,
        text: vysledek
          .map((v) => {
            const co =
              v.druh === 'vypis'
                ? `výpis ${v.cislo}/${v.rok}`
                : `přehled plateb ${v.od ? `od ${datum(v.od)} ` : ''}do ${datum(v.do)}`
            if (v.uz_byl_nahrany) return `${v.nazev_uctu}: ${co} už byl nahraný dřív, nic se nezměnilo.`
            const drive = v.uz_nahranych
              ? ` ${pocetPlateb(v.uz_nahranych)} už aplikace měla, ty se nezdvojily.`
              : ''
            return `${v.nazev_uctu}: nahrán ${co}, nových plateb ${v.novych}.${drive}`
          })
          .join(' '),
      })
      poNahrani()
    } catch (e) {
      const d = e instanceof ChybaApi ? (e.detail as { kod?: string; cislo?: string }) : null
      if (d && typeof d === 'object' && d.kod === 'neznamy_ucet') {
        setNeznamy(d.cislo ?? '')
      } else {
        setZprava({ chyba: true, text: (e as Error).message })
      }
    } finally {
      setPracuji(false)
    }
  }

  return (
    <section className="nahrani">
      <h2>Nahrát platby z banky</h2>
      <p className="tlumene">
        Nahrajte výpis ve formátu GPC (někde se jmenuje ABO), nebo přehled pohybů, který
        internetové bankovnictví Raiffeisenbank stáhne jako CSV. Přehled pohybů stačí na
        průběžné zaúčtování plateb; zůstatek účtu ověří až výpis. Stejné platby se nikdy
        nezdvojí, i když se soubory překrývají.
      </p>
      <div className="radek">
        <input
          key={klicPole}
          id="soubor-vypisu"
          className="skryte"
          type="file"
          accept=".gpc,.abo,.txt,.csv"
          aria-label="Soubor s výpisem"
          onChange={(e) => {
            setSoubor(e.target.files?.[0] ?? null)
            setNeznamy(null)
            setZprava(null)
          }}
        />
        <label htmlFor="soubor-vypisu" className="vyber-souboru">
          <span>Vybrat soubor</span>
          {soubor ? soubor.name : 'Zatím není vybraný žádný soubor'}
        </label>
        <button disabled={!soubor || pracuji} onClick={() => soubor && nahraj(soubor)}>
          {pracuji ? 'Nahrávám…' : 'Nahrát'}
        </button>
      </div>
      {neznamy !== null && soubor && (
        <div className="dotaz">
          <p>
            Účet <strong>{neznamy}</strong> aplikace zatím nezná. Který účet SVJ to je?
          </p>
          {volne.length === 0 ? (
            <p className="chyba">
              Všechny účty SVJ už mají číslo přiřazené. Zkontrolujte, že jde o výpis účtu SVJ.
            </p>
          ) : (
            <div className="radek">
              {volne.map((u) => (
                <button key={u.ucel} disabled={pracuji} onClick={() => nahraj(soubor, u.ucel)}>
                  {u.nazev}
                </button>
              ))}
              <button className="vedlejsi" onClick={() => setNeznamy(null)}>
                Zrušit
              </button>
            </div>
          )}
        </div>
      )}
      {zprava && <p className={zprava.chyba ? 'chyba' : 'uspech'}>{zprava.text}</p>}
    </section>
  )
}

function pocetPlateb(n: number) {
  if (n === 1) return '1 platbu'
  if (n >= 2 && n <= 4) return `${n} platby`
  return `${n} plateb`
}

const POPIS_POLE: Record<string, string> = {
  jednotka: 'Jednotka',
  protistrana: 'Dodavatel',
  faktura: 'Kterou fakturu platba platí',
  drivejsi_vlastnik: 'Dřívější vlastník',
}

function PolozkaPohybu({
  pohyb: p,
  data,
  poZauctovani,
}: {
  pohyb: Pohyb
  data: Banka
  poZauctovani: (p: Pohyb) => void
}) {
  const smer = p.castka > 0 ? 'prijem' : 'vydaj'
  const moznosti = data.moznosti[smer]
  const [operace, setOperace] = useState(p.navrh?.operace ?? '')
  const [vstupy, setVstupy] = useState<Record<string, string>>(() => ({
    protistrana: p.nazev,
    ...p.navrh?.vstupy,
  }))
  const [zapamatovat, setZapamatovat] = useState(!p.navrh)
  // Platbu s návrhem stačí potvrdit; formulář se otevře, až když ho někdo chce změnit.
  const [upravuji, setUpravuji] = useState(!p.navrh)
  const [chyba, setChyba] = useState<string | null>(null)
  const [pracuji, setPracuji] = useState(false)
  const vybrana = moznosti.find((m) => m.id === operace)
  const ostatniUcty = data.ucty.filter((u) => u.ucel !== p.ucel)
  const nazevUctu = data.ucty.find((u) => u.ucel === p.ucel)?.nazev ?? p.ucel

  async function zauctuj() {
    if (!vybrana) return
    setPracuji(true)
    setChyba(null)
    try {
      const hodnoty = Object.fromEntries(
        [...vybrana.pole, ...vybrana.volitelna].map((pole) => [pole, vstupy[pole] ?? '']),
      )
      poZauctovani(
        await api<Pohyb>(`/api/banka/pohyby/${p.id}`, {
          method: 'POST',
          json: {
            operace,
            vstupy: hodnoty,
            zapamatovat: zapamatovat && !!(p.protiucet || p.vs) && operace !== 'uhrada-faktury',
          },
        }),
      )
    } catch (e) {
      setChyba((e as Error).message)
    } finally {
      setPracuji(false)
    }
  }

  return (
    <li className={`pohyb ${p.zauctovano ? 'hotovo' : ''}`}>
      <div className="pohyb-hlavicka">
        <span>{datum(p.datum)}</span>
        <strong className={p.castka > 0 ? 'prijem' : 'vydaj'}>
          {p.castka > 0 ? '+' : ''}
          {kc(p.castka)}
        </strong>
        <span className="tlumene">
          {nazevUctu}, {p.zdroj}
        </span>
      </div>
      <div className="pohyb-udaje">
        <span>{p.nazev || (p.castka > 0 ? 'Příchozí platba' : 'Odchozí platba')}</span>
        {p.protiucet && <span className="tlumene">účet {p.protiucet}</span>}
        {p.vs && <span className="tlumene">VS {p.vs}</span>}
        {p.zprava && <span className="tlumene">„{p.zprava}“</span>}
      </div>

      {p.zauctovano ? (
        <p className="uspech">
          Zaúčtováno: {p.zauctovano.nazev}
          {popisVstupu(p.zauctovano.vstupy, data)} · zápis {p.zauctovano.zapis} ·{' '}
          {p.zauctovano.zauctoval}
        </p>
      ) : p.navrh && !upravuji ? (
        <div className="pohyb-navrh">
          <p>
            <strong>
              {vybrana?.nazev ?? 'Návrh zaúčtování'}
              {popisVstupu(p.navrh.vstupy, data)}
            </strong>
            <span className="tlumene">{p.navrh.duvod}</span>
          </p>
          <div className="radek">
            <button disabled={!vybrana || pracuji} onClick={zauctuj}>
              {pracuji ? 'Účtuji…' : 'Zaúčtovat'}
            </button>
            <button className="vedlejsi" disabled={pracuji} onClick={() => setUpravuji(true)}>
              Změnit
            </button>
          </div>
          {chyba && <p className="chyba">{chyba}</p>}
        </div>
      ) : (
        <div className="pohyb-formular">
          {p.navrh && <p className="navrh">Návrh: {p.navrh.duvod}</p>}
          <label>
            Co je to za platbu
            <select value={operace} onChange={(e) => setOperace(e.target.value)}>
              <option value="">Vyberte…</option>
              {moznosti.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.nazev}
                  {m.stav === 'overit' ? ' (postup zatím nepotvrdila účetní)' : ''}
                </option>
              ))}
            </select>
          </label>
          {vybrana?.pole.map((pole) => (
            <label key={pole}>
              {pole === 'druhy_ucet'
                ? smer === 'prijem'
                  ? 'Ze kterého účtu SVJ'
                  : 'Na který účet SVJ'
                : POPIS_POLE[pole]}
              {pole === 'faktura' ? (
                <VyberFaktury
                  faktury={data.faktury}
                  castka={-p.castka}
                  value={vstupy.faktura ?? ''}
                  onChange={(v) => setVstupy({ ...vstupy, faktura: v })}
                />
              ) : pole === 'drivejsi_vlastnik' ? (
                <select
                  value={vstupy.drivejsi_vlastnik ?? ''}
                  onChange={(e) => setVstupy({ ...vstupy, drivejsi_vlastnik: e.target.value })}
                >
                  <option value="">Vyberte…</option>
                  {data.drivejsi
                    .filter((d) => !vstupy.jednotka || d.jednotka === vstupy.jednotka)
                    .map((d) => (
                      <option key={`${d.jednotka}|${d.vlastnik}`} value={d.vlastnik}>
                        {d.vlastnik} ({d.jednotka}, {d.castka > 0 ? `dluží ${kc(d.castka)}` : `přeplatek ${kc(-d.castka)}`})
                      </option>
                    ))}
                </select>
              ) : pole === 'protistrana' ? (
                <input
                  value={vstupy.protistrana ?? ''}
                  onChange={(e) => setVstupy({ ...vstupy, protistrana: e.target.value })}
                />
              ) : (
                <select
                  value={vstupy[pole] ?? ''}
                  onChange={(e) =>
                    // Určený dluh patří k jednotce; po změně jednotky neplatí.
                    setVstupy({ ...vstupy, [pole]: e.target.value, ...(pole === 'jednotka' && { dluh: '' }) })
                  }
                >
                  <option value="">Vyberte…</option>
                  {pole === 'jednotka' && operace === 'uhrada-odepsane-pohledavky'
                    ? data.odepsane.map((o) => (
                        <option key={o.jednotka} value={o.jednotka}>
                          {o.jednotka} (odepsaný dluh {kc(o.zbyva)})
                        </option>
                      ))
                    : pole === 'jednotka'
                    ? data.jednotky.map((j) => (
                        <option key={j} value={j}>
                          {j}
                        </option>
                      ))
                    : ostatniUcty.map((u) => (
                        <option key={u.ucel} value={u.ucel}>
                          {u.nazev}
                        </option>
                      ))}
                </select>
              )}
            </label>
          ))}
          {operace === 'uhrada-odepsane-pohledavky' && data.odepsane.length === 0 && (
            <p className="tlumene">
              Žádná jednotka nemá odepsaný dluh, který by zbýval zaplatit. Nedobytné dluhy se
              odepisují na stránce Dlužníci.
            </p>
          )}
          {vybrana?.volitelna.includes('dluh') && vstupy.jednotka && (
            <VyberDluhu
              rok={Number(p.datum.slice(0, 4))}
              jednotka={vstupy.jednotka}
              value={vstupy.dluh ?? ''}
              onChange={(v) => setVstupy({ ...vstupy, dluh: v })}
            />
          )}
          {(p.protiucet || p.vs) && vybrana && vybrana.pole.length > 0 && operace !== 'uhrada-faktury' && (
            <label className="zaskrtavatko">
              <input
                type="checkbox"
                checked={zapamatovat}
                onChange={(e) => setZapamatovat(e.target.checked)}
              />
              Další platby {p.protiucet ? 'z tohoto účtu' : 's tímto VS'} navrhovat stejně
            </label>
          )}
          <div className="radek">
            <button disabled={!vybrana || pracuji} onClick={zauctuj}>
              {pracuji ? 'Účtuji…' : 'Zaúčtovat'}
            </button>
            {chyba && <span className="chyba">{chyba}</span>}
          </div>
        </div>
      )}
    </li>
  )
}

function popisVstupu(vstupy: Record<string, string>, data: Banka) {
  const casti = Object.entries(vstupy).map(([k, v]) =>
    k === 'druhy_ucet'
      ? (data.ucty.find((u) => u.ucel === v)?.nazev ?? v)
      : k === 'jednotka'
        ? `jednotka ${v}`
        : k === 'faktura'
          ? `doklad FP ${v}`
          : k === 'dluh'
            ? 'na dluh, který určil vlastník'
            : v,
  )
  return casti.length ? ` (${casti.join(', ')})` : ''
}

/**
 * Na který dluh vlastník platí, když to při platbě řekl (§ 1933 OZ). Bez určení jde platba
 * na nejstarší dluh.
 */
function VyberDluhu({
  rok,
  jednotka,
  value,
  onChange,
}: {
  rok: number
  jednotka: string
  value: string
  onChange: (v: string) => void
}) {
  const [dluhy, setDluhy] = useState<DluhJednotky[] | null>(null)
  useEffect(() => {
    let platne = true
    api<DluhJednotky[]>(`/api/banka/dluhy/${rok}?${new URLSearchParams({ jednotka })}`)
      .then((d) => platne && setDluhy(d))
      .catch(() => platne && setDluhy([]))
    return () => {
      platne = false
    }
  }, [rok, jednotka])
  if (!dluhy || dluhy.length < 2) return null
  return (
    <label>
      Na který dluh vlastník platí
      <select value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">Neurčil, na nejstarší dluh</option>
        {dluhy.map((d) => (
          <option key={d.radek} value={String(d.radek)}>
            {d.popis}
            {d.splatnost ? `, splatné ${new Date(d.splatnost).toLocaleDateString('cs-CZ')}` : ''}
            {`, zbývá ${kc(d.zbyva)}`}
          </option>
        ))}
      </select>
    </label>
  )
}

function VyberFaktury({
  faktury,
  castka,
  value,
  onChange,
}: {
  faktury: OtevrenaFaktura[]
  castka: number
  value: string
  onChange: (v: string) => void
}) {
  if (faktury.length === 0)
    return (
      <span className="tlumene">
        Žádná faktura nečeká na zaplacení. Nejdřív ji zadejte na stránce{' '}
        <a href="#faktury">Faktury</a>.
      </span>
    )
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">Vyberte…</option>
      {faktury.map((f) => (
        <option key={f.cislo} value={f.cislo} disabled={f.zbyva < castka}>
          {f.dodavatel}
          {f.cislo_dodavatele ? `, faktura ${f.cislo_dodavatele}` : ''} · zbývá {kc(f.zbyva)} ·
          splatná {datum(f.splatnost)}
          {f.zbyva < castka ? ' (platba je vyšší)' : ''}
        </option>
      ))}
    </select>
  )
}
