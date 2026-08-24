import { useEffect, useMemo, useState } from 'react'
import GlassCard from '../components/GlassCard'
import { listAlerts, type AlertRecord } from '../lib/api'

const tactics = [
  {
    id: 'recon', name: 'Reconnaissance', color: '#7c3aed',
    techniques: [
      { id: 'T1595', name: 'Active Scanning', detected: true, ts: '23:41' },
      { id: 'T1592', name: 'Gather Victim Host Info', detected: true, ts: '23:42' },
    ]
  },
  {
    id: 'resource', name: 'Resource Development', color: '#8b5cf6',
    techniques: [
      { id: 'T1584', name: 'Compromise Infrastructure', detected: false, ts: null },
    ]
  },
  {
    id: 'initial', name: 'Initial Access', color: '#ff3366',
    techniques: [
      { id: 'T1190', name: 'Exploit Public App', detected: true, ts: '23:55' },
      { id: 'T1133', name: 'External Remote Svc', detected: false, ts: null },
    ]
  },
  {
    id: 'exec', name: 'Execution', color: '#ff6644',
    techniques: [
      { id: 'T1059', name: 'Command & Scripting', detected: true, ts: '00:02' },
      { id: 'T1203', name: 'Exploit for Exec', detected: false, ts: null },
    ]
  },
  {
    id: 'persist', name: 'Persistence', color: '#ffaa00',
    techniques: [
      { id: 'T1547', name: 'Boot Autostart Exec', detected: false, ts: null },
      { id: 'T1136', name: 'Create Account', detected: false, ts: null },
    ]
  },
  {
    id: 'privesc', name: 'Privilege Escalation', color: '#f59e0b',
    techniques: [
      { id: 'T1548', name: 'Abuse Elevation Control', detected: false, ts: null },
    ]
  },
  {
    id: 'defense', name: 'Defense Evasion', color: '#00d4ff',
    techniques: [
      { id: 'T1562', name: 'Impair Defenses', detected: false, ts: null },
      { id: 'T1036', name: 'Masquerading', detected: false, ts: null },
    ]
  },
  {
    id: 'lateral', name: 'Lateral Movement', color: '#00ff88',
    techniques: [
      { id: 'T1021', name: 'Remote Services', detected: false, ts: null },
    ]
  },
  {
    id: 'exfil', name: 'Exfiltration', color: '#ef4444',
    techniques: [
      { id: 'T1041', name: 'Exfil Over C2', detected: false, ts: null },
    ]
  },
]

export default function AttackPath() {
  const [hoveredTactic, setHoveredTactic] = useState<string | null>(null)
  const [alerts, setAlerts] = useState<AlertRecord[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let ignore = false
    async function load() {
      try {
        const data = await listAlerts()
        if (!ignore) setAlerts(data)
      } catch (err) {
        if (!ignore) setError(err instanceof Error ? err.message : 'Unable to load attack path data')
      }
    }
    void load()
    return () => { ignore = true }
  }, [])

  const attackFlow = useMemo(() => alerts.slice(0, 5).map((alert, index) => ({
    id: index + 1,
    src: index === 0 ? 'External IP' : 'Internal Host',
    dst: index < 2 ? 'Web API :443' : 'SRV-DB-01',
    action: alert.title,
    ts: new Date(alert.created_at).toLocaleTimeString('en-IN', { timeZone: 'Asia/Kolkata', hour12: false }),
    blocked: alert.status === 'resolved',
  })), [alerts])

  const detectedCount = tactics.reduce((a, t) => a + t.techniques.filter(x => x.detected).length, 0)
  const totalCount = tactics.reduce((a, t) => a + t.techniques.length, 0)

  return (
    <div className="p-4 md:p-6 space-y-4 md:space-y-5">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <div className="flex-1 min-w-0">
          <h1 className="font-display font-bold text-xl sm:text-2xl tracking-widest neon-cyan">ATTACK PATH VISUALIZATION</h1>
          <p className="font-mono text-xs mt-0.5" style={{ color: 'var(--t-muted, #8899bb)' }}>MITRE ATT&CK Framework Mapping · INC-2847</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <div className="glass-bright rounded px-3 py-1.5 font-mono text-xs min-h-[44px] flex items-center" style={{ color: '#ff3366', border: '1px solid rgba(255,51,102,0.3)' }}>
            {detectedCount} / {totalCount} TECHNIQUES OBSERVED
          </div>
        </div>
      </div>

      {error ? <div className="font-mono text-xs" style={{ color: '#ff3366' }}>{error}</div> : null}

      {/* MITRE matrix */}
      <GlassCard className="p-4 md:p-5">
        <div className="font-display font-bold text-sm tracking-wider neon-cyan mb-4">MITRE ATT&CK MATRIX</div>
        <div className="overflow-x-auto pb-2">
          <div className="flex gap-2" style={{ minWidth: 700 }}>
            {tactics.map(tactic => (
              <div key={tactic.id}
                onMouseEnter={() => setHoveredTactic(tactic.id)}
                onMouseLeave={() => setHoveredTactic(null)}
                className="rounded-lg overflow-hidden transition-all flex-1"
                style={{ border: `1px solid ${tactic.color}30`, background: hoveredTactic === tactic.id ? `${tactic.color}10` : 'rgba(0,0,0,0.2)', minWidth: 75 }}>
                <div className="px-2 py-1.5 text-center font-mono text-xs font-semibold"
                  style={{ background: `${tactic.color}20`, color: tactic.color, fontSize: 10, lineHeight: 1.3 }}>
                  {tactic.name}
                </div>
                <div className="p-1.5 space-y-1">
                  {tactic.techniques.map(tech => (
                    <div key={tech.id}
                      className="rounded px-1.5 py-1 text-center transition-all"
                      style={{
                        background: tech.detected ? `${tactic.color}25` : 'rgba(255,255,255,0.03)',
                        border: `1px solid ${tech.detected ? tactic.color : 'var(--t-border-light, rgba(255,255,255,0.06))'}60`,
                      }}>
                      <div className="font-mono font-semibold" style={{ fontSize: 10, color: tech.detected ? tactic.color : 'var(--t-muted, #8899bb)' }}>{tech.id}</div>
                      <div className="font-mono leading-tight" style={{ fontSize: 9, color: tech.detected ? 'var(--t-text, #c8d8ee)' : 'var(--t-muted, #556677)', marginTop: 2 }}>{tech.name}</div>
                      {tech.detected && (
                        <div className="font-mono mt-1" style={{ fontSize: 9, color: tactic.color }}>{tech.ts}</div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
        <div className="flex flex-wrap gap-4 mt-3">
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 rounded" style={{ background: 'rgba(255,51,102,0.3)', border: '1px solid #ff3366' }} />
            <span className="font-mono text-xs" style={{ color: 'var(--t-muted, #8899bb)' }}>Detected/Active</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 rounded" style={{ background: 'var(--t-border-light, rgba(255,255,255,0.04))', border: '1px solid rgba(255,255,255,0.1)' }} />
            <span className="font-mono text-xs" style={{ color: 'var(--t-muted, #8899bb)' }}>Not observed</span>
          </div>
        </div>
      </GlassCard>

      {/* Attack flow diagram */}
      <GlassCard className="p-4 md:p-5">
        <div className="font-display font-bold text-sm tracking-wider neon-cyan mb-4">INTERACTIVE ATTACK FLOW — INC-2847 · DDoS + SQL Injection</div>
        <div className="flex items-center gap-0 overflow-x-auto pb-2">
          {attackFlow.map((step, i) => (
            <div key={step.id} className="flex items-center shrink-0">
              <div className="flex flex-col items-center" style={{ minWidth: 160 }}>
                <div className="font-mono text-xs mb-2" style={{ color: 'var(--t-muted, #8899bb)' }}>{step.ts}</div>
                <div className="rounded-xl p-3 w-36 text-center transition-all hover:scale-105"
                  style={{
                    background: step.blocked ? 'rgba(0,255,136,0.08)' : 'rgba(255,51,102,0.08)',
                    border: `1px solid ${step.blocked ? 'rgba(0,255,136,0.35)' : 'rgba(255,51,102,0.35)'}`,
                  }}>
                  <div className="font-mono text-xs font-semibold" style={{ color: step.blocked ? '#00ff88' : '#ff3366' }}>
                    {step.blocked ? '🛡 BLOCKED' : '⚠ DETECTED'}
                  </div>
                  <div className="font-mono text-xs mt-1 font-semibold" style={{ color: 'var(--t-text, #c8d8ee)' }}>{step.action}</div>
                  <div className="mt-2">
                    <div className="font-mono" style={{ fontSize: 9, color: 'var(--t-muted, #8899bb)' }}>{step.src}</div>
                    <div className="font-mono" style={{ fontSize: 9, color: 'var(--t-muted, #8899bb)' }}>→ {step.dst}</div>
                  </div>
                </div>
              </div>
              {i < attackFlow.length - 1 && (
                <div className="flex items-center mx-1 shrink-0">
                  <div style={{ width: 24, height: 2, background: 'rgba(255,51,102,0.5)' }} />
                  <svg width="8" height="12" viewBox="0 0 8 12">
                    <path d="M0 0 L8 6 L0 12 Z" fill="rgba(255,51,102,0.5)" />
                  </svg>
                </div>
              )}
            </div>
          ))}
        </div>
      </GlassCard>

      {/* Attacker info */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        <GlassCard className="p-4 col-span-1" glow="red">
          <div className="font-display font-bold text-sm tracking-wider mb-3" style={{ color: '#ff3366' }}>ATTACKER PROFILE</div>
          {[
            { l: 'Source IP', v: '192.0.2.88' },
            { l: 'ASN', v: 'AS64496 · Unknown ISP' },
            { l: 'GeoIP', v: 'Unknown / Tor Exit' },
            { l: 'First Seen', v: '2024-01-14 23:41' },
            { l: 'Threat Intel', v: 'Known Threat Actor' },
            { l: 'Confidence', v: '94%' },
          ].map(m => (
            <div key={m.l} className="flex justify-between py-1.5" style={{ borderBottom: '1px solid rgba(255,51,102,0.08)' }}>
              <span className="font-mono text-xs" style={{ color: 'var(--t-muted, #8899bb)' }}>{m.l}</span>
              <span className="font-mono text-xs" style={{ color: 'var(--t-text, #c8d8ee)' }}>{m.v}</span>
            </div>
          ))}
        </GlassCard>

        <GlassCard className="p-4 col-span-2">
          <div className="font-display font-bold text-sm tracking-wider neon-cyan mb-3">INDICATORS OF COMPROMISE (IoCs)</div>
          <div className="space-y-2">
            {[
              { type: 'IP', value: '192.0.2.88', threat: 'Attacker Source', conf: 'HIGH' },
              { type: 'IP', value: '198.51.100.99', threat: 'C2 Server', conf: 'HIGH' },
              { type: 'URL', value: '/api/v2/users?id=1 OR 1=1--', threat: 'SQL Injection Payload', conf: 'CONFIRMED' },
              { type: 'UA', value: 'python-requests/2.28.0', threat: 'Automated Scanner', conf: 'MEDIUM' },
              { type: 'HASH', value: 'b3d4e8f1a2c9...', threat: 'Dropped Malware', conf: 'MEDIUM' },
            ].map((ioc, i) => (
              <div key={i} className="flex items-center gap-3 p-2 rounded-lg"
                style={{ background: 'rgba(0,212,255,0.04)', border: '1px solid rgba(0,212,255,0.08)' }}>
                <span className="font-mono text-xs px-2 py-0.5 rounded shrink-0"
                  style={{ background: 'rgba(0,212,255,0.12)', color: '#00d4ff' }}>{ioc.type}</span>
                <span className="font-mono text-xs flex-1 truncate" style={{ color: 'var(--t-text, #c8d8ee)' }}>{ioc.value}</span>
                <span className="font-mono text-xs" style={{ color: 'var(--t-muted, #8899bb)' }}>{ioc.threat}</span>
                <span className="font-mono text-xs px-2 py-0.5 rounded shrink-0"
                  style={{ background: 'rgba(255,51,102,0.12)', color: '#ff3366', fontSize: 9 }}>{ioc.conf}</span>
              </div>
            ))}
          </div>
        </GlassCard>
      </div>
    </div>
  )
}
