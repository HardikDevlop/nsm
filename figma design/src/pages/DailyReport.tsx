/**
 * NMS Pro — Daily Network Monitoring Report
 * All 8 sections, real data, print/export support.
 */
import { useEffect, useRef, useState } from 'react'
import type React from 'react'
import GlassCard from '../components/GlassCard'
import { getDailyReport, type DailyReport, type DailyReportDevice } from '../lib/api'

let xlsxModulePromise: Promise<typeof import('xlsx')> | null = null

/* ── colour palette ─────────────────────────────────────────────────────── */
const SEV: Record<string, { bg: string; text: string; border: string }> = {
  CRITICAL: { bg: 'rgba(255,51,102,0.12)',  text: '#ff3366', border: 'rgba(255,51,102,0.35)'  },
  HIGH:     { bg: 'rgba(255,102,68,0.12)',  text: '#ff6644', border: 'rgba(255,102,68,0.35)'  },
  WARNING:  { bg: 'rgba(255,170,0,0.12)',   text: '#ffaa00', border: 'rgba(255,170,0,0.35)'   },
  INFO:     { bg: 'rgba(0,212,255,0.10)',   text: '#00d4ff', border: 'rgba(0,212,255,0.30)'   },
  GOOD:     { bg: 'rgba(0,255,136,0.10)',   text: '#00ff88', border: 'rgba(0,255,136,0.30)'   },
}
const statusStyle = (s: string) =>
  s === 'online'  ? { color: '#00ff88' } :
  s === 'offline' ? { color: '#ff3366' } : { color: '#ffaa00' }

/* ── tiny helpers ───────────────────────────────────────────────────────── */
const na = (v: unknown): string => (v === null || v === undefined) ? 'N/A' : String(v)
const pct = (v: number | null | undefined) => v != null ? `${v.toFixed(1)}%` : 'N/A'
const ms  = (v: number | null | undefined) => v != null ? `${v.toFixed(1)} ms` : 'N/A'
const fmtBytes = (b: number | undefined | null) => {
  if (!b) return '0 B'
  if (b >= 1_073_741_824) return `${(b / 1_073_741_824).toFixed(2)} GB`
  if (b >= 1_048_576)     return `${(b / 1_048_576).toFixed(1)} MB`
  if (b >= 1024)          return `${(b / 1024).toFixed(1)} KB`
  return `${b} B`
}
const fmtSec = (s: number) => {
  if (!s) return '0s'
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60
  return h ? `${h}h ${m}m ${sec}s` : m ? `${m}m ${sec}s` : `${sec}s`
}
const ts = (iso: string | null | undefined) =>
  iso ? new Date(iso).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', hour12: false }) : '—'

/* ── reusable UI parts ──────────────────────────────────────────────────── */
function SevBadge({ sev }: { sev: string }) {
  const s = SEV[sev.toUpperCase()] ?? SEV.INFO
  return (
    <span className="font-mono text-[10px] px-1.5 py-0.5 rounded font-semibold uppercase"
      style={{ background: s.bg, color: s.text, border: `1px solid ${s.border}` }}>
      {sev}
    </span>
  )
}

function SectionTitle({ icon, title, subtitle }: { icon: string; title: string; subtitle?: string }) {
  return (
    <div className="flex items-center gap-3 mb-4 pb-3" style={{ borderBottom: '1px solid rgba(0,212,255,0.12)' }}>
      <div className="w-9 h-9 rounded-lg flex items-center justify-center shrink-0"
        style={{ background: 'rgba(0,212,255,0.1)', border: '1px solid rgba(0,212,255,0.25)' }}>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#00d4ff" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
          <path d={icon}/>
        </svg>
      </div>
      <div>
        <div className="font-display font-bold text-base tracking-wider neon-cyan">{title}</div>
        {subtitle && <div className="font-mono text-[10px] mt-0.5" style={{ color: 'var(--t-muted, #8899bb)' }}>{subtitle}</div>}
      </div>
    </div>
  )
}

function StatTile({ label, value, color = 'var(--t-text, #c8d8ee)', sub }: { label: string; value: string | number; color?: string; sub?: string }) {
  return (
    <div className="p-3 rounded-lg text-center" style={{ background: 'rgba(0,0,0,0.2)', border: '1px solid rgba(0,212,255,0.1)' }}>
      <div className="font-display font-bold text-xl" style={{ color }}>{value}</div>
      <div className="font-mono text-[10px] mt-0.5" style={{ color: 'var(--t-muted, #8899bb)' }}>{label}</div>
      {sub && <div className="font-mono text-[9px] mt-0.5" style={{ color: 'var(--t-muted, #556677)' }}>{sub}</div>}
    </div>
  )
}

function MiniBar({ pct: p, color = '#00d4ff' }: { pct: number; color?: string }) {
  const c = p >= 90 ? '#ff3366' : p >= 70 ? '#ffaa00' : color
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 rounded-full overflow-hidden" style={{ background: 'rgba(0,0,0,0.3)', minWidth: 60 }}>
        <div className="h-full rounded-full" style={{ width: `${Math.min(p, 100)}%`, background: c }}/>
      </div>
      <span className="font-mono text-[10px] w-8 text-right shrink-0" style={{ color: c }}>{p.toFixed(0)}%</span>
    </div>
  )
}

function DeviceTable({ rows, cols }: {
  rows: DailyReportDevice[]
  cols: { key: string; label: string; render?: (row: DailyReportDevice) => React.ReactNode }[]
}) {
  if (!rows.length) return <div className="font-mono text-xs py-4 text-center" style={{ color: 'var(--t-muted, #8899bb)' }}>Data Not Available</div>
  return (
    <div className="overflow-x-auto">
      <table className="w-full" style={{ minWidth: 400 }}>
        <thead>
          <tr style={{ borderBottom: '1px solid rgba(0,212,255,0.1)' }}>
            {cols.map(c => <th key={c.key} className="text-left px-3 py-2 font-mono text-[10px] uppercase" style={{ color: 'var(--t-muted, #8899bb)' }}>{c.label}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} style={{ borderBottom: '1px solid rgba(0,212,255,0.05)' }}>
              {cols.map(c => (
                <td key={c.key} className="px-3 py-2 font-mono text-xs" style={{ color: 'var(--t-text, #c8d8ee)' }}>
                  {c.render ? c.render(row) : na((row as unknown as Record<string, unknown>)[c.key])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function HealthGauge({ score, label }: { score: number; label: string }) {
  const color = score >= 80 ? '#00ff88' : score >= 60 ? '#ffaa00' : '#ff3366'
  const r = 36, circ = 2 * Math.PI * r
  const dash = (score / 100) * circ
  return (
    <div className="flex flex-col items-center">
      <svg width="100" height="100" viewBox="0 0 100 100">
        <circle cx="50" cy="50" r={r} fill="none" stroke="rgba(0,212,255,0.1)" strokeWidth="8"/>
        <circle cx="50" cy="50" r={r} fill="none" stroke={color} strokeWidth="8"
          strokeDasharray={`${dash} ${circ}`} strokeLinecap="round"
          transform="rotate(-90 50 50)"
          style={{ filter: `drop-shadow(0 0 6px ${color})`, transition: 'stroke-dasharray 1s ease' }}/>
        <text x="50" y="46" textAnchor="middle" style={{ fontSize: 18, fontFamily: 'Space Grotesk', fontWeight: 700, fill: color }}>{score}</text>
        <text x="50" y="60" textAnchor="middle" style={{ fontSize: 9, fontFamily: 'JetBrains Mono', fill: 'var(--t-muted, #8899bb)' }}>/ 100</text>
      </svg>
      <div className="font-mono text-xs mt-1 font-bold" style={{ color }}>{label}</div>
    </div>
  )
}

/* ═══════════════════════════════════════════════════════════════════════════
   EXCEL EXPORT
═══════════════════════════════════════════════════════════════════════════ */
async function exportToExcel(d: DailyReport) {
  const XLSX = await (xlsxModulePromise ??= import('xlsx'))
  const wb = XLSX.utils.book_new()

  /* ── helper: append a sheet ── */
  const addSheet = (name: string, rows: Record<string, unknown>[]) => {
    const ws = XLSX.utils.json_to_sheet(rows)
    // auto-width columns
    const cols = rows.length ? Object.keys(rows[0]).map(k => ({
      wch: Math.max(k.length, ...rows.map(r => String(r[k] ?? '').length)) + 2,
    })) : []
    ws['!cols'] = cols
    XLSX.utils.book_append_sheet(wb, ws, name)
  }

  /* 1 ── Summary sheet */
  addSheet('Summary', [
    { Field: 'Report Date',         Value: d.report_date },
    { Field: 'Period',              Value: d.period },
    { Field: 'Generated At',        Value: d.generated_at },
    { Field: 'Overall Health',      Value: d.daily_summary.overall_health },
    { Field: 'Health Score',        Value: d.daily_summary.health_score },
    { Field: 'Total Devices',       Value: d.availability.total_devices },
    { Field: 'Online Devices',      Value: d.availability.online },
    { Field: 'Offline Devices',     Value: d.availability.offline },
    { Field: 'Availability %',      Value: d.availability.availability_pct },
    { Field: 'Status Changes 24h',  Value: d.incidents.total_status_changes },
    { Field: 'Total Alerts 24h',    Value: d.alerts.total_alerts_24h },
    { Field: 'Critical Alerts',     Value: d.alerts.critical },
    { Field: 'Open Alerts',         Value: d.alerts.open },
    { Field: 'Resolved Alerts',     Value: d.alerts.resolved },
    { Field: 'Total Interfaces',    Value: d.interfaces.total },
    { Field: 'Interfaces Up',       Value: d.interfaces.up },
    { Field: 'Interfaces Down',     Value: d.interfaces.down },
    { Field: 'Perf Samples 24h',    Value: d.performance.sample_count },
    { Field: 'Avg CPU %',           Value: d.performance.cpu.avg ?? 'N/A' },
    { Field: 'Avg Memory %',        Value: d.performance.memory.avg ?? 'N/A' },
    { Field: 'Avg Latency ms',      Value: d.performance.latency.avg ?? 'N/A' },
    { Field: 'Avg Packet Loss %',   Value: d.performance.packet_loss.avg ?? 'N/A' },
  ])

  /* 2 ── Device Availability */
  if (d.availability.devices_with_downtime.length) {
    addSheet('Availability', d.availability.devices_with_downtime.map(r => ({
      Hostname:       r.hostname,
      'IP Address':   r.ip,
      Status:         r.status ?? '',
      'Downtime (s)': r.downtime_sec ?? 0,
      'Last Seen':    (r as unknown as Record<string, unknown>)['last_seen'] as string ?? '',
    })))
  }

  /* 3 ── Performance */
  addSheet('Performance', [
    { Metric: 'CPU Utilization %',   Avg: d.performance.cpu.avg,      Max: d.performance.cpu.max,      Samples: d.performance.cpu.samples },
    { Metric: 'Memory Utilization %',Avg: d.performance.memory.avg,   Max: d.performance.memory.max,   Samples: d.performance.memory.samples },
    { Metric: 'Disk Utilization %',  Avg: d.performance.disk.avg,     Max: d.performance.disk.max,     Samples: d.performance.disk.samples },
    { Metric: 'Latency ms',          Avg: d.performance.latency.avg,  Max: d.performance.latency.max,  Samples: d.performance.latency.samples },
    { Metric: 'Packet Loss %',       Avg: d.performance.packet_loss.avg, Max: d.performance.packet_loss.max, Samples: d.performance.packet_loss.samples },
    { Metric: 'Bandwidth',           Avg: d.performance.bandwidth.avg,Max: d.performance.bandwidth.max,Samples: d.performance.bandwidth.samples },
  ])

  /* 4 ── Interfaces */
  if (d.interfaces.high_traffic.length) {
    addSheet('Interfaces', d.interfaces.high_traffic.map(i => ({
      Name:         i.name,
      Device:       i.hostname,
      Status:       i.status,
      'Traffic In': i.traffic_in ?? 0,
      'Traffic Out':i.traffic_out ?? 0,
      Speed:        i.speed ?? '',
      'Last Updated': i.last_updated ?? '',
    })))
  }

  /* 5 ── Alerts */
  if (d.alerts.recent_alerts.length) {
    addSheet('Alerts', d.alerts.recent_alerts.map(a => ({
      Severity:    a.severity,
      Title:       a.title,
      Device:      a.hostname,
      Status:      a.status,
      'Created At':a.created_at ?? '',
    })))
  }

  /* 6 ── Incidents */
  if (d.incidents.changes.length) {
    addSheet('Incidents', d.incidents.changes.map(c => ({
      Device:      c.hostname,
      IP:          c.ip,
      'Old Status':c.old_status ?? '',
      'New Status':c.new_status,
      Reason:      c.reason ?? '',
      Timestamp:   c.timestamp ?? '',
    })))
  }

  /* 7 ── Top Performers */
  const perfRows = [
    ...d.top_performers.top_cpu.map(r => ({ Category: 'Top CPU',     Hostname: r.hostname, IP: r.ip, 'Avg Value': r.avg_value, 'Max Value': r.max_value })),
    ...d.top_performers.top_memory.map(r => ({ Category: 'Top Memory', Hostname: r.hostname, IP: r.ip, 'Avg Value': r.avg_value, 'Max Value': r.max_value })),
    ...d.top_performers.top_latency.map(r => ({ Category: 'Top Latency', Hostname: r.hostname, IP: r.ip, 'Avg Value': r.avg_value, 'Max Value': r.max_value })),
    ...d.top_performers.max_downtime.map(r => ({ Category: 'Max Downtime', Hostname: r.hostname, IP: r.ip, 'Avg Value': r.downtime_sec, 'Max Value': r.downtime_sec })),
    ...d.top_performers.max_alerts.map(r => ({ Category: 'Most Alerts', Hostname: r.hostname, IP: r.ip, 'Avg Value': r.alerts ?? r.count, 'Max Value': r.alerts ?? r.count })),
  ]
  if (perfRows.length) addSheet('Top Performers', perfRows)

  /* 8 ── Recommendations */
  addSheet('Recommendations', d.recommendations.map((r, i) => ({
    '#':        i + 1,
    Priority:   r.priority,
    Action:     r.message,
  })))

  /* ── Save ── */
  const filename = `NMS_Daily_Report_${d.report_date}.xlsx`
  XLSX.writeFile(wb, filename)
}

/* ═══════════════════════════════════════════════════════════════════════════
   MAIN PAGE
═══════════════════════════════════════════════════════════════════════════ */
export default function DailyReport() {
  const [data,    setData]    = useState<DailyReport | null>(null)
  const [loading, setLoading] = useState(true)
  const [error,   setError]   = useState<string | null>(null)
  const [exporting, setExporting] = useState(false)
  const printRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    void (async () => {
      try {
        setData(await getDailyReport())
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Failed to load report')
      }
      setLoading(false)
    })()
  }, [])

  const handlePrint = () => window.print()
  const handleExport = async () => {
    if (!data || exporting) return
    setExporting(true)
    try {
      await exportToExcel(data)
    } finally {
      setExporting(false)
    }
  }

  /* ── loading / error ── */
  if (loading) return (
    <div className="p-6 flex items-center justify-center min-h-[60vh]">
      <div className="flex flex-col items-center gap-4">
        <div className="w-10 h-10 rounded-full border-2 animate-spin" style={{ borderColor: '#00d4ff', borderTopColor: 'transparent' }}/>
        <span className="font-mono text-sm" style={{ color: 'var(--t-muted, #8899bb)' }}>Generating report…</span>
      </div>
    </div>
  )

  if (error || !data) return (
    <div className="p-6 font-mono text-sm text-center" style={{ color: '#ff3366' }}>
      {error ?? 'No data returned'} — check backend logs.
    </div>
  )

  const d = data
  const healthColor = d.daily_summary.overall_health === 'GOOD' ? '#00ff88'
    : d.daily_summary.overall_health === 'WARNING' ? '#ffaa00' : '#ff3366'

  return (
    <>
      {/* ── Print CSS injected inline ── */}
      <style>{`
        @media print {
          body { background: #fff !important; color: #000 !important; }
          .no-print { display: none !important; }
          .print-page { page-break-inside: avoid; }
          .glass, .glass-bright { background: #f8f9fa !important; border: 1px solid #dee2e6 !important; }
          .neon-cyan { color: #0066cc !important; }
          * { box-shadow: none !important; text-shadow: none !important; }
        }
      `}</style>

      <div ref={printRef} className="p-4 md:p-6 space-y-6 w-full">

        {/* ══ REPORT HEADER ══════════════════════════════════════════════ */}
        <div className="no-print flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
          <div>
            <h1 className="font-display font-bold text-2xl tracking-widest neon-cyan">
              NMS PRO — DAILY NETWORK MONITORING REPORT
            </h1>
            <p className="font-mono text-xs mt-1" style={{ color: 'var(--t-muted, #8899bb)' }}>
              Reporting Period: {d.period}
            </p>
          </div>
          <div className="flex gap-2 shrink-0">
            <button onClick={() => void getDailyReport().then(setData)}
              className="flex items-center gap-1.5 px-3 py-2 rounded font-mono text-xs hover:opacity-80 transition-all"
              style={{ background: 'rgba(0,212,255,0.1)', border: '1px solid rgba(0,212,255,0.3)', color: '#00d4ff' }}>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M23 4v6h-6M1 20v-6h6"/><path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/></svg>
              Refresh
            </button>
            <button onClick={handlePrint}
              className="flex items-center gap-1.5 px-4 py-2 rounded font-mono text-xs font-semibold hover:opacity-90 transition-all"
              style={{ background: 'var(--t-accent)', color: '#fff', border: '1px solid var(--t-accent-border)' }}>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="6 9 6 2 18 2 18 9"/><path d="M6 18H4a2 2 0 01-2-2v-5a2 2 0 012-2h16a2 2 0 012 2v5a2 2 0 01-2 2h-2"/><rect x="6" y="14" width="12" height="8"/></svg>
              Print / PDF
            </button>
            <button onClick={() => void handleExport()}
              className="flex items-center gap-1.5 px-4 py-2 rounded font-mono text-xs font-semibold hover:opacity-90 transition-all"
              style={{ background: 'rgba(0,200,100,0.15)', color: '#00cc66', border: '1px solid rgba(0,200,100,0.4)' }}>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>
              {exporting ? 'Exporting…' : 'Export Excel'}
            </button>          </div>
        </div>

        {/* Report title band (visible in print too) */}
        <GlassCard className="p-5 print-page">
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
            <div>
              <div className="font-display font-bold text-xl tracking-wider neon-cyan">
                NMS PRO — DAILY NETWORK MONITORING REPORT
              </div>
              <div className="font-mono text-xs mt-1 space-y-0.5">
                <div style={{ color: 'var(--t-muted, #8899bb)' }}>Date: <span style={{ color: 'var(--t-text, #c8d8ee)' }}>{d.report_date}</span></div>
                <div style={{ color: 'var(--t-muted, #8899bb)' }}>Period: <span style={{ color: 'var(--t-text, #c8d8ee)' }}>{d.period}</span></div>
                <div style={{ color: 'var(--t-muted, #8899bb)' }}>Generated: <span style={{ color: 'var(--t-text, #c8d8ee)' }}>{ts(d.generated_at)}</span></div>
              </div>
            </div>
            <div className="flex items-center gap-6">
              <HealthGauge score={d.daily_summary.health_score} label={d.daily_summary.overall_health}/>
              <div className="space-y-1.5">
                <div className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full" style={{ background: '#00ff88' }}/>
                  <span className="font-mono text-xs" style={{ color: 'var(--t-muted, #8899bb)' }}>Online: <span style={{ color: '#00ff88' }}>{d.availability.online}</span></span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full" style={{ background: '#ff3366' }}/>
                  <span className="font-mono text-xs" style={{ color: 'var(--t-muted, #8899bb)' }}>Offline: <span style={{ color: '#ff3366' }}>{d.availability.offline}</span></span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full" style={{ background: '#00d4ff' }}/>
                  <span className="font-mono text-xs" style={{ color: 'var(--t-muted, #8899bb)' }}>Availability: <span style={{ color: '#00d4ff' }}>{pct(d.availability.availability_pct)}</span></span>
                </div>
              </div>
            </div>
          </div>
        </GlassCard>

        {/* ══ SECTION 1 — DEVICE AVAILABILITY ════════════════════════════ */}
        <GlassCard className="p-5 print-page">
          <SectionTitle icon="M9 3H5a2 2 0 00-2 2v4m6-6h10a2 2 0 012 2v4M9 3v18" title="1. Device / Network Availability" subtitle="Status of all monitored devices in the last 24 hours"/>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-5">
            <StatTile label="Total Devices"   value={d.availability.total_devices} color="#00d4ff"/>
            <StatTile label="Online"          value={d.availability.online}  color="#00ff88"/>
            <StatTile label="Offline"         value={d.availability.offline} color={d.availability.offline > 0 ? '#ff3366' : 'var(--t-muted, #8899bb)'}/>
            <StatTile label="Availability %"  value={pct(d.availability.availability_pct)} color={d.availability.availability_pct >= 99 ? '#00ff88' : d.availability.availability_pct >= 95 ? '#ffaa00' : '#ff3366'}/>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mb-5">
            <StatTile label="Status Changes" value={d.incidents.total_status_changes} color="#ffaa00" sub="In 24h"/>
            <StatTile label="Went Offline"   value={d.incidents.went_offline}  color="#ff3366" sub="In 24h"/>
            <StatTile label="Came Online"    value={d.incidents.came_online}   color="#00ff88" sub="In 24h"/>
          </div>
          {d.availability.devices_with_downtime.length > 0 ? (
            <>
              <div className="font-mono text-xs font-semibold mb-2" style={{ color: '#ff3366' }}>⚠ Devices with Downtime</div>
              <DeviceTable rows={d.availability.devices_with_downtime} cols={[
                { key: 'hostname', label: 'Hostname' },
                { key: 'ip_address', label: 'IP Address', render: r => r.ip },
                { key: 'status',   label: 'Status', render: r => <span style={statusStyle(r.status ?? '')}>{r.status ?? '—'}</span> },
                { key: 'downtime', label: 'Downtime', render: r => fmtSec(r.downtime_sec ?? 0) },
                { key: 'last_seen',label: 'Last Seen', render: r => ts(r['last_seen' as keyof typeof r] as string) },
              ]}/>
            </>
          ) : (
            <div className="font-mono text-xs py-3 px-4 rounded-lg" style={{ background: 'rgba(0,255,136,0.06)', border: '1px solid rgba(0,255,136,0.2)', color: '#00ff88' }}>
              ✓ All devices online — no downtime recorded in last 24 hours.
            </div>
          )}
        </GlassCard>

        {/* ══ SECTION 2 — PERFORMANCE MONITORING ═════════════════════════ */}
        <GlassCard className="p-5 print-page">
          <SectionTitle icon="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" title="2. Performance Monitoring" subtitle={`${d.performance.sample_count.toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', hour12: true })} metric samples in 24h`}/>

          {/* Performance overview table */}
          <div className="overflow-x-auto mb-5">
            <table className="w-full" style={{ minWidth: 500 }}>
              <thead>
                <tr style={{ borderBottom: '1px solid rgba(0,212,255,0.1)' }}>
                  {['Metric', 'Avg', 'Max', 'Samples', 'Status'].map(h => (
                    <th key={h} className="text-left px-3 py-2 font-mono text-[10px] uppercase" style={{ color: 'var(--t-muted, #8899bb)' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {[
                  { label: 'CPU Utilization',   data: d.performance.cpu,         unit: '%', threshold: 70 },
                  { label: 'Memory Utilization',data: d.performance.memory,       unit: '%', threshold: 80 },
                  { label: 'Disk Utilization',  data: d.performance.disk,         unit: '%', threshold: 85 },
                  { label: 'Latency / RTT',     data: d.performance.latency,      unit: ' ms', threshold: 100 },
                  { label: 'Packet Loss',        data: d.performance.packet_loss, unit: '%', threshold: 1 },
                  { label: 'Bandwidth Usage',   data: d.performance.bandwidth,    unit: ' Mbps', threshold: 80 },
                ].map(row => {
                  const avg  = row.data.avg
                  const maxV = row.data.max
                  const bad  = avg != null && avg > row.threshold
                  const col  = avg == null ? 'var(--t-muted, #8899bb)' : bad ? '#ff3366' : avg > row.threshold * 0.8 ? '#ffaa00' : '#00ff88'
                  return (
                    <tr key={row.label} style={{ borderBottom: '1px solid rgba(0,212,255,0.05)' }}>
                      <td className="px-3 py-2.5 font-mono text-xs" style={{ color: 'var(--t-text, #c8d8ee)' }}>{row.label}</td>
                      <td className="px-3 py-2.5 font-mono text-xs font-semibold" style={{ color: col }}>
                        {avg != null ? `${avg.toFixed(1)}${row.unit}` : 'N/A'}
                      </td>
                      <td className="px-3 py-2.5 font-mono text-xs" style={{ color: 'var(--t-muted, #8899bb)' }}>
                        {maxV != null ? `${maxV.toFixed(1)}${row.unit}` : 'N/A'}
                      </td>
                      <td className="px-3 py-2.5 font-mono text-xs" style={{ color: 'var(--t-muted, #8899bb)' }}>{row.data.samples}</td>
                      <td className="px-3 py-2.5">
                        {row.data.samples === 0
                          ? <span className="font-mono text-[10px] px-1.5 py-0.5 rounded" style={{ background: 'rgba(136,153,187,0.1)', color: 'var(--t-muted, #8899bb)' }}>N/A</span>
                          : bad
                            ? <SevBadge sev="WARNING"/>
                            : <span className="font-mono text-[10px] px-1.5 py-0.5 rounded" style={{ background: 'rgba(0,255,136,0.1)', color: '#00ff88' }}>NORMAL</span>
                        }
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>

          {/* Top devices */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            {[
              { title: 'Top CPU Devices',     rows: d.performance.top_cpu_devices,     key: 'avg_value', unit: '%' },
              { title: 'Top Memory Devices',  rows: d.performance.top_mem_devices,     key: 'avg_value', unit: '%' },
              { title: 'Top Latency Devices', rows: d.performance.top_latency_devices, key: 'avg_value', unit: ' ms' },
            ].map(panel => (
              <div key={panel.title}>
                <div className="font-mono text-[10px] font-semibold mb-2 uppercase tracking-wider" style={{ color: 'var(--t-muted, #667799)' }}>{panel.title}</div>
                {panel.rows.length === 0
                  ? <div className="font-mono text-xs" style={{ color: 'var(--t-muted, #8899bb)' }}>N/A</div>
                  : <div className="space-y-2">
                      {panel.rows.map((r, i) => {
                        const v = (r as unknown as Record<string,unknown>)[panel.key] as number ?? 0
                        return (
                          <div key={i}>
                            <div className="flex justify-between font-mono text-[10px] mb-0.5">
                              <span className="truncate max-w-[120px]" style={{ color: 'var(--t-text, #c8d8ee)' }}>{r.hostname}</span>
                              <span style={{ color: v > 70 ? '#ff3366' : '#00d4ff' }}>{v.toFixed(1)}{panel.unit}</span>
                            </div>
                            <MiniBar pct={panel.unit === ' ms' ? Math.min(v / 3, 100) : v}/>
                          </div>
                        )
                      })}
                    </div>
                }
              </div>
            ))}
          </div>
        </GlassCard>

        {/* ══ SECTION 3 — NETWORK INTERFACE DETAILS ══════════════════════ */}
        <GlassCard className="p-5 print-page">
          <SectionTitle icon="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" title="3. Network Interface Details" subtitle="Interface status, traffic and errors"/>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mb-5">
            <StatTile label="Total Interfaces" value={d.interfaces.total} color="#00d4ff"/>
            <StatTile label="Up"   value={d.interfaces.up}   color="#00ff88"/>
            <StatTile label="Down" value={d.interfaces.down} color={d.interfaces.down > 0 ? '#ff3366' : 'var(--t-muted, #8899bb)'}/>
          </div>

          {/* High traffic */}
          <div className="mb-4">
            <div className="font-mono text-[10px] font-semibold mb-2 uppercase tracking-wider" style={{ color: 'var(--t-muted, #667799)' }}>High-Utilisation Interfaces (Top 10 by Traffic)</div>
            {d.interfaces.high_traffic.length === 0
              ? <div className="font-mono text-xs" style={{ color: 'var(--t-muted, #8899bb)' }}>Data Not Available</div>
              : <div className="overflow-x-auto">
                  <table className="w-full" style={{ minWidth: 520 }}>
                    <thead>
                      <tr style={{ borderBottom: '1px solid rgba(0,212,255,0.1)' }}>
                        {['Interface','Device','Status','Traffic In','Traffic Out','Speed'].map(h => (
                          <th key={h} className="text-left px-3 py-2 font-mono text-[10px] uppercase" style={{ color: 'var(--t-muted, #8899bb)' }}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {d.interfaces.high_traffic.map((iface, i) => (
                        <tr key={i} style={{ borderBottom: '1px solid rgba(0,212,255,0.05)' }}>
                          <td className="px-3 py-2 font-mono text-xs" style={{ color: '#00d4ff' }}>{iface.name}</td>
                          <td className="px-3 py-2 font-mono text-xs" style={{ color: 'var(--t-text, #c8d8ee)' }}>{iface.hostname}</td>
                          <td className="px-3 py-2"><span style={statusStyle(iface.status)} className="font-mono text-xs">{iface.status.toUpperCase()}</span></td>
                          <td className="px-3 py-2 font-mono text-xs" style={{ color: 'var(--t-muted, #8899bb)' }}>{fmtBytes(iface.traffic_in)}</td>
                          <td className="px-3 py-2 font-mono text-xs" style={{ color: 'var(--t-muted, #8899bb)' }}>{fmtBytes(iface.traffic_out)}</td>
                          <td className="px-3 py-2 font-mono text-xs" style={{ color: 'var(--t-muted, #8899bb)' }}>{iface.speed ?? '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
            }
          </div>

          {/* Errors */}
          {d.interfaces.interfaces_with_errors.length > 0 && (
            <div className="mb-4">
              <div className="font-mono text-[10px] font-semibold mb-2 uppercase tracking-wider" style={{ color: '#ff6644' }}>Interfaces with Errors</div>
              <DeviceTable rows={d.interfaces.interfaces_with_errors.map(i => ({ device_id: i.device_id, hostname: `${i.name} @ ${i.hostname}`, ip: String(i.packet_errors), status: i.status }))} cols={[
                { key: 'hostname',      label: 'Interface @ Device' },
                { key: 'ip',           label: 'Errors', render: r => <span style={{ color: '#ff6644' }}>{r.ip}</span> },
                { key: 'status',       label: 'Status', render: r => <span style={statusStyle(r.status ?? '')}>{r.status}</span> },
              ]}/>
            </div>
          )}

          {/* Down interfaces */}
          {d.interfaces.down_interfaces.length > 0 && (
            <div>
              <div className="font-mono text-[10px] font-semibold mb-2 uppercase tracking-wider" style={{ color: '#ff3366' }}>Down Interfaces</div>
              <div className="flex flex-wrap gap-2">
                {d.interfaces.down_interfaces.map((i, idx) => (
                  <span key={idx} className="font-mono text-[10px] px-2 py-0.5 rounded"
                    style={{ background: 'rgba(255,51,102,0.1)', color: '#ff3366', border: '1px solid rgba(255,51,102,0.25)' }}>
                    {i.name} @ {(i as unknown as {device: string}).device || '—'}
                  </span>
                ))}
              </div>
            </div>
          )}
        </GlassCard>

        {/* ══ SECTION 4 — ALERTS & EVENTS ════════════════════════════════ */}
        <GlassCard className="p-5 print-page">
          <SectionTitle icon="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" title="4. Alerts & Events" subtitle="Alert summary for the last 24 hours"/>
          <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-3 mb-5">
            <StatTile label="Total Alerts"   value={d.alerts.total_alerts_24h} color="#00d4ff"/>
            <StatTile label="Critical" value={d.alerts.critical} color={d.alerts.critical > 0 ? '#ff3366' : 'var(--t-muted, #8899bb)'}/>
            <StatTile label="High"     value={d.alerts.high}     color={d.alerts.high > 0     ? '#ff6644' : 'var(--t-muted, #8899bb)'}/>
            <StatTile label="Warning"  value={d.alerts.warning}  color={d.alerts.warning > 0  ? '#ffaa00' : 'var(--t-muted, #8899bb)'}/>
            <StatTile label="Resolved" value={d.alerts.resolved} color="#00ff88"/>
            <StatTile label="Open"     value={d.alerts.open}     color={d.alerts.open > 0     ? '#ffaa00' : 'var(--t-muted, #8899bb)'}/>
          </div>

          {/* Recent alerts table */}
          {d.alerts.recent_alerts.length > 0 ? (
            <div className="overflow-x-auto mb-4">
              <div className="font-mono text-[10px] font-semibold mb-2 uppercase tracking-wider" style={{ color: 'var(--t-muted, #667799)' }}>Recent Alerts (Last 20)</div>
              <table className="w-full" style={{ minWidth: 600 }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid rgba(0,212,255,0.1)' }}>
                    {['Severity','Title','Device','Status','Time'].map(h => (
                      <th key={h} className="text-left px-3 py-2 font-mono text-[10px] uppercase" style={{ color: 'var(--t-muted, #8899bb)' }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {d.alerts.recent_alerts.map((a, i) => (
                    <tr key={i} style={{ borderBottom: '1px solid rgba(0,212,255,0.05)' }}>
                      <td className="px-3 py-2"><SevBadge sev={a.severity}/></td>
                      <td className="px-3 py-2 font-mono text-xs max-w-xs truncate" style={{ color: 'var(--t-text, #c8d8ee)' }}>{a.title}</td>
                      <td className="px-3 py-2 font-mono text-xs" style={{ color: 'var(--t-muted, #8899bb)' }}>{a.hostname}</td>
                      <td className="px-3 py-2 font-mono text-xs" style={{ color: a.status === 'resolved' ? '#00ff88' : '#ffaa00' }}>{a.status}</td>
                      <td className="px-3 py-2 font-mono text-xs whitespace-nowrap" style={{ color: 'var(--t-muted, #8899bb)' }}>{ts(a.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="font-mono text-xs mb-4" style={{ color: 'var(--t-muted, #8899bb)' }}>Data Not Available</div>
          )}

          {/* Events summary */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <div className="font-mono text-[10px] font-semibold mb-2 uppercase tracking-wider" style={{ color: 'var(--t-muted, #667799)' }}>Event Types (24h) — Total: {d.alerts.total_events_24h}</div>
              {Object.entries(d.alerts.event_types).length > 0
                ? <div className="space-y-1.5">
                    {Object.entries(d.alerts.event_types).map(([type, count]) => (
                      <div key={type} className="flex items-center justify-between font-mono text-xs">
                        <span style={{ color: 'var(--t-text, #c8d8ee)' }}>{type.replace(/_/g, ' ')}</span>
                        <span className="px-2 py-0.5 rounded" style={{ background: 'rgba(0,212,255,0.1)', color: '#00d4ff' }}>{count}</span>
                      </div>
                    ))}
                  </div>
                : <div className="font-mono text-xs" style={{ color: 'var(--t-muted, #8899bb)' }}>No events</div>
              }
            </div>
            <div>
              <div className="font-mono text-[10px] font-semibold mb-2 uppercase tracking-wider" style={{ color: 'var(--t-muted, #667799)' }}>Top Alert-Generating Devices</div>
              {d.alerts.top_alert_devices.length > 0
                ? <DeviceTable rows={d.alerts.top_alert_devices} cols={[
                    { key: 'hostname', label: 'Device' },
                    { key: 'ip',      label: 'IP' },
                    { key: 'count',   label: 'Alerts', render: r => <span style={{ color: '#ff3366' }}>{r.count}</span> },
                  ]}/>
                : <div className="font-mono text-xs" style={{ color: 'var(--t-muted, #8899bb)' }}>Data Not Available</div>
              }
            </div>
          </div>
        </GlassCard>

        {/* ══ SECTION 5 — INCIDENTS & STATUS HISTORY ═════════════════════ */}
        <GlassCard className="p-5 print-page">
          <SectionTitle
            icon="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
            title="5. Incidents & Problems"
            subtitle="Device status transitions in the last 24 hours"
          />
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mb-5">
            <StatTile label="Total Changes"  value={d.incidents.total_status_changes} color="#00d4ff"/>
            <StatTile label="Went Offline"   value={d.incidents.went_offline}          color={d.incidents.went_offline > 0 ? '#ff3366' : 'var(--t-muted, #8899bb)'}/>
            <StatTile label="Came Online"    value={d.incidents.came_online}           color="#00ff88"/>
          </div>

          {d.incidents.changes.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full" style={{ minWidth: 560 }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid rgba(0,212,255,0.1)' }}>
                    {['Device','IP','Previous Status','New Status','Reason','Time'].map(h => (
                      <th key={h} className="text-left px-3 py-2 font-mono text-[10px] uppercase" style={{ color: 'var(--t-muted, #8899bb)' }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {d.incidents.changes.map((c, i) => (
                    <tr key={i} style={{ borderBottom: '1px solid rgba(0,212,255,0.05)' }}>
                      <td className="px-3 py-2 font-mono text-xs" style={{ color: 'var(--t-text, #c8d8ee)' }}>{c.hostname}</td>
                      <td className="px-3 py-2 font-mono text-xs" style={{ color: 'var(--t-muted, #8899bb)' }}>{c.ip}</td>
                      <td className="px-3 py-2 font-mono text-xs" style={statusStyle(c.old_status ?? '')}>{c.old_status ?? '—'}</td>
                      <td className="px-3 py-2 font-mono text-xs" style={statusStyle(c.new_status)}>{c.new_status}</td>
                      <td className="px-3 py-2 font-mono text-xs" style={{ color: 'var(--t-muted, #8899bb)' }}>{c.reason ?? '—'}</td>
                      <td className="px-3 py-2 font-mono text-xs whitespace-nowrap" style={{ color: 'var(--t-muted, #8899bb)' }}>{ts(c.timestamp)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="font-mono text-xs py-3 px-4 rounded-lg"
              style={{ background: 'rgba(0,255,136,0.06)', border: '1px solid rgba(0,255,136,0.2)', color: '#00ff88' }}>
              ✓ No status changes recorded in the last 24 hours.
            </div>
          )}
        </GlassCard>

        {/* ══ SECTION 6 — TOP / BOTTOM PERFORMERS ════════════════════════ */}
        <GlassCard className="p-5 print-page">
          <SectionTitle
            icon="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6"
            title="6. Top Performers"
            subtitle="Devices ranked by CPU, memory, latency, downtime and alerts"
          />
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">

            {/* Top CPU */}
            <div>
              <div className="font-mono text-[10px] font-semibold mb-2 uppercase tracking-wider" style={{ color: '#ff6644' }}>Top CPU Usage</div>
              {d.top_performers.top_cpu.length === 0
                ? <div className="font-mono text-xs" style={{ color: 'var(--t-muted, #8899bb)' }}>Data Not Available</div>
                : <div className="space-y-2.5">
                    {d.top_performers.top_cpu.map((r, i) => (
                      <div key={i}>
                        <div className="flex justify-between font-mono text-[10px] mb-0.5">
                          <span className="truncate max-w-[130px]" style={{ color: 'var(--t-text, #c8d8ee)' }}>{r.hostname}</span>
                          <span style={{ color: r.avg_value! > 80 ? '#ff3366' : '#ffaa00' }}>{r.avg_value?.toFixed(1)}%</span>
                        </div>
                        <MiniBar pct={r.avg_value ?? 0} color="#ff6644"/>
                        <div className="font-mono text-[9px] mt-0.5" style={{ color: 'var(--t-muted, #556677)' }}>Max: {r.max_value?.toFixed(1)}% — {r.ip}</div>
                      </div>
                    ))}
                  </div>
              }
            </div>

            {/* Top Memory */}
            <div>
              <div className="font-mono text-[10px] font-semibold mb-2 uppercase tracking-wider" style={{ color: '#b366ff' }}>Top Memory Usage</div>
              {d.top_performers.top_memory.length === 0
                ? <div className="font-mono text-xs" style={{ color: 'var(--t-muted, #8899bb)' }}>Data Not Available</div>
                : <div className="space-y-2.5">
                    {d.top_performers.top_memory.map((r, i) => (
                      <div key={i}>
                        <div className="flex justify-between font-mono text-[10px] mb-0.5">
                          <span className="truncate max-w-[130px]" style={{ color: 'var(--t-text, #c8d8ee)' }}>{r.hostname}</span>
                          <span style={{ color: r.avg_value! > 85 ? '#ff3366' : '#b366ff' }}>{r.avg_value?.toFixed(1)}%</span>
                        </div>
                        <MiniBar pct={r.avg_value ?? 0} color="#b366ff"/>
                        <div className="font-mono text-[9px] mt-0.5" style={{ color: 'var(--t-muted, #556677)' }}>Max: {r.max_value?.toFixed(1)}% — {r.ip}</div>
                      </div>
                    ))}
                  </div>
              }
            </div>

            {/* Top Latency */}
            <div>
              <div className="font-mono text-[10px] font-semibold mb-2 uppercase tracking-wider" style={{ color: '#00d4ff' }}>Top Latency</div>
              {d.top_performers.top_latency.length === 0
                ? <div className="font-mono text-xs" style={{ color: 'var(--t-muted, #8899bb)' }}>Data Not Available</div>
                : <div className="space-y-2.5">
                    {d.top_performers.top_latency.map((r, i) => (
                      <div key={i}>
                        <div className="flex justify-between font-mono text-[10px] mb-0.5">
                          <span className="truncate max-w-[130px]" style={{ color: 'var(--t-text, #c8d8ee)' }}>{r.hostname}</span>
                          <span style={{ color: r.avg_value! > 100 ? '#ff3366' : '#00d4ff' }}>{ms(r.avg_value)}</span>
                        </div>
                        <MiniBar pct={Math.min((r.avg_value ?? 0) / 3, 100)} color="#00d4ff"/>
                        <div className="font-mono text-[9px] mt-0.5" style={{ color: 'var(--t-muted, #556677)' }}>Max: {ms(r.max_value)} — {r.ip}</div>
                      </div>
                    ))}
                  </div>
              }
            </div>

            {/* Max Downtime */}
            <div>
              <div className="font-mono text-[10px] font-semibold mb-2 uppercase tracking-wider" style={{ color: '#ff3366' }}>Max Downtime</div>
              {d.top_performers.max_downtime.length === 0
                ? <div className="font-mono text-xs py-2" style={{ color: 'var(--t-muted, #8899bb)' }}>No downtime recorded ✓</div>
                : <DeviceTable rows={d.top_performers.max_downtime} cols={[
                    { key: 'hostname', label: 'Device' },
                    { key: 'ip',       label: 'IP' },
                    { key: 'downtime', label: 'Duration', render: r => <span style={{ color: '#ff3366' }}>{fmtSec(r.downtime_sec ?? 0)}</span> },
                  ]}/>
              }
            </div>

            {/* Max Alerts */}
            <div>
              <div className="font-mono text-[10px] font-semibold mb-2 uppercase tracking-wider" style={{ color: '#ffaa00' }}>Most Alerts</div>
              {d.top_performers.max_alerts.length === 0
                ? <div className="font-mono text-xs" style={{ color: 'var(--t-muted, #8899bb)' }}>Data Not Available</div>
                : <DeviceTable rows={d.top_performers.max_alerts} cols={[
                    { key: 'hostname', label: 'Device' },
                    { key: 'ip',       label: 'IP' },
                    { key: 'alerts',   label: 'Alerts', render: r => <span style={{ color: '#ffaa00' }}>{r.alerts ?? r.count}</span> },
                  ]}/>
              }
            </div>

          </div>
        </GlassCard>

        {/* ══ SECTION 7 — DAILY SUMMARY ══════════════════════════════════ */}
        <GlassCard className="p-5 print-page">
          <SectionTitle
            icon="M9 12l2 2 4-4M7.835 4.697a3.42 3.42 0 001.946-.806 3.42 3.42 0 014.438 0 3.42 3.42 0 001.946.806 3.42 3.42 0 013.138 3.138 3.42 3.42 0 00.806 1.946 3.42 3.42 0 010 4.438 3.42 3.42 0 00-.806 1.946 3.42 3.42 0 01-3.138 3.138 3.42 3.42 0 00-1.946.806 3.42 3.42 0 01-4.438 0 3.42 3.42 0 00-1.946-.806 3.42 3.42 0 01-3.138-3.138 3.42 3.42 0 00-.806-1.946 3.42 3.42 0 010-4.438 3.42 3.42 0 00.806-1.946 3.42 3.42 0 013.138-3.138z"
            title="7. Daily Summary"
            subtitle="Overall network health and key observations"
          />

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-5">

            {/* Health gauge + scores */}
            <div className="flex flex-col items-center gap-3 py-2">
              <HealthGauge score={d.daily_summary.health_score} label={d.daily_summary.overall_health}/>
              <div className="w-full space-y-2">
                <div className="flex items-center justify-between font-mono text-xs">
                  <span style={{ color: 'var(--t-muted, #8899bb)' }}>Availability</span>
                  <span style={{ color: '#00d4ff' }}>{pct(d.daily_summary.availability_pct)}</span>
                </div>
                <MiniBar pct={d.daily_summary.availability_pct} color="#00d4ff"/>
                <div className="flex items-center justify-between font-mono text-xs mt-1">
                  <span style={{ color: 'var(--t-muted, #8899bb)' }}>Health Score</span>
                  <span style={{ color: healthColor }}>{d.daily_summary.health_score} / 100</span>
                </div>
                <MiniBar pct={d.daily_summary.health_score} color={healthColor}/>
              </div>
            </div>

            {/* Issues list */}
            <div>
              <div className="font-mono text-[10px] font-semibold mb-3 uppercase tracking-wider" style={{ color: 'var(--t-muted, #667799)' }}>Issues Observed</div>
              <div className="space-y-2">
                {d.daily_summary.issues.map((issue, i) => {
                  const isGood = issue.startsWith('No major')
                  return (
                    <div key={i} className="flex items-start gap-2 font-mono text-xs p-2 rounded"
                      style={{
                        background: isGood ? 'rgba(0,255,136,0.06)' : 'rgba(255,170,0,0.06)',
                        border: `1px solid ${isGood ? 'rgba(0,255,136,0.2)' : 'rgba(255,170,0,0.2)'}`,
                      }}>
                      <span style={{ color: isGood ? '#00ff88' : '#ffaa00', marginTop: 1 }}>{isGood ? '✓' : '⚠'}</span>
                      <span style={{ color: 'var(--t-text, #c8d8ee)' }}>{issue}</span>
                    </div>
                  )
                })}
              </div>
            </div>

            {/* Devices needing attention */}
            <div>
              <div className="font-mono text-[10px] font-semibold mb-3 uppercase tracking-wider" style={{ color: 'var(--t-muted, #667799)' }}>Devices Needing Attention</div>
              {d.daily_summary.devices_needing_attention.length === 0
                ? <div className="font-mono text-xs py-2 px-3 rounded"
                    style={{ background: 'rgba(0,255,136,0.06)', border: '1px solid rgba(0,255,136,0.2)', color: '#00ff88' }}>
                    ✓ No devices need immediate attention.
                  </div>
                : <div className="space-y-1.5">
                    {d.daily_summary.devices_needing_attention.map((dev, i) => (
                      <div key={i} className="flex items-center justify-between p-2 rounded"
                        style={{ background: 'rgba(255,51,102,0.06)', border: '1px solid rgba(255,51,102,0.2)' }}>
                        <div>
                          <div className="font-mono text-xs font-semibold" style={{ color: 'var(--t-text, #c8d8ee)' }}>{dev.hostname}</div>
                          <div className="font-mono text-[9px]" style={{ color: 'var(--t-muted, #8899bb)' }}>{dev.ip}</div>
                        </div>
                        <div className="text-right">
                          <span style={statusStyle(dev.status ?? '')} className="font-mono text-[10px]">{dev.status}</span>
                          <div className="font-mono text-[9px] mt-0.5" style={{ color: 'var(--t-muted, #8899bb)' }}>{dev.reason}</div>
                        </div>
                      </div>
                    ))}
                  </div>
              }
            </div>

          </div>
        </GlassCard>

        {/* ══ SECTION 8 — RECOMMENDATIONS ════════════════════════════════ */}
        <GlassCard className="p-5 print-page">
          <SectionTitle
            icon="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"
            title="8. Recommendations"
            subtitle="Actionable items for Network / IT Operations team"
          />

          <div className="space-y-3">
            {d.recommendations.map((rec, i) => {
              const sev = SEV[rec.priority.toUpperCase()] ?? SEV.INFO
              return (
                <div key={i} className="flex items-start gap-3 p-4 rounded-lg"
                  style={{ background: sev.bg, border: `1px solid ${sev.border}` }}>
                  <div className="shrink-0 mt-0.5">
                    <SevBadge sev={rec.priority}/>
                  </div>
                  <div className="font-mono text-xs leading-relaxed" style={{ color: 'var(--t-text, #c8d8ee)' }}>{rec.message}</div>
                </div>
              )
            })}
          </div>

          {/* Footer */}
          <div className="mt-6 pt-4 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2"
            style={{ borderTop: '1px solid rgba(0,212,255,0.1)' }}>
            <div className="font-mono text-[10px]" style={{ color: 'var(--t-muted, #556677)' }}>
              Generated by NMS Pro · Agnigate Networks · {ts(d.generated_at)}
            </div>
            <div className="font-mono text-[10px]" style={{ color: 'var(--t-muted, #556677)' }}>
              Report Period: {d.period}
            </div>
          </div>
        </GlassCard>

      </div>{/* end max-w-7xl wrapper */}
    </>
  )
}
