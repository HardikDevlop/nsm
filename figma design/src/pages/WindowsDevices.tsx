/* eslint-disable @typescript-eslint/no-explicit-any */
import { Fragment, useEffect, useMemo, useRef, useState, type CSSProperties, type ReactNode } from "react"
import { Link, useNavigate, useParams } from "react-router"
import GlassCard from "../components/GlassCard"
import WindowsDeviceOverview from "../components/WindowsDeviceOverview"
import WindowsDiskInventoryPanel from "../components/WindowsDiskInventory"
import WindowsCATrustPanel from "../components/windows/WindowsCATrustPanel"
import WindowsTCPDiagnostics from "../components/windows/WindowsTCPDiagnostics"
import WindowsTLSDiagnostics from "../components/windows/WindowsTLSDiagnostics"
import { formatBitsPerSecond, formatBytesBinary, formatBytesPerSecond, formatFrequency, formatLatency, formatPercentage, formatUptime } from "../unitFormatting"
import {
  createDevice,
  createWindowsCredential,
  deleteDevice,
  fetchWindowsMetric,
  fetchWindowsHardware,
  discoverWindowsHardwareSensors,
  fetchWindowsSystemEvents,
  getWindowsSystemEvents,
  getWindowsMetric,
  getWindowsHardware,
  getWindowsDiskInventory,
  getWindowsDiskHealth,
  getWindowsUSBInventory,
  getWindowsThresholds,
  updateWindowsThresholds,
  listDevices,
  listEnrolledWindowsDeviceIds,
  listSites,
  listWindowsCredentials,
  testWindowsConnection,
  updateWindowsCredential,
  type DeviceRecord,
  type SiteRecord,
  type WindowsCredentialRecord,
  type WindowsMetricSnapshot,
  type WindowsMemoryCounter,
  type WindowsDiskCapacity,
  type WindowsDiskCounter,
  type WindowsDiskInventory,
  type WindowsDiskHealthResponse,
  type WindowsHardwareSnapshot,
  type WindowsNativeSensor,
  type WindowsSystemEvent,
  type WindowsUSBInventory,
} from "../lib/api"
import { useAuth } from "../components/AuthContext"
import { isWindowsDevice } from "../lib/windowsClassification"

/* ════════════════════════════════════════════════════════════════
   Types & constants
   ════════════════════════════════════════════════════════════════ */
type Step = 1 | 2 | 3
type Progress = "idle" | "device" | "credential" | "testing" | "connected" | "failed"
type Module = WindowsMetricSnapshot["module"]
type CounterLike = { value?: number | null; status?: string } | undefined

const tabNames = ["overview", "cpu", "memory", "disk", "network", "hardware", "storage", "events", "usb"] as const
type TabName = (typeof tabNames)[number]
const tabLabels: Record<TabName, string> = {
  overview: "Overview",
  cpu: "CPU",
  memory: "Memory",
  disk: "Disk",
  network: "Network",
  hardware: "Hardware",
  storage: "Storage",
  events: "Event Logs",
  usb: "USB",
}
const tabIcons: Record<TabName, string> = {
  overview: "◧",
  cpu: "▦",
  memory: "▤",
  disk: "◉",
  network: "⇄",
  hardware: "⚙",
  storage: "▣",
  events: "☰",
  usb: "▣",
}
const metricTabs: TabName[] = ["overview", "cpu", "memory", "disk", "network"]
const wizardSteps = ["Device", "Credentials", "Test"] as const

const emptyForm = {
  hostname: "",
  ip_address: "",
  site_id: "",
  username: "",
  domain: "",
  connection_host: "",
  password: "",
}
const NA = "N/A"
const MUTED_VALUES = new Set(["N/A", "Unavailable", "Not Supported", "Permission Denied", "Collection Failed", "Not available", "—"])
const norm = (v: string) => v.trim().toLowerCase()
const isNum = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v)

// Some Windows agents report MaxClockSpeed as the current/base clock. Prefer
// the higher advertised clock from the processor name when that happens.
const cpuMaxFrequencyMhz = (cpu: any): number | null => {
  const reported = isNum(cpu?.max_clock_speed_mhz) ? cpu.max_clock_speed_mhz : null
  const advertised = String(cpu?.name ?? "").match(/@\s*([\d.]+)\s*(GHz|MHz)\b/i)
  const advertisedMhz = advertised
    ? Number(advertised[1]) * (advertised[2].toLowerCase() === "ghz" ? 1000 : 1)
    : null
  const values = [reported, advertisedMhz].filter((value): value is number => value != null && Number.isFinite(value))
  return values.length ? Math.max(...values) : null
}

/* ════════════════════════════════════════════════════════════════
   Formatting helpers
   ════════════════════════════════════════════════════════════════ */
const windowsOnboardingMessage = (value: string) => {
  if (/winrm protocol error|protocol error|wsman/i.test(value)) return "Windows device and credentials were saved, but WinRM validation could not complete. Verify the computer name, HTTPS certificate trust, and WinRM service settings, then retry."
  if (/authentication|credential|invalid user|access denied/i.test(value)) return "Windows device was saved, but the credentials were rejected. Verify the Windows username, computer name, and password, then retry."
  if (/tls|certificate|ssl/i.test(value)) return "Windows device was saved, but the WinRM HTTPS certificate could not be verified. Check the configured CA trust bundle."
  if (/timeout|network|connect/i.test(value)) return "Windows device was saved, but WinRM HTTPS could not be reached. Verify port 5986 and the remote WinRM service."
  return value
}
const fmtBytes = (v?: number | null) => formatBytesBinary(v)
const fmtMiB = (v: number | null | undefined) => formatBytesBinary(isNum(v) ? v * 1024 ** 2 : null)
const fmtRate = (v?: number | null) => formatBitsPerSecond(isNum(v) ? v * 8 : null)
const fmtThroughput = (v?: number | null) => formatBytesPerSecond(v)
const fmtPct = (v: unknown) => formatPercentage(isNum(v) ? v : null)
const fmtLinkSpeed = (v?: number | null) => formatBitsPerSecond(v)
const IST = { timeZone: "Asia/Kolkata" } as const
const fmtDateTime = (value?: string | null) => (value ? new Date(value).toLocaleString("en-IN", IST) : "Never fetched")
const fmtEventTime = (value: string | null | undefined) => {
  if (!value) return NA
  const utc = /(?:Z|[+-]\d{2}:\d{2})$/.test(value) ? value : `${value}Z`
  const date = new Date(utc)
  return Number.isNaN(date.getTime()) ? NA : date.toLocaleString("en-IN", IST)
}
const fmtOsDate = (value: unknown) => {
  if (typeof value !== "string" || !value) return "Not available"
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? "Not available" : date.toLocaleString("en-IN", IST)
}
const fmtHardwareDate = (value: unknown) => {
  if (typeof value !== "string" || !value) return NA
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? NA : date.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" })
}
const fmtUptime = (value: unknown) => formatUptime(isNum(value) ? value : null, { na: NA })
const fmtLocale = (v: unknown) => (v === "0409" ? "English (United States)" : v == null || v === "" ? "Not available" : String(v))
const fmtTimezone = (value: unknown) => {
  const offset = Number(value)
  if (!Number.isFinite(offset)) return "Not available"
  const sign = offset >= 0 ? "+" : "-"
  const abs = Math.abs(offset)
  return `UTC${sign}${String(Math.floor(abs / 60)).padStart(2, "0")}:${String(abs % 60).padStart(2, "0")}`
}
const fmtServicePack = (v: unknown) => (v === "0" || v === 0 ? "No service pack" : v == null || v === "" ? "Not available" : String(v))

const counterText = (c: CounterLike, fmt: (v: number) => string = String) => {
  if (!c || !isNum(c.value)) {
    if (c?.status === "unsupported") return "Not Supported"
    if (c?.status === "permission_denied") return "Permission Denied"
    if (c?.status === "collection_failed") return "Collection Failed"
    return "Unavailable"
  }
  return fmt(c.value)
}
const sensorValue = (s: WindowsNativeSensor) => {
  if (s.status === "unsupported") return "Not Supported"
  if (s.status === "permission_denied") return "Permission Denied"
  if (s.status !== "ok" || s.value == null) return "Unavailable"
  const digits = s.unit === "°C" || s.unit === "V" ? 2 : 0
  return `${s.value.toFixed(digits)} ${s.unit}`
}
const sensorGroup = (s: WindowsNativeSensor) => {
  const label = `${s.sensor_name} ${s.name ?? ""}`.toLowerCase()
  if (s.sensor_type === "fan") return "Fan Sensors"
  if (s.sensor_type === "load") return "GPU Utilization"
  if (s.sensor_type === "voltage") return "Voltage Sensors"
  if (s.sensor_type === "temperature" && /(gpu|graphics|video)/.test(label)) return "GPU Temperature"
  if (s.sensor_type === "temperature" && /(ssd|nvme|disk|storage|drive)/.test(label)) return "Storage Temperature"
  if (s.sensor_type === "temperature") return "Temperature Sensors"
  return "Other Sensors"
}
const networkRowKey = (a: Record<string, unknown>) =>
  `${a.interface_index ?? "unknown"}:${a.mac_address ?? a.name ?? a.description ?? "adapter"}`
const isOnlineStatus = (status?: string | null) => /online|up/i.test(status ?? "")

/* ════════════════════════════════════════════════════════════════
   Shared styles
   ════════════════════════════════════════════════════════════════ */
const C = {
  muted: "var(--t-muted)",
  text: "var(--t-text)",
  accent: "var(--t-accent)",
  success: "var(--t-success)",
  danger: "var(--t-danger)",
  warning: "var(--t-warning, #f59e0b)",
  card: "var(--wd-card, var(--t-card))",
  bg: "var(--wd-page, var(--t-bg))",
  border: "var(--wd-border, var(--t-border))",
  borderLight: "var(--wd-border-light, var(--t-border-light))",
}
const inputStyle: CSSProperties = { background: C.card, color: C.text, border: "1px solid var(--t-border-alpha)" }
const fieldCls = "mt-1 w-full rounded-lg px-3 py-2 text-sm outline-none transition focus:ring-2"
const labelCls = "font-mono text-[10px] uppercase tracking-wide"
const primaryBtn: CSSProperties = { background: C.accent, color: C.bg }
const ghostBtn: CSSProperties = { background: "transparent", color: C.text, border: `1px solid ${C.border}` }

/* ════════════════════════════════════════════════════════════════
   Reusable UI building blocks
   ════════════════════════════════════════════════════════════════ */
const tone = (v: number | null) => {
  if (v == null) return C.muted
  if (v >= 90) return C.danger
  if (v >= 70) return C.warning
  return C.success
}
type WindowsThresholds = { cpu: number; memory: number; disk: number }
const DEFAULT_WINDOWS_THRESHOLDS: WindowsThresholds = { cpu: 40, memory: 40, disk: 40 }
const safeThreshold = (value: unknown, fallback = 40) => {
  const number = typeof value === "number" ? value : Number(value)
  return Number.isFinite(number) && number >= 1 && number <= 100 ? number : fallback
}
const thresholdWarning = (usage: unknown, threshold: number) => isNum(usage) && usage >= threshold
const WarningBadge = ({ threshold }: { threshold: number }) => <span className="ml-2 rounded-full border px-2 py-0.5 text-[10px] font-semibold" style={{ color: C.warning, borderColor: C.warning, background: "#fff7ed" }}>WARNING · ≥ {threshold}%</span>

/** Progress bar: LABEL (key) on the left, VALUE on the right. */
function Bar({ label, value, right, color = "#3478F6" }: { label: string; value: unknown; right?: string; color?: string }) {
  const v = isNum(value) ? Math.max(0, Math.min(100, value)) : null
  return (
    <div>
      <div className="flex items-baseline justify-between gap-2 text-xs">
        <span className="font-mono text-[10px] uppercase tracking-wide" style={{ color: C.muted }}>{label}</span>
        <span className="font-mono font-semibold" style={{ color: v == null ? C.muted : color }}>{right ?? fmtPct(value)}</span>
      </div>
      <div className="mt-1.5 h-2 w-full overflow-hidden rounded-full" style={{ background: C.borderLight }}>
        <div className="h-full rounded-full transition-all duration-500" style={{ width: `${v ?? 0}%`, background: color }} />
      </div>
    </div>
  )
}

/** Stat tile: small muted KEY on top, bold VALUE below, accent stripe on the left. */
function Tile({ label, value, sub, accent }: { label: string; value: ReactNode; sub?: ReactNode; accent?: string }) {
  const muted = MUTED_VALUES.has(String(value))
  return (
    <div
      className="rounded-lg border p-2.5"
      style={{ borderColor: C.borderLight, background: C.card, borderLeft: `3px solid ${accent ?? (muted ? C.borderLight : C.accent)}` }}
    >
      <div className="font-mono text-[10px] uppercase tracking-wide" style={{ color: C.muted }}>{label}</div>
      <div className="mt-1 break-words text-sm font-semibold" style={{ color: muted ? C.muted : C.text }}>{value}</div>
      {sub != null && <div className="mt-0.5 break-words font-mono text-[10px]" style={{ color: C.muted }}>{sub}</div>}
    </div>
  )
}

/** Key / value list: KEY on the left (muted, uppercase), VALUE on the right (bold). */
function KV({ rows }: { rows: Array<[string, ReactNode]> }) {
  return (
    <dl>
      {rows.map(([key, value], i) => {
        const muted = MUTED_VALUES.has(String(value))
        return (
          <div
            key={`${key}:${i}`}
            className="flex items-start justify-between gap-4 py-2"
            style={{ borderTop: i === 0 ? "none" : `1px dashed ${C.borderLight}` }}
          >
            <dt className="shrink-0 font-mono text-[10px] uppercase tracking-wide" style={{ color: C.muted }}>{key}</dt>
            <dd className="min-w-0 break-words text-right text-xs font-semibold" style={{ color: muted ? C.muted : C.text }}>{value}</dd>
          </div>
        )
      })}
    </dl>
  )
}

function Group({ title, children, className = "", hint }: { title: string; children: ReactNode; className?: string; hint?: string }) {
  return (
    <div className={`rounded-xl border p-4 ${className}`} style={{ borderColor: C.border, background: C.bg }}>
      <div className="mb-3 flex items-center justify-between gap-2 border-b pb-2.5" style={{ borderColor: C.borderLight }}>
        <div className="flex min-w-0 items-center gap-2 font-display text-sm font-bold" style={{ color: C.text }}>
          <span className="inline-block h-2 w-2 shrink-0 rounded-full" style={{ background: C.accent }} />
          {title}
        </div>
        {hint && <div className="font-mono text-[10px]" style={{ color: C.muted }}>{hint}</div>}
      </div>
      {children}
    </div>
  )
}

function Badge({ text, color }: { text: string; color: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 font-mono text-[10px] uppercase" style={{ color, borderColor: color }}>
      <span className="inline-block h-1.5 w-1.5 rounded-full" style={{ background: color }} />
      {text}
    </span>
  )
}

function BigNumber({ value, color, caption }: { value: ReactNode; color: string; caption?: string }) {
  return (
    <div>
      <div className="font-display text-4xl font-bold leading-none" style={{ color }}>{value}</div>
      {caption && <div className="mt-1 font-mono text-[10px] uppercase" style={{ color: C.muted }}>{caption}</div>}
    </div>
  )
}

function CardShell({
  title, subtitle, collectedAt, success, error, action, children,
}: {
  title: string
  subtitle?: string
  collectedAt?: string | null
  success?: boolean
  error?: string
  action?: ReactNode
  children: ReactNode
}) {
  return (
    <GlassCard className="p-4 md:p-5">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b pb-3" style={{ borderColor: C.borderLight }}>
        <div>
          <div className="font-display text-lg font-bold" style={{ color: C.text }}>{title}</div>
          {subtitle && <div className="font-mono text-[10px]" style={{ color: C.muted }}>{subtitle}</div>}
          {collectedAt !== undefined && (
            <div className="mt-1.5 flex flex-wrap items-center gap-2 font-mono text-[10px]" style={{ color: C.muted }}>
              <span>Last collected:</span>
              <span className="font-semibold" style={{ color: collectedAt ? C.text : C.muted }}>{fmtDateTime(collectedAt)}</span>
              {success && <Badge text="Fetch complete" color={C.success} />}
            </div>
          )}
        </div>
        {action}
      </div>
      {error && (
        <div role="alert" className="mt-3 rounded-lg border p-2.5 font-mono text-[11px]" style={{ color: C.danger, borderColor: C.danger }}>
          ⚠ {error}
        </div>
      )}
      <div className="mt-4">{children}</div>
    </GlassCard>
  )
}

function ActionButton({ label, busyLabel, busy, onClick, disabled }: { label: string; busyLabel: string; busy: boolean; onClick: () => void; disabled?: boolean }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={busy || disabled}
      className="inline-flex items-center gap-2 rounded-lg px-4 py-2 font-mono text-[10px] font-bold transition hover:brightness-110 disabled:cursor-not-allowed"
      style={{ ...primaryBtn, opacity: busy || disabled ? 0.6 : 1 }}
    >
      {busy && <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent" />}
      {busy ? busyLabel : `↻ ${label}`}
    </button>
  )
}

const EmptyState = ({ text = "No saved data. Use the FETCH button to collect it." }: { text?: string }) => (
  <div className="rounded-xl border border-dashed p-8 text-center" style={{ borderColor: C.borderLight }}>
    <div className="text-2xl" style={{ color: C.muted }}>∅</div>
    <div className="mt-2 font-mono text-xs" style={{ color: C.muted }}>{text}</div>
  </div>
)

const LoadingBlock = ({ text }: { text: string }) => (
  <div className="flex items-center justify-center gap-3 p-6 font-mono text-xs" style={{ color: C.muted }}>
    <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
    {text}
  </div>
)

function Stepper({ step }: { step: Step }) {
  return (
    <ol className="mt-4 flex items-center gap-2">
      {wizardSteps.map((name, i) => {
        const n = i + 1
        const done = n < step
        const active = n === step
        return (
          <li key={name} className="flex flex-1 items-center gap-2">
            <span
              className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full font-mono text-xs font-bold"
              style={{
                background: done || active ? C.accent : "transparent",
                color: done || active ? C.bg : C.muted,
                border: `1px solid ${done || active ? C.accent : C.border}`,
              }}
            >
              {done ? "✓" : n}
            </span>
            <span className="font-mono text-[10px] uppercase" style={{ color: active ? C.text : C.muted }}>{name}</span>
            {n < 3 && <span className="h-px flex-1" style={{ background: done ? C.accent : C.borderLight }} />}
          </li>
        )
      })}
    </ol>
  )
}

/* ════════════════════════════════════════════════════════════════
   CPU panel
   ════════════════════════════════════════════════════════════════ */
function CpuBody({ data }: { data: any }) {
  const c = data.counters || {}
  const val = (k: string) => c[k]?.value
  const perCpu: any[] = Array.isArray(data.logical_processors_usage) ? data.logical_processors_usage : []
  const unsupported = Object.values(c).some((x: any) => x?.status === "unsupported")
  const usage = isNum(data.usage_percent) ? data.usage_percent : null
  const blue = "#3478F6"
  const orange = "#F59E0B"
  const neutral = "#94A3B8"
  const counterDisplay = (key: string, counter: any) => {
    const value = counter?.value == null ? NA : String(counter.value)
    const unit = key.endsWith("_percent") ? "%" : key.endsWith("_per_sec") ? "/s" : ""
    return `${value}${unit}`
  }
  const identityRows = [
    ["Processor", data.identity?.model ?? data.model],
    ["Manufacturer", data.identity?.manufacturer],
    ["Physical cores", data.identity?.physical_cores],
    ["Logical processors", data.identity?.logical_processors ?? data.logical_processors],
    ["Maximum clock speed", data.identity?.clock_speed_mhz != null ? formatFrequency(data.identity.clock_speed_mhz * 1_000_000) : null],
    ["Architecture", data.identity?.architecture],
    ["Virtualization", data.identity?.virtualization],
    ["L1 cache", data.identity?.l1_cache],
    ["L2 cache", data.identity?.l2_cache],
    ["L3 cache", data.identity?.l3_cache],
    ["CPU ID", data.identity?.cpu_id],
  ]
  return (
    <div className="space-y-4">
      <div className="grid gap-4 lg:grid-cols-[minmax(240px,.8fr)_minmax(0,1.8fr)]">
        <Group title="Total CPU Utilization">
          <div className="mb-3 text-2xl" style={{ color: blue }}>◉</div>
          <BigNumber value={fmtPct(data.usage_percent)} color={blue} caption="CPU usage" />
          <div className="mt-4"><Bar label="Usage" value={data.usage_percent} color={blue} /></div>
        </Group>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
          <Tile label="Physical cores" value={data.identity?.physical_cores ?? NA} />
          <Tile label="Logical processors" value={data.identity?.logical_processors ?? data.logical_processors ?? NA} />
          <Tile label="Processor queue" value={counterText(c.processor_queue_length)} />
          <Tile label="Interrupts / sec" value={counterText(c.interrupts_per_sec)} />
          <Tile label="Context switches / sec" value={counterText(c.context_switches_per_sec)} />
          <Tile label="Idle time" value={isNum(val("idle_time_percent")) ? fmtPct(val("idle_time_percent")) : counterText(c.idle_time_percent)} />
        </div>
      </div>
      <Group title="CPU Information" hint="All collected processor details">
        <KV rows={identityRows.map(([label, value]) => [label, value == null || value === "" ? NA : String(value)] as [string, ReactNode])} />
      </Group>
      <Group title="Performance Counters" hint={`${Object.keys(c).length} counters collected`}>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {Object.entries(c).map(([key, counter]: [string, any]) => (
            <Tile key={key} label={key.replaceAll("_", " ")} value={counterDisplay(key, counter)} sub={`status: ${counter?.status ?? NA}${counter?.error ? ` · ${counter.error}` : ""}`} />
          ))}
        </div>
      </Group>
      <Group title="CPU Time Distribution">
        <div className="grid gap-4 md:grid-cols-3">
          <Bar label="User time" value={val("user_time_percent")} color={blue} />
          <Bar label="Privileged time" value={val("privileged_time_percent")} color={orange} />
          <Bar label="Idle time" value={val("idle_time_percent")} color={neutral} />
        </div>
      </Group>
      {perCpu.length > 0 && (
        <Group title="Per Logical CPU Utilization" hint={`${perCpu.length} threads`}>
          <div className="overflow-x-auto"><table className="w-full min-w-[760px] text-left"><thead><tr style={{ color: C.muted }}>{["CPU", "Usage", "User", "Privileged", "Idle", "Interrupts / sec", "Context switches / sec"].map((label) => <th key={label} className="px-2 py-2 font-mono text-[10px] uppercase">{label}</th>)}</tr></thead><tbody>{perCpu.map((row, i) => <tr key={row.name ?? i} style={{ borderTop: `1px solid ${C.borderLight}` }}><td className="px-2 py-2 font-mono text-xs">{row.name ?? `CPU ${i}`}</td><td className="w-40 px-2 py-2"><Bar label="" value={row.usage_percent} color={blue} /></td><td className="px-2 py-2 text-xs">{fmtPct(row.user_percent)}</td><td className="px-2 py-2 text-xs">{fmtPct(row.privileged_percent)}</td><td className="px-2 py-2 text-xs">{fmtPct(row.idle_percent)}</td><td className="px-2 py-2 text-xs">{row.interrupts_per_sec ?? NA}</td><td className="px-2 py-2 text-xs">{row.context_switches_per_sec ?? NA}</td></tr>)}</tbody></table></div>
        </Group>
      )}
      {unsupported && <div className="font-mono text-[10px]" style={{ color: C.muted }}>ℹ Some CPU counters are unsupported by this Windows provider.</div>}
    </div>
  )
}

function CpuDashboardBody({ data, systemData, threshold }: { data: any; systemData?: any; threshold: number }) {
  const counters = data.counters || {}
  const perCpu: any[] = Array.isArray(data.logical_processors_usage) ? data.logical_processors_usage : []
  const usage = isNum(data.usage_percent) ? data.usage_percent : null
  const physical = data.identity?.physical_cores
  const logical = data.identity?.logical_processors ?? data.logical_processors
  const processes: any[] = Array.isArray(data.processes) ? data.processes : []
  const counterValue = (key: string) => counters[key]?.value == null ? NA : String(counters[key].value)
  const maxSpeed = data.identity?.clock_speed_mhz == null ? NA : formatFrequency(data.identity.clock_speed_mhz * 1_000_000)
  const currentSpeed = data.identity?.current_clock_speed_mhz == null ? NA : formatFrequency(data.identity.current_clock_speed_mhz * 1_000_000)
  // Prefer the system payload returned with the fresh CPU fetch. The separately
  // loaded system snapshot may be older and can contain a null uptime.
  const system = { ...(systemData ?? {}), ...(data.system ?? {}) }
  const uptimeSeconds = isNum(data.uptime_seconds) ? data.uptime_seconds : isNum(system.uptime_seconds) ? system.uptime_seconds : (() => {
    const boot = Date.parse(String(system.last_boot_time ?? ""))
    return Number.isFinite(boot) ? Math.max(0, (Date.now() - boot) / 1000) : null
  })()
  const info = [["Processor", data.identity?.model ?? data.model], ["Manufacturer", data.identity?.manufacturer], ["Architecture", system.architecture], ["Physical cores", physical], ["Logical processors", logical], ["Current speed", currentSpeed], ["Maximum speed", maxSpeed], ["Virtualization", data.identity?.virtualization], ["L1 cache", data.identity?.l1_cache], ["L2 cache", data.identity?.l2_cache], ["L3 cache", data.identity?.l3_cache], ["CPU ID", data.identity?.cpu_id]]
  const stat = (label: string, value: ReactNode, color: string, visual?: ReactNode) => <div className="flex min-h-[132px] flex-col rounded-xl border p-3 shadow-sm" style={{ background: C.card, borderColor: C.borderLight }}><div className="flex items-start gap-2"><span className="text-xl" style={{ color }}>{label === "CPU Usage" ? "◉" : label === "Cores" ? "▣" : label === "Threads" ? "⌘" : label === "Processes" ? "▦" : label === "CPU Speed" ? "◔" : "◷"}</span><div><div className="text-xs font-semibold" style={{ color: C.text }}>{label}</div><div className="mt-1 text-xl font-bold" style={{ color: C.text }}>{value}</div></div></div><div className="mt-auto pt-3 h-7">{visual ?? <div className="flex h-full items-center justify-center text-[10px]" style={{ color: C.muted }}>N/A</div>}</div></div>
  const progress = (value: number | null, color: string) => <div className="h-2 rounded-full" style={{ background: C.borderLight }}><div className="h-full rounded-full" style={{ width: `${Math.max(0, Math.min(100, value ?? 0))}%`, background: color }} /></div>
  const panel = (title: string, children: ReactNode, className = "") => <div className={`rounded-xl border p-4 ${className}`} style={{ background: C.card, borderColor: C.borderLight }}>{children}</div>
  const warning = thresholdWarning(usage, threshold)
  return <div className="rounded-xl border p-1" style={{ background: C.bg, borderColor: warning ? C.warning : C.borderLight }}>
    <style>{`.cpu-dash-table th{background:var(--wd-table-header,var(--t-table-header));color:var(--wd-muted,var(--t-muted));font-size:10px}.cpu-dash-table td{border-top:1px solid var(--wd-border-light,var(--t-border-light));color:var(--wd-text,var(--t-text));font-size:11px;padding:6px 8px}.cpu-info-row{display:grid;grid-template-columns:44% 56%;border-top:1px solid var(--wd-border-light,var(--t-border-light));padding:7px 8px;font-size:11px}.cpu-info-row:first-child{border-top:0}`}</style>
    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-6">
      {stat("CPU Usage", <>{fmtPct(usage)}{warning && <WarningBadge threshold={threshold} />}</>, C.accent, usage == null ? null : progress(usage, C.accent))}
      {stat("Cores", physical ?? NA, C.accent, progress(physical && logical ? physical * 100 / logical : null, C.accent))}
      {stat("Threads", data.thread_count ?? NA, C.accent)}
      {stat("Processes", data.process_count ?? NA, C.accent)}
      {stat("CPU Speed", currentSpeed, C.accent)}
      {stat("Uptime", fmtUptime(uptimeSeconds ?? (() => { const boot = Date.parse(String(system.last_boot_time ?? "")); return Number.isFinite(boot) ? Math.max(0, (Date.now() - boot) / 1000) : null })()), C.accent)}
    </div>
    <div className="mt-3 grid gap-3 xl:grid-cols-[1.15fr_1fr_.88fr]">
      {panel("CPU Usage History", <><div className="flex items-center justify-between"><b className="text-sm" style={{ color: C.text }}>⚙ CPU Usage History</b><select className="rounded border px-2 py-1 text-[10px]" style={inputStyle} defaultValue="24h"><option value="24h">Last 24 Hours</option></select></div><div className="flex h-56 items-center justify-center text-center text-xs" style={{ color: C.muted }}>Historical CPU samples are not stored for Windows monitoring.</div></>)}
      {panel("CPU Load (Per Core)", <><div className="flex items-center justify-between"><b className="text-sm" style={{ color: C.text }}>⚙ CPU Load (Per Core)</b><span className="text-[10px]" style={{ color: C.muted }}>Live sample</span></div><div className="mt-4 space-y-3">{perCpu.length ? perCpu.map((row, i) => <Bar key={row.name ?? i} label={`Core ${row.name ?? i}`} value={row.usage_percent} color={C.accent} />) : <div className="flex h-48 items-center justify-center text-xs" style={{ color: C.muted }}>Per-core data unavailable.</div>}</div></>)}
      {panel("CPU Information", <><b className="text-sm" style={{ color: C.text }}>⚙ CPU Information</b><div className="mt-3">{info.map(([label, value]) => <div className="cpu-info-row" key={label}><span style={{ color: C.muted }}>{label}</span><span className="break-words text-right" style={{ color: C.text }}>{value == null || value === "" ? NA : String(value)}</span></div>)}</div></>)}
    </div>
    {panel("Top CPU Processes", <><div className="flex flex-wrap items-center justify-between gap-3"><b className="text-sm text-slate-800">⚙ Top CPU Processes</b><div className="flex gap-2"><button type="button" className="text-lg">↻</button><select className="rounded border px-2 py-1 text-[10px]" defaultValue="10"><option value="10">Top 10</option><option value="20">Top 20</option><option value="50">Top 50</option></select><input className="rounded border px-2 py-1 text-[10px]" placeholder="Search processes…" /></div></div><div className="mt-3 overflow-x-auto"><table className="cpu-dash-table w-full min-w-[900px] text-left"><thead><tr>{["#", "Process Name", "PID", "CPU Usage", "Memory Usage", "Threads", "Status", "Path"].map((x) => <th className="px-2 py-2" key={x}>{x}</th>)}</tr></thead><tbody>{processes.length ? processes.slice(0, 50).map((row, i) => <tr key={`${row.pid ?? "process"}-${i}`}><td>{i + 1}</td><td>{row.name ?? NA}</td><td>{row.pid ?? NA}</td><td>{NA}</td><td>{row.memory_bytes == null ? NA : fmtBytes(row.memory_bytes)}</td><td>{row.thread_count ?? NA}</td><td>{row.status ?? NA}</td><td className="max-w-[260px] truncate">{row.path ?? NA}</td></tr>) : <tr><td colSpan={8} className="p-7 text-center text-xs text-slate-400">Process-level metrics are unavailable for this device.</td></tr>}</tbody></table></div></>)}
    {panel("Advanced CPU Metrics", <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{[["Processor queue length", "processor_queue_length"], ["User time percentage", "user_time_percent"], ["Privileged time percentage", "privileged_time_percent"], ["Idle time percentage", "idle_time_percent"], ["Interrupts per second", "interrupts_per_sec"], ["Context switches per second", "context_switches_per_sec"]].map(([label, key]) => <Tile key={key} label={label} value={counterValue(key)} sub={`status: ${counters[key]?.status ?? NA}`} />)}</div>)}
    {perCpu.length > 0 && panel("Per Logical CPU Details", <div className="overflow-x-auto"><table className="cpu-dash-table w-full min-w-[760px] text-left"><thead><tr>{["Logical CPU", "Usage", "User Time", "Privileged Time", "Idle Time", "Interrupts/sec", "Context Switches/sec"].map((x) => <th className="px-2 py-2" key={x}>{x}</th>)}</tr></thead><tbody>{perCpu.map((row, i) => <tr key={row.name ?? i}><td>{row.name ?? `CPU ${i}`}</td><td>{fmtPct(row.usage_percent)}</td><td>{fmtPct(row.user_percent)}</td><td>{fmtPct(row.privileged_percent)}</td><td>{fmtPct(row.idle_percent)}</td><td>{row.interrupts_per_sec ?? NA}</td><td>{row.context_switches_per_sec ?? NA}</td></tr>)}</tbody></table></div>)}
  </div>
}

/* ════════════════════════════════════════════════════════════════
   Memory panel
   ════════════════════════════════════════════════════════════════ */
function MemoryIcon({ type, size = 16 }: { type: "memory" | "cpu" | "check" | "layers" | "physical" | "virtual" | "paging" | "kernel" | "metric"; size?: number }) {
  const paths: Record<string, string> = {
    memory: "M4 5h16M4 12h16M4 19h16M7 3v18M17 3v18", cpu: "M5 5h14v14H5zM8 8h8v8H8z", check: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0-0-18Zm-4 9 3 3 5-6", layers: "M12 4 4 8l8 4 8-4-8-4Zm-8 8 8 4 8-4M4 16l8 4 8-4", physical: "M5 5h14v14H5zM8 9h8M8 13h5", virtual: "M4 7h16M7 4v16M17 4v16", paging: "M6 18V9m6 9V5m6 13v-6", kernel: "M12 4v16M4 12h16M6 6l12 12M18 6 6 18", metric: "M5 12h14M12 5v14",
  }
  return <svg aria-hidden="true" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d={paths[type]} /></svg>
}

const memoryMetricIcon = (label: string): "memory" | "cpu" | "check" | "layers" | "physical" | "virtual" | "paging" | "kernel" | "metric" => label.includes("Usage") ? "metric" : label.includes("Physical") ? "physical" : label.includes("Commit") || label.includes("Cached") ? "layers" : label.includes("Pool") ? "kernel" : "paging"

function MemoryBody({ data, threshold, cpuData }: { data: any; threshold: number; cpuData?: any }) {
  const counters = data.counters || {}
  const k = (name: string) => counters[name] as WindowsMemoryCounter | undefined
  const blue = "#3478F6"
  const teal = "#13B8A6"
  const violet = "#8B5CF6"
  const orange = "#F59E0B"
  const red = "#EF6A6A"
  const warning = thresholdWarning(data.usage_percent, threshold)
  const bytesGiB = (v: unknown) => isNum(v) ? `${(v / 1024 ** 3).toFixed(2)} GiB` : NA
  const counterValue = (name: string) => k(name)?.value
  const counterBytes = (name: string) => bytesGiB(counterValue(name))
  const counterRate = (name: string) => isNum(counterValue(name)) ? `${counterValue(name)} /sec` : counterText(k(name), String)
  const processes = Array.isArray(cpuData?.processes) ? [...cpuData.processes].filter((p) => isNum(p?.memory_bytes)).sort((a, b) => b.memory_bytes - a.memory_bytes).slice(0, 8) : []
  const composition = [
    ["Used", data.used_bytes, blue], ["Available", data.free_bytes, teal],
    ["Cached", counterValue("cache_bytes"), violet], ["Paged pool", counterValue("pool_paged_bytes"), orange],
    ["Non-paged pool", counterValue("pool_nonpaged_bytes"), red],
  ] as const
  const detailRows: Array<[string, ReactNode]> = [
    ["Total Physical Memory", bytesGiB(data.total_bytes)], ["Used Physical Memory", bytesGiB(data.used_bytes)],
    ["Available Physical Memory", bytesGiB(data.free_bytes)], ["Memory Usage %", fmtPct(data.usage_percent)],
    ["Committed Memory", counterBytes("committed_bytes")], ["Commit Limit", counterBytes("commit_limit")],
    ["Commit Usage %", counterText(k("percent_committed_bytes_in_use"), (v) => `${v.toFixed(1)}%`)],
    ["Cached Memory", counterBytes("cache_bytes")], ["Pages/sec", counterRate("pages_per_sec")],
    ["Reads/sec", counterRate("page_reads_per_sec")], ["Writes/sec", counterRate("page_writes_per_sec")],
    ["Page Faults/sec", counterRate("page_faults_per_sec")], ["Paged Pool", counterBytes("pool_paged_bytes")],
    ["Non-Paged Pool", counterBytes("pool_nonpaged_bytes")],
  ]
  return (
    <div className="space-y-4 rounded-xl border p-1" style={{ borderColor: warning ? C.warning : "transparent" }}>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {[["memory", "Total Memory", bytesGiB(data.total_bytes), "Physical RAM", violet], ["cpu", "Used Memory", bytesGiB(data.used_bytes), `${fmtPct(data.usage_percent)} used`, blue], ["check", "Available Memory", bytesGiB(data.free_bytes), isNum(data.total_bytes) && isNum(data.free_bytes) ? `${((data.free_bytes / data.total_bytes) * 100).toFixed(1)}% available` : NA, "#16A34A"], ["layers", "Committed Memory", `${counterBytes("committed_bytes")} / ${counterBytes("commit_limit")}`, `Commit ${counterText(k("percent_committed_bytes_in_use"), (v) => `${v.toFixed(1)}%`)}`, orange]].map(([icon, label, value, sub, color]) => <div key={label} className="group flex min-h-[150px] flex-col rounded-xl border p-4 transition-shadow hover:shadow-sm" style={{ borderColor: C.borderLight, background: C.card, borderTop: `3px solid ${color}` }}><div className="flex items-center justify-between"><span className="flex h-9 w-9 items-center justify-center rounded-lg" style={{ color, background: `${color}18` }}><MemoryIcon type={icon as any} size={18} /></span><span className="text-[10px] font-semibold uppercase tracking-wider" style={{ color: C.muted }}>{label}</span></div><div className="mt-4 text-xl font-bold tracking-tight" style={{ color: C.text }}>{value}</div><div className="mt-1 text-[11px]" style={{ color: C.muted }}>{sub}</div>{(label === "Used Memory" || label === "Available Memory") && <div className="mt-auto pt-3"><div className="h-1.5 overflow-hidden rounded-full" style={{ background: C.borderLight }}><div className="h-full rounded-full" style={{ width: `${label === "Used Memory" ? data.usage_percent ?? 0 : isNum(data.total_bytes) && isNum(data.free_bytes) ? data.free_bytes * 100 / data.total_bytes : 0}%`, background: color }} /></div></div>}</div>)}
      </div>
      <div className="grid gap-4 xl:grid-cols-[1.15fr_.85fr]">
        <Group title="Memory Usage" hint="Last 24 Hours">
          <div className="flex h-52 flex-col items-center justify-center rounded-lg border border-dashed text-center" style={{ borderColor: C.borderLight }}>
            <div className="text-3xl font-semibold" style={{ color: blue }}>{fmtPct(data.usage_percent)}</div>
            <div className="mt-2 text-xs" style={{ color: C.muted }}>Historical samples unavailable</div>
            <div className="mt-1 max-w-xs text-[10px]" style={{ color: C.muted }}>The current Windows snapshot API exposes the latest sample only.</div>
          </div>
        </Group>
        <Group title="Memory Composition" hint="Categories may overlap">
          <div className="space-y-3">{composition.map(([label, value, color]) => {
            const percent = isNum(value) && isNum(data.total_bytes) && data.total_bytes > 0 ? Math.min(100, value * 100 / data.total_bytes) : null
            return <div key={label}><div className="flex justify-between text-xs"><span style={{ color: C.text }}>{label}</span><span className="font-mono" style={{ color: C.muted }}>{bytesGiB(value)}{percent == null ? "" : ` · ${percent.toFixed(1)}% of RAM`}</span></div><div className="mt-1 h-2 overflow-hidden rounded-full" style={{ background: C.borderLight }}><div className="h-full rounded-full" style={{ width: `${percent ?? 0}%`, background: color }} /></div></div>
          })}</div>
          <div className="mt-3 text-[10px]" style={{ color: C.muted }}>Used, cached and pool values can overlap; percentages are shown independently of the total.</div>
        </Group>
      </div>
      <div className="grid gap-4 xl:grid-cols-[1.05fr_.95fr]">
        <Group title="Memory Details"><div className="grid gap-3 sm:grid-cols-2">{[["Physical Memory", "physical", detailRows.slice(0, 4)], ["Commit & Cache", "virtual", detailRows.slice(4, 8)], ["Paging Activity", "paging", detailRows.slice(8, 12)], ["Kernel Memory", "kernel", detailRows.slice(12)]].map(([title, sectionIcon, rows]) => <section key={title as string} className="rounded-lg border p-2.5" style={{ borderColor: C.borderLight, background: "#fbfdff" }}><h4 className="mb-1.5 flex items-center gap-2 text-xs font-bold" style={{ color: C.text }}><span className="flex h-6 w-6 items-center justify-center rounded-md" style={{ color: blue, background: `${blue}12` }}><MemoryIcon type={sectionIcon as any} size={14} /></span>{title}</h4><dl>{(rows as Array<[string, ReactNode]>).map(([label, value]) => <div key={label} className="group flex items-center justify-between gap-3 border-t py-2 first:border-t-0" style={{ borderColor: C.borderLight }}><dt className="flex min-w-0 items-center gap-2 text-[11px]" style={{ color: C.muted }}><span style={{ color: blue }}><MemoryIcon type={memoryMetricIcon(label)} size={14} /></span><span className="truncate">{label}</span></dt><dd className="shrink-0 text-right text-xs font-semibold" style={{ color: C.text }}>{label.includes("Usage") && value !== NA ? <span className="rounded-full px-2 py-0.5 text-[10px]" style={{ color: violet, background: `${violet}14` }}>{value}</span> : value}</dd></div>)}</dl></section>)}</div></Group>
        <Group title="Top Memory Consuming Processes" hint="Live process snapshot">
          {processes.length ? <div className="space-y-3">{processes.map((p, index) => <div key={`${p.pid ?? p.name}-${index}`}><div className="flex justify-between gap-3 text-xs"><span className="truncate" style={{ color: C.text }}>{p.name ?? NA}</span><span className="shrink-0 font-mono" style={{ color: C.muted }}>{fmtBytes(p.memory_bytes)}</span></div><Bar label={`PID ${p.pid ?? NA}`} value={isNum(data.total_bytes) && data.total_bytes > 0 ? p.memory_bytes * 100 / data.total_bytes : null} color={index % 2 ? teal : blue} /></div>)}</div> : <div className="flex min-h-48 items-center justify-center rounded-lg border border-dashed text-center text-xs" style={{ borderColor: C.borderLight, color: C.muted }}>Process data unavailable</div>}
        </Group>
      </div>
    </div>
  )
}

/* ════════════════════════════════════════════════════════════════
   Disk panel
   ════════════════════════════════════════════════════════════════ */
const DISK_TILES: Array<[string, string, (v: number) => string]> = [
  ["Read IOPS", "read_iops", (v) => `${v} ops/s`],
  ["Write IOPS", "write_iops", (v) => `${v} ops/s`],
  ["Total IOPS", "total_iops", (v) => `${v} ops/s`],
  ["Read throughput", "read_bytes_per_sec", fmtThroughput],
  ["Write throughput", "write_bytes_per_sec", fmtThroughput],
  ["Total throughput", "total_bytes_per_sec", fmtThroughput],
  ["Read latency", "read_latency_ms", (v) => formatLatency(v)],
  ["Write latency", "write_latency_ms", (v) => formatLatency(v)],
  ["Avg latency", "average_latency_ms", (v) => formatLatency(v)],
  ["Avg queue", "average_queue_length", String],
  ["Current queue", "current_queue_length", String],
  ["Split I/O", "split_io_per_sec", (v) => `${v} ops/s`],
]
function DiskCounters({ metrics }: { metrics: Record<string, WindowsDiskCounter> }) {
  return (
    <div>
      <div className="mb-3">
        <Bar label="Disk time" value={metrics.percent_disk_time?.value} right={counterText(metrics.percent_disk_time, (v) => `${v.toFixed(1)}%`)} />
      </div>
      <div className="grid grid-cols-2 gap-2 md:grid-cols-3 lg:grid-cols-4">
        {DISK_TILES.map(([label, key, fmt]) => <Tile key={key} label={label} value={counterText(metrics[key], fmt)} />)}
      </div>
    </div>
  )
}
function DiskBody({ data, threshold }: { data: any; threshold: number }) {
  const [expanded, setExpanded] = useState<Record<string, boolean>>({})
  const [aggregateOpen, setAggregateOpen] = useState(false)
  const disks = (Array.isArray(data) ? data : []) as WindowsDiskCapacity[]
  const perf: any = disks[0]?.performance
  const sumNullable = (key: "size_bytes" | "used_bytes" | "free_bytes") => {
    const values = disks.map((d) => d[key]).filter(isNum)
    return values.length ? values.reduce((sum, value) => sum + value, 0) : null
  }
  const totalSize = sumNullable("size_bytes")
  const totalUsed = sumNullable("used_bytes")
  const totalFree = sumNullable("free_bytes")
  const logicalRows = Array.isArray(perf?.logical) ? perf.logical : []
  const physicalRows = Array.isArray(perf?.physical) ? perf.physical : []
  const aggregateIops = perf?.aggregate?.logical?.total_iops
  const aggregateThroughput = perf?.aggregate?.logical?.total_bytes_per_sec
  const toggle = (key: string) => setExpanded((current) => ({ ...current, [key]: !current[key] }))
  const counterDisplay = (metrics: Record<string, WindowsDiskCounter>, key: string, formatter: (value: number) => string = String) => counterText(metrics[key], formatter)
  const performanceRows = [
    ["Read IOPS", "read_iops", (v: number) => `${v} ops/s`], ["Write IOPS", "write_iops", (v: number) => `${v} ops/s`], ["Total IOPS", "total_iops", (v: number) => `${v} ops/s`],
    ["Read throughput", "read_bytes_per_sec", fmtThroughput], ["Write throughput", "write_bytes_per_sec", fmtThroughput], ["Total throughput", "total_bytes_per_sec", fmtThroughput],
    ["Read latency", "read_latency_ms", (v: number) => formatLatency(v)], ["Write latency", "write_latency_ms", (v: number) => formatLatency(v)], ["Average latency", "average_latency_ms", (v: number) => formatLatency(v)],
    ["Average queue", "average_queue_length", String], ["Current queue", "current_queue_length", String], ["Split I/O", "split_io_per_sec", (v: number) => `${v} ops/s`], ["Disk time", "percent_disk_time", (v: number) => `${v.toFixed(1)}%`],
  ] as Array<[string, string, (value: number) => string]>
  const performanceGroups: Array<[string, Array<[string, string, (value: number) => string]>]> = [
    ["Read/Write IOPS", performanceRows.slice(0, 3)],
    ["Throughput", performanceRows.slice(3, 6)],
    ["Latency", performanceRows.slice(6, 9)],
    ["Queue & Disk Time", performanceRows.slice(9)],
  ]
  const performanceTable = (kind: "Logical" | "Physical", rows: any[]) => <Group title={`${kind} Disk Performance`}>
    {rows.length ? <div className="overflow-x-auto"><table className="w-full min-w-[620px] text-left"><thead><tr>{["Disk", "Read IOPS", "Write IOPS", "Total IOPS", "Throughput", "Latency", "Details"].map((label) => <th key={label} className="px-3 py-2 font-mono text-[10px] uppercase" style={{ color: C.muted, background: "var(--wd-table-header, var(--t-table-header))" }}>{label}</th>)}</tr></thead><tbody>{rows.map((row: any) => { const metrics = row.metrics ?? {}; const key = `${kind}:${row.instance}`; return <><tr key={key} className="border-t" style={{ borderColor: C.borderLight }}><td className="px-3 py-2 text-xs font-semibold" style={{ color: C.text }}>{row.instance ?? NA}</td><td className="px-3 py-2 text-xs">{counterDisplay(metrics, "read_iops", (v) => `${v} ops/s`)}</td><td className="px-3 py-2 text-xs">{counterDisplay(metrics, "write_iops", (v) => `${v} ops/s`)}</td><td className="px-3 py-2 text-xs">{counterDisplay(metrics, "total_iops", (v) => `${v} ops/s`)}</td><td className="px-3 py-2 text-xs">{counterDisplay(metrics, "total_bytes_per_sec", fmtThroughput)}</td><td className="px-3 py-2 text-xs">{counterDisplay(metrics, "average_latency_ms", formatLatency)}</td><td className="px-3 py-2"><button type="button" onClick={() => toggle(key)} aria-expanded={Boolean(expanded[key])} aria-controls={`${key}-details`} className="inline-flex items-center gap-1 rounded border px-2 py-1 font-mono text-[10px] font-semibold" style={{ color: C.accent, borderColor: C.borderLight }}>{expanded[key] ? "Collapse" : "Details"}<span aria-hidden>{expanded[key] ? "⌃" : "⌄"}</span></button></td></tr>{expanded[key] && <tr id={`${key}-details`} key={`${key}:details`} className="border-t" style={{ borderColor: C.borderLight, background: "var(--wd-table-hover, var(--t-table-row-hover))" }}><td colSpan={7} className="px-3 py-3"><div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">{performanceGroups.map(([group, groupRows]) => <section key={group} className="rounded-lg border p-2.5" style={{ borderColor: C.borderLight, background: C.card }}><h4 className="mb-2 border-b pb-1.5 font-mono text-[10px] font-bold uppercase tracking-wide" style={{ color: C.accent, borderColor: C.borderLight }}>{group}</h4><div className="space-y-1.5">{groupRows.map(([label, metric, formatter]) => <div key={metric} className="flex items-center justify-between gap-2"><span className="text-[10px]" style={{ color: C.muted }}>{label}</span><span className="text-right text-xs font-semibold" style={{ color: C.text }}>{counterDisplay(metrics, metric, formatter)}</span></div>)}</div></section>)}</div></td></tr>}</> })}</tbody></table></div> : <div className="text-xs" style={{ color: C.muted }}>No {kind.toLowerCase()} performance instances.</div>}
  </Group>
  const warning = disks.some((disk) => thresholdWarning(disk.usage_percent, threshold))
  return (
    <div className="space-y-4 rounded-xl border p-1" style={{ borderColor: warning ? C.warning : C.borderLight, background: C.bg }}>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {[
          ["◫", "Total Capacity", fmtBytes(totalSize), `${disks.length} volume${disks.length === 1 ? "" : "s"}`, C.accent],
          ["◒", "Used", fmtBytes(totalUsed), totalSize != null && totalUsed != null && totalSize > 0 ? `${(totalUsed * 100 / totalSize).toFixed(1)}% used` : NA, C.warning],
          ["✓", "Free", fmtBytes(totalFree), totalSize != null && totalFree != null && totalSize > 0 ? `${(totalFree * 100 / totalSize).toFixed(1)}% free` : NA, C.accent],
          ["⇄", "Disk I/O", counterText(aggregateIops, (v) => `${v} ops/s`), `Throughput ${counterText(aggregateThroughput, fmtThroughput)}`, C.accent],
        ].map(([icon, label, value, sub, color]) => {
          const percentage = label === "Used" && totalSize && totalUsed != null ? totalUsed * 100 / totalSize : label === "Free" && totalSize && totalFree != null ? totalFree * 100 / totalSize : null
          return <div key={String(label)} className="min-w-0 rounded-xl border p-3 transition-shadow hover:shadow-sm" style={{ borderColor: C.borderLight, background: C.card, borderTop: `3px solid ${C.border}` }}><div className="flex items-center justify-between gap-2"><span className="flex h-8 w-8 items-center justify-center rounded-lg text-sm font-bold" style={{ color, background: `${color}18` }}>{icon}</span><span className="font-mono text-[10px] uppercase tracking-wide" style={{ color: C.muted }}>{label}</span></div><div className="mt-3 break-words text-lg font-bold" style={{ color: MUTED_VALUES.has(String(value)) ? C.muted : C.text }}>{value}</div><div className="mt-1 break-words font-mono text-[10px]" style={{ color: C.muted }}>{sub}</div>{percentage != null && <div className="mt-3 h-1.5 overflow-hidden rounded-full" style={{ background: C.borderLight }}><div className="h-full rounded-full" style={{ width: `${Math.min(100, Math.max(0, percentage))}%`, background: color }} /></div>}</div>
        })}
      </div>
      {warning && <div className="mb-2"><WarningBadge threshold={threshold} /> <span className="text-xs" style={{ color: C.muted }}>At least one volume has reached its capacity threshold.</span></div>}
      <Group title="Disk Inventory" hint="Logical volumes">
        {disks.length ? <div className="overflow-x-auto"><table className="w-full min-w-[680px] text-left"><thead><tr>{["Drive", "Capacity", "Used", "Free", "Usage", "Status"].map((label) => <th key={label} className="px-3 py-2 font-mono text-[10px] uppercase" style={{ color: C.muted, background: "var(--wd-table-header, var(--t-table-header))" }}>{label}</th>)}</tr></thead><tbody>{disks.map((d) => { const status = d.usage_percent == null ? "Unavailable" : thresholdWarning(d.usage_percent, threshold) ? "Warning" : "Healthy"; return <tr key={d.device_id} className="border-t" style={{ borderColor: C.borderLight }}><td className="px-3 py-2 text-xs font-semibold" style={{ color: C.text }}>{d.device_id || NA}<div className="font-normal" style={{ color: C.muted }}>{d.volume_name || "Unnamed volume"}</div></td><td className="px-3 py-2 text-xs">{fmtBytes(d.size_bytes)}</td><td className="px-3 py-2 text-xs">{fmtBytes(d.used_bytes)}</td><td className="px-3 py-2 text-xs">{fmtBytes(d.free_bytes)}</td><td className="min-w-[150px] px-3 py-2 text-xs"><div className="flex items-center gap-2"><span>{fmtPct(d.usage_percent)}</span><div className="h-1.5 flex-1 overflow-hidden rounded-full" style={{ background: C.borderLight }}><div className="h-full" style={{ width: `${d.usage_percent ?? 0}%`, background: status === "Warning" ? C.warning : C.accent }} /></div></div></td><td className="px-3 py-2"><Badge text={status} color={status === "Warning" ? C.warning : status === "Healthy" ? C.accent : C.muted} /></td></tr> })}</tbody></table></div> : <EmptyState text="No volumes reported." />}
      </Group>
      <div className="grid gap-3 md:grid-cols-2"><Group title="Disk Usage" hint="Last 24 Hours"><div className="flex min-h-24 items-center justify-center rounded-lg border border-dashed text-center text-xs" style={{ borderColor: C.borderLight, color: C.muted }}>Historical data unavailable</div></Group><Group title="Disk I/O" hint="Last 24 Hours"><div className="flex min-h-24 items-center justify-center rounded-lg border border-dashed text-center text-xs" style={{ borderColor: C.borderLight, color: C.muted }}>Historical data unavailable</div></Group></div>
      {perf ? (
        <div className="space-y-3">
          {performanceTable("Logical", logicalRows)}
          {performanceTable("Physical", physicalRows)}
          <div className="rounded-xl border" style={{ borderColor: C.border }}>
            <button type="button" onClick={() => setAggregateOpen((open) => !open)} className="flex w-full items-center justify-between gap-3 p-4 text-left" aria-expanded={aggregateOpen}>
              <span><span className="font-display text-sm font-bold" style={{ color: C.text }}>Aggregate disk metrics</span><span className="ml-2 font-mono text-[10px] uppercase" style={{ color: C.muted }}>Logical + physical</span></span>
              <span className="font-mono text-[10px] font-bold" style={{ color: C.accent }}>{aggregateOpen ? "HIDE" : "SHOW"} · {aggregateOpen ? "⌃" : "⌄"}</span>
            </button>
            {aggregateOpen && <div className="grid gap-3 border-t p-3 md:grid-cols-2" style={{ borderColor: C.borderLight }}>
              {(["logical", "physical"] as const).map((kind) => (
                <Group key={kind} title={`${kind} aggregate`}>
                  {perf.aggregate?.[kind] ? <DiskCounters metrics={perf.aggregate[kind]} /> : <div className="text-xs" style={{ color: C.muted }}>Unavailable</div>}
                </Group>
              ))}
            </div>}
          </div>
        </div>
      ) : <div className="text-xs" style={{ color: C.muted }}>Disk performance unavailable in this snapshot.</div>}
    </div>
  )
}

/* ════════════════════════════════════════════════════════════════
   Network panel
   ════════════════════════════════════════════════════════════════ */
function NetworkBody({ data }: { data: any }) {
  const adapters: Array<Record<string, any>> = Array.isArray(data) ? data : []
  if (!adapters.length) return <EmptyState />
  const [query, setQuery] = useState("")
  const [filter, setFilter] = useState<"all" | "connected" | "disconnected" | "unknown">("all")
  const [expanded, setExpanded] = useState<string | null>(null)
  const active = adapters.filter((a) => /^connected$/i.test(String(a.interface_status ?? ""))).length
  const rx = adapters.reduce((s, a) => s + (isNum(a.rx_bytes_per_sec) ? a.rx_bytes_per_sec : 0), 0)
  const tx = adapters.reduce((s, a) => s + (isNum(a.tx_bytes_per_sec) ? a.tx_bytes_per_sec : 0), 0)
  const statusOf = (a: Record<string, any>) => {
    const value = String(a.interface_status ?? "").trim()
    return /^connected$/i.test(value) ? "connected" : /disconnected|down|disabled/i.test(value) ? "disconnected" : "unknown"
  }
  const filtered = adapters.filter((a) => {
    const name = String(a.name ?? a.description ?? "Network adapter")
    return name.toLowerCase().includes(query.trim().toLowerCase()) && (filter === "all" || statusOf(a) === filter)
  })
  const value = (v: unknown, fallback = NA) => v == null || v === "" ? fallback : String(v)
  const statusColor = (status: string) => status === "connected" ? C.accent : status === "disconnected" ? C.danger : C.muted
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">
        <Tile label="Total network adapters" value={adapters.length} accent={C.accent} />
        <Tile label="Active / connected" value={active} accent={C.accent} />
        <Tile label="Total receive rate" value={fmtRate(rx)} accent={C.accent} />
        <Tile label="Total transmit rate" value={fmtRate(tx)} accent={C.accent} />
      </div>
      <div className="rounded-xl border" style={{ borderColor: C.border, background: C.card }}>
        <div className="flex flex-col gap-2 border-b p-3 sm:flex-row" style={{ borderColor: C.borderLight }}>
          <input aria-label="Search network adapters" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search adapter name" className="min-w-0 flex-1 rounded-lg px-3 py-2 text-xs outline-none focus:ring-2" style={inputStyle} />
          <select aria-label="Filter network adapters" value={filter} onChange={(e) => setFilter(e.target.value as typeof filter)} className="rounded-lg px-3 py-2 text-xs outline-none" style={inputStyle}>
            <option value="all">All statuses</option><option value="connected">Connected</option><option value="disconnected">Disconnected</option><option value="unknown">Unknown</option>
          </select>
        </div>
        <div className="overflow-x-auto"><table className="w-full min-w-[920px] text-left"><thead><tr style={{ background: "#f4f8fc" }}>{["Adapter name", "Interface / index", "MAC address", "Link speed", "Receive rate", "Transmit rate", "Connection status", "Details"].map((label) => <th key={label} className="px-3 py-2 font-mono text-[10px] uppercase tracking-wide" style={{ color: C.muted }}>{label}</th>)}</tr></thead><tbody>
          {filtered.map((a) => {
            const key = networkRowKey(a), status = statusOf(a), open = expanded === key
            const known = new Set(["name", "description", "interface_index", "adapter_index", "mac_address", "link_speed_bps", "rx_bytes_per_sec", "tx_bytes_per_sec", "interface_status"])
            const extra = Object.entries(a).filter(([k]) => !known.has(k) && k !== "ipv4_addresses" && k !== "ipv6_addresses")
            const addresses = (v: unknown) => Array.isArray(v) ? v.filter((item): item is string => typeof item === "string" && item.length > 0) : []
            return <Fragment key={key}>
              <tr key={key} className="border-t align-top" style={{ borderColor: C.borderLight }}><td className="max-w-0 break-words px-3 py-3 text-xs font-semibold">{value(a.name ?? a.description, "Network adapter")}<div className="mt-0.5 break-words text-[10px] font-normal" style={{ color: C.muted }}>{value(a.description)}</div></td><td className="px-3 py-3 font-mono text-xs">{value(a.interface_index)}{a.adapter_index != null ? <div style={{ color: C.muted }}>Adapter {a.adapter_index}</div> : null}</td><td className="break-all px-3 py-3 font-mono text-xs">{value(a.mac_address)}</td><td className="px-3 py-3 text-xs">{fmtLinkSpeed(isNum(a.link_speed_bps) ? a.link_speed_bps : null)}</td><td className="px-3 py-3 text-xs">{fmtRate(isNum(a.rx_bytes_per_sec) ? a.rx_bytes_per_sec : null)}</td><td className="px-3 py-3 text-xs">{fmtRate(isNum(a.tx_bytes_per_sec) ? a.tx_bytes_per_sec : null)}</td><td className="px-3 py-3"><span className="rounded-full border px-2 py-1 font-mono text-[10px] font-semibold uppercase" style={{ color: statusColor(status), borderColor: statusColor(status) }}>{value(a.interface_status, "Unknown")}</span></td><td className="px-3 py-3"><button type="button" aria-expanded={open} onClick={() => setExpanded(open ? null : key)} className="rounded-md border px-2 py-1 font-mono text-[10px] font-semibold" style={{ color: C.accent, borderColor: C.border }}>{open ? "HIDE" : "VIEW"}</button></td></tr>
              {open && <tr key={`${key}:details`}><td colSpan={8} className="max-w-0 border-b p-3" style={{ borderColor: C.borderLight, background: "#f8fbff" }}><div className="grid min-w-0 grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3"><Group title="Adapter Identity"><KV rows={[["Name", value(a.name)], ["Description", value(a.description)], ["Interface index", value(a.interface_index)], ["Adapter index", value(a.adapter_index)]]} /></Group><Group title="Connection & Link"><KV rows={[["MAC address", value(a.mac_address)], ["Status", value(a.interface_status, "Unknown")], ["Link speed", fmtLinkSpeed(isNum(a.link_speed_bps) ? a.link_speed_bps : null)]]} /></Group><Group title="Traffic Performance"><KV rows={[["Receive rate", fmtRate(isNum(a.rx_bytes_per_sec) ? a.rx_bytes_per_sec : null)], ["Transmit rate", fmtRate(isNum(a.tx_bytes_per_sec) ? a.tx_bytes_per_sec : null)]]} /></Group></div><div className="mt-3 grid min-w-0 grid-cols-1 gap-3 border-t pt-3 md:grid-cols-2" style={{ borderColor: C.borderLight }}><div className="min-w-0"><div className={labelCls} style={{ color: C.muted }}>IPv4 addresses</div><div className="mt-1 break-words font-mono text-xs">{addresses(a.ipv4_addresses).length ? addresses(a.ipv4_addresses).join(", ") : NA}</div></div><div className="min-w-0"><div className={labelCls} style={{ color: C.muted }}>IPv6 addresses</div><div className="mt-1 break-all font-mono text-xs">{addresses(a.ipv6_addresses).length ? addresses(a.ipv6_addresses).join(", ") : NA}</div></div></div>{extra.length > 0 && <div className="mt-3 border-t pt-3" style={{ borderColor: C.borderLight }}><KV rows={extra.map(([k, v]) => [k.replaceAll("_", " "), value(v)] as [string, ReactNode])} /></div>}</td></tr>}
            </Fragment>
          })}
          {!filtered.length && <tr><td colSpan={8} className="p-8 text-center font-mono text-xs" style={{ color: C.muted }}>No adapters match the current search or status filter.</td></tr>}
        </tbody></table></div>
      </div>
      <div className="grid gap-3 md:grid-cols-2"><Group title="Network Utilization" hint="Last 24 Hours"><div className="flex min-h-24 items-center justify-center rounded-lg border border-dashed text-center text-xs" style={{ borderColor: C.borderLight, color: C.muted }}>Historical data unavailable</div></Group><Group title="Network Traffic" hint="Last 24 Hours"><div className="flex min-h-24 items-center justify-center rounded-lg border border-dashed text-center text-xs" style={{ borderColor: C.borderLight, color: C.muted }}>Historical data unavailable</div></Group></div>
    </div>
  )
}

function USBBody({ inventory }: { inventory: WindowsUSBInventory }) {
  const devices = Array.isArray(inventory.usb?.devices) ? inventory.usb.devices : []
  const controllers = Array.isArray(inventory.usb?.controllers) ? inventory.usb.controllers : []
  const hubs = Array.isArray(inventory.usb?.hubs) ? inventory.usb.hubs : []
  const hubUnavailable = inventory.usb?.collection_errors?.some((error) => error.source === "Win32_USBHub") ?? false
  const presence = (d: any) => String(d.presence_state ?? (d.present === true ? "Present" : d.present === false ? "Absent" : "Unknown"))
  const health = (d: any) => String(d.driver_health ?? "Unknown")
  const classification = (d: any) => {
    const value = String(d.device_class ?? "").trim()
    if (!value) return String(d.device_type ?? "Unknown")
    const labels: Record<string, string> = {
      WPD: "WPD (Portable Device)",
      USB: "USB",
      HIDClass: "HID",
      DiskDrive: "Disk Drive",
      Camera: "Camera",
      Bluetooth: "Bluetooth",
    }
    return labels[value] ?? value
  }
  const statusColor = (value: string) => value === "Present" || value === "Healthy" ? C.accent : value === "Disabled" ? C.warning : value === "DriverError" ? C.danger : C.muted
  const count = (value: string) => devices.filter((d) => value === presence(d) || value === health(d)).length
  return (
    <div className="space-y-4">
      {inventory.status === "partial" && <div role="status" className="rounded-lg border p-3 font-mono text-xs" style={{ color: C.warning, borderColor: C.warning }}>Some USB inventory sources were unavailable; showing the collected results.</div>}
      <div className="grid grid-cols-2 gap-2 md:grid-cols-3 xl:grid-cols-6">
        <Tile label="Controllers" value={controllers.length} />
        <Tile label="Hubs" value={hubUnavailable ? "Unavailable" : hubs.length} />
        <Tile label="Devices" value={devices.length} />
        <Tile label="Present" value={count("Present")} accent={C.accent} />
        <Tile label="Disabled" value={count("Disabled")} accent={C.warning} />
        <Tile label="Driver errors" value={count("DriverError")} accent={C.danger} />
      </div>
      {inventory.status === "empty" && <EmptyState text="No USB inventory was reported by the Windows device." />}
      {inventory.usb.collection_errors?.length > 0 && <Group title="Collection warnings"><div className="space-y-2">{inventory.usb.collection_errors.map((e, i) => <div key={`${e.source}:${i}`} className="rounded border p-2 font-mono text-xs" style={{ color: C.warning, borderColor: C.borderLight }}>{e.source ?? "USB source"}: {e.error ?? e.status ?? "Unavailable"}</div>)}</div></Group>}
      {devices.length > 0 && <div className="grid gap-4 lg:grid-cols-2">{devices.map((d, index) => {
        const p = presence(d); const h = health(d)
        return <Group key={String(d.instance_id ?? `${d.name ?? "device"}:${index}`)} title={String(d.name ?? "USB device")}>
          <div className="flex flex-wrap gap-2 mb-3"><Badge text={p} color={statusColor(p)} /><Badge text={h} color={statusColor(h)} /></div>
          <KV rows={[
            ["Classification", classification(d)],
            ["Manufacturer", String(d.manufacturer ?? NA)],
            ["Vendor / Product", `${d.vendor_id ?? NA} / ${d.product_id ?? NA}`],
            ["Instance ID", <span className="break-all font-mono">{String(d.instance_id ?? NA)}</span>],
            ["PnP status", String(d.pnp_status ?? NA)],
          ]} />
        </Group>
      })}</div>}
    </div>
  )
}

/* ════════════════════════════════════════════════════════════════
   Hardware panel
   ════════════════════════════════════════════════════════════════ */
function HardwareBody({ hardware }: { hardware: WindowsHardwareSnapshot }) {
  const hw = hardware as any
  const blocks: Array<[string, any, Array<[string, string]>]> = [
    ["Computer System", hw.computer_system, [["Manufacturer", "manufacturer"], ["Model", "model"], ["System type", "system_type"], ["Domain", "domain"], ["Workgroup", "workgroup"], ["Domain joined", "part_of_domain"]]],
    ["System Product", hw.system_product, [["Vendor", "vendor"], ["Name", "name"], ["Version", "version"]]],
    ["Motherboard", hw.baseboard, [["Manufacturer", "manufacturer"], ["Product", "product"], ["Version", "version"]]],
    ["BIOS", hw.bios, [["Manufacturer", "manufacturer"], ["Version", "smbios_bios_version"], ["Release date", "release_date"]]],
  ]
  const show = (data: any, key: string) => {
    if (key === "part_of_domain") return data?.[key] == null ? NA : data[key] ? "Yes" : "No"
    if (key === "release_date") return fmtHardwareDate(data?.[key])
    return data?.[key] == null || data[key] === "" ? NA : String(data[key])
  }
  const processors: any[] = hw.processors ?? []
  const arrays: any[] = hw.memory_arrays ?? []
  const modules: any[] = hw.memory_modules ?? []
  const firstProcessor = processors[0]
  const ramBytes = modules.map((m) => m.capacity_bytes).filter(isNum).reduce((sum, value) => sum + value, 0)
  const summary = [
    ["Manufacturer", show(hw.computer_system, "manufacturer")],
    ["System model", show(hw.computer_system, "model")],
    ["Processor", firstProcessor?.name == null || firstProcessor.name === "" ? NA : String(firstProcessor.name)],
    ["Installed RAM", modules.some((m) => isNum(m.capacity_bytes)) ? fmtBytes(ramBytes) : NA],
  ] as Array<[string, ReactNode]>
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">
        {summary.map(([label, value]) => <Tile key={label} label={label} value={value} accent={C.accent} />)}
      </div>
      <div className="font-display text-base font-bold" style={{ color: C.text }}>System Information</div>
      <div className="grid gap-3 md:grid-cols-2">
        {blocks.map(([title, data, fields]) => (
          <Group key={title} title={title}>
            <KV rows={fields.map(([label, key]) => [label, show(data, key)] as [string, ReactNode])} />
          </Group>
        ))}
      </div>
      <div className="font-display text-base font-bold" style={{ color: C.text }}>Processor Information</div>
      <Group title="Processors" hint={`${processors.length} processor${processors.length === 1 ? "" : "s"}`}>
        {processors.length ? (
          <div className="grid gap-3 lg:grid-cols-2">
            {processors.map((cpu, i) => (
              <div key={i} className="min-w-0 rounded-lg border p-3" style={{ borderColor: C.borderLight, background: C.card }}>
                <div className="break-words text-sm font-semibold">{String(cpu.name || NA)}</div>
                <div className="font-mono text-[10px]" style={{ color: C.muted }}>{String(cpu.manufacturer || NA)}</div>
                <div className="mt-2 grid grid-cols-3 gap-2">
                  <Tile label="Cores" value={cpu.number_of_cores == null ? NA : String(cpu.number_of_cores)} />
                  <Tile label="Threads" value={cpu.number_of_logical_processors == null ? NA : String(cpu.number_of_logical_processors)} />
                  <Tile label="Max freq" value={isNum(cpuMaxFrequencyMhz(cpu)) ? formatFrequency(cpuMaxFrequencyMhz(cpu)! * 1_000_000) : NA} />
                </div>
              </div>
            ))}
          </div>
        ) : <EmptyState text="No saved CPU data." />}
      </Group>
      <div className="font-display text-base font-bold" style={{ color: C.text }}>Memory Hardware</div>
      <div className="grid gap-3 lg:grid-cols-3">
        <Group title="Memory Arrays" className="lg:col-span-1">
          {arrays.length ? (
            <div className="space-y-3">
              {arrays.map((arr, i) => (
                <div key={i} className="rounded-lg border p-2.5" style={{ borderColor: C.borderLight, background: C.card }}>
                  <KV
                    rows={[
                      ["Max capacity", fmtBytes(isNum(arr.max_capacity_bytes) ? arr.max_capacity_bytes : null)],
                      ["Slots", arr.memory_devices == null ? NA : String(arr.memory_devices)],
                      ["Location", String(arr.location || NA)],
                    ]}
                  />
                </div>
              ))}
            </div>
          ) : <EmptyState text="No saved data." />}
        </Group>
        <Group title="Physical RAM Modules" className="min-w-0 lg:col-span-2" hint={`${modules.length} module${modules.length === 1 ? "" : "s"}`}>
          {modules.length ? (
            <div className="overflow-x-auto"><table className="w-full min-w-[640px] text-left"><thead><tr style={{ background: "#f4f8fc" }}>{["Capacity", "Slot", "Speed", "Manufacturer", "Memory type", "Bank label"].map((label) => <th key={label} className="px-2 py-2 font-mono text-[10px] uppercase" style={{ color: C.muted }}>{label}</th>)}</tr></thead><tbody>{modules.map((m, i) => <tr key={i} className="border-t" style={{ borderColor: C.borderLight }}><td className="px-2 py-2 text-xs">{fmtBytes(isNum(m.capacity_bytes) ? m.capacity_bytes : null)}</td><td className="px-2 py-2 text-xs">{String(m.device_locator || NA)}</td><td className="px-2 py-2 text-xs">{m.speed_mhz == null ? NA : `${m.speed_mhz} MHz`}</td><td className="px-2 py-2 text-xs">{String(m.manufacturer || NA)}</td><td className="px-2 py-2 text-xs">{m.smbios_memory_type == null ? NA : String(m.smbios_memory_type)}</td><td className="px-2 py-2 text-xs">{String(m.bank_label || NA)}</td></tr>)}</tbody></table></div>
          ) : <EmptyState text="No saved data." />}
        </Group>
      </div>
    </div>
  )
}

function SensorsBody({ sensors }: { sensors: WindowsNativeSensor[] }) {
  const groups = ["Temperature Sensors", "GPU Temperature", "Storage Temperature", "Fan Sensors", "GPU Utilization", "Voltage Sensors", "Other Sensors"]
  const bad = sensors.filter((s) => s.status !== "ok")
  return (
    <div className="space-y-3">
      <div className="grid gap-3 md:grid-cols-3">
        {groups.map((group) => {
          const rows = sensors.filter((s) => s.status === "ok" && sensorGroup(s) === group)
          return (
            <Group key={group} title={group} hint={rows.length ? `${rows.length}` : undefined}>
              {rows.length ? (
                <div className="space-y-2">
                  {rows.map((s) => (
                    <div key={s.sensor_id || `${s.source}:${s.sensor_name}`} className="flex items-center justify-between gap-3 rounded-lg border p-2" style={{ borderColor: C.borderLight, background: C.card }}>
                      <div className="min-w-0">
                        <div className="truncate text-xs font-semibold">{s.sensor_name}</div>
                        <div className="font-mono text-[10px]" style={{ color: C.muted }}>{s.source}</div>
                      </div>
                      <div className="shrink-0 font-mono text-sm font-bold" style={{ color: C.accent }}>{sensorValue(s)}</div>
                    </div>
                  ))}
                </div>
              ) : <div className="font-mono text-xs" style={{ color: C.muted }}>No sensors reported</div>}
            </Group>
          )
        })}
      </div>
      {bad.length > 0 && (
        <Group title="Unsupported / Unavailable Sensors" hint={`${bad.length}`}>
          <div className="grid gap-2 md:grid-cols-3">
            {bad.map((s) => <Tile key={`${s.source}:${s.sensor_name}`} label={s.source} value={s.sensor_name} sub={sensorValue(s)} accent={C.warning} />)}
          </div>
        </Group>
      )}
    </div>
  )
}

/* ════════════════════════════════════════════════════════════════
   OS details (shown on Overview)
   ════════════════════════════════════════════════════════════════ */
function OsDetailsBody({ data }: { data: any }) {
  const sections: Array<[string, Array<[string, string]>]> = [
    ["OS Identity", [["Name", "caption"], ["Manufacturer", "manufacturer"], ["Version", "version"], ["Build", "build_number"], ["Architecture", "architecture"]]],
    ["Installation & Boot", [["Install date", "install_date"], ["Last boot", "last_boot_time"], ["Uptime", "uptime_seconds"]]],
    ["System Configuration", [["Windows directory", "windows_directory"], ["System directory", "system_directory"], ["System drive", "system_drive"], ["Boot device", "boot_device"]]],
    ["Regional Settings", [["Locale", "locale"], ["Timezone offset", "time_zone"], ["Service pack", "service_pack"]]],
  ]
  const display = (key: string, value: unknown) => {
    if (key === "install_date" || key === "last_boot_time") return fmtOsDate(value)
    if (key === "uptime_seconds") return fmtUptime(value)
    if (key === "locale") return fmtLocale(value)
    if (key === "time_zone") return fmtTimezone(value)
    if (key === "service_pack") return fmtServicePack(value)
    return value == null || value === "" ? "Not available" : String(value)
  }
  return (
    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
      {sections.map(([title, fields]) => (
        <Group key={title} title={title}>
          <KV rows={fields.map(([label, key]) => [label, display(key, data?.[key])] as [string, ReactNode])} />
        </Group>
      ))}
    </div>
  )
}

/* ════════════════════════════════════════════════════════════════
   Page
   ════════════════════════════════════════════════════════════════ */
export default function WindowsDevices() {
  const navigate = useNavigate()
  const { deviceId: routeDeviceId, section: routeSection } = useParams<{ deviceId?: string; section?: string }>()
  const activeDeviceTab: TabName = tabNames.includes(routeSection as TabName) ? (routeSection as TabName) : "overview"
  const { hasPermission } = useAuth()

  const [devices, setDevices] = useState<DeviceRecord[]>([])
  const [allDevices, setAllDevices] = useState<DeviceRecord[]>([])
  const [sites, setSites] = useState<SiteRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [sitesLoading, setSitesLoading] = useState(false)
  const [error, setError] = useState("")
  const [onboardingNotice, setOnboardingNotice] = useState("")
  const [duplicate, setDuplicate] = useState<DeviceRecord | null>(null)

  // add-device wizard
  const [showAdd, setShowAdd] = useState(false)
  const [step, setStep] = useState<Step>(1)
  const [saving, setSaving] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const [progress, setProgress] = useState<Progress>("idle")
  const [form, setForm] = useState(emptyForm)
  const [createdDevice, setCreatedDevice] = useState<DeviceRecord | null>(null)
  const [credentialSaved, setCredentialSaved] = useState(false)
  const [selectedDeviceId, setSelectedDeviceId] = useState("")
  const [existingCredential, setExistingCredential] = useState<WindowsCredentialRecord | null>(null)
  const [credentialLoading, setCredentialLoading] = useState(false)

  // list filters
  const [deviceQuery, setDeviceQuery] = useState("")
  const [statusFilter, setStatusFilter] = useState<"all" | "online" | "offline">("all")

  // device details
  const [expandedDeviceId, setExpandedDeviceId] = useState<number | null>(null)
  const [thresholds, setThresholds] = useState<WindowsThresholds>(DEFAULT_WINDOWS_THRESHOLDS)
  const [thresholdDraft, setThresholdDraft] = useState<WindowsThresholds>(DEFAULT_WINDOWS_THRESHOLDS)
  const [thresholdDialogOpen, setThresholdDialogOpen] = useState(false)
  const [thresholdLoading, setThresholdLoading] = useState(false)
  const [thresholdSaving, setThresholdSaving] = useState(false)
  const [thresholdError, setThresholdError] = useState("")
  const [thresholdNotice, setThresholdNotice] = useState("")
  const thresholdsRequest = useRef(0)
  const detailsRequest = useRef(0)
  const [metrics, setMetrics] = useState<Partial<Record<Module, WindowsMetricSnapshot>>>({})
  const [metricState, setMetricState] = useState<Partial<Record<Module, "loading" | "success" | "error">>>({})
  const [metricErrors, setMetricErrors] = useState<Partial<Record<Module, string>>>({})
  const metricInFlight = useRef(new Set<string>())
  const [snapshotLoading, setSnapshotLoading] = useState(false)
  const [snapshotError, setSnapshotError] = useState("")

  const [hardware, setHardware] = useState<WindowsHardwareSnapshot | null>(null)
  const [hardwareLoading, setHardwareLoading] = useState(false)
  const [hardwareFetching, setHardwareFetching] = useState(false)
  const [hardwareError, setHardwareError] = useState("")
  const [nativeSensors, setNativeSensors] = useState<WindowsNativeSensor[]>([])
  const [sensorProviders, setSensorProviders] = useState<Array<{ provider: string; status: string; error?: string | null }>>([])
  const [sensorLoading, setSensorLoading] = useState(false)
  const [sensorError, setSensorError] = useState("")

  const [diskInventory, setDiskInventory] = useState<WindowsDiskInventory | null>(null)
  const [diskInventoryLoading, setDiskInventoryLoading] = useState(false)
  const [diskInventoryError, setDiskInventoryError] = useState("")
  const [diskInventoryOpen, setDiskInventoryOpen] = useState(false)
  const [diskHealth, setDiskHealth] = useState<WindowsDiskHealthResponse | null>(null)
  const [diskHealthLoading, setDiskHealthLoading] = useState(false)
  const [diskHealthError, setDiskHealthError] = useState("")
  const [diskHealthOpen, setDiskHealthOpen] = useState(false)
  const diskInventoryCache = useRef(new Map<number, WindowsDiskInventory>())
  const diskHealthCache = useRef(new Map<number, WindowsDiskHealthResponse>())
  const diskInventoryInFlight = useRef(new Map<number, Promise<WindowsDiskInventory>>())
  const diskHealthInFlight = useRef(new Map<number, Promise<WindowsDiskHealthResponse>>())
  const [usbInventory, setUsbInventory] = useState<WindowsUSBInventory | null>(null)
  const [usbLoading, setUsbLoading] = useState(false)
  const [usbError, setUsbError] = useState("")
  const usbCache = useRef(new Map<number, WindowsUSBInventory>())
  const usbInFlight = useRef(new Map<number, Promise<WindowsUSBInventory>>())

  useEffect(() => {
    if (expandedDeviceId == null) return
    const requestId = ++thresholdsRequest.current
    setThresholds(DEFAULT_WINDOWS_THRESHOLDS)
    setThresholdDraft(DEFAULT_WINDOWS_THRESHOLDS)
    setThresholdDialogOpen(false)
    setThresholdLoading(true)
    setThresholdError("")
    setThresholdNotice("")
    void getWindowsThresholds(expandedDeviceId).then((value) => {
      if (requestId !== thresholdsRequest.current) return
      const loaded = {
        cpu: safeThreshold(value.cpu_threshold),
        memory: safeThreshold(value.memory_threshold),
        disk: safeThreshold(value.disk_threshold),
      }
      setThresholds(loaded)
      setThresholdDraft(loaded)
    }).catch((cause) => {
      if (requestId !== thresholdsRequest.current) return
      setThresholdError(cause instanceof Error ? cause.message : "Unable to load threshold settings")
    }).finally(() => {
      if (requestId === thresholdsRequest.current) setThresholdLoading(false)
    })
  }, [expandedDeviceId])

  const saveThresholds = async () => {
    if (expandedDeviceId == null || thresholdSaving || thresholdLoading || !hasPermission("devices:update")) return
    const deviceId = expandedDeviceId
    const next = { cpu: safeThreshold(thresholdDraft.cpu), memory: safeThreshold(thresholdDraft.memory), disk: safeThreshold(thresholdDraft.disk) }
    setThresholdSaving(true)
    setThresholdError("")
    setThresholdNotice("")
    try {
      const saved = await updateWindowsThresholds(deviceId, { cpu_threshold: next.cpu, memory_threshold: next.memory, disk_threshold: next.disk })
      if (deviceId !== expandedDeviceId) return
      const confirmed = { cpu: safeThreshold(saved.cpu_threshold), memory: safeThreshold(saved.memory_threshold), disk: safeThreshold(saved.disk_threshold) }
      setThresholds(confirmed)
      setThresholdDraft(confirmed)
      setThresholdNotice("Threshold settings saved")
    } catch (cause) {
      if (deviceId === expandedDeviceId) setThresholdError(cause instanceof Error ? cause.message : "Unable to save threshold settings")
    } finally {
      setThresholdSaving(false)
    }
  }

  const [systemEvents, setSystemEvents] = useState<WindowsSystemEvent[]>([])
  const [systemEventsLoading, setSystemEventsLoading] = useState(false)
  const [systemEventsError, setSystemEventsError] = useState("")
  const [systemEventsOffset, setSystemEventsOffset] = useState(0)
  const [systemEventsHasNext, setSystemEventsHasNext] = useState(false)
  const [systemEventsFetch, setSystemEventsFetch] = useState<{ fetched_count: number; inserted_count: number; collected_at: string } | null>(null)
  const [systemEventIdFilter, setSystemEventIdFilter] = useState("")
  const [systemEventLevelFilter, setSystemEventLevelFilter] = useState("")
  const [systemEventStartFilter, setSystemEventStartFilter] = useState("")
  const [systemEventEndFilter, setSystemEventEndFilter] = useState("")
  const [expandedEventId, setExpandedEventId] = useState<number | null>(null)
  const systemEventsInFlight = useRef<string | null>(null)
  const systemEventsLimit = 50

  /* ───────────── data loaders ───────────── */
  const loadSystemEvents = async (deviceId: number, offset = 0) => {
    const requestId = detailsRequest.current
    setSystemEventsLoading(true)
    setSystemEventsError("")
    try {
      const eventId = systemEventIdFilter.trim() ? Number(systemEventIdFilter) : undefined
      const result = await getWindowsSystemEvents(deviceId, offset, systemEventsLimit, {
        eventId: eventId !== undefined && Number.isInteger(eventId) && eventId >= 0 ? eventId : undefined,
        level: systemEventLevelFilter || undefined,
        startTime: systemEventStartFilter ? new Date(`${systemEventStartFilter}T00:00:00`).toISOString() : undefined,
        endTime: systemEventEndFilter ? new Date(`${systemEventEndFilter}T23:59:59.999`).toISOString() : undefined,
      })
      if (requestId !== detailsRequest.current) return
      setSystemEvents(result.items)
      setSystemEventsOffset(result.offset)
      setSystemEventsHasNext(result.items.length === result.limit)
    } catch (e) {
      if (requestId !== detailsRequest.current) return
      setSystemEventsError(e instanceof Error ? e.message : "Unable to load saved System events")
    } finally {
      if (requestId === detailsRequest.current) setSystemEventsLoading(false)
    }
  }

  const fetchSystemEvents = async () => {
    if (!expandedDeviceId || systemEventsInFlight.current) return
    const requestId = detailsRequest.current
    const deviceId = expandedDeviceId
    const requestKey = `${requestId}:${deviceId}`
    systemEventsInFlight.current = requestKey
    setSystemEventsLoading(true)
    setSystemEventsError("")
    try {
      const result = await fetchWindowsSystemEvents(deviceId, 50)
      if (requestId !== detailsRequest.current) return
      setSystemEventsFetch(result)
      await loadSystemEvents(deviceId, 0)
    } catch (e) {
      if (requestId !== detailsRequest.current) return
      setSystemEventsError(e instanceof Error ? e.message : "Unable to fetch System events")
    } finally {
      if (systemEventsInFlight.current === requestKey) systemEventsInFlight.current = null
      if (requestId === detailsRequest.current) setSystemEventsLoading(false)
    }
  }

  const clearEventFilters = () => {
    setSystemEventIdFilter("")
    setSystemEventLevelFilter("")
    setSystemEventStartFilter("")
    setSystemEventEndFilter("")
    setSystemEventsOffset(0)
  }

  const openDetails = async (device: DeviceRecord) => {
    const requestId = ++detailsRequest.current
    systemEventsInFlight.current = null
    setExpandedDeviceId(device.id)
    setMetrics({})
    setMetricState({})
    setMetricErrors({})
    setSnapshotLoading(true)
    setSnapshotError("")
    setHardware(null)
    setHardwareFetching(false)
    setHardwareLoading(true)
    setHardwareError("")
    setDiskInventory(null)
    setDiskInventoryOpen(false)
    setDiskInventoryLoading(false)
    setDiskInventoryError("")
    setDiskHealth(null)
    setDiskHealthOpen(false)
    setDiskHealthLoading(false)
    setDiskHealthError("")
    setUsbInventory(null)
    setUsbLoading(false)
    setUsbError("")
    setNativeSensors([])
    setSensorProviders([])
    setSensorLoading(false)
    setSensorError("")
    setSystemEvents([])
    setSystemEventsLoading(false)
    setSystemEventsError("")
    setSystemEventsOffset(0)
    setSystemEventsHasNext(false)
    setSystemEventsFetch(null)
    setExpandedEventId(null)
    try {
      const loaded = await Promise.all(
        (["system", "cpu", "memory", "disk", "network"] as const).map((module) => getWindowsMetric(device.id, module)),
      )
      if (requestId !== detailsRequest.current) return
      setMetrics(Object.fromEntries(loaded.map((item) => [item.module, item])) as Partial<Record<Module, WindowsMetricSnapshot>>)
      void loadSystemEvents(device.id, 0)
      void getWindowsHardware(device.id)
        .then((value) => { if (requestId === detailsRequest.current) setHardware(value) })
        .catch((e) => { if (requestId === detailsRequest.current) setHardwareError(e instanceof Error ? e.message : "Unable to load saved hardware information") })
        .finally(() => { if (requestId === detailsRequest.current) setHardwareLoading(false) })
    } catch (e) {
      if (requestId !== detailsRequest.current) return
      setSnapshotError(e instanceof Error ? e.message : "Unable to load stored Windows metrics")
      setHardwareLoading(false)
    } finally {
      if (requestId === detailsRequest.current) setSnapshotLoading(false)
    }
  }

  const loadDiskInventory = async (force = false) => {
    if (!expandedDeviceId) return
    const deviceId = expandedDeviceId
    const requestId = detailsRequest.current
    if (!force) {
      const cached = diskInventoryCache.current.get(deviceId)
      if (cached) { setDiskInventory(cached); return }
    }
    const existing = diskInventoryInFlight.current.get(deviceId)
    if (existing) return existing
    setDiskInventoryLoading(true)
    setDiskInventoryError("")
    const request = getWindowsDiskInventory(deviceId)
      .then((value) => {
        diskInventoryCache.current.set(deviceId, value)
        if (requestId === detailsRequest.current) setDiskInventory(value)
        return value
      })
      .catch((err) => {
        if (requestId === detailsRequest.current) setDiskInventoryError(err instanceof Error ? err.message : "Unable to load disk inventory")
        throw err
      })
      .finally(() => {
        diskInventoryInFlight.current.delete(deviceId)
        if (requestId === detailsRequest.current) setDiskInventoryLoading(false)
      })
    diskInventoryInFlight.current.set(deviceId, request)
    return request
  }

  const loadDiskHealth = async (force = false) => {
    if (!expandedDeviceId) return
    const deviceId = expandedDeviceId
    const requestId = detailsRequest.current
    if (!force) {
      const cached = diskHealthCache.current.get(deviceId)
      if (cached) { setDiskHealth(cached); return }
    }
    const existing = diskHealthInFlight.current.get(deviceId)
    if (existing) return existing
    setDiskHealthLoading(true)
    setDiskHealthError("")
    const request = getWindowsDiskHealth(deviceId)
      .then((value) => {
        diskHealthCache.current.set(deviceId, value)
        if (requestId === detailsRequest.current) setDiskHealth(value)
        return value
      })
      .catch((err) => {
        if (requestId === detailsRequest.current) setDiskHealthError(err instanceof Error ? err.message : "Unable to load disk health")
        throw err
      })
      .finally(() => {
        diskHealthInFlight.current.delete(deviceId)
        if (requestId === detailsRequest.current) setDiskHealthLoading(false)
      })
    diskHealthInFlight.current.set(deviceId, request)
    return request
  }

  const fetchHardware = async () => {
    if (!expandedDeviceId || hardwareFetching) return
    const requestId = detailsRequest.current
    setHardwareFetching(true)
    setHardwareError("")
    try {
      const value = await fetchWindowsHardware(expandedDeviceId)
      if (requestId === detailsRequest.current) setHardware(value)
    } catch (e) {
      if (requestId === detailsRequest.current) setHardwareError(e instanceof Error ? e.message : "Unable to fetch hardware information")
    } finally {
      if (requestId === detailsRequest.current) setHardwareFetching(false)
    }
  }

  const loadUsbInventory = async (force = false) => {
    if (!expandedDeviceId) return
    const deviceId = expandedDeviceId
    const requestId = detailsRequest.current
    if (!force) {
      const cached = usbCache.current.get(deviceId)
      if (cached) { setUsbInventory(cached); return cached }
    }
    const existing = usbInFlight.current.get(deviceId)
    if (existing) return existing
    setUsbLoading(true)
    setUsbError("")
    const request = getWindowsUSBInventory(deviceId)
      .then((value) => {
        if (value.device_id !== deviceId) throw new Error("USB inventory response did not match the selected device")
        usbCache.current.set(deviceId, value)
        if (requestId === detailsRequest.current) setUsbInventory(value)
        return value
      })
      .catch((error) => { if (requestId === detailsRequest.current) setUsbError(error instanceof Error ? error.message : "Unable to load USB inventory"); throw error })
      .finally(() => { usbInFlight.current.delete(deviceId); if (requestId === detailsRequest.current) setUsbLoading(false) })
    usbInFlight.current.set(deviceId, request)
    return request
  }

  const discoverSensors = async () => {
    if (!expandedDeviceId || sensorLoading) return
    const requestId = detailsRequest.current
    const deviceId = expandedDeviceId
    setSensorLoading(true)
    setSensorError("")
    try {
      const result = await discoverWindowsHardwareSensors(deviceId)
      if (requestId === detailsRequest.current && result.device_id === deviceId) {
        setNativeSensors(result.sensors)
        setSensorProviders((result.providers ?? []).map(({ provider, status, error: err }) => ({ provider, status, error: err })))
      }
    } catch (e) {
      if (requestId === detailsRequest.current) setSensorError(e instanceof Error ? e.message : "Unable to discover native sensors")
    } finally {
      setSensorLoading(false)
    }
  }

  const fetchMetric = async (module: Module) => {
    if (!expandedDeviceId) return
    const requestId = detailsRequest.current
    const deviceId = expandedDeviceId
    const requestKey = `${deviceId}:${module}`
    if (metricInFlight.current.has(requestKey)) return
    metricInFlight.current.add(requestKey)
    setMetricState((c) => ({ ...c, [module]: "loading" }))
    setMetricErrors((c) => ({ ...c, [module]: undefined }))
    try {
      const result = await fetchWindowsMetric(deviceId, module)
      if (requestId !== detailsRequest.current) return
      setMetrics((c) => ({ ...c, [module]: result }))
      setMetricState((c) => ({ ...c, [module]: "success" }))
    } catch (e) {
      if (requestId !== detailsRequest.current) return
      setMetricState((c) => ({ ...c, [module]: "error" }))
      setMetricErrors((c) => ({ ...c, [module]: e instanceof Error ? e.message : `Unable to fetch ${module}` }))
    } finally {
      metricInFlight.current.delete(requestKey)
    }
  }

  const loadDevices = () => {
    setLoading(true)
    return listDevices()
      .then(async (items) => {
        const enrolledIds = new Set(await listEnrolledWindowsDeviceIds())
        const windowsItems = items.filter((item) => isWindowsDevice(item) || enrolledIds.has(item.id))
        setAllDevices(items)
        setDevices(windowsItems)
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Unable to load Windows devices"))
      .finally(() => setLoading(false))
  }

  /* ───────────── effects ───────────── */
  useEffect(() => {
    void loadDevices()
    setSitesLoading(true)
    void listSites()
      .then(setSites)
      .catch((e) => setError(e instanceof Error ? e.message : "Unable to load authorized sites"))
      .finally(() => setSitesLoading(false))
  }, [])

  // keep the opened device in sync with the URL
  useEffect(() => {
    if (!routeDeviceId) {
      if (expandedDeviceId !== null) setExpandedDeviceId(null)
      return
    }
    if (!devices.length) return
    const device = devices.find((item) => String(item.id) === routeDeviceId)
    if (device && expandedDeviceId !== device.id) void openDetails(device)
  }, [routeDeviceId, devices, expandedDeviceId])

  // Storage tab: keep both queries manual so opening the tab does not trigger WinRM calls.
  useEffect(() => {
    if (activeDeviceTab !== "storage" || !expandedDeviceId) return
    setDiskInventoryOpen(true)
    setDiskHealthOpen(true)
  }, [activeDeviceTab, expandedDeviceId])

  useEffect(() => {
    if (activeDeviceTab === "usb" && expandedDeviceId) void loadUsbInventory().catch(() => undefined)
  }, [activeDeviceTab, expandedDeviceId])

  useEffect(() => {
    if (!selectedDeviceId) {
      setExistingCredential(null)
      return
    }
    const device = allDevices.find((item) => String(item.id) === selectedDeviceId)
    if (!device) return
    setCredentialLoading(true)
    void listWindowsCredentials(device.id)
      .then((rows) => {
        const current = rows[0] ?? null
        setExistingCredential(current)
        if (current)
          setForm((v) => ({ ...v, username: current.username, domain: current.domain ?? "", connection_host: current.connection_host ?? "" }))
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Unable to load Windows credential status"))
      .finally(() => setCredentialLoading(false))
  }, [selectedDeviceId, allDevices])

  /* ───────────── derived ───────────── */
  const online = useMemo(() => devices.filter((d) => isOnlineStatus(d.status)).length, [devices])
  const filteredDevices = useMemo(
    () =>
      devices.filter((device) => {
        const query = deviceQuery.trim().toLowerCase()
        const matchesQuery = !query || `${device.hostname} ${device.ip_address} ${device.id}`.toLowerCase().includes(query)
        const isOnline = isOnlineStatus(device.status)
        return matchesQuery && (statusFilter === "all" || (statusFilter === "online" ? isOnline : !isOnline))
      }),
    [devices, deviceQuery, statusFilter],
  )
  const siteName = (siteId?: number | null) => (siteId == null ? "—" : sites.find((s) => s.id === siteId)?.name ?? String(siteId))
  const inDetail = Boolean(routeDeviceId)
  const detailDevice = routeDeviceId ? devices.find((d) => String(d.id) === routeDeviceId) : undefined
  const selectDeviceTab = (tab: TabName) => {
    if (routeDeviceId) navigate(`/windows-devices/${routeDeviceId}/${tab}`)
  }

  /* ───────────── actions ───────────── */
  const removeDevice = async (device: DeviceRecord) => {
    if (!window.confirm(`Delete Windows device ${device.hostname} (ID ${device.id})? This removes the device and related inventory data.`)) return
    setError("")
    try {
      await deleteDevice(device.id)
      setExpandedDeviceId(null)
      if (routeDeviceId) navigate("/windows-devices")
      await loadDevices()
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to delete device")
    }
  }

  const findDuplicate = () =>
    allDevices.find((d) => norm(d.ip_address) === norm(form.ip_address) || norm(d.hostname) === norm(form.hostname))

  const deviceStep = () => {
    if (!form.hostname.trim() || !form.ip_address.trim()) return setError("Select an existing device or provide hostname and IP address.")
    if (!selectedDeviceId) {
      const d = findDuplicate()
      if (d) {
        setDuplicate(d)
        return setError(`A device already exists with the same ${norm(d.ip_address) === norm(form.ip_address) ? "IP address" : "hostname"}. Select it from the device list.`)
      }
    }
    setError("")
    setDuplicate(null)
    setStep(2)
  }
  const credentialStep = () => {
    if (!form.username.trim() || !form.domain.trim() || (!existingCredential && !form.password))
      return setError(
        existingCredential
          ? "Username and computer name are required. Enter a new password only if it should be changed."
          : "Username, computer name, and password are required.",
      )
    setError("")
    setStep(3)
  }
  const reset = () => {
    setForm(emptyForm)
    setSelectedDeviceId("")
    setExistingCredential(null)
    setCredentialLoading(false)
    setStep(1)
    setProgress("idle")
    setCreatedDevice(null)
    setCredentialSaved(false)
    setShowPassword(false)
    setDuplicate(null)
    setError("")
    setOnboardingNotice("")
    setShowAdd(false)
  }
  const onboard = async () => {
    if (saving) return
    setSaving(true)
    setError("")
    setOnboardingNotice("")
    setDuplicate(null)
    let device: DeviceRecord | null = createdDevice
    try {
      if (!device) {
        const d = findDuplicate()
        if (selectedDeviceId && d?.id === Number(selectedDeviceId)) {
          device = d
          setCreatedDevice(d)
        } else if (d) {
          setDuplicate(d)
          setProgress("failed")
          setError("This device already exists. Select it from the device list.")
          return
        } else {
          setProgress("device")
          device = await createDevice({
            hostname: form.hostname.trim(),
            ip_address: form.ip_address.trim(),
            ...(form.site_id ? { site_id: Number(form.site_id) } : {}),
            topology_metadata: { platform: "windows", onboarding_source: "windows_devices" },
          })
          setCreatedDevice(device)
        }
      }
      if (!credentialSaved) {
        setProgress("credential")
        const saved = existingCredential
          ? await updateWindowsCredential(device.id, existingCredential.id, {
              username: form.username.trim(),
              domain: form.domain.trim(),
              connection_host: form.connection_host.trim() || undefined,
              ...(form.password ? { secret: form.password } : {}),
            })
          : await createWindowsCredential(device.id, {
              device_id: device.id,
              username: form.username.trim(),
              domain: form.domain.trim(),
              connection_host: form.connection_host.trim() || undefined,
              secret: form.password,
              enabled: true,
            })
        setExistingCredential(saved)
        setCredentialSaved(true)
        setForm((v) => ({ ...v, password: "" }))
      }
      setProgress("testing")
      const result = await testWindowsConnection(device.id)
      if (!result.ok) {
        setProgress("connected")
        await loadDevices()
        setOnboardingNotice("Device and credentials saved. WinRM validation is pending; you can retry the connection test from the device details.")
        return
      }
      setProgress("connected")
      await loadDevices()
    } catch (e) {
      setProgress("failed")
      const message = e instanceof Error ? e.message : "Unable to complete Windows onboarding"
      if (device) await loadDevices()
      if (device && /already|409|processing/i.test(message)) {
        try {
          const rows = await listWindowsCredentials(device.id)
          const current = rows[0] ?? null
          setExistingCredential(current)
          setCredentialSaved(false)
          setError(current ? "An existing credential was found. Review the fields and retry to update it." : windowsOnboardingMessage(message))
        } catch {
          setError(windowsOnboardingMessage(message))
        }
      } else setError(windowsOnboardingMessage(message))
    } finally {
      setSaving(false)
    }
  }
  const progressLabel = ({
    device: "Creating Device…",
    credential: "Saving Credentials…",
    testing: "Testing Connection…",
    connected: "Connected",
    failed: "Failed",
    idle: "",
  } as Record<Progress, string>)[progress]

  /* ───────────── tab panels ───────────── */
  const metricCard = (module: Module, title: string, subtitle: string, fetchLabel: string, body: ReactNode) => (
    <CardShell
      title={title}
      subtitle={subtitle}
      collectedAt={metrics[module]?.collected_at ?? null}
      success={metricState[module] === "success"}
      error={metricErrors[module]}
      action={<ActionButton label={fetchLabel} busyLabel="FETCHING…" busy={metricState[module] === "loading"} onClick={() => void fetchMetric(module)} />}
    >
      {body}
    </CardShell>
  )

  const eventSummary = useMemo(() => {
    const count = (re: RegExp) => systemEvents.filter((e) => re.test(e.level ?? "")).length
    return { critical: count(/critical/i), error: count(/error/i), warning: count(/warn/i), info: count(/info/i) }
  }, [systemEvents])
  const levelColor = (level?: string | null) =>
    /critical|error/i.test(level ?? "") ? C.danger : /warn/i.test(level ?? "") ? C.warning : /info/i.test(level ?? "") ? C.accent : C.muted

  const renderTab = (d: DeviceRecord) => {
    if (metricTabs.includes(activeDeviceTab)) {
      if (snapshotLoading) return <GlassCard className="p-6"><LoadingBlock text="Loading stored metrics…" /></GlassCard>
      if (snapshotError)
        return <div role="alert" className="rounded-lg border p-3 font-mono text-xs" style={{ color: C.danger, borderColor: C.danger }}>⚠ {snapshotError}</div>
    }
    switch (activeDeviceTab) {
      case "overview":
        return (
          <div className="space-y-4">
            <div id="windows-overview-section">
              <WindowsDeviceOverview device={d} metrics={metrics} hardware={hardware} loading={snapshotLoading || hardwareLoading} />
            </div>
            <WindowsCATrustPanel deviceId={d.id} deviceName={d.hostname} siteId={d.site_id} />
            <WindowsTCPDiagnostics deviceId={d.id} siteId={d.site_id} deviceName={d.hostname} />
            <WindowsTLSDiagnostics deviceId={d.id} siteId={d.site_id} deviceName={d.hostname} />
            {metricCard("system", "Operating System Details", "Identity, boot, configuration and regional settings", "FETCH SYSTEM INFO",
              metrics.system?.data ? <OsDetailsBody data={metrics.system.data} /> : <EmptyState />)}
          </div>
        )
      case "cpu":
        return metricCard("cpu", "CPU", "Processor utilization and counters", "FETCH CPU",
          metrics.cpu?.data ? <CpuDashboardBody data={metrics.cpu.data} systemData={metrics.system?.data} threshold={thresholds.cpu} /> : <EmptyState />)
      case "memory":
        return metricCard("memory", "Memory", "Capacity, commit, paging and kernel pools", "FETCH MEMORY",
          metrics.memory?.data ? <MemoryBody data={metrics.memory.data} cpuData={metrics.cpu?.data} threshold={thresholds.memory} /> : <EmptyState />)
      case "disk":
        return metricCard("disk", "Disk", "Volume capacity and I/O performance", "FETCH DISK",
          metrics.disk?.data ? <DiskBody data={metrics.disk.data} threshold={thresholds.disk} /> : <EmptyState />)
      case "network":
        return metricCard("network", "Network Interfaces", "Adapters, link speed and traffic", "FETCH NETWORK",
          metrics.network?.data ? <NetworkBody data={metrics.network.data} /> : <EmptyState />)
      case "usb":
        return (
          <CardShell title="USB Devices" subtitle="Read-only Windows USB controllers, hubs and PnP inventory" collectedAt={usbInventory?.collected_at ?? null} error={usbError}
            action={<ActionButton label="REFRESH USB" busyLabel="REFRESHING…" busy={usbLoading} onClick={() => void loadUsbInventory(true).catch(() => undefined)} />}>
            {usbLoading && !usbInventory ? <LoadingBlock text="Loading USB inventory…" /> : usbInventory ? <USBBody inventory={usbInventory} /> : <EmptyState text="No USB inventory loaded yet." />}
          </CardShell>
        )
      case "hardware":
        return (
          <div className="space-y-4">
            <CardShell
              title="Hardware Information"
              subtitle="Saved Windows hardware identity and inventory"
              collectedAt={hardware?.collected_at ?? null}
              error={hardwareError}
              action={<ActionButton label="FETCH HARDWARE" busyLabel="FETCHING…" busy={hardwareFetching} disabled={hardwareLoading} onClick={() => void fetchHardware()} />}
            >
              {hardwareLoading ? <LoadingBlock text="Loading saved hardware…" /> : hardware ? <HardwareBody hardware={hardware} /> : <EmptyState text="No saved hardware data. Use FETCH HARDWARE to collect it." />}
            </CardShell>
            <CardShell
              title="Hardware Sensors"
              subtitle="Read-only native WMI/CIM and provider discovery"
              collectedAt={nativeSensors[0]?.collected_at ?? null}
              error={sensorError}
              action={<ActionButton label="DISCOVER NATIVE SENSORS" busyLabel="DISCOVERING…" busy={sensorLoading} onClick={() => void discoverSensors()} />}
            >
              {sensorProviders.length > 0 && (
                <div className="mb-3 flex flex-wrap gap-2">
                  {sensorProviders.map((p) => <Badge key={p.provider} text={`${p.provider}: ${p.status}`} color={p.status === "ok" ? C.success : C.muted} />)}
                </div>
              )}
              {sensorLoading ? <LoadingBlock text="Discovering native sensors…" /> : nativeSensors.length ? <SensorsBody sensors={nativeSensors} /> : <EmptyState text="No sensor readings yet. Use DISCOVER NATIVE SENSORS." />}
            </CardShell>
          </div>
        )
      case "storage":
        return (
          <div id="windows-storage-section" className="grid grid-cols-1 items-start gap-4">
            <WindowsDiskInventoryPanel
              inventory={diskInventory ?? { device_id: expandedDeviceId ?? 0, physical_disks: [], partitions: [], modern_physical_disks: [], modern_status: "unavailable", modern_error: null }}
              loading={diskInventoryLoading}
              error={diskInventoryError}
              open={diskInventoryOpen}
              onToggle={() => setDiskInventoryOpen((open) => !open)}
              onFetch={() => void loadDiskInventory(true).catch(() => undefined)}
              onRetry={() => void loadDiskInventory(true).catch(() => undefined)}
            />
          </div>
        )
      case "events":
        const eventCounts = { critical: eventSummary.critical, error: eventSummary.error, warning: eventSummary.warning, info: eventSummary.info }
        const eventTotal = systemEvents.length
        const eventDays = Array.from(systemEvents.reduce((map, item) => {
          const day = item.time_created ? new Date(item.time_created).toISOString().slice(0, 10) : ""
          if (day) map.set(day, (map.get(day) ?? 0) + 1)
          return map
        }, new Map<string, number>())).sort(([a], [b]) => a.localeCompare(b))
        const maxEventDay = Math.max(1, ...eventDays.map(([, count]) => count))
        return (
          <CardShell title="Windows System Event Logs" subtitle={systemEvents.length ? `${systemEvents.length} saved records loaded` : "No saved events"} error={systemEventsError} action={<ActionButton label="FETCH SYSTEM EVENTS" busyLabel="FETCHING…" busy={systemEventsLoading} onClick={() => void fetchSystemEvents()} />}>
            <div className="space-y-3">
              {systemEventsFetch && (
                <div className="flex flex-wrap items-center gap-2 border-b pb-2 font-mono text-[10px]" style={{ color: C.muted, borderColor: C.borderLight }}>
                  <Badge text="Fetch complete" color={C.success} />
                  <span>fetched <b style={{ color: C.text }}>{systemEventsFetch.fetched_count}</b></span>
                  <span>· inserted <b style={{ color: C.text }}>{systemEventsFetch.inserted_count}</b></span>
                  <span>· {fmtDateTime(systemEventsFetch.collected_at)}</span>
                </div>
              )}
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-4">
                {[['Critical / Error', eventCounts.critical + eventCounts.error, C.danger, '✦'], ['Warning', eventCounts.warning, C.warning, '⚠'], ['Information', eventCounts.info, C.accent, 'ⓘ'], ['Total Events', eventTotal, C.accent, '▤']].map(([label, value, color, icon]) => <div key={String(label)} className="event-summary-card flex min-h-[104px] flex-col rounded-lg border p-3" style={{ borderColor: C.borderLight, background: C.card, boxShadow: "var(--wd-event-shadow)" }}><div className="flex items-center justify-between"><span className="font-mono text-[10px] font-semibold uppercase" style={{ color: C.muted }}>{label}</span><span aria-hidden className="event-summary-icon text-base" style={{ color: color as string, background: "var(--wd-event-icon-bg)" }}>{icon}</span></div><div className="mt-auto pt-2 font-display text-3xl font-bold leading-none" style={{ color: C.text }}>{value}</div>{label === 'Critical / Error' && <div className="mt-1 font-mono text-[10px]" style={{ color: C.muted }}>Critical {eventCounts.critical} · Error {eventCounts.error}</div>}</div>)}
              </div>

              <section className="event-panel rounded-lg border p-3" style={{ borderColor: C.borderLight, background: C.card, boxShadow: "var(--wd-event-shadow)" }}><div className="flex items-center justify-between gap-2"><div><h3 className="font-display text-sm font-bold" style={{ color: C.text }}>Event Activity</h3><p className="font-mono text-[10px]" style={{ color: C.muted }}>{eventDays.length ? `Loaded records · ${eventDays[0][0]} to ${eventDays[eventDays.length - 1][0]}` : "Historical data unavailable"}</p></div></div>{eventDays.length >= 3 ? <svg viewBox="0 0 640 170" className="mt-2 h-36 w-full" role="img" aria-label="Event counts by loaded date"><g stroke="var(--t-border-light)" strokeWidth="1" strokeDasharray="3 4"><line x1="42" y1="15" x2="42" y2="140" /><line x1="42" y1="15" x2="620" y2="15" /><line x1="42" y1="77" x2="620" y2="77" /><line x1="42" y1="140" x2="620" y2="140" /></g><polyline fill="none" stroke="var(--t-accent)" strokeWidth="3" points={eventDays.map(([, count], index) => `${(index / (eventDays.length - 1)) * 578 + 42},${140 - (count / maxEventDay) * 110}`).join(" ")} />{eventDays.map(([day, count], index) => <circle key={day} cx={(index / (eventDays.length - 1)) * 578 + 42} cy={140 - (count / maxEventDay) * 110} r="3.5" fill="var(--t-accent)"><title>{day}: {count} event{count === 1 ? "" : "s"}</title></circle>)}<text x="30" y="143" textAnchor="end" fill="var(--t-muted)" fontSize="9">0</text><text x="30" y="18" textAnchor="end" fill="var(--t-muted)" fontSize="9">{maxEventDay}</text><text x="42" y="160" fill="var(--t-muted)" fontSize="9">{eventDays[0][0]}</text><text x="620" y="160" textAnchor="end" fill="var(--t-muted)" fontSize="9">{eventDays[eventDays.length - 1][0]}</text></svg> : eventDays.length > 0 ? <div className="mt-3 flex h-28 items-end gap-3 border-b border-l px-3 pb-0" style={{ borderColor: C.borderLight }}>{eventDays.map(([day, count]) => <div key={day} className="flex min-w-0 flex-1 flex-col items-center justify-end gap-1" title={`${day}: ${count} event${count === 1 ? "" : "s"}`}><span className="font-mono text-[10px]" style={{ color: C.muted }}>{count}</span><div className="w-full max-w-12 rounded-t" style={{ height: `${Math.max(8, (count / maxEventDay) * 82)}px`, background: C.accent }} /><span className="max-w-full truncate font-mono text-[9px]" style={{ color: C.muted }}>{day}</span></div>)}</div> : <div className="flex h-28 items-center justify-center font-mono text-xs" style={{ color: C.muted }}>Historical data unavailable</div>}</section>
              <p className="font-mono text-[10px]" style={{ color: C.muted }}>Log type distribution unavailable: the current endpoint exposes the System channel only.</p>

              <Group title="Filters">
                <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-5">
                  <label className={labelCls} style={{ color: C.muted }}>
                    Event ID
                    <input aria-label="Event ID filter" value={systemEventIdFilter} onChange={(e) => { setSystemEventIdFilter(e.target.value.replace(/[^0-9]/g, "")); setSystemEventsOffset(0) }} placeholder="e.g. 7036" className={fieldCls} style={inputStyle} />
                  </label>
                  <label className={labelCls} style={{ color: C.muted }}>
                    Level
                    <select aria-label="Event level filter" value={systemEventLevelFilter} onChange={(e) => { setSystemEventLevelFilter(e.target.value); setSystemEventsOffset(0) }} className={fieldCls} style={inputStyle}>
                      <option value="">All levels</option><option>Critical</option><option>Error</option><option>Warning</option><option>Information</option>
                    </select>
                  </label>
                  <label className={labelCls} style={{ color: C.muted }}>
                    From
                    <input aria-label="Event start date" type="date" value={systemEventStartFilter} onChange={(e) => { setSystemEventStartFilter(e.target.value); setSystemEventsOffset(0) }} className={fieldCls} style={inputStyle} />
                  </label>
                  <label className={labelCls} style={{ color: C.muted }}>
                    To
                    <input aria-label="Event end date" type="date" value={systemEventEndFilter} onChange={(e) => { setSystemEventEndFilter(e.target.value); setSystemEventsOffset(0) }} className={fieldCls} style={inputStyle} />
                  </label>
                  <div className="flex items-end gap-2">
                    <button type="button" onClick={() => expandedDeviceId && void loadSystemEvents(expandedDeviceId, 0)} disabled={systemEventsLoading} className="flex-1 rounded-lg px-3 py-2 font-mono text-[10px] font-bold disabled:opacity-60" style={primaryBtn}>APPLY</button>
                    <button type="button" onClick={() => { clearEventFilters(); expandedDeviceId && void loadSystemEvents(expandedDeviceId, 0) }} className="rounded-lg px-3 py-2 font-mono text-[10px]" style={ghostBtn}>CLEAR</button>
                  </div>
                </div>
                <p className="mt-2 font-mono text-[10px]" style={{ color: C.muted }}>Log Type and Source/Provider filters are unavailable because the current endpoint does not expose those filter parameters.</p>
              </Group>

              <div className="event-panel overflow-x-auto rounded-xl border" style={{ borderColor: C.borderLight, boxShadow: "var(--wd-event-shadow)" }}>
                <table className="w-full min-w-[860px] text-left">
                  <thead>
                    <tr style={{ color: C.muted, background: C.bg }}>
                      {["Event Time", "Level", "Log Name", "Event ID", "Source / Provider", "Computer", "Message"].map((h) => <th key={h} className="px-3 py-2.5 font-mono text-[10px] uppercase tracking-wide">{h}</th>)}
                    </tr>
                  </thead>
                  <tbody>
                    {systemEventsLoading && !systemEvents.length ? (
                      <tr><td colSpan={7}><LoadingBlock text="Loading saved events…" /></td></tr>
                    ) : systemEvents.length ? systemEvents.map((item) => {
                      const open = expandedEventId === item.record_id
                      const message = item.message || NA
                      return (
                        <tr key={`${item.record_id}:${item.event_id}`} className="align-top transition-colors hover:brightness-110" style={{ borderTop: `1px solid ${C.borderLight}`, borderLeft: `3px solid ${levelColor(item.level)}` }}>
                          <td className="whitespace-nowrap px-3 py-2 font-mono text-[11px]">{fmtEventTime(item.time_created)}</td>
                          <td className="px-3 py-2"><Badge text={item.level || NA} color={levelColor(item.level)} /></td>
                          <td className="px-3 py-2 text-[11px]">System</td>
                          <td className="px-3 py-2 font-mono text-xs font-bold">{item.event_id}</td>
                          <td className="px-3 py-2 text-[11px]">{item.provider || NA}</td>
                          <td className="px-3 py-2 text-[11px]">{item.machine_name || NA}</td>
                          <td className="max-w-[420px] px-3 py-2 text-[11px]">
                            <button type="button" className="w-full whitespace-pre-wrap break-words text-left" onClick={() => setExpandedEventId(open ? null : item.record_id)} title={open ? "Click to collapse" : "Click to expand"}>
                              {open ? message : message.length > 120 ? `${message.slice(0, 120)}…` : message}
                              {message.length > 120 && <span className="ml-1 font-mono text-[10px]" style={{ color: C.accent }}>{open ? "less" : "more"}</span>}
                            </button>
                          </td>
                        </tr>
                      )
                    }) : (
                      <tr><td colSpan={7} className="px-3 py-8 text-center font-mono text-xs" style={{ color: C.muted }}>No saved events. Use FETCH SYSTEM EVENTS to collect them.</td></tr>
                    )}
                  </tbody>
                </table>
              </div>

              <div className="flex items-center justify-between font-mono text-[10px]" style={{ color: C.muted }}>
                <button type="button" className="rounded-lg px-3 py-1.5 disabled:opacity-40" style={ghostBtn} disabled={systemEventsOffset === 0 || systemEventsLoading} onClick={() => expandedDeviceId && void loadSystemEvents(expandedDeviceId, Math.max(0, systemEventsOffset - systemEventsLimit))}>← PREVIOUS</button>
                <span>Page {Math.floor(systemEventsOffset / systemEventsLimit) + 1} · offset {systemEventsOffset}</span>
                <button type="button" className="rounded-lg px-3 py-1.5 disabled:opacity-40" style={ghostBtn} disabled={!systemEventsHasNext || systemEventsLoading} onClick={() => expandedDeviceId && void loadSystemEvents(expandedDeviceId, systemEventsOffset + systemEventsLimit)}>NEXT →</button>
              </div>
            </div>
          </CardShell>
        )
    }
  }

  /* ───────────── render ───────────── */
  return (
    <div className="windows-devices-theme dashboard-page min-h-full space-y-5 rounded-2xl p-4 md:p-6 animate-fadeIn">
      <style>{`.windows-devices-theme{--wd-page:var(--t-bg);--wd-panel:var(--t-card);--wd-card:var(--t-card);--wd-table-header:var(--t-table-header);--wd-table-row:var(--t-table-row);--wd-table-hover:var(--t-table-row-hover);--wd-border:var(--t-border);--wd-border-light:var(--t-border-light);--wd-text:var(--t-text);--wd-muted:var(--t-muted);--wd-event-shadow:0 2px 8px rgba(15,23,42,.06);--wd-event-icon-bg:rgba(59,130,246,.08)}[data-theme="dark"] .windows-devices-theme{--wd-page:#000000;--wd-panel:#000000;--wd-card:#000000;--wd-table-header:#000000;--wd-table-row:#000000;--wd-table-hover:#000000;--wd-border:#303030;--wd-border-light:rgba(255,255,255,.16);--wd-text:#F1F5F9;--wd-muted:#A0A8B5;--wd-event-shadow:none;--wd-event-icon-bg:rgba(255,255,255,.08)}.windows-devices-theme .dashboard-page,.windows-devices-theme{background:var(--wd-page);color:var(--wd-text)}.windows-devices-theme input,.windows-devices-theme select{background:var(--wd-card);color:var(--wd-text);border-color:var(--wd-border);outline:none}.windows-devices-theme input:focus,.windows-devices-theme select:focus{border-color:var(--t-accent);box-shadow:0 0 0 2px color-mix(in srgb,var(--t-accent) 22%,transparent)}.windows-devices-theme input::placeholder{color:var(--wd-muted)}.windows-devices-theme table thead,.windows-devices-theme table thead th{background:var(--wd-table-header)}.windows-devices-theme table tbody tr{background:var(--wd-table-row)}.windows-devices-theme table tbody tr:hover{background:var(--wd-table-hover)}.windows-devices-theme .glass{background:var(--wd-panel)}.windows-devices-theme .event-summary-card{transition:transform .16s ease,box-shadow .16s ease}.windows-devices-theme .event-summary-card:hover{transform:translateY(-1px);box-shadow:0 4px 12px rgba(15,23,42,.10)}.windows-devices-theme .event-summary-icon{display:inline-flex;height:24px;width:24px;align-items:center;justify-content:center;border-radius:7px}`}</style>
      <header className="rounded-2xl border p-5 md:p-7" style={{ background: C.card, borderColor: C.border }}>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="font-display text-lg font-semibold tracking-tight md:text-2xl" style={{ color: C.text }}>WINDOWS DEVICES</h1>
            <p className="mt-1 font-mono text-xs" style={{ color: C.muted }}>Standalone and workgroup Windows PCs · WinRM HTTPS / NTLM</p>
          </div>
          {hasPermission("devices:create") && (
            <button type="button" onClick={() => (showAdd ? reset() : (setShowAdd(true), setError("")))} className="rounded-lg px-4 py-2 font-mono text-xs font-bold transition hover:brightness-110" style={showAdd ? ghostBtn : primaryBtn}>
              {showAdd ? "✕ CANCEL" : "+ ADD WINDOWS DEVICE"}
            </button>
          )}
        </div>
        <div className="mt-5 flex flex-wrap gap-2 font-mono text-[10px] uppercase" style={{ color: C.muted }}>
          <span className="rounded-full border px-3 py-1" style={{ borderColor: C.border }}>● Manual collection</span>
          <span className="rounded-full border px-3 py-1" style={{ borderColor: C.border }}>● PostgreSQL snapshots</span>
        </div>
      </header>

      {showAdd && (
        <GlassCard className="p-5">
          <h2 className="font-display text-lg font-bold" style={{ color: C.text }}>ADD WINDOWS DEVICE</h2>
          <div className="font-mono text-[10px]" style={{ color: C.muted }}>
            Step {step} of 3 · {step === 1 ? "Device Details" : step === 2 ? "Windows Credentials" : "Save & Test Connection"}
          </div>
          <Stepper step={step} />

          {step === 1 && (
            <div className="mt-5 grid grid-cols-1 gap-4 md:grid-cols-3">
              <label className={`${labelCls} md:col-span-3`} style={{ color: C.muted }}>
                Existing Device
                <select
                  value={selectedDeviceId}
                  onChange={(e) => {
                    const id = e.target.value
                    setSelectedDeviceId(id)
                    const d = allDevices.find((item) => String(item.id) === id)
                    if (d) setForm((v) => ({ ...v, hostname: d.hostname, ip_address: d.ip_address, site_id: d.site_id ? String(d.site_id) : "" }))
                    else setForm((v) => ({ ...v, hostname: "", ip_address: "", site_id: "" }))
                    setError("")
                  }}
                  disabled={saving || loading}
                  className={fieldCls}
                  style={inputStyle}
                >
                  <option value="">Add a new Windows device manually</option>
                  {allDevices.map((d) => <option key={d.id} value={d.id}>{d.hostname} · {d.ip_address} · ID {d.id}</option>)}
                </select>
              </label>
              <label className={`${labelCls} md:col-span-2`} style={{ color: C.muted }}>
                Connection Host (DNS/IP)
                <input value={form.connection_host} onChange={(e) => setForm({ ...form, connection_host: e.target.value })} disabled={saving} autoComplete="off" placeholder="Defaults to inventory hostname/IP" className={fieldCls} style={inputStyle} />
              </label>
              <label className={labelCls} style={{ color: C.muted }}>
                Hostname
                <input value={form.hostname} onChange={(e) => !selectedDeviceId && setForm({ ...form, hostname: e.target.value })} readOnly={Boolean(selectedDeviceId)} disabled={saving} className={fieldCls} style={{ ...inputStyle, opacity: selectedDeviceId ? 0.7 : 1 }} />
              </label>
              <label className={labelCls} style={{ color: C.muted }}>
                IP Address
                <input value={form.ip_address} onChange={(e) => !selectedDeviceId && setForm({ ...form, ip_address: e.target.value })} readOnly={Boolean(selectedDeviceId)} disabled={saving} className={fieldCls} style={{ ...inputStyle, opacity: selectedDeviceId ? 0.7 : 1 }} />
              </label>
              <label className={labelCls} style={{ color: C.muted }}>
                Authorized Site
                <select value={form.site_id} onChange={(e) => !selectedDeviceId && setForm({ ...form, site_id: e.target.value })} disabled={saving || sitesLoading || !sites.length || Boolean(selectedDeviceId)} className={fieldCls} style={inputStyle}>
                  <option value="">{sitesLoading ? "Loading sites…" : sites.length ? "Select site" : "No accessible sites"}</option>
                  {sites.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                </select>
              </label>
            </div>
          )}

          {step === 2 && (
            <div className="mt-5 grid grid-cols-1 gap-4 md:grid-cols-2">
              <label className={labelCls} style={{ color: C.muted }}>
                Username
                <input value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} disabled={saving} autoComplete="off" className={fieldCls} style={inputStyle} />
              </label>
              <label className={labelCls} style={{ color: C.muted }}>
                Domain / Computer Name
                <input value={form.domain} onChange={(e) => setForm({ ...form, domain: e.target.value })} disabled={saving} autoComplete="off" className={fieldCls} style={inputStyle} />
              </label>
              <label className={`${labelCls} md:col-span-2`} style={{ color: C.muted }}>
                Password {existingCredential && <span className="normal-case">(leave blank to keep current)</span>}
                <div className="mt-1 flex">
                  <input type={showPassword ? "text" : "password"} value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} disabled={saving} autoComplete="new-password" className="w-full rounded-l-lg px-3 py-2 text-sm outline-none" style={inputStyle} />
                  <button type="button" onClick={() => setShowPassword((v) => !v)} disabled={saving} className="rounded-r-lg px-3 font-mono text-[10px]" style={{ ...ghostBtn, borderLeft: "none" }}>{showPassword ? "HIDE" : "SHOW"}</button>
                </div>
              </label>
            </div>
          )}

          {step === 3 && (
            <div className="mt-5 grid gap-3 md:grid-cols-2">
              <Group title="Device">
                <KV rows={[["Hostname", form.hostname], ["IP address", form.ip_address], ["Connection host", form.connection_host || "Inventory hostname/IP"], ["Site", sites.find((s) => String(s.id) === form.site_id)?.name ?? "—"]]} />
              </Group>
              <Group title="Credentials">
                <KV rows={[["Username", form.username], ["Domain / computer", form.domain], ["Password", "••••••••"]]} />
              </Group>
              {progressLabel && (
                <div className="md:col-span-2">
                  <Badge text={progressLabel} color={progress === "connected" ? C.success : progress === "failed" ? C.danger : C.accent} />
                </div>
              )}
            </div>
          )}

          {error && (
            <div role="alert" className="mt-4 rounded-lg p-3 font-mono text-xs" style={{ color: C.danger, border: `1px solid ${C.danger}` }}>
              ⚠ {error}
              {duplicate && (
                <div className="mt-2">
                  <Link to={`/devices/${duplicate.id}`} className="underline" style={{ color: C.accent }}>
                    OPEN EXISTING DEVICE {duplicate.hostname} (ID {duplicate.id})
                  </Link>
                </div>
              )}
            </div>
          )}
          {onboardingNotice && (
            <div role="status" className="mt-4 rounded-lg p-3 font-mono text-xs" style={{ color: C.success, border: `1px solid ${C.success}` }}>✓ {onboardingNotice}</div>
          )}

          <div className="mt-5 flex flex-wrap gap-2">
            {step > 1 && <button type="button" onClick={() => setStep((step - 1) as Step)} disabled={saving} className="rounded-lg px-4 py-2 font-mono text-xs disabled:opacity-60" style={ghostBtn}>← BACK</button>}
            {step === 1 && <button type="button" onClick={deviceStep} disabled={saving} className="rounded-lg px-4 py-2 font-mono text-xs font-bold disabled:opacity-60" style={primaryBtn}>CONTINUE →</button>}
            {step === 2 && <button type="button" onClick={credentialStep} disabled={saving || credentialLoading} className="rounded-lg px-4 py-2 font-mono text-xs font-bold disabled:opacity-60" style={primaryBtn}>{credentialLoading ? "LOADING…" : "CONTINUE →"}</button>}
            {step === 3 && (
              <button type="button" onClick={() => void onboard()} disabled={saving || progress === "connected"} className="rounded-lg px-4 py-2 font-mono text-xs font-bold disabled:opacity-60" style={primaryBtn}>
                {saving ? "PROCESSING…" : progress === "failed" ? "RETRY" : "SAVE & TEST CONNECTION"}
              </button>
            )}
          </div>
        </GlassCard>
      )}

      {!showAdd && error && (
        <div role="alert" className="rounded-lg border p-3 font-mono text-xs" style={{ color: C.danger, borderColor: C.danger }}>⚠ {error}</div>
      )}

      {/* ───────────── DEVICE DETAIL VIEW ───────────── */}
      {inDetail ? (
        <div className="space-y-4">
          <GlassCard className="p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <button type="button" onClick={() => navigate("/windows-devices")} className="font-mono text-[11px] font-bold hover:underline" style={{ color: C.accent }}>← BACK TO WINDOWS DEVICES</button>
              <div className="flex flex-wrap gap-2">
                {detailDevice && hasPermission("devices:update") && <button type="button" disabled={thresholdLoading} onClick={() => { setThresholdDraft(thresholds); setThresholdError(""); setThresholdNotice(""); setThresholdDialogOpen(true) }} className="rounded-lg border px-3 py-1.5 font-mono text-[10px] font-bold disabled:opacity-50" style={ghostBtn}>⚙ THRESHOLD SETTINGS</button>}
                {hasPermission("devices:delete") && detailDevice && (
                  <button type="button" onClick={() => void removeDevice(detailDevice)} className="rounded-lg border px-3 py-1.5 font-mono text-[10px] font-bold" style={{ color: C.danger, borderColor: C.danger }}>🗑 DELETE DEVICE</button>
                )}
              </div>
            </div>
            {detailDevice && (
              <div className="mt-4 grid grid-cols-2 gap-2 md:grid-cols-4">
                <Tile label="Hostname" value={detailDevice.hostname} />
                <Tile label="IP address" value={detailDevice.ip_address} />
                <Tile label="Device ID" value={detailDevice.id} />
                <Tile label="Status" value={<Badge text={detailDevice.status || "Unknown"} color={isOnlineStatus(detailDevice.status) ? C.success : C.muted} />} accent={isOnlineStatus(detailDevice.status) ? C.success : C.muted} />
              </div>
            )}
          </GlassCard>

          {thresholdDialogOpen && detailDevice && (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" role="dialog" aria-modal="true" aria-label="Threshold Settings" onClick={() => setThresholdDialogOpen(false)}>
              <div className="w-full max-w-sm rounded-xl border bg-white p-5 shadow-2xl" style={{ borderColor: C.border }} onClick={(event) => event.stopPropagation()}>
                <div className="flex items-start justify-between gap-3">
                  <div><h2 className="font-display text-lg font-bold" style={{ color: C.text }}>Threshold Settings</h2><p className="mt-1 text-xs" style={{ color: C.muted }}>Device {detailDevice.id} · values are percentages</p></div>
                  <button type="button" aria-label="Close threshold settings" onClick={() => setThresholdDialogOpen(false)} className="text-lg" style={{ color: C.muted }}>×</button>
                </div>
                <div className="mt-4 space-y-3">
                  {thresholdLoading && <p className="text-xs" style={{ color: C.muted }}>Loading backend settings…</p>}
                  {thresholdError && <p role="alert" className="rounded border p-2 text-xs" style={{ color: C.danger, borderColor: C.danger }}>⚠ {thresholdError}</p>}
                  {thresholdNotice && <p role="status" className="rounded border p-2 text-xs" style={{ color: C.success, borderColor: C.success }}>{thresholdNotice}</p>}
                  {([['cpu', 'CPU'], ['memory', 'Memory'], ['disk', 'Disk']] as const).map(([key, label]) => (
                    <label key={key} className="block text-xs font-semibold" style={{ color: C.text }}>{label} usage threshold
                      <div className="mt-1 flex items-center gap-2"><input aria-label={`${label} threshold`} type="number" min={1} max={100} step={1} value={thresholdDraft[key]} onChange={(event) => setThresholdDraft((current) => ({ ...current, [key]: safeThreshold(event.target.value, current[key]) }))} className={fieldCls} style={inputStyle} /><span style={{ color: C.muted }}>%</span></div>
                    </label>
                  ))}
                </div>
                <div className="mt-5 flex justify-end gap-2"><button type="button" onClick={() => setThresholdDialogOpen(false)} className="rounded-lg px-4 py-2 font-mono text-xs" style={ghostBtn}>CANCEL</button><button type="button" disabled={thresholdSaving || thresholdLoading} onClick={() => void saveThresholds()} className="rounded-lg px-4 py-2 font-mono text-xs font-bold disabled:opacity-50" style={primaryBtn}>{thresholdSaving ? "SAVING…" : "SAVE"}</button></div>
              </div>
            </div>
          )}

          <div className="overflow-x-auto rounded-xl border" style={{ borderColor: C.borderLight, background: C.card }}>
            <nav className="flex min-w-max items-center gap-1 p-1" aria-label="Windows device sections">
              {tabNames.map((tab) => (
                <button
                  key={tab}
                  type="button"
                  onClick={() => selectDeviceTab(tab)}
                  aria-current={activeDeviceTab === tab ? "page" : undefined}
                  className="flex items-center gap-2 rounded-lg px-3 py-2 font-mono text-[10px] uppercase transition-colors"
                  style={{
                    color: activeDeviceTab === tab ? C.accent : C.muted,
                    background: activeDeviceTab === tab ? "var(--t-table-row-hover)" : "transparent",
                    borderBottom: activeDeviceTab === tab ? `2px solid ${C.accent}` : "2px solid transparent",
                  }}
                >
                  <span aria-hidden>{tabIcons[tab]}</span>
                  {tabLabels[tab]}
                </button>
              ))}
            </nav>
          </div>

          {loading && !detailDevice ? (
            <GlassCard className="p-6"><LoadingBlock text="Loading Windows device…" /></GlassCard>
          ) : !detailDevice ? (
            <GlassCard className="p-6 text-center font-mono text-xs">Windows device {routeDeviceId} was not found.</GlassCard>
          ) : (
            renderTab(detailDevice)
          )}
        </div>
      ) : (
        /* ───────────── DEVICE LIST VIEW ───────────── */
        <>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            {([["WINDOWS DEVICES", devices.length, C.accent], ["ONLINE", online, C.success], ["OFFLINE / UNKNOWN", devices.length - online, C.muted]] as const).map(([label, value, color]) => (
              <GlassCard key={label} className="p-4">
                <div className="flex items-center gap-2 font-mono text-[10px]" style={{ color: C.muted }}>
                  <span className="inline-block h-2 w-2 rounded-full" style={{ background: color }} />
                  {label}
                </div>
                <div className="mt-2 font-display text-3xl font-bold" style={{ color: C.text }}>{value}</div>
              </GlassCard>
            ))}
          </div>

          <GlassCard className="overflow-hidden">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b p-4" style={{ borderColor: C.borderLight }}>
              <div>
                <div className="font-display text-lg font-bold" style={{ color: C.text }}>Managed Windows Devices</div>
                <div className="font-mono text-[10px] uppercase" style={{ color: C.muted }}>{filteredDevices.length} of {devices.length} devices</div>
              </div>
              <div className="flex flex-wrap gap-2">
                <input value={deviceQuery} onChange={(e) => setDeviceQuery(e.target.value)} placeholder="🔍 Search hostname, IP, ID" className="rounded-lg border px-3 py-2 font-mono text-xs outline-none focus:ring-2" style={{ background: C.bg, borderColor: C.border, color: C.text }} />
                <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value as typeof statusFilter)} className="rounded-lg border px-3 py-2 font-mono text-xs outline-none" style={{ background: C.bg, borderColor: C.border, color: C.text }}>
                  <option value="all">All status</option><option value="online">Online</option><option value="offline">Offline / unknown</option>
                </select>
              </div>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[720px] text-left">
                <thead>
                  <tr style={{ background: C.bg, borderBottom: `1px solid ${C.borderLight}` }}>
                    {["Device", "IP Address", "Site", "Status", "Action"].map((h) => (
                      <th key={h} className="px-4 py-3 font-mono text-[10px] uppercase tracking-wide" style={{ color: C.muted }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {loading ? (
                    <tr><td colSpan={5}><LoadingBlock text="Loading Windows devices…" /></td></tr>
                  ) : filteredDevices.length ? (
                    filteredDevices.map((d) => {
                      const up = isOnlineStatus(d.status)
                      return (
                        <tr key={d.id} className="transition-colors hover:brightness-110" style={{ borderTop: `1px solid ${C.borderLight}`, borderLeft: `3px solid ${up ? C.success : C.borderLight}` }}>
                          <td className="px-4 py-3">
                            <button type="button" onClick={() => navigate(`/windows-devices/${d.id}`)} className="text-left text-sm font-semibold hover:underline">{d.hostname}</button>
                            <div className="font-mono text-[10px]" style={{ color: C.muted }}>ID {d.id}</div>
                          </td>
                          <td className="px-4 py-3 font-mono text-xs">{d.ip_address}</td>
                          <td className="px-4 py-3 text-xs">{siteName(d.site_id)}</td>
                          <td className="px-4 py-3"><Badge text={d.status || "Unknown"} color={up ? C.success : C.muted} /></td>
                          <td className="px-4 py-3">
                            <button type="button" onClick={() => navigate(`/windows-devices/${d.id}`)} className="mr-3 rounded-lg px-3 py-1 font-mono text-[10px] font-bold" style={primaryBtn}>DETAILS →</button>
                            {hasPermission("devices:delete") && (
                              <button type="button" onClick={() => void removeDevice(d)} className="rounded-lg border px-3 py-1 font-mono text-[10px]" style={{ color: C.danger, borderColor: C.danger }}>DELETE</button>
                            )}
                          </td>
                        </tr>
                      )
                    })
                  ) : (
                    <tr><td colSpan={5}><EmptyState text="No Windows devices found." /></td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </GlassCard>
        </>
      )}
    </div>
  )
}
