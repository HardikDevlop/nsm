import { useEffect, useMemo, useRef, useState } from 'react'
import GlassCard from '../components/GlassCard'
import RealtimeController from '../components/RealtimeController'
import { useRealtimeDevices, useRealtimeMetrics, useRealtimeAlerts } from '../hooks/useRealtimeData'
import {
  AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, RadialBarChart, RadialBar,
} from 'recharts'
import {
  killAllServices,
} from '../lib/api'
import { confirmDanger } from '../lib/swal'

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

/* ─── main page ──────────────────────────────────────────────────────────────── */
export default function Dashboard() {
  const [activeTab,  setActiveTab]  = useState<'in'|'out'>('in')
  const [killing,    setKilling]    = useState(false)
  const [killMsg,    setKillMsg]    = useState<string|null>(null)
  
  // Real-time control state
  const [refreshInterval, setRefreshInterval] = useState(5)  // seconds
  const [timeWindow, setTimeWindow] = useState(30)          // seconds  
  const [realtimeEnabled, setRealtimeEnabled] = useState(true)
  
  // Real-time data hooks
  const devicesRealtime = useRealtimeDevices(refreshInterval, timeWindow, realtimeEnabled)
  const metricsRealtime = useRealtimeMetrics(2, timeWindow, realtimeEnabled) // Keep metrics at 2s
  const alertsRealtime = useRealtimeAlerts(refreshInterval, timeWindow, realtimeEnabled)
  
  // Get current data
  const devices = devicesRealtime.data || []
  const metrics = metricsRealtime.data || []
  const alerts = alertsRealtime.data || []
  
  // Loading and error states
  const loading = devicesRealtime.loading || metricsRealtime.loading || alertsRealtime.loading
  const error = devicesRealtime.error || metricsRealtime.error || alertsRealtime.error

  /* kill all backend services */
  const handleKillAll = async () => {
    const ok = await confirmDanger({
      title: 'Stop all backend monitoring services?',
      text: 'SNMP polling, realtime ICMP monitor, and device monitoring status will be paused. Data in DB is not deleted.',
      confirmText: 'Stop Services',
    })
    if (!ok) return
    setKilling(true); setKillMsg(null)
    try {
      const r = await killAllServices()
      setKillMsg(r.success
        ? `✓ All services stopped. Killed: ${r.killed.length}`
        : `⚠ Partial stop — errors: ${r.errors?.join('; ') || 'Unknown error'}`)
      // Force refresh of real-time data
      devicesRealtime.refresh()
      alertsRealtime.refresh()
    } catch (e) {
      setKillMsg(`Error: ${e instanceof Error ? e.message : String(e)}`)
    } finally { setKilling(false) }
  }

  // Calculate dashboard stats from loaded data
  const stats = useMemo(() => {
    const totalDevices = devices.length
    const onlineDevices = devices.filter(d => d.status === 'online').length
    const criticalAlerts = alerts.filter(a => a.severity === 'critical' && a.status !== 'resolved').length
    const totalAlerts = alerts.filter(a => a.status !== 'resolved').length
    
    // Calculate average metrics from time window data
    const windowMetrics = metricsRealtime.getDataInWindow(timeWindow).map(d => d.data).flat()
    const avgCpu = windowMetrics.length > 0 
      ? windowMetrics.reduce((sum, m) => sum + (m.cpu_usage || 0), 0) / windowMetrics.length 
      : 0
    const avgMemory = windowMetrics.length > 0
      ? windowMetrics.reduce((sum, m) => sum + (m.memory_usage || 0), 0) / windowMetrics.length
      : 0

    return {
      totalDevices,
      onlineDevices,
      offlineDevices: totalDevices - onlineDevices,
      criticalAlerts,
      totalAlerts,
      avgCpu: Math.round(avgCpu * 10) / 10,
      avgMemory: Math.round(avgMemory * 10) / 10,
      dataPoints: windowMetrics.length,
      dataRate: metricsRealtime.getDataRate()
    }
  }, [devices, alerts, metricsRealtime, timeWindow])

  /* derived dashboard calculations */
  const healthScore = stats.totalDevices ? Math.round((stats.onlineDevices / stats.totalDevices) * 100) : 0

  const threatData = useMemo(()=>[
    { name:'Critical', count:alerts.filter(a=>a.severity==='critical' && a.status !== 'resolved').length, color:'#ff3366' },
    { name:'High',     count:alerts.filter(a=>a.severity==='high' && a.status !== 'resolved').length,     color:'#ffaa00' },
    { name:'Medium',   count:alerts.filter(a=>(a.severity==='medium'||a.severity==='warning') && a.status !== 'resolved').length, color:'#7c3aed' },
  ],[alerts])

  const serverStatus = useMemo(()=>{
    // Get latest metrics per device
    const deviceMetrics = devices.slice(0,5).map(d => {
      const latestMetric = metrics.find(m => m.device_id === d.id)
      return {
        name: d.hostname || d.ip_address,
        cpu: latestMetric?.cpu_usage ?? 0,
        ram: latestMetric?.memory_usage ?? 0,
        status: d.status,
      }
    })
    return deviceMetrics
  }, [devices, metrics])

  const trafficData = useMemo(()=>{
    // Generate traffic data from real-time metrics window
    const windowData = metricsRealtime.getDataInWindow(timeWindow)
    return windowData.map((entry, i) => ({
      time: new Date(entry.timestamp).toLocaleTimeString('en-US', { 
        hour12: false, 
        hour: '2-digit', 
        minute: '2-digit',
        second: '2-digit'
      }),
      in: Math.round((entry.data.find(m => m.bandwidth_usage)?.bandwidth_usage || 0) * 0.8),
      out: Math.round((entry.data.find(m => m.bandwidth_usage)?.bandwidth_usage || 0) * 0.6),
    })).slice(-20) // Show last 20 data points
  }, [metricsRealtime, timeWindow])

  // Summary cards for KPI section
  const summaryCards = useMemo(() => [
    {
      label: 'TOTAL DEVICES',
      value: `${stats.onlineDevices}/${stats.totalDevices}`,
      sub: `${stats.offlineDevices} offline ${realtimeEnabled ? '• Live' : '• Paused'}`,
      glow: stats.offlineDevices > 0 ? 'amber' as const : 'cyan' as const,
      icon: 'M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z'
    },
    {
      label: 'ACTIVE INCIDENTS',
      value: stats.criticalAlerts,
      sub: `${stats.totalAlerts} total alerts`,
      glow: stats.criticalAlerts > 0 ? 'red' as const : 'green' as const,
      icon: 'M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.732-.833-2.464 0L4.35 16.5c-.77.833.192 2.5 1.732 2.5z'
    },
    {
      label: 'AVG CPU LOAD',
      value: `${stats.avgCpu}%`,
      sub: `${timeWindow}s window • ${stats.dataPoints} points`,
      glow: stats.avgCpu > 70 ? 'red' as const : stats.avgCpu > 50 ? 'amber' as const : 'green' as const,
      icon: 'M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z'
    },
    {
      label: 'DATA RATE',
      value: `${stats.dataRate.toFixed(1)}/s`,
      sub: 'metrics per second',
      glow: stats.dataRate > 1 ? 'green' as const : 'amber' as const,
      icon: 'M13 10V3L4 14h7v7l9-11h-7z'
    },
    {
      label: 'HEALTH SCORE',
      value: `${healthScore}%`,
      sub: `system health • ${refreshInterval}s refresh`,
      glow: healthScore > 80 ? 'green' as const : healthScore > 60 ? 'amber' as const : 'red' as const,
      icon: 'M4.8 2.3A.3.3 0 105 2H4a2 2 0 00-2 2v1a.2.2 0 00.3.3l1.5-1.5zM7.5 5.5L9 4h6l1.5 1.5M20 12a8 8 0 11-16 0 8 8 0 0116 0zm-8-3a3 3 0 100 6 3 3 0 000-6z'
    }
  ], [stats, healthScore, timeWindow, refreshInterval, realtimeEnabled])

  return (
    <div className="p-4 md:p-6 space-y-4 md:space-y-5">

      {/* ── header ──────────────────────────────────────────────────────── */}
      <div className="flex flex-col lg:flex-row items-start lg:items-center justify-between gap-4">
        <div className="flex-1 min-w-0">
          <h1 className="font-display font-bold text-xl sm:text-2xl tracking-widest neon-cyan">SOC OVERVIEW</h1>
          <p className="font-mono text-xs mt-0.5" style={{ color:'#8899bb' }}>
            Security Operations Center — Real-time monitoring system
            {metricsRealtime.lastUpdate && (
              <span> • Updated {new Date(metricsRealtime.lastUpdate).toLocaleTimeString()}</span>
            )}
          </p>
        </div>
        
        {/* Compact Controls Row */}
        <div className="flex items-center gap-3">
          <RealtimeController
            currentInterval={refreshInterval}
            currentTimeWindow={timeWindow}
            isEnabled={realtimeEnabled}
            onIntervalChange={(interval) => {
              setRefreshInterval(interval)
              setRealtimeEnabled(true)
            }}
            onTimeWindowChange={setTimeWindow}
            onEnabledChange={setRealtimeEnabled}
          />
          
          <button onClick={()=>window.location.reload()} disabled={loading}
            className="font-mono text-xs px-3 py-2 rounded glass-bright flex items-center gap-1.5 hover:bg-cyan-400/10 transition-all"
            style={{ border:'1px solid rgba(0,212,255,0.25)', color:'#00d4ff', opacity:loading?0.5:1 }}>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M23 4v6h-6M1 20v-6h6"/>
              <path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/>
            </svg>
            REFRESH
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

      {/* ── KPI tiles ───────────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3 md:gap-4">
        {summaryCards.map(card=>(
          <StatTile key={card.label} label={card.label} value={card.value} sub={card.sub} glow={card.glow} icon={card.icon}/>
        ))}
      </div>

      {/* ── main row: traffic + health ──────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 md:gap-5">
        
        {/* Traffic Overview */}
        <GlassCard className="p-4 md:p-5">
          <div className="flex items-center justify-between mb-4">
            <div>
              <div className="font-display font-bold text-base tracking-wider neon-cyan">TRAFFIC OVERVIEW</div>
              <div className="font-mono text-xs mt-0.5" style={{ color:'#8899bb' }}>
                Real-time • {timeWindow}s window • {trafficData.length} points
              </div>
            </div>
            <div className="flex bg-gray-800/50 rounded p-0.5">
              {(['in','out'] as const).map(t=>(
                <button key={t} onClick={()=>setActiveTab(t)}
                  className={`font-mono text-[10px] px-2 py-1 rounded transition-all ${activeTab===t?'bg-cyan-500/20 text-cyan-400':'text-gray-400 hover:text-gray-300'}`}>
                  {t.toUpperCase()}
                </button>
              ))}
            </div>
          </div>
          {trafficData.length === 0 ? (
            <div className="font-mono text-xs py-8 text-center" style={{ color:'#8899bb' }}>No traffic data yet</div>
          ) : (
            <ResponsiveContainer width="100%" height={200}>
              <AreaChart data={trafficData}>
                <defs>
                  <linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor={activeTab==='in'?'#00d4ff':'#7c3aed'} stopOpacity={0.3}/>
                    <stop offset="95%" stopColor={activeTab==='in'?'#00d4ff':'#7c3aed'} stopOpacity={0}/>
                  </linearGradient>
                </defs>
                <XAxis dataKey="time" tick={{fill:'#8899bb',fontSize:10,fontFamily:'JetBrains Mono'}} tickLine={false} axisLine={false}/>
                <YAxis tick={{fill:'#8899bb',fontSize:10,fontFamily:'JetBrains Mono'}} tickLine={false} axisLine={false}/>
                <Tooltip contentStyle={{background:'rgba(8,25,55,0.95)',border:'1px solid rgba(0,212,255,0.3)',borderRadius:6,fontFamily:'JetBrains Mono',fontSize:11,color:'#c8d8ee'}}/>
                <Area type="monotone" dataKey={activeTab} stroke={activeTab==='in'?'#00d4ff':'#7c3aed'} strokeWidth={2} fill="url(#areaGrad)" dot={false}/>
              </AreaChart>
            </ResponsiveContainer>
          )}
        </GlassCard>

        {/* Network Health */}
        <GlassCard className="p-4 md:p-5">
          <div className="font-display font-bold text-base tracking-wider neon-cyan mb-1">NETWORK HEALTH</div>
          <div className="font-mono text-xs mb-4" style={{ color:'#8899bb' }}>
            {stats.onlineDevices} devices online
            {stats.offlineDevices > 0 && ` · ${stats.offlineDevices} offline`}
          </div>
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="font-mono text-xs" style={{ color:'#8899bb' }}>Devices Online</span>
              <span className="font-display font-bold" style={{ color:'#00ff88' }}>{healthScore}%</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="font-mono text-xs" style={{ color:'#8899bb' }}>Alert-Free</span>
              <span className="font-display font-bold" style={{ color:stats.totalAlerts>0?'#ffaa00':'#00ff88' }}>{stats.totalAlerts === 0 ? '100%' : `${Math.round(100-stats.totalAlerts*10)}%`}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="font-mono text-xs" style={{ color:'#8899bb' }}>Avg CPU Load</span>
              <span className="font-display font-bold" style={{ color:stats.avgCpu>70?'#ff3366':stats.avgCpu>50?'#ffaa00':'#00ff88' }}>{stats.avgCpu}%</span>
            </div>
          </div>
        </GlassCard>
      </div>

      {/* ── bottom row: threats + servers ──────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 md:gap-5">
        
        {/* Threat Detection */}
        <GlassCard className="p-4 md:p-5">
          <div className="font-display font-bold text-base tracking-wider neon-cyan mb-1">THREAT DETECTION</div>
          <div className="font-mono text-xs mb-4" style={{ color:'#8899bb' }}>No active threats</div>
          <div className="space-y-3">
            {threatData.map(item=>(
              <div key={item.name} className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded-full" style={{background:item.color}}/>
                  <span className="font-mono text-xs" style={{color:'#c8d8ee'}}>{item.name}</span>
                </div>
                <span className="font-display font-bold" style={{color:item.color}}>{item.count}</span>
              </div>
            ))}
          </div>
        </GlassCard>

        {/* Device Connectivity */}
        <GlassCard className="p-4 md:p-5">
          <div className="font-display font-bold text-base tracking-wider neon-cyan mb-1">DEVICE CONNECTIVITY</div>
          <div className="font-mono text-xs mb-4" style={{ color:'#8899bb' }}>No devices on DB yet</div>
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="font-mono text-xs" style={{ color:'#8899bb' }}>Devices Found</span>
              <span className="font-display font-bold" style={{ color:'#00d4ff' }}>{stats.totalDevices}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="font-mono text-xs" style={{ color:'#8899bb' }}>Online Now</span>
              <span className="font-display font-bold" style={{ color:'#00ff88' }}>{stats.onlineDevices}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="font-mono text-xs" style={{ color:'#8899bb' }}>Offline</span>
              <span className="font-display font-bold" style={{ color:'#ff3366' }}>{stats.offlineDevices}</span>
            </div>
          </div>
        </GlassCard>
      </div>

      {/* ── server status ─────────────────────────────────────────────── */}
      {serverStatus.length > 0 && (
        <GlassCard className="p-4 md:p-5">
          <div className="font-display font-bold text-base tracking-wider neon-cyan mb-1">SERVER STATUS</div>
          <div className="font-mono text-xs mb-4" style={{ color:'#8899bb' }}>Real-time metrics</div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-3">
            {serverStatus.map(srv=>(
              <div key={srv.name} className="rounded-lg p-3 space-y-2" style={{background:'rgba(0,212,255,0.04)', border:'1px solid rgba(0,212,255,0.1)'}}>
                <div className="flex items-center justify-between">
                  <span className="font-mono text-xs font-semibold" style={{color:'#c8d8ee'}}>{srv.name}</span>
                  <span className={`w-2 h-2 rounded-full ${srv.status==='online'?'bg-green-400':'bg-red-400'}`}/>
                </div>
                <div className="space-y-1.5">
                  <div className="flex justify-between items-center">
                    <span className="font-mono text-[10px]" style={{color:'#8899bb'}}>CPU</span>
                    <span className="font-mono text-[10px]" style={{color:srv.cpu>70?'#ff3366':'#00ff88'}}>{srv.cpu.toFixed(1)}%</span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="font-mono text-[10px]" style={{color:'#8899bb'}}>RAM</span>
                    <span className="font-mono text-[10px]" style={{color:srv.ram>80?'#ff3366':'#00ff88'}}>{srv.ram.toFixed(1)}%</span>
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
