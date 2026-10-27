import { useEffect, useRef, useState } from "react"
import GlassCard from "../GlassCard"
import { useAuth } from "../AuthContext"
import { runWindowsWinRMDiagnostic, type WindowsWinRMDiagnostic } from "../../lib/api"

type Props = { deviceId: number; siteId?: number | null; deviceName?: string }
const labels: Record<string, string> = { winrm_authentication: "WinRM authentication", powershell_authorization: "PowerShell authorization", cim_query: "CIM query" }
const guidance: Record<string, string> = {
  authentication_failed: "Verify the monitoring account credentials and permitted authentication configuration.",
  access_denied: "Verify the WinRM session endpoint and monitoring-account permissions.",
  cim_query_failed: "Verify WMI/CIM access rights and namespace permissions.",
  transport: "Verify the HTTPS listener and review the preceding TLS diagnostics.",
  timeout: "Verify connectivity and remote service responsiveness.",
}

export default function WindowsWinRMDiagnostics({ deviceId, siteId, deviceName = `Device ${deviceId}` }: Props) {
  const { hasPermission } = useAuth()
  const [result, setResult] = useState<WindowsWinRMDiagnostic | null>(null)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState("")
  const requestId = useRef(0)
  useEffect(() => { requestId.current += 1; setResult(null); setError(""); setRunning(false) }, [deviceId, siteId])
  if (!hasPermission("devices:update")) return null
  const run = async () => {
    if (running || !Number.isInteger(deviceId) || deviceId <= 0) return
    const current = ++requestId.current
    setRunning(true); setResult(null); setError("")
    try { const next = await runWindowsWinRMDiagnostic(deviceId); if (current === requestId.current) setResult(next) }
    catch { if (current === requestId.current) setError("Unable to run the WinRM diagnostic.") }
    finally { if (current === requestId.current) setRunning(false) }
  }
  const stages = result?.stages ?? []
  const overall = stages.length && stages.every((stage) => stage.status === "PASS") ? "PASS" : stages.length ? "FAIL" : "Not tested"
  return <GlassCard className="p-5" aria-label="Windows WinRM diagnostics">
    <div className="flex flex-wrap items-start justify-between gap-3"><div><h2 className="font-display font-bold" style={{ color: "var(--t-text)" }}>WINRM / POWERSHELL / CIM</h2><p className="mt-1 font-mono text-xs" style={{ color: "var(--t-muted)" }}>{deviceName} · Read-only diagnostics</p></div><button type="button" onClick={() => void run()} disabled={running} className="rounded-lg px-3 py-2 font-mono text-[10px] font-bold" style={{ background: "var(--t-accent)", color: "var(--t-bg)" }}>{running ? "TESTING…" : "RUN DIAGNOSTICS"}</button></div>
    {running && <p className="mt-4 font-mono text-xs">Running…</p>}
    {!running && !result && !error && <p className="mt-4 font-mono text-xs" style={{ color: "var(--t-muted)" }}>Not tested.</p>}
    {error && <p role="alert" className="mt-4 font-mono text-xs" style={{ color: "var(--t-danger, #ff6688)" }}>⚠ {error}</p>}
    {result && <div className="mt-4 space-y-3"><div className="font-mono text-xs">Overall status: <strong>{overall}</strong></div>{stages.map((stage) => <div key={stage.step} className="rounded-lg border p-3 font-mono text-xs" style={{ borderColor: stage.status === "PASS" ? "var(--t-success)" : stage.status === "FAIL" ? "var(--t-danger, #ff6688)" : "var(--t-border)" }}><div className="flex justify-between gap-2"><strong>{labels[stage.step] || stage.step}</strong><span>{stage.status}</span></div><div className="mt-1">Category: {stage.category}</div><div className="mt-1">{stage.message}</div>{stage.category === "indeterminate" && stage.step === "winrm_authentication" && <p className="mt-2" style={{ color: "var(--t-muted)" }}>Authentication and PowerShell session execution were verified together; independent authentication status is not available.</p>}{guidance[stage.category] && <p className="mt-2" style={{ color: "var(--t-muted)" }}>{guidance[stage.category]}</p>}</div>)}</div>}
  </GlassCard>
}
