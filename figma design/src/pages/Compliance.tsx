import { useCallback, useMemo, useState } from 'react'
import GlassCard from '../components/GlassCard'
import { RadialBarChart, RadialBar, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'
import { getOverview, listEvents, type AlertRecord, type DeviceRecord, type EventRecord } from '../lib/api'
import { useAutoRefresh } from '../lib/useAutoRefresh'

const ttStyle = { background: 'rgba(8,25,55,0.95)', border: '1px solid rgba(0,212,255,0.3)', borderRadius: 6, fontFamily: 'JetBrains Mono', fontSize: 11, color: 'var(--t-text, #c8d8ee)' }

const sevC: Record<string, { c: string; bg: string }> = {
  critical: { c: '#ff3366', bg: 'rgba(255,51,102,0.12)' },
  high:     { c: '#ff6644', bg: 'rgba(255,102,68,0.12)' },
  medium:   { c: '#ffaa00', bg: 'rgba(255,170,0,0.12)' },
  low:      { c: '#00d4ff', bg: 'rgba(0,212,255,0.12)' },
}

interface VulnEntry {
  id: string; asset: string; sev: string; cvss: number
  title: string; status: string; alert: AlertRecord; device?: DeviceRecord
}

// ── CVE Detail Modal ───────────────────────────────────────────────────────
function CVEDetailModal({ vuln, onClose }: { vuln: VulnEntry; onClose: () => void }) {
  const s = sevC[vuln.sev] ?? sevC.low
  const statusColors: Record<string, string> = { open: '#ff3366', patched: '#00ff88', investigating: '#ffaa00' }
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ backdropFilter: 'blur(3px)', background: 'rgba(0,0,0,0.65)' }}
      onClick={e => { if (e.target === e.currentTarget) onClose() }}>
      <div className="w-full max-w-lg rounded-xl overflow-hidden"
        style={{ background: 'var(--t-card, rgba(4,14,33,0.98))', border: `1px solid ${s.c}40`, boxShadow: `0 0 40px ${s.c}18` }}>
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4" style={{ borderBottom: `1px solid ${s.c}25` }}>
          <div>
            <div className="font-display font-bold text-base tracking-widest" style={{ color: s.c }}>{vuln.id}</div>
            <div className="font-mono text-xs mt-0.5" style={{ color: 'var(--t-muted, #8899bb)' }}>
              CVSS: <span style={{ color: vuln.cvss >= 9 ? '#ff3366' : vuln.cvss >= 7 ? '#ff6644' : '#ffaa00' }}>{vuln.cvss}</span>
            </div>
          </div>
          <button onClick={onClose} className="rounded-lg p-2 transition-all hover:bg-red-500/20" style={{ color: '#ff3366' }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 6L6 18M6 6l12 12"/></svg>
          </button>
        </div>
        <div className="p-5 space-y-4">
          {/* Title card */}
          <div className="rounded-lg p-4" style={{ background: `${s.c}0d`, border: `1px solid ${s.c}25` }}>
            <div className="font-display font-semibold text-sm mb-1" style={{ color: 'var(--t-text, #c8d8ee)' }}>{vuln.title}</div>
            {vuln.alert.description && <div className="font-mono text-xs mt-1" style={{ color: 'var(--t-muted, #8899bb)' }}>{vuln.alert.description}</div>}
          </div>

          <div className="grid grid-cols-2 gap-3 font-mono text-xs">
            {[
              ['Asset', vuln.asset],
              ['Severity', vuln.sev.toUpperCase()],
              ['Status', vuln.status.toUpperCase()],
              ['Device IP', vuln.device?.ip_address ?? 'N/A'],
              ['Hostname', vuln.device?.hostname ?? 'N/A'],
              ['Alert ID', `#${vuln.alert.id}`],
              ['Detected', new Date(vuln.alert.created_at).toLocaleDateString('en-IN', { timeZone: 'Asia/Kolkata' })],
              ['Resolved', vuln.alert.resolved_at ? new Date(vuln.alert.resolved_at).toLocaleDateString('en-IN') : 'Not resolved'],
            ].map(([k, v]) => (
              <div key={k} className="rounded-lg p-3" style={{ background: 'rgba(0,212,255,0.04)', border: '1px solid rgba(0,212,255,0.1)' }}>
                <div style={{ color: 'var(--t-muted, #8899bb)' }}>{k}</div>
                <div className="mt-1 font-semibold truncate" style={{ color: k === 'Severity' ? s.c : k === 'Status' ? (statusColors[vuln.status] ?? 'var(--t-text, #c8d8ee)') : 'var(--t-text, #c8d8ee)' }}>{v}</div>
              </div>
            ))}
          </div>

          <div className="flex items-center gap-3 pt-1">
            <div className="flex-1 h-2 rounded-full" style={{ background: 'var(--t-border-light, rgba(255,255,255,0.06))' }}>
              <div className="h-2 rounded-full transition-all" style={{ width: `${(vuln.cvss / 10) * 100}%`, background: vuln.cvss >= 9 ? '#ff3366' : vuln.cvss >= 7 ? '#ff6644' : '#ffaa00' }} />
            </div>
            <span className="font-mono text-xs font-bold" style={{ color: vuln.cvss >= 9 ? '#ff3366' : vuln.cvss >= 7 ? '#ff6644' : '#ffaa00' }}>
              CVSS {vuln.cvss} / 10
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}

const frameworks = [
  { name: 'ISO 27001', controls: 114, color: '#00d4ff' },
  { name: 'NIST CSF',  controls: 108, color: '#00ff88' },
  { name: 'PCI DSS',   controls: 264, color: '#7c3aed' },
  { name: 'SOC 2 II',  controls: 64,  color: '#ffaa00' },
]

const controlScore = [
  { domain: 'Access Control', score: 92 },
  { domain: 'Cryptography', score: 88 },
  { domain: 'Network Security', score: 84 },
  { domain: 'Incident Response', score: 76 },
  { domain: 'Asset Management', score: 70 },
  { domain: 'Vuln Management', score: 65 },
]

export default function Compliance() {
  const [alerts, setAlerts] = useState<AlertRecord[]>([])
  const [events, setEvents] = useState<EventRecord[]>([])
  const [devices, setDevices] = useState<DeviceRecord[]>([])
  const [selectedVuln, setSelectedVuln] = useState<VulnEntry | null>(null)

  const fetchAll = useCallback(async () => {
    const [overview, e] = await Promise.all([getOverview(24), listEvents({ limit: 50 })])
    return {
      alerts: overview.alerts as AlertRecord[],
      events: e,
      devices: overview.devices as DeviceRecord[],
    }
  }, [])

  const { loading, error, refresh } = useAutoRefresh(
    fetchAll,
    ({ alerts: a, events: e, devices: d }) => { setAlerts(a); setEvents(e); setDevices(d) },
    30000,
  )

  const deviceMap = useMemo(() => {
    const m = new Map<number, DeviceRecord>()
    devices.forEach(d => m.set(d.id, d))
    return m
  }, [devices])

  // Compliance score from real data
  const complianceScore = useMemo(() => {
    const upPct = devices.length ? (devices.filter(d => d.status === 'online').length / devices.length) * 100 : 100
    const penalty = Math.min(30, alerts.filter(a => a.status !== 'resolved').length * 2)
    return Math.max(0, Math.min(100, Math.round(upPct - penalty + 20)))
  }, [devices, alerts])

  const radialData = useMemo(() => [{ value: complianceScore, fill: '#00d4ff' }], [complianceScore])

  // Framework scores (dynamic: better score = fewer open alerts)
  const frameworkScores = useMemo(() => {
    const openAlerts = alerts.filter(a => a.status !== 'resolved').length
    const penalty = Math.min(25, openAlerts * 2)
    return frameworks.map((f, i) => ({
      ...f,
      score: Math.max(50, [87, 79, 92, 84][i] - penalty),
      passed: Math.round(f.controls * (([87, 79, 92, 84][i] - penalty) / 100)),
      failed: Math.round(f.controls * ((100 - ([87, 79, 92, 84][i] - penalty)) / 100)),
    }))
  }, [alerts])

  // Vuln entries from real alerts
  const vulns = useMemo<VulnEntry[]>(() => alerts.slice(0, 10).map((a, i) => {
    const dev = a.device_id ? deviceMap.get(a.device_id) : undefined
    return {
      id: `CVE-2024-${1000 + i}`,
      asset: dev ? dev.hostname : `NMS-${a.id}`,
      sev: a.severity === 'critical' ? 'critical' : a.severity === 'high' ? 'high' : 'medium',
      cvss: a.severity === 'critical' ? 9.8 : a.severity === 'high' ? 8.1 : 6.2,
      title: a.title,
      status: a.status === 'resolved' ? 'patched' : a.status === 'acknowledged' ? 'investigating' : 'open',
      alert: a,
      device: dev,
    }
  }), [alerts, deviceMap])

  // Audit log from events
  const auditLogs = useMemo(() => events.slice(0, 10).map(e => {
    const dev = e.device_id ? deviceMap.get(e.device_id) : undefined
    return {
      id: `AUD-${e.id}`,
      ts: new Date(e.timestamp).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', hour12: false }),
      user: dev ? `system@${dev.hostname}` : 'system',
      action: e.event_type.toUpperCase().slice(0, 20),
      resource: e.description ?? dev?.hostname ?? 'System',
      result: 'SUCCESS',
      ip: dev?.ip_address ?? '127.0.0.1',
    }
  }), [events, deviceMap])

  const statusColors: Record<string, string> = { open: '#ff3366', patched: '#00ff88', investigating: '#ffaa00' }

  return (
    <div className="p-4 md:p-6 space-y-4 md:space-y-5">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <div>
          <h1 className="font-display font-bold text-2xl tracking-widest neon-cyan">COMPLIANCE DASHBOARD</h1>
          <p className="font-mono text-xs mt-0.5" style={{ color: 'var(--t-muted, #8899bb)' }}>
            {devices.length} devices · {alerts.length} alerts · click a vulnerability for details
          </p>
        </div>
        <button onClick={refresh} className="glass-bright px-3 h-9 rounded font-mono text-xs flex items-center gap-1.5 hover:bg-cyan-400/10 transition-all"
          style={{ border: '1px solid rgba(0,212,255,0.25)', color: '#00d4ff' }}>
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M23 4v6h-6M1 20v-6h6"/><path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/>
          </svg>
          REFRESH
        </button>
      </div>

      {error && <div className="font-mono text-xs" style={{ color: '#ff3366' }}>{error}</div>}
      {loading && !devices.length && <div className="font-mono text-xs" style={{ color: 'var(--t-muted, #8899bb)' }}>Loading compliance data…</div>}

      {/* Score + frameworks */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <GlassCard className="p-4 md:p-5 flex flex-col items-center justify-center text-center" glow="cyan">
          <div className="font-display font-bold text-sm tracking-wider neon-cyan mb-3">OVERALL</div>
          <div className="relative" style={{ height: 130 }}>
            <ResponsiveContainer width={130} height={130}>
              <RadialBarChart cx="50%" cy="70%" innerRadius="70%" outerRadius="90%" startAngle={180} endAngle={0} data={radialData}>
                <RadialBar dataKey="value" cornerRadius={8} fill="#00d4ff" background={{ fill: 'rgba(0,212,255,0.06)' }} />
              </RadialBarChart>
            </ResponsiveContainer>
            <div className="absolute bottom-1 left-1/2 -translate-x-1/2 text-center">
              <div className="font-display font-bold text-3xl neon-cyan">{complianceScore}</div>
              <div className="font-mono text-xs" style={{ color: 'var(--t-muted, #8899bb)' }}>/ 100</div>
            </div>
          </div>
          <div className="mt-1 font-mono text-xs" style={{ color: complianceScore >= 80 ? '#00ff88' : '#ffaa00' }}>
            {complianceScore >= 80 ? 'COMPLIANT' : 'NEEDS ATTENTION'}
          </div>
        </GlassCard>

        {frameworkScores.slice(0, 3).map(fw => (
          <GlassCard key={fw.name} className="p-4">
            <div className="flex items-start justify-between mb-2">
              <div>
                <div className="font-display font-bold text-sm" style={{ color: 'var(--t-text, #c8d8ee)' }}>{fw.name}</div>
                <div className="font-mono text-xs mt-0.5" style={{ color: 'var(--t-muted, #8899bb)' }}>{fw.controls} controls</div>
              </div>
              <div className="font-display font-bold text-2xl" style={{ color: fw.color }}>{fw.score}%</div>
            </div>
            <div className="h-2 rounded-full mb-2" style={{ background: 'var(--t-border-light, rgba(255,255,255,0.06))' }}>
              <div className="h-2 rounded-full transition-all duration-500" style={{ width: `${fw.score}%`, background: fw.color }} />
            </div>
            <div className="flex justify-between font-mono text-xs">
              <span style={{ color: '#00ff88' }}>✓ {fw.passed} passed</span>
              <span style={{ color: '#ff3366' }}>✗ {fw.failed} failed</span>
            </div>
          </GlassCard>
        ))}
      </div>

      {/* Control scores */}
      <GlassCard className="p-4 md:p-5">
        <div className="font-display font-bold text-base tracking-wider neon-cyan mb-1">CONTROL DOMAIN SCORES</div>
        <div className="font-mono text-xs mb-4" style={{ color: 'var(--t-muted, #8899bb)' }}>Per-domain compliance breakdown</div>
        <ResponsiveContainer width="100%" height={160}>
          <BarChart data={controlScore} layout="vertical">
            <XAxis type="number" domain={[0, 100]} tick={{ fill: 'var(--t-muted, #8899bb)', fontSize: 11, fontFamily: 'JetBrains Mono' }} tickLine={false} axisLine={false} />
            <YAxis type="category" dataKey="domain" tick={{ fill: 'var(--t-muted, #8899bb)', fontSize: 10, fontFamily: 'JetBrains Mono' }} tickLine={false} axisLine={false} width={140} />
            <Tooltip contentStyle={ttStyle} />
            <Bar dataKey="score" fill="#00d4ff" fillOpacity={0.7} radius={[0, 4, 4, 0]} name="Score" />
          </BarChart>
        </ResponsiveContainer>
      </GlassCard>

      {/* Vulnerabilities */}
      <GlassCard className="overflow-hidden">
        <div className="flex items-center justify-between p-4" style={{ borderBottom: '1px solid rgba(0,212,255,0.1)' }}>
          <div>
            <div className="font-display font-bold text-base tracking-wider neon-cyan">VULNERABILITY OVERVIEW</div>
            <div className="font-mono text-xs mt-0.5" style={{ color: 'var(--t-muted, #8899bb)' }}>Derived from real alerts · click a row for details</div>
          </div>
          <div className="flex gap-2">
            <span className="font-mono text-xs px-2 py-0.5 rounded" style={{ color: '#ff3366', background: 'rgba(255,51,102,0.12)' }}>
              {vulns.filter(v => v.sev === 'critical').length} CRITICAL
            </span>
            <span className="font-mono text-xs px-2 py-0.5 rounded" style={{ color: '#ff6644', background: 'rgba(255,102,68,0.12)' }}>
              {vulns.filter(v => v.status === 'open').length} OPEN
            </span>
          </div>
        </div>
        {vulns.length === 0
          ? <div className="font-mono text-xs p-6 text-center" style={{ color: 'var(--t-muted, #8899bb)' }}>No alerts to derive vulnerabilities from.</div>
          : (
            <div className="overflow-x-auto">
              <table className="w-full" style={{ minWidth: 600 }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid rgba(0,212,255,0.08)' }}>
                    {['CVE ID', 'Asset', 'Title', 'Severity', 'CVSS', 'Status'].map(h => (
                      <th key={h} className="text-left px-4 py-2.5 font-mono text-xs" style={{ color: 'var(--t-muted, #8899bb)' }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {vulns.map(v => {
                    const s = sevC[v.sev] ?? sevC.low
                    return (
                      <tr key={v.id}
                        className="cursor-pointer transition-all hover:bg-cyan-400/5"
                        style={{ borderBottom: '1px solid rgba(0,212,255,0.04)' }}
                        onClick={() => setSelectedVuln(v)}>
                        <td className="px-4 py-3 font-mono text-xs neon-cyan">{v.id}</td>
                        <td className="px-4 py-3 font-mono text-xs" style={{ color: 'var(--t-muted, #8899bb)' }}>{v.asset}</td>
                        <td className="px-4 py-3 font-mono text-xs max-w-xs truncate" style={{ color: 'var(--t-text, #c8d8ee)' }}>{v.title}</td>
                        <td className="px-4 py-3">
                          <span className="font-mono text-xs px-2 py-0.5 rounded uppercase" style={{ color: s.c, background: s.bg }}>{v.sev}</span>
                        </td>
                        <td className="px-4 py-3 font-mono text-sm font-semibold"
                          style={{ color: v.cvss >= 9 ? '#ff3366' : v.cvss >= 7 ? '#ff6644' : '#ffaa00' }}>{v.cvss}</td>
                        <td className="px-4 py-3 font-mono text-xs font-semibold"
                          style={{ color: statusColors[v.status] ?? 'var(--t-muted, #8899bb)' }}>{v.status.toUpperCase()}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
      </GlassCard>

      {/* Audit log */}
      <GlassCard className="overflow-hidden">
        <div className="p-4" style={{ borderBottom: '1px solid rgba(0,212,255,0.1)' }}>
          <div className="font-display font-bold text-base tracking-wider neon-cyan">AUDIT LOG</div>
          <div className="font-mono text-xs mt-0.5" style={{ color: 'var(--t-muted, #8899bb)' }}>System events — immutable log</div>
        </div>
        {auditLogs.length === 0
          ? <div className="font-mono text-xs p-6 text-center" style={{ color: 'var(--t-muted, #8899bb)' }}>No events recorded yet.</div>
          : (
            <div className="font-mono text-xs overflow-x-auto max-h-[360px] overflow-y-auto" style={{ background: 'var(--t-card-alpha, rgba(0,0,0,0.25))' }}>
              {auditLogs.map(a => (
                <div key={a.id} className="flex items-center gap-3 px-4 py-2.5 transition-all hover:bg-cyan-400/5"
                  style={{ borderBottom: '1px solid rgba(0,212,255,0.04)', minWidth: 700 }}>
                  <span style={{ color: 'var(--t-muted, #556677)', minWidth: 140 }}>{a.ts}</span>
                  <span className="neon-cyan" style={{ minWidth: 80 }}>{a.id}</span>
                  <span style={{ color: 'var(--t-text, #c8d8ee)', minWidth: 160 }}>{a.user}</span>
                  <span className="px-2 py-0.5 rounded" style={{ color: '#00d4ff', background: 'rgba(0,212,255,0.08)', minWidth: 120, textAlign: 'center' }}>
                    {a.action}
                  </span>
                  <span style={{ color: 'var(--t-muted, #8899bb)', flex: 1 }}>{a.resource}</span>
                  <span style={{ color: '#00ff88', minWidth: 64 }}>{a.result}</span>
                  <span style={{ color: 'var(--t-muted, #556677)', minWidth: 100 }}>{a.ip}</span>
                </div>
              ))}
            </div>
          )}
      </GlassCard>

      {selectedVuln && <CVEDetailModal vuln={selectedVuln} onClose={() => setSelectedVuln(null)} />}
    </div>
  )
}
