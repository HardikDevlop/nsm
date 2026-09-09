import { useEffect, useMemo, useState } from "react"
import { useNavigate } from "react-router"
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
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

const C = {
  cyan: "#00d4ff",
  green: "#00ff88",
  red: "#ff3366",
  amber: "#ffaa00",
  muted: "var(--t-muted, #8899bb)",
}
const fmt = (n: number | null | undefined, suffix = "") =>
  n == null || Number.isNaN(n) ? "N/A" : `${n.toFixed(n < 10 ? 1 : 0)}${suffix}`
const formatTraffic = (n: number | null | undefined) => {
  if (n == null || !Number.isFinite(Number(n))) return "N/A"
  const mbps = Number(n)
  const absolute = Math.abs(mbps)
  if (absolute >= 1000) return `${(mbps / 1000).toFixed(2)} Gbps`
  if (absolute >= 1) return `${mbps.toFixed(2)} Mbps`
  return `${(mbps * 1000).toFixed(2)} Kbps`
}
const clock = (s?: string | null) =>
  s
    ? new Date(s).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
    : "N/A"

function Badge({
  label,
  tone = "cyan",
}: {
  label: string
  tone?: "cyan" | "green" | "red" | "amber"
}) {
  const color = C[tone]
  return (
    <span
      className="font-mono text-[10px] uppercase px-2 py-1 rounded"
      style={{
        color,
        background: `${color}14`,
        border: `1px solid ${color}45`,
      }}
    >
      {label}
    </span>
  )
}
function Empty({ text = "No stored data available" }: { text?: string }) {
  return (
    <div
      className="font-mono text-xs py-8 text-center"
      style={{ color: C.muted }}
    >
      {text}
    </div>
  )
}
function Metric({
  label,
  number,
  hint,
  tone = "cyan",
  onClick,
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
      className="p-4"
      onClick={onClick}
      role={onClick ? "button" : undefined}
      tabIndex={onClick ? 0 : undefined}
    >
      <div
        className="flex justify-between font-mono text-[10px] uppercase tracking-widest"
        style={{ color: C.muted }}
      >
        <span>{label}</span>
        <i
          className="status-dot"
          style={{ background: color, boxShadow: `0 0 8px ${color}` }}
        />
      </div>
      <div className="font-display text-3xl mt-3" style={{ color }}>
        {number}
      </div>
      <div className="font-mono text-[10px] mt-1" style={{ color: C.muted }}>
        {hint}
      </div>
    </GlassCard>
  )
}
function Panel({
  title,
  subtitle,
  children,
  onClick,
}: {
  title: string
  subtitle?: string
  children: React.ReactNode
  onClick?: () => void
}) {
  return (
    <GlassCard
      className="p-4 md:p-5"
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
            <p
              className="font-mono text-[10px] mt-1"
              style={{ color: C.muted }}
            >
              {subtitle}
            </p>
          )}
        </div>
        {onClick && (
          <span className="font-mono text-[10px]" style={{ color: C.cyan }}>
            OPEN →
          </span>
        )}
      </div>
      {children}
    </GlassCard>
  )
}
function BarLine({
  label,
  current,
  total,
  tone = C.green,
}: {
  label: string
  current: number
  total: number
  tone?: string
}) {
  return (
    <div>
      <div
        className="flex justify-between font-mono text-xs mb-1"
        style={{ color: C.muted }}
      >
        <span>{label}</span>
        <span style={{ color: tone }}>
          {current}/{total}
        </span>
      </div>
      <div
        className="h-2 rounded-full overflow-hidden"
        style={{ background: "rgba(255,255,255,.07)" }}
      >
        <div
          className="h-full rounded-full"
          style={{
            width: `${total ? Math.min(100, (current / total) * 100) : 0}%`,
            background: tone,
          }}
        />
      </div>
    </div>
  )
}
function Mini({
  label,
  number,
  tone = C.cyan,
}: {
  label: string
  number: string | number
  tone?: string
}) {
  return (
    <div
      className="rounded-lg p-3"
      style={{ background: "rgba(0,212,255,.04)" }}
    >
      <div className="font-mono text-[10px]" style={{ color: C.muted }}>
        {label}
      </div>
      <div className="font-display text-2xl" style={{ color: tone }}>
        {number}
      </div>
    </div>
  )
}

export default function Dashboard() {
  const navigate = useNavigate()
  const { t } = useI18n()
  const d = t.dashboard
  const [data, setData] = useState<OverviewResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [range, setRange] = useState("24H")
  const [updated, setUpdated] = useState<Date | null>(null)
  const load = async (quiet = false) => {
    if (!quiet) setLoading(true)
    try {
      setError(null)
      const hours =
        range === "1H" ? 1 : range === "6H" ? 6 : range === "7D" ? 168 : 24
      setData(await getOverview(hours))
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
  const devices = data?.devices ?? []
  const summary = data?.summary
  const snmpEnabled = devices.filter((d) => Boolean(d.snmp_version)).length
  const health = {
    online: summary?.online_devices ?? 0,
    offline: summary?.offline_devices ?? 0,
    warning: summary?.warning_devices ?? 0,
    unknown: Math.max(
      0,
      (summary?.total_devices ?? 0) -
        (summary?.online_devices ?? 0) -
        (summary?.offline_devices ?? 0) -
        (summary?.warning_devices ?? 0),
    ),
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
  const chart = useMemo(() => {
    const buckets = new Map<number, { timestamp: string; rx_mbps: number; tx_mbps: number }>()

    for (const sample of n?.traffic_history ?? []) {
      if (!sample.timestamp) continue
      const timestamp = new Date(sample.timestamp).getTime()
      if (!Number.isFinite(timestamp)) continue

      const rx = sample.rx_mbps == null ? null : Number(sample.rx_mbps)
      const tx = sample.tx_mbps == null ? null : Number(sample.tx_mbps)
      // Ignore the initial counter sample, which has no calculated rate yet.
      if (rx == null && tx == null) continue

      // One poll creates a row per interface. Aggregate the rows into a
      // one-minute point so the chart represents total network traffic.
      const bucketTimestamp = Math.floor(timestamp / 60_000) * 60_000
      const current = buckets.get(bucketTimestamp) ?? {
        timestamp: new Date(bucketTimestamp).toISOString(),
        rx_mbps: 0,
        tx_mbps: 0,
      }
      if (Number.isFinite(rx)) current.rx_mbps += rx as number
      if (Number.isFinite(tx)) current.tx_mbps += tx as number
      buckets.set(bucketTimestamp, current)
    }

    return [...buckets.values()]
      .sort((a, b) => a.timestamp.localeCompare(b.timestamp))
      .map((point) => ({ ...point, label: clock(point.timestamp) }))
  }, [n?.traffic_history])
  return (
    <div
      className="p-4 md:p-6 space-y-5"
      style={{
        background:
          "radial-gradient(circle at 85% 0%, rgba(0,212,255,.08), transparent 34%)",
      }}
    >
      <div className="flex flex-col lg:flex-row lg:items-end justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="font-display font-bold text-2xl md:text-3xl tracking-widest neon-cyan">
              {d.title}
            </h1>
            <Badge label={d.live} tone="green" />
          </div>
          <p className="font-mono text-xs mt-1" style={{ color: C.muted }}>
            {d.subtitle}{" "}{updated?.toLocaleTimeString() ?? d.na}
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
            {["1H", "6H", "24H", "7D"].map((x) => (
              <button
                key={x}
                onClick={() => setRange(x)}
                className="font-mono text-[10px] px-3 py-2 rounded"
                style={{
                  color: range === x ? "#000" : C.muted,
                  background: range === x ? C.cyan : "transparent",
                }}
              >
                {x}
              </button>
            ))}
          </div>
          <button
            onClick={() => void load()}
            disabled={loading}
            className="font-mono text-xs px-3 py-2 rounded glass-bright"
            style={{ color: C.cyan, border: `1px solid ${C.cyan}40` }}
          >
            {loading ? d.loading : d.refresh}
          </button>
        </div>
      </div>
      {error && (
        <div
          className="font-mono text-xs rounded-lg p-3"
          style={{
            color: C.red,
            background: `${C.red}12`,
            border: `1px solid ${C.red}40`,
          }}
        >
          {error}
        </div>
      )}
      {loading && !data ? (
        <div
          className="glass rounded-xl p-12 text-center font-mono text-sm"
          style={{ color: C.cyan }}
        >
          {d.loadingStored}
        </div>
      ) : (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-8 gap-3">
            <Metric
              label={d.totalDevices}
              number={summary?.total_devices ?? d.na}
              hint={d.inventory}
              onClick={() => navigate("/device-monitoring")}
            />
            <Metric
              label={d.online}
              number={summary?.online_devices ?? d.na}
              hint={d.reachable}
              tone="green"
              onClick={() => navigate("/device-monitoring")}
            />
            <Metric
              label={d.offline}
              number={summary?.offline_devices ?? d.na}
              hint={d.unreachable}
              tone="red"
              onClick={() => navigate("/device-monitoring")}
            />
            <Metric
              label={d.snmpEnabled}
              number={snmpEnabled}
              hint={d.credentialsConfigured}
              tone="green"
              onClick={() => navigate("/snmp/devices")}
            />
            <Metric
              label={d.snmpFailed}
              number={n?.polling.failure ?? d.na}
              hint={d.last24Hours}
              tone="red"
              onClick={() => navigate("/monitoring-jobs")}
            />
            <Metric
              label={d.criticalAlerts}
              number={summary?.critical_alerts ?? d.na}
              hint={d.openAcknowledged}
              tone="red"
              onClick={() => navigate("/alerts")}
            />
            <Metric
              label={d.warningAlerts}
              number={
                (n?.alerts_by_severity.warning ?? 0) +
                (n?.alerts_by_severity.medium ?? 0)
              }
              hint={d.openAcknowledged}
              tone="amber"
              onClick={() => navigate("/alerts")}
            />
            <Metric
              label={d.interfacesDown}
              number={n?.interface_summary.down ?? d.na}
              hint={d.latestSnmpState}
              tone="red"
              onClick={() => navigate("/interfaces")}
            />
          </div>
          <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
            <Panel
              title={d.deviceHealth}
              subtitle={d.persistedIcmpStatus}
              onClick={() => navigate("/device-monitoring")}
            >
              <div className="grid grid-cols-2 gap-3 mb-4">
                <div className="text-center">
                  <div className="font-display text-4xl neon-green">
                    {summary?.total_devices
                      ? `${((summary.online_devices / summary.total_devices) * 100).toFixed(1)}%`
                      : "N/A"}
                  </div>
                  <div
                    className="font-mono text-[10px]"
                    style={{ color: C.muted }}
                  >
                    {d.availability}
                  </div>
                </div>
                <div className="space-y-2">
                  <BarLine
                    label={d.online}
                    current={health.online}
                    total={summary?.total_devices ?? 0}
                  />
                  <BarLine
                    label={d.offline}
                    current={health.offline}
                    total={summary?.total_devices ?? 0}
                    tone={C.red}
                  />
                </div>
              </div>
              <div className="grid grid-cols-4 gap-2">
                {Object.entries(health).map(([key, val]) => (
                  <div
                    key={key}
                    className="text-center rounded-lg p-2"
                    style={{ background: "rgba(0,212,255,.04)" }}
                  >
                    <div
                      className="font-display text-lg"
                      style={{
                        color:
                          key === "offline"
                            ? C.red
                            : key === "warning"
                              ? C.amber
                              : C.green,
                      }}
                    >
                      {val}
                    </div>
                    <div
                      className="font-mono text-[9px] uppercase"
                      style={{ color: C.muted }}
                    >
                      {d.health[key as keyof typeof d.health]}
                    </div>
                  </div>
                ))}
              </div>
              <div
                className="font-mono text-[10px] mt-4"
                style={{ color: C.muted }}
              >
                {d.lastSuccessfulPoll} {clock(n?.polling.last_success)}
              </div>
            </Panel>
            <Panel
              title={d.performance}
              subtitle={d.latestNormalizedReadings}
              onClick={() => navigate("/snmp/dashboard")}
            >
              <div className="grid grid-cols-2 gap-3 mb-4">
                {([
                  "CPU",
                  "MEMORY",
                  "STORAGE",
                  "TEMPERATURE",
                  "UPTIME",
                  "LOAD",
                ] as const).map((label) => {
                  const values =
                    label === "CPU"
                      ? perf
                          .map((x) => x.cpu)
                          .filter((x): x is number => x != null)
                      : label === "MEMORY"
                        ? perf
                            .map((x) => x.memory)
                            .filter((x): x is number => x != null)
                        : []
                  return (
                    <div
                      key={label}
                      className="rounded-lg p-3"
                      style={{
                        background: "rgba(0,212,255,.04)",
                        border: "1px solid rgba(0,212,255,.09)",
                      }}
                    >
                      <div
                        className="font-mono text-[10px]"
                        style={{ color: C.muted }}
                      >
                        {d[label.toLowerCase() as keyof typeof d]}
                      </div>
                      <div className="font-display text-lg mt-1 neon-cyan">
                        {values.length
                          ? fmt(
                              values.reduce((a, b) => a + b, 0) / values.length,
                              "%",
                            )
                          : d.na}
                      </div>
                    </div>
                  )
                })}
              </div>
              <div className="font-mono text-[10px]" style={{ color: C.muted }}>
                {d.unsupportedReading}
              </div>
            </Panel>
            <Panel
              title={d.snmpMonitoring}
              subtitle={d.pollOutcomes}
              onClick={() => navigate("/monitoring-jobs")}
            >
              <div className="space-y-3">
                <BarLine
                  label={d.successfulPolls}
                  current={n?.polling.success ?? 0}
                  total={(n?.polling.success ?? 0) + (n?.polling.failure ?? 0)}
                />
                <BarLine
                  label={d.failedPolls}
                  current={n?.polling.failure ?? 0}
                  total={(n?.polling.success ?? 0) + (n?.polling.failure ?? 0)}
                  tone={C.red}
                />
                <div className="grid grid-cols-2 gap-3 pt-2">
                  <div>
                    <div
                      className="font-mono text-[10px]"
                      style={{ color: C.muted }}
                    >
                      {d.activeJobs}
                    </div>
                    <div className="font-display text-xl neon-cyan">
                      {n?.polling.active_jobs ?? d.na}
                    </div>
                  </div>
                  <div>
                    <div
                      className="font-mono text-[10px]"
                      style={{ color: C.muted }}
                    >
                      {d.unsupportedOids}
                    </div>
                    <div
                      className="font-display text-xl"
                      style={{ color: C.amber }}
                    >
                      {n?.polling.unsupported_oids ?? d.na}
                    </div>
                  </div>
                </div>
                <div
                  className="font-mono text-[10px]"
                  style={{ color: C.muted }}
                >
                  {d.lastSuccess} {clock(n?.polling.last_success)} · {d.lastFailure}{" "}
                  {clock(n?.polling.last_failure)}
                </div>
              </div>
            </Panel>
          </div>
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
            <Panel
              title={d.networkTraffic}
              subtitle={`${d.storedInterfaceSamples} · ${range}`}
              onClick={() => navigate("/interfaces")}
            >
              <div className="flex gap-6 mb-3">
                <div>
                  <div
                    className="font-mono text-[10px]"
                    style={{ color: C.muted }}
                  >
                    {d.rxTraffic}
                  </div>
                  <div className="font-display text-2xl neon-green">
                    {formatTraffic(n?.traffic.rx_mbps)}
                  </div>
                </div>
                <div>
                  <div
                    className="font-mono text-[10px]"
                    style={{ color: C.muted }}
                  >
                    {d.txTraffic}
                  </div>
                  <div className="font-display text-2xl neon-cyan">
                    {formatTraffic(n?.traffic.tx_mbps)}
                  </div>
                </div>
              </div>
              {chart.length ? (
                <ResponsiveContainer width="100%" height={190}>
                  <AreaChart data={chart}>
                    <CartesianGrid
                      stroke="rgba(255,255,255,.08)"
                      vertical={false}
                    />
                    <XAxis
                      dataKey="label"
                      tick={{ fill: C.muted, fontSize: 10 }}
                    />
                    <YAxis tick={{ fill: C.muted, fontSize: 10 }} />
                    <Tooltip
                      formatter={(value, name) => [
                        formatTraffic(Number(value)),
                        name,
                      ]}
                    />
                    <Area
                      type="monotone"
                      dataKey="rx_mbps"
                      stroke={C.green}
                      fill={`${C.green}22`}
                      name="RX Traffic"
                    />
                    <Area
                      type="monotone"
                      dataKey="tx_mbps"
                      stroke={C.cyan}
                      fill="transparent"
                      name="TX Traffic"
                    />
                  </AreaChart>
                </ResponsiveContainer>
              ) : (
                <Empty text={d.noInterfaceHistory} />
              )}
            </Panel>
            <Panel
              title={d.topDevicesByTraffic}
              subtitle={d.latestInterfaceTotals}
            >
              <div className="space-y-3">
                {n?.traffic.top_devices?.length ? (
                  n.traffic.top_devices.map((item) => (
                    <div
                      key={item.device_id}
                      className="flex justify-between font-mono text-xs"
                    >
                      <span style={{ color: "var(--t-text, #c8d8ee)" }}>
                        {item.device_name || `Device ${item.device_id}`}
                      </span>
                      <span style={{ color: C.cyan }}>
                        {(item.rx_mbps + item.tx_mbps).toFixed(2)} Mbps
                      </span>
                    </div>
                  ))
                ) : (
                  <Empty text={d.noStoredData} />
                )}
              </div>
            </Panel>
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            <Panel
              title={d.interfaces}
              subtitle={d.latestSnmpState}
              onClick={() => navigate("/interfaces")}
            >
              <div className="grid grid-cols-3 gap-2 mb-4">
                <Mini
                  label={d.total}
                  number={n?.interface_summary.total ?? d.na}
                />
                <Mini
                  label={d.up}
                  number={n?.interface_summary.up ?? d.na}
                  tone={C.green}
                />
                <Mini
                  label={d.down}
                  number={n?.interface_summary.down ?? d.na}
                  tone={C.red}
                />
              </div>
              <div
                className="grid grid-cols-2 gap-3 font-mono text-xs"
                style={{ color: C.muted }}
              >
                {" "}
                <span>
                  {d.errors}{" "}
                  <b style={{ color: C.red }}>
                    {n?.interface_summary.errors ?? d.na}
                  </b>
                </span>
                <span>
                  {d.drops}{" "}
                  <b style={{ color: C.amber }}>
                    {n?.interface_summary.drops ?? d.na}
                  </b>
                </span>
              </div>
            </Panel>
            <Panel
              title={d.alerts}
              subtitle={d.activeAlertSeverity}
              onClick={() => navigate("/alerts")}
            >
              <div className="space-y-2">
                {["critical", "high", "medium", "warning", "low", "info"].map(
                  (sev) => (
                    <div
                      key={sev}
                      className="flex justify-between font-mono text-xs"
                    >
                      <span className="capitalize" style={{ color: C.muted }}>
                        {d.severity[sev as keyof typeof d.severity]}
                      </span>
                      <span
                        style={{
                          color:
                            sev === "critical"
                              ? C.red
                              : sev === "warning" || sev === "medium"
                                ? C.amber
                                : C.cyan,
                        }}
                      >
                        {n?.alerts_by_severity[sev] ?? 0}
                      </span>
                    </div>
                  ),
                )}
              </div>
            </Panel>
            <Panel
              title={d.networkInformation}
              subtitle={d.normalizedTopologyInventory}
              onClick={() => navigate("/topology")}
            >
              <div className="grid grid-cols-2 gap-3">
                {Object.entries({
                  [d.lldpCdpNeighbors]: n?.network.lldp_neighbors,
                  [d.vlans]: n?.network.vlan_count,
                  [d.routes]: n?.network.routing_entries,
                  [d.arp]: n?.network.arp_entries,
                  [d.mac]: n?.network.mac_entries,
                  [d.topologyNodes]: n?.network.topology_nodes,
                }).map(([label, metric]) => (
                  <div key={label}>
                    <div
                      className="font-mono text-[10px]"
                      style={{ color: C.muted }}
                    >
                      {label}
                    </div>
                    <div className="font-display text-lg neon-cyan">
                      {metric == null ? d.na : metric}
                    </div>
                  </div>
                ))}
              </div>
            </Panel>
          </div>
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
            <Panel title={d.deviceTypes} subtitle={d.inventoryClassification}>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                {Object.entries(n?.device_types ?? {}).length ? (
                  Object.entries(n?.device_types ?? {}).map(
                    ([label, count]) => (
                      <div
                        key={label}
                        className="rounded-lg p-3"
                        style={{ background: "rgba(0,212,255,.04)" }}
                      >
                        <div
                          className="font-display text-sm"
                          style={{ color: "var(--t-text, #c8d8ee)" }}
                        >
                          {label}
                        </div>
                        <div className="font-display text-2xl neon-cyan">
                          {count}
                        </div>
                      </div>
                    ),
                  )
                ) : (
                  <Empty text={d.noDeviceTypes} />
                )}
              </div>
            </Panel>
            <Panel
              title={d.recentDevicesActivity}
              subtitle={d.lastPersistedState}
              onClick={() => navigate("/device-monitoring")}
            >
              <div className="overflow-x-auto">
                <table className="w-full text-left">
                  <thead>
                    <tr
                      className="font-mono text-[10px] uppercase"
                      style={{ color: C.muted }}
                    >
                      {[d.device, d.ip, d.type, d.status, d.lastPoll].map(
                        (h) => (
                          <th key={h} className="pb-2 pr-3">
                            {h}
                          </th>
                        ),
                      )}
                    </tr>
                  </thead>
                  <tbody>
                    {devices.slice(0, 8).map((d) => (
                      <tr
                        key={d.id}
                        className="font-mono text-xs"
                        style={{ borderTop: "1px solid rgba(255,255,255,.06)" }}
                      >
                        <td className="py-2 pr-3" style={{ color: "var(--t-text, #c8d8ee)" }}>
                          {d.hostname}
                        </td>
                        <td className="py-2 pr-3" style={{ color: C.muted }}>
                          {d.ip_address}
                        </td>
                        <td className="py-2 pr-3" style={{ color: C.muted }}>
                          {d.device_type || d.na}
                        </td>
                        <td className="py-2 pr-3">
                          <Badge
                            label={d.status}
                            tone={
                              d.status === "online"
                                ? "green"
                                : d.status === "offline"
                                  ? "red"
                                  : "amber"
                            }
                          />
                        </td>
                        <td className="py-2" style={{ color: C.muted }}>
                          {clock(
                            n?.devices[String(d.id)]?.last_poll?.timestamp ??
                              d.last_seen,
                          )}
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
    </div>
  )
}
