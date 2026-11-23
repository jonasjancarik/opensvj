// Prezentační web OpenSVJ: seznam toho, co aplikace umí, a rok po měsících.

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

seznamSchopnosti()
rokPoMesicich()
kopirovani()
prichody()
