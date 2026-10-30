import { useEffect, useRef, useState } from "react"
import GlassCard from "../GlassCard"
import { useAuth } from "../AuthContext"
import { runWindowsTLSDiagnostic, type WindowsTLSDiagnostic } from "../../lib/api"

type Props = { deviceId: number; siteId?: number | null; deviceName?: string }
const guidance: Record<string, string> = {
  untrusted_certificate: "Verify that the assigned CA bundle trusts the Windows HTTPS listener certificate.",
  hostname_mismatch: "Verify the registered device address matches a DNS name or IP SAN on the certificate.",
  expired_certificate: "Renew the Windows HTTPS listener certificate before retrying.",
  certificate_not_yet_valid: "Verify the certificate validity dates and the system clock.",
  tls_handshake_failed: "Verify the HTTPS listener and protocol compatibility on the Windows device.",
}
const expiry = (value?: string) => value ? new Date(value).toLocaleString() : "Not reported"

export default function WindowsTLSDiagnostics({ deviceId, siteId, deviceName = `Device ${deviceId}` }: Props) {
  const { hasPermission } = useAuth()
  const [result, setResult] = useState<WindowsTLSDiagnostic | null>(null)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState("")
  const requestId = useRef(0)
  useEffect(() => { requestId.current += 1; setResult(null); setError(""); setRunning(false) }, [deviceId, siteId])
  if (!hasPermission("devices:update")) return null
  const run = async () => {
    if (running || !Number.isInteger(deviceId) || deviceId <= 0) return
    const current = ++requestId.current
    setRunning(true); setResult(null); setError("")
    try { const next = await runWindowsTLSDiagnostic(deviceId); if (current === requestId.current) setResult(next) }
    catch { if (current === requestId.current) setError("Unable to run the TLS certificate diagnostic.") }
    finally { if (current === requestId.current) setRunning(false) }
  }
  const category = result?.category?.toLowerCase() ?? ""
  const certificate = result?.certificate
  return <GlassCard className="p-4" aria-label="Windows TLS diagnostics">
    <div className="flex flex-wrap items-center justify-between gap-3"><div><h2 className="font-display text-sm font-bold" style={{ color: "var(--t-text)" }}>TLS Certificate</h2><p className="mt-1 font-mono text-[10px]" style={{ color: "var(--t-muted)" }}>{deviceName} · WinRM HTTPS certificate</p></div><button type="button" onClick={() => void run()} disabled={running} className="rounded-md px-3 py-1.5 font-mono text-[10px] font-bold" style={{ background: "var(--t-accent)", color: "var(--t-bg)" }}>{running ? "VERIFYING…" : "VERIFY TLS"}</button></div>
    <p className="mt-3 font-mono text-[10px]" style={{ color: "var(--t-muted)" }}>TLS success does not prove WinRM authentication, PowerShell authorization, or CIM access.</p>
    {running && <p className="mt-3 font-mono text-xs">Running…</p>}
    {!running && !result && !error && <p className="mt-3 font-mono text-xs" style={{ color: "var(--t-muted)" }}>Not tested.</p>}
    {error && <p role="alert" className="mt-3 font-mono text-xs" style={{ color: "var(--t-danger, #ff6688)" }}>⚠ {error}</p>}
    {result && <div className="mt-3 rounded-md border p-2.5 font-mono text-[10px]" style={{ borderColor: result.status === "PASS" ? "var(--t-success)" : "var(--t-danger, #ff6688)" }}><div className="flex justify-between gap-2"><span>Status</span><strong style={{ color: result.status === "PASS" ? "var(--t-success)" : "var(--t-danger, #ff6688)" }}>{result.status}</strong></div><div className="mt-1">Category: {result.category}</div><div className="mt-1">{result.message}</div>{guidance[category] && <p className="mt-2" style={{ color: "var(--t-muted)" }}>{guidance[category]}</p>}{certificate && <dl className="mt-2 grid gap-1 md:grid-cols-2"><div>Subject: {certificate.subject}</div><div>Issuer: {certificate.issuer}</div><div>Expires: {expiry(certificate.expires_at)}</div><div>Days remaining: {certificate.days_remaining}</div><div className="md:col-span-2">SAN match: {certificate.san_match ? "Yes" : "No"}</div></dl>}</div>}
  </GlassCard>
}
