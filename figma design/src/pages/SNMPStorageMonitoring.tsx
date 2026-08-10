import { useCallback, useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router'
import GlassCard from '../components/GlassCard'
import SNMPStatusBadge from '../components/SNMPStatusBadge'
import { getSNMPStorageVolumes, getSNMPSystemInfo, type SNMPStorageVolume, type SNMPSystemInfo } from '../lib/api'

function fmtBytes(bytes: number | undefined): string {
  if (bytes === undefined || bytes === null || bytes === 0) return '—'
  const abs = Math.abs(bytes)
  if (abs >= 1_099_511_627_776) return `${(bytes / 1_099_511_627_776).toFixed(2)} TB`
  if (abs >= 1_073_741_824) return `${(bytes / 1_073_741_824).toFixed(2)} GB`
  if (abs >= 1_048_576) return `${(bytes / 1_048_576).toFixed(1)} MB`
  if (abs >= 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${bytes} B`
}

function healthColor(h: 'healthy' | 'warning' | 'critical'): string {
  return h === 'healthy' ? '#00ff88' : h === 'warning' ? '#ffaa00' : '#ff3366'
}

function utilizColor(pct: number): string {
  if (pct >= 90) return '#ff3366'
  if (pct >= 75) return '#ffaa00'
  return '#00d4ff'
}

function VolumeCard({ vol }: { vol: SNMPStorageVolume }) {
  const pct = vol.utilization_percent
  const uColor = utilizColor(pct)
  const hColor = healthColor(vol.health)

  return (
    <GlassCard className="p-4 space-y-3">
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#00d4ff" strokeWidth="1.8">
              <path d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4" />
            </svg>
            <span className="font-mono text-sm font-bold truncate" style={{ color: '#c8d8ee' }}>
              {vol.mount_name}
            </span>
          </div>
          {vol.type && (
            <div className="font-mono text-[10px]" style={{ color: '#667799' }}>{vol.type}</div>
          )}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <div className="w-2 h-2 rounded-full"
            style={{ background: hColor, boxShadow: `0 0 6px ${hColor}` }}
            title={`Health: ${vol.health}`} />
          <SNMPStatusBadge status={vol.health} size="xs" />
        </div>
      </div>

      {/* Utilization Bar */}
      <div>
        <div className="flex justify-between mb-1.5">
          <span className="font-mono text-[10px]" style={{ color: '#667799' }}>
            Used {fmtBytes(vol.used_bytes)} of {fmtBytes(vol.total_bytes)}
          </span>
          <span className="font-mono text-[10px] font-bold" style={{ color: uColor }}>
            {pct.toFixed(1)}%
          </span>
        </div>
        <div className="h-3 rounded-full overflow-hidden" style={{ background: 'rgba(0,0,0,0.3)' }}>
          <div
            className="h-full rounded-full transition-all"
            style={{
              width: `${Math.min(pct, 100)}%`,
              background: `linear-gradient(90deg, ${uColor}99, ${uColor})`,
            }}
          />
        </div>
      </div>

      {/* Metrics Grid */}
      <div className="grid grid-cols-2 gap-3">
        {[
          { l: 'Total', v: fmtBytes(vol.total_bytes), c: '#8899bb' },
          { l: 'Used', v: fmtBytes(vol.used_bytes), c: uColor },
          { l: 'Free', v: fmtBytes(vol.free_bytes), c: '#00ff88' },
          { l: 'Utilization', v: `${pct.toFixed(1)}%`, c: uColor },
        ].map(m => (
          <div key={m.l}>
            <div className="font-mono text-[9px] mb-0.5" style={{ color: '#556677' }}>{m.l}</div>
            <div className="font-mono text-xs font-semibold" style={{ color: m.c }}>{m.v}</div>
          </div>
        ))}
      </div>

      {/* Last Updated */}
      <div className="font-mono text-[9px] pt-1" style={{ color: '#445566', borderTop: '1px solid rgba(0,212,255,0.06)' }}>
        Updated: {new Date(vol.last_updated).toLocaleString()}
      </div>
    </GlassCard>
  )
}

export default function SNMPStorageMonitoring() {
  const { deviceId } = useParams<{ deviceId: string }>()
  const navigate = useNavigate()
  const id = Number(deviceId)

  const [volumes, setVolumes] = useState<SNMPStorageVolume[]>([])
  const [sysInfo, setSysInfo] = useState<SNMPSystemInfo | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    if (!id) return
    setLoading(true)
    setError(null)
    try {
      const [volData, sysData] = await Promise.all([
        getSNMPStorageVolumes(id),
        getSNMPSystemInfo(id),
      ])
      setVolumes(volData)
      setSysInfo(sysData)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load storage data')
    } finally {
      setLoading(false)
    }
  }, [id])

  useEffect(() => { void load() }, [load])
  useEffect(() => {
    const t = setInterval(() => void load(), 60_000)
    return () => clearInterval(t)
  }, [load])

  // Aggregates
  const totalBytes = volumes.reduce((a, v) => a + v.total_bytes, 0)
  const usedBytes = volumes.reduce((a, v) => a + v.used_bytes, 0)
  const freeBytes = volumes.reduce((a, v) => a + v.free_bytes, 0)
  const overallPct = totalBytes > 0 ? (usedBytes / totalBytes) * 100 : 0
  const criticalVols = volumes.filter(v => v.health === 'critical').length
  const warningVols = volumes.filter(v => v.health === 'warning').length

  return (
    <div className="p-4 md:p-6 space-y-4 md:space-y-5">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 font-mono text-xs" style={{ color: '#667799' }}>
        <button onClick={() => navigate(`/snmp/dashboard/${id}`)} className="hover:text-cyan-400 transition-colors">
          SNMP
        </button>
        <span>/</span>
        <span style={{ color: '#c8d8ee' }}>Storage</span>
      </div>

      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <div>
          <h1 className="font-display font-bold text-xl sm:text-2xl tracking-widest neon-cyan">
            STORAGE MONITORING
          </h1>
          <p className="font-mono text-xs mt-0.5" style={{ color: '#8899bb' }}>
            {sysInfo?.hostname || `Device ${id}`} · {volumes.length} volume{volumes.length !== 1 ? 's' : ''} · auto-refresh 60s
          </p>
        </div>
        <button onClick={() => void load()}
          className="glass-bright px-3 py-1.5 rounded font-mono text-xs transition-all hover:bg-cyan-400/10 flex items-center gap-1.5"
          style={{ border: '1px solid rgba(0,212,255,0.25)', color: '#00d4ff' }}>
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M23 4v6h-6M1 20v-6h6" /><path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15" />
          </svg>
          REFRESH
        </button>
      </div>

      {error && (
        <div className="font-mono text-xs p-4 rounded"
          style={{ color: '#ff3366', background: 'rgba(255,51,102,0.1)', border: '1px solid rgba(255,51,102,0.3)' }}>
          {error}
        </div>
      )}

      {loading && (
        <div className="flex items-center justify-center p-12">
          <span className="font-mono text-sm" style={{ color: '#00d4ff' }}>Loading storage data...</span>
        </div>
      )}

      {!loading && volumes.length === 0 && (
        <GlassCard className="p-8 text-center space-y-3">
          <div className="font-display font-bold text-lg" style={{ color: '#8899bb' }}>
            Storage Monitoring Not Supported
          </div>
          <div className="font-mono text-sm" style={{ color: '#667799' }}>
            No Data Available From Device
          </div>
          <button onClick={() => navigate(`/snmp/dashboard/${id}`)}
            className="mt-4 px-4 py-2 rounded font-mono text-xs"
            style={{ background: 'rgba(0,212,255,0.1)', color: '#00d4ff', border: '1px solid rgba(0,212,255,0.3)' }}>
            Back to Dashboard
          </button>
        </GlassCard>
      )}

      {!loading && volumes.length > 0 && (
        <>
          {/* Summary Tiles */}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
            {[
              { l: 'Volumes', v: volumes.length, c: '#00d4ff' },
              { l: 'Total', v: fmtBytes(totalBytes), c: '#8899bb' },
              { l: 'Used', v: fmtBytes(usedBytes), c: utilizColor(overallPct) },
              { l: 'Free', v: fmtBytes(freeBytes), c: '#00ff88' },
              { l: 'Critical', v: criticalVols, c: criticalVols > 0 ? '#ff3366' : '#8899bb' },
            ].map(t => (
              <GlassCard key={t.l} className="p-4 text-center">
                <div className="font-display font-bold text-xl" style={{ color: t.c }}>{t.v}</div>
                <div className="font-mono text-xs mt-1" style={{ color: '#8899bb' }}>{t.l}</div>
              </GlassCard>
            ))}
          </div>

          {/* Overall Bar */}
          <GlassCard className="p-4">
            <div className="flex items-center justify-between mb-3">
              <div className="font-display font-bold text-sm tracking-wider neon-cyan">TOTAL STORAGE UTILIZATION</div>
              <div className="flex items-center gap-3">
                {warningVols > 0 && (
                  <span className="font-mono text-xs" style={{ color: '#ffaa00' }}>
                    {warningVols} warning
                  </span>
                )}
                {criticalVols > 0 && (
                  <span className="font-mono text-xs" style={{ color: '#ff3366' }}>
                    {criticalVols} critical
                  </span>
                )}
                <span className="font-mono text-xs font-bold" style={{ color: utilizColor(overallPct) }}>
                  {overallPct.toFixed(1)}%
                </span>
              </div>
            </div>
            <div className="h-4 rounded-full overflow-hidden mb-2" style={{ background: 'rgba(0,0,0,0.3)' }}>
              <div
                className="h-full rounded-full transition-all"
                style={{
                  width: `${Math.min(overallPct, 100)}%`,
                  background: `linear-gradient(90deg, ${utilizColor(overallPct)}99, ${utilizColor(overallPct)})`,
                }}
              />
            </div>
            <div className="flex justify-between font-mono text-[10px]" style={{ color: '#667799' }}>
              <span>0</span>
              <span>{fmtBytes(usedBytes)} used of {fmtBytes(totalBytes)}</span>
              <span>{fmtBytes(totalBytes)}</span>
            </div>
          </GlassCard>

          {/* Volume Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {volumes.map(vol => (
              <VolumeCard key={vol.id} vol={vol} />
            ))}
          </div>
        </>
      )}
    </div>
  )
}
