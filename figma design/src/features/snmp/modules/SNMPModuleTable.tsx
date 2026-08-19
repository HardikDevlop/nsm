import { useState, useMemo } from 'react';
import GlassCard from '../../../components/GlassCard';
import { SNMPTableColumn } from './snmpModuleRegistry';
import { formatBytes, formatSpeed, formatSensorValue, getStatusColor, getHealthColor } from './snmpModuleRegistry';

interface SNMPModuleTableProps<T> {
  rows: T[];
  loading?: boolean;
  error?: string | null;
  emptyMessage?: string;
  searchPlaceholder?: string;
  columns: SNMPTableColumn[];
  defaultSortKey?: string;
  defaultSortOrder?: 'asc' | 'desc';
  onRowClick?: (row: T) => void;
  rowKey?: keyof T | ((row: T) => string);
  pageSize?: number;
  showPagination?: boolean;
  className?: string;
}

function SNMPModuleTable<T>({
  rows,
  loading = false,
  error = null,
  emptyMessage = 'No data available.',
  searchPlaceholder = 'Search...',
  columns,
  defaultSortKey,
  defaultSortOrder = 'asc',
  onRowClick,
  rowKey = 'id' as keyof T,
  pageSize: initialPageSize = 50,
  showPagination = true,
  className = '',
}: SNMPModuleTableProps<T>) {
  const [search, setSearch] = useState('');
  const [sortKey, setSortKey] = useState<string | null>(defaultSortKey || null);
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>(defaultSortOrder);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(initialPageSize);

  const getRowKey = (row: T): string => {
    if (typeof rowKey === 'function') return rowKey(row);
    return String(row[rowKey]);
  };

  const filteredRows = useMemo(() => {
    let result = rows;

    if (search) {
      const q = search.toLowerCase();
      result = result.filter((row) =>
        columns.some((col) => {
          const value = (row as any)[col.key];
          if (value === null || value === undefined) return false;
          return String(value).toLowerCase().includes(q);
        })
      );
    }

    if (sortKey) {
      const col = columns.find((c) => c.key === sortKey);
      if (col?.sortable) {
        result = [...result].sort((a, b) => {
          const aVal = (a as any)[sortKey];
          const bVal = (b as any)[sortKey];
          if (aVal === null || aVal === undefined) return 1;
          if (bVal === null || bVal === undefined) return -1;
          const cmp = aVal < bVal ? -1 : aVal > bVal ? 1 : 0;
          return sortOrder === 'asc' ? cmp : -cmp;
        });
      }
    }

    return result;
  }, [rows, search, sortKey, sortOrder, columns]);

  const totalPages = Math.ceil(filteredRows.length / pageSize) || 1;
  const paginatedRows = useMemo(() => {
    if (!showPagination) return filteredRows;
    const start = (page - 1) * pageSize;
    return filteredRows.slice(start, start + pageSize);
  }, [filteredRows, page, pageSize, showPagination]);

  const handleSort = (columnKey: string) => {
    const col = columns.find((c) => c.key === columnKey);
    if (!col?.sortable) return;
    if (sortKey === columnKey) {
      setSortOrder((prev) => (prev === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(columnKey);
      setSortOrder('asc');
    }
    setPage(1);
  };

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setPage(1);
  };

  const handlePageChange = (newPage: number) => {
    if (newPage >= 1 && newPage <= totalPages) {
      setPage(newPage);
    }
  };

  const renderCell = (row: T, column: SNMPTableColumn) => {
    const value = (row as any)[column.key];

    if (column.render) {
      return column.render(row);
    }

    switch (column.type) {
      case 'status': {
        const status = String(value || 'unknown').toLowerCase();
        const color = getStatusColor(status);
        return (
          <span
            className="font-mono text-[10px] px-1.5 py-0.5 rounded"
            style={{
              background: `${color}15`,
              color,
              border: `1px solid ${color}30`,
            }}
          >
            {String(value).toUpperCase()}
          </span>
        );
      }
      case 'bytes':
        return <span className="font-mono text-xs" style={{ color: '#c8d8ee' }}>{formatBytes(value)}</span>;
      case 'percent': {
        const pct = Number(value);
        const color = pct >= 90 ? '#ff3366' : pct >= 75 ? '#ffaa00' : '#00d4ff';
        return <span className="font-mono text-xs font-semibold" style={{ color }}>{pct.toFixed(1)}%</span>;
      }
      case 'timestamp':
        return <span className="font-mono text-[10px]" style={{ color: '#8899bb' }}>{value ? new Date(value).toLocaleString() : '—'}</span>;
      case 'number':
        return <span className="font-mono text-xs" style={{ color: '#c8d8ee' }}>{value !== null && value !== undefined ? String(value) : '—'}</span>;
      case 'custom':
        return <span className="font-mono text-xs" style={{ color: '#c8d8ee' }}>{value !== null && value !== undefined ? String(value) : '—'}</span>;
      default:
        return <span className="font-mono text-xs" style={{ color: '#c8d8ee' }}>{value !== null && value !== undefined ? String(value) : '—'}</span>;
    }
  };

  if (loading) {
    return (
      <GlassCard className={className}>
        <div className="flex items-center justify-center p-12">
          <div className="font-mono text-sm" style={{ color: '#00d4ff' }}>Loading data...</div>
        </div>
      </GlassCard>
    );
  }

  if (error) {
    return (
      <GlassCard className={className}>
        <div className="font-mono text-xs p-4 rounded text-center" style={{ color: '#ff3366', background: 'rgba(255,51,102,0.1)', border: '1px solid rgba(255,51,102,0.3)' }}>
          {error}
        </div>
      </GlassCard>
    );
  }

  if (filteredRows.length === 0) {
    return (
      <GlassCard className={className}>
        <div className="font-mono text-xs p-6 text-center" style={{ color: '#8899bb' }}>
          {emptyMessage}
        </div>
      </GlassCard>
    );
  }

  return (
    <GlassCard className={`overflow-hidden ${className}`}>
      <div className="p-3" style={{ borderBottom: '1px solid rgba(0,212,255,0.1)' }}>
        <form onSubmit={handleSearch} className="flex gap-3">
          <div className="flex-1 min-w-[200px]">
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={searchPlaceholder}
              className="w-full glass-bright rounded px-3 py-2 font-mono text-xs"
              style={{ border: '1px solid rgba(0,212,255,0.25)', color: '#c8d8ee', background: 'rgba(8,25,55,0.7)' }}
            />
          </div>
        </form>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full" style={{ minWidth: 800 }}>
          <thead>
            <tr style={{ borderBottom: '1px solid rgba(0,212,255,0.08)' }}>
              {columns.map((col) => (
                <th
                  key={col.key}
                  onClick={() => col.sortable && handleSort(col.key)}
                  className={`text-left px-4 py-2.5 font-mono text-xs sticky top-0 select-none ${col.sortable ? 'cursor-pointer' : ''}`}
                  style={{
                    color: '#8899bb',
                    background: 'rgba(8,25,55,0.95)',
                    userSelect: 'none',
                  }}
                >
                  <div className="flex items-center gap-1">
                    {col.label}
                    {col.sortable && sortKey === col.key && (
                      <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="#00d4ff" strokeWidth="2">
                        {sortOrder === 'asc' ? <path d="M18 15l-6-6-6 6" /> : <path d="M6 9l6 6 6-6" />}
                      </svg>
                    )}
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {paginatedRows.map((row, index) => (
              <tr
                key={getRowKey(row)}
                onClick={() => onRowClick?.(row)}
                style={{
                  borderBottom: '1px solid rgba(0,212,255,0.04)',
                  cursor: onRowClick ? 'pointer' : 'default',
                  background: index % 2 === 0 ? 'transparent' : 'rgba(0,212,255,0.01)',
                }}
              >
                {columns.map((col) => (
                  <td key={col.key} className="px-4 py-2">
                    {renderCell(row, col)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {showPagination && totalPages > 1 && (
        <div className="p-4 flex flex-col sm:flex-row items-center justify-between gap-3" style={{ borderTop: '1px solid rgba(0,212,255,0.1)' }}>
          <div className="font-mono text-xs" style={{ color: '#8899bb' }}>
            Showing {((page - 1) * pageSize) + 1} to {Math.min(page * pageSize, filteredRows.length)} of {filteredRows.length}
          </div>
          <div className="flex items-center gap-2">
            <select
              value={pageSize}
              onChange={(e) => { setPageSize(Number(e.target.value)); setPage(1); }}
              className="glass-bright rounded px-2 py-1 font-mono text-xs"
              style={{ border: '1px solid rgba(0,212,255,0.25)', color: '#c8d8ee', background: 'rgba(8,25,55,0.7)' }}>
              <option value={25}>25</option>
              <option value={50}>50</option>
              <option value={100}>100</option>
              <option value={200}>200</option>
            </select>
            <button onClick={() => handlePageChange(page - 1)} disabled={page === 1}
              className="glass-bright px-3 py-1.5 rounded font-mono text-xs"
              style={{ border: '1px solid rgba(0,212,255,0.25)', color: '#00d4ff', opacity: page === 1 ? 0.4 : 1 }}>
              PREV
            </button>
            <span className="font-mono text-xs px-2" style={{ color: '#c8d8ee' }}>
              Page {page} / {totalPages}
            </span>
            <button onClick={() => handlePageChange(page + 1)} disabled={page === totalPages}
              className="glass-bright px-3 py-1.5 rounded font-mono text-xs"
              style={{ border: '1px solid rgba(0,212,255,0.25)', color: '#00d4ff', opacity: page === totalPages ? 0.4 : 1 }}>
              NEXT
            </button>
          </div>
        </div>
      )}
    </GlassCard>
  );
}

export default SNMPModuleTable;
