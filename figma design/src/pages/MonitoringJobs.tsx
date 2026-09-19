import { useCallback, useEffect, useState } from 'react'
import GlassCard from '../components/GlassCard'
import { PermissionGuard } from '../components/PermissionGuard'
import TablePagination from '../components/TablePagination'
import { useTablePagination } from '../hooks/useTablePagination'
import { toast, confirmDanger } from '../lib/swal'
import { listMonitoringJobs, getRuntimeStatus, getOverview, getDeviceMonitoringConfigs, restartMonitoringJob, restartRuntimeProcess, createMonitoringJob, updateMonitoringJob, deleteMonitoringJob, type MonitoringJobRecord, type RuntimeStatusRecord, type OverviewResponse } from '../lib/api'

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (<div><label className="font-mono text-xs block mb-1" style={{ color: 'var(--t-muted)' }}>{label}</label>{children}</div>)
}

const inputStyle: React.CSSProperties = { background: 'var(--t-border-light, rgba(255,255,255,0.04))', border: '1px solid var(--t-border-alpha)', color: 'var(--t-text)', outline: 'none' }

export default function MonitoringJobs() {
  const [items, setItems] = useState<MonitoringJobRecord[]>([])
  const [runtime, setRuntime] = useState<RuntimeStatusRecord | null>(null)
  const [overview, setOverview] = useState<OverviewResponse | null>(null)
  const [snmpJobs, setSnmpJobs] = useState<Array<any>>([])
  const [metricDetail, setMetricDetail] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [showModal, setShowModal] = useState(false)
  const [editing, setEditing] = useState<MonitoringJobRecord | null>(null)
  const [saving, setSaving] = useState(false)
  const [search, setSearch] = useState('')
  const [fName, setFName] = useState('')
  const [fType, setFType] = useState('icmp')
  const [fSchedule, setFSchedule] = useState('*/5 * * * *')
  const [fEnabled, setFEnabled] = useState(true)

  const load = useCallback(async () => {
    const [jobsResult, runtimeResult, overviewResult] = await Promise.allSettled([listMonitoringJobs(), getRuntimeStatus(), getOverview(24)])
    if (jobsResult.status === 'fulfilled') setItems(jobsResult.value)
    else toast.error(jobsResult.reason instanceof Error ? jobsResult.reason.message : 'Failed to load monitoring jobs')
    if (runtimeResult.status === 'fulfilled') setRuntime(runtimeResult.value)
    else setRuntime(null)
    if (overviewResult.status === 'fulfilled') {
      setOverview(overviewResult.value)
      const configs = await Promise.all(overviewResult.value.devices.map(device => getDeviceMonitoringConfigs(device.id).catch(() => [])))
      setSnmpJobs(configs.flat())
    }
    setLoading(false)
  }, [])

  async function handleRestart(pid: number) {
    try { await restartRuntimeProcess(pid); toast.success('Monitoring worker restart requested'); await load() }
    catch (e) { toast.error(e instanceof Error ? e.message : 'Restart failed') }
  }

  async function handleJobRestart(job: any) {
    try { await restartMonitoringJob(job.device_id, job.module_name, job.interval_seconds); toast.success(`${job.module_name} restarted`); await load() }
    catch (e) { toast.error(e instanceof Error ? e.message : 'Job restart failed') }
  }

  function duration(seconds: number) {
    const days = Math.floor(seconds / 86400); const hours = Math.floor((seconds % 86400) / 3600); const minutes = Math.floor((seconds % 3600) / 60)
    return `${days ? `${days}d ` : ''}${hours}h ${minutes}m`
  }

  useEffect(() => { void load() }, [load])

  function openCreate() {
    setEditing(null); setFName(''); setFType('icmp'); setFSchedule('*/5 * * * *'); setFEnabled(true); setShowModal(true)
  }
  function openEdit(item: MonitoringJobRecord) {
    setEditing(item); setFName(item.job_name); setFType(item.job_type); setFSchedule(item.schedule); setFEnabled(item.enabled); setShowModal(true)
  }

  async function handleSubmit() {
    if (!fName.trim()) { toast.warning('Name required'); return }
    setSaving(true)
    try {
      const data = { job_name: fName.trim(), job_type: fType, schedule: fSchedule, enabled: fEnabled }
      if (editing) {
        await updateMonitoringJob(editing.id, data)
        toast.success('Updated')
      } else {
        await createMonitoringJob(data)
        toast.success('Created')
      }
      setShowModal(false)
      await load()
    } catch (e) { toast.error(e instanceof Error ? e.message : 'Save failed') }
    setSaving(false)
  }

  async function handleDelete(item: MonitoringJobRecord) {
    const ok = await confirmDanger({ title: `Delete "${item.job_name}"?`, text: 'Cannot be undone.', confirmText: 'Delete' })
    if (!ok) return
    try { await deleteMonitoringJob(item.id); toast.success('Deleted'); await load() } catch (e) { toast.error(e instanceof Error ? e.message : 'Delete failed') }
  }

  const filtered = items.filter(i => !search.trim() || i.job_name.toLowerCase().includes(search.toLowerCase()) || i.job_type.toLowerCase().includes(search.toLowerCase()))
  const pagination = useTablePagination(filtered)

  if (loading) {
    return (<div className="p-6 flex items-center justify-center min-h-[50vh]"><div className="flex flex-col items-center gap-3"><div className="w-8 h-8 rounded-full border-2 animate-spin" style={{ borderColor: 'var(--t-accent)', borderTopColor: 'transparent' }} /><span className="font-mono text-xs" style={{ color: 'var(--t-muted)' }}>LOADING…</span></div></div>)
  }

  return (
    <div className="p-4 md:p-6 space-y-5">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div><h1 className="font-display font-bold text-xl md:text-2xl" style={{ color: 'var(--t-text)' }}>Monitoring Jobs</h1><p className="font-mono text-xs mt-1" style={{ color: 'var(--t-muted)' }}>{overview?.normalized.polling.configured_jobs ?? items.length} configured job{(overview?.normalized.polling.configured_jobs ?? items.length) !== 1 ? 's' : ''}</p></div>
        <div className="flex gap-2">
          <input value={search} onChange={e => { setSearch(e.target.value); pagination.setPage(1) }} placeholder="Search…" className="rounded-lg px-3 py-2 font-mono text-xs" style={{ ...inputStyle, minWidth: 160 }} onFocus={e => { e.currentTarget.style.borderColor = 'var(--t-accent)' }} onBlur={e => { e.currentTarget.style.borderColor = 'var(--t-border-alpha)' }} />
        </div>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {[
          ['Processes', runtime ? runtime.processes.length : (overview?.services.any_running ? 2 : '—'), 'var(--t-accent)'],
          ['Running', runtime ? runtime.processes.filter(p => p.status === 'running').length : (overview?.services.any_running ? 1 : '—'), '#4ade80'],
          ['Response', runtime ? `${runtime.response_time_ms} ms` : (overview ? `${overview.normalized.polling.total_attempts} attempts` : 'Unavailable'), 'var(--t-accent)'],
          ['Configured jobs', overview?.normalized.polling.configured_jobs ?? items.length, 'var(--t-accent)'],
          ['Workers', overview ? `${[overview.services.snmp_polling, overview.services.realtime_monitor].filter(worker => worker.running).length}/2` : '—', '#4ade80'],
        ].map(([label, value, color]) => <GlassCard key={String(label)} className="p-4 cursor-pointer transition-all hover:-translate-y-0.5 hover:border-cyan-400/60" onClick={() => setMetricDetail(String(label))} role="button" tabIndex={0}><div className="font-mono text-[10px] uppercase" style={{ color: 'var(--t-muted)' }}>{label}</div><div className="font-display text-2xl mt-1" style={{ color: String(color) }}>{value}</div><div className="font-mono text-[9px] mt-2" style={{ color: 'var(--t-muted)' }}>CLICK FOR DETAILS</div></GlassCard>)}
      </div>

      {metricDetail && <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={() => setMetricDetail(null)}><div className="w-full max-w-lg rounded-xl p-5 shadow-2xl" style={{ background: 'var(--t-surface, #0f1b2d)', border: '1px solid var(--t-accent-border)' }} onClick={event => event.stopPropagation()}><div className="flex items-center justify-between"><h2 className="font-display font-bold text-lg" style={{ color: 'var(--t-text)' }}>{metricDetail}</h2><button className="rounded px-3 py-1 font-mono text-xs" style={{ border: '1px solid var(--t-border-alpha)', color: 'var(--t-muted)' }} onClick={() => setMetricDetail(null)}>CLOSE</button></div><div className="mt-4 space-y-3 font-mono text-xs" style={{ color: 'var(--t-muted)' }}>{metricDetail === 'Processes' && <><p><b style={{ color: 'var(--t-text)' }}>Meaning:</b> detected NMS backend processes, such as Uvicorn and monitoring workers.</p><p><b style={{ color: 'var(--t-text)' }}>Current:</b> {runtime ? `${runtime.processes.length} process(es)` : overview ? 'Process-level endpoint unavailable; service telemetry is being used.' : 'Unavailable'}</p></>}{metricDetail === 'Running' && <><p><b style={{ color: 'var(--t-text)' }}>Meaning:</b> processes currently in running state.</p><p><b style={{ color: 'var(--t-text)' }}>Current:</b> {runtime ? `${runtime.processes.filter(process => process.status === 'running').length} process(es)` : overview ? `${[overview.services.snmp_polling, overview.services.realtime_monitor].filter(worker => worker.running).length} registered worker(s)` : 'Unavailable'}</p></>}{metricDetail === 'Response' && <><p><b style={{ color: 'var(--t-text)' }}>Meaning:</b> runtime-status API response time when process telemetry is available.</p><p><b style={{ color: 'var(--t-text)' }}>Current:</b> {runtime ? `${runtime.response_time_ms} ms` : `Runtime API unavailable; ${overview?.normalized.polling.total_attempts ?? 0} polling attempts observed`}</p></>}{metricDetail === 'Configured jobs' && <><p><b style={{ color: 'var(--t-text)' }}>Meaning:</b> enabled SNMP monitoring configurations across devices.</p><p><b style={{ color: 'var(--t-text)' }}>Current:</b> {overview?.normalized.polling.configured_jobs ?? items.length} configured job(s), {overview?.normalized.polling.active_jobs ?? 0} active now.</p></>}</div></div></div>}

      <GlassCard className="overflow-hidden">
        <div className="px-4 py-3 font-mono text-xs uppercase tracking-wider" style={{ color: 'var(--t-muted)', borderBottom: '1px solid var(--t-border-light)' }}>NMS workers and services</div>
        <div className="overflow-x-auto"><table className="w-full text-left" style={{ minWidth: 760 }}><thead><tr style={{ borderBottom: '1px solid var(--t-border-light)' }}>{['Process', 'PID', 'Status', 'Uptime', 'Command', 'Action'].map(h => <th key={h} className="px-4 py-3 font-mono text-xs uppercase" style={{ color: 'var(--t-muted)' }}>{h}</th>)}</tr></thead><tbody>{runtime?.processes.map(process => <tr key={process.pid} style={{ borderBottom: '1px solid var(--t-border-alpha)' }}><td className="px-4 py-3 font-medium text-sm" style={{ color: 'var(--t-text)' }}>{process.name}</td><td className="px-4 py-3 font-mono text-xs" style={{ color: 'var(--t-muted)' }}>{process.pid}</td><td className="px-4 py-3"><span className="px-2 py-1 rounded text-xs font-mono" style={{ color: '#4ade80', background: 'rgba(74,222,128,.16)' }}>{process.status}</span></td><td className="px-4 py-3 font-mono text-xs" style={{ color: 'var(--t-muted)' }}>{duration(process.uptime_seconds)}</td><td className="px-4 py-3 font-mono text-[10px] max-w-[420px] truncate" style={{ color: 'var(--t-muted)' }}>{process.command}</td><td className="px-4 py-3"><button onClick={() => void handleRestart(process.pid)} disabled={process.name !== 'Monitoring worker'} className="rounded px-3 py-1.5 font-mono text-xs disabled:opacity-40" style={{ color: '#fff', background: 'var(--t-accent)' }}>Restart</button></td></tr>)}</tbody></table></div>
        {!runtime?.processes.length && overview && <div className="grid grid-cols-1 md:grid-cols-2 gap-3 p-4"><div className="rounded-lg p-3" style={{ border: '1px solid var(--t-border-alpha)' }}><div className="font-medium" style={{ color: 'var(--t-text)' }}>SNMP Polling Service</div><div className="font-mono text-xs mt-2" style={{ color: overview.services.snmp_polling.running ? '#4ade80' : '#ff3366' }}>{overview.services.snmp_polling.running ? 'RUNNING' : 'STOPPED'} · {overview.normalized.polling.active_jobs} active jobs</div><div className="font-mono text-xs mt-1" style={{ color: 'var(--t-muted)' }}>{overview.normalized.polling.successful_attempts} success · {overview.normalized.polling.failed_attempts} failed</div></div><div className="rounded-lg p-3" style={{ border: '1px solid var(--t-border-alpha)' }}><div className="font-medium" style={{ color: 'var(--t-text)' }}>Realtime Monitor</div><div className="font-mono text-xs mt-2" style={{ color: overview.services.realtime_monitor.running ? '#4ade80' : '#ff3366' }}>{overview.services.realtime_monitor.running ? 'RUNNING' : 'STOPPED'}</div><div className="font-mono text-xs mt-1" style={{ color: 'var(--t-muted)' }}>Live service telemetry available</div></div></div>}
        {!runtime?.processes.length && !overview && <div className="py-8 text-center font-mono text-xs" style={{ color: 'var(--t-muted)' }}>Runtime telemetry unavailable.</div>}
      </GlassCard>

      {snmpJobs.length > 0 && <GlassCard className="overflow-hidden"><div className="px-4 py-3 font-mono text-xs uppercase tracking-wider" style={{ color: 'var(--t-muted)', borderBottom: '1px solid var(--t-border-light)' }}>Live SNMP jobs</div><div className="overflow-x-auto"><table className="w-full text-left"><thead><tr style={{ borderBottom: '1px solid var(--t-border-light)' }}>{['Device ID', 'Job / Module', 'Interval', 'Status', 'Last Poll', 'Action'].map(h => <th key={h} className="px-4 py-3 font-mono text-xs uppercase" style={{ color: 'var(--t-muted)' }}>{h}</th>)}</tr></thead><tbody>{snmpJobs.map(job => <tr key={`${job.device_id}-${job.module_name}`} style={{ borderBottom: '1px solid var(--t-border-alpha)' }}><td className="px-4 py-3 font-mono text-xs" style={{ color: 'var(--t-muted)' }}>{job.device_id}</td><td className="px-4 py-3 font-medium" style={{ color: 'var(--t-text)' }}>{job.module_name}</td><td className="px-4 py-3 font-mono text-xs" style={{ color: 'var(--t-muted)' }}>{job.interval_seconds}s</td><td className="px-4 py-3 font-mono text-xs" style={{ color: job.status === 'running' ? '#4ade80' : '#ff3366' }}>{job.status}</td><td className="px-4 py-3 font-mono text-xs" style={{ color: 'var(--t-muted)' }}>{job.last_poll_at ?? '—'}</td><td className="px-4 py-3"><button onClick={() => void handleJobRestart(job)} className="rounded px-3 py-1.5 font-mono text-xs" style={{ background: 'var(--t-accent)', color: '#fff' }}>Restart</button></td></tr>)}</tbody></table></div></GlassCard>}

      {overview && <GlassCard className="overflow-hidden"><div className="flex items-center justify-between px-4 py-3" style={{ borderBottom: '1px solid var(--t-border-light)' }}><div className="font-mono text-xs uppercase tracking-wider" style={{ color: 'var(--t-muted)' }}>NMS workers ({[overview.services.snmp_polling, overview.services.realtime_monitor].filter(worker => worker.running).length} running / 2 registered)</div><div className="font-mono text-[10px]" style={{ color: 'var(--t-muted)' }}>Workers are backend services, not individual device jobs</div></div><div className="grid grid-cols-1 md:grid-cols-2 gap-3 p-4">{[
        { name: 'SNMP Polling Worker', state: overview.services.snmp_polling, role: 'Runs scheduled SNMP collection for configured device modules such as interfaces, CPU, memory, storage and environment. Persists polling results and errors.' },
        { name: 'Realtime Monitor Worker', state: overview.services.realtime_monitor, role: 'Performs live device reachability checks, records latency/packet loss, updates online/offline state and uptime/downtime counters.' },
      ].map(worker => <div key={worker.name} className="rounded-lg p-4" style={{ border: '1px solid var(--t-border-alpha)' }}><div className="flex items-center justify-between gap-3"><div className="font-display font-semibold" style={{ color: 'var(--t-text)' }}>{worker.name}</div><span className="rounded px-2 py-1 font-mono text-[10px]" style={{ color: worker.state.running ? '#4ade80' : '#ff3366', background: worker.state.running ? 'rgba(74,222,128,.14)' : 'rgba(255,51,102,.14)' }}>{worker.state.running ? 'RUNNING' : 'STOPPED'}</span></div><p className="mt-2 font-mono text-xs leading-relaxed" style={{ color: 'var(--t-muted)' }}>{worker.role}</p><div className="mt-3 font-mono text-[10px]" style={{ color: 'var(--t-muted)' }}>Last update: {worker.state.last_update ?? '—'}</div></div>)}</div></GlassCard>}

      <GlassCard className="overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left" style={{ minWidth: 640 }}>
            <thead><tr style={{ borderBottom: '1px solid var(--t-border-light)' }}>{['Name', 'Type', 'Schedule', 'Status', 'Last Run', 'Actions'].map(h => (<th key={h} className="px-4 py-3 font-mono text-xs uppercase tracking-wider" style={{ color: 'var(--t-muted)' }}>{h}</th>))}</tr></thead>
            <tbody>
              {pagination.paginatedItems.map(item => (
                <tr key={item.id} style={{ borderBottom: '1px solid var(--t-border-alpha)' }} onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = 'rgba(0,212,255,0.03)' }} onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = '' }}>
                  <td className="px-4 py-3 font-display font-medium text-sm" style={{ color: 'var(--t-text)' }}>{item.job_name}</td>
                  <td className="px-4 py-3 font-mono text-xs" style={{ color: 'var(--t-muted)' }}>{item.job_type}</td>
                  <td className="px-4 py-3 font-mono text-xs" style={{ color: 'var(--t-muted)' }}>{item.schedule}</td>
                  <td className="px-4 py-3"><span className="px-2 py-1 rounded text-xs font-mono" style={{ background: item.enabled ? 'rgba(74,222,128,0.2)' : 'rgba(255,51,102,0.2)', color: item.enabled ? '#4ade80' : '#ff3366' }}>{item.enabled ? 'Enabled' : 'Disabled'}</span></td>
                  <td className="px-4 py-3 font-mono text-xs" style={{ color: 'var(--t-muted)' }}>{item.last_run ? new Date(item.last_run).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', hour12: true }) : '—'}</td>
                  <td className="px-4 py-3">
                    <div className="flex gap-1">
                      <PermissionGuard permission="monitoring_jobs:update"><button onClick={() => openEdit(item)} title="Edit" className="p-1.5 rounded transition-colors" style={{ color: 'var(--t-muted)' }} onMouseEnter={e => { e.currentTarget.style.color = 'var(--t-accent)' }} onMouseLeave={e => { e.currentTarget.style.color = 'var(--t-muted)' }}><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/></svg></button></PermissionGuard>
                      <PermissionGuard permission="monitoring_jobs:delete"><button onClick={() => handleDelete(item)} title="Delete" className="p-1.5 rounded transition-colors" style={{ color: 'var(--t-muted)' }} onMouseEnter={e => { e.currentTarget.style.color = '#ff3366' }} onMouseLeave={e => { e.currentTarget.style.color = 'var(--t-muted)' }}><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/></svg></button></PermissionGuard>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {filtered.length === 0 && (<div className="py-12 text-center font-mono text-xs" style={{ color: 'var(--t-muted)' }}>{search ? 'No matches.' : 'No jobs yet.'}</div>)}
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
          <div className="glass rounded-xl p-6 w-full max-w-md shadow-2xl" style={{ border: '1px solid rgba(0,212,255,0.25)' }} onClick={e => e.stopPropagation()}>
            <h3 className="font-display font-bold text-lg mb-4" style={{ color: 'var(--t-accent)' }}>{editing ? '✏ Edit Job' : '+ New Job'}</h3>
            <div className="space-y-4">
              <Field label="NAME *"><input value={fName} onChange={e => setFName(e.target.value)} autoFocus placeholder="ICMP Check" className="w-full rounded-lg px-3 py-2.5 font-mono text-sm" style={inputStyle} onFocus={e => { e.currentTarget.style.borderColor = 'var(--t-accent)' }} onBlur={e => { e.currentTarget.style.borderColor = 'var(--t-border-alpha)' }}/></Field>
              <Field label="TYPE"><select value={fType} onChange={e => setFType(e.target.value)} className="w-full rounded-lg px-3 py-2.5 font-mono text-sm" style={inputStyle}><option value="icmp">ICMP</option><option value="snmp">SNMP</option><option value="tcp">TCP</option><option value="http">HTTP</option></select></Field>
              <Field label="SCHEDULE (CRON)"><input value={fSchedule} onChange={e => setFSchedule(e.target.value)} placeholder="*/5 * * * *" className="w-full rounded-lg px-3 py-2.5 font-mono text-sm" style={inputStyle} onFocus={e => { e.currentTarget.style.borderColor = 'var(--t-accent)' }} onBlur={e => { e.currentTarget.style.borderColor = 'var(--t-border-alpha)' }}/></Field>
              <Field label="ENABLED"><label className="flex items-center gap-2 cursor-pointer"><input type="checkbox" checked={fEnabled} onChange={e => setFEnabled(e.target.checked)} className="w-4 h-4"/><span className="font-mono text-xs" style={{ color: 'var(--t-text)' }}>Enable this job</span></label></Field>
            </div>
            <div className="flex gap-2 justify-end mt-6">
              <button onClick={() => setShowModal(false)} className="rounded-lg px-4 py-2 font-mono text-xs hover:opacity-80 transition-all" style={{ background: 'var(--t-border-light, rgba(255,255,255,0.05))', border: '1px solid var(--t-border-alpha)', color: 'var(--t-muted)' }}>Cancel</button>
              <button onClick={() => void handleSubmit()} disabled={saving || !fName.trim()} className="rounded-lg px-5 py-2 font-mono text-xs font-semibold transition-all disabled:opacity-50 flex items-center gap-2" style={{ background: 'var(--t-accent)', color: '#fff', border: '1px solid var(--t-accent-border)' }}>{saving ? <><span className="w-3 h-3 rounded-full border animate-spin inline-block" style={{ borderColor:'#fff',borderTopColor:'transparent' }}/> Saving…</> : editing ? '✓ Update' : '+ Create'}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
