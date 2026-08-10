import { useState } from 'react'
import GlassCard from './GlassCard'
import { addDiscoveredDevices, discoverSNMP, type SNMPDiscoveryResponse } from '../lib/api'

export default function SNMPDiscoveryPanel({ compact = false, onCompleted }: { compact?: boolean; onCompleted?: () => Promise<void> | void }) {
  const [ips, setIps] = useState('192.168.100.10')
  const [version, setVersion] = useState<'v2c' | 'v3'>('v3')
  const [community, setCommunity] = useState('public')
  const [username, setUsername] = useState('Agnigate')
  const [authProtocol, setAuthProtocol] = useState('SHA')
  const [authPassword, setAuthPassword] = useState('Gate@123')
  const [privacyProtocol, setPrivacyProtocol] = useState('AES128')
  const [privacyPassword, setPrivacyPassword] = useState('Gate@123')
  const [securityLevel, setSecurityLevel] = useState('authNoPriv')
  const [timeout, setTimeoutValue] = useState('2')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [response, setResponse] = useState<SNMPDiscoveryResponse | null>(null)
  const [storeMessage, setStoreMessage] = useState<string | null>(null)

  const run = async () => {
    setBusy(true); setError(null)
    try {
      const addresses = ips.split(/[\s,]+/).map(ip => ip.trim()).filter(Boolean)
      if (!addresses.length) throw new Error('Enter at least one IP address')
      const result = await discoverSNMP({
        ips: addresses, snmp_version: version, timeout_seconds: Number(timeout) || 2,
        communities: version === 'v2c' ? [community] : undefined,
        username: version === 'v3' ? username : null,
        auth_protocol: version === 'v3' && securityLevel !== 'noAuthNoPriv' ? authProtocol : null,
        auth_password: version === 'v3' && securityLevel !== 'noAuthNoPriv' ? authPassword : null,
        privacy_protocol: version === 'v3' && securityLevel === 'authPriv' ? privacyProtocol : null,
        privacy_password: version === 'v3' && securityLevel === 'authPriv' ? privacyPassword : null,
        security_level: version === 'v3' ? securityLevel : null,
      })
      setResponse(result)
      setStoreMessage(null)
    } catch (err) { setError(err instanceof Error ? err.message : 'SNMP discovery failed') }
    finally { setBusy(false) }
  }

  const store = async () => {
    if (!response) return
    setBusy(true); setError(null)
    try {
      const devices = Object.entries(response.results).map(([ip, data]) => ({ ip_address: ip, ...data }))
      const saved = await addDiscoveredDevices({ devices, site_id: null })
      setStoreMessage(`${saved.added_count} device(s) saved; ${saved.skipped_count} skipped`)
      await onCompleted?.()
    } catch (err) { setError(err instanceof Error ? err.message : 'Device storage failed') }
    finally { setBusy(false) }
  }

  const input = (value: string, set: (v: string) => void, placeholder?: string) => (
    <input value={value} onChange={e => set(e.target.value)} placeholder={placeholder} className="w-full rounded border px-2 py-2 font-mono text-xs outline-none" style={{ background: 'rgba(4,14,33,0.85)', borderColor: 'rgba(0,212,255,0.2)', color: '#c8d8ee' }} />
  )

  return <GlassCard className="p-4">
    <div className="flex items-center justify-between gap-2 mb-3">
      <div><div className="font-display font-bold text-sm tracking-wider neon-cyan">SNMP DEVICE DISCOVERY</div><div className="font-mono text-xs mt-1" style={{ color: '#8899bb' }}>Discover and store devices dynamically</div></div>
      <span className="font-mono text-xs" style={{ color: busy ? '#ffaa00' : '#00ff88' }}>{busy ? 'POLLING…' : 'READY'}</span>
    </div>
    <div className={`grid gap-2 ${compact ? 'md:grid-cols-2' : 'md:grid-cols-3 xl:grid-cols-4'}`}>
      <div className="md:col-span-2">{input(ips, setIps, 'IP addresses separated by spaces or commas')}</div>
      <select value={version} onChange={e => setVersion(e.target.value as 'v2c' | 'v3')} className="rounded border px-2 py-2 font-mono text-xs" style={{ background: '#041021', color: '#c8d8ee', borderColor: 'rgba(0,212,255,0.2)' }}><option value="v3">SNMPv3</option><option value="v2c">SNMPv2c</option></select>
      {version === 'v2c' ? input(community, setCommunity, 'Community') : <>{input(username, setUsername, 'Username')}<select value={securityLevel} onChange={e => setSecurityLevel(e.target.value)} className="rounded border px-2 py-2 font-mono text-xs" style={{ background: '#041021', color: '#c8d8ee', borderColor: 'rgba(0,212,255,0.2)' }}><option>noAuthNoPriv</option><option>authNoPriv</option><option>authPriv</option></select>{securityLevel !== 'noAuthNoPriv' && <>{input(authProtocol, setAuthProtocol)}{input(authPassword, setAuthPassword)}</>}{securityLevel === 'authPriv' && <>{input(privacyProtocol, setPrivacyProtocol)}{input(privacyPassword, setPrivacyPassword)}</>}</>}
      <div>{input(timeout, setTimeoutValue, 'Timeout seconds')}</div>
    </div>
    <div className="mt-3 flex items-center gap-3"><button onClick={run} disabled={busy} className="rounded px-4 py-2 font-display text-xs tracking-wider disabled:opacity-50" style={{ background: 'rgba(0,212,255,0.16)', border: '1px solid rgba(0,212,255,0.3)', color: '#c8d8ee' }}>{busy ? 'DISCOVERING…' : 'DISCOVER & STORE'}</button>{error && <span className="font-mono text-xs" style={{ color: '#ff3366' }}>{error}</span>}</div>
    {response && <div className="mt-4"><div className="flex items-center gap-3 mb-2"><div className="font-mono text-xs" style={{ color: '#00ff88' }}>{response.count}/{response.scanned} device(s) discovered</div><button onClick={store} disabled={busy} className="rounded px-3 py-1.5 font-display text-xs disabled:opacity-50" style={{ background: 'rgba(0,255,136,0.12)', border: '1px solid rgba(0,255,136,0.3)', color: '#00ff88' }}>STORE DISCOVERED</button>{storeMessage && <span className="font-mono text-xs" style={{ color: '#00ff88' }}>{storeMessage}</span>}</div><div className="grid gap-2">{Object.entries(response.results).map(([ip, data]) => { const fallback = `device-${ip.replaceAll('.', '-')}`; return <div key={ip} className="rounded border p-3 font-mono text-xs" style={{ borderColor: 'rgba(0,212,255,0.15)' }}><div style={{ color: '#00d4ff' }}>{ip} · {String(data.hostname ?? data.sysName ?? fallback)}</div><div style={{ color: '#8899bb' }}>{String(data.sysDescr ?? 'Not Supported')} · {String(data.vendor ?? 'Not Supported')} · uptime {String(data.uptime_seconds ?? 'Not Supported')}s</div></div> })}</div></div>}
  </GlassCard>
}
