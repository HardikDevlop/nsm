import GlassCard from "../../../components/GlassCard"
import { useState } from "react"
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

function inventoryRows(data: any): any[] {
  if (!data || typeof data !== "object" || Array.isArray(data)) return []
  const groups = ["chassis", "modules", "power_supplies", "fans", "sensors", "cpus", "other"]
  return groups.flatMap((group) => {
    const value = data[group]
    if (Array.isArray(value)) return value
    return value && typeof value === "object" ? [value] : []
  }).sort((left, right) => Number(left?.index ?? 0) - Number(right?.index ?? 0))
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

function inventoryDate(value: unknown): string {
  if (!value) return "Not available"
  const date = new Date(String(value))
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString("en-IN", { timeZone: "Asia/Kolkata", hour12: true })
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
  const inventoryData = name === "inventory" ? (collector?.data || {}) : null
  const inventoryChassis = inventoryData?.chassis || {}
  const inventoryValues = name === "inventory" ? {
    total_count: inventoryData?.total_count ?? 0,
    fru_count: inventoryData?.fru_count ?? 0,
    port_count: inventoryData?.port_count ?? inventoryData?.ports?.length,
    loader_date: inventoryData?.loader_date ?? collector?.timestamp,
    system_uptime: inventoryData?.system_uptime ?? inventoryData?.uptime ?? inventoryData?.system?.uptime,
    loader_version: inventoryData?.loader_version ?? inventoryChassis.software_rev,
    firmware_version: inventoryData?.firmware_version ?? inventoryChassis.firmware_rev,
  } : null
  const [inventoryView, setInventoryView] = useState<"all" | "ports" | null>(null)
  const inventoryComponents = name === "inventory" ? inventoryRows(collector?.data) : []
  const inventoryPorts = name === "inventory" && Array.isArray(collector?.data?.ports)
    ? collector.data.ports
    : []
  const inventoryAllRows = [...inventoryComponents, ...inventoryPorts]
    .sort((left: any, right: any) => Number(left?.index ?? 0) - Number(right?.index ?? 0))
  const color = collector?.supported ? config?.color || "#00d4ff" : "#ff3366"
  const rows = name === "inventory" ? inventoryRows(collector?.data) : findRows(collector?.data)
  // ARP users need the VLAN identity, not the bridge interface index.
  const displayRows = name === "interfaces"
    ? rows.slice().sort((left: any, right: any) =>
        Number(left?.ifIndex ?? left?.if_index ?? 0) - Number(right?.ifIndex ?? right?.if_index ?? 0),
      )
    : name === "arp"
    ? rows.map((row: any) => {
        const next = { ...row }
        delete next.interface
        delete next.if_index
        delete next.port
        if (!("vlan_id" in next)) next.vlan_id = null
        return next
      })
    : rows
  const configuredSummaryFields = config?.summaryFields
  const summary = getSummaryItems(collector?.data)
    .filter(
      ([key]) =>
        !configuredSummaryFields || configuredSummaryFields.includes(key),
    )
    .filter(([key]) => !(name === "interfaces" && /mac/i.test(key)))
    .filter(([, value]) => !isEmptyValue(value))
  const columns =
    displayRows.length > 0
      ? Array.from(
          new Set(displayRows.flatMap((row) => Object.keys(row || {}))),
        ).filter((column) => !(name === "mac_table" && /ip_addresses|^ips$/i.test(column))).slice(0, 12)
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
    <GlassCard className="snmp-collector-card overflow-hidden">
      <div
        className="relative overflow-hidden p-4"
        style={{
          borderBottom: `1px solid ${color}33`,
          background: "var(--t-card)",
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
        {name === "inventory" && (
          <div className="relative mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {[
              ["Total components", inventoryValues?.total_count],
              ["Ports", inventoryValues?.port_count],
              ["Loader date", inventoryDate(inventoryValues?.loader_date)],
              ["System uptime", inventoryValues?.system_uptime],
              ["Loader version", inventoryValues?.loader_version],
              ["Firmware version", inventoryValues?.firmware_version],
              ["Chassis model", inventoryChassis.model],
              ["Serial number", inventoryChassis.serial],
              ["Manufacturer", inventoryChassis.manufacturer],
              ["Hardware revision", inventoryChassis.hardware_rev],
              ["Chassis index", inventoryChassis.index],
            ].map(([label, value]) => {
              const clickable = label === "Total components" || label === "Ports"
              return <div
                key={String(label)}
                role={clickable ? "button" : undefined}
                tabIndex={clickable ? 0 : undefined}
                onClick={clickable ? () => setInventoryView(label === "Ports" ? "ports" : "all") : undefined}
                onKeyDown={clickable ? (event) => {
                  if (event.key === "Enter" || event.key === " ") setInventoryView(label === "Ports" ? "ports" : "all")
                } : undefined}
                className={`rounded-lg p-3 ${clickable ? "cursor-pointer transition-colors hover:border-cyan-400/50" : ""}`}
                style={{ background: "var(--t-card)", border: "1px solid var(--t-border-alpha)" }}
              >
                <div className="font-mono text-[10px] uppercase tracking-wide" style={{ color: "var(--t-muted)" }}>{label}</div>
                <div className="mt-1 break-words font-mono text-sm font-semibold" style={{ color: value === undefined || value === null || value === "" ? "var(--t-muted)" : "var(--t-text)" }}>
                  {value === undefined || value === null || value === "" ? "Not available" : String(value)}
                </div>
                {clickable && <div className="mt-1 font-mono text-[9px] uppercase tracking-wider" style={{ color: "var(--t-accent)" }}>View details</div>}
              </div>
            })}
          </div>
        )}
        {macTableStats && (
          <div className="snmp-mac-stats relative mt-4 grid grid-cols-2 gap-2 sm:grid-cols-5">
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
                  className="snmp-mac-stat rounded-lg border p-2.5"
                  style={{
                    borderColor: `${tone}33`,
                    background: "var(--t-card)",
                  }}
                >
                  <div
                    className="font-mono text-[9px] uppercase tracking-wider"
                    style={{ color: "var(--t-text)" }}
                  >
                    {label}
                  </div>
                  <div
                    className="mt-1 font-display text-xl font-normal"
                    style={{ color: "var(--t-text)" }}
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
            <>              <div className="snmp-port-summary overflow-x-auto p-4 sm:p-5">
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
                <table className="snmp-port-summary-table w-full" style={{ minWidth: 860 }}>
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
                          style={{ color: "var(--t-text-secondary)", background: "var(--t-table-header)" }}
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
                          background: index % 2 ? "var(--t-table-row)" : "transparent",
                        }}
                      >
                        <td
                          className="px-3 py-2 font-mono text-xs"
                          style={{ color: "var(--t-text, #111827)", opacity: 1 }}
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
                          style={{ color: "var(--t-text, #111827)", opacity: 1 }}
                        >
                          {group.mac_count}
                        </td>
                        <td
                          className="px-3 py-2 font-mono text-xs"
                          style={{ color: "var(--t-text, #111827)", opacity: 1 }}
                        >
                          {group.vlans?.join(", ") || "-"}
                        </td>
                        <td className="px-3 py-2 align-top">
                          <div className="grid max-h-40 gap-1 overflow-y-auto pr-1 sm:grid-cols-2">
                            {(group.device_mappings || []).map((mapping: any) => (
                              <div
                                key={mapping.mac}
                                className="snmp-mac-mapping rounded border px-2 py-1"
                                style={{ borderColor: "var(--t-border)", background: "var(--t-card)" }}
                              >
                                <div className="flex flex-wrap items-center gap-2 font-mono text-[9px] leading-tight">
                                  <span className="inline-flex items-center gap-1">
                                    <b className="rounded px-1 py-0.5 text-[8px] font-semibold tracking-wider" style={{ color: 'var(--t-text-secondary)', background: 'var(--t-table-header)', border: '1px solid var(--t-border)' }}>MAC</b>
                                    <span className="font-semibold" style={{ color: 'var(--t-text)' }}>{mapping.mac}</span>
                                  </span>
                                  <span className="inline-flex items-center gap-1">
                                    <b className="rounded px-1 py-0.5 text-[8px] font-semibold tracking-wider" style={{ color: 'var(--t-accent)', background: 'var(--t-accent-alpha)', border: '1px solid var(--t-accent-border)' }}>IP</b>
                                    <span className="font-semibold" style={{ color: mapping.ips?.length ? 'var(--t-accent)' : 'var(--t-muted)' }}>{mapping.ips?.join(", ") || "NOT RESOLVED"}</span>
                                  </span>
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
          {name === "inventory" && inventoryView && (
            <div className="mx-4 mb-4 overflow-hidden rounded-lg" style={{ border: "1px solid var(--t-border)", background: "var(--t-card)" }}>
              <div className="flex items-center justify-between gap-3 border-b p-3" style={{ borderColor: "var(--t-border)" }}>
                <div className="font-display text-xs font-bold uppercase tracking-[.16em]" style={{ color: "var(--t-accent)" }}>
                  {inventoryView === "ports" ? "Port Details" : "Component Details"}
                </div>
                <button type="button" className="font-mono text-[10px] uppercase" style={{ color: "var(--t-muted)" }} onClick={() => setInventoryView(null)}>Close</button>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full" style={{ minWidth: inventoryView === "ports" ? 700 : 1100 }}>
                  <thead>
                    <tr style={{ background: "var(--t-table-header)" }}>
                      {(inventoryView === "ports"
                        ? ["index", "name", "class", "parent_index", "parent_rel_pos"]
                        : ["index", "name", "description", "class", "model", "serial", "hardware_rev", "firmware_rev", "software_rev", "manufacturer", "is_fru", "parent_index"]
                      ).map((column) => <th key={column} className="px-3 py-2 text-left font-mono text-[10px] uppercase" style={{ color: "var(--t-text-secondary)" }}>{titleize(column)}</th>)}
                    </tr>
                  </thead>
                  <tbody>
                    {(inventoryView === "ports" ? inventoryPorts : inventoryAllRows).map((row: any, index: number) => {
                      const columnsForRow = inventoryView === "ports"
                        ? ["index", "name", "class", "parent_index", "parent_rel_pos"]
                        : ["index", "name", "description", "class", "model", "serial", "hardware_rev", "firmware_rev", "software_rev", "manufacturer", "is_fru", "parent_index"]
                      return <tr key={`${row?.index ?? index}`} style={{ borderTop: "1px solid var(--t-border)" }}>
                        {columnsForRow.map((column) => <td key={column} className="px-3 py-2 font-mono text-[10px]" style={{ color: "var(--t-text)" }}>{formatMetricValue(column, row?.[column])}</td>)}
                      </tr>
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}
          {name !== "inventory" && summary.length > 0 && (
            <div className="grid grid-cols-2 gap-2 p-4 sm:p-5 md:grid-cols-4">
              {summary.map(([key, value]) => (
                <div
                  key={key}
                  className="rounded-lg p-3"
                  style={{
                    background: "var(--t-card)",
                    border: "1px solid var(--t-border)",
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
                    style={{ color: "var(--t-text, #111827)", opacity: 1 }}
                  >
                    {formatMetricValue(key, value)}
                  </div>
                </div>
              ))}
            </div>
          )}
          {rows.length > 0 && name !== "inventory" && (
            <div className="overflow-x-auto">
              <table className="w-full snmp-readable-table snmp-collector-data-table snmp-arp-table" style={{ minWidth: 900 }}>
                <thead>
                  <tr
                    style={{ borderBottom: "1px solid rgba(0,212,255,0.08)" }}
                  >
                    {columns.map((col) => (
                      <th
                        key={col}
                        className="text-left px-4 py-2 font-mono text-xs"
                        style={{
                          color: "#111827",
                          background: "transparent",
                          opacity: 1,
                        }}
                      >
                        {titleize(col)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {displayRows.map((row, index) => (
                    <tr
                      key={index}
                      style={{ borderBottom: "1px solid rgba(0,212,255,0.04)" }}
                    >
                      {columns.map((col) => (
                        <td
                          key={col}
                          className="px-4 py-2 font-mono text-[10px] max-w-[260px] truncate"
                          style={{ color: "var(--t-text, #111827)", opacity: 1 }}
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
                border: "1px solid var(--t-border)",
                background: "var(--t-card)",
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
