import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useState } from "react"
import GlassCard from "../components/GlassCard"
import { useAuth } from "../components/AuthContext"
import {
  acknowledgeIncident,
  analyzeIncidentRCA,
  createIncident,
  getManagedIncident,
  listIncidents,
  reopenIncident,
  resolveIncident,
  updateIncident,
  addIncidentComment,
  type ManagedIncident,
} from "../lib/api"

const style = {
  background: "var(--t-card)",
  color: "var(--t-text)",
  border: "1px solid var(--t-border-alpha)",
}

export default function IncidentManagement() {
  const { hasPermission } = useAuth()
  const client = useQueryClient()
  const [selected, setSelected] = useState<number>()
  const [comment, setComment] = useState("")
  const [category, setCategory] = useState("other")
  const [priority, setPriority] = useState("p3")
  const [assignedTo, setAssignedTo] = useState<number>()
  const [actionError, setActionError] = useState("")
  const incidents = useQuery({
    queryKey: ["managed-incidents"],
    queryFn: () => listIncidents(),
    enabled: hasPermission("incidents:read"),
    staleTime: 30_000,
    refetchOnWindowFocus: false,
    refetchOnMount: false,
  })
  const detail = useQuery({
    queryKey: ["managed-incident", selected],
    queryFn: () => getManagedIncident(selected!),
    enabled: hasPermission("incidents:read") && selected != null,
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  })
  const create = useMutation({
    mutationFn: () =>
      createIncident({
        title: "Manual incident",
        category,
        priority,
        assigned_to: assignedTo,
        alert_ids: [],
      }),
    onSuccess: () =>
      client.invalidateQueries({ queryKey: ["managed-incidents"] }),
  })
  const refresh = () => {
    client.invalidateQueries({ queryKey: ["managed-incidents"] })
    client.invalidateQueries({ queryKey: ["managed-incident", selected] })
    client.invalidateQueries({ queryKey: ["rca-incidents"] })
    client.invalidateQueries({ queryKey: ["rca-incident"] })
  }
  const showActionError = (error: unknown) =>
    setActionError(
      error instanceof Error ? error.message : "Incident action failed.",
    )
  const mutationOptions = { onSuccess: refresh, onError: showActionError }
  const close = useMutation({
    mutationFn: (id: number) => updateIncident(id, { status: "closed" }),
    ...mutationOptions,
  })
  const acknowledge = useMutation({
    mutationFn: acknowledgeIncident,
    ...mutationOptions,
  })
  const resolve = useMutation({
    mutationFn: resolveIncident,
    ...mutationOptions,
  })
  const reopen = useMutation({ mutationFn: reopenIncident, ...mutationOptions })
  const transition = useMutation({
    mutationFn: ({ id, status }: { id: number; status: string }) =>
      updateIncident(id, { status }),
    ...mutationOptions,
  })
  const assign = useMutation({
    mutationFn: (id: number) =>
      updateIncident(id, { assigned_to: assignedTo ?? null }),
    ...mutationOptions,
  })
  const analyzeRca = useMutation({
    mutationFn: analyzeIncidentRCA,
    ...mutationOptions,
  })
  const analyzeSelectedRca = () => {
    if (selected == null) return
    setActionError("")
    analyzeRca.mutate(selected)
  }
  const addComment = useMutation({
    mutationFn: () => addIncidentComment(selected!, comment),
    onSuccess: () => {
      setComment("")
      client.invalidateQueries({ queryKey: ["managed-incidents"] })
    },
  })
  if (!hasPermission("incidents:read"))
    return (
      <div
        className="p-6 font-mono text-sm"
        style={{ color: "var(--t-muted)" }}
      >
        You do not have permission to view incident management.
      </div>
    )
  const item: ManagedIncident | undefined =
    detail.data ?? incidents.data?.items.find((row) => row.id === selected)
  const status = item?.status
  const activeStatus =
    status === "open" || status === "investigating" || status === "pending"
  return (
    <div className="p-4 md:p-6 space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1
            className="font-display font-bold text-2xl tracking-widest"
            style={{ color: "var(--t-text)" }}
          >
            INCIDENT MANAGEMENT
          </h1>
          <p
            className="font-mono text-xs mt-1"
            style={{ color: "var(--t-muted)" }}
          >
            Alerts and RCA remain preserved as linked evidence
          </p>
        </div>
        {hasPermission("incidents:create") && (
          <div className="flex flex-wrap gap-2">
            <select
              aria-label="Incident category"
              value={category}
              onChange={(event) => setCategory(event.target.value)}
              className="rounded px-3 py-2 font-mono text-xs"
              style={style}
            >
              <option value="availability">Availability</option>
              <option value="performance">Performance</option>
              <option value="security">Security</option>
              <option value="change">Change</option>
              <option value="other">Other</option>
            </select>
            <select
              aria-label="Incident priority"
              value={priority}
              onChange={(event) => setPriority(event.target.value)}
              className="rounded px-3 py-2 font-mono text-xs"
              style={style}
            >
              <option value="p1">P1</option>
              <option value="p2">P2</option>
              <option value="p3">P3</option>
              <option value="p4">P4</option>
              <option value="p5">P5</option>
            </select>
            <input
              aria-label="Incident assignee"
              type="number"
              min="1"
              value={assignedTo ?? ""}
              onChange={(event) =>
                setAssignedTo(
                  event.target.value ? Number(event.target.value) : undefined,
                )
              }
              placeholder="Assignee ID"
              className="w-28 rounded px-3 py-2 font-mono text-xs"
              style={style}
            />
            <button
              type="button"
              onClick={() => create.mutate()}
              className="rounded px-3 py-2 font-mono text-xs"
              style={{ background: "#00d4ff", color: "#06111a" }}
            >
              Create incident
            </button>
          </div>
        )}
      </div>
      {actionError && (
        <div
          role="alert"
          className="rounded px-3 py-2 font-mono text-xs"
          style={{
            background: "#3a1420",
            color: "#ffb3c1",
            border: "1px solid #ff6688",
          }}
        >
          {actionError}
        </div>
      )}
      <div className="grid grid-cols-1 xl:grid-cols-[minmax(280px,.8fr)_minmax(0,1.4fr)] gap-4">
        <GlassCard className="overflow-hidden">
          <div
            className="px-4 py-3 font-display font-semibold text-sm"
            style={{ borderBottom: "1px solid var(--t-border-light)" }}
          >
            Incidents
          </div>
          {incidents.data?.items.map((row) => (
            <button
              type="button"
              key={row.id}
              onClick={() => {
                setSelected(row.id)
                setActionError("")
              }}
              className="w-full text-left px-4 py-3"
              style={{
                borderBottom: "1px solid var(--t-border-alpha)",
                background: row.id === selected ? "var(--t-bg)" : "transparent",
              }}
            >
              <div className="font-mono text-xs">
                #{row.id} · {row.title}
              </div>
              <div
                className="font-mono text-[10px] mt-1"
                style={{ color: "var(--t-muted)" }}
              >
                {row.priority} · {row.category} · {row.status}
              </div>
            </button>
          ))}
          {!incidents.data?.items.length && (
            <div
              className="p-6 text-center font-mono text-xs"
              style={{ color: "var(--t-muted)" }}
            >
              No persisted incidents.
            </div>
          )}
        </GlassCard>
        <GlassCard>
          {item ? (
            <div className="space-y-4">
              <div>
                <h2 className="font-display font-semibold text-lg">
                  {item.title}
                </h2>
                <div
                  className="font-mono text-xs mt-1"
                  style={{ color: "var(--t-muted)" }}
                >
                  {item.priority} · {item.category} · assigned user{" "}
                  {item.assigned_to ?? "unassigned"} ·{" "}
                  {item.service_id
                    ? `service ${item.service_id}`
                    : "no service"}
                </div>
              </div>
              <div
                className="rounded p-3 font-mono text-xs"
                style={{
                  background: "var(--t-bg)",
                  color:
                    item.sla?.response_breached || item.sla?.resolution_breached
                      ? "#ff6688"
                      : "var(--t-muted)",
                }}
              >
                <div className="font-display font-semibold text-sm">
                  SLA timer
                </div>
                {item.sla ? (
                  <div className="mt-1">
                    Response deadline{" "}
                    {new Date(item.sla.response_deadline).toLocaleString()} ·
                    Resolution deadline{" "}
                    {new Date(item.sla.resolution_deadline).toLocaleString()} ·{" "}
                    {item.sla.paused_at
                      ? "Paused by configured state"
                      : "Running"}
                    {item.sla.response_breached || item.sla.resolution_breached
                      ? " · BREACHED"
                      : ""}
                  </div>
                ) : (
                  "No SLA policy configured for this priority/service."
                )}
              </div>
              <div
                className="rounded p-3 font-mono text-xs"
                style={{ background: "var(--t-bg)", color: "var(--t-muted)" }}
              >
                <div className="font-display font-semibold text-sm" style={{ color: "var(--t-text)" }}>
                  Incident RCA
                </div>
                {item.rca ? (
                  <>
                    <div className="mt-1" style={{ color: "#4ade80" }}>
                      Probable Root Cause: {item.rca.root_label}
                    </div>
                    <div className="mt-1">
                      Confidence: {(item.rca.confidence * 100).toFixed(1)}% · {item.rca.impact_summary}
                    </div>
                    <div className="mt-1">Supporting Evidence: {item.rca.evidence.length}</div>
                  </>
                ) : (
                  "No Incident-scoped RCA has been analyzed."
                )}
              </div>
              <div className="flex flex-wrap gap-2">
                {hasPermission("rca:execute") && (
                  <button
                    type="button"
                    onClick={analyzeSelectedRca}
                    disabled={analyzeRca.isPending || selected == null}
                    className="rounded px-3 py-2 font-mono text-xs"
                    style={style}
                  >
                    {analyzeRca.isPending ? "Analyzing RCA..." : "Analyze RCA"}
                  </button>
                )}
                {hasPermission("incidents:update") && status === "open" && (
                  <>
                    <button
                      type="button"
                      onClick={() => acknowledge.mutate(item.id)}
                      className="rounded px-3 py-2 font-mono text-xs"
                      style={style}
                    >
                      Acknowledge
                    </button>
                    <button
                      type="button"
                      onClick={() =>
                        transition.mutate({
                          id: item.id,
                          status: "investigating",
                        })
                      }
                      className="rounded px-3 py-2 font-mono text-xs"
                      style={style}
                    >
                      Investigating
                    </button>
                    <button
                      type="button"
                      onClick={() => resolve.mutate(item.id)}
                      className="rounded px-3 py-2 font-mono text-xs"
                      style={style}
                    >
                      Resolve
                    </button>
                  </>
                )}
                {hasPermission("incidents:update") &&
                  status === "investigating" && (
                    <>
                      <button
                        type="button"
                        onClick={() =>
                          transition.mutate({ id: item.id, status: "pending" })
                        }
                        className="rounded px-3 py-2 font-mono text-xs"
                        style={style}
                      >
                        Pending
                      </button>
                      <button
                        type="button"
                        onClick={() => resolve.mutate(item.id)}
                        className="rounded px-3 py-2 font-mono text-xs"
                        style={style}
                      >
                        Resolve
                      </button>
                    </>
                  )}
                {hasPermission("incidents:update") && status === "pending" && (
                  <>
                    <button
                      type="button"
                      onClick={() =>
                        transition.mutate({
                          id: item.id,
                          status: "investigating",
                        })
                      }
                      className="rounded px-3 py-2 font-mono text-xs"
                      style={style}
                    >
                      Investigating
                    </button>
                    <button
                      type="button"
                      onClick={() => resolve.mutate(item.id)}
                      className="rounded px-3 py-2 font-mono text-xs"
                      style={style}
                    >
                      Resolve
                    </button>
                  </>
                )}
                {hasPermission("incidents:update") && status === "resolved" && (
                  <>
                    <button
                      type="button"
                      onClick={() => close.mutate(item.id)}
                      className="rounded px-3 py-2 font-mono text-xs"
                      style={style}
                    >
                      Close incident
                    </button>
                    <button
                      type="button"
                      onClick={() => reopen.mutate(item.id)}
                      className="rounded px-3 py-2 font-mono text-xs"
                      style={style}
                    >
                      Reopen
                    </button>
                  </>
                )}
                {hasPermission("incidents:update") && activeStatus && (
                  <>
                    <input
                      aria-label="Incident assignee"
                      type="number"
                      min="1"
                      value={assignedTo ?? item.assigned_to ?? ""}
                      onChange={(event) =>
                        setAssignedTo(
                          event.target.value
                            ? Number(event.target.value)
                            : undefined,
                        )
                      }
                      placeholder="Assignee ID"
                      className="w-28 rounded px-3 py-2 font-mono text-xs"
                      style={style}
                    />
                    <button
                      type="button"
                      onClick={() => assign.mutate(item.id)}
                      className="rounded px-3 py-2 font-mono text-xs"
                      style={style}
                    >
                      Assign
                    </button>
                  </>
                )}
              </div>
              <div>
                <h3 className="font-display font-semibold text-sm">
                  Linked alerts
                </h3>
                <div
                  className="font-mono text-xs mt-2 space-y-1"
                  style={{ color: "var(--t-muted)" }}
                >
                  {item.alerts?.length
                    ? item.alerts.map((alert) => (
                        <div key={alert.id}>
                          #{alert.id} {alert.severity}: {alert.title} ·{" "}
                          {alert.device_name ?? "device unavailable"}{" "}
                          {alert.ip_address ? `(${alert.ip_address})` : ""}{" "}
                          {alert.interface_name
                            ? `· interface ${alert.interface_name}`
                            : ""}{" "}
                          · {alert.status}
                        </div>
                      ))
                    : "No alerts linked"}
                </div>
              </div>
              <div>
                <h3 className="font-display font-semibold text-sm">
                  Incident history
                </h3>
                <div
                  className="font-mono text-xs mt-2 space-y-1"
                  style={{ color: "var(--t-muted)" }}
                >
                  {item.history?.length
                    ? item.history.map((row) => (
                        <div key={row.id}>
                          {row.created_at} · {row.action}
                          {row.reason ? ` · ${row.reason}` : ""}
                        </div>
                      ))
                    : "No history recorded"}
                </div>
              </div>
              <div>
                <h3 className="font-display font-semibold text-sm">Comments</h3>
                {item.comments?.map((row) => (
                  <div
                    key={row.id}
                    className="mt-2 rounded p-2 font-mono text-xs"
                    style={{ background: "var(--t-bg)" }}
                  >
                    {row.body}
                  </div>
                ))}
                {hasPermission("incidents:update") && (
                  <div className="flex gap-2 mt-2">
                    <input
                      aria-label="Incident comment"
                      value={comment}
                      onChange={(event) => setComment(event.target.value)}
                      placeholder="Add operational comment"
                      className="flex-1 rounded px-3 py-2 font-mono text-xs"
                      style={style}
                    />
                    <button
                      type="button"
                      disabled={!comment.trim()}
                      onClick={() => addComment.mutate()}
                      className="rounded px-3 py-2 font-mono text-xs"
                      style={style}
                    >
                      Add
                    </button>
                  </div>
                )}
              </div>
              <div>
                <h3 className="font-display font-semibold text-sm">
                  Attachments
                </h3>
                <div
                  className="font-mono text-xs mt-2"
                  style={{ color: "var(--t-muted)" }}
                >
                  {item.attachments?.length
                    ? item.attachments.map((row) => row.file_name).join(" · ")
                    : "No attachments registered"}
                </div>
              </div>
            </div>
          ) : (
            <div
              className="p-8 text-center font-mono text-xs"
              style={{ color: "var(--t-muted)" }}
            >
              Select an incident to inspect evidence, comments, attachments and
              closure.
            </div>
          )}
        </GlassCard>
      </div>
    </div>
  )
}
