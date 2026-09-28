import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useParams, Link } from 'react-router'
import GlassCard from '../components/GlassCard'
import { PermissionGuard } from '../components/PermissionGuard'
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid } from 'recharts'
import {
  getDevice,
  getDeviceHistory,
  getDeviceStatusHistory,
  getMonitoringStatus,
  listDeviceMetrics,
  startMonitoringDevice,
  stopMonitoringDevice,
  streamMonitoring,
  type DeviceHistoryResponse,
  type DeviceMetricRecord,
  type DeviceRecord,
} from '../lib/api'
import { formatISTTime } from '../time'

const ttStyle = { background: 'rgba(8,25,55,0.95)', border: '1px solid rgba(0,212,255,0.3)', borderRadius: 6, fontFamily: 'JetBrains Mono', fontSize: 12, color: 'var(--t-text, #c8d8ee)' }

function liveStatusLabel(status: string): string {
  if (status === 'up' || status === 'online') return 'UP'
  if (status === 'down' || status === 'offline') return 'DN'
  return 'WAIT'
}

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds}s`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  return `${h}h ${m}m`
}

function formatTimestamp(ts: string | null | undefined): string {
  if (!ts) return '—'
  try {
    const d = new Date(ts)
    return d.toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', hour12: true })
  } catch {
    return ts
  }
}

export default function DeviceMonitoring() {
  const { deviceId } = useParams()
  const [device, setDevice] = useState<DeviceRecord | null>(null)
  const [metrics, setMetrics] = useState<DeviceMetricRecord[]>([])
  const [history, setHistory] = useState<DeviceHistoryResponse | null>(null)
  const [statusHistory, setStatusHistory] = useState<Array<{ id: number; old_status: string | null; new_status: string; change_reason: string | null; timestamp: string }>>([])
  const [liveStatus, setLiveStatus] = useState<string | null>(null)
  const [liveRtt, setLiveRtt] = useState<number | null>(null)
  const [liveLastCheck, setLiveLastCheck] = useState<string | null>(null)
  const [liveHistory, setLiveHistory] = useState<Array<{ time: string; status: string; rtt_ms: number | null }>>([])
  const [isMonitoring, setIsMonitoring] = useState(false)
  const [startingMonitor, setStartingMonitor] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [metricPage, setMetricPage] = useState(1)
  const [statusPage, setStatusPage] = useState(1)
  const [showAvailabilityDetails, setShowAvailabilityDetails] = useState(false)
  const metricPageSize = 25
  const statusPageSize = 25
  const cleanupRef = useRef<(() => void) | null>(null)
  const deviceRef = useRef<DeviceRecord | null>(null)
  const monitoringRef = useRef(false)

  // Load initial device data
  const loadDevice = useCallback(async () => {
    if (!deviceId) return
    try {
      const dev = await getDevice(Number(deviceId))
      setDevice(dev)
      return dev
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load device')
      return null
    }
  }, [deviceId])

  // Load metrics
  const loadMetrics = useCallback(async () => {
    if (!deviceId) return
    try {
      const data = await listDeviceMetrics(Number(deviceId), { limit: 200 })
      setMetrics(data)
    } catch { /* silent */ }
  }, [deviceId])

  // Load status history
  const loadStatusHistory = useCallback(async () => {
    if (!deviceId) return
    try {
      const data = await getDeviceStatusHistory(Number(deviceId))
      setStatusHistory(data)
    } catch { /* silent */ }
  }, [deviceId])

  // Load full device history (monitoring summary + metrics timeseries)
  const loadHistory = useCallback(async (ip: string) => {
    try {
      const data = await getDeviceHistory(ip, 24)
      setHistory(data)
    } catch { /* silent */ }
  }, [])

  useEffect(() => {
    deviceRef.current = device
  }, [device])

  useEffect(() => {
    monitoringRef.current = isMonitoring
  }, [isMonitoring])

  // Initial load
  useEffect(() => {
    let ignore = false
    void (async () => {
      const dev = await loadDevice()
      if (ignore || !dev) return
      await Promise.all([loadMetrics(), loadStatusHistory(), loadHistory(dev.ip_address)])
    })()
    return () => { ignore = true }
  }, [loadDevice, loadMetrics, loadStatusHistory, loadHistory])

  // SSE stream for real-time monitoring updates
  useEffect(() => {
    let cancelled = false

    void (async () => {
      // Check if this device is already being monitored (started from list page or elsewhere)
      try {
        const status = await getMonitoringStatus()
        const currentDevice = deviceRef.current
        if (cancelled || !currentDevice) return
        const match = status.devices.find(d => String(d.device_id) === deviceId || String(d.ip) === currentDevice.ip_address)
        if (match) {
          setIsMonitoring(true)
          setLiveStatus(String(match.status ?? 'unknown'))
          setLiveRtt(match.last_rtt_ms as number | null)
          setLiveLastCheck(match.last_check as string | null)
          const hist = match.history as Array<{ time: string; status: string; rtt_ms: number | null }> | undefined
          if (hist) setLiveHistory(hist)
        }
      } catch { /* silent */ }

      // Connect to SSE for live updates
      try {
        const cleanup = await streamMonitoring((event) => {
          if (cancelled) return
          const data = event.data as { summary: Record<string, unknown>; devices: Array<Record<string, unknown>> }
          const allDevices = data.devices
          const currentDevice = deviceRef.current
          if (!currentDevice) return
          const match = allDevices.find(d => String(d.device_id) === deviceId || String(d.ip) === currentDevice.ip_address)
          if (match) {
            // Device is being monitored — update live data
            setIsMonitoring(true)
            setLiveStatus(String(match.status ?? 'unknown'))
            setLiveRtt(match.last_rtt_ms as number | null)
            setLiveLastCheck(match.last_check as string | null)
            const hist = match.history as Array<{ time: string; status: string; rtt_ms: number | null }> | undefined
            if (hist) setLiveHistory(hist)
          } else if (monitoringRef.current) {
            // Device was being monitored but is no longer in the list — stopped externally
            setIsMonitoring(false)
            setLiveStatus(null)
            setLiveRtt(null)
            setLiveLastCheck(null)
            setLiveHistory([])
          }
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
  }, [device, deviceId])

  // Auto-refresh metrics every 15s
  useEffect(() => {
    const interval = setInterval(() => {
      if (document.visibilityState !== 'visible') return
      void loadMetrics()
      void loadStatusHistory()
    }, 15000)
    return () => clearInterval(interval)
  }, [loadMetrics, loadStatusHistory])

  const handleStartMonitoring = async () => {
    if (!device) return
    setStartingMonitor(true)
    try {
      await startMonitoringDevice({
        ip: device.ip_address,
        hostname: device.hostname,
        mac_address: device.mac_address,
        site_id: device.site_id,
        device_id: device.id,
      })
      setIsMonitoring(true)
      setDevice(current => current ? { ...current, monitoring_status: true } : current)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to start monitoring')
    } finally {
      setStartingMonitor(false)
    }
  }

  const handleStopMonitoring = async () => {
    if (!device) return
    try {
      await stopMonitoringDevice(device.ip_address)
      setIsMonitoring(false)
      setDevice(current => current ? { ...current, monitoring_status: false } : current)
      setLiveStatus(null)
      setLiveRtt(null)
      setLiveLastCheck(null)
      setLiveHistory([])
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to stop monitoring')
    }
  }

  // Determine effective status (live > DB)
  const effectiveStatus = liveStatus ?? (device?.status === 'online' ? 'up' : device?.status === 'offline' ? 'down' : 'unknown')
  const isUp = effectiveStatus === 'up' || effectiveStatus === 'online'
  const isDown = effectiveStatus === 'down' || effectiveStatus === 'offline'

  // Latency chart data — 5-minute buckets, show at least 5 chunks
  const chartData = useMemo(() => {
    const BUCKET_MS = 5 * 60 * 1000 // 5 minutes
    const sorted = metrics.slice().sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime())
    if (sorted.length === 0) return []

    const buckets = new Map<number, { latencies: number[]; losses: number[] }>()
    for (const m of sorted) {
      const ts = new Date(m.created_at).getTime()
      const key = Math.floor(ts / BUCKET_MS) * BUCKET_MS
      if (!buckets.has(key)) buckets.set(key, { latencies: [], losses: [] })
      const bucket = buckets.get(key)!
      if (m.latency != null) bucket.latencies.push(m.latency)
      if (m.packet_loss != null) bucket.losses.push(m.packet_loss)
    }

    // Show last 5+ chunks (at least 5)
    const allBuckets = Array.from(buckets.entries()).sort(([a], [b]) => a - b)
    const displayBuckets = allBuckets.length >= 5 ? allBuckets.slice(-Math.max(5, allBuckets.length)) : allBuckets

    return displayBuckets.map(([key, { latencies, losses }]) => {
      const d = new Date(key)
      const timeStr = formatISTTime(d, true)
      const dateStr = d.toLocaleDateString('en-IN', { timeZone: 'Asia/Kolkata', day: '2-digit', month: 'short' })
      const avgLat = latencies.length > 0 ? latencies.reduce((s, v) => s + v, 0) / latencies.length : null
      const avgLoss = losses.length > 0 ? losses.reduce((s, v) => s + v, 0) / losses.length : null
      return {
        time: `${dateStr} ${timeStr}`,
        latency: avgLat !== null ? Math.round(avgLat * 100) / 100 : null,
        packet_loss: avgLoss !== null ? Math.round(avgLoss * 100) / 100 : null,
      }
    })
  }, [metrics])

  // Pagination
  const totalMetricPages = Math.max(1, Math.ceil(metrics.length / metricPageSize))
  const pagedMetrics = useMemo(() => metrics.slice((metricPage - 1) * metricPageSize, metricPage * metricPageSize), [metrics, metricPage])
  const realStatusHistory = useMemo(() => statusHistory.filter(entry => (
    entry.new_status === 'online' && (entry.old_status === 'offline' || entry.old_status === 'online')
  ) || (
    entry.new_status === 'offline' && (entry.old_status === 'online' || entry.old_status === 'offline')
  )), [statusHistory])
  const totalStatusPages = Math.max(1, Math.ceil(realStatusHistory.length / statusPageSize))
  const pagedStatusHistory = useMemo(() => realStatusHistory.slice((statusPage - 1) * statusPageSize, statusPage * statusPageSize), [realStatusHistory, statusPage])

  useEffect(() => { setMetricPage(1) }, [metrics.length])
  useEffect(() => { setStatusPage(1) }, [realStatusHistory.length])

  const summary = history?.summary
  const availabilityRows = useMemo(() => {
    if (!history?.status_history?.length) return []
    const end = Date.now()
    const rows = [...history.status_history]
      .filter(item => item.timestamp)
      .sort((a, b) => new Date(a.timestamp!).getTime() - new Date(b.timestamp!).getTime())
    return rows.map((item, index) => {
      const start = new Date(item.timestamp!).getTime()
      const next = rows[index + 1]?.timestamp ? new Date(rows[index + 1].timestamp!).getTime() : end
      return { ...item, state: item.new_status === 'online' ? 'UP' : item.new_status === 'offline' ? 'DOWN' : item.new_status.toUpperCase(), duration: Math.max(0, Math.floor((next - start) / 1000)) }
    })
  }, [history])

  return (
    <div className="p-3 md:p-4 space-y-3 md:space-y-4">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <div className="flex-1 min-w-0">
          <h1 className="font-display font-bold text-lg sm:text-xl tracking-widest neon-cyan">DEVICE MONITORING</h1>
          <p className="font-mono text-xs mt-0.5" style={{ color: 'var(--t-muted, #8899bb)' }}>
            {device ? `${device.hostname} · ${device.ip_address}` : 'Loading device details…'}
          </p>
        </div>
        <Link to="/device-monitoring" className="font-mono text-xs" style={{ color: '#00d4ff' }}>← Back to Monitoring</Link>
      </div>

      {error ? <div className="font-mono text-xs" style={{ color: '#ff3366' }}>{error}</div> : null}

      {device ? (
        <>
          {/* Top row: Live status + Device overview */}
          <div className="grid gap-3 grid-cols-1 lg:grid-cols-3">
            {/* Live Status Card */}
            <GlassCard className="p-3 md:p-4" glow={isUp ? 'green' : isDown ? 'red' : 'amber'}>
              <div className="font-display font-bold text-sm tracking-wider neon-cyan mb-2">LIVE STATUS</div>
              <div className="flex items-center gap-3 mb-3">
                <div
                  className="w-12 h-12 rounded-full flex items-center justify-center"
                  style={{
                    background: isUp ? 'rgba(0,255,136,0.12)' : isDown ? 'rgba(255,51,102,0.12)' : 'rgba(255,170,0,0.12)',
                    border: `2px solid ${isUp ? '#00ff88' : isDown ? '#ff3366' : '#ffaa00'}`,
                    boxShadow: `0 0 15px ${isUp ? 'rgba(0,255,136,0.3)' : isDown ? 'rgba(255,51,102,0.3)' : 'rgba(255,170,0,0.3)'}`,
                  }}
                >
                  <span className="font-display font-bold text-sm" style={{ color: isUp ? '#00ff88' : isDown ? '#ff3366' : '#ffaa00' }}>
                    {isUp ? 'UP' : isDown ? 'DN' : '?'}
                  </span>
                </div>
                <div>
                  <div className="font-display text-sm tracking-wide" style={{ color: 'var(--t-text, #c8d8ee)' }}>{device.hostname}</div>
                  <div className="font-mono text-xs" style={{ color: 'var(--t-muted, #8899bb)' }}>{device.ip_address}</div>
                  {liveRtt !== null && liveRtt !== undefined ? (
                    <div className="font-mono text-xs mt-0.5" style={{ color: '#00d4ff' }}>RTT: {liveRtt.toFixed(1)}ms</div>
                  ) : null}
                  {liveLastCheck ? (
                    <div className="font-mono text-xs mt-0.5" style={{ color: 'var(--t-muted, #8899bb)' }}>Last check: {formatTimestamp(liveLastCheck)}</div>
                  ) : null}
                </div>
              </div>
              <div className="flex gap-2">
                {!isMonitoring ? (
                  <PermissionGuard permission="monitoring:execute">
                  <button
                    onClick={handleStartMonitoring}
                    disabled={startingMonitor}
                    className="rounded px-4 py-2 font-display text-xs tracking-wider uppercase transition disabled:opacity-60"
                    style={{ background: 'rgba(0,255,136,0.16)', border: '1px solid rgba(0,255,136,0.3)', color: 'var(--t-text, #c8d8ee)' }}
                  >
                    {startingMonitor ? 'STARTING…' : 'START MONITORING'}
                  </button>
                  </PermissionGuard>
                ) : (
                  <PermissionGuard permission="monitoring:execute">
                  <button
                    onClick={handleStopMonitoring}
                    className="rounded px-4 py-2 font-display text-xs tracking-wider uppercase transition"
                    style={{ background: 'rgba(255,51,102,0.16)', border: '1px solid rgba(255,51,102,0.3)', color: 'var(--t-text, #c8d8ee)' }}
                  >
                    STOP MONITORING
                  </button>
                  </PermissionGuard>
                )}
              </div>
            </GlassCard>

            {/* Device Overview */}
            <GlassCard className="p-3 md:p-4 cursor-pointer hover:brightness-105 transition" onClick={() => setShowAvailabilityDetails(true)}>
              <div className="font-display font-bold text-sm tracking-wider neon-cyan mb-2">DEVICE OVERVIEW</div>
              <div className="space-y-1.5 font-mono text-xs" style={{ color: 'var(--t-text, #c8d8ee)' }}>
                <div className="flex justify-between"><span style={{ color: 'var(--t-muted, #8899bb)' }}>Hostname</span><span>{device.hostname}</span></div>
                <div className="flex justify-between"><span style={{ color: 'var(--t-muted, #8899bb)' }}>IP Address</span><span>{device.ip_address}</span></div>
                <div className="flex justify-between"><span style={{ color: 'var(--t-muted, #8899bb)' }}>Status</span><span style={{ color: isUp ? '#00ff88' : isDown ? '#ff3366' : '#ffaa00' }}>{effectiveStatus}</span></div>
                <div className="flex justify-between"><span style={{ color: 'var(--t-muted, #8899bb)' }}>Monitoring</span><span style={{ color: isMonitoring ? '#00ff88' : 'var(--t-muted, #8899bb)' }}>{isMonitoring ? 'Enabled' : 'Disabled'}</span></div>
                <div className="flex justify-between"><span style={{ color: 'var(--t-muted, #8899bb)' }}>Last Check</span><span>{formatTimestamp(liveLastCheck ?? device.last_seen)}</span></div>
              </div>
            </GlassCard>

            {/* Uptime / Availability Stats */}
            <GlassCard className="p-3 md:p-4">
              <div className="font-display font-bold text-sm tracking-wider neon-cyan mb-2">AVAILABILITY</div>
              {summary ? (
                <div className="space-y-2">
                  <div className="flex items-center gap-2">
                    <div className="flex-1">
                      <div className="font-mono text-xs mb-0.5" style={{ color: 'var(--t-muted, #8899bb)' }}>AVAILABILITY</div>
                      <div className="font-display text-xl font-bold" style={{ color: summary.availability_pct >= 99 ? '#00ff88' : summary.availability_pct >= 95 ? '#ffaa00' : '#ff3366' }}>
                        {summary.availability_pct}%
                      </div>
                    </div>
                    <div className="h-8 w-px" style={{ background: 'rgba(0,212,255,0.15)' }} />
                    <div className="flex-1">
                      <div className="font-mono text-xs mb-0.5" style={{ color: 'var(--t-muted, #8899bb)' }}>CHANGES</div>
                      <div className="font-display text-lg font-bold" style={{ color: '#00d4ff' }}>{summary.total_status_changes}</div>
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <div className="rounded p-2" style={{ background: 'rgba(0,255,136,0.06)', border: '1px solid rgba(0,255,136,0.15)' }}>
                      <div className="font-mono text-xs" style={{ color: 'var(--t-muted, #8899bb)' }}>Uptime</div>
                      <div className="font-mono text-sm" style={{ color: '#00ff88' }}>{formatDuration(summary.uptime_seconds)}</div>
                    </div>
                    <div className="rounded p-2" style={{ background: 'rgba(255,51,102,0.06)', border: '1px solid rgba(255,51,102,0.15)' }}>
                      <div className="font-mono text-xs" style={{ color: 'var(--t-muted, #8899bb)' }}>Downtime</div>
                      <div className="font-mono text-sm" style={{ color: '#ff3366' }}>{formatDuration(summary.downtime_seconds)}</div>
                    </div>
                  </div>
                  <div className="font-mono text-xs" style={{ color: 'var(--t-muted, #8899bb)' }}>
                    {summary.total_pings} checks • {summary.up_events ?? 0} UP events • {summary.down_events ?? 0} DOWN events • {summary.total_hours}h window
                  </div>
                  <button type="button" onClick={(event) => { event.stopPropagation(); setShowAvailabilityDetails(true) }} className="font-mono text-[10px] mt-2 uppercase tracking-wider text-left hover:underline" style={{ color: '#00d4ff' }}>VIEW EXACT UP/DOWN TIMELINE →</button>
                  {summary.last_status_change ? (
                    <div className="font-mono text-xs" style={{ color: 'var(--t-muted, #8899bb)' }}>
                      Last: {formatTimestamp(summary.last_status_change)}
                    </div>
                  ) : null}
                </div>
              ) : (
                <div className="space-y-1.5 font-mono text-xs" style={{ color: 'var(--t-muted, #8899bb)' }}>
                  <div className="flex justify-between"><span>Uptime</span><span>{formatDuration(device.uptime_seconds)}</span></div>
                  <div className="flex justify-between"><span>Downtime</span><span>{formatDuration(device.downtime_seconds)}</span></div>
                  <div className="flex justify-between"><span>Last Change</span><span>{formatTimestamp(device.last_status_change)}</span></div>
                  <div className="mt-2" style={{ color: 'var(--t-muted, #8899bb)' }}>Start monitoring for stats.</div>
                </div>
              )}
            </GlassCard>
          </div>

          {/* Latency Chart */}
          <GlassCard className="p-4">
            <div className="font-display font-bold text-sm tracking-wider neon-cyan mb-2">LATENCY & PACKET LOSS</div>
            <div className="font-mono text-xs mb-3" style={{ color: 'var(--t-muted, #8899bb)' }}>5-min chunks • Last 5+ buckets • Auto-refresh 15s</div>
            {chartData.length === 0 ? (
              <div className="font-mono text-xs" style={{ color: 'var(--t-muted, #8899bb)' }}>No data yet. Start monitoring to see trends.</div>
            ) : (
              <ResponsiveContainer width="100%" height={180}>
                <LineChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,212,255,0.08)" />
                  <XAxis dataKey="time" tick={{ fill: 'var(--t-muted, #8899bb)', fontSize: 10, fontFamily: 'JetBrains Mono' }} tickLine={false} axisLine={false} interval="preserveStartEnd" />
                  <YAxis yAxisId="left" tick={{ fill: 'var(--t-muted, #8899bb)', fontSize: 10, fontFamily: 'JetBrains Mono' }} tickLine={false} axisLine={false} />
                  <YAxis yAxisId="right" orientation="right" tick={{ fill: 'var(--t-muted, #8899bb)', fontSize: 10, fontFamily: 'JetBrains Mono' }} tickLine={false} axisLine={false} domain={[0, 100]} />
                  <Tooltip contentStyle={ttStyle} />
                  <Line yAxisId="left" type="monotone" dataKey="latency" stroke="#00d4ff" strokeWidth={1.5} dot={false} name="Latency (ms)" />
                  <Line yAxisId="right" type="monotone" dataKey="packet_loss" stroke="#ff3366" strokeWidth={1} dot={false} name="Packet Loss (%)" strokeDasharray="4 2" />
                </LineChart>
              </ResponsiveContainer>
            )}
          </GlassCard>

          {/* Live Monitoring History + Status Change History */}
          <div className="grid gap-3 lg:grid-cols-2">
            {/* Live Ping History (from SSE) */}
            <GlassCard className="p-3 md:p-4">
              <div className="font-display font-bold text-sm tracking-wider neon-cyan mb-2">LIVE PING HISTORY</div>
              <div className="font-mono text-xs mb-3" style={{ color: 'var(--t-muted, #8899bb)' }}>Last 20 pings from real-time monitor</div>
              {liveHistory.length === 0 ? (
                <div className="font-mono text-xs" style={{ color: 'var(--t-muted, #8899bb)' }}>No live data. Start monitoring for real-time pings.</div>
              ) : (
                <div className="space-y-1 max-h-[320px] overflow-y-auto">
                  {liveHistory.slice().reverse().map((entry, i) => (
                    <div key={i} className="flex items-center justify-between rounded p-2" style={{ background: 'rgba(0,212,255,0.04)', border: '1px solid rgba(0,212,255,0.08)' }}>
                      <div className="flex items-center gap-2">
                        <div className="w-1.5 h-1.5 rounded-full" style={{ background: entry.status === 'up' ? '#00ff88' : entry.status === 'down' ? '#ff3366' : '#ffaa00' }} />
                        <span className="font-mono text-xs" style={{ color: 'var(--t-text, #c8d8ee)' }}>{liveStatusLabel(entry.status)}</span>
                      </div>
                      <span className="font-mono text-xs" style={{ color: 'var(--t-muted, #8899bb)' }}>{entry.rtt_ms !== null ? `${entry.rtt_ms.toFixed(1)}ms` : 'timeout'}</span>
                      <span className="font-mono text-xs" style={{ color: 'var(--t-muted, #667799)' }}>{formatTimestamp(entry.time)}</span>
                    </div>
                  ))}
                </div>
              )}
            </GlassCard>

            {/* Status Change History */}
            <GlassCard className="p-3 md:p-4">
              <div className="font-display font-bold text-sm tracking-wider neon-cyan mb-2">STATUS CHANGE HISTORY</div>
              <div className="font-mono text-xs mb-3" style={{ color: 'var(--t-muted, #8899bb)' }}>{device.ip_address} · verified online/offline transitions from database · {realStatusHistory.length} recorded changes</div>
              {realStatusHistory.length === 0 ? (
                <div className="font-mono text-xs" style={{ color: 'var(--t-muted, #8899bb)' }}>No up/down changes recorded yet.</div>
              ) : (
                <>
                  <div className="space-y-1 max-h-[280px] overflow-y-auto">
                    {pagedStatusHistory.map(entry => (
                      <div key={entry.id} className="flex items-center justify-between rounded p-2" style={{ background: 'rgba(0,212,255,0.04)', border: '1px solid rgba(0,212,255,0.08)' }}>
                        <div className="flex items-center gap-2">
                          <div className="w-1.5 h-1.5 rounded-full" style={{ background: entry.new_status === 'online' ? '#00ff88' : '#ff3366' }} />
                          <span className="font-mono text-xs" style={{ color: 'var(--t-text, #c8d8ee)' }}>
                            {device.ip_address} · {entry.old_status} → {entry.new_status}
                          </span>
                        </div>
                        <span className="font-mono text-xs" style={{ color: 'var(--t-muted, #667799)' }}>{formatTimestamp(entry.timestamp)}</span>
                      </div>
                    ))}
                  </div>
                  {totalStatusPages > 1 && (
                    <div className="mt-2 flex items-center justify-between">
                      <div className="font-mono text-xs" style={{ color: 'var(--t-muted, #8899bb)' }}>Page {statusPage} of {totalStatusPages}</div>
                      <div className="flex gap-1">
                        <button onClick={() => setStatusPage(p => Math.max(1, p - 1))} disabled={statusPage === 1} className="rounded px-2 py-1 font-mono text-xs" style={{ background: 'rgba(0,212,255,0.1)', border: '1px solid rgba(0,212,255,0.2)', color: 'var(--t-text, #c8d8ee)' }}>←</button>
                        <button onClick={() => setStatusPage(p => Math.min(totalStatusPages, p + 1))} disabled={statusPage >= totalStatusPages} className="rounded px-2 py-1 font-mono text-xs" style={{ background: 'rgba(0,212,255,0.1)', border: '1px solid rgba(0,212,255,0.2)', color: 'var(--t-text, #c8d8ee)' }}>→</button>
                      </div>
                    </div>
                  )}
                </>
              )}
            </GlassCard>
          </div>

          {showAvailabilityDetails && (
            <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70" onClick={() => setShowAvailabilityDetails(false)}>
              <div className="glass rounded-xl p-5 w-full max-w-4xl max-h-[88vh] overflow-hidden shadow-2xl" style={{ border: '1px solid rgba(0,212,255,.3)' }} onClick={e => e.stopPropagation()}>
                <div className="flex items-start justify-between gap-3 mb-4"><div><h2 className="font-display font-bold text-lg" style={{ color: 'var(--t-text)' }}>Availability Timeline</h2><p className="font-mono text-xs mt-1" style={{ color: 'var(--t-muted)' }}>{device.hostname} · last {summary?.total_hours ?? 24} hours · IST</p></div><button onClick={() => setShowAvailabilityDetails(false)} className="font-mono text-xs" style={{ color: 'var(--t-muted)' }}>CLOSE ✕</button></div>
                {availabilityRows.length === 0 ? <div className="py-10 text-center font-mono text-xs" style={{ color: 'var(--t-muted)' }}>No ON/OFF periods recorded in this window.</div> : <div className="overflow-auto max-h-[62vh]"><table className="w-full text-left font-mono text-xs"><thead><tr style={{ borderBottom: '1px solid var(--t-border-alpha)' }}>{['Period','ON/OFF','Started (IST)','Ended (IST)','Total duration','Evidence'].map(label => <th key={label} className="px-3 py-3 uppercase tracking-wider whitespace-nowrap" style={{ color: 'var(--t-muted)' }}>{label}</th>)}</tr></thead><tbody>{availabilityRows.map((row, index) => { const next = availabilityRows[index + 1]; return <tr key={row.id} style={{ borderBottom: '1px solid var(--t-border-alpha)' }}><td className="px-3 py-3" style={{ color: 'var(--t-muted)' }}>#{index + 1}</td><td className="px-3 py-3"><span className="px-2 py-1 rounded" style={{ color: row.state === 'UP' ? '#00ff88' : '#ff3366', background: row.state === 'UP' ? 'rgba(0,255,136,.1)' : 'rgba(255,51,102,.1)' }}>{row.state}</span></td><td className="px-3 py-3 whitespace-nowrap" style={{ color: 'var(--t-text)' }}>{formatTimestamp(row.timestamp)}</td><td className="px-3 py-3 whitespace-nowrap" style={{ color: 'var(--t-muted)' }}>{next ? formatTimestamp(next.timestamp) : 'Current'}</td><td className="px-3 py-3 whitespace-nowrap" style={{ color: 'var(--t-text)' }}>{formatDuration(row.duration)}</td><td className="px-3 py-3" style={{ color: 'var(--t-muted)' }}>{row.reason ?? 'Verified ICMP transition'}</td></tr> })}</tbody></table></div>}
              </div>
            </div>
          )}

        </>
      ) : (
        !error && <GlassCard className="p-5"><div className="font-mono text-xs" style={{ color: 'var(--t-muted, #8899bb)' }}>Loading device data…</div></GlassCard>
      )}
    </div>
  )
}
