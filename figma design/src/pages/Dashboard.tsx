import { useEffect, useMemo, useRef, useState } from 'react'
import GlassCard from '../components/GlassCard'
import {
  AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, RadialBarChart, RadialBar,
} from 'recharts'
import {
  getOverview, killAllServices,
  type OverviewResponse,
} from '../lib/api'

const COLORS = ['#ff3366', '#ffaa00', '#7c3aed', '#00d4ff', '#00ff88']

/* ─── stat tile ─────────────────────────────────────────────────────────────── */
function StatTile({ label, value, sub, glow, icon }: {
  label: string; value: string | number; sub?: string
  glow?: 'cyan'|'green'|'red'|'amber'; icon: string
}) {
  const c = { cyan:'#00d4ff', green:'#00ff88', red:'#ff3366', amber:'#ffaa00' } as const
  const col = glow ? c[glow] : '#00d4ff'
  return (
    <GlassCard glow={glow} className="p-3 md:p-5">
      <div className="flex items-start justify-between mb-2 md:mb-3">
        <div className="w-9 h-9 rounded-lg flex items-center justify-center shrink-0"
          style={{ background:`${col}15`, border:`1px solid ${col}30` }}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke={col}
            strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <path d={icon}/>
          </svg>
        </div>
        <span className="font-mono text-xs px-2 py-0.5 rounded" style={{ color:col, background:`${col}15` }}>LIVE</span>
      </div>
      <div className="font-display font-bold text-xl sm:text-3xl leading-none" style={{ color:col }}>{value}</div>
      <div className="font-mono text-xs mt-1 tracking-wider" style={{ color:'#8899bb' }}>{label}</div>
      {sub && <div className="font-mono text-xs mt-0.5" style={{ color:'#556677' }}>{sub}</div>}
    </GlassCard>
  )
}

/* ─── service status pill ────────────────────────────────────────────────────── */
function SvcPill({ label, running }: { label: string; running: boolean }) {
  return (
    <span className="flex items-center gap-1.5 font-mono text-[10px] px-2 py-1 rounded"
      style={{
        border:  `1px solid ${running?'rgba(0,255,136,0.35)':'rgba(255,51,102,0.35)'}`,
        background: running?'rgba(0,255,136,0.07)':'rgba(255,51,102,0.07)',
        color:   running?'#00ff88':'#ff6688',
      }}>
      <span className="w-1.5 h-1.5 rounded-full"
        style={{ background:running?'#00ff88':'#ff3366', boxShadow:`0 0 4px ${running?'#00ff88':'#ff3366'}` }}/>
      {label}: {running?'RUNNING':'STOPPED'}
    </span>
  )
}

/* ─── main page ──────────────────────────────────────────────────────────────── */
export default function Dashboard() {
  const [activeTab,  setActiveTab]  = useState<'in'|'out'>('in')
  const [data,       setData]       = useState<OverviewResponse|null>(null)
  const [loading,    setLoading]    = useState(true)
  const [error,      setError]      = useState<string|null>(null)
  const [fetchedAt,  setFetchedAt]  = useState('')
  const [killing,    setKilling]    = useState(false)
  const [killMsg,    setKillMsg]    = useState<string|null>(null)
  const abortRef = useRef<AbortController|null>(null)

  /* single DB fetch — no interval, no repeated calls on navigation */
  const load = async () => {
    abortRef.current?.abort()
    abortRef.current = new AbortController()
    setLoading(true); setError(null)
    try {
      const r = await getOverview()
      setData(r)
      setFetchedAt(new Date(r.fetched_at).toLocaleTimeString())
    } catch (e) {
      if ((e as Error).name !== 'AbortError')
        setError(e instanceof Error ? e.message : 'Load failed')
    } finally { setLoading(false) }
  }

  useEffect(() => {
    void load()
    return () => { abortRef.current?.abort() }
  }, []) // eslint-disable-line

  /* kill all backend services */
  const handleKillAll = async () => {
    if (!window.confirm(
      'Stop ALL backend monitoring services?\n\n' +
      '• SNMP Polling Engine (APScheduler) → STOPPED\n' +
      '• Realtime ICMP Monitor → STOPPED\n' +
      '• All device monitoring_status → paused\n\n' +
      'Data in DB is not deleted. Restart the backend server to resume.'
    )) return
    setKilling(true); setKillMsg(null)
    try {
      const r = await killAllServices()
      setKillMsg(r.success
        ? `✓ All services stopped. Killed: ${r.killed.length}`
        : `⚠ Partial stop — errors: ${r.errors.join('; ')}`)
      void load()          // refresh service states
    } catch (e) {
      setKillMsg(`Error: ${e instanceof Error ? e.message : String(e)}`)
    } finally { setKilling(false) }
  }

  /* derived */
  const s  = data?.summary
  const devs = data?.devices ?? []
  const alerts = data?.alerts ?? []
  const events = data?.events ?? []
  const svc  = data?.services

  const healthScore = s ? Math.round((s.online_devices/Math.max(1,s.total_devices))*100) : 0

  const threatData = useMemo(()=>[
    { name:'Critical', count:alerts.filter(a=>a.severity==='critical').length, color:'#ff3366' },
    { name:'High',     count:alerts.filter(a=>a.severity==='high').length,     color:'#ffaa00' },
    { name:'Medium',   count:alerts.filter(a=>a.severity==='medium'||a.severity==='warning').length, color:'#7c3aed' },
  ],[alerts])

  const serverStatus = useMemo(()=>devs.slice(0,5).map(d=>({
    name:d.hostname, cpu:d.cpu_usage??0, ram:d.memory_usage??0, status:d.status,
  })),[devs])

  const healthGauge = [{ value:healthScore, fill:'#00d4ff' }]

  const trafficData = useMemo(()=>Array.from({length:24},(_,i)=>({
    t:`${i}:00`, in:200+(events.length?(i%7)*60:0), out:140+(i%5)*40,
  })),[events.length])

  const summaryCards = [
    { label:'TOTAL DEVICES',   value:s?.total_devices??0,    sub:`${s?.online_devices??0} online`,    glow:'cyan'  as const, icon:'M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z' },
    { label:'ACTIVE INCIDENTS', value:s?.active_alerts??0,   sub:`${s?.critical_alerts??0} critical`, glow:'red'   as const, icon:'M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z' },
    { label:'CRITICAL ALERTS',  value:s?.critical_alerts??0, sub:'Last 24h',                          glow:'amber' as const, icon:'M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9' },
    { label:'THREATS BLOCKED',  value:s?.recent_events??0,   sub:'This week',                         glow:'green' as const, icon:'M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z' },
    { label:'HEALTH SCORE',     value:`${healthScore}%`,     sub:`${s?.offline_devices??0} offline`,  glow:'amber' as const, icon:'M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z' },
  ]

  return (
    <div className="p-4 md:p-6 space-y-4 md:space-y-5">

      {/* ── header ──────────────────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <div className="flex-1 min-w-0">
          <h1 className="font-display font-bold text-xl sm:text-2xl tracking-widest neon-cyan">SOC OVERVIEW</h1>
          <p className="font-mono text-xs mt-0.5" style={{ color:'#8899bb' }}>
            Security Operations Center — data fetched from DB once on load
            {fetchedAt && ` · fetched ${fetchedAt}`}
          </p>
        </div>
        <div className="flex flex-wrap gap-2 items-center">
          {svc && (
            <>
              <SvcPill label="SNMP" running={svc.snmp_polling.running}/>
              <SvcPill label="ICMP" running={svc.realtime_monitor.running}/>
            </>
          )}
          <button onClick={()=>void load()} disabled={loading}
            className="font-mono text-xs px-3 py-2 rounded glass-bright flex items-center gap-1.5 hover:bg-cyan-400/10 transition-all"
            style={{ border:'1px solid rgba(0,212,255,0.25)', color:'#00d4ff', opacity:loading?0.5:1 }}>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M23 4v6h-6M1 20v-6h6"/>
              <path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/>
            </svg>
            {loading?'Loading…':'REFRESH DB'}
          </button>
          {/* ── KILL ALL SERVICES ── */}
          <button onClick={()=>void handleKillAll()} disabled={killing}
            className="font-mono text-xs px-4 py-2 rounded font-semibold flex items-center gap-2 transition-all"
            style={{
              border:`1px solid ${killing?'rgba(255,51,102,0.3)':'rgba(255,51,102,0.6)'}`,
              background: killing?'rgba(255,51,102,0.08)':'rgba(255,51,102,0.15)',
              color:'#ff3366', opacity:killing?0.55:1, cursor:killing?'not-allowed':'pointer',
              boxShadow:!killing?'0 0 10px rgba(255,51,102,0.25)':'none',
            }}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <rect x="9" y="2" width="6" height="6" rx="1"/>
              <path d="M12 8v4m0 4h.01M5.07 19a9 9 0 1113.86 0"/>
            </svg>
            {killing?'Stopping…':'■ KILL ALL SERVICES'}
          </button>
        </div>
      </div>

      {/* kill result */}
      {killMsg && (
        <div className="flex items-center justify-between gap-3 font-mono text-xs p-3 rounded"
          style={{
            background: killMsg.startsWith('✓')?'rgba(0,255,136,0.07)':'rgba(255,170,0,0.07)',
            border:`1px solid ${killMsg.startsWith('✓')?'rgba(0,255,136,0.25)':'rgba(255,170,0,0.25)'}`,
            color: killMsg.startsWith('✓')?'#00ff88':'#ffaa00',
          }}>
          <span>{killMsg}</span>
          <button onClick={()=>setKillMsg(null)} className="opacity-60 hover:opacity-100 text-sm">✕</button>
        </div>
      )}

      {error && (
        <div className="font-mono text-xs p-3 rounded" style={{ color:'#ff3366', background:'rgba(255,51,102,0.07)', border:'1px solid rgba(255,51,102,0.25)' }}>
          {error}
        </div>
      )}

      {/* ── service status bar ──────────────────────────────────────────── */}
      {svc && (
        <GlassCard className="p-3">
          <div className="flex flex-wrap items-center gap-4">
            <span className="font-mono text-xs font-semibold" style={{ color:'#8899bb' }}>SERVICES</span>
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full" style={{ background:svc.snmp_polling.running?'#00ff88':'#ff3366', boxShadow:`0 0 5px ${svc.snmp_polling.running?'#00ff88':'#ff3366'}` }}/>
              <span className="font-mono text-xs" style={{ color:'#c8d8ee' }}>SNMP Polling Engine</span>
              <span className="font-mono text-[10px] px-1.5 py-0.5 rounded" style={{ color:svc.snmp_polling.running?'#00ff88':'#ff3366', background:svc.snmp_polling.running?'rgba(0,255,136,0.1)':'rgba(255,51,102,0.1)' }}>
                {svc.snmp_polling.running?`RUNNING · ${svc.snmp_polling.job_count??0} jobs`:'STOPPED'}
              </span>
            </div>
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full" style={{ background:svc.realtime_monitor.running?'#00ff88':'#ff3366', boxShadow:`0 0 5px ${svc.realtime_monitor.running?'#00ff88':'#ff3366'}` }}/>
              <span className="font-mono text-xs" style={{ color:'#c8d8ee' }}>Realtime ICMP Monitor</span>
              <span className="font-mono text-[10px] px-1.5 py-0.5 rounded" style={{ color:svc.realtime_monitor.running?'#00ff88':'#ff3366', background:svc.realtime_monitor.running?'rgba(0,255,136,0.1)':'rgba(255,51,102,0.1)' }}>
                {svc.realtime_monitor.running?`RUNNING · ${svc.realtime_monitor.device_count??0} devices`:'STOPPED'}
              </span>
            </div>
            {!svc.any_running && (
              <span className="font-mono text-[10px] ml-auto" style={{ color:'#ffaa00' }}>
                ⚠ All services stopped — restart server to resume automatic monitoring
              </span>
            )}
          </div>
        </GlassCard>
      )}

      {/* ── KPI tiles ───────────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3 md:gap-4">
        {summaryCards.map(card=>(
          <StatTile key={card.label} label={card.label} value={card.value} sub={card.sub} glow={card.glow} icon={card.icon}/>
        ))}
      </div>

      {/* ── main row: traffic + health ──────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <GlassCard className="lg:col-span-2 p-4 md:p-5">
          <div className="flex items-center justify-between mb-4 gap-3">
            <div>
              <div className="font-display font-bold text-sm tracking-wider neon-cyan">TRAFFIC OVERVIEW</div>
              <div className="font-mono text-xs" style={{ color:'#8899bb' }}>Inbound / Outbound Mbps · 24h</div>
            </div>
            <div className="flex gap-2">
              {(['in','out'] as const).map(t=>(
                <button key={t} onClick={()=>setActiveTab(t)}
                  className="font-mono text-xs px-3 py-2 rounded transition-all"
                  style={{ background:activeTab===t?'rgba(0,212,255,0.15)':'transparent', color:activeTab===t?'#00d4ff':'#8899bb', border:`1px solid ${activeTab===t?'rgba(0,212,255,0.4)':'rgba(0,212,255,0.1)'}` }}>
                  {t.toUpperCase()}
                </button>
              ))}
            </div>
          </div>
          <ResponsiveContainer width="100%" height={200}>
            <AreaChart data={trafficData}>
              <defs>
                <linearGradient id="gin"  x1="0" y1="0" x2="0" y2="1"><stop offset="5%"  stopColor="#00d4ff" stopOpacity={0.3}/><stop offset="95%" stopColor="#00d4ff" stopOpacity={0}/></linearGradient>
                <linearGradient id="gout" x1="0" y1="0" x2="0" y2="1"><stop offset="5%"  stopColor="#00ff88" stopOpacity={0.3}/><stop offset="95%" stopColor="#00ff88" stopOpacity={0}/></linearGradient>
              </defs>
              <XAxis dataKey="t" tick={{ fill:'#8899bb',fontSize:11,fontFamily:'JetBrains Mono' }} tickLine={false} axisLine={false} interval={3}/>
              <YAxis   tick={{ fill:'#8899bb',fontSize:11,fontFamily:'JetBrains Mono' }} tickLine={false} axisLine={false}/>
              <Tooltip contentStyle={{ background:'rgba(8,25,55,0.95)',border:'1px solid rgba(0,212,255,0.3)',borderRadius:6,fontFamily:'JetBrains Mono',fontSize:12 }}/>
              <Area type="monotone" dataKey="in"  stroke="#00d4ff" strokeWidth={2} fill="url(#gin)"  dot={false}/>
              <Area type="monotone" dataKey="out" stroke="#00ff88" strokeWidth={2} fill="url(#gout)" dot={false}/>
            </AreaChart>
          </ResponsiveContainer>
        </GlassCard>

        <GlassCard className="p-4 md:p-5">
          <div className="font-display font-bold text-base tracking-wider neon-cyan mb-4">NETWORK HEALTH</div>
          <div className="relative flex items-center justify-center" style={{ height:160 }}>
            <ResponsiveContainer width="100%" height={160}>
              <RadialBarChart cx="50%" cy="80%" innerRadius="70%" outerRadius="90%" startAngle={180} endAngle={0} data={healthGauge}>
                <RadialBar dataKey="value" cornerRadius={8} fill="#00d4ff" background={{ fill:'rgba(0,212,255,0.08)' }}/>
              </RadialBarChart>
            </ResponsiveContainer>
            <div className="absolute bottom-6 text-center">
              <div className="font-display font-bold text-4xl neon-cyan">{healthScore}</div>
              <div className="font-mono text-xs" style={{ color:'#8899bb' }}>/ 100</div>
            </div>
          </div>
          <div className="mt-2 space-y-2">
            {[
              { l:'Devices Online',  v:healthScore,                                              c:'#00d4ff' },
              { l:'Alert-free',      v:Math.max(0,100-(s?.critical_alerts??0)*15),              c:'#00ff88' },
              { l:'Event Load',      v:Math.max(0,100-Math.min(80,(s?.recent_events??0)*4)),    c:'#ffaa00' },
            ].map(item=>(
              <div key={item.l}>
                <div className="flex justify-between font-mono text-xs mb-1">
                  <span style={{ color:'#8899bb' }}>{item.l}</span>
                  <span style={{ color:item.c }}>{item.v}%</span>
                </div>
                <div className="h-1 rounded-full" style={{ background:'rgba(255,255,255,0.06)' }}>
                  <div className="h-1 rounded-full transition-all" style={{ width:`${item.v}%`,background:item.c }}/>
                </div>
              </div>
            ))}
          </div>
        </GlassCard>
      </div>

      {/* ── bottom row: threats · ISP · servers ─────────────────────────── */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {/* Threat Detection */}
        <GlassCard className="p-4 md:p-5">
          <div className="font-display font-bold text-base tracking-wider neon-cyan mb-4">THREAT DETECTION</div>
          <div className="flex gap-4">
            <ResponsiveContainer width={120} height={120}>
              <PieChart>
                <Pie data={threatData} cx="50%" cy="50%" innerRadius={35} outerRadius={55} dataKey="count" strokeWidth={0}>
                  {threatData.map((_,i)=><Cell key={i} fill={COLORS[i]}/>)}
                </Pie>
              </PieChart>
            </ResponsiveContainer>
            <div className="flex-1 space-y-2">
              {threatData.map((t,i)=>(
                <div key={t.name} className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div className="w-2 h-2 rounded-full" style={{ background:COLORS[i] }}/>
                    <span className="font-mono text-xs" style={{ color:'#8899bb' }}>{t.name}</span>
                  </div>
                  <span className="font-mono text-xs font-semibold" style={{ color:COLORS[i] }}>{t.count}</span>
                </div>
              ))}
              {alerts.length===0 && <div className="font-mono text-xs" style={{ color:'#667799' }}>No active alerts</div>}
            </div>
          </div>
        </GlassCard>

        {/* ISP Health — live from devices */}
        <GlassCard className="p-4 md:p-5">
          <div className="font-display font-bold text-base tracking-wider neon-cyan mb-4">DEVICE CONNECTIVITY</div>
          <div className="space-y-2">
            {devs.length===0 ? (
              <div className="font-mono text-xs" style={{ color:'#667799' }}>No devices in DB yet.</div>
            ) : devs.slice(0,4).map(dev=>(
              <div key={dev.id} className="rounded-lg p-3" style={{ background:'rgba(0,212,255,0.04)',border:'1px solid rgba(0,212,255,0.1)' }}>
                <div className="flex items-center justify-between mb-1">
                  <span className="font-mono text-xs font-semibold truncate" style={{ color:'#c8d8ee' }}>{dev.hostname}</span>
                  <span className={`status-dot ${dev.status}`}/>
                </div>
                <div className="grid grid-cols-2 gap-1">
                  <div>
                    <div className="font-mono text-[10px]" style={{ color:'#8899bb' }}>Latency</div>
                    <div className="font-mono text-xs font-semibold" style={{ color:dev.latency&&dev.latency>100?'#ff3366':'#00ff88' }}>
                      {dev.latency ? `${dev.latency.toFixed(0)}ms` : '—'}
                    </div>
                  </div>
                  <div>
                    <div className="font-mono text-[10px]" style={{ color:'#8899bb' }}>Interfaces</div>
                    <div className="font-mono text-xs font-semibold" style={{ color:'#00d4ff' }}>
                      {dev.interface_count > 0 ? `${dev.interfaces_up}/${dev.interface_count} up` : '—'}
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </GlassCard>

        {/* Server / Device Status */}
        <GlassCard className="p-4 md:p-5">
          <div className="font-display font-bold text-base tracking-wider neon-cyan mb-4">SERVER STATUS</div>
          <div className="space-y-2">
            {serverStatus.length===0 ? (
              <div className="font-mono text-xs" style={{ color:'#667799' }}>No devices found in DB.</div>
            ) : serverStatus.map(s=>(
              <div key={s.name} className="flex items-center gap-3 py-2" style={{ borderBottom:'1px solid rgba(0,212,255,0.06)' }}>
                <span className={`status-dot ${s.status}`}/>
                <span className="font-mono text-xs flex-1 truncate" style={{ color:'#c8d8ee' }}>{s.name}</span>
                <div className="flex gap-3 shrink-0">
                  <div className="text-right">
                    <div className="font-mono text-xs" style={{ color:s.cpu>80?'#ff3366':'#8899bb' }}>{s.cpu>0?`${s.cpu.toFixed(0)}%`:'—'}</div>
                    <div className="font-mono text-[9px]" style={{ color:'#556677' }}>CPU</div>
                  </div>
                  <div className="text-right">
                    <div className="font-mono text-xs" style={{ color:s.ram>85?'#ffaa00':'#8899bb' }}>{s.ram>0?`${s.ram.toFixed(0)}%`:'—'}</div>
                    <div className="font-mono text-[9px]" style={{ color:'#556677' }}>RAM</div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </GlassCard>
      </div>

      {/* ── recent events ────────────────────────────────────────────────── */}
      {events.length > 0 && (
        <GlassCard className="overflow-hidden">
          <div className="p-4" style={{ borderBottom:'1px solid rgba(0,212,255,0.08)' }}>
            <div className="font-display font-bold text-sm tracking-wider neon-cyan">RECENT EVENTS</div>
            <div className="font-mono text-xs mt-0.5" style={{ color:'#8899bb' }}>Last 20 events · from DB</div>
          </div>
          <div className="max-h-48 overflow-y-auto">
            {events.map(ev=>(
              <div key={ev.id} className="flex items-start gap-3 px-4 py-2.5" style={{ borderBottom:'1px solid rgba(0,212,255,0.04)' }}>
                <span className="font-mono text-[10px] px-1.5 py-0.5 rounded shrink-0 mt-0.5"
                  style={{ color:'#00d4ff', background:'rgba(0,212,255,0.1)', border:'1px solid rgba(0,212,255,0.2)' }}>
                  {ev.event_type}
                </span>
                <div className="flex-1 min-w-0">
                  <div className="font-mono text-xs truncate" style={{ color:'#c8d8ee' }}>{ev.description??'—'}</div>
                  <div className="font-mono text-[10px] mt-0.5" style={{ color:'#667799' }}>
                    {ev.timestamp ? new Date(ev.timestamp).toLocaleString('en-IN',{timeZone:'Asia/Kolkata',hour12:true}) : ''}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </GlassCard>
      )}

    </div>
  )
}
