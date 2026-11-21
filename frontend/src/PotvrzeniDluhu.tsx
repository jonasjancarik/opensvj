import type { Data, Jednotka } from './Dluznici'
import { datum, SeznamPolozek } from './Dluznici'
import { kc } from './penize'
import { Rozeslat } from './Rozeslat'
import './tisk.css'

const DNI_STARY_VYPIS = 7

function pohybu(n: number) {
  return n === 1 ? '1 pohyb' : n < 5 ? `${n} pohyby` : `${n} pohybů`
}

/**
 * Potvrzení o dluzích při převodu jednotky (§ 1186 odst. 3 občanského zákoníku).
 * Na kupujícího přejdou jen dluhy, které z potvrzení zjistit mohl, proto musí být
 * účetnictví aktuální.
 */
export function PotvrzeniDluhu({ data, jednotka: j, zpet }: { data: Data; jednotka: Jednotka; zpet: () => void }) {
  const splatne = j.polozky.filter((p) => p.po_splatnosti)
  const nesplatne = j.polozky.filter((p) => !p.po_splatnosti)
  const stariVypisu = data.posledni_vypis
    ? (new Date(data.dnes).getTime() - new Date(data.posledni_vypis).getTime()) / 86_400_000
    : null

  return (
    <>
      <div className="radek neni-v-tisku">
        <button className="vedlejsi" onClick={zpet}>
          Zpět na dlužníky
        </button>
        <button onClick={() => window.print()}>Vytisknout</button>
      </div>
      <div className="neni-v-tisku">
        {data.nezauctovane_pohyby > 0 && (
          <p className="upozorneni">
            Na stránce <a href="#banka">Banka</a> zbývá zaúčtovat {pohybu(data.nezauctovane_pohyby)}.
            Zaúčtujte je dřív, než potvrzení vydáte: kdyby v potvrzení byl dluh nižší, než
            ve skutečnosti je, na kupujícího přejde jen částka z potvrzení a zbytek je nutné
            vymáhat po prodávajícím.
          </p>
        )}
        {stariVypisu === null ? (
          <p className="upozorneni">Aplikace zatím nemá žádný bankovní výpis.</p>
        ) : stariVypisu > DNI_STARY_VYPIS ? (
          <p className="upozorneni">
            Poslední nahraný pohyb na účtu je z {datum(data.posledni_vypis!)}. Před vydáním
            potvrzení nahrajte aktuální výpis, ať jsou v něm i nejnovější platby.
          </p>
        ) : null}
        <p className="tlumene">
          Potvrzení dostává prodávající vlastník. Kupujícímu ho společenství může vydat jen
          s jeho souhlasem. Výdaje za vydání (např. faktura účetní) může společenství přeúčtovat
          prodávajícímu, ale ne víc, než skutečně stály.
        </p>
        <Rozeslat druh="potvrzeni" klic={`potvrzeni:${j.jednotka}`} nazev="Potvrzení o dluzích vlastníka jednotky" />
      </div>

      <article className="upominka" data-jednotka={j.jednotka}>
        <p>
          <strong>{data.svj}</strong>
          {data.ico && <>, IČ {data.ico}</>}
          {data.sidlo && (
            <>
              <br />
              {data.sidlo}
            </>
          )}
        </p>
        <h2>Potvrzení o dluzích vlastníka jednotky {j.jednotka}</h2>
        <p className="tlumene">podle § 1186 odst. 3 občanského zákoníku</p>
        {j.vlastnici.length > 0 && (
          <p>
            Vlastník jednotky: {j.vlastnici.map((v) => v.jmeno).join(', ')}
          </p>
        )}
        {splatne.length === 0 ? (
          <p>
            Společenství potvrzuje, že k {datum(data.dnes)} u jednotky č. {j.jednotka} neeviduje
            žádné splatné dluhy vlastníka na příspěvcích na správu domu a pozemku, na zálohách na
            služby ani na nedoplatcích z jejich vyúčtování.
          </p>
        ) : (
          <>
            <p>
              Společenství potvrzuje, že k {datum(data.dnes)} u jednotky č. {j.jednotka} eviduje
              tyto splatné dluhy vlastníka na příspěvcích na správu domu a pozemku, na zálohách
              na služby a na nedoplatcích z jejich vyúčtování:
            </p>
            <SeznamPolozek polozky={splatne} />
            <p>
              <strong>Splatné dluhy celkem: {kc(j.po_splatnosti)}</strong>
            </p>
          </>
        )}
        {nesplatne.length > 0 && (
          <p>
            Pro úplnost: ještě nesplatné jsou{' '}
            {nesplatne
              .map((p) => `${p.popis.toLowerCase()} se splatností ${datum(p.splatnost!)}`)
              .join(', ')}
            , celkem {kc(j.nesplatne)}.
          </p>
        )}
        {j.preplatek > 0 && <p>Vlastník má u společenství přeplatek {kc(j.preplatek)}.</p>}
        <p>
          Při převodu jednotky se zálohy nevypořádávají (§ 1186 odst. 1 občanského zákoníku).
          Potvrzení nezahrnuje výsledek vyúčtování služeb a záloh na správu domu za období, které
          ještě nebylo vyúčtováno.
        </p>
        <p className="vpravo">Dne {datum(data.dnes)}</p>
        <div className="podpisy">
          <p>
            Za výbor společenství
            <br />
            <span className="podpis">jméno, funkce a podpis</span>
          </p>
          <p>
            <br />
            <span className="podpis">jméno, funkce a podpis</span>
          </p>
        </div>
      </article>
    </>
  )
}
