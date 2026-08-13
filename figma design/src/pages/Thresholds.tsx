import { useCallback, useEffect, useState } from 'react'
import GlassCard from '../components/GlassCard'
import { PermissionGuard } from '../components/PermissionGuard'
import { toast, confirmDanger } from '../lib/swal'
import { listThresholds, createThreshold, updateThreshold, deleteThreshold, type ThresholdRecord } from '../lib/api'

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (<div><label className="font-mono text-xs block mb-1" style={{ color: 'var(--t-muted)' }}>{label}</label>{children}</div>)
}

const inputStyle: React.CSSProperties = {
  background: 'rgba(255,255,255,0.04)',
  border: '1px solid var(--t-border-alpha)',
  color: 'var(--t-text)',
  outline: 'none',
}

export default function Thresholds() {
  const [items, setItems] = useState<ThresholdRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [showModal, setShowModal] = useState(false)
  const [editing, setEditing] = useState<ThresholdRecord | null>(null)
  const [saving, setSaving] = useState(false)
  const [search, setSearch] = useState('')
  const [fMetric, setFMetric] = useState('')
  const [fValue, setFValue] = useState('')
  const [fCondition, setFCondition] = useState('>')
  const [fSeverity, setFSeverity] = useState('warning')
  const [fDesc, setFDesc] = useState('')

  const load = useCallback(async () => {
    try { setItems(await listThresholds()) } catch (e) { toast.error(e instanceof Error ? e.message : 'Failed to load') }
    setLoading(false)
  }, [])

  useEffect(() => { void load() }, [load])

  function openCreate() {
    setEditing(null); setFMetric(''); setFValue(''); setFCondition('>'); setFSeverity('warning'); setFDesc(''); setShowModal(true)
  }
  function openEdit(item: ThresholdRecord) {
    setEditing(item); setFMetric(item.metric_name); setFValue(String(item.threshold_value)); setFCondition(item.condition); setFSeverity(item.severity); setFDesc(item.description ?? ''); setShowModal(true)
  }

  async function handleSubmit() {
    if (!fMetric.trim() || !fValue.trim()) { toast.warning('Metric and value required'); return }
    setSaving(true)
    try {
      const data = { metric_name: fMetric.trim(), threshold_value: Number(fValue), condition: fCondition, severity: fSeverity, description: fDesc.trim() || null }
      if (editing) {
        await updateThreshold(editing.id, data)
        toast.success('Updated')
      } else {
        await createThreshold(data)
        toast.success('Created')
      }
      setShowModal(false)
      await load()
    } catch (e) { toast.error(e instanceof Error ? e.message : 'Save failed') }
    setSaving(false)
  }

  async function handleDelete(item: ThresholdRecord) {
    const ok = await confirmDanger({ title: `Delete threshold?`, text: 'Cannot be undone.', confirmText: 'Delete' })
    if (!ok) return
    try { await deleteThreshold(item.id); toast.success('Deleted'); await load() } catch (e) { toast.error(e instanceof Error ? e.message : 'Delete failed') }
  }

  const filtered = items.filter(i => !search.trim() || i.metric_name.toLowerCase().includes(search.toLowerCase()) || i.severity.toLowerCase().includes(search.toLowerCase()))

  if (loading) {
    return (<div className="p-6 flex items-center justify-center min-h-[50vh]"><div className="flex flex-col items-center gap-3"><div className="w-8 h-8 rounded-full border-2 animate-spin" style={{ borderColor: 'var(--t-accent)', borderTopColor: 'transparent' }} /><span className="font-mono text-xs" style={{ color: 'var(--t-muted)' }}>LOADING…</span></div></div>)
  }

  return (
    <div className="p-4 md:p-6 space-y-5">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div><h1 className="font-display font-bold text-xl md:text-2xl" style={{ color: 'var(--t-text)' }}>Thresholds</h1><p className="font-mono text-xs mt-1" style={{ color: 'var(--t-muted)' }}>{items.length} threshold{items.length !== 1 ? 's' : ''}</p></div>
        <div className="flex gap-2">
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search…" className="rounded-lg px-3 py-2 font-mono text-xs" style={{ ...inputStyle, minWidth: 160 }} onFocus={e => { e.currentTarget.style.borderColor = 'var(--t-accent)' }} onBlur={e => { e.currentTarget.style.borderColor = 'var(--t-border-alpha)' }} />
          <PermissionGuard permission="thresholds:create"><button onClick={openCreate} className="rounded-lg px-4 py-2 font-display font-semibold text-sm flex items-center gap-2 hover:opacity-90 transition-all" style={{ background: 'var(--t-accent)', color: '#fff', border: '1px solid var(--t-accent-border)' }}><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><path d="M12 5v14M5 12h14"/></svg>New</button></PermissionGuard>
        </div>
      </div>

      <GlassCard className="overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left" style={{ minWidth: 640 }}>
            <thead><tr style={{ borderBottom: '1px solid var(--t-border-light)' }}>{['Metric', 'Condition', 'Value', 'Severity', 'Actions'].map(h => (<th key={h} className="px-4 py-3 font-mono text-xs uppercase tracking-wider" style={{ color: 'var(--t-muted)' }}>{h}</th>))}</tr></thead>
            <tbody>
              {filtered.map(item => (
                <tr key={item.id} style={{ borderBottom: '1px solid var(--t-border-alpha)' }} onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = 'rgba(0,212,255,0.03)' }} onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = '' }}>
                  <td className="px-4 py-3 font-display font-medium text-sm" style={{ color: 'var(--t-text)' }}>{item.metric_name}</td>
                  <td className="px-4 py-3 font-mono text-xs" style={{ color: 'var(--t-muted)' }}>{item.condition}</td>
                  <td className="px-4 py-3 font-mono text-xs" style={{ color: 'var(--t-muted)' }}>{item.threshold_value}</td>
                  <td className="px-4 py-3 font-mono text-xs" style={{ color: 'var(--t-muted)' }}>{item.severity}</td>
                  <td className="px-4 py-3">
                    <div className="flex gap-1">
                      <PermissionGuard permission="thresholds:update"><button onClick={() => openEdit(item)} title="Edit" className="p-1.5 rounded transition-colors" style={{ color: 'var(--t-muted)' }} onMouseEnter={e => { e.currentTarget.style.color = 'var(--t-accent)' }} onMouseLeave={e => { e.currentTarget.style.color = 'var(--t-muted)' }}><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/></svg></button></PermissionGuard>
                      <PermissionGuard permission="thresholds:delete"><button onClick={() => handleDelete(item)} title="Delete" className="p-1.5 rounded transition-colors" style={{ color: 'var(--t-muted)' }} onMouseEnter={e => { e.currentTarget.style.color = '#ff3366' }} onMouseLeave={e => { e.currentTarget.style.color = 'var(--t-muted)' }}><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/></svg></button></PermissionGuard>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {filtered.length === 0 && (<div className="py-12 text-center font-mono text-xs" style={{ color: 'var(--t-muted)' }}>{search ? 'No matches.' : 'No thresholds yet.'}</div>)}
      </GlassCard>

      {showModal && (
        <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4" onClick={() => setShowModal(false)}>
          <div className="glass rounded-xl p-6 w-full max-w-md shadow-2xl" style={{ border: '1px solid rgba(0,212,255,0.25)' }} onClick={e => e.stopPropagation()}>
            <h3 className="font-display font-bold text-lg mb-4" style={{ color: 'var(--t-accent)' }}>{editing ? '✏ Edit Threshold' : '+ New Threshold'}</h3>
            <div className="space-y-4">
              <Field label="METRIC *"><input value={fMetric} onChange={e => setFMetric(e.target.value)} autoFocus placeholder="cpu_usage" className="w-full rounded-lg px-3 py-2.5 font-mono text-sm" style={inputStyle} onFocus={e => { e.currentTarget.style.borderColor = 'var(--t-accent)' }} onBlur={e => { e.currentTarget.style.borderColor = 'var(--t-border-alpha)' }}/></Field>
              <Field label="CONDITION"><select value={fCondition} onChange={e => setFCondition(e.target.value)} className="w-full rounded-lg px-3 py-2.5 font-mono text-sm" style={inputStyle}><option value=">">{'>'}</option><option value="<">{'<'}</option><option value=">=">{'>='}</option><option value="<=">{'<='}</option><option value="==">==</option></select></Field>
              <Field label="VALUE *"><input value={fValue} onChange={e => setFValue(e.target.value)} type="number" placeholder="80" className="w-full rounded-lg px-3 py-2.5 font-mono text-sm" style={inputStyle} onFocus={e => { e.currentTarget.style.borderColor = 'var(--t-accent)' }} onBlur={e => { e.currentTarget.style.borderColor = 'var(--t-border-alpha)' }}/></Field>
              <Field label="SEVERITY"><select value={fSeverity} onChange={e => setFSeverity(e.target.value)} className="w-full rounded-lg px-3 py-2.5 font-mono text-sm" style={inputStyle}><option value="info">Info</option><option value="warning">Warning</option><option value="high">High</option><option value="critical">Critical</option></select></Field>
              <Field label="DESCRIPTION"><textarea value={fDesc} onChange={e => setFDesc(e.target.value)} rows={2} placeholder="Optional…" className="w-full rounded-lg px-3 py-2.5 font-mono text-sm resize-none" style={inputStyle} onFocus={e => { e.currentTarget.style.borderColor = 'var(--t-accent)' }} onBlur={e => { e.currentTarget.style.borderColor = 'var(--t-border-alpha)' }}/></Field>
            </div>
            <div className="flex gap-2 justify-end mt-6">
              <button onClick={() => setShowModal(false)} className="rounded-lg px-4 py-2 font-mono text-xs hover:opacity-80 transition-all" style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid var(--t-border-alpha)', color: 'var(--t-muted)' }}>Cancel</button>
              <button onClick={() => void handleSubmit()} disabled={saving || !fMetric.trim() || !fValue.trim()} className="rounded-lg px-5 py-2 font-mono text-xs font-semibold transition-all disabled:opacity-50 flex items-center gap-2" style={{ background: 'var(--t-accent)', color: '#fff', border: '1px solid var(--t-accent-border)' }}>{saving ? <><span className="w-3 h-3 rounded-full border animate-spin inline-block" style={{ borderColor:'#fff',borderTopColor:'transparent' }}/> Saving…</> : editing ? '✓ Update' : '+ Create'}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
