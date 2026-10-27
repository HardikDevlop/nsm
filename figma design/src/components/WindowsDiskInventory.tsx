import GlassCard from "./GlassCard"
import type { WindowsDiskInventory as Inventory } from "../lib/api"

type Props = { inventory: Inventory; loading: boolean; error: string; open: boolean; onToggle: () => void; onFetch: () => void; onRetry: () => void }
const unavailable = "Not available"
const bytes = (value: number | null | undefined) => {
  if (value == null || !Number.isFinite(value)) return unavailable
  if (value < 1024) return `${value.toFixed(0)} B`
  if (value < 1024 ** 2) return `${(value / 1024).toFixed(1)} KiB`
  if (value < 1024 ** 3) return `${(value / 1024 ** 2).toFixed(1)} MiB`
  if (value >= 1024 ** 4) return `${(value / 1024 ** 4).toFixed(1)} TiB`
  if (value >= 1024 ** 3) return `${(value / 1024 ** 3).toFixed(1)} GiB`
  return `${(value / 1024 ** 2).toFixed(1)} MiB`
}
const text = (value: unknown) => value == null || value === "" ? unavailable : String(value)
export default function WindowsDiskInventory({ inventory, loading, error, open, onToggle, onFetch, onRetry }: Props) {
  return <GlassCard className="p-4">
    <div className="flex flex-wrap items-center justify-between gap-3"><div><div className="font-display text-base font-bold" style={{ color: "var(--t-text)" }}>Physical Disk Inventory</div><div className="mt-1 text-sm" style={{ color: "var(--t-muted)" }}>Physical disks</div></div><div className="flex items-center gap-3"><span className="font-mono text-[10px]" style={{ color: "var(--t-muted)" }}>{loading ? "Loading…" : inventory.physical_disks.length ? `${inventory.physical_disks.length} disk(s)` : "Not fetched"}</span><button type="button" onClick={onFetch} disabled={loading} className="rounded px-4 py-2 font-mono text-[10px] disabled:opacity-70" style={{ background: "var(--t-accent)", color: "var(--t-bg)" }}>{loading ? "FETCHING…" : "FETCH INVENTORY"}</button><button type="button" onClick={onToggle} className="font-mono text-[10px]" style={{ color: "var(--t-accent)" }}>{open ? "CLOSE" : "OPEN INVENTORY"}</button>{error && <button type="button" onClick={onRetry} className="font-mono text-[10px]" style={{ color: "var(--t-danger)" }}>RETRY</button>}</div></div>
    {!open && <div className="mt-4 text-xs" style={{ color: "var(--t-muted)" }}>Click FETCH INVENTORY to query physical disks.</div>}
    {open && error && <div role="alert" className="mt-4 font-mono text-xs" style={{ color: "var(--t-danger)" }}>{error}</div>}
    {open && !error && loading && <div className="mt-4 font-mono text-xs">Loading disk inventory…</div>}
    {open && !error && !loading && (<>
      {inventory.physical_disks.length ? <div className="mt-4 grid grid-cols-1 gap-3">{inventory.physical_disks.map((disk) => <div key={disk.device_id || String(disk.index)} className="rounded-xl border p-4" style={{ borderColor: "var(--t-border-light)", background: "var(--t-card)" }}><div className="flex items-start justify-between gap-3"><div className="min-w-0"><div className="font-mono text-[10px] uppercase" style={{ color: "var(--t-accent)" }}>Physical disk #{text(disk.index)}</div><div className="mt-2 break-words text-sm font-semibold">{text(disk.model)}</div></div><span className="shrink-0 rounded-full border px-2 py-1 font-mono text-[10px]" style={{ borderColor: "var(--t-success)", color: "var(--t-success)" }}>{text(disk.status)}</span></div><dl className="mt-4 grid gap-3 text-xs sm:grid-cols-2 lg:grid-cols-4">{[["Capacity", bytes(disk.size_bytes)], ["Interface / bus", text(disk.interface_type)], ["Media type", text(disk.media_type)], ["Status", text(disk.status)], ["Firmware", text(disk.firmware_revision)], ["Serial", disk.serial_number ? "Hidden by default" : unavailable]].map(([label, value]) => <div key={label}><dt className="font-mono text-[10px] uppercase" style={{ color: "var(--t-muted)" }}>{label}</dt><dd className="mt-1 break-words">{value}</dd></div>)}</dl></div>)}</div> : <div className="mt-4 text-xs" style={{ color: "var(--t-muted)" }}>No physical disks reported.</div>}
    </>)}
    {open && <div className="mt-4 border-t pt-4" style={{ borderColor: "var(--t-border-light)" }}><div className="font-mono text-[10px] uppercase" style={{ color: "var(--t-muted)" }}>Modern Storage Provider</div>{inventory.modern_status === "ok" && inventory.modern_physical_disks.length ? <div className="mt-3 grid gap-3 md:grid-cols-2">{inventory.modern_physical_disks.map((disk, index) => <div key={index} className="min-w-0 rounded-lg border p-3 text-xs" style={{ borderColor: "var(--t-border-light)", background: "var(--t-card)" }}><div className="break-words font-semibold">{text(disk.FriendlyName)}</div><div className="mt-2 break-words" style={{ color: "var(--t-muted)" }}>Media: {text(disk.MediaType)} · Bus: {text(disk.BusType)}</div><div className="mt-1 break-words" style={{ color: "var(--t-muted)" }}>Health: {text(disk.HealthStatus)} · Operational: {text(disk.OperationalStatus)}</div></div>)}</div> : <div className="mt-2 break-words text-xs" style={{ color: "var(--t-muted)" }}>{inventory.modern_error || "Modern storage provider unsupported or unavailable"}</div>}</div>}
  </GlassCard>
}
