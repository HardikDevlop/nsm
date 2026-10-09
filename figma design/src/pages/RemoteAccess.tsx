import { useEffect, useMemo, useRef, useState } from "react"
import { Terminal } from "@xterm/xterm"
import { FitAddon } from "@xterm/addon-fit"
import "@xterm/xterm/css/xterm.css"
import GlassCard from "../components/GlassCard"
import {
  createDevice,
  createRemoteAccessSession,
  listDeviceOptions,
  listRemoteAccessSessions,
  listRemoteAccessSessionHistory,
  openRemoteAccessTerminal,
  testRemoteAccess,
  listRemoteAccessCredentials,
  updateRemoteAccessCredential,
  deleteRemoteAccessCredential,
  trustSSHHostKey,
  revokeSSHHostKey,
  scanSSHHostKey,
  type DeviceOptionRecord,
  type RemoteAccessTestResponse,
  type RemoteAccessCredentialRecord,
} from "../lib/api"
import { toast } from "../lib/swal"

const inputStyle: React.CSSProperties = {
  background: "var(--t-border-light, rgba(255,255,255,.04))",
  border: "1px solid var(--t-border-alpha)",
  color: "var(--t-text)",
  outline: "none",
}
export default function RemoteAccess() {
  const remoteAccessDraftKey = "nms.remote-access.draft"
  type TerminalTab = {
    sessionUuid: string
    deviceId: number
    ipAddress?: string
    hostname: string
    protocol: "ssh" | "telnet"
    port: number
    deviceUsername?: string
    status: "connecting" | "connected" | "disconnected" | "error"
    startedAt?: number
  }
  type SessionHistoryEntry = TerminalTab & { endedAt?: number; reason?: string; sourceIp?: string; deviceIp?: string; userName?: string }
  const friendlyDisconnectReason = (reason?: string | null) => {
    if (!reason) return "—"
    if (/api disconnect|user disconnect|disconnect requested/i.test(reason)) return "User disconnected"
    if (/idle/i.test(reason)) return "Idle timeout"
    if (/connection lost|websocket|transport|network/i.test(reason)) return "Connection lost"
    if (/backend session owner|owner was lost|backend/i.test(reason)) return "Backend session lost"
    return reason
  }
  const [devices, setDevices] = useState<DeviceOptionRecord[]>([])
  const [deviceId, setDeviceId] = useState<number | "">("")
  const [addingDevice, setAddingDevice] = useState(false)
  const [addingDeviceBusy, setAddingDeviceBusy] = useState(false)
  const [newDevice, setNewDevice] = useState({ hostname: "", ip_address: "" })
  const [newDeviceError, setNewDeviceError] = useState("")
  const [protocol, setProtocol] = useState<"ssh" | "telnet">("ssh")
  const [username, setUsername] = useState("admin")
  const [password, setPassword] = useState("")
  const [showPassword, setShowPassword] = useState(false)
  const [remember, setRemember] = useState(true)
  const [tab, setTab] = useState("Terminal")
  const [connected, setConnected] = useState(false)
  const [port, setPort] = useState(22)
  const [customPort, setCustomPort] = useState(false)
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<RemoteAccessTestResponse | null>(
    null,
  )
  const [validatedInput, setValidatedInput] = useState<string | null>(null)
  const [testError, setTestError] = useState("")
  const [hostKeyActionBusy, setHostKeyActionBusy] = useState(false)
  const [hostKeyDialog, setHostKeyDialog] = useState<"unknown" | "mismatch" | null>(null)
  const [terminalTabs, setTerminalTabs] = useState<TerminalTab[]>([])
  const [connectingRequest, setConnectingRequest] = useState(false)
  const [activeSessionUuid, setActiveSessionUuid] = useState<string | null>(
    null,
  )
  const [terminalError, setTerminalError] = useState("")
  const [timerNow, setTimerNow] = useState(Date.now())
  const [sessionHistory, setSessionHistory] = useState<SessionHistoryEntry[]>([])
  const [terminalFullscreen, setTerminalFullscreen] = useState(false)
  const [connectionPanelVisible, setConnectionPanelVisible] = useState(true)
  const terminalHostRef = useRef<HTMLDivElement>(null)
  const terminalPanelRef = useRef<HTMLDivElement>(null)
  const terminalRef = useRef<Terminal | null>(null)
  const fitRef = useRef<FitAddon | null>(null)
  const terminalHostsRef = useRef(new Map<string, HTMLDivElement>())
  const visibleTerminalSessionRef = useRef<string | null>(null)
  const bootstrapPromiseRef = useRef<Promise<[DeviceOptionRecord[], Awaited<ReturnType<typeof listRemoteAccessSessions>>, Awaited<ReturnType<typeof listRemoteAccessSessionHistory>>]> | null>(null)
  const terminalsRef = useRef(new Map<string, { terminal: Terminal; fit: FitAddon; input: { dispose: () => void }; resize: { dispose: () => void }; observer: ResizeObserver; fitFrame?: number; lastResize?: string; lastWidth?: number; lastHeight?: number; lastFitSize?: string; diagnosticSequence?: number; firstOutput?: boolean; lastPostOutputGeometry?: string }>())
  const socketsRef = useRef(new Map<string, WebSocket>())
  const connectingSessionsRef = useRef(new Set<string>())
  const disconnectingSessionsRef = useRef(new Set<string>())
  const intentionalSocketCloseRef = useRef(new Set<string>())
  const connectionToastShownRef = useRef(new Set<string>())
  const connectionToastStorageKey = (sessionUuid: string) => `nms.remote-access.connection-toast:${sessionUuid}`
  visibleTerminalSessionRef.current = tab === "Terminal" ? activeSessionUuid : null
  // Keep the connection form across route unmounts. The device session itself
  // is owned by the backend and is restored from the active-sessions API.
  useEffect(() => {
    try {
      const requestedDeviceId = new URLSearchParams(window.location.search).get("device_id")
      if (requestedDeviceId && /^\d+$/.test(requestedDeviceId)) setDeviceId(Number(requestedDeviceId))
      const saved = JSON.parse(localStorage.getItem(remoteAccessDraftKey) ?? "null") as Partial<{
        deviceId: number | ""; protocol: "ssh" | "telnet"; username: string;
        remember: boolean; port: number; customPort: boolean;
      }> | null
      if (!saved) return
      if (!requestedDeviceId && saved.deviceId !== undefined) setDeviceId(saved.deviceId)
      if (saved.protocol) setProtocol(saved.protocol)
      if (saved.username !== undefined) setUsername(saved.username)
      if (saved.remember !== undefined) setRemember(saved.remember)
      if (saved.port !== undefined) setPort(saved.port)
      if (saved.customPort !== undefined) setCustomPort(saved.customPort)
    } catch { /* ignore malformed browser storage */ }
  }, [])
  useEffect(() => {
    if (!devices.length) return
    let cancelled = false
    const refreshSessionData = async () => {
      try {
        const [activeSessions, history] = await Promise.all([
          listRemoteAccessSessions(),
          listRemoteAccessSessionHistory(),
        ])
        if (cancelled) return
        const deviceById = new Map(devices.map((device) => [device.id, device]))
        const activeIds = new Set(activeSessions.map((session) => session.session_uuid))
        setSessionHistory(history.map((session) => ({
          sessionUuid: session.session_uuid,
          deviceId: session.device_id,
          hostname: deviceById.get(session.device_id)?.hostname ?? String(session.device_id),
          protocol: session.protocol,
          port: session.port,
          status: session.status === "connected" && activeIds.has(session.session_uuid) ? "connected" : "disconnected",
          startedAt: new Date(session.started_at).getTime(),
          endedAt: session.ended_at ? new Date(session.ended_at).getTime() : undefined,
          reason: session.disconnect_reason ?? "—",
          sourceIp: session.source_ip ?? undefined,
          deviceIp: deviceById.get(session.device_id)?.ip_address ?? undefined,
          userName: session.user_name ?? undefined,
        } as SessionHistoryEntry)))
      } catch {
        // Keep the last successful history visible during a transient refresh failure.
      }
    }
    const interval = window.setInterval(() => { void refreshSessionData() }, 5000)
    return () => {
      cancelled = true
      window.clearInterval(interval)
    }
  }, [devices])
  useEffect(() => {
    try {
      localStorage.setItem(remoteAccessDraftKey, JSON.stringify({
        deviceId, protocol, username, remember, port, customPort,
      }))
    } catch { /* storage may be unavailable */ }
  }, [deviceId, protocol, username, remember, port, customPort])
  useEffect(() => {
    let cancelled = false
    bootstrapPromiseRef.current ??= Promise.all([
      listDeviceOptions({ limit: 500 }),
      listRemoteAccessSessions(),
      listRemoteAccessSessionHistory(),
    ])
    void bootstrapPromiseRef.current.then(([deviceOptions, activeSessions, history]) => {
      if (cancelled) return
      setDevices(deviceOptions)
      if (deviceOptions.length === 0) setAddingDevice(true)
      const deviceById = new Map(deviceOptions.map((device) => [device.id, device]))
      const restored = activeSessions.map((session) => ({
        sessionUuid: session.session_uuid,
        deviceId: session.device_id,
        ipAddress: deviceById.get(session.device_id)?.ip_address,
        hostname: deviceById.get(session.device_id)?.hostname ?? String(session.device_id),
        protocol: session.protocol,
        port: session.port,
        status: session.status === "connected" ? "connected" : "connecting",
        deviceUsername: session.device_username,
        startedAt: new Date(session.started_at).getTime(),
      } as TerminalTab))
      const unique = restored.filter((session, index, all) =>
        all.findIndex((candidate) => candidate.deviceId === session.deviceId) === index,
      )
      const activeIds = new Set(unique.map((session) => session.sessionUuid))
      setTerminalTabs(unique)
      setActiveSessionUuid((active) => active ?? (
        unique.find((session) => session.status === "connected")?.sessionUuid ??
        unique[0]?.sessionUuid ??
        null
      ))
      setSessionHistory(history.map((session) => ({
        sessionUuid: session.session_uuid,
        deviceId: session.device_id,
        hostname: deviceById.get(session.device_id)?.hostname ?? String(session.device_id),
        protocol: session.protocol,
        port: session.port,
        status: session.status === "connected" && activeIds.has(session.session_uuid) ? "connected" : "disconnected",
        startedAt: new Date(session.started_at).getTime(),
        endedAt: session.ended_at ? new Date(session.ended_at).getTime() : undefined,
        reason: session.disconnect_reason ?? "—",
        sourceIp: session.source_ip ?? undefined,
        deviceIp: deviceById.get(session.device_id)?.ip_address ?? undefined,
        userName: session.user_name ?? undefined,
      } as SessionHistoryEntry)))
    }).catch(() => undefined)
    return () => { cancelled = true }
  }, [])
  const selected = useMemo(
    () => devices.find((d) => d.id === deviceId),
    [devices, deviceId],
  )
  const selectedCredential: RemoteAccessCredentialRecord | undefined = undefined
  const host = selected?.ip_address ?? ""
  const saveNewDevice = async () => {
    const hostname = newDevice.hostname.trim()
    const ipAddress = newDevice.ip_address.trim()
    if (!hostname || !ipAddress) {
      setNewDeviceError("Enter a device name and IP address.")
      return
    }
    setAddingDeviceBusy(true)
    setNewDeviceError("")
    try {
      const saved = await createDevice({ hostname, ip_address: ipAddress })
      const option: DeviceOptionRecord = {
        id: saved.id,
        hostname: saved.hostname,
        ip_address: saved.ip_address,
        mac_address: saved.mac_address,
        model: saved.model,
        vendor_name: saved.vendor_name,
        device_type: saved.device_type,
        status: saved.status,
      }
      setDevices((current) => current.some((device) => device.id === option.id)
        ? current
        : [...current, option])
      setDeviceId(option.id)
      setNewDevice({ hostname: "", ip_address: "" })
      setAddingDevice(false)
      setTestResult(null)
      setValidatedInput(null)
      toast.success(`${option.hostname} added to devices`)
    } catch (error) {
      setNewDeviceError(error instanceof Error ? error.message : "Unable to add device.")
    } finally {
      setAddingDeviceBusy(false)
    }
  }
  const formatSessionTime = (timestamp?: number) =>
    timestamp ? new Date(timestamp).toLocaleString() : "—"
  const formatDuration = (startedAt?: number, endedAt?: number) => {
    if (!startedAt) return "—"
    const totalSeconds = Math.max(0, Math.floor(((endedAt ?? timerNow) - startedAt) / 1000))
    const hours = Math.floor(totalSeconds / 3600)
    const minutes = Math.floor((totalSeconds % 3600) / 60)
    const seconds = totalSeconds % 60
    return hours > 0
      ? `${hours}h ${String(minutes).padStart(2, "0")}m ${String(seconds).padStart(2, "0")}s`
      : `${minutes}m ${String(seconds).padStart(2, "0")}s`
  }
  const changeProtocol = (value: "ssh" | "telnet") => {
    setProtocol(value)
    if (!customPort) setPort(value === "ssh" ? 22 : 23)
    setTestResult(null)
    setValidatedInput(null)
    setTestError("")
  }
  const inputFingerprint = () => JSON.stringify({ deviceId, protocol, port, username: username.trim(), secretPresent: Boolean(password) })
  const activeSessionForDevice = (id: number | "") => terminalTabs.find(
    (item) => item.deviceId === id && (item.status === "connected" || item.status === "connecting"),
  )
  const notifyAlreadyConnected = (session: TerminalTab) => {
    toast.warning(`${session.hostname} is already connected via ${session.protocol.toUpperCase()}.`)
  }
  useEffect(() => {
    if (validatedInput !== null) {
      setTestResult(null)
      setValidatedInput(null)
    }
  }, [deviceId, protocol, port, username, password])
  const runTest = async () => {
    const activeSession = activeSessionForDevice(deviceId)
    if (activeSession) {
      notifyAlreadyConnected(activeSession)
      return
    }
    setTestResult(null)
    setTestError("")
    if (deviceId === "" || (protocol === "telnet" && (!username.trim() || !password))) {
      setTestError(protocol === "ssh" ? "Select a device." : "Select a device and enter username and password.")
      return
    }
    setTesting(true)
    try {
      const result = await testRemoteAccess({
          device_id: deviceId,
          protocol,
          port,
          ...(selectedCredential
            ? { credential_id: selectedCredential.id }
            : (username.trim() && password ? { username: username.trim(), secret: password } : {})),
          auth_type: "password",
          remember_credential: remember,
      })
      setTestResult(result)
      setHostKeyDialog(
        result.error_code === "HOST_KEY_UNKNOWN" ? "unknown" :
          result.error_code === "HOST_KEY_MISMATCH" ? "mismatch" : null,
      )
      setValidatedInput(result.success ? inputFingerprint() : null)
    } catch (error) {
      setTestError(
        error instanceof Error ? error.message : "Connection test failed.",
      )
    } finally {
      setTesting(false)
    }
  }
  const retryAfterHostKeyAction = async () => {
    setHostKeyDialog(null)
    await runTest()
  }
  const trustUnknownHostKey = async () => {
    const item = testResult
    if (!item?.host_key_id) return
    setHostKeyActionBusy(true)
    try {
      await trustSSHHostKey(item.host_key_id)
      toast.success("SSH host key trusted. Retesting connection…")
      await retryAfterHostKeyAction()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Unable to trust SSH host key")
    } finally { setHostKeyActionBusy(false) }
  }
  const updateChangedHostKey = async () => {
    const item = testResult
    if (!item?.host_key_id || !window.confirm("Replace the trusted SSH host key with the received fingerprint?")) return
    setHostKeyActionBusy(true)
    try {
      await revokeSSHHostKey(item.host_key_id)
      await scanSSHHostKey(Number(deviceId), port)
      await trustSSHHostKey(item.host_key_id)
      toast.success("SSH host key updated. Retesting connection…")
      await retryAfterHostKeyAction()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Unable to update SSH host key")
    } finally { setHostKeyActionBusy(false) }
  }
  const connectTerminal = async () => {
    // A host-key trust/update action retries validation asynchronously. Do not
    // create a session from the previous HOST_KEY_UNKNOWN result while that
    // live device test is still running.
    if (testing || hostKeyActionBusy) return
    setTerminalError("")
    const existing = activeSessionForDevice(deviceId)
    if (existing) {
      notifyAlreadyConnected(existing)
      return
    }
    if (connectingRequest || connectingSessionsRef.current.size > 0) return
    // Test Connection is intentionally optional. Connect Terminal must use one
    // real session connection; never validate a saved credential with a
    // disposable SSH connection immediately before creating the session.
    const savedCredentialId = selectedCredential?.id
    if (deviceId === "" || (!selectedCredential && (!username.trim() || !password)) && !savedCredentialId) {
      setTerminalError("Select a device and enter username and password.")
      return
    }
    const deviceName = selected?.hostname ?? host
    toast.info(`Connecting to ${deviceName}...`)
    setConnectingRequest(true)
    connectingSessionsRef.current.add("pending")
    try {
      const sessionPayload = {
        device_id: deviceId,
        protocol,
        port,
        ...(savedCredentialId
          ? { credential_id: savedCredentialId }
          : { username: username.trim(), secret: password, remember_credential: remember }),
      }
      const session = await createRemoteAccessSession(sessionPayload)
      connectingSessionsRef.current.delete("pending")
      const next: TerminalTab = {
        sessionUuid: session.session_uuid,
        deviceId,
        ipAddress: host,
        hostname: selected?.hostname ?? host,
        protocol,
        port: session.port,
        deviceUsername: session.device_username,
        status: "connecting",
        startedAt: new Date(session.started_at).getTime(),
      }
      setTerminalTabs((tabs) => {
        const identity = next.ipAddress || String(next.deviceId)
        if (tabs.some((item) => item.sessionUuid === next.sessionUuid || item.deviceId === next.deviceId || (identity && item.ipAddress === identity))) {
          return tabs
        }
        return [...tabs, next]
      })
      setActiveSessionUuid(session.session_uuid)
      toast.info(`${session.protocol.toUpperCase()} session created; opening terminal...`)
    } catch (error) {
      connectingSessionsRef.current.delete("pending")
      setConnectingRequest(false)
      const message = error instanceof Error ? error.message : "unable to create session"
      const duplicate = message.match(/^DEVICE_ALREADY_CONNECTED:(ssh|telnet)$/i)
      if (duplicate) {
        toast.warning(`${deviceName} is already connected via ${duplicate[1].toUpperCase()}.`)
        return
      }
      toast.error(`Connection failed: ${message}`)
      setTerminalError(
        message || "Unable to create terminal session.",
      )
    } finally {
      connectingSessionsRef.current.delete("pending")
      setConnectingRequest(false)
    }
  }
  const disconnectTerminalImpl = async (sessionUuid: string) => {
    const tab = terminalTabs.find((item) => item.sessionUuid === sessionUuid)
    const socket = socketsRef.current.get(sessionUuid)
    if (socket && socket.readyState < WebSocket.CLOSING) {
      intentionalSocketCloseRef.current.add(sessionUuid)
      if (socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: "disconnect" }))
      }
      socket.close()
    }
    socketsRef.current.delete(sessionUuid)
    const terminalState = terminalsRef.current.get(sessionUuid)
    if (terminalState) {
      terminalState.input.dispose()
      terminalState.resize.dispose()
      terminalState.observer.disconnect()
      terminalState.terminal.dispose()
      terminalsRef.current.delete(sessionUuid)
    }
    if (tab) {
      setSessionHistory((history) => [{ ...tab, status: "disconnected", endedAt: Date.now(), reason: "User disconnected" }, ...history.filter((item) => item.sessionUuid !== sessionUuid)].slice(0, 50))
    }
    if (tab) {
      toast.info(`Disconnected from ${tab.hostname}`)
    }
    setTerminalTabs((tabs) =>
      tabs.filter((tab) => tab.sessionUuid !== sessionUuid),
    )
    setActiveSessionUuid((active) => active === sessionUuid ? null : active)
  }
  const disconnectTerminal = async (sessionUuid: string) => {
    if (disconnectingSessionsRef.current.has(sessionUuid)) return
    disconnectingSessionsRef.current.add(sessionUuid)
    try {
      await disconnectTerminalImpl(sessionUuid)
    } finally {
      disconnectingSessionsRef.current.delete(sessionUuid)
    }
  }
  const activeTab = terminalTabs.find(
    (tab) => tab.sessionUuid === activeSessionUuid,
  )
  useEffect(() => {
    if (!activeTab) return
    setDeviceId(activeTab.deviceId)
    setProtocol(activeTab.protocol)
    setPort(activeTab.port)
    setUsername(activeTab.deviceUsername ?? "")
    setCustomPort(activeTab.port !== (activeTab.protocol === "ssh" ? 22 : 23))
  }, [activeTab?.sessionUuid])
  const connecting = terminalTabs.some((item) => item.status === "connecting")
  const formLocked = Boolean(activeTab && (activeTab.status === "connected" || activeTab.status === "connecting"))
  const rememberHistory = (entry: TerminalTab) => {
    const next = [{ ...entry, endedAt: Date.now() }, ...sessionHistory.filter((item) => item.sessionUuid !== entry.sessionUuid)].slice(0, 50)
    setSessionHistory(next)
  }
  const startNewSession = () => {
    setActiveSessionUuid(null)
    setDeviceId("")
    setUsername("")
    setPassword("")
    setShowPassword(false)
    setProtocol("ssh")
    setPort(22)
    setCustomPort(false)
    setTestResult(null)
    setValidatedInput(null)
    setTestError("")
    setTerminalError("")
    setAddingDevice(false)
    setNewDeviceError("")
    setTab("Terminal")
  }
  const appendTerminalOutput = (sessionUuid: string, output: string) => {
    void sessionUuid
    void output
  }
  const terminalDiagnostic = (sessionUuid: string, event: string) => {
    const state = terminalsRef.current.get(sessionUuid)
    const host = terminalHostsRef.current.get(sessionUuid)
    if (!state || !host) return
    state.diagnosticSequence = (state.diagnosticSequence ?? 0) + 1
    const rect = host.getBoundingClientRect()
    console.debug("remote-terminal", {
      event, sessionUuid, sequence: state.diagnosticSequence, timestamp: Date.now(),
      containerWidth: rect.width, containerHeight: rect.height,
      cols: state.terminal.cols, rows: state.terminal.rows,
    })
  }
  const syncTerminalResize = (sessionUuid: string) => {
    const state = terminalsRef.current.get(sessionUuid)
    const socket = socketsRef.current.get(sessionUuid)
    if (!state || socket?.readyState !== WebSocket.OPEN) return
    const signature = `${state.terminal.cols}x${state.terminal.rows}`
    if (state.lastResize === signature) return
    state.lastResize = signature
    socket.send(JSON.stringify({ type: "resize", cols: state.terminal.cols, rows: state.terminal.rows }))
    console.debug("remote-terminal", { event: "resize-sent", sessionUuid, cols: state.terminal.cols, rows: state.terminal.rows })
  }
  const fitVisibleTerminal = (sessionUuid: string, force = false) => {
    if (visibleTerminalSessionRef.current !== sessionUuid) return
    const state = terminalsRef.current.get(sessionUuid)
    const host = terminalHostsRef.current.get(sessionUuid)
    if (!state || !host?.isConnected) return
    // Once the device has produced terminal output, keep the negotiated grid
    // stable. Re-fitting after route/visibility churn changes the PTY geometry
    // underneath ANSI cursor-positioned output and causes apparent gaps.
    if (state.firstOutput && !force) return
    const { width, height } = host.getBoundingClientRect()
    if (width <= 0 || height <= 0 || host.clientWidth <= 0 || host.clientHeight <= 0) return
    if (state.lastWidth !== undefined && state.lastHeight !== undefined
      && Math.abs(width - state.lastWidth) < 1 && Math.abs(height - state.lastHeight) < 1) return
    state.lastWidth = width
    state.lastHeight = height
    try {
      state.fit.fit()
      state.terminal.refresh(0, Math.max(0, state.terminal.rows - 1))
      const size = `${state.terminal.cols}x${state.terminal.rows}`
      if (state.firstOutput && state.lastPostOutputGeometry !== `${width}x${height}:${size}`) {
        state.lastPostOutputGeometry = `${width}x${height}:${size}`
        terminalDiagnostic(sessionUuid, "geometry-changed-after-first-output")
      }
      if (state.lastFitSize !== size) {
        state.lastFitSize = size
        console.debug("remote-terminal", { event: "terminal-fit", sessionUuid, width, height, cols: state.terminal.cols, rows: state.terminal.rows })
      }
      syncTerminalResize(sessionUuid)
    } catch {
      // xterm can reject a fit while its renderer is being initialized.
    }
  }
  useEffect(() => {
    if (!activeTab?.startedAt) return
    const interval = window.setInterval(() => setTimerNow(Date.now()), 1000)
    return () => window.clearInterval(interval)
  }, [activeTab?.startedAt])
  useEffect(() => {
    const handleFullscreenChange = () => {
      const isFullscreen = document.fullscreenElement === terminalPanelRef.current
      setTerminalFullscreen(isFullscreen)
      if (isFullscreen && activeSessionUuid) {
        requestAnimationFrame(() => fitVisibleTerminal(activeSessionUuid, true))
      }
    }
    document.addEventListener("fullscreenchange", handleFullscreenChange)
    return () => document.removeEventListener("fullscreenchange", handleFullscreenChange)
  }, [activeSessionUuid])
  useEffect(() => {
    if (!activeSessionUuid || tab !== "Terminal" || !terminalHostRef.current) return
    const sessionUuid = activeSessionUuid
    const sessionTab = terminalTabs.find((item) => item.sessionUuid === sessionUuid)
    if (!sessionTab) return
    const host = terminalHostsRef.current.get(sessionUuid) ?? terminalHostRef.current
    if (terminalsRef.current.has(sessionUuid)) {
      const frame = requestAnimationFrame(() => fitVisibleTerminal(sessionUuid))
      console.debug("remote-terminal", { event: "xterm-reused", sessionUuid, wsReused: socketsRef.current.get(sessionUuid)?.readyState === WebSocket.OPEN })
      return () => cancelAnimationFrame(frame)
    }
    const terminal = new Terminal({
      // Device adapters already deliver terminal line endings. Let xterm's
      // parser handle CR/LF as received; converting LF again can add apparent
      // gaps when a device sends CRLF/ANSI cursor sequences.
      convertEol: false,
      cursorBlink: true,
      fontFamily: "monospace",
      fontSize: 13,
      theme: { background: "#080d12", foreground: "#d9e3e8" },
    })
    const fit = new FitAddon()
    terminal.loadAddon(fit)
    terminal.open(host)
    const observer = new ResizeObserver(() => {
      const state = terminalsRef.current.get(sessionUuid)
      // xterm's own screen/scrollbar measurement can change the host's
      // fractional width after output starts. Fitting in response to that
      // self-change creates a cols feedback loop (114 -> 126). The terminal
      // is already fitted before the socket opens; later user/window layout
      // changes are handled by the visibility effect below.
      if (state?.firstOutput) return
      if (!state || state.fitFrame !== undefined) return
      state.fitFrame = requestAnimationFrame(() => {
        state.fitFrame = undefined
        fitVisibleTerminal(sessionUuid)
      })
    })
    terminalsRef.current.set(sessionUuid, { terminal, fit, input: { dispose: () => undefined }, resize: { dispose: () => undefined }, observer })
    observer.observe(host)
    terminalDiagnostic(sessionUuid, "terminal-created")
    terminalDiagnostic(sessionUuid, "xterm-opened")
    let socket: WebSocket | undefined
    const waitForInitialGeometry = () => new Promise<void>((resolve) => {
      const check = () => {
        const rect = host.getBoundingClientRect()
        if (rect.width > 0 && rect.height > 0 && host.clientWidth > 0 && host.clientHeight > 0) {
          terminalDiagnostic(sessionUuid, "terminal-container-ready")
          fitVisibleTerminal(sessionUuid)
          terminalDiagnostic(sessionUuid, "initial-fit")
          resolve()
          return
        }
        requestAnimationFrame(check)
      }
      requestAnimationFrame(check)
    })
    void waitForInitialGeometry().then(() => openRemoteAccessTerminal(sessionUuid))
      .then((opened) => {
        if (!terminalsRef.current.has(sessionUuid) || socketsRef.current.has(sessionUuid)) {
          opened.close()
          return
        }
        socket = opened
        socketsRef.current.set(sessionUuid, opened)
        opened.binaryType = "arraybuffer"
        terminalDiagnostic(sessionUuid, "ws-created")
        opened.onopen = () => {
          setTerminalTabs((tabs) =>
            tabs.map((tab) =>
              tab.sessionUuid === sessionUuid
              ? { ...tab, status: "connected", startedAt: tab.startedAt ?? Date.now() }
                : tab,
            ),
          )
          let toastAlreadyShown = connectionToastShownRef.current.has(sessionUuid)
          try {
            toastAlreadyShown = toastAlreadyShown || sessionStorage.getItem(connectionToastStorageKey(sessionUuid)) === "shown"
          } catch { /* storage may be unavailable */ }
          if (!toastAlreadyShown) {
            connectionToastShownRef.current.add(sessionUuid)
            try {
              sessionStorage.setItem(connectionToastStorageKey(sessionUuid), "shown")
            } catch { /* storage may be unavailable */ }
            toast.success(`${sessionTab.hostname} ${sessionTab.protocol.toUpperCase()} connection established`)
          }
          syncTerminalResize(sessionUuid)
          terminalDiagnostic(sessionUuid, "ws-open")
          terminalDiagnostic(sessionUuid, "initial-resize-sent")
        }
        let firstOutput = false
        let firstOutputWritten = false
        const writeOutput = (output: string) => {
          if (!firstOutput) {
            firstOutput = true
            const state = terminalsRef.current.get(sessionUuid)
            if (state) state.firstOutput = true
            terminalDiagnostic(sessionUuid, "first-output-received")
          }
          terminal.write(output)
          if (!firstOutputWritten) {
            firstOutputWritten = true
            terminalDiagnostic(sessionUuid, "first-output-written")
          }
        }
        opened.onmessage = (event) => {
          if (typeof event.data === "string") {
            try {
              const message = JSON.parse(event.data)
              if (message.type === "error") {
                const output = `\r\n${message.message}\r\n`
                writeOutput(output)
                appendTerminalOutput(sessionUuid, output)
              } else if (message.type === "output") {
                const output = message.data ?? ""
                writeOutput(output)
                appendTerminalOutput(sessionUuid, output)
              }
            } catch {
              writeOutput(event.data)
              appendTerminalOutput(sessionUuid, event.data)
            }
          } else {
            const output = new TextDecoder().decode(new Uint8Array(event.data))
            writeOutput(output)
            appendTerminalOutput(sessionUuid, output)
          }
        }
        opened.onerror = () => {
          toast.error("Connection failed: terminal WebSocket could not be opened")
          setTerminalError("Terminal connection failed.")
          setTerminalTabs((tabs) =>
            tabs.map((tab) =>
              tab.sessionUuid === sessionUuid
                ? { ...tab, status: "error" }
                : tab,
            ),
          )
        }
        opened.onclose = (event) => {
          socketsRef.current.delete(sessionUuid)
          if (intentionalSocketCloseRef.current.delete(sessionUuid)) return
          const unrecoverable = event.code === 4404
          const temporaryUnavailable = event.code === 1006 || event.code === 0
          const closedTab = terminalTabs.find((item) => item.sessionUuid === sessionUuid) ?? sessionTab
          if (temporaryUnavailable) {
            setTerminalTabs((tabs) => tabs.map((item) => item.sessionUuid === sessionUuid
              ? { ...item, status: "connected" }
              : item))
            setTerminalError("Remote Access service unavailable. The session was not ended.")
            toast.warning("Remote Access service unavailable")
            return
          }
          const terminalState = terminalsRef.current.get(sessionUuid)
          if (terminalState) {
            terminalState.input.dispose()
            terminalState.resize.dispose()
            terminalState.observer.disconnect()
            terminalState.terminal.clear()
            terminalState.terminal.reset()
            terminalState.terminal.dispose()
          } else {
            terminal.dispose()
          }
          terminalsRef.current.delete(sessionUuid)
          setTerminalTabs((tabs) => unrecoverable
            ? tabs.filter((item) => item.sessionUuid !== sessionUuid)
            : tabs.map((item) => item.sessionUuid === sessionUuid ? { ...item, status: "disconnected" } : item))
          setActiveSessionUuid((active) => active === sessionUuid ? null : active)
          setTerminalError(unrecoverable
            ? "Session ended because the Remote Access service restarted. Start a new session."
            : "Session disconnected. Start a new session to reconnect.")
          toast.info(unrecoverable
            ? "Remote Access session ended after service restart"
            : `Disconnected from ${closedTab.hostname}`)
          const activeIds = new Set(terminalTabs
            .filter((item) => item.sessionUuid !== sessionUuid && item.status === "connected")
            .map((item) => item.sessionUuid))
          void listRemoteAccessSessionHistory().then((history) => {
            const deviceById = new Map(devices.map((device) => [device.id, device]))
            setSessionHistory(history.map((item) => ({
              sessionUuid: item.session_uuid,
              deviceId: item.device_id,
              hostname: deviceById.get(item.device_id)?.hostname ?? String(item.device_id),
              protocol: item.protocol,
              port: item.port,
              status: item.status === "connected" && activeIds.has(item.session_uuid) ? "connected" : "disconnected",
              startedAt: new Date(item.started_at).getTime(),
              endedAt: item.ended_at ? new Date(item.ended_at).getTime() : undefined,
              reason: item.disconnect_reason ?? "—",
              sourceIp: item.source_ip ?? undefined,
              deviceIp: deviceById.get(item.device_id)?.ip_address ?? undefined,
              userName: item.user_name ?? undefined,
            } as SessionHistoryEntry)))
          }).catch(() => undefined)
        }
      })
      .catch((error) => {
        toast.error(`Connection failed: ${error instanceof Error ? error.message : "unable to open terminal"}`)
        setTerminalError(
          error instanceof Error ? error.message : "Unable to open terminal.",
        )
        setTerminalTabs((tabs) =>
          tabs.map((tab) =>
            tab.sessionUuid === sessionUuid
              ? { ...tab, status: "error" }
              : tab,
          ),
        )
      })
    const input = terminal.onData((data) => {
      if (socket?.readyState === WebSocket.OPEN)
        socket.send(JSON.stringify({ type: "input", data }))
    })
    const resize = terminal.onResize(({ cols, rows }) => {
      const state = terminalsRef.current.get(sessionUuid)
      if (!state) return
      if (state.lastResize === `${cols}x${rows}`) return
      if (socket?.readyState === WebSocket.OPEN) {
        state.lastResize = `${cols}x${rows}`
        socket.send(JSON.stringify({ type: "resize", cols, rows }))
        console.debug("remote-terminal", { event: "resize-sent", sessionUuid, cols, rows })
      }
    })
    const state = terminalsRef.current.get(sessionUuid)!
    state.input = input
    state.resize = resize
    return undefined
  }, [activeSessionUuid, tab])

  useEffect(() => () => {
    for (const [sessionUuid, state] of terminalsRef.current) {
      state.input.dispose()
      state.resize.dispose()
      state.observer.disconnect()
      state.terminal.dispose()
    }
    terminalsRef.current.clear()
    // Detach the browser transport without disconnecting the backend session.
    for (const [sessionUuid, socket] of socketsRef.current) {
      if (socket.readyState < WebSocket.CLOSING) {
        intentionalSocketCloseRef.current.add(sessionUuid)
        socket.close()
      }
    }
    socketsRef.current.clear()
  }, [])
  const Button = ({
    children,
    primary = false,
    ...props
  }: React.ButtonHTMLAttributes<HTMLButtonElement> & { primary?: boolean }) => (
    <button
      {...props}
      className={`rounded-lg px-4 py-2.5 font-display font-semibold text-sm transition hover:opacity-90 disabled:opacity-50 ${props.className ?? ""}`}
      style={{
        background: primary ? "var(--t-accent)" : "transparent",
        color: primary ? "#fff" : "var(--t-text)",
        border: `1px solid ${
          primary ? "var(--t-accent)" : "var(--t-border-alpha)"
        }`,
      }}
    >
      {children}
    </button>
  )
  return (
    <div className="p-4 md:p-6 space-y-5 min-h-full">
      <div className="flex flex-col xl:flex-row xl:items-end justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1
              className="font-display font-bold text-3xl md:text-4xl tracking-wide"
              style={{ color: "var(--t-accent)" }}
            >
              REMOTE ACCESS
            </h1>
            <span
              className="rounded-md px-3 py-1 text-xs font-mono font-bold"
              style={{
                color: "#12b8b0",
                background: "rgba(18,184,176,.12)",
                border: "1px solid rgba(18,184,176,.3)",
              }}
            >
              LIVE
            </span>
          </div>
          <p className="mt-2 text-sm" style={{ color: "var(--t-muted)" }}>
            Secure SSH and Telnet access to manage your network devices
          </p>
        </div>
        <div
          className="flex rounded-xl overflow-hidden"
          style={{ border: "1px solid var(--t-border-alpha)" }}
        >
          {["Terminal", "Active Sessions", "Session History"].map((item) => (
            <button
              key={item}
              onClick={() => setTab(item)}
              className="px-4 md:px-5 py-3 text-sm font-display"
              style={{
                color: tab === item ? "#fff" : "var(--t-muted)",
                background: tab === item ? "var(--t-accent)" : "transparent",
              }}
            >
              {item}
            </button>
          ))}
        </div>
      </div>
      {tab !== "Terminal" && (
        <GlassCard className="p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-display text-lg tracking-widest" style={{ color: "var(--t-accent)" }}>
              {tab === "Active Sessions" ? "ACTIVE SESSIONS" : "SESSION HISTORY"}
            </h2>
            <span className="text-xs" style={{ color: "var(--t-muted)" }}>
              {tab === "Active Sessions" ? terminalTabs.length : sessionHistory.length} session(s)
            </span>
          </div>
          {(tab === "Active Sessions" ? terminalTabs : sessionHistory).length === 0 ? (
            <div className="py-10 text-center text-sm" style={{ color: "var(--t-muted)" }}>No sessions available.</div>
          ) : tab === "Session History" ? (
            <div className="overflow-x-auto rounded-lg" style={{ border: "1px solid var(--t-border-alpha)" }}>
              <table className="w-full min-w-[980px] text-left text-xs">
                <thead style={{ background: "var(--t-table-header, var(--t-bg))", color: "var(--t-muted)" }}>
                  <tr>
                    {['Device', 'Target IP', 'Protocol', 'Connected', 'Duration', 'Disconnected', 'Reason'].map((heading) => (
                      <th key={heading} className="px-4 py-3 font-mono font-bold uppercase tracking-wide">{heading}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {sessionHistory.map((item) => (
                    <tr key={item.sessionUuid} style={{ borderTop: "1px solid var(--t-border-alpha)", color: "var(--t-text)" }}>
                      <td className="px-4 py-3 font-semibold">{item.hostname}</td>
                      <td className="px-4 py-3 font-mono">{item.deviceIp ?? "—"}</td>
                      <td className="px-4 py-3">{item.protocol.toUpperCase()} · {item.port}</td>
                      <td className="px-4 py-3 whitespace-nowrap">{formatSessionTime(item.startedAt)}</td>
                      <td className="px-4 py-3 whitespace-nowrap">{formatDuration(item.startedAt, item.endedAt)}</td>
                      <td className="px-4 py-3 whitespace-nowrap">{formatSessionTime(item.endedAt)}</td>
                      <td className="px-4 py-3">{friendlyDisconnectReason(item.reason)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="space-y-2">
              {(tab === "Active Sessions" ? terminalTabs : sessionHistory).map((item) => (
                <button key={item.sessionUuid} onClick={() => { if (tab === "Active Sessions") { setActiveSessionUuid(item.sessionUuid); setTab("Terminal") } }} className="w-full text-left rounded-lg px-4 py-3 flex flex-wrap gap-3 items-center" style={{ border: "1px solid var(--t-border-alpha)" }}>
                  <span className="font-semibold">{item.hostname}</span>
            <span className="text-xs" style={{ color: "var(--t-muted)" }}>{item.protocol.toUpperCase()} · port {item.port}</span>
                  <span className="ml-auto text-xs" style={{ color: item.status === "connected" ? "#22c55e" : "var(--t-muted)" }}>{item.status.toUpperCase()}</span>
                  {(tab === "Active Sessions" || item.status === "connected") && (
                    <span
                      role="button"
                      tabIndex={0}
                      className="rounded border border-red-400/40 px-2 py-1 text-xs text-red-400"
                      onClick={(event) => { event.stopPropagation(); void disconnectTerminal(item.sessionUuid) }}
                      onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); event.stopPropagation(); void disconnectTerminal(item.sessionUuid) } }}
                    >
                      Disconnect
                    </span>
                  )}
                </button>
              ))}
            </div>
          )}
        </GlassCard>
      )}
      <div ref={terminalPanelRef} className={`${tab === "Terminal" ? "" : "hidden "}remote-access-workspace${terminalFullscreen && !connectionPanelVisible ? " form-hidden" : ""} grid min-w-0 grid-cols-1 xl:grid-cols-[minmax(330px,38%)_1fr] gap-5`}>
        <GlassCard className={`p-5 space-y-5${terminalFullscreen && !connectionPanelVisible ? " connection-panel-hidden" : ""}`}>
          <div className="flex items-center gap-2">
            <span style={{ color: "var(--t-accent)" }}>⌁</span>
            <h2
              className="font-display text-lg tracking-widest"
              style={{ color: "var(--t-accent)" }}
            >
              CONNECTION
            </h2>
          </div>
          <div>
            <div className="flex justify-between mb-2">
              <label className="text-xs font-display">Select Device</label>
              <button className="text-xs" style={{ color: "var(--t-accent)" }}>
                View Device Details
              </button>
            </div>
            <select
              value={addingDevice ? "add" : deviceId}
              disabled={formLocked}
              onChange={(event) => {
                if (event.target.value === "add") {
                  setDeviceId("")
                  setNewDeviceError("")
                  setAddingDevice(true)
                  return
                }
                setAddingDevice(false)
                setDeviceId(event.target.value ? Number(event.target.value) : "")
              }}
              className="w-full rounded-lg px-3 py-3 text-sm"
              style={inputStyle}
            >
              <option value="">Select a device</option>
              {devices.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.hostname} ({d.ip_address})
                </option>
              ))}
              <option value="add">+ Add New Remote Device</option>
            </select>
          </div>
          {addingDevice && (
            <div className="space-y-3 rounded-lg p-4" style={{ border: "1px solid var(--t-border-alpha)" }}>
              <div className="flex items-center justify-between gap-3">
                <h3 className="font-display text-sm" style={{ color: "var(--t-accent)" }}>ADD REMOTE DEVICE</h3>
                {devices.length > 0 && (
                  <button type="button" className="text-xs" style={{ color: "var(--t-muted)" }} onClick={() => setAddingDevice(false)}>
                    Cancel
                  </button>
                )}
              </div>
              <label className="block text-xs font-display">
                Device name
                <input
                  autoFocus
                  value={newDevice.hostname}
                  onChange={(event) => setNewDevice((current) => ({ ...current, hostname: event.target.value }))}
                  placeholder="Core-switch"
                  className="mt-2 w-full rounded-lg px-3 py-3 text-sm"
                  style={inputStyle}
                />
              </label>
              <label className="block text-xs font-display">
                IP address
                <input
                  value={newDevice.ip_address}
                  onChange={(event) => setNewDevice((current) => ({ ...current, ip_address: event.target.value }))}
                  placeholder="192.0.2.10"
                  inputMode="decimal"
                  className="mt-2 w-full rounded-lg px-3 py-3 text-sm"
                  style={inputStyle}
                />
              </label>
              {newDeviceError && <p role="alert" className="text-sm text-red-400">{newDeviceError}</p>}
              <Button primary disabled={addingDeviceBusy} onClick={() => void saveNewDevice()}>
                {addingDeviceBusy ? "Adding device..." : "Add device"}
              </Button>
            </div>
          )}
          {selected && <>
          <div>
            <label className="block mb-2 text-xs font-display">Protocol</label>
            <div className="grid grid-cols-2 gap-3">
              {(["ssh", "telnet"] as const).map((value) => (
                <button
                  key={value}
                  disabled={formLocked}
                  onClick={() => changeProtocol(value)}
                  className="rounded-lg p-3 text-left"
                  style={{
                    ...inputStyle,
                    borderColor:
                      protocol === value
                        ? "var(--t-accent)"
                        : "var(--t-border-alpha)",
                  }}
                >
                  <div className="font-display font-semibold">
                    {value.toUpperCase()}
                  </div>
                  <div
                    className="text-xs mt-1"
                    style={{ color: "var(--t-muted)" }}
                  >
                    {value === "ssh"
                      ? "Secure (Encrypted)"
                      : "Legacy (Unencrypted)"}
                    <br />
                    Default Port: {value === "ssh" ? 22 : 23}
                  </div>
                </button>
              ))}
            </div>
          </div>
          <div className="grid grid-cols-[1fr_100px] gap-3">
            <label className="text-xs font-display">
              Host / IP Address
              <input
                value={host}
                readOnly
                className="mt-2 w-full rounded-lg px-3 py-3 text-sm"
                style={inputStyle}
              />
            </label>
            <label className="text-xs font-display">
              Port
              <input
                value={port}
                disabled={formLocked}
                onChange={(e) => {
                  setPort(Number(e.target.value))
                  setCustomPort(true)
                }}
                type="number"
                min="1"
                max="65535"
                className="mt-2 w-full rounded-lg px-3 py-3 text-sm"
                style={inputStyle}
              />
            </label>
          </div>
          <label className="block text-xs font-display">
            Username
            <input
              value={username}
              disabled={formLocked || Boolean(selectedCredential)}
              onChange={(e) => setUsername(e.target.value)}
              className="mt-2 w-full rounded-lg px-3 py-3 text-sm"
              style={inputStyle}
            />
          </label>
          <label className="block text-xs font-display">
            Password
            <div className="relative mt-2">
              <input
                type={showPassword ? "text" : "password"}
                value={password}
                disabled={formLocked || Boolean(selectedCredential)}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Enter password"
                className="w-full rounded-lg px-3 py-3 pr-12 text-sm"
                style={inputStyle}
              />
              <button
                type="button"
                disabled={formLocked || Boolean(selectedCredential)}
                onClick={() => setShowPassword((v) => !v)}
                className="absolute right-3 top-2.5 text-lg"
              >
                ◉
              </button>
            </div>
          </label>
          <label className="flex items-center gap-2 text-xs">
            <input
              type="checkbox"
              checked={remember}
              disabled={formLocked || Boolean(selectedCredential)}
              onChange={(e) => setRemember(e.target.checked)}
            />{" "}
            Remember credential for this device
          </label>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <Button disabled={testing || connectingRequest || formLocked} onClick={() => void runTest()}>
              ↗ &nbsp; {testing ? "Testing..." : "Test Connection"}
            </Button>
            <Button primary disabled={testing || connecting || connectingRequest || hostKeyActionBusy || formLocked} onClick={() => void connectTerminal()}>
              ▶ &nbsp; {connecting || connectingRequest ? "Connecting..." : "Connect Terminal →"}
            </Button>
          </div>
          {(testing || connectingRequest) && (
            <div role="status" aria-live="polite" className="flex items-center gap-2 text-xs" style={{ color: "var(--t-accent)" }}>
              <span className="inline-block h-2 w-2 animate-pulse rounded-full" style={{ background: "var(--t-accent)" }} />
              {testing
                ? `Checking ${protocol.toUpperCase()} credentials for ${selected?.hostname ?? host}...`
                : `Opening ${protocol.toUpperCase()} session to ${selected?.hostname ?? host}...`}
            </div>
          )}
          {testResult?.success && (
            <div
              className="rounded-lg p-3 text-sm"
              style={{
                color: "#119447",
                background: "rgba(17,148,71,.1)",
                border: "1px solid rgba(17,148,71,.25)",
              }}
            >
              ● &nbsp; <strong>Connection Successful</strong>
              <div className="text-xs ml-5">
                {protocol.toUpperCase()} connection verified successfully
                {testResult.latency != null
                  ? ` (${testResult.latency} ms)`
                  : ""}
              </div>
            </div>
          )}
          {testResult && !testResult.success && (
            <div
              className="rounded-lg p-3 text-sm"
              style={{
                color: "#dc2626",
                background: "rgba(220,38,38,.1)",
                border: "1px solid rgba(220,38,38,.25)",
              }}
            >
              ● &nbsp;{" "}
              <strong>
                {testResult.error_code === "SSH_AUTH_FAILED"
                  ? "Authentication Failed"
                  : testResult.error_code === "TCP_TIMEOUT"
                    ? "Timeout"
                    : testResult.error_code === "TCP_REFUSED"
                      ? "Connection Refused"
                      : "Connection Failed"}
              </strong>
              <div className="text-xs ml-5">
                {testResult.error_code === "SSH_AUTH_FAILED"
                  ? "The username/password or saved credential was rejected by the device. Credential management is available from the existing credential page."
                  : testResult.message || "The connection could not be established."}
              </div>
            </div>
          )}
          {testError && (
            <div
              className="rounded-lg p-3 text-sm"
              style={{
                color: "#dc2626",
                background: "rgba(220,38,38,.1)",
                border: "1px solid rgba(220,38,38,.25)",
              }}
            >
              ● &nbsp; {testError}
            </div>
          )}
          {hostKeyDialog && testResult && (
            <div
              className="fixed inset-0 z-50 flex items-center justify-center p-4"
              role="dialog"
              aria-modal="true"
              style={{ background: "var(--t-overlay, rgba(0,0,0,.62))" }}
            >
              <div
                className="w-full max-w-lg rounded-xl p-5 space-y-4 shadow-2xl"
                style={{
                  background: "var(--t-card, #081228)",
                  color: "var(--t-text)",
                  border: "1px solid var(--t-border-alpha)",
                  boxShadow: "0 20px 60px var(--t-shadow, rgba(0,0,0,.35))",
                }}
              >
                <div>
                  <h2 className="font-display text-xl tracking-wide" style={{ color: "var(--t-accent)" }}>
                    {hostKeyDialog === "unknown" ? "New SSH Device Identity" : "SSH Host Key Changed"}
                  </h2>
                  <p className="mt-2 text-sm" style={{ color: "var(--t-muted)" }}>
                    {hostKeyDialog === "unknown"
                      ? "SSH service is available, but this device has not been trusted by NMS yet."
                      : "The device identity does not match the trusted host key."}
                  </p>
                </div>
                <div className="rounded-lg p-3 space-y-2 text-xs font-mono" style={{ background: "var(--t-bg)", color: "var(--t-text)", border: "1px solid var(--t-border-alpha)" }}>
                  <div>Device/IP: {selected?.hostname ?? host} / {host}</div>
                  <div>Port: {testResult.port ?? port}</div>
                  <div>Key type: {testResult.key_type ?? "—"}</div>
                  {hostKeyDialog === "unknown"
                    ? <div className="break-all">Fingerprint: {testResult.fingerprint ?? "—"}</div>
                    : <>
                      <div className="break-all">Stored fingerprint: {testResult.stored_fingerprint ?? "—"}</div>
                      <div className="break-all">Received fingerprint: {testResult.received_fingerprint ?? "—"}</div>
                    </>}
                </div>
                <div className="flex justify-end gap-2">
                  <Button disabled={hostKeyActionBusy} onClick={() => setHostKeyDialog(null)}>Cancel</Button>
                  {hostKeyDialog === "unknown"
                    ? <Button primary disabled={hostKeyActionBusy} onClick={() => void trustUnknownHostKey()}>{hostKeyActionBusy ? "Trusting…" : "Trust & Connect"}</Button>
                    : <Button primary disabled={hostKeyActionBusy} onClick={() => void updateChangedHostKey()}>{hostKeyActionBusy ? "Updating…" : "Review & Update"}</Button>}
                </div>
              </div>
            </div>
          )}
          </>}
        </GlassCard>
        <GlassCard className="p-4 md:p-5 min-h-[570px] flex flex-col min-w-0">
          <div className="flex items-center gap-2 mb-4">
            <span style={{ color: "var(--t-accent)" }}>⌁</span>
            <h2
              className="font-display text-lg tracking-widest"
              style={{ color: "var(--t-accent)" }}
            >
              TERMINAL
            </h2>
            <div className="ml-auto flex gap-2">
              {terminalFullscreen && (
              <button
                title={terminalFullscreen ? (connectionPanelVisible ? "Hide connection form" : "Show connection form") : "Connection form is available beside terminal"}
                aria-label={terminalFullscreen ? (connectionPanelVisible ? "Hide connection form" : "Show connection form") : "Connection form is available beside terminal"}
                onClick={() => { if (terminalFullscreen) setConnectionPanelVisible((visible) => !visible) }}
                disabled={!terminalFullscreen}
                className="inline-flex h-9 w-9 items-center justify-center rounded-lg transition hover:bg-white/[.08] disabled:cursor-not-allowed disabled:opacity-40"
                style={{ border: "1px solid var(--t-border-alpha)" }}
              >
                <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.8"><rect x="3" y="4" width="18" height="16" rx="2" /><path d={connectionPanelVisible ? "M9 4v16M9 8h12M9 12h12M9 16h12" : "M7 8h10M7 12h10M7 16h10"} /></svg>
              </button>
              )}
              <button
                title={terminalFullscreen ? "Exit fullscreen" : "Open terminal workspace fullscreen"}
                aria-label={terminalFullscreen ? "Exit fullscreen" : "Open terminal workspace fullscreen"}
                onClick={() => void (terminalFullscreen ? document.exitFullscreen?.() : terminalPanelRef.current?.requestFullscreen?.())}
                className="inline-flex h-9 w-9 items-center justify-center rounded-lg transition hover:bg-white/[.08]"
                style={{ border: "1px solid var(--t-border-alpha)" }}
              >
                {terminalFullscreen ? (
                  <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M9 4H4v5M4 4l6 6M15 4h5v5M20 4l-6 6M9 20H4v-5M4 20l6-6M15 20h5v-5M20 20l-6-6" /></svg>
                ) : (
                  <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M8 3H3v5M3 3l6 6M16 3h5v5M21 3l-6 6M8 21H3v-5M3 21l6-6M16 21h5v-5M21 21l-6-6" /></svg>
                )}
              </button>
            </div>
          </div>
          <div className="flex gap-2 mb-3 overflow-auto">
            {terminalTabs.map((tabItem) => (
              <button
                key={tabItem.sessionUuid}
                onClick={() => setActiveSessionUuid(tabItem.sessionUuid)}
                className="rounded-t-lg px-4 py-2 text-sm whitespace-nowrap"
                style={{
                  background:
                    activeSessionUuid === tabItem.sessionUuid
                      ? "var(--t-border-light)"
                      : "transparent",
                  border: "1px solid var(--t-border-alpha)",
                }}
              >
                ● &nbsp; {tabItem.hostname} &nbsp;{" "}
                <span
                  onClick={(event) => {
                    event.stopPropagation()
                    void disconnectTerminal(tabItem.sessionUuid)
                  }}
                >
                  ×
                </span>
              </button>
            ))}
            <button
              onClick={startNewSession}
              className="rounded-lg px-4 py-2 text-sm whitespace-nowrap"
              style={{
                border: "1px solid var(--t-border-alpha)",
                color: "var(--t-muted)",
              }}
            >
              ＋ New Session
            </button>
          </div>
          <div
            className="rounded-t-xl min-w-0 overflow-hidden flex-1 flex flex-col"
            style={{ background: "#080d12", color: "#d9e3e8", height: "clamp(390px, 62vh, 720px)", minHeight: 390, flex: "1 1 auto" }}
          >
            {selected && <div
              className="px-4 py-3 flex flex-wrap items-center gap-3 text-xs"
              style={{ background: "#152232" }}
            >
              <span>
                ▣ &nbsp;{" "}
                {activeTab?.hostname ?? selected?.hostname ?? "No device selected"}
              </span>
              <span>|</span>
              <span>{activeTab ? (devices.find((d) => d.id === activeTab.deviceId)?.ip_address ?? host) : host}</span>
              <span>|</span>
              <span>
                {(activeTab?.protocol ?? protocol).toUpperCase()} : {activeTab?.port ?? port}
              </span>
              <span>|</span>
              <span>User: {formLocked ? "session locked" : (username || "—")}</span>
              <span
                className="ml-auto rounded-full px-3 py-1"
                style={{
                  color: "#4ade80",
                  border: "1px solid #15803d",
                  background: "rgba(22,163,74,.12)",
                }}
              >
                ● {activeTab?.status?.toUpperCase() ?? "NOT CONNECTED"}
              </span>
              <span>
                {activeTab?.startedAt
                  ? `${String(Math.floor((timerNow - activeTab.startedAt) / 60000)).padStart(2, "0")}:${String(Math.floor((timerNow - activeTab.startedAt) / 1000) % 60).padStart(2, "0")}`
                  : "--:--"}
              </span>
              {activeTab && (activeTab.status === "connected" || activeTab.status === "connecting") && (
                <Button
                  primary
                  onClick={() => void disconnectTerminal(activeTab.sessionUuid)}
                  className="!py-1.5 !px-3 !text-xs"
                >
                  ↗ Disconnect
                </Button>
              )}
            </div>}
            <div className="p-2 min-w-0 flex-1 overflow-hidden" style={{ minHeight: 0 }}>
              {terminalTabs.map((tabItem) => (
                <div
                  key={tabItem.sessionUuid}
                  ref={(node) => {
                    if (node) terminalHostsRef.current.set(tabItem.sessionUuid, node)
                    else terminalHostsRef.current.delete(tabItem.sessionUuid)
                  }}
                  className={activeSessionUuid === tabItem.sessionUuid ? "remote-terminal-host h-full min-w-0 overflow-hidden" : "hidden"}
                  style={{ minHeight: 390, width: "100%", maxWidth: "100%" }}
                />
              ))}
              <div ref={terminalHostRef} className={activeTab ? "hidden" : "remote-terminal-host h-full min-w-0 overflow-hidden"}>
              {!activeTab && (
                <div className="h-full flex items-center justify-center font-mono text-xs" style={{ color: "#8899bb" }}>
                  Connect to a device to start a terminal session
                </div>
              )}
              </div>
            </div>
          </div>
          {terminalError && (
            <div
              className="rounded-lg p-3 mt-3 text-sm"
              style={{
                color: "#dc2626",
                background: "rgba(220,38,38,.1)",
                border: "1px solid rgba(220,38,38,.25)",
              }}
            >
              {terminalError}
            </div>
          )}
          {selected && <div
            className="flex flex-wrap gap-x-5 gap-y-2 px-4 py-3 text-xs font-mono"
            style={{
              color: "var(--t-muted)",
              border: "1px solid var(--t-border-alpha)",
              borderTop: 0,
            }}
          >
            <span>⌁ &nbsp; {protocol.toUpperCase()}</span>
            <span>UTF-8</span>
            <span>120 × 34</span>
                <span>{activeTab ? `${activeTab.protocol.toUpperCase()} terminal` : "No active terminal"}</span>
            <span>{activeTab ? host : "—"}</span>
            <span style={{ color: activeTab?.status === "connected" ? "#22c55e" : "#8899bb" }}>● {activeTab?.status === "connected" ? "LIVE" : "—"}</span>
            <span className="ml-auto">Ctrl + C to interrupt</span>
          </div>}
        </GlassCard>
      </div>
    </div>
  )
}
