import {useEffect, useLayoutEffect, useRef, useState} from 'react'
export function useObjectUrl(file: Blob | null) {
  const [url, setUrl] = useState('')
  useEffect(() => {if (!file) {setUrl(''); return}; const next = URL.createObjectURL(file); setUrl(next); return () => URL.revokeObjectURL(next)}, [file])
  return url
}
const navigationKey = 'agriscanMobileIndex'
let resetScroll = false
const pageNames = new Set(['welcome','login','register','forgot-password','home','detect','records','profile','plots','knowledge','settings','models','tasks'])
function canonicalRoute(value: string) {
  const [page, mode] = value.split('/')
  if (!pageNames.has(page)) return 'home'
  if (page === 'detect') return `detect/${['image','video','camera'].includes(mode) ? mode : 'image'}`
  return page
}
export function useRoute() {
  const [route, setRoute] = useState(() => {
    const hash = window.location.hash.slice(1)
    return hash ? canonicalRoute(hash) : localStorage.getItem('agriscan-mobile-welcomed') ? 'login' : 'welcome'
  })
  const positions = useRef(new Map<string, number>())
  const restorePosition = useRef(0)
  useEffect(() => {
    let current = route, index = 0
    const initialState={...window.history.state,[navigationKey]:0}
    delete initialState.agriscanMobileAssistant
    window.history.replaceState(initialState, '', `#${current}`)
    const update = () => {
      const hash = window.location.hash.slice(1)
      if (hash === 'assistant') {
        window.history.replaceState({...window.history.state, [navigationKey]: index}, '', `#${current}`)
        window.dispatchEvent(new Event('agriscan-mobile-assistant-open')); return
      }
      const next = canonicalRoute(hash || 'home')
      if (resetScroll) {positions.current.clear();restorePosition.current=0;resetScroll=false}
      else positions.current.set(current, window.scrollY)
      if (next === current) {if(hash!==next)window.history.replaceState({...window.history.state,[navigationKey]:index},'',`#${next}`);return}
      const previousIndex = window.history.state?.[navigationKey]
      index = typeof previousIndex === 'number' ? previousIndex : index + 1
      window.history.replaceState({...window.history.state, [navigationKey]: index}, '', `#${next}`)
      restorePosition.current = positions.current.get(next) ?? 0
      current = next; setRoute(next)
    }
    window.addEventListener('hashchange', update)
    return () => window.removeEventListener('hashchange', update)
    // This listener owns the route cursor for the lifetime of the application.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  useLayoutEffect(() => {window.scrollTo({top: restorePosition.current, behavior: 'instant'})}, [route])
  return route
}
export function navigate(route: string) {
  if (route === 'assistant') {window.dispatchEvent(new Event('agriscan-mobile-assistant-open')); return}
  window.location.hash = canonicalRoute(route)
}
export function replaceRoute(route: string, reset = false) {
  const state = {...window.history.state, ...(reset ? {[navigationKey]: 0} : {})}
  if(reset){delete state.agriscanMobileAssistant;resetScroll=true}
  window.history.replaceState(state, '', `#${canonicalRoute(route)}`)
  window.dispatchEvent(new HashChangeEvent('hashchange'))
}
export function goBack(fallback = 'home') {
  if ((window.history.state?.[navigationKey] ?? 0) > 0) window.history.back()
  else replaceRoute(fallback)
}
export const formatTime = (value: number) => `${Math.floor(value / 60).toString().padStart(2, '0')}:${Math.floor(value % 60).toString().padStart(2, '0')}`
export const formatFrameTime = (value:number) => `${Math.floor(value/60).toString().padStart(2,'0')}:${(value%60).toFixed(2).padStart(5,'0')}`
export function confidence(value: number | null) {if (value == null) return '—'; if (value === 1) return '≈100%'; if (value > .9999) return '>99.99%'; if (value > 0 && value < .0001) return '<0.01%'; return `${(value * 100).toFixed(2)}%`}
