import { useCallback, useEffect, useState } from 'react'
import GlassCard from '../components/GlassCard'
import { PermissionGuard } from '../components/PermissionGuard'
import TablePagination from '../components/TablePagination'
import { useTablePagination } from '../hooks/useTablePagination'
import { toast, confirmDanger } from '../lib/swal'
import { listDeviceCredentials, createDeviceCredential, updateDeviceCredential, deleteDeviceCredential, listDeviceOptions, scanSSHHostKey, trustSSHHostKey, revokeSSHHostKey, testRemoteAccess, type DeviceCredentialRecord, type DeviceOptionRecord, type SSHHostKeyMetadata } from '../lib/api'
import { useAuth } from '../components/AuthContext'

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (<div><label className="font-mono text-xs block mb-1" style={{ color: 'var(--t-muted)' }}>{label}</label>{children}</div>)
}

const inputStyle: React.CSSProperties = { background: 'var(--t-border-light, rgba(255,255,255,0.04))', border: '1px solid var(--t-border-alpha)', color: 'var(--t-text)', outline: 'none' }

export default function DeviceCredentials() {
  const [items, setItems] = useState<DeviceCredentialRecord[]>([])
  const [devices, setDevices] = useState<DeviceOptionRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [showModal, setShowModal] = useState(false)
  const [editing, setEditing] = useState<DeviceCredentialRecord | null>(null)
  const [saving, setSaving] = useState(false)
  const [search, setSearch] = useState('')
  const [fDeviceId, setFDeviceId] = useState<number>(0)
  const [fType, setFType] = useState('snmp_v2c')
  const [fUsername, setFUsername] = useState('')
  const [fPassword, setFPassword] = useState('')
  const [fCommunity, setFCommunity] = useState('')
  const [fPort, setFPort] = useState(22)
  const [fAuthType, setFAuthType] = useState<'password' | 'private_key'>('password')
  const [hostKey, setHostKey] = useState<SSHHostKeyMetadata | null>(null)
  const [hostKeyId, setHostKeyId] = useState<number | null>(null)
  const [hostKeyLoading, setHostKeyLoading] = useState(false)
  const [hostKeyError, setHostKeyError] = useState('')
  const [testLoading, setTestLoading] = useState(false)
  const [testError, setTestError] = useState('')
  const { hasPermission } = useAuth()

  const load = useCallback(async () => {
    try {
      const [credsData, devicesData] = await Promise.all([listDeviceCredentials(), listDeviceOptions()])
      setItems(credsData)
      setDevices(devicesData)
    } catch (e) { toast.error(e instanceof Error ? e.message : 'Failed to load') }
    setLoading(false)
  }, [])

  useEffect(() => { void load() }, [load])

  function clearHostKey() { setHostKey(null); setHostKeyId(null); setHostKeyError(''); setTestError('') }
  function openCreate() { setEditing(null); setFDeviceId(devices[0]?.id || 0); setFType('snmp_v2c'); setFUsername(''); setFPassword(''); setFCommunity('public'); setFPort(22); setFAuthType('password'); clearHostKey(); setShowModal(true) }
  function openEdit(item: DeviceCredentialRecord) { setEditing(item); setFDeviceId(item.device_id); setFType(item.credential_type); setFUsername(item.username ?? ''); setFPassword(''); setFCommunity(''); setFPort(22); setFAuthType('password'); clearHostKey(); setShowModal(true) }

  function changeDevice(id: number) { setFDeviceId(id); if (fType === 'ssh') clearHostKey() }
  function changeType(type: string) { setFType(type); if (type !== 'ssh') clearHostKey() }

  async function handleScanHostKey() {
    if (!hasPermission('remote_access:manage_credentials') || !fDeviceId || fPort < 1 || fPort > 65535) return
    setHostKeyLoading(true); setHostKeyError(''); clearHostKey()
    try {
      const result = await scanSSHHostKey(fDeviceId, fPort)
      setHostKey(result)
      setHostKeyId(result.id)
    } catch (e) { setHostKeyError(e instanceof Error ? e.message : 'Host-key scan failed') }
    finally { setHostKeyLoading(false) }
  }

  async function handleHostKeyAction(action: 'trust' | 'revoke') {
    if (!hostKeyId) { setHostKeyError('Host-key record id is unavailable; scan again after the backend returns it.'); return }
    try { setHostKey(action === 'trust' ? await trustSSHHostKey(hostKeyId) : await revokeSSHHostKey(hostKeyId)) }
    catch (e) { setHostKeyError(e instanceof Error ? e.message : 'Host-key update failed') }
  }

  async function handleTestConnection() {
    if (!fDeviceId || !fUsername.trim() || !fPassword) { setTestError('Device, username, and authentication secret are required.'); return }
    setTestLoading(true); setTestError('')
    try {
      const result = await testRemoteAccess({ device_id: fDeviceId, protocol: 'ssh', port: fPort, username: fUsername.trim(), secret: fPassword, auth_type: fAuthType, remember_credential: false })
      if (!result.success) setTestError([result.stage, result.error_code, result.message].filter(Boolean).join(' · ') || 'Connection failed')
      else toast.success('SSH connection verified')
    } catch (e) { setTestError(e instanceof Error ? e.message : 'Connection test failed') }
    finally { setTestLoading(false) }
  }

  async function handleSubmit() {
    if (!fDeviceId) { toast.warning('Device required'); return }
    setSaving(true)
    try {
      const data: any = { device_id: fDeviceId, credential_type: fType, username: fUsername.trim() || null }
      if (fPassword.trim()) data.password = fPassword.trim()
      if (fCommunity.trim()) data.community_string = fCommunity.trim()
      if (editing) {
        await updateDeviceCredential(editing.id, data)
        toast.success('Updated')
      } else {
        await createDeviceCredential(data)
        toast.success('Created')
      }
      setShowModal(false)
      await load()
    } catch (e) { toast.error(e instanceof Error ? e.message : 'Save failed') }
    setSaving(false)
  }

  async function handleDelete(item: DeviceCredentialRecord) {
    const ok = await confirmDanger({ title: `Delete credential?`, text: 'Cannot be undone.', confirmText: 'Delete' })
    if (!ok) return
    try { await deleteDeviceCredential(item.id); toast.success('Deleted'); await load() } catch (e) { toast.error(e instanceof Error ? e.message : 'Delete failed') }
  }

  const filtered = items.filter(i => !search.trim() || i.credential_type.toLowerCase().includes(search.toLowerCase()))
  const deviceMap = new Map(devices.map(device => [device.id, device]))
  const pagination = useTablePagination(filtered)

  if (loading) {
    return (<div className="p-6 flex items-center justify-center min-h-[50vh]"><div className="flex flex-col items-center gap-3"><div className="w-8 h-8 rounded-full border-2 animate-spin" style={{ borderColor: 'var(--t-accent)', borderTopColor: 'transparent' }} /><span className="font-mono text-xs" style={{ color: 'var(--t-muted)' }}>LOADING…</span></div></div>)
  }

  return (
    <div className="p-4 md:p-6 space-y-5">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div><h1 className="font-display font-bold text-xl md:text-2xl" style={{ color: 'var(--t-text)' }}>Device Credentials</h1><p className="font-mono text-xs mt-1" style={{ color: 'var(--t-muted)' }}>{items.length} credential{items.length !== 1 ? 's' : ''} • Encrypted Storage</p></div>
        <div className="flex gap-2">
          <input value={search} onChange={e => { setSearch(e.target.value); pagination.setPage(1) }} placeholder="Search…" className="rounded-lg px-3 py-2 font-mono text-xs" style={{ ...inputStyle, minWidth: 160 }} onFocus={e => { e.currentTarget.style.borderColor = 'var(--t-accent)' }} onBlur={e => { e.currentTarget.style.borderColor = 'var(--t-border-alpha)' }} />
          <PermissionGuard permission="device_credentials:create"><button onClick={openCreate} className="rounded-lg px-4 py-2 font-display font-semibold text-sm flex items-center gap-2 hover:opacity-90 transition-all" style={{ background: 'var(--t-accent)', color: '#fff', border: '1px solid var(--t-accent-border)' }}><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><path d="M12 5v14M5 12h14"/></svg>New</button></PermissionGuard>
        </div>
      </div>

      <GlassCard className="overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left" style={{ minWidth: 640 }}>
            <thead><tr style={{ borderBottom: '1px solid var(--t-border-light)' }}>{['Device', 'Type', 'Username', 'Created', 'Actions'].map(h => (<th key={h} className="px-4 py-3 font-mono text-xs uppercase tracking-wider" style={{ color: 'var(--t-muted)' }}>{h}</th>))}</tr></thead>
            <tbody>
              {pagination.paginatedItems.map(item => {
                const device = deviceMap.get(item.device_id)
                return (
                  <tr key={item.id} style={{ borderBottom: '1px solid var(--t-border-alpha)' }} onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = 'rgba(0,212,255,0.03)' }} onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = '' }}>
                    <td className="px-4 py-3 font-display font-medium text-sm" style={{ color: 'var(--t-text)' }}>{device ? device.hostname : `Device #${item.device_id}`}</td>
                    <td className="px-4 py-3 font-mono text-xs" style={{ color: 'var(--t-muted)' }}>{item.credential_type}</td>
                    <td className="px-4 py-3 font-mono text-xs" style={{ color: 'var(--t-muted)' }}>{item.username || '—'}</td>
                    <td className="px-4 py-3 font-mono text-xs" style={{ color: 'var(--t-muted)' }}>{new Date(item.created_at).toLocaleDateString('en-IN', { timeZone: 'Asia/Kolkata' })}</td>
                    <td className="px-4 py-3">
                      <div className="flex gap-1">
                        <PermissionGuard permission="device_credentials:update"><button onClick={() => openEdit(item)} title="Edit" className="p-1.5 rounded transition-colors" style={{ color: 'var(--t-muted)' }} onMouseEnter={e => { e.currentTarget.style.color = 'var(--t-accent)' }} onMouseLeave={e => { e.currentTarget.style.color = 'var(--t-muted)' }}><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/></svg></button></PermissionGuard>
                        <PermissionGuard permission="device_credentials:delete"><button onClick={() => handleDelete(item)} title="Delete" className="p-1.5 rounded transition-colors" style={{ color: 'var(--t-muted)' }} onMouseEnter={e => { e.currentTarget.style.color = '#ff3366' }} onMouseLeave={e => { e.currentTarget.style.color = 'var(--t-muted)' }}><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/></svg></button></PermissionGuard>
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
        {filtered.length === 0 && (<div className="py-12 text-center font-mono text-xs" style={{ color: 'var(--t-muted)' }}>{search ? 'No matches.' : 'No credentials yet.'}</div>)}
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
            <h3 className="font-display font-bold text-lg mb-4" style={{ color: 'var(--t-accent)' }}>{editing ? '✏ Edit Credential' : '🔒 New Credential'}</h3>
            <div className="space-y-4">
              <Field label="DEVICE *"><select value={fDeviceId} onChange={e => changeDevice(Number(e.target.value))} className="w-full rounded-lg px-3 py-2.5 font-mono text-sm" style={inputStyle}>{devices.map(d => (<option key={d.id} value={d.id}>{d.hostname} ({d.ip_address})</option>))}</select></Field>
              <Field label="TYPE"><select value={fType} onChange={e => changeType(e.target.value)} className="w-full rounded-lg px-3 py-2.5 font-mono text-sm" style={inputStyle}><option value="snmp_v2c">SNMP v2c</option><option value="snmp_v3">SNMP v3</option><option value="ssh">SSH</option><option value="api">API</option></select></Field>
              {fType === 'ssh' && <>
                <Field label="HOST"><input readOnly value={devices.find(d => d.id === fDeviceId)?.ip_address ?? ''} className="w-full rounded-lg px-3 py-2.5 font-mono text-sm opacity-75" style={inputStyle} /></Field>
                <Field label="SSH PORT"><input type="number" min={1} max={65535} value={fPort} onChange={e => { setFPort(Number(e.target.value)); clearHostKey() }} className="w-full rounded-lg px-3 py-2.5 font-mono text-sm" style={inputStyle} /></Field>
                <Field label="AUTHENTICATION"><select value={fAuthType} onChange={e => setFAuthType(e.target.value as 'password' | 'private_key')} className="w-full rounded-lg px-3 py-2.5 font-mono text-sm" style={inputStyle}><option value="password">Password</option><option value="private_key">Private Key</option></select></Field>
              </>}
              {(fType === 'ssh' || fType === 'snmp_v3' || fType === 'api') && <Field label="USERNAME"><input value={fUsername} onChange={e => setFUsername(e.target.value)} placeholder="admin" className="w-full rounded-lg px-3 py-2.5 font-mono text-sm" style={inputStyle} onFocus={e => { e.currentTarget.style.borderColor = 'var(--t-accent)' }} onBlur={e => { e.currentTarget.style.borderColor = 'var(--t-border-alpha)' }}/></Field>}
              {(fType === 'ssh' || fType === 'snmp_v3') && <Field label="PASSWORD"><input type="password" value={fPassword} onChange={e => setFPassword(e.target.value)} placeholder={editing ? '(unchanged)' : 'password'} className="w-full rounded-lg px-3 py-2.5 font-mono text-sm" style={inputStyle} onFocus={e => { e.currentTarget.style.borderColor = 'var(--t-accent)' }} onBlur={e => { e.currentTarget.style.borderColor = 'var(--t-border-alpha)' }}/></Field>}
              {fType === 'snmp_v2c' && <Field label="COMMUNITY STRING"><input value={fCommunity} onChange={e => setFCommunity(e.target.value)} placeholder="public" className="w-full rounded-lg px-3 py-2.5 font-mono text-sm" style={inputStyle} onFocus={e => { e.currentTarget.style.borderColor = 'var(--t-accent)' }} onBlur={e => { e.currentTarget.style.borderColor = 'var(--t-border-alpha)' }}/></Field>}
              {fType === 'ssh' && <div className="rounded-lg p-3 space-y-3" style={{ border: '1px solid var(--t-border-alpha)' }}>
                <div className="font-display font-semibold text-sm" style={{ color: 'var(--t-text)' }}>Host Key</div>
                {hasPermission('remote_access:manage_credentials') && <button type="button" onClick={() => void handleScanHostKey()} disabled={hostKeyLoading || !fDeviceId || !Number.isInteger(fPort) || fPort < 1 || fPort > 65535} className="rounded-lg px-3 py-2 font-mono text-xs disabled:opacity-50" style={{ background: 'var(--t-accent)', color: '#fff' }}>{hostKeyLoading ? 'Scanning…' : 'Scan Host Key'}</button>}
                {hostKeyError && <div className="font-mono text-xs" style={{ color: '#ff6688' }}>{hostKeyError}</div>}
                {hostKey && <div className="space-y-1 font-mono text-xs" style={{ color: 'var(--t-muted)' }}><div>Key type: <span style={{ color: 'var(--t-text)' }}>{hostKey.key_type}</span></div><div>Fingerprint: <span style={{ color: 'var(--t-text)' }}>{hostKey.fingerprint}</span></div><div>Status: <span style={{ color: 'var(--t-text)' }}>{hostKey.status}</span></div>{hasPermission('remote_access:manage_credentials') && hostKeyId && hostKey.status === 'PENDING' && <button type="button" onClick={() => void handleHostKeyAction('trust')} className="mt-2 rounded-lg px-3 py-2" style={{ background: 'var(--t-accent)', color: '#fff' }}>Trust Host Key</button>}{hasPermission('remote_access:manage_credentials') && hostKeyId && hostKey.status === 'TRUSTED' && <button type="button" onClick={() => void handleHostKeyAction('revoke')} className="mt-2 rounded-lg px-3 py-2" style={{ background: 'transparent', border: '1px solid var(--t-border-alpha)', color: 'var(--t-text)' }}>Revoke Trust</button>}</div>}
              </div>}
              {fType === 'ssh' && <div><button type="button" onClick={() => void handleTestConnection()} disabled={testLoading} className="rounded-lg px-3 py-2 font-mono text-xs disabled:opacity-50" style={{ background: 'var(--t-border-light)', color: 'var(--t-text)' }}>{testLoading ? 'Testing…' : 'Test Connection'}</button>{testError && <div className="font-mono text-xs mt-2" style={{ color: '#ff6688' }}>{testError}</div>}</div>}
            </div>
            <div className="flex gap-2 justify-end mt-6">
              <button onClick={() => setShowModal(false)} className="rounded-lg px-4 py-2 font-mono text-xs hover:opacity-80 transition-all" style={{ background: 'var(--t-border-light, rgba(255,255,255,0.05))', border: '1px solid var(--t-border-alpha)', color: 'var(--t-muted)' }}>Cancel</button>
              <button onClick={() => void handleSubmit()} disabled={saving || !fDeviceId} className="rounded-lg px-5 py-2 font-mono text-xs font-semibold transition-all disabled:opacity-50 flex items-center gap-2" style={{ background: 'var(--t-accent)', color: '#fff', border: '1px solid var(--t-accent-border)' }}>{saving ? <><span className="w-3 h-3 rounded-full border animate-spin inline-block" style={{ borderColor:'#fff',borderTopColor:'transparent' }}/> Saving…</> : editing ? '✓ Update' : '🔒 Create'}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
