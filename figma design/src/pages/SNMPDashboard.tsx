import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router'
import GlassCard from '../components/GlassCard'
import SNMPModuleCard from '../components/SNMPModuleCard'
import SNMPHealthIndicator from '../components/SNMPHealthIndicator'
import SNMPStatusBadge from '../components/SNMPStatusBadge'
import {
  getSNMPDeviceOverview,
  getSNMPSystemInfo,
  listSNMPDevices,
  type SNMPDeviceOverview,
  type SNMPSystemInfo,
  type DeviceRecord,
} from '../lib/api'

// Module icons mapping
const moduleIcons: Record<string, string> = {
  system: 'M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z',
  cpu: 'M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z',
  memory: 'M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4',
  storage: 'M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4',
  interfaces: 'M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4',
  environment: 'M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z',
  lldp: 'M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z',
  routing: 'M13 10V3L4 14h7v7l9-11h-7z',
  vlans: 'M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10',
  topology: 'M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9',
  mac: 'M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10',
  oids: 'M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z',
  polling: 'M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z',
  statistics: 'M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z',
  alerts: 'M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z',
}

function formatUptime(seconds: number | undefined): string {
  if (!seconds || seconds <= 0) return '—'
  const d = Math.floor(seconds / 86400)
  const h = Math.floor((seconds % 86400) / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  if (d > 0) return `${d}d ${h}h ${m}m`
  if (h > 0) return `${h}h ${m}m`
  return `${m}m`
}

export default function SNMPDashboard() {
  const { deviceId } = useParams<{ deviceId: string }>()
  const navigate = useNavigate()
  
  const [devices, setDevices] = useState<DeviceRecord[]>([])
  const [selectedDeviceId, setSelectedDeviceId] = useState<number | null>(null)
  const [overview, setOverview] = useState<SNMPDeviceOverview | null>(null)
  const [systemInfo, setSystemInfo] = useState<SNMPSystemInfo | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Load device list
  useEffect(() => {
    let ignore = false
    const loadDevices = async () => {
      try {
        const devs = await listSNMPDevices()
        if (!ignore) {
          setDevices(devs)
          // Auto-select first device or from URL
          if (deviceId) {
            setSelectedDeviceId(Number(deviceId))
          } else if (devs.length > 0) {
            setSelectedDeviceId(devs[0].id)
          }
        }
      } catch (err) {
        if (!ignore) {
          setError(err instanceof Error ? err.message : 'Failed to load devices')
        }
      }
    }
    void loadDevices()
    return () => { ignore = true }
  }, [deviceId])

  // Load device overview and system info
  useEffect(() => {
    if (!selectedDeviceId) return
    let ignore = false
    const loadData = async () => {
      setLoading(true)
      setError(null)
      try {
        const [overviewData, sysData] = await Promise.all([
          getSNMPDeviceOverview(selectedDeviceId),
          getSNMPSystemInfo(selectedDeviceId),
        ])
        if (!ignore) {
          setOverview(overviewData)
          setSystemInfo(sysData)
        }
      } catch (err) {
        if (!ignore) {
          setError(err instanceof Error ? err.message : 'Failed to load device data')
        }
      } finally {
        if (!ignore) setLoading(false)
      }
    }
    void loadData()
    return () => { ignore = true }
  }, [selectedDeviceId])

  const handleDeviceChange = (devId: number) => {
    setSelectedDeviceId(devId)
    navigate(`/snmp/dashboard/${devId}`)
  }

  const currentDevice = devices.find(d => d.id === selectedDeviceId)

  return (
    <div className="p-4 md:p-6 space-y-4 md:space-y-5">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <div className="flex-1 min-w-0">
          <h1 className="font-display font-bold text-xl sm:text-2xl tracking-widest neon-cyan">
            SNMP MONITORING
          </h1>
          <p className="font-mono text-xs mt-0.5" style={{ color: '#8899bb' }}>
            Enterprise Dynamic SNMP Management System
          </p>
        </div>
        
        {/* Device Selector */}
        {devices.length > 0 && (
          <select
            value={selectedDeviceId || ''}
            onChange={(e) => handleDeviceChange(Number(e.target.value))}
            className="glass-bright px-3 py-2 rounded font-mono text-xs min-h-[44px]"
            style={{ border: '1px solid rgba(0,212,255,0.25)', color: '#c8d8ee', background: 'rgba(8,25,55,0.6)' }}
          >
            {devices.map(dev => (
              <option key={dev.id} value={dev.id}>
                {dev.hostname || dev.ip_address}
              </option>
            ))}
          </select>
        )}
      </div>

      {error && (
        <div className="font-mono text-xs p-4 rounded" style={{ color: '#ff3366', background: 'rgba(255,51,102,0.1)', border: '1px solid rgba(255,51,102,0.3)' }}>
          {error}
        </div>
      )}

      {devices.length === 0 && !loading && (
        <GlassCard className="p-8 text-center">
          <div className="font-mono text-sm mb-3" style={{ color: '#8899bb' }}>
            No SNMP devices found
          </div>
          <div className="font-mono text-xs" style={{ color: '#667799' }}>
            Discover devices and configure SNMP credentials to start monitoring.
          </div>
          <button
            onClick={() => navigate('/snmp-monitoring')}
            className="mt-4 px-4 py-2 rounded font-mono text-xs transition-all"
            style={{ background: 'rgba(0,212,255,0.15)', color: '#00d4ff', border: '1px solid rgba(0,212,255,0.4)' }}
          >
            Go to SNMP Discovery
          </button>
        </GlassCard>
      )}

      {loading && selectedDeviceId && (
        <div className="flex items-center justify-center p-12">
          <div className="font-mono text-sm" style={{ color: '#00d4ff' }}>
            Loading device data...
          </div>
        </div>
      )}

      {!loading && overview && currentDevice && (
        <>
          {/* Device Summary Card */}
          <GlassCard className="p-4">
            <div className="flex flex-wrap items-start gap-4">
              <div className="flex-1 min-w-[250px]">
                <div className="flex items-center gap-3 mb-3">
                  <h2 className="font-display font-bold text-lg tracking-wider neon-cyan">
                    {overview.hostname || currentDevice.ip_address}
                  </h2>
                  <SNMPHealthIndicator health={overview.health} showLabel size="md" />
                </div>
                
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <div className="font-mono text-[10px] mb-0.5" style={{ color: '#667799' }}>IP Address</div>
                    <div className="font-mono text-xs" style={{ color: '#c8d8ee' }}>{overview.ip_address}</div>
                  </div>
                  <div>
                    <div className="font-mono text-[10px] mb-0.5" style={{ color: '#667799' }}>Vendor</div>
                    <div className="font-mono text-xs" style={{ color: '#c8d8ee' }}>{overview.vendor || 'Unknown'}</div>
                  </div>
                  <div>
                    <div className="font-mono text-[10px] mb-0.5" style={{ color: '#667799' }}>Model</div>
                    <div className="font-mono text-xs" style={{ color: '#c8d8ee' }}>{overview.model || 'Unknown'}</div>
                  </div>
                  <div>
                    <div className="font-mono text-[10px] mb-0.5" style={{ color: '#667799' }}>Uptime</div>
                    <div className="font-mono text-xs" style={{ color: '#c8d8ee' }}>
                      {systemInfo?.uptime_display || formatUptime(overview.uptime_seconds)}
                    </div>
                  </div>
                </div>
              </div>

              <div className="flex flex-col gap-2">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-[10px]" style={{ color: '#667799' }}>Polling:</span>
                  <SNMPStatusBadge status={overview.polling_enabled ? 'active' : 'inactive'} />
                </div>
                {overview.last_poll && (
                  <div className="font-mono text-[10px]" style={{ color: '#667799' }}>
                    Last: {new Date(overview.last_poll).toLocaleString()}
                  </div>
                )}
              </div>
            </div>

            {/* System Description */}
            {systemInfo?.supported && systemInfo.description && (
              <div className="mt-4 pt-4" style={{ borderTop: '1px solid rgba(0,212,255,0.1)' }}>
                <div className="font-mono text-[10px] mb-1" style={{ color: '#667799' }}>System Description</div>
                <div className="font-mono text-xs" style={{ color: '#8899bb' }}>{systemInfo.description}</div>
              </div>
            )}
          </GlassCard>

          {/* ── Quick navigation to every SNMP sub-page ── */}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
            {[
              { label:'CPU',        path:`/snmp/cpu/${selectedDeviceId}`,         color:'#00ff88' },
              { label:'Memory',     path:`/snmp/memory/${selectedDeviceId}`,      color:'#7c3aed' },
              { label:'Interfaces', path:`/snmp/interfaces/${selectedDeviceId}`,  color:'#00bfff' },
              { label:'Storage',    path:`/snmp/storage/${selectedDeviceId}`,     color:'#ffaa00' },
              { label:'Environment',path:`/snmp/environment/${selectedDeviceId}`, color:'#ff6644' },
              { label:'Topology',   path:`/snmp/topology/${selectedDeviceId}`,    color:'#a78bfa' },
              { label:'OID Explorer',path:`/snmp/oids/${selectedDeviceId}`,       color:'#34d399' },
              { label:'Polling',    path:`/snmp/polling/${selectedDeviceId}`,     color:'#f472b6' },
              { label:'Statistics', path:`/snmp/statistics/${selectedDeviceId}`,  color:'#fb923c' },
              { label:'↑ SNMP Home',path:'/snmp-monitoring',                      color:'#8899bb' },
            ].map(nav => (
              <button key={nav.label} onClick={()=>navigate(nav.path)}
                className="p-3 rounded-lg font-mono text-xs text-left transition-all hover:scale-[1.02]"
                style={{ border:`1px solid ${nav.color}33`, background:`${nav.color}0d`, color:nav.color }}>
                <div className="font-semibold">{nav.label}</div>
              </button>
            ))}
          </div>

          {/* Module Cards Grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {overview.modules.map(module => {
              const icon = moduleIcons[module.name.toLowerCase()] || moduleIcons.system
              const routePath = `/snmp/${module.name.toLowerCase()}/${selectedDeviceId}`

              return (
                <SNMPModuleCard
                  key={module.name}
                  title={module.name.toUpperCase()}
                  icon={icon}
                  status={module.status}
                  health={module.health}
                  lastPoll={module.last_poll}
                  objectCount={module.object_count}
                  navigateTo={module.status === 'supported' ? routePath : undefined}
                  summary={
                    module.status === 'supported' && module.summary ? (
                      <div className="space-y-1">
                        {Object.entries(module.summary).slice(0, 3).map(([key, value]) => (
                          <div key={key} className="flex justify-between items-center gap-2">
                            <span className="font-mono text-[10px] truncate" style={{ color: '#667799' }}>
                              {key.replace(/_/g, ' ')}:
                            </span>
                            <span className="font-mono text-[10px] font-semibold" style={{ color: '#c8d8ee' }}>
                              {String(value)}
                            </span>
                          </div>
                        ))}
                      </div>
                    ) : undefined
                  }
                />
              )
            })}
          </div>

          {/* Quick Actions */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <button
              onClick={() => navigate(`/snmp/oids/${selectedDeviceId}`)}
              className="glass-bright p-3 rounded font-mono text-xs transition-all hover:bg-cyan-400/5 text-left"
              style={{ border: '1px solid rgba(0,212,255,0.15)' }}
            >
              <div className="font-semibold mb-1 neon-cyan">OID Explorer</div>
              <div style={{ color: '#8899bb' }}>Browse all OIDs</div>
            </button>
            <button
              onClick={() => navigate(`/snmp/polling/${selectedDeviceId}`)}
              className="glass-bright p-3 rounded font-mono text-xs transition-all hover:bg-cyan-400/5 text-left"
              style={{ border: '1px solid rgba(0,212,255,0.15)' }}
            >
              <div className="font-semibold mb-1 neon-cyan">Poll History</div>
              <div style={{ color: '#8899bb' }}>View polling logs</div>
            </button>
            <button
              onClick={() => navigate(`/snmp/statistics/${selectedDeviceId}`)}
              className="glass-bright p-3 rounded font-mono text-xs transition-all hover:bg-cyan-400/5 text-left"
              style={{ border: '1px solid rgba(0,212,255,0.15)' }}
            >
              <div className="font-semibold mb-1 neon-cyan">Statistics</div>
              <div style={{ color: '#8899bb' }}>Performance data</div>
            </button>
            <button
              onClick={() => navigate(`/snmp/topology`)}
              className="glass-bright p-3 rounded font-mono text-xs transition-all hover:bg-cyan-400/5 text-left"
              style={{ border: '1px solid rgba(0,212,255,0.15)' }}
            >
              <div className="font-semibold mb-1 neon-cyan">Topology</div>
              <div style={{ color: '#8899bb' }}>Network map</div>
            </button>
          </div>
        </>
      )}
    </div>
  )
}
