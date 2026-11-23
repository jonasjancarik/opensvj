// Prezentační web OpenSVJ: dům s okny, seznam toho, co aplikace umí, a rok po měsících.
// Čísla odpovídají ukázkovému SVJ Ukázková 12 (backend/tests/naplneni.py).

const kc = (halire) =>
  (halire / 100).toLocaleString('cs-CZ', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' Kč'

// ---------- Dům: každé okno je jedna jednotka ----------
const JEDNOTKY = [
  ['1001/1', 'Jan Novák a Marie Nováková', 325000],
  ['1001/2', 'Petr Dvořák', -250000],
  ['1001/3', 'Alena Králová', 0],
  ['1001/4', 'Tomáš Procházka', 1248800],
  ['1001/5', 'Lucie Veselá a Martin Veselý', 0],
  ['1001/6', 'Hana Marková', 0],
  ['1001/7', 'Jiří Kučera', 1286000],
  ['1001/8', 'Eva Svobodová', 1416700],
  ['1001/9', 'Pavel Černý a Jana Černá', 1508800],
  ['1001/10', 'Ondřej Beneš', 8576000],
  ['1001/11', 'Kavárna Na rohu s.r.o.', 1066000],
  ['1001/12', 'Zuzana Horáková', 1141200],
].map(([oznaceni, vlastnik, dluh]) => ({ oznaceni, vlastnik, dluh, puvodni: dluh }))

function oknoSlovy(n) {
  return n === 1 ? 'okno' : n >= 2 && n <= 4 ? 'okna' : 'oken'
}

function postavDum() {
  const misto = document.getElementById('dum')
  if (!misto) return
  const SL = 3, RX = 44, RY = 50, OS = 20, OV = 30, OKRAJ = 20, STRECHA = 36
  const pater = Math.ceil(JEDNOTKY.length / SL)
  const fasada = SL * RX + 20 - (RX - OS)
  const sirka = fasada + 2 * OKRAJ
  const zacatek = STRECHA + 16
  const prizemi = zacatek + pater * RY
  const vyska = prizemi + 62
  const stred = sirka / 2
  let svg = `<svg viewBox="0 0 ${sirka} ${vyska}" role="group" aria-label="Dům s dvanácti jednotkami">`
  svg += `<path class="d-linka" d="M${stred - 26} ${STRECHA - 10} Q${stred} ${STRECHA - 36} ${stred + 26} ${STRECHA - 10}Z"/>`
  svg += `<rect class="d-linka" x="${OKRAJ - 8}" y="${STRECHA - 10}" width="${fasada + 16}" height="10" rx="2"/>`
  svg += `<rect class="d-fasada" x="${OKRAJ}" y="${STRECHA}" width="${fasada}" height="${vyska - STRECHA - 4}"/>`
  for (let p = 1; p <= pater; p++)
    svg += `<rect class="d-linka" opacity=".7" x="${OKRAJ}" y="${zacatek + p * RY - 9}" width="${fasada}" height="2.5"/>`
  JEDNOTKY.forEach((j, i) => {
    const x = OKRAJ + 10 + (i % SL) * RX
    const y = zacatek + (pater - 1 - Math.floor(i / SL)) * RY
    svg +=
      `<g class="d-jednotka" data-i="${i}" tabindex="0" role="button">` +
      `<rect class="d-okno" x="${x}" y="${y}" width="${OS}" height="${OV}" rx="1.5"/>` +
      `<path class="d-pricka" d="M${x + OS / 2} ${y}v${OV}M${x} ${y + 12}h${OS}"/>` +
      `<rect class="d-linka" x="${x - 2}" y="${y + OV}" width="${OS + 4}" height="3" rx="1"/>` +
      (j.dluh < 0
        ? `<rect class="d-truhlik" x="${x}" y="${y + OV - 4}" width="${OS}" height="4" rx="1"/>` +
          [4, 10, 16].map((dx, k) => `<circle class="d-kvet" cx="${x + dx}" cy="${y + OV - (k === 1 ? 6 : 5)}" r="2"/>`).join('')
        : '') +
      `<rect class="d-vyber" x="${x - 4}" y="${y - 4}" width="${OS + 8}" height="${OV + 9}" rx="3"/>` +
      `<rect class="d-terc" x="${x - 10}" y="${y - 8}" width="${OS + 20}" height="${OV + 18}"/>` +
      `</g>`
  })
  svg += `<path class="d-dvere" d="M${stred - 16} ${vyska - 4}v-38a16 16 0 0 1 32 0v38Z"/>`
  svg += `<circle class="d-klika" cx="${stred + 11}" cy="${vyska - 22}" r="1.6"/>`
  svg += `<rect class="d-zem" x="${OKRAJ - 10}" y="${vyska - 4}" width="${fasada + 20}" height="3" rx="1.5"/></svg>`
  misto.innerHTML = svg

  const okna = [...misto.querySelectorAll('.d-jednotka')]
  const el = (id) => document.getElementById(id)
  let vybrana = 7

  function prekresli() {
    const sviti = JEDNOTKY.filter((j) => j.dluh <= 0).length
    const dluh = JEDNOTKY.reduce((s, j) => s + Math.max(j.dluh, 0), 0)
    el('dum-sviti').textContent =
      sviti === JEDNOTKY.length ? 'Svítí celý dům.' : `${sviti === 1 ? 'Svítí' : 'Svítí'} ${sviti} z 12 oken.`
    el('dum-dluh').textContent = dluh ? `Po splatnosti je ${kc(dluh)}.` : 'Nikdo nic nedluží.'
    okna.forEach((o, i) => {
      const j = JEDNOTKY[i]
      o.classList.toggle('sviti', j.dluh <= 0)
      o.classList.toggle('vybrana', i === vybrana)
      o.setAttribute(
        'aria-label',
        `Jednotka ${j.oznaceni}, ${j.dluh > 0 ? 'dluží ' + kc(j.dluh) : j.dluh < 0 ? 'přeplatek ' + kc(-j.dluh) : 'má zaplaceno'}`,
      )
    })
    const j = JEDNOTKY[vybrana]
    el('j-oznaceni').textContent = `Jednotka ${j.oznaceni}`
    el('j-vlastnik').textContent = j.vlastnik
    const stav = el('j-stav')
    stav.textContent = j.dluh > 0 ? `dluží ${kc(j.dluh)}` : j.dluh < 0 ? `přeplatek ${kc(-j.dluh)}` : 'má zaplaceno'
    stav.classList.toggle('ok', j.dluh <= 0)
    const tl = el('j-zauctovat')
    tl.disabled = j.dluh <= 0
    tl.textContent = j.dluh > 0 ? 'Zaúčtovat platbu' : 'Zaúčtováno'
    el('dum-znovu').hidden = JEDNOTKY.every((x) => x.dluh === x.puvodni)
  }

  okna.forEach((o, i) => {
    const vyber = () => {
      vybrana = i
      prekresli()
    }
    o.addEventListener('click', vyber)
    o.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault()
        vyber()
      }
    })
  })
  el('j-zauctovat').addEventListener('click', () => {
    JEDNOTKY[vybrana].dluh = 0
    // Po zaúčtování nabídne další jednotku, která ještě dluží.
    const dalsi = JEDNOTKY.findIndex((j) => j.dluh > 0)
    prekresli()
    if (dalsi >= 0)
      setTimeout(() => {
        vybrana = dalsi
        prekresli()
      }, 900)
  })
  el('dum-znovu').addEventListener('click', () => {
    JEDNOTKY.forEach((j) => (j.dluh = j.puvodni))
    vybrana = 7
    prekresli()
  })
  prekresli()
}

// ---------- Co aplikace umí: seznam s hledáním a náhledem ----------
function seznamSchopnosti() {
  const seznam = document.getElementById('umi-polozky')
  const hledat = document.getElementById('umi-hledat')
  const nahled = document.getElementById('umi-nahled')
  const sekce = nahled?.parentElement
  if (!seznam || !hledat || !nahled || !sekce) return
  const polozky = [...seznam.children]
  const uzky = window.matchMedia('(max-width: 860px)')
  const bezDiakritiky = (t) => t.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()

  function vyber(li) {
    polozky.forEach((p) => {
      p.classList.toggle('aktivni', p === li)
      p.querySelector('button').setAttribute('aria-expanded', String(p === li))
    })
    if (!li) return
    nahled.querySelectorAll('img').forEach((img) => {
      const aktivni = img.dataset.obrazek === li.dataset.obrazek
      if (aktivni) img.loading = 'eager'
      img.classList.toggle('aktivni', aktivni)
    })
    // Na telefonu se náhled otevře přímo pod vybraným řádkem.
    if (uzky.matches) li.appendChild(nahled)
    else if (nahled.parentElement !== sekce) sekce.appendChild(nahled)
  }

  polozky.forEach((li) => {
    const tl = li.querySelector('button')
    tl.addEventListener('click', () => vyber(li))
    tl.addEventListener('mouseenter', () => !uzky.matches && vyber(li))
    tl.addEventListener('focus', () => !uzky.matches && vyber(li))
  })
  hledat.addEventListener('input', () => {
    const q = bezDiakritiky(hledat.value.trim())
    const videt = polozky.filter((li) => {
      const sedi = !q || bezDiakritiky(li.textContent).includes(q)
      li.hidden = !sedi
      return sedi
    })
    document.getElementById('umi-nic').hidden = videt.length > 0
    if (videt.length && !videt.includes(seznam.querySelector('.aktivni'))) vyber(videt[0])
  })
  hledat.addEventListener('keydown', (e) => {
    if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return
    e.preventDefault()
    const videt = polozky.filter((li) => !li.hidden)
    const i = videt.indexOf(seznam.querySelector('.aktivni'))
    const dalsi = videt[(i + (e.key === 'ArrowDown' ? 1 : -1) + videt.length) % videt.length]
    if (dalsi) vyber(dalsi)
  })
  uzky.addEventListener('change', () => vyber(seznam.querySelector('.aktivni') ?? polozky[0]))
  vyber(polozky[0])
}

// ---------- Rok po měsících ----------
function rokPoMesicich() {
  const misto = document.getElementById('rok-mesice')
  const sekce = document.getElementById('rok')
  if (!misto || !sekce) return
  const NAZVY = ['leden', 'únor', 'březen', 'duben', 'květen', 'červen', 'červenec', 'srpen', 'září', 'říjen', 'listopad', 'prosinec']
  // Ukázkový předpis platí od března; leden a únor jsou bez předpisu.
  const mesice = NAZVY.map((nazev, i) => {
    const b = document.createElement('button')
    b.type = 'button'
    b.className = 'mesic' + (i >= 2 && i <= 10 ? ' zauctovano' : '')
    b.disabled = i !== 11
    b.setAttribute('aria-label', i < 2 ? `${nazev}: bez předpisu` : `${nazev}: zaúčtováno`)
    misto.appendChild(b)
    return b
  })
  const prosinec = mesice[11]
  function nastav(hotovo) {
    sekce.classList.toggle('hotovo', hotovo)
    prosinec.classList.toggle('zauctovano', hotovo)
    prosinec.classList.toggle('lze', !hotovo)
    prosinec.classList.toggle('posledni', hotovo)
    prosinec.setAttribute('aria-label', hotovo ? 'prosinec: zaúčtováno, vrátit zpět' : 'Zaúčtovat prosinec')
    document.getElementById('rok-pocet').textContent = hotovo ? '10' : '9'
    document.getElementById('rok-nadpis').innerHTML = hotovo
      ? 'Rok je <span id="rok-slovo">předepsaný</span>'
      : 'Zbývá <span id="rok-slovo">prosinec</span>'
  }
  prosinec.addEventListener('click', () => nastav(!sekce.classList.contains('hotovo')))
  nastav(false)
}

// ---------- Kopírování příkazů ----------
function kopirovani() {
  const tl = document.getElementById('kopirovat')
  const prikazy = document.getElementById('prikazy')
  if (!tl || !prikazy) return
  if (!navigator.clipboard) {
    tl.hidden = true
    return
  }
  tl.addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(prikazy.textContent)
      tl.textContent = 'Zkopírováno'
    } catch {
      tl.textContent = 'Nejde zkopírovat'
    }
    setTimeout(() => (tl.textContent = 'Zkopírovat'), 1800)
  })
}

// ---------- Příchod částí při posunu ----------
function prichody() {
  const casti = document.querySelectorAll(
    '#umi-hledat, #umi-polozky li, .umi-nahled, .rok-text > *, .rok-pruh, .pole h2, .pole > p, .platba, .dlazdice, .zaver-text > *, .zaver-okno, .pata > *',
  )
  if (!('IntersectionObserver' in window)) return
  const pozorovatel = new IntersectionObserver(
    (zaznamy) => {
      zaznamy.forEach((z) => {
        if (!z.isIntersecting) return
        z.target.classList.add('je-tu')
        pozorovatel.unobserve(z.target)
      })
    },
    { rootMargin: '0px 0px -8% 0px' },
  )
  casti.forEach((c) => {
    const sourozenci = [...c.parentElement.children].filter((s) => s.matches?.('*'))
    c.style.setProperty('--zpozdeni', `${Math.min(sourozenci.indexOf(c), 8) * 0.07}s`)
    c.classList.add('prijde')
    pozorovatel.observe(c)
  })
}

postavDum()
seznamSchopnosti()
rokPoMesicich()
kopirovani()
prichody()
