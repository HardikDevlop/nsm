import { useEffect, useMemo, useState } from "react"
import { useNavigate, useParams } from "react-router"
import plugUltraAsset from "../assets/plug-ultra.png"
import {
  getLatestInterfaces,
  getLatestManualTopologySnapshot,
  getSNMPInterfaces,
  updateManualTopologySnapshot,
  type SNMPInterfaceStats,
} from "../lib/api"

type Port = {
  id: number
  name: string
  ifIndex: number | null
  admin: string
  oper: string
  speed: string
  mac: string
  ip: string
  description: string
  source: string
  ifType: string
}
type Device = {
  id: string
  name: string
  type: string
  tone?: string
  x?: number
  y?: number
  backendId?: number
  ipAddress?: string
  subtitle?: string
  vendor?: string
  model?: string
  status?: string
  ports?: string[]
  portStatuses?: Record<string, string>
  portSources?: Record<string, string>
}
type Link = {
  id: string
  from: string
  to: string
  fromPort?: string
  toPort?: string
  status?: string
  fromIfIndex?: number | null
  toIfIndex?: number | null
}
type Workspace = { devices: Device[] links: Link[] }

const STORAGE_KEY = "nms.manual-topology.workspace.v2"

function normalizePort(
  item: SNMPInterfaceStats,
  index: number,
  source: string,
): Port {
  const raw = item as unknown as Record<string, unknown>
  const ifIndexRaw = raw.if_index ?? raw.ifIndex
  return {
    id: Number(raw.id ?? raw.interface_id ?? ifIndexRaw ?? index),
    name: String(
      raw.name ?? raw.interface_name ?? `Interface ${ifIndexRaw ?? index + 1}`,
    ),
    ifIndex: ifIndexRaw == null ? null : Number(ifIndexRaw),
    admin: String(
      raw.admin_status ?? raw.adminStatus ?? "UNKNOWN",
    ).toUpperCase(),
    oper: String(
      raw.status ?? raw.oper_status ?? raw.operStatus ?? "UNKNOWN",
    ).toUpperCase(),
    speed: String(raw.speed_display ?? raw.speed_label ?? raw.speed ?? (raw.speed_bps != null ? `${Number(raw.speed_bps) >= 1_000_000_000 ? (Number(raw.speed_bps) / 1_000_000_000).toFixed(1) + " Gbps" : Number(raw.speed_bps) >= 1_000_000 ? (Number(raw.speed_bps) / 1_000_000).toFixed(0) + " Mbps" : raw.speed_bps + " bps"}` : "N/A")),
    mac: String(raw.mac_address ?? raw.mac ?? ""),
    ip: Array.isArray(raw.ip_addresses ?? raw.addresses)
      ? ((raw.ip_addresses ?? raw.addresses) as unknown[]).map(String).join(", ")
      : String(raw.ip_address ?? raw.ip ?? raw.primary_ip ?? ""),
    description: String(raw.description ?? ""),
    source,
    ifType: String(raw.if_type ?? raw.ifType ?? raw.type ?? ""),
  }
}

function manualPort(name: string, device: Device): Port {
  return {
    id: 0,
    name,
    ifIndex: null,
    admin: "UNKNOWN",
    oper: device.portStatuses?.[name]?.toUpperCase() || "UNKNOWN",
    speed: "N/A",
    mac: "",
    ip: "",
    description: "Manual fallback port",
    source: "manual_fallback",
    ifType: "ethernet",
  }
}

function fallbackPort(device: Device): Port {
  return manualPort("Port 1", device)
}

function portState(port: Port, link?: Link) {
  if (link) return "USED"
  if (port.source === "manual_fallback") return "MANUAL"
  if (port.admin === "DOWN") return "ADMIN DOWN"
  if (port.oper === "DOWN") return "DOWN"
  if (port.oper === "UP") return "AVAILABLE / UP"
  return "UNKNOWN"
}

function isUplink(port: Port) {
  return /sfp|qsfp|tengig|ten.?gig|twentyfivegig|25g|fortygig|40g|hundredgig|100g|uplink/i.test(
    `${port.name} ${port.description} ${port.speed}`,
  )
}

function isLogical(port: Port) {
  return /lag|port.?channel|etherchannel|bond|bridge|vlan|svi|loopback|tunnel|irb|virtual|sub.?interface/i.test(
    `${port.name} ${port.description} ${port.ifType}`,
  )
}

function isManagement(port: Port) {
  return /management|^mgmt|managementethernet/i.test(
    `${port.name} ${port.description}`,
  )
}

function naturalPortSort(a: Port, b: Port) {
  return a.name.localeCompare(b.name, undefined, {
    numeric: true,
    sensitivity: "base",
  })
}

function portNumber(port: Port) {
  return port.name.match(/[0-9]+(?:\/[0-9]+)*/)?.[0] || port.name
}

function categoryLabel(device: Device) {
  const type = device.type.toLowerCase()
  if (type.includes("switch")) return "SWITCH / DENSE ACCESS"
  if (type.includes("router")) return "ROUTER / WAN EDGE"
  if (type.includes("firewall")) return "FIREWALL / SECURITY EDGE"
  if (type.includes("server")) return "SERVER / NIC PANEL"
  if (type.includes("camera")) return "CAMERA / NETWORK ENDPOINT"
  if (type.includes("access point") || type === "ap")
    return "WIRELESS / ACCESS POINT"
  return "NETWORK DEVICE"
}

function statusColor(port: Port, link?: Link) {
  if (link) return "#61c98d"
  if (port.oper === "DOWN" || port.admin === "DOWN") return "#d9646a"
  if (port.oper === "UP") return "#61c98d"
  if (port.source === "manual_fallback") return "#d4a95c"
  return "#77827f"
}

function PortSocket({
  port,
  link,
  selected,
  onSelect,
  peerName,
}: {
  port: Port
  link?: Link
  selected: boolean
  onSelect: () => void
  peerName?: string
}) {
  const state = portState(port, link)
  const color = statusColor(port, link)
  return (
    <button
      type="button"
      aria-label={`${port.name}, ${state}${
        peerName ? `, connected to ${peerName}` : ""
      }`}
      title={`${port.name}\nifIndex: ${port.ifIndex ?? "N/A"}\n${port.oper} - ${port.speed}${
        peerName ? `\nConnected: ${peerName}` : ""
      }`}
      onClick={onSelect}
      className={`device-port-socket group min-w-[62px] rounded border bg-[#1a2222] px-1.5 pb-1.5 pt-1 text-center transition hover:border-[#d4a95c99] ${
        selected ? "border-[#f1f5f4] ring-2 ring-[#61c98d]" : "border-[#56605e]"
      }`}
    >
      <span className="mx-auto mb-1 block text-[8px] font-semibold text-[#dce5e2]">
        {portNumber(port)}
      </span>
      <span className="mx-auto block h-7 w-10 overflow-hidden rounded-sm border border-[#090c0d] bg-[#070a0b] shadow-[inset_0_1px_2px_#64706c55]">
        <img
          src={plugUltraAsset}
          alt=""
          aria-hidden="true"
          className="h-full w-full rotate-180 object-contain"
        />
      </span>
      <span className="mt-1 flex items-center justify-center gap-1 font-mono text-[7px] text-[#aab5b1]">
        <span
          className="h-1.5 w-1.5 rounded-full"
          style={{ backgroundColor: color, boxShadow: `0 0 5px ${color}` }}
        />
        {link ? "USED" : port.oper === "UP" ? "UP" : "FREE"}
      </span>
      {link && (
        <span className="mt-0.5 block text-[6px] text-[#61c98d]">PLUGGED</span>
      )}
    </button>
  )
}

export default function DevicePortMap() {
  const navigate = useNavigate()
  const { deviceId } = useParams<{ deviceId: string }>()
  const [workspace, setWorkspace] = useState<Workspace>({
    devices: [],
    links: [],
  })
  const [ports, setPorts] = useState<Port[]>([])
  const [selectedPort, setSelectedPort] = useState<string | null>(null)
  const [search, setSearch] = useState("")
  const [filter, setFilter] = useState("ALL")
  const [deviceLoading, setDeviceLoading] = useState(true)
  const [interfacesLoading, setInterfacesLoading] = useState(true)
  const [connectionsLoading, setConnectionsLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [retryToken, setRetryToken] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [panelZoom, setPanelZoom] = useState(100)

  const device = workspace.devices.find((item) => item.id === deviceId)
  const linksForDevice = useMemo(
    () =>
      workspace.links.filter(
        (link) => link.from === deviceId || link.to === deviceId,
      ),
    [workspace.links, deviceId],
  )
  const linkForPort = (port: string) =>
    linksForDevice.find((link) =>
      link.from === deviceId ? link.fromPort === port : link.toPort === port,
    )
  const peerForLink = (link: Link) => {
    const peerId = link.from === deviceId ? link.to : link.from
    const peer = workspace.devices.find((item) => item.id === peerId)
    return {
      device: peer,
      port: link.from === deviceId ? link.toPort : link.fromPort,
    }
  }

  useEffect(() => {
    let active = true
    let cached: Workspace = { devices: [], links: [] }
    try {
      cached = JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}")
    } catch {
      cached = { devices: [], links: [] }
    }
    cached.devices = Array.isArray(cached.devices) ? cached.devices : []
    cached.links = Array.isArray(cached.links) ? cached.links : []
    setWorkspace(cached)
    setDeviceLoading(false)
    setConnectionsLoading(false)
    const requestedPort = new URLSearchParams(window.location.search).get(
      "port",
    )
    if (requestedPort) setSelectedPort(requestedPort)
    const current = cached.devices.find((item: Device) => item.id === deviceId)
    if (!current) {
      setInterfacesLoading(false)
      setError("Device is not present in the manual topology workspace.")
      return () => {
        active = false
      }
    }
    if (!current.backendId) {
      const manualPorts = (current.ports || []).map((name) =>
        manualPort(name, current),
      )
      setPorts(manualPorts.length ? manualPorts : [fallbackPort(current)])
      setInterfacesLoading(false)
      setRefreshing(false)
      return () => {
        active = false
      }
    }

    const hasExistingData = ports.length > 0
    setInterfacesLoading(!hasExistingData)
    setRefreshing(hasExistingData)
    setError(null)
    const withTimeout = <T,>(request: Promise<T>, fallback: T, ms = 8000) =>
      Promise.race([
        request,
        new Promise<T>((resolve) => window.setTimeout(() => resolve(fallback), ms)),
      ])

    void Promise.all([
      withTimeout(getSNMPInterfaces(current.backendId), []),
      withTimeout(getLatestInterfaces(current.backendId), []),
    ]).then(([snmp, latest]) => {
      if (!active) return
      const rows = (snmp.length ? snmp : latest).map((item, index) =>
        normalizePort(item, index, snmp.length ? "snmp" : "latest"),
      )
      if (rows.length) {
        rows.sort(naturalPortSort)
        setPorts(rows.length ? rows : [fallbackPort(current)])
        setError(null)
      } else {
        setPorts([fallbackPort(current)])
        setError("No live interface data returned. Showing a fallback port; use Retry to check again.")
      }
      setInterfacesLoading(false)
      setRefreshing(false)
    })
    return () => {
      active = false
    }
  }, [deviceId, retryToken])

  const classified = useMemo(() => {
    const sorted = [...ports].sort(naturalPortSort)
    return {
      physical: sorted.filter(
        (port) => !isLogical(port) && !isManagement(port) && !isUplink(port),
      ),
      uplinks: sorted.filter((port) => !isLogical(port) && isUplink(port)),
      management: sorted.filter(
        (port) => !isLogical(port) && isManagement(port),
      ),
      logical: sorted.filter(isLogical),
    }
  }, [ports])
  const matchesPort = (port: Port) => {
    const link = linkForPort(port.name)
    const peer = link ? peerForLink(link) : null
    const state = portState(port, link)
    const haystack =
      `${port.name} ${port.ifIndex ?? ""} ${port.description} ${port.ip} ${peer?.device?.name || ""} ${peer?.device?.ipAddress || ""} ${peer?.port || ""}`.toLowerCase()
    return (
      (!search || haystack.includes(search.toLowerCase())) &&
      (filter === "ALL" ||
        (filter === "USED" && !!link) ||
        (filter === "FREE" && !link) ||
        (filter === "UP" && port.oper === "UP") ||
        (filter === "DOWN" && port.oper === "DOWN") ||
        (filter === "ISSUES" &&
          ["DOWN", "ADMIN DOWN", "UNKNOWN"].includes(state)))
    )
  }
  const visiblePorts = ports.filter(matchesPort)
  const visiblePhysical = classified.physical.filter(matchesPort)
  const selected = ports.find((port) => port.name === selectedPort) || null
  const selectedLink = selected ? linkForPort(selected.name) : undefined
  const selectedPeer = selectedLink ? peerForLink(selectedLink) : null
  const used = ports.filter((port) => linkForPort(port.name)).length

  const persistLinks = async (links: Link[]) => {
    const next = { ...workspace, links }
    setWorkspace(next)
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
    try {
      const snapshot = await getLatestManualTopologySnapshot()
      if (snapshot) await updateManualTopologySnapshot(snapshot.id, next)
    } catch {
      setError("Local link state saved, but snapshot sync failed.")
    }
  }

  if (deviceLoading)
    return (
      <main className="min-h-full bg-[#0b0f11] p-6 text-sm text-[#d4a95c]">
        LOADING DEVICE PORTS...
      </main>
    )
  if (!device)
    return (
      <main className="min-h-full bg-[#0b0f11] p-6 text-sm">
        {error || "Device not found."}
      </main>
    )
  const dataLoading = interfacesLoading && ports.length === 0
  const physicalBanks = Array.from(
    { length: Math.ceil(visiblePhysical.length / 12) },
    (_, bank) => visiblePhysical.slice(bank * 12, bank * 12 + 12),
  )
  return (
    <main className="device-port-map-page min-h-full bg-[#0b0f11] p-4 text-[#e5e7e7] sm:p-6">
      <button
        className="tool mb-4"
        onClick={() => navigate("/manual-topology")}
      >
        ← BACK TO MANUAL TOPOLOGY
      </button>
      <header className="rounded-xl border border-white/[.1] bg-[#11161a] p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="flex items-center gap-4">
            <div
              className="flex h-16 w-20 items-center justify-center rounded-lg border border-[#61c98d55] bg-[#17221e] text-2xl"
              style={{ color: device.tone || "#61c98d" }}
            >
              ◈
            </div>
            <div>
              <div className="font-mono text-[9px] uppercase tracking-[.2em] text-[#7f8b88]">
                Device port map
              </div>
              <h1 className="mt-1 text-2xl font-semibold">{device.name}</h1>
              <div className="font-mono text-[10px] text-[#9aa3a0]">
                {device.ipAddress || device.subtitle || "No IP"} ·{" "}
                {device.vendor || "N/A"} · {device.model || "N/A"}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span className="rounded-full border border-[#61c98d55] bg-[#61c98d12] px-3 py-1 font-mono text-[9px] text-[#61c98d]">
              {device.status?.toUpperCase() || "UNKNOWN"}
            </span>
            <span className="rounded-full border border-white/[.1] px-3 py-1 font-mono text-[9px]">
              {device.type.toUpperCase()}
            </span>
          </div>
        </div>
        <div className="mt-5 grid grid-cols-2 gap-2 sm:grid-cols-6">
          {[
            [dataLoading ? "--" : ports.length, "INTERFACES"],
            [dataLoading ? "--" : classified.physical.length, "PHYSICAL"],
            [dataLoading ? "--" : classified.uplinks.length, "HIGH SPEED"],
            [dataLoading ? "--" : classified.logical.length, "LOGICAL"],
            [dataLoading ? "--" : used, "USED"],
            [
              dataLoading
                ? "--"
                : Math.max(classified.physical.length - used, 0),
              "FREE",
            ],
          ].map(([value, label]) => (
            <div
              key={label}
              className="device-port-stat rounded border border-white/[.08] bg-[#0d1113] p-3"
            >
              <div className="text-xl text-[#61c98d]">{value}</div>
              <div className="font-mono text-[8px] text-[#7f8b88]">{label}</div>
            </div>
          ))}
        </div>
      </header>
      {error && (
        <div className="mt-3 flex flex-wrap items-center justify-between gap-3 rounded border border-[#d4a95c66] bg-[#d4a95c12] p-3 text-xs text-[#d4a95c]">
          <span>{error}</span>
          {error === "UNABLE TO LOAD PORTS" && (
            <button
              className="tool border-[#d4a95c99] text-[#f0d28a]"
              onClick={() => setRetryToken((value) => value + 1)}
            >
              RETRY
            </button>
          )}
        </div>
      )}
      <section className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1fr)_320px]">
        <div className="rounded-xl border border-white/[.1] bg-[#11161a] p-5">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <div className="font-mono text-[10px] uppercase tracking-[.16em]">
                Device front panel
              </div>
              <div className="mt-1 text-[10px] text-[#7f8b88]">
                Real interfaces only. Click a port for details.
              </div>
            </div>
            <div className="font-mono text-[9px] text-[#7f8b88]">
              {dataLoading
                ? "LOADING DEVICE PORTS..."
                : `${ports.length} INTERFACES`}
            </div>
          </div>
          <div className="mt-5 overflow-x-auto rounded-xl border border-white/[.1] bg-[#0d1113] p-4">
            <div
              className="device-front-panel mx-auto min-w-[720px] rounded-lg border border-[#4b5752] bg-[linear-gradient(145deg,#303936_0%,#111716_42%,#252d2b_100%)] p-4 shadow-[inset_0_1px_0_#ffffff18,0_16px_36px_#000b]"
              style={{
                width: `${Math.min(100, Math.max(70, panelZoom * 0.82))}%`,
              }}
            >
              <div className="mb-3 flex items-center justify-between border-b border-[#080b0c] pb-3">
                <div>
                  <div className="font-sans text-xl font-black tracking-[.18em] text-[#d9dfdc] drop-shadow-[0_1px_1px_#000]">
                    {device.vendor || "AGNIGATE"}
                  </div>
                  <div className="mt-0.5 font-mono text-[8px] uppercase tracking-[.2em] text-[#77827f]">
                    {categoryLabel(device)}
                  </div>
                </div>
                <div className="text-right font-mono text-[8px] uppercase text-[#aab5b1]">
                  <div>{device.name}</div>
                  <div className="mt-1 text-[#61c98d]">
                    {device.status?.toUpperCase() || "UNKNOWN"} / LIVE PORT MAP
                  </div>
                </div>
              </div>
              <div className="mb-3 flex items-center gap-3 rounded border border-[#080b0c] bg-[#0a0d0e] px-3 py-2 shadow-[inset_0_1px_3px_#000]">
                <span className="h-2 w-2 rounded-full bg-[#61c98d] shadow-[0_0_8px_#61c98d]" />
                <span className="font-mono text-[8px] uppercase tracking-widest text-[#aab5b1]">
                  {device.ipAddress || device.subtitle || "NO MANAGEMENT IP"}
                </span>
                <span className="ml-auto font-mono text-[8px] text-[#77827f]">
                  {ports.length} INTERFACES / {used} CONNECTED
                </span>
              </div>
              {connectionsLoading && !dataLoading && (
                <div className="mb-2 text-[9px] font-mono uppercase text-[#d4a95c]">
                  ● LOADING CONNECTIONS...
                </div>
              )}
              {refreshing && (
                <div className="mb-3 text-[9px] font-mono uppercase text-[#d4a95c]">
                  ● REFRESHING PORT STATUS...
                </div>
              )}
              {dataLoading ? (
                <div className="space-y-3" aria-label="Loading device ports">
                  <div className="font-mono text-[10px] uppercase text-[#d4a95c]">
                    ● LOADING DEVICE PORTS...
                  </div>
                  <div className="grid grid-cols-6 gap-2 sm:grid-cols-12">
                    {Array.from({ length: 24 }, (_, index) => (
                      <span
                        key={index}
                        className="h-12 rounded border border-[#4b575255] bg-[#141b1a]"
                      />
                    ))}
                  </div>
                </div>
              ) : (
                <>
                  {physicalBanks.map((bank, index) => (
                    <div
                      key={`bank-${index}`}
                      className="mb-3 rounded border border-[#52605a] bg-[#151d1c] p-2"
                    >
                      <div className="mb-2 font-mono text-[8px] uppercase text-[#77827f]">
                        RJ45 BANK {index + 1}
                      </div>
                      <div className="grid grid-cols-6 gap-2 sm:grid-cols-12">
                        {bank.map((port) => {
                          const link = linkForPort(port.name)
                          return (
                            <PortSocket
                              key={port.name}
                              port={port}
                              link={link}
                              selected={selectedPort === port.name}
                              onSelect={() => setSelectedPort(port.name)}
                              peerName={
                                link
                                  ? peerForLink(link).device?.name
                                  : undefined
                              }
                            />
                          )
                        })}
                      </div>
                    </div>
                  ))}
                  {classified.uplinks.filter(matchesPort).length > 0 && (
                    <div className="device-sfp-bay mt-4 rounded border border-[#8a6b35] bg-[#241f16] p-3">
                      <div className="mb-2 font-mono text-[8px] uppercase tracking-widest text-[#f0d28a]">
                        SFP / HIGH-SPEED UPLINK BAY
                      </div>
                      <div className="device-sfp-bay flex flex-wrap gap-2">
                        {classified.uplinks.filter(matchesPort).map((port) => {
                          const link = linkForPort(port.name)
                          return (
                            <PortSocket
                              key={port.name}
                              port={port}
                              link={link}
                              selected={selectedPort === port.name}
                              onSelect={() => setSelectedPort(port.name)}
                              peerName={
                                link
                                  ? peerForLink(link).device?.name
                                  : undefined
                              }
                            />
                          )
                        })}
                      </div>
                    </div>
                  )}
                  {classified.management.filter(matchesPort).length > 0 && (
                    <div className="mt-4 rounded border border-[#53636a] bg-[#172025] p-3">
                      <div className="mb-2 font-mono text-[8px] uppercase tracking-widest text-[#aab5b1]">
                        DEDICATED MANAGEMENT
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {classified.management
                          .filter(matchesPort)
                          .map((port) => (
                            <PortSocket
                              key={port.name}
                              port={port}
                              link={linkForPort(port.name)}
                              selected={selectedPort === port.name}
                              onSelect={() => setSelectedPort(port.name)}
                            />
                          ))}
                      </div>
                    </div>
                  )}
                </>
              )}
              <div className="mt-4 flex items-center justify-between border-t border-white/[.1] pt-3">
                <span className="font-mono text-[8px] text-[#77827f]">
                  PHYSICAL PORT VIEW /{" "}
                  {dataLoading ? "--" : classified.physical.length}
                </span>
                <div className="flex items-center gap-1">
                  <button
                    className="tool h-7 px-2"
                    aria-label="Zoom out front panel"
                    onClick={() =>
                      setPanelZoom((value) => Math.max(75, value - 10))
                    }
                  >
                    -
                  </button>
                  <span className="min-w-12 text-center font-mono text-[9px] text-[#d4a95c]">
                    {panelZoom}%
                  </span>
                  <button
                    className="tool h-7 px-2"
                    aria-label="Zoom in front panel"
                    onClick={() =>
                      setPanelZoom((value) => Math.min(200, value + 10))
                    }
                  >
                    +
                  </button>
                </div>
              </div>
            </div>
          </div>
          <div className="mt-5 flex flex-wrap gap-2">
            {[
              ["ALL", "ALL"],
              ["USED", "USED"],
              ["FREE", "FREE"],
              ["UP", "UP"],
              ["DOWN", "DOWN"],
              ["ISSUES", "ISSUES"],
            ].map(([value, label]) => (
              <button
                key={value}
                className={`tool ${
                  filter === value ? "border-[#61c98d] text-[#61c98d]" : ""
                }`}
                onClick={() => setFilter(value)}
              >
                {label}
              </button>
            ))}
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search port/device..."
              className="h-8 min-w-48 flex-1 rounded border border-white/[.1] bg-[#0d1113] px-2 text-[10px]"
            />
          </div>
          <div className="mt-4 overflow-x-auto rounded border border-white/[.08]">
            <table className="w-full min-w-[760px] text-left text-[10px]">
              <thead className="device-port-table-head bg-[#18201f] font-mono text-[8px] uppercase text-[#7f8b88]">
                <tr>
                  {[
                    "PORT",
                    "STATUS",
                    "SPEED",
                    "USED",
                    "CONNECTED DEVICE",
                    "REMOTE PORT",
                    "VERIFICATION",
                  ].map((label) => (
                    <th key={label} className="p-3">
                      {label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {visiblePorts.map((port) => {
                  const link = linkForPort(port.name)
                  const peer = link ? peerForLink(link) : null
                  return (
                    <tr
                      key={`row-${port.name}`}
                      onClick={() => setSelectedPort(port.name)}
                      className={`cursor-pointer border-t border-white/[.06] hover:bg-white/[.03] ${
                        selectedPort === port.name ? "bg-[#294b4322]" : ""
                      }`}
                    >
                      <td className="p-3 font-mono">{port.name}</td>
                      <td className="p-3">
                        {port.oper}{" "}
                        <span className="text-[#7f8b88]">/ {port.admin}</span>
                      </td>
                      <td className="p-3">{port.speed}</td>
                      <td className="p-3">
                        {link ? (
                          <span className="text-[#61c98d]">USED</span>
                        ) : (
                          "FREE"
                        )}
                      </td>
                      <td className="p-3">
                        {peer?.device ? (
                          <button
                            className="text-[#61c98d] underline"
                            onClick={() =>
                              navigate(
                                `/manual-topology/device/${peer.device?.id}/ports`,
                              )
                            }
                          >
                            {peer.device.name}
                          </button>
                        ) : (
                          "-"
                        )}
                      </td>
                      <td className="p-3">{peer?.port || "-"}</td>
                      <td className="p-3">
                        {link ? (
                          <span className="text-[#61c98d]">
                            MANUAL / {link.status || "UNKNOWN"}
                          </span>
                        ) : (
                          "-"
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          {classified.logical.length > 0 && (
            <div className="mt-5 overflow-x-auto rounded border border-white/[.08]">
              <div className="border-b border-white/[.08] bg-[#18201f] p-3 font-mono text-[9px] uppercase tracking-widest text-[#d4a95c]">
                Logical Interfaces / Not Physical Sockets
              </div>
              <table className="w-full min-w-[700px] text-left text-[10px]">
                <tbody>
                  {classified.logical.filter(matchesPort).map((port) => (
                    <tr
                      key={`logical-${port.name}`}
                      onClick={() => setSelectedPort(port.name)}
                      className={`cursor-pointer border-t border-white/[.06] hover:bg-white/[.03] ${
                        selectedPort === port.name ? "bg-[#294b4322]" : ""
                      }`}
                    >
                      <td className="p-3 font-mono">{port.name}</td>
                      <td className="p-3 text-[#9aa3a0]">
                        {port.ifType || "logical"}
                      </td>
                      <td className="p-3">
                        {port.oper} / {port.admin}
                      </td>
                      <td className="p-3">{port.ip || "-"}</td>
                      <td className="p-3">{port.description || "-"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
        <aside className="device-port-details-panel rounded-xl border border-white/[.1] bg-[#11161a] p-5">
          <div className="font-mono text-[10px] uppercase tracking-[.16em]">
            Port details
          </div>
          {selected ? (
            <div className="mt-4 space-y-3 text-[10px]">
              <div className="text-lg font-semibold">{selected.name}</div>
              {[
                ["ifIndex", selected.ifIndex ?? "N/A"],
                ["Admin", selected.admin],
                ["Operational", selected.oper],
                ["Speed", selected.speed],
                ["MAC", selected.mac || "N/A"],
                ["IP", selected.ip || "N/A"],
                ["State", portState(selected, selectedLink)],
              ].map(([label, value]) => (
                <div
                  key={label}
                  className="device-port-detail-row flex justify-between border-b border-white/[.06] py-2"
                >
                  <span className="text-[#7f8b88]">{label}</span>
                  <span>{value}</span>
                </div>
              ))}
              {selectedPeer?.device && (
                <div className="rounded border border-[#61c98d55] bg-[#17221e] p-3">
                  <div className="font-mono text-[8px] uppercase text-[#7f8b88]">
                    Connected to
                  </div>
                  <button
                    className="mt-1 text-[#61c98d] underline"
                    onClick={() =>
                      navigate(
                        `/manual-topology/device/${selectedPeer.device?.id}/ports`,
                      )
                    }
                  >
                    {selectedPeer.device.name}
                  </button>
                  <div className="mt-1 font-mono text-[9px]">
                    Remote Port: {selectedPeer.port || "N/A"}
                  </div>
                  <div className="mt-1 text-[9px]">
                    Manual / {selectedLink?.status || "UNKNOWN"}
                  </div>
                </div>
              )}
              {selectedLink ? (
                <div className="flex gap-2">
                  <button
                    className="tool flex-1"
                    onClick={() => setSelectedPort(null)}
                  >
                    VIEW LINK
                  </button>
                  <button
                    className="tool flex-1 border-[#d9646a66] text-[#d9646a]"
                    onClick={() => {
                      if (
                        window.confirm(
                          `Remove manual connection ${device.name} / ${selected.name} to ${selectedPeer?.device?.name || "peer"}?`,
                        )
                      )
                        void persistLinks(
                          workspace.links.filter(
                            (link) => link.id !== selectedLink.id,
                          ),
                        )
                    }}
                  >
                    DISCONNECT
                  </button>
                </div>
              ) : isLogical(selected) ? (
                <div className="rounded border border-[#d4a95c55] bg-[#d4a95c0d] p-3 text-[9px] text-[#d4a95c]">
                  Logical interface. Physical connect action is not available
                  here.
                </div>
              ) : (
                <button
                  className="tool w-full border-[#61c98d66] text-[#61c98d]"
                  onClick={() =>
                    navigate(
                      `/manual-topology?connectDevice=${encodeURIComponent(device.id)}&connectPort=${encodeURIComponent(selected.name)}`,
                    )
                  }
                >
                  CONNECT
                </button>
              )}
            </div>
          ) : (
            <div className="mt-4 text-xs text-[#7f8b88]">
              Select a port to inspect status, peer, and available actions.
            </div>
          )}
        </aside>
      </section>
    </main>
  )
}
