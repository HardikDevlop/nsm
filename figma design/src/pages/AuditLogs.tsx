import { useCallback, useEffect, useState } from 'react'
import GlassCard from '../components/GlassCard'
import { toast } from '../lib/swal'
import {
  listAuditLogs,
  type AuditLogRecord,
} from '../lib/api'

const inputStyle: React.CSSProperties = {
  background: 'rgba(255,255,255,0.04)',
  border: '1px solid var(--t-border-alpha)',
  color: 'var(--t-text)',
  outline: 'none',
}

export default function AuditLogs() {
  const [logs, setLogs] = useState<AuditLogRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')

  const load = useCallback(async () => {
    try {
      setLogs(await listAuditLogs())
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to load audit logs')
    }
    setLoading(false)
  }, [])

  useEffect(() => { void load() }, [load])

  const filtered = logs.filter(log =>
    !search.trim() ||
    log.action.toLowerCase().includes(search.toLowerCase()) ||
    log.resource_name.toLowerCase().includes(search.toLowerCase())
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
          <h1 className="font-display font-bold text-xl md:text-2xl" style={{ color: 'var(--t-text)' }}>Audit Logs</h1>
          <p className="font-mono text-xs mt-1" style={{ color: 'var(--t-muted)' }}>{logs.length} log entr{logs.length !== 1 ? 'ies' : 'y'} • Read-only</p>
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
        </div>
      </div>

      <GlassCard className="overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left" style={{ minWidth: 640 }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--t-border-light)' }}>
                {['Action', 'Resource', 'User ID', 'Timestamp'].map(h => (
                  <th key={h} className="px-4 py-3 font-mono text-xs uppercase tracking-wider" style={{ color: 'var(--t-muted)' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.map(log => (
                <tr key={log.id} style={{ borderBottom: '1px solid var(--t-border-alpha)' }}
                  onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = 'rgba(0,212,255,0.03)' }}
                  onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = '' }}>
                  <td className="px-4 py-3">
                    <span className="font-display font-medium text-sm" style={{ color: 'var(--t-text)' }}>
                      {log.action}
                    </span>
                  </td>
                  <td className="px-4 py-3 font-mono text-xs" style={{ color: 'var(--t-muted)' }}>
                    {log.resource_name}
                  </td>
                  <td className="px-4 py-3 font-mono text-xs" style={{ color: 'var(--t-muted)' }}>
                    {log.user_id ?? '—'}
                  </td>
                  <td className="px-4 py-3 font-mono text-xs" style={{ color: 'var(--t-muted)' }}>
                    {new Date(log.timestamp).toLocaleString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {filtered.length === 0 && (
          <div className="py-12 text-center font-mono text-xs" style={{ color: 'var(--t-muted)' }}>
            {search ? 'No audit logs match your search.' : 'No audit logs yet.'}
          </div>
        )}
      </GlassCard>
    </div>
  )
}
