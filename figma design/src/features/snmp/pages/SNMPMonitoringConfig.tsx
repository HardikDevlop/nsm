import { useState } from 'react'
import { useParams, useNavigate } from 'react-router'
import GlassCard from '../../../components/GlassCard'
import SNMPStatusBadge from '../components/SNMPStatusBadge'
import { useSNMPDeviceDetails, useStartModuleMonitoring, useStopModuleMonitoring, useUpdateModuleMonitoring } from '../hooks/useSnmpQueries'
import { getSupportedModuleConfigs, getModuleConfig, MODULE_ORDER, INTERVAL_OPTIONS } from '../modules'

export default function SNMPMonitoringConfig() {
  const { deviceId } = useParams<{ deviceId: string }>()
  const navigate = useNavigate()
  const id = Number(deviceId)
  const startMonitoring = useStartModuleMonitoring()
  const stopMonitoring = useStopModuleMonitoring()
  const updateMonitoring = useUpdateModuleMonitoring()

  const { data, isLoading, error, refetch } = useSNMPDeviceDetails(id)

  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)

  const handleStartMonitoring = async (module: string, intervalSeconds: number) => {
    try {
      await startMonitoring.mutateAsync({ deviceId: id, module, intervalSeconds })
      setSuccessMessage(`Started monitoring ${getModuleConfig(module)?.label || module}`)
      setErrorMessage(null)
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : 'Failed to start monitoring')
    }
  }

  const handleStopMonitoring = async (module: string) => {
    try {
      await stopMonitoring.mutateAsync({ deviceId: id, module })
      setSuccessMessage(`Stopped monitoring ${getModuleConfig(module)?.label || module}`)
      setErrorMessage(null)
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : 'Failed to stop monitoring')
    }
  }

  const handleUpdateInterval = async (module: string, intervalSeconds: number) => {
    try {
      await updateMonitoring.mutateAsync({ deviceId: id, module, data: { interval_seconds: intervalSeconds } })
      setSuccessMessage(`Updated ${getModuleConfig(module)?.label || module} interval to ${intervalSeconds}s`)
      setErrorMessage(null)
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : 'Failed to update interval')
    }
  }

  const handleToggleEnabled = async (module: string, enabled: boolean) => {
    try {
      await updateMonitoring.mutateAsync({ deviceId: id, module, data: { enabled } })
      setSuccessMessage(`${enabled ? 'Enabled' : 'Disabled'} monitoring for ${getModuleConfig(module)?.label || module}`)
      setErrorMessage(null)
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : 'Failed to update monitoring')
    }
  }

  const clearMessages = () => {
    setErrorMessage(null)
    setSuccessMessage(null)
  }

  if (isLoading) {
    return (
      <div className="p-4 md:p-6 space-y-4 md:space-y-5">
        <div className="flex items-center justify-center p-12">
          <div className="font-mono text-sm" style={{ color: '#00d4ff' }}>Loading device...</div>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="p-4 md:p-6 space-y-4 md:space-y-5">
        <GlassCard className="p-8 text-center">
          <div className="font-display font-bold text-lg" style={{ color: '#ff3366' }}>Failed to Load Device</div>
          <div className="font-mono text-sm mt-2" style={{ color: '#8899bb' }}>{error.message}</div>
          <button onClick={() => navigate('/snmp/devices')} className="mt-4 px-4 py-2 rounded font-mono text-xs"
            style={{ background: 'rgba(0,212,255,0.1)', color: '#00d4ff', border: '1px solid rgba(0,212,255,0.3)' }}>
            Back to Devices
          </button>
        </GlassCard>
      </div>
    )
  }

  if (!data) {
    return (
      <div className="p-4 md:p-6 space-y-4 md:space-y-5">
        <GlassCard className="p-8 text-center">
          <div className="font-display font-bold text-lg" style={{ color: '#ff3366' }}>Device Not Found</div>
          <button onClick={() => navigate('/snmp/devices')} className="mt-4 px-4 py-2 rounded font-mono text-xs"
            style={{ background: 'rgba(0,212,255,0.1)', color: '#00d4ff', border: '1px solid rgba(0,212,255,0.3)' }}>
            Back to Devices
          </button>
        </GlassCard>
      </div>
    )
  }

  const { device, capabilities } = data
  const caps = capabilities || {}
  const monitoring = Array.isArray(data.monitoring) ? data.monitoring : []

  const supportedModules = getSupportedModuleConfigs(caps)
  const allModuleConfigs = MODULE_ORDER.map(id => getModuleConfig(id)).filter(Boolean) as any[]

  const modulesWithConfig = allModuleConfigs.map(moduleConfig => {
    const config = monitoring.find(m => m.module_name === moduleConfig.id)
    const supported = !!caps[moduleConfig.id]
    return {
      module: moduleConfig,
      supported,
      config: config || {
        module_name: moduleConfig.id,
        enabled: false,
        interval_seconds: 60,
        status: supported ? 'stopped' : 'not_supported',
        last_poll_at: null,
        next_poll_at: null,
        error_message: null,
      },
    }
  })

  return (
    <div className="p-4 md:p-6 space-y-4 md:space-y-5">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 font-mono text-xs" style={{ color: '#667799' }}>
        <button onClick={() => navigate('/snmp/devices')} className="hover:text-cyan-400 transition-colors">DEVICES</button>
        <span>/</span>
        <button onClick={() => navigate(`/snmp/devices/${id}`)} className="hover:text-cyan-400 transition-colors">{device.name || device.ip_address}</button>
        <span>/</span>
        <span style={{ color: '#c8d8ee' }}>MONITORING CONFIG</span>
      </div>

      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <div className="flex-1 min-w-0">
          <h1 className="font-display font-bold text-xl sm:text-2xl tracking-widest neon-cyan">MONITORING CONFIGURATION</h1>
          <p className="font-mono text-xs mt-0.5" style={{ color: '#8899bb' }}>
            {device.name || device.ip_address} · {device.ip_address} · Per-module intervals
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge status={device.status} />
          <SNMPStatusBadge status={device.monitoring_status ? 'verified' : 'unknown'} />
          <button onClick={() => { refetch(); clearMessages(); }} className="glass-bright px-3 py-1.5 rounded font-mono text-xs hover:bg-cyan-400/10 flex items-center gap-1.5"
            style={{ border: '1px solid rgba(0,212,255,0.25)', color: '#00d4ff' }}>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M23 4v6h-6M1 20v-6h6"/><path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/>
            </svg>
            REFRESH
          </button>
          <button onClick={() => navigate(`/snmp/devices/${id}`)}
            className="glass-bright px-3 py-1.5 rounded font-mono text-xs hover:bg-gray-400/10"
            style={{ border: '1px solid rgba(136,153,187,0.25)', color: '#8899bb' }}>
            BACK TO DEVICE
          </button>
        </div>
      </div>

      {errorMessage && (
        <div className="font-mono text-xs p-3 rounded" style={{ color: '#ff3366', background: 'rgba(255,51,102,0.1)', border: '1px solid rgba(255,51,102,0.3)' }}>
          {errorMessage}
        </div>
      )}
      {successMessage && (
        <div className="font-mono text-xs p-3 rounded" style={{ color: '#00ff88', background: 'rgba(0,255,136,0.1)', border: '1px solid rgba(0,255,136,0.3)' }}>
          {successMessage}
        </div>
      )}

      {/* Legend */}
      <GlassCard className="p-3">
        <div className="flex flex-wrap items-center gap-4 font-mono text-[10px]" style={{ color: '#8899bb' }}>
          <span>LEGEND:</span>
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded" style={{ background: '#00ff88' }}></span>
            MONITORING
          </span>
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded" style={{ background: '#ff3366' }}></span>
            STOPPED
          </span>
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded" style={{ background: '#ffaa00' }}></span>
            WAITING
          </span>
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded" style={{ background: '#8899bb' }}></span>
            NOT SUPPORTED
          </span>
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded" style={{ background: '#ff3366' }}></span>
            ERROR
          </span>
          <span className="ml-auto">Intervals: 30s · 60s · 120s · 300s · 600s</span>
        </div>
      </GlassCard>

      {/* Module Configuration Table */}
      <GlassCard className="overflow-hidden">
        <div className="p-4" style={{ borderBottom: '1px solid rgba(0,212,255,0.1)' }}>
          <div className="font-display font-bold text-sm tracking-wider neon-cyan mb-1">MODULE MONITORING CONFIGURATION</div>
          <div className="font-mono text-xs" style={{ color: '#8899bb' }}>
            Configure each SNMP module independently. Only supported modules can be monitored.
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full" style={{ minWidth: 900 }}>
            <thead>
              <tr style={{ borderBottom: '1px solid rgba(0,212,255,0.08)' }}>
                {['MODULE', 'SUPPORTED', 'ENABLED', 'STATUS', 'INTERVAL', 'LAST POLL', 'NEXT POLL', 'ACTIONS'].map(h => (
                  <th key={h} className="text-left px-4 py-2.5 font-mono text-xs sticky top-0"
                    style={{ color: '#8899bb', background: 'rgba(8,25,55,0.95)' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {modulesWithConfig.map(m => {
                const status = m.config.status
                const statusColor = getModuleStatusColor(status)
                const isRunning = status === 'running'

                return (
                  <tr key={m.module.id} style={{ borderBottom: '1px solid rgba(0,212,255,0.04)' }}>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <div className="w-7 h-7 rounded flex items-center justify-center shrink-0"
                          style={{ background: m.supported ? 'rgba(0,255,136,0.1)' : 'rgba(255,51,102,0.1)' }}>
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
                            stroke={m.supported ? '#00ff88' : '#ff3366'} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                            <path d={m.module.icon} />
                          </svg>
                        </div>
                        <div className="font-mono text-xs font-medium" style={{ color: m.supported ? '#00ff88' : '#ff3366' }}>
                          {m.module.label.toUpperCase()}
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <span className="font-mono text-[10px] px-1.5 py-0.5 rounded"
                        style={{
                          background: m.supported ? 'rgba(0,255,136,0.15)' : 'rgba(255,51,102,0.15)',
                          color: m.supported ? '#00ff88' : '#ff3366',
                          border: `1px solid ${m.supported ? 'rgba(0,255,136,0.3)' : 'rgba(255,51,102,0.3)'}`,
                        }}>
                        {m.supported ? 'YES' : 'NO'}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <label className="flex items-center gap-2 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={m.config.enabled}
                          onChange={(e) => handleToggleEnabled(m.module.id, e.target.checked)}
                          disabled={!m.supported || updateMonitoring.isPending}
                          className="w-4 h-4 accent-cyan-400"
                        />
                        <span className="font-mono text-[10px]" style={{ color: m.supported ? '#c8d8ee' : '#667799' }}>
                          {m.config.enabled ? 'YES' : 'NO'}
                        </span>
                      </label>
                    </td>
                    <td className="px-4 py-3">
                      <span className="font-mono text-[10px] px-2 py-0.5 rounded"
                        style={{
                          background: `${statusColor}15`,
                          color: statusColor,
                          border: `1px solid ${statusColor}30`,
                        }}>
                        {getModuleStatusLabel(status)}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <select
                        value={m.config.interval_seconds}
                        onChange={(e) => handleUpdateInterval(m.module.id, Number(e.target.value))}
                        disabled={!m.supported}
                        className="glass-bright rounded px-2 py-1 font-mono text-xs min-w-[80px]"
                        style={{
                          border: '1px solid rgba(0,212,255,0.25)',
                          color: '#c8d8ee',
                          background: 'rgba(8,25,55,0.7)',
                          opacity: m.supported ? 1 : 0.5,
                        }}>
                        {INTERVAL_OPTIONS.map(opt => (
                          <option key={opt} value={opt}>{opt}s</option>
                        ))}
                      </select>
                    </td>
                    <td className="px-4 py-3 font-mono text-[10px]" style={{ color: '#8899bb' }}>
                      {m.config.last_poll_at ? new Date(m.config.last_poll_at).toLocaleString() : '—'}
                    </td>
                    <td className="px-4 py-3 font-mono text-[10px]" style={{ color: '#8899bb' }}>
                      {m.config.next_poll_at ? new Date(m.config.next_poll_at).toLocaleString() : '—'}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-1">
                        {m.supported && (
                          <>
                            {!isRunning ? (
                              <button onClick={() => handleStartMonitoring(m.module.id, m.config.interval_seconds)}
                                disabled={startMonitoring.isPending}
                                className="font-mono text-[10px] px-2 py-1 rounded"
                                style={{ background: 'rgba(0,255,136,0.1)', color: '#00ff88', border: '1px solid rgba(0,255,136,0.3)' }}>
                                START
                              </button>
                            ) : (
                              <button onClick={() => handleStopMonitoring(m.module.id)}
                                disabled={stopMonitoring.isPending}
                                className="font-mono text-[10px] px-2 py-1 rounded"
                                style={{ background: 'rgba(255,51,102,0.1)', color: '#ff3366', border: '1px solid rgba(255,51,102,0.3)' }}>
                                STOP
                              </button>
                            )}
                            <label className="flex items-center gap-1 cursor-pointer">
                              <input
                                type="checkbox"
                                checked={m.config.enabled}
                                onChange={(e) => handleToggleEnabled(m.module.id, e.target.checked)}
                                disabled={updateMonitoring.isPending}
                                className="w-4 h-4 accent-cyan-400"
                              />
                              <span className="font-mono text-[9px]" style={{ color: '#8899bb' }}>ENABLED</span>
                            </label>
                          </>
                        )}
                        {!m.supported && (
                          <span className="font-mono text-[10px]" style={{ color: '#667799' }}>NOT SUPPORTED</span>
                        )}
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </GlassCard>
    </div>
  )
}

function getModuleStatusColor(status: string): string {
  switch (status) {
    case 'running': return '#00ff88'
    case 'stopped': return '#ff3366'
    case 'waiting_first_poll': return '#ffaa00'
    case 'not_supported': return '#8899bb'
    case 'error': return '#ff3366'
    default: return '#8899bb'
  }
}

function getModuleStatusLabel(status: string): string {
  switch (status) {
    case 'running': return 'MONITORING'
    case 'stopped': return 'STOPPED'
    case 'waiting_first_poll': return 'WAITING'
    case 'not_supported': return 'NOT SUPPORTED'
    case 'error': return 'ERROR'
    default: return status.toUpperCase()
  }
}

// Re-export StatusBadge component for use in this file
function StatusBadge({ status, type = 'device' }: { status: string; type?: 'device' | 'snmp' | 'monitoring' }) {
  const STATUS_COLORS: Record<string, { dot: string; text: string }> = {
    online: { dot: '#00ff88', text: '#00ff88' },
    offline: { dot: '#ff3366', text: '#ff3366' },
    warning: { dot: '#ffaa00', text: '#ffaa00' },
    unknown: { dot: '#8899bb', text: '#8899bb' },
  }

  const SNMP_STATUS_COLORS: Record<string, { bg: string; text: string; border: string }> = {
    verified: { bg: 'rgba(0,255,136,0.1)', text: '#00ff88', border: 'rgba(0,255,136,0.3)' },
    unknown: { bg: 'rgba(136,153,187,0.1)', text: '#8899bb', border: 'rgba(136,153,187,0.3)' },
    error: { bg: 'rgba(255,51,102,0.1)', text: '#ff3366', border: 'rgba(255,51,102,0.3)' },
  }

  const MONITORING_STATUS_COLORS: Record<string, { bg: string; text: string; border: string }> = {
    running: { bg: 'rgba(0,255,136,0.1)', text: '#00ff88', border: 'rgba(0,255,136,0.3)' },
    stopped: { bg: 'rgba(255,51,102,0.1)', text: '#ff3366', border: 'rgba(255,51,102,0.3)' },
    waiting_first_poll: { bg: 'rgba(255,170,0,0.1)', text: '#ffaa00', border: 'rgba(255,170,0,0.3)' },
    not_supported: { bg: 'rgba(136,153,187,0.1)', text: '#8899bb', border: 'rgba(136,153,187,0.3)' },
    error: { bg: 'rgba(255,51,102,0.1)', text: '#ff3366', border: 'rgba(255,51,102,0.3)' },
  }

  const colors = type === 'device'
    ? STATUS_COLORS[status] || STATUS_COLORS.unknown
    : type === 'snmp'
    ? SNMP_STATUS_COLORS[status] || SNMP_STATUS_COLORS.unknown
    : MONITORING_STATUS_COLORS[status] || MONITORING_STATUS_COLORS.stopped

  return (
    <span
      className="font-mono text-[10px] px-2 py-0.5 rounded uppercase"
      style={{
        background: colors.bg,
        color: colors.text,
        border: `1px solid ${colors.border}`,
      }}
    >
      {status.toUpperCase()}
    </span>
  )
}
