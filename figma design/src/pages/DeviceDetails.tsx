import { useEffect, useMemo, useState } from "react"
import { Link, useParams } from "react-router"
import GlassCard from "../components/GlassCard"
import {
  createWindowsCredential,
  getDevice,
  getSNMPDeviceOverview,
  listWindowsCredentials,
  testWindowsConnection,
  updateWindowsCredential,
  type DeviceRecord,
  type WindowsCredentialRecord,
} from "../lib/api"
import { useAuth } from "../components/AuthContext"
import { isWindowsDevice } from "../lib/windowsClassification"
import { formatUptime } from "../unitFormatting"
const missing = "—"
const date = (v?: string | null) =>
  v
    ? new Date(v).toLocaleString("en-IN", { timeZone: "Asia/Kolkata" })
    : missing
const duration = (s?: number | null) =>
  formatUptime(s, { na: missing })
function Field({ label, value }: { label: string value: unknown }) {
  return (
    <div>
      <div
        className="font-mono text-[10px] uppercase"
        style={{ color: "var(--t-muted)" }}
      >
        {label}
      </div>
      <div className="text-sm mt-1" style={{ color: "var(--t-text)" }}>
        {value || missing}
      </div>
    </div>
  )
}

function windowsStatus(
  result: { ok: boolean category?: string } | null,
  configured: boolean,
  testing: boolean,
) {
  if (testing) return ["Testing", "#fbbf24"] as const
  if (!configured) return ["Not Configured", "var(--t-muted)"] as const
  if (!result) return ["Configured", "var(--t-accent)"] as const
  if (result.ok) return ["Connected", "#4ade80"] as const
  const labels: Record<string, string> = {
    authentication: "Authentication Failed",
    tls: "Certificate Verification Failed",
    timeout: "Connection Timeout",
    network: "Connection Refused",
    permission: "Permission Denied",
    protocol: "Connection Failed",
  }
  return [
    labels[result.category ?? ""] ?? "Connection Failed",
    "#ff6b8a",
  ] as const
}

function WindowsMonitoring({
  device,
  live,
}: {
  device: DeviceRecord
  live: Record<string, any>
}) {
  const { hasPermission } = useAuth()
  const canUpdate = hasPermission("devices:update")
  const [credential, setCredential] = useState<WindowsCredentialRecord | null>(
    null,
  )
  const [username, setUsername] = useState("")
  const [domain, setDomain] = useState("")
  const [connectionHost, setConnectionHost] = useState("")
  const [password, setPassword] = useState("")
  const [showPassword, setShowPassword] = useState(false)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [result, setResult] = useState<{
    ok: boolean
    category?: string
    message?: string
  } | null>(null)
  const [error, setError] = useState("")
  useEffect(() => {
    let active = true
    void listWindowsCredentials(device.id)
      .then((rows) => {
        if (!active) return
        const current = rows[0] ?? null
        setCredential(current)
        setUsername(current?.username ?? "")
        setDomain(current?.domain ?? "")
        setConnectionHost(current?.connection_host ?? "")
      })
      .catch((e) => {
        if (active)
          setError(
            e instanceof Error
              ? e.message
              : "Unable to load Windows credentials",
          )
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [device.id])
  const [status, color] = windowsStatus(result, credential != null, testing)
  const save = async () => {
    if (!username.trim() || (!credential && !password)) {
      setError("Username and password are required for initial setup.")
      return
    }
    setSaving(true)
    setError("")
    try {
      const saved = credential
        ? await updateWindowsCredential(device.id, credential.id, {
            username: username.trim(),
            domain: domain.trim() || undefined,
            connection_host: connectionHost.trim() || undefined,
            ...(password ? { secret: password } : {}),
          })
        : await createWindowsCredential(device.id, {
            device_id: device.id,
            username: username.trim(),
            domain: domain.trim() || undefined,
            connection_host: connectionHost.trim() || undefined,
            secret: password,
            enabled: true,
          })
      setCredential(saved)
      setConnectionHost(saved.connection_host ?? "")
      setPassword("")
      setResult(null)
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "Unable to save Windows credentials",
      )
    } finally {
      setSaving(false)
    }
  }
  const test = async () => {
    setTesting(true)
    setError("")
    setResult(null)
    try {
      setResult(await testWindowsConnection(device.id))
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "Unable to test Windows connection",
      )
    } finally {
      setTesting(false)
    }
  }
  return (
    <GlassCard className="p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2
            className="font-display font-bold"
            style={{ color: "var(--t-text)" }}
          >
            WINDOWS MONITORING
          </h2>
          <p
            className="mt-1 font-mono text-xs"
            style={{ color: "var(--t-muted)" }}
          >
            WinRM HTTPS · NTLM · port 5986
          </p>
        </div>
        <span
          className="rounded-full px-3 py-1 font-mono text-[10px] uppercase"
          style={{ color, border: `1px solid ${color}` }}
        >
          {status}
        </span>
      </div>
      {loading ? (
        <div
          className="mt-5 font-mono text-xs"
          style={{ color: "var(--t-muted)" }}
        >
          Loading credential status…
        </div>
      ) : (
        <div className="mt-5 space-y-4">
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <label
              className="font-mono text-[10px] uppercase"
              style={{ color: "var(--t-muted)" }}
            >
              Username
              <input
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                disabled={!canUpdate || saving}
                className="mt-1 w-full rounded px-3 py-2 text-sm"
                style={{
                  background: "var(--t-bg)",
                  color: "var(--t-text)",
                  border: "1px solid var(--t-border-light)",
                }}
                autoComplete="off"
              />
            </label>
            <label
              className="font-mono text-[10px] uppercase"
              style={{ color: "var(--t-muted)" }}
            >
              Domain / Computer Name
              <input
                value={domain}
                onChange={(e) => setDomain(e.target.value)}
                disabled={!canUpdate || saving}
                className="mt-1 w-full rounded px-3 py-2 text-sm"
                style={{
                  background: "var(--t-bg)",
                  color: "var(--t-text)",
                  border: "1px solid var(--t-border-light)",
                }}
                autoComplete="off"
              />
            </label>
          </div>
          <label
            className="block font-mono text-[10px] uppercase"
            style={{ color: "var(--t-muted)" }}
          >
            Connection Host (DNS/IP)
            <input
              value={connectionHost}
              onChange={(e) => setConnectionHost(e.target.value)}
              disabled={!canUpdate || saving}
              placeholder="Defaults to inventory hostname/IP"
              className="mt-1 w-full rounded px-3 py-2 text-sm"
              style={{
                background: "var(--t-bg)",
                color: "var(--t-text)",
                border: "1px solid var(--t-border-light)",
              }}
              autoComplete="off"
            />
          </label>
          <label
            className="block font-mono text-[10px] uppercase"
            style={{ color: "var(--t-muted)" }}
          >
            Password
            <input
              type={showPassword ? "text" : "password"}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={!canUpdate || saving}
              placeholder={
                credential
                  ? "Leave blank to keep current password"
                  : "Enter monitoring password"
              }
              className="mt-1 w-full rounded px-3 py-2 text-sm"
              style={{
                background: "var(--t-bg)",
                color: "var(--t-text)",
                border: "1px solid var(--t-border-light)",
              }}
              autoComplete="new-password"
            />
            <button
              type="button"
              onClick={() => setShowPassword((value) => !value)}
              className="mt-2 font-mono text-[10px]"
              style={{ color: "var(--t-accent)" }}
            >
              {showPassword ? "HIDE PASSWORD" : "SHOW PASSWORD"}
            </button>
          </label>
          {error && (
            <div
              role="alert"
              className="rounded p-3 font-mono text-xs"
              style={{
                color: "#ff6b8a",
                border: "1px solid rgba(255,51,102,.35)",
              }}
            >
              {error}
            </div>
          )}
          {result?.message && (
            <div
              className="rounded p-3 font-mono text-xs"
              style={{
                color: result.ok ? "#4ade80" : "#ffb86b",
                border: result.ok
                  ? "1px solid rgba(74,222,128,.35)"
                  : "1px solid rgba(255,184,107,.35)",
              }}
            >
              {status}: {result.message}
            </div>
          )}
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => void save()}
              disabled={!canUpdate || saving || testing}
              className="rounded px-4 py-2 font-mono text-xs"
              style={{
                background: "var(--t-accent)",
                color: "#fff",
                opacity: canUpdate ? 1 : 0.5,
              }}
            >
              {saving ? "SAVING…" : "SAVE CREDENTIALS"}
            </button>
            <button
              type="button"
              onClick={() => void test()}
              disabled={!credential || saving || testing}
              className="rounded px-4 py-2 font-mono text-xs"
              style={{
                background: "var(--t-border-alpha)",
                color: "var(--t-text)",
                opacity: credential ? 1 : 0.5,
              }}
            >
              {testing ? "TESTING…" : "TEST CONNECTION"}
            </button>
          </div>
          {!canUpdate && (
            <p
              className="font-mono text-[10px]"
              style={{ color: "var(--t-muted)" }}
            >
              You need devices:update permission to manage or test Windows
              credentials.
            </p>
          )}
        </div>
      )}
    </GlassCard>
  )
}

export default function DeviceDetails() {
  const { deviceId } = useParams()
  const [device, setDevice] = useState<DeviceRecord | null>(null)
  const [snmp, setSnmp] = useState<Record<string, any> | null>(null)
  const [error, setError] = useState("")
  useEffect(() => {
    if (!deviceId) return
    const id = Number(deviceId)
    void Promise.all([getDevice(id), getSNMPDeviceOverview(id)])
      .then(([record, overview]) => {
        setDevice(record)
        setSnmp(overview)
      })
      .catch((e) =>
        setError(e instanceof Error ? e.message : "Device not found"),
      )
  }, [deviceId])
  if (error)
    return (
      <div className="p-6 font-mono text-sm" style={{ color: "#ff6b8a" }}>
        {error}
      </div>
    )
  if (!device)
    return (
      <div
        className="p-6 font-mono text-sm"
        style={{ color: "var(--t-muted)" }}
      >
        Loading device…
      </div>
    )
  const live = snmp || {}
  const snmpConfigured = Boolean(
    live.snmp_version ||
      device.snmp_version ||
      (live.modules || []).some((module: any) => module?.supported),
  )
  const snmpVersion =
    live.snmp_version ||
    device.snmp_version ||
    (snmpConfigured ? "Configured" : missing)
  const overview = [
    ["Name / Hostname", live.hostname ?? device.hostname],
    ["IP Address", live.ip_address ?? device.ip_address],
    ["MAC Address", device.mac_address],
    ["Device Type", live.device_type ?? device.device_type],
    ["Vendor", live.vendor ?? device.vendor_name ?? device.vendor],
    ["Model", live.model ?? device.model],
    ["Site ID", device.site_id],
    ["Status", live.status ?? device.status],
    ["Last Seen", live.last_poll ?? date(device.last_seen)],
  ]
  const showWindows = isWindowsDevice(device, live)
  return (
    <div className="p-4 md:p-6 space-y-5">
      <header className="flex flex-col md:flex-row md:items-start md:justify-between gap-3">
        <div>
          <Link
            to="/devices"
            className="font-mono text-xs"
            style={{ color: "var(--t-accent)" }}
          >
            ← ALL DEVICES
          </Link>
          <h1
            className="font-display font-bold text-xl md:text-2xl mt-3"
            style={{ color: "var(--t-text)" }}
          >
            {live.hostname ?? device.hostname ?? "DEVICE DETAILS"}
          </h1>
          <p
            className="font-mono text-xs mt-1"
            style={{ color: "var(--t-muted)" }}
          >
            General device information and inventory overview
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Link
            to={`/device-monitoring/${device.id}`}
            className="rounded px-3 py-2 font-mono text-xs"
            style={{ background: "var(--t-accent)", color: "#fff" }}
          >
            VIEW MONITORING
          </Link>
          <Link
            to={`/snmp/devices/${device.id}`}
            className="rounded px-3 py-2 font-mono text-xs"
            style={{ background: "var(--t-accent)", color: "#fff" }}
          >
            SNMP DEVICE
          </Link>
          <Link
            to={`/remote-access?device_id=${device.id}`}
            className="rounded px-3 py-2 font-mono text-xs"
            style={{ background: "var(--t-accent)", color: "#fff" }}
          >
            REMOTE ACCESS
          </Link>
        </div>
      </header>
      <GlassCard className="p-5">
        <h2
          className="font-display font-bold"
          style={{ color: "var(--t-text)" }}
        >
          DEVICE OVERVIEW
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 mt-4">
          {overview.map(([label, value]) => (
            <Field key={label} label={label} value={value} />
          ))}
        </div>
      </GlassCard>
      <GlassCard className="p-5">
        <h2
          className="font-display font-bold"
          style={{ color: "var(--t-text)" }}
        >
          INVENTORY / SYSTEM INFORMATION
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 mt-4">
          {[
            ["Device ID", device.id],
            ["Vendor ID", device.vendor_id],
            ["Device Type ID", device.device_type_id],
            ["Serial Number", device.serial_number],
            ["Firmware Version", device.firmware_version],
            ["Uptime", duration(device.uptime_seconds)],
            ["Downtime", duration(device.downtime_seconds)],
          ].map(([label, value]) => (
            <Field key={String(label)} label={String(label)} value={value} />
          ))}
        </div>
      </GlassCard>
      <GlassCard className="p-5">
        <h2
          className="font-display font-bold"
          style={{ color: "var(--t-text)" }}
        >
          CONNECTIVITY / PROTOCOLS
        </h2>
        <div
          className="grid grid-cols-2 md:grid-cols-3 gap-4 mt-4 text-sm"
          style={{ color: "var(--t-text)" }}
        >
          <div>
            ICMP:{" "}
            {device.last_seen
              ? `Last seen ${date(device.last_seen)}`
              : "No activity recorded"}
          </div>
          <div>
            SNMP:{" "}
            {snmpConfigured
              ? `Last poll ${date(live.last_poll)}`
              : "No activity recorded"}
          </div>
          <div>
            SNMP Version:{" "}
            {snmpConfigured ? snmpVersion : "No activity recorded"}
          </div>
          <div>
            Monitoring Status:{" "}
            {(live.polling_enabled ?? device.monitoring_status)
              ? "Active"
              : "Inactive"}
          </div>
        </div>
      </GlassCard>
      {showWindows && <WindowsMonitoring device={device} live={live} />}
    </div>
  )
}
