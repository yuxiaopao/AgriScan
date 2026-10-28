import {useEffect, useState} from 'react'
export function useObjectUrl(file: Blob | null) {
  const [url, setUrl] = useState('')
  useEffect(() => {if (!file) {setUrl(''); return}; const next = URL.createObjectURL(file); setUrl(next); return () => URL.revokeObjectURL(next)}, [file])
  return url
}
export function useRoute() {
  const [route, setRoute] = useState(() => window.location.hash.slice(1) || (localStorage.getItem('agriscan-mobile-welcomed') ? 'login' : 'welcome'))
  useEffect(() => {const update = () => {setRoute(window.location.hash.slice(1) || 'home'); window.scrollTo({top: 0})}; window.addEventListener('hashchange', update); return () => window.removeEventListener('hashchange', update)}, [])
  return route
}
export function navigate(route: string) {window.location.hash = route}
export const formatTime = (value: number) => `${Math.floor(value / 60).toString().padStart(2, '0')}:${Math.floor(value % 60).toString().padStart(2, '0')}`
export const formatFrameTime = (value:number) => `${Math.floor(value/60).toString().padStart(2,'0')}:${(value%60).toFixed(2).padStart(5,'0')}`
export function confidence(value: number | null) {if (value == null) return '—'; if (value === 1) return '≈100%'; if (value > .9999) return '>99.99%'; if (value > 0 && value < .0001) return '<0.01%'; return `${(value * 100).toFixed(2)}%`}
