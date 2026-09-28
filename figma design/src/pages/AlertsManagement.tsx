import { useCallback, useEffect, useState } from 'react'
import { useLocation } from 'react-router'
import GlassCard from '../components/GlassCard'
import { PermissionGuard } from '../components/PermissionGuard'
import TablePagination from '../components/TablePagination'
import { useDeferredSearch } from '../hooks/useDeferredSearch'
import { useTablePagination } from '../hooks/useTablePagination'
import { toast, confirmDanger } from '../lib/swal'
import {
  listAlerts, createAlert, updateAlert, deleteAlert, acknowledgeAlert, resolveAlert, clearAllAlerts,
  listDeviceOptions,
  type AlertRecord,
  type DeviceOptionRecord,
} from '../lib/api'

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="font-mono text-xs block mb-1" style={{ color: 'var(--t-muted)' }}>{label}</label>
      {children}
    </div>
  )
}

const inputStyle: React.CSSProperties = {
  background: 'var(--t-border-light, rgba(255,255,255,0.04))',
  border: '1px solid var(--t-border-alpha)',
  color: 'var(--t-text)',
  outline: 'none',
}

const severityColors: Record<string, string> = {
  critical: '#ff3366',
  high: '#ff6b35',
  warning: '#ffa500',
  info: '#00d4ff',
}

const statusColors: Record<string, string> = {
  open: '#ff6b35',
  acknowledged: '#ffa500',
  resolved: '#4ade80',
}

export default function AlertsManagement() {
  const location = useLocation()
  const [alerts, setAlerts] = useState<AlertRecord[]>([])
  const [devices, setDevices] = useState<DeviceOptionRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [showModal, setShowModal] = useState(false)
  const [detailsAlert, setDetailsAlert] = useState<AlertRecord | null>(null)
  const [editing, setEditing] = useState<AlertRecord | null>(null)
  const [saving, setSaving] = useState(false)
  const { search, setSearch, normalizedSearch } = useDeferredSearch()
  const [statusFilter, setStatusFilter] = useState<string>('all')

  const [fDeviceId, setFDeviceId] = useState<number | ''>('')
  const [fSeverity, setFSeverity] = useState('warning')
  const [fTitle, setFTitle] = useState('')
  const [fDescription, setFDescription] = useState('')
  const [fStatus, setFStatus] = useState('open')

  const load = useCallback(async () => {
    try {
      const filter = statusFilter === 'all' ? undefined : statusFilter
      const [alertsData, devicesData] = await Promise.all([
        listAlerts(filter),
        listDeviceOptions()
      ])
      setAlerts(alertsData)
      setDevices(devicesData)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to load alerts')
    }
    setLoading(false)
  }, [statusFilter])

  useEffect(() => { void load() }, [load])

  useEffect(() => {
    const id = Number(new URLSearchParams(location.search).get('alert_id'))
    if (!id || !alerts.length || detailsAlert) return
    const alert = alerts.find(item => item.id === id)
    if (alert) {
      const device = alert.device_id != null ? deviceMap.get(alert.device_id) : undefined
      setDetailsAlert(device ? { ...alert, hostname: alert.hostname ?? device.hostname, ip_address: alert.ip_address ?? device.ip_address } : alert)
    }
  }, [alerts, location.search])

  function openCreate() {
    setEditing(null)
    setFDeviceId('')
    setFSeverity('warning')
    setFTitle('')
    setFDescription('')
    setFStatus('open')
    setShowModal(true)
  }

  function openEdit(alert: AlertRecord) {
    setEditing(alert)
    setFDeviceId(alert.device_id ?? '')
    setFSeverity(alert.severity)
    setFTitle(alert.title)
    setFDescription(alert.description ?? '')
    setFStatus(alert.status)
    setShowModal(true)
  }

  async function handleSubmit() {
    if (!fTitle.trim()) { toast.warning('Title is required'); return }
    setSaving(true)
    try {
      const data = {
        device_id: fDeviceId === '' ? null : fDeviceId,
        severity: fSeverity,
        title: fTitle.trim(),
        description: fDescription.trim() || null,
        status: fStatus,
      }
      if (editing) {
        await updateAlert(editing.id, data)
        toast.success(`Alert "${fTitle}" updated`)
      } else {
        await createAlert(data)
        toast.success(`Alert "${fTitle}" created`)
      }
      setShowModal(false)
      await load()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Save failed')
    }
    setSaving(false)
  }

  async function handleAcknowledge(alert: AlertRecord) {
    try {
      await acknowledgeAlert(alert.id)
      toast.success(`Alert acknowledged`)
      await load()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Acknowledge failed')
    }
  }

  async function handleResolve(alert: AlertRecord) {
    try {
      await resolveAlert(alert.id)
      toast.success(`Alert resolved`)
      await load()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Resolve failed')
    }
  }

  async function handleDelete(alert: AlertRecord) {
    const ok = await confirmDanger({
      title: `Delete alert "${alert.title}"?`,
      text: 'This action cannot be undone.',
      confirmText: 'Delete Alert',
    })
    if (!ok) return
    try {
      await deleteAlert(alert.id)
      toast.success(`Alert deleted`)
      await load()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Delete failed')
    }
  }

  async function handleClearAll() {
    const ok = await confirmDanger({
      title: 'Clear all alerts?',
      text: 'This will remove all alerts from the system.',
      confirmText: 'Clear All Alerts',
    })
    if (!ok) return
    try {
      const result = await clearAllAlerts()
      toast.success(`${result.cleared} alert(s) cleared`)
      await load()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Clear all failed')
    }
  }

  const filtered = alerts.filter(a =>
    !normalizedSearch ||
    a.title.toLowerCase().includes(normalizedSearch) ||
    (a.description ?? '').toLowerCase().includes(normalizedSearch) ||
    a.severity.toLowerCase().includes(normalizedSearch)
  )
  const deviceMap = new Map(devices.map(device => [device.id, device]))
  const detailDevice = detailsAlert?.device_id != null ? deviceMap.get(detailsAlert.device_id) : undefined
  const pagination = useTablePagination(filtered)

  if (loading) {
    return (
      <div className="p-6 flex items-center justify-center min-h-[50vh]">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 rounded-full border-2 animate-spin" style={{ borderColor: 'var(--t-accent)', borderTopColor: 'transparent' }} />
          <span className="font-mono text-xs" style={{ color: 'var(--t-muted)' }}>LOADING…</span>
        </div>
      </div>
    )
  }

  return (
    <div className="p-4 md:p-6 space-y-5">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="font-display font-bold text-xl md:text-2xl" style={{ color: 'var(--t-text)' }}>Alert Management</h1>
          <p className="font-mono text-xs mt-1" style={{ color: 'var(--t-muted)' }}>{alerts.length} alert{alerts.length !== 1 ? 's' : ''}</p>
        </div>
        <div className="flex gap-2 flex-wrap">
          <select
            value={statusFilter}
            onChange={e => { setStatusFilter(e.target.value); pagination.setPage(1) }}
            className="rounded-lg px-3 py-2 font-mono text-xs"
            style={inputStyle}>
            <option value="all">All Status</option>
            <option value="open">Open</option>
            <option value="acknowledged">Acknowledged</option>
            <option value="resolved">Resolved</option>
          </select>
          <input
            value={search}
            onChange={e => { setSearch(e.target.value); pagination.setPage(1) }}
            placeholder="Search…"
            className="rounded-lg px-3 py-2 font-mono text-xs"
            style={{ ...inputStyle, minWidth: 160 }}
            onFocus={e => { e.currentTarget.style.borderColor = 'var(--t-accent)' }}
            onBlur={e => { e.currentTarget.style.borderColor = 'var(--t-border-alpha)' }}
          />
          <PermissionGuard permission="alerts:delete">
            <button
              onClick={handleClearAll}
              disabled={alerts.length === 0}
              className="rounded-lg px-4 py-2 font-mono text-xs hover:opacity-90 transition-all disabled:opacity-50"
              style={{ background: 'rgba(255,51,102,0.2)', color: '#ff3366', border: '1px solid rgba(255,51,102,0.3)' }}>
              Clear All
            </button>
          </PermissionGuard>
          <PermissionGuard permission="alerts:create">
            <button
              onClick={openCreate}
              className="rounded-lg px-4 py-2 font-display font-semibold text-sm flex items-center gap-2 hover:opacity-90 transition-all"
              style={{ background: 'var(--t-accent)', color: '#fff', border: '1px solid var(--t-accent-border)' }}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><path d="M12 5v14M5 12h14"/></svg>
              New
            </button>
          </PermissionGuard>
        </div>
      </div>

      <GlassCard className="overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left" style={{ minWidth: 800 }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--t-border-light)' }}>
                {['Severity', 'Title', 'Device', 'Status', 'Created', 'Actions'].map(h => (
                  <th key={h} className="px-4 py-3 font-mono text-xs uppercase tracking-wider" style={{ color: 'var(--t-muted)' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {pagination.paginatedItems.map(alert => {
                const device = alert.device_id != null ? deviceMap.get(alert.device_id) : undefined
                return (
                  <tr key={alert.id} style={{ borderBottom: '1px solid var(--t-border-alpha)' }}
                    onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = 'rgba(0,212,255,0.03)' }}
                    onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = '' }}>
                    <td className="px-4 py-3">
                      <span className="px-2 py-1 rounded text-xs font-mono font-semibold"
                        style={{ background: `${severityColors[alert.severity]}20`, color: severityColors[alert.severity] }}>
                        {alert.severity.toUpperCase()}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <div className="font-display font-medium text-sm" style={{ color: 'var(--t-text)' }}>{alert.title}</div>
                      {alert.description && (
                        <div className="font-mono text-xs mt-1" style={{ color: 'var(--t-muted)' }}>{alert.description}</div>
                      )}
                    </td>
                    <td className="px-4 py-3 font-mono text-xs" style={{ color: 'var(--t-muted)' }}>
                      {device ? `${device.hostname} (${device.ip_address})` : '—'}
                    </td>
                    <td className="px-4 py-3">
                      <span className="px-2 py-1 rounded text-xs font-mono"
                        style={{ background: `${statusColors[alert.status]}20`, color: statusColors[alert.status] }}>
                        {alert.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 font-mono text-xs" style={{ color: 'var(--t-muted)' }}>
                      {new Date(alert.created_at).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', hour12: true })}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex gap-1">
                        <button onClick={() => { const device = alert.device_id != null ? deviceMap.get(alert.device_id) : undefined; setDetailsAlert(device ? { ...alert, hostname: alert.hostname ?? device.hostname, ip_address: alert.ip_address ?? device.ip_address } : alert) }} title="Show alert details"
                          className="p-1.5 rounded transition-colors text-xs font-mono px-2"
                          style={{ background: 'rgba(0,212,255,0.1)', color: 'var(--t-accent)', border: '1px solid rgba(0,212,255,0.2)' }}>
                          SHOW
                        </button>
                        {alert.status === 'open' && (
                          <PermissionGuard permission="alerts:update">
                            <button onClick={() => handleAcknowledge(alert)} title="Acknowledge"
                              className="p-1.5 rounded transition-colors text-xs font-mono px-2"
                              style={{ background: 'rgba(255,165,0,0.1)', color: '#ffa500' }}>
                              ACK
                            </button>
                          </PermissionGuard>
                        )}
                        {alert.status !== 'resolved' && (
                          <PermissionGuard permission="alerts:update">
                            <button onClick={() => handleResolve(alert)} title="Resolve"
                              className="p-1.5 rounded transition-colors text-xs font-mono px-2"
                              style={{ background: 'rgba(74,222,128,0.1)', color: '#4ade80' }}>
                              RESOLVE
                            </button>
                          </PermissionGuard>
                        )}
                        <PermissionGuard permission="alerts:update">
                          <button onClick={() => openEdit(alert)} title="Edit"
                            className="p-1.5 rounded transition-colors" style={{ color: 'var(--t-muted)' }}
                            onMouseEnter={e => { e.currentTarget.style.color = 'var(--t-accent)' }}
                            onMouseLeave={e => { e.currentTarget.style.color = 'var(--t-muted)' }}>
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                              <path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/>
                            </svg>
                          </button>
                        </PermissionGuard>
                        <PermissionGuard permission="alerts:delete">
                          <button onClick={() => handleDelete(alert)} title="Delete"
                            className="p-1.5 rounded transition-colors" style={{ color: 'var(--t-muted)' }}
                            onMouseEnter={e => { e.currentTarget.style.color = '#ff3366' }}
                            onMouseLeave={e => { e.currentTarget.style.color = 'var(--t-muted)' }}>
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                              <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/>
                            </svg>
                          </button>
                        </PermissionGuard>
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
        {filtered.length === 0 && (
          <div className="py-12 text-center font-mono text-xs" style={{ color: 'var(--t-muted)' }}>
            {search ? 'No alerts match your search.' : 'No alerts yet.'}
          </div>
        )}
        {filtered.length > 0 && (
          <TablePagination
            page={pagination.page}
            pageCount={pagination.pageCount}
            pageSize={pagination.pageSize}
            startItem={pagination.startItem}
            endItem={pagination.endItem}
            totalItems={pagination.totalItems}
            onPageChange={pagination.setPage}
            onPageSizeChange={(pageSize) => { pagination.setPageSize(pageSize); pagination.setPage(1) }}
          />
        )}
      </GlassCard>

      {showModal && (
        <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4" onClick={() => setShowModal(false)}>
          <div className="glass rounded-xl p-6 w-full max-w-lg shadow-2xl" style={{ border: '1px solid rgba(0,212,255,0.25)' }}
            onClick={e => e.stopPropagation()}>
            <h3 className="font-display font-bold text-lg mb-4" style={{ color: 'var(--t-accent)' }}>
              {editing ? '✏ Edit Alert' : '+ New Alert'}
            </h3>
            <div className="space-y-4">
              <Field label="DEVICE (OPTIONAL)">
                <select
                  value={fDeviceId}
                  onChange={e => setFDeviceId(e.target.value === '' ? '' : Number(e.target.value))}
                  className="w-full rounded-lg px-3 py-2.5 font-mono text-sm"
                  style={inputStyle}>
                  <option value="">-- None --</option>
                  {devices.map(d => (
                    <option key={d.id} value={d.id}>{d.hostname} ({d.ip_address})</option>
                  ))}
                </select>
              </Field>
              <Field label="SEVERITY *">
                <select
                  value={fSeverity}
                  onChange={e => setFSeverity(e.target.value)}
                  className="w-full rounded-lg px-3 py-2.5 font-mono text-sm"
                  style={inputStyle}>
                  <option value="info">Info</option>
                  <option value="warning">Warning</option>
                  <option value="high">High</option>
                  <option value="critical">Critical</option>
                </select>
              </Field>
              <Field label="TITLE *">
                <input
                  value={fTitle}
                  onChange={e => setFTitle(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter') void handleSubmit() }}
                  autoFocus
                  placeholder="e.g. High CPU Usage"
                  className="w-full rounded-lg px-3 py-2.5 font-mono text-sm"
                  style={inputStyle}
                  onFocus={e => { e.currentTarget.style.borderColor = 'var(--t-accent)' }}
                  onBlur={e => { e.currentTarget.style.borderColor = 'var(--t-border-alpha)' }}
                />
              </Field>
              <Field label="DESCRIPTION">
                <textarea
                  value={fDescription}
                  onChange={e => setFDescription(e.target.value)}
                  rows={3}
                  placeholder="Optional description…"
                  className="w-full rounded-lg px-3 py-2.5 font-mono text-sm resize-none"
                  style={inputStyle}
                  onFocus={e => { e.currentTarget.style.borderColor = 'var(--t-accent)' }}
                  onBlur={e => { e.currentTarget.style.borderColor = 'var(--t-border-alpha)' }}
                />
              </Field>
              <Field label="STATUS">
                <select
                  value={fStatus}
                  onChange={e => setFStatus(e.target.value)}
                  className="w-full rounded-lg px-3 py-2.5 font-mono text-sm"
                  style={inputStyle}>
                  <option value="open">Open</option>
                  <option value="acknowledged">Acknowledged</option>
                  <option value="resolved">Resolved</option>
                </select>
              </Field>
            </div>
            <div className="flex gap-2 justify-end mt-6">
              <button
                onClick={() => setShowModal(false)}
                className="rounded-lg px-4 py-2 font-mono text-xs hover:opacity-80 transition-all"
                style={{ background: 'var(--t-border-light, rgba(255,255,255,0.05))', border: '1px solid var(--t-border-alpha)', color: 'var(--t-muted)' }}>
                Cancel
              </button>
              <button
                onClick={() => void handleSubmit()}
                disabled={saving || !fTitle.trim()}
                className="rounded-lg px-5 py-2 font-mono text-xs font-semibold transition-all disabled:opacity-50 flex items-center gap-2"
                style={{ background: 'var(--t-accent)', color: '#fff', border: '1px solid var(--t-accent-border)' }}>
                {saving ? <><span className="w-3 h-3 rounded-full border animate-spin inline-block" style={{ borderColor:'#fff',borderTopColor:'transparent' }}/> Saving…</> : editing ? '✓ Update' : '+ Create'}
              </button>
            </div>
          </div>
        </div>
      )}

      {detailsAlert && (
        <div className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-4" onClick={() => setDetailsAlert(null)}>
          <div className="glass rounded-xl p-6 w-full max-w-2xl max-h-[90vh] overflow-y-auto shadow-2xl" style={{ border: '1px solid rgba(0,212,255,0.3)' }} onClick={e => e.stopPropagation()}>
            <div className="flex items-start justify-between gap-4 mb-5">
              <div><div className="font-mono text-[10px] uppercase tracking-widest" style={{ color: 'var(--t-muted)' }}>Alert #{detailsAlert.id}</div><h3 className="font-display font-bold text-xl mt-1" style={{ color: 'var(--t-text)' }}>{detailsAlert.title}</h3></div>
              <button onClick={() => setDetailsAlert(null)} className="font-mono text-xs" style={{ color: 'var(--t-muted)' }}>CLOSE ✕</button>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-5">
              {[['Severity', detailsAlert.severity.toUpperCase(), severityColors[detailsAlert.severity] ?? 'var(--t-accent)'], ['Status', detailsAlert.status.toUpperCase(), statusColors[detailsAlert.status] ?? 'var(--t-muted)'], ['Device', detailsAlert.hostname ?? detailDevice?.hostname ?? (detailsAlert.device_id ? `Device #${detailsAlert.device_id}` : 'Global'), 'var(--t-text)'], ['Device ID', detailsAlert.device_id ?? 'N/A', 'var(--t-text)'], ['Resolved', detailsAlert.resolved_at ? 'YES' : 'NO', detailsAlert.resolved_at ? '#4ade80' : 'var(--t-muted)']].map(([label, value, color]) => <div key={label} className="rounded-lg p-3" style={{ background: 'var(--t-border-light)', border: '1px solid var(--t-border-alpha)' }}><div className="font-mono text-[9px] uppercase" style={{ color: 'var(--t-muted)' }}>{label}</div><div className="font-display text-sm mt-1" style={{ color }}>{value}</div></div>)}
            </div>
            <div className="grid md:grid-cols-2 gap-3 mb-5 font-mono text-xs">
              <div><span style={{ color: 'var(--t-muted)' }}>IP address: </span><span style={{ color: 'var(--t-text)' }}>{detailsAlert.ip_address ?? detailsAlert.ip ?? detailDevice?.ip_address ?? 'N/A'}</span></div>
              <div><span style={{ color: 'var(--t-muted)' }}>MAC address: </span><span style={{ color: 'var(--t-text)' }}>{detailDevice?.mac_address ?? 'N/A'}</span></div>
              <div><span style={{ color: 'var(--t-muted)' }}>Created (IST): </span><span style={{ color: 'var(--t-text)' }}>{new Date(detailsAlert.created_at).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', hour12: true })}</span></div>
              <div><span style={{ color: 'var(--t-muted)' }}>Resolved (IST): </span><span style={{ color: 'var(--t-text)' }}>{detailsAlert.resolved_at ? new Date(detailsAlert.resolved_at).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', hour12: true }) : 'Still active'}</span></div>
              <div><span style={{ color: 'var(--t-muted)' }}>Acknowledged by: </span><span style={{ color: 'var(--t-text)' }}>{detailsAlert.acknowledged_by ?? 'N/A'}</span></div>
            </div>
            <div className="rounded-lg p-4" style={{ background: 'rgba(0,212,255,0.04)', border: '1px solid var(--t-border-alpha)' }}><div className="font-mono text-[10px] uppercase tracking-widest mb-2" style={{ color: 'var(--t-muted)' }}>Full event history</div><pre className="font-mono text-xs whitespace-pre-wrap break-words" style={{ color: 'var(--t-text)', fontFamily: 'inherit' }}>{detailsAlert.description || 'No description recorded.'}</pre></div>
          </div>
        </div>
      )}
    </div>
  )
}
