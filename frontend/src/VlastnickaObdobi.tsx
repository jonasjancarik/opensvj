import { kc } from './penize'
import type { Adresat } from './Vlastnici'

/** Část vyúčtování jednotky za dobu, kdy ji vlastnil jeden vlastník. */
export type ObdobiVlastnika = {
  od: string
  do: string
  mesice: number[]
  soucasny: boolean
  osoby: number[]
  vlastnici: Adresat[]
  zalohy: number
  naklady: number
  rozdil: number
  polozky: { kod: string; naklady: number; zalohy: number }[]
}

const datum = (d: string) => new Date(d).toLocaleDateString('cs-CZ')

const MESICE = [
  'leden',
  'únor',
  'březen',
  'duben',
  'květen',
  'červen',
  'červenec',
  'srpen',
  'září',
  'říjen',
  'listopad',
  'prosinec',
]

/** „leden až červen“, případně více úseků oddělených čárkou. */
function mesiceText(mesice: number[]) {
  const useky: [number, number][] = []
  for (const m of mesice) {
    const posledni = useky[useky.length - 1]
    if (posledni && posledni[1] === m - 1) posledni[1] = m
    else useky.push([m, m])
  }
  return useky.map(([a, b]) => (a === b ? MESICE[a - 1] : `${MESICE[a - 1]} až ${MESICE[b - 1]}`)).join(', ')
}

/** Vysvětlení na začátku vyúčtování, které se týká jen části roku. */
export function UvodObdobi({ o, jednotka, rok }: { o: ObdobiVlastnika; jednotka: string; rok: number }) {
  return (
    <p>
      Jednotka {jednotka} během roku {rok} změnila vlastníka. Toto vyúčtování je za dobu, kdy jste ji vlastnili
      {o.soucasny ? ` od ${datum(o.od)}` : ` do ${datum(o.do)}`}: obsahuje zálohy předepsané za {mesiceText(o.mesice)}{' '}
      {rok} a odpovídající část nákladů jednotky.
    </p>
  )
}

/** Rozpis jednotky po vlastnících v rozbaleném řádku tabulky jednotek. */
export function ObdobiVRozpisu({ obdobi }: { obdobi: ObdobiVlastnika[] }) {
  if (obdobi.length === 0) return null
  return (
    <>
      <p className="tlumene">Jednotka v roce změnila vlastníka, každý dostane vyúčtování za své měsíce:</p>
      <ul>
        {obdobi.map((o) => (
          <li key={o.od}>
            <span>
              {o.vlastnici.map((v) => v.jmeno).join(', ') || 'Vlastník není zapsaný'}
              <span className="tlumene"> ({mesiceText(o.mesice)})</span>
            </span>
            <span>
              {o.rozdil > 0 ? `nedoplatek ${kc(o.rozdil)}` : o.rozdil < 0 ? `přeplatek ${kc(-o.rozdil)}` : 'vyrovnáno'}
            </span>
          </li>
        ))}
      </ul>
    </>
  )
}
