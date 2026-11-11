import {createContext, useContext, useLayoutEffect, useState, type ReactNode} from 'react'
import {cropThemes, getCropTheme, type CropTheme} from './cropThemes'

const storageKey = 'agriscan-crop-theme'
const initialCrop = () => {
  try {const saved = localStorage.getItem(storageKey); if (saved && getCropTheme(saved)) return saved} catch { /* Preferences are optional in private browsing. */ }
  return '番茄'
}
const CropThemeContext = createContext<{crop: string; theme: CropTheme; setCrop: (crop: string) => void} | null>(null)

export function CropThemeProvider({children}: {children: ReactNode}) {
  const [crop, setCrop] = useState(initialCrop)
  const theme = getCropTheme(crop) ?? cropThemes[0]
  useLayoutEffect(() => {
    const root = document.documentElement
    root.dataset.cropTheme = theme.id
    const colors = {accent: theme.accent, dark: theme.dark, soft: theme.soft, canvas: theme.canvas, glow: theme.glow}
    for (const [name, color] of Object.entries(colors)) root.style.setProperty(`--crop-${name}`, color)
    try {localStorage.setItem(storageKey, crop)} catch { /* Continue switching even when storage is unavailable. */ }
  }, [crop, theme])
  return <CropThemeContext.Provider value={{crop, theme, setCrop}}>{children}</CropThemeContext.Provider>
}

export function useCropTheme() {
  const value = useContext(CropThemeContext)
  if (!value) throw new Error('Crop theme requires CropThemeProvider')
  return value
}
