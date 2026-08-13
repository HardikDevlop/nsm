import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router'
import GlassCard from '../components/GlassCard'
import SNMPDiscoveryPanel from '../components/SNMPDiscoveryPanel'
import {
  listAlerts, listSNMPDevices, listInterfaces, listDeviceMetrics,
  getMonitoringStatus, stopAllMonitoring, startAllMonitoring,
  type AlertRecord, type DeviceMetricRecord, type DeviceRecord,
  type InterfaceRecord, deleteDevice, updateDevice,
} from '../lib/api'
import { useAuth } from '../components/AuthContext'
import { confirmDanger, promptText, toast } from '../lib/swal'

/* ── severity colours ─────────────────────────────────────────────────────── */
const SEV: Record<string, { c: string; bg: string }> = {
  critical: { c: '#ff3366', bg: 'rgba(255,51,102,0.12)' },
  high:     { c: '#ff6644', bg: 'rgba(255,102,68,0.12)' },
  warning:  { c: '#ffaa00', bg: 'rgba(255,170,0,0.12)' },
  medium:   { c: '#ffaa00', bg: 'rgba(255,170,0,0.12)' },
  info:     { c: '#00d4ff', bg: 'rgba(0,212,255,0.12)' },
}

/* ── helpers ──────────────────────────────────────────────────────────────── */
function fmtBytes(b: number | undefined): string {
  if (!b) return '—'
  if (b >= 1_073_741_824) return `${(b / 1_073_741_824).toFixed(2)} GB`
  if (b >= 1_048_576)     return `${(b / 1_048_576).toFixed(1)} MB`
  if (b >= 1024)          return `${(b / 1024).toFixed(1)} KB`
  return `${b} B`
}
function fmtUptime(s: number): string {
  if (s <= 0) return '—'
  const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60)
  return d > 0 ? `${d}d ${h}h` : h > 0 ? `${h}h ${m}m` : `${m}m`
}
function classifyType(hostname: string): string {
  const h = hostname.toLowerCase()
  if (h.includes('switch') || h.includes('sw-')) return 'switch'
  if (h.includes('firewall') || h.includes('fw')) return 'firewall'
  if (h.includes('router') || h.includes('gw'))   return 'router'
  if (h.includes('srv') || h.includes('server'))  return 'server'
  return 'default'
}

/* ── device-type icons ────────────────────────────────────────────────────── */
const TYPE_ICON: Record<string, string> = {
  switch:   'M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4',
  firewall: 'M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z',
  router:   'M13 10V3L4 14h7v7l9-11h-7z',
  server:   'M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2',
  default:  'M8.111 16.404a5.5 5.5 0 017.778 0M12 20h.01m-7.08-7.071c3.904-3.905 10.236-3.905 14.141 0',
}

/* ── SNMP sub-page navigation cards ─────────────────────────────────────── */
interface NavCard { label: string; path: (id: number) => string; icon: string; desc: string; color: string }
const SNMP_NAV: NavCard[] = [
  { label: 'Dashboard',    path: id=>`/snmp/devices/${id}`,              color: '#00d4ff', desc: 'Overview & modules',       icon: 'M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6' },
  { label: 'CPU',          path: id=>`/snmp/devices/${id}/cpu`,          color: '#00ff88', desc: 'Utilisation & cores',       icon: 'M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z' },
  { label: 'Memory',       path: id=>`/snmp/devices/${id}/memory`,       color: '#7c3aed', desc: 'RAM, swap & buffers',       icon: 'M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4' },
  { label: 'Interfaces',   path: id=>`/snmp/devices/${id}/interfaces`,   color: '#00bfff', desc: 'IF-MIB traffic & errors',   icon: 'M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4' },
  { label: 'Storage',      path: id=>`/snmp/devices/${id}/storage`,      color: '#ffaa00', desc: 'hrStorageTable volumes',    icon: 'M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4' },
  { label: 'Environment',  path: id=>`/snmp/devices/${id}/environment`,  color: '#ff6644', desc: 'Temp, fans, PSU, sensors',  icon: 'M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z' },
  { label: 'Topology',     path: id=>`/snmp/devices/${id}/topology`,     color: '#a78bfa', desc: 'LLDP / CDP / ARP graph',    icon: 'M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9' },
  { label: 'OID Explorer', path: id=>`/snmp/devices/${id}/oids`,         color: '#34d399', desc: 'Browse all polled OIDs',    icon: 'M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z' },
  { label: 'Polling',      path: id=>`/snmp/devices/${id}/polling`,      color: '#f472b6', desc: 'History & statistics',      icon: 'M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z' },
]

/* ── service start/stop button ───────────────────────────────────────────── */
function SvcBtn({ label, active, busy, onToggle }: { label: string; active: boolean; busy: boolean; onToggle: () => void }) {
  return (
    <button onClick={onToggle} disabled={busy}
      className="flex items-center gap-2 px-3 py-2 rounded font-mono text-xs transition-all select-none"
      style={{
        border:  `1px solid ${active ? 'rgba(0,255,136,0.4)' : 'rgba(255,51,102,0.35)'}`,
        background: active ? 'rgba(0,255,136,0.08)' : 'rgba(255,51,102,0.08)',
        color:   active ? '#00ff88' : '#ff3366',
        opacity: busy ? 0.5 : 1,
        cursor:  busy ? 'not-allowed' : 'pointer',
        minWidth: 160,
      }}>
      <span className="w-2 h-2 rounded-full shrink-0"
        style={{ background: active ? '#00ff88' : '#ff3366', boxShadow: active ? '0 0 6px #00ff88' : '0 0 6px #ff3366' }} />
      {busy ? 'Working…' : active ? `■ STOP ${label}` : `▶ START ${label}`}
    </button>
  )
}

/* ── main page ───────────────────────────────────────────────────────────── */
export default function SNMPMonitoring() {
  const navigate = useNavigate()
  const { isSuperAdmin } = useAuth()

  const [tab,         setTab]        = useState<'devices'|'oids'|'traps'>('devices')
  const [devices,     setDevices]    = useState<DeviceRecord[]>([])
  const [alerts,      setAlerts]     = useState<AlertRecord[]>([])
  const [interfaces,  setIfaces]     = useState<InterfaceRecord[]>([])
  const [metrics,     setMetrics]    = useState<DeviceMetricRecord[]>([])
  const [liveList,    setLive]       = useState<Record<string,unknown>[]>([])
  const [error,       setError]      = useState<string|null>(null)
  const [lastUpdate,  setLastUpdate] = useState<string>('')
  const [selectedId,  setSelected]   = useState<number|null>(null)

  /* service controls */
  const [pingOn,    setPingOn]    = useState(true)
  const [pollOn,    setPollOn]    = useState(true)
  const [autoOn,    setAutoOn]    = useState(true)
  const [pingBusy,  setPingBusy]  = useState(false)
  const abortRef = useRef<AbortController|null>(null)

  /* ── fetch all data ───────────────────────────────────────────────────── */
  const loadData = useCallback(async () => {
    abortRef.current?.abort()
    abortRef.current = new AbortController()
    try {
      const [devs, alts, ifs, mets, mon] = await Promise.all([
        listSNMPDevices(), listAlerts(), listInterfaces(),
        listDeviceMetrics(), getMonitoringStatus(),
      ])
      setDevices(devs); setAlerts(alts); setIfaces(ifs)
      setMetrics(mets); setLive(mon.devices)
      if (devs.length > 0 && !selectedId) setSelected(devs[0].id)
      setLastUpdate(new Date().toLocaleTimeString())
      setError(null)
    } catch (e) {
      if ((e as Error).name !== 'AbortError')
        setError(e instanceof Error ? e.message : 'Load failed')
    }
  }, [selectedId])

  useEffect(() => { void loadData() }, [])        // eslint-disable-line
  useEffect(() => {
    if (!autoOn) return
    const id = setInterval(() => { void loadData() }, 15_000)
    return () => clearInterval(id)
  }, [autoOn, loadData])
  useEffect(() => () => { abortRef.current?.abort() }, [])

  /* ── service toggle handlers ──────────────────────────────────────────── */
  const togglePing = async () => {
    setPingBusy(true)
    try {
      if (pingOn) { await stopAllMonitoring(); setPingOn(false) }
      else { await startAllMonitoring(devices.map(d=>({ ip:d.ip_address, hostname:d.hostname, device_id:d.id } as Record<string,unknown>))); setPingOn(true) }
    } catch { /* silent */ } finally { setPingBusy(false) }
  }

  const removeDevice = async (id: number) => {
    if (!isSuperAdmin) return
    const dev = devices.find(d => d.id === id)
    const ok = await confirmDanger({
      title: `Delete ${dev?.hostname || dev?.ip_address || 'device'}?`,
      text: 'This action cannot be undone.',
      confirmText: 'Delete',
    })
    if (!ok) return
    try {
      await deleteDevice(id)
      toast.success('Device deleted')
      void loadData()
    } catch (e) {
      const message = (e as Error).message
      setError(message)
      toast.error(message)
    }
  }
  const editDevice = async (dev: DeviceRecord) => {
    if (!isSuperAdmin) return
    const h = await promptText({
      title: 'Edit hostname',
      inputLabel: 'Hostname',
      inputValue: dev.hostname,
      confirmText: 'Update',
    })
    if (!h) return
    try {
      await updateDevice(dev.id, { hostname: h })
      toast.success('Device updated')
      void loadData()
    } catch (e) {
      const message = (e as Error).message
      setError(message)
      toast.error(message)
    }
  }

  /* ── derived maps ─────────────────────────────────────────────────────── */
  const deviceById = useMemo(() => new Map(devices.map(d=>[d.id,d])), [devices])

  const ifByDev = useMemo(() => {
    const m = new Map<number,InterfaceRecord[]>()
    for (const i of interfaces) m.set(i.device_id, [...(m.get(i.device_id)??[]), i])
    return m
  }, [interfaces])

  const latestMet = useMemo(() => {
    const m = new Map<number,DeviceMetricRecord>()
    for (const r of [...metrics].sort((a,b)=>new Date(b.created_at).getTime()-new Date(a.created_at).getTime()))
      if (!m.has(r.device_id)) m.set(r.device_id, r)
    return m
  }, [metrics])

  const liveById = useMemo(() => {
    const m = new Map<number,Record<string,unknown>>()
    for (const d of liveList) { const id=d.device_id as number; if(id) m.set(id,d) }
    return m
  }, [liveList])

  const inventory = useMemo(() => devices.map(dev => {
    const ifaces = ifByDev.get(dev.id)??[]
    const met    = latestMet.get(dev.id)
    const live   = liveById.get(dev.id)
    const ls     = live ? String(live.status??'') : null
    const status = ls==='up'?'online': ls==='down'?'offline': dev.status==='online'?'online': dev.status==='offline'?'offline':'warning'
    return {
      id: dev.id,
      hostname: dev.hostname||`device-${dev.ip_address}`,
      type: classifyType(dev.hostname),
      ip: dev.ip_address, mac: dev.mac_address??'—',
      model: dev.model??dev.serial_number??'SNMP discovered',
      uptime: fmtUptime(dev.uptime_seconds),
      ports: ifaces.length, portUp: ifaces.filter(i=>i.status==='up').length,
      cpu: met?.cpu_usage??null, mem: met?.memory_usage??null,
      temp: met?.temperature??null, fw: dev.firmware_version??'—',
      status, alertCount: alerts.filter(a=>a.device_id===dev.id).length,
    }
  }), [devices, ifByDev, latestMet, liveById, alerts])

  const oids = useMemo(() => {
    const out: {oid:string;name:string;device:string;value:string;type:string}[] = []
    for (const dev of devices) {
      const ifaces = ifByDev.get(dev.id)??[]
      const met    = latestMet.get(dev.id)
      const lbl    = dev.hostname||dev.ip_address
      out.push({oid:'1.3.6.1.2.1.1.3.0',  name:'sysUpTime',   device:lbl, value:fmtUptime(dev.uptime_seconds), type:'TimeTicks'})
      out.push({oid:'1.3.6.1.2.1.2.1.0',  name:'ifNumber',    device:lbl, value:String(ifaces.length),        type:'Integer'})
      if (met?.cpu_usage    !=null) out.push({oid:'1.3.6.1.4.1.9.9.109.1.1.1.1.6', name:'cpuUsage',    device:lbl, value:`${met.cpu_usage.toFixed(1)}%`,    type:'Gauge32'})
      if (met?.memory_usage !=null) out.push({oid:'1.3.6.1.4.1.9.9.48.1.1.1.5',   name:'memoryUsed',  device:lbl, value:`${met.memory_usage.toFixed(1)}%`, type:'Gauge32'})
      if (met?.temperature  !=null) out.push({oid:'1.3.6.1.4.1.9.9.13.1.3.1.3',   name:'temperature', device:lbl, value:`${met.temperature.toFixed(1)} °C`, type:'Gauge32'})
      for (const iface of ifaces) {
        out.push({oid:`1.3.6.1.2.1.2.2.1.10.${iface.id}`,name:`ifIn[${iface.interface_name}]`,  device:lbl,value:fmtBytes(iface.traffic_in), type:'Counter64'})
        out.push({oid:`1.3.6.1.2.1.2.2.1.16.${iface.id}`,name:`ifOut[${iface.interface_name}]`, device:lbl,value:fmtBytes(iface.traffic_out),type:'Counter64'})
      }
    }
    return out
  }, [devices, ifByDev, latestMet])

  const traps = useMemo(() => {
    const names = ['linkDown','linkUp','authenticationFailure','warmStart','coldStart','bgpBackwardTransition','ifStatusChange']
    return alerts.map((a,i) => {
      const dev = a.device_id ? deviceById.get(a.device_id) : null
      return {
        id:`TRAP-${1000+i}`,
        ts: new Date(a.created_at).toLocaleTimeString('en-IN',{timeZone:'Asia/Kolkata',hour12:false}),
        date: new Date(a.created_at).toLocaleDateString('en-IN',{timeZone:'Asia/Kolkata',day:'2-digit',month:'short'}),
        device: dev?`${dev.hostname} (${dev.ip_address})`:(a.device_id?`DEV-${a.device_id}`:'NMS-SERVER'),
        oid: names[i%names.length],
        severity: a.severity==='critical'?'critical':a.severity==='high'?'high':a.severity==='medium'?'warning':'info',
        msg: a.title, description: a.description??'', status: a.status,
      }
    })
  }, [alerts, deviceById])

  const onlineCount = inventory.filter(d=>d.status==='online').length

  /* ── render ────────────────────────────────────────────────────────────── */
  return (
    <div className="p-4 md:p-6 space-y-4 md:space-y-5">

      {/* ── header ─────────────────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <div>
          <h1 className="font-display font-bold text-xl sm:text-2xl tracking-widest neon-cyan">SNMP MONITORING</h1>
          <p className="font-mono text-xs mt-0.5" style={{ color: '#8899bb' }}>
            {devices.length} devices · {interfaces.length} interfaces · {alerts.length} traps
            {lastUpdate && ` · updated ${lastUpdate}`}
          </p>
        </div>
        <div className="flex flex-wrap gap-2 items-center">
          <span className="glass-bright rounded px-3 py-1.5 font-mono text-xs" style={{ color:'#00d4ff', border:'1px solid rgba(0,212,255,0.25)' }}>
            SNMPv3 · Community: nexus-soc
          </span>
          <button onClick={()=>void loadData()}
            className="glass-bright px-3 py-1.5 rounded font-mono text-xs hover:bg-cyan-400/10 flex items-center gap-1.5"
            style={{ border:'1px solid rgba(0,212,255,0.25)', color:'#00d4ff' }}>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M23 4v6h-6M1 20v-6h6"/><path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/>
            </svg>
            REFRESH
          </button>
        </div>
      </div>

      {error && (
        <div className="font-mono text-xs p-3 rounded" style={{ color:'#ff3366', background:'rgba(255,51,102,0.1)', border:'1px solid rgba(255,51,102,0.3)' }}>
          {error}
        </div>
      )}

      {/* ── service controls ───────────────────────────────────────────── */}
      <GlassCard className="p-4">
        <div className="font-display font-bold text-sm tracking-wider neon-cyan mb-3">SERVICE CONTROLS</div>
        <div className="flex flex-wrap gap-3 items-center">
          <SvcBtn label="PING MONITOR"  active={pingOn}  busy={pingBusy} onToggle={()=>void togglePing()} />
          <SvcBtn label="SNMP POLLING"  active={pollOn}  busy={false}    onToggle={()=>setPollOn(v=>!v)} />
          <SvcBtn label="AUTO REFRESH"  active={autoOn}  busy={false}    onToggle={()=>setAutoOn(v=>!v)} />
          {devices.length > 0 && (
            <div className="ml-auto flex items-center gap-2">
              <span className="font-mono text-xs" style={{ color:'#8899bb' }}>Device:</span>
              <select value={selectedId??''} onChange={e=>setSelected(Number(e.target.value))}
                className="glass-bright rounded px-2 py-1 font-mono text-xs"
                style={{ border:'1px solid rgba(0,212,255,0.25)', color:'#c8d8ee', background:'rgba(8,25,55,0.7)' }}>
                {devices.map(d=><option key={d.id} value={d.id}>{d.hostname||d.ip_address}</option>)}
              </select>
            </div>
          )}
        </div>
        {!pingOn  && <p className="mt-2 font-mono text-[10px]" style={{color:'#ffaa00'}}>⚠ Ping monitoring stopped — devices show last-known status.</p>}
        {!pollOn  && <p className="mt-1 font-mono text-[10px]" style={{color:'#ffaa00'}}>⚠ SNMP polling paused — metrics will not update.</p>}
        {!autoOn  && <p className="mt-1 font-mono text-[10px]" style={{color:'#8899bb'}}>ℹ Auto-refresh disabled — click REFRESH to update manually.</p>}
      </GlassCard>

      {/* ── discovery panel ─────────────────────────────────────────────── */}
      <SNMPDiscoveryPanel onCompleted={()=>void loadData()} />

      {/* ── stat tiles ──────────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
        {([
          { l:'Discovered Devices', v:devices.length,    c:'#00d4ff' },
          { l:'Online',             v:onlineCount,       c:'#00ff88' },
          { l:'Interfaces',         v:interfaces.length, c:'#7c3aed' },
          { l:'Traps Received',     v:alerts.length,     c:'#ffaa00' },
          { l:'OIDs Polled',        v:oids.length,       c:'#00bfff' },
        ] as const).map(s=>(
          <GlassCard key={s.l} className="p-4 text-center">
            <div className="font-display font-bold text-xl sm:text-2xl" style={{color:s.c}}>{s.v}</div>
            <div className="font-mono text-xs mt-1" style={{color:'#8899bb'}}>{s.l}</div>
          </GlassCard>
        ))}
      </div>

      {/* ── navigate to sub-pages ───────────────────────────────────────── */}
      <GlassCard className="p-4">
        <div className="flex items-center justify-between mb-3">
          <div className="font-display font-bold text-sm tracking-wider neon-cyan">SNMP MODULES</div>
          {!selectedId && <span className="font-mono text-[10px]" style={{color:'#ffaa00'}}>Select a device above to navigate</span>}
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3">
          {SNMP_NAV.map(nav => {
            const disabled = !selectedId
            return (
              <button
                key={nav.label}
                onClick={() => { if (selectedId) navigate(nav.path(selectedId)) }}
                disabled={disabled}
                className="flex flex-col gap-2 p-3 rounded-lg text-left transition-all group"
                style={{
                  border: `1px solid ${disabled ? 'rgba(136,153,187,0.15)' : nav.color + '33'}`,
                  background: disabled ? 'rgba(255,255,255,0.02)' : `${nav.color}0d`,
                  cursor: disabled ? 'not-allowed' : 'pointer',
                  opacity: disabled ? 0.45 : 1,
                }}>
                <div className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0"
                  style={{ background: disabled ? 'rgba(255,255,255,0.05)' : `${nav.color}1a`, border: `1px solid ${disabled ? 'rgba(136,153,187,0.2)' : nav.color + '44'}` }}>
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
                    stroke={disabled ? '#8899bb' : nav.color} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                    <path d={nav.icon} />
                  </svg>
                </div>
                <div>
                  <div className="font-mono text-xs font-semibold leading-tight" style={{ color: disabled ? '#8899bb' : nav.color }}>
                    {nav.label}
                  </div>
                  <div className="font-mono text-[10px] mt-0.5 leading-tight" style={{ color: '#667799' }}>
                    {nav.desc}
                  </div>
                </div>
              </button>
            )
          })}
        </div>
      </GlassCard>

      {/* ── tabs ────────────────────────────────────────────────────────── */}
      <div className="flex flex-wrap gap-2">
        {(['devices','oids','traps'] as const).map(t => (
          <button key={t} onClick={()=>setTab(t)}
            className="font-mono text-xs px-4 py-2 rounded capitalize transition-all"
            style={{
              background: tab===t ? 'rgba(0,212,255,0.15)' : 'transparent',
              color:  tab===t ? '#00d4ff' : '#8899bb',
              border: `1px solid ${tab===t ? 'rgba(0,212,255,0.4)' : 'rgba(0,212,255,0.1)'}`,
            }}>{t.toUpperCase()}</button>
        ))}
      </div>

      {/* ── DEVICES tab ─────────────────────────────────────────────────── */}
      {tab === 'devices' && (
        <GlassCard className="overflow-hidden">
          <div className="p-4" style={{ borderBottom:'1px solid rgba(0,212,255,0.1)' }}>
            <div className="font-display font-bold text-base tracking-wider neon-cyan">DEVICE INVENTORY</div>
            <div className="font-mono text-xs mt-0.5" style={{color:'#8899bb'}}>
              Live data · CPU/MEM from latest poll · click a device to open SNMP dashboard
            </div>
          </div>
          {inventory.length === 0 ? (
            <div className="font-mono text-xs p-6 text-center" style={{color:'#8899bb'}}>
              No devices found. Run SNMP Discovery above to detect devices.
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-0">
              {inventory.map(dev => {
                const icon = TYPE_ICON[dev.type]??TYPE_ICON.default
                return (
                  <div key={dev.id}
                    onClick={()=>{ if (selectedId===dev.id) navigate(`/snmp/devices/${dev.id}`); else setSelected(dev.id) }}
                    role="button" tabIndex={0}
                    onKeyDown={e=>{ if(e.key==='Enter') navigate(`/snmp/devices/${dev.id}`) }}
                    className="p-3 sm:p-4 flex gap-3 sm:gap-4 transition-all hover:bg-cyan-400/5 cursor-pointer"
                    style={{ borderBottom:'1px solid rgba(0,212,255,0.06)', borderRight:'1px solid rgba(0,212,255,0.06)',
                      background: selectedId===dev.id ? 'rgba(0,212,255,0.05)' : undefined }}>
                    <div className="w-9 h-9 rounded-lg flex items-center justify-center shrink-0"
                      style={{ background:'rgba(0,212,255,0.08)', border:'1px solid rgba(0,212,255,0.2)' }}>
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#00d4ff" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                        <path d={icon}/>
                      </svg>
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1 flex-wrap">
                        <span className="font-mono text-xs font-semibold truncate" style={{color:'#c8d8ee'}}>{dev.hostname}</span>
                        <span className={`status-dot ${dev.status} shrink-0`}/>
                        {dev.alertCount > 0 && (
                          <span className="font-mono text-[9px] px-1.5 py-0.5 rounded shrink-0" style={{background:'rgba(255,51,102,0.15)',color:'#ff3366'}}>
                            {dev.alertCount} alert{dev.alertCount!==1?'s':''}
                          </span>
                        )}
                      </div>
                      <div className="font-mono text-[10px] mb-1 truncate" style={{color:'#8899bb'}}>{dev.model}</div>
                      {isSuperAdmin && (
                        <div className="flex gap-2 mb-1">
                          <button onClick={e=>{e.stopPropagation();const orig=deviceById.get(dev.id);if(orig)void editDevice(orig)}}
                            className="font-mono text-[10px] px-2 py-0.5 rounded border"
                            style={{color:'#00d4ff',borderColor:'rgba(0,212,255,0.35)'}}>EDIT</button>
                          <button onClick={e=>{e.stopPropagation();void removeDevice(dev.id)}}
                            className="font-mono text-[10px] px-2 py-0.5 rounded border"
                            style={{color:'#ff6688',borderColor:'rgba(255,102,136,0.35)'}}>DELETE</button>
                        </div>
                      )}
                      <div className="grid grid-cols-2 gap-x-3 gap-y-0.5">
                        {([
                          {l:'IP',    v:dev.ip},
                          {l:'MAC',   v:dev.mac},
                          {l:'Uptime',v:dev.uptime},
                          {l:'Ports', v:dev.ports>0?`${dev.portUp}/${dev.ports} up`:'—'},
                          {l:'CPU',   v:dev.cpu!=null?`${dev.cpu.toFixed(1)}%`:'—',   c:dev.cpu!=null?(dev.cpu>70?'#ff3366':'#00ff88'):undefined},
                          {l:'MEM',   v:dev.mem!=null?`${dev.mem.toFixed(1)}%`:'—',   c:dev.mem!=null?(dev.mem>80?'#ffaa00':'#00ff88'):undefined},
                          {l:'TEMP',  v:dev.temp!=null?`${dev.temp.toFixed(1)} °C`:'—',c:dev.temp!=null?(dev.temp>70?'#ff3366':'#00d4ff'):undefined},
                          {l:'FW',    v:dev.fw},
                        ] as {l:string;v:string;c?:string}[]).map(m=>(
                          <div key={m.l} className="flex gap-1 min-w-0">
                            <span className="font-mono text-[10px] shrink-0" style={{color:'#556677'}}>{m.l}:</span>
                            <span className="font-mono text-[10px] truncate" style={{color:m.c??'#8899bb'}}>{m.v}</span>
                          </div>
                        ))}
                      </div>
                      {/* quick SNMP sub-page links for selected device */}
                      {selectedId===dev.id && (
                        <div className="flex flex-wrap gap-1 mt-2 pt-2" style={{borderTop:'1px solid rgba(0,212,255,0.1)'}}>
                          {SNMP_NAV.slice(0,5).map(nav=>(
                            <button key={nav.label}
                              onClick={e=>{e.stopPropagation();navigate(nav.path(dev.id))}}
                              className="font-mono text-[9px] px-2 py-0.5 rounded"
                              style={{background:`${nav.color}15`,color:nav.color,border:`1px solid ${nav.color}30`}}>
                              {nav.label}
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </GlassCard>
      )}

      {/* ── OIDs tab ────────────────────────────────────────────────────── */}
      {tab === 'oids' && (
        <GlassCard className="overflow-hidden">
          <div className="p-4" style={{borderBottom:'1px solid rgba(0,212,255,0.1)'}}>
            <div className="font-display font-bold text-base tracking-wider neon-cyan">OID MONITORING</div>
            <div className="font-mono text-xs mt-0.5" style={{color:'#8899bb'}}>
              {oids.length} OIDs · sysUpTime, interfaces, CPU, memory, temperature
            </div>
          </div>
          {oids.length === 0 ? (
            <div className="font-mono text-xs p-6 text-center" style={{color:'#8899bb'}}>
              No OID data. Add devices with SNMP credentials to see polling data.
            </div>
          ) : (
            <div className="max-h-[600px] overflow-y-auto overflow-x-auto">
              <table className="w-full" style={{minWidth:500}}>
                <thead>
                  <tr style={{borderBottom:'1px solid rgba(0,212,255,0.08)'}}>
                    {['OID','Name','Device','Value','Type'].map(h=>(
                      <th key={h} className="text-left px-4 py-2.5 font-mono text-xs sticky top-0"
                        style={{color:'#8899bb',background:'rgba(8,25,55,0.95)'}}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {oids.map((o,i)=>(
                    <tr key={`${o.oid}-${i}`} style={{borderBottom:'1px solid rgba(0,212,255,0.04)'}}>
                      <td className="px-4 py-2 font-mono text-xs neon-cyan">{o.oid}</td>
                      <td className="px-4 py-2 font-mono text-xs" style={{color:'#c8d8ee'}}>{o.name}</td>
                      <td className="px-4 py-2 font-mono text-xs" style={{color:'#8899bb'}}>{o.device}</td>
                      <td className="px-4 py-2 font-mono text-sm font-semibold" style={{color:'#00ff88'}}>{o.value}</td>
                      <td className="px-4 py-2 font-mono text-xs" style={{color:'#7c3aed'}}>{o.type}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </GlassCard>
      )}

      {/* ── TRAPS tab ───────────────────────────────────────────────────── */}
      {tab === 'traps' && (
        <GlassCard className="overflow-hidden">
          <div className="p-4" style={{borderBottom:'1px solid rgba(0,212,255,0.1)'}}>
            <div className="font-display font-bold text-base tracking-wider neon-cyan">TRAP NOTIFICATIONS</div>
            <div className="font-mono text-xs mt-0.5" style={{color:'#8899bb'}}>
              {traps.length} traps from device alerts
            </div>
          </div>
          <div className="max-h-[600px] overflow-y-auto">
            {traps.length === 0 ? (
              <div className="font-mono text-xs text-center py-6" style={{color:'#8899bb'}}>
                No traps received. Device alerts appear here as SNMP trap notifications.
              </div>
            ) : traps.map(trap => {
              const s = SEV[trap.severity]??SEV.info
              return (
                <div key={trap.id} className="flex items-start gap-3 px-4 py-3"
                  style={{borderBottom:'1px solid rgba(0,212,255,0.06)'}}>
                  <span className="font-mono text-xs font-semibold px-2 py-0.5 rounded uppercase shrink-0 mt-0.5"
                    style={{color:s.c,background:s.bg,border:`1px solid ${s.c}30`}}>{trap.severity}</span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-mono text-xs neon-cyan">{trap.id}</span>
                      <span className="font-mono text-xs px-1.5 py-0.5 rounded"
                        style={{color:trap.status==='resolved'?'#00ff88':'#ffaa00',background:trap.status==='resolved'?'rgba(0,255,136,0.1)':'rgba(255,170,0,0.1)'}}>
                        {trap.status}
                      </span>
                      <span className="font-mono text-xs ml-auto shrink-0" style={{color:'#8899bb'}}>{trap.date} {trap.ts}</span>
                    </div>
                    <div className="font-mono text-xs mt-1" style={{color:'#c8d8ee'}}>{trap.msg}</div>
                    {trap.description && <div className="font-mono text-xs mt-0.5" style={{color:'#667799'}}>{trap.description}</div>}
                    <div className="flex flex-wrap gap-x-4 mt-1">
                      <span className="font-mono text-xs" style={{color:'#8899bb'}}>Device: <span style={{color:'#c8d8ee'}}>{trap.device}</span></span>
                      <span className="font-mono text-xs" style={{color:'#8899bb'}}>OID: <span style={{color:'#7c3aed'}}>{trap.oid}</span></span>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        </GlassCard>
      )}

    </div>
  )
}
