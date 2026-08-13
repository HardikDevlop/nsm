import { useEffect, useState, useMemo } from 'react'
import { useParams, useNavigate } from 'react-router'
import GlassCard from '../components/GlassCard'
import SNMPStatusBadge from '../components/SNMPStatusBadge'
import SNMPHealthIndicator from '../components/SNMPHealthIndicator'
import { useSNMPDeviceDetails, useStartModuleMonitoring, useStopModuleMonitoring, useUpdateModuleMonitoring, useInvalidateDeviceQueries } from '../hooks/useSnmpQueries'
import { 
  SNMPModuleCard, 
  SNMPModuleShell, 
  getSupportedModuleConfigs, 
  getModuleConfig,
  MODULE_ORDER,
  formatUptime,
  formatBytes,
  getHealthColor
} from '../modules';

function formatUptimeLocal(seconds: number | undefined): string {
  if (!seconds || seconds <= 0) return '—'
  const d = Math.floor(seconds / 86400)
  const h = Math.floor((seconds % 86400) / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  if (d > 0) return `${d}d ${h}h ${m}m`
  if (h > 0) return `${h}h ${m}m`
  return `${m}m`
}

export default function SNMPDeviceDetails() {
  const { deviceId } = useParams<{ deviceId: string }>()
  const navigate = useNavigate()
  const id = Number(deviceId)
  const invalidateDevice = useInvalidateDeviceQueries()

  const startMonitoring = useStartModuleMonitoring()
  const stopMonitoring = useStopModuleMonitoring()
  const updateMonitoring = useUpdateModuleMonitoring()

  const { data, isLoading, error, refetch } = useSNMPDeviceDetails(id)

  const [activeTab, setActiveTab] = useState<'overview' | 'monitoring' | 'metrics' | 'history'>('overview')
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  const handleStartMonitoring = async (module: string, intervalSeconds: number) => {
    try {
      await startMonitoring.mutateAsync({ deviceId: id, module, intervalSeconds })
      setErrorMessage(null)
      invalidateDevice(id)
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : 'Failed to start monitoring')
    }
  }

  const handleStopMonitoring = async (module: string) => {
    try {
      await stopMonitoring.mutateAsync({ deviceId: id, module })
      setErrorMessage(null)
      invalidateDevice(id)
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : 'Failed to stop monitoring')
    }
  }

  const handleUpdateInterval = async (module: string, intervalSeconds: number) => {
    try {
      await updateMonitoring.mutateAsync({ deviceId: id, module, data: { interval_seconds: intervalSeconds } })
      setErrorMessage(null)
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : 'Failed to update interval')
    }
  }

  const handleToggleEnabled = async (module: string, enabled: boolean) => {
    try {
      await updateMonitoring.mutateAsync({ deviceId: id, module, data: { enabled } })
      setErrorMessage(null)
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : 'Failed to update monitoring')
    }
  }

  const handleRefresh = () => {
    refetch()
  }

  if (isLoading) {
    return (
      <div className="p-4 md:p-6 space-y-4 md:space-y-5">
        <div className="flex items-center justify-center p-12">
          <div className="font-mono text-sm" style={{ color: '#00d4ff' }}>Loading device details...</div>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="p-4 md:p-6 space-y-4 md:space-y-5">
        <GlassCard className="p-8 text-center">
          <div className="font-display font-bold text-lg" style={{ color: '#ff3366' }}>Failed to Load Device</div>
          <div className="font-mono text-sm mt-2" style={{ color: '#8899bb' }}>{errorMessage || error.message}</div>
          <button onClick={handleRefresh} className="mt-4 px-4 py-2 rounded font-mono text-xs"
            style={{ background: 'rgba(0,212,255,0.1)', color: '#00d4ff', border: '1px solid rgba(0,212,255,0.3)' }}>
            Retry
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

  const { device, snmp, capabilities, monitoring, latest_metrics, polling_history } = data
  const caps = capabilities || {}

  const supportedModules = useMemo(() => getSupportedModuleConfigs(caps), [caps])
  const allModuleConfigs = useMemo(() => MODULE_ORDER.map(id => getModuleConfig(id)).filter(Boolean), [])

  const modulesWithConfig = allModuleConfigs.map(moduleConfig => {
    const config = monitoring.find(m => m.module_name === moduleConfig!.id)
    const supported = !!caps[moduleConfig!.id]
    return {
      module: moduleConfig!,
      supported,
      config: config || {
        module_name: moduleConfig!.id,
        enabled: false,
        interval_seconds: 60,
        status: supported ? 'stopped' : 'not_supported',
        last_poll_at: null,
        next_poll_at: null,
        error_message: null,
      },
    }
  }).filter(m => m.module)

  return (
    <div className="p-4 md:p-6 space-y-4 md:space-y-5">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 font-mono text-xs" style={{ color: '#667799' }}>
        <button onClick={() => navigate('/snmp/devices')} className="hover:text-cyan-400 transition-colors">DEVICES</button>
        <span>/</span>
        <span style={{ color: '#c8d8ee' }}>{device.name || device.ip_address}</span>
      </div>

      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <div className="flex-1 min-w-0">
          <h1 className="font-display font-bold text-xl sm:text-2xl tracking-widest neon-cyan">
            {device.name || device.ip_address}
          </h1>
          <p className="font-mono text-xs mt-0.5" style={{ color: '#8899bb' }}>
            {device.ip_address} · {device.vendor || 'Unknown'} · {device.device_type || 'Unknown'}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge status={device.status} />
          <SNMPStatusBadge status={snmp.status === 'verified' ? 'verified' : 'unknown'} />
          <button onClick={handleRefresh} className="glass-bright px-3 py-1.5 rounded font-mono text-xs hover:bg-cyan-400/10 flex items-center gap-1.5"
            style={{ border: '1px solid rgba(0,212,255,0.25)', color: '#00d4ff' }}>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M23 4v6h-6M1 20v-6h6"/><path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/>
            </svg>
            REFRESH
          </button>
          <button onClick={() => navigate(`/snmp/devices/${id}/monitoring`)}
            className="glass-bright px-3 py-1.5 rounded font-mono text-xs hover:bg-purple-400/10"
            style={{ border: '1px solid rgba(124,58,237,0.25)', color: '#7c3aed' }}>
            CONFIGURE MONITORING
          </button>
        </div>
      </div>

      {errorMessage && (
        <div className="font-mono text-xs p-3 rounded" style={{ color: '#ff3366', background: 'rgba(255,51,102,0.1)', border: '1px solid rgba(255,51,102,0.3)' }}>
          {errorMessage}
        </div>
      )}

      {/* Tabs */}
      <div className="flex flex-wrap gap-1">
        {(['overview', 'monitoring', 'metrics', 'history'] as const).map(tab => (
          <button key={tab} onClick={() => setActiveTab(tab)}
            className="font-mono text-xs px-4 py-2 rounded capitalize transition-all"
            style={{
              background: activeTab === tab ? 'rgba(0,212,255,0.15)' : 'transparent',
              color: activeTab === tab ? '#00d4ff' : '#8899bb',
              border: `1px solid ${activeTab === tab ? 'rgba(0,212,255,0.4)' : 'rgba(0,212,255,0.1)'}`,
            }}>{tab.toUpperCase()}</button>
        ))}
      </div>

      {/* OVERVIEW TAB */}
      {activeTab === 'overview' && (
        <>
          {/* Device Summary Card */}
          <GlassCard className="p-4">
            <div className="flex flex-wrap items-start gap-4">
              <div className="flex-1 min-w-[250px]">
                <div className="flex items-center gap-3 mb-3">
                  <h2 className="font-display font-bold text-lg tracking-wider neon-cyan">
                    {device.name || device.ip_address}
                  </h2>
                  <SNMPHealthIndicator health={device.status === 'online' ? 'healthy' : device.status === 'offline' ? 'critical' : 'unknown'} showLabel size="md" />
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <div className="font-mono text-[10px] mb-0.5" style={{ color: '#667799' }}>IP Address</div>
                    <div className="font-mono text-xs" style={{ color: '#c8d8ee' }}>{device.ip_address}</div>
                  </div>
                  <div>
                    <div className="font-mono text-[10px] mb-0.5" style={{ color: '#667799' }}>Hostname</div>
                    <div className="font-mono text-xs" style={{ color: '#c8d8ee' }}>{device.hostname}</div>
                  </div>
                  <div>
                    <div className="font-mono text-[10px] mb-0.5" style={{ color: '#667799' }}>Vendor</div>
                    <div className="font-mono text-xs" style={{ color: '#c8d8ee' }}>{device.vendor || 'Unknown'}</div>
                  </div>
                  <div>
                    <div className="font-mono text-[10px] mb-0.5" style={{ color: '#667799' }}>Model</div>
                    <div className="font-mono text-xs" style={{ color: '#c8d8ee' }}>{device.model || 'Unknown'}</div>
                  </div>
                  <div>
                    <div className="font-mono text-[10px] mb-0.5" style={{ color: '#667799' }}>Serial</div>
                    <div className="font-mono text-xs" style={{ color: '#c8d8ee' }}>{device.serial_number || '—'}</div>
                  </div>
                  <div>
                    <div className="font-mono text-[10px] mb-0.5" style={{ color: '#667799' }}>Firmware</div>
                    <div className="font-mono text-xs" style={{ color: '#c8d8ee' }}>{device.firmware || '—'}</div>
                  </div>
                  <div>
                    <div className="font-mono text-[10px] mb-0.5" style={{ color: '#667799' }}>MAC</div>
                    <div className="font-mono text-xs" style={{ color: '#c8d8ee' }}>{device.mac_address || '—'}</div>
                  </div>
                  <div>
                    <div className="font-mono text-[10px] mb-0.5" style={{ color: '#667799' }}>Uptime</div>
                    <div className="font-mono text-xs" style={{ color: '#c8d8ee' }}>{formatUptimeLocal(device.uptime_seconds)}</div>
                  </div>
                </div>
              </div>

              <div className="flex flex-col gap-2 min-w-[200px]">
                <div>
                  <div className="font-mono text-[10px] mb-1" style={{ color: '#667799' }}>SNMP Version</div>
                  <div className="font-mono text-xs" style={{ color: '#c8d8ee' }}>{snmp.version || '—'}</div>
                </div>
                <div>
                  <div className="font-mono text-[10px] mb-1" style={{ color: '#667799' }}>SNMP Status</div>
                  <SNMPStatusBadge status={snmp.status === 'verified' ? 'verified' : 'unknown'} />
                </div>
                <div>
                  <div className="font-mono text-[10px] mb-1" style={{ color: '#667799' }}>Device Status</div>
                  <StatusBadge status={device.status} />
                </div>
                <div>
                  <div className="font-mono text-[10px] mb-1" style={{ color: '#667799' }}>Monitoring</div>
                  <StatusBadge status={device.monitoring_status ? 'running' : 'stopped'} type="monitoring" />
                </div>
                {device.last_seen && (
                  <div>
                    <div className="font-mono text-[10px] mb-1" style={{ color: '#667799' }}>Last Seen</div>
                    <div className="font-mono text-xs" style={{ color: '#c8d8ee' }}>
                      {new Date(device.last_seen).toLocaleString()}
                    </div>
                  </div>
                )}
              </div>
            </div>
          </GlassCard>

          {/* Capabilities */}
          <GlassCard className="p-4">
            <div className="font-display font-bold text-sm tracking-wider neon-cyan mb-3">SNMP CAPABILITIES</div>
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6 gap-2">
              {allModuleConfigs.map(moduleConfig => {
                if (!moduleConfig) return null
                const supported = !!caps[moduleConfig.id]
                return (
                  <div key={moduleConfig.id} className="flex items-center gap-2 p-2 rounded"
                    style={{
                      background: supported ? 'rgba(0,255,136,0.05)' : 'rgba(255,51,102,0.05)',
                      border: `1px solid ${supported ? 'rgba(0,255,136,0.15)' : 'rgba(255,51,102,0.15)'}`,
                    }}>
                    <div className="w-6 h-6 rounded flex items-center justify-center shrink-0"
                      style={{ background: supported ? 'rgba(0,255,136,0.1)' : 'rgba(255,51,102,0.1)' }}>
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none"
                        stroke={supported ? '#00ff88' : '#ff3366'} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                        <path d={moduleConfig.icon} />
                      </svg>
                    </div>
                    <div className="font-mono text-xs" style={{ color: supported ? '#00ff88' : '#ff3366' }}>
                      {moduleConfig.label.toUpperCase()}
                    </div>
                  </div>
                )
              })}
            </div>
          </GlassCard>

          {/* Quick Navigation to Module Pages */}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
            {supportedModules.map(moduleConfig => (
              <button key={moduleConfig.id} onClick={() => navigate(`/snmp/devices/${id}/${moduleConfig.route}`)}
                className="p-3 rounded-lg font-mono text-xs text-left transition-all hover:scale-[1.02]"
                style={{ border: `1px solid ${moduleConfig.color}33`, background: `${moduleConfig.color}0d`, color: moduleConfig.color }}>
                <div className="font-semibold">{moduleConfig.label}</div>
              </button>
            ))}
            <button key="monitoring" onClick={() => navigate(`/snmp/devices/${id}/monitoring`)}
              className="p-3 rounded-lg font-mono text-xs text-left transition-all hover:scale-[1.02]"
              style={{ border: `1px solid #7c3aed33`, background: `#7c3aed0d`, color: '#7c3aed' }}>
              <div className="font-semibold">MONITORING</div>
            </button>
            <button key="oids" onClick={() => navigate(`/snmp/oids/${id}`)}
              className="p-3 rounded-lg font-mono text-xs text-left transition-all hover:scale-[1.02]"
              style={{ border: `1px solid #14b8a633`, background: `#14b8a60d`, color: '#14b8a6' }}>
              <div className="font-semibold">OID EXPLORER</div>
            </button>
            <button key="polling" onClick={() => navigate(`/snmp/polling/${id}`)}
              className="p-3 rounded-lg font-mono text-xs text-left transition-all hover:scale-[1.02]"
              style={{ border: `1px solid #f9731633`, background: `#f973160d`, color: '#f97316' }}>
              <div className="font-semibold">POLLING</div>
            </button>
            <button key="topology" onClick={() => navigate(`/snmp/topology/${id}`)}
              className="p-3 rounded-lg font-mono text-xs text-left transition-all hover:scale-[1.02]"
              style={{ border: `1px solid #6366f133`, background: `#6366f10d`, color: '#6366f1' }}>
              <div className="font-semibold">TOPOLOGY</div>
            </button>
            <button key="back" onClick={() => navigate('/snmp/devices')}
              className="p-3 rounded-lg font-mono text-xs text-left transition-all hover:scale-[1.02]"
              style={{ border: `1px solid #8899bb33`, background: `#8899bb0d`, color: '#8899bb' }}>
              <div className="font-semibold">↑ DEVICES</div>
            </button>
          </div>
        </>
      )}

      {/* MONITORING TAB */}
      {activeTab === 'monitoring' && (
        <>
          <GlassCard className="p-4">
            <div className="font-display font-bold text-sm tracking-wider neon-cyan mb-3">MONITORING CONFIGURATION</div>
            <div className="font-mono text-xs mb-4" style={{ color: '#8899bb' }}>
              Configure per-module monitoring with custom polling intervals. Changes take effect immediately.
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
                    const intervalOptions = [30, 60, 120, 300, 600]

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
                            {intervalOptions.map(opt => (
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
        </>
      )}

      {/* METRICS TAB */}
      {activeTab === 'metrics' && (
        <>
          {/* CPU */}
          {latest_metrics.cpu && (
            <GlassCard className="p-4">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <div className="font-display font-bold text-sm tracking-wider neon-cyan">CPU</div>
                  <div className="font-mono text-xs" style={{ color: '#8899bb' }}>
                    Current: {latest_metrics.cpu.current_usage?.toFixed(1)}% · Last: {latest_metrics.cpu.polled_at ? new Date(latest_metrics.cpu.polled_at).toLocaleString() : '—'}
                  </div>
                </div>
                <div className="font-mono text-lg font-semibold" style={{ color: '#00d4ff' }}>
                  {latest_metrics.cpu.current_usage?.toFixed(1)}%
                </div>
              </div>
              {latest_metrics.cpu.per_core && Object.keys(latest_metrics.cpu.per_core).length > 0 && (
                <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-3 mt-4">
                  {Object.entries(latest_metrics.cpu.per_core).map(([core, usage]) => (
                    <div key={core} className="text-center">
                      <svg width="56" height="56" viewBox="0 0 56 56" className="mx-auto">
                        <circle cx="28" cy="28" r="22" fill="none" stroke="rgba(0,212,255,0.1)" strokeWidth="4" />
                        <circle cx="28" cy="28" r="22" fill="none"
                          stroke={usage >= 90 ? '#ff3366' : usage >= 70 ? '#ffaa00' : '#00ff88'}
                          strokeWidth="4" strokeDasharray={`${(usage / 100) * 138.2} 138.2`}
                          strokeLinecap="round" transform="rotate(-90 28 28)" />
                        <text x="28" y="33" textAnchor="middle" fontSize="11" fontFamily="monospace"
                          fill={usage >= 90 ? '#ff3366' : usage >= 70 ? '#ffaa00' : '#00ff88'}>
                          {usage.toFixed(0)}%
                        </text>
                      </svg>
                      <div className="font-mono text-[10px] mt-1" style={{ color: '#8899bb' }}>Core {core}</div>
                    </div>
                  ))}
                </div>
              )}
            </GlassCard>
          )}

          {/* Memory */}
          {latest_metrics.memory && (
            <GlassCard className="p-4">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <div className="font-display font-bold text-sm tracking-wider neon-cyan">MEMORY</div>
                  <div className="font-mono text-xs" style={{ color: '#8899bb' }}>
                    Used: {formatBytes(latest_metrics.memory.used_bytes)} / {formatBytes(latest_metrics.memory.total_bytes)} · {latest_metrics.memory.utilization_percent?.toFixed(1)}%
                  </div>
                </div>
                <div className="font-mono text-lg font-semibold" style={{ color: '#7c3aed' }}>
                  {latest_metrics.memory.utilization_percent?.toFixed(1)}%
                </div>
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <div className="p-3 rounded" style={{ background: 'rgba(0,212,255,0.05)', border: '1px solid rgba(0,212,255,0.1)' }}>
                  <div className="font-mono text-[10px]" style={{ color: '#667799' }}>TOTAL</div>
                  <div className="font-mono text-xs font-semibold" style={{ color: '#c8d8ee' }}>{formatBytes(latest_metrics.memory.total_bytes)}</div>
                </div>
                <div className="p-3 rounded" style={{ background: 'rgba(0,255,136,0.05)', border: '1px solid rgba(0,255,136,0.1)' }}>
                  <div className="font-mono text-[10px]" style={{ color: '#667799' }}>USED</div>
                  <div className="font-mono text-xs font-semibold" style={{ color: '#c8d8ee' }}>{formatBytes(latest_metrics.memory.used_bytes)}</div>
                </div>
                <div className="p-3 rounded" style={{ background: 'rgba(124,58,237,0.05)', border: '1px solid rgba(124,58,237,0.1)' }}>
                  <div className="font-mono text-[10px]" style={{ color: '#667799' }}>FREE</div>
                  <div className="font-mono text-xs font-semibold" style={{ color: '#c8d8ee' }}>{formatBytes(latest_metrics.memory.free_bytes)}</div>
                </div>
                <div className="p-3 rounded" style={{ background: 'rgba(255,170,0,0.05)', border: '1px solid rgba(255,170,0,0.1)' }}>
                  <div className="font-mono text-[10px]" style={{ color: '#667799' }}>UTIL</div>
                  <div className="font-mono text-xs font-semibold" style={{ color: '#c8d8ee' }}>{latest_metrics.memory.utilization_percent?.toFixed(1)}%</div>
                </div>
              </div>
            </GlassCard>
          )}

          {/* Storage */}
          {latest_metrics.storage && latest_metrics.storage.length > 0 && (
            <GlassCard className="p-4">
              <div className="font-display font-bold text-sm tracking-wider neon-cyan mb-4">STORAGE</div>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                {latest_metrics.storage.map(vol => (
                  <div key={vol.volume_id} className="p-3 rounded" style={{ background: 'rgba(8,25,55,0.5)', border: '1px solid rgba(0,212,255,0.1)' }}>
                    <div className="font-mono text-xs font-semibold mb-1" style={{ color: '#c8d8ee' }}>{vol.mount_name || vol.volume_id}</div>
                    <div className="grid grid-cols-2 gap-2 text-center">
                      <div>
                        <div className="font-mono text-[10px]" style={{ color: '#667799' }}>TOTAL</div>
                        <div className="font-mono text-xs" style={{ color: '#c8d8ee' }}>{formatBytes(vol.total_bytes)}</div>
                      </div>
                      <div>
                        <div className="font-mono text-[10px]" style={{ color: '#667799' }}>USED</div>
                        <div className="font-mono text-xs" style={{ color: '#c8d8ee' }}>{formatBytes(vol.used_bytes)}</div>
                      </div>
                      <div>
                        <div className="font-mono text-[10px]" style={{ color: '#667799' }}>FREE</div>
                        <div className="font-mono text-xs" style={{ color: '#c8d8ee' }}>{formatBytes(vol.free_bytes)}</div>
                      </div>
                      <div>
                        <div className="font-mono text-[10px]" style={{ color: '#667799' }}>UTIL</div>
                        <div className="font-mono text-xs font-semibold"
                          style={{ color: vol.utilization_percent && vol.utilization_percent >= 90 ? '#ff3366' : vol.utilization_percent && vol.utilization_percent >= 75 ? '#ffaa00' : '#00ff88' }}>
                          {vol.utilization_percent?.toFixed(1)}%
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </GlassCard>
          )}

          {/* Interfaces */}
          {latest_metrics.interfaces && latest_metrics.interfaces.length > 0 && (
            <GlassCard className="overflow-hidden">
              <div className="p-4" style={{ borderBottom: '1px solid rgba(0,212,255,0.1)' }}>
                <div className="font-display font-bold text-sm tracking-wider neon-cyan">INTERFACES ({latest_metrics.interfaces.length})</div>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full" style={{ minWidth: 900 }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid rgba(0,212,255,0.08)' }}>
                      {['NAME', 'STATUS', 'SPEED', 'RX', 'TX', 'UTIL', 'ERRORS', 'LAST POLL'].map(h => (
                        <th key={h} className="text-left px-4 py-2 font-mono text-xs sticky top-0"
                          style={{ color: '#8899bb', background: 'rgba(8,25,55,0.95)' }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {latest_metrics.interfaces.map(iface => (
                      <tr key={iface.interface_id} style={{ borderBottom: '1px solid rgba(0,212,255,0.04)' }}>
                        <td className="px-4 py-2 font-mono text-xs" style={{ color: '#c8d8ee' }}>{iface.name}</td>
                        <td className="px-4 py-2">
                          <span className="font-mono text-[10px] px-1.5 py-0.5 rounded"
                            style={{
                              background: iface.oper_status === 'UP' ? 'rgba(0,255,136,0.15)' : 'rgba(255,51,102,0.15)',
                              color: iface.oper_status === 'UP' ? '#00ff88' : '#ff3366',
                            }}>
                            {iface.oper_status}
                          </span>
                        </td>
                        <td className="px-4 py-2 font-mono text-[10px]" style={{ color: '#8899bb' }}>
                          {iface.speed_bps ? `${(iface.speed_bps / 1_000_000).toFixed(0)} Mbps` : '—'}
                        </td>
                        <td className="px-4 py-2 font-mono text-xs" style={{ color: '#00ff88' }}>
                          {iface.rx_mbps?.toFixed(2)} Mbps
                        </td>
                        <td className="px-4 py-2 font-mono text-xs" style={{ color: '#ff6644' }}>
                          {iface.tx_mbps?.toFixed(2)} Mbps
                        </td>
                        <td className="px-4 py-2 font-mono text-xs" style={{ color: '#ffaa00' }}>
                          {iface.utilization_percent?.toFixed(1)}%
                        </td>
                        <td className="px-4 py-2 font-mono text-[10px]" style={{ color: '#8899bb' }}>
                          {iface.errors ? `${iface.errors}` : '0'}
                        </td>
                        <td className="px-4 py-2 font-mono text-[10px]" style={{ color: '#8899bb' }}>
                          {iface.last_poll ? new Date(iface.last_poll).toLocaleTimeString() : '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </GlassCard>
          )}

          {/* Environment */}
          {latest_metrics.environment && latest_metrics.environment.length > 0 && (
            <GlassCard className="p-4">
              <div className="font-display font-bold text-sm tracking-wider neon-cyan mb-4">ENVIRONMENT SENSORS</div>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                {latest_metrics.environment.map(sensor => (
                  <div key={sensor.sensor_id} className="p-3 rounded" style={{ background: 'rgba(8,25,55,0.5)', border: '1px solid rgba(0,212,255,0.1)' }}>
                    <div className="flex items-center justify-between mb-1">
                      <div className="font-mono text-xs" style={{ color: '#c8d8ee' }}>{sensor.sensor_name}</div>
                      <span className="font-mono text-[10px] px-1.5 py-0.5 rounded uppercase"
                        style={{
                          background: sensor.status === 'ok' ? 'rgba(0,255,136,0.15)' : sensor.status === 'warning' ? 'rgba(255,170,0,0.15)' : 'rgba(255,51,102,0.15)',
                          color: sensor.status === 'ok' ? '#00ff88' : sensor.status === 'warning' ? '#ffaa00' : '#ff3366',
                        }}>
                        {sensor.status}
                      </span>
                    </div>
                    <div className="font-mono text-sm font-semibold" style={{ color: '#00d4ff' }}>
                      {sensor.value !== null ? `${sensor.value.toFixed(1)} ${sensor.unit || ''}` : '—'}
                    </div>
                    <div className="font-mono text-[10px]" style={{ color: '#8899bb' }}>
                      Type: {sensor.sensor_type} · {sensor.last_poll ? new Date(sensor.last_poll).toLocaleTimeString() : '—'}
                    </div>
                  </div>
                ))}
              </div>
            </GlassCard>
          )}
        </>
      )}

      {/* HISTORY TAB */}
      {activeTab === 'history' && (
        <GlassCard className="overflow-hidden">
          <div className="p-4" style={{ borderBottom: '1px solid rgba(0,212,255,0.1)' }}>
            <div className="font-display font-bold text-sm tracking-wider neon-cyan">POLLING HISTORY</div>
          </div>
          {polling_history && polling_history.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full" style={{ minWidth: 800 }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid rgba(0,212,255,0.08)' }}>
                    {['TIMESTAMP', 'MODULE', 'STATUS', 'DURATION', 'ERROR'].map(h => (
                      <th key={h} className="text-left px-4 py-2.5 font-mono text-xs sticky top-0"
                        style={{ color: '#8899bb', background: 'rgba(8,25,55,0.95)' }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {polling_history.map(p => (
                    <tr key={p.id} style={{ borderBottom: '1px solid rgba(0,212,255,0.04)' }}>
                      <td className="px-4 py-2 font-mono text-[10px]" style={{ color: '#8899bb' }}>
                        {new Date(p.timestamp).toLocaleString()}
                      </td>
                      <td className="px-4 py-2 font-mono text-xs" style={{ color: '#c8d8ee' }}>{p.collector.toUpperCase()}</td>
                      <td className="px-4 py-2">
                        <span className="font-mono text-[10px] px-1.5 py-0.5 rounded"
                          style={{
                            background: p.status === 'success' ? 'rgba(0,255,136,0.15)' : 'rgba(255,51,102,0.15)',
                            color: p.status === 'success' ? '#00ff88' : '#ff3366',
                          }}>
                          {p.status.toUpperCase()}
                        </span>
                      </td>
                      <td className="px-4 py-2 font-mono text-[10px]" style={{ color: '#8899bb' }}>
                        {p.duration_ms ? `${p.duration_ms.toFixed(1)} ms` : '—'}
                      </td>
                      <td className="px-4 py-2 font-mono text-[10px]" style={{ color: p.error ? '#ff3366' : '#8899bb' }}>
                        {p.error || '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="font-mono text-xs p-6 text-center" style={{ color: '#8899bb' }}>
              No polling history available yet.
            </div>
          )}
        </GlassCard>
      )}
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

function formatBytes(bytes: number | null | undefined): string {
  if (!bytes) return '—'
  if (bytes >= 1_073_741_824) return `${(bytes / 1_073_741_824).toFixed(2)} GB`
  if (bytes >= 1_048_576) return `${(bytes / 1_048_576).toFixed(1)} MB`
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${bytes} B`
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