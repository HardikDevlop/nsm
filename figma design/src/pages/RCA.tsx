import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useState } from "react"
import GlassCard from "../components/GlassCard"
import { useAuth } from "../components/AuthContext"
import { analyzeRCA, getRCAIncident, listRCAIncidents, type RCAAlert, type RCAEvidence, type RCAIncident } from "../lib/api"

const inputStyle = { background: "var(--t-card)", color: "var(--t-text)", border: "1px solid var(--t-border-alpha)" }
type AlertContext = RCAAlert & { ip_address?: string | null; ip?: string | null; interface_name?: string | null; interface?: string | null }

function faultType(alert?: RCAAlert) { return alert?.title.split(":", 1)[0] || "Unknown fault" }
function affectedEntity(alert?: RCAAlert, fallback = "Unavailable") { return alert?.title.includes(":") ? alert.title.split(":").slice(1).join(":").trim() : fallback }
function currentState(alerts: RCAAlert[]) {
  if (!alerts.length) return "UNKNOWN"
  const statuses = alerts.map((alert) => alert.status.trim().toLowerCase())
  const allResolved = statuses.every((status) => status === "resolved")
  const allOpen = statuses.every((status) => status === "open")
  const hasOpen = statuses.some((status) => status === "open")
  const hasResolved = statuses.some((status) => status === "resolved")
  if (allOpen) return "ACTIVE"
  if (allResolved) return "RECOVERED"
  if (hasOpen && hasResolved) return "PARTIALLY RECOVERED"
  return "UNKNOWN"
}
function confidenceBand(confidence: number) { const percent = confidence * 100; return percent < 40 ? "Low" : percent < 70 ? "Moderate" : percent < 90 ? "High" : "Very High" }
function formatTimestamp(value?: string) { return value ? new Date(value).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', hour12: true }) : "Unavailable" }
function contextValue(alert: RCAAlert | undefined, evidence: RCAEvidence | undefined, keys: string[]) {
  const alertData = alert as AlertContext | undefined
  for (const key of keys) {
    const value = alertData?.[key as keyof AlertContext] ?? evidence?.payload?.[key]
    if (typeof value === "string" && value.trim()) return value.trim()
  }
  return null
}
function stateStyle(state: string) {
  if (state === "RECOVERED") return { color: "#4ade80", background: "rgba(74,222,128,.1)" }
  if (state === "ACTIVE") return { color: "#ff6688", background: "rgba(255,102,136,.1)" }
  if (state === "PARTIALLY RECOVERED") return { color: "#fbbf24", background: "rgba(251,191,36,.1)" }
  return { color: "#94a3b8", background: "rgba(148,163,184,.1)" }
}
function Field({ label, value }: { label: string; value: string }) {
  return <div className="min-w-0"><div className="font-mono text-[10px] uppercase" style={{ color: "var(--t-muted)" }}>{label}</div><div className="font-mono text-xs mt-1 break-words" style={{ color: "var(--t-text)" }}>{value}</div></div>
}

export default function RCA() {
  const { hasPermission } = useAuth()
  const client = useQueryClient()
  const [hours, setHours] = useState(24)
  const [selectedId, setSelectedId] = useState<number>()
  const [analysisError, setAnalysisError] = useState("")
  const incidents = useQuery({ queryKey: ["rca-incidents", hours], queryFn: () => listRCAIncidents(hours), enabled: hasPermission("rca:read"), staleTime: 30_000, refetchOnWindowFocus: false, refetchOnMount: false })
  const detail = useQuery({ queryKey: ["rca-incident", selectedId], queryFn: () => getRCAIncident(selectedId!), enabled: hasPermission("rca:read") && selectedId != null, staleTime: 30_000, refetchOnWindowFocus: false })
  const analyze = useMutation({ mutationFn: () => analyzeRCA(hours), onSuccess: (result) => { setAnalysisError(""); client.invalidateQueries({ queryKey: ["rca-incidents"] }); if (result.incident) setSelectedId(result.incident.id) }, onError: (error) => setAnalysisError(error instanceof Error ? error.message : "RCA analysis failed.") })
  if (!hasPermission("rca:read")) return <div className="p-6 font-mono text-sm" style={{ color: "var(--t-muted)" }}>You do not have permission to view RCA.</div>

  const selected: RCAIncident | undefined = detail.data ?? incidents.data?.items.find((item) => item.id === selectedId)
  const alerts = selected?.raw_alerts ?? []
  const evidence = selected?.evidence ?? []
  const strongestEvidence = evidence.length ? evidence.reduce((best, item) => item.score > best.score ? item : best) : undefined
  const strongestAlert = (strongestEvidence?.alert_id != null ? alerts.find((alert) => alert.id === strongestEvidence.alert_id) : undefined) ?? alerts[0]
  const state = currentState(alerts)
  const ipAddress = contextValue(strongestAlert, strongestEvidence, ["ip_address", "ip", "management_ip"])
  const interfaceName = contextValue(strongestAlert, strongestEvidence, ["interface_name", "interface", "if_name"])
  const stateColors = stateStyle(state)

  return <div className="p-4 md:p-6 space-y-5">
    <div className="flex flex-wrap items-end justify-between gap-4"><div><h1 className="font-display font-bold text-2xl tracking-widest" style={{ color: "var(--t-text)" }}>ROOT CAUSE ANALYSIS</h1><p className="font-mono text-xs mt-1" style={{ color: "var(--t-muted)" }}>Correlated alerts and evidence · raw alerts remain visible</p></div><div className="flex gap-2"><select aria-label="RCA time range" value={hours} onChange={(event) => setHours(Number(event.target.value))} className="rounded px-3 py-2 font-mono text-xs" style={inputStyle}><option value={1}>Last 1 hour</option><option value={24}>Last 24 hours</option><option value={168}>Last 7 days</option><option value={720}>Last 30 days</option></select>{hasPermission("rca:execute") && <button type="button" onClick={() => { setAnalysisError(""); analyze.mutate() }} disabled={analyze.isPending} className="rounded px-3 py-2 font-mono text-xs" style={{ background: "#00d4ff", color: "#06111a" }}>{analyze.isPending ? "Analyzing..." : "Analyze alerts"}</button>}</div></div>
    {analysisError && <div role="alert" className="rounded px-3 py-2 font-mono text-xs" style={{ color: "#ffb3c1", background: "#3a1420", border: "1px solid #ff6688" }}>{analysisError}</div>}
    <div className="grid grid-cols-1 xl:grid-cols-[minmax(260px,.7fr)_minmax(0,1.5fr)] gap-4">
      <GlassCard className="overflow-hidden"><div className="px-4 py-3 font-display font-semibold text-sm" style={{ borderBottom: "1px solid var(--t-border-light)", color: "var(--t-text)" }}>RCA incidents</div>{incidents.isError ? <div className="p-4 font-mono text-xs" style={{ color: "#ff6688" }}>Unable to load stored RCA incidents.</div> : incidents.data?.items.length ? incidents.data.items.map((item) => { const itemAlerts = item.raw_alerts ?? []; return <button type="button" key={item.id} onClick={() => setSelectedId(item.id)} className="w-full text-left px-4 py-3" style={{ borderBottom: "1px solid var(--t-border-alpha)", background: item.id === selectedId ? "var(--t-bg)" : "transparent" }}><div className="font-mono text-xs" style={{ color: "var(--t-text)" }}>{item.root_label}</div><div className="font-mono text-[10px] mt-1" style={{ color: "var(--t-muted)" }}>{faultType(itemAlerts[0])} · {(item.confidence * 100).toFixed(1)}% · {currentState(itemAlerts)}</div><div className="font-mono text-[10px] mt-1" style={{ color: "var(--t-muted)" }}>Analyzed {formatTimestamp(item.updated_at)}</div></button> }) : <div className="p-6 text-center font-mono text-xs" style={{ color: "var(--t-muted)" }}>No stored RCA incidents. Run an analysis to correlate recent alerts.</div>}</GlassCard>
      <GlassCard>{detail.isLoading ? <div className="p-8 text-center font-mono text-xs" style={{ color: "var(--t-muted)" }}>Loading RCA detail...</div> : detail.isError ? <div role="alert" className="p-8 text-center font-mono text-xs" style={{ color: "#ff6688" }}>Unable to load RCA detail.</div> : !selected ? <div className="p-8 text-center font-mono text-xs" style={{ color: "var(--t-muted)" }}>Select an RCA result to inspect the evidence and current state.</div> : <div className="space-y-4">
        <div className="flex flex-wrap items-start justify-between gap-3 pb-3" style={{ borderBottom: "1px solid var(--t-border-alpha)" }}><div><div className="font-mono text-[10px] uppercase" style={{ color: "var(--t-muted)" }}>Selected RCA result</div><h2 className="font-display font-semibold text-xl mt-1" style={{ color: "var(--t-text)" }}>{selected.root_label}</h2></div><span className="rounded px-3 py-1 font-mono text-xs" style={{ color: stateColors.color, background: stateColors.background, border: `1px solid ${stateColors.color}` }}>{state}</span></div>
        <section className="rounded p-4" style={{ background: "var(--t-bg)", border: "1px solid var(--t-border-alpha)" }}><h3 className="font-display font-semibold text-sm" style={{ color: "var(--t-text)" }}>What Happened</h3><div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 mt-3"><Field label="Fault / event type" value={faultType(strongestAlert)} /><Field label="Affected device / CI" value={selected.root_label || affectedEntity(strongestAlert)} /><Field label="Severity" value={strongestAlert?.severity || "Unavailable"} /><Field label="Detected" value={formatTimestamp(strongestAlert?.created_at)} />{ipAddress && <Field label="IP address" value={ipAddress} />}{interfaceName && <Field label="Interface" value={interfaceName} />}</div></section>
        <section className="rounded p-4" style={{ background: "rgba(74,222,128,.05)", border: "1px solid rgba(74,222,128,.25)" }}><h3 className="font-display font-semibold text-sm" style={{ color: "var(--t-text)" }}>Probable Root Cause</h3><div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mt-3"><Field label="Root entity" value={selected.root_label} /><Field label="Entity type" value={selected.root_kind || "Unavailable"} /><Field label="Confidence" value={`${(selected.confidence * 100).toFixed(1)}% · ${confidenceBand(selected.confidence)}`} /></div></section>
        <section><h3 className="font-display font-semibold text-sm" style={{ color: "var(--t-text)" }}>Current State</h3><p className="font-mono text-xs mt-2" style={{ color: "var(--t-muted)" }}>{state === "ACTIVE" ? "All supporting alerts are open." : state === "RECOVERED" ? "All supporting alerts are resolved." : state === "PARTIALLY RECOVERED" ? "Supporting alerts include both open and resolved states." : "Insufficient supporting alert data to determine current state."}</p>{!alerts.length && <div className="font-mono text-xs mt-2" style={{ color: "#ffb86b" }}>Insufficient evidence to determine a probable root cause.</div>}</section>
        <section><h3 className="font-display font-semibold text-sm" style={{ color: "var(--t-text)" }}>Why RCA Selected This</h3><div className="mt-2 rounded p-3 font-mono text-xs" style={{ background: "var(--t-bg)", border: "1px solid var(--t-border-alpha)" }}>{strongestAlert ? <><div style={{ color: "#00d4ff" }}>Strongest supporting alert · #{strongestAlert.id}</div><div className="mt-1" style={{ color: "var(--t-text)" }}>{strongestAlert.title}</div><div className="mt-1" style={{ color: "var(--t-muted)" }}>Severity: {strongestAlert.severity} · Status: {strongestAlert.status} · Detected: {formatTimestamp(strongestAlert.created_at)}</div></> : <div style={{ color: "var(--t-muted)" }}>No supporting alert available.</div>}{strongestEvidence?.reason && <div className="mt-2" style={{ color: "var(--t-muted)" }}>{strongestEvidence.reason}</div>}</div></section>
        <section><h3 className="font-display font-semibold text-sm" style={{ color: "var(--t-text)" }}>IMPACT</h3><div className="mt-2 rounded p-3 font-mono text-xs space-y-1" style={{ background: "var(--t-bg)", border: "1px solid var(--t-border-alpha)", color: "var(--t-muted)" }}><div>Directly affected entity: <span style={{ color: "var(--t-text)" }}>{selected.root_label}</span></div><div>Correlated alerts: <span style={{ color: "var(--t-text)" }}>{alerts.length}</span></div><div>{selected.impact_summary?.trim() || "No downstream impact identified from available evidence."}</div></div></section>
        <section><h3 className="font-display font-semibold text-sm" style={{ color: "var(--t-text)" }}>Supporting Evidence</h3><div className="mt-2 space-y-2">{alerts.length ? alerts.map((alert) => { const alertItems = evidence.filter((item) => item.alert_id === alert.id); return <details key={alert.id} className="rounded" style={{ background: "var(--t-bg)", border: "1px solid var(--t-border-alpha)" }}><summary className="cursor-pointer px-3 py-2 font-mono text-xs" style={{ color: "var(--t-text)" }}>#{alert.id} · {alert.title} · {alert.severity} · {alert.status}</summary><div className="px-3 pb-3 pt-1 space-y-1 font-mono text-[10px]" style={{ color: "var(--t-muted)" }}><div>Detected: {formatTimestamp(alert.created_at)}</div><div>Affected entity: {affectedEntity(alert, selected.root_label)}</div>{alertItems.map((item) => <div key={item.id} className="pt-1" style={{ color: "var(--t-text)" }}>Evidence: {item.reason}</div>)}</div></details> }) : <div className="rounded p-3 font-mono text-xs" style={{ color: "var(--t-muted)", background: "var(--t-bg)" }}>No raw supporting alerts available.</div>}</div></section>
        <div className="font-mono text-[10px]" style={{ color: "var(--t-muted)" }}>Confidence is a deterministic correlation score based on available monitoring evidence; it is not an ML prediction.</div>
        <div className="font-mono text-[10px]" style={{ color: "var(--t-muted)" }}>Analysis window: {formatTimestamp(selected.window_start)} - {formatTimestamp(selected.window_end)} · RCA analyzed: {formatTimestamp(selected.updated_at || selected.created_at)}</div>
      </div>}</GlassCard>
    </div>
  </div>
}
