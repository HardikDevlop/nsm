import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react'

type Theme = 'dark' | 'light'

export interface ThemeColors {
  bg: string
  text: string
  accent: string
  card: string
  muted: string
  border: string
}

const DARK_DEFAULTS: ThemeColors = {
  bg: '#000000',
  text: '#e2e8f5',
  accent: '#FF0015',
  card: '#0f0f0f',
  muted: '#888888',
  border: '#1e1e1e',
}

const LIGHT_DEFAULTS: ThemeColors = {
  bg: '#f0f2f5',
  text: '#1a1a2e',
  accent: '#FF0015',
  card: '#ffffff',
  muted: '#666666',
  border: '#e0e0e0',
}

interface ThemeContextType {
  theme: Theme
  toggleTheme: () => void
  colors: ThemeColors
  setColor: (key: keyof ThemeColors, value: string) => void
  resetColors: () => void
  defaults: ThemeColors
}

const ThemeContext = createContext<ThemeContextType>({
  theme: 'light',
  toggleTheme: () => {},
  colors: LIGHT_DEFAULTS,
  setColor: () => {},
  resetColors: () => {},
  defaults: LIGHT_DEFAULTS,
})

function hexToRgba(hex: string, alpha: number): string {
  const r = parseInt(hex.slice(1, 3), 16)
  const g = parseInt(hex.slice(3, 5), 16)
  const b = parseInt(hex.slice(5, 7), 16)
  return `rgba(${r}, ${g}, ${b}, ${alpha})`
}

function applyCSS(colors: ThemeColors) {
  const s = document.documentElement.style
  s.setProperty('--t-bg', colors.bg)
  s.setProperty('--t-text', colors.text)
  s.setProperty('--t-accent', colors.accent)
  s.setProperty('--t-card', colors.card)
  s.setProperty('--t-muted', colors.muted)
  s.setProperty('--t-border', colors.border)
  s.setProperty('--t-card-alpha', hexToRgba(colors.card, 0.7))
  s.setProperty('--t-border-alpha', hexToRgba(colors.border, 0.8))
  s.setProperty('--t-border-light', hexToRgba(colors.border, 0.12))
  s.setProperty('--t-accent-alpha', hexToRgba(colors.accent, 0.15))
  s.setProperty('--t-accent-border', hexToRgba(colors.accent, 0.4))
  s.setProperty('--t-muted-dim', hexToRgba(colors.muted, 0.6))
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>(() => {
    const saved = localStorage.getItem('theme-mode')
    if (saved === 'dark' || saved === 'light') return saved as Theme
    return 'light'
  })

  const [colors, setColors] = useState<ThemeColors>(() => {
    try {
      const saved = localStorage.getItem('theme-colors')
      if (saved) {
        const parsed = JSON.parse(saved) as ThemeColors
        // Migrate old accent colors to new agnigate red
        if (parsed.accent === '#ff6432' || parsed.accent === '#ff3366' || parsed.accent === '#d72323') parsed.accent = '#FF0015'
        return parsed
      }
    } catch { /* ignore */ }
    return LIGHT_DEFAULTS
  })

  const defaults = theme === 'dark' ? DARK_DEFAULTS : LIGHT_DEFAULTS

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('theme-mode', theme)
  }, [theme])

  useEffect(() => {
    applyCSS(colors)
    localStorage.setItem('theme-colors', JSON.stringify(colors))
  }, [colors])

  const toggleTheme = useCallback(() => {
    setTheme(t => {
      const next = t === 'dark' ? 'light' : 'dark'
      const nextDefaults = next === 'dark' ? DARK_DEFAULTS : LIGHT_DEFAULTS
      setColors(prev => {
        // If current colors are the other theme's defaults, switch to new defaults
        const curDefaults = t === 'dark' ? DARK_DEFAULTS : LIGHT_DEFAULTS
        const isDefault = (Object.keys(curDefaults) as (keyof ThemeColors)[]).every(
          k => prev[k] === curDefaults[k]
        )
        return isDefault ? nextDefaults : prev
      })
      return next
    })
  }, [])

  const setColor = useCallback((key: keyof ThemeColors, value: string) => {
    setColors(prev => ({ ...prev, [key]: value }))
  }, [])

  const resetColors = useCallback(() => {
    setColors(theme === 'dark' ? DARK_DEFAULTS : LIGHT_DEFAULTS)
  }, [theme])

  return (
    <ThemeContext.Provider value={{ theme, toggleTheme, colors, setColor, resetColors, defaults }}>
      {children}
    </ThemeContext.Provider>
  )
}

export function useTheme() {
  return useContext(ThemeContext)
}

export { hexToRgba, DARK_DEFAULTS, LIGHT_DEFAULTS }
