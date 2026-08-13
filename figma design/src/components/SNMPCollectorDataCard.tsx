import GlassCard from './GlassCard'
import { formatBytes, formatSpeed, getModuleConfig } from '../modules/snmpModuleRegistry'

function titleize(text: string): string {
  return text.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

function formatValue(value: any): string {
  if (value === null || value === undefined || value === '') return '-'
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  if (typeof value === 'number') return Number.isInteger(value) ? String(value) : value.toFixed(2)
  if (typeof value === 'string') return value
  if (typeof value === 'object' && value.display) return String(value.display)
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

function formatMetricValue(key: string, value: any): string {
  if (value === null || value === undefined) return '-'
  if (key.includes('bytes') || key.includes('octets')) return formatBytes(Number(value))
  if (key.includes('speed_bps')) return formatSpeed(Number(value))
  if (key.includes('percent')) return `${Number(value).toFixed(1)}%`
  if (key.includes('timestamp') || key.includes('polled_at') || key.includes('last_poll')) {
    const date = new Date(value)
    return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString()
  }
  return formatValue(value)
}

function findRows(data: any): any[] {
  if (!data) return []
  if (Array.isArray(data)) return data
  for (const value of Object.values(data)) {
    if (Array.isArray(value)) return value
  }
  return []
}

function getSummaryItems(data: any): Array<[string, any]> {
  if (!data || typeof data !== 'object' || Array.isArray(data)) return []
  return Object.entries(data)
    .filter(([, value]) => !Array.isArray(value))
    .slice(0, 12)
}

function isEmptyValue(value: any): boolean {
  if (value === null || value === undefined || value === '') return true
  if (Array.isArray(value)) return value.length === 0
  if (typeof value === 'object') return Object.keys(value).length === 0
  return false
}

export default function SNMPCollectorDataCard({ name, collector }: { name: string; collector: any }) {
  const config = getModuleConfig(name)
  const color = collector?.supported ? (config?.color || '#00d4ff') : '#ff3366'
  const rows = findRows(collector?.data)
  const summary = getSummaryItems(collector?.data).filter(([, value]) => !isEmptyValue(value))
  const columns = rows.length > 0
    ? Array.from(new Set(rows.flatMap(row => Object.keys(row || {})))).slice(0, 12)
    : []

  return (
    <GlassCard className="overflow-hidden">
      <div className="p-4" style={{ borderBottom: `1px solid ${color}33` }}>
        <div className="flex flex-wrap items-center gap-2">
          <div className="font-display font-bold text-sm tracking-wider" style={{ color }}>
            {titleize(config?.label || name)}
          </div>
          <span className="font-mono text-[10px] px-1.5 py-0.5 rounded"
            style={{ background: collector?.supported ? 'rgba(0,255,136,0.12)' : 'rgba(255,51,102,0.12)', color }}>
            {collector?.supported ? 'SUPPORTED' : 'NOT SUPPORTED'}
          </span>
          {collector?.timestamp && <span className="font-mono text-[10px] ml-auto" style={{ color: '#667799' }}>{new Date(collector.timestamp).toLocaleString()}</span>}
        </div>
        {!collector?.supported && collector?.reason && (
          <div className="font-mono text-xs mt-2" style={{ color: '#ffaa00' }}>{collector.reason}</div>
        )}
      </div>

      {collector?.supported ? (
        <>
          {summary.length > 0 && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2 p-4">
              {summary.map(([key, value]) => (
                <div key={key} className="p-2 rounded" style={{ background: 'rgba(8,25,55,0.45)', border: '1px solid rgba(0,212,255,0.08)' }}>
                  <div className="font-mono text-[10px]" style={{ color: '#667799' }}>{titleize(key)}</div>
                  <div className="font-mono text-xs mt-1 break-words" style={{ color: '#c8d8ee' }}>{formatMetricValue(key, value)}</div>
                </div>
              ))}
            </div>
          )}
          {rows.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full" style={{ minWidth: 900 }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid rgba(0,212,255,0.08)' }}>
                    {columns.map(col => (
                      <th key={col} className="text-left px-4 py-2 font-mono text-xs"
                        style={{ color: '#8899bb', background: 'rgba(8,25,55,0.95)' }}>{titleize(col)}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row, index) => (
                    <tr key={index} style={{ borderBottom: '1px solid rgba(0,212,255,0.04)' }}>
                      {columns.map(col => (
                        <td key={col} className="px-4 py-2 font-mono text-[10px] max-w-[260px] truncate" style={{ color: '#c8d8ee' }}>
                          {formatMetricValue(col, row?.[col])}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {summary.length === 0 && rows.length === 0 ? (
            <div className="font-mono text-xs p-6 text-center" style={{ color: '#8899bb' }}>
              Supported, but no rows stored yet.
            </div>
          ) : (
            <details className="mx-4 mb-4 rounded" style={{ border: '1px solid rgba(0,212,255,0.1)', background: 'rgba(8,25,55,0.25)' }}>
              <summary className="font-mono text-[10px] px-3 py-2 cursor-pointer" style={{ color: '#00d4ff' }}>
                RAW DATA
              </summary>
              <pre className="font-mono text-[10px] p-3 overflow-x-auto max-h-80" style={{ color: '#8899bb' }}>
                {JSON.stringify(collector.data ?? {}, null, 2)}
              </pre>
            </details>
          )}
        </>
      ) : (
        <div className="p-4">
          {collector?.missing?.length > 0 && (
            <div className="font-mono text-[10px]" style={{ color: '#8899bb' }}>
              Missing: {collector.missing.join(', ')}
            </div>
          )}
        </div>
      )}
    </GlassCard>
  )
}
