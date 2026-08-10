const DEFAULT_API_BASE = '/api/v1'
const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? DEFAULT_API_BASE).replace(/\/$/, '')

let authToken: string | null = null
let authPromise: Promise<string> | null = null

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
}

async function requestJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = await ensureAuth()
  const response = await fetch(buildUrl(path), {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
      ...(init.headers ?? {}),
    },
  })

  if (response.status === 401) {
    authToken = null
    window.localStorage.removeItem('nms_access_token')
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
  return requestJson<DeviceRecord[]>('/snmp/devices')
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
