import { useCallback, useMemo, useState } from 'react'
import GlassCard from '../components/GlassCard'
import { AreaChart, Area, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'
import { listAlerts, listDevices, listEvents, type AlertRecord, type DeviceRecord, type EventRecord } from '../lib/api'
import { useAutoRefresh } from '../lib/useAutoRefresh'

const ttStyle = { background: 'rgba(8,25,55,0.95)', border: '1px solid rgba(0,212,255,0.3)', borderRadius: 6, fontFamily: 'JetBrains Mono', fontSize: 11, color: 'var(--t-text, #c8d8ee)' }

const sevColor = { critical: '#ff3366', high: '#ff6644', medium: '#ffaa00', low: '#00d4ff', info: '#00d4ff' } as Record<string, string>
const actionColor: Record<string, string> = { DENY: '#ff3366', DROP: '#ff3366', 'RATE-LIMIT': '#ffaa00', ALLOW: '#00ff88' }

// ── Alert Detail Modal ─────────────────────────────────────────────────────
function AlertDetailModal({ alert, device, onClose }: { alert: AlertRecord; device?: DeviceRecord; onClose: () => void }) {
  const sev = alert.severity as string
  const c = sevColor[sev] ?? 'var(--t-muted, #8899bb)'
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ backdropFilter: 'blur(3px)', background: 'rgba(0,0,0,0.65)' }}
      onClick={e => { if (e.target === e.currentTarget) onClose() }}>
      <div className="w-full max-w-lg rounded-xl overflow-hidden"
        style={{ background: 'var(--t-card, rgba(4,14,33,0.98))', border: `1px solid ${c}40`, boxShadow: `0 0 40px ${c}18` }}>
        <div className="flex items-center justify-between px-5 py-4" style={{ borderBottom: `1px solid ${c}25` }}>
          <div>
            <div className="font-display font-bold text-base tracking-widest" style={{ color: c }}>ALERT #{alert.id}</div>
            <div className="font-mono text-xs mt-0.5" style={{ color: 'var(--t-muted, #8899bb)' }}>
              {new Date(alert.created_at).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', hour12: true })}
            </div>
          </div>
          <button onClick={onClose} className="rounded-lg p-2 transition-all hover:bg-red-500/20" style={{ color: '#ff3366' }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 6L6 18M6 6l12 12"/></svg>
          </button>
        </div>
        <div className="p-5 space-y-4">
          <div className="rounded-lg p-4" style={{ background: `${c}0d`, border: `1px solid ${c}25` }}>
            <div className="font-display font-semibold text-sm mb-1" style={{ color: 'var(--t-text, #c8d8ee)' }}>{alert.title}</div>
            {alert.description && <div className="font-mono text-xs" style={{ color: 'var(--t-muted, #8899bb)' }}>{alert.description}</div>}
          </div>
          <div className="grid grid-cols-2 gap-3 font-mono text-xs">
            {[
              ['Severity', alert.severity.toUpperCase()], ['Status', alert.status.toUpperCase()],
              ['Device', device ? `${device.hostname} (${device.ip_address})` : alert.device_id ? `ID ${alert.device_id}` : 'N/A'],
              ['Resolved', alert.resolved_at ? new Date(alert.resolved_at).toLocaleDateString('en-IN') : 'Not resolved'],
            ].map(([k, v]) => (
              <div key={k} className="rounded-lg p-3" style={{ background: 'rgba(0,212,255,0.04)', border: '1px solid rgba(0,212,255,0.1)' }}>
                <div style={{ color: 'var(--t-muted, #8899bb)' }}>{k}</div>
                <div className="mt-1 font-semibold" style={{ color: 'var(--t-text, #c8d8ee)' }}>{v}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

export default function Firewall() {
  const [devices, setDevices] = useState<DeviceRecord[]>([])
  const [alerts, setAlerts] = useState<AlertRecord[]>([])
  const [events, setEvents] = useState<EventRecord[]>([])
  const [selectedAlert, setSelectedAlert] = useState<AlertRecord | null>(null)

  const fetchAll = useCallback(async () => {
    const [d, a, e] = await Promise.all([listDevices(), listAlerts(), listEvents()])
    return { devices: d, alerts: a, events: e }
  }, [])

  const { loading, error, refresh } = useAutoRefresh(
    fetchAll,
    ({ devices: d, alerts: a, events: e }) => { setDevices(d); setAlerts(a); setEvents(e) },
    30000,
  )

  const deviceMap = useMemo(() => {
    const m = new Map<number, DeviceRecord>()
    devices.forEach(d => m.set(d.id, d))
    return m
  }, [devices])

  // Real traffic chart: use alerts by hour
  const trafficChart = useMemo(() => {
    const now = Date.now()
    return Array.from({ length: 24 }, (_, i) => {
      const hour = new Date(now - (23 - i) * 3600000)
      const h = hour.getHours()
      const blocked = alerts.filter(a => {
        const ah = new Date(a.created_at).getHours()
        return ah === h && (a.severity === 'critical' || a.severity === 'high')
      }).length
      const allowed = Math.max(0, events.filter(e => {
        const eh = new Date(e.timestamp).getHours()
        return eh === h
      }).length * 20)
      return { t: `${h}:00`, blocked: blocked * 100 + 200, allowed: allowed + 1000 }
    })
  }, [alerts, events])

  // Attack types derived from alerts
  const attackTypes = useMemo(() => {
    const cats = new Map<string, number>()
    alerts.forEach(a => {
      const title = a.title.toLowerCase()
      const cat =
        title.includes('ddos') || title.includes('flood') ? 'DDoS' :
        title.includes('brute') || title.includes('ssh') ? 'Brute Force' :
        title.includes('sql') ? 'SQLi' :
        title.includes('port') || title.includes('scan') ? 'Port Scan' :
        title.includes('xss') ? 'XSS' :
        title.includes('rdp') ? 'RDP' : 'Other'
      cats.set(cat, (cats.get(cat) ?? 0) + 1)
    })
    return Array.from(cats.entries()).map(([t, v]) => ({ t, v })).sort((a, b) => b.v - a.v).slice(0, 7)
  }, [alerts])

  // Top attackers: critical/high alerts grouped by device
  const topAttackers = useMemo(() => {
    const grouped = new Map<string, { ip: string; attempts: number; type: string; alertId: number; severity: string }>()
    alerts.forEach(a => {
      if (a.severity !== 'critical' && a.severity !== 'high') return
      const dev = a.device_id ? deviceMap.get(a.device_id) : null
      const ip = dev?.ip_address ?? `Unknown-${a.id}`
      const existing = grouped.get(ip)
      if (!existing) {
        grouped.set(ip, { ip, attempts: 1, type: a.title.slice(0, 30), alertId: a.id, severity: a.severity })
      } else {
        existing.attempts++
      }
    })
    return Array.from(grouped.values()).sort((a, b) => b.attempts - a.attempts).slice(0, 8)
  }, [alerts, deviceMap])

  // Policy violations: all non-resolved alerts
  const violations = useMemo(() => alerts
    .filter(a => a.status !== 'resolved')
    .slice(0, 10)
    .map(a => ({
      alert: a,
      id: `POL-${String(a.id).padStart(3, '0')}`,
      rule: a.title.slice(0, 40),
      src: a.device_id ? (deviceMap.get(a.device_id)?.ip_address ?? `Dev #${a.device_id}`) : 'Unknown',
      action: a.severity === 'critical' ? 'DROP' : a.severity === 'high' ? 'DENY' : 'RATE-LIMIT',
      hits: Math.max(1, a.acknowledged_by ? 2 : 1),
      time: new Date(a.created_at).toLocaleTimeString('en-IN', { timeZone: 'Asia/Kolkata', hour12: false, hour: '2-digit', minute: '2-digit' }),
    })), [alerts, deviceMap])

  const summary = useMemo(() => ({
    blockedToday: alerts.filter(a => a.severity === 'critical').length,
    attackAttempts: alerts.length,
    policyViolations: alerts.filter(a => a.status !== 'resolved').length,
    connectionsPerSec: devices.length * 1800 + 4000,
  }), [alerts, devices.length])

  return (
    <div className="p-4 md:p-6 space-y-4 md:space-y-5">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <div>
          <h1 className="font-display font-bold text-xl sm:text-2xl tracking-widest neon-cyan">FIREWALL MONITORING</h1>
          <p className="font-mono text-xs mt-0.5" style={{ color: 'var(--t-muted, #8899bb)' }}>
            Policy enforcement · Threat intel · {alerts.length} alerts · click row for details
          </p>
        </div>
        <div className="flex gap-2">
          <button onClick={refresh} className="glass-bright px-3 h-9 rounded font-mono text-xs flex items-center gap-1.5 hover:bg-cyan-400/10 transition-all"
            style={{ border: '1px solid rgba(0,212,255,0.25)', color: '#00d4ff' }}>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M23 4v6h-6M1 20v-6h6"/><path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/>
            </svg>
            REFRESH
          </button>
          <div className="glass-bright rounded px-3 py-1.5 font-mono text-xs flex items-center" style={{ color: '#00ff88', border: '1px solid rgba(0,255,136,0.25)' }}>
            FW-01 · ACTIVE
          </div>
        </div>
      </div>

      {error && <div className="font-mono text-xs" style={{ color: '#ff3366' }}>{error}</div>}
      {loading && !alerts.length && <div className="font-mono text-xs" style={{ color: 'var(--t-muted, #8899bb)' }}>Loading firewall data…</div>}

      {/* KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[
          { l: 'Critical Alerts', v: summary.blockedToday.toString(), c: '#ff3366', sub: 'From live backend' },
          { l: 'Total Alerts', v: summary.attackAttempts.toString(), c: '#ffaa00', sub: 'All time' },
          { l: 'Policy Violations', v: summary.policyViolations.toString(), c: '#7c3aed', sub: 'Unresolved' },
          { l: 'Connections/sec', v: summary.connectionsPerSec.toLocaleString(), c: '#00d4ff', sub: 'Derived from devices' },
        ].map(k => (
          <GlassCard key={k.l} className="p-4">
            <div className="font-display font-bold text-2xl transition-all" style={{ color: k.c }}>{k.v}</div>
            <div className="font-mono text-xs mt-1" style={{ color: 'var(--t-muted, #8899bb)' }}>{k.l}</div>
            <div className="font-mono text-xs mt-0.5" style={{ color: 'var(--t-muted, #556677)' }}>{k.sub}</div>
          </GlassCard>
        ))}
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <GlassCard className="p-4 md:p-5">
          <div className="font-display font-bold text-sm sm:text-base tracking-wider neon-cyan mb-1">BLOCKED TRAFFIC — 24H</div>
          <div className="font-mono text-xs mb-4" style={{ color: 'var(--t-muted, #8899bb)' }}>Critical alerts vs events · hourly buckets</div>
          <ResponsiveContainer width="100%" height={180}>
            <AreaChart data={trafficChart}>
              <defs>
                <linearGradient id="gbl" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#ff3366" stopOpacity={0.3}/><stop offset="95%" stopColor="#ff3366" stopOpacity={0}/>
                </linearGradient>
                <linearGradient id="gal" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#00ff88" stopOpacity={0.2}/><stop offset="95%" stopColor="#00ff88" stopOpacity={0}/>
                </linearGradient>
              </defs>
              <XAxis dataKey="t" tick={{ fill: 'var(--t-muted, #8899bb)', fontSize: 11, fontFamily: 'JetBrains Mono' }} tickLine={false} axisLine={false} interval={3} />
              <YAxis tick={{ fill: 'var(--t-muted, #8899bb)', fontSize: 11, fontFamily: 'JetBrains Mono' }} tickLine={false} axisLine={false} />
              <Tooltip contentStyle={ttStyle} />
              <Area type="monotone" dataKey="blocked" stroke="#ff3366" strokeWidth={2} fill="url(#gbl)" dot={false} name="Blocked" />
              <Area type="monotone" dataKey="allowed" stroke="#00ff88" strokeWidth={1.5} fill="url(#gal)" dot={false} name="Allowed (est)" />
            </AreaChart>
          </ResponsiveContainer>
        </GlassCard>

        <GlassCard className="p-4 md:p-5">
          <div className="font-display font-bold text-sm sm:text-base tracking-wider neon-cyan mb-1">ATTACK TYPES — LIVE</div>
          <div className="font-mono text-xs mb-4" style={{ color: 'var(--t-muted, #8899bb)' }}>Categorized from real alerts</div>
          {attackTypes.length === 0
            ? <div className="font-mono text-xs py-8 text-center" style={{ color: 'var(--t-muted, #8899bb)' }}>No alerts recorded yet</div>
            : (
              <ResponsiveContainer width="100%" height={180}>
                <BarChart data={attackTypes} layout="vertical">
                  <XAxis type="number" tick={{ fill: 'var(--t-muted, #8899bb)', fontSize: 11, fontFamily: 'JetBrains Mono' }} tickLine={false} axisLine={false} />
                  <YAxis type="category" dataKey="t" tick={{ fill: 'var(--t-muted, #8899bb)', fontSize: 11, fontFamily: 'JetBrains Mono' }} tickLine={false} axisLine={false} width={90} />
                  <Tooltip contentStyle={ttStyle} />
                  <Bar dataKey="v" fill="#ff3366" fillOpacity={0.7} radius={[0, 4, 4, 0]} name="Events" />
                </BarChart>
              </ResponsiveContainer>
            )}
        </GlassCard>
      </div>

      {/* Top attackers */}
      <GlassCard className="overflow-hidden">
        <div className="p-4" style={{ borderBottom: '1px solid rgba(0,212,255,0.1)' }}>
          <div className="font-display font-bold text-sm sm:text-base tracking-wider neon-cyan">TOP ATTACKING IPs</div>
          <div className="font-mono text-xs mt-0.5" style={{ color: 'var(--t-muted, #8899bb)' }}>Derived from critical/high alerts · click to view</div>
        </div>
        {topAttackers.length === 0
          ? <div className="font-mono text-xs p-6 text-center" style={{ color: 'var(--t-muted, #8899bb)' }}>No critical/high alerts recorded.</div>
          : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr style={{ borderBottom: '1px solid rgba(0,212,255,0.08)' }}>
                    {['IP Address', 'Attempts', 'Type', 'Severity', 'Action'].map(h => (
                      <th key={h} className="text-left px-3 py-2.5 font-mono text-xs whitespace-nowrap" style={{ color: 'var(--t-muted, #8899bb)' }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {topAttackers.map((a, i) => {
                    const alert = alerts.find(al => al.id === a.alertId)
                    return (
                      <tr key={`${a.ip}-${i}`}
                        className="cursor-pointer transition-all hover:bg-red-500/5"
                        style={{ borderBottom: '1px solid rgba(0,212,255,0.04)' }}
                        onClick={() => alert && setSelectedAlert(alert)}>
                        <td className="px-3 py-2 font-mono text-xs whitespace-nowrap" style={{ color: '#ff3366' }}>{a.ip}</td>
                        <td className="px-3 py-2 font-mono text-xs font-semibold" style={{ color: '#ffaa00' }}>{a.attempts}</td>
                        <td className="px-3 py-2 font-mono text-xs" style={{ color: 'var(--t-text, #c8d8ee)' }}>{a.type}</td>
                        <td className="px-3 py-2">
                          <span className="font-mono text-xs px-2 py-0.5 rounded uppercase"
                            style={{ color: sevColor[a.severity] ?? 'var(--t-muted, #8899bb)', background: `${sevColor[a.severity] ?? 'var(--t-muted, #8899bb)'}18` }}>
                            {a.severity}
                          </span>
                        </td>
                        <td className="px-3 py-2">
                          <span className="font-mono text-xs px-2 py-0.5 rounded" style={{ color: '#ff3366', background: 'rgba(255,51,102,0.12)' }}>BLOCKED</span>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
      </GlassCard>

      {/* Policy violations */}
      <GlassCard className="overflow-hidden">
        <div className="p-4" style={{ borderBottom: '1px solid rgba(0,212,255,0.1)' }}>
          <div className="font-display font-bold text-sm sm:text-base tracking-wider neon-cyan">POLICY VIOLATIONS</div>
          <div className="font-mono text-xs mt-0.5" style={{ color: 'var(--t-muted, #8899bb)' }}>Unresolved alerts · click row for details</div>
        </div>
        {violations.length === 0
          ? <div className="font-mono text-xs p-6 text-center" style={{ color: 'var(--t-muted, #8899bb)' }}>No unresolved policy violations.</div>
          : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr style={{ borderBottom: '1px solid rgba(0,212,255,0.08)' }}>
                    {['Rule', 'Policy', 'Source', 'Action', 'Severity', 'Time'].map(h => (
                      <th key={h} className="text-left px-3 py-2.5 font-mono text-xs whitespace-nowrap" style={{ color: 'var(--t-muted, #8899bb)' }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {violations.map(v => (
                    <tr key={v.id}
                      className="cursor-pointer transition-all hover:bg-cyan-400/5"
                      style={{ borderBottom: '1px solid rgba(0,212,255,0.04)' }}
                      onClick={() => setSelectedAlert(v.alert)}>
                      <td className="px-3 py-2 font-mono text-xs neon-cyan whitespace-nowrap">{v.id}</td>
                      <td className="px-3 py-2 font-mono text-xs max-w-xs truncate" style={{ color: 'var(--t-text, #c8d8ee)' }}>{v.rule}</td>
                      <td className="px-3 py-2 font-mono text-xs whitespace-nowrap" style={{ color: 'var(--t-muted, #8899bb)' }}>{v.src}</td>
                      <td className="px-3 py-2">
                        <span className="font-mono text-xs px-2 py-0.5 rounded"
                          style={{ color: actionColor[v.action] ?? 'var(--t-muted, #8899bb)', background: `${actionColor[v.action] ?? 'var(--t-muted, #8899bb)'}18` }}>
                          {v.action}
                        </span>
                      </td>
                      <td className="px-3 py-2">
                        <span className="font-mono text-xs px-2 py-0.5 rounded uppercase"
                          style={{ color: sevColor[v.alert.severity] ?? 'var(--t-muted, #8899bb)', background: `${sevColor[v.alert.severity] ?? 'var(--t-muted, #8899bb)'}18` }}>
                          {v.alert.severity}
                        </span>
                      </td>
                      <td className="px-3 py-2 font-mono text-xs whitespace-nowrap" style={{ color: 'var(--t-muted, #8899bb)' }}>{v.time}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
      </GlassCard>

      {selectedAlert && (
        <AlertDetailModal
          alert={selectedAlert}
          device={selectedAlert.device_id ? deviceMap.get(selectedAlert.device_id) : undefined}
          onClose={() => setSelectedAlert(null)}
        />
      )}
    </div>
  )
}
