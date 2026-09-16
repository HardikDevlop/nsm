import { ReactNode } from 'react'
import { useNavigate, useParams } from 'react-router'
import GlassCard from '../../../components/GlassCard'
import SNMPStatusBadge from './SNMPStatusBadge'
import { useSNMPDeviceDetails, useStartModuleMonitoring, useStopModuleMonitoring, useUpdateModuleMonitoring } from '../hooks/useSnmpQueries'

const INTERVALS = [15, 30, 60, 120, 300, 600]

const MODULE_ROUTES: Record<string, string> = {
  overview: '',
  monitoring: 'monitoring',
  interfaces: 'interfaces',
  cpu: 'cpu',
  memory: 'memory',
  storage: 'storage',
  environment: 'environment',
  vlan: 'vlan',
  lldp: 'lldp',
  routing: 'routing',
}

function title(text: string) {
  return text.replace(/_/g, ' ').replace(/\b\w/g, char => char.toUpperCase())
}

export function SNMPModuleShell({
  module,
  title: pageTitle,
  children,
  unsupportedMessage,
}: {
  module: string
  title?: string
  children: ReactNode
  unsupportedMessage?: string
}) {
  const { deviceId } = useParams<{ deviceId: string }>()
  const navigate = useNavigate()
  const id = Number(deviceId)
  const { data, isLoading, error } = useSNMPDeviceDetails(id)
  const start = useStartModuleMonitoring()
  const stop = useStopModuleMonitoring()
  const update = useUpdateModuleMonitoring()

  if (isLoading) {
    return <div className="p-4 md:p-6 font-mono text-sm" style={{ color: '#00d4ff' }}>Loading device...</div>
  }

  if (error || !data) {
    return (
      <div className="p-4 md:p-6">
        <GlassCard className="p-6 text-center">
          <div className="font-display font-bold" style={{ color: '#ff3366' }}>Unable to load SNMP device</div>
          <div className="font-mono text-xs mt-2" style={{ color: '#8899bb' }}>{error?.message ?? 'Device not found'}</div>
        </GlassCard>
      </div>
    )
  }

  const device = data.device
  const supported = module === 'overview' || module === 'monitoring' || Boolean(data.capabilities?.[module])
  const config = data.monitoring.find(item => item.module_name === module)
  const isRunning = config?.status === 'running'
  const interval = config?.interval_seconds ?? 60

  return (
    <div className="p-4 md:p-6 space-y-4 md:space-y-5">
      <div className="flex items-center gap-2 font-mono text-xs" style={{ color: '#667799' }}>
        <button type="button" onClick={() => navigate('/snmp/devices')} className="hover:text-cyan-400">SNMP DEVICES</button>
        <span>/</span>
        <button type="button" onClick={() => navigate(`/snmp/devices/${id}`)} className="hover:text-cyan-400">{device.name || device.ip_address}</button>
        <span>/</span>
        <span style={{ color: '#c8d8ee' }}>{pageTitle ?? title(module)}</span>
      </div>

      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3">
        <div className="min-w-0">
          <h1 className="font-display font-bold text-xl sm:text-2xl tracking-widest neon-cyan">{pageTitle ?? title(module)}</h1>
          <p className="font-mono text-xs mt-0.5" style={{ color: '#8899bb' }}>
            {device.name || device.hostname || device.ip_address} · {device.ip_address} · {device.last_seen ? `Last seen ${new Date(device.last_seen).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', hour12: true })}` : 'Last seen N/A'}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <SNMPStatusBadge status={data.snmp.status === 'verified' ? 'verified' : 'unknown'} />
          {module !== 'overview' && module !== 'monitoring' && (
            <>
              <select
                value={interval}
                disabled={!supported}
                onChange={event => update.mutate({ deviceId: id, module, data: { interval_seconds: Number(event.target.value) } })}
                className="glass-bright rounded px-2 py-1.5 font-mono text-xs"
                style={{ border: '1px solid rgba(0,212,255,0.25)', color: '#c8d8ee', background: 'rgba(8,25,55,0.7)', opacity: supported ? 1 : 0.5 }}
              >
                {INTERVALS.map(value => <option key={value} value={value}>{value}s</option>)}
              </select>
              {isRunning ? (
                <button type="button" disabled={!supported || stop.isPending} onClick={() => stop.mutate({ deviceId: id, module })}
                  className="px-3 py-1.5 rounded font-mono text-xs" style={{ border: '1px solid rgba(255,51,102,0.35)', color: '#ff3366', background: 'rgba(255,51,102,0.1)' }}>
                  STOP MONITORING
                </button>
              ) : (
                <button type="button" disabled={!supported || start.isPending} onClick={() => start.mutate({ deviceId: id, module, intervalSeconds: interval })}
                  className="px-3 py-1.5 rounded font-mono text-xs" style={{ border: '1px solid rgba(0,255,136,0.35)', color: '#00ff88', background: 'rgba(0,255,136,0.1)' }}>
                  START MONITORING
                </button>
              )}
            </>
          )}
        </div>
      </div>

      <div className="flex gap-1 overflow-x-auto pb-1">
        {Object.entries(MODULE_ROUTES).map(([key, route]) => {
          const ok = key === 'overview' || key === 'monitoring' || Boolean(data.capabilities?.[key])
          const active = key === module
          return (
            <button key={key} type="button" disabled={!ok} onClick={() => navigate(`/snmp/devices/${id}${route ? `/${route}` : ''}`)}
              className="font-mono text-xs px-3 py-2 rounded whitespace-nowrap"
              style={{
                background: active ? 'rgba(0,212,255,0.15)' : 'transparent',
                color: active ? '#00d4ff' : ok ? '#8899bb' : '#556677',
                border: `1px solid ${active ? 'rgba(0,212,255,0.4)' : 'rgba(0,212,255,0.1)'}`,
                cursor: ok ? 'pointer' : 'not-allowed',
              }}>
              {title(key)}{!ok ? ' · Not Supported' : ''}
            </button>
          )
        })}
      </div>

      {!supported ? (
        <GlassCard className="p-8 text-center">
          <div className="font-display font-bold text-base" style={{ color: '#8899bb' }}>{unsupportedMessage ?? `${title(module)} is not supported by this device.`}</div>
        </GlassCard>
      ) : children}
    </div>
  )
}
