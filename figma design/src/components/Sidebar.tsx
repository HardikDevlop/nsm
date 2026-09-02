import { NavLink } from 'react-router'
import { useEffect, useMemo, useState } from 'react'
import { useTheme } from './ThemeContext'
import { useAuth } from './AuthContext'
import { requestJson, type DashboardSummary } from '../lib/api'
import { useBranding } from './BrandingContext'

type Props = { 
  collapsed: boolean
  mobileOpen?: boolean
  onToggle: () => void
  onClose?: () => void
}

const nav = [
  { to: '/', label: 'Overview', icon: 'M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6', permission: 'dashboard:read', exact: true },
  { to: '/topology', label: 'Network Topology', icon: 'M13 10V3L4 14h7v7l9-11h-7z', permission: 'topology:read' },
  { to: '/manual-topology', label: 'Manual Topology', icon: 'M4 4h16v16H4zM8 8h8M8 12h8M8 16h5', permission: 'topology:read' },
  { to: '/isp', label: 'IP Scan', icon: 'M8.111 16.404a5.5 5.5 0 017.778 0M12 20h.01m-7.08-7.071c3.904-3.905 10.236-3.905 14.141 0M1.394 9.393c5.857-5.857 15.355-5.857 21.213 0', permission: 'isp:read' },
  { to: '/device-monitoring', label: 'Device Monitoring', icon: 'M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z', permission: 'device_monitoring:read' },
  // { to: '/incidents', label: 'Incidents', icon: 'M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z', permission: 'incidents:read' },
  // { to: '/attack-path', label: 'Attack Path', icon: 'M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7', permission: 'attack_path:read' },
  { to: '/packet-analysis', label: 'Packet Analysis', icon: 'M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z', permission: 'packet_analysis:read' },
  { to: '/flow-analytics', label: 'Flow Analytics', icon: 'M4 19V5m0 14h16M8 16v-5m4 5V7m4 9v-8', permission: 'flows:read' },
  { to: '/apm', label: 'APM Service Health', icon: 'M4 19h16M6 16v-5m4 5V7m4 9v-3m4 3V4', permission: 'apm:read' },
  { to: '/cmdb', label: 'CMDB', icon: 'M4 5h16v14H4zM8 9h8M8 13h5M8 17h8', permission: 'cmdb:read' },
  { to: '/rca', label: 'Root Cause Analysis', icon: 'M12 3v18M3 12h18M5 5l14 14M19 5L5 19', permission: 'rca:read' },
  { to: '/incident-management', label: 'Incident Management', icon: 'M4 5h16v14H4zM8 9h8M8 13h5M8 17h8', permission: 'incidents:read' },
  { to: '/problem-management', label: 'Problem Management', icon: 'M12 3a9 9 0 100 18 9 9 0 000-18zm0 5v5m0 3h.01', permission: 'problems:read' },
  { to: '/change-management', label: 'Change Management', icon: 'M4 5h16v14H4zM8 9h8M8 13h5M8 17h8', permission: 'changes:read' },
  { to: '/knowledge-base', label: 'Knowledge Base', icon: 'M4 5h16v14H4zM8 9h8M8 13h6M8 17h4', permission: 'knowledge:read' },
  { to: '/configuration-backups', label: 'Configuration Backups', icon: 'M5 4h14v16H5zM8 8h8M8 12h8M8 16h5', permission: 'config_backups:read' },
  { to: '/configuration-compliance', label: 'Configuration Compliance', icon: 'M12 3l8 4v5c0 5-3.5 8-8 9-4.5-1-8-4-8-9V7zM9 12l2 2 4-4', permission: 'config_compliance:read' },
  { to: '/availability', label: 'Availability Reports', icon: 'M4 19h16M6 16v-5M10 16V7M14 16v-3M18 16V4', permission: 'availability:read' },
  { to: '/qos', label: 'QoS Monitoring', icon: 'M4 19h16M6 16v-5M10 16V7M14 16v-3M18 16V4', permission: 'qos:read' },
  { to: '/bgp', label: 'BGP Monitoring', icon: 'M4 19h16M5 15l4-5 4 3 6-8', permission: 'bgp:read' },
  // { to: '/nginx', label: 'Nginx Monitor', icon: 'M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2m-2-4h.01M17 16h.01', permission: 'nginx:read' },
  // { to: '/firewall', label: 'Firewall', icon: 'M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z', permission: 'firewall:read' },
  { to: '/snmp/devices', label: 'SNMP Devices', icon: 'M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z', permission: 'devices:read' },
  { to: '/servers', label: 'Server Monitor', icon: 'M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2', permission: 'server_monitoring:read' },
  { to: '/linux-servers', label: 'Linux Server Monitoring', icon: 'M4 5h16v14H4zM8 9h8M8 13h5', permission: 'linux_servers:read' },
  // { to: '/forensics', label: 'Forensics', icon: 'M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z', permission: 'forensics:read' },
  // { to: '/compliance', label: 'Compliance', icon: 'M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4', permission: 'compliance:read' },
  
  // Management section
  { to: '/alerts-management', label: 'Alert Management', icon: 'M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z', permission: 'alerts:read', management: true },
  { to: '/events', label: 'Events', icon: 'M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z', permission: 'events:read', management: true },
  { to: '/notifications', label: 'Notifications', icon: 'M15 17h5l-5 5v-5zM4.868 19.504L8.094 12l-3.226-7.504L3 5.496z', permission: 'notifications:read', management: true },
  // { to: '/thresholds', label: 'Thresholds', icon: 'M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z', permission: 'thresholds:read', management: true },
  { to: '/monitoring-jobs', label: 'Monitoring Jobs', icon: 'M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z', permission: 'monitoring_jobs:read', management: true },
  { to: '/interfaces', label: 'Network Interfaces', icon: 'M8.111 16.404a5.5 5.5 0 017.778 0M12 20h.01m-7.08-7.071c3.904-3.905 10.236-3.905 14.141 0M1.394 9.393c5.857-5.857 15.355-5.857 21.213 0', permission: 'interfaces:read', management: true },
  
  // Admin section
  { to: '/roles', label: 'Role Management', icon: 'M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z', permission: 'roles:read', admin: true },
  { to: '/users', label: 'User Management', icon: 'M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z', permission: 'users:read', admin: true },
  { to: '/organizations', label: 'Organizations', icon: 'M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4', permission: 'organizations:read', admin: true },
  { to: '/sites', label: 'Sites', icon: 'M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0zM15 11a3 3 0 11-6 0 3 3 0 016 0z', permission: 'sites:read', admin: true },
  { to: '/vendors', label: 'Vendors', icon: 'M9 3H5a2 2 0 00-2 2v4m6-6h10a2 2 0 012 2v4M9 3v18m0 0h10a2 2 0 002-2v-4M9 21H5a2 2 0 01-2-2v-4m0 0h18', permission: 'vendors:read', admin: true },
  { to: '/device-types', label: 'Device Types', icon: 'M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6z', permission: 'device_types:read', admin: true },
  { to: '/device-credentials', label: 'Device Credentials', icon: 'M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z', permission: 'device_credentials:read', admin: true },
  { to: '/audit-logs', label: 'Audit Logs', icon: 'M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01', permission: 'audit_logs:read', admin: true },
  { to: '/reports/management', label: 'Report Management', icon: 'M4 5h16v14H4zM7 9h10M7 13h6M7 17h4', permission: 'reports:read', admin: true },
  { to: '/reports/daily', label: 'Daily Report', icon: 'M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z', permission: 'reports:read', admin: true },
]

export default function Sidebar({ collapsed, mobileOpen, onToggle, onClose }: Props) {
  const { theme, colors } = useTheme()
  const { hasPermission, user, logout } = useAuth()
  const branding = useBranding()
  const isDark = theme === 'dark'
  const [onlineCount, setOnlineCount] = useState(0)
  const [healthScore, setHealthScore] = useState(0)
  const [totalDevices, setTotalDevices] = useState(0)

  // Filter nav items by permission
  const visibleNav = useMemo(() => nav.filter(item => item.to !== '/servers' && hasPermission(item.permission)), [hasPermission])

  useEffect(() => {
    const summary = window.sessionStorage.getItem('nms.dashboard.summary.v1')
    if (summary) {
      try {
        const parsed = JSON.parse(summary) as { total_devices?: number; online_devices?: number }
        const total = parsed.total_devices ?? 0
        const online = parsed.online_devices ?? 0
        setTotalDevices(total)
        setOnlineCount(online)
        setHealthScore(total > 0 ? Math.round((online / total) * 100) : 0)
      } catch {
        // Ignore a malformed optional cache and use the live request below.
      }
    }

    let mounted = true
    let controller: AbortController | null = null
    let inFlight = false

    const loadLiveStatus = async () => {
      if (!mounted || inFlight || document.visibilityState !== 'visible') return
      inFlight = true
      controller?.abort()
      controller = new AbortController()
      try {
        const live = await requestJson<DashboardSummary>('/dashboard/summary', { signal: controller.signal })
        if (!mounted) return
        const total = live.total_devices ?? 0
        const online = live.online_devices ?? 0
        setTotalDevices(total)
        setOnlineCount(online)
        setHealthScore(total > 0 ? Math.round((online / total) * 100) : 0)
      } catch (error) {
        if (!(error instanceof Error && error.name === 'AbortError')) {
          // Keep the last known values if the live summary is temporarily unavailable.
        }
      } finally {
        inFlight = false
      }
    }

    void loadLiveStatus()
    const timer = window.setInterval(() => { void loadLiveStatus() }, 15_000)
    const onVisibilityChange = () => {
      if (document.visibilityState === 'visible') void loadLiveStatus()
    }
    document.addEventListener('visibilitychange', onVisibilityChange)
    return () => {
      mounted = false
      clearInterval(timer)
      controller?.abort()
      document.removeEventListener('visibilitychange', onVisibilityChange)
    }
  }, [])

  // On mobile, use mobileOpen to control visibility
  // On desktop, always show (collapsed or expanded)
  const isVisible = mobileOpen !== undefined ? mobileOpen : true
  const isMobile = typeof window !== 'undefined' && window.innerWidth < 768

  if (isMobile && !isVisible) return null

  // Split nav into main, management, and admin sections
  const mainNav = visibleNav.filter(item => !item.admin && !item.management)
  const managementNav = visibleNav.filter(item => item.management)
  const adminNav = visibleNav.filter(item => item.admin)

  const prefetchers = useMemo(() => ({
    '/': () => import('../pages/Dashboard'),
    '/topology': () => import('../pages/Topology'),
    '/manual-topology': () => import('../pages/ManualTopology'),
    '/isp': () => import('../pages/ISPMonitoring'),
    '/device-monitoring': () => import('../pages/DeviceMonitoringList'),
    '/packet-analysis': () => import('../pages/PacketAnalysis'),
    '/flow-analytics': () => import('../pages/FlowAnalytics'),
    '/apm': () => import('../pages/APM'),
    '/cmdb': () => import('../pages/CMDB'),
    '/rca': () => import('../pages/RCA'),
    '/incident-management': () => import('../pages/IncidentManagement'),
    '/problem-management': () => import('../pages/ProblemManagement'),
    '/change-management': () => import('../pages/ChangeManagement'),
    '/knowledge-base': () => import('../pages/KnowledgeBase'),
    '/configuration-backups': () => import('../pages/ConfigurationBackups'),
    '/configuration-compliance': () => import('../pages/ConfigurationCompliance'),
    '/nginx': () => import('../pages/NginxMonitoring'),
    '/firewall': () => import('../pages/Firewall'),
    '/forensics': () => import('../pages/Forensics'),
    '/compliance': () => import('../pages/Compliance'),
    '/alerts-management': () => import('../pages/AlertsManagement'),
    '/events': () => import('../pages/Events'),
    '/notifications': () => import('../pages/Notifications'),
    '/thresholds': () => import('../pages/Thresholds'),
    '/monitoring-jobs': () => import('../pages/MonitoringJobs'),
    '/interfaces': () => import('../pages/InterfacesList'),
    '/roles': () => import('../pages/RoleManagement'),
    '/users': () => import('../pages/UserManagement'),
    '/organizations': () => import('../pages/Organizations'),
    '/sites': () => import('../pages/Sites'),
    '/vendors': () => import('../pages/Vendors'),
    '/reports/management': () => import('../pages/ReportManagement'),
    '/reports/daily': () => import('../pages/DailyReport'),
    '/audit-logs': () => import('../pages/AuditLogs'),
    '/device-credentials': () => import('../pages/DeviceCredentials'),
    '/device-types': () => import('../pages/DeviceTypes'),
    '/snmp/devices': () => import('../pages/DeviceMonitoringList'),
  }), [])

  const prefetchRoute = (to: string) => {
    const fn = prefetchers[to as keyof typeof prefetchers]
    if (fn) void fn().catch(() => undefined)
  }

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
            {branding.logo_url ? <img src={branding.logo_url} alt={branding.application_name} className="h-6 w-auto object-contain" /> : <div className="font-display font-bold text-sm" style={{ color: 'var(--t-text)' }}>{branding.application_name}</div>}
            <div className="font-mono text-xs mt-0.5" style={{ color: 'var(--t-muted)' }}>{branding.application_name}</div>
          </div>
        )}
        <button onClick={() => {
          if (window.innerWidth < 768) {
            if (onClose) onClose()
          } else {
            onToggle()
          }
        }} aria-label={collapsed ? 'Expand navigation' : 'Collapse navigation'} className="ml-auto transition-colors shrink-0" style={{ color: 'var(--t-muted)' }}>
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
              onMouseEnter={() => prefetchRoute(item.to)}
              onFocus={() => prefetchRoute(item.to)}
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

        {/* Management section */}
        {managementNav.length > 0 && (
          <>
            {!collapsed && (
              <div className="px-2 pt-4 pb-1">
                <span className="font-mono text-xs uppercase tracking-widest" style={{ color: 'var(--t-muted)' }}>
                  Management
                </span>
              </div>
            )}
            {!collapsed && <div className="mx-2 mb-1" style={{ borderTop: '1px solid var(--t-border-light)' }} />}
            {collapsed && <div className="my-2 mx-2" style={{ borderTop: '1px solid var(--t-border-light)' }} />}
            <div className="space-y-0.5">
              {managementNav.map(item => (
                <NavLink key={item.to} to={item.to}
                  onClick={() => { if (window.innerWidth < 768 && onClose) onClose() }}
                  onMouseEnter={() => prefetchRoute(item.to)}
                  onFocus={() => prefetchRoute(item.to)}
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
                  onMouseEnter={() => prefetchRoute(item.to)}
                  onFocus={() => prefetchRoute(item.to)}
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
