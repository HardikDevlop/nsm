import { useState, useEffect } from 'react'
import { Outlet, useLocation, useNavigate } from 'react-router'
import Sidebar from './Sidebar'
import NotificationPanel from './NotificationPanel'
import ThemePicker from './ThemePicker'
import { useTheme } from './ThemeContext'
import { listAlerts, recordPageView, type AlertRecord } from '../lib/api'

export default function Layout() {
  const [notifOpen, setNotifOpen] = useState(false)
  const [pickerOpen, setPickerOpen] = useState(false)
  const [time, setTime] = useState(new Date())
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const { theme, toggleTheme, colors } = useTheme()
  const isDark = theme === 'dark'
  const navigate = useNavigate()
  const location = useLocation()
  const [alerts, setAlerts] = useState<AlertRecord[]>([])
  const showBack = location.pathname !== '/'

  useEffect(() => {
    void recordPageView(location.pathname).catch(() => {})
  }, [location.pathname])

  useEffect(() => {
    const loadAlerts = () => { void listAlerts().then(setAlerts).catch(() => setAlerts([])) }
    loadAlerts()
    const timer = setInterval(loadAlerts, 15000)
    return () => clearInterval(timer)
  }, [])

  const panelAlerts = alerts.slice(0, 8).map(alert => ({
    id: alert.id,
    type: alert.severity,
    msg: alert.description || alert.title,
    time: new Date(alert.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
  }))
  const openAlertCount = alerts.filter(alert => alert.status !== 'resolved').length

  useEffect(() => {
    const t = setInterval(() => setTime(new Date()), 1000)
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
        onToggle={() => setSidebarCollapsed(c => !c)}
        onClose={() => setSidebarOpen(false)}
      />

      <div className="flex flex-col flex-1 overflow-hidden">
        {/* Top bar */}
        <header className={`${isDark ? 'glass' : 'glass-light'} flex items-center justify-between px-3 md:px-6 py-3 z-20 shrink-0`}
          style={{ borderBottom: `1px solid var(--t-border-light)`, borderLeft: 'none', borderTop: 'none', borderRight: 'none' }}>
          {/* Mobile menu button */}
          <button 
            onClick={() => setSidebarOpen(true)}
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
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M19 12H5" />
                  <path d="M12 19l-7-7 7-7" />
                </svg>
                <span className="hidden sm:inline font-mono text-xs">BACK</span>
              </button>
            )}
            <div className="hidden sm:flex items-center gap-2">
              <span className="status-dot online" />
              <span className="font-mono text-xs" style={{ color: 'var(--t-muted)' }}>SYSTEM OPERATIONAL</span>
            </div>
            <div className="hidden sm:block h-4 w-px" style={{ background: 'var(--t-border-light)' }} />
            <span className="hidden sm:inline font-mono text-xs neon-cyan">THREAT LEVEL: ELEVATED</span>
          </div>

          <div className="flex items-center gap-2 md:gap-6">
            <div className="hidden md:block text-right">
              <div className="font-mono text-base md:text-lg font-semibold leading-none neon-cyan">{fmt(time)}</div>
              <div className="font-mono text-xs mt-0.5" style={{ color: 'var(--t-muted)' }}>{fmtDate(time)} IST</div>
            </div>

            <div className="flex items-center gap-2">
              {/* Theme toggle */}
              <button onClick={toggleTheme}
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
              <button onClick={() => setPickerOpen(true)}
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

              {/* Active incidents badge 
              <div className={`${isDark ? 'glass-bright' : 'glass-light'} rounded px-2 md:px-3 py-1.5 flex items-center gap-1 md:gap-2 cursor-pointer transition-colors`}
                style={{ border: '1px solid rgba(255,51,102,0.35)' }}>
                <span className="status-dot offline" />
                <span className="hidden sm:inline font-mono text-xs" style={{ color: '#ff3366' }}>7 ACTIVE</span>
              </div>
                  */}
              {/* Notifications */}
              <button onClick={() => setNotifOpen(o => !o)}
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
        <NotificationPanel alerts={panelAlerts} onClose={() => setNotifOpen(false)} onViewAll={() => { setNotifOpen(false); navigate('/alerts') }} />
      )}

      {/* Theme picker */}
      <ThemePicker open={pickerOpen} onClose={() => setPickerOpen(false)} />
    </div>
  )
}
