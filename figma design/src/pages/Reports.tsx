import { useCallback, useEffect, useState } from 'react'
import GlassCard from '../components/GlassCard'
import { PermissionGuard } from '../components/PermissionGuard'
import { toast, confirmDanger } from '../lib/swal'
import {
  listReports, createReport, updateReport, deleteReport,
  type ReportRecord,
} from '../lib/api'

const inputStyle: React.CSSProperties = {
  background: 'rgba(255,255,255,0.04)',
  border: '1px solid var(--t-border-alpha)',
  color: 'var(--t-text)',
  outline: 'none',
}

const REPORT_TYPES = [
  'Network Summary', 'Device Inventory', 'Traffic Analysis', 'Alert Summary',
  'Uptime Report', 'Security Audit', 'Compliance Report', 'Performance Report',
  'Bandwidth Report', 'Incident Report', 'Custom',
]

const TYPE_ICONS: Record<string, string> = {
  'Network Summary':    '#00d4ff',
  'Device Inventory':  '#00ff88',
  'Traffic Analysis':  '#7c3aed',
  'Alert Summary':     '#ff3366',
  'Uptime Report':     '#00bfff',
  'Security Audit':    '#ff6644',
  'Compliance Report': '#ffaa00',
  'Performance Report':'#a78bfa',
  'Bandwidth Report':  '#00d4ff',
  'Incident Report':   '#ff3366',
  'Custom':            '#8899bb',
}

function typeColor(t: string) { return TYPE_ICONS[t] ?? 'var(--t-accent)' }

function StatusBadge({ type }: { type: string }) {
  const col = typeColor(type)
  return (
    <span className="font-mono text-[10px] px-2 py-0.5 rounded"
      style={{ background:`${col}18`, color:col, border:`1px solid ${col}44` }}>
      {type}
    </span>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="font-mono text-xs block mb-1" style={{ color:'var(--t-muted)' }}>{label}</label>
      {children}
    </div>
  )
}

export default function Reports() {
  const [reports,  setReports]  = useState<ReportRecord[]>([])
  const [loading,  setLoading]  = useState(true)
  const [showModal,setShowModal]= useState(false)
  const [editing,  setEditing]  = useState<ReportRecord|null>(null)
  const [saving,   setSaving]   = useState(false)
  const [search,   setSearch]   = useState('')
  const [fName,    setFName]    = useState('')
  const [fType,    setFType]    = useState(REPORT_TYPES[0])
  const [fPath,    setFPath]    = useState('')

  const load = useCallback(async () => {
    try { setReports(await listReports()) }
    catch (e) { toast.error(e instanceof Error ? e.message : 'Failed to load reports') }
    setLoading(false)
  }, [])

  useEffect(() => { void load() }, [load])

  function openCreate() { setEditing(null); setFName(''); setFType(REPORT_TYPES[0]); setFPath(''); setShowModal(true) }
  function openEdit(r: ReportRecord) { setEditing(r); setFName(r.report_name); setFType(r.report_type); setFPath(r.file_path??''); setShowModal(true) }

  async function handleSubmit() {
    if (!fName.trim()) { toast.warning('Report name is required'); return }
    setSaving(true)
    try {
      if (editing) {
        await updateReport(editing.id, { report_name:fName.trim(), report_type:fType, file_path:fPath.trim()||undefined })
        toast.success(`"${fName}" updated`)
      } else {
        await createReport({ report_name:fName.trim(), report_type:fType, file_path:fPath.trim()||undefined })
        toast.success(`"${fName}" created`)
      }
      setShowModal(false); await load()
    } catch (e) { toast.error(e instanceof Error ? e.message : 'Save failed') }
    setSaving(false)
  }

  async function handleDelete(r: ReportRecord) {
    const ok = await confirmDanger({
      title: `Delete "${r.report_name}"?`,
      text: 'This report record will be permanently removed.',
      confirmText: 'Delete Report',
    })
    if (!ok) return
    try {
      await deleteReport(r.id)
      toast.success(`"${r.report_name}" deleted`)
      await load()
    } catch (e) { toast.error(e instanceof Error ? e.message : 'Delete failed') }
  }

  const filtered = reports.filter(r =>
    !search.trim() ||
    r.report_name.toLowerCase().includes(search.toLowerCase()) ||
    r.report_type.toLowerCase().includes(search.toLowerCase())
  )

  if (loading) {
    return (
      <div className="p-6 flex items-center justify-center min-h-[50vh]">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 rounded-full border-2 animate-spin" style={{ borderColor:'var(--t-accent)',borderTopColor:'transparent' }}/>
          <span className="font-mono text-xs" style={{ color:'var(--t-muted)' }}>LOADING…</span>
        </div>
      </div>
    )
  }

  return (
    <div className="p-4 md:p-6 space-y-5">
      {/* header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="font-display font-bold text-xl md:text-2xl" style={{ color:'var(--t-text)' }}>Reports</h1>
          <p className="font-mono text-xs mt-1" style={{ color:'var(--t-muted)' }}>{reports.length} report{reports.length!==1?'s':''}</p>
        </div>
        <div className="flex gap-2">
          <input value={search} onChange={e=>setSearch(e.target.value)} placeholder="Search…"
            className="rounded-lg px-3 py-2 font-mono text-xs" style={{...inputStyle,minWidth:160}}
            onFocus={e=>{e.currentTarget.style.borderColor='var(--t-accent)'}}
            onBlur={e =>{e.currentTarget.style.borderColor='var(--t-border-alpha)'}}/>
          <PermissionGuard permission="reports:create">
            <button onClick={openCreate}
              className="rounded-lg px-4 py-2 font-display font-semibold text-sm flex items-center gap-2 hover:opacity-90 transition-all"
              style={{ background:'var(--t-accent)',color:'#fff',border:'1px solid var(--t-accent-border)' }}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><path d="M12 5v14M5 12h14"/></svg>
              New
            </button>
          </PermissionGuard>
        </div>
      </div>

      {/* table */}
      <GlassCard className="overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left" style={{ minWidth:540 }}>
            <thead>
              <tr style={{ borderBottom:'1px solid var(--t-border-light)' }}>
                {['Report Name','Type','Generated','File','Actions'].map(h=>(
                  <th key={h} className="px-4 py-3 font-mono text-xs uppercase tracking-wider" style={{ color:'var(--t-muted)' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.map(r=>(
                <tr key={r.id} style={{ borderBottom:'1px solid var(--t-border-alpha)' }}
                  onMouseEnter={e=>{(e.currentTarget as HTMLElement).style.background='rgba(0,212,255,0.03)'}}
                  onMouseLeave={e=>{(e.currentTarget as HTMLElement).style.background=''}}>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-3">
                      <div className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0"
                        style={{ background:`${typeColor(r.report_type)}18`, border:`1px solid ${typeColor(r.report_type)}44` }}>
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={typeColor(r.report_type)} strokeWidth="1.8" strokeLinecap="round">
                          <path d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>
                        </svg>
                      </div>
                      <span className="font-display font-medium text-sm" style={{ color:'var(--t-text)' }}>{r.report_name}</span>
                    </div>
                  </td>
                  <td className="px-4 py-3"><StatusBadge type={r.report_type}/></td>
                  <td className="px-4 py-3 font-mono text-xs" style={{ color:'var(--t-muted)' }}>
                    {new Date(r.generated_at).toLocaleString('en-IN',{timeZone:'Asia/Kolkata',hour12:true,day:'2-digit',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit'})}
                  </td>
                  <td className="px-4 py-3 font-mono text-xs" style={{ color:'var(--t-muted)' }}>
                    {r.file_path
                      ? <a href={r.file_path} target="_blank" rel="noreferrer"
                          className="flex items-center gap-1 hover:underline" style={{ color:'var(--t-accent)' }}>
                          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M10 13a5 5 0 007.54.54l3-3a5 5 0 00-7.07-7.07l-1.72 1.71M14 11a5 5 0 00-7.54-.54l-3 3a5 5 0 007.07 7.07l1.71-1.71"/></svg>
                          Link
                        </a>
                      : '—'}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex gap-1">
                      <PermissionGuard permission="reports:update">
                        <button onClick={()=>openEdit(r)} title="Edit"
                          className="p-1.5 rounded transition-colors" style={{ color:'var(--t-muted)' }}
                          onMouseEnter={e=>{e.currentTarget.style.color='var(--t-accent)'}}
                          onMouseLeave={e=>{e.currentTarget.style.color='var(--t-muted)'}}>
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                            <path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/>
                          </svg>
                        </button>
                      </PermissionGuard>
                      <PermissionGuard permission="reports:delete">
                        <button onClick={()=>handleDelete(r)} title="Delete"
                          className="p-1.5 rounded transition-colors" style={{ color:'var(--t-muted)' }}
                          onMouseEnter={e=>{e.currentTarget.style.color='#ff3366'}}
                          onMouseLeave={e=>{e.currentTarget.style.color='var(--t-muted)'}}>
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                            <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/>
                          </svg>
                        </button>
                      </PermissionGuard>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {filtered.length===0&&(
          <div className="py-12 text-center font-mono text-xs" style={{ color:'var(--t-muted)' }}>
            {search?`No reports match "${search}".`:'No reports yet. Create the first one.'}
          </div>
        )}
      </GlassCard>

      {/* modal */}
      {showModal&&(
        <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4" onClick={()=>setShowModal(false)}>
          <div className="glass rounded-xl p-6 w-full max-w-md shadow-2xl" style={{ border:'1px solid rgba(0,212,255,0.25)' }}
            onClick={e=>e.stopPropagation()}>
            <h3 className="font-display font-bold text-lg mb-5" style={{ color:'var(--t-accent)' }}>
              {editing?'✏ Edit Report':'+ New Report'}
            </h3>
            <div className="space-y-4">
              <Field label="REPORT NAME *">
                <input value={fName} onChange={e=>setFName(e.target.value)}
                  onKeyDown={e=>{if(e.key==='Enter')void handleSubmit()}}
                  autoFocus placeholder="e.g. Monthly Network Summary"
                  className="w-full rounded-lg px-3 py-2.5 font-mono text-sm" style={inputStyle}
                  onFocus={e=>{e.currentTarget.style.borderColor='var(--t-accent)'}}
                  onBlur={e =>{e.currentTarget.style.borderColor='var(--t-border-alpha)'}}/>
              </Field>
              <Field label="REPORT TYPE">
                <select value={fType} onChange={e=>setFType(e.target.value)}
                  className="w-full rounded-lg px-3 py-2.5 font-mono text-sm" style={inputStyle}
                  onFocus={e=>{e.currentTarget.style.borderColor='var(--t-accent)'}}
                  onBlur={e =>{e.currentTarget.style.borderColor='var(--t-border-alpha)'}}>
                  {REPORT_TYPES.map(t=><option key={t} value={t}>{t}</option>)}
                </select>
              </Field>
              <Field label="FILE PATH / URL (optional)">
                <input value={fPath} onChange={e=>setFPath(e.target.value)}
                  placeholder="/reports/monthly.pdf or https://…"
                  className="w-full rounded-lg px-3 py-2.5 font-mono text-sm" style={inputStyle}
                  onFocus={e=>{e.currentTarget.style.borderColor='var(--t-accent)'}}
                  onBlur={e =>{e.currentTarget.style.borderColor='var(--t-border-alpha)'}}/>
              </Field>
            </div>
            <div className="flex gap-2 justify-end mt-6">
              <button onClick={()=>setShowModal(false)}
                className="rounded-lg px-4 py-2 font-mono text-xs hover:opacity-80 transition-all"
                style={{ background:'rgba(255,255,255,0.05)',border:'1px solid var(--t-border-alpha)',color:'var(--t-muted)' }}>
                Cancel
              </button>
              <button onClick={()=>void handleSubmit()} disabled={saving||!fName.trim()}
                className="rounded-lg px-5 py-2 font-mono text-xs font-semibold disabled:opacity-50 flex items-center gap-2 transition-all"
                style={{ background:'var(--t-accent)',color:'#fff',border:'1px solid var(--t-accent-border)' }}>
                {saving?<><span className="w-3 h-3 rounded-full border animate-spin inline-block" style={{borderColor:'#fff',borderTopColor:'transparent'}}/> Saving…</>:editing?'✓ Update':'+ Create'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
