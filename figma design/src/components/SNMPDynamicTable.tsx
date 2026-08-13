import { ReactNode, useMemo, useState } from 'react'

export interface SNMPTableColumn<T> {
  key: string
  label: string
  sortable?: boolean
  render?: (row: T) => ReactNode
  getValue?: (row: T) => string | number | null | undefined
}

function fallbackValue<T extends Record<string, any>>(row: T, key: string) {
  const value = row[key]
  if (value === null || value === undefined || value === '') return 'N/A'
  if (Array.isArray(value)) return value.length ? value.join(', ') : 'N/A'
  return String(value)
}

export default function SNMPDynamicTable<T extends Record<string, any>>({
  columns,
  rows,
  loading = false,
  error,
  emptyMessage = 'No data available.',
  searchPlaceholder = 'Search...',
  pageSize = 25,
}: {
  columns: SNMPTableColumn<T>[]
  rows: T[]
  loading?: boolean
  error?: string | null
  emptyMessage?: string
  searchPlaceholder?: string
  pageSize?: number
}) {
  const [search, setSearch] = useState('')
  const [sortKey, setSortKey] = useState<string | null>(null)
  const [sortAsc, setSortAsc] = useState(true)
  const [page, setPage] = useState(1)

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    const base = q
      ? rows.filter(row => columns.some(col => String(col.getValue?.(row) ?? fallbackValue(row, col.key)).toLowerCase().includes(q)))
      : rows
    if (!sortKey) return base
    const col = columns.find(c => c.key === sortKey)
    return [...base].sort((a, b) => {
      const av = col?.getValue?.(a) ?? fallbackValue(a, sortKey)
      const bv = col?.getValue?.(b) ?? fallbackValue(b, sortKey)
      return String(av).localeCompare(String(bv), undefined, { numeric: true }) * (sortAsc ? 1 : -1)
    })
  }, [columns, rows, search, sortKey, sortAsc])

  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize))
  const safePage = Math.min(page, totalPages)
  const visible = filtered.slice((safePage - 1) * pageSize, safePage * pageSize)

  const toggleSort = (key: string) => {
    if (sortKey === key) setSortAsc(v => !v)
    else {
      setSortKey(key)
      setSortAsc(true)
    }
  }

  if (loading) {
    return <div className="font-mono text-xs p-6 text-center" style={{ color: '#00d4ff' }}>Loading data...</div>
  }

  if (error) {
    return <div className="font-mono text-xs p-6 text-center" style={{ color: '#ff3366' }}>{error}</div>
  }

  return (
    <div className="space-y-3">
      <input
        value={search}
        onChange={event => { setSearch(event.target.value); setPage(1) }}
        placeholder={searchPlaceholder}
        className="w-full glass-bright rounded px-3 py-2 font-mono text-xs"
        style={{ border: '1px solid rgba(0,212,255,0.25)', color: '#c8d8ee', background: 'rgba(8,25,55,0.7)' }}
      />
      {filtered.length === 0 ? (
        <div className="font-mono text-xs p-6 text-center" style={{ color: '#8899bb' }}>{emptyMessage}</div>
      ) : (
        <>
          <div className="overflow-x-auto">
            <table className="w-full" style={{ minWidth: 760 }}>
              <thead>
                <tr style={{ borderBottom: '1px solid rgba(0,212,255,0.08)' }}>
                  {columns.map(col => (
                    <th key={col.key} className="text-left px-4 py-2.5 font-mono text-xs sticky top-0"
                      style={{ color: '#8899bb', background: 'rgba(8,25,55,0.95)' }}>
                      {col.sortable ? (
                        <button type="button" onClick={() => toggleSort(col.key)} className="flex items-center gap-1">
                          {col.label}
                          {sortKey === col.key ? (sortAsc ? '▲' : '▼') : ''}
                        </button>
                      ) : col.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {visible.map((row, index) => (
                  <tr key={String(row.id ?? row.interface_id ?? index)} style={{ borderBottom: '1px solid rgba(0,212,255,0.04)' }}>
                    {columns.map(col => (
                      <td key={col.key} className="px-4 py-3 font-mono text-xs" style={{ color: '#c8d8ee' }}>
                        {col.render ? col.render(row) : fallbackValue(row, col.key)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="flex flex-col sm:flex-row items-center justify-between gap-2 font-mono text-xs" style={{ color: '#8899bb' }}>
            <span>{filtered.length} row{filtered.length === 1 ? '' : 's'} · Page {safePage} of {totalPages}</span>
            <div className="flex items-center gap-2">
              <button type="button" disabled={safePage <= 1} onClick={() => setPage(p => Math.max(1, p - 1))}
                className="px-3 py-1 rounded" style={{ border: '1px solid rgba(0,212,255,0.2)', opacity: safePage <= 1 ? 0.5 : 1 }}>PREV</button>
              <button type="button" disabled={safePage >= totalPages} onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                className="px-3 py-1 rounded" style={{ border: '1px solid rgba(0,212,255,0.2)', opacity: safePage >= totalPages ? 0.5 : 1 }}>NEXT</button>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
