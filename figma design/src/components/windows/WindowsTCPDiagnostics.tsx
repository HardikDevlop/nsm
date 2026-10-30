import { useEffect, useRef, useState } from "react"
import GlassCard from "../GlassCard"
import { useAuth } from "../AuthContext"
import { runWindowsTCPDiagnostic, type WindowsTCPDiagnostic } from "../../lib/api"

type Props = { deviceId: number; siteId?: number | null; deviceName?: string }

const guidance: Record<string, string> = {
  connection_refused: "Confirm WinRM HTTPS is listening on TCP 5986 and permitted by the Windows firewall.",
  timeout: "Confirm the device is reachable from the collector and that TCP 5986 is allowed through intervening firewalls.",
  dns_resolution: "Confirm the registered hostname resolves correctly from the NMS collector.",
  invalid_target: "Review the registered Windows device hostname or address.",
}

export default function WindowsTCPDiagnostics({ deviceId, siteId, deviceName = `Device ${deviceId}` }: Props) {
  const { hasPermission } = useAuth()
  const [result, setResult] = useState<WindowsTCPDiagnostic | null>(null)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState("")
  const requestId = useRef(0)
  useEffect(() => { requestId.current += 1; setResult(null); setError(""); setRunning(false) }, [deviceId, siteId])
  if (!hasPermission("devices:update")) return null
  const run = async () => {
    if (running || !Number.isInteger(deviceId) || deviceId <= 0) return
    const current = ++requestId.current
    setRunning(true); setResult(null); setError("")
    try { const next = await runWindowsTCPDiagnostic(deviceId); if (current === requestId.current) setResult(next) }
    catch { if (current === requestId.current) setError("Unable to run the TCP connectivity diagnostic.") }
    finally { if (current === requestId.current) setRunning(false) }
  }
  const category = result?.category?.toLowerCase() ?? ""
  return <GlassCard className="p-4" aria-label="Windows TCP diagnostics">
    <div className="flex flex-wrap items-center justify-between gap-3"><div><h2 className="font-display text-sm font-bold" style={{ color: "var(--t-text)" }}>TCP Connectivity</h2><p className="mt-1 font-mono text-[10px]" style={{ color: "var(--t-muted)" }}>{deviceName} · WinRM HTTPS port 5986</p></div><button type="button" onClick={() => void run()} disabled={running} className="rounded-md px-3 py-1.5 font-mono text-[10px] font-bold" style={{ background: "var(--t-accent)", color: "var(--t-bg)" }}>{running ? "TESTING…" : "TEST TCP"}</button></div>
    <p className="mt-3 font-mono text-[10px]" style={{ color: "var(--t-muted)" }}>TCP reachability does not prove TLS, authentication, or CIM access.</p>
    {running && <p className="mt-2 font-mono text-xs">Running…</p>}
    {!running && !result && !error && <p className="mt-2 font-mono text-xs" style={{ color: "var(--t-muted)" }}>Not tested.</p>}
    {error && <p role="alert" className="mt-2 font-mono text-xs" style={{ color: "var(--t-danger, #ff6688)" }}>⚠ {error}</p>}
    {result && <div className="mt-3 rounded-md border p-2.5 font-mono text-[10px]" style={{ borderColor: result.status === "PASS" ? "var(--t-success)" : "var(--t-danger, #ff6688)" }}><div className="flex justify-between gap-2"><span>Status</span><strong style={{ color: result.status === "PASS" ? "var(--t-success)" : "var(--t-danger, #ff6688)" }}>{result.status}</strong></div><div className="mt-1">Category: {result.category}</div><div className="mt-1">{result.message}</div>{guidance[category] && <p className="mt-2" style={{ color: "var(--t-muted)" }}>{guidance[category]}</p>}</div>}
  </GlassCard>
}
