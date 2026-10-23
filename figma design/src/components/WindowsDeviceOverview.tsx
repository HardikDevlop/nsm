import GlassCard from "./GlassCard"
import type { ReactNode } from "react"
import type { DeviceRecord, WindowsHardwareSnapshot, WindowsMetricSnapshot } from "../lib/api"

type Props = {
  device: DeviceRecord
  metrics: Partial<Record<WindowsMetricSnapshot["module"], WindowsMetricSnapshot>>
  hardware: WindowsHardwareSnapshot | null
  loading: boolean
}

const unavailable = "Not available"
const value = (item: unknown) => item == null || item === "" ? unavailable : String(item)
const bytes = (item: unknown) => {
  if (typeof item !== "number" || !Number.isFinite(item)) return unavailable
  if (item >= 1024 ** 3) return `${(item / 1024 ** 3).toFixed(1)} GiB`
  return `${(item / 1024 ** 2).toFixed(1)} MiB`
}
const date = (item: unknown) => {
  if (typeof item !== "string" || !item) return unavailable
  const parsed = new Date(item)
  return Number.isNaN(parsed.getTime()) ? unavailable : parsed.toLocaleString("en-IN", { timeZone: "Asia/Kolkata" })
}
const uptime = (item: unknown) => {
  if (typeof item !== "number" || !Number.isFinite(item) || item < 0) return unavailable
  const minutes = Math.floor(item / 60)
  return `${Math.floor(minutes / 1440)}d ${Math.floor((minutes % 1440) / 60)}h ${minutes % 60}m`
}

function MetricCard({ label, icon, main, detail, progress }: { label: string; icon: string; main: string; detail: string; progress?: number | null }) {
  return <GlassCard className="p-4">
    <div className="flex items-center justify-between">
      <span className="font-mono text-[10px] uppercase tracking-wider" style={{ color: "var(--t-muted)" }}>{label}</span>
      <span aria-hidden="true" className="text-base" style={{ color: "var(--t-accent)" }}>{icon}</span>
    </div>
    <div className="mt-3 font-display text-2xl font-bold" style={{ color: "var(--t-text)" }}>{main}</div>
    <div className="mt-1 truncate font-mono text-[10px]" style={{ color: "var(--t-muted)" }}>{detail}</div>
    {progress != null && Number.isFinite(progress) && <div className="mt-3 h-1.5 overflow-hidden rounded-full" style={{ background: "var(--t-border-light)" }}><div className="h-full rounded-full" style={{ width: `${Math.max(0, Math.min(100, progress))}%`, background: "var(--t-accent)" }} /></div>}
  </GlassCard>
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return <div><dt className="font-mono text-[10px] uppercase" style={{ color: "var(--t-muted)" }}>{label}</dt><dd className="mt-1 break-words text-sm" style={{ color: "var(--t-text)" }}>{children}</dd></div>
}

export default function WindowsDeviceOverview({ device, metrics, hardware, loading }: Props) {
  const system = metrics.system?.data ?? {}
  const cpu = metrics.cpu?.data ?? {}
  const memory = metrics.memory?.data ?? {}
  const disks = Array.isArray(metrics.disk?.data) ? metrics.disk.data : []
  const network = Array.isArray(metrics.network?.data) ? metrics.network.data : []
  const online = /online|up/i.test(device.status)
  const disk = disks[0] as Record<string, unknown> | undefined
  const totalMemory = bytes(memory.total_bytes)
  const usedMemory = bytes(memory.used_bytes)
  const diskSummary = disk ? `${value(disk.usage_percent)}% used · ${bytes(disk.size_bytes)}` : unavailable
  const cpuUsage = typeof cpu.usage_percent === "number" ? cpu.usage_percent : null
  const memoryUsage = typeof memory.usage_percent === "number" ? memory.usage_percent : null
  const diskUsage = typeof disk?.usage_percent === "number" ? disk.usage_percent : null

  return <section className="space-y-4" aria-label="Windows device overview">
    <GlassCard className="p-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex flex-wrap items-center gap-3">
            <h2 className="font-display text-xl font-bold" style={{ color: "var(--t-text)" }}>{device.hostname}</h2>
            <span className="rounded-full border px-2 py-1 font-mono text-[10px] uppercase" style={{ color: online ? "var(--t-success)" : "var(--t-danger)", borderColor: online ? "var(--t-success)" : "var(--t-danger)" }}>{online ? "Online" : "Offline"}</span>
          </div>
          <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 font-mono text-xs" style={{ color: "var(--t-muted)" }}><span>{device.ip_address}</span><span>{value(system.caption || system.operating_system || "Windows")}</span><span>Device ID {device.id}</span></div>
        </div>
        <div className="text-left sm:text-right"><div className="font-mono text-[10px] uppercase" style={{ color: "var(--t-muted)" }}>Last collected</div><div className="mt-1 text-sm" style={{ color: "var(--t-text)" }}>{date(metrics.system?.collected_at || device.last_seen)}</div></div>
      </div>
    </GlassCard>

    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
      <MetricCard label="CPU usage" icon="◌" main={cpuUsage == null ? unavailable : `${cpuUsage}%`} detail={`${value(cpu.identity?.physical_cores)} physical cores`} progress={cpuUsage} />
      <MetricCard label="Memory" icon="▦" main={`${usedMemory} / ${totalMemory}`} detail={memoryUsage == null ? "Usage not available" : `${memoryUsage}% used`} progress={memoryUsage} />
      <MetricCard label="Disk capacity" icon="▤" main={disk ? bytes(disk.size_bytes) : unavailable} detail={diskSummary} progress={diskUsage} />
      <MetricCard label="Network" icon="⌁" main={network.length ? `${network.length} adapters` : unavailable} detail={network.length ? `${network.filter((item: Record<string, unknown>) => /up|connected/i.test(String(item.interface_status))).length} active interfaces` : "No saved network data"} />
    </div>

    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      <GlassCard className="p-5"><div className="font-display text-base font-bold" style={{ color: "var(--t-text)" }}>System information</div><dl className="mt-4 grid gap-4 sm:grid-cols-2">
        <Field label="Operating system">{value(system.caption)}</Field><Field label="Version / build">{value(system.version)}{system.build_number ? ` · Build ${system.build_number}` : ""}</Field><Field label="Hostname">{value(system.hostname || device.hostname)}</Field><Field label="Manufacturer">{value(system.manufacturer)}</Field><Field label="Domain">{value(system.domain || system.domain_name)}</Field><Field label="Uptime">{uptime(system.uptime_seconds)}</Field>
      </dl></GlassCard>
      <GlassCard className="p-5"><div className="font-display text-base font-bold" style={{ color: "var(--t-text)" }}>Hardware summary</div>{loading ? <div className="mt-4 font-mono text-xs" style={{ color: "var(--t-muted)" }}>Loading available hardware…</div> : <dl className="mt-4 grid gap-4 sm:grid-cols-2">
        <Field label="Processor">{value(hardware?.processors?.[0]?.name || hardware?.processors?.[0]?.caption || cpu.identity?.name)}</Field><Field label="Installed memory">{hardware?.memory_modules?.length ? `${hardware.memory_modules.length} module${hardware.memory_modules.length === 1 ? "" : "s"}` : totalMemory}</Field><Field label="Physical disks">{disks.length ? String(disks.length) : unavailable}</Field><Field label="Network adapters">{network.length ? String(network.length) : unavailable}</Field><Field label="Model">{value(hardware?.computer_system?.model || device.model)}</Field>
      </dl>}</GlassCard>
    </div>
  </section>
}
