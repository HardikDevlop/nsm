/**
 * SNMPDiscoveryPanel — discovers SNMP-enabled devices and shows results
 * in structured, richly formatted device cards.
 */
import { useState } from 'react'
import GlassCard from '../../../components/GlassCard'
import { addDiscoveredDevices, checkStoredDevices, discoverDevice, discoverSNMP, type SNMPDiscoveryResponse } from '../../../lib/api'
import { toast } from '../../../lib/swal'

// Import buildUrl and ensureAuth for API calls
const DEFAULT_API_BASE = '/api/v1'
const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? DEFAULT_API_BASE).replace(/\/$/, '')
function buildUrl(path: string) {
  return `${API_BASE}${path.startsWith('/') ? path : `/${path}`}`
}
async function ensureAuth(): Promise<string> {
  const token = window.localStorage.getItem('nms_access_token')
  if (!token) throw new Error('Not authenticated')
  return token
}

/* ── helpers ─────────────────────────────────────────────────────────────── */
function fmtUptime(seconds: unknown): string {
  const s = Number(seconds)
  if (!s || isNaN(s)) return '—'
  const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60)
  if (d > 0) return `${d}d ${h}h ${m}m`
  if (h > 0) return `${h}h ${m}m`
  return `${m}m`
}

function clean(v: unknown, fallback = '—'): string {
  const s = String(v ?? '').trim()
  return s && s !== 'Not Supported' && s !== 'None' && s !== 'null' ? s : fallback
}

const INPUT = "w-full rounded-lg px-3 py-2 font-mono text-xs outline-none"
const INPUT_STYLE = { background: 'rgba(4,14,33,0.85)', border: '1px solid rgba(0,212,255,0.2)', color: '#c8d8ee' } as const
const SEL_STYLE  = { background: '#041021', border: '1px solid rgba(0,212,255,0.2)', color: '#c8d8ee' } as const

function parseIPv4(value: string): number[] | null {
  const parts = value.trim().split('.')
  if (parts.length !== 4 || parts.some(part => !/^\d{1,3}$/.test(part))) return null
  const numbers = parts.map(Number)
  return numbers.every(part => part >= 0 && part <= 255) ? numbers : null
}

function ipv4ToNumber(parts: number[]): number {
  return (((parts[0] * 256) + parts[1]) * 256 + parts[2]) * 256 + parts[3]
}

function numberToIPv4(value: number): string {
  return [value >>> 24, (value >>> 16) & 255, (value >>> 8) & 255, value & 255].join('.')
}

/* ── SNMP result card ────────────────────────────────────────────────────── */
function SNMPResultCard({
  ip, data, stored, onStore,
}: {
  ip: string
  data: Record<string, unknown>
  stored: boolean
  onStore: () => void
}) {
  const colData = data.collectors as Record<string, {supported?: boolean; data?: Record<string, any>}> | undefined
  const systemData = colData?.system?.data || {}
  const hostname  = clean(data.hostname ?? data.sysName ?? systemData.hostname, ip)
  const descr     = clean(data.sysDescr ?? data.description ?? systemData.description)
  const vendor    = clean(data.vendor ?? data.snmp_vendor ?? systemData.vendor)
  const model     = clean(data.model ?? systemData.model)
  const uptimeData = (data.uptime_seconds ?? systemData.uptime_seconds ?? systemData.uptime) as any
  const uptime    = fmtUptime(typeof uptimeData === 'object' ? uptimeData?.seconds : uptimeData)
  const version   = clean(data.snmp_version, 'SNMP')

  /* collectors data */
  const cpu     = colData?.cpu?.data?.overall_percent as number | undefined
  const mem     = colData?.memory?.data?.utilization_percent as number | undefined
  const ifaces  = colData?.interfaces?.data as { interface_count?: number; up_count?: number } | undefined
  
  /* capabilities - show Yes/No for each module */
  const capabilities = [
    { name: 'CPU', supported: colData?.cpu?.supported ?? false },
    { name: 'Memory', supported: colData?.memory?.supported ?? false },
    { name: 'Storage', supported: colData?.storage?.supported ?? false },
    { name: 'Interfaces', supported: colData?.interfaces?.supported ?? false },
    { name: 'Environment', supported: colData?.environment?.supported ?? false },
    { name: 'LLDP', supported: colData?.lldp?.supported ?? false },
    { name: 'Routing', supported: colData?.routing?.supported ?? false },
    { name: 'VLANs', supported: colData?.vlan?.supported ?? false },
  ]

  return (
    <div className="rounded-xl overflow-hidden transition-all"
      style={{ border: stored ? '1px solid rgba(0,255,136,0.25)' : '1px solid rgba(0,212,255,0.15)', background: stored ? 'rgba(0,255,136,0.03)' : 'rgba(0,212,255,0.03)' }}>

      {/* top bar */}
      <div className="flex items-center justify-between px-4 py-2.5"
        style={{ borderBottom: '1px solid rgba(0,212,255,0.08)', background: 'rgba(0,0,0,0.2)' }}>
        <div className="flex items-center gap-2.5">
          <span className="w-2 h-2 rounded-full shrink-0"
            style={{ background: '#00ff88', boxShadow: '0 0 6px #00ff88' }}/>
          <span className="font-mono text-sm font-bold" style={{ color: '#00d4ff' }}>{ip}</span>
          <span className="font-mono text-xs" style={{ color: '#c8d8ee' }}>{hostname !== ip ? hostname : ''}</span>
          <span className="font-mono text-[10px] px-1.5 py-0.5 rounded"
            style={{ background: 'rgba(0,212,255,0.1)', color: '#00d4ff', border: '1px solid rgba(0,212,255,0.2)' }}>
            {version.toUpperCase()}
          </span>
          {stored && (
            <span className="font-mono text-[10px] px-1.5 py-0.5 rounded"
              style={{ background: 'rgba(0,255,136,0.12)', color: '#00ff88', border: '1px solid rgba(0,255,136,0.25)' }}>
              ✓ STORED
            </span>
          )}
        </div>
        {!stored && (
          <button onClick={onStore}
            className="font-mono text-xs px-3 py-1 rounded transition-all hover:opacity-80 shrink-0"
            style={{ background: 'rgba(0,212,255,0.12)', border: '1px solid rgba(0,212,255,0.3)', color: '#00d4ff' }}>
            + ADD
          </button>
        )}
      </div>

      {/* body */}
      <div className="px-4 py-3 grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-x-6 gap-y-2">
        {[
          { l: 'Hostname',  v: hostname !== ip ? hostname : '—' },
          { l: 'Vendor',    v: vendor },
          { l: 'Model',     v: model },
          { l: 'Uptime',    v: uptime },
          cpu  !== undefined ? { l: 'CPU',    v: `${cpu.toFixed(1)}%`,   c: cpu > 80 ? '#ff3366' : '#00ff88' } : null,
          mem  !== undefined ? { l: 'Memory', v: `${mem.toFixed(1)}%`,   c: mem > 85 ? '#ffaa00' : '#00ff88' } : null,
          ifaces ? { l: 'Interfaces', v: `${ifaces.up_count ?? 0}/${ifaces.interface_count ?? 0} up`, c: '#00d4ff' } : null,
        ].filter(Boolean).map(item => {
          const it = item as { l: string; v: string; c?: string }
          return (
            <div key={it.l}>
              <div className="font-mono text-[10px]" style={{ color: '#556677' }}>{it.l}</div>
              <div className="font-mono text-xs truncate" style={{ color: it.c ?? '#c8d8ee' }}>{it.v}</div>
            </div>
          )
        })}
      </div>

      {/* capabilities badges */}
      <div className="px-4 pb-3">
        <div className="font-mono text-[10px] mb-1.5" style={{ color: '#556677' }}>Capabilities</div>
        <div className="flex flex-wrap gap-1.5">
          {capabilities.map(({ name, supported }) => (
            <span key={name}
              className="font-mono text-[10px] px-2 py-0.5 rounded"
              style={{
                background: supported ? 'rgba(0,255,136,0.1)' : 'rgba(255,51,102,0.1)',
                color: supported ? '#00ff88' : '#ff3366',
                border: `1px solid ${supported ? 'rgba(0,255,136,0.25)' : 'rgba(255,51,102,0.25)'}`,
              }}>
              {name}: {supported ? 'Yes' : 'No'}
            </span>
          ))}
        </div>
      </div>

      {/* sysDescr strip */}
      {descr !== '—' && (
        <div className="px-4 pb-3">
          <div className="font-mono text-[10px]" style={{ color: '#556677' }}>Description</div>
          <div className="font-mono text-[11px] leading-relaxed" style={{ color: '#8899bb' }}>
            {descr.length > 160 ? descr.slice(0, 160) + '…' : descr}
          </div>
        </div>
      )}
    </div>
  )
}

/* ── main panel ──────────────────────────────────────────────────────────── */
export default function SNMPDiscoveryPanel({
  compact = false,
  onCompleted,
}: {
  compact?: boolean
  onCompleted?: () => Promise<void> | void
}) {
  const [ips,             setIps]             = useState('192.168.100.1')
  const [scanMode,        setScanMode]        = useState<'single' | 'range' | 'full'>('single')
  const [rangeStart,      setRangeStart]      = useState('192.168.100.1')
  const [rangeEnd,        setRangeEnd]        = useState('192.168.100.254')
  const [fullPrefix,      setFullPrefix]      = useState('192.168.100')
  const [version,         setVersion]         = useState<'v2c'|'v3'>('v3')
  const [community,       setCommunity]       = useState('public')
  const [username,        setUsername]        = useState('Agnigate')
  const [authProtocol,    setAuthProtocol]    = useState('MD5')
  const [authPassword,    setAuthPassword]    = useState('Gate@123')
  const [privacyProtocol, setPrivacyProtocol] = useState('DES')
  const [privacyPassword, setPrivacyPassword] = useState('Gate@123')
  const [securityLevel,   setSecurityLevel]   = useState('authPriv')
  const [timeout,         setTimeout]         = useState('1')
  const [busy,            setBusy]            = useState(false)
  const [response,        setResponse]        = useState<SNMPDiscoveryResponse | null>(null)
  const [storedIps,       setStoredIps]       = useState<Set<string>>(new Set())
  const [scanProgress,    setScanProgress]    = useState({ scanned: 0, total: 0 })

  const run = async () => {
    setBusy(true)
    try {
      let addresses: string[] = []
      if (scanMode === 'single') {
        const single = parseIPv4(ips)
        if (!single) {
          toast.warning('Please enter one valid IPv4 address.')
          setBusy(false)
          return
        }
        addresses = [numberToIPv4(ipv4ToNumber(single))]
      } else if (scanMode === 'range') {
        const start = parseIPv4(rangeStart)
        const end = parseIPv4(rangeEnd)
        if (!start || !end || ipv4ToNumber(start) > ipv4ToNumber(end)) {
          toast.warning('Enter a valid start and end IP range')
          setBusy(false)
          return
        }
        const first = ipv4ToNumber(start)
        const last = ipv4ToNumber(end)
        if (last - first + 1 > 255) {
          toast.warning('IP range cannot be larger than 255 addresses')
          setBusy(false)
          return
        }
        addresses = Array.from({ length: last - first + 1 }, (_, index) => numberToIPv4(first + index))
      } else {
        const prefix = fullPrefix.trim().split('.')
        if (prefix.length !== 3 || prefix.some(part => !/^\d+$/.test(part) || Number(part) < 0 || Number(part) > 255)) {
          toast.warning('Full discovery needs a prefix like 192.168.100')
          setBusy(false)
          return
        }
        addresses = Array.from({ length: 255 }, (_, host) => `${prefix.join('.')}.${host}`)
      }
      if (!addresses.length) { toast.warning('Enter at least one IP address'); setBusy(false); return }
      setResponse(null)
      setStoredIps(new Set())
      setScanProgress({ scanned: 0, total: addresses.length })
      let results: Record<string, Record<string, unknown>> = {}
      try {
        const result = await discoverSNMP({
          ips: addresses, snmp_version: version, timeout_seconds: Number(timeout) || 1,
          communities: version === 'v2c' ? [community] : undefined,
          username:    version === 'v3' ? username : null,
          auth_protocol:    version === 'v3' && securityLevel !== 'noAuthNoPriv' ? authProtocol    : null,
          auth_password:    version === 'v3' && securityLevel !== 'noAuthNoPriv' ? authPassword    : null,
          privacy_protocol: version === 'v3' && securityLevel === 'authPriv'    ? privacyProtocol : null,
          privacy_password: version === 'v3' && securityLevel === 'authPriv'    ? privacyPassword : null,
          security_level: version === 'v3' ? securityLevel : null,
        })
        results = result.results
      } catch {
        // A scan with no responders is shown as an empty result set.
      }
      setScanProgress({ scanned: addresses.length, total: addresses.length })
      setResponse({ scanned: addresses.length, count: Object.keys(results).length, results })
      // Mark devices that are already in inventory before rendering result actions.
      // This keeps the ADD action limited to genuinely new devices.
      const discoveredIps = Object.keys(results)
      if (discoveredIps.length > 0) {
        try {
          const stored = await checkStoredDevices(discoveredIps)
          setStoredIps(new Set(stored.stored_ips))
        } catch {
          // Keep the existing empty state if the optional inventory check fails.
        }
      }
      toast.success(`${Object.keys(results).length}/${addresses.length} device(s) responded to SNMP`)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'SNMP discovery failed')
    }
    setBusy(false)
  }

  const storeAll = async () => {
    if (!response) return
    setBusy(true)
    try {
      const devices = Object.entries(response.results).map(([ip, data]) => {
        const collectors = (data as any).collectors || {}
        const capabilities: Record<string, boolean> = {}
        Object.keys(collectors).forEach(key => {
          capabilities[key] = collectors[key]?.supported === true
        })
        return {
          ip_address: ip,
          ...data,
          capabilities // Include capabilities
        }
      })
      
      const saved = await addDiscoveredDevices({
        devices,
        site_id: null,
        discovery_source: 'snmp',
        snmp_version: version,
        communities: version === 'v2c' ? [community] : undefined,
        username: version === 'v3' ? username : null,
        auth_protocol: version === 'v3' && securityLevel !== 'noAuthNoPriv' ? authProtocol : null,
        auth_password: version === 'v3' && securityLevel !== 'noAuthNoPriv' ? authPassword : null,
        privacy_protocol: version === 'v3' && securityLevel === 'authPriv' ? privacyProtocol : null,
        privacy_password: version === 'v3' && securityLevel === 'authPriv' ? privacyPassword : null,
        security_level: version === 'v3' ? securityLevel : null,
      })
      const ips = Object.keys(response.results)
      setStoredIps(new Set(ips))
      toast.success(`${saved.added_count} device(s) saved, ${saved.skipped_count} skipped`)
      await onCompleted?.()
      setBusy(false)

      // Enrichment is intentionally non-blocking. The inventory row is
      // already persisted; full SNMP discovery and monitoring can finish later.
      void Promise.all((saved.added || []).map(async addedDevice => {
        const deviceId = Number((addedDevice as any).id)
        if (!deviceId) return
        try {
          await discoverDevice(deviceId)
        } catch (err) {
          console.warn(`Full SNMP discovery failed for device ${deviceId}`, err)
        }
      })).then(async () => {
        if (!saved.added?.length) return
        try {
          const token = await ensureAuth()
          await Promise.all(saved.added.map(async addedDevice => {
            const device = addedDevice as any
            const collectors = (response.results[device.ip_address] as any)?.collectors || {}
            const modulesToStart = ['cpu', 'memory', 'storage', 'interfaces'].filter(module => collectors[module]?.supported)
            await Promise.all(modulesToStart.map(async module => {
              const moduleResponse = await fetch(buildUrl(`/snmp/devices/${device.id}/monitoring/${module}/start`), {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
                body: JSON.stringify({ module_name: module, interval_seconds: 60 }),
              })
              if (!moduleResponse.ok) console.warn(`Failed to start ${module} monitoring:`, await moduleResponse.text())
            }))
          }))
        } catch (err) {
          console.warn('Background monitoring setup failed', err)
        }
      }).catch(err => console.warn('Background device enrichment failed', err))
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Storage failed')
      setBusy(false)
    }
  }

  const storeSingle = async (ip: string, data: Record<string, unknown>) => {
    setBusy(true)
    try {
      // Extract capabilities from collectors
      const collectors = (data as any).collectors || {}
      const capabilities: Record<string, boolean> = {}
      Object.keys(collectors).forEach(key => {
        capabilities[key] = collectors[key]?.supported === true
      })
      
      // Add capabilities to device data
      const devicePayload = {
        ip_address: ip,
        ...data,
        capabilities // Include capabilities in payload
      }
      
      const saved = await addDiscoveredDevices({
        devices: [devicePayload],
        site_id: null,
        discovery_source: 'snmp',
        snmp_version: version,
        communities: version === 'v2c' ? [community] : undefined,
        username: version === 'v3' ? username : null,
        auth_protocol: version === 'v3' && securityLevel !== 'noAuthNoPriv' ? authProtocol : null,
        auth_password: version === 'v3' && securityLevel !== 'noAuthNoPriv' ? authPassword : null,
        privacy_protocol: version === 'v3' && securityLevel === 'authPriv' ? privacyProtocol : null,
        privacy_password: version === 'v3' && securityLevel === 'authPriv' ? privacyPassword : null,
        security_level: version === 'v3' ? securityLevel : null,
      })
      setStoredIps(prev => new Set([...prev, ip]))
      await onCompleted?.()
      setBusy(false)

      if (saved.added_count > 0) {
        toast.success(`${ip} saved to database`)
        const addedDevice = saved.added?.[0] as any
        void (async () => {
          if (!addedDevice?.id) return
          try {
            await discoverDevice(Number(addedDevice.id))
          } catch (err) {
            console.warn(`Full SNMP discovery failed for device ${addedDevice.id}`, err)
          }
          const modulesToStart = ['cpu', 'memory', 'storage', 'interfaces'].filter(module => collectors[module]?.supported)
          if (!modulesToStart.length) return
          try {
            const token = await ensureAuth()
            await Promise.all(modulesToStart.map(async module => {
              const moduleResponse = await fetch(buildUrl(`/snmp/devices/${addedDevice.id}/monitoring/${module}/start`), {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
                body: JSON.stringify({ module_name: module, interval_seconds: 60 }),
              })
              if (!moduleResponse.ok) console.warn(`Failed to start ${module} monitoring:`, await moduleResponse.text())
            }))
          } catch (err) {
            console.warn(`Background monitoring setup failed for ${ip}`, err)
          }
        })()
      } else toast.info(`${ip} already exists in database`)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Storage failed')
      setBusy(false)
    }
  }

  const resultCount = response ? Object.keys(response.results).length : 0

  return (
    <GlassCard className="p-4">
      {/* header */}
      <div className="flex items-center justify-between gap-2 mb-4">
        <div>
          <div className="font-display font-bold text-sm tracking-wider neon-cyan">DISCOVER SNMP DEVICES</div>
          <div className="font-mono text-xs mt-0.5" style={{ color: '#8899bb' }}>
            Scan a single IP or range, verify the response, and add devices to monitoring.
          </div>
        </div>
        <span className="font-mono text-[10px] px-2 py-1 rounded"
          style={{ color: busy ? '#ffaa00' : '#00ff88', background: busy ? 'rgba(255,170,0,0.1)' : 'rgba(0,255,136,0.1)', border: `1px solid ${busy ? 'rgba(255,170,0,0.3)' : 'rgba(0,255,136,0.3)'}` }}>
          {busy ? `● SCANNING ${scanProgress.scanned}/${scanProgress.total}` : '● READY'}
        </span>
      </div>

      {/* inputs */}
      <div className={`grid gap-2 ${compact ? 'md:grid-cols-2' : 'md:grid-cols-3 xl:grid-cols-4'}`}>
        <select value={scanMode} onChange={e => setScanMode(e.target.value as 'single' | 'range' | 'full')}
          className="rounded-lg px-2 py-2 font-mono text-xs" style={SEL_STYLE}>
          <option value="single">SINGLE IP</option>
          <option value="range">IP RANGE</option>
          <option value="full">FULL DISCOVERY (0-255)</option>
        </select>
        {scanMode === 'single' && <div className="md:col-span-2">
          <input value={ips} onChange={e => setIps(e.target.value.replace(/[^\d.]/g, ''))}
            placeholder="Single IPv4, e.g. 192.168.1.10"
            className={INPUT} style={INPUT_STYLE}/>
          <div className="font-mono text-[10px] mt-1" style={{ color: '#8899bb' }}>
            Enter one address only. Range mode allows 192.168.1.1 to 192.168.1.255 (maximum 255 IPs).
          </div>
        </div>}
        {scanMode === 'range' && <>
          <input value={rangeStart} onChange={e => setRangeStart(e.target.value.replace(/[^\d.]/g, ''))}
            placeholder="Start: 192.168.1.1" className={INPUT} style={INPUT_STYLE}/>
          <input value={rangeEnd} onChange={e => setRangeEnd(e.target.value.replace(/[^\d.]/g, ''))}
            placeholder="End: 192.168.1.255" className={INPUT} style={INPUT_STYLE}/>
        </>}
        {scanMode === 'full' && <div className="md:col-span-2">
          <input value={fullPrefix} onChange={e => setFullPrefix(e.target.value.replace(/[^\d.]/g, ''))}
            placeholder="Network prefix, e.g. 192.168.100" className={INPUT} style={INPUT_STYLE}/>
          <div className="font-mono text-[10px] mt-1" style={{ color: '#8899bb' }}>
            Scans {fullPrefix || 'x.x.x'}.0 through {fullPrefix || 'x.x.x'}.254 (maximum 255 IPs).
          </div>
        </div>}
        <select value={version} onChange={e => setVersion(e.target.value as 'v2c'|'v3')}
          className="rounded-lg px-2 py-2 font-mono text-xs" style={SEL_STYLE}>
          <option value="v3">SNMPv3</option>
          <option value="v2c">SNMPv2c</option>
        </select>
        {version === 'v2c'
          ? <input value={community} onChange={e => setCommunity(e.target.value)}
              placeholder="Community string" className={INPUT} style={INPUT_STYLE}/>
          : <>
              <input value={username} onChange={e => setUsername(e.target.value)}
                placeholder="Username" className={INPUT} style={INPUT_STYLE}/>
              <select value={securityLevel} onChange={e => setSecurityLevel(e.target.value)}
                className="rounded-lg px-2 py-2 font-mono text-xs" style={SEL_STYLE}>
                <option>noAuthNoPriv</option><option>authNoPriv</option><option>authPriv</option>
              </select>
              {securityLevel !== 'noAuthNoPriv' && <>
                <select value={authProtocol} onChange={e => setAuthProtocol(e.target.value)}
                  className="rounded-lg px-2 py-2 font-mono text-xs" style={SEL_STYLE}>
                  <option value="MD5">MD5</option>
                  <option value="SHA">SHA</option>
                </select>
                <input type="password" value={authPassword} onChange={e => setAuthPassword(e.target.value)}
                  placeholder="Auth Password" className={INPUT} style={INPUT_STYLE}/>
              </>}
              {securityLevel === 'authPriv' && <>
                <select value={privacyProtocol} onChange={e => setPrivacyProtocol(e.target.value)}
                  className="rounded-lg px-2 py-2 font-mono text-xs" style={SEL_STYLE}>
                  <option value="DES">DES</option>
                  <option value="AES">AES</option>
                </select>
                <input type="password" value={privacyPassword} onChange={e => setPrivacyPassword(e.target.value)}
                  placeholder="Privacy Password" className={INPUT} style={INPUT_STYLE}/>
              </>}
            </>
        }
        <input value={timeout} onChange={e => setTimeout(e.target.value)}
          placeholder="Timeout (sec)" className={INPUT} style={INPUT_STYLE}/>
      </div>

      {/* actions */}
      <div className="mt-4 flex flex-wrap items-center gap-3">
        <button onClick={() => void run()} disabled={busy}
          className="rounded-lg px-5 py-2 font-display text-xs tracking-wider font-semibold transition-all disabled:opacity-50 flex items-center gap-2"
          style={{ background: busy ? 'rgba(255,170,0,0.12)' : 'rgba(0,212,255,0.15)', border: `1px solid ${busy ? 'rgba(255,170,0,0.4)' : 'rgba(0,212,255,0.4)'}`, color: busy ? '#ffaa00' : '#00d4ff' }}>
          {busy
            ? <><span className="w-3 h-3 rounded-full border animate-spin inline-block" style={{ borderColor: '#ffaa00', borderTopColor: 'transparent' }}/> DISCOVERING…</>
            : '▶ DISCOVER & STORE'
          }
        </button>
        {resultCount > 0 && (
          <button onClick={() => void storeAll()} disabled={busy || storedIps.size === resultCount}
            className="rounded-lg px-5 py-2 font-display text-xs tracking-wider font-semibold transition-all disabled:opacity-50"
            style={{ background: 'rgba(0,255,136,0.12)', border: '1px solid rgba(0,255,136,0.35)', color: '#00ff88' }}>
            STORE ALL ({resultCount - storedIps.size} new)
          </button>
        )}
        {resultCount > 0 && (
          <span className="font-mono text-xs" style={{ color: '#8899bb' }}>
            {resultCount} device{resultCount !== 1 ? 's' : ''} found · {storedIps.size} stored
          </span>
        )}
      </div>

      {/* results */}
      {response && resultCount > 0 && (
        <div className="mt-5 space-y-3">
          <div className="font-display font-bold text-sm tracking-wider neon-cyan">
            SNMP DISCOVERY RESULTS — {resultCount} device{resultCount !== 1 ? 's' : ''}
          </div>
          {Object.entries(response.results).map(([ip, data]) => (
            <SNMPResultCard
              key={ip}
              ip={ip}
              data={data as Record<string, unknown>}
              stored={storedIps.has(ip)}
              onStore={() => void storeSingle(ip, data as Record<string, unknown>)}
            />
          ))}
        </div>
      )}

      {response && resultCount === 0 && (
        <div className="mt-4 p-4 rounded-lg text-center font-mono text-xs"
          style={{ background: 'rgba(255,170,0,0.06)', border: '1px solid rgba(255,170,0,0.2)', color: '#8899bb' }}>
          No SNMP responses received. Check credentials and that SNMP is enabled on target devices.
        </div>
      )}
    </GlassCard>
  )
}
