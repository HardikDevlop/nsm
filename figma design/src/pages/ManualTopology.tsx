import { useEffect, useMemo, useRef, useState } from "react"
import { useBlocker } from "react-router"
import GlassCard from "../components/GlassCard"
import {
  createManualTopologySnapshot,
  getLatestInterfaces,
  getLatestManualTopologySnapshot,
  getSNMPInterfaces,
  listSNMPDevicesOptimized,
  pingIps,
  reconcileManualTopology,
  resolveManualTopologyChange,
  type ManualTopologyChange,
  type SNMPDeviceListItem,
  updateDevice,
  updateManualTopologySnapshot,
} from "../lib/api"
import { toast } from "../lib/swal"

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
  geometry?: "straight" | "curved"
}
type Workspace = { devices: Device[]; links: Link[] }
type VerificationStatus =
  | "VERIFIED"
  | "DISCONNECTED"
  | "UNEXPECTED"
  | "PORT_MISMATCH"
  | "DEVICE_OFFLINE"
  | "UNKNOWN"
type ActualTopology = {
  devices: Array<Record<string, unknown>>
  links: Array<Record<string, unknown>>
  timestamp?: string | null
}
type ConfirmRequest = {
  title: string
  description: string
  details: Array<[string, string]>
  confirmLabel: string
  tone: "amber" | "red" | "green"
  secondStep?: {
    title: string
    description: string
    confirmLabel: string
  }
  onConfirm: () => void
}
type ContextMenuState = { x: number; y: number; deviceId?: string; linkId?: string }
const FALLBACK_PORT = "Port 1"
const CANVAS_WIDTH = 1440
const CANVAS_HEIGHT = 900

function linkUsesPort(link: Link, deviceId: string, port: string) {
  return (
    (link.from === deviceId && link.fromPort === port) ||
    (link.to === deviceId && link.toPort === port)
  )
}

function isPortOccupied(links: Link[], deviceId: string, port: string, exceptLinkId?: string) {
  return links.some((link) => link.id !== exceptLinkId && linkUsesPort(link, deviceId, port))
}

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
const OFFLINE_ALERT_KEY = "nms.device-health.offline-alerts.v1"
const tones = [
  "#c8c1b4",
  "#9bb5a3",
  "#b7c0ba",
  "#d0a65a",
  "#8eaaa0",
  "#d8d2c6",
  "#b98d71",
]
const PEN_COLOR = "var(--t-accent)"
const PEN_SURFACE = "var(--t-accent-alpha)"
const PEN_BORDER = "var(--t-accent-border)"

const paletteItems = [
  ["Firewall", "Firewall"],
  ["Router", "Router"],
  ["Switch", "Switch"],
  ["Server", "Server"],
  ["NVR", "NVR"],
  ["Camera", "Camera"],
  ["Access Point", "Access Point"],
  ["Wireless", "Wireless"],
  ["Cloud", "Internet / Cloud"],
  ["Generic device", "Network device"],
  ["Others", "Network device"],
] as const

function inventoryCategory(device: SNMPDeviceListItem) {
  const value = `${device.device_type || ""} ${device.hostname || ""} ${device.name || ""} ${device.model || ""}`.toLowerCase()
  if (value.includes("firewall") || value.includes("fortigate") || value.includes("palo alto")) return "Firewall"
  if (value.includes("router") || value.includes("gateway") || value.includes("mikrotik")) return "Router"
  if (value.includes("switch") || value.includes("catalyst") || value.includes("nexus")) return "Switch"
  if (value.includes("nvr") || value.includes("dvr") || value.includes("video recorder")) return "NVR"
  if (value.includes("camera") || value.includes("cctv") || value.includes("ipcam")) return "Camera"
  if (value.includes("access point") || value.includes("wireless") || value.includes("wifi") || value.includes("wap")) return "Access Point"
  if (value.includes("server")) return "Server"
  return "Others"
}

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

function SafetyConfirmDialog({
  request,
  step,
  onCancel,
  onConfirm,
}: {
  request: ConfirmRequest
  step: 1 | 2
  onCancel: () => void
  onConfirm: () => void
}) {
  const secondStep = step === 2 && request.secondStep
  const accent = request.tone === "red" ? "#d87b73" : request.tone === "green" ? "#9bb5a3" : "#d0a65a"
  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/70 p-4" role="presentation">
      <div
        className="w-full max-w-lg rounded-xl p-5 shadow-2xl"
        role="dialog"
        aria-modal="true"
        aria-labelledby="topology-confirm-title"
        style={{ background: "#171b1a", border: `1px solid ${accent}88`, color: "#e7e1d5" }}
      >
        <div className="flex gap-3">
          <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-full" style={{ color: accent, background: `${accent}18` }} aria-hidden="true">
            <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M12 3 2.8 20h18.4L12 3Z" /><path d="M12 9v5M12 17h.01" /></svg>
          </div>
          <div className="min-w-0 flex-1">
            <h2 id="topology-confirm-title" className="font-display text-lg font-semibold">{secondStep ? request.secondStep?.title : request.title}</h2>
            <p className="mt-1 font-mono text-xs leading-relaxed" style={{ color: "#a8b0aa" }}>{secondStep ? request.secondStep?.description : request.description}</p>
          </div>
        </div>
        <div className="mt-4 space-y-2 rounded-lg p-3" style={{ background: "#101413", border: "1px solid rgba(231,225,213,.1)" }}>
          {request.details.map(([label, value]) => (
            <div key={label} className="grid grid-cols-[7rem_1fr] gap-3 font-mono text-[10px]">
              <span className="uppercase" style={{ color: "#7f8982" }}>{label}</span>
              <span className="break-words" style={{ color: "#e7e1d5" }}>{value}</span>
            </div>
          ))}
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <button type="button" onClick={onCancel} className="rounded-md px-4 py-2 font-mono text-[10px] uppercase" style={{ color: "#b7c0ba", border: "1px solid rgba(231,225,213,.18)" }}>Cancel</button>
          <button type="button" onClick={onConfirm} className="rounded-md px-4 py-2 font-mono text-[10px] font-bold uppercase" style={{ color: "#101413", background: accent }}>{secondStep ? request.secondStep?.confirmLabel : request.secondStep ? "Review & Confirm" : request.confirmLabel}</button>
        </div>
      </div>
    </div>
  )
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

function parallelLinkGeometry(
  from: Device,
  to: Device,
  lane: number,
  laneCount: number,
  geometryMode?: Link["geometry"],
) {
  const dx = to.x - from.x
  const dy = to.y - from.y
  const length = Math.hypot(dx, dy) || 1
  const offset = geometryMode === "straight"
    ? 0
    : geometryMode === "curved"
      ? (lane - (laneCount - 1) / 2) * 30 || 30
      : (lane - (laneCount - 1) / 2) * 30
  const normalX = -dy / length
  const normalY = dx / length
  const midX = (from.x + to.x) / 2
  const midY = (from.y + to.y) / 2
  const controlX = midX + normalX * offset
  const controlY = midY + normalY * offset
  const curveMidX = (from.x + 2 * controlX + to.x) / 4
  const curveMidY = (from.y + 2 * controlY + to.y) / 4

  return {
    d: offset === 0
      ? `M ${from.x} ${from.y} L ${to.x} ${to.y}`
      : `M ${from.x} ${from.y} Q ${controlX} ${controlY} ${to.x} ${to.y}`,
    midpoint: { x: curveMidX, y: curveMidY },
  }
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
  onContextMenu,
}: {
  device: Device
  selected: boolean
  onClick: (event: React.MouseEvent<SVGGElement>) => void
  expanded: boolean
  onTogglePorts: () => void
  onPortClick: (port: string) => void
  onPortPointerDown: (port: string) => void
  onDragStart: (event: React.PointerEvent<SVGGElement>) => void
  onResizeStart: (event: React.PointerEvent<SVGGElement>) => void
  sourcePort: { deviceId: string; port: string } | null
  hovered: boolean
  onHoverChange: (hovered: boolean) => void
  showTargetPorts: boolean
  warning: boolean
  onContextMenu: (event: React.MouseEvent<SVGGElement>) => void
}) {
  const ports = Array.isArray(device.ports) && device.ports.length > 0 ? device.ports : [FALLBACK_PORT]
  // Keep saved cards visually consistent while preserving a small resize range.
  const width = Math.max(260, Math.min(300, device.width ?? 280))
  const height = Math.max(72, Math.min(88, device.height ?? 76))
  const interfacePanelWidth = width
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
  const displayName = ["", "(none)", "null", "unknown", "unknown device"].includes(device.name.trim().toLowerCase())
    ? "Network device"
    : device.name.trim()
  const nameLines = wrapDeviceName(displayName, Math.max(16, Math.floor((width - 112) / 5.6)))
  const subtitleMaxLength = Math.max(18, Math.floor((width - 58) / 5))
  const typeLabel = device.type.trim().toUpperCase() || "DEVICE"
  const typeTextLength = Math.min(58, Math.max(32, width - 108))
  const casingFill = "var(--topology-node)"
  const bezelFill = hovered
    ? "var(--topology-node-highlight)"
    : "transparent"
  return (
    <g
      transform={`translate(${device.x - width / 2}, ${device.y - height / 2})`}
      onClick={onClick}
      onContextMenu={onContextMenu}
      onPointerDown={onDragStart}
      onMouseEnter={() => onHoverChange(true)}
      onMouseLeave={() => onHoverChange(false)}
      className="cursor-grab"
    >
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
      <rect x="2" y="2" width="5" height={height - 4} rx="2.5" fill={device.tone} />
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
      <circle cx="48" cy={height - 14} r="3" fill={portStatus(ports[0]) === "down" ? "#dc2626" : portStatus(ports[0]) === "up" ? "#059669" : "var(--t-muted)"} />
      <text x="56" y={height - 11} fill="var(--t-muted)" fontSize="6.5" fontFamily="JetBrains Mono, monospace" letterSpacing=".3">
        {downCount > 0 ? `${downCount} PORT${downCount === 1 ? "" : "S"} DOWN` : `${upCount || ports.length} PORT${(upCount || ports.length) === 1 ? "" : "S"} READY`}
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
                    fill={active ? PEN_SURFACE : "var(--t-bg)"}
                    stroke={active ? PEN_BORDER : "var(--t-border-light)"}
                  />
                  {active || portStatus(port) ? (
                    <circle
                      cx="7"
                      cy="7"
                      r="2"
                      fill={active ? PEN_COLOR : statusColor(port)}
                    />
                  ) : null}
                  <text
                    x="12"
                    y="10"
                    fill={active ? PEN_COLOR : "var(--t-muted)"}
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
  const [selectedIds, setSelectedIds] = useState<string[]>([])
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
  const [deviceHealth, setDeviceHealth] = useState<Record<number, boolean>>({})
  const [portsLoading, setPortsLoading] = useState(false)
  const [portsError, setPortsError] = useState<string | null>(null)
  const [portsReload, setPortsReload] = useState(0)
  const interfaceRefreshDevice = useRef<number | null>(null)
  const loadedInterfaceDevices = useRef(new Set<number>())
  const svgRef = useRef<SVGSVGElement | null>(null)
  const workspaceGridRef = useRef<HTMLDivElement | null>(null)
  const canvasScrollRef = useRef<HTMLDivElement | null>(null)
  const [isCanvasFullscreen, setIsCanvasFullscreen] = useState(false)
  const [canvasZoom, setCanvasZoom] = useState(1)
  const [canvasPan, setCanvasPan] = useState({ x: 0, y: 0 })
  const [canvasViewport, setCanvasViewport] = useState({
    x: 0,
    y: 0,
    width: CANVAS_WIDTH,
    height: CANVAS_HEIGHT,
  })
  const [paletteCollapsed, setPaletteCollapsed] = useState(false)
  const [expandedPaletteCategories, setExpandedPaletteCategories] = useState<Record<string, boolean>>({})
  const [snapToGrid, setSnapToGrid] = useState(true)
  const [selectionBox, setSelectionBox] = useState<{
    start: { x: number; y: number }
    end: { x: number; y: number }
  } | null>(null)
  const [panState, setPanState] = useState<{
    startX: number
    startY: number
    originX: number
    originY: number
  } | null>(null)
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
  const [actualTopology, setActualTopology] = useState<ActualTopology | null>(null)
  const [reconcileLoading, setReconcileLoading] = useState(false)
  const [reconcileError, setReconcileError] = useState<string | null>(null)
  const [editing, setEditing] = useState<Device | null>(null)
  const [activeView, setActiveView] = useState<"physical" | "logical">(
    "physical",
  )
  const [verificationView, setVerificationView] = useState<"manual" | "actual" | "compare">("compare")
  const [confirmRequest, setConfirmRequest] = useState<ConfirmRequest | null>(null)
  const [confirmStep, setConfirmStep] = useState<1 | 2>(1)
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false)
  const [searchQuery, setSearchQuery] = useState("")
  const [deviceTypeFilter, setDeviceTypeFilter] = useState("all")
  const [healthFilter, setHealthFilter] = useState("all")
  const [verificationFilter, setVerificationFilter] = useState("all")
  const [onlyMismatches, setOnlyMismatches] = useState(false)
  const [onlyOffline, setOnlyOffline] = useState(false)
  const [contextMenu, setContextMenu] = useState<ContextMenuState | null>(null)
  const [checked, setChecked] = useState<boolean[]>(
    checklistItems.map(() => false),
  )
  const alertedOfflineIps = useRef(new Set<string>())
  const historyRef = useRef<Workspace[]>([])
  const futureRef = useRef<Workspace[]>([])
  const historyApplyingRef = useRef(false)
  const lastWorkspaceRef = useRef(JSON.stringify(workspace))
  const persistedWorkspaceRef = useRef(JSON.stringify(workspace))
  const latestWorkspaceRef = useRef(workspace)
  const searchInputRef = useRef<HTMLInputElement | null>(null)
  const navigationBlocker = useBlocker(hasUnsavedChanges)

  const requestConfirmation = (request: ConfirmRequest) => {
    setConfirmStep(1)
    setConfirmRequest(request)
  }

  const syncCanvasViewport = () => {
    const container = canvasScrollRef.current
    const svg = svgRef.current
    if (!container || !svg) return
    const rect = svg.getBoundingClientRect()
    if (!rect.width || !rect.height) return

    const viewBoxWidth = CANVAS_WIDTH / canvasZoom
    const viewBoxHeight = CANVAS_HEIGHT / canvasZoom

    setCanvasViewport({
      x:
        CANVAS_WIDTH / 2 -
        CANVAS_WIDTH / (2 * canvasZoom) -
        canvasPan.x +
        (container.scrollLeft / rect.width) * viewBoxWidth,
      y:
        CANVAS_HEIGHT / 2 -
        CANVAS_HEIGHT / (2 * canvasZoom) -
        canvasPan.y +
        (container.scrollTop / rect.height) * viewBoxHeight,
      width: (container.clientWidth / rect.width) * viewBoxWidth,
      height: (container.clientHeight / rect.height) * viewBoxHeight,
    })
  }

  const cancelConfirmation = () => {
    setConfirmRequest(null)
    setConfirmStep(1)
  }

  const confirmPendingChange = () => {
    if (!confirmRequest) {
      if (navigationBlocker.state === "blocked") navigationBlocker.proceed()
      return
    }
    if (confirmStep === 1 && confirmRequest.secondStep) {
      setConfirmStep(2)
      return
    }
    const action = confirmRequest.onConfirm
    cancelConfirmation()
    action()
  }

  useEffect(() => {
    const serialized = JSON.stringify(workspace)
    latestWorkspaceRef.current = workspace
    setHasUnsavedChanges(serialized !== persistedWorkspaceRef.current)
    if (serialized === lastWorkspaceRef.current) return
    if (!historyApplyingRef.current) {
      historyRef.current = [...historyRef.current, JSON.parse(lastWorkspaceRef.current) as Workspace].slice(-30)
      futureRef.current = []
    }
    historyApplyingRef.current = false
    lastWorkspaceRef.current = serialized
  }, [workspace])

  useEffect(() => {
    try {
      const saved = JSON.parse(
        window.sessionStorage.getItem(OFFLINE_ALERT_KEY) || "[]",
      )
      if (Array.isArray(saved)) {
        alertedOfflineIps.current = new Set(saved.filter((ip) => typeof ip === "string"))
      }
    } catch {
      // Optional session-only alert state.
    }
  }, [])

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(workspace))
  }, [workspace])
  useEffect(() => {
    syncCanvasViewport()
  }, [canvasPan.x, canvasPan.y, canvasZoom, isCanvasFullscreen, workspace.devices.length, activeView])
  useEffect(() => {
    const container = canvasScrollRef.current
    if (!container) return
    const handleScroll = () => syncCanvasViewport()
    const handleResize = () => syncCanvasViewport()
    container.addEventListener("scroll", handleScroll, { passive: true })
    window.addEventListener("resize", handleResize)
    return () => {
      container.removeEventListener("scroll", handleScroll)
      window.removeEventListener("resize", handleResize)
    }
  }, [canvasPan.x, canvasPan.y, canvasZoom, isCanvasFullscreen, activeView])
  useEffect(() => {
    const warnBeforeUnload = (event: BeforeUnloadEvent) => {
      if (!hasUnsavedChanges) return
      event.preventDefault()
      event.returnValue = ""
    }
    window.addEventListener("beforeunload", warnBeforeUnload)
    return () => window.removeEventListener("beforeunload", warnBeforeUnload)
  }, [hasUnsavedChanges])
  useEffect(() => {
    void getLatestManualTopologySnapshot()
      .then((snapshot) => {
        if (!snapshot) return
        setSnapshotId(snapshot.id)
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
        .then((snapshot) => {
          setSnapshotId(snapshot.id)
          const savedWorkspace = JSON.stringify(workspace)
          persistedWorkspaceRef.current = savedWorkspace
          if (JSON.stringify(latestWorkspaceRef.current) === savedWorkspace) setHasUnsavedChanges(false)
        })
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
          if (result.live) {
            setActualTopology({
              devices: Array.isArray(result.live.devices) ? result.live.devices : [],
              links: Array.isArray(result.live.links) ? result.live.links : [],
              timestamp: result.last_reconciled_at,
            })
          }
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
    let cancelled = false
    // Bypass the short-lived GET cache: this page is also responsible for
    // removing deleted devices from its persisted topology workspace.
    void listSNMPDevicesOptimized(
      { page: 1, page_size: 200 },
      new AbortController().signal,
    )
      .then((response) => {
        if (cancelled) return
        setRealDevices(response.items)
        const activeIds = new Set(response.items.map((device) => device.id))
        if (activeIds.size === 0) {
          const emptyWorkspace: Workspace = { devices: [], links: [] }
          setWorkspace(emptyWorkspace)
          setSelectedId(null)
          setSelectedLinkId(null)
          setEditing(null)
          setConnectFrom(null)
          setConnectMode(false)
          setSourcePort(null)
          setDeviceHealth({})
          window.localStorage.removeItem(STORAGE_KEY)
          window.sessionStorage.removeItem(OFFLINE_ALERT_KEY)

          // Remove the server-side baseline as well. Otherwise a fresh
          // reload could resurrect deleted devices from the latest snapshot.
          void getLatestManualTopologySnapshot().then((snapshot) => {
            if (snapshot) {
              void updateManualTopologySnapshot(snapshot.id, emptyWorkspace)
            }
          }).catch(() => undefined)
          return
        }
        setWorkspace((current) => {
          const devices = current.devices.filter(
            (device) => !device.backendId || activeIds.has(device.backendId),
          )
          if (devices.length === current.devices.length) return current
          const deviceIds = new Set(devices.map((device) => device.id))
          return {
            devices,
            links: current.links.filter(
              (link) => deviceIds.has(link.from) && deviceIds.has(link.to),
            ),
          }
        })
      })
      .catch(() => {
        if (!cancelled) setRealDevices([])
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (realDevices.length === 0) return
    let cancelled = false
    const checkDeviceHealth = async () => {
      try {
        const results = await pingIps(
          realDevices.map((device) => device.ip_address).filter(Boolean),
          1000,
        )
        if (cancelled) return
        const byIp = new Map(results.results.map((result) => [result.ip, result]))
        const nextHealth: Record<number, boolean> = {}
        const offline: SNMPDeviceListItem[] = []
        realDevices.forEach((device) => {
          const result = byIp.get(device.ip_address)
          const reachable = result?.reachable === true
          nextHealth[device.id] = reachable
          if (!reachable) offline.push(device)
          if (reachable) alertedOfflineIps.current.delete(device.ip_address)
        })
        setDeviceHealth(nextHealth)
        const newOffline = offline.filter((device) => {
          if (alertedOfflineIps.current.has(device.ip_address)) return false
          alertedOfflineIps.current.add(device.ip_address)
          return true
        })
        if (newOffline.length > 0) {
          try {
            window.sessionStorage.setItem(
              OFFLINE_ALERT_KEY,
              JSON.stringify([...alertedOfflineIps.current]),
            )
          } catch {
            // Optional session-only alert state.
          }
          toast.error(
            `Device unreachable: ${newOffline
              .map((device) => `${device.ip_address} (${device.hostname || device.name || "unknown"})`)
              .join(", ")}`,
          )
        }
      } catch (error) {
        if (!cancelled) {
          toast.warning(
            error instanceof Error
              ? `Device health check failed: ${error.message}`
              : "Device health check failed",
          )
        }
      }
    }
    void checkDeviceHealth()
    const timer = window.setInterval(checkDeviceHealth, 120000)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [realDevices])

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
          status:
            deviceHealth[real.id] === undefined
              ? device.status
              : deviceHealth[real.id]
                ? "online"
                : "offline",
        }
      }),
    }))
  }, [realDevices, deviceHealth])

  const selected = workspace.devices.find((device) => device.id === selectedId)
  const selectedPorts = Array.isArray(selected?.ports) && selected.ports.length > 0
    ? selected.ports
    : [FALLBACK_PORT]
  const completed = checked.filter(Boolean).length
  const deviceById = useMemo(
    () => new Map(workspace.devices.map((device) => [device.id, device])),
    [workspace.devices],
  )
  const actualDevices = useMemo<Device[]>(() => {
    if (!actualTopology) return []
    return actualTopology.devices.map((raw, index) => {
      const backendId = Number(raw.id ?? raw.device_id)
      const existing = workspace.devices.find((device) => device.backendId === backendId)
      return {
        ...(existing ?? {}),
        id: existing?.id ?? `actual-${String(raw.id ?? index)}`,
        backendId: Number.isFinite(backendId) ? backendId : undefined,
        name: String(raw.display_name ?? raw.hostname ?? raw.sys_name ?? raw.name ?? `DEVICE ${index + 1}`),
        subtitle: String(raw.ip_address ?? raw.ip ?? existing?.subtitle ?? "SNMP device"),
        ipAddress: String(raw.ip_address ?? raw.ip ?? existing?.ipAddress ?? ""),
        type: String(raw.type ?? raw.device_type ?? raw.vendor ?? existing?.type ?? "Network device"),
        tone: existing?.tone ?? tones[index % tones.length],
        status: deviceHealth[backendId] === false ? "offline" : String(raw.status ?? existing?.status ?? "unknown"),
        x: existing?.x ?? 150 + (index % 4) * 220,
        y: existing?.y ?? 120 + Math.floor(index / 4) * 120,
      }
    })
  }, [actualTopology, deviceHealth, workspace.devices])
  const actualDeviceById = useMemo(
    () => new Map(actualDevices.map((device) => [device.id, device])),
    [actualDevices],
  )
  const actualLinks = useMemo<Link[]>(() => {
    if (!actualTopology) return []
    return actualTopology.links.map((raw, index) => {
      const from = String(raw.from ?? raw.source_node ?? raw.source_device_id ?? "")
      const to = String(raw.to ?? raw.target_node ?? raw.target_device_id ?? "")
      const fromDevice = actualDevices.find((device) => String(device.id) === from || String(device.backendId) === from)
      const toDevice = actualDevices.find((device) => String(device.id) === to || String(device.backendId) === to)
      const fromPort = String(raw.fromPort ?? raw.source_port ?? raw.local_port ?? "")
      const toPort = String(raw.toPort ?? raw.target_port ?? raw.remote_port ?? "")
      return {
        id: `actual-link-${String(raw.id ?? index)}`,
        from: fromDevice?.id ?? from,
        to: toDevice?.id ?? to,
        fromPort,
        toPort,
        label: String(raw.label ?? `${fromPort || "unknown port"} → ${toPort || "unknown port"}`),
        geometry: "curved",
      }
    }).filter((link) => actualDeviceById.has(link.from) && actualDeviceById.has(link.to))
  }, [actualTopology, actualDevices, actualDeviceById])
  const endpointKey = (deviceId: string, port?: string) => `${deviceId}::${String(port ?? "").trim().toLowerCase()}`
  const devicePairKey = (link: Link) => [link.from, link.to].sort().join("::")
  const linkKey = (link: Link) => [endpointKey(link.from, link.fromPort), endpointKey(link.to, link.toPort)].sort().join("||")
  const verification = useMemo(() => {
    const manual = workspace.links.map((link) => {
      const from = deviceById.get(link.from)
      const to = deviceById.get(link.to)
      const offline = [from, to].some((device) => device?.backendId != null && deviceHealth[device.backendId] === false)
      let status: VerificationStatus = "UNKNOWN"
      if (offline) status = "DEVICE_OFFLINE"
      else if (!actualTopology) status = "UNKNOWN"
      else if (!link.fromPort || !link.toPort) status = "UNKNOWN"
      else if (actualLinks.some((candidate) => linkKey(candidate) === linkKey(link))) status = "VERIFIED"
      else if (actualLinks.some((candidate) => devicePairKey(candidate) === devicePairKey(link))) status = "PORT_MISMATCH"
      else status = "DISCONNECTED"
      return { id: link.id, status, manualLink: link, actualLink: actualLinks.find((candidate) => devicePairKey(candidate) === devicePairKey(link)) }
    })
    const manualKeys = new Set(manual.map((item) => item.actualLink ? linkKey(item.actualLink) : ""))
    const unexpected = actualLinks
      .filter((link) => !manualKeys.has(linkKey(link)) && !manual.some((item) => devicePairKey(item.manualLink) === devicePairKey(link)))
      .map((link) => ({ id: link.id, status: "UNEXPECTED" as VerificationStatus, actualLink: link }))
    return [...manual, ...unexpected]
  }, [actualLinks, actualTopology, deviceById, deviceHealth, workspace.links])
  const verificationCounts = {
    total: workspace.links.length,
    verified: verification.filter((item) => item.status === "VERIFIED").length,
    issues: verification.filter((item) => item.status !== "VERIFIED").length,
    unexpected: verification.filter((item) => item.status === "UNEXPECTED").length,
    offline: new Set(verification.filter((item) => item.status === "DEVICE_OFFLINE").flatMap((item) => [item.manualLink?.from, item.manualLink?.to].filter(Boolean))).size,
  }
  const statusMeta = (status: VerificationStatus) => ({
    VERIFIED: { label: "VERIFIED", color: "#79c69a", icon: "✓" },
    DISCONNECTED: { label: "DISCONNECTED", color: "#d7aa59", icon: "!" },
    UNEXPECTED: { label: "UNEXPECTED", color: "#da6b6b", icon: "!" },
    PORT_MISMATCH: { label: "PORT MISMATCH", color: "#d7aa59", icon: "↔" },
    DEVICE_OFFLINE: { label: "DEVICE OFFLINE", color: "#da6b6b", icon: "×" },
    UNKNOWN: { label: "UNKNOWN", color: "#9ba59f", icon: "?" },
  }[status])
  const verificationByLinkId = useMemo(() => {
    const result = new Map<string, (typeof verification)[number]>()
    verification.forEach((item) => {
      if (item.manualLink) result.set(item.manualLink.id, item)
      if (item.actualLink) result.set(item.actualLink.id, item)
    })
    return result
  }, [verification])
  const verificationForLink = (linkId: string) => verificationByLinkId.get(linkId)
  const visibleDevices = verificationView === "actual" ? actualDevices : workspace.devices
  const visibleDeviceById = verificationView === "actual" ? actualDeviceById : deviceById
  const visibleLinks = verificationView === "actual"
    ? actualLinks
      : verificationView === "compare"
        ? [...workspace.links, ...verification.filter((item) => item.status === "UNEXPECTED" && item.actualLink).map((item) => item.actualLink as Link)]
        : workspace.links
  const filteredTopology = useMemo(() => {
    const query = searchQuery.trim().toLowerCase()
    const queryLinks = visibleLinks.filter((link) => {
      if (!query) return false
      const from = visibleDeviceById.get(link.from)
      const to = visibleDeviceById.get(link.to)
      return [link.label, link.fromPort, link.toPort, from?.name, to?.name, from?.ipAddress, to?.ipAddress].filter(Boolean).join(" ").toLowerCase().includes(query)
    })
    const deviceMatches = new Set(
      visibleDevices
        .filter((device) => {
          const verificationStatuses = verification
            .filter((item) => item.manualLink?.from === device.id || item.manualLink?.to === device.id || item.actualLink?.from === device.id || item.actualLink?.to === device.id)
            .map((item) => item.status)
          const health = (device.status ?? (device.backendId != null && deviceHealth[device.backendId] === false ? "offline" : "unknown")).toLowerCase()
          const searchFields = [device.name, device.subtitle, device.ipAddress, device.macAddress, device.type].filter(Boolean).join(" ").toLowerCase()
          return (!query || searchFields.includes(query) || queryLinks.some((link) => link.from === device.id || link.to === device.id)) &&
            (deviceTypeFilter === "all" || device.type.toLowerCase() === deviceTypeFilter) &&
            (healthFilter === "all" || health === healthFilter) &&
            (!onlyOffline || health === "offline") &&
            (!onlyMismatches || verificationStatuses.some((status) => status !== "VERIFIED")) &&
            (verificationFilter === "all" || verificationStatuses.includes(verificationFilter as VerificationStatus))
        })
        .map((device) => device.id),
    )
    const links = visibleLinks.filter((link) => {
      const item = verificationForLink(link.id)
      const from = visibleDeviceById.get(link.from)
      const to = visibleDeviceById.get(link.to)
      const linkText = [link.label, link.fromPort, link.toPort, from?.name, to?.name, from?.ipAddress, to?.ipAddress].filter(Boolean).join(" ").toLowerCase()
      const status = item?.status ?? (verificationView === "actual" ? "VERIFIED" : "UNKNOWN")
      return deviceMatches.has(link.from) && deviceMatches.has(link.to) &&
        (!query || linkText.includes(query)) &&
        (verificationFilter === "all" || status === verificationFilter) &&
        (!onlyMismatches || status !== "VERIFIED")
    })
    const linkDeviceIds = new Set(links.flatMap((link) => [link.from, link.to]))
    return {
      devices: visibleDevices.filter((device) => deviceMatches.has(device.id) || linkDeviceIds.has(device.id)),
      links,
    }
  }, [deviceHealth, deviceTypeFilter, healthFilter, onlyMismatches, onlyOffline, searchQuery, verification, verificationFilter, verificationView, visibleDevices, visibleDeviceById, visibleLinks, verificationByLinkId])
  const filteredDevices = filteredTopology.devices
  const filteredLinks = filteredTopology.links
  const focusVerification = (item: { manualLink?: Link; actualLink?: Link }) => {
    const link = item.manualLink ?? item.actualLink
    if (!link) return
    setVerificationView("compare")
    setSelectedLinkId(link.id)
    setSelectedId(link.from)
    setSelectedIds([link.from, link.to])
  }
  const interfacePoint = (deviceId: string, rawPort: string) => {
    const device = deviceById.get(deviceId)
    if (!device) return null
    const ports =
      Array.isArray(device.ports) && device.ports.length > 0
        ? device.ports
        : [FALLBACK_PORT]
    const index = Math.max(0, ports.indexOf(rawPort))
    const width = Math.max(260, Math.min(300, device.width ?? 280))
    const height = Math.max(72, Math.min(88, device.height ?? 76))
    const panelWidth = width
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
    if (verificationView === "actual") return
    const point = canvasPoint(
      event as unknown as React.PointerEvent<SVGSVGElement>,
    )
    if (!point) return
    event.preventDefault()
    svgRef.current?.setPointerCapture?.(event.pointerId)
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
    if (verificationView === "actual") return
    const point = canvasPoint(
      event as unknown as React.PointerEvent<SVGSVGElement>,
    )
    if (!point) return
    event.preventDefault()
    svgRef.current?.setPointerCapture?.(event.pointerId)
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
    if (panState) {
      const rect = svgRef.current?.getBoundingClientRect()
      if (rect) {
        const scaleX = (CANVAS_WIDTH / canvasZoom) / rect.width
        const scaleY = (CANVAS_HEIGHT / canvasZoom) / rect.height
        setCanvasPan({
          x: panState.originX + (event.clientX - panState.startX) * scaleX,
          y: panState.originY + (event.clientY - panState.startY) * scaleY,
        })
      }
      return
    }
    if (selectionBox) {
      setSelectionBox({ start: selectionBox.start, end: point })
      return
    }
    if (dragState) {
      setWorkspace((current) => ({
        ...current,
        devices: current.devices.map((device) =>
          device.id === dragState.id
            ? {
                ...device,
                x: Math.max(40, Math.min(CANVAS_WIDTH - 40, snapToGrid ? Math.round((point.x - dragState.offsetX) / 24) * 24 : point.x - dragState.offsetX)),
                y: Math.max(40, Math.min(CANVAS_HEIGHT - 40, snapToGrid ? Math.round((point.y - dragState.offsetY) / 24) * 24 : point.y - dragState.offsetY)),
              }
            : device,
        ),
      }))
      return
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

  const startCanvasPointer = (event: React.PointerEvent<SVGSVGElement>) => {
    const target = event.target as SVGElement
    if (event.target !== event.currentTarget && target.getAttribute("data-canvas-background") !== "true") return
    const point = canvasPoint(event)
    if (!point) return
    if (event.altKey || event.shiftKey) {
      setPanState({
        startX: event.clientX,
        startY: event.clientY,
        originX: canvasPan.x,
        originY: canvasPan.y,
      })
      return
    }
    setSelectedId(null)
    setSelectedIds([])
    setSelectedLinkId(null)
    setSelectionBox({ start: point, end: point })
  }

  const finishCanvasPointer = () => {
    if (selectionBox) {
      const left = Math.min(selectionBox.start.x, selectionBox.end.x)
      const right = Math.max(selectionBox.start.x, selectionBox.end.x)
      const top = Math.min(selectionBox.start.y, selectionBox.end.y)
      const bottom = Math.max(selectionBox.start.y, selectionBox.end.y)
      const ids = workspace.devices
        .filter((device) => device.x >= left && device.x <= right && device.y >= top && device.y <= bottom)
        .map((device) => device.id)
      if (ids.length) {
        setSelectedIds(ids)
        setSelectedId(ids[ids.length - 1])
      }
    }
    setSelectionBox(null)
    setPanState(null)
    setDragState(null)
    setResizeState(null)
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
        const effectivePortNames = portNames.length > 0 ? portNames : [FALLBACK_PORT]
        if (portNames.length === 0) setPortsError(null)
        setWorkspace((current) => ({
          ...current,
          devices: current.devices.map((device) =>
            device.id === selected.id
              ? { ...device, ports: effectivePortNames, portStatuses }
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

  const importAvailableDevice = (raw: SNMPDeviceListItem | undefined) => {
    if (!raw) return
    const id = `real-${raw.id}`
    const category = inventoryCategory(raw)
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
              type: category === "Others" ? "Network device" : category,
              tone: "#00d4ff",
              x: 150 + (current.devices.length % 4) * 220,
              y: 120 + Math.floor(current.devices.length / 4) * 120,
            },
          ],
    }))
    setSelectedId(id)
    setSelectedIds([id])
  }

  const startNew = (deviceType = "Switch") => {
    const index = workspace.devices.length
    setEditing({
      id: `device-${Date.now()}`,
      name: "NEW DEVICE",
      subtitle: "Add IP / VLAN",
      ipAddress: "",
      macAddress: "",
      location: "",
      type: deviceType,
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
    if (sourcePort && isPortOccupied(workspace.links, sourcePort.deviceId, sourcePort.port)) {
      toast.warning("This port is already connected to another device.")
      setSourcePort(null)
      setConnectMode(false)
      return
    }
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
    const existingDevice = workspace.devices.find((device) => device.id === editing.id)
    const connectedLinks = existingDevice
      ? workspace.links.filter((link) => link.from === editing.id || link.to === editing.id)
      : []
    const identityChanged = existingDevice && [
      existingDevice.name !== nextDevice.name,
      existingDevice.ipAddress !== nextDevice.ipAddress,
      existingDevice.macAddress !== nextDevice.macAddress,
      existingDevice.location !== nextDevice.location,
      existingDevice.type !== nextDevice.type,
      JSON.stringify(existingDevice.ports ?? []) !== JSON.stringify(nextDevice.ports ?? []),
    ].some(Boolean)
    const commitDevice = () => {
      setWorkspace((current) => ({
        ...current,
        devices: current.devices.some((device) => device.id === editing.id)
          ? current.devices.map((device) => device.id === editing.id ? nextDevice : device)
          : [...current.devices, nextDevice],
        links: autoLink ? [...current.links, autoLink] : current.links,
      }))
      setEditing(null)
      if (nextDevice.backendId) {
        void updateDevice(nextDevice.backendId, {
          hostname: nextDevice.name,
          ip_address: nextDevice.ipAddress,
          mac_address: nextDevice.macAddress || undefined,
          topology_metadata: { location: nextDevice.location || null },
        }).catch(() => setPortsError("Device details could not be saved to the database"))
      }
      if (autoLink) {
        setSourcePort(null)
        setConnectFrom(null)
        setConnectMode(false)
      }
    }
    if (autoLink) {
      requestConfirmation({
        title: "Create physical connection?",
        description: "Review the new manual link before it is added to the topology.",
        details: [["Current state", "No connection"], ["Proposed", `${displayPort(sourcePort.deviceId, sourcePort.port)} ↔ ${displayPort(nextDevice.id, autoLink.toPort ?? FALLBACK_PORT)}`], ["Impact", "Adds one manual topology connection"]],
        confirmLabel: "Confirm Change",
        tone: "amber",
        onConfirm: commitDevice,
      })
      return
    }
    if (identityChanged) {
      requestConfirmation({
        title: "Change device identity?",
        description: "These details are used to identify this device in the manual topology.",
        details: [["Current", `${existingDevice.name} · ${existingDevice.ipAddress || existingDevice.subtitle || "No IP"}`], ["Proposed", `${nextDevice.name} · ${nextDevice.ipAddress || "No IP"}`], ["Connected links", connectedLinks.length ? connectedLinks.map((link) => `${link.fromPort ?? FALLBACK_PORT} ↔ ${link.toPort ?? FALLBACK_PORT}`).join(", ") : "None"], ["Proposed ports", nextDevice.ports?.join(", ") || "None"], ["Impact", nextDevice.backendId ? "Updates the linked SNMP device details; existing link endpoints stay stored" : "Updates the manual device record; existing link endpoints stay stored"]],
        confirmLabel: "Confirm Change",
        tone: "amber",
        onConfirm: commitDevice,
      })
      return
    }
    commitDevice()
  }

  const deleteSelected = (requestedId = selectedId) => {
    if (!requestedId) return
    const device = workspace.devices.find((item) => item.id === requestedId)
    if (!device) return
    const connectedLinks = workspace.links.filter((link) => link.from === requestedId || link.to === requestedId)
    const connectedPorts = connectedLinks.map((link) => `${link.from === requestedId ? device.name : workspace.devices.find((item) => item.id === link.from)?.name ?? "Unknown"} ${link.from === requestedId ? link.fromPort ?? FALLBACK_PORT : link.toPort ?? FALLBACK_PORT}`).join(", ") || "None"
    const commitDelete = () => {
      setWorkspace((current) => ({
        devices: current.devices.filter((item) => item.id !== requestedId),
        links: current.links.filter((link) => link.from !== requestedId && link.to !== requestedId),
      }))
      setSelectedId(null)
      setSelectedIds([])
      setEditing(null)
      setConnectFrom(null)
      setConnectMode(false)
      setSourcePort(null)
    }
    requestConfirmation({
      title: "Delete this device?",
      description: connectedLinks.length ? "This device has connected topology links. Review the permanent removal before continuing." : "This removes the device from the manual topology.",
      details: [["Device", device.name], ["IP address", device.ipAddress || device.subtitle || "Not set"], ["Connected links", String(connectedLinks.length)], ["Connected ports", connectedPorts], ["Backend / SNMP", device.backendId ? `Yes · device #${device.backendId}` : "No · manual-only device"], ["Will be removed", connectedLinks.length ? "Device record and every attached manual connection" : "Manual device record"]],
      confirmLabel: "Review Deletion",
      tone: "red",
      secondStep: connectedLinks.length ? { title: "Confirm permanent topology removal?", description: "The manual links listed above will be deleted with this device. Live SNMP data will not be changed.", confirmLabel: "Delete Device" } : undefined,
      onConfirm: commitDelete,
    })
  }

  const disconnectLink = (linkId: string) => {
    const link = workspace.links.find((item) => item.id === linkId)
    if (!link) return
    const from = workspace.devices.find((device) => device.id === link.from)
    const to = workspace.devices.find((device) => device.id === link.to)
    requestConfirmation({
      title: "Delete physical connection?",
      description: "This removes the link from the manual topology only.",
      details: [["Current", `${from?.name ?? link.from} ${link.fromPort ?? FALLBACK_PORT} ↔ ${to?.name ?? link.to} ${link.toPort ?? FALLBACK_PORT}`], ["Proposed", "No manual connection"], ["Impact", "The live SNMP topology is unchanged"]],
      confirmLabel: "Confirm Change",
      tone: "red",
      onConfirm: () => {
        setWorkspace((current) => ({ ...current, links: current.links.filter((item) => item.id !== linkId) }))
        setSelectedLinkId(null)
      },
    })
  }

  const toggleLinkGeometry = (linkId: string) => {
    setWorkspace((current) => ({
      ...current,
      links: current.links.map((link) =>
        link.id === linkId
          ? { ...link, geometry: link.geometry === "straight" ? "curved" : "straight" }
          : link,
      ),
    }))
  }

  const applyResolvedChange = async (
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

  const resolveChange = (change: ManualTopologyChange, action: "accept_real_change" | "keep_manual") => {
    if (action !== "accept_real_change") {
      void applyResolvedChange(change, action)
      return
    }
    requestConfirmation({
      title: "Accept physical topology change?",
      description: "Manual topology differs from the physical network. Live SNMP data will replace the affected manual baseline only after confirmation.",
      details: [["Detected change", changeDescription(change)], ["Expected", changeStateLabel(change.expected)], ["Observed", changeStateLabel(change.observed)], ["Alternative", "Keep manual topology and continue monitoring"]],
      confirmLabel: "Accept Real Change",
      tone: "amber",
      onConfirm: () => { void applyResolvedChange(change, action) },
    })
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

  const selectNode = (id: string, additive = false) => {
    setSelectedIds((current) => additive
      ? current.includes(id) ? current.filter((item) => item !== id) : [...current, id]
      : [id])
    setSelectedId(id)
    if (!connectMode) return
    setConnectFrom(id)
  }

  const undo = () => {
    const previous = historyRef.current.pop()
    if (!previous) return
    futureRef.current.push(workspace)
    historyApplyingRef.current = true
    setWorkspace(previous)
  }

  const redo = () => {
    const next = futureRef.current.pop()
    if (!next) return
    historyRef.current.push(workspace)
    historyApplyingRef.current = true
    setWorkspace(next)
  }

  const fitCanvas = () => {
    if (!workspace.devices.length) {
      setCanvasZoom(1)
      setCanvasPan({ x: 0, y: 0 })
      return
    }
    const bounds = workspace.devices.reduce(
      (acc, device) => ({
        minX: Math.min(acc.minX, device.x),
        minY: Math.min(acc.minY, device.y),
        maxX: Math.max(acc.maxX, device.x),
        maxY: Math.max(acc.maxY, device.y),
      }),
      { minX: Infinity, minY: Infinity, maxX: -Infinity, maxY: -Infinity },
    )
    const width = Math.max(360, bounds.maxX - bounds.minX + 300)
    const height = Math.max(280, bounds.maxY - bounds.minY + 180)
    setCanvasZoom(Math.max(0.6, Math.min(1.8, Math.min(CANVAS_WIDTH / width, CANVAS_HEIGHT / height))))
    setCanvasPan({
      x: (bounds.minX + bounds.maxX) / 2 - CANVAS_WIDTH / 2,
      y: (bounds.minY + bounds.maxY) / 2 - CANVAS_HEIGHT / 2,
    })
  }

  const autoLayout = () => {
    if (verificationView === "actual" || workspace.devices.length === 0) return
    setWorkspace((current) => ({
      ...current,
      devices: current.devices.map((device, index) => ({
        ...device,
        x: 150 + (index % 4) * 230,
        y: 110 + Math.floor(index / 4) * 130,
      })),
    }))
    setCanvasZoom(1)
    setCanvasPan({ x: 0, y: 0 })
  }

  const downloadFile = (content: BlobPart, fileName: string, type: string) => {
    const url = URL.createObjectURL(new Blob([content], { type }))
    const anchor = document.createElement("a")
    anchor.href = url
    anchor.download = fileName
    anchor.click()
    URL.revokeObjectURL(url)
  }

  const exportSvg = () => {
    if (!svgRef.current) return
    const clone = svgRef.current.cloneNode(true) as SVGSVGElement
    clone.setAttribute("xmlns", "http://www.w3.org/2000/svg")
    clone.setAttribute("width", "1200")
    clone.setAttribute("height", "720")
    downloadFile(new XMLSerializer().serializeToString(clone), "manual-topology.svg", "image/svg+xml")
  }

  const exportPng = () => {
    if (!svgRef.current) return
    const clone = svgRef.current.cloneNode(true) as SVGSVGElement
    clone.setAttribute("xmlns", "http://www.w3.org/2000/svg")
    clone.setAttribute("width", "1200")
    clone.setAttribute("height", "720")
    const svgUrl = URL.createObjectURL(new Blob([new XMLSerializer().serializeToString(clone)], { type: "image/svg+xml" }))
    const image = new Image()
    image.onload = () => {
      const canvas = document.createElement("canvas")
      canvas.width = 1200
      canvas.height = 720
      canvas.getContext("2d")?.drawImage(image, 0, 0)
      canvas.toBlob((blob) => blob && downloadFile(blob, "manual-topology.png", "image/png"))
      URL.revokeObjectURL(svgUrl)
    }
    image.src = svgUrl
  }

  const openContextMenu = (event: React.MouseEvent<SVGGElement>, target: Pick<ContextMenuState, "deviceId" | "linkId">) => {
    event.preventDefault()
    event.stopPropagation()
    setContextMenu({ x: event.clientX, y: event.clientY, ...target })
  }

  const deviceTypes = useMemo(() => Array.from(new Set(workspace.devices.map((device) => device.type.toLowerCase()))).sort(), [workspace.devices])
  const inventoryItems = useMemo(() => realDevices.map((device) => {
    const canvasDevice = workspace.devices.find((item) => item.backendId === device.id)
    const categorySource = canvasDevice
      ? { ...device, name: canvasDevice.name, hostname: canvasDevice.name, device_type: canvasDevice.type }
      : device
    return { device, canvasDevice, category: inventoryCategory(categorySource) }
  }), [realDevices, workspace.devices])

  const createPaletteDevice = (type: string, point?: { x: number; y: number }) => {
    const index = workspace.devices.length
    const deviceType = type === "Internet / Cloud" ? "Cloud" : type
    const id = `device-${Date.now()}`
    const device: Device = {
      id,
      name: `${deviceType.toUpperCase()} ${String(index + 1).padStart(2, "0")}`,
      subtitle: "Add IP / VLAN",
      type: deviceType,
      tone: tones[index % tones.length],
      x: point?.x ?? 150 + (index % 4) * 220,
      y: point?.y ?? 120 + Math.floor(index / 4) * 120,
      ports: ["Gi0/1", "Gi0/2"],
    }
    setWorkspace((current) => ({ ...current, devices: [...current.devices, device] }))
    setSelectedId(id)
    setSelectedIds([id])
    setEditing(device)
  }

  const handleCanvasDrop = (event: React.DragEvent<SVGSVGElement>) => {
    event.preventDefault()
    const type = event.dataTransfer.getData("manual-topology/device-type")
    const point = canvasPoint(event as unknown as React.PointerEvent<SVGSVGElement>)
    if (type && point) createPaletteDevice(type, point)
  }

  const selectPort = (deviceId: string, port: string) => {
    if (!connectMode) {
      if (isPortOccupied(workspace.links, deviceId, port)) {
        toast.warning("This port is already connected to another device.")
        return
      }
      setConnectMode(true)
      setConnectFrom(deviceId)
      setConnectionPointer(interfacePoint(deviceId, port))
      return setSourcePort({ deviceId, port })
    }
    if (!sourcePort) return setSourcePort({ deviceId, port })
    if (sourcePort.deviceId === deviceId) {
      if (sourcePort.port !== port && isPortOccupied(workspace.links, deviceId, port)) {
        toast.warning("This port is already connected to another device.")
        return
      }
      return setSourcePort({ deviceId, port })
    }
    if (isPortOccupied(workspace.links, deviceId, port) ||
        isPortOccupied(workspace.links, sourcePort.deviceId, sourcePort.port)) {
      toast.warning("This port is already connected to another device.")
      return
    }
    const proposedLink: Link = {
      id: `link-${Date.now()}`,
      from: sourcePort.deviceId,
      to: deviceId,
      fromPort: sourcePort.port,
      toPort: port,
      label: `${displayPort(sourcePort.deviceId, sourcePort.port)} → ${displayPort(deviceId, port)}`,
    }
    requestConfirmation({
      title: "Create physical connection?",
      description: "Review both physical endpoints before adding this manual link.",
      details: [["Current", "No manual connection"], ["Proposed", `${displayPort(sourcePort.deviceId, sourcePort.port)} ↔ ${displayPort(deviceId, port)}`], ["Impact", "Adds one manual topology connection"]],
      confirmLabel: "Confirm Change",
      tone: "amber",
      onConfirm: () => {
        setWorkspace((current) => {
          if (isPortOccupied(current.links, deviceId, port) || isPortOccupied(current.links, proposedLink.from, proposedLink.fromPort ?? FALLBACK_PORT)) return current
          return { ...current, links: [...current.links, proposedLink] }
        })
        setSourcePort(null)
        setConnectFrom(null)
        setConnectMode(false)
        setConnectionPointer(null)
      },
    })
  }

  const beginPortConnection = (deviceId: string, port: string) => {
    if (isPortOccupied(workspace.links, deviceId, port) &&
        !(sourcePort?.deviceId === deviceId && sourcePort.port === port)) {
      toast.warning("This port is already connected to another device.")
      return
    }
    if (!connectMode || !sourcePort || sourcePort.deviceId === deviceId) {
      setConnectMode(true)
      setConnectFrom(deviceId)
      setSourcePort({ deviceId, port })
      setConnectionPointer(interfacePoint(deviceId, port))
    }
  }

  const toggleCanvasFullscreen = async () => {
    if (!workspaceGridRef.current) return
    try {
      if (document.fullscreenElement) {
        await document.exitFullscreen()
      } else {
        await workspaceGridRef.current.requestFullscreen()
      }
    } catch {
      // Fullscreen is optional on browsers that do not allow the API.
      setIsCanvasFullscreen((value) => !value)
    }
  }

  useEffect(() => {
    const handleFullscreenChange = () => setIsCanvasFullscreen(document.fullscreenElement === workspaceGridRef.current)
    document.addEventListener("fullscreenchange", handleFullscreenChange)
    return () => document.removeEventListener("fullscreenchange", handleFullscreenChange)
  }, [])

  useEffect(() => {
    const closeContextMenu = () => setContextMenu(null)
    window.addEventListener("click", closeContextMenu)
    return () => window.removeEventListener("click", closeContextMenu)
  }, [])

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement
      if (target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)) return
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "z") {
        event.preventDefault()
        event.shiftKey ? redo() : undo()
      } else if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "y") {
        event.preventDefault()
        redo()
      } else if (event.key === "Delete" || event.key === "Backspace") {
        if (selectedId) deleteSelected()
        else if (selectedLinkId) disconnectLink(selectedLinkId)
      } else if (event.key === "Escape") {
        setContextMenu(null)
        setSelectedId(null)
        setSelectedIds([])
        setSelectedLinkId(null)
        setConnectMode(false)
        setSourcePort(null)
        setSelectionBox(null)
      } else if (event.key === "/") {
        event.preventDefault()
        searchInputRef.current?.focus()
      } else if (event.key.toLowerCase() === "f") {
        event.preventDefault()
        fitCanvas()
      } else if (event.key.toLowerCase() === "l") {
        event.preventDefault()
        autoLayout()
      }
    }
    window.addEventListener("keydown", handleKeyDown)
    return () => window.removeEventListener("keydown", handleKeyDown)
  }, [selectedId, selectedLinkId, workspace])

  return (
    <main className="manual-topology-shell min-h-full overflow-y-auto" style={{ background: "var(--t-bg)", color: "var(--t-text)" }}>
      <div className="w-full max-w-[2400px] mx-auto space-y-3 p-3 md:p-5 2xl:p-7">
        <header
          className="flex flex-col xl:flex-row xl:items-center justify-between gap-4 rounded-xl px-4 py-3"
          style={{
            background: "var(--t-card)",
            border: "1px solid var(--t-border-alpha)",
            boxShadow: "0 18px 50px var(--topology-node-shadow)",
          }}
        >
          <div>
            <div
              className="font-mono text-[10px] tracking-[.24em] uppercase"
              style={{ color: "#b7c0ba" }}
            >
              Network workspace / manual design board
            </div>
            <h1
              className="font-display text-2xl md:text-3xl font-semibold tracking-wide mt-1"
              style={{ color: "var(--t-text)" }}
            >
              Manual Topology <span style={{ color: "var(--t-muted)" }}>·</span>{" "}
              <span style={{ color: "#9bb5a3" }}>Design Board</span>
            </h1>
            <p
              className="font-mono text-[10px] mt-1 max-w-2xl"
              style={{ color: "#8e9690" }}
            >
              Arrange devices, connect physical ports, and keep a clean network
              record with live health context.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <span
              className="px-2.5 py-1.5 rounded-md font-mono text-[10px] uppercase"
              style={{
                color: "#9bd3ad",
                background: "rgba(121,198,154,.08)",
                border: "1px solid rgba(121,198,154,.24)",
              }}
            >
              {workspace.devices.length} devices
            </span>
            <span
              className="px-2.5 py-1.5 rounded-md font-mono text-[10px] uppercase"
              style={{
                color: "#d0a65a",
                background: "rgba(208,166,90,.08)",
                border: "1px solid rgba(208,166,90,.28)",
              }}
            >
              {workspace.links.length} links
            </span>
            <button
              type="button"
              onClick={startNew}
              className="px-3 py-2 rounded-md font-mono text-[10px] font-semibold"
              style={{ color: "var(--t-bg)", background: "var(--t-accent)" }}
            >
              + ADD DEVICE
            </button>
          </div>
        </header>

        <div
          className="flex flex-wrap items-center justify-between gap-3 rounded-lg px-4 py-2.5"
          style={{
            background: "var(--t-card)",
            border: "1px solid var(--t-border-alpha)",
          }}
        >
          <div className="flex items-center gap-2 min-w-0">
            <span className="w-2 h-2 rounded-full animate-pulse" style={{ background: "#00ff88", boxShadow: "0 0 10px #00ff88" }} />
            <span className="font-mono text-[10px] uppercase tracking-widest" style={{ color: "var(--t-muted)" }}>Canvas ready</span>
            <span className="font-mono text-[10px] truncate" style={{ color: "var(--t-text)" }}>Drag an available device from Library to import it</span>
          </div>
          <span className="font-mono text-[9px] uppercase" style={{ color: "var(--t-muted)" }}>Auto-save enabled</span>
        </div>

        <section className="rounded-lg p-3 md:p-4" style={{ background: "var(--t-card)", border: "1px solid var(--t-border-alpha)" }} aria-label="Topology filters and tools">
          <div className="flex flex-col xl:flex-row xl:items-center gap-2">
            <label className="relative flex-1 min-w-[220px]">
              <span className="sr-only">Search devices and connections</span>
              <svg aria-hidden="true" className="absolute left-3 top-2.5 h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="#7f8984" strokeWidth="1.8"><circle cx="11" cy="11" r="6.5" /><path d="m16 16 5 5" /></svg>
              <input ref={searchInputRef} value={searchQuery} onChange={(event) => setSearchQuery(event.target.value)} placeholder="Search hostname / IP / MAC / connection · press /" className="w-full rounded-md py-2 pl-9 pr-3 font-mono text-[10px] outline-none" style={{ color: "var(--t-text)", background: "var(--t-bg)", border: "1px solid var(--t-border-alpha)" }} />
            </label>
            <select aria-label="Filter by device type" value={deviceTypeFilter} onChange={(event) => setDeviceTypeFilter(event.target.value)} className="rounded-md px-2.5 py-2 font-mono text-[10px] uppercase" style={{ color: "var(--t-text)", background: "var(--t-bg)", border: "1px solid var(--t-border-alpha)" }}>
              <option value="all">All types</option>
              {deviceTypes.map((type) => <option key={type} value={type}>{type}</option>)}
            </select>
            <select aria-label="Filter by health status" value={healthFilter} onChange={(event) => setHealthFilter(event.target.value)} className="rounded-md px-2.5 py-2 font-mono text-[10px] uppercase" style={{ color: "var(--t-text)", background: "var(--t-bg)", border: "1px solid var(--t-border-alpha)" }}>
              <option value="all">All health</option><option value="online">Online</option><option value="offline">Offline</option><option value="unknown">Unknown</option>
            </select>
            <select aria-label="Filter by verification status" value={verificationFilter} onChange={(event) => setVerificationFilter(event.target.value)} className="rounded-md px-2.5 py-2 font-mono text-[10px] uppercase" style={{ color: "var(--t-text)", background: "var(--t-bg)", border: "1px solid var(--t-border-alpha)" }}>
              <option value="all">All verification</option>
              {(["VERIFIED", "DISCONNECTED", "UNEXPECTED", "PORT_MISMATCH", "DEVICE_OFFLINE", "UNKNOWN"] as const).map((status) => <option key={status} value={status}>{status.replace("_", " ")}</option>)}
            </select>
            <button type="button" onClick={() => setOnlyMismatches((value) => !value)} aria-pressed={onlyMismatches} className="rounded-md px-2.5 py-2 font-mono text-[10px] uppercase" style={{ color: onlyMismatches ? "#d0a65a" : "#9ba59f", background: onlyMismatches ? "rgba(208,166,90,.12)" : "transparent", border: `1px solid ${onlyMismatches ? "rgba(208,166,90,.4)" : "rgba(231,225,213,.16)"}` }}>Mismatches</button>
            <button type="button" onClick={() => setOnlyOffline((value) => !value)} aria-pressed={onlyOffline} className="rounded-md px-2.5 py-2 font-mono text-[10px] uppercase" style={{ color: onlyOffline ? "#da6b6b" : "#9ba59f", background: onlyOffline ? "rgba(218,107,107,.12)" : "transparent", border: `1px solid ${onlyOffline ? "rgba(218,107,107,.4)" : "rgba(231,225,213,.16)"}` }}>Offline only</button>
            <button type="button" onClick={() => { setSearchQuery(""); setDeviceTypeFilter("all"); setHealthFilter("all"); setVerificationFilter("all"); setOnlyMismatches(false); setOnlyOffline(false) }} className="rounded-md px-2.5 py-2 font-mono text-[10px] uppercase" style={{ color: "#9ba59f", border: "1px solid rgba(231,225,213,.16)" }}>Clear</button>
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 font-mono text-[9px] uppercase" style={{ color: "#7f8984" }}>
            <span>{filteredDevices.length} devices · {filteredLinks.length} connections shown</span>
            <span className="inline-flex items-center gap-1.5"><i className="h-2 w-2 rounded-full" style={{ background: "#79c69a" }} /> verified</span>
            <span className="inline-flex items-center gap-1.5"><i className="h-2 w-2 rounded-full" style={{ background: "#d7aa59" }} /> mismatch / pending</span>
            <span className="inline-flex items-center gap-1.5"><i className="h-2 w-2 rounded-full" style={{ background: "#da6b6b" }} /> offline / unexpected</span>
            <span className="ml-auto" style={{ color: reconcileLoading ? "#d0a65a" : actualTopology ? "#7f8984" : "#da6b6b" }}>{reconcileLoading ? "Verifying live SNMP topology..." : actualTopology ? `Last verification ${new Date(actualTopology.timestamp ?? Date.now()).toLocaleString()}` : "SNMP verification not available"}</span>
          </div>
        </section>

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

        <GlassCard className="p-4 md:p-5" style={{ border: `1px solid ${verificationCounts.issues ? "rgba(215,170,89,.28)" : "rgba(121,198,154,.24)"}` }}>
          <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
            <div>
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full" style={{ background: verificationCounts.issues ? "#d7aa59" : "#79c69a" }} />
                <h2 className="font-display text-lg font-semibold" style={{ color: "#e7e1d5" }}>Topology Verification</h2>
              </div>
              <p className="font-mono text-[10px] mt-1" style={{ color: "#8e9690" }}>
                {actualTopology ? `Manual baseline compared with live SNMP physical topology · ${verificationView.toUpperCase()} VIEW` : "Run live reconciliation to compare the manual baseline with SNMP physical connectivity."}
              </p>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 min-w-0">
              {[
                [verificationCounts.total, "Manual links", "#d8d2c6"],
                [verificationCounts.verified, "Verified", "#79c69a"],
                [verificationCounts.issues, "Mismatched", "#d7aa59"],
                [verificationCounts.unexpected, "Unexpected", "#da6b6b"],
                [verificationCounts.offline, "Offline", "#da6b6b"],
              ].map(([value, label, color]) => (
                <div key={label} className="rounded-md px-3 py-2 min-w-[82px]" style={{ background: "#121615", border: "1px solid rgba(231,225,213,.10)" }}>
                  <div className="font-mono text-lg" style={{ color: String(color) }}>{value}</div>
                  <div className="font-mono text-[8px] uppercase tracking-wider" style={{ color: "#7f8984" }}>{label}</div>
                </div>
              ))}
            </div>
          </div>
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 mt-4 pt-3" style={{ borderTop: "1px solid rgba(231,225,213,.08)" }}>
            <span className="font-mono text-[9px] uppercase" style={{ color: "#7f8984" }}>Last verification: {actualTopology?.timestamp ? new Date(actualTopology.timestamp).toLocaleString() : "NOT RUN"}</span>
            <div className="flex flex-wrap gap-2">
              {verification.filter((item) => item.status !== "VERIFIED").slice(0, 6).map((item) => {
                const meta = statusMeta(item.status)
                return <button key={item.id} type="button" onClick={() => focusVerification(item)} className="rounded-md px-2.5 py-1.5 font-mono text-[9px] uppercase" style={{ color: meta.color, border: `1px solid ${meta.color}55`, background: `${meta.color}10` }} title="Focus issue on canvas">{meta.icon} {meta.label}</button>
              })}
            </div>
          </div>
        </GlassCard>

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

        <div
          ref={workspaceGridRef}
          className={isCanvasFullscreen
            ? "fixed inset-0 z-50 grid lg:grid-cols-[190px_minmax(0,1fr)_320px] gap-3 items-stretch p-4 md:p-6 overflow-hidden"
            : "grid lg:grid-cols-[190px_minmax(0,1fr)_320px] gap-3 items-stretch"}
          style={isCanvasFullscreen ? { background: "var(--t-bg)" } : undefined}
        >
          <aside
            className={isCanvasFullscreen ? "flex flex-col rounded-xl p-3 gap-1.5 min-h-0 overflow-y-auto" : "hidden lg:flex flex-col rounded-xl p-3 gap-1.5"}
            style={{
              background: "var(--t-card)",
              border: "1px solid var(--t-border-alpha)",
            }}
          >
            <div className="flex items-center justify-between px-1 py-1">
              <div>
                <div className="font-mono text-[9px] uppercase tracking-[.18em]" style={{ color: "var(--t-text)" }}>Palette</div>
                <div className="font-mono text-[8px] mt-1" style={{ color: "#7f8984" }}>Drag to canvas</div>
              </div>
              <button type="button" onClick={() => setPaletteCollapsed((value) => !value)} className="rounded p-1" style={{ color: "#9ba59f" }} aria-label="Collapse device palette">
                {paletteCollapsed ? "›" : "‹"}
              </button>
            </div>
            {!paletteCollapsed && paletteItems.map(([label, type], index) => {
              const category = type === "Network device" ? (label === "Others" ? "Others" : label) : type === "Internet / Cloud" ? "Cloud" : type
              const matchingDevices = inventoryItems.filter((item) => item.category === category)
              const expanded = expandedPaletteCategories[label] === true
              return (
                <div key={label}>
                  <div className="flex items-center gap-1">
                    <button
                      type="button"
                      draggable
                      onDragStart={(event) => event.dataTransfer.setData("manual-topology/device-type", type)}
                      onClick={() => setExpandedPaletteCategories((current) => ({ ...current, [label]: !current[label] }))}
                      className="flex min-w-0 flex-1 items-center gap-3 rounded-lg px-2 py-2 text-left transition-colors hover:bg-white/[.05]"
                      title={matchingDevices.length ? `Show ${label} devices` : `Add ${label} to canvas`}
                      aria-expanded={matchingDevices.length ? expanded : undefined}
                    >
                      <span className="flex h-8 w-8 items-center justify-center rounded-md" style={{ background: "#202624", border: "1px solid rgba(231,225,213,.12)" }}>
                        <svg width="28" height="28" viewBox="0 0 48 48"><DeviceGlyph type={type} tone={tones[index % tones.length]} /></svg>
                      </span>
                      <span className="min-w-0">
                        <span className="block font-mono text-[10px]" style={{ color: "var(--t-text)" }}>{label}{matchingDevices.length > 0 && <span style={{ color: "var(--t-muted)" }}> ({matchingDevices.length})</span>}</span>
                        <span className="mt-0.5 block font-mono text-[8px]" style={{ color: "#7f8984" }}>{matchingDevices.length ? (expanded ? "HIDE DEVICES" : "SHOW DEVICES") : "NODE"}</span>
                      </span>
                    </button>
                    <button type="button" onClick={() => startNew(type)} className="rounded px-1.5 py-1 font-mono text-[11px]" style={{ color: "#9bb5a3" }} title={`Add new ${label}`} aria-label={`Add new ${label}`}>+</button>
                  </div>
                  {expanded && matchingDevices.map(({ device, canvasDevice }, deviceIndex) => {
                    const deviceLabel = canvasDevice?.name || device.hostname || device.name || device.ip_address
                    const deviceType = canvasDevice?.type || device.device_type || category
                    const imported = Boolean(canvasDevice)
                    return (
                      <button
                        type="button"
                        key={device.id}
                        onClick={() => importAvailableDevice(device)}
                        className="ml-11 flex w-[calc(100%-2.75rem)] items-center gap-2 rounded-md px-1 py-1.5 text-left transition-colors hover:bg-white/5"
                        title={imported ? `${deviceLabel} is already on canvas` : `Import ${deviceLabel}`}
                        style={{ opacity: imported ? 0.55 : 1 }}
                      >
                        <svg width="18" height="18" viewBox="0 0 48 48" className="shrink-0"><DeviceGlyph type={deviceType} tone={tones[(index + deviceIndex + 1) % tones.length]} /></svg>
                        <span className="min-w-0">
                          <span className="block truncate font-mono text-[8px]" style={{ color: "var(--t-text)" }}>{deviceLabel}</span>
                          <span className="block truncate font-mono text-[7px]" style={{ color: "var(--t-muted)" }}>{imported ? "IMPORTED" : device.ip_address}</span>
                        </span>
                      </button>
                    )
                  })}
                </div>
              )
            })}
            <div className="mt-auto pt-2 border-t" style={{ borderColor: "var(--t-border-light)" }}>
              <button type="button" onClick={() => setConnectMode((value) => !value)} className="w-full rounded-lg px-1 py-2.5" style={{ color: connectMode ? PEN_COLOR : "var(--t-muted)", background: connectMode ? PEN_SURFACE : "transparent" }}>
                <svg className="mx-auto" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M6 12h12M12 6v12" /><circle cx="6" cy="12" r="3" /><circle cx="18" cy="12" r="3" /></svg>
                <span className="font-mono text-[9px] block mt-1">{connectMode ? "Cancel" : "Wire"}</span>
              </button>
            </div>
          </aside>

        <div
          className="min-w-0 min-h-0"
        >
        <GlassCard className="overflow-hidden min-w-0 h-full">
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
              <div className="flex items-center gap-1 rounded-md p-1" style={{ border: "1px solid var(--t-border-alpha)", background: "var(--t-bg)" }} aria-label="Topology verification view">
                {(["manual", "actual", "compare"] as const).map((view) => (
                  <button key={view} type="button" onClick={() => setVerificationView(view)} className="px-2.5 py-1.5 rounded font-mono text-[10px] uppercase" style={{ color: verificationView === view ? "var(--t-text)" : "var(--t-muted)", background: verificationView === view ? "var(--t-card)" : "transparent" }} title={`${view} topology view`}>
                    {view}
                  </button>
                ))}
              </div>
              <button
                type="button"
                onClick={() => void toggleCanvasFullscreen()}
                className="px-3 py-1.5 rounded-md font-mono text-[10px] uppercase"
                style={{ color: "var(--t-accent)", border: "1px solid var(--t-accent-border)", background: "var(--t-accent-alpha)" }}
              >
                {isCanvasFullscreen ? "EXIT FULL SCREEN" : "FULL SCREEN"}
              </button>
              <div className="flex items-center gap-1 rounded-md p-1" style={{ border: "1px solid var(--t-border-alpha)", background: "var(--t-bg)" }}>
                <button type="button" onClick={() => setCanvasZoom((value) => Math.max(0.6, Number((value - 0.1).toFixed(1))))} className="w-7 h-6 rounded font-mono text-xs" style={{ color: "var(--t-text)" }} aria-label="Zoom out">−</button>
                <button type="button" onClick={() => setCanvasZoom(1)} className="px-1.5 h-6 rounded font-mono text-[9px]" style={{ color: "var(--t-muted)" }} aria-label="Reset zoom">{Math.round(canvasZoom * 100)}%</button>
                <button type="button" onClick={() => setCanvasZoom((value) => Math.min(1.8, Number((value + 0.1).toFixed(1))))} className="w-7 h-6 rounded font-mono text-xs" style={{ color: "var(--t-text)" }} aria-label="Zoom in">+</button>
              </div>
              <button type="button" onClick={fitCanvas} className="px-3 py-1.5 rounded-md font-mono text-[10px] uppercase" style={{ color: "#d0a65a", border: "1px solid rgba(208,166,90,.28)" }}>FIT</button>
              <button type="button" onClick={autoLayout} disabled={verificationView === "actual"} className="px-3 py-1.5 rounded-md font-mono text-[10px] uppercase disabled:opacity-30" style={{ color: "#9bb5a3", border: "1px solid rgba(155,181,163,.28)" }} title="Auto-layout devices (L)">LAYOUT</button>
              <div className="flex items-center gap-1 rounded-md p-1" style={{ border: "1px solid var(--t-border-alpha)", background: "var(--t-bg)" }} aria-label="Export topology">
                <button type="button" onClick={exportSvg} className="px-2 h-6 rounded font-mono text-[10px]" style={{ color: "var(--t-text)" }} title="Export SVG">SVG</button>
                <button type="button" onClick={exportPng} className="px-2 h-6 rounded font-mono text-[10px]" style={{ color: "var(--t-text)" }} title="Export PNG">PNG</button>
                <button type="button" onClick={() => window.print()} className="px-2 h-6 rounded font-mono text-[10px]" style={{ color: "var(--t-text)" }} title="Print or save as PDF">PDF</button>
              </div>
              <div className="flex items-center gap-1 rounded-md p-1" style={{ border: "1px solid var(--t-border-alpha)", background: "var(--t-bg)" }}>
                <button type="button" onClick={undo} disabled={!historyRef.current.length} className="px-2 h-6 rounded font-mono text-[10px] disabled:opacity-30" style={{ color: "var(--t-text)" }} title="Undo (Ctrl/Cmd+Z)">UNDO</button>
                <button type="button" onClick={redo} disabled={!futureRef.current.length} className="px-2 h-6 rounded font-mono text-[10px] disabled:opacity-30" style={{ color: "var(--t-text)" }} title="Redo (Ctrl/Cmd+Shift+Z)">REDO</button>
              </div>
              <button type="button" onClick={() => setSnapToGrid((value) => !value)} className="px-3 py-1.5 rounded-md font-mono text-[10px] uppercase" style={{ color: snapToGrid ? "#9bd3ad" : "#7f8984", border: `1px solid ${snapToGrid ? "rgba(121,198,154,.35)" : "rgba(231,225,213,.12)"}`, background: snapToGrid ? "rgba(121,198,154,.08)" : "transparent" }}>SNAP {snapToGrid ? "ON" : "OFF"}</button>
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
                disabled={verificationView === "actual" || (!selectedId && !connectMode)}
                className="px-3 py-1.5 rounded-md font-mono text-[10px] uppercase"
                style={{
                  color: connectMode ? PEN_COLOR : "var(--t-accent)",
                  border: "1px solid var(--t-accent-border)",
                  background: connectMode
                    ? PEN_SURFACE
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
                    color: PEN_COLOR,
                    border: `1px solid ${PEN_BORDER}`,
                    background: PEN_SURFACE,
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
              {selectedLinkId && (
                <button
                  type="button"
                  onClick={() => toggleLinkGeometry(selectedLinkId)}
                  className="px-3 py-1.5 rounded-md font-mono text-[10px] uppercase"
                  style={{
                    color: "var(--t-text)",
                    border: "1px solid var(--t-border-alpha)",
                    background: "var(--t-card)",
                  }}
                >
                  CHANGE TO {workspace.links.find((link) => link.id === selectedLinkId)?.geometry === "straight" ? "CURVED" : "STRAIGHT"}
                </button>
              )}
              <button
                type="button"
                onClick={editSelectedDevice}
                disabled={verificationView === "actual" || !selected}
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
                disabled={verificationView === "actual" || !selected}
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
            <div
              className={isCanvasFullscreen
                ? "relative flex-1 min-h-0 min-w-0"
                : "relative min-h-[560px] max-h-[calc(100vh-280px)] min-w-0"}
            >
              <div
                ref={canvasScrollRef}
                className={isCanvasFullscreen
                  ? "h-full min-h-0 overflow-auto overscroll-contain p-3 md:p-5"
                  : "min-h-[560px] max-h-[calc(100vh-280px)] overflow-auto overscroll-contain p-3 md:p-6"}
                style={{
                  backgroundColor: "var(--topology-canvas)",
                  backgroundImage: "radial-gradient(circle, var(--topology-grid-dot) 1px, transparent 1.2px)",
                  backgroundSize: "24px 24px",
                  scrollbarColor: "var(--t-muted) var(--topology-canvas)",
                  scrollbarWidth: "thin",
                  scrollbarGutter: "stable",
                }}
              >
              <svg
                ref={svgRef}
                viewBox={`${CANVAS_WIDTH / 2 - CANVAS_WIDTH / 2 / canvasZoom - canvasPan.x} ${CANVAS_HEIGHT / 2 - CANVAS_HEIGHT / 2 / canvasZoom - canvasPan.y} ${CANVAS_WIDTH / canvasZoom} ${CANVAS_HEIGHT / canvasZoom}`}
                className={isCanvasFullscreen ? "w-full h-full min-h-[520px] rounded-lg" : "w-[1600px] h-[1000px] max-w-none rounded-lg"}
                style={{
                  touchAction: "none",
                  userSelect: "none",
                  background: "transparent",
                  border: "1px solid rgba(231,225,213,.10)",
                  cursor: connectMode
                    ? "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='24' height='24'%3E%3Cpath d='M4 20l4-1L20 7l-3-3L5 16z' fill='%23f4f1ea' stroke='%23101318'/%3E%3C/svg%3E\") 2 22, crosshair"
                    : "default",
                }}
                onPointerDown={startCanvasPointer}
                onPointerMove={moveCanvasItem}
                onPointerUp={finishCanvasPointer}
                onPointerCancel={finishCanvasPointer}
                onPointerLeave={() => {
                  finishCanvasPointer()
                }}
                onDragOver={(event) => event.preventDefault()}
                onDrop={handleCanvasDrop}
                onWheel={(event) => {
                  event.preventDefault()
                  setCanvasZoom((value) => Math.max(0.6, Math.min(1.8, Number((value + (event.deltaY < 0 ? 0.1 : -0.1)).toFixed(1)))))
                }}
                role="img"
                aria-label="Editable manual network topology"
              >
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
                {workspace.devices.length > 0 && filteredDevices.length === 0 && (
                  <g>
                    <text x="480" y="260" textAnchor="middle" fill="var(--t-text)" fontSize="18" fontWeight="700">No matching topology items</text>
                    <text x="480" y="290" textAnchor="middle" fill="var(--t-muted)" fontSize="12" fontFamily="JetBrains Mono, monospace">Clear search or filters to restore the full topology</text>
                  </g>
                )}
                {filteredLinks.map((link) => {
                  const from = visibleDeviceById.get(link.from)
                  const to = visibleDeviceById.get(link.to)
                  if (!from || !to) return null
                  const pairKey = [link.from, link.to].sort().join("::")
                  const parallelLinks = filteredLinks.filter(
                    (candidate) => [candidate.from, candidate.to].sort().join("::") === pairKey,
                  )
                  const lane = parallelLinks.findIndex((candidate) => candidate.id === link.id)
                  const geometry = parallelLinkGeometry(from, to, lane, parallelLinks.length, link.geometry)
                  const verificationItem = verificationForLink(link.id)
                  const linkStatus = verificationItem?.status ?? (verificationView === "actual" ? "VERIFIED" : "UNKNOWN")
                  const linkMeta = statusMeta(linkStatus)
                  return (
                    <g
                      key={link.id}
                      onClick={() => setSelectedLinkId(link.id)}
                      onContextMenu={(event) => openContextMenu(event, { linkId: link.id })}
                      className="cursor-pointer"
                    >
                      <path
                        d={geometry.d}
                        fill="none"
                        stroke="transparent"
                        strokeWidth="12"
                        strokeLinecap="round"
                      />
                      <path
                        d={geometry.d}
                        fill="none"
                        stroke={
                          selectedLinkId === link.id
                            ? "#e7e1d5"
                            : linkMeta.color
                        }
                        strokeOpacity={selectedLinkId === link.id ? ".98" : ".82"}
                        strokeWidth={selectedLinkId === link.id ? "4" : "2.5"}
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeDasharray={linkStatus === "DISCONNECTED" || linkStatus === "PORT_MISMATCH" ? "8 6" : linkStatus === "UNEXPECTED" ? "3 4" : undefined}
                      />
                      <circle
                        cx={geometry.midpoint.x}
                        cy={geometry.midpoint.y}
                        r="4"
                        fill={selectedLinkId === link.id ? "#e7e1d5" : linkMeta.color}
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
                      <title>{`${linkMeta.icon} ${linkMeta.label}: ${link.fromPort || "unknown port"} ↔ ${link.toPort || "unknown port"}`}</title>
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
                      stroke={PEN_COLOR}
                      strokeWidth="2.5"
                      strokeDasharray="7 5"
                      opacity=".95"
                    />
                    <circle
                      cx={connectionPointer.x}
                      cy={connectionPointer.y}
                      r="5"
                      fill="none"
                      stroke={PEN_COLOR}
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
                {filteredDevices.map((device) => (
                  <NodeCard
                    key={device.id}
                    device={device}
                    warning={deviceHasTopologyWarning(device)}
                    selected={
                      selectedIds.includes(device.id) || connectFrom === device.id
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
                      if (verificationView === "actual") return
                      setSelectedId(device.id)
                      selectPort(device.id, port)
                    }}
                    onPortPointerDown={(port) =>
                      verificationView === "actual" ? undefined : beginPortConnection(device.id, port)
                    }
                    onDragStart={(event) => startDrag(device, event)}
                    onResizeStart={(event) => startResize(device, event)}
                    onContextMenu={(event) => openContextMenu(event, { deviceId: device.id })}
                    sourcePort={sourcePort}
                    onClick={(event) => verificationView === "actual" ? selectNode(device.id) : selectNode(device.id, event.shiftKey)}
                  />
                ))}
                {filteredLinks.map((link) => {
                  const from = visibleDeviceById.get(link.from)
                  const to = visibleDeviceById.get(link.to)
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
                  const fromLabelWidth = Math.max(54, fromPort.length * 5.5 + 16)
                  const toLabelWidth = Math.max(54, toPort.length * 5.5 + 16)
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
                          x={-fromLabelWidth / 2}
                          y="-11"
                          width={fromLabelWidth}
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
                          x={-toLabelWidth / 2}
                          y="-11"
                          width={toLabelWidth}
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
                {selectionBox && (
                  <rect
                    x={Math.min(selectionBox.start.x, selectionBox.end.x)}
                    y={Math.min(selectionBox.start.y, selectionBox.end.y)}
                    width={Math.abs(selectionBox.end.x - selectionBox.start.x)}
                    height={Math.abs(selectionBox.end.y - selectionBox.start.y)}
                    fill="rgba(121,198,154,.08)"
                    stroke="#79c69a"
                    strokeDasharray="5 4"
                    pointerEvents="none"
                  />
                )}
              </svg>
              </div>
              <div className="absolute bottom-5 right-5 w-36 h-24 rounded-lg p-2 hidden sm:block" style={{ background: "var(--t-card-alpha)", border: "1px solid var(--t-border-alpha)", boxShadow: "0 10px 28px var(--topology-node-shadow)" }}>
                <div className="font-mono text-[8px] uppercase tracking-widest mb-1" style={{ color: "#7f8984" }}>Minimap</div>
                <svg viewBox={`0 0 ${CANVAS_WIDTH} ${CANVAS_HEIGHT}`} className="w-full h-[76px]">
                  {workspace.links.map((link) => {
                    const from = deviceById.get(link.from)
                    const to = deviceById.get(link.to)
                    return from && to ? <line key={link.id} x1={from.x} y1={from.y} x2={to.x} y2={to.y} stroke="#77847d" strokeWidth="5" /> : null
                  })}
                  {workspace.devices.map((device) => <circle key={device.id} cx={device.x} cy={device.y} r="12" fill={device.tone} opacity=".9" />)}
                  <rect x={canvasViewport.x} y={canvasViewport.y} width={canvasViewport.width} height={canvasViewport.height} fill="none" stroke="var(--t-accent)" strokeWidth="4" opacity=".7" />
                </svg>
              </div>
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
        </div>

          <aside
            className="rounded-xl p-4 min-h-[420px]"
            style={{
              background: "var(--t-card)",
              border: "1px solid var(--t-border-alpha)",
            }}
          >
            {selected ? (
              <div className="space-y-4">
                <div className="flex items-start justify-between gap-3 border-b pb-3" style={{ borderColor: "var(--t-border-light)" }}>
                  <div className="flex items-center gap-2 min-w-0">
                    <div className="w-9 h-9 rounded-lg flex items-center justify-center" style={{ background: `${selected.tone}18`, border: `1px solid ${selected.tone}55` }}>
                      <svg width="22" height="22" viewBox="0 0 48 48"><DeviceGlyph type={selected.type} tone={selected.tone} /></svg>
                    </div>
                    <div className="min-w-0">
                      <div className="font-display font-semibold text-sm truncate" style={{ color: "var(--t-text)" }}>{selected.name}</div>
                      <div className="font-mono text-[10px] uppercase" style={{ color: selected.tone }}>{selected.type}</div>
                    </div>
                  </div>
                  <button type="button" onClick={() => setSelectedId(null)} className="font-mono text-xs" style={{ color: "var(--t-muted)" }}>×</button>
                </div>

                {editing?.id === selected.id && (
                  <div className="space-y-2 rounded-lg p-3" style={{ background: "var(--t-bg)", border: "1px solid var(--t-accent-border)" }}>
                    <div className="font-mono text-[9px] uppercase tracking-widest" style={{ color: "var(--t-accent)" }}>Edit device</div>
                    {([
                      ["name", "Device name"],
                      ["ipAddress", "Device IP"],
                      ["macAddress", "MAC address"],
                      ["location", "Location"],
                      ["type", "Device type"],
                    ] as const).map(([field, label]) => (
                      <label key={field} className="block">
                        <span className="font-mono text-[9px] uppercase" style={{ color: "var(--t-muted)" }}>{label}</span>
                        <input
                          value={editing[field] ?? ""}
                          onChange={(event) => setEditing({ ...editing, [field]: event.target.value })}
                          className="mt-1 w-full rounded-md px-2.5 py-2 font-mono text-[11px] outline-none"
                          style={{ color: "var(--t-text)", background: "var(--t-card)", border: "1px solid var(--t-border-alpha)" }}
                        />
                      </label>
                    ))}
                    <label className="block">
                      <span className="font-mono text-[9px] uppercase" style={{ color: "var(--t-muted)" }}>Ports (comma separated)</span>
                      <input
                        value={editing.ports?.join(", ") ?? ""}
                        onChange={(event) => setEditing({ ...editing, ports: event.target.value.split(",").map((port) => port.trim()).filter(Boolean) })}
                        className="mt-1 w-full rounded-md px-2.5 py-2 font-mono text-[11px] outline-none"
                        style={{ color: "var(--t-text)", background: "var(--t-card)", border: "1px solid var(--t-border-alpha)" }}
                      />
                    </label>
                    <div className="grid grid-cols-2 gap-2 pt-1">
                      <button type="button" onClick={() => setEditing(null)} className="rounded-md py-2 font-mono text-[10px] uppercase" style={{ color: "var(--t-muted)", border: "1px solid var(--t-border-alpha)" }}>Cancel</button>
                      <button type="button" onClick={saveDevice} className="rounded-md py-2 font-mono text-[10px] uppercase" style={{ color: "var(--t-bg)", background: "var(--t-accent)" }}>Save changes</button>
                    </div>
                  </div>
                )}

                <div className="flex items-center justify-between rounded-lg px-3 py-2" style={{ background: selected.status === "offline" ? "rgba(255,51,102,.08)" : "rgba(0,255,136,.07)", border: `1px solid ${selected.status === "offline" ? "rgba(255,51,102,.25)" : "rgba(0,255,136,.2)"}` }}>
                  <span className="font-mono text-[10px] uppercase" style={{ color: "var(--t-muted)" }}>Health status</span>
                  <span className="font-mono text-[10px] uppercase" style={{ color: selected.status === "offline" ? "#ff3366" : "#00ff88" }}>{selected.status || "manual"}</span>
                </div>

                <div className="space-y-2">
                  {[
                    ["Device IP", selected.ipAddress || selected.subtitle || "Not set"],
                    ["MAC address", selected.macAddress || "Not set"],
                    ["Location", selected.location || "Not set"],
                  ].map(([label, value]) => (
                    <div key={label}>
                      <div className="font-mono text-[9px] uppercase mb-1" style={{ color: "var(--t-muted)" }}>{label}</div>
                      <div className="rounded-md px-2.5 py-2 font-mono text-[11px] truncate" style={{ color: "var(--t-text)", background: "var(--t-bg)", border: "1px solid var(--t-border-alpha)" }}>{value}</div>
                    </div>
                  ))}
                </div>

                <div>
                  <div className="flex items-center justify-between mb-2">
                    <span className="font-mono text-[9px] uppercase" style={{ color: "var(--t-muted)" }}>Interfaces</span>
                    <span className="font-mono text-[10px]" style={{ color: "var(--t-accent)" }}>{selectedPorts.length}</span>
                  </div>
                  <div className="space-y-1.5 max-h-36 overflow-y-auto">
                    {selectedPorts.slice(0, 12).map((port) => (
                      <button key={port} type="button" onClick={() => selectPort(selected.id, port)} className="w-full flex items-center justify-between rounded-md px-2.5 py-2 text-left" style={{ background: "var(--t-bg)", border: "1px solid var(--t-border-alpha)" }}>
                        <span className="font-mono text-[10px] truncate" style={{ color: "var(--t-text)" }}>{portLabel(port)}</span>
                        <span className="w-1.5 h-1.5 rounded-full" style={{ background: selected.portStatuses?.[port]?.toLowerCase() === "up" ? "#00ff88" : selected.portStatuses?.[port]?.toLowerCase() === "down" ? "#ff3366" : "var(--t-muted)" }} />
                      </button>
                    ))}
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-2">
                  <button type="button" onClick={editSelectedDevice} className="rounded-md py-2 font-mono text-[10px] uppercase" style={{ color: "var(--t-accent)", border: "1px solid var(--t-accent-border)" }}>Edit device</button>
                  <button type="button" onClick={() => { setConnectMode(true); setConnectFrom(selected.id) }} className="rounded-md py-2 font-mono text-[10px] uppercase" style={{ color: "#00ff88", border: "1px solid rgba(0,255,136,.3)" }}>Connect</button>
                </div>
              </div>
            ) : (
              <div className="h-full min-h-[420px] flex flex-col items-center justify-center text-center">
                <div className="w-12 h-12 rounded-xl flex items-center justify-center mb-3" style={{ color: "var(--t-accent)", background: "var(--t-accent-alpha)", border: "1px solid var(--t-accent-border)" }}>
                  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M12 3v18M3 12h18" /><circle cx="12" cy="12" r="8" /></svg>
                </div>
                <div className="font-display text-sm" style={{ color: "var(--t-text)" }}>Select a device</div>
                <div className="font-mono text-[10px] mt-1 max-w-[190px]" style={{ color: "var(--t-muted)" }}>Choose a node on the canvas to inspect ports, health, and connection actions.</div>
              </div>
            )}
          </aside>
        </div>

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
            ) : null}
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
      {contextMenu && (
        <div className="fixed z-[90] min-w-[180px] rounded-lg p-1 shadow-2xl" style={{ left: Math.min(contextMenu.x, window.innerWidth - 210), top: Math.min(contextMenu.y, window.innerHeight - 180), background: "#171b1a", border: "1px solid rgba(231,225,213,.2)" }} role="menu" aria-label="Topology context menu" onClick={(event) => event.stopPropagation()}>
          {contextMenu.deviceId && (
            <>
              <button type="button" role="menuitem" className="block w-full rounded px-3 py-2 text-left font-mono text-[10px] uppercase hover:bg-white/5" style={{ color: "#e7e1d5" }} onClick={() => { setSelectedId(contextMenu.deviceId!); setSelectedIds([contextMenu.deviceId!]); setContextMenu(null) }}>Select device</button>
              <button type="button" role="menuitem" disabled={verificationView === "actual"} className="block w-full rounded px-3 py-2 text-left font-mono text-[10px] uppercase hover:bg-white/5 disabled:opacity-30" style={{ color: "#d8d2c6" }} onClick={() => { const device = workspace.devices.find((item) => item.id === contextMenu.deviceId); if (device) setEditing({ ...device, ipAddress: device.ipAddress ?? device.subtitle, macAddress: device.macAddress ?? "", location: device.location ?? "" }); setSelectedId(contextMenu.deviceId!); setContextMenu(null) }}>Edit details</button>
              <button type="button" role="menuitem" disabled={verificationView === "actual"} className="block w-full rounded px-3 py-2 text-left font-mono text-[10px] uppercase hover:bg-white/5 disabled:opacity-30" style={{ color: "#da6b6b" }} onClick={() => { deleteSelected(contextMenu.deviceId!); setContextMenu(null) }}>Remove device</button>
            </>
          )}
          {contextMenu.linkId && (
            <>
              <button type="button" role="menuitem" className="block w-full rounded px-3 py-2 text-left font-mono text-[10px] uppercase hover:bg-white/5" style={{ color: "#e7e1d5" }} onClick={() => { setSelectedLinkId(contextMenu.linkId!); setContextMenu(null) }}>Select connection</button>
              <button type="button" role="menuitem" disabled={verificationView === "actual"} className="block w-full rounded px-3 py-2 text-left font-mono text-[10px] uppercase hover:bg-white/5 disabled:opacity-30" style={{ color: "#da6b6b" }} onClick={() => { disconnectLink(contextMenu.linkId!); setContextMenu(null) }}>Disconnect</button>
            </>
          )}
        </div>
      )}
      {confirmRequest ? (
        <SafetyConfirmDialog
          request={confirmRequest}
          step={confirmStep}
          onCancel={cancelConfirmation}
          onConfirm={confirmPendingChange}
        />
      ) : navigationBlocker.state === "blocked" ? (
        <SafetyConfirmDialog
          request={{
            title: "Leave topology editor?",
            description: "This page has changes that are still being saved. Leaving now may discard them.",
            details: [["Saved state", "Manual topology has pending changes"], ["Action", "Stay to finish saving, or leave without saving"]],
            confirmLabel: "Leave Without Saving",
            tone: "amber",
            onConfirm: () => navigationBlocker.proceed(),
          }}
          step={1}
          onCancel={() => navigationBlocker.reset()}
          onConfirm={confirmPendingChange}
        />
      ) : null}
    </main>
  )
}
