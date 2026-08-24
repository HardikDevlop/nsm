import { useEffect, useMemo, useRef, useState } from "react"
import GlassCard from "../components/GlassCard"
import {
  createManualTopologySnapshot,
  getLatestInterfaces,
  getLatestManualTopologySnapshot,
  getSNMPInterfaces,
  listSNMPDevicesOptimized,
  reconcileManualTopology,
  resolveManualTopologyChange,
  type ManualTopologyChange,
  type SNMPDeviceListItem,
  updateDevice,
  updateManualTopologySnapshot,
} from "../lib/api"

type Device = {
  id: string
  name: string
  subtitle: string
  type: string
  tone: string
  x: number
  y: number
  backendId?: number
  ports?: string[]
  portStatuses?: Record<string, string>
  status?: string
  ipAddress?: string
  macAddress?: string
  location?: string
  width?: number
  height?: number
}
type Link = {
  id: string
  from: string
  to: string
  label: string
  fromPort?: string
  toPort?: string
}
type Workspace = { devices: Device[] links: Link[] }

const portLabel = (interfaceName: string, _index?: number) =>
  interfaceName || "INTERFACE NOT SET"

const isVirtualPort = (name: string, type?: string) => {
  const normalizedType = (type ?? "").toLowerCase().replace(/[\s._/-]+/g, "")
  const physicalTypes = new Set([
    "6",
    "ethernetcsmacd",
    "ethernet",
    "fastethernet",
    "gigabitethernet",
    "tengigabitethernet",
  ])
  if (normalizedType && !physicalTypes.has(normalizedType)) return true

  const value = `${name} ${type ?? ""}`.toLowerCase().replace(/[\s._/-]+/g, "")
  return [
    "vlan",
    "loopback",
    "null",
    "tunnel",
    "tun",
    "bridge",
    "br",
    "bond",
    "portchannel",
    "po",
    "stack",
    "stackport",
    "stacksub",
    "nve",
    "vxlan",
    "mgmt",
    "management",
    "svi",
    "irb",
    "overlay",
    "virtual",
    "cpu",
    "internal",
  ].some((prefix) => value.startsWith(prefix) || value.includes(prefix))
}

const STORAGE_KEY = "nms.manual-topology.workspace.v2"
const LEGACY_STORAGE_KEY = "nms.manual-topology.workspace.v1"
const tones = [
  "#f97316",
  "#ff3366",
  "#00d4ff",
  "#38bdf8",
  "#a78bfa",
  "#00ff88",
  "#facc15",
]

const initialWorkspace: Workspace = {
  devices: [
    {
      id: "isp",
      name: "INTERNET / ISP",
      subtitle: "WAN uplink",
      type: "Internet",
      tone: "#f97316",
      x: 480,
      y: 54,
    },
    {
      id: "fw-01",
      name: "FIREWALL FW-01",
      subtitle: "10.0.0.1/30",
      type: "Firewall",
      tone: "#ff3366",
      x: 480,
      y: 154,
    },
    {
      id: "cs-01",
      name: "CORE SWITCH CS-01",
      subtitle: "VLAN 99 · 10.0.0.2",
      type: "Switch",
      tone: "#00d4ff",
      x: 480,
      y: 254,
    },
    {
      id: "as-01",
      name: "ACCESS SW AS-01",
      subtitle: "10.0.0.11",
      type: "Switch",
      tone: "#38bdf8",
      x: 270,
      y: 374,
    },
    {
      id: "as-02",
      name: "ACCESS SW AS-02",
      subtitle: "10.0.0.12",
      type: "Switch",
      tone: "#38bdf8",
      x: 690,
      y: 374,
    },
    {
      id: "users",
      name: "USERS / WI-FI",
      subtitle: "VLAN 10 / 20",
      type: "Endpoint",
      tone: "#a78bfa",
      x: 270,
      y: 494,
    },
    {
      id: "servers",
      name: "SERVERS / PRINTERS",
      subtitle: "VLAN 30 / 40",
      type: "Server",
      tone: "#00ff88",
      x: 690,
      y: 494,
    },
  ],
  links: [
    { id: "l1", from: "isp", to: "fw-01", label: "WAN" },
    { id: "l2", from: "fw-01", to: "cs-01", label: "LAN" },
    { id: "l3", from: "cs-01", to: "as-01", label: "TRUNK" },
    { id: "l4", from: "cs-01", to: "as-02", label: "TRUNK" },
    { id: "l5", from: "as-01", to: "users", label: "ACCESS" },
    { id: "l6", from: "as-02", to: "servers", label: "ACCESS" },
  ],
}

const checklistItems = [
  "Every device has a hostname and management IP",
  "Both interface names are written on every link",
  "Trunk and access links are clearly identified",
  "VLAN, subnet and gateway details are verified",
  "Backup links and single points of failure are marked",
]

function loadWorkspace(): Workspace {
  try {
    window.localStorage.removeItem(LEGACY_STORAGE_KEY)
    const saved = window.localStorage.getItem(STORAGE_KEY)
    if (saved) return normalizeWorkspace(JSON.parse(saved))
  } catch {
    /* Local persistence is optional. */
  }
  return { devices: [], links: [] }
}

function normalizeWorkspace(value: unknown): Workspace {
  const rawWorkspace = (value ?? {}) as {
    devices?: unknown[]
    links?: Link[]
  }
  const devices = Array.isArray(rawWorkspace.devices)
    ? rawWorkspace.devices.map((item, index) => {
        const raw = (item ?? {}) as Record<string, unknown>
        const name = String(
          raw.hostname ??
            raw.name ??
            raw.ipAddress ??
            raw.ip_address ??
            raw.subtitle ??
            `DEVICE ${index + 1}`,
        )
        const subtitle = String(
          raw.subtitle ?? raw.ipAddress ?? raw.ip_address ?? "",
        )
        return { ...raw, name, subtitle } as unknown as Device
      })
    : []
  return {
    devices,
    links: Array.isArray(rawWorkspace.links) ? rawWorkspace.links : [],
  }
}

function DeviceGlyph({ type, tone }: { type: string; tone: string }) {
  const normalizedType = type.toLowerCase()
  const common = {
    fill: "none",
    stroke: tone,
    strokeWidth: 1.5,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
  }

  if (normalizedType.includes("firewall")) {
    return <path {...common} d="M24 16l6 2v4c0 4-2.5 6.5-6 8-3.5-1.5-6-4-6-8v-4l6-2z" />
  }
  if (normalizedType.includes("nvr") || normalizedType.includes("dvr") || normalizedType.includes("video recorder")) {
    return (
      <g {...common}>
        <rect x="17" y="19" width="14" height="10" rx="1.5" />
        <path d="M20 22h2M20 26h2M26 22h2M26 26h2" />
        <path d="M23 22l3 2-3 2v-4z" fill={tone} stroke="none" />
      </g>
    )
  }
  if (normalizedType.includes("camera")) {
    return <g {...common}><path d="M18 21h2l1.5-2h5l1.5 2h2v7H18v-7z" /><circle cx="24.5" cy="24.5" r="2.2" /></g>
  }
  if (normalizedType.includes("access") || normalizedType.includes("wifi")) {
    return <g {...common}><path d="M18 22a8.5 8.5 0 0112 0" /><path d="M20.5 24.5a5 5 0 017 0" /><path d="M23 27a1.5 1.5 0 012 0" /></g>
  }
  if (normalizedType.includes("router")) {
    return <g {...common}><rect x="18" y="22" width="12" height="6" rx="1.5" /><path d="M21 22v-3M27 22v-3M20.5 25h.1M23.5 25h.1M26.5 25h.1" /></g>
  }
  if (normalizedType.includes("switch")) {
    return <g {...common}><rect x="17" y="21" width="14" height="7" rx="1.5" /><path d="M20 24h.1M23 24h.1M26 24h.1M29 24h.1" /></g>
  }
  if (normalizedType.includes("server")) {
    return <g {...common}><rect x="18" y="18" width="12" height="4" rx="1" /><rect x="18" y="24" width="12" height="4" rx="1" /><path d="M21 20h.1M21 26h.1M24 20h4M24 26h4" /></g>
  }
  if (normalizedType.includes("internet") || normalizedType.includes("isp")) {
    return <circle {...common} cx="24" cy="24" r="7" />
  }
  return <g {...common}><rect x="18" y="19" width="12" height="9" rx="1.5" /><path d="M22 30h4M20 32h8" /></g>
}

function wrapDeviceName(name: string, maxChars: number) {
  const words = name.trim().split(/\s+/).filter(Boolean)
  if (!words.length) return ["DEVICE"]

  const lines: string[] = []
  let current = ""
  words.forEach((word) => {
    const next = current ? `${current} ${word}` : word
    if (current && next.length > maxChars) {
      lines.push(current)
      current = word
    } else {
      current = next
    }
  })
  if (current) lines.push(current)
  return lines.length > 2
    ? [lines[0], `${lines.slice(1).join(" ").slice(0, maxChars - 1)}…`]
    : lines
}

function NodeCard({
  device,
  selected,
  onClick,
  expanded,
  onTogglePorts,
  onPortClick,
  onPortPointerDown,
  onDragStart,
  onResizeStart,
  sourcePort,
  hovered,
  onHoverChange,
  showTargetPorts,
  warning,
}: {
  device: Device
  selected: boolean
  onClick: () => void
  expanded: boolean
  onTogglePorts: () => void
  onPortClick: (port: string) => void
  onPortPointerDown: (port: string) => void
  onDragStart: (event: React.PointerEvent<SVGGElement>) => void
  onResizeStart: (event: React.PointerEvent<SVGGElement>) => void
  sourcePort: { deviceId: string port: string } | null
  hovered: boolean
  onHoverChange: (hovered: boolean) => void
  showTargetPorts: boolean
  warning: boolean
}) {
  const ports = Array.isArray(device.ports) ? device.ports : ["interface-1"]
  const width = device.width ?? 210
  const height = device.height ?? 68
  const interfacePanelWidth = Math.max(width, 320)
  const interfaceColumnWidth = (interfacePanelWidth - 18) / 2
  const portRows = Math.ceil(ports.length / 2)
  const panelHeight = ports.length > 0 ? portRows * 17 + 12 : 32
  const showPorts = expanded || showTargetPorts
  const portStatus = (port: string) => {
    const status = device.portStatuses?.[port]?.toLowerCase()
    return status === "up" || status === "down" ? status : ""
  }
  const statusColor = (port: string) =>
    portStatus(port) === "up"
      ? "#00ff88"
      : portStatus(port) === "down"
        ? "#ff3366"
        : "var(--t-muted, #8899bb)"
  const upCount = ports.filter((port) => portStatus(port) === "up").length
  const downCount = ports.filter((port) => portStatus(port) === "down").length
  const controlCenterX = width - 21
  const labelEndX = width - 39
  const nameLines = wrapDeviceName(device.name, Math.max(16, Math.floor((width - 112) / 5.6)))
  const subtitleMaxLength = Math.max(18, Math.floor((width - 58) / 5))
  const typeLabel = device.type.trim().toUpperCase() || "DEVICE"
  const typeTextLength = Math.min(58, Math.max(32, width - 108))
  const casingFill = selected ? "var(--t-card, #0f0f0f)" : "var(--t-card, #0f0f0f)"
  const bezelFill = hovered
    ? "var(--t-accent-alpha, rgba(14, 165, 233, .15))"
    : "var(--t-border-light, rgba(148, 163, 184, .08))"
  return (
    <g
      transform={`translate(${device.x - width / 2}, ${device.y - height / 2})`}
      onClick={onClick}
      onPointerDown={onDragStart}
      onMouseEnter={() => onHoverChange(true)}
      onMouseLeave={() => onHoverChange(false)}
      className="cursor-pointer"
    >
      <defs>
        <linearGradient id={`device-gloss-${device.id}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#ffffff" stopOpacity=".10" />
          <stop offset="45%" stopColor="#ffffff" stopOpacity=".03" />
          <stop offset="100%" stopColor="#000000" stopOpacity=".14" />
        </linearGradient>
      </defs>
      <rect
        x="1"
        y="1"
        width={width - 2}
        height={height - 2}
        rx="14"
        fill={casingFill}
        stroke={selected ? "var(--t-accent)" : device.tone}
        strokeWidth={selected ? 2.5 : 1.2}
        strokeOpacity=".95"
        filter="url(#topologyGlow)"
      />
      <rect
        x="1"
        y="1"
        width={width - 2}
        height={height - 2}
        rx="14"
        fill={`url(#device-gloss-${device.id})`}
        opacity=".9"
      />
    
      <rect x="9" y="1" width={width - 10} height="6" rx="3" fill={bezelFill} />
      
      <circle cx="24" cy="24" r="10" fill={device.tone} fillOpacity=".14" stroke={device.tone} />
      <DeviceGlyph type={device.type} tone={device.tone} />
      <text
        x="42"
        y="24"
        fill="var(--t-text, var(--t-text, #e2e8f5))"
        fontSize="8.6"
        fontWeight="700"
        letterSpacing=".3"
      >
        {nameLines.map((line, index) => (
          <tspan key={`${line}-${index}`} x="42" dy={index === 0 ? 0 : 12}>
            {line}
          </tspan>
        ))}
      </text>
      <text
        x="42"
        y={nameLines.length > 1 ? 52 : 41}
        fill="var(--t-muted, var(--t-muted, #8899bb))"
        fontSize="7.4"
        fontFamily="JetBrains Mono, monospace"
      >
        {device.subtitle.slice(0, subtitleMaxLength)}
      </text>
      <text
        x={labelEndX}
        y="24"
        textAnchor="end"
        fill={device.tone}
        fontSize={width < 250 ? "5.8" : "6.3"}
        fontWeight="800"
        fontFamily="JetBrains Mono, monospace"
        letterSpacing=".45"
        textLength={typeTextLength}
        lengthAdjust="spacingAndGlyphs"
      >
        {typeLabel}
      </text>
      <g
        onPointerDown={(event) => event.stopPropagation()}
        onClick={(event) => {
          event.stopPropagation()
          onTogglePorts()
        }}
      >
        <rect
          x={width - 33}
          y="10"
          width="24"
          height="24"
          rx="7"
          fill={expanded ? "var(--t-accent-alpha, rgba(34, 211, 238, .22))" : "var(--t-card-alpha, rgba(30, 41, 59, .86))"}
          stroke={expanded ? "var(--t-accent-border, rgba(34, 211, 238, .7))" : "var(--t-border-alpha, rgba(148, 163, 184, .22))"}
          strokeWidth="1"
        />
        <circle
          cx={controlCenterX}
          cy="22"
          r="8"
          fill={expanded ? "var(--t-accent-alpha, rgba(34, 211, 238, .1))" : "var(--t-bg, rgba(15, 23, 42, .46))"}
        />
        <path
          d={expanded
            ? `M${controlCenterX - 4} 23l4-4 4 4`
            : `M${controlCenterX - 4} 21l4 4 4-4`}
          fill="none"
          stroke={expanded ? "#67e8f9" : "var(--t-accent)"}
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </g>
      {warning && (
        <g
          transform={`translate(${width - 61}, 10)`}
          pointerEvents="none"
        >
          <title>LIVE TOPOLOGY CHANGE DETECTED</title>
          <circle cx="11" cy="11" r="10" fill="#ff3366" opacity=".18">
            <animate
              attributeName="opacity"
              values=".18;.5;.18"
              dur="1.4s"
              repeatCount="indefinite"
            />
          </circle>
          <circle cx="11" cy="11" r="7" fill="#ff3366" />
          <text
            x="11"
            y="15"
            textAnchor="middle"
            fill="#101318"
            fontSize="11"
            fontWeight="800"
          >
            !
          </text>
        </g>
      )}
      {showPorts && (
        <g
          transform={`translate(0, ${height + 6})`}
          onPointerDown={(event) => event.stopPropagation()}
          onClick={(event) => event.stopPropagation()}
        >
          <rect
            width={interfacePanelWidth}
            height={panelHeight}
            rx="10"
            fill="var(--t-card, rgba(15, 23, 42, .98))"
            stroke="var(--t-accent-border, rgba(34, 211, 238, .48))"
            strokeWidth="1.2"
          />
          {ports.length > 0 ? (
            ports.map((port, index) => {
              const column = index % 2
              const row = Math.floor(index / 2)
              const active =
                sourcePort?.deviceId === device.id && sourcePort.port === port
              return (
                <g
                  key={port}
                  transform={`translate(${6 + column * interfaceColumnWidth}, ${7 + row * 17})`}
                  onPointerDown={(event) => {
                    event.stopPropagation()
                    onPortPointerDown(port)
                  }}
                  onClick={() => onPortClick(port)}
                >
                  <rect
                    width={interfaceColumnWidth - 4}
                    height="14"
                    rx="3"
                    fill={active ? "rgba(0,255,136,.16)" : "var(--t-bg)"}
                    stroke={active ? "#00ff88" : "var(--t-border-light)"}
                  />
                  {active || portStatus(port) ? (
                    <circle
                      cx="7"
                      cy="7"
                      r="2"
                      fill={active ? "#00ff88" : statusColor(port)}
                    />
                  ) : null}
                  <text
                    x="12"
                    y="10"
                    fill={active ? "#00ff88" : "var(--t-muted)"}
                    fontSize="6.5"
                    fontFamily="JetBrains Mono, monospace"
                  >
                    {portLabel(port, index)}
                  </text>
                </g>
              )
            })
          ) : (
            <text
              x="10"
              y="20"
              fill="var(--t-muted)"
              fontSize="9"
              fontFamily="JetBrains Mono, monospace"
            >
              NO PHYSICAL INTERFACES FOUND
            </text>
          )}
        </g>
      )}
      {hovered && !showPorts && ports.length > 0 && (
        <g transform={`translate(0, ${height + 6})`} pointerEvents="none">
          <rect
            width={width}
            height="72"
            rx="8"
            fill="var(--t-card, #101318)"
            stroke="var(--t-accent)"
            strokeOpacity=".65"
          />
          <text
            x="8"
            y="14"
            fill="var(--t-muted)"
            fontSize="8"
            fontWeight="700"
            fontFamily="JetBrains Mono, monospace"
          >
            INTERFACES · UP / DOWN
          </text>
          <g transform="translate(8, 25)">
            <circle cx="4" cy="8" r="4" fill="#00ff88">
              <animate
                attributeName="opacity"
                values="1;.3;1"
                dur="1.2s"
                repeatCount="indefinite"
              />
            </circle>
            <text x="14" y="6" fill="#00ff88" fontSize="8" fontWeight="700">
              UP
            </text>
            <text
              x="14"
              y="20"
              fill="var(--t-text)"
              fontSize="14"
              fontWeight="700"
              fontFamily="JetBrains Mono, monospace"
            >
              {upCount}
            </text>
          </g>
          <g transform={`translate(${width / 2 - 20}, 25)`}>
            <circle cx="4" cy="8" r="4" fill="#ff3366" />
            <text x="14" y="6" fill="#ff3366" fontSize="8" fontWeight="700">
              DOWN
            </text>
            <text
              x="14"
              y="20"
              fill="var(--t-text)"
              fontSize="14"
              fontWeight="700"
              fontFamily="JetBrains Mono, monospace"
            >
              {downCount}
            </text>
          </g>
        </g>
      )}
      <g
        onPointerDown={(event) => {
          event.stopPropagation()
          onResizeStart(event)
        }}
      >
        <path
          d={`M${width - 14} ${height - 7}l7-7M${width - 8} ${height - 7}l7-7`}
          stroke="var(--t-accent)"
          strokeWidth="1.5"
        />
        <rect
          x={width - 22}
          y={height - 22}
          width="22"
          height="22"
          fill="transparent"
        />
      </g>
    </g>
  )
}

export default function ManualTopology() {
  const [workspace, setWorkspace] = useState<Workspace>(() => loadWorkspace())
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [connectFrom, setConnectFrom] = useState<string | null>(null)
  const [connectMode, setConnectMode] = useState(false)
  const [sourcePort, setSourcePort] = useState<{
    deviceId: string
    port: string
  } | null>(null)
  const [expandedDeviceId, setExpandedDeviceId] = useState<string | null>(null)
  const [hoveredDeviceId, setHoveredDeviceId] = useState<string | null>(null)
  const [connectionPointer, setConnectionPointer] = useState<{
    x: number
    y: number
  } | null>(null)
  const [selectedLinkId, setSelectedLinkId] = useState<string | null>(null)
  const [realDevices, setRealDevices] = useState<SNMPDeviceListItem[]>([])
  const [realDeviceId, setRealDeviceId] = useState("")
  const [portsLoading, setPortsLoading] = useState(false)
  const [portsError, setPortsError] = useState<string | null>(null)
  const [portsReload, setPortsReload] = useState(0)
  const interfaceRefreshDevice = useRef<number | null>(null)
  const loadedInterfaceDevices = useRef(new Set<number>())
  const svgRef = useRef<SVGSVGElement | null>(null)
  const [dragState, setDragState] = useState<{
    id: string
    offsetX: number
    offsetY: number
  } | null>(null)
  const [resizeState, setResizeState] = useState<{
    id: string
    startX: number
    startY: number
    width: number
    height: number
  } | null>(null)
  const [snapshotId, setSnapshotId] = useState<number | null>(null)
  const [topologyChanges, setTopologyChanges] =
    useState<ManualTopologyChange[]>([])
  const [reconcileLoading, setReconcileLoading] = useState(false)
  const [reconcileError, setReconcileError] = useState<string | null>(null)
  const [editing, setEditing] = useState<Device | null>(null)
  const [activeView, setActiveView] = useState<"physical" | "logical">(
    "physical",
  )
  const [checked, setChecked] = useState<boolean[]>(
    checklistItems.map(() => false),
  )

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(workspace))
  }, [workspace])
  useEffect(() => {
    void getLatestManualTopologySnapshot()
      .then((snapshot) => {
        if (!snapshot) return
        setSnapshotId(snapshot.id)
        if (workspace.devices.length === 0 && snapshot.payload?.devices?.length)
          setWorkspace(normalizeWorkspace(snapshot.payload))
        setTopologyChanges(snapshot.changes ?? [])
      })
      .catch(() => undefined)
    // The local workspace remains the editing source; the server supplies its identity and alerts.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  useEffect(() => {
    if (workspace.devices.length === 0) return
    const timer = window.setTimeout(() => {
      const request = snapshotId
        ? updateManualTopologySnapshot(snapshotId, workspace)
        : createManualTopologySnapshot(workspace)
      void request
        .then((snapshot) => setSnapshotId(snapshot.id))
        .catch(() => undefined)
    }, 900)
    return () => window.clearTimeout(timer)
  }, [snapshotId, workspace])
  useEffect(() => {
    if (!snapshotId) return
    const check = () => {
      setReconcileLoading(true)
      void reconcileManualTopology(snapshotId)
        .then((result) => {
          setTopologyChanges(result.changes ?? [])
          setReconcileError(null)
        })
        .catch((error) =>
          setReconcileError(
            error instanceof Error
              ? error.message
              : "Live topology comparison unavailable",
          ),
        )
        .finally(() => setReconcileLoading(false))
    }
    check()
    const timer = window.setInterval(check, 120000)
    return () => window.clearInterval(timer)
  }, [snapshotId])
  useEffect(() => {
    void listSNMPDevicesOptimized({ page: 1, page_size: 200 })
      .then((response) => setRealDevices(response.items))
      .catch(() => setRealDevices([]))
  }, [])

  useEffect(() => {
    if (realDevices.length === 0) return
    setWorkspace((current) => ({
      ...current,
      devices: current.devices.map((device) => {
        if (!device.backendId) return device
        const real = realDevices.find((item) => item.id === device.backendId)
        if (!real || !/^device[-_]/i.test(String(device.name ?? "")))
          return device
        return {
          ...device,
          name: real.hostname || real.name || real.ip_address,
          subtitle: device.ipAddress || real.ip_address,
        }
      }),
    }))
  }, [realDevices])

  const selected = workspace.devices.find((device) => device.id === selectedId)
  const selectedPorts = Array.isArray(selected?.ports)
    ? selected.ports
    : ["interface-1"]
  const completed = checked.filter(Boolean).length
  const deviceById = useMemo(
    () => new Map(workspace.devices.map((device) => [device.id, device])),
    [workspace.devices],
  )
  const interfacePoint = (deviceId: string, rawPort: string) => {
    const device = deviceById.get(deviceId)
    if (!device) return null
    const ports =
      Array.isArray(device.ports) && device.ports.length > 0
        ? device.ports
        : ["interface-1"]
    const index = Math.max(0, ports.indexOf(rawPort))
    const width = device.width ?? 210
    const height = device.height ?? 68
    const panelWidth = Math.max(width, 320)
    const columnWidth = (panelWidth - 18) / 2
    return {
      x: device.x - width / 2 + 6 + (index % 2) * columnWidth + 7,
      y:
        device.y - height / 2 + height + 6 + 7 + Math.floor(index / 2) * 17 + 7,
    }
  }
  const displayPort = (deviceId: string, rawPort?: string) => {
    if (!rawPort) return "INTERFACE NOT SET"
    const ports = deviceById.get(deviceId)?.ports ?? []
    return portLabel(rawPort ?? "", Math.max(0, ports.indexOf(rawPort ?? "")))
  }

  const canvasPoint = (event: React.PointerEvent<SVGSVGElement>) => {
    const svg = svgRef.current
    const matrix = svg?.getScreenCTM()
    if (!matrix) return null
    const point = svg.createSVGPoint()
    point.x = event.clientX
    point.y = event.clientY
    const local = point.matrixTransform(matrix.inverse())
    return { x: local.x, y: local.y }
  }

  const startDrag = (
    device: Device,
    event: React.PointerEvent<SVGGElement>,
  ) => {
    const point = canvasPoint(
      event as unknown as React.PointerEvent<SVGSVGElement>,
    )
    if (!point) return
    setSelectedId(device.id)
    setDragState({
      id: device.id,
      offsetX: point.x - device.x,
      offsetY: point.y - device.y,
    })
  }

  const startResize = (
    device: Device,
    event: React.PointerEvent<SVGGElement>,
  ) => {
    const point = canvasPoint(
      event as unknown as React.PointerEvent<SVGSVGElement>,
    )
    if (!point) return
    setSelectedId(device.id)
    setResizeState({
      id: device.id,
      startX: point.x,
      startY: point.y,
      width: device.width ?? 210,
      height: device.height ?? 68,
    })
  }

  const moveCanvasItem = (event: React.PointerEvent<SVGSVGElement>) => {
    const point = canvasPoint(event)
    if (!point) return
    if (sourcePort) setConnectionPointer(point)
    if (dragState) {
      setWorkspace((current) => ({
        ...current,
        devices: current.devices.map((device) =>
          device.id === dragState.id
            ? {
                ...device,
                x: Math.max(110, Math.min(850, point.x - dragState.offsetX)),
                y: Math.max(40, Math.min(530, point.y - dragState.offsetY)),
              }
            : device,
        ),
      }))
    }
    if (resizeState) {
      setWorkspace((current) => ({
        ...current,
        devices: current.devices.map((device) =>
          device.id === resizeState.id
            ? {
                ...device,
                width: Math.max(
                  150,
                  Math.min(
                    360,
                    resizeState.width + point.x - resizeState.startX,
                  ),
                ),
                height: Math.max(
                  58,
                  Math.min(
                    180,
                    resizeState.height + point.y - resizeState.startY,
                  ),
                ),
              }
            : device,
        ),
      }))
    }
  }

  useEffect(() => {
    if (!selected?.backendId) return
    const deviceId = selected.backendId
    const forceReload = interfaceRefreshDevice.current === deviceId
    const hasStoredInterfaces =
      Array.isArray(selected.ports) && selected.ports.length > 0
    if (
      !forceReload &&
      (hasStoredInterfaces || loadedInterfaceDevices.current.has(deviceId))
    ) {
      loadedInterfaceDevices.current.add(deviceId)
      return
    }
    interfaceRefreshDevice.current = null
    let cancelled = false
    setPortsLoading(true)
    setPortsError(null)
    const loadPorts = async () => {
      try {
        let liveInterfaces = [] as Awaited<ReturnType<typeof getSNMPInterfaces>>
        try {
          liveInterfaces = await getSNMPInterfaces(selected.backendId!)
        } catch {
          // Cached polling data can still provide the complete port inventory.
        }
        let cachedInterfaces =
          [] as Awaited<ReturnType<typeof getLatestInterfaces>>
        try {
          cachedInterfaces = await getLatestInterfaces(selected.backendId!)
        } catch {
          // A live response is still useful when no cached snapshot exists.
        }
        // A populated live inventory is authoritative. Only augment a single
        // live result with cache because some agents return partial IF-MIB rows.
        const allInterfaces =
          liveInterfaces.length > 1
            ? liveInterfaces
            : [...liveInterfaces, ...cachedInterfaces]
        const seenPorts = new Set<string>()
        const portStatuses: Record<string, string> = {}
        const portNames = allInterfaces
          .map((port) => {
            const raw = port as typeof port & {
              interface?: string
              if_name?: string
              ifIndex?: number | string
              description?: string
              type?: string
              if_type?: string
              oper_status?: string
              admin_status?: string
            }
            const name =
              raw.name ||
              raw.interface ||
              raw.if_name ||
              raw.description ||
              (raw.if_index != null || raw.ifIndex != null
                ? `ifIndex ${raw.if_index ?? raw.ifIndex}`
                : "")
            if (isVirtualPort(name, raw.type || raw.if_type)) return ""
            const key = String(
              raw.if_index ?? raw.ifIndex ?? name,
            ).toLowerCase()
            if (!name || seenPorts.has(key)) return ""
            seenPorts.add(key)
            portStatuses[name] = String(
              raw.oper_status ?? raw.status ?? raw.admin_status ?? "unknown",
            ).toLowerCase()
            return name
          })
          .filter(Boolean)
        if (cancelled) return
        if (portNames.length === 0) {
          setPortsError(
            "No interface data found. Run SNMP polling/discovery for this device first.",
          )
        }
        setWorkspace((current) => ({
          ...current,
          devices: current.devices.map((device) =>
            device.id === selected.id
              ? { ...device, ports: portNames, portStatuses }
              : device,
          ),
        }))
        loadedInterfaceDevices.current.add(deviceId)
      } catch (error) {
        if (!cancelled)
          setPortsError(
            error instanceof Error ? error.message : "Unable to load ports",
          )
      } finally {
        if (!cancelled) setPortsLoading(false)
      }
    }
    void loadPorts()
    return () => {
      cancelled = true
    }
  }, [portsReload, selected?.backendId, selected?.id])

  const importRealDevice = () => {
    const raw = realDevices.find((device) => String(device.id) === realDeviceId)
    if (!raw) return
    const id = `real-${raw.id}`
    setWorkspace((current) => ({
      ...current,
      devices: current.devices.some((device) => device.id === id)
        ? current.devices
        : [
            ...current.devices,
            {
              id,
              backendId: raw.id,
              name: raw.hostname || raw.ip_address || `DEVICE ${raw.id}`,
              subtitle: raw.ip_address,
              ipAddress: raw.ip_address,
              macAddress: raw.mac_address ?? "",
              location: raw.topology_metadata?.location ?? "",
              status: raw.status,
              type: raw.hostname?.toLowerCase().includes("switch")
                ? "Switch"
                : "Network device",
              tone: "#00d4ff",
              x: 150 + (current.devices.length % 4) * 220,
              y: 120 + Math.floor(current.devices.length / 4) * 120,
            },
          ],
    }))
    setSelectedId(id)
    setRealDeviceId("")
  }

  const startNew = () => {
    const index = workspace.devices.length
    setEditing({
      id: `device-${Date.now()}`,
      name: "NEW DEVICE",
      subtitle: "Add IP / VLAN",
      ipAddress: "",
      macAddress: "",
      location: "",
      type: "Switch",
      tone: tones[index % tones.length],
      x: 150 + (index % 4) * 220,
      y: 120 + Math.floor(index / 4) * 120,
    })
    setSelectedId(null)
  }

  const startNewFromPort = () => {
    if (!sourcePort) return
    const index = workspace.devices.length
    setEditing({
      id: `device-${Date.now()}`,
      name: "NEW DEVICE",
      subtitle: "Add IP / VLAN",
      ipAddress: "",
      macAddress: "",
      location: "",
      type: "Switch",
      tone: tones[index % tones.length],
      x: 150 + (index % 4) * 220,
      y: 120 + Math.floor(index / 4) * 120,
      ports: ["Gi0/1"],
    })
    setSelectedId(null)
  }

  const editSelectedDevice = () => {
    if (!selected) return
    setEditing({
      ...selected,
      ipAddress: selected.ipAddress ?? selected.subtitle,
      macAddress: selected.macAddress ?? "",
      location: selected.location ?? "",
    })
  }

  const saveDevice = () => {
    if (!editing || !editing.name.trim()) return
    const nextDevice = {
      ...editing,
      name: editing.name.trim(),
      ipAddress: editing.ipAddress?.trim() ?? "",
      macAddress: editing.macAddress?.trim() ?? "",
      location: editing.location?.trim() ?? "",
      subtitle: editing.ipAddress?.trim() || editing.subtitle,
    }
    const autoLink =
      sourcePort &&
      !workspace.devices.some((device) => device.id === editing.id)
        ? {
            id: `link-${Date.now()}`,
            from: sourcePort.deviceId,
            to: editing.id,
            fromPort: sourcePort.port,
            toPort: nextDevice.ports?.[0] ?? "Gi0/1",
            label: `${displayPort(sourcePort.deviceId, sourcePort.port)} → ${portLabel(nextDevice.ports?.[0] ?? "Gi0/1", 0)}`,
          }
        : null
    setWorkspace((current) => ({
      ...current,
      devices: current.devices.some((device) => device.id === editing.id)
        ? current.devices.map((device) =>
            device.id === editing.id ? nextDevice : device,
          )
        : [...current.devices, nextDevice],
      links: autoLink ? [...current.links, autoLink] : current.links,
    }))
    setEditing(null)
    if (nextDevice.backendId) {
      void updateDevice(nextDevice.backendId, {
        hostname: nextDevice.name,
        ip_address: nextDevice.ipAddress,
        mac_address: nextDevice.macAddress || undefined,
        topology_metadata: {
          location: nextDevice.location || null,
        },
      }).catch(() => {
        setPortsError("Device details could not be saved to the database")
      })
    }
    if (autoLink) {
      setSourcePort(null)
      setConnectFrom(null)
      setConnectMode(false)
    }
  }

  const deleteSelected = () => {
    if (!selectedId) return
    if (!window.confirm("Remove this device and its connections?")) return
    setWorkspace((current) => ({
      devices: current.devices.filter((device) => device.id !== selectedId),
      links: current.links.filter(
        (link) => link.from !== selectedId && link.to !== selectedId,
      ),
    }))
    setSelectedId(null)
    setEditing(null)
    setConnectFrom(null)
    setConnectMode(false)
    setSourcePort(null)
  }

  const disconnectLink = (linkId: string) => {
    setWorkspace((current) => ({
      ...current,
      links: current.links.filter((link) => link.id !== linkId),
    }))
    setSelectedLinkId(null)
  }

  const resolveChange = async (
    change: ManualTopologyChange,
    action: "accept_real_change" | "keep_manual",
  ) => {
    if (!snapshotId) return
    try {
      const result = await resolveManualTopologyChange(
        snapshotId,
        change.id,
        action,
      )
      setTopologyChanges(result.changes ?? [])
      if (action === "accept_real_change" && result.payload?.devices)
        setWorkspace(result.payload)
    } catch (error) {
      setReconcileError(
        error instanceof Error
          ? error.message
          : "Unable to resolve topology change",
      )
    }
  }

  const changeDescription = (change: ManualTopologyChange) =>
    change.change_type === "CONNECTION_DISCONNECTED"
      ? "Real device connection is disconnected"
      : change.change_type === "CONNECTION_ADDED"
        ? "A new real device connection was detected"
        : change.change_type === "DEVICE_OFFLINE"
          ? "A monitored device became unreachable"
          : change.change_type === "DEVICE_ONLINE"
            ? "A monitored device came back online"
            : change.change_type

  const changeStateLabel = (state?: Record<string, unknown> | null) => {
    if (!state) return "No connection"
    if (state.status) return `Device status: ${String(state.status)}`
    return `${String(state.fromPort ?? "unknown port")} → ${String(state.toPort ?? "unknown port")}`
  }

  const deviceHasTopologyWarning = (device: Device) =>
    topologyChanges.some((change) => {
      const states = [change.expected, change.observed]
      return states.some((state) => {
        if (!state) return false
        const ids = [state.device_id, state.from, state.to]
          .filter((value) => value != null)
          .map((value) => String(value))
        return (
          ids.includes(device.id) ||
          (device.backendId != null &&
            (ids.includes(String(device.backendId)) ||
              ids.includes(`real-${device.backendId}`)))
        )
      })
    })

  const selectNode = (id: string) => {
    setSelectedId(id)
    if (!connectMode) return
    setConnectFrom(id)
  }

  const selectPort = (deviceId: string, port: string) => {
    if (!connectMode) {
      setConnectMode(true)
      setConnectFrom(deviceId)
      setConnectionPointer(interfacePoint(deviceId, port))
      return setSourcePort({ deviceId, port })
    }
    if (!sourcePort) return setSourcePort({ deviceId, port })
    if (sourcePort.deviceId === deviceId)
      return setSourcePort({ deviceId, port })
    const exists = workspace.links.some(
      (link) =>
        (link.from === sourcePort.deviceId &&
          link.to === deviceId &&
          link.fromPort === sourcePort.port &&
          link.toPort === port) ||
        (link.from === deviceId &&
          link.to === sourcePort.deviceId &&
          link.fromPort === port &&
          link.toPort === sourcePort.port),
    )
    if (!exists)
      setWorkspace((current) => ({
        ...current,
        links: [
          ...current.links,
          {
            id: `link-${Date.now()}`,
            from: sourcePort.deviceId,
            to: deviceId,
            fromPort: sourcePort.port,
            toPort: port,
            label: `${displayPort(sourcePort.deviceId, sourcePort.port)} → ${displayPort(deviceId, port)}`,
          },
        ],
      }))
    setSourcePort(null)
    setConnectFrom(null)
    setConnectMode(false)
    setConnectionPointer(null)
  }

  const beginPortConnection = (deviceId: string, port: string) => {
    if (!connectMode || !sourcePort || sourcePort.deviceId === deviceId) {
      setConnectMode(true)
      setConnectFrom(deviceId)
      setSourcePort({ deviceId, port })
      setConnectionPointer(interfacePoint(deviceId, port))
    }
  }

  return (
    <main className="min-h-full overflow-y-auto p-4 md:p-6 lg:p-8 grid-bg">
      <div className="max-w-[1500px] mx-auto space-y-6">
        <header className="flex flex-col lg:flex-row lg:items-end justify-between gap-4">
          <div>
            <div
              className="font-mono text-xs tracking-[.24em] uppercase"
              style={{ color: "var(--t-accent)" }}
            >
              Network documentation / editable workspace
            </div>
            <h1
              className="font-display text-3xl md:text-4xl font-semibold tracking-wide mt-2"
              style={{ color: "var(--t-text)" }}
            >
              Manual Topology
            </h1>
            <p
              className="font-display mt-2 max-w-2xl"
              style={{ color: "var(--t-muted)" }}
            >
              Import real devices, load their live interface names and connect
              interface-to-interface.
            </p>
          </div>
          <button
            type="button"
            onClick={startNew}
            className="px-4 py-2 rounded-lg font-mono text-xs font-semibold"
            style={{ color: "var(--t-bg)", background: "var(--t-accent)" }}
          >
            + ADD DEVICE
          </button>
        </header>

        <GlassCard className="p-4">
          <div className="flex flex-col md:flex-row md:items-center gap-3">
            <div className="flex-1">
              <div
                className="font-mono text-[10px] uppercase tracking-widest"
                style={{ color: "var(--t-muted)" }}
              >
                Import real monitored device
              </div>
              <select
                value={realDeviceId}
                onChange={(event) => setRealDeviceId(event.target.value)}
                className="mt-2 w-full rounded-md px-3 py-2 font-display text-sm outline-none"
                style={{
                  color: "var(--t-text)",
                  background: "var(--t-bg)",
                  border: "1px solid var(--t-border-alpha)",
                }}
              >
                <option value="">Select a real switch/router/firewall</option>
                {realDevices.map((device) => (
                  <option key={device.id} value={device.id}>
                    {device.hostname} · {device.ip_address}
                  </option>
                ))}
              </select>
            </div>
            <button
              type="button"
              onClick={importRealDevice}
              disabled={!realDeviceId}
              className="px-4 py-2 rounded-md font-mono text-xs"
              style={{
                color: "var(--t-bg)",
                background: "var(--t-accent)",
                opacity: realDeviceId ? 1 : 0.45,
              }}
            >
              IMPORT DEVICE + PORTS
            </button>
          </div>
          <div
            className="font-mono text-[10px] mt-2"
            style={{ color: "var(--t-muted)" }}
          >
            The device must have SNMP interface data available. Ports are loaded
            from the live monitoring API.
          </div>
        </GlassCard>

        <section className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {[
            [workspace.devices.length, "Devices"],
            [workspace.links.length, "Connections"],
            ["04", "VLANs"],
            [`${completed}/${checklistItems.length}`, "Verified"],
          ].map(([value, label]) => (
            <GlassCard key={label} className="p-4">
              <div
                className="font-mono text-2xl font-semibold"
                style={{ color: "var(--t-accent)" }}
              >
                {value}
              </div>
              <div
                className="font-mono text-[10px] uppercase tracking-widest mt-1"
                style={{ color: "var(--t-muted)" }}
              >
                {label}
              </div>
            </GlassCard>
          ))}
        </section>

        {(topologyChanges.length > 0 || reconcileError) && (
          <GlassCard className="p-5" glow="red">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-2">
              <div>
                <h2 className="font-display text-lg font-semibold text-red-400">
                  Topology change warning
                </h2>
                <p
                  className="font-mono text-[10px] mt-1"
                  style={{ color: "var(--t-muted)" }}
                >
                  {reconcileError ??
                    `${topologyChanges.length} live change${
                      topologyChanges.length === 1 ? "" : "s"
                    } detected against the saved manual baseline.`}
                </p>
              </div>
              <div
                className="font-mono text-[10px]"
                style={{
                  color: reconcileLoading ? "var(--t-accent)" : "#ff3366",
                }}
              >
                {reconcileLoading
                  ? "CHECKING LIVE TOPOLOGY..."
                  : "LIVE RECONCILIATION"}
              </div>
            </div>
            <div className="space-y-3 mt-4">
              {topologyChanges.map((change) => (
                <div
                  key={change.id}
                  className="rounded-lg p-3"
                  style={{
                    border: "1px solid rgba(255,51,102,.35)",
                    background: "rgba(255,51,102,.06)",
                  }}
                >
                  <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-red-400">⚠</span>
                        <span
                          className="font-display font-semibold"
                          style={{ color: "var(--t-text)" }}
                        >
                          {changeDescription(change)}
                        </span>
                      </div>
                      <div
                        className="font-mono text-[10px] mt-2"
                        style={{ color: "var(--t-muted)" }}
                      >
                        Previously:{" "}
                        <span style={{ color: "#ffaa00" }}>
                          {changeStateLabel(change.expected)}
                        </span>{" "}
                        · Now:{" "}
                        <span style={{ color: "#ff3366" }}>
                          {changeStateLabel(change.observed)}
                        </span>
                      </div>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <button
                        type="button"
                        onClick={() =>
                          resolveChange(change, "accept_real_change")
                        }
                        className="px-3 py-1.5 rounded-md font-mono text-[10px]"
                        style={{
                          color: "#00ff88",
                          border: "1px solid #00ff88",
                          background: "rgba(0,255,136,.08)",
                        }}
                      >
                        ACCEPT REAL CHANGE
                      </button>
                      <button
                        type="button"
                        onClick={() => resolveChange(change, "keep_manual")}
                        className="px-3 py-1.5 rounded-md font-mono text-[10px]"
                        style={{
                          color: "var(--t-accent)",
                          border: "1px solid var(--t-accent-border)",
                        }}
                      >
                        KEEP MANUAL BASELINE
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </GlassCard>
        )}

        <GlassCard className="overflow-hidden">
          <div
            className="flex flex-col md:flex-row md:items-center justify-between gap-3 px-4 md:px-6 py-4"
            style={{ borderBottom: "1px solid var(--t-border-light)" }}
          >
            <div>
              <h2
                className="font-display text-lg font-semibold"
                style={{ color: "var(--t-text)" }}
              >
                Editable topology canvas
              </h2>
              <p
                className="font-mono text-[10px] mt-1"
                style={{ color: "var(--t-muted)" }}
              >
                {connectMode
                  ? sourcePort
                    ? "NOW SELECT THE TARGET DEVICE AND CLICK ITS PORT"
                    : "SELECT A SOURCE DEVICE, THEN CLICK ITS PORT"
                  : "CLICK CHEVRON FOR INTERFACES · DRAG CARD TO MOVE · CORNER HANDLE TO RESIZE"}
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => {
                  if (connectMode) {
                    setConnectMode(false)
                    setConnectFrom(null)
                    setSourcePort(null)
                    setConnectionPointer(null)
                  } else if (selectedId) {
                    setConnectMode(true)
                    setConnectFrom(null)
                    setSourcePort(null)
                  }
                }}
                disabled={!selectedId && !connectMode}
                className="px-3 py-1.5 rounded-md font-mono text-[10px] uppercase"
                style={{
                  color: connectMode ? "#00ff88" : "var(--t-accent)",
                  border: "1px solid var(--t-accent-border)",
                  background: connectMode
                    ? "rgba(0,255,136,.1)"
                    : "transparent",
                }}
              >
                {connectMode ? (
                  "CANCEL PEN"
                ) : (
                  <span className="inline-flex items-center gap-1.5">
                    <svg
                      width="13"
                      height="13"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      aria-hidden="true"
                    >
                      <path d="M12 20h9" />
                      <path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L8 18l-4 1 1-4Z" />
                    </svg>
                    PEN CONNECT
                  </span>
                )}
              </button>
              {sourcePort && (
                <button
                  type="button"
                  onClick={() => setConnectMode(true)}
                  className="px-3 py-1.5 rounded-md font-mono text-[10px] uppercase"
                  style={{
                    color: "#00ff88",
                    border: "1px solid #00ff88",
                    background: "rgba(0,255,136,.1)",
                  }}
                >
                  DRAW CONNECTION · {sourcePort.port}
                </button>
              )}
              {selectedLinkId && (
                <button
                  type="button"
                  onClick={() => disconnectLink(selectedLinkId)}
                  className="px-3 py-1.5 rounded-md font-mono text-[10px] uppercase"
                  style={{
                    color: "#ff3366",
                    border: "1px solid #ff3366",
                    background: "rgba(255,51,102,.1)",
                  }}
                >
                  DISCONNECT SELECTED LINK
                </button>
              )}
              <button
                type="button"
                onClick={editSelectedDevice}
                disabled={!selected}
                className="px-3 py-1.5 rounded-md font-mono text-[10px] uppercase"
                style={{
                  color: "var(--t-text)",
                  border: "1px solid var(--t-border-alpha)",
                  opacity: selected ? 1 : 0.4,
                }}
              >
                EDIT CARD
              </button>
              <button
                type="button"
                onClick={deleteSelected}
                disabled={!selected}
                className="px-3 py-1.5 rounded-md font-mono text-[10px] uppercase"
                style={{
                  color: "#ff3366",
                  border: "1px solid #ff336655",
                  opacity: selected ? 1 : 0.4,
                }}
              >
                REMOVE DEVICE
              </button>
              <div
                className="flex p-1 rounded-lg"
                style={{ background: "var(--t-border-light)" }}
              >
                {(["physical", "logical"] as const).map((view) => (
                  <button
                    key={view}
                    type="button"
                    onClick={() => setActiveView(view)}
                    className="px-3 py-1.5 rounded-md font-mono text-[10px] uppercase"
                    style={{
                      color:
                        activeView === view
                          ? "var(--t-accent)"
                          : "var(--t-muted)",
                      background:
                        activeView === view
                          ? "var(--t-accent-alpha)"
                          : "transparent",
                    }}
                  >
                    {view}
                  </button>
                ))}
              </div>
            </div>
          </div>
          {activeView === "physical" ? (
            <div className="overflow-x-auto p-3 md:p-6">
              <svg
                ref={svgRef}
                viewBox="0 0 960 570"
                className="w-full min-w-[720px] h-auto grid-bg rounded-lg"
                style={{
                  touchAction: "none",
                  cursor: connectMode
                    ? "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='24' height='24'%3E%3Cpath d='M4 20l4-1L20 7l-3-3L5 16z' fill='%2300d4ff' stroke='%23000'/%3E%3C/svg%3E\") 2 22, crosshair"
                    : "default",
                }}
                onPointerMove={moveCanvasItem}
                onPointerUp={() => {
                  setDragState(null)
                  setResizeState(null)
                }}
                onPointerLeave={() => {
                  setDragState(null)
                  setResizeState(null)
                }}
                role="img"
                aria-label="Editable manual network topology"
              >
                <defs>
                  <pattern
                    id="manual-topology-grid"
                    width="24"
                    height="24"
                    patternUnits="userSpaceOnUse"
                  >
                    <path
                      d="M 24 0 L 0 0 0 24"
                      fill="none"
                      stroke="var(--t-border-light)"
                      strokeWidth=".7"
                    />
                  </pattern>
                </defs>
                <rect
                  width="960"
                  height="570"
                  fill="url(#manual-topology-grid)"
                  opacity=".7"
                />
                {workspace.devices.length === 0 && (
                  <g>
                    <text
                      x="480"
                      y="260"
                      textAnchor="middle"
                      fill="var(--t-text)"
                      fontSize="18"
                      fontWeight="700"
                    >
                      No devices added yet
                    </text>
                    <text
                      x="480"
                      y="290"
                      textAnchor="middle"
                      fill="var(--t-muted)"
                      fontSize="12"
                      fontFamily="JetBrains Mono, monospace"
                    >
                      Import a real device above or create a new card
                    </text>
                  </g>
                )}
                {workspace.links.map((link) => {
                  const from = deviceById.get(link.from)
                  const to = deviceById.get(link.to)
                  if (!from || !to) return null
                  return (
                    <g
                      key={link.id}
                      onClick={() => setSelectedLinkId(link.id)}
                      className="cursor-pointer"
                    >
                      <line
                        x1={from.x}
                        y1={from.y}
                        x2={to.x}
                        y2={to.y}
                        stroke={
                          selectedLinkId === link.id
                            ? "#ff3366"
                            : "rgba(34, 211, 238, .95)"
                        }
                        strokeOpacity={selectedLinkId === link.id ? ".95" : ".72"}
                        strokeWidth={selectedLinkId === link.id ? "4" : "2.5"}
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      />
                      <circle
                        cx={(from.x + to.x) / 2}
                        cy={(from.y + to.y) / 2}
                        r="4"
                        fill={selectedLinkId === link.id ? "#ff3366" : "#00ff88"}
                      >
                        <animate
                          attributeName="r"
                          values="3;7;3"
                          dur="1.8s"
                          repeatCount="indefinite"
                        />
                        <animate
                          attributeName="opacity"
                          values="1;.25;1"
                          dur="1.8s"
                          repeatCount="indefinite"
                        />
                      </circle>
                    </g>
                  )
                })}
                {sourcePort && connectionPointer && (
                  <g pointerEvents="none">
                    <line
                      x1={
                        interfacePoint(sourcePort.deviceId, sourcePort.port)
                          ?.x ?? 0
                      }
                      y1={
                        interfacePoint(sourcePort.deviceId, sourcePort.port)
                          ?.y ?? 0
                      }
                      x2={connectionPointer.x}
                      y2={connectionPointer.y}
                      stroke="#00ff88"
                      strokeWidth="2.5"
                      strokeDasharray="7 5"
                      opacity=".95"
                    />
                    <circle
                      cx={connectionPointer.x}
                      cy={connectionPointer.y}
                      r="5"
                      fill="none"
                      stroke="#00ff88"
                      strokeWidth="2"
                    >
                      <animate
                        attributeName="r"
                        values="4;8;4"
                        dur="1s"
                        repeatCount="indefinite"
                      />
                    </circle>
                  </g>
                )}
                {workspace.devices.map((device) => (
                  <NodeCard
                    key={device.id}
                    device={device}
                    warning={deviceHasTopologyWarning(device)}
                    selected={
                      selectedId === device.id || connectFrom === device.id
                    }
                    expanded={expandedDeviceId === device.id}
                    hovered={hoveredDeviceId === device.id}
                    showTargetPorts={
                      connectMode &&
                      !!sourcePort &&
                      hoveredDeviceId === device.id &&
                      sourcePort.deviceId !== device.id
                    }
                    onHoverChange={(hovered) =>
                      setHoveredDeviceId(hovered ? device.id : null)
                    }
                    onTogglePorts={() =>
                      setExpandedDeviceId((current) =>
                        current === device.id ? null : device.id,
                      )
                    }
                    onPortClick={(port) => {
                      setSelectedId(device.id)
                      selectPort(device.id, port)
                    }}
                    onPortPointerDown={(port) =>
                      beginPortConnection(device.id, port)
                    }
                    onDragStart={(event) => startDrag(device, event)}
                    onResizeStart={(event) => startResize(device, event)}
                    sourcePort={sourcePort}
                    onClick={() => selectNode(device.id)}
                  />
                ))}
                {workspace.links.map((link) => {
                  const from = deviceById.get(link.from)
                  const to = deviceById.get(link.to)
                  if (!from || !to) return null
                  const dx = to.x - from.x
                  const dy = to.y - from.y
                  const fromScale =
                    1 /
                    Math.max(
                      Math.abs(dx) / ((from.width ?? 210) / 2),
                      Math.abs(dy) / ((from.height ?? 68) / 2),
                    )
                  const toScale =
                    1 /
                    Math.max(
                      Math.abs(dx) / ((to.width ?? 210) / 2),
                      Math.abs(dy) / ((to.height ?? 68) / 2),
                    )
                  const fromLabelX = from.x + dx * fromScale + (dx < 0 ? 8 : -8)
                  const fromLabelY = from.y + dy * fromScale + (dy < 0 ? -8 : 8)
                  const toLabelX = to.x - dx * toScale + (dx < 0 ? -8 : 8)
                  const toLabelY = to.y - dy * toScale + (dy < 0 ? -8 : 8)
                  const fromPort = displayPort(link.from, link.fromPort)
                  const toPort = displayPort(link.to, link.toPort)
                  const labelStyle = {
                    fill: "var(--t-card, #101318)",
                    stroke:
                      selectedLinkId === link.id
                        ? "#ff3366"
                        : "var(--t-border-light)",
                  }
                  return (
                    <g key={`${link.id}-ports`} pointerEvents="none">
                      <g transform={`translate(${fromLabelX}, ${fromLabelY})`}>
                        <rect
                          x="-27"
                          y="-11"
                          width="54"
                          height="16"
                          rx="4"
                          {...labelStyle}
                          strokeOpacity=".95"
                        />
                        <text
                          x="0"
                          y="0"
                          textAnchor="middle"
                          dominantBaseline="middle"
                          fill={
                            selectedLinkId === link.id
                              ? "#ff3366"
                              : "var(--t-text)"
                          }
                          fontSize="8"
                          fontWeight="700"
                          fontFamily="JetBrains Mono, monospace"
                        >
                          {fromPort}
                        </text>
                      </g>
                      <g transform={`translate(${toLabelX}, ${toLabelY})`}>
                        <rect
                          x="-27"
                          y="-11"
                          width="54"
                          height="16"
                          rx="4"
                          {...labelStyle}
                          strokeOpacity=".95"
                        />
                        <text
                          x="0"
                          y="0"
                          textAnchor="middle"
                          dominantBaseline="middle"
                          fill={
                            selectedLinkId === link.id
                              ? "#ff3366"
                              : "var(--t-text)"
                          }
                          fontSize="8"
                          fontWeight="700"
                          fontFamily="JetBrains Mono, monospace"
                        >
                          {toPort}
                        </text>
                      </g>
                    </g>
                  )
                })}
              </svg>
            </div>
          ) : (
            <div className="p-4 md:p-6 grid md:grid-cols-2 gap-3">
              {[
                ["10", "Users", "192.168.10.0/24", "192.168.10.1", "#a78bfa"],
                ["20", "Wi-Fi", "192.168.20.0/24", "192.168.20.1", "#f97316"],
                ["30", "Servers", "192.168.30.0/24", "192.168.30.1", "#00ff88"],
                [
                  "40",
                  "Printers",
                  "192.168.40.0/24",
                  "192.168.40.1",
                  "#facc15",
                ],
              ].map(([id, name, subnet, gateway, color]) => (
                <div
                  key={id}
                  className="rounded-lg p-4"
                  style={{
                    border: `1px solid ${color}55`,
                    background: `${color}0b`,
                  }}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-xs" style={{ color }}>
                      VLAN {id}
                    </span>
                    <span
                      className="font-display text-sm"
                      style={{ color: "var(--t-text)" }}
                    >
                      {name}
                    </span>
                  </div>
                  <div
                    className="font-mono text-xs mt-4"
                    style={{ color: "var(--t-muted)" }}
                  >
                    {subnet}
                  </div>
                  <div
                    className="font-mono text-[10px] mt-1"
                    style={{ color: "var(--t-muted)" }}
                  >
                    GATEWAY · {gateway}
                  </div>
                </div>
              ))}
            </div>
          )}
        </GlassCard>

        {selected && (
          <GlassCard className="p-5">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
              <div>
                <h2
                  className="font-display text-lg font-semibold"
                  style={{ color: "var(--t-text)" }}
                >
                  {selected.name} · Physical interfaces
                </h2>
                <p
                  className="font-mono text-[10px] mt-1"
                  style={{ color: "var(--t-muted)" }}
                >
                  {selected.backendId
                    ? "LIVE INTERFACE NAMES FROM SNMP MONITORING"
                    : "MANUAL CARD · IMPORT A REAL DEVICE TO LOAD ACTUAL INTERFACES"}
                </p>
                <div className="flex flex-wrap gap-x-5 gap-y-1 mt-3 font-mono text-[10px]">
                  <span style={{ color: "var(--t-muted)" }}>
                    IP ·{" "}
                    <strong style={{ color: "var(--t-text)" }}>
                      {selected.ipAddress || selected.subtitle || "NOT SET"}
                    </strong>
                  </span>
                  <span style={{ color: "var(--t-muted)" }}>
                    MAC ·{" "}
                    <strong style={{ color: "var(--t-text)" }}>
                      {selected.macAddress || "NOT SET"}
                    </strong>
                  </span>
                  <span style={{ color: "var(--t-muted)" }}>
                    LOCATION ·{" "}
                    <strong style={{ color: "var(--t-text)" }}>
                      {selected.location || "NOT SET"}
                    </strong>
                  </span>
                </div>
              </div>
              <button
                type="button"
                onClick={deleteSelected}
                className="px-3 py-1.5 rounded-md font-mono text-[10px] uppercase"
                style={{ color: "#ff3366", border: "1px solid #ff336655" }}
              >
                REMOVE THIS DEVICE
              </button>
              {portsLoading && (
                <span
                  className="font-mono text-xs"
                  style={{ color: "var(--t-accent)" }}
                >
                  Loading interface names...
                </span>
              )}
              {selected.backendId && !portsLoading && (
                <button
                  type="button"
                  onClick={() => {
                    interfaceRefreshDevice.current = selected.backendId ?? null
                    setPortsReload((value) => value + 1)
                  }}
                  className="px-3 py-1.5 rounded-md font-mono text-[10px]"
                  style={{
                    color: "var(--t-accent)",
                    border: "1px solid var(--t-accent-border)",
                  }}
                >
                  REFRESH INTERFACES
                </button>
              )}
            </div>
            {portsError && (
              <div className="font-mono text-xs mt-3 text-red-400">
                {portsError}
              </div>
            )}
            {sourcePort?.deviceId === selected.id && (
              <button
                type="button"
                onClick={startNewFromPort}
                className="mt-4 px-3 py-2 rounded-md font-mono text-xs"
                style={{ color: "var(--t-bg)", background: "#00ff88" }}
              >
                + NEW CARD FROM {sourcePort.port}
              </button>
            )}
            {selectedPorts.length > 0 ? (
              <div className="flex flex-wrap gap-2 mt-4">
                {selectedPorts.map((port, index) => (
                  <button
                    key={port}
                    type="button"
                    onClick={() => selectPort(selected.id, port)}
                    className="px-3 py-2 rounded-md font-mono text-xs"
                    style={{
                      color:
                        sourcePort?.deviceId === selected.id &&
                        sourcePort.port === port
                          ? "#00ff88"
                          : "var(--t-text)",
                      background:
                        sourcePort?.deviceId === selected.id &&
                        sourcePort.port === port
                          ? "rgba(0,255,136,.12)"
                          : "var(--t-bg)",
                      border: `1px solid ${
                        sourcePort?.deviceId === selected.id &&
                        sourcePort.port === port
                          ? "#00ff88"
                          : "var(--t-border-alpha)"
                      }`,
                    }}
                  >
                    {portLabel(port, index)}
                  </button>
                ))}
              </div>
            ) : (
              <div
                className="font-mono text-xs mt-4"
                style={{ color: "var(--t-muted)" }}
              >
                No physical interfaces found. Virtual interfaces are hidden.
              </div>
            )}
          </GlassCard>
        )}

        {editing && (
          <GlassCard className="p-5" glow="cyan">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h2
                  className="font-display text-lg font-semibold"
                  style={{ color: "var(--t-text)" }}
                >
                  {workspace.devices.some((device) => device.id === editing.id)
                    ? "Edit device card"
                    : "Create device card"}
                </h2>
                <p
                  className="font-mono text-[10px] mt-1"
                  style={{ color: "var(--t-muted)" }}
                >
                  {editing.backendId
                    ? "REAL DEVICE DETAILS ARE SAVED TO THE DATABASE"
                    : "DETAILS ARE SAVED IN THIS BROWSER"}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setEditing(null)}
                style={{ color: "var(--t-muted)" }}
              >
                X
              </button>
            </div>
            <div className="grid md:grid-cols-4 gap-3">
              {([
                ["name", "Device name"],
                ["ipAddress", "IP address"],
                ["macAddress", "MAC address"],
                ["location", "Location"],
                ["type", "Device type"],
              ] as const).map(([field, label]) => (
                <label
                  key={field}
                  className="font-mono text-[10px] uppercase"
                  style={{ color: "var(--t-muted)" }}
                >
                  {label}
                  <input
                    value={editing[field] ?? ""}
                    onChange={(event) =>
                      setEditing({ ...editing, [field]: event.target.value })
                    }
                    className="mt-2 w-full rounded-md px-3 py-2 font-display text-sm outline-none"
                    style={{
                      color: "var(--t-text)",
                      background: "var(--t-bg)",
                      border: "1px solid var(--t-border-alpha)",
                    }}
                  />
                </label>
              ))}
              <label
                className="font-mono text-[10px] uppercase"
                style={{ color: "var(--t-muted)" }}
              >
                Color
                <input
                  type="color"
                  value={editing.tone}
                  onChange={(event) =>
                    setEditing({ ...editing, tone: event.target.value })
                  }
                  className="mt-2 w-full h-9 rounded-md cursor-pointer"
                />
              </label>
              <label
                className="font-mono text-[10px] uppercase md:col-span-2"
                style={{ color: "var(--t-muted)" }}
              >
                Ports (comma separated)
                <input
                  value={editing.ports?.join(", ") ?? ""}
                  onChange={(event) =>
                    setEditing({
                      ...editing,
                      ports: event.target.value
                        .split(",")
                        .map((port) => port.trim())
                        .filter(Boolean),
                    })
                  }
                  placeholder="Gi0/1, Gi0/2, Gi0/3"
                  className="mt-2 w-full rounded-md px-3 py-2 font-display text-sm outline-none"
                  style={{
                    color: "var(--t-text)",
                    background: "var(--t-bg)",
                    border: "1px solid var(--t-border-alpha)",
                  }}
                />
              </label>
            </div>
            <div className="flex justify-end gap-2 mt-4">
              <button
                type="button"
                onClick={() => setEditing(null)}
                className="px-4 py-2 rounded-md font-mono text-xs"
                style={{
                  color: "var(--t-muted)",
                  border: "1px solid var(--t-border-alpha)",
                }}
              >
                CANCEL
              </button>
              <button
                type="button"
                onClick={saveDevice}
                className="px-4 py-2 rounded-md font-mono text-xs"
                style={{ color: "var(--t-bg)", background: "var(--t-accent)" }}
              >
                SAVE CARD
              </button>
            </div>
          </GlassCard>
        )}

        <section className="grid lg:grid-cols-[1.35fr_.65fr] gap-6">
          <GlassCard className="overflow-hidden">
            <div
              className="px-5 py-4"
              style={{ borderBottom: "1px solid var(--t-border-light)" }}
            >
              <h2
                className="font-display text-lg font-semibold"
                style={{ color: "var(--t-text)" }}
              >
                Connections
              </h2>
              <p
                className="font-mono text-[10px] mt-1"
                style={{ color: "var(--t-muted)" }}
              >
                Click a line to select it, then use DISCONNECT; or use the table
                action
              </p>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left">
                <thead>
                  <tr
                    style={{
                      color: "var(--t-muted)",
                      borderBottom: "1px solid var(--t-border-light)",
                    }}
                  >
                    {[
                      "Source interface",
                      "Destination interface",
                      "Link type",
                      "Action",
                    ].map((label) => (
                      <th
                        key={label}
                        className="px-5 py-3 font-mono text-[10px] uppercase tracking-wider font-normal"
                      >
                        {label}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {workspace.links.map((link) => (
                    <tr
                      key={link.id}
                      style={{
                        borderBottom: "1px solid var(--t-border-light)",
                      }}
                    >
                      <td
                        className="px-5 py-3 font-mono text-xs"
                        style={{ color: "var(--t-text)" }}
                      >
                        {deviceById.get(link.from)?.name} ·{" "}
                        {displayPort(link.from, link.fromPort)}
                      </td>
                      <td
                        className="px-5 py-3 font-mono text-xs"
                        style={{ color: "var(--t-text)" }}
                      >
                        {deviceById.get(link.to)?.name} ·{" "}
                        {displayPort(link.to, link.toPort)}
                      </td>
                      <td className="px-5 py-3 font-mono text-xs text-cyan-400">
                        {link.label}
                      </td>
                      <td className="px-5 py-3">
                        <button
                          type="button"
                          onClick={() => disconnectLink(link.id)}
                          className="font-mono text-[10px] text-red-400"
                        >
                          DISCONNECT
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </GlassCard>
          <GlassCard className="p-5">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h2
                  className="font-display text-lg font-semibold"
                  style={{ color: "var(--t-text)" }}
                >
                  Verification checklist
                </h2>
                <p
                  className="font-mono text-[10px] mt-1"
                  style={{ color: "var(--t-muted)" }}
                >
                  {completed} OF {checklistItems.length} COMPLETE
                </p>
              </div>
              <div
                className="font-mono text-xs"
                style={{
                  color:
                    completed === checklistItems.length
                      ? "#00ff88"
                      : "var(--t-accent)",
                }}
              >
                {Math.round((completed / checklistItems.length) * 100)}%
              </div>
            </div>
            <div
              className="w-full h-1 rounded-full mt-4"
              style={{ background: "var(--t-border-light)" }}
            >
              <div
                className="h-1 rounded-full transition-all"
                style={{
                  width: `${(completed / checklistItems.length) * 100}%`,
                  background: "#00ff88",
                }}
              />
            </div>
            <div className="space-y-3 mt-5">
              {checklistItems.map((item, index) => (
                <label
                  key={item}
                  className="flex gap-3 items-start cursor-pointer"
                >
                  <input
                    type="checkbox"
                    checked={checked[index]}
                    onChange={() =>
                      setChecked((previous) =>
                        previous.map((value, itemIndex) =>
                          itemIndex === index ? !value : value,
                        ),
                      )
                    }
                    className="mt-0.5 accent-cyan-400"
                  />
                  <span
                    className="font-display text-sm leading-tight"
                    style={{
                      color: checked[index]
                        ? "var(--t-muted)"
                        : "var(--t-text)",
                      textDecoration: checked[index] ? "line-through" : "none",
                    }}
                  >
                    {item}
                  </span>
                </label>
              ))}
            </div>
          </GlassCard>
        </section>
      </div>
    </main>
  )
}
