const DEFAULT_API_BASE = '/api/v1'
const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? DEFAULT_API_BASE).replace(/\/$/, '')
const GET_CACHE_TTL_MS = 15_000
const GET_CACHE_PREFIX = 'nms.api.cache.v1:'

let authToken: string | null = null
let authPromise: Promise<string> | null = null
const getCache = new Map<string, { expiresAt: number; value: unknown }>()
const inflightRequests = new Map<string, Promise<unknown>>()

function buildUrl(path: string) {
  return `${API_BASE}${path.startsWith('/') ? path : `/${path}`}`
}

/** Load token from localStorage if present. Does NOT auto-login. */
async function ensureAuth(): Promise<string> {
  if (authToken) return authToken
  if (authPromise) return authPromise

  const cached = window.localStorage.getItem('nms_access_token')
  if (cached) {
    authToken = cached
    return cached
  }

  throw new Error('Not authenticated')
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
    const parsed = JSON.parse(persisted) as { expiresAt?: number; value?: T }
    if (!parsed?.expiresAt || parsed.expiresAt <= now) {
      window.sessionStorage.removeItem(`${GET_CACHE_PREFIX}${key}`)
      return null
    }
    getCache.set(key, { expiresAt: parsed.expiresAt, value: parsed.value as unknown })
    return parsed.value ?? null
  } catch {
    return null
  }
}

function writeCached<T>(key: string, value: T) {
  const record = { expiresAt: Date.now() + GET_CACHE_TTL_MS, value }
  getCache.set(key, record)
  try {
    window.sessionStorage.setItem(`${GET_CACHE_PREFIX}${key}`, JSON.stringify(record))
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
    keys.forEach(key => window.sessionStorage.removeItem(key))
  } catch {
    // ignore storage failures
  }
}

/** Explicit login — stores token in memory + localStorage. */
export async function login(email: string, password: string): Promise<string> {
  const response = await fetch(buildUrl('/auth/login'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })
  if (!response.ok) {
    const detail = await response.json().catch(() => null)
    throw new Error(detail?.detail ?? 'Invalid credentials')
  }
  const payload = await response.json()
  authToken = payload.access_token as string
  window.localStorage.setItem('nms_access_token', authToken)
  return authToken
}

/** Clear auth state. */
export function logout() {
  authToken = null
  authPromise = null
  window.localStorage.removeItem('nms_access_token')
  clearRequestCache()
}

export async function requestJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = await ensureAuth()
  const method = (init.method ?? 'GET').toUpperCase()
  const canCache = method === 'GET' && !init.signal && !init.body
  const key = canCache ? cacheKey(path, token) : ''

  if (canCache) {
    const cached = readCached<T>(key)
    if (cached !== null) return cached
    const existing = inflightRequests.get(key)
    if (existing) return existing as Promise<T>
  }

  const request = fetch(buildUrl(path), {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
      ...(init.headers ?? {}),
    },
  }).then(async response => {
    if (response.status === 401) {
      authToken = null
      window.localStorage.removeItem('nms_access_token')
      clearRequestCache()
      return requestJson<T>(path, init)
    }

    if (!response.ok) {
      let detail = ''
      try {
        const body = await response.json() as { detail?: string | { message?: string } }
        detail = typeof body.detail === 'string' ? body.detail : body.detail?.message ?? ''
      } catch { /* non-JSON error */ }
      throw new Error(detail ? `Request failed: ${response.status} — ${detail}` : `Request failed: ${response.status}`)
    }

    return response.json() as Promise<T>
  })

  if (canCache) inflightRequests.set(key, request as Promise<unknown>)
  try {
    const result = await request
    if (canCache) writeCached(key, result)
    return result
  } finally {
    if (canCache) inflightRequests.delete(key)
  }
}

export interface DashboardSummary {
  total_devices: number
  online_devices: number
  offline_devices: number
  active_alerts: number
  critical_alerts: number
  recent_events: number
}

export interface DeviceRecord {
  id: number
  hostname: string
  ip_address: string
  snmp_version?: string | null
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
  last_status_change?: string | null
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
  event: 'progress' | 'discovered' | 'complete' | 'error'
  data: any
}

export interface ChunkedDiscoveryJobStatus {
  progress: ChunkedDiscoveryProgress
  discovered: Record<string, unknown>[]
}

export interface AddDiscoveredDevicesPayload {
  devices: Record<string, unknown>[]
  site_id?: number | null
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
  return requestJson<DashboardSummary>('/dashboard/summary')
}

export async function detectLocalSubnet(): Promise<{ subnet: string; ip: string | null }> {
  return requestJson<{ subnet: string; ip: string | null }>('/discovery/local-subnet')
}

export async function listDevices(): Promise<DeviceRecord[]> {
  return requestJson<DeviceRecord[]>('/devices')
}

/** Devices with an explicitly configured SNMP credential only. */
export async function listSNMPDevices(): Promise<DeviceRecord[]> {
  const payload = await requestJson<DeviceRecord[] | { items?: DeviceRecord[]; devices?: DeviceRecord[] }>('/snmp/devices')
  if (Array.isArray(payload)) return payload
  if (Array.isArray(payload.items)) return payload.items
  if (Array.isArray(payload.devices)) return payload.devices
  return []
}

export interface SNMPDiscoveryPayload {
  ips: string[]
  snmp_version: 'v2c' | 'v3'
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

export async function discoverSNMP(payload: SNMPDiscoveryPayload): Promise<SNMPDiscoveryResponse> {
  return requestJson<SNMPDiscoveryResponse>('/discovery/snmp', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function listDeviceMetrics(deviceId?: number): Promise<DeviceMetricRecord[]> {
  const path = deviceId ? `/device-metrics?device_id=${deviceId}` : '/device-metrics'
  return requestJson<DeviceMetricRecord[]>(path)
}

export async function listAlerts(statusFilter?: string): Promise<AlertRecord[]> {
  const path = statusFilter ? `/alerts?status_filter=${encodeURIComponent(statusFilter)}` : '/alerts'
  return requestJson<AlertRecord[]>(path)
}

export async function listEvents(): Promise<EventRecord[]> {
  return requestJson<EventRecord[]>('/events')
}

export async function listInterfaces(): Promise<InterfaceRecord[]> {
  return requestJson<InterfaceRecord[]>('/interfaces')
}

export async function listNotifications(): Promise<NotificationRecord[]> {
  return requestJson<NotificationRecord[]>('/notifications')
}

export async function startChunkedDiscovery(payload: ChunkedDiscoveryRequest): Promise<ChunkedDiscoveryStartResponse> {
  return requestJson<ChunkedDiscoveryStartResponse>('/discovery/chunked-scan', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function getChunkedDiscoveryStatus(jobId: string): Promise<ChunkedDiscoveryJobStatus> {
  return requestJson<ChunkedDiscoveryJobStatus>(`/discovery/chunked-scan/${jobId}`)
}

export async function addDiscoveredDevices(payload: AddDiscoveredDevicesPayload): Promise<{ added_count: number; skipped_count: number; added: Array<Record<string, unknown>>; skipped: Array<Record<string, unknown>> }> {
  return requestJson('/discovery/add-devices', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function checkStoredDevices(ips: string[]): Promise<{ stored_ips: string[] }> {
  return requestJson('/discovery/check-stored', {
    method: 'POST',
    body: JSON.stringify({ ips }),
  })
}

export async function startMonitoringDevice(payload: MonitorDevicePayload): Promise<Record<string, unknown>> {
  return requestJson('/discovery/monitoring/start', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function stopMonitoringDevice(ip: string): Promise<{ ip: string; stopped: boolean }> {
  return requestJson('/discovery/monitoring/stop', {
    method: 'POST',
    body: JSON.stringify({ ip }),
  })
}

export async function startAllMonitoring(devices: Record<string, unknown>[]): Promise<{ added: number; total_monitored: number }> {
  return requestJson('/discovery/monitoring/start-all', {
    method: 'POST',
    body: JSON.stringify({ devices }),
  })
}

export async function stopAllMonitoring(): Promise<{ stopped: number }> {
  return requestJson('/discovery/monitoring/stop-all', {
    method: 'POST',
  })
}

export async function streamChunkedDiscovery(jobId: string, onEvent: (event: ChunkedDiscoveryEvent) => void): Promise<void> {
  const token = await ensureAuth()
  const response = await fetch(buildUrl(`/discovery/chunked-scan/${jobId}/progress`), {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  })

  if (!response.ok) {
    throw new Error(`Discovery stream failed: ${response.status}`)
  }

  const reader = response.body?.getReader()
  if (!reader) {
    throw new Error('Discovery stream is not available in this browser')
  }

  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { value, done } = await reader.read()
    if (done) {
      break
    }

    buffer += decoder.decode(value, { stream: true })
    const parts = buffer.split('\n\n')
    buffer = parts.pop() ?? ''

    for (const part of parts) {
      const lines = part.split('\n').map(line => line.trimEnd())
      let eventName = 'message'
      let payload = ''

      for (const line of lines) {
        if (!line) continue
        if (line.startsWith('event:')) {
          eventName = line.slice(6).trim()
        } else if (line.startsWith('data:')) {
          payload += `${line.slice(5).trimStart()}\n`
        }
      }

      if (payload.trim()) {
        onEvent({
          event: eventName as ChunkedDiscoveryEvent['event'],
          data: JSON.parse(payload.trim()),
        })
      }
    }
  }

  const trailing = buffer.trim()
  if (trailing) {
    const lines = trailing.split('\n').map(line => line.trimEnd())
    let eventName = 'message'
    let payload = ''

    for (const line of lines) {
      if (!line) continue
      if (line.startsWith('event:')) {
        eventName = line.slice(6).trim()
      } else if (line.startsWith('data:')) {
        payload += `${line.slice(5).trimStart()}\n`
      }
    }

    if (payload.trim()) {
      onEvent({
        event: eventName as ChunkedDiscoveryEvent['event'],
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
    total_pings: number
    current_status: string
    last_seen: string | null
    last_status_change: string | null
  }
}

export async function getDeviceHistory(ip: string, hours = 24): Promise<DeviceHistoryResponse> {
  return requestJson<DeviceHistoryResponse>(`/discovery/device-history/${encodeURIComponent(ip)}?hours=${hours}`)
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
  return requestJson<MonitoringStatusResponse>('/discovery/monitoring/status')
}

export async function getDeviceStatusHistory(deviceId: number): Promise<Array<{
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
  event: 'update'
  data: MonitoringStatusResponse
}

export async function pingIps(ips: string[], timeoutMs = 1000): Promise<{ count: number; results: Array<{ ip: string; reachable: boolean; status: string; rtt?: number }> }> {
  return requestJson('/discovery/icmp', {
    method: 'POST',
    body: JSON.stringify({ ips, timeout_ms: timeoutMs }),
  })
}

export async function streamMonitoring(onEvent: (event: MonitoringStreamEvent) => void): Promise<() => void> {
  const token = await ensureAuth()
  const controller = new AbortController()

  const response = await fetch(buildUrl('/discovery/monitoring/stream'), {
    headers: { Authorization: `Bearer ${token}` },
    signal: controller.signal,
  })

  if (!response.ok) {
    throw new Error(`Monitoring stream failed: ${response.status}`)
  }

  const reader = response.body?.getReader()
  if (!reader) {
    throw new Error('Monitoring stream is not available')
  }

  const decoder = new TextDecoder()
  let buffer = ''

  const pump = async () => {
    try {
      while (true) {
        const { value, done } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const parts = buffer.split('\n\n')
        buffer = parts.pop() ?? ''

        for (const part of parts) {
          const lines = part.split('\n').map(l => l.trimEnd())
          let eventName = 'message'
          let payload = ''
          for (const line of lines) {
            if (!line) continue
            if (line.startsWith('event:')) eventName = line.slice(6).trim()
            else if (line.startsWith('data:')) payload += `${line.slice(5).trimStart()}\n`
          }
          if (payload.trim()) {
            onEvent({ event: eventName as MonitoringStreamEvent['event'], data: JSON.parse(payload.trim()) })
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

// ── Organizations ──

export interface OrganizationRecord {
  id: number
  name: string
  description?: string | null
  created_at: string
}

export async function listOrganizations(): Promise<OrganizationRecord[]> {
  return requestJson('/organizations')
}

export async function createOrganization(data: { name: string; description?: string }): Promise<OrganizationRecord> {
  return requestJson('/organizations', {
    method: 'POST',
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
  return requestJson('/sites')
}

export async function createSite(data: { name: string; organization_id: number; city?: string; state?: string }): Promise<SiteRecord> {
  return requestJson('/sites', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}
export async function updateSite(id: number, data: { name?: string; organization_id?: number; city?: string; state?: string }): Promise<SiteRecord> {
  return requestJson(`/sites/${id}`, { method: 'PATCH', body: JSON.stringify(data) })
}
export async function deleteSite(id: number): Promise<{ detail: string }> {
  return requestJson(`/sites/${id}`, { method: 'DELETE' })
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
  return requestJson('/devices', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function updateDevice(id: number, data: Partial<{
  hostname: string
  ip_address: string
  mac_address: string
  model: string
  serial_number: string
  firmware_version: string
  site_id: number
  status: string
}>): Promise<DeviceRecord> {
  return requestJson(`/devices/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export async function deleteDevice(id: number): Promise<{ deleted: boolean }> {
  return requestJson(`/devices/${id}`, { method: 'DELETE' })
}

export async function deleteAllDevices(): Promise<{ deleted: number; message: string }> {
  return requestJson('/devices', { method: 'DELETE' })
}

// ── Alerts ──

export async function clearAllAlerts(): Promise<{ cleared: number }> {
  return requestJson('/alerts/clear-all', { method: 'DELETE' })
}

// ── RBAC: Auth / Me ──

export interface UserRecord {
  id: number
  uuid: string
  name: string
  email: string
  role_id: number | null
  role_name: string | null
  permissions: string[]
  status: string
  created_at: string
}

export async function getMe(): Promise<UserRecord> {
  return requestJson<UserRecord>('/auth/me')
}

// ── RBAC: Roles ──

export interface RoleRecord {
  id: number
  role_name: string
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
  return requestJson<RoleRecord[]>('/roles')
}

export async function createRole(data: { role_name: string }): Promise<RoleRecord> {
  return requestJson('/roles', { method: 'POST', body: JSON.stringify(data) })
}

export async function updateRole(id: number, data: { role_name?: string }): Promise<RoleRecord> {
  return requestJson(`/roles/${id}`, { method: 'PATCH', body: JSON.stringify(data) })
}

export async function deleteRole(id: number): Promise<{ detail: string }> {
  return requestJson(`/roles/${id}`, { method: 'DELETE' })
}

export async function getRolePermissions(id: number): Promise<RoleWithPermissions> {
  return requestJson<RoleWithPermissions>(`/roles/${id}/permissions`)
}

export async function setRolePermissions(id: number, permission_ids: number[]): Promise<RoleWithPermissions> {
  return requestJson(`/roles/${id}/permissions`, {
    method: 'PUT',
    body: JSON.stringify({ permission_ids }),
  })
}

// ── RBAC: Permissions ──

export async function listPermissions(module?: string): Promise<PermissionRecord[]> {
  const path = module ? `/permissions?module=${encodeURIComponent(module)}` : '/permissions'
  return requestJson<PermissionRecord[]>(path)
}

// ── RBAC: Users ──

export async function listUsers(): Promise<UserRecord[]> {
  return requestJson<UserRecord[]>('/users')
}

export async function createUser(data: {
  name: string
  email: string
  password: string
  role_id?: number
  status?: string
}): Promise<UserRecord> {
  return requestJson('/users', { method: 'POST', body: JSON.stringify(data) })
}

export async function updateUser(id: number, data: {
  name?: string
  email?: string
  password?: string
  role_id?: number | null
  status?: string
}): Promise<UserRecord> {
  return requestJson(`/users/${id}`, { method: 'PATCH', body: JSON.stringify(data) })
}

export async function deleteUser(id: number): Promise<{ detail: string }> {
  return requestJson(`/users/${id}`, { method: 'DELETE' })
}

export async function assignUserRole(id: number, role_id: number): Promise<UserRecord> {
  return requestJson(`/users/${id}/role`, {
    method: 'POST',
    body: JSON.stringify({ role_id }),
  })
}

// ── SNMP Dynamic Monitoring ──

export interface SNMPModuleSummary {
  name: string
  supported: boolean
  status: 'supported' | 'unsupported' | 'error'
  last_poll?: string | null
  object_count?: number
  health?: 'healthy' | 'warning' | 'critical' | 'unknown'
  summary?: Record<string, any>
}

export interface SNMPDeviceOverview {
  device_id: number
  hostname: string
  ip_address: string
  vendor?: string | null
  model?: string | null
  uptime_seconds?: number
  health: 'healthy' | 'warning' | 'critical' | 'unknown'
  polling_enabled: boolean
  last_poll?: string | null
  modules: SNMPModuleSummary[]
}

export interface SNMPSystemInfo {
  hostname?: string
  description?: string
  uptime_seconds?: number
  uptime_display?: string
  contact?: string
  location?: string
  services?: number
  supported: boolean
}

export interface SNMPCPUStats {
  device_id: number
  current_usage?: number
  average?: number
  maximum?: number
  minimum?: number
  percentile_95?: number
  per_core?: Array<{ core: number; usage: number }>
  history: Array<{ timestamp: string; usage: number }>
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
  history: Array<{ timestamp: string; used: number; free: number; utilization: number }>
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
  health: 'healthy' | 'warning' | 'critical'
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
  status: 'UP' | 'DOWN' | 'UNKNOWN'
  admin_status: 'UP' | 'DOWN' | 'UNKNOWN'
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
  sensor_type: 'temperature' | 'fan' | 'voltage' | 'power' | 'humidity' | 'other'
  current_value?: number
  unit?: string
  threshold_warning?: number
  threshold_critical?: number
  status: 'ok' | 'warning' | 'critical' | 'unknown'
  history: Array<{ timestamp: string; value: number }>
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
  status: 'active' | 'inactive'
  last_updated: string
}

export interface SNMPVLANInfo {
  id: number
  device_id: number
  vlan_id: number
  vlan_name?: string
  tagged_ports?: string[]
  untagged_ports?: string[]
  status: 'active' | 'inactive'
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
  status: 'success' | 'failure'
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
  link_type: 'lldp' | 'cdp' | 'discovered'
  status: 'active' | 'inactive'
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

export async function getSNMPDeviceOverview(deviceId: number): Promise<SNMPDeviceOverview> {
  return requestJson<SNMPDeviceOverview>(`/snmp/devices/${deviceId}/overview`)
}

export async function getSNMPSystemInfo(deviceId: number): Promise<SNMPSystemInfo> {
  return requestJson<SNMPSystemInfo>(`/snmp/devices/${deviceId}/system`)
}

export async function getSNMPCPUStats(deviceId: number, hours = 24): Promise<SNMPCPUStats> {
  return requestJson<SNMPCPUStats>(`/snmp/devices/${deviceId}/cpu?hours=${hours}`)
}

export async function getSNMPMemoryStats(deviceId: number, hours = 24): Promise<SNMPMemoryStats> {
  return requestJson<SNMPMemoryStats>(`/snmp/devices/${deviceId}/memory?hours=${hours}`)
}

export async function getSNMPStorageVolumes(deviceId: number): Promise<SNMPStorageVolume[]> {
  return requestJson<SNMPStorageVolume[]>(`/snmp/devices/${deviceId}/storage`)
}

export async function getSNMPInterfaces(deviceId: number): Promise<SNMPInterfaceStats[]> {
  return requestJson<SNMPInterfaceStats[]>(`/snmp/devices/${deviceId}/interfaces`)
}

export async function getSNMPInterfaceHistory(interfaceId: number, hours = 24): Promise<SNMPInterfaceHistory> {
  return requestJson<SNMPInterfaceHistory>(`/snmp/interfaces/${interfaceId}/history?hours=${hours}`)
}

export async function getSNMPEnvironmentSensors(deviceId: number): Promise<SNMPEnvironmentSensor[]> {
  return requestJson<SNMPEnvironmentSensor[]>(`/snmp/devices/${deviceId}/environment`)
}

export async function getSNMPLLDPNeighbors(deviceId: number): Promise<SNMPLLDPNeighbor[]> {
  return requestJson<SNMPLLDPNeighbor[]>(`/snmp/devices/${deviceId}/lldp`)
}

export async function getSNMPRoutingTable(deviceId: number): Promise<SNMPRoutingEntry[]> {
  return requestJson<SNMPRoutingEntry[]>(`/snmp/devices/${deviceId}/routing`)
}

export async function getSNMPVLANs(deviceId: number): Promise<SNMPVLANInfo[]> {
  return requestJson<SNMPVLANInfo[]>(`/snmp/devices/${deviceId}/vlans`)
}

export async function getSNMPOIDCache(deviceId: number): Promise<SNMPOIDCacheEntry[]> {
  return requestJson<SNMPOIDCacheEntry[]>(`/snmp/devices/${deviceId}/oids`)
}

export async function getSNMPOIDTree(deviceId: number): Promise<SNMPOIDTree> {
  return requestJson<SNMPOIDTree>(`/snmp/devices/${deviceId}/oid-tree`)
}

export async function getSNMPPollingHistory(deviceId: number, hours = 24): Promise<SNMPPollingHistory[]> {
  return requestJson<SNMPPollingHistory[]>(`/snmp/devices/${deviceId}/polling-history?hours=${hours}`)
}

export async function getSNMPPollingStatistics(deviceId: number): Promise<SNMPPollingStatistics> {
  return requestJson<SNMPPollingStatistics>(`/snmp/devices/${deviceId}/polling-stats`)
}

export async function getSNMPTopology(deviceId?: number): Promise<SNMPTopologyGraph> {
  const path = deviceId ? `/snmp/topology?device_id=${deviceId}` : '/snmp/topology'
  return requestJson<SNMPTopologyGraph>(path)
}

// ── Overview (single call for entire Dashboard) ───────────────────────────

export interface DeviceOverviewItem {
  id: number
  hostname: string
  ip_address: string
  mac_address?: string | null
  status: string
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
}

export interface OverviewResponse {
  summary: {
    total_devices: number
    online_devices: number
    offline_devices: number
    warning_devices: number
    active_alerts: number
    critical_alerts: number
    recent_events: number
  }
  devices: DeviceOverviewItem[]
  alerts: AlertRecord[]
  events: EventRecord[]
  services: {
    snmp_polling: ServiceState
    realtime_monitor: ServiceState
    any_running: boolean
  }
  fetched_at: string
}

export async function getOverview(): Promise<OverviewResponse> {
  return requestJson<OverviewResponse>('/overview')
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
  return requestJson<KillAllResponse>('/monitoring/kill-all', { method: 'POST' })
}

export async function getServiceStates(): Promise<OverviewResponse['services']> {
  return requestJson<OverviewResponse['services']>('/monitoring/services')
}

// ── Organizations (full CRUD) ─────────────────────────────────────────────
export async function updateOrganization(id: number, data: { name?: string; description?: string }): Promise<OrganizationRecord> {
  return requestJson(`/organizations/${id}`, { method: 'PATCH', body: JSON.stringify(data) })
}
export async function deleteOrganization(id: number): Promise<{ detail: string }> {
  return requestJson(`/organizations/${id}`, { method: 'DELETE' })
}

// ── Vendors ───────────────────────────────────────────────────────────────
export interface VendorRecord {
  id: number
  vendor_name: string
}
export async function listVendors(): Promise<VendorRecord[]> {
  return requestJson<VendorRecord[]>('/vendors')
}
export async function createVendor(data: { vendor_name: string }): Promise<VendorRecord> {
  return requestJson('/vendors', { method: 'POST', body: JSON.stringify(data) })
}
export async function updateVendor(id: number, data: { vendor_name?: string }): Promise<VendorRecord> {
  return requestJson(`/vendors/${id}`, { method: 'PATCH', body: JSON.stringify(data) })
}
export async function deleteVendor(id: number): Promise<{ detail: string }> {
  return requestJson(`/vendors/${id}`, { method: 'DELETE' })
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
  return requestJson<ReportRecord[]>('/reports')
}
export async function createReport(data: { report_name: string; report_type: string; file_path?: string }): Promise<ReportRecord> {
  return requestJson('/reports', { method: 'POST', body: JSON.stringify(data) })
}
export async function updateReport(id: number, data: { report_name?: string; report_type?: string; file_path?: string }): Promise<ReportRecord> {
  return requestJson(`/reports/${id}`, { method: 'PATCH', body: JSON.stringify(data) })
}
export async function deleteReport(id: number): Promise<{ detail: string }> {
  return requestJson(`/reports/${id}`, { method: 'DELETE' })
}

// ── Daily Network Monitoring Report ──────────────────────────────────────
export interface DailyReportSeverity { [key: string]: number }
export interface DailyReportDevice { device_id: number; hostname: string; ip: string; avg_value?: number; max_value?: number; count?: number; status?: string; downtime_sec?: number; alerts?: number; reason?: string }
export interface DailyReportInterface { id: number; name: string; device_id: number; hostname: string; status: string; traffic_in?: number; traffic_out?: number; speed?: string; packet_errors?: number; last_updated?: string }
export interface DailyReportAlert { id: number; severity: string; title: string; description?: string | null; status: string; device_id?: number | null; hostname: string; created_at?: string | null }
export interface DailyReportChange { device_id: number; hostname: string; ip: string; old_status: string | null; new_status: string; reason?: string | null; timestamp?: string | null }
export interface DailyReportRecommendation { priority: string; message: string }

export interface DailyReport {
  report_date: string
  period: string
  generated_at: string
  availability: {
    total_devices: number; online: number; offline: number; warning: number
    availability_pct: number; downtime_events_24h: number
    devices_with_downtime: DailyReportDevice[]
  }
  performance: {
    sample_count: number
    cpu:      { avg: number | null; max: number | null; samples: number }
    memory:   { avg: number | null; max: number | null; samples: number }
    disk:     { avg: number | null; max: number | null; samples: number }
    latency:  { avg: number | null; max: number | null; samples: number }
    packet_loss: { avg: number | null; max: number | null; samples: number }
    bandwidth:   { avg: number | null; max: number | null; samples: number }
    top_cpu_devices: DailyReportDevice[]
    top_mem_devices: DailyReportDevice[]
    top_latency_devices: DailyReportDevice[]
  }
  interfaces: {
    total: number; up: number; down: number
    high_traffic: DailyReportInterface[]
    interfaces_with_errors: DailyReportInterface[]
    down_interfaces: DailyReportInterface[]
  }
  alerts: {
    total_alerts_24h: number; by_severity: DailyReportSeverity
    resolved: number; open: number
    critical: number; high: number; warning: number; info: number
    top_alert_devices: DailyReportDevice[]
    recent_alerts: DailyReportAlert[]
    total_events_24h: number; event_types: DailyReportSeverity
  }
  incidents: {
    total_status_changes: number; went_offline: number; came_online: number
    changes: DailyReportChange[]
  }
  top_performers: {
    top_cpu: DailyReportDevice[]; top_memory: DailyReportDevice[]
    top_latency: DailyReportDevice[]; max_downtime: DailyReportDevice[]
    max_alerts: DailyReportDevice[]
  }
  daily_summary: {
    overall_health: string; health_score: number; availability_pct: number
    issues: string[]; devices_needing_attention: DailyReportDevice[]
  }
  recommendations: DailyReportRecommendation[]
}

export async function getDailyReport(): Promise<DailyReport> {
  return requestJson<DailyReport>('/reports/daily')
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

export async function listSNMPDevicesOptimized(params: {
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
}): Promise<SNMPDevicesResponse> {
  const query = new URLSearchParams()
  if (params.page) query.set('page', String(params.page))
  if (params.page_size) query.set('page_size', String(params.page_size))
  if (params.search) query.set('search', params.search)
  if (params.status) query.set('status', params.status)
  if (params.snmp_status) query.set('snmp_status', params.snmp_status)
  if (params.monitoring_status) query.set('monitoring_status', params.monitoring_status)
  if (params.device_type) query.set('device_type', params.device_type)
  if (params.vendor) query.set('vendor', params.vendor)
  if (params.model) query.set('model', params.model)
  if (params.hostname) query.set('hostname', params.hostname)
  if (params.sort_by) query.set('sort_by', params.sort_by)
  if (params.sort_order) query.set('sort_order', params.sort_order)
  return requestJson<SNMPDevicesResponse>(`/snmp/devices?${query.toString()}`)
}

export async function getSNMPDeviceDetails(deviceId: number): Promise<SNMPDeviceDetails> {
  return requestJson<SNMPDeviceDetails>(`/snmp/devices/${deviceId}`)
}

export async function getSNMPDeviceMonitoringConfigs(deviceId: number): Promise<MonitoringConfig[]> {
  return requestJson<MonitoringConfig[]>(`/snmp/devices/${deviceId}/monitoring`)
}

export async function startModuleMonitoring(deviceId: number, module: string, intervalSeconds: number): Promise<MonitoringConfig & { message: string }> {
  return requestJson(`/snmp/devices/${deviceId}/monitoring/${module}/start`, {
    method: 'POST',
    body: JSON.stringify({ module_name: module, interval_seconds: intervalSeconds }),
  })
}

export async function stopModuleMonitoring(deviceId: number, module: string): Promise<{ stopped: boolean; message: string }> {
  return requestJson(`/snmp/devices/${deviceId}/monitoring/${module}/stop`, {
    method: 'POST',
  })
}

export async function updateModuleMonitoring(deviceId: number, module: string, data: MonitoringUpdateRequest): Promise<MonitoringConfig> {
  return requestJson(`/snmp/devices/${deviceId}/monitoring/${module}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
}

export async function getModuleMonitoringStatus(deviceId: number, module: string): Promise<MonitoringConfig> {
  return requestJson<MonitoringConfig>(`/snmp/devices/${deviceId}/monitoring/${module}/status`)
}

export async function getLatestMetrics(deviceId: number): Promise<{
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

export async function getLatestInterfaces(deviceId: number): Promise<LatestInterface[]> {
  return requestJson<LatestInterface[]>(`/snmp/devices/${deviceId}/interfaces/latest`)
}

export async function getLatestStorage(deviceId: number): Promise<LatestStorage[]> {
  return requestJson<LatestStorage[]>(`/snmp/devices/${deviceId}/storage/latest`)
}

export async function getLatestEnvironment(deviceId: number): Promise<LatestEnvironment[]> {
  return requestJson<LatestEnvironment[]>(`/snmp/devices/${deviceId}/environment/latest`)
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
  history: Array<{ timestamp: string; used: number; free: number; utilization: number }>
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
  status: 'UP' | 'DOWN' | 'UNKNOWN'
  admin_status: 'UP' | 'DOWN' | 'UNKNOWN'
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
  health: 'healthy' | 'warning' | 'critical'
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
  sensor_type: 'temperature' | 'fan' | 'voltage' | 'power' | 'humidity' | 'other'
  current_value?: number
  unit?: string
  threshold_warning?: number
  threshold_critical?: number
  status: 'ok' | 'warning' | 'critical' | 'unknown'
  history: Array<{ timestamp: string; value: number }>
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
  status: 'active' | 'inactive'
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
  status: 'active' | 'inactive'
  last_updated: string
}

export interface SNMPTopologyLink {
  source_device_id: number
  source_device_name: string
  source_port: string
  target_device_id: number
  target_device_name: string
  target_port: string
  link_type: 'lldp' | 'cdp' | 'discovered'
  status: 'active' | 'inactive'
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
  status: 'success' | 'failure'
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
export async function getSNMPStorageStats(deviceId: number): Promise<SNMPStorageStats> {
  return requestJson<SNMPStorageStats>(`/snmp/devices/${deviceId}/storage`)
}

export async function getSNMPEnvironmentStats(deviceId: number): Promise<SNMPEnvironmentStats> {
  return requestJson<SNMPEnvironmentStats>(`/snmp/devices/${deviceId}/environment`)
}

// Device CRUD - Add device with SNMP credentials
export interface AddDeviceRequest {
  ip_address: string
  name?: string
  hostname?: string
  snmp_version: 'v2c' | 'v3'
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

export async function addSNMPDevice(data: AddDeviceRequest): Promise<AddDeviceResponse> {
  return requestJson<AddDeviceResponse>('/devices/manual', {
    method: 'POST',
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

export async function testSNMPConnection(deviceId: number): Promise<SNMPTestResponse> {
  return requestJson<SNMPTestResponse>(`/snmp/devices/${deviceId}/test-snmp`, {
    method: 'POST',
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

export async function discoverDevice(deviceId: number): Promise<SNMPDiscoverResponse> {
  return requestJson<SNMPDiscoverResponse>(`/snmp/devices/${deviceId}/discover`, {
    method: 'POST',
  })
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
  return requestJson('/alerts', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function updateAlert(id: number, data: {
  severity?: string
  title?: string
  description?: string | null
  status?: string
}): Promise<AlertRecord> {
  return requestJson(`/alerts/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export async function deleteAlert(id: number): Promise<{ detail: string }> {
  return requestJson(`/alerts/${id}`, { method: 'DELETE' })
}

export async function acknowledgeAlert(id: number): Promise<AlertRecord> {
  return requestJson(`/alerts/${id}/acknowledge`, { method: 'POST' })
}

export async function resolveAlert(id: number): Promise<AlertRecord> {
  return requestJson(`/alerts/${id}/resolve`, { method: 'POST' })
}

// ── Events CRUD ─────────────────────────────────────────────────────────────

export async function createEvent(data: {
  device_id?: number | null
  event_type: string
  description?: string | null
}): Promise<EventRecord> {
  return requestJson('/events', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function updateEvent(id: number, data: {
  event_type?: string
  description?: string | null
}): Promise<EventRecord> {
  return requestJson(`/events/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export async function deleteEvent(id: number): Promise<{ detail: string }> {
  return requestJson(`/events/${id}`, { method: 'DELETE' })
}

// ── Notifications CRUD ──────────────────────────────────────────────────────

export async function createNotification(data: {
  alert_id?: number | null
  channel: string
  sent_to: string
  status?: string
}): Promise<NotificationRecord> {
  return requestJson('/notifications', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function updateNotification(id: number, data: {
  channel?: string
  sent_to?: string
  status?: string
}): Promise<NotificationRecord> {
  return requestJson(`/notifications/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export async function deleteNotification(id: number): Promise<{ detail: string }> {
  return requestJson(`/notifications/${id}`, { method: 'DELETE' })
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
  return requestJson<ThresholdRecord[]>('/thresholds')
}

export async function createThreshold(data: {
  metric_name: string
  threshold_value: number
  condition: string
  severity: string
  description?: string | null
}): Promise<ThresholdRecord> {
  return requestJson('/thresholds', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function updateThreshold(id: number, data: {
  metric_name?: string
  threshold_value?: number
  condition?: string
  severity?: string
  description?: string | null
}): Promise<ThresholdRecord> {
  return requestJson(`/thresholds/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export async function deleteThreshold(id: number): Promise<{ detail: string }> {
  return requestJson(`/thresholds/${id}`, { method: 'DELETE' })
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
  return requestJson<MonitoringJobRecord[]>('/monitoring-jobs')
}

export async function createMonitoringJob(data: {
  job_name: string
  job_type: string
  schedule: string
  enabled?: boolean
}): Promise<MonitoringJobRecord> {
  return requestJson('/monitoring-jobs', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function updateMonitoringJob(id: number, data: {
  job_name?: string
  job_type?: string
  schedule?: string
  enabled?: boolean
}): Promise<MonitoringJobRecord> {
  return requestJson(`/monitoring-jobs/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export async function deleteMonitoringJob(id: number): Promise<{ detail: string }> {
  return requestJson(`/monitoring-jobs/${id}`, { method: 'DELETE' })
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
  return requestJson('/interfaces', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function updateInterface(id: number, data: {
  interface_name?: string
  status?: string
  speed?: string | null
  traffic_in?: number
  traffic_out?: number
  packet_errors?: number
}): Promise<InterfaceRecord> {
  return requestJson(`/interfaces/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export async function deleteInterface(id: number): Promise<{ detail: string }> {
  return requestJson(`/interfaces/${id}`, { method: 'DELETE' })
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
  return requestJson<DeviceCredentialRecord[]>('/device-credentials')
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
  return requestJson('/device-credentials', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function updateDeviceCredential(id: number, data: {
  credential_type?: string
  username?: string | null
  password?: string | null
  community_string?: string | null
  auth_password?: string | null
  privacy_password?: string | null
  api_token?: string | null
}): Promise<DeviceCredentialRecord> {
  return requestJson(`/device-credentials/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export async function deleteDeviceCredential(id: number): Promise<{ detail: string }> {
  return requestJson(`/device-credentials/${id}`, { method: 'DELETE' })
}

// ── Device Types ────────────────────────────────────────────────────────────

export interface DeviceTypeRecord {
  id: number
  type_name: string
  description?: string | null
  created_at: string
}

export async function listDeviceTypes(): Promise<DeviceTypeRecord[]> {
  return requestJson<DeviceTypeRecord[]>('/device-types')
}

export async function createDeviceType(data: {
  type_name: string
  description?: string | null
}): Promise<DeviceTypeRecord> {
  return requestJson('/device-types', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function updateDeviceType(id: number, data: {
  type_name?: string
  description?: string | null
}): Promise<DeviceTypeRecord> {
  return requestJson(`/device-types/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export async function deleteDeviceType(id: number): Promise<{ detail: string }> {
  return requestJson(`/device-types/${id}`, { method: 'DELETE' })
}

// ── Audit Logs (Read-Only) ──────────────────────────────────────────────────

export interface AuditLogRecord {
  id: number
  user_id?: number | null
  user_name?: string | null
  action: string
  resource_name: string
  timestamp: string
}

export async function listAuditLogs(userId?: number): Promise<AuditLogRecord[]> {
  const query = userId == null ? '' : `?user_id=${userId}`
  return requestJson<AuditLogRecord[]>(`/audit-logs${query}`)
}

export async function recordPageView(page: string): Promise<void> {
  await requestJson(`/audit-logs/page-view?page=${encodeURIComponent(page)}`, { method: 'POST' })
}

export interface AuditLogUser { id: number; name: string; email: string }

export async function listAuditLogUsers(): Promise<AuditLogUser[]> {
  return requestJson<AuditLogUser[]>('/audit-logs/users')
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
  return requestJson('/device-metrics', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function updateDeviceMetric(id: number, data: {
  cpu_usage?: number | null
  memory_usage?: number | null
  disk_usage?: number | null
  temperature?: number | null
  latency?: number | null
  packet_loss?: number | null
  bandwidth_usage?: number | null
}): Promise<DeviceMetricRecord> {
  return requestJson(`/device-metrics/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export async function deleteDeviceMetric(id: number): Promise<{ detail: string }> {
  return requestJson(`/device-metrics/${id}`, { method: 'DELETE' })
}
