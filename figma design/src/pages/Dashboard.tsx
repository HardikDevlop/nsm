import { useEffect, useMemo, useState } from 'react'
import GlassCard from '../components/GlassCard'
import { getOverview, type DeviceRecord } from '../lib/api'

type Point = { label: string; up: number; down: number }

const COLORS = {
  cyan: '#00d4ff',
  green: '#00ff88',
  red: '#ff3366',
  muted: '#8899bb',
  bg: 'rgba(0,212,255,0.05)',
}

function countStatus<T extends { status?: string }>(items: T[]) {
  const up = items.filter(item => String(item.status ?? '').toLowerCase() === 'online' || String(item.status ?? '').toLowerCase() === 'up' || String(item.status ?? '').toLowerCase() === 'active').length
  return { up, down: Math.max(0, items.length - up), total: items.length }
}

function Sparkline({ points, accent = COLORS.cyan }: { points: Point[]; accent?: string }) {
  const width = 220
  const height = 72
  const values = points.flatMap(point => [point.up, point.down])
  const max = Math.max(1, ...values)
  const step = points.length > 1 ? width / (points.length - 1) : width
  const upPath = points
    .map((point, index) => `${index === 0 ? 'M' : 'L'} ${index * step} ${height - (point.up / max) * (height - 16) - 8}`)
    .join(' ')
  const downPath = points
    .map((point, index) => `${index === 0 ? 'M' : 'L'} ${index * step} ${height - (point.down / max) * (height - 16) - 8}`)
    .join(' ')

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-20">
      <defs>
        <linearGradient id={`g-${accent.replace('#', '')}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={accent} stopOpacity="0.35" />
          <stop offset="100%" stopColor={accent} stopOpacity="0.02" />
        </linearGradient>
      </defs>
      <path d={`${upPath} L ${width} ${height - 8} L 0 ${height - 8} Z`} fill={`url(#g-${accent.replace('#', '')})`} />
      <path d={upPath} fill="none" stroke={accent} strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
      <path d={downPath} fill="none" stroke={COLORS.red} strokeWidth="1.6" strokeLinecap="round" strokeDasharray="4 4" />
    </svg>
  )
}

function StatusCard({
  title,
  subtitle,
  total,
  up,
  down,
  points,
}: {
  title: string
  subtitle: string
  total: number
  up: number
  down: number
  points: Point[]
}) {
  return (
    <GlassCard className="p-4 md:p-5">
      <div className="flex items-start justify-between gap-3 mb-3">
        <div>
          <div className="font-display font-bold text-lg tracking-widest neon-cyan">{title}</div>
          <div className="font-mono text-xs mt-1" style={{ color: COLORS.muted }}>{subtitle}</div>
        </div>
        <div className="text-right">
          <div className="font-display text-2xl leading-none" style={{ color: COLORS.green }}>{total}</div>
          <div className="font-mono text-[10px] mt-1" style={{ color: COLORS.muted }}>TOTAL</div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 mb-4">
        <MiniStat label="UP" value={up} color={COLORS.green} />
        <MiniStat label="DOWN" value={down} color={COLORS.red} />
      </div>

      <Sparkline points={points} />
    </GlassCard>
  )
}

function MiniStat({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className="rounded-lg p-3" style={{ background: COLORS.bg, border: '1px solid rgba(0,212,255,0.12)' }}>
      <div className="font-mono text-[10px]" style={{ color: COLORS.muted }}>{label}</div>
      <div className="font-display text-xl mt-1" style={{ color }}>{value}</div>
    </div>
  )
}

export default function Dashboard() {
  const [icmpDevices, setIcmpDevices] = useState<DeviceRecord[]>([])
  const [icmpHistory, setIcmpHistory] = useState<Point[]>([])
  const [snmpHistory, setSnmpHistory] = useState<Point[]>([])
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = async (quiet = false) => {
    if (!quiet) setLoading(true)
    setError(null)
    try {
      const overview = await getOverview()
      const icmp = overview.devices.map(device => ({
        ...device,
        status: device.status ?? 'unknown',
      }))
      setIcmpDevices(icmp)

      const icmpCount = countStatus(icmp)
      const snmpCount = {
        up: icmp.filter(device => Boolean(device.snmp_version)).length,
        down: Math.max(0, icmp.length - icmp.filter(device => Boolean(device.snmp_version)).length),
      }
      const stamp = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
      setIcmpHistory(prev => [...prev.slice(-11), { label: stamp, up: icmpCount.up, down: icmpCount.down }])
      setSnmpHistory(prev => [...prev.slice(-11), { label: stamp, up: snmpCount.up, down: snmpCount.down }])
      setUpdatedAt(new Date())
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Unable to load dashboard')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
    const timer = window.setInterval(() => void load(true), 15_000)
    return () => window.clearInterval(timer)
  }, [])

  const icmp = useMemo(() => countStatus(icmpDevices), [icmpDevices])
  const snmp = useMemo(() => {
    const configured = icmpDevices.filter(device => Boolean(device.snmp_version)).length
    return { up: configured, down: Math.max(0, icmpDevices.length - configured), total: icmpDevices.length }
  }, [icmpDevices])

  return (
    <div className="p-4 md:p-6 space-y-5" style={{ background: 'radial-gradient(circle at top, rgba(0,212,255,0.06), transparent 40%)' }}>
      <div className="flex flex-col lg:flex-row lg:items-end justify-between gap-3">
        <div>
          <h1 className="font-display font-bold text-2xl md:text-3xl tracking-widest neon-cyan">DASHBOARD</h1>
          <p className="font-mono text-xs mt-1" style={{ color: COLORS.muted }}>
            ICMP and SNMP device health in one clean view
            {updatedAt ? ` • Updated ${updatedAt.toLocaleTimeString()}` : ''}
          </p>
        </div>
        <button
          type="button"
          onClick={() => void load()}
          disabled={loading}
          className="font-mono text-xs px-3 py-2 rounded glass-bright"
          style={{ border: '1px solid rgba(0,212,255,0.24)', color: COLORS.cyan, opacity: loading ? 0.6 : 1 }}
        >
          {loading ? 'LOADING…' : 'REFRESH'}
        </button>
      </div>

      {error && (
        <div className="font-mono text-xs rounded p-3" style={{ color: COLORS.red, background: 'rgba(255,51,102,0.08)', border: '1px solid rgba(255,51,102,0.2)' }}>
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <StatusCard
          title="ICMP"
          subtitle="Reachability status based on live ping checks"
          total={icmp.total}
          up={icmp.up}
          down={icmp.down}
          points={icmpHistory}
        />

        <StatusCard
          title="SNMP"
          subtitle="Devices with SNMP visibility and monitoring enabled"
          total={snmp.total}
          up={snmp.up}
          down={snmp.down}
          points={snmpHistory}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <GlassCard className="p-4 md:p-5">
          <div className="font-display font-bold text-base tracking-widest neon-cyan mb-3">ICMP DEVICE LIST</div>
          <div className="space-y-2 max-h-[320px] overflow-auto pr-1">
            {icmpDevices.slice(0, 8).map(device => (
              <DeviceRow
                key={device.id}
                name={device.hostname}
                ip={device.ip_address}
                status={device.status}
              />
            ))}
            {icmpDevices.length === 0 && <EmptyState text="No ICMP devices found" />}
          </div>
        </GlassCard>

        <GlassCard className="p-4 md:p-5">
          <div className="font-display font-bold text-base tracking-widest neon-cyan mb-3">SNMP DEVICE LIST</div>
          <div className="space-y-2 max-h-[320px] overflow-auto pr-1">
            {icmpDevices.filter(device => String(device.snmp_version ?? '').length > 0).slice(0, 8).map(device => (
              <DeviceRow
                key={device.id}
                name={device.hostname}
                ip={device.ip_address}
                status="online"
              />
            ))}
            {icmpDevices.filter(device => String(device.snmp_version ?? '').length > 0).length === 0 && <EmptyState text="No SNMP devices found" />}
          </div>
        </GlassCard>

        <GlassCard className="p-4 md:p-5">
          <div className="font-display font-bold text-base tracking-widest neon-cyan mb-3">QUICK SUMMARY</div>
          <div className="space-y-3">
            <SummaryLine label="ICMP Online" value={icmp.up} total={icmp.total} />
            <SummaryLine label="ICMP Offline" value={icmp.down} total={icmp.total} accent={COLORS.red} />
            <SummaryLine label="SNMP Configured" value={snmp.up} total={snmp.total} />
            <SummaryLine label="SNMP Unconfigured" value={snmp.down} total={snmp.total} accent={COLORS.red} />
          </div>
        </GlassCard>
      </div>
    </div>
  )
}

function DeviceRow({ name, ip, status }: { name: string; ip: string; status: string }) {
  const online = String(status).toLowerCase() === 'online' || String(status).toLowerCase() === 'up' || String(status).toLowerCase() === 'active'
  return (
    <div className="rounded-lg px-3 py-2 flex items-center justify-between gap-3" style={{ background: 'rgba(0,212,255,0.03)', border: '1px solid rgba(0,212,255,0.08)' }}>
      <div className="min-w-0">
        <div className="font-display text-sm tracking-wide truncate" style={{ color: '#dbeafe' }}>{name}</div>
        <div className="font-mono text-[11px] truncate" style={{ color: COLORS.muted }}>{ip}</div>
      </div>
      <span className="font-mono text-[10px] px-2 py-0.5 rounded" style={{ color: online ? COLORS.green : COLORS.red, background: online ? 'rgba(0,255,136,0.08)' : 'rgba(255,51,102,0.08)', border: `1px solid ${online ? 'rgba(0,255,136,0.18)' : 'rgba(255,51,102,0.18)'}` }}>
        {String(status).toUpperCase()}
      </span>
    </div>
  )
}

function SummaryLine({ label, value, total, accent = COLORS.green }: { label: string; value: number; total: number; accent?: string }) {
  return (
    <div>
      <div className="flex items-center justify-between font-mono text-xs mb-1" style={{ color: COLORS.muted }}>
        <span>{label}</span>
        <span style={{ color: accent }}>{value}/{total}</span>
      </div>
      <div className="h-2 rounded-full overflow-hidden" style={{ background: 'rgba(255,255,255,0.06)' }}>
        <div className="h-full rounded-full" style={{ width: `${total ? (value / total) * 100 : 0}%`, background: accent }} />
      </div>
    </div>
  )
}

function EmptyState({ text }: { text: string }) {
  return <div className="font-mono text-xs py-6 text-center" style={{ color: COLORS.muted }}>{text}</div>
}
