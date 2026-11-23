/**
 * Potvrzovací okno místo `window.confirm`. Vrací true, když uživatel akci potvrdí.
 * Okno je nativní <dialog>, takže Esc i zaměření tlačítek fungují samy.
 */
export function potvrdit({
  nadpis,
  text,
  ano,
  ne = 'Zpět',
}: {
  nadpis: string
  text: string
  ano: string
  ne?: string
}): Promise<boolean> {
  return new Promise((hotovo) => {
    const okno = document.createElement('dialog')
    okno.className = 'potvrzeni'
    const h = document.createElement('h2')
    h.textContent = nadpis
    const p = document.createElement('p')
    p.textContent = text
    const radek = document.createElement('form')
    radek.method = 'dialog'
    radek.className = 'radek potvrzeni-tlacitka'
    const zpet = document.createElement('button')
    zpet.className = 'vedlejsi'
    zpet.value = 'ne'
    zpet.textContent = ne
    const ok = document.createElement('button')
    ok.value = 'ano'
    ok.textContent = ano
    radek.append(zpet, ok)
    okno.append(h, p, radek)
    okno.addEventListener('close', () => {
      hotovo(okno.returnValue === 'ano')
      okno.remove()
    })
    okno.addEventListener('click', (e) => {
      if (e.target === okno) okno.close('ne')
    })
    document.body.append(okno)
    okno.showModal()
    ok.focus()
  })
}

/**
 * Potvrzení, ke kterému uživatel musí napsat důvod (zapíše se do historie změn).
 * Vrací napsaný důvod, nebo null, když uživatel akci nepotvrdí.
 */
export function potvrditSDuvodem({
  nadpis,
  text,
  ano,
  popisDuvodu,
  ne = 'Zpět',
}: {
  nadpis: string
  text: string
  ano: string
  popisDuvodu: string
  ne?: string
}): Promise<string | null> {
  return new Promise((hotovo) => {
    const okno = document.createElement('dialog')
    okno.className = 'potvrzeni'
    const h = document.createElement('h2')
    h.textContent = nadpis
    const p = document.createElement('p')
    p.textContent = text
    const formular = document.createElement('form')
    formular.method = 'dialog'
    const popisek = document.createElement('label')
    popisek.className = 'potvrzeni-duvod'
    popisek.textContent = popisDuvodu
    const pole = document.createElement('textarea')
    pole.rows = 3
    pole.maxLength = 500
    pole.required = true
    popisek.append(pole)
    const radek = document.createElement('div')
    radek.className = 'radek potvrzeni-tlacitka'
    const zpet = document.createElement('button')
    zpet.type = 'button'
    zpet.className = 'vedlejsi'
    zpet.textContent = ne
    zpet.addEventListener('click', () => okno.close('ne'))
    const ok = document.createElement('button')
    ok.value = 'ano'
    ok.textContent = ano
    ok.disabled = true
    pole.addEventListener('input', () => (ok.disabled = !pole.value.trim()))
    radek.append(zpet, ok)
    formular.append(popisek, radek)
    okno.append(h, p, formular)
    okno.addEventListener('close', () => {
      hotovo(okno.returnValue === 'ano' && pole.value.trim() ? pole.value.trim() : null)
      okno.remove()
    })
    okno.addEventListener('click', (e) => {
      if (e.target === okno) okno.close('ne')
    })
    document.body.append(okno)
    okno.showModal()
    pole.focus()
  })
}
