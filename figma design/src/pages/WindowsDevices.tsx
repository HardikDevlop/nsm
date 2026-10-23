/* eslint-disable @typescript-eslint/no-explicit-any */
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react"
import { Link, useNavigate, useParams } from "react-router"
import GlassCard from "../components/GlassCard"
import WindowsDeviceOverview from "../components/WindowsDeviceOverview"
import WindowsDiskInventoryPanel from "../components/WindowsDiskInventory"
import WindowsStorageHealth from "../components/WindowsStorageHealth"
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

const tabNames = ["overview", "cpu", "memory", "disk", "network", "hardware", "storage", "events"] as const
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
}
const metricTabs: TabName[] = ["overview", "cpu", "memory", "disk", "network"]

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
const norm = (v: string) => v.trim().toLowerCase()
const isNum = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v)

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
const fmtBytes = (v?: number | null) => {
  if (!isNum(v)) return NA
  if (v < 1024 ** 3) return `${(v / 1024 ** 2).toFixed(1)} MiB`
  return `${(v / 1024 ** 3).toFixed(1)} GiB`
}
const fmtMiB = (v: number) => (v >= 1024 ? `${(v / 1024).toFixed(1)} GiB` : `${v.toFixed(1)} MiB`)
const fmtRate = (v?: number | null) => {
  if (!isNum(v)) return NA
  if (v < 1024) return `${v.toFixed(0)} B/s`
  if (v < 1024 ** 2) return `${(v / 1024).toFixed(1)} KB/s`
  return `${(v / 1024 ** 2).toFixed(1)} MB/s`
}
const fmtThroughput = (v: number) => (v >= 1024 ** 2 ? `${(v / 1024 ** 2).toFixed(1)} MiB/s` : `${(v / 1024).toFixed(1)} KiB/s`)
const fmtPct = (v: unknown) => (isNum(v) ? `${Number(v).toFixed(1)}%` : NA)
const fmtLinkSpeed = (v?: number | null) => {
  if (!isNum(v)) return NA
  if (v >= 1_000_000_000) return `${(v / 1_000_000_000).toFixed(1)} Gbps`
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)} Mbps`
  return `${(v / 1000).toFixed(1)} Kbps`
}
const fmtDateTime = (value?: string | null) =>
  value ? new Date(value).toLocaleString("en-IN", { timeZone: "Asia/Kolkata" }) : "Never fetched"
const fmtEventTime = (value: string | null | undefined) => {
  if (!value) return NA
  const utc = /(?:Z|[+-]\d{2}:\d{2})$/.test(value) ? value : `${value}Z`
  const date = new Date(utc)
  return Number.isNaN(date.getTime()) ? NA : date.toLocaleString("en-IN", { timeZone: "Asia/Kolkata" })
}
const fmtOsDate = (value: unknown) => {
  if (typeof value !== "string" || !value) return "Not available"
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? "Not available" : date.toLocaleString("en-IN", { timeZone: "Asia/Kolkata" })
}
const fmtHardwareDate = (value: unknown) => {
  if (typeof value !== "string" || !value) return NA
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? NA : date.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" })
}
const fmtUptime = (value: unknown) => {
  if (!isNum(value) || value < 0) return "Not available"
  const totalMinutes = Math.floor(value / 60)
  const days = Math.floor(totalMinutes / 1440)
  const hours = Math.floor((totalMinutes % 1440) / 60)
  return `${days}d ${hours}h ${totalMinutes % 60}m`
}
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
   Reusable UI building blocks (cards, bars, tiles, badges)
   ════════════════════════════════════════════════════════════════ */
const tone = (v: number | null) => {
  if (v == null) return "var(--t-muted)"
  if (v >= 90) return "var(--t-danger)"
  if (v >= 70) return "var(--t-warning, #f59e0b)"
  return "var(--t-success)"
}

function Bar({ label, value, right }: { label: string; value: unknown; right?: string }) {
  const v = isNum(value) ? Math.max(0, Math.min(100, value)) : null
  return (
    <div>
      <div className="flex items-baseline justify-between gap-2 text-xs">
        <span style={{ color: "var(--t-muted)" }}>{label}</span>
        <span className="font-mono" style={{ color: v == null ? "var(--t-muted)" : "var(--t-text)" }}>{right ?? fmtPct(value)}</span>
      </div>
      <div className="mt-1 h-2 w-full overflow-hidden rounded-full" style={{ background: "var(--t-border-light)" }}>
        <div className="h-full rounded-full transition-all" style={{ width: `${v ?? 0}%`, background: tone(v) }} />
      </div>
    </div>
  )
}

function Tile({ label, value, sub }: { label: string; value: ReactNode; sub?: ReactNode }) {
  const muted = ["N/A", "Unavailable", "Not Supported", "Permission Denied", "Collection Failed", "Not available"].includes(String(value))
  return (
    <div className="rounded-lg border p-2.5" style={{ borderColor: "var(--t-border-light)", background: "var(--t-card)" }}>
      <div className="font-mono text-[10px] uppercase" style={{ color: "var(--t-muted)" }}>{label}</div>
      <div className="mt-1 break-words text-sm font-semibold" style={{ color: muted ? "var(--t-muted)" : "var(--t-text)" }}>{value}</div>
      {sub != null && <div className="mt-0.5 break-words font-mono text-[10px]" style={{ color: "var(--t-muted)" }}>{sub}</div>}
    </div>
  )
}

function Group({ title, children, className = "" }: { title: string; children: ReactNode; className?: string }) {
  return (
    <div className={`rounded-xl border p-3 ${className}`} style={{ borderColor: "var(--t-border-light)", background: "var(--t-bg)" }}>
      <div className="mb-2 font-mono text-[10px] uppercase" style={{ color: "var(--t-muted)" }}>{title}</div>
      {children}
    </div>
  )
}

function Badge({ text, color }: { text: string; color: string }) {
  return (
    <span className="inline-block rounded-full border px-2 py-0.5 font-mono text-[10px] uppercase" style={{ color, borderColor: color }}>
      {text}
    </span>
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
    <GlassCard className="p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="font-display text-base font-bold" style={{ color: "var(--t-text)" }}>{title}</div>
          {subtitle && <div className="font-mono text-[10px]" style={{ color: "var(--t-muted)" }}>{subtitle}</div>}
          {collectedAt !== undefined && (
            <div className="mt-1 font-mono text-[10px]" style={{ color: "var(--t-muted)" }}>
              Last collected: {fmtDateTime(collectedAt)}
              {success && <span className="ml-2" style={{ color: "var(--t-success)" }}>· FETCH COMPLETE</span>}
            </div>
          )}
        </div>
        {action}
      </div>
      {error && (
        <div role="alert" className="mt-3 rounded border p-2 font-mono text-[10px]" style={{ color: "var(--t-danger)", borderColor: "var(--t-danger)" }}>
          {error}
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
      className="rounded px-4 py-2 font-mono text-[10px]"
      style={{ background: "var(--t-accent)", color: "var(--t-bg)", opacity: busy || disabled ? 0.7 : 1 }}
    >
      {busy ? busyLabel : label}
    </button>
  )
}

const EmptyState = ({ text = "No saved data. Use the FETCH button to collect it." }: { text?: string }) => (
  <div className="rounded-lg border border-dashed p-6 text-center font-mono text-xs" style={{ color: "var(--t-muted)", borderColor: "var(--t-border-light)" }}>
    {text}
  </div>
)

/* ════════════════════════════════════════════════════════════════
   CPU panel
   ════════════════════════════════════════════════════════════════ */
function CpuBody({ data }: { data: any }) {
  const c = data.counters || {}
  const val = (k: string) => c[k]?.value
  const perCpu: any[] = Array.isArray(data.logical_processors_usage) ? data.logical_processors_usage : []
  const unsupported = Object.values(c).some((x: any) => x?.status === "unsupported")
  return (
    <div className="space-y-4">
      <div className="grid gap-3 md:grid-cols-3">
        <Group title="Total Utilization">
          <div className="text-3xl font-bold" style={{ color: tone(isNum(data.usage_percent) ? data.usage_percent : null) }}>{fmtPct(data.usage_percent)}</div>
          <div className="mt-2"><Bar label="Usage" value={data.usage_percent} /></div>
        </Group>
        <div className="grid grid-cols-2 gap-2 md:col-span-2 lg:grid-cols-3">
          <Tile label="Physical cores" value={data.identity?.physical_cores ?? NA} />
          <Tile label="Logical processors" value={data.identity?.logical_processors ?? data.logical_processors ?? NA} />
          <Tile label="Processor queue" value={counterText(c.processor_queue_length)} />
          <Tile label="Interrupts / sec" value={counterText(c.interrupts_per_sec)} />
          <Tile label="Context switches / sec" value={counterText(c.context_switches_per_sec)} />
          <Tile label="Idle time" value={isNum(val("idle_time_percent")) ? fmtPct(val("idle_time_percent")) : counterText(c.idle_time_percent)} />
        </div>
      </div>
      <Group title="Time Distribution">
        <div className="grid gap-3 md:grid-cols-3">
          <Bar label="User" value={val("user_time_percent")} />
          <Bar label="Privileged" value={val("privileged_time_percent")} />
          <Bar label="Idle" value={val("idle_time_percent")} />
        </div>
      </Group>
      {perCpu.length > 0 && (
        <Group title="Per Logical CPU">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {perCpu.map((row, i) => <Bar key={row.name ?? i} label={`CPU ${row.name ?? i}`} value={row.usage_percent} />)}
          </div>
        </Group>
      )}
      {unsupported && <div className="font-mono text-[10px]" style={{ color: "var(--t-muted)" }}>Some CPU counters are unsupported by this Windows provider.</div>}
    </div>
  )
}

/* ════════════════════════════════════════════════════════════════
   Memory panel
   ════════════════════════════════════════════════════════════════ */
function MemoryBody({ data }: { data: any }) {
  const counters = data.counters || {}
  const k = (name: string) => counters[name] as WindowsMemoryCounter | undefined
  return (
    <div className="space-y-4">
      <div className="grid gap-3 md:grid-cols-3">
        <Group title="Memory Usage">
          <div className="text-3xl font-bold" style={{ color: tone(isNum(data.usage_percent) ? data.usage_percent : null) }}>{fmtPct(data.usage_percent)}</div>
          <div className="mt-2"><Bar label="Used" value={data.usage_percent} right={`${fmtBytes(data.used_bytes)} / ${fmtBytes(data.total_bytes)}`} /></div>
        </Group>
        <div className="grid grid-cols-2 gap-2 md:col-span-2">
          <Tile label="Total" value={fmtBytes(data.total_bytes)} />
          <Tile label="Used" value={fmtBytes(data.used_bytes)} />
          <Tile label="OS free" value={fmtBytes(data.free_bytes)} />
          <Tile label="PerfMon available" value={counterText(k("available_mbytes"), fmtMiB)} />
        </div>
      </div>
      <div className="grid gap-3 md:grid-cols-3">
        <Group title="Commit & Cache">
          <div className="grid grid-cols-2 gap-2">
            <Tile label="Committed" value={counterText(k("committed_bytes"), fmtBytes)} />
            <Tile label="Commit limit" value={counterText(k("commit_limit"), fmtBytes)} />
            <Tile label="Cache" value={counterText(k("cache_bytes"), fmtBytes)} />
          </div>
          <div className="mt-3">
            <Bar label="Commit usage" value={k("percent_committed_bytes_in_use")?.value} right={counterText(k("percent_committed_bytes_in_use"), (v) => `${v.toFixed(1)}%`)} />
          </div>
        </Group>
        <Group title="Paging Activity">
          <div className="grid grid-cols-2 gap-2">
            <Tile label="Pages / sec" value={counterText(k("pages_per_sec"), String)} />
            <Tile label="Reads / sec" value={counterText(k("page_reads_per_sec"), String)} />
            <Tile label="Writes / sec" value={counterText(k("page_writes_per_sec"), String)} />
            <Tile label="Faults / sec" value={counterText(k("page_faults_per_sec"), String)} />
          </div>
        </Group>
        <Group title="Kernel Memory">
          <div className="grid grid-cols-2 gap-2">
            <Tile label="Paged pool" value={counterText(k("pool_paged_bytes"), fmtBytes)} />
            <Tile label="Nonpaged pool" value={counterText(k("pool_nonpaged_bytes"), fmtBytes)} />
          </div>
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
  ["Read latency", "read_latency_ms", (v) => `${v} ms`],
  ["Write latency", "write_latency_ms", (v) => `${v} ms`],
  ["Avg latency", "average_latency_ms", (v) => `${v} ms`],
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
function DiskBody({ data }: { data: any }) {
  const disks = (Array.isArray(data) ? data : []) as WindowsDiskCapacity[]
  const perf: any = disks[0]?.performance
  const totalSize = disks.reduce((s, d) => s + (isNum(d.size_bytes) ? d.size_bytes : 0), 0)
  const totalUsed = disks.reduce((s, d) => s + (isNum(d.used_bytes) ? d.used_bytes : 0), 0)
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
        <Tile label="Volumes" value={disks.length} />
        <Tile label="Total capacity" value={fmtBytes(totalSize)} />
        <Tile label="Used" value={fmtBytes(totalUsed)} />
        <Tile label="Free" value={fmtBytes(Math.max(0, totalSize - totalUsed))} />
      </div>
      <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
        {disks.map((d) => (
          <Group key={d.device_id} title={`${d.device_id || NA} · ${d.volume_name || "Unnamed volume"}`}>
            <Bar label="Used" value={d.usage_percent} right={`${fmtPct(d.usage_percent)} · ${fmtBytes(d.used_bytes)} / ${fmtBytes(d.size_bytes)}`} />
          </Group>
        ))}
        {!disks.length && <EmptyState text="No volumes reported." />}
      </div>
      {perf ? (
        <div className="space-y-3">
          {([["Logical", perf.logical], ["Physical", perf.physical]] as const).map(([kind, rows]) => (
            <Group key={kind} title={`${kind} Disk Performance`}>
              {rows?.length ? (
                <div className="space-y-4">
                  {rows.map((row: any) => (
                    <div key={`${kind}:${row.instance}`}>
                      <div className="mb-2 font-mono text-xs">{kind} instance: {row.instance}</div>
                      <DiskCounters metrics={row.metrics} />
                    </div>
                  ))}
                </div>
              ) : <div className="text-xs" style={{ color: "var(--t-muted)" }}>No {kind.toLowerCase()} performance instances</div>}
            </Group>
          ))}
          <div className="grid gap-3 md:grid-cols-2">
            {(["logical", "physical"] as const).map((kind) => (
              <Group key={kind} title={`${kind} aggregate`}>
                {perf.aggregate?.[kind] ? <DiskCounters metrics={perf.aggregate[kind]} /> : <div className="text-xs" style={{ color: "var(--t-muted)" }}>Unavailable</div>}
              </Group>
            ))}
          </div>
        </div>
      ) : <div className="text-xs" style={{ color: "var(--t-muted)" }}>Disk performance unavailable in this snapshot.</div>}
    </div>
  )
}

/* ════════════════════════════════════════════════════════════════
   Network panel
   ════════════════════════════════════════════════════════════════ */
function NetworkBody({ data }: { data: any }) {
  const adapters: Array<Record<string, any>> = Array.isArray(data) ? data : []
  if (!adapters.length) return <EmptyState />
  const active = adapters.filter((a) => /up|connected/i.test(String(a.interface_status ?? ""))).length
  const rx = adapters.reduce((s, a) => s + (isNum(a.rx_bytes_per_sec) ? a.rx_bytes_per_sec : 0), 0)
  const tx = adapters.reduce((s, a) => s + (isNum(a.tx_bytes_per_sec) ? a.tx_bytes_per_sec : 0), 0)
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
        <Tile label="Adapters" value={adapters.length} />
        <Tile label="Active" value={active} />
        <Tile label="Total RX" value={fmtRate(rx)} />
        <Tile label="Total TX" value={fmtRate(tx)} />
      </div>
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {adapters.map((a) => {
          const ipv4: string[] = Array.isArray(a.ipv4_addresses) ? a.ipv4_addresses : []
          const ipv6: string[] = Array.isArray(a.ipv6_addresses) ? a.ipv6_addresses : []
          const up = /up|connected/i.test(String(a.interface_status ?? ""))
          return (
            <Group key={networkRowKey(a)} title={`Interface ${a.interface_index ?? NA}${a.adapter_index != null ? ` · Adapter ${a.adapter_index}` : ""}`}>
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="break-words text-sm font-semibold">{String(a.name || NA)}</div>
                  <div className="break-words font-mono text-[10px]" style={{ color: "var(--t-muted)" }}>{String(a.description || NA)}</div>
                </div>
                <Badge text={String(a.interface_status || "Unknown")} color={up ? "var(--t-success)" : "var(--t-muted)"} />
              </div>
              <div className="mt-3 grid grid-cols-2 gap-2">
                <Tile label="MAC" value={String(a.mac_address || NA)} />
                <Tile label="Link speed" value={fmtLinkSpeed(isNum(a.link_speed_bps) ? a.link_speed_bps : null)} />
                <Tile label="Receive" value={fmtRate(isNum(a.rx_bytes_per_sec) ? a.rx_bytes_per_sec : null)} />
                <Tile label="Transmit" value={fmtRate(isNum(a.tx_bytes_per_sec) ? a.tx_bytes_per_sec : null)} />
              </div>
              <div className="mt-2 grid gap-2">
                <Tile label="IPv4" value={ipv4.length ? ipv4.join(", ") : NA} />
                <Tile label="IPv6" value={ipv6.length ? ipv6.join(", ") : NA} />
              </div>
            </Group>
          )
        })}
      </div>
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
  return (
    <div className="space-y-4">
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        {blocks.map(([title, data, fields]) => (
          <Group key={title} title={title}>
            <div className="grid gap-2">{fields.map(([label, key]) => <Tile key={key} label={label} value={show(data, key)} />)}</div>
          </Group>
        ))}
      </div>
      <Group title="CPU Details">
        {processors.length ? (
          <div className="grid gap-3 md:grid-cols-2">
            {processors.map((cpu, i) => (
              <div key={i} className="rounded-lg border p-3" style={{ borderColor: "var(--t-border-light)", background: "var(--t-card)" }}>
                <div className="text-sm font-semibold">{String(cpu.name || NA)}</div>
                <div className="font-mono text-[10px]" style={{ color: "var(--t-muted)" }}>{String(cpu.manufacturer || NA)}</div>
                <div className="mt-2 grid grid-cols-3 gap-2">
                  <Tile label="Cores" value={cpu.number_of_cores == null ? NA : String(cpu.number_of_cores)} />
                  <Tile label="Threads" value={cpu.number_of_logical_processors == null ? NA : String(cpu.number_of_logical_processors)} />
                  <Tile label="Max freq" value={cpu.max_clock_speed_mhz == null ? NA : `${cpu.max_clock_speed_mhz} MHz`} />
                </div>
              </div>
            ))}
          </div>
        ) : <EmptyState text="No saved CPU data." />}
      </Group>
      <div className="grid gap-3 lg:grid-cols-3">
        <Group title="Memory Arrays" className="lg:col-span-1">
          {arrays.length ? (
            <div className="space-y-2">
              {arrays.map((arr, i) => (
                <div key={i} className="grid grid-cols-3 gap-2">
                  <Tile label="Capacity" value={fmtBytes(isNum(arr.max_capacity_bytes) ? arr.max_capacity_bytes : null)} />
                  <Tile label="Slots" value={arr.memory_devices == null ? NA : String(arr.memory_devices)} />
                  <Tile label="Location" value={String(arr.location || NA)} />
                </div>
              ))}
            </div>
          ) : <EmptyState text="No saved data." />}
        </Group>
        <Group title="Physical RAM Modules" className="lg:col-span-2">
          {modules.length ? (
            <div className="grid gap-3 md:grid-cols-2">
              {modules.map((m, i) => (
                <div key={i} className="rounded-lg border p-3" style={{ borderColor: "var(--t-border-light)", background: "var(--t-card)" }}>
                  <div className="text-sm font-semibold">{fmtBytes(isNum(m.capacity_bytes) ? m.capacity_bytes : null)} · {String(m.device_locator || `Module ${i + 1}`)}</div>
                  <div className="mt-2 grid grid-cols-2 gap-2">
                    <Tile label="Speed" value={m.speed_mhz == null ? NA : `${m.speed_mhz} MHz`} />
                    <Tile label="Manufacturer" value={String(m.manufacturer || NA)} />
                    <Tile label="Memory type" value={m.smbios_memory_type == null ? NA : String(m.smbios_memory_type)} />
                    <Tile label="Bank label" value={String(m.bank_label || NA)} />
                  </div>
                </div>
              ))}
            </div>
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
            <Group key={group} title={group}>
              {rows.length ? (
                <div className="space-y-2">
                  {rows.map((s) => (
                    <div key={s.sensor_id || `${s.source}:${s.sensor_name}`} className="rounded-lg border p-2" style={{ borderColor: "var(--t-border-light)", background: "var(--t-card)" }}>
                      <div className="text-xs">{s.sensor_name}</div>
                      <div className="font-mono text-sm font-semibold" style={{ color: "var(--t-success)" }}>{sensorValue(s)}</div>
                      <div className="font-mono text-[10px]" style={{ color: "var(--t-muted)" }}>{s.source}</div>
                    </div>
                  ))}
                </div>
              ) : <div className="font-mono text-xs" style={{ color: "var(--t-muted)" }}>No sensors reported</div>}
            </Group>
          )
        })}
      </div>
      {bad.length > 0 && (
        <Group title="Unsupported / Unavailable Sensors">
          <div className="grid gap-2 md:grid-cols-3">
            {bad.map((s) => <Tile key={`${s.source}:${s.sensor_name}`} label={s.source} value={s.sensor_name} sub={sensorValue(s)} />)}
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
          <div className="grid gap-2">{fields.map(([label, key]) => <Tile key={key} label={label} value={display(key, data?.[key])} />)}</div>
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
      const result = await fetchWindowsSystemEvents(deviceId)
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

  // Storage tab: auto-load inventory and health
  useEffect(() => {
    if (activeDeviceTab !== "storage" || !expandedDeviceId) return
    setDiskInventoryOpen(true)
    setDiskHealthOpen(true)
    void loadDiskInventory().catch(() => undefined)
    void loadDiskHealth().catch(() => undefined)
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
    /critical|error/i.test(level ?? "") ? "var(--t-danger)" : /warn/i.test(level ?? "") ? "var(--t-warning, #f59e0b)" : /info/i.test(level ?? "") ? "var(--t-accent)" : "var(--t-muted)"
  const inputStyle = { background: "var(--t-card)", color: "var(--t-text)", border: "1px solid var(--t-border-alpha)" }

  const renderTab = (d: DeviceRecord) => {
    if (metricTabs.includes(activeDeviceTab)) {
      if (snapshotLoading) return <GlassCard className="p-6 text-center font-mono text-xs">Loading stored metrics…</GlassCard>
      if (snapshotError)
        return <div role="alert" className="rounded-lg border p-3 font-mono text-xs" style={{ color: "var(--t-danger)", borderColor: "var(--t-danger)" }}>{snapshotError}</div>
    }
    switch (activeDeviceTab) {
      case "overview":
        return (
          <div className="space-y-4">
            <div id="windows-overview-section">
              <WindowsDeviceOverview device={d} metrics={metrics} hardware={hardware} loading={snapshotLoading || hardwareLoading} />
            </div>
            {metricCard("system", "Operating System Details", "Identity, boot, configuration and regional settings", "FETCH SYSTEM INFO",
              metrics.system?.data ? <OsDetailsBody data={metrics.system.data} /> : <EmptyState />)}
          </div>
        )
      case "cpu":
        return metricCard("cpu", "CPU", "Processor utilization and counters", "FETCH CPU",
          metrics.cpu?.data ? <CpuBody data={metrics.cpu.data} /> : <EmptyState />)
      case "memory":
        return metricCard("memory", "Memory", "Capacity, commit, paging and kernel pools", "FETCH MEMORY",
          metrics.memory?.data ? <MemoryBody data={metrics.memory.data} /> : <EmptyState />)
      case "disk":
        return metricCard("disk", "Disk", "Volume capacity and I/O performance", "FETCH DISK",
          metrics.disk?.data ? <DiskBody data={metrics.disk.data} /> : <EmptyState />)
      case "network":
        return metricCard("network", "Network Interfaces", "Adapters, addresses, link speed and traffic", "FETCH NETWORK",
          metrics.network?.data ? <NetworkBody data={metrics.network.data} /> : <EmptyState />)
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
              {hardwareLoading ? <div className="font-mono text-xs">Loading saved hardware…</div> : hardware ? <HardwareBody hardware={hardware} /> : <EmptyState text="No saved hardware data. Use FETCH HARDWARE to collect it." />}
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
                  {sensorProviders.map((p) => <Badge key={p.provider} text={`${p.provider}: ${p.status}`} color={p.status === "ok" ? "var(--t-success)" : "var(--t-muted)"} />)}
                </div>
              )}
              {sensorLoading ? <div className="font-mono text-xs">Discovering native sensors…</div> : nativeSensors.length ? <SensorsBody sensors={nativeSensors} /> : <EmptyState text="No sensor readings yet. Use DISCOVER NATIVE SENSORS." />}
            </CardShell>
          </div>
        )
      case "storage":
        return (
          <div id="windows-storage-section" className="grid grid-cols-1 items-start gap-4 lg:grid-cols-2">
            <WindowsDiskInventoryPanel
              inventory={diskInventory ?? { device_id: expandedDeviceId ?? 0, physical_disks: [], partitions: [], modern_physical_disks: [], modern_status: "unavailable", modern_error: null }}
              loading={diskInventoryLoading}
              error={diskInventoryError}
              open={diskInventoryOpen}
              onToggle={() => setDiskInventoryOpen((open) => !open)}
              onRetry={() => void loadDiskInventory(true).catch(() => undefined)}
            />
            <WindowsStorageHealth
              health={diskHealth}
              loading={diskHealthLoading}
              error={diskHealthError}
              open={diskHealthOpen}
              onToggle={() => setDiskHealthOpen((open) => !open)}
              onRetry={() => void loadDiskHealth(true).catch(() => undefined)}
            />
          </div>
        )
      case "events":
        return (
          <CardShell
            title="Windows System Event Logs"
            subtitle={systemEvents.length ? `${systemEvents.length} saved event${systemEvents.length === 1 ? "" : "s"} shown` : "No saved events"}
            error={systemEventsError}
            action={<ActionButton label="FETCH SYSTEM EVENTS" busyLabel="FETCHING…" busy={systemEventsLoading} onClick={() => void fetchSystemEvents()} />}
          >
            <div className="space-y-4">
              {systemEventsFetch && (
                <div className="font-mono text-[10px]" style={{ color: "var(--t-success)" }}>
                  FETCH COMPLETE · fetched {systemEventsFetch.fetched_count} · inserted {systemEventsFetch.inserted_count} · {fmtDateTime(systemEventsFetch.collected_at)}
                </div>
              )}
              <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
                <Tile label="Critical" value={eventSummary.critical} />
                <Tile label="Error" value={eventSummary.error} />
                <Tile label="Warning" value={eventSummary.warning} />
                <Tile label="Information" value={eventSummary.info} />
              </div>
              <div className="flex flex-wrap gap-2">
                <input aria-label="Event ID filter" value={systemEventIdFilter} onChange={(e) => { setSystemEventIdFilter(e.target.value.replace(/[^0-9]/g, "")); setSystemEventsOffset(0) }} placeholder="Event ID" className="rounded px-2 py-2 font-mono text-[10px]" style={inputStyle} />
                <select aria-label="Event level filter" value={systemEventLevelFilter} onChange={(e) => { setSystemEventLevelFilter(e.target.value); setSystemEventsOffset(0) }} className="rounded px-2 py-2 font-mono text-[10px]" style={inputStyle}>
                  <option value="">All levels</option><option>Critical</option><option>Error</option><option>Warning</option><option>Information</option>
                </select>
                <input aria-label="Event start date" type="date" value={systemEventStartFilter} onChange={(e) => { setSystemEventStartFilter(e.target.value); setSystemEventsOffset(0) }} className="rounded px-2 py-2 font-mono text-[10px]" style={inputStyle} />
                <input aria-label="Event end date" type="date" value={systemEventEndFilter} onChange={(e) => { setSystemEventEndFilter(e.target.value); setSystemEventsOffset(0) }} className="rounded px-2 py-2 font-mono text-[10px]" style={inputStyle} />
                <button type="button" onClick={() => expandedDeviceId && void loadSystemEvents(expandedDeviceId, 0)} disabled={systemEventsLoading} className="rounded px-3 py-2 font-mono text-[10px]" style={{ background: "var(--t-accent)", color: "var(--t-bg)" }}>APPLY FILTERS</button>
              </div>
              <div className="overflow-x-auto rounded-xl border" style={{ borderColor: "var(--t-border-light)" }}>
                <table className="w-full min-w-[900px] text-left">
                  <thead>
                    <tr style={{ color: "var(--t-muted)", background: "var(--t-bg)" }}>
                      {["Event Time", "Event ID", "Level", "Provider", "Computer", "Message"].map((h) => <th key={h} className="px-3 py-2 font-mono text-[10px] uppercase">{h}</th>)}
                    </tr>
                  </thead>
                  <tbody>
                    {systemEventsLoading && !systemEvents.length ? (
                      <tr><td colSpan={6} className="px-3 py-6 text-center font-mono text-xs">Loading saved events…</td></tr>
                    ) : systemEvents.length ? systemEvents.map((item) => (
                      <tr key={`${item.record_id}:${item.event_id}`} style={{ borderTop: "1px solid var(--t-border-light)" }}>
                        <td className="px-3 py-2 font-mono text-[10px]">{fmtEventTime(item.time_created)}</td>
                        <td className="px-3 py-2 font-mono text-xs">{item.event_id}</td>
                        <td className="px-3 py-2"><Badge text={item.level || NA} color={levelColor(item.level)} /></td>
                        <td className="px-3 py-2 text-xs">{item.provider || NA}</td>
                        <td className="px-3 py-2 text-xs">{item.machine_name || NA}</td>
                        <td className="max-w-[360px] px-3 py-2 text-xs">
                          <button type="button" className="text-left" onClick={() => setExpandedEventId(expandedEventId === item.record_id ? null : item.record_id)}>
                            {expandedEventId === item.record_id ? item.message || NA : (item.message || NA).length > 120 ? `${(item.message || "").slice(0, 120)}…` : item.message || NA}
                          </button>
                        </td>
                      </tr>
                    )) : (
                      <tr><td colSpan={6} className="px-3 py-6 text-center font-mono text-xs" style={{ color: "var(--t-muted)" }}>No saved events. Use FETCH SYSTEM EVENTS to collect them.</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
              <div className="flex items-center justify-between font-mono text-[10px]" style={{ color: "var(--t-muted)" }}>
                <button type="button" disabled={systemEventsOffset === 0 || systemEventsLoading} onClick={() => expandedDeviceId && void loadSystemEvents(expandedDeviceId, Math.max(0, systemEventsOffset - systemEventsLimit))}>PREVIOUS</button>
                <span>Offset {systemEventsOffset}</span>
                <button type="button" disabled={!systemEventsHasNext || systemEventsLoading} onClick={() => expandedDeviceId && void loadSystemEvents(expandedDeviceId, systemEventsOffset + systemEventsLimit)}>NEXT</button>
              </div>
            </div>
          </CardShell>
        )
    }
  }

  /* ───────────── render ───────────── */
  return (
    <div className="dashboard-page min-h-full space-y-5 rounded-2xl p-4 md:p-6 animate-fadeIn">
      <header className="rounded-2xl border p-5 md:p-7" style={{ background: "var(--t-card)", borderColor: "var(--t-border)" }}>
        <h1 className="font-display text-2xl font-bold tracking-tight md:text-4xl" style={{ color: "var(--t-text)" }}>WINDOWS DEVICES</h1>
        <div className="mt-1 flex flex-wrap items-center justify-between gap-3">
          <p className="font-mono text-xs" style={{ color: "var(--t-muted)" }}>Standalone and workgroup Windows PCs · WinRM HTTPS / NTLM</p>
          {hasPermission("devices:create") && (
            <button type="button" onClick={() => (showAdd ? reset() : (setShowAdd(true), setError("")))} className="rounded px-4 py-2 font-mono text-xs" style={{ background: "var(--t-accent)", color: "var(--t-bg)" }}>
              {showAdd ? "CANCEL" : "ADD WINDOWS DEVICE"}
            </button>
          )}
        </div>
        <div className="mt-5 flex gap-2 font-mono text-[10px] uppercase" style={{ color: "var(--t-muted)" }}>
          <span className="rounded-full border px-3 py-1" style={{ borderColor: "var(--t-border)" }}>Manual collection</span>
          <span className="rounded-full border px-3 py-1" style={{ borderColor: "var(--t-border)" }}>PostgreSQL snapshots</span>
        </div>
      </header>

      {showAdd && (
        <GlassCard className="p-5">
          <h2 className="font-display font-bold" style={{ color: "var(--t-text)" }}>ADD WINDOWS DEVICE · STEP {step} OF 3</h2>
          <div className="mt-1 font-mono text-[10px]" style={{ color: "var(--t-muted)" }}>
            {step === 1 ? "Device Details" : step === 2 ? "Windows Credentials" : "Save & Test Connection"}
          </div>

          {step === 1 && (
            <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-3">
              <label className="font-mono text-[10px] uppercase md:col-span-3" style={{ color: "var(--t-muted)" }}>
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
                  className="mt-1 w-full rounded px-3 py-2 text-sm"
                >
                  <option value="">Add a new Windows device manually</option>
                  {allDevices.map((d) => <option key={d.id} value={d.id}>{d.hostname} · {d.ip_address} · ID {d.id}</option>)}
                </select>
              </label>
              <label className="font-mono text-[10px] uppercase md:col-span-2" style={{ color: "var(--t-muted)" }}>
                Connection Host (DNS/IP)
                <input value={form.connection_host} onChange={(e) => setForm({ ...form, connection_host: e.target.value })} disabled={saving} autoComplete="off" placeholder="Defaults to inventory hostname/IP" className="mt-1 w-full rounded px-3 py-2 text-sm" />
              </label>
              <label className="font-mono text-[10px] uppercase" style={{ color: "var(--t-muted)" }}>
                Hostname
                <input value={form.hostname} onChange={(e) => !selectedDeviceId && setForm({ ...form, hostname: e.target.value })} readOnly={Boolean(selectedDeviceId)} disabled={saving} className="mt-1 w-full rounded px-3 py-2 text-sm" />
              </label>
              <label className="font-mono text-[10px] uppercase" style={{ color: "var(--t-muted)" }}>
                IP Address
                <input value={form.ip_address} onChange={(e) => !selectedDeviceId && setForm({ ...form, ip_address: e.target.value })} readOnly={Boolean(selectedDeviceId)} disabled={saving} className="mt-1 w-full rounded px-3 py-2 text-sm" />
              </label>
              <label className="font-mono text-[10px] uppercase" style={{ color: "var(--t-muted)" }}>
                Authorized Site
                <select value={form.site_id} onChange={(e) => !selectedDeviceId && setForm({ ...form, site_id: e.target.value })} disabled={saving || sitesLoading || !sites.length || Boolean(selectedDeviceId)} className="mt-1 w-full rounded px-3 py-2 text-sm">
                  <option value="">{sitesLoading ? "Loading sites…" : sites.length ? "Select site" : "No accessible sites"}</option>
                  {sites.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                </select>
              </label>
            </div>
          )}

          {step === 2 && (
            <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2">
              <label className="font-mono text-[10px] uppercase" style={{ color: "var(--t-muted)" }}>
                Username
                <input value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} disabled={saving} autoComplete="off" className="mt-1 w-full rounded px-3 py-2 text-sm" />
              </label>
              <label className="font-mono text-[10px] uppercase" style={{ color: "var(--t-muted)" }}>
                Domain / Computer Name
                <input value={form.domain} onChange={(e) => setForm({ ...form, domain: e.target.value })} disabled={saving} autoComplete="off" className="mt-1 w-full rounded px-3 py-2 text-sm" />
              </label>
              <label className="font-mono text-[10px] uppercase md:col-span-2" style={{ color: "var(--t-muted)" }}>
                Password
                <div className="mt-1 flex">
                  <input type={showPassword ? "text" : "password"} value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} disabled={saving} autoComplete="new-password" className="w-full rounded-l px-3 py-2 text-sm" />
                  <button type="button" onClick={() => setShowPassword((v) => !v)} disabled={saving} className="rounded-r px-2 font-mono text-[10px]">{showPassword ? "HIDE" : "SHOW"}</button>
                </div>
              </label>
            </div>
          )}

          {step === 3 && (
            <div className="mt-4 space-y-2 font-mono text-xs" style={{ color: "var(--t-text)" }}>
              <div>Hostname: {form.hostname}</div>
              <div>IP Address: {form.ip_address}</div>
              <div>Connection Host: {form.connection_host || "Inventory hostname/IP"}</div>
              <div>Site: {sites.find((s) => String(s.id) === form.site_id)?.name ?? "—"}</div>
              <div>Username: {form.username}</div>
              <div>Password: ********</div>
              {progressLabel && (
                <div style={{ color: progress === "connected" ? "var(--t-success)" : progress === "failed" ? "var(--t-danger)" : "var(--t-accent)" }}>{progressLabel}</div>
              )}
            </div>
          )}

          {error && (
            <div role="alert" className="mt-4 rounded p-3 font-mono text-xs" style={{ color: "var(--t-danger)", border: "1px solid var(--t-danger)" }}>
              {error}
              {duplicate && (
                <div className="mt-2">
                  <Link to={`/devices/${duplicate.id}`} className="underline" style={{ color: "var(--t-accent)" }}>
                    OPEN EXISTING DEVICE {duplicate.hostname} (ID {duplicate.id})
                  </Link>
                </div>
              )}
            </div>
          )}
          {onboardingNotice && (
            <div role="status" className="mt-4 rounded p-3 font-mono text-xs" style={{ color: "var(--t-success)", border: "1px solid var(--t-success)" }}>{onboardingNotice}</div>
          )}

          <div className="mt-4 flex flex-wrap gap-2">
            {step > 1 && <button type="button" onClick={() => setStep((step - 1) as Step)} disabled={saving} className="rounded px-4 py-2 font-mono text-xs">BACK</button>}
            {step === 1 && <button type="button" onClick={deviceStep} disabled={saving} className="rounded px-4 py-2 font-mono text-xs">CONTINUE</button>}
            {step === 2 && <button type="button" onClick={credentialStep} disabled={saving || credentialLoading} className="rounded px-4 py-2 font-mono text-xs">CONTINUE</button>}
            {step === 3 && (
              <button type="button" onClick={() => void onboard()} disabled={saving || progress === "connected"} className="rounded px-4 py-2 font-mono text-xs">
                {saving ? "PROCESSING…" : progress === "failed" ? "RETRY" : "SAVE & TEST CONNECTION"}
              </button>
            )}
          </div>
        </GlassCard>
      )}

      {!showAdd && error && (
        <div role="alert" className="rounded-lg p-3 font-mono text-xs" style={{ color: "var(--t-danger)" }}>{error}</div>
      )}

      {/* ───────────── DEVICE DETAIL VIEW ───────────── */}
      {inDetail ? (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <button type="button" onClick={() => navigate("/windows-devices")} className="font-mono text-[11px]" style={{ color: "var(--t-accent)" }}>← BACK TO WINDOWS DEVICES</button>
            {detailDevice && (
              <div className="flex flex-wrap items-center gap-2 font-mono text-[11px]" style={{ color: "var(--t-muted)" }}>
                <span style={{ color: "var(--t-text)" }}>{detailDevice.hostname}</span>
                <span>· {detailDevice.ip_address}</span>
                <span>· ID {detailDevice.id}</span>
                <Badge text={detailDevice.status || "Unknown"} color={isOnlineStatus(detailDevice.status) ? "var(--t-success)" : "var(--t-muted)"} />
                {hasPermission("devices:delete") && (
                  <button type="button" onClick={() => void removeDevice(detailDevice)} className="ml-2" style={{ color: "var(--t-danger)" }}>DELETE</button>
                )}
              </div>
            )}
          </div>

          <div className="overflow-x-auto rounded-xl border" style={{ borderColor: "var(--t-border-light)", background: "var(--t-card)" }}>
            <nav className="flex min-w-max items-center gap-1 p-1" aria-label="Windows device sections">
              {tabNames.map((tab) => (
                <button
                  key={tab}
                  type="button"
                  onClick={() => selectDeviceTab(tab)}
                  className="rounded-lg px-3 py-2 font-mono text-[10px] uppercase transition-colors"
                  style={{
                    color: activeDeviceTab === tab ? "var(--t-accent)" : "var(--t-muted)",
                    background: activeDeviceTab === tab ? "var(--t-table-row-hover)" : "transparent",
                    borderBottom: activeDeviceTab === tab ? "2px solid var(--t-accent)" : "2px solid transparent",
                  }}
                >
                  {tabLabels[tab]}
                </button>
              ))}
            </nav>
          </div>

          {loading && !detailDevice ? (
            <GlassCard className="p-6 text-center font-mono text-xs">Loading Windows device…</GlassCard>
          ) : !detailDevice ? (
            <GlassCard className="p-6 text-center font-mono text-xs">Windows device {routeDeviceId} was not found.</GlassCard>
          ) : (
            renderTab(detailDevice)
          )}
        </div>
      ) : (
        /* ───────────── DEVICE LIST VIEW ───────────── */
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
            {([["WINDOWS DEVICES", devices.length], ["ONLINE", online], ["OFFLINE / UNKNOWN", devices.length - online]] as const).map(([label, value]) => (
              <GlassCard key={label} className="p-4">
                <div className="font-mono text-[10px]" style={{ color: "var(--t-muted)" }}>{label}</div>
                <div className="mt-2 font-display text-2xl font-bold" style={{ color: "var(--t-text)" }}>{value}</div>
              </GlassCard>
            ))}
          </div>

          <GlassCard className="overflow-hidden">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b p-4" style={{ borderColor: "var(--t-border-light)" }}>
              <div>
                <div className="font-display text-lg font-bold" style={{ color: "var(--t-text)" }}>Managed Windows Devices</div>
                <div className="font-mono text-[10px] uppercase" style={{ color: "var(--t-muted)" }}>{filteredDevices.length} of {devices.length} devices</div>
              </div>
              <div className="flex flex-wrap gap-2">
                <input value={deviceQuery} onChange={(e) => setDeviceQuery(e.target.value)} placeholder="Search hostname, IP, ID" className="rounded-lg border px-3 py-2 font-mono text-xs" style={{ background: "var(--t-bg)", borderColor: "var(--t-border)", color: "var(--t-text)" }} />
                <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value as typeof statusFilter)} className="rounded-lg border px-3 py-2 font-mono text-xs" style={{ background: "var(--t-bg)", borderColor: "var(--t-border)", color: "var(--t-text)" }}>
                  <option value="all">All status</option><option value="online">Online</option><option value="offline">Offline / unknown</option>
                </select>
              </div>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[720px] text-left">
                <thead>
                  <tr style={{ borderBottom: "1px solid var(--t-border-light)" }}>
                    {["Device", "IP Address", "Site", "Status", "Action"].map((h) => (
                      <th key={h} className="px-4 py-3 font-mono text-[10px] uppercase" style={{ color: "var(--t-muted)" }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {loading ? (
                    <tr><td colSpan={5} className="p-10 text-center font-mono text-xs">Loading Windows devices…</td></tr>
                  ) : filteredDevices.length ? (
                    filteredDevices.map((d) => (
                      <tr key={d.id} style={{ borderTop: "1px solid var(--t-border-light)" }}>
                        <td className="px-4 py-3">
                          <div className="text-sm">{d.hostname}</div>
                          <div className="font-mono text-[10px]" style={{ color: "var(--t-muted)" }}>ID {d.id}</div>
                        </td>
                        <td className="px-4 py-3 font-mono text-xs">{d.ip_address}</td>
                        <td className="px-4 py-3 text-xs">{siteName(d.site_id)}</td>
                        <td className="px-4 py-3"><Badge text={d.status || "Unknown"} color={isOnlineStatus(d.status) ? "var(--t-success)" : "var(--t-muted)"} /></td>
                        <td className="px-4 py-3">
                          <button type="button" onClick={() => navigate(`/windows-devices/${d.id}`)} className="mr-3 font-mono text-xs" style={{ color: "var(--t-accent)" }}>MORE</button>
                          {hasPermission("devices:delete") && (
                            <button type="button" onClick={() => void removeDevice(d)} className="mr-3 font-mono text-xs" style={{ color: "var(--t-danger)" }}>DELETE</button>
                          )}
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr><td colSpan={5} className="p-10 text-center font-mono text-xs">No Windows devices found.</td></tr>
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