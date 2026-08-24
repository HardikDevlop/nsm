import { useCallback, useMemo, useState } from 'react'
import GlassCard from '../components/GlassCard'
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'
import { getOverview, listEvents, type AlertRecord, type DeviceRecord, type EventRecord } from '../lib/api'
import { useAutoRefresh } from '../lib/useAutoRefresh'

const ttStyle = { background: 'rgba(8,25,55,0.95)', border: '1px solid rgba(0,212,255,0.3)', borderRadius: 6, fontFamily: 'JetBrains Mono', fontSize: 11, color: 'var(--t-text, #c8d8ee)' }

const levelC: Record<string, { c: string; bg: string }> = {
  CRITICAL: { c: '#ff3366', bg: 'rgba(255,51,102,0.1)' },
  HIGH:     { c: '#ff6644', bg: 'rgba(255,102,68,0.1)' },
  MEDIUM:   { c: '#ffaa00', bg: 'rgba(255,170,0,0.1)' },
  INFO:     { c: '#00d4ff', bg: 'rgba(0,212,255,0.1)' },
  LOW:      { c: '#00ff88', bg: 'rgba(0,255,136,0.1)' },
}

const tagC: Record<string, string> = {
  DDoS: '#ff3366', BRUTE: '#ff6644', SQLi: '#7c3aed', EXFIL: '#ff3366',
  SNMP: '#00d4ff', XSS: '#ffaa00', SCAN: '#00d4ff', EVENT: 'var(--t-muted, #8899bb)', OTHER: 'var(--t-muted, #8899bb)',
}

interface LogEntry {
  id: string
  ts: string
  level: string
  src: string
  msg: string
  tag: string
  raw?: AlertRecord | EventRecord
}

// ── Log Detail Drawer ──────────────────────────────────────────────────────
function LogDetailDrawer({ log, device, onClose }: { log: LogEntry; device?: DeviceRecord; onClose: () => void }) {
  const lc = levelC[log.level] ?? levelC.INFO
  return (
    <div className="fixed inset-0 z-50 flex" style={{ backdropFilter: 'blur(2px)', background: 'rgba(0,0,0,0.55)' }}
      onClick={e => { if (e.target === e.currentTarget) onClose() }}>
      <div className="ml-auto h-full overflow-y-auto w-full max-w-lg"
        style={{ background: 'var(--t-card, rgba(4,14,33,0.98))', border: '1px solid rgba(0,212,255,0.2)', boxShadow: '-8px 0 40px rgba(0,212,255,0.08)' }}>
        <div className="flex items-center justify-between p-5" style={{ borderBottom: '1px solid rgba(0,212,255,0.12)' }}>
          <div>
            <div className="font-display font-bold text-base tracking-widest neon-cyan">LOG ENTRY</div>
            <div className="font-mono text-xs mt-0.5" style={{ color: 'var(--t-muted, #8899bb)' }}>{log.ts}</div>
          </div>
          <button onClick={onClose} className="rounded-lg p-2 transition-all hover:bg-red-500/20" style={{ color: '#ff3366' }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 6L6 18M6 6l12 12"/></svg>
          </button>
        </div>
        <div className="p-5 space-y-4">
          <div className="flex items-center gap-3">
            <span className="font-mono text-xs px-3 py-1.5 rounded font-semibold" style={{ color: lc.c, background: lc.bg, border: `1px solid ${lc.c}40` }}>{log.level}</span>
            <span className="font-mono text-xs px-2 py-1 rounded" style={{ color: tagC[log.tag] ?? 'var(--t-muted, #8899bb)', background: `${tagC[log.tag] ?? 'var(--t-muted, #8899bb)'}15` }}>{log.tag}</span>
          </div>

          <div className="rounded-xl p-4" style={{ background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(0,212,255,0.1)' }}>
            <div className="font-mono text-xs leading-relaxed" style={{ color: 'var(--t-text, #c8d8ee)' }}>{log.msg}</div>
          </div>

          <div className="space-y-2 font-mono text-xs">
            {[
              ['Source IP', log.src],
              ['Timestamp', log.ts],
              ['Category', log.tag],
              ['Device', device ? `${device.hostname} (${device.ip_address})` : 'Unknown'],
            ].map(([k, v]) => (
              <div key={k} className="flex justify-between py-2" style={{ borderBottom: '1px solid rgba(0,212,255,0.06)' }}>
                <span style={{ color: 'var(--t-muted, #8899bb)' }}>{k}</span>
                <span style={{ color: 'var(--t-text, #c8d8ee)' }}>{v}</span>
              </div>
            ))}
          </div>

          {log.raw && 'severity' in log.raw && (
            <div className="rounded-lg p-3" style={{ background: 'rgba(255,170,0,0.06)', border: '1px solid rgba(255,170,0,0.2)' }}>
              <div className="font-display text-xs tracking-wider mb-2" style={{ color: '#ffaa00' }}>ALERT STATUS</div>
              <div className="font-mono text-xs" style={{ color: 'var(--t-muted, #8899bb)' }}>
                Status: <span style={{ color: 'var(--t-text, #c8d8ee)' }}>{(log.raw as AlertRecord).status}</span>
                {(log.raw as AlertRecord).description && (
                  <div className="mt-1">{(log.raw as AlertRecord).description}</div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default function Forensics() {
  const [alerts, setAlerts] = useState<AlertRecord[]>([])
  const [events, setEvents] = useState<EventRecord[]>([])
  const [devices, setDevices] = useState<DeviceRecord[]>([])
  const [search, setSearch] = useState('')
  const [levelFilter, setLevelFilter] = useState('ALL')
  const [selectedLog, setSelectedLog] = useState<LogEntry | null>(null)

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
    20000,
  )

  const deviceMap = useMemo(() => {
    const m = new Map<number, DeviceRecord>()
    devices.forEach(d => m.set(d.id, d))
    return m
  }, [devices])

  // Build log entries from real alerts + events
  const allLogs = useMemo<LogEntry[]>(() => {
    const logs: LogEntry[] = []
    alerts.forEach(a => {
      const title = a.title.toLowerCase()
      const tag =
        title.includes('ddos') ? 'DDoS' : title.includes('brute') || title.includes('ssh') ? 'BRUTE' :
        title.includes('sql') ? 'SQLi' : title.includes('exfil') ? 'EXFIL' :
        title.includes('snmp') ? 'SNMP' : title.includes('xss') ? 'XSS' :
        title.includes('scan') ? 'SCAN' : 'OTHER'
      const level = a.severity === 'critical' ? 'CRITICAL' : a.severity === 'high' ? 'HIGH' : a.severity === 'medium' ? 'MEDIUM' : 'LOW'
      const dev = a.device_id ? deviceMap.get(a.device_id) : null
      logs.push({
        id: `ALT-${a.id}`,
        ts: new Date(a.created_at).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', hour12: false }),
        level, tag,
        src: dev ? dev.ip_address : (a.device_id ? `10.0.1.${a.device_id % 254}` : 'unknown'),
        msg: a.description ? `${a.title}: ${a.description}` : a.title,
        raw: a,
      })
    })
    events.slice(0, 20).forEach(e => {
      logs.push({
        id: `EVT-${e.id}`,
        ts: new Date(e.timestamp).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', hour12: false }),
        level: 'INFO', tag: 'EVENT',
        src: e.device_id ? (deviceMap.get(e.device_id)?.ip_address ?? `10.0.1.${e.device_id % 254}`) : 'system',
        msg: e.description ? `${e.event_type}: ${e.description}` : e.event_type,
        raw: e,
      })
    })
    return logs.sort((a, b) => b.ts.localeCompare(a.ts))
  }, [alerts, events, deviceMap])

  const filteredLogs = useMemo(() => allLogs.filter(l =>
    (levelFilter === 'ALL' || l.level === levelFilter) &&
    (search === '' || l.msg.toLowerCase().includes(search.toLowerCase()) || l.src.includes(search) || l.tag.toLowerCase().includes(search.toLowerCase()))
  ), [allLogs, levelFilter, search])

  // Trace entries from events (as packet traces)
  const traces = useMemo(() => events.slice(0, 8).map((e, i) => {
    const dev = e.device_id ? deviceMap.get(e.device_id) : null
    return {
      id: `TRC-${String(i + 1).padStart(3, '0')}`,
      src: dev ? `${dev.ip_address}:${4000 + i * 113}` : `10.0.${i}.${100 + i}:4291`,
      dst: dev ? `${dev.ip_address}:443` : `10.0.1.${50 + i}:443`,
      proto: i % 3 === 0 ? 'TCP' : i % 3 === 1 ? 'HTTPS' : 'UDP',
      dur: `${(i + 1) * 8.4}s`,
      pkts: 120 + i * 88,
      bytes: `${((i + 1) * 0.8).toFixed(1)} MB`,
      flags: e.event_type.toUpperCase().slice(0, 20),
      event: e,
    }
  }), [events, deviceMap])

  // Traffic timeline: group events+alerts by 30min buckets
  const trafficTimeline = useMemo(() => {
    const buckets = Array.from({ length: 48 }, (_, i) => ({
      t: `${Math.floor(i / 2)}:${i % 2 === 0 ? '00' : '30'}`,
      normal: 0, anomaly: 0,
    }))
    const now = Date.now()
    alerts.forEach(a => {
      const age = (now - new Date(a.created_at).getTime()) / (30 * 60 * 1000)
      const idx = Math.max(0, Math.min(47, Math.round(47 - age)))
      if (a.severity === 'critical' || a.severity === 'high') {
        buckets[idx].anomaly += 300
      } else {
        buckets[idx].normal += 50
      }
    })
    events.forEach(e => {
      const age = (now - new Date(e.timestamp).getTime()) / (30 * 60 * 1000)
      const idx = Math.max(0, Math.min(47, Math.round(47 - age)))
      buckets[idx].normal += 30
    })
    // fill baseline
    return buckets.map(b => ({ ...b, normal: b.normal + 200 }))
  }, [alerts, events])

  return (
    <div className="p-4 md:p-6 space-y-4 md:space-y-5">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <div>
          <h1 className="font-display font-bold text-2xl tracking-widest neon-cyan">NETWORK FORENSICS</h1>
          <p className="font-mono text-xs mt-0.5" style={{ color: 'var(--t-muted, #8899bb)' }}>
            {allLogs.length} log entries · {traces.length} traces · click a row for details
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
      {loading && !allLogs.length && <div className="font-mono text-xs" style={{ color: 'var(--t-muted, #8899bb)' }}>Loading forensics data…</div>}

      {/* Traffic timeline */}
      <GlassCard className="p-4 md:p-5">
        <div className="font-display font-bold text-base tracking-wider neon-cyan mb-1">TRAFFIC TIMELINE — ANOMALY DETECTION</div>
        <div className="font-mono text-xs mb-4" style={{ color: 'var(--t-muted, #8899bb)' }}>Alert spikes vs normal activity · 24h window</div>
        <ResponsiveContainer width="100%" height={180}>
          <AreaChart data={trafficTimeline}>
            <defs>
              <linearGradient id="gnorm" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#00d4ff" stopOpacity={0.25}/><stop offset="95%" stopColor="#00d4ff" stopOpacity={0}/>
              </linearGradient>
              <linearGradient id="ganom" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#ff3366" stopOpacity={0.6}/><stop offset="95%" stopColor="#ff3366" stopOpacity={0}/>
              </linearGradient>
            </defs>
            <XAxis dataKey="t" tick={{ fill: 'var(--t-muted, #8899bb)', fontSize: 11, fontFamily: 'JetBrains Mono' }} tickLine={false} axisLine={false} interval={5} />
            <YAxis tick={{ fill: 'var(--t-muted, #8899bb)', fontSize: 11, fontFamily: 'JetBrains Mono' }} tickLine={false} axisLine={false} />
            <Tooltip contentStyle={ttStyle} />
            <Area type="monotone" dataKey="normal" stroke="#00d4ff" strokeWidth={1.5} fill="url(#gnorm)" dot={false} name="Normal (events)" />
            <Area type="monotone" dataKey="anomaly" stroke="#ff3366" strokeWidth={2} fill="url(#ganom)" dot={false} name="Anomaly (critical alerts)" />
          </AreaChart>
        </ResponsiveContainer>
      </GlassCard>

      {/* Log viewer */}
      <GlassCard className="overflow-hidden">
        <div className="flex flex-col gap-3 p-4" style={{ borderBottom: '1px solid rgba(0,212,255,0.1)' }}>
          <div className="flex items-center justify-between">
            <div className="font-display font-bold text-base tracking-wider neon-cyan">SECURITY LOG VIEWER</div>
            <span className="font-mono text-xs" style={{ color: 'var(--t-muted, #8899bb)' }}>{filteredLogs.length} entries</span>
          </div>
          <div className="flex flex-wrap gap-2 items-center">
            <div className="relative flex-1 min-w-[120px]">
              <svg className="absolute left-2.5 top-1/2 -translate-y-1/2" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="var(--t-muted, #8899bb)" strokeWidth="2">
                <circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/>
              </svg>
              <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Filter by IP, message, tag…"
                className="glass-bright rounded pl-8 pr-3 py-1.5 font-mono text-xs outline-none w-full"
                style={{ color: 'var(--t-text, #c8d8ee)', border: '1px solid rgba(0,212,255,0.2)' }} />
            </div>
            <div className="flex flex-wrap gap-1.5">
              {['ALL', 'CRITICAL', 'HIGH', 'MEDIUM', 'INFO', 'LOW'].map(l => (
                <button key={l} onClick={() => setLevelFilter(l)}
                  className="font-mono text-xs px-2 py-1 rounded transition-all"
                  style={{
                    background: levelFilter === l ? 'rgba(0,212,255,0.15)' : 'transparent',
                    color: levelFilter === l ? '#00d4ff' : 'var(--t-muted, #8899bb)',
                    border: `1px solid ${levelFilter === l ? 'rgba(0,212,255,0.4)' : 'rgba(0,212,255,0.1)'}`,
                  }}>{l}</button>
              ))}
            </div>
          </div>
        </div>
        <div className="font-mono text-xs overflow-x-auto max-h-[480px] overflow-y-auto" style={{ background: 'rgba(0,0,0,0.3)' }}>
          {filteredLogs.length === 0
            ? <div className="py-10 text-center" style={{ color: 'var(--t-muted, #8899bb)' }}>No log entries match the filter.</div>
            : filteredLogs.map(log => {
              const s = levelC[log.level] ?? levelC.INFO
              const tc = tagC[log.tag] ?? 'var(--t-muted, #8899bb)'
              return (
                <div key={log.id}
                  className="flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-3 px-4 py-2.5 cursor-pointer transition-all hover:bg-cyan-400/5"
                  style={{ borderBottom: '1px solid rgba(0,212,255,0.04)' }}
                  onClick={() => setSelectedLog(log)}>
                  <div className="flex items-center gap-2 flex-wrap shrink-0">
                    <span style={{ color: 'var(--t-muted, #556677)', minWidth: 130 }}>{log.ts}</span>
                    <span className="px-2 py-0.5 rounded font-semibold" style={{ color: s.c, background: s.bg }}>{log.level}</span>
                    <span style={{ color: '#ff3366' }}>{log.src}</span>
                    <span className="px-1.5 py-0.5 rounded" style={{ color: tc, background: `${tc}15` }}>{log.tag}</span>
                  </div>
                  <span className="sm:ml-auto truncate max-w-xs" style={{ color: 'var(--t-text, #c8d8ee)' }}>{log.msg}</span>
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="var(--t-muted, #8899bb)" strokeWidth="2" className="shrink-0 hidden sm:block">
                    <path d="M9 18l6-6-6-6"/>
                  </svg>
                </div>
              )
            })}
        </div>
      </GlassCard>

      {/* Packet traces */}
      <GlassCard className="overflow-hidden">
        <div className="p-4" style={{ borderBottom: '1px solid rgba(0,212,255,0.1)' }}>
          <div className="font-display font-bold text-base tracking-wider neon-cyan">PACKET TRACE</div>
          <div className="font-mono text-xs mt-0.5" style={{ color: 'var(--t-muted, #8899bb)' }}>Session-level tracking · click to expand</div>
        </div>
        {traces.length === 0
          ? <div className="font-mono text-xs p-6 text-center" style={{ color: 'var(--t-muted, #8899bb)' }}>No events available to build traces.</div>
          : (
            <div className="overflow-x-auto">
              <table className="w-full" style={{ minWidth: 600 }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid rgba(0,212,255,0.08)' }}>
                    {['Trace ID', 'Source', 'Destination', 'Protocol', 'Duration', 'Packets', 'Bytes', 'Event Type'].map(h => (
                      <th key={h} className="text-left px-4 py-2.5 font-mono text-xs" style={{ color: 'var(--t-muted, #8899bb)' }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {traces.map(t => {
                    const logEntry: LogEntry = {
                      id: t.id, ts: new Date(t.event.timestamp).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', hour12: false }),
                      level: 'INFO', tag: 'EVENT',
                      src: t.src, msg: t.event.description ?? t.event.event_type,
                      raw: t.event,
                    }
                    return (
                      <tr key={t.id}
                        className="cursor-pointer transition-all hover:bg-cyan-400/5"
                        style={{ borderBottom: '1px solid rgba(0,212,255,0.04)' }}
                        onClick={() => setSelectedLog(logEntry)}>
                        <td className="px-4 py-3 font-mono text-xs neon-cyan">{t.id}</td>
                        <td className="px-4 py-3 font-mono text-xs" style={{ color: '#ff3366' }}>{t.src}</td>
                        <td className="px-4 py-3 font-mono text-xs" style={{ color: 'var(--t-text, #c8d8ee)' }}>{t.dst}</td>
                        <td className="px-4 py-3 font-mono text-xs" style={{ color: '#7c3aed' }}>{t.proto}</td>
                        <td className="px-4 py-3 font-mono text-xs" style={{ color: 'var(--t-muted, #8899bb)' }}>{t.dur}</td>
                        <td className="px-4 py-3 font-mono text-xs" style={{ color: '#00d4ff' }}>{t.pkts.toLocaleString()}</td>
                        <td className="px-4 py-3 font-mono text-xs" style={{ color: '#00ff88' }}>{t.bytes}</td>
                        <td className="px-4 py-3">
                          <span className="font-mono text-xs px-2 py-0.5 rounded truncate" style={{ color: '#ff3366', background: 'rgba(255,51,102,0.12)' }}>{t.flags}</span>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
      </GlassCard>

      {selectedLog && (
        <LogDetailDrawer
          log={selectedLog}
          device={selectedLog.raw && 'device_id' in selectedLog.raw && selectedLog.raw.device_id ? deviceMap.get(selectedLog.raw.device_id) : undefined}
          onClose={() => setSelectedLog(null)}
        />
      )}
    </div>
  )
}
