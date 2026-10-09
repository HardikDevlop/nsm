import { useMemo, useState } from 'react'
import { useParams } from 'react-router'
import { SNMPModuleShell } from '../modules/SNMPModuleShell'
import { formatBytes, formatSpeed } from '../modules/snmpModuleRegistry'
import GlassCard from '../../../components/GlassCard'
import SNMPCollectorDataCard from '../components/SNMPCollectorDataCard'
import { useModuleData, useDeviceCapabilities } from '../modules/useSNMPModules'
import { useLatestInterfaces } from '../hooks/useSnmpQueries'
import { formatIST } from '../../../time'

function interfaceHealth(util: number | undefined, status: string): 'healthy' | 'warning' | 'critical' | 'unknown' {
  if (status !== 'UP') return 'critical'
  if (util === undefined || util === null) return 'unknown'
  if (util >= 90) return 'critical'
  if (util >= 75) return 'warning'
  return 'healthy'
}

function asNumber(value: any): number | undefined {
  if (value === null || value === undefined || value === '') return undefined
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : undefined
}

function formatInterfaceSpeed(iface: any): string {
  if (iface?.speed_label) return String(iface.speed_label)
  const speed = asNumber(iface?.speed_bps)
  return speed !== undefined ? formatSpeed(speed) : '—'
}

function formatInterfaceMac(iface: any): string {
  const value = iface?.mac ?? iface?.mac_address ?? iface?.mac_raw ?? iface?.phys_address ?? iface?.physical_address ?? iface?.hardware_address ?? iface?.ifPhysAddr
  if (!value) return 'N/A (not advertised)'
  const compact = String(value).replace(/[^0-9a-f]/gi, '')
  if (compact.length === 12) return compact.match(/.{2}/g)?.join(':').toUpperCase() ?? String(value)
  return String(value)
}

function formatTraffic(iface: any, direction: 'rx' | 'tx'): string {
  const mbps = asNumber(direction === 'rx' ? iface?.rx_mbps : iface?.tx_mbps)
  if (mbps !== undefined) return `${mbps.toFixed(2)} Mbps`

  const bps = asNumber(direction === 'rx' ? iface?.rx_bps : iface?.tx_bps)
  if (bps !== undefined) return `${formatSpeed(bps)}/s`

  const octets = asNumber(direction === 'rx' ? (iface?.rx_octets ?? iface?.in_octets) : (iface?.tx_octets ?? iface?.out_octets))
  return octets !== undefined ? formatBytes(octets) : '—'
}

function canonicalInterfaceName(value: unknown): string {
  return String(value || '')
    .replace(/^[^·]+·\s*/, '')
    .trim()
    .toLowerCase()
}

function displayInterfaceName(value: unknown, ifIndex?: unknown): string {
  const name = String(value || `Interface ${ifIndex ?? ''}`).trim()
  return name.includes('·') ? name.split('·').pop()!.trim() : name
}

function isPhysicalInterface(iface: any): boolean {
  const type = String(iface?.type || iface?.if_type || '').toLowerCase()
  const name = String(iface?.name || iface?.description || '').toLowerCase()
  if (/(loopback|vlan|tunnel|virtual|bridge|lag|port-channel|bond|cpu|null)/.test(`${type} ${name}`)) return false
  return /(ethernet|gigabit|fastethernet|tengig|twentyfive|fortygig|hundredgig|fiber|physical)/.test(`${type} ${name}`)
}

function preferInterface(current: any, candidate: any): any {
  const score = (iface: any) =>
    Number(String(iface?.oper_status || '').toLowerCase() === 'up') * 4 +
    Number(isPhysicalInterface(iface)) * 3 +
    Number(Boolean(iface?.mac || iface?.mac_address)) * 2 +
    Number(Boolean(iface?.rx_mbps || iface?.tx_mbps || iface?.in_octets || iface?.out_octets))
  return score(candidate) > score(current) ? candidate : current
}

export default function SNMPInterfaceMonitoring() {
  const { deviceId } = useParams<{ deviceId: string }>()
  const id = Number(deviceId)

  const { data: caps } = useDeviceCapabilities(id)
  const { data, isLoading, error } = useModuleData(id, 'interfaces')
  const { data: latestInterfaces } = useLatestInterfaces(id)
  const [statusFilter, setStatusFilter] = useState<'ALL' | 'UP' | 'DOWN'>('ALL')

  const livePayload = data as any
  const liveData = livePayload?.data ?? {}
  const interfaces = useMemo(() => {
    const rows = Array.isArray(liveData?.interfaces)
      ? liveData.interfaces
      : Array.isArray(livePayload)
        ? livePayload
        : []
    const sourceRows = rows.length > 0 ? rows : (latestInterfaces || [])
    const uniqueRows = new Map<string, any>()
    sourceRows.forEach((iface: any, index: number) => {
      const key = canonicalInterfaceName(iface?.name || iface?.description || iface?.ifIndex || index) || `interface-${index}`
      const current = uniqueRows.get(key)
      uniqueRows.set(key, current ? preferInterface(current, iface) : iface)
    })
    return [...uniqueRows.values()]
  }, [latestInterfaces, liveData?.interfaces, livePayload])
  const supported = caps?.interfaces === true || livePayload?.supported === true || interfaces.length > 0
  const interfaceCollector = {
    collector: 'interfaces',
    supported: true,
    timestamp: livePayload?.timestamp || interfaces.find(i => i.last_poll || i.polled_at || i.last_updated)?.last_poll,
    data: Object.keys(liveData || {}).length > 0 ? liveData : { interfaces },
    reason: livePayload?.reason,
    missing: livePayload?.missing || [],
    warnings: livePayload?.warnings || [],
  }

  if (!isLoading && !supported && !interfaces.length) {
    return (
      <SNMPModuleShell module="interfaces" title="Interface Monitoring" unsupportedMessage="Interface monitoring is not supported by this device.">
        <div />
      </SNMPModuleShell>
    )
  }

  const upCount = interfaces.filter(i => (i.oper_status ?? '').toUpperCase() === 'UP').length
  const downCount = interfaces.filter(i => (i.oper_status ?? '').toUpperCase() === 'DOWN' || i.oper_status === 'down').length
  const visibleInterfaces = (statusFilter === 'ALL'
    ? interfaces
    : interfaces.filter(i => (i.oper_status ?? '').toUpperCase() === statusFilter)
  ).slice().sort((a, b) => Number(a.ifIndex ?? a.if_index ?? 0) - Number(b.ifIndex ?? b.if_index ?? 0))
  const otherCount = Math.max(interfaces.length - upCount - downCount, 0)
  const physicalCount = interfaces.filter(isPhysicalInterface).length
  const updatedAt = livePayload?.timestamp || interfaces.find(i => i.last_poll || i.polled_at || i.last_updated)?.last_poll || interfaces.find(i => i.last_updated)?.last_updated

  return (
    <SNMPModuleShell module="interfaces" title="Interface Monitoring" showMonitoringControls={true}>
      {(isLoading || error || livePayload?.reason || updatedAt) && (
        <GlassCard className="p-3">
          <div className="flex flex-wrap items-center gap-3 font-mono text-xs">
            <span style={{ color: isLoading ? '#ffaa00' : error ? '#ff3366' : '#00ff88' }}>
              {isLoading ? 'Loading latest poll...' : error ? 'Latest poll unavailable' : 'Latest poll snapshot'}
            </span>
            {updatedAt && <span style={{ color: 'var(--t-text-secondary)' }}>Updated {formatIST(updatedAt)}</span>}
            {livePayload?.collection_ms != null && <span style={{ color: '#8899bb' }}>{livePayload.collection_ms} ms</span>}
            {error && <span className="truncate" style={{ color: '#ff6688' }}>{error.message}</span>}
            {!error && livePayload?.reason && <span className="truncate" style={{ color: '#ffaa00' }}>{livePayload.reason}</span>}
          </div>
        </GlassCard>
      )}

      {/* Summary Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 mb-4">
        {[
          { label: 'Total', value: interfaces.length, color: '#00d4ff' },
          { label: 'UP', value: upCount, color: '#00ff88' },
          { label: 'DOWN', value: downCount, color: downCount > 0 ? '#ff3366' : '#00ff88' },
          { label: 'OTHER', value: otherCount, color: otherCount > 0 ? '#ffaa00' : '#8899bb' },
          { label: 'PHYSICAL', value: physicalCount, color: '#22d3ee' },
        ].map(tile => (
          <GlassCard key={tile.label} className="p-4 text-center">
            <div className="font-display font-bold text-xl sm:text-2xl" style={{ color: tile.color }}>
              {tile.value}
            </div>
            <div className="font-mono text-xs mt-1" style={{ color: '#8899bb' }}>{tile.label}</div>
          </GlassCard>
        ))}
      </div>

      {/* Interface Table */}
      <GlassCard className="overflow-hidden">
        <div className="p-4" style={{ borderBottom: '1px solid rgba(0,212,255,0.1)' }}>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="font-display font-bold text-sm tracking-wider neon-cyan">INTERFACES ({visibleInterfaces.length})</div>
            <select value={statusFilter} onChange={event => setStatusFilter(event.target.value as 'ALL' | 'UP' | 'DOWN')} className="rounded px-3 py-1.5 font-mono text-xs" style={{ background: 'var(--t-card)', color: 'var(--t-text)', border: '1px solid var(--t-border-alpha)' }} aria-label="Interface status filter">
              <option value="ALL">ALL</option>
              <option value="UP">UP</option>
              <option value="DOWN">DOWN</option>
            </select>
          </div>
        </div>
        <div className="overflow-x-auto">
          {visibleInterfaces.length === 0 ? (
            <div className="font-mono text-xs text-center py-8" style={{ color: '#8899bb' }}>
              No interface rows yet. Start interface monitoring or use REFRESH after SNMP credentials are verified.
            </div>
          ) : (
          <table className="w-full snmp-readable-table snmp-collector-data-table snmp-interface-table" style={{ minWidth: 1100 }}>
            <thead>
              <tr style={{ borderBottom: '1px solid rgba(0,212,255,0.08)' }}>
                {[
                  { key: 'if-index', label: 'IF INDEX', sortable: true },
                  { key: 'name', label: 'NAME', sortable: true },
                  { key: 'status', label: 'STATUS' },
                  { key: 'speed', label: 'SPEED', sortable: true },
                  { key: 'rx', label: 'RX', sortable: true },
                  { key: 'tx', label: 'TX', sortable: true },
                  { key: 'errors', label: 'ERRORS', sortable: true },
                  { key: 'discards', label: 'DISCARDS', sortable: true },
                ].map(col => (
                  <th
                    key={col.key}
                    className="text-left px-4 py-2.5 font-mono text-xs sticky top-0 select-none"
                    style={{ color: '#111827', background: 'transparent', opacity: 1, userSelect: 'none' }}
                  >
                    {col.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {visibleInterfaces.map((iface, index) => {
                const operStatus = (iface.oper_status ?? '').toUpperCase()
                const health = interfaceHealth(iface.utilization_percent, operStatus)
                const hColors = { healthy: '#00ff88', warning: '#ffaa00', critical: '#ff3366', unknown: '#8899bb' }
                return (
                  <tr
                    key={iface.interface_id ?? iface.ifIndex ?? iface.name ?? index}
                    style={{
                      borderBottom: '1px solid rgba(0,212,255,0.04)',
                      background: index % 2 === 0 ? 'transparent' : 'rgba(0,212,255,0.01)',
                    }}
                  >
                    <td className="px-4 py-2 font-mono text-xs font-semibold" style={{ color: 'var(--t-text, #111827)', opacity: 1 }}>
                      {iface.ifIndex ?? iface.if_index ?? '—'}
                    </td>
                    <td className="px-4 py-2 font-mono text-xs font-semibold" style={{ color: 'var(--t-text, #111827)', opacity: 1 }}>
                      {displayInterfaceName(iface.name, iface.ifIndex)}
                    </td>
                    <td className="px-4 py-2">
                      <span className="font-mono text-[10px] px-1.5 py-0.5 rounded"
                        style={{
                          background: (iface.oper_status === 'UP' || iface.oper_status === 'up') ? 'rgba(0,255,136,0.15)' : 'rgba(255,51,102,0.15)',
                          color: (iface.oper_status === 'UP' || iface.oper_status === 'up') ? '#00ff88' : '#ff3366',
                          border: `1px solid ${(iface.oper_status === 'UP' || iface.oper_status === 'up') ? 'rgba(0,255,136,0.3)' : 'rgba(255,51,102,0.3)'}`,
                        }}>
                        {(iface.oper_status ?? 'UNKNOWN').toUpperCase()}
                      </span>
                    </td>
                    <td className="px-4 py-2 font-mono text-[10px]" style={{ color: '#8899bb' }}>
                      {formatInterfaceSpeed(iface)}
                    </td>
                    <td className="px-4 py-2 font-mono text-xs" style={{ color: '#00ff88' }}>
                      {formatTraffic(iface, 'rx')}
                    </td>
                    <td className="px-4 py-2 font-mono text-xs" style={{ color: '#ff6644' }}>
                      {formatTraffic(iface, 'tx')}
                    </td>
                    <td className="px-4 py-2 font-mono text-[10px]" style={{ color: (iface.errors ?? iface.in_errors ?? 0) > 0 ? '#ff3366' : '#8899bb' }}>
                      {(iface.errors ?? iface.in_errors ?? 0)}
                    </td>
                    <td className="px-4 py-2 font-mono text-[10px]" style={{ color: (iface.discards ?? iface.in_discards ?? 0) > 0 ? '#ffaa00' : '#8899bb' }}>
                      {(iface.discards ?? iface.in_discards ?? 0)}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
          )}
        </div>
      </GlassCard>

      <SNMPCollectorDataCard name="interfaces" collector={interfaceCollector} />
    </SNMPModuleShell>
  )
}
