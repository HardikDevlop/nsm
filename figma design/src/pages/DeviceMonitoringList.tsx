import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router'
import GlassCard from '../components/GlassCard'
import { PermissionGuard } from '../components/PermissionGuard'
import {
  listDevices,
  getMonitoringStatus,
  startAllMonitoring,
  stopAllMonitoring,
  startMonitoringDevice,
  stopMonitoringDevice,
  streamMonitoring,
  type DeviceRecord,
  type MonitoringStatusResponse,
} from '../lib/api'

type LiveDevice = Record<string, unknown>

export default function DeviceMonitoringList() {
  const [devices, setDevices] = useState<DeviceRecord[]>([])
  const [monitoringData, setMonitoringData] = useState<MonitoringStatusResponse | null>(null)
  const [liveDevices, setLiveDevices] = useState<LiveDevice[]>([])
  const [loading, setLoading] = useState(true)
  const [startingAll, setStartingAll] = useState(false)
  const [stoppingAll, setStoppingAll] = useState(false)
  const [actionInProgress, setActionInProgress] = useState<Record<string, boolean>>({})
  const [error, setError] = useState<string | null>(null)
  const cleanupRef = useRef<(() => void) | null>(null)

  // Load devices from DB
  const loadDevices = useCallback(async () => {
    try {
      const data = await listDevices()
      setDevices(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load devices')
    } finally {
      setLoading(false)
    }
  }, [])

  // Load monitoring status
  const loadStatus = useCallback(async () => {
    try {
      const data = await getMonitoringStatus()
      setMonitoringData(data)
      setLiveDevices(data.devices)
    } catch {
      // silent — SSE will provide data
    }
  }, [])

  // Initial load
  useEffect(() => {
    let ignore = false
    void (async () => {
      await loadDevices()
      await loadStatus()
    })()
    return () => { ignore = true }
  }, [loadDevices, loadStatus])

  // SSE stream for real-time monitoring updates
  useEffect(() => {
    let cancelled = false
    void (async () => {
      try {
        const cleanup = await streamMonitoring((event) => {
          if (cancelled) return
          const data = event.data as MonitoringStatusResponse
          setMonitoringData(data)
          setLiveDevices(data.devices)
        })
        cleanupRef.current = cleanup
      } catch {
        // silent
      }
    })()
    return () => {
      cancelled = true
      if (cleanupRef.current) {
        cleanupRef.current()
        cleanupRef.current = null
      }
    }
  }, [])

  // Build a map of IP → live monitoring data
  const liveMap = useMemo(() => {
    const map = new Map<string, LiveDevice>()
    for (const d of liveDevices) {
      const ip = String(d.ip ?? '')
      if (ip) map.set(ip, d)
    }
    return map
  }, [liveDevices])

  // Start monitoring all devices
  const handleStartAll = async () => {
    setStartingAll(true)
    try {
      const payload = devices.map(d => ({
        ip_address: d.ip_address,
        hostname: d.hostname,
        mac_address: d.mac_address,
        site_id: d.site_id,
        device_id: d.id,
      }))
      await startAllMonitoring(payload)
      await loadStatus()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start monitoring')
    } finally {
      setStartingAll(false)
    }
  }

  // Stop monitoring all devices
  const handleStopAll = async () => {
    setStoppingAll(true)
    try {
      await stopAllMonitoring()
      await loadStatus()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to stop monitoring')
    } finally {
      setStoppingAll(false)
    }
  }

  // Start monitoring a single device
  const handleStartDevice = async (device: DeviceRecord) => {
    setActionInProgress(prev => ({ ...prev, [device.ip_address]: true }))
    try {
      await startMonitoringDevice({
        ip: device.ip_address,
        hostname: device.hostname,
        mac_address: device.mac_address,
        site_id: device.site_id,
        device_id: device.id,
      })
    } catch {
      // silent — will update via SSE
    } finally {
      setActionInProgress(prev => {
        const next = { ...prev }
        delete next[device.ip_address]
        return next
      })
    }
  }

  // Stop monitoring a single device
  const handleStopDevice = async (ip: string) => {
    setActionInProgress(prev => ({ ...prev, [ip]: true }))
    try {
      await stopMonitoringDevice(ip)
    } catch {
      // silent
    } finally {
      setActionInProgress(prev => {
        const next = { ...prev }
        delete next[ip]
        return next
      })
    }
  }

  const summary = monitoringData?.summary
  const totalMonitored = summary?.total_monitored ?? 0
  const totalUp = summary?.up ?? 0
  const totalDown = summary?.down ?? 0

  return (
    <div className="p-4 md:p-6 space-y-4 md:space-y-5">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <div className="flex-1 min-w-0">
          <h1 className="font-display font-bold text-xl sm:text-2xl tracking-widest neon-cyan">DEVICE MONITORING</h1>
          <p className="font-mono text-xs mt-0.5" style={{ color: '#8899bb' }}>
            {devices.length} device{devices.length !== 1 ? 's' : ''} in database · {totalMonitored} under monitoring
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {totalMonitored > 0 && (
            <PermissionGuard permission="monitoring:execute">
            <button
              onClick={handleStopAll}
              disabled={stoppingAll}
              className="rounded-lg px-4 py-2 font-display text-xs tracking-wider uppercase transition disabled:opacity-60 min-h-[44px]"
              style={{ background: 'rgba(255,51,102,0.12)', border: '1px solid rgba(255,51,102,0.3)', color: '#ff3366' }}
            >
              {stoppingAll ? 'STOPPING…' : '■ STOP ALL'}
            </button>
            </PermissionGuard>
          )}
          <PermissionGuard permission="monitoring:execute">
          <button
            onClick={handleStartAll}
            disabled={startingAll || devices.length === 0}
            className="rounded-lg px-4 py-2 font-display text-xs tracking-wider uppercase transition disabled:opacity-60 min-h-[44px]"
            style={{ background: 'rgba(0,255,136,0.12)', border: '1px solid rgba(0,255,136,0.3)', color: '#00ff88' }}
          >
            {startingAll ? 'STARTING…' : '▶ START ALL'}
          </button>
          </PermissionGuard>
        </div>
      </div>

      {error ? <div className="font-mono text-xs" style={{ color: '#ff3366' }}>{error}</div> : null}

      {/* Summary cards */}
      <div className="grid gap-3 grid-cols-2 md:grid-cols-4">
        <GlassCard className="p-4">
          <div className="font-mono text-xs mb-1" style={{ color: '#8899bb' }}>TOTAL DEVICES</div>
          <div className="font-display text-2xl sm:text-3xl font-bold" style={{ color: '#00d4ff' }}>{devices.length}</div>
        </GlassCard>
        <GlassCard className="p-4">
          <div className="font-mono text-xs mb-1" style={{ color: '#8899bb' }}>MONITORED</div>
          <div className="font-display text-2xl sm:text-3xl font-bold" style={{ color: '#00d4ff' }}>{totalMonitored}</div>
        </GlassCard>
        <GlassCard className="p-4">
          <div className="font-mono text-xs mb-1" style={{ color: '#8899bb' }}>ONLINE</div>
          <div className="font-display text-2xl sm:text-3xl font-bold" style={{ color: '#00ff88' }}>{totalUp}</div>
        </GlassCard>
        <GlassCard className="p-4">
          <div className="font-mono text-xs mb-1" style={{ color: '#8899bb' }}>OFFLINE</div>
          <div className="font-display text-2xl sm:text-3xl font-bold" style={{ color: '#ff3366' }}>{totalDown}</div>
        </GlassCard>
      </div>

      {/* Device list */}
      <GlassCard className="p-4 md:p-5">
        <div className="font-display font-bold text-sm sm:text-base tracking-wider neon-cyan mb-4">ALL DEVICES</div>
        {loading ? (
          <div className="font-mono text-xs" style={{ color: '#8899bb' }}>Loading devices…</div>
        ) : devices.length === 0 ? (
          <div className="font-mono text-xs" style={{ color: '#8899bb' }}>
            No devices in database. Run a discovery and add devices first.
          </div>
        ) : (
          <div className="space-y-2">
            {devices.map(device => {
              const live = liveMap.get(device.ip_address)
              const isMonitored = !!live
              const liveStatus = live ? String(live.status ?? 'unknown') : 'unknown'
              const liveRtt = live ? (live.last_rtt_ms as number | null) : null
              const liveLastCheck = live ? (live.last_check as string | null) : null
              const isBusy = !!actionInProgress[device.ip_address]

              let statusColor = '#8899bb'
              let statusLabel = 'NOT MONITORED'
              if (isMonitored) {
                if (liveStatus === 'up') { statusColor = '#00ff88'; statusLabel = 'UP' }
                else if (liveStatus === 'down') { statusColor = '#ff3366'; statusLabel = 'DOWN' }
                else { statusColor = '#ffaa00'; statusLabel = 'UNKNOWN' }
              }

              return (
                <div key={device.id} className="flex flex-col sm:flex-row items-start sm:items-center gap-3 sm:gap-4 rounded-lg p-3"
                  style={{ background: 'rgba(0,212,255,0.03)', border: '1px solid rgba(0,212,255,0.08)' }}>
                  {/* Status dot */}
                  <div className="w-3 h-3 rounded-full shrink-0" style={{
                    background: statusColor,
                    boxShadow: isMonitored ? `0 0 8px ${statusColor}` : 'none',
                  }} />

                  {/* Device info */}
                  <div className="flex-1 min-w-0 w-full sm:w-auto">
                    <div className="font-display text-sm tracking-wider" style={{ color: '#c8d8ee' }}>
                      {device.hostname || 'Unknown'}
                    </div>
                    <div className="font-mono text-xs" style={{ color: '#8899bb' }}>
                      {device.ip_address}
                      {device.mac_address ? ` · ${device.mac_address}` : ''}
                    </div>
                  </div>

                  {/* Live stats */}
                  {isMonitored && (
                    <div className="text-right shrink-0 w-full sm:w-auto">
                      {liveRtt !== null && liveRtt !== undefined ? (
                        <div className="font-mono text-xs" style={{ color: '#00d4ff' }}>
                          RTT: {liveRtt.toFixed(1)} ms
                        </div>
                      ) : null}
                      {liveLastCheck ? (
                        <div className="font-mono text-xs" style={{ color: '#667799' }}>
                          {formatTime(liveLastCheck)}
                        </div>
                      ) : null}
                    </div>
                  )}

                  <div className="flex items-center gap-2 w-full sm:w-auto flex-wrap">
                    {/* Status badge */}
                    <div className="font-mono text-xs px-2 py-1 rounded shrink-0 min-h-[36px] flex items-center"
                      style={{ color: statusColor, background: `${statusColor}15`, border: `1px solid ${statusColor}30` }}>
                      {statusLabel}
                    </div>

                    {/* Actions */}
                    <div className="flex items-center gap-2 shrink-0 flex-wrap">
                      {isMonitored ? (
                        <PermissionGuard permission="monitoring:execute">
                        <button
                          onClick={() => handleStopDevice(device.ip_address)}
                          disabled={isBusy}
                          className="rounded px-3 py-1.5 font-mono text-xs uppercase transition disabled:opacity-60 min-h-[36px]"
                          style={{ background: 'rgba(255,51,102,0.1)', border: '1px solid rgba(255,51,102,0.25)', color: '#ff3366' }}
                        >
                          {isBusy ? '…' : '■ Stop'}
                        </button>
                        </PermissionGuard>
                      ) : (
                        <PermissionGuard permission="monitoring:execute">
                        <button
                          onClick={() => handleStartDevice(device)}
                          disabled={isBusy}
                          className="rounded px-3 py-1.5 font-mono text-xs uppercase transition disabled:opacity-60 min-h-[36px]"
                          style={{ background: 'rgba(0,255,136,0.1)', border: '1px solid rgba(0,255,136,0.25)', color: '#00ff88' }}
                        >
                          {isBusy ? '…' : '▶ Start'}
                        </button>
                        </PermissionGuard>
                      )}
                      <Link
                        to={`/device-monitoring/${device.id}`}
                        className="rounded px-3 py-1.5 font-mono text-xs uppercase transition min-h-[36px] flex items-center"
                        style={{ background: 'rgba(0,212,255,0.1)', border: '1px solid rgba(0,212,255,0.25)', color: '#00d4ff' }}
                      >
                        View Details
                      </Link>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </GlassCard>

    </div>
  )
}

function formatTime(ts: string): string {
  try {
    const d = new Date(ts)
    return d.toLocaleTimeString('en-IN', { timeZone: 'Asia/Kolkata', hour12: false })
  } catch {
    return ts
  }
}
