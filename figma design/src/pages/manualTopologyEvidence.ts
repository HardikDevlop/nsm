type RecordData = Record<string, unknown>
type Endpoint = { id: string; name?: string; backendId?: number; ipAddress?: string; subtitle?: string; portSources?: Record<string, string> }
type Connection = { from: string; to: string; fromPort?: string; toPort?: string; fromPortSource?: string; toPortSource?: string }

const portKey = (value: unknown) => String(value ?? "").trim().toLowerCase()
  .split(/\s+[·•]\s+/).pop()!.replace(/\s+/g, "")
  .replace(/^gigabitethernet/, "gi").replace(/^fastethernet/, "fa")
  .replace(/^tengigabitethernet/, "te").replace(/^ethernet/, "eth")
const known = (value: unknown) => Boolean(value) && !/unknown|n\/a/i.test(String(value))

export function comparePhysicalConnection(link: Connection, devices: Endpoint[], observations: RecordData[]): RecordData & { status: string } {
  const aliases = (id: string) => {
    const device = devices.find(item => item.id === id)
    return new Set([id, device?.backendId, device?.name, device?.ipAddress, device?.subtitle]
      .filter(value => value != null && value !== "").map(value => String(value).trim().toLowerCase()))
  }
  const source = aliases(link.from), target = aliases(link.to)
  const isAssignedPort = (side: "from" | "to") => {
    const port = side === "from" ? link.fromPort : link.toPort
    const origin = side === "from" ? link.fromPortSource : link.toPortSource
    const device = devices.find(item => item.id === link[side])
    return Boolean(port) && (origin ?? device?.portSources?.[port!]) === "manual_fallback"
  }
  const candidates = observations.flatMap(item => {
    const from = String(item.from ?? item.source_node ?? item.source_device ?? "").trim().toLowerCase()
    const to = String(item.to ?? item.target_node ?? item.target_device ?? "").trim().toLowerCase()
    const direct = source.has(from) && target.has(to)
    const reverse = target.has(from) && source.has(to)
    if (!direct && !reverse) return []
    const a = item.fromPort ?? item.source_port ?? item.local_port ?? ""
    const b = item.toPort ?? item.target_port ?? item.remote_port ?? ""
    const sourcePort = reverse ? b : a, targetPort = reverse ? a : b
    const evidence = item.verified !== false && Boolean(item.evidence_available || item.evidence_source || item.protocol || item.verified)
    const mismatch = (known(sourcePort) && portKey(sourcePort) !== portKey(link.fromPort)) ||
      (known(targetPort) && portKey(targetPort) !== portKey(link.toPort))
    const assignedSource = !known(sourcePort) && isAssignedPort("from") && known(targetPort)
    const assignedTarget = !known(targetPort) && isAssignedPort("to") && known(sourcePort)
    const hasSourcePort = known(sourcePort) || assignedSource
    const hasTargetPort = known(targetPort) || assignedTarget
    const status = !evidence ? "UNKNOWN" : mismatch ? "PORT_MISMATCH" :
      hasSourcePort && hasTargetPort ? "VERIFIED" :
      hasSourcePort || hasTargetPort ? "PARTIAL_DISCOVERY" : "UNKNOWN"
    return [{ ...item, from: link.from, to: link.to, fromPort: sourcePort, toPort: targetPort, source_device: devices.find(d => d.id === link.from)?.name || link.from,
      target_device: devices.find(d => d.id === link.to)?.name || link.to,
      source_port: assignedSource ? `${link.fromPort} (assigned)` : sourcePort || "Not discovered",
      target_port: assignedTarget ? `${link.toPort} (assigned)` : targetPort || "Not discovered",
      source_port_assigned: assignedSource, target_port_assigned: assignedTarget,
      evidence_source: item.evidence_source ?? item.protocol ?? item.evidenceSource,
      status, reason: !evidence ? "Physical evidence is unavailable for this connection." :
        status === "VERIFIED" && (assignedSource || assignedTarget) ? "Connection verified from the discovered endpoint port and device-pair evidence. The other endpoint uses an assigned manual port." :
        !mismatch && (!known(sourcePort) || !known(targetPort)) ? "Only one endpoint port was discovered; the full port-to-port connection is not verified." : undefined }]
  })
  return candidates.find(item => item.status === "VERIFIED") ||
    candidates.find(item => item.status === "UNKNOWN") || candidates[0] || {
      status: "UNKNOWN", reason: "No live physical evidence was found for this device pair.",
    }
}
