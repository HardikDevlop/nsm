import { useEffect, useState, useCallback } from 'react'
import GlassCard from '../components/GlassCard'
import { PermissionGuard } from '../components/PermissionGuard'
import {
  listUsers, createUser, updateUser, deleteUser, assignUserRole,
  listRoles,
  type UserRecord, type RoleRecord,
} from '../lib/api'

export default function UserManagement() {
  const [users, setUsers] = useState<UserRecord[]>([])
  const [roles, setRoles] = useState<RoleRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [showForm, setShowForm] = useState(false)
  const [editingUser, setEditingUser] = useState<UserRecord | null>(null)
  const [deleteConfirm, setDeleteConfirm] = useState<number | null>(null)

  // Form state
  const [formName, setFormName] = useState('')
  const [formEmail, setFormEmail] = useState('')
  const [formPassword, setFormPassword] = useState('')
  const [formRoleId, setFormRoleId] = useState<number | null>(null)
  const [formStatus, setFormStatus] = useState('active')

  const load = useCallback(async () => {
    try {
      const [u, r] = await Promise.all([listUsers(), listRoles()])
      setUsers(u)
      setRoles(r)
    } catch { /* silent */ }
    setLoading(false)
  }, [])

  useEffect(() => { void load() }, [load])

  function openCreate() {
    setEditingUser(null)
    setFormName('')
    setFormEmail('')
    setFormPassword('')
    setFormRoleId(null)
    setFormStatus('active')
    setShowForm(true)
  }

  function openEdit(user: UserRecord) {
    setEditingUser(user)
    setFormName(user.name)
    setFormEmail(user.email)
    setFormPassword('')
    setFormRoleId(user.role_id)
    setFormStatus(user.status)
    setShowForm(true)
  }

  async function handleSubmit() {
    setSaving(true)
    setError('')
    try {
      if (editingUser) {
        const data: Record<string, any> = {
          name: formName.trim(),
          email: formEmail.trim(),
          status: formStatus,
        }
        if (formPassword) data.password = formPassword
        if (formRoleId !== undefined) data.role_id = formRoleId
        await updateUser(editingUser.id, data)
      } else {
        await createUser({
          name: formName.trim(),
          email: formEmail.trim(),
          password: formPassword,
          role_id: formRoleId ?? undefined,
          status: formStatus,
        })
      }
      setShowForm(false)
      await load()
    } catch (e: any) {
      setError(e?.message ?? 'Failed to save user')
    }
    setSaving(false)
  }

  async function handleDelete(id: number) {
    try {
      await deleteUser(id)
      setDeleteConfirm(null)
      await load()
    } catch (e: any) {
      setError(e?.message ?? 'Failed to delete')
    }
  }

  async function handleRoleChange(userId: number, roleId: number) {
    try {
      await assignUserRole(userId, roleId)
      await load()
    } catch (e: any) {
      setError(e?.message ?? 'Failed to assign role')
    }
  }

  async function toggleStatus(user: UserRecord) {
    try {
      await updateUser(user.id, { status: user.status === 'active' ? 'inactive' : 'active' })
      await load()
    } catch (e: any) {
      setError(e?.message ?? 'Failed to update status')
    }
  }

  if (loading) {
    return (
      <div className="p-4 md:p-6 flex items-center justify-center min-h-[50vh]">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 rounded-full border-2 animate-spin" style={{ borderColor: 'var(--t-accent)', borderTopColor: 'transparent' }} />
          <span className="font-mono text-xs" style={{ color: 'var(--t-muted)' }}>LOADING USERS...</span>
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
            User Management
          </h1>
          <p className="font-mono text-xs mt-1" style={{ color: 'var(--t-muted)' }}>
            {users.length} users &middot; {roles.length} roles
          </p>
        </div>
        <PermissionGuard permission="users:create">
          <button onClick={openCreate}
            className="rounded-lg px-4 py-2 font-display font-medium text-sm transition-all"
            style={{ background: 'var(--t-accent)', color: '#fff', border: '1px solid var(--t-accent-border)' }}>
            + New User
          </button>
        </PermissionGuard>
      </div>

      {error && (
        <div className="px-4 py-2 rounded-lg font-mono text-xs" style={{ background: 'rgba(255,51,102,0.1)', border: '1px solid rgba(255,51,102,0.3)', color: '#ff3366' }}>
          {error}
        </div>
      )}

      {/* User table */}
      <GlassCard className="overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left">
            <thead>
              <tr style={{ borderBottom: '1px solid var(--t-border-light)' }}>
                <th className="px-4 py-3 font-mono text-xs uppercase tracking-wider" style={{ color: 'var(--t-muted)' }}>User</th>
                <th className="px-4 py-3 font-mono text-xs uppercase tracking-wider hidden sm:table-cell" style={{ color: 'var(--t-muted)' }}>Email</th>
                <th className="px-4 py-3 font-mono text-xs uppercase tracking-wider" style={{ color: 'var(--t-muted)' }}>Role</th>
                <th className="px-4 py-3 font-mono text-xs uppercase tracking-wider hidden md:table-cell" style={{ color: 'var(--t-muted)' }}>Status</th>
                <th className="px-4 py-3 font-mono text-xs uppercase tracking-wider text-right" style={{ color: 'var(--t-muted)' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.map(user => (
                <tr key={user.id} style={{ borderBottom: '1px solid var(--t-border-alpha)' }}>
                  {/* User name */}
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-3">
                      <div className="w-8 h-8 rounded-full flex items-center justify-center shrink-0 font-display font-bold text-xs"
                        style={{ background: 'var(--t-accent-alpha)', color: 'var(--t-accent)', border: '1px solid var(--t-accent-border)' }}>
                        {user.name.charAt(0).toUpperCase()}
                      </div>
                      <div>
                        <div className="font-display font-medium text-sm" style={{ color: 'var(--t-text)' }}>{user.name}</div>
                        <div className="font-mono text-xs sm:hidden" style={{ color: 'var(--t-muted)' }}>{user.email}</div>
                      </div>
                    </div>
                  </td>
                  {/* Email */}
                  <td className="px-4 py-3 font-mono text-xs hidden sm:table-cell" style={{ color: 'var(--t-muted)' }}>{user.email}</td>
                  {/* Role */}
                  <td className="px-4 py-3">
                    <PermissionGuard permission="users:update" fallback={
                      <span className="font-mono text-xs px-2 py-1 rounded" style={{ background: 'var(--t-accent-alpha)', color: 'var(--t-accent)', border: '1px solid var(--t-accent-border)' }}>
                        {user.role_name ?? 'No Role'}
                      </span>
                    }>
                      <select
                        value={user.role_id ?? ''}
                        onChange={e => handleRoleChange(user.id, Number(e.target.value))}
                        className="font-mono text-xs rounded px-2 py-1 outline-none cursor-pointer"
                        style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid var(--t-border-alpha)', color: 'var(--t-text)' }}
                      >
                        <option value="">No Role</option>
                        {roles.map(r => <option key={r.id} value={r.id}>{r.role_name}</option>)}
                      </select>
                    </PermissionGuard>
                  </td>
                  {/* Status */}
                  <td className="px-4 py-3 hidden md:table-cell">
                    <button onClick={() => toggleStatus(user)}
                      className="flex items-center gap-1.5 font-mono text-xs transition-colors"
                      style={{ color: user.status === 'active' ? '#00ff88' : '#ff3366' }}>
                      <span className={`status-dot ${user.status === 'active' ? 'online' : 'offline'}`} />
                      {user.status === 'active' ? 'Active' : 'Inactive'}
                    </button>
                  </td>
                  {/* Actions */}
                  <td className="px-4 py-3 text-right">
                    <div className="flex items-center justify-end gap-1">
                      <PermissionGuard permission="users:update">
                        <button onClick={() => openEdit(user)}
                          className="p-1.5 rounded transition-colors" style={{ color: 'var(--t-muted)' }}
                          onMouseEnter={e => { e.currentTarget.style.color = 'var(--t-accent)' }}
                          onMouseLeave={e => { e.currentTarget.style.color = 'var(--t-muted)' }}>
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7" />
                            <path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z" />
                          </svg>
                        </button>
                      </PermissionGuard>
                      <PermissionGuard permission="users:delete">
                        <button onClick={() => setDeleteConfirm(user.id)}
                          className="p-1.5 rounded transition-colors" style={{ color: 'var(--t-muted)' }}
                          onMouseEnter={e => { e.currentTarget.style.color = '#ff3366' }}
                          onMouseLeave={e => { e.currentTarget.style.color = 'var(--t-muted)' }}>
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" />
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
        {users.length === 0 && (
          <div className="py-12 text-center">
            <p className="font-mono text-xs" style={{ color: 'var(--t-muted)' }}>No users found</p>
          </div>
        )}
      </GlassCard>

      {/* Create/Edit form modal */}
      {showForm && (
        <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4" onClick={() => setShowForm(false)}>
          <div className="glass rounded-xl p-6 w-full max-w-md" onClick={e => e.stopPropagation()}>
            <h3 className="font-display font-semibold text-lg mb-4" style={{ color: 'var(--t-text)' }}>
              {editingUser ? 'Edit User' : 'Create User'}
            </h3>
            <div className="space-y-3">
              <div>
                <label className="font-mono text-xs block mb-1" style={{ color: 'var(--t-muted)' }}>NAME</label>
                <input value={formName} onChange={e => setFormName(e.target.value)}
                  className="w-full rounded-lg px-3 py-2 font-mono text-sm outline-none"
                  style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid var(--t-border-alpha)', color: 'var(--t-text)' }}
                  onFocus={e => { e.currentTarget.style.borderColor = 'var(--t-accent)' }}
                  onBlur={e => { e.currentTarget.style.borderColor = 'var(--t-border-alpha)' }}
                />
              </div>
              <div>
                <label className="font-mono text-xs block mb-1" style={{ color: 'var(--t-muted)' }}>EMAIL</label>
                <input type="email" value={formEmail} onChange={e => setFormEmail(e.target.value)}
                  className="w-full rounded-lg px-3 py-2 font-mono text-sm outline-none"
                  style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid var(--t-border-alpha)', color: 'var(--t-text)' }}
                  onFocus={e => { e.currentTarget.style.borderColor = 'var(--t-accent)' }}
                  onBlur={e => { e.currentTarget.style.borderColor = 'var(--t-border-alpha)' }}
                />
              </div>
              <div>
                <label className="font-mono text-xs block mb-1" style={{ color: 'var(--t-muted)' }}>
                  PASSWORD{editingUser && ' (leave blank to keep)'}
                </label>
                <input type="password" value={formPassword} onChange={e => setFormPassword(e.target.value)}
                  className="w-full rounded-lg px-3 py-2 font-mono text-sm outline-none"
                  style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid var(--t-border-alpha)', color: 'var(--t-text)' }}
                  onFocus={e => { e.currentTarget.style.borderColor = 'var(--t-accent)' }}
                  onBlur={e => { e.currentTarget.style.borderColor = 'var(--t-border-alpha)' }}
                />
              </div>
              <div>
                <label className="font-mono text-xs block mb-1" style={{ color: 'var(--t-muted)' }}>ROLE</label>
                <select value={formRoleId ?? ''} onChange={e => setFormRoleId(e.target.value ? Number(e.target.value) : null)}
                  className="w-full rounded-lg px-3 py-2 font-mono text-sm outline-none cursor-pointer"
                  style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid var(--t-border-alpha)', color: 'var(--t-text)' }}
                >
                  <option value="">No Role</option>
                  {roles.map(r => <option key={r.id} value={r.id}>{r.role_name}</option>)}
                </select>
              </div>
              <div>
                <label className="font-mono text-xs block mb-1" style={{ color: 'var(--t-muted)' }}>STATUS</label>
                <select value={formStatus} onChange={e => setFormStatus(e.target.value)}
                  className="w-full rounded-lg px-3 py-2 font-mono text-sm outline-none cursor-pointer"
                  style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid var(--t-border-alpha)', color: 'var(--t-text)' }}
                >
                  <option value="active">Active</option>
                  <option value="inactive">Inactive</option>
                </select>
              </div>
            </div>
            <div className="flex gap-2 justify-end mt-5">
              <button onClick={() => setShowForm(false)}
                className="rounded-lg px-4 py-2 font-mono text-xs"
                style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid var(--t-border-alpha)', color: 'var(--t-text)' }}>
                Cancel
              </button>
              <button onClick={handleSubmit} disabled={saving || !formName.trim() || !formEmail.trim() || (!editingUser && !formPassword)}
                className="rounded-lg px-4 py-2 font-mono text-xs transition-all disabled:opacity-50"
                style={{ background: 'var(--t-accent)', color: '#fff', border: '1px solid var(--t-accent-border)' }}>
                {saving ? 'Saving...' : editingUser ? 'Update' : 'Create'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Delete confirmation */}
      {deleteConfirm !== null && (
        <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4" onClick={() => setDeleteConfirm(null)}>
          <div className="glass rounded-xl p-6 w-full max-w-sm" onClick={e => e.stopPropagation()}>
            <h3 className="font-display font-semibold text-base mb-2" style={{ color: '#ff3366' }}>Delete User</h3>
            <p className="font-mono text-xs mb-4" style={{ color: 'var(--t-muted)' }}>
              Are you sure? This action cannot be undone.
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
