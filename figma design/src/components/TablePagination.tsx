const selectStyle: React.CSSProperties = {
  background: 'var(--t-border-light, rgba(255,255,255,0.04))',
  border: '1px solid var(--t-border-alpha)',
  color: 'var(--t-text)',
  outline: 'none',
}

type TablePaginationProps = {
  page: number
  pageCount: number
  pageSize: number
  startItem: number
  endItem: number
  totalItems: number
  onPageChange: (page: number) => void
  onPageSizeChange: (pageSize: number) => void
  pageSizes?: number[]
}

export default function TablePagination({
  page,
  pageCount,
  pageSize,
  startItem,
  endItem,
  totalItems,
  onPageChange,
  onPageSizeChange,
  pageSizes = [25, 50, 75, 100],
}: TablePaginationProps) {
  return (
    <div className="flex flex-col sm:flex-row items-center justify-between gap-3 px-4 py-3" style={{ borderTop: '1px solid var(--t-border-alpha)' }}>
      <span className="font-mono text-xs" style={{ color: 'var(--t-muted)' }}>
        Showing {startItem}-{endItem} of {totalItems}
      </span>
      <div className="flex items-center gap-2">
        <select
          value={pageSize}
          onChange={e => onPageSizeChange(Number(e.target.value))}
          className="rounded px-2 py-1 font-mono text-xs"
          style={selectStyle}
        >
          {pageSizes.map(size => (
            <option key={size} value={size}>{size} per page</option>
          ))}
        </select>
        <button
          disabled={page <= 1}
          onClick={() => onPageChange(Math.max(1, page - 1))}
          className="rounded px-2 py-1 font-mono text-xs disabled:opacity-40"
          style={selectStyle}
        >
          PREV
        </button>
        <span className="font-mono text-xs" style={{ color: 'var(--t-muted)' }}>
          {page} / {pageCount}
        </span>
        <button
          disabled={page >= pageCount}
          onClick={() => onPageChange(Math.min(pageCount, page + 1))}
          className="rounded px-2 py-1 font-mono text-xs disabled:opacity-40"
          style={selectStyle}
        >
          NEXT
        </button>
      </div>
    </div>
  )
}
