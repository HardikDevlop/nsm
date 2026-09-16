import { useEffect, useMemo, useState } from 'react'
import GlassCard from '../components/GlassCard'
import { toast } from '../lib/swal'
import {
  downloadReportManagementCSV,
  getReportManagement,
  getReportManagementOptions,
  type DeviceOptionRecord,
  type DeviceTypeRecord,
  type ReportManagementRecord,
  type ReportManagementSummary,
  type SiteRecord,
} from '../lib/api'

let xlsxModulePromise: Promise<typeof import('xlsx')> | null = null

const PROTOCOLS = [
  { value: 'all', label: 'SNMP + ICMP' },
  { value: 'snmp', label: 'SNMP' },
  { value: 'icmp', label: 'ICMP' },
] as const

const PERIODS = [
  { value: 'weekly', label: 'Weekly' },
  { value: 'monthly', label: 'Monthly' },
  { value: 'yearly', label: 'Yearly' },
  { value: 'custom', label: 'Custom Date Range' },
] as const

function formatDateInput(date: Date) {
  return date.toISOString().slice(0, 10)
}

function useDefaultRange(period: string) {
  const end = new Date()
  const start = new Date()
  if (period === 'monthly') start.setDate(end.getDate() - 30)
  else if (period === 'yearly') start.setDate(end.getDate() - 365)
  else start.setDate(end.getDate() - 7)
  return { start_date: formatDateInput(start), end_date: formatDateInput(end) }
}

function Stat({ label, value, accent }: { label: string; value: string | number; accent?: string }) {
  return (
    <div className="rounded-2xl p-4" style={{ background: 'rgba(0,0,0,0.18)', border: '1px solid rgba(0,212,255,0.14)' }}>
      <div className="font-display text-2xl font-bold" style={{ color: accent ?? 'var(--t-text)' }}>{value}</div>
      <div className="font-mono text-[10px] uppercase tracking-[0.2em] mt-1" style={{ color: 'var(--t-muted)' }}>{label}</div>
    </div>
  )
}

function pickColor(value: string) {
  if (value === 'met' || value === 'healthy') return '#00ff88'
  if (value === 'degraded') return '#ffaa00'
  if (value === 'breached' || value === 'critical') return '#ff3366'
  return '#00d4ff'
}

function toCsv(rows: Record<string, unknown>[]) {
  const keys = rows.length ? Object.keys(rows[0]) : []
  const escape = (v: unknown) => `"${String(v ?? '').replaceAll('"', '""')}"`
  return [keys.join(','), ...rows.map(row => keys.map(key => escape(row[key])).join(','))].join('\n')
}

export default function ReportManagement() {
  const [options, setOptions] = useState<{ device_types: DeviceTypeRecord[]; sites: SiteRecord[]; devices: DeviceOptionRecord[] }>({
    device_types: [],
    sites: [],
    devices: [],
  })
  const [filters, setFilters] = useState(() => ({ protocol: 'all', period: 'weekly', ...useDefaultRange('weekly') }))
  const [summary, setSummary] = useState<ReportManagementSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [exporting, setExporting] = useState<'csv' | 'xlsx' | null>(null)

  const selectedDevices = useMemo(() => {
    return options.devices.filter(device => {
      if (filters.device_type_id && device.device_type_id !== Number(filters.device_type_id)) return false
      if (filters.site_id && device.site_id !== Number(filters.site_id)) return false
      return true
    })
  }, [options.devices, filters.device_type_id, filters.site_id])

  const load = async (nextFilters = filters) => {
    setLoading(true)
    setError(null)
    try {
      const [opts, report] = await Promise.all([
        getReportManagementOptions(),
        getReportManagement(nextFilters),
      ])
      setOptions(opts)
      setSummary(report)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load reports')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void load() }, [])

  const update = (patch: Partial<typeof filters>) => {
    setFilters(prev => ({ ...prev, ...patch }))
  }

  const runReport = () => void load(filters)

  const handleExport = async (format: 'csv' | 'xlsx') => {
    if (!summary || exporting) return
    setExporting(format)
    try {
      if (format === 'csv') {
        const blob = await downloadReportManagementCSV(filters)
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `report-management-${summary.period_start.slice(0, 10)}-${summary.period_end.slice(0, 10)}.csv`
        a.click()
        URL.revokeObjectURL(url)
      } else {
        const XLSX = await (xlsxModulePromise ??= import('xlsx'))
        const wb = XLSX.utils.book_new()
        const sheet = XLSX.utils.json_to_sheet(summary.records.map(r => ({
          Device: r.hostname,
          IP: r.ip_address,
          Site: r.site_name ?? '',
          Type: r.device_type_name ?? '',
          Protocol: r.protocol,
          Availability: r.availability_pct,
          DowntimeSeconds: r.downtime_seconds,
          SNMPHealth: r.snmp_health,
          PerformanceScore: r.performance_score ?? '',
          InterfaceCount: r.interface_count ?? '',
          InterfaceDown: r.interface_down_count ?? '',
          SLAStatus: r.sla_status,
        })))
        XLSX.utils.book_append_sheet(wb, sheet, 'Reports')
        const meta = XLSX.utils.json_to_sheet([
          { Field: 'Period Start', Value: summary.period_start },
          { Field: 'Period End', Value: summary.period_end },
          { Field: 'Total Devices', Value: summary.total_devices },
          { Field: 'Availability %', Value: summary.availability_pct },
          { Field: 'Downtime Seconds', Value: summary.downtime_seconds },
          { Field: 'SLA Met %', Value: summary.sla_met_pct },
        ])
        XLSX.utils.book_append_sheet(wb, meta, 'Summary')
        XLSX.writeFile(wb, `report-management-${summary.period_start.slice(0, 10)}-${summary.period_end.slice(0, 10)}.xlsx`)
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Export failed')
    } finally {
      setExporting(null)
    }
  }

  const activeSummary = summary ?? null

  if (loading && !summary) {
    return <div className="p-6 min-h-[50vh] flex items-center justify-center text-sm font-mono" style={{ color: 'var(--t-muted)' }}>Loading report module…</div>
  }

  if (error && !summary) {
    return <div className="p-6 text-sm font-mono" style={{ color: '#ff3366' }}>{error}</div>
  }

  return (
    <div className="p-4 md:p-6 space-y-5">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold" style={{ color: 'var(--t-text)' }}>Report Management</h1>
          <p className="font-mono text-xs mt-1" style={{ color: 'var(--t-muted)' }}>Real SNMP + ICMP data only. Filters drive both UI and exports.</p>
        </div>
        <div className="flex gap-2">
          <button onClick={() => void handleExport('csv')} className="rounded-lg px-4 py-2 text-sm font-semibold" style={{ background: 'rgba(0,212,255,0.14)', color: '#00d4ff', border: '1px solid rgba(0,212,255,0.25)' }}>
            {exporting === 'csv' ? 'Exporting…' : 'CSV'}
          </button>
          <button onClick={() => void handleExport('xlsx')} className="rounded-lg px-4 py-2 text-sm font-semibold" style={{ background: 'var(--t-accent)', color: '#fff', border: '1px solid var(--t-accent-border)' }}>
            {exporting === 'xlsx' ? 'Exporting…' : 'Excel'}
          </button>
          <button onClick={runReport} className="rounded-lg px-4 py-2 text-sm font-semibold" style={{ background: 'rgba(255,255,255,0.04)', color: 'var(--t-text)', border: '1px solid var(--t-border-alpha)' }}>Run Report</button>
        </div>
      </div>

      <GlassCard className="p-4">
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          <label className="text-xs font-mono" style={{ color: 'var(--t-muted)' }}>
            Device Type
            <select className="mt-1 w-full rounded-lg px-3 py-2" value={filters.device_type_id ?? ''} onChange={e => update({ device_type_id: e.target.value ? Number(e.target.value) : null })}>
              <option value="">All</option>
              {options.device_types.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
            </select>
          </label>
          <label className="text-xs font-mono" style={{ color: 'var(--t-muted)' }}>
            Device
            <select className="mt-1 w-full rounded-lg px-3 py-2" value={filters.device_id ?? ''} onChange={e => update({ device_id: e.target.value ? Number(e.target.value) : null })}>
              <option value="">All</option>
              {selectedDevices.map(item => <option key={item.id} value={item.id}>{item.hostname} ({item.ip_address})</option>)}
            </select>
          </label>
          <label className="text-xs font-mono" style={{ color: 'var(--t-muted)' }}>
            Site
            <select className="mt-1 w-full rounded-lg px-3 py-2" value={filters.site_id ?? ''} onChange={e => update({ site_id: e.target.value ? Number(e.target.value) : null })}>
              <option value="">All</option>
              {options.sites.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
            </select>
          </label>
          <label className="text-xs font-mono" style={{ color: 'var(--t-muted)' }}>
            SNMP/ICMP
            <select className="mt-1 w-full rounded-lg px-3 py-2" value={filters.protocol} onChange={e => update({ protocol: e.target.value as typeof filters.protocol })}>
              {PROTOCOLS.map(item => <option key={item.value} value={item.value}>{item.label}</option>)}
            </select>
          </label>
          <label className="text-xs font-mono" style={{ color: 'var(--t-muted)' }}>
            Period
            <select className="mt-1 w-full rounded-lg px-3 py-2" value={filters.period} onChange={e => update({ period: e.target.value as typeof filters.period, ...(e.target.value === 'custom' ? {} : useDefaultRange(e.target.value)) })}>
              {PERIODS.map(item => <option key={item.value} value={item.value}>{item.label}</option>)}
            </select>
          </label>
          <label className="text-xs font-mono" style={{ color: 'var(--t-muted)' }}>
            Start Date
            <input className="mt-1 w-full rounded-lg px-3 py-2" type="date" value={filters.start_date ?? ''} onChange={e => update({ start_date: e.target.value })} disabled={filters.period !== 'custom'} />
          </label>
          <label className="text-xs font-mono" style={{ color: 'var(--t-muted)' }}>
            End Date
            <input className="mt-1 w-full rounded-lg px-3 py-2" type="date" value={filters.end_date ?? ''} onChange={e => update({ end_date: e.target.value })} disabled={filters.period !== 'custom'} />
          </label>
        </div>
      </GlassCard>

      {activeSummary && (
        <>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <Stat label="Availability" value={`${activeSummary.availability_pct.toFixed(2)}%`} accent={pickColor(activeSummary.availability_pct >= 99 ? 'met' : 'breached')} />
            <Stat label="Downtime Seconds" value={activeSummary.downtime_seconds.toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', hour12: true })} accent="#ff6644" />
            <Stat label="SNMP Health" value={activeSummary.avg_snmp_health?.toFixed(2) ?? 'N/A'} accent={pickColor(activeSummary.avg_snmp_health && activeSummary.avg_snmp_health >= 85 ? 'healthy' : activeSummary.avg_snmp_health && activeSummary.avg_snmp_health >= 60 ? 'degraded' : 'critical')} />
            <Stat label="SLA Met %" value={`${activeSummary.sla_met_pct.toFixed(2)}%`} accent={pickColor(activeSummary.sla_met_pct >= 99 ? 'met' : 'critical')} />
          </div>

          <div className="grid gap-3 lg:grid-cols-3">
            {Object.entries(activeSummary.sections).map(([key, section]) => (
              <GlassCard key={key} className="p-4">
                <div className="font-display font-semibold text-base">{section.title}</div>
                <div className="mt-2 text-2xl font-bold" style={{ color: pickColor(key === 'sla' ? (section.average ?? 0) >= 99 ? 'met' : 'critical' : key === 'snmp_health' ? (section.average ?? 0) >= 85 ? 'healthy' : 'degraded' : 'info') }}>
                  {section.average != null ? section.average.toFixed(2) : section.count}
                </div>
                <div className="font-mono text-[10px] mt-1" style={{ color: 'var(--t-muted)' }}>Records: {section.count}</div>
              </GlassCard>
            ))}
          </div>

          <GlassCard className="overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-left" style={{ minWidth: 1200 }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--t-border-light)' }}>
                    {['Device', 'Site', 'Type', 'Protocol', 'Avail %', 'Downtime', 'SNMP', 'Perf', 'Interfaces', 'SLA'].map(col => (
                      <th key={col} className="px-4 py-3 font-mono text-[10px] uppercase tracking-[0.2em]" style={{ color: 'var(--t-muted)' }}>{col}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {activeSummary.records.map(row => (
                    <tr key={row.device_id} style={{ borderBottom: '1px solid var(--t-border-alpha)' }}>
                      <td className="px-4 py-3">
                        <div className="font-semibold">{row.hostname}</div>
                        <div className="font-mono text-[10px]" style={{ color: 'var(--t-muted)' }}>{row.ip_address}</div>
                      </td>
                      <td className="px-4 py-3">{row.site_name ?? 'N/A'}</td>
                      <td className="px-4 py-3">{row.device_type_name ?? 'N/A'}</td>
                      <td className="px-4 py-3">{row.protocol}</td>
                      <td className="px-4 py-3" style={{ color: pickColor(row.availability_pct >= 99 ? 'met' : 'critical') }}>{row.availability_pct.toFixed(2)}%</td>
                      <td className="px-4 py-3">{row.downtime_seconds.toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', hour12: true })}s</td>
                      <td className="px-4 py-3" style={{ color: pickColor(row.snmp_health) }}>{row.snmp_health}{row.snmp_success_rate != null ? ` (${row.snmp_success_rate.toFixed(1)}%)` : ''}</td>
                      <td className="px-4 py-3">{row.performance_score != null ? row.performance_score.toFixed(2) : 'N/A'}</td>
                      <td className="px-4 py-3">{row.interface_count ?? 0}{row.interface_down_count ? ` / down ${row.interface_down_count}` : ''}</td>
                      <td className="px-4 py-3" style={{ color: pickColor(row.sla_status) }}>{row.sla_status}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </GlassCard>
        </>
      )}
    </div>
  )
}
