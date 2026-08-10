/**
 * SNMPSubnetDiscovery — Dynamic SNMP sweep for an entire subnet.
 *
 * Accepts the current subnet from the ISP discovery target (e.g. 192.168.1.0/24),
 * generates all .1–.254 host IPs, fires discoverSNMP in configurable batches,
 * and streams live per-device results as they come in.
 *
 * No IP address is hardcoded — everything is derived from the subnet prop.
 */

import { useCallback, useState } from 'react'
import GlassCard from './GlassCard'
import { addDiscoveredDevices, discoverSNMP } from '../lib/api'

// ── helpers ───────────────────────────────────────────────────────────────────

function subnetToHostIPs(cidr: string): string[] {
  try {
    const [base, prefixStr] = cidr.split('/')
    const prefix = parseInt(prefixStr ?? '24', 10)
    const parts = base.split('.').map(Number)
    if (parts.length !== 4 || parts.some(isNaN)) return []

    // For /24 and similar — just iterate the last octet .1–.254
    if (prefix >= 24) {
      return Array.from({ length: 254 }, (_, i) => `${parts[0]}.${parts[1]}.${parts[2]}.${i + 1}`)
    }
    // For wider subnets cap at first 254 hosts for safety
    return Array.from({ length: 254 }, (_, i) => `${parts[0]}.${parts[1]}.${parts[2]}.${i + 1}`)
  } catch {
    return []
  }
}

function chunkArray<T>(arr: T[], size: number): T[][] {
  const chunks: T[][] = []
  for (let i = 0; i < arr.length; i += size) {
    chunks.push(arr.slice(i, i + size))
  }
  return chunks
}

// ── types ─────────────────────────────────────────────────────────────────────

interface DiscoveredSNMPDevice {
  ip: string
  hostname: string
  description: string
  vendor: string
  uptime: string
  version: string
  raw: Record<string, unknown>
}

interface SNMPSubnetDiscoveryProps {
  /** Current subnet from ISP discovery (e.g. "192.168.1.0/24") */
  subnet: string
  onDevicesStored?: () => void
}

// ── component ─────────────────────────────────────────────────────────────────

export default function SNMPSubnetDiscovery({ subnet, onDevicesStored }: SNMPSubnetDiscoveryProps) {
  const [expanded, setExpanded] = useState(true) // Start expanded when in modal

  // Scan mode: single IP, IP range, or full subnet
  const [scanMode, setScanMode] = useState<'single' | 'range' | 'subnet'>('single')
  const [singleIP, setSingleIP] = useState('')
  const [rangeStart, setRangeStart] = useState('')
  const [rangeEnd, setRangeEnd] = useState('')

  // SNMP credentials
  const [version, setVersion] = useState<'v2c' | 'v3'>('v2c')
  const [community, setCommunity] = useState('public')
  const [username, setUsername] = useState('')
  const [authProtocol, setAuthProtocol] = useState('SHA')
  const [authPassword, setAuthPassword] = useState('')
  const [privacyProtocol, setPrivacyProtocol] = useState('AES128')
  const [privacyPassword, setPrivacyPassword] = useState('')
  const [securityLevel, setSecurityLevel] = useState('authNoPriv')
  const [timeoutSec, setTimeoutSec] = useState('2')
  const [batchSize, setBatchSize] = useState('10')

  // State
  const [running, setRunning] = useState(false)
  const [scanned, setScanned] = useState(0)
  const [total, setTotal] = useState(0)
  const [found, setFound] = useState<DiscoveredSNMPDevice[]>([])
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState(false)
  const [storing, setStoring] = useState(false)
  const [storeMsg, setStoreMsg] = useState<string | null>(null)
  const [storedIps, setStoredIps] = useState<Set<string>>(new Set())

  const hostIPs = subnetToHostIPs(subnet)

  // ── helpers: generate IP list based on mode ───────────────────────────────

  const getTargetIPs = useCallback((): { ips: string[]; error?: string } => {
    if (scanMode === 'single') {
      const ip = singleIP.trim()
      if (!ip) return { ips: [], error: 'Enter an IP address' }
      return { ips: [ip] }
    }
    if (scanMode === 'range') {
      const start = rangeStart.trim()
      const end = rangeEnd.trim()
      if (!start || !end) return { ips: [], error: 'Enter both start and end IPs' }
      const startParts = start.split('.').map(Number)
      const endParts = end.split('.').map(Number)
      if (startParts.length !== 4 || endParts.length !== 4) return { ips: [], error: 'Invalid IP range format' }
      // Same /24: vary only last octet
      const prefix = startParts.slice(0, 3).join('.')
      const startLast = startParts[3]
      const endLast = endParts[3]
      if (startLast > endLast) return { ips: [], error: 'Start IP must be ≤ End IP' }
      const ips = Array.from({ length: endLast - startLast + 1 }, (_, i) => `${prefix}.${startLast + i}`)
      return { ips }
    }
    // subnet
    const ips = subnetToHostIPs(subnet)
    if (!ips.length) return { ips: [], error: 'Invalid subnet format. Expected e.g. 192.168.1.0/24' }
    return { ips }
  }, [scanMode, singleIP, rangeStart, rangeEnd, subnet])

  const run = useCallback(async () => {
    const { ips, error: ipError } = getTargetIPs()
    if (!ips.length) {
      setError(ipError ?? 'No IPs to scan')
      return
    }

    setRunning(true)
    setDone(false)
    setError(null)
    setFound([])
    setStoredIps(new Set())
    setStoreMsg(null)
    setScanned(0)
    setTotal(ips.length)

    const batch = Math.max(1, Math.min(50, parseInt(batchSize, 10) || 10))
    const chunks = chunkArray(ips, batch)

    let discovered: DiscoveredSNMPDevice[] = []

    for (const chunk of chunks) {
      try {
        const res = await discoverSNMP({
          ips: chunk,
          snmp_version: version,
          timeout_seconds: parseFloat(timeoutSec) || 2,
          communities: version === 'v2c' ? [community] : undefined,
          username: version === 'v3' ? username || undefined : null,
          auth_protocol: version === 'v3' && securityLevel !== 'noAuthNoPriv' ? authProtocol : null,
          auth_password: version === 'v3' && securityLevel !== 'noAuthNoPriv' ? authPassword : null,
          privacy_protocol: version === 'v3' && securityLevel === 'authPriv' ? privacyProtocol : null,
          privacy_password: version === 'v3' && securityLevel === 'authPriv' ? privacyPassword : null,
          security_level: version === 'v3' ? securityLevel : null,
        })

        // Add each responding device immediately for live feedback
        for (const [ip, data] of Object.entries(res.results)) {
          const d = data as Record<string, unknown>
          const device: DiscoveredSNMPDevice = {
            ip,
            hostname: String(d.hostname ?? d.sysName ?? `device-${ip}`),
            description: String(d.sysDescr ?? d.description ?? '—'),
            vendor: String(d.vendor ?? d.snmp_vendor ?? '—'),
            uptime: String(d.uptime_seconds != null ? `${Math.round(Number(d.uptime_seconds))}s` : '—'),
            version: String(d.snmp_version ?? version),
            raw: d,
          }
          discovered = [...discovered, device]
          setFound([...discovered])
        }
      } catch {
        // Chunk failed (timeout for whole batch) — continue to next chunk
      }

      setScanned(prev => Math.min(prev + chunk.length, ips.length))
    }

    setRunning(false)
    setDone(true)
  }, [getTargetIPs, version, community, username, authProtocol, authPassword, privacyProtocol, privacyPassword, securityLevel, timeoutSec, batchSize])

  const storeAll = async () => {
    if (found.length === 0) return
    setStoring(true)
    setStoreMsg(null)
    try {
      const devices = found.map(d => ({ ip_address: d.ip, hostname: d.hostname, ...d.raw }))
      const saved = await addDiscoveredDevices({ devices, site_id: null })
      setStoredIps(new Set(found.map(d => d.ip)))
      setStoreMsg(`${saved.added_count} device(s) saved, ${saved.skipped_count} skipped`)
      onDevicesStored?.()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to store devices')
    } finally {
      setStoring(false)
    }
  }

  const storeSingle = async (device: DiscoveredSNMPDevice) => {
    if (storedIps.has(device.ip)) return
    try {
      const saved = await addDiscoveredDevices({
        devices: [{ ip_address: device.ip, hostname: device.hostname, ...device.raw }],
        site_id: null,
      })
      if (saved.added_count > 0 || saved.skipped_count > 0) {
        setStoredIps(prev => new Set([...prev, device.ip]))
      }
      onDevicesStored?.()
    } catch {
      // silent — user can retry
    }
  }

  const progress = total > 0 ? Math.round((scanned / total) * 100) : 0

  return (
    <GlassCard className="overflow-hidden">
      {/* ── Header / Toggle ── */}
      <button
        className="w-full flex items-center justify-between p-4 transition-all hover:bg-cyan-400/5"
        onClick={() => setExpanded(e => !e)}
      >
        <div className="flex items-center gap-3">
          {/* SNMP icon */}
          <div
            className="w-9 h-9 rounded-lg flex items-center justify-center"
            style={{ background: 'rgba(0,212,255,0.1)', border: '1px solid rgba(0,212,255,0.25)' }}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#00d4ff" strokeWidth="1.8">
              <path d="M8.111 16.404a5.5 5.5 0 017.778 0M12 20h.01m-7.08-7.071c3.904-3.905 10.236-3.905 14.141 0M1.394 9.393c5.857-5.857 15.355-5.857 21.213 0" />
            </svg>
          </div>
          <div className="text-left">
            <div className="font-display font-bold text-sm tracking-wider neon-cyan">SNMP SUBNET DISCOVERY</div>
            <div className="font-mono text-xs mt-0.5" style={{ color: '#8899bb' }}>
              Scan {hostIPs.length} IPs in {subnet || '—'} for SNMP-enabled devices
            </div>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {/* Status badge */}
          {running && (
            <span className="font-mono text-[10px] px-2 py-1 rounded animate-pulse"
              style={{ background: 'rgba(255,170,0,0.15)', color: '#ffaa00', border: '1px solid rgba(255,170,0,0.3)' }}>
              SCANNING {scanned}/{total}
            </span>
          )}
          {done && !running && (
            <span className="font-mono text-[10px] px-2 py-1 rounded"
              style={{ background: found.length > 0 ? 'rgba(0,255,136,0.15)' : 'rgba(136,153,187,0.12)', color: found.length > 0 ? '#00ff88' : '#8899bb', border: `1px solid ${found.length > 0 ? 'rgba(0,255,136,0.3)' : 'rgba(136,153,187,0.2)'}` }}>
              {found.length} FOUND
            </span>
          )}
          <svg
            width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#8899bb" strokeWidth="2"
            style={{ transform: expanded ? 'rotate(180deg)' : 'rotate(0deg)', transition: 'transform 0.2s' }}
          >
            <path d="M19 9l-7 7-7-7" />
          </svg>
        </div>
      </button>

      {/* ── Expanded Body ── */}
      {expanded && (
        <div className="border-t px-4 pb-4 space-y-4" style={{ borderColor: 'rgba(0,212,255,0.1)' }}>

          {/* Scan Mode Tabs */}
          <div className="mt-4">
            <div className="font-mono text-[10px] mb-2 font-semibold uppercase tracking-wider" style={{ color: '#667799' }}>
              SCAN TARGET
            </div>
            <div className="flex gap-2 mb-3">
              {(['single', 'range', 'subnet'] as const).map(mode => (
                <button
                  key={mode}
                  onClick={() => setScanMode(mode)}
                  className="flex-1 px-3 py-2 rounded font-mono text-xs font-bold transition-all"
                  style={{
                    background: scanMode === mode ? 'rgba(0,212,255,0.2)' : 'rgba(0,0,0,0.3)',
                    border: `1px solid ${scanMode === mode ? 'rgba(0,212,255,0.5)' : 'rgba(0,212,255,0.15)'}`,
                    color: scanMode === mode ? '#00d4ff' : '#8899bb',
                  }}
                >
                  {mode === 'single' ? 'SINGLE IP' : mode === 'range' ? 'IP RANGE' : 'FULL SUBNET'}
                </button>
              ))}
            </div>

            {/* Single IP Input */}
            {scanMode === 'single' && (
              <input
                value={singleIP}
                onChange={e => setSingleIP(e.target.value)}
                placeholder="e.g. 192.168.100.10"
                className="w-full rounded px-3 py-2 font-mono text-sm"
                style={{ background: 'rgba(4,14,33,0.85)', border: '1px solid rgba(0,212,255,0.3)', color: '#c8d8ee', outline: 'none' }}
              />
            )}

            {/* IP Range Inputs */}
            {scanMode === 'range' && (
              <div className="grid grid-cols-2 gap-3">
                <input
                  value={rangeStart}
                  onChange={e => setRangeStart(e.target.value)}
                  placeholder="Start: 192.168.100.1"
                  className="rounded px-3 py-2 font-mono text-sm"
                  style={{ background: 'rgba(4,14,33,0.85)', border: '1px solid rgba(0,212,255,0.3)', color: '#c8d8ee', outline: 'none' }}
                />
                <input
                  value={rangeEnd}
                  onChange={e => setRangeEnd(e.target.value)}
                  placeholder="End: 192.168.100.50"
                  className="rounded px-3 py-2 font-mono text-sm"
                  style={{ background: 'rgba(4,14,33,0.85)', border: '1px solid rgba(0,212,255,0.3)', color: '#c8d8ee', outline: 'none' }}
                />
              </div>
            )}

            {/* Full Subnet Info */}
            {scanMode === 'subnet' && (
              <div className="p-3 rounded font-mono text-xs"
                style={{ background: 'rgba(0,212,255,0.05)', border: '1px solid rgba(0,212,255,0.12)' }}>
                <span style={{ color: '#667799' }}>Target subnet: </span>
                <span style={{ color: '#00d4ff' }}>{subnet || 'Not set'}</span>
                <span style={{ color: '#667799' }}> · {hostIPs.length} host IPs (.1 – .254)</span>
              </div>
            )}
          </div>

          {/* Credentials */}
          <div>
            <div className="font-mono text-[10px] mb-2 font-semibold uppercase tracking-wider" style={{ color: '#667799' }}>
              SNMP Credentials
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2">
              {/* Version */}
              <select
                value={version}
                onChange={e => setVersion(e.target.value as 'v2c' | 'v3')}
                className="rounded px-2 py-2 font-mono text-xs col-span-1"
                style={{ background: 'rgba(4,14,33,0.85)', border: '1px solid rgba(0,212,255,0.2)', color: '#c8d8ee' }}
              >
                <option value="v2c">SNMPv2c</option>
                <option value="v3">SNMPv3</option>
              </select>

              {version === 'v2c' ? (
                <input
                  value={community}
                  onChange={e => setCommunity(e.target.value)}
                  placeholder="Community string"
                  className="rounded px-2 py-2 font-mono text-xs"
                  style={{ background: 'rgba(4,14,33,0.85)', border: '1px solid rgba(0,212,255,0.2)', color: '#c8d8ee', outline: 'none' }}
                />
              ) : (
                <>
                  <input value={username} onChange={e => setUsername(e.target.value)} placeholder="Username"
                    className="rounded px-2 py-2 font-mono text-xs"
                    style={{ background: 'rgba(4,14,33,0.85)', border: '1px solid rgba(0,212,255,0.2)', color: '#c8d8ee', outline: 'none' }} />
                  <select value={securityLevel} onChange={e => setSecurityLevel(e.target.value)}
                    className="rounded px-2 py-2 font-mono text-xs"
                    style={{ background: 'rgba(4,14,33,0.85)', border: '1px solid rgba(0,212,255,0.2)', color: '#c8d8ee' }}>
                    <option>noAuthNoPriv</option>
                    <option>authNoPriv</option>
                    <option>authPriv</option>
                  </select>
                  {securityLevel !== 'noAuthNoPriv' && (
                    <>
                      <input value={authProtocol} onChange={e => setAuthProtocol(e.target.value)} placeholder="Auth protocol (SHA)"
                        className="rounded px-2 py-2 font-mono text-xs"
                        style={{ background: 'rgba(4,14,33,0.85)', border: '1px solid rgba(0,212,255,0.2)', color: '#c8d8ee', outline: 'none' }} />
                      <input value={authPassword} onChange={e => setAuthPassword(e.target.value)} placeholder="Auth password"
                        type="password"
                        className="rounded px-2 py-2 font-mono text-xs"
                        style={{ background: 'rgba(4,14,33,0.85)', border: '1px solid rgba(0,212,255,0.2)', color: '#c8d8ee', outline: 'none' }} />
                    </>
                  )}
                  {securityLevel === 'authPriv' && (
                    <>
                      <input value={privacyProtocol} onChange={e => setPrivacyProtocol(e.target.value)} placeholder="Privacy protocol (AES128)"
                        className="rounded px-2 py-2 font-mono text-xs"
                        style={{ background: 'rgba(4,14,33,0.85)', border: '1px solid rgba(0,212,255,0.2)', color: '#c8d8ee', outline: 'none' }} />
                      <input value={privacyPassword} onChange={e => setPrivacyPassword(e.target.value)} placeholder="Privacy password"
                        type="password"
                        className="rounded px-2 py-2 font-mono text-xs"
                        style={{ background: 'rgba(4,14,33,0.85)', border: '1px solid rgba(0,212,255,0.2)', color: '#c8d8ee', outline: 'none' }} />
                    </>
                  )}
                </>
              )}

              {/* Timeout */}
              <input value={timeoutSec} onChange={e => setTimeoutSec(e.target.value)} placeholder="Timeout (sec)"
                className="rounded px-2 py-2 font-mono text-xs"
                style={{ background: 'rgba(4,14,33,0.85)', border: '1px solid rgba(0,212,255,0.2)', color: '#c8d8ee', outline: 'none' }} />

              {/* Batch size */}
              <div className="flex items-center gap-2">
                <select
                  value={batchSize}
                  onChange={e => setBatchSize(e.target.value)}
                  className="flex-1 rounded px-2 py-2 font-mono text-xs"
                  style={{ background: 'rgba(4,14,33,0.85)', border: '1px solid rgba(0,212,255,0.2)', color: '#c8d8ee' }}
                >
                  {['5', '10', '20', '25', '50'].map(v => (
                    <option key={v} value={v}>Batch {v}</option>
                  ))}
                </select>
              </div>
            </div>
          </div>

          {/* Scan button */}
          <div className="flex flex-wrap items-center gap-3">
            <button
              onClick={() => void run()}
              disabled={running}
              className="px-5 py-2 rounded font-display text-xs tracking-wider font-bold transition-all disabled:opacity-40"
              style={{
                background: running ? 'rgba(255,170,0,0.12)' : 'rgba(0,212,255,0.15)',
                border: `1px solid ${running ? 'rgba(255,170,0,0.4)' : 'rgba(0,212,255,0.4)'}`,
                color: running ? '#ffaa00' : '#00d4ff',
              }}
            >
              {running
                ? `SCANNING ${scanned}/${total}…`
                : scanMode === 'single'
                ? 'SCAN 1 IP FOR SNMP'
                : scanMode === 'range'
                ? 'SCAN IP RANGE FOR SNMP'
                : `SCAN ${hostIPs.length} IPs FOR SNMP`}
            </button>

            {done && found.length > 0 && (
              <button
                onClick={() => void storeAll()}
                disabled={storing || storedIps.size === found.length}
                className="px-4 py-2 rounded font-display text-xs tracking-wider font-bold transition-all disabled:opacity-40"
                style={{
                  background: 'rgba(0,255,136,0.12)',
                  border: '1px solid rgba(0,255,136,0.35)',
                  color: '#00ff88',
                }}
              >
                {storing ? 'STORING…' : `STORE ALL (${found.length - storedIps.size} new)`}
              </button>
            )}

            {storeMsg && (
              <span className="font-mono text-xs" style={{ color: '#00ff88' }}>{storeMsg}</span>
            )}
            {error && (
              <span className="font-mono text-xs" style={{ color: '#ff3366' }}>{error}</span>
            )}
          </div>

          {/* Progress bar */}
          {(running || (done && total > 0)) && (
            <div>
              <div className="flex justify-between mb-1.5">
                <span className="font-mono text-[10px]" style={{ color: '#8899bb' }}>
                  {running ? `Scanning batch by batch…` : `Scan complete`}
                </span>
                <span className="font-mono text-[10px] font-bold" style={{ color: running ? '#ffaa00' : '#00ff88' }}>
                  {progress}% · {scanned}/{total} IPs
                </span>
              </div>
              <div className="h-1.5 rounded-full overflow-hidden" style={{ background: 'rgba(0,0,0,0.3)' }}>
                <div
                  className="h-full rounded-full transition-all"
                  style={{
                    width: `${progress}%`,
                    background: running
                      ? 'linear-gradient(90deg, #ffaa0080, #ffaa00)'
                      : 'linear-gradient(90deg, #00ff8880, #00ff88)',
                  }}
                />
              </div>
            </div>
          )}

          {/* Results */}
          {found.length > 0 && (
            <div>
              <div className="font-display font-bold text-sm tracking-wider neon-cyan mb-3">
                SNMP DEVICES FOUND ({found.length})
              </div>
              <div className="space-y-2 max-h-[400px] overflow-y-auto pr-1">
                {found.map(device => {
                  const isStored = storedIps.has(device.ip)
                  return (
                    <div
                      key={device.ip}
                      className="p-3 rounded"
                      style={{
                        background: 'rgba(0,0,0,0.25)',
                        border: `1px solid ${isStored ? 'rgba(0,255,136,0.2)' : 'rgba(0,212,255,0.15)'}`,
                      }}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-1 flex-wrap">
                            {/* Green SNMP indicator */}
                            <div
                              className="w-2 h-2 rounded-full"
                              style={{ background: '#00ff88', boxShadow: '0 0 6px #00ff88' }}
                            />
                            <span className="font-mono text-xs font-bold" style={{ color: '#00d4ff' }}>{device.ip}</span>
                            <span className="font-mono text-xs" style={{ color: '#c8d8ee' }}>{device.hostname}</span>
                            <span
                              className="font-mono text-[9px] px-1.5 py-0.5 rounded"
                              style={{ background: 'rgba(0,212,255,0.12)', color: '#00d4ff', border: '1px solid rgba(0,212,255,0.25)' }}
                            >
                              {device.version.toUpperCase()}
                            </span>
                            {isStored && (
                              <span className="font-mono text-[9px] px-1.5 py-0.5 rounded"
                                style={{ background: 'rgba(0,255,136,0.12)', color: '#00ff88', border: '1px solid rgba(0,255,136,0.25)' }}>
                                STORED
                              </span>
                            )}
                          </div>
                          <div className="grid grid-cols-1 sm:grid-cols-3 gap-x-4 gap-y-0.5">
                            <div className="font-mono text-[10px] truncate" style={{ color: '#8899bb' }}>
                              <span style={{ color: '#556677' }}>Vendor: </span>{device.vendor}
                            </div>
                            <div className="font-mono text-[10px] truncate" style={{ color: '#8899bb' }}>
                              <span style={{ color: '#556677' }}>Uptime: </span>{device.uptime}
                            </div>
                            <div className="font-mono text-[10px] truncate sm:col-span-3 mt-0.5" style={{ color: '#667799' }}>
                              {device.description.length > 120
                                ? `${device.description.slice(0, 120)}…`
                                : device.description}
                            </div>
                          </div>
                        </div>
                        {/* Store single */}
                        {!isStored && (
                          <button
                            onClick={() => void storeSingle(device)}
                            className="shrink-0 px-3 py-1.5 rounded font-mono text-[10px] font-bold transition-all"
                            style={{
                              background: 'rgba(0,212,255,0.1)',
                              border: '1px solid rgba(0,212,255,0.3)',
                              color: '#00d4ff',
                            }}
                          >
                            + ADD
                          </button>
                        )}
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {/* Empty after scan */}
          {done && found.length === 0 && (
            <div className="py-6 text-center">
              <div className="font-mono text-sm mb-1" style={{ color: '#8899bb' }}>No SNMP response received</div>
              <div className="font-mono text-xs" style={{ color: '#556677' }}>
                None of the {total} IPs in {subnet} responded to SNMP.
                Check community string, credentials, and that SNMP is enabled on target devices.
              </div>
            </div>
          )}
        </div>
      )}
    </GlassCard>
  )
}
