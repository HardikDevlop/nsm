import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import GlassCard from '../components/GlassCard'
import { PermissionGuard } from '../components/PermissionGuard'
import { listAlerts, listDevices, getMonitoringStatus, streamMonitoring, clearAllAlerts, type AlertRecord, type DeviceRecord } from '../lib/api'
import { confirmDanger, toast } from '../lib/swal'

type Sev = 'critical' | 'high' | 'medium' | 'low'
type Status = 'open' | 'investigating' | 'resolved'

const sevColor: Record<Sev, { c: string; bg: string }> = {
  critical: { c: '#ff3366', bg: 'rgba(255,51,102,0.12)' },
  high: { c: '#ff6644', bg: 'rgba(255,102,68,0.12)' },
  medium: { c: '#ffaa00', bg: 'rgba(255,170,0,0.12)' },
  low: { c: '#00d4ff', bg: 'rgba(0,212,255,0.12)' },
}

const statusColor: Record<Status, { c: string; label: string }> = {
  open: { c: '#ff3366', label: 'OPEN' },
  investigating: { c: '#ffaa00', label: 'INVESTIGATING' },
  resolved: { c: '#00ff88', label: 'RESOLVED' },
}

type LiveDevice = Record<string, unknown>

type IncidentRow = {
  id: string
  title: string
  sev: Sev
  status: Status
  src: string
  dst: string
  time: string
  assigned: string
  type: string
}

export default function Incidents() {
  const [filter, setFilter] = useState<'all' | Sev | Status>('all')
  const [selected, setSelected] = useState<IncidentRow | null>(null)
  const [alerts, setAlerts] = useState<AlertRecord[]>([])
  const [devices, setDevices] = useState<DeviceRecord[]>([])
  const [liveDevices, setLiveDevices] = useState<LiveDevice[]>([])
  const [error, setError] = useState<string | null>(null)
  const cleanupRef = useRef<(() => void) | null>(null)

  // Load alerts + devices + monitoring status
  const loadData = useCallback(async () => {
    try {
      const [alertData, deviceData, monStatus] = await Promise.all([
        listAlerts(),
        listDevices(),
        getMonitoringStatus(),
      ])
      setAlerts(alertData)
      setDevices(deviceData)
      setLiveDevices(monStatus.devices)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load incidents')
    }
  }, [])

  useEffect(() => {
    let ignore = false
    void (async () => {
      await loadData()
    })()
    return () => { ignore = true }
  }, [loadData])

  // SSE stream for live monitoring updates (ping counts, status)
  useEffect(() => {
    let cancelled = false
    void (async () => {
      try {
        const cleanup = await streamMonitoring((event) => {
          if (cancelled) return
          const data = event.data as { devices: LiveDevice[] }
          setLiveDevices(data.devices)
        })
        cleanupRef.current = cleanup
      } catch { /* silent */ }
    })()
    return () => {
      cancelled = true
      if (cleanupRef.current) {
        cleanupRef.current()
        cleanupRef.current = null
      }
    }
  }, [])

  // Build a map: device_id → live monitoring data
  const liveByDeviceId = useMemo(() => {
    const map = new Map<number, LiveDevice>()
    for (const d of liveDevices) {
      const devId = d.device_id as number | undefined
      if (devId) map.set(devId, d)
    }
    return map
  }, [liveDevices])

  // Build per-device alert counts
  const alertCountByDevice = useMemo(() => {
    const counts = new Map<number, number>()
    for (const a of alerts) {
      if (a.device_id) {
        counts.set(a.device_id, (counts.get(a.device_id) ?? 0) + 1)
      }
    }
    return counts
  }, [alerts])

  // Build device rows with status, alert count, ping count
  const deviceRows = useMemo(() => {
    return devices.map(dev => {
      const live = liveByDeviceId.get(dev.id)
      const alertCount = alertCountByDevice.get(dev.id) ?? 0
      const liveStatus = live ? String(live.status ?? 'unknown') : null
      const totalPings = live ? (live.total_pings as number ?? 0) : 0
      const isMonitored = !!live

      // Determine display status
      let displayStatus: string
      let statusClr: string
      if (liveStatus === 'up') { displayStatus = 'UP'; statusClr = '#00ff88' }
      else if (liveStatus === 'down') { displayStatus = 'DOWN'; statusClr = '#ff3366' }
      else if (dev.status === 'online') { displayStatus = 'ONLINE'; statusClr = '#00ff88' }
      else if (dev.status === 'offline') { displayStatus = 'OFFLINE'; statusClr = '#ff3366' }
      else { displayStatus = 'UNKNOWN'; statusClr = '#ffaa00' }

      return {
        id: dev.id,
        hostname: dev.hostname || `device-${dev.ip_address.replace(/\./g, '-')}`,
        ip: dev.ip_address,
        status: displayStatus,
        statusClr,
        alertCount,
        totalPings,
        isMonitored,
      }
    })
  }, [devices, liveByDeviceId, alertCountByDevice])

  // Sort: DOWN first, then by alert count desc
  const sortedDeviceRows = useMemo(() => {
    return [...deviceRows].sort((a, b) => {
      if (a.status === 'DOWN' && b.status !== 'DOWN') return -1
      if (b.status === 'DOWN' && a.status !== 'DOWN') return 1
      return b.alertCount - a.alertCount
    })
  }, [deviceRows])

  const incidents: IncidentRow[] = useMemo(() => alerts.map(alert => ({
    id: `INC-${alert.id}`,
    title: alert.title,
    sev: (alert.severity === 'critical' || alert.severity === 'high' || alert.severity === 'medium' || alert.severity === 'low' ? alert.severity : 'medium') as Sev,
    status: (alert.status === 'resolved' ? 'resolved' : alert.status === 'acknowledged' ? 'investigating' : 'open') as Status,
    src: alert.device_id
      ? `${alert.hostname || devices.find(d => d.id === alert.device_id)?.hostname || `Device ${alert.device_id}`} · ${alert.ip_address || alert.ip || devices.find(d => d.id === alert.device_id)?.ip_address || 'IP N/A'}`
      : 'System',
    dst: alert.description ?? 'NMS',
    time: new Date(alert.created_at).toLocaleString('en-GB', { hour12: false }),
    assigned: alert.acknowledged_by ? `User ${alert.acknowledged_by}` : 'Auto',
    type: alert.severity,
  })), [alerts, devices])

  const filtered = incidents.filter(inc => {
    if (filter === 'all') return true
    return inc.sev === filter || inc.status === filter
  })

  const downCount = deviceRows.filter(d => d.status === 'DOWN' || d.status === 'OFFLINE').length

  const handleClearAll = async () => {
    const ok = await confirmDanger({
      title: `Clear all ${alerts.length} alerts?`,
      text: 'This cannot be undone.',
      confirmText: 'Clear',
    })
    if (!ok) return
    try {
      await clearAllAlerts()
      setAlerts([])
      setError(null)
      toast.success('All alerts cleared')
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to clear alerts'
      setError(message)
      toast.error(message)
    }
  }

  return (
    <div className="p-4 md:p-6 space-y-4 md:space-y-5">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <div className="flex-1 min-w-0">
          <h1 className="font-display font-bold text-xl sm:text-2xl tracking-widest neon-cyan">INCIDENT MANAGEMENT</h1>
          <p className="font-mono text-xs mt-0.5" style={{ color: 'var(--t-muted, #8899bb)' }}>Auto + manual reporting · Severity-based triage</p>
        </div>
        <div className="flex flex-wrap gap-2">
          {alerts.length > 0 && (
            <PermissionGuard permission="alerts:delete">
            <button onClick={handleClearAll} className="font-mono text-xs px-4 py-2 rounded-lg transition-all hover:opacity-80 min-h-[44px]"
              style={{ background: 'rgba(255,51,102,0.15)', border: '1px solid rgba(255,51,102,0.4)', color: '#ff3366' }}>
              CLEAR ALL ({alerts.length})
            </button>
            </PermissionGuard>
          )}
          <PermissionGuard permission="alerts:create">
          <button className="font-mono text-xs px-4 py-2 rounded-lg transition-all min-h-[44px]"
            style={{ background: 'rgba(255,51,102,0.15)', border: '1px solid rgba(255,51,102,0.4)', color: '#ff3366' }}>
            + REPORT INCIDENT
          </button>
          </PermissionGuard>
        </div>
      </div>

      {error ? <div className="font-mono text-xs" style={{ color: '#ff3366' }}>{error}</div> : null}

      {/* Summary KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
        {[
          { l: 'Critical', v: incidents.filter(i => i.sev === 'critical').length, c: '#ff3366', bg: 'rgba(255,51,102,0.1)' },
          { l: 'High', v: incidents.filter(i => i.sev === 'high').length, c: '#ff6644', bg: 'rgba(255,102,68,0.1)' },
          { l: 'Medium', v: incidents.filter(i => i.sev === 'medium').length, c: '#ffaa00', bg: 'rgba(255,170,0,0.1)' },
          { l: 'Resolved', v: incidents.filter(i => i.status === 'resolved').length, c: '#00ff88', bg: 'rgba(0,255,136,0.1)' },
          { l: 'Devices Down', v: downCount, c: downCount > 0 ? '#ff3366' : '#00ff88', bg: downCount > 0 ? 'rgba(255,51,102,0.1)' : 'rgba(0,255,136,0.1)' },
        ].map(s => (
          <div key={s.l} className="glass rounded-xl p-4 text-center cursor-pointer transition-all hover:scale-[1.02]"
            style={{ background: s.bg, border: `1px solid ${s.c}30` }}
            onClick={() => setFilter(f => f === s.l.toLowerCase() ? 'all' : s.l.toLowerCase() as Sev | Status)}>
            <div className="font-display font-bold text-xl sm:text-3xl" style={{ color: s.c }}>{s.v}</div>
            <div className="font-mono text-xs mt-1" style={{ color: 'var(--t-muted, #8899bb)' }}>{s.l}</div>
          </div>
        ))}
      </div>

      {/* Per-device alert + status + ping count */}
      {sortedDeviceRows.length > 0 && (
        <GlassCard className="p-4 md:p-5">
          <div className="font-display font-bold text-sm sm:text-base tracking-wider neon-cyan mb-4">DEVICE STATUS & ALERTS</div>
          <div className="font-mono text-xs mb-3" style={{ color: 'var(--t-muted, #8899bb)' }}>
            Per-device alert count · live status · ping count (auto-updates via SSE)
          </div>
          <div className="space-y-1.5">
            {sortedDeviceRows.map(dev => (
              <div key={dev.id} className="flex flex-col sm:flex-row items-start sm:items-center gap-3 rounded-lg p-3"
                style={{ background: 'rgba(0,212,255,0.03)', border: '1px solid rgba(0,212,255,0.08)' }}>
                {/* Status dot */}
                <div className="w-3 h-3 rounded-full shrink-0" style={{
                  background: dev.statusClr,
                  boxShadow: `0 0 8px ${dev.statusClr}`,
                }} />

                {/* Device info */}
                <div className="flex-1 min-w-0 w-full sm:w-auto">
                  <div className="font-display text-sm tracking-wider" style={{ color: 'var(--t-text, #c8d8ee)' }}>
                    {dev.hostname}
                  </div>
                  <div className="font-mono text-xs" style={{ color: 'var(--t-muted, #667799)' }}>{dev.ip}</div>
                </div>

                <div className="flex items-center gap-3 w-full sm:w-auto flex-wrap">
                  {/* Status badge */}
                  <div className="font-mono text-xs px-2.5 py-1.5 rounded shrink-0 uppercase min-h-[36px] flex items-center"
                    style={{ color: dev.statusClr, background: `${dev.statusClr}15`, border: `1px solid ${dev.statusClr}30` }}>
                    {dev.status}
                  </div>

                  {/* Alert count */}
                  <div className="text-center shrink-0 px-3">
                    <div className="font-display text-xl font-bold" style={{ color: dev.alertCount > 0 ? '#ff3366' : 'var(--t-muted, #8899bb)' }}>
                      {dev.alertCount}
                    </div>
                    <div className="font-mono text-xs" style={{ color: 'var(--t-muted, #667799)' }}>ALERTS</div>
                  </div>

                  {/* Ping count */}
                  <div className="text-center shrink-0 px-3">
                    <div className="font-display text-xl font-bold" style={{ color: '#00d4ff' }}>
                      {dev.totalPings}
                    </div>
                    <div className="font-mono text-xs" style={{ color: 'var(--t-muted, #667799)' }}>PINGS</div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </GlassCard>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Incident table */}
        <GlassCard className="lg:col-span-2 overflow-hidden">
          <div className="flex flex-col sm:flex-row items-start sm:items-center gap-3 p-4" style={{ borderBottom: '1px solid rgba(0,212,255,0.1)' }}>
            <div className="font-display font-bold text-sm tracking-wider neon-cyan">INCIDENT LOG</div>
            <div className="sm:ml-auto flex flex-wrap gap-2">
              {(['all', 'critical', 'high', 'investigating', 'resolved'] as const).map(f => (
                <button key={f} onClick={() => setFilter(f)}
                  className="font-mono text-xs px-2.5 py-1.5 rounded capitalize transition-all min-h-[36px]"
                  style={{
                    background: filter === f ? 'rgba(0,212,255,0.15)' : 'transparent',
                    color: filter === f ? '#00d4ff' : 'var(--t-muted, #8899bb)',
                    border: `1px solid ${filter === f ? 'rgba(0,212,255,0.4)' : 'rgba(0,212,255,0.1)'}`,
                  }}>{f}</button>
              ))}
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr style={{ borderBottom: '1px solid rgba(0,212,255,0.08)' }}>
                  {['ID', 'Title', 'Sev', 'Status', 'Time', 'Assigned'].map(h => (
                    <th key={h} className="text-left px-4 py-2.5 font-mono text-xs" style={{ color: 'var(--t-muted, #8899bb)' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filtered.length === 0 ? (
                  <tr><td colSpan={6} className="px-4 py-6 font-mono text-xs text-center" style={{ color: 'var(--t-muted, #8899bb)' }}>No incidents match the current filter.</td></tr>
                ) : filtered.map(inc => {
                  const s = sevColor[inc.sev]
                  const st = statusColor[inc.status]
                  return (
                    <tr key={inc.id}
                      onClick={() => setSelected(p => p?.id === inc.id ? null : inc)}
                      className="cursor-pointer transition-all"
                      style={{
                        borderBottom: '1px solid rgba(0,212,255,0.04)',
                        background: selected?.id === inc.id ? 'rgba(0,212,255,0.06)' : 'transparent',
                      }}
                      onMouseEnter={e => { if (selected?.id !== inc.id) (e.currentTarget as HTMLElement).style.background = 'rgba(0,212,255,0.03)' }}
                      onMouseLeave={e => { if (selected?.id !== inc.id) (e.currentTarget as HTMLElement).style.background = 'transparent' }}>
                      <td className="px-4 py-3 font-mono text-xs neon-cyan whitespace-nowrap">{inc.id}</td>
                      <td className="px-4 py-3 font-mono text-xs max-w-xs" style={{ color: 'var(--t-text, #c8d8ee)' }}>
                        <div className="truncate">{inc.title}</div>
                        <div className="text-[10px] mt-1 truncate" style={{ color: 'var(--t-muted, #667799)' }}>SOURCE: {inc.src}</div>
                      </td>
                      <td className="px-4 py-3">
                        <span className="font-mono text-xs px-2 py-0.5 rounded uppercase"
                          style={{ color: s.c, background: s.bg }}>{inc.sev}</span>
                      </td>
                      <td className="px-4 py-3">
                        <span className="font-mono text-xs" style={{ color: st.c }}>{st.label}</span>
                      </td>
                      <td className="px-4 py-3 font-mono text-xs whitespace-nowrap" style={{ color: 'var(--t-muted, #8899bb)' }}>{inc.time.split(' ')[1]}</td>
                      <td className="px-4 py-3 font-mono text-xs" style={{ color: 'var(--t-muted, #8899bb)' }}>{inc.assigned}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </GlassCard>

        {/* Timeline */}
        <GlassCard className="p-4">
          <div className="font-display font-bold text-sm tracking-wider neon-cyan mb-4">TIMELINE</div>
          <div className="relative space-y-4">
            <div className="absolute left-[11px] top-0 bottom-0 w-px" style={{ background: 'rgba(0,212,255,0.15)' }} />
            {/* Dynamic timeline from alerts */}
            {alerts.slice(0, 8).map((alert, i) => {
              const c = alert.severity === 'critical' ? '#ff3366' : alert.severity === 'high' ? '#ff6644' : alert.severity === 'medium' ? '#ffaa00' : '#00d4ff'
              const time = new Date(alert.created_at).toLocaleTimeString('en-IN', { timeZone: 'Asia/Kolkata', hour12: false })
              return (
                <div key={i} className="flex gap-3 relative pl-7">
                  <div className="absolute left-0 top-1.5 w-[23px] h-[23px] rounded-full flex items-center justify-center"
                    style={{ background: `${c}18`, border: `1.5px solid ${c}60` }}>
                    <div className="w-1.5 h-1.5 rounded-full" style={{ background: c }} />
                  </div>
                  <div>
                    <div className="font-mono text-xs font-semibold" style={{ color: c }}>{time}</div>
                    <div className="font-mono text-xs mt-0.5 leading-snug" style={{ color: 'var(--t-muted, #8899bb)' }}>{alert.title}</div>
                  </div>
                </div>
              )
            })}
            {alerts.length === 0 && (
              <div className="font-mono text-xs pl-7" style={{ color: 'var(--t-muted, #8899bb)' }}>No incidents recorded yet.</div>
            )}
          </div>
        </GlassCard>
      </div>
    </div>
  )
}
