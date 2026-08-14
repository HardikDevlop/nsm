import { useState, useCallback, useMemo } from 'react'
import { useNavigate } from 'react-router'
import GlassCard from '../components/GlassCard'
import SNMPDiscoveryPanel from '../components/SNMPDiscoveryPanel'
import { useSNMPDevices, usePrefetchDeviceDetails, useInvalidateDeviceQueries } from '../hooks/useSnmpQueries'
import { updateDevice, deleteDevice } from '../lib/api'
import { useAuth } from '../components/AuthContext'
import { confirmDanger, toast } from '../lib/swal'

const STATUS_COLORS: Record<string, { dot: string; text: string }> = {
  online: { dot: '#00ff88', text: '#00ff88' },
  offline: { dot: '#ff3366', text: '#ff3366' },
  warning: { dot: '#ffaa00', text: '#ffaa00' },
  unknown: { dot: '#8899bb', text: '#8899bb' },
}

const SNMP_STATUS_COLORS: Record<string, { bg: string; text: string; border: string }> = {
  verified: { bg: 'rgba(0,255,136,0.1)', text: '#00ff88', border: 'rgba(0,255,136,0.3)' },
  unknown: { bg: 'rgba(136,153,187,0.1)', text: '#8899bb', border: 'rgba(136,153,187,0.3)' },
  error: { bg: 'rgba(255,51,102,0.1)', text: '#ff3366', border: 'rgba(255,51,102,0.3)' },
}

const MONITORING_STATUS_COLORS: Record<string, { bg: string; text: string; border: string }> = {
  running: { bg: 'rgba(0,255,136,0.1)', text: '#00ff88', border: 'rgba(0,255,136,0.3)' },
  stopped: { bg: 'rgba(255,51,102,0.1)', text: '#ff3366', border: 'rgba(255,51,102,0.3)' },
  waiting_first_poll: { bg: 'rgba(255,170,0,0.1)', text: '#ffaa00', border: 'rgba(255,170,0,0.3)' },
  not_supported: { bg: 'rgba(136,153,187,0.1)', text: '#8899bb', border: 'rgba(136,153,187,0.3)' },
  error: { bg: 'rgba(255,51,102,0.1)', text: '#ff3366', border: 'rgba(255,51,102,0.3)' },
}

function StatusBadge({ status, type = 'device' }: { status: string; type?: 'device' | 'snmp' | 'monitoring' }) {
  const colors = type === 'device'
    ? STATUS_COLORS[status] || STATUS_COLORS.unknown
    : type === 'snmp'
    ? SNMP_STATUS_COLORS[status] || SNMP_STATUS_COLORS.unknown
    : MONITORING_STATUS_COLORS[status] || MONITORING_STATUS_COLORS.stopped

  return (
    <span
      className="font-mono text-[10px] px-2 py-0.5 rounded uppercase"
      style={{
        background: colors.bg,
        color: colors.text,
        border: `1px solid ${colors.border}`,
      }}
    >
      {status.toUpperCase()}
    </span>
  )
}

function ActionButton({ children, onClick, color, disabled, title }: {
  children: React.ReactNode
  onClick: () => void
  color: string
  disabled?: boolean
  title?: string
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      title={title}
      className="font-mono text-[10px] px-2 py-1 rounded transition-all flex items-center gap-1"
      style={{
        border: `1px solid ${color}44`,
        background: `${color}15`,
        color,
        opacity: disabled ? 0.4 : 1,
        cursor: disabled ? 'not-allowed' : 'pointer',
      }}
    >
      {children}
    </button>
  )
}

// Edit Device Dialog Component
function EditDeviceDialog({ device, onClose, onSave }: { 
  device: any, 
  onClose: () => void, 
  onSave: (data: any) => void 
}) {
  const [formData, setFormData] = useState({
    hostname: device.hostname || '',
    ip_address: device.ip_address || '',
    model: device.model || '',
    serial_number: device.serial_number || '',
    firmware_version: device.firmware_version || '',
    mac_address: device.mac_address || '',
    monitoring_status: device.monitoring_status || false,
  })
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)
    setError(null)
    
    try {
      await onSave(formData)
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update device')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center" 
      style={{ backdropFilter: 'blur(4px)', background: 'rgba(0,0,0,0.7)' }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}>
      
      <div className="w-full max-w-lg mx-4" 
        style={{ background: 'rgba(4,14,33,0.98)', border: '1px solid rgba(0,212,255,0.3)', borderRadius: 12 }}>
        
        {/* Header */}
        <div className="flex items-center justify-between p-5" style={{ borderBottom: '1px solid rgba(0,212,255,0.15)' }}>
          <div>
            <div className="font-display font-bold text-lg tracking-widest neon-cyan">EDIT DEVICE</div>
            <div className="font-mono text-xs mt-0.5" style={{ color: '#8899bb' }}>
              {device.name || device.hostname || device.ip_address}
            </div>
          </div>
          <button onClick={onClose} 
            className="rounded-lg p-2 transition-all hover:bg-red-500/20" 
            style={{ color: '#ff3366', border: '1px solid rgba(255,51,102,0.3)' }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M18 6L6 18M6 6l12 12"/>
            </svg>
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="p-5 space-y-4">
          {error && (
            <div className="font-mono text-xs p-3 rounded" 
              style={{ color: '#ff3366', background: 'rgba(255,51,102,0.1)', border: '1px solid rgba(255,51,102,0.3)' }}>
              {error}
            </div>
          )}

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="font-mono text-xs block mb-1" style={{ color: '#667799' }}>HOSTNAME</label>
              <input
                type="text"
                value={formData.hostname}
                onChange={(e) => setFormData({ ...formData, hostname: e.target.value })}
                className="w-full glass-bright rounded px-3 py-2 font-mono text-xs"
                style={{ border: '1px solid rgba(0,212,255,0.25)', color: '#c8d8ee', background: 'rgba(8,25,55,0.7)' }}
              />
            </div>

            <div>
              <label className="font-mono text-xs block mb-1" style={{ color: '#667799' }}>IP ADDRESS</label>
              <input
                type="text"
                value={formData.ip_address}
                onChange={(e) => setFormData({ ...formData, ip_address: e.target.value })}
                className="w-full glass-bright rounded px-3 py-2 font-mono text-xs"
                style={{ border: '1px solid rgba(0,212,255,0.25)', color: '#c8d8ee', background: 'rgba(8,25,55,0.7)' }}
                required
              />
            </div>

            <div>
              <label className="font-mono text-xs block mb-1" style={{ color: '#667799' }}>MODEL</label>
              <input
                type="text"
                value={formData.model}
                onChange={(e) => setFormData({ ...formData, model: e.target.value })}
                className="w-full glass-bright rounded px-3 py-2 font-mono text-xs"
                style={{ border: '1px solid rgba(0,212,255,0.25)', color: '#c8d8ee', background: 'rgba(8,25,55,0.7)' }}
              />
            </div>

            <div>
              <label className="font-mono text-xs block mb-1" style={{ color: '#667799' }}>SERIAL NUMBER</label>
              <input
                type="text"
                value={formData.serial_number}
                onChange={(e) => setFormData({ ...formData, serial_number: e.target.value })}
                className="w-full glass-bright rounded px-3 py-2 font-mono text-xs"
                style={{ border: '1px solid rgba(0,212,255,0.25)', color: '#c8d8ee', background: 'rgba(8,25,55,0.7)' }}
              />
            </div>

            <div>
              <label className="font-mono text-xs block mb-1" style={{ color: '#667799' }}>FIRMWARE VERSION</label>
              <input
                type="text"
                value={formData.firmware_version}
                onChange={(e) => setFormData({ ...formData, firmware_version: e.target.value })}
                className="w-full glass-bright rounded px-3 py-2 font-mono text-xs"
                style={{ border: '1px solid rgba(0,212,255,0.25)', color: '#c8d8ee', background: 'rgba(8,25,55,0.7)' }}
              />
            </div>

            <div>
              <label className="font-mono text-xs block mb-1" style={{ color: '#667799' }}>MAC ADDRESS</label>
              <input
                type="text"
                value={formData.mac_address}
                onChange={(e) => setFormData({ ...formData, mac_address: e.target.value })}
                placeholder="aa:bb:cc:dd:ee:ff"
                className="w-full glass-bright rounded px-3 py-2 font-mono text-xs"
                style={{ border: '1px solid rgba(0,212,255,0.25)', color: '#c8d8ee', background: 'rgba(8,25,55,0.7)' }}
              />
            </div>
          </div>

          <div className="flex items-center gap-3">
            <input
              type="checkbox"
              id="monitoring_status"
              checked={formData.monitoring_status}
              onChange={(e) => setFormData({ ...formData, monitoring_status: e.target.checked })}
              className="rounded"
              style={{ accentColor: '#00d4ff' }}
            />
            <label htmlFor="monitoring_status" className="font-mono text-xs" style={{ color: '#c8d8ee' }}>
              Enable monitoring for this device
            </label>
          </div>

          <div className="flex items-center justify-end gap-3 pt-3" style={{ borderTop: '1px solid rgba(0,212,255,0.15)' }}>
            <button type="button" onClick={onClose}
              className="glass-bright px-4 py-2 rounded font-mono text-xs hover:bg-red-400/10"
              style={{ border: '1px solid rgba(255,51,102,0.25)', color: '#ff3366' }}>
              CANCEL
            </button>
            <button type="submit" disabled={saving}
              className="glass-bright px-4 py-2 rounded font-mono text-xs hover:bg-cyan-400/10 flex items-center gap-2"
              style={{ border: '1px solid rgba(0,212,255,0.25)', color: '#00d4ff', opacity: saving ? 0.6 : 1 }}>
              {saving && (
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="animate-spin">
                  <path d="M21 12a9 9 0 11-6.219-8.56"/>
                </svg>
              )}
              {saving ? 'SAVING...' : 'SAVE CHANGES'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default function SNMPDevicesPage() {
  const navigate = useNavigate()
  const { hasPermission } = useAuth()
  const canCreate = hasPermission('devices:create')
  const canUpdate = hasPermission('devices:update')
  const canDelete = hasPermission('devices:delete')
  const prefetchDevice = usePrefetchDeviceDetails()
  const invalidateDevice = useInvalidateDeviceQueries()

  // Pagination & filter state
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(50)
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState<string>('')
  const [snmpStatusFilter, setSnmpStatusFilter] = useState<string>('')
  const [monitoringStatusFilter, setMonitoringStatusFilter] = useState<string>('')
  const [deviceTypeFilter, setDeviceTypeFilter] = useState<string>('')
  const [vendorFilter, setVendorFilter] = useState<string>('')
  const [sortBy, setSortBy] = useState('id')
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('asc')
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [editingDevice, setEditingDevice] = useState<any | null>(null)
  const [deleting, setDeleting] = useState<number | null>(null)

  // Fetch devices using React Query
  const { data, isLoading, isFetching, error: queryError, refetch } = useSNMPDevices({
    page,
    page_size: pageSize,
    search: search || undefined,
    status: statusFilter || undefined,
    snmp_status: snmpStatusFilter || undefined,
    monitoring_status: monitoringStatusFilter || undefined,
    device_type: deviceTypeFilter || undefined,
    vendor: vendorFilter || undefined,
    sort_by: sortBy,
    sort_order: sortOrder,
  })

  const devices = data?.items || []
  const total = data?.total || 0
  const totalPages = data?.total_pages || 0

  // Handle sort
  const handleSort = (column: string) => {
    if (sortBy === column) {
      setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc')
    } else {
      setSortBy(column)
      setSortOrder('asc')
    }
  }

  // Handle page change
  const handlePageChange = (newPage: number) => {
    if (newPage >= 1 && newPage <= totalPages) {
      setPage(newPage)
    }
  }

  // Handle search submit
  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault()
    setPage(1) // Reset to first page on search
  }

  // Clear filters
  const clearFilters = () => {
    setSearch('')
    setStatusFilter('')
    setSnmpStatusFilter('')
    setMonitoringStatusFilter('')
    setDeviceTypeFilter('')
    setVendorFilter('')
    setPage(1)
  }

  // Row click - navigate to device details
  const handleRowClick = (device: any) => {
    if (selectedId === device.id) {
      navigate(`/snmp/devices/${device.id}`)
    } else {
      setSelectedId(device.id)
      prefetchDevice(device.id)
    }
  }

  // Quick actions
  const handleTestSNMP = async (deviceId: number, e: React.MouseEvent) => {
    e.stopPropagation()
    try {
      // TODO: Call test SNMP endpoint
      setError('SNMP test triggered')
      setTimeout(() => setError(null), 3000)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'SNMP test failed')
    }
  }

  const handleConfigureMonitoring = (deviceId: number, e: React.MouseEvent) => {
    e.stopPropagation()
    navigate(`/snmp/devices/${deviceId}/monitoring`)
  }

  const handleEditDevice = (device: any, e: React.MouseEvent) => {
    e.stopPropagation()
    setEditingDevice(device)
  }

  const handleSaveDevice = async (formData: any) => {
    if (!editingDevice) return
    
    try {
      await updateDevice(editingDevice.id, formData)
      refetch() // Refresh the device list
      setError(null)
    } catch (err) {
      throw err // Let EditDeviceDialog handle the error
    }
  }

  const handleDeleteDevice = async (deviceId: number, e: React.MouseEvent) => {
    e.stopPropagation()
    
    const device = devices.find(d => d.id === deviceId)
    const deviceName = device?.name || device?.hostname || device?.ip_address || `device-${deviceId}`
    
    if (!canDelete) return
    const ok = await confirmDanger({
      title: `Delete device "${deviceName}"?`,
      text: 'This will remove the device from monitoring, delete collected metrics, and stop monitoring jobs. This action cannot be undone.',
      confirmText: 'Delete',
    })
    if (!ok) return

    setDeleting(deviceId)
    try {
      await deleteDevice(deviceId)
      refetch() // Refresh the device list
      setError(null)
      toast.success(`Device "${deviceName}" deleted`)
      
      // Show success message
      setError(`Device "${deviceName}" deleted successfully`)
      setTimeout(() => setError(null), 5000)
      
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Delete failed')
    } finally {
      setDeleting(null)
    }
  }

  const handleRefresh = () => {
    refetch()
  }

  const hasFilters = search || statusFilter || snmpStatusFilter || monitoringStatusFilter || deviceTypeFilter || vendorFilter

  return (
    <div className="p-4 md:p-6 space-y-4 md:space-y-5">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <div>
          <h1 className="font-display font-bold text-xl sm:text-2xl tracking-widest neon-cyan">SNMP DEVICES</h1>
          <p className="font-mono text-xs mt-0.5" style={{ color: '#8899bb' }}>
            {total} devices · Page {page} of {totalPages || 1} · {pageSize} per page
          </p>
        </div>
        <div className="flex flex-wrap gap-2 items-center">
          <button onClick={handleRefresh} disabled={isFetching}
            className="glass-bright px-3 py-1.5 rounded font-mono text-xs hover:bg-cyan-400/10 flex items-center gap-1.5"
            style={{ border: '1px solid rgba(0,212,255,0.25)', color: '#00d4ff', opacity: isFetching ? 0.6 : 1 }}>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M23 4v6h-6M1 20v-6h6"/><path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/>
            </svg>
            REFRESH
          </button>
          {canCreate && (
            <button onClick={() => navigate('/snmp/devices/add')}
              className="glass-bright px-3 py-1.5 rounded font-mono text-xs hover:bg-cyan-400/10 flex items-center gap-1.5"
              style={{ border: '1px solid rgba(0,212,255,0.25)', color: '#00d4ff' }}>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
              </svg>
              ADD DEVICE
            </button>
          )}
        </div>
      </div>

      {error && (
        <div className={`font-mono text-xs p-3 rounded ${error.includes('successfully') ? 'success-message' : 'error-message'}`} 
          style={{ 
            color: error.includes('successfully') ? '#00ff88' : '#ff3366', 
            background: error.includes('successfully') ? 'rgba(0,255,136,0.1)' : 'rgba(255,51,102,0.1)', 
            border: error.includes('successfully') ? '1px solid rgba(0,255,136,0.3)' : '1px solid rgba(255,51,102,0.3)' 
          }}>
          {error}
        </div>
      )}

      {/* Search & Filters */}
      <GlassCard className="p-4">
        <form onSubmit={handleSearch} className="space-y-3">
          <div className="flex flex-wrap gap-3 items-end">
            <div className="flex-1 min-w-[200px]">
              <label className="font-mono text-[10px] block mb-1" style={{ color: '#667799' }}>SEARCH</label>
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search IP, hostname, MAC..."
                className="w-full glass-bright rounded px-3 py-2 font-mono text-xs"
                style={{ border: '1px solid rgba(0,212,255,0.25)', color: '#c8d8ee', background: 'rgba(8,25,55,0.7)' }}
              />
            </div>

            <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}
              className="glass-bright rounded px-3 py-2 font-mono text-xs min-w-[140px]"
              style={{ border: '1px solid rgba(0,212,255,0.25)', color: '#c8d8ee', background: 'rgba(8,25,55,0.7)' }}>
              <option value="">ALL STATUS</option>
              <option value="online">ONLINE</option>
              <option value="offline">OFFLINE</option>
              <option value="warning">WARNING</option>
              <option value="unknown">UNKNOWN</option>
            </select>

            <select value={snmpStatusFilter} onChange={(e) => setSnmpStatusFilter(e.target.value)}
              className="glass-bright rounded px-3 py-2 font-mono text-xs min-w-[140px]"
              style={{ border: '1px solid rgba(0,212,255,0.25)', color: '#c8d8ee', background: 'rgba(8,25,55,0.7)' }}>
              <option value="">ALL SNMP</option>
              <option value="verified">VERIFIED</option>
              <option value="unknown">UNKNOWN</option>
              <option value="error">ERROR</option>
            </select>

            <select value={monitoringStatusFilter} onChange={(e) => setMonitoringStatusFilter(e.target.value)}
              className="glass-bright rounded px-3 py-2 font-mono text-xs min-w-[160px]"
              style={{ border: '1px solid rgba(0,212,255,0.25)', color: '#c8d8ee', background: 'rgba(8,25,55,0.7)' }}>
              <option value="">ALL MONITORING</option>
              <option value="running">RUNNING</option>
              <option value="stopped">STOPPED</option>
              <option value="waiting_first_poll">WAITING</option>
              <option value="not_supported">NOT SUPPORTED</option>
            </select>
          </div>

          <div className="flex flex-wrap gap-3 items-end">
            <select value={deviceTypeFilter} onChange={(e) => setDeviceTypeFilter(e.target.value)}
              className="glass-bright rounded px-3 py-2 font-mono text-xs min-w-[140px]"
              style={{ border: '1px solid rgba(0,212,255,0.25)', color: '#c8d8ee', background: 'rgba(8,25,55,0.7)' }}>
              <option value="">ALL TYPES</option>
              <option value="router">ROUTER</option>
              <option value="switch">SWITCH</option>
              <option value="firewall">FIREWALL</option>
              <option value="server">SERVER</option>
              <option value="access_point">ACCESS POINT</option>
            </select>

            <input
              type="text"
              value={vendorFilter}
              onChange={(e) => setVendorFilter(e.target.value)}
              placeholder="Vendor filter..."
              className="glass-bright rounded px-3 py-2 font-mono text-xs min-w-[140px]"
              style={{ border: '1px solid rgba(0,212,255,0.25)', color: '#c8d8ee', background: 'rgba(8,25,55,0.7)' }}
            />

            <div className="flex items-center gap-2">
              <button type="submit"
                className="glass-bright px-4 py-2 rounded font-mono text-xs hover:bg-cyan-400/10 flex items-center gap-1.5"
                style={{ border: '1px solid rgba(0,212,255,0.25)', color: '#00d4ff' }}>
                APPLY
              </button>
              {hasFilters && (
                <button type="button" onClick={clearFilters}
                  className="glass-bright px-3 py-2 rounded font-mono text-xs hover:bg-red-400/10"
                  style={{ border: '1px solid rgba(255,51,102,0.25)', color: '#ff3366' }}>
                  CLEAR
                </button>
              )}
            </div>
          </div>
        </form>
      </GlassCard>

      {/* Discovery Panel */}
      <SNMPDiscoveryPanel onCompleted={() => refetch()} />

      {/* Device Table */}
      <GlassCard className="overflow-hidden">
        <div className="p-4" style={{ borderBottom: '1px solid rgba(0,212,255,0.1)' }}>
          <div className="font-display font-bold text-base tracking-wider neon-cyan">DEVICE INVENTORY</div>
          <div className="font-mono text-xs mt-0.5" style={{ color: '#8899bb' }}>
            DB-backed data · Click row to select · Double-click to open details
          </div>
        </div>

        {isLoading ? (
          <div className="flex items-center justify-center p-12">
            <div className="font-mono text-sm" style={{ color: '#00d4ff' }}>Loading devices...</div>
          </div>
        ) : devices.length === 0 ? (
          <div className="font-mono text-xs p-6 text-center" style={{ color: '#8899bb' }}>
            No devices found. Run SNMP Discovery above or add a device manually.
          </div>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full" style={{ minWidth: 1000 }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid rgba(0,212,255,0.08)' }}>
                    {[
                      { key: 'name', label: 'NAME' },
                      { key: 'ip_address', label: 'IP ADDRESS' },
                      { key: 'hostname', label: 'HOSTNAME' },
                      { key: 'model', label: 'MODEL' },
                      { key: 'snmp_version', label: 'SNMP' },
                      { key: 'snmp_status', label: 'SNMP STATUS' },
                      { key: 'status', label: 'STATUS' },
                      { key: 'monitoring_enabled', label: 'MONITORING' },
                      { key: 'modules_monitored', label: 'MODULES' },
                      { key: 'last_seen', label: 'LAST SEEN' },
                      { key: 'last_poll_at', label: 'LAST POLL' },
                    ].map(col => (
                      <th
                        key={col.key}
                        onClick={() => handleSort(col.key)}
                        className="text-left px-4 py-2.5 font-mono text-xs cursor-pointer sticky top-0 select-none"
                        style={{ color: '#8899bb', background: 'rgba(8,25,55,0.95)', userSelect: 'none' }}
                      >
                        <div className="flex items-center gap-1">
                          {col.label}
                          {sortBy === col.key && (
                            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="#00d4ff" strokeWidth="2">
                              {sortOrder === 'asc' ? <path d="M18 15l-6-6-6 6" /> : <path d="M6 9l6 6 6-6" />}
                            </svg>
                          )}
                        </div>
                      </th>
                    ))}
                    <th className="text-left px-4 py-2.5 font-mono text-xs sticky top-0" style={{ color: '#8899bb', background: 'rgba(8,25,55,0.95)' }}>ACTIONS</th>
                  </tr>
                </thead>
                <tbody>
                  {devices.map((device, index) => (
                    <tr
                      key={device.id}
                      onClick={() => handleRowClick(device)}
                      onDoubleClick={() => navigate(`/snmp/devices/${device.id}`)}
                      style={{
                        borderBottom: '1px solid rgba(0,212,255,0.04)',
                        background: selectedId === device.id ? 'rgba(0,212,255,0.05)' : undefined,
                        cursor: 'pointer',
                      }}
                    >
                      <td className="px-4 py-2 font-mono text-xs font-semibold" style={{ color: '#c8d8ee' }}>
                        {device.name || device.hostname || `device-${device.ip_address}`}
                      </td>
                      <td className="px-4 py-2 font-mono text-xs neon-cyan">{device.ip_address}</td>
                      <td className="px-4 py-2 font-mono text-xs" style={{ color: '#8899bb' }}>{device.hostname || '—'}</td>
                      <td className="px-4 py-2 font-mono text-xs truncate max-w-[150px]" style={{ color: '#8899bb' }}>{device.model || '—'}</td>
                      <td className="px-4 py-2 font-mono text-xs" style={{ color: '#7c3aed' }}>{device.snmp_version || '—'}</td>
                      <td className="px-4 py-2"><StatusBadge status={device.snmp_status} type="snmp" /></td>
                      <td className="px-4 py-2"><StatusBadge status={device.status} type="device" /></td>
                      <td className="px-4 py-2">
                        {device.monitoring_enabled ? (
                          <StatusBadge status="running" type="monitoring" />
                        ) : (
                          <StatusBadge status="stopped" type="monitoring" />
                        )}
                      </td>
                      <td className="px-4 py-2 font-mono text-xs" style={{ color: '#00d4ff' }}>{device.modules_monitored}</td>
                      <td className="px-4 py-2 font-mono text-[10px]" style={{ color: '#8899bb' }}>
                        {device.last_seen ? new Date(device.last_seen).toLocaleString() : '—'}
                      </td>
                      <td className="px-4 py-2 font-mono text-[10px]" style={{ color: '#8899bb' }}>
                        {device.last_poll_at ? new Date(device.last_poll_at).toLocaleString() : '—'}
                      </td>
                      <td className="px-4 py-2">
                        <div className="flex items-center gap-1">
                          <ActionButton
                            onClick={(e) => handleTestSNMP(device.id, e)}
                            color="#00d4ff"
                            title="Test SNMP"
                          >
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
                            </svg>
                          </ActionButton>
                          <ActionButton
                            onClick={(e) => handleConfigureMonitoring(device.id, e)}
                            color="#7c3aed"
                            title="Configure Monitoring"
                          >
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                              <circle cx="12" cy="12" r="3" />
                              <path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-2 2 2 2 0 01-2-2v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83 0 2 2 0 010-2.83l.06-.06a1.65 1.65 0 00.33-1.82 1.65 1.65 0 00-1.51-1H3a2 2 0 01-2-2 2 2 0 012-2h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 010-2.83 2 2 0 012.83 0l.06.06a1.65 1.65 0 001.82.33H9a1.65 1.65 0 001-1.51V3a2 2 0 012-2 2 2 0 012 2v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 0 2 2 0 010 2.83l-.06.06a1.65 1.65 0 00-.33 1.82V9a1.65 1.65 0 001.51 1H21a2 2 0 012 2 2 2 0 01-2 2h-.09a1.65 1.65 0 00-1.51 1z" />
                            </svg>
                          </ActionButton>
                          {(canUpdate || canDelete) && (
                            <>
                              {canUpdate && <ActionButton
                                onClick={(e) => handleEditDevice(device, e)}
                                color="#ffaa00"
                                title="Edit Device"
                              >
                                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                  <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                                  <path d="m18.5 2.5 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                                </svg>
                              </ActionButton>}
                              {canDelete && <ActionButton
                                onClick={(e) => handleDeleteDevice(device.id, e)}
                                color="#ff3366"
                                title="Delete Device"
                                disabled={deleting === device.id}
                              >
                                {deleting === device.id ? (
                                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="animate-spin">
                                    <path d="M21 12a9 9 0 11-6.219-8.56"/>
                                  </svg>
                                ) : (
                                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                    <polyline points="3 6 5 6 21 6" />
                                    <path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" />
                                  </svg>
                                )}
                              </ActionButton>}
                            </>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            <div className="p-4 flex flex-col sm:flex-row items-center justify-between gap-3" style={{ borderTop: '1px solid rgba(0,212,255,0.1)' }}>
              <div className="font-mono text-xs" style={{ color: '#8899bb' }}>
                Showing {((page - 1) * pageSize) + 1} to {Math.min(page * pageSize, total)} of {total} devices
              </div>
              <div className="flex items-center gap-2">
                <select value={pageSize} onChange={(e) => { setPageSize(Number(e.target.value)); setPage(1); }}
                  className="glass-bright rounded px-2 py-1 font-mono text-xs"
                  style={{ border: '1px solid rgba(0,212,255,0.25)', color: '#c8d8ee', background: 'rgba(8,25,55,0.7)' }}>
                  <option value={25}>25</option>
                  <option value={50}>50</option>
                  <option value={100}>100</option>
                  <option value={200}>200</option>
                </select>
                <button onClick={() => handlePageChange(page - 1)} disabled={page === 1 || isFetching}
                  className="glass-bright px-3 py-1.5 rounded font-mono text-xs"
                  style={{ border: '1px solid rgba(0,212,255,0.25)', color: '#00d4ff', opacity: page === 1 || isFetching ? 0.4 : 1 }}>
                  PREV
                </button>
                <span className="font-mono text-xs px-2" style={{ color: '#c8d8ee' }}>
                  Page {page} / {totalPages}
                </span>
                <button onClick={() => handlePageChange(page + 1)} disabled={page === totalPages || isFetching}
                  className="glass-bright px-3 py-1.5 rounded font-mono text-xs"
                  style={{ border: '1px solid rgba(0,212,255,0.25)', color: '#00d4ff', opacity: page === totalPages || isFetching ? 0.4 : 1 }}>
                  NEXT
                </button>
              </div>
            </div>
          </>
        )}
      </GlassCard>

      {/* Edit Device Dialog */}
      {editingDevice && (
        <EditDeviceDialog
          device={editingDevice}
          onClose={() => setEditingDevice(null)}
          onSave={handleSaveDevice}
        />
      )}
    </div>
  )
}
