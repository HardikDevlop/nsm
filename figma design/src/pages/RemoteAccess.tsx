import { useEffect, useMemo, useRef, useState } from "react"
import { Terminal } from "@xterm/xterm"
import { FitAddon } from "@xterm/addon-fit"
import "@xterm/xterm/css/xterm.css"
import GlassCard from "../components/GlassCard"
import {
  createRemoteAccessSession,
  deleteRemoteAccessSession,
  listDeviceOptions,
  listRemoteAccessSessions,
  listRemoteAccessSessionHistory,
  openRemoteAccessTerminal,
  testRemoteAccess,
  type DeviceOptionRecord,
  type RemoteAccessTestResponse,
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
  type SessionHistoryEntry = TerminalTab & { endedAt?: number; reason?: string; userId?: number }
  const [devices, setDevices] = useState<DeviceOptionRecord[]>([])
  const [deviceId, setDeviceId] = useState<number | "">("")
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
  const [terminalTabs, setTerminalTabs] = useState<TerminalTab[]>([])
  const [activeSessionUuid, setActiveSessionUuid] = useState<string | null>(
    null,
  )
  const [terminalError, setTerminalError] = useState("")
  const [timerNow, setTimerNow] = useState(Date.now())
  const [sessionHistory, setSessionHistory] = useState<SessionHistoryEntry[]>([])
  const terminalHostRef = useRef<HTMLDivElement>(null)
  const terminalPanelRef = useRef<HTMLDivElement>(null)
  const terminalRef = useRef<Terminal | null>(null)
  const fitRef = useRef<FitAddon | null>(null)
  const terminalHostsRef = useRef(new Map<string, HTMLDivElement>())
  const terminalsRef = useRef(new Map<string, { terminal: Terminal; fit: FitAddon; input: { dispose: () => void }; resize: { dispose: () => void }; observer: ResizeObserver }>())
  const socketsRef = useRef(new Map<string, WebSocket>())
  const connectingSessionsRef = useRef(new Set<string>())
  // Keep the connection form across route unmounts. The device session itself
  // is owned by the backend and is restored from the active-sessions API.
  useEffect(() => {
    try {
      const saved = JSON.parse(localStorage.getItem(remoteAccessDraftKey) ?? "null") as Partial<{
        deviceId: number | ""; protocol: "ssh" | "telnet"; username: string;
        remember: boolean; port: number; customPort: boolean;
      }> | null
      if (!saved) return
      if (saved.deviceId !== undefined) setDeviceId(saved.deviceId)
      if (saved.protocol) setProtocol(saved.protocol)
      if (saved.username !== undefined) setUsername(saved.username)
      if (saved.remember !== undefined) setRemember(saved.remember)
      if (saved.port !== undefined) setPort(saved.port)
      if (saved.customPort !== undefined) setCustomPort(saved.customPort)
    } catch { /* ignore malformed browser storage */ }
  }, [])
  useEffect(() => {
    try {
      localStorage.setItem(remoteAccessDraftKey, JSON.stringify({
        deviceId, protocol, username, remember, port, customPort,
      }))
    } catch { /* storage may be unavailable */ }
  }, [deviceId, protocol, username, remember, port, customPort])
  useEffect(() => {
    void listDeviceOptions({ limit: 500 })
      .then((items) => {
        setDevices(items)
      })
      .catch(() => undefined)
  }, [])
  useEffect(() => {
    void listRemoteAccessSessions().then((sessions) => {
      const restored = sessions.map((session) => ({
        sessionUuid: session.session_uuid, deviceId: session.device_id,
        ipAddress: devices.find((d) => d.id === session.device_id)?.ip_address,
        hostname: devices.find((d) => d.id === session.device_id)?.hostname ?? String(session.device_id),
        protocol: session.protocol, port: session.port, status: session.status === "connected" ? "connected" : "connecting",
        deviceUsername: session.device_username,
        startedAt: new Date(session.started_at).getTime(),
      } as TerminalTab))
      // The API can be observed more than once while the device options load.
      // Keep one tab per backend session and one live terminal per device/IP.
      const unique = restored.filter((session, index, all) => {
        const identity = session.ipAddress || String(session.deviceId)
        return all.findIndex((candidate) =>
          candidate.sessionUuid === session.sessionUuid ||
          (candidate.ipAddress || String(candidate.deviceId)) === identity,
        ) === index
      })
      setTerminalTabs(unique)
      // Route/tab remounts restore the backend session list, but the local
      // active-tab pointer is lost. Re-select the live session so the terminal
      // does not open as a blank screen after returning to this page.
      setActiveSessionUuid((active) => active ?? (
        unique.find((session) => session.status === "connected")?.sessionUuid ??
        unique[0]?.sessionUuid ??
        null
      ))
    }).catch(() => undefined)
  }, [devices])
  useEffect(() => {
    void Promise.all([listRemoteAccessSessionHistory(), listRemoteAccessSessions()]).then(([sessions, activeSessions]) => {
      const activeIds = new Set(activeSessions.map((session) => session.session_uuid))
      setSessionHistory(sessions.map((session) => ({
        sessionUuid: session.session_uuid, deviceId: session.device_id,
        hostname: devices.find((d) => d.id === session.device_id)?.hostname ?? String(session.device_id),
        protocol: session.protocol, port: session.port,
        // A history row is connected only while it is also returned by the
        // active-session endpoint. This prevents stale CONNECTED rows after a
        // lost browser/backend owner.
        status: session.status === "connected" && activeIds.has(session.session_uuid) ? "connected" : "disconnected",
        startedAt: new Date(session.started_at).getTime(), endedAt: session.ended_at ? new Date(session.ended_at).getTime() : undefined,
        reason: session.disconnect_reason ?? "—", userId: session.user_id,
      } as SessionHistoryEntry)))
    }).catch(() => undefined)
  }, [devices])
  const selected = useMemo(
    () => devices.find((d) => d.id === deviceId),
    [devices, deviceId],
  )
  const host = selected?.ip_address ?? ""
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
  useEffect(() => {
    if (validatedInput !== null) {
      setTestResult(null)
      setValidatedInput(null)
    }
  }, [deviceId, protocol, port, username, password])
  const runTest = async () => {
    setTestResult(null)
    setTestError("")
    if (deviceId === "" || !username.trim() || !password) {
      setTestError("Select a device and enter username and password.")
      return
    }
    setTesting(true)
    try {
      const result = await testRemoteAccess({
          device_id: deviceId,
          protocol,
          port,
          username: username.trim(),
          secret: password,
          auth_type: "password",
          remember_credential: remember,
      })
        console.info("[remote-access] test result", {
          success: result.success, host: result.host, protocol: result.protocol,
          port: result.port, credential_id: result.credential_id,
          stage: result.stage, code: result.error_code,
          message: result.message,
        })
      setTestResult(result)
      setValidatedInput(result.success ? inputFingerprint() : null)
    } catch (error) {
      setTestError(
        error instanceof Error ? error.message : "Connection test failed.",
      )
    } finally {
      setTesting(false)
    }
  }
  const connectTerminal = async () => {
    setTerminalError("")
    const validationMatches = testResult?.success === true && validatedInput === inputFingerprint()
    const savedCredentialId = validationMatches && testResult.credential_id
      ? testResult.credential_id
      : undefined
    if (!validationMatches) {
      setTerminalError("Run a successful connection test before opening a terminal.")
      return
    }
    if (terminalTabs.some((tab) => tab.status === "connecting") || connectingSessionsRef.current.size > 0) return
    const deviceName = selected?.hostname ?? host
    const existing = terminalTabs.find((tab) =>
      tab.deviceId === deviceId || (host && tab.ipAddress === host),
    )
    if (existing) {
      setActiveSessionUuid(existing.sessionUuid)
      setTab("Terminal")
      setTerminalError(`A terminal is already open for ${existing.hostname} (${existing.ipAddress ?? host}).`)
      return
    }
    toast.info(`Connecting to ${deviceName}...`)
    connectingSessionsRef.current.add("pending")
    try {
      const sessionPayload = {
        device_id: deviceId,
        protocol,
        port,
        ...(savedCredentialId
          ? { credential_id: savedCredentialId }
          : { username: username.trim(), secret: password }),
      }
      const session = await createRemoteAccessSession(sessionPayload)
      console.info("[terminal] session-created")
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
      toast.info("SSH session created; opening terminal...")
    } catch (error) {
      connectingSessionsRef.current.delete("pending")
      toast.error(`Connection failed: ${error instanceof Error ? error.message : "unable to create session"}`)
      setTerminalError(
        error instanceof Error
          ? error.message
          : "Unable to create terminal session.",
      )
    }
  }
  const disconnectTerminal = async (sessionUuid: string) => {
    const tab = terminalTabs.find((item) => item.sessionUuid === sessionUuid)
    const socket = socketsRef.current.get(sessionUuid)
    if (socket && socket.readyState < WebSocket.CLOSING) {
      socket.send(JSON.stringify({ type: "disconnect" }))
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
      console.info("[terminal] xterm-disposed", sessionUuid)
    }
    try {
      const ended = await deleteRemoteAccessSession(sessionUuid)
      if (ended) {
        setSessionHistory((history) => [{
          ...(tab ?? { sessionUuid, deviceId: ended.device_id, hostname: String(ended.device_id), protocol: ended.protocol, port: ended.port, status: ended.status, startedAt: new Date(ended.started_at).getTime() }),
          status: "disconnected",
          endedAt: ended.ended_at ? new Date(ended.ended_at).getTime() : Date.now(),
          reason: ended.disconnect_reason ?? "—",
          userId: ended.user_id,
        } as SessionHistoryEntry, ...history.filter((item) => item.sessionUuid !== sessionUuid)].slice(0, 50))
      } else if (tab) {
        rememberHistory(tab)
      }
    } catch {
      /* the WebSocket may already have disconnected the session */
    }
    if (tab) {
      toast.info(`Disconnected from ${tab.hostname}`)
    }
    setTerminalTabs((tabs) =>
      tabs.filter((tab) => tab.sessionUuid !== sessionUuid),
    )
    setActiveSessionUuid((active) => active === sessionUuid ? null : active)
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
    // Keep the connection form/draft intact when switching tabs or returning
    // from another route. Only session-specific validation should be reset.
    setTestResult(null)
    setValidatedInput(null)
    setTestError("")
    setTerminalError("")
    setTab("Terminal")
  }
  const appendTerminalOutput = (sessionUuid: string, output: string) => {
    void sessionUuid
    void output
  }
  useEffect(() => {
    if (!activeTab?.startedAt) return
    const interval = window.setInterval(() => setTimerNow(Date.now()), 1000)
    return () => window.clearInterval(interval)
  }, [activeTab?.startedAt])
  useEffect(() => {
    if (!activeSessionUuid || !terminalHostRef.current) return
    if (terminalsRef.current.has(activeSessionUuid)) return
    const sessionUuid = activeSessionUuid
    const tab = terminalTabs.find((item) => item.sessionUuid === sessionUuid)
    if (!tab) return
    const host = terminalHostsRef.current.get(sessionUuid) ?? terminalHostRef.current
    const terminal = new Terminal({
      convertEol: true,
      cursorBlink: true,
      fontFamily: "monospace",
      fontSize: 13,
      theme: { background: "#080d12", foreground: "#d9e3e8" },
    })
    const fit = new FitAddon()
    terminal.loadAddon(fit)
    terminal.open(host)
    fit.fit()
    terminalRef.current = terminal
    fitRef.current = fit
    terminalsRef.current.set(sessionUuid, { terminal, fit, input: { dispose: () => undefined }, resize: { dispose: () => undefined }, observer: new ResizeObserver(() => fit.fit()) })
    console.info("[terminal] xterm-created", sessionUuid)
    let socket: WebSocket | undefined
    void openRemoteAccessTerminal(sessionUuid)
      .then((opened) => {
        if (!terminalsRef.current.has(sessionUuid) || socketsRef.current.has(sessionUuid)) {
          opened.close()
          return
        }
        socket = opened
        socketsRef.current.set(sessionUuid, opened)
        opened.binaryType = "arraybuffer"
        opened.onopen = () => {
          console.info("[terminal] ws-open", sessionUuid)
          setTerminalTabs((tabs) =>
            tabs.map((tab) =>
              tab.sessionUuid === sessionUuid
              ? { ...tab, status: "connected", startedAt: tab.startedAt ?? Date.now() }
                : tab,
            ),
          )
          toast.success(`${tab.hostname} ${tab.protocol.toUpperCase()} connection established`)
          opened.send(
            JSON.stringify({
              type: "resize",
              cols: terminal.cols,
              rows: terminal.rows,
            }),
          )
        }
        opened.onmessage = (event) => {
          if (typeof event.data === "string") {
            try {
              const message = JSON.parse(event.data)
              if (message.type === "error") {
                const output = `\r\n${message.message}\r\n`
                terminal.write(output)
                appendTerminalOutput(sessionUuid, output)
              } else if (message.type === "output") {
                const output = message.data ?? ""
                terminal.write(output)
                appendTerminalOutput(sessionUuid, output)
              }
            } catch {
              terminal.write(event.data)
              appendTerminalOutput(sessionUuid, event.data)
            }
          } else {
            const output = new TextDecoder().decode(new Uint8Array(event.data))
            terminal.write(output)
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
        opened.onclose = () => {
          socketsRef.current.delete(sessionUuid)
          console.info("[terminal] ws-close", sessionUuid)
          const closedTab = terminalTabs.find((item) => item.sessionUuid === sessionUuid) ?? tab
          terminal.clear()
          terminal.reset()
          terminal.dispose()
          terminalsRef.current.delete(sessionUuid)
          setTerminalTabs((tabs) => tabs.map((item) => item.sessionUuid === sessionUuid ? { ...item, status: "disconnected" } : item))
          setActiveSessionUuid((active) => active === sessionUuid ? null : active)
          setTerminalError("Session disconnected. Start a new session to reconnect.")
          toast.info(`Disconnected from ${closedTab.hostname}`)
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
      if (socket?.readyState === WebSocket.OPEN)
        socket.send(JSON.stringify({ type: "resize", cols, rows }))
    })
    const observer = terminalsRef.current.get(sessionUuid)!.observer
    observer.observe(host)
    const state = terminalsRef.current.get(sessionUuid)!
    state.input = input
    state.resize = resize
    return undefined
  }, [activeSessionUuid])

  useEffect(() => () => {
    for (const [sessionUuid, state] of terminalsRef.current) {
      state.input.dispose()
      state.resize.dispose()
      state.observer.disconnect()
      state.terminal.dispose()
      console.info("[terminal] xterm-disposed", sessionUuid)
    }
    terminalsRef.current.clear()
    // Detach the browser transport without disconnecting the backend session.
    for (const socket of socketsRef.current.values()) {
      if (socket.readyState < WebSocket.CLOSING) socket.close()
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
                  {tab === "Session History" && (
                    <div className="w-full grid grid-cols-1 sm:grid-cols-3 gap-2 pt-2 text-xs" style={{ color: "var(--t-muted)" }}>
                      <span>Connected: {formatSessionTime(item.startedAt)}</span>
                      <span>Duration: {formatDuration(item.startedAt, item.status === "connected" ? undefined : item.endedAt)}</span>
                      <span>Disconnected: {item.status === "connected" ? "—" : formatSessionTime(item.endedAt)}</span>
                      <span>User: {item.userId ?? "—"}</span>
                      <span>Reason: {item.reason ?? "—"}</span>
                    </div>
                  )}
                </button>
              ))}
            </div>
          )}
        </GlassCard>
      )}
      <div className={`${tab === "Terminal" ? "" : "hidden "}grid grid-cols-1 xl:grid-cols-[minmax(330px,38%)_1fr] gap-5`}>
        <GlassCard className="p-5 space-y-5">
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
              value={deviceId}
              disabled={formLocked}
              onChange={(e) =>
                setDeviceId(e.target.value ? Number(e.target.value) : "")
              }
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
              disabled={formLocked}
              onChange={(e) => setUsername(e.target.value)}
              className="mt-2 w-full rounded-lg px-3 py-3 text-sm"
              style={inputStyle}
            />
          </label>
          <label className="block text-xs font-display">
            Authentication
            <div
              className="mt-2 rounded-lg px-3 py-3 text-sm"
              style={inputStyle}
            >
              🔑 &nbsp; Password
            </div>
          </label>
          <label className="block text-xs font-display">
            Password
            <div className="relative mt-2">
              <input
                type={showPassword ? "text" : "password"}
                value={password}
                disabled={formLocked}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Enter password"
                className="w-full rounded-lg px-3 py-3 pr-12 text-sm"
                style={inputStyle}
              />
              <button
                type="button"
                disabled={formLocked}
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
              disabled={formLocked}
              onChange={(e) => setRemember(e.target.checked)}
            />{" "}
            Remember credential for this device
          </label>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <Button disabled={testing || formLocked} onClick={() => void runTest()}>
              ↗ &nbsp; {testing ? "Testing..." : "Test Connection"}
            </Button>
            <Button primary disabled={connecting || formLocked} onClick={() => void connectTerminal()}>
              ▶ &nbsp; {connecting ? "Connecting..." : "Connect Terminal →"}
            </Button>
          </div>
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
                {testResult.error_code ? `${testResult.error_code}${testResult.stage ? ` @ ${testResult.stage}` : ""}: ` : ""}
                {testResult.message ||
                  "The connection could not be established."}
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
          </>}
        </GlassCard>
        <GlassCard ref={terminalPanelRef} className="p-4 md:p-5 min-h-[570px] flex flex-col">
          <div className="flex items-center gap-2 mb-4">
            <span style={{ color: "var(--t-accent)" }}>⌁</span>
            <h2
              className="font-display text-lg tracking-widest"
              style={{ color: "var(--t-accent)" }}
            >
              TERMINAL
            </h2>
            <div className="ml-auto flex gap-2">
              <button
                onClick={() => void terminalPanelRef.current?.requestFullscreen?.()}
                className="p-2 rounded-lg"
                style={{ border: "1px solid var(--t-border-alpha)" }}
              >
                ⛶
              </button>
              <button
                className="p-2 rounded-lg"
                style={{ border: "1px solid var(--t-border-alpha)" }}
              >
                ⚙
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
            className="rounded-t-xl overflow-hidden flex-1 flex flex-col"
            style={{ background: "#080d12", color: "#d9e3e8", minHeight: 390 }}
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
            <div className="p-2 flex-1" style={{ minHeight: 390 }}>
              {terminalTabs.map((tabItem) => (
                <div
                  key={tabItem.sessionUuid}
                  ref={(node) => {
                    if (node) terminalHostsRef.current.set(tabItem.sessionUuid, node)
                    else terminalHostsRef.current.delete(tabItem.sessionUuid)
                  }}
                  className={activeSessionUuid === tabItem.sessionUuid ? "h-full" : "hidden"}
                  style={{ minHeight: 390 }}
                />
              ))}
              <div ref={terminalHostRef} className={activeTab ? "hidden" : "h-full"}>
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
