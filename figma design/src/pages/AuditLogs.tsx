import { useCallback, useEffect, useState } from 'react'
import GlassCard from '../components/GlassCard'
import TablePagination from '../components/TablePagination'
import { toast } from '../lib/swal'
import {
  getAuditLogSummary,
  listAuditLogs,
  listAuditLogUsers,
  type AuditLogFilters,
  type AuditLogPage,
  type AuditLogSummary,
  type AuditLogUser,
  type AuditLogRecord,
} from '../lib/api'

const inputStyle: React.CSSProperties = {
  background: 'var(--t-border-light, rgba(255,255,255,0.04))',
  border: '1px solid var(--t-border-alpha)',
  color: 'var(--t-text)',
  outline: 'none',
}

const EMPTY_SUMMARY: AuditLogSummary = {
  total_activities: 0,
  successful_actions: 0,
  failed_actions: 0,
  login_success: 0,
  login_failed: 0,
  account_locked: 0,
  user_status_changes: 0,
}

type FilterState = {
  user_id: string
  outcome: string
  start_date: string
  end_date: string
}

const EMPTY_FILTERS: FilterState = {
  user_id: '', outcome: '', start_date: '', end_date: '',
}

function toApiFilters(filters: FilterState, pageSize: number, page: number): AuditLogFilters & { include_total: true } {
  const result: AuditLogFilters & { include_total: true } = { limit: pageSize, offset: (page - 1) * pageSize, include_total: true }
  if (filters.user_id) result.user_id = Number(filters.user_id)
  if (filters.outcome) result.outcome = filters.outcome
  if (filters.start_date) result.start_date = filters.start_date
  if (filters.end_date) result.end_date = filters.end_date
  return result
}

function isAccessDenied(error: unknown) {
  return error instanceof Error && /permission|access denied/i.test(error.message)
}

export default function AuditLogs() {
  const [logs, setLogs] = useState<AuditLogRecord[]>([])
  const [summary, setSummary] = useState<AuditLogSummary>(EMPTY_SUMMARY)
  const [users, setUsers] = useState<AuditLogUser[]>([])
  const [filters, setFilters] = useState<FilterState>(EMPTY_FILTERS)
  const [pendingFilters, setPendingFilters] = useState<FilterState>(EMPTY_FILTERS)
  const [loading, setLoading] = useState(true)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(50)
  const [total, setTotal] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [accessDenied, setAccessDenied] = useState(false)

  const load = useCallback(async (activeFilters: FilterState, activePage: number, activePageSize: number) => {
    setLoading(true)
    setError(null)
    setAccessDenied(false)
    try {
      const apiFilters = toApiFilters(activeFilters, activePageSize, activePage)
      const [auditLogs, auditSummary, auditUsers] = await Promise.all([
        listAuditLogs(apiFilters) as Promise<AuditLogPage>,
        getAuditLogSummary({
          start_date: activeFilters.start_date || undefined,
          end_date: activeFilters.end_date || undefined,
        }),
        listAuditLogUsers(),
      ])
      setLogs(auditLogs.items)
      setTotal(auditLogs.total)
      setSummary(auditSummary)
      setUsers(auditUsers)
    } catch (e) {
      const denied = isAccessDenied(e)
      setAccessDenied(denied)
      setError(denied ? 'You do not have access to security-wide audit activity.' : e instanceof Error ? e.message : 'Failed to load audit logs')
      if (!denied) toast.error(e instanceof Error ? e.message : 'Failed to load audit logs')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load(filters, page, pageSize)
    const timer = window.setInterval(() => { void load(filters, page, pageSize) }, 10000)
    return () => window.clearInterval(timer)
  }, [load, filters, page, pageSize])

  function applyFilters() {
    setFilters(pendingFilters)
    setPage(1)
    void load(pendingFilters, 1, pageSize)
  }

  function clearFilters() {
    setPendingFilters(EMPTY_FILTERS)
    setFilters(EMPTY_FILTERS)
    setPage(1)
    void load(EMPTY_FILTERS, 1, pageSize)
  }

  function updateFilter(key: keyof FilterState, value: string) {
    setPendingFilters(current => ({ ...current, [key]: value }))
  }

  const summaryCards: Array<[string, number, string]> = [
    ['Total Activities', summary.total_activities, 'var(--t-accent)'],
    ['Successful Actions', summary.successful_actions, '#00ff88'],
    ['Failed Actions', summary.failed_actions, '#ff6688'],
    ['Login Success', summary.login_success, '#00ff88'],
    ['Login Failed', summary.login_failed, '#ff6688'],
    ['Account Locked', summary.account_locked, '#f59e0b'],
    ['User Status Changes', summary.user_status_changes, '#a855f7'],
  ]

  if (loading && !logs.length && !error) {
    return <div className="p-6 flex items-center justify-center min-h-[50vh]"><div className="flex flex-col items-center gap-3"><div className="w-8 h-8 rounded-full border-2 animate-spin" style={{ borderColor: 'var(--t-accent)', borderTopColor: 'transparent' }} /><span className="font-mono text-xs" style={{ color: 'var(--t-muted)' }}>LOADING AUDIT ACTIVITY…</span></div></div>
  }

  if (accessDenied) {
    return <div className="p-6 flex items-center justify-center min-h-[50vh]"><GlassCard className="p-8 text-center max-w-md"><h2 className="font-display font-semibold text-lg mb-2" style={{ color: '#ff6688' }}>Access Denied</h2><p className="font-mono text-xs" style={{ color: 'var(--t-muted)' }}>{error}</p></GlassCard></div>
  }

  return (
    <div className="p-4 md:p-6 space-y-5">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div><h1 className="font-display font-bold text-xl md:text-2xl" style={{ color: 'var(--t-text)' }}>Audit Logs</h1><p className="font-mono text-xs mt-1" style={{ color: 'var(--t-muted)' }}>{logs.length} visible entr{logs.length !== 1 ? 'ies' : 'y'} • Read-only</p></div>
        <button onClick={() => { void load(filters, page, pageSize) }} disabled={loading} className="rounded-lg px-3 py-2 font-mono text-xs disabled:opacity-50" style={{ ...inputStyle, color: 'var(--t-accent)' }}>REFRESH</button>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-7 gap-3">
        {summaryCards.map(([label, value, color]) => <GlassCard key={label} className="p-4"><div className="font-mono text-[10px] uppercase tracking-wider" style={{ color: 'var(--t-muted)' }}>{label}</div><div className="font-display font-bold text-2xl mt-2" style={{ color }}>{value}</div></GlassCard>)}
      </div>

      <GlassCard className="p-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          <select value={pendingFilters.user_id} onChange={e => updateFilter('user_id', e.target.value)} className="rounded-lg px-3 py-2 font-mono text-xs" style={inputStyle}><option value="">All users</option>{users.map(user => <option key={user.id} value={user.id}>{user.name} ({user.email})</option>)}</select>
          <select value={pendingFilters.outcome} onChange={e => updateFilter('outcome', e.target.value)} className="rounded-lg px-3 py-2 font-mono text-xs" style={inputStyle}><option value="">All outcomes</option><option value="success">Success</option><option value="failure">Failure</option></select>
          <input type="date" value={pendingFilters.start_date} onChange={e => updateFilter('start_date', e.target.value)} className="rounded-lg px-3 py-2 font-mono text-xs" style={inputStyle} />
          <input type="date" value={pendingFilters.end_date} onChange={e => updateFilter('end_date', e.target.value)} className="rounded-lg px-3 py-2 font-mono text-xs" style={inputStyle} />
        </div>
        <div className="flex gap-2 mt-4"><button onClick={applyFilters} disabled={loading} className="rounded-lg px-4 py-2 font-mono text-xs disabled:opacity-50" style={{ ...inputStyle, color: 'var(--t-accent)' }}>APPLY FILTERS</button><button onClick={clearFilters} disabled={loading} className="rounded-lg px-4 py-2 font-mono text-xs disabled:opacity-50" style={inputStyle}>CLEAR FILTERS</button></div>
      </GlassCard>

      {error && !accessDenied && <GlassCard className="p-4" style={{ borderColor: 'rgba(255,102,136,0.45)' }}><p className="font-mono text-xs" style={{ color: '#ff6688' }}>{error}</p></GlassCard>}

      <GlassCard className="overflow-hidden">
        <div className="overflow-x-auto"><table className="w-full text-left" style={{ minWidth: 980 }}><thead><tr style={{ borderBottom: '1px solid var(--t-border-light)' }}>{['Action', 'Resource', 'User', 'Source IP', 'User Agent', 'Timestamp'].map(h => <th key={h} className="px-4 py-3 font-mono text-xs uppercase tracking-wider" style={{ color: 'var(--t-muted)' }}>{h}</th>)}</tr></thead><tbody>{logs.map(log => <tr key={log.id} style={{ borderBottom: '1px solid var(--t-border-alpha)' }}><td className="px-4 py-3 font-display font-medium text-sm" style={{ color: 'var(--t-text)' }}>{log.action}</td><td className="px-4 py-3 font-mono text-xs" style={{ color: 'var(--t-muted)' }}>{log.resource_name}</td><td className="px-4 py-3 font-mono text-xs" style={{ color: 'var(--t-muted)' }}>{log.user_name ?? (log.user_id != null ? `User #${log.user_id}` : 'System')}</td><td className="px-4 py-3 font-mono text-xs" style={{ color: log.source_ip ? 'var(--t-text)' : 'var(--t-muted)' }}>{log.source_ip ?? '—'}</td><td className="px-4 py-3 font-mono text-[10px] max-w-[220px] truncate" title={log.user_agent ?? undefined} style={{ color: 'var(--t-muted)' }}>{log.user_agent ?? '—'}</td><td className="px-4 py-3 font-mono text-xs" style={{ color: 'var(--t-muted)' }}>{new Date(log.timestamp).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', hour12: true })}</td></tr>)}</tbody></table></div>
        {logs.length === 0 && <div className="py-12 text-center font-mono text-xs" style={{ color: 'var(--t-muted)' }}>No audit logs match the selected filters.</div>}
        {total > 0 && <TablePagination
          page={page}
          pageCount={Math.max(1, Math.ceil(total / pageSize))}
          pageSize={pageSize}
          startItem={(page - 1) * pageSize + 1}
          endItem={Math.min(page * pageSize, total)}
          totalItems={total}
          pageSizes={[25, 50, 100]}
          onPageChange={nextPage => { setPage(nextPage); void load(filters, nextPage, pageSize) }}
          onPageSizeChange={nextSize => { setPageSize(nextSize); setPage(1); void load(filters, 1, nextSize) }}
        />}
      </GlassCard>
    </div>
  )
}
