import { useCallback, useEffect, useState } from 'react'
import GlassCard from '../components/GlassCard'
import { PermissionGuard } from '../components/PermissionGuard'
import { toast, confirmDanger } from '../lib/swal'
import {
  listSites, createSite, updateSite, deleteSite,
  listOrganizations,
  type SiteRecord, type OrganizationRecord,
} from '../lib/api'

/* ── helpers ────────────────────────────────────────────────────────────── */
const inputStyle: React.CSSProperties = {
  background: 'var(--t-border-light, rgba(255,255,255,0.04))',
  border: '1px solid var(--t-border-alpha)',
  color: 'var(--t-text)',
  outline: 'none',
}

function Field({ label, required, children }: { label: string; required?: boolean; children: React.ReactNode }) {
  return (
    <div>
      <label className="font-mono text-xs block mb-1" style={{ color: 'var(--t-muted)' }}>
        {label}{required && <span style={{ color: '#ff3366' }}> *</span>}
      </label>
      {children}
    </div>
  )
}

function focus(e: React.FocusEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) {
  e.currentTarget.style.borderColor = 'var(--t-accent)'
}
function blur(e: React.FocusEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) {
  e.currentTarget.style.borderColor = 'var(--t-border-alpha)'
}

/* ── page ────────────────────────────────────────────────────────────────── */
export default function Sites() {
  const [sites,     setSites]     = useState<SiteRecord[]>([])
  const [orgs,      setOrgs]      = useState<OrganizationRecord[]>([])
  const [loading,   setLoading]   = useState(true)
  const [showModal, setShowModal] = useState(false)
  const [editing,   setEditing]   = useState<SiteRecord | null>(null)
  const [saving,    setSaving]    = useState(false)
  const [search,    setSearch]    = useState('')

  /* form state */
  const [fName,   setFName]   = useState('')
  const [fOrgId,  setFOrgId]  = useState<number | ''>('')
  const [fCity,   setFCity]   = useState('')
  const [fState,  setFState]  = useState('')

  /* ── load ─────────────────────────────────────────────────────────────── */
  const load = useCallback(async () => {
    try {
      const [s, o] = await Promise.all([listSites(), listOrganizations()])
      setSites(s)
      setOrgs(o)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to load sites')
    }
    setLoading(false)
  }, [])

  useEffect(() => { void load() }, [load])

  /* ── modal open ───────────────────────────────────────────────────────── */
  function openCreate() {
    setEditing(null)
    setFName(''); setFOrgId(orgs[0]?.id ?? ''); setFCity(''); setFState('')
    setShowModal(true)
  }

  function openEdit(site: SiteRecord) {
    setEditing(site)
    setFName(site.name)
    setFOrgId(site.organization_id)
    setFCity(site.city ?? '')
    setFState(site.state ?? '')
    setShowModal(true)
  }

  /* ── submit ───────────────────────────────────────────────────────────── */
  async function handleSubmit() {
    if (!fName.trim())   { toast.warning('Site name is required');         return }
    if (fOrgId === '')   { toast.warning('Please select an organization'); return }

    setSaving(true)
    try {
      const payload = {
        name:            fName.trim(),
        organization_id: Number(fOrgId),
        city:            fCity.trim()  || undefined,
        state:           fState.trim() || undefined,
      }
      if (editing) {
        await updateSite(editing.id, payload)
        toast.success(`"${fName}" updated`)
      } else {
        await createSite(payload)
        toast.success(`"${fName}" created`)
      }
      setShowModal(false)
      await load()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Save failed')
    }
    setSaving(false)
  }

  /* ── delete ───────────────────────────────────────────────────────────── */
  async function handleDelete(site: SiteRecord) {
    const ok = await confirmDanger({
      title:       `Delete "${site.name}"?`,
      text:        'Devices assigned to this site will become unassigned.',
      confirmText: 'Delete Site',
    })
    if (!ok) return
    try {
      await deleteSite(site.id)
      toast.success(`"${site.name}" deleted`)
      await load()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Delete failed')
    }
  }

  /* ── derived ──────────────────────────────────────────────────────────── */
  const orgMap = new Map(orgs.map(o => [o.id, o]))

  const filtered = sites.filter(s =>
    !search.trim() ||
    s.name.toLowerCase().includes(search.toLowerCase()) ||
    (s.city  ?? '').toLowerCase().includes(search.toLowerCase()) ||
    (s.state ?? '').toLowerCase().includes(search.toLowerCase()) ||
    (orgMap.get(s.organization_id)?.name ?? '').toLowerCase().includes(search.toLowerCase())
  )

  // Group sites by organization for a cleaner view
  const grouped = filtered.reduce<Record<number, SiteRecord[]>>((acc, s) => {
    (acc[s.organization_id] ??= []).push(s)
    return acc
  }, {})

  /* ── loading ──────────────────────────────────────────────────────────── */
  if (loading) {
    return (
      <div className="p-6 flex items-center justify-center min-h-[50vh]">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 rounded-full border-2 animate-spin"
            style={{ borderColor: 'var(--t-accent)', borderTopColor: 'transparent' }} />
          <span className="font-mono text-xs" style={{ color: 'var(--t-muted)' }}>LOADING…</span>
        </div>
      </div>
    )
  }

  /* ── render ───────────────────────────────────────────────────────────── */
  return (
    <div className="p-4 md:p-6 space-y-5">

      {/* header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="font-display font-bold text-xl md:text-2xl" style={{ color: 'var(--t-text)' }}>
            Sites
          </h1>
          <p className="font-mono text-xs mt-1" style={{ color: 'var(--t-muted)' }}>
            {sites.length} site{sites.length !== 1 ? 's' : ''} across {orgs.length} organization{orgs.length !== 1 ? 's' : ''}
          </p>
        </div>
        <div className="flex gap-2">
          <input
            value={search} onChange={e => setSearch(e.target.value)}
            placeholder="Search sites, city, org…"
            className="rounded-lg px-3 py-2 font-mono text-xs"
            style={{ ...inputStyle, minWidth: 180 }}
            onFocus={focus} onBlur={blur}
          />
          <PermissionGuard permission="sites:create">
            <button
              onClick={openCreate}
              disabled={orgs.length === 0}
              className="rounded-lg px-4 py-2 font-display font-semibold text-sm flex items-center gap-2 hover:opacity-90 transition-all disabled:opacity-50"
              style={{ background: 'var(--t-accent)', color: '#fff', border: '1px solid var(--t-accent-border)' }}
              title={orgs.length === 0 ? 'Create an organization first' : undefined}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                <path d="M12 5v14M5 12h14"/>
              </svg>
              New Site
            </button>
          </PermissionGuard>
        </div>
      </div>

      {/* no organizations notice */}
      {orgs.length === 0 && (
        <div className="rounded-xl p-4 font-mono text-xs"
          style={{ background: 'rgba(255,170,0,0.08)', border: '1px solid rgba(255,170,0,0.25)', color: '#ffaa00' }}>
          ⚠ No organizations exist yet. Go to <strong>Organizations</strong> and create one before adding sites.
        </div>
      )}

      {/* empty state */}
      {sites.length === 0 && orgs.length > 0 && (
        <GlassCard className="py-16 text-center">
          <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="var(--t-muted)" strokeWidth="1" className="mx-auto mb-3 opacity-40">
            <path d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z"/>
            <path d="M15 11a3 3 0 11-6 0 3 3 0 016 0z"/>
          </svg>
          <div className="font-mono text-xs" style={{ color: 'var(--t-muted)' }}>No sites yet. Create the first one.</div>
        </GlassCard>
      )}

      {/* grouped by organization */}
      {Object.keys(grouped).length > 0 && (
        <div className="space-y-6">
          {Object.entries(grouped).map(([orgIdStr, orgSites]) => {
            const orgId = Number(orgIdStr)
            const org   = orgMap.get(orgId)
            return (
              <div key={orgId}>
                {/* org label */}
                <div className="flex items-center gap-2 mb-3">
                  <div className="w-6 h-6 rounded-full flex items-center justify-center text-xs font-display font-bold shrink-0"
                    style={{ background: 'var(--t-accent-alpha)', color: 'var(--t-accent)', border: '1px solid var(--t-accent-border)' }}>
                    {(org?.name ?? 'O').charAt(0).toUpperCase()}
                  </div>
                  <span className="font-display font-semibold text-sm" style={{ color: 'var(--t-text)' }}>
                    {org?.name ?? `Organization #${orgId}`}
                  </span>
                  <span className="font-mono text-[10px] px-1.5 py-0.5 rounded"
                    style={{ background: 'var(--t-accent-alpha)', color: 'var(--t-accent)' }}>
                    {orgSites.length} site{orgSites.length !== 1 ? 's' : ''}
                  </span>
                </div>

                {/* site cards */}
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
                  {orgSites.map(site => (
                    <GlassCard key={site.id} className="p-4 group relative">
                      {/* icon */}
                      <div className="flex items-start gap-3 mb-3">
                        <div className="w-9 h-9 rounded-lg flex items-center justify-center shrink-0"
                          style={{ background: 'rgba(0,212,255,0.08)', border: '1px solid rgba(0,212,255,0.2)' }}>
                          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#00d4ff" strokeWidth="1.8" strokeLinecap="round">
                            <path d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z"/>
                            <path d="M15 11a3 3 0 11-6 0 3 3 0 016 0z"/>
                          </svg>
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="font-display font-semibold text-sm truncate" style={{ color: 'var(--t-text)' }}>
                            {site.name}
                          </div>
                          {(site.city || site.state) && (
                            <div className="font-mono text-[10px] truncate mt-0.5" style={{ color: 'var(--t-muted)' }}>
                              {[site.city, site.state].filter(Boolean).join(', ')}
                            </div>
                          )}
                        </div>
                      </div>

                      {/* site ID badge */}
                      <div className="font-mono text-[10px]" style={{ color: 'var(--t-muted)' }}>
                        ID: {site.id}
                      </div>

                      {/* action buttons — show on hover */}
                      <div className="absolute top-2 right-2 flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                        <PermissionGuard permission="sites:update">
                          <button onClick={() => openEdit(site)} title="Edit"
                            className="p-1.5 rounded transition-colors"
                            style={{ color: 'var(--t-muted)', background: 'rgba(0,0,0,0.4)' }}
                            onMouseEnter={e => { e.currentTarget.style.color = 'var(--t-accent)' }}
                            onMouseLeave={e => { e.currentTarget.style.color = 'var(--t-muted)' }}>
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                              <path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/>
                              <path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/>
                            </svg>
                          </button>
                        </PermissionGuard>
                        <PermissionGuard permission="sites:delete">
                          <button onClick={() => handleDelete(site)} title="Delete"
                            className="p-1.5 rounded transition-colors"
                            style={{ color: 'var(--t-muted)', background: 'rgba(0,0,0,0.4)' }}
                            onMouseEnter={e => { e.currentTarget.style.color = '#ff3366' }}
                            onMouseLeave={e => { e.currentTarget.style.color = 'var(--t-muted)' }}>
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                              <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/>
                            </svg>
                          </button>
                        </PermissionGuard>
                      </div>
                    </GlassCard>
                  ))}
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* no search results */}
      {filtered.length === 0 && sites.length > 0 && (
        <div className="py-8 text-center font-mono text-xs" style={{ color: 'var(--t-muted)' }}>
          No sites match "{search}"
        </div>
      )}

      {/* ── Create / Edit Modal ── */}
      {showModal && (
        <div
          className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4"
          onClick={() => setShowModal(false)}>
          <div
            className="glass rounded-xl p-6 w-full max-w-md shadow-2xl"
            style={{ border: '1px solid rgba(0,212,255,0.25)' }}
            onClick={e => e.stopPropagation()}>
            <h3 className="font-display font-bold text-lg mb-5" style={{ color: 'var(--t-accent)' }}>
              {editing ? '✏ Edit Site' : '+ New Site'}
            </h3>

            <div className="space-y-4">
              {/* Organization */}
              <Field label="ORGANIZATION" required>
                <select
                  value={fOrgId}
                  onChange={e => setFOrgId(Number(e.target.value))}
                  className="w-full rounded-lg px-3 py-2.5 font-mono text-sm"
                  style={inputStyle} onFocus={focus} onBlur={blur}>
                  <option value="">— Select organization —</option>
                  {orgs.map(o => <option key={o.id} value={o.id}>{o.name}</option>)}
                </select>
              </Field>

              {/* Site name */}
              <Field label="SITE NAME" required>
                <input
                  value={fName}
                  onChange={e => setFName(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter') void handleSubmit() }}
                  autoFocus
                  placeholder="e.g. Mumbai HQ"
                  className="w-full rounded-lg px-3 py-2.5 font-mono text-sm"
                  style={inputStyle} onFocus={focus} onBlur={blur}/>
              </Field>

              {/* City + State */}
              <div className="grid grid-cols-2 gap-3">
                <Field label="CITY">
                  <input
                    value={fCity}
                    onChange={e => setFCity(e.target.value)}
                    placeholder="Mumbai"
                    className="w-full rounded-lg px-3 py-2.5 font-mono text-sm"
                    style={inputStyle} onFocus={focus} onBlur={blur}/>
                </Field>
                <Field label="STATE / REGION">
                  <input
                    value={fState}
                    onChange={e => setFState(e.target.value)}
                    placeholder="Maharashtra"
                    className="w-full rounded-lg px-3 py-2.5 font-mono text-sm"
                    style={inputStyle} onFocus={focus} onBlur={blur}/>
                </Field>
              </div>
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
                disabled={saving || !fName.trim() || fOrgId === ''}
                className="rounded-lg px-5 py-2 font-mono text-xs font-semibold transition-all disabled:opacity-50 flex items-center gap-2"
                style={{ background: 'var(--t-accent)', color: '#fff', border: '1px solid var(--t-accent-border)' }}>
                {saving
                  ? <><span className="w-3 h-3 rounded-full border animate-spin inline-block"
                      style={{ borderColor: '#fff', borderTopColor: 'transparent' }}/> Saving…</>
                  : editing ? '✓ Update Site' : '+ Create Site'
                }
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
