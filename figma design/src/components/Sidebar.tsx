import { NavLink } from 'react-router'
import { useEffect, useState } from 'react'
import { useTheme } from './ThemeContext'
import { useAuth } from './AuthContext'
import { getDashboardSummary, listDevices, type DeviceRecord } from '../lib/api'

type Props = { 
  collapsed: boolean
  mobileOpen?: boolean
  onToggle: () => void
  onClose?: () => void
}

const nav = [
  { to: '/', label: 'Overview', icon: 'M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6', permission: 'dashboard:read', exact: true },
  { to: '/topology', label: 'Network Topology', icon: 'M13 10V3L4 14h7v7l9-11h-7z', permission: 'topology:read' },
  { to: '/isp', label: 'IP Scan', icon: 'M8.111 16.404a5.5 5.5 0 017.778 0M12 20h.01m-7.08-7.071c3.904-3.905 10.236-3.905 14.141 0M1.394 9.393c5.857-5.857 15.355-5.857 21.213 0', permission: 'isp:read' },
  { to: '/device-monitoring', label: 'Device Monitoring', icon: 'M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z', permission: 'device_monitoring:read' },
  // { to: '/incidents', label: 'Incidents', icon: 'M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z', permission: 'incidents:read' },
  // { to: '/attack-path', label: 'Attack Path', icon: 'M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7', permission: 'attack_path:read' },
  { to: '/packet-analysis', label: 'Packet Analysis', icon: 'M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z', permission: 'packet_analysis:read' },
  { to: '/nginx', label: 'Nginx Monitor', icon: 'M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2m-2-4h.01M17 16h.01', permission: 'nginx:read' },
  { to: '/firewall', label: 'Firewall', icon: 'M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z', permission: 'firewall:read' },
  { to: '/snmp', label: 'SNMP Monitor', icon: 'M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z', permission: 'devices:read' },
  { to: '/servers', label: 'Server Monitor', icon: 'M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2', permission: 'server_monitoring:read' },
  { to: '/forensics', label: 'Forensics', icon: 'M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z', permission: 'forensics:read' },
  { to: '/compliance', label: 'Compliance', icon: 'M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4', permission: 'compliance:read' },
  // Admin section
  { to: '/roles', label: 'Role Management', icon: 'M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z', permission: 'roles:read', admin: true },
  { to: '/users', label: 'User Management', icon: 'M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z', permission: 'users:read', admin: true },
]

export default function Sidebar({ collapsed, mobileOpen, onToggle, onClose }: Props) {
  const { theme, colors } = useTheme()
  const { hasPermission, user, logout } = useAuth()
  const isDark = theme === 'dark'
  const [onlineCount, setOnlineCount] = useState(0)
  const [healthScore, setHealthScore] = useState(0)
  const [totalDevices, setTotalDevices] = useState(0)

  // Filter nav items by permission
  const visibleNav = nav.filter(item => hasPermission(item.permission))

  useEffect(() => {
    let ignore = false
    async function load() {
      try {
        const [summary, devices] = await Promise.all([getDashboardSummary(), listDevices()])
        if (!ignore) {
          setTotalDevices(summary.total_devices)
          setOnlineCount(summary.online_devices)
          setHealthScore(summary.total_devices > 0
            ? Math.round((summary.online_devices / summary.total_devices) * 100)
            : 0)
        }
      } catch { /* silent */ }
    }
    void load()
    return () => { ignore = true }
  }, [])

  // Auto-refresh every 30s
  useEffect(() => {
    const interval = setInterval(async () => {
      try {
        const [summary] = await Promise.all([getDashboardSummary()])
        setTotalDevices(summary.total_devices)
        setOnlineCount(summary.online_devices)
        setHealthScore(summary.total_devices > 0
          ? Math.round((summary.online_devices / summary.total_devices) * 100)
          : 0)
      } catch { /* silent */ }
    }, 30000)
    return () => clearInterval(interval)
  }, [])

  // On mobile, use mobileOpen to control visibility
  // On desktop, always show (collapsed or expanded)
  const isVisible = mobileOpen !== undefined ? mobileOpen : true
  const isMobile = typeof window !== 'undefined' && window.innerWidth < 768

  if (isMobile && !isVisible) return null

  // Split nav into main and admin sections
  const mainNav = visibleNav.filter(item => !item.admin)
  const adminNav = visibleNav.filter(item => item.admin)

  return (
    <aside className={`${isDark ? 'glass' : 'glass-light'} flex flex-col shrink-0 transition-all duration-300 z-30 fixed md:relative h-full`}
      style={{
        width: collapsed ? 64 : 224,
        borderRight: '1px solid var(--t-border-alpha)',
        borderTop: 'none', borderBottom: 'none', borderLeft: 'none',
        transform: isMobile && !mobileOpen ? 'translateX(-100%)' : 'translateX(0)',
      }}>
      {/* Logo */}
      <div className="flex items-center gap-3 px-4 py-4 shrink-0"
        style={{ borderBottom: '1px solid var(--t-border-light)' }}>
        <div className="shrink-0 w-8 h-8 flex items-center justify-center rounded overflow-hidden"
          style={{ background: 'rgb(239 231 231 / 15%)', border: '1px solid var(--t-accent-border)' }}>
          <img src="/favicon.png" alt="" className="w-6 h-6 object-contain" />
        </div>
        {!collapsed && (
          <div className="overflow-hidden">
            <img src="/header-logo.png" alt="Agnigate" className="h-6 w-auto object-contain" />
            <div className="font-mono text-xs mt-0.5" style={{ color: 'var(--t-muted)' }}>v4.2.1 · NMS</div>
          </div>
        )}
        <button onClick={() => {
          if (window.innerWidth < 768) {
            if (onClose) onClose()
          } else {
            onToggle()
          }
        }} className="ml-auto transition-colors shrink-0" style={{ color: 'var(--t-muted)' }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            {collapsed
              ? <path d="M9 18l6-6-6-6" />
              : <path d="M15 18l-6-6 6-6" />}
          </svg>
        </button>
      </div>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto py-3 px-2">
        {/* Main nav */}
        <div className="space-y-0.5">
          {mainNav.map(item => (
            <NavLink key={item.to} to={item.to} end={item.to === '/'}
              onClick={() => { if (window.innerWidth < 768 && onClose) onClose() }}
              className={({ isActive }) =>
                `flex items-center gap-3 px-2 py-2 rounded transition-all duration-150 group relative ${
                  isActive ? '' : ''
                }`
              }
              style={({ isActive }) => ({
                color: isActive ? 'var(--t-accent)' : 'var(--t-muted)',
                background: isActive ? 'var(--t-accent-alpha)' : 'transparent',
                border: isActive ? '1px solid var(--t-accent-border)' : '1px solid transparent',
              })}
            >
              {({ isActive }) => (
                <>
                  {isActive && (
                    <span className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-5 rounded-r"
                      style={{ background: 'var(--t-accent)', boxShadow: '0 0 8px var(--t-accent-alpha)' }} />
                  )}
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none"
                    stroke={isActive ? 'var(--t-accent)' : 'currentColor'} strokeWidth="1.8"
                    strokeLinecap="round" strokeLinejoin="round" className="shrink-0">
                    <path d={item.icon} />
                  </svg>
                  {!collapsed && (
                    <span className="font-display font-medium text-sm tracking-wide truncate">{item.label}</span>
                  )}
                </>
              )}
            </NavLink>
          ))}
        </div>

        {/* Admin section */}
        {adminNav.length > 0 && (
          <>
            {!collapsed && (
              <div className="px-2 pt-4 pb-1">
                <span className="font-mono text-xs uppercase tracking-widest" style={{ color: 'var(--t-muted)' }}>
                  Administration
                </span>
              </div>
            )}
            {!collapsed && <div className="mx-2 mb-1" style={{ borderTop: '1px solid var(--t-border-light)' }} />}
            {collapsed && <div className="my-2 mx-2" style={{ borderTop: '1px solid var(--t-border-light)' }} />}
            <div className="space-y-0.5">
              {adminNav.map(item => (
                <NavLink key={item.to} to={item.to}
                  onClick={() => { if (window.innerWidth < 768 && onClose) onClose() }}
                  className={({ isActive }) =>
                    `flex items-center gap-3 px-2 py-2 rounded transition-all duration-150 group relative ${
                      isActive ? '' : ''
                    }`
                  }
                  style={({ isActive }) => ({
                    color: isActive ? 'var(--t-accent)' : 'var(--t-muted)',
                    background: isActive ? 'var(--t-accent-alpha)' : 'transparent',
                    border: isActive ? '1px solid var(--t-accent-border)' : '1px solid transparent',
                  })}
                >
                  {({ isActive }) => (
                    <>
                      {isActive && (
                        <span className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-5 rounded-r"
                          style={{ background: 'var(--t-accent)', boxShadow: '0 0 8px var(--t-accent-alpha)' }} />
                      )}
                      <svg width="15" height="15" viewBox="0 0 24 24" fill="none"
                        stroke={isActive ? 'var(--t-accent)' : 'currentColor'} strokeWidth="1.8"
                        strokeLinecap="round" strokeLinejoin="round" className="shrink-0">
                        <path d={item.icon} />
                      </svg>
                      {!collapsed && (
                        <span className="font-display font-medium text-sm tracking-wide truncate">{item.label}</span>
                      )}
                    </>
                  )}
                </NavLink>
              ))}
            </div>
          </>
        )}
      </nav>

      {/* Footer */}
      {!collapsed && (
        <div className="px-4 py-3 shrink-0" style={{ borderTop: '1px solid var(--t-border-light)' }}>
          <div className="flex items-center gap-2 mb-2">
            <span className={`status-dot ${onlineCount > 0 ? 'online' : 'offline'}`} />
            <span className="font-mono text-xs" style={{ color: 'var(--t-muted)' }}>
              {onlineCount} / {totalDevices} devices online
            </span>
          </div>
          <div className="w-full rounded-full h-1" style={{ background: 'var(--t-border-light)' }}>
            <div className="h-1 rounded-full transition-all duration-500" style={{
              width: `${healthScore}%`,
              background: healthScore > 80
                ? `linear-gradient(90deg, #00ff88, #00ff8888)`
                : healthScore > 50
                  ? `linear-gradient(90deg, #ffaa00, #ffaa0088)`
                  : `linear-gradient(90deg, #ff3366, #ff336688)`,
            }} />
          </div>
          <div className="font-mono text-xs mt-1" style={{ color: 'var(--t-muted)' }}>{healthScore}% health score</div>

          {/* User info + logout */}
          {user && (
            <div className="mt-2 pt-2" style={{ borderTop: '1px solid var(--t-border-light)' }}>
              <div className="flex items-center justify-between">
                <div className="min-w-0 flex-1">
                  <div className="font-display text-xs font-medium truncate" style={{ color: 'var(--t-text)' }}>{user.name}</div>
                  <div className="font-mono text-xs truncate" style={{ color: 'var(--t-muted)' }}>{user.role_name ?? 'No Role'}</div>
                </div>
                <button onClick={logout}
                  className="p-1 rounded transition-colors shrink-0 ml-2"
                  style={{ color: 'var(--t-muted)' }}
                  onMouseEnter={e => { e.currentTarget.style.color = '#ff3366' }}
                  onMouseLeave={e => { e.currentTarget.style.color = 'var(--t-muted)' }}
                  title="Sign out">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4M16 17l5-5-5-5M21 12H9" />
                  </svg>
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </aside>
  )
}
