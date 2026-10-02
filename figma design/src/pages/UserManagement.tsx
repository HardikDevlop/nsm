import Swal from 'sweetalert2'
import { useEffect, useState, useCallback } from 'react'
import GlassCard from '../components/GlassCard'
import { PermissionGuard } from '../components/PermissionGuard'
import { useAuth } from '../components/AuthContext'
import TablePagination from '../components/TablePagination'
import { useTablePagination } from '../hooks/useTablePagination'
import { toast, confirmDanger } from '../lib/swal'
import {
  listUsers, createUser, updateUser, deleteUser, assignUserRole, updateUserStatus,
  listRoles, listSites, getUserSites, replaceUserSites,
  type UserRecord, type RoleRecord, type UserStatus,
} from '../lib/api'

/* ── helpers ────────────────────────────────────────────────────────────── */
const STATUS_COLORS: Record<string, { text: string; dot: string }> = {
  active:   { text: '#00ff88', dot: 'online'  },
  disabled: { text: '#f59e0b', dot: 'offline' },
  blocked:  { text: '#ff3366', dot: 'offline' },
  locked:   { text: '#a855f7', dot: 'offline' },
}

const STATUS_LABELS: Record<UserStatus, string> = {
  active: 'Active',
  disabled: 'Disabled',
  suspended: 'Suspended',
  
}

function targetAuthority(user: UserRecord): number | null {
  const level = (user as UserRecord & { authority_level?: number | null }).authority_level
  return typeof level === 'number' && Number.isFinite(level) ? level : null
}

function roleAuthority(role: RoleRecord): number | null {
  const level = (role as RoleRecord & { authority_level?: number | null }).authority_level
  return typeof level === 'number' && Number.isFinite(level) ? level : null
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
  const [siteModalUser, setSiteModalUser] = useState<UserRecord | null>(null)
  const [sites, setSites] = useState<Array<{ id: number; name: string }>>([])
  const [assignedSiteIds, setAssignedSiteIds] = useState<Set<number>>(new Set())
  const [sitesLoading, setSitesLoading] = useState(false)
  const [sitesSaving, setSitesSaving] = useState(false)
  const [sitesError, setSitesError] = useState('')
  const { user: currentUser, authorityLevel, isSuperAdmin, canManageAuthority } = useAuth()

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

  useEffect(() => {
    void load()
    const timer = window.setInterval(() => { void load() }, 10000)
    return () => window.clearInterval(timer)
  }, [load])

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

  /* ── status actions ───────────────────────────────────────────────────── */
  async function handleStatusChange(user: UserRecord, status: UserStatus) {
    if (status === user.status && status !== 'suspended') return
    let suspendedUntil: string | undefined
    if (status === 'suspended') {
      const dates = await Swal.fire({
        title: 'Suspension period',
        html: '<label>From <input id="suspend-from" type="datetime-local" class="swal2-input"></label><label>Until <input id="suspend-until" type="datetime-local" class="swal2-input"></label>',
        showCancelButton: true,
        confirmButtonText: 'Continue',
        preConfirm: () => {
          const from = (document.getElementById('suspend-from') as HTMLInputElement)?.value
          const until = (document.getElementById('suspend-until') as HTMLInputElement)?.value
          if (!from || !until || new Date(until) <= new Date(from)) { Swal.showValidationMessage('Select a valid From and Until time'); return false }
          return { from, until }
        },
      })
      if (!dates.isConfirmed) return
      suspendedUntil = dates.value.until
    }
    const action = status === 'active' ? 'Activate' : status === 'disabled' ? 'Disable' : 'Suspend'
    if (status !== 'active') {
      const ok = await confirmDanger({
        title: `${action} ${user.name}?`,
        text: status === 'suspended' ? `Confirm suspension of ${user.name} for the selected date range.` : `This will set the account status to ${STATUS_LABELS[status]}.`,
        confirmText: action,
      })
      if (!ok) return
    }
    try {
      await updateUserStatus(user.id, status, suspendedUntil)
      toast.info(`${user.name} is now ${STATUS_LABELS[status]}`)
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

  const assignableRoles = roles.filter(role => {
    const level = roleAuthority(role)
    const assignable = (role as RoleRecord & { is_assignable?: boolean }).is_assignable
    return assignable !== false && level !== null && (isSuperAdmin ? level < 100 : canManageAuthority(level))
  })

  const pagination = useTablePagination(users)

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
                    style={{ color: 'var(--t-text)', background: 'var(--t-table-header)', borderBottom: '1px solid var(--t-border-alpha)' }}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {pagination.paginatedItems.map(user => {
                const sc = STATUS_COLORS[user.status] ?? { text: 'var(--t-muted, #8899bb)', dot: 'unknown' }
                const targetLevel = targetAuthority(user)
                const canManage = currentUser?.id !== user.id && (
                  isSuperAdmin
                    ? targetLevel !== null && targetLevel < 100
                    : canManageAuthority(targetLevel)
                )
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
                      {canManage && <PermissionGuard permission="users:update"
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
                            background: 'var(--t-border-light, rgba(255,255,255,0.04))',
                            border: '1px solid var(--t-border-alpha)',
                            color: 'var(--t-text)',
                          }}
                          onFocus={e  => { e.currentTarget.style.borderColor = 'var(--t-accent)' }}
                          onBlur={e   => { e.currentTarget.style.borderColor = 'var(--t-border-alpha)' }}>
                          <option value="">No Role</option>
                          {assignableRoles.map(r => <option key={r.id} value={r.id}>{r.role_name}</option>)}
                        </select>
                      </PermissionGuard>}
                    </td>

                    {/* Status */}
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <span className="inline-flex items-center gap-1.5 rounded-full px-2 py-1 font-mono text-xs"
                          style={{ color: sc.text, background: `${sc.text}1a`, border: `1px solid ${sc.text}55` }}>
                          <span className={`status-dot ${sc.dot}`} />
                          {STATUS_LABELS[user.status as UserStatus] ?? user.status}
                        </span>
                        {canManage && <PermissionGuard permission="users:update">
                          <select
                            value={user.status}
                            onChange={e => void handleStatusChange(user, e.target.value as UserStatus)}
                            className="rounded-lg px-2 py-1 font-mono text-xs outline-none"
                            style={{ background: 'var(--t-border-light, rgba(255,255,255,0.04))', border: '1px solid var(--t-border-alpha)', color: sc.text }}
                            title="Change user status">
                            {(Object.keys(STATUS_LABELS) as UserStatus[]).map(status => (
                              <option key={status} value={status}>{STATUS_LABELS[status]}</option>
                            ))}
                          </select>
                        </PermissionGuard>}
                        {isSuperAdmin && user.status === 'suspended' && (
                          <button type="button" onClick={() => void handleStatusChange(user, 'suspended')} className="rounded px-2 py-1 font-mono text-[10px]" style={{ color: '#a855f7', border: '1px solid #a855f755' }} title="Apply a new suspension period">
                            Re-suspend
                          </button>
                        )}
                      </div>
                    </td>

                    {/* Actions */}
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-1">
                        {canManage && <PermissionGuard permission="users:update">
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
                        </PermissionGuard>}
                        {canManage && <PermissionGuard permission="users:update">
                          <button onClick={() => void openSiteModal(user)} title="Manage sites"
                            className="px-2 py-1 rounded font-mono text-[10px] transition-colors"
                            style={{ color: 'var(--t-accent)', border: '1px solid var(--t-accent-border)', background: 'var(--t-accent-alpha)' }}>
                            Sites
                          </button>
                        </PermissionGuard>}
                        {canManage && <PermissionGuard permission="users:delete">
                          <button onClick={() => void handleDelete(user)} title="Delete user"
                            className="p-1.5 rounded transition-colors"
                            style={{ color: 'var(--t-muted)' }}
                            onMouseEnter={e => { e.currentTarget.style.color = '#ff3366' }}
                            onMouseLeave={e => { e.currentTarget.style.color = 'var(--t-muted)' }}>
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                              <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/>
                            </svg>
                          </button>
                        </PermissionGuard>}
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
        {users.length > 0 && (
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

      {siteModalUser && (
        <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4" onClick={() => !sitesSaving && setSiteModalUser(null)}>
          <div className="glass rounded-xl p-6 w-full max-w-md shadow-2xl" style={{ border: '1px solid rgba(0,212,255,0.25)' }} onClick={e => e.stopPropagation()}>
            <h3 className="font-display font-bold text-lg mb-1" style={{ color: 'var(--t-accent)' }}>Manage Sites</h3>
            <p className="font-mono text-xs mb-4" style={{ color: 'var(--t-muted)' }}>Assign sites for {siteModalUser.name}. Empty selection removes all assignments.</p>
            {sitesLoading ? <div className="py-8 text-center font-mono text-xs" style={{ color: 'var(--t-muted)' }}>Loading sites…</div> : sitesError ? <div className="rounded-lg p-3 font-mono text-xs" style={{ color: '#ff3366', background: 'rgba(255,51,102,.08)', border: '1px solid rgba(255,51,102,.3)' }}>{sitesError}</div> : (
              <div className="max-h-64 overflow-y-auto space-y-2">
                {sites.length === 0 ? <div className="py-6 text-center font-mono text-xs" style={{ color: 'var(--t-muted)' }}>No accessible sites available.</div> : sites.map(site => (
                  <label key={site.id} className="flex items-center gap-3 rounded-lg px-3 py-2 cursor-pointer" style={{ background: 'var(--t-border-light)', border: '1px solid var(--t-border-alpha)' }}>
                    <input type="checkbox" checked={assignedSiteIds.has(site.id)} onChange={() => setAssignedSiteIds(prev => { const next = new Set(prev); next.has(site.id) ? next.delete(site.id) : next.add(site.id); return next })} />
                    <span className="font-mono text-sm" style={{ color: 'var(--t-text)' }}>{site.name}</span>
                  </label>
                ))}
              </div>
            )}
            <div className="flex gap-2 justify-end mt-6">
              <button onClick={() => setSiteModalUser(null)} disabled={sitesSaving} className="rounded-lg px-4 py-2.5 font-mono text-xs" style={{ background: 'var(--t-border-light)', border: '1px solid var(--t-border-alpha)', color: 'var(--t-muted)' }}>Cancel</button>
              <button onClick={() => void saveSiteAssignments()} disabled={sitesLoading || sitesSaving || !!sitesError} className="rounded-lg px-5 py-2.5 font-mono text-xs font-semibold disabled:opacity-50" style={{ background: 'var(--t-accent)', color: '#fff' }}>{sitesSaving ? 'Saving…' : 'Save'}</button>
            </div>
          </div>
        </div>
      )}

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
                  style={{ background: 'var(--t-border-light, rgba(255,255,255,0.04))', border: '1px solid var(--t-border-alpha)', color: 'var(--t-text)' }}
                  onFocus={e => { e.currentTarget.style.borderColor = 'var(--t-accent)' }}
                  onBlur={e  => { e.currentTarget.style.borderColor = 'var(--t-border-alpha)' }}
                />
              </FormField>

              {/* Email */}
              <FormField label="EMAIL ADDRESS" required>
                <input type="email" value={fEmail} onChange={e => setFEmail(e.target.value)}
                  placeholder="user@company.com"
                  className="w-full rounded-lg px-3 py-2.5 font-mono text-sm outline-none"
                  style={{ background: 'var(--t-border-light, rgba(255,255,255,0.04))', border: '1px solid var(--t-border-alpha)', color: 'var(--t-text)' }}
                  onFocus={e => { e.currentTarget.style.borderColor = 'var(--t-accent)' }}
                  onBlur={e  => { e.currentTarget.style.borderColor = 'var(--t-border-alpha)' }}
                />
              </FormField>

              {/* Password */}
              <FormField label={editingUser ? 'PASSWORD (optional)' : 'PASSWORD'} required={!editingUser}>
                <input type="password" value={fPassword} onChange={e => setFPassword(e.target.value)}
                  placeholder={editingUser ? 'Leave blank to keep current' : 'Min 6 characters'}
                  className="w-full rounded-lg px-3 py-2.5 font-mono text-sm outline-none"
                  style={{ background: 'var(--t-border-light, rgba(255,255,255,0.04))', border: '1px solid var(--t-border-alpha)', color: 'var(--t-text)' }}
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
                    style={{ background: 'var(--t-border-light, rgba(255,255,255,0.04))', border: '1px solid var(--t-border-alpha)', color: 'var(--t-text)' }}
                    onFocus={e => { e.currentTarget.style.borderColor = 'var(--t-accent)' }}
                    onBlur={e  => { e.currentTarget.style.borderColor = 'var(--t-border-alpha)' }}>
                    <option value="">No Role</option>
                    {assignableRoles.map(r => <option key={r.id} value={r.id}>{r.role_name}</option>)}
                  </select>
                </FormField>

                {!editingUser && (
                <FormField label="STATUS">
                  <select value={fStatus} onChange={e => setFStatus(e.target.value)}
                    className="w-full rounded-lg px-3 py-2.5 font-mono text-sm outline-none cursor-pointer"
                    style={{ background: 'var(--t-border-light, rgba(255,255,255,0.04))', border: '1px solid var(--t-border-alpha)', color: 'var(--t-text)' }}
                    onFocus={e => { e.currentTarget.style.borderColor = 'var(--t-accent)' }}
                    onBlur={e  => { e.currentTarget.style.borderColor = 'var(--t-border-alpha)' }}>
                    <option value="active">Active</option>
                    <option value="disabled">Disabled</option>
                  </select>
                </FormField>
                )}
              </div>
            </div>

            {/* Modal actions */}
            <div className="flex gap-2 justify-end mt-6">
              <button onClick={() => setShowModal(false)}
                className="rounded-lg px-4 py-2.5 font-mono text-xs transition-all hover:opacity-80"
                style={{ background: 'var(--t-border-light, rgba(255,255,255,0.05))', border: '1px solid var(--t-border-alpha)', color: 'var(--t-muted)' }}>
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
