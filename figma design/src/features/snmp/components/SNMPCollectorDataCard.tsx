import GlassCard from "../../../components/GlassCard"
import MacPortTopology2D from "./MacPortTopology2D"
import {
  formatBytes,
  formatSpeed,
  getModuleConfig,
} from "../modules/snmpModuleRegistry"

function titleize(text: string): string {
  return text.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())
}

function formatValue(value: any): string {
  if (value === null || value === undefined || value === "") return "-"
  if (typeof value === "boolean") return value ? "Yes" : "No"
  if (typeof value === "number")
    return Number.isInteger(value) ? String(value) : value.toFixed(2)
  if (typeof value === "string") return value
  if (typeof value === "object" && value.display) return String(value.display)
  if (typeof value === "object") return JSON.stringify(value)
  return String(value)
}

function formatMetricValue(key: string, value: any): string {
  if (value === null || value === undefined) return "-"
  if (key.includes("bytes") || key.includes("octets"))
    return formatBytes(Number(value))
  if (key.includes("speed_bps")) return formatSpeed(Number(value))
  if (key.includes("percent")) return `${Number(value).toFixed(1)}%`
  if (
    key.includes("timestamp") ||
    key.includes("polled_at") ||
    key.includes("last_poll")
  ) {
    const date = new Date(value)
    return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', hour12: true })
  }
  return formatValue(value)
}

function findRows(data: any): any[] {
  if (!data) return []
  if (Array.isArray(data)) return data
  for (const value of Object.values(data)) {
    if (Array.isArray(value)) return value
  }
  return []
}

function getSummaryItems(data: any): Array<[string, any]> {
  if (!data || typeof data !== "object" || Array.isArray(data)) return []
  return Object.entries(data)
    .filter(([, value]) => !Array.isArray(value))
    .slice(0, 12)
}

function isEmptyValue(value: any): boolean {
  if (value === null || value === undefined || value === "") return true
  if (Array.isArray(value)) return value.length === 0
  if (typeof value === "object") return Object.keys(value).length === 0
  return false
}

function normalizeMac(value: unknown): string | null {
  const compact = String(value ?? "")
    .replace(/[^0-9a-f]/gi, "")
    .toUpperCase()
  if (compact.length !== 12) return null
  return compact.match(/.{2}/g)?.join(":") || null
}

function ipSortKey(value: unknown): [number, ...Array<number | string>] {
  const text = String(value)
  const parts = text.split(".")
  if (parts.length === 4 && parts.every((part) => /^\d+$/.test(part))) {
    return [0, ...parts.map(Number)]
  }
  return [1, text]
}

export default function SNMPCollectorDataCard({
  name,
  collector,
  arpEntries = [],
  refreshing = false,
  onRefresh,
}: {
  name: string
  collector: any
  arpEntries?: any[]
  refreshing?: boolean
  onRefresh?: () => void
}) {
  const config = getModuleConfig(name)
  const color = collector?.supported ? config?.color || "#00d4ff" : "#ff3366"
  const rows = findRows(collector?.data)
  const configuredSummaryFields = config?.summaryFields
  const summary = getSummaryItems(collector?.data)
    .filter(
      ([key]) =>
        !configuredSummaryFields || configuredSummaryFields.includes(key),
    )
    .filter(([, value]) => !isEmptyValue(value))
  const columns =
    rows.length > 0
      ? Array.from(
          new Set(rows.flatMap((row) => Object.keys(row || {}))),
        ).slice(0, 12)
      : []
  const selfMacs = new Set(
    (collector?.data?.entries || [])
      .filter((entry: any) => String(entry?.status || '').toLowerCase() === 'self')
      .map((entry: any) => normalizeMac(entry?.mac || entry?.mac_address))
      .filter(Boolean),
  )
  const portGroups =
    name === "mac_table" && Array.isArray(collector?.data?.port_groups)
      ? collector.data.port_groups
          .map((group: any) => ({
            ...group,
            macs: (group.macs || []).filter((mac: any) => !selfMacs.has(normalizeMac(mac))),
          }))
          .filter((group: any) => group.macs.length > 0)
      : []
  const ipByMac = new Map<string, string[]>()
  arpEntries.forEach((entry) => {
    const mac = normalizeMac(entry?.mac || entry?.mac_address)
    const ip = entry?.ip_address || entry?.ip
    if (!mac || !ip) return
    ipByMac.set(mac, [...new Set([...(ipByMac.get(mac) || []), String(ip)])])
  })
  // The MAC-table endpoint also returns its last-known ARP mapping on each
  // entry. Use it when the separate ARP request is temporarily empty.
  ;(collector?.data?.entries || []).forEach((entry: any) => {
    const mac = normalizeMac(entry?.mac || entry?.mac_address)
    const ips =
      entry?.ip_addresses || (entry?.ip_address ? [entry.ip_address] : [])
    if (!mac || !ips.length) return
    ipByMac.set(mac, [
      ...new Set([...(ipByMac.get(mac) || []), ...ips.map(String)]),
    ])
  })
  const enrichedPortGroups = portGroups.map((group: any) => {
    const macs = [...new Set((group.macs || []).map(normalizeMac).filter(Boolean))] as string[]
    const ips = [...(group.ip_addresses || group.ips || [])]
    macs.forEach((mac) => ips.push(...(ipByMac.get(mac) || [])))
    const vlans = [...new Set(group.vlans || [])].sort((a: any, b: any) => Number(a) - Number(b))
    const deviceMappings = macs
      .map((mac) => ({
        mac,
        ips: [...new Set(ipByMac.get(mac) || [])].sort((a, b) => {
          const left = ipSortKey(a)
          const right = ipSortKey(b)
          return JSON.stringify(left).localeCompare(JSON.stringify(right), undefined, { numeric: true })
        }),
      }))
      // Keep useful MAC -> IP relationships at the top. Unresolved MACs are
      // still shown, but never push the actionable mappings out of view.
      .sort((left, right) => Number(right.ips.length > 0) - Number(left.ips.length > 0) || left.mac.localeCompare(right.mac))
    return {
      ...group,
      macs,
      mac_count: macs.length,
      vlans,
      device_mappings: deviceMappings,
      classification: group.classification || "UNKNOWN",
      ip_addresses: [...new Set(ips)].sort((a, b) => {
        const left = ipSortKey(a)
        const right = ipSortKey(b)
        return JSON.stringify(left).localeCompare(JSON.stringify(right), undefined, { numeric: true })
      }),
    }
  })
  const macTableStats =
    name === "mac_table"
      ? {
          ports: portGroups.length,
          macs: new Set(
            enrichedPortGroups.flatMap((group: any) => group.macs || []),
          ).size,
          ips: new Set(
            enrichedPortGroups.flatMap(
              (group: any) => group.ip_addresses || [],
            ),
          ).size,
          vlans: new Set(
            enrichedPortGroups.flatMap((group: any) => group.vlans || []),
          ).size,
          uplinks: portGroups.filter(
            (group: any) => group.classification === "UPLINK/TRUNK",
          ).length,
        }
      : null
  const dataQuality = collector?.data?.data_quality ||
    (collector?.collection_status === "FAILED" ? "stale" : "partial")
  const qualityTone = dataQuality === "complete" ? "#00ff88" : dataQuality === "stale" ? "#ff6b8a" : "#ffaa00"

  return (
    <GlassCard className="overflow-hidden">
      <div
        className="relative overflow-hidden p-4"
        style={{
          borderBottom: `1px solid ${color}33`,
          background:
            "linear-gradient(135deg, rgba(8,25,55,.8), rgba(5,12,25,.45))",
        }}
      >
        <div
          className="absolute -right-10 -top-16 h-36 w-36 rounded-full opacity-20"
          style={{ background: color, filter: "blur(35px)" }}
        />
        <div className="relative flex flex-wrap items-center gap-2">
          <div>
            <div
              className="font-display font-bold text-sm tracking-[.16em]"
              style={{ color }}
            >
              {titleize(config?.label || name)}
            </div>
            {name === "mac_table" && (
              <div
                className="mt-1 font-mono text-[9px] uppercase tracking-wider"
                style={{ color: "#8899bb" }}
              >
                Forwarding database · learned L2 identities
              </div>
            )}
          </div>
          <span
            className="rounded border px-2 py-1 font-mono text-[9px] uppercase tracking-wider"
            style={{
              background: collector?.supported
                ? "rgba(0,255,136,0.12)"
                : "rgba(255,51,102,0.12)",
              color,
            }}
          >
            {collector?.supported ? "SUPPORTED" : "NOT SUPPORTED"}
          </span>
          {collector?.timestamp && (
            <span
              className="ml-auto font-mono text-[10px]"
              style={{ color: "#667799" }}
            >
              LAST POLL · {new Date(collector.timestamp).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', hour12: true })}
            </span>
          )}
          {name === "mac_table" && onRefresh && (
            <button type="button" onClick={onRefresh} disabled={refreshing} className="tool ml-auto h-7 border-cyan-400/30 px-2 text-[9px]" style={{ color: refreshing ? "#ffaa00" : "#00d4ff" }}>
              {refreshing ? "REFRESHING..." : "REFRESH"}
            </button>
          )}
        </div>
        {name === "mac_table" && collector?.supported && (
          <div className="relative mt-3 flex flex-wrap items-center gap-2 font-mono text-[9px] uppercase tracking-wider" style={{ color: qualityTone }}>
            <span>{dataQuality === "complete" ? "● DATA COMPLETE" : dataQuality === "stale" ? "○ DATA STALE" : "◐ DATA PARTIAL"}</span>
            {dataQuality !== "complete" && <span style={{ color: "#8899bb" }}>MACs retained · ARP enrichment may be pending</span>}
          </div>
        )}
        {macTableStats && (
          <div className="relative mt-4 grid grid-cols-2 gap-2 sm:grid-cols-5">
            {([
              ["PORTS", macTableStats.ports, "#00d4ff"],
              ["MAC ADDRESSES", macTableStats.macs, "#00ff88"],
              ["IP MAPPINGS", macTableStats.ips, "#67e8f9"],
              ["VLANS", macTableStats.vlans, "#a78bfa"],
              ["UPLINKS", macTableStats.uplinks, "#ffaa00"],
            ] as Array<[string, number, string]>).map(
              ([label, value, tone]) => (
                <div
                  key={label}
                  className="rounded-lg border p-2.5"
                  style={{
                    borderColor: `${tone}33`,
                    background: "rgba(2,8,18,.55)",
                  }}
                >
                  <div
                    className="font-mono text-[8px] uppercase tracking-wider"
                    style={{ color: "#667799" }}
                  >
                    {label}
                  </div>
                  <div
                    className="mt-1 font-display text-lg font-bold"
                    style={{ color: tone }}
                  >
                    {value}
                  </div>
                </div>
              ),
            )}
          </div>
        )}
        {!collector?.supported && collector?.reason && (
          <div className="font-mono text-xs mt-2" style={{ color: "#ffaa00" }}>
            {collector.reason}
          </div>
        )}
      </div>

      {collector?.supported ? (
        <>
          {portGroups.length > 0 && (
            <>
              <MacPortTopology2D groups={enrichedPortGroups} />
              <div className="overflow-x-auto p-4 sm:p-5">
                <div className="mb-3 flex items-center justify-between gap-3">
                  <div>
                    <div
                      className="font-display text-xs font-bold tracking-[.16em]"
                      style={{ color: "#00d4ff" }}
                    >
                      PORT SUMMARY
                    </div>
                    <div
                      className="mt-1 font-mono text-[9px] uppercase tracking-wider"
                      style={{ color: "#667799" }}
                    >
                      Each learned MAC with its matching ARP IP address
                    </div>
                  </div>
                  <span
                    className="rounded border border-cyan-400/20 px-2 py-1 font-mono text-[9px]"
                    style={{ color: "#8899bb" }}
                  >
                    {portGroups.length} PORTS
                  </span>
                </div>
                <table className="w-full" style={{ minWidth: 860 }}>
                  <thead>
                    <tr>
                      {[
                        "Port",
                        "Classification",
                        "MAC Count",
                        "VLANs",
                        "Device MAC → IP Mapping",
                      ].map((col) => (
                        <th
                          key={col}
                          className="sticky top-0 px-3 py-2.5 text-left font-mono text-[9px] uppercase tracking-wider"
                          style={{ color: "#8899bb", background: "#081937" }}
                        >
                          {col}
                        </th>
                      ))}
                    </tr>
                  </thead>
                <tbody>
                  {enrichedPortGroups.map((group: any, index: number) => (
                      <tr
                        key={`${group.if_index ?? group.port ?? `unknown-${index}`}`}
                        className="transition-colors hover:bg-cyan-400/[.04]"
                        style={{
                          borderTop: "1px solid rgba(0,212,255,0.06)",
                          background:
                            index % 2 ? "rgba(8,25,55,.18)" : "transparent",
                        }}
                      >
                        <td
                          className="px-3 py-2 font-mono text-xs"
                          style={{ color: "#c8d8ee" }}
                        >
                          {group.port ?? group.if_index ?? "-"}
                        </td>
                        <td
                          className="px-3 py-2 font-mono text-xs"
                          style={{
                            color:
                              group.classification === "UPLINK/TRUNK"
                                ? "#a78bfa"
                                : group.classification === "ENDPOINT"
                                  ? "#00ff88"
                                  : "#ffaa00",
                          }}
                        >
                          {group.classification}
                        </td>
                        <td
                          className="px-3 py-2 font-mono text-xs"
                          style={{ color: "#c8d8ee" }}
                        >
                          {group.mac_count}
                        </td>
                        <td
                          className="px-3 py-2 font-mono text-xs"
                          style={{ color: "#c8d8ee" }}
                        >
                          {group.vlans?.join(", ") || "-"}
                        </td>
                        <td className="px-3 py-2 align-top">
                          <div className="grid max-h-40 gap-1 overflow-y-auto pr-1 sm:grid-cols-2">
                            {(group.device_mappings || []).map((mapping: any) => (
                              <div
                                key={mapping.mac}
                                className="rounded border px-2 py-1"
                                style={{ borderColor: "rgba(0,212,255,0.12)", background: "rgba(8,25,55,.28)" }}
                              >
                                <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 font-mono text-[9px] leading-tight">
                                  <span style={{ color: mapping.ips?.length ? "#f1f5f9" : "#77859b" }}><span style={{ color: "#8899bb" }}>MAC</span> {mapping.mac}</span>
                                  <span style={{ color: mapping.ips?.length ? "#67e8f9" : "#77859b" }}><span style={{ color: "#8899bb" }}>IP</span> {mapping.ips?.join(", ") || "NOT RESOLVED"}</span>
                                </div>
                              </div>
                            ))}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
          {summary.length > 0 && (
            <div className="grid grid-cols-2 gap-2 p-4 sm:p-5 md:grid-cols-4">
              {summary.map(([key, value]) => (
                <div
                  key={key}
                  className="rounded-lg p-3"
                  style={{
                    background:
                      "linear-gradient(145deg, rgba(8,25,55,.65), rgba(2,8,18,.5))",
                    border: "1px solid rgba(0,212,255,0.12)",
                  }}
                >
                  <div
                    className="font-mono text-[10px]"
                    style={{ color: "#667799" }}
                  >
                    {titleize(key)}
                  </div>
                  <div
                    className="font-mono text-xs mt-1 break-words"
                    style={{ color: "#c8d8ee" }}
                  >
                    {formatMetricValue(key, value)}
                  </div>
                </div>
              ))}
            </div>
          )}
          {rows.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full" style={{ minWidth: 900 }}>
                <thead>
                  <tr
                    style={{ borderBottom: "1px solid rgba(0,212,255,0.08)" }}
                  >
                    {columns.map((col) => (
                      <th
                        key={col}
                        className="text-left px-4 py-2 font-mono text-xs"
                        style={{
                          color: "#8899bb",
                          background: "rgba(8,25,55,0.95)",
                        }}
                      >
                        {titleize(col)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row, index) => (
                    <tr
                      key={index}
                      style={{ borderBottom: "1px solid rgba(0,212,255,0.04)" }}
                    >
                      {columns.map((col) => (
                        <td
                          key={col}
                          className="px-4 py-2 font-mono text-[10px] max-w-[260px] truncate"
                          style={{ color: "#c8d8ee" }}
                        >
                          {formatMetricValue(col, row?.[col])}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {summary.length === 0 && rows.length === 0 ? (
            <div
              className="font-mono text-xs p-6 text-center"
              style={{ color: "#8899bb" }}
            >
              Supported, but no rows stored yet.
            </div>
          ) : (
            <details
              className="mx-4 mb-4 rounded"
              style={{
                border: "1px solid rgba(0,212,255,0.1)",
                background: "rgba(8,25,55,0.25)",
              }}
            >
              <summary
                className="font-mono text-[10px] px-3 py-2 cursor-pointer"
                style={{ color: "#00d4ff" }}
              >
                RAW DATA
              </summary>
              <pre
                className="font-mono text-[10px] p-3 overflow-x-auto max-h-80"
                style={{ color: "#8899bb" }}
              >
                {JSON.stringify(collector.data ?? {}, null, 2)}
              </pre>
            </details>
          )}
        </>
      ) : (
        <div className="p-4">
          {collector?.missing?.length > 0 && (
            <div className="font-mono text-[10px]" style={{ color: "#8899bb" }}>
              Missing: {collector.missing.join(", ")}
            </div>
          )}
        </div>
      )}
    </GlassCard>
  )
}
