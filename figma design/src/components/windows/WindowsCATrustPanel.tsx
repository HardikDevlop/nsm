import { useEffect, useRef, useState } from "react"
import GlassCard from "../GlassCard"
import { useAuth } from "../AuthContext"
import { getWindowsDeviceTrust, listWindowsCABundles, type WindowsCABundle, type WindowsEffectiveTrust } from "../../lib/api"
import WindowsCAUploadDialog from "./WindowsCAUploadDialog"
import WindowsCAAssignmentDialog from "./WindowsCAAssignmentDialog"
import WindowsCAUnassignmentDialog from "./WindowsCAUnassignmentDialog"
import WindowsCARevocationDialog from "./WindowsCARevocationDialog"

type Props = { deviceId: number; siteId?: number | null }

const sourceLabel = (source?: string) => ({ per_device: "Per-device CA", global: "Global CA", system: "System trust", none: "No trust configured", unavailable: "Trust unavailable" }[source ?? "none"] ?? "Trust unavailable")

function date(value?: string | null) {
  if (!value) return "Not reported"
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? "Not reported" : parsed.toLocaleString()
}

function Fingerprint({ value }: { value?: string | null }) {
  return <span className="break-all font-mono text-[10px]" style={{ color: "var(--t-muted)" }}>{value || "Not reported"}</span>
}

export default function WindowsCATrustPanel({ deviceId, siteId, deviceName = `Device ${deviceId}` }: Props & { deviceName?: string }) {
  const { hasPermission } = useAuth()
  const [trust, setTrust] = useState<WindowsEffectiveTrust | null>(null)
  const [bundles, setBundles] = useState<WindowsCABundle[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")
  const [uploadOpen, setUploadOpen] = useState(false)
  const [refreshKey, setRefreshKey] = useState(0)
  const [assignmentOpen, setAssignmentOpen] = useState(false)
  const [unassignmentOpen, setUnassignmentOpen] = useState(false)
  const [revokeBundle, setRevokeBundle] = useState<WindowsCABundle | null>(null)
  const requestId = useRef(0)

  useEffect(() => {
    if (!hasPermission("windows_ca:read") || !Number.isInteger(deviceId) || deviceId <= 0 || siteId == null) return
    const currentRequest = ++requestId.current
    setTrust(null)
    setBundles([])
    setUploadOpen(false)
    setAssignmentOpen(false)
    setUnassignmentOpen(false)
    setRevokeBundle(null)
    setError("")
    setLoading(true)
    Promise.all([getWindowsDeviceTrust(deviceId), listWindowsCABundles(siteId)])
      .then(([nextTrust, nextBundles]) => {
        if (currentRequest !== requestId.current) return
        setTrust(nextTrust)
        setBundles(nextBundles)
      })
      .catch(() => {
        if (currentRequest === requestId.current) setError("Unable to load Windows CA trust information.")
      })
      .finally(() => {
        if (currentRequest === requestId.current) setLoading(false)
      })
  }, [deviceId, siteId, hasPermission, refreshKey])

  if (!hasPermission("windows_ca:read")) return null
  if (siteId == null) return <GlassCard className="p-5"><p className="font-mono text-xs" style={{ color: "var(--t-muted)" }}>CA trust is unavailable because this device has no site.</p></GlassCard>
  if (loading) return <GlassCard className="p-5"><p className="font-mono text-xs" style={{ color: "var(--t-muted)" }}>Loading Windows CA trust…</p></GlassCard>
  if (error) return <GlassCard className="p-5" role="alert"><p className="font-mono text-xs" style={{ color: "var(--t-danger, #ff6688)" }}>⚠ {error}</p></GlassCard>

  return (
    <GlassCard className="p-5" aria-label="Windows CA trust">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="font-display font-bold" style={{ color: "var(--t-text)" }}>WINDOWS CA TRUST</h2>
          <p className="mt-1 font-mono text-xs" style={{ color: "var(--t-muted)" }}>Trust configuration for this device</p>
        </div>
        {hasPermission("windows_ca:manage") && <button type="button" onClick={() => setUploadOpen(true)} className="rounded-lg px-3 py-2 font-mono text-[10px] font-bold" style={{ background: "var(--t-accent)", color: "var(--t-bg)" }}>UPLOAD CA</button>}
        {hasPermission("windows_ca:assign") && <button type="button" onClick={() => setAssignmentOpen(true)} className="rounded-lg border px-3 py-2 font-mono text-[10px] font-bold" style={{ color: "var(--t-accent)", borderColor: "var(--t-border)" }}>{trust?.bundle_id ? "REPLACE CA" : "ASSIGN CA"}</button>}
        {hasPermission("windows_ca:assign") && trust?.trust_source === "per_device" && trust.bundle_id != null && <button type="button" onClick={() => setUnassignmentOpen(true)} className="rounded-lg border px-3 py-2 font-mono text-[10px] font-bold" style={{ color: "var(--t-warning, #f0b44d)", borderColor: "var(--t-border)" }}>REMOVE CA</button>}
        <span className="rounded-full border px-3 py-1 font-mono text-[10px]" style={{ color: "var(--t-accent)", borderColor: "var(--t-border)" }}>{sourceLabel(trust?.trust_source)}</span>
      </div>
      {trust?.trust_source === "unavailable" ? <p className="mt-4 font-mono text-xs" role="alert" style={{ color: "var(--t-danger, #ff6688)" }}>CA trust configuration is unavailable or invalid. Review the configured trust settings before running Windows monitoring.</p> : trust?.trust_source === "none" || !trust ? <p className="mt-4 font-mono text-xs" style={{ color: "var(--t-warning, #f0b44d)" }}>No Windows CA trust configuration is available.</p> : (
        <dl className="mt-4 grid gap-3 text-xs md:grid-cols-2">
          <div><dt className="font-mono text-[10px] uppercase" style={{ color: "var(--t-muted)" }}>Bundle</dt><dd className="mt-1" style={{ color: "var(--t-text)" }}>{trust.bundle_name || "Not applicable"}</dd></div>
          <div><dt className="font-mono text-[10px] uppercase" style={{ color: "var(--t-muted)" }}>Expires</dt><dd className="mt-1" style={{ color: "var(--t-text)" }}>{date(trust.expires_at)}</dd></div>
          <div className="md:col-span-2"><dt className="font-mono text-[10px] uppercase" style={{ color: "var(--t-muted)" }}>Fingerprint</dt><dd className="mt-1"><Fingerprint value={trust.fingerprint} /></dd></div>
        </dl>
      )}
      <div className="mt-5 border-t pt-4" style={{ borderColor: "var(--t-border)" }}>
        <h3 className="font-display text-sm font-bold" style={{ color: "var(--t-text)" }}>SITE CA BUNDLES</h3>
        {!bundles.length ? <p className="mt-3 font-mono text-xs" style={{ color: "var(--t-muted)" }}>No CA bundles are available for this site.</p> : (
          <div className="mt-3 space-y-3">
            {bundles.map((bundle) => <div key={bundle.id} className="rounded-lg border p-3" style={{ borderColor: "var(--t-border)" }}>
              <div className="flex flex-wrap items-center justify-between gap-2"><span className="font-semibold" style={{ color: "var(--t-text)" }}>{bundle.name}</span><span className="font-mono text-[10px] uppercase" style={{ color: bundle.status === "active" ? "var(--t-success)" : "var(--t-muted)" }}>{bundle.status}</span>{hasPermission("windows_ca:manage") && (trust?.bundle_id === bundle.id ? <span className="font-mono text-[10px]" style={{ color: "var(--t-warning, #f0b44d)" }}>ASSIGNED TO THIS DEVICE</span> : bundle.status === "revoked" ? null : <button type="button" onClick={() => setRevokeBundle(bundle)} className="rounded-lg border px-2 py-1 font-mono text-[10px]" style={{ color: "var(--t-danger, #ff6688)", borderColor: "var(--t-border)" }}>REVOKE</button>)}</div>
              <div className="mt-2 grid gap-2 font-mono text-[10px] md:grid-cols-2" style={{ color: "var(--t-muted)" }}>
                <span>Issuer: {bundle.issuer || "Not reported"}</span><span>Expires: {date(bundle.not_after)}</span><span className="md:col-span-2">Fingerprint: <Fingerprint value={bundle.sha256_fingerprint} /></span>
              </div>
            </div>)}
          </div>
        )}
      </div>
      {uploadOpen && <WindowsCAUploadDialog siteId={siteId} onClose={() => setUploadOpen(false)} onUploaded={() => { setUploadOpen(false); setRefreshKey((value) => value + 1) }} />}
      {assignmentOpen && <WindowsCAAssignmentDialog deviceId={deviceId} deviceName={deviceName} bundles={bundles} trust={trust} onClose={() => setAssignmentOpen(false)} onAssigned={() => { setAssignmentOpen(false); setRefreshKey((value) => value + 1) }} />}
      {unassignmentOpen && trust && <WindowsCAUnassignmentDialog deviceId={deviceId} deviceName={deviceName} trust={trust} onClose={() => setUnassignmentOpen(false)} onUnassigned={() => { setUnassignmentOpen(false); setRefreshKey((value) => value + 1) }} />}
      {revokeBundle && <WindowsCARevocationDialog bundle={revokeBundle} onClose={() => setRevokeBundle(null)} onRevoked={() => { setRevokeBundle(null); setRefreshKey((value) => value + 1) }} />}
    </GlassCard>
  )
}
