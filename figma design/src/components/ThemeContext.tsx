import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react'
import { useBranding } from './BrandingContext'

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
  bg: '#0b1220',
  text: '#e6edf7',
  accent: '#3b82f6',
  card: '#111c2e',
  muted: '#94a3b8',
  border: '#263750',
}

const LIGHT_DEFAULTS: ThemeColors = {
  bg: '#f6f3ed',
  text: '#172033',
  accent: '#3b82f6',
  card: '#fcfaf7',
  muted: '#64748b',
  border: '#ded8ce',
}

interface ThemeContextType {
  theme: Theme
  toggleTheme: () => void
  colors: ThemeColors
  setColor: (key: keyof ThemeColors, value: string) => void
  resetColors: () => void
  defaults: ThemeColors
  fontScale: number
  setFontScale: (value: number) => void
  fontFamily: string
  setFontFamily: (value: string) => void
}

type ThemePalettes = Record<Theme, ThemeColors>

const ThemeContext = createContext<ThemeContextType>({
  theme: 'light',
  toggleTheme: () => {},
  colors: LIGHT_DEFAULTS,
  setColor: () => {},
  resetColors: () => {},
  defaults: LIGHT_DEFAULTS,
  fontScale: 1,
  setFontScale: () => {},
  fontFamily: 'Josefin Sans',
  setFontFamily: () => {},
})

function hexToRgba(hex: string, alpha: number): string {
  const r = parseInt(hex.slice(1, 3), 16)
  const g = parseInt(hex.slice(3, 5), 16)
  const b = parseInt(hex.slice(5, 7), 16)
  return `rgba(${r}, ${g}, ${b}, ${alpha})`
}

function applyCSS(colors: ThemeColors, theme: Theme) {
  const s = document.documentElement.style
  const fallback = theme === 'dark' ? DARK_DEFAULTS : LIGHT_DEFAULTS
  // Older builds persisted the forced-white typography override. Repair that
  // value when switching to light mode instead of requiring users to clear
  // local storage manually.
  const text = theme === 'light' && (colors.text || '').toLowerCase() === '#ffffff' ? fallback.text : (colors.text || fallback.text)
  const muted = theme === 'light' && (colors.muted || '').toLowerCase() === '#ffffff' ? fallback.muted : (colors.muted || fallback.muted)
  s.setProperty('--t-bg', colors.bg)
  // Derive typography from the active palette. Keeping this token tied to the
  // selected theme prevents light mode from inheriting dark-mode white text.
  s.setProperty('--t-text', text)
  s.setProperty('--t-accent', colors.accent)
  s.setProperty('--t-card', colors.card)
  s.setProperty('--t-muted', muted)
  s.setProperty('--t-border', colors.border)
  s.setProperty('--t-card-alpha', hexToRgba(colors.card, 0.7))
  s.setProperty('--t-border-alpha', hexToRgba(colors.border, 0.8))
  s.setProperty('--t-border-light', hexToRgba(colors.border, 0.12))
  s.setProperty('--t-accent-alpha', hexToRgba(colors.accent, 0.15))
  s.setProperty('--t-accent-border', hexToRgba(colors.accent, 0.4))
  s.setProperty('--t-muted-dim', hexToRgba(colors.muted, 0.6))
  s.setProperty('--t-surface', colors.card)
  s.setProperty('--t-surface-text', text)
  const secondary = theme === 'light' ? '#475569' : muted
  const disabled = theme === 'light' ? '#64748b' : hexToRgba(muted, 0.7)
  s.setProperty('--t-text-secondary', secondary)
  s.setProperty('--t-text-disabled', disabled)
  s.setProperty('--t-border-strong', colors.border)
  s.setProperty('--t-table-header', theme === 'light' ? '#e8eef5' : colors.card)
  s.setProperty('--t-table-row', theme === 'light' ? colors.card : colors.card)
  s.setProperty('--t-table-row-hover', theme === 'light' ? '#f3eee6' : hexToRgba(colors.accent, 0.08))
  s.setProperty('--t-tooltip-bg', colors.card)
  s.setProperty('--t-surface-hover', hexToRgba(colors.accent, 0.08))
  s.setProperty('--t-surface-active', hexToRgba(colors.accent, 0.15))
  s.setProperty('--t-input-bg', theme === 'light' ? colors.card : colors.card)
  s.setProperty('--t-input-border', colors.border)
  s.setProperty('--t-sidebar-bg', colors.card)
  s.setProperty('--t-header-bg', colors.card)
  s.setProperty('--t-overlay', 'rgba(0, 0, 0, 0.4)')
  s.setProperty('--t-divider', colors.border)
  s.setProperty('--t-accent-hover', colors.accent)
  s.setProperty('--t-accent-soft', hexToRgba(colors.accent, 0.15))
  s.setProperty('--t-success', '#00ff88')
  s.setProperty('--t-warning', '#ffb000')
  s.setProperty('--t-danger', '#ff0015')
  s.setProperty('--t-info', '#00d4ff')
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const { allowed_themes } = useBranding()
  const [theme, setTheme] = useState<Theme>(() => {
    const saved = localStorage.getItem('theme-mode')
    if (saved === 'dark' || saved === 'light') return saved as Theme
    return 'light'
  })

  const [palettes, setPalettes] = useState<ThemePalettes>(() => {
    try {
      // Versioned key ensures old hard-coded cyan/red palettes cannot
      // override the current accessible defaults.
      const saved = localStorage.getItem('theme-colors-v2')
      if (saved) {
        const parsed = JSON.parse(saved) as ThemeColors | Partial<ThemePalettes>
        const migrate = (value: ThemeColors, fallback: ThemeColors): ThemeColors => {
          const next = { ...fallback, ...value }
          // Migrate the previous stock light palette while preserving genuine
          // user customizations and all dark/custom theme behavior.
          if (fallback.bg === LIGHT_DEFAULTS.bg && ['#eef2f6', '#f1f5f9'].includes(next.bg.toLowerCase())) next.bg = LIGHT_DEFAULTS.bg
          if (fallback.bg === LIGHT_DEFAULTS.bg && ['#f8fafc'].includes(next.card.toLowerCase())) next.card = LIGHT_DEFAULTS.card
          if (fallback.bg === LIGHT_DEFAULTS.bg && next.border.toLowerCase() === '#d7dee8') next.border = LIGHT_DEFAULTS.border
          if (fallback.bg === LIGHT_DEFAULTS.bg && next.muted.toLowerCase() === '#475569') next.muted = LIGHT_DEFAULTS.muted
          if (fallback.bg === LIGHT_DEFAULTS.bg && next.border.toLowerCase() === '#cbd5e1') next.border = LIGHT_DEFAULTS.border
          if (['#ff6432', '#ff3366', '#d72323'].includes(next.accent.toLowerCase())) next.accent = '#FF0015'
          return next
        }
        if ('dark' in parsed || 'light' in parsed) {
          return {
            dark: migrate((parsed as Partial<ThemePalettes>).dark ?? DARK_DEFAULTS, DARK_DEFAULTS),
            light: migrate((parsed as Partial<ThemePalettes>).light ?? LIGHT_DEFAULTS, LIGHT_DEFAULTS),
          }
        }
        // Legacy flat palettes belonged to the previously persisted mode.
        const mode = localStorage.getItem('theme-mode') === 'dark' ? 'dark' : 'light'
        return { dark: mode === 'dark' ? migrate(parsed as ThemeColors, DARK_DEFAULTS) : DARK_DEFAULTS,
          light: mode === 'light' ? migrate(parsed as ThemeColors, LIGHT_DEFAULTS) : LIGHT_DEFAULTS }
      }
    } catch { /* ignore */ }
    return { dark: DARK_DEFAULTS, light: LIGHT_DEFAULTS }
  })
  const [fontScale, setFontScale] = useState<number>(() => {
    const saved = Number(localStorage.getItem('font-scale'))
    return saved >= 0.01 && saved <= 1.5 ? saved : 1
  })
  const [fontFamily, setFontFamily] = useState(() => localStorage.getItem('font-family') || 'Josefin Sans')

  const defaults = theme === 'dark' ? DARK_DEFAULTS : LIGHT_DEFAULTS
  const colors = palettes[theme]
  const canToggle = allowed_themes.length > 1

  useEffect(() => {
    document.documentElement.style.fontSize = `${fontScale * 100}%`
    localStorage.setItem('font-scale', String(fontScale))
  }, [fontScale])

  useEffect(() => {
    document.documentElement.style.setProperty('--t-font-family', `'${fontFamily}', sans-serif`)
    localStorage.setItem('font-family', fontFamily)
  }, [fontFamily])

  useEffect(() => {
    if (!allowed_themes.includes(theme)) setTheme(allowed_themes[0] ?? 'light')
  }, [allowed_themes, theme])

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('theme-mode', theme)
  }, [theme])

  useEffect(() => {
    applyCSS(colors, theme)
    localStorage.setItem('theme-colors-v2', JSON.stringify(palettes))
  }, [colors, palettes, theme])

  const toggleTheme = useCallback(() => {
    if (!canToggle) return
    setTheme(t => {
      const next = t === 'dark' ? 'light' : 'dark'
      return next
    })
  }, [canToggle])

  const setColor = useCallback((key: keyof ThemeColors, value: string) => {
    setPalettes(prev => ({ ...prev, [theme]: { ...prev[theme], [key]: value } }))
  }, [theme])

  const resetColors = useCallback(() => {
    setPalettes(prev => ({ ...prev, [theme]: theme === 'dark' ? DARK_DEFAULTS : LIGHT_DEFAULTS }))
    setFontScale(1)
  }, [theme])

  return (
    <ThemeContext.Provider value={{ theme, toggleTheme, colors, setColor, resetColors, defaults, fontScale, setFontScale, fontFamily, setFontFamily }}>
      {children}
    </ThemeContext.Provider>
  )
}

export function useTheme() {
  return useContext(ThemeContext)
}

export { hexToRgba, DARK_DEFAULTS, LIGHT_DEFAULTS }
