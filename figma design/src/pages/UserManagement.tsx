import { useEffect, useState, useCallback } from 'react'
import GlassCard from '../components/GlassCard'
import { PermissionGuard } from '../components/PermissionGuard'
import { toast, confirmDanger } from '../lib/swal'
import {
  listUsers, createUser, updateUser, deleteUser, assignUserRole,
  listRoles,
  type UserRecord, type RoleRecord,
} from '../lib/api'

/* ── helpers ────────────────────────────────────────────────────────────── */
const STATUS_COLORS: Record<string, { text: string; dot: string }> = {
  active:   { text: '#00ff88', dot: 'online'  },
  inactive: { text: '#ff3366', dot: 'offline' },
}

function Avatar({ name }: { name: string }) {
  return (
    <div className="w-9 h-9 rounded-full flex items-center justify-center shrink-0 font-display font-bold text-sm"
      style={{ background: 'var(--t-accent-alpha)', color: 'var(--t-accent)', border: '1px solid var(--t-accent-border)' }}>
      {name.charAt(0).toUpperCase()}
    </div>
  )
}

/* ── page ────────────────────────────────────────────────────────────────── */
export default function UserManagement() {
  const [users,       setUsers]       = useState<UserRecord[]>([])
  const [roles,       setRoles]       = useState<RoleRecord[]>([])
  const [loading,     setLoading]     = useState(true)
  const [showModal,   setShowModal]   = useState(false)
  const [editingUser, setEditingUser] = useState<UserRecord | null>(null)
  const [modalSaving, setModalSaving] = useState(false)

  /* form state */
  const [fName,     setFName]     = useState('')
  const [fEmail,    setFEmail]    = useState('')
  const [fPassword, setFPassword] = useState('')
  const [fRoleId,   setFRoleId]   = useState<number | null>(null)
  const [fStatus,   setFStatus]   = useState('active')

  /* ── load ────────────────────────────────────────────────────────────── */
  const load = useCallback(async () => {
    try {
      const [u, r] = await Promise.all([listUsers(), listRoles()])
      setUsers(u)
      setRoles(r)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to load users')
    }
    setLoading(false)
  }, [])

  useEffect(() => { void load() }, [load])

  /* ── open modal ──────────────────────────────────────────────────────── */
  function openCreate() {
    setEditingUser(null)
    setFName(''); setFEmail(''); setFPassword('')
    setFRoleId(null); setFStatus('active')
    setShowModal(true)
  }

  function openEdit(user: UserRecord) {
    setEditingUser(user)
    setFName(user.name); setFEmail(user.email); setFPassword('')
    setFRoleId(user.role_id); setFStatus(user.status)
    setShowModal(true)
  }

  /* ── create / update ─────────────────────────────────────────────────── */
  async function handleSubmit() {
    if (!fName.trim())  { toast.warning('Name is required');  return }
    if (!fEmail.trim()) { toast.warning('Email is required'); return }
    if (!editingUser && fPassword.length < 6) {
      toast.warning('Password must be at least 6 characters')
      return
    }
    setModalSaving(true)
    try {
      if (editingUser) {
        // Build update payload — only include password if user typed a new one
        const payload: Parameters<typeof updateUser>[1] = {
          name:    fName.trim(),
          email:   fEmail.trim(),
          status:  fStatus,
          role_id: fRoleId,
        }
        if (fPassword) payload.password = fPassword
        await updateUser(editingUser.id, payload)
        toast.success(`User "${fName}" updated`)
      } else {
        await createUser({
          name:     fName.trim(),
          email:    fEmail.trim(),
          password: fPassword,
          role_id:  fRoleId ?? undefined,
          status:   fStatus,
        })
        toast.success(`User "${fName}" created`)
      }
      setShowModal(false)
      await load()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to save user')
    }
    setModalSaving(false)
  }

  /* ── delete ──────────────────────────────────────────────────────────── */
  async function handleDelete(user: UserRecord) {
    const ok = await confirmDanger({
      title:       `Delete "${user.name}"?`,
      text:        `This will permanently remove ${user.email} from the system.`,
      confirmText: 'Delete User',
    })
    if (!ok) return
    try {
      await deleteUser(user.id)
      toast.success(`User "${user.name}" deleted`)
      await load()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to delete user')
    }
  }

  /* ── toggle status ────────────────────────────────────────────────────── */
  async function handleToggleStatus(user: UserRecord) {
    const next = user.status === 'active' ? 'inactive' : 'active'
    try {
      await updateUser(user.id, { status: next })
      toast.info(`${user.name} is now ${next}`)
      await load()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Status update failed')
    }
  }

  /* ── inline role change ───────────────────────────────────────────────── */
  async function handleRoleChange(user: UserRecord, roleId: number) {
    try {
      await assignUserRole(user.id, roleId)
      const roleName = roles.find(r => r.id === roleId)?.role_name ?? 'role'
      toast.success(`${user.name} assigned to ${roleName}`)
      await load()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Role assignment failed')
    }
  }

  /* ── render ─────────────────────────────────────────────────────────── */
  if (loading) {
    return (
      <div className="p-6 flex items-center justify-center min-h-[50vh]">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 rounded-full border-2 animate-spin"
            style={{ borderColor: 'var(--t-accent)', borderTopColor: 'transparent' }} />
          <span className="font-mono text-xs" style={{ color: 'var(--t-muted)' }}>LOADING USERS…</span>
        </div>
      </div>
    )
  }

  return (
    <div className="p-4 md:p-6 space-y-6">

      {/* ── header ────────────────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="font-display font-bold text-xl md:text-2xl" style={{ color: 'var(--t-text)' }}>
            User Management
          </h1>
          <p className="font-mono text-xs mt-1" style={{ color: 'var(--t-muted)' }}>
            {users.length} users · {roles.length} roles
          </p>
        </div>
        <PermissionGuard permission="users:create">
          <button onClick={openCreate}
            className="rounded-lg px-4 py-2 font-display font-semibold text-sm transition-all hover:opacity-90 flex items-center gap-2"
            style={{ background: 'var(--t-accent)', color: '#fff', border: '1px solid var(--t-accent-border)' }}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><path d="M12 5v14M5 12h14"/></svg>
            New User
          </button>
        </PermissionGuard>
      </div>

      {/* ── user table ────────────────────────────────────────────────── */}
      <GlassCard className="overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left" style={{ minWidth: 520 }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--t-border-light)' }}>
                {['User', 'Email', 'Role', 'Status', 'Actions'].map(h => (
                  <th key={h} className="px-4 py-3 font-mono text-xs uppercase tracking-wider"
                    style={{ color: 'var(--t-muted)', background: 'rgba(8,18,40,0.6)' }}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {users.map(user => {
                const sc = STATUS_COLORS[user.status] ?? { text: '#8899bb', dot: 'unknown' }
                return (
                  <tr key={user.id} className="transition-colors"
                    style={{ borderBottom: '1px solid var(--t-border-alpha)' }}
                    onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = 'rgba(0,212,255,0.03)' }}
                    onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = '' }}>

                    {/* User */}
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-3">
                        <Avatar name={user.name} />
                        <div>
                          <div className="font-display font-medium text-sm" style={{ color: 'var(--t-text)' }}>
                            {user.name}
                          </div>
                          <div className="font-mono text-[10px] opacity-60" style={{ color: 'var(--t-muted)' }}>
                            ID: {user.id}
                          </div>
                        </div>
                      </div>
                    </td>

                    {/* Email */}
                    <td className="px-4 py-3 font-mono text-xs" style={{ color: 'var(--t-muted)' }}>
                      {user.email}
                    </td>

                    {/* Role — inline change */}
                    <td className="px-4 py-3">
                      <PermissionGuard permission="users:update"
                        fallback={
                          <span className="font-mono text-xs px-2 py-1 rounded"
                            style={{ background: 'var(--t-accent-alpha)', color: 'var(--t-accent)', border: '1px solid var(--t-accent-border)' }}>
                            {user.role_name ?? 'No Role'}
                          </span>
                        }>
                        <select
                          value={user.role_id ?? ''}
                          onChange={e => e.target.value ? void handleRoleChange(user, Number(e.target.value)) : undefined}
                          className="font-mono text-xs rounded-lg px-2 py-1.5 outline-none cursor-pointer"
                          style={{
                            background: 'rgba(255,255,255,0.04)',
                            border: '1px solid var(--t-border-alpha)',
                            color: 'var(--t-text)',
                          }}
                          onFocus={e  => { e.currentTarget.style.borderColor = 'var(--t-accent)' }}
                          onBlur={e   => { e.currentTarget.style.borderColor = 'var(--t-border-alpha)' }}>
                          <option value="">No Role</option>
                          {roles.map(r => <option key={r.id} value={r.id}>{r.role_name}</option>)}
                        </select>
                      </PermissionGuard>
                    </td>

                    {/* Status — click to toggle */}
                    <td className="px-4 py-3">
                      <PermissionGuard permission="users:update"
                        fallback={
                          <span className="flex items-center gap-1.5 font-mono text-xs" style={{ color: sc.text }}>
                            <span className={`status-dot ${sc.dot}`} />{user.status}
                          </span>
                        }>
                        <button onClick={() => void handleToggleStatus(user)}
                          className="flex items-center gap-1.5 font-mono text-xs transition-opacity hover:opacity-70"
                          style={{ color: sc.text }}
                          title={`Click to set ${user.status === 'active' ? 'inactive' : 'active'}`}>
                          <span className={`status-dot ${sc.dot}`} />
                          {user.status === 'active' ? 'Active' : 'Inactive'}
                        </button>
                      </PermissionGuard>
                    </td>

                    {/* Actions */}
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-1">
                        <PermissionGuard permission="users:update">
                          <button onClick={() => openEdit(user)} title="Edit user"
                            className="p-1.5 rounded transition-colors"
                            style={{ color: 'var(--t-muted)' }}
                            onMouseEnter={e => { e.currentTarget.style.color = 'var(--t-accent)' }}
                            onMouseLeave={e => { e.currentTarget.style.color = 'var(--t-muted)' }}>
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                              <path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/>
                              <path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/>
                            </svg>
                          </button>
                        </PermissionGuard>
                        <PermissionGuard permission="users:delete">
                          <button onClick={() => void handleDelete(user)} title="Delete user"
                            className="p-1.5 rounded transition-colors"
                            style={{ color: 'var(--t-muted)' }}
                            onMouseEnter={e => { e.currentTarget.style.color = '#ff3366' }}
                            onMouseLeave={e => { e.currentTarget.style.color = 'var(--t-muted)' }}>
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                              <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/>
                            </svg>
                          </button>
                        </PermissionGuard>
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
        {users.length === 0 && (
          <div className="py-12 text-center font-mono text-xs" style={{ color: 'var(--t-muted)' }}>
            No users found. Create the first one.
          </div>
        )}
      </GlassCard>

      {/* ── Create / Edit modal ──────────────────────────────────────────── */}
      {showModal && (
        <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4"
          onClick={() => setShowModal(false)}>
          <div className="glass rounded-xl p-6 w-full max-w-md shadow-2xl"
            style={{ border: '1px solid rgba(0,212,255,0.25)' }}
            onClick={e => e.stopPropagation()}>

            <h3 className="font-display font-bold text-lg mb-1" style={{ color: 'var(--t-accent)' }}>
              {editingUser ? '✏ Edit User' : '+ New User'}
            </h3>
            <p className="font-mono text-xs mb-5" style={{ color: 'var(--t-muted)' }}>
              {editingUser
                ? 'Update user details. Leave password blank to keep current.'
                : 'Fill in all fields to create a new user.'}
            </p>

            <div className="space-y-4">
              {/* Name */}
              <FormField label="FULL NAME" required>
                <input value={fName} onChange={e => setFName(e.target.value)}
                  placeholder="John Doe"
                  className="w-full rounded-lg px-3 py-2.5 font-mono text-sm outline-none"
                  style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid var(--t-border-alpha)', color: 'var(--t-text)' }}
                  onFocus={e => { e.currentTarget.style.borderColor = 'var(--t-accent)' }}
                  onBlur={e  => { e.currentTarget.style.borderColor = 'var(--t-border-alpha)' }}
                />
              </FormField>

              {/* Email */}
              <FormField label="EMAIL ADDRESS" required>
                <input type="email" value={fEmail} onChange={e => setFEmail(e.target.value)}
                  placeholder="user@company.com"
                  className="w-full rounded-lg px-3 py-2.5 font-mono text-sm outline-none"
                  style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid var(--t-border-alpha)', color: 'var(--t-text)' }}
                  onFocus={e => { e.currentTarget.style.borderColor = 'var(--t-accent)' }}
                  onBlur={e  => { e.currentTarget.style.borderColor = 'var(--t-border-alpha)' }}
                />
              </FormField>

              {/* Password */}
              <FormField label={editingUser ? 'PASSWORD (optional)' : 'PASSWORD'} required={!editingUser}>
                <input type="password" value={fPassword} onChange={e => setFPassword(e.target.value)}
                  placeholder={editingUser ? 'Leave blank to keep current' : 'Min 6 characters'}
                  className="w-full rounded-lg px-3 py-2.5 font-mono text-sm outline-none"
                  style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid var(--t-border-alpha)', color: 'var(--t-text)' }}
                  onFocus={e => { e.currentTarget.style.borderColor = 'var(--t-accent)' }}
                  onBlur={e  => { e.currentTarget.style.borderColor = 'var(--t-border-alpha)' }}
                />
              </FormField>

              {/* Role + Status row */}
              <div className="grid grid-cols-2 gap-3">
                <FormField label="ROLE">
                  <select value={fRoleId ?? ''}
                    onChange={e => setFRoleId(e.target.value ? Number(e.target.value) : null)}
                    className="w-full rounded-lg px-3 py-2.5 font-mono text-sm outline-none cursor-pointer"
                    style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid var(--t-border-alpha)', color: 'var(--t-text)' }}
                    onFocus={e => { e.currentTarget.style.borderColor = 'var(--t-accent)' }}
                    onBlur={e  => { e.currentTarget.style.borderColor = 'var(--t-border-alpha)' }}>
                    <option value="">No Role</option>
                    {roles.map(r => <option key={r.id} value={r.id}>{r.role_name}</option>)}
                  </select>
                </FormField>

                <FormField label="STATUS">
                  <select value={fStatus} onChange={e => setFStatus(e.target.value)}
                    className="w-full rounded-lg px-3 py-2.5 font-mono text-sm outline-none cursor-pointer"
                    style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid var(--t-border-alpha)', color: 'var(--t-text)' }}
                    onFocus={e => { e.currentTarget.style.borderColor = 'var(--t-accent)' }}
                    onBlur={e  => { e.currentTarget.style.borderColor = 'var(--t-border-alpha)' }}>
                    <option value="active">Active</option>
                    <option value="inactive">Inactive</option>
                  </select>
                </FormField>
              </div>
            </div>

            {/* Modal actions */}
            <div className="flex gap-2 justify-end mt-6">
              <button onClick={() => setShowModal(false)}
                className="rounded-lg px-4 py-2.5 font-mono text-xs transition-all hover:opacity-80"
                style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid var(--t-border-alpha)', color: 'var(--t-muted)' }}>
                Cancel
              </button>
              <button
                onClick={() => void handleSubmit()}
                disabled={
                  modalSaving ||
                  !fName.trim() ||
                  !fEmail.trim() ||
                  (!editingUser && fPassword.length < 6)
                }
                className="rounded-lg px-5 py-2.5 font-mono text-xs font-semibold transition-all disabled:opacity-50 flex items-center gap-2"
                style={{ background: 'var(--t-accent)', color: '#fff', border: '1px solid var(--t-accent-border)' }}>
                {modalSaving
                  ? <><span className="w-3 h-3 rounded-full border animate-spin inline-block" style={{ borderColor: '#fff', borderTopColor: 'transparent' }}/> Saving…</>
                  : editingUser ? '✓ Update User' : '+ Create User'
                }
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

/* ── small form label helper ─────────────────────────────────────────────── */
function FormField({ label, required, children }: {
  label: string; required?: boolean; children: React.ReactNode
}) {
  return (
    <div>
      <label className="font-mono text-xs block mb-1.5" style={{ color: 'var(--t-muted)' }}>
        {label}{required && <span style={{ color: '#ff3366' }}> *</span>}
      </label>
      {children}
    </div>
  )
}
