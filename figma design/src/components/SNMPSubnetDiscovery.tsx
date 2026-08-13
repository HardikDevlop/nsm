/**
 * SNMPSubnetDiscovery — rich SNMP sweep with structured device cards.
 * Scan modes: single IP / IP range / full subnet.
 */
import { useCallback, useState } from 'react'
import GlassCard from './GlassCard'
import { addDiscoveredDevices, discoverSNMP } from '../lib/api'
import { toast } from '../lib/swal'

/* ── helpers ──────────────────────────────────────────────────────────────── */
function fmtUp(raw: unknown): string {
  const s = Number(raw)
  if (!s || isNaN(s)) return '—'
  const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60)
  return d > 0 ? `${d}d ${h}h ${m}m` : h > 0 ? `${h}h ${m}m` : `${m}m`
}

function clean(v: unknown, fb = '—'): string {
  const s = String(v ?? '').trim()
  return s && !['not supported', 'none', 'null', 'undefined', '—', ''].includes(s.toLowerCase()) ? s : fb
}

function subnetIPs(cidr: string): string[] {
  try {
    const [b] = cidr.split('/')
    const p = b.split('.').map(Number)
    if (p.length !== 4 || p.some(isNaN)) return []
    return Array.from({ length: 254 }, (_, i) => `${p[0]}.${p[1]}.${p[2]}.${i + 1}`)
  } catch { return [] }
}

function chk<T>(arr: T[], n: number): T[][] {
  const r: T[][] = []
  for (let i = 0; i < arr.length; i += n) r.push(arr.slice(i, i + n))
  return r
}

/* ── types ────────────────────────────────────────────────────────────────── */
interface SD {
  ip: string; hostname: string; descr: string; vendor: string
  model: string; serial: string; firmware: string; uptime: string
  version: string; raw: Record<string, unknown>
}

/* ── style constants ──────────────────────────────────────────────────────── */
const SEL = { background: 'rgba(4,14,33,0.85)', border: '1px solid rgba(0,212,255,0.2)', color: '#c8d8ee' } as const
const INP = { ...SEL, outline: 'none' } as const

/* ── DevCard ──────────────────────────────────────────────────────────────── */
function DevCard({ d, stored, onStore }: { d: SD; stored: boolean; onStore: () => void }) {
  const fields = [
    { l: 'Vendor',   v: d.vendor   },
    { l: 'Model',    v: d.model    },
    { l: 'Uptime',   v: d.uptime   },
    { l: 'Serial',   v: d.serial   },
    { l: 'Firmware', v: d.firmware },
  ].filter(f => f.v !== '—')

  return (
    <div
      className="rounded-xl overflow-hidden transition-all"
      style={{
        border:      stored ? '1px solid rgba(0,255,136,0.25)' : '1px solid rgba(0,212,255,0.18)',
        background:  stored ? 'rgba(0,255,136,0.02)' : 'rgba(0,212,255,0.02)',
      }}
    >
      {/* ── top bar ── */}
      <div
        className="flex items-center justify-between px-4 py-2.5 flex-wrap gap-2"
        style={{ borderBottom: '1px solid rgba(0,212,255,0.08)', background: 'rgba(0,0,0,0.18)' }}
      >
        <div className="flex items-center gap-2 flex-wrap min-w-0">
          <span
            className="w-2 h-2 rounded-full shrink-0"
            style={{ background: '#00ff88', boxShadow: '0 0 7px #00ff88' }}
          />
          <span className="font-mono text-sm font-bold" style={{ color: '#00d4ff' }}>{d.ip}</span>
          {d.hostname !== d.ip && (
            <span className="font-mono text-xs truncate max-w-[180px]" style={{ color: '#c8d8ee' }}>
              {d.hostname}
            </span>
          )}
          <span
            className="font-mono text-[10px] px-1.5 py-0.5 rounded"
            style={{ background: 'rgba(0,212,255,0.1)', color: '#00d4ff', border: '1px solid rgba(0,212,255,0.25)' }}
          >
            {d.version.toUpperCase()}
          </span>
          {stored && (
            <span
              className="font-mono text-[10px] px-1.5 py-0.5 rounded"
              style={{ background: 'rgba(0,255,136,0.12)', color: '#00ff88', border: '1px solid rgba(0,255,136,0.3)' }}
            >
              ✓ STORED
            </span>
          )}
        </div>

        {!stored && (
          <button
            onClick={onStore}
            className="font-mono text-xs px-3 py-1 rounded shrink-0 transition-all hover:opacity-80"
            style={{ background: 'rgba(0,212,255,0.12)', border: '1px solid rgba(0,212,255,0.35)', color: '#00d4ff' }}
          >
            + ADD
          </button>
        )}
      </div>

      {/* ── fields grid ── */}
      {fields.length > 0 && (
        <div className="px-4 pt-3 pb-2 grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-x-6 gap-y-2">
          {fields.map(f => (
            <div key={f.l}>
              <div className="font-mono text-[10px]" style={{ color: '#556677' }}>{f.l}</div>
              <div className="font-mono text-xs truncate" style={{ color: '#c8d8ee' }}>{f.v}</div>
            </div>
          ))}
        </div>
      )}

      {/* ── sysDescr ── */}
      {d.descr !== '—' && (
        <div className="px-4 pb-3 pt-1">
          <div className="font-mono text-[10px] mb-0.5" style={{ color: '#556677' }}>Description</div>
          <div className="font-mono text-[11px] leading-relaxed" style={{ color: '#8899bb' }}>
            {d.descr.length > 160 ? d.descr.slice(0, 160) + '…' : d.descr}
          </div>
        </div>
      )}
    </div>
  )
}

/* ── main component ───────────────────────────────────────────────────────── */
export default function SNMPSubnetDiscovery({
  subnet,
  onDevicesStored,
}: {
  subnet: string
  onDevicesStored?: () => void
}) {
  const [expanded,  setExpanded]  = useState(true)
  const [mode,      setMode]      = useState<'single' | 'range' | 'subnet'>('single')
  const [singleIP,  setSingleIP]  = useState('')
  const [rangeS,    setRangeS]    = useState('')
  const [rangeE,    setRangeE]    = useState('')
  const [ver,       setVer]       = useState<'v2c' | 'v3'>('v2c')
  const [com,       setCom]       = useState('public')
  const [usr,       setUsr]       = useState('')
  const [ap,        setAp]        = useState('SHA')
  const [apw,       setApw]       = useState('')
  const [pp,        setPp]        = useState('AES128')
  const [ppw,       setPpw]       = useState('')
  const [sl,        setSl]        = useState('authNoPriv')
  const [timeout,   setTimeout_]  = useState('2')
  const [batchSize, setBatchSize] = useState('10')
  const [running,   setRunning]   = useState(false)
  const [scanned,   setScanned]   = useState(0)
  const [total,     setTotal]     = useState(0)
  const [found,     setFound]     = useState<SD[]>([])
  const [done,      setDone]      = useState(false)
  const [storing,   setStoring]   = useState(false)
  const [storedIps, setStoredIps] = useState<Set<string>>(new Set())
  const hostIPs = subnetIPs(subnet)

  /* build target IP list */
  const getIPs = useCallback((): string[] => {
    if (mode === 'single') { const ip = singleIP.trim(); return ip ? [ip] : [] }
    if (mode === 'range') {
      const sp = rangeS.split('.').map(Number)
      const ep = rangeE.split('.').map(Number)
      if (sp.length !== 4 || ep.length !== 4 || sp[3] > ep[3]) return []
      return Array.from({ length: ep[3] - sp[3] + 1 }, (_, i) => `${sp.slice(0, 3).join('.')}.${sp[3] + i}`)
    }
    return hostIPs
  }, [mode, singleIP, rangeS, rangeE, hostIPs])

  /* parse one SNMP result into SD */
  const mkDevice = (ip: string, d: Record<string, unknown>): SD => ({
    ip,
    raw:      d,
    hostname: clean(d.hostname ?? d.sysName, ip),
    descr:    clean(d.sysDescr ?? d.description),
    vendor:   clean(d.vendor ?? d.snmp_vendor),
    model:    clean(d.model),
    serial:   clean(d.serial_number ?? d.serial),
    firmware: clean(d.firmware_version ?? d.firmware),
    uptime:   fmtUp(d.uptime_seconds),
    version:  clean(d.snmp_version, ver),
  })

  /* run scan */
  const doScan = useCallback(async () => {
    const ips = getIPs()
    if (!ips.length) { toast.warning('No IPs to scan'); return }
    setRunning(true); setDone(false); setFound([]); setStoredIps(new Set())
    setScanned(0); setTotal(ips.length)
    const batch = Math.max(1, Math.min(50, parseInt(batchSize, 10) || 10))
    let disc: SD[] = []
    for (const chunk of chk(ips, batch)) {
      try {
        const res = await discoverSNMP({
          ips: chunk, snmp_version: ver, timeout_seconds: parseFloat(timeout) || 2,
          communities:      ver === 'v2c' ? [com] : undefined,
          username:         ver === 'v3' ? usr || undefined : null,
          auth_protocol:    ver === 'v3' && sl !== 'noAuthNoPriv' ? ap  : null,
          auth_password:    ver === 'v3' && sl !== 'noAuthNoPriv' ? apw : null,
          privacy_protocol: ver === 'v3' && sl === 'authPriv'     ? pp  : null,
          privacy_password: ver === 'v3' && sl === 'authPriv'     ? ppw : null,
          security_level:   ver === 'v3' ? sl : null,
        })
        for (const [ip, data] of Object.entries(res.results)) {
          disc = [...disc, mkDevice(ip, data as Record<string, unknown>)]
          setFound([...disc])
        }
      } catch { /* chunk timed out — continue */ }
      setScanned(p => Math.min(p + chunk.length, ips.length))
    }
    setRunning(false); setDone(true)
    if (disc.length) toast.success(`${disc.length} device${disc.length !== 1 ? 's' : ''} responded to SNMP`)
    else             toast.info('No SNMP responses — check credentials and that SNMP is enabled')
  }, [getIPs, ver, com, usr, ap, apw, pp, ppw, sl, timeout, batchSize])

  /* store all */
  const storeAll = async () => {
    if (!found.length) return
    setStoring(true)
    try {
      const devs  = found.map(d => ({ ip_address: d.ip, hostname: d.hostname, ...d.raw }))
      const saved = await addDiscoveredDevices({ devices: devs, site_id: null })
      setStoredIps(new Set(found.map(d => d.ip)))
      toast.success(`${saved.added_count} stored, ${saved.skipped_count} skipped`)
      onDevicesStored?.()
    } catch (e) { toast.error(e instanceof Error ? e.message : 'Store failed') }
    setStoring(false)
  }

  /* store single */
  const storeSingle = async (d: SD) => {
    if (storedIps.has(d.ip)) return
    try {
      const saved = await addDiscoveredDevices({
        devices: [{ ip_address: d.ip, hostname: d.hostname, ...d.raw }],
        site_id: null,
      })
      setStoredIps(p => new Set([...p, d.ip]))
      if (saved.added_count > 0) toast.success(`${d.ip} saved to database`)
      else                        toast.info(`${d.ip} already exists in database`)
      onDevicesStored?.()
    } catch (e) { toast.error(e instanceof Error ? e.message : 'Store failed') }
  }

  const pct     = total > 0 ? Math.round((scanned / total) * 100) : 0
  const newCount = found.length - storedIps.size

  return (
    <GlassCard className="overflow-hidden">
      {/* ── collapsible header ── */}
      <button
        className="w-full flex items-center justify-between p-4 hover:bg-cyan-400/5 transition-all"
        onClick={() => setExpanded(e => !e)}
      >
        <div className="flex items-center gap-3">
          <div
            className="w-9 h-9 rounded-lg flex items-center justify-center shrink-0"
            style={{ background: 'rgba(0,212,255,0.1)', border: '1px solid rgba(0,212,255,0.25)' }}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#00d4ff" strokeWidth="1.8">
              <path d="M8.111 16.404a5.5 5.5 0 017.778 0M12 20h.01m-7.08-7.071c3.904-3.905 10.236-3.905 14.141 0M1.394 9.393c5.857-5.857 15.355-5.857 21.213 0" />
            </svg>
          </div>
          <div className="text-left">
            <div className="font-display font-bold text-sm tracking-wider neon-cyan">SNMP SUBNET DISCOVERY</div>
            <div className="font-mono text-xs mt-0.5" style={{ color: '#8899bb' }}>
              Scan {hostIPs.length} IPs in {subnet || '—'}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {running && (
            <span className="font-mono text-[10px] px-2 py-1 rounded animate-pulse"
              style={{ background: 'rgba(255,170,0,0.15)', color: '#ffaa00', border: '1px solid rgba(255,170,0,0.3)' }}>
              SCANNING {scanned}/{total}
            </span>
          )}
          {done && !running && (
            <span className="font-mono text-[10px] px-2 py-1 rounded"
              style={{
                background: found.length > 0 ? 'rgba(0,255,136,0.15)' : 'rgba(136,153,187,0.12)',
                color:      found.length > 0 ? '#00ff88' : '#8899bb',
                border:     `1px solid ${found.length > 0 ? 'rgba(0,255,136,0.3)' : 'rgba(136,153,187,0.2)'}`,
              }}>
              {found.length} FOUND
            </span>
          )}
          <svg
            width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#8899bb" strokeWidth="2"
            style={{ transform: expanded ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s' }}
          >
            <path d="M19 9l-7 7-7-7" />
          </svg>
        </div>
      </button>

      {/* ── body ── */}
      {expanded && (
        <div className="border-t px-4 pb-5 space-y-4" style={{ borderColor: 'rgba(0,212,255,0.1)' }}>

          {/* scan mode tabs */}
          <div className="mt-4">
            <div className="font-mono text-[10px] mb-2 font-semibold uppercase tracking-wider" style={{ color: '#667799' }}>
              SCAN TARGET
            </div>
            <div className="flex gap-2 mb-3">
              {(['single', 'range', 'subnet'] as const).map(m => (
                <button key={m} onClick={() => setMode(m)}
                  className="flex-1 px-3 py-2 rounded-lg font-mono text-xs font-bold transition-all"
                  style={{
                    background: mode === m ? 'rgba(0,212,255,0.2)' : 'rgba(0,0,0,0.25)',
                    border:     `1px solid ${mode === m ? 'rgba(0,212,255,0.5)' : 'rgba(0,212,255,0.15)'}`,
                    color:      mode === m ? '#00d4ff' : '#8899bb',
                  }}>
                  {m === 'single' ? 'SINGLE IP' : m === 'range' ? 'IP RANGE' : 'FULL SUBNET'}
                </button>
              ))}
            </div>

            {mode === 'single' && (
              <input value={singleIP} onChange={e => setSingleIP(e.target.value)}
                placeholder="e.g. 192.168.1.10"
                className="w-full rounded-lg px-3 py-2 font-mono text-sm" style={INP} />
            )}
            {mode === 'range' && (
              <div className="grid grid-cols-2 gap-3">
                <input value={rangeS} onChange={e => setRangeS(e.target.value)} placeholder="Start: 192.168.1.1"  className="rounded-lg px-3 py-2 font-mono text-sm" style={INP} />
                <input value={rangeE} onChange={e => setRangeE(e.target.value)} placeholder="End:   192.168.1.50" className="rounded-lg px-3 py-2 font-mono text-sm" style={INP} />
              </div>
            )}
            {mode === 'subnet' && (
              <div className="p-3 rounded-lg font-mono text-xs"
                style={{ background: 'rgba(0,212,255,0.05)', border: '1px solid rgba(0,212,255,0.12)' }}>
                <span style={{ color: '#667799' }}>Target: </span>
                <span style={{ color: '#00d4ff' }}>{subnet || 'not set'}</span>
                <span style={{ color: '#667799' }}> · {hostIPs.length} host IPs (.1–.254)</span>
              </div>
            )}
          </div>

          {/* credentials */}
          <div>
            <div className="font-mono text-[10px] mb-2 font-semibold uppercase tracking-wider" style={{ color: '#667799' }}>
              SNMP CREDENTIALS
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2">
              <select value={ver} onChange={e => setVer(e.target.value as 'v2c' | 'v3')}
                className="rounded-lg px-2 py-2 font-mono text-xs" style={SEL}>
                <option value="v2c">SNMPv2c</option>
                <option value="v3">SNMPv3</option>
              </select>

              {ver === 'v2c' ? (
                <input value={com} onChange={e => setCom(e.target.value)} placeholder="Community string"
                  className="rounded-lg px-2 py-2 font-mono text-xs" style={INP} />
              ) : (
                <>
                  <input value={usr} onChange={e => setUsr(e.target.value)} placeholder="Username"
                    className="rounded-lg px-2 py-2 font-mono text-xs" style={INP} />
                  <select value={sl} onChange={e => setSl(e.target.value)}
                    className="rounded-lg px-2 py-2 font-mono text-xs" style={SEL}>
                    <option>noAuthNoPriv</option>
                    <option>authNoPriv</option>
                    <option>authPriv</option>
                  </select>
                  {sl !== 'noAuthNoPriv' && (
                    <>
                      <input value={ap}  onChange={e => setAp(e.target.value)}  placeholder="Auth Protocol (SHA)"  className="rounded-lg px-2 py-2 font-mono text-xs" style={INP} />
                      <input type="password" value={apw} onChange={e => setApw(e.target.value)} placeholder="Auth Password" className="rounded-lg px-2 py-2 font-mono text-xs" style={INP} />
                    </>
                  )}
                  {sl === 'authPriv' && (
                    <>
                      <input value={pp}  onChange={e => setPp(e.target.value)}  placeholder="Privacy Protocol (AES128)" className="rounded-lg px-2 py-2 font-mono text-xs" style={INP} />
                      <input type="password" value={ppw} onChange={e => setPpw(e.target.value)} placeholder="Privacy Password" className="rounded-lg px-2 py-2 font-mono text-xs" style={INP} />
                    </>
                  )}
                </>
              )}

              <input value={timeout} onChange={e => setTimeout_(e.target.value)} placeholder="Timeout (sec)"
                className="rounded-lg px-2 py-2 font-mono text-xs" style={INP} />
              <select value={batchSize} onChange={e => setBatchSize(e.target.value)}
                className="rounded-lg px-2 py-2 font-mono text-xs" style={SEL}>
                {['5', '10', '20', '25', '50'].map(v => <option key={v} value={v}>Batch {v}</option>)}
              </select>
            </div>
          </div>

          {/* action buttons */}
          <div className="flex flex-wrap items-center gap-3">
            <button onClick={() => void doScan()} disabled={running}
              className="px-5 py-2 rounded-lg font-display text-xs font-bold tracking-wider transition-all disabled:opacity-40 flex items-center gap-2"
              style={{
                background: running ? 'rgba(255,170,0,0.12)' : 'rgba(0,212,255,0.15)',
                border:     `1px solid ${running ? 'rgba(255,170,0,0.4)' : 'rgba(0,212,255,0.4)'}`,
                color:      running ? '#ffaa00' : '#00d4ff',
              }}>
              {running
                ? <><span className="w-3 h-3 rounded-full border border-current border-t-transparent animate-spin inline-block" />
                    SCANNING {scanned}/{total}…
                  </>
                : mode === 'single' ? '▶ SCAN 1 IP'
                : mode === 'range'  ? '▶ SCAN IP RANGE'
                :                    `▶ SCAN ${hostIPs.length} IPs`
              }
            </button>

            {done && found.length > 0 && (
              <button onClick={() => void storeAll()} disabled={storing || newCount === 0}
                className="px-4 py-2 rounded-lg font-display text-xs font-bold tracking-wider transition-all disabled:opacity-40"
                style={{ background: 'rgba(0,255,136,0.12)', border: '1px solid rgba(0,255,136,0.35)', color: '#00ff88' }}>
                {storing ? 'STORING…' : `STORE ALL (${newCount} new)`}
              </button>
            )}
          </div>

          {/* progress bar */}
          {(running || (done && total > 0)) && (
            <div>
              <div className="flex justify-between mb-1.5 font-mono text-[10px]">
                <span style={{ color: '#8899bb' }}>{running ? 'Scanning in batches…' : 'Scan complete'}</span>
                <span style={{ color: running ? '#ffaa00' : '#00ff88' }}>
                  {pct}% · {scanned}/{total} IPs · {found.length} found
                </span>
              </div>
              <div className="h-1.5 rounded-full overflow-hidden" style={{ background: 'rgba(0,0,0,0.3)' }}>
                <div className="h-full rounded-full transition-all duration-300"
                  style={{
                    width:      `${pct}%`,
                    background: running
                      ? 'linear-gradient(90deg, rgba(255,170,0,0.6), #ffaa00)'
                      : 'linear-gradient(90deg, rgba(0,255,136,0.6), #00ff88)',
                  }} />
              </div>
            </div>
          )}

          {/* results */}
          {found.length > 0 && (
            <div>
              <div className="flex items-center justify-between mb-3">
                <div className="font-display font-bold text-sm tracking-wider neon-cyan">
                  SNMP DEVICES FOUND ({found.length})
                  {storedIps.size > 0 && (
                    <span className="font-mono text-xs ml-2 font-normal" style={{ color: '#00ff88' }}>
                      · {storedIps.size} stored
                    </span>
                  )}
                </div>
              </div>
              <div className="space-y-3 max-h-[60vh] overflow-y-auto pr-1">
                {found.map(d => (
                  <DevCard
                    key={d.ip}
                    d={d}
                    stored={storedIps.has(d.ip)}
                    onStore={() => void storeSingle(d)}
                  />
                ))}
              </div>
            </div>
          )}

          {/* empty after scan */}
          {done && found.length === 0 && (
            <div className="py-8 text-center rounded-lg"
              style={{ background: 'rgba(255,170,0,0.04)', border: '1px solid rgba(255,170,0,0.15)' }}>
              <div className="font-mono text-sm mb-1" style={{ color: '#8899bb' }}>No SNMP responses</div>
              <div className="font-mono text-xs" style={{ color: '#556677' }}>
                None of the {total} IPs responded. Check credentials and that SNMP is enabled on target devices.
              </div>
            </div>
          )}
        </div>
      )}
    </GlassCard>
  )
}
