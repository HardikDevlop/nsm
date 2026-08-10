import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router'
import GlassCard from '../components/GlassCard'
import { AreaChart, Area, LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'
import {
  listAlerts, listDevices, listDeviceMetrics, listInterfaces,
  type AlertRecord, type DeviceMetricRecord, type DeviceRecord, type InterfaceRecord,
} from '../lib/api'
import { useAutoRefresh } from '../lib/useAutoRefresh'

const ttStyle = { background: 'rgba(8,25,55,0.95)', border: '1px solid rgba(0,212,255,0.3)', borderRadius: 6, fontFamily: 'JetBrains Mono', fontSize: 11, color: '#c8d8ee' }

function getColor(v: number) {
  if (v > 85) return '#ff3366'
  if (v > 70) return '#ffaa00'
  return '#00ff88'
}

function UsageBar({ value, color }: { value: number; color: string }) {
  return (
    <div className="h-1.5 rounded-full w-full" style={{ background: 'rgba(255,255,255,0.06)' }}>
      <div className="h-1.5 rounded-full transition-all duration-500" style={{ width: `${Math.min(100, value)}%`, background: color }} />
    </div>
  )
}

function formatBytes(b: number) {
  if (b === 0) return '0 B'
  if (b < 1024) return `${b.toFixed(0)} B`
  if (b < 1048576) return `${(b / 1024).toFixed(1)} KB`
  if (b < 1073741824) return `${(b / 1048576).toFixed(1)} MB`
  return `${(b / 1073741824).toFixed(2)} GB`
}

function formatDuration(s: number) {
  if (s < 60) return `${s}s`
  if (s < 3600) return `${Math.floor(s / 60)}m`
  return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`
}

interface ServerRow {
  device: DeviceRecord
  metrics: DeviceMetricRecord[]
  interfaces: InterfaceRecord[]
  cpu: number; ram: number; disk: number; latency: number
  netIn: number; netOut: number; errors: number
}

// ── Detail Side-Panel ──────────────────────────────────────────────────────
function ServerDetailPanel({ srv, onClose }: { srv: ServerRow; onClose: () => void }) {
  const { device, metrics, interfaces } = srv
  const chartData = useMemo(() => {
    const sorted = [...metrics].sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime())
    return sorted.slice(-20).map(m => ({
      t: new Date(m.created_at).toLocaleTimeString('en-IN', { timeZone: 'Asia/Kolkata', hour12: false, hour: '2-digit', minute: '2-digit' }),
      cpu: m.cpu_usage ?? 0,
      ram: m.memory_usage ?? 0,
      latency: m.latency ?? 0,
      pkt_loss: m.packet_loss ?? 0,
    }))
  }, [metrics])

  const isOnline = device.status === 'online'

  return (
    <div className="fixed inset-0 z-50 flex" style={{ backdropFilter: 'blur(2px)', background: 'rgba(0,0,0,0.55)' }}
      onClick={e => { if (e.target === e.currentTarget) onClose() }}>
      <div className="ml-auto h-full overflow-y-auto w-full max-w-xl"
        style={{ background: 'rgba(4,14,33,0.98)', border: '1px solid rgba(0,212,255,0.2)', boxShadow: '-8px 0 40px rgba(0,212,255,0.08)' }}>
        {/* Header */}
        <div className="flex items-center justify-between p-5" style={{ borderBottom: '1px solid rgba(0,212,255,0.12)' }}>
          <div>
            <div className="font-display font-bold text-lg tracking-widest neon-cyan">{device.hostname}</div>
            <div className="font-mono text-xs mt-0.5" style={{ color: '#8899bb' }}>{device.ip_address} · {device.model ?? 'Unknown model'}</div>
          </div>
          <button onClick={onClose} className="rounded-lg p-2 transition-all hover:bg-red-500/20" style={{ color: '#ff3366', border: '1px solid rgba(255,51,102,0.3)' }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 6L6 18M6 6l12 12"/></svg>
          </button>
        </div>

        <div className="p-5 space-y-5">
          {/* Status banner */}
          <div className="rounded-xl p-4 flex items-center gap-4"
            style={{ background: isOnline ? 'rgba(0,255,136,0.06)' : 'rgba(255,51,102,0.06)', border: `1px solid ${isOnline ? 'rgba(0,255,136,0.25)' : 'rgba(255,51,102,0.25)'}` }}>
            <div className="w-12 h-12 rounded-full flex items-center justify-center font-display font-bold text-sm"
              style={{ background: isOnline ? 'rgba(0,255,136,0.15)' : 'rgba(255,51,102,0.15)', color: isOnline ? '#00ff88' : '#ff3366', border: `2px solid ${isOnline ? '#00ff88' : '#ff3366'}` }}>
              {isOnline ? 'UP' : 'DN'}
            </div>
            <div className="flex-1">
              <div className="font-display font-semibold text-sm" style={{ color: '#c8d8ee' }}>
                {isOnline ? 'Device is Online' : 'Device is Offline'}
              </div>
              <div className="font-mono text-xs mt-0.5" style={{ color: '#8899bb' }}>
                Uptime: {formatDuration(device.uptime_seconds)} · Last seen: {device.last_seen ? new Date(device.last_seen).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', hour12: true }) : '—'}
              </div>
            </div>
            <Link to={`/device-monitoring/${device.id}`}
              className="font-mono text-xs px-3 py-2 rounded-lg transition-all hover:opacity-80"
              style={{ background: 'rgba(0,212,255,0.12)', border: '1px solid rgba(0,212,255,0.3)', color: '#00d4ff' }}>
              Full Monitor →
            </Link>
          </div>

          {/* Live metrics */}
          <div>
            <div className="font-display font-bold text-xs tracking-widest neon-cyan mb-3">RESOURCE USAGE</div>
            <div className="space-y-3">
              {[
                { l: 'CPU', v: srv.cpu }, { l: 'RAM', v: srv.ram }, { l: 'Disk', v: srv.disk },
              ].map(m => (
                <div key={m.l}>
                  <div className="flex justify-between font-mono text-xs mb-1">
                    <span style={{ color: '#8899bb' }}>{m.l}</span>
                    <span style={{ color: getColor(m.v) }}>{m.v.toFixed(1)}%</span>
                  </div>
                  <UsageBar value={m.v} color={getColor(m.v)} />
                </div>
              ))}
            </div>
          </div>

          {/* Net + Latency stats */}
          <div className="grid grid-cols-3 gap-3">
            {[
              { l: 'Latency', v: `${srv.latency.toFixed(1)}ms`, c: '#00d4ff' },
              { l: 'Net In', v: formatBytes(srv.netIn), c: '#00ff88' },
              { l: 'Net Out', v: formatBytes(srv.netOut), c: '#7c3aed' },
            ].map(s => (
              <div key={s.l} className="rounded-lg p-3 text-center" style={{ background: 'rgba(0,212,255,0.04)', border: '1px solid rgba(0,212,255,0.1)' }}>
                <div className="font-display font-bold text-base" style={{ color: s.c }}>{s.v}</div>
                <div className="font-mono text-xs mt-0.5" style={{ color: '#8899bb' }}>{s.l}</div>
              </div>
            ))}
          </div>

          {/* Metric trend chart */}
          {chartData.length > 0 ? (
            <div>
              <div className="font-display font-bold text-xs tracking-widest neon-cyan mb-3">CPU & RAM TREND</div>
              <ResponsiveContainer width="100%" height={140}>
                <LineChart data={chartData}>
                  <XAxis dataKey="t" tick={{ fill: '#8899bb', fontSize: 10, fontFamily: 'JetBrains Mono' }} tickLine={false} axisLine={false} interval="preserveStartEnd" />
                  <YAxis domain={[0, 100]} tick={{ fill: '#8899bb', fontSize: 10, fontFamily: 'JetBrains Mono' }} tickLine={false} axisLine={false} />
                  <Tooltip contentStyle={ttStyle} />
                  <Line type="monotone" dataKey="cpu" stroke="#00d4ff" strokeWidth={1.5} dot={false} name="CPU %" />
                  <Line type="monotone" dataKey="ram" stroke="#7c3aed" strokeWidth={1.5} dot={false} name="RAM %" />
                </LineChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className="font-mono text-xs rounded-lg p-4 text-center" style={{ color: '#8899bb', background: 'rgba(0,212,255,0.04)', border: '1px solid rgba(0,212,255,0.1)' }}>
              No metric history available. Start monitoring to collect data.
            </div>
          )}

          {/* Interfaces table */}
          {interfaces.length > 0 && (
            <div>
              <div className="font-display font-bold text-xs tracking-widest neon-cyan mb-3">INTERFACES ({interfaces.length})</div>
              <div className="space-y-2">
                {interfaces.map(iface => (
                  <div key={iface.id} className="flex items-center justify-between rounded-lg px-3 py-2"
                    style={{ background: 'rgba(0,212,255,0.04)', border: '1px solid rgba(0,212,255,0.08)' }}>
                    <div className="flex items-center gap-2">
                      <div className="w-2 h-2 rounded-full" style={{ background: iface.status === 'up' ? '#00ff88' : '#ff3366' }} />
                      <span className="font-mono text-xs" style={{ color: '#c8d8ee' }}>{iface.interface_name}</span>
                    </div>
                    <div className="flex gap-3 font-mono text-xs" style={{ color: '#8899bb' }}>
                      <span>↓ {formatBytes(iface.traffic_in)}</span>
                      <span>↑ {formatBytes(iface.traffic_out)}</span>
                      {iface.packet_errors > 0 && <span style={{ color: '#ff3366' }}>{iface.packet_errors} err</span>}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Device info */}
          <div>
            <div className="font-display font-bold text-xs tracking-widest neon-cyan mb-3">DEVICE INFO</div>
            <div className="space-y-2 font-mono text-xs" style={{ color: '#c8d8ee' }}>
              {[
                ['Serial', device.serial_number ?? '—'], ['Firmware', device.firmware_version ?? '—'],
                ['MAC', device.mac_address ?? '—'], ['Monitoring', device.monitoring_status ? 'Enabled' : 'Disabled'],
                ['Created', new Date(device.created_at).toLocaleDateString('en-IN')],
              ].map(([k, v]) => (
                <div key={k} className="flex justify-between">
                  <span style={{ color: '#8899bb' }}>{k}</span><span>{v}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Main Page ──────────────────────────────────────────────────────────────
export default function ServerMonitoring() {
  const [devices, setDevices] = useState<DeviceRecord[]>([])
  const [metrics, setMetrics] = useState<DeviceMetricRecord[]>([])
  const [interfaces, setInterfaces] = useState<InterfaceRecord[]>([])
  const [alerts, setAlerts] = useState<AlertRecord[]>([])
  const [selected, setSelected] = useState<ServerRow | null>(null)

  const fetchAll = useCallback(async () => {
    const [d, m, i, a] = await Promise.all([listDevices(), listDeviceMetrics(), listInterfaces(), listAlerts()])
    return { devices: d, metrics: m, interfaces: i, alerts: a }
  }, [])

  const { loading, error, refresh } = useAutoRefresh(
    fetchAll,
    ({ devices: d, metrics: m, interfaces: i, alerts: a }) => {
      setDevices(d); setMetrics(m); setInterfaces(i); setAlerts(a)
    },
    15000,
  )

  // Build per-device ServerRow objects
  const servers = useMemo<ServerRow[]>(() => devices.map(device => {
    const devMetrics = metrics.filter(m => m.device_id === device.id)
    const devIfaces = interfaces.filter(i => i.device_id === device.id)
    const recent = devMetrics.slice(-5)
    const avg = (key: keyof DeviceMetricRecord) => {
      const vals = recent.map(m => m[key] as number | null).filter(v => v != null) as number[]
      return vals.length ? vals.reduce((s, v) => s + v, 0) / vals.length : 0
    }
    return {
      device,
      metrics: devMetrics,
      interfaces: devIfaces,
      cpu: avg('cpu_usage'),
      ram: avg('memory_usage'),
      disk: avg('disk_usage'),
      latency: avg('latency'),
      netIn: devIfaces.reduce((s, i) => s + i.traffic_in, 0),
      netOut: devIfaces.reduce((s, i) => s + i.traffic_out, 0),
      errors: devIfaces.reduce((s, i) => s + i.packet_errors, 0),
    }
  }), [devices, metrics, interfaces])

  // Aggregate trend charts across all servers
  const cpuHistory = useMemo(() => {
    const sorted = [...metrics].sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime())
    const recent = sorted.slice(-30)
    return recent.map(m => ({
      t: new Date(m.created_at).toLocaleTimeString('en-IN', { timeZone: 'Asia/Kolkata', hour12: false, hour: '2-digit', minute: '2-digit' }),
      v: m.cpu_usage ?? 0,
    }))
  }, [metrics])

  const ramHistory = useMemo(() => {
    const sorted = [...metrics].sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime())
    return sorted.slice(-30).map(m => ({
      t: new Date(m.created_at).toLocaleTimeString('en-IN', { timeZone: 'Asia/Kolkata', hour12: false, hour: '2-digit', minute: '2-digit' }),
      v: m.memory_usage ?? 0,
    }))
  }, [metrics])

  const netHistory = useMemo(() => {
    const sorted = [...metrics].sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime())
    return sorted.slice(-30).map(m => ({
      t: new Date(m.created_at).toLocaleTimeString('en-IN', { timeZone: 'Asia/Kolkata', hour12: false, hour: '2-digit', minute: '2-digit' }),
      tx: m.bandwidth_usage ?? 0,
      rx: m.latency ?? 0,
    }))
  }, [metrics])

  const summary = useMemo(() => ({
    online: devices.filter(d => d.status === 'online').length,
    avgCpu: servers.length ? servers.reduce((s, r) => s + r.cpu, 0) / servers.length : 0,
    avgRam: servers.length ? servers.reduce((s, r) => s + r.ram, 0) / servers.length : 0,
    alertsActive: alerts.filter(a => a.status !== 'resolved').length,
  }), [devices, servers, alerts])

  return (
    <div className="p-4 md:p-6 space-y-4 md:space-y-5">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <div>
          <h1 className="font-display font-bold text-2xl tracking-widest neon-cyan">SERVER MONITORING</h1>
          <p className="font-mono text-xs mt-0.5" style={{ color: '#8899bb' }}>
            {devices.length} devices · auto-refresh 15s · click a card for details
          </p>
        </div>
        <button onClick={refresh} className="glass-bright px-3 h-9 rounded font-mono text-xs flex items-center gap-1.5 transition-all hover:bg-cyan-400/10"
          style={{ border: '1px solid rgba(0,212,255,0.25)', color: '#00d4ff' }}>
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M23 4v6h-6M1 20v-6h6"/><path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/>
          </svg>
          REFRESH
        </button>
      </div>

      {error && <div className="font-mono text-xs" style={{ color: '#ff3366' }}>{error}</div>}
      {loading && !devices.length && <div className="font-mono text-xs" style={{ color: '#8899bb' }}>Loading server data…</div>}

      {/* KPI bar */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[
          { l: 'Servers Online', v: `${summary.online}/${servers.length}`, c: '#00ff88' },
          { l: 'Avg CPU', v: `${summary.avgCpu.toFixed(1)}%`, c: '#00d4ff' },
          { l: 'Avg RAM', v: `${summary.avgRam.toFixed(1)}%`, c: '#7c3aed' },
          { l: 'Active Alerts', v: summary.alertsActive.toString(), c: '#ff3366' },
        ].map(k => (
          <GlassCard key={k.l} className="p-4 text-center">
            <div className="font-display font-bold text-2xl transition-all" style={{ color: k.c }}>{k.v}</div>
            <div className="font-mono text-xs mt-1" style={{ color: '#8899bb' }}>{k.l}</div>
          </GlassCard>
        ))}
      </div>

      {/* Server cards grid */}
      {servers.length === 0 && !loading ? (
        <GlassCard className="p-8 text-center">
          <div className="font-mono text-xs" style={{ color: '#8899bb' }}>No devices found. Discover devices via ISP &amp; WAN Monitoring to populate this view.</div>
        </GlassCard>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {servers.map(srv => {
            const isOffline = srv.device.status === 'offline'
            const isWarn = srv.cpu > 70 || srv.ram > 70
            return (
              <GlassCard key={srv.device.id}
                className="p-4 cursor-pointer transition-all hover:-translate-y-0.5"
                glow={isOffline ? 'red' : isWarn ? 'amber' : undefined}
                onClick={() => setSelected(srv)}>
                <div className="flex items-start justify-between mb-3">
                  <div>
                    <div className="font-display font-bold text-sm" style={{ color: isOffline ? '#ff3366' : '#c8d8ee' }}>{srv.device.hostname}</div>
                    <div className="font-mono text-xs mt-0.5" style={{ color: '#8899bb' }}>{srv.device.ip_address}</div>
                    {srv.device.model && <div className="font-mono text-xs mt-0.5" style={{ color: '#556677' }}>{srv.device.model}</div>}
                  </div>
                  <div className="flex flex-col items-end gap-1">
                    <span className={`status-dot ${isOffline ? 'offline' : 'online'}`} style={{ marginTop: 3 }} />
                    <span className="font-mono text-xs px-1.5 py-0.5 rounded"
                      style={{ fontSize: 9, color: '#00d4ff', background: 'rgba(0,212,255,0.08)', border: '1px solid rgba(0,212,255,0.15)' }}>
                      DETAILS →
                    </span>
                  </div>
                </div>

                <div className="space-y-2.5">
                  {[{ l: 'CPU', v: srv.cpu }, { l: 'RAM', v: srv.ram }, { l: 'Disk', v: srv.disk }].map(m => (
                    <div key={m.l}>
                      <div className="flex justify-between font-mono text-xs mb-1">
                        <span style={{ color: '#8899bb' }}>{m.l}</span>
                        <span style={{ color: getColor(m.v) }}>{m.v.toFixed(1)}%</span>
                      </div>
                      <UsageBar value={m.v} color={getColor(m.v)} />
                    </div>
                  ))}
                </div>

                <div className="mt-3 grid grid-cols-3 gap-2">
                  <div className="font-mono text-xs text-center rounded py-1" style={{ background: 'rgba(0,212,255,0.04)', color: '#00d4ff' }}>
                    <div className="font-bold">{srv.latency.toFixed(0)}ms</div>
                    <div style={{ fontSize: 9, color: '#8899bb' }}>Latency</div>
                  </div>
                  <div className="font-mono text-xs text-center rounded py-1" style={{ background: 'rgba(0,255,136,0.04)', color: '#00ff88' }}>
                    <div className="font-bold">{srv.interfaces.filter(i => i.status === 'up').length}/{srv.interfaces.length}</div>
                    <div style={{ fontSize: 9, color: '#8899bb' }}>Ifaces Up</div>
                  </div>
                  <div className="font-mono text-xs text-center rounded py-1" style={{ background: srv.errors > 0 ? 'rgba(255,51,102,0.06)' : 'rgba(0,255,136,0.04)', color: srv.errors > 0 ? '#ff3366' : '#00ff88' }}>
                    <div className="font-bold">{srv.errors}</div>
                    <div style={{ fontSize: 9, color: '#8899bb' }}>Errors</div>
                  </div>
                </div>
              </GlassCard>
            )
          })}
        </div>
      )}

      {/* Trend charts */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {[
          { title: 'CPU TREND', key: 'v', color: '#00d4ff', gradId: 'gcpu', data: cpuHistory },
          { title: 'RAM TREND', key: 'v', color: '#7c3aed', gradId: 'gram', data: ramHistory },
        ].map(chart => (
          <GlassCard key={chart.title} className="p-4 md:p-5">
            <div className="font-display font-bold text-sm tracking-wider neon-cyan mb-1">{chart.title}</div>
            <div className="font-mono text-xs mb-3" style={{ color: '#8899bb' }}>All devices · 30 readings</div>
            {chart.data.length === 0
              ? <div className="font-mono text-xs py-6 text-center" style={{ color: '#8899bb' }}>No data yet</div>
              : (
                <ResponsiveContainer width="100%" height={130}>
                  <AreaChart data={chart.data}>
                    <defs>
                      <linearGradient id={chart.gradId} x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor={chart.color} stopOpacity={0.35} />
                        <stop offset="95%" stopColor={chart.color} stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <XAxis dataKey="t" tick={{ fill: '#8899bb', fontSize: 10, fontFamily: 'JetBrains Mono' }} tickLine={false} axisLine={false} interval="preserveStartEnd" />
                    <YAxis domain={[0, 100]} tick={{ fill: '#8899bb', fontSize: 10, fontFamily: 'JetBrains Mono' }} tickLine={false} axisLine={false} />
                    <Tooltip contentStyle={ttStyle} />
                    <Area type="monotone" dataKey={chart.key} stroke={chart.color} strokeWidth={2} fill={`url(#${chart.gradId})`} dot={false} name={chart.title} />
                  </AreaChart>
                </ResponsiveContainer>
              )}
          </GlassCard>
        ))}

        <GlassCard className="p-4 md:p-5">
          <div className="font-display font-bold text-sm tracking-wider neon-cyan mb-1">NETWORK I/O</div>
          <div className="font-mono text-xs mb-3" style={{ color: '#8899bb' }}>Bandwidth · 30 readings</div>
          {netHistory.length === 0
            ? <div className="font-mono text-xs py-6 text-center" style={{ color: '#8899bb' }}>No data yet</div>
            : (
              <ResponsiveContainer width="100%" height={130}>
                <LineChart data={netHistory}>
                  <XAxis dataKey="t" tick={{ fill: '#8899bb', fontSize: 10, fontFamily: 'JetBrains Mono' }} tickLine={false} axisLine={false} interval="preserveStartEnd" />
                  <YAxis tick={{ fill: '#8899bb', fontSize: 10, fontFamily: 'JetBrains Mono' }} tickLine={false} axisLine={false} />
                  <Tooltip contentStyle={ttStyle} />
                  <Line type="monotone" dataKey="tx" stroke="#00d4ff" strokeWidth={1.5} dot={false} name="BW/Latency" />
                  <Line type="monotone" dataKey="rx" stroke="#00ff88" strokeWidth={1.5} dot={false} name="Latency ms" />
                </LineChart>
              </ResponsiveContainer>
            )}
        </GlassCard>
      </div>

      {/* Detail panel */}
      {selected && <ServerDetailPanel srv={selected} onClose={() => setSelected(null)} />}
    </div>
  )
}
