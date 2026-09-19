import { useEffect, useMemo, useState } from "react"
import { useNavigate } from "react-router"
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ResponsiveContainer,
  Tooltip,
  Treemap,
  XAxis,
  YAxis,
} from "recharts"
import GlassCard from "../components/GlassCard"
import { useI18n } from "../i18n/I18nContext"
import {
  getOverview,
  type NormalizedOverview,
  type OverviewResponse,
} from "../lib/api"
import { formatISTTime, parseISTDate } from "../time"

/* ─────────────────────────────  THEME  ───────────────────────────── */
const C = {
  cyan: "#00d4ff",
  green: "#00ff88",
  red: "#ff3366",
  amber: "#ffaa00",
  purple: "#8b5cf6",
  pink: "#ec4899",
  orange: "#ff6b35",
  blue: "#3b82f6",
  teal: "#14b8a6",
  lime: "#a3e635",
  muted: "var(--t-muted, #8899bb)",
}

const PALETTE = [
  "#00d4ff", "#00ff88", "#ffaa00", "#ff3366", "#8b5cf6",
  "#ec4899", "#ff6b35", "#3b82f6", "#14b8a6", "#a3e635",
  "#f472b6", "#22d3ee", "#facc15", "#fb7185", "#c084fc",
]

const fmt = (n: number | null | undefined, suffix = "") =>
  n == null || Number.isNaN(n) ? "N/A" : `${n.toFixed(n < 10 ? 1 : 0)}${suffix}`

const formatTraffic = (n: number | null | undefined) => {
  if (n == null || !Number.isFinite(Number(n))) return "N/A"
  const raw = Number(n)
  // Stored interface rates can come from the collector as bps while older
  // records are already normalized to Mbps. Treat very large values as bps
  // so the dashboard never presents impossible multi-thousand-Tbps readings.
  const mbps = Math.abs(raw) >= 1_000_000 ? raw / 1_000_000 : raw
  const absolute = Math.abs(mbps)
  if (absolute >= 1_000_000) return `${(mbps / 1_000_000).toFixed(1)} Tbps`
  if (absolute >= 1000) return `${(mbps / 1000).toFixed(1)} Gbps`
  if (absolute >= 1) return `${mbps.toFixed(1)} Mbps`
  return `${(mbps * 1000).toFixed(1)} Kbps`
}

const clock = (s?: string | null) =>
  s
    ? formatISTTime(s)
    : "N/A"

/* ─────────────────────────────  PRIMITIVES  ───────────────────────────── */
function Badge({ label, tone = "cyan" }: { label: string; tone?: keyof typeof C }) {
  const color = C[tone] as string
  return (
    <span
      className="font-mono text-[10px] uppercase px-2 py-1 rounded transition-all duration-300 hover:scale-105"
      style={{
        color,
        background: `${color}14`,
        border: `1px solid ${color}45`,
        boxShadow: `0 0 12px ${color}22`,
      }}
    >
      {label}
    </span>
  )
}

function SectionLabel({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-3 mt-2 mb-1 select-none">
      <span
        className="font-mono text-[10px] uppercase tracking-[0.25em] whitespace-nowrap"
        style={{ color: C.cyan, textShadow: `0 0 10px ${C.cyan}55` }}
      >
        {label}
      </span>
      <span
        className="h-px flex-1"
        style={{
          background: `linear-gradient(90deg, ${C.cyan}55, transparent)`,
        }}
      />
    </div>
  )
}

function Empty({ text = "No stored data available" }: { text?: string }) {
  return (
    <div
      className="font-mono text-xs py-10 text-center flex flex-col items-center gap-2"
      style={{ color: C.muted }}
    >
      <span
        className="h-8 w-8 rounded-full flex items-center justify-center"
        style={{ border: `1px dashed ${C.muted}66` }}
      >
        ∅
      </span>
      {text}
    </div>
  )
}

function Metric({
  label, number, hint, tone = "cyan", onClick,
}: {
  label: string
  number: string | number
  hint: string
  tone?: "cyan" | "green" | "red" | "amber"
  onClick?: () => void
}) {
  const color = C[tone]
  return (
    <GlassCard
      className="p-4 transition-all duration-500 hover:-translate-y-1.5 hover:shadow-2xl cursor-pointer group relative overflow-hidden"
      onClick={onClick}
      role={onClick ? "button" : undefined}
      tabIndex={onClick ? 0 : undefined}
    >
      {/* shimmer overlay */}
      <div
        className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-500 pointer-events-none"
        style={{
          background: `radial-gradient(circle at 50% 0%, ${color}22, transparent 70%)`,
        }}
      />
      {/* accent edge so each metric reads as its own signal, not a grey tile */}
      <div
        className="absolute inset-x-0 top-0 h-[2px] opacity-70"
        style={{ background: `linear-gradient(90deg, transparent, ${color}, transparent)` }}
      />
      <div
        className="flex justify-between font-mono text-[10px] uppercase tracking-widest relative"
        style={{ color: C.muted }}
      >
        <span>{label}</span>
        <i
          className="status-dot animate-pulse"
          style={{ background: color, boxShadow: `0 0 10px ${color}` }}
        />
      </div>
      <div
        className="font-display text-3xl mt-3 transition-transform duration-500 group-hover:scale-110 relative"
        style={{ color, textShadow: `0 0 20px ${color}66` }}
      >
        {number}
      </div>
      <div className="font-mono text-[10px] mt-1 relative" style={{ color: C.muted }}>
        {hint}
      </div>
    </GlassCard>
  )
}

function Panel({
  title, subtitle, children, onClick, className = "",
}: {
  title: string
  subtitle?: string
  children: React.ReactNode
  onClick?: () => void
  className?: string
}) {
  return (
    <GlassCard
      className={`p-4 md:p-5 transition-all duration-500 hover:border-cyan-400/40 animate-fadeIn group/panel ${className}`}
      onClick={onClick}
      role={onClick ? "button" : undefined}
      tabIndex={onClick ? 0 : undefined}
    >
      <div className="flex justify-between gap-3 mb-4">
        <div>
          <h2 className="font-display font-bold text-base tracking-widest neon-cyan">
            {title}
          </h2>
          {subtitle && (
            <p className="font-mono text-[10px] mt-1" style={{ color: C.muted }}>
              {subtitle}
            </p>
          )}
        </div>
        {onClick && (
          <span
            className="font-mono text-[10px] transition-transform duration-300 group-hover/panel:translate-x-1"
            style={{ color: C.cyan }}
          >
            OPEN →
          </span>
        )}
      </div>
      {children}
    </GlassCard>
  )
}

function BarLine({
  label, current, total, tone = C.green,
}: {
  label: string
  current: number
  total: number
  tone?: string
}) {
  const pct = total ? Math.min(100, (current / total) * 100) : 0
  return (
    <div>
      <div className="flex justify-between font-mono text-xs mb-1" style={{ color: C.muted }}>
        <span>{label}</span>
        <span style={{ color: tone }}>{current}/{total}</span>
      </div>
      <div className="h-2 rounded-full overflow-hidden" style={{ background: "rgba(255,255,255,.07)" }}>
        <div
          className="h-full rounded-full transition-all duration-1000 ease-out"
          style={{
            width: `${pct}%`,
            background: `linear-gradient(90deg, ${tone}, ${tone}bb)`,
            boxShadow: `0 0 12px ${tone}88`,
          }}
        />
      </div>
    </div>
  )
}

function Mini({
  label, number, tone = C.cyan,
}: {
  label: string
  number: string | number
  tone?: string
}) {
  return (
    <div
      className="rounded-lg p-3 transition-all duration-300 hover:scale-105"
      style={{
        background: "rgba(0,212,255,.04)",
        border: "1px solid rgba(0,212,255,.12)",
      }}
    >
      <div className="font-mono text-[10px]" style={{ color: C.muted }}>{label}</div>
      <div className="font-display text-2xl" style={{ color: tone }}>{number}</div>
    </div>
  )
}

/* ═══════════════  🕐 CLOCK GAUGE — the star of the show  ═══════════════ */
function ClockGauge({
  value, max = 100, label, unit = "%", size = 180, valueLabel,
  tone = C.cyan, tickCount = 60, showTicks = true, showScale = false,
}: {
  value: number
  max?: number
  label: string
  unit?: string
  valueLabel?: string
  size?: number
  tone?: string
  tickCount?: number
  showTicks?: boolean
  showScale?: boolean
}) {
  // A non-numeric valueLabel ("NO DATA", "WAITING"...) means there's nothing
  // real to plot. Render a calm, static ring instead of a needle pointing at
  // a meaningless 0% — that's what was overlapping the "NO DATA" text.
  const isNoData = Boolean(valueLabel && !/^\d/.test(valueLabel))
  const pct = isNoData ? 0 : Math.max(0, Math.min(1, value / max))
  const [animatedPct, setAnimatedPct] = useState(0)
  useEffect(() => {
    if (isNoData) {
      setAnimatedPct(0)
      return
    }
    let frame = 0
    const started = performance.now()
    const duration = 1250
    const animate = (now: number) => {
      const progress = Math.min(1, (now - started) / duration)
      const eased = 1 - Math.pow(1 - progress, 3)
      setAnimatedPct(pct * eased)
      if (progress < 1) frame = requestAnimationFrame(animate)
    }
    frame = requestAnimationFrame(animate)
    return () => cancelAnimationFrame(frame)
  }, [pct, isNoData])

  const animatedValue = max * animatedPct
  const radius = size / 2 - 18
  const cx = size / 2
  const cy = size / 2
  const startAngle = 135
  const totalAngle = 270

  // Arc path helper
  const polarToCartesian = (angle: number, r: number) => {
    const rad = ((angle - 90) * Math.PI) / 180
    return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) }
  }

  const arcPath = (start: number, end: number, r: number) => {
    const s = polarToCartesian(start, r)
    const e = polarToCartesian(end, r)
    const largeArc = end - start <= 180 ? 0 : 1
    return `M ${s.x} ${s.y} A ${r} ${r} 0 ${largeArc} 1 ${e.x} ${e.y}`
  }

  const endAngle = startAngle + totalAngle * animatedPct

  return (
    <div className="flex flex-col items-center relative" style={{ width: size }}>
      <svg width={size} height={size} className="overflow-visible">
        {/* outer glow ring */}
        <circle
          cx={cx} cy={cy} r={radius + 8}
          fill="none" stroke={`${tone}18`} strokeWidth="1"
        />

        {/* background arc */}
        <path
          d={arcPath(startAngle, startAngle + totalAngle, radius)}
          fill="none"
          className="gauge-track"
          stroke="rgba(255,255,255,.08)"
          strokeWidth="10"
          strokeLinecap="round"
        />

        {/* progress arc */}
        <path
          d={arcPath(startAngle, endAngle, radius)}
          fill="none"
          stroke={tone}
          strokeWidth="10"
          strokeLinecap="round"
          style={{
            filter: `drop-shadow(0 0 8px ${tone})`,
            transition: "stroke-dasharray 1s ease-out",
          }}
        />

        {/* clock-like ticks */}
        {showTicks &&
          Array.from({ length: tickCount }).map((_, i) => {
            const angle = startAngle + (totalAngle / (tickCount - 1)) * i
            const isMajor = i % 5 === 0
            const inner = polarToCartesian(angle, radius - 16)
            const outer = polarToCartesian(angle, radius - (isMajor ? 10 : 12))
            const active = !isNoData && angle <= endAngle
            return (
              <line
                key={i}
                x1={inner.x} y1={inner.y}
                x2={outer.x} y2={outer.y}
                className="gauge-tick"
                stroke={active ? tone : "rgba(255,255,255,.18)"}
                strokeWidth={isMajor ? 2 : 1}
                strokeLinecap="round"
                style={{ transition: "stroke .4s ease" }}
              />
            )
          })}

        {/* needle — hidden in the no-data state so it never sits on top of the label */}
        {!isNoData && (() => {
          const tip = polarToCartesian(endAngle, radius - 24)
          const tail = polarToCartesian(endAngle + 180, 10)
          return (
            <>
              <line
                x1={tail.x} y1={tail.y} x2={tip.x} y2={tip.y}
                stroke={tone}
                strokeWidth="2.5"
                strokeLinecap="round"
                style={{ filter: `drop-shadow(0 0 6px ${tone})`, transition: "all 1s ease-out" }}
              />
              <circle cx={cx} cy={cy} r="6" fill={tone} style={{ filter: `drop-shadow(0 0 8px ${tone})` }} />
              <circle className="gauge-center" cx={cx} cy={cy} r="2.5" fill="#0a1428" />
            </>
          )
        })()}
        {isNoData && (
          <circle cx={cx} cy={cy} r="3" fill="rgba(255,255,255,.25)" />
        )}

        {/* min/max scale labels at the two ends of the arc — fills the dead
            space under the ring and gives the reading a frame of reference */}
        {showScale && (() => {
          const minPos = polarToCartesian(startAngle, radius + 16)
          const maxPos = polarToCartesian(startAngle + totalAngle, radius + 16)
          return (
            <>
              <text x={minPos.x} y={minPos.y} textAnchor="middle" dominantBaseline="middle" fontSize="9" fontFamily="monospace" fill="rgba(255,255,255,.32)">0</text>
              <text x={maxPos.x} y={maxPos.y} textAnchor="middle" dominantBaseline="middle" fontSize="9" fontFamily="monospace" fill="rgba(255,255,255,.32)">{max}</text>
            </>
          )
        })()}
      </svg>

      {/* center value */}
      <div
        className={`mt-2 font-display text-center ${isNoData ? "text-sm tracking-widest" : "text-2xl"}`}
        style={{
          color: isNoData ? "rgba(255,255,255,.4)" : tone,
          textShadow: isNoData ? "none" : `0 0 16px ${tone}88`,
        }}
      >
        {valueLabel ?? `${animatedValue.toFixed(animatedValue < 10 ? 1 : 0)}${unit}`}
      </div>
      <div className="font-mono text-[10px] mt-1 uppercase tracking-widest" style={{ color: C.muted }}>
        {label}
      </div>
    </div>
  )
}

/* ═══════════════  🎯 SPEEDOMETER GAUGE (semi-circle)  ═══════════════ */
function Speedometer({
  value, max = 100, label, unit = "%", tone = C.cyan, size = 130,
}: {
  value: number
  max?: number
  label: string
  unit?: string
  tone?: string
  size?: number
}) {
  const pct = Math.max(0, Math.min(1, value / max))
  const [animatedPct, setAnimatedPct] = useState(0)
  useEffect(() => {
    let frame = 0
    const started = performance.now()
    const duration = 1000
    const animate = (now: number) => {
      const progress = Math.min(1, (now - started) / duration)
      const eased = 1 - Math.pow(1 - progress, 3)
      setAnimatedPct(pct * eased)
      if (progress < 1) frame = requestAnimationFrame(animate)
    }
    frame = requestAnimationFrame(animate)
    return () => cancelAnimationFrame(frame)
  }, [pct])

  const cx = size / 2
  const cy = size / 2 + 8
  const radius = size / 2 - 14

  const polar = (angle: number, r: number) => {
    const rad = ((angle - 90) * Math.PI) / 180
    return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) }
  }
  const arc = (start: number, end: number, r: number) => {
    const s = polar(start, r)
    const e = polar(end, r)
    const large = end - start <= 180 ? 0 : 1
    return `M ${s.x} ${s.y} A ${r} ${r} 0 ${large} 1 ${e.x} ${e.y}`
  }

  const startAngle = 180
  const sweep = 180
  const endAngle = startAngle + sweep * animatedPct

  return (
    <div className="relative flex flex-col items-center" style={{ width: size, height: size * 1.34 }}>
      <svg width={size} height={size * 0.65} className="block shrink-0 overflow-visible">
        <path d={arc(startAngle, startAngle + sweep, radius)} fill="none" stroke="rgba(255,255,255,.08)" strokeWidth="9" strokeLinecap="round" />
        <path
          d={arc(startAngle, endAngle, radius)} fill="none" stroke={tone} strokeWidth="9" strokeLinecap="round"
          style={{ filter: `drop-shadow(0 0 8px ${tone})`, transition: "all 1s ease-out" }}
        />
        {/* ticks */}
        {Array.from({ length: 11 }).map((_, i) => {
          const a = startAngle + (sweep / 10) * i
          const inner = polar(a, radius - 15)
          const outer = polar(a, radius - 6)
          const active = a <= endAngle
          return <line key={i} x1={inner.x} y1={inner.y} x2={outer.x} y2={outer.y} stroke={active ? tone : "rgba(255,255,255,.2)"} strokeWidth={i % 5 === 0 ? 2 : 1} strokeLinecap="round" />
        })}
        {/* needle */}
        <line
          x1={cx} y1={cy}
          x2={polar(endAngle, radius - 20).x}
          y2={polar(endAngle, radius - 20).y}
          stroke={tone} strokeWidth="2.5" strokeLinecap="round"
          style={{ filter: `drop-shadow(0 0 6px ${tone})`, transition: "all 1s ease-out" }}
        />
        <circle cx={cx} cy={cy} r="6" fill={tone} style={{ filter: `drop-shadow(0 0 8px ${tone})` }} />
        <circle cx={cx} cy={cy} r="2.5" fill="#0a1428" />
      </svg>
      <div className="pointer-events-none absolute left-0 right-0 top-[116px] flex flex-col items-center text-center">
        <div className="font-display text-xl leading-none" style={{ color: tone, textShadow: `0 0 14px ${tone}88` }}>
          {(value * animatedPct / (pct || 1)).toFixed(value < 10 ? 1 : 0)}{unit}
        </div>
        <div className="mt-1 font-mono text-[9px] uppercase tracking-widest whitespace-nowrap" style={{ color: C.muted }}>{label}</div>
      </div>
    </div>
  )
}

/* ═══════════════  ✨ SPARKLINE (mini inline chart)  ═══════════════ */
function Sparkline({ data, tone = C.cyan }: { data: number[]; tone?: string }) {
  const chartData = data.map((v, i) => ({ i, v }))
  return (
    <div className="h-8 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={chartData}>
          <Line
            type="monotone" dataKey="v" stroke={tone} strokeWidth={2}
            dot={false} isAnimationActive
            style={{ filter: `drop-shadow(0 0 4px ${tone}88)` }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

function TrafficMiniChart({ data, dataKey, tone }: { data: Array<{ label: string; rx_mbps: number; tx_mbps: number }>; dataKey: "rx_mbps" | "tx_mbps"; tone: string }) {
  return <div className="h-[105px] w-full">
    <ResponsiveContainer width="100%" height="100%">
      <AreaChart data={data} margin={{ top: 8, right: 4, left: 2, bottom: 0 }}>
        <defs><linearGradient id={`mini-${dataKey}`} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={tone} stopOpacity={.35} /><stop offset="100%" stopColor={tone} stopOpacity={0} /></linearGradient></defs>
        <CartesianGrid stroke="rgba(148,163,184,.12)" vertical={false} />
        <XAxis dataKey="label" tick={{ fill: "var(--t-muted)", fontSize: 8 }} tickLine={false} axisLine={false} minTickGap={22} />
        <YAxis tick={{ fill: "var(--t-muted)", fontSize: 8 }} tickLine={false} axisLine={false} width={52} tickFormatter={(v) => formatTraffic(Number(v))} />
        <Tooltip content={<ChartTooltip formatter={(v: any) => formatTraffic(Number(v))} />} />
        <Area type="monotone" dataKey={dataKey} stroke={tone} fill={`url(#mini-${dataKey})`} strokeWidth={2} dot={false} activeDot={{ r: 4, fill: tone }} animationDuration={800} />
      </AreaChart>
    </ResponsiveContainer>
  </div>
}

/* ═══════════════  💠 Custom Tooltip  ═══════════════ */
function ChartTooltip({ active, payload, label, formatter }: any) {
  if (!active || !payload?.length) return null
  return (
    <div
      className="dashboard-tooltip rounded-lg px-3 py-2.5 shadow-2xl backdrop-blur-md animate-fadeIn"
      style={{
        background: "#071426",
        border: "1px solid rgba(67,168,255,.7)",
        boxShadow: "0 10px 28px rgba(15,23,42,.32), 0 0 20px rgba(0,150,255,.18)",
        minWidth: 118,
      }}
    >
      {label && (
        <div className="font-mono text-[10px] mb-1.5 uppercase tracking-wide" style={{ color: "#b9c9df" }}>{label}</div>
      )}
      {payload.map((p: any, i: number) => (
        <div key={i} className="font-mono text-xs flex items-center gap-2 whitespace-nowrap">
          <span className="inline-block w-2 h-2 rounded-full shrink-0" style={{ background: p.color || p.fill, boxShadow: `0 0 6px ${p.color || p.fill}` }} />
          <span style={{ color: "#dbeafe" }}>{p.name}:</span>
          <strong style={{ color: "#ffffff", fontWeight: 700 }}>
            {formatter ? formatter(p.value, p.name) : p.value}
          </strong>
        </div>
      ))}
    </div>
  )
}

/* ═══════════════  🗺 Custom Treemap content  ═══════════════ */
function TreemapCell(props: any) {
  const { x, y, width, height, name, value, index } = props
  const fill = PALETTE[index % PALETTE.length]
  const showText = width > 60 && height > 30
  return (
    <g>
      <rect
        x={x} y={y} width={width} height={height}
        style={{
          fill, stroke: "#0a1428", strokeWidth: 2,
          filter: `drop-shadow(0 0 6px ${fill}88)`,
          transition: "all .4s ease",
        }}
      />
      {showText && (
        <>
          <text x={x + 8} y={y + 20} fill="#0a1428" fontSize={11} fontFamily="monospace" fontWeight="bold">
            {name}
          </text>
          <text x={x + 8} y={y + 36} fill="#0a1428" fontSize={13} fontFamily="monospace" fontWeight="bold">
            {value}
          </text>
        </>
      )}
    </g>
  )
}

/* ─────────────────────────────  MAIN  ───────────────────────────── */
export default function Dashboard() {
  const navigate = useNavigate()
  const { t } = useI18n()
  const d = t.dashboard

  const [data, setData] = useState<OverviewResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [range, setRange] = useState("12H")
  const [updated, setUpdated] = useState<Date | null>(null)

  const load = async (quiet = false) => {
    if (!quiet) setLoading(true)
    try {
      setError(null)
      const hours = range === "1H" ? 1 : range === "6H" ? 6 : range === "12H" ? 12 : range === "7D" ? 168 : 24
      const snapshot = await getOverview(hours)
      setData(snapshot)
      setUpdated(new Date())
    } catch (e) {
      setError(e instanceof Error ? e.message : d.noStoredData)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") void load(true)
    }, 30000)
    return () => window.clearInterval(timer)
  }, [range])

  const n: NormalizedOverview | null = data?.normalized ?? null
  const rangeLabel = range === "1H" ? "Last 1 hour" : range === "6H" ? "Last 6 hours" : range === "12H" ? "Last 12 hours" : range === "7D" ? "Last 7 days" : "Last 24 hours"
  const devices = data?.devices ?? []
  const summary = data?.summary
  const snmpEnabled = devices.filter((d) => Boolean(d.snmp_version)).length

  const health = {
    online: summary?.health_counts?.online ?? summary?.online_devices ?? 0,
    offline: summary?.health_counts?.offline ?? summary?.offline_devices ?? 0,
    degraded: summary?.health_counts?.degraded ?? 0,
    stale: summary?.health_counts?.stale ?? 0,
    warning: summary?.health_counts?.degraded ?? summary?.warning_devices ?? 0,
    unknown: summary?.health_counts?.unknown ?? 0,
  }

  const perf = useMemo(
    () =>
      devices
        .map((d) => ({
          cpu: n?.devices[String(d.id)]?.cpu ?? d.cpu_usage,
          memory: n?.devices[String(d.id)]?.memory ?? d.memory_usage,
        }))
        .filter((x) => x.cpu != null || x.memory != null),
    [devices, n],
  )

  const avgCpu = useMemo(() => {
    const v = perf.map((x) => x.cpu).filter((x): x is number => x != null)
    return v.length ? v.reduce((a, b) => a + b, 0) / v.length : 0
  }, [perf])
  const avgMem = useMemo(() => {
    const v = perf.map((x) => x.memory).filter((x): x is number => x != null)
    return v.length ? v.reduce((a, b) => a + b, 0) / v.length : 0
  }, [perf])

  /* Traffic history aggregated per minute */
  const chart = useMemo(() => {
    const buckets = new Map<number, { timestamp: string; rx_mbps: number; tx_mbps: number }>()
    for (const sample of n?.traffic_history ?? []) {
      if (!sample.timestamp) continue
      const ts = parseISTDate(sample.timestamp).getTime()
      if (!Number.isFinite(ts)) continue
      const rx = sample.rx_mbps == null ? null : Number(sample.rx_mbps)
      const tx = sample.tx_mbps == null ? null : Number(sample.tx_mbps)
      if (rx == null && tx == null) continue
      const b = Math.floor(ts / 60_000) * 60_000
      const cur = buckets.get(b) ?? {
        timestamp: new Date(b).toISOString(), rx_mbps: 0, tx_mbps: 0,
      }
      if (Number.isFinite(rx)) cur.rx_mbps += rx as number
      if (Number.isFinite(tx)) cur.tx_mbps += tx as number
      buckets.set(b, cur)
    }
    return [...buckets.values()]
      .sort((a, b) => a.timestamp.localeCompare(b.timestamp))
      .map((p) => ({ ...p, label: clock(p.timestamp) }))
  }, [n?.traffic_history])

  /* Sparkline data from chart */
  const rxSpark = useMemo(() => chart.slice(-20).map((p) => p.rx_mbps), [chart])
  const txSpark = useMemo(() => chart.slice(-20).map((p) => p.tx_mbps), [chart])
  const latestTrafficSample = chart.length ? chart[chart.length - 1].timestamp : null
  const currentRx = n?.traffic.rx_mbps
  const currentTx = n?.traffic.tx_mbps

  /* Peak combined throughput actually observed in this window — used to
     normalize the radar's "Traffic" axis dynamically instead of a fixed
     magic number, so the reading stays meaningful at any traffic scale. */
  const trafficPeak = useMemo(() => {
    const peak = chart.reduce((max, p) => Math.max(max, (p.rx_mbps ?? 0) + (p.tx_mbps ?? 0)), 0)
    const currentValues = [currentRx, currentTx].filter((value): value is number => value != null && Number.isFinite(value))
    const current = currentValues.length ? currentValues.reduce((sum, value) => sum + value, 0) : null
    return Math.max(peak, current ?? 0, 1)
  }, [chart, n?.traffic.rx_mbps, n?.traffic.tx_mbps])

  const availability = summary?.total_devices
    ? (health.online / summary.total_devices) * 100
    : 0

  const healthPie = useMemo(
    () =>
      [
        { name: "Online", value: health.online, fill: C.green },
        { name: "Degraded", value: health.degraded, fill: C.amber },
        { name: "Stale", value: health.stale, fill: C.orange },
        { name: "Offline", value: health.offline, fill: C.red },
        { name: "Unknown", value: health.unknown, fill: C.muted },
      ].filter((x) => x.value > 0),
    [health],
  )

  const deviceTypePie = useMemo(() => {
    const entries = Object.entries(n?.device_types ?? {})
    return entries.map(([name, value], i) => ({
      name, value: Number(value) || 0, fill: PALETTE[i % PALETTE.length],
    }))
  }, [n?.device_types])

  /* Treemap data: device types */
  const treemapData = useMemo(
    () => deviceTypePie.map((p) => ({ name: p.name, size: p.value })),
    [deviceTypePie],
  )

  /* Radar data: multi-metric health */
  const radarData = useMemo(() => {
    const total = summary?.total_devices ?? 0
    const ifTotal = n?.interface_summary.total ?? 0
    const pollTotal = (n?.polling.successful_attempts ?? 0) + (n?.polling.failed_attempts ?? 0)
    const currentValues = [currentRx, currentTx].filter((value): value is number => value != null && Number.isFinite(value))
    const currentTraffic = currentValues.length ? currentValues.reduce((sum, value) => sum + value, 0) : null
    return [
      { metric: "Availability", A: availability, full: 100 },
      { metric: "Polling", A: pollTotal ? ((n?.polling.successful_attempts ?? 0) / pollTotal) * 100 : 0, full: 100 },
      { metric: "Interfaces Up", A: ifTotal ? ((n?.interface_summary.up ?? 0) / ifTotal) * 100 : 0, full: 100 },
      { metric: "SNMP Enabled", A: total ? (snmpEnabled / total) * 100 : 0, full: 100 },
      { metric: "Health", A: total ? ((health.online + health.warning * 0.5) / total) * 100 : 0, full: 100 },
      { metric: "Traffic", A: currentTraffic == null ? 0 : (currentTraffic / trafficPeak) * 100, full: 100 },
    ]
  }, [availability, snmpEnabled, summary, n, health, trafficPeak])

  const topDevicesData = useMemo(
    () =>
      (n?.traffic.top_devices ?? [])
        .map((item) => ({
          name: item.device_name || `Device ${item.device_id}`,
          total: Number((item.rx_mbps + item.tx_mbps).toFixed(2)),
        }))
        .sort((a, b) => b.total - a.total)
        .slice(0, 8),
    [n?.traffic.top_devices],
  )

  /* Alerts grouped by severity — colors and totals are fully dynamic,
     read straight from whatever severities the API returns. */
  const severityColor: Record<string, string> = {
    critical: C.red, high: "#ff6b35", medium: C.amber,
    warning: "#ffd166", low: C.cyan, info: "#8b9cff",
  }
  const alertChart = useMemo(
    () =>
      Object.entries(n?.alerts_by_severity ?? {}).map(([name, value]) => ({
        name: name.slice(0, 3).toUpperCase(),
        fullName: name,
        value: Number(value) || 0,
        fill: severityColor[name] ?? C.cyan,
      })),
    [n?.alerts_by_severity],
  )

  const pollTotal = (n?.polling.successful_attempts ?? 0) + (n?.polling.failed_attempts ?? 0)
  const pollSuccessPct = pollTotal ? ((n?.polling.successful_attempts ?? 0) / pollTotal) * 100 : 0
  const pollDisplay = pollTotal
    ? `${pollSuccessPct.toFixed(1)}%`
    : "N/A"

  return (
    <div
      className="dashboard-page p-4 md:p-6 space-y-5 animate-fadeIn"
      style={{
        background:
          "radial-gradient(circle at 85% 0%, rgba(0,212,255,.08), transparent 34%), radial-gradient(circle at 0% 100%, rgba(139,92,246,.06), transparent 40%)",
      }}
    >
      {/* ── HEADER ── */}
      <div className="flex flex-col lg:flex-row lg:items-end justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="font-display font-bold text-2xl md:text-3xl tracking-widest neon-cyan">
              {d.title}
            </h1>
            <Badge label={d.live} tone="green" />
          </div>
          <p className="font-mono text-xs mt-1" style={{ color: C.muted }}>
            {d.subtitle} {updated ? formatISTTime(updated, true) : d.na} IST
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div
            className="flex rounded-lg p-1"
            style={{
              background: "rgba(255,255,255,.04)",
              border: "1px solid var(--t-border-alpha)",
            }}
          >
            {["1H", "6H", "12H", "24H", "7D"].map((x) => (
              <button
                key={x}
                onClick={() => setRange(x)}
                className="font-mono text-[10px] px-3 py-2 rounded transition-all duration-300"
                style={{
                  color: range === x ? "#000" : C.muted,
                  background: range === x ? C.cyan : "transparent",
                  boxShadow: range === x ? `0 0 16px ${C.cyan}66` : "none",
                }}
              >
                {x}
              </button>
            ))}
          </div>
          <button
            onClick={() => void load()}
            disabled={loading}
            className="font-mono text-xs px-3 py-2 rounded glass-bright transition-all duration-300 hover:scale-105 disabled:opacity-60 disabled:cursor-not-allowed"
            style={{ color: C.cyan, border: `1px solid ${C.cyan}40` }}
          >
            {loading ? d.loading : d.refresh}
          </button>
        </div>
      </div>

      {error && (
        <div
          className="font-mono text-xs rounded-lg p-3 animate-slideDown flex items-center gap-2"
          style={{ color: C.red, background: `${C.red}12`, border: `1px solid ${C.red}40` }}
        >
          <span className="h-1.5 w-1.5 rounded-full shrink-0" style={{ background: C.red, boxShadow: `0 0 8px ${C.red}` }} />
          {error}
        </div>
      )}

      {loading && !data ? (
        <div
          className="glass rounded-xl p-12 text-center font-mono text-sm animate-pulse"
          style={{ color: C.cyan }}
        >
          {d.loadingStored}
        </div>
      ) : (
        <>
          {/* ── METRIC CARDS ── */}
          <SectionLabel label="Overview" />
          <div className="grid grid-cols-2 sm:grid-cols-4 2xl:grid-cols-8 gap-3 animate-slideUp">
            <Metric label={d.totalDevices} number={summary?.total_devices ?? 0} hint={d.inventory} onClick={() => navigate("/device-monitoring")} />
            <Metric label={d.online} number={summary?.online_devices ?? 0} hint={d.reachable} tone="green" onClick={() => navigate("/device-monitoring")} />
            <Metric label={d.offline} number={summary?.offline_devices ?? 0} hint={d.unreachable} tone="red" onClick={() => navigate("/device-monitoring")} />
            <Metric label={d.snmpEnabled} number={snmpEnabled} hint={d.credentialsConfigured} tone="green" onClick={() => navigate("/snmp/devices")} />
            <Metric label={d.snmpFailed} number={n?.polling.failure ?? 0} hint={rangeLabel} tone="red" onClick={() => navigate("/monitoring-jobs")} />
            <Metric label={d.criticalAlerts} number={summary?.critical_alerts ?? 0} hint={d.openAcknowledged} tone="red" onClick={() => navigate("/alerts")} />
            <Metric label={d.warningAlerts} number={(n?.alerts_by_severity.warning ?? 0) + (n?.alerts_by_severity.medium ?? 0)} hint={d.openAcknowledged} tone="amber" onClick={() => navigate("/alerts")} />
          <Metric label={d.interfacesDown} number={n?.interface_summary.down ?? 0} hint={d.latestSnmpState} tone="red" onClick={() => navigate("/snmp")} />
          </div>

          {/* ═══════════ ROW: 4 CLOCK GAUGES ═══════════ */}
          <Panel title="System Vitals" subtitle="Real-time circular gauges · clock-style readouts" className="system-vitals-panel">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-5 py-2">
              {[
                { value: availability, label: "Availability", tone: C.green },
                { value: pollSuccessPct, valueLabel: pollDisplay, label: "Poll Success", tone: C.cyan },
                { value: avgCpu, label: "Avg CPU", tone: C.amber },
                { value: avgMem, label: "Avg Memory", tone: C.purple },
              ].map((g) => (
                <div
                  key={g.label}
                  className="flex flex-col items-center justify-center rounded-2xl px-4 py-6 w-full transition-all duration-300 hover:-translate-y-1"
                  style={{
                    background: `linear-gradient(160deg, ${g.tone}12, transparent 75%)`,
                    border: `1px solid ${g.tone}30`,
                  }}
                >
                  <ClockGauge value={g.value} valueLabel={g.valueLabel} label={g.label} tone={g.tone} showScale size={190} />
                </div>
              ))}
            </div>
          </Panel>

          {/* ═══════════ ROW: SPEEDOMETERS + SPARKLINES ═══════════ */}
          <SectionLabel label="Performance & Traffic" />
          <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
            <Panel title="Live Traffic" subtitle="RX / TX current load">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 py-4">
                {[{ label: "Receive", short: "RX", value: currentRx, tone: C.green, spark: rxSpark }, { label: "Transmit", short: "TX", value: currentTx, tone: C.cyan, spark: txSpark }].map((item) => {
                  const max = Math.max(...[currentRx, currentTx].filter((value): value is number => value != null && Number.isFinite(value)), 1)
                  const pct = item.value == null ? 0 : (item.value / max) * 100
                  return <div key={item.short} className="traffic-metric rounded-2xl p-4" style={{ border: `1px solid ${item.tone}35`, background: `linear-gradient(145deg, ${item.tone}12, transparent 70%)` }}>
                    <div className="flex items-center justify-between">
                      <span className="font-mono text-[10px] uppercase tracking-widest" style={{ color: C.muted }}>{item.label} <b style={{ color: item.tone }}>· {item.short}</b></span>
                      <span className="h-2 w-2 rounded-full" style={{ background: item.tone, boxShadow: `0 0 10px ${item.tone}` }} />
                    </div>
                    <div className="font-display text-3xl mt-3" style={{ color: item.tone }}>{formatTraffic(item.value)}</div>
                    <div className="mt-4 h-2 rounded-full overflow-hidden" style={{ background: "var(--t-border-light)" }}><div className="traffic-fill h-full rounded-full" style={{ width: `${pct}%`, background: item.tone, boxShadow: `0 0 12px ${item.tone}` }} /></div>
                    <div className="mt-3">
                      <TrafficMiniChart
                        data={chart.length ? chart.slice(-24) : [{ label: "Now", rx_mbps: item.short === "RX" ? item.value : 0, tx_mbps: item.short === "TX" ? item.value : 0 }]}
                        dataKey={item.short === "RX" ? "rx_mbps" : "tx_mbps"}
                        tone={item.tone}
                      />
                    </div>
                  </div>
                })}
              </div>
            </Panel>

            {/* ═══════════ RADAR — 6-metric health snapshot ═══════════ */}
            <Panel title="Health Radar" subtitle="Multi-metric snapshot">
              <ResponsiveContainer width="100%" height={300}>
                <RadarChart data={radarData} outerRadius="72%">
                  <defs>
                    <linearGradient id="radarFill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor={C.cyan} stopOpacity={0.75} />
                      <stop offset="100%" stopColor={C.purple} stopOpacity={0.35} />
                    </linearGradient>
                  </defs>
                  <PolarGrid stroke="rgba(0,212,255,.22)" />
                  <PolarAngleAxis dataKey="metric" tick={{ fill: C.muted, fontSize: 10, fontFamily: "monospace" }} />
                  <PolarRadiusAxis angle={30} domain={[0, 100]} tick={{ fill: C.muted, fontSize: 9 }} stroke="rgba(255,255,255,.1)" />
                  <Radar name="Health" dataKey="A" stroke={C.cyan} fill="url(#radarFill)" fillOpacity={0.6} strokeWidth={2} animationDuration={1400} />
                  <Tooltip content={<ChartTooltip formatter={(v: any) => `${Number(v).toFixed(1)}%`} />} />
                </RadarChart>
              </ResponsiveContainer>
            </Panel>

            {/* ═══════════ RADIAL BAR — device status share ═══════════ */}
            <Panel title="Status Share" subtitle="Devices by state (radial bars)">
              <div className="relative h-[260px]">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={healthPie}
                      dataKey="value"
                      nameKey="name"
                      innerRadius="58%"
                      outerRadius="78%"
                      paddingAngle={4}
                      cornerRadius={10}
                      stroke="none"
                      animationBegin={120}
                      animationDuration={1100}
                      isAnimationActive
                    >
                      {healthPie.map((entry) => <Cell key={entry.name} fill={entry.fill} />)}
                    </Pie>
                    <Tooltip content={<ChartTooltip />} />
                  </PieChart>
                </ResponsiveContainer>
                {healthPie.length === 0 && (
                  <div className="absolute inset-0 flex items-center justify-center">
                    <Empty text={d.noStoredData} />
                  </div>
                )}
                <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none pb-1">
                  <span className="font-display text-3xl font-semibold" style={{ color: C.green }}>{health.online}</span>
                  <span className="font-mono text-[10px] uppercase tracking-widest" style={{ color: C.muted }}>online now</span>
                </div>
              </div>
              <div className="grid grid-cols-4 gap-2 mt-3">
                {Object.entries(health).map(([key, val]) => (
                  <div key={key} className="text-center rounded-lg p-2 transition-all duration-300 hover:scale-105" style={{ background: "rgba(0,212,255,.04)" }}>
                    <div className="font-display text-lg" style={{ color: key === "offline" ? C.red : key === "warning" ? C.amber : C.green }}>
                      {val}
                    </div>
                    <div className="font-mono text-[9px] uppercase" style={{ color: C.muted }}>
                      {d.health[key as keyof typeof d.health]}
                    </div>
                  </div>
                ))}
              </div>
            </Panel>
          </div>

          {/* ═══════════ ROW: Area Traffic + Top Devices ═══════════ */}
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
            <Panel title={d.networkTraffic} subtitle={`${d.storedInterfaceSamples} · ${range}`} onClick={() => navigate("/snmp")}>
              <div className="flex gap-6 mb-3">
                <div>
                  <div className="font-mono text-[10px]" style={{ color: C.muted }}>{d.rxTraffic}</div>
                  <div className="font-display text-2xl neon-green">{formatTraffic(n?.traffic.rx_mbps)}</div>
                </div>
                <div>
                  <div className="font-mono text-[10px]" style={{ color: C.muted }}>{d.txTraffic}</div>
                  <div className="font-display text-2xl neon-cyan">{formatTraffic(n?.traffic.tx_mbps)}</div>
                </div>
              </div>
              {chart.length ? (
                <ResponsiveContainer width="100%" height={200}>
                  <AreaChart data={chart}>
                    <defs>
                      <linearGradient id="rxGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor={C.green} stopOpacity={0.55} />
                        <stop offset="100%" stopColor={C.green} stopOpacity={0} />
                      </linearGradient>
                      <linearGradient id="txGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor={C.cyan} stopOpacity={0.55} />
                        <stop offset="100%" stopColor={C.cyan} stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid stroke="rgba(255,255,255,.08)" vertical={false} />
                    <XAxis dataKey="label" tick={{ fill: C.muted, fontSize: 10 }} />
                    <YAxis tick={{ fill: C.muted, fontSize: 10 }} tickFormatter={(v) => formatTraffic(Number(v))} width={78} />
                    <Tooltip content={<ChartTooltip formatter={(v: any) => formatTraffic(Number(v))} />} />
                    <Area type="monotone" dataKey="rx_mbps" stroke={C.green} fill="url(#rxGrad)" name="RX" strokeWidth={2} animationDuration={1200} />
                    <Area type="monotone" dataKey="tx_mbps" stroke={C.cyan} fill="url(#txGrad)" name="TX" strokeWidth={2} animationDuration={1200} />
                  </AreaChart>
                </ResponsiveContainer>
              ) : (
                <div className="space-y-5 py-8">
                  <div className="font-mono text-[10px] uppercase tracking-widest" style={{ color: C.muted }}>Current load snapshot</div>
                  {[{ label: "RX throughput", value: currentRx, tone: C.green }, { label: "TX throughput", value: currentTx, tone: C.cyan }].map((item) => {
                    const max = Math.max(...[currentRx, currentTx].filter((value): value is number => value != null && Number.isFinite(value)), 1)
                    return <div key={item.label}>
                      <div className="flex justify-between font-mono text-xs mb-2"><span style={{ color: C.muted }}>{item.label}</span><strong style={{ color: item.tone }}>{formatTraffic(item.value)}</strong></div>
                      <div className="h-3 rounded-full overflow-hidden" style={{ background: "var(--t-border-light)" }}><div className="traffic-fill h-full rounded-full" style={{ width: `${item.value == null ? 0 : (item.value / max) * 100}%`, background: item.tone, boxShadow: `0 0 14px ${item.tone}` }} /></div>
                    </div>
                  })}
                  <div className="flex items-center gap-2 font-mono text-[10px]" style={{ color: C.muted }}><span className="h-2 w-2 rounded-full" style={{ background: C.amber }} /> Historical samples are not available for {range}</div>
                </div>
              )}
            </Panel>

            <Panel title={d.topDevicesByTraffic} subtitle={d.latestInterfaceTotals}>
              {topDevicesData.length ? (
                <ResponsiveContainer width="100%" height={280}>
                  <BarChart data={topDevicesData} layout="vertical" margin={{ left: 0, right: 20, top: 5, bottom: 5 }}>
                    <CartesianGrid stroke="rgba(255,255,255,.07)" horizontal={false} />
                    <XAxis type="number" tick={{ fill: C.muted, fontSize: 10 }} tickFormatter={(v) => formatTraffic(Number(v))} />
                    <YAxis type="category" dataKey="name" width={90} tick={{ fill: C.muted, fontSize: 10 }} axisLine={false} tickLine={false} />
                    <Tooltip content={<ChartTooltip formatter={(v: any) => formatTraffic(Number(v))} />} cursor={{ fill: "rgba(0,212,255,.06)" }} />
                    <Bar dataKey="total" name="Traffic" radius={[0, 6, 6, 0]} animationDuration={1200}>
                      {topDevicesData.map((_, i) => <Cell key={i} fill={PALETTE[i % PALETTE.length]} />)}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              ) : <Empty text={d.noStoredData} />}
            </Panel>
          </div>

          {/* ═══════════ ROW: Treemap + Donut + Alerts ═══════════ */}
          <SectionLabel label="Inventory & Alerts" />
          <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
            {/* ═══ TREEMAP ═══ */}
            <Panel title="Device Type Map" subtitle="Treemap · proportional inventory">
              {treemapData.length ? (
                <div className="space-y-4 py-2">
                  <div className="flex items-end justify-between">
                    <div>
                      <div className="font-mono text-[10px] uppercase tracking-widest" style={{ color: C.muted }}>Inventory total</div>
                      <div className="font-display text-4xl" style={{ color: C.cyan }}>{summary?.total_devices ?? 0}</div>
                    </div>
                    <Badge label={`${deviceTypePie.length} categories`} tone="cyan" />
                  </div>
                  {deviceTypePie.map((item) => {
                    const pct = summary?.total_devices ? (item.value / summary.total_devices) * 100 : 0
                    return (
                      <div key={item.name} className="device-type-row">
                        <div className="flex justify-between items-center mb-1.5 font-mono text-xs">
                          <span className="flex items-center gap-2" style={{ color: "var(--t-text)" }}>
                            <i className="h-2.5 w-2.5 rounded-full" style={{ background: item.fill, boxShadow: `0 0 8px ${item.fill}` }} />
                            {item.name}
                          </span>
                          <strong style={{ color: item.fill }}>{item.value} <small style={{ color: C.muted }}>({pct.toFixed(0)}%)</small></strong>
                        </div>
                        <div className="h-3 rounded-full overflow-hidden" style={{ background: "var(--t-border-light)" }}>
                          <div className="device-type-fill h-full rounded-full" style={{ width: `${Math.max(pct, 2)}%`, background: `linear-gradient(90deg, ${item.fill}, ${item.fill}99)`, boxShadow: `0 0 12px ${item.fill}88` }} />
                        </div>
                      </div>
                    )
                  })}
                  <p className="font-mono text-[10px] pt-1" style={{ color: C.muted }}>Distribution by managed device classification</p>
                </div>
              ) : <Empty text={d.noDeviceTypes} />}
            </Panel>

            {/* ═══ DONUT ═══ */}
            <Panel title={d.deviceTypes} subtitle={d.inventoryClassification}>
              {deviceTypePie.length ? (
                <ResponsiveContainer width="100%" height={280}>
                  <PieChart>
                    <defs>
                      {deviceTypePie.map((e, i) => (
                        <radialGradient id={`pieGrad-${i}`} key={i}>
                          <stop offset="0%" stopColor={e.fill} stopOpacity={0.95} />
                          <stop offset="100%" stopColor={e.fill} stopOpacity={0.55} />
                        </radialGradient>
                      ))}
                    </defs>
                    <Pie
                      data={deviceTypePie}
                      dataKey="value"
                      nameKey="name"
                      innerRadius="48%"
                      outerRadius="82%"
                      paddingAngle={3}
                      stroke="rgba(0,0,0,.35)"
                      animationDuration={1400}
                    >
                      {deviceTypePie.map((entry, i) => (
                        <Cell key={entry.name} fill={`url(#pieGrad-${i})`} stroke={entry.fill} />
                      ))}
                    </Pie>
                    <Tooltip content={<ChartTooltip />} />
                    <Legend iconSize={9} wrapperStyle={{ fontSize: 10, fontFamily: "monospace" }} />
                  </PieChart>
                </ResponsiveContainer>
              ) : <Empty text={d.noDeviceTypes} />}
            </Panel>

            {/* ═══ ALERTS BY SEVERITY ═══ */}
            <Panel title={d.alerts} subtitle={d.activeAlertSeverity} onClick={() => navigate("/alerts")}>
              {alertChart.some((b) => b.value > 0) ? (
                <ResponsiveContainer width="100%" height={280}>
                  <BarChart data={alertChart} margin={{ top: 10, right: 10, left: 0, bottom: 5 }}>
                    <CartesianGrid stroke="rgba(255,255,255,.08)" vertical={false} />
                    <XAxis dataKey="name" tick={{ fill: C.muted, fontSize: 10 }} />
                    <YAxis tick={{ fill: C.muted, fontSize: 10 }} allowDecimals={false} />
                    <Tooltip content={<ChartTooltip />} cursor={{ fill: "rgba(0,212,255,.06)" }} />
                    <Bar dataKey="value" name="Alerts" radius={[6, 6, 0, 0]} animationDuration={1000}>
                      {alertChart.map((entry) => <Cell key={entry.fullName} fill={entry.fill} />)}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              ) : <Empty text={d.noStoredData} />}
            </Panel>
          </div>

          {/* ═══════════ ROW: Line Trend + Interfaces + SNMP ═══════════ */}
          <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
            <Panel title="Traffic Trend" subtitle={`DB persisted samples · ${range}${latestTrafficSample ? ` · last sample ${clock(latestTrafficSample)}` : " · awaiting samples"}`} onClick={() => navigate("/snmp")}>
              {chart.length ? (
                <ResponsiveContainer width="100%" height={230}>
                  <LineChart data={chart}>
                    <CartesianGrid stroke="rgba(255,255,255,.07)" vertical={false} />
                    <XAxis dataKey="label" tick={{ fill: C.muted, fontSize: 9 }} />
                    <YAxis tick={{ fill: C.muted, fontSize: 9 }} tickFormatter={(v) => formatTraffic(Number(v))} width={78} />
                    <Tooltip content={<ChartTooltip formatter={(v: any) => formatTraffic(Number(v))} />} />
                    <Line type="monotone" dataKey="rx_mbps" stroke={C.green} strokeWidth={2.5} dot={false} name="RX" animationDuration={1200} />
                    <Line type="monotone" dataKey="tx_mbps" stroke={C.cyan} strokeWidth={2.5} dot={false} name="TX" animationDuration={1400} />
                  </LineChart>
                </ResponsiveContainer>
              ) : <Empty text={d.noInterfaceHistory} />}
            </Panel>

            <Panel title={d.interfaces} subtitle={d.latestSnmpState} onClick={() => navigate("/snmp")}>
              <div className="grid grid-cols-3 gap-2 mb-4">
                <Mini label={d.total} number={n?.interface_summary.total ?? 0} />
                <Mini label={d.up} number={n?.interface_summary.up ?? 0} tone={C.green} />
                <Mini label={d.down} number={n?.interface_summary.down ?? 0} tone={C.red} />
              </div>
              <div className="grid grid-cols-2 gap-3 font-mono text-xs mb-4" style={{ color: C.muted }}>
                <span>{d.errors} <b style={{ color: C.red }}>{n?.interface_summary.errors ?? 0}</b></span>
                <span>{d.drops} <b style={{ color: C.amber }}>{n?.interface_summary.drops ?? 0}</b></span>
              </div>
              {/* Mini gauges */}
              <div className="grid grid-cols-2 items-start gap-3 pt-1">
                <Speedometer
                  value={n?.interface_summary.total ? ((n?.interface_summary.up ?? 0) / n.interface_summary.total) * 100 : 0}
                  label="Interfaces UP"
                  tone={C.green}
                  size={110}
                />
                <Speedometer
                  value={n?.interface_summary.total ? ((n?.interface_summary.down ?? 0) / n.interface_summary.total) * 100 : 0}
                  label="Interfaces DOWN"
                  tone={C.red}
                  size={110}
                />
              </div>
            </Panel>

            <Panel title={d.snmpMonitoring} subtitle="Historical polling attempt outcomes" onClick={() => navigate("/monitoring-jobs")}>
              <div className="space-y-3">
                <BarLine label={d.successfulAttempts} current={n?.polling.successful_attempts ?? 0} total={n?.polling.total_attempts ?? 0} />
                <BarLine label={d.failedAttempts} current={n?.polling.failed_attempts ?? 0} total={n?.polling.total_attempts ?? 0} tone={C.red} />
                <div className="grid grid-cols-2 gap-3 pt-2">
                  <div>
                    <div className="font-mono text-[10px]" style={{ color: C.muted }}>{d.configuredJobs}</div>
                    <div className="font-display text-xl neon-cyan">{n?.polling.configured_jobs ?? 0}</div>
                  </div>
                  <div>
                    <div className="font-mono text-[10px]" style={{ color: C.muted }}>{d.unsupportedAttempts}</div>
                    <div className="font-display text-xl" style={{ color: C.amber }}>{n?.polling.unsupported_attempts ?? 0}</div>
                  </div>
                </div>
                <div className="grid grid-cols-3 gap-2 font-mono text-[10px]" style={{ color: C.muted }}>
                  <span>{d.noDataAttempts}: <b className="text-white">{n?.polling.no_data_attempts ?? 0}</b></span>
                  <span>{d.unknownAttempts}: <b className="text-white">{n?.polling.unknown_attempts ?? 0}</b></span>
                  <span>{d.totalAttempts}: <b className="text-white">{n?.polling.total_attempts ?? 0}</b></span>
                </div>
                <div className="flex justify-center pt-2">
                  <ClockGauge
                    value={pollSuccessPct}
                    valueLabel={pollDisplay}
                    label="Poll Success"
                    tone={C.cyan}
                    size={140}
                    tickCount={40}
                  />
                </div>
              </div>
            </Panel>
          </div>

          {/* ═══════════ ROW: Network Info + Recent Table ═══════════ */}
          <SectionLabel label="Topology & Recent Activity" />
          <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
            <Panel title={d.networkInformation} subtitle={d.normalizedTopologyInventory}>
              <div className="grid grid-cols-2 gap-3">
                {Object.entries({
                  [d.lldpCdpNeighbors]: n?.network.lldp_neighbors,
                  [d.vlans]: n?.network.vlan_count,
                  [d.routes]: n?.network.routing_entries,
                  [d.arp]: n?.network.arp_entries,
                  [d.mac]: n?.network.mac_entries,
                  [d.topologyNodes]: n?.network.topology_nodes,
                }).map(([label, metric]) => (
                  <div key={label} className="transition-all duration-300 hover:translate-x-1">
                    <div className="font-mono text-[10px]" style={{ color: C.muted }}>{label}</div>
                    <div className="font-display text-lg neon-cyan">{metric == null ? "N/A" : metric}</div>
                  </div>
                ))}
              </div>
            </Panel>

            <Panel
              title={d.recentDevicesActivity}
              subtitle={d.lastPersistedState}
              onClick={() => navigate("/device-monitoring")}
              className="xl:col-span-2"
            >
              <div className="overflow-x-auto">
                <table className="w-full text-left">
                  <thead>
                    <tr className="font-mono text-[10px] uppercase" style={{ color: C.muted }}>
                      {[d.device, d.ip, d.type, d.status, d.lastPoll].map((h) => (
                        <th key={h} className="pb-2 pr-3">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {devices.slice(0, 8).map((dv) => (
                      <tr
                        key={dv.id}
                        className="font-mono text-xs transition-colors duration-200 hover:bg-cyan-400/5"
                        style={{ borderTop: "1px solid rgba(255,255,255,.06)" }}
                      >
                        <td className="py-2 pr-3" style={{ color: "var(--t-text, #c8d8ee)" }}>{dv.hostname}</td>
                        <td className="py-2 pr-3" style={{ color: C.muted }}>{dv.ip_address}</td>
                        <td className="py-2 pr-3" style={{ color: C.muted }}>{dv.device_type || d.na}</td>
                        <td className="py-2 pr-3">
                          <Badge
                            label={dv.health?.status ?? dv.status}
                            tone={dv.health?.status === "online" ? "green" : dv.health?.status === "offline" ? "red" : "amber"}
                          />
                          {dv.health?.health_reason && <div className="mt-1 text-[9px]" style={{ color: C.muted }}>{dv.health.health_reason}</div>}
                        </td>
                        <td className="py-2" style={{ color: C.muted }}>
                          {clock(n?.devices[String(dv.id)]?.last_poll?.timestamp ?? dv.last_seen)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {!devices.length && <Empty text={d.noDevices} />}
              </div>
            </Panel>
          </div>
        </>
      )}

      {/* ── GLOBAL ANIMATIONS ── */}
      <style>{`
        @keyframes fadeIn {
          from { opacity: 0; transform: translateY(8px); }
          to   { opacity: 1; transform: translateY(0); }
        }
        @keyframes slideUp {
          from { opacity: 0; transform: translateY(20px); }
          to   { opacity: 1; transform: translateY(0); }
        }
        @keyframes slideDown {
          from { opacity: 0; transform: translateY(-10px); }
          to   { opacity: 1; transform: translateY(0); }
        }
        .animate-fadeIn  { animation: fadeIn 0.6s ease-out both; }
        .animate-slideUp { animation: slideUp 0.7s ease-out both; }
        .animate-slideDown { animation: slideDown 0.4s ease-out both; }

        .recharts-bar-rectangle:hover { filter: drop-shadow(0 0 8px currentColor); }
        .recharts-pie-sector:hover    { filter: drop-shadow(0 0 10px currentColor); }
        .recharts-area:hover          { filter: drop-shadow(0 0 6px currentColor); }
        .recharts-radar-polygon       { filter: drop-shadow(0 0 8px #00d4ff88); }
      `}</style>
    </div>
  )
}
