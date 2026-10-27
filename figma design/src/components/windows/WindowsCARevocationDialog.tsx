import { useState } from "react"
import GlassCard from "../GlassCard"
import { revokeWindowsCABundle, type WindowsCABundle } from "../../lib/api"

type Props = { bundle: WindowsCABundle; onClose: () => void; onRevoked: () => void }

export default function WindowsCARevocationDialog({ bundle, onClose, onRevoked }: Props) {
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState("")
  const submit = async () => {
    if (submitting || bundle.status === "revoked") return
    setSubmitting(true); setError("")
    try { await revokeWindowsCABundle(bundle.id); onRevoked() }
    catch { setError("Unable to revoke the Windows CA bundle. It may be actively assigned.") }
    finally { setSubmitting(false) }
  }
  return <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" role="dialog" aria-modal="true" aria-label="Revoke Windows CA bundle">
    <GlassCard className="w-full max-w-lg p-5">
      <div className="flex items-start justify-between gap-3"><div><h2 className="font-display font-bold" style={{ color: "var(--t-text)" }}>REVOKE WINDOWS CA</h2><p className="mt-1 font-mono text-xs" style={{ color: "var(--t-muted)" }}>{bundle.name}</p></div><button type="button" onClick={onClose} disabled={submitting} aria-label="Close revocation dialog">✕</button></div>
      <div className="mt-5 rounded-lg border p-4 font-mono text-xs" style={{ borderColor: "var(--t-warning, #f0b44d)" }}><p>Revoke this CA bundle?</p><p className="mt-2">Status: {bundle.status}</p><p className="mt-1 break-all">Fingerprint: {bundle.sha256_fingerprint || "Not reported"}</p><p className="mt-3" style={{ color: "var(--t-warning, #f0b44d)" }}>Revocation prevents future use. Devices are not automatically unassigned.</p></div>
      {error && <p role="alert" className="mt-3 font-mono text-xs" style={{ color: "var(--t-danger, #ff6688)" }}>⚠ {error}</p>}
      <div className="mt-5 flex justify-end gap-2"><button type="button" onClick={onClose} disabled={submitting} className="rounded-lg border px-3 py-2 font-mono text-xs">CANCEL</button><button type="button" onClick={() => void submit()} disabled={submitting || bundle.status === "revoked"} className="rounded-lg px-3 py-2 font-mono text-xs" style={{ background: "var(--t-danger, #ff6688)", color: "var(--t-bg)" }}>{submitting ? "REVOKING…" : "CONFIRM REVOCATION"}</button></div>
    </GlassCard>
  </div>
}
