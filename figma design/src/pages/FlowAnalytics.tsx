import { useQuery } from '@tanstack/react-query'
import GlassCard from '../components/GlassCard'
import { useAuth } from '../components/AuthContext'
import { getFlowAnalytics, getFlowRecords, getFlowTrends, listDeviceOptions, listSites, type FlowAnalyticsFilters, type FlowAnalyticsItem, type FlowRecord, type SiteRecord } from '../lib/api'
import { useState } from 'react'

const dimensions = [
  ['talkers', 'Top Talkers'], ['sources', 'Top Sources'], ['destinations', 'Top Destinations'],
  ['applications', 'Applications'], ['protocols', 'Protocols'], ['conversations', 'Conversations'],
  ['interfaces', 'Interfaces'],
] as const

const formatBytes = (value: number) => {
  if (!value) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const power = Math.min(units.length - 1, Math.floor(Math.log(value) / Math.log(1024)))
  return `${(value / 1024 ** power).toFixed(power ? 1 : 0)} ${units[power]}`
}

function AnalyticsTable({ title, items }: { title: string; items?: FlowAnalyticsItem[] }) {
  const sourceLabel = (item: FlowAnalyticsItem) => {
    if (item.source === 'ipfix' && item.quality === 'accounted') return 'IPFIX · Accounted'
    if (item.source === 'ipfix' && item.sampled === true) return 'IPFIX · Sampled'
    if (item.source === 'sflow' && item.quality === 'estimated') return 'sFlow · Estimated'
    if (item.source === 'sflow' && item.quality === 'counter') return 'sFlow · Counter'
    return 'Unknown'
  }
  return <GlassCard className="overflow-hidden">
    <div className="px-4 py-3 flex items-center justify-between" style={{ borderBottom: '1px solid var(--t-border-light)' }}>
      <h2 className="font-display font-semibold text-sm" style={{ color: 'var(--t-text)' }}>{title}</h2>
      <span className="font-mono text-[10px]" style={{ color: 'var(--t-muted)' }}>{items?.length ?? 0} results</span>
    </div>
    <div className="overflow-x-auto"><table className="w-full text-left"><thead><tr style={{ color: 'var(--t-muted)' }}>
      {['Name', 'Bytes', 'Packets', 'Flows'].map(label => <th key={label} className="px-4 py-2 font-mono text-[10px] uppercase">{label}</th>)}
    </tr></thead><tbody>{items?.length ? items.map(item => <tr key={item.name} style={{ borderTop: '1px solid var(--t-border-alpha)' }}>
      <td className="px-4 py-2 font-mono text-xs" style={{ color: 'var(--t-text)' }}><div>{item.name}</div><span className="inline-flex mt-1 rounded border px-1.5 py-0.5 text-[9px] uppercase tracking-wide" style={{ color: 'var(--t-muted)', borderColor: 'var(--t-border-alpha)' }}>{sourceLabel(item)}</span></td>
      <td className="px-4 py-2 font-mono text-xs" style={{ color: '#00d4ff' }}>{formatBytes(item.bytes)}</td>
      <td className="px-4 py-2 font-mono text-xs" style={{ color: 'var(--t-muted)' }}>{item.packets.toLocaleString()}</td>
      <td className="px-4 py-2 font-mono text-xs" style={{ color: 'var(--t-muted)' }}>{item.flows.toLocaleString()}</td>
    </tr>) : <tr><td colSpan={4} className="px-4 py-8 text-center font-mono text-xs" style={{ color: 'var(--t-muted)' }}>No flow data for these filters</td></tr>}</tbody></table></div>
  </GlassCard>
}

function Trend({ points }: { points?: { timestamp: string; bytes: number }[] }) {
  if (!points?.length) return <div className="h-40 flex items-center justify-center font-mono text-xs" style={{ color: 'var(--t-muted)' }}>No trend data for these filters</div>
  const max = Math.max(...points.map(point => point.bytes), 1)
  return <div className="h-40 flex items-end gap-1 px-4 pb-4 pt-5">
    {points.map(point => <div key={point.timestamp} title={`${new Date(point.timestamp).toLocaleString()}: ${formatBytes(point.bytes)}`} className="flex-1 rounded-t bg-cyan-400/60 hover:bg-cyan-300 transition-colors" style={{ height: `${Math.max(3, (point.bytes / max) * 100)}%` }} />)}
  </div>
}

const display = (value: string | number | null | undefined) => value == null || value === '' ? '—' : String(value)
const dateTime = (value: string | null) => value ? new Date(value).toLocaleString() : '—'

function FlowRecordsTable({ records, isLoading, page, hasNext, onPageChange }: { records?: FlowRecord[]; isLoading: boolean; page: number; hasNext: boolean; onPageChange: (page: number) => void }) {
  return <GlassCard className="overflow-hidden">
    <div className="px-4 py-3 flex items-center justify-between" style={{ borderBottom: '1px solid var(--t-border-light)' }}>
      <div><h2 className="font-display font-semibold text-sm" style={{ color: 'var(--t-text)' }}>Flow Records</h2><p className="font-mono text-[10px] mt-1" style={{ color: 'var(--t-muted)' }}>Detailed exporter records</p></div>
      <span className="font-mono text-[10px]" style={{ color: 'var(--t-muted)' }}>{records?.length ?? 0} records</span>
    </div>
    <div className="overflow-x-auto"><table className="w-full text-left min-w-[1250px]"><thead><tr style={{ color: 'var(--t-muted)' }}>
      {['Time', 'Device / Exporter', 'Source', 'Destination', 'IP Protocol', 'Bytes', 'Packets', 'Interfaces', 'Type'].map(label => <th key={label} className="px-4 py-2 font-mono text-[10px] uppercase">{label}</th>)}
    </tr></thead><tbody>
      {isLoading ? <tr><td colSpan={9} className="px-4 py-8 text-center font-mono text-xs" style={{ color: 'var(--t-muted)' }}>Loading flow records...</td></tr> : records?.length ? records.map(record => <tr key={record.id} style={{ borderTop: '1px solid var(--t-border-alpha)' }}>
        <td className="px-4 py-3 font-mono text-[10px]" style={{ color: 'var(--t-muted)' }}><div>{dateTime(record.flow_start)}</div><div className="mt-1">to {dateTime(record.flow_end)}</div></td>
        <td className="px-4 py-3 font-mono text-xs" style={{ color: 'var(--t-text)' }}><div>{display(record.device_name)}</div><div className="mt-1 text-[10px]" style={{ color: 'var(--t-muted)' }}>{record.exporter_ip}</div></td>
        <td className="px-4 py-3 font-mono text-xs" style={{ color: '#00d4ff' }}>{display(record.src_ip)}{record.src_port != null ? `:${record.src_port}` : ''}</td>
        <td className="px-4 py-3 font-mono text-xs" style={{ color: '#00d4ff' }}>{display(record.dst_ip)}{record.dst_port != null ? `:${record.dst_port}` : ''}</td>
        <td className="px-4 py-3 font-mono text-xs" style={{ color: 'var(--t-muted)' }}>{display(record.ip_protocol)}</td>
        <td className="px-4 py-3 font-mono text-xs" style={{ color: '#00d4ff' }}>{formatBytes(record.bytes)}</td>
        <td className="px-4 py-3 font-mono text-xs" style={{ color: 'var(--t-muted)' }}>{record.packets.toLocaleString()}</td>
        <td className="px-4 py-3 font-mono text-[10px]" style={{ color: 'var(--t-muted)' }}><div>in: {display(record.input_interface_name ?? record.input_ifindex)}</div><div className="mt-1">out: {display(record.output_interface_name ?? record.output_ifindex)}</div></td>
        <td className="px-4 py-3 font-mono text-[10px] uppercase" style={{ color: 'var(--t-muted)' }}>{record.protocol} v{display(record.source_version)}</td>
      </tr>) : <tr><td colSpan={9} className="px-4 py-8 text-center font-mono text-xs" style={{ color: 'var(--t-muted)' }}>No flow records for these filters</td></tr>}
    </tbody></table></div>
    {(page > 1 || hasNext) && <div className="flex items-center justify-between px-4 py-3" style={{ borderTop: '1px solid var(--t-border-alpha)' }}><span className="font-mono text-xs" style={{ color: 'var(--t-muted)' }}>Page {page}</span><div className="flex gap-2"><button disabled={page <= 1 || isLoading} onClick={() => onPageChange(page - 1)} className="rounded px-3 py-1.5 font-mono text-xs disabled:opacity-40" style={{ border: '1px solid var(--t-border-alpha)', color: 'var(--t-text)' }}>Previous</button><button disabled={!hasNext || isLoading} onClick={() => onPageChange(page + 1)} className="rounded px-3 py-1.5 font-mono text-xs disabled:opacity-40" style={{ border: '1px solid var(--t-border-alpha)', color: 'var(--t-text)' }}>Next</button></div></div>}
  </GlassCard>
}

export default function FlowAnalytics() {
  const { hasPermission } = useAuth()
  const [hours, setHours] = useState(24)
  const [deviceId, setDeviceId] = useState<number | undefined>()
  const [siteId, setSiteId] = useState<number | undefined>()
  const [protocol, setProtocol] = useState<FlowAnalyticsFilters['protocol']>()
  const [recordsPage, setRecordsPage] = useState(1)
  const filters: FlowAnalyticsFilters = { hours, device_id: deviceId, site_id: siteId, protocol, page_size: 10 }
  const recordFilters: FlowAnalyticsFilters = { ...filters, page: recordsPage, page_size: 25 }
  const query = useQuery({
    queryKey: ['flow-analytics', filters],
    queryFn: async () => {
      const [analytics, trends] = await Promise.all([
        Promise.all(dimensions.map(([dimension]) => getFlowAnalytics(dimension, filters))),
        getFlowTrends(filters),
      ])
      return { analytics, trends }
    },
    enabled: hasPermission('flows:read'),
    staleTime: 30_000,
    refetchOnWindowFocus: false,
    refetchOnMount: false,
  })
  const records = useQuery({
    queryKey: ['flow-records', recordFilters],
    queryFn: () => getFlowRecords(recordFilters),
    enabled: hasPermission('flows:read'),
    staleTime: 30_000,
    refetchOnWindowFocus: false,
    refetchOnMount: false,
  })
  const devices = useQuery({ queryKey: ['flow-analytics-devices'], queryFn: () => listDeviceOptions({ limit: 500 }), staleTime: 300_000, enabled: hasPermission('flows:read') })
  const sites = useQuery<SiteRecord[]>({ queryKey: ['flow-analytics-sites'], queryFn: listSites, staleTime: 300_000, enabled: hasPermission('flows:read') })
  const trendPoints = query.data?.trends ?? []
  const totalBytes = trendPoints.reduce((sum, point) => sum + point.bytes, 0)
  const peakBytes = trendPoints.reduce((peak, point) => Math.max(peak, point.bytes), 0)

  if (!hasPermission('flows:read')) return <div className="p-6 font-mono text-sm" style={{ color: 'var(--t-muted)' }}>You do not have permission to view flow analytics.</div>
  if (query.isError) return <div className="p-6 font-mono text-sm" style={{ color: '#ff6688' }}>Unable to load flow analytics. {query.error instanceof Error ? query.error.message : 'Request failed.'}</div>

  return <div className="p-4 md:p-6 space-y-5">
    <div className="flex flex-col lg:flex-row lg:items-end justify-between gap-4">
      <div><h1 className="font-display font-bold text-2xl tracking-widest" style={{ color: 'var(--t-text)' }}>FLOW ANALYTICS</h1><p className="font-mono text-xs mt-1" style={{ color: 'var(--t-muted)' }}>Real exporter data · cached for 30 seconds · no automatic polling</p></div>
      <div className="flex flex-wrap gap-2">
        <select aria-label="Time range" value={hours} onChange={event => { setHours(Number(event.target.value)); setRecordsPage(1) }} className="rounded px-3 py-2 font-mono text-xs" style={{ background: 'var(--t-card)', color: 'var(--t-text)', border: '1px solid var(--t-border-alpha)' }}><option value={1}>Last 1 hour</option><option value={24}>Last 24 hours</option><option value={168}>Last 7 days</option><option value={720}>Last 30 days</option></select>
        <select aria-label="Flow protocol" value={protocol ?? ''} onChange={event => { setProtocol((event.target.value || undefined) as FlowAnalyticsFilters['protocol']); setRecordsPage(1) }} className="rounded px-3 py-2 font-mono text-xs" style={{ background: 'var(--t-card)', color: 'var(--t-text)', border: '1px solid var(--t-border-alpha)' }}><option value="">All flow protocols</option><option value="sflow">sFlow</option><option value="ipfix">IPFIX</option></select>
        <select aria-label="Device filter" value={deviceId ?? ''} onChange={event => { setDeviceId(event.target.value ? Number(event.target.value) : undefined); setRecordsPage(1) }} className="rounded px-3 py-2 font-mono text-xs" style={{ background: 'var(--t-card)', color: 'var(--t-text)', border: '1px solid var(--t-border-alpha)' }}><option value="">All devices</option>{devices.data?.map(device => <option key={device.id} value={device.id}>{device.hostname || device.ip_address}</option>)}</select>
        <select aria-label="Site filter" value={siteId ?? ''} onChange={event => { setSiteId(event.target.value ? Number(event.target.value) : undefined); setRecordsPage(1) }} className="rounded px-3 py-2 font-mono text-xs" style={{ background: 'var(--t-card)', color: 'var(--t-text)', border: '1px solid var(--t-border-alpha)' }}><option value="">All sites</option>{sites.data?.map(site => <option key={site.id} value={site.id}>{site.name}</option>)}</select>
      </div>
    </div>
    <GlassCard>
      <div className="px-4 py-3" style={{ borderBottom: '1px solid var(--t-border-light)' }}><h2 className="font-display font-semibold text-sm" style={{ color: 'var(--t-text)' }}>Traffic Overview</h2></div>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3 p-4">
        {[
          ['Observed bytes', formatBytes(totalBytes)],
          ['Peak bucket', formatBytes(peakBytes)],
          ['Time buckets', trendPoints.length.toLocaleString()],
        ].map(([label, value]) => <div key={label} className="rounded p-3" style={{ background: 'var(--t-bg)', border: '1px solid var(--t-border-alpha)' }}><div className="font-mono text-[10px] uppercase" style={{ color: 'var(--t-muted)' }}>{label}</div><div className="font-display font-semibold text-lg mt-1" style={{ color: 'var(--t-text)' }}>{value}</div></div>)}
      </div>
      <div className="px-4 py-3" style={{ borderTop: '1px solid var(--t-border-light)', borderBottom: '1px solid var(--t-border-light)' }}><h2 className="font-display font-semibold text-sm" style={{ color: 'var(--t-text)' }}>Traffic Trend</h2></div><Trend points={trendPoints} />
    </GlassCard>
    <FlowRecordsTable records={records.data?.items} isLoading={records.isLoading} page={recordsPage} hasNext={(records.data?.items.length ?? 0) === 25} onPageChange={setRecordsPage} />
    <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">{dimensions.map(([dimension, title], index) => <AnalyticsTable key={dimension} title={title} items={query.data?.analytics[index]?.items} />)}</div>
  </div>
}
