import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
} from "react"
import { useNavigate } from "react-router"
import {
  createManualTopologySnapshot,
  getLatestInterfaces,
  getLatestManualTopologySnapshot,
  getOverview,
  getSNMPInterfaces,
  getSNMPTopology,
  listSNMPDevicesOptimized,
  reconcileManualTopology,
  resolveManualTopologyChange,
  updateDevice,
  updateManualTopologySnapshot,
  type DeviceRecord,
  type ManualTopologyChange,
  type SNMPDeviceListItem,
  type SNMPInterfaceStats,
} from "../lib/api"
import { toast } from "../lib/swal"
import { readViewports, centeredViewport, zoomViewport, type Viewport } from "./manualTopologyViewport"
import { portEndpoint, compactPortLabel } from "./manualTopologyPorts"
import { comparePhysicalConnection } from "./manualTopologyEvidence"
import { useI18n } from "../i18n/I18nContext"
import { buildLogicalTopologyGraph, collectTopologyDevice, makeNode } from "../lib/topologyGraphBuilder"

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
  description?: string
  topologyMetadata?: Record<string, unknown>
  portSources?: Record<string, "snmp" | "latest" | "manual_fallback">
  vendor?: string
  model?: string
  serialNumber?: string
  firmware?: string
  snmpVersion?: string
  monitoringEnabled?: boolean
  lastSeen?: string
}
type Link = {
  id: string
  from: string
  to: string
  label: string
  fromPort?: string
  toPort?: string
  fromIfIndex?: number | null
  toIfIndex?: number | null
  fromPortSource?: string
  toPortSource?: string
  routingPoints?: Array<{ x: number y: number }>
  status?: string
  origin?: "manual" | "discovered_physical"
  discoverySource?: string
  confidence?: "HIGH" | "MEDIUM" | "LOW"
  evidence?: string[]
}
type Workspace = { devices: Device[] links: Link[] }
type ViewMode = "manual" | "actual" | "compare"
type DeviceHealthStatus = "online" | "offline" | "degraded" | "stale" | "unknown"
type EditForm = {
  name: string
  type: string
  ip: string
  mac: string
  location: string
  description: string
  vendor: string
  model: string
  serial: string
  firmware: string
  snmpVersion: string
}

const CANVAS = { width: 1400, height: 820 }
const NODE_SOCKET = { x: 58, y: 34 }
const STORAGE_KEY = "nms.manual-topology.workspace.v2"
const VIEWPORT_STORAGE_KEY = "nms.manual-topology.viewport.v1"

function normalizeHealthStatus(value: unknown): DeviceHealthStatus {
  const status = String(value ?? "unknown").toLowerCase()
  return status === "online" || status === "offline" || status === "degraded" || status === "stale"
    ? status
    : "unknown"
}

function healthColor(status: DeviceHealthStatus) {
  if (status === "online") return "#61c98d"
  if (status === "offline") return "#d9646a"
  if (status === "degraded") return "#d4a95c"
  return "#9aa3a0"
}

function healthLabel(status: DeviceHealthStatus) {
  return status.charAt(0).toUpperCase() + status.slice(1)
}
const palette = [
  "#3b82f6",
  "#36c2b4",
  "#d4a95c",
  "#61c98d",
  "#9b8afb",
]
const editableDeviceTypes = [
  "Network Device",
  "Core Switch",
  "Switch",
  "Router",
  "Firewall",
  "Server",
  "Camera",
  "NVR",
  "Access Point",
  "WiFi",
  "AP",
  "Wireless Controller",
  "Storage",
  "Printer",
  "Phone",
  "Gateway",
  "Load Balancer",
  "Cloud",
  "Generic Device",
]

const symbolLibrary = [
  { category: "NETWORK", items: ["Router", "Core Switch", "Switch", "Gateway", "Modem", "Hub", "Bridge", "Load Balancer", "Internet", "Cloud"] },
  { category: "SECURITY", items: ["Firewall", "UTM", "IDS", "IPS", "VPN Gateway", "Security Appliance"] },
  { category: "SERVERS", items: ["Generic Server", "Linux Server", "Windows Server", "Web Server", "Database Server", "Mail Server", "Virtual Machine", "Hypervisor"] },
  { category: "WIRELESS", items: ["Access Point", "Wireless Controller", "WiFi Router", "Wireless Bridge", "Antenna"] },
  { category: "VIDEO / CCTV", items: ["IP Camera", "Dome Camera", "Bullet Camera", "PTZ Camera", "NVR", "DVR"] },
  { category: "ENDPOINTS", items: ["Desktop", "Laptop", "Printer", "IP Phone", "Mobile", "Tablet", "IoT Device", "Sensor"] },
  { category: "STORAGE", items: ["NAS", "SAN", "Storage Array", "Backup Appliance"] },
  { category: "POWER", items: ["UPS", "PDU"] },
  { category: "CLOUD", items: ["Cloud", "Internet", "SaaS", "Data Center", "Remote Site"] },
  { category: "GENERIC", items: ["Generic Device", "Unknown Device", "Custom Node", "Site", "Rack", "Building", "Group", "Zone"] },
] as const

type DeviceKind = "SWITCH" | "CORE_SWITCH" | "ROUTER" | "FIREWALL" | "CAMERA" | "NVR" | "ACCESS_POINT" | "SERVER" | "STORAGE" | "PRINTER" | "PHONE" | "CLOUD" | "GENERIC_DEVICE"

function classifyDevice(
  type?: string,
  name?: string,
  vendor?: string,
  model?: string,
): DeviceKind {
  const explicit = String(type || "")
    .toLowerCase()
    .replace(/[._-]+/g, " ")
    .trim()
  const hints = `${name || ""} ${vendor || ""} ${model || ""}`.toLowerCase()
  if (explicit.includes("core") && explicit.includes("switch"))
    return "CORE_SWITCH"
  if (
    ["switch", "managed switch", "l2 switch", "l3 switch"].some((value) =>
      explicit.includes(value),
    ) ||
    explicit === "sw"
  )
    return "SWITCH"
  if (
    explicit.includes("firewall") ||
    explicit.includes("utm") ||
    explicit.includes("security appliance")
  )
    return "FIREWALL"
  if (explicit.includes("router") || explicit.includes("gateway"))
    return "ROUTER"
  if (explicit.includes("camera") || explicit.includes("cctv")) return "CAMERA"
  if (
    explicit.includes("nvr") ||
    explicit.includes("dvr") ||
    explicit.includes("video recorder")
  )
    return "NVR"
  if (
    explicit.includes("wireless") ||
    explicit.includes("access point") ||
    explicit === "ap" ||
    explicit.includes("wifi ap")
  )
    return "ACCESS_POINT"
  if (
    explicit.includes("server") ||
    explicit.includes("linux") ||
    explicit.includes("windows server")
  )
    return "SERVER"
  if (explicit.includes("storage") || explicit.includes("nas")) return "STORAGE"
  if (explicit.includes("printer")) return "PRINTER"
  if (explicit.includes("phone") || explicit.includes("voip")) return "PHONE"
  if (
    explicit.includes("cloud") ||
    explicit.includes("internet") ||
    hints.includes("cloud")
  )
    return "CLOUD"
  if (hints.includes("firewall") || hints.includes("fortigate"))
    return "FIREWALL"
  if (hints.includes("camera") || hints.includes("cctv")) return "CAMERA"
  if (
    hints.includes("nvr") ||
    hints.includes("dvr") ||
    /(^|\s)nr(\s|[-_]|$)/i.test(hints)
  )
    return "NVR"
  if (
    hints.includes("access point") ||
    hints.includes("wireless") ||
    hints.includes("wifi") ||
    /(^|\s)ap(\s|[-_]|$)/i.test(hints)
  )
    return "ACCESS_POINT"
  if (hints.includes("storage") || hints.includes("nas")) return "STORAGE"
  if (hints.includes("printer")) return "PRINTER"
  if (hints.includes("phone") || hints.includes("voip")) return "PHONE"
  if (hints.includes("cloud") || hints.includes("internet")) return "CLOUD"
  if (hints.includes("switch"))
    return hints.includes("core") ? "CORE_SWITCH" : "SWITCH"
  if (hints.includes("router") || hints.includes("gateway")) return "ROUTER"
  if (hints.includes("server")) return "SERVER"
  return "GENERIC_DEVICE"
}

function deviceAccent(kind: DeviceKind, index = 0) {
  return {
    CORE_SWITCH: "#36c2b4",
    SWITCH: "#61c98d",
    ROUTER: "#e39a55",
    FIREWALL: "#d9646a",
    SERVER: "#9b8afb",
    NVR: "#d4a95c",
    CAMERA: "#e4c45b",
    ACCESS_POINT: "#d879c8",
    STORAGE: "#a98cf0",
    PRINTER: "#77b3c8",
    PHONE: "#7891a8",
    CLOUD: "#c5cfcc",
    GENERIC_DEVICE: palette[index % palette.length],
  }[kind]
}

function toneFor(
  type: string,
  index = 0,
  name?: string,
  vendor?: string,
  model?: string,
) {
  return deviceAccent(classifyDevice(type, name, vendor, model), index)
}

function glyph(type: string, name?: string, vendor?: string, model?: string) {
  const kind = classifyDevice(type, name, vendor, model)
  if (kind === "FIREWALL")
    return (
      <>
        <path d="M24 5 39 11v11c0 9-6 15-15 20C15 37 9 31 9 22V11z" />
        <path d="m16 24 5 5 11-12" />
      </>
    )
  if (kind === "CORE_SWITCH")
    return (
      <>
        <path d="M8 14h32v18H8z" />
        <path d="M13 20h22M13 26h22" />
        <circle cx="16" cy="20" r="1.5" fill="currentColor" stroke="none" />
        <circle cx="24" cy="20" r="1.5" fill="currentColor" stroke="none" />
        <circle cx="32" cy="20" r="1.5" fill="currentColor" stroke="none" />
        <circle cx="24" cy="26" r="2" />
        <path d="M24 8v6M17 8l7 6 7-6M17 34h14" />
      </>
    )
  if (kind === "SWITCH")
    return (
      <>
        <rect x="7" y="14" width="34" height="18" rx="3" />
        <path d="M12 20h3M19 20h3M26 20h3M33 20h3M12 26h3M19 26h3M26 26h3M33 26h3" />
        <path d="M15 10v4M24 10v4M33 10v4M15 32v5M33 32v5" />
      </>
    )
  if (kind === "ROUTER")
    return (
      <>
        <circle cx="24" cy="24" r="13" />
        <path d="M11 24h26M24 11c4 4 6 8 6 13s-2 9-6 13c-4-4-6-8-6-13s2-9 6-13Z" />
        <path d="m24 5 4 4-4 4M43 24l-4 4-4-4" />
      </>
    )
  if (kind === "CAMERA")
    return (
      <>
        <path d="M8 15h23l9 6v9H8z" />
        <circle cx="27" cy="25" r="5" />
        <path d="M8 18H4M15 15l3-5h8l3 5" />
      </>
    )
  if (kind === "NVR")
    return (
      <>
        <rect x="8" y="8" width="32" height="11" rx="2" />
        <rect x="8" y="23" width="32" height="11" rx="2" />
        <path d="M14 13h.1M14 28h.1M20 13h14M20 28h14" />
      </>
    )
  if (kind === "ACCESS_POINT")
    return (
      <>
        <path d="M5 18a27 27 0 0 1 38 0M10 24a20 20 0 0 1 28 0M16 30a12 12 0 0 1 16 0" />
        <path d="M24 30v9M18 39h12" />
        <circle cx="24" cy="24" r="2" fill="currentColor" stroke="none" />
      </>
    )
  if (kind === "SERVER" || kind === "STORAGE")
    return (
      <>
        <rect x="9" y="7" width="30" height="10" rx="2" />
        <rect x="9" y="22" width="30" height="10" rx="2" />
        <path d="M14 12h.1M14 27h.1M20 12h13M20 27h13M17 37h14M24 32v5" />
      </>
    )
  if (kind === "PRINTER")
    return (
      <>
        <path d="M14 17V8h20v9M10 17h28v14H10z" />
        <path d="M16 26h16M16 35h16" />
      </>
    )
  if (kind === "PHONE")
    return (
      <>
        <rect x="15" y="6" width="18" height="34" rx="3" />
        <path d="M20 11h8M22 35h4" />
      </>
    )
  if (kind === "CLOUD")
    return (
      <path d="M13 32h22a8 8 0 0 0 1-16 12 12 0 0 0-23 4 6 6 0 0 0 0 12Z" />
    )
  return (
    <>
      <path d="M24 6 40 15v18L24 42 8 33V15z" />
      <circle cx="24" cy="24" r="4" />
      <path d="M24 10v10M12 17l9 5M36 17l-9 5M12 31l9-5M36 31l-9-5" />
    </>
  )
}

function deviceIllustration(type: string, tone: string) {
  const kind = classifyDevice(type)
  const isSwitch = kind === "SWITCH" || kind === "CORE_SWITCH"
  const isServer = kind === "SERVER" || kind === "STORAGE" || kind === "NVR"
  const isCloud = kind === "CLOUD"
  if (isCloud)
    return (
      <>
        <path d="M22 51h66c10 0 17-6 17-15 0-8-6-14-14-15-3-10-12-16-22-16-12 0-21 7-24 18-9-1-16 5-16 14 0 8 6 14 15 14Z" fill="#26383b" stroke={tone} strokeWidth="2" />
        <path d="M34 38h41M43 29h23M52 20v25" stroke={tone} strokeWidth="2" opacity=".8" />
      </>
    )
  if (kind === "ACCESS_POINT")
    return (
      <>
        <ellipse cx="68" cy="43" rx="42" ry="16" fill="#202d31" stroke={tone} strokeWidth="2" />
        <path d="M28 43v8c0 8 18 14 40 14s40-6 40-14v-8" fill="#101719" stroke={tone} strokeWidth="2" />
        <path d="M48 36a28 28 0 0 1 40 0M54 31a20 20 0 0 1 28 0" fill="none" stroke={tone} strokeWidth="2" strokeLinecap="round" />
        <circle cx="68" cy="43" r="3" fill="#61c98d" />
      </>
    )
  if (kind === "ROUTER")
    return (
      <>
        <polygon points="20,34 65,22 111,34 65,48" fill="#2c3438" stroke={tone} strokeWidth="1.8" />
        <polygon points="20,34 65,48 65,65 20,51" fill="#172124" stroke={tone} strokeWidth="1.8" />
        <polygon points="65,48 111,34 111,51 65,65" fill="#0d1416" stroke={tone} strokeWidth="1.8" />
        <path d="M38 32V14M92 29V11" stroke={tone} strokeWidth="2" />
        <circle cx="38" cy="14" r="3" fill={tone} /><circle cx="92" cy="11" r="3" fill={tone} />
        <path d="M74 50h25M74 56h15" stroke="#9aa3a0" strokeWidth="2" />
        <circle cx="70" cy="50" r="2" fill="#61c98d" /><circle cx="70" cy="56" r="2" fill="#e3a45d" />
      </>
    )
  if (kind === "FIREWALL")
    return (
      <>
        <polygon points="18,28 73,15 115,28 60,42" fill="#3a252a" stroke={tone} strokeWidth="1.8" />
        <polygon points="18,28 60,42 60,63 18,49" fill="#21181b" stroke={tone} strokeWidth="1.8" />
        <polygon points="60,42 115,28 115,49 60,63" fill="#160f12" stroke={tone} strokeWidth="1.8" />
        <path d="M78 42v10M72 47h12M91 40l10-3" stroke={tone} strokeWidth="2" strokeLinecap="round" />
        <circle cx="68" cy="47" r="2" fill="#d9646a" /><circle cx="68" cy="54" r="2" fill="#61c98d" />
      </>
    )
  if (kind === "CAMERA")
    return (
      <>
        <path d="M25 39h47l18-9v22l-18-9H25Z" fill="#28383b" stroke={tone} strokeWidth="2" />
        <circle cx="58" cy="42" r="10" fill="#101719" stroke={tone} strokeWidth="2" />
        <circle cx="58" cy="42" r="4" fill={tone} />
        <path d="M39 29V18h24l7 11M42 18l5-7h12l5 7" fill="none" stroke={tone} strokeWidth="2" />
      </>
    )
  if (kind === "NVR")
    return (
      <>
        <polygon points="20,25 76,12 115,25 59,39" fill="#39352a" stroke={tone} strokeWidth="1.8" />
        <polygon points="20,25 59,39 59,66 20,52" fill="#211f19" stroke={tone} strokeWidth="1.8" />
        <polygon points="59,39 115,25 115,52 59,66" fill="#151411" stroke={tone} strokeWidth="1.8" />
        <path d="M68 43h37M68 51h37" stroke="#9a8d67" strokeWidth="1.5" />
        <circle cx="64" cy="43" r="2" fill="#61c98d" /><circle cx="64" cy="51" r="2" fill="#e3a45d" />
        <path d="M28 34h18M28 41h18" stroke="#d4a95c" strokeWidth="2" />
      </>
    )
  if (kind === "STORAGE")
    return (
      <>
        <polygon points="20,25 76,12 115,25 59,39" fill="#30294a" stroke={tone} strokeWidth="1.8" />
        <polygon points="20,25 59,39 59,66 20,52" fill="#1b1830" stroke={tone} strokeWidth="1.8" />
        <polygon points="59,39 115,25 115,52 59,66" fill="#100e1d" stroke={tone} strokeWidth="1.8" />
        <ellipse cx="78" cy="45" rx="12" ry="4" fill="#1b1830" stroke={tone} /><ellipse cx="98" cy="40" rx="8" ry="3" fill="#1b1830" stroke={tone} />
        <path d="M67 53h34" stroke="#a98cf0" strokeWidth="1.5" /><circle cx="64" cy="53" r="2" fill="#61c98d" />
      </>
    )
  if (kind === "PHONE" || kind === "PRINTER")
    return (
      <>
        <polygon points="30,28 75,17 106,27 61,39" fill="#2a3a3e" stroke={tone} strokeWidth="1.8" />
        <polygon points="30,28 61,39 61,63 30,52" fill="#192528" stroke={tone} strokeWidth="1.8" />
        <polygon points="61,39 106,27 106,51 61,63" fill="#101719" stroke={tone} strokeWidth="1.8" />
        <rect x="70" y="42" width="25" height="10" rx="1" fill="#080d0f" stroke={tone} strokeWidth="1" />
        <path d="M75 46h15M75 49h10" stroke="#c5cfcc" strokeWidth="1" />
      </>
    )
  return (
    <>
      <polygon points="17,22 82,9 119,25 52,39" fill="#263438" stroke={tone} strokeWidth="1.5" />
      <polygon points="17,22 52,39 52,66 17,49" fill="#182326" stroke={tone} strokeWidth="1.5" />
      <polygon points="52,39 119,25 119,53 52,66" fill="#101719" stroke={tone} strokeWidth="1.5" />
      <path d="M23 27 48 39v18L23 45Z" fill="#2d4144" opacity=".8" />
      {isSwitch ? (
        <>
          <path d="M58 43h53v13H58z" fill="#080d0f" stroke="#738584" strokeWidth="1" />
          {Array.from({ length: 8 }, (_, index) => (
            <circle key={index} cx={64 + index * 6} cy="48" r="1.5" fill={index % 3 === 0 ? "#61c98d" : "#c5cfcc"} />
          ))}
          {Array.from({ length: 8 }, (_, index) => (
            <circle key={`lower-${index}`} cx={64 + index * 6} cy="52" r="1.5" fill={index % 4 === 0 ? "#e3a45d" : "#52615d"} />
          ))}
          <rect x="24" y="38" width="17" height="6" rx="1" fill="#081012" stroke="#61c98d" strokeWidth="1" />
          <circle cx="28" cy="41" r="1.5" fill="#61c98d" /><circle cx="33" cy="41" r="1.5" fill="#61c98d" /><circle cx="38" cy="41" r="1.5" fill="#e3a45d" />
        </>
      ) : isServer ? (
        <>
          <rect x="59" y="36" width="51" height="21" rx="2" fill="#080d0f" stroke="#738584" strokeWidth="1" />
          <path d="M64 42h40M64 49h40" stroke="#52615d" strokeWidth="1" />
          <circle cx="67" cy="39" r="1.5" fill="#61c98d" /><circle cx="67" cy="46" r="1.5" fill="#e3a45d" /><circle cx="67" cy="53" r="1.5" fill="#d9646a" />
        </>
      ) : (
        <>
          <path d="M66 40h32M66 46h24" stroke="#738584" strokeWidth="2" />
          <circle cx="63" cy="40" r="2" fill={tone} /><circle cx="63" cy="46" r="2" fill="#61c98d" />
          <path d="M30 30l12 5M38 28l12 5" stroke="#c5cfcc" strokeWidth="1.5" opacity=".8" />
        </>
      )}
      <path d="M20 50h26M57 61h45" stroke="#0a1012" strokeWidth="2" opacity=".8" />
    </>
  )
}

function normalizeWorkspace(raw: unknown): Workspace {
  const value =
    raw && typeof raw === "object" ? raw as Record<string, unknown> : {}
  const devices = Array.isArray(value.devices) ? value.devices : []
  const links = Array.isArray(value.links) ? value.links : []
  return {
    devices: devices.flatMap((item, index) => {
      if (!item || typeof item !== "object") return []
      const d = item as Record<string, unknown>
      const id = String(d.id ?? `device-${index}`)
      const name = String(d.name ?? d.hostname ?? "Network device")
      const vendor =
        typeof d.vendor === "string"
          ? d.vendor
          : typeof d.vendor_name === "string"
            ? d.vendor_name
            : undefined
      const model = typeof d.model === "string" ? d.model : undefined
      const metadata =
        d.topology_metadata && typeof d.topology_metadata === "object"
          ? d.topology_metadata as Record<string, unknown>
          : {}
      const type = String(metadata.manual_type ?? d.type ?? d.device_type ?? "Network Device")
      return [
        {
          id,
          name,
          subtitle: String(d.subtitle ?? d.ipAddress ?? d.ip_address ?? ""),
          type,
          tone: String(d.tone ?? toneFor(type, index, name, vendor, model)),
          x: Number(d.x ?? 180 + (index % 4) * 260),
          y: Number(d.y ?? 170 + Math.floor(index / 4) * 220),
          backendId: Number(d.backendId ?? d.backend_id ?? d.backendDeviceId ?? d.backend_device_id ?? d.resourceId ?? d.resource_id ?? metadata.backendDeviceId ?? metadata.backend_device_id ?? metadata.resourceId) || undefined,
          ports: Array.isArray(d.ports) ? d.ports.map(String) : [],
          portSources:
            d.portSources && typeof d.portSources === "object"
              ? d.portSources as Record<string, "snmp" | "latest" | "manual_fallback">
              : {},
          portStatuses:
            d.portStatuses && typeof d.portStatuses === "object"
              ? d.portStatuses as Record<string, string>
              : {},
          status: String(d.status ?? "unknown"),
          ipAddress:
            typeof d.ipAddress === "string"
              ? d.ipAddress
              : typeof d.ip_address === "string"
                ? d.ip_address
                : typeof d.ip === "string"
                  ? d.ip
                : undefined,
          macAddress:
            typeof d.macAddress === "string"
              ? d.macAddress
              : typeof d.mac_address === "string"
                ? d.mac_address
                : typeof d.mac === "string"
                  ? d.mac
                : undefined,
          location:
            typeof d.location === "string"
              ? d.location
              : typeof metadata.location === "string"
                ? metadata.location
                : undefined,
          description:
            typeof d.description === "string"
              ? d.description
              : typeof metadata.description === "string"
                ? metadata.description
                : undefined,
          topologyMetadata: metadata,
          vendor,
          model,
          serialNumber:
            typeof d.serialNumber === "string"
              ? d.serialNumber
              : typeof d.serial_number === "string"
                ? d.serial_number
                : undefined,
          firmware:
            typeof d.firmware === "string"
              ? d.firmware
              : typeof d.firmware_version === "string"
                ? d.firmware_version
                : undefined,
          snmpVersion:
            typeof d.snmpVersion === "string" ? d.snmpVersion : undefined,
          monitoringEnabled:
            typeof d.monitoringEnabled === "boolean"
              ? d.monitoringEnabled
              : undefined,
          lastSeen: typeof d.lastSeen === "string" ? d.lastSeen : undefined,
        },
      ]
    }),
    links: links.flatMap((item, index) => {
      if (!item || typeof item !== "object") return []
      const l = item as Record<string, unknown>
      if (l.from == null || l.to == null) return []
      return [
        {
          id: String(l.id ?? `link-${index}`),
          from: String(l.from),
          to: String(l.to),
          label: String(l.label ?? ""),
          fromPort: typeof l.fromPort === "string" ? l.fromPort : undefined,
          toPort: typeof l.toPort === "string" ? l.toPort : undefined,
          fromIfIndex: typeof l.fromIfIndex === "number" ? l.fromIfIndex : null,
          toIfIndex: typeof l.toIfIndex === "number" ? l.toIfIndex : null,
          fromPortSource:
            typeof l.fromPortSource === "string" ? l.fromPortSource : undefined,
          toPortSource:
            typeof l.toPortSource === "string" ? l.toPortSource : undefined,
          routingPoints: Array.isArray(l.routingPoints)
            ? l.routingPoints.filter(
                (p): p is { x: number y: number } =>
                  !!p &&
                  typeof p === "object" &&
                  typeof (p as { x?: unknown }).x === "number" &&
                  typeof (p as { y?: unknown }).y === "number",
              )
            : undefined,
          status: typeof l.status === "string" ? l.status : undefined,
          origin: l.origin === "discovered_physical" ? "discovered_physical" : "manual",
          discoverySource: typeof l.discoverySource === "string" ? l.discoverySource : undefined,
          confidence: l.confidence === "HIGH" || l.confidence === "MEDIUM" || l.confidence === "LOW" ? l.confidence : undefined,
          evidence: Array.isArray(l.evidence) ? l.evidence.map(String) : undefined,
        },
      ]
    }),
  }
}

function readCache(): Workspace {
  try {
    return normalizeWorkspace(
      JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "{}"),
    )
  } catch {
    return { devices: [], links: [] }
  }
}

function autoWorkspaceFromTopology(raw: unknown): Workspace {
  const value =
    raw && typeof raw === "object" ? raw as Record<string, unknown> : {}
  const rawDevices = Array.isArray(value.devices) ? value.devices : []
  const rawLinks = Array.isArray(value.links) ? value.links : []
  const devices: Device[] = rawDevices.flatMap((item, index) => {
    if (!item || typeof item !== "object") return []
    const device = item as Record<string, unknown>
    const backendId = Number(device.id ?? device.device_id)
    if (!Number.isFinite(backendId)) return []
    const type = String(device.type ?? device.device_type ?? "Network Device")
    const name = String(device.hostname ?? device.name ?? `Device ${backendId}`)
    const vendor = String(device.vendor ?? "")
    const model = String(device.model ?? "")
    return [
      {
        id: `device-${backendId}`,
        backendId,
        name,
        subtitle: String(device.ip_address ?? device.ip ?? ""),
        type,
        tone: toneFor(type, index, name, vendor, model),
        x: 220 + (index % 4) * 280,
        y: 180 + Math.floor(index / 4) * 190,
        ipAddress: String(device.ip_address ?? device.ip ?? "") || undefined,
        macAddress: String(device.mac_address ?? device.mac ?? "") || undefined,
        status: String(device.status ?? "unknown"),
        ports: [],
      },
    ]
  })
  const deviceIds = new Set(devices.map((device) => device.id))
  const links: Link[] = rawLinks.flatMap((item, index) => {
    if (!item || typeof item !== "object") return []
    const link = item as Record<string, unknown>
    const fromId = Number(
      link.from ?? link.source_node ?? link.source_device_id ?? link.source,
    )
    const toId = Number(
      link.to ?? link.target_node ?? link.target_device_id ?? link.target,
    )
    if (!Number.isFinite(fromId) || !Number.isFinite(toId)) return []
    const from = `device-${fromId}`
    const to = `device-${toId}`
    if (!deviceIds.has(from) || !deviceIds.has(to) || from === to) return []
    const fromPort =
      String(link.fromPort ?? link.source_port ?? link.local_port ?? "") ||
      undefined
    const toPort =
      String(link.toPort ?? link.target_port ?? link.remote_port ?? "") ||
      undefined
    return [
      {
        id: `auto-link-${index}-${from}-${to}`,
        from,
        to,
        fromPort,
        toPort,
        label: `${fromPort ?? "source"} -> ${toPort ?? "target"}`,
        status: String(link.status ?? "VERIFIED").toUpperCase(),
      },
    ]
  })
  return { devices, links }
}

function pruneWorkspaceToLiveDevices(
  workspace: Workspace,
  liveDevices: SNMPDeviceListItem[],
): Workspace {
  const liveBackendIds = new Set(liveDevices.map((device) => device.id))
  const devices = workspace.devices.filter(
    (device) =>
      device.backendId == null || liveBackendIds.has(device.backendId),
  )
  const deviceIds = new Set(devices.map((device) => device.id))
  return {
    devices,
    links: workspace.links.filter(
      (link) => deviceIds.has(link.from) && deviceIds.has(link.to),
    ),
  }
}

function workspaceChanged(left: Workspace, right: Workspace) {
  return (
    left.devices.length !== right.devices.length ||
    left.links.length !== right.links.length
  )
}

function statusColor(status?: string) {
  const value = status?.toUpperCase()
  if (value === "VERIFIED") return "#61c98d"
  if (value === "PORT_MISMATCH") return "#ff4d5e"
  if (value === "UNEXPECTED" || value === "DISCONNECTED") return "#d9646a"
  if (value === "DEVICE_OFFLINE") return "#78827e"
  return "#9aa3a0"
}

function portsFor(device: Device) {
  return device.ports?.length ? device.ports : ["Manual Port 1"]
}

const valueOf = (item: Record<string, unknown>, ...keys: string[]) => {
  for (const key of keys) if (item[key] != null && String(item[key]).trim()) return item[key]
  return undefined
}
const normId = (value: unknown) => value == null ? "" : String(value).trim().toLowerCase()
const normIp = (value: unknown) => normId(value).replace(/^\[|\]$/g, "")
const normMac = (value: unknown) => normId(value).replace(/[.:\-\s]/g, "")
const normalizeBackendDeviceId = (value: unknown) => {
  const text = normId(value)
  return /^device-\d+$/.test(text) ? text.slice(7) : text
}
function extractTopologyEndpoint(value: unknown) {
  const object = value && typeof value === "object" ? value as Record<string, unknown> : {}
  const data = object.data && typeof object.data === "object" ? object.data as Record<string, unknown> : {}
  const merged = { ...data, ...object }
  const rawId = typeof value === "object" ? valueOf(merged, "topologyNodeId", "nodeId", "node_id", "id") : value
  return {
    topologyNodeId: rawId == null ? "" : String(rawId),
    backendDeviceId: normalizeBackendDeviceId(valueOf(merged, "backendDeviceId", "backend_device_id", "deviceId", "device_id", "resourceId", "resource_id", "device_id")),
    ip: normIp(valueOf(merged, "ip", "ipAddress", "ip_address", "managementIp", "management_ip")),
    mac: normMac(valueOf(merged, "mac", "macAddress", "mac_address", "chassisMac", "chassis_mac")),
    hostname: normId(valueOf(merged, "hostname", "name", "label", "sysName", "sys_name", "system_name")),
    originalNode: value,
  }
}
const normPort = (value: unknown) => normId(value).replace(/\\s+/g, "")

function physicalLinkKey(link: Pick<Link, "from" | "to" | "fromPort" | "toPort">) {
  const a = `${link.from}|${normPort(link.fromPort)}`
  const b = `${link.to}|${normPort(link.toPort)}`
  return a < b ? `${a}::${b}` : `${b}::${a}`
}

function discoverPhysicalLinks(raw: unknown, canvasDevices: Device[]) {
  const value = raw && typeof raw === "object" ? raw as Record<string, unknown> : {}
  const rawDevices = Array.isArray(value.devices) ? value.devices : []
  const rawLinks = Array.isArray(value.links) ? value.links : []
  const byBackend = new Map<string, Device>()
  const byCanvasId = new Map<string, Device>(canvasDevices.map((device) => [normId(device.id), device]))
  const byIp = new Map<string, Device>()
  const byMac = new Map<string, Device>()
  const byName = new Map<string, Device[]>()
  for (const device of canvasDevices) {
    if (device.backendId != null) byBackend.set(normalizeBackendDeviceId(device.backendId), device)
    if (device.ipAddress) byIp.set(normIp(device.ipAddress), device)
    if (device.macAddress) byMac.set(normMac(device.macAddress), device)
    const name = normId(device.name); if (name) byName.set(name, [...(byName.get(name) ?? []), device])
  }
  const resolve = (item: Record<string, unknown>) => {
    const backend = valueOf(item, "backendDeviceId", "backend_device_id", "resourceId", "id", "device_id", "source_device_id", "target_device_id")
    const directCanvas = backend != null ? byCanvasId.get(normId(backend)) || byCanvasId.get(`device-${normalizeBackendDeviceId(backend)}`) : undefined
    const ip = valueOf(item, "ip_address", "ip", "source_ip", "target_ip")
    const mac = valueOf(item, "mac_address", "mac", "chassis_id", "chassis_mac", "source_mac", "target_mac", "source_chassis_id", "target_chassis_id")
    const hostname = normId(valueOf(item, "hostname", "name", "source_hostname", "target_hostname"))
    return directCanvas || (backend != null && byBackend.get(normalizeBackendDeviceId(backend))) ||
      (ip != null && byIp.get(normIp(ip))) || (mac != null && byMac.get(normMac(mac))) ||
      ((byName.get(hostname) ?? []).length === 1 ? byName.get(hostname)![0] : undefined)
  }
  const deviceById = new Map(rawDevices.flatMap((d) => {
    if (!d || typeof d !== "object") return []
    const x = d as Record<string, unknown>; const id = valueOf(x, "id", "device_id")
    return id == null ? [] : [[normId(id), x] as const]
  }))
  const out: Link[] = []; const unresolved: Record<string, unknown>[] = []; const seen = new Set<string>(); let discarded = 0
  for (const candidate of rawLinks) {
    if (!candidate || typeof candidate !== "object") { discarded++; continue }
    const l = candidate as Record<string, unknown>
    const sourceEndpoint = extractTopologyEndpoint(valueOf(l, "source_device_id", "source", "from", "source_node", "source_id"))
    const targetEndpoint = extractTopologyEndpoint(valueOf(l, "target_device_id", "target", "to", "target_node", "target_id"))
    const sid = sourceEndpoint.topologyNodeId
    const tid = targetEndpoint.topologyNodeId
    const sourceRaw = deviceById.get(normId(sid)) ?? {}
    const targetRaw = deviceById.get(normId(tid)) ?? {}
    const from = resolve({ ...sourceRaw, backendDeviceId: sourceEndpoint.backendDeviceId, source_device_id: sourceEndpoint.backendDeviceId || sid, source_ip: sourceEndpoint.ip || valueOf(l, "source_ip", "source_management_ip", "local_ip"), source_hostname: sourceEndpoint.hostname || valueOf(l, "source_hostname", "source_device_name"), source_mac: sourceEndpoint.mac || valueOf(l, "source_mac", "source_chassis_id") })
    const to = resolve({ ...targetRaw, backendDeviceId: targetEndpoint.backendDeviceId, target_device_id: targetEndpoint.backendDeviceId || tid, target_ip: targetEndpoint.ip || valueOf(l, "target_ip", "target_management_ip", "remote_ip", "remote_management_ip"), target_hostname: targetEndpoint.hostname || valueOf(l, "target_hostname", "target_device_name", "remote_hostname", "remote_system_name"), target_mac: targetEndpoint.mac || valueOf(l, "target_mac", "target_chassis_id", "remote_mac", "remote_chassis_id") })
    const sourceMatch = from ? (from.backendId != null ? "id" : from.ipAddress ? "ip" : from.macAddress ? "mac" : "hostname") : "none"
    const targetMatch = to ? (to.backendId != null ? "id" : to.ipAddress ? "ip" : to.macAddress ? "mac" : "hostname") : "unmanaged"
    console.debug("DISCOVERY_LINK_TRACE", { raw: { source: sid, target: tid }, sourceResolution: { matchedBy: sourceMatch, deviceId: from?.backendId ?? null, canvasNode: from?.id ?? null }, targetResolution: { matchedBy: targetMatch, deviceId: to?.backendId ?? null, canvasNode: to?.id ?? null }, result: from && to ? "CREATED" : "DISCARDED", reason: from && to ? null : !to ? "UNMANAGED_OR_UNRESOLVED_DEVICE" : "source device not found" })
    if (!from || !to || from.id === to.id) { discarded++; if (!to) unresolved.push(l); console.debug("DISCOVERY_LINK_DISCARDED", { reason: !from ? "UNMANAGED_OR_UNRESOLVED_SOURCE" : !to ? "UNMANAGED_OR_UNRESOLVED_TARGET" : "SELF_LINK" }); continue }
    const fromPort = valueOf(l, "source_port", "local_port", "fromPort", "localPort")
    const toPort = valueOf(l, "target_port", "remote_port", "toPort", "remotePort")
    const discoverySource = String(valueOf(l, "discovery_source", "evidence_source", "link_type", "protocol") ?? "physical")
    const evidence = Array.isArray(l.evidence) ? l.evidence.map(String) : [discoverySource]
    const rawConfidence = String(valueOf(l, "confidence", "evidence_confidence") ?? (/lldp|cdp/i.test(discoverySource) ? "HIGH" : "MEDIUM")).toUpperCase()
    const confidence = rawConfidence === "HIGH" || rawConfidence === "LOW" ? rawConfidence : "MEDIUM"
    const normalized: Link = { id: `discovered-${physicalLinkKey({ from: from.id, to: to.id, fromPort: fromPort ? String(fromPort) : undefined, toPort: toPort ? String(toPort) : undefined })}`, from: from.id, to: to.id, fromPort: fromPort ? String(fromPort) : undefined, toPort: toPort ? String(toPort) : undefined, fromIfIndex: Number(valueOf(l, "source_ifIndex", "source_if_index", "local_ifIndex")) || null, toIfIndex: Number(valueOf(l, "target_ifIndex", "target_if_index", "remote_ifIndex")) || null, label: `${fromPort ? String(fromPort) : "N/A"} ↔ ${toPort ? String(toPort) : "N/A"}`, status: String(valueOf(l, "status") ?? "VERIFIED").toUpperCase(), origin: "discovered_physical", discoverySource, confidence, evidence }
    console.debug("PHYSICAL_LINK_CONFIRMED", { from: from.id, to: to.id, confidence, evidence })
    const key = physicalLinkKey(normalized); if (!seen.has(key)) { seen.add(key); out.push(normalized) } else console.debug("DISCOVERY_LINK_DISCARDED", { reason: "duplicate physical link" })
  }
  console.debug("DISCOVERY_RAW_TOPOLOGY", { devices: rawDevices.length, links: rawLinks.length })
  return { links: out, discarded, unresolved }
}

type NormalizedPort = {
  id: number
  name: string
  description: string
  ifType: string
  ifIndex: number | null
  if_index: number | null
  adminStatus: string
  admin_status: string
  operStatus: string
  status: string
  speed: string
  speed_display: string
  mac: string
  ip: string
  source: "snmp" | "latest" | "manual_fallback"
  isPhysicalDiscovered: boolean
}

function normalizePort(
  item: SNMPInterfaceStats,
  source: "snmp" | "latest",
): NormalizedPort {
  const raw = item as unknown as Record<string, unknown>
  const ifIndexValue = raw.if_index ?? raw.ifIndex
  const ifIndex = ifIndexValue == null ? null : Number(ifIndexValue)
  const adminStatus = String(raw.admin_status ?? raw.adminStatus ?? "UNKNOWN")
  const operStatus = String(
    raw.status ?? raw.oper_status ?? raw.operStatus ?? "UNKNOWN",
  )
  const speed = String(raw.speed_display ?? raw.speed ?? "N/A")
  return {
    id: Number(raw.id ?? raw.interface_id ?? ifIndexValue ?? 0),
    name: String(
      raw.name ??
        raw.interface_name ??
        `Interface ${ifIndexValue ?? "unknown"}`,
    ),
    description: String(raw.description ?? ""),
    ifType: String(raw.if_type ?? raw.ifType ?? ""),
    ifIndex,
    if_index: ifIndex,
    adminStatus,
    admin_status: adminStatus,
    operStatus,
    status: operStatus,
    speed,
    speed_display: speed,
    mac: String(raw.mac_address ?? raw.mac ?? ""),
    ip: String(raw.ip_address ?? raw.ip ?? ""),
    source,
    isPhysicalDiscovered: true,
  }
}

function fallbackPort(): NormalizedPort {
  return {
    id: 0,
    name: "Manual Port 1",
    description: "",
    ifType: "manual",
    ifIndex: null,
    if_index: null,
    adminStatus: "UNKNOWN",
    admin_status: "UNKNOWN",
    operStatus: "UNKNOWN",
    status: "UNKNOWN",
    speed: "N/A",
    speed_display: "N/A",
    mac: "",
    ip: "",
    source: "manual_fallback",
    isPhysicalDiscovered: false,
  }
}

function normalizePortName(value?: string) {
  return String(value || "")
    .toLowerCase()
    .replace(/\s+/g, "")
    .replace(
      /^(gigabitethernet|fastethernet|tengigabitethernet|ethernet|gi|ge|fa|te)/,
      "",
    )
}

function isLogicalPort(
  port?: NormalizedPort | { name?: string ifType?: string },
) {
  const value = `${port?.name || ""} ${port?.ifType || ""}`.toLowerCase()
  return /port[- ]?channel|bond|bridge|vlan|svi|tunnel|loopback|virtual|software/.test(
    value,
  )
}

type PortOccupancy = {
  occupied: boolean
  linkId?: string
  peerDeviceId?: string
  peerPortName?: string
}

function getPortOccupancy(
  workspace: Workspace,
  deviceId: string,
  port: { name?: string ifIndex?: number | null } | string,
): PortOccupancy {
  const portName = typeof port === "string" ? port : port.name
  const ifIndex = typeof port === "string" ? null : port.ifIndex
  for (const link of workspace.links) {
    const endpoints = [
      {
        deviceId: link.from,
        portName: link.fromPort,
        ifIndex: link.fromIfIndex,
      },
      { deviceId: link.to, portName: link.toPort, ifIndex: link.toIfIndex },
    ]
    const endpoint = endpoints.find((item) => {
      if (item.deviceId !== deviceId) return false
      if (ifIndex != null && item.ifIndex != null && item.ifIndex === ifIndex)
        return true
      return normalizePortName(item.portName) === normalizePortName(portName)
    })
    if (!endpoint) continue
    const peer = endpoints.find((item) => item !== endpoint)
    return {
      occupied: true,
      linkId: link.id,
      peerDeviceId: peer?.deviceId,
      peerPortName: peer?.portName,
    }
  }
  return { occupied: false }
}

function MiniMap({
  workspace,
  viewport,
  onSelect,
}: {
  workspace: Workspace
  viewport: { x: number y: number width: number height: number }
  onSelect?: (point: { x: number y: number }) => void
}) {
  return (
    <svg
      viewBox={`0 0 ${CANVAS.width} ${CANVAS.height}`}
      className="h-full w-full"
      onClick={(event) => {
        if (!onSelect) return
        const rect = event.currentTarget.getBoundingClientRect()
        onSelect({
          x: ((event.clientX - rect.left) / rect.width) * CANVAS.width,
          y: ((event.clientY - rect.top) / rect.height) * CANVAS.height,
        })
      }}
    >
      <rect className="topology-minimap-bg" width={CANVAS.width} height={CANVAS.height} fill="#0d1113" />
      {workspace.links.map((link) => {
        const a = workspace.devices.find((d) => d.id === link.from)
        const b = workspace.devices.find((d) => d.id === link.to)
        return a && b ? (
          <line
            key={link.id}
            x1={a.x}
            y1={a.y}
            x2={b.x}
            y2={b.y}
            stroke={statusColor(link.status)}
            strokeWidth="5"
          />
        ) : null
      })}
      {workspace.devices.map((d) => (
        <circle key={d.id} cx={d.x} cy={d.y} r="12" fill={d.tone} />
      ))}
      <rect
        x={viewport.x}
        y={viewport.y}
        width={viewport.width}
        height={viewport.height}
        fill="none"
        stroke="#3b82f6"
        strokeWidth="5"
      />
    </svg>
  )
}

export default function ManualTopology() {
  const navigate = useNavigate()
  const { t } = useI18n()
  const tr = { ...t.workflow, manualTitle: "Topology", manualSubtitle: "Network topology workspace" }
  const [workspace, setWorkspace] = useState<Workspace>(() => readCache())
  const [snapshotId, setSnapshotId] = useState<number | null>(null)
  const [realDevices, setRealDevices] = useState<SNMPDeviceListItem[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [detailsOpen, setDetailsOpen] = useState(false)
  const [removeConfirmDevice, setRemoveConfirmDevice] = useState<Device | null>(null)
  const [selectedLinkId, setSelectedLinkId] = useState<string | null>(null)
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [connectMode, setConnectMode] = useState(false)
  const [source, setSource] = useState<{
    deviceId: string
    port: string
  } | null>(null)
  const [targetDeviceId, setTargetDeviceId] = useState<string | null>(null)
  const [targetPort, setTargetPort] = useState<string | null>(null)
  const [connectionError, setConnectionError] = useState<string | null>(null)
  const [verificationAlert, setVerificationAlert] = useState<{
    title: string
    message: string
    expected: string
    actual: string
  } | null>(null)
  const [pointer, setPointer] = useState<{ x: number y: number } | null>(null)
  const [interfaces, setInterfaces] =
    useState<Record<string, NormalizedPort[]>>({})
  const [allInterfaces, setAllInterfaces] =
    useState<Record<string, NormalizedPort[]>>({})
  const [portView, setPortView] = useState<"physical" | "all">("physical")
  const [portSearch, setPortSearch] = useState("")
  const [portStatus, setPortStatus] = useState<"all" | "up" | "down">("all")
  const [view, setView] = useState<ViewMode>("manual")
  const [search, setSearch] = useState("")
  const [symbolSearch, setSymbolSearch] = useState("")
  const [collapsedSymbols, setCollapsedSymbols] = useState<Set<string>>(new Set())
  const [manualAddOpen, setManualAddOpen] = useState(false)
  const [manualAddType, setManualAddType] = useState("Network Device")
  const [manualAddPosition, setManualAddPosition] = useState<{ x: number; y: number } | null>(null)
  const [manualAddForm, setManualAddForm] = useState({ name: "", ip: "", mac: "", location: "" })
  const [typeFilter, setTypeFilter] = useState("all")
  const [healthFilter, setHealthFilter] = useState("all")
  const [filtersOpen, setFiltersOpen] = useState(false)
  const [paletteOpen, setPaletteOpen] = useState(false)
  const [canvasFullscreen, setCanvasFullscreen] = useState(false)
  const [pageFullscreen, setPageFullscreen] = useState(false)
  const [snap, setSnap] = useState(true)
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [devicesPanelOpen, setDevicesPanelOpen] = useState(true)
  const [viewports, setViewports] = useState<Record<string, Viewport>>(() => {
    try { return readViewports(localStorage.getItem(VIEWPORT_STORAGE_KEY)) }
    catch { return {} }
  })
  const currentViewport = viewports[view] ?? centeredViewport(workspace.devices)
  const { zoom, pan } = currentViewport
  const setZoom = (value: number | ((previous: number) => number)) => {
    setViewports(previous => {
      const current = previous[view] ?? currentViewport
      return { ...previous, [view]: { ...current, zoom: typeof value === "function" ? value(current.zoom) : value } }
    })
  }
  const setPan = (value: Viewport["pan"] | ((previous: Viewport["pan"]) => Viewport["pan"])) => {
    setViewports(previous => {
      const current = previous[view] ?? currentViewport
      return { ...previous, [view]: { ...current, pan: typeof value === "function" ? value(current.pan) : value } }
    })
  }
  const [drag, setDrag] = useState<{ id: string ox: number oy: number } | null>(
    null,
  )
  const [canvasDrag, setCanvasDrag] = useState<{
    x: number
    y: number
    px: number
    py: number
  } | null>(null)
  const [routingDrag, setRoutingDrag] = useState<{
    linkId: string
    index: number
  } | null>(null)
  const [changes, setChanges] = useState<ManualTopologyChange[]>([])
  const [topologyPollMinutes, setTopologyPollMinutes] = useState(2)
  const [discoveryBusy, setDiscoveryBusy] = useState(false)
  const [selectedChange, setSelectedChange] =
    useState<ManualTopologyChange | null>(null)
  const [differenceLoading, setDifferenceLoading] = useState(false)
  const [applyingActual, setApplyingActual] = useState(false)
  const [confirmingConnectivity, setConfirmingConnectivity] = useState(false)
  const [resolutionNotice, setResolutionNotice] = useState<string | null>(null)
  const [actualWorkspace, setActualWorkspace] = useState<Workspace>({
    devices: [],
    links: [],
  })
  const [lastSaved, setLastSaved] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [editingDeviceId, setEditingDeviceId] = useState<string | null>(null)
  const [editForm, setEditForm] = useState<EditForm | null>(null)
  const [editErrors, setEditErrors] = useState<Record<string, string>>({})
  const [editSaving, setEditSaving] = useState(false)
  const [history, setHistory] = useState<Workspace[]>([])
  const [future, setFuture] = useState<Workspace[]>([])
  const [devicePanelTab, setDevicePanelTab] =
    useState<"canvas" | "available" | "manual">("canvas")
  const [inspectorTab, setInspectorTab] =
    useState<"overview" | "ports" | "monitoring">("overview")
  const [linkStatusFilter, setLinkStatusFilter] = useState("all")
  const [locationFilter, setLocationFilter] = useState("all")
  const [kindFilter, setKindFilter] = useState<DeviceKind | "ALL">("ALL")
  const [showPortLabels, setShowPortLabels] = useState(false)
  const [hoveredLinkId, setHoveredLinkId] = useState<string | null>(null)
  const [hoveredDeviceId, setHoveredDeviceId] = useState<string | null>(null)
  const [deviceHealth, setDeviceHealth] = useState<Record<number, DeviceHealthStatus>>({})
  const mainRef = useRef<HTMLElement | null>(null)
  const svgRef = useRef<SVGSVGElement | null>(null)
  const dragMoved = useRef(false)
  const dragDeviceId = useRef<string | null>(null)
  const dragFrame = useRef<number | null>(null)
  const dragStartWorkspace = useRef<Workspace | null>(null)
  const dragLatestWorkspace = useRef<Workspace | null>(null)
  const routingLatestWorkspace = useRef<Workspace | null>(null)
  const saveTimer = useRef<number | null>(null)

  const healthStatusFor = (device: Device): DeviceHealthStatus =>
    device.backendId != null
      ? deviceHealth[device.backendId] ?? "unknown"
      : "unknown"
  const healthColorFor = (device: Device) => healthColor(healthStatusFor(device))
  const renderedToneFor = (device: Device) =>
    healthStatusFor(device) === "offline" ? "#d9646a" : device.tone
  const panStart = useRef<{ x: number y: number } | null>(null)

  const clampZoom = (value: number) => Math.min(3, Math.max(0.25, value))
  const zoomPresets = [0.25, 0.5, 0.75, 1, 1.25, 1.5, 1.75, 2, 2.5, 3]

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const connectDevice = params.get("connectDevice")
    const connectPort = params.get("connectPort")
    if (!connectDevice || !connectPort) return
    setSelectedId(connectDevice)
    setConnectMode(true)
    setSource({ deviceId: connectDevice, port: connectPort })
    window.history.replaceState({}, "", "/manual-topology")
  }, [])

  useEffect(() => {
    try {
      localStorage.setItem(VIEWPORT_STORAGE_KEY, JSON.stringify(viewports))
    } catch {
      // View state is optional and must never affect topology persistence.
    }
  }, [viewports])
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null
      if (target?.matches("input, textarea, select, [contenteditable=true]"))
        return
      if (event.shiftKey && event.key.toLowerCase() === "f") {
        event.preventDefault()
        if (selected) focusDevice(selected)
      } else if (event.key === "+" || event.key === "=") {
        event.preventDefault()
        changeCanvasZoom(zoom + 0.1)
      } else if (event.key === "-") {
        event.preventDefault()
        changeCanvasZoom(zoom - 0.1)
      } else if (event.key === "0") {
        event.preventDefault()
        setZoom(1)
        setPan({ x: 0, y: 0 })
      } else if (event.key.toLowerCase() === "f") {
        event.preventDefault()
        fitToView()
      }
    }
    window.addEventListener("keydown", onKeyDown)
    return () => window.removeEventListener("keydown", onKeyDown)
  })

  const selected = workspace.devices.find((d) => d.id === selectedId) ?? null
  const hoverDeviceStats = (device: Device) => {
    const knownPorts = allInterfaces[device.id] ?? interfaces[device.id]
    const totalPorts = knownPorts?.length ?? device.ports?.length ?? 0
    const upPorts = knownPorts
      ? knownPorts.filter((port) => port.operStatus.toUpperCase() === "UP")
          .length
      : device.portStatuses
        ? Object.values(device.portStatuses).filter(
            (status) => status.toUpperCase() === "UP",
          ).length
        : null
    const connectedPorts = workspace.links.filter(
      (link) => link.from === device.id || link.to === device.id,
    ).length
    const connections = workspace.links
      .filter((link) => link.from === device.id || link.to === device.id)
      .map((link) => {
        const isFrom = link.from === device.id
        const peer = workspace.devices.find((item) => item.id === (isFrom ? link.to : link.from))
        return {
          localPort: isFrom ? link.fromPort : link.toPort,
          peerPort: isFrom ? link.toPort : link.fromPort,
          peerName: peer?.name,
          status: link.status,
          source: link.discoverySource || link.origin,
          confidence: link.confidence,
        }
      })
    const evidenceState = connections.length
      ? connections.some((connection) => connection.source && /lldp|cdp/i.test(connection.source))
        ? "LLDP/CDP verified"
        : connections.some((connection) => connection.source)
          ? "Inferred / manual"
          : "Manual link"
      : "N/A — no link evidence"
    return { totalPorts, upPorts, connectedPorts, connections, evidenceState }
  }
  const deviceTypes = useMemo(
    () => [...new Set(workspace.devices.map((d) => d.type))].sort(),
    [workspace.devices],
  )
  const visibleDevices = useMemo(
    () =>
      workspace.devices.filter((d) => {
        const q = search.toLowerCase()
        const matches =
          !q ||
          [
            d.name,
            d.subtitle,
            d.ipAddress,
            d.macAddress,
            d.type,
            d.vendor,
            d.model,
            d.location,
          ].some((v) => v?.toLowerCase().includes(q))
        return (
          matches &&
          (kindFilter === "ALL" ||
            classifyDevice(d.type, d.name, d.vendor, d.model) === kindFilter) &&
          (typeFilter === "all" || d.type === typeFilter) &&
          (locationFilter === "all" || d.location === locationFilter) &&
          (healthFilter === "all" ||
            (healthFilter === "offline"
              ? healthStatusFor(d) === "offline"
              : healthStatusFor(d) !== "offline"))
        )
      }),
    [
      workspace.devices,
      search,
      kindFilter,
      typeFilter,
      locationFilter,
      healthFilter,
    ],
  )
  const visibleIds = new Set(visibleDevices.map((d) => d.id))
  const visibleLinks = workspace.links.filter(
    (l) =>
      visibleIds.has(l.from) &&
      visibleIds.has(l.to) &&
      (linkStatusFilter === "all" ||
        l.status?.toLowerCase() === linkStatusFilter),
  )
  const viewport = {
    x: -pan.x / zoom,
    y: -pan.y / zoom,
    width: CANVAS.width / zoom,
    height: CANVAS.height / zoom,
  }
  const tooltipPlacement = (device: Device) => {
    const tooltipWidth = 300
    const tooltipHeight = 172
    const groupX = device.x - 70
    const groupY = device.y - 46
    const rightX = 132
    const leftX = -310
    const topY = -88
    const bottomY = 86
    const fitsRight = groupX + rightX + tooltipWidth <= viewport.x + viewport.width
    const fitsLeft = groupX + leftX >= viewport.x
    const fitsTop = groupY + topY >= viewport.y
    const fitsBottom =
      groupY + bottomY + tooltipHeight <= viewport.y + viewport.height
    return {
      x: fitsRight || !fitsLeft ? rightX : leftX,
      y: fitsTop || !fitsBottom ? topY : bottomY,
    }
  }

  const commit = (next: Workspace) => {
    setHistory((items) => [...items.slice(-39), workspace])
    setFuture([])
    setWorkspace(next)
  }
  const save = async (next: Workspace) => {
    setSaving(true)
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
      const result = snapshotId
        ? await updateManualTopologySnapshot(snapshotId, next)
        : await createManualTopologySnapshot(next)
      setSnapshotId(result.id)
      setChanges(result.changes ?? [])
      setLastSaved(new Date().toLocaleTimeString('en-IN', { timeZone: 'Asia/Kolkata', hour12: true }))
      return result
    } catch {
      toast.error("Manual topology could not be saved.")
      return null
    } finally {
      setSaving(false)
    }
  }
  const scheduleSave = (next: Workspace) => {
    if (saveTimer.current) window.clearTimeout(saveTimer.current)
    saveTimer.current = window.setTimeout(() => void save(next), 900)
  }
  const updateWorkspace = (next: Workspace) => {
    commit(next)
    scheduleSave(next)
  }

  useEffect(() => {
    let active = true
    const syncDeviceHealth = () => {
      void getOverview()
        .then((result) => {
          if (!active) return
          const next: Record<number, DeviceHealthStatus> = {}
          for (const item of result.devices ?? []) {
            if (item?.id != null) next[Number(item.id)] = normalizeHealthStatus(item.health?.status)
          }
          setDeviceHealth(next)
        })
        .catch(() => undefined)
    }
    syncDeviceHealth()
    const healthTimer = window.setInterval(syncDeviceHealth, 10000)
    return () => {
      active = false
      window.clearInterval(healthTimer)
    }
  }, [])

  useEffect(() => {
    let active = true
    const syncAutomaticTopology = () =>
      void getSNMPTopology()
        .then((result) => {
          if (active) setActualWorkspace(autoWorkspaceFromTopology(result))
        })
        .catch(() => undefined)
    void Promise.all([
      getLatestManualTopologySnapshot(),
      listSNMPDevicesOptimized({ page: 1, page_size: 200 }),
    ])
      .then(async ([result, devicesResult]) => {
        if (!active) return
        setRealDevices(devicesResult.items ?? [])
        const loaded = result ? normalizeWorkspace(result.payload) : readCache()
        const next = pruneWorkspaceToLiveDevices(loaded, devicesResult.items ?? [])
        setWorkspace(next)
        if (result) {
          setSnapshotId(result.id)
          setChanges(result.changes ?? [])
        }
        localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
        if (result && workspaceChanged(loaded, next)) {
          try {
            const saved = await updateManualTopologySnapshot(result.id, next)
            if (active) {
              setChanges(saved.changes ?? [])
              setLastSaved(new Date().toLocaleTimeString('en-IN', { timeZone: 'Asia/Kolkata', hour12: true }))
            }
          } catch {
            if (active) toast.error("Deleted devices could not be removed from the saved topology.")
          }
        }
      })
      .catch(() => undefined)
    void syncAutomaticTopology()
    const topologyTimer = window.setInterval(syncAutomaticTopology, 30000)
    return () => {
      active = false
      window.clearInterval(topologyTimer)
      if (saveTimer.current) window.clearTimeout(saveTimer.current)
    }
  }, [])
  useEffect(() => {
    if (!selected?.backendId || interfaces[selected.id]) return
    const physical = (items: SNMPInterfaceStats[]) =>
      items.filter(
        (item) =>
          !/^(vlan|lo|loopback|tunnel|mgmt|management|svi|port-channel|bridge|bond|virtual|cpu|software)/i.test(
            `${item.name} ${item.description ?? ""}`,
          ),
      )
    void Promise.allSettled([
      getSNMPInterfaces(selected.backendId),
      getLatestInterfaces(selected.backendId),
    ])
      .then((results) => {
        const currentAll =
          results[0].status === "fulfilled"
            ? results[0].value.map((item) => normalizePort(item, "snmp"))
            : []
        const latestAll =
          results[1].status === "fulfilled"
            ? results[1].value.map((item) => normalizePort(item, "latest"))
            : []
        const all = currentAll.length ? currentAll : latestAll
        const usable = physical(
          currentAll.length
            ? results[0].value
            : results[1].status === "fulfilled"
              ? results[1].value
              : [],
        ).map((item) =>
          normalizePort(item, currentAll.length ? "snmp" : "latest"),
        )
        const fallback = usable.length ? usable : [fallbackPort()]
        setAllInterfaces((items) => ({ ...items, [selected.id]: all }))
        setInterfaces((items) => ({ ...items, [selected.id]: fallback }))
        updateWorkspace({
          ...workspace,
          devices: workspace.devices.map((d) =>
            d.id === selected.id
              ? {
                  ...d,
                  ports: fallback.map((i) => i.name),
                  portSources: Object.fromEntries(
                    fallback.map((i) => [i.name, i.source]),
                  ),
                  portStatuses: Object.fromEntries(
                    fallback.map((i) => [i.name, i.operStatus]),
                  ),
                }
              : d,
          ),
        })
      })
      .catch(() => {
        const fallback = fallbackPort()
        setAllInterfaces((items) => ({ ...items, [selected.id]: [] }))
        setInterfaces((items) => ({ ...items, [selected.id]: [fallback] }))
      })
  }, [selected?.id, selected?.backendId])
  useEffect(() => {
    if (!snapshotId) return
    const timer = window.setInterval(() => {
      void reconcileManualTopology(snapshotId)
        .then((result) => {
          setChanges(result.changes ?? [])
          setActualWorkspace(normalizeWorkspace({
            devices: workspace.devices,
            links: result.live?.links ?? [],
          }))
        })
        .catch(() => undefined)
    }, topologyPollMinutes * 60_000)
    return () => window.clearInterval(timer)
  }, [snapshotId, topologyPollMinutes])

  const point = (event: ReactPointerEvent<SVGSVGElement>) => {
    const rect = svgRef.current?.getBoundingClientRect()
    if (!rect) return null
    // SVG uses xMidYMid meet, so account for the letterbox before applying
    // the editor's pan/zoom transform. This keeps the cursor on the canvas.
    const scale = Math.min(
      rect.width / CANVAS.width,
      rect.height / CANVAS.height,
    )
    const offsetX = (rect.width - CANVAS.width * scale) / 2
    const offsetY = (rect.height - CANVAS.height * scale) / 2
    const canvasX = (event.clientX - rect.left - offsetX) / scale
    const canvasY = (event.clientY - rect.top - offsetY) / scale
    return {
      // The SVG group is `translate(pan) scale(zoom)`, so invert those
      // operations in reverse order. Center-based math drifts after zooming.
      x: (canvasX - pan.x) / zoom,
      y: (canvasY - pan.y) / zoom,
    }
  }
  const moveDevice = (event: ReactPointerEvent<SVGGElement>, id: string) => {
    if (!drag) return
    dragMoved.current = true
    const p = point(event as unknown as ReactPointerEvent<SVGSVGElement>)
    if (!p) return
    const next = {
      ...workspace,
      devices: workspace.devices.map((d) =>
        d.id === id
          ? {
              ...d,
              // Keep pointer movement continuous; snap is applied once on release.
              x: p.x + drag.ox,
              y: p.y + drag.oy,
            }
          : d,
      ),
    }
    dragLatestWorkspace.current = next
    if (dragFrame.current) window.cancelAnimationFrame(dragFrame.current)
    dragFrame.current = window.requestAnimationFrame(() => {
      setWorkspace(next)
      dragFrame.current = null
    })
  }
  const addDevice = (type = "Network Device", position?: { x: number; y: number }) => {
    setManualAddType(type)
    setManualAddPosition(position ?? null)
    setManualAddForm({ name: "", ip: "", mac: "", location: "" })
    setManualAddOpen(true)
  }
  const createManualDevice = () => {
    const name = manualAddForm.name.trim()
    const ip = manualAddForm.ip.trim()
    const mac = manualAddForm.mac.trim()
    const location = manualAddForm.location.trim()
    if (!name) {
      toast.warning("Enter a device name.")
      return
    }
    if (ip && !/^((25[0-5]|2[0-4]\d|1?\d?\d)(\.|$)){4}$/.test(ip)) {
      toast.error("Enter a valid IP address or leave it empty.")
      return
    }
    if (mac && !/^([0-9a-f]{2}[:-]){5}[0-9a-f]{2}$/i.test(mac)) {
      toast.error("Enter a valid MAC address or leave it empty.")
      return
    }
    const next: Device = {
      id: `manual-${Date.now()}`,
      name: name.trim(),
      subtitle: ip,
      ipAddress: ip || undefined,
      macAddress: mac || undefined,
      location: location || undefined,
      type,
      tone: toneFor(type, workspace.devices.length),
      x: manualAddPosition?.x ?? 220 + (workspace.devices.length % 4) * 260,
      y: manualAddPosition?.y ?? 180 + Math.floor(workspace.devices.length / 4) * 190,
      status: "manual",
      ports: ["Manual Port 1"],
      portSources: { "Manual Port 1": "manual_fallback" },
    }
    updateWorkspace({ ...workspace, devices: [...workspace.devices, next] })
    setPaletteOpen(false)
    setManualAddOpen(false)
  }
  const filteredSymbolLibrary = symbolLibrary
    .map((group) => ({
      ...group,
      items: group.items.filter((item) =>
        item.toLowerCase().includes(symbolSearch.trim().toLowerCase()),
      ),
    }))
    .filter((group) => group.items.length > 0)
  const importDevice = (item: SNMPDeviceListItem) => {
    if (workspace.devices.some((d) => d.backendId === item.id)) return
    const next: Device = {
      id: `device-${item.id}`,
      backendId: item.id,
      name: item.hostname || item.name,
      subtitle: item.ip_address,
      ipAddress: item.ip_address,
      macAddress: item.mac_address ?? undefined,
      type: item.device_type || "Network Device",
      tone: toneFor(item.device_type || "", workspace.devices.length),
      status: item.status,
      model: item.model ?? undefined,
      serialNumber: item.serial_number ?? undefined,
      firmware: item.firmware ?? undefined,
      snmpVersion: item.snmp_version ?? undefined,
      monitoringEnabled: item.monitoring_enabled,
      lastSeen: item.last_seen ?? undefined,
      x: 220 + (workspace.devices.length % 4) * 260,
      y: 180 + Math.floor(workspace.devices.length / 4) * 190,
      ports: [],
    }
    updateWorkspace({ ...workspace, devices: [...workspace.devices, next] })
    setPaletteOpen(false)
  }
  const resetConnection = () => {
    setConnectMode(false)
    setSource(null)
    setTargetDeviceId(null)
    setTargetPort(null)
    setConnectionError(null)
    setPointer(null)
  }
  const selectPort = (deviceId: string, port: string) => {
    if (view === "actual") return
    if (!source) {
      setSource({ deviceId, port })
      setConnectionError(null)
      return
    }
    if (!targetDeviceId) {
      if (source.deviceId === deviceId) {
        toast.error("Choose a different destination device.")
        return
      }
      setTargetDeviceId(deviceId)
      setTargetPort(port)
      setConnectionError(null)
      return
    }
    if (source.deviceId === deviceId) {
      toast.error("Choose a different destination device.")
      return
    }
    if (targetPort) return
    setTargetPort(port)
    setConnectionError(null)
  }
  const createConnection = () => {
    if (!source || !targetDeviceId || !targetPort) {
      setConnectionError(
        "Select a source device, source port, target device, and target port.",
      )
      return
    }
    const sourceInterface = interfaces[source.deviceId]?.find(
      (item) => item.name === source.port,
    )
    const targetInterface = interfaces[targetDeviceId]?.find(
      (item) => item.name === targetPort,
    )
    const sourcePortRecord = sourceInterface ?? { name: source.port }
    const targetPortRecord = targetInterface ?? { name: targetPort }
    if (isLogicalPort(sourcePortRecord) || isLogicalPort(targetPortRecord)) {
      setConnectionError(
        "Logical interfaces cannot be used for a physical topology link.",
      )
      return
    }
    const sourceOccupancy = getPortOccupancy(
      workspace,
      source.deviceId,
      sourcePortRecord,
    )
    const targetOccupancy = getPortOccupancy(
      workspace,
      targetDeviceId,
      targetPortRecord,
    )
    if (sourceOccupancy.occupied || targetOccupancy.occupied) {
      const occupied = sourceOccupancy.occupied
        ? `${sourcePortRecord.name} is connected to ${sourceOccupancy.peerPortName || "another endpoint"}`
        : `${targetPortRecord.name} is connected to ${targetOccupancy.peerPortName || "another endpoint"}`
      setConnectionError(`Port already in use: ${occupied}.`)
      return
    }
    const duplicate = workspace.links.some(
      (l) =>
        l.from === source.deviceId &&
        l.to === targetDeviceId &&
        l.fromPort === source.port &&
        l.toPort === targetPort,
    )
    if (duplicate) {
      setConnectionError("That port-to-port link already exists.")
      return
    }
    const createdLink = {
      id: `link-${Date.now()}`,
      from: source.deviceId,
      to: targetDeviceId,
      fromPort: source.port,
      toPort: targetPort,
      fromIfIndex: sourceInterface?.ifIndex ?? null,
      toIfIndex: targetInterface?.ifIndex ?? null,
      fromPortSource: sourceInterface?.source ?? "manual_fallback",
      toPortSource: targetInterface?.source ?? "manual_fallback",
      label: `${source.port} - ${targetPort}`,
      status: "VERIFYING",
    }
    const next = { ...workspace, links: [...workspace.links, createdLink] }
    setWorkspace(next)
    setSelectedLinkId(createdLink.id)
    resetConnection()
    toast.success("Connection saved. Verifying physical connectivity...")
    void save(next)
      .then((saved) => {
        const id = saved?.id ?? snapshotId
        if (!id) return null
        return reconcileManualTopology(id).then((result) => {
          const response = result as typeof result & {
            live?: {
              links?: Array<Record<string, unknown>>
              devices?: unknown[]
              evidence_available?: boolean
            }
          }
          const liveLinks = response.live?.links ?? []
          const sourceDevice = workspace.devices.find(
            (device) => device.id === source.deviceId,
          )
          const targetDevice = workspace.devices.find(
            (device) => device.id === targetDeviceId,
          )
          const observation = comparePhysicalConnection(createdLink, workspace.devices, liveLinks)
          const status = observation.status
          if (status === "PORT_MISMATCH") {
            setVerificationAlert({
              title: "WRONG PHYSICAL CONNECTION",
              message: "The selected ports do not match the live physical connection.",
              expected: `${sourceDevice?.name || source.deviceId} / ${source.port} ↔ ${targetDevice?.name || targetDeviceId} / ${targetPort}`,
              actual: `${observation.source_device} / ${observation.source_port} ↔ ${observation.target_device} / ${observation.target_port}`,
            })
          } else setVerificationAlert(null)
          setWorkspace((current) => ({
            ...current,
            links: current.links.map((link) =>
              link.id === createdLink.id ? { ...link, status } : link,
            ),
          }))
          setChanges(result.changes ?? [])
          setActualWorkspace(normalizeWorkspace({
            devices: workspace.devices,
            links: response.live?.links ?? [],
          }))
          if (status === "VERIFIED")
            toast.success(
              `Physical connectivity verified${
                observation.evidence_source
                  ? ` · Evidence: ${observation.evidence_source}`
                  : ""
              }`,
            )
          else if (status === "DEVICE_OFFLINE")
            toast.error("Physical verification unavailable — device offline")
          else if (status === "PORT_MISMATCH")
            toast.error(
              "Wrong physical connection: selected ports do not match live wiring",
            )
          else if (status === "DISCONNECTED")
            toast.error("No matching physical connection found")
          else toast.error("Physical connectivity could not be verified")
        })
      })
      .catch(() => {
        setWorkspace((current) => ({
          ...current,
          links: current.links.map((link) =>
            link.id === createdLink.id ? { ...link, status: "UNKNOWN" } : link,
          ),
        }))
        toast.error("Physical connectivity could not be verified")
      })
  }
  const autoLayout = () => {
    const next = {
      ...workspace,
      devices: workspace.devices.map((d, i) => ({
        ...d,
        x: 180 + (i % 5) * 250,
        y: 150 + Math.floor(i / 5) * 190,
      })),
    }
    updateWorkspace(next)
  }
  const undo = () => {
    const previous = history.at(-1)
    if (!previous) return
    setFuture((items) => [...items, workspace])
    setHistory((items) => items.slice(0, -1))
    setWorkspace(previous)
    scheduleSave(previous)
  }
  const redo = () => {
    const next = future.at(-1)
    if (!next) return
    setHistory((items) => [...items, workspace])
    setFuture((items) => items.slice(0, -1))
    setWorkspace(next)
    scheduleSave(next)
  }
  const removeSelected = () => {
    if (selectedId) {
      const device = workspace.devices.find((d) => d.id === selectedId)
      if (!device) return
      setRemoveConfirmDevice(device)
      return
    } else if (selectedLinkId)
      updateWorkspace({
        ...workspace,
        links: workspace.links.filter((l) => l.id !== selectedLinkId),
      })
    setSelectedId(null)
    setSelectedLinkId(null)
    setDetailsOpen(false)
  }
  const confirmRemoveDevice = () => {
    if (!removeConfirmDevice) return
    const deviceId = removeConfirmDevice.id
    updateWorkspace({
      devices: workspace.devices.filter((device) => device.id !== deviceId),
      links: workspace.links.filter(
        (link) => link.from !== deviceId && link.to !== deviceId,
      ),
    })
    setRemoveConfirmDevice(null)
    setSelectedId(null)
    setSelectedLinkId(null)
    setDetailsOpen(false)
  }
  const exportSvg = () => {
    const svg = svgRef.current
    if (!svg) return
    const blob = new Blob([new XMLSerializer().serializeToString(svg)], {
      type: "image/svg+xml",
    })
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = "manual-topology.svg"
    a.click()
    URL.revokeObjectURL(url)
  }
  const exportPng = () => {
    const svg = svgRef.current
    if (!svg) return
    const image = new Image()
    const url = URL.createObjectURL(
      new Blob([new XMLSerializer().serializeToString(svg)], {
        type: "image/svg+xml",
      }),
    )
    image.onload = () => {
      const canvas = document.createElement("canvas")
      canvas.width = CANVAS.width
      canvas.height = CANVAS.height
      canvas.getContext("2d")?.drawImage(image, 0, 0)
      canvas.toBlob((blob) => {
        if (!blob) return
        const link = document.createElement("a")
        link.href = URL.createObjectURL(blob)
        link.download = "manual-topology.png"
        link.click()
      })
      URL.revokeObjectURL(url)
    }
    image.src = url
  }
  const exportPdf = () => window.print()
  const addBend = () => {
    if (!selectedLinkId) return
    const link = workspace.links.find((item) => item.id === selectedLinkId)
    if (!link) return
    const a = workspace.devices.find((d) => d.id === link.from)
    const b = workspace.devices.find((d) => d.id === link.to)
    if (!a || !b) return
    updateWorkspace({
      ...workspace,
      links: workspace.links.map((item) =>
        item.id === link.id
          ? {
              ...item,
              routingPoints: [
                ...(item.routingPoints ?? []),
                { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 },
              ],
            }
          : item,
      ),
    })
  }
  const resetRoute = () => {
    if (!selectedLinkId) return
    updateWorkspace({
      ...workspace,
      links: workspace.links.map((item) =>
        item.id === selectedLinkId
          ? { ...item, routingPoints: undefined }
          : item,
      ),
    })
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
      setChanges(result.changes ?? [])
      if (action === "accept_real_change" && result.payload) {
        const next = normalizeWorkspace(result.payload)
        setWorkspace(next)
        localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
      }
      toast.success(
        action === "keep_manual"
          ? "Manual topology kept."
          : "Real topology change accepted.",
      )
      setResolutionNotice(
        action === "keep_manual"
          ? `${change.change_type}: MANUAL RETAINED — live difference remains under review.`
          : `${change.change_type}: REAL CHANGE ACCEPTED — manual topology updated from physical evidence.`,
      )
      setSelectedChange(null)
    } catch {
      toast.error("Unable to resolve topology change.")
    }
  }
  const confirmConnectivity = async () => {
    if (!selectedLink) return
    const next = {
      ...workspace,
      links: workspace.links.map(link => link.id === selectedLink.id
        ? { ...link, status: "VERIFIED", evidence_source: "MANUAL_CONFIRMATION" }
        : link),
    }
    setConfirmingConnectivity(true)
    try {
      const saved = await save(next)
      if (!saved) return
      commit(next)
      setSelectedChange(null)
      setResolutionNotice("CONNECTIVITY CONFIRMED — link marked VERIFIED by user.")
      toast.success("Connectivity marked as verified.")
    } finally {
      setConfirmingConnectivity(false)
    }
  }
  const runPhysicalDiscovery = async () => {
    if (!snapshotId || discoveryBusy) return
    setDiscoveryBusy(true)
    toast.info("Discovery running — collecting fresh physical topology...")
    try {
      // Use fresh backend topology evidence; the visual layout cache is not
      // part of Manual Discovery authority.
      const freshTopology = await getSNMPTopology(undefined, false)
      // Discovery is deliberately independent of the visual layout cache.
      const liveTopology: Awaited<ReturnType<typeof getSNMPTopology>> | null = freshTopology
      let canvasDevices = [...workspace.devices]
      const topologyValue = liveTopology as unknown as Record<string, unknown>
      const topologyDevices = Array.isArray(topologyValue.devices) ? topologyValue.devices as Record<string, unknown>[] : []
      const identity = (item: Record<string, unknown>) => ({ id: normId(valueOf(item, "backendDeviceId", "backend_device_id", "deviceId", "id", "device_id")), ip: normIp(valueOf(item, "ip_address", "ip", "management_ip")), mac: normMac(valueOf(item, "mac_address", "mac")), name: normId(valueOf(item, "hostname", "name", "sys_name", "system_name")) })
      const matches = (raw: Record<string, unknown>, side: "source" | "target") => {
        const id = normId(valueOf(raw, `${side}_device_id`, side === "source" ? "source" : "target"))
        const ip = normIp(valueOf(raw, `${side}_ip`, `${side}_management_ip`, side === "source" ? "local_ip" : "remote_ip"))
        const mac = normMac(valueOf(raw, `${side}_mac`, `${side}_chassis_id`, side === "source" ? "source_chassis_id" : "remote_chassis_id"))
        const name = normId(valueOf(raw, `${side}_hostname`, `${side}_device_name`, `${side}_system_name`, side === "target" ? "remote_hostname" : "source_hostname"))
        const candidates = [...(realDevices as unknown as Record<string, unknown>[]), ...topologyDevices]
        return candidates.find((d) => {
          const item = identity(d)
          return (id && item.id === id) || (ip && item.ip === ip) || (mac && item.mac === mac) || (name && item.name === name)
        })
      }
      const discoveryInventory = realDevices as unknown as DeviceRecord[]
      const discoveryNodes = discoveryInventory.map((item, index) => makeNode(item, `inventory-${index}`))
      const collections = await Promise.all(discoveryNodes.map((node) => collectTopologyDevice(node, true)))
      const logicalGraph = buildLogicalTopologyGraph({
        collections,
        inventory: discoveryInventory,
        topologyNodes: topologyDevices,
        topologyLinks: Array.isArray(topologyValue.links) ? topologyValue.links : [],
      })
      const logicalTopology = { ...liveTopology, devices: logicalGraph.nodes, links: logicalGraph.links }
      const initial = discoverPhysicalLinks(logicalTopology, canvasDevices)
      for (const raw of initial.unresolved) {
        const item = matches(raw, "target")
        if (!item || canvasDevices.some((d) => normId(d.backendId) === normId(valueOf(item, "id", "device_id")))) continue
        const backendId = Number(valueOf(item, "id", "device_id"))
        if (!Number.isFinite(backendId)) continue
        const type = String(valueOf(item, "device_type", "type") ?? "Network Device")
        const name = String(valueOf(item, "hostname", "name", "sys_name", "system_name") ?? `Device ${backendId}`)
        const ip = String(valueOf(item, "ip_address", "ip", "management_ip") ?? "")
        canvasDevices.push({ id: `device-${backendId}`, backendId, name, subtitle: ip, ipAddress: ip || undefined, macAddress: String(valueOf(item, "mac_address", "mac") ?? "") || undefined, type, tone: toneFor(type, canvasDevices.length), status: String(valueOf(item, "status") ?? "unknown"), model: String(valueOf(item, "model") ?? "") || undefined, x: 220 + (canvasDevices.length % 4) * 260, y: 180 + Math.floor(canvasDevices.length / 4) * 190, ports: [] })
      }
      const discovered = discoverPhysicalLinks(logicalTopology, canvasDevices)
      console.debug("MANUAL_DISCOVERY_FROM_NETWORK_TOPOLOGY", {
        networkTopologyLinks: Array.isArray((liveTopology as unknown as Record<string, unknown>).links) ? ((liveTopology as unknown as Record<string, unknown>).links as unknown[]).length : 0,
        mappedLinks: discovered.links.length,
        createdLinks: discovered.links.length,
        skippedLinks: discovered.discarded,
      })
      const manualLinks = workspace.links.filter((link) => link.origin !== "discovered_physical")
      const nextWorkspace = { devices: canvasDevices, links: [...manualLinks, ...discovered.links] }
      const result = await reconcileManualTopology(snapshotId)
      setChanges(result.changes ?? [])
      setWorkspace(nextWorkspace)
      commit(nextWorkspace)
      localStorage.setItem(STORAGE_KEY, JSON.stringify(nextWorkspace))
      const saved = await save(nextWorkspace)
      if (!saved) throw new Error("workspace save failed")
      setActualWorkspace({ devices: canvasDevices, links: discovered.links })
      setView("actual")
      toast.success(`Discovery complete — ${canvasDevices.length} devices, ${discovered.links.length} physical links synchronized${discovered.discarded ? `; ${discovered.discarded} could not be mapped` : ""}.`)
    } catch {
      toast.error("Physical discovery could not be completed or saved.")
    } finally {
      setDiscoveryBusy(false)
    }
  }
  const issueStatus = (change: ManualTopologyChange) =>
    String(change.change_type || "UNKNOWN")
      .toUpperCase()
      .includes("PORT")
      ? "PORT_MISMATCH"
      : String(change.change_type || "UNKNOWN")
            .toUpperCase()
            .includes("DISCONNECT")
        ? "DISCONNECTED"
        : String(change.observed?.status ?? "UNKNOWN").toUpperCase()
  const isPartialDiscovery = (change: ManualTopologyChange) =>
    issueStatus(change) === "PARTIAL_DISCOVERY" ||
    (Boolean(change.observed?.evidence_source) &&
      issueStatus(change) === "UNKNOWN" &&
      (Boolean(change.observed?.source_port) !== Boolean(change.observed?.target_port)))
  const evidenceValue = (
    record: Record<string, unknown> | null | undefined,
    keys: string[],
  ) => {
    const aliases: Record<string, string[]> = {
      source_device: ["from", "source_node"], target_device: ["to", "target_node"],
      source_port: ["fromPort", "local_port"], target_port: ["toPort", "remote_port"],
    }
    const value = keys.flatMap(key => [key, ...(aliases[key] ?? [])])
      .map((key) => record?.[key])
      .find((item) => item != null && String(item) !== "")
    if (keys.includes("source_device") || keys.includes("target_device")) {
      return workspace.devices.find(device => device.id === String(value))?.name || (value == null ? "Not discovered" : String(value))
    }
    return value == null ? "Not discovered" : String(value)
  }
  const deviceReference = (record: Record<string, unknown> | null | undefined, keys: string[]) => {
    const value = evidenceValue(record, keys)
    const device = workspace.devices.find(item => item.id === value || item.backendId != null && String(item.backendId) === value)
    if (!device) return value
    return device.name || device.ipAddress || device.macAddress || device.id
  }
  const observedPortValue = (change: ManualTopologyChange, side: "source" | "target") => {
    const value = evidenceValue(change.observed, side === "source"
      ? ["source_port", "from_port", "port"]
      : ["target_port", "to_port", "remote_port"])
    return value
  }
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement
      if (
        target.isContentEditable ||
        ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)
      )
        return
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "z") {
        event.preventDefault()
        event.shiftKey ? redo() : undo()
      } else if (
        (event.metaKey || event.ctrlKey) &&
        event.key.toLowerCase() === "y"
      ) {
        event.preventDefault()
        redo()
      } else if (event.key === "Delete" || event.key === "Backspace") {
        event.preventDefault()
        removeSelected()
      } else if (event.key === "Escape") {
        setSelectedId(null)
        setSelectedLinkId(null)
        setSelectedChange(null)
        setConnectMode(false)
        setSource(null)
      } else if (event.key === "/") {
        event.preventDefault()
        document
          .querySelector<HTMLInputElement>(
            'input[placeholder="Search device..."]',
          )
          ?.focus()
      } else if (event.key.toLowerCase() === "f") {
        event.preventDefault()
        setZoom(1)
        setPan({ x: 0, y: 0 })
      } else if (event.key.toLowerCase() === "l") {
        event.preventDefault()
        autoLayout()
      }
    }
    window.addEventListener("keydown", handler)
    return () => window.removeEventListener("keydown", handler)
  }, [workspace, history, future, selectedId, selectedLinkId])
  useEffect(() => {
    const reset = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setSource(null)
        setTargetDeviceId(null)
        setTargetPort(null)
        setConnectionError(null)
        setPointer(null)
        setConnectMode(false)
      }
    }
    window.addEventListener("keydown", reset)
    return () => window.removeEventListener("keydown", reset)
  }, [])
  useEffect(() => {
    if (!canvasFullscreen) return
    const closeFullscreen = (event: KeyboardEvent) => {
      if (event.key === "Escape") setCanvasFullscreen(false)
    }
    window.addEventListener("keydown", closeFullscreen)
    return () => window.removeEventListener("keydown", closeFullscreen)
  }, [canvasFullscreen])
  useEffect(() => {
    const syncFullscreenState = () =>
      setPageFullscreen(document.fullscreenElement === mainRef.current)
    document.addEventListener("fullscreenchange", syncFullscreenState)
    return () =>
      document.removeEventListener("fullscreenchange", syncFullscreenState)
  }, [])
  useEffect(() => {
    if (
      connectMode &&
      source &&
      selectedId &&
      selectedId !== source.deviceId &&
      !targetDeviceId
    )
      setTargetDeviceId(selectedId)
  }, [connectMode, source, selectedId, targetDeviceId])
  const canvasWorkspace =
    view === "actual" && actualWorkspace.devices.length
      ? actualWorkspace
      : workspace
  const canvasDevices =
    view === "actual" && actualWorkspace.devices.length
      ? actualWorkspace.devices
      : visibleDevices
  const canvasLinks =
    view === "actual" && actualWorkspace.devices.length
      ? actualWorkspace.links
      : visibleLinks
  const unexpectedLinks =
    view === "compare"
      ? actualWorkspace.links.filter(
          (actual) =>
            !workspace.links.some(
              (manual) =>
                [manual.from, manual.to].sort().join("::") ===
                [actual.from, actual.to].sort().join("::"),
            ),
        )
      : []
  const linkEndpoints = (link: Link) => {
    const a = canvasWorkspace.devices.find((d) => d.id === link.from)
    const b = canvasWorkspace.devices.find((d) => d.id === link.to)
    if (!a || !b) return null
    return {
      source: portEndpoint(a, link, canvasWorkspace.links, canvasWorkspace.devices),
      target: portEndpoint(b, link, canvasWorkspace.links, canvasWorkspace.devices),
      sourceDevice: a,
      targetDevice: b,
    }
  }
  const linkPath = (link: Link) => {
    const endpoints = linkEndpoints(link)
    if (!endpoints) return null
    const points = [
      endpoints.source,
      endpoints.source.exit,
      ...(link.routingPoints ?? []),
      endpoints.target.exit,
      endpoints.target,
    ]
    return points.map((p, i) => `${i ? "L" : "M"} ${p.x} ${p.y}`).join(" ")
  }
  const previewAnchor = (device: Device, target: { x: number y: number }) => {
    return {
      x: device.x + NODE_SOCKET.x,
      y: device.y + NODE_SOCKET.y,
    }
  }
  const actualPath = (link: Link) => {
    const a = actualWorkspace.devices.find((d) => d.id === link.from)
    const b = actualWorkspace.devices.find((d) => d.id === link.to)
    if (!a || !b) return null
    const start = portEndpoint(a, link, actualWorkspace.links, actualWorkspace.devices)
    const end = portEndpoint(b, link, actualWorkspace.links, actualWorkspace.devices)
    return `M ${start.x} ${start.y} L ${start.exit.x} ${start.exit.y} L ${end.exit.x} ${end.exit.y} L ${end.x} ${end.y}`
  }
  const selectedLink =
    workspace.links.find((link) => link.id === selectedLinkId) ?? null
  const selectedLinkDifference = selectedLink
    ? (() => {
        const fromDevice = workspace.devices.find(
          (device) => device.id === selectedLink.from,
        )
        const toDevice = workspace.devices.find(
          (device) => device.id === selectedLink.to,
        )
        return {
          id: -1,
          change_type: "CONNECTION_REVIEW",
          signature: selectedLink.id,
          status: selectedLink.status || "UNKNOWN",
          expected: {
            source_device: fromDevice?.name || selectedLink.from,
            source_port: selectedLink.fromPort || "PORT UNKNOWN",
            target_device: toDevice?.name || selectedLink.to,
            target_port: selectedLink.toPort || "PORT UNKNOWN",
          },
          observed: {
            status: "UNKNOWN",
            reason: "Refresh live physical evidence to verify this connection.",
            evidence_source:
              (selectedLink as Link & { evidence_source?: string })
                .evidence_source || "N/A",
          },
          detected_at: null,
        } satisfies ManualTopologyChange
      })()
    : null
  const applyActualConnection = async () => {
    if (!selectedChange?.observed || applyingActual) return
    const link = workspace.links.find(item => item.id === selectedChange.signature)
    if (!link) return
    const observed = selectedChange.observed
    const endpoint = (side: "from" | "to") => {
      const assigned = Boolean(observed[side === "from" ? "source_port_assigned" : "target_port_assigned"])
      const oldPort = side === "from" ? link.fromPort : link.toPort
      const raw = String(observed[side === "from" ? "source_port" : "target_port"] || "")
      if (!assigned && (!raw || /not discovered|unknown|n\/a/i.test(raw))) return null
      const device = workspace.devices.find(item => item.id === link[side])
      const port = assigned ? oldPort : device?.ports?.find(name => compactPortLabel(name).toLowerCase() === compactPortLabel(raw).toLowerCase()) || raw
      const iface = (interfaces[link[side]] || []).find(item => item.name === port)
      return { port, ifIndex: iface?.ifIndex, origin: assigned ? "manual_fallback" : iface?.source || device?.portSources?.[port || ""] || "snmp" }
    }
    const from = endpoint("from"), to = endpoint("to")
    if (!from?.port || !to?.port) { toast.error("Actual endpoint ports are not available."); return }
    const occupied = workspace.links.some(item => item.id !== link.id && (
      (item.from === link.from && item.fromPort === from.port) || (item.to === link.from && item.toPort === from.port) ||
      (item.from === link.to && item.fromPort === to.port) || (item.to === link.to && item.toPort === to.port)))
    if (occupied) { toast.error("An actual port is already used by another connection. Remove that connection first."); return }
    const corrected = { ...link, fromPort: from.port, toPort: to.port, fromIfIndex: from.ifIndex, toIfIndex: to.ifIndex,
      fromPortSource: from.origin, toPortSource: to.origin, label: `${from.port} - ${to.port}` }
    const checked = comparePhysicalConnection(corrected, workspace.devices, [observed])
    const next = { ...workspace, links: workspace.links.map(item => item.id === link.id ? { ...corrected, status: checked.status } : item) }
    setApplyingActual(true)
    if (saveTimer.current) window.clearTimeout(saveTimer.current)
    try {
      const saved = await save(next)
      if (!saved) { localStorage.setItem(STORAGE_KEY, JSON.stringify(workspace)); return }
      commit(next)
      setVerificationAlert(null)
      setSelectedChange(null)
      toast.success("Connection changed to the actual physical ports.")
    } finally { setApplyingActual(false) }
  }
  const openSelectedLinkDifference = async () => {
    if (!selectedLinkDifference) return
    if (!snapshotId) {
      setSelectedChange(selectedLinkDifference)
      return
    }
    setDifferenceLoading(true)
    try {
      const result = await reconcileManualTopology(snapshotId)
      const response = result as typeof result & {
        live?: { links?: Array<Record<string, unknown>> }
      }
      const refreshedChanges = response.changes ?? []
      const observation = comparePhysicalConnection(selectedLink!, workspace.devices, response.live?.links ?? [])
      setChanges(refreshedChanges)
      setActualWorkspace(normalizeWorkspace({
        devices: workspace.devices,
        links: response.live?.links ?? [],
      }))
      setSelectedChange({
        ...selectedLinkDifference,
        id: -1,
        change_type: "CONNECTION_REVIEW",
        observed: observation,
        status: observation.status,
        detected_at: String(observation.last_verified_at ?? observation.observed_at ?? "") || null,
      })
      setWorkspace(current => ({ ...current, links: current.links.map(link =>
        link.id === selectedLink?.id ? { ...link, status: observation.status } : link) }))
    } catch {
      setSelectedChange(selectedLinkDifference)
      toast.error("Live physical evidence could not be refreshed.")
    } finally {
      setDifferenceLoading(false)
    }
  }
  const previewSource = source
    ? workspace.devices.find((device) => device.id === source.deviceId)
    : null
  const previewPath =
    previewSource && pointer && !targetPort
      ? (() => {
          const start = previewAnchor(previewSource, pointer)
          return `M ${start.x} ${start.y} L ${pointer.x} ${pointer.y}`
        })()
      : null
  const previewSocket =
    previewSource && pointer && !targetPort
      ? previewAnchor(previewSource, pointer)
      : null
  const portPanelDevice =
    workspace.devices.find(
      (device) => device.id === (targetDeviceId ?? selectedId),
    ) ?? null
  const portPanelAllPorts = portPanelDevice
    ? ((portView === "all"
        ? allInterfaces[portPanelDevice.id]
        : interfaces[portPanelDevice.id]) ??
      (portPanelDevice.ports?.length
        ? portPanelDevice.ports.map((name, index) => ({
            ...fallbackPort(),
            id: index,
            name,
            source:
              portPanelDevice.portSources?.[name] ?? "manual_fallback" as const,
            operStatus: portPanelDevice.portStatuses?.[name] ?? "UNKNOWN",
          }))
        : [fallbackPort()]))
    : []
  const portPanelPorts = portPanelAllPorts.filter(
    (port) =>
      (portView === "all" || !isLogicalPort(port)) &&
      (!portSearch ||
        `${port.name} ${port.description ?? ""}`
          .toLowerCase()
          .includes(portSearch.toLowerCase())) &&
      (portStatus === "all" || port.operStatus.toLowerCase() === portStatus),
  )
  const portOccupancy = useMemo(
    () =>
      new Map(
        portPanelAllPorts.map((port) => [
          port.name,
          getPortOccupancy(workspace, portPanelDevice?.id || "", port),
        ]),
      ),
    [workspace, portPanelAllPorts, portPanelDevice?.id],
  )
  const selectedPortSummary = useMemo(() => {
    const total = portPanelAllPorts.length
    const up = portPanelAllPorts.filter(
      (port) => port.operStatus.toUpperCase() === "UP",
    ).length
    const down = portPanelAllPorts.filter(
      (port) => port.operStatus.toUpperCase() === "DOWN",
    ).length
    const used = portPanelAllPorts.filter(
      (port) =>
        getPortOccupancy(workspace, portPanelDevice?.id || "", port).occupied,
    ).length
    return { total, up, down, used, available: Math.max(total - used, 0) }
  }, [workspace, portPanelAllPorts, portPanelDevice?.id])
  const locations = [
    ...new Set(
      workspace.devices.map((device) => device.location).filter(Boolean),
    ),
  ] as string[]
  const onlineCount = workspace.devices.filter(
    (device) =>
      !["offline", "down", "unreachable"].includes(
        device.status?.toLowerCase() || "",
      ),
  ).length
  const linkCounts = {
    verified: workspace.links.filter((link) => link.status === "VERIFIED")
      .length,
    issues: workspace.links.filter((link) =>
      ["PORT_MISMATCH", "DISCONNECTED", "UNEXPECTED"].includes(
        link.status || "",
      ),
    ).length,
    unknown: workspace.links.filter((link) =>
      ["UNKNOWN", "VERIFYING"].includes(link.status || ""),
    ).length,
  }
  const availableDevices = realDevices.filter(
    (item) => !workspace.devices.some((device) => device.backendId === item.id),
  )
  const changeCanvasZoom = (nextZoom: number) => {
    const next = zoomViewport({ zoom, pan }, nextZoom)
    setViewports(previous => ({ ...previous, [view]: next }))
  }
  const zoomAtClientPoint = (
    event: React.WheelEvent<SVGSVGElement>,
    nextZoom: number,
  ) => {
    const rect = svgRef.current?.getBoundingClientRect()
    if (!rect) return
    const sx = ((event.clientX - rect.left) / rect.width) * CANVAS.width
    const sy = ((event.clientY - rect.top) / rect.height) * CANVAS.height
    const worldX = (sx - pan.x) / zoom
    const worldY = (sy - pan.y) / zoom
    setZoom(nextZoom)
    setPan({ x: sx - worldX * nextZoom, y: sy - worldY * nextZoom })
  }
  const fitToView = () => {
    const devices = canvasDevices
    if (!devices.length) {
      setZoom(1)
      setPan({ x: 0, y: 0 })
      return
    }
    const padding = 150
    const minX = Math.min(...devices.map((device) => device.x - 70))
    const maxX = Math.max(...devices.map((device) => device.x + 70))
    const minY = Math.min(...devices.map((device) => device.y - 55))
    const maxY = Math.max(...devices.map((device) => device.y + 55))
    const nextZoom = clampZoom(
      Math.min(
        CANVAS.width / Math.max(maxX - minX + padding, 1),
        CANVAS.height / Math.max(maxY - minY + padding, 1),
      ),
    )
    const centerX = (minX + maxX) / 2
    const centerY = (minY + maxY) / 2
    setZoom(nextZoom)
    setPan({
      x: CANVAS.width / 2 - centerX * nextZoom,
      y: CANVAS.height / 2 - centerY * nextZoom,
    })
  }
  const focusDevice = (device: Device) => {
    setSelectedId(device.id)
    const nextZoom = Math.max(1.5, zoom)
    setZoom(clampZoom(nextZoom))
    setPan({
      x: CANVAS.width / 2 - device.x * clampZoom(nextZoom),
      y: CANVAS.height / 2 - device.y * clampZoom(nextZoom),
    })
    setInspectorTab("overview")
  }
  const togglePageFullscreen = async () => {
    try {
      if (document.fullscreenElement) {
        await document.exitFullscreen()
      } else {
        await mainRef.current?.requestFullscreen()
      }
    } catch {
      // Browsers can deny fullscreen; the canvas fullscreen control remains available.
      setCanvasFullscreen((value) => !value)
    }
  }
  const beginConnect = (deviceId?: string) => {
    setConnectMode(true)
    setInspectorTab("ports")
    setConnectionError(null)
    if (deviceId) {
      setSelectedId(deviceId)
      setTargetDeviceId(null)
      setTargetPort(null)
    }
  }
  const openDevicePorts = (device: Device) => {
    setSource(null)
    setTargetDeviceId(null)
    setTargetPort(null)
    setConnectionError(null)
    focusDevice(device)
    beginConnect(device.id)
  }
  const chooseTarget = (deviceId: string) => {
    if (!connectMode || !source || deviceId === source.deviceId) return
    setTargetDeviceId(deviceId)
    setTargetPort(null)
    setInspectorTab("ports")
    setSelectedId(deviceId)
  }
  const portStatusTone = (port: NormalizedPort) =>
    port.source === "manual_fallback"
      ? "#d4a95c"
      : port.operStatus.toUpperCase() === "UP"
        ? "#61c98d"
        : port.operStatus.toUpperCase().includes("DOWN")
          ? "#d9646a"
          : "#9aa3a0"
  const linkTone = (status?: string) =>
    ({
      VERIFIED: "#61c98d",
      VERIFYING: "#9b8afb",
      PORT_MISMATCH: "#ff4d5e",
      DISCONNECTED: "#d9646a",
      UNEXPECTED: "#d9646a",
      DEVICE_OFFLINE: "#78827e",
      UNKNOWN: "#9aa3a0",
    })[status || "UNKNOWN"] || "#68737a"

  const editDevice = (device: Device) => {
    if (connectMode) resetConnection()
    setEditingDeviceId(device.id)
    setEditErrors({})
    setEditForm({
      name: device.name,
      type: device.type,
      ip: device.ipAddress || device.subtitle || "",
      mac: device.macAddress || "",
      location: device.location || "",
      description: device.description || "",
      vendor: device.vendor || "",
      model: device.model || "",
      serial: device.serialNumber || "",
      firmware: device.firmware || "",
      snmpVersion: device.snmpVersion || "",
    })
    setInspectorTab("overview")
  }
  const cancelEditDevice = () => {
    setEditingDeviceId(null)
    setEditForm(null)
    setEditErrors({})
  }
  const saveEditedDevice = async () => {
    const device = workspace.devices.find((item) => item.id === editingDeviceId)
    if (!device || !editForm || editSaving) return
    const errors: Record<string, string> = {}
    if (!editForm.name.trim()) errors.name = "Device name is required"
    if (
      editForm.ip.trim() &&
      !/^((25[0-5]|2[0-4]\d|1?\d?\d)(\.|$)){4}$/.test(editForm.ip.trim())
    )
      errors.ip = "Invalid IP address"
    if (
      editForm.mac.trim() &&
      !/^([0-9a-f]{2}[:-]){5}[0-9a-f]{2}$/i.test(editForm.mac.trim())
    )
      errors.mac = "Invalid MAC address"
    setEditErrors(errors)
    if (Object.keys(errors).length) return
    const changed =
      editForm.name.trim() !== device.name ||
      editForm.type !== device.type ||
      editForm.ip.trim() !== (device.ipAddress || device.subtitle || "") ||
      editForm.mac.trim() !== (device.macAddress || "") ||
      editForm.location.trim() !== (device.location || "") ||
      editForm.description.trim() !== (device.description || "")
      || editForm.vendor.trim() !== (device.vendor || "")
      || editForm.model.trim() !== (device.model || "")
      || editForm.serial.trim() !== (device.serialNumber || "")
      || editForm.firmware.trim() !== (device.firmware || "")
      || editForm.snmpVersion.trim() !== (device.snmpVersion || "")
    if (!changed) return
    setEditSaving(true)
    try {
      if (device.backendId) {
        await updateDevice(device.backendId, {
          hostname: editForm.name.trim(),
          ip_address: editForm.ip.trim() || undefined,
          mac_address: editForm.mac.trim() || undefined,
          model: editForm.model.trim() || undefined,
          serial_number: editForm.serial.trim() || undefined,
          firmware_version: editForm.firmware.trim() || undefined,
          vendor_name: editForm.vendor.trim() || undefined,
          topology_metadata: {
            ...device.topologyMetadata,
            manual_type: editForm.type.trim() || "Network Device",
            location: editForm.location.trim() || null,
            description: editForm.description.trim() || null,
            manual_vendor: editForm.vendor.trim() || null,
            manual_snmp_version: editForm.snmpVersion.trim() || null,
          },
        })
      }
      const nextDevice: Device = {
        ...device,
        name: editForm.name.trim(),
        type: editForm.type.trim() || "Network Device",
        tone: toneFor(
          editForm.type.trim() || "Network Device",
          workspace.devices.indexOf(device),
          editForm.name.trim(),
          device.vendor,
          device.model,
        ),
        subtitle: editForm.ip.trim() || undefined,
        ipAddress: editForm.ip.trim() || undefined,
        macAddress: editForm.mac.trim() || undefined,
        location: editForm.location.trim() || undefined,
        description: editForm.description.trim() || undefined,
        vendor: editForm.vendor.trim() || undefined,
        model: editForm.model.trim() || undefined,
        serialNumber: editForm.serial.trim() || undefined,
        firmware: editForm.firmware.trim() || undefined,
        snmpVersion: editForm.snmpVersion.trim() || undefined,
        topologyMetadata: {
          ...device.topologyMetadata,
          manual_type: editForm.type.trim() || "Network Device",
          location: editForm.location.trim() || null,
          description: editForm.description.trim() || null,
          manual_vendor: editForm.vendor.trim() || null,
          manual_snmp_version: editForm.snmpVersion.trim() || null,
        },
      }
      updateWorkspace({
        ...workspace,
        devices: workspace.devices.map((item) =>
          item.id === device.id ? nextDevice : item,
        ),
      })
      cancelEditDevice()
      toast.success("Changes saved")
    } catch {
      setEditErrors({ form: "Failed to update device. Please retry." })
      toast.error("Failed to update device")
    } finally {
      setEditSaving(false)
    }
  }
  const portForDevice = (deviceId: string, portName: string) =>
    [...(interfaces[deviceId] || []), ...(allInterfaces[deviceId] || [])].find(
      (port) => port.name === portName,
    )
  const handlePortSelect = (device: Device, port: string) => {
    const portInfo = portForDevice(device.id, port) || {
      name: port,
      ifIndex: null,
    }
    if (isLogicalPort(portInfo)) {
      setConnectionError(
        "Logical interfaces cannot be used as physical endpoints.",
      )
      return
    }
    const occupancy = getPortOccupancy(workspace, device.id, portInfo)
    if (occupancy.occupied) {
      const peer = workspace.devices.find(
        (item) => item.id === occupancy.peerDeviceId,
      )
      setConnectionError(
        `Port already in use: ${device.name} / ${port} is connected to ${peer?.name || occupancy.peerDeviceId || "another device"} / ${occupancy.peerPortName || "unknown port"}.`,
      )
      setSelectedId(device.id)
      setInspectorTab("ports")
      return
    }
    setConnectionError(null)
    setSelectedId(device.id)
    setInspectorTab("ports")
    if (
      connectMode &&
      source &&
      !targetDeviceId &&
      device.id !== source.deviceId
    ) {
      setTargetDeviceId(device.id)
      setTargetPort(null)
      return
    }
    selectPort(device.id, port)
  }
  const createVerifiedConnection = () => {
    if (!source || !targetDeviceId || !targetPort) {
      setConnectionError(
        "Select a source device, source port, target device, and target port.",
      )
      return
    }
    const sourceInfo = portForDevice(source.deviceId, source.port) || {
      name: source.port,
      ifIndex: null,
    }
    const targetInfo = portForDevice(targetDeviceId, targetPort) || {
      name: targetPort,
      ifIndex: null,
    }
    const sourceOccupancy = getPortOccupancy(
      workspace,
      source.deviceId,
      sourceInfo,
    )
    const targetOccupancy = getPortOccupancy(
      workspace,
      targetDeviceId,
      targetInfo,
    )
    if (sourceOccupancy.occupied || targetOccupancy.occupied) {
      setConnectionError(
        "Port already in use. Choose another physical port or remove the existing connection.",
      )
      return
    }
    createConnection()
  }
  const statusBadge = (status?: string) => {
    const value = status?.toUpperCase() || "UNKNOWN"
    const icon =
      value === "VERIFIED"
        ? "✓"
        : value === "PORT_MISMATCH"
          ? "⚠"
          : value === "DISCONNECTED" || value === "UNEXPECTED"
            ? "×"
            : value === "VERIFYING"
              ? "◌"
              : "?"
    return (
      <span
        className="inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[9px] font-semibold"
        style={{
          color: linkTone(value),
          borderColor: `${linkTone(value)}55`,
          backgroundColor: `${linkTone(value)}12`,
        }}
      >
        {icon} {value.replaceAll("_", " ")}
      </span>
    )
  }

  return (
    <main
      ref={mainRef}
      className={`manual-topology-page min-h-full bg-[var(--t-bg)] p-3 text-[var(--t-text)] md:p-5 ${
        pageFullscreen ? "min-h-screen overflow-auto" : ""
      }`}
      onPointerUp={() => {
        if (dragFrame.current) {
          window.cancelAnimationFrame(dragFrame.current)
          dragFrame.current = null
        }
        if (
          dragMoved.current &&
          dragStartWorkspace.current &&
          dragLatestWorkspace.current
        ) {
          const latest = dragLatestWorkspace.current
          const next =
            snap && dragDeviceId.current
              ? {
                  ...latest,
                  devices: latest.devices.map((device) =>
                    device.id === dragDeviceId.current
                      ? {
                          ...device,
                          x: Math.round(device.x / 20) * 20,
                          y: Math.round(device.y / 20) * 20,
                        }
                      : device,
                  ),
                }
              : latest
          setWorkspace(next)
          setHistory((items) => [
            ...items.slice(-39),
            dragStartWorkspace.current as Workspace,
          ])
          setFuture([])
          dragLatestWorkspace.current = next
          scheduleSave(next)
        }
        setDrag(null)
        setCanvasDrag(null)
        setRoutingDrag(null)
        dragStartWorkspace.current = null
        dragLatestWorkspace.current = null
        dragDeviceId.current = null
        routingLatestWorkspace.current = null
      }}
    >
      {manualAddOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" role="dialog" aria-modal="true">
          <form
            className="w-full max-w-md rounded-xl border border-[#36c2b466] bg-[#11161a] p-5 shadow-[0_20px_60px_#000b]"
            onSubmit={(event) => { event.preventDefault(); createManualDevice() }}
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="font-mono text-[9px] uppercase tracking-[.2em] text-[#8b9693]">Manual Device</div>
                <h2 className="mt-1 text-lg font-semibold text-[#e7eceb]">Add {manualAddType}</h2>
                <p className="mt-1 text-[10px] text-[#9aa3a0]">Enter the details once to add this device to the topology.</p>
              </div>
              <button type="button" className="icon-tool" onClick={() => setManualAddOpen(false)} aria-label="Close">×</button>
            </div>
            <div className="mt-4 space-y-3">
              {[
                ["name", "Name", "Device name", true],
                ["ip", "IP Address", "Optional", false],
                ["mac", "MAC Address", "Optional", false],
                ["location", "Location", "Optional", false],
              ].map(([key, label, placeholder, required]) => (
                <label key={key as string} className="block">
                  <span className="mb-1 block font-mono text-[9px] uppercase tracking-wider text-[#9aa3a0]">{label as string}{required ? " *" : ""}</span>
                  <input
                    autoFocus={key === "name"}
                    required={Boolean(required)}
                    value={manualAddForm[key as keyof typeof manualAddForm]}
                    onChange={(event) => setManualAddForm((current) => ({ ...current, [key as string]: event.target.value }))}
                    placeholder={placeholder as string}
                    className="h-9 w-full rounded-md border border-white/[.12] bg-[#0b0e11] px-3 text-xs text-[#e7eceb] outline-none focus:border-[#36c2b4]"
                  />
                </label>
              ))}
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <button type="button" className="tool" onClick={() => setManualAddOpen(false)}>CANCEL</button>
              <button type="submit" className="tool border-[#61c98d66] text-[#61c98d]">ADD DEVICE</button>
            </div>
          </form>
        </div>
      )}
      <header className={`mb-3 rounded-xl border border-white/[.1] bg-[#11161a] p-4 shadow-[0_12px_35px_rgba(0,0,0,.22)] ${pageFullscreen ? "hidden" : ""}`}>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="font-mono text-[9px] uppercase tracking-[.24em] text-[#8b9693]">
              Network workspace / design board
            </div>
            <h1 className="mt-1 text-2xl font-semibold tracking-tight">
              {tr.manualTitle}
            </h1>
            <div className="font-mono text-[10px] text-[#9aa3a0]">
              {tr.manualSubtitle}
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={tr.searchDevices}
              aria-label={tr.searchDevices}
              className="h-9 w-64 rounded-md border border-white/[.12] bg-[#0b0e11] px-3 text-xs outline-none focus:border-[#9b8afb]"
            />
            <button
              className="tool border-[#61c98d66] text-[#61c98d]"
              onClick={() => {
                setPaletteOpen(true)
                setDevicePanelTab("manual")
              }}
            >
              + DEVICE
            </button>
            <button
              className={`tool ${
                connectMode ? "border-[#9b8afb] text-[#c7b9ff]" : ""
              }`}
              onClick={() => (connectMode ? resetConnection() : beginConnect())}
            >
              {tr.connect}
            </button>
            <button className="tool" onClick={autoLayout}>
              {tr.autoLayout}
            </button>
            <button
              className="tool"
              onClick={() => {
                setZoom(1)
                setPan({ x: 0, y: 0 })
              }}
            >
              {tr.fit}
            </button>
            <button
              className={`tool ${
                snap ? "border-[#61c98d] text-[#61c98d]" : ""
              }`}
              onClick={() => setSnap((value) => !value)}
            >
              {tr.snap} {snap ? tr.on : tr.off}
            </button>
            <button
              className="tool"
              title="Undo (Ctrl/Cmd+Z)"
              onClick={undo}
              disabled={!history.length}
            >
              {tr.undo}
            </button>
            <button
              className="tool"
              title="Redo (Ctrl/Cmd+Y)"
              onClick={redo}
              disabled={!future.length}
            >
              {tr.redo}
            </button>
            <button className="tool" onClick={exportSvg}>
              {tr.export}
            </button>
            <button
              className={`tool ${
                showPortLabels ? "border-[#61c98d] text-[#61c98d]" : ""
              }`}
              onClick={() => setShowPortLabels((value) => !value)}
              aria-pressed={showPortLabels}
            >
              {tr.showPorts} {showPortLabels ? tr.on : tr.off}
            </button>
            <button
              className="tool border-[#36c2b466] text-[#36c2b4]"
              title={pageFullscreen ? "Exit fullscreen" : "View topology fullscreen"}
              onClick={() => void togglePageFullscreen()}
            >
              {pageFullscreen ? "EXIT FULL" : "FULLSCREEN"}
            </button>
          </div>
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-2">
          {[
            {
              label: tr.devices,
              value: workspace.devices.length,
              tone: "#9aa3a0",
            },
            { label: tr.links, value: workspace.links.length, tone: "#9b8afb" },
            { label: tr.online, value: onlineCount, tone: "#61c98d" },
            {
              label: tr.issues,
              value: changes.length + linkCounts.issues,
              tone: "#d4a95c",
            },
          ].map((metric) => (
            <div
              key={metric.label}
              className="min-w-[92px] rounded-lg border border-white/[.08] bg-[#0d1113] px-3 py-2"
            >
              <div
                className="text-lg font-semibold"
                style={{ color: metric.tone }}
              >
                {metric.value}
              </div>
              <div className="font-mono text-[8px] tracking-[.16em] text-[#7f8b88]">
                {metric.label}
              </div>
            </div>
          ))}
          <div className="ml-auto rounded-md border border-white/[.1] bg-[#0d1113] p-1">
            {(["manual", "actual", "compare"] as ViewMode[]).map((mode) => (
              <button
                key={mode}
                className={`px-3 py-1.5 font-mono text-[9px] uppercase ${
                  view === mode
                    ? "rounded bg-[#25312d] text-[#61c98d]"
                    : "text-[#7f8b88]"
                }`}
                onClick={() => setView(mode)}
              >
                {mode}
              </button>
            ))}
          </div>
        </div>
      </header>
      {verificationAlert && (
        <div
          className="mt-3 rounded-xl border border-[#d9646a88] bg-[#3a191d] p-3 shadow-[0_8px_24px_#0005]"
          role="alert"
        >
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="font-mono text-[10px] font-bold uppercase tracking-[.16em] text-[#ff858a]">
                ⚠ {verificationAlert.title}
              </div>
              <div className="mt-1 text-xs text-[#f2c7c9]">
                {verificationAlert.message}
              </div>
              <div className="mt-2 grid gap-1 font-mono text-[9px] sm:grid-cols-2 sm:gap-x-6">
                <span>
                  <b className="font-normal text-[#a98b8e]">SELECTED:</b>{" "}
                  {verificationAlert.expected}
                </span>
                <span>
                  <b className="font-normal text-[#a98b8e]">ACTUAL:</b>{" "}
                  {verificationAlert.actual}
                </span>
              </div>
            </div>
            <button
              className="tool border-[#d9646a88] text-[#ff858a]"
              onClick={() => setVerificationAlert(null)}
            >
              DISMISS
            </button>
          </div>
        </div>
      )}
      {changes.length > 0 && (
        <div className="mt-3 rounded-lg border border-[#d4a95c66] bg-[#241f14] px-3 py-2" role="status">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px]">
            <span className="font-mono uppercase tracking-[.16em] text-[#d4a95c]">⚠ TOPOLOGY ALERT</span>
            <span className="text-[#e7d6ad]">
              {changes.length} mismatch{changes.length === 1 ? "" : "es"} detected · {changes[0].change_type}
            </span>
            <span className="font-mono text-[9px] text-[#9aa3a0]">
              {changes[0].status === "kept_manual" ? "MANUAL RETAINED" : "PENDING ACTION"}
            </span>
            <button className="tool ml-auto h-6 px-2 text-[9px]" onClick={() => setSelectedChange(changes[0])}>
              SHOW EVIDENCE
            </button>
          </div>
          <div className="mt-1 truncate font-mono text-[9px] text-[#a98b8e]">
            Expected: {evidenceValue(changes[0].expected, ["source_device", "from_device", "device"])} : {evidenceValue(changes[0].expected, ["source_port", "from_port", "port"])} → {evidenceValue(changes[0].expected, ["target_device", "to_device", "remote_device"])} : {evidenceValue(changes[0].expected, ["target_port", "to_port", "remote_port"])}
          </div>
          <div className="truncate font-mono text-[9px] text-[#9aa3a0]">
            Actual: {evidenceValue(changes[0].observed, ["source_device", "from_device", "device"])} : {evidenceValue(changes[0].observed, ["source_port", "from_port", "port"])} → {evidenceValue(changes[0].observed, ["target_device", "to_device", "remote_device"])} : {evidenceValue(changes[0].observed, ["target_port", "to_port", "remote_port"])} · Evidence: {evidenceValue(changes[0].observed, ["evidenceSource", "evidence_source", "source"])}
          </div>
        </div>
      )}
      {resolutionNotice && (
        <div className="mt-2 rounded border border-[#61c98d66] bg-[#13251b] px-3 py-2 font-mono text-[9px] text-[#9de0b6]" role="status">
          {resolutionNotice}
          <button className="ml-3 text-[#61c98d] underline" onClick={() => setResolutionNotice(null)}>DISMISS</button>
        </div>
      )}
      <section className={`grid ${pageFullscreen ? "h-[calc(100dvh-2.5rem)]" : "h-[calc(100dvh-220px)] min-h-[720px]"} min-h-0 grid-cols-1 items-stretch gap-3 ${
        devicesPanelOpen && sidebarOpen
          ? "xl:grid-cols-[300px_minmax(0,1fr)_315px]"
          : devicesPanelOpen
            ? "xl:grid-cols-[300px_minmax(0,1fr)]"
            : sidebarOpen
              ? "xl:grid-cols-[minmax(0,1fr)_315px]"
              : "xl:grid-cols-1"
      }`}>
        {devicesPanelOpen && (
        <aside className="flex h-full min-h-0 flex-col overflow-y-auto rounded-xl border border-white/[.1] bg-[#11161a] p-3">
          <div className="mb-2 flex shrink-0 justify-end">
            <button
              className="tool"
              aria-label="Hide symbols and devices sidebar"
              onClick={() => setDevicesPanelOpen(false)}
            >
              ‹ HIDE
            </button>
          </div>
          <div className="mb-3 shrink-0 rounded-lg border border-[#36c2b444] bg-[#0d1517] p-2.5">
            <div className="font-mono text-[10px] font-semibold uppercase tracking-[.18em] text-[#dce5e2]">
              NETWORK SYMBOLS
            </div>
            <input
              value={symbolSearch}
              onChange={(event) => setSymbolSearch(event.target.value)}
              placeholder="Search symbols..."
              aria-label="Search symbols"
              className="mt-2 h-8 w-full rounded border border-white/[.1] bg-[#0b0e11] px-2 text-[10px] outline-none focus:border-[#36c2b4]"
            />
            <div className="mt-2 max-h-36 space-y-1 overflow-y-auto overscroll-contain pr-1">
              {filteredSymbolLibrary.map((group) => {
                const collapsed = collapsedSymbols.has(group.category)
                return (
                  <div key={group.category} className="border-b border-white/[.06] pb-1">
                    <button
                      className="flex w-full items-center justify-between py-1 font-mono text-[8px] uppercase tracking-wider text-[#8b9693]"
                      onClick={() => setCollapsedSymbols((current) => {
                        const next = new Set(current)
                        if (next.has(group.category)) next.delete(group.category)
                        else next.add(group.category)
                        return next
                      })}
                    >
                      <span>{group.category}</span><span>{collapsed ? "+" : "−"}</span>
                    </button>
                    {!collapsed && (
                      <div className="grid grid-cols-2 gap-1">
                        {group.items.map((symbol) => (
                          <button
                            key={symbol}
                            draggable
                            onDragStart={(event) => event.dataTransfer.setData("application/x-nms-symbol", symbol)}
                            onClick={() => addDevice(symbol)}
                            className="flex min-h-14 flex-col items-center justify-center gap-1 rounded border border-white/[.08] bg-[#111b1d] p-1 text-center text-[8px] text-[#dce5e2] transition hover:border-[#36c2b4] hover:bg-[#172522]"
                            title={`Drag ${symbol} to the canvas`}
                          >
                            <svg width="24" height="24" viewBox="0 0 48 48" fill="none" stroke={toneFor(symbol)} strokeWidth="2" aria-hidden="true">
                              {glyph(symbol)}
                            </svg>
                            <span className="leading-tight">{symbol}</span>
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          </div>
          <div className="flex items-center justify-between">
            <div>
              <div className="font-mono text-[10px] uppercase tracking-[.18em] text-[#dce5e2]">
                Devices
              </div>
              <div className="mt-1 text-[10px] text-[#7f8b88]">
                {workspace.devices.length} on canvas
              </div>
            </div>
            <button
              className="icon-tool"
              title="Hide devices sidebar"
              aria-label="Hide devices sidebar"
              onClick={() => setDevicesPanelOpen(false)}
            >
              ‹
            </button>
          </div>
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search devices..."
            aria-label="Device drawer search"
            className="mt-3 h-8 rounded border border-white/[.1] bg-[#0d1113] px-2 text-[10px] outline-none focus:border-[#9b8afb]"
          />
          <div className="mt-3 grid grid-cols-3 rounded border border-white/[.08] bg-[#0d1113] p-1">
            {([
              ["canvas", "ON CANVAS"],
              ["available", "AVAILABLE"],
              ["manual", "MANUAL"],
            ] as const).map(([tab, label]) => (
              <button
                key={tab}
                className={`rounded px-1 py-1.5 font-mono text-[8px] ${
                  devicePanelTab === tab
                    ? "bg-[#29332f] text-[#61c98d]"
                    : "text-[#7f8b88]"
                }`}
                onClick={() => setDevicePanelTab(tab)}
              >
                {label}
              </button>
            ))}
          </div>
          <div
            className="mt-2 flex flex-wrap gap-1"
            aria-label="Device type filters"
          >
            {([
              "ALL",
              "SWITCH",
              "CORE_SWITCH",
              "ROUTER",
              "FIREWALL",
              "CAMERA",
              "NVR",
              "ACCESS_POINT",
              "SERVER",
              "GENERIC_DEVICE",
            ] as const).map((kind) => (
              <button
                key={kind}
                className={`rounded border px-1.5 py-1 font-mono text-[7px] uppercase ${
                  kindFilter === kind
                    ? "border-[#61c98d88] bg-[#17221e] text-[#61c98d]"
                    : "border-white/[.08] text-[#7f8b88]"
                }`}
                onClick={() => setKindFilter(kind)}
              >
                {kind === "ALL" ? "ALL" : kind.replaceAll("_", " ")}
              </button>
            ))}
          </div>
          <div className="mt-3 min-h-0 flex-1 space-y-3 overflow-y-auto overscroll-contain pr-1 [scrollbar-gutter:stable]">
            {devicePanelTab === "canvas" &&
              visibleDevices.map((device) => (
                <div
                  key={device.id}
                  className={`rounded-lg border p-2 ${
                    selectedId === device.id
                      ? "border-[#61c98d88] bg-[#17221e]"
                      : "border-white/[.08] bg-[#0d1113]"
                  }`}
                >
                  <div className="flex items-start gap-2">
                    <svg
                      width="28"
                      height="28"
                      viewBox="0 0 48 48"
                      fill="none"
                      stroke={renderedToneFor(device)}
                      strokeWidth="2"
                      aria-hidden="true"
                    >
                      {glyph(
                        device.type,
                        device.name,
                        device.vendor,
                        device.model,
                      )}
                    </svg>
                    <span
                      className="mt-1 h-2.5 w-2.5 rounded-full"
                      style={{
                        background: healthColorFor(device),
                      }}
                    />
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-[11px] font-medium">
                        {device.name}
                      </div>
                      <div className="truncate font-mono text-[9px] text-[#7f8b88]">
                        {device.ipAddress || device.subtitle || "No IP"}
                      </div>
                    </div>
                  </div>
                  <div className="mt-2 flex items-center justify-between font-mono text-[8px] text-[#8b9693]">
                    <span>{healthLabel(healthStatusFor(device))}</span>
                    <span>{device.ports?.length || 0} ports</span>
                  </div>
                  <div className="mt-2 flex flex-wrap gap-1">
                    <button
                      className="tool h-7 flex-1 px-2 text-[8px]"
                      onClick={() => focusDevice(device)}
                    >
                      FOCUS
                    </button>
                    <button
                      className="tool h-7 flex-1 px-2 text-[8px]"
                      onClick={() => {
                        setSelectedId(device.id)
                        setInspectorTab("overview")
                      }}
                    >
                      VIEW
                    </button>
                    <button
                      className="tool h-7 flex-1 px-2 text-[8px]"
                      onClick={() => beginConnect(device.id)}
                    >
                      CONNECT
                    </button>
                    <button
                      className="tool h-7 px-2 text-[8px]"
                      onClick={() => editDevice(device)}
                    >
                      EDIT
                    </button>
                    <button
                      className="port-map-action tool h-7 min-w-full px-2 text-[8px] font-semibold"
                      onClick={() =>
                        navigate(`/manual-topology/device/${device.id}/ports`)
                      }
                    >
                      PORT MAP
                    </button>
                  </div>
                </div>
              ))}
            {devicePanelTab === "available" &&
              (availableDevices.length ? (
                availableDevices.map((item) => (
                  <div
                    key={item.id}
                    className="rounded-lg border border-white/[.08] bg-[#0d1113] p-2"
                  >
                    <div className="text-[11px]">
                      {item.hostname || item.name}
                    </div>
                    <div className="font-mono text-[9px] text-[#7f8b88]">
                      {item.ip_address} · {item.device_type || "device"}
                    </div>
                    <div className="mt-2 flex items-center justify-between">
                      <span className="text-[9px] text-[#61c98d]">
                        {item.status || "UNKNOWN"}
                      </span>
                      <button
                        className="tool h-7 px-2 text-[8px]"
                        onClick={() => importDevice(item)}
                      >
                        ADD TO TOPOLOGY
                      </button>
                    </div>
                  </div>
                ))
              ) : (
                <div className="py-8 text-center text-[10px] text-[#7f8b88]">
                  No available devices
                </div>
              ))}
            {devicePanelTab === "manual" && (
              <div className="space-y-3">
                <button
                  className="w-full rounded-lg border border-[#61c98d55] bg-[#17221e] p-3 text-left text-[10px] text-[#61c98d]"
                  onClick={() => addDevice()}
                >
                  + ADD MANUAL DEVICE
                  <div className="mt-1 text-[9px] text-[#8b9693]">
                    Name, type, IP, MAC, location
                  </div>
                </button>
                <div className="text-[9px] leading-5 text-[#7f8b88]">
                  Manual-only devices stay in this workspace and are never
                  deleted from the monitored inventory.
                </div>
              </div>
            )}
          </div>
        </aside>
        )}
        <div
          className={`relative flex h-full min-h-0 flex-col overflow-hidden rounded-xl border border-white/[.1] bg-[#0d1113] ${
            canvasFullscreen
              ? "fixed inset-0 z-[70] min-h-0 rounded-none border-0"
              : ""
          }`}
        >
          <div className="flex shrink-0 flex-wrap items-center gap-3 border-b border-white/[.1] bg-[#11161a] px-3 py-2">
            {!devicesPanelOpen && (
              <button
                className="tool shrink-0"
                aria-label="Show symbols and devices sidebar"
                title="Show symbols and devices sidebar"
                onClick={() => setDevicesPanelOpen(true)}
              >
                › UNHIDE
              </button>
            )}
          {selectedLink && view !== "actual" && (
            <div className="flex min-w-0 flex-wrap items-center gap-2 text-[10px]">
              <span>
                {selectedLink.fromPort || "source"} ↔{" "}
                {selectedLink.toPort || "target"}
              </span>
              {statusBadge(selectedLink.status)}
              <button className="tool h-7" onClick={addBend}>
                + BEND
              </button>
              <button className="tool h-7" onClick={resetRoute}>
                RESET ROUTE
              </button>
              <button className="tool h-7" onClick={removeSelected}>
                DELETE
              </button>
            </div>
          )}
          <div className="ml-auto flex flex-wrap items-center gap-2">
            <div className="rounded-lg border border-white/[.1] bg-[#11161a] p-1">
              <select
                aria-label="Link status filter"
                value={linkStatusFilter}
                onChange={(event) => setLinkStatusFilter(event.target.value)}
                className="bg-transparent px-2 py-1 font-mono text-[9px] text-[#9aa3a0] outline-none"
              >
                <option value="all">All links</option>
                <option value="verified">Verified</option>
                <option value="verifying">Verifying</option>
                <option value="port_mismatch">Mismatch</option>
                <option value="unknown">Unknown</option>
              </select>
            </div>
            <label className="flex items-center gap-1 rounded-lg border border-white/[.1] bg-[#11161a] px-2 py-1 font-mono text-[9px] text-[#9aa3a0]">
              POLL
              <select
                aria-label="Physical connectivity polling interval"
                value={topologyPollMinutes}
                onChange={(event) => setTopologyPollMinutes(Number(event.target.value))}
                className="bg-transparent text-[#61c98d] outline-none"
              >
                {Array.from({ length: 10 }, (_, index) => index + 1).map((minutes) => (
                  <option key={minutes} value={minutes}>{minutes} MIN</option>
                ))}
              </select>
            </label>
            <button
              className="tool"
              title={pageFullscreen ? "Exit fullscreen" : "View topology fullscreen"}
              onClick={() => void togglePageFullscreen()}
            >
              {pageFullscreen ? "EXIT FULL" : "FULLSCREEN"}
            </button>
            <button
              className="tool"
              onClick={() => setSidebarOpen((value) => !value)}
            >
              {sidebarOpen ? "HIDE SIDEBAR ›" : "‹ SHOW SIDEBAR"}
            </button>
          </div>
          </div>
          <div className="relative min-h-0 flex-1">
          <div className="absolute left-3 top-3 z-20 flex flex-col gap-1 rounded-lg border border-white/[.1] bg-[#11161a]/95 p-1">
            <button
              className={`icon-tool ${connectMode ? "active" : ""}`}
              title="Connect devices"
              aria-label="Connect devices"
              onClick={() => (connectMode ? resetConnection() : beginConnect())}
            >
              ⌘
            </button>
          </div>
          <div className="absolute right-3 top-3 z-20 w-64 max-w-[calc(100%-24px)] rounded-xl border border-white/[.12] bg-[#11161a]/95 p-3 shadow-lg">
            <div className="flex items-center justify-between gap-2">
              <span className="font-mono text-[9px] tracking-widest text-[#8b9693]">ZOOM</span>
              <div className="flex items-center gap-1">
                <button className="tool !h-8 !w-8 !p-0 !text-base disabled:opacity-30" aria-label="Zoom out" disabled={zoom <= 0.25} onClick={() => changeCanvasZoom(zoom - 0.1)}>−</button>
                <button className="tool !h-8 !w-16 !p-0 tabular-nums" title="Reset to 100%" aria-label={`Zoom ${Math.round(zoom * 100)} percent. Reset to 100 percent`} onClick={() => changeCanvasZoom(1)}>{Math.round(zoom * 100)}%</button>
                <button className="tool !h-8 !w-8 !p-0 !text-base disabled:opacity-30" aria-label="Zoom in" disabled={zoom >= 3} onClick={() => changeCanvasZoom(zoom + 0.1)}>+</button>
              </div>
              <button className="tool !h-8 !px-2" title="Fit visible topology" onClick={fitToView}>FIT</button>
            </div>
            <input type="range" min="25" max="300" step="1" value={Math.round(zoom * 100)}
              aria-label="Topology zoom" aria-valuetext={`${Math.round(zoom * 100)} percent`}
              onChange={event => changeCanvasZoom(Number(event.target.value) / 100)}
              className="mt-3 block h-1.5 w-full cursor-pointer accent-[#61c98d]" />
            <div className="mt-2 flex justify-between font-mono text-[8px] text-[#7f8b88]"><span>25%</span><span>Ctrl + scroll</span><span>300%</span></div>
          </div>
          {connectMode && (
            <div className="topology-connect-banner absolute left-14 right-3 top-3 z-20 flex flex-wrap items-center gap-2 rounded-lg border border-[#9b8afb55] bg-[#181622]/95 px-3 py-2 text-[10px]">
              <b className="text-[#c7b9ff]">CONNECT DEVICES</b>
              <span className="text-[#a9aaa9]">
                {!source
                  ? "1 Select source device and port"
                  : !targetDeviceId
                    ? `2 Source: ${source.port} · select target device`
                    : !targetPort
                      ? "3 Select target port"
                      : "4 Review and verify"}
              </span>
              {targetPort && (
                <button
                  className="tool border-[#61c98d66] text-[#61c98d]"
                  onClick={createVerifiedConnection}
                >
                  CREATE & VERIFY
                </button>
              )}
              <button className="tool" onClick={resetConnection}>
                CANCEL
              </button>
            </div>
          )}
          <svg
            ref={svgRef}
            viewBox={`0 0 ${CANVAS.width} ${CANVAS.height}`}
            className={`h-full w-full ${pageFullscreen || canvasFullscreen ? "min-h-0" : "min-h-[720px]"}`}
            onDragOver={(event) => event.preventDefault()}
            onDrop={(event) => {
              event.preventDefault()
              const type = event.dataTransfer.getData("application/x-nms-symbol")
              if (!type) return
              const position = point(event as unknown as ReactPointerEvent<SVGSVGElement>)
              if (position) addDevice(type, position)
            }}
            style={{
              backgroundImage: "radial-gradient(#26302d 1px, transparent 1px)",
              backgroundSize: "24px 24px",
            }}
            onWheel={(event) => {
              if (!event.ctrlKey && !event.metaKey) return
              event.preventDefault()
              const nextZoom = clampZoom(
                zoom * (event.deltaY < 0 ? 1.15 : 0.87),
              )
              zoomAtClientPoint(event, nextZoom)
            }}
            onPointerDown={(event) => {
              const p = point(event)
              if (
                p &&
                (event.button === 1 || event.target === event.currentTarget)
              )
                setCanvasDrag({
                  x: pan.x,
                  y: pan.y,
                  px: event.clientX,
                  py: event.clientY,
                })
            }}
            onPointerMove={(event) => {
              const p = point(event)
              if (p) setPointer(p)
              if (canvasDrag)
                setPan(() => {
                  const rect = svgRef.current?.getBoundingClientRect()
                  const scaleX = rect ? CANVAS.width / rect.width : 1
                  const scaleY = rect ? CANVAS.height / rect.height : 1
                  return {
                    x: canvasDrag.x + (event.clientX - canvasDrag.px) * scaleX,
                    y: canvasDrag.y + (event.clientY - canvasDrag.py) * scaleY,
                  }
                })
              if (routingDrag) {
                const p = point(event)
                const link = workspace.links.find(
                  (item) => item.id === routingDrag.linkId,
                )
                if (p && link)
                  updateWorkspace({
                    ...workspace,
                    links: workspace.links.map((item) =>
                      item.id === link.id
                        ? {
                            ...item,
                            routingPoints: (item.routingPoints ?? []).map(
                              (q, index) =>
                                index === routingDrag.index ? p : q,
                            ),
                          }
                        : item,
                    ),
                  })
              }
            }}
          >
            <g transform={`translate(${pan.x} ${pan.y}) scale(${zoom})`}>
              {previewPath && (
                <>
                  <path
                    d={previewPath}
                    fill="none"
                    stroke="#9b8afb"
                    strokeWidth="2"
                    strokeDasharray="7 5"
                    opacity=".95"
                    pointerEvents="none"
                  />
                  {previewSocket && (
                    <circle
                      cx={previewSocket.x}
                      cy={previewSocket.y}
                      r="5"
                      fill="#181622"
                      stroke="#9b8afb"
                      strokeWidth="2"
                    />
                  )}
                  {zoom >= 0.7 && (
                    <text
                      x={(previewSocket?.x || 0) + 8}
                      y={(previewSocket?.y || 0) - 8}
                      fill="#c7b9ff"
                      fontSize="8"
                      fontFamily="monospace"
                    >
                      {source?.port || "PORT UNKNOWN"}
                    </text>
                  )}
                </>
              )}
              {unexpectedLinks.map((link) => {
                const path = actualPath(link)
                return path ? (
                  <path
                    key={`unexpected-${link.id}`}
                    d={path}
                    fill="none"
                    stroke="#d9646a"
                    strokeWidth="2"
                    strokeDasharray="7 5"
                  />
                ) : null
              })}
              {canvasLinks.map((link) => {
                const path = linkPath(link)
                const endpoints = linkEndpoints(link)
                if (!path || !endpoints) return null
                const tone = linkTone(link.status)
                const wrongConnection = link.status === "PORT_MISMATCH"
                const warningPoint = link.routingPoints?.length
                  ? link.routingPoints[Math.floor(link.routingPoints.length / 2)]
                  : { x: (endpoints.source.exit.x + endpoints.target.exit.x) / 2, y: (endpoints.source.exit.y + endpoints.target.exit.y) / 2 }
                const socketLabel = (port?: string, source?: string) =>
                  `${port || "PORT 1"}${
                    source === "manual_fallback" ? " (MANUAL)" : ""
                  }`
                return (
                  <g
                    key={link.id}
                    onMouseEnter={() => setHoveredLinkId(link.id)}
                    onMouseLeave={() => setHoveredLinkId(null)}
                    onClick={() => {
                      setSelectedLinkId(link.id)
                      setSelectedId(null)
                    }}
                  >
                    <title>{`${endpoints.sourceDevice.name} / ${socketLabel(link.fromPort, link.fromPortSource)} -> ${endpoints.targetDevice.name} / ${socketLabel(link.toPort, link.toPortSource)} / ${link.status || "UNKNOWN"} / ${String((link as Link & { evidence_source?: string }).evidence_source || "evidence unavailable")}`}</title>
                    <path
                      d={path}
                      fill="none"
                      stroke="transparent"
                      strokeWidth="18"
                    />
                    <path
                      d={path}
                      fill="none"
                      stroke={tone}
                      className={wrongConnection ? "wrong-connection-line" : undefined}
                      strokeWidth={wrongConnection || selectedLinkId === link.id ? "3" : "1.7"}
                      strokeDasharray={
                        link.status === "VERIFYING" ||
                        link.status === "UNKNOWN" ||
                        link.status === "UNEXPECTED" ||
                        link.status === "DISCONNECTED" ||
                        link.status === "PARTIAL_DISCOVERY"
                          ? "7 5"
                          : undefined
                      }
                    />
                    {wrongConnection && (
                      <g transform={`translate(${warningPoint.x},${warningPoint.y})`} className="cursor-help" role="img"
                        aria-label="Incorrect connection. The selected ports do not match the actual physical connection.">
                        <title>Incorrect connection. The selected ports do not match the actual physical connection. Open Difference and choose Change to Actual Connection to correct it.</title>
                        <path d="M 0 -13 L 14 11 L -14 11 Z" fill="#351016" stroke="#ff4d5e" strokeWidth="2" />
                        <text y="7" textAnchor="middle" fill="#fff" fontSize="17" fontWeight="bold">!</text>
                      </g>
                    )}
                    {[
                      { point: endpoints.source, device: endpoints.sourceDevice, port: link.fromPort, origin: link.fromPortSource },
                      { point: endpoints.target, device: endpoints.targetDevice, port: link.toPort, origin: link.toPortSource },
                    ].map((endpoint, index) => (
                      <g key={index} className="cursor-pointer">
                        <title>{`${endpoint.device.name}: ${socketLabel(endpoint.port, endpoint.origin)}`}</title>
                        <path
                          d={endpoint.point.leader}
                          fill="none" stroke={tone} strokeWidth="1.5" opacity=".9"
                        />
                        <rect className="topology-port-label" x={endpoint.point.x - 25} y={endpoint.point.y - 9} width="50" height="18" rx="4"
                          fill="#11161a" stroke={tone}
                          strokeWidth={selectedLinkId === link.id || hoveredLinkId === link.id ? 2 : 1}
                        />
                        <text className="topology-port-label-text" x={endpoint.point.x} y={endpoint.point.y + 3} textAnchor="middle"
                          fill="#e7eceb" fontSize="9" fontFamily="monospace"
                          textLength={compactPortLabel(endpoint.port).length > 7 ? 44 : undefined}
                          lengthAdjust="spacingAndGlyphs"
                        >{compactPortLabel(endpoint.port)}</text>
                      </g>
                    ))}
                  </g>
                )
              })}
              {canvasDevices.map((device) => (
                <g
                  key={device.id}
                  transform={`translate(${device.x - 70},${device.y - 46})`}
                  onPointerDown={(event) => {
                    event.stopPropagation()
                    event.currentTarget.setPointerCapture?.(event.pointerId)
                    if (event.button === 1) {
                      setCanvasDrag({
                        x: pan.x,
                        y: pan.y,
                        px: event.clientX,
                        py: event.clientY,
                      })
                      return
                    }
                    if (view === "actual") return
                    dragMoved.current = false
                    dragDeviceId.current = device.id
                    dragStartWorkspace.current = workspace
                    const p = point(
                      event as unknown as ReactPointerEvent<SVGSVGElement>,
                    )
                    if (p)
                      setDrag({
                        id: device.id,
                        ox: device.x - p.x,
                        oy: device.y - p.y,
                      })
                    setSelectedId(device.id)
                    setSelectedLinkId(null)
                  }}
                  onPointerMove={(event) => moveDevice(event, device.id)}
                  onMouseEnter={() => setHoveredDeviceId(device.id)}
                  onMouseLeave={() => setHoveredDeviceId(null)}
                  onClick={() => {
                    if (dragMoved.current) return
                    if (connectMode && source) chooseTarget(device.id)
                    else {
                      setSelectedId(device.id)
                      setInspectorTab("overview")
                    }
                  }}
                  onDoubleClick={() => openDevicePorts(device)}
                  className="cursor-grab active:cursor-grabbing"
                >
                  <rect
                    x="0"
                    y="0"
                    width="140"
                    height="92"
                    rx="6"
                    fill="transparent"
                    stroke={
                      selectedId === device.id
                        ? `${renderedToneFor(device)}ee`
                        : `${renderedToneFor(device)}66`
                    }
                    strokeWidth="2"
                    strokeDasharray={selectedId === device.id ? "4 4" : undefined}
                  />
                  <g>{deviceIllustration(device.type, renderedToneFor(device))}</g>
                  <circle
                    cx="111"
                    cy="13"
                    r="3"
                    fill={healthColorFor(device)}
                  />
                  {zoom < 0.5 && (
                    <text
                      x="70"
                      y="78"
                      textAnchor="middle"
                      fill="#e7eceb"
                      fontSize="8"
                      fontWeight="600"
                    >
                      {device.name.slice(0, 11)}
                    </text>
                  )}
                  {zoom >= 0.5 && (
                    <>
                      <text
                        x="70"
                        y="78"
                        textAnchor="middle"
                        fill="#e7eceb"
                        fontSize="10"
                        fontWeight="600"
                      >
                        {device.name.slice(0, 15)}
                      </text>
                      <text
                        x="70"
                        y="90"
                        fill="#8b9693"
                        fontSize="8"
                        fontFamily="monospace"
                      >
                        {(device.ipAddress || device.subtitle || "NO IP").slice(
                          0,
                          17,
                        )}
                      </text>
                    </>
                  )}
                  {connectMode && (
                    <circle
                      cx="128"
                      cy="80"
                      r="7"
                      fill="#181622"
                      stroke={
                        source?.deviceId === device.id ? "#c7b9ff" : "#9b8afb"
                      }
                      strokeWidth="1.5"
                      onClick={(event) => {
                        event.stopPropagation()
                        setSelectedId(device.id)
                        setInspectorTab("ports")
                      }}
                    />
                  )}
                  {hoveredDeviceId === device.id && zoom >= 0.5 && (
                    <foreignObject
                      x={tooltipPlacement(device).x}
                      y={tooltipPlacement(device).y}
                      width="300"
                      height="230"
                      pointerEvents="none"
                    >
                      <div className="rounded-md border border-[#52615d] bg-[#11161a]/[.98] p-2 text-[#e7eceb] shadow-[0_8px_20px_#0009]">
                        <div className="flex items-center justify-between gap-2">
                          <div className="min-w-0 flex-1 truncate text-[11px] font-semibold leading-tight">
                            {device.name}
                          </div>
                          <span className="shrink-0 rounded border border-[#61c98d55] bg-[#61c98d]/10 px-2 py-1 font-mono text-[10px] font-semibold tabular-nums text-[#b3f2cd]">
                            {device.ipAddress || device.subtitle || "No IP"}
                          </span>
                        </div>
                        <div className="mt-1 flex items-center justify-between gap-2">
                          <span className="font-mono text-[7px] uppercase tracking-wider text-[#7f8b88]">
                            {classifyDevice(device.type, device.name, device.vendor, device.model).replaceAll("_", " ")}
                          </span>
                          <span className="shrink-0 rounded border border-[#61c98d55] px-1 py-0.5 font-mono text-[7px] text-[#61c98d]">
                            {healthLabel(healthStatusFor(device))}
                          </span>
                        </div>
                        <div className="mt-1.5 grid grid-cols-2 gap-x-2 gap-y-0.5 border-y border-white/[.08] py-1.5 font-mono text-[7px] leading-tight">
                          <span className="text-[#7f8b88]">TOTAL PORTS</span>
                          <span>
                            {hoverDeviceStats(device).totalPorts || "--"}
                          </span>
                          <span className="text-[#7f8b88]">UP PORTS</span>
                          <span className="text-[#61c98d]">
                            {hoverDeviceStats(device).upPorts ?? "--"}
                          </span>
                          <span className="text-[#7f8b88]">CONNECTED</span>
                          <span>{hoverDeviceStats(device).connectedPorts}</span>
                        </div>
                        <div className="mb-1.5 border-b border-white/[.08] pb-1.5 font-mono text-[7px] leading-tight">
                          <span className="text-[#7f8b88]">LINK EVIDENCE</span>
                          <span className="ml-2 text-[#dce5e2]">{hoverDeviceStats(device).evidenceState}</span>
                        </div>
                        {hoverDeviceStats(device).connections.length > 0 && (
                          <div className="mt-1.5 border-b border-white/[.08] pb-1.5 font-mono text-[7px] leading-tight">
                            <div className="mb-1 uppercase tracking-wider text-[#7f8b88]">PORT CONNECTIONS</div>
                            {hoverDeviceStats(device).connections.slice(0, 4).map((connection, index) => (
                              <div key={`${connection.peerName}-${index}`} className="flex items-center justify-between gap-2">
                                <span className="truncate text-[#dce5e2]">{connection.localPort || "Port unavailable"}</span>
                                <span className="truncate text-right text-[#61c98d]">
                                  → {connection.peerName || "Device unavailable"} · {connection.peerPort || "Port unavailable"}
                                </span>
                              </div>
                            ))}
                            {hoverDeviceStats(device).connections.length > 4 && <div className="mt-0.5 text-[#7f8b88]">+{hoverDeviceStats(device).connections.length - 4} more</div>}
                          </div>
                        )}
                        <div className="mt-1.5 grid grid-cols-2 gap-x-2 gap-y-1 font-mono text-[7px] leading-tight">
                          <span>
                            <b className="font-normal text-[#7f8b88]">MAC</b>
                            <br />
                            <span className="block truncate">{device.macAddress || "N/A"}</span>
                          </span>
                          <span>
                            <b className="font-normal text-[#7f8b88]">VENDOR</b>
                            <br />
                            <span className="block truncate">{device.vendor || "N/A"}</span>
                          </span>
                          <span>
                            <b className="font-normal text-[#7f8b88]">MODEL</b>
                            <br />
                            <span className="block truncate">{device.model || "N/A"}</span>
                          </span>
                          <span>
                            <b className="font-normal text-[#7f8b88]">
                              LOCATION
                            </b>
                            <br />
                            <span className="block truncate">{device.location || "N/A"}</span>
                          </span>
                        </div>
                      </div>
                    </foreignObject>
                  )}
                </g>
              ))}
            </g>
          </svg>
          <div className="absolute bottom-3 right-3 h-24 w-40 rounded-lg border border-white/[.12] bg-[#11161a] p-1">
            <MiniMap
              workspace={{ devices: canvasDevices, links: canvasLinks }}
              viewport={viewport}
              onSelect={(point) =>
                setPan({
                  x: CANVAS.width / 2 - point.x * zoom,
                  y: CANVAS.height / 2 - point.y * zoom,
                })
              }
            />
          </div>
          </div>
        </div>
      {sidebarOpen && (
        <aside className="h-full min-h-0 overflow-y-auto overscroll-contain rounded-xl border border-white/[.1] bg-[#11161a] p-3">
          <div className="mb-2 flex justify-end">
            <button className="tool" aria-label="Hide inspector sidebar" onClick={() => setSidebarOpen(false)}>HIDE ›</button>
          </div>
          {connectMode ? (
            <div className="flex h-[calc(100%-42px)] min-h-0 flex-col">
              <div className="flex items-center justify-between">
                <div>
                  <div className="font-mono text-[10px] uppercase tracking-[.18em] text-[#c7b9ff]">
                    Connect Devices
                  </div>
                  <div className="mt-1 text-[10px] text-[#7f8b88]">
                    Pinned connection workflow
                  </div>
                </div>
                <button
                  className="icon-tool"
                  title="Cancel connection"
                  onClick={resetConnection}
                >
                  ×
                </button>
              </div>
              <div className="mt-4 shrink-0 space-y-2 text-[10px]">
                <div
                  className={`rounded-lg border p-3 ${
                    source
                      ? "border-[#9b8afb66] bg-[#181622]"
                      : "border-white/[.1] bg-[#0d1113]"
                  }`}
                >
                  <div className="font-mono text-[8px] uppercase text-[#8b9693]">
                    1 SOURCE / 2 SOURCE PORT
                  </div>
                  <div className="mt-2 font-medium">
                    {source
                      ? workspace.devices.find(
                          (device) => device.id === source.deviceId,
                        )?.name
                      : "Select a device port"}
                  </div>
                  {source && (
                    <div className="mt-1 font-mono text-[#c7b9ff]">
                      {source.port}
                    </div>
                  )}
                </div>
                <div
                  className={`rounded-lg border p-3 ${
                    targetDeviceId
                      ? "border-[#61c98d66] bg-[#17221e]"
                      : "border-white/[.1] bg-[#0d1113]"
                  }`}
                >
                  <div className="font-mono text-[8px] uppercase text-[#8b9693]">
                    3 TARGET / 4 TARGET PORT
                  </div>
                  <div className="mt-2 font-medium">
                    {targetDeviceId
                      ? workspace.devices.find(
                          (device) => device.id === targetDeviceId,
                        )?.name
                      : "Select another device"}
                  </div>
                  {targetPort && (
                    <div className="mt-1 font-mono text-[#61c98d]">
                      {targetPort}
                    </div>
                  )}
                </div>
              </div>
              <div className="mt-4 flex min-h-0 flex-1 flex-col border-t border-white/[.08] pt-3">
                <div className="mb-2 flex items-center justify-between">
                  <span className="font-mono text-[9px] uppercase text-[#8b9693]">
                    {targetDeviceId
                      ? "TARGET PORTS"
                      : source
                        ? "TARGET DEVICE"
                        : "SOURCE PORTS"}
                  </span>
                  <span className="text-[9px] text-[#7f8b88]">
                    {portPanelPorts.length} shown
                  </span>
                </div>
                {source && !targetDeviceId && (
                  <div className="min-h-0 flex-1 space-y-1 overflow-y-auto overscroll-contain pr-1 [scrollbar-gutter:stable]">
                    {workspace.devices
                      .filter((device) => device.id !== source.deviceId)
                      .map((device) => (
                        <button
                          key={device.id}
                          className="flex w-full items-center justify-between rounded border border-white/[.08] bg-[#0d1113] p-2 text-left hover:border-[#9b8afb88]"
                          onClick={() => chooseTarget(device.id)}
                        >
                          <span>
                            {device.name}
                            <small className="block font-mono text-[8px] text-[#7f8b88]">
                              {device.ipAddress || "No IP"}
                            </small>
                          </span>
                          <span className="text-[#9b8afb]">→</span>
                        </button>
                      ))}
                  </div>
                )}
                {(!source || targetDeviceId) && (
                  <div className="min-h-0 flex-1 space-y-1 overflow-y-auto overscroll-contain pr-1 [scrollbar-gutter:stable]">
                    {portPanelPorts.map((port) => {
                      const occupancy = portOccupancy.get(port.name)
                      const logical = isLogicalPort(port)
                      return (
                        <div
                          key={`${port.id}-${port.name}`}
                          className="rounded-lg border border-white/[.08] bg-[#0d1113] p-2"
                        >
                          <div className="flex items-center justify-between">
                            <span className="truncate text-[10px]">
                              {port.name}
                            </span>
                            <span style={{ color: portStatusTone(port) }}>
                              ● {port.operStatus.toUpperCase()}
                            </span>
                          </div>
                          <div className="mt-1 font-mono text-[8px] text-[#7f8b88]">
                            ifIndex {port.ifIndex ?? "N/A"} ·{" "}
                            {port.speed_display || "N/A"} ·{" "}
                            {port.source === "manual_fallback"
                              ? "MANUAL · physical port not discovered"
                              : port.source.toUpperCase()}
                          </div>
                          <div
                            className={`mt-1 text-[8px] ${
                              occupancy?.occupied
                                ? "text-[#d9646a]"
                                : logical
                                  ? "text-[#c7b9ff]"
                                  : "text-[#61c98d]"
                            }`}
                          >
                            {occupancy?.occupied
                              ? `USED · ${occupancy.peerPortName || "peer connected"}`
                              : logical
                                ? "LOGICAL · NOT A PHYSICAL ENDPOINT"
                                : "AVAILABLE PHYSICAL ENDPOINT"}
                          </div>
                          <button
                            className="tool mt-2 h-7 w-full"
                            disabled={Boolean(occupancy?.occupied || logical)}
                            onClick={() =>
                              portPanelDevice &&
                              handlePortSelect(portPanelDevice, port.name)
                            }
                          >
                            {occupancy?.occupied
                              ? "PORT IN USE"
                              : logical
                                ? "LOGICAL"
                                : "USE PORT"}
                          </button>
                        </div>
                      )
                    })}
                  </div>
                )}
                {targetPort && (
                  <div className="mt-3 shrink-0 rounded-lg border border-[#61c98d55] bg-[#17221e] p-3">
                    <div className="font-mono text-[9px] uppercase text-[#8b9693]">
                      5 CONNECTION REVIEW
                    </div>
                    <div className="mt-2">
                      {source?.port} <span className="text-[#7f8b88]">→</span>{" "}
                      {targetPort}
                    </div>
                    <button
                      className="tool mt-3 w-full border-[#61c98d66] text-[#61c98d]"
                      onClick={createVerifiedConnection}
                    >
                      CREATE & VERIFY
                    </button>
                  </div>
                )}
                {connectionError && (
                  <div className="mt-2 text-[9px] text-[#d9646a]">
                    {connectionError}
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div>
              <div className="flex items-center justify-between">
                <div>
                  <div className="font-mono text-[10px] uppercase tracking-[.18em] text-[#dce5e2]">
                    Inspector
                  </div>
                  <div className="mt-1 text-[10px] text-[#7f8b88]">
                    {selected?.name || "Select a device or link"}
                  </div>
                </div>
                <button
                  className="icon-tool"
                  title="Start connection"
                  onClick={() => beginConnect(selected?.id)}
                >
                  ⌘
                </button>
              </div>
              <div className="mt-3 grid grid-cols-3 rounded border border-white/[.08] bg-[#0d1113] p-1">
                {([
                  ["overview", "OVERVIEW"],
                  ["ports", "PORTS"],
                  ["monitoring", "MONITORING"],
                ] as const).map(([tab, label]) => (
                  <button
                    key={tab}
                    className={`rounded px-1 py-1.5 font-mono text-[8px] ${
                      inspectorTab === tab
                        ? "bg-[#29332f] text-[#61c98d]"
                        : "text-[#7f8b88]"
                    }`}
                    onClick={() => setInspectorTab(tab)}
                  >
                    {label}
                  </button>
                ))}
              </div>
              {selectedLink && inspectorTab === "overview" && (
                <div className="mt-4 space-y-3 text-[10px]">
                  <div className="font-mono text-[10px] uppercase tracking-[.16em] text-[#dce5e2]">
                    CONNECTION
                  </div>
                  {[
                    ["FROM", selectedLink.from],
                    [
                      "SOURCE PORT",
                      `${selectedLink.fromPort || "PORT UNKNOWN"} / ifIndex ${selectedLink.fromIfIndex ?? "N/A"}`,
                    ],
                    ["TO", selectedLink.to],
                    [
                      "TARGET PORT",
                      `${selectedLink.toPort || "PORT UNKNOWN"} / ifIndex ${selectedLink.toIfIndex ?? "N/A"}`,
                    ],
                    ["STATUS", selectedLink.status || "UNKNOWN"],
                    [
                      "PHYSICAL EVIDENCE",
                      String(
                        (selectedLink as Link & { evidence_source?: string })
                          .evidence_source || "N/A",
                      ),
                    ],
                  ].map(([label, value]) => (
                    <div
                      key={label}
                      className="flex justify-between gap-3 border-b border-white/[.06] py-2"
                    >
                      <span className="text-[#7f8b88]">{label}</span>
                      <span className="max-w-[190px] truncate text-right">
                        {workspace.devices.find((device) => device.id === value)
                          ?.name || value}
                      </span>
                    </div>
                  ))}
                  <div className="grid grid-cols-2 gap-2 pt-2">
                    <button
                      className="tool"
                      onClick={() =>
                        navigate(
                          `/manual-topology/device/${selectedLink.from}/ports?port=${encodeURIComponent(selectedLink.fromPort || "")}`,
                        )
                      }
                    >
                      VIEW SOURCE PORT
                    </button>
                    <button
                      className="tool"
                      onClick={() =>
                        navigate(
                          `/manual-topology/device/${selectedLink.to}/ports?port=${encodeURIComponent(selectedLink.toPort || "")}`,
                        )
                      }
                    >
                      VIEW TARGET PORT
                    </button>
                    <button
                      className="tool"
                      onClick={() => void openSelectedLinkDifference()}
                      disabled={differenceLoading}
                    >
                      {differenceLoading ? "CHECKING..." : "VIEW DIFFERENCE"}
                    </button>
                    <button
                      className="tool border-[#d9646a66] text-[#d9646a]"
                      onClick={removeSelected}
                    >
                      DELETE MANUAL LINK
                    </button>
                  </div>
                </div>
              )}
              {selected &&
                inspectorTab === "overview" &&
                editingDeviceId === selected.id &&
                editForm && (
                  <div className="mt-4 space-y-3 text-[10px]">
                    <div className="flex items-center justify-between border-b border-white/[.08] pb-2">
                      <div className="font-mono text-[10px] uppercase tracking-[.16em] text-[#dce5e2]">
                        EDIT DEVICE
                      </div>
                      <span className="font-mono text-[8px] text-[#7f8b88]">
                        {selected.backendId ? "BACKEND-LINKED" : "MANUAL-ONLY"}
                      </span>
                    </div>
                    {editErrors.form && (
                      <div className="rounded border border-[#d9646a66] bg-[#d9646a12] p-2 text-[#d9646a]">
                        {editErrors.form}
                      </div>
                    )}
                    <div className="font-mono text-[8px] uppercase tracking-widest text-[#7f8b88]">
                      GENERAL
                    </div>
                    <label className="block">
                      Display Name
                      <input
                        value={editForm.name}
                        onChange={(event) =>
                          setEditForm({ ...editForm, name: event.target.value })
                        }
                        className="mt-1 h-8 w-full rounded border border-white/[.1] bg-[#0d1113] px-2 text-[10px]"
                      />
                      {editErrors.name && (
                        <span className="mt-1 block text-[9px] text-[#d9646a]">
                          {editErrors.name}
                        </span>
                      )}
                    </label>
                    <label className="block">
                      Device Type
                      <input
                        value={editForm.type}
                        onChange={(event) =>
                          setEditForm({ ...editForm, type: event.target.value })
                        }
                        list="manual-device-types"
                        placeholder="Network Device, Switch, Router, AP..."
                        className="mt-1 h-8 w-full rounded border border-white/[.1] bg-[#0d1113] px-2 text-[10px]"
                      />
                      <datalist id="manual-device-types">
                        {[...new Set(editableDeviceTypes)].map((type) => (
                          <option key={type} value={type} />
                        ))}
                      </datalist>
                      <span className="mt-1 block text-[8px] text-[#9aa3a0]">
                        Type a device category to update its icon
                      </span>
                    </label>
                    <label className="block">
                      IP Address
                      <input
                        value={editForm.ip}
                        onChange={(event) =>
                          setEditForm({ ...editForm, ip: event.target.value })
                        }
                        className={`mt-1 h-8 w-full rounded border ${
                          editErrors.ip
                            ? "border-[#d9646a]"
                            : "border-white/[.1]"
                        } ${
                          "bg-[#0d1113]"
                        } px-2 text-[10px]`}
                      />
                      {editErrors.ip && <span className="mt-1 block text-[9px] text-[#d9646a]">{editErrors.ip}</span>}
                    </label>
                    <label className="block">
                      MAC Address
                      <input
                        value={editForm.mac}
                        onChange={(event) =>
                          setEditForm({ ...editForm, mac: event.target.value })
                        }
                        className={`mt-1 h-8 w-full rounded border ${
                          editErrors.mac
                            ? "border-[#d9646a]"
                            : "border-white/[.1]"
                        } ${
                          "bg-[#0d1113]"
                        } px-2 text-[10px]`}
                      />
                      {editErrors.mac && <span className="mt-1 block text-[9px] text-[#d9646a]">{editErrors.mac}</span>}
                    </label>
                    <label className="block">
                      {selected.backendId ? "Topology Location" : "Location"}
                      <input
                        value={editForm.location}
                        onChange={(event) =>
                          setEditForm({
                            ...editForm,
                            location: event.target.value,
                          })
                        }
                        className="mt-1 h-8 w-full rounded border border-white/[.1] bg-[#0d1113] px-2 text-[10px]"
                      />
                    </label>
                    <label className="block">
                      Description
                      <textarea
                        value={editForm.description}
                        onChange={(event) =>
                          setEditForm({
                            ...editForm,
                            description: event.target.value,
                          })
                        }
                        rows={2}
                        className="mt-1 w-full rounded border border-white/[.1] bg-[#0d1113] px-2 py-1 text-[10px]"
                      />
                    </label>
                    <div className="border-t border-white/[.08] pt-3">
                      <div className="font-mono text-[8px] uppercase tracking-widest text-[#7f8b88]">
                        DISCOVERED / SYNCED
                      </div>
                      <div className="mt-2 grid grid-cols-2 gap-2 text-[9px]">
                        {([["Vendor", "vendor"], ["Model", "model"], ["Serial", "serial"], ["Firmware", "firmware"], ["SNMP Version", "snmpVersion"]] as const).map(([label, field]) => (
                          <label key={field} className="rounded border border-white/[.06] bg-[#18201f] p-2">
                            <div className="text-[#7f8b88]">{label}</div>
                            <input value={editForm[field]} onChange={(event) => setEditForm({ ...editForm, [field]: event.target.value })} className="mt-1 h-7 w-full rounded border border-white/[.1] bg-[#0d1113] px-1 text-[9px]" />
                          </label>
                        ))}
                        <div className="rounded border border-white/[.06] bg-[#18201f] p-2"><div className="text-[#7f8b88]">Last Seen</div><div className="mt-1">{selected.lastSeen || "N/A"}</div></div>
                      </div>
                    </div>
                    <div className="flex gap-2 pt-1">
                      <button
                        className="tool flex-1"
                        onClick={cancelEditDevice}
                      >
                        CANCEL
                      </button>
                      <button
                        className="tool flex-1 border-[#61c98d66] text-[#61c98d] disabled:cursor-not-allowed disabled:opacity-40"
                        disabled={
                          editSaving ||
                          !editForm.name.trim() ||
                          (editForm.name === selected.name &&
                            editForm.type === selected.type &&
                            editForm.ip ===
                              (selected.ipAddress || selected.subtitle || "") &&
                            editForm.mac === (selected.macAddress || "") &&
                            editForm.location === (selected.location || "") &&
                            editForm.description ===
                              (selected.description || "") &&
                            editForm.vendor === (selected.vendor || "") &&
                            editForm.model === (selected.model || "") &&
                            editForm.serial === (selected.serialNumber || "") &&
                            editForm.firmware === (selected.firmware || "") &&
                            editForm.snmpVersion === (selected.snmpVersion || ""))
                        }
                        onClick={() => void saveEditedDevice()}
                      >
                        {editSaving ? "SAVING..." : "SAVE CHANGES"}
                      </button>
                    </div>
                  </div>
                )}
              {selected &&
                inspectorTab === "overview" &&
                editingDeviceId !== selected.id && (
                  <div className="mt-4 space-y-2 text-[10px]">
                    {[
                      ["Device", selected.name],
                      ["IP", selected.ipAddress || selected.subtitle || "N/A"],
                      ["MAC", selected.macAddress || "N/A"],
                      ["Type", selected.type],
                      ["Vendor", selected.vendor || "N/A"],
                      ["Model", selected.model || "N/A"],
                      ["Serial", selected.serialNumber || "N/A"],
                      ["Location", selected.location || "N/A"],
                    ].map(([label, value]) => (
                      <div
                        key={label}
                        className="flex justify-between gap-3 border-b border-white/[.06] py-2"
                      >
                        <span className="text-[#7f8b88]">{label}</span>
                        <span className="max-w-[170px] truncate text-right">
                          {value}
                        </span>
                      </div>
                    ))}
                    <div className="flex gap-2 pt-2">
                      <button
                        className="tool flex-1"
                        onClick={() => editDevice(selected)}
                      >
                        EDIT
                      </button>
                      <button
                        className="tool flex-1"
                        onClick={() =>
                          navigate(
                            `/manual-topology/device/${selected.id}/ports`,
                          )
                        }
                      >
                        PORT MAP
                      </button>
                      <button
                        className="tool flex-1 border-[#d9646a55] text-[#d9646a]"
                        onClick={removeSelected}
                      >
                        REMOVE
                      </button>
                    </div>
                  </div>
                )}
              {selected && inspectorTab === "ports" && (
                <div className="mt-4">
                  <input
                    value={portSearch}
                    onChange={(event) => setPortSearch(event.target.value)}
                    placeholder="Search ports..."
                    className="h-8 w-full rounded border border-white/[.1] bg-[#0d1113] px-2 text-[10px] outline-none"
                  />
                  <div className="mt-2 flex gap-1">
                    <button
                      className={`tool h-7 flex-1 ${
                        portView === "physical"
                          ? "border-[#61c98d] text-[#61c98d]"
                          : ""
                      }`}
                      onClick={() => setPortView("physical")}
                    >
                      PHYSICAL PORTS
                    </button>
                    <button
                      className={`tool h-7 flex-1 ${
                        portView === "all"
                          ? "border-[#61c98d] text-[#61c98d]"
                          : ""
                      }`}
                      onClick={() => setPortView("all")}
                    >
                      ALL INTERFACES
                    </button>
                  </div>
                  <div className="mt-2 flex items-center justify-between text-[8px] text-[#7f8b88]">
                    <span>
                      {portPanelAllPorts.length} total ·{" "}
                      {
                        portPanelAllPorts.filter(
                          (port) => port.operStatus.toUpperCase() === "UP",
                        ).length
                      }{" "}
                      up
                    </span>
                    <select
                      value={portStatus}
                      onChange={(event) =>
                        setPortStatus(
                          event.target.value as "all" | "up" | "down",
                        )
                      }
                      className="bg-transparent text-[#9aa3a0]"
                    >
                      <option value="all">ALL</option>
                      <option value="up">UP</option>
                      <option value="down">DOWN</option>
                    </select>
                  </div>
                  <div className="mt-2 grid grid-cols-4 gap-1 text-center font-mono text-[8px]">
                    {[
                      [selectedPortSummary.total, "TOTAL"],
                      [selectedPortSummary.up, "UP"],
                      [selectedPortSummary.used, "USED"],
                      [selectedPortSummary.available, "FREE"],
                    ].map(([value, label]) => (
                      <div
                        key={label}
                        className="rounded border border-white/[.08] bg-[#0d1113] p-1"
                      >
                        <div className="text-[#dce5e2]">{value}</div>
                        <div className="text-[#6f7975]">{label}</div>
                      </div>
                    ))}
                  </div>
                  <div className="mt-2 max-h-[470px] space-y-1 overflow-y-auto">
                    {portPanelPorts.map((port) => {
                      const occupancy = portOccupancy.get(port.name)
                      const logical = isLogicalPort(port)
                      return (
                        <div
                          key={`${port.id}-${port.name}`}
                          className="rounded-lg border border-white/[.08] bg-[#0d1113] p-2"
                        >
                          <div className="flex justify-between gap-2">
                            <span className="truncate text-[10px]">
                              {port.name}
                            </span>
                            <span style={{ color: portStatusTone(port) }}>
                              ● {port.operStatus.toUpperCase()}
                            </span>
                          </div>
                          <div className="mt-1 font-mono text-[8px] text-[#7f8b88]">
                            ifIndex {port.ifIndex ?? "N/A"} ·{" "}
                            {port.speed_display} ·{" "}
                            {port.source === "manual_fallback"
                              ? "MANUAL"
                              : port.source.toUpperCase()}
                          </div>
                          <div
                            className={`mt-1 text-[8px] ${
                              occupancy?.occupied
                                ? "text-[#d9646a]"
                                : logical
                                  ? "text-[#c7b9ff]"
                                  : "text-[#61c98d]"
                            }`}
                          >
                            {occupancy?.occupied
                              ? `USED · ${occupancy.peerPortName || "peer connected"}`
                              : logical
                                ? "LOGICAL · NOT A PHYSICAL ENDPOINT"
                                : "AVAILABLE PHYSICAL ENDPOINT"}
                          </div>
                          <button
                            className="tool mt-2 h-7 w-full"
                            disabled={Boolean(occupancy?.occupied || logical)}
                            onClick={() =>
                              handlePortSelect(selected, port.name)
                            }
                          >
                            {occupancy?.occupied
                              ? "PORT IN USE"
                              : logical
                                ? "LOGICAL"
                                : "USE PORT"}
                          </button>
                        </div>
                      )
                    })}
                  </div>
                </div>
              )}
              {selected && inspectorTab === "monitoring" && (
                <div className="mt-4 space-y-2 text-[10px]">
                  {[
                    ["Status", healthLabel(healthStatusFor(selected))],
                    ["SNMP", selected.snmpVersion || "N/A"],
                    [
                      "Reachability",
                      healthLabel(healthStatusFor(selected)),
                    ],
                    ["Last seen", selected.lastSeen || "N/A"],
                    ["Firmware", selected.firmware || "N/A"],
                    [
                      "Monitoring",
                      selected.monitoringEnabled == null
                        ? "N/A"
                        : selected.monitoringEnabled
                          ? "Enabled"
                          : "Disabled",
                    ],
                  ].map(([label, value]) => (
                    <div
                      key={label}
                      className="flex justify-between gap-3 border-b border-white/[.06] py-2"
                    >
                      <span className="text-[#7f8b88]">{label}</span>
                      <span>{value}</span>
                    </div>
                  ))}
                </div>
              )}
              {!selected && (
                <div className="py-12 text-center text-[10px] text-[#7f8b88]">
                  Select a device to inspect its details.
                </div>
              )}
            </div>
          )}
        </aside>
        )}
      </section>
      <div className="hidden">
        <div className="rounded-xl border border-white/[.1] bg-[#11161a] p-3">
          <div className="font-mono text-[9px] uppercase tracking-[.16em] text-[#8b9693]">
            Connectivity
          </div>
          <div className="mt-2 grid grid-cols-3 gap-2 text-center">
            <div>
              <div className="text-lg text-[#61c98d]">
                {linkCounts.verified}
              </div>
              <div className="text-[8px] text-[#7f8b88]">VERIFIED</div>
            </div>
            <div>
              <div className="text-lg text-[#d4a95c]">{linkCounts.issues}</div>
              <div className="text-[8px] text-[#7f8b88]">ISSUES</div>
            </div>
            <div>
              <div className="text-lg text-[#9aa3a0]">{linkCounts.unknown}</div>
              <div className="text-[8px] text-[#7f8b88]">UNKNOWN</div>
            </div>
          </div>
        </div>
        <div className="rounded-xl border border-white/[.1] bg-[#11161a] p-3">
          <div className="font-mono text-[9px] uppercase tracking-[.16em] text-[#8b9693]">
            Filters
          </div>
          <div className="mt-2 flex flex-wrap gap-2">
            <select
              value={typeFilter}
              onChange={(event) => setTypeFilter(event.target.value)}
              className="tool h-7"
            >
              <option value="all">All types</option>
              {deviceTypes.map((type) => (
                <option key={type}>{type}</option>
              ))}
            </select>
            <select
              value={locationFilter}
              onChange={(event) => setLocationFilter(event.target.value)}
              className="tool h-7"
            >
              <option value="all">All locations</option>
              {locations.map((location) => (
                <option key={location}>{location}</option>
              ))}
            </select>
            <select
              value={healthFilter}
              onChange={(event) => setHealthFilter(event.target.value)}
              className="tool h-7"
            >
              <option value="all">All health</option>
              <option value="online">Online</option>
              <option value="offline">Offline</option>
            </select>
            <button
              className="tool h-7"
              onClick={() => {
                setTypeFilter("all")
                setLocationFilter("all")
                setHealthFilter("all")
                setLinkStatusFilter("all")
              }}
            >
              CLEAR
            </button>
          </div>
        </div>
        <div className="rounded-xl border border-white/[.1] bg-[#11161a] p-3">
          <div className="font-mono text-[9px] uppercase tracking-[.16em] text-[#8b9693]">
            Save status
          </div>
          <div className="mt-2 text-xs">
            {saving
              ? "Saving workspace..."
              : lastSaved
                ? `Saved ${lastSaved}`
                : "Local changes autosave after edits"}
          </div>
          <div className="mt-1 text-[9px] text-[#7f8b88]">
            Actual topology refreshes automatically every 30 seconds.
          </div>
        </div>
      </div>
      {selectedChange && (
        <div
          className="fixed inset-0 z-[60] flex items-center justify-center bg-black/75 p-4"
          onClick={() => setSelectedChange(null)}
        >
          <section
            className="w-full max-w-lg rounded-xl border border-[#d4a95c66] bg-[#11161a] p-5"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-start justify-between">
              <div>
                <h2 className="text-lg font-semibold">Difference</h2>
                <div className="mt-1">
                  {statusBadge(issueStatus(selectedChange))}
                </div>
              </div>
              <button className="tool" onClick={() => setSelectedChange(null)}>
                CLOSE
              </button>
            </div>
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              <div className="rounded border border-white/[.08] bg-[#0d1113] p-3 text-xs">
                <div className="font-mono text-[8px] text-[#7f8b88]">
                  MANUAL CONNECTION
                </div>
                <div className="mt-2">
                      {deviceReference(selectedChange.expected, [
                    "source_device",
                    "from_device",
                    "device",
                  ])}{" "}
                  :{" "}
                  {deviceReference(selectedChange.expected, [
                    "source_port",
                    "from_port",
                    "port",
                  ])}
                  <br />↓<br />
                  {deviceReference(selectedChange.expected, [
                    "target_device",
                    "to_device",
                    "remote_device",
                  ])}{" "}
                  :{" "}
                  {evidenceValue(selectedChange.expected, [
                    "target_port",
                    "to_port",
                    "remote_port",
                  ])}
                </div>
              </div>
              <div className="rounded border border-white/[.08] bg-[#0d1113] p-3 text-xs">
                <div className="font-mono text-[8px] text-[#7f8b88]">
                  ACTUAL PHYSICAL CONNECTION
                </div>
                <div className="mt-2">
                  {issueStatus(selectedChange) === "DISCONNECTED" ? (
                    <>
                      <div className="font-semibold text-[#ff858a]">NO LIVE CONNECTION DETECTED</div>
                      <div className="mt-2 text-[10px] leading-relaxed text-[#9aa3a0]">
                        The physical discovery source did not report this link. This is a disconnected-link alert, not an unknown port.
                      </div>
                    </>
                  ) : (
                    <>
                      {isPartialDiscovery(selectedChange) && (
                        <div className="mb-2 font-semibold text-[#d4a95c]">PARTIAL DISCOVERY · 1 ENDPOINT PORT FOUND</div>
                      )}
                      {deviceReference(selectedChange.observed, ["source_device", "from_device", "device"])} : {observedPortValue(selectedChange, "source")}
                      <br />↓<br />
                      {deviceReference(selectedChange.observed, ["target_device", "to_device", "remote_device"])} : {observedPortValue(selectedChange, "target")}
                    </>
                  )}
                </div>
              </div>
            </div>
            <div className="mt-3 rounded border border-[#d4a95c55] bg-[#241f14] p-3 text-[10px] leading-relaxed text-[#e7d6ad]">
              {issueStatus(selectedChange) === "DISCONNECTED"
                ? "KEEP MANUAL retains the drawn link and keeps this warning. ACCEPT REAL CHANGE removes the manual link because no matching physical connection was detected."
                : isPartialDiscovery(selectedChange)
                  ? "PARTIAL DISCOVERY: one endpoint port was found, but the peer port was not reported. The link remains unverified until both ports are discovered."
                  : "KEEP MANUAL retains the manual connection. ACCEPT REAL CHANGE updates it using the observed physical evidence."}
            </div>
            <div className="mt-3 rounded border border-white/[.08] p-3 font-mono text-[10px] text-[#9aa3a0]">
              Evidence:{" "}
              {evidenceValue(selectedChange.observed, [
                "evidenceSource",
                "evidence_source",
                "source",
              ])}
              <br />
              Confidence:{" "}
              {evidenceValue(selectedChange.observed, ["confidence"])}
              <br />
              Last verified: {selectedChange.detected_at || "N/A"}
              {selectedChange.observed?.reason && (
                <div className="mt-2 text-[#d4a95c]">{String(selectedChange.observed.reason)}</div>
              )}
            </div>
            {selectedChange.id > 0 ? (
              <div className="mt-4 flex justify-end gap-2">
                <button
                  className="tool border-[#61c98d66] text-[#61c98d]"
                  disabled={confirmingConnectivity || !selectedLink}
                  onClick={() => void confirmConnectivity()}
                >
                  {confirmingConnectivity ? "SAVING…" : "CONFIRM CONNECTIVITY"}
                </button>
                <button
                  className="tool"
                  onClick={() =>
                    void resolveChange(selectedChange, "keep_manual")
                  }
                >
                  KEEP MANUAL
                </button>
                <button
                  className="tool border-[#61c98d66] text-[#61c98d]"
                  onClick={() =>
                    void resolveChange(selectedChange, "accept_real_change")
                  }
                >
                  ACCEPT REAL CHANGE
                </button>
                {issueStatus(selectedChange) === "PORT_MISMATCH" && (
                  <button
                    className="tool !border-[#61c98d66] !text-[#61c98d]"
                    disabled={applyingActual}
                    onClick={() => void applyActualConnection()}
                  >
                    {applyingActual ? "Saving…" : "CHANGE TO ACTUAL CONNECTION"}
                  </button>
                )}
              </div>
            ) : (
              <div className="mt-4 text-right font-mono text-[9px] uppercase text-[#7f8b88]">
                <button className="tool" disabled={applyingActual} onClick={() => setSelectedChange(null)}>Keep Manual Connection</button>
                <button className="tool !border-[#61c98d66] !text-[#61c98d]" disabled={confirmingConnectivity || !selectedLink} onClick={() => void confirmConnectivity()}>
                  {confirmingConnectivity ? "Saving…" : "Confirm Connectivity"}
                </button>
                {issueStatus(selectedChange) === "PORT_MISMATCH" && (
                  <button className="tool !border-[#61c98d66] !text-[#61c98d]" disabled={applyingActual} onClick={() => void applyActualConnection()}>
                    {applyingActual ? "Saving…" : "Change to Actual Connection"}
                  </button>
                )}
              </div>
            )}
          </section>
        </div>
      )}
      {removeConfirmDevice && (
        <div
          className="fixed inset-0 z-[80] flex items-center justify-center bg-[#050708]/80 p-4 backdrop-blur-sm"
          role="presentation"
          onClick={() => setRemoveConfirmDevice(null)}
        >
          <section
            role="dialog"
            aria-modal="true"
            aria-labelledby="remove-device-title"
            className="w-full max-w-md rounded-xl border border-[#d9646a88] bg-[#11161a] p-5 shadow-[0_24px_80px_#000c]"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-start gap-3">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full border border-[#d9646a88] bg-[#3a191d] text-lg text-[#ff858a]">
                !
              </div>
              <div className="min-w-0">
                <div className="font-mono text-[9px] uppercase tracking-[.2em] text-[#ff858a]">
                  Remove device
                </div>
                <h2 id="remove-device-title" className="mt-1 truncate text-base font-semibold text-[#e7eceb]">
                  Remove &quot;{removeConfirmDevice.name}&quot;?
                </h2>
              </div>
            </div>
            <p className="mt-4 rounded-lg border border-white/[.08] bg-[#0d1113] p-3 text-[11px] leading-5 text-[#c5cfcc]">
              The device node and its attached manual links will be removed from this topology. The monitored backend/SNMP device will remain safe and will not be deleted.
            </p>
            <div className="mt-5 flex justify-end gap-2">
              <button className="tool" onClick={() => setRemoveConfirmDevice(null)}>
                CANCEL
              </button>
              <button
                className="tool border-[#d9646a99] bg-[#3a191d] text-[#ff858a] hover:border-[#ff858a]"
                onClick={confirmRemoveDevice}
              >
                REMOVE DEVICE
              </button>
            </div>
          </section>
        </div>
      )}
      <footer className="hidden">
        <span>
          Selected:{" "}
          <b className="text-[#e5e7e7]">
            {selected?.name || (selectedLinkId ? "Link" : "None")}
          </b>
        </span>
        <span>Devices: {workspace.devices.length}</span>
        <span>Links: {workspace.links.length}</span>
        <span>
          Last Saved: {saving ? "Saving..." : lastSaved || "Not saved"}
        </span>
        <span className="ml-auto">Shortcuts: / F L</span>
      </footer>
      <style>{`@keyframes wrong-connection-pulse{0%,100%{opacity:1}50%{opacity:.3}}.wrong-connection-line{animation:wrong-connection-pulse 1.4s ease-in-out infinite}@media(prefers-reduced-motion:reduce){.wrong-connection-line{animation:none}}.tool{height:32px;border:1px solid rgba(170,190,180,.14);background:#11161a;color:#e5e7e7;border-radius:6px;padding:0 10px;font:10px ui-monospace,monospace;text-transform:uppercase}.tool:hover{border-color:#9b8afb;color:#fff}.tool:disabled{opacity:.35;cursor:not-allowed}.icon-tool{height:32px;width:32px;border:1px solid transparent;background:transparent;color:#9aa3a0;border-radius:5px;font:16px ui-monospace,monospace}.icon-tool:hover,.icon-tool.active{background:#242033;border-color:#9b8afb;color:#c7b9ff}`}</style>
    </main>
  )
  /*
    <header className="mb-3 flex flex-wrap items-center justify-between gap-3 border-b border-white/[.08] pb-3">
      <div><div className="font-mono text-[9px] uppercase tracking-[.24em] text-[#6f7975]">Network workspace / topology board</div><h1 className="mt-1 text-2xl font-semibold">Topology</h1><div className="font-mono text-[10px] text-[#9aa3a0]">Network topology workspace</div></div>
      <div className="flex flex-wrap items-center justify-end gap-2"><input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search device..." className="h-9 w-64 rounded-md border border-white/[.12] bg-[#111517] px-3 font-mono text-[10px] outline-none" /><button onClick={autoLayout} className="tool">Auto Layout</button><button onClick={() => { setZoom(1); setPan({ x: 0, y: 0 }) }} className="tool">Fit to View</button><button onClick={undo} disabled={!history.length} className="tool disabled:opacity-30">Undo</button><button onClick={redo} disabled={!future.length} className="tool disabled:opacity-30">Redo</button><button onClick={() => setSnap((v) => !v)} className={`tool ${snap ? "border-[#61c98d] text-[#61c98d]" : ""}`}>Snap {snap ? "On" : "Off"}</button><button onClick={exportSvg} className="tool">SVG</button><button onClick={exportPng} className="tool">PNG</button><button onClick={exportPdf} className="tool">PDF</button><button onClick={() => setPaletteOpen((v) => !v)} className="tool">More ...</button></div>
    </header>
    <div className="mb-2 flex items-center gap-2"><button className="tool" onClick={() => setPaletteOpen((v) => !v)}>Devices</button><button className="tool" onClick={() => setFiltersOpen((v) => !v)}>Filters</button>{filtersOpen && <><select className="tool" value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)}><option value="all">All types</option>{deviceTypes.map((t) => <option key={t}>{t}</option>)}</select><select className="tool" value={healthFilter} onChange={(e) => setHealthFilter(e.target.value)}><option value="all">All health</option><option value="online">Online</option><option value="offline">Offline</option></select></>}</div>
    <section className="grid min-h-[680px] grid-cols-1 gap-3 xl:grid-cols-[minmax(0,1fr)_290px]">
      <div className="relative min-h-[680px] overflow-hidden rounded-lg border border-white/[.12] bg-[#0d1113]">
        <div className="absolute left-3 top-3 z-20 flex flex-col gap-1 rounded-md border border-white/[.12] bg-[#111517]/95 p-1"><button className="icon-tool" title="Select">↖</button><button className={`icon-tool ${connectMode ? "active" : ""}`} onClick={() => connectMode ? resetConnection() : (setConnectMode(true), setConnectionError(null))} title="Connect">{connectMode ? "CONNECTING" : "CONNECT"}</button><button className="icon-tool" onClick={() => addDevice()} title="Add device">+</button><button className="icon-tool" onClick={removeSelected} title="Delete">×</button><span className="my-1 border-t border-white/[.1]" /><button className="icon-tool" onClick={() => setZoom((v) => Math.min(1.8, v + .1))} title="Zoom in">+</button><button className="icon-tool" onClick={() => setZoom((v) => Math.max(.6, v - .1))} title="Zoom out">−</button><button className="icon-tool" onClick={() => { setZoom(1); setPan({ x: 0, y: 0 }) }} title="Fit">⌂</button></div>
        {paletteOpen && <div className="absolute left-14 top-3 z-30 w-72 rounded-md border border-white/[.12] bg-[#111517] p-3 shadow-xl"><div className="mb-2 font-mono text-[9px] uppercase tracking-widest text-[#9aa3a0]">Add or import device</div><div className="mb-3 grid grid-cols-2 gap-1">{["Firewall", "Router", "Switch", "Server", "Wireless", "Generic Device"].map((type) => <button key={type} className="tool text-left" onClick={() => addDevice(type)}>+ {type}</button>)}</div><div className="max-h-52 space-y-1 overflow-y-auto">{realDevices.map((item) => <button key={item.id} className="block w-full rounded border border-white/[.08] p-2 text-left hover:bg-white/[.05]" onClick={() => importDevice(item)}><div className="text-[11px]">{item.hostname || item.name}</div><div className="font-mono text-[9px] text-[#6f7975]">{item.ip_address} · {item.device_type || "device"}</div></button>)}</div></div>}
        <div className="absolute right-3 top-3 z-10 flex items-center gap-2"><div className="rounded-md border border-white/[.1] bg-[#111517] p-1">{(["manual", "actual", "compare"] as ViewMode[]).map((v) => <button key={v} className={`px-2 py-1 font-mono text-[9px] uppercase ${view === v ? "bg-[#25312d] text-[#61c98d]" : "text-[#6f7975]"}`} onClick={() => setView(v)}>{v}</button>)}</div><button className="tool" onClick={() => setSidebarOpen((v) => !v)}>Sidebar</button></div>
        {connectMode && <div className="absolute left-14 right-3 top-3 z-20 flex flex-wrap items-center gap-2 rounded-md border border-[#3b82f6]/50 bg-[#111517]/95 px-3 py-2 font-mono text-[9px] uppercase"><span className="text-[#61c98d]">Connect workflow</span><span className="text-[#9aa3a0]">{!source ? "1. Select a source port" : !targetDeviceId ? `2. Source: ${source.port} · select destination device and port` : !targetPort ? "3. Select destination port" : `4. Review: ${source.port} → ${targetPort}`}</span>{targetPort && <button className="tool border-[#61c98d] text-[#61c98d]" onClick={createConnection}>Create & Save Link</button>}<button className="tool" onClick={() => { setConnectMode(false); setSource(null); setTargetDeviceId(null); setTargetPort(null); setConnectionError(null); setPointer(null) }}>Cancel</button>{connectionError && <span className="w-full text-[#d9646a]">{connectionError}</span>}</div>}
        <svg ref={svgRef} viewBox={`0 0 ${CANVAS.width} ${CANVAS.height}`} className="h-full min-h-[680px] w-full" style={{ backgroundImage: "radial-gradient(#26302d 1px, transparent 1px)", backgroundSize: "24px 24px" }} onPointerDown={(e) => { const p = point(e); if (p && e.target === e.currentTarget) setCanvasDrag({ x: pan.x, y: pan.y, px: e.clientX, py: e.clientY }) }} onPointerMove={(e) => { const p = point(e); if (p) setPointer(p); if (canvasDrag) setPan({ x: canvasDrag.x + e.clientX - canvasDrag.px, y: canvasDrag.y + e.clientY - canvasDrag.py }); if (routingDrag) { const p = point(e); if (p) { const link = workspace.links.find((l) => l.id === routingDrag.linkId); if (link) updateWorkspace({ ...workspace, links: workspace.links.map((l) => l.id === link.id ? { ...l, routingPoints: (l.routingPoints ?? []).map((q, i) => i === routingDrag.index ? p : q) } : l) }) } } }}>
          {previewPath && <path d={previewPath} fill="none" stroke="#3b82f6" strokeWidth="2" strokeDasharray="5 5" opacity=".9" pointerEvents="none" />}
          {unexpectedLinks.map((link) => { const path = actualPath(link); return path ? <g key={`unexpected-${link.id}`} onClick={() => { setSelectedChange(changes[0] ?? null); setSelectedLinkId(link.id); setSelectedId(null) }}><path d={path} fill="none" stroke="#d9646a" strokeWidth="2" strokeDasharray="7 5" opacity=".9" /><circle cx={actualWorkspace.devices.find((d) => d.id === link.from)?.x} cy={actualWorkspace.devices.find((d) => d.id === link.from)?.y} r="3" fill="#d9646a" /></g> : null })}
          {canvasLinks.map((link) => { const path = linkPath(link); return path ? <g key={link.id} onClick={() => { setSelectedLinkId(link.id); setSelectedId(null); const change = changes.find((item) => item.status === "pending") ?? null; if (change) setSelectedChange(change) }}><path d={path} fill="none" stroke="transparent" strokeWidth="18" /><path d={path} fill="none" stroke={statusColor(link.status)} strokeWidth={selectedLinkId === link.id ? "2.4" : "1.5"} strokeDasharray={link.status === "UNEXPECTED" || link.status === "UNKNOWN" ? "6 5" : undefined} /><circle cx={canvasWorkspace.devices.find((d) => d.id === link.from)?.x} cy={canvasWorkspace.devices.find((d) => d.id === link.from)?.y} r="3" fill={statusColor(link.status)} />{selectedLinkId === link.id && (link.routingPoints ?? []).map((p, i) => <circle key={i} cx={p.x} cy={p.y} r="6" fill="#111517" stroke="#3b82f6" onPointerDown={(e) => { e.stopPropagation(); setRoutingDrag({ linkId: link.id, index: i }) }} />)}</g> : null })}
          {canvasDevices.map((device) => <g key={device.id} transform={`translate(${device.x - 50},${device.y - 40})`} onPointerDown={(e) => { e.stopPropagation(); if (view === "actual") return; dragMoved.current = false; dragStartWorkspace.current = workspace; const p = point(e as unknown as ReactPointerEvent<SVGSVGElement>); if (p) setDrag({ id: device.id, ox: device.x - p.x, oy: device.y - p.y }); setSelectedId(device.id); setSelectedLinkId(null) }} onPointerMove={(e) => moveDevice(e, device.id)} onClick={() => { if (!dragMoved.current) setDetailsOpen(true) }} className="cursor-grab"><circle cx="50" cy="28" r="21" fill={`${device.tone}18`} stroke={selectedId === device.id ? "#e5e7e7" : `${device.tone}99`} strokeWidth={selectedId === device.id ? "2" : "1"} /><svg x="26" y="4" width="48" height="48" viewBox="0 0 48 48" fill="none" stroke={device.status?.toLowerCase() === "offline" ? "#78827e" : device.tone} strokeWidth="2">{glyph(device.type)}</svg><text x="50" y="62" textAnchor="middle" fill="#e5e7e7" fontSize="10" fontWeight="600">{device.name.slice(0, 18)}</text><text x="50" y="74" textAnchor="middle" fill="#9aa3a0" fontSize="8" fontFamily="monospace">{(device.ipAddress || device.subtitle || "").slice(0, 20)}</text><circle cx="86" cy="61" r="3" fill={device.status?.toLowerCase() === "offline" ? "#d9646a" : "#61c98d"} />{(selectedId === device.id || connectMode) && <g transform="translate(-10,88)">{portsFor(device).slice(0, 8).map((port, i) => <g key={port} onPointerDown={(e) => e.stopPropagation()} onClick={() => selectPort(device.id, port)}><rect x={(i % 2) * 62} y={Math.floor(i / 2) * 18} width="58" height="15" rx="3" fill="#111517" stroke="#293532" /><circle cx={(i % 2) * 62 + 8} cy={Math.floor(i / 2) * 18 + 7} r="2" fill={device.portSources?.[port] === "manual_fallback" ? "#9aa3a0" : device.portStatuses?.[port]?.toLowerCase() === "down" ? "#d9646a" : "#61c98d"} /><text x={(i % 2) * 62 + 14} y={Math.floor(i / 2) * 18 + 10} fill="#9aa3a0" fontSize="7" fontFamily="monospace">{port.slice(0, 9)}{device.portSources?.[port] === "manual_fallback" ? " · MANUAL" : ""}</text></g>)}</g>}</g>)}
        </svg>
        {selectedLink && view !== "actual" && <div className="absolute bottom-3 left-14 z-20 flex max-w-[calc(100%-240px)] flex-wrap items-center gap-1 rounded border border-white/[.12] bg-[#111517] p-1"><span className="px-2 font-mono text-[9px] text-[#9aa3a0]">{selectedLink.fromPort ?? "source"} → {selectedLink.toPort ?? "target"}</span><button className="tool" onClick={addBend}>+ Bend</button><button className="tool" onClick={resetRoute}>Reset Route</button><button className="tool" onClick={() => { const link = workspace.links.find((item) => item.id === selectedLinkId); if (link?.routingPoints?.length) updateWorkspace({ ...workspace, links: workspace.links.map((item) => item.id === link.id ? { ...item, routingPoints: link.routingPoints?.slice(0, -1) } : item) }) }}>Remove Bend</button><button className="tool" onClick={() => removeSelected()}>Delete Link</button></div>}
        <div className="absolute bottom-3 right-3 h-24 w-40 rounded border border-white/[.12] bg-[#111517] p-1"><MiniMap workspace={{ devices: canvasDevices, links: canvasLinks }} viewport={viewport} /></div>
        {portPanelDevice && <div className="absolute right-3 top-16 z-20 w-64 max-w-[calc(100%-80px)] rounded-md border border-white/[.12] bg-[#111517]/95 p-3 shadow-xl"><div className="font-mono text-[9px] uppercase tracking-widest text-[#9aa3a0]">Ports / Interfaces</div><div className="mt-1 truncate text-xs font-semibold">{portPanelDevice.name}</div><input className="mt-2 h-7 w-full rounded border border-white/[.1] bg-[#0d1113] px-2 font-mono text-[9px]" placeholder="Search ports..." value={portSearch} onChange={(event) => setPortSearch(event.target.value)} /><div className="mt-2 flex gap-1"><button className={`tool h-7 flex-1 ${portView === "physical" ? "border-[#61c98d] text-[#61c98d]" : ""}`} onClick={() => setPortView("physical")}>Physical Ports</button><button className={`tool h-7 flex-1 ${portView === "all" ? "border-[#61c98d] text-[#61c98d]" : ""}`} onClick={() => setPortView("all")}>All Interfaces</button></div><div className="mt-2 flex items-center justify-between font-mono text-[8px] uppercase text-[#6f7975]"><span>{portPanelAllPorts.length} ports · {portPanelAllPorts.filter((port) => port.operStatus.toUpperCase() === "UP").length} up · {portPanelAllPorts.filter((port) => port.operStatus.toUpperCase() === "DOWN").length} down</span><span className="flex gap-1"><button onClick={() => setPortStatus("all")}>ALL</button><button onClick={() => setPortStatus("up")}>UP</button><button onClick={() => setPortStatus("down")}>DOWN</button></span></div><div className="mt-2 max-h-80 space-y-1 overflow-y-auto">{portPanelPorts.map((port) => <div key={`${port.id}-${port.name}`} className="rounded border border-white/[.08] bg-[#0d1113] p-2"><div className="flex items-center justify-between gap-2"><span className="truncate text-[10px]">{port.name}</span><span className={port.operStatus.toUpperCase() === "UP" ? "text-[#61c98d]" : "text-[#d9646a]"}>● {port.operStatus.toUpperCase()}</span></div><div className="mt-1 font-mono text-[8px] text-[#6f7975]">ifIndex: {port.ifIndex ?? "null"} · {port.speed_display} · {port.source === "manual_fallback" ? "MANUAL PORT" : port.source.toUpperCase()}</div><button className="tool mt-2 h-7 w-full" onClick={() => { if (!connectMode) setConnectMode(true); selectPort(portPanelDevice.id, port.name) }}>{source?.deviceId === portPanelDevice.id && source.port === port.name ? "SOURCE SELECTED" : "USE PORT"}</button></div>)}</div></div>}
      </div>
      {sidebarOpen && <aside className="max-h-[calc(100vh-150px)] overflow-y-auto rounded-lg border border-white/[.12] bg-[#111517] p-3"><div className="mb-3 font-mono text-[10px] uppercase tracking-widest text-[#9aa3a0]">Topology Overview</div><div className="grid grid-cols-2 gap-2">{[[workspace.devices.length, "Devices"], [workspace.links.length, "Links"], [changes.length, "Issues"], [workspace.devices.filter((d) => d.status?.toLowerCase() !== "offline").length, "Online"]].map(([v, l]) => <div key={String(l)} className="rounded border border-white/[.08] bg-[#0d1113] p-2"><div className="text-lg text-[#61c98d]">{v}</div><div className="font-mono text-[8px] uppercase text-[#6f7975]">{l}</div></div>)}</div><div className="mt-5 border-t border-white/[.08] pt-3"><div className="font-mono text-[10px] uppercase tracking-widest text-[#9aa3a0]">Device Types</div>{deviceTypes.map((type, i) => <div key={type} className="mt-2 flex justify-between font-mono text-[9px] text-[#9aa3a0]"><span><i className="mr-2 inline-block h-2 w-2 rounded-full" style={{ background: toneFor(type, i) }} />{type}</span><span>{workspace.devices.filter((d) => d.type === type).length}</span></div>)}</div><div className="mt-5 border-t border-white/[.08] pt-3"><div className="font-mono text-[10px] uppercase tracking-widest text-[#9aa3a0]">Layers / Groups</div>{deviceTypes.map((type) => <div key={type} className="mt-2 font-mono text-[9px] uppercase text-[#6f7975]">{type}</div>)}</div><div className="mt-5 border-t border-white/[.08] pt-3"><div className="font-mono text-[10px] uppercase tracking-widest text-[#9aa3a0]">Legends</div>{[["#61c98d", "Verified"], ["#d4a95c", "Mismatch"], ["#d9646a", "Unexpected / disconnected"], ["#9aa3a0", "Unknown / offline"]].map(([color, label]) => <div key={label} className="mt-2 flex items-center gap-2 font-mono text-[9px] text-[#9aa3a0]"><i className="h-2 w-2 rounded-full" style={{ background: color }} />{label}</div>)}</div>{selected && <div className="mt-5 border-t border-white/[.08] pt-3"><div className="text-sm font-semibold">{selected.name}</div><div className="font-mono text-[9px] text-[#6f7975]">{selected.type} · {selected.ipAddress || selected.subtitle || "No IP"}</div><button className="tool mt-3 w-full" onClick={() => { const name = window.prompt("Device name", selected.name); if (name) { const next = { ...workspace, devices: workspace.devices.map((d) => d.id === selected.id ? { ...d, name } : d) }; updateWorkspace(next); if (selected.backendId) void updateDevice(selected.backendId, { hostname: name }) } }}>Edit Device</button></div>}</aside>}
    </section>
    {changes.length > 0 && <div className="mt-3 rounded border border-[#d4a95c55] bg-[#d4a95c0d] p-3"><div className="font-mono text-[10px] uppercase text-[#d4a95c]">Connectivity mismatch</div>{changes.slice(0, 3).map((change) => <div key={change.id} className="mt-2 flex flex-wrap items-center gap-2 text-xs"><span>{change.change_type}</span><button className="tool" onClick={() => setSelectedChange(change)}>View Difference</button><button className="tool" onClick={() => void resolveChange(change, "keep_manual")}>Keep Manual</button><button className="tool" onClick={() => void resolveChange(change, "accept_real_change")}>Accept Real Change</button></div>)}</div>}
    {detailsOpen && selected && <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={() => setDetailsOpen(false)}><section className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-lg border border-white/[.14] bg-[#111517] p-5" onClick={(e) => e.stopPropagation()}><div className="flex items-start justify-between"><div><h2 className="text-lg font-semibold">Device Details</h2><div className="font-mono text-[9px] uppercase text-[#6f7975]">{selected.type}</div></div><button className="tool" onClick={() => setDetailsOpen(false)}>Close</button></div><div className="mt-4 grid gap-3 sm:grid-cols-2">{[["Hostname", selected.name], ["Display Name", selected.name], ["IP Address", selected.ipAddress || selected.subtitle], ["MAC Address", selected.macAddress], ["Vendor", selected.vendor], ["Model", selected.model], ["Serial Number", selected.serialNumber], ["Firmware", selected.firmware], ["SNMP Version", selected.snmpVersion], ["Backend Device ID", selected.backendId], ["Monitoring Enabled", selected.monitoringEnabled], ["Last Seen", selected.lastSeen], ["Status", selected.status], ["Location", selected.location]].map(([label, value]) => <div key={String(label)} className="rounded border border-white/[.08] bg-[#0d1113] p-2"><div className="font-mono text-[8px] uppercase text-[#6f7975]">{label}</div><div className="mt-1 text-xs">{value == null || value === "" ? "N/A" : String(value)}</div></div>)}</div><div className="mt-5 border-t border-white/[.08] pt-4"><div className="font-mono text-[10px] uppercase text-[#9aa3a0]">Interfaces</div><div className="mt-2 space-y-1">{(interfaces[selected.id] ?? []).map((item) => <div key={item.id} className="flex flex-wrap justify-between gap-2 rounded border border-white/[.06] p-2 font-mono text-[9px]"><span>{item.name} · ifIndex {item.if_index}</span><span className={item.status === "UP" ? "text-[#61c98d]" : "text-[#d9646a]"}>{item.admin_status} / {item.status} · {item.speed_display || "N/A"}</span></div>)}{!(interfaces[selected.id]?.length) && <div className="text-xs text-[#6f7975]">Interfaces unavailable</div>}</div></div><div className="mt-4 flex gap-2"><button className="tool" onClick={() => { const name = window.prompt("Hostname", selected.name); if (name?.trim()) { updateWorkspace({ ...workspace, devices: workspace.devices.map((d) => d.id === selected.id ? { ...d, name: name.trim() } : d) }); if (selected.backendId) void updateDevice(selected.backendId, { hostname: name.trim() }) } }}>Edit Device</button><button className="tool" onClick={removeSelected}>Remove From Topology</button></div></section></div>}
    {selectedChange && <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/75 p-4" onClick={() => setSelectedChange(null)}><section className="w-full max-w-lg rounded-lg border border-[#d4a95c66] bg-[#111517] p-5" onClick={(e) => e.stopPropagation()}><div className="flex items-start justify-between"><div><h2 className="text-lg font-semibold">Difference</h2><div className="font-mono text-[9px] uppercase text-[#d4a95c]">{issueStatus(selectedChange)}</div></div><button className="tool" onClick={() => setSelectedChange(null)}>Close</button></div><div className="mt-4 grid gap-3 sm:grid-cols-2"><div className="rounded border border-white/[.08] bg-[#0d1113] p-3"><div className="font-mono text-[9px] uppercase text-[#9aa3a0]">Manual Connection</div><div className="mt-2 text-xs">{evidenceValue(selectedChange.expected, ["source_device", "from_device", "device"])} : {evidenceValue(selectedChange.expected, ["source_port", "from_port", "port"])}<br />→<br />{evidenceValue(selectedChange.expected, ["target_device", "to_device", "remote_device"])} : {evidenceValue(selectedChange.expected, ["target_port", "to_port", "remote_port"])}</div></div><div className="rounded border border-white/[.08] bg-[#0d1113] p-3"><div className="font-mono text-[9px] uppercase text-[#9aa3a0]">Actual Physical Connection</div><div className="mt-2 text-xs">{evidenceValue(selectedChange.observed, ["source_device", "from_device", "device"])} : {evidenceValue(selectedChange.observed, ["source_port", "from_port", "port"])}<br />→<br />{evidenceValue(selectedChange.observed, ["target_device", "to_device", "remote_device"])} : {evidenceValue(selectedChange.observed, ["target_port", "to_port", "remote_port"])}</div></div></div><div className="mt-3 space-y-1 rounded border border-white/[.08] p-3 font-mono text-[10px]">Status: {issueStatus(selectedChange)}<br />Evidence: {evidenceValue(selectedChange.observed, ["evidenceSource", "evidence_source", "source"])}<br />Confidence: {evidenceValue(selectedChange.observed, ["confidence"])}<br />Last verified: {selectedChange.detected_at || "N/A"}{issueStatus(selectedChange) === "UNKNOWN" && <><br /><span className="text-[#9aa3a0]">Insufficient physical evidence</span></>}</div><div className="mt-4 flex justify-end gap-2"><button className="tool" onClick={() => void resolveChange(selectedChange, "keep_manual")}>Keep Manual</button><button className="tool" onClick={() => void resolveChange(selectedChange, "accept_real_change")}>Accept Real Change</button></div></section></div>}
    <footer className="mt-3 flex min-h-8 flex-wrap items-center gap-5 border-t border-white/[.1] pt-2 font-mono text-[9px] uppercase text-[#6f7975]"><span>Selected: <b className="text-[#e5e7e7]">{selected?.name || (selectedLinkId ? "Link" : "None")}</b></span><span>Devices: {workspace.devices.length}</span><span>Links: {workspace.links.length}</span><span>Last Saved: {saving ? "Saving..." : lastSaved || "Not saved"}</span><span className="ml-auto">Shortcuts: / F L</span></footer>
      <style>{`.tool{height:32px;border:1px solid rgba(170,190,180,.14);background:#111517;color:#e5e7e7;border-radius:6px;padding:0 10px;font:10px ui-monospace,monospace;text-transform:uppercase}.tool:hover{border-color:#3b82f6;color:#fff}.icon-tool{height:32px;width:32px;border:1px solid transparent;background:transparent;color:#9aa3a0;border-radius:5px;font:16px ui-monospace,monospace}.icon-tool[title="Connect"]{width:88px;font-size:9px}.icon-tool:hover,.icon-tool.active{background:#172522;border-color:#3b82f6;color:#61c98d}`}</style>
  </main>
  */
}
