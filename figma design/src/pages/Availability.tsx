import { useMemo, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import GlassCard from "../components/GlassCard"
import { useAuth } from "../components/AuthContext"
import {
  createAvailabilityReport,
  getAvailabilityReport,
  listAvailabilityReports,
  listDeviceOptions,
  type AvailabilityReport,
} from "../lib/api"

const controlStyle = {
  background: "var(--t-card)",
  color: "var(--t-text)",
  border: "1px solid var(--t-border-alpha)",
}
type Period = "24h" | "7d" | "30d" | "custom"
function Badge({
  children,
  tone = "neutral",
}: {
  children: React.ReactNode
  tone?: "good" | "bad" | "warn" | "neutral"
}) {
  const colors = {
    good: "#4ade80",
    bad: "#ff6688",
    warn: "#ffb86b",
    neutral: "var(--t-muted)",
  }
  return (
    <span
      className="inline-flex items-center gap-1 rounded-full px-2 py-1 font-mono text-[10px] uppercase"
      style={{
        color: colors[tone],
        background: `${colors[tone]}18`,
        border: `1px solid ${colors[tone]}44`,
      }}
    >
      <span
        className="h-1.5 w-1.5 rounded-full"
        style={{ background: colors[tone] }}
      />
      {children}
    </span>
  )
}
function duration(seconds: number | null | undefined) {
  if (seconds == null) return "—"
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m`
  const hours = Math.floor(minutes / 60)
  return `${hours}h ${minutes % 60}m`
}
function percent(value: number | null | undefined) {
  return value == null
    ? "No sufficient monitoring data"
    : `${value.toFixed(3)}%`
}
function tone(report: AvailabilityReport) {
  return report.availability_percent == null
    ? "neutral"
    : report.sla_breached
      ? "bad"
      : "good"
}

export function latestAvailabilityReports(rows: AvailabilityReport[]) {
  const latest = new Map<string, AvailabilityReport>()
  for (const row of rows) {
    const key = availabilityEntityKey(row)
    const current = latest.get(key)
    if (
      !current ||
      (row.generated_at ?? "") > (current.generated_at ?? "") ||
      ((row.generated_at ?? "") === (current.generated_at ?? "") &&
        row.id > current.id)
    ) {
      latest.set(key, row)
    }
  }
  return [...latest.values()]
}

function availabilityEntityKey(row: Pick<AvailabilityReport, "entity_type" | "entity_id">) {
  return `${row.entity_type}:${row.entity_id}`
}

export function summarizeAvailabilityReports(rows: AvailabilityReport[]) {
  const latest = latestAvailabilityReports(rows)
  const valid = latest.filter((row) => row.availability_percent != null)
  return {
    latest,
    availability: valid.length
      ? valid.reduce((sum, row) => sum + row.availability_percent!, 0) /
        valid.length
      : null,
    devices: latest.length,
    met: latest.filter((row) => row.sla_breached === false).length,
    breached: latest.filter((row) => row.sla_breached === true).length,
    outages: latest.reduce(
      (sum, row) =>
        sum +
        (row.outages?.filter((outage) => outage.ongoing).length ??
          (row.current_outage?.ongoing ? 1 : 0)),
      0,
    ),
  }
}

export default function Availability() {
  const { hasPermission } = useAuth()
  const client = useQueryClient()
  const allowed = hasPermission("availability:read")
  const [period, setPeriod] = useState<Period>("24h")
  const [deviceId, setDeviceId] = useState<number | undefined>()
  const [sla, setSla] = useState("99")
  const [customStart, setCustomStart] = useState("")
  const [customEnd, setCustomEnd] = useState("")
  const [selected, setSelected] = useState<AvailabilityReport | null>(null)
  const [expandedHistoryKey, setExpandedHistoryKey] = useState<string | null>(null)
  const devices = useQuery({
    queryKey: ["availability-devices"],
    queryFn: () => listDeviceOptions({ limit: 500 }),
    staleTime: 300_000,
    enabled: allowed,
  })
  const reports = useQuery({
    queryKey: ["availability-reports"],
    queryFn: () => listAvailabilityReports({ limit: 500 }),
    staleTime: 30_000,
    refetchOnWindowFocus: false,
    enabled: allowed,
  })
  const generate = useMutation({
    mutationFn: createAvailabilityReport,
    onSuccess: (report) => {
      setSelected(report)
      client.invalidateQueries({ queryKey: ["availability-reports"] })
    },
  })
  const summary = useMemo(() => {
    return summarizeAvailabilityReports(reports.data?.items ?? [])
  }, [reports.data])
  const range = () => {
    const end = new Date()
    if (period !== "custom") end.setSeconds(0, 0)
    const start = new Date(end)
    if (period === "24h") start.setHours(start.getHours() - 24)
    if (period === "7d") start.setDate(start.getDate() - 7)
    if (period === "30d") start.setDate(start.getDate() - 30)
    return {
      start: period === "custom" ? customStart : start.toISOString(),
      end: period === "custom" ? customEnd : end.toISOString(),
    }
  }
  const run = () => {
    if (deviceId == null) return
    const selectedRange = range()
    if (!selectedRange.start || !selectedRange.end) return
    generate.mutate({
      entity_type: "device",
      entity_id: deviceId,
      start: selectedRange.start,
      end: selectedRange.end,
      sla_target: Number(sla),
    })
  }
  const selectReport = async (report: AvailabilityReport) => {
    try {
      setSelected(await getAvailabilityReport(report.id))
    } catch {
      // Keep the persisted list row visible if the detail request fails.
      setSelected(report)
    }
  }
  if (!allowed)
    return (
      <div
        className="p-6 font-mono text-sm"
        style={{ color: "var(--t-muted)" }}
      >
        You do not have permission to view availability.
      </div>
    )
  if (reports.isError)
    return (
      <div className="p-6 font-mono text-sm" style={{ color: "#ff6688" }}>
        Unable to load availability reports.
      </div>
    )
  const rows = reports.data?.items ?? []
  const latestIds = new Set(summary.latest.map((report) => report.id))
  const historyRows = rows.filter((row) => !latestIds.has(row.id))
  return (
    <div className="space-y-5 p-4 md:p-6">
      <header>
        <h1
          className="font-display text-2xl font-bold tracking-widest"
          style={{ color: "var(--t-text)" }}
        >
          ENTERPRISE AVAILABILITY
        </h1>
        <p
          className="mt-2 font-mono text-xs"
          style={{ color: "var(--t-muted)" }}
        >
          Evidence-based uptime, coverage and service-level visibility
        </p>
      </header>
      <div className="grid grid-cols-2 gap-2 lg:grid-cols-5">
        {[
          [
            "Overall Availability",
            summary.availability == null
              ? "—"
              : `${summary.availability.toFixed(2)}%`,
          ],
          ["Devices Monitored", summary.devices],
          ["Meeting SLA", summary.met],
          ["SLA Breaches", summary.breached],
          ["Active Outages", summary.outages],
        ].map(([label, value]) => (
          <div
            key={String(label)}
            className="rounded-xl p-3"
            style={{
              background: "var(--t-card)",
              border: "1px solid var(--t-border-alpha)",
            }}
          >
            <div
              className="font-mono text-[10px] uppercase"
              style={{ color: "var(--t-muted)" }}
            >
              {label}
            </div>
            <div
              className="mt-1 font-display text-lg font-semibold"
              style={{ color: "var(--t-text)" }}
            >
              {value}
            </div>
          </div>
        ))}
      </div>
      <GlassCard>
        <div className="flex flex-col gap-3 p-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <div
              className="mb-2 font-display text-sm font-semibold"
              style={{ color: "var(--t-text)" }}
            >
              Generate report
            </div>
            <div className="flex flex-wrap gap-1">
              {(["24h", "7d", "30d", "custom"] as Period[]).map((value) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => setPeriod(value)}
                  className="rounded-lg px-3 py-2 font-mono text-[10px] uppercase"
                  style={{
                    background: period === value ? "#00d4ff22" : "transparent",
                    color: period === value ? "#00d4ff" : "var(--t-muted)",
                    border: `1px solid ${
                      period === value ? "#00d4ff66" : "var(--t-border-alpha)"
                    }`,
                  }}
                >
                  {value === "24h"
                    ? "24 Hours"
                    : value === "7d"
                      ? "7 Days"
                      : value === "30d"
                        ? "30 Days"
                        : "Custom"}
                </button>
              ))}
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <select
              aria-label="Availability device"
              value={deviceId ?? ""}
              onChange={(event) =>
                setDeviceId(
                  event.target.value ? Number(event.target.value) : undefined,
                )
              }
              className="rounded-lg px-3 py-2 font-mono text-xs"
              style={controlStyle}
            >
              <option value="">Select device</option>
              {devices.data?.map((device) => (
                <option key={device.id} value={device.id}>
                  {device.hostname} · {device.ip_address}
                </option>
              ))}
            </select>
            <input
              aria-label="SLA target"
              type="number"
              min="0"
              max="100"
              step="0.01"
              value={sla}
              onChange={(event) => setSla(event.target.value)}
              className="w-24 rounded-lg px-3 py-2 font-mono text-xs"
              style={controlStyle}
            />
            {period === "custom" && (
              <>
                <input
                  aria-label="Custom start"
                  type="datetime-local"
                  value={customStart}
                  onChange={(event) => setCustomStart(event.target.value)}
                  className="rounded-lg px-3 py-2 font-mono text-xs"
                  style={controlStyle}
                />
                <input
                  aria-label="Custom end"
                  type="datetime-local"
                  value={customEnd}
                  onChange={(event) => setCustomEnd(event.target.value)}
                  className="rounded-lg px-3 py-2 font-mono text-xs"
                  style={controlStyle}
                />
              </>
            )}
            <button
              type="button"
              onClick={run}
              disabled={generate.isPending || deviceId == null}
              className="rounded-lg px-4 py-2 font-mono text-xs font-semibold disabled:opacity-50"
              style={{ background: "#00d4ff", color: "#06111a" }}
            >
              {generate.isPending ? "Generating..." : "Generate / Refresh"}
            </button>
          </div>
        </div>
      </GlassCard>
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1.45fr)_minmax(300px,.75fr)]">
        <GlassCard className="overflow-hidden">
          <div
            className="flex items-center justify-between px-5 py-4"
            style={{ borderBottom: "1px solid var(--t-border-alpha)" }}
          >
            <div>
              <h2
                className="font-display text-sm font-semibold"
                style={{ color: "var(--t-text)" }}
              >
                Availability Reports
              </h2>
              <p
                className="mt-1 font-mono text-[10px]"
                style={{ color: "var(--t-muted)" }}
              >
                Persisted report history
              </p>
            </div>
            {reports.isLoading && (
              <span
                className="font-mono text-[10px]"
                style={{ color: "var(--t-muted)" }}
              >
                Loading...
              </span>
            )}
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead>
                <tr style={{ color: "var(--t-muted)" }}>
                  {[
                    "Device / Scope",
                    "Status",
                    "Availability",
                    "Coverage",
                    "Uptime",
                    "Downtime",
                    "Outages",
                    "SLA",
                  ].map((label) => (
                    <th
                      key={label}
                      className="px-4 py-3 font-mono text-[10px] uppercase"
                    >
                      {label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {summary.latest.length ? (
                  summary.latest.map((row) => (
                    <tr
                      key={row.id}
                      onClick={() => void selectReport(row)}
                      className="cursor-pointer transition-colors hover:bg-white/[.03]"
                      style={{
                        borderTop: "1px solid var(--t-border-alpha)",
                        background:
                          selected?.id === row.id ? "#00d4ff0d" : "transparent",
                      }}
                    >
                      <td className="px-4 py-3 font-mono text-xs">
                        <div className="flex items-center gap-2">
                          {row.device_name ??
                            `${row.entity_type} #${row.entity_id}`}
                          <Badge
                            tone="good"
                          >
                            current
                          </Badge>
                        </div>
                        <div
                          className="mt-1 text-[10px]"
                          style={{ color: "var(--t-muted)" }}
                        >
                          {row.ip_address ?? `Report #${row.id}`}
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <Badge
                          tone={
                            row.current_status === "online"
                              ? "good"
                              : row.current_status === "offline"
                                ? "bad"
                                : "neutral"
                          }
                        >
                          {row.current_status ?? "unknown"}
                        </Badge>
                      </td>
                      <td className="px-4 py-3 font-mono text-xs">
                        {percent(row.availability_percent)}
                      </td>
                      <td className="px-4 py-3 font-mono text-xs">
                        {row.coverage_percent == null
                          ? "—"
                          : `${row.coverage_percent}%`}
                      </td>
                      <td className="px-4 py-3 font-mono text-xs">
                        {duration(row.uptime_seconds)}
                      </td>
                      <td className="px-4 py-3 font-mono text-xs">
                        {duration(row.downtime_seconds)}
                      </td>
                      <td className="px-4 py-3 font-mono text-xs">
                        {row.outage_count}
                      </td>
                      <td className="px-4 py-3">
                        <Badge tone={tone(row)}>
                          {row.sla_breached == null
                            ? "insufficient data"
                            : row.sla_breached
                              ? "breached"
                              : "met"}
                          </Badge>
                        <div className="mt-2">
                          <button
                            type="button"
                            onClick={(event) => {
                              event.stopPropagation()
                              const key = availabilityEntityKey(row)
                              setExpandedHistoryKey((current) =>
                                current === key ? null : key,
                              )
                            }}
                            className="font-mono text-[10px] underline"
                            style={{ color: "#00d4ff" }}
                          >
                            View History (
                            {historyRows.filter(
                              (history) =>
                                availabilityEntityKey(history) ===
                                availabilityEntityKey(row),
                            ).length}
                            )
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td
                      colSpan={8}
                      className="px-4 py-14 text-center font-mono text-xs"
                      style={{ color: "var(--t-muted)" }}
                    >
                      {reports.isLoading
                        ? "Loading persisted reports..."
                        : "No historical availability reports."}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          {expandedHistoryKey && (
            <div
              className="border-t p-4"
              style={{ borderColor: "var(--t-border-alpha)" }}
            >
              <div
                className="mb-3 font-mono text-[10px] uppercase"
                style={{ color: "var(--t-muted)" }}
              >
                History · {expandedHistoryKey}
              </div>
              <div className="space-y-2">
                {historyRows.filter(
                  (history) =>
                    availabilityEntityKey(history) === expandedHistoryKey,
                ).length ? (
                  historyRows
                    .filter(
                      (history) =>
                        availabilityEntityKey(history) === expandedHistoryKey,
                    )
                    .map((history) => (
                      <button
                        key={history.id}
                        type="button"
                        onClick={() => void selectReport(history)}
                        className="flex w-full items-center justify-between rounded-lg p-3 text-left hover:bg-white/[.03]"
                        style={{
                          color: "var(--t-text)",
                          background: "var(--t-bg)",
                        }}
                      >
                        <span className="font-mono text-xs">
                          Report #{history.id} · {history.window_start} to {history.window_end}
                        </span>
                        <span className="font-mono text-[10px]" style={{ color: "var(--t-muted)" }}>
                          history
                        </span>
                      </button>
                    ))
                ) : (
                  <div className="font-mono text-xs" style={{ color: "var(--t-muted)" }}>
                    No older reports for this entity.
                  </div>
                )}
              </div>
            </div>
          )}
        </GlassCard>
        {selected ? (
          <GlassCard>
            <div
              className="px-5 py-4"
              style={{ borderBottom: "1px solid var(--t-border-alpha)" }}
            >
              <h2
                className="font-display text-sm font-semibold"
                style={{ color: "var(--t-text)" }}
              >
                Outage Details
              </h2>
              <p
                className="mt-1 font-mono text-[10px]"
                style={{ color: "var(--t-muted)" }}
              >
                {selected.device_name ?? `Entity #${selected.entity_id}`} ·{" "}
                {selected.window_start} to {selected.window_end}
              </p>
            </div>
            <div className="space-y-3 p-5">
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <div
                    className="font-mono text-[10px]"
                    style={{ color: "var(--t-muted)" }}
                  >
                    <span title="Time during the selected period where the device state could not be confidently classified as online or offline.">
                      Unknown / Unmonitored Time
                    </span>
                  </div>
                  <div className="font-mono text-xs">
                    {duration(selected.unknown_seconds)}
                  </div>
                </div>
                <div>
                  <div
                    className="font-mono text-[10px]"
                    style={{ color: "var(--t-muted)" }}
                  >
                    SLA Target
                  </div>
                  <div className="font-mono text-xs">
                    {selected.sla_target_percent}%
                  </div>
                </div>
              </div>
              {selected.availability_percent == null && (
                <div
                  className="rounded-lg p-3 font-mono text-xs"
                  style={{ color: "#ffb86b", background: "#ffb86b14" }}
                >
                  No sufficient monitoring data
                </div>
              )}
              {selected.outages?.length ? (
                selected.outages.map((outage) => (
                  <div
                    key={outage.id}
                    className="rounded-lg p-3"
                    style={{ background: "var(--t-bg)" }}
                  >
                    <div className="flex justify-between gap-2 font-mono text-xs">
                      <span>{outage.start_time}</span>
                      <Badge tone={outage.planned ? "warn" : "bad"}>
                        {outage.planned ? "planned" : "unplanned"}
                      </Badge>
                    </div>
                    <div
                      className="mt-2 font-mono text-[10px]"
                      style={{ color: "var(--t-muted)" }}
                    >
                      {outage.end_time ?? "Ongoing"} ·{" "}
                      {duration(outage.duration_seconds)} ·{" "}
                      {outage.reason ?? "Reason unavailable"}
                    </div>
                  </div>
                ))
              ) : (
                <div
                  className="py-8 text-center font-mono text-xs"
                  style={{ color: "var(--t-muted)" }}
                >
                  {selected.unknown_seconds === 0
                    ? "No outages recorded during this period."
                    : "No outages recorded; unknown / unmonitored time remains."}
                </div>
              )}
            </div>
          </GlassCard>
        ) : (
          <GlassCard>
            <div
              className="p-12 text-center font-mono text-xs"
              style={{ color: "var(--t-muted)" }}
            >
              Select a report to view outage details.
            </div>
          </GlassCard>
        )}
      </div>
    </div>
  )
}
