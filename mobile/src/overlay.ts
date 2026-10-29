const locks = new Set<symbol>()
let previousOverflow = ''

export function lockBodyScroll() {
  const token = Symbol('overlay')
  if (!locks.size) previousOverflow = document.body.style.overflow
  locks.add(token)
  document.body.style.overflow = 'hidden'
  return () => {locks.delete(token); if (!locks.size) document.body.style.overflow = previousOverflow}
}
