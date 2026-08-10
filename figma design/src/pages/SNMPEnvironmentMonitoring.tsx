import { useCallback, useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router'
import GlassCard from '../components/GlassCard'
import SNMPMetricChart from '../components/SNMPMetricChart'
import SNMPStatusBadge from '../components/SNMPStatusBadge'
import { getSNMPEnvironmentSensors, getSNMPSystemInfo, type SNMPEnvironmentSensor, type SNMPSystemInfo } from '../lib/api'

// ── Sensor type config ─────────────────────────────────────────────────────

const SENSOR_TYPE_CONFIG: Record<
  SNMPEnvironmentSensor['sensor_type'],
  { label: string; icon: string; defaultUnit: string; color: string }
> = {
  temperature: {
    label: 'Temperature',
    icon: 'M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z',
    defaultUnit: '°C',
    color: '#ff6644',
  },
  fan: {
    label: 'Fan',
    icon: 'M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15',
    defaultUnit: 'RPM',
    color: '#00d4ff',
  },
  voltage: {
    label: 'Voltage',
    icon: 'M13 10V3L4 14h7v7l9-11h-7z',
    defaultUnit: 'V',
    color: '#ffaa00',
  },
  power: {
    label: 'Power',
    icon: 'M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2z',
    defaultUnit: 'W',
    color: '#7c3aed',
  },
  humidity: {
    label: 'Humidity',
    icon: 'M3 15a4 4 0 004 4h9a5 5 0 10-.1-9.999 5.002 5.002 0 10-9.78 2.096A4.001 4.001 0 003 15z',
    defaultUnit: '%',
    color: '#00bfff',
  },
  other: {
    label: 'Sensor',
    icon: 'M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2z',
    defaultUnit: '',
    color: '#8899bb',
  },
}

const STATUS_COLORS = {
  ok: '#00ff88',
  warning: '#ffaa00',
  critical: '#ff3366',
  unknown: '#8899bb',
}

function fmtValue(value: number | undefined, unit: string | undefined, type: SNMPEnvironmentSensor['sensor_type']): string {
  if (value === undefined || value === null) return '—'
  const u = unit || SENSOR_TYPE_CONFIG[type].defaultUnit
  return `${value.toFixed(1)}${u}`
}

// ── Sensor Detail Modal ───────────────────────────────────────────────────────

function SensorDetail({ sensor, onClose }: { sensor: SNMPEnvironmentSensor; onClose: () => void }) {
  const cfg = SENSOR_TYPE_CONFIG[sensor.sensor_type]
  const statusColor = STATUS_COLORS[sensor.status]
  const unit = sensor.unit || cfg.defaultUnit

  const chartData = sensor.history.map(p => ({ timestamp: p.timestamp, value: p.value }))

  return (
    <div
      className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-4"
      style={{ background: 'rgba(0,0,0,0.7)', backdropFilter: 'blur(4px)' }}
      onClick={e => { if (e.target === e.currentTarget) onClose() }}
    >
      <div
        className="w-full max-w-2xl max-h-[90vh] overflow-y-auto rounded-xl space-y-4"
        style={{ background: 'rgba(8,25,55,0.98)', border: '1px solid rgba(0,212,255,0.2)' }}
      >
        {/* Header */}
        <div className="flex items-start justify-between p-5" style={{ borderBottom: '1px solid rgba(0,212,255,0.1)' }}>
          <div>
            <div className="flex items-center gap-3 mb-1">
              <div
                className="w-8 h-8 rounded-lg flex items-center justify-center"
                style={{ background: `${cfg.color}18`, border: `1px solid ${cfg.color}40` }}
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={cfg.color} strokeWidth="1.8">
                  <path d={cfg.icon} />
                </svg>
              </div>
              <div>
                <h2 className="font-display font-bold text-lg neon-cyan">{sensor.sensor_name}</h2>
                <div className="font-mono text-xs" style={{ color: '#8899bb' }}>{cfg.label}</div>
              </div>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-lg transition-all hover:bg-white/5"
            style={{ color: '#8899bb' }}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M18 6L6 18M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="px-5 pb-5 space-y-4">
          {/* Current value */}
          <div className="flex items-center justify-between">
            <div>
              <div className="font-mono text-[10px] mb-1" style={{ color: '#667799' }}>CURRENT VALUE</div>
              <div className="font-display font-bold text-4xl" style={{ color: cfg.color }}>
                {fmtValue(sensor.current_value, sensor.unit, sensor.sensor_type)}
              </div>
            </div>
            <div className="text-right space-y-2">
              <SNMPStatusBadge status={sensor.status} />
              {sensor.threshold_warning !== undefined && (
                <div className="font-mono text-xs" style={{ color: '#ffaa00' }}>
                  Warn: {sensor.threshold_warning}{unit}
                </div>
              )}
              {sensor.threshold_critical !== undefined && (
                <div className="font-mono text-xs" style={{ color: '#ff3366' }}>
                  Crit: {sensor.threshold_critical}{unit}
                </div>
              )}
            </div>
          </div>

          {/* Threshold indicator bar (for temperature/voltage/power/humidity) */}
          {sensor.current_value !== undefined && sensor.threshold_critical !== undefined && (
            <div>
              <div className="flex justify-between mb-1">
                <span className="font-mono text-[9px]" style={{ color: '#556677' }}>0{unit}</span>
                <span className="font-mono text-[9px]" style={{ color: '#556677' }}>
                  Critical: {sensor.threshold_critical}{unit}
                </span>
              </div>
              <div className="h-2 rounded-full overflow-hidden" style={{ background: 'rgba(0,0,0,0.3)' }}>
                <div
                  className="h-full rounded-full transition-all"
                  style={{
                    width: `${Math.min((sensor.current_value / sensor.threshold_critical) * 100, 100)}%`,
                    background: statusColor,
                  }}
                />
              </div>
            </div>
          )}

          {/* Historical chart */}
          <div>
            <div className="font-display font-bold text-sm neon-cyan mb-3">HISTORICAL TREND</div>
            <SNMPMetricChart
              data={chartData}
              height={150}
              color={cfg.color}
              unit={unit}
              label={cfg.label}
              showArea
              showGrid
              showAxes
              noDataMessage="No Historical Data Yet"
            />
          </div>

          <div className="font-mono text-xs" style={{ color: '#556677' }}>
            Last updated: {new Date(sensor.last_updated).toLocaleString()}
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Sensor Card ───────────────────────────────────────────────────────────────

function SensorCard({ sensor, onClick }: { sensor: SNMPEnvironmentSensor; onClick: () => void }) {
  const cfg = SENSOR_TYPE_CONFIG[sensor.sensor_type]
  const statusColor = STATUS_COLORS[sensor.status]
  const unit = sensor.unit || cfg.defaultUnit

  // Mini sparkline: last 8 history points
  const miniHistory = sensor.history.slice(-8)

  return (
    <GlassCard
      className="p-4 cursor-pointer transition-all hover:bg-cyan-400/5"
      onClick={onClick}
      role="button"
      tabIndex={0}
      onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onClick() } }}
    >
      {/* Header */}
      <div className="flex items-start gap-3 mb-3">
        <div
          className="w-9 h-9 rounded-lg flex items-center justify-center shrink-0"
          style={{ background: `${cfg.color}18`, border: `1px solid ${cfg.color}40` }}
        >
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke={cfg.color} strokeWidth="1.8">
            <path d={cfg.icon} />
          </svg>
        </div>
        <div className="flex-1 min-w-0">
          <div className="font-mono text-xs font-bold truncate" style={{ color: '#c8d8ee' }}>
            {sensor.sensor_name}
          </div>
          <div className="font-mono text-[10px]" style={{ color: '#667799' }}>{cfg.label}</div>
        </div>
        {/* Status dot */}
        <div
          className="w-2.5 h-2.5 rounded-full shrink-0 mt-1"
          style={{ background: statusColor, boxShadow: `0 0 6px ${statusColor}` }}
          title={`Status: ${sensor.status}`}
        />
      </div>

      {/* Current Value */}
      <div className="mb-3">
        <div className="font-display font-bold text-2xl" style={{ color: cfg.color }}>
          {fmtValue(sensor.current_value, sensor.unit, sensor.sensor_type)}
        </div>
        <SNMPStatusBadge status={sensor.status} size="xs" />
      </div>

      {/* Thresholds */}
      {(sensor.threshold_warning !== undefined || sensor.threshold_critical !== undefined) && (
        <div className="flex gap-4 mb-3">
          {sensor.threshold_warning !== undefined && (
            <div>
              <div className="font-mono text-[9px]" style={{ color: '#556677' }}>Warn</div>
              <div className="font-mono text-xs" style={{ color: '#ffaa00' }}>
                {sensor.threshold_warning}{unit}
              </div>
            </div>
          )}
          {sensor.threshold_critical !== undefined && (
            <div>
              <div className="font-mono text-[9px]" style={{ color: '#556677' }}>Crit</div>
              <div className="font-mono text-xs" style={{ color: '#ff3366' }}>
                {sensor.threshold_critical}{unit}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Mini sparkline */}
      {miniHistory.length >= 2 && (
        <SNMPMetricChart
          data={miniHistory.map(p => ({ timestamp: p.timestamp, value: p.value }))}
          height={40}
          color={cfg.color}
          showArea={false}
          showGrid={false}
          showAxes={false}
          noDataMessage=""
        />
      )}

      {/* Footer */}
      <div
        className="flex items-center justify-between mt-3 pt-2"
        style={{ borderTop: '1px solid rgba(0,212,255,0.06)' }}
      >
        <span className="font-mono text-[9px]" style={{ color: '#445566' }}>
          {new Date(sensor.last_updated).toLocaleTimeString()}
        </span>
        <span className="font-mono text-[10px] flex items-center gap-1" style={{ color: '#00d4ff' }}>
          History
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M5 12h14M12 5l7 7-7 7" />
          </svg>
        </span>
      </div>
    </GlassCard>
  )
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function SNMPEnvironmentMonitoring() {
  const { deviceId } = useParams<{ deviceId: string }>()
  const navigate = useNavigate()
  const id = Number(deviceId)

  const [sensors, setSensors] = useState<SNMPEnvironmentSensor[]>([])
  const [sysInfo, setSysInfo] = useState<SNMPSystemInfo | null>(null)
  const [selected, setSelected] = useState<SNMPEnvironmentSensor | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [typeFilter, setTypeFilter] = useState<SNMPEnvironmentSensor['sensor_type'] | 'all'>('all')

  const load = useCallback(async () => {
    if (!id) return
    setLoading(true)
    setError(null)
    try {
      const [envData, sysData] = await Promise.all([
        getSNMPEnvironmentSensors(id),
        getSNMPSystemInfo(id),
      ])
      setSensors(envData)
      setSysInfo(sysData)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load environment data')
    } finally {
      setLoading(false)
    }
  }, [id])

  useEffect(() => { void load() }, [load])
  useEffect(() => {
    const t = setInterval(() => void load(), 60_000)
    return () => clearInterval(t)
  }, [load])

  // Discover which sensor types actually exist in the data
  const presentTypes = Array.from(new Set(sensors.map(s => s.sensor_type)))
  const filtered = typeFilter === 'all' ? sensors : sensors.filter(s => s.sensor_type === typeFilter)

  const criticalCount = sensors.filter(s => s.status === 'critical').length
  const warningCount = sensors.filter(s => s.status === 'warning').length

  // Group by type for the summary section
  const sensorGroups = presentTypes.reduce<Record<string, SNMPEnvironmentSensor[]>>((acc, type) => {
    acc[type] = sensors.filter(s => s.sensor_type === type)
    return acc
  }, {})

  return (
    <div className="p-4 md:p-6 space-y-4 md:space-y-5">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 font-mono text-xs" style={{ color: '#667799' }}>
        <button onClick={() => navigate(`/snmp/dashboard/${id}`)} className="hover:text-cyan-400 transition-colors">
          SNMP
        </button>
        <span>/</span>
        <span style={{ color: '#c8d8ee' }}>Environment</span>
      </div>

      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <div>
          <h1 className="font-display font-bold text-xl sm:text-2xl tracking-widest neon-cyan">
            ENVIRONMENT MONITORING
          </h1>
          <p className="font-mono text-xs mt-0.5" style={{ color: '#8899bb' }}>
            {sysInfo?.hostname || `Device ${id}`} · {sensors.length} sensor{sensors.length !== 1 ? 's' : ''} · auto-refresh 60s
          </p>
        </div>
        <button
          onClick={() => void load()}
          className="glass-bright px-3 py-1.5 rounded font-mono text-xs transition-all hover:bg-cyan-400/10 flex items-center gap-1.5"
          style={{ border: '1px solid rgba(0,212,255,0.25)', color: '#00d4ff' }}
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M23 4v6h-6M1 20v-6h6" />
            <path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15" />
          </svg>
          REFRESH
        </button>
      </div>

      {error && (
        <div className="font-mono text-xs p-4 rounded" style={{ color: '#ff3366', background: 'rgba(255,51,102,0.1)', border: '1px solid rgba(255,51,102,0.3)' }}>
          {error}
        </div>
      )}

      {loading && (
        <div className="flex items-center justify-center p-12">
          <span className="font-mono text-sm" style={{ color: '#00d4ff' }}>Loading sensor data...</span>
        </div>
      )}

      {!loading && sensors.length === 0 && (
        <GlassCard className="p-8 text-center space-y-3">
          <div className="font-display font-bold text-lg" style={{ color: '#8899bb' }}>
            Environment Monitoring Not Supported
          </div>
          <div className="font-mono text-sm" style={{ color: '#667799' }}>
            No Data Available From Device
          </div>
          <button
            onClick={() => navigate(`/snmp/dashboard/${id}`)}
            className="mt-4 px-4 py-2 rounded font-mono text-xs"
            style={{ background: 'rgba(0,212,255,0.1)', color: '#00d4ff', border: '1px solid rgba(0,212,255,0.3)' }}
          >
            Back to Dashboard
          </button>
        </GlassCard>
      )}

      {!loading && sensors.length > 0 && (
        <>
          {/* Summary tiles */}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
            <GlassCard className="p-4 text-center">
              <div className="font-display font-bold text-2xl" style={{ color: '#00d4ff' }}>{sensors.length}</div>
              <div className="font-mono text-xs mt-1" style={{ color: '#8899bb' }}>Total Sensors</div>
            </GlassCard>
            <GlassCard className="p-4 text-center">
              <div className="font-display font-bold text-2xl" style={{ color: '#00ff88' }}>
                {sensors.filter(s => s.status === 'ok').length}
              </div>
              <div className="font-mono text-xs mt-1" style={{ color: '#8899bb' }}>OK</div>
            </GlassCard>
            <GlassCard className="p-4 text-center">
              <div className="font-display font-bold text-2xl" style={{ color: warningCount > 0 ? '#ffaa00' : '#8899bb' }}>
                {warningCount}
              </div>
              <div className="font-mono text-xs mt-1" style={{ color: '#8899bb' }}>Warning</div>
            </GlassCard>
            <GlassCard className="p-4 text-center">
              <div className="font-display font-bold text-2xl" style={{ color: criticalCount > 0 ? '#ff3366' : '#8899bb' }}>
                {criticalCount}
              </div>
              <div className="font-mono text-xs mt-1" style={{ color: '#8899bb' }}>Critical</div>
            </GlassCard>
            <GlassCard className="p-4 text-center">
              <div className="font-display font-bold text-2xl" style={{ color: '#7c3aed' }}>
                {presentTypes.length}
              </div>
              <div className="font-mono text-xs mt-1" style={{ color: '#8899bb' }}>Sensor Types</div>
            </GlassCard>
          </div>

          {/* Sensor type filter — only show types that exist */}
          {presentTypes.length > 1 && (
            <div className="flex flex-wrap gap-2">
              <button
                onClick={() => setTypeFilter('all')}
                className="font-mono text-xs px-3 py-1.5 rounded transition-all"
                style={{
                  background: typeFilter === 'all' ? 'rgba(0,212,255,0.15)' : 'transparent',
                  color: typeFilter === 'all' ? '#00d4ff' : '#8899bb',
                  border: `1px solid ${typeFilter === 'all' ? 'rgba(0,212,255,0.4)' : 'rgba(0,212,255,0.1)'}`,
                }}
              >
                All
              </button>
              {presentTypes.map(type => {
                const cfg = SENSOR_TYPE_CONFIG[type]
                return (
                  <button
                    key={type}
                    onClick={() => setTypeFilter(type)}
                    className="font-mono text-xs px-3 py-1.5 rounded transition-all"
                    style={{
                      background: typeFilter === type ? `${cfg.color}20` : 'transparent',
                      color: typeFilter === type ? cfg.color : '#8899bb',
                      border: `1px solid ${typeFilter === type ? `${cfg.color}50` : 'rgba(0,212,255,0.1)'}`,
                    }}
                  >
                    {cfg.label} ({sensorGroups[type]?.length ?? 0})
                  </button>
                )
              })}
            </div>
          )}

          {/* Sensor Cards — grouped if showing all */}
          {typeFilter === 'all' ? (
            presentTypes.map(type => {
              const group = sensorGroups[type] ?? []
              const cfg = SENSOR_TYPE_CONFIG[type]
              return (
                <div key={type}>
                  <div className="flex items-center gap-2 mb-3">
                    <div
                      className="w-6 h-6 rounded flex items-center justify-center"
                      style={{ background: `${cfg.color}18` }}
                    >
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke={cfg.color} strokeWidth="1.8">
                        <path d={cfg.icon} />
                      </svg>
                    </div>
                    <span className="font-display font-bold text-sm tracking-wider" style={{ color: cfg.color }}>
                      {cfg.label.toUpperCase()} ({group.length})
                    </span>
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4 mb-6">
                    {group.map(s => (
                      <SensorCard key={s.id} sensor={s} onClick={() => setSelected(s)} />
                    ))}
                  </div>
                </div>
              )
            })
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
              {filtered.map(s => (
                <SensorCard key={s.id} sensor={s} onClick={() => setSelected(s)} />
              ))}
            </div>
          )}
        </>
      )}

      {/* Sensor Detail Modal */}
      {selected && <SensorDetail sensor={selected} onClose={() => setSelected(null)} />}
    </div>
  )
}
