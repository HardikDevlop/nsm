import { lazy, Suspense, useState, useEffect } from 'react'
import { Outlet, useLocation, useNavigate } from 'react-router'
import Sidebar from './Sidebar'
import { useTheme } from './ThemeContext'
import { clearAllAlerts, listAlerts, recordPageView, type AlertRecord } from '../lib/api'
import { useI18n } from '../i18n/I18nContext'
import { useBranding } from './BrandingContext'
import { useKeyboardShortcuts } from './useKeyboardShortcuts'
import { useQueryClient } from '../lib/queryProvider'
import { clearClientCache } from '../lib/clearClientCache'

const PAGE_VIEW_THROTTLE_MS = 30_000
const ALERT_CACHE_KEY = 'nms.layout.alerts.v1'
const ALERT_HIDDEN_KEY = 'nms.layout.hidden-alert-ids.v1'
const ALERT_REFRESH_MS = 60_000

const NotificationPanel = lazy(() => import('./NotificationPanel'))
const ThemePicker = lazy(() => import('./ThemePicker'))

export default function Layout() {
  const [notifOpen, setNotifOpen] = useState(false)
  const [pickerOpen, setPickerOpen] = useState(false)
  const [time, setTime] = useState(new Date())
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [sidebarCollapsed] = useState(true)
  const { theme, toggleTheme, colors } = useTheme()
  const { locale, setLocale, t } = useI18n()
  const branding = useBranding()
  const queryClient = useQueryClient()
  const isDark = theme === 'dark'
  const navigate = useNavigate()
  const location = useLocation()
  const [alerts, setAlerts] = useState<AlertRecord[]>([])
  const [hiddenAlertIds, setHiddenAlertIds] = useState<number[]>([])
  const [clearingCache, setClearingCache] = useState(false)
  const showBack = location.pathname !== '/'

  useKeyboardShortcuts(() => setNotifOpen(open => !open))

  const persistAlerts = (nextAlerts: AlertRecord[]) => {
    try {
      window.sessionStorage.setItem(ALERT_CACHE_KEY, JSON.stringify({ alerts: nextAlerts }))
    } catch {
      // optional cache only
    }
  }

  const persistHiddenAlertIds = (nextIds: number[]) => {
    try {
      window.localStorage.setItem(ALERT_HIDDEN_KEY, JSON.stringify({ ids: nextIds }))
    } catch {
      // optional cache only
    }
  }

  useEffect(() => {
    try {
      const cached = window.sessionStorage.getItem(ALERT_CACHE_KEY)
      if (!cached) return
      const parsed = JSON.parse(cached) as { alerts?: AlertRecord[] }
      if (Array.isArray(parsed.alerts)) setAlerts(parsed.alerts)
    } catch {
      // optional cache only
    }
  }, [])

  useEffect(() => {
    try {
      const cached = window.localStorage.getItem(ALERT_HIDDEN_KEY)
      if (!cached) return
      const parsed = JSON.parse(cached) as { ids?: number[] }
      if (Array.isArray(parsed.ids)) setHiddenAlertIds(parsed.ids.filter(id => Number.isFinite(id)))
    } catch {
      // optional cache only
    }
  }, [])

  useEffect(() => {
    const key = `nms.pageview.${location.pathname}`
    const lastSeen = Number(window.sessionStorage.getItem(key) || '0')
    const now = Date.now()
    if (now - lastSeen < PAGE_VIEW_THROTTLE_MS) return
    window.sessionStorage.setItem(key, String(now))
    void recordPageView(location.pathname).catch(() => {})
  }, [location.pathname])

  useEffect(() => {
    let mounted = true
    let inFlight = false
    const loadAlerts = async () => {
      if (!mounted || inFlight || document.visibilityState !== 'visible') return
      inFlight = true
      try {
        const nextAlerts = await listAlerts(undefined, { limit: 50 })
        if (mounted) {
          setAlerts(nextAlerts)
          persistAlerts(nextAlerts)
        }
      } catch {
        if (mounted) setAlerts([])
      } finally {
        inFlight = false
      }
    }
    void loadAlerts()
    const timer = window.setInterval(() => { void loadAlerts() }, ALERT_REFRESH_MS)
    const onVisibilityChange = () => { if (document.visibilityState === 'visible') void loadAlerts() }
    document.addEventListener('visibilitychange', onVisibilityChange)
    return () => {
      mounted = false
      clearInterval(timer)
      document.removeEventListener('visibilitychange', onVisibilityChange)
    }
  }, [])

  useEffect(() => {
    const warm = () => {
    }
    if (typeof window !== 'undefined' && 'requestIdleCallback' in window) {
      const idleId = window.requestIdleCallback(warm, { timeout: 1500 })
      return () => window.cancelIdleCallback(idleId)
    }
    const timer = window.setTimeout(warm, 800)
    return () => window.clearTimeout(timer)
  }, [])

  const visiblePanelSource = alerts.filter(alert => !hiddenAlertIds.includes(alert.id))
  const panelAlerts = visiblePanelSource.slice(0, 8).map(alert => ({
    id: alert.id,
    type: alert.severity,
    msg: alert.description || alert.title,
    time: new Date(alert.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
  }))
  const openAlertCount = visiblePanelSource.filter(alert => alert.status !== 'resolved').length

  const handleDismissAlert = (id: number) => {
    setHiddenAlertIds(current => {
      if (current.includes(id)) return current
      const nextIds = [...current, id]
      persistHiddenAlertIds(nextIds)
      return nextIds
    })
  }

  const handleClearAllAlerts = async () => {
    if (!visiblePanelSource.length) return
    try {
      await clearAllAlerts()
      setAlerts(current => current.filter(alert => !visiblePanelSource.some(item => item.id === alert.id)))
      setHiddenAlertIds(current => {
        const merged = [...new Set([...current, ...visiblePanelSource.map(alert => alert.id)])]
        persistHiddenAlertIds(merged)
        return merged
      })
      persistAlerts([])
    } catch {
      // Keep the alerts visible when the server could not clear them.
    }
  }

  const handleClearCache = async () => {
    if (clearingCache) return
    setClearingCache(true)
    await clearClientCache(queryClient)
    window.location.reload()
  }

  useEffect(() => {
    const tick = () => setTime(new Date())
    tick()
    const t = window.setInterval(() => {
      if (document.visibilityState === 'visible') tick()
    }, 1000)
    return () => clearInterval(t)
  }, [])

  const fmt = (d: Date) =>
    d.toLocaleTimeString('en-IN', { timeZone: 'Asia/Kolkata', hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })
  const fmtDate = (d: Date) =>
    d.toLocaleDateString('en-IN', { timeZone: 'Asia/Kolkata', weekday: 'short', year: 'numeric', month: 'short', day: '2-digit' })

  return (
    <div className={`flex h-screen overflow-hidden ${isDark ? 'grid-bg' : ''}`}
      style={{ background: colors.bg }}>
      {/* Mobile overlay */}
      {sidebarOpen && (
        <div className="fixed inset-0 bg-black/50 z-20 md:hidden" onClick={() => setSidebarOpen(false)} />
      )}
      <Sidebar 
        collapsed={sidebarCollapsed} 
        mobileOpen={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
      />

      <div className="flex flex-col flex-1 overflow-hidden">
        {/* Top bar */}
        <header className={`${isDark ? 'glass' : 'glass-light'} flex items-center justify-between px-3 md:px-6 py-3 z-20 shrink-0`}
          style={{ borderBottom: `1px solid var(--t-border-light)`, borderLeft: 'none', borderTop: 'none', borderRight: 'none' }}>
          {/* Mobile menu button */}
          <button 
            onClick={() => setSidebarOpen(true)}
            aria-label="Open navigation"
            className="md:hidden p-2 rounded-lg transition-colors"
            style={{ color: 'var(--t-muted)' }}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </button>

          <div className="flex items-center gap-2 md:gap-4">
            {showBack && (
              <button
                type="button"
                onClick={() => navigate(-1)}
                className={`${isDark ? 'glass-bright' : 'glass-light'} rounded px-2 md:px-3 py-1.5 flex items-center gap-1.5 cursor-pointer transition-all hover:bg-cyan-400/10`}
                style={{ border: '1px solid var(--t-border-alpha)', color: 'var(--t-accent)' }}
                title="Go back"
                aria-label="Go back"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M19 12H5" />
                  <path d="M12 19l-7-7 7-7" />
                </svg>
                <span className="hidden sm:inline font-mono text-xs">{t.back}</span>
              </button>
            )}
            <div className="hidden sm:flex items-center gap-2">
              <span className="status-dot online" />
              <span className="font-mono text-xs" style={{ color: 'var(--t-muted)' }}>{t.systemOperational}</span>
            </div>
            <div className="hidden sm:block h-4 w-px" style={{ background: 'var(--t-border-light)' }} />
            <span className="hidden sm:inline font-mono text-xs neon-cyan">{t.threatLevel}</span>
          </div>

          <div className="flex items-center gap-2 md:gap-6">
            <div className="hidden md:block text-right">
              <div className="font-mono text-base md:text-lg font-semibold leading-none neon-cyan">{fmt(time)}</div>
              <div className="font-mono text-xs mt-0.5" style={{ color: 'var(--t-muted)' }}>{fmtDate(time)} IST</div>
            </div>

            <div className="flex items-center gap-2">
              {/* Theme toggle */}
              <button onClick={toggleTheme} disabled={branding.allowed_themes.length < 2} aria-label="Toggle theme"
                className={`${isDark ? 'glass-bright' : 'glass-light'} rounded px-2 md:px-3 py-1.5 flex items-center gap-1 md:gap-2 cursor-pointer transition-all`}
                style={{ border: '1px solid var(--t-border-alpha)' }}>
                {isDark ? (
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--t-muted)" strokeWidth="2">
                    <circle cx="12" cy="12" r="5" />
                    <path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42" />
                  </svg>
                ) : (
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--t-muted)" strokeWidth="2">
                    <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
                  </svg>
                )}
                <span className="hidden md:inline font-mono text-xs" style={{ color: 'var(--t-muted)' }}>{isDark ? 'DARK' : 'LIGHT'}</span>
              </button>

              {/* Theme color picker */}
              <button onClick={() => setPickerOpen(true)} aria-label="Customize theme"
                className={`${isDark ? 'glass-bright' : 'glass-light'} rounded px-2 md:px-3 py-1.5 flex items-center gap-1 md:gap-2 cursor-pointer transition-all`}
                style={{ border: '1px solid var(--t-border-alpha)' }}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--t-accent)" strokeWidth="2">
                  <circle cx="12" cy="12" r="3" />
                  <path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 5.64l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 18.36l1.42 1.42" />
                </svg>
                <div className="hidden md:flex gap-0.5">
                  {['#FF0015', '#00d4ff', '#00ff88'].map(c => (
                    <div key={c} className="w-2 h-2 rounded-full" style={{ background: c }} />
                  ))}
                </div>
              </button>

              <select aria-label="Language" value={locale} onChange={event => setLocale(event.target.value as 'en' | 'hi')} className="rounded px-2 py-1.5 font-mono text-xs" style={{ background: 'var(--t-card)', color: 'var(--t-muted)', border: '1px solid var(--t-border-alpha)' }}><option value="en">English</option><option value="hi">हिन्दी</option></select>

              {/* Notifications */}
              <button onClick={() => setNotifOpen(o => !o)} aria-label="Open notifications"
                className={`relative ${isDark ? 'glass-bright' : 'glass-light'} rounded px-2 md:px-3 py-1.5 flex items-center gap-1 md:gap-2 cursor-pointer transition-all`}
                style={{ border: '1px solid var(--t-border-alpha)' }}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--t-muted)" strokeWidth="2">
                  <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
                  <path d="M13.73 21a2 2 0 0 1-3.46 0" />
                </svg>
                <span className="hidden sm:inline font-mono text-xs" style={{ color: 'var(--t-muted)' }}>{openAlertCount}</span>
                {openAlertCount > 0 && <span className="absolute -top-1 -right-1 w-2 h-2 rounded-full pulse-glow"
                  style={{ background: '#ff3366', boxShadow: '0 0 8px rgba(255,51,102,0.8)' }} />}
              </button>

              <button
                type="button"
                onClick={() => { void handleClearCache() }}
                disabled={clearingCache}
                aria-label="Clear website cache"
                title="Clear all website cache"
                className={`${isDark ? 'glass-bright' : 'glass-light'} rounded px-2 md:px-3 py-1.5 flex items-center gap-1 md:gap-2 cursor-pointer transition-all disabled:cursor-wait disabled:opacity-60`}
                style={{ border: '1px solid var(--t-border-alpha)', color: 'var(--t-muted)' }}
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M4 7h16" />
                  <path d="M10 11v6M14 11v6" />
                  <path d="M6 7l1 14h10l1-14" />
                  <path d="M9 7V4h6v3" />
                </svg>
                <span className="hidden md:inline font-mono text-xs">{clearingCache ? 'CLEARING' : 'CLEAR CACHE'}</span>
              </button>
            </div>
          </div>
        </header>

        {/* Main content */}
        <main className="flex-1 overflow-y-auto relative">
          <Outlet />
        </main>
      </div>

      {/* Notification panel */}
      {notifOpen && (
        <Suspense fallback={null}>
          <NotificationPanel
            alerts={panelAlerts}
            onClose={() => setNotifOpen(false)}
            onViewAll={() => { setNotifOpen(false); navigate('/alerts') }}
            onDismiss={handleDismissAlert}
            onClearAll={handleClearAllAlerts}
          />
        </Suspense>
      )}

      {/* Theme picker */}
      <Suspense fallback={null}>
        <ThemePicker open={pickerOpen} onClose={() => setPickerOpen(false)} />
      </Suspense>
    </div>
  )
}
