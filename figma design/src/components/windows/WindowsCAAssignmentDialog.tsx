import { useMemo, useState } from "react"
import GlassCard from "../GlassCard"
import { assignWindowsDeviceCA, type WindowsCABundle, type WindowsEffectiveTrust } from "../../lib/api"

type Props = { deviceId: number; deviceName: string; bundles: WindowsCABundle[]; trust: WindowsEffectiveTrust | null; onAssigned: () => void; onClose: () => void }
const expiry = (value?: string | null) => value ? new Date(value).toLocaleString() : "Not reported"

export default function WindowsCAAssignmentDialog({ deviceId, deviceName, bundles, trust, onAssigned, onClose }: Props) {
  const [selectedId, setSelectedId] = useState("")
  const [confirming, setConfirming] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState("")
  const eligible = useMemo(() => bundles.filter((bundle) => bundle.status === "active" && bundle.id !== trust?.bundle_id), [bundles, trust?.bundle_id])
  const selected = eligible.find((bundle) => String(bundle.id) === selectedId)
  const submit = async () => {
    if (!selected || submitting) return
    setSubmitting(true); setError("")
    try { await assignWindowsDeviceCA(deviceId, selected.id); onAssigned() }
    catch { setError("Unable to assign the Windows CA bundle.") }
    finally { setSubmitting(false) }
  }
  return <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" role="dialog" aria-modal="true" aria-label="Assign Windows CA certificate">
    <GlassCard className="w-full max-w-lg p-5">
      <div className="flex items-start justify-between gap-3"><div><h2 className="font-display font-bold" style={{ color: "var(--t-text)" }}>{trust?.bundle_id ? "REPLACE WINDOWS CA" : "ASSIGN WINDOWS CA"}</h2><p className="mt-1 font-mono text-xs" style={{ color: "var(--t-muted)" }}>{deviceName} · Current trust: {trust?.trust_source || "none"}</p></div><button type="button" onClick={onClose} disabled={submitting} aria-label="Close assignment dialog">✕</button></div>
      {!confirming ? <>
        <label className="mt-5 block font-mono text-xs" style={{ color: "var(--t-muted)" }}>Eligible site CA bundle<select value={selectedId} onChange={(event) => setSelectedId(event.target.value)} disabled={submitting} className="mt-1 w-full rounded-lg border px-3 py-2"><option value="">Select a CA bundle</option>{bundles.map((bundle) => <option key={bundle.id} value={bundle.id} disabled={bundle.status !== "active" || bundle.id === trust?.bundle_id}>{bundle.name} · {bundle.status}</option>)}</select></label>
        {selected && <div className="mt-4 rounded-lg border p-3 font-mono text-xs" style={{ borderColor: "var(--t-border)", color: "var(--t-muted)" }}><div>Name: {selected.name}</div><div>Fingerprint: {selected.sha256_fingerprint}</div><div>Expires: {expiry(selected.not_after)}</div></div>}
        <p className="mt-4 font-mono text-xs" style={{ color: "var(--t-warning, #f0b44d)" }}>Per-device assignment overrides global or system trust for this device.</p>
        {error && <p role="alert" className="mt-3 font-mono text-xs" style={{ color: "var(--t-danger, #ff6688)" }}>⚠ {error}</p>}
        <div className="mt-5 flex justify-end gap-2"><button type="button" onClick={onClose} disabled={submitting} className="rounded-lg border px-3 py-2 font-mono text-xs">CANCEL</button><button type="button" onClick={() => selected && setConfirming(true)} disabled={!selected || submitting} className="rounded-lg px-3 py-2 font-mono text-xs" style={{ background: "var(--t-accent)", color: "var(--t-bg)" }}>CONTINUE</button></div>
      </> : <>
        <div className="mt-5 rounded-lg border p-4 font-mono text-xs" style={{ borderColor: "var(--t-warning, #f0b44d)" }}><p>Change effective CA trust for <strong>{deviceName}</strong>?</p><p className="mt-2">Selected: {selected?.name}</p><p className="mt-1 break-all">Fingerprint: {selected?.sha256_fingerprint}</p><p className="mt-3" style={{ color: "var(--t-warning, #f0b44d)" }}>This will change the certificate authority used for this device.</p></div>
        {error && <p role="alert" className="mt-3 font-mono text-xs" style={{ color: "var(--t-danger, #ff6688)" }}>⚠ {error}</p>}
        <div className="mt-5 flex justify-end gap-2"><button type="button" onClick={() => setConfirming(false)} disabled={submitting} className="rounded-lg border px-3 py-2 font-mono text-xs">BACK</button><button type="button" onClick={() => void submit()} disabled={submitting} className="rounded-lg px-3 py-2 font-mono text-xs" style={{ background: "var(--t-accent)", color: "var(--t-bg)" }}>{submitting ? "ASSIGNING…" : "CONFIRM ASSIGNMENT"}</button></div>
      </>}
    </GlassCard>
  </div>
}
