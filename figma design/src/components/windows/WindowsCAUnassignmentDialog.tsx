import { useState } from "react"
import GlassCard from "../GlassCard"
import { unassignWindowsDeviceCA, type WindowsEffectiveTrust } from "../../lib/api"

type Props = { deviceId: number; deviceName: string; trust: WindowsEffectiveTrust; onClose: () => void; onUnassigned: () => void }

export default function WindowsCAUnassignmentDialog({ deviceId, deviceName, trust, onClose, onUnassigned }: Props) {
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState("")
  const submit = async () => {
    if (submitting || trust.trust_source !== "per_device" || trust.bundle_id == null) return
    setSubmitting(true); setError("")
    try { await unassignWindowsDeviceCA(deviceId); onUnassigned() }
    catch { setError("Unable to remove the Windows CA assignment.") }
    finally { setSubmitting(false) }
  }
  return <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" role="dialog" aria-modal="true" aria-label="Remove Windows CA assignment">
    <GlassCard className="w-full max-w-lg p-5">
      <div className="flex items-start justify-between gap-3"><div><h2 className="font-display font-bold" style={{ color: "var(--t-text)" }}>REMOVE WINDOWS CA</h2><p className="mt-1 font-mono text-xs" style={{ color: "var(--t-muted)" }}>{deviceName}</p></div><button type="button" onClick={onClose} disabled={submitting} aria-label="Close unassignment dialog">✕</button></div>
      <div className="mt-5 rounded-lg border p-4 font-mono text-xs" style={{ borderColor: "var(--t-warning, #f0b44d)" }}><p>Remove the per-device CA assignment for this device?</p><p className="mt-2">Current bundle: {trust.bundle_name || "Not reported"}</p><p className="mt-3" style={{ color: "var(--t-warning, #f0b44d)" }}>The device will use the existing global or system trust policy. This does not guarantee that its Windows connection will continue working.</p></div>
      {error && <p role="alert" className="mt-3 font-mono text-xs" style={{ color: "var(--t-danger, #ff6688)" }}>⚠ {error}</p>}
      <div className="mt-5 flex justify-end gap-2"><button type="button" onClick={onClose} disabled={submitting} className="rounded-lg border px-3 py-2 font-mono text-xs">CANCEL</button><button type="button" onClick={() => void submit()} disabled={submitting} className="rounded-lg px-3 py-2 font-mono text-xs" style={{ background: "var(--t-accent)", color: "var(--t-bg)" }}>{submitting ? "REMOVING…" : "CONFIRM REMOVAL"}</button></div>
    </GlassCard>
  </div>
}
