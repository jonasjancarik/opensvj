// Prezentační web OpenSVJ: seznam toho, co aplikace umí, a drobné pohyby.

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
    '#umi-hledat, #umi-polozky li, .umi-nahled, .pole h2, .pole > p, .platba, .dlazdice, .zaver-text > *, .zaver-okno, .pata > *',
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
kopirovani()
prichody()
