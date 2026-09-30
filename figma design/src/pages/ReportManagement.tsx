import { useEffect, useMemo, useState, type ReactNode } from 'react'
import GlassCard from '../components/GlassCard'
import { exportReportManagementPdf } from '../lib/reportPdf'
import { ResponsiveContainer, LineChart, Line, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid, Legend } from 'recharts'
import { toast } from '../lib/swal'
import {
  getReportManagement,
  getReportManagementEmailSchedule,
  getReportManagementOptions,
  getReportSchedules, createReportSchedule, updateReportSchedule, deleteReportSchedule, getGeneratedReports, downloadGeneratedReport,
  type ReportSchedule, type GeneratedReport,
  type DeviceOptionRecord,
  type DeviceTypeRecord,
  type ReportEmailScheduleStatus,
  type ReportManagementSummary,
  type ReportManagementRecord,
  type SiteRecord,
} from '../lib/api'

let xlsxModulePromise: Promise<typeof import('xlsx')> | null = null

const PROTOCOLS = [
  { value: 'all', label: 'SNMP + ICMP' },
  { value: 'snmp', label: 'SNMP' },
  { value: 'icmp', label: 'ICMP' },
] as const

const PERIODS = [
  { value: 'today', label: 'Today' },
  { value: 'yesterday', label: 'Yesterday' },
  { value: 'weekly', label: 'Weekly' },
  { value: 'monthly', label: 'Monthly' },
  { value: 'yearly', label: 'Yearly' },
  { value: 'custom', label: 'Custom' },
] as const

type Filters = {
  protocol: (typeof PROTOCOLS)[number]['value']
  period: (typeof PERIODS)[number]['value']
  start_date: string
  end_date: string
  device_type_id?: number | null
  device_id?: number | null
  site_id?: number | null
  device_status: "all" | "up" | "down" | "unreachable"
  alert_severity: "all" | "critical" | "high" | "medium" | "low" | "warning" | "info"
}

/* ---------- palette & helpers ---------- */

const C = {
  good: '#22c55e',
  warn: '#f59e0b',
  bad: '#f43f5e',
  info: '#38bdf8',
  neutral: '#94a3b8',
}

const tint = (hex: string, a: number) => {
  const n = parseInt(hex.slice(1), 16)
  return `rgba(${n >> 16}, ${(n >> 8) & 255}, ${n & 255}, ${a})`
}

function formatDateInput(date: Date) {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function spreadsheetSafe(value: unknown) {
  if (typeof value !== 'string') return value
  return /^[=+\-@]/.test(value.trimStart()) ? `'${value}` : value
}

function formatDuration(seconds: number | null | undefined) {
  const total = Math.max(0, Math.round(Number(seconds) || 0))
  const d = Math.floor(total / 86400)
  const h = Math.floor((total % 86400) / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  if (d > 0) return `${d}d ${h}h ${m}m`
  if (h > 0) return `${h}h ${m}m ${s}s`
  return `${m}m ${s}s`
}

function getDefaultRange(period: string) {
  const end = new Date()
  const start = new Date()
  if (period === 'today') start.setDate(end.getDate())
  else if (period === 'yesterday') {
    start.setDate(end.getDate() - 1)
    end.setDate(end.getDate() - 1)
  } else if (period === 'monthly') start.setDate(end.getDate() - 30)
  else if (period === 'yearly') start.setDate(end.getDate() - 365)
  else start.setDate(end.getDate() - 7)
  return { start_date: formatDateInput(start), end_date: formatDateInput(end) }
}

const availabilityTone = (pct: number | null) => pct == null ? C.neutral : pct >= 99 ? C.good : pct >= 95 ? C.warn : C.bad
const healthTone = (v: string) => (v === 'healthy' ? C.good : v === 'degraded' ? C.warn : v === 'critical' || v === 'down' ? C.bad : C.neutral)
const slaTone = (v: string) => (v === 'met' ? C.good : v === 'degraded' ? C.warn : v === 'breached' || v === 'critical' ? C.bad : C.neutral)

/* ---------- icons ---------- */

type IconProps = { className?: string }
const svgProps = {
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.8,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
}

const IconDownload = ({ className = 'h-4 w-4' }: IconProps) => (
  <svg {...svgProps} className={className}><path d="M12 3v12m0 0l-4-4m4 4l4-4M4 20h16" /></svg>
)
const IconSearch = ({ className = 'h-4 w-4' }: IconProps) => (
  <svg {...svgProps} className={className}><circle cx="11" cy="11" r="7" /><path d="M20 20l-3.5-3.5" /></svg>
)
const IconServer = ({ className = 'h-4 w-4' }: IconProps) => (
  <svg {...svgProps} className={className}><rect x="3" y="4" width="18" height="7" rx="2" /><rect x="3" y="13" width="18" height="7" rx="2" /><path d="M7 7.5h.01M7 16.5h.01" /></svg>
)
const IconPulse = ({ className = 'h-4 w-4' }: IconProps) => (
  <svg {...svgProps} className={className}><path d="M3 12h4l3-8 4 16 3-8h4" /></svg>
)
const IconClock = ({ className = 'h-4 w-4' }: IconProps) => (
  <svg {...svgProps} className={className}><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></svg>
)
const IconShield = ({ className = 'h-4 w-4' }: IconProps) => (
  <svg {...svgProps} className={className}><path d="M12 3l8 3v6c0 4.5-3.2 8-8 9-4.8-1-8-4.5-8-9V6l8-3z" /><path d="M9 12l2 2 4-4" /></svg>
)
const IconHeart = ({ className = 'h-4 w-4' }: IconProps) => (
  <svg {...svgProps} className={className}><path d="M20.8 5.6a5 5 0 00-7.1 0L12 7.3l-1.7-1.7a5 5 0 00-7.1 7.1L12 21l8.8-8.3a5 5 0 000-7.1z" /></svg>
)
const IconMail = ({ className = 'h-4 w-4' }: IconProps) => (
  <svg {...svgProps} className={className}><rect x="3" y="5" width="18" height="14" rx="2" /><path d="M3 7l9 6 9-6" /></svg>
)
const IconInbox = ({ className = 'h-4 w-4' }: IconProps) => (
  <svg {...svgProps} className={className}><path d="M3 13l3-8h12l3 8v6a1 1 0 01-1 1H4a1 1 0 01-1-1v-6z" /><path d="M3 13h5l1 3h6l1-3h5" /></svg>
)
const IconReport = ({ className = 'h-4 w-4' }: IconProps) => (
  <svg {...svgProps} className={className}><path d="M6 3h9l4 4v14H6z" /><path d="M14 3v5h5M9 13h6M9 17h6" /></svg>
)
const IconCalendar = ({ className = 'h-4 w-4' }: IconProps) => (
  <svg {...svgProps} className={className}><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M3 10h18M8 3v4M16 3v4" /></svg>
)

/* ---------- small UI parts ---------- */

const controlStyle: React.CSSProperties = {
  background: 'rgba(0,0,0,0.22)',
  border: '1px solid var(--t-border-alpha)',
  color: 'var(--t-text)',
  outline: 'none',
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-[11px] font-medium uppercase tracking-wider" style={{ color: 'var(--t-muted)' }}>{label}</span>
      {children}
    </label>
  )
}

function Select(props: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return <select {...props} className="h-9 w-full rounded-lg px-2.5 text-[13px] transition hover:border-white/20 focus:ring-2 focus:ring-sky-400/30" style={controlStyle} />
}

function DateInput(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      type="date"
      className="h-9 w-full rounded-lg px-2.5 text-[13px] transition hover:border-white/20 focus:ring-2 focus:ring-sky-400/30 disabled:cursor-not-allowed disabled:opacity-40"
      style={controlStyle}
    />
  )
}

function Segmented<T extends string>({ value, options, onChange }: { value: T; options: readonly { value: T; label: string }[]; onChange: (v: T) => void }) {
  return (
    <div className="inline-flex flex-wrap gap-0.5 rounded-lg p-0.5" style={{ background: 'rgba(0,0,0,0.25)', border: '1px solid var(--t-border-alpha)' }}>
      {options.map(o => {
        const active = o.value === value
        return (
          <button
            key={o.value}
            type="button"
            onClick={() => onChange(o.value)}
            className="rounded-md px-3 py-1.5 text-[12.5px] font-medium transition hover:text-white focus-visible:ring-2 focus-visible:ring-sky-400/40"
            style={{
              background: active ? 'var(--t-accent)' : 'transparent',
              color: active ? '#fff' : 'var(--t-muted)',
              boxShadow: active ? '0 1px 6px rgba(14,165,233,0.25)' : 'none',
            }}
          >
            {o.label}
          </button>
        )
      })}
    </div>
  )
}

function Pill({ text, color }: { text: string; color: string }) {
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[11px] font-medium capitalize"
      style={{ background: tint(color, 0.12), color, border: `1px solid ${tint(color, 0.25)}` }}
    >
      <span className="h-1.5 w-1.5 rounded-full" style={{ background: color }} />
      {text}
    </span>
  )
}

function Kpi({ label, value, hint, color, icon }: { label: string; value: string | number; hint?: string; color: string; icon: ReactNode }) {
  return (
    <div
      className="relative overflow-hidden rounded-xl p-4"
      style={{
        background: `linear-gradient(135deg, ${tint(color, 0.08)} 0%, rgba(255,255,255,0.02) 60%)`,
        border: '1px solid var(--t-border-alpha)',
      }}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="text-[11px] font-medium uppercase tracking-wider" style={{ color: 'var(--t-muted)' }}>{label}</div>
        <span className="flex h-8 w-8 items-center justify-center rounded-lg" style={{ background: tint(color, 0.14), color }}>{icon}</span>
      </div>
      <div className="mt-2 text-[26px] font-semibold leading-none tracking-tight tabular-nums" style={{ color: 'var(--t-text)' }}>{value}</div>
      {hint && <div className="mt-2 text-[11px]" style={{ color }}>{hint}</div>}
    </div>
  )
}

function Bar({ pct, color }: { pct: number; color: string }) {
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full" style={{ background: 'rgba(255,255,255,0.08)' }}>
      <div className="h-full rounded-full transition-all duration-500" style={{ width: `${Math.max(0, Math.min(100, pct))}%`, background: color }} />
    </div>
  )
}

/* circular gauge used on the section cards */
function Ring({ pct, color, size = 64 }: { pct: number; color: string; size?: number }) {
  const stroke = 6
  const r = (size - stroke) / 2
  const circ = 2 * Math.PI * r
  const clamped = Math.max(0, Math.min(100, pct))
  return (
    <div className="relative shrink-0" style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth={stroke} />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={color}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={circ}
          strokeDashoffset={circ * (1 - clamped / 100)}
          style={{ transition: 'stroke-dashoffset 600ms ease', filter: `drop-shadow(0 0 4px ${tint(color, 0.45)})` }}
        />
      </svg>
      <span className="absolute inset-0 flex items-center justify-center text-[12px] font-semibold tabular-nums" style={{ color: 'var(--t-text)' }}>
        {Math.round(clamped)}%
      </span>
    </div>
  )
}

function ExportButton({ children, onClick, busy, variant }: { children: ReactNode; onClick: () => void; busy: boolean; variant: 'ghost' | 'solid' }) {
  const solid = variant === 'solid'
  return (
    <button
      onClick={onClick}
      disabled={busy}
      className="inline-flex h-9 items-center gap-1.5 rounded-lg px-3.5 text-[13px] font-medium transition hover:brightness-110 focus-visible:ring-2 focus-visible:ring-sky-400/40 disabled:opacity-50"
      style={{
        background: solid ? 'var(--t-accent)' : 'rgba(255,255,255,0.04)',
        color: solid ? '#fff' : 'var(--t-text)',
        border: `1px solid ${solid ? 'var(--t-accent-border)' : 'var(--t-border-alpha)'}`,
        boxShadow: solid ? '0 2px 10px rgba(14,165,233,0.22)' : 'none',
      }}
    >
      {children}
    </button>
  )
}

function Skeleton() {
  return (
    <div className="w-full space-y-5 p-4 md:p-6" aria-busy="true">
      <div className="h-8 w-56 animate-pulse rounded-md" style={{ background: 'rgba(255,255,255,0.06)' }} />
      <div className="h-32 animate-pulse rounded-xl" style={{ background: 'rgba(255,255,255,0.04)' }} />
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {[0, 1, 2, 3].map(i => (
          <div key={i} className="h-28 animate-pulse rounded-xl" style={{ background: 'rgba(255,255,255,0.04)' }} />
        ))}
      </div>
      <div className="h-72 animate-pulse rounded-xl" style={{ background: 'rgba(255,255,255,0.04)' }} />
    </div>
  )
}

const SECTION_ICONS: Record<string, ReactNode> = {
  availability: <IconPulse />,
  downtime: <IconClock />,
  sla: <IconShield />,
  snmp_health: <IconHeart />,
}

function trendLabel(value: string, granularity: 'hourly' | 'daily' | 'monthly') {
  const date = new Date(value)
  if (granularity === 'hourly') return date.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: false })
  if (granularity === 'daily') return date.toLocaleDateString('en-IN', { month: 'short', day: 'numeric' })
  return date.toLocaleDateString('en-IN', { month: 'short', year: 'numeric' })
}
const trendTooltip = { contentStyle: { background: 'var(--t-bg)', border: '1px solid var(--t-border-alpha)', borderRadius: 8, color: 'var(--t-text)' }, labelStyle: { color: 'var(--t-muted)' } }
function TrendCard({ title, children, empty }: { title: string; children: ReactNode; empty: boolean }) {
  return <GlassCard className="min-w-0 p-4"><div className="mb-3 text-[13px] font-semibold" style={{ color: 'var(--t-text)' }}>{title}</div>{empty ? <div className="flex h-52 items-center justify-center text-[12px]" style={{ color: 'var(--t-muted)' }}>No historical data available</div> : <div className="h-52 w-full">{children}</div>}</GlassCard>
}

/* ---------- page ---------- */

export default function ReportManagement() {
  const [options, setOptions] = useState<{ device_types: DeviceTypeRecord[]; sites: SiteRecord[]; devices: DeviceOptionRecord[] }>({
    device_types: [],
    sites: [],
    devices: [],
  })
  const [filters, setFilters] = useState<Filters>(() => ({ protocol: 'all', period: 'today', device_status: 'all', alert_severity: 'all', ...getDefaultRange('today') }))
  const [summary, setSummary] = useState<ReportManagementSummary | null>(null)
  const [emailSchedule, setEmailSchedule] = useState<ReportEmailScheduleStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [exporting, setExporting] = useState<'csv' | 'xlsx' | 'pdf' | null>(null)
  const [query, setQuery] = useState('')
  const [selectedRecord, setSelectedRecord] = useState<ReportManagementRecord | null>(null)
  const [scheduleView, setScheduleView] = useState(false)
  const [schedules, setSchedules] = useState<ReportSchedule[]>([])
  const [generatedReports, setGeneratedReports] = useState<GeneratedReport[]>([])
  const [scheduleLoading, setScheduleLoading] = useState(false)
  const [scheduleError, setScheduleError] = useState<string | null>(null)
  const [scheduleEditor, setScheduleEditor] = useState<ReportSchedule | null | false>(false)
  const [scheduleForm, setScheduleForm] = useState({ name: '', frequency: 'daily' as ReportSchedule['frequency'], run_time: '09:00', enabled: false, report_format: 'csv' as const, site_id: null as number | null, device_id: null as number | null, device_type_id: null as number | null, device_status: 'all' as Filters['device_status'], protocol: 'all' as Filters['protocol'], alert_severity: 'all' as Filters['alert_severity'] })

  const selectedDevices = useMemo(
    () =>
      options.devices.filter(device => {
        if (filters.device_type_id && device.device_type_id !== Number(filters.device_type_id)) return false
        if (filters.site_id && device.site_id !== Number(filters.site_id)) return false
        return true
      }),
    [options.devices, filters.device_type_id, filters.site_id],
  )

  const visibleRecords = useMemo(() => {
    const records = summary?.records ?? []
    const q = query.trim().toLowerCase()
    if (!q) return records
    return records.filter(r =>
      [r.hostname, r.ip_address, r.site_name, r.device_type_name].some(v => (v ?? '').toString().toLowerCase().includes(q)),
    )
  }, [summary, query])

  const loadSchedules = async () => {
    setScheduleLoading(true); setScheduleError(null)
    try { const [items, history] = await Promise.all([getReportSchedules(), getGeneratedReports()]); setSchedules(items); setGeneratedReports(history) }
    catch (err) { setScheduleError(err instanceof Error ? err.message : 'Failed to load scheduled reports') }
    finally { setScheduleLoading(false) }
  }
  const openSchedules = () => { setScheduleView(true); if (!schedules.length && !generatedReports.length) void loadSchedules() }
  const openScheduleEditor = (item?: ReportSchedule) => {
    setScheduleEditor(item ?? null)
    setScheduleForm({ name: item?.name ?? '', frequency: item?.frequency ?? 'daily', run_time: item?.run_time ?? '09:00', enabled: item?.enabled ?? false, report_format: 'csv', site_id: item?.filters?.site_id ?? null, device_id: item?.filters?.device_id ?? null, device_type_id: item?.filters?.device_type_id ?? null, device_status: item?.filters?.device_status ?? 'all', protocol: item?.filters?.protocol ?? 'all', alert_severity: item?.filters?.alert_severity ?? 'all' })
  }
  const saveSchedule = async () => {
    try {
      const payload = { name: scheduleForm.name.trim(), enabled: scheduleForm.enabled, frequency: scheduleForm.frequency, run_time: scheduleForm.run_time, report_format: 'csv' as const, filters: { site_id: scheduleForm.site_id, device_id: scheduleForm.device_id, device_type_id: scheduleForm.device_type_id, device_status: scheduleForm.device_status, protocol: scheduleForm.protocol, alert_severity: scheduleForm.alert_severity } }
      if (!payload.name) throw new Error('Schedule name is required')
      if (scheduleEditor) await updateReportSchedule(scheduleEditor.id, payload); else await createReportSchedule(payload)
      setScheduleEditor(false); await loadSchedules(); toast.success('Schedule saved')
    } catch (err) { toast.error(err instanceof Error ? err.message : 'Could not save schedule') }
  }
  const toggleSchedule = async (item: ReportSchedule) => { try { await updateReportSchedule(item.id, { enabled: !item.enabled }); await loadSchedules() } catch (err) { toast.error(err instanceof Error ? err.message : 'Could not update schedule') } }
  const removeSchedule = async (item: ReportSchedule) => { if (!window.confirm('Delete this schedule? Generated report history will be preserved.')) return; try { await deleteReportSchedule(item.id); await loadSchedules(); toast.success('Schedule deleted') } catch (err) { toast.error(err instanceof Error ? err.message : 'Could not delete schedule') } }
  const downloadGenerated = async (item: GeneratedReport) => { try { const result = await downloadGeneratedReport(item.id); const url = URL.createObjectURL(result.blob); const anchor = document.createElement('a'); anchor.href = url; anchor.download = result.filename; anchor.click(); URL.revokeObjectURL(url) } catch (err) { toast.error(err instanceof Error ? err.message : 'Download failed') } }

  const load = async (nextFilters = filters) => {
    setLoading(true)
    setError(null)
    try {
      const [opts, report] = await Promise.all([getReportManagementOptions(), getReportManagement(nextFilters)])
      setOptions(opts)
      setSummary(report)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load reports')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
    void getReportManagementEmailSchedule().then(setEmailSchedule).catch(() => setEmailSchedule(null))
  }, [])

  const update = (patch: Partial<Filters>) => setFilters(prev => ({ ...prev, ...patch }))
  const runReport = () => void load(filters)

 const handleExport = async (format: 'csv' | 'xlsx' | 'pdf') => {
  if (!summary || exporting) return

  setExporting(format)

  try {
    const stamp = `${summary.period_start.slice(0, 10)}_to_${summary.period_end.slice(0, 10)}`

    const displayDate = (value?: string | null) =>
      value ? new Date(value).toLocaleString('en-IN') : ''

    // --------------------------------------------------
    // SAFE FLAT EXPORT DATA
    // --------------------------------------------------

    const flatRows = summary.records
      .map((r) => ({
        'Device Name': r.hostname ?? '',

        Hostname:
          r.inventory?.hostname ??
          r.hostname ??
          '',

        'IP Address':
          r.inventory?.ip_address ??
          r.ip_address ??
          '',

        'MAC Address':
          r.inventory?.mac_address ??
          '',

        Site:
          r.inventory?.site ??
          r.site_name ??
          '',

        'Device Type':
          r.inventory?.device_type ??
          r.device_type_name ??
          '',

        Vendor:
          r.inventory?.vendor ??
          '',

        Model:
          r.inventory?.model ??
          '',

        'Serial Number':
          r.inventory?.serial_number ??
          '',

        'OS Version':
          r.inventory?.os_version ??
          '',

        'Firmware Version':
          r.inventory?.firmware_version ??
          '',

        'SNMP Version':
          r.inventory?.snmp_version ??
          '',

        'Current Status':
          r.current_status ?? '',

        'First Discovered':
          displayDate(r.inventory?.first_discovered_at),

        'Last Seen':
          displayDate(r.inventory?.last_seen_at),

        'Availability %':
          r.availability_pct ?? '',

        'Total Downtime':
          r.downtime_seconds != null
            ? formatDuration(r.downtime_seconds)
            : '',

        'Outage Count':
          r.outage_count ?? 0,

        'Longest Outage':
          r.longest_outage_seconds != null
            ? formatDuration(r.longest_outage_seconds)
            : '',

        'Last Outage':
          displayDate(r.last_outage_time),

        'Last Recovery':
          displayDate(r.last_recovery_time),

        'CPU Avg %':
          r.avg_cpu_percent ?? '',

        'CPU Max %':
          r.max_cpu_percent ?? '',

        'CPU P95 %':
          r.p95_cpu_percent ?? '',

        'Memory Avg %':
          r.avg_memory_percent ?? '',

        'Memory Max %':
          r.max_memory_percent ?? '',

        'Memory P95 %':
          r.p95_memory_percent ?? '',

        'Latency Avg ms':
          r.avg_latency_ms ?? '',

        'Latency Max ms':
          r.max_latency_ms ?? '',

        'Latency P95 ms':
          r.p95_latency_ms ?? '',

        'Packet Loss Avg %':
          r.avg_packet_loss_pct ?? '',

        'Packet Loss Max %':
          r.max_packet_loss_pct ?? '',

        'Total Interfaces':
          r.interface_count ?? '',

        'Down Interfaces':
          r.interface_down_count ?? '',

        'Total Alerts':
          r.alert_count ?? 0,

        'Critical Alerts':
          r.critical_alert_count ?? 0,

        'Warning Alerts':
          r.warning_alert_count ?? 0,

        'Active Alerts':
          r.active_alert_count ?? 0,

        'Resolved Alerts':
          r.resolved_alert_count ?? 0,

        'SLA Target %':
          r.sla_target_percent ?? '',

        'Actual Availability %':
          r.availability_pct ?? '',

        'SLA Variance %':
          r.sla_variance_percent ?? '',

        'Allowed Downtime':
          r.allowed_downtime_seconds != null
            ? formatDuration(r.allowed_downtime_seconds)
            : '',

        'SLA Breach Duration':
          r.sla_breach_seconds != null
            ? formatDuration(r.sla_breach_seconds)
            : '',

        'SLA Status':
          r.sla_status ?? '',
      }))
      .map((row) =>
        Object.fromEntries(
          Object.entries(row).map(([key, value]) => [
            key,
            spreadsheetSafe(value),
          ]),
        ),
      )

    // --------------------------------------------------
    // PDF
    // --------------------------------------------------

    if (format === 'pdf') {
      exportReportManagementPdf(summary, filters)
      return
    }

    // --------------------------------------------------
    // CSV
    // --------------------------------------------------

    if (format === 'csv') {
      const headers = Object.keys(
        flatRows[0] ?? {
          'Device Name': '',
        },
      )

      const escapeCsv = (value: unknown) => {
        const text = value == null ? '' : String(value)

        return /[",\n]/.test(text)
          ? `"${text.replaceAll('"', '""')}"`
          : text
      }

      const csv = [
        headers,
        ...flatRows.map((row) =>
          headers.map((header) =>
            escapeCsv(row[header as keyof typeof row]),
          ),
        ),
      ]
        .map((row) => row.join(','))
        .join('\r\n')

      const blob = new Blob(
        [`\uFEFF${csv}`],
        {
          type: 'text/csv;charset=utf-8',
        },
      )

      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')

      a.href = url
      a.download = `NMS_Report_${stamp}.csv`

      document.body.appendChild(a)
      a.click()
      a.remove()

      URL.revokeObjectURL(url)

      return
    }

    // --------------------------------------------------
    // EXCEL
    // --------------------------------------------------

    const xlsxModule =
      await (xlsxModulePromise ??= import('xlsx'))

    // Handles both ESM and default-export builds of xlsx.
    const XLSX = (
      (xlsxModule as any).default ??
      xlsxModule
    ) as typeof import('xlsx')

    if (
      !XLSX?.utils?.book_new ||
      !XLSX?.utils?.json_to_sheet ||
      !XLSX?.utils?.book_append_sheet ||
      !XLSX?.writeFile
    ) {
      throw new Error('Excel export library failed to load')
    }

    const wb = XLSX.utils.book_new()

    // -------------------------
    // Devices sheet
    // -------------------------

    const devicesSheet =
      XLSX.utils.json_to_sheet(flatRows)

    devicesSheet['!freeze'] = {
      xSplit: 0,
      ySplit: 1,
    }

    devicesSheet['!autofilter'] = {
      ref: devicesSheet['!ref'] ?? 'A1:A1',
    }

    devicesSheet['!cols'] =
      Object.keys(flatRows[0] ?? {}).map(() => ({
        wch: 18,
      }))

    XLSX.utils.book_append_sheet(
      wb,
      devicesSheet,
      'Devices',
    )

    // -------------------------
    // Summary sheet
    // -------------------------

    const summaryRows = [
      {
        Field: 'Report Period',
        Value: `${summary.period_start} to ${summary.period_end}`,
      },
      {
        Field: 'Generated At',
        Value: new Date().toLocaleString('en-IN'),
      },
      {
        Field: 'Applied Site',
        Value: filters.site_id ?? 'All',
      },
      {
        Field: 'Applied Device Type',
        Value: filters.device_type_id ?? 'All',
      },
      {
        Field: 'Applied Protocol',
        Value: filters.protocol ?? 'All',
      },
      {
        Field: 'Applied Status',
        Value: filters.device_status ?? 'All',
      },
      {
        Field: 'Total Devices',
        Value: summary.total_devices ?? 0,
      },
      {
        Field: 'Up Devices',
        Value: summary.up_devices ?? 0,
      },
      {
        Field: 'Down Devices',
        Value: summary.down_devices ?? 0,
      },
      {
        Field: 'Unreachable Devices',
        Value: summary.unreachable_devices ?? 0,
      },
      {
        Field: 'Average Availability',
        Value: summary.availability_pct ?? '',
      },
      {
        Field: 'Total Alerts',
        Value: summary.total_alerts ?? 0,
      },
      {
        Field: 'Critical Alerts',
        Value: summary.critical_alerts ?? 0,
      },
      {
        Field: 'Alert MTTR',
        Value:
          summary.alert_mttr_seconds != null
            ? formatDuration(summary.alert_mttr_seconds)
            : '',
      },
      {
        Field: 'SLA Met',
        Value: summary.sla_met_devices ?? 0,
      },
      {
        Field: 'SLA Breached',
        Value: summary.sla_breached_devices ?? 0,
      },
      {
        Field: 'SLA Unknown',
        Value: summary.sla_unknown_devices ?? 0,
      },
      {
        Field: 'Inventory Assets',
        Value: summary.inventory_total_assets ?? 0,
      },
    ].map((row) => ({
      ...row,
      Value: spreadsheetSafe(row.Value),
    }))

    const summarySheet =
      XLSX.utils.json_to_sheet(summaryRows)

    summarySheet['!cols'] = [
      { wch: 28 },
      { wch: 30 },
    ]

    XLSX.utils.book_append_sheet(
      wb,
      summarySheet,
      'Summary',
    )

    XLSX.writeFile(
      wb,
      `NMS_Report_${stamp}.xlsx`,
    )
  } catch (err) {
    console.error('Report export failed:', err)

    toast.error(
      err instanceof Error
        ? err.message
        : 'Export failed',
    )
  } finally {
    setExporting(null)
  }
}

  if (loading && !summary) return <Skeleton />

  if (error && !summary) {
    return (
      <div className="p-6">
        <div className="mx-auto max-w-md rounded-xl p-5 text-[13px]" style={{ background: tint(C.bad, 0.08), border: `1px solid ${tint(C.bad, 0.3)}`, color: C.bad }}>
          <div className="text-[14px] font-semibold">Couldn't load the report</div>
          <p className="mt-1 opacity-90">{error}</p>
          <button onClick={runReport} className="mt-3 rounded-lg px-3.5 py-1.5 text-[13px] font-medium transition hover:brightness-125" style={{ background: tint(C.bad, 0.18) }}>Try again</button>
        </div>
      </div>
    )
  }

  const s = summary
  const snmp = s?.avg_snmp_health
  const snmpColor = snmp == null ? C.neutral : snmp >= 85 ? C.good : snmp >= 60 ? C.warn : C.bad
  const availPct = s?.availability_pct ?? null
  const slaPct = Number(s?.sla_met_pct ?? 0)
  const slaColor = slaPct >= 99 ? C.good : slaPct >= 95 ? C.warn : C.bad
  const scheduleOk = !!emailSchedule && emailSchedule.enabled && emailSchedule.smtp_configured && emailSchedule.recipient_count > 0

  const fmtDate = (value: string) => new Date(value).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })
  const formatReportDate = (value: string) => new Date(`${value.slice(0, 10)}T12:00:00`).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })
  const periodText = s
    ? filters.period === 'today' || filters.period === 'yesterday'
      ? formatReportDate(filters.period === 'today' ? filters.start_date : filters.end_date)
      : `${fmtDate(s.period_start)} – ${fmtDate(s.period_end)}`
    : ''

  return (
    <>
    {!scheduleView && <div className="w-full space-y-6 p-4 md:p-6">
      <div className="flex gap-2 border-b pb-3" style={{ borderColor: 'var(--t-border-alpha)' }}><button type="button" onClick={() => setScheduleView(false)} className="rounded-lg px-3 py-1.5 text-[12px] font-medium" style={{ background: !scheduleView ? tint(C.info, 0.16) : 'rgba(255,255,255,.04)', color: !scheduleView ? C.info : 'var(--t-muted)' }}>Reports</button><button type="button" onClick={openSchedules} className="rounded-lg px-3 py-1.5 text-[12px] font-medium" style={{ background: scheduleView ? tint(C.info, 0.16) : 'rgba(255,255,255,.04)', color: scheduleView ? C.info : 'var(--t-muted)' }}>Scheduled Reports</button></div>
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3.5">
          <span
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl"
            style={{
              background: `linear-gradient(135deg, ${tint(C.info, 0.28)}, ${tint(C.info, 0.08)})`,
              border: `1px solid ${tint(C.info, 0.3)}`,
              color: C.info,
            }}
          >
            <IconReport className="h-5 w-5" />
          </span>
          <div>
            <h1 className="text-[22px] font-semibold leading-tight tracking-tight" style={{ color: 'var(--t-text)' }}>Report management</h1>
            <p className="mt-1 flex flex-wrap items-center gap-2 text-[13px]" style={{ color: 'var(--t-muted)' }}>
              {periodText ? (
                <>
                  <span>Showing data for</span>
                  <span
                    className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[12px] font-medium"
                    style={{ background: 'rgba(255,255,255,0.06)', border: '1px solid var(--t-border-alpha)', color: 'var(--t-text)' }}
                  >
                    <IconCalendar className="h-3.5 w-3.5" />
                    {periodText}
                  </span>
                </>
              ) : (
                'Live SNMP and ICMP monitoring data'
              )}
            </p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <ExportButton variant="ghost" busy={exporting === 'pdf'} onClick={() => void handleExport('pdf')}>
            {exporting === 'pdf' ? 'Exporting…' : 'PDF'}
          </ExportButton>
          <ExportButton variant="ghost" busy={exporting === 'csv'} onClick={() => void handleExport('csv')}>
            <IconDownload />
            {exporting === 'csv' ? 'Exporting…' : 'CSV'}
          </ExportButton>
          <ExportButton variant="solid" busy={exporting === 'xlsx'} onClick={() => void handleExport('xlsx')}>
            <IconDownload />
            {exporting === 'xlsx' ? 'Exporting…' : 'Excel'}
          </ExportButton>
        </div>
      </div>

      {/* Filters */}
      <GlassCard className="p-4 md:p-5">
        <div className="mb-4 flex flex-wrap items-end gap-x-6 gap-y-3">
          <Field label="Period">
            <Segmented
              value={filters.period}
              options={PERIODS}
              onChange={v => update({ period: v, ...(v === 'custom' ? {} : getDefaultRange(v)) })}
            />
          </Field>
          <Field label="Protocol">
            <Segmented value={filters.protocol} options={PROTOCOLS} onChange={v => update({ protocol: v })} />
          </Field>
        </div>
        <div className="grid gap-3 border-t pt-4 md:grid-cols-2 xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)_minmax(0,1fr)_auto]" style={{ borderColor: 'var(--t-border-alpha)' }}>
          <Field label="Site"><Select value={filters.site_id ?? ''} onChange={e => update({ site_id: e.target.value ? Number(e.target.value) : null, device_id: null })}><option value="">All sites</option>{options.sites.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</Select></Field>
          <Field label="Device type"><Select value={filters.device_type_id ?? ''} onChange={e => update({ device_type_id: e.target.value ? Number(e.target.value) : null, device_id: null })}><option value="">All types</option>{options.device_types.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</Select></Field>
          <Field label="Status"><Select value={filters.device_status} onChange={e => update({ device_status: e.target.value as Filters['device_status'] })}><option value="all">All statuses</option><option value="up">Up</option><option value="down">Down</option><option value="unreachable">Unreachable</option></Select></Field>
          <Field label="Alert severity"><Select value={filters.alert_severity} onChange={e => update({ alert_severity: e.target.value as Filters['alert_severity'] })}><option value="all">All severities</option>{['critical','high','medium','low','warning','info'].map(v => <option key={v} value={v}>{v}</option>)}</Select></Field>
          <Field label="Device">
            <Select value={filters.device_id ?? ''} onChange={e => update({ device_id: e.target.value ? Number(e.target.value) : null })}>
              <option value="">All devices</option>
              {selectedDevices.map(item => <option key={item.id} value={item.id}>{item.hostname} ({item.ip_address})</option>)}
            </Select>
          </Field>
          <Field label="Start date">
            <DateInput value={filters.start_date ?? ''} onChange={e => update({ start_date: e.target.value })} disabled={filters.period !== 'custom'} />
          </Field>
          <Field label="End date">
            <DateInput value={filters.end_date ?? ''} onChange={e => update({ end_date: e.target.value })} disabled={filters.period !== 'custom'} />
          </Field>
          <div className="flex items-end">
            <button
              onClick={runReport}
              disabled={loading}
              className="h-9 w-full rounded-lg px-5 text-[13px] font-medium text-white transition hover:brightness-110 focus-visible:ring-2 focus-visible:ring-sky-400/40 disabled:opacity-50 md:w-auto"
              style={{ background: 'var(--t-accent)', boxShadow: '0 2px 10px rgba(14,165,233,0.25)' }}
            >
              {loading ? 'Applying…' : 'Apply filters'}
            </button>
          </div>
        </div>
        {/* {emailSchedule && (
          <div className="mt-4 flex flex-wrap items-center gap-x-2 gap-y-1 border-t pt-3 text-[12px]" style={{ borderColor: 'var(--t-border-alpha)', color: 'var(--t-muted)' }}>
            <span style={{ color: scheduleOk ? C.good : C.warn }}><IconMail className="h-3.5 w-3.5" /></span>
            <span>
              Yesterday's Excel report emailed daily at {emailSchedule.schedule} {emailSchedule.timezone}
            </span>
            <span>· {emailSchedule.recipient_count} recipient{emailSchedule.recipient_count === 1 ? '' : 's'}</span>
            {!emailSchedule.smtp_configured && <span style={{ color: C.warn }}>· SMTP configuration required</span>}
          </div>
        )} */}
      </GlassCard>

      {s && (
        <div className={`space-y-6 transition-opacity ${loading ? 'opacity-50' : 'opacity-100'}`}>
          {/* KPIs */}
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <Kpi label="Total devices" value={s.total_devices} color={C.info} icon={<IconServer />} /><Kpi label="Up devices" value={s.up_devices} color={C.good} icon={<IconPulse />} /><Kpi label="Down devices" value={s.down_devices} color={C.bad} icon={<IconServer />} /><Kpi label="Unreachable devices" value={s.unreachable_devices} color={C.warn} icon={<IconInbox />} /><Kpi label="Total alerts" value={s.total_alerts} color={C.info} icon={<IconInbox />} /><Kpi label="Critical alerts" value={s.critical_alerts} color={C.bad} icon={<IconShield />} /><Kpi label="Total outages" value={s.total_outages} color={C.warn} icon={<IconClock />} /><Kpi label="Average availability" value={availPct == null ? "—" : `${availPct.toFixed(2)}%`} color={availabilityTone(availPct)} icon={<IconPulse />} />
          </div>
          <GlassCard className="flex flex-wrap items-center gap-x-5 gap-y-2 px-4 py-3 text-[12px]" style={{ color: 'var(--t-muted)' }}>
            <span>Alerts: <strong style={{ color: 'var(--t-text)' }}>{s.total_alerts}</strong></span>
            <span>Critical: <strong style={{ color: C.bad }}>{s.critical_alerts}</strong></span>
            <span>Warning: <strong style={{ color: C.warn }}>{s.warning_alerts}</strong></span>
            <span>Info: <strong style={{ color: C.info }}>{s.info_alerts}</strong></span>
            <span>Active: <strong style={{ color: C.warn }}>{s.active_alerts}</strong></span>
            <span>Resolved: <strong style={{ color: C.good }}>{s.resolved_alerts}</strong></span>
            <span>Acknowledged: <strong style={{ color: 'var(--t-text)' }}>{s.acknowledged_alerts}</strong></span>
            {s.alert_mttr_seconds != null && <span>MTTR: <strong style={{ color: 'var(--t-text)' }}>{formatDuration(s.alert_mttr_seconds)}</strong></span>}
          </GlassCard>
          <GlassCard className="flex flex-wrap items-center gap-x-5 gap-y-2 px-4 py-3 text-[12px]" style={{ color: 'var(--t-muted)' }}>
            <span>SLA configured: <strong style={{ color: 'var(--t-text)' }}>{s.sla_configured_devices}</strong></span><span>Met: <strong style={{ color: C.good }}>{s.sla_met_devices}</strong></span><span>Breached: <strong style={{ color: C.bad }}>{s.sla_breached_devices}</strong></span><span>Unknown: <strong style={{ color: 'var(--t-muted)' }}>{s.sla_unknown_devices}</strong></span>
          </GlassCard>
          <GlassCard className="flex flex-wrap items-center gap-x-5 gap-y-2 px-4 py-3 text-[12px]" style={{ color: 'var(--t-muted)' }}><span>Assets: <strong style={{ color: 'var(--t-text)' }}>{s.inventory_total_assets}</strong></span><span>Unknown: <strong style={{ color: C.warn }}>{s.inventory_unknown_assets}</strong></span></GlassCard>
          {/* <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
            <Kpi label="Total devices" value={s.total_devices ?? 0} hint="In selected scope" color={C.info} icon={<IconServer />} />
            <Kpi label="Availability" value={`${availPct.toFixed(2)}%`} hint={availPct == null ? 'No data' : availPct >= 99 ? 'On target' : availPct >= 95 ? 'Below target' : 'Needs attention'} color={availabilityTone(availPct)} icon={<IconPulse />} />
            <Kpi label="Total downtime" value={formatDuration(s.downtime_seconds)} hint="Across all devices" color={C.neutral} icon={<IconClock />} />
            <Kpi label="SLA met" value={`${slaPct.toFixed(2)}%`} hint={slaPct >= 99 ? 'Compliant' : 'At risk'} color={slaColor} icon={<IconShield />} />
            <Kpi label="Avg SNMP health" value={snmp != null ? Number(snmp).toFixed(1) : '—'} hint={snmp == null ? 'No SNMP data' : snmp >= 85 ? 'Healthy' : snmp >= 60 ? 'Degraded' : 'Critical'} color={snmpColor} icon={<IconHeart />} />
          </div> */}

          {/* Historical trends */}
          {s.trends && <div><div className="mb-3 text-[15px] font-semibold" style={{ color: 'var(--t-text)' }}>Historical Trends</div><div className="grid min-w-0 gap-3 lg:grid-cols-2">
            <TrendCard title="Availability trend" empty={!s.trends.availability.some(p => p.availability_percent != null)}><ResponsiveContainer width="100%" height="100%"><LineChart data={s.trends.availability}><CartesianGrid stroke="rgba(255,255,255,.08)" /><XAxis dataKey="bucket" tickFormatter={v => trendLabel(v, s.trends.bucket_granularity)} stroke="var(--t-muted)" tick={{ fontSize: 10 }} /><YAxis domain={[0, 100]} unit="%" stroke="var(--t-muted)" tick={{ fontSize: 10 }} /><Tooltip {...trendTooltip} labelFormatter={v => trendLabel(String(v), s.trends.bucket_granularity)} formatter={(v: number | null) => [v == null ? '—' : `${v.toFixed(2)}%`, 'Availability']} /><Line type="monotone" dataKey="availability_percent" stroke={C.good} dot={false} connectNulls={false} /></LineChart></ResponsiveContainer></TrendCard>
            <TrendCard title="Alert trend" empty={!s.trends.alerts.length}><ResponsiveContainer width="100%" height="100%"><BarChart data={s.trends.alerts}><CartesianGrid stroke="rgba(255,255,255,.08)" /><XAxis dataKey="bucket" tickFormatter={v => trendLabel(v, s.trends.bucket_granularity)} stroke="var(--t-muted)" tick={{ fontSize: 10 }} /><YAxis allowDecimals={false} stroke="var(--t-muted)" tick={{ fontSize: 10 }} /><Tooltip {...trendTooltip} labelFormatter={v => trendLabel(String(v), s.trends.bucket_granularity)} /><Legend /><Bar dataKey="critical" fill={C.bad} /><Bar dataKey="warning" fill={C.warn} /><Bar dataKey="info" fill={C.info} /></BarChart></ResponsiveContainer></TrendCard>
            <TrendCard title="Performance trend" empty={!s.trends.performance.some(p => p.cpu_avg != null || p.memory_avg != null)}><ResponsiveContainer width="100%" height="100%"><LineChart data={s.trends.performance}><CartesianGrid stroke="rgba(255,255,255,.08)" /><XAxis dataKey="bucket" tickFormatter={v => trendLabel(v, s.trends.bucket_granularity)} stroke="var(--t-muted)" tick={{ fontSize: 10 }} /><YAxis unit="%" stroke="var(--t-muted)" tick={{ fontSize: 10 }} /><Tooltip {...trendTooltip} labelFormatter={v => trendLabel(String(v), s.trends.bucket_granularity)} /><Legend /><Line type="monotone" dataKey="cpu_avg" name="CPU %" stroke={C.info} dot={false} connectNulls={false} /><Line type="monotone" dataKey="memory_avg" name="Memory %" stroke={C.warn} dot={false} connectNulls={false} /></LineChart></ResponsiveContainer></TrendCard>
            <TrendCard title="Bandwidth trend" empty={!s.trends.bandwidth.some(p => p.rx_mbps != null || p.tx_mbps != null)}><ResponsiveContainer width="100%" height="100%"><LineChart data={s.trends.bandwidth}><CartesianGrid stroke="rgba(255,255,255,.08)" /><XAxis dataKey="bucket" tickFormatter={v => trendLabel(v, s.trends.bucket_granularity)} stroke="var(--t-muted)" tick={{ fontSize: 10 }} /><YAxis unit=" Mbps" stroke="var(--t-muted)" tick={{ fontSize: 10 }} /><Tooltip {...trendTooltip} labelFormatter={v => trendLabel(String(v), s.trends.bucket_granularity)} formatter={(v: number | null, name: string) => [v == null ? '—' : `${v.toFixed(2)} Mbps`, name === 'rx_mbps' ? 'RX' : 'TX']} /><Legend /><Line type="monotone" dataKey="rx_mbps" name="RX" stroke={C.good} dot={false} connectNulls={false} /><Line type="monotone" dataKey="tx_mbps" name="TX" stroke={C.info} dot={false} connectNulls={false} /></LineChart></ResponsiveContainer></TrendCard>
          </div></div>}

          {/* Sections */}
          <div className="grid gap-3" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))' }}>
            {Object.entries(s.sections).map(([key, section]) => {
              const avg = section.average
              const color =
                key === 'sla' ? ((avg ?? 0) >= 99 ? C.good : C.bad) : key === 'snmp_health' ? ((avg ?? 0) >= 85 ? C.good : C.warn) : C.info
              const showRing = avg != null && key !== 'downtime'
              return (
                <GlassCard key={key} className="relative flex flex-col justify-between overflow-hidden p-4">
                  <span className="absolute inset-x-0 top-0 h-0.5" style={{ background: `linear-gradient(90deg, ${color}, transparent)` }} />
                  <div className="flex items-center gap-2">
                    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg" style={{ background: tint(color, 0.14), color }}>
                      {SECTION_ICONS[key] ?? <IconInbox />}
                    </span>
                    <div className="truncate text-[12.5px] font-medium" style={{ color: 'var(--t-muted)' }} title={section.title}>{section.title}</div>
                  </div>
                  <div className="mt-3 flex min-h-[52px] items-center justify-between gap-2">
                    <div className="truncate text-[24px] font-semibold leading-none tracking-tight tabular-nums" style={{ color: 'var(--t-text)' }}>
                      {avg != null ? (key === 'downtime' ? formatDuration(avg) : avg.toFixed(2)) : section.count}
                    </div>
                    {showRing && <Ring pct={avg as number} color={color} size={52} />}
                  </div>
                  <div className="mt-2 text-[11px]" style={{ color: 'var(--t-muted)' }}>
                    <span className="rounded-full px-2 py-0.5" style={{ background: tint(C.neutral, 0.14) }}>{section.count} records</span>
                  </div>
                </GlassCard>
              )
            })}
          </div>

          {/* Device table */}
          <GlassCard className="overflow-hidden">
            <div className="flex flex-col gap-3 px-5 py-4 sm:flex-row sm:items-center sm:justify-between" style={{ borderBottom: '1px solid var(--t-border-light)' }}>
              <div className="flex items-center gap-3">
                <span className="flex h-8 w-8 items-center justify-center rounded-lg" style={{ background: tint(C.info, 0.12), color: C.info }}>
                  <IconServer />
                </span>
                <div>
                  <h2 className="text-[15px] font-semibold leading-tight" style={{ color: 'var(--t-text)' }}>Device report</h2>
                  <p className="mt-0.5 text-[12px]" style={{ color: 'var(--t-muted)' }}>
                    {query.trim()
                      ? `${visibleRecords.length} of ${s.records.length} devices`
                      : `${s.records.length} ${s.records.length === 1 ? 'device' : 'devices'}`}
                  </p>
                </div>
              </div>
              <div className="relative w-full sm:w-72">
                <span className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2" style={{ color: 'var(--t-muted)' }}><IconSearch /></span>
                <input
                  value={query}
                  onChange={e => setQuery(e.target.value)}
                  placeholder="Search device, IP, site…"
                  className="h-9 w-full rounded-lg pl-8 pr-2.5 text-[13px] transition hover:border-white/20 focus:ring-2 focus:ring-sky-400/30"
                  style={controlStyle}
                />
              </div>
            </div>
            <div className="max-h-[70vh] overflow-auto">
              <table className="w-full border-collapse text-left text-[13px]" style={{ minWidth: 1500 }}>
                <thead>
                  <tr>
                    {['Device', 'Site', 'Protocol', 'Availability', 'Downtime', 'Outages', 'Last outage', 'Last recovery', 'Status', 'SNMP health', 'Performance', 'Interfaces', 'Alerts', 'SLA', ''].map(col => (
                      <th
                        key={col}
                        className="sticky top-0 z-10 whitespace-nowrap px-4 py-3 text-[11px] font-semibold uppercase tracking-wider first:pl-5 last:pr-5"
                        style={{ color: 'var(--t-muted)', background: 'var(--t-bg)', borderBottom: '1px solid var(--t-border-light)' }}
                      >
                        {col}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {visibleRecords.length === 0 && (
                    <tr>
                      <td colSpan={16} className="px-4 py-14 text-center">
                        <div className="mx-auto flex max-w-xs flex-col items-center gap-2" style={{ color: 'var(--t-muted)' }}>
                          <span className="flex h-11 w-11 items-center justify-center rounded-full" style={{ background: 'rgba(255,255,255,0.05)' }}>
                            <IconInbox className="h-5 w-5" />
                          </span>
                          <div className="text-[13px] font-medium" style={{ color: 'var(--t-text)' }}>No devices found</div>
                          <div className="text-[12px]">{query.trim() ? 'Try a different search term.' : 'No devices match these filters.'}</div>
                        </div>
                      </td>
                    </tr>
                  )}
                  {visibleRecords.map((row, i) => {
                    const tone = availabilityTone(row.availability_pct)
                    return (
                      <tr
                        key={row.device_id}
                        className="transition-colors hover:bg-white/[0.04]"
                        style={{ borderBottom: '1px solid var(--t-border-alpha)', background: i % 2 ? 'rgba(255,255,255,0.015)' : 'transparent' }}
                      >
                        <td className="py-3 pl-5 pr-4">
                          <div className="flex items-center gap-3">
                            <span className="relative flex h-9 w-9 shrink-0 items-center justify-center rounded-lg" style={{ background: tint(tone, 0.12), color: tone }}>
                              <IconServer />
                              <span className="absolute -bottom-0.5 -right-0.5 h-2.5 w-2.5 rounded-full" style={{ background: tone, boxShadow: '0 0 0 2px var(--t-bg)' }} />
                            </span>
                            <div className="min-w-0">
                              <div className="truncate font-medium" style={{ color: 'var(--t-text)' }}>{row.hostname}</div>
                              <div className="mt-0.5 font-mono text-[11px]" style={{ color: 'var(--t-muted)' }}>{row.ip_address}</div>
                            </div>
                          </div>
                        </td>
                        <td className="px-4 py-3" style={{ color: 'var(--t-text)' }}>{row.site_name ?? '—'}</td>
                        <td className="px-4 py-3">
                          <span className="rounded-md px-2 py-0.5 text-[10.5px] font-semibold uppercase tracking-wide" style={{ background: 'rgba(255,255,255,0.06)', color: 'var(--t-muted)' }}>{row.protocol}</span>
                        </td>
                        <td className="w-48 px-4 py-3">
                          <div className="font-semibold tabular-nums" style={{ color: tone }}>{row.availability_pct == null ? "—" : `${row.availability_pct.toFixed(2)}%`}</div>
                          <div className="mt-1.5">{row.availability_pct != null && <Bar pct={row.availability_pct} color={tone} />}</div>
                        </td>
                        <td className="whitespace-nowrap px-4 py-3 tabular-nums" style={{ color: 'var(--t-text)' }}>{formatDuration(row.downtime_seconds)}</td>
                        <td className="whitespace-nowrap px-4 py-3 tabular-nums" style={{ color: 'var(--t-text)' }}>{row.outage_count} <span style={{ color: 'var(--t-muted)' }}>({formatDuration(row.longest_outage_seconds)})</span></td>
                        <td className="whitespace-nowrap px-4 py-3 text-[11px]" style={{ color: 'var(--t-muted)' }}>{row.last_outage_time ? new Date(row.last_outage_time).toLocaleString('en-IN') : '—'}</td>
                        <td className="whitespace-nowrap px-4 py-3 text-[11px]" style={{ color: 'var(--t-muted)' }}>{row.last_recovery_time ? new Date(row.last_recovery_time).toLocaleString('en-IN') : '—'}</td>
                        <td className="whitespace-nowrap px-4 py-3"><Pill text={row.current_status} color={row.current_status === 'online' || row.current_status === 'up' ? C.good : row.current_status === 'unreachable' ? C.warn : C.bad} /></td>
                        <td className="whitespace-nowrap px-4 py-3">
                          <Pill text={row.snmp_health} color={healthTone(row.snmp_health)} />
                          {row.snmp_success_rate != null && <span className="ml-2 text-[11px] tabular-nums" style={{ color: 'var(--t-muted)' }}>{row.snmp_success_rate.toFixed(1)}%</span>}
                        </td>
                        <td className="px-4 py-3 text-[11px] leading-5" style={{ color: 'var(--t-text)' }}>
                          {row.avg_cpu_percent != null && <div>CPU {row.avg_cpu_percent.toFixed(0)}%</div>}
                          {row.avg_memory_percent != null && <div>Memory {row.avg_memory_percent.toFixed(0)}%</div>}
                          {row.avg_latency_ms != null && <div>Latency {row.avg_latency_ms.toFixed(0)}ms</div>}
                          {row.avg_cpu_percent == null && row.avg_memory_percent == null && row.avg_latency_ms == null && '—'}
                        </td>
                        <td className="whitespace-nowrap px-4 py-3 tabular-nums" style={{ color: 'var(--t-text)' }}>
                          {row.interface_count ?? 0}
                          {row.interface_down_count ? <span className="ml-2 rounded-full px-2 py-0.5 text-[11px] font-medium" style={{ background: tint(C.bad, 0.12), color: C.bad }}>{row.interface_down_count} down</span> : null}
                        </td>
                        <td className="whitespace-nowrap px-4 py-3 tabular-nums" style={{ color: 'var(--t-text)' }}>{row.alert_count} <span className="ml-1 text-[11px]" style={{ color: row.critical_alert_count ? C.bad : 'var(--t-muted)' }}>{row.critical_alert_count} critical</span></td>
                        <td className="py-3 pl-4 pr-5"><Pill text={row.sla_status} color={slaTone(row.sla_status)} /></td>
                        <td className="whitespace-nowrap px-3 py-3"><button type="button" onClick={() => setSelectedRecord(row)} className="rounded-lg px-2.5 py-1.5 text-[11px] font-medium text-sky-300 transition hover:bg-sky-400/10" style={{ border: '1px solid var(--t-border-alpha)' }}>View Details</button></td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </GlassCard>
        </div>
      )}
    </div>}
      {scheduleView && <div className="space-y-5"><GlassCard className="p-4"><div className="mb-3 flex items-center justify-between"><div><h2 className="text-[15px] font-semibold" style={{ color: 'var(--t-text)' }}>Scheduled Reports</h2><p className="text-[11px]" style={{ color: 'var(--t-muted)' }}>CSV only · Daily: previous calendar day · Weekly: previous 7 completed days · Monthly: previous calendar month</p></div><div className="flex gap-2"><button type="button" onClick={() => void loadSchedules()} className="rounded-lg px-3 py-1.5 text-[11px]" style={{ border: '1px solid var(--t-border-alpha)', color: 'var(--t-muted)' }}>Refresh</button><button type="button" onClick={() => openScheduleEditor()} className="rounded-lg px-3 py-1.5 text-[11px]" style={{ background: C.info, color: '#00131d' }}>New schedule</button></div></div>{scheduleLoading ? <div className="py-8 text-center text-[12px]" style={{ color: 'var(--t-muted)' }}>Loading scheduled reports…</div> : scheduleError ? <div className="py-6 text-center text-[12px]" style={{ color: C.bad }}>{scheduleError}</div> : schedules.length === 0 ? <div className="py-8 text-center text-[12px]" style={{ color: 'var(--t-muted)' }}>No scheduled reports yet.</div> : <div className="overflow-x-auto"><table className="w-full min-w-[720px] text-left text-[12px]"><thead><tr>{['Name','Frequency','Run time','Format','Status','Last run','Next run','Actions'].map(x => <th key={x} className="px-3 py-2 uppercase" style={{ color: 'var(--t-muted)' }}>{x}</th>)}</tr></thead><tbody>{schedules.map(item => <tr key={item.id} className="border-t" style={{ borderColor: 'var(--t-border-alpha)' }}><td className="px-3 py-2" style={{ color: 'var(--t-text)' }}>{item.name}</td><td className="px-3 py-2 uppercase">{item.frequency}</td><td className="px-3 py-2">{item.run_time}</td><td className="px-3 py-2 uppercase">{item.report_format}</td><td className="px-3 py-2"><Pill text={item.enabled ? 'enabled' : 'disabled'} color={item.enabled ? C.good : C.neutral} /></td><td className="px-3 py-2">{item.last_run_at ? new Date(item.last_run_at).toLocaleString('en-IN') : '—'}</td><td className="px-3 py-2">{item.next_run_at ? new Date(item.next_run_at).toLocaleString('en-IN') : '—'}</td><td className="px-3 py-2"><div className="flex gap-1"><button onClick={() => openScheduleEditor(item)} className="rounded px-2 py-1" style={{ border: '1px solid var(--t-border-alpha)' }}>Edit</button><button onClick={() => void toggleSchedule(item)} className="rounded px-2 py-1" style={{ border: '1px solid var(--t-border-alpha)' }}>{item.enabled ? 'Disable' : 'Enable'}</button><button onClick={() => void removeSchedule(item)} className="rounded px-2 py-1" style={{ color: C.bad, border: '1px solid var(--t-border-alpha)' }}>Delete</button></div></td></tr>)}</tbody></table></div>}</GlassCard><GlassCard className="p-4"><h2 className="mb-3 text-[15px] font-semibold" style={{ color: 'var(--t-text)' }}>Generated Reports</h2>{generatedReports.length === 0 ? <div className="py-8 text-center text-[12px]" style={{ color: 'var(--t-muted)' }}>No generated reports yet.</div> : <div className="overflow-x-auto"><table className="w-full min-w-[680px] text-left text-[12px]"><thead><tr>{['Report','Period','Generated','Format','Size','Status','Action'].map(x => <th key={x} className="px-3 py-2 uppercase" style={{ color: 'var(--t-muted)' }}>{x}</th>)}</tr></thead><tbody>{generatedReports.map(item => <tr key={item.id} className="border-t" style={{ borderColor: 'var(--t-border-alpha)' }}><td className="px-3 py-2" style={{ color: 'var(--t-text)' }}>{item.report_name}</td><td className="px-3 py-2">{new Date(item.period_start).toLocaleDateString('en-IN')} – {new Date(item.period_end).toLocaleDateString('en-IN')}</td><td className="px-3 py-2">{new Date(item.generated_at).toLocaleString('en-IN')}</td><td className="px-3 py-2 uppercase">{item.format}</td><td className="px-3 py-2">{item.file_size != null ? `${Math.max(1, Math.round(item.file_size / 1024))} KB` : '—'}</td><td className="px-3 py-2"><Pill text={item.status} color={item.status === 'SUCCESS' ? C.good : item.status === 'FAILED' ? C.bad : C.warn} /></td><td className="px-3 py-2">{item.status === 'SUCCESS' && <button onClick={() => void downloadGenerated(item)} className="rounded px-2 py-1" style={{ border: '1px solid var(--t-border-alpha)', color: C.info }}>Download</button>}</td></tr>)}</tbody></table></div>}</GlassCard></div>}
      {selectedRecord && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-3 sm:p-6" onClick={e => { if (e.target === e.currentTarget) setSelectedRecord(null) }}>
          <div className="flex max-h-[90vh] w-full max-w-5xl flex-col overflow-hidden rounded-2xl" style={{ background: 'var(--t-bg)', border: '1px solid var(--t-border-alpha)', boxShadow: '0 20px 60px rgba(0,0,0,.45)' }}>
            <div className="flex items-center justify-between border-b px-5 py-4" style={{ borderColor: 'var(--t-border-alpha)' }}><div><div className="font-semibold" style={{ color: 'var(--t-text)' }}>{selectedRecord.hostname}</div><div className="text-[12px]" style={{ color: 'var(--t-muted)' }}>{selectedRecord.ip_address}</div></div><button type="button" onClick={() => setSelectedRecord(null)} className="text-xl" style={{ color: 'var(--t-muted)' }}>×</button></div>
            <div className="space-y-5 overflow-y-auto p-5 text-[12px]" style={{ color: 'var(--t-muted)' }}>
              <section><h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wider" style={{ color: C.info }}>Overview</h3><div className="grid gap-2 sm:grid-cols-3">{[['Status', selectedRecord.current_status], ['Availability', selectedRecord.availability_pct == null ? '—' : `${selectedRecord.availability_pct.toFixed(2)}%`], ['Downtime', formatDuration(selectedRecord.downtime_seconds)], ['Outages', selectedRecord.outage_count], ['Longest outage', formatDuration(selectedRecord.longest_outage_seconds)], ['SLA target', selectedRecord.sla_target_percent != null ? `${selectedRecord.sla_target_percent.toFixed(2)}%` : '—'], ['SLA variance', selectedRecord.sla_variance_percent != null ? `${selectedRecord.sla_variance_percent.toFixed(2)}%` : '—'], ['Allowed downtime', selectedRecord.allowed_downtime_seconds != null ? formatDuration(selectedRecord.allowed_downtime_seconds) : '—'], ['SLA breach time', selectedRecord.sla_breach_seconds != null ? formatDuration(selectedRecord.sla_breach_seconds) : '—'], ['Last outage', selectedRecord.last_outage_time ? new Date(selectedRecord.last_outage_time).toLocaleString('en-IN') : '—'], ['Last recovery', selectedRecord.last_recovery_time ? new Date(selectedRecord.last_recovery_time).toLocaleString('en-IN') : '—']].map(([label, value]) => <div key={String(label)}><span>{label}: </span><strong style={{ color: 'var(--t-text)' }}>{value}</strong></div>)}</div></section>
              <section><h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wider" style={{ color: C.info }}>Asset Information</h3><div className="grid gap-2 sm:grid-cols-2">{Object.entries(selectedRecord.inventory ?? {}).filter(([, value]) => value != null && value !== '').map(([label, value]) => <div key={label}><span style={{ color: 'var(--t-muted)' }}>{label.replaceAll('_', ' ')}: </span><strong style={{ color: 'var(--t-text)' }}>{String(value)}</strong></div>)}</div></section>
              {(selectedRecord.avg_cpu_percent != null || selectedRecord.avg_memory_percent != null || selectedRecord.avg_latency_ms != null || selectedRecord.avg_packet_loss_pct != null) && <section><h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wider" style={{ color: C.info }}>Performance</h3><div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">{[['CPU', selectedRecord.avg_cpu_percent, selectedRecord.max_cpu_percent, selectedRecord.p95_cpu_percent, '%'], ['Memory', selectedRecord.avg_memory_percent, selectedRecord.max_memory_percent, selectedRecord.p95_memory_percent, '%'], ['Latency', selectedRecord.avg_latency_ms, selectedRecord.max_latency_ms, selectedRecord.p95_latency_ms, 'ms'], ['Packet loss', selectedRecord.avg_packet_loss_pct, selectedRecord.max_packet_loss_pct, null, '%']].map(([name, avg, max, p95, unit]) => <div key={String(name)} className="rounded-lg p-3" style={{ background: 'rgba(255,255,255,.04)' }}><div className="mb-1 font-medium" style={{ color: 'var(--t-text)' }}>{name}</div>Avg {avg != null ? `${Number(avg).toFixed(2)}${unit}` : '—'} · Max {max != null ? `${Number(max).toFixed(2)}${unit}` : '—'}{p95 != null && <> · P95 {Number(p95).toFixed(2)}{unit}</>}</div>)}</div></section>}
              {selectedRecord.interface_details?.length > 0 && <section><h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wider" style={{ color: C.info }}>Interfaces</h3>{selectedRecord.interface_details_truncated && <div className="mb-2 text-[11px]" style={{ color: 'var(--t-muted)' }}>Showing {selectedRecord.interface_details.length} of {selectedRecord.interface_details_total} interfaces.</div>}<div className="max-h-64 overflow-auto rounded-lg" style={{ border: '1px solid var(--t-border-alpha)' }}><table className="w-full min-w-[760px] text-left"><thead><tr>{['Interface','Status','Speed','Util avg','Util max','Util P95','RX avg','TX avg','Error rate'].map(x => <th key={x} className="whitespace-nowrap px-3 py-2 text-[10px] uppercase" style={{ color: 'var(--t-muted)' }}>{x}</th>)}</tr></thead><tbody>{selectedRecord.interface_details.map(item => <tr key={item.interface_id} className="border-t" style={{ borderColor: 'var(--t-border-alpha)' }}><td className="px-3 py-2" style={{ color: 'var(--t-text)' }}>{item.name ?? `#${item.interface_id}`}</td><td className="px-3 py-2">{item.current_status ?? '—'}</td><td className="px-3 py-2">{item.speed ?? '—'}</td><td className="px-3 py-2">{item.avg_utilization_pct != null ? `${item.avg_utilization_pct.toFixed(2)}%` : '—'}</td><td className="px-3 py-2">{item.max_utilization_pct != null ? `${item.max_utilization_pct.toFixed(2)}%` : '—'}</td><td className="px-3 py-2">{item.p95_utilization_pct != null ? `${item.p95_utilization_pct.toFixed(2)}%` : '—'}</td><td className="px-3 py-2">{item.avg_inbound_mbps != null ? `${item.avg_inbound_mbps.toFixed(2)} Mbps` : '—'}</td><td className="px-3 py-2">{item.avg_outbound_mbps != null ? `${item.avg_outbound_mbps.toFixed(2)} Mbps` : '—'}</td><td className="px-3 py-2">{item.avg_error_rate_pct != null ? `${item.avg_error_rate_pct.toFixed(4)}%` : '—'}</td></tr>)}</tbody></table></div></section>}
              {selectedRecord.alert_details?.length > 0 && <section>{selectedRecord.alert_details_truncated && <div className="mb-2 text-[11px]" style={{ color: 'var(--t-muted)' }}>Showing {selectedRecord.alert_details.length} of {selectedRecord.alert_details_total} alerts.</div>}<h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wider" style={{ color: C.info }}>Alerts</h3><div className="space-y-2">{selectedRecord.alert_details.map(alert => <div key={alert.alert_id} className="rounded-lg p-3" style={{ background: 'rgba(255,255,255,.04)' }}><div className="flex flex-wrap items-center gap-2"><Pill text={alert.severity} color={alert.severity === 'critical' ? C.bad : alert.severity === 'warning' ? C.warn : C.info} /><strong style={{ color: 'var(--t-text)' }}>{alert.title}</strong><span>{alert.status}</span></div><div className="mt-1">Created {alert.created_at ? new Date(alert.created_at).toLocaleString('en-IN') : '—'} · Resolved {alert.resolved_at ? new Date(alert.resolved_at).toLocaleString('en-IN') : '—'} · Duration {alert.duration_seconds != null ? formatDuration(alert.duration_seconds) : '—'}</div></div>)}</div></section>}
            </div>
          </div>
        </div>
      )}
      {scheduleEditor !== false && <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-3" onClick={e => { if (e.target === e.currentTarget) setScheduleEditor(false) }}><div className="w-full max-w-lg rounded-2xl p-5" style={{ background: 'var(--t-bg)', border: '1px solid var(--t-border-alpha)' }}><div className="mb-4 flex items-center justify-between"><h2 className="font-semibold" style={{ color: 'var(--t-text)' }}>{scheduleEditor ? 'Edit schedule' : 'New schedule'}</h2><button onClick={() => setScheduleEditor(false)} style={{ color: 'var(--t-muted)' }}>×</button></div><div className="grid gap-3 sm:grid-cols-2">{[['Name', 'name']].map(([label, key]) => <label key={key} className="sm:col-span-2 text-[11px]" style={{ color: 'var(--t-muted)' }}>{label}<input value={scheduleForm.name} onChange={e => setScheduleForm(v => ({ ...v, name: e.target.value }))} className="mt-1 w-full rounded-lg p-2 text-[12px]" style={{ background: 'rgba(255,255,255,.04)', color: 'var(--t-text)', border: '1px solid var(--t-border-alpha)' }} /></label>)}<label className="text-[11px]" style={{ color: 'var(--t-muted)' }}>Frequency<select value={scheduleForm.frequency} onChange={e => setScheduleForm(v => ({ ...v, frequency: e.target.value as ReportSchedule['frequency'] }))} className="mt-1 w-full rounded-lg p-2" style={{ background: 'var(--t-bg)', color: 'var(--t-text)' }}><option value="daily">Daily</option><option value="weekly">Weekly</option><option value="monthly">Monthly</option></select></label><label className="text-[11px]" style={{ color: 'var(--t-muted)' }}>Run time<input type="time" value={scheduleForm.run_time} onChange={e => setScheduleForm(v => ({ ...v, run_time: e.target.value }))} className="mt-1 w-full rounded-lg p-2" style={{ background: 'var(--t-bg)', color: 'var(--t-text)' }} /></label><label className="text-[11px]" style={{ color: 'var(--t-muted)' }}>Format<input value="CSV" disabled className="mt-1 w-full rounded-lg p-2" style={{ background: 'rgba(255,255,255,.04)', color: 'var(--t-muted)' }} /></label><label className="flex items-end gap-2 text-[11px]" style={{ color: 'var(--t-muted)' }}><input type="checkbox" checked={scheduleForm.enabled} onChange={e => setScheduleForm(v => ({ ...v, enabled: e.target.checked }))} /> Enabled</label><label className="text-[11px]" style={{ color: 'var(--t-muted)' }}>Site<select value={scheduleForm.site_id ?? ''} onChange={e => setScheduleForm(v => ({ ...v, site_id: e.target.value ? Number(e.target.value) : null }))} className="mt-1 w-full rounded-lg p-2" style={{ background: 'var(--t-bg)', color: 'var(--t-text)' }}><option value="">All sites</option>{options.sites.map(x => <option key={x.id} value={x.id}>{x.name}</option>)}</select></label><label className="text-[11px]" style={{ color: 'var(--t-muted)' }}>Device type<select value={scheduleForm.device_type_id ?? ''} onChange={e => setScheduleForm(v => ({ ...v, device_type_id: e.target.value ? Number(e.target.value) : null }))} className="mt-1 w-full rounded-lg p-2" style={{ background: 'var(--t-bg)', color: 'var(--t-text)' }}><option value="">All types</option>{options.device_types.map(x => <option key={x.id} value={x.id}>{x.name}</option>)}</select></label><label className="text-[11px]" style={{ color: 'var(--t-muted)' }}>Device<select value={scheduleForm.device_id ?? ''} onChange={e => setScheduleForm(v => ({ ...v, device_id: e.target.value ? Number(e.target.value) : null }))} className="mt-1 w-full rounded-lg p-2" style={{ background: 'var(--t-bg)', color: 'var(--t-text)' }}><option value="">All devices</option>{options.devices.map(x => <option key={x.id} value={x.id}>{x.hostname}</option>)}</select></label><label className="text-[11px]" style={{ color: 'var(--t-muted)' }}>Protocol<select value={scheduleForm.protocol} onChange={e => setScheduleForm(v => ({ ...v, protocol: e.target.value as Filters['protocol'] }))} className="mt-1 w-full rounded-lg p-2" style={{ background: 'var(--t-bg)', color: 'var(--t-text)' }}><option value="all">SNMP + ICMP</option><option value="snmp">SNMP</option><option value="icmp">ICMP</option></select></label><label className="text-[11px]" style={{ color: 'var(--t-muted)' }}>Status<select value={scheduleForm.device_status} onChange={e => setScheduleForm(v => ({ ...v, device_status: e.target.value as Filters['device_status'] }))} className="mt-1 w-full rounded-lg p-2" style={{ background: 'var(--t-bg)', color: 'var(--t-text)' }}><option value="all">All</option><option value="up">Up</option><option value="down">Down</option><option value="unreachable">Unreachable</option></select></label><label className="text-[11px]" style={{ color: 'var(--t-muted)' }}>Alert severity<select value={scheduleForm.alert_severity} onChange={e => setScheduleForm(v => ({ ...v, alert_severity: e.target.value as Filters['alert_severity'] }))} className="mt-1 w-full rounded-lg p-2" style={{ background: 'var(--t-bg)', color: 'var(--t-text)' }}><option value="all">All</option><option value="critical">Critical</option><option value="warning">Warning</option><option value="info">Info</option></select></label><div className="flex justify-end gap-2 sm:col-span-2"><button onClick={() => setScheduleEditor(false)} className="rounded-lg px-3 py-2 text-[12px]" style={{ border: '1px solid var(--t-border-alpha)', color: 'var(--t-muted)' }}>Cancel</button><button onClick={() => void saveSchedule()} className="rounded-lg px-3 py-2 text-[12px]" style={{ background: C.info, color: '#00131d' }}>Save</button></div></div></div></div>}
    </>
  )
}