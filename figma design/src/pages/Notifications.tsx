import { useCallback, useEffect, useState } from 'react'
import GlassCard from '../components/GlassCard'
import { PermissionGuard } from '../components/PermissionGuard'
import { toast, confirmDanger } from '../lib/swal'
import {
  listNotifications, createNotification, updateNotification, deleteNotification, listAlerts,
  type NotificationRecord,
  type AlertRecord,
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
  background: 'rgba(255,255,255,0.04)',
  border: '1px solid var(--t-border-alpha)',
  color: 'var(--t-text)',
  outline: 'none',
}

const statusColors: Record<string, string> = {
  pending: '#ffa500',
  sent: '#4ade80',
  failed: '#ff3366',
}

export default function Notifications() {
  const [notifications, setNotifications] = useState<NotificationRecord[]>([])
  const [alerts, setAlerts] = useState<AlertRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [showModal, setShowModal] = useState(false)
  const [editing, setEditing] = useState<NotificationRecord | null>(null)
  const [saving, setSaving] = useState(false)
  const [search, setSearch] = useState('')

  const [fAlertId, setFAlertId] = useState<number | ''>('')
  const [fChannel, setFChannel] = useState('email')
  const [fSentTo, setFSentTo] = useState('')
  const [fStatus, setFStatus] = useState('pending')

  const load = useCallback(async () => {
    try {
      const [notificationsData, alertsData] = await Promise.all([listNotifications(), listAlerts()])
      setNotifications(notificationsData)
      setAlerts(alertsData)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to load notifications')
    }
    setLoading(false)
  }, [])

  useEffect(() => { void load() }, [load])

  function openCreate() {
    setEditing(null)
    setFAlertId('')
    setFChannel('email')
    setFSentTo('')
    setFStatus('pending')
    setShowModal(true)
  }

  function openEdit(notification: NotificationRecord) {
    setEditing(notification)
    setFAlertId(notification.alert_id ?? '')
    setFChannel(notification.channel)
    setFSentTo(notification.sent_to)
    setFStatus(notification.status)
    setShowModal(true)
  }

  async function handleSubmit() {
    if (!fSentTo.trim()) { toast.warning('Recipient is required'); return }
    setSaving(true)
    try {
      const data = {
        alert_id: fAlertId === '' ? null : fAlertId,
        channel: fChannel,
        sent_to: fSentTo.trim(),
        status: fStatus,
      }
      if (editing) {
        await updateNotification(editing.id, data)
        toast.success(`Notification updated`)
      } else {
        await createNotification(data)
        toast.success(`Notification created`)
      }
      setShowModal(false)
      await load()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Save failed')
    }
    setSaving(false)
  }

  async function handleDelete(notification: NotificationRecord) {
    const ok = await confirmDanger({
      title: `Delete notification?`,
      text: 'This action cannot be undone.',
      confirmText: 'Delete Notification',
    })
    if (!ok) return
    try {
      await deleteNotification(notification.id)
      toast.success(`Notification deleted`)
      await load()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Delete failed')
    }
  }

  const filtered = notifications.filter(n =>
    !search.trim() ||
    n.channel.toLowerCase().includes(search.toLowerCase()) ||
    n.sent_to.toLowerCase().includes(search.toLowerCase()) ||
    n.status.toLowerCase().includes(search.toLowerCase())
  )

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
          <h1 className="font-display font-bold text-xl md:text-2xl" style={{ color: 'var(--t-text)' }}>Notifications</h1>
          <p className="font-mono text-xs mt-1" style={{ color: 'var(--t-muted)' }}>{notifications.length} notification{notifications.length !== 1 ? 's' : ''}</p>
        </div>
        <div className="flex gap-2">
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search…"
            className="rounded-lg px-3 py-2 font-mono text-xs"
            style={{ ...inputStyle, minWidth: 160 }}
            onFocus={e => { e.currentTarget.style.borderColor = 'var(--t-accent)' }}
            onBlur={e => { e.currentTarget.style.borderColor = 'var(--t-border-alpha)' }}
          />
          <PermissionGuard permission="notifications:create">
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
          <table className="w-full text-left" style={{ minWidth: 640 }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--t-border-light)' }}>
                {['Channel', 'Sent To', 'Alert', 'Status', 'Sent At', 'Actions'].map(h => (
                  <th key={h} className="px-4 py-3 font-mono text-xs uppercase tracking-wider" style={{ color: 'var(--t-muted)' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.map(notification => {
                const alert = alerts.find(a => a.id === notification.alert_id)
                return (
                  <tr key={notification.id} style={{ borderBottom: '1px solid var(--t-border-alpha)' }}
                    onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = 'rgba(0,212,255,0.03)' }}
                    onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = '' }}>
                    <td className="px-4 py-3 font-display font-medium text-sm" style={{ color: 'var(--t-text)' }}>
                      {notification.channel}
                    </td>
                    <td className="px-4 py-3 font-mono text-xs" style={{ color: 'var(--t-muted)' }}>
                      {notification.sent_to}
                    </td>
                    <td className="px-4 py-3 font-mono text-xs" style={{ color: 'var(--t-muted)' }}>
                      {alert ? alert.title : '—'}
                    </td>
                    <td className="px-4 py-3">
                      <span className="px-2 py-1 rounded text-xs font-mono"
                        style={{ background: `${statusColors[notification.status]}20`, color: statusColors[notification.status] }}>
                        {notification.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 font-mono text-xs" style={{ color: 'var(--t-muted)' }}>
                      {notification.sent_at ? new Date(notification.sent_at).toLocaleString() : '—'}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex gap-1">
                        <PermissionGuard permission="notifications:update">
                          <button onClick={() => openEdit(notification)} title="Edit"
                            className="p-1.5 rounded transition-colors" style={{ color: 'var(--t-muted)' }}
                            onMouseEnter={e => { e.currentTarget.style.color = 'var(--t-accent)' }}
                            onMouseLeave={e => { e.currentTarget.style.color = 'var(--t-muted)' }}>
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                              <path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/>
                            </svg>
                          </button>
                        </PermissionGuard>
                        <PermissionGuard permission="notifications:delete">
                          <button onClick={() => handleDelete(notification)} title="Delete"
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
            {search ? 'No notifications match your search.' : 'No notifications yet.'}
          </div>
        )}
      </GlassCard>

      {showModal && (
        <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4" onClick={() => setShowModal(false)}>
          <div className="glass rounded-xl p-6 w-full max-w-lg shadow-2xl" style={{ border: '1px solid rgba(0,212,255,0.25)' }}
            onClick={e => e.stopPropagation()}>
            <h3 className="font-display font-bold text-lg mb-4" style={{ color: 'var(--t-accent)' }}>
              {editing ? '✏ Edit Notification' : '+ New Notification'}
            </h3>
            <div className="space-y-4">
              <Field label="ALERT (OPTIONAL)">
                <select
                  value={fAlertId}
                  onChange={e => setFAlertId(e.target.value === '' ? '' : Number(e.target.value))}
                  className="w-full rounded-lg px-3 py-2.5 font-mono text-sm"
                  style={inputStyle}>
                  <option value="">-- None --</option>
                  {alerts.map(a => (
                    <option key={a.id} value={a.id}>{a.title}</option>
                  ))}
                </select>
              </Field>
              <Field label="CHANNEL *">
                <select
                  value={fChannel}
                  onChange={e => setFChannel(e.target.value)}
                  className="w-full rounded-lg px-3 py-2.5 font-mono text-sm"
                  style={inputStyle}>
                  <option value="email">Email</option>
                  <option value="sms">SMS</option>
                  <option value="slack">Slack</option>
                  <option value="webhook">Webhook</option>
                </select>
              </Field>
              <Field label="SENT TO *">
                <input
                  value={fSentTo}
                  onChange={e => setFSentTo(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter') void handleSubmit() }}
                  autoFocus
                  placeholder="e.g. admin@example.com"
                  className="w-full rounded-lg px-3 py-2.5 font-mono text-sm"
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
                  <option value="pending">Pending</option>
                  <option value="sent">Sent</option>
                  <option value="failed">Failed</option>
                </select>
              </Field>
            </div>
            <div className="flex gap-2 justify-end mt-6">
              <button
                onClick={() => setShowModal(false)}
                className="rounded-lg px-4 py-2 font-mono text-xs hover:opacity-80 transition-all"
                style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid var(--t-border-alpha)', color: 'var(--t-muted)' }}>
                Cancel
              </button>
              <button
                onClick={() => void handleSubmit()}
                disabled={saving || !fSentTo.trim()}
                className="rounded-lg px-5 py-2 font-mono text-xs font-semibold transition-all disabled:opacity-50 flex items-center gap-2"
                style={{ background: 'var(--t-accent)', color: '#fff', border: '1px solid var(--t-accent-border)' }}>
                {saving ? <><span className="w-3 h-3 rounded-full border animate-spin inline-block" style={{ borderColor:'#fff',borderTopColor:'transparent' }}/> Saving…</> : editing ? '✓ Update' : '+ Create'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
