import { useCallback, useEffect, useState } from 'react'
import GlassCard from '../components/GlassCard'
import { PermissionGuard } from '../components/PermissionGuard'
import { toast, confirmDanger } from '../lib/swal'
import {
  listVendors, createVendor, updateVendor, deleteVendor,
  type VendorRecord,
} from '../lib/api'

const inputStyle: React.CSSProperties = {
  background: 'var(--t-border-light, rgba(255,255,255,0.04))',
  border: '1px solid var(--t-border-alpha)',
  color: 'var(--t-text)',
  outline: 'none',
}

// Well-known vendor brand colors for visual flair
const VENDOR_COLORS: Record<string, string> = {
  cisco: '#00d4ff', fortinet: '#ee4444', huawei: '#ff3366',
  juniper: '#00bfff', 'palo alto': '#ff6a00', mikrotik: '#a78bfa',
  sophos: '#ffaa00', vmware: '#00c853', arista: '#00ff88', hp: '#0096d6',
  dell: '#007db8', aruba: '#ff8c00', ubiquiti: '#00d4ff', f5: '#e63946',
  'check point': '#ff3366', agnigate: '#00d4ff',
}

function vendorColor(name: string): string {
  const lower = name.toLowerCase()
  for (const [key, color] of Object.entries(VENDOR_COLORS)) {
    if (lower.includes(key)) return color
  }
  return 'var(--t-accent)'
}

export default function Vendors() {
  const [vendors,   setVendors]   = useState<VendorRecord[]>([])
  const [loading,   setLoading]   = useState(true)
  const [showModal, setShowModal] = useState(false)
  const [editing,   setEditing]   = useState<VendorRecord | null>(null)
  const [saving,    setSaving]    = useState(false)
  const [search,    setSearch]    = useState('')
  const [fName,     setFName]     = useState('')

  const load = useCallback(async () => {
    try { setVendors(await listVendors()) }
    catch (e) { toast.error(e instanceof Error ? e.message : 'Failed to load vendors') }
    setLoading(false)
  }, [])

  useEffect(() => { void load() }, [load])

  function openCreate() { setEditing(null); setFName(''); setShowModal(true) }
  function openEdit(v: VendorRecord) { setEditing(v); setFName(v.vendor_name); setShowModal(true) }

  async function handleSubmit() {
    if (!fName.trim()) { toast.warning('Vendor name is required'); return }
    setSaving(true)
    try {
      if (editing) {
        await updateVendor(editing.id, { vendor_name: fName.trim() })
        toast.success(`"${fName}" updated`)
      } else {
        await createVendor({ vendor_name: fName.trim() })
        toast.success(`"${fName}" added`)
      }
      setShowModal(false); await load()
    } catch (e) { toast.error(e instanceof Error ? e.message : 'Save failed') }
    setSaving(false)
  }

  async function handleDelete(v: VendorRecord) {
    const ok = await confirmDanger({
      title: `Remove "${v.vendor_name}"?`,
      text: 'Devices assigned to this vendor will become unassigned.',
      confirmText: 'Delete Vendor',
    })
    if (!ok) return
    try {
      await deleteVendor(v.id)
      toast.success(`"${v.vendor_name}" removed`)
      await load()
    } catch (e) { toast.error(e instanceof Error ? e.message : 'Delete failed') }
  }

  const filtered = vendors.filter(v =>
    !search.trim() || v.vendor_name.toLowerCase().includes(search.toLowerCase())
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
          <h1 className="font-display font-bold text-xl md:text-2xl" style={{ color:'var(--t-text)' }}>Vendors</h1>
          <p className="font-mono text-xs mt-1" style={{ color:'var(--t-muted)' }}>{vendors.length} vendor{vendors.length!==1?'s':''}</p>
        </div>
        <div className="flex gap-2">
          <input value={search} onChange={e=>setSearch(e.target.value)} placeholder="Search…"
            className="rounded-lg px-3 py-2 font-mono text-xs" style={{...inputStyle,minWidth:160}}
            onFocus={e=>{e.currentTarget.style.borderColor='var(--t-accent)'}}
            onBlur={e =>{e.currentTarget.style.borderColor='var(--t-border-alpha)'}}/>
          <PermissionGuard permission="vendors:create">
            <button onClick={openCreate}
              className="rounded-lg px-4 py-2 font-display font-semibold text-sm flex items-center gap-2 hover:opacity-90 transition-all"
              style={{ background:'var(--t-accent)',color:'#fff',border:'1px solid var(--t-accent-border)' }}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><path d="M12 5v14M5 12h14"/></svg>
              New
            </button>
          </PermissionGuard>
        </div>
      </div>

      {/* card grid */}
      {filtered.length === 0 ? (
        <GlassCard className="py-16 text-center font-mono text-xs" style={{ color:'var(--t-muted)' }}>
          {search ? `No vendors match "${search}".` : 'No vendors yet. Add the first one.'}
        </GlassCard>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-3">
          {filtered.map(v => {
            const col = vendorColor(v.vendor_name)
            return (
              <GlassCard key={v.id} className="p-4 flex flex-col items-center gap-3 text-center group relative">
                {/* avatar */}
                <div className="w-12 h-12 rounded-xl flex items-center justify-center text-xl font-display font-bold"
                  style={{ background:`${col}18`, border:`1px solid ${col}44`, color:col }}>
                  {v.vendor_name.charAt(0).toUpperCase()}
                </div>
                <div className="font-display font-medium text-sm leading-tight" style={{ color:'var(--t-text)' }}>
                  {v.vendor_name}
                </div>
                {/* actions — appear on hover */}
                <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity absolute top-2 right-2">
                  <PermissionGuard permission="vendors:update">
                    <button onClick={() => openEdit(v)} title="Edit"
                      className="p-1 rounded transition-colors" style={{ color:'var(--t-muted)' }}
                      onMouseEnter={e=>{e.currentTarget.style.color='var(--t-accent)'}}
                      onMouseLeave={e=>{e.currentTarget.style.color='var(--t-muted)'}}>
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                        <path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/>
                      </svg>
                    </button>
                  </PermissionGuard>
                  <PermissionGuard permission="vendors:delete">
                    <button onClick={() => handleDelete(v)} title="Delete"
                      className="p-1 rounded transition-colors" style={{ color:'var(--t-muted)' }}
                      onMouseEnter={e=>{e.currentTarget.style.color='#ff3366'}}
                      onMouseLeave={e=>{e.currentTarget.style.color='var(--t-muted)'}}>
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                        <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/>
                      </svg>
                    </button>
                  </PermissionGuard>
                </div>
              </GlassCard>
            )
          })}
        </div>
      )}

      {/* modal */}
      {showModal && (
        <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4" onClick={()=>setShowModal(false)}>
          <div className="glass rounded-xl p-6 w-full max-w-sm shadow-2xl" style={{ border:'1px solid rgba(0,212,255,0.25)' }}
            onClick={e=>e.stopPropagation()}>
            <h3 className="font-display font-bold text-lg mb-4" style={{ color:'var(--t-accent)' }}>
              {editing?'✏ Edit Vendor':'+ New Vendor'}
            </h3>
            <label className="font-mono text-xs block mb-1.5" style={{ color:'var(--t-muted)' }}>VENDOR NAME *</label>
            <input value={fName} onChange={e=>setFName(e.target.value)}
              onKeyDown={e=>{if(e.key==='Enter')void handleSubmit()}}
              autoFocus placeholder="e.g. Cisco Systems"
              className="w-full rounded-lg px-3 py-2.5 font-mono text-sm mb-5" style={inputStyle}
              onFocus={e=>{e.currentTarget.style.borderColor='var(--t-accent)'}}
              onBlur={e =>{e.currentTarget.style.borderColor='var(--t-border-alpha)'}}/>
            <div className="flex gap-2 justify-end">
              <button onClick={()=>setShowModal(false)}
                className="rounded-lg px-4 py-2 font-mono text-xs hover:opacity-80 transition-all"
                style={{ background:'var(--t-border-light, rgba(255,255,255,0.05))',border:'1px solid var(--t-border-alpha)',color:'var(--t-muted)' }}>
                Cancel
              </button>
              <button onClick={()=>void handleSubmit()} disabled={saving||!fName.trim()}
                className="rounded-lg px-5 py-2 font-mono text-xs font-semibold disabled:opacity-50 flex items-center gap-2 transition-all"
                style={{ background:'var(--t-accent)',color:'#fff',border:'1px solid var(--t-accent-border)' }}>
                {saving?<><span className="w-3 h-3 rounded-full border animate-spin inline-block" style={{borderColor:'#fff',borderTopColor:'transparent'}}/> Saving…</>:editing?'✓ Update':'+ Add'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
