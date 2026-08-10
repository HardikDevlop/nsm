import { useEffect, useState, useCallback } from 'react'
import GlassCard from '../components/GlassCard'
import { PermissionGuard } from '../components/PermissionGuard'
import {
  listRoles, createRole, updateRole, deleteRole,
  getRolePermissions, setRolePermissions,
  listPermissions,
  type RoleRecord, type PermissionRecord, type RoleWithPermissions,
} from '../lib/api'

export default function RoleManagement() {
  const [roles, setRoles] = useState<RoleRecord[]>([])
  const [allPermissions, setAllPermissions] = useState<PermissionRecord[]>([])
  const [selectedRole, setSelectedRole] = useState<RoleWithPermissions | null>(null)
  const [selectedPermIds, setSelectedPermIds] = useState<Set<number>>(new Set())
  const [roleName, setRoleName] = useState('')
  const [editingId, setEditingId] = useState<number | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [deleteConfirm, setDeleteConfirm] = useState<number | null>(null)

  const load = useCallback(async () => {
    try {
      const [r, p] = await Promise.all([listRoles(), listPermissions()])
      setRoles(r)
      setAllPermissions(p)
    } catch { /* silent */ }
    setLoading(false)
  }, [])

  useEffect(() => { void load() }, [load])

  async function handleSelectRole(role: RoleRecord) {
    try {
      const rw = await getRolePermissions(role.id)
      setSelectedRole(rw)
      setSelectedPermIds(new Set(rw.permissions.map(p => p.id)))
    } catch { /* silent */ }
  }

  function togglePerm(id: number) {
    setSelectedPermIds(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  function toggleModule(mod: string) {
    const modPerms = allPermissions.filter(p => p.module === mod)
    const allSelected = modPerms.every(p => selectedPermIds.has(p.id))
    setSelectedPermIds(prev => {
      const next = new Set(prev)
      if (allSelected) {
        modPerms.forEach(p => next.delete(p.id))
      } else {
        modPerms.forEach(p => next.add(p.id))
      }
      return next
    })
  }

  function toggleAll() {
    if (selectedPermIds.size === allPermissions.length) {
      setSelectedPermIds(new Set())
    } else {
      setSelectedPermIds(new Set(allPermissions.map(p => p.id)))
    }
  }

  async function handleSave() {
    if (!selectedRole) return
    setSaving(true)
    setError('')
    try {
      await setRolePermissions(selectedRole.id, Array.from(selectedPermIds))
      await load()
    } catch (e: any) {
      setError(e?.message ?? 'Failed to save')
    }
    setSaving(false)
  }

  async function handleCreateOrUpdate() {
    if (!roleName.trim()) return
    setSaving(true)
    setError('')
    try {
      if (editingId) {
        await updateRole(editingId, { role_name: roleName.trim() })
      } else {
        await createRole({ role_name: roleName.trim() })
      }
      setRoleName('')
      setEditingId(null)
      setShowForm(false)
      await load()
    } catch (e: any) {
      setError(e?.message ?? 'Failed to save role')
    }
    setSaving(false)
  }

  async function handleDelete(id: number) {
    try {
      await deleteRole(id)
      if (selectedRole?.id === id) setSelectedRole(null)
      setDeleteConfirm(null)
      await load()
    } catch (e: any) {
      setError(e?.message ?? 'Failed to delete')
    }
  }

  function startEdit(role: RoleRecord) {
    setRoleName(role.role_name)
    setEditingId(role.id)
    setShowForm(true)
  }

  // Group permissions by module
  const grouped = allPermissions.reduce<Record<string, PermissionRecord[]>>((acc, p) => {
    (acc[p.module] ??= []).push(p)
    return acc
  }, {})

  const filteredGrouped = search
    ? Object.fromEntries(
        Object.entries(grouped).filter(([, perms]) =>
          perms.some(p => p.code.includes(search) || p.name.toLowerCase().includes(search.toLowerCase()) || p.module.toLowerCase().includes(search.toLowerCase()))
        )
      )
    : grouped

  if (loading) {
    return (
      <div className="p-4 md:p-6 flex items-center justify-center min-h-[50vh]">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 rounded-full border-2 animate-spin" style={{ borderColor: 'var(--t-accent)', borderTopColor: 'transparent' }} />
          <span className="font-mono text-xs" style={{ color: 'var(--t-muted)' }}>LOADING ROLES...</span>
        </div>
      </div>
    )
  }

  return (
    <div className="p-4 md:p-6 space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="font-display font-bold text-xl md:text-2xl" style={{ color: 'var(--t-text)' }}>
            Role Management
          </h1>
          <p className="font-mono text-xs mt-1" style={{ color: 'var(--t-muted)' }}>
            {roles.length} roles &middot; {allPermissions.length} permissions
          </p>
        </div>
        <PermissionGuard permission="roles:create">
          <button
            onClick={() => { setRoleName(''); setEditingId(null); setShowForm(true) }}
            className="rounded-lg px-4 py-2 font-display font-medium text-sm transition-all"
            style={{ background: 'var(--t-accent)', color: '#fff', border: '1px solid var(--t-accent-border)' }}
          >
            + New Role
          </button>
        </PermissionGuard>
      </div>

      {error && (
        <div className="px-4 py-2 rounded-lg font-mono text-xs" style={{ background: 'rgba(255,51,102,0.1)', border: '1px solid rgba(255,51,102,0.3)', color: '#ff3366' }}>
          {error}
        </div>
      )}

      {/* Create/Edit form modal */}
      {showForm && (
        <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4" onClick={() => setShowForm(false)}>
          <div className="glass rounded-xl p-6 w-full max-w-sm" onClick={e => e.stopPropagation()}>
            <h3 className="font-display font-semibold text-lg mb-4" style={{ color: 'var(--t-text)' }}>
              {editingId ? 'Edit Role' : 'Create Role'}
            </h3>
            <label className="font-mono text-xs block mb-1.5" style={{ color: 'var(--t-muted)' }}>ROLE NAME</label>
            <input
              value={roleName}
              onChange={e => setRoleName(e.target.value)}
              autoFocus
              className="w-full rounded-lg px-3 py-2.5 font-mono text-sm outline-none mb-4"
              style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid var(--t-border-alpha)', color: 'var(--t-text)' }}
              onFocus={e => { e.currentTarget.style.borderColor = 'var(--t-accent)' }}
              onBlur={e => { e.currentTarget.style.borderColor = 'var(--t-border-alpha)' }}
              onKeyDown={e => { if (e.key === 'Enter') handleCreateOrUpdate() }}
            />
            <div className="flex gap-2 justify-end">
              <button onClick={() => setShowForm(false)}
                className="rounded-lg px-4 py-2 font-mono text-xs transition-all"
                style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid var(--t-border-alpha)', color: 'var(--t-text)' }}>
                Cancel
              </button>
              <button onClick={handleCreateOrUpdate} disabled={saving || !roleName.trim()}
                className="rounded-lg px-4 py-2 font-mono text-xs transition-all disabled:opacity-50"
                style={{ background: 'var(--t-accent)', color: '#fff', border: '1px solid var(--t-accent-border)' }}>
                {saving ? 'Saving...' : editingId ? 'Update' : 'Create'}
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="flex flex-col lg:flex-row gap-6">
        {/* Role list */}
        <div className="lg:w-72 shrink-0 space-y-2">
          {roles.map(role => (
            <div
              key={role.id}
              onClick={() => handleSelectRole(role)}
              className={`rounded-xl px-4 py-3 cursor-pointer transition-all ${selectedRole?.id === role.id ? '' : ''}`}
              style={{
                background: selectedRole?.id === role.id ? 'var(--t-accent-alpha)' : 'rgba(255,255,255,0.02)',
                border: selectedRole?.id === role.id ? '1px solid var(--t-accent-border)' : '1px solid var(--t-border-alpha)',
              }}
            >
              <div className="flex items-center justify-between">
                <span className="font-display font-medium text-sm" style={{ color: selectedRole?.id === role.id ? 'var(--t-accent)' : 'var(--t-text)' }}>
                  {role.role_name}
                </span>
                <div className="flex gap-1">
                  <PermissionGuard permission="roles:update">
                    <button onClick={e => { e.stopPropagation(); startEdit(role) }}
                      className="p-1 rounded transition-colors" style={{ color: 'var(--t-muted)' }}
                      onMouseEnter={e => { e.currentTarget.style.color = 'var(--t-accent)' }}
                      onMouseLeave={e => { e.currentTarget.style.color = 'var(--t-muted)' }}>
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7" />
                        <path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z" />
                      </svg>
                    </button>
                  </PermissionGuard>
                  <PermissionGuard permission="roles:delete">
                    <button onClick={e => { e.stopPropagation(); setDeleteConfirm(role.id) }}
                      className="p-1 rounded transition-colors" style={{ color: 'var(--t-muted)' }}
                      onMouseEnter={e => { e.currentTarget.style.color = '#ff3366' }}
                      onMouseLeave={e => { e.currentTarget.style.color = 'var(--t-muted)' }}>
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" />
                      </svg>
                    </button>
                  </PermissionGuard>
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* Permission picker */}
        {selectedRole && (
          <div className="flex-1 min-w-0">
            <GlassCard className="p-4 md:p-6">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4">
                <div>
                  <h3 className="font-display font-semibold text-base" style={{ color: 'var(--t-text)' }}>
                    Permissions — {selectedRole.role_name}
                  </h3>
                  <p className="font-mono text-xs mt-0.5" style={{ color: 'var(--t-muted)' }}>
                    {selectedPermIds.size} / {allPermissions.length} selected
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  {/* Global toggle */}
                  <button onClick={toggleAll}
                    className="rounded-lg px-3 py-1.5 font-mono text-xs transition-all"
                    style={{
                      background: selectedPermIds.size === allPermissions.length ? 'var(--t-accent-alpha)' : 'rgba(255,255,255,0.04)',
                      border: '1px solid var(--t-border-alpha)',
                      color: selectedPermIds.size === allPermissions.length ? 'var(--t-accent)' : 'var(--t-muted)',
                    }}>
                    {selectedPermIds.size === allPermissions.length ? 'DESELECT ALL' : 'SELECT ALL'}
                  </button>
                  {/* Save */}
                  <PermissionGuard permission="roles:update">
                    <button onClick={handleSave} disabled={saving}
                      className="rounded-lg px-4 py-1.5 font-mono text-xs transition-all disabled:opacity-50"
                      style={{ background: 'var(--t-accent)', color: '#fff', border: '1px solid var(--t-accent-border)' }}>
                      {saving ? 'Saving...' : 'Save'}
                    </button>
                  </PermissionGuard>
                </div>
              </div>

              {/* Search */}
              <input
                value={search}
                onChange={e => setSearch(e.target.value)}
                placeholder="Search permissions..."
                className="w-full rounded-lg px-3 py-2 font-mono text-xs outline-none mb-4"
                style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid var(--t-border-alpha)', color: 'var(--t-text)' }}
                onFocus={e => { e.currentTarget.style.borderColor = 'var(--t-accent)' }}
                onBlur={e => { e.currentTarget.style.borderColor = 'var(--t-border-alpha)' }}
              />

              {/* Module cards grid */}
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
                {Object.entries(filteredGrouped).map(([mod, perms]) => {
                  const modSelected = perms.filter(p => selectedPermIds.has(p.id)).length
                  const allMod = modSelected === perms.length
                  return (
                    <div key={mod} className="rounded-lg p-3" style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid var(--t-border-alpha)' }}>
                      {/* Module header */}
                      <div className="flex items-center justify-between mb-2">
                        <button onClick={() => toggleModule(mod)}
                          className="flex items-center gap-2 font-display font-medium text-xs uppercase tracking-wider"
                          style={{ color: allMod ? 'var(--t-accent)' : 'var(--t-text)' }}>
                          <span className="w-4 h-4 rounded flex items-center justify-center text-xs"
                            style={{
                              background: allMod ? 'var(--t-accent)' : 'rgba(255,255,255,0.05)',
                              border: `1px solid ${allMod ? 'var(--t-accent)' : 'var(--t-border-alpha)'}`,
                              color: allMod ? '#fff' : 'var(--t-muted)',
                            }}>
                            {allMod ? '✓' : ''}
                          </span>
                          {mod.replace(/_/g, ' ')}
                        </button>
                        <span className="font-mono text-xs px-1.5 py-0.5 rounded"
                          style={{ background: 'rgba(255,255,255,0.05)', color: 'var(--t-muted)' }}>
                          {modSelected}/{perms.length}
                        </span>
                      </div>
                      {/* Permission checkboxes */}
                      <div className="space-y-1">
                        {perms.map(perm => {
                          const checked = selectedPermIds.has(perm.id)
                          if (search && !perm.code.includes(search) && !perm.name.toLowerCase().includes(search.toLowerCase())) return null
                          return (
                            <label key={perm.id} className="flex items-center gap-2 cursor-pointer py-0.5 group">
                              <span className="w-3.5 h-3.5 rounded flex items-center justify-center shrink-0"
                                style={{
                                  background: checked ? 'var(--t-accent)' : 'rgba(255,255,255,0.05)',
                                  border: `1px solid ${checked ? 'var(--t-accent)' : 'var(--t-border-alpha)'}`,
                                }}>
                                {checked && <span className="text-white text-xs leading-none">✓</span>}
                              </span>
                              <input type="checkbox" className="hidden" checked={checked} onChange={() => togglePerm(perm.id)} />
                              <span className="font-mono text-xs truncate" style={{ color: checked ? 'var(--t-text)' : 'var(--t-muted)' }}>
                                {perm.name}
                              </span>
                              <span className="font-mono text-xs ml-auto shrink-0 hidden sm:inline" style={{ color: 'var(--t-muted)' }}>
                                {perm.action}
                              </span>
                            </label>
                          )
                        })}
                      </div>
                    </div>
                  )
                })}
              </div>
            </GlassCard>
          </div>
        )}

        {!selectedRole && (
          <div className="flex-1 flex items-center justify-center min-h-[300px]">
            <div className="text-center">
              <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="var(--t-muted)" strokeWidth="1" className="mx-auto mb-3 opacity-40">
                <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
              </svg>
              <p className="font-mono text-xs" style={{ color: 'var(--t-muted)' }}>Select a role to manage permissions</p>
            </div>
          </div>
        )}
      </div>

      {/* Delete confirmation */}
      {deleteConfirm !== null && (
        <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4" onClick={() => setDeleteConfirm(null)}>
          <div className="glass rounded-xl p-6 w-full max-w-sm" onClick={e => e.stopPropagation()}>
            <h3 className="font-display font-semibold text-base mb-2" style={{ color: '#ff3366' }}>Delete Role</h3>
            <p className="font-mono text-xs mb-4" style={{ color: 'var(--t-muted)' }}>
              Are you sure? This cannot be undone.
            </p>
            <div className="flex gap-2 justify-end">
              <button onClick={() => setDeleteConfirm(null)}
                className="rounded-lg px-4 py-2 font-mono text-xs"
                style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid var(--t-border-alpha)', color: 'var(--t-text)' }}>
                Cancel
              </button>
              <button onClick={() => handleDelete(deleteConfirm)}
                className="rounded-lg px-4 py-2 font-mono text-xs"
                style={{ background: '#ff3366', color: '#fff', border: '1px solid rgba(255,51,102,0.5)' }}>
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
