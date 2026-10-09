import { normalizeKnownDeviceIdentity } from "./deviceIdentity"

const DEFAULT_API_BASE = "/api/v1"
const API_BASE = (
  import.meta.env.VITE_API_BASE_URL ?? DEFAULT_API_BASE
).replace(/\/$/, "")
const GET_CACHE_TTL_MS = 30_000
const GET_CACHE_PREFIX = "nms.api.cache.v1:"

let authToken: string | null = null
let authPromise: Promise<string> | null = null
const getCache = new Map<string, { expiresAt: number value: unknown }>()
const inflightRequests = new Map<string, Promise<unknown>>()

function buildUrl(path: string) {
  return `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`
}

export interface BrandingRecord {
  application_name: string
  logo_url: string | null
  allowed_themes: Array<"light" | "dark">
}

export async function getBranding(
  signal?: AbortSignal,
): Promise<BrandingRecord> {
  const response = await fetch(buildUrl("/branding"), { signal })
  if (!response.ok) throw new Error("Unable to load application branding")
  return response.json() as Promise<BrandingRecord>
}

/** Load token from localStorage if present. Does NOT auto-login. */
async function ensureAuth(): Promise<string> {
  if (authToken) return authToken
  if (authPromise) return authPromise

  const cached = window.localStorage.getItem("nms_access_token")
  if (cached) {
    authToken = cached
    return cached
  }

  throw new Error("Not authenticated")
}

function cacheKey(path: string, token: string) {
  return `${token}::${path}`
}

function readCached<T>(key: string): T | null {
  const now = Date.now()
  const cached = getCache.get(key)
  if (cached && cached.expiresAt > now) return cached.value as T
  if (cached) getCache.delete(key)
  try {
    const persisted = window.sessionStorage.getItem(`${GET_CACHE_PREFIX}${key}`)
    if (!persisted) return null
    const parsed = JSON.parse(persisted) as { expiresAt?: number value?: T }
    if (!parsed?.expiresAt || parsed.expiresAt <= now) {
      window.sessionStorage.removeItem(`${GET_CACHE_PREFIX}${key}`)
      return null
    }
    getCache.set(key, {
      expiresAt: parsed.expiresAt,
      value: parsed.value as unknown,
    })
    return parsed.value ?? null
  } catch {
    return null
  }
}

function writeCached<T>(key: string, value: T) {
  const record = { expiresAt: Date.now() + GET_CACHE_TTL_MS, value }
  getCache.set(key, record)
  try {
    window.sessionStorage.setItem(
      `${GET_CACHE_PREFIX}${key}`,
      JSON.stringify(record),
    )
  } catch {
    // Optional cache only.
  }
}

function clearRequestCache() {
  getCache.clear()
  inflightRequests.clear()
  try {
    const keys: string[] = []
    for (let index = 0; index < window.sessionStorage.length; index++) {
      const key = window.sessionStorage.key(index)
      if (key?.startsWith(GET_CACHE_PREFIX)) keys.push(key)
    }
    keys.forEach((key) => window.sessionStorage.removeItem(key))
  } catch {
    // ignore storage failures
  }
}

export function clearApiCache() {
  clearRequestCache()
}

function invalidateGetCache() {
  clearRequestCache()
}

export function clearNmsClientState() {
  authToken = null
  authPromise = null
  clearRequestCache()
}

export function invalidateNmsGetCache() {
  invalidateGetCache()
}

function friendlyApiMessage(status: number, detail: string): string {
  const normalized = detail.trim()
  if (status === 401)
    return "Your session has expired or the credentials are invalid. Please sign in again."
  if (status === 403)
    return "You do not have permission to perform this action."
  if (status === 400) {
    if (
      /ips\[\]/i.test(normalized) ||
      /ip(?:s)?\[\] is required/i.test(normalized)
    ) {
      return "Please provide the required device information."
    }
    return normalized || "The request could not be processed."
  }
  if (status === 404) return "Device not found."
  if (status === 409) {
    if (/^DEVICE_ALREADY_CONNECTED:(ssh|telnet)$/i.test(normalized)) return normalized
    return "This item is already being processed."
  }
  if (status === 422) return "The submitted data is incomplete or invalid."
  if (status === 502 || status === 503 || status === 504)
    return "The service is temporarily unavailable. Please retry in a moment."
  if (status >= 500)
    return "An unexpected server error occurred. Please try again."
  return normalized || "Request failed."
}

function networkMessage(error: unknown): string {
  if (error instanceof DOMException && error.name === "AbortError")
    return "Request was cancelled."
  return "Unable to connect to the server."
}

/** Explicit login — stores token in memory + localStorage. */
export async function login(email: string, password: string): Promise<string> {
  // A new login must never inherit a previous user's cached API/session data.
  authToken = null
  authPromise = null
  window.localStorage.removeItem("nms_access_token")
  window.sessionStorage.removeItem("nms.user.cache.v2")
  clearRequestCache()

  let response: Response
  try {
    response = await fetch(buildUrl("/auth/login"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    })
  } catch (error) {
    throw new Error(networkMessage(error))
  }
  if (!response.ok) {
    let detail = ""
    try {
      const body = (await response.json()) as { detail?: string }
      detail = body.detail ?? ""
    } catch {
      // Non-JSON responses still get a safe status-based message.
    }
    throw new Error(
      response.status === 401
        ? "Invalid email or password."
        : friendlyApiMessage(response.status, detail),
    )
  }
  const payload = (await response.json()) as { access_token?: unknown }
  if (typeof payload.access_token !== "string" || !payload.access_token) {
    throw new Error("The server returned an invalid login response.")
  }
  authToken = payload.access_token
  window.localStorage.setItem("nms_access_token", authToken)
  return authToken
}

/** Clear auth state. */
export async function serverLogout(): Promise<void> {
  // Capture the token before local logout clears it. Using requestJson here
  // raced with apiLogout() and left the server-side session active.
  const token = authToken || window.localStorage.getItem("nms_access_token")
  try {
    if (token) {
      await fetch(buildUrl("/auth/logout"), {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        keepalive: true,
      })
    }
  } finally {
    logout()
  }
}

export function logout() {
  authToken = null
  authPromise = null
  window.localStorage.removeItem("nms_access_token")
  clearRequestCache()
}

export async function requestJson<T>(
  path: string,
  init: RequestInit = {},
  retryUnauthorized = true,
): Promise<T> {
  const token = await ensureAuth()
  const method = (init.method ?? "GET").toUpperCase()
  // React Query supplies an AbortSignal for cancellable requests. Cancellation
  // and GET deduplication are independent concerns: keep both enabled so
  // concurrent page consumers share one request without losing cancellation.
  const canCache = method === "GET" && !init.body && init.cache !== "no-store"
  const isMutation =
    method === "POST" ||
    method === "PUT" ||
    method === "PATCH" ||
    method === "DELETE"
  const key = canCache ? cacheKey(path, token) : ""

  if (canCache) {
    const cached = readCached<T>(key)
    if (cached !== null) return cached
    const existing = inflightRequests.get(key)
    if (existing) return existing as Promise<T>
  }

  const timeoutController = new AbortController()
  // Report ranges can legitimately span months/years and require larger
  // aggregate queries than normal UI reads. Keep the normal guard for the
  // rest of the app, but allow report generation enough time to finish.
  const timeoutMs = path.startsWith('/reports/management') ? 120_000 : 15_000
  let didTimeout = false
  const timeoutId = window.setTimeout(() => {
    didTimeout = true
    timeoutController.abort()
  }, timeoutMs)
  const externalSignal = init.signal
  if (externalSignal) {
    if (externalSignal.aborted) timeoutController.abort()
    else
      externalSignal.addEventListener(
        "abort",
        () => timeoutController.abort(),
        { once: true },
      )
  }

  const startedAt = performance.now()
  const request = fetch(buildUrl(path), {
    ...init,
    signal: timeoutController.signal,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
      ...(init.headers ?? {}),
    },
  })
    .then(async (response) => {
      if (response.status === 401) {
        authToken = null
        window.localStorage.removeItem("nms_access_token")
        clearRequestCache()
        if (retryUnauthorized) return requestJson<T>(path, init, false)
        throw new Error(friendlyApiMessage(response.status, ""))
      }

      if (!response.ok) {
        let detail = ""
        try {
          const body = (await response.json()) as {
            detail?: string | { message?: string }
            error?: {
              code?: string
              message?: string
              detail?: string
              suggestion?: string
              request_id?: string
            }
          }
          if (body.error) {
            const safe = [
              body.error.message,
              body.error.detail,
              body.error.suggestion,
            ]
              .filter(Boolean)
              .join(" ")
            detail = safe || body.error.code || ""
          } else {
            detail =
              typeof body.detail === "string"
                ? body.detail
                : (body.detail?.message ?? "")
          }
        } catch {
          /* non-JSON error */
        }
        throw new Error(friendlyApiMessage(response.status, detail))
      }

      const payload = await response.json()
      return normalizeKnownDeviceIdentity(payload) as T
    })
    .catch((error) => {
      // Browser fetch failures are TypeError instances; do not leak browser or
      // runtime implementation text into the UI.
      if (error instanceof Error) {
        if (error.name === "AbortError" && didTimeout)
          throw new Error("Request timed out. Please try again.")
        if (error.name === "TypeError") throw new Error(networkMessage(error))
        throw error
      }
      throw new Error(networkMessage(error))
    })

  if (canCache) inflightRequests.set(key, request as Promise<unknown>)
  try {
    const result = await request
    if (canCache) writeCached(key, result)
    if (isMutation) invalidateGetCache()
    return result
  } finally {
    window.clearTimeout(timeoutId)
    if (canCache) inflightRequests.delete(key)
  }
}

export interface DashboardSummary {
  total_devices: number
  online_devices: number
  offline_devices: number
  health_counts: Record<"online" | "offline" | "degraded" | "stale" | "unknown", number>
  active_alerts: number
  critical_alerts: number
  recent_events: number
}

export interface FlowAnalyticsItem {
  name: string
  bytes: number
  packets: number
  flows: number
  source?: "sflow" | "ipfix" | "unknown"
  quality?: "accounted" | "estimated" | "counter" | "unknown"
  sampled?: boolean | null
  sampling_rate?: number | null
}

export interface FlowTrendItem {
  timestamp: string
  bytes: number
  packets: number
  flows: number
}

export interface FlowAnalyticsResponse {
  items: FlowAnalyticsItem[]
  page?: number
  page_size?: number
  filters?: {
    hours?: number
    device_id?: number | null
    site_id?: number | null
    protocol?: FlowProtocol | null
  }
  from?: string
  to?: string
}

export interface FlowRecord {
  id: number
  device_id: number | null
  device_name: string | null
  exporter_ip: string
  input_ifindex: number | null
  input_interface_name: string | null
  output_ifindex: number | null
  output_interface_name: string | null
  protocol: FlowProtocol
  source_version: string | null
  flow_start: string | null
  flow_end: string | null
  src_ip: string | null
  dst_ip: string | null
  src_port: number | null
  dst_port: number | null
  ip_protocol: number | null
  bytes: number
  packets: number
}

export interface FlowRecordsResponse {
  items: FlowRecord[]
  page: number
  page_size: number
  from: string
  to: string
}

export type FlowProtocol = "sflow" | "ipfix"

export interface FlowAnalyticsFilters {
  hours: number
  device_id?: number
  site_id?: number
  protocol?: FlowProtocol
  page?: number
  page_size?: number
}

export async function getFlowAnalytics(
  dimension: "talkers" | "sources" | "destinations" | "applications" | "protocols" | "conversations" | "interfaces",
  filters: FlowAnalyticsFilters,
): Promise<FlowAnalyticsResponse> {
  const query = new URLSearchParams({
    hours: String(filters.hours),
    page: String(filters.page ?? 1),
    page_size: String(filters.page_size ?? 10),
  })
  if (filters.device_id != null)
    query.set("device_id", String(filters.device_id))
  if (filters.site_id != null) query.set("site_id", String(filters.site_id))
  if (filters.protocol) query.set("protocol", filters.protocol)
  return requestJson<FlowAnalyticsResponse>(
    `/flows/analytics/${dimension}?${query}`,
  )
}

export async function getFlowTrends(
  filters: FlowAnalyticsFilters,
): Promise<FlowTrendItem[]> {
  const query = new URLSearchParams({
    hours: String(filters.hours),
    bucket: filters.hours > 48 ? "day" : "hour",
  })
  if (filters.device_id != null)
    query.set("device_id", String(filters.device_id))
  if (filters.site_id != null) query.set("site_id", String(filters.site_id))
  if (filters.protocol) query.set("protocol", filters.protocol)
  const response = await requestJson<{ items: FlowTrendItem[] }>(
    `/flows/analytics/trends?${query}`,
  )
  return response.items
}

export async function getFlowRecords(
  filters: FlowAnalyticsFilters,
): Promise<FlowRecordsResponse> {
  const query = new URLSearchParams({
    hours: String(filters.hours),
    page: String(filters.page ?? 1),
    page_size: String(filters.page_size ?? 25),
  })
  if (filters.device_id != null)
    query.set("device_id", String(filters.device_id))
  if (filters.site_id != null) query.set("site_id", String(filters.site_id))
  if (filters.protocol) query.set("protocol", filters.protocol)
  return requestJson<FlowRecordsResponse>(`/flows/analytics/records?${query}`)
}

export interface APMFilters {
  hours: number
  application_id?: number
  service_id?: number
  device_id?: number
  site_id?: number
  page?: number
  page_size?: number
}

export interface APMOverviewItem {
  application_id: number
  service_id: number
  application_name: string
  service_name: string
  request_count: number
  error_count: number
  error_rate: number
  response_time_ms: number
  slow_transaction_count: number
  availability_percent: number
}

export interface APMServiceMetric {
  observed_at: string
  transaction_id?: number | null
  response_time_ms: number
  request_count: number
  error_count: number
  slow_transaction_count: number
  availability_percent: number
}

export interface APMDependencyItem {
  source_service_id: number
  source_service_name: string
  target_service_id?: number | null
  target_name: string
  dependency_type?: string | null
  call_count: number
  error_count: number
  error_rate: number
  response_time_ms: number
}

export interface APMApplicationOption {
  id: number
  name: string
  environment: string
}
export interface APMServiceOption {
  id: number
  application_id: number
  name: string
  service_key: string
  device_id?: number | null
  site_id?: number | null
  application_name: string
}

function apmQuery(filters: APMFilters): string {
  const query = new URLSearchParams({
    hours: String(filters.hours),
    page: String(filters.page ?? 1),
    page_size: String(filters.page_size ?? 50),
  })
  for (const [key, value] of Object.entries(filters))
    if (
      key !== "hours" &&
      key !== "page" &&
      key !== "page_size" &&
      value != null
    )
      query.set(key, String(value))
  return `?${query}`
}

export async function listAPMApplications(): Promise<APMApplicationOption[]> {
  return requestJson("/apm/applications")
}
export async function listAPMServices(
  applicationId?: number,
): Promise<APMServiceOption[]> {
  return requestJson(
    `/apm/services${
      applicationId == null ? "" : `?application_id=${applicationId}`
    }`,
  )
}
export async function getAPMOverview(
  filters: APMFilters,
): Promise<{ items: APMOverviewItem[] from: string to: string }> {
  return requestJson(`/apm/overview${apmQuery(filters)}`)
}
export async function getAPMServiceMetrics(
  serviceId: number,
  filters: APMFilters,
): Promise<{ items: APMServiceMetric[] from: string to: string }> {
  return requestJson(`/apm/services/${serviceId}/metrics${apmQuery(filters)}`)
}
export async function getAPMDependencies(
  filters: APMFilters,
): Promise<{ items: APMDependencyItem[] from: string to: string }> {
  return requestJson(`/apm/dependencies${apmQuery(filters)}`)
}

export interface CMDBType {
  id: number
  name: string
  category: string
  description?: string | null
  created_at: string
  updated_at: string
  deleted_at?: string | null
}
export interface CMDBItem {
  id: number
  ci_type_id: number
  name: string
  external_key?: string | null
  lifecycle_state: string
  owner_user_id?: number | null
  organization_id?: number | null
  device_id?: number | null
  interface_id?: number | null
  site_id?: number | null
  application_id?: number | null
  environment?: string | null
  attributes: Record<string, unknown>
  created_at: string
  updated_at: string
  first_discovered?: string | null
  last_seen?: string | null
  last_synchronized?: string | null
  sync_source?: string | null
  deleted_at?: string | null
}
export interface CMDBRelationship {
  id: number
  source_ci_id: number
  target_ci_id: number
  relationship_type: string
  created_at: string
  managed_by?: string
  source_key?: string | null
  deleted_at?: string | null
}
export interface CMDBHistory {
  id: number
  ci_id: number
  changed_by_user_id?: number | null
  action: string
  field_name?: string | null
  old_value?: string | null
  new_value?: string | null
  changed_at: string
}
export interface CMDBItemFilters {
  search?: string
  ci_type_id?: number
  lifecycle_state?: string
  owner_user_id?: number
  device_id?: number
  site_id?: number
  application_id?: number
  skip?: number
  limit?: number
}

export async function listCMDBTypes(): Promise<CMDBType[]> {
  return requestJson("/cmdb/types")
}
export async function listCMDBItems(
  filters: CMDBItemFilters = {},
): Promise<CMDBItem[]> {
  const query = new URLSearchParams()
  for (const [key, value] of Object.entries(filters))
    if (value != null && value !== "") query.set(key, String(value))
  return requestJson(`/cmdb/items${query.toString() ? `?${query}` : ""}`)
}
export async function getCMDBRelationships(
  ciId: number,
): Promise<CMDBRelationship[]> {
  return requestJson(`/cmdb/items/${ciId}/relationships`)
}
export async function getCMDBHistory(ciId: number): Promise<CMDBHistory[]> {
  return requestJson(`/cmdb/items/${ciId}/history`)
}
export interface CMDBSyncResult {
  created: number
  updated: number
  unchanged: number
  skipped: number
  errors: number
  relationships_created: number
  relationships_updated: number
  relationships_removed: number
  relationships_unchanged: number
  started_at: string
  completed_at: string
}
export async function syncCMDB(): Promise<CMDBSyncResult> {
  return requestJson("/cmdb/sync", { method: "POST" })
}

export interface DeviceRecord {
  id: number
  hostname: string
  ip_address: string
  snmp_version?: string | null
  vendor?: string | null
  mac_address?: string | null
  status: string
  monitoring_status: boolean
  last_seen?: string | null
  created_at: string
  uptime_seconds: number
  downtime_seconds: number
  vendor_id?: number | null
  device_type_id?: number | null
  site_id?: number | null
  serial_number?: string | null
  model?: string | null
  firmware_version?: string | null
  vendor_name?: string | null
  device_type?: string | null
  last_status_change?: string | null
  topology_metadata?: {
    port?: string
    vlans?: string[]
    ips?: string[]
    location?: string | null
  }
}

export interface DeviceOptionRecord {
  id: number
  hostname: string
  ip_address: string
  mac_address?: string | null
  model?: string | null
  vendor_name?: string | null
  device_type?: string | null
  status: string
}

export interface SiteRecord {
  id: number
  organization_id: number
  name: string
  city?: string | null
  state?: string | null
  latitude?: number | null
  longitude?: number | null
}

export interface DeviceTypeRecord {
  id: number
  name: string
  description?: string | null
  created_at: string
  max_concurrent_sessions?: number
}

export interface DeviceMetricRecord {
  id: number
  device_id: number
  cpu_usage?: number | null
  memory_usage?: number | null
  disk_usage?: number | null
  temperature?: number | null
  latency?: number | null
  packet_loss?: number | null
  bandwidth_usage?: number | null
  created_at: string
}

export interface AlertRecord {
  id: number
  device_id?: number | null
  hostname?: string | null
  ip_address?: string | null
  ip?: string | null
  severity: string
  title: string
  description?: string | null
  status: string
  acknowledged_by?: number | null
  resolved_at?: string | null
  created_at: string
}

export interface EventRecord {
  id: number
  device_id?: number | null
  event_type: string
  description?: string | null
  timestamp: string
}

export interface InterfaceRecord {
  id: number
  device_id: number
  interface_name: string
  status: string
  speed?: string | null
  traffic_in: number
  traffic_out: number
  packet_errors: number
  last_updated: string
}

export interface NotificationRecord {
  id: number
  alert_id?: number | null
  channel: string
  sent_to: string
  status: string
  sent_at?: string | null
}

export interface ChunkedDiscoveryRequest {
  network_range: string
  site_id?: number | null
  ports?: number[]
  timeout_ms?: number
  snmp_community?: string
  scan_icmp?: boolean
  scan_ports?: boolean
  scan_snmp?: boolean
  max_hosts?: number
  chunk_size?: number
  modules?: string[]
}

export interface ChunkedDiscoveryProgress {
  job_id: string
  status: string
  network_range: string
  total_ips: number
  chunk_size: number
  chunks_total: number
  chunks_completed: number
  ips_scanned: number
  discovered_count: number
  progress_pct: number
  elapsed_seconds: number
  error?: string | null
}

export interface ChunkedDiscoveryStartResponse {
  job_id: string
  total_ips: number
  chunks_total: number
  chunk_size: number
  status: string
}

export interface ChunkedDiscoveryEvent {
  event: "progress" | "discovered" | "complete" | "error"
  data: any
}

export interface ChunkedDiscoveryJobStatus {
  progress: ChunkedDiscoveryProgress
  discovered: Record<string, unknown>[]
}

export interface AddDiscoveredDevicesPayload {
  devices: Record<string, unknown>[]
  site_id?: number | null
  discovery_source?: "icmp" | "snmp" | null
  snmp_version?: "v2c" | "v3"
  communities?: string[]
  username?: string | null
  auth_protocol?: string | null
  auth_password?: string | null
  privacy_protocol?: string | null
  privacy_password?: string | null
  security_level?: string | null
}

export interface MonitorDevicePayload {
  ip: string
  hostname?: string | null
  vendor?: string | null
  mac_address?: string | null
  site_id?: number | null
  device_id?: number | null
}

export async function getDashboardSummary(): Promise<DashboardSummary> {
  return requestJson<DashboardSummary>("/dashboard/summary")
}

export interface ReportManagementFilters {
  device_type_id?: number | null
  device_id?: number | null
  site_id?: number | null
  device_status?: "all" | "up" | "down" | "unreachable"
  alert_severity?: "all" | "critical" | "high" | "medium" | "low" | "warning" | "info"
  protocol?: "all" | "snmp" | "icmp"
  period?: "today" | "yesterday" | "weekly" | "monthly" | "yearly" | "custom"
  start_date?: string | null
  end_date?: string | null
}

export interface ReportSchedule {
  id: number
  name: string
  enabled: boolean
  frequency: "daily" | "weekly" | "monthly"
  run_time: string
  timezone?: string | null
  report_format: "csv"
  filters: ReportManagementFilters
  created_at: string
  updated_at: string
  last_run_at?: string | null
  next_run_at?: string | null
}

export interface GeneratedReport {
  id: number
  schedule_id?: number | null
  report_name: string
  format: string
  status: "RUNNING" | "SUCCESS" | "FAILED"
  period_start: string
  period_end: string
  generated_at: string
  file_size?: number | null
  error_message?: string | null
}

export async function getReportSchedules() {
  return requestJson<ReportSchedule[]>("/reports/schedules")
}
export async function createReportSchedule(
  payload: Omit<ReportSchedule, "id" | "created_at" | "updated_at" | "last_run_at" | "next_run_at">,
) {
  return requestJson<ReportSchedule>("/reports/schedules", {
    method: "POST",
    body: JSON.stringify(payload),
  })
}
export async function updateReportSchedule(
  id: number,
  payload: Partial<Omit<ReportSchedule, "id" | "created_at" | "updated_at">>,
) {
  return requestJson<ReportSchedule>(`/reports/schedules/${id}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  })
}
export async function deleteReportSchedule(id: number) {
  await requestJson<void>(`/reports/schedules/${id}`, { method: "DELETE" })
}
export async function getGeneratedReports() {
  return requestJson<GeneratedReport[]>("/reports/generated")
}
export async function downloadGeneratedReport(id: number) {
  const token = await ensureAuth()
  const response = await fetch(buildUrl(`/reports/generated/${id}/download`), {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!response.ok) throw new Error(`Request failed: ${response.status}`)
  return {
    blob: await response.blob(),
    filename:
      response.headers
        .get("Content-Disposition")
        ?.match(/filename="?([^";]+)"?/)?.[1] ?? `generated-report-${id}.csv`,
  }
}

export interface ReportEmailScheduleStatus {
  enabled: boolean
  schedule: string
  timezone: string
  report_period: "yesterday"
  format: "xlsx"
  recipient_count: number
  smtp_configured: boolean
}

export async function getReportManagementEmailSchedule(): Promise<ReportEmailScheduleStatus> {
  return requestJson<ReportEmailScheduleStatus>(
    "/reports/management/email-schedule",
  )
}

export interface ReportInterfaceDetail {
  interface_id: number
  name?: string | null
  admin_status?: string | null
  operational_status?: string | null
  speed?: string | null
  avg_utilization_pct?: number | null
  max_utilization_pct?: number | null
  p95_utilization_pct?: number | null
  avg_inbound_mbps?: number | null
  avg_outbound_mbps?: number | null
  avg_error_rate_pct?: number | null
  current_status?: string | null
}

export interface ReportInventory {
  hostname?: string | null
  ip_address?: string | null
  mac_address?: string | null
  device_type?: string | null
  vendor?: string | null
  model?: string | null
  serial_number?: string | null
  os_version?: string | null
  firmware_version?: string | null
  site?: string | null
  snmp_version?: string | null
  first_discovered_at?: string | null
  last_seen_at?: string | null
}

export interface ReportManagementRecord {
  device_id: number
  hostname: string
  ip_address: string
  site_name?: string | null
  device_type_name?: string | null
  protocol: string
  availability_pct: number | null
  downtime_seconds: number
  outage_count: number
  longest_outage_seconds: number
  last_outage_time?: string | null
  last_recovery_time?: string | null
  current_status: string
  snmp_success_rate?: number | null
  icmp_success_rate?: number | null
  snmp_health: string
  performance_score?: number | null
  interface_count?: number | null
  interface_down_count?: number | null
  avg_cpu_percent?: number | null
  avg_memory_percent?: number | null
  avg_latency_ms?: number | null
  packet_loss_pct?: number | null
  max_cpu_percent?: number | null
  p95_cpu_percent?: number | null
  max_memory_percent?: number | null
  p95_memory_percent?: number | null
  max_latency_ms?: number | null
  p95_latency_ms?: number | null
  avg_packet_loss_pct?: number | null
  max_packet_loss_pct?: number | null
  interface_details: ReportInterfaceDetail[]
  interface_details_total: number
  interface_details_truncated: boolean
  alert_details: ReportAlertDetail[]
  alert_details_total: number
  alert_details_truncated: boolean
  inventory: ReportInventory
  alert_count: number
  critical_alert_count: number
  warning_alert_count: number
  active_alert_count: number
  resolved_alert_count: number
  alert_mttr_seconds?: number | null
  sla_target_percent?: number | null
  sla_variance_percent?: number | null
  allowed_downtime_seconds?: number | null
  sla_breach_seconds?: number | null
  sla_status: string
  period_start: string
  period_end: string
}

export interface ReportAlertDetail {
  alert_id: number
  device_id?: number | null
  device_name?: string | null
  site_name?: string | null
  severity: string
  title: string
  description?: string | null
  created_at?: string | null
  acknowledged_at?: string | null
  acknowledged_by?: number | null
  resolved_at?: string | null
  duration_seconds?: number | null
  status: string
}

export interface ReportManagementSection {
  title: string
  count: number
  average?: number | null
  maximum?: number | null
  minimum?: number | null
}

export interface ReportTrendAvailabilityPoint {
  bucket: string
  availability_percent: number | null
}
export interface ReportTrendPerformancePoint {
  bucket: string
  cpu_avg: number | null
  memory_avg: number | null
  latency_avg_ms: number | null
}
export interface ReportTrendBandwidthPoint {
  bucket: string
  rx_mbps: number | null
  tx_mbps: number | null
}
export interface ReportTrendAlertPoint {
  bucket: string
  total: number
  critical: number
  warning: number
  info: number
}
export interface ReportManagementTrends {
  bucket_granularity: "hourly" | "daily" | "monthly"
  availability: ReportTrendAvailabilityPoint[]
  performance: ReportTrendPerformancePoint[]
  bandwidth: ReportTrendBandwidthPoint[]
  alerts: ReportTrendAlertPoint[]
}

export interface ReportManagementSummary {
  filters: ReportManagementFilters
  period_start: string
  period_end: string
  total_devices: number
  total_records: number
  availability_pct: number | null
  downtime_seconds: number
  avg_snmp_health?: number | null
  avg_performance_score?: number | null
  sla_met_pct: number
  sla_configured_devices: number
  sla_met_devices: number
  sla_breached_devices: number
  sla_unknown_devices: number
  snmp_devices: number
  icmp_devices: number
  up_devices: number
  down_devices: number
  unreachable_devices: number
  total_alerts: number
  critical_alerts: number
  total_outages: number
  warning_alerts: number
  info_alerts: number
  active_alerts: number
  resolved_alerts: number
  acknowledged_alerts: number
  alert_mttr_seconds?: number | null
  most_affected_device_id?: number | null
  most_affected_device_name?: string | null
  alert_details: ReportAlertDetail[]
  alert_details_total: number
  alert_details_truncated: boolean
  sections: Record<string, ReportManagementSection>
  records: ReportManagementRecord[]
  trends: ReportManagementTrends
}

function appendQueryParams(
  query: URLSearchParams,
  filters: Record<string, unknown>,
) {
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "")
      query.set(key, String(value))
  })
}

export async function getReportManagement(
  filters: ReportManagementFilters,
): Promise<ReportManagementSummary> {
  const query = new URLSearchParams()
  appendQueryParams(query, filters)
  const suffix = query.size ? `?${query.toString()}` : ""
  return requestJson<ReportManagementSummary>(`/reports/management${suffix}`)
}

export async function getReportManagementOptions(): Promise<{
  device_types: DeviceTypeRecord[]
  sites: SiteRecord[]
  devices: DeviceOptionRecord[]
}> {
  return requestJson("/reports/management/options")
}

export async function downloadReportManagementCSV(
  filters: ReportManagementFilters,
): Promise<Blob> {
  const query = new URLSearchParams()
  appendQueryParams(query, { ...filters, format: "csv" })
  const token = await ensureAuth()
  const response = await fetch(
    buildUrl(`/reports/management/export?${query.toString()}`),
    {
      headers: { Authorization: `Bearer ${token}` },
    },
  )
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`)
  }
  return response.blob()
}

export async function detectLocalSubnet(): Promise<{
  subnet: string
  ip: string | null
}> {
  return requestJson<{ subnet: string ip: string | null }>(
    "/discovery/local-subnet",
  )
}

export async function listDevices(params?: {
  skip?: number
  limit?: number
}): Promise<DeviceRecord[]> {
  const query = new URLSearchParams()
  if (params?.skip != null) query.set("skip", String(params.skip))
  if (params?.limit != null) query.set("limit", String(params.limit))
  const suffix = query.size ? `?${query.toString()}` : ""
  return requestJson<DeviceRecord[]>(`/devices${suffix}`)
}

export async function listDeviceOptions(params?: {
  skip?: number
  limit?: number
}): Promise<DeviceOptionRecord[]> {
  const query = new URLSearchParams()
  if (params?.skip != null) query.set("skip", String(params.skip))
  if (params?.limit != null) query.set("limit", String(params.limit))
  const suffix = query.size ? `?${query.toString()}` : ""
  return requestJson<DeviceOptionRecord[]>(`/devices/options${suffix}`)
}

export interface RemoteAccessTestResponse {
  success: boolean
  protocol: "ssh" | "telnet"
  host: string | null
  port: number | null
  latency?: number
  error_code?: string | null
  stage?: string | null
  message?: string | null
  credential_id?: number | null
  connection_metadata?: Record<string, unknown>
  requires_trust?: boolean
  key_type?: string
  fingerprint?: string
  stored_fingerprint?: string
  received_fingerprint?: string
  host_key_id?: number
}

export interface RemoteAccessCredentialRecord {
  id: number
  device_id: number
  protocol: "ssh" | "telnet"
  port: number
  username: string
  auth_type: "password" | "private_key"
  is_verified: boolean
  last_verified_at: string | null
  created_by: number | null
  created_at: string
  updated_at: string
}

export async function listRemoteAccessCredentials(deviceId?: number): Promise<RemoteAccessCredentialRecord[]> {
  const suffix = deviceId ? `?device_id=${encodeURIComponent(deviceId)}` : ""
  return requestJson<RemoteAccessCredentialRecord[]>(`/remote-access/credentials${suffix}`)
}

export async function updateRemoteAccessCredential(id: number, payload: {
  username?: string
  secret?: string
  port?: number
  auth_type?: "password" | "private_key"
}): Promise<RemoteAccessCredentialRecord> {
  return requestJson<RemoteAccessCredentialRecord>(`/remote-access/credentials/${id}`, {
    method: "PATCH", body: JSON.stringify(payload),
  })
}

export async function deleteRemoteAccessCredential(id: number): Promise<{ deleted: boolean; credential_id: number }> {
  return requestJson(`/remote-access/credentials/${id}`, {
    method: "DELETE",
  })
}

export interface RemoteAccessSession {
  session_uuid: string
  device_id: number
  protocol: "ssh" | "telnet"
  port: number
  device_username: string
  status: string
  started_at: string
  ended_at: string | null
  disconnect_reason: string | null
  user_id: number
  source_ip: string | null
  user_name?: string | null
}

export async function listRemoteAccessSessions(): Promise<RemoteAccessSession[]> {
  return requestJson<RemoteAccessSession[]>("/remote-access/sessions", { cache: "no-store" })
}

export async function listRemoteAccessSessionHistory(): Promise<RemoteAccessSession[]> {
  return requestJson<RemoteAccessSession[]>("/remote-access/sessions/history", { cache: "no-store" })
}

export async function createRemoteAccessSession(payload: {
  device_id: number
  protocol: "ssh" | "telnet"
  port: number
  credential_id?: number
  username?: string
  secret?: string
  remember_credential?: boolean
}): Promise<RemoteAccessSession> {
  return requestJson<RemoteAccessSession>("/remote-access/sessions", {
    method: "POST",
    body: JSON.stringify({
      ...payload,
      username: payload.username,
      secret: payload.secret,
    }),
  })
}

export async function deleteRemoteAccessSession(
  sessionUuid: string,
): Promise<RemoteAccessSession | null> {
  return requestJson<RemoteAccessSession | null>(
    `/remote-access/sessions/${encodeURIComponent(sessionUuid)}`,
    { method: "DELETE" },
  )
}

export async function openRemoteAccessTerminal(
  sessionUuid: string,
): Promise<WebSocket> {
  const token = await ensureAuth()
  const apiUrl = buildUrl(
    `/remote-access/sessions/${encodeURIComponent(sessionUuid)}/terminal`,
  )
  const url = apiUrl.replace(/^http/, "ws")
  return new WebSocket(url, `nms-bearer-${token}`)
}

export async function testRemoteAccess(payload: {
  device_id: number
  protocol: "ssh" | "telnet"
  port: number
  credential_id?: number
  username?: string
  secret?: string
  auth_type?: "password" | "private_key"
  remember_credential: boolean
}): Promise<RemoteAccessTestResponse> {
  return requestJson<RemoteAccessTestResponse>("/remote-access/test", {
    method: "POST",
    body: JSON.stringify(payload),
  })
}

export interface SSHHostKeyMetadata {
  id: number
  device_id: number
  host: string
  port: number
  key_type: string
  fingerprint: string
  status: "PENDING" | "TRUSTED" | "REVOKED"
}

export async function scanSSHHostKey(deviceId: number, port: number): Promise<SSHHostKeyMetadata> {
  return requestJson<SSHHostKeyMetadata>("/remote-access/host-keys/scan", {
    method: "POST", body: JSON.stringify({ device_id: deviceId, port }),
  })
}

export async function trustSSHHostKey(id: number): Promise<SSHHostKeyMetadata> {
  return requestJson<SSHHostKeyMetadata>(`/remote-access/host-keys/${id}/trust`, { method: "POST" })
}

export async function revokeSSHHostKey(id: number): Promise<SSHHostKeyMetadata> {
  return requestJson<SSHHostKeyMetadata>(`/remote-access/host-keys/${id}/revoke`, { method: "POST" })
}

/** Devices with an explicitly configured SNMP credential only. */
export async function listSNMPDevices(): Promise<DeviceRecord[]> {
  const payload = await requestJson<DeviceRecord[] | {
    items?: DeviceRecord[]
    devices?: DeviceRecord[]
  }>("/snmp/devices")
  if (Array.isArray(payload)) return payload
  if (Array.isArray(payload.items)) return payload.items
  if (Array.isArray(payload.devices)) return payload.devices
  return []
}

export interface SNMPDiscoveryPayload {
  ips: string[]
  snmp_version: "v2c" | "v3"
  communities?: string[]
  username?: string | null
  auth_protocol?: string | null
  auth_password?: string | null
  privacy_protocol?: string | null
  privacy_password?: string | null
  security_level?: string | null
  timeout_seconds?: number
}

export interface SNMPDiscoveryResponse {
  scanned: number
  count: number
  results: Record<string, Record<string, unknown>>
}

export async function discoverSNMP(
  payload: SNMPDiscoveryPayload,
): Promise<SNMPDiscoveryResponse> {
  return requestJson<SNMPDiscoveryResponse>("/discovery/snmp", {
    method: "POST",
    body: JSON.stringify(payload),
  })
}

export async function listDeviceMetrics(
  deviceId?: number,
  params?: { skip?: number limit?: number },
): Promise<DeviceMetricRecord[]> {
  const query = new URLSearchParams()
  if (deviceId != null) query.set("device_id", String(deviceId))
  if (params?.skip != null) query.set("skip", String(params.skip))
  if (params?.limit != null) query.set("limit", String(params.limit))
  const path = `/device-metrics${query.size ? `?${query.toString()}` : ""}`
  return requestJson<DeviceMetricRecord[]>(path)
}

export async function listAlerts(
  statusFilter?: string,
  params?: { skip?: number limit?: number },
): Promise<AlertRecord[]> {
  const query = new URLSearchParams()
  if (statusFilter) query.set("status_filter", statusFilter)
  if (params?.skip != null) query.set("skip", String(params.skip))
  if (params?.limit != null) query.set("limit", String(params.limit))
  const path = `/alerts${query.size ? `?${query.toString()}` : ""}`
  return requestJson<AlertRecord[]>(path)
}

export async function listEvents(params?: {
  skip?: number
  limit?: number
}): Promise<EventRecord[]> {
  const query = new URLSearchParams()
  if (params?.skip != null) query.set("skip", String(params.skip))
  if (params?.limit != null) query.set("limit", String(params.limit))
  const suffix = query.size ? `?${query.toString()}` : ""
  return requestJson<EventRecord[]>(`/events${suffix}`)
}

export const SYSLOG_SEVERITY_LABELS = [
  "Emergency",
  "Alert",
  "Critical",
  "Error",
  "Warning",
  "Notice",
  "Informational",
  "Debug",
] as const

export interface SyslogRecord {
  id: number
  device_id: number | null
  interface_id: number | null
  alert_id: number | null
  incident_id: number | null
  source_ip: string | null
  facility: number | null
  severity: number | null
  hostname: string | null
  application: string | null
  process_id: string | null
  message_id: string | null
  structured_data: string | null
  event_timestamp: string | null
  message: string | null
  raw_message: string | null
  received_at: string
  fingerprint: string | null
  device_name?: string | null
}

export interface SyslogRecordsResponse {
  items: SyslogRecord[]
  total: number
  limit: number
  offset: number
}

export interface SyslogRecordFilters {
  start?: string
  end?: string
  device_id?: number
  source_ip?: string
  hostname?: string
  severity?: number
  facility?: number
  application?: string
  pattern?: string
  limit?: number
  offset?: number
}

export interface SyslogRule {
  id: number
  name: string
  pattern: string
  min_severity: number | null
  alert_severity: string
  cooldown_seconds: number
  enabled: boolean
  device_id: number | null
  source_ip: string | null
  hostname: string | null
  facility: number | null
  application: string | null
  created_by: number | null
  created_at: string
}

export type SyslogRulePayload = Omit<SyslogRule, "id" | "created_by" | "created_at">

export async function listSyslogRecords(
  filters: SyslogRecordFilters = {},
): Promise<SyslogRecordsResponse> {
  const query = new URLSearchParams()
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "")
      query.set(key, String(value))
  })
  return requestJson<SyslogRecordsResponse>(
    `/syslog/records?${query.toString()}`,
  )
}

export async function listSyslogRules(): Promise<SyslogRule[]> {
  return requestJson("/syslog/rules")
}
export async function createSyslogRule(
  payload: SyslogRulePayload,
): Promise<SyslogRule> {
  return requestJson("/syslog/rules", {
    method: "POST",
    body: JSON.stringify(payload),
  })
}
export async function updateSyslogRule(
  id: number,
  payload: SyslogRulePayload,
): Promise<SyslogRule> {
  return requestJson(`/syslog/rules/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  })
}
export async function deleteSyslogRule(id: number): Promise<void> {
  await requestJson(`/syslog/rules/${id}`, { method: "DELETE" })
}
export async function setSyslogRuleEnabled(
  id: number,
  enabled: boolean,
): Promise<SyslogRule> {
  return requestJson(`/syslog/rules/${id}/${enabled ? "enable" : "disable"}`, {
    method: "POST",
  })
}
export async function cleanupSyslog(
  retentionDays: number,
  batchSize = 1000,
): Promise<{ deleted: number retention_days: number }> {
  return requestJson(
    `/syslog/retention/cleanup?retention_days=${retentionDays}&batch_size=${batchSize}`,
    { method: "POST" },
  )
}

export async function listInterfaces(params?: {
  skip?: number
  limit?: number
}): Promise<InterfaceRecord[]> {
  const query = new URLSearchParams()
  if (params?.skip != null) query.set("skip", String(params.skip))
  if (params?.limit != null) query.set("limit", String(params.limit))
  const suffix = query.size ? `?${query.toString()}` : ""
  return requestJson<InterfaceRecord[]>(`/interfaces${suffix}`)
}

export async function listNotifications(): Promise<NotificationRecord[]> {
  return requestJson<NotificationRecord[]>("/notifications")
}

export async function startChunkedDiscovery(
  payload: ChunkedDiscoveryRequest,
): Promise<ChunkedDiscoveryStartResponse> {
  return requestJson<ChunkedDiscoveryStartResponse>("/discovery/chunked-scan", {
    method: "POST",
    body: JSON.stringify(payload),
  })
}

export async function getChunkedDiscoveryStatus(
  jobId: string,
): Promise<ChunkedDiscoveryJobStatus> {
  return requestJson<ChunkedDiscoveryJobStatus>(
    `/discovery/chunked-scan/${jobId}`,
  )
}

export async function addDiscoveredDevices(
  payload: AddDiscoveredDevicesPayload,
): Promise<{
  added_count: number
  skipped_count: number
  added: Array<Record<string, unknown>>
  skipped: Array<Record<string, unknown>>
}> {
  return requestJson("/discovery/add-devices", {
    method: "POST",
    body: JSON.stringify(payload),
  })
}

export async function checkStoredDevices(
  ips: string[],
): Promise<{ stored_ips: string[] }> {
  return requestJson("/discovery/check-stored", {
    method: "POST",
    body: JSON.stringify({ ips }),
  })
}

export async function startMonitoringDevice(
  payload: MonitorDevicePayload,
): Promise<Record<string, unknown>> {
  return requestJson("/discovery/monitoring/start", {
    method: "POST",
    body: JSON.stringify(payload),
  })
}

export async function stopMonitoringDevice(
  ip: string,
): Promise<{ ip: string stopped: boolean }> {
  return requestJson("/discovery/monitoring/stop", {
    method: "POST",
    body: JSON.stringify({ ip }),
  })
}

export async function startAllMonitoring(
  devices: Record<string, unknown>[],
): Promise<{ added: number total_monitored: number }> {
  return requestJson("/discovery/monitoring/start-all", {
    method: "POST",
    body: JSON.stringify({ devices }),
  })
}

export async function stopAllMonitoring(): Promise<{ stopped: number }> {
  return requestJson("/discovery/monitoring/stop-all", {
    method: "POST",
  })
}

export async function streamChunkedDiscovery(
  jobId: string,
  onEvent: (event: ChunkedDiscoveryEvent) => void,
): Promise<void> {
  const token = await ensureAuth()
  const response = await fetch(
    buildUrl(`/discovery/chunked-scan/${jobId}/progress`),
    {
      headers: {
        Authorization: `Bearer ${token}`,
      },
    },
  )

  if (!response.ok) {
    throw new Error(`Discovery stream failed: ${response.status}`)
  }

  const reader = response.body?.getReader()
  if (!reader) {
    throw new Error("Discovery stream is not available in this browser")
  }

  const decoder = new TextDecoder()
  let buffer = ""

  while (true) {
    const { value, done } = await reader.read()
    if (done) {
      break
    }

    buffer += decoder.decode(value, { stream: true })
    const parts = buffer.split("\n\n")
    buffer = parts.pop() ?? ""

    for (const part of parts) {
      const lines = part.split("\n").map((line) => line.trimEnd())
      let eventName = "message"
      let payload = ""

      for (const line of lines) {
        if (!line) continue
        if (line.startsWith("event:")) {
          eventName = line.slice(6).trim()
        } else if (line.startsWith("data:")) {
          payload += `${line.slice(5).trimStart()}\n`
        }
      }

      if (payload.trim()) {
        onEvent({
          event: eventName as ChunkedDiscoveryEvent["event"],
          data: JSON.parse(payload.trim()),
        })
      }
    }
  }

  const trailing = buffer.trim()
  if (trailing) {
    const lines = trailing.split("\n").map((line) => line.trimEnd())
    let eventName = "message"
    let payload = ""

    for (const line of lines) {
      if (!line) continue
      if (line.startsWith("event:")) {
        eventName = line.slice(6).trim()
      } else if (line.startsWith("data:")) {
        payload += `${line.slice(5).trimStart()}\n`
      }
    }

    if (payload.trim()) {
      onEvent({
        event: eventName as ChunkedDiscoveryEvent["event"],
        data: JSON.parse(payload.trim()),
      })
    }
  }
}

// ---------------------------------------------------------------- Device detail

export async function getDevice(deviceId: number): Promise<DeviceRecord> {
  return requestJson<DeviceRecord>(`/devices/${deviceId}`)
}


export interface DeviceHistoryResponse {
  device: Record<string, unknown>
  status_history: Array<{
    id: number
    old_status: string | null
    new_status: string
    reason: string | null
    timestamp: string | null
  }>
  metrics: Array<{
    timestamp: string | null
    latency_ms: number | null
    packet_loss: number | null
    cpu_usage: number | null
    memory_usage: number | null
  }>
  summary: {
    total_hours: number
    uptime_seconds: number
    downtime_seconds: number
    uptime_hours: number
    downtime_hours: number
    availability_pct: number
    total_status_changes: number
    up_events?: number
    down_events?: number
    total_pings: number
    current_status: string
    last_seen: string | null
    last_status_change: string | null
  }
}

export async function getDeviceHistory(
  ip: string,
  hours = 24,
): Promise<DeviceHistoryResponse> {
  return requestJson<DeviceHistoryResponse>(
    `/discovery/device-history/${encodeURIComponent(ip)}?hours=${hours}`,
  )
}

export interface MonitoringStatusResponse {
  summary: {
    total_monitored: number
    up: number
    down: number
    unknown: number
    loop_running: boolean
  }
  devices: Array<Record<string, unknown>>
}

export async function getMonitoringStatus(): Promise<MonitoringStatusResponse> {
  return requestJson<MonitoringStatusResponse>("/discovery/monitoring/status")
}

export async function getDeviceStatusHistory(
  deviceId: number,
): Promise<Array<{
  id: number
  device_id: number
  old_status: string | null
  new_status: string
  change_reason: string | null
  timestamp: string
}>> {
  return requestJson(`/devices/${deviceId}/status-history`)
}

// ---------------------------------------------------------------- Realtime monitoring SSE

export interface MonitoringStreamEvent {
  event: "update"
  data: MonitoringStatusResponse
}

export interface TopologyStreamEvent {
  event: "topology"
  data: { revision: string updated_at: string }
}

export async function pingIps(ips: string[], timeoutMs = 1000): Promise<{
  count: number
  results: Array<{ ip: string reachable: boolean status: string rtt?: number }>
}> {
  return requestJson("/discovery/icmp", {
    method: "POST",
    body: JSON.stringify({ ips, timeout_ms: timeoutMs }),
  })
}

async function streamJsonEvents<T>(
  path: string,
  onEvent: (event: T) => void,
): Promise<() => void> {
  const token = await ensureAuth()
  const controller = new AbortController()

  const response = await fetch(buildUrl(path), {
    headers: { Authorization: `Bearer ${token}` },
    signal: controller.signal,
  })

  if (!response.ok) {
    throw new Error(`Event stream failed: ${response.status}`)
  }

  const reader = response.body?.getReader()
  if (!reader) {
    throw new Error("Event stream is not available")
  }

  const decoder = new TextDecoder()
  let buffer = ""

  const pump = async () => {
    try {
      while (true) {
        const { value, done } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const parts = buffer.split("\n\n")
        buffer = parts.pop() ?? ""

        for (const part of parts) {
          const lines = part.split("\n").map((l) => l.trimEnd())
          let eventName = "message"
          let payload = ""
          for (const line of lines) {
            if (!line) continue
            if (line.startsWith("event:")) eventName = line.slice(6).trim()
            else if (line.startsWith("data:"))
              payload += `${line.slice(5).trimStart()}\n`
          }
          if (payload.trim()) {
            onEvent({ event: eventName, data: JSON.parse(payload.trim()) } as T)
          }
        }
      }
    } catch {
      // aborted or network error — silent exit
    }
  }

  void pump()

  return () => {
    controller.abort()
  }
}

export function streamMonitoring(
  onEvent: (event: MonitoringStreamEvent) => void,
): Promise<() => void> {
  return streamJsonEvents("/discovery/monitoring/stream", onEvent)
}

export function streamTopologyUpdates(
  onEvent: (event: TopologyStreamEvent) => void,
): Promise<() => void> {
  return streamJsonEvents("/snmp/topology/stream", onEvent)
}

// ── Organizations ──

export interface OrganizationRecord {
  id: number
  name: string
  description?: string | null
  created_at: string
}

export async function listOrganizations(): Promise<OrganizationRecord[]> {
  return requestJson("/organizations")
}

export async function createOrganization(data: {
  name: string
  description?: string
}): Promise<OrganizationRecord> {
  return requestJson("/organizations", {
    method: "POST",
    body: JSON.stringify(data),
  })
}

// ── Sites ──

export interface SiteRecord {
  id: number
  name: string
  organization_id: number
  city?: string | null
  state?: string | null
}

export async function listSites(): Promise<SiteRecord[]> {
  return requestJson("/sites")
}

export async function createSite(data: {
  name: string
  organization_id: number
  city?: string
  state?: string
}): Promise<SiteRecord> {
  return requestJson("/sites", {
    method: "POST",
    body: JSON.stringify(data),
  })
}
export async function updateSite(
  id: number,
  data: { name?: string organization_id?: number city?: string state?: string },
): Promise<SiteRecord> {
  return requestJson(`/sites/${id}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  })
}
export async function deleteSite(id: number): Promise<{ detail: string }> {
  return requestJson(`/sites/${id}`, { method: "DELETE" })
}

// ── Device CRUD ──

export async function createDevice(data: {
  hostname: string
  ip_address: string
  mac_address?: string
  model?: string
  serial_number?: string
  firmware_version?: string
  site_id?: number
}): Promise<DeviceRecord> {
  return requestJson("/devices", {
    method: "POST",
    body: JSON.stringify(data),
  })
}

export async function updateDevice(
  id: number,
  data: Partial<{
    hostname: string
    ip_address: string
    mac_address: string
    model: string
    serial_number: string
    firmware_version: string
    site_id: number
    status: string
    monitoring_status: boolean
    vendor_name: string
    topology_metadata: {
      [key: string]: unknown
      port?: string
      vlans?: string[]
      ips?: string[]
      location?: string | null
      description?: string | null
    }
  }>,
): Promise<DeviceRecord> {
  return requestJson(`/devices/${id}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  })
}

export async function deleteDevice(id: number): Promise<{ deleted: boolean }> {
  return requestJson(`/devices/${id}`, { method: "DELETE" })
}

export async function deleteAllDevices(): Promise<{
  deleted: number
  message: string
}> {
  return requestJson("/devices", { method: "DELETE" })
}

// ── Alerts ──

export async function clearAllAlerts(): Promise<{ cleared: number }> {
  return requestJson("/alerts/clear-all", { method: "DELETE" })
}

// ── RBAC: Auth / Me ──

export type UserStatus = "active" | "disabled" | "suspended"

export interface UserRecord {
  id: number
  uuid: string
  name: string
  email: string
  role_id: number | null
  role_name: string | null
  authority_level?: number | null
  permissions: string[]
  status: string
  created_at: string
}

export async function getMe(): Promise<UserRecord> {
  return requestJson<UserRecord>("/auth/me")
}

// ── RBAC: Roles ──

export interface RoleRecord {
  id: number
  role_name: string
  authority_level?: number | null
  is_system_role?: boolean
  is_assignable?: boolean
}

export interface PermissionRecord {
  id: number
  code: string
  name: string
  module: string
  action: string
  description: string | null
}

export interface RoleWithPermissions extends RoleRecord {
  permissions: PermissionRecord[]
}

export async function listRoles(): Promise<RoleRecord[]> {
  return requestJson<RoleRecord[]>("/roles")
}

export async function createRole(data: {
  role_name: string
  authority_level?: number
}): Promise<RoleRecord> {
  return requestJson("/roles", { method: "POST", body: JSON.stringify(data) })
}

export async function updateRole(
  id: number,
  data: { role_name?: string authority_level?: number },
): Promise<RoleRecord> {
  return requestJson(`/roles/${id}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  })
}

export async function deleteRole(id: number): Promise<{ detail: string }> {
  return requestJson(`/roles/${id}`, { method: "DELETE" })
}

export async function getRolePermissions(
  id: number,
): Promise<RoleWithPermissions> {
  return requestJson<RoleWithPermissions>(`/roles/${id}/permissions`)
}

export async function setRolePermissions(
  id: number,
  permission_ids: number[],
): Promise<RoleWithPermissions> {
  return requestJson(`/roles/${id}/permissions`, {
    method: "PUT",
    body: JSON.stringify({ permission_ids }),
  })
}

// ── RBAC: Permissions ──

export async function listPermissions(
  module?: string,
): Promise<PermissionRecord[]> {
  const path = module
    ? `/permissions?module=${encodeURIComponent(module)}&limit=500`
    : "/permissions?limit=500"
  return requestJson<PermissionRecord[]>(path)
}

// ── RBAC: Users ──

export interface UserSiteAssignments {
  site_ids: number[]
}

export interface UserSessionRecord {
  session_id: string
  created_at: string
  last_seen_at: string
  expires_at: string
  revoked_at: string | null
  revoke_reason: string | null
  ip_address: string | null
  user_agent: string | null
  active: boolean
}

export interface UserActivityResponse {
  items: Array<Record<string, unknown>>
  total: number
  limit: number
  offset: number
}

export async function listUserSessions(
  id: number,
): Promise<UserSessionRecord[]> {
  return requestJson<UserSessionRecord[]>(`/users/${id}/sessions`)
}

export async function revokeUserSession(
  id: number,
  sessionId: string,
): Promise<{ detail: string }> {
  return requestJson(`/users/${id}/sessions/${encodeURIComponent(sessionId)}`, {
    method: "DELETE",
  })
}

export async function revokeAllUserSessions(
  id: number,
): Promise<{ revoked: number }> {
  return requestJson(`/users/${id}/sessions/revoke-all`, { method: "POST" })
}

export async function listUserActivity(
  id: number,
  params: Record<string, string | number | undefined> = {},
): Promise<UserActivityResponse> {
  const query = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== "") query.set(key, String(value))
  })
  return requestJson<UserActivityResponse>(
    `/users/${id}/activity${query.toString() ? `?${query}` : ""}`,
  )
}

export async function getUserSites(id: number): Promise<UserSiteAssignments> {
  return requestJson<UserSiteAssignments>(`/users/${id}/sites`)
}

export async function replaceUserSites(
  id: number,
  site_ids: number[],
): Promise<UserSiteAssignments> {
  return requestJson<UserSiteAssignments>(`/users/${id}/sites`, {
    method: "PUT",
    body: JSON.stringify({ site_ids }),
  })
}

export async function listUsers(): Promise<UserRecord[]> {
  return requestJson<UserRecord[]>("/users")
}

export async function createUser(data: {
  name: string
  email: string
  password: string
  role_id?: number
  status?: string
}): Promise<UserRecord> {
  return requestJson("/users", { method: "POST", body: JSON.stringify(data) })
}

export async function updateUser(
  id: number,
  data: {
    name?: string
    email?: string
    password?: string
    role_id?: number | null
    status?: string
  },
): Promise<UserRecord> {
  return requestJson(`/users/${id}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  })
}

export async function updateUserStatus(
  id: number,
  status: UserStatus,
  suspendedUntil?: string,
): Promise<UserRecord> {
  return requestJson(`/users/${id}/status`, {
    method: "PATCH",
    body: JSON.stringify({
      status,
      ...(suspendedUntil
        ? { suspended_until: new Date(suspendedUntil).toISOString() }
        : {}),
    }),
  })
}

export async function deleteUser(id: number): Promise<{ detail: string }> {
  return requestJson(`/users/${id}`, { method: "DELETE" })
}

export async function assignUserRole(
  id: number,
  role_id: number,
): Promise<UserRecord> {
  return requestJson(`/users/${id}/role`, {
    method: "POST",
    body: JSON.stringify({ role_id }),
  })
}

// ── SNMP Dynamic Monitoring ──

export interface SNMPModuleSummary {
  name: string
  supported: boolean
  status: "supported" | "unsupported" | "error"
  last_poll?: string | null
  object_count?: number
  health?: "healthy" | "warning" | "critical" | "unknown"
  summary?: Record<string, any>
}

export interface SNMPDeviceOverview {
  device_id: number
  hostname: string
  ip_address: string
  vendor?: string | null
  model?: string | null
  uptime_seconds?: number
  health: "healthy" | "warning" | "critical" | "unknown"
  polling_enabled: boolean
  last_poll?: string | null
  modules: SNMPModuleSummary[]
}

export interface SNMPSystemInfo {
  hostname?: string
  description?: string
  mac_address?: string | null
  uptime_seconds?: number
  uptime_display?: string
  contact?: string
  location?: string
  services?: number
  data?: {
    uptime?: {
      seconds?: number | null
      ticks?: number | null
      display?: string | null
    }
    [key: string]: unknown
  }
  supported: boolean
}

export interface SNMPCPUStats {
  device_id: number
  current_usage?: number
  average?: number
  maximum?: number
  minimum?: number
  percentile_95?: number
  per_core?: Array<{ core: number usage: number }>
  history: Array<{ timestamp: string usage: number }>
  supported: boolean
  poll_interval?: number
  last_poll?: string
}

export interface SNMPMemoryStats {
  device_id: number
  total_bytes?: number
  used_bytes?: number
  free_bytes?: number
  cached_bytes?: number
  buffer_bytes?: number
  swap_total?: number
  swap_used?: number
  utilization_percent?: number
  history: Array<{
    timestamp: string
    used: number
    free: number
    utilization: number
  }>
  supported: boolean
  last_poll?: string
}

export interface SNMPStorageVolume {
  id: number
  device_id: number
  mount_name: string
  total_bytes: number
  used_bytes: number
  free_bytes: number
  utilization_percent: number
  type?: string
  health: "healthy" | "warning" | "critical"
  last_updated: string
}

export interface SNMPInterfaceStats {
  id: number
  device_id: number
  if_index: number
  name: string
  description?: string
  mac_address?: string
  speed_bps?: number
  speed_display?: string
  status: "UP" | "DOWN" | "UNKNOWN"
  admin_status: "UP" | "DOWN" | "UNKNOWN"
  mtu?: number
  rx_mbps?: number
  tx_mbps?: number
  rx_octets?: number
  tx_octets?: number
  rx_packets?: number
  tx_packets?: number
  errors?: number
  discards?: number
  utilization_percent?: number
  last_change?: string
  last_updated: string
}

export interface SNMPInterfaceHistory {
  interface_id: number
  history: Array<{
    timestamp: string
    rx_mbps: number
    tx_mbps: number
    utilization: number
    errors: number
    packet_rate: number
  }>
  statistics: {
    peak_mbps: number
    average_mbps: number
    percentile_95_mbps: number
  }
}

export interface SNMPEnvironmentSensor {
  id: number
  device_id: number
  sensor_name: string
  sensor_type: "temperature" | "fan" | "voltage" | "power" | "humidity" | "other"
  current_value?: number
  unit?: string
  threshold_warning?: number
  threshold_critical?: number
  status: "ok" | "warning" | "critical" | "unknown"
  history: Array<{ timestamp: string value: number }>
  last_updated: string
}

export interface SNMPLLDPNeighbor {
  id: number
  device_id: number
  local_port: string
  remote_device: string
  remote_port: string
  remote_system_name?: string
  remote_description?: string
  remote_mgmt_ip?: string
  capabilities?: string[]
  last_updated: string
}

export interface SNMPRoutingEntry {
  id: number
  device_id: number
  destination: string
  next_hop: string
  interface?: string
  metric?: number
  protocol?: string
  type?: string
  status: "active" | "inactive"
  last_updated: string
}

export interface SNMPVLANInfo {
  id: number
  device_id: number
  vlan_id: number
  vlan_name?: string
  tagged_ports?: string[]
  untagged_ports?: string[]
  status: "active" | "inactive"
  last_updated: string
}

export interface SNMPOIDCacheEntry {
  id: number
  device_id: number
  oid: string
  oid_name?: string
  value?: string
  type?: string
  mib?: string
  supported: boolean
  last_seen: string
  vendor_specific: boolean
}

export interface SNMPOIDTree {
  oid: string
  name: string
  children?: SNMPOIDTree[]
  value?: string
  type?: string
  supported: boolean
}

export interface SNMPPollingHistory {
  id: number
  device_id: number
  collector: string
  status: "success" | "failure"
  duration_ms: number
  objects_collected?: number
  error?: string | null
  timestamp: string
}

export interface SNMPPollingStatistics {
  total_polls: number
  success_count: number
  failure_count: number
  success_rate: number
  average_duration_ms: number
  max_duration_ms: number
  min_duration_ms: number
  by_collector: Array<{
    collector: string
    polls: number
    success_rate: number
    avg_duration_ms: number
  }>
  recent_history: SNMPPollingHistory[]
}

export interface SNMPTopologyLink {
  source_device_id: number
  source_device_name: string
  source_port: string
  target_device_id: number
  target_device_name: string
  target_port: string
  link_type: "lldp" | "cdp" | "discovered"
  status: "active" | "inactive"
}

export interface SNMPTopologyGraph {
  devices: Array<{
    id: number
    hostname: string
    ip_address: string
    type?: string
    vendor?: string
  }>
  links: SNMPTopologyLink[]
}

// SNMP API Functions

export async function getSNMPDeviceOverview(
  deviceId: number,
): Promise<SNMPDeviceOverview> {
  return requestJson<SNMPDeviceOverview>(`/snmp/devices/${deviceId}/overview`, { cache: "no-store" })
}

export async function getSNMPSystemInfo(
  deviceId: number,
): Promise<SNMPSystemInfo> {
  return requestJson<SNMPSystemInfo>(`/snmp/devices/${deviceId}/system`)
}

export async function getSNMPCPUStats(
  deviceId: number,
  hours = 24,
): Promise<SNMPCPUStats> {
  return requestJson<SNMPCPUStats>(
    `/snmp/devices/${deviceId}/cpu?hours=${hours}`,
  )
}

export async function getSNMPMemoryStats(
  deviceId: number,
  hours = 24,
): Promise<SNMPMemoryStats> {
  return requestJson<SNMPMemoryStats>(
    `/snmp/devices/${deviceId}/memory?hours=${hours}`,
  )
}

export async function getSNMPStorageVolumes(
  deviceId: number,
): Promise<SNMPStorageVolume[]> {
  return requestJson<SNMPStorageVolume[]>(`/snmp/devices/${deviceId}/storage`)
}

export async function getSNMPInterfaces(
  deviceId: number,
): Promise<SNMPInterfaceStats[]> {
  const payload = await requestJson<SNMPInterfaceStats[] | {
    data?: { interfaces?: SNMPInterfaceStats[] }
    interfaces?: SNMPInterfaceStats[]
  }>(`/snmp/devices/${deviceId}/interfaces`)
  if (Array.isArray(payload)) return payload
  return payload.data?.interfaces ?? payload.interfaces ?? []
}

export async function getSNMPInterfaceHistory(
  interfaceId: number,
  hours = 24,
): Promise<SNMPInterfaceHistory> {
  return requestJson<SNMPInterfaceHistory>(
    `/snmp/interfaces/${interfaceId}/history?hours=${hours}`,
  )
}

export async function getSNMPEnvironmentSensors(
  deviceId: number,
): Promise<SNMPEnvironmentSensor[]> {
  return requestJson<SNMPEnvironmentSensor[]>(
    `/snmp/devices/${deviceId}/environment`,
  )
}

export async function getSNMPLLDPNeighbors(
  deviceId: number,
): Promise<SNMPLLDPNeighbor[]> {
  return requestJson<SNMPLLDPNeighbor[]>(`/snmp/devices/${deviceId}/lldp`)
}

export async function getSNMPRoutingTable(
  deviceId: number,
): Promise<SNMPRoutingEntry[]> {
  return requestJson<SNMPRoutingEntry[]>(`/snmp/devices/${deviceId}/routing`)
}

export async function getSNMPVLANs(deviceId: number): Promise<SNMPVLANInfo[]> {
  return requestJson<SNMPVLANInfo[]>(`/snmp/devices/${deviceId}/vlans`)
}

export async function getSNMPOIDCache(
  deviceId: number,
): Promise<SNMPOIDCacheEntry[]> {
  return requestJson<SNMPOIDCacheEntry[]>(`/snmp/devices/${deviceId}/oids`)
}

export async function getSNMPOIDTree(deviceId: number): Promise<SNMPOIDTree> {
  return requestJson<SNMPOIDTree>(`/snmp/devices/${deviceId}/oid-tree`)
}

export async function getSNMPPollingHistory(
  deviceId: number,
  hours = 24,
): Promise<SNMPPollingHistory[]> {
  return requestJson<SNMPPollingHistory[]>(
    `/snmp/devices/${deviceId}/polling-history?hours=${hours}`,
  )
}

export async function getSNMPPollingStatistics(
  deviceId: number,
): Promise<SNMPPollingStatistics> {
  return requestJson<SNMPPollingStatistics>(
    `/snmp/devices/${deviceId}/polling-stats`,
  )
}

export async function getSNMPTopology(
  deviceId?: number,
  refresh = false,
): Promise<SNMPTopologyGraph> {
  const params = new URLSearchParams()
  if (deviceId) params.set("device_id", String(deviceId))
  if (refresh) params.set("refresh", "true")
  const query = params.toString()
  const path = query ? `/snmp/topology?${query}` : "/snmp/topology"
  return requestJson<SNMPTopologyGraph>(path)
}

export async function persistSNMPTopologySnapshot(
  deviceId: number,
  snapshot: {
    devices: unknown[]
    links: unknown[]
    collected_at: string
    source?: string
  },
): Promise<{ persisted: boolean collected_at: string }> {
  return requestJson(`/snmp/topology/snapshot`, {
    method: "POST",
    body: JSON.stringify({ device_id: deviceId, ...snapshot }),
  })
}

export interface ManualTopologyChange {
  id: number
  change_type: "CONNECTION_DISCONNECTED" | "CONNECTION_ADDED" | string
  signature: string
  expected?: Record<string, unknown> | null
  observed?: Record<string, unknown> | null
  status: "pending" | "accepted" | "kept_manual" | string
  detected_at?: string | null
  resolved_at?: string | null
  resolution_note?: string | null
}

export interface ManualTopologySnapshotResponse {
  id: number
  name: string
  payload: any
  reconcile_status: string
  last_reconciled_at?: string | null
  changes: ManualTopologyChange[]
  live?: { links?: any[] devices?: any[] }
}

export async function createManualTopologySnapshot(
  payload: any,
): Promise<ManualTopologySnapshotResponse> {
  return requestJson<ManualTopologySnapshotResponse>(
    "/manual-topology/snapshots",
    {
      method: "POST",
      body: JSON.stringify({ name: "Manual topology", payload }),
    },
  )
}

export async function updateManualTopologySnapshot(
  snapshotId: number,
  payload: any,
): Promise<ManualTopologySnapshotResponse> {
  return requestJson<ManualTopologySnapshotResponse>(
    `/manual-topology/snapshots/${snapshotId}`,
    {
      method: "PUT",
      body: JSON.stringify({ name: "Manual topology", payload }),
    },
  )
}

export async function getLatestManualTopologySnapshot(): Promise<ManualTopologySnapshotResponse | null> {
  return requestJson<ManualTopologySnapshotResponse | null>(
    "/manual-topology/snapshots/latest",
  )
}

export async function reconcileManualTopology(
  snapshotId: number,
): Promise<ManualTopologySnapshotResponse> {
  return requestJson<ManualTopologySnapshotResponse>(
    `/manual-topology/snapshots/${snapshotId}/reconcile`,
    { method: "POST" },
  )
}

export async function resolveManualTopologyChange(
  snapshotId: number,
  changeId: number,
  action: "accept_real_change" | "keep_manual",
  note?: string,
): Promise<ManualTopologySnapshotResponse> {
  return requestJson<ManualTopologySnapshotResponse>(
    `/manual-topology/snapshots/${snapshotId}/changes/${changeId}/resolve`,
    {
      method: "POST",
      body: JSON.stringify({ action, note }),
    },
  )
}

// ── Overview (single call for entire Dashboard) ───────────────────────────

export interface DeviceOverviewItem {
  id: number
  hostname: string
  ip_address: string
  mac_address?: string | null
  status: string
  health?: {
    status?: string
    health_reason?: string
    freshness_status?: string
    age_seconds?: number | null
  }
  monitoring_status: boolean
  vendor?: string | null
  device_type?: string | null
  model?: string | null
  serial_number?: string | null
  firmware_version?: string | null
  uptime_seconds: number
  last_seen?: string | null
  created_at: string
  site_id?: number | null
  snmp_version?: string | null
  interface_count: number
  interfaces_up: number
  cpu_usage?: number | null
  memory_usage?: number | null
  temperature?: number | null
  latency?: number | null
  packet_loss?: number | null
  metric_at?: string | null
}

export interface ServiceState {
  running: boolean
  job_count?: number
  device_count?: number
  label: string
  summary?: Record<string, unknown>
  last_job_started_at?: string | null
  last_job_finished_at?: string | null
  last_job_success_at?: string | null
  last_job_failure_at?: string | null
  recent_failure_count?: number
  lease_owned?: boolean
}

export interface NormalizedOverview {
  performance?: {
    avg_cpu: number | null
    avg_memory: number | null
    sample_count?: number
  }
  correlation?: {
    window_minutes: number
    correlated_outage_alerts: number
    correlated_performance_alerts: number
  }
  devices: Record<string, {
    cpu: number | null
    memory: number | null
    load: Record<string, number> | null
    uptime_seconds: number
    storage: Array<{
      mount_name?: string | null
      utilization_percent?: number | null
      polled_at?: string | null
    }>
    environment: Array<{
      sensor_name?: string | null
      sensor_type: string
      value?: number | null
      unit?: string | null
      status: string
      polled_at?: string | null
    }>
    last_poll: {
      timestamp?: string | null
      status?: string
      collector?: string
      error?: string | null
    } | null
  }>
  interfaces: Array<{
    device_id: number
    device_name?: string | null
    interface_id: number
    name?: string | null
    oper_status: string
    admin_status: string
    speed_bps?: number | null
    rx_mbps?: number | null
    tx_mbps?: number | null
    errors?: number | null
    discards?: number | null
    rx_packets?: number | null
    tx_packets?: number | null
    utilization_percent?: number | null
    polled_at?: string | null
  }>
  traffic_history: Array<{
    timestamp?: string | null
    device_id: number
    rx_mbps?: number | null
    tx_mbps?: number | null
    utilization_percent?: number | null
  }>
  traffic: {
    rx_mbps: number
    tx_mbps: number
    top_devices: Array<{
      device_id: number
      device_name?: string | null
      rx_mbps: number
      tx_mbps: number
    }>
    top_interfaces: NormalizedOverview["interfaces"]
  }
  polling: {
    successful_attempts: number
    unsupported_attempts: number
    no_data_attempts: number
    failed_attempts: number
    unknown_attempts: number
    total_attempts: number
    success_rate: number | null
    success: number
    failure: number
    last_success?: string | null
    last_failure?: string | null
    active_jobs: number
    configured_jobs: number
    enabled_jobs: number
    collector_failures: number
    unsupported_oids: number
  }
  interface_summary: {
    total: number
    up: number
    down: number
    errors: number
    drops: number
  }
  alerts_by_severity: Record<string, number>
  device_types: Record<string, number>
  network: {
    lldp_neighbors: number
    vlan_count: number
    routing_entries: number
    arp_entries: number | null
    mac_entries: number | null
    topology_nodes: number
  }
}

export interface OverviewResponse {
  summary: {
    historical_availability_pct?: number | null
    total_devices: number
    online_devices: number
    offline_devices: number
    warning_devices: number
    active_alerts: number
    critical_alerts: number
    recent_events: number
    health_counts?: Record<string, number>
  }
  devices: DeviceOverviewItem[]
  alerts: AlertRecord[]
  events: EventRecord[]
  services: {
    snmp_polling: ServiceState
    realtime_monitor: ServiceState
    any_running: boolean
  }
  normalized: NormalizedOverview
  fetched_at: string
}

export async function getOverview(
  hours = 24,
  forceRefresh = false,
): Promise<OverviewResponse> {
  // The overview is a live dashboard snapshot; never reuse the generic
  // 30-second client cache for it. Backend applies a short 10-second cache.
  return requestJson<OverviewResponse>(
    `/overview?hours=${hours}${forceRefresh ? "&force_refresh=true" : ""}`,
    { cache: "no-store" },
  )
}

export async function getDeviceMonitoringConfigs(
  deviceId: number,
): Promise<Array<{
  device_id: number
  module_name: string
  enabled: boolean
  interval_seconds: number
  status: string
  last_poll_at?: string | null
  next_poll_at?: string | null
  error_message?: string | null
}>> {
  return requestJson(`/snmp/devices/${deviceId}/monitoring`)
}

export async function restartMonitoringJob(
  deviceId: number,
  module: string,
  intervalSeconds: number,
): Promise<unknown> {
  await requestJson(`/snmp/devices/${deviceId}/monitoring/${module}/stop`, {
    method: "POST",
  })
  return requestJson(`/snmp/devices/${deviceId}/monitoring/${module}/start`, {
    method: "POST",
    body: JSON.stringify({
      module_name: module,
      interval_seconds: intervalSeconds,
    }),
  })
}

// ── Kill all monitoring services ──────────────────────────────────────────

export interface KillAllResponse {
  success: boolean
  killed: string[]
  errors: string[]
  message: string
  stopped_at: string
}

export async function killAllServices(): Promise<KillAllResponse> {
  return requestJson<KillAllResponse>("/monitoring/kill-all", {
    method: "POST",
  })
}

export async function getServiceStates(): Promise<OverviewResponse["services"]> {
  return requestJson<OverviewResponse["services"]>("/monitoring/services")
}

export async function startPollingService(): Promise<OverviewResponse["services"]> {
  return requestJson<OverviewResponse["services"]>(
    "/monitoring/polling/start",
    { method: "POST" },
  )
}

// ── Organizations (full CRUD) ─────────────────────────────────────────────
export async function updateOrganization(
  id: number,
  data: { name?: string description?: string },
): Promise<OrganizationRecord> {
  return requestJson(`/organizations/${id}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  })
}
export async function deleteOrganization(
  id: number,
): Promise<{ detail: string }> {
  return requestJson(`/organizations/${id}`, { method: "DELETE" })
}

// ── Vendors ───────────────────────────────────────────────────────────────
export interface VendorRecord {
  id: number
  vendor_name: string
}
export async function listVendors(): Promise<VendorRecord[]> {
  return requestJson<VendorRecord[]>("/vendors")
}
export async function createVendor(data: {
  vendor_name: string
}): Promise<VendorRecord> {
  return requestJson("/vendors", { method: "POST", body: JSON.stringify(data) })
}
export async function updateVendor(
  id: number,
  data: { vendor_name?: string },
): Promise<VendorRecord> {
  return requestJson(`/vendors/${id}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  })
}
export async function deleteVendor(id: number): Promise<{ detail: string }> {
  return requestJson(`/vendors/${id}`, { method: "DELETE" })
}

// ── Reports ───────────────────────────────────────────────────────────────
export interface ReportRecord {
  id: number
  report_name: string
  report_type: string
  generated_by?: number | null
  file_path?: string | null
  generated_at: string
}
export async function listReports(): Promise<ReportRecord[]> {
  return requestJson<ReportRecord[]>("/reports")
}
export async function createReport(data: {
  report_name: string
  report_type: string
  file_path?: string
}): Promise<ReportRecord> {
  return requestJson("/reports", { method: "POST", body: JSON.stringify(data) })
}
export async function updateReport(
  id: number,
  data: { report_name?: string report_type?: string file_path?: string },
): Promise<ReportRecord> {
  return requestJson(`/reports/${id}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  })
}
export async function deleteReport(id: number): Promise<{ detail: string }> {
  return requestJson(`/reports/${id}`, { method: "DELETE" })
}

// ── Daily Network Monitoring Report ──────────────────────────────────────
export interface DailyReportSeverity {
  [key: string]: number
}
export interface DailyReportDevice {
  device_id: number
  hostname: string
  ip: string
  avg_value?: number
  max_value?: number
  count?: number
  status?: string
  downtime_sec?: number
  alerts?: number
  reason?: string
}
export interface DailyReportInterface {
  id: number
  name: string
  device_id: number
  hostname: string
  status: string
  traffic_in?: number
  traffic_out?: number
  speed?: string
  packet_errors?: number
  last_updated?: string
}
export interface DailyReportAlert {
  id: number
  severity: string
  title: string
  description?: string | null
  status: string
  device_id?: number | null
  hostname: string
  created_at?: string | null
}
export interface DailyReportChange {
  device_id: number
  hostname: string
  ip: string
  old_status: string | null
  new_status: string
  reason?: string | null
  timestamp?: string | null
}
export interface DailyReportRecommendation {
  priority: string
  message: string
}

export interface DailyReport {
  report_date: string
  period: string
  generated_at: string
  availability: {
    total_devices: number
    online: number
    offline: number
    warning: number
    availability_pct: number
    downtime_events_24h: number
    devices_with_downtime: DailyReportDevice[]
  }
  performance: {
    sample_count: number
    cpu: { avg: number | null max: number | null samples: number }
    memory: { avg: number | null max: number | null samples: number }
    disk: { avg: number | null max: number | null samples: number }
    latency: { avg: number | null max: number | null samples: number }
    packet_loss: { avg: number | null max: number | null samples: number }
    bandwidth: { avg: number | null max: number | null samples: number }
    top_cpu_devices: DailyReportDevice[]
    top_mem_devices: DailyReportDevice[]
    top_latency_devices: DailyReportDevice[]
  }
  interfaces: {
    total: number
    up: number
    down: number
    high_traffic: DailyReportInterface[]
    interfaces_with_errors: DailyReportInterface[]
    down_interfaces: DailyReportInterface[]
  }
  alerts: {
    total_alerts_24h: number
    by_severity: DailyReportSeverity
    resolved: number
    open: number
    critical: number
    high: number
    warning: number
    info: number
    top_alert_devices: DailyReportDevice[]
    recent_alerts: DailyReportAlert[]
    total_events_24h: number
    event_types: DailyReportSeverity
  }
  incidents: {
    total_status_changes: number
    went_offline: number
    came_online: number
    changes: DailyReportChange[]
  }
  top_performers: {
    top_cpu: DailyReportDevice[]
    top_memory: DailyReportDevice[]
    top_latency: DailyReportDevice[]
    max_downtime: DailyReportDevice[]
    max_alerts: DailyReportDevice[]
  }
  daily_summary: {
    overall_health: string
    health_score: number
    availability_pct: number
    issues: string[]
    devices_needing_attention: DailyReportDevice[]
  }
  recommendations: DailyReportRecommendation[]
}

export async function getDailyReport(): Promise<DailyReport> {
  return requestJson<DailyReport>("/reports/daily")
}

// ============================================================================
// NEW SNMP MONITORING API (DB-First Architecture)
// ============================================================================

export interface SNMPDeviceListItem {
  id: number
  name: string
  ip_address: string
  hostname: string
  device_type: string | null
  model: string | null
  serial_number: string | null
  firmware: string | null
  mac_address: string | null
  status: string
  snmp_version: string | null
  snmp_status: string
  monitoring_enabled: boolean
  last_seen: string | null
  last_poll_at: string | null
  modules_monitored: number
}

export interface SNMPDevicesResponse {
  items: SNMPDeviceListItem[]
  page: number
  page_size: number
  total: number
  total_pages: number
}

export interface MonitoringConfig {
  module_name: string
  enabled: boolean
  interval_seconds: number
  status: string
  last_started_at: string | null
  last_stopped_at: string | null
  last_poll_at: string | null
  next_poll_at: string | null
  error_message: string | null
}

export interface SNMPDeviceDetails {
  device: {
    id: number
    name: string
    ip_address: string
    hostname: string
    description: string | null
    device_type: string | null
    vendor: string | null
    model: string | null
    serial_number: string | null
    firmware: string | null
    mac_address: string | null
    status: string
    monitoring_status: boolean
    last_seen: string | null
    created_at: string | null
    uptime_seconds: number
  }
  snmp: {
    version: string | null
    port: number
    status: string
    last_test_at: string | null
  }
  capabilities: Record<string, boolean>
  monitoring: MonitoringConfig[]
  latest_metrics: {
    cpu: {
      utilization_percent: number | null
      per_core: Record<string, number>
      load_avg: Record<string, number>
      polled_at: string | null
    } | null
    memory: {
      total_bytes: number | null
      used_bytes: number | null
      free_bytes: number | null
      utilization_percent: number | null
      polled_at: string | null
    } | null
    storage: Array<{
      volume_id: string
      mount_name: string | null
      total_bytes: number | null
      used_bytes: number | null
      free_bytes: number | null
      utilization_percent: number | null
      type_label: string | null
      polled_at: string | null
    }>
    interfaces: Array<{
      interface_id: number
      if_index: number
      name: string | null
      oper_status: string
      admin_status: string
      speed_bps: number | null
      rx_mbps: number | null
      tx_mbps: number | null
      utilization_percent: number | null
      polled_at: string | null
    }>
    environment: Array<{
      sensor_id: string
      sensor_name: string | null
      sensor_type: string
      value: number | null
      unit: string | null
      status: string
      polled_at: string | null
    }>
  }
  polling_history: Array<{
    id: number
    collector: string
    status: string
    duration_ms: number
    error: string | null
    timestamp: string
  }>
}

export interface LatestCPU {
  device_id: number
  supported: boolean
  current_usage: number | null
  per_core: Record<string, number>
  load_avg: Record<string, number>
  last_poll: string | null
}

export interface LatestMemory {
  device_id: number
  supported: boolean
  total_bytes: number | null
  used_bytes: number | null
  free_bytes: number | null
  utilization_percent: number | null
  last_poll: string | null
}

export interface LatestInterface {
  interface_id: number
  if_index: number
  name: string | null
  oper_status: string
  admin_status: string
  speed_bps: number | null
  rx_mbps: number | null
  tx_mbps: number | null
  rx_octets: number | null
  tx_octets: number | null
  rx_packets: number | null
  tx_packets: number | null
  errors: number | null
  discards: number | null
  utilization_percent: number | null
  last_poll: string | null
}

export interface LatestStorage {
  volume_id: string
  mount_name: string | null
  total_bytes: number | null
  used_bytes: number | null
  free_bytes: number | null
  utilization_percent: number | null
  type_label: string | null
  last_poll: string | null
}

export interface LatestEnvironment {
  sensor_id: string
  sensor_name: string | null
  sensor_type: string
  value: number | null
  unit: string | null
  status: string
  last_poll: string | null
}

export interface MonitoringStartRequest {
  module_name: string
  interval_seconds: number
}

export interface MonitoringUpdateRequest {
  enabled?: boolean
  interval_seconds?: number
}

// API Functions

export async function listSNMPDevicesOptimized(
  params: {
    page?: number
    page_size?: number
    search?: string
    status?: string
    snmp_status?: string
    monitoring_status?: string
    device_type?: string
    vendor?: string
    model?: string
    hostname?: string
    sort_by?: string
    sort_order?: string
  },
  signal?: AbortSignal,
): Promise<SNMPDevicesResponse> {
  const query = new URLSearchParams()
  if (params.page) query.set("page", String(params.page))
  if (params.page_size) query.set("page_size", String(params.page_size))
  if (params.search) query.set("search", params.search)
  if (params.status) query.set("status", params.status)
  if (params.snmp_status) query.set("snmp_status", params.snmp_status)
  if (params.monitoring_status)
    query.set("monitoring_status", params.monitoring_status)
  if (params.device_type) query.set("device_type", params.device_type)
  if (params.vendor) query.set("vendor", params.vendor)
  if (params.model) query.set("model", params.model)
  if (params.hostname) query.set("hostname", params.hostname)
  if (params.sort_by) query.set("sort_by", params.sort_by)
  if (params.sort_order) query.set("sort_order", params.sort_order)
  return requestJson<SNMPDevicesResponse>(`/snmp/devices?${query.toString()}`, {
    signal,
    cache: "no-store",
  })
}

export async function getSNMPDeviceDetails(
  deviceId: number,
): Promise<SNMPDeviceDetails> {
  // Manual refreshes must observe current persisted capabilities/metrics,
  // not the shared short-lived GET cache.
  return requestJson<SNMPDeviceDetails>(`/snmp/devices/${deviceId}`, {
    signal: new AbortController().signal,
  })
}

export async function getSNMPDeviceMonitoringConfigs(
  deviceId: number,
): Promise<MonitoringConfig[]> {
  return requestJson<MonitoringConfig[]>(`/snmp/devices/${deviceId}/monitoring`)
}

export async function startModuleMonitoring(
  deviceId: number,
  module: string,
  intervalSeconds: number,
): Promise<MonitoringConfig & { message: string }> {
  return requestJson(`/snmp/devices/${deviceId}/monitoring/${module}/start`, {
    method: "POST",
    body: JSON.stringify({
      module_name: module,
      interval_seconds: intervalSeconds,
    }),
  })
}

export async function stopModuleMonitoring(
  deviceId: number,
  module: string,
): Promise<{ stopped: boolean message: string }> {
  return requestJson(`/snmp/devices/${deviceId}/monitoring/${module}/stop`, {
    method: "POST",
  })
}

export async function updateModuleMonitoring(
  deviceId: number,
  module: string,
  data: MonitoringUpdateRequest,
): Promise<MonitoringConfig> {
  return requestJson(`/snmp/devices/${deviceId}/monitoring/${module}`, {
    method: "PUT",
    body: JSON.stringify(data),
  })
}

export async function getModuleMonitoringStatus(
  deviceId: number,
  module: string,
): Promise<MonitoringConfig> {
  return requestJson<MonitoringConfig>(
    `/snmp/devices/${deviceId}/monitoring/${module}/status`,
  )
}

export async function getLatestMetrics(
  deviceId: number,
): Promise<{
  cpu: LatestCPU | null
  memory: LatestMemory | null
  storage: LatestStorage[]
  interfaces: LatestInterface[]
  environment: LatestEnvironment[]
}> {
  return requestJson(`/snmp/devices/${deviceId}/metrics/latest`)
}

export async function getLatestCPU(deviceId: number): Promise<LatestCPU> {
  return requestJson<LatestCPU>(`/snmp/devices/${deviceId}/cpu/latest`)
}

export async function getLatestMemory(deviceId: number): Promise<LatestMemory> {
  return requestJson<LatestMemory>(`/snmp/devices/${deviceId}/memory/latest`)
}

export async function getLatestInterfaces(
  deviceId: number,
): Promise<LatestInterface[]> {
  return requestJson<LatestInterface[]>(
    `/snmp/devices/${deviceId}/interfaces/latest`,
  )
}

export async function getLatestStorage(
  deviceId: number,
): Promise<LatestStorage[]> {
  return requestJson<LatestStorage[]>(
    `/snmp/devices/${deviceId}/storage/latest`,
  )
}

export async function getLatestEnvironment(
  deviceId: number,
): Promise<LatestEnvironment[]> {
  return requestJson<LatestEnvironment[]>(
    `/snmp/devices/${deviceId}/environment/latest`,
  )
}

// ============================================================================
// NEW SNMP MONITORING ENDPOINTS FOR ADDITIONAL MODULES
// ============================================================================

export interface SNMPMemoryStats {
  device_id: number
  supported: boolean
  total_bytes?: number
  used_bytes?: number
  free_bytes?: number
  cached_bytes?: number
  buffer_bytes?: number
  swap_total?: number
  swap_free?: number
  utilization_percent?: number
  history: Array<{
    timestamp: string
    used: number
    free: number
    utilization: number
  }>
  last_poll?: string
}

export interface SNMPInterfaceStats {
  interface_id: number
  device_id: number
  if_index: number
  name: string
  description?: string
  mac_address?: string
  speed_bps?: number
  speed_display?: string
  status: "UP" | "DOWN" | "UNKNOWN"
  admin_status: "UP" | "DOWN" | "UNKNOWN"
  mtu?: number
  rx_mbps?: number
  tx_mbps?: number
  rx_octets?: number
  tx_octets?: number
  rx_packets?: number
  tx_packets?: number
  errors?: number
  discards?: number
  utilization_percent?: number
  last_change?: string
  last_updated: string
}

export interface SNMPInterfaceHistory {
  interface_id: number
  history: Array<{
    timestamp: string
    rx_mbps: number
    tx_mbps: number
    utilization: number
    errors: number
    packet_rate: number
  }>
  statistics: {
    peak_mbps: number
    average_mbps: number
    percentile_95_mbps: number
  }
}

export interface SNMPStorageVolume {
  id: number
  device_id: number
  mount_name: string
  total_bytes: number
  used_bytes: number
  free_bytes: number
  utilization_percent: number
  type?: string
  health: "healthy" | "warning" | "critical"
  last_updated: string
}

export interface SNMPStorageStats {
  device_id: number
  supported: boolean
  volumes: SNMPStorageVolume[]
  last_poll?: string
}

export interface SNMPEnvironmentSensor {
  id: number
  device_id: number
  sensor_name: string
  sensor_type: "temperature" | "fan" | "voltage" | "power" | "humidity" | "other"
  current_value?: number
  unit?: string
  threshold_warning?: number
  threshold_critical?: number
  status: "ok" | "warning" | "critical" | "unknown"
  history: Array<{ timestamp: string value: number }>
  last_updated: string
}

export interface SNMPEnvironmentStats {
  device_id: number
  supported: boolean
  sensors: SNMPEnvironmentSensor[]
  last_poll?: string
}

export interface SNMPVLANInfo {
  id: number
  device_id: number
  vlan_id: number
  vlan_name?: string
  tagged_ports?: string[]
  untagged_ports?: string[]
  status: "active" | "inactive"
  last_updated: string
}

export interface SNMPLLDPNeighbor {
  id: number
  device_id: number
  local_port: string
  remote_device: string
  remote_port: string
  remote_system_name?: string
  remote_description?: string
  remote_mgmt_ip?: string
  capabilities?: string[]
  last_updated: string
}

export interface SNMPRoutingEntry {
  id: number
  device_id: number
  destination: string
  next_hop: string
  interface?: string
  metric?: number
  protocol?: string
  type?: string
  status: "active" | "inactive"
  last_updated: string
}

export interface SNMPTopologyLink {
  source_device_id: number
  source_device_name: string
  source_port: string
  target_device_id: number
  target_device_name: string
  target_port: string
  link_type: "lldp" | "cdp" | "discovered"
  status: "active" | "inactive"
}

export interface SNMPTopologyGraph {
  devices: Array<{
    id: number
    hostname: string
    ip_address: string
    type?: string
    vendor?: string
  }>
  links: SNMPTopologyLink[]
}

export interface SNMPOIDCacheEntry {
  id: number
  device_id: number
  oid: string
  oid_name?: string
  value?: string
  type?: string
  mib?: string
  supported: boolean
  last_seen: string
  vendor_specific: boolean
}

export interface SNMPOIDTree {
  oid: string
  name: string
  children?: SNMPOIDTree[]
  value?: string
  type?: string
  supported: boolean
}

export interface SNMPPollingHistory {
  id: number
  device_id: number
  collector: string
  status: "success" | "failure"
  duration_ms: number
  objects_collected?: number
  error?: string | null
  timestamp: string
}

export interface SNMPPollingStatistics {
  total_polls: number
  success_count: number
  failure_count: number
  success_rate: number
  average_duration_ms: number
  max_duration_ms: number
  min_duration_ms: number
  by_collector: Array<{
    collector: string
    polls: number
    success_rate: number
    avg_duration_ms: number
  }>
  recent_history: SNMPPollingHistory[]
}

// API Functions for new endpoints - use the ones defined above to avoid duplicates
// getSNMPMemoryStats, getSNMPInterfaces, getSNMPInterfaceHistory, getSNMPVLANs, getSNMPLLDPNeighbors
// getSNMPRoutingTable, getSNMPTopology, getSNMPOIDCache, getSNMPOIDTree, getSNMPPollingHistory, getSNMPPollingStatistics
// are already exported above in the first SNMP API Functions section
export async function getSNMPStorageStats(
  deviceId: number,
): Promise<SNMPStorageStats> {
  return requestJson<SNMPStorageStats>(`/snmp/devices/${deviceId}/storage`)
}

export async function getSNMPEnvironmentStats(
  deviceId: number,
): Promise<SNMPEnvironmentStats> {
  return requestJson<SNMPEnvironmentStats>(
    `/snmp/devices/${deviceId}/environment`,
  )
}

// Device CRUD - Add device with SNMP credentials
export interface AddDeviceRequest {
  ip_address: string
  name?: string
  hostname?: string
  snmp_version: "v2c" | "v3"
  community_string?: string
  username?: string
  auth_protocol?: string
  auth_password?: string
  privacy_protocol?: string
  privacy_password?: string
  security_level?: string
  snmp_port?: number
  location?: string
  description?: string
  vendor_override?: string
  model_override?: string
  device_type_override?: string
  site_id?: number
  mac_address?: string
  auto_discover?: boolean
}

export interface AddDeviceResponse {
  device: {
    id: number
    ip_address: string
    hostname: string
    status: string
    created: boolean
  }
  discovery: Record<string, unknown>
}

export async function addSNMPDevice(
  data: AddDeviceRequest,
): Promise<AddDeviceResponse> {
  return requestJson<AddDeviceResponse>("/devices/manual", {
    method: "POST",
    body: JSON.stringify(data),
  })
}

// SNMP Test
export interface SNMPTestResponse {
  reachable: boolean
  snmp_enabled: boolean
  hostname?: string
  vendor?: string
  device_type?: string
  response_ms: number
  device_id: number
  ip: string
  error?: string
}

export async function testSNMPConnection(
  deviceId: number,
): Promise<SNMPTestResponse> {
  return requestJson<SNMPTestResponse>(`/snmp/devices/${deviceId}/test-snmp`, {
    method: "POST",
  })
}

// Discovery
export interface SNMPDiscoverResponse {
  identity: Record<string, unknown>
  capabilities: Record<string, boolean>
  reachable: boolean
  vendor: string
  device_type: string
  hostname: string
}

export async function discoverDevice(
  deviceId: number,
): Promise<SNMPDiscoverResponse> {
  return requestJson<SNMPDiscoverResponse>(
    `/snmp/devices/${deviceId}/discover`,
    {
      method: "POST",
    },
  )
}

// ============================================================================
// MISSING CRUD API FUNCTIONS
// ============================================================================

// ── Alerts CRUD ─────────────────────────────────────────────────────────────

export async function createAlert(data: {
  device_id?: number | null
  severity: string
  title: string
  description?: string | null
  status?: string
}): Promise<AlertRecord> {
  return requestJson("/alerts", {
    method: "POST",
    body: JSON.stringify(data),
  })
}

export async function updateAlert(
  id: number,
  data: {
    severity?: string
    title?: string
    description?: string | null
    status?: string
  },
): Promise<AlertRecord> {
  return requestJson(`/alerts/${id}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  })
}

export async function deleteAlert(id: number): Promise<{ detail: string }> {
  return requestJson(`/alerts/${id}`, { method: "DELETE" })
}

export async function acknowledgeAlert(id: number): Promise<AlertRecord> {
  return requestJson(`/alerts/${id}/acknowledge`, { method: "POST" })
}

export async function resolveAlert(id: number): Promise<AlertRecord> {
  return requestJson(`/alerts/${id}/resolve`, { method: "POST" })
}

// ── Events CRUD ─────────────────────────────────────────────────────────────

export async function createEvent(data: {
  device_id?: number | null
  event_type: string
  description?: string | null
}): Promise<EventRecord> {
  return requestJson("/events", {
    method: "POST",
    body: JSON.stringify(data),
  })
}

export async function updateEvent(
  id: number,
  data: {
    event_type?: string
    description?: string | null
  },
): Promise<EventRecord> {
  return requestJson(`/events/${id}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  })
}

export async function deleteEvent(id: number): Promise<{ detail: string }> {
  return requestJson(`/events/${id}`, { method: "DELETE" })
}

// ── Notifications CRUD ──────────────────────────────────────────────────────

export async function createNotification(data: {
  alert_id?: number | null
  channel: string
  sent_to: string
  status?: string
}): Promise<NotificationRecord> {
  return requestJson("/notifications", {
    method: "POST",
    body: JSON.stringify(data),
  })
}

export async function updateNotification(
  id: number,
  data: {
    channel?: string
    sent_to?: string
    status?: string
  },
): Promise<NotificationRecord> {
  return requestJson(`/notifications/${id}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  })
}

export async function deleteNotification(
  id: number,
): Promise<{ detail: string }> {
  return requestJson(`/notifications/${id}`, { method: "DELETE" })
}

// ── Thresholds ──────────────────────────────────────────────────────────────

export interface ThresholdRecord {
  id: number
  metric_name: string
  threshold_value: number
  condition: string
  severity: string
  description?: string | null
  created_at: string
}

export async function listThresholds(): Promise<ThresholdRecord[]> {
  return requestJson<ThresholdRecord[]>("/thresholds")
}

export async function createThreshold(data: {
  metric_name: string
  threshold_value: number
  condition: string
  severity: string
  description?: string | null
}): Promise<ThresholdRecord> {
  return requestJson("/thresholds", {
    method: "POST",
    body: JSON.stringify(data),
  })
}

export async function updateThreshold(
  id: number,
  data: {
    metric_name?: string
    threshold_value?: number
    condition?: string
    severity?: string
    description?: string | null
  },
): Promise<ThresholdRecord> {
  return requestJson(`/thresholds/${id}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  })
}

export async function deleteThreshold(id: number): Promise<{ detail: string }> {
  return requestJson(`/thresholds/${id}`, { method: "DELETE" })
}

// ── Monitoring Jobs ─────────────────────────────────────────────────────────

export interface MonitoringJobRecord {
  id: number
  job_name: string
  job_type: string
  schedule: string
  enabled: boolean
  last_run?: string | null
  next_run?: string | null
  status: string
  created_at: string
}

export async function listMonitoringJobs(): Promise<MonitoringJobRecord[]> {
  return requestJson<MonitoringJobRecord[]>("/monitoring-jobs")
}

export interface RuntimeProcessRecord {
  pid: number
  name: string
  status: string
  uptime_seconds: number
  command: string
}

export interface RuntimeStatusRecord {
  response_time_ms: number
  processes: RuntimeProcessRecord[]
}

export async function getRuntimeStatus(): Promise<RuntimeStatusRecord> {
  return requestJson<RuntimeStatusRecord>("/runtime-status", {
    cache: "no-store",
  })
}

export async function restartRuntimeProcess(
  pid: number,
): Promise<{ detail: string pid: number }> {
  return requestJson(`/runtime-status/restart/${pid}`, { method: "POST" })
}

export async function createMonitoringJob(data: {
  job_name: string
  job_type: string
  schedule: string
  enabled?: boolean
}): Promise<MonitoringJobRecord> {
  return requestJson("/monitoring-jobs", {
    method: "POST",
    body: JSON.stringify(data),
  })
}

export async function updateMonitoringJob(
  id: number,
  data: {
    job_name?: string
    job_type?: string
    schedule?: string
    enabled?: boolean
  },
): Promise<MonitoringJobRecord> {
  return requestJson(`/monitoring-jobs/${id}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  })
}

export async function deleteMonitoringJob(
  id: number,
): Promise<{ detail: string }> {
  return requestJson(`/monitoring-jobs/${id}`, { method: "DELETE" })
}

// ── Interfaces CRUD ─────────────────────────────────────────────────────────

export async function createInterface(data: {
  device_id: number
  interface_name: string
  status: string
  speed?: string | null
  traffic_in?: number
  traffic_out?: number
  packet_errors?: number
}): Promise<InterfaceRecord> {
  return requestJson("/interfaces", {
    method: "POST",
    body: JSON.stringify(data),
  })
}

export async function updateInterface(
  id: number,
  data: {
    interface_name?: string
    status?: string
    speed?: string | null
    traffic_in?: number
    traffic_out?: number
    packet_errors?: number
  },
): Promise<InterfaceRecord> {
  return requestJson(`/interfaces/${id}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  })
}

export async function deleteInterface(id: number): Promise<{ detail: string }> {
  return requestJson(`/interfaces/${id}`, { method: "DELETE" })
}

// ── Device Credentials ──────────────────────────────────────────────────────

export interface DeviceCredentialRecord {
  id: number
  device_id: number
  credential_type: string
  username?: string | null
  created_at: string
}

export async function listDeviceCredentials(): Promise<DeviceCredentialRecord[]> {
  return requestJson<DeviceCredentialRecord[]>("/device-credentials")
}

export async function createDeviceCredential(data: {
  device_id: number
  credential_type: string
  username?: string | null
  password?: string | null
  community_string?: string | null
  auth_password?: string | null
  privacy_password?: string | null
  api_token?: string | null
}): Promise<DeviceCredentialRecord> {
  return requestJson("/device-credentials", {
    method: "POST",
    body: JSON.stringify(data),
  })
}

export async function updateDeviceCredential(
  id: number,
  data: {
    credential_type?: string
    username?: string | null
    password?: string | null
    community_string?: string | null
    auth_password?: string | null
    privacy_password?: string | null
    api_token?: string | null
  },
): Promise<DeviceCredentialRecord> {
  return requestJson(`/device-credentials/${id}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  })
}

export async function deleteDeviceCredential(
  id: number,
): Promise<{ detail: string }> {
  return requestJson(`/device-credentials/${id}`, { method: "DELETE" })
}

// ── Device Types ────────────────────────────────────────────────────────────

export interface DeviceTypeRecord {
  id: number
  name: string
  description?: string | null
  created_at?: string | null
}

export async function listDeviceTypes(): Promise<DeviceTypeRecord[]> {
  return requestJson<DeviceTypeRecord[]>("/device-types")
}

export async function createDeviceType(data: {
  name: string
  description?: string | null
}): Promise<DeviceTypeRecord> {
  return requestJson("/device-types", {
    method: "POST",
    body: JSON.stringify(data),
  })
}

export async function updateDeviceType(
  id: number,
  data: {
    name?: string
    description?: string | null
  },
): Promise<DeviceTypeRecord> {
  return requestJson(`/device-types/${id}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  })
}

export async function deleteDeviceType(
  id: number,
): Promise<{ detail: string }> {
  return requestJson(`/device-types/${id}`, { method: "DELETE" })
}

// ── Audit Logs (Read-Only) ──────────────────────────────────────────────────

export interface AuditLogRecord {
  id: number
  user_id?: number | null
  user_name?: string | null
  action: string
  resource_name: string
  timestamp: string
  source_ip?: string | null
  user_agent?: string | null
  outcome?: string | null
}

export interface AuditLogFilters {
  user_id?: number
  action?: string
  outcome?: string
  resource_type?: string
  resource_id?: number
  source_ip?: string
  start_date?: string
  end_date?: string
  limit?: number
  offset?: number
}

export interface AuditLogPage {
  items: AuditLogRecord[]
  total: number
}

export function listAuditLogs(): Promise<AuditLogRecord[]>
export function listAuditLogs(userId: number): Promise<AuditLogRecord[]>
export function listAuditLogs(
  params: AuditLogFilters & { include_total: true },
): Promise<AuditLogPage>
export async function listAuditLogs(
  params?: AuditLogFilters | number,
): Promise<AuditLogRecord[] | AuditLogPage> {
  // Preserve the original listAuditLogs() and listAuditLogs(userId) signatures.
  const filters: AuditLogFilters =
    typeof params === "number" ? { user_id: params } : (params ?? {})
  const query = new URLSearchParams()
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== null && value !== "")
      query.set(key, String(value))
  }
  const suffix = query.toString() ? `?${query.toString()}` : ""
  return requestJson<AuditLogRecord[] | AuditLogPage>(`/audit-logs${suffix}`)
}

export interface AuditLogSummary {
  total_activities: number
  successful_actions: number
  failed_actions: number
  login_success: number
  login_failed: number
  account_locked: number
  user_status_changes: number
}

export interface AuditLogSummaryParams {
  start_date?: string
  end_date?: string
}

export async function getAuditLogSummary(
  params: AuditLogSummaryParams = {},
): Promise<AuditLogSummary> {
  const query = new URLSearchParams()
  if (params.start_date !== undefined)
    query.set("start_date", params.start_date)
  if (params.end_date !== undefined) query.set("end_date", params.end_date)
  const suffix = query.toString() ? `?${query.toString()}` : ""
  return requestJson<AuditLogSummary>(`/audit-logs/summary${suffix}`)
}

export async function recordPageView(page: string): Promise<void> {
  await requestJson(`/audit-logs/page-view?page=${encodeURIComponent(page)}`, {
    method: "POST",
  })
}

export interface AuditLogUser {
  id: number
  name: string
  email: string
}

export async function listAuditLogUsers(): Promise<AuditLogUser[]> {
  return requestJson<AuditLogUser[]>("/audit-logs/users")
}

// ── Device Metrics CRUD ─────────────────────────────────────────────────────

export async function createDeviceMetric(data: {
  device_id: number
  cpu_usage?: number | null
  memory_usage?: number | null
  disk_usage?: number | null
  temperature?: number | null
  latency?: number | null
  packet_loss?: number | null
  bandwidth_usage?: number | null
}): Promise<DeviceMetricRecord> {
  return requestJson("/device-metrics", {
    method: "POST",
    body: JSON.stringify(data),
  })
}

export async function updateDeviceMetric(
  id: number,
  data: {
    cpu_usage?: number | null
    memory_usage?: number | null
    disk_usage?: number | null
    temperature?: number | null
    latency?: number | null
    packet_loss?: number | null
    bandwidth_usage?: number | null
  },
): Promise<DeviceMetricRecord> {
  return requestJson(`/device-metrics/${id}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  })
}

export async function deleteDeviceMetric(
  id: number,
): Promise<{ detail: string }> {
  return requestJson(`/device-metrics/${id}`, { method: "DELETE" })
}

export interface LinuxServerRecord {
  id: number
  uuid: string
  hostname: string
  ip_address: string
  display_name?: string | null
  os_name?: string | null
  os_version?: string | null
  architecture?: string | null
  snmp_available?: boolean | null
  snmp_version?: string | null
  ssh_port: number
  status: string
  enabled: boolean
  last_seen_at?: string | null
  last_error?: string | null
  created_at: string
  updated_at: string
}
export interface LinuxServerDetail extends LinuxServerRecord {
  interfaces: Array<{
    id: number
    interface_name: string
    mac_address?: string | null
    state?: string | null
    speed_mbps?: number | null
    mtu?: number | null
  }>
  disks: Array<{
    id: number
    device?: string | null
    mount_point: string
    filesystem?: string | null
    total_bytes?: number | null
    used_bytes?: number | null
    available_bytes?: number | null
    usage_percent?: number | null
  }>
  monitoring_config?: { enabled: boolean interval_seconds: number } | null
}
export interface LinuxDetectedData {
  ip_address: string
  hostname: string
  os_name?: string | null
  os_version?: string | null
  architecture?: string | null
  snmp_available?: boolean | null
  snmp_version?: string | null
  interfaces: LinuxServerDetail["interfaces"]
  disks: LinuxServerDetail["disks"]
  status: string
}
export interface LinuxDetectionResponse {
  success: boolean
  status: string
  message: string
  data?: LinuxDetectedData | null
  warnings: string[]
  ssh_valid?: boolean
  snmp_valid?: boolean
  ssh_error?: string | null
  snmp_error?: string | null
}
export interface LinuxSecurityEvent {
  id: number
  linux_server_id: number
  event_timestamp: string
  source_ip?: string | null
  destination_ip?: string | null
  destination_port?: number | null
  event_type: string
  severity?: string | null
  raw_message: string
  event_hash: string
  created_at: string
}
export interface LinuxMonitoringStatus {
  server_id: number
  enabled: boolean
  status: "running" | "stopped" | "failed"
  interval_seconds: number
  last_run_at?: string | null
  last_success_at?: string | null
  last_error?: string | null
}
export interface LinuxRetentionStatus {
  retention_hours: number
  last_cleanup_at?: string | null
  last_cleanup_error?: string | null
}
export async function listLinuxServers(): Promise<LinuxServerRecord[]> {
  return requestJson("/linux-servers")
}
export async function getLinuxRetentionStatus(): Promise<LinuxRetentionStatus> {
  return requestJson("/linux-servers/retention/status")
}
export async function detectLinuxServer(
  data: Record<string, unknown>,
): Promise<LinuxDetectionResponse> {
  return requestJson("/linux-servers/detect", {
    method: "POST",
    body: JSON.stringify(data),
  })
}
export async function validateLinuxSSH(
  data: Record<string, unknown>,
): Promise<LinuxDetectionResponse> {
  return requestJson("/linux-servers/detect/ssh", {
    method: "POST",
    body: JSON.stringify(data),
  })
}
export async function validateLinuxSNMP(
  data: Record<string, unknown>,
): Promise<LinuxDetectionResponse> {
  return requestJson("/linux-servers/detect/snmp", {
    method: "POST",
    body: JSON.stringify(data),
  })
}
export async function addLinuxServer(
  data: Record<string, unknown>,
): Promise<LinuxServerDetail> {
  return requestJson("/linux-servers", {
    method: "POST",
    body: JSON.stringify(data),
  })
}
export async function getLinuxServer(id: number): Promise<LinuxServerDetail> {
  return requestJson(`/linux-servers/${id}`)
}
export async function updateLinuxServer(
  id: number,
  data: Record<string, unknown>,
): Promise<LinuxServerRecord> {
  return requestJson(`/linux-servers/${id}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  })
}
export async function deleteLinuxServer(
  id: number,
): Promise<{ detail: string }> {
  return requestJson(`/linux-servers/${id}`, { method: "DELETE" })
}
export async function listLinuxMonitoringStatus(): Promise<LinuxMonitoringStatus[]> {
  return requestJson("/linux-servers/monitoring/status")
}
export async function startLinuxMonitoring(
  id: number,
  data: Record<string, string>,
): Promise<LinuxMonitoringStatus> {
  return requestJson(`/linux-servers/${id}/monitoring/start`, {
    method: "POST",
    body: JSON.stringify(data),
  })
}
export async function stopLinuxMonitoring(
  id: number,
): Promise<LinuxMonitoringStatus> {
  return requestJson(`/linux-servers/${id}/monitoring/stop`, { method: "POST" })
}

export interface LinuxMetricSnapshot {
  id: number
  linux_server_id: number
  collected_at: string
  cpu_percent?: number | null
  memory_percent?: number | null
  swap_percent?: number | null
  disk_percent?: number | null
  disk_io_read_bytes_per_sec?: number | null
  disk_io_write_bytes_per_sec?: number | null
  load_1m?: number | null
  load_5m?: number | null
  load_15m?: number | null
  uptime_seconds?: number | null
  network_rx_bytes_per_sec?: number | null
  network_tx_bytes_per_sec?: number | null
  packets_per_sec?: number | null
  interface_errors?: number | null
  interface_drops?: number | null
  details?: Record<string, unknown>
}
export async function getLinuxCurrentMetrics(
  id: number,
): Promise<LinuxMetricSnapshot> {
  return requestJson(`/linux-servers/${id}/metrics/latest`)
}
export async function getLinuxMetricHistory(
  id: number,
  since?: string,
): Promise<LinuxMetricSnapshot[]> {
  return requestJson(
    `/linux-servers/${id}/metrics/history${
      since ? `?since=${encodeURIComponent(since)}` : ""
    }`,
  )
}
export async function listLinuxSecurityEvents(
  id: number,
): Promise<LinuxSecurityEvent[]> {
  return requestJson(`/linux-servers/${id}/security/events`)
}

export interface RCAEvidence {
  id: number
  evidence_type: string
  alert_id?: number | null
  event_id?: number | null
  relationship_id?: number | null
  score: number
  reason: string
  payload?: Record<string, unknown> | null
}
export interface RCAAlert {
  id: number
  device_id?: number | null
  severity: string
  title: string
  description?: string | null
  status: string
  created_at: string
}
export interface RCAIncident {
  id: number
  root_kind: string
  root_label: string
  root_device_id?: number | null
  root_interface_id?: number | null
  root_ci_id?: number | null
  confidence: number
  impact_summary: string
  window_start: string
  window_end: string
  created_at?: string
  updated_at?: string
  evidence: RCAEvidence[]
  raw_alerts?: RCAAlert[]
}
export async function analyzeRCA(
  hours: number,
): Promise<{ incident: RCAIncident | null alerts_considered: number }> {
  return requestJson("/rca/analyze", {
    method: "POST",
    body: JSON.stringify({ hours }),
  })
}
export async function listRCAIncidents(
  hours = 24,
): Promise<{ items: RCAIncident[] skip: number limit: number }> {
  return requestJson(`/rca/incidents?hours=${hours}`)
}
export async function getRCAIncident(id: number): Promise<RCAIncident> {
  return requestJson(`/rca/incidents/${id}`)
}
export async function analyzeIncidentRCA(
  id: number,
): Promise<{ incident_id: number rca: RCAIncident }> {
  return requestJson(`/incidents/${id}/rca`, { method: "POST" })
}

export interface ManagedIncident {
  id: number
  title: string
  description?: string | null
  category: string
  priority: string
  status: string
  correlation_key?: string | null
  assigned_to?: number | null
  created_by?: number | null
  rca_incident_id?: number | null
  rca?: RCAIncident | null
  service_id?: number | null
  acknowledged_at?: string | null
  acknowledged_by?: number | null
  resolved_at?: string | null
  closed_at?: string | null
  created_at?: string
  updated_at?: string
  alert_ids: number[]
  alerts?: Array<RCAAlert & {
    device_name?: string | null
    ip_address?: string | null
    interface_name?: string | null
    resolved_at?: string | null
  }>
  sla?: {
    response_deadline: string
    resolution_deadline: string
    response_breached: boolean
    resolution_breached: boolean
    paused_at?: string | null
    paused_seconds: number
  } | null
  sla_history?: Array<{
    id: number
    action: string
    details?: string | null
    created_at: string
  }>
  history?: Array<{
    id: number
    action: string
    actor_id?: number | null
    old_value?: string | null
    new_value?: string | null
    reason?: string | null
    created_at: string
  }>
  comments?: Array<{
    id: number
    body: string
    author_id?: number | null
    created_at: string
  }>
  attachments?: Array<{
    id: number
    file_name: string
    content_type?: string | null
    size_bytes: number
    storage_key: string
    created_at: string
  }>
}
export async function listIncidents(
  params: { status_filter?: string category?: string priority?: string } = {},
): Promise<{ items: ManagedIncident[] skip: number limit: number }> {
  const query = new URLSearchParams(params as Record<string, string>).toString()
  return requestJson(`/incidents${query ? `?${query}` : ""}`)
}
export async function createIncident(data: {
  title: string
  description?: string
  category: string
  priority: string
  assigned_to?: number
  service_id?: number
  alert_ids?: number[]
  rca_incident_id?: number
}): Promise<ManagedIncident> {
  return requestJson("/incidents", {
    method: "POST",
    body: JSON.stringify(data),
  })
}
export interface SLAPolicy {
  id: number
  priority: string
  service_id?: number | null
  response_target_minutes: number
  resolution_target_minutes: number
  pause_states: string[]
  escalation_after_minutes?: number | null
  enabled: boolean
}
export async function listIncidentSLAPolicies(): Promise<SLAPolicy[]> {
  return requestJson("/incidents/sla/policies")
}
export async function updateIncident(
  id: number,
  data: Record<string, unknown>,
): Promise<ManagedIncident> {
  return requestJson(`/incidents/${id}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  })
}
export async function getManagedIncident(id: number): Promise<ManagedIncident> {
  return requestJson(`/incidents/${id}`)
}
export async function acknowledgeIncident(
  id: number,
): Promise<ManagedIncident> {
  return requestJson(`/incidents/${id}/acknowledge`, { method: "POST" })
}
export async function resolveIncident(id: number): Promise<ManagedIncident> {
  return requestJson(`/incidents/${id}/resolve`, { method: "POST" })
}
export async function reopenIncident(id: number): Promise<ManagedIncident> {
  return requestJson(`/incidents/${id}/reopen`, { method: "POST" })
}
export async function getIncidentHistory(
  id: number,
): Promise<ManagedIncident["history"]> {
  return requestJson(`/incidents/${id}/history`)
}
export async function addIncidentComment(
  id: number,
  body: string,
): Promise<unknown> {
  return requestJson(`/incidents/${id}/comments`, {
    method: "POST",
    body: JSON.stringify({ body }),
  })
}

export interface ManagedProblemIncident {
  id: number
  title: string
  status: string
  priority: string
  rca?: {
    id: number
    reference: string
    status: string
    probable_root_cause: string
    root_kind: string
    root_label: string
    confidence: number
    impact_summary: string
    updated_at?: string
  } | null
}
export interface ManagedProblem {
  id: number
  number: string
  title: string
  description?: string | null
  category: string
  priority: string
  status: string
  root_cause?: string | null
  workaround?: string | null
  known_error?: string | null
  permanent_fix?: string | null
  owner_id?: number | null
  incident_ids: number[]
  incidents?: ManagedProblemIncident[]
  history?: Array<{
    id: number
    action: string
    field_name?: string | null
    old_value?: string | null
    new_value?: string | null
    created_at: string
  }>
}
export async function listProblems(
  params: { status?: string category?: string } = {},
): Promise<{ items: ManagedProblem[] skip: number limit: number }> {
  const query = new URLSearchParams(params as Record<string, string>).toString()
  return requestJson(`/problems${query ? `?${query}` : ""}`)
}
export async function createProblem(
  data: Record<string, unknown>,
): Promise<ManagedProblem> {
  return requestJson("/problems", {
    method: "POST",
    body: JSON.stringify(data),
  })
}
export async function getProblem(id: number): Promise<ManagedProblem> {
  return requestJson(`/problems/${id}`)
}
export async function updateProblem(
  id: number,
  data: Record<string, unknown>,
): Promise<ManagedProblem> {
  return requestJson(`/problems/${id}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  })
}
export async function linkProblemIncident(
  problemId: number,
  incidentId: number,
): Promise<{ linked: boolean }> {
  return requestJson(`/problems/${problemId}/incidents/${incidentId}`, {
    method: "POST",
  })
}

export interface ChangeRequest {
  id: number
  number: string
  title: string
  description?: string | null
  category: string
  risk: string
  impact: string
  priority: string
  status: string
  requested_by?: number | null
  owner_id?: number | null
  approved_by?: number | null
  approved_at?: string | null
  approval_required: boolean
  approval_comment?: string | null
  rejected_by?: number | null
  rejected_at?: string | null
  rejection_comment?: string | null
  maintenance_start?: string | null
  maintenance_end?: string | null
  implementation_plan?: string | null
  rollback_plan?: string | null
  implementation_result?: string | null
  implementation_failure_reason?: string | null
  rollback_result?: string | null
  rollback_status?: string | null
  closure_note?: string | null
  ci_ids: number[]
  incident_ids: number[]
  problem_ids: number[]
  cis?: Array<{ id: number name: string status?: string | null }>
  incidents?: Array<{
    id: number
    title: string
    status: string
    priority?: string | null
  }>
  problems?: Array<{
    id: number
    number: string
    title: string
    status: string
    priority?: string | null
  }>
  history?: Array<{
    id: number
    action: string
    field_name?: string | null
    old_value?: string | null
    new_value?: string | null
    created_at: string
  }>
}
export async function listChanges(
  params: { status?: string risk?: string } = {},
): Promise<{ items: ChangeRequest[] skip: number limit: number }> {
  const query = new URLSearchParams(params as Record<string, string>).toString()
  return requestJson(`/changes${query ? `?${query}` : ""}`)
}
export async function createChange(
  data: Record<string, unknown>,
): Promise<ChangeRequest> {
  return requestJson("/changes", { method: "POST", body: JSON.stringify(data) })
}
export async function updateChange(
  id: number,
  data: Record<string, unknown>,
): Promise<ChangeRequest> {
  return requestJson(`/changes/${id}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  })
}
export async function submitChange(id: number): Promise<ChangeRequest> {
  return requestJson(`/changes/${id}/submit`, { method: "POST" })
}
export async function approveChange(
  id: number,
  comment?: string,
): Promise<ChangeRequest> {
  return requestJson(`/changes/${id}/approve`, {
    method: "POST",
    body: JSON.stringify({ comment }),
  })
}
export async function rejectChange(
  id: number,
  comment?: string,
): Promise<ChangeRequest> {
  return requestJson(`/changes/${id}/reject`, {
    method: "POST",
    body: JSON.stringify({ comment }),
  })
}
export async function scheduleChange(id: number): Promise<ChangeRequest> {
  return requestJson(`/changes/${id}/schedule`, { method: "POST" })
}
export async function startChangeImplementation(
  id: number,
): Promise<ChangeRequest> {
  return requestJson(`/changes/${id}/implementation/start`, { method: "POST" })
}
export async function completeChangeImplementation(
  id: number,
  result?: string,
): Promise<ChangeRequest> {
  return requestJson(`/changes/${id}/implementation/complete`, {
    method: "POST",
    body: JSON.stringify({ result }),
  })
}
export async function failChangeImplementation(
  id: number,
  failure_reason?: string,
): Promise<ChangeRequest> {
  return requestJson(`/changes/${id}/implementation/fail`, {
    method: "POST",
    body: JSON.stringify({ failure_reason }),
  })
}
export async function rollbackChange(
  id: number,
  result?: string,
  status = "completed",
): Promise<ChangeRequest> {
  return requestJson(`/changes/${id}/rollback`, {
    method: "POST",
    body: JSON.stringify({ result, status }),
  })
}
export async function closeChange(
  id: number,
  comment?: string,
): Promise<ChangeRequest> {
  return requestJson(`/changes/${id}/close`, {
    method: "POST",
    body: JSON.stringify({ comment }),
  })
}
export async function linkChangeCI(
  changeId: number,
  ciId: number,
): Promise<{ linked: boolean }> {
  return requestJson(`/changes/${changeId}/cis/${ciId}`, { method: "POST" })
}
export async function linkChangeIncident(
  changeId: number,
  incidentId: number,
): Promise<{ linked: boolean }> {
  return requestJson(`/changes/${changeId}/incidents/${incidentId}`, {
    method: "POST",
  })
}
export async function linkChangeProblem(
  changeId: number,
  problemId: number,
): Promise<{ linked: boolean }> {
  return requestJson(`/changes/${changeId}/problems/${problemId}`, {
    method: "POST",
  })
}
export async function unlinkChangeCI(
  changeId: number,
  ciId: number,
): Promise<{ linked: boolean }> {
  return requestJson(`/changes/${changeId}/cis/${ciId}`, { method: "DELETE" })
}
export async function unlinkChangeIncident(
  changeId: number,
  incidentId: number,
): Promise<{ linked: boolean }> {
  return requestJson(`/changes/${changeId}/incidents/${incidentId}`, {
    method: "DELETE",
  })
}
export async function unlinkChangeProblem(
  changeId: number,
  problemId: number,
): Promise<{ linked: boolean }> {
  return requestJson(`/changes/${changeId}/problems/${problemId}`, {
    method: "DELETE",
  })
}
export async function listChangeIncidents(): Promise<ManagedIncident[]> {
  return requestJson("/changes/available/incidents")
}
export async function listChangeProblems(): Promise<ManagedProblem[]> {
  return requestJson("/changes/available/problems")
}
export async function listChangeCIs(): Promise<CMDBItem[]> {
  return requestJson("/changes/available/cis")
}

export interface KnowledgeArticle {
  id: number
  number: string
  title: string
  summary?: string | null
  article_type: string
  category?: string | null
  tags: string[]
  owner_id?: number | null
  status: string
  published_at?: string | null
  view_count: number
  helpful_count: number
  not_helpful_count: number
  current_version: number
  body?: string | null
  incident_ids: number[]
  problem_ids: number[]
  change_ids: number[]
  ci_ids: number[]
  device_ids: number[]
  service_ids: number[]
  related_article_ids: number[]
  changes?: Array<{ id: number number: string title: string status: string }>
  cis?: Array<{ id: number name: string status: string }>
  related_articles?: Array<{
    id: number
    number: string
    title: string
    status: string
  }>
  usage?: { incident_count: number problem_count: number }
  versions?: Array<{
    version: number
    changed_by?: number | null
    created_at: string
  }>
  history?: Array<{
    id: number
    action: string
    actor_id?: number | null
    metadata?: Record<string, unknown> | null
    created_at: string
  }>
}
export async function listKnowledge(
  filters: {
    search?: string
    article_type?: string
    status?: string
    category?: string
    tag?: string
    owner_id?: number | string
  } = {},
): Promise<{ items: KnowledgeArticle[] skip: number limit: number }> {
  const query = new URLSearchParams()
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== undefined && value !== "") query.set(key, String(value))
  })
  return requestJson(`/knowledge${query.size ? `?${query.toString()}` : ""}`)
}
export async function createKnowledge(
  data: Record<string, unknown>,
): Promise<KnowledgeArticle> {
  return requestJson("/knowledge", {
    method: "POST",
    body: JSON.stringify(data),
  })
}
export async function getKnowledge(id: number): Promise<KnowledgeArticle> {
  return requestJson(`/knowledge/${id}`)
}
export async function updateKnowledge(
  id: number,
  data: Record<string, unknown>,
): Promise<KnowledgeArticle> {
  return requestJson(`/knowledge/${id}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  })
}
export async function submitKnowledgeForReview(
  id: number,
): Promise<KnowledgeArticle> {
  return requestJson(`/knowledge/${id}/submit-review`, { method: "POST" })
}
export async function returnKnowledgeToDraft(
  id: number,
): Promise<KnowledgeArticle> {
  return requestJson(`/knowledge/${id}/return-to-draft`, { method: "POST" })
}
export async function publishKnowledge(id: number): Promise<KnowledgeArticle> {
  return requestJson(`/knowledge/${id}/publish`, { method: "POST" })
}
export async function retireKnowledge(id: number): Promise<KnowledgeArticle> {
  return requestJson(`/knowledge/${id}/retire`, { method: "POST" })
}
export async function restoreKnowledge(id: number): Promise<KnowledgeArticle> {
  return requestJson(`/knowledge/${id}/restore`, { method: "POST" })
}
export async function listKnowledgeAvailable(
  type: "incidents" | "problems" | "changes" | "cis" | "devices" | "services",
): Promise<Array<Record<string, unknown>>> {
  return requestJson(`/knowledge/available/${type}`)
}
export async function linkKnowledgeRelationship(
  articleId: number,
  type: string,
  targetId: number,
): Promise<{ linked: boolean }> {
  return requestJson(`/knowledge/${articleId}/${type}/${targetId}`, {
    method: "POST",
  })
}
export async function unlinkKnowledgeRelationship(
  articleId: number,
  type: string,
  targetId: number,
): Promise<{ linked: boolean }> {
  return requestJson(`/knowledge/${articleId}/${type}/${targetId}`, {
    method: "DELETE",
  })
}
export async function submitKnowledgeFeedback(
  articleId: number,
  helpful: boolean,
): Promise<KnowledgeArticle> {
  return requestJson(`/knowledge/${articleId}/feedback`, {
    method: "POST",
    body: JSON.stringify({ helpful }),
  })
}

export interface ConfigurationVersion {
  id: number
  device_id: number
  version: number
  source: string
  checksum: string
  is_startup: boolean
  captured_at: string
  unchanged?: boolean
  content?: string | null
}
export async function captureConfiguration(data: {
  device_id: number
  source: string
  content: string
  is_startup?: boolean
}): Promise<ConfigurationVersion> {
  return requestJson("/config-backups/capture", {
    method: "POST",
    body: JSON.stringify(data),
  })
}
export async function listConfigurationVersions(
  deviceId: number,
): Promise<{ items: ConfigurationVersion[] skip: number limit: number }> {
  return requestJson(`/config-backups/devices/${deviceId}`)
}
export async function getConfigurationVersion(
  deviceId: number,
  version: number,
): Promise<ConfigurationVersion> {
  return requestJson(`/config-backups/devices/${deviceId}/versions/${version}`)
}
export interface ConfigurationComparison {
  id: number
  device_id: number
  from_version: number
  to_version: number
  added_lines: string[]
  removed_lines: string[]
  changed_lines: Array<{
    from_line: string[]
    to_line: string[]
    from_number: number
    to_number: number
  }>
  initiated_by?: number | null
  created_at: string
}
export async function compareConfigurationVersions(
  deviceId: number,
  fromVersion: number,
  toVersion: number,
): Promise<ConfigurationComparison> {
  return requestJson("/config-backups/compare", {
    method: "POST",
    body: JSON.stringify({
      device_id: deviceId,
      from_version: fromVersion,
      to_version: toVersion,
    }),
  })
}
export async function compareBaselineCurrent(
  deviceId: number,
): Promise<ConfigurationComparison> {
  return requestJson(
    `/config-backups/devices/${deviceId}/compare/baseline-current`,
  )
}
export interface ConfigurationCompliancePolicy {
  id: number
  name: string
  description?: string | null
  rules: Record<string, unknown>
  enabled: boolean
  created_by?: number | null
  created_at: string
}
export interface ConfigurationComplianceViolation {
  id: number
  policy_id: number
  device_id: number
  version: number
  severity: string
  status: string
  evidence: Record<string, unknown>
  recommendation?: string | null
  detected_at: string
  resolved_at?: string | null
}
export async function listConfigurationCompliancePolicies(): Promise<{
  items: ConfigurationCompliancePolicy[]
}> {
  return requestJson("/config-compliance/policies")
}
export async function createConfigurationCompliancePolicy(data: {
  name: string
  description?: string
  rules: Record<string, unknown>
  enabled?: boolean
}): Promise<ConfigurationCompliancePolicy> {
  return requestJson("/config-compliance/policies", {
    method: "POST",
    body: JSON.stringify(data),
  })
}
export async function evaluateConfigurationCompliance(
  policy_id: number,
  device_id: number,
): Promise<{
  compliant: boolean
  violation: ConfigurationComplianceViolation | null
}> {
  return requestJson("/config-compliance/evaluate", {
    method: "POST",
    body: JSON.stringify({ policy_id, device_id }),
  })
}
export async function listConfigurationComplianceViolations(
  status?: string,
): Promise<{ items: ConfigurationComplianceViolation[] }> {
  return requestJson(
    `/config-compliance/violations${
      status ? `?status=${encodeURIComponent(status)}` : ""
    }`,
  )
}
export interface AvailabilityOutage {
  id: number
  device_id?: number | null
  start_time: string
  end_time?: string | null
  duration_seconds: number
  ongoing: boolean
  planned: boolean
  reason?: string | null
}
export interface AvailabilityReport {
  id: number
  entity_type: string
  entity_id: number
  device_name?: string | null
  ip_address?: string | null
  current_status?: string | null
  requested_duration_seconds: number
  monitored_duration_seconds: number
  uptime_seconds: number
  downtime_seconds: number
  unknown_seconds: number
  availability_percent: number | null
  coverage_percent: number | null
  planned_downtime_seconds: number
  unplanned_downtime_seconds: number
  outage_count: number
  last_outage?: AvailabilityOutage | null
  current_outage?: AvailabilityOutage | null
  outages?: AvailabilityOutage[]
  mttr_seconds: number | null
  mtbf_seconds: number | null
  sla_target_percent: number
  achieved_percent: number | null
  sla_breached: boolean | null
  downtime_reasons: Record<string, number>
  window_start: string
  window_end: string
  generated_at?: string
}
export interface AvailabilityReportRequest {
  entity_type: string
  entity_id: number
  start: string
  end: string
  sla_target?: number
}
export async function listAvailabilityReports(params?: {
  entity_type?: string
  entity_id?: number
  limit?: number
}): Promise<{ items: AvailabilityReport[] }> {
  const query = new URLSearchParams()
  if (params?.entity_type) query.set("entity_type", params.entity_type)
  if (params?.entity_id != null)
    query.set("entity_id", String(params.entity_id))
  if (params?.limit != null) query.set("limit", String(params.limit))
  return requestJson(
    `/availability/reports${query.size ? `?${query.toString()}` : ""}`,
  )
}
export async function createAvailabilityReport(
  payload: AvailabilityReportRequest,
): Promise<AvailabilityReport> {
  return requestJson("/availability/reports", {
    method: "POST",
    body: JSON.stringify(payload),
  })
}
export async function getAvailabilityReport(
  id: number,
): Promise<AvailabilityReport> {
  return requestJson(`/availability/reports/${id}`)
}
export interface QoSSample {
  id: number
  device_id: number
  interface_id?: number | null
  observed_at: string
  tos?: number | null
  dscp?: number | null
  phb?: string | null
  traffic_class?: string | null
  queue_utilization?: number | null
  queue_drops: number
  source: string
}
export async function listQoSSamples(deviceId?: number): Promise<QoSSample[]> {
  return requestJson(`/qos/samples${deviceId ? `?device_id=${deviceId}` : ""}`)
}
export interface BGPObservation {
  id: number
  device_id: number
  neighbor: string
  state: string
  remote_as?: number | null
  next_hop?: string | null
  prefixes: number
  as_path?: string | null
  observed_at: string
}
export async function listBGPNeighbors(
  deviceId?: number,
): Promise<BGPObservation[]> {
  return requestJson(
    `/bgp/neighbors${deviceId ? `?device_id=${deviceId}` : ""}`,
  )
}
export async function collectLinuxSecurity(
  id: number,
  data: Record<string, unknown>,
): Promise<{
  success: boolean
  status: string
  message: string
  collected_events: number
  warnings: string[]
  events: LinuxSecurityEvent[]
}> {
  return requestJson(`/linux-servers/${id}/security/collect`, {
    method: "POST",
    body: JSON.stringify(data),
  })
}
