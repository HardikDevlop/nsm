import { useEffect, useState, useCallback } from 'react'
import GlassCard from '../components/GlassCard'
import { PermissionGuard } from '../components/PermissionGuard'
import { toast, confirmDanger } from '../lib/swal'
import {
  listRoles, createRole, updateRole, deleteRole,
  getRolePermissions, setRolePermissions,
  listPermissions,
  type RoleRecord, type PermissionRecord, type RoleWithPermissions,
} from '../lib/api'

export default function RoleManagement() {
  const [roles,          setRoles]          = useState<RoleRecord[]>([])
  const [allPerms,       setAllPerms]       = useState<PermissionRecord[]>([])
  const [selectedRole,   setSelectedRole]   = useState<RoleWithPermissions | null>(null)
  const [selectedIds,    setSelectedIds]    = useState<Set<number>>(new Set())
  const [search,         setSearch]         = useState('')
  const [loading,        setLoading]        = useState(true)
  const [savingPerms,    setSavingPerms]    = useState(false)
  const [showModal,      setShowModal]      = useState(false)
  const [editingRole,    setEditingRole]    = useState<RoleRecord | null>(null)
  const [modalName,      setModalName]      = useState('')
  const [modalSaving,    setModalSaving]    = useState(false)

  /* ── load ──────────────────────────────────────────────────────────────── */
  const load = useCallback(async () => {
    try {
      const [r, p] = await Promise.all([listRoles(), listPermissions()])
      setRoles(r)
      setAllPerms(p)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to load roles')
    }
    setLoading(false)
  }, [])

  useEffect(() => { void load() }, [load])

  /* ── select role → load its permissions ───────────────────────────────── */
  async function handleSelectRole(role: RoleRecord) {
    try {
      const rw = await getRolePermissions(role.id)
      setSelectedRole(rw)
      setSelectedIds(new Set(rw.permissions.map(p => p.id)))
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to load permissions')
    }
  }

  /* ── toggle helpers ────────────────────────────────────────────────────── */
  function togglePerm(id: number) {
    setSelectedIds(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id); else next.add(id)
      return next
    })
  }

  function toggleModule(mod: string) {
    const modPerms = allPerms.filter(p => p.module === mod)
    const allSel   = modPerms.every(p => selectedIds.has(p.id))
    setSelectedIds(prev => {
      const next = new Set(prev)
      if (allSel) modPerms.forEach(p => next.delete(p.id))
      else        modPerms.forEach(p => next.add(p.id))
      return next
    })
  }

  function toggleAll() {
    if (selectedIds.size === allPerms.length)
      setSelectedIds(new Set())
    else
      setSelectedIds(new Set(allPerms.map(p => p.id)))
  }

  /* ── save permissions ──────────────────────────────────────────────────── */
  async function handleSavePerms() {
    if (!selectedRole) return
    setSavingPerms(true)
    try {
      await setRolePermissions(selectedRole.id, Array.from(selectedIds))
      toast.success(`Permissions saved for "${selectedRole.role_name}"`)
      await load()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to save permissions')
    }
    setSavingPerms(false)
  }

  /* ── open modal ────────────────────────────────────────────────────────── */
  function openCreate() {
    setEditingRole(null)
    setModalName('')
    setShowModal(true)
  }

  function openEdit(role: RoleRecord, e: React.MouseEvent) {
    e.stopPropagation()
    setEditingRole(role)
    setModalName(role.role_name)
    setShowModal(true)
  }

  /* ── create / update role ──────────────────────────────────────────────── */
  async function handleModalSubmit() {
    const name = modalName.trim()
    if (!name) { toast.warning('Role name cannot be empty'); return }
    setModalSaving(true)
    try {
      if (editingRole) {
        await updateRole(editingRole.id, { role_name: name })
        toast.success(`Role "${name}" updated`)
        /* refresh selected role if it was the edited one */
        if (selectedRole?.id === editingRole.id)
          setSelectedRole(prev => prev ? { ...prev, role_name: name } : prev)
      } else {
        await createRole({ role_name: name })
        toast.success(`Role "${name}" created`)
      }
      setShowModal(false)
      await load()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to save role')
    }
    setModalSaving(false)
  }

  /* ── delete role ───────────────────────────────────────────────────────── */
  async function handleDelete(role: RoleRecord, e: React.MouseEvent) {
    e.stopPropagation()
    const ok = await confirmDanger({
      title:       `Delete "${role.role_name}"?`,
      text:        'All users with this role will lose their permissions. This cannot be undone.',
      confirmText: 'Delete Role',
    })
    if (!ok) return
    try {
      await deleteRole(role.id)
      toast.success(`Role "${role.role_name}" deleted`)
      if (selectedRole?.id === role.id) { setSelectedRole(null); setSelectedIds(new Set()) }
      await load()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to delete role')
    }
  }

  /* ── grouped permissions ───────────────────────────────────────────────── */
  const grouped = allPerms.reduce<Record<string, PermissionRecord[]>>((acc, p) => {
    (acc[p.module] ??= []).push(p)
    return acc
  }, {})

  const filteredGrouped = search.trim()
    ? Object.fromEntries(
        Object.entries(grouped).filter(([mod, perms]) =>
          mod.includes(search.toLowerCase()) ||
          perms.some(p =>
            p.code.toLowerCase().includes(search.toLowerCase()) ||
            p.name.toLowerCase().includes(search.toLowerCase())
          )
        )
      )
    : grouped

  /* ── render ────────────────────────────────────────────────────────────── */
  if (loading) {
    return (
      <div className="p-6 flex items-center justify-center min-h-[50vh]">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 rounded-full border-2 animate-spin"
            style={{ borderColor: 'var(--t-accent)', borderTopColor: 'transparent' }} />
          <span className="font-mono text-xs" style={{ color: 'var(--t-muted)' }}>LOADING ROLES…</span>
        </div>
      </div>
    )
  }

  return (
    <div className="p-4 md:p-6 space-y-6">

      {/* ── header ──────────────────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="font-display font-bold text-xl md:text-2xl" style={{ color: 'var(--t-text)' }}>
            Role Management
          </h1>
          <p className="font-mono text-xs mt-1" style={{ color: 'var(--t-muted)' }}>
            {roles.length} roles · {allPerms.length} permissions
          </p>
        </div>
        <PermissionGuard permission="roles:create">
          <button onClick={openCreate}
            className="rounded-lg px-4 py-2 font-display font-semibold text-sm transition-all hover:opacity-90 flex items-center gap-2"
            style={{ background: 'var(--t-accent)', color: '#fff', border: '1px solid var(--t-accent-border)' }}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><path d="M12 5v14M5 12h14"/></svg>
            New Role
          </button>
        </PermissionGuard>
      </div>

      {/* ── layout: role list + permission editor ────────────────────────── */}
      <div className="flex flex-col lg:flex-row gap-6">

        {/* Role list */}
        <div className="lg:w-72 shrink-0 space-y-2">
          {roles.length === 0 && (
            <div className="font-mono text-xs py-8 text-center" style={{ color: 'var(--t-muted)' }}>
              No roles yet. Create the first one.
            </div>
          )}
          {roles.map(role => {
            const isSelected = selectedRole?.id === role.id
            return (
              <div key={role.id} onClick={() => handleSelectRole(role)}
                className="rounded-xl px-4 py-3 cursor-pointer transition-all"
                style={{
                  background: isSelected ? 'var(--t-accent-alpha)' : 'rgba(255,255,255,0.02)',
                  border: isSelected ? '1px solid var(--t-accent-border)' : '1px solid var(--t-border-alpha)',
                }}>
                <div className="flex items-center justify-between gap-2">
                  <span className="font-display font-medium text-sm truncate"
                    style={{ color: isSelected ? 'var(--t-accent)' : 'var(--t-text)' }}>
                    {role.role_name}
                  </span>
                  <div className="flex gap-1 shrink-0">
                    <PermissionGuard permission="roles:update">
                      <button onClick={e => openEdit(role, e)} title="Edit role name"
                        className="p-1.5 rounded transition-colors"
                        style={{ color: 'var(--t-muted)' }}
                        onMouseEnter={e => { e.currentTarget.style.color = 'var(--t-accent)' }}
                        onMouseLeave={e => { e.currentTarget.style.color = 'var(--t-muted)' }}>
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                          <path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/>
                          <path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/>
                        </svg>
                      </button>
                    </PermissionGuard>
                    <PermissionGuard permission="roles:delete">
                      <button onClick={e => handleDelete(role, e)} title="Delete role"
                        className="p-1.5 rounded transition-colors"
                        style={{ color: 'var(--t-muted)' }}
                        onMouseEnter={e => { e.currentTarget.style.color = '#ff3366' }}
                        onMouseLeave={e => { e.currentTarget.style.color = 'var(--t-muted)' }}>
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                          <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/>
                        </svg>
                      </button>
                    </PermissionGuard>
                  </div>
                </div>
              </div>
            )
          })}
        </div>

        {/* Permission editor */}
        {selectedRole ? (
          <div className="flex-1 min-w-0">
            <GlassCard className="p-4 md:p-6">
              {/* editor header */}
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4">
                <div>
                  <h3 className="font-display font-semibold text-base" style={{ color: 'var(--t-text)' }}>
                    Permissions — <span style={{ color: 'var(--t-accent)' }}>{selectedRole.role_name}</span>
                  </h3>
                  <p className="font-mono text-xs mt-0.5" style={{ color: 'var(--t-muted)' }}>
                    {selectedIds.size} / {allPerms.length} selected
                  </p>
                </div>
                <div className="flex items-center gap-2 flex-wrap">
                  <button onClick={toggleAll}
                    className="rounded-lg px-3 py-1.5 font-mono text-xs transition-all"
                    style={{
                      background: selectedIds.size === allPerms.length ? 'var(--t-accent-alpha)' : 'rgba(255,255,255,0.04)',
                      border: '1px solid var(--t-border-alpha)',
                      color: selectedIds.size === allPerms.length ? 'var(--t-accent)' : 'var(--t-muted)',
                    }}>
                    {selectedIds.size === allPerms.length ? 'DESELECT ALL' : 'SELECT ALL'}
                  </button>
                  <PermissionGuard permission="roles:update">
                    <button onClick={handleSavePerms} disabled={savingPerms}
                      className="rounded-lg px-4 py-1.5 font-mono text-xs font-semibold transition-all disabled:opacity-50 flex items-center gap-2"
                      style={{ background: 'var(--t-accent)', color: '#fff', border: '1px solid var(--t-accent-border)' }}>
                      {savingPerms
                        ? <><span className="w-3 h-3 rounded-full border animate-spin inline-block" style={{ borderColor: '#fff', borderTopColor: 'transparent' }}/> Saving…</>
                        : <>💾 Save Permissions</>
                      }
                    </button>
                  </PermissionGuard>
                </div>
              </div>

              {/* color legend */}
              <div className="flex flex-wrap items-center gap-3 mb-3 px-1">
                {([
                  { action: 'CREATE',  col: '#00ff88' },
                  { action: 'READ',    col: '#00d4ff' },
                  { action: 'UPDATE',  col: '#ffaa00' },
                  { action: 'DELETE',  col: '#ff3366' },
                  { action: 'EXECUTE', col: '#a78bfa' },
                ] as const).map(({ action, col }) => (
                  <div key={action} className="flex items-center gap-1">
                    <span className="w-2 h-2 rounded-sm" style={{ background: col }}/>
                    <span className="font-mono text-[9px]" style={{ color: 'var(--t-muted)' }}>{action}</span>
                  </div>
                ))}
              </div>

              {/* search */}
              <input value={search} onChange={e => setSearch(e.target.value)}
                placeholder="Search permissions…"
                className="w-full rounded-lg px-3 py-2 font-mono text-xs outline-none mb-4"
                style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid var(--t-border-alpha)', color: 'var(--t-text)' }}
                onFocus={e  => { e.currentTarget.style.borderColor = 'var(--t-accent)' }}
                onBlur={e   => { e.currentTarget.style.borderColor = 'var(--t-border-alpha)' }}
              />

              {/* module cards */}
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3 max-h-[60vh] overflow-y-auto pr-1">
                {Object.entries(filteredGrouped).map(([mod, perms]) => {
                  const sel    = perms.filter(p => selectedIds.has(p.id)).length
                  const allMod = sel === perms.length
                  const none   = sel === 0

                  // Clean module label: replace underscores, title-case
                  const modLabel = mod.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())

                  // Module category colors
                  const isCrud     = perms.some(p => ['create','read','update','delete'].includes(p.action))
                  const isExec     = perms.some(p => p.action === 'execute')
                  const modColor   = isExec ? '#a78bfa' : allMod ? 'var(--t-accent)' : none ? 'var(--t-muted)' : '#ffaa00'

                  return (
                    <div key={mod} className="rounded-xl overflow-hidden"
                      style={{
                        background: allMod ? 'rgba(0,212,255,0.04)' : 'rgba(255,255,255,0.02)',
                        border: `1px solid ${allMod ? 'rgba(0,212,255,0.2)' : none ? 'var(--t-border-alpha)' : 'rgba(255,170,0,0.2)'}`,
                      }}>
                      {/* module header — click to toggle whole module */}
                      <button
                        type="button"
                        onClick={() => toggleModule(mod)}
                        className="w-full flex items-center justify-between px-3 py-2.5 hover:bg-white/5 transition-all"
                        style={{ borderBottom: '1px solid var(--t-border-alpha)' }}>
                        <div className="flex items-center gap-2 min-w-0">
                          {/* checkbox */}
                          <span
                            className="w-4 h-4 rounded flex items-center justify-center shrink-0 text-[9px]"
                            style={{
                              background: allMod ? 'var(--t-accent)' : none ? 'rgba(255,255,255,0.04)' : 'rgba(255,170,0,0.15)',
                              border: `1px solid ${allMod ? 'var(--t-accent)' : none ? 'var(--t-border-alpha)' : 'rgba(255,170,0,0.4)'}`,
                              color: allMod ? '#fff' : '#ffaa00',
                              fontWeight: 700,
                            }}>
                            {allMod ? '✓' : none ? '' : '–'}
                          </span>
                          <span
                            className="font-display font-semibold text-xs uppercase tracking-wider truncate"
                            style={{ color: modColor }}>
                            {modLabel}
                          </span>
                        </div>
                        {/* count badge */}
                        <span
                          className="font-mono text-[10px] px-1.5 py-0.5 rounded shrink-0"
                          style={{
                            background: allMod ? 'rgba(0,212,255,0.15)' : none ? 'rgba(255,255,255,0.05)' : 'rgba(255,170,0,0.12)',
                            color:      allMod ? 'var(--t-accent)'  : none ? 'var(--t-muted)'  : '#ffaa00',
                          }}>
                          {sel}/{perms.length}
                        </span>
                      </button>

                      {/* permission toggle buttons */}
                      <div className="grid grid-cols-2 gap-1.5 p-2.5">
                        {perms
                          .filter(p => !search.trim() ||
                            p.code.toLowerCase().includes(search.toLowerCase()) ||
                            p.name.toLowerCase().includes(search.toLowerCase()) ||
                            p.action.toLowerCase().includes(search.toLowerCase()))
                          .map(perm => {
                            const checked = selectedIds.has(perm.id)
                            const actionColor: Record<string, string> = {
                              create:  '#00ff88',
                              read:    '#00d4ff',
                              update:  '#ffaa00',
                              delete:  '#ff3366',
                              execute: '#a78bfa',
                            }
                            const col = actionColor[perm.action] ?? '#8899bb'
                            return (
                              <button
                                key={perm.id}
                                type="button"
                                onClick={() => togglePerm(perm.id)}
                                className="flex items-center gap-1.5 px-2 py-1.5 rounded-lg text-left transition-all"
                                style={{
                                  background: checked ? `${col}18` : 'rgba(255,255,255,0.02)',
                                  border: `1px solid ${checked ? col + '55' : 'var(--t-border-alpha)'}`,
                                  cursor: 'pointer',
                                }}>
                                <span
                                  className="w-3 h-3 rounded flex items-center justify-center shrink-0"
                                  style={{
                                    background: checked ? col : 'rgba(255,255,255,0.04)',
                                    border: `1px solid ${checked ? col : 'var(--t-border-alpha)'}`,
                                  }}>
                                  {checked && <span style={{ color: '#000', fontSize: 8, lineHeight: 1, fontWeight: 700 }}>✓</span>}
                                </span>
                                <span
                                  className="font-mono text-[10px] uppercase font-semibold tracking-wider"
                                  style={{ color: checked ? col : 'var(--t-muted)' }}>
                                  {perm.action}
                                </span>
                              </button>
                            )
                          })}
                      </div>
                    </div>
                  )
                })}
                {Object.keys(filteredGrouped).length === 0 && search && (
                  <div className="col-span-3 py-8 text-center font-mono text-xs" style={{ color: 'var(--t-muted)' }}>
                    No permissions match "{search}"
                  </div>
                )}
              </div>
            </GlassCard>
          </div>
        ) : (
          <div className="flex-1 flex items-center justify-center min-h-[300px]">
            <div className="text-center space-y-3">
              <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="var(--t-muted)"
                strokeWidth="1" className="mx-auto opacity-30">
                <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
              </svg>
              <p className="font-mono text-xs" style={{ color: 'var(--t-muted)' }}>
                Select a role to manage its permissions
              </p>
            </div>
          </div>
        )}
      </div>

      {/* ── Create/Edit modal ────────────────────────────────────────────── */}
      {showModal && (
        <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4"
          onClick={() => setShowModal(false)}>
          <div className="glass rounded-xl p-6 w-full max-w-sm shadow-2xl"
            style={{ border: '1px solid rgba(0,212,255,0.25)' }}
            onClick={e => e.stopPropagation()}>
            <h3 className="font-display font-bold text-lg mb-1" style={{ color: 'var(--t-accent)' }}>
              {editingRole ? '✏ Edit Role' : '+ New Role'}
            </h3>
            <p className="font-mono text-xs mb-4" style={{ color: 'var(--t-muted)' }}>
              {editingRole ? 'Update the role name below.' : 'Enter a name for the new role.'}
            </p>
            <label className="font-mono text-xs block mb-1.5" style={{ color: 'var(--t-muted)' }}>
              ROLE NAME
            </label>
            <input
              value={modalName}
              onChange={e => setModalName(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') void handleModalSubmit() }}
              autoFocus
              placeholder="e.g. Network Engineer"
              className="w-full rounded-lg px-3 py-2.5 font-mono text-sm outline-none mb-5"
              style={{
                background: 'rgba(255,255,255,0.04)',
                border: '1px solid var(--t-border-alpha)',
                color: 'var(--t-text)',
              }}
              onFocus={e  => { e.currentTarget.style.borderColor = 'var(--t-accent)' }}
              onBlur={e   => { e.currentTarget.style.borderColor = 'var(--t-border-alpha)' }}
            />
            <div className="flex gap-2 justify-end">
              <button onClick={() => setShowModal(false)}
                className="rounded-lg px-4 py-2 font-mono text-xs transition-all hover:opacity-80"
                style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid var(--t-border-alpha)', color: 'var(--t-muted)' }}>
                Cancel
              </button>
              <button onClick={() => void handleModalSubmit()}
                disabled={modalSaving || !modalName.trim()}
                className="rounded-lg px-5 py-2 font-mono text-xs font-semibold transition-all disabled:opacity-50 flex items-center gap-2"
                style={{ background: 'var(--t-accent)', color: '#fff', border: '1px solid var(--t-accent-border)' }}>
                {modalSaving
                  ? <><span className="w-3 h-3 rounded-full border animate-spin inline-block" style={{ borderColor: '#fff', borderTopColor: 'transparent' }}/> Saving…</>
                  : editingRole ? 'Update Role' : 'Create Role'
                }
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
