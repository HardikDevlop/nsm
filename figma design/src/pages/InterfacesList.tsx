import { useCallback, useEffect, useState } from 'react'
import GlassCard from '../components/GlassCard'
import { PermissionGuard } from '../components/PermissionGuard'
import TablePagination from '../components/TablePagination'
import { useDeferredSearch } from '../hooks/useDeferredSearch'
import { useTablePagination } from '../hooks/useTablePagination'
import { toast, confirmDanger } from '../lib/swal'
import { listInterfaces, createInterface, updateInterface, deleteInterface, listDeviceOptions, type InterfaceRecord, type DeviceOptionRecord } from '../lib/api'

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (<div><label className="font-mono text-xs block mb-1" style={{ color: 'var(--t-muted)' }}>{label}</label>{children}</div>)
}

const inputStyle: React.CSSProperties = { background: 'var(--t-border-light, rgba(255,255,255,0.04))', border: '1px solid var(--t-border-alpha)', color: 'var(--t-text)', outline: 'none' }

export default function InterfacesList() {
  const [items, setItems] = useState<InterfaceRecord[]>([])
  const [devices, setDevices] = useState<DeviceOptionRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [showModal, setShowModal] = useState(false)
  const [editing, setEditing] = useState<InterfaceRecord | null>(null)
  const [saving, setSaving] = useState(false)
  const { search, setSearch, normalizedSearch } = useDeferredSearch()
  const [fDeviceId, setFDeviceId] = useState<number>(0)
  const [fName, setFName] = useState('')
  const [fStatus, setFStatus] = useState('up')
  const [fSpeed, setFSpeed] = useState('')

  const load = useCallback(async () => {
    try {
      const [intData, devData] = await Promise.all([listInterfaces(), listDeviceOptions()])
      setItems(intData)
      setDevices(devData)
    } catch (e) { toast.error(e instanceof Error ? e.message : 'Failed to load') }
    setLoading(false)
  }, [])

  useEffect(() => { void load() }, [load])

  function openCreate() { setEditing(null); setFDeviceId(devices[0]?.id || 0); setFName(''); setFStatus('up'); setFSpeed(''); setShowModal(true) }
  function openEdit(item: InterfaceRecord) { setEditing(item); setFDeviceId(item.device_id); setFName(item.interface_name); setFStatus(item.status); setFSpeed(item.speed ?? ''); setShowModal(true) }

  async function handleSubmit() {
    if (!fDeviceId || !fName.trim()) { toast.warning('Device and name required'); return }
    setSaving(true)
    try {
      const data: any = { device_id: fDeviceId, interface_name: fName.trim(), status: fStatus, speed: fSpeed.trim() || null, traffic_in: 0, traffic_out: 0, packet_errors: 0 }
      if (editing) {
        await updateInterface(editing.id, data)
        toast.success('Updated')
      } else {
        await createInterface(data)
        toast.success('Created')
      }
      setShowModal(false)
      await load()
    } catch (e) { toast.error(e instanceof Error ? e.message : 'Save failed') }
    setSaving(false)
  }

  async function handleDelete(item: InterfaceRecord) {
    const ok = await confirmDanger({ title: `Delete interface "${item.interface_name}"?`, text: 'Cannot be undone.', confirmText: 'Delete' })
    if (!ok) return
    try { await deleteInterface(item.id); toast.success('Deleted'); await load() } catch (e) { toast.error(e instanceof Error ? e.message : 'Delete failed') }
  }

  const filtered = items.filter(i => !normalizedSearch || i.interface_name.toLowerCase().includes(normalizedSearch))
  const deviceMap = new Map(devices.map(device => [device.id, device]))
  const pagination = useTablePagination(filtered)

  if (loading) {
    return (<div className="p-6 flex items-center justify-center min-h-[50vh]"><div className="flex flex-col items-center gap-3"><div className="w-8 h-8 rounded-full border-2 animate-spin" style={{ borderColor: 'var(--t-accent)', borderTopColor: 'transparent' }} /><span className="font-mono text-xs" style={{ color: 'var(--t-muted)' }}>LOADING…</span></div></div>)
  }

  return (
    <div className="p-4 md:p-6 space-y-5">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div><h1 className="font-display font-bold text-xl md:text-2xl" style={{ color: 'var(--t-text)' }}>Network Interfaces</h1><p className="font-mono text-xs mt-1" style={{ color: 'var(--t-muted)' }}>{items.length} interface{items.length !== 1 ? 's' : ''}</p></div>
        <div className="flex gap-2">
          <input value={search} onChange={e => { setSearch(e.target.value); pagination.setPage(1) }} placeholder="Search…" className="rounded-lg px-3 py-2 font-mono text-xs" style={{ ...inputStyle, minWidth: 160 }} onFocus={e => { e.currentTarget.style.borderColor = 'var(--t-accent)' }} onBlur={e => { e.currentTarget.style.borderColor = 'var(--t-border-alpha)' }} />
          <PermissionGuard permission="interfaces:create"><button onClick={openCreate} className="rounded-lg px-4 py-2 font-display font-semibold text-sm flex items-center gap-2 hover:opacity-90 transition-all" style={{ background: 'var(--t-accent)', color: '#fff', border: '1px solid var(--t-accent-border)' }}><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><path d="M12 5v14M5 12h14"/></svg>New</button></PermissionGuard>
        </div>
      </div>

      <GlassCard className="overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left" style={{ minWidth: 800 }}>
            <thead><tr style={{ borderBottom: '1px solid var(--t-border-light)' }}>{['Interface', 'Device', 'Status', 'Speed', 'Traffic In', 'Traffic Out', 'Errors', 'Actions'].map(h => (<th key={h} className="px-4 py-3 font-mono text-xs uppercase tracking-wider" style={{ color: 'var(--t-muted)' }}>{h}</th>))}</tr></thead>
            <tbody>
              {pagination.paginatedItems.map(item => {
                const device = deviceMap.get(item.device_id)
                return (
                  <tr key={item.id} style={{ borderBottom: '1px solid var(--t-border-alpha)' }} onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = 'rgba(0,212,255,0.03)' }} onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = '' }}>
                    <td className="px-4 py-3 font-display font-medium text-sm" style={{ color: 'var(--t-text)' }}>{item.interface_name}</td>
                    <td className="px-4 py-3 font-mono text-xs" style={{ color: 'var(--t-muted)' }}>{device ? device.hostname : '—'}</td>
                    <td className="px-4 py-3"><span className="px-2 py-1 rounded text-xs font-mono" style={{ background: item.status === 'up' ? 'rgba(74,222,128,0.2)' : 'rgba(255,51,102,0.2)', color: item.status === 'up' ? '#4ade80' : '#ff3366' }}>{item.status.toUpperCase()}</span></td>
                    <td className="px-4 py-3 font-mono text-xs" style={{ color: 'var(--t-muted)' }}>{item.speed || '—'}</td>
                    <td className="px-4 py-3 font-mono text-xs" style={{ color: 'var(--t-muted)' }}>{item.traffic_in.toFixed(2)} MB</td>
                    <td className="px-4 py-3 font-mono text-xs" style={{ color: 'var(--t-muted)' }}>{item.traffic_out.toFixed(2)} MB</td>
                    <td className="px-4 py-3 font-mono text-xs" style={{ color: item.packet_errors > 0 ? '#ff3366' : 'var(--t-muted)' }}>{item.packet_errors}</td>
                    <td className="px-4 py-3">
                      <div className="flex gap-1">
                        <PermissionGuard permission="interfaces:update"><button onClick={() => openEdit(item)} title="Edit" className="p-1.5 rounded transition-colors" style={{ color: 'var(--t-muted)' }} onMouseEnter={e => { e.currentTarget.style.color = 'var(--t-accent)' }} onMouseLeave={e => { e.currentTarget.style.color = 'var(--t-muted)' }}><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/></svg></button></PermissionGuard>
                        <PermissionGuard permission="interfaces:delete"><button onClick={() => handleDelete(item)} title="Delete" className="p-1.5 rounded transition-colors" style={{ color: 'var(--t-muted)' }} onMouseEnter={e => { e.currentTarget.style.color = '#ff3366' }} onMouseLeave={e => { e.currentTarget.style.color = 'var(--t-muted)' }}><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/></svg></button></PermissionGuard>
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
        {filtered.length === 0 && (<div className="py-12 text-center font-mono text-xs" style={{ color: 'var(--t-muted)' }}>{search ? 'No matches.' : 'No interfaces yet.'}</div>)}
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
            <h3 className="font-display font-bold text-lg mb-4" style={{ color: 'var(--t-accent)' }}>{editing ? '✏ Edit Interface' : '+ New Interface'}</h3>
            <div className="space-y-4">
              <Field label="DEVICE *"><select value={fDeviceId} onChange={e => setFDeviceId(Number(e.target.value))} className="w-full rounded-lg px-3 py-2.5 font-mono text-sm" style={inputStyle}>{devices.map(d => (<option key={d.id} value={d.id}>{d.hostname}</option>))}</select></Field>
              <Field label="INTERFACE NAME *"><input value={fName} onChange={e => setFName(e.target.value)} autoFocus placeholder="eth0" className="w-full rounded-lg px-3 py-2.5 font-mono text-sm" style={inputStyle} onFocus={e => { e.currentTarget.style.borderColor = 'var(--t-accent)' }} onBlur={e => { e.currentTarget.style.borderColor = 'var(--t-border-alpha)' }}/></Field>
              <Field label="STATUS"><select value={fStatus} onChange={e => setFStatus(e.target.value)} className="w-full rounded-lg px-3 py-2.5 font-mono text-sm" style={inputStyle}><option value="up">Up</option><option value="down">Down</option></select></Field>
              <Field label="SPEED"><input value={fSpeed} onChange={e => setFSpeed(e.target.value)} placeholder="1 Gbps" className="w-full rounded-lg px-3 py-2.5 font-mono text-sm" style={inputStyle} onFocus={e => { e.currentTarget.style.borderColor = 'var(--t-accent)' }} onBlur={e => { e.currentTarget.style.borderColor = 'var(--t-border-alpha)' }}/></Field>
            </div>
            <div className="flex gap-2 justify-end mt-6">
              <button onClick={() => setShowModal(false)} className="rounded-lg px-4 py-2 font-mono text-xs hover:opacity-80 transition-all" style={{ background: 'var(--t-border-light, rgba(255,255,255,0.05))', border: '1px solid var(--t-border-alpha)', color: 'var(--t-muted)' }}>Cancel</button>
              <button onClick={() => void handleSubmit()} disabled={saving || !fDeviceId || !fName.trim()} className="rounded-lg px-5 py-2 font-mono text-xs font-semibold transition-all disabled:opacity-50 flex items-center gap-2" style={{ background: 'var(--t-accent)', color: '#fff', border: '1px solid var(--t-accent-border)' }}>{saving ? <><span className="w-3 h-3 rounded-full border animate-spin inline-block" style={{ borderColor:'#fff',borderTopColor:'transparent' }}/> Saving…</> : editing ? '✓ Update' : '+ Create'}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
