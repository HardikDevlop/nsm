import { useEffect, useMemo, useRef, useState } from "react"
import { useAuth } from "../AuthContext"
import TablePagination from "../TablePagination"
import {
  fetchWindowsProcesses,
  getWindowsProcesses,
  getWindowsProcessHistory,
  getWindowsProcessHistoryDetail,
  type WindowsProcessHistoryDetail,
  type WindowsProcessHistorySnapshot,
  type WindowsProcessHistoryItem,
  type WindowsProcessQuery,
  type WindowsProcessRecord,
  type WindowsTaskManagerSnapshot,
} from "../../lib/api"
import {
  formatTaskManagerAge,
  formatTaskManagerMemory,
  formatTaskManagerReason,
  presentProcessCPU,
  presentTaskManagerStatus,
} from "../../lib/windowsTaskManagerDisplay"

const DEFAULT_PAGE_SIZE = 50
const MAX_PAGE_SIZE = 200
const colors = {
  text: "var(--t-text)", muted: "var(--t-muted)", accent: "var(--t-accent)",
  border: "var(--t-border-light)", card: "var(--wd-card, var(--t-card))",
  warning: "var(--t-warning, #f59e0b)", danger: "var(--t-danger)",
}

type Props = { deviceId: number }
type Sort = NonNullable<WindowsProcessQuery["sort"]>

const FRIENDLY_PROCESS_NAMES: Record<string, string> = {
  "System Idle Process": "CPU Idle Time",
  System: "Windows System",
  Registry: "Windows Registry",
  "smss.exe": "Windows Session Manager",
  "csrss.exe": "Client Server Runtime",
  "wininit.exe": "Windows Initialization",
  "winlogon.exe": "Windows Sign-in",
  "services.exe": "Windows Service Control Manager",
  "lsass.exe": "Local Security Authority",
  "svchost.exe": "Windows Service Host",
  "dwm.exe": "Desktop Window Manager",
  "spoolsv.exe": "Print Spooler",
}

const NOT_AVAILABLE = "Not available"

function localTimestamp(value: string | null | undefined): string {
  if (!value) return NOT_AVAILABLE
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? NOT_AVAILABLE : date.toLocaleString([], { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit", second: "2-digit" })
}

function historyCpu(item: WindowsProcessHistoryItem): string {
  if (item.cpu_status === "warming_up") return "Warming up"
  if (item.cpu_status !== "ok" || item.cpu_percent == null) return "Not available"
  return `${item.cpu_percent.toFixed(1)}%`
}

function HistoryView({ deviceId, colors }: { deviceId: number; colors: typeof colors }) {
  const [history, setHistory] = useState<WindowsProcessHistorySnapshot[]>([])
  const [detail, setDetail] = useState<WindowsProcessHistoryDetail | null>(null)
  const [selected, setSelected] = useState<number | null>(null)
  const [page, setPage] = useState(1)
  const [detailPage, setDetailPage] = useState(1)
  const [search, setSearch] = useState("")
  const [sort, setSort] = useState<"name" | "pid" | "cpu" | "memory" | "threads">("name")
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const pageSize = 50

  useEffect(() => {
    let active = true
    setLoading(true); setError(null)
    void getWindowsProcessHistory(deviceId, { limit: pageSize, offset: (page - 1) * pageSize }).then((result) => {
      if (active) setHistory(result.items)
    }).catch(() => { if (active) setError("Unable to load process history.") }).finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [deviceId, page])

  useEffect(() => {
    if (selected == null) return
    let active = true
    setLoading(true); setError(null)
    void getWindowsProcessHistoryDetail(deviceId, selected).then((result) => {
      if (active) { setDetail(result); setDetailPage(1) }
    }).catch(() => { if (active) setError("Unable to load snapshot details.") }).finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [deviceId, selected])

  const filtered = useMemo(() => {
    const needle = search.trim().toLowerCase()
    const items = (detail?.items ?? []).filter((item) => !needle || (item.name ?? "").toLowerCase().includes(needle) || String(item.pid ?? "").includes(needle))
    return [...items].sort((a, b) => {
      const value = sort === "name" ? (a.name ?? "").localeCompare(b.name ?? "") : sort === "pid" ? (a.pid ?? Number.MAX_SAFE_INTEGER) - (b.pid ?? Number.MAX_SAFE_INTEGER) : sort === "cpu" ? (b.cpu_percent ?? -1) - (a.cpu_percent ?? -1) : sort === "memory" ? (b.working_set_bytes ?? -1) - (a.working_set_bytes ?? -1) : (b.thread_count ?? -1) - (a.thread_count ?? -1)
      return value || (a.pid ?? 0) - (b.pid ?? 0)
    })
  }, [detail, search, sort])
  const shown = filtered.slice((detailPage - 1) * pageSize, detailPage * pageSize)
  const memory = (value: number | null) => value == null ? NOT_AVAILABLE : formatTaskManagerMemory(value).replace("Unavailable", NOT_AVAILABLE)

  return <div className="p-4">
    {error && <p role="alert" className="mb-4 rounded border p-3 font-mono text-xs" style={{ color: colors.danger, borderColor: colors.danger }}>{error}</p>}
    {loading && <p role="status" className="p-6 text-center font-mono text-xs" style={{ color: colors.muted }}>Loading history…</p>}
    {!loading && !detail && <><table className="w-full text-left"><thead><tr>{["Collection Time", "Total Processes", "Snapshot ID", ""].map((label) => <th key={label} className="px-3 py-2 font-mono text-[10px] uppercase" style={{ color: colors.muted }}>{label}</th>)}</tr></thead><tbody>{history.map((item) => <tr key={item.snapshot_id} className="border-t" style={{ borderColor: colors.border }}><td className="px-3 py-2 text-xs">{localTimestamp(item.collected_at)}</td><td className="px-3 py-2 text-xs">{item.process_count}</td><td className="px-3 py-2 font-mono text-xs">{item.snapshot_id}</td><td className="px-3 py-2"><button type="button" className="rounded border px-2 py-1 font-mono text-[10px]" onClick={() => setSelected(item.snapshot_id)} style={{ borderColor: colors.border, color: colors.accent }}>VIEW DETAILS</button></td></tr>)}</tbody></table>{history.length === 0 && <p className="p-6 text-center font-mono text-xs" style={{ color: colors.muted }}>No historical snapshots are available.</p>}<TablePagination page={page} pageCount={history.length === pageSize ? page + 1 : page} pageSize={pageSize} startItem={history.length ? (page - 1) * pageSize + 1 : 0} endItem={(page - 1) * pageSize + history.length} totalItems={(page - 1) * pageSize + history.length} onPageChange={setPage} onPageSizeChange={() => undefined} pageSizes={[50]} /></>}
    {!loading && detail && <><div className="mb-4 flex flex-wrap items-center justify-between gap-2"><button type="button" onClick={() => { setSelected(null); setDetail(null) }} className="rounded border px-3 py-2 font-mono text-[10px]" style={{ borderColor: colors.border, color: colors.accent }}>← SNAPSHOT LIST</button><span className="font-mono text-xs" style={{ color: colors.muted }}>Snapshot {detail.snapshot_id} · {localTimestamp(detail.collected_at)}</span></div><div className="mb-4 flex flex-wrap gap-2"><input aria-label="History process search" value={search} onChange={(e) => { setSearch(e.target.value); setDetailPage(1) }} placeholder="Search name or PID" className="rounded-lg border px-3 py-2 font-mono text-xs" style={{ background: colors.card, color: colors.text, borderColor: colors.border }} /><select aria-label="History sort" value={sort} onChange={(e) => setSort(e.target.value as typeof sort)} className="rounded-lg border px-3 py-2 font-mono text-xs" style={{ background: colors.card, color: colors.text, borderColor: colors.border }}><option value="name">Name</option><option value="pid">PID</option><option value="cpu">CPU</option><option value="memory">Memory</option><option value="threads">Threads</option></select></div><table className="w-full text-left"><thead><tr>{["Process Name", "PID", "CPU Usage", "Memory Usage", "Threads", "Started At"].map((label) => <th key={label} className="px-3 py-2 font-mono text-[10px] uppercase" style={{ color: colors.muted }}>{label}</th>)}</tr></thead><tbody>{shown.map((item, index) => <tr key={`${item.pid}-${index}`} className="border-t" style={{ borderColor: colors.border }}><td className="px-3 py-2 text-xs">{friendlyProcessName(item.name)}<div className="font-mono text-[10px]" style={{ color: colors.muted }}>Original: {originalProcessName(item.name)} · Parent PID: {metricText(item.parent_pid)} · {item.cpu_status !== "ok" ? `${item.cpu_status ?? "unavailable"}: ${item.cpu_reason ?? ""}` : ""}</div></td><td className="px-3 py-2 font-mono text-xs">{metricText(item.pid)}</td><td className="px-3 py-2 text-xs">{historyCpu(item)}</td><td className="px-3 py-2 text-xs">{memory(item.working_set_bytes)}<div className="font-mono text-[10px]" style={{ color: colors.muted }}>Private: {memory(item.private_memory_bytes)}</div></td><td className="px-3 py-2 font-mono text-xs">{metricText(item.thread_count)}</td><td className="px-3 py-2 text-xs">{localTimestamp(item.started_at ?? item.creation_time)}</td></tr>)}</tbody></table>{shown.length === 0 && <p className="p-6 text-center font-mono text-xs" style={{ color: colors.muted }}>No processes match this search.</p>}<TablePagination page={detailPage} pageCount={Math.max(1, Math.ceil(filtered.length / pageSize))} pageSize={pageSize} startItem={filtered.length ? (detailPage - 1) * pageSize + 1 : 0} endItem={Math.min(detailPage * pageSize, filtered.length)} totalItems={filtered.length} onPageChange={setDetailPage} onPageSizeChange={() => undefined} pageSizes={[50]} /></>}
  </div>
}

function friendlyProcessName(name: string | null): string {
  return (name && FRIENDLY_PROCESS_NAMES[name]) || name || NOT_AVAILABLE
}

function originalProcessName(name: string | null): string {
  return name || NOT_AVAILABLE
}

function metricText(value: unknown): string {
  return value == null || (typeof value === "number" && !Number.isFinite(value)) ? NOT_AVAILABLE : String(value)
}

function memoryText(value: number | null | undefined): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return NOT_AVAILABLE
  return formatTaskManagerMemory(value).replace("Unavailable", NOT_AVAILABLE)
}

function usageColor(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "var(--t-muted)"
  return value >= 75 ? "var(--t-danger, #ef4444)" : value >= 35 ? "var(--t-warning, #f59e0b)" : "var(--t-success, #22c55e)"
}

function usageBar(value: number | null | undefined, basis = 100) {
  if (value == null || !Number.isFinite(value)) return <span className="text-[10px]" style={{ color: colors.muted }}>—</span>
  return <span className="mt-1 block h-1 w-20 overflow-hidden rounded-full" style={{ background: "var(--t-border-light)" }}><span className="block h-full rounded-full" style={{ width: `${Math.min(100, Math.max(0, value / basis * 100))}%`, background: usageColor(value) }} /></span>
}

function processTimestamp(value: string | null | undefined): string {
  if (!value) return NOT_AVAILABLE
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return NOT_AVAILABLE
  const now = new Date()
  const sameDay = (left: Date, right: Date) => left.getFullYear() === right.getFullYear() && left.getMonth() === right.getMonth() && left.getDate() === right.getDate()
  const time = date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit", second: "2-digit" })
  if (sameDay(date, now)) return `Today, ${time}`
  const yesterday = new Date(now)
  yesterday.setDate(now.getDate() - 1)
  if (sameDay(date, yesterday)) return `Yesterday, ${time}`
  return `${date.toLocaleDateString([], { month: "short", day: "numeric", year: "numeric" })}, ${time}`
}

export default function WindowsProcessesPanel({ deviceId }: Props) {
  const { hasPermission } = useAuth()
  const canRefresh = hasPermission("devices:update")
  const [snapshot, setSnapshot] = useState<WindowsTaskManagerSnapshot<WindowsProcessRecord> | null>(null)
  const [name, setName] = useState("")
  const [sort, setSort] = useState<Sort | undefined>(undefined)
  const [direction, setDirection] = useState<"asc" | "desc">("asc")
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE)
  const [expanded, setExpanded] = useState<string | null>(null)
  const [view, setView] = useState<"live" | "history">("live")
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [pollingStatus, setPollingStatus] = useState<"starting" | "waiting" | "collecting" | "paused" | "error">("starting")
  const [error, setError] = useState<string | null>(null)
  const requestSeq = useRef(0)
  const mounted = useRef(true)
  const pollingInFlight = useRef(false)
  const pollTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const pidSearch = /^\d+$/.test(name.trim()) ? Number(name.trim()) : null
  const query = useMemo<WindowsProcessQuery>(() => ({
    ...(name && pidSearch == null ? { name } : {}), ...(sort ? { sort } : {}), direction,
    limit: Math.min(pageSize, MAX_PAGE_SIZE), offset: (page - 1) * pageSize,
  }), [name, pidSearch, sort, direction, page, pageSize])

  useEffect(() => {
    mounted.current = true
    return () => { mounted.current = false }
  }, [])

  useEffect(() => {
    if (view === "history") return
    let active = true
    let timer: ReturnType<typeof setTimeout> | null = null
    const schedule = () => {
      if (!active || document.hidden) { if (active) setPollingStatus("paused"); return }
      setPollingStatus("waiting")
      timer = setTimeout(() => { void poll() }, 5000)
      pollTimer.current = timer
    }
    const poll = async () => {
      if (!active || document.hidden || pollingInFlight.current) return schedule()
      pollingInFlight.current = true
      const sequence = ++requestSeq.current
      setPollingStatus("collecting")
      try {
        const result = await fetchWindowsProcesses(deviceId, query)
        if (!active || !mounted.current || sequence !== requestSeq.current) return
        if (result.status !== "ok") {
          setSnapshot((current) => current ? { ...current, status: result.status, reason: result.reason, age_seconds: result.age_seconds } : result)
          setPollingStatus("error")
        } else {
          const latest = await getWindowsProcesses(deviceId, query)
          if (active && mounted.current && sequence === requestSeq.current) { setSnapshot(latest); setError(null); setPollingStatus("waiting") }
        }
      } catch {
        if (active && mounted.current && sequence === requestSeq.current) { setError("Automatic process refresh failed. Existing snapshot data was preserved."); setPollingStatus("error") }
      } finally {
        pollingInFlight.current = false
        if (active) schedule()
      }
    }
    const onVisibility = () => {
      if (document.hidden) {
        if (timer) clearTimeout(timer)
        timer = null
        pollTimer.current = null
        setPollingStatus("paused")
      } else if (!pollingInFlight.current) {
        void poll()
      }
    }
    document.addEventListener("visibilitychange", onVisibility)
    const initialSequence = ++requestSeq.current
    setLoading(true)
    setError(null)
    void getWindowsProcesses(deviceId, query).then((next) => {
      if (active && mounted.current && initialSequence === requestSeq.current) { setSnapshot(next); setPollingStatus("waiting") }
    }).catch(() => {
      if (active && mounted.current && initialSequence === requestSeq.current) { setError("Unable to load process data."); setPollingStatus("error") }
    }).finally(() => {
      if (active && mounted.current && initialSequence === requestSeq.current) { setLoading(false); schedule() }
    })
    return () => { active = false; document.removeEventListener("visibilitychange", onVisibility); if (timer) clearTimeout(timer); if (pollTimer.current) clearTimeout(pollTimer.current); pollTimer.current = null }
  }, [deviceId, query, view])

  const refresh = async () => {
    if (!canRefresh || refreshing || pollingInFlight.current) return
    pollingInFlight.current = true
    const sequence = ++requestSeq.current
    setRefreshing(true)
    setError(null)
    try {
      const result = await fetchWindowsProcesses(deviceId, query)
      if (!mounted.current || sequence !== requestSeq.current) return
      if (result.status !== "ok") {
        setSnapshot((current) => current ? { ...current, status: result.status, reason: result.reason, age_seconds: result.age_seconds } : result)
        return
      }
      const latest = await getWindowsProcesses(deviceId, query)
      if (mounted.current && sequence === requestSeq.current) setSnapshot(latest)
    } catch {
      if (mounted.current && sequence === requestSeq.current) setError("Process refresh failed. Existing snapshot data was preserved.")
    } finally {
      pollingInFlight.current = false
      if (mounted.current && sequence === requestSeq.current) setRefreshing(false)
    }
  }

  const status = presentTaskManagerStatus(snapshot?.status)
  const rows = (snapshot?.items ?? []).filter((row) => pidSearch == null || row.pid === pidSearch)
  const pageCount = Math.max(1, Math.ceil((snapshot?.total ?? 0) / pageSize))
  const emptyMessage = snapshot?.status === "no_snapshot" ? "No process snapshot is available. Use Refresh to collect one." : name ? "No processes match this search." : "No processes are available in this snapshot."
  const cpuCandidates = rows.filter((row) => row.name !== "System Idle Process" && row.cpu_status === "ok" && typeof row.cpu_percent === "number" && Number.isFinite(row.cpu_percent))
  const memoryCandidates = rows.filter((row) => typeof row.working_set_bytes === "number" && Number.isFinite(row.working_set_bytes))
  const highestCpu = cpuCandidates.reduce<WindowsProcessRecord | null>((best, row) => !best || (row.cpu_percent ?? -1) > (best.cpu_percent ?? -1) ? row : best, null)
  const highestMemory = memoryCandidates.reduce<WindowsProcessRecord | null>((best, row) => !best || (row.working_set_bytes ?? -1) > (best.working_set_bytes ?? -1) ? row : best, null)
  const memoryBasis = memoryCandidates.reduce((max, row) => Math.max(max, row.working_set_bytes ?? 0), 0)

  const updatePageSize = (value: number) => { setPageSize(Math.min(MAX_PAGE_SIZE, value)); setPage(1) }
  const updateSearch = (value: string) => { setName(value.slice(0, 100)); setPage(1) }
  const updateSort = (value: string) => { setSort((value || undefined) as Sort | undefined); setPage(1) }

  if (view === "history") {
    return <section className="rounded-xl border" style={{ borderColor: colors.border, background: colors.card }} aria-label="Windows process history">
      <div className="flex flex-wrap items-center justify-between gap-4 border-b p-5" style={{ borderColor: colors.border }}><div><span className="rounded-md bg-blue-500/10 px-2 py-1 font-mono text-[10px] font-semibold uppercase tracking-wide" style={{ color: colors.accent }}>History</span><h2 className="mt-2 font-display text-lg font-semibold" style={{ color: colors.text }}>Windows Processes</h2><p className="mt-1 text-xs" style={{ color: colors.muted }}>Historical process monitoring</p></div><div className="flex rounded-lg border p-1" style={{ borderColor: colors.border }}><button type="button" onClick={() => setView("live")} className="rounded-md px-3 py-1.5 font-mono text-[10px]" style={{ color: colors.muted }}>LIVE</button><button type="button" className="rounded-md px-3 py-1.5 font-mono text-[10px] font-bold" style={{ background: colors.accent, color: "var(--t-bg)" }}>HISTORY</button></div></div>
      <HistoryView deviceId={deviceId} colors={colors} />
    </section>
  }

  return (
    <section className="rounded-xl border" style={{ borderColor: colors.border, background: colors.card }} aria-label="Windows processes">
      <div className="flex flex-wrap items-center justify-between gap-4 border-b p-5" style={{ borderColor: colors.border }}>
        <div><div className="flex items-center gap-2"><span className="rounded-md bg-emerald-500/10 px-2 py-1 text-[10px] font-bold uppercase tracking-wider text-emerald-500">Live monitoring</span><span className="h-2 w-2 rounded-full bg-emerald-500" aria-label="Live" /></div><h2 className="mt-2 font-display text-lg font-bold" style={{ color: colors.text }}>Windows Processes</h2><p className="mt-1 text-xs" style={{ color: colors.muted }}>Real-time process monitoring and historical performance.</p></div>
        <div className="flex flex-wrap items-center justify-end gap-2"><div className="hidden text-right lg:block"><div className="font-mono text-[10px]" style={{ color: colors.muted }}>Auto Refresh: 5s · Last Updated</div><div className="font-mono text-[10px]" style={{ color: pollingStatus === "error" ? colors.danger : colors.muted }}>{pollingStatus === "collecting" ? "◌ Collecting" : pollingStatus === "paused" ? "Paused" : pollingStatus === "error" ? "Connection issue" : `● Live${snapshot?.collected_at ? ` · ${processTimestamp(snapshot.collected_at)}` : ""}`}</div></div><div className="flex rounded-lg border p-1" style={{ borderColor: colors.border }}><button type="button" onClick={() => setView("live")} className="rounded-md px-3 py-1.5 font-mono text-[10px] font-bold" style={{ background: colors.accent, color: "var(--t-bg)" }}>LIVE</button><button type="button" onClick={() => setView("history")} className="rounded-md px-3 py-1.5 font-mono text-[10px]" style={{ color: colors.muted }}>HISTORY</button></div><button aria-label="Refresh live processes" type="button" onClick={() => void refresh()} disabled={!canRefresh || refreshing} className="rounded-lg px-3 py-2 font-mono text-[10px] font-bold shadow-sm transition-opacity hover:opacity-90 disabled:opacity-50" style={{ background: colors.accent, color: "var(--t-bg)" }}>{refreshing ? "REFRESHING…" : "↻ REFRESH"}</button></div>
      </div>
      <div className="flex flex-wrap items-center gap-2 border-b p-4" style={{ borderColor: colors.border }}>
        <label className="flex items-center gap-2 rounded-lg border px-3 py-2" style={{ borderColor: colors.border, background: colors.card }}><span aria-hidden="true" style={{ color: colors.muted }}>⌕</span><input value={name} maxLength={100} onChange={(event) => updateSearch(event.target.value)} placeholder="Search process name or PID" className="min-w-[190px] bg-transparent font-mono text-xs outline-none" style={{ color: colors.text }} /></label>
        <select aria-label="Process sort" value={sort ?? ""} onChange={(event) => updateSort(event.target.value)} className="rounded-lg border px-3 py-2 font-mono text-xs" style={{ background: colors.card, color: colors.text, borderColor: colors.border }}><option value="">Default order</option><option value="cpu">CPU</option><option value="memory">Memory</option><option value="name">Name</option><option value="pid">PID</option></select>
        <select aria-label="Sort direction" value={direction} onChange={(event) => { setDirection(event.target.value as "asc" | "desc"); setPage(1) }} className="rounded-lg border px-3 py-2 font-mono text-xs" style={{ background: colors.card, color: colors.text, borderColor: colors.border }}><option value="asc">Ascending</option><option value="desc">Descending</option></select>
        {name && <button type="button" aria-label="Clear process search" onClick={() => updateSearch("")} className="rounded-lg px-2 py-2 font-mono text-xs" style={{ color: colors.muted }}>Clear</button>}<span className="ml-auto font-mono text-[10px]" style={{ color: colors.muted }}>{rows.length} shown · {snapshot?.total ?? 0} total</span>
      </div>
      {!canRefresh && <p className="border-b px-4 py-2 font-mono text-[10px]" style={{ color: colors.muted, borderColor: colors.border }}>Live refresh requires device update permission.</p>}
      {snapshot && snapshot.status !== "ok" && <div role="status" className="border-b px-4 py-3 font-mono text-xs" style={{ color: status.severity === "danger" ? colors.danger : colors.warning, borderColor: colors.border }}>{status.label}{formatTaskManagerReason(snapshot.reason)}: {status.explanation}{snapshot.age_seconds > 0 && ` · ${formatTaskManagerAge(snapshot.age_seconds)}`}</div>}
      {snapshot && rows.length > 0 && <div className="grid gap-3 border-b p-4 sm:grid-cols-2 xl:grid-cols-4" style={{ borderColor: colors.border }}>
        {[{ label: "Total Running Processes", icon: "▦", value: String(snapshot.total), sub: "Current snapshot" }, { label: "Highest CPU Process", icon: "⌁", value: highestCpu ? friendlyProcessName(highestCpu.name) : NOT_AVAILABLE, sub: highestCpu ? `${presentProcessCPU(highestCpu.cpu_status, highestCpu.cpu_percent).text} CPU` : "No available CPU data", bar: highestCpu?.cpu_percent, basis: 100 }, { label: "Highest Memory Process", icon: "▤", value: highestMemory ? friendlyProcessName(highestMemory.name) : NOT_AVAILABLE, sub: highestMemory ? `${memoryText(highestMemory.working_set_bytes)} · relative to snapshot` : "No memory data", bar: highestMemory?.working_set_bytes, basis: memoryBasis }, { label: "Last Successful Collection", icon: "◷", value: snapshot.collected_at ? processTimestamp(snapshot.collected_at) : NOT_AVAILABLE, sub: snapshot.status === "ok" ? "Collection healthy" : status.label }].map((card) => <div key={card.label} className="min-h-[104px] rounded-xl border p-4 shadow-sm" style={{ borderColor: colors.border, background: "color-mix(in srgb, var(--t-card) 72%, transparent)" }}><div className="flex items-center justify-between"><div className="font-mono text-[10px] uppercase tracking-wider" style={{ color: colors.muted }}>{card.label}</div><span className="text-base" style={{ color: colors.accent }}>{card.icon}</span></div><div className="mt-2 truncate text-sm font-semibold" style={{ color: colors.text }}>{card.value}</div><div className="mt-1 text-[10px]" style={{ color: colors.muted }}>{card.sub}</div>{card.bar !== undefined && usageBar(card.bar, card.basis)}</div>)}
      </div>}
      {error && <p role="alert" className="m-4 rounded border p-3 font-mono text-xs" style={{ color: colors.danger, borderColor: colors.danger }}>{error}</p>}
      {loading ? <p role="status" className="p-6 text-center font-mono text-xs" style={{ color: colors.muted }}>Loading processes…</p> : rows.length === 0 ? <p className="p-6 text-center font-mono text-xs" style={{ color: colors.muted }}>{emptyMessage}</p> : (
        <div className="max-h-[620px] overflow-auto"><table className="w-full min-w-[980px] text-left"><thead className="sticky top-0 z-10"><tr style={{ background: "var(--wd-table-header, var(--t-table-header))" }}>{["Process Name", "Process ID", "CPU Usage", "Memory Usage", "Threads", "Started At"].map((label) => <th key={label} className="px-3 py-3 font-mono text-[10px] uppercase tracking-wider" style={{ color: colors.muted }}>{label}</th>)}</tr></thead><tbody>{rows.map((row, index) => { const cpu = presentProcessCPU(row.cpu_status, row.cpu_percent); const key = `${row.pid ?? "terminated"}-${index}`; const isExpanded = expanded === key; return <><tr key={key} className="border-t transition-colors hover:bg-black/5" style={{ borderColor: colors.border }}><td className="px-3 py-3 text-xs" style={{ color: colors.text }}><button type="button" className="mr-2 rounded p-1 font-mono focus:outline-none focus:ring-2" aria-label={`${isExpanded ? "Hide" : "Show"} details for ${originalProcessName(row.name)}`} onClick={() => setExpanded(isExpanded ? null : key)}>{isExpanded ? "▾" : "▸"}</button><span className="font-semibold">{friendlyProcessName(row.name)}</span><div className="ml-8 font-mono text-[10px]" style={{ color: colors.muted }}>Original: {originalProcessName(row.name)}</div></td><td className="px-3 py-3 font-mono text-xs text-right">{metricText(row.pid)}</td><td className="px-3 py-3 text-xs" style={{ color: cpu.severity === "success" ? colors.text : colors.muted }}><div>{cpu.text === "Unavailable" ? NOT_AVAILABLE : cpu.text}</div>{cpu.status === "ok" && usageBar(row.cpu_percent)}</td><td className="px-3 py-3 text-xs"><div>{memoryText(row.working_set_bytes)}</div>{typeof row.working_set_bytes === "number" && usageBar(row.working_set_bytes, memoryBasis)}</td><td className="px-3 py-3 font-mono text-xs text-right">{metricText(row.thread_count)}</td><td className="px-3 py-3 text-xs">{processTimestamp(row.creation_time)}</td></tr>{isExpanded && <tr key={`${key}-details`}><td colSpan={6} className="bg-black/5 px-10 py-4 text-xs" style={{ color: colors.muted }}><div className="grid gap-2 sm:grid-cols-2"><span>Parent Process ID: {metricText(row.parent_pid)}</span><span>CPU Status: {row.cpu_status}{row.cpu_reason ? ` · ${row.cpu_reason}` : ""}</span><span>Working Set: {memoryText(row.working_set_bytes)}</span><span>Private Memory: {memoryText(row.private_memory_bytes)}</span><span>Threads: {metricText(row.thread_count)}</span><span>Process Creation: {processTimestamp(row.creation_time)}</span></div></td></tr>}</> })}</tbody></table></div>
      )}
      {snapshot && snapshot.total > 0 && <TablePagination page={page} pageCount={pageCount} pageSize={pageSize} startItem={Math.min((page - 1) * pageSize + 1, snapshot.total)} endItem={Math.min(page * pageSize, snapshot.total)} totalItems={snapshot.total} onPageChange={setPage} onPageSizeChange={updatePageSize} pageSizes={[50, 100, 200]} />}
    </section>
  )
}
